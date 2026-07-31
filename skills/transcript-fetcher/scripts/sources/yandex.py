"""Yandex VH / Strm source adapter — **ASR-only by design**.

Targets the player behind Yandex Cloud webinar and stream recordings:

    https://runtime.strm.yandex.ru/player/episode/<EPISODE_ID>
    https://frontend.vh.yandex.ru/player/<EPISODE_ID>

Why this adapter is thin
------------------------
yt-dlp has no extractor for ``runtime.strm.yandex.ru`` (it returns
``Unsupported URL``), but its **generic** extractor handles the signed
HLS/DASH manifest URL directly. So the only genuinely new logic here is a
**resolver**: episode id -> signed manifest URL. Everything downstream —
the audio-minimal download, silence removal, the ASR backend chain, the
stat sidecar, the description sidecar — is reused verbatim from
:mod:`sources._ytdlp_media`, :mod:`sources._description` and :mod:`asr`,
exactly as :mod:`sources.x` does.

No caption path
---------------
Unlike :mod:`sources.x` (captions-first, ASR-fallback), this adapter goes
**straight to ASR**. That is not a shortcut: the player carries no caption
track at all. Verified five independent ways across five distinct
episodes — the config JSON has no subtitle/caption/track key, the HLS
master has zero ``#EXT-X-MEDIA`` tags, the DASH manifest has only
``contentType="video"`` and ``contentType="audio" lang="rus"``
AdaptationSets, ``yt-dlp --list-subs`` reports ``has no subtitles``, and a
live player reports ``video.textTracks: []``. A caption ladder here would
be dead code that costs a round-trip and can never succeed.

Traps this module exists to avoid
---------------------------------
1. **The config's ``duration`` field lies.** It overstates every episode —
   4365 vs a real 3800 s, and 43970 vs a real 8825 s (~5x) on the samples
   used to build this. Ground truth is the sum of ``#EXTINF`` in the media
   playlist (:func:`probe_duration_via_manifest`), which is what the
   download/ASR timeout budget derives from. Trusting the JSON field would
   blow the timeouts apart.
2. **Signed URLs are per-request and short-lived** (~48 h; the ``ysign1``
   value differs on every config fetch), so they are never cached —
   :func:`resolve_streams` runs fresh on every call.
3. **Never point ffmpeg at the HLS *master* playlist.** It lists ~79
   ``#EXT-X-STREAM-INF`` variants and ffmpeg opens all of them, hanging
   past any sane timeout. This module hands the manifest to yt-dlp, which
   resolves a single variant itself.
4. **yt-dlp reports "success" too loosely.** ``download_audio`` returns a
   non-None path whenever ANY ``media.*`` artefact is left in the workdir,
   even when yt-dlp exited non-zero (e.g. a postprocessor error leaving a
   complete-but-unconverted container). Gating the DASH->HLS fallback on
   ``media is not None`` alone silently defeats the fallback and swallows
   the real error, so :func:`fetch_yandex_transcript` also requires an
   empty ``stderr`` and purges stale artefacts between attempts.

Auth: none. The config endpoint answers HTTP 200 with no headers — the
SmartCaptcha lives on the *content* site (e.g. ``aistudio.yandex.ru``),
not on the player host. ``cookies_file`` is accepted for contract parity
with the sibling adapters and honoured if supplied.
"""
from __future__ import annotations

import http.client
import json
import re
import shutil
import tempfile
import urllib.error
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.request import Request

from asr._base import DEFAULT_ASR_TIMEOUT_SEC
from . import _ytdlp_media as ytm
from ._cookies import build_authenticated_opener
from ._description import write_description_md
from ._log import make_logger
from ._stat import (
    MissingDependencyError,
    SourceAuthError,
    SourceRateLimitError,
    TranscriptFetchError,
    TranscriptStat,
)
from ._vtt_to_text import count_speaker_turns
from .youtube import DEFAULT_TIMEOUT_SEC, _coerce_int

# Kept in sync with fetch.py's _SOURCE_BY_HOST entries for this adapter.
YANDEX_HOSTS = (
    "runtime.strm.yandex.ru",
    "frontend.vh.yandex.ru",
    "strm.yandex.ru",
)

# Hosts a resolved stream URL is allowed to live on. The manifest URL comes
# from a remote JSON document and is handed to a subprocess, so it is
# untrusted input: without this allowlist a hostile or compromised response
# could redirect the download anywhere (SSRF).
#
# Deliberately an EXACT-HOST set, not a domain-suffix match. An earlier
# revision allowed ``*.yandexcloud.net``, which is object storage: any user
# can create a bucket there, so a suffix rule turned the allowlist into an
# open redirect (`mybucket.storage.yandexcloud.net` passed). Streams live on
# the strm/vh hosts only; the wildcard bought nothing and cost the guarantee.
_ALLOWED_STREAM_HOSTS = frozenset(
    {
        "strm.yandex.ru",
        "runtime.strm.yandex.ru",
        "frontend.vh.yandex.ru",
        "vh.yandex.ru",
    }
)

CONFIG_ENDPOINT = "https://runtime.strm.yandex.ru/player/episode/{episode_id}?format=json"

# A config/manifest document is small (observed: 3 KB JSON, 40 KB master,
# 750 KB media playlist). Cap the read so a hostile or misconfigured origin
# cannot OOM us — `timeout` bounds individual socket reads, NOT total
# transfer, so a slow-drip 600 MB body would otherwise be read in full.
# Mirrors sources/skool.py's `_MAX_HTML_BYTES` precedent.
_MAX_DOC_BYTES = 8 * 1024 * 1024

# Episode ids observed are ``vple…`` but the id is opaque; accept a
# conservative slug and reject everything else. This is the ONLY thing
# interpolated into CONFIG_ENDPOINT, so it must not admit ``/``, ``?``,
# ``#``, a scheme, or a trailing newline.
#
# `fullmatch`, never `match`: with `match` the anchor `$` also matches
# BEFORE a single trailing newline, so `"abcdefgh\n"` slipped through and
# reached http.client as a control character in the URL.
_EPISODE_ID_RE = re.compile(r"[A-Za-z0-9_-]{8,64}")

# The trailing `(?![A-Za-z0-9_-])` matters: without it a 100-char slug is
# CAPTURED TRUNCATED at 64 chars and then passes validation, so the adapter
# would silently resolve a DIFFERENT episode than the URL named.
_URL_PATTERNS = (
    re.compile(r"/player/episode/([A-Za-z0-9_-]{8,64})(?![A-Za-z0-9_-])"),
    re.compile(
        r"frontend\.vh\.yandex\.ru/player/([A-Za-z0-9_-]{8,64})(?![A-Za-z0-9_-])"
    ),
)


def is_yandex_player_url(url: str) -> bool:
    """True when ``url``'s hostname is one this adapter actually serves.

    ``fetch.py``'s dispatch table already gates the CLI, but this module is
    also a public library entry point: without a host check of its own,
    ``extract_episode_id`` matched the ``/player/episode/<id>`` path shape on
    ANY host, so a direct call with ``https://evil.example.com/player/episode/…``
    was accepted and recorded in ``stat.url`` next to content that in fact
    came from ``runtime.strm.yandex.ru``. Not an SSRF (the config endpoint
    host is a hard constant) — but the stat must not misreport its source.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in set(YANDEX_HOSTS)


def extract_episode_id(url: str) -> Optional[str]:
    """Pull the opaque episode id out of a Yandex VH/Strm player URL.

    Returns ``None`` when the URL is not a Yandex player URL or carries no
    recognisable id — the caller turns that into a clear error rather than
    guessing.
    """
    if not url or not is_yandex_player_url(url):
        return None
    for pat in _URL_PATTERNS:
        m = pat.search(url)
        if m and _EPISODE_ID_RE.fullmatch(m.group(1)):
            return m.group(1)
    return None


def _http_get(url: str, *, timeout_sec: int, cookies_file: Optional[Path] = None) -> bytes:
    """GET a small document with redirects pinned to the allowlist.

    Uses the shared hardened opener rather than ``urllib.request.urlopen``:
    the default global opener follows a cross-host 302 and carries
    ``FileHandler``/``FTPHandler``, so the pre-flight allowlist check on the
    *original* URL guaranteed nothing about where the bytes actually came
    from. ``_RestrictedRedirectHandler`` re-checks every hop.
    """
    opener = build_authenticated_opener(
        cookies_file, allowed_hosts=_ALLOWED_STREAM_HOSTS | set(YANDEX_HOSTS)
    )
    try:
        with opener.open(Request(url, method="GET"), timeout=timeout_sec) as resp:
            raw = resp.read(_MAX_DOC_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SourceAuthError(
                f"Yandex player refused access to {url} (HTTP {e.code}). "
                "The recording may be private or region-locked."
            ) from e
        if e.code == 429:
            raise SourceRateLimitError(
                f"Yandex player rate-limited the request (HTTP 429) for {url}."
            ) from e
        raise TranscriptFetchError(
            f"Yandex player returned HTTP {e.code} for {url}"
        ) from e
    except urllib.error.URLError as e:
        raise TranscriptFetchError(f"could not reach {url}: {e.reason}") from e
    # urllib does NOT wrap failures raised during getresponse()/read(): a
    # half-sent body surfaces as a bare TimeoutError or http.client
    # IncompleteRead, neither of which is a URLError. Without these the
    # exception escaped as an unexpected exit 1.
    except (http.client.HTTPException, TimeoutError, OSError) as e:
        raise TranscriptFetchError(
            f"transport error fetching {url}: {type(e).__name__}: {e}"
        ) from e
    if len(raw) > _MAX_DOC_BYTES:
        raise TranscriptFetchError(
            f"refusing oversized response from {url} (> {_MAX_DOC_BYTES} bytes)"
        )
    return raw


def _is_allowed_stream_url(url: str) -> bool:
    """True when ``url`` is https on an exactly-allowlisted Yandex host."""
    try:
        p = urlparse(url)
    except ValueError:
        # urlparse raises on a malformed IPv6 literal; a hostile config must
        # not turn into an uncaught ValueError (which fetch.py maps to a
        # misleading exit-2 "UsageError" about the user's own URL).
        return False
    if p.scheme != "https":
        return False
    return (p.hostname or "").lower() in _ALLOWED_STREAM_HOSTS


def resolve_streams(
    episode_id: str,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cookies_file: Optional[Path] = None,
    log=None,
) -> dict:
    """Resolve an episode id to its signed manifest URLs + metadata.

    Returns a dict with ``hls`` / ``dash`` (either may be ``None``), plus
    ``title``, ``description``, ``json_duration`` and ``rejected`` (stream
    URLs dropped for living off-allowlist).

    ``json_duration`` is deliberately named to flag that it is NOT
    trustworthy (module docstring, trap 1). Nothing here derives a timeout
    from it; it is carried only so a caller can compare.

    Never cached: the signature is minted per request and expires (~48 h).
    """
    if not _EPISODE_ID_RE.fullmatch(episode_id or ""):
        raise TranscriptFetchError(f"refusing malformed Yandex episode id: {episode_id!r}")

    raw = _http_get(
        CONFIG_ENDPOINT.format(episode_id=episode_id),
        timeout_sec=timeout_sec,
        cookies_file=cookies_file,
    )
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise TranscriptFetchError(
            f"Yandex player config for {episode_id} was not valid JSON: {e}"
        ) from e
    # Valid JSON that is not an object (e.g. `[]`, `"x"`, `null`) would sail
    # past the decode guard and die on .get() with an AttributeError -> the
    # undocumented exit 1. Reject it as the malformed payload it is.
    if not isinstance(doc, dict):
        raise TranscriptFetchError(
            f"Yandex player config for {episode_id} was not a JSON object "
            f"(got {type(doc).__name__})"
        )

    # The payload nests everything under `content`; tolerate a flat shape too.
    content = doc.get("content") if isinstance(doc.get("content"), dict) else doc

    out: dict = {
        "episode_id": episode_id,
        "title": content.get("title"),
        "description": content.get("description"),
        "json_duration": _coerce_int(content.get("duration")),
        "hls": None,
        "dash": None,
        "rejected": [],
    }
    for stream in content.get("streams") or []:
        if not isinstance(stream, dict):
            continue
        kind = (stream.get("type") or "").lower()
        url = stream.get("url")
        if not url or kind not in ("hls", "dash"):
            continue
        if not _is_allowed_stream_url(url):
            # Do NOT hand an off-host URL to yt-dlp. Record it so the skip is
            # actually observable — a bare `continue` made a hostile-looking
            # config indistinguishable from one that simply lacked the format.
            out["rejected"].append(f"{kind}: {url}")
            if log is not None:
                log(f"refusing off-allowlist {kind} stream: {url}")
            continue
        out[kind] = url

    if not out["hls"] and not out["dash"]:
        detail = (
            f" (rejected off-allowlist: {'; '.join(out['rejected'])})"
            if out["rejected"]
            else ""
        )
        raise TranscriptFetchError(
            f"Yandex player config for {episode_id} carried no usable "
            f"HLS/DASH stream on an allowlisted host{detail}."
        )
    return out


def probe_duration_via_manifest(
    hls_master_url: str,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cookies_file: Optional[Path] = None,
) -> Optional[int]:
    """Real duration in seconds: sum of ``#EXTINF`` in the media playlist.

    This is the ONLY trustworthy duration for these recordings (module
    docstring, trap 1). Resolves master -> first variant -> media playlist.
    Returns ``None`` if anything about the manifest is unexpected — the
    caller then falls back to a duration-free timeout budget rather than
    trusting the config's inflated field.
    """
    try:
        master = _http_get(
            hls_master_url, timeout_sec=timeout_sec, cookies_file=cookies_file
        ).decode("utf-8", errors="replace")
    except (TranscriptFetchError, SourceAuthError, SourceRateLimitError):
        return None

    variant: Optional[str] = None
    lines = master.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
            candidate = lines[i + 1].strip()
            if candidate and not candidate.startswith("#"):
                variant = urljoin(hls_master_url, candidate)
                break
    if variant is None:
        # Already a media playlist? Sum it directly.
        return _sum_extinf(master)

    if not _is_allowed_stream_url(variant):
        return None
    try:
        media = _http_get(
            variant, timeout_sec=timeout_sec, cookies_file=cookies_file
        ).decode("utf-8", errors="replace")
    except (TranscriptFetchError, SourceAuthError, SourceRateLimitError):
        return None
    return _sum_extinf(media)


def _sum_extinf(playlist: str) -> Optional[int]:
    """Sum ``#EXTINF:<seconds>`` durations. ``None`` when unusable."""
    vals = re.findall(r"#EXTINF:\s*([0-9]+(?:\.[0-9]+)?)", playlist)
    if not vals:
        return None
    try:
        total = sum(float(v) for v in vals)
    except (ValueError, OverflowError):
        return None
    # A crafted playlist can carry `#EXTINF:1e400` -> inf, and int(round(inf))
    # raises OverflowError. The contract is "None when unexpected", not a crash.
    if total != total or total in (float("inf"), float("-inf")) or total < 0:
        return None
    try:
        return int(round(total))
    except (OverflowError, ValueError):
        return None


def manifest_candidates(streams: dict, *, clipping: bool) -> list[tuple[str, str]]:
    """Ordered ``(kind, url)`` manifests to try for the audio download.

    Order depends on whether the download will be **clipped**
    (``--max-duration-min``), because clipping changes who opens the input:

    * **No clipping** -> prefer **DASH**. Its audio-only ``Representation``
      (mp4a.40.2 192 kbps, ``lang="rus"``) means yt-dlp downloads zero video
      bytes; the HLS variants are all muxed A/V, so the HLS path pays for a
      144p video track it immediately discards.
    * **Clipping** -> prefer **HLS**. ``--download-sections`` makes yt-dlp
      hand the input to **ffmpeg**, and ffmpeg cannot open Yandex's DASH
      manifest at all (``Invalid data found when processing input`` — it does
      not follow the 302 + ``BaseURL`` indirection). This is not theoretical:
      it is the exact failure the first end-to-end run hit.

    Either way the other manifest is kept as a fallback, so a single-format
    outage degrades instead of failing the run.
    """
    order = ("hls", "dash") if clipping else ("dash", "hls")
    return [(kind, streams[kind]) for kind in order if streams.get(kind)]


def _purge_media(workdir: Path) -> None:
    """Delete ``media.*`` artefacts left by a previous download attempt.

    ``find_downloaded_media`` globs ``media.*``, so without this a failed
    first candidate's leftover container is picked up as the second
    candidate's "successful" download.
    """
    for leftover in workdir.glob("media.*"):
        try:
            leftover.unlink()
        except OSError:
            pass


def _raise_for_media_failure(stderr: Optional[str], url: str) -> None:
    """Map a yt-dlp media failure onto the documented exit codes.

    Without this every download failure collapsed into a bare
    ``TranscriptFetchError`` -> exit 3, so an HTTP 403 reported exit 3 where
    SKILL.md §Failure semantics promises 5, and a 429 reported 3 where it
    promises 6. ``classify_failure`` is the same public helper x.py routes
    through, so the two ASR adapters now agree.
    """
    kind = ytm.classify_failure(stderr or "")
    tail = "; ".join((stderr or "").strip().splitlines()[-3:])
    if kind == "auth":
        raise SourceAuthError(
            f"Yandex refused the media download for {url} (auth/forbidden): {tail}"
        )
    if kind == "rate":
        raise SourceRateLimitError(
            f"Yandex rate-limited the media download for {url}: {tail}"
        )
    raise TranscriptFetchError(f"audio download failed for {url}: {tail}")


def fetch_yandex_transcript(
    url: str,
    out_path: Path,
    *,
    lang: str = "ru",
    yt_dlp_bin: Optional[str] = None,
    workdir: Optional[Path] = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    concurrent_fragments: Optional[int] = None,
    media_timeout_sec: Optional[int] = None,
    cookies_file: Optional[Path] = None,
    cookies_from_browser: Optional[str] = None,
    with_description: bool = False,
    description_only: bool = False,
    asr_allow_cloud: bool = False,
    asr_model: Optional[str] = None,
    asr_timeout_sec: int = DEFAULT_ASR_TIMEOUT_SEC,
    max_duration_min: Optional[float] = None,
    remove_silence: bool = True,
    debug: bool = False,
) -> TranscriptStat:
    """Transcribe a Yandex VH/Strm recording via ASR.

    Same return contract as the other adapters (:class:`TranscriptStat`).
    Raises ``SourceAuthError`` / ``SourceRateLimitError`` /
    ``TranscriptFetchError`` / ``MissingDependencyError``, all mapped to
    exit codes by the CLI.
    """
    log = make_logger(debug)
    out_path = Path(out_path)

    episode_id = extract_episode_id(url)
    if episode_id is None:
        raise TranscriptFetchError(
            f"not a recognisable Yandex VH/Strm player URL: {url} — expected "
            "https://runtime.strm.yandex.ru/player/episode/<ID>"
        )

    log("Detected Yandex VH/Strm episode")

    if description_only:
        with_description = True

    # ffmpeg is genuinely required for the ASR path (HLS/DASH-only source, so
    # without it the download is not a container an ASR engine can open) —
    # but NOT for `--description-only`, which touches no media at all. The
    # guard therefore lives inside the media branch, as it does in x.py.
    cleanup_workdir = False
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="transcript-fetcher-yandex-"))
        cleanup_workdir = True
    else:
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    try:
        # ---- 1. resolve manifests (fresh — signatures are per-request) -- #
        log("Resolving stream manifests")
        streams = resolve_streams(
            episode_id, timeout_sec=timeout_sec, cookies_file=cookies_file, log=log
        )
        for rej in streams.get("rejected", []):
            notes.append(f"refused off-allowlist stream {rej}")

        # ---- 2. real duration from the media playlist, NOT the JSON ---- #
        real_duration: Optional[int] = None
        if streams["hls"]:
            log("Probing real duration from the media playlist")
            real_duration = probe_duration_via_manifest(
                streams["hls"], timeout_sec=timeout_sec, cookies_file=cookies_file
            )
        if real_duration is not None:
            notes.append(f"duration: {real_duration}s from #EXTINF sum")
            if streams["json_duration"] and streams["json_duration"] != real_duration:
                notes.append(
                    f"config JSON duration ({streams['json_duration']}s) is wrong — ignored"
                )
        else:
            # DASH-only configs have no playlist to sum, so the budget falls
            # back to media_timeout_for(None) = 1800 s. Say so: a silent 1800 s
            # ceiling on a 2 h recording looks like a hang, not a budget.
            notes.append(
                "duration: unknown (no HLS playlist to sum) — using the default "
                "media budget, which may be short for a long recording"
            )

        # The budget must reflect what we will actually DOWNLOAD. With
        # --max-duration-min the download is clipped, so deriving the budget
        # from the full duration hands a 6 h ceiling to a 10 min job and turns
        # a stall into a 6 h hang. Mirrors the clamp in x.py.
        budget_duration = real_duration
        if (
            budget_duration is not None
            and max_duration_min
            and max_duration_min > 0
            and ytm.ffmpeg_available()
        ):
            budget_duration = min(budget_duration, max_duration_min * 60)
        media_budget = (
            media_timeout_sec
            if media_timeout_sec is not None
            else ytm.media_timeout_for(budget_duration)
        )

        plain = ""
        chosen_kind: Optional[str] = None
        chosen_lang: Optional[str] = None
        transcript_origin: Optional[str] = None
        asr_backend: Optional[str] = None
        asr_model_used: Optional[str] = None
        media_path: Optional[Path] = None

        if not description_only:
            if not ytm.ffmpeg_available():
                raise MissingDependencyError(
                    "ffmpeg is required to transcribe Yandex VH/Strm media: it is "
                    "an HLS/DASH stream, and without ffmpeg the downloaded media "
                    "is not a valid container the ASR engine can open.",
                    remediation=(
                        "Install ffmpeg — `brew install ffmpeg` (macOS) / "
                        "`sudo apt-get install ffmpeg` (Linux), or "
                        "`python scripts/install_components.py --system --run`."
                    ),
                )

            # ---- 3. audio download, DASH/HLS in clipping-aware order ---- #
            clipping = bool(max_duration_min and max_duration_min > 0)
            candidates = manifest_candidates(streams, clipping=clipping)
            media = None
            last_err: Optional[str] = None
            failures: list[str] = []
            for kind, manifest in candidates:
                log(f"Downloading audio via {kind.upper()}")
                _purge_media(workdir)
                cand_media, derr = ytm.download_audio(
                    manifest,
                    workdir,
                    timeout_sec=media_budget,
                    cookies_file=cookies_file,
                    cookies_from_browser=cookies_from_browser,
                    yt_dlp_bin=yt_dlp_bin,
                    max_duration_min=max_duration_min,
                    concurrent_fragments=concurrent_fragments,
                )
                # `download_audio` returns a path whenever ANY media.* artefact
                # survives, EVEN when yt-dlp exited non-zero — so a
                # postprocessor failure leaves a complete-but-wrong container
                # and looks like success. Require a clean stderr too, else the
                # fallback this whole module exists for never fires.
                if cand_media is not None and not derr:
                    media = cand_media
                    if kind != candidates[0][0]:
                        notes.append(f"audio: fell back to {kind.upper()} manifest")
                    break
                last_err = derr or f"{kind}: no media produced"
                failures.append(f"{kind}: {'; '.join((derr or '').strip().splitlines()[-2:])}")
                log(f"{kind.upper()} attempt failed, trying next manifest")
            if media is None:
                _purge_media(workdir)
                notes.append("audio: every manifest failed — " + " | ".join(failures))
                _raise_for_media_failure(last_err, url)
            media_path = media

            # ---- 4. strip long silences (cuts Whisper filler on dead air) #
            media_for_asr = media
            if remove_silence:
                log("Removing long silences")
                desilenced, snote = ytm.remove_silence(
                    media, workdir, timeout_sec=asr_timeout_sec or DEFAULT_ASR_TIMEOUT_SEC
                )
                notes.append(snote)
                if desilenced is not None:
                    media_for_asr = desilenced

            # ---- 5. ASR ------------------------------------------------ #
            from asr import transcribe_with_fallback

            result = transcribe_with_fallback(
                media_for_asr,
                lang=lang,
                allow_cloud=asr_allow_cloud,
                model=asr_model,
                timeout_sec=asr_timeout_sec or DEFAULT_ASR_TIMEOUT_SEC,
                log=log,
            )
            plain = result.text
            chosen_kind = "asr"
            chosen_lang = result.language or lang
            transcript_origin = result.backend_name
            asr_backend = result.backend_name
            asr_model_used = result.model
            notes.append(f"transcribed via ASR backend '{result.backend_name}'")
            notes.append("Yandex VH/Strm carries no caption track — ASR is the only path")

            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(plain, encoding="utf-8")

        # ---- 6. stat ---------------------------------------------------- #
        stat = TranscriptStat(
            source="yandex",
            url=url,
            video_id=episode_id,
            output_path=str(out_path),
            chosen_track_kind=chosen_kind,
            chosen_track_lang=chosen_lang,
            char_count=len(plain),
            speaker_turn_count=count_speaker_turns(plain) if plain else 0,
            quality_flag=None,
            notes=notes,
            transcript_origin=transcript_origin,
            asr_backend=asr_backend,
            asr_model=asr_model_used,
        )
        stat.title = streams.get("title")
        stat.duration_sec = real_duration

        # Last-resort duration fill from the downloaded media.
        if stat.duration_sec is None and media_path is not None:
            probed = ytm.probe_media_duration(media_path)
            if probed is not None:
                stat.duration_sec = probed
                stat.notes.append("duration: derived via ffprobe")

        # ---- 7. description sidecar ------------------------------------- #
        if with_description:
            stat.uploader = "Yandex"
            desc_path = write_description_md(
                out_path,
                frontmatter={
                    "source": "yandex",
                    "url": url,
                    "episode_id": episode_id,
                    "title": streams.get("title"),
                    "uploader": "Yandex",
                    "duration_sec": stat.duration_sec,
                },
                title=streams.get("title"),
                body=(streams.get("description") or "").strip(),
            )
            stat.description_path = str(desc_path)
            stat.notes.append("description: wrote .description.md")

        return stat
    finally:
        log("Cleaning temporary files")
        if cleanup_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
        log("Finished")

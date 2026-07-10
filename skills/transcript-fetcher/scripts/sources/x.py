"""X.com (Twitter) source adapter — captions-first, ASR-fallback.

Handles native X status video AND Broadcasts/Spaces. The provider encapsulates
the **entire** decision (use pre-existing captions vs transcribe audio) so the
CLI core in ``fetch.py`` never special-cases X — it just dispatches to
:func:`fetch_x_transcript` like any other source (the user's explicit
"another provider, not conditionals in core" requirement).

Pipeline (arch-016 §2.2)::

    probe metadata (yt-dlp -J, one call)
        ├─ captions present for a ladder lang ─► download VTT ─► clean  (origin: embedded-captions)
        └─ none ─────────────────────────────► download audio ─► ASR    (origin: <backend>)

All intermediate files live under one tempdir removed in ``finally`` even on
error (no residual artifacts). ASR is delegated to the pluggable
:mod:`asr` registry — adding a new engine never touches this file.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

from asr._base import DEFAULT_ASR_TIMEOUT_SEC

from . import _auth
from . import _ytdlp_media as ytm
from ._captions import captions_file_to_plain_meta
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
from .youtube import (
    DEFAULT_TIMEOUT_SEC,
    _coerce_int,
    _format_upload_date,
)

# Caption ladder used when the X media *does* carry subtitles. Most X captions
# are auto-generated; we still try manual first per the skill's quality ethos.
DEFAULT_FALLBACK_X = (
    ("manual", "en"),
    ("auto", "en"),
)

# Re-export so callers (and tests) have one import surface.
extract_x_id = ytm.extract_x_id


def fetch_x_transcript(
    url: str,
    out_path: Path,
    *,
    fallback_ladder: Iterable[tuple[str, str]] = DEFAULT_FALLBACK_X,
    lang: str = "en",
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
    """Fetch an X.com transcript (captions if present, else ASR).

    Same return contract as the other adapters (:class:`TranscriptStat`).
    Raises ``SourceAuthError`` (private/protected/suspended), ``SourceRateLimitError``
    (429), ``TranscriptFetchError`` (no transcript producible), or
    ``MissingDependencyError`` (yt-dlp/ffmpeg/no-ASR-backend) — all mapped to
    exit codes by the CLI.

    ``concurrent_fragments``/``media_timeout_sec`` (arch-016 §10, task 029.02)
    apply to the ASR-path media download ONLY — the metadata probe keeps
    ``timeout_sec``. ``media_timeout_sec`` is expected to already be the
    CLI-or-env value resolved by the caller (``fetch.py``); ``None`` here means
    "derive the budget from the probed duration" via
    :func:`_ytdlp_media.media_timeout_for` (kept ``Optional`` so a direct
    library caller — e.g. a test — can also pass an explicit budget or rely on
    the duration-derived floor).
    """
    log = make_logger(debug)
    out_path = Path(out_path)
    ladder: tuple[tuple[str, str], ...] = tuple(fallback_ladder)
    video_id = ytm.extract_x_id(url)
    if description_only:
        with_description = True

    log("Detected X media")

    cleanup_workdir = False
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="transcript-fetcher-x-"))
        cleanup_workdir = True
    else:
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)

    try:
        # ---- 1. metadata probe (single -J call) ------------------------ #
        log("Fetching metadata")
        info, err = ytm.probe_metadata(
            url,
            timeout_sec=timeout_sec,
            cookies_file=cookies_file,
            cookies_from_browser=cookies_from_browser,
            yt_dlp_bin=yt_dlp_bin,
        )
        if info is None:
            _raise_for_failure(err, url, cookies_file=cookies_file)
            # _raise_for_failure always raises; this is unreachable.
            raise TranscriptFetchError(f"could not fetch metadata for {url}")

        # Media (audio) download budget — resolved ONCE, here, now that the
        # duration is known (info in hand). CLI-or-env (`media_timeout_sec`,
        # already resolved by the caller) wins; else the duration-derived floor.
        # Applies ONLY to the ASR-path `download_audio()` call below — the probe
        # above kept `timeout_sec`, and captions/silence-removal/ASR keep their
        # own existing budgets untouched.
        #
        # `--max-duration-min` CLIPS the actual download (see `download_audio`'s
        # `--download-sections`) — the budget must respect that clip, not the
        # full probed duration, else a `--max-duration-min 10` run on a 6-hour
        # broadcast gets a budget sized for the whole 6 hours. When the clip is
        # active and the probed duration is a positive number, feed the SMALLER
        # of (probed duration, clip) to `media_timeout_for`. BUT `--download-
        # sections` (the clip itself) is only emitted in `download_audio`'s
        # `ffmpeg_available()` branch — without ffmpeg a progressive (non-HLS)
        # download is NOT clipped, so the budget must NOT be clipped either;
        # feeding it the clipped duration there would size a premature timeout
        # for a download that is actually pulling the FULL media.
        effective_duration = info.get("duration")
        if (
            max_duration_min is not None
            and max_duration_min > 0
            and isinstance(effective_duration, (int, float))
            and effective_duration > 0
            and ytm.ffmpeg_available()
        ):
            effective_duration = min(effective_duration, max_duration_min * 60)
        media_budget = (
            media_timeout_sec
            if media_timeout_sec is not None
            else ytm.media_timeout_for(effective_duration)
        )

        notes: list[str] = []
        chosen_kind: Optional[str] = None
        chosen_lang: Optional[str] = None
        transcript_origin: Optional[str] = None
        asr_backend: Optional[str] = None
        asr_model_used: Optional[str] = None
        media_path: Optional[Path] = None
        plain = ""
        codec_used = "utf-8"

        if not description_only:
            picked = ytm.pick_caption(info, ladder)
            if picked is None:
                # The language-specific ladder matched nothing — but if the media
                # DOES carry any caption track, prefer it over ASR (captions-first
                # is the skill's ethos; the creator's own text beats a slow,
                # lower-fidelity transcription). The transcript language then
                # follows the available track, not --lang.
                fallback = ytm.pick_any_caption(info)
                if fallback is not None:
                    picked = fallback
                    notes.append(
                        f"no caption matched the requested ladder; using the "
                        f"available {fallback[0]}:{fallback[1]} track"
                    )

            # ---- 2a. caption path ------------------------------------- #
            if picked is not None:
                kind, clang = picked
                log("Embedded captions found")
                log("Downloading captions")
                pre_existing = ytm.existing_caption_files(workdir)
                ok, cap_path, cap_fmt, msg = ytm.download_captions(
                    url=url,
                    lang=clang,
                    kind=kind,
                    workdir=workdir,
                    pre_existing=pre_existing,
                    yt_dlp_bin=yt_dlp_bin,
                    timeout_sec=timeout_sec,
                    cookies_file=cookies_file,
                    cookies_from_browser=cookies_from_browser,
                )
                if msg:
                    notes.append(msg)
                if ok and cap_path is not None:
                    # Format-aware: VTT / SRT / TTML all collapse to the same clean
                    # prose (closes TF-X-4). Parse into LOCALS first — only commit
                    # (set transcript_origin / codec_used) if the result is
                    # non-empty, so a parse error OR an empty/whitespace caption
                    # falls through to ASR instead of silently writing an empty
                    # "embedded-captions" transcript.
                    try:
                        parsed, parsed_codec = captions_file_to_plain_meta(
                            cap_path, cap_fmt
                        )
                    except (ValueError, OSError) as e:
                        # ValueError: TTML refused (DTD/XXE guard) / malformed XML /
                        # undecodable bytes. OSError: the just-downloaded file became
                        # unreadable (vanished / permission). Either way fall through
                        # to ASR rather than crash — "never a crash, never empty".
                        parsed, parsed_codec = "", "utf-8"
                        notes.append(f"caption parse failed ({cap_fmt}): {e}")
                    if parsed.strip():
                        plain, codec_used = parsed, parsed_codec
                        chosen_kind, chosen_lang = kind, clang
                        transcript_origin = "embedded-captions"
                        if cap_fmt and cap_fmt != "vtt":
                            notes.append(f"captions parsed from {cap_fmt} format")
                    else:
                        notes.append(
                            f"captions ({cap_fmt}) yielded no text — falling back to ASR"
                        )
                else:
                    notes.append(
                        "captions advertised but download failed — falling back to ASR"
                    )

            # ---- 2b. ASR path (no captions, or caption download failed) #
            if transcript_origin is None:
                # Fail fast: an HLS-only source (X Broadcasts/Spaces) needs
                # ffmpeg to produce a valid container the ASR engine can open.
                # Without it, skip the (large, slow) download that would only
                # yield an unplayable file → clear exit-7 with remediation.
                if not ytm.ffmpeg_available() and ytm.is_hls_only(info):
                    raise MissingDependencyError(
                        "ffmpeg is required to transcribe this X media: it is an "
                        "HLS stream, and without ffmpeg the downloaded media is not "
                        "a valid container the ASR engine can open.",
                        remediation=(
                            "Install ffmpeg — `brew install ffmpeg` (macOS) / "
                            "`sudo apt-get install ffmpeg` (Linux), or "
                            "`python scripts/install_components.py --system --run`."
                        ),
                    )
                log("Downloading audio")
                media, derr = ytm.download_audio(
                    url,
                    workdir,
                    timeout_sec=media_budget,
                    cookies_file=cookies_file,
                    cookies_from_browser=cookies_from_browser,
                    yt_dlp_bin=yt_dlp_bin,
                    max_duration_min=max_duration_min,
                    concurrent_fragments=concurrent_fragments,
                )
                if media is None:
                    _raise_for_failure(
                        derr, url, default_msg="audio download failed",
                        cookies_file=cookies_file, media_download=True,
                    )
                    raise TranscriptFetchError(f"audio download failed for {url}")
                media_path = media

                # Pre-process: strip long silences so a Whisper-family engine is
                # less likely to hallucinate filler over dead air (TF-X-6). Never
                # fatal — on any problem we fall back to the original media. The
                # ORIGINAL `media_path` is kept for the ffprobe duration fill so
                # duration_sec reflects the real media, not the de-silenced clip.
                media_for_asr = media
                if remove_silence:
                    log("Removing long silences")
                    desilenced, snote = ytm.remove_silence(
                        media, workdir, timeout_sec=asr_timeout_sec or 900
                    )
                    notes.append(snote)
                    if desilenced is not None:
                        media_for_asr = desilenced

                from asr import transcribe_with_fallback

                try:
                    result = transcribe_with_fallback(
                        media_for_asr,
                        lang=lang,
                        allow_cloud=asr_allow_cloud,
                        model=asr_model,
                        timeout_sec=asr_timeout_sec or DEFAULT_ASR_TIMEOUT_SEC,
                        log=log,
                    )
                except TranscriptFetchError as e:
                    # If every backend failed to OPEN the media and ffmpeg is
                    # absent, the likely cause is an unplayable no-ffmpeg HLS
                    # container — append an actionable hint.
                    if not ytm.ffmpeg_available():
                        raise TranscriptFetchError(
                            f"{e} — NOTE: ffmpeg is not installed; the downloaded "
                            "media may be an unplayable container. Install ffmpeg "
                            "(brew install ffmpeg) and retry."
                        ) from e
                    raise
                plain = result.text
                chosen_kind = "asr"
                chosen_lang = result.language or lang
                transcript_origin = result.backend_name
                asr_backend = result.backend_name
                asr_model_used = result.model
                notes.append(f"transcribed via ASR backend '{result.backend_name}'")

            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(plain, encoding="utf-8")

        # ---- 3. build stat ------------------------------------------- #
        quality_flag: Optional[str] = None
        if not description_only and codec_used not in ("utf-8", "utf-8-sig"):
            quality_flag = "encoding_recovered"
            notes.append(f"VTT was decoded as {codec_used}, not utf-8")

        stat = TranscriptStat(
            source="x",
            url=url,
            video_id=video_id,
            output_path=str(out_path),
            chosen_track_kind=chosen_kind,
            chosen_track_lang=chosen_lang,
            char_count=len(plain),
            speaker_turn_count=count_speaker_turns(plain) if plain else 0,
            quality_flag=quality_flag,
            notes=notes,
            transcript_origin=transcript_origin,
            asr_backend=asr_backend,
            asr_model=asr_model_used,
        )

        # ---- 4. description sidecar ---------------------------------- #
        if with_description:
            stat.title = info.get("title")
            stat.uploader = info.get("uploader") or info.get("channel")
            stat.upload_date = _format_upload_date(info.get("upload_date"))
            stat.duration_sec = _coerce_int(info.get("duration"))
            desc_path = _write_x_description(info=info, url=url, out_path=out_path)
            stat.description_path = str(desc_path)
            stat.notes.append("description: wrote .description.md")

        # ---- 5. fill duration from the media if metadata lacked it ---- #
        # X Broadcasts/Spaces often report duration=None in yt-dlp metadata.
        # When we downloaded the media for ASR and ffmpeg is present, derive
        # the real duration via ffprobe (ships with ffmpeg — no new dep).
        if (
            stat.duration_sec is None
            and media_path is not None
            and ytm.ffmpeg_available()
        ):
            probed = ytm.probe_media_duration(media_path)
            if probed is not None:
                stat.duration_sec = probed
                stat.notes.append("duration: derived via ffprobe")

        return stat
    finally:
        log("Cleaning temporary files")
        if cleanup_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
        log("Finished")


def _raise_for_failure(
    stderr: Optional[str],
    url: str,
    *,
    default_msg: str = "could not fetch media",
    cookies_file: Optional[Path] = None,
    media_download: bool = False,
) -> None:
    """Map a yt-dlp failure string to the right typed exception. Always raises.

    ``cookies_file`` (R9b) is the SAME resolved file the caller passed to
    yt-dlp for this attempt (or ``None``) — on an ``"auth"`` classification the
    message names it (so the user knows exactly which file to refresh) or, when
    none was used, points at the convention path DERIVED FROM THE URL'S HOST
    (``~/.transcript-fetcher/<host>-cookies.txt``, ``www.``/``mobile.`` labels
    stripped) — a hardcoded ``x.com-cookies.txt`` would be a dead-end hint for
    the other 5 documented X hosts (twitter.com, www.x.com, mobile.x.com, ...).
    ``_auth.resolve_cookies_file``'s convention lookup carries the matching
    fallback (tries the exact host first, then the same ``www``/``mobile``/``m``
    label-stripped host — see its module docstring), so the printed hint is
    guaranteed to round-trip: creating the named file makes the NEXT attempt
    for any of the 6 allowlisted hosts pick it up.

    ``media_download`` (F8) is True ONLY when the failure came from the ASR-path
    media download (not the metadata probe) — on a ``"rate"`` classification it
    appends a hint naming ``--concurrent-fragments`` (the new parallel-fragment
    default is a plausible cause of a 429 that a metadata-probe rate-limit
    is not).
    """
    category = ytm.classify_failure(stderr or "")
    tail = _tail(stderr)
    if category == "auth":
        if cookies_file is not None:
            cookie_hint = f"refresh the cookies file you supplied ({cookies_file})"
        else:
            host = (urlparse(url).hostname or "x.com").lower()
            for prefix in ("www.", "mobile."):
                if host.startswith(prefix):
                    host = host[len(prefix):]
                    break
            convention = _auth.DEFAULT_AUTH_DIR / f"{host}-cookies.txt"
            cookie_hint = (
                f"supply a fresh --cookies-file, or place one at the convention "
                f"path {convention}"
            )
        raise SourceAuthError(
            f"X media requires authentication or is protected/suspended: {url}"
            + (f" ({tail})" if tail else "")
            + f" — {cookie_hint} (or use --cookies-from-browser)."
        )
    if category == "rate":
        msg = (
            f"X rate-limited the request for {url}"
            + (f" ({tail})" if tail else "")
            + " — retry later."
        )
        if media_download:
            msg += (
                " If this recurs during the media download, lower "
                "--concurrent-fragments (parallel fragment requests can trip "
                "rate limits)."
            )
        raise SourceRateLimitError(msg)
    if category == "transient":
        # The ONLY category the concurrency/media-budget remediation can fix
        # (see `_ytdlp_media.classify_failure` docstring) — a media (audio)
        # download socket-timeout, not a metadata-probe timeout.
        raise TranscriptFetchError(
            f"{default_msg} for {url}" + (f": {tail}" if tail else ""),
            remediation=(
                "The media download timed out. Long HLS broadcasts need parallel "
                "fragment download — raise --concurrent-fragments (e.g. 16) and/or "
                "--media-timeout-sec (e.g. 3600)."
            ),
        )
    # "hard" or unknown → not producible.
    raise TranscriptFetchError(
        f"{default_msg} for {url}" + (f": {tail}" if tail else "")
    )


def _tail(stderr: Optional[str], n: int = 3) -> str:
    if not stderr:
        return ""
    lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    signal = [ln for ln in lines if not ln.startswith("WARNING:")]
    chosen = signal if signal else lines
    return " | ".join(chosen[-n:])


def _write_x_description(*, info: dict, url: str, out_path: Path) -> Path:
    title = info.get("title") or "(untitled)"
    body = (info.get("description") or "").strip()
    frontmatter: dict = {
        "source": "x",
        "url": url,
        "video_id": info.get("id"),
        "title": title,
        "uploader": info.get("uploader") or info.get("channel"),
        "uploader_url": info.get("uploader_url") or info.get("channel_url"),
        "upload_date": _format_upload_date(info.get("upload_date")),
        "duration_sec": _coerce_int(info.get("duration")),
        "view_count": _coerce_int(info.get("view_count")),
        "like_count": _coerce_int(info.get("like_count")),
    }
    return write_description_md(
        out_path, frontmatter=frontmatter, title=title, body=body
    )


__all__ = (
    "DEFAULT_FALLBACK_X",
    "extract_x_id",
    "fetch_x_transcript",
)

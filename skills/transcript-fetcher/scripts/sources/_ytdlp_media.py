"""Reusable yt-dlp media helpers — the shared, source-neutral plumbing.

This module is the **forward extension surface** for yt-dlp-backed sources. The X
adapter (and any future TikTok/Twitch/Vimeo-ASR adapter) builds on it so the
genuinely shared logic — metadata probe, caption-availability inspection,
audio-minimal download, failure classification — lives in exactly one place.

It reuses the battle-tested primitives from :mod:`sources.youtube` (the same way
:mod:`sources.vimeo` does): the base argv builder and the VTT subtitle download
helper are imported rather than re-authored, and the failure-phrase classifier
**extends youtube's pattern tuples** instead of copying them (so the base set
cannot silently fork — arch-016 review #4).

Nothing here imports yt-dlp at module load; the binary is invoked as a
subprocess only when a function runs.
"""
from __future__ import annotations

import functools
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Optional

from ._captions import SUPPORTED_CAPTION_EXTS
from ._stat import MissingDependencyError
from .youtube import (
    DEFAULT_TIMEOUT_SEC,
    _HARD_FAILURE_PATTERNS as _YT_HARD,
    _RATE_LIMIT_PATTERNS as _YT_RATE,
    _try_download_subtitle,
    _yt_dlp_command,
)

# Re-export the canonical helpers so a consuming adapter imports only from here.
yt_dlp_argv = _yt_dlp_command
download_subtitle = _try_download_subtitle

# Default parallel-fragment count for the media (HLS) download (arch-016 §10.1).
# `download_audio()` clamps any override to [1, 32]: the upper bound guards against
# tripping X's rate limiter, `1` reproduces the pre-029 serial download for A/B
# debugging.
DEFAULT_CONCURRENT_FRAGMENTS = 8

# X-specific phrases layered ON TOP of youtube's base tuples.
_X_AUTH_PATTERNS = (
    "http error 401",
    "http error 403",
    "this account is protected",
    "this post is protected",
    "protected tweet",
    "account is suspended",
    "suspended account",
    "this post is from a suspended account",
    "nsfw tweet",
    "age-restricted",
    "you are not authorized",
    "log in to",
    "requested content cannot be displayed",
)
_X_RATE_PATTERNS = ("rate limit exceeded", "rate-limit")
_X_HARD_PATTERNS = (
    "tweet is unavailable",
    "this post is unavailable",
    "post is unavailable",
    "no longer available",
    "broadcast is unavailable",
    "broadcast unavailable",
    "this broadcast is not available",
    "media unavailable",
    "no video could be found",
    "nothing to download",
)


def classify_failure(stderr: str) -> Optional[str]:
    """Categorise a yt-dlp failure for an X URL.

    Returns one of ``"auth"`` / ``"rate"`` / ``"transient"`` / ``"hard"`` or
    ``None`` when no known phrase matched. The X adapter maps these onto
    ``SourceAuthError`` (5) / ``SourceRateLimitError`` (6) /
    ``TranscriptFetchError`` (3, remediation-carrying for ``"transient"``).

    ``"transient"`` is scoped to the media (audio) download's socket-timeout
    phrase ONLY (``"timeout downloading audio"``, emitted by
    :func:`download_audio`) — it deliberately does NOT match the metadata
    probe's timeout phrase (``"timeout probing metadata"``, emitted by
    :func:`probe_metadata`): a slow probe is not fixed by raising
    ``--concurrent-fragments``/``--media-timeout-sec``, so folding it into
    ``"transient"`` would point the user at a remediation that cannot help.
    It is the ONLY category the concurrency/media-budget remediation can fix
    (arch-016 §10, task 029.02).

    Ordering + match rule (deliberate, closes an in-band-signalling gap):
    the ``"transient"`` check runs LAST (after auth/rate/hard) and matches via
    ``str.startswith`` rather than a substring test. ``download_audio``'s
    ``TimeoutExpired`` branch replaces stderr WHOLESALE with the sentinel
    string, so for that internally-authored message ``startswith`` is an exact
    match. But this function is also fed RAW yt-dlp stderr from the metadata
    probe / caption download / non-timeout download failures — a channel that
    can echo server-supplied free text. If that text happened to contain the
    phrase mid-string while ALSO carrying an auth/rate/hard signal, a substring
    match checked first would let ``"transient"`` spoof over the correct
    (and more actionable) classification. Checking auth/rate/hard first, and
    matching the transient sentinel only at the START of the string, closes
    that without touching the authored timeout message itself.
    """
    s = (stderr or "").lower()
    for pat in _X_AUTH_PATTERNS:
        if pat in s:
            return "auth"
    for pat in (*_YT_RATE, *_X_RATE_PATTERNS):
        if pat in s:
            # youtube buckets some 'sign in to confirm' phrases as rate-limit;
            # but an explicit auth phrase already won above.
            return "rate"
    for pat in (*_YT_HARD, *_X_HARD_PATTERNS):
        if pat in s:
            return "hard"
    if s.startswith("timeout downloading audio"):
        return "transient"
    return None


@functools.cache
def ffmpeg_available() -> bool:
    # Cached: ffmpeg presence is fixed for a process (config is set once at the
    # CLI entry point), so a batch run does not re-probe $PATH per URL. Tests that
    # need a different result patch this function object directly (bypasses cache).
    import _config as cfg  # local import to keep module import light

    return shutil.which(cfg.ffmpeg_bin()) is not None


def is_hls_only(info: dict) -> bool:
    """True iff every real media format is HLS (``m3u8``) — no progressive file.

    Used to **fail fast** when ffmpeg is absent: yt-dlp's native HLS downloader
    concatenates fragments into a file that is NOT a valid playable container
    without an ffmpeg remux, so an ASR engine (MacWhisper/AVFoundation) cannot
    open it. Returns ``False`` when formats are unknown/empty (don't block on
    missing info) or when any progressive format exists (that one IS playable).
    """
    media_fmts = [
        f for f in (info.get("formats") or [])
        if f.get("acodec") not in (None, "none")
        or f.get("vcodec") not in (None, "none")
    ]
    if not media_fmts:
        return "m3u8" in (info.get("protocol") or "")
    return all("m3u8" in (f.get("protocol") or "") for f in media_fmts)


def extract_x_id(url: str) -> Optional[str]:
    """Pull the status id or broadcast/space id out of an X/Twitter URL."""
    patterns = (
        r"(?:x|twitter)\.com/i/broadcasts/([A-Za-z0-9]+)",
        r"(?:x|twitter)\.com/i/spaces/([A-Za-z0-9]+)",
        r"(?:x|twitter)\.com/[^/]+/status/(\d+)",
        r"(?:x|twitter)\.com/i/status/(\d+)",
    )
    for pat in patterns:
        m = re.search(pat, url, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def probe_metadata(
    url: str,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cookies_file: Optional[Path] = None,
    cookies_from_browser: Optional[str] = None,
    yt_dlp_bin: Optional[str] = None,
) -> tuple[Optional[dict], Optional[str]]:
    """Run ``yt-dlp -J --skip-download`` once. Returns ``(info, stderr)``.

    ``info`` is the parsed metadata dict on success, else ``None`` with the
    captured stderr so the caller can classify the failure. Raises
    :class:`MissingDependencyError` if yt-dlp itself is absent.
    """
    args = [
        *yt_dlp_argv(yt_dlp_bin),
        "-J",
        "--no-warnings",
        "--skip-download",
        "--socket-timeout", str(min(timeout_sec, 60)),
    ]
    if cookies_file is not None:
        args += ["--cookies", str(cookies_file)]
    if cookies_from_browser:
        args += ["--cookies-from-browser", cookies_from_browser]
    args += ["--", url]
    try:
        proc = subprocess.run(
            args, check=False, capture_output=True, text=True, timeout=timeout_sec
        )
    except FileNotFoundError as e:
        raise MissingDependencyError(
            f"yt-dlp is not installed: {e}",
            remediation="Run `bash skills/transcript-fetcher/scripts/install.sh`.",
        ) from e
    except subprocess.TimeoutExpired:
        return None, f"timeout probing metadata (>{timeout_sec}s)"
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return None, proc.stderr or ""
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as e:
        return None, f"could not parse yt-dlp -J output: {e}"


def caption_langs(info: dict) -> dict:
    """Return ``{"manual": [langs], "auto": [langs]}`` from an info dict."""
    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    return {"manual": list(subs.keys()), "auto": list(auto.keys())}


def pick_caption(
    info: dict, ladder: Iterable[tuple[str, str]]
) -> Optional[tuple[str, str]]:
    """First ``(kind, lang)`` in ``ladder`` for which a caption track exists."""
    cap = caption_langs(info)
    for kind, lang in ladder:
        pool = cap["manual"] if kind == "manual" else cap["auto"]
        if lang in pool:
            return (kind, lang)
    return None


def pick_any_caption(info: dict) -> Optional[tuple[str, str]]:
    """Last-resort caption pick: ANY available track, **manual preferred over auto**.

    Used by the X adapter as a fallback when the language-specific ladder matched
    nothing but the media DOES carry captions (e.g. the user kept the default
    ``--lang ru`` yet the post only has a ``manual en`` track). Using an
    out-of-ladder caption — the creator's own text — is faster and more accurate
    than dropping to ASR. Returns ``(kind, lang)`` or ``None`` when there are no
    captions at all. Caller should surface a note (the transcript language then
    differs from the requested ``--lang``).
    """
    cap = caption_langs(info)
    if cap["manual"]:
        return ("manual", cap["manual"][0])
    if cap["auto"]:
        return ("auto", cap["auto"][0])
    return None


def _stderr_tail(stderr: Optional[str], n: int = 3) -> str:
    if not stderr:
        return ""
    lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    return " | ".join(lines[-n:])


def existing_caption_files(workdir: Path) -> set:
    """Snapshot resolved paths of caption files already in ``workdir``.

    Passed as ``pre_existing`` to :func:`download_captions` so a ladder step
    never re-claims a file an earlier step downloaded. Covers every supported
    caption extension (not just ``.vtt``).
    """
    out: set = set()
    for ext in SUPPORTED_CAPTION_EXTS:
        for p in workdir.glob(f"*.{ext}"):
            out.add(p.resolve())
    return out


def _find_new_caption(workdir: Path, lang: str, pre_existing: set) -> Optional[Path]:
    """Find a freshly-downloaded ``<id>.<lang>.<ext>`` caption file (any supported
    text format) not present before the call. Prefers vtt > srt > ttml on a tie,
    then most-recent mtime."""
    pref = {ext: i for i, ext in enumerate(SUPPORTED_CAPTION_EXTS)}
    candidates = []
    for ext in SUPPORTED_CAPTION_EXTS:
        needle = f".{lang}.{ext}"
        for p in workdir.glob(f"*.{ext}"):
            if p.name.endswith(needle) and p.resolve() not in pre_existing:
                candidates.append(p)
    if not candidates:
        return None
    candidates.sort(
        key=lambda p: (pref.get(p.suffix.lower().lstrip("."), 99), -p.stat().st_mtime)
    )
    return candidates[0]


def download_captions(
    *,
    url: str,
    lang: str,
    kind: str,
    workdir: Path,
    pre_existing: set,
    yt_dlp_bin: Optional[str] = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cookies_file: Optional[Path] = None,
    cookies_from_browser: Optional[str] = None,
    sub_format: str = "vtt/srt/ttml/best",
) -> tuple[bool, Optional[Path], Optional[str], Optional[str]]:
    """Download one ``(kind, lang)`` caption track in ANY supported text format.

    The multi-format forward-surface counterpart to youtube's VTT-only
    ``download_subtitle`` (closes TF-X-4): yt-dlp is handed a format *preference
    list* (``vtt/srt/ttml/best``) so a source that serves only SRT or TTML still
    yields a parseable track instead of being treated as caption-less and pushed
    to ASR.

    Returns ``(ok, path, fmt, note)`` where ``fmt`` is the downloaded file's
    lowercased extension (``vtt``/``srt``/``ttml``/…) and ``note`` is a
    human-readable transparency line. ``ok`` is False (with ``path``/``fmt``
    None) when nothing parseable arrived.
    """
    out_tmpl = str(workdir / "%(id)s.%(ext)s")
    args = [
        *yt_dlp_argv(yt_dlp_bin),
        "--skip-download",
        "--sub-format", sub_format,
        "--sub-langs", lang,
        "--output", out_tmpl,
    ]
    if cookies_file is not None:
        args += ["--cookies", str(cookies_file)]
    if cookies_from_browser:
        args += ["--cookies-from-browser", cookies_from_browser]
    if kind == "manual":
        args.append("--write-subs")
    elif kind == "auto":
        args.append("--write-auto-subs")
    else:
        return False, None, None, f"unknown kind={kind!r}"
    # `--` terminates flag parsing so a `-`-leading URL is a positional.
    args += ["--", url]

    try:
        proc = subprocess.run(
            args, check=False, capture_output=True, text=True, timeout=timeout_sec
        )
    except FileNotFoundError as e:
        return False, None, None, f"yt-dlp not found: {e}"
    except subprocess.TimeoutExpired:
        return False, None, None, f"timeout fetching {kind}:{lang} (>{timeout_sec}s)"

    cat = classify_failure(proc.stderr or "")
    if proc.returncode != 0 and cat:
        tail = _stderr_tail(proc.stderr)
        return False, None, None, (
            f"{kind}:{lang} {cat}: {tail}" if tail else f"{kind}:{lang} {cat}"
        )

    found = _find_new_caption(workdir, lang, pre_existing)
    if found is not None:
        # Containment: the yt-dlp-authored name must stay inside workdir.
        if found.resolve().parent != workdir.resolve():
            return False, None, None, f"refusing caption outside workdir: {found.name}"
        pre_existing.add(found.resolve())
        fmt = found.suffix.lower().lstrip(".")
        return True, found, fmt, f"got {kind}:{lang} -> {found.name}"

    if proc.returncode != 0:
        tail = _stderr_tail(proc.stderr)
        return False, None, None, (
            f"{kind}:{lang} yt-dlp rc={proc.returncode}: {tail}"
            if tail
            else f"{kind}:{lang} yt-dlp rc={proc.returncode}"
        )
    return False, None, None, f"no subtitle returned for {kind}:{lang}"


def download_audio(
    url: str,
    workdir: Path,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cookies_file: Optional[Path] = None,
    cookies_from_browser: Optional[str] = None,
    yt_dlp_bin: Optional[str] = None,
    max_duration_min: Optional[float] = None,
    concurrent_fragments: Optional[int] = None,
) -> tuple[Optional[Path], Optional[str]]:
    """Download the minimal media needed for ASR. Returns ``(media_path, stderr)``.

    Strategy (arch-016 §3.3):
      * **ffmpeg present** → extract audio-only (`-x --audio-format m4a`).
      * **ffmpeg absent** → download the smallest muxed variant deterministically
        (`-f worstaudio/worst -S +size,+br`) and hand the media file to a
        video-capable backend (MacWhisper). Never a literal instance-specific
        format id.

    ``concurrent_fragments`` (arch-016 §10.1) sets ``--concurrent-fragments`` on
    the media argv — ``None`` resolves to :data:`DEFAULT_CONCURRENT_FRAGMENTS`,
    then any value is clamped to ``[1, 32]``. Emitted unconditionally: yt-dlp
    treats it as a safe no-op for a progressive (non-fragmented) single-file
    download, and it is what turns a ~120 KB/s serial HLS pull into a parallel
    one for a long X Broadcast/Space.

    Security: a **fixed** output template (`media.%(ext)s`, NOT `%(id)s.%(ext)s`)
    is used; the resulting file is resolved and asserted to live inside
    ``workdir`` before it is returned, closing the untrusted-filename / path-escape
    gap on the yt-dlp-authored name.
    """
    out_tmpl = str(workdir / "media.%(ext)s")
    args = [
        *yt_dlp_argv(yt_dlp_bin),
        "--no-playlist",
        "--no-warnings",
        "--output", out_tmpl,
    ]
    effective_fragments = (
        DEFAULT_CONCURRENT_FRAGMENTS if concurrent_fragments is None else concurrent_fragments
    )
    n_fragments = min(32, max(1, int(effective_fragments)))
    args += ["--concurrent-fragments", str(n_fragments)]
    # Always pick the smallest variant that still carries audio (minimal bytes).
    # Use yt-dlp's built-in ``worst*`` selectors (deterministically the
    # lowest-quality/-bitrate variant, NOT a literal instance-specific format id).
    # NOTE: do NOT combine these with ``-S +size/+br`` — a ``+`` sort makes "best"
    # the smallest, which inverts ``worst`` into picking the LARGEST.
    args += ["-f", "worstaudio/worst[acodec!=none]/worst"]
    if ffmpeg_available():
        # Extract a clean, small audio-only m4a. For HLS sources (X Broadcasts/
        # Spaces) this remux is also what makes the output a VALID container an
        # ASR engine can open — see is_hls_only() / the fail-fast in x.py.
        args += ["-x", "--audio-format", "m4a"]
        # Clip to the first N minutes — bounds BOTH the download bytes and the
        # ASR time for a long Broadcast/Space. Needs ffmpeg (already required
        # for the HLS path); a `*START-END` section is a time range in seconds.
        if max_duration_min and max_duration_min > 0:
            args += ["--download-sections", f"*0-{int(max_duration_min * 60)}"]
    if cookies_file is not None:
        args += ["--cookies", str(cookies_file)]
    if cookies_from_browser:
        args += ["--cookies-from-browser", cookies_from_browser]
    args += ["--", url]

    try:
        proc = subprocess.run(
            args, check=False, capture_output=True, text=True, timeout=timeout_sec
        )
    except FileNotFoundError as e:
        raise MissingDependencyError(
            f"yt-dlp is not installed: {e}",
            remediation="Run `bash skills/transcript-fetcher/scripts/install.sh`.",
        ) from e
    except subprocess.TimeoutExpired:
        return None, f"timeout downloading audio (>{timeout_sec}s)"

    media = find_downloaded_media(workdir)
    if media is not None:
        # Containment assertion — the yt-dlp-authored name must stay inside workdir.
        if media.resolve().parent != workdir.resolve():
            return None, f"refusing media outside workdir: {media}"
        return media, (proc.stderr if proc.returncode != 0 else None)
    return None, proc.stderr or f"no media produced (rc={proc.returncode})"


def media_timeout_for(duration_s: Optional[float]) -> int:
    """Media-download budget in seconds from a probed duration.

    ``min(21600, max(600, duration_s*4))`` when the probe reported a positive,
    finite duration (a 70-min broadcast → ~16800 s), else a generous 1800 s (X
    Broadcasts commonly probe duration=None). The 21600 s (6 h) upper cap
    exists because a per-attempt subprocess timeout is a HANG CEILING, not a
    wait time we actually expect to incur — an unbounded ``duration*4`` lets a
    pathological probed duration (or an un-clipped multi-hour broadcast) yield
    a multi-day budget that only yt-dlp's own (much shorter) socket-timeout
    would ever actually bound in practice.

    Accepts ``duration_s`` defensively — int/float/numeric string — because
    the value comes straight from yt-dlp's ``-J`` JSON: ``Infinity``/``NaN``
    round-trip through ``json.loads`` on a pathological extractor value, and a
    caller may hand in a numeric string. Unparseable / non-finite (NaN/inf) /
    non-positive / ``None`` all fall back to the 1800 s default rather than
    raising (bare ``int(duration_s*4)`` would raise ``OverflowError`` on
    ``inf`` or ``TypeError`` on a ``str``). A FINITE but astronomically large
    ``duration_s`` (e.g. ``1e308``) is ALSO handled without raising: once
    ``d >= 5400`` the ``21600`` cap already applies (``5400 * 4 == 21600``),
    so the cap is returned directly, before ever computing ``d * 4`` — for
    ``d`` near the float max that intermediate product overflows to ``inf``,
    and ``int(inf)`` raises ``OverflowError`` (the exact residual the
    never-raises contract above would otherwise miss). Pure + unit-testable;
    the CLI/env override it in x.py (029.02)."""
    try:
        d = float(duration_s)
    except (TypeError, ValueError):
        return 1800
    if not math.isfinite(d) or d <= 0:
        return 1800
    if d >= 5400:
        return 21600
    return min(21600, max(600, int(d * 4)))


def probe_media_duration(media: Path, *, timeout_sec: int = 60) -> Optional[int]:
    """Return the media duration in whole seconds via ffprobe, or ``None``.

    Used to fill ``stat.duration_sec`` when yt-dlp metadata reports ``None``
    (common for X Broadcasts/Spaces). ffprobe ships with ffmpeg, which is already
    required for the HLS ASR path, so this adds no new dependency. Never raises —
    a missing/failing ffprobe just yields ``None``.
    """
    import _config as cfg  # local import to keep module import light

    try:
        proc = subprocess.run(
            [
                cfg.ffprobe_bin(), "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=nokey=1:noprint_wrappers=1",
                str(media),
            ],
            check=False, capture_output=True, text=True, timeout=timeout_sec,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    raw = (proc.stdout or "").strip()
    try:
        return int(float(raw)) if raw else None
    except ValueError:
        return None


def remove_silence(
    media: Path,
    workdir: Path,
    *,
    threshold_db: Optional[str] = None,
    min_silence_sec: Optional[float] = None,
    keep_silence_sec: Optional[float] = None,
    timeout_sec: int = 900,
) -> tuple[Optional[Path], str]:
    """Strip long silences from ``media`` via ffmpeg's ``silenceremove`` filter.

    Returns ``(desilenced_path, note)`` on success, or ``(None, note)`` when
    ffmpeg is absent / the filter removed nothing / the output is empty — the
    caller then transcribes the ORIGINAL ``media``. **Never raises**: a
    preprocessing failure must not break the ASR pipeline.

    Mitigates Whisper-family hallucinated filler on silent lead-in/out/gaps
    (TF-X-6, the user's "analyse audio and remove large silences" approach) by
    collapsing dead air longer than ``min_silence_sec`` down to
    ``keep_silence_sec``, gated at ``threshold_db``. Because the threshold treats
    only true silence as removable, **music and speech (which carry energy above
    the threshold) survive** — so this helps the silent-lead-in case but not a
    music-only intro (see TF-X-6 residual). Timestamps shift, but the ASR path
    emits no timecodes, so the text output stays faithful.
    """
    import _config as cfg  # local import to keep module import light

    if not ffmpeg_available():
        return None, "silence-removal skipped: ffmpeg not available"

    thr = cfg.silence_threshold_db() if threshold_db is None else threshold_db
    gap = cfg.silence_min_gap_sec() if min_silence_sec is None else min_silence_sec
    keep = cfg.silence_keep_sec() if keep_silence_sec is None else keep_silence_sec
    out = workdir / "media.desilenced.m4a"
    # Trim leading silence (start_*) AND collapse every interior/trailing silence
    # longer than `gap` to `keep` seconds (stop_periods=-1). detection=peak is the
    # conservative choice (less likely to clip quiet speech than rms).
    # `*_threshold` takes a dB-suffixed value natively (silenceremove parses "dB");
    # do NOT convert to a bare linear number — ffmpeg reads a bare negative as a huge
    # amplitude ratio and errors ("Result too large"). Durations carry an explicit
    # `s` unit for clarity/forward-compat (bare floats also parse as seconds).
    af = (
        f"silenceremove=start_periods=1:start_duration=0:start_threshold={thr}"
        f":detection=peak:stop_periods=-1:stop_duration={gap}s"
        f":stop_threshold={thr}:stop_silence={keep}s"
    )
    argv = [
        cfg.ffmpeg_bin(), "-nostdin", "-y", "-i", str(media),
        "-af", af, "-c:a", "aac", "-b:a", "96k", str(out),
    ]
    try:
        proc = subprocess.run(
            argv, check=False, capture_output=True, text=True, timeout=timeout_sec
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return None, f"silence-removal skipped: ffmpeg failed ({type(e).__name__})"

    if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        return None, "silence-removal skipped: ffmpeg produced no usable output"

    before = probe_media_duration(media)
    after = probe_media_duration(out)
    if before is not None and after is not None:
        removed = before - after
        if removed <= 0:
            # Nothing meaningfully removed — drop the re-encode, keep original.
            try:
                out.unlink()
            except OSError:
                pass
            return None, "silence-removal: no long silence found (using original)"
        return out, (
            f"silence-removal: stripped ~{removed}s of silence "
            f"({before}s → {after}s)"
        )
    return out, "silence-removal: applied (duration delta unknown)"


def find_downloaded_media(workdir: Path) -> Optional[Path]:
    """Find the downloaded ``media.*`` file, ignoring sidecars/partials."""
    # ``.info.json`` / ``.description`` end in ``.json`` / ``.description`` so the
    # suffix check below covers them; ``.part``/``.ytdl`` are partial-download
    # sidecars. One suffix filter is sufficient.
    ignore_suffixes = {".part", ".ytdl", ".json", ".description"}
    candidates = []
    for p in workdir.glob("media.*"):
        if p.is_dir():
            continue
        if p.suffix.lower() in ignore_suffixes:
            continue
        # The silence-removal output (`media.desilenced.m4a`) is a derived file,
        # not the yt-dlp download — never mistake it for the source media.
        if ".desilenced." in p.name:
            continue
        candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


__all__ = (
    "DEFAULT_CONCURRENT_FRAGMENTS",
    "DEFAULT_TIMEOUT_SEC",
    "caption_langs",
    "classify_failure",
    "download_audio",
    "download_captions",
    "download_subtitle",
    "existing_caption_files",
    "extract_x_id",
    "ffmpeg_available",
    "find_downloaded_media",
    "is_hls_only",
    "media_timeout_for",
    "pick_any_caption",
    "pick_caption",
    "probe_media_duration",
    "probe_metadata",
    "remove_silence",
    "yt_dlp_argv",
)

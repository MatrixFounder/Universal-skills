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
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Optional

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

    Returns one of ``"auth"`` / ``"rate"`` / ``"hard"`` (in that precedence) or
    ``None`` when no known phrase matched. The X adapter maps these onto
    ``SourceAuthError`` (5) / ``SourceRateLimitError`` (6) /
    ``TranscriptFetchError`` (3).
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


def download_audio(
    url: str,
    workdir: Path,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cookies_file: Optional[Path] = None,
    cookies_from_browser: Optional[str] = None,
    yt_dlp_bin: Optional[str] = None,
    max_duration_min: Optional[float] = None,
) -> tuple[Optional[Path], Optional[str]]:
    """Download the minimal media needed for ASR. Returns ``(media_path, stderr)``.

    Strategy (arch-016 §3.3):
      * **ffmpeg present** → extract audio-only (`-x --audio-format m4a`).
      * **ffmpeg absent** → download the smallest muxed variant deterministically
        (`-f worstaudio/worst -S +size,+br`) and hand the media file to a
        video-capable backend (MacWhisper). Never a literal instance-specific
        format id.

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
        candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


__all__ = (
    "DEFAULT_TIMEOUT_SEC",
    "caption_langs",
    "classify_failure",
    "download_audio",
    "download_subtitle",
    "extract_x_id",
    "ffmpeg_available",
    "find_downloaded_media",
    "is_hls_only",
    "pick_caption",
    "probe_media_duration",
    "probe_metadata",
    "yt_dlp_argv",
)

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

from asr._base import DEFAULT_ASR_TIMEOUT_SEC

from . import _ytdlp_media as ytm
from ._description import write_description_md
from ._log import make_logger
from ._stat import (
    MissingDependencyError,
    SourceAuthError,
    SourceRateLimitError,
    TranscriptFetchError,
    TranscriptStat,
)
from ._vtt_to_text import count_speaker_turns, vtt_file_to_plain_meta
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
    cookies_file: Optional[Path] = None,
    with_description: bool = False,
    description_only: bool = False,
    asr_allow_cloud: bool = False,
    asr_model: Optional[str] = None,
    asr_timeout_sec: int = DEFAULT_ASR_TIMEOUT_SEC,
    debug: bool = False,
) -> TranscriptStat:
    """Fetch an X.com transcript (captions if present, else ASR).

    Same return contract as the other adapters (:class:`TranscriptStat`).
    Raises ``SourceAuthError`` (private/protected/suspended), ``SourceRateLimitError``
    (429), ``TranscriptFetchError`` (no transcript producible), or
    ``MissingDependencyError`` (yt-dlp/ffmpeg/no-ASR-backend) — all mapped to
    exit codes by the CLI.
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
            yt_dlp_bin=yt_dlp_bin,
        )
        if info is None:
            _raise_for_failure(err, url)
            # _raise_for_failure always raises; this is unreachable.
            raise TranscriptFetchError(f"could not fetch metadata for {url}")

        notes: list[str] = []
        chosen_kind: Optional[str] = None
        chosen_lang: Optional[str] = None
        transcript_origin: Optional[str] = None
        asr_backend: Optional[str] = None
        asr_model_used: Optional[str] = None
        plain = ""
        codec_used = "utf-8"

        if not description_only:
            picked = ytm.pick_caption(info, ladder)

            # ---- 2a. caption path ------------------------------------- #
            if picked is not None:
                kind, clang = picked
                log("Embedded captions found")
                log("Downloading captions")
                pre_existing = {p.resolve() for p in workdir.glob("*.vtt")}
                ok, vtt_path, msg = ytm.download_subtitle(
                    url=url,
                    lang=clang,
                    kind=kind,
                    workdir=workdir,
                    pre_existing=pre_existing,
                    yt_dlp_bin=yt_dlp_bin,
                    timeout_sec=timeout_sec,
                    cookies_file=cookies_file,
                    with_info_json=False,
                )
                if msg:
                    notes.append(msg)
                if ok and vtt_path is not None:
                    plain, codec_used = vtt_file_to_plain_meta(vtt_path)
                    chosen_kind, chosen_lang = kind, clang
                    transcript_origin = "embedded-captions"
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
                    timeout_sec=timeout_sec,
                    cookies_file=cookies_file,
                    yt_dlp_bin=yt_dlp_bin,
                )
                if media is None:
                    _raise_for_failure(derr, url, default_msg="audio download failed")
                    raise TranscriptFetchError(f"audio download failed for {url}")

                from asr import transcribe_with_fallback

                try:
                    result = transcribe_with_fallback(
                        media,
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

        return stat
    finally:
        log("Cleaning temporary files")
        if cleanup_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
        log("Finished")


def _raise_for_failure(
    stderr: Optional[str], url: str, *, default_msg: str = "could not fetch media"
) -> None:
    """Map a yt-dlp failure string to the right typed exception. Always raises."""
    category = ytm.classify_failure(stderr or "")
    tail = _tail(stderr)
    if category == "auth":
        raise SourceAuthError(
            f"X media requires authentication or is protected/suspended: {url}"
            + (f" ({tail})" if tail else "")
            + " — supply --cookies-file with a logged-in session if you have access."
        )
    if category == "rate":
        raise SourceRateLimitError(
            f"X rate-limited the request for {url}"
            + (f" ({tail})" if tail else "")
            + " — retry later."
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

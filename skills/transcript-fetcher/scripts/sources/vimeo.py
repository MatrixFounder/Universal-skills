"""Vimeo source adapter.

A minimal sibling to :mod:`youtube` that targets Vimeo URLs through
the same ``yt-dlp`` plumbing. yt-dlp natively supports Vimeo: caption
download is the same ``--write-subs`` / ``--write-auto-subs`` switch,
the language argument is the same shape, and the resulting VTT goes
through the same cleaner.

Important differences from YouTube:
- Vimeo auto-captions are far rarer than on YouTube. Many videos have
  no caption track at all; in that case the adapter raises
  :class:`TranscriptFetchError` with the full ladder included in the
  message.
- There is no ``<lang>-orig`` quirk; we use ``<lang>`` directly.
- yt-dlp's Vimeo info-json carries ``description``, ``uploader``,
  ``upload_date``, and ``duration`` like YouTube, so the
  ``--with-description`` path works unchanged.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from ._description import write_description_md
from ._stat import TranscriptFetchError, TranscriptStat
from ._vtt_to_text import count_speaker_turns, vtt_file_to_plain_meta
from .youtube import (  # reuse YouTube helpers — same yt-dlp plumbing
    DEFAULT_TIMEOUT_SEC,
    _classify_failure,
    _coerce_int,
    _fetch_video_info,
    _find_new_vtt,
    _format_upload_date,
    _pick_fresh_info_json,
    _stderr_tail,
    _yt_dlp_command,
)


DEFAULT_FALLBACK_VIMEO = (
    ("manual", "en"),
    ("auto", "en"),
)


def extract_vimeo_id(url: str) -> Optional[str]:
    """Pull a numeric Vimeo video id out of common URL shapes."""
    patterns = (
        r"vimeo\.com/(\d+)",
        r"player\.vimeo\.com/video/(\d+)",
    )
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def fetch_vimeo_transcript(
    url: str,
    out_path: Path,
    *,
    fallback_ladder: Iterable[tuple[str, str]] = DEFAULT_FALLBACK_VIMEO,
    yt_dlp_bin: Optional[str] = None,
    workdir: Optional[Path] = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    cookies_file: Optional[Path] = None,
    with_description: bool = False,
    description_only: bool = False,
) -> TranscriptStat:
    """Fetch a Vimeo transcript via yt-dlp. Same contract as YouTube."""
    out_path = Path(out_path)
    video_id = extract_vimeo_id(url)
    ladder: tuple[tuple[str, str], ...] = tuple(fallback_ladder)
    if description_only:
        with_description = True

    cleanup_workdir = False
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="transcript-fetcher-vimeo-"))
        cleanup_workdir = True
    else:
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)

    pre_existing = {p.resolve() for p in workdir.glob("*.vtt")}
    pre_existing_info = {p.resolve() for p in workdir.glob("*.info.json")}
    notes: list[str] = []
    chosen_kind: Optional[str] = None
    chosen_lang: Optional[str] = None
    vtt_path: Optional[Path] = None
    plain = ""
    codec_used = "utf-8"

    try:
        if not description_only:
            for kind, lang in ladder:
                ok, vtt_path, msg = _try_download_vimeo_subtitle(
                    url=url,
                    lang=lang,
                    kind=kind,
                    workdir=workdir,
                    pre_existing=pre_existing,
                    yt_dlp_bin=yt_dlp_bin,
                    timeout_sec=timeout_sec,
                    cookies_file=cookies_file,
                    with_info_json=with_description,
                )
                if msg:
                    notes.append(msg)
                if ok and vtt_path is not None:
                    chosen_kind = kind
                    chosen_lang = lang
                    break

            if vtt_path is None or chosen_lang is None:
                tried = [f"{k}:{l}" for k, l in ladder]
                raise TranscriptFetchError(
                    f"No caption track available for {url}: tried {tried}. "
                    f"Notes: {notes[-3:] if notes else '[]'}"
                )

            plain, codec_used = vtt_file_to_plain_meta(vtt_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(plain, encoding="utf-8")

        quality_flag: Optional[str] = None
        if not description_only:
            if codec_used not in ("utf-8", "utf-8-sig"):
                quality_flag = "encoding_recovered"
                notes.append(f"VTT was decoded as {codec_used}, not utf-8")

        stat = TranscriptStat(
            source="vimeo",
            url=url,
            video_id=video_id,
            output_path=str(out_path),
            chosen_track_kind=chosen_kind,
            chosen_track_lang=chosen_lang,
            char_count=len(plain),
            speaker_turn_count=count_speaker_turns(plain) if plain else 0,
            quality_flag=quality_flag,
            notes=notes,
        )

        if with_description:
            info: Optional[dict] = _pick_fresh_info_json(workdir, pre_existing_info)
            if info is None:
                info = _fetch_video_info(
                    url=url,
                    workdir=workdir,
                    yt_dlp_bin=yt_dlp_bin,
                    timeout_sec=timeout_sec,
                    cookies_file=cookies_file,
                )
            if info is not None:
                stat.title = info.get("title")
                stat.uploader = info.get("uploader") or info.get("channel")
                stat.upload_date = _format_upload_date(info.get("upload_date"))
                stat.duration_sec = _coerce_int(info.get("duration"))
                desc_path = _write_vimeo_description(
                    info=info, url=url, out_path=out_path
                )
                stat.description_path = str(desc_path)
                stat.notes.append("description: wrote .description.md")
            else:
                stat.notes.append("description: yt-dlp info.json not available")
                if description_only:
                    raise TranscriptFetchError(
                        f"description_only requested but yt-dlp could not "
                        f"fetch metadata for {url}"
                    )

        return stat
    finally:
        if cleanup_workdir:
            shutil.rmtree(workdir, ignore_errors=True)


def _try_download_vimeo_subtitle(
    *,
    url: str,
    lang: str,
    kind: str,
    workdir: Path,
    pre_existing: set[Path],
    yt_dlp_bin: Optional[str],
    timeout_sec: int,
    cookies_file: Optional[Path] = None,
    with_info_json: bool = False,
) -> tuple[bool, Optional[Path], Optional[str]]:
    """Same shape as YouTube's helper, just inlined to keep ladder logic clean."""
    out_tmpl = str(workdir / "%(id)s.%(ext)s")
    args = [
        *_yt_dlp_command(yt_dlp_bin),
        "--skip-download",
        "--sub-format", "vtt",
        "--sub-langs", lang,
        "--output", out_tmpl,
    ]
    if cookies_file is not None:
        args.extend(["--cookies", str(cookies_file)])
    if with_info_json:
        args.append("--write-info-json")
    if kind == "manual":
        args.append("--write-subs")
    elif kind == "auto":
        args.append("--write-auto-subs")
    else:
        return False, None, f"unknown kind={kind!r}"
    args.append("--")
    args.append(url)

    try:
        proc = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except FileNotFoundError as e:
        return False, None, f"yt-dlp not found: {e}"
    except subprocess.TimeoutExpired:
        return False, None, f"timeout fetching {kind}:{lang} (>{timeout_sec}s)"

    failure_reason = _classify_failure(proc.stderr or "")
    if proc.returncode != 0 and failure_reason:
        tail = _stderr_tail(proc.stderr or "", 3)
        return False, None, (
            f"{kind}:{lang} {failure_reason}: {tail}"
            if tail
            else f"{kind}:{lang} {failure_reason}"
        )

    vtt = _find_new_vtt(workdir, lang, pre_existing)
    if vtt is not None:
        pre_existing.add(vtt.resolve())
        return True, vtt, f"got {kind}:{lang} -> {vtt.name}"

    if proc.returncode != 0:
        tail = _stderr_tail(proc.stderr or "", 3)
        return False, None, (
            f"{kind}:{lang} yt-dlp rc={proc.returncode}: {tail}"
            if tail
            else f"{kind}:{lang} yt-dlp rc={proc.returncode}"
        )
    return False, None, f"no subtitle returned for {kind}:{lang}"


def _write_vimeo_description(*, info: dict, url: str, out_path: Path) -> Path:
    title = info.get("title") or "(untitled)"
    body = (info.get("description") or "").strip()
    frontmatter: dict = {
        "source": "vimeo",
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
    "DEFAULT_FALLBACK_VIMEO",
    "extract_vimeo_id",
    "fetch_vimeo_transcript",
)

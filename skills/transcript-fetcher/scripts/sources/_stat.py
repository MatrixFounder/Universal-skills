"""Shared transcript-stat record and sidecar writer.

The :class:`TranscriptStat` is the contract returned by every source
adapter (``youtube``, ``vimeo``, ``skool``). The CLI in ``fetch.py``
serialises it to JSON on stdout and writes the same payload as a
``.stat.json`` sidecar next to the plain-text transcript.

New fields added in v1.1 (description + Skool support) are all
``Optional`` so the schema stays backward-compatible: pre-v1.1
consumers that ignore unknown keys still work, and ``--with-description``
is opt-in (defaults leave the new fields as ``None``).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TranscriptStat:
    """Machine-readable record describing one fetched transcript.

    Emitted as one line of JSON on stdout by ``fetch.py`` (or written
    to ``<output>.stat.json``). Schema is intentionally flat and
    string-keyed for easy consumption by downstream pipelines.
    """

    source: str  # "youtube" | "vimeo" | "skool"
    url: str
    video_id: Optional[str]
    output_path: str
    chosen_track_kind: Optional[str]  # "manual" | "auto" | "skool_manual"
    chosen_track_lang: Optional[str]  # "ru" | "ru-orig" | "en" | "unknown" | ...
    char_count: int
    speaker_turn_count: int
    quality_flag: Optional[str] = None  # e.g. "english_auto_translation"
    notes: list[str] = field(default_factory=list)
    # v1.1 — description + metadata (populated only with --with-description
    # or when the source carries metadata anyway, e.g. Skool lesson title).
    title: Optional[str] = None
    uploader: Optional[str] = None
    upload_date: Optional[str] = None  # ISO YYYY-MM-DD
    duration_sec: Optional[int] = None
    description_path: Optional[str] = None  # absolute path to .description.md
    # v1.1 — Skool-specific: when a Skool lesson embeds another source.
    embed_source: Optional[str] = None  # "youtube" | "vimeo" | "none" | other host
    embed_url: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def write_stat_sidecar(stat: TranscriptStat, plain_path: Path) -> Path:
    """Write the JSON stat record next to the plain-text output.

    The sidecar path is ``<plain_path>.stat.json``. Returns that path.
    """
    sidecar = Path(str(plain_path) + ".stat.json")
    sidecar.write_text(
        json.dumps(stat.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return sidecar


class TranscriptFetchError(RuntimeError):
    """Raised when no caption track in the fallback ladder is available."""


class SourceAuthError(RuntimeError):
    """Raised when a source requires auth that was missing or rejected."""


class SourceRateLimitError(RuntimeError):
    """Raised when a source returns an HTTP 429 / explicit throttle."""

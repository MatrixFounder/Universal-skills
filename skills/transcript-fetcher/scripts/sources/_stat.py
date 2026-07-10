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

    source: str  # "youtube" | "vimeo" | "skool" | "x"
    url: str
    video_id: Optional[str]
    output_path: str
    chosen_track_kind: Optional[str]  # "manual" | "auto" | "skool_manual" | "asr"
    chosen_track_lang: Optional[str]  # "ru" | "ru-orig" | "en" | "unknown" | ...
    char_count: int
    speaker_turn_count: int
    quality_flag: Optional[str] = None  # e.g. "english_auto_translation"
    notes: list[str] = field(default_factory=list)
    # TASK 026 — transcript provenance. Lets a downstream skill know HOW the
    # text was produced (pre-existing captions vs which ASR engine). All
    # Optional/None-default so the schema stays backward-compatible: the
    # youtube/vimeo/skool adapters never set them.
    transcript_origin: Optional[str] = None  # "embedded-captions" | "macwhisper"
    #                                          | "whisper-cli" | "whisper-cpp" | "openai-api"
    asr_backend: Optional[str] = None  # == backend name when chosen_track_kind == "asr"
    asr_model: Optional[str] = None  # backend-reported model id, if any
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
    """Raised when no caption track in the fallback ladder is available.

    Mirrors :class:`MissingDependencyError`'s optional ``remediation`` attribute
    (task 029.02, R7): a transient media-download timeout can carry an
    actionable hint (e.g. raise ``--concurrent-fragments``/``--media-timeout-sec``)
    that ``fetch.py`` surfaces in both the single-URL and batch JSON error
    envelopes. Backward-compatible — every existing ``TranscriptFetchError("msg")``
    call site keeps working unchanged; ``remediation`` defaults to ``None``.
    """

    def __init__(self, message: str, *, remediation: Optional[str] = None) -> None:
        super().__init__(message)
        self.remediation = remediation


class SourceAuthError(RuntimeError):
    """Raised when a source requires auth that was missing or rejected."""


class SourceRateLimitError(RuntimeError):
    """Raised when a source returns an HTTP 429 / explicit throttle."""


class MissingDependencyError(RuntimeError):
    """Raised when a required external tool is unavailable.

    Covers: yt-dlp missing; ffmpeg required but absent; or no ASR backend
    available (and the opt-in cloud backend was not enabled). Distinct from
    :class:`TranscriptFetchError` (which means a transcript could not be
    produced *despite* the toolchain being present). Maps to CLI exit code 7.

    The ``remediation`` attribute carries an actionable hint surfaced to the
    user instead of a raw traceback.

    IMPORTANT: this is intentionally a direct subclass of ``RuntimeError`` and
    **NOT** of ``TranscriptFetchError`` — ``fetch.py`` relies on that to route
    it to exit 7 via a dedicated ``except`` clause placed before the generic
    handler (otherwise it would be swallowed as exit 1).
    """

    def __init__(self, message: str, *, remediation: Optional[str] = None) -> None:
        super().__init__(message)
        self.remediation = remediation

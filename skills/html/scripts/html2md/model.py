"""In-memory IR passed between the FC stages (ARCH §4). Dataclasses only — no logic.

Flow:  acquire → AcquireResult → clean → CleanResult → core_bridge → markdown → emit
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceMeta:
    """Frontmatter source fields (ARCH §4.1). All best-effort / optional."""

    url: str | None = None
    title: str | None = None
    date: str | None = None
    author: str | None = None


@dataclass(frozen=True)
class AcquireResult:
    """FC-1 output (ARCH §4.1).

    ``mode``   — "file" | "archive" | "url"
    ``engine`` — the real fetch tier: "lite" | "lite+arxiv-html" | "lite+restapi" |
                 "lite+nojs" | "jina" | "remote:<host>" | "chrome" | None (offline)
    ``images`` — {original_url: local_path}  (archive/file; url fills lazily at emit)
    ``content_kind`` — "html" (default; flows through clean→turndown) | "markdown"
                 (trust-mode: ``markdown`` carries the reader's own clean Markdown and
                 the clean/turndown passes are bypassed — TASK 023 R4)
    ``markdown`` — populated only when ``content_kind == "markdown"``
    """

    html: str
    base_url: str = ""
    mode: str = "file"
    engine: str | None = None
    source_meta: SourceMeta = field(default_factory=SourceMeta)
    images: dict = field(default_factory=dict)
    content_kind: str = "html"
    markdown: str | None = None


@dataclass(frozen=True)
class CleanResult:
    """FC-2 output (ARCH §4.2). ``reader_html`` is None when --no-reader."""

    whole_html: str
    reader_html: str | None = None

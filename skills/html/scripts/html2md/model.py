"""In-memory IR passed between the FC stages (ARCH §4). Dataclasses only — no logic.

Flow:  acquire → AcquireResult → clean → CleanResult → core_bridge → markdown → emit
       acquire → AcquireResult → serialize → FetchArtifact (OP1 fetch, on disk)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SourceMeta:
    """Frontmatter source fields (ARCH §4.1). All best-effort / optional."""

    url: str | None = None
    title: str | None = None
    date: str | None = None
    author: str | None = None

    def to_dict(self) -> dict:
        return {"url": self.url, "title": self.title, "date": self.date,
                "author": self.author}

    @classmethod
    def from_dict(cls, d: dict) -> "SourceMeta":
        return cls(url=d.get("url"), title=d.get("title"), date=d.get("date"),
                   author=d.get("author"))


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


@dataclass(frozen=True)
class FetchArtifact:
    """OP1 (`html fetch`) on-disk product (TASK 027).

    What was written: the saved HTML page, its ``<slug>.meta.json`` sidecar, and the
    attachments dir (when images were localized). The combined ``html2md`` command
    deletes ``html_path`` + ``meta_path`` after OP2 converts, keeping the ``.md`` (+
    ``.reader.md``) + ``_attachments/``. ``base_url`` is the directory the HTML lives in
    (so OP2 / pdf resolve the localized images against it).
    """

    html_path: Path
    meta_path: Path | None
    attachments_dir: Path | None
    source_meta: SourceMeta = field(default_factory=SourceMeta)
    engine: str | None = None
    base_url: str = ""

"""html2md-OWNED thin facade over the pdf-mastered cleaning cluster.

This file is authored by html2md and is **NOT** under the ``diff -q`` replication
gate (ARCH §9 / CLAUDE.md §2). The five sibling modules
(``archives``/``reader_mode``/``preprocess``/``dom_utils``/``normalize_css``) ARE
byte-identical replicas of ``skills/pdf/scripts/html2pdf_lib/`` (master = pdf).

It re-exports ONLY the clean public symbols and **must never** import
``render``/``chrome_engine``/the pdf package ``__init__`` — those are the only
weasyprint/playwright carriers and are deliberately not replicated. The
import smoke-test (ARCH §9 G-2) asserts ``weasyprint``/``playwright`` stay out of
``sys.modules`` after importing ``web_clean.archives`` + ``web_clean.reader_mode``.
"""
from __future__ import annotations

from .archives import extract_archive, list_archive_frames
from .preprocess import preprocess_html
from .reader_mode import reader_mode_html

# Frozen facade surface (task-022-01) — exactly the four symbols downstream beads
# consume. `extract_mhtml`/`extract_webarchive` stay importable from
# `web_clean.archives` directly but are not part of the package facade.
__all__ = [
    "preprocess_html",
    "reader_mode_html",
    "extract_archive",
    "list_archive_frames",
]

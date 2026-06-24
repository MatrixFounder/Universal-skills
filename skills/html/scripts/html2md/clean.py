"""FC-2 — HTML cleaning via the pdf-mastered ``web_clean`` cluster (ARCH §2.1, §4.2).

``whole_html`` = chrome/ad-stripped whole page; ``reader_html`` = article-extracted
(reader-mode + universal SPA-chrome heuristic), or ``None`` when ``--no-reader``.

The ``web_clean`` modules are NEVER edited here (ARCH §9) — only called. Any cleaning
bug is fixed in the pdf master and re-replicated.
"""
from __future__ import annotations

from web_clean import preprocess_html, reader_mode_html

from .model import AcquireResult, CleanResult


def clean(acq: AcquireResult, *, reader: bool) -> CleanResult:
    """Produce ``{whole_html, reader_html}`` from an :class:`AcquireResult`.

    ``preprocess_html`` runs once (chrome/ad/icon strip); the reader variant is
    extracted from the *preprocessed* HTML so it inherits the same cleaning. The
    whole-page variant is always the faithful fallback (ARCH §10).
    """
    whole = preprocess_html(acq.html)
    reader_html = reader_mode_html(whole) if reader else None
    return CleanResult(whole_html=whole, reader_html=reader_html)

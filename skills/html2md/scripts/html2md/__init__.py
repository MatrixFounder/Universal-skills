"""html2md — universal Web/HTML → Markdown converter & Obsidian web-clipper (TASK 022).

Closed public surface. The body lives in the submodules; the ``html2md.py`` shim
re-execs into ``scripts/.venv`` then calls :func:`main`.

Proprietary, All Rights Reserved — this package embeds byte-identical copies of
proprietary docx/pdf code (the turndown core via the Node bridge, and the
``web_clean`` cleaning cluster), so it is a derived work governed by the per-skill
LICENSE/NOTICE (see CLAUDE.md §3).
"""
from __future__ import annotations

from .cli import convert, main
from .exceptions import (
    BadInput,
    ConvertFailed,
    EngineNotInstalled,
    FetchFailed,
    InternalError,
    SelfOverwriteRefused,
    _AppError,
)

__all__ = [
    "main",
    "convert",
    "_AppError",
    "BadInput",
    "ConvertFailed",
    "EngineNotInstalled",
    "FetchFailed",
    "InternalError",
    "SelfOverwriteRefused",
]

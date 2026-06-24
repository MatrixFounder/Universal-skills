"""html — universal Web/HTML → Markdown converter & Obsidian web-clipper (TASK 022).

Closed public surface. The body lives in the submodules; the ``html`` launcher
re-execs into ``scripts/.venv`` then calls :func:`main` (the multi-verb CLI), and the
``html2md`` launcher calls :func:`combined_main` (the fetch→md→delete one-shot).

Proprietary, All Rights Reserved — this package embeds byte-identical copies of
proprietary docx/pdf code (the turndown core via the Node bridge, and the
``web_clean`` cleaning cluster), so it is a derived work governed by the per-skill
LICENSE/NOTICE (see CLAUDE.md §3).
"""
from __future__ import annotations

from .cli import _load_skill_env, combined_main, convert, main
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
    "combined_main",
    "convert",
    "_load_skill_env",
    "_AppError",
    "BadInput",
    "ConvertFailed",
    "EngineNotInstalled",
    "FetchFailed",
    "InternalError",
    "SelfOverwriteRefused",
]

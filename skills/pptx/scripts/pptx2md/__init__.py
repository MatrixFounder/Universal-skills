"""pptx → Markdown converter (TASK 020). Body of ``scripts/pptx2md.py``.

Closed public surface — the thin shim ``pptx2md.py`` re-exports :func:`main`
and the :class:`_AppError` subclasses. Internal modules (``cli``, ``extract``,
``images``, ``ocr``, ``emit``, ``model``) are not part of the public contract.

This package consumes two shared, read-only files by import: ``_errors`` and
``office._encryption`` (both live in ``scripts/``). To make the package
importable standalone (tests, ``-c`` probes) regardless of whether the shim ran
first, we defensively insert the owning ``scripts/`` directory onto ``sys.path``
here — the same directory the shim inserts. It is byte-identical work, so it is
idempotent.
"""
from __future__ import annotations

import os
import sys

# scripts/ = parent of this package dir; needed for `import _errors` and
# `from office._encryption import ...`.
_SCRIPTS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from .cli import convert, main  # noqa: E402  (after sys.path bootstrap)
from .exceptions import (  # noqa: E402
    BadInput,
    InternalError,
    LanguagePackMissing,
    OcrEngineUnavailable,
    SelfOverwriteRefused,
    _AppError,
)

__all__ = [
    "main",
    "convert",
    "_AppError",
    "SelfOverwriteRefused",
    "OcrEngineUnavailable",
    "LanguagePackMissing",
    "BadInput",
    "InternalError",
]

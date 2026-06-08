#!/usr/bin/env python3
"""TASK 020: Convert a .pptx/.pptm deck into structured Markdown.

Thin CLI shim. Body lives in the ``pptx2md/`` package. See ``--help`` for the
full flag surface. Images are extracted to a sidecar ``media/`` folder and linked;
``--ocr`` (opt-in) recovers text baked into images via system ``tesseract``.
"""
from __future__ import annotations

import os
import sys

# Self-bootstrap into the skill's .venv (TASK 019 D-2) — first executable
# statement, before any heavy third-party import. Makes bare `python3
# scripts/pptx2md.py` behave identically to `./.venv/bin/python …`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # scripts/
import _venv_bootstrap  # noqa: E402

_venv_bootstrap.reexec_into_venv(requires=("pptx",))

from pptx2md import (  # noqa: E402  -- re-exports; body lives in the package
    BadInput,
    InternalError,
    LanguagePackMissing,
    OcrEngineUnavailable,
    SelfOverwriteRefused,
    _AppError,
    main,
)

__all__ = [
    "main",
    "_AppError",
    "SelfOverwriteRefused",
    "OcrEngineUnavailable",
    "LanguagePackMissing",
    "BadInput",
    "InternalError",
]


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""xlsx-9: Convert an .xlsx workbook into Markdown.

Thin CLI shim on top of the xlsx-10.A `xlsx_read/` foundation. Body
lives in `xlsx2md/`. See `--help` for the full flag list.
"""
from __future__ import annotations

import _venv_bootstrap  # self-bootstrap into scripts/.venv (TASK 019; replicated per CLAUDE.md §2)
_venv_bootstrap.reexec_into_venv(requires=("openpyxl",), _file=__file__)

import sys  # noqa: E402  -- after _venv_bootstrap re-exec (see above)
from pathlib import Path  # noqa: E402  -- after _venv_bootstrap re-exec (see above)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xlsx2md import (  # noqa: E402  -- re-exports; body lives in package
    main,
    convert_xlsx_to_md,
    _AppError,
    SelfOverwriteRefused,
    GfmMergesRequirePolicy,
    IncludeFormulasRequiresHTML,
    PostValidateFailed,
    InconsistentHeaderDepth,
    HeaderRowsConflict,
    InternalError,
)

__all__ = [
    "main",
    "convert_xlsx_to_md",
    "_AppError",
    "SelfOverwriteRefused",
    "GfmMergesRequirePolicy",
    "IncludeFormulasRequiresHTML",
    "PostValidateFailed",
    "InconsistentHeaderDepth",
    "HeaderRowsConflict",
    "InternalError",
]


if __name__ == "__main__":
    sys.exit(main())

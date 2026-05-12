#!/usr/bin/env python3
"""xlsx-8: Convert an ``.xlsx`` workbook into JSON (flat / nested).

Thin CLI shim on top of the xlsx-10.A :mod:`xlsx_read` foundation.
Body lives in the sibling :mod:`xlsx2csv2json` package; this file
only re-exports the public surface and hard-binds ``--format json``
via ``format_lock="json"``. See ``--help`` for the flag list and
``docs/ARCHITECTURE.md §4.1`` for the four JSON shape rules.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the sibling scripts/ directory importable so the package can
# resolve `_errors` (a 4-skill replicated module living one level up
# from the package).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from xlsx2csv2json import (  # noqa: E402  -- re-exports; body lives in package
    main,
    convert_xlsx_to_json,
    _AppError,
    SelfOverwriteRefused,
    MultiTableRequiresOutputDir,
    MultiSheetRequiresOutputDir,
    HeaderRowsConflict,
    InvalidSheetNameForFsPath,
    OutputPathTraversal,
    FormatLockedByShim,
    PostValidateFailed,
)

__all__ = [
    "main",
    "convert_xlsx_to_json",
    "_AppError",
    "SelfOverwriteRefused",
    "MultiTableRequiresOutputDir",
    "MultiSheetRequiresOutputDir",
    "HeaderRowsConflict",
    "InvalidSheetNameForFsPath",
    "OutputPathTraversal",
    "FormatLockedByShim",
    "PostValidateFailed",
]


if __name__ == "__main__":
    sys.exit(main(format_lock="json"))

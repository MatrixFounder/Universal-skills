#!/usr/bin/env python3
"""xlsx-2: Convert a JSON / JSONL document into a styled .xlsx workbook.

Three input shapes are auto-detected: array-of-objects (single
sheet), dict-of-arrays-of-objects (multi-sheet), and JSONL (one
JSON object per line — auto-detected via `.jsonl` extension).
Native JSON types are preserved; ISO-8601 date strings are
auto-coerced to Excel datetime cells. Output styling mirrors
csv2xlsx 1:1 (bold header, freeze, auto-filter, column widths).

Usage:
    python3 json2xlsx.py INPUT OUTPUT [flags]
    cat data.json | python3 json2xlsx.py - report.xlsx

See `json2xlsx.py --help` for the full flag list (lands in
task-004-07; this is the 004.01 skeleton).

Implementation: this shim only re-exports the public surface from
the `json2xlsx` package next to it. The body of every public
symbol lives in the package — never in this file. Single source of
truth for `convert_json_to_xlsx` is `json2xlsx/__init__.py`.

# TODO(task-004-07): CLI orchestrator + full flag set
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the sibling scripts/ directory importable so the package can
# resolve `_errors` (a 4-skill replicated module living one level up
# from the package).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from json2xlsx import (  # noqa: E402  -- re-exports; body lives in package
    main,
    _run,
    convert_json_to_xlsx,
    _AppError,
    EmptyInput,
    NoRowsToWrite,
    JsonDecodeError,
    UnsupportedJsonShape,
    InvalidSheetName,
    TimezoneNotSupported,
    InvalidDateString,
    SelfOverwriteRefused,
    PostValidateFailed,
)


if __name__ == "__main__":
    sys.exit(main())

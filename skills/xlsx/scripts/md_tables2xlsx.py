#!/usr/bin/env python3
"""xlsx-3: Convert markdown tables to a multi-sheet styled .xlsx.

Two table flavors auto-detected: GFM pipe tables (with per-column
alignment carried to Excel cell alignment) and HTML `<table>` blocks
(with `colspan`/`rowspan` honoured as Excel merged cells). Sheet
names derive from the nearest preceding heading; fallback `Table-N`.
Default-on numeric / ISO-date coercion (csv2xlsx + json2xlsx parity).

Usage:
    python3 md_tables2xlsx.py INPUT OUTPUT [flags]
    cat report.md | python3 md_tables2xlsx.py - report.xlsx

This shim only re-exports the public surface from the `md_tables2xlsx`
package next to it. The body of every public symbol lives in the
package — never in this file. Single source of truth for
`convert_md_tables_to_xlsx` is `md_tables2xlsx/__init__.py` (ARCH M4
mirrors xlsx-2 `convert_json_to_xlsx`).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the sibling scripts/ directory importable so the package can
# resolve `_errors` (a 4-skill replicated module living one level up
# from the package).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from md_tables2xlsx import (  # noqa: E402  -- re-exports; body lives in package
    main,
    _run,
    convert_md_tables_to_xlsx,
    _AppError,
    EmptyInput,
    NoTablesFound,
    MalformedTable,
    InputEncodingError,
    InvalidSheetName,
    SelfOverwriteRefused,
    PostValidateFailed,
    NoSubstantialRowsAfterParse,
)


if __name__ == "__main__":
    sys.exit(main())

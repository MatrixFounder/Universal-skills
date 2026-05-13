"""xlsx_read — read-only, closed-API reader library for .xlsx workbooks.

Foundation library for xlsx-8 (`xlsx2csv` / `xlsx2json`) and xlsx-9
(`xlsx2md`). Built once here, consumed twice. Future xlsx-10.B
refactors `xlsx_check_rules/` to consume this package as well.

This module is the **single public surface**. Everything else lives in
underscore-prefixed private modules (`_workbook`, `_sheets`, `_merges`,
`_tables`, `_headers`, `_values`, `_types`, `_exceptions`) and is
**banned from external import** by the ruff banned-api rule in
`skills/xlsx/scripts/pyproject.toml`. Cross-module imports inside this
package use sibling-relative form (`from ._merges import ...`) which is
allowed; absolute imports of `xlsx_read._*` from outside the package
fail lint.

Honest-scope catalogue (v1) — see docs/TASK.md §1.4 and
docs/ARCHITECTURE.md §10 for full rationale:

- Read-only: no write paths.
- No formula evaluation: cached value only (`include_formulas=True`
  emits the formula string verbatim).
- No pandas dependency.
- Named ranges scope=`workbook` are **ignored** in `detect_tables`;
  only sheet-scope ranges are recognised.
- ListObject `headerRowCount=0` → synthetic `col_1..col_N` headers
  + a warning in `TableData.warnings`. Output shape stays array-of-
  objects (never array-of-arrays) for downstream JSON parity.
- Overlapping `<mergeCells>` (corrupted workbooks) → fail-loud
  `OverlappingMerges`.
- Public dataclasses are `frozen=True` at the outer level. Inner
  sequences (rows, headers, warnings) are mutable `list` — caller
  must not mutate; library does not deepcopy on read.
- **NOT thread-safe.** openpyxl `Workbook` is not thread-safe.
  Caller is responsible for per-thread / per-process `WorkbookReader`
  instances. No module-level mutable singletons live in this package.
- xlsx-7 (`xlsx_check_rules/`) duplicates a portion of this reader
  logic in v1 by design — the refactor is deferred to xlsx-10.B
  (see `docs/office-skills-backlog.md`).

Caller-side responsibilities (honest scope — NOT enforced here):

- **Path allowlisting.** `open_workbook` follows symlinks via
  `Path.resolve(strict=True)`. Callers exposing this API to untrusted
  input paths must allowlist before passing.
- **Zip-bomb defense.** The library does NOT enforce compressed /
  uncompressed size caps on the input archive. Callers feeding
  untrusted input must constrain memory upstream (e.g. RLIMIT_AS,
  container memory limits, or a pre-flight size check).
- **Downstream sanitisation.** Cell values are extracted verbatim
  — no escaping for LLM, shell, or SQL contexts. Callers feeding
  output to a downstream consumer must apply context-appropriate
  escaping at the boundary.
- **`_gap_detect` allocation cap.** Refuses to materialise an
  occupancy grid larger than 1,000,000 cells (defends against
  pathological `<dimension ref="A1:XFD1048576"/>` payloads). Callers
  that need to scan a genuinely-massive sheet must use
  `detect_tables(mode="whole")` or `mode="tables-only"`.
- **Excel 1900 leap-year bug NOT compensated.** `datetime_format=
  "excel-serial"` emits true day-count from `1899-12-30`. Serials in
  the 1-59 range (legacy Jan/Feb 1900) are off by one day vs Excel's
  display.

This package does **NOT** import any cross-skill replicated file
(`_errors.py`, `_soffice.py`, `preview.py`, `office_passwd.py`,
`office/`). The 5-file silent `diff -q` gate (CLAUDE.md §2) is
untouched.
"""

from ._exceptions import (
    AmbiguousHeaderBoundary,
    EncryptedWorkbookError,
    MacroEnabledWarning,
    OverlappingMerges,
    SheetNotFound,
    TooManyMerges,
)
from ._types import (
    DateFmt,
    MergePolicy,
    SheetInfo,
    TableData,
    TableDetectMode,
    TableRegion,
    WorkbookReader,
)
from ._workbook import open_workbook

__all__ = [
    "open_workbook",
    "WorkbookReader",
    "SheetInfo",
    "TableRegion",
    "TableData",
    "MergePolicy",
    "TableDetectMode",
    "DateFmt",
    "EncryptedWorkbookError",
    "MacroEnabledWarning",
    "OverlappingMerges",
    "AmbiguousHeaderBoundary",
    "SheetNotFound",
    "TooManyMerges",
]

# Task 010-06 [LOGIC IMPLEMENTATION]: `emit_csv.py` — CSV writer + multi-file orchestration

## Use Case Connection
- UC-02 (CSV single sheet stdout)
- UC-04 (CSV multi-table subdirectory schema)
- UC-06 (CSV hyperlink markdown emission)

## Task Goal

Implement `emit_csv.py` per ARCH §2.1 F4 and §4.2: single-region
writer to file/stdout, multi-region orchestrator with subdirectory
schema `<output-dir>/<sheet>/<table>.csv`, hyperlink markdown emission
`[text](url)`, path-traversal guard (D-A8). Independent of 010-05 —
both 010-05 and 010-06 can be developed in parallel after 010-04.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2csv2json/emit_csv.py`

**Functions:**

- `emit_csv(payloads, *, output, output_dir, sheet_selector, tables_mode, include_hyperlinks, datetime_format) -> int`
  - Parameters mirror `emit_json.emit_json` minus `header_flatten_style`
    (CSV ignores it — silently per ARCH §12 Q-2) AND plus `output_dir`.
  - Logic:
    1. Materialise `payloads_list = list(payloads)` (NOTE: CSV
       theoretically streams region-by-region, but `iter_table_payloads`
       has already realised the underlying `TableData` per region, so
       per-workbook materialisation is the same cost as JSON. The
       row-by-row write is what saves memory inside each region.).
    2. Compute `len(payloads_list)`:
       - 0 regions → exit 0, no file output (empty workbook is not an error).
       - 1 region → call `_emit_single_region(payloads_list[0], output)`.
       - > 1 region → require `output_dir`:
         - If `output_dir is None`: should already have been raised by
           dispatch (MultiTableRequiresOutputDir / MultiSheetRequiresOutputDir);
           defensive re-check here raises `MultiTableRequiresOutputDir`.
         - Else: call `_emit_multi_region(payloads_list, output_dir)`.
    3. Return 0.

- `_emit_single_region(payload: tuple, output: Path | None) -> None`
  - Parameters: `(sheet_name, region, table_data)` triple.
  - Logic:
    1. Open `output` for write (UTF-8, no BOM, newline='') OR write
       to `sys.stdout` via `csv.writer(sys.stdout, ...)`.
    2. Construct `csv.writer(fp, quoting=csv.QUOTE_MINIMAL,
       lineterminator="\n")`.
    3. `writer.writerow(table_data.headers)`.
    4. For each row in `table_data.rows`: convert hyperlink cells via
       `_format_hyperlink_csv` if applicable; `writer.writerow(row)`.

- `_emit_multi_region(payloads_list: list[tuple], output_dir: Path) -> None`
  - Logic:
    1. `output_dir = output_dir.resolve()`; `output_dir.mkdir(parents=True, exist_ok=True)`.
    2. For each `(sheet_name, region, table_data)`:
       a. `region_name = region.name or f"Table-{i}"` (defensive — library should always set `.name`).
       b. **D-A8 path-traversal guard:**
          ```python
          target = (output_dir / sheet_name / f"{region_name}.csv").resolve()
          if not target.is_relative_to(output_dir):
              raise OutputPathTraversal(
                  f"Computed write-path escapes --output-dir: {target}"
              )
          ```
          (Python ≥ 3.9 has `Path.is_relative_to`; xlsx skill baseline ≥ 3.10.)
       c. `target.parent.mkdir(parents=True, exist_ok=True)`.
       d. Open `target` for write and call the same writer body as
          `_emit_single_region` (factor into a shared `_write_region_csv` helper).

- `_format_hyperlink_csv(value, href) -> str`
  - Logic: return `f"[{value}]({href})"` if `href` else `value`.
  - **NEVER** emit `=HYPERLINK(...)` (R10.d, D7 lock).
  - Edge: empty `value` → `f"[]({href})"` (valid markdown; UC-06 A2).

- `_write_region_csv(fp, table_data: TableData, *, include_hyperlinks: bool, hyperlinks_by_idx: dict | None) -> None`
  - Shared helper used by both `_emit_single_region` and `_emit_multi_region`.
  - Iterates rows, applies `_format_hyperlink_csv` per cell, calls `writer.writerow`.

**Imports added:**
```python
from __future__ import annotations

import csv
import sys
from pathlib import Path

from xlsx_read import TableData

from .exceptions import (
    MultiTableRequiresOutputDir,
    OutputPathTraversal,
)
```

**Sentinel removal:** `-997` sentinel deleted; `emit_csv` returns `0` on success.

### New Files

#### `skills/xlsx/scripts/xlsx2csv2json/tests/test_emit_csv.py`

Unit tests for `emit_csv.py`:

1. **TC-UNIT-01 (`test_emit_csv_single_region_to_file`):** 1 region, `output=/tmp/out.csv` → file contains valid CSV `csv.reader`-parseable.
2. **TC-UNIT-02 (`test_emit_csv_single_region_to_stdout`):** redirect stdout; 1 region; `output=None` → stdout contains valid CSV.
3. **TC-UNIT-03 (`test_emit_csv_quoting_minimal`):** value `"foo, bar"` (contains comma) → CSV cell quoted; value `"plain"` → no quotes.
4. **TC-UNIT-04 (`test_emit_csv_newline_in_value_quoted`):** value with `\n` → quoted with `\r\n` or `\n` line breaks inside; `csv.reader` reverses correctly.
5. **TC-UNIT-05 (`test_emit_csv_multi_region_subdirectory`):** 2 regions on 2 sheets (sheet "A" region "T1", sheet "B" region "T2"); `output_dir=/tmp/out` → files at `/tmp/out/A/T1.csv` and `/tmp/out/B/T2.csv`.
6. **TC-UNIT-06 (`test_emit_csv_multi_region_without_output_dir_defensive`):** mock 2-region payload; `output_dir=None` → raises `MultiTableRequiresOutputDir` (defensive; dispatch should have caught first).
7. **TC-UNIT-07 (`test_emit_csv_path_traversal_guard`):** mock 1 region with `region.name="../escaped"`; `output_dir=/tmp/safe` → raises `OutputPathTraversal`.
8. **TC-UNIT-08 (`test_emit_csv_path_traversal_via_sheet`):** mock 1 region with `sheet_name="../bad"` (note: dispatch's `_validate_sheet_path_components` should catch first; this is a defence-in-depth test) — emit_csv raises `OutputPathTraversal` if reached.
9. **TC-UNIT-09 (`test_emit_csv_hyperlink_markdown_format`):** include_hyperlinks=True; row contains hyperlink → CSV cell value is `"[text](url)"`.
10. **TC-UNIT-10 (`test_emit_csv_no_hyperlink_formula_emission`):** regression — assert NO row contains `=HYPERLINK(` substring (R10.d lock).
11. **TC-UNIT-11 (`test_emit_csv_empty_hyperlink_text`):** hyperlink value is empty string → CSV cell `"[](url)"` (valid markdown, UC-06 A2).
12. **TC-UNIT-12 (`test_emit_csv_empty_payloads`):** 0 regions → exit 0, no files created.
13. **TC-UNIT-13 (`test_emit_csv_parent_dir_auto_create`):** `output=/tmp/sub/dir/out.csv`; `/tmp/sub/dir` doesn't exist → emit creates parent.
14. **TC-UNIT-14 (`test_emit_csv_utf8_no_bom`):** non-ASCII sheet data; CSV file is UTF-8 with no BOM.
15. **TC-UNIT-15 (`test_emit_csv_lineterminator_lf`):** check raw bytes — lines end with `\n` only (not `\r\n`).
16. **TC-UNIT-16 (`test_emit_csv_sheet_name_with_underscores`):** sheet `"with__double_underscore"` produces directory `with__double_underscore/` (NOT split — L4 lock).

#### `skills/xlsx/scripts/xlsx2csv2json/tests/fixtures/single_sheet_with_hyperlinks.xlsx`

Hand-built: 1 sheet "Links", header `["text", "url"]`, 3 rows where
column `url` cells carry openpyxl `Hyperlink` objects.

### Component Integration

- `cli._dispatch_to_emit` already wires `emit_csv` from 010-04; this
  task swaps the stub for the real body.
- `_emit_multi_region` is the **only** place that creates per-region
  files; it's also the only place that performs the D-A8
  path-traversal guard.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (`csv_single_sheet_stdout`):** maps to TASK §5.5 #7 —
   `python3 xlsx2csv.py fixtures/single_sheet_simple.xlsx --sheet Data
   > /tmp/out.csv` → exit 0; `/tmp/out.csv` is valid CSV.
2. **TC-E2E-02 (`csv_multi_table_subdirectory_schema`):** maps to
   TASK §5.5 #15 — `python3 xlsx2csv.py fixtures/multi_table_listobjects.xlsx
   --tables listobjects --output-dir /tmp/multi` → exit 0; files at
   `/tmp/multi/Summary/RevenueTable.csv` and
   `/tmp/multi/Summary/CostsTable.csv`.

### Unit Tests

(16 listed above.)

### Regression Tests

- All previous tests green (010-01..010-05).
- `ruff check scripts/` green.
- xlsx_read frozen-surface regression: `import xlsx_read; len(xlsx_read.__all__) == 13`.

## Acceptance Criteria

- [ ] `_emit_single_region`, `_emit_multi_region`, `_format_hyperlink_csv`, `_write_region_csv` implemented.
- [ ] All 16 unit tests in `test_emit_csv.py` pass.
- [ ] Both E2E pass.
- [ ] Path-traversal guard active (D-A8); covers `..` in sheet OR region name.
- [ ] No `=HYPERLINK()` formula emission (regression TC-UNIT-10 locked).
- [ ] Subdirectory schema `<sheet>/<table>.csv` — sheet names with `__` are NOT mistaken for separator (L4 lock).
- [ ] UTF-8 output, no BOM, `\n` line-terminator.
- [ ] `ruff check scripts/` green.
- [ ] 12-line `diff -q` silent.

## Notes

- **CSV "streaming":** the per-region body uses `csv.writer.writerow`
  which writes row-by-row to the file handle. The
  `iter_table_payloads` upstream is NOT a true stream (it returns
  whole `TableData` objects), but per-region the row write IS
  incremental.
- **Path.is_relative_to availability:** Python 3.9+. xlsx skill
  baseline is 3.10 (TASK §4.3), so safe.
- **Multi-sheet single-region CSV:** with `--sheet all` and each
  sheet having 1 region (so `len(regions) > 1` only because of
  multi-sheet, not multi-table), we still need `--output-dir` per
  TASK §R12.f. Defensive check in `_emit_multi_region` matches
  dispatch's earlier raise.
- The decision to keep `_validate_sheet_path_components` in
  `dispatch` (not `emit_csv`) is per ARCH §2.1 F2 — defense-in-depth
  is the emit-csv path-traversal guard.

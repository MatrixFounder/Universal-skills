# Task 010-05 [LOGIC IMPLEMENTATION]: `emit_json.py` — JSON shape builder + writer

## Use Case Connection
- UC-01 (JSON single sheet happy path)
- UC-03 (multi-table nested shape)
- UC-05 (multi-row header flatten + `--header-flatten-style`)
- UC-06 (hyperlink dict-shape emission)

## Task Goal

Implement `emit_json.py` per ARCH §2.1 F3 and §4.1: pure-function
shape builder (`_shape_for_payloads`) for the four JSON shapes (R11
a–e), `_row_to_dict` helper, `emit_json` driver. Use
`json.dumps(..., ensure_ascii=False, indent=2, sort_keys=False)` per
D-A9.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2csv2json/emit_json.py`

**Functions:**

- `emit_json(payloads, *, output, sheet_selector, tables_mode, header_flatten_style, include_hyperlinks, datetime_format) -> int`
  - Parameters:
    - `payloads` — iterator of `(sheet_name, TableRegion, TableData)`.
    - `output` — `Path | None` (None → stdout).
    - `sheet_selector` — `"all"` or sheet name (controls single vs multi-sheet form).
    - `tables_mode` — `"whole" | "listobjects" | "gap" | "auto"`.
    - `header_flatten_style` — `"string" | "array"` (controls multi-row header rendering).
    - `include_hyperlinks` — bool (controls hyperlink cell shape).
    - `datetime_format` — `"ISO" | "excel-serial" | "raw"` (verified passthrough; emit format mostly governed by library).
  - Logic:
    1. Materialise `payloads_list = list(payloads)` (per ARCH §8: JSON path accumulates).
    2. `shape = _shape_for_payloads(payloads_list, sheet_selector=sheet_selector, tables_mode=tables_mode, header_flatten_style=header_flatten_style, include_hyperlinks=include_hyperlinks)`.
    3. `text = json.dumps(shape, ensure_ascii=False, indent=2, sort_keys=False)`.
    4. Write `text` to `output` (UTF-8, no BOM) OR `sys.stdout.write(text + "\n")` if `output is None`.
    5. Return 0.
  - Raises: nothing custom; lets `_AppError`s from upstream propagate.

- `_shape_for_payloads(payloads_list: list[tuple], *, sheet_selector, tables_mode, header_flatten_style, include_hyperlinks) -> Any`
  - Pure function (unit-testable on synthetic data).
  - Logic — apply the 4 shape rules from ARCH §4.1:
    1. Group `payloads_list` by `sheet_name` (preserving doc order via `dict` insertion order).
    2. For each sheet, compute the per-sheet shape:
       - 1 region → flat array-of-objects (rule 1).
       - > 1 region → `{"tables": {region.name: [dict_rows]}}` (rule 3 — note: the per-sheet dict is `{"tables": {...}}` only when nested under the multi-sheet wrapper; standalone single-sheet multi-region uses `{region.name: [dict_rows]}` directly per rule 4).
    3. Apply per-mode wrapping:
       - **Single sheet, single region** (rule 1): return flat array.
       - **Single sheet, multi-region** (rule 4): return `{region.name: [...]}`.
       - **Multi-sheet, all single-region** (rule 2): return `{sheet: [...]}`.
       - **Multi-sheet, mixed** (rule 3): return `{sheet: [...] | {"tables": {...}}}` — mixed-shape per sheet IS the contract (ARCH §4.1).

- `_row_to_dict(headers: list, row: list, *, header_flatten_style: str, include_hyperlinks: bool, hyperlinks_by_idx: dict[int, str] | None = None) -> dict`
  - Parameters:
    - `headers` — flattened header list from `TableData.headers`.
    - `row` — values from `TableData.rows[i]`.
    - `header_flatten_style` — when `"array"` AND the header was originally multi-row (contains U+203A separator), split key into a list (caller decides — see Note 1 below).
    - `include_hyperlinks` — when True AND `hyperlinks_by_idx[i]` set, emit dict-form `{"value": v, "href": h}`.
    - `hyperlinks_by_idx` — optional index → href mapping (caller pre-extracts).
  - Logic: zip headers with row values; if hyperlink applies replace value with dict; emit dict.
  - **Key transform for `header_flatten_style == "array"`:**
    `key.split("›")` → list of N parts, stripped of whitespace.

**Imports added:**
```python
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
```

**Sentinel removal:** `-997` sentinel deleted; `emit_json` returns `0` on success.

### Hyperlink dict-shape extraction (R10.b)

The library `xlsx_read.read_table(include_hyperlinks=True)` exposes
hyperlinks via... (verify in implementation — likely a parallel
`TableData.hyperlinks: list[list[str | None]]` or a sentinel in
`TableData.rows` as `{"value", "href"}` already). **Investigation
required at implementation time:** read `skills/xlsx/scripts/xlsx_read/
_types.py:read_table` and `_values.py:extract_cell` to confirm. If the
library returns the dict-form already, `_row_to_dict` passes it
through unchanged. If the library returns plain values + a parallel
hyperlink map, `_row_to_dict` zips and constructs the dict.

**Honest scope note:** the implementer is permitted to extend
`xlsx_read._values.extract_cell` IF investigation reveals the
hyperlink handle is not exposed at the public boundary — BUT this
crosses the xlsx-10.A frozen-surface boundary. Preferred path:
re-extract hyperlinks via a fresh openpyxl-level pass on the region
in `dispatch` (call site of `read_table`) and pass the parallel map
down to `_row_to_dict`. Avoids xlsx-10.A modification.

### New Files

#### `skills/xlsx/scripts/xlsx2csv2json/tests/test_emit_json.py`

Unit tests for `emit_json.py`:

1. **TC-UNIT-01 (`test_shape_single_sheet_single_region_flat`):** input = `[("Sheet1", region_A, table_A)]` → flat `[{...}, ...]`.
2. **TC-UNIT-02 (`test_shape_multi_sheet_all_single_region`):** input = `[("S1", r1, t1), ("S2", r2, t2)]` → `{"S1": [...], "S2": [...]}`.
3. **TC-UNIT-03 (`test_shape_single_sheet_multi_region`):** input = `[("S1", rA, tA), ("S1", rB, tB)]` → `{"TableA": [...], "TableB": [...]}` (no enclosing sheet key).
4. **TC-UNIT-04 (`test_shape_multi_sheet_multi_region_nested`):** input = `[("S1", rA, tA), ("S1", rB, tB), ("S2", rC, tC)]` → `{"S1": {"tables": {"TableA": [...], "TableB": [...]}}, "S2": [...]}` (mixed shape).
5. **TC-UNIT-05 (`test_shape_empty_payloads`):** → `[]` (empty list).
6. **TC-UNIT-06 (`test_shape_region_order_preserved`):** regions yielded in doc order are preserved in `tables` dict insertion order.
7. **TC-UNIT-07 (`test_row_to_dict_simple`):** `headers=["a", "b"], row=[1, 2]` → `{"a": 1, "b": 2}`.
8. **TC-UNIT-08 (`test_row_to_dict_header_flatten_style_array_splits_on_U203A`):** `headers=["2026 plan › Q1", "2026 plan › Q2"], row=[100, 200], style="array"` → `{tuple ish-form? or list-form per ARCH }`. **Decision:** since JSON cannot have list keys, `"array"` style produces array-of-rows where each row is **itself** array-of-`{key_parts: [], value: ...}` objects. **Re-spec this in 010-05 implementation; tentative shape:** `[[{"key": ["2026 plan", "Q1"], "value": 100}, {"key": ["2026 plan", "Q2"], "value": 200}], ...]`. **Action:** at implementation time, finalise the array-shape contract and pin in `references/json-shapes.md` (010-07). For this task, the unit test asserts that splitting happens; the JSON envelope is whatever the implementer locks.
9. **TC-UNIT-09 (`test_row_to_dict_hyperlink_dict_shape`):** `include_hyperlinks=True`, hyperlink at col-0 with href `"http://x"` → `{"a": {"value": "click", "href": "http://x"}, "b": 2}`.
10. **TC-UNIT-10 (`test_emit_json_stdout`):** redirect stdout, call `emit_json(payloads, output=None, ...)` → captured stdout contains valid JSON parseable by `json.loads`.
11. **TC-UNIT-11 (`test_emit_json_file_path`):** call with `output=Path("/tmp/out.json")` → file exists; `json.loads(file.read_text())` succeeds.
12. **TC-UNIT-12 (`test_emit_json_utf8_no_bom`):** sheet with non-ASCII data; output file decoded as UTF-8 succeeds; first 3 bytes are NOT `\xef\xbb\xbf`.
13. **TC-UNIT-13 (`test_emit_json_special_char_sheet_name_preserved`):** sheet name `"Q1 / Q2 split"` → JSON key preserves the `/` (no escape) but `\"` and `\\` escaped per RFC.
14. **TC-UNIT-14 (`test_emit_json_indent_2`):** output contains `\n  ` (2-space indent).

### Component Integration

- `cli._dispatch_to_emit` already wires `emit_json` from 010-04;
  this task swaps the stub for the real body.
- `emit_csv` (010-06) is independent — both consume the same
  iterator.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (`json_single_sheet_default_flags`):** maps to TASK
   §5.5 #1 — `python3 xlsx2json.py fixtures/single_sheet_simple.xlsx
   /tmp/out.json` → exit 0; file is valid JSON matching expected
   shape (flat array-of-objects). Full assertion deferred to 010-07
   E2E cluster; this task only asserts exit 0 + parseable.
2. **TC-E2E-02 (`json_multi_table_listobjects_nested`):** maps to
   TASK §5.5 #10 — `python3 xlsx2json.py fixtures/multi_table_listobjects.xlsx
   /tmp/out.json --tables listobjects` → JSON shape contains
   `tables: {RevenueTable: [...], CostsTable: [...]}`.

### Unit Tests

(14 listed above.)

### Regression Tests

- All previous tests green.
- `ruff check scripts/` green.
- xlsx_read public surface still frozen (regression: `import xlsx_read; xlsx_read.__all__` unchanged).

## Acceptance Criteria

- [ ] `_shape_for_payloads` implemented (pure function).
- [ ] `_row_to_dict` handles hyperlink dict-shape + array-style header.
- [ ] `emit_json` writes valid JSON to file or stdout.
- [ ] All 14 unit tests in `test_emit_json.py` pass.
- [ ] Both E2E (single-sheet, multi-table) pass.
- [ ] `--header-flatten-style array` produces a documented JSON
  shape (locked in 010-07 references).
- [ ] Non-ASCII chars preserved as UTF-8 (no BOM).
- [ ] `ruff check scripts/` green.
- [ ] 12-line `diff -q` silent.

## Notes

- **Hyperlink extraction:** verify at implementation if xlsx_read's
  `read_table(include_hyperlinks=True)` exposes hyperlinks in a
  consumable form. If not, fall back to a parallel openpyxl pass in
  `dispatch._extract_hyperlinks_for_region(reader, region)` — keeps
  xlsx-10.A frozen. Document the chosen path in
  `xlsx2csv2json/__init__.py` honest-scope docstring (per 010-07).
- **`--header-flatten-style array` JSON shape:** decide at
  implementation time between (a) `{"key": [...], "value": ...}`
  per-cell envelope OR (b) parallel header-keys array. Lock in
  010-07 references.
- **Perf gate:** include opt-in 10K × 20 perf test gated by
  `RUN_PERF_TESTS=1` env (mirror xlsx-2 D8 pattern). Out-of-budget is
  a warning, not a failure, in v1 per plan §5 R-5.

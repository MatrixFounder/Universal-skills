# Task 009-05: F4 `_tables.py` — 3-tier table detector [LOGIC IMPLEMENTATION]

## Use Case Connection
- **UC-03** (Detect tables — main + alternatives A1–A6).

## RTM Coverage
- **[R5]** `detect_tables()` — Tier-1 ListObjects (re-parse
  `xl/tables/tableN.xml` via lxml with hardened parser), Tier-2
  sheet-scope named ranges, Tier-3 gap-detection. Defaults
  `gap_rows=2`, `gap_cols=1` (M4 fix). Modes `auto` / `tables-only`
  / `whole`.

## Task Goal

Replace stubs in `_tables.py` with the real 3-tier detector:
- **Tier-1 (ListObjects):** parse `xl/tables/tableN.xml` parts via
  `openpyxl`'s low-level access (`wb.loaded_theme` is not enough —
  use `ws.tables`); for each table, emit `TableRegion(source="listobject",
  name=table_name, listobject_header_row_count=table.headerRowCount)`.
- **Tier-2 (sheet-scope named ranges):** iterate `wb.defined_names`
  with `localSheetId` matching the target sheet's index; skip
  ranges already covered by a Tier-1 region; emit
  `TableRegion(source="named_range", name=range_name,
  listobject_header_row_count=None)`.
- **Tier-3 (gap-detect):** for the remaining sheet area, split on
  ≥ `gap_rows` consecutive empty rows AND/OR ≥ `gap_cols`
  consecutive empty cols; emit `TableRegion(source="gap_detect",
  name=f"Table-{N}")` in document order.
- **Modes:** `"auto"` runs all three tiers. `"tables-only"` runs
  Tier-1 + Tier-2 only. `"whole"` returns a single region
  spanning `ws.dimensions`.

## Changes Description

### New Files
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/listobject_one.xlsx` —
  workbook with one Excel Table (ListObject) named `"Revenue"`,
  `headerRowCount=1`.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/listobject_no_header.xlsx`
  — ListObject `"NoHead"` with `headerRowCount=0`.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/named_range_sheet_scope.xlsx`
  — single sheet-scoped `<definedName>` `"KPI"` pointing to a
  range.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/named_range_workbook_scope.xlsx`
  — workbook-scope named range (must be **ignored** by Tier-2).
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/gap_two_tables.xlsx`
  — two data rectangles separated by 2 empty rows.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/gap_one_col.xlsx` —
  two rectangles separated by 1 empty column.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/listobject_overlap_named.xlsx`
  — ListObject AND a sheet-scope named range covering the same
  rectangle (Tier-1 must win, UC-03 A4).
- `skills/xlsx/scripts/xlsx_read/tests/test_tables.py` — unit + E2E.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_read/_tables.py`
- **Replace** stub with:
  - `def detect_tables(wb, sheet_name, *, mode="auto", gap_rows=2,
    gap_cols=1) -> list[TableRegion]`:
    - If `mode == "whole"`: read `ws.dimensions`; emit one region.
    - Else collect Tier-1 + Tier-2; if `mode == "auto"`, append
      Tier-3 over the area not covered by tiers above.
  - `def _listobjects_for_sheet(wb, sheet_name) -> list[TableRegion]`:
    - Iterate `wb[sheet_name].tables.values()` (openpyxl exposes
      ListObjects as a dict keyed by table name).
    - Parse `table.ref` (e.g. `"A1:E20"`) via openpyxl's
      `range_boundaries` helper.
    - Capture `table.headerRowCount` into
      `listobject_header_row_count`.
  - `def _named_ranges_for_sheet(wb, sheet_name) -> list[TableRegion]`:
    - For each `name in wb.defined_names`: read its
      `.localSheetId`; skip if `None` (workbook-scope) or if it
      points to a different sheet.
    - Resolve `.destinations` to `(sheet, range_str)` tuples;
      emit one `TableRegion` per resolved rectangle (defended-in-
      depth: ignore destinations whose sheet ≠ requested).
  - `def _gap_detect(ws, claimed, gap_rows, gap_cols) ->
    list[TableRegion]`:
    - Compute the "free area" = `ws.dimensions` minus `claimed`
      bounding boxes (claimed list is small — set-difference at
      cell-level acceptable).
    - Sweep top-to-bottom, left-to-right; emit one region per
      contiguous non-empty rectangle separated from neighbours by
      ≥ `gap_rows` empty rows OR ≥ `gap_cols` empty cols.
  - `def _has_overlap(region, claimed) -> bool` — helper used to
    drop Tier-2 ranges that overlap Tier-1 (UC-03 A4).

## Test Cases

### End-to-end Tests (TC-E2E-* in `test_tables.py`)

1. **TC-E2E-01 (listobject_detect):** `detect_tables(wb, "Sheet1",
   mode="auto")` on `listobject_one.xlsx` returns exactly one
   region with `source="listobject"`, `name="Revenue"`,
   `listobject_header_row_count=1`.
2. **TC-E2E-02 (listobject_no_header):** Same shape on
   `listobject_no_header.xlsx`; region carries
   `listobject_header_row_count=0` (the actual synthetic-header
   emit is in 009-06).
3. **TC-E2E-03 (named_range_sheet_scope_detected):** `detect_tables`
   on `named_range_sheet_scope.xlsx` returns one
   `source="named_range"` region.
4. **TC-E2E-04 (named_range_workbook_scope_ignored):** `detect_tables`
   on `named_range_workbook_scope.xlsx` returns `[]` (Tier-2 sheet-
   scope only, D8 honest-scope item d).
5. **TC-E2E-05 (gap_two_tables_default_thresholds):** `detect_tables`
   on `gap_two_tables.xlsx` with default `gap_rows=2/gap_cols=1`
   returns two regions, both `source="gap_detect"`, names
   `"Table-1"` and `"Table-2"` in document order.
6. **TC-E2E-06 (gap_one_col):** `gap_one_col.xlsx` → 2 regions
   (1 empty col = sufficient default).
7. **TC-E2E-07 (listobject_wins_over_named):** `detect_tables` on
   `listobject_overlap_named.xlsx` returns **one** region with
   `source="listobject"` (Tier-1 wins, UC-03 A4).
8. **TC-E2E-08 (mode_whole):** `mode="whole"` on any fixture
   returns exactly one region spanning the full `ws.dimensions`.
9. **TC-E2E-09 (mode_tables_only_skips_gap):** `mode="tables-only"`
   on `gap_two_tables.xlsx` (no ListObjects, no named ranges)
   returns `[]`.

### Unit Tests

1. **TC-UNIT-01 (`_listobjects_for_sheet` parse_ref):** Manually
   construct a workbook with a Table at `B2:D5`; assert the
   returned region's `top_row=2, left_col=2, bottom_row=5,
   right_col=4`.
2. **TC-UNIT-02 (`_named_ranges_for_sheet` localSheetId match):**
   Build a workbook with three sheets and a named range scoped to
   sheet index 1; assert it appears for sheet[1] and not for [0]
   or [2].
3. **TC-UNIT-03 (`_gap_detect` threshold boundary):** Build a
   fixture with exactly 1 empty row between two rectangles; with
   `gap_rows=2` returns ONE region (over-split avoided per M4
   fix); with `gap_rows=1` returns TWO.
4. **TC-UNIT-04 (`_has_overlap`):** Truth-table for adjacent vs.
   overlapping rectangles.

### Regression Tests
- 009-02 + 009-03 + 009-04 tests green.
- 12-line `diff -q` silent.

## Acceptance Criteria

- [ ] All 9 TC-E2E and 4 TC-UNIT cases pass.
- [ ] `detect_tables(mode="whole")` returns exactly one region.
- [ ] Workbook-scope named ranges are silently ignored (D8).
- [ ] Tier-1 wins over Tier-2 on rectangular overlap (UC-03 A4).
- [ ] `_gap_detect` honours `gap_rows=2` default — single-empty-row
  separators do NOT over-split (M4 fix).
- [ ] `ruff` + `validate_skill.py` exit 0; 12-line silent.

## Notes

- openpyxl 3.1+ exposes ListObjects via `Worksheet.tables` (a
  `TableList` dict-like). If a fixture cannot be created via
  openpyxl (`Workbook.tables.add`) at test time, hand-build via
  the lxml writer used by xlsx-7 fixtures — same pattern.
- Defined-names parsing must guard against named ranges whose
  destinations resolve to multiple sheets (Excel allows
  comma-separated destinations). For v1, take the first
  destination matching the requested sheet and ignore the rest;
  this matches the "v1 scope" intent of TASK §1.4.
- `_gap_detect` complexity is bounded by `ws.calculate_dimension()`
  cell count. For sheets larger than 1M cells, performance budget
  (§4.1) is 5 s — acceptable; if a profile shows hot-spot, defer to
  v2 streaming optimisation.

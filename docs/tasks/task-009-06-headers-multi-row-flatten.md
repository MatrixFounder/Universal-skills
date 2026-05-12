# Task 009-06: F5 `_headers.py` — multi-row + flatten + synthetic [LOGIC IMPLEMENTATION]

## Use Case Connection
- **UC-04** main scenario step 3 + Alternatives A1 (synthetic
  headers), A2 (ambiguous boundary), A8 (explicit `header_rows=0`).

## RTM Coverage
- **[R7]** Multi-row header detection + ` › ` (U+203A) flatten +
  synthetic `col_1..col_N` + `AmbiguousHeaderBoundary` warning.

## Task Goal

Replace stubs in `_headers.py` with real logic:
- `detect_header_band(ws, region, hint)`:
  - If `hint` is an int ≥ 0 → return it verbatim.
  - If `hint == "auto"`: scan from `region.top_row` downward; a row
    is a "header row" if it contains at least one column-spanning
    merge (width ≥ 2) confined to the region's column span. Stop
    at the first non-header row; return that 0-based count
    (default `1` if no merges found).
- `flatten_headers(rows, header_rows, separator=" › ")`:
  - Vertical-join top→sub keys with U+203A separator (` › `).
  - Empty cells inherit the value above (sticky fill — common
    Excel convention for multi-row headers).
  - Returns `(list[str], list[str])` — flattened keys + warnings.
- `synthetic_headers(width)` returns `[f"col_{i+1}" for i in
  range(width)]` (final form, unchanged from stub).
- `_ambiguous_boundary_check(merges, region, header_rows)`:
  - For each merge in the region, check if it **straddles** the
    `top_row + header_rows - 1` ↔ `top_row + header_rows` boundary.
  - If any does → emit `AmbiguousHeaderBoundary` via
    `warnings.warn` and append a string to the returned warnings
    list. **Does not raise.**

## Changes Description

### New Files
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/headers_single_row.xlsx`
  — standard 1-row header.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/headers_two_row_merged.xlsx`
  — 2-row header with top row containing 1×2 merges
  (`"2026 Plan"` over `"Q1"`/`"Q2"`).
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/headers_three_row.xlsx`
  — 3-row header (top: year, middle: quarter, bottom: metric).
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/headers_ambiguous.xlsx`
  — a 1×3 merge straddling the detected 1-row-header/body boundary.
- `skills/xlsx/scripts/xlsx_read/tests/test_headers.py` — unit + E2E.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_read/_headers.py`
- **Replace** stub with the full implementation described in the
  Goal section.
- Add internal helper `_is_column_spanning_merge(merge, region) ->
  bool` — true iff the merge's `(top_row == top_row)` AND
  `right_col - left_col >= 1` AND merge confined to region's col
  span.
- Sticky-fill logic: when flattening, if `row[i] is None` or `""`,
  inherit from `row[i-1]` of the **same** header level (left-fill,
  to handle Excel's "merge horizontally then leave right cells
  empty" pattern).

## Test Cases

### End-to-end Tests (TC-E2E-* in `test_headers.py`)

1. **TC-E2E-01 (single_row):** Open
   `headers_single_row.xlsx`; for the corresponding region call
   `detect_header_band(ws, region, "auto")` → returns `1`.
   `flatten_headers(rows[:1], 1)` returns the header row verbatim.
2. **TC-E2E-02 (two_row_merged_auto):** Open
   `headers_two_row_merged.xlsx`; `detect_header_band(..., "auto")`
   → returns `2`. `flatten_headers(rows[:2], 2)` returns
   `["2026 Plan › Q1", "2026 Plan › Q2", ...]` with U+203A.
3. **TC-E2E-03 (three_row_auto):** Same shape on
   `headers_three_row.xlsx` → returns `3`; keys are
   `"Top › Mid › Bot"` triples.
4. **TC-E2E-04 (ambiguous_boundary_warns):** Open
   `headers_ambiguous.xlsx`; under
   `warnings.catch_warnings(record=True)`, `_ambiguous_boundary_check`
   emits exactly one `AmbiguousHeaderBoundary` warning.
5. **TC-E2E-05 (synthetic_headers_zero):** `detect_header_band(ws,
   region, hint=0)` → returns 0; then `synthetic_headers(width=5)`
   returns `["col_1", ..., "col_5"]`.
6. **TC-E2E-06 (hint_int_passthrough):** `detect_header_band(ws,
   region, hint=2)` returns `2` unconditionally (no auto-detect).

### Unit Tests

1. **TC-UNIT-01 (U+203A_separator_byte):** `flatten_headers(...)`
   output contains `›` codepoint exactly where expected;
   regression guard against accidental replacement with `/` or `>`.
2. **TC-UNIT-02 (sticky_fill_left):** Row `["A", None, "B"]`
   flattened with `[None, "x", None]` below → keys
   `["A › x", "A › x", "B › x"]` (sticky-fill left, then sticky-
   fill from above).
3. **TC-UNIT-03 (`_is_column_spanning_merge`):** Truth-table over
   row-merge / col-merge / rect-merge / out-of-region cases.
4. **TC-UNIT-04 (synthetic_headers_format):** Output is exactly
   `[f"col_{i+1}" for i in range(N)]` — regression against
   accidental zero-based or zero-pad changes.

### Regression Tests
- All 009-0X test files (X ≤ 5) green.
- 12-line `diff -q` silent.

## Acceptance Criteria

- [ ] `detect_header_band(..., "auto")` correctly returns 1, 2,
  3 for the three header fixtures.
- [ ] `flatten_headers` uses `›` (U+203A) as separator.
- [ ] `AmbiguousHeaderBoundary` warning is emitted via
  `warnings.warn`, NOT raised.
- [ ] `synthetic_headers(N)` returns the exact `col_1..col_N`
  format.
- [ ] All 6 TC-E2E and 4 TC-UNIT cases pass.
- [ ] `ruff` + `validate_skill.py` exit 0; 12-line silent.

## Notes

- The auto-detect is **deliberately simple**: any column-spanning
  merge in the top rows is a signal. False-positives are
  acceptable in v1 (caller can override via integer `header_rows`).
- The "sticky-fill left" pattern handles Excel's idiom of merging
  cells horizontally then writing the label in the leftmost cell
  — common in financial reports.
- The actual `synthetic_headers` emit + warning surfacing happens
  in 009-08 (`WorkbookReader.read_table` wires it). This task
  only delivers the helper.

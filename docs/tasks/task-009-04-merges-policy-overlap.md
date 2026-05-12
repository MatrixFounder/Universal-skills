# Task 009-04: F3 `_merges.py` — parse + 3 policies + overlap fail-loud [LOGIC IMPLEMENTATION]

## Use Case Connection
- **UC-04** main scenario step 4 (apply merge policy) + Alternative
  A7 (overlapping merges → `OverlappingMerges`).

## RTM Coverage
- **[R9]** Merge resolution + 3 policies + overlapping fail-loud
  (M8 / D4 fix — `_overlapping_merges_check` runs before policy
  application, regardless of openpyxl's undefined behaviour).

## Task Goal

Replace stubs in `_merges.py` with real logic:
- `parse_merges(ws)` reads `ws.merged_cells.ranges` and returns a
  `MergeMap = dict[tuple[int,int], tuple[int,int]]` mapping each
  anchor `(row, col)` to its inclusive bottom-right `(row, col)`.
- `apply_merge_policy(rows, merges, policy)` is a **pure** function:
  it returns a new row-grid, never mutates the input.
  - `"anchor-only"`: only `(top_row, left_col)` carries the value;
    other cells in the merge range → `None`.
  - `"fill"`: anchor value broadcast to every cell.
  - `"blank"`: identical to `"anchor-only"` (semantic alias; reserved
    for future divergence per ARCHITECTURE §4.1 enum note).
- `_overlapping_merges_check(ranges)` raises `OverlappingMerges`
  on the **first** intersecting pair detected (fail-loud, M8 fix).
  Runs **before** `apply_merge_policy` in the caller pipeline.

## Changes Description

### New Files
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/merges_row.xlsx` —
  one merge spanning 1×3 (single row, 3 cols).
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/merges_col.xlsx` —
  one merge spanning 3×1.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/merges_rect.xlsx` —
  one 3×3 rectangular merge.
- `skills/xlsx/scripts/xlsx_read/tests/fixtures/merges_overlap.xlsx`
  — **the same fixture as 009-02's `overlapping_merges.xlsx`** —
  re-used (do not duplicate; reference path).
- `skills/xlsx/scripts/xlsx_read/tests/test_merges.py` — unit +
  E2E.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_read/_merges.py`
- **Replace** stubs with:
  - `def parse_merges(ws) -> MergeMap` — iterate
    `ws.merged_cells.ranges`; for each `CellRange r` build
    `((r.min_row, r.min_col), (r.max_row, r.max_col))`.
  - `def apply_merge_policy(rows, merges, policy) ->
    list[list[Any]]` — implement the three policies on a deep copy
    of `rows` (list comprehension `[[...] for row in rows]` — no
    `copy.deepcopy` because rows are list[list[primitive]]).
  - `def _overlapping_merges_check(ranges) -> None` — O(n²)
    pairwise check (n is small in practice — typical workbooks have
    < 50 merges per sheet); on the first intersecting pair raise
    `OverlappingMerges(f"Overlapping merges: {r1} ∩ {r2}")`.

## Test Cases

### End-to-end Tests (TC-E2E-* in `test_merges.py`)

1. **TC-E2E-01 (parse_row_merge):** Open `merges_row.xlsx`; assert
   `parse_merges(ws)` returns exactly one entry mapping the
   anchor to the bottom-right cell of the 1×3 range.
2. **TC-E2E-02 (parse_col_merge):** Same shape, 3×1.
3. **TC-E2E-03 (parse_rect_merge):** Same shape, 3×3.
4. **TC-E2E-04 (apply_anchor_only_3_fixtures):** For each of
   row/col/rect fixtures, materialise the cell grid manually,
   apply `anchor-only` policy, assert the anchor retains its value
   and **all other cells in the merge range are `None`**.
5. **TC-E2E-05 (apply_fill_3_fixtures):** Same matrix; assert
   **every cell in the range carries the anchor value**.
6. **TC-E2E-06 (apply_blank_3_fixtures):** Same matrix; result
   identical to `anchor-only` (semantic alias).
7. **TC-E2E-07 (overlap_fail_loud):** Open `merges_overlap.xlsx`;
   call `_overlapping_merges_check(ws.merged_cells.ranges)`;
   assert `OverlappingMerges` raised with both range strings in
   the message.

### Unit Tests

1. **TC-UNIT-01 (pure_function_no_mutation):** Build a row-grid
   `original`; deep-copy it; call `apply_merge_policy(original,
   ...)`; assert `original` unchanged.
2. **TC-UNIT-02 (empty_merges_passthrough):** `apply_merge_policy
   (rows, {}, "anchor-only")` returns rows shape-identical to
   input.
3. **TC-UNIT-03 (overlap_detector_no_false_positive):** Adjacent
   non-overlapping ranges (e.g. `A1:A3` and `A4:A6`) produce no
   exception.
4. **TC-UNIT-04 (overlap_detector_partial_corner_overlap):**
   `A1:B2` and `B2:C3` (share single cell `B2`) raise
   `OverlappingMerges`.

### Regression Tests
- 009-02 + 009-03 tests still green.
- 12-line cross-skill `diff -q` silent.

## Acceptance Criteria

- [ ] All 7 TC-E2E and 4 TC-UNIT cases pass.
- [ ] `apply_merge_policy` is pure (TC-UNIT-01 enforces).
- [ ] `_overlapping_merges_check` runs in O(n²) where n is the
  number of merges (acceptable; merges per sheet are bounded in
  real workbooks).
- [ ] `ruff` + `validate_skill.py` exit 0; 12-line silent.

## Notes

- "blank" policy in v1 is functionally identical to "anchor-only".
  This is **intentional** (ARCHITECTURE §4.1 enum note): the slot
  is reserved for a future v2 divergence (`""` instead of `None`
  for non-anchor cells). Tests assert identity, not difference.
- The pairwise overlap check is O(n²) by design — sorting + sweep
  would be O(n log n) but adds complexity for a worst-case n that
  is small in practice. Defer optimisation if profiling shows it.

# Task 011.02 — [R2] Bounded merge-count in `parse_merges(ws)`

## Use Case Connection
- UC-02: Bounded merge-count in `parse_merges(ws)` (`xlsx-8a-02`)

## Task Goal
Add a hard cap on the merge-range iteration in
[`xlsx_read._merges.parse_merges`](../../skills/xlsx/scripts/xlsx_read/_merges.py)
to close the Sec-MED-3 memory-exhaustion vector raised by
`/vdd-multi-3` 2026-05-13. A hand-crafted OOXML workbook with
millions of `<mergeCell>` entries (legal per the spec) currently
materialises the full Python dict in RAM before any
`apply_merge_policy` work begins. The 100K cap matches the
practical real-world upper bound (largest seen: ~8K merges on a
200-sheet financial model) with 10× headroom.

This task **re-opens a 2nd file in the xlsx-10.A frozen surface**
(per §15.5 / §15.10.5 carve-out boundary rule); the change is
additive (new constant, new exception class, new export), no
existing function signature mutates.

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_read/_exceptions.py`

**New class `TooManyMerges`:**
- Inherits `RuntimeError` (NOT `_AppError` — `xlsx_read/` is the
  closed-API library; the shim is the cross-5 envelope owner,
  matches the `OverlappingMerges` precedent at
  [`_exceptions.py:26`](../../skills/xlsx/scripts/xlsx_read/_exceptions.py#L26)).
- Docstring: "Raised when a worksheet's `<mergeCell>` count exceeds
  `_MAX_MERGES`. Caller maps to exit 2 (Sec-MED-3 memory-exhaustion
  mitigation, xlsx-8a-02). Practical real-world maximum is ~8K
  merges; 100K cap gives 10× headroom while bounding RAM for the
  resulting `MergeMap` dict at ~6 MiB."

#### File: `skills/xlsx/scripts/xlsx_read/_merges.py`

**New module-level constant:**
- `_MAX_MERGES: int = 100_000` — placed near the top of the
  module with a one-line docstring referencing TASK §7.3 D2.

**New import:**
- `from ._exceptions import OverlappingMerges, TooManyMerges`
  (extends the existing `OverlappingMerges` import).

**Function `parse_merges(ws)` (lines ~36-41):**
- Inside the `for r in ws.merged_cells.ranges:` loop, after
  `out[(r.min_row, r.min_col)] = (r.max_row, r.max_col)`, add a
  guard:
  ```python
  if len(out) > _MAX_MERGES:
      raise TooManyMerges(
          f"Worksheet {getattr(ws, 'title', '?')!r}: more than "
          f"{_MAX_MERGES} merge ranges; aborting to protect memory."
      )
  ```
- The check fires on the 100_001st iteration (per D-A14
  cap+1 semantics).

#### File: `skills/xlsx/scripts/xlsx_read/__init__.py`

**Public API export:**
- Add `from ._exceptions import TooManyMerges` to the existing
  import block.
- Add `"TooManyMerges"` to the module-level `__all__` list (next
  to `"OverlappingMerges"`).

#### File: `skills/xlsx/scripts/xlsx2csv2json/cli.py`

**Function `_run_with_envelope`:**
- Import `TooManyMerges` from `xlsx_read` (extends the existing
  `from xlsx_read import (...)` block).
- Add a new `except TooManyMerges as exc:` branch (between
  `OverlappingMerges` and `_AppError`):
  ```python
  except TooManyMerges as exc:
      return _errors.report_error(
          str(exc),
          code=2,
          error_type="TooManyMerges",
          details={},
          json_mode=json_mode,
          stream=sys.stderr,
      )
  ```

### Component Integration

`TooManyMerges` propagates from `parse_merges` → `read_table` →
`iter_table_payloads` (in the shim) → `_run_with_envelope`. No
intermediate handler swallows it.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01:** `test_parse_merges_at_100000_passes`
   - Input: a `Mock` worksheet whose `merged_cells.ranges`
     attribute yields exactly 100_000 mock-range objects (each
     with `.min_row=1, .max_row=1, .min_col=N, .max_col=N` for
     N in `range(1, 100_001)`).
   - Expected: `parse_merges(mock_ws)` returns a full
     `MergeMap` dict of 100_000 entries; no raise.

2. **TC-E2E-02:** `test_parse_merges_at_100001_raises`
   - Input: same mock construction with 100_001 ranges.
   - Expected: `TooManyMerges` raised on the 100_001st insertion;
     no partial `MergeMap` returned.

3. **TC-E2E-03:** `test_too_many_merges_routes_through_envelope`
   - Hosted in `xlsx2csv2json/tests/test_cross_cutting.py`.
   - Input: subprocess `xlsx2csv.py book-with-many-merges.xlsx
     --json-errors` (fixture authored with 100_001 merges via a
     hand-crafted OOXML synthesiser).
   - Expected: exit 2; stdout JSON envelope
     `{"v":1,"error":"...","code":2,"error_type":"TooManyMerges","details":{}}`.

### Unit Tests
Covered by TC-E2E-01 and TC-E2E-02 (the cap is a single-statement
guard; unit-level coverage is identical).

### Regression Tests
- All existing tests in `skills/xlsx/scripts/xlsx_read/tests/test_merges.py`
  remain green (positive merge resolution, `apply_merge_policy`,
  `_overlapping_merges_check`, etc.).
- 12-line cross-skill `diff -q` gate from ARCH §9.4 silent.

## Acceptance Criteria
- [ ] `grep -n "_MAX_MERGES" skills/xlsx/scripts/xlsx_read/_merges.py`
  returns ≥ 2 hits.
- [ ] `grep -n "TooManyMerges" skills/xlsx/scripts/xlsx_read/__init__.py`
  returns ≥ 1 hit (`__all__` export).
- [ ] `from xlsx_read import TooManyMerges` works at the Python
  level.
- [ ] `cli._run_with_envelope` carries a `TooManyMerges` branch
  with `code=2`.
- [ ] All 3 TC-E2E tests green.
- [ ] `test_merges.py` regression suite 100% green.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx`
  exit 0.

## Stub-First Pass Breakdown

### Pass 1 — Stub + Red E2E
1. Add `TooManyMerges` class to `_exceptions.py`.
2. Add `_MAX_MERGES = 100_000` constant + import to `_merges.py`
   (no guard yet).
3. Add `TooManyMerges` to `__init__.py` `__all__` + import.
4. Add `_run_with_envelope` branch to `cli.py` (target-class is
   imported but no raise-site exists yet).
5. Write all 3 E2E tests — TC-E2E-01 (positive) passes already;
   TC-E2E-02 and TC-E2E-03 FAIL Red.

### Pass 2 — Logic + Green E2E
1. Insert the `if len(out) > _MAX_MERGES: raise ...` guard inside
   the `parse_merges` loop.
2. Re-run TC-E2E-02 and TC-E2E-03 — Green.
3. Re-run regression suite — all green.

## Notes
- `TooManyMerges` inherits `RuntimeError` (NOT `_AppError`) because
  it lives in `xlsx_read/`, which is the closed-API library. The
  cross-5 envelope is the shim's responsibility — `cli.py` does
  the `except TooManyMerges → code=2` mapping. This mirrors the
  `OverlappingMerges` precedent.
- The fixture for TC-E2E-03 (workbook with 100_001 merges) must
  be **synthesised at test-time** (not committed). The fixture
  builder uses `openpyxl.Workbook()` + a loop adding merges, then
  saves to a temp file. Honest scope: synthesising 100_001 merges
  takes ~5-10 seconds; the test is tagged `@unittest.skip("slow")`
  by default and run only under `RUN_SLOW_TESTS=1`.
- Effort: S (≤ 2 hours). Diff size: ~30 LOC across 4 files.

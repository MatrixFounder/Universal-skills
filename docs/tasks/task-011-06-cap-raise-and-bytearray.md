# Task 011.06 — [R8] `_GAP_DETECT_MAX_CELLS` raise + `bytearray` matrices

## Use Case Connection
- UC-06: Large-table CSV emit (3M cells, `xlsx-8a-06`)

## Task Goal
Raise `_GAP_DETECT_MAX_CELLS` from `1_000_000` to `50_000_000` and
switch the `_gap_detect` occupancy matrix + `_build_claimed_mask`
mask from `list[list[bool]]` (8 bytes/ref + list overhead) to a
flat `bytearray(n_rows * n_cols)` (1 byte/ref) — 8× memory
reduction with Big-O unchanged. Add an early-exit
`if not claimed: return None` in `_build_claimed_mask` so the
common case (Tier-1 + Tier-2 empty) skips the allocation entirely.

This closes **PERF-HIGH-1** from
[`docs/KNOWN_ISSUES.md`](../KNOWN_ISSUES.md) and unblocks the
user-documented workload of 100K rows × 20-30 cols ≈ 2-3M cells
for both CSV and JSON outputs.

**Fixture-timing prerequisite for 011-07 and 011-08** — those
sub-tasks' 3M-cell synthesised tests cannot complete under the v1
1M-cell cap during fixture setup; this task MUST land first.

This task **re-opens a 3rd file in the xlsx-10.A frozen surface**
(`_tables.py`, joining `_merges.py` + `_exceptions.py` +
`__init__.py` from earlier beads). Per §15.10.5 m5-fix, the
carve-out is bounded by the rule "each re-opened file ships with
a documented `KNOWN_ISSUES.md` entry or §15.x decision record" —
this task deletes the `PERF-HIGH-1` entry as its rationale anchor.

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_read/_tables.py`

**Constant raise (line ~313):**
- Change `_GAP_DETECT_MAX_CELLS: int = 1_000_000`
  → `_GAP_DETECT_MAX_CELLS: int = 50_000_000` (D8 in TASK §7.3 /
  D-A15 in ARCH §15.10.3).
- Update the docstring on the line above to reflect the new value
  and the 50M = 1/343 of XFD1048576 attack envelope ratio.

**Function `_gap_detect` (lines ~307-345):**
- Replace `occupancy: list[list[bool]] = [[False] * n_cols for _ in
  range(n_rows)]` with `occupancy = bytearray(n_rows * n_cols)`
  (initialised to all-zero by the constructor — equivalent to
  all-False).
- Update every read `occupancy[r][c]` → `occupancy[r * n_cols + c]`.
- Update every write `occupancy[r][c] = True` →
  `occupancy[r * n_cols + c] = 1`.

**Function `_build_claimed_mask` (lines ~406-416):**
- **Early-exit guard at top of function:**
  ```python
  if not claimed:
      return None
  ```
- Replace `mask: list[list[bool]] = [[False] * n_cols for _ in
  range(n_rows)]` with `mask = bytearray(n_rows * n_cols)`.
- Update writes `mask[r][c] = True` → `mask[r * n_cols + c] = 1`.
- Return type signature update:
  `def _build_claimed_mask(...) -> bytearray | None:` (was
  `-> list[list[bool]]`).

**Functions `_split_on_gap` / `_tight_bbox`** (callers of
`_gap_detect` and `_build_claimed_mask`):
- Update buffer indexing — wherever they read
  `occupancy[r][c]` or `mask[r][c]`, switch to flat-buffer
  `[r * n_cols + c]` indexing.
- Where the consumer of `mask` is `_gap_detect`-internal, add a
  guard:
  ```python
  if claimed_mask is None or not claimed_mask[r * n_cols + c]:
      # cell is unclaimed; proceed with occupancy scan
  ```
  (Per arch-review m4 fix / D-A16 consumer-guard contract.)

**Function `_whole_sheet_region`** (line ~580):
- The `if cells_scanned > _GAP_DETECT_MAX_CELLS:` branch reads
  the same lifted constant — no body change needed, but the
  silent-truncation threshold for `--tables whole` now sits at
  50M alongside `_gap_detect`. Update the inline comment on that
  line to reflect the 50× raise.

#### File: `docs/KNOWN_ISSUES.md`

**Delete the entire `PERF-HIGH-1` section** (lines ~17-61). The
fix has landed; the entry is retired per the file's lifecycle
rule ("When a fix lands, the entry is moved to a section
'Resolved' with a commit-hash pointer, or simply deleted with the
fix commit referenced from the related task/backlog row").

The commit message for this bead MUST reference the
`PERF-HIGH-1` text in the body so the rationale persists in `git
log` for posterity.

### Component Integration

The bytearray flip is internal to `_tables.py`. All public
`xlsx_read/` API surface (`detect_tables`, `read_table`, etc.) is
unchanged. Consumers (`xlsx2csv2json/dispatch.py:iter_table_payloads`
→ `read_table` → `_tables`) see no signature change.

The `_build_claimed_mask` may now return `None`. The only
consumer (`_gap_detect`) handles `None` via the consumer-guard
contract above.

## Test Cases

### End-to-end Tests

Hosted in `xlsx_read/tests/test_tables.py`.

1. **TC-E2E-01:** `test_R8_gap_detect_at_3M_cells_succeeds`
   - Fixture: synthetic 100K × 30 fixture (via `openpyxl.Workbook()`
     + programmatic cell fill).
   - Invocation: `WorkbookReader(...).detect_tables(sheet,
     mode="auto")`.
   - Expected: returns ≥ 1 region; no raise; `_gap_detect`'s
     occupancy is a `bytearray` (verify via
     `tracemalloc.get_traced_memory()` peak under 100 MB).

2. **TC-E2E-02:** `test_R8_gap_detect_at_50M_plus_one_raises`
   - Fixture: hand-crafted `<dimension ref="A1:..."/>` declaring a
     bbox of > 50M cells with one corner cell containing data.
   - Expected: `_gap_detect` raises (continues current cap behaviour
     at the new 50M threshold).

3. **TC-E2E-03:** `test_R8_bytearray_correctness_vs_listoflist`
   - Fixture: 100 × 100 synthetic sheet with a known
     gap-detect-relevant pattern.
   - Approach: parametric test that runs the original
     `list[list[bool]]` reference implementation (held inline in
     the test as `_v1_reference_gap_detect`) and the new bytearray
     implementation, asserts the returned region lists are
     element-wise equal.
   - The reference impl is committed alongside the test for
     ongoing same-output gating; it can be deleted in a future
     cleanup if confidence holds.

### Unit Tests

1. **TC-UNIT-01:** `test_R8_build_claimed_mask_empty_returns_None`
   - Input: empty `claimed` set.
   - Expected: `_build_claimed_mask` returns `None` (early-exit
     guard).

2. **TC-UNIT-02:** `test_R8_build_claimed_mask_non_empty_returns_bytearray`
   - Input: claimed set with a few entries.
   - Expected: returns a `bytearray` of length `n_rows * n_cols`
     with 1-bits at the claimed positions.

### Regression Tests
- All existing tests in `xlsx_read/tests/test_tables.py` 100%
  green (the bytearray flip is internal; library-level behaviour
  is preserved).
- All existing tests in `xlsx2csv2json/tests/` 100% green (the
  dispatch path consumes `TableData`, not the matrix).
- 12-line cross-skill `diff -q` gate from ARCH §9.4 silent.

## Acceptance Criteria
- [ ] `grep -E "_GAP_DETECT_MAX_CELLS\s*=\s*50_000_000"
  skills/xlsx/scripts/xlsx_read/_tables.py` returns ≥ 1 hit.
- [ ] `grep -n "bytearray(" skills/xlsx/scripts/xlsx_read/_tables.py`
  returns ≥ 2 hits (`_gap_detect` + `_build_claimed_mask`).
- [ ] `grep -n "if not claimed:" skills/xlsx/scripts/xlsx_read/_tables.py`
  returns ≥ 1 hit (early-exit guard).
- [ ] `grep -n "PERF-HIGH-1" docs/KNOWN_ISSUES.md` returns **0**
  hits (entry deleted).
- [ ] All 3 E2E + 2 unit tests green.
- [ ] `xlsx_read/tests/test_tables.py` regression 100% green.
- [ ] `xlsx2csv2json/tests/` regression 100% green.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] `validate_skill.py skills/xlsx` exit 0.
- [ ] CSV path on 100K × 30 fixture writes 100 001 lines
  (header + data).

## Stub-First Pass Breakdown

### Pass 1 — Stub + Red E2E
1. Lift `_GAP_DETECT_MAX_CELLS` to `50_000_000` (1-line change).
   Matrix representation **unchanged** at this stage (still
   `list[list[bool]]`).
2. Write all 3 E2E + 2 unit tests.
   - TC-E2E-01 may **still FAIL** Red on memory budget — the v1
     matrix at 3M cells transiently allocates ~24 MB
     `list[list[bool]]`, which may exceed the 100 MB budget when
     stacked with openpyxl working set. Confirm by running the
     test; the budget assertion is the Red gate.
   - TC-E2E-02 passes at the new cap.
   - TC-E2E-03 passes (reference impl == reference impl).
   - TC-UNIT-01 FAILS Red (no early-exit yet — returns
     `list[list[bool]]`).
   - TC-UNIT-02 passes for non-empty `claimed`.

### Pass 2 — Logic + Green E2E
1. Replace `list[list[bool]]` allocations with `bytearray` flat
   buffers in `_gap_detect`, `_build_claimed_mask`, and update
   indexing in `_split_on_gap` / `_tight_bbox`.
2. Add the `if not claimed: return None` early-exit guard.
3. Update the `_gap_detect` consumer-guard to handle `None`.
4. Re-run all tests — Green (memory budget now under 5 MB on the
   `_gap_detect` matrix alone for 3M cells; well under the 100 MB
   budget).
5. Delete the `PERF-HIGH-1` section from `docs/KNOWN_ISSUES.md`.

## Notes
- Cap value 50M is policy (D8 / D-A15). Raising further requires
  a code-change PR with rationale (per Q-15-1 policy stance).
- The `tracemalloc` budget assertion in TC-E2E-01 sits at 100 MB
  to account for openpyxl's transient working set; the
  `_gap_detect` matrix itself is bounded at 50 MB (50M × 1 byte)
  but real-workload measurements show ~5-10 MB for 3M cells
  (allocator may pre-size).
- The reference impl in TC-E2E-03 is the SINGLE point of
  byte-level regression detection — keep it; do not refactor.
- Effort: M (~4 hours). Diff size: ~40 LOC across 1 file +
  ~150 LOC test additions + `KNOWN_ISSUES.md` deletion.

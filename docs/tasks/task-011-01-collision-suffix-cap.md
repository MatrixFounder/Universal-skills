# Task 011.01 — [R1] Bounded collision-suffix in `_emit_multi_region`

## Use Case Connection
- UC-01: Bounded collision-suffix in multi-region CSV emit (`xlsx-8a-01`)

## Task Goal
Add a hard cap on the per-region filename collision-suffix loop in
[`emit_csv._emit_multi_region`](../../skills/xlsx/scripts/xlsx2csv2json/emit_csv.py)
to close the Sec-HIGH-3 DoS vector raised by `/vdd-multi-3` 2026-05-13.
A crafted workbook with > 1000 same-named regions (e.g. many
ListObjects named "Table" colliding with `Table-N` gap-detect
fallbacks) currently forces an unbounded O(N²) `Path.resolve()` +
`is_relative_to` loop. The cap fires fail-loud before wall-clock
dominates, via a new typed exception that routes through the
existing cross-5 envelope contract (exit 2).

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2csv2json/exceptions.py`

**New class `CollisionSuffixExhausted`:**
- Inherits `_AppError`
- Class attribute `CODE = 2`
- Docstring: "Per-region filename collision-suffix loop in
  `_emit_multi_region` attempted more than `_MAX_COLLISION_SUFFIX`
  variants without finding a unique path. Triggered by crafted
  workbooks with many same-named regions (Sec-HIGH-3 DoS
  mitigation, xlsx-8a-01)."
- Add `"CollisionSuffixExhausted"` to module-level `__all__`.

#### File: `skills/xlsx/scripts/xlsx2csv2json/emit_csv.py`

**New module-level constant:**
- `_MAX_COLLISION_SUFFIX: int = 1000` — placed near the top of the
  file with a one-line docstring referencing TASK §7.3 D1 and
  ARCH §15.3 D-A14.

**Function `_emit_multi_region` (lines ~162-172):**
- Inside the `while target in written:` loop, after `suffix += 1`,
  add a guard:
  ```python
  if suffix > _MAX_COLLISION_SUFFIX:
      raise CollisionSuffixExhausted(
          f"Region {region_name!r} on sheet {sheet_name!r}: "
          f"{_MAX_COLLISION_SUFFIX} collision suffixes exhausted; "
          f"refusing to keep iterating."
      )
  ```
- The check fires when `suffix` exceeds 1000 (i.e. on the 1001st
  attempted variant per D-A14 cap+1 semantics).

#### File: `skills/xlsx/scripts/xlsx2csv2json/exceptions.py` import

`emit_csv.py` adds `from .exceptions import CollisionSuffixExhausted`
to the existing exception import block at the top of the module.

### Component Integration

`cli._run_with_envelope` already has a generic `_AppError` branch
that maps the new exception to exit 2 with the cross-5 envelope —
no change needed there. The basename-only `details` extraction
also already exists; the new exception's message uses only
sheet/region names (already validated by
`_validate_sheet_path_components`).

## Test Cases

### End-to-end Tests

1. **TC-E2E-01:** `test_collision_suffix_caps_at_1000`
   - Input: synthetic 1001-region payload list, all colliding on
     the same `(sheet, region_name)` tuple after dispatch
     (simulated by calling `_emit_multi_region` directly with a
     hand-crafted payload list of 1001 entries sharing the same
     name).
   - Expected: `CollisionSuffixExhausted` raised; exit 2 envelope
     under `--json-errors`; `details = {"sheet": ..., "region": ...}`;
     no absolute paths leaked.

2. **TC-E2E-02:** `test_collision_suffix_999_succeeds`
   - Input: 999 colliding payloads (one below the cap).
   - Expected: all 999 files written successfully (suffixes
     `__2` through `__1000`); no raise.

### Unit Tests
Covered by the E2E tests above (the cap is a single-statement
guard; unit-level coverage is identical to E2E coverage).

### Regression Tests
- All existing tests in `skills/xlsx/scripts/xlsx2csv2json/tests/`
  remain green.
- Specifically, `test_M2_colliding_region_names_get_numeric_suffix`
  (from the vdd-multi-2 review) MUST continue to pass — it asserts
  the suffix logic works at the 2-region scale.
- 12-line cross-skill `diff -q` gate from ARCH §9.4 silent.

## Acceptance Criteria
- [ ] `grep -n "_MAX_COLLISION_SUFFIX" skills/xlsx/scripts/xlsx2csv2json/emit_csv.py`
  returns ≥ 2 hits (declaration + guard).
- [ ] `grep -n "CollisionSuffixExhausted" skills/xlsx/scripts/xlsx2csv2json/exceptions.py`
  returns ≥ 1 hit; class extends `_AppError`; `CODE = 2`.
- [ ] `test_collision_suffix_caps_at_1000` green.
- [ ] `test_collision_suffix_999_succeeds` green.
- [ ] `test_M2_colliding_region_names_get_numeric_suffix` green.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx`
  exit 0.

## Stub-First Pass Breakdown

### Pass 1 — Stub + Red E2E
1. Add `CollisionSuffixExhausted` class shell to `exceptions.py`
   (full docstring, `CODE = 2`, `__all__` export).
2. Add `_MAX_COLLISION_SUFFIX = 1000` constant to `emit_csv.py`
   (no guard yet).
3. Write `test_collision_suffix_caps_at_1000` — it FAILS (Red)
   because no guard exists.
4. Write `test_collision_suffix_999_succeeds` — it passes already
   (no change to existing behaviour at sub-cap counts).

### Pass 2 — Logic + Green E2E
1. Insert the `if suffix > _MAX_COLLISION_SUFFIX: raise ...` guard
   inside the `while target in written:` loop.
2. Re-run `test_collision_suffix_caps_at_1000` — Green.
3. Re-run regression suite — all green.

## Notes
- Cap value 1000 is policy (D8 in TASK §7.3 / D-A14 in ARCH §15.3).
  Raising requires a code-change PR with rationale, not env-var
  / CLI flag.
- `details` envelope payload `{"sheet": <name>, "region": <name>}`
  is safe because both names have already passed
  `_validate_sheet_path_components` (per dispatch.py D-A8).
- Effort: S (≤ 1 hour). Diff size: ~20 LOC across 2 files.

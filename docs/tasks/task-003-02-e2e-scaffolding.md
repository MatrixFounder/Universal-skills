# Task 003.02: E2E + battery driver scaffolding

## Use Case Connection
- **I9.2** (`test_battery.py` driver shape).
- **I9.3** (canary saboteur slot — empty trap framework).

## Task Goal
Add a new `xlsx_check_rules` block to `tests/test_e2e.sh`, create the `tests/test_battery.py` driver shell, and create the empty `tests/canary_check.sh` saboteur framework. **All E2E + battery assertions should fail uniformly** (because 003.01 stubs raise `NotImplementedError`); the failure mode must be parseable so that as 003.05–003.16 ship, fixtures turn green incrementally.

## Changes Description

### New Files

- `skills/xlsx/scripts/tests/test_battery.py` — Python `unittest` driver. Walks `tests/golden/manifests/*.yaml`, calls `tests/golden/inputs/_generate.py` (added in 003.03) to regenerate fixtures, runs `xlsx_check_rules.py` with manifest-supplied flags, asserts `(exit_code, summary key subset, findings rule_id set ⊇ required, ∩ forbidden = ∅)`. Skeleton in this task: the driver enumerates manifests, runs the CLI, and emits **xfail** (`unittest.expectedFailure`) per fixture — this is intentional during Stub-First red state. Successive tasks remove the `expectedFailure` decorator from fixtures they own.

- `skills/xlsx/scripts/tests/canary_check.sh` — saboteur runner. Skeleton with one TODO per saboteur (10 slots), each guarded by a `trap` to revert. Each slot is a no-op shell function in this task; functions are filled in 003.16.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

- Append new block under existing `xlsx_add_comment` block:

```bash
echo "=== xlsx_check_rules ==="
# Block expanded incrementally by tasks 003.05+; in 003.02 contains the
# happy-path smoke only:
"$PY" "$SCRIPTS/xlsx_check_rules.py" --help > /dev/null && echo "OK: --help"
```

- Subsequent task files (003.05+) extend the block by appending one or more fixture invocations per F-region.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01:** `bash skills/xlsx/scripts/tests/test_e2e.sh` runs the new `xlsx_check_rules` block; the only line that runs is `--help`. Exits 0 (smoke passes; no fixtures yet).
2. **TC-E2E-02:** `bash skills/xlsx/scripts/tests/canary_check.sh` exits 0 (every saboteur slot is a no-op).

### Unit Tests
1. **TC-UNIT-01:** `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest tests.test_battery` runs and reports **xfail** for every manifest currently registered (zero, because 003.04 has not run yet) — exits 0.
2. **TC-UNIT-02:** `test_battery.py` module imports without errors; `BatteryTestCase` subclass exists with `test_<manifest_name>` placeholder method shape.

### Regression Tests
- xlsx-6 unit + E2E suites pass unchanged.

## Acceptance Criteria
- [ ] `tests/test_battery.py` skeleton created.
- [ ] `tests/canary_check.sh` skeleton created (executable bit set: `chmod +x`).
- [ ] `tests/test_e2e.sh` has the new `xlsx_check_rules` block.
- [ ] All TC-E2E / TC-UNIT pass.
- [ ] xlsx-6 tests still green (regression gate).

## Notes
- The driver `test_battery.py` reads manifests via PyYAML or ruamel.yaml-safe (whichever lands first; this driver does not need YAML hardening — it processes our own trusted manifests).
- The driver intentionally sets `expectedFailure` on per-manifest tests so red-state during Stub-First does not pollute CI signal.
- Saboteur slot naming convention: `_saboteur_NN_short_description()` for slots 01–10. Each takes a single optional arg (the fixture name to verify it broke) and is invoked by a top-level `for s in 01 02 ... 10; do ...; done` loop with `trap` cleanup.

# Task 003.03: Unit-test scaffolding + fixture-generator skeleton

## Use Case Connection
- **I9.1** (`tests/golden/inputs/_generate.py` — fixture generator skeleton).
- **All TASK Use Cases** (unit-test module structure).

## Task Goal
Create the `tests/test_xlsx_check_rules.py` Python `unittest` module structure (one `TestCase` class per F-region), and create the declarative-manifest fixture generator skeleton at `tests/golden/inputs/_generate.py`. The generator is **declarative-only at this stage**: it reads YAML manifests in `tests/golden/manifests/*.yaml` (none exist yet — added in 003.04) and writes corresponding `.xlsx` + `.json`/`.yaml` outputs; in this task it implements the manifest-walk plumbing but no actual workbook generation logic.

## Changes Description

### New Files

- `skills/xlsx/scripts/tests/test_xlsx_check_rules.py` — Python `unittest` module. Eleven `TestCase` classes:
  - `TestConstants` (003.05)
  - `TestExceptions` (003.05)
  - `TestAstNodes` (003.06)
  - `TestCellTypes` (003.07) — including `TestHonestScopeOpenpyxlErrorSubset` (D4)
  - `TestScopeResolver` (003.08) — including `TestHonestScopeMultiRowHeaders` (R13.g)
  - `TestRulesLoader` (003.09)
  - `TestDslParser` (003.10) — including `TestHonestScopeClosedAst`
  - `TestEvaluator` (003.11)
  - `TestAggregates` (003.12)
  - `TestOutput` (003.13) — including `TestM2EnvelopeAlwaysThreeKeys`
  - `TestCli` (003.14) — including `TestPartialFlushMainThread` (M-2 architect lock)
  - `TestRemarksWriter` (003.15) — including `TestM1DualStream` (M-1 architect lock)

  In this task: each class has one `test_smoke` method that asserts `import xlsx_check_rules.<module>` works (already passes thanks to 003.01 stubs). All other methods have `@unittest.skip("task-003-NN — not implemented")` decorators; later tasks remove the skip when they ship the module.

- `skills/xlsx/scripts/tests/golden/inputs/_generate.py` — Python script. CLI:
  - `_generate.py --all` — regenerate every fixture from manifests.
  - `_generate.py --check` — re-hash each manifest, regenerate stale outputs only (Q5=hybrid optimisation).
  - `_generate.py --regenerate-perf-fixture` — regenerate `huge-100k-rows.xlsx` (deterministic seed `random.seed(42)`).
  - In this task: implements the manifest-walk plumbing only; one TODO per fixture-shape (clean-pass / timesheet / hostile-yaml / ...) which 003.04 fills in.

- `skills/xlsx/scripts/tests/golden/inputs/.gitignore` — content:
  ```
  *
  !.gitignore
  !huge-100k-rows.xlsx
  !huge-100k-rows.rules.json
  ```
  Per Q5 hybrid: small fixtures regenerated each test run (excluded); the 100K-row perf fixture is committed (allow-listed).

- `skills/xlsx/scripts/tests/golden/manifests/.gitkeep` — placeholder so directory exists in git.

- `skills/xlsx/scripts/tests/golden/README.md` — provenance + "agent-output-only — DO NOT open in Excel" warning (per R14.e). Body fleshed out in 003.17.

## Test Cases

### Unit Tests
1. **TC-UNIT-01:** `python -m unittest tests.test_xlsx_check_rules` runs; reports `OK (skipped=N)` where N matches the number of `@unittest.skip` decorators currently in place. 11 `test_smoke` methods pass.

2. **TC-UNIT-02:** `_generate.py --check` exits 0 (no manifests to process yet); `_generate.py --all` exits 0 (no manifests).

### Regression Tests
- xlsx-6 unit + E2E suites pass unchanged.
- `test_battery.py` (003.02) still reports xfail for all (zero) manifests.

## Acceptance Criteria
- [ ] `tests/test_xlsx_check_rules.py` with 11 `TestCase` classes + 11 `test_smoke` methods.
- [ ] `_generate.py` skeleton with three CLI modes (`--all`, `--check`, `--regenerate-perf-fixture`).
- [ ] `tests/golden/inputs/.gitignore` written.
- [ ] `tests/golden/manifests/` directory exists with `.gitkeep`.
- [ ] `tests/golden/README.md` placeholder.
- [ ] `_generate.py --check` and `_generate.py --all` exit 0.
- [ ] xlsx-6 regression gate green.

## Notes
- `test_smoke` methods must NOT be `@unittest.skip`'ed — they run and pass (importing the stub module is the smoke). This gives the test suite an immediately-positive signal even during the all-NotImplementedError red phase.
- The fixture generator output paths follow `tests/golden/inputs/<fixture-name>.xlsx` + `tests/golden/inputs/<fixture-name>.rules.{json,yaml}` + `tests/golden/manifests/<fixture-name>.yaml`. Names match the SPEC §13 fixture index.
- `_generate.py` uses `openpyxl.Workbook` + `openpyxl.styles` for normal fixtures; `openpyxl.Workbook(write_only=True)` for `huge-100k-rows.xlsx`. No `lxml` direct emission needed at fixture level (we are testing xlsx-7's READ path).

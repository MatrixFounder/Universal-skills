# Task 003.04a: Manifest schema + generator core + 10 happy-path fixtures

> **Split origin:** plan-reviewer M-1 (`docs/reviews/plan-003-review.md`) split the original 003.04 (42-manifest mega-task) into 003.04a (this — schema + generator core + 10 happy-path manifests) and 003.04b (adversarial / cross-sheet / output manifests). 003.04b can run in parallel to 003.05.

## Use Case Connection
- **I9.1** (`_generate.py` — small-fixture path; schema + plumbing).
- **R12.a partial** (manifest schema + first 10 fixtures — happy path only).

## Task Goal
Define the manifest schema. Implement small-fixture generation in `_generate.py` (`--all`, `--check`, `--regenerate-perf-fixture` stub). Author the **first 10 manifests** — happy-path / layout-variance fixtures only:
- #1 clean-pass
- #2 timesheet-violations
- #3 header-row-3
- #4 excel-table-data
- #5 multi-row-headers
- #6 transposed-layout
- #7 dup-header
- #8 missing-header
- #9 apostrophe-sheet
- #10b modern-error-text (D4 lock)

The other 32 fixtures (adversarial / cross-sheet / output / honest-scope) are owned by 003.04b. The perf fixture (#31 `huge-100k-rows.xlsx`) is deferred to 003.16a. Manifests use a declarative schema:

```yaml
# tests/golden/manifests/clean-pass.yaml
id: 1
name: clean-pass
sheet:
  name: Sheet1
  cells:
    A1: { type: header, value: "Hours" }
    A2: { type: number, value: 8 }
    A3: { type: number, value: 7 }
rules: |
  {
    "version": 1,
    "rules": [
      {"id": "hours-positive", "scope": "col:Hours",
       "check": "value > 0", "severity": "error"}
    ]
  }
expected:
  exit_code: 0
  summary:
    errors: 0
    warnings: 0
  required_rule_ids: []
  forbidden_rule_ids: []
```

## Changes Description

### New Files (10 manifests for this task)

**Layout & schema variance** (9 of 9): `clean-pass.yaml`, `timesheet-violations.yaml`, `header-row-3.yaml`, `excel-table-data.yaml`, `multi-row-headers.yaml`, `transposed-layout.yaml`, `dup-header.yaml`, `missing-header.yaml`, `apostrophe-sheet.yaml`.

**Type & error edges (D4 anchor only)** (1 of 8 + #10b): `modern-error-text.yaml` (#10b — `#SPILL!` stored as text → no auto-emit per D4).

The remaining 32 fixtures land in 003.04b.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/tests/golden/inputs/_generate.py`

- Implement small-fixture generation per manifest schema. Generator produces:
  - `tests/golden/inputs/<id>.xlsx`
  - `tests/golden/inputs/<id>.rules.{json,yaml}` (extension follows manifest's `rules_format` field; default `json`)
  - `tests/golden/inputs/<id>.expected.json` (the expected envelope subset for `test_battery.py` to compare against)
- The 100K-row perf fixture path (`--regenerate-perf-fixture`) is left as a `raise NotImplementedError("task-003-16")`.

#### File: `skills/xlsx/scripts/tests/golden/inputs/.gitignore`

- No changes (already excludes everything except `huge-100k-rows.*`).

#### File: `skills/xlsx/scripts/tests/golden/README.md`

- Flesh out the provenance section: each fixture lists its source manifest, its purpose, the SPEC §-anchor it locks. "DO NOT open in Excel" + reasoning.

## Test Cases

### Unit Tests
1. **TC-UNIT-01:** `_generate.py --all` exits 0; produces 10 `.xlsx` + 10 `.rules.{json,yaml}` + 10 `.expected.json` triples (the 10 manifests authored in this task).
2. **TC-UNIT-02:** `_generate.py --check` fast-path (rebuilds nothing if all hashes match); exits 0.
3. **TC-UNIT-03:** Each manifest validates against the manifest schema (id, name, sheet/rules/expected fields present and well-formed).

### End-to-end Tests
1. **TC-E2E-01:** `bash tests/test_e2e.sh` still smoke-only (xlsx-7 happy path is `--help`); fixtures exist but are NOT yet asserted because no F-region is implemented.
2. **TC-E2E-02:** `python -m unittest tests.test_battery` reports xfail for all 42 fixtures (intentional Stub-First red — Phase 1 final state).

### Regression Tests
- xlsx-6 tests still pass.

## Acceptance Criteria
- [ ] 10 manifests in `tests/golden/manifests/*.yaml` (9 layout-variance + 1 D4 anchor).
- [ ] `_generate.py --all` produces 10 fixture-triple files.
- [ ] `_generate.py --check` short-circuits when nothing has changed.
- [ ] Manifest schema documented in `tests/golden/README.md`.
- [ ] xlsx-6 tests still green.
- [ ] 003.04b can begin (this task delivers the schema and generator that 003.04b consumes).

## Notes
- The `huge-100k-rows.xlsx` fixture is intentionally **not generated in this task** — it's expensive (8–15 s) and depends on the perf-fixture path that 003.16 wires up. The manifest exists but `_generate.py --regenerate-perf-fixture` is a no-op stub.
- Use openpyxl `Workbook()` + `Worksheet.cell(row, col, value)` for straightforward fixtures. For `errors-as-values.xlsx`, set `cell.value = "#REF!"` and `cell.data_type = 'e'` (openpyxl exposes `data_type` for direct manipulation). For `formulas-no-cache.xlsx`, use a fresh openpyxl workbook (formulas without cached values is the default state).
- For `apostrophe-sheet.xlsx`: sheet name is `Bob's Sheet` (single apostrophe in the sheet name). The rule file references `'Bob''s Sheet'!A1` (apostrophe doubled per Excel/ECMA-376).
- For YAML hostile fixtures (#23–#26): write the rule file as raw bytes via Python `open(..., 'wb').write(b'…')` to avoid accidental escaping by the generator.

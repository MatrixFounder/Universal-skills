# Task 003.04b: Adversarial / cross-sheet / output / honest-scope manifests (32 fixtures)

> **Split origin:** plan-reviewer M-1 split the original 003.04 mega-task. 003.04a delivered the schema, generator core, and 10 happy-path fixtures (#1–#9, #10b). This task delivers the remaining 32 fixtures. **003.04b can run in parallel to 003.05–003.07** because none of the implementation tasks depend on the adversarial fixtures until 003.09 (rules-loader; #23–#28) and later.

## Use Case Connection
- **I9.1** (`_generate.py` — extends generator with raw-bytes hostile-YAML path).
- **I9.4** (R13.l honest-scope locks — manifest slots; tests land in 003.17).
- **R12.a** (≥ 21 xlsx-7 fixtures complete — total 42 after this task).

## Task Goal
Author the remaining 32 fixture manifests + `.rules.{json,yaml}` + `.expected.json` triples. Add the **raw-bytes hostile-YAML write path** to `_generate.py` (used by #23–#28; bypasses YAML serialiser to ensure the hostile patterns reach `_load_yaml_hardened` unmodified). The perf fixture (#31 `huge-100k-rows.xlsx`) is still deferred to 003.16a.

## Changes Description

### New Files (32 manifests)

**Type & error edges** (8): `errors-as-values.yaml` (#10), `mixed-types-aggregate.yaml` (#11), `mixed-types-aggregate-strict.yaml` (#12), `merged-data-cells.yaml` (#13), `formulas-no-cache.yaml` (#14), `localized-dates-ru-text.yaml` (#15), `localized-dates-ru-text-flag.yaml` (#16), `whitespace-values.yaml` (#17).

**Cross-sheet & aggregates** (4): `multi-sheet-aggregates.yaml` (#18), `aggregate-cache.yaml` (#19 — 10K rows), `aggregate-cache-strict.yaml` (#19a), `divide-by-zero.yaml` (#20), `nan-aggregate.yaml` (#21). _(5 manifests covering 4 spec entries — #19/19a count separately.)_

**Adversarial / DoS** (10): `regex-dos.yaml` (#22), `billion-laughs.yaml` (#23), `yaml-string-with-ampersand.yaml` (#23a — negative regression), `yaml-custom-tag.yaml` (#24), `yaml11-bool-trap.yaml` (#25), `yaml-dup-keys.yaml` (#26), `deep-composite.yaml` (#27), `huge-rules.yaml` (#28), `format-string-injection.yaml` (#29), `unknown-builtin.yaml` (#30).

**Scale & perf — deferred** (#31 manifest skeleton only — fixture generation lives in 003.16a; flag-combo fixtures #32a/b/c are full): `huge-100k-rows.yaml` (#31, manifest only), `streaming-incompat-auto.yaml` (#32a), `streaming-incompat-append.yaml` (#32b), `streaming-replace-explicit.yaml` (#32c), `noisy-all-violate.yaml` (#33).

**Output mode** (6): `reviewed-roundtrip.yaml` (#34), `reviewed-rerun-suffix.yaml` (#35), `empty-require-data.yaml` (#36), `same-path-input-output.yaml` (#37), `encrypted-input.yaml` (#38), `full-pipeline-xlsx-6.yaml` (#39).

**M2 envelope contract** (2): `full-pipeline-partial-flush.yaml` (#39a), `full-pipeline-max-findings-zero.yaml` (#39b).

### Changes in Existing Files

#### File: `skills/xlsx/scripts/tests/golden/inputs/_generate.py`

- Extend with `_write_raw_bytes_yaml(path, raw_bytes)` helper for hostile fixtures (#23–#26). Bypasses any YAML library to keep adversarial patterns intact.
- Implement `_make_workbook_with_error_cells(...)` for #10 (sets `cell.value = "#REF!"; cell.data_type = 'e'` directly via openpyxl).
- Implement `_make_workbook_with_merged_cells(...)` for #5 and #13.
- Implement `_make_encrypted_workbook(...)` for #38 (uses `office_passwd.py --set-password` from xlsx-6's existing pipeline; READ-ONLY consumer of an existing tool — does NOT modify `office_passwd.py`).

#### File: `skills/xlsx/scripts/tests/golden/README.md`

- Extend per-fixture provenance table with the 32 new entries.

## Test Cases

### Unit Tests
1. **TC-UNIT-01:** `_generate.py --all` exits 0; produces 42 fixture triples total (10 from 003.04a + 32 from this task).
2. **TC-UNIT-02:** `_generate.py --check` short-circuits on second invocation.
3. **TC-UNIT-03:** Hostile-YAML fixtures (#23, #24, #25, #26) round-trip the raw bytes (no escaping by the generator). Verify by reading the file back and asserting the literal `&` / `*` / `!!python/object` / dup-key patterns are present.
4. **TC-UNIT-04:** `#23a yaml-string-with-ampersand` produces a YAML file with `description: 'see Q1 & Q2'` whose `&` is INSIDE a quoted scalar (the generator's literal-scalar escaper must NOT promote it to an anchor).

### Regression Tests
- xlsx-6 tests still green.
- `test_battery.py` xfail count = 42 (all manifests xfail until their owning F-region task ships).

## Acceptance Criteria
- [ ] 32 new manifests + corresponding rules/expected files.
- [ ] `_generate.py --all` produces 42 fixture triples (cumulative).
- [ ] Hostile-YAML raw-bytes write path implemented and verified.
- [ ] `tests/golden/README.md` provenance table covers all 42 entries.
- [ ] xlsx-6 tests still green.

## Notes
- For #38 (encrypted-input): re-use `skills/xlsx/scripts/office_passwd.py` (xlsx-6 cross-skill helper). The generator invokes it via subprocess on the ALREADY-generated plain workbook; `_generate.py` does NOT import or modify the helper.
- For #19 (aggregate-cache): 10K rows is a sweet spot — small enough to generate fast (< 1 s), large enough that cache replay timing is meaningful. Use `random.seed(19)` for determinism.
- Hostile-YAML patterns must be authored as raw bytes — even `repr`'ing the YAML body in Python and writing it can introduce escapes. The `_write_raw_bytes_yaml` helper takes `bytes`, not `str`, to make this explicit.
- The #29 fixture (`format-string-injection`) workbook contains a cell whose value is the literal string `${value}`; the rule's `message` field is `"got: $value"`. The expected behaviour (locked by test in 003.13) is that the message renders as `got: ${value}` literally — `string.Template` substitutes once and stops.

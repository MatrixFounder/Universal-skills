# Task 004.02: E2E + unit test scaffolding + synthetic round-trip pin + drift detection

## Use Case Connection
- **UC-1** (LLM array-of-objects), **UC-2** (multi-sheet), **UC-3** (JSONL), **UC-4** (stdin envelope), **UC-5** (round-trip synthetic) — every test fixture for every UC is scaffolded here.

## Task Goal
Author the full test inventory for xlsx-2 in Stub-First red state: (a) extend `tests/test_e2e.sh` with ≥ 10 named E2E cases that exercise the CLI from the outside; (b) create `tests/test_json2xlsx.py` with ≥ 25 unit cases (covering parse / coerce / style / sheet validation / encoding); (c) pin the synthetic xlsx-8 round-trip JSON contract at `tests/golden/json2xlsx_xlsx8_shape.json`; (d) wire the style-constant drift assertion (AQ-1 lock). Every test is **expected red** at end-of-task because logic doesn't exist yet — but the failure mode must be uniform `NotImplementedError`, NOT `ImportError` / `AssertionError on missing fixture`.

**Closes AQ-1** — drift-detection mechanism: test setUp adds `sys.path.insert(0, "<scripts>")`, the assertion accepts both `"F2F2F2"` and `"00F2F2F2"` to absorb openpyxl's lazy ARGB normalisation.

**Closes AQ-5** — `T-roundtrip-xlsx8-live` is gated by `@unittest.skipUnless(_xlsx2json_available(), "xlsx-8 not landed yet")`; the helper checks for `import xlsx2json` succeeding.

## Changes Description

### New Files

- `skills/xlsx/scripts/tests/test_json2xlsx.py` — ≥ 25 unit cases, organised into classes per F-region:

  ```
  TestLoaders (F1+F2)
    test_read_input_file_utf8
    test_read_input_stdin_dash
    test_read_input_file_not_found
    test_detect_array_of_objects
    test_detect_multi_sheet_dict
    test_detect_jsonl_by_extension
    test_detect_unsupported_scalar
    test_detect_unsupported_list_of_lists
    test_detect_empty_array_no_rows
    test_jsonl_blank_line_tolerated
    test_jsonl_malformed_line_reports_line_number

  TestCoerce (F3)
    test_coerce_int_to_int
    test_coerce_bool_to_bool_not_int     # checks bool-before-int rule (ARCH §4.1)
    test_coerce_iso_date_to_date
    test_coerce_iso_datetime_to_datetime
    test_coerce_aware_dt_default_to_utc_naive
    test_coerce_aware_dt_strict_dates_raises
    test_coerce_invalid_date_no_coerce
    test_coerce_no_date_coerce_flag

  TestWriter (F4)
    test_union_headers_first_seen_order
    test_validate_sheet_name_ok
    test_validate_sheet_name_too_long
    test_validate_sheet_name_invalid_chars
    test_style_header_row_bold_grey_centre
    test_size_columns_caps_at_max
    test_style_constants_drift_csv2xlsx   # AQ-1 LOCK

  TestCliHelpers (F6+F8)
    test_assert_distinct_paths_collision_exit_6
    test_assert_distinct_paths_stdin_skipped
    test_post_validate_enabled_truthy_allowlist
  ```

  **All tests RED in this task** — `setUp` adds `sys.path.insert(0, str(Path(__file__).parent.parent))`; tests call into stubs which raise `NotImplementedError`. Uses `self.assertRaises(NotImplementedError, …)` *as a temporary contract* in 004.02; each test gets rewritten to assert the real behaviour as its owning F-region logic lands.

- `skills/xlsx/scripts/tests/golden/json2xlsx_xlsx8_shape.json` — synthetic round-trip pin. Hand-authored JSON that mirrors the xlsx-8 output shape declared in backlog row xlsx-8 (line 194):

  ```json
  {
    "Employees": [
      {"Name": "Alice", "Hired": "2024-01-15", "Salary": 100000, "Active": true},
      {"Name": "Bob",   "Hired": "2025-06-01", "Salary": 95000,  "Active": true},
      {"Name": "Carol", "Hired": "2026-02-20", "Salary": null,   "Active": false}
    ],
    "Departments": [
      {"Dept": "Eng",   "Head": "Alice", "HC": 12},
      {"Dept": "Ops",   "Head": "Bob",   "HC": 8}
    ]
  }
  ```

  Locked attributes: (a) sheet names as top-level keys (NO normalisation); (b) ISO-8601 dates as strings; (c) JSON `null` preserved; (d) JSON `bool` preserved; (e) `int` vs `float` numeric types preserved.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Append a new `# ==== xlsx-2 / json2xlsx.py ====` block with ≥ 10 named E2E cases. **All red in this task** — assertions written against the final-state expected behaviour, then commented-out / `skip`'d / temporarily replaced with `NotImplementedError`-grep until each F-region lands.

E2E case inventory:

| Tag | Setup | Expected (final state) |
| :--- | :--- | :--- |
| `T-happy-single-sheet` | `echo '[{"Name":"Alice","Age":30}]' > in.json; json2xlsx.py in.json out.xlsx` | Exit 0; `out.xlsx` opens; sheet "Sheet1"; B2=30 numeric; styled header |
| `T-happy-multi-sheet` | Write multi-sheet JSON; `json2xlsx.py in.json out.xlsx` | Exit 0; 2 sheets in input order; each independently styled |
| `T-happy-jsonl` | `printf '{"a":1}\n{"a":2}\n' > in.jsonl; json2xlsx.py in.jsonl out.xlsx` | Exit 0; 1 sheet; 2 rows |
| `T-stdin-dash` | `cat in.json | json2xlsx.py - out.xlsx` | Exit 0; equivalent to file mode |
| `T-same-path` | `json2xlsx.py same.xlsx same.xlsx --json-errors` | Exit 6; stderr is single-line JSON envelope `{v:1, error:..., code:6, type:"SelfOverwriteRefused", details:{input,output}}` |
| `T-invalid-json` | `echo '[{' > truncated.json; json2xlsx.py truncated.json out.xlsx --json-errors` | Exit 2; envelope `type: JsonDecodeError`, `details: {line, column}` |
| `T-empty-array` | `echo '[]' > empty.json; json2xlsx.py empty.json out.xlsx` | Exit 2; type `NoRowsToWrite` |
| `T-iso-dates` | JSON with `"Hired": "2024-01-15"`; convert | Exit 0; `Hired` cell `data_type=='n'`; `number_format` starts with `YYYY-MM-DD` |
| `T-strict-dates-aware-rejected` | JSON with `"Ts": "2024-01-15T09:00:00Z"`; `json2xlsx.py … --strict-dates --json-errors` | Exit 2; envelope `type: TimezoneNotSupported`, `details: {value, tz_offset}` |
| `T-roundtrip-xlsx8-synthetic` | Use `tests/golden/json2xlsx_xlsx8_shape.json` as input; convert to `roundtrip.xlsx`; open with openpyxl; verify sheet names + headers + cell values match expected |
| `T-envelope-cross5-shape` | `json2xlsx.py /nonexistent out.xlsx --json-errors` | Exit 1; envelope contains exactly the keys `{v, error, code, type, details}` — NO `ok` / `message` (cross-5 frozen schema lock) |

(11 cases ≥ 10 minimum.)

#### File: `skills/xlsx/scripts/tests/__init__.py` (if absent)

- Ensure test discovery works for `test_json2xlsx.py` (mirror xlsx-7 setup).

### Component Integration

Tests live alongside existing xlsx test files. The E2E harness reuses existing `assert_exit`, `assert_stderr_contains` helpers from `test_e2e.sh`. Synthetic golden JSON lives under `tests/golden/` (new directory; or reuse if xlsx-7 created it — confirm in 004.02 first).

## Test Cases

### Meta-test: this task's own verification

1. **TC-META-01:** Running `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest tests.test_json2xlsx` reports `ran NN tests, errors=NN, failures=0` with every failure root cause being `NotImplementedError` (NOT `AssertionError on missing fixture`, NOT `ImportError`).
2. **TC-META-02:** `bash skills/xlsx/scripts/tests/test_e2e.sh` reports the xlsx-2 block as expected-fail with consistent `NotImplementedError` markers in stderr.
3. **TC-META-03:** The drift-detection unit test `test_style_constants_drift_csv2xlsx` is currently passing (csv2xlsx is the live source of truth; writer.py constants don't exist yet, so the assertion is one-sided pre-004.06).

### Regression Tests
- xlsx-6 / xlsx-7 / csv2xlsx unit + E2E suites pass unchanged.

## Acceptance Criteria

- [ ] `tests/test_json2xlsx.py` has ≥ 25 named test methods organised in 4 classes.
- [ ] `tests/test_e2e.sh` has the xlsx-2 block with ≥ 10 named tags.
- [ ] `tests/golden/json2xlsx_xlsx8_shape.json` exists and matches the shape locked in this task.
- [ ] Every test in the xlsx-2 block fails *uniformly* with `NotImplementedError` (NOT mixed exception types) — **EXCEPT** `T-same-path`, which is expected to turn GREEN at the END of 004.03 (cli_helpers.assert_distinct_paths lands there, NOT in 004.02). The test stays RED in this task and turns GREEN in the next. Plan-reviewer #11 nit.
- [ ] `test_style_constants_drift_csv2xlsx` accepts both `"F2F2F2"` and `"00F2F2F2"` (AQ-1 closure).
- [ ] `T-roundtrip-xlsx8-live` skipped via `@unittest.skipUnless(_xlsx2json_available(), …)`; helper present (AQ-5 closure).
- [ ] Existing test suites green.
- [ ] `validate_skill.py skills/xlsx` exits 0.

## Notes

- The strategy in this task is **lock all tests now, turn green later**. By 004.08 every E2E case is green; by 004.05 the TestCoerce class is green; etc. Tracking which test belongs to which task is in the test-class docstring.
- Style-constant drift assertion is the one place we cross-reference `csv2xlsx`; this is an intentional, single-touch coupling that does NOT make csv2xlsx a library import target during production code paths.
- Synthetic xlsx-8 contract: write **only** the shape attributes locked in this task. xlsx-8's eventual emission may vary on optional cosmetic details (cell-value indentation in JSON output, etc.) — those don't matter; what matters is sheet names, headers, types, null handling.

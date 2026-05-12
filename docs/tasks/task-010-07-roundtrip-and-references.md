# Task 010-07 [LOGIC IMPLEMENTATION]: Round-trip contract + references + 30-E2E cluster

## Use Case Connection
- UC-10 (round-trip xlsx-2 ↔ xlsx-8)
- UC-01..UC-09 (locked via full E2E cluster)

## Task Goal

Activate the round-trip contract between xlsx-2 (`json2xlsx`) and
xlsx-8 (`xlsx2json`); update `references/json-shapes.md` with the
xlsx-8 read-back shapes (R11 a–e); add the 30-E2E test cluster from
TASK §5.5; wire the env-flag opt-in `XLSX_XLSX2CSV2JSON_POST_VALIDATE`;
finalise the honest-scope docstring in `xlsx2csv2json/__init__.py`.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/references/json-shapes.md`

**Append** a new top-level section:

```markdown
---

## xlsx-8 read-back shapes (`xlsx2json.py`)

> **Status:** Frozen contract as of Task 010 merge. xlsx-2
> (`json2xlsx.py`) v1 consume behaviour for each shape is documented;
> shapes (3) and (4) are **lossy** on xlsx-2 v1 consume (deferred to
> xlsx-2 v2 `--write-listobjects`).

### Shape 1 — Single sheet, single region (flat array-of-objects)

[example JSON …]

### Shape 2 — Multi-sheet, single region per sheet (dict-of-arrays)

[example JSON …]

### Shape 3 — Multi-sheet, multi-region per sheet (nested `tables`)

[example JSON …]
> xlsx-2 v1 consume: collapses `tables` key — per-table arrays
> concatenated under the sheet key OR first region wins. Full
> reverse-restore deferred to xlsx-2 v2.

### Shape 4 — Single sheet, multi-region (flat `{Name: [...]}`)

[example JSON …]
> xlsx-2 v1 consume: same lossy behaviour as Shape 3.

### Hyperlink dict-shape (cell-level, when `--include-hyperlinks`)

\`\`\`json
{"col_a": {"value": "click here", "href": "https://..."}, "col_b": 42}
\`\`\`

### `--header-flatten-style array` shape (multi-row header in JSON)

[finalised in 010-05 implementation; lock the exact envelope here]
```

Each shape gets a 5–10 line synthetic example. Reference TASK §R11
for the rule numbers.

#### File: `skills/xlsx/scripts/json2xlsx/tests/test_json2xlsx.py`

**Modify** `TestRoundTripXlsx8::test_live_roundtrip` (or whatever
the existing skipUnless gate predicate is):

- Before: `@unittest.skipUnless(<xlsx-8 not yet shipped>, "xlsx-8 pending")`.
- After: gate flipped to live (always-run). The predicate may be
  removed entirely OR repurposed to skip only when the
  `xlsx2json.py` shim is missing from disk (defensive against tests
  running in a partial checkout):
  ```python
  @unittest.skipUnless(
      (Path(__file__).resolve().parents[3] / "scripts" / "xlsx2json.py").exists(),
      "xlsx2json.py shim not present",
  )
  def test_live_roundtrip(self):
      ...
  ```
- The test body verifies: take a reference `.xlsx`, run xlsx-2
  → JSON via `xlsx2json.py`, run JSON → xlsx-2 via `json2xlsx.py`,
  run xlsx-2 → JSON via `xlsx2json.py` again, `diff -q` the two
  JSON outputs → empty (byte-identical).

**Risk mitigation (plan §5 R-2):** add a positive assertion to the
test class to fail-loud if the test is silently skipped:
```python
def test_live_roundtrip_is_not_skipped(self):
    self.assertTrue(
        (Path(__file__).resolve().parents[3] / "scripts" / "xlsx2json.py").exists(),
        "Post-xlsx-8 merge, xlsx2json.py shim MUST exist",
    )
```

#### File: `skills/xlsx/scripts/xlsx2csv2json/__init__.py`

**Replace** the placeholder docstring with the full honest-scope
catalogue (TASK §1.4 a–l):

```python
"""xlsx-8: read-back CLI body — emit .xlsx as CSV or JSON.

Thin emit-side glue on top of the xlsx-10.A `xlsx_read/` foundation.

Honest scope (v1):
- (a) Cached value only ...
- (b) Rich-text spans → plain-text concat ...
...
- (l) `--tables listobjects` includes Tier-2 named ranges silently.

Path-component reject list (when CSV multi-region mode in effect):
{/, \\, .., NUL, :, *, ?, <, >, |, "} plus "." and "".

`--tables` enum mapping (D-A2):
- whole        → library mode `whole`
- listobjects  → library mode `tables-only` (incl. Tier-2 named ranges)
- gap          → library mode `auto` + post-filter `r.source == "gap_detect"`
- auto         → library mode `auto`
"""
```

#### File: `skills/xlsx/scripts/xlsx2csv2json/cli.py`

**Add** post-validate env-flag check at end of `_dispatch_to_emit`:

```python
def _post_validate_json_output(output_path: Path | None) -> None:
    """Env-flag opt-in JSON round-trip via json.loads.

    Triggered by `XLSX_XLSX2CSV2JSON_POST_VALIDATE=1`. On failure:
    unlink the output file and raise PostValidateFailed (exit 7).
    """
    import os, json
    if os.environ.get("XLSX_XLSX2CSV2JSON_POST_VALIDATE") != "1":
        return
    if output_path is None:
        return  # stdout — no file to validate
    try:
        json.loads(output_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        try:
            output_path.unlink()
        except OSError:
            pass
        raise PostValidateFailed(f"JSON re-parse failed: {output_path.name}") from exc
```

Wire it in `_dispatch_to_emit` AFTER `emit_json` returns (CSV path
skips — CSV has no schema; per TASK §R20.b).

### New Files

#### `skills/xlsx/scripts/xlsx2csv2json/tests/test_e2e.py`

Implements the 30 E2E scenarios from TASK §5.5 as test methods:

```python
class TestE2EReadBack(unittest.TestCase):
    # 1.  json_single_sheet_default_flags                       — UC-01
    # 2.  json_stdout_when_output_omitted                       — UC-01 A1
    # 3.  json_sheet_named_filter                               — UC-01 A2
    # 4.  json_hidden_sheet_skipped_default                     — UC-01 A3
    # 5.  json_hidden_sheet_included_with_flag                  — UC-01 A3
    # 6.  json_special_char_sheet_name_preserved                — UC-01 A4
    # 7.  csv_single_sheet_stdout                                — UC-02
    # 8.  csv_sheet_all_without_output_dir_exits_2               — UC-02 A1
    # 9.  csv_quoting_minimal_correct                            — UC-02
    # 10. json_multi_table_listobjects_nested_shape              — UC-03
    # 11. json_multi_table_gap_detect_default_2_1                — UC-03 A1
    # 12. json_multi_table_auto_falls_back_to_gap                — UC-03 A2
    # 13. json_single_table_falls_through_flat                   — UC-03 A3
    # 14. header_rows_int_with_multi_table_exits_2_HeaderRowsConflict — UC-03 A4
    # 15. csv_multi_table_subdirectory_schema                    — UC-04
    # 16. csv_multi_table_without_output_dir_exits_2             — UC-04 A1
    # 17. csv_sheet_name_with_slash_exits_2_InvalidSheetNameForFsPath — UC-04 A2
    # 18. header_rows_auto_detects_multi_row_header_with_U203A   — UC-05
    # 19. header_flatten_style_array_only_for_json               — UC-05 A1
    # 20. ambiguous_header_boundary_surfaced_as_warning          — UC-05 A2
    # 21. synthetic_headers_when_listobject_header_row_count_zero — UC-05 A3
    # 22. hyperlinks_json_dict_shape_value_href                  — UC-06
    # 23. hyperlinks_csv_markdown_link_text_url                  — UC-06
    # 24. encrypted_workbook_exits_3_with_basename_only          — UC-07
    # 25. same_path_via_symlink_exits_6_SelfOverwriteRefused     — UC-08
    # 26. json_errors_envelope_shape_v1                          — UC-09
    # 27. roundtrip_xlsx2_simple_shape_byte_identical            — UC-10
    # 28. merge_policy_anchor_only_fill_blank_three_fixtures     — R8
    # 29. include_formulas_emits_formula_strings_not_cached      — R6.e
    # 30. output_dir_path_traversal_rejected_OutputPathTraversal  — §4.2
```

Each method:
- Uses `subprocess.run(["python3", "skills/xlsx/scripts/xlsx2(json|csv).py", ...])`
  OR direct `convert_xlsx_to_*(...)` call (faster, isolates Python
  process startup overhead).
- Asserts exit code + (where file output) parses correctly + (where
  envelope) JSON line shape.

#### Fixtures (new — to be hand-built):

- `fixtures/encrypted.xlsx` — encrypted with password "test".
- `fixtures/macro_enabled.xlsm` — carries `vbaProject.bin`.
- `fixtures/multi_row_header.xlsx` — 2-row header (banner + sub-labels), 1 sheet.
- `fixtures/listobject_header_zero.xlsx` — ListObject with `headerRowCount=0`.
- `fixtures/merge_overlap_*.xlsx` — three policies × 1 fixture each
  (anchor-only, fill, blank).
- `fixtures/with_formulas.xlsx` — cells with `=SUM(...)` formulas and
  cached values.
- `fixtures/ambiguous_header_boundary.xlsx` — merge straddles
  detected header/body cut.
- `fixtures/hidden_sheet.xlsx` — 1 visible + 1 hidden + 1 veryHidden.
- `fixtures/special_char_sheet_name.xlsx` — sheet named `"Q1 / Q2 split"`.

Reuse `xlsx_read/tests/fixtures/*.xlsx` where applicable (test-suite
isolation NOT required — fixtures are read-only).

#### `skills/xlsx/scripts/xlsx2csv2json/tests/test_post_validate.py`

Unit tests for the env-flag post-validate hook:

1. **TC-UNIT-01:** env flag unset → no validation, no raise.
2. **TC-UNIT-02:** env flag set + valid JSON output → no raise.
3. **TC-UNIT-03:** env flag set + corrupted file (truncate) → raises `PostValidateFailed`, file unlinked.
4. **TC-UNIT-04:** env flag set + CSV path (output_path=None for the helper) → skip, no raise (CSV has no schema).

### Component Integration

- xlsx-2's existing `TestRoundTripXlsx8` becomes a live test of this
  pair — first proof that the two-way contract holds.
- The 30-E2E cluster lives in `xlsx2csv2json/tests/test_e2e.py` —
  isolated from prior xlsx test suites.

## Test Cases

### End-to-end Tests

All 30 in `test_e2e.py` (listed above) — green is the gate.

### Unit Tests

- `test_post_validate.py` × 4 (listed above).

### Regression Tests

- xlsx-2's `TestRoundTripXlsx8::test_live_roundtrip` — must be live
  AND green.
- xlsx-2's `test_live_roundtrip_is_not_skipped` defensive — must be
  green.
- All previous tests green (010-01..010-06).
- `ruff check scripts/` green.

## Acceptance Criteria

- [ ] `references/json-shapes.md` updated with xlsx-8 section
  (shapes 1–4 + hyperlink + array-style).
- [ ] xlsx-2's `TestRoundTripXlsx8::test_live_roundtrip` skipUnless
  gate flipped (or predicate adjusted to defensive form).
- [ ] `test_live_roundtrip_is_not_skipped` defensive assertion added.
- [ ] 30 E2E scenarios in `test_e2e.py` — ALL GREEN.
- [ ] Env-flag post-validate hook wired; 4 unit tests pass.
- [ ] `xlsx2csv2json/__init__.py` docstring includes full TASK §1.4
  honest-scope catalogue.
- [ ] All required fixtures created.
- [ ] `ruff check scripts/` green.
- [ ] 12-line `diff -q` silent (ARCH §9.4).

## Notes

- **Round-trip test scope:** simple-shape (rule 1 or rule 2) only.
  Shapes 3 and 4 are lossy on xlsx-2 v1 consume; their round-trip is
  NOT in the test (deferred to xlsx-2 v2).
- **Encrypted fixture:** generate via `office_passwd.py` (xlsx skill's
  password helper) to ensure detection path matches production.
- **Macro fixture:** can be a copy of `xlsx_read/tests/fixtures/*.xlsm`
  if one exists; otherwise generate via openpyxl + manual zip
  injection (low-effort because the test only checks the warning
  surface, not VBA execution).
- **Fixture file size discipline:** keep each ≤ 20 KiB to avoid
  bloating the repo. Hand-built single-row workbooks are typically
  ~6 KiB.

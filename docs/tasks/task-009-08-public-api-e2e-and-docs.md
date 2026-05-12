# Task 009-08: F7 public API wiring + 30 E2E + final gates [LOGIC IMPLEMENTATION + DOCS]

## Use Case Connection
- **UC-01..UC-06** (full integration of all functional regions).

## RTM Coverage
- **[R1]** Public API surface closure — closed-API regression test
  that returns are NEVER openpyxl types.
- **[R6]** `read_table()` dispatch — finalised wiring through F3
  (`_merges`), F5 (`_headers`), F6 (`_values`).
- **[R12]** Honest-scope + thread-safety docs — final pass.
- **[R13]** Test suite (≥ 20 E2E) + validator + 12-line `diff -q`
  silent gate — final gate.

## Task Goal

Bind `WorkbookReader.read_table` to the pipeline F4 (region) →
F5 (headers) → F3 (merges + overlap check) → F6 (values), produce
the materialised `TableData`. Land the full **30-scenario E2E**
suite from TASK §5.5 in `tests/test_e2e.py`. Run all final gates
and verify silent diff. Update `SKILL.md §10` and `.AGENTS.md` as
the closing documentation pass.

## Changes Description

### New Files
- `skills/xlsx/scripts/xlsx_read/tests/test_e2e.py` — 30 named
  scenarios from TASK §5.5 (1–30).
- `skills/xlsx/scripts/xlsx_read/tests/test_public_api.py` —
  closed-API regression tests:
  - Assert `__all__` membership unchanged (parity with TC-UNIT-01
    of 009-01).
  - Walk public-API return values; assert
    `not any('openpyxl' in repr(type(x)) for x in
    flatten(returned))`.
  - AST-grep regression — no module-level mutable globals in
    `xlsx_read/*.py` (L2 fix; UC-05 acceptance criterion).

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_read/_types.py` (UPDATE — final wiring)
- `WorkbookReader.read_table(self, region: TableRegion, *,
  header_rows="auto", merge_policy="anchor-only",
  include_hyperlinks=False, include_formulas=False,
  datetime_format="ISO") -> TableData`:
  - Resolve the sheet object: `ws = self._wb[region.sheet]`.
  - `merges = _merges.parse_merges(ws)`.
  - Slice the raw row-grid from `region` bounds.
  - `_merges._overlapping_merges_check(ws.merged_cells.ranges)` —
    raises `OverlappingMerges` if any.
  - `rows = _merges.apply_merge_policy(raw_rows, merges,
    merge_policy)`.
  - **Header resolution branch:**
    - If `region.source == "listobject"` and
      `region.listobject_header_row_count == 0`:
      - Use `_headers.synthetic_headers(width)`; append warning
        `f"Table {region.name!r} had no headers; emitted synthetic
        col_1..col_{width}"`.
    - Else: `hdr = _headers.detect_header_band(ws, region,
      header_rows)`; `headers, hdr_warnings =
      _headers.flatten_headers(rows[:hdr], hdr)`; check ambiguous
      boundary; consume header rows from `rows`.
  - **Value extraction:** for each row, for each cell in column
    span, call `_values.extract_cell(cell,
    include_formulas=..., include_hyperlinks=...,
    datetime_format=...)`; lift warnings into `warnings` list.
  - Return `TableData(region=region, headers=headers, rows=rows,
    warnings=warnings)`.

#### File: `skills/xlsx/scripts/xlsx_read/__init__.py`
- Verify `__all__` unchanged from 009-01.
- Add module-level closing docstring paragraph re-stating honest-
  scope + thread-safety constraints (R12 closure).

#### File: `skills/xlsx/.AGENTS.md`
- Update `## xlsx_read/` section to reflect **final** module layout
  (the contract is now stable; this is informational).

#### File: `skills/xlsx/SKILL.md` (§10)
- Verify the known-duplication marker is present (from 009-01); no
  text change — just an audit pass.

## Test Cases

### End-to-end Tests (`test_e2e.py` — 30 named scenarios, TASK §5.5)

| # | Scenario | Fixture (reused) |
| --- | --- | --- |
| 1 | open_encrypted_raises_EncryptedWorkbookError | encrypted.xlsx |
| 2 | open_xlsm_emits_MacroEnabledWarning_only | macros.xlsm |
| 3 | open_corrupted_zip_propagates_openpyxl_error_unchanged | (text file) |
| 4 | sheets_enumerate_visible_plus_hidden_state_field | three_sheets_mixed.xlsx |
| 5 | sheets_enumerate_include_hidden_skipped_by_caller_filter | three_sheets_mixed.xlsx |
| 6 | sheets_resolver_NAME_returns_one_entry | three_sheets_mixed.xlsx |
| 7 | sheets_resolver_all_returns_all | three_sheets_mixed.xlsx |
| 8 | sheets_resolver_missing_NAME_raises_SheetNotFound | three_sheets_mixed.xlsx |
| 9 | merges_anchor_only_three_fixtures | merges_row/col/rect.xlsx |
| 10 | merges_fill_three_fixtures | same |
| 11 | merges_blank_three_fixtures | same |
| 12 | tables_listobject_detect_with_xl_tables_fixture | listobject_one.xlsx |
| 13 | tables_listobject_headerRowCount_zero_synthetic_headers | listobject_no_header.xlsx |
| 14 | tables_named_range_detect_sheet_scope | named_range_sheet_scope.xlsx |
| 15 | tables_named_range_workbook_scope_ignored | named_range_workbook_scope.xlsx |
| 16 | tables_gap_detect_default_thresholds_2_rows_1_col | gap_two_tables.xlsx |
| 17 | tables_auto_fallback_no_listobjects_uses_gap_detect | gap_two_tables.xlsx |
| 18 | headers_single_row_default_behavior | headers_single_row.xlsx |
| 19 | headers_multi_row_auto_detect_flatten_with_U203A | headers_two_row_merged.xlsx |
| 20 | headers_ambiguous_boundary_emits_warning | headers_ambiguous.xlsx |
| 21 | values_formula_cached_default | values_formula_cached.xlsx |
| 22 | values_formula_stale_cache_emits_warning | values_stale_cache.xlsx |
| 23 | values_number_format_heuristic_decimal_percent_currency_text | values_numformat.xlsx |
| 24 | values_datetime_iso_excel_serial_raw | values_numformat.xlsx |
| 25 | values_hyperlink_extracted_when_opted_in | values_hyperlink.xlsx |
| 26 | values_rich_text_flatten_spans | values_richtext.xlsx |
| 27 | public_api_closed_no_openpyxl_leak | any |
| 28 | overlapping_merges_raises_OverlappingMerges | overlapping_merges.xlsx |
| 29 | dataclasses_outer_frozen_inner_mutable | (constructed) |
| 30 | module_level_singletons_absent (AST-grep) | xlsx_read/*.py |

### Unit Tests (in `test_public_api.py`)

1. **TC-UNIT-01 (`__all__` integrity carryover):** Same regression
   as 009-01 TC-UNIT-01, re-asserted.
2. **TC-UNIT-02 (closed-api no-openpyxl-leak):** Walk every public
   return value (sheets list, regions list, TableData fields);
   assert no `openpyxl.*` types reachable via `type(...)`.
3. **TC-UNIT-03 (no module-level mutable singletons):** AST-parse
   each `xlsx_read/*.py`; assert no module-level `=` assignments
   create `list`, `dict`, `set` literals (regression for L2 fix /
   UC-05 acceptance criterion).

### Regression Tests
- All previous 009-0X test files green.
- `python3 .claude/skills/skill-creator/scripts/validate_skill.py
  skills/xlsx` exits 0.
- Existing xlsx-2/3/4/7 E2E suites green.
- 12-line cross-skill `diff -q` from ARCHITECTURE §9.4 — silent.

## Acceptance Criteria

- [ ] `WorkbookReader.read_table` wired end-to-end through F3 + F5 + F6.
- [ ] All 30 named E2E scenarios pass.
- [ ] All 3 `test_public_api.py` regression tests pass.
- [ ] `ruff check skills/xlsx/scripts` exit 0.
- [ ] `validate_skill.py skills/xlsx` exit 0.
- [ ] 12-line cross-skill `diff -q` silent.
- [ ] All previous test suites (009-01..009-07 + xlsx-2/3/4/7)
  remain green.
- [ ] `SKILL.md §10` known-duplication marker present;
  `.AGENTS.md §xlsx_read` finalised.

## Notes

- This task is the **final integration gate**. If any of the 30
  E2E scenarios fails, the failure points to the responsible
  upstream task (009-02..009-07) — do **not** patch in this task;
  open a follow-up in the responsible task's PR/branch.
- The closed-API leak regression (TC-UNIT-02) is the **single
  most important** test in this task — it guards the entire R1
  contract. If it ever flakes, treat as a P0.
- Memory check: with `read_only=True` (auto-mode for > 10 MiB),
  a 10K-row × 20-col `read_table` should stay under 200 MiB RSS
  (TASK §4.1 performance contract). Smoke-profile via
  `/usr/bin/time -l` (macOS) at task close; record actual peak
  in this task's PR description for later perf-budget tracking.

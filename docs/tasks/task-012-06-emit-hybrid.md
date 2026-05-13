# Task 012-06 [LOGIC IMPLEMENTATION]: `emit_hybrid.py` — per-table format selector, H2/H3 orchestration, `GfmMergesRequirePolicy` raise-site

> **Predecessor:** 012-04, 012-05.
> **RTM:** [R7] (multi-sheet H2 ordering), [R12] (hybrid auto-select;
> four promotion rules), [R15] (raise-site for `--format gfm` +
> body merges + default policy = fail → exit 2).
> **UCs:** UC-02 (H2 ordering), UC-03 (H3 ordering), UC-04 (hybrid
> promotion on merges), UC-05 (hybrid promotion on multi-row),
> UC-07 Scenario C (hybrid promotion on formulas), UC-11 (hybrid
> promotion on `headerRowCount=0`).

## Use Case Connection

- UC-02 — per-sheet `## SheetName` H2 in document order.
- UC-03 — per-table `### TableName` (ListObject / named range)
  or `### Table-N` (gap-detect / `--no-split`) H3.
- UC-04 — hybrid promotion rule 1: any body merge → HTML.
- UC-05 — hybrid promotion rule 2: any ` › ` in header → HTML.
- UC-07 Scenario C — hybrid promotion rule 3:
  `--include-formulas` + ≥ 1 formula cell → HTML (per-table).
- UC-11 — hybrid promotion rule 4: `listobject_header_row_count
  == 0` → HTML (per D13).

## Task Goal

Implement `emit_hybrid.py` per ARCH §2.1 F3 + TASK R2.e (this
module is the TASK-mandated "per-table format selector"):

1. `select_format(table_data, args)` returns `"gfm"` or `"html"`
   per the four promotion rules + `--format` flag.
2. `emit_workbook_md(reader, args, out)` is the outer orchestration
   loop: iterate `dispatch.iter_table_payloads`, emit per-sheet
   `## SheetName` H2, emit per-table `### TableName` H3, call
   `emit_gfm_table` or `emit_html_table` per `select_format`,
   flush.
3. Predicates `_has_body_merges`, `_is_multi_row_header`,
   `_has_formula_cells`, `_is_synthetic_header` are pure
   functions consumed by `select_format`.
4. `GfmMergesRequirePolicy` raise-site: when `args.format == "gfm"`
   AND body merges present in a table AND
   `args.gfm_merge_policy == "fail"` → raise (CODE=2). This is
   the D14 lock that the M7-style validation cannot do
   pre-open (because merge presence is unknown until library
   reads the table). The raise happens inside the orchestration
   loop, AFTER the offending table is read.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2md/emit_hybrid.py`

**Function `_has_body_merges(table_data) -> bool`:**

- Replace stub. Returns True iff `table_data.rows` contains at
  least one `None` cell after column position 0 in any row (i.e.
  a likely merge child via the heuristic established in 012-04 /
  012-05). Documented honest-scope: a cell explicitly set to
  `None` in the source is indistinguishable from a merge child.
- More accurate alternative: parse `table_data.warnings` for a
  "merge anchor" marker — but `xlsx_read` does NOT emit such a
  marker in v1. The `None`-run heuristic is the v1 default;
  follow-up xlsx-10.B may add a merges side-channel.

**Function `_is_multi_row_header(table_data) -> bool`:**

- Replace stub. Returns True iff any element of
  `table_data.headers` contains the substring ` › ` (U+203A
  with surrounding spaces). This is the locked D6 separator.
- A workbook with literal ` › ` in a single-row header will
  trigger this (A-A3 honest scope; documented).

**Function `_has_formula_cells(table_data) -> bool`:**

- Replace stub. Returns True iff any cell value in
  `table_data.rows` is a string starting with `"="` (formula
  marker — only meaningful when
  `reader.read_table(include_formulas=True)` was used).
- Note: `args.include_formulas == False` → formulas are NOT
  surfaced by the library; the cell value is the cached value.
  In that mode, this predicate always returns False — which is
  exactly what we want (no promotion).

**Function `_is_synthetic_header(table_data) -> bool`:**

- Replace stub. Returns True iff `table_data.region.source ==
  "listobject"` AND `table_data.region.listobject_header_row_count
  == 0`.

**Function `select_format(table_data, args) -> Literal["gfm", "html"]`:**

- Replace stub. Logic:
  ```text
  if args.format == "gfm":
      return "gfm"
  if args.format == "html":
      return "html"
  # args.format == "hybrid": apply four promotion rules
  if _has_body_merges(table_data):
      return "html"
  if _is_multi_row_header(table_data):
      return "html"
  if args.include_formulas and _has_formula_cells(table_data):
      return "html"
  if _is_synthetic_header(table_data):
      return "html"
  return "gfm"
  ```

**Function `emit_workbook_md(reader, args, out) -> int`:**

- Replace stub. Outer orchestration loop:
  ```text
  from .dispatch import iter_table_payloads
  from .emit_gfm import emit_gfm_table
  from .emit_html import emit_html_table

  current_sheet = None
  emitted_any = False
  single_sheet_mode = (args.sheet != "all")
  cell_addr_prefix = ""

  for sheet_info, region, table_data in iter_table_payloads(reader, args):
      # R7.d: --sheet NAME suppresses H2 (caller knows the sheet).
      if not single_sheet_mode:
          if current_sheet != sheet_info.name:
              if emitted_any:
                  out.write("\n")
              out.write(f"## {sheet_info.name}\n\n")
              current_sheet = sheet_info.name

      # R7 / Q-A1 closed: emit ### Table-N H3 even when --no-split
      # (predictable layout). Resolve table label:
      table_label = region.name or _gap_detect_label(...)
      # _gap_detect_label assigns "Table-1", "Table-2", ... per
      # discovery order within the current sheet (counter reset on
      # sheet change).
      out.write(f"### {table_label}\n\n")

      # GfmMergesRequirePolicy raise-site (R15 fail-mode lock):
      if (
          args.format == "gfm"
          and args.gfm_merge_policy == "fail"
          and _has_body_merges(table_data)
      ):
          raise GfmMergesRequirePolicy({
              "table": table_label,
              "sheet": sheet_info.name,
              "suggestion": "use --format hybrid, --format html, "
                            "or --gfm-merge-policy duplicate/blank",
          })

      fmt = select_format(table_data, args)
      if fmt == "gfm":
          emit_gfm_table(
              table_data, out,
              gfm_merge_policy=args.gfm_merge_policy,
              hyperlink_allowlist=args._hyperlink_allowlist,
              cell_addr_prefix=f"{sheet_info.name}!",
          )
      else:
          emit_html_table(
              table_data, out,
              include_formulas=args.include_formulas,
              hyperlink_allowlist=args._hyperlink_allowlist,
              cell_addr_prefix=f"{sheet_info.name}!",
          )
      out.write("\n")
      out.flush()  # D-A7 streaming flush
      emitted_any = True

  return 0
  ```

**Function `_gap_detect_label(state, region) -> str`:**

- Helper that maintains a per-sheet counter for unnamed regions
  (`region.name is None` — happens for `gap_detect` regions and
  `--no-split` whole-sheet regions). Returns `"Table-1"`,
  `"Table-2"`, etc., resetting on sheet change.
- For `--no-split` whole-sheet single region with `region.name is
  None`, returns `"Table-1"` (per ARCH Q-A1 closed decision).

### New Files

#### `skills/xlsx/scripts/xlsx2md/tests/test_emit_hybrid.py`

Unit tests for `select_format` + predicates + `emit_workbook_md`
+ `_gap_detect_label` (≥ 8 tests per TASK §5.2).

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/multi_sheet_in_order.xlsx`

Hand-built: 3 visible sheets `Sales`, `Costs`, `Summary` in that
document order. Each has 1 header + 2 rows. Used by H2 order test.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/multi_table_h3_order.xlsx`

Hand-built: 1 sheet with two ListObjects `RevenueTable` (rows
2-4) and `CostsTable` (rows 7-9). H3 order test.

### Changes in `xlsx2md/__init__.py`

No changes (re-exports were locked in 012-01; the orchestration
function `emit_workbook_md` is not exported — it's an internal
function used by `cli.main()`).

## Test Cases

### E2E Tests (binding TASK §5.1 slugs)

| # | Slug | Fixture | Assertion | Expected exit |
| --- | --- | --- | --- | --- |
| 3 | `T-sheet-named-filter` | `multi_sheet_in_order.xlsx` | `python3 xlsx2md.py multi_sheet_in_order.xlsx --sheet=Sales` → output has 0 `## ` headings (single-sheet mode suppresses H2 per R7.d); table content present. | 0 |
| 4 | `T-multi-sheet-h2-ordering` | `multi_sheet_in_order.xlsx` | `python3 xlsx2md.py multi_sheet_in_order.xlsx` → output has exactly 3 `## ` headings in order `Sales`, `Costs`, `Summary`. | 0 |
| 7 | `T-multi-table-listobjects-h3` | `multi_table_h3_order.xlsx` | `python3 xlsx2md.py multi_table_h3_order.xlsx` → output has exactly 2 `### ` headings in order `RevenueTable`, `CostsTable`. | 0 |
| 9 | `T-gfm-merges-require-policy-exit2` | `two_row_horizontal_merge.xlsx` (012-04) | `python3 xlsx2md.py two_row_horizontal_merge.xlsx --format=gfm` → envelope `type == "GfmMergesRequirePolicy"`. Raise-site is `emit_workbook_md`, NOT a pre-flight check (because merge presence is unknown until table is read). | 2 |

### Unit Tests

In `test_emit_hybrid.py` (≥ 8 tests per TASK §5.2):

1. **TC-UNIT-01** `test_select_format_gfm_no_merges_no_formula_returns_gfm`.
2. **TC-UNIT-02** `test_select_format_hybrid_with_merges_returns_html`.
3. **TC-UNIT-03** `test_select_format_hybrid_with_multi_row_header_returns_html`.
4. **TC-UNIT-04** `test_select_format_hybrid_with_formula_and_include_returns_html`.
5. **TC-UNIT-05** `test_select_format_hybrid_with_formula_but_no_include_returns_gfm`
   (formula cells not surfaced if `include_formulas=False`).
6. **TC-UNIT-06** `test_select_format_hybrid_with_synthetic_header_returns_html`.
7. **TC-UNIT-07** `test_select_format_explicit_gfm_overrides_all_promotion_rules`.
8. **TC-UNIT-08** `test_select_format_explicit_html_overrides_all_promotion_rules`.
9. **TC-UNIT-09** `test_emit_workbook_md_multi_sheet_h2_order`.
10. **TC-UNIT-10** `test_emit_workbook_md_multi_table_h3_order`.
11. **TC-UNIT-11** `test_emit_workbook_md_single_sheet_mode_suppresses_h2`
    (when `args.sheet != "all"`).
12. **TC-UNIT-12** `test_emit_workbook_md_gfm_merges_requires_policy_raises_at_merge_observed`
    (mock `iter_table_payloads` yields a table with merges + args
    `format=gfm`, `gfm_merge_policy=fail` → raises
    `GfmMergesRequirePolicy`).
13. **TC-UNIT-13** `test_emit_workbook_md_gfm_merge_policy_duplicate_no_raise`
    (same fixture but `gfm_merge_policy=duplicate` → no raise;
    emit completes; warning emitted by `_apply_gfm_merge_policy`).
14. **TC-UNIT-14** `test_gap_detect_label_resets_on_sheet_change`.
15. **TC-UNIT-15** `test_no_split_whole_sheet_emits_table_1_h3`
    (`args.no_split=True` → output contains `### Table-1` H3 per
    ARCH Q-A1 closed decision).

### Regression Tests

- 5-line `diff -q` silent gate.
- 012-01..012-05 tests still green; smoke E2E now produces a full
  markdown document (was: only header / body rows in 012-04, only
  body table in 012-05).
- `ruff check skills/xlsx/scripts/` green.
- Existing xlsx test suites unchanged.

## Acceptance Criteria

- [ ] `_has_body_merges`, `_is_multi_row_header`,
      `_has_formula_cells`, `_is_synthetic_header` predicates
      implemented per ARCH §2.1 F3.
- [ ] `select_format` applies the four promotion rules in the
      documented order; `--format gfm` / `--format html` short-
      circuit before promotion rules.
- [ ] `emit_workbook_md` emits `## SheetName` H2 per visible
      sheet in document order (suppressed when `args.sheet !=
      "all"` per R7.d).
- [ ] `emit_workbook_md` emits `### TableName` (or `### Table-N`)
      H3 per table in document order.
- [ ] `_gap_detect_label` maintains per-sheet counter, reset on
      sheet change.
- [ ] `GfmMergesRequirePolicy` raise-site fires when
      `--format=gfm` + body merges + default `--gfm-merge-policy=fail`.
- [ ] `--no-split` emits `### Table-1` H3 (Q-A1 closed).
- [ ] Streaming flush (`out.flush()`) after each table (D-A7).
- [ ] 4 E2E test slugs above passing.
- [ ] ≥ 15 unit tests passing.
- [ ] 012-01..012-05 tests still green.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] 5-line `diff -q` silent gate green.
- [ ] No changes to `xlsx_read/`, `office/`, `_errors.py`,
      `_soffice.py`, `preview.py`, `office_passwd.py`,
      `xlsx2csv2json/`, `json2xlsx/`, `md_tables2xlsx/`.

## Stub-First Gate Update

The 012-01..012-05 smoke E2E assertion is updated per
`tdd-stub-first §2.4`:

- For `single_cell.xlsx`, `python3 xlsx2md.py single_cell.xlsx`
  (default `--format=hybrid`) now produces a real complete
  markdown document with `## Sheet1` H2 + `### Table-1` (or
  similar) H3 + GFM table body (was: stand-alone table without
  H2/H3 in 012-04/05).

## Notes

- **`--no-split` H3 decision**: ARCH §12 closes Q-A1 as "emit
  `### Table-1` even in `--no-split`". TASK §3 UC-03 A2 said "no
  H3 heading emitted". ARCH supersedes TASK (it was specified
  AFTER TASK §3 was drafted; ARCH §2.1 F3 explicitly says
  "`### Table-1` H3 heading is still emitted"). The plan uses
  ARCH's wording.
- **`--sheet NAME` H2 suppression** is the orthogonal rule: when
  the caller selects a single sheet, no H2 wrapper is emitted
  (caller already knows the sheet). Tests #3 and #4 lock both
  behaviours.
- **R15 raise-site placement**: in xlsx-8's `xlsx2csv2json`, the
  CSV multi-region raise-site lives in `dispatch.py`. In xlsx-9,
  the equivalent `GfmMergesRequirePolicy` raise lives in
  `emit_hybrid.py` because the format decision (which determines
  whether the gate fires) and the merge observation happen in the
  same orchestration loop. Pre-flight validation
  (`_validate_flag_combo` in 012-02) cannot fire this gate because
  the merge presence is unknown pre-open.
- **Hybrid streaming**: per ARCH D-A7, after each table emit,
  call `out.flush()` so a piped consumer sees output incrementally.
- **`emit_workbook_md` return value**: `0` on success. Failure
  paths raise `_AppError` (caught by `cli.main()` envelope).
- **No new imports needed** beyond what 012-01..012-05 added.

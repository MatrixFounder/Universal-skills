# Task 012-05 [LOGIC IMPLEMENTATION]: `emit_html.py` + `headers.py` — HTML `<table>` emission, multi-row `<thead>` reconstruction

> **Predecessor:** 012-02, 012-03, 012-04 (`inline.py` shared).
> **RTM:** [R10a] (HTML half via shared helper), [R11], [R14c]
> (multi-row `<thead>` D-A11 reconstruction), [R18] (`data-formula`
> attr + `class="stale-cache"`).
> **UCs:** UC-04 (HTML colspan), UC-05 (multi-row HTML `<thead>`),
> UC-06 HTML half (`<a href>`), UC-07 Scenario B/C (`data-formula`),
> UC-11 HTML half (D13 synthetic `<thead>`).

## Use Case Connection

- UC-04 — merged body cells: `<td colspan="2">Total</td>` at
  anchor, child suppressed.
- UC-05 — multi-row header in HTML mode: `<thead>` with multiple
  `<tr>`; banner row gets `colspan` attribute; reconstruction
  from ` › `-joined headers per D-A11.
- UC-06 — hyperlink `<a href="url">text</a>` in HTML cells.
- UC-07 Scenario B/C — `--include-formulas` →
  `<td data-formula="=A1+B1">42</td>`; stale-cache →
  `<td data-formula="..." class="stale-cache"></td>`.
- UC-11 — `headerRowCount=0` ListObject in HTML mode emits
  visible `<thead>` with synthetic `col_1..col_N` cells (D13).

## Task Goal

Implement the HTML emitter (`emit_html.py`) and the header
reconstruction helper module (`headers.py`). The emitter writes
`<table>` blocks with `<thead>` + `<tbody>`, colspan/rowspan at
merge anchors, `<a href>` hyperlinks (via shared
`inline._render_hyperlink`), `data-formula` attributes when
`--include-formulas` is active, `class="stale-cache"` for stale
formula cells. The header helper module owns the emit-side
reconstruction of multi-row `<thead>` from `xlsx_read`'s
` › `-joined flat headers list (D12 / D-A11).

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2md/headers.py`

**Function `split_headers_to_rows(headers: list[str]) -> list[list[str]]`:**

- Replace stub. For each header string, split on ` › ` separator.
  Return a list of rows: `rows[i][j]` is the i-th header level of
  the j-th column.
- Example: `["2026 plan › Q1", "2026 plan › Q2", "2026 plan › Q3"]`
  → `[["2026 plan", "2026 plan", "2026 plan"], ["Q1", "Q2", "Q3"]]`.
- Single-row case: `["a", "b", "c"]` → `[["a", "b", "c"]]`.

**Function `compute_colspan_spans(header_rows: list[list[str]]) -> list[list[int]]`:**

- For each row except the last (leaf), compute colspan values for
  consecutive identical-prefix positions. Returns parallel list:
  `spans[i][j]` is the colspan of position j in row i. Positions
  with colspan == 1 still emit `<th>` (no `colspan` attr).
- Algorithm:
  - For row 0 (top banner): scan positions; consecutive
    identical values share a span; first position of the run
    gets the count, subsequent positions get 0 (suppressed from
    output).
  - For row i > 0: similar but the prefix path through rows
    0..i-1 must also match (i.e., compare the full prefix tuple,
    not just the current-level cell).
  - Leaf row (i == len-1): always colspan=1 for each position.

**Function `validate_header_depth_uniformity(headers: list[str]) -> int`:**

- Count ` › ` separators per header; if not uniform, raise
  `InconsistentHeaderDepth` (CODE=2). Otherwise return the depth
  N (separators + 1).
- This is the D-A11 defensive check; `xlsx_read.flatten_headers`
  is expected to enforce uniformity, but xlsx-9 double-checks.

#### File: `skills/xlsx/scripts/xlsx2md/emit_html.py`

**Function `emit_html_table(table_data, out, *, include_formulas=False,
hyperlink_allowlist, cell_addr_prefix="") -> None`:**

- Replace stub. Writes a complete HTML `<table>` block to `out`.
- Skeleton:
  ```text
  out.write("<table>\n")
  headers = list(table_data.headers)
  region = table_data.region
  _emit_thead(headers, region, out)
  _emit_tbody(table_data.rows, region, out,
              include_formulas=include_formulas,
              hyperlink_map=_build_hyperlinks_map(table_data),
              formula_map=_build_formula_map(table_data),
              allowed_schemes=hyperlink_allowlist,
              cell_addr_prefix=cell_addr_prefix)
  out.write("</table>\n")
  ```

**Function `_emit_thead(headers, region, out) -> None`:**

- If `headers` is empty (impossible after `xlsx_read` library
  resolution — `headerRowCount=0` produces synthetic
  `col_1..col_N` headers) → skip `<thead>` block (defensive).
- Else: validate depth uniformity via
  `headers.validate_header_depth_uniformity(headers)`. If depth
  N > 1: reconstruct multi-row `<thead>`:
  ```text
  header_rows = split_headers_to_rows(headers)
  spans = compute_colspan_spans(header_rows)
  out.write("<thead>\n")
  for row_idx, row in enumerate(header_rows):
      out.write("<tr>")
      for col_idx, text in enumerate(row):
          colspan = spans[row_idx][col_idx]
          if colspan == 0:
              continue  # suppressed (covered by earlier <th>)
          attr = f' colspan="{colspan}"' if colspan > 1 else ""
          out.write(f"<th{attr}>{html.escape(text)}</th>")
      out.write("</tr>\n")
  out.write("</thead>\n")
  ```
- For depth N == 1 (single-row header): emit single `<tr>` inside
  `<thead>` with one `<th>` per column.
- **D13 synthetic-header lock:** when `region.source ==
  "listobject" and region.listobject_header_row_count == 0`,
  headers will be `["col_1", "col_2", ...]` (synthetic from
  library). The `<thead>` block still emits — even though they're
  synthetic — because a `<table>` without `<thead>` is ambiguous
  for downstream parsers (D13). No special branch needed; the
  emit just runs through the standard single-row path.

**Function `_emit_tbody(rows, region, out, *, include_formulas,
hyperlink_map, formula_map, allowed_schemes, cell_addr_prefix) -> None`:**

- `out.write("<tbody>\n")`.
- For each `r_idx, row in enumerate(rows)`:
  - `out.write("<tr>")`.
  - For each `c_idx, value in enumerate(row)`:
    - If this cell is a merge child (suppressed) → skip.
      Determine via the same heuristic from 012-04
      `_apply_gfm_merge_policy` (`None`-run after non-None anchor)
      OR via a side-channel on `table_data` if added.
    - Compute `(colspan, rowspan)` from merge metadata; default
      `(1, 1)`.
    - Compute formula (if any) from `formula_map.get((r_idx,
      c_idx))`.
    - Compute hyperlink (if any) from `hyperlink_map.get((r_idx,
      c_idx))`.
    - Compute cell text via
      `inline.render_cell_value(value, mode="html",
      hyperlink_href=href, allowed_schemes=allowed_schemes,
      cell_addr=cell_addr_prefix + col_letter(c_idx) +
      str(r_idx + header_depth))`.
    - Determine `<td>` attributes:
      - `colspan="N"` if N > 1.
      - `rowspan="N"` if N > 1.
      - `data-formula="..."` if `include_formulas and formula is
        not None`. Value is `html.escape(formula, quote=True)`.
      - `class="stale-cache"` if `include_formulas and formula
        is not None and value is None` (stale).
    - `out.write(f"<td{attrs}>{cell_text}</td>")`.
  - `out.write("</tr>\n")`.
- `out.write("</tbody>\n")`.

**Function `_format_cell_html(value, *, formula=None, is_anchor=False,
colspan=1, rowspan=1) -> str`:**

- Convenience wrapper for `<td>` emit; consumed by
  `_emit_tbody` (alternative to the inline write above).
- Logic per ARCH §2.1 F5 — `html.escape` for text;
  `html.escape(url, quote=True)` for href; `<br>` for newlines;
  `data-formula` when applicable. Hyperlink is delegated to
  `inline._render_hyperlink` via `render_cell_value`.

### New Files

#### `skills/xlsx/scripts/xlsx2md/tests/test_emit_html.py`

Unit tests for `emit_html_table` + `_emit_thead` + `_emit_tbody`
+ `_format_cell_html` (≥ 12 tests per TASK §5.2).

#### `skills/xlsx/scripts/xlsx2md/tests/test_headers.py`

Unit tests for `headers.*` (≥ 8 tests).

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/multi_row_header_html.xlsx`

Hand-built (or symlink to `multi_row_header_gfm.xlsx` from
012-04): 2-row header with 1×3 banner merge.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/cell_with_formula.xlsx`

Hand-built: 1 sheet with cell `C3` containing formula `=A3+B3`
(cached value `42`), plus another cell `D3` with formula
`=A3*B3` and no cached value (stale). Used for `--include-formulas`
+ `class="stale-cache"` tests.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/cell_with_html_script.xlsx`

Hand-built: 1 sheet with cell `A2 = "<script>alert(1)</script>"`.
Used for HTML escape regression.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/vertical_merge.xlsx`

Hand-built: 1 sheet, 1 header row, column A merged across rows
2-4 with anchor value `"Name"`. Used for `rowspan` test.

## Test Cases

### E2E Tests (binding TASK §5.1 slugs)

| # | Slug | Fixture | Assertion | Expected exit |
| --- | --- | --- | --- | --- |
| 8 | `T-merged-body-cells-html-colspan` | `two_row_horizontal_merge.xlsx` (012-04) | `python3 xlsx2md.py two_row_horizontal_merge.xlsx --format=html` → output contains `<td colspan="2">Total</td>`; child `<td>` for col C is absent from the same `<tr>`. | 0 |
| 10 | `T-multi-row-header-html-thead` | `multi_row_header_html.xlsx` | `python3 xlsx2md.py multi_row_header_html.xlsx --format=html` → `<thead>` contains two `<tr>` rows; first `<th>` has `colspan="3"`; second row has 3 `<th>` cells with `Q1`, `Q2`, `Q3`. | 0 |
| 13 | `T-hyperlink-html-anchor-tag` | `hyperlink_various_schemes.xlsx` | `python3 xlsx2md.py hyperlink_various_schemes.xlsx --format=html` → output contains `<a href="https://ok.com">...</a>`. | 0 |
| 15 | `T-include-formulas-html-data-attr` | `cell_with_formula.xlsx` | `python3 xlsx2md.py cell_with_formula.xlsx --format=html --include-formulas` → output contains `data-formula="=A3+B3"` AND visible content `42`. | 0 |
| 24 | `T-synthetic-headers-listobject-zero` | `listobject_header_zero.xlsx` (012-03) | `python3 xlsx2md.py listobject_header_zero.xlsx --format=html` → output `<thead>` contains `<th>col_1</th>...<th>col_N</th>`; stderr warning contains `"synthetic col_1"`. | 0 |
| 30 | `T-hyperlink-allowlist-blocks-javascript-html` | `hyperlink_various_schemes.xlsx` | `--format=html` → for `javascript:` cell, `<td>` contains plain text (NO `<a href>`); stderr warning emitted. | 0 |

### Unit Tests

In `test_emit_html.py` (≥ 12 tests per TASK §5.2):

1. **TC-UNIT-01** `test_emit_html_single_row_header_simple_body`.
2. **TC-UNIT-02** `test_emit_html_horizontal_merge_colspan_anchor`.
3. **TC-UNIT-03** `test_emit_html_horizontal_merge_child_cell_suppressed`.
4. **TC-UNIT-04** `test_emit_html_vertical_merge_rowspan_anchor`.
5. **TC-UNIT-05** `test_emit_html_data_formula_attr_emitted`.
6. **TC-UNIT-06** `test_emit_html_stale_cache_class_on_empty_formula_cell`.
7. **TC-UNIT-07** `test_emit_html_newline_to_br_in_cell`.
8. **TC-UNIT-08** `test_emit_html_hyperlink_anchor_tag_form`.
9. **TC-UNIT-09** `test_emit_html_hyperlink_blocked_scheme_emits_text_only`.
10. **TC-UNIT-10** `test_emit_html_html_escape_lt_gt_amp_in_cell_text`
    (cell with `"<script>"` literal emits `&lt;script&gt;`).
11. **TC-UNIT-11** `test_emit_html_thead_multi_row_with_colspan`.
12. **TC-UNIT-12** `test_emit_html_synthetic_thead_when_header_rows_zero`
    (D13 lock: `headerRowCount=0` → `<thead>` with `col_1..col_N` visible).
13. **TC-UNIT-13** `test_emit_html_attribute_value_escape_double_quote_in_href`
    (href contains `"` → `&quot;`).
14. **TC-UNIT-14** `test_emit_html_attribute_value_escape_in_data_formula`
    (formula contains `"` → `&quot;`).

In `test_headers.py` (≥ 8 tests):

1. **TC-UNIT-01** `test_split_headers_single_row_passthrough`.
2. **TC-UNIT-02** `test_split_headers_two_level_separator`.
3. **TC-UNIT-03** `test_split_headers_three_level_separator`.
4. **TC-UNIT-04** `test_compute_colspan_top_row_groups_consecutive_identical`.
5. **TC-UNIT-05** `test_compute_colspan_leaf_row_always_1`.
6. **TC-UNIT-06** `test_compute_colspan_intermediate_row_groups_by_prefix_path`.
7. **TC-UNIT-07** `test_validate_header_depth_uniformity_returns_n`.
8. **TC-UNIT-08** `test_validate_header_depth_uniformity_raises_inconsistent_depth_on_mismatch`.

### Regression Tests

- 5-line `diff -q` silent gate.
- 012-01..012-04 tests still green; smoke E2E updated to assert
  HTML emit produces non-empty `<table>` for `single_cell.xlsx`
  with `--format=html`.
- `ruff check skills/xlsx/scripts/` green.
- Existing xlsx test suites unchanged.

## Acceptance Criteria

- [ ] `headers.split_headers_to_rows` correctly splits ` › `
      separators into row-by-row matrix.
- [ ] `headers.compute_colspan_spans` correctly groups
      consecutive identical prefix paths; suppresses covered
      positions via colspan=0 sentinel.
- [ ] `headers.validate_header_depth_uniformity` raises
      `InconsistentHeaderDepth` (CODE=2) on non-uniform depth.
- [ ] `emit_html_table` writes `<table>` + `<thead>` + `<tbody>`
      blocks per ARCH §2.1 F5.
- [ ] `<thead>` reconstruction emits multi-row `<tr>` with
      colspan attrs for banner rows; single-row case emits one
      `<tr>` with no colspan.
- [ ] Body merge anchor → `<td colspan="N">` / `<td rowspan="N">`;
      child cells suppressed.
- [ ] `--include-formulas` → `data-formula="=..."` attr; stale
      formula (no cached value) → `class="stale-cache"`.
- [ ] Hyperlink HTML emit: allowed → `<a href="...">...</a>`
      (uses shared `inline._render_hyperlink` from 012-04);
      blocked → plain text + warning.
- [ ] `html.escape` applied to cell text content + attribute
      values (`<script>` → `&lt;script&gt;`; `"` in href →
      `&quot;`).
- [ ] D13 lock: `headerRowCount=0` ListObject → visible
      `<thead>` with synthetic `col_1..col_N` `<th>` cells.
- [ ] 6 E2E test slugs above passing.
- [ ] ≥ 22 unit tests passing (14 + 8).
- [ ] 012-01..012-04 tests still green.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] 5-line `diff -q` silent gate green.
- [ ] No changes to `xlsx_read/`, `office/`,
      `_errors.py`, `_soffice.py`, `preview.py`,
      `office_passwd.py`, `xlsx2csv2json/`, `json2xlsx/`,
      `md_tables2xlsx/`.

## Stub-First Gate Update

The 012-01..012-04 smoke E2E assertion is updated per
`tdd-stub-first §2.4`:

- For `single_cell.xlsx`, `python3 xlsx2md.py single_cell.xlsx
  --format=html` now produces a real `<table>` (was: empty
  output in 012-04 because emit_html was still STUB).

## Notes

- **`<thead>` is always emitted** even for `headerRowCount=0`
  ListObjects (D13). The library returns synthetic
  `["col_1", "col_2", ...]` headers, which run through the
  standard single-row `<thead>` path — no special branch is
  needed inside `_emit_thead`.
- **Merge metadata side-channel:** `TableData` has no merges
  attribute (xlsx-10.A frozen API). The HTML emitter detects
  merge children via the `None`-run heuristic (same as 012-04
  `_apply_gfm_merge_policy`). For more accurate colspan/rowspan
  resolution, a follow-up xlsx-10.B can extend `TableData`. For
  v1, the heuristic is acceptable; document in module docstring.
  - Note: the heuristic detects horizontal spans inside a single
    row, but vertical spans (rowspan) require cross-row analysis.
    For UC-04 vertical merge fixture, the test asserts the
    rowspan attribute is correctly emitted when the merge is
    inferred from `None` cells in subsequent rows under a non-None
    anchor cell with no other non-None values in that column for
    the merge span.
  - Alternative: the emitter consults the closer-to-source
    `table_data.region` to compute merges by querying the
    workbook directly (via `reader.merges_in_region(...)` —
    NOT in xlsx_read public API; would require xlsx-10.B).
    For v1 honest scope: use the `None`-run heuristic; document.
- **`html.escape` parameters:** for cell text content,
  `html.escape(text, quote=False)` is sufficient (don't need to
  escape `"`, `'` in text content). For attribute values
  (`data-formula`, `href`), use `html.escape(text, quote=True)`
  (escapes `"` and `'`).
- **HTML pretty-printing:** A-A1 honest scope (no indentation
  within `<table>`). The emit functions write compact HTML.
- **`urllib.parse`** import is in `inline.py` (012-04). This task
  does not add it again.
- **`headers.py` IS NOT used by `emit_gfm.py`** — GFM mode keeps
  the flat headers as-is (one row with ` › ` separator). HTML
  mode reconstructs multi-row via this helper.
- **`InconsistentHeaderDepth`** is a defensive class declared in
  012-01 (`exceptions.py`). This is the first raise-site.

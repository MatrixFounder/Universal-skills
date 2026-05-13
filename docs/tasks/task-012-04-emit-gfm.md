# Task 012-04 [LOGIC IMPLEMENTATION]: `emit_gfm.py` + `inline.py` — pure GFM emission, hyperlink allowlist, multi-row flatten

> **Predecessor:** 012-02, 012-03.
> **RTM:** [R10], [R10a] (GFM half + shared `inline._render_hyperlink`),
> [R14d] (multi-row ` › ` flatten), [R15] (`_apply_gfm_merge_policy`),
> [R16] (newline `<br>`, pipe escape, hyperlink emit).
> **UCs:** UC-01 (GFM happy path), UC-04 (GFM merge policies +
> `GfmMergesRequirePolicy` raise-site shared with 012-06),
> UC-05 GFM half (` › ` flatten), UC-06 GFM half (`[text](url)`),
> UC-11 GFM half (synthetic visible header + separator),
> UC-12 (cell-newline `<br>`).

## Use Case Connection

- UC-01 — single sheet, default flags, no merges → valid GFM
  pipe table.
- UC-04 — GFM merge policy variants
  (`fail`/`duplicate`/`blank`).
- UC-05 — multi-row header in pure GFM: header rows flattened
  with ` › ` U+203A separator + warning.
- UC-06 — hyperlink emission `[text](url)` in GFM cells.
- UC-11 — `headerRowCount=0` listobject in GFM: synthetic
  visible header row `| col_1 | col_2 | ... |` + separator row.
- UC-12 — cell newline `\n` → `<br>` (round-trip with xlsx-3).

## Task Goal

Implement the pure GFM emitter (`emit_gfm.py`) and the shared
inline-content helper module (`inline.py`). The emitter writes
header + separator + body rows; the inline module owns cell-level
formatting (pipe escape, newline-to-`<br>`, hyperlink rendering
with scheme-allowlist filter).

This task also implements the hyperlink scheme allowlist (R10a /
D-A15) at the shared `inline._render_hyperlink` site — consumed by
both `emit_gfm.py` (here) and `emit_html.py` (012-05). Default
allowlist `{http, https, mailto}`; `'*'` allows all (None
sentinel); `""` blocks all (empty frozenset). Blocked schemes
emit plain `value` text + `UserWarning`.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2md/inline.py`

**Function `_escape_pipe_gfm(text: str) -> str`:**

- Replace stub. Return `text.replace("|", "\\|")`. Other GFM
  special chars (`*`, `_`, `` ` ``) pass through intentionally
  (markdown-in-cell affordance; mirrors xlsx-3 inline contract).

**Function `_escape_html_entities(text: str) -> str`:**

- Replace stub. Return `html.escape(text)` (consumed by
  `emit_html.py` in 012-05; living here per ARCH §2.1 F6 because
  this is the inline-rendering module).

**Function `_newlines_to_br(text: str) -> str`:**

- Replace stub. Return `"<br>".join(text.split("\n"))`. No
  trailing `<br>` unless the input has a trailing `\n`.

**Function `_render_hyperlink(value, href, *, mode, allowed_schemes) -> str`:**

- Replace stub. The CORE of D-A15 / R10a:
  - Parse `urllib.parse.urlsplit(href).scheme.lower()`.
  - Special case (R10a c): empty scheme (relative URL like
    `page.html`) → treated as `"http"`.
  - **Scheme decision:**
    - If `allowed_schemes is None` (sentinel for `'*'`) → allow.
    - If `allowed_schemes is frozenset()` → block (empty
      allowlist blocks all).
    - Else if `scheme in allowed_schemes` → allow; else block.
  - If allowed:
    - `mode == "gfm"` → return `f"[{value_text}]({href})"`
      where `value_text` is `_escape_pipe_gfm(str(value or ""))`
      with `\n` → `<br>` applied. Empty text → `f"[]({href})"`
      (UC-06 A1, valid markdown).
    - `mode == "html"` → return
      `f'<a href="{html.escape(href, quote=True)}">{html.escape(value_text)}</a>'`.
      Empty text → `f'<a href="...."></a>'`. (Consumed by 012-05;
      tested here.)
  - If blocked:
    - Emit `warnings.warn(f"cell {sheet}!{col_letter}{row}: "
      f"hyperlink scheme {scheme!r} not in allowlist; "
      f"emitted text-only", UserWarning, stacklevel=2)`.
      Note: the cell-location prefix requires context that
      `_render_hyperlink` doesn't have; the emit-side passes the
      `cell_addr: str | None` parameter so the warning can be
      precise. If not provided, the warning is the generic form
      `f"hyperlink scheme {scheme!r} not in allowlist; emitted text-only"`.
    - Return plain `value_text` (no markup).

Signature finalised:

```python
def _render_hyperlink(
    value: Any,
    href: str,
    *,
    mode: Literal["gfm", "html"],
    allowed_schemes: frozenset[str] | None,
    cell_addr: str | None = None,
) -> str: ...
```

**Function `render_cell_value(value, *, mode, include_formulas=False,
formula=None, hyperlink_href=None, allowed_schemes, cell_addr=None)
-> str`:**

- Central dispatcher consumed by both `emit_gfm.py` and
  `emit_html.py`:
  1. If `value is None` → return `""`.
  2. If `hyperlink_href is not None` (cell has hyperlink) →
     route through `_render_hyperlink(value, hyperlink_href,
     mode=mode, allowed_schemes=allowed_schemes,
     cell_addr=cell_addr)`.
  3. Else convert `value` to text:
     - `mode == "gfm"`: apply `_escape_pipe_gfm` then
       `_newlines_to_br` (then any other GFM-specific text
       transforms).
     - `mode == "html"`: apply `_escape_html_entities` then
       `_newlines_to_br`.
  4. If `include_formulas` and `formula is not None`: the formula
     is consumed by the HTML emitter via a separate `data-formula`
     attr path (NOT injected here). This branch returns the cached
     value text; the formula attribute is handled by
     `emit_html._format_cell_html`.

#### File: `skills/xlsx/scripts/xlsx2md/emit_gfm.py`

**Function `emit_gfm_table(table_data, out, *, gfm_merge_policy,
hyperlink_allowlist, cell_addr_prefix="") -> None`:**

- Replace stub. Writes header row + `|---|` separator + body
  rows to `out` (a writable text stream).
- Skeleton:
  ```text
  headers = list(table_data.headers)
  # Multi-row detection: if any header contains " › " separator
  is_multi_row = any(" › " in h for h in headers)
  if is_multi_row:
      warnings.warn(
          f"Table {table_data.region.name or table_data.region.sheet!r} "
          f"has multi-row header; GFM output flattened with ' › ' "
          f"separator",
          UserWarning,
          stacklevel=2,
      )

  rows = list(table_data.rows)
  # Apply merge policy (raises GfmMergesRequirePolicy if fail+merges;
  # raise-site lives in emit_hybrid.select_format BEFORE this is
  # called for `--format gfm` — but defensively check here too).
  rows = _apply_gfm_merge_policy(
      rows, table_data.region, gfm_merge_policy,
  )

  _emit_header_row_gfm(headers, out)
  hyperlinks_map = _build_hyperlinks_map(table_data)
  for r_idx, row in enumerate(rows):
      _emit_body_row_gfm(
          row, r_idx, hyperlinks_map, headers,
          out=out, allowed_schemes=hyperlink_allowlist,
          cell_addr_prefix=cell_addr_prefix,
      )
  ```

**Function `_emit_header_row_gfm(headers, out) -> None`:**

- Write `| h1 | h2 | ... |` line + `|---|---|...|` separator line
  (one `---` per column).
- Headers themselves are passed through `_escape_pipe_gfm` to
  protect against literal `|` inside the (flattened) header
  string.

**Function `_emit_body_row_gfm(row, r_idx, hyperlinks_map, headers,
*, out, allowed_schemes, cell_addr_prefix) -> None`:**

- For each cell:
  - Look up hyperlink (if any) from `hyperlinks_map.get((r_idx,
    c_idx))`.
  - Compute `cell_addr = cell_addr_prefix + col_letter(c_idx) +
    str(r_idx + offset)` (offset depends on header band length;
    pass through table_data.region.top_row).
  - Call
    `inline.render_cell_value(cell, mode="gfm",
    hyperlink_href=hl_href, allowed_schemes=allowed_schemes,
    cell_addr=cell_addr)`.
- Write `"| " + " | ".join(cell_strs) + " |\n"`.

**Function `_apply_gfm_merge_policy(rows, region, policy) -> list[list[Any]]`:**

- For `policy == "fail"`: if `region.merges` (or equivalent — see
  note below) is non-empty in the body band, raise
  `GfmMergesRequirePolicy`. Note: `TableData` does NOT carry a
  merges attribute directly; xlsx-9 detects merges via the
  presence of `None`-typed body cells that the library already
  resolved via `merge_policy="anchor-only"` — that is, the
  emitter cannot retroactively detect merges without re-reading.
  - Solution: this raise-site is **moved to `emit_hybrid.select_format`**
    (012-06) which has access to the `TableRegion` + can query
    `TableData.warnings` or a new helper. The `_apply_gfm_merge_policy`
    function here handles ONLY the `duplicate` / `blank`
    transformations.
- For `policy == "duplicate"`: copy anchor cell value into all
  cells in a merge span (horizontal + vertical). Emit
  `summary.warnings` count (via `warnings.warn`).
- For `policy == "blank"`: leave child cells empty. Emit
  `warnings.warn` count.
- Determining merge spans without `TableData.merges`: re-build
  from `region.merges` IF that attribute is added to xlsx_read
  (it is NOT, per current xlsx-10.A API). Alternative: the
  library resolves merges via `merge_policy` parameter to
  `read_table`. xlsx-9 passes `merge_policy="anchor-only"` (D2
  baseline; matches GFM-fail-default), so child cells of body
  merges are `None`. For `duplicate` / `blank`:
  - Determine "merge presence" by inspecting `None` cells in
    rows: a contiguous run of `None` after a non-None anchor in
    the same row is a horizontal merge span.
  - For `duplicate`: replace `None` with the anchor's value.
  - For `blank`: leave `None` as `""` (already empty).
- Honest-scope: a cell explicitly set to `None` in the source
  (not a merge child) is indistinguishable. This is a documented
  emit-side limitation; xlsx-3 round-trip is unaffected because
  duplicate-policy is opt-in.
- A cleaner solution: 012-03 attaches `region.merges_in_body:
  list[tuple[anchor_r, anchor_c, span_r, span_c]] | None` to a
  side-channel on `TableData` (e.g. `table_data.warnings`
  metadata). For v1, the heuristic `None`-run approach above is
  acceptable; document in module docstring.

### New Files

#### `skills/xlsx/scripts/xlsx2md/tests/test_emit_gfm.py`

Unit tests for `emit_gfm.emit_gfm_table` + `_apply_gfm_merge_policy`
+ `_emit_header_row_gfm` (≥ 10 tests per TASK §5.2).

#### `skills/xlsx/scripts/xlsx2md/tests/test_inline.py`

Unit tests for `inline.*` (≥ 10 tests):
1. `_escape_pipe_gfm` escapes `|` → `\|`.
2. `_newlines_to_br` joins lines with `<br>` (no trailing).
3. `_render_hyperlink` GFM allowed scheme emits `[text](url)`.
4. `_render_hyperlink` HTML allowed scheme emits `<a href>`.
5. `_render_hyperlink` empty scheme treated as `http`.
6. `_render_hyperlink` `javascript:` blocked → plain text +
   warning.
7. `_render_hyperlink` `'*'` (None sentinel) allows
   `javascript:`.
8. `_render_hyperlink` `frozenset()` (empty) blocks
   `https://`.
9. `_render_hyperlink` case-insensitive scheme match
   (`HTTPS` allowed).
10. `_render_hyperlink` empty value `""` produces `[](url)`
    (GFM) and `<a href="url"></a>` (HTML).

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/cell_with_pipe.xlsx`

Hand-built: single sheet, single cell `A2 = "a|b|c"`. Used for
pipe-escape regression.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/cell_with_newline.xlsx`

Hand-built: single cell `A2 = "first line\nsecond line"`
(`ALT+ENTER`). Used for `<br>` regression + UC-12 round-trip.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/hyperlink_various_schemes.xlsx`

Hand-built: 4 cells with hyperlinks of different schemes:
`https://ok.com`, `mailto:x@y`, `javascript:alert(1)`,
`ftp://archive.org`. Used by R10a regression cluster.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/multi_row_header_gfm.xlsx`

Hand-built: 2-row header (`"2026 plan"` merged across cols A-C
in row 1; `"Q1"`, `"Q2"`, `"Q3"` in row 2) + 3 data rows. Used
for UC-05 GFM ` › ` flatten.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/two_row_horizontal_merge.xlsx`

Hand-built: 1 sheet, 1 header row, body row with cols B+C merged
(`"Total"`). Used by `--gfm-merge-policy duplicate`/`blank`/`fail`
tests.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/synthetic_header_listobject.xlsx`

Same as `listobject_header_zero.xlsx` from 012-03 (or symlink).
Used by GFM synthetic-header tests.

## Test Cases

### E2E Tests (binding TASK §5.1 slugs)

| # | Slug | Fixture | Assertion | Expected exit |
| --- | --- | --- | --- | --- |
| 1 | `T-single-sheet-gfm-default` | `single_cell.xlsx` (012-02) | `python3 xlsx2md.py single_cell.xlsx --format=gfm` → stdout matches `| col1 |\n|---|\n| hello |\n` (or, with the no-header-flag default `--header-rows=auto`, single-row header detection treats row 1 as header). | 0 |
| 11 | `T-multi-row-header-gfm-u203a-flatten` | `multi_row_header_gfm.xlsx` | `python3 xlsx2md.py multi_row_header_gfm.xlsx --format=gfm` → header row contains ` › ` (U+203A) separator; stderr contains `"multi-row header"` warning. | 0 |
| 12 | `T-hyperlink-gfm-url-form` | `hyperlink_various_schemes.xlsx` | `python3 xlsx2md.py hyperlink_various_schemes.xlsx --format=gfm` → output contains `[text](https://ok.com)`. | 0 |
| 23 | `T-gfm-merge-policy-duplicate` | `two_row_horizontal_merge.xlsx` | `python3 xlsx2md.py two_row_horizontal_merge.xlsx --format=gfm --gfm-merge-policy=duplicate` → second cell contains anchor value `"Total"`; stderr warning emitted. | 0 |
| 31 | `T-hyperlink-allowlist-blocks-javascript-gfm` | `hyperlink_various_schemes.xlsx` | `--format=gfm` → output for `javascript:` cell is plain text `"text"` (NOT `[text](javascript:...)`); stderr warning emitted. | 0 |
| 32 | `T-hyperlink-allowlist-default-passes-https-mailto` | `hyperlink_various_schemes.xlsx` | `--format=gfm` (default allowlist) → `https://ok.com` AND `mailto:x@y` cells emit full link form; `javascript:` AND `ftp://` blocked. | 0 |
| 33 | `T-hyperlink-allowlist-custom-extends` | `hyperlink_various_schemes.xlsx` | `--format=gfm --hyperlink-scheme-allowlist=http,https,mailto,ftp` → `ftp://` cell emits link form; `javascript:` still blocked. | 0 |

### Unit Tests

In `test_emit_gfm.py` (≥ 10 tests per TASK §5.2):

1. **TC-UNIT-01** `test_emit_gfm_single_row_header_two_data_rows`.
2. **TC-UNIT-02** `test_emit_gfm_pipe_escape_in_cell`.
3. **TC-UNIT-03** `test_emit_gfm_newline_to_br_in_cell`.
4. **TC-UNIT-04** `test_emit_gfm_hyperlink_inline_form` (mock
   TableData with hyperlink href).
5. **TC-UNIT-05** `test_emit_gfm_multi_row_header_flatten_with_u203a`.
6. **TC-UNIT-06** `test_emit_gfm_multi_row_header_emits_warning_to_stderr`.
7. **TC-UNIT-07** `test_emit_gfm_synthetic_header_visible_row_plus_separator`.
8. **TC-UNIT-08** `test_emit_gfm_merge_policy_duplicate_repeats_anchor`.
9. **TC-UNIT-09** `test_emit_gfm_merge_policy_blank_leaves_empty`.
10. **TC-UNIT-10** `test_emit_gfm_separator_row_has_correct_column_count`.
11. **TC-UNIT-11** `test_emit_gfm_empty_table_body_only_emits_header_plus_separator`.
12. **TC-UNIT-12** `test_emit_gfm_hyperlink_blocked_scheme_emits_plain_text`.

In `test_inline.py` (10 tests as listed above; supplements
TASK §5.2 by adding the shared-helper coverage).

### Regression Tests

- 5-line `diff -q` silent gate.
- 012-01 + 012-02 + 012-03 tests still green; smoke E2E updated
  to assert GFM emit produces non-empty markdown for
  `single_cell.xlsx`.
- `ruff check skills/xlsx/scripts/` green.
- Existing xlsx test suites unchanged.

## Acceptance Criteria

- [ ] `emit_gfm.emit_gfm_table` implemented per ARCH §2.1 F4.
- [ ] `inline.render_cell_value` central dispatcher implemented
      per ARCH §2.1 F6.
- [ ] `inline._render_hyperlink` implements scheme-allowlist
      filter with `None` (allow all), `frozenset()` (block all),
      and the default 3-scheme set; case-insensitive; empty
      scheme treated as `http`.
- [ ] Hyperlink GFM emit: allowed → `[text](url)`; blocked →
      plain text + `UserWarning`.
- [ ] Hyperlink HTML emit: allowed → `<a href="...">...</a>`;
      blocked → plain text + `UserWarning`. (HTML wiring is
      verified in 012-05; the helper is correct here.)
- [ ] Multi-row header (` › ` in any header string) → GFM
      flatten emit + warning.
- [ ] Pipe `|` in cell → `\|` escape.
- [ ] Newline `\n` in cell → `<br>`.
- [ ] Synthetic header `headerRowCount=0` → visible
      `| col_1 | col_2 | ... |` row + separator row (UC-11 GFM
      half).
- [ ] `--gfm-merge-policy duplicate` repeats anchor value into
      child cells + warning.
- [ ] `--gfm-merge-policy blank` leaves child cells empty +
      warning.
- [ ] 7 E2E test slugs above passing.
- [ ] ≥ 22 unit tests passing (12 + 10).
- [ ] 012-01..012-03 tests still green; smoke updated.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] 5-line `diff -q` silent gate green.
- [ ] No changes to `xlsx_read/`, `office/`,
      `_errors.py`, `_soffice.py`, `preview.py`,
      `office_passwd.py`, `xlsx2csv2json/`, `json2xlsx/`,
      `md_tables2xlsx/`.

## Stub-First Gate Update

The 012-01..012-03 smoke E2E is updated per
`tdd-stub-first §2.4`:

- For `single_cell.xlsx`, `python3 xlsx2md.py single_cell.xlsx
  --format=gfm` now produces a real GFM table with one column +
  one data row (was: empty output in 012-03).
- The pipe-escape, newline-to-`<br>`, hyperlink unit tests in
  this task assert real behaviour for the FIRST TIME (stubs in
  012-01 had no escape logic).

## Notes

- **Hybrid format selector** (012-06) decides when to call
  `emit_gfm_table` vs `emit_html_table` — this task implements
  the GFM half only. Hybrid orchestration is OUT OF SCOPE here.
- **`GfmMergesRequirePolicy` raise-site** lives in 012-06
  (`emit_hybrid.select_format` / `emit_workbook_md`) because
  the format decision happens upstream. `_apply_gfm_merge_policy`
  here handles the `duplicate` and `blank` transforms only.
- **Cell address for warnings:** the `cell_addr` param of
  `_render_hyperlink` is best-effort. If the emit-side cannot
  compute the precise letter-row form (e.g. inside multi-row
  header flatten), the warning falls back to the generic
  "hyperlink scheme {scheme!r} not in allowlist" form. Tests
  assert the warning fires, not the exact text.
- **`urllib.parse.urlsplit`** is preferred over `urlparse`
  because it handles `mailto:` and other non-authority schemes
  correctly without `netloc` munging.
- **Multi-row header detection heuristic:** ` › ` (U+203A with
  surrounding spaces) is the locked separator (D6). Any header
  string containing this substring triggers the multi-row
  detection. A workbook with literal U+203A in headers (no
  multi-row intent) will be misdetected — this is the A-A3
  honest scope (ARCH §10 A-A3). Documented in module docstring.
- **No external deps** added. `html`, `urllib.parse`, `warnings`
  are stdlib.

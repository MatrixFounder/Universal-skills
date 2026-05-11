# Task 005.06: `tables.py` — GFM pipe parser + HTML `<table>` parser (F3+F4)

## Use Case Connection
- UC-1 (HAPPY PATH) — GFM pipe parsing.
- UC-3 (HTML `<table>` with colspan/rowspan).
- R2 (full sub-features); R3 (full sub-features); R9.c, R9.h (locks).

## Task Goal

Implement both table parsers in one module per ARCH §3.2. The
module-level `_HTML_PARSER` singleton was already constructed in
005.01; this task ADDS the actual `lxml.html.fragment_fromstring`
invocation and the `_expand_spans` colspan/rowspan logic.

After this task, the following E2E cases turn GREEN (assuming
005.08 writer + 005.09 orchestrator):

- `T-happy-gfm` — 3-table fixture extracts to 3 `RawTable` instances.
- `T-happy-html` — HTML `<table>` with colspan extracts merged-cell ranges.
- The HTML billion-laughs DoS test passes (M1 regression lock).

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/md_tables2xlsx/tables.py`

**Module-level (already from 005.01):**

```python
_HTML_PARSER = lxml.html.HTMLParser(
    no_network=True,
    huge_tree=False,
    recover=True,
)
```

**Public dispatcher (ARCH m2 review-fix):**

```python
def parse_table(block: Block) -> RawTable | None:
    """Dispatcher — cli.py orchestrator calls just this."""
    if isinstance(block, PipeTable):
        return parse_pipe_table(block)
    if isinstance(block, HtmlTable):
        return parse_html_table(block)
    raise TypeError(f"Unexpected Block type: {type(block).__name__}")
```

**`parse_pipe_table(block: PipeTable) -> RawTable | None`:**
- First line: header row → call `_split_row(line)`.
- Second line: separator → `_parse_alignment_marker(sep_line, n_cols)`. If column count mismatch with header → emit single-line stderr warning (`f"warning: pipe table at line {block.line}: column count mismatch (header={n_header}, sep={n_sep}); skipping"`), return `None`.
- Remaining lines: data rows. Each row split via `_split_row`. Cells stripped via `strip_inline_markdown` (from `inline.py`). If row has too-few cells, pad with `None`; if too-many, truncate.
- Return `RawTable(header=cells, rows=[[...]], alignments=[...], merges=[], source="gfm", source_line=block.line)`.

**`parse_html_table(block: HtmlTable) -> RawTable`:**
- Parse fragment: `fragment = lxml.html.fragment_fromstring(block.fragment, create_parent=False, parser=_HTML_PARSER)`.
- `rows_with_spans = []`; for each `<tr>` element via `_walk_rows`:
  - For each `<th>` / `<td>` child: `text = (cell.text_content() or "").strip()`; `colspan = int(cell.get("colspan", 1))`; `rowspan = int(cell.get("rowspan", 1))`.
  - Strip inline markdown / `<br>` / entities via `strip_inline_markdown`.
- Pass `rows_with_spans` through `_expand_spans` → produces rectangular grid + `list[MergeRange]`.
- Header row: first row from `<thead>` if present, else first row from `<tbody>` (or root children).
- Return `RawTable(...)` with `source="html"`.

**Helpers:**

- `_split_row(line: str) -> list[str]`: handle `|` boundaries + `\|` escapes:
  - Strip leading `|` and trailing `|` if present.
  - Walk char-by-char; `\|` → literal `|`, `|` → cell boundary.
  - Strip each cell's whitespace.
- `_parse_alignment_marker(sep_line: str, n_cols: int) -> list[Alignment]`:
  - Split sep_line on `|`.
  - For each segment: `re.match(r"^\s*(:?)-+(:?)\s*$", seg)`. Left `:` and right `:` determine alignment.
  - Return list of `"left"`, `"right"`, `"center"`, or `"general"`.
- `_walk_rows(table_el) -> Iterator[lxml.html.HtmlElement]`:
  - If `<thead>` present: yield rows from `<thead>` first, then `<tbody>` (and direct `<tr>` children if no tbody).
  - Else: yield rows in document order.
- `_expand_spans(rows: list[list[tuple[str, int, int]]]) -> tuple[list[list[str | None]], list[MergeRange]]`:
  - Initialise empty grid; iterate row-by-row.
  - For each cell `(text, colspan, rowspan)`: find next free column in current row, write `text` there, mark `colspan-1` cells to its right + `rowspan-1` cells below as "occupied by this anchor".
  - Build `MergeRange` per `(colspan, rowspan) != (1, 1)` cell, with **1-indexed** start/end row/col where row 1 = header (ARCH m9 boundary conversion).
  - Return `(grid, merges)`.

### Component Integration

Public surface: `parse_table` (dispatcher), `parse_pipe_table`,
`parse_html_table`, `RawTable`, `MergeRange`. Consumed by `cli.py`
(005.09) orchestrator. Imports `Block`, `PipeTable`, `HtmlTable`
from `loaders` (or wherever they live — see 005.04 note).

## Test Cases

### End-to-end Tests

- (E2E green is gated on writer + orchestrator; this task makes them parser-side correct.)

### Unit Tests

**TestPipeParser:**

1. **TC-UNIT-01 (test_basic_pipe_table):** `| a | b |\n|---|---|\n| 1 | 2 |` → `RawTable(header=["a","b"], rows=[["1","2"]], alignments=["general","general"], merges=[], source="gfm")`.
2. **TC-UNIT-02 (test_alignment_markers):** `|---|---:|:--:|` → `["left", "right", "center"]`.
3. **TC-UNIT-03 (test_escaped_pipe_in_cell):** `| a \| b | c |` → first cell is `"a | b"`.
4. **TC-UNIT-04 (test_column_count_mismatch_skips):** Header has 3 cols, separator has 2 → `parse_pipe_table` returns `None` and stderr has warning.
5. **TC-UNIT-05 (test_inline_strip_in_cell):** `| **bold** | _italic_ |` → header == `["bold", "italic"]`.
6. **TC-UNIT-06 (test_trailing_pipe_optional):** Both `| a | b |` and `a | b` accepted.
7. **TC-UNIT-07 (test_zero_data_rows_kept):** Header + separator only, no body → `RawTable(rows=[])` (header-only is valid; R10.c lock).

**TestHtmlParser:**

1. **TC-UNIT-08 (test_basic_html_table):** `<table><tr><th>a</th></tr><tr><td>1</td></tr></table>` → `RawTable(header=["a"], rows=[["1"]], merges=[])`.
2. **TC-UNIT-09 (test_thead_tbody_split):** `<table><thead><tr><th>h</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>` → header from `<thead>`.
3. **TC-UNIT-10 (test_colspan_rowspan):** `<table><tr><td colspan="2">A</td></tr><tr><td>1</td><td>2</td></tr></table>` → 1 `MergeRange(start_row=1, start_col=1, end_row=1, end_col=2)`; first-row second cell is `None`.
4. **TC-UNIT-11 (test_rowspan_only):** `<table><tr><td rowspan="2">A</td><td>B</td></tr><tr><td>C</td></tr></table>` → `MergeRange(1,1,2,1)`; second-row first cell is `None`.
5. **TC-UNIT-12 (test_html_entity_decode):** `<td>a &amp; b</td>` → cell value `"a & b"`.
6. **TC-UNIT-13 (test_html_lxml_lenient_malformed_recovery):** `<table><tr><td>x</tr></table>` (missing `</td>`) — `lxml.html` auto-closes; parser still returns a valid `RawTable` with one cell. (TASK m4 review-fix.)
7. **TC-UNIT-14 (TestHonestScopeLocks::test_html_billion_laughs_neutered):** Synthetic 100-level nested entity payload → wall-clock ≤ 100 ms AND `parse_html_table` returns successfully. ALSO asserts `_HTML_PARSER.no_network is True` (ARCH M1 lock — parser-instance pin, not just runtime measure).
8. **TC-UNIT-15 (TestHonestScopeLocks::test_html_parser_no_huge_tree):** `_HTML_PARSER.options` does NOT have the HUGE_TREE bit set. (ARCH M1.)
9. **TC-UNIT-16 (TestHonestScopeLocks::test_gfm_no_colspan_support):** GFM table with literal text `colspan=2` in a cell → just a text cell; no merge range emitted. R9.c lock — colspan/rowspan are HTML-only.

**TestParserDispatch:**

1. **TC-UNIT-17 (test_parse_table_dispatches_pipe):** Pass a `PipeTable` block → `parse_table` returns a `RawTable` with `source="gfm"`.
2. **TC-UNIT-18 (test_parse_table_dispatches_html):** Pass a `HtmlTable` block → `source="html"`.
3. **TC-UNIT-19 (test_parse_table_unknown_block_raises):** Pass a `Heading` block → `TypeError`.

### Regression Tests

- Existing tests pass.
- `loaders.iter_blocks` output is consumed correctly (no API drift).

## Acceptance Criteria

- [ ] All 19 unit tests pass.
- [ ] `_HTML_PARSER` is a module-level singleton (NOT constructed per call).
- [ ] `test_html_billion_laughs_neutered` (TC-UNIT-14) asserts BOTH wall-clock AND parser-instance attributes.
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] Eleven `diff -q` cross-skill replication checks silent.

## Notes

`_expand_spans` is the trickiest helper — pathological cases
(overlapping `colspan`/`rowspan` that don't form a regular grid)
should produce best-effort output with a non-fatal warning. The
"first valid merge wins" tie-breaker is the contract; openpyxl's
`merge_cells` raises `ValueError` on overlap, which is caught in
005.08 writer.py (R9.h lock).

The TC-UNIT-14 billion-laughs lock is the **prime ARCH M1
regression test**. If a future maintainer changes `_HTML_PARSER`
construction (e.g., flips `huge_tree=True` for "performance"), this
test catches it on next CI run.

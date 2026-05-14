# Markdown ↔ XLSX Round-Trip Contract (xlsx-9 ↔ xlsx-3)

> **Status:** **FROZEN** as of xlsx-9 v1 merge (Task 012).
> **Owners:**
> - xlsx-9 (`xlsx2md.py`) — producer of Markdown from `.xlsx`.
> - xlsx-3 (`md_tables2xlsx.py`) — producer of `.xlsx` from Markdown.
> **Goal:** unambiguous round-trip contract between Markdown shape and
> `.xlsx` workbook structure for the "read my spreadsheet as Markdown →
> edit → write it back" loop.
>
> xlsx-3's implementation **MUST** consume this spec unchanged. If
> xlsx-9 discovery work surfaces a requirement that forces a revision,
> both skills update synchronously in the same commit (see ARCH §3.2 C6
> and the m4 lock for the equivalent xlsx-2/xlsx-8 pair).

---

## §1 Scope

This document is the **single source of truth** for the Markdown shape
contract shared between xlsx-9 (`xlsx2md`) and xlsx-3 (`md_tables2xlsx`).
Both implementations parse / emit Markdown according to the same rules so
a clean round-trip is possible.

**Document structure emitted by xlsx-9 (ARCH §2.1 F3):**

```
## <Sheet name>           ← one H2 per worksheet (verbatim name)

### <Table name>          ← one H3 per table region (ListObject name, or
                            "Table-N" for gap-detected regions)

<GFM or HTML table block> ← format selected per §4 hybrid rules
```

Sheets are emitted in workbook tab order. Multiple table regions per
sheet each get their own H3 + table block. The `--no-split` flag
suppresses the H3 headings (ARCH §2.1 F3 note).

In scope:
- Two table emit shapes: GFM pipe-table (§2) and HTML `<table>` (§3).
- Per-table format selection via hybrid mode (§4).
- Inline contract shared by both shapes (§5).
- Sheet-name asymmetry between xlsx-9 and xlsx-3 (§6, D9 lock).
- Round-trip limitations — honest scope per TASK 012 §1.4 (§7).
- Live round-trip test activation mechanism (§8).

Out of scope (xlsx-9 v1; tracked separately):
- Cell-level formatting round-trip (fonts, colours, alignment, borders).
- Comment round-trip (v2 sidecar; tracked as xlsx-6 parity).
- Chart / image / shape preservation.
- Pivot table live data (static cached values only).

---

## §2 GFM Shape

xlsx-9 emits a GFM [pipe-table](https://github.github.com/gfm/#tables-extension-)
when the table passes all four hybrid promotion rules with no promotion
(see §4). Cross-reference: ARCH §2.1 F4 (`emit_gfm.py`), TASK R2.c,
R10, R16.

### §2.1 Single-row header (common case)

```text
| h1 | h2 | h3 |
|---|---|---|
| v1 | v2 | v3 |
| v4 | v5 | v6 |
```

- Header row is the first row of the table region (`headerRowCount=1`).
- Separator row uses `---` alignment markers (no leading/trailing
  colons unless alignment info is present). Minimum 3 dashes per cell.
- Each data row follows immediately. Empty cells appear as `||` (two
  adjacent pipes with no content between them after trimming).

### §2.2 Multi-row header — degraded with ` › ` flatten

When the workbook has a multi-row header (merged cells spanning header
rows), xlsx-9 **flattens** the header to a single row using the
U+203A RIGHT SINGLE QUOTATION MARK separator (` › `), and emits a
`UserWarning` on stderr. Cross-reference: ARCH §2.1 F4, D-A11.

```text
| 2026 plan › Q1 | 2026 plan › Q2 |
|---|---|
| 100 | 200 |
```

xlsx-3 reads these as literal header strings (the ` › ` character
becomes part of the column name). This is a **lossy** degradation —
the multi-row structure is NOT reconstructed by xlsx-3 on write-back.
The document round-trip is cell-content-preserving but NOT
header-structure-preserving for multi-row headers.

### §2.3 Synthetic header for `headerRowCount=0`

When the table region has no header row (`headerRowCount=0`), xlsx-9
emits synthetic column names `col_1`, `col_2`, …, `col_N` as the GFM
header row, and emits a `UserWarning`. Cross-reference: ARCH D13,
TASK §1.4 (i), TASK R12.c.

```text
| col_1 | col_2 | col_3 |
|---|---|---|
| raw1  | raw2  | raw3  |
```

The synthetic headers are **visible in the output** — not commented or
suppressed. Downstream consumers must treat `col_N` as a sentinel for
"no original header". xlsx-3 writes these column names verbatim as the
header row.

### §2.4 Pipe `\|` escape

A literal `|` character inside a cell value is escaped to `\|` in GFM
output. Cross-reference: ARCH §2.1 F4, TASK R10.

```text
| A \| B | C |
|---|---|
| x \| y | z |
```

xlsx-3 unescapes `\|` back to `|` during parse
(`inline.strip_inline_markdown` step).

### §2.5 Newline `<br>`

A literal `\n` (ALT+ENTER) inside a cell value is replaced with `<br>`
in GFM output. Cross-reference: ARCH §2.1 F4, TASK R16, TASK 012-07
UC-12.

```text
| Note |
|---|
| first line<br>second line |
```

xlsx-3 R9.c converts `<br>` back to `\n` in the cell value on
write-back (via `inline.strip_inline_markdown` → `<br>` → `\n`
transformation). This is the **lossless path** for the newline
round-trip — cell content is byte-identical after one full cycle.

### §2.6 Hyperlink `[text](url)`

A cell containing a hyperlink with an allowed scheme is emitted as a
GFM inline link. Cross-reference: ARCH §2.1 F4, TASK R10, D-A15.

```text
| [click here](https://example.com) |
```

Scheme allowlist (default): `http`, `https`, `mailto`. A hyperlink
whose scheme is NOT in the allowlist is emitted as plain text (the
display text only, no link), with a `UserWarning` on stderr.

xlsx-3 reads `[text](url)` as plain text (the URL is stripped by
`inline.strip_inline_markdown`). **Hyperlinks are NOT round-trippable
through GFM in xlsx-3 v1** — the URL is lost on write-back.

---

## §3 HTML Shape

xlsx-9 emits an HTML `<table>` block when the table is promoted to HTML
by the hybrid mode selector (see §4). Cross-reference: ARCH §2.1 F5
(`emit_html.py`), TASK R2.d, R11, R14, R18.

### §3.1 Basic structure

```html
<table>
<thead>
<tr><th>h1</th><th>h2</th></tr>
</thead>
<tbody>
<tr><td>v1</td><td>v2</td></tr>
</tbody>
</table>
```

- `<thead>` contains the header row(s).
- `<tbody>` contains data rows.
- Cell content is `html.escape(text)` — HTML special characters are
  entity-encoded (`&`, `<`, `>`, `"` → `&amp;`, `&lt;`, `&gt;`,
  `&quot;`). Cross-reference: ARCH §4 (security table).

### §3.2 Multi-row `<thead>` reconstruction

When a multi-row header was flattened with ` › ` separators by
`xlsx_read`, xlsx-9's `headers.py` reconstructs the multi-row
`<thead>` by splitting each header string on ` › ` and grouping
header cells into N `<tr>` rows, with `colspan` spans computed per
column group. Cross-reference: ARCH D-A11, ARCH §3.2 `headers.py`.

```html
<thead>
<tr><th colspan="2">2026 plan</th></tr>
<tr><th>Q1</th><th>Q2</th></tr>
</thead>
```

`InconsistentHeaderDepth` is raised if separator counts differ across
columns (D-A11 defensive check).

### §3.3 `colspan` and `rowspan` on merge anchors

Merged cell ranges are emitted as `colspan` / `rowspan` attributes on
the anchor cell. Child cells within the merge are **suppressed**
(not emitted as `<td></td>`). Cross-reference: ARCH §2.1 F5, TASK R11.

```html
<tr><td colspan="2">merged</td></tr>
<tr><td>a</td><td>b</td></tr>
```

### §3.4 `data-formula` attribute

When `--include-formulas` is active, formula cells carry a
`data-formula` attribute containing the formula string (escaped with
`html.escape(formula, quote=True)`). Cross-reference: ARCH §4.

```html
<td data-formula="=SUM(A1:A3)">42</td>
```

### §3.5 `class="stale-cache"` for formula with no cached value

If a formula cell has no cached value (the workbook was saved without
recalculation), xlsx-9 emits an empty `<td>` with
`class="stale-cache"`. Cross-reference: ARCH §2.1 F5.

```html
<td class="stale-cache" data-formula="=VLOOKUP(A1,B:C,2)"></td>
```

### §3.6 Hyperlinks `<a href>`

A hyperlink cell with an allowed scheme is emitted as `<a href="...">text</a>`.
Both the text and URL are escaped:
- Text: `html.escape(display_text)`.
- URL: `html.escape(url, quote=True)` for the `href` attribute.

Cross-reference: ARCH §4 (security table, hyperlink injection row),
ARCH D-A15, TASK R10a.

```html
<td><a href="https://example.com">click here</a></td>
```

Scheme not in allowlist → plain text emitted (no `<a>` tag), plus
`UserWarning`. This is the **Sec-MED-2** mitigation applied at design
time for xlsx-9 (higher attack surface than xlsx-8's JSON key output).

### §3.7 Synthetic `<thead>` for `headerRowCount=0`

When `headerRowCount=0`, xlsx-9 emits synthetic `col_1..col_N` headers
in `<thead>`. Cross-reference: ARCH D13, TASK §1.4 (i).

```html
<thead>
<tr><th>col_1</th><th>col_2</th></tr>
</thead>
```

---

## §4 Hybrid Mode

xlsx-9's `emit_hybrid.py` (`F3`) selects the output format on a
per-table basis. Cross-reference: ARCH §2.1 F3, TASK R2.e, R12.

Four promotion rules are evaluated in order. The first match selects
HTML; if no rule matches, GFM is selected:

| Rule | Condition | Promoted to |
| :--- | :--- | :--- |
| Rule 1 | Table body has ≥ 1 merged cell range | HTML |
| Rule 2 | Header has ≥ 2 rows (multi-row header) | HTML |
| Rule 3 | `--include-formulas` flag AND table has ≥ 1 formula cell | HTML |
| Rule 4 | `headerRowCount=0` (synthetic headers) | HTML (D13) |
| — | None of the above | GFM |

The `--format gfm` and `--format html` flags **override** the hybrid
selector for all tables. Specifying `--format gfm` with a table that
has body merges raises `GfmMergesRequirePolicy` (exit 2) unless
`--gfm-merge-policy` is also set.

---

## §5 Inline Contract

The following transformations apply to **both** GFM and HTML output
(the `inline.py` module, `F6`). Cross-reference: ARCH §2.1 F6.

### §5.1 Cell newline `\n` → `<br>`

Embedded newline characters (Excel ALT+ENTER) become `<br>` in the
output. This applies in both GFM cell values and HTML `<td>` text nodes.

**Lossless on xlsx-3 round-trip (TASK R9.c):** xlsx-3's
`inline.strip_inline_markdown` converts `<br>` back to `\n` in the
cell value. Cell content is byte-identical before and after one full
`xlsx2md → md_tables2xlsx` cycle (UC-12).

### §5.2 Pipe `|` → `\|` (GFM) / `&#124;` (HTML)

A literal pipe character in cell content is escaped to prevent
GFM column-boundary confusion or HTML attribute injection.
- GFM: escaped to `\|` by `_escape_pipe_gfm`.
- HTML: `html.escape` converts `|` to itself (pipe is not an HTML
  special character), but the HTML context is safe because cells
  are always inside `<td>` content, not attributes.

### §5.3 Empty cell

An empty cell value (`""` or `None`) becomes:
- GFM: `||` (two adjacent pipes with no content between them).
- HTML: `<td></td>` (empty element, no whitespace inside).

### §5.4 Hyperlink scheme allowlist

The allowlist is applied to all hyperlink emissions (GFM and HTML).
Default: `{http, https, mailto}`. Configurable via
`--hyperlink-scheme-allowlist` (D-A15 / Sec-MED-2). Cross-reference:
ARCH §4 (security table).

---

## §6 Sheet-Name Asymmetry (D9 Lock)

> **This is EXPECTED behaviour, NOT a regression.**
> Cross-reference: ARCH D9, ARCH §10 Q-2, TASK 012-07 §Notes.

xlsx-9 emits sheet names **verbatim** in `## H2` headings — no
sanitisation, no truncation.

xlsx-3's `naming.py` applies Excel sheet-name sanitisation rules on
write-back:
- `History` (case-insensitive) → `History_` (reserved name).
- Names longer than 31 UTF-16 code units → truncated to 31.
- Forbidden characters (`[ ] : * ? / \`) → replaced with `_`.

As a result, a workbook with a sheet named `History` round-tripped
through `xlsx2md → md_tables2xlsx` produces:
1. First pass: `## History` (xlsx-9 emits verbatim).
2. Write-back: xlsx-3 saves as sheet `History_`.
3. Second pass: `## History_` (xlsx-9 emits the new name verbatim).

**Contract assertion:** the live round-trip test
(`TestRoundTripXlsx9::test_live_roundtrip_xlsx_md`) asserts
**cell-content byte-equality** between stages 1 and 3, NOT sheet-name
equality. Sheet-name drift under xlsx-3 sanitisation is accepted and
documented here.

The `_extract_table_bodies()` normaliser in the test strips H2 and H3
lines from both sides of the comparison before asserting equality.

---

## §7 Round-Trip Limitations (Honest Scope)

The following limitations are **deliberately accepted in v1**.
Cross-reference: TASK 012 §1.4 items (a)–(j).

- **(a) Rich-text spans collapse to plain-text concatenation.** A cell
  with bold/italic partial-run formatting emits the concatenated
  plain text; run boundaries and formatting attributes are lost.

- **(b) Cell styles dropped.** Font, background colour, borders,
  number format, and alignment are not encoded in the Markdown output.
  xlsx-3 applies its own default styling on write-back (bold header
  row, light-grey fill, auto-filter, freeze pane).

- **(c) Comments dropped (v2 sidecar).** xlsx-9 v1 does not emit cell
  comments to Markdown. The comment surface belongs to xlsx-6.

- **(d) Charts / images / shapes dropped.** Non-cell content is not
  represented in the Markdown output.

- **(e) Pivot tables → static cached values.** xlsx-9 emits the
  cached cell values from the pivot table cache; live pivot data
  relationships are lost.

- **(f) Data validation dropdowns dropped.** Cell validation rules
  (dropdown lists, numeric constraints) are not emitted.

- **(g) Formula without cached value → empty cell or `data-formula`
  attribute.** If the workbook was saved without recalculation
  (`stale-cache`), the formula cell emits as empty (GFM) or with
  `class="stale-cache"` (HTML). See §3.5.

- **(h) Shared / array formulas → cached value only.** The formula
  string for array/shared formulas is available via `--include-formulas`
  (HTML mode only), but the formula type is not preserved.

- **(i) `headerRowCount=0` → visible synthetic `col_1..col_N` headers.**
  Downstream consumers see `col_N` as literal header names; the
  original header-less structure is not reconstructable. See §2.3 and
  §3.7.

- **(j) Diagonal borders / sparklines / camera objects dropped.**
  These OOXML features have no Markdown representation.

- **Merges un-merge on xlsx-3 write-back.** xlsx-3 v1 does not
  re-merge HTML `colspan`/`rowspan` back into Excel merged cell ranges.
  The anchor cell value is written to an individual cell; sibling cells
  within the original merge are written with their suppressed-but-present
  value (empty string or the anchor's value, depending on the parser
  path). Round-trip un-merges all ranges.

---

## §8 Live Round-Trip Test Activation

Cross-reference: TASK 012-07 §"Changes in Existing Files", ARCH §5.2
task row 012-07.

### §8.1 Gate mechanism

`TestRoundTripXlsx9::test_live_roundtrip_xlsx_md` in
`skills/xlsx/scripts/tests/test_md_tables2xlsx.py` is guarded by:

```python
@unittest.skipUnless(xlsx2md_available(), "xlsx2md not yet implemented")
```

`xlsx2md_available()` performs two probes:
1. `import xlsx2md` must succeed (passes after task 012-01).
2. `convert_xlsx_to_md` on the `single_cell.xlsx` fixture must return
   exit code 0 AND produce non-empty Markdown (passes after task
   012-06).

Before task 012-06, probe (2) fails because `convert_xlsx_to_md` is a
stub (returns 0 but produces empty output). After task 012-06, both
probes pass and the gate flips to live.

### §8.2 What the live test asserts

`test_live_roundtrip_xlsx_md` uses the `roundtrip_basic.xlsx` fixture
(strings, integers, ISO dates — no merges, no formulas, no styles):

```
xlsx → md (stage 1) → xlsx → md (stage 3)
```

Assertion: `_extract_table_bodies(stage1_md) == _extract_table_bodies(stage3_md)`.

The `_extract_table_bodies()` normaliser strips H2 headings and H3
headings from the comparison, asserting only that the **table body
content** (headers + data rows) is byte-identical across the cycle.
Sheet-name drift (§6) is explicitly excluded from the assertion.

### §8.3 Newline round-trip test (`UC-12`)

`test_live_roundtrip_cell_newline_br` uses the `cell_with_newline.xlsx`
fixture and asserts:

1. `xlsx2md(cell_with_newline.xlsx)` → Markdown output contains `<br>`.
2. `md_tables2xlsx(md)` → xlsx; cell A2 reads
   `"first line\nsecond line"` byte-identical (xlsx-3 R9.c converts
   `<br>` → `\n`).

### §8.4 Meta-test

`test_xlsx2md_available_returns_true_after_xlsx9_lands` asserts that
`xlsx2md_available()` returns `True` unconditionally. This is a sanity
check that the gate helper is wired correctly and the round-trip tests
are not silently skipping after the xlsx-9 merge.

---

## §9 Test Contract

Both xlsx-9 and xlsx-3 **MUST** keep these fixtures in sync:

- `skills/xlsx/scripts/xlsx2md/tests/fixtures/roundtrip_basic.xlsx` —
  round-trip-safe multi-cell fixture (strings, integers, ISO dates).
  NO merges, NO formulas, NO styles, NO comments.
- `skills/xlsx/scripts/xlsx2md/tests/fixtures/cell_with_newline.xlsx` —
  single-table fixture with embedded newline in cell A2 (2-column layout
  required for GFM block detection).

The `test_live_roundtrip_xlsx_md` test body performs
`xlsx2md → md_tables2xlsx → xlsx2md` and asserts structural equivalence
per §8.2. If xlsx-9 discovery work requires a revision to this spec,
BOTH skills must update synchronously in the same commit; otherwise the
live round-trip test breaks until parity is restored.

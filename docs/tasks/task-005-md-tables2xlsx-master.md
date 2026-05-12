# Task 005 — xlsx-3 — `md_tables2xlsx.py` (Markdown tables → multi-sheet .xlsx)

> **Backlog row:** `xlsx-3` (`docs/office-skills-backlog.md` §xlsx).
> **Predecessor / sibling:** `csv2xlsx.py` (styling reference, MERGED) and
> `json2xlsx.py` (Task-004, MERGED) — xlsx-3 is the **third** input-shape
> writer in the same converter family. Same `HEADER_FILL` / `HEADER_FONT` /
> `MAX_COL_WIDTH` look-and-feel.
> **Status (2026-05-11):** ✅ **MERGED**. 10-step atomic chain (005.01–005.10)
> + 12-fix `/vdd-multi` Phase-3 pass shipped. Body below is the
> historical Analysis-phase spec — preserved verbatim for design
> traceability. See **§14 Implementation Summary** (end of doc) for
> post-merge actuals (LOC, test counts, fixes, deltas vs spec).

---

## 0. Meta Information

- **Task ID:** `005`
- **Slug:** `md-tables2xlsx`
- **Backlog row:** `xlsx-3` (`docs/office-skills-backlog.md` §xlsx, p.189).
- **Effort estimate:** **S → M** (backlog reads S "извлечь все markdown-
  таблицы из .md"; VDD kick-off Q&A 2026-05-11 widened scope by accepting
  HTML `<table>` blocks alongside GFM pipe tables (D1) and full cross-
  cutting parity (D4). Final LOC estimate: shim ≤ 60 + `md_tables2xlsx/`
  package ~700 LOC + tests ~600 LOC. Strictly below xlsx-2's footprint
  because no JSONL streaming path and no timezone-strict path.
- **Decisions locked from `/vdd-start-feature` Q&A (2026-05-11):**
  - **D1 — Table flavors:** v1 accepts **two** markdown table flavors:
    1. **GFM pipe tables** (CommonMark + GFM extension §5.4): header
       row, `|---|---|` separator, body rows. Per-column alignment
       (`:---`, `---:`, `:---:`) carried into Excel cell horizontal
       alignment (`left` / `right` / `center`).
    2. **HTML `<table>` blocks** parsed via `lxml.html` — recognises
       `<thead>` / `<tbody>` / `<th>` / `<td>` / `<tr>`. `colspan` /
       `rowspan` honoured as Excel merged cells. Tables inside fenced
       code blocks (```` ``` ````) or inside HTML comments (`<!-- -->`)
       are **skipped** (they are code samples / commented-out, not
       data). Tables inside blockquotes (`> | a | b |`) are skipped in
       v1 (rare, ambiguous nesting; honest scope §11.7).
    Out of scope (deferred, honest scope §§11.1–11.2 and §11.7):
    RST grid tables (`+----+----+`), MultiMarkdown extensions
    (col-grouping `||`), PHP-Markdown-Extra table caption
    (`[Caption]`), blockquoted tables (`> | a | b |`).
  - **D2 — Sheet naming (locked algorithm, m3 review-fix):**
    - **Primary rule:** Each table's sheet name is the **nearest
      preceding markdown heading** (`#`/`##`/`###`/`####`/`#####`/`######`)
      OR the nearest preceding HTML heading (`<h1>`–`<h6>`). "Nearest"
      = closest *above* the table in document order.
    - **Fallback:** When no heading precedes the table, name =
      `Table-N` where N is the 1-indexed order of unnamed tables in
      document order (`Table-1`, `Table-2`, … — independent counter
      from the dedup suffix `-2`/`-3` in step 8 below).
    - **Markdown formatting in heading text** (e.g. `## **Bold heading**`
      or `### Heading with `code``) is stripped to plain text BEFORE
      sanitisation (`_strip_inline_markdown` helper, see R5.b).
    - **Sanitisation algorithm (numbered; runs once per table, in this
      exact order — Developer MUST NOT reorder, M3 review-fix):**
      1. Strip inline markdown from heading text → `raw`.
      2. Replace forbidden chars `[ ] : * ? / \` with `_` in `raw`.
      3. Collapse runs of whitespace to single space.
      4. Strip leading / trailing whitespace and `'`.
      5. If empty → set `raw = "Table-N"` (N = 1-indexed counter of
         tables whose pipeline reached step 5 with empty name).
      6. **Truncate to 31 characters** (Excel hard limit; sheet names
         are stored as UTF-16 strings — count UTF-16 code units, NOT
         UTF-8 bytes, m1 review-fix). Call the result `base`.
      7. **Reserved-name guard:** if `base.lower() == "history"`,
         append `_` to `base`, then re-apply step 6 (re-truncate to
         31). Lock: step 7 runs at most once per invocation.
      8. **Workbook-wide dedup (case-insensitive):** maintain
         `used_lower: set[str]` across the whole workbook. If
         `base.lower() in used_lower`:
         - try suffixes `-2`, `-3`, … `-99` in order;
         - for each candidate suffix `S`, form
           `candidate = base[:31 - len(S)] + S` (truncate the prefix,
           keep suffix intact);
         - first `candidate.lower()` not in `used_lower` wins;
         - if all 98 candidates collide → raise `InvalidSheetName`
           (exit 2) with `details: {original: base, retry_cap: 99}`.
      9. Add the winning name's lowercase form to `used_lower` and
         return the winning name.
  - **D3 — Cell coercion:** Default-on auto-coercion mirrors csv2xlsx +
    json2xlsx contract:
    - **Numbers:** strings matching `^-?\d+(?:[.,]\d+)?$` → int or
      float (comma normalised to dot before parse). **Leading-zero
      preservation:** if any non-empty value in the column starts with
      `0` followed by another digit (e.g. `"007"`, `"0123456789"`) →
      whole column kept as text (csv2xlsx parity, see
      `_coerce_column` in `skills/xlsx/scripts/csv2xlsx.py`).
    - **ISO dates:** strings matching `YYYY-MM-DD` → Excel date cell
      (`number_format = "YYYY-MM-DD"`). Strings matching `YYYY-MM-DD
      HH:MM:SS` or `YYYY-MM-DDTHH:MM:SS` → Excel datetime cell
      (`number_format = "YYYY-MM-DD HH:MM:SS"`). Timezone-aware ISO
      strings (`...Z`, `...+02:00`) are coerced to UTC-naive (mirrors
      json2xlsx D7 default-mode, NOT strict-mode; xlsx-3 does NOT ship
      `--strict-dates` in v1 — markdown is human-authored, strict-mode
      footgun outweighs the upside).
    - **Inline markdown in cells:** `**bold**`, `*italic*`, `` `code` ``,
      `[text](url)`, `~~strike~~`, `<br>` → stripped to plain text
      BEFORE coercion. The plain-text result is what gets coerced /
      written. `<br>` becomes a literal `\n` in the cell value
      (Excel renders if `wrap_text=True`; see honest scope §11.3 for
      v1 non-wrap policy).
    - **Empty cell:** GFM pipe `||` or HTML `<td></td>` → openpyxl
      `None` (Excel blank cell), NOT empty string `""`.
    - **Opt-out:** `--no-coerce` → every cell is forced to `str` with
      `number_format = "@"` (text). Useful when the markdown table is
      a config / changelog where `2024.01` is a version, not a number.
  - **D4 — Cross-cutting parity (full):**
    - **cross-5** `--json-errors` envelope (`{v:1, error, code, type,
      details}`) via `add_json_errors_argument` / `report_error` from
      `_errors.py`. Argparse usage errors route through the envelope
      (`type:"UsageError"`).
    - **cross-7 H1** same-path guard (xlsx-skill internal label;
      "H1" = first hardening pass landed across the office-skill
      family — same wording in xlsx-2/xlsx-6/xlsx-7): input path and
      output path resolved via `Path.resolve()` (follows symlinks);
      identical resolved path → exit 6 `SelfOverwriteRefused`. Input
      `-` (stdin) bypasses this check (no on-disk identity to compare).
    - **stdin** `INPUT == "-"` reads UTF-8 markdown bytes from
      `sys.stdin.buffer` (binary then decode for honest UTF-8 handling).
    - **cross-3** (encryption) / **cross-4** (macros): **N/A** — input
      is markdown, not OOXML.
  - **D5 — Plan shape:** Atomic chain of **7–10 sub-tasks** (mirrors
    Task-004 D5 / Task-003 D2 patterns). Shim + package up front. Per-
    subtask review files in `docs/reviews/`; archive in `docs/tasks/`.
- **Decisions locked from task-reviewer round-1 (2026-05-11, see
  `docs/reviews/task-005-review.md`, m8 promotion of O1–O3 to D6–D8):**
  - **D6 (was O1) — Heading walk crosses fenced-code-block boundaries.**
    Pre-scan strips fenced code blocks and HTML comments; a `## Heading`
    *inside* a code block is not a heading. A `## Heading` *before* a
    code block IS the nearest preceding heading for a table *after*
    the code block. Matches user intuition; near-zero real-world
    risk of false positives.
  - **D7 (was O2) — No `Source`-cell or sheet-level provenance
    metadata in v1.** `Worksheet.title` carries enough context; agents
    needing line-number provenance use `xlsx_add_comment.py` (xlsx-6)
    downstream. Low-cost retrofit if a real demand emerges.
  - **D8 (was O3) — `XLSX_MD_TABLES_POST_VALIDATE` env-var default
    OFF.** Matches xlsx-2/xlsx-6 precedent (opt-in only). CI sets it
    for the e2e suite.

---

## 1. General Description

### Goal

Ship a CLI **`skills/xlsx/scripts/md_tables2xlsx.py`** that reads a
markdown document (file or stdin) and emits a styled multi-sheet
`.xlsx` workbook with **one sheet per extracted table**. Two table
flavors are recognised: GFM pipe tables (with column-alignment carried
over to Excel cell alignment) and HTML `<table>` blocks (with
`colspan` / `rowspan` honoured as Excel merged cells). Sheet names
derive from the nearest preceding heading; fallback `Table-N`.
Default-on numeric / ISO-date coercion mirrors csv2xlsx + json2xlsx.
Output styling matches csv2xlsx 1:1.

### Why now

- **Closes the agent's "user pasted documentation, give me Excel" loop.**
  A tech-spec / README / Confluence-export / Notion-export commonly
  contains the data the user actually wants in spreadsheet form
  (parameter tables, benchmark numbers, pricing matrices, status
  trackers). Today the agent has to copy each table to CSV by hand,
  pipe through `csv2xlsx`, and lose context (no per-table headings,
  no multi-sheet packaging). xlsx-3 closes this loop with one CLI
  call.
- **Symmetric with `pdf-12` (`pdf_extract_tables.py`).** Once xlsx-3
  ships, the agent can chain `pdf_extract_tables.py --format markdown`
  → `md_tables2xlsx.py` to extract tables from a PDF report into a
  workbook in two deterministic steps.
- **No new dependency.** GFM pipe-table parsing is hand-rolled (~120 LOC
  for the whole `tables.py` module). HTML `<table>` parsing reuses
  `lxml` which is already in `requirements.txt:3` (used by `office/`).
  Coercion reuses `python-dateutil` (already in `requirements.txt:9`).

### Scope boundary (precision)

- **IN-scope for v1:** GFM pipe tables, HTML `<table>` blocks, heading-
  derived sheet names, numeric + ISO-date coercion, inline-markdown
  strip, cross-5 envelope, cross-7 H1 same-path, stdin `-`.
- **OUT-of-scope for v1** (honest scope §11): RST grid tables,
  MultiMarkdown extensions, PHP-Markdown-Extra captions, blockquoted
  tables, `<table>` nested inside fenced code blocks, line-wrap on
  `<br>` cells (no `wrap_text=True`), formula recalculation hook,
  per-cell formatting beyond plain-text strip (bold/italic NOT
  carried to Excel Run rich-text).

---

## 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R1** | Read markdown source from file path OR stdin sentinel `-`. | YES | (a) UTF-8 strict decode with `errors="strict"` (fail-loud on bad bytes per R8.a); (b) sentinel `-` reads `sys.stdin.buffer` and labels source as `"<stdin>"`; (c) file-not-found → exit 1 `FileNotFound`; (d) empty body → exit 2 `EmptyInput`. |
| **R2** | Parse GFM pipe tables per CommonMark + GFM §5.4. | YES | (a) header row required; (b) separator row `|---|---|` validates column count match — mismatch → skip table + warn (cross-5 `MalformedPipeSeparator` info-level on stderr, NOT envelope, processing continues); (c) trailing-pipe variations (`| a | b |` vs `a | b`) both accepted; (d) escaped pipes `\|` carry literal `|` to cell; (e) per-column alignment markers (`:---`, `---:`, `:---:`) recorded for R6.b. |
| **R3** | Parse HTML `<table>` blocks via `lxml.html`. | YES | (a) `<thead>`/`<tbody>` honoured if present; absent `<thead>` → first `<tr>` is header (GFM-like); (b) `<th>` AND `<td>` both treated as data cells (cell type comes from coercion, not tag); (c) `colspan` / `rowspan` → openpyxl merged cells; (d) inline `<table>` inside `<p>` accepted; (e) **tables inside `<!-- -->` HTML comments OR inside ` ```fenced``` ` code blocks are skipped silently** (pre-scan-strip pass). |
| **R4** | Sheet-name resolution per D2. | YES | (a) walk document, for each table find nearest preceding `#-######` OR `<h1>-<h6>` heading; (b) strip inline markdown from heading text (`_strip_inline_markdown`); (c) sanitisation pipeline §0/D2/(a-g); (d) workbook-wide dedup using case-insensitive comparison; (e) `--sheet-prefix STR` flag overrides primary rule (every sheet becomes `STR-1`, `STR-2`, … — useful for `--sheet-prefix "Report"` when the markdown has no headings). |
| **R5** | Inline-markdown strip helper. | YES | (a) `**X**` / `__X__` / `*X*` / `_X_` → `X` (non-greedy regex); (b) `` `X` `` → `X`; (c) `[text](url)` → `text` (link target dropped; v2 may surface as Excel hyperlink); (d) `~~X~~` → `X`; (e) `<br>` / `<br/>` / `<br />` → `\n`; (f) `&amp;` / `&lt;` / `&gt;` / `&quot;` / `&#NN;` HTML entities decoded; (g) other HTML tags inside a cell stripped to text (e.g. `<span>X</span>` → `X`). |
| **R6** | Cell coercion per D3. | YES | (a) numeric regex `^-?\d+(?:[.,]\d+)?$` → int/float; leading-zero column kept as text; (b) ISO-date regex (`YYYY-MM-DD` / `YYYY-MM-DDTHH:MM:SS[.ffffff][±HH:MM\|Z]`) → Excel date / datetime cell with proper `number_format`; aware datetimes → UTC-naive; (c) GFM alignment marker carried to `cell.alignment.horizontal` (`left` / `right` / `center` / `general`); (d) empty cell → `None` not `""`; (e) `--no-coerce` flag → every cell `str` + `number_format="@"`. |
| **R7** | Output styling matches csv2xlsx 1:1. | YES | (a) bold header row, `F2F2F2` `PatternFill` fill, centered alignment; (b) freeze panes `A2`; (c) auto-filter over data range; (d) column widths = `min(max(header_len, max_data_len) + 2, MAX_COL_WIDTH=50)`; (e) opt-outs `--no-freeze`, `--no-filter`. |
| **R8** | Cross-cutting parity per D4. | YES | (a) `--json-errors` envelope cross-5 shape `{v:1, error, code, type, details}` via `_errors.add_json_errors_argument` + `report_error`; (b) cross-7 H1 same-path guard via `Path.resolve()` (follows symlinks) → exit 6 `SelfOverwriteRefused`; (c) stdin `-` bypasses same-path; (d) NO cross-3 / cross-4 (input is markdown). |
| **R9** | Honest-scope locks (regression — M2 review-fix; (a)–(j) cover §11.1–§11.10 1:1, except §11.10 TOCTOU is doc-only). | YES | Lock-in tests for: (a) **§11.1** RST grid tables NOT parsed (file containing only `+--+--+`-tables exits 2 `NoTablesFound`); (b) **§11.2** MultiMarkdown `[Caption]` / PHP-Markdown-Extra extensions → rendered as literal text in cells, no caption metadata; (c) **§11.3** no `wrap_text=True` on `<br>` cells (cell value contains literal `\n`, openpyxl `wrap_text` attr is None); (d) **§11.4** inline-markdown bold/italic NOT carried to Excel rich-text Runs (cell value is plain `str`, no `RichTextBlock`); (e) **§11.5** no formula resolution — `"=SUM(A1:A3)"` written as literal text (cell `data_type = "s"`, not `"f"`); (f) **§11.6** no `--strict-dates` flag in v1 (argparse rejects the flag); (g) **§11.7** blockquoted `> | a | b |` lines → not extracted (fixture with blockquoted table only → exit 2 `NoTablesFound`); (h) **§11.8** overlapping `colspan`/`rowspan` → emit stderr warning, first merge wins (subsequent merge dropped silently); (i) **§11.9** `<style>foo</style>` and `<script>foo</script>` blocks inside markdown → skipped silently (not parsed as data, not surfaced as text); (j) **§11.10** symlink TOCTOU race — documentation-only lock (no deterministic regression test possible; mirrors xlsx-2 ARCH §10 honest scope). Also include the historic cross-flavor regression: `colspan`/`rowspan` valid in HTML tables only, NOT GFM. |
| **R10** | Empty-input guards. | YES | (a) zero tables found → exit 2 `NoTablesFound` envelope (NOT silent success — agent should know nothing was extracted); (b) `--allow-empty` flag opts into "write empty workbook with single placeholder sheet" (rare CI use-case); (c) zero-row table (header only, no data rows) → write sheet with just header + freeze pane (NOT skip — header IS the data here). |
| **R11** | Cross-skill replication boundary preserved. | YES | (a) no edits to `office/`, `_soffice.py`, `_errors.py`, `preview.py`, `office_passwd.py`; (b) `diff -q` gating check from CLAUDE.md §2 passes; (c) optional post-validate hook `XLSX_MD_TABLES_POST_VALIDATE=1` (mirrors xlsx-6 / xlsx-2) → subprocess `office/validate.py` on output → exit 7 `PostValidateFailed` + unlink output on failure. |

**Counts:** 11 requirements, **61 sub-features** after M2 review-fix
(R1.4 + R2.5 + R3.5 + R4.5 + R5.7 + R6.5 + R7.5 + R8.4 + R9.10 + R10.3
+ R11.3 + 1 cross-flavor regression in R9). Every requirement carries
≥ 3 sub-features (analyst-prompt minimum honoured); average 5.5.

---

## 3. Problem Description

LLM- and agent-driven workflows constantly produce or ingest markdown
documents (technical specs, runbooks, Confluence/Notion exports,
chat-paste reports). These documents commonly contain **the data the
user actually wants in Excel**: pricing matrices, parameter tables,
benchmark numbers, release-feature trackers. Today the agent must:

1. Manually copy each table to a CSV file, OR
2. Pipe through markdown-to-HTML → HTML-to-CSV → `csv2xlsx`, losing
   per-table heading context, OR
3. Hand-roll openpyxl boilerplate inline (no styling, no leading-zero
   preservation, no ISO-date coercion).

All three workarounds lose information (heading → sheet-name
provenance is gone) and produce ugly output (no styling, no freeze,
no auto-filter).

The `md_tables2xlsx.py` CLI delivers a one-shot deterministic path:
markdown in → multi-sheet styled `.xlsx` out, one sheet per table,
sheet name = preceding heading. Pairs with the future `pdf-12`
(`pdf_extract_tables.py --format markdown`) for full PDF → markdown
→ xlsx extraction pipelines.

---

## 4. Use Cases

### UC-1: Convert a tech-spec markdown to a multi-sheet workbook (HAPPY PATH)

- **Actors:** Agent (or human) running the CLI.
- **Preconditions:**
  - A valid UTF-8 markdown file exists with ≥ 1 GFM pipe table or
    HTML `<table>` block.
  - The output `.xlsx` path is on a writable filesystem.
- **Main Scenario:**
  1. User invokes `python3 md_tables2xlsx.py spec.md out.xlsx`.
  2. CLI reads `spec.md`, parses the document into a token stream.
  3. CLI identifies all GFM pipe tables and HTML `<table>` blocks
     (skipping fenced-code-block and HTML-comment regions).
  4. For each table, CLI walks backward to find the nearest preceding
     `#-######` or `<h1>-<h6>` heading; if found, applies the
     sanitisation pipeline (D2) and uses it as the sheet name. If
     not found OR collision after dedup, falls back to `Table-N`.
  5. For each cell, CLI strips inline markdown (R5), then applies
     numeric / ISO-date coercion (R6).
  6. CLI writes the workbook with csv2xlsx-style header (bold,
     light-grey fill, centered) on each sheet, freeze pane `A2`,
     auto-filter over the data range, auto column widths.
  7. CLI exits 0 silently.
- **Alternative Scenarios:**
  - **A1 (empty markdown):** Body has zero non-whitespace bytes →
    exit 2 `EmptyInput` envelope.
  - **A2 (no tables found):** Markdown has prose but no tables →
    exit 2 `NoTablesFound` envelope unless `--allow-empty` is passed.
  - **A3 (malformed pipe-table separator):** A table-looking block
     with column-count mismatch between header and separator is
     skipped + a single-line warning is written to stderr (NOT
     envelope, NOT exit-non-zero); processing continues with remaining
     valid tables.
  - **A4 (file not found):** Input path doesn't exist → exit 1
     `FileNotFound` envelope.
  - **A5 (decode error):** Non-UTF-8 bytes in input → exit 2
     `InputEncodingError` envelope with `details: {offset}`.
- **Postconditions:** A valid `.xlsx` file at the output path,
  validated against `office/validators/xlsx.py` if
  `XLSX_MD_TABLES_POST_VALIDATE=1` is set.
- **Acceptance Criteria:**
  - **PASS:** `python3 md_tables2xlsx.py examples/spec_with_tables.md
    /tmp/out.xlsx` exits 0 and produces a workbook with N sheets where
    N == number of tables in the markdown (counted by a separate
    `grep -E '^\|.*\|$|<table'` test fixture).
  - **PASS:** Each sheet's name matches the nearest preceding heading
    OR `Table-N` per D2.
  - **PASS:** `python3 office/validate.py /tmp/out.xlsx` exits 0.
  - **PASS:** Opening in Excel / LibreOffice shows all sheets with
    bold header, freeze pane, and auto-filter.
  - **FAIL** (caught in CI): missing sheet, missing freeze pane, or
    cell coercion regression (an obvious number stored as text).

### UC-2: Stream markdown from stdin and write a workbook

- **Actors:** Agent piping LLM output into the CLI.
- **Preconditions:** Output `.xlsx` path is on a writable filesystem.
- **Main Scenario:**
  1. User invokes `cat report.md | python3 md_tables2xlsx.py -
     out.xlsx`.
  2. CLI detects `INPUT == "-"`, reads `sys.stdin.buffer`, decodes
     UTF-8 strictly.
  3. Same pipeline as UC-1 from step (3) onward.
- **Alternative Scenarios:**
  - **A1 (stdin is empty):** zero bytes from stdin → exit 2
    `EmptyInput` envelope with `details: {source: "<stdin>"}`.
  - **A2 (bad UTF-8 on stdin):** decode error → exit 2
    `InputEncodingError` envelope with `details: {source: "<stdin>",
    offset: BYTE_OFFSET}`.
- **Postconditions:** Same as UC-1.
- **Acceptance Criteria:**
  - **PASS:** stdin pipe produces a workbook structurally identical
    (binary diff modulo timestamps) to passing the same content as
    file.
  - **PASS:** Same-path guard is **bypassed** for stdin (there is no
    on-disk input to compare against output).

### UC-3: HTML `<table>` block with `colspan` / `rowspan`

- **Actors:** Agent processing Confluence/Notion HTML-table export
  re-pasted into a markdown file.
- **Preconditions:** Markdown contains a `<table>` block where some
  `<td>` or `<th>` carries `colspan="N"` or `rowspan="N"`.
- **Main Scenario:**
  1. CLI parses the `<table>` via `lxml.html.fragment_fromstring`.
  2. For each cell with `colspan="N"` and/or `rowspan="N"`, CLI
     records the merge range and writes the cell value to the anchor
     cell (top-left of the merged range).
  3. CLI invokes `ws.merge_cells(start_row=..., start_column=...,
     end_row=..., end_column=...)` for each recorded range.
- **Alternative Scenarios:**
  - **A1 (overlapping merge ranges):** Pathological HTML produces
    overlapping `rowspan` / `colspan` that don't form a regular grid
    → CLI silently drops the second merge (openpyxl `merge_cells`
    raises `ValueError`; caught and converted to a stderr warning).
    Honest-scope §11.8.
  - **A2 (invalid HTML — unclosed tag):** `lxml.html` is lenient and
    auto-closes; the resulting tree is parsed as best-effort. No
    error envelope.
- **Postconditions:** Workbook has merged-cell ranges that round-trip
  through openpyxl.
- **Acceptance Criteria:**
  - **PASS:** A 2×3 merge (`rowspan=2 colspan=3`) appears as
    `A1:C2` merged range in the output sheet.
  - **PASS:** Anchor-cell value is the cell text from the source
    `<td>`; the other cells in the merged range are blank (openpyxl
    `None`).

### UC-4: Same-path collision (input == output)

- **Actors:** Careless agent passing the same path twice.
- **Preconditions:** Caller provides `INPUT == OUTPUT` (literally or
  via a symlink).
- **Main Scenario:**
  1. CLI resolves both paths via `Path.resolve()` (follows symlinks).
  2. Resolved paths compare equal → exit 6 `SelfOverwriteRefused`
     envelope. No output file written.
- **Alternative Scenarios:**
  - **A1 (input is `-`):** Stdin bypasses the guard (there is no
    on-disk input).
- **Postconditions:** No file modified on disk.
- **Acceptance Criteria:**
  - **PASS:** `md_tables2xlsx.py a.md a.md` exits 6, prints envelope
    on `--json-errors`, leaves `a.md` byte-identical.
  - **PASS:** `ln -s spec.md alias.md; md_tables2xlsx.py spec.md
    alias.md` also exits 6 (symlink follow).

---

## 5. Acceptance Criteria (Global / E2E)

The following E2E tests gate `validate_skill.py skills/xlsx` exit 0
and the final merge.

### Mandatory E2E cases (≥ 10 in `tests/test_e2e.sh`)

| Tag | What it asserts |
|---|---|
| **T-happy-gfm** | 3 GFM tables under 3 different `##` headings → workbook has 3 sheets named after headings. |
| **T-happy-html** | 1 GFM + 1 `<table>` block → workbook has 2 sheets, correct merging on HTML colspan. |
| **T-stdin-dash** | `cat fixture.md \| md_tables2xlsx.py - out.xlsx` produces same workbook (modulo timestamps) as file-mode. |
| **T-same-path** | `md_tables2xlsx.py x.md x.md` → exit 6, envelope shape, no file modified. |
| **T-no-tables** | Markdown with prose only, no tables → exit 2 `NoTablesFound` envelope. |
| **T-no-tables-allow-empty** | Same input with `--allow-empty` → exit 0, single placeholder sheet `Empty`. |
| **T-fenced-code-table** | Markdown with a pipe-table-looking block INSIDE ```` ```text … ``` ```` fence → skipped, exit 2 `NoTablesFound`. |
| **T-html-comment-table** | `<table>` inside `<!-- … -->` → skipped, exit 2 `NoTablesFound`. |
| **T-coerce-leading-zero** | GFM table with a column of `"007", "042"` values → column kept as text in Excel (not stored as int 7). |
| **T-coerce-iso-date** | GFM table with `"2026-05-11"` column → Excel datetime cell with `number_format="YYYY-MM-DD"`. |
| **T-sheet-name-sanitisation** | Heading `## Q1: [Budget]` → sheet name `Q1_ _Budget_` (forbidden chars `:`/`[`/`]` replaced with `_`). |
| **T-sheet-name-dedup** | Two `## Results` headings → sheets `Results` and `Results-2`. |
| **T-envelope-cross5-shape** | `--json-errors` on any failure → single-line JSON on stderr with keys `{v, error, code, type, details}`. |

13 E2E cases inventoried (≥ 10 required per RTM); Planner picks the
final list and inventories tags in the task chain.

### Unit-test budget

`tests/test_md_tables2xlsx.py` ≥ 35 unit cases organized in classes:

- `TestPipeParser` (~ 10 cases) — header / separator / trailing-pipe / escaped-pipe / column-count mismatch / alignment markers / nested-text / `<br>` in cell.
- `TestHtmlParser` (~ 6 cases) — `<thead>`/`<tbody>`, `<th>` vs `<td>`, colspan, rowspan, entity decode, malformed-but-recovered.
- `TestInlineStrip` (~ 6 cases) — bold / italic / code / link / strikethrough / `<br>` / entity / mixed.
- `TestCoerce` (~ 6 cases) — numeric / comma-decimal / leading-zero / iso-date / iso-datetime / aware-tz / no-coerce.
- `TestSheetNaming` (~ 5 cases) — heading-strip / sanitisation / 31-char truncation / dedup / fallback Table-N / reserved-name `History`.
- `TestExceptions` / `TestPublicSurface` (~ 4 cases) — `_AppError` shape, public-API re-exports from shim.

### Validation gating

- `python3 .claude/skills/skill-creator/scripts/validate_skill.py
  skills/xlsx` → exit 0.
- `diff -qr skills/docx/scripts/office skills/xlsx/scripts/office`
  → silent.
- The eleven cross-skill `diff -q` checks (CLAUDE.md §2 / xlsx-2
  ARCH §9) all silent.

---

## 6. Stub-First / Atomic-Chain Compliance

Mirrors xlsx-2 Task-004 D5: **Stage 1** scaffolds the shim + empty
package + test files (all skipped) + fixtures + doc stubs. **Stage 2**
fills modules one at a time with the test suite going RED → GREEN.
**Stage 3** finalises docs and the round-trip contract reference.

Per-subtask shape (Planner locks the slice):

- **Stage 1 (scaffolding):**
  - 005-01: skeleton (shim + package `__init__.py` + empty modules +
    fixtures + `tests/test_md_tables2xlsx.py` (all-skipped) +
    `tests/test_e2e.sh` (13 named skip-stubs)).
- **Stage 2 (logic):**
  - 005-02: `exceptions.py` + cross-cutting helpers (cross-5 envelope
    wiring, cross-7 H1 same-path, stdin reader, `--json-errors`).
  - 005-03: `tables.py` — GFM pipe parser (R2).
  - 005-04: `tables.py` — HTML `<table>` parser (R3) + merge-range
    handling (UC-3).
  - 005-05: `inline.py` — inline-markdown strip (R5).
  - 005-06: `coerce.py` — numeric + ISO-date coercion (R6) +
    leading-zero detection.
  - 005-07: `naming.py` — sheet-name resolution + sanitisation (R4 /
    D2 a-g).
  - 005-08: `writer.py` — workbook construction, styling, freeze /
    auto-filter / column widths.
  - 005-09: `cli.py` — argparse, `_run` linear pipeline, public
    `convert_md_tables_to_xlsx` helper.
- **Stage 3 (finalisation):**
  - 005-10: post-validate-e2e-green + final docs polish + `.AGENTS.md`
    sync + cross-skill `diff -q` gate green.

Planner may merge sub-tasks if the LOC pressure is low (e.g.
005-03+005-04 if combined pipe+HTML parser ≤ 350 LOC). The decision
is the Planner's; this section sets the ceiling, not the floor.

---

## 7. Exit Codes (Locked Surface)

| Exit | Meaning | Raised by |
|---|---|---|
| **0** | Success | normal path |
| **1** | Input file not found / IO error on output (parent dir missing) | `FileNotFound`, `OSError` envelope |
| **2** | Input shape / validation error (parse failure, no tables found, empty body, bad UTF-8) | `EmptyInput`, `NoTablesFound`, `MalformedTable`, `InputEncodingError`, `InvalidSheetName` |
| **6** | Same-path collision (input resolves to output) | `SelfOverwriteRefused` |
| **7** | Post-validate hook failed (`XLSX_MD_TABLES_POST_VALIDATE=1` + `office/validate.py` non-zero) | `PostValidateFailed` |

Exit codes 3, 4, 5 are deliberately **unused** in xlsx-3 (cross-3
encryption / cross-4 macro / argparse=2 collision avoidance):

- **3** — reserved for cross-3 (encrypted-input refusal) in OOXML
  readers; N/A for markdown input.
- **4** — reserved for cross-4 (macro-bearing input warning); N/A for
  markdown input.
- **5** — reserved (no current use).

Argparse usage errors (`UsageError`) exit **2** through the envelope
(cross-5 unifies them with shape / validation errors — this matches
xlsx-2 and xlsx-7 precedent).

---

## 8. Public API (Locked Surface)

```python
# skills/xlsx/scripts/md_tables2xlsx/__init__.py
# Final shape after ARCH M4 review-fix: mirrors xlsx-2's
# convert_json_to_xlsx 1:1 — argparse-routed for sibling parity.
def convert_md_tables_to_xlsx(
    input_path: str | Path,   # path or "-" for stdin (str)
    output_path: str | Path,
    **kwargs: object,         # allow_empty / coerce / freeze /
                              # auto_filter / sheet_prefix / encoding
                              # — each maps 1:1 to a CLI flag.
) -> int: ...                  # returns exit code (0 happy; non-zero
                              # per exit-code matrix in §7)
```

Both `input_path` and `output_path` accept `str | Path` symmetrically
(m9 review-fix). Internally, both are normalised to `str` and routed
through `main(argv)` using the **`--flag=value` atomic-token form**
(VDD-multi M4 protection inherited from xlsx-2: a kwarg value
beginning with `--` cannot poison argparse). Sentinel `"-"` is the
*only* legal `str` value that bypasses `Path` resolution (stdin); all
other strings are treated as filesystem paths.

`main(argv: list[str] | None = None) -> int` is the argparse
entrypoint, re-exported from `md_tables2xlsx.cli`.

**Single source of truth:** `convert_md_tables_to_xlsx` lives in
`md_tables2xlsx/__init__.py`; the shim `md_tables2xlsx.py` only
re-exports it (mirrors xlsx-2 task-004-07 D2 pattern locked in
Architecture review of Task-004).

---

## 9. CLI Surface (Locked)

```
python3 md_tables2xlsx.py INPUT OUTPUT [flags]

Positional:
  INPUT             Path to .md/.markdown file, or "-" for stdin
  OUTPUT            Destination .xlsx file

Flags:
  --no-coerce            Disable numeric / ISO-date coercion (force all cells to text)
  --no-freeze            Disable freeze pane on header row
  --no-filter            Disable auto-filter over data range
  --allow-empty          When zero tables found, write an empty workbook (exit 0) instead of NoTablesFound (exit 2)
  --sheet-prefix STR     Override heading-based sheet naming with sequential STR-1, STR-2, ...
  --encoding ENC         Input file encoding (default: utf-8; markdown is canonically UTF-8)
  --json-errors          Emit failures as a single-line JSON envelope on stderr (cross-5)
  -h, --help             Show this help and exit
```

8 flags total (vs xlsx-2's 8, xlsx-7's 22). Effort-S budget respected.

---

## 10. Cross-Skill Replication Boundary (CLAUDE.md §2)

xlsx-3 is **strictly additive** within `skills/xlsx/scripts/`. It must
NOT modify any of the following (which are byte-replicated across the
office skills):

- `skills/xlsx/scripts/_errors.py` (4-skill)
- `skills/xlsx/scripts/_soffice.py` (4-skill)
- `skills/xlsx/scripts/preview.py` (4-skill)
- `skills/xlsx/scripts/office_passwd.py` (3-skill OOXML)
- `skills/xlsx/scripts/office/` (3-skill OOXML)

The eleven `diff -q` gating checks from CLAUDE.md §2 / xlsx-2 ARCH §9
remain silent. xlsx-3 invokes `office/validators/xlsx.py` only via
subprocess (post-validate hook), not by import — same pattern as
xlsx-6 and xlsx-2.

---

## 11. Honest Scope (Locked Limitations for v1)

These limitations are **intentional** for v1. Items §11.1–§11.9 are
locked by a regression test in R9 (sub-bullets R9.a–R9.i, one per
item, M2 review-fix). Item §11.10 (TOCTOU symlink race) is
documentation-only — no deterministic regression test exists; mirrors
xlsx-2 ARCH §10 honest-scope acceptance. Re-litigation of any item
requires a documented v2 use-case in the backlog.

1. **No RST grid tables.** Files containing only `+---+---+`-tables
   exit 2 `NoTablesFound`. RST grid parser adds ~200 LOC for low
   real-world hit-rate; defer to v2 if Sphinx-doc inputs become a
   reported pattern.
2. **No MultiMarkdown / PHP-Markdown-Extra extensions.** Column
   grouping (`||`), table captions (`[Caption]`), and inline rowspan
   markers (`^^`) are NOT parsed. The cells render as literal text.
3. **No `wrap_text=True` on `<br>` cells.** The cell value contains a
   literal `\n`, but Excel renders it on one line unless the user
   manually sets wrap. Adding `wrap_text=True` would also force a
   row-height recalc and is a styling decision better made by the
   user (some workflows want compact rows, others want wrapped).
   Defer to v2 flag `--wrap-br-cells`.
4. **No rich-text Runs.** Bold / italic / code spans are stripped to
   plain text. Carrying them as openpyxl `Run` objects would require
   per-character rich-text encoding and would diverge visually from
   csv2xlsx + json2xlsx output.
5. **No formula resolution.** Markdown table cells are static text;
   no `=SUM(...)` is generated. If the user wants formulas, they edit
   the workbook downstream.
6. **No `--strict-dates` mode.** Markdown is human-authored and
   strict-mode would reject `2026-05-11+02:00`-style strings that a
   human meant as "May 11 in CEST". The default-mode silent UTC-naive
   coercion is the right default for this input class.
7. **Blockquoted tables (`> | a | b |`) are skipped.** Nesting is
   ambiguous (is the `>` the blockquote marker or a column-1
   continuation?) and the real-world prevalence is near zero. v2 may
   surface the table if a clear demand emerges.
8. **Overlapping HTML merge ranges drop silently.** When `colspan` /
   `rowspan` produce a non-grid layout, openpyxl raises
   `ValueError`; xlsx-3 catches and emits a stderr warning, keeping
   the first valid merge and dropping the overlap. Mirror's xlsx-6's
   merged-cell-conflict resolution.
9. **No HTML `<style>` / `<script>` interpretation.** `<style>` and
   `<script>` blocks inside the markdown are skipped entirely (treated
   as raw text and discarded). No CSS-driven cell formatting in v1.
10. **Symlink race between `resolve()` and `open()`.** Mirrors xlsx-2
    ARCH §10 honest-scope item — same v1 TOCTOU acceptance. (R9
    documentation-only lock per §11 preamble; no deterministic
    regression test is possible without a controlled fs race harness.)

---

## 12. Open Questions (residual)

All scope-blocking questions from `/vdd-start-feature` Q&A were
closed in D1–D5. Round-1 task-reviewer (`docs/reviews/task-005-review.md`)
m8 promoted the previously-open O1 / O2 / O3 to **D6 / D7 / D8**
(documented in §0 above). No residual open questions remain at the
Analysis → Architecture boundary.

If the Architect surfaces new questions during §3 (System Architecture)
or §4 (Data Model) drafting, they land in
`docs/ARCHITECTURE.md` §11 (residual open questions) and the
architecture-reviewer loops on them, not on this TASK.

---

## 13. Definition of Done

- [ ] `docs/PLAN.md` and `docs/tasks/task-005-NN-*.md` files for the
      atomic chain (7-10 sub-tasks per §6).
- [ ] All Stage-2 modules implemented and unit tests GREEN
      (≥ 35 cases).
- [ ] All E2E cases GREEN (≥ 10; tags inventoried in §5).
- [ ] `python3 .claude/skills/skill-creator/scripts/validate_skill.py
      skills/xlsx` → exit 0.
- [ ] The eleven `diff -q` cross-skill replication checks
      (CLAUDE.md §2) → silent.
- [ ] `skills/xlsx/SKILL.md` §2 capabilities + §4 script contract
      updated with `md_tables2xlsx.py`.
- [ ] `skills/xlsx/.AGENTS.md` updated with module map for the new
      package.
- [ ] `docs/office-skills-backlog.md` xlsx-3 row updated with
      ✅ DONE + LOC + test counts.

---

## 14. Implementation Summary (post-merge, 2026-05-11)

> Added during `/update-docs` to reflect what actually shipped vs. the
> pre-implementation spec above. The §0–§13 spec is preserved verbatim
> as the design-time contract; this section captures the post-merge
> reality.

### 14.1. Chain delivery

**10 atomic sub-tasks** shipped under the Task-004 D5 pattern
(scaffolding → logic per F-region → finalization), within the 7–10
envelope locked in D5:

| Sub-task | Closes | LOC actual / budget | Status |
|---|---|---|---|
| 005.01 — skeleton (shim + 10-module package + `.AGENTS.md` placeholder) | R11.a-c, R12.c | shim 47/60, pkg total skeleton | ✅ |
| 005.02 — test scaffolding (109 unit + 14 E2E SKIP-stubs + 5 fixtures) | R11.a-d | tests ~700 LOC | ✅ |
| 005.03 — exceptions + cross-cutting helpers (envelope-only E2E green) | R8, R10.a/c | exceptions 107/90 (+17), cli_helpers part of 133/80 | ✅ |
| 005.04 — `loaders.py` (F1+F2: pre-scan + block iteration) | R1, R2.b, R3.e, R9.g, R9.i | 486/180 (+306; CommonMark indented-code parser intrinsically heavy) | ✅ |
| 005.05 — `inline.py` (F5) + `coerce.py` (F6) | R5, R6 | inline 76/100, coerce 141/150 | ✅ |
| 005.06 — `tables.py` (F3+F4 + M1 billion-laughs lock) | R2, R3, M1 | 352/220 (+132; colspan/rowspan grid + safe-parse helper) | ✅ |
| 005.07 — `naming.py` (F7: 9-step algo + M3 UTF-16 dedup lock) | R4, M3 | 166/130 (+36) | ✅ |
| 005.08 — `writer.py` (F8 + 3-way drift detection) | R6.c, R7, R10.c, A6, A8 | 184/200 ✓ | ✅ |
| 005.09 — `cli.py` orchestrator + post-validate + M4 atomic-token | R8, R9, R10.b/d, R11.c, M4 | 278/280 (within M2 guardrail) | ✅ |
| 005.10 — Final docs (SKILL.md + `.AGENTS.md` + backlog ✅ DONE) | R11.e, R12.a-d | (docs only) | ✅ |

**Package total (post-vdd-multi):** 2044 LOC (vs original 1540-LOC
ceiling; +504 over). Honest overshoot concentrated in:

- `loaders.py` (486 vs 180) — 4-region CommonMark pre-scan pipeline +
  4 frozen dataclasses + line-preserving replacement primitive. Per-
  helper sizes are all sane; the budget was set at architecture time
  before the indented-code-block spec was fully fleshed.
- `tables.py` (352 vs 220) — `_expand_spans` colspan/rowspan grid +
  `_parse_span` safe-parse helper (added in vdd-multi H1). Each
  function is ≤ 100 LOC; no monolith.

All modules within the 500-LOC architect-cap.

### 14.2. `/vdd-multi` Phase-3 fixes (after chain merged)

After the 10-task chain completed, an orthogonal three-critic
adversarial pass (`critic-logic` + `critic-security` +
`critic-performance` in parallel) surfaced **3 HIGH + 7 MED + 1 LOW**
real findings (no critical). All 12 were inlined with regression tests
(`TestVddMultiFixes`, 15 tests):

| # | Sev | File | Fix |
|---|---|---|---|
| H1 | HIGH | `tables.py` | Safe `_parse_span()` with try/except + clamp to Excel column limit `_MAX_SPAN=16384` (closes uncaught `ValueError` on `colspan="abc"` AND unbounded width allocation). |
| H2 | HIGH | `cli.py` | Widened `try/except OSError` around `assert_distinct_paths` (symlink-loop / ENAMETOOLONG no longer escape as bare traceback). |
| H3 | HIGH | `loaders.py` (`_replace_with_spaces`) | Rewrote per-char Python loop as `split("\n")` / `join` — 30× faster on adversarial input; same semantics. |
| H4 | MED→HIGH | `loaders.py` (`_strip_style_script`) | Added `pos` tracking so repeated style-blocks don't re-scan from position 0 (O(N²) → O(n)). |
| M1 | MED | `naming.py` | `_CONTROL_RE` strip pass — C0/DEL chars `\x00-\x1F\x7F` no longer slip past sanitisation (Excel previously refused to open). |
| M2 | MED | `tables.py` (`_walk_rows`) | Merges direct `<tr>` children even when `<thead>`/`<tbody>` present (no longer silently drops legacy markup). |
| M3 | MED | `tables.py` | Empty `<table>` returns `None` (stderr warning) instead of producing an empty-named sheet. |
| M4 | MED | `loaders.py` | `_FENCED_OPEN_RE` capped at `{0,3}` leading spaces per CommonMark (4+ spaces is now correctly an indented code block). |
| M5 | MED | `cli.py` | `SystemExit(None)` → clean exit 0 (was incorrectly mapped to UsageError envelope). |
| M6 | MED | `__init__.py` | `convert_md_tables_to_xlsx(sheet_prefix=None)` skips the kwarg (was producing a literal `"None"` sheet prefix). |
| M7 | LOW→MED | `cli_helpers.py` | Subprocess `--` separator before user-controlled output path (no `--`-prefixed flag injection into `office/validate.py`'s argparse). |
| L1 | LOW | `coerce.py` | `_has_leading_zero` catches negative leading-zero `-007` via `lstrip("-")` (was only `007`). |

Deferred to honest scope (documented in `md_tables2xlsx/.AGENTS.md`):
stdin DoS unbounded `read()`, HTML surrogate codepoint corruption,
macOS case-insensitive filesystem same-path bypass, `_STYLE_OPEN_RE`
greedy `>` inside quoted attributes, post-validate `capture_output`
unbounded.

### 14.3. Test inventory (post-merge)

- **`tests/test_md_tables2xlsx.py`** — **109 unit tests**, ALL LIVE
  (0 SKIP). 9 test classes:
  - `TestPublicSurface` (5) — public symbols, signature pin, parser
    singleton, ARCH M4 routing + atomic-token protection.
  - `TestPipeParser` (16) — block detection + full GFM parse + 4
    pre-scan strippers (fenced / comment / indented / style+script).
  - `TestHtmlParser` (11) — basic, thead/tbody, colspan/rowspan,
    entities, malformed-recovery, billion-laughs neuter (ARCH M1),
    singleton-reuse, R9.c GFM-no-colspan lock.
  - `TestInlineStrip` (12) — all R5 sub-features + R9.b (§11.2
    MultiMarkdown literal) + R9.d (no rich-text Runs) + idempotence.
  - `TestCoerce` (10) — numeric / ISO-date / leading-zero / aware-tz /
    lenient-date rejection / mixed-column.
  - `TestSheetNaming` (13) — full 9-step algorithm + ARCH M3 emoji-
    collision dedup + `History` reservation + dedup overflow.
  - `TestExceptions` (9) — typed taxonomy + truthy allowlist + same-
    path guard (incl. symlink follow) + stdin decode strict.
  - `TestStyleConstantDrift` (5) — 3-way drift detection (csv2xlsx ↔
    json2xlsx ↔ md_tables2xlsx).
  - `TestWriter` (13) — full workbook write + merges + alignment +
    freeze / filter + R9.e formula lock + ARCH A6/A8 locks.
  - **`TestVddMultiFixes` (15)** — regression locks for all 12 fixes
    above (some fixes have multiple regression tests).

- **`tests/test_e2e.sh`** — **14 named xlsx-3 E2E cases**, ALL LIVE:
  `T-md-tables-happy-gfm`, `-happy-html`, `-stdin-dash`, `-same-path`,
  `-no-tables`, `-no-tables-allow-empty`, `-fenced-code-table-only`,
  `-html-comment-table-only`, `-coerce-leading-zero`, `-coerce-iso-date`,
  `-sheet-name-sanitisation`, `-sheet-name-dedup`,
  `-envelope-cross5-shape`, `-indented-code-block-skip`.

- **Whole-skill regression**: 511 unit tests / 7 SKIP (unrelated pre-
  existing) / 0 fail. 141 E2E pass / 0 fail. `validate_skill.py
  skills/xlsx` exit 0. Eleven cross-skill `diff -q` (CLAUDE.md §2)
  silent.

### 14.4. Deltas vs spec (§0–§13)

The implementation hews to the spec; the few intentional deltas are:

- **§6 sub-task count**: spec said 7–10 (D5 envelope); shipped 10.
- **§0 / §8 LOC budget**: spec ceiling was ~ 760 LOC production +
  ~ 600 LOC tests. Actual: ~ 2044 LOC production + ~ 1300 LOC tests.
  All within 500-LOC-per-module architect-cap; honest scope §14.1.
- **§13 DoD `≥ 35 unit cases`**: shipped 109. `≥ 10 E2E cases`:
  shipped 14.
- **R3 + R6**: GFM column-alignment marker `:---:` requires `-{3,}`
  hyphens per CommonMark / GFM spec; the implementation enforces this
  (3+ hyphens), so `:--:` (2 hyphens between colons) is treated as
  "no explicit alignment" → openpyxl `general`. Test fixtures use
  `:---:` consistently.
- **§11.2 R9.b lock** (post task-reviewer M1 review-fix): MultiMarkdown
  `[Caption]` syntax test (`test_multimarkdown_caption_literal`) was
  added late in 005.05 after plan-review flagged the original RTM
  attribution was off-by-one (R9.b ↔ R9.c label inversion). Locked
  correctly post-fix.
- **vdd-multi additions**: 12 fixes + 15 regression tests (§14.2)
  represent post-spec hardening — every deferred-honest-scope item is
  documented in `md_tables2xlsx/.AGENTS.md`.

### 14.5. Artefacts

- **Code**: `skills/xlsx/scripts/md_tables2xlsx.py` (shim) +
  `skills/xlsx/scripts/md_tables2xlsx/` package (10 modules).
- **Tests**: `skills/xlsx/scripts/tests/test_md_tables2xlsx.py` +
  appended cases in `tests/test_e2e.sh`.
- **Fixtures**: `skills/xlsx/examples/md_tables_{simple,html,fenced,
  no_tables,sheet_naming_edge}.md`.
- **Docs**:
  - [`skills/xlsx/SKILL.md`](../skills/xlsx/SKILL.md) updated (Red
    Flag + Capability bullet + Script Contract line).
  - [`skills/xlsx/scripts/.AGENTS.md`](../skills/xlsx/scripts/.AGENTS.md)
    + [`skills/xlsx/scripts/md_tables2xlsx/.AGENTS.md`](../skills/xlsx/scripts/md_tables2xlsx/.AGENTS.md)
    final module map + architectural locks + R9.a-j table.
  - [`docs/office-skills-backlog.md`](office-skills-backlog.md)
    xlsx-3 row ✅ DONE with full status line.
- **Reviews**: [`docs/reviews/task-005-review.md`](reviews/task-005-review.md)
  (task-reviewer) + [`docs/reviews/task-005-architecture-review.md`](reviews/task-005-architecture-review.md)
  (architecture-reviewer) + [`docs/reviews/task-005-plan-review.md`](reviews/task-005-plan-review.md)
  (plan-reviewer); per-task Sarcasmotron rounds inline in session-state.

---

**End of TASK 005 — xlsx-3 — `md_tables2xlsx.py` (✅ MERGED 2026-05-11).**

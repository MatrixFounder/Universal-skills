# TASK 012 — xlsx-9: `xlsx2md.py` (read-back в markdown)

> **Mode:** VDD (Verification-Driven Development).
> **Source backlog row:** [`docs/office-skills-backlog.md`](office-skills-backlog.md) → `xlsx-9` (line 200).
> **Status:** DRAFT v1 — pending Task-Reviewer approval.
> **Predecessors (✅ MERGED):**
> - TASK 009 (`xlsx-10.A` — `xlsx_read/`) — ✅ 2026-05-12.
> - TASK 010 (`xlsx-8` — `xlsx2csv.py` / `xlsx2json.py`) — ✅ 2026-05-12.
> - TASK 011 (`xlsx-8a` — production hardening) — ✅ 2026-05-13.
> - TASK [prior] (`xlsx-3` — `md_tables2xlsx.py`) — ✅ (long-merged).

---

## 0. Meta Information

- **Task ID:** `012`
- **Slug:** `xlsx-9-xlsx2md`
- **Backlog row:** `xlsx-9` (`docs/office-skills-backlog.md` line 200).
- **Target skill:** `skills/xlsx/` (Proprietary — see CLAUDE.md §3, `skills/xlsx/LICENSE`).
- **Cross-skill replication:** **None.** xlsx-9 is xlsx-specific and touches no
  cross-replicated files. The 5-file silent `diff -q` gate (CLAUDE.md §2) MUST
  remain silent after this task lands. The five pairs listed below are the
  xlsx↔docx subset of the full 11-directional `diff -q` matrix in CLAUDE.md §2;
  xlsx-9 touches only xlsx, so this subset is sufficient for xlsx-9 gating.
  The five guarded files are:
  1. `skills/docx/scripts/office/` ↔ `skills/xlsx/scripts/office/` (dir)
  2. `skills/docx/scripts/_soffice.py` ↔ `skills/xlsx/scripts/_soffice.py`
  3. `skills/docx/scripts/_errors.py` ↔ `skills/xlsx/scripts/_errors.py`
  4. `skills/docx/scripts/preview.py` ↔ `skills/xlsx/scripts/preview.py`
  5. `skills/docx/scripts/office_passwd.py` ↔ `skills/xlsx/scripts/office_passwd.py`
  None of these are touched by xlsx-9. Assert silence via:
  ```bash
  diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
  diff -q  skills/docx/scripts/_soffice.py skills/xlsx/scripts/_soffice.py
  diff -q  skills/docx/scripts/_errors.py  skills/xlsx/scripts/_errors.py
  diff -q  skills/docx/scripts/preview.py  skills/xlsx/scripts/preview.py
  diff -q  skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
  ```
- **Mode flag:** Standard (no `[LIGHT]`).
- **Cross-5 envelope rename:** Backlog-row literal envelope `type`
  `MergedCellsRequireHTML` is renamed to `GfmMergesRequirePolicy`
  per D14 (cross-5 envelope public-contract decision).
- **Reference docs:**
  - `xlsx_read/` public surface: [`skills/xlsx/scripts/xlsx_read/__init__.py`](../skills/xlsx/scripts/xlsx_read/__init__.py).
  - `xlsx_read/` types / WorkbookReader contract: [`skills/xlsx/scripts/xlsx_read/_types.py`](../skills/xlsx/scripts/xlsx_read/_types.py).
  - Sibling emit-side package (architecture precedent): [`skills/xlsx/scripts/xlsx2csv2json/__init__.py`](../skills/xlsx/scripts/xlsx2csv2json/__init__.py).
  - Round-trip counterpart (inverse direction): [`skills/xlsx/scripts/md_tables2xlsx/__init__.py`](../skills/xlsx/scripts/md_tables2xlsx/__init__.py).
  - JSON-shapes contract (shape-contract precedent): [`skills/xlsx/references/json-shapes.md`](../skills/xlsx/references/json-shapes.md).
  - New round-trip contract document (created by this task): `skills/xlsx/references/xlsx-md-shapes.md`.
  - Stylistic task reference: [`docs/tasks/task-010-xlsx-8-readback-master.md`](tasks/task-010-xlsx-8-readback-master.md).

---

## 1. General Description

### 1.1. Goal

Ship a CLI shim `skills/xlsx/scripts/xlsx2md.py` (≤ 60 LOC) plus an
in-skill package `skills/xlsx/scripts/xlsx2md/` that converts an `.xlsx`
workbook into a structured Markdown document with per-sheet H2 sections,
per-table H3 headings, and per-table auto-selected GFM or HTML `<table>`
emission, delegating ALL reader logic to the `xlsx_read` foundation
library.

### 1.2. Motivation

- **Closes the read-back-to-markdown gap.** `md_tables2xlsx.py` (xlsx-3)
  converts markdown tables into `.xlsx`; xlsx-9 is the inverse, completing
  the `xlsx → md → edits → xlsx` pipeline.
- **Symmetric round-trip pair to xlsx-3.** Agent edit loops operate
  natively in markdown; xlsx-9 enables a clean `xlsx → md → AI-edits
  → md_tables2xlsx → xlsx` workflow without intermediate CSV/JSON
  serialisation.
- **Reuses the xlsx_read foundation.** All reader complexity (merge
  resolution, ListObjects, gap-detect, multi-row headers, hyperlinks,
  stale-cache, encryption / macro probes) is already implemented in
  `xlsx_read/`; xlsx-9 is emit-only work, bounded in scope like xlsx-8.
- **Bread-and-butter for agent edit loops.** Markdown is the LLM-native
  diff and review format; outputting `.xlsx` content as markdown lets
  orchestration agents read, edit, and write back without round-tripping
  through JSON or CSV.

### 1.3. Connection with the existing system

**Imports (consumed without modification):**
- `xlsx_read.open_workbook`, `xlsx_read.WorkbookReader`,
  `xlsx_read.SheetInfo`, `xlsx_read.TableRegion`, `xlsx_read.TableData`,
  `xlsx_read.MergePolicy`, `xlsx_read.TableDetectMode`,
  `xlsx_read.DateFmt`, plus typed exceptions
  (`EncryptedWorkbookError`, `MacroEnabledWarning`,
  `OverlappingMerges`, `AmbiguousHeaderBoundary`, `SheetNotFound`).
- `_errors.report_error`, `_errors.add_json_errors_argument`
  (cross-5 envelope — 4-skill replicated file; read-only use, not modified).

**Activates round-trip contract at merge:**
- xlsx-3 (`md_tables2xlsx/tests/`) — `test_live_roundtrip_xlsx_md`
  is gated `@unittest.skipUnless(xlsx2md_available(), ...)` and flips to
  live when `import xlsx2md` succeeds after this task lands.
- New file `skills/xlsx/references/xlsx-md-shapes.md` — frozen
  xlsx-9 ↔ xlsx-3 round-trip contract (mirrors `json-shapes.md` for
  xlsx-2 ↔ xlsx-8).

**Out of scope (separate tickets, do NOT touch):**
- xlsx-10.B (xlsx-7 refactor to consume `xlsx_read/`) — ownership-bounded
  14-day timer starts at xlsx-9 merge; not this task.
- xlsx-8 / xlsx-8a / xlsx-2 — no modifications to any existing shim or
  package.

### 1.4. Honest scope (v1 — explicitly out of scope)

These items are **deliberately deferred**. Each is documented in the
relevant module docstring AND locked by a regression test where applicable.

- **(a)** Rich-text spans (bold/italic runs inside a single cell) →
  plain-text concat. Delegated to `xlsx_read._values.extract_cell`.
- **(b)** Cell styles (color / font / fill / border / alignment /
  conditional formatting) → dropped without warning. Markdown has no
  cell-style representation.
- **(c)** Comments → dropped. Deferred to v2 sidecar pattern à la
  docx-4 (`xlsx2md.comments.json`).
- **(d)** Charts / images / shapes → dropped. `preview.py` remains the
  canonical visual path.
- **(e)** Pivot tables → unfold to static cached values (requires
  `xlsx_recalc.py` upstream for fresh values).
- **(f)** Data validation dropdowns → dropped without warning.
- **(g)** Formulas without cached value → warning + empty cell; OR
  formula string emitted in `data-formula` HTML attribute when
  `--include-formulas` is active.
- **(h)** Shared / array formulas → cached value only.
- **(i)** ListObjects `headerRowCount=0` handling — delegated to
  `xlsx_read.tables` (R2-M3 / single source of truth, NOT duplicated in
  xlsx2md). xlsx-9 inherits: `headerRowCount=0` → synthetic `col_1..col_N`
  headers emitted by the library. **Markdown emit per-mode:**
  - Pure GFM: emit synthetic visible header row `| col_1 | col_2 | ... |`
    + separator row (without separator GFM cannot be parsed as a table).
  - HTML: synthetic `<thead>` with `col_1..col_N` `<th>` cells emitted
    (D13 lock — downstream-parser symmetry with GFM; xlsx_read library
    returns synthetic headers in `TableData.headers` regardless of emit
    mode).
  - Hybrid: auto-promote to HTML (mirrors R2-M1 formula-promotion logic).
  - All three modes: warning in `summary.warnings`
    `"Table 'X' had no headers; emitted synthetic col_1..col_N"`.
- **(j)** Diagonal borders / sparklines / camera objects → dropped
  without warning (not renderable in markdown).
- **(k)** `--header-rows smart` vs `--header-rows auto` produce different
  output shapes on metadata-banner workbooks: `smart` shifts past the
  banner and emits a flat leaf-key header; `auto` keeps the merge-derived
  multi-level form (` › `-flattened in GFM, `<thead>` with multiple `<tr>`
  in HTML). This is intentional — `smart` for "skip the metadata I don't
  want", `auto` for "preserve the multi-level header band". Inherited
  honest-scope from xlsx-8a-09 / TASK 011 R11.
- **(l)** Hyperlink scheme allowlist defaults to `{http, https, mailto}`.
  Schemes outside the allowlist emit text-only with a warning (NOT a
  fail). To allow all schemes (NOT recommended), pass
  `--hyperlink-scheme-allowlist '*'`. To strip all hyperlinks, pass
  `--hyperlink-scheme-allowlist ""`. Parity with xlsx-8a-03 / Sec-MED-2.
- **(m)** Hyperlinks are always extracted (D5 lock — no
  `--include-hyperlinks` opt-out flag). This means `xlsx2md.py` always
  opens the workbook in `read_only_mode=False` (or the `--memory-mode`
  override; see R20a) because openpyxl `ReadOnlyCell` does not expose
  `cell.hyperlink`. Memory cost: ~5-10× the workbook file size on disk.
  On 15 MB workbooks this is ~75-150 MB Python heap; on 100 MB workbooks
  ~0.5-1 GB. Inherited honest-scope from xlsx-8 §14.1 C1 fix.
  **Workaround for memory-constrained CI**: pass `--memory-mode=streaming`
  (hyperlinks become unreliable per (l); explicit trade-off).
- **(R3-H1 lock)** `--sanitize-sheet-names` option **dropped entirely**.
  xlsx-3's `naming.py` sanitisation (e.g., `History` → `History_`,
  >31 UTF-16 chars truncated) is xlsx-3's write-side contract.
  xlsx-9 reads sheet names verbatim from `xl/workbook.xml/<sheets>` and
  emits them verbatim in `## H2` headings. The asymmetry (`History` →
  `## History` in xlsx-9, `## History_` after xlsx-3 round-trip) is
  expected, documented in `xlsx-md-shapes.md`, and NOT a regression.

---

## 2. Requirements Traceability Matrix (RTM)

**Convention:** Epics (`E*`) group cohesive feature areas; Issues (`R*`)
are atomic, testable requirements within an Epic. Each sub-feature is
independently testable. MVP column marks ship-blocking work for v1.

---

### Epic E1 — Package + Shim Skeleton

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R1** | CLI shim `xlsx2md.py` (≤ 60 LOC) | ✅ | (a) `skills/xlsx/scripts/xlsx2md.py` is a re-export shim of ≤ 60 LOC that `sys.path.insert`s its parent and calls `xlsx2md.main(sys.argv[1:])`; (b) shim is directly executable as `python3 xlsx2md.py INPUT.xlsx`; (c) no business logic in the shim — all logic lives in `xlsx2md/`; (d) regression test: LOC count of `xlsx2md.py` is ≤ 60 (fail if exceeded). |
| **R2** | In-skill package `xlsx2md/` with single-responsibility modules | ✅ | (a) Package directory `skills/xlsx/scripts/xlsx2md/` with `__init__.py`, `cli.py`, `emit_gfm.py`, `emit_html.py`, `emit_hybrid.py`, `exceptions.py`; (b) `cli.py` owns `build_parser()` and `main(argv)` orchestrator; (c) `emit_gfm.py` owns pure-GFM table serialisation; (d) `emit_html.py` owns HTML `<table>` serialisation with `colspan`/`rowspan`; (e) `emit_hybrid.py` owns per-table format selector (auto-select GFM vs HTML); (f) `exceptions.py` owns all `_AppError` subclasses; (g) no module exceeds 700 LOC (xlsx skill precedent). |
| **R3** | Package import hygiene and toolchain | ✅ | (a) `sys.path.insert(0, parent)` once in the shim so `xlsx2md` + `_errors` resolve without installation; (b) `from xlsx2md import main, convert_xlsx_to_md, _AppError, ...` re-export list in `__init__.py` mirrors xlsx-3 / xlsx-2 pattern; (c) `ruff check scripts/` is green (reuses `pyproject.toml` from xlsx-10.A; no new banned-api rule needed — `xlsx2md` is allowed to import from `xlsx_read` public surface, not `xlsx_read._*`). |

---

### Epic E2 — Core CLI Surface and Backward-Compatible Defaults

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R4** | Input + output positional / optional args | ✅ | (a) Positional `INPUT` — path to `.xlsx` / `.xlsm`; (b) optional positional `[OUTPUT]` — path to output `.md` file, OR `-` for explicit stdout; (c) when `OUTPUT` is omitted entirely, output goes to stdout; (d) when `OUTPUT` is a path and its parent directory does not exist, auto-create parent dir (csv2xlsx parity); (e) cross-7 H1 same-path canonical-resolve guard: `Path.resolve()` on both INPUT and OUTPUT — if equal, exit 6 `SelfOverwriteRefused`; guard applies even when extensions differ (`.xlsx` vs `.md`). |
| **R5** | Sheet selector | ✅ | (a) `--sheet NAME` — process single named sheet only; (b) `--sheet all` (default) — process all visible sheets in document order from `xl/workbook.xml/<sheets>`; (c) missing sheet name → exit 2 envelope `SheetNotFound` (typed exception from `xlsx_read` re-mapped to envelope); (d) `--include-hidden` opt-in (default: skip sheets with `state="hidden"` or `state="veryHidden"`). |
| **R6** | Default flag values (backward-compat lock) | ✅ | (a) `--format hybrid` default (per-table auto-select); (b) `--header-rows auto` default; (c) `--gap-rows 2` default (M4 VDD-adversarial fix — single empty row is not a reliable splitter); (d) `--gap-cols 1` default; (e) `--gfm-merge-policy fail` default (fail-loud over silent lossy); (f) `--datetime-format ISO` default (xlsx-3 round-trip parity); (g) `--include-formulas` off by default (cached value only); (h) regression test pins the all-flags-omitted output shape against a synthetic fixture: single-sheet, single-row header, no merges, ISO dates, no formulas, GFM output (because `hybrid` + no-merges selects GFM). |

---

### Epic E3 — Multi-Sheet and Multi-Table Detection

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R7** | Multi-sheet output with H2 headings | ✅ | (a) Each visible sheet in document order produces a `## SheetName` H2 section; (b) document order is derived from `WorkbookReader.sheets()` which reads `xl/workbook.xml/<sheets>` ordering; (c) hidden sheets are skipped by default; `--include-hidden` includes them; (d) `--sheet NAME` suppresses H2 headings entirely (single-sheet output has no H2 wrapper — caller already knows which sheet); (e) sheet names are emitted verbatim with no sanitisation (markdown has no 31-char limit, no forbidden-char restrictions). |
| **R8** | Multi-table detection (3-tier) | ✅ | (a) Tier-1 ListObjects from `xl/tables/tableN.xml` — each table produces a `### TableName` H3 heading, document order preserved; (b) Tier-2 sheet-scope named ranges (`<definedName>` with `localSheetId`) — each named range produces a `### RangeName` H3 heading; (c) Tier-3 gap-detect fallback — produces headings `### Table-1`, `### Table-2`, … in discovery order; (d) `--no-table-autodetect` disables Tier-1 + Tier-2 (only gap-detect runs); H3 headings still emitted for gap-detected tables; implemented as post-call filter `r.source == "gap_detect"` on the result of `detect_tables(mode="auto")` (D7 — no `xlsx_read` API extension); (e) `--no-split` disables all splitting — treats whole sheet as one table (no H3 heading emitted, whole-sheet single-region via `detect_tables(mode="whole")`); (f) when `--no-table-autodetect` post-call gap-filter yields zero regions for a sheet (dense data, no gap separators), shim falls back to whole-sheet emission for that sheet and surfaces an info warning `"no gap-detected tables found; emitting whole-sheet markdown for <SheetName>"` — exit code unchanged (typically 0). |
| **R9** | Gap-detect configuration | ✅ | (a) `--gap-rows N` (default 2) — minimum consecutive fully-empty rows to trigger a table split; (b) `--gap-cols N` (default 1) — minimum consecutive fully-empty columns to trigger a table split; (c) both forwarded to `WorkbookReader.detect_tables(..., gap_rows=N, gap_cols=N)`; (d) regression test confirms that a single empty row inside a table (common visual separator) does NOT split with the default `--gap-rows 2`; (e) regression test confirms `--gap-rows 1` DOES split on a single empty row. |

---

### Epic E4 — Format Engine: GFM, HTML, and Hybrid

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R10** | `--format gfm` — pure GFM emission | ✅ | (a) Each table emits as a standard GFM pipe table: header row + `|---|---|` separator + body rows; (b) pipe `\|` characters in cell values are escaped as `\|`; (c) cell newlines (ALT+ENTER, `\n` in openpyxl) → `<br>` (round-trip contract with xlsx-3 R9.c); (d) hyperlinks emitted as `[text](url)` in GFM mode; (e) `--format gfm` + merged body cells defaults to exit 2 `GfmMergesRequirePolicy` unless `--gfm-merge-policy` is explicitly set to `duplicate` or `blank`. |
| **R11** | `--format html` — HTML `<table>` emission | ✅ | (a) Each table emits as a full HTML `<table>` block with `<thead>` + `<tbody>`; (b) merged cells use `colspan` / `rowspan` attributes on the anchor cell; child cells are suppressed from output (reverse of xlsx-3's `_expand_spans` algorithm); (c) pipe `\|` characters in cell values are escaped as `&#124;`; (d) cell newlines → `<br>` inside HTML cells; (e) hyperlinks emitted as `<a href="url">text</a>`; (f) `--include-formulas`: formula-cells gain `data-formula="=A1+B1"` attribute on the `<td>` element. |
| **R12** | `--format hybrid` — per-table auto-select (default) | ✅ | (a) For each table independently: if merges == ∅ AND single-row header AND no cell-newlines, emit GFM; otherwise emit HTML; (b) `--include-formulas` in hybrid mode: any table containing ≥ 1 formula-cell is promoted from GFm to HTML (R2-M1 lock) so `data-formula` attributes can be emitted; tables without formula cells remain GFM; (c) `headerRowCount=0` tables are promoted to HTML in hybrid mode (§1.4 (i)); (d) regression test verifies that a pure-data table (no merges, no formulas, no newlines) produces GFM in hybrid mode; (e) regression test verifies that a table with one merge produces HTML in hybrid mode. |
| **R13** | M7 lock — `--format gfm` + `--include-formulas` is an error | ✅ | (a) If `--format gfm` AND `--include-formulas`, exit 2 with envelope `IncludeFormulasRequiresHTML` before any file I/O; (b) error code is 2; envelope shape is cross-5 v1 `{v:1, error, code:2, type:"IncludeFormulasRequiresHTML", details:{}}`; (c) `--format html` + `--include-formulas` is valid (no error); (d) `--format hybrid` + `--include-formulas` is valid and triggers R12.b promotion rule; (e) regression test via `xlsx2md.py fixture.xlsx --format gfm --include-formulas` → exit 2 before opening workbook. |
| **R10a** | `--hyperlink-scheme-allowlist` URL scheme filter (Sec-MED-2 — NOT deferred) | ✅ | (a) New flag `--hyperlink-scheme-allowlist CSV` (default `http,https,mailto`); comma-separated case-insensitive scheme list; (b) for each hyperlink cell, parse `urllib.parse.urlsplit(href).scheme.lower()`; if NOT in allowlist — **GFM mode**: emit cell as plain text only (URL stripped; only the `[text]` part without `(url)`); stderr warning `"cell SHEET!A1: hyperlink scheme '<scheme>' not in allowlist; emitted text-only"` — **HTML mode**: emit `<td>` with cell text only (no `<a href>`); same stderr warning; (c) special case: empty scheme (`href="page.html"` — relative URL) treated as `http`; documented honest-scope; (d) `--hyperlink-scheme-allowlist ""` (empty) → all hyperlinks stripped to text; `--hyperlink-scheme-allowlist '*'` → all schemes allowed (NOT recommended; documented in `--help`); (e) `javascript:` / `data:` / `vbscript:` / `file:` / `vscode://` / `slack://` blocked by default — xlsx-9 emits clickable HTML `<a href>` into renderers (browser preview, Marp, GitHub, Obsidian, IDE preview) making attack surface strictly higher than xlsx-8's JSON-object emission; mirror xlsx-8a-03 / Sec-MED-2 fix; (f) regression test fixture with `javascript:alert(1)` + `https://ok.com` + `mailto:x@y` → only latter two emit `<a href>` / `[text](url)`; `javascript:` cell emits text-only + warning. |

---

### Epic E5 — Header Handling, Merges, and Inline Content

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R14** | Multi-row header detection and emission | ✅ | (a) `--header-rows auto` (default): `WorkbookReader.read_table(region, header_rows="auto")` auto-detects column-spanning merges in top rows as the header band; (b) `--header-rows N` (int ≥ 1): forces exactly N rows as header; (c) **HTML mode**: multi-row header emits as `<thead>` with multiple `<tr>` rows; colspan in the top header row is preserved via `colspan` attribute; (d) **Pure GFM mode**: multi-row header is degraded to a single row where sub-headings are joined with ` › ` (U+203A SINGLE RIGHT-POINTING ANGLE QUOTATION MARK, D6 lock) — e.g., `2026 plan › Q1`; a `summary.warnings` entry is emitted for each table that was degraded; (e) `AmbiguousHeaderBoundary` warning from `xlsx_read` is relayed to `summary.warnings`, never raised as an error; (f) integer `--header-rows N` and `--header-rows auto` both route through the same `xlsx_read.read_table(..., header_rows=...)` call path — emit-side code does NOT branch on which form was used; the distinction is purely in what value is passed to the library; (g) `--header-rows smart`: invokes `xlsx_read.read_table(region, header_rows="smart")` which runs `_detect_data_table_offset` (type-pattern heuristic) to skip metadata blocks above the data table; on hit (score ≥ 3.5), `region.top_row` shifts past the metadata and detection proceeds as a 1-row header — inherited from xlsx-8a-09 / TASK 011 R11; same library entry point, same heuristic; documented in `references/xlsx-md-shapes.md`; honest-scope per §1.4 (k): `smart` and `auto` produce different output shapes; (h) combining `--header-rows N` (explicit integer) with `--tables != whole` (i.e., multi-table mode where per-table header counts may differ) → exit 2 envelope `HeaderRowsConflict` with `details {n_requested: N, table_count: M, suggestion: "use --header-rows auto or --header-rows smart for multi-table workbooks"}` — inherited from xlsx-8 §14.5 M1 fix; rationale: a fixed N applied uniformly across tables with varying header structures silently corrupts data (header rows misclassified as body, or first body row misclassified as header). |
| **R15** | Merged body-cell handling (GFM policy) | ✅ | (a) `--gfm-merge-policy fail` (default): presence of merges in a table body forces the table to emit as HTML (because the caller has not opted into a lossy GFM strategy); in `--format gfm` mode, this exits 2 `GfmMergesRequirePolicy`; (b) `--gfm-merge-policy duplicate`: merged child cells receive a copy of the anchor cell's value; a `summary.warnings` entry is emitted with the count of duplicated cells per table; (c) `--gfm-merge-policy blank`: merged child cells are emitted as empty; a `summary.warnings` entry is emitted; (d) `--format hybrid` with body merges: the table is automatically promoted to HTML (bypassing the `--gfm-merge-policy` flag entirely — hybrid handles it natively); (e) regression test: `--gfm-merge-policy duplicate` on a fixture with a 2-cell horizontal merge → second cell repeats anchor value + warning in output. |
| **R16** | Inline content — cell newlines, pipe escaping, hyperlinks | ✅ | (a) Cell newline (`\n`, openpyxl `ALT+ENTER` linebreak) → `<br>` in both GFM and HTML output (GFM inline HTML is valid per spec; xlsx-3 R9.c round-trip mirror); (b) Pipe character `|` in cell value → `\|` escape in GFM table cells; `&#124;` in HTML `<td>` content; (c) `cell.hyperlink` (from `xlsx_read` `include_hyperlinks=True` call) → `[text](url)` in GFM cells; `<a href="url">text</a>` in HTML cells; (d) hyperlink with empty text (`cell.value == ""`): GFM emits `[](url)` (valid markdown); HTML emits `<a href="url"></a>`; (e) hyperlinks are always read from `xlsx_read` with `include_hyperlinks=True` (xlsx-9 does NOT gate this behind a flag — markdown representation of a link is lossless; this differs from xlsx-8 where JSON/CSV shape is more constrained). |
| **R17** | Numbers, dates, formula cells | ✅ | (a) `--datetime-format ISO` (default): date/datetime cells emitted as `YYYY-MM-DD` / `YYYY-MM-DDTHH:MM:SS`; (b) `--datetime-format excel-serial`: emit the Excel day-count serial (integer or float) as a string; (c) `--datetime-format raw`: emit Python repr of value (for Python-callers only; CLI users see same-as-ISO due to D10 stream-emit note); (d) `cell.number_format` heuristic preserved from `xlsx_read._values.extract_cell` — `#,##0.00` formats emit formatted strings, percentage formats emit `%`-suffixed strings, leading-zero text columns emit verbatim; (e) formula cell with cached value: emit cached value; formula cell without cached value (stale): emit empty + relay `summary.warnings` stale-cache warning from `xlsx_read`. |

---

### Epic E6 — Numbers, Dates, and Formula Attributes

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R18** | `--include-formulas` — `data-formula` attribute | ✅ | (a) When `--include-formulas` is active and `--format html` (or `--format hybrid` with formula-containing tables promoted to HTML): formula cells gain `data-formula="=<formula string>"` on the `<td>` element; (b) cached value (if present) is still emitted as the visible cell content; (c) formula cells where `cell.value is None` (stale cache): `<td data-formula="=..." class="stale-cache"></td>` with empty content + stale-cache warning; (d) `--format gfm` + `--include-formulas` exits 2 `IncludeFormulasRequiresHTML` (M7 lock, R13); (e) regression test: fixture with `=A1+B1` formula → verifies `data-formula` attribute present in HTML output. |
| **R19** | `--datetime-format` flag | ✅ | (a) Three accepted values: `ISO` (default), `excel-serial`, `raw`; (b) forwarded to `WorkbookReader.read_table(..., datetime_format=...)` via `DateFmt` type; (c) invalid value → argparse error with usage message; (d) `excel-serial` note: Excel 1900 leap-year bug is NOT compensated (emits true day-count from 1899-12-30; serials 1–59 are off by one day vs Excel display — honest scope from `xlsx_read` module docstring); (e) regression test: a date cell `2026-01-15` with `--datetime-format excel-serial` emits the expected serial number. |
| **R20** | Number format heuristic (delegated to `xlsx_read`) | ✅ | (a) `extract_cell` in `xlsx_read._values` applies `number_format` heuristic — xlsx-9 receives formatted strings, NOT raw floats, for `#,##0.00` / `0%` / `0.0%` / date format codes; (b) xlsx-9 emits the formatted string as-is in the markdown cell (no re-formatting); (c) leading-zero text columns (e.g., `007`, typed as text in Excel) are preserved as-is from `xlsx_read`; (d) raw float values (unknown format codes) emitted as Python `str(float)` — same as `xlsx_read` default; (e) regression test: fixture with `#,##0.00` formatted cell `1234.5` → markdown cell contains `"1,234.50"`. |
| **R20a** | `--memory-mode {auto,streaming,full}` — openpyxl read-mode exposure (xlsx-8a-11 / R13 parity) | ✅ | (a) New flag `--memory-mode {auto,streaming,full}` (default `auto`); maps to `xlsx_read.open_workbook(..., read_only_mode=...)`: `auto` → library default (size-threshold-driven; ≥ 100 MiB → streaming); `streaming` → force `read_only_mode=True`; `full` → force `read_only_mode=False` (in-memory; correct merge and hyperlink handling); (b) interaction with hyperlinks (D5 always-on): when `memory_mode != "full"` AND library auto-switches to streaming for large workbooks, hyperlinks become unreliable (openpyxl `ReadOnlyCell.hyperlink` is not exposed); shim surfaces `summary.warnings` entry `"hyperlinks unreliable in streaming mode; pass --memory-mode=full or extract on a smaller workbook"`; (c) `--memory-mode=full` on a workbook ≥ 100 MiB in a CI environment with capped RSS (≤ 4 GB) may OOM — shim does NOT raise pre-emptively; documented in `--help` epilogue and §1.4 (m); (d) inherited from xlsx-8a-11 / TASK 011 R13 — same library plumbing, same flag surface, same defaults; (e) regression test: synthetic 15 MB workbook + `--memory-mode=streaming` → peak RSS ≤ 200 MB (measured via `tracemalloc`; marked `@unittest.skipUnless(SLOW)` for CI duration). |

---

### Epic E7 — Cross-Cutting Parity

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R21** | Cross-3 — encrypted input | ✅ | (a) `xlsx_read.open_workbook` raises `EncryptedWorkbookError` on OPC `EncryptedPackage` stream; (b) shim catches → emit cross-5 envelope `{v:1, error:"...", code:3, type:"EncryptedWorkbookError", details:{filename:"<basename>"}}` to stderr; (c) exit 3; (d) `details.filename` is basename only (no full-path leak, parity with xlsx-8 / xlsx_read §13.2 fix); (e) regression test with encrypted fixture → exit 3 + exact envelope shape assertion. |
| **R22** | Cross-4 — macro-bearing input | ✅ | (a) `xlsx_read.open_workbook` emits `MacroEnabledWarning` via `warnings.warn` for `.xlsm` inputs; (b) shim captures via `warnings.catch_warnings(record=True)` and surfaces the text in `summary.warnings` or a stderr line; (c) extraction CONTINUES — `.xlsm` files are read and converted normally; (d) `--json-errors` mode: macro warning appears before the summary (not inside the error envelope, which is reserved for failures); (e) regression test with `.xlsm` fixture → exit 0 + warning text present in stderr. |
| **R23** | Cross-5 — `--json-errors` envelope | ✅ | (a) `_errors.add_json_errors_argument(parser)` adds the standard `--json-errors` flag; (b) ALL fail paths route through `_errors.report_error()` — no ad-hoc `sys.exit()` calls outside the envelope helper; (c) envelope shape `{v:1, error, code, type, details}` is byte-identical to xlsx-2 / xlsx-3 / xlsx-8 (regression via `_errors._SCHEMA_VERSION == 1` assertion); (d) `code` is NEVER 0 (guarded by `report_error`); (e) regression test: any failure path with `--json-errors` → stdout/stderr contains valid JSON, parseable by `json.loads`, with all five keys present; (f) unhandled exception terminal envelope (xlsx-8 §14.4 H3 inheritance): exceptions outside the documented dispatch table (`PermissionError`, `OSError`, generic `RuntimeError`, etc.) are caught by a terminal envelope branch and rendered as `{"v":1, "error":"Internal error: <ClassName>", "code":7, "type":"InternalError", "details":{}}` — raw exception message is dropped to prevent absolute-path leaks from openpyxl / `xlsx_read` internals; for local debugging, run without `--json-errors` to see the Python traceback; exit code 7 (parity with xlsx-8 `_AppError` register). |
| **R24** | Cross-7 — H1 same-path guard | ✅ | (a) Canonical-resolve via `Path.resolve()` follows symlinks before comparison (csv2xlsx parity); (b) same resolved path for INPUT and OUTPUT → exit 6 `SelfOverwriteRefused`; (c) guard applies even when INPUT and OUTPUT have different extensions (`.xlsx` vs `.md`) — paranoia guard against `cp` misnaming; (d) regression test: symlink `out.md -> input.xlsx` → exit 6; (e) regression test: `input.xlsx` and `output.md` are different inodes → exit 0. |

---

### Epic E8 — Round-Trip Contract, Honest-Scope Locks, and Tests

| ID | Requirement | MVP? | Sub-features |
| --- | --- | --- | --- |
| **R25** | `xlsx-md-shapes.md` round-trip contract document | ✅ | (a) New file `skills/xlsx/references/xlsx-md-shapes.md` documenting the xlsx-9 ↔ xlsx-3 contract (mirrors `json-shapes.md`); (b) §1 scope: GFM and HTML output shapes, H2/H3 heading structure, cell-content encoding rules; (c) §2 sheet-name asymmetry: xlsx-9 emits sheet names verbatim in `## H2`, xlsx-3 `naming.py` may sanitise on write-back (`History` → `History_`) — documented as EXPECTED, not a regression; (d) §3 round-trip limitations honest scope (merges un-merge on xlsx-3 write-back, formulas emit as cached values, styles dropped, comments dropped); (e) §4 live round-trip activation (test gate mechanism). |
| **R26** | xlsx-3 live round-trip test flip | ✅ | (a) After this task merges, `import xlsx2md` succeeds in the test environment; (b) `@unittest.skipUnless(xlsx2md_available(), ...)` gate in xlsx-3's `test_live_roundtrip_xlsx_md` method flips to live; (c) the test body performs `xlsx2md(fixture.xlsx) → fixture.md → md_tables2xlsx(fixture.md) → roundtrip.xlsx → xlsx2md(roundtrip.xlsx)` and asserts cell CONTENT byte-identical (NOT sheet-name byte-identical — see R25.c); (d) NO modifications to xlsx-3 source code beyond uncommenting / activating the skip gate; (e) regression: xlsx-3's full existing test suite (all tests except the newly-activated gate) PASS unchanged. |
| **R27** | Test suite — ≥ 14 E2E + full unit suite per module | ✅ | (a) At least 14 named E2E scenarios (§5.5 fixed list); (b) unit tests per module: `cli.py`, `emit_gfm.py`, `emit_html.py`, `emit_hybrid.py`, `exceptions.py` — at minimum 8 unit tests per module; (c) `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0; (d) all existing xlsx-* E2E suites green (no-behaviour-change gate); (e) 5-file silent `diff -q` gate stays silent (§0 cross-skill replication). |

---

## 3. Use Cases

> **Convention:** Actors: `User` (CLI invoker / orchestrating agent),
> `xlsx2md shim` (System), `xlsx_read library` (System), `OS / FS`
> (External system).

### UC-01 — Convert single sheet to GFM (happy path, default flags)

**Actors:** User, xlsx2md shim, xlsx_read library.

**Preconditions:**
- Input `.xlsx` is unencrypted, readable, ≥ 1 visible sheet.
- The first (and only selected) sheet has a single-row header in row 1,
  no merged cells, no formula cells, no hyperlinks.

**Main Scenario:**
1. User runs `python3 xlsx2md.py report.xlsx`.
2. Shim parses argv; binds defaults: `--sheet all`, `--format hybrid`,
   `--header-rows auto`, `--gap-rows 2`, `--gap-cols 1`,
   `--gfm-merge-policy fail`, `--datetime-format ISO`, no formulas.
3. Shim invokes `xlsx_read.open_workbook(Path("report.xlsx"))`.
4. Shim calls `reader.sheets()`; filters out hidden sheets.
5. For each visible sheet: `reader.detect_tables(sheet, mode="auto",
   gap_rows=2, gap_cols=1)` → one region (whole sheet, no ListObjects,
   no gap splits).
6. Shim calls `reader.read_table(region, header_rows="auto",
   merge_policy="anchor-only", include_hyperlinks=True,
   include_formulas=False, datetime_format="ISO")` → `TableData`.
7. Hybrid selector: merges == ∅, single-row header, no newlines → GFM.
8. GFM emitter writes `| col1 | col2 | ... |` header + separator +
   body rows to stdout.
9. Exit 0.

**Alternative Scenarios:**
- **A1: Output to file.** `python3 xlsx2md.py report.xlsx output.md`
  → file written; no stdout output.
- **A2: Single sheet via `--sheet`.** `--sheet "Sheet1"` → no `## H2`
  heading emitted (single-sheet output has no H2 wrapper).
- **A3: Hidden sheet.** Skipped silently; `--include-hidden` opts in.
- **A4: Empty sheet (zero data rows).** Header row only output; exit 0.

**Postconditions:**
- Output is valid GFM (parseable by any CommonMark renderer).

**Acceptance Criteria:**
- ✅ Exit code 0.
- ✅ Output is parseable as GFM table (`| header |` + `|---|` separator).
- ✅ No `openpyxl.*` type ever leaks into markdown output (regression via
  `type()` audit on `TableData.rows` values).
- ✅ Datetimes formatted per ISO-8601 default.
- ✅ Exercises: R4, R5, R6, R7, R10, R17, R20.

---

### UC-02 — Convert multi-sheet workbook to markdown

**Actors:** User, xlsx2md shim, xlsx_read library.

**Preconditions:**
- Input `.xlsx` with three visible sheets (`Sales`, `Costs`, `Summary`)
  and one hidden sheet (`_Internal`).

**Main Scenario:**
1. User runs `python3 xlsx2md.py budget.xlsx budget.md`.
2. Shim processes sheets in document order from `WorkbookReader.sheets()`.
3. Hidden sheet `_Internal` is skipped.
4. For each visible sheet, shim emits `## SheetName` H2 heading
   followed by the table content.
5. Output file `budget.md` contains `## Sales`, `## Costs`, `## Summary`
   in that order.
6. Exit 0.

**Alternative Scenarios:**
- **A1: `--include-hidden`.** Hidden sheet `_Internal` is included;
  `## _Internal` heading appears in document order.
- **A2: `--sheet Sales`.** Only `## Sales` section emitted (but wait —
  single-sheet mode suppresses H2 heading; output is just the table).
  Actually: no H2 heading when `--sheet NAME` is used (D10 analogue).
- **A3: Sheet name contains special markdown chars (`## Sheet [1]`).
  Emitted verbatim — no escaping of `[`, `]` in H2 headings (markdown
  headings are not inline content; only cell values need escaping).

**Postconditions:**
- `budget.md` exists; each visible sheet appears as `## SheetName` section.

**Acceptance Criteria:**
- ✅ Exit code 0.
- ✅ Exactly 3 `## ` headings in output (hidden sheet absent).
- ✅ Heading order matches `xl/workbook.xml/<sheets>` document order.
- ✅ `--include-hidden` produces 4 `## ` headings.
- ✅ Exercises: R5, R7.

---

### UC-03 — Multi-table sheet via ListObjects

**Actors:** User, xlsx2md shim, xlsx_read library.

**Preconditions:**
- Input `.xlsx` with one sheet `"Budget"` containing two ListObjects
  (`xl/tables/table1.xml` = `RevenueTable`, `xl/tables/table2.xml` =
  `CostsTable`) and no gap between them.

**Main Scenario:**
1. User runs `python3 xlsx2md.py budget.xlsx`.
2. Shim calls `reader.detect_tables("Budget", mode="auto", ...)`.
   Library returns two `TableRegion` objects with `source="listobject"`.
3. For each region, shim emits `### TableName` H3 heading followed by
   the table content.
4. Output: `## Budget` → `### RevenueTable` → table → `### CostsTable`
   → table.
5. Exit 0.

**Alternative Scenarios:**
- **A1: `--no-table-autodetect`.** Disables Tier-1 + Tier-2; shim calls
  `detect_tables(mode="auto")` then filters `r.source == "gap_detect"`.
  Since no gap separator exists, a single whole-region is produced
  (or gap-detect may find no split); fallback heading `Table-1`.
- **A2: `--no-split`.** Calls `detect_tables(mode="whole")`; one region
  covering entire sheet; no H3 heading emitted.
- **A3: ListObject with `headerRowCount=0`.** xlsx_read returns synthetic
  `col_1..col_N` headers + warning. In hybrid mode, table is auto-promoted
  to HTML (§1.4 (i)); warning relayed in `summary.warnings`.

**Postconditions:**
- Output contains `### RevenueTable` and `### CostsTable` headings.

**Acceptance Criteria:**
- ✅ Exit code 0.
- ✅ Exactly 2 `### ` headings in output.
- ✅ H3 heading text matches ListObject name verbatim.
- ✅ Table order is document order (deterministic across re-reads).
- ✅ `--no-table-autodetect` produces ≤ 1 `### ` heading (gap fallback).
- ✅ Exercises: R8, R12.

---

### UC-04 — Merged body cells force HTML

**Actors:** User, xlsx2md shim, xlsx_read library.

**Preconditions:**
- Input sheet has a table with a horizontal 2-cell body merge in row 3
  (columns B and C merged; value `"Total"`).

**Main Scenario (hybrid mode, default):**
1. User runs `python3 xlsx2md.py report.xlsx` (default `--format hybrid`).
2. Hybrid selector: merges ≠ ∅ → promotes table to HTML emission.
3. HTML emitter produces `<td colspan="2">Total</td>` at the merge
   anchor; the child cell (col C) is suppressed.
4. Exit 0.

**Main Scenario (`--gfm-merge-policy fail`, default, with `--format gfm`):**
1. User runs `python3 xlsx2md.py report.xlsx --format gfm`.
2. Table has body merges; `--gfm-merge-policy fail` (default) → exit 2
   `GfmMergesRequirePolicy` envelope before writing any output.

**Alternative Scenarios:**
- **A1: `--gfm-merge-policy duplicate`.** Anchor value `"Total"` is
  duplicated to the child cell (col C). Warning in `summary.warnings`.
  GFM table row: `| ... | Total | Total |`.
- **A2: `--gfm-merge-policy blank`.** Anchor has `"Total"`, child cell
  is empty. Warning in `summary.warnings`. GFM row: `| ... | Total | |`.
- **A3: Vertical merge spanning 3 rows.** HTML: anchor gets
  `rowspan="3"`, rows 2 and 3 suppress the cell. GFM duplicate/blank
  policies handle row-wise.

**Postconditions (hybrid):**
- Output HTML contains `colspan="2"` and child cell suppressed.

**Acceptance Criteria:**
- ✅ Hybrid default: HTML output with `colspan="2"` at anchor; child cell absent from `<tr>`.
- ✅ `--format gfm` (no policy): exit 2 `GfmMergesRequirePolicy`.
- ✅ `--gfm-merge-policy duplicate`: second cell contains anchor value + warning emitted.
- ✅ `--gfm-merge-policy blank`: second cell empty + warning emitted.
- ✅ Exercises: R11, R12, R15.

---

### UC-05 — Multi-row header: HTML `<thead>`, GFM ` › ` flatten

**Actors:** User, xlsx2md shim, xlsx_read library.

**Preconditions:**
- Input sheet with 2-row header: row 1 = `"2026 plan"` merged across
  cols A–C; row 2 = `"Q1"`, `"Q2"`, `"Q3"`.

**Main Scenario (HTML / hybrid with merges):**
1. User runs `python3 xlsx2md.py plan.xlsx --format html`.
2. `WorkbookReader.read_table(region, header_rows="auto")` returns
   `TableData.headers = ["2026 plan › Q1", "2026 plan › Q2", "2026 plan › Q3"]`
   (flattened by xlsx_read with ` › ` separator).
3. HTML emitter reconstructs two `<tr>` rows inside `<thead>`:
   first row: `<th colspan="3">2026 plan</th>`;
   second row: `<th>Q1</th>`, `<th>Q2</th>`, `<th>Q3</th>`.
4. Exit 0.

**Main Scenario (pure GFM):**
1. User runs `python3 xlsx2md.py plan.xlsx --format gfm`.
2. Library returns flattened headers with ` › ` separator.
3. GFM emitter emits single header row:
   `| 2026 plan › Q1 | 2026 plan › Q2 | 2026 plan › Q3 |`.
4. Warning in `summary.warnings`: `"Table 'Sheet1' has multi-row header;
   GFM output flattened with ' › ' separator"`.
5. Exit 0.

**Alternative Scenarios:**
- **A1: `--header-rows 1` explicit.** Only row 1 used as header; row 2
  becomes first data row. No multi-row detection.
- **A2: Ambiguous header boundary.** Library emits
  `AmbiguousHeaderBoundary` warning; shim relays to `summary.warnings`;
  processing continues best-effort.

**Postconditions:**
- HTML output has `<thead>` with correct `colspan` on banner row.
- GFM output has single flattened header row + degradation warning.

**Acceptance Criteria:**
- ✅ HTML output: `<thead>` contains two `<tr>` rows; first `<th>` has `colspan="3"`.
- ✅ GFM output: header row contains ` › ` (U+203A) separator; warning emitted to stderr.
- ✅ Warning is surfaced (not silently swallowed) in GFM mode.
- ✅ `--header-rows 1` suppresses multi-row detection.
- ✅ Exercises: R14.

---

### UC-06 — Hyperlink emission (GFM and HTML modes)

**Actors:** User, xlsx2md shim, xlsx_read library.

**Preconditions:**
- Input sheet with cell B2 containing text `"Click here"` and
  `cell.hyperlink.target = "https://example.com"`.

**Main Scenario (GFM):**
1. User runs `python3 xlsx2md.py links.xlsx --format gfm`.
2. xlsx_read returns `cell.hyperlink` data (include_hyperlinks=True is
   always used internally by xlsx2md, per R16.e).
3. GFM emitter produces `[Click here](https://example.com)` in the
   cell position.
4. Exit 0.

**Main Scenario (HTML):**
1. User runs `python3 xlsx2md.py links.xlsx --format html`.
2. HTML emitter produces `<a href="https://example.com">Click here</a>`
   in the `<td>`.
3. Exit 0.

**Alternative Scenarios:**
- **A1: Empty text hyperlink.** GFM: `[](https://...)`. HTML:
  `<a href="https://..."></a>`.
- **A2: No hyperlink (default cell).** Plain text emitted; no link markup.
- **A3: Hyperlink with special chars in URL.** Emitted verbatim (no
  URL-encoding — `xlsx_read` returns the raw target string).

**Postconditions:**
- Hyperlink text and URL both preserved in output.

**Acceptance Criteria:**
- ✅ GFM mode: cell content is `[text](url)` form.
- ✅ HTML mode: cell content is `<a href="url">text</a>` form.
- ✅ No `=HYPERLINK()` formula syntax emitted (R4-L2 lock parity with xlsx-8).
- ✅ Exercises: R16.

---

### UC-07 — `--include-formulas` interaction with `--format`

**Actors:** User, xlsx2md shim, xlsx_read library.

**Preconditions:**
- Input sheet with cell C3 containing formula `=A3+B3`, cached
  value `42`.

**Scenario A — `--format gfm` + `--include-formulas` → exit 2:**
1. User runs `python3 xlsx2md.py data.xlsx --format gfm --include-formulas`.
2. Shim detects incompatible flag combination BEFORE opening the workbook.
3. Exit 2 with envelope `IncludeFormulasRequiresHTML`
   `{v:1, error:"...", code:2, type:"IncludeFormulasRequiresHTML", details:{}}`.

**Scenario B — `--format html` + `--include-formulas` → valid, `data-formula` emitted:**
1. User runs `python3 xlsx2md.py data.xlsx --format html --include-formulas`.
2. Shim calls `reader.read_table(region, include_formulas=True, ...)`.
3. Cell C3 yields cached value `42` + formula string `"=A3+B3"`.
4. HTML emitter: `<td data-formula="=A3+B3">42</td>`.
5. Exit 0.

**Scenario C — `--format hybrid` + `--include-formulas` → formula tables promoted:**
1. User runs `python3 xlsx2md.py data.xlsx --format hybrid --include-formulas`.
2. Hybrid selector: formula cell present in this table → promote to HTML.
3. HTML output with `data-formula` attribute.
4. Exit 0.

**Postconditions (Scenario B):**
- Output HTML contains `data-formula="=A3+B3"` attribute on the cell.

**Acceptance Criteria:**
- ✅ Scenario A: exit 2 + correct envelope type before any file I/O.
- ✅ Scenario B: exit 0 + `data-formula="=A3+B3"` present in `<td>`.
- ✅ Scenario C: exit 0 + formula table emitted as HTML + `data-formula` present.
- ✅ Non-formula cells in Scenario C remain GFM (hybrid: only formula tables promoted).
- ✅ Exercises: R13, R18.

---

### UC-08 — Same-path guard (`OUTPUT == INPUT` after `Path.resolve()`)

**Actors:** User, xlsx2md shim, OS.

**Preconditions:**
- A symlink `out.md` → `input.xlsx` exists (or user passes both the
  same resolved path).

**Main Scenario:**
1. Shim resolves `INPUT` via `Path.resolve()` → `/tmp/input.xlsx`.
2. Shim resolves `OUTPUT` via `Path.resolve()` → same `/tmp/input.xlsx`
   (symlink followed).
3. Paths equal → emit cross-5 envelope `SelfOverwriteRefused`; exit 6.

**Alternative Scenarios:**
- **A1: Different extensions on the same inode.** `input.xlsx` and
  `input.md` are different filenames on the same inode (via hard link
  or naming collision). `Path.resolve()` resolves to the same absolute
  path → exit 6. Guards against `cp input.xlsx input.md` misnaming.
- **A2: Genuinely different paths.** `/tmp/input.xlsx` vs
  `/tmp/output.md` → exit 0 (guard passes).

**Postconditions:**
- Shim exits 6 without creating or modifying any output file.

**Acceptance Criteria:**
- ✅ Exit code 6 when resolved paths are equal.
- ✅ Exit code 6 even when file extensions differ (paranoia guard).
- ✅ Mirror xlsx-8 same-path guard regression test via fixture symlink.
- ✅ Exercises: R24.

---

### UC-09 — Encrypted workbook (cross-3)

**Actors:** User, xlsx2md shim, xlsx_read library.

**Preconditions:**
- Input file is an OOXML workbook encrypted with a password
  (OPC `EncryptedPackage` stream present).

**Main Scenario:**
1. User runs `python3 xlsx2md.py encrypted.xlsx`.
2. `xlsx_read.open_workbook` raises `EncryptedWorkbookError`.
3. Shim catches → emit cross-5 envelope to stderr:
   `{v:1, error:"Workbook is encrypted: encrypted.xlsx",
   code:3, type:"EncryptedWorkbookError",
   details:{filename:"encrypted.xlsx"}}`.
4. Exit 3.

**Alternative Scenarios:**

- **A1: `--json-errors` mode active.**
  1. Shim catches `EncryptedWorkbookError`.
  2. Shim emits a single-line JSON envelope to stdout:
     `{"v":1,"error":"...","code":3,"type":"EncryptedWorkbookError","details":{"filename":"<basename>"}}`.
  3. Exit 3.

**Postconditions:**
- No output `.md` file is created (atomic open/write — encryption probe
  runs before any markdown is emitted).
- stderr (without `--json-errors`) carries a single human-readable line
  `error: workbook is encrypted (...)`; stdout is empty.

**Acceptance Criteria:**
- ✅ Exit code 3.
- ✅ `details.filename` is basename only (no full-path leak).
- ✅ `--json-errors` causes envelope to be valid JSON on stderr.
- ✅ Exercises: R21, R23.

---

### UC-10 — `.xlsm` workbook with macros (cross-4)

**Actors:** User, xlsx2md shim, xlsx_read library.

**Preconditions:**
- Input file is `data.xlsm` (macro-enabled workbook).

**Main Scenario:**
1. User runs `python3 xlsx2md.py data.xlsm output.md`.
2. `xlsx_read.open_workbook` emits `MacroEnabledWarning` via `warnings.warn`.
3. Shim captures via `warnings.catch_warnings(record=True)`.
4. Shim surfaces warning on stderr: `"Warning: macro-enabled workbook;
   macros are not executed"`.
5. Extraction continues normally; output.md is written.
6. Exit 0.

**Alternative Scenarios:**

- **A1: `--json-errors` mode active.**
  1. The macro warning rides on stderr via `warnings.warn(MacroEnabledWarning(...))`
     — it does NOT appear inside the success envelope.
  2. Markdown output is still emitted to stdout/file; exit 0.

**Postconditions:**
- Output `.md` exists and is valid markdown.
- stderr contains exactly one `MacroEnabledWarning` line for the input file.

**Acceptance Criteria:**
- ✅ Exit code 0 (not an error).
- ✅ Warning text present on stderr.
- ✅ Output file written (extraction continues normally).
- ✅ Exercises: R22.

---

### UC-11 — ListObject with `headerRowCount=0` (synthetic headers)

**Actors:** User, xlsx2md shim, xlsx_read library.

**Preconditions:**
- Input sheet has a ListObject where `xl/tables/table1.xml` has
  `headerRowCount="0"` (no header row defined).

**Main Scenario (hybrid mode):**
1. User runs `python3 xlsx2md.py data.xlsx --format hybrid`.
2. `reader.detect_tables` returns one `TableRegion` with
   `listobject_header_row_count=0`.
3. Hybrid selector: `headerRowCount=0` → promote to HTML (§1.4 (i)).
4. Library returns `TableData` with synthetic
   `headers=['col_1', 'col_2', 'col_3']` and the original 'no headers'
   warning in `TableData.warnings`.
5. Shim emits `<table>` with
   `<thead><tr><th>col_1</th><th>col_2</th><th>col_3</th></tr></thead>`
   (HTML mode, per D13), or pipe-row + separator-row (GFM mode), or
   auto-promoted HTML (hybrid mode). All three modes surface the
   `summary.warnings` entry `"Table 'Table1' had no headers; emitted
   synthetic col_1..col_3"`.
6. Exit 0.

**Acceptance Criteria:**
- ✅ Exit code 0.
- ✅ Warning containing `"synthetic col_1"` present on stderr.
- ✅ GFM mode: synthetic header row `| col_1 | col_2 | ... |` + separator row present in output.
- ✅ HTML mode: `<thead>` with synthetic `col_1..col_N` `<th>` cells present and visible (per D13).
- ✅ Exercises: R14 (§1.4 (i)), R12.

---

### UC-12 — Cell newline `<br>` round-trip contract

**Actors:** User, xlsx2md shim, xlsx_read library, xlsx-3 shim.

**Preconditions:**
- Input sheet cell A2 contains text with embedded newline:
  `"First line\nSecond line"` (entered via ALT+ENTER in Excel).

**Main Scenario:**
1. User runs `python3 xlsx2md.py data.xlsx output.md`.
2. xlsx_read returns cell value `"First line\nSecond line"`.
3. GFM/HTML emitter replaces `\n` with `<br>` in the cell content:
   `First line<br>Second line`.
4. User then runs `python3 md_tables2xlsx.py output.md roundtrip.xlsx`.
5. xlsx-3 R9.c converts `<br>` back to `\n` in the xlsx cell.
6. Round-trip cell content is byte-identical.

**Alternative Scenarios:**

- **A1: Cell with three embedded newlines.**
  1. Library returns the value with three `\n` separators.
  2. Shim emits three `<br>` separators in document order (no `<br>`
     before the first segment; no trailing `<br>` after the last).
  3. xlsx-3 reverse path consumes the `<br>`s back to `\n`s preserving
     count and order.

- **A2: Cell newline inside a GFM-emitted table with no merges.**
  1. Pipe `|` in the same cell is escaped as `\|`; newline still becomes
     `<br>` (the cell stays on one rendered line in source markdown, but
     renders as multi-line in the GitHub preview).
  2. Round-trip parity holds: xlsx-3 splits on `<br>` → `\n` before
     consuming the GFM table.

**Postconditions:**
- Cell content byte-identical after xlsx-9 → xlsx-3 round-trip when the
  source cell contained newlines.
- Test slug `T-cell-newline-br-roundtrip` (§5.1 entry #21) asserts this.

**Acceptance Criteria:**
- ✅ `\n` in cell value → `<br>` in markdown output (GFM and HTML modes).
- ✅ Round-trip via xlsx-3: cell content byte-identical after `xlsx2md → md_tables2xlsx`.
- ✅ Exercises: R16.

---

## 4. Acceptance Criteria (Top-level / per-task)

Gate conditions for declaring TASK 012 complete:

1. ✅ `skills/xlsx/scripts/xlsx2md.py` exists and is ≤ 60 LOC.
2. ✅ `skills/xlsx/scripts/xlsx2md/` package exists with modules:
   `__init__.py`, `cli.py`, `emit_gfm.py`, `emit_html.py`,
   `emit_hybrid.py`, `exceptions.py`.
3. ✅ Public helper `convert_xlsx_to_md(input_path, output_path, **kwargs) -> int`
   exported from `xlsx2md/__init__.py` and mirrors xlsx-3's
   `convert_md_tables_to_xlsx` `--flag=value` atomic-token convention.
4. ✅ All 14+ E2E scenarios in §5 pass.
5. ✅ `python3 .claude/skills/skill-creator/scripts/validate_skill.py
   skills/xlsx` exits 0.
6. ✅ 5-file silent `diff -q` gate (§0) remains silent after merge.
7. ✅ All existing xlsx-* E2E suites (xlsx-2, xlsx-3, xlsx-6, xlsx-7,
   xlsx-8, xlsx-8a, xlsx-10.A) pass unchanged.
8. ✅ `ruff check scripts/` is green (no new ruff violations).
9. ✅ `skills/xlsx/references/xlsx-md-shapes.md` exists and documents
   the xlsx-9 ↔ xlsx-3 round-trip contract.
10. ✅ xlsx-3's `test_live_roundtrip_xlsx_md` has flipped from skip to
    live AND passes.
11. ✅ `--format gfm` + `--include-formulas` → exit 2
    `IncludeFormulasRequiresHTML` (M7 lock).
12. ✅ Default `--gap-rows 2` confirmed by regression: single-empty-row
    fixture does NOT split with defaults.
13. ✅ `TASK.md` honest-scope items (a)–(m) + R3-H1 each have either a
    module-docstring note or a regression test locking the behaviour.
    Items (k)–(m) are inherited from xlsx-8 / xlsx-8a hardening
    (R14(g) `smart` mode, R10a hyperlink scheme allowlist, R20a
    `--memory-mode` flag respectively).
14. ✅ `skills/xlsx/SKILL.md` registry gains `xlsx2md.py` row.
15. ✅ `docs/KNOWN_ISSUES.md` has an entry `XLSX-10B-DEFER` (or
    equivalent) linking back to backlog row `xlsx-10.B` with a 14-day
    deadline marker (date stamp `2026-05-13 + 14 days`) — verifiable
    via `grep -q "xlsx-10.B" docs/KNOWN_ISSUES.md`.

---

## 5. Test Plan

### 5.1. E2E scenarios (≥ 14 required — 25 listed below; surplus locks key edge cases)

| # | Slug | Scenario | Maps to |
| --- | --- | --- | --- |
| 1 | `T-single-sheet-gfm-default` | Single sheet, default flags (hybrid→GFM), no merges → valid GFM pipe table | UC-01 |
| 2 | `T-stdout-when-output-omitted` | No OUTPUT arg → markdown written to stdout | UC-01 A1 |
| 3 | `T-sheet-named-filter` | `--sheet "Sheet1"` → no H2 heading, table only | UC-02 A2 |
| 4 | `T-multi-sheet-h2-ordering` | 3-sheet workbook → 3 `## ` headings in document order | UC-02 |
| 5 | `T-hidden-sheet-skipped-default` | Hidden sheet absent from output by default | UC-02 |
| 6 | `T-hidden-sheet-included-with-flag` | `--include-hidden` → hidden sheet appears | UC-02 A1 |
| 7 | `T-multi-table-listobjects-h3` | ListObjects → `### TableName` H3 headings | UC-03 |
| 8 | `T-merged-body-cells-html-colspan` | Body merge → HTML `colspan="2"` output | UC-04 |
| 9 | `T-gfm-merges-require-policy-exit2` | `--format gfm` + merges → exit 2 `GfmMergesRequirePolicy` | UC-04 main (gfm) |
| 10 | `T-multi-row-header-html-thead` | 2-row merged header → `<thead>` with `colspan` in HTML | UC-05 |
| 11 | `T-multi-row-header-gfm-u203a-flatten` | 2-row merged header in GFM → ` › ` separator + warning | UC-05 |
| 12 | `T-hyperlink-gfm-url-form` | Cell with `cell.hyperlink` → `[text](url)` in GFM | UC-06 |
| 13 | `T-hyperlink-html-anchor-tag` | Cell with `cell.hyperlink` → `<a href>` in HTML | UC-06 |
| 14 | `T-include-formulas-gfm-exits2` | `--format gfm --include-formulas` → exit 2 before I/O | UC-07 Scenario A |
| 15 | `T-include-formulas-html-data-attr` | `--format html --include-formulas` → `data-formula` attr | UC-07 Scenario B |
| 16 | `T-same-path-via-symlink-exit6` | Symlink `out.md → input.xlsx` → exit 6 `SelfOverwriteRefused` | UC-08 |
| 17 | `T-encrypted-workbook-exit3` | Encrypted `.xlsx` → exit 3 + basename-only in details | UC-09 |
| 18 | `T-xlsm-macro-warning` | `.xlsm` → exit 0 + macro warning on stderr | UC-10 |
| 19 | `T-gap-detect-default-no-split-on-1-row` | Single empty row does NOT split with `--gap-rows 2` | R9 |
| 20 | `T-gap-detect-splits-on-2-empty-rows` | Two consecutive empty rows DO split into two tables | R9 |
| 21 | `T-cell-newline-br-roundtrip` | `\n` in cell → `<br>` in output; xlsx-3 round-trip byte-identical | UC-12 |
| 22 | `T-json-errors-envelope-shape-v1` | Any failure with `--json-errors` → valid cross-5 JSON envelope | R23 |
| 23 | `T-gfm-merge-policy-duplicate` | `--gfm-merge-policy duplicate` → anchor value repeated + warning | UC-04 A1 |
| 24 | `T-synthetic-headers-listobject-zero` | `headerRowCount=0` → synthetic headers + warning emitted | UC-11 |
| 25 | `T-no-autodetect-empty-fallback-whole-sheet` | `--no-table-autodetect` on dense sheet (no gaps) → whole-sheet markdown emitted, info warning, exit 0 | R8(f) |
| 26 | `T-header-rows-smart-skips-metadata-block` | 6-row metadata banner + row 7 unmerged header + 10-row data; `--header-rows smart` → leaf headers, NOT `["От","До"]`-style synthetic keys | R14(g) |
| 27 | `T-header-rows-int-with-multi-table-exits-2-conflict` | Two regions (1-row header + 3-row banner header); `--header-rows 2 --tables listobjects` → exit 2 `HeaderRowsConflict` | R14(h) |
| 28 | `T-memory-mode-streaming-bounds-peak-rss` | Synthetic 15 MB workbook + `--memory-mode=streaming` → peak RSS ≤ 200 MB (`tracemalloc`; `@unittest.skipUnless(SLOW)`) | R20a(e) |
| 29 | `T-memory-mode-auto-respects-library-default-100mib-threshold` | Workbook < 100 MiB with `--memory-mode=auto` → library default respected (no forced mode) | R20a(a) |
| 30 | `T-hyperlink-allowlist-blocks-javascript-html` | Cell with `javascript:alert(1)` href → HTML `<td>` emits text-only; no `<a href>`; warning on stderr | R10a(f) |
| 31 | `T-hyperlink-allowlist-blocks-javascript-gfm` | Cell with `javascript:alert(1)` href → GFM emits `[text]` without `(url)`; warning on stderr | R10a(f) |
| 32 | `T-hyperlink-allowlist-default-passes-https-mailto` | Cells with `https://ok.com` and `mailto:x@y` → both emit full link syntax in default mode | R10a(f) |
| 33 | `T-hyperlink-allowlist-custom-extends` | `--hyperlink-scheme-allowlist http,https,mailto,ftp` → `ftp://` links emitted; `javascript:` still blocked | R10a(d) |
| 34 | `T-internal-error-envelope-redacts-raw-message` | Monkey-patch `xlsx_read.open_workbook` → raise `PermissionError("/Users/secret/file.xlsx")`; assert envelope `error` field does NOT contain `"/Users/secret"` | R23(f) |

**Count:** 34 ≥ 14 required (surplus entries lock key edge cases; §R27.a).

### 5.2. Unit-test targets per module

| Module | Min test count | Focus areas |
| --- | --- | --- |
| `cli.py` | 8 | arg parsing, defaults, `--format gfm + --include-formulas` rejection, `--no-split` / `--no-table-autodetect` flags |
| `emit_gfm.py` | 10 | pipe-char escape, cell newline → `<br>`, hyperlink `[text](url)`, multi-row flatten ` › `, header+separator emission |
| `emit_html.py` | 12 | colspan/rowspan anchor, child-cell suppression, `data-formula` attr, `<br>` in cells, `<a href>` hyperlinks, `<thead>` multi-row, headerless `<table>` |
| `emit_hybrid.py` | 8 | GFM selection (no merges), HTML selection (merges), formula-promotion rule, `headerRowCount=0` promotion |
| `exceptions.py` | 4 | each custom exception instantiation + envelope code mapping |

### 5.3. Regression gates

- ✅ `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0.
- ✅ `ruff check skills/xlsx/scripts/` green.
- ✅ Existing xlsx-2 / xlsx-3 / xlsx-6 / xlsx-7 / xlsx-8 / xlsx-8a / xlsx-10.A E2E suites green.
- ✅ xlsx-3's `test_live_roundtrip_xlsx_md` flips to live and passes.
- ✅ 5-file silent `diff -q` gate silent.

---

## 6. Open Questions

### 6.1. Blocking — None.

All required decisions are either locked by the backlog row, derived
from predecessor tasks (xlsx-3, xlsx-8, xlsx-10.A), or recorded as
deliberate choices in §7 Decisions.

### 6.2. Non-blocking (deferred to architect / implementation)

- **Q-A1 [NON-BLOCKING]:** Should `xlsx2md` always enable
  `include_hyperlinks=True` when calling `xlsx_read.read_table`, or
  should this be gated behind a `--include-hyperlinks` CLI flag like
  xlsx-8? **Defaulted to always-on** (D5 — markdown `[text](url)`
  is lossless and universally readable; there is no JSON-shape
  compatibility concern as in xlsx-8's dict-form complication). If
  later user feedback requests opt-out, add `--no-hyperlinks` flag.

- **Q-A2 [NON-BLOCKING]:** For HTML emission of multi-row headers with
  `xlsx_read`'s ` › `-flattened `headers` list, should xlsx2md
  reconstruct the original multi-row structure from the flat headers,
  or should `xlsx_read` expose raw per-row header data?
  **Defaulted**: reconstruct from flat headers by splitting on ` › `
  and computing merge spans — this is the inverse of `flatten_headers`.
  No `xlsx_read` API extension needed in v1 (D12).

- **Q-A3 [NON-BLOCKING]:** Should `headerRowCount=0` ListObject tables
  in HTML mode emit a `<thead>` with synthetic `col_1..col_N` header
  cells (visible to users) or emit a completely headerless `<table>`?
  **Defaulted**: emit a visible `<thead>` with synthetic headers in all
  modes including HTML, because a truly headerless table (no `<thead>`)
  is ambiguous to downstream parsers. The warning still fires. (D13)

- **Q-A4 [NON-BLOCKING]:** Should `--datetime-format raw` produce
  Python `datetime` repr strings (e.g., `"datetime.datetime(2026, 1, 15,
  9, 0)"`)?  **Defaulted**: `raw` emits `str(value)` which for datetime
  objects is the same ISO form as `ISO` mode, per xlsx-8 §1.4 (n)
  precedent. The distinction only matters for Python-caller direct
  library use.

- **Q-A5 [NON-BLOCKING]:** Should the `convert_xlsx_to_md` public helper
  use the `--flag=value` atomic-token form (xlsx-3 pattern) or the
  separate `[flag, value]` list form (xlsx-2 pattern)?
  **Defaulted**: `--flag=value` form (xlsx-3 / md_tables2xlsx pattern,
  D-ARCH M4 lock). Boolean `True` kwargs append the flag only.

---

## 7. Decisions

### D1 — Single in-skill package `xlsx2md/`, not multi-package

- **Decision:** One package `skills/xlsx/scripts/xlsx2md/` serves the
  single shim `xlsx2md.py`.
- **Rationale:** xlsx-2, xlsx-3, xlsx-8 all use one-package-per-shim
  layout. A second package would duplicate the CLI surface for no gain.
  Unlike xlsx-8 (which has CSV and JSON as genuinely orthogonal formats),
  xlsx-9 has a single output format (markdown) with GFM/HTML as
  sub-modes handled internally.
- **Alternatives considered:** Two packages (`xlsx2md_gfm/`,
  `xlsx2md_html/`) — rejected; over-engineering for orthogonal emitters
  that share 80% of their logic.
- **Lock-strength:** HARD (mirrors xlsx-3 / xlsx-8 precedent).

### D2 — Default `--format hybrid` (per-table auto-select)

- **Decision:** `--format hybrid` is the default; pure `gfm` or `html`
  must be requested explicitly.
- **Rationale:** Hybrid gives the best ergonomics — simple tables (no
  merges, single-row headers) produce clean GFM that renders in every
  markdown viewer; complex tables (merges, multi-row headers) silently
  upgrade to HTML which is also valid GFM in all CommonMark renderers.
  The user rarely needs to think about the distinction.
- **Alternatives considered:** `--format gfm` as default — rejected;
  breaks silently on merged-cell tables. `--format html` as default —
  rejected; produces verbose HTML for simple tables that most users
  prefer as lightweight GFM.
- **Lock-strength:** HARD (backlog row pins this explicitly).

### D3 — Default `--gfm-merge-policy fail` (fail-loud over silent lossy)

- **Decision:** In pure `--format gfm` mode, merged cells exit 2 by
  default unless `--gfm-merge-policy duplicate` or `blank` is explicitly
  set.
- **Rationale:** Silent lossy merge handling (duplicate/blank) would
  confuse users who see different cell counts than expected. Fail-loud
  matches VDD adversarial methodology — caller must opt into lossy
  behaviour explicitly.
- **Alternatives considered:** Default `duplicate` — rejected (silent
  data duplication is misleading). Default `blank` — rejected (loses
  data silently).
- **Lock-strength:** HARD.

### D4 — Default `--datetime-format ISO` (xlsx-3 round-trip parity)

- **Decision:** ISO-8601 string form for dates/datetimes.
- **Rationale:** xlsx-3 (`md_tables2xlsx`) auto-coerces ISO-8601 strings
  back to date cells on import. Using ISO default ensures
  `xlsx2md → md_tables2xlsx` preserves date semantics.
- **Alternatives considered:** Excel-serial default — rejected; non-human-
  readable, breaks xlsx-3 round-trip.
- **Lock-strength:** HARD (backlog row pins this).

### D5 — Hyperlinks always extracted (no opt-in flag)

- **Decision:** `include_hyperlinks=True` is always passed to
  `xlsx_read.read_table`. No `--include-hyperlinks` flag.
- **Rationale:** Unlike xlsx-8 (where JSON/CSV hyperlink shapes are
  novel and potentially breaking), markdown `[text](url)` is the
  completely natural representation of a hyperlink. Omitting hyperlinks
  silently would lose information. The only cost is that files > 10 MiB
  may force `read_only=False` (same xl-8 §1.4(m) trade-off); however,
  xlsx2md's output is text, not binary, and most markdown use-cases
  target human-readable sizes.
- **Alternatives considered:** `--include-hyperlinks` flag — deferred
  to v2 opt-OUT (`--no-hyperlinks`) if memory cost is observed in
  production (Q-A1).
- **Lock-strength:** SOFT (can be revisited if large-file memory
  complaints emerge).

### D6 — Multi-row header flatten separator = ` › ` (U+203A)

- **Decision:** The separator character for multi-row header flattening
  in GFM mode is ` › ` (U+203A SINGLE RIGHT-POINTING ANGLE QUOTATION
  MARK, with a space on each side).
- **Rationale:** This character does not appear in real spreadsheet
  column headers (validated in xlsx-8 M6 VDD-adversarial fix). The
  alternative ` / ` collides with common header patterns like
  `"Q1 / Q2 split"`. This is exactly the separator used by
  `xlsx_read._headers.flatten_headers` — xlsx2md inherits it and
  mirrors it for display.
- **Alternatives considered:** ` / ` — rejected (collision with common
  header text). `" | "` — rejected (collides with GFM pipe syntax).
- **Lock-strength:** HARD (backlog row pins U+203A explicitly; parity
  with xlsx-8 / xlsx-10.A).

### D7 — `--no-table-autodetect` semantics (gap-only via post-call filter)

- **Decision:** `--no-table-autodetect` disables Tier-1 (ListObjects)
  and Tier-2 (named ranges). Implementation: call
  `detect_tables(mode="auto")` then filter the result to keep only
  `region.source == "gap_detect"` regions. No `xlsx_read` API extension
  in v1.
- **Rationale:** `xlsx_read.TableDetectMode` has only three values:
  `"auto"`, `"tables-only"`, `"whole"`. There is no `"gap-only"` enum
  value. Adding one would require modifying `xlsx_read/_types.py` and
  `_tables.py` — cross-task API change with potential regression
  surface. The post-call filter pattern is already used by xlsx-8 for
  `--tables gap` (ARCH D-A2 precedent); xlsx-9 mirrors it identically.
- **Alternatives considered:** Add `"gap-only"` to `TableDetectMode`
  — deferred to xlsx-10.B or a future `xlsx_read` minor version.
- **Lock-strength:** SOFT (will naturally become a HARD via
  `xlsx_read` API update if `gap-only` is ever added).

### D8 — Same-path guard via `Path.resolve()` (cross-7 H1 lock)

- **Decision:** Both `INPUT` and `OUTPUT` are canonicalised via
  `Path.resolve()` (follows symlinks, resolves `..`). If equal, exit 6
  `SelfOverwriteRefused` regardless of extension difference.
- **Rationale:** Standard cross-7 parity (json2xlsx, csv2xlsx,
  xlsx2csv, xlsx2json all implement this). The extension difference
  guard is a paranoia defence against `cp input.xlsx output.xlsx`
  misnaming where both are then passed as arguments.
- **Lock-strength:** HARD (cross-7 H1 is a fixed cross-skill contract).

### D9 — Sheet-name asymmetry with xlsx-3 is expected, NOT a regression

- **Decision:** xlsx-9 emits sheet names verbatim from `WorkbookReader.sheets()`.
  xlsx-3 `naming.py` may sanitise on write-back (e.g., `History` → `History_`).
  This asymmetry is documented in `xlsx-md-shapes.md` §2 and is the
  EXPECTED contract.
- **Rationale:** xlsx-9 is a read-back path; it cannot know which
  sanitisations xlsx-3 will apply. The correct approach is to document
  the contract, not to pre-sanitise in xlsx-9 (which would be
  speculative). Round-trip tests assert content byte-equality, NOT
  sheet-name byte-equality.
- **Lock-strength:** HARD (R3-H1 lock in backlog row).

### D10 — Stream-emit row-by-row to the output sink

- **Decision:** xlsx2md emits one markdown table at a time, writing
  rows as they are produced, without building a whole-workbook in-memory
  model. Text I/O (markdown) is cheap; no JSON-style structural
  materialisation is needed.
- **Rationale:** Unlike JSON (where the entire shape must be known before
  serialisation to insert commas correctly), markdown tables can be
  emitted incrementally: header, separator, then each body row. This
  bounds memory at approximately one `TableData` (one table's rows) at
  a time, not the entire workbook.
- **Alternatives considered:** Whole-workbook string accumulate then
  write — rejected; unnecessary memory cost for large workbooks.
- **Lock-strength:** SOFT (may be revisited if per-table streaming
  proves difficult for multi-row header reconstruction).

### D11 — DEPRECATED (folded into D5)

- **Decision:** Duplicate of D5. Retained as a numbered placeholder to
  avoid renumbering D12–D14. See D5 for the authoritative hyperlinks
  always-on decision.

### D12 — Multi-row header HTML reconstruction from flat headers

- **Decision:** To emit `<thead>` with multiple `<tr>` rows, xlsx2md
  splits flattened headers on the ` › ` separator and re-groups them
  into banner rows. This is a local emit-side concern; no `xlsx_read`
  API extension required in v1.
- **Rationale:** `xlsx_read.TableData.headers` is a flat `list[str]`
  of ` › `-joined strings. The html emitter splits each header string
  on ` › `, computes unique prefixes per position, and emits `<th colspan>`
  for repeated prefix spans. This is O(columns) and entirely local.
- **Lock-strength:** SOFT (a richer `xlsx_read` header API could
  supersede this in xlsx-10.B).

### D13 — `headerRowCount=0` emits synthetic `<thead>` in HTML mode

- **Decision:** Even in HTML mode, a `headerRowCount=0` table emits
  a `<thead>` with synthetic `col_1..col_N` header cells (visible to
  end-users and downstream parsers). Warning is always emitted.
- **Rationale:** A completely headerless `<table>` (no `<thead>`) is
  ambiguous — downstream tools (xlsx-3, pandas, browsers) cannot
  reliably distinguish a headerless table from a table that lost its
  header in processing. Making synthetic headers visible ensures
  downstream consumers can at least identify the column structure.
  `summary.warnings` warns the caller that these are synthetic.
- **Lock-strength:** SOFT (Q-A3 — revisable if users prefer invisible
  headers).

### D14 — Cross-5 envelope `type` renamed from backlog's `MergedCellsRequireHTML` to `GfmMergesRequirePolicy`

- **Decision:** The cross-5 error envelope `type` field for the
  `--format gfm` + merged-cells fail path is `GfmMergesRequirePolicy`,
  not the backlog row's literal `MergedCellsRequireHTML`.
- **Rationale:** The original name implies the only remedy is switching
  to HTML mode. In v1, the user can also use `--gfm-merge-policy=duplicate`
  or `--gfm-merge-policy=blank` to stay in GFM (lossy but allowed). The
  new name describes the actual contract: a policy is required, not
  specifically HTML. Renaming now, before any stable CLI release, costs
  nothing. After release it would be a breaking change.
- **Alternatives considered:** Keep the backlog literal
  `MergedCellsRequireHTML` — rejected; misleads callers into thinking
  the only escape is `--format html`.
- **Lock-strength:** HARD (public cross-5 envelope `type` contract; must
  not drift between TASK, implementation, and tests).

---

## 8. Atomic-Chain Skeleton

Planner-handoff bullet list of likely atomic sub-tasks. Not a plan — the
Planner will validate, sequence, and size these.

- **`012-01`** — Package scaffold + tests scaffolding (create
  `xlsx2md.py` shim + `xlsx2md/` package directories + `exceptions.py`
  + empty module stubs + test file skeletons; validate_skill baseline).
- **`012-02`** — CLI + dispatch (implement `cli.py`: `build_parser()`,
  `main(argv)`, arg defaults, M7 pre-flight `gfm+formulas→exit2`, dispatch
  to `emit_hybrid.select` + output-file handling, same-path guard,
  `convert_xlsx_to_md` public helper in `__init__.py`).
- **`012-03`** — `emit_gfm.py` (GFM pipe table: pipe-char escape,
  `\n→<br>`, hyperlink `[text](url)`, header+separator, `--gfm-merge-policy`
  variants, multi-row-header ` › ` flatten + warning).
- **`012-04`** — `emit_html.py` (HTML `<table>`: colspan/rowspan
  anchor, child-cell suppression, `data-formula` attr, `<a href>`,
  `<br>`, `<thead>` multi-row header reconstruction from flat headers,
  synthetic `<thead>` for `headerRowCount=0`).
- **`012-05`** — `emit_hybrid.py` (per-table GFM/HTML selector: merge
  check, formula-bearing promotion, `headerRowCount=0` promotion; +
  multi-sheet H2 / multi-table H3 orchestration loop).
- **`012-06`** — Cross-cutting envelopes + same-path guard (cross-3,
  cross-4, cross-5 `--json-errors`, cross-7 `Path.resolve()` guard;
  all E2E cross-cutting tests).
- **`012-07`** — `xlsx-md-shapes.md` contract + xlsx-3 live round-trip
  flip (write the contract doc; flip `@unittest.skipUnless` gate in
  xlsx-3's test suite; verify round-trip cell-content byte-equality).
- **`012-08`** — Final docs + validate_skill (update `skills/xlsx/SKILL.md`
  registry row, `skills/xlsx/.AGENTS.md` section, module docstrings for
  honest scope §1.4; `validate_skill.py` exit 0; all E2E green; 5-file
  `diff -q` gate silent).

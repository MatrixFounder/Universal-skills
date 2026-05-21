# ARCHITECTURE: xlsx-9 — `xlsx2md.py` (read-back to Markdown)

> **Prior `docs/ARCHITECTURE.md`** (xlsx-8 + xlsx-8a) **is archived verbatim at** [`docs/architectures/architecture-008-xlsx-8-and-8a-readback-and-hardening.md`](architectures/architecture-008-xlsx-8-and-8a-readback-and-hardening.md).
>
> **Status:** SPECIFIED 2026-05-13 (TASK 012, 8 atomic sub-tasks
> 012-01..012-08). Implementation pending; this document defines the
> contract.
>
> **Template:** `architecture-format-core` with selectively extended
> §5 (Interfaces) + §6 (Tech stack) + §7 (Security) + §9 (Cross-skill
> replication boundary) — this is a **new in-skill shim + package**
> (~9 modules) added on top of the xlsx-10.A `xlsx_read/` foundation.
> The selection mirrors the precedents set by xlsx-2 / xlsx-3 / xlsx-8.

---

## 1. Task Description

- **TASK:** [`docs/TASK.md`](TASK.md) (Task 012, slug `xlsx-9-xlsx2md`,
  DRAFT v1).
- **Brief summary of requirements:** Ship a CLI shim
  `skills/xlsx/scripts/xlsx2md.py` (≤ 60 LOC) plus an in-skill
  package `skills/xlsx/scripts/xlsx2md/` that converts `.xlsx`
  workbooks into a structured Markdown document. The document has
  per-sheet H2 sections, per-table H3 headings, and per-table
  auto-selected GFM pipe-table or HTML `<table>` emission. All reader
  logic (merge resolution, ListObjects, gap-detect, multi-row headers,
  hyperlinks, stale-cache, encryption/macro probes) is **delegated**
  to the `xlsx_read/` foundation library; the shim package owns only
  emit-side concerns.
- **Public surface:**
  - One shim `xlsx2md.py` (≤ 60 LOC), re-exporting from `xlsx2md`.
  - Package public helpers: `convert_xlsx_to_md(...)`, `main(argv)`,
    plus shim-level exception types (`SelfOverwriteRefused`,
    `GfmMergesRequirePolicy`, `IncludeFormulasRequiresHTML`,
    `PostValidateFailed`).
- **Decisions inherited from TASK §7 (D1–D14)** are reproduced here
  so this document is self-contained:

  | D | Decision | Rationale |
  | --- | --- | --- |
  | D1 | Single in-skill package `xlsx2md/` | xlsx-2 / xlsx-3 / xlsx-8 precedent; single output format (markdown) with GFM/HTML as sub-modes. |
  | D2 | Default `--format hybrid` | Best ergonomics; simple tables → clean GFM; complex tables → HTML silently. |
  | D3 | Default `--gfm-merge-policy fail` | Fail-loud; caller must opt into lossy GFM behaviour explicitly. |
  | D4 | Default `--datetime-format ISO` | xlsx-3 round-trip parity; ISO-8601 dates auto-coerced by md_tables2xlsx. |
  | D5 | Hyperlinks always extracted (no opt-in flag) | Markdown `[text](url)` is lossless natural representation; no JSON-shape compat concern. |
  | D6 | Multi-row header flatten separator = ` › ` (U+203A) | Same separator used by `xlsx_read._headers.flatten_headers`; no collision with real header text. |
  | D7 | `--no-table-autodetect` via post-call filter | No `xlsx_read` API extension; mirrors xlsx-8 D-A2 precedent. |
  | D8 | Same-path guard via `Path.resolve()` | Cross-7 H1 lock; mirrors json2xlsx / xlsx2csv / xlsx2json. |
  | D9 | Sheet-name asymmetry with xlsx-3 is expected | xlsx-9 emits verbatim; xlsx-3 sanitises on write-back; contract documented in `xlsx-md-shapes.md`. |
  | D10 | Stream-emit row-by-row to output sink | Markdown is incrementally serialisable; memory peak = one `TableData` at a time. |
  | D11 | DEPRECATED (folded into D5) | Retained as numbered placeholder; see D5. |
  | D12 | Multi-row header HTML reconstruction from flat headers | Emit-side splits ` › `-joined headers; no `xlsx_read` API extension v1. |
  | D13 | `headerRowCount=0` emits synthetic `<thead>` in HTML mode | Ambiguity guard for downstream parsers; synthetic headers visible, warning always emitted. |
  | D14 | Cross-5 envelope `type` renamed to `GfmMergesRequirePolicy` | Policy is required (not specifically HTML); correct name before any stable release. |

- **Architect-layer decisions added by this document** (locked here,
  not in TASK):

  | D | Decision | Rationale |
  | --- | --- | --- |
  | D-A1 | Single package `xlsx2md/`, not multi-package | Emit-side branching ≤ 50 LOC; two packages would duplicate the entire CLI surface. Mirror xlsx-3 / xlsx-8 precedent. |
  | D-A2 | `--no-table-autodetect` via post-call filter `r.source == "gap_detect"` | Library API freeze (xlsx-10.A); filter cost ≤ 4 LOC in `dispatch.py`. Mirror xlsx-8 D-A2. |
  | D-A3 | Single public helper `convert_xlsx_to_md(...)`, NOT multi-format | xlsx-9 has one output format; multi-format question (xlsx-8) doesn't arise. |
  | D-A4 | `lxml.html.HTMLParser` singleton NOT needed | xlsx-9 EMITS HTML, does not parse it; no parser surface whatsoever. Explicitly noted to prevent xlsx-3 mirroring temptation. |
  | D-A5 | Package imports only `xlsx_read.<public>` (ruff banned-api enforced) | Closed-API consumer contract; first proof by xlsx-8, second proof by xlsx-9. |
  | D-A6 | Warnings from `xlsx_read` propagate via `warnings.showwarning` — NOT injected into markdown body | Injecting into output would corrupt the round-trip contract with xlsx-3 (a `summary:` block misread as a section). |
  | D-A7 | Streaming emit: one table at a time to output sink | Markdown is text; no structural materialisation needed. Memory peak = `O(table_max_cells)`. D10 confirmed. |
  | D-A8 | Output-path same-path canonical-resolve guard via `Path.resolve()` | Even with extension mismatch; paranoia guard. Mirror xlsx-8 D-A8. |
  | D-A9 | `emit_html.py` uses `html.escape()`; `emit_gfm.py` uses `\|` for pipe escape | stdlib is sufficient; no custom HTML escaper. |
  | D-A10 | All shim-level fail paths route through `_errors.report_error()` | No `sys.exit(N)` outside that helper; mirrors xlsx-2 / xlsx-3 / xlsx-8. |
  | D-A11 | Multi-row header `<thead>` reconstruction: count ` › ` separators per header cell, group into N rows, raise `InconsistentHeaderDepth` if separator counts differ | Emit-side O(columns) reconstruction; documents expected edge case with literal ` › ` in user data (ambiguous, accepted, see §10 A-A3). |
  | D-A12 | Cell newline → `<br>` applied inside emit layer, not pushed to `xlsx_read` | Library returns raw value; emit functions split on `\n` and inject `<br>` (HTML) or `<br>` (GFM inline HTML, valid per CommonMark). |
  | D-A13 | `--header-rows smart` inherited from xlsx-8a-09; no re-implementation of heuristic in xlsx-9 | Pass-through only: `read_table(header_rows="smart")`. Heuristic `_detect_data_table_offset` lives in `xlsx_read/`; xlsx-9 does not reimplement it. R14(g). |
  | D-A14 | `--memory-mode` inherited from xlsx-8a-11; CLI flag → `open_workbook(read_only_mode=...)` pass-through | `auto` = size-threshold (≥ 100 MiB → streaming); `streaming` = `True`; `full` = `False`. No xlsx-9 buffering logic. R20a. |
  | D-A15 | `--hyperlink-scheme-allowlist` default-enabled in v1 (NOT deferred to v2); default `http,https,mailto` | xlsx-9 emits clickable HTML `<a href>` into renderers — higher attack surface than xlsx-8's JSON key output. Sec-MED-2 lesson applied at design time. `R10a`. Supersedes prior A-A4 v2-deferral. |

---

## 2. Functional Architecture

> **Convention:** F1–F9 are functional regions. Each maps to one
> private module in the `xlsx2md/` package. No region spans more than
> one module; no module owns more than one region.

### 2.1. Functional Components

#### F1 — CLI argument parsing + dispatch (`cli.py`)

**Purpose:** Single argparse surface; `build_parser()` with full flag
set; `main(argv)` orchestrator; M7 pre-flight check
(`--format gfm` + `--include-formulas` → exit 2 before any I/O);
same-path guard; output-parent auto-create; dispatch to
emit-selector.

**Functions:**
- `build_parser() -> argparse.ArgumentParser` — constructs the full
  flag surface (§5.1 CLI reference).
- `main(argv: list[str] | None = None) -> int` — top-level
  orchestrator; returns exit code.
- `_validate_flag_combo(args) -> None` — raises envelope exceptions
  for cross-flag invariants (`IncludeFormulasRequiresHTML`,
  `SelfOverwriteRefused`, `HeaderRowsConflict`).
- `_resolve_paths(args) -> tuple[Path, Path | None]` — canonical
  `Path.resolve()` + same-path guard + output-parent auto-create.

**Dependencies:**
- Depends on: `argparse`, `pathlib`, `sys`, `_errors` (cross-5
  envelope helper).
- Depended on by: shim `xlsx2md.py`; `convert_xlsx_to_md`.

---

#### F2 — Reader-glue / dispatch (`dispatch.py`)

**Purpose:** Open the workbook via `xlsx_read.open_workbook` (with
`read_only_mode` resolved from `--memory-mode`: `streaming` → `True`,
`full` → `False`, `auto` → size-threshold ≥ 100 MiB), enumerate sheets
(filtering hidden per `--include-hidden`), detect regions per detection
mode (with the post-call filter for `--no-table-autodetect`), iterate
per region, hand off `(sheet_info, region, table_data)` triples to the
emitter.

**Functions:**
- `iter_table_payloads(reader, args) -> Iterator[tuple[SheetInfo,
  TableRegion, TableData]]` — yields per-region triples (filtered
  for `--no-table-autodetect` gap-only case and `--sheet` selector).
- `_detect_mode_for_args(args) -> tuple[TableDetectMode,
  Callable[[TableRegion], bool]]` — returns `(library_mode,
  post_filter_predicate)`. `--no-table-autodetect` → `("auto",
  lambda r: r.source == "gap_detect")`; `--no-split` →
  `("whole", lambda r: True)`; default → `("auto", lambda r:
  True)`.
- `_gap_fallback_if_empty(payloads, sheet, reader, args) -> list[...]`
  — when `--no-table-autodetect` gap-filter yields zero regions for
  a sheet, falls back to whole-sheet emission + surfaces info warning
  (R8.f).

**Dependencies:**
- Depends on: `xlsx_read` public surface.
- Depended on by: F3 (`emit_hybrid.py` — format selector / orchestration).

---

#### F3 — Per-table format selector (`emit_hybrid.py`)

**Purpose:** For each `(sheet_info, region, table_data)` triple
yielded by `dispatch.py`, choose GFM or HTML emit format, write H2 /
H3 headings, route to the matching emitter, and flush to the output
sink. This is the TASK R2.(e)-mandated module; it owns all per-table
format logic so that `emit_gfm.py` and `emit_html.py` remain pure
serialisers with no promotion decisions inside them.

**Functions:**
- `select_format(table_data, args) -> Literal["gfm", "html"]` —
  applies the four promotion rules for hybrid mode:
  1. merges ≠ ∅ → `"html"` (D3 / TASK R12.a)
  2. multi-row header (` › ` present in any header string) → `"html"` (D12 / TASK R14.c)
  3. `--include-formulas` AND table has ≥ 1 formula-cell → `"html"` (D14 / TASK R12.b)
  4. `headerRowCount=0` (synthetic headers) → `"html"` (D13 / TASK R12.c)
  Returns `"gfm"` if none of the above apply. For fixed `--format gfm` or
  `--format html`, returns that value directly (no promotion check needed).
- `emit_workbook_md(reader, args, out) -> int` — outer orchestration
  loop: iterates `dispatch.iter_table_payloads`, writes `## SheetName`
  H2 per sheet, writes `### TableName` H3 per table, calls
  `select_format` to choose the emitter, calls `emit_gfm_table` or
  `emit_html_table` accordingly. Returns exit code.
- `_has_body_merges(table_data) -> bool` — predicate; True iff
  `table_data.region` has at least one merge cell in the body (below
  the header band).
- `_has_formula_cells(table_data) -> bool` — predicate; True iff any
  cell value is a formula string (starts with `=`; only meaningful
  when `include_formulas=True` was passed to `read_table`).
- `_is_multi_row_header(table_data) -> bool` — predicate; True iff
  any element of `table_data.headers` contains the ` › ` separator.
- `_is_synthetic_header(table_data) -> bool` — predicate; True iff
  `table_data.region.listobject_header_row_count == 0`.

**Note on `--no-split`:** when `detect_tables(mode="whole")` returns
a single region, `### Table-1` H3 heading is still emitted
(Q-A1 closed → §12; predictable layout for downstream parsers).

**Dependencies:**
- Depends on: F2 (`dispatch.py`), F4 (`emit_gfm.py`), F5 (`emit_html.py`).
- Depended on by: F1 (`cli.py:main()`).

---

#### F4 — GFM emitter (`emit_gfm.py`)

**Purpose:** Pure GFM table serialisation for a single `TableData`.

**Functions:**
- `emit_gfm_table(table_data, out, *, gfm_merge_policy, include_hidden=False) -> None` — writes header row + `|---|` separator + body rows to `out` file object.
- `_format_cell_gfm(value) -> str` — escape `|` → `\|`; replace `\n`
  → `<br>`; hyperlink → `[text](url)`; None → `""`.
- `_emit_header_row_gfm(headers, out) -> None` — writes `| h1 | h2 | ... |`
  and `|---|---|...|` separator. For multi-row headers (` › ` present):
  flatten to single row (D6 lock) + emit `AmbiguousHeaderWarning` for
  downstream logging.
- `_apply_gfm_merge_policy(rows, merges, policy) -> list[list[Any]]` —
  resolves body merges per `duplicate|blank` policy; raises
  `GfmMergesRequirePolicy` for `fail` policy.

**Dependencies:** `inline.py` (shared inline-content helpers).

---

#### F5 — HTML emitter (`emit_html.py`)

**Purpose:** HTML `<table>` serialisation for a single `TableData`.

**Functions:**
- `emit_html_table(table_data, out, *, include_formulas=False) -> None` —
  writes `<table>`, `<thead>`, `<tbody>` blocks to `out`.
- `_emit_thead(headers, merges_in_header_band, out) -> None` —
  reconstruct multi-row `<tr>` rows inside `<thead>` by splitting
  ` › ` separators (D-A11 algorithm: see §3.2 `headers.py` module).
- `_emit_tbody(rows, region, merges, out, *, include_formulas) -> None` —
  emit `<tr>/<td>/<th>` with `colspan`/`rowspan` at anchor cells;
  child cells suppressed from output.
- `_format_cell_html(value, *, formula=None, is_anchor=False,
  colspan=1, rowspan=1) -> str` — `html.escape(...)` for text;
  `html.escape(url, quote=True)` for href; `<br>` for newlines;
  `data-formula` attr when `formula` and `include_formulas` active.

**Dependencies:** `inline.py`, `headers.py`.

---

#### F6 — Inline content helpers (`inline.py`)

**Purpose:** Shared cell-value rendering that is format-agnostic up
to the point where GFM and HTML diverge.

**Functions:**
- `render_cell_value(value, *, mode: Literal["gfm","html"],
  include_formulas=False, formula=None) -> str` — central dispatcher.
- `_escape_pipe_gfm(text) -> str` — replaces `|` with `\|`.
- `_escape_html_entities(text) -> str` — calls `html.escape(text)`.
- `_newlines_to_br(text) -> str` — splits on `\n`, joins with `<br>`.
- `_render_hyperlink(value, href, mode, *, allowed_schemes: frozenset[str]) -> str` —
  checks `href` scheme against `allowed_schemes` (D-A15); scheme not
  in set → emits plain `value` text + surfaces `UserWarning` naming
  the blocked scheme. For allowed schemes: `[text](url)` for GFM;
  `<a href="url">text</a>` for HTML.

---

#### F7 — Multi-row header reconstruction (`headers.py`)

**Purpose:** Emit-side reconstruction of multi-row `<thead>` from
the flat ` › `-joined `TableData.headers` list. This is a pure
emit-side concern (library does not expose raw per-row header data
per D12).

**Functions:**
- `split_headers_to_rows(headers: list[str]) -> list[list[str]]` —
  splits each header string on ` › ` separator; returns a list of
  rows where row 0 is the top header band and row N-1 is the leaf
  header.
- `compute_colspan_spans(header_rows: list[list[str]]) -> list[list[int]]` —
  for each position in row 0..N-2, count how many consecutive leaf
  positions share the same prefix path; returns a parallel list of
  colspan values. A column with no span → colspan=1 (omitted in
  output).
- `validate_header_depth_uniformity(headers: list[str]) -> int` —
  returns the depth N (number of ` › ` separators + 1). Raises
  `InconsistentHeaderDepth` if headers differ in separator count
  (defensive; `xlsx_read` should enforce uniformity, but this is a
  second safety layer).

**Note on literal ` › ` in user data:** if a workbook contains a
header cell whose text includes U+203A as plain content (not as a
separator), the reconstruction will misinterpret it. This is
documented as accepted edge case A-A3 in §10.

---

#### F8 — Exceptions catalogue (`exceptions.py`)

**Purpose:** Define all shim-level error types and their exit codes.

**Classes:**
- `class _AppError(RuntimeError)` — base; `CODE: int` class attr
  consumed by `_errors.report_error`.
- `SelfOverwriteRefused (CODE=6)` — cross-7 H1.
- `GfmMergesRequirePolicy (CODE=2)` — `--format gfm` + body merges
  without explicit policy (D14 rename of backlog `MergedCellsRequireHTML`).
- `IncludeFormulasRequiresHTML (CODE=2)` — M7 lock: `--format gfm`
  + `--include-formulas`.
- `PostValidateFailed (CODE=7)` — env-flag post-validate gate.
- `InconsistentHeaderDepth (CODE=2)` — multi-row header reconstruction
  finds non-uniform separator depth (D-A11 defensive check).
- `HeaderRowsConflict (CODE=2)` — `--header-rows N` (int) combined
  with `--tables != whole` (R14(h)); raised in `_validate_flag_combo`
  before any file I/O.
- `InternalError (CODE=7)` — terminal catch-all for any unhandled
  exception reaching `main()` top level; raw exception message is
  redacted to prevent path leaks from openpyxl / `xlsx_read`
  internals; emitted via `_errors.report_error` as
  `{"v":1,"error":"Internal error: <ClassName>","code":7,"type":"InternalError","details":{}}`
  (R23(f), inherited from xlsx-8 §14.4 H3 fix).

**Dependencies:** None (leaf module).

---

#### F9 — Public-API surface + honest-scope docstring (`__init__.py`)

**Purpose:** Re-export `convert_xlsx_to_md`, `main`, all `_AppError`
subclasses; expose `__all__`; host the honest-scope catalogue (module
docstring mirrors TASK §1.4).

**Public symbols (frozen surface):**
```python
__all__ = [
    "main",
    "convert_xlsx_to_md",
    "_AppError",
    "SelfOverwriteRefused",
    "GfmMergesRequirePolicy",
    "IncludeFormulasRequiresHTML",
    "PostValidateFailed",
    "InconsistentHeaderDepth",
    "HeaderRowsConflict",
    "InternalError",
]
```

**Function:**
- `convert_xlsx_to_md(input_path, output_path=None, **kwargs) -> int`
  — wraps `main()` via `_build_argv`; `--flag=value` atomic-token
  form (D-A3 / D7 pattern, mirrors `convert_md_tables_to_xlsx`).

---

### 2.2. Functional Components Diagram

```
xlsx2md.py (shim)
      │
      ▼
F9 — __init__.py (public surface)
      │
      ▼
F1 — cli.py (argparse + main() + path guard)
      │                         │
      ▼                         ▼
F3 — emit_hybrid.py       (pre-flight exits: cross-3/4/5/7)
  (per-table format
   selector + H2/H3
   orchestration loop)
      │
      ▼
F2 — dispatch.py
  (reader-glue,
   iter_table_payloads)
      │
      ├─────────────────────┐
      ▼                     ▼
F4 — emit_gfm.py      F5 — emit_html.py
      │                     │
      └──────┬──────────────┘
             ▼
F6 — inline.py (shared cell-value rendering)
F7 — headers.py (multi-row <thead> reconstruction)

F8 — exceptions.py  ←──── codes consumed by _errors.report_error
xlsx_read/          ←──── all reader logic delegated here
_errors.py          ←──── cross-5 envelope (read-only use)
```

---

## 3. System Architecture

### 3.1. Architectural Style

**Style:** **Thin shim + in-skill Python package**, layered on top of
the xlsx-10.A `xlsx_read/` foundation. No new system tools; no new
PyPI dependencies.

**Justification:**
- Mirrors the proven xlsx pattern: each CLI in `skills/xlsx/scripts/`
  is a ≤ 60 LOC re-export shim; the body lives in a sibling `<name>/`
  package. Reference precedents: xlsx-2 (`json2xlsx.py` + `json2xlsx/`
  package), xlsx-3 (`md_tables2xlsx.py` + `md_tables2xlsx/`), xlsx-8
  (`xlsx2csv.py` / `xlsx2json.py` + `xlsx2csv2json/`).
- **Layered** (F9 ← F1 ← F3 ← F2 ← F4/F5 ← F6/F7/F8); each layer
  depends only on layers below; no cycles.
- **Zero new dependencies** above what xlsx-10.A already added
  (`ruff`, `openpyxl`, `lxml` — all already pinned). stdlib `html`
  (already present) covers entity escaping.
- **Single source of truth for reader logic** — every reader concern
  forwarded to `xlsx_read.WorkbookReader`. Drift between this package
  and `xlsx_read` = bug.

### 3.2. System Components

#### C1 — `skills/xlsx/scripts/xlsx2md.py` (NEW, ≤ 60 LOC)

**Type:** Shell-entry shim.

**Purpose:** Re-export from `xlsx2md`; directly executable as
`python3 xlsx2md.py INPUT.xlsx`.

**File body (locked surface):**
```python
#!/usr/bin/env python3
"""xlsx-9: Convert an .xlsx workbook into Markdown.

Thin CLI shim on top of the xlsx-10.A `xlsx_read/` foundation. Body
lives in `xlsx2md/`. See `--help` for the full flag list.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xlsx2md import (  # noqa: E402
    main,
    convert_xlsx_to_md,
    _AppError,
    SelfOverwriteRefused,
    GfmMergesRequirePolicy,
    IncludeFormulasRequiresHTML,
    PostValidateFailed,
    InconsistentHeaderDepth,
    HeaderRowsConflict,
)


if __name__ == "__main__":
    sys.exit(main())
```

**Technologies:** Python ≥ 3.10.

**Interfaces:**
- **Inbound:** shell (`python3 xlsx2md.py ...`).
- **Outbound:** `xlsx2md.main()`.

---

#### C2 — `skills/xlsx/scripts/xlsx2md/` (NEW, package, ~9 modules)

**Type:** In-skill Python package.

**Purpose:** Body for the shim; emit-side only.

**File layout:**
```
skills/xlsx/scripts/xlsx2md/
  __init__.py        # F9 — public surface + honest-scope docstring
  cli.py             # F1 — argparse + main() + dispatch + path guard
  dispatch.py        # F2 — reader-glue + iter_table_payloads
  emit_hybrid.py     # F3 — per-table GFM/HTML selector + promotion rules (D2/D13/D14) [TASK R2.e]
  emit_gfm.py        # F4 — GFM pipe-table emitter [TASK R2.c]
  emit_html.py       # F5 — HTML <table> emitter [TASK R2.d]
  inline.py          # F6 — shared cell-value inline rendering [arch-layer helper]
  headers.py         # F7 — multi-row <thead> reconstruction [arch-layer helper]
  exceptions.py      # F8 — _AppError + subclasses [TASK R2.f]
  tests/
    __init__.py
    conftest.py
    fixtures/        # .xlsx fixtures (≥ 25 files)
    test_cli.py
    test_dispatch.py
    test_emit_gfm.py
    test_emit_html.py
    test_emit_hybrid.py
    test_exceptions.py
    test_public_api.py
    test_e2e.py      # 25 E2E scenarios from TASK §5.1
```

Helper modules `inline.py` and `headers.py` are architecture-layer
additions to the TASK R2 module list — they extract cell-inline
rendering and multi-row `<thead>` reconstruction into
single-responsibility shared modules consumed by both `emit_gfm.py`
and `emit_html.py`. They do NOT replace any TASK R2 module; they
reduce code duplication between GFM and HTML emit paths.

**Technologies:** Python ≥ 3.10, `xlsx_read` (xlsx-10.A), `html`
(stdlib), `argparse` (stdlib), `pathlib` (stdlib), `warnings`
(stdlib), `sys` (stdlib).

**Interfaces:**
- **Inbound (Python import):** `from xlsx2md import
  convert_xlsx_to_md, main, ...` — only symbols in `__all__`.
- **Outbound:** `from xlsx_read import open_workbook, WorkbookReader,
  SheetInfo, TableRegion, TableData, MergePolicy, TableDetectMode,
  DateFmt, EncryptedWorkbookError, MacroEnabledWarning,
  OverlappingMerges, AmbiguousHeaderBoundary, SheetNotFound,
  TooManyMerges`. `from _errors import report_error,
  add_json_errors_argument`.

**Dependencies:**
- External libs: NONE new.
- Other in-skill components: `xlsx_read/` (closed-API consumer);
  `_errors.py` (cross-5 envelope helper; read-only use).
- System components NOT modified: `office/`, `_soffice.py`,
  `_errors.py`, `preview.py`, `office_passwd.py`. 5-file cross-skill
  `diff -q` silent gate stays silent.

---

#### C3 — `skills/xlsx/scripts/requirements.txt` (UNCHANGED)

No new dependencies. xlsx-10.A already pinned `openpyxl`, `lxml`,
`ruff`. `html` is stdlib.

#### C4 — `skills/xlsx/scripts/pyproject.toml` (UNCHANGED)

`ruff` banned-api rule from xlsx-10.A continues to enforce that
external code imports only `xlsx_read.<public>`, never
`xlsx_read._*`. No new rule needed — `xlsx2md` is a new consumer
that benefits from the existing rule without modification.

#### C5 — `skills/xlsx/scripts/install.sh` (UNCHANGED)

`ruff check scripts/` post-hook from xlsx-10.A covers the new package.

#### C6 — `skills/xlsx/references/xlsx-md-shapes.md` (NEW, ≥ 1 page)

**Purpose:** Round-trip contract document mirroring
`skills/xlsx/references/json-shapes.md`. Documents:
- §1 Scope — H2-per-sheet, H3-per-table emission shape; GFM and HTML
  table emit shapes.
- §2 GFM shape — pipe-table format with sub-cases: single-row header,
  multi-row header degraded with ` › ` flatten, synthetic header for
  `headerRowCount=0`.
- §3 HTML shape — `<table>` with `<thead>` + `<tbody>` +
  `colspan`/`rowspan` + `data-formula`; multi-row `<thead>` with
  multiple `<tr>`; synthetic `<thead>` for `headerRowCount=0`.
- §4 Hybrid mode — per-table promotion rules (D2 / D14 from TASK).
- §5 Inline contract — `<br>` for newlines; pipe escape; hyperlink
  branches; HTML entity escaping.
- §6 Sheet-name asymmetry — xlsx-9 emits verbatim; xlsx-3 sanitises
  on write-back (`History` → `History_`); documented as EXPECTED
  (D9 lock), NOT a regression.
- §7 Round-trip limitations (honest scope) — merges un-merge on
  xlsx-3 write-back; formulas emit as cached values; styles dropped;
  comments dropped.
- §8 Live round-trip test activation — the xlsx-3
  `@unittest.skipUnless(xlsx2md_available(), ...)` gate flips to live
  at xlsx-9 merge.

#### C7 — `skills/xlsx/SKILL.md` (MODIFIED)

Registry table gains a row for `xlsx2md.py`. §10 honest-scope
catalogue gains: *"`xlsx2md` v1: rich-text spans / styles / comments /
charts / pivot tables / data-validation dropped; see TASK 012 §1.4."*

#### C8 — `skills/xlsx/.AGENTS.md` (MODIFIED — Developer-only)

Add `## xlsx2md` section documenting: new package + shim; honest-scope
items; `--no-table-autodetect` → post-call-filter note (D-A2 pattern);
hyperlinks always-on rationale (D5); cross-link to `xlsx_read` section.

---

### 3.3. Components Diagram

```
skills/xlsx/scripts/
  xlsx2md.py  ─────────────────────────────────────────────────────┐
                                                                    │
  xlsx2md/                                                          │
    __init__.py ◄───── Python callers (from xlsx2md import ...)     │
    cli.py       ◄───────────────────────────────────────────────── ┘
    dispatch.py  ──► xlsx_read/ (FOUNDATION — xlsx-10.A)
    emit_gfm.py  ──► inline.py
    emit_html.py ──► inline.py, headers.py
    exceptions.py
    ─────────────────────────────────────────────────────────────────
  _errors.py      (cross-5 envelope — READ ONLY, not modified)
  xlsx_read/      (FOUNDATION — xlsx-10.A, not modified)
  references/
    xlsx-md-shapes.md  (NEW round-trip contract doc)
    json-shapes.md     (UNCHANGED)
```

---

## 4. Data Model (Conceptual)

> **Note:** xlsx-9 introduces no new dataclasses. Everything consumed
> (`SheetInfo`, `TableRegion`, `TableData`, `MergePolicy`,
> `TableDetectMode`, `DateFmt`) is **imported** from `xlsx_read/` and
> used as-is. The only new "data" is the **Markdown text produced by
> the emitters** — a derived text format, not a Python entity.

### 4.1. Derived shape — Markdown output (frozen contract)

Full specification lives in `skills/xlsx/references/xlsx-md-shapes.md`
(§6 above). Architecture-level summary with canonical examples:

**Structural skeleton:**
```
## SheetName          (H2 — per visible sheet, in document order)
### TableName         (H3 — per table, from ListObject name / range
                       name / "Table-N" for gap-detect)

<table content — GFM or HTML, per format-selector>

## NextSheet
### AnotherTable
...
```

**GFM — single-row header (most common case):**
```markdown
| col_a | col_b | col_c |
|---|---|---|
| val1 | val2 | val3 |
| val4 | val5 | val6 |
```

**GFM — synthetic header (`headerRowCount=0`):**
```markdown
| col_1 | col_2 | col_3 |
|---|---|---|
| data1 | data2 | data3 |
```

**HTML — merged body cells (hybrid auto-promotes):**
```html
<table>
<thead><tr><th>Name</th><th>Value</th></tr></thead>
<tbody>
<tr><td colspan="2">Section Total</td></tr>
<tr><td>Item A</td><td>42</td></tr>
</tbody>
</table>
```

**HTML — multi-row header (` › ` separator reconstruction):**
```html
<table>
<thead>
<tr><th colspan="3">2026 plan</th></tr>
<tr><th>Q1</th><th>Q2</th><th>Q3</th></tr>
</thead>
<tbody>...</tbody>
</table>
```

**Hybrid auto-promote (formula cell):**
```html
<table>
<thead><tr><th>A</th><th>B</th><th>Sum</th></tr></thead>
<tbody>
<tr><td>10</td><td>20</td><td data-formula="=A2+B2">30</td></tr>
</tbody>
</table>
```

### 4.2. In-memory emit intermediate

Per-table, the emit functions operate on `TableData.rows: list[list[Any]]`
directly. The pre-escaped cell strings are generated inline and written
to the output sink without materialising a whole-table intermediate
`list[list[str]]`. Memory peak = one `TableData` (one table's rows)
at a time — bounded by `xlsx_read`'s own `read_table` materialisation.

### 4.3. Schema diagram

```
TableData (from xlsx_read — NOT redefined here)
  ├── region: TableRegion
  ├── headers: list[str]     (flat, ` › `-joined for multi-row)
  ├── rows: list[list[Any]]
  └── warnings: list[str]
       │
       ▼
Format selector
  ├── GFM branch → emit_gfm.py → pipe-table text bytes → output sink
  └── HTML branch → emit_html.py → <table> text bytes → output sink
```

---

## 5. Interfaces

### 5.1. External (CLI)

**`xlsx2md.py` arguments (locked surface):**

| Flag | Type / Domain | Default | Notes |
| --- | --- | --- | --- |
| `INPUT` (positional) | path | required | `.xlsx` / `.xlsm`. |
| `[OUTPUT]` (optional positional) | path or `-` | stdout | `-` = explicit stdout; omit = stdout. |
| `--sheet NAME\|all` | str | `all` | `NAME` → single sheet (no H2 heading emitted); `all` → all visible sheets in document order. Missing name → exit 2 `SheetNotFound`. |
| `--include-hidden` | flag | off | Include sheets with `state="hidden"` or `state="veryHidden"`. |
| `--format gfm\|html\|hybrid` | enum | `hybrid` | `gfm`: all tables as GFM pipe-tables. `html`: all tables as `<table>`. `hybrid`: per-table auto-select. |
| `--header-rows N\|auto\|smart` | int ≥ 1, `"auto"`, or `"smart"` | `auto` | Forwarded to `read_table(header_rows=...)`. `smart` runs `_detect_data_table_offset` heuristic (xlsx-8a-09 R11) to skip metadata blocks above data tables; orthogonal to multi-table mode (R14(g)). `--header-rows N` (int) + `--tables != whole` → exit 2 `HeaderRowsConflict` (R14(h)). |
| `--memory-mode auto\|streaming\|full` | enum | `auto` | Maps to `open_workbook(read_only_mode=...)`: `streaming` → `True`; `full` → `False`; `auto` → size-threshold heuristic (≥ 100 MiB → streaming). Inherited from xlsx-8a-11 (R20a). |
| `--hyperlink-scheme-allowlist SCHEMES` | comma-separated str | `http,https,mailto` | Hyperlinks whose scheme is not in the allowlist are emitted as text-only + warning (Sec-MED-2). Applies to both `<a href>` (HTML/hybrid) and `[text](url)` (GFM) paths. Default-enabled in v1 (D-A15). |
| `--no-table-autodetect` | flag | off | Disables Tier-1 + Tier-2; only gap-detect regions emitted (D-A2 post-call filter). |
| `--no-split` | flag | off | Whole sheet = one table; `detect_tables(mode="whole")`; H3 heading `### Table-1` still emitted. |
| `--gap-rows N` | int ≥ 1 | `2` | Gap-detect row threshold (M4 fix parity with xlsx-8). |
| `--gap-cols N` | int ≥ 1 | `1` | Gap-detect column threshold. |
| `--gfm-merge-policy fail\|duplicate\|blank` | enum | `fail` | Body-merge handling in GFM mode. `fail` → exit 2 `GfmMergesRequirePolicy`. `duplicate` / `blank` → lossy GFM + warning. Ignored for HTML / hybrid (HTML handles merges natively). |
| `--datetime-format ISO\|excel-serial\|raw` | enum | `ISO` | Forwarded to `read_table(datetime_format=...)`. |
| `--include-formulas` | flag | off | HTML + hybrid: `data-formula` attr on formula cells. GFM: exit 2 `IncludeFormulasRequiresHTML` (M7 lock). |
| `--json-errors` | flag | off | Cross-5 envelope on stderr for all fail paths. |

**Flag interaction summary (cross-flag invariants):**

| Combination | Result |
| --- | --- |
| `--format gfm` + `--include-formulas` | Exit 2 `IncludeFormulasRequiresHTML` before file I/O |
| `--format gfm` + body merges + `--gfm-merge-policy fail` (default) | Exit 2 `GfmMergesRequirePolicy` |
| `--format html` + `--include-formulas` | Valid — `data-formula` attrs emitted |
| `--format hybrid` + `--include-formulas` | Valid — formula tables promoted to HTML |
| `--no-split` + `--no-table-autodetect` | `--no-split` wins; `detect_tables(mode="whole")` used |
| `INPUT == OUTPUT` (after `Path.resolve()`) | Exit 6 `SelfOverwriteRefused` |
| `--sheet NAME` (sheet absent) | Exit 2 `SheetNotFound` |
| `--header-rows N` (int) + `--tables != whole` | Exit 2 `HeaderRowsConflict` before file I/O (R14(h)) |
| `--memory-mode streaming` | Forces `read_only_mode=True` regardless of workbook size; cell styles unavailable in streaming mode (openpyxl limitation; warning emitted if `--include-formulas` active) |
| `--hyperlink-scheme-allowlist ""` (empty string) | All hyperlinks stripped to text; equivalent to disabling hyperlink emission |

### 5.2. Internal (Python import — for library consumers)

```python
from xlsx2md import convert_xlsx_to_md, main, _AppError, ...

def convert_xlsx_to_md(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    sheet: str = "all",
    include_hidden: bool = False,
    format: Literal["gfm", "html", "hybrid"] = "hybrid",
    header_rows: int | Literal["auto", "smart"] = "auto",
    no_table_autodetect: bool = False,
    no_split: bool = False,
    gap_rows: int = 2,
    gap_cols: int = 1,
    gfm_merge_policy: Literal["fail", "duplicate", "blank"] = "fail",
    datetime_format: Literal["ISO", "excel-serial", "raw"] = "ISO",
    include_formulas: bool = False,
    memory_mode: Literal["auto", "streaming", "full"] = "auto",
    hyperlink_scheme_allowlist: str = "http,https,mailto",
    json_errors: bool = False,
) -> int: ...  # exit code
```

Per D-A3 / D7, the helper builds argv with `--flag=value` atomic-token
form and routes through `main(argv)`. `None` kwargs are skipped.
Boolean `True` kwargs append the flag only (no `=True`). Programmatic
and CLI callers share the same argparse code path.

### 5.3. Library boundary contract (D-A5)

The package imports **only** from `xlsx_read.<public>`. The ruff
`banned-api` rule in xlsx-10.A `pyproject.toml` fails lint on any
`from xlsx_read._*` import.

**Exact `xlsx_read.__all__` exports consumed:**

```python
from xlsx_read import (
    open_workbook,
    WorkbookReader,
    SheetInfo,
    TableRegion,
    TableData,
    MergePolicy,
    TableDetectMode,
    DateFmt,
    EncryptedWorkbookError,
    MacroEnabledWarning,
    OverlappingMerges,
    AmbiguousHeaderBoundary,
    SheetNotFound,
    TooManyMerges,
)
```

**Additional library boundary rules:**
- `warnings.catch_warnings(record=True)` is the only legal capture
  point for `MacroEnabledWarning` and `AmbiguousHeaderBoundary`.
- `_errors.report_error` is the only legal exit-code + stderr path.
- No direct `openpyxl.*` import inside the package (regression test
  greps for `openpyxl` outside test-fixture builders).
- `lxml` is NOT imported at all (xlsx-9 emits HTML, does not parse
  it — D-A4).

---

## 6. Technology Stack

### 6.1. Runtime

- Python ≥ 3.10 (xlsx skill baseline; `Literal`, `match` optional,
  `X | Y` union syntax).
- `openpyxl ≥ 3.1.0` — **transitive only** (via `xlsx_read/`); never
  imported directly.
- `lxml ≥ 5.0` — **transitive only** (via `xlsx_read._values` for
  hyperlink extraction); never imported directly.
- stdlib: `argparse`, `pathlib`, `warnings`, `html`, `sys`.

### 6.2. Direct PyPI dependencies (requirements.txt deltas)

| Package | New? | Note |
| --- | --- | --- |
| _(none)_ | — | No additions; xlsx-10.A already pinned `openpyxl`, `lxml`, `ruff`; `html` is stdlib. |

### 6.3. Excluded technologies (deliberate)

- **`pandas`** — parallel xlsx-2 / xlsx-3 / xlsx-8 lock. Not needed
  for row-by-row text emit.
- **`markdown` / `commonmark` PyPI libs** — xlsx-9 EMITS markdown,
  does not parse it. Parsing is xlsx-3's job (lxml.html only). No
  parser needed on the emit side.
- **`Jinja2` / template engines** — overkill for a row-by-row stream;
  adds a dep for zero gain.
- **`openpyxl` direct import** — forbidden (D-A5); always via
  `xlsx_read/`.
- **`lxml` direct import** — forbidden (D-A4); emit side has no parser
  surface.

### 6.4. Test stack

- `unittest` (stdlib) — matches xlsx skill convention (xlsx-2 / xlsx-3
  / xlsx-7 / xlsx-10.A / xlsx-8 all use `unittest`).
- Fixtures: hand-built `.xlsx` files in `xlsx2md/tests/fixtures/`.
  Reuse `xlsx_read/tests/fixtures/` for input-side scenarios; create
  NEW fixtures for emit-side edge cases (merges, multi-row headers,
  formula cells, hyperlinks, `headerRowCount=0`).

---

## 7. Security

### 7.1. Threat model

- **Trust boundary:** the input `.xlsx` file (delegated to
  `xlsx_read/`), the `OUTPUT` path (this task's concern), and CLI argv
  (parsed via stdlib `argparse`).
- **Adversary model:** hostile workbook (XXE, billion-laughs, zip-bomb,
  macro-bearing — all mitigated by `xlsx_read/` per xlsx-10.A §7.2).
  **NEW threats at the xlsx-9 shim layer:** HTML injection in cell
  content; GFM pipe injection; path traversal via same-path guard; DoS
  via `data-formula` attribute injection.

### 7.2. Per-threat mitigation

| Threat | Mitigation | Owner |
| --- | --- | --- |
| **HTML injection in cell content** (`<script>`, `<style>`, `<img onerror>` literals in cells) | `emit_html.py` calls `html.escape(text)` on every cell value before inserting into `<td>` content. Without escaping, a downstream HTML viewer (marp-slide, browser preview, GitHub markdown render) would execute the payload. | F5 (`emit_html.py`) + F6 (`inline.py`). |
| **Hyperlink URL injection** (`javascript:` / `data:` URIs in href attr) | Two-layer mitigation (D-A15 / Sec-MED-2): (1) Scheme allowlist — `_render_hyperlink` checks `href` scheme against `--hyperlink-scheme-allowlist` (default `http,https,mailto`); scheme not in set → emit plain text + `UserWarning`; NO `<a href>` emitted. (2) Attribute escaping — `html.escape(url, quote=True)` on every href that passes the allowlist, neutralising `"` injection. Applied to BOTH `<a href>` (HTML/hybrid) and `[text](url)` (GFM) paths. Default-enabled in v1 because xlsx-9 emits clickable HTML with higher attack surface than xlsx-8's JSON output. | F5 + F6 (`inline.py:_render_hyperlink`). |
| **`data-formula` attribute injection** (formula strings may contain `"` and `&`) | `html.escape(formula, quote=True)` for `data-formula` attribute value. A malicious formula like `=cmd("| calc")` is NOT executed (data attribute, not code), but unescaped `"` would break the attribute and allow injection of further attrs. | F5 (`emit_html.py`). |
| **GFM pipe injection** (cell value contains `\|`) | `emit_gfm.py` escapes `|` → `\|` in every cell. Other GFM special chars (`*`, `_`, `` ` ``) are passed through intentionally — markdown-in-cell is the user-facing affordance (mirrors xlsx-3). | F4 (`emit_gfm.py`) + F6 (`inline.py`). |
| **Same-path overwrite (cross-7 H1)** | `Path.resolve()` follows symlinks; equality check before any write → `SelfOverwriteRefused` exit 6. Applies even when extensions differ. | F1 (`cli.py`). |
| **Information leak via error messages** | All envelope error messages use `path.name` (basename), NOT `path.resolve()` full path. Parallel xlsx-8 §13.2 fix. | F1 + `_errors`. |
| **DoS via malicious `<dimension>`** | Mitigated upstream by `xlsx_read._gap_detect` allocation cap (50M cells from xlsx-8a §15.10.1). No new surface in xlsx-9. | `xlsx_read/` upstream. |

### 7.3. OWASP Top-10 mapping (subset applicable to a non-network CLI)

| OWASP item | Applies? | Status |
| --- | --- | --- |
| A03:2021 Injection (HTML) | Yes | `html.escape()` in all HTML cell-text and attr-value positions. |
| A05:2021 Security Misconfiguration | Yes | `argparse` default-secure; no `--unsafe` flags. |
| A08:2021 Software / Data Integrity Failures | Partial | Stale-cache warning surfaced (never silently swallowed). |
| A01:2021 Broken Access Control (path traversal) | Limited (xlsx-9 v1 has single output file, no directory layout) | Same-path guard via `Path.resolve()`. Path traversal via `--output-dir` not applicable in v1 (single-file output only). |

### 7.4. Privilege and filesystem boundaries

- **Reads:** the input `.xlsx` only (delegated to `xlsx_read/`).
- **Writes:** `OUTPUT` file (or stdout). Nothing else. No temp files.
  No subprocess. No network.
- **No shell.** No `subprocess.run`, no `os.system`.
- **No network.** No `urllib`, `requests`, `socket`.

---

## 8. Scalability and Performance

### 8.1. Memory model

**Streaming emit (D-A7):** xlsx-9 writes one markdown table at a time.
Memory peak = `O(table_max_cells)` — specifically, the `TableData`
for the largest table (its `rows` list already materialised by
`xlsx_read.read_table`). Previous tables are flushed to the output
sink before the next `read_table` call. No whole-workbook intermediate
object model.

**Upper bound:** A 100K-row × 30-column table → `TableData.rows` ≈
3M cells. With `xlsx_read` streaming mode (≥ 100 MiB workbooks):
~180 MB for the rows list + ~100 MB openpyxl working set = ~280 MB
peak. With non-streaming mode (< 100 MiB): ~300-600 MB total. GFM
emit doubles the string volume (~2× source bytes); HTML emit is ~5-10×
the source byte count for cell text. Output is streamed to sink; no
second copy in memory.

**Stdout flush:** `flush()` is called after each table when streaming
to a pipe, so a piped consumer sees output incrementally.

### 8.2. CPU

Dominant cost is `xlsx_read.read_table` (per xlsx-8 ARCH §8 baseline:
100K × 10 = ~5-10 s on commodity hardware). Markdown emit itself is
O(cells) with trivial per-cell cost (`html.escape`, `str.replace`,
`str.split`). Document the upper bound: emitting 3M-cell HTML output
is feasible if the upstream read fits; ~30 s end-to-end (indicative,
not a contract — actual time depends on workbook structure and hardware).

### 8.3. I/O

Single output sink, sequential append. No random-access seeks. For
file output, `Path.open("w", encoding="utf-8")` is used (no temp-file
rename needed because there is no partial-write risk on single-file
output — each table is independently valid markdown).

---

## 9. Cross-Skill Replication Boundary (CLAUDE.md §2)

### 9.1. Files this task MUST NOT modify

The 5-file subset of the cross-skill silent gate that touches xlsx:

```bash
diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
diff -q  skills/docx/scripts/_soffice.py skills/xlsx/scripts/_soffice.py
diff -q  skills/docx/scripts/_errors.py  skills/xlsx/scripts/_errors.py
diff -q  skills/docx/scripts/preview.py  skills/xlsx/scripts/preview.py
diff -q  skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
```

All five must produce **no output** after this task lands. xlsx-9
touches ZERO cross-replicated files; the gate must remain silent.

### 9.2. New files (xlsx-only, no replication required)

- `skills/xlsx/scripts/xlsx2md.py` (shim)
- `skills/xlsx/scripts/xlsx2md/__init__.py`
- `skills/xlsx/scripts/xlsx2md/cli.py`
- `skills/xlsx/scripts/xlsx2md/dispatch.py`
- `skills/xlsx/scripts/xlsx2md/emit_gfm.py`
- `skills/xlsx/scripts/xlsx2md/emit_html.py`
- `skills/xlsx/scripts/xlsx2md/emit_hybrid.py`
- `skills/xlsx/scripts/xlsx2md/inline.py`
- `skills/xlsx/scripts/xlsx2md/headers.py`
- `skills/xlsx/scripts/xlsx2md/exceptions.py`
- `skills/xlsx/scripts/xlsx2md/tests/` (all test files + fixtures)
- `skills/xlsx/references/xlsx-md-shapes.md`

### 9.3. Modified files (xlsx-only, no replication required)

- `skills/xlsx/SKILL.md` — registry entry for `xlsx2md.py`; §10
  honest-scope note.
- `skills/xlsx/.AGENTS.md` — `## xlsx2md` section.
- `skills/xlsx/scripts/md_tables2xlsx/tests/test_md_tables2xlsx.py` —
  `TestRoundTripXlsx9::test_live_roundtrip_xlsx_md`
  `@unittest.skipUnless(xlsx2md_available(), ...)` predicate flips to
  live. This is a **test activation only** — no production code in
  `md_tables2xlsx/` is changed.

### 9.4. Frozen surfaces (must not be touched)

- `skills/xlsx/scripts/xlsx_read/**` (xlsx-10.A frozen API; xlsx-9
  is a consumer, not a modifier).
- `skills/xlsx/scripts/pyproject.toml` (toolchain reused as-is).
- `skills/xlsx/scripts/requirements.txt` (no new deps).
- `skills/xlsx/scripts/install.sh` (no new post-hooks).
- `skills/xlsx/scripts/xlsx2csv2json/**` (xlsx-8 package; no changes).
- `skills/xlsx/scripts/xlsx2csv.py`, `skills/xlsx/scripts/xlsx2json.py`
  (xlsx-8 shims; no changes).

---

## 10. Honest Scope (v1)

Items **(a)–(j)** + **R3-H1** are locked verbatim from TASK §1.4.
Architecture-layer additions:

- **(a)** Rich-text spans → plain-text concat. Delegated to
  `xlsx_read._values.extract_cell`.
- **(b)** Cell styles (color / font / fill / border / alignment /
  conditional formatting) → dropped. Markdown has no cell-style
  representation.
- **(c)** Comments → dropped. Deferred to v2 sidecar
  `xlsx2md.comments.json`.
- **(d)** Charts / images / shapes → dropped. `preview.py` remains
  the canonical visual path.
- **(e)** Pivot tables → unfold to static cached values.
- **(f)** Data validation dropdowns → dropped without warning.
- **(g)** Formulas without cached value → empty cell + warning;
  OR `data-formula` attr in HTML with `class="stale-cache"` when
  `--include-formulas` active.
- **(h)** Shared / array formulas → cached value only.
- **(i)** ListObjects `headerRowCount=0` → synthetic `col_1..col_N`
  headers emitted by library; hybrid auto-promotes to HTML; warning
  always surfaced.
- **(j)** Diagonal borders / sparklines / camera objects → dropped.
- **(R3-H1)** `--sanitize-sheet-names` option dropped entirely.
  Sheet names emitted verbatim from `xl/workbook.xml/<sheets>`.

**Architecture-layer honest-scope additions:**

- **A-A1** — No HTML pretty-printing (indentation / line breaks within
  `<table>`). Output is compact HTML (no `  <tr>\n    <td>`). Rationale:
  round-trip with xlsx-3 doesn't need pretty HTML; bytes saved; no
  external lib needed for formatting.
- **A-A2** — No CSS class names on emitted `<table>` / `<th>` / `<td>`
  (except `class="stale-cache"` for stale-cache formula cells per (g)
  above). CSS styling is a render-side concern. v2 may add
  `--css-class-prefix` if user request.
- **A-A3** — `<thead>` multi-row reconstruction is ambiguous when a
  header cell contains literal ` › ` (U+203A) as plain data content
  (not as a separator). The reconstruction will misinterpret it. This
  is an accepted edge case: xlsx-3's read direction has the same
  ambiguity; the symmetric contract is locked. A workbook with literal
  U+203A in headers is the user's responsibility.
- **A-A4 (SUPERSEDED by D-A15)** — `--hyperlink-scheme-allowlist` is
  default-enabled in v1 (NOT deferred to v2). Default allowlist:
  `http,https,mailto`. Scheme-filtered hyperlinks (e.g. `javascript:`,
  `data:`, `ftp:`) are emitted as plain text + `UserWarning`. This
  applies to both the HTML `<a href>` path and the GFM `[text](url)`
  path. See §7.2 and D-A15.

- **(k)** `--header-rows smart` is a pass-through to the library's
  `_detect_data_table_offset` heuristic (xlsx-8a-09). xlsx-9 does NOT
  re-implement the heuristic. Edge cases in heuristic detection are
  therefore `xlsx_read/`'s responsibility, not this package's.

- **(l)** `--hyperlink-scheme-allowlist` default `http,https,mailto`
  covers the common case. `ftp:`, `file:`, `tel:`, custom schemes, and
  any future protocol not in the list are stripped to text. Users who
  require additional schemes must pass `--hyperlink-scheme-allowlist`
  explicitly.

- **(m)** `hyperlinks=True` in `read_table` incurs a per-cell openpyxl
  relationship lookup. For very wide workbooks (> 10K hyperlinks) in
  `--memory-mode streaming` (`read_only_mode=True`), this may be
  slower than the non-streaming path because openpyxl's read-only
  mode does not cache relationship data. This is an openpyxl
  implementation detail, not a design choice of xlsx-9.

---

## 11. Atomic-Chain Skeleton (Planner handoff)

TASK §8 lists 8 atomic beads (012-01..012-08). Architecture-side
refinement with file-level deliverables:

| # | Slug | File-level deliverables | Stub-First gate |
| --- | --- | --- | --- |
| 012-01 | `pkg-skeleton` | `xlsx2md.py` shim (≤ 60 LOC, stub `main()` call); `xlsx2md/__init__.py` (`__all__` locked, stubs re-exported); `cli.py` argparse skeleton (flags declared, `main()` returns 0); `exceptions.py` (`_AppError` + 5 subclasses with `CODE` attrs); `tests/` directory structure with empty `test_*.py` files (RED). | `python3 xlsx2md.py --help` exits 0; `python3 -c "from xlsx2md import convert_xlsx_to_md"` works; `ruff check scripts/` green. |
| 012-02 | `cross-cutting-envelopes` | `cli.py`: `_validate_flag_combo` raises `IncludeFormulasRequiresHTML`, `SelfOverwriteRefused`, and `HeaderRowsConflict`; `_resolve_paths` with `Path.resolve()` guard and output-parent auto-create; `_errors` integration; terminal catch-all at `main()` top level (R23(f): any unhandled exception → redacted `InternalError` code 7 envelope); `convert_xlsx_to_md` `_build_argv` in `__init__.py` (includes `memory_mode` and `hyperlink_scheme_allowlist` kwargs). Tests: encrypted → exit 3; macro → exit 0 + warning; same-path → exit 6; `--json-errors` envelope shape v1; M7 lock exit 2 before I/O; `HeaderRowsConflict` exit 2 before I/O; terminal catch-all emits code 7 with redacted message. | UC-08, UC-09, R13, R14(h), R23, R23(f), R24 acceptance criteria green. |
| 012-03 | `dispatch-and-reader-glue` | `dispatch.py`: `iter_table_payloads`; `_detect_mode_for_args` (D-A2 gap-filter); `_resolve_read_only_mode(args)` mapping `--memory-mode` to `read_only_mode` bool/None for `open_workbook` (D-A14); sheet filtering (`--sheet`, `--include-hidden`); `_gap_fallback_if_empty` (R8.f). Tests: sheet filtering; hidden skip; `--no-table-autodetect`; `--no-split`; gap-fallback warning path; `--memory-mode streaming` → `read_only_mode=True`; `--memory-mode auto` + file size < 100 MiB → `read_only_mode=False`; `--header-rows smart` forwarded verbatim to `read_table`. | `test_dispatch.py` green; smoke open + enumerate + detect; R14(g), R20a. |
| 012-04 | `emit-gfm` | `emit_gfm.py`: pipe-row + separator-row + body-row; `inline.py`: `_escape_pipe_gfm`, `_newlines_to_br`, `_render_hyperlink` (with `allowed_schemes` param, D-A15); `_apply_gfm_merge_policy` (duplicate / blank / fail). Tests: pipe `\|` escape; `\n` → `<br>`; hyperlink `[text](url)` for allowed scheme; blocked scheme (`ftp:`) → plain text + warning; empty allowlist → all hyperlinks plain text; multi-row ` › ` flatten + warning; synthetic header GFM; `--gfm-merge-policy` variants. | `test_emit_gfm.py` ≥ 10 tests green; UC-01, R10, R10a, R16 green. |
| 012-05 | `emit-html` | `emit_html.py`: `<table>` + `<thead>` + `<tbody>`; `colspan`/`rowspan`; child-cell suppression; `data-formula` attr; `html.escape` for text + attrs; `_emit_thead` reconstructing multi-row `<tr>`; `<a href>` emission only for allowed schemes (D-A15 via `inline.py`). `headers.py`: `split_headers_to_rows`, `compute_colspan_spans`, `validate_header_depth_uniformity`. Tests: merge `colspan="2"` anchor; child-cell absent; `data-formula` present; `<br>` in cells; `<a href>` hyperlinks for allowed scheme; `javascript:` href → plain text + warning (Sec-MED-2); multi-row `<thead>` with `colspan`; synthetic `<thead>` for `headerRowCount=0`; `html.escape` for `<script>` literal in cell. | `test_emit_html.py` ≥ 12 tests green; UC-04, UC-05, UC-11, R10a, R11, R14, R18 green. |
| 012-06 | `emit-hybrid` | `emit_hybrid.py` (TASK R2.e): `select_format` with four promotion rules (§2.1 F3); `emit_workbook_md` H2/H3 orchestration loop; `_has_body_merges`, `_is_multi_row_header`, `_has_formula_cells`, `_is_synthetic_header` predicates. ≥ 8 unit tests per TASK §5.2: GFM selection (no merges, single-row header, no formulas); HTML selection (merges present); HTML selection (multi-row header); HTML selection (formula-cell in hybrid+include-formulas); HTML selection (headerRowCount=0); `--format gfm` + merges + default policy → exit 2 `GfmMergesRequirePolicy`; multi-sheet H2 ordering; multi-table H3 ordering; `--no-split` emits `### Table-1` H3. | `test_emit_hybrid.py` ≥ 8 tests green; UC-03, UC-04, R12, R15 green. |
| 012-07 | `roundtrip-contract` | `skills/xlsx/references/xlsx-md-shapes.md` (full document per C6 spec). xlsx-3 test flip: `test_live_roundtrip_xlsx_md` `@skipUnless` gate activated; live round-trip asserts cell-content byte-equality (NOT sheet-name equality — D9 lock). Tests: `T-cell-newline-br-roundtrip` green (xlsx-9 → xlsx-3 cycle). | All 25 E2E scenarios green; xlsx-3 live round-trip passes; `xlsx-md-shapes.md` exists and has ≥ 4 sections. |
| 012-08 | `final-docs-and-validation` | `skills/xlsx/SKILL.md` registry row; `skills/xlsx/.AGENTS.md` section; module docstrings for honest-scope §1.4 items per module; regression tests for A-A3 (literal ` › ` in header → reconstruction result consistent across re-runs); regression for D9 (`History` sheet name preserved verbatim); regression for D13 (`headerRowCount=0` HTML emit visible `<thead>`); regression for R6.h (all-flags-omitted output shape pinned against synthetic fixture — single-sheet, single-row header, no merges, ISO dates, no formulas → GFM output); regression for R20.e (number-format heuristic — `#,##0.00` cell `1234.5` → markdown cell contains `"1,234.50"`); regression for D-A15 (`javascript:` href → plain text, no `<a href>`); regression for R23(f) (unhandled exception → code 7 envelope with redacted message); regression for R14(h) (`HeaderRowsConflict` on int + non-whole); regression for R14(g) (`--header-rows smart` forwarded to library); regression for R20a (`--memory-mode streaming` → `read_only_mode=True`). `validate_skill.py skills/xlsx` exit 0; `ruff check scripts/` green; 5-line `diff -q` silent gate; full test suite green. | All gates green. |

---

## 12. Open Questions

> **All blocking ambiguities are resolved.** The items below were
> considered during the design pass and closed as D-A decisions. They
> are retained here for traceability.

- **Q-A1 (CLOSED → D-A locked):** Should `--no-split` emit a
  `### Table-1` H3 heading, OR should the whole sheet be emitted
  directly under the `## SheetName` H2 with no H3?
  **Decision (locked in §2.1 F3):** emit `### Table-1` H3 — predictable
  layout for downstream parsers; consistent with the gap-detect case
  where unnamed tables always get `### Table-N` headings.

- **Q-A2 (CLOSED → D-A7):** Multi-sheet output with mixed
  `--format hybrid` per-table choices — should the EMIT ORDER
  interleave HTML + GFM tables, OR should tables per sheet share a
  per-sheet format?
  **Decision (locked in §3.1):** per-table format — predictable, no
  surprise behaviour. A document with `## Sheet1 \n [HTML table] \n
  ## Sheet2 \n [GFM table]` is fully valid CommonMark + GitHub
  Flavored Markdown.

- **Q-A3 (CLOSED → D-A):** `--gfm-merge-policy=duplicate` semantics —
  when a 2×3 merge fills 6 cells, do all 6 cells get the anchor value,
  OR does only the first row get duplicated?
  **Decision (locked in §2.1 F4):** all 6 cells get the anchor value.
  Matches xlsx-8 `--merge-policy=fill` semantic for downstream tooling
  consistency. Warning emitted with count of duplicated cells.

---

## 13. Decision-Record Summary

Full table of all decisions locked in this architecture document.
D1–D14 are from TASK; D-A1–D-A15 are architecture-layer additions.

| ID | Decision (one-line) |
| --- | --- |
| **D1** | Single in-skill package `xlsx2md/` |
| **D2** | Default `--format hybrid` |
| **D3** | Default `--gfm-merge-policy fail` |
| **D4** | Default `--datetime-format ISO` |
| **D5** | Hyperlinks always extracted via `include_hyperlinks=True` |
| **D6** | Multi-row header flatten separator = ` › ` (U+203A) |
| **D7** | `--no-table-autodetect` via `r.source=="gap_detect"` post-call filter |
| **D8** | Same-path guard via `Path.resolve()` (follows symlinks) |
| **D9** | Sheet-name asymmetry with xlsx-3 is expected, NOT a regression |
| **D10** | Stream-emit row-by-row; memory peak = one `TableData` at a time |
| **D11** | DEPRECATED (folded into D5) |
| **D12** | Multi-row header HTML reconstruction from flat ` › `-joined headers; no `xlsx_read` API extension |
| **D13** | `headerRowCount=0` → visible synthetic `<thead>` in HTML mode; warning always emitted |
| **D14** | Cross-5 envelope `type` for GFM-merges error = `GfmMergesRequirePolicy` (not `MergedCellsRequireHTML`) |
| **D-A1** | Single package `xlsx2md/`; emit-side branching ≤ 50 LOC |
| **D-A2** | `--no-table-autodetect` via post-call filter; library API frozen |
| **D-A3** | Single public helper `convert_xlsx_to_md`; `--flag=value` atomic-token form (xlsx-3 pattern) |
| **D-A4** | `lxml.html.HTMLParser` NOT used; xlsx-9 emits HTML, does not parse it |
| **D-A5** | Package imports only `xlsx_read.<public>`; ruff banned-api enforced |
| **D-A6** | `xlsx_read` warnings propagate via `warnings.showwarning`; NOT injected into markdown body |
| **D-A7** | Streaming emit to output sink; one table at a time; stdout `flush()` after each table |
| **D-A8** | `Path.resolve()` same-path guard even when extensions differ |
| **D-A9** | `html.escape()` for HTML cell text + attrs; `\|` for GFM pipe escape; no custom escaper |
| **D-A10** | All fail paths route through `_errors.report_error()`; no `sys.exit(N)` elsewhere |
| **D-A11** | Multi-row `<thead>`: count ` › ` separators per header; group into N rows; raise `InconsistentHeaderDepth` if non-uniform |
| **D-A12** | `\n` → `<br>` applied inside emit layer; library returns raw value verbatim |
| **D-A13** | `--header-rows smart` inherited from xlsx-8a-09; pass-through to `read_table(header_rows="smart")`; no re-implementation of heuristic in xlsx-9 |
| **D-A14** | `--memory-mode {auto,streaming,full}` inherited from xlsx-8a-11; CLI flag → `open_workbook(read_only_mode=...)` pass-through; `auto` uses ≥ 100 MiB size threshold |
| **D-A15** | `--hyperlink-scheme-allowlist` default-enabled in v1 (NOT v2-deferred); default `http,https,mailto`; scheme-filtered hyperlinks emit text-only + warning; supersedes A-A4 v2-deferral |
| **D-A16** | **Path C′ — parallel hyperlink-extraction pass** via `dispatch._extract_hyperlinks_for_region` (mirrors xlsx-8 pattern). Crosses `reader._wb` to access `cell.hyperlink.target`; `read_table` called with `include_hyperlinks=False` so display text survives in `TableData.rows`. Yields `(SheetInfo, TableRegion, TableData, hyperlinks_map)` **4-tuple** (not 3-tuple as originally specified). Closes the "URL replaces display text" gap from §5.3 honest-scope; allowlist filter applied at dispatch boundary (D-A15 enforcement point). |
| **D-A17** | **Streaming-warnings `showwarning` hook** via `cli._streaming_warnings_to_stderr` context manager — replaces the original `warnings.catch_warnings(record=True)` buffering pattern (which silently dropped warnings on exception paths and defeated D-A7 streaming UX). Each `warnings.warn(...)` writes immediately to stderr + flush; survives any exception from `emit_workbook_md`. |
| **D-A18** | **Atomic temp-file write** via `<output>.partial` sibling + `os.replace(temp, final)`; validation (D-A19) runs against TEMP **before** publish so a failing M2 gate does NOT leave bogus content at `output_path`. On any failure (emit or validate) temp is unlinked. Stdout mode unchanged. |
| **D-A19** | **Env-flag re-parse gate `XLSX_XLSX2MD_POST_VALIDATE`** (`1/true/yes/on`) re-reads the temp file pre-publish; raises `PostValidateFailed` (code 7) on empty / unrecognised-as-markdown content. Default off. |
| **D-A20** | **Effective-streaming detection** via `reader._read_only` post-open. The hyperlink-unreliability warning fires for either explicit `--memory-mode=streaming` OR library auto-streaming (size threshold ≥ 100 MiB on `--memory-mode=auto`); previously only fired on explicit. Second documented D-A5 closed-API crossing (first being `reader._wb` in D-A16). |
| **D-A21** | **`--include-formulas` wiring**: `cli.main` passes `keep_formulas=args.include_formulas` to `open_workbook`; `emit_html._emit_tbody` detects formula strings (`value.startswith("=")`) → emits `data-formula` attribute + `class="stale-cache"`. When BOTH formula AND hyperlink are present on the same cell, both are preserved: `<td data-formula="..."><a href="...">=formula</a></td>` (was: silent link loss in iter-1). |
| **D-A22** | **GFM angle-bracket form for hyperlinks** with `()` / whitespace / `\n`/`\r`/`\t` / `<>` in the URL: `[text](<url>)` per CommonMark §6.3; the FULL set `<→%3C, >→%3E, \n→%0A, \r→%0D, \t→%09` is percent-encoded inside the angle form to prevent CommonMark-renderer markdown-injection bypass of the scheme allowlist via LF in a permitted URL. |
| **D-A23** | **Lazy `cell_addr` computation**: `_make_cell_addr(c_idx)` closure invoked only when `hyperlinks_map.get((header_band+r_idx, c_idx))` is non-None (i.e. the warning-path applies). Avoids O(cells) `get_column_letter` + f-string allocations for the 99.999% of cells without hyperlinks. |
| **D-A24** | **Kwarg validation in `convert_xlsx_to_md`** against `_KNOWN_KWARGS` frozenset (14 names) → raises `TypeError` for unknown kwarg. Prevents `SystemExit(2)` propagation from argparse to Python callers. |
| **D-A25** | **xlsx-8a-09 auto→smart fallback hot-patch (post-ship 2026-05-14)**: in `iter_table_payloads`, after `read_table(header_rows="auto")` returns, validate header-depth uniformity via `headers.validate_header_depth_uniformity`. On `InconsistentHeaderDepth`, retry the same region with `header_rows="smart"` (xlsx-8a-09 R11) + emit one `UserWarning` per retry; otherwise-identical kwargs (`merge_policy`, `include_hyperlinks`, `include_formulas`, `datetime_format`). Gated to **auto only** — explicit `--header-rows=smart` / `--header-rows=<int>` honour user intent and bypass the retry (downstream defensive raise still fires for explicit cases). Surfaces xlsx-8a-09 transparently for default-flag users on the masterdata banner-and-metadata pattern. |

---

## 14. Post-merge adaptations (vdd-multi 2026-05-14)

The body of §1–§13 documents the **design-time specification**. The
shipped implementation differs in nine documented ways — all
introduced during VDD adversarial review (Sarcasmotron + vdd-multi
iterations 1 + 2). The deltas below are LIVE in the merged code; the
upstream §1–§13 prose is preserved verbatim for historical reference.
Each subsection cross-links to its D-A decision row.

### 14.1. Path C′ — 4-tuple dispatch yield (D-A16)

Originally `iter_table_payloads` yielded `(SheetInfo, TableRegion, TableData)` triples and `read_table` was called with `include_hyperlinks=True`. Probing `xlsx_read._values.extract_cell` revealed that `include_hyperlinks=True` REPLACES the cell value with the URL — display text is lost. The Path C′ refactor (mirrors xlsx-8 `_extract_hyperlinks_for_region` at `xlsx2csv2json/dispatch.py:102-176`) does a parallel openpyxl pass via `reader._wb` to extract `cell.hyperlink.target` while `read_table(include_hyperlinks=False)` preserves display text. Result: emit produces `[click here](https://...)` with both pieces intact.

**Files**: [`dispatch.py:221-281`](../skills/xlsx/scripts/xlsx2md/dispatch.py#L221) (`_extract_hyperlinks_for_region`), `iter_table_payloads` now yields **4-tuple**. Consumers: `emit_hybrid.emit_workbook_md` unpacks 4-tuple; `emit_gfm_table` and `emit_html_table` accept new `hyperlinks_map=` param.

### 14.2. Streaming `showwarning` hook (D-A17)

Original §5 prose specified `with warnings.catch_warnings(record=True)` + post-loop drain. This pattern silently dropped the captured list on any exception path AND deferred user-facing stderr output until workbook completion (defeating D-A7 per-table flush UX). The shipped implementation replaces it with `cli._streaming_warnings_to_stderr()` — a context manager installing a custom `warnings.showwarning` that writes each warning to stderr + flush IMMEDIATELY. Restores `original_showwarning` + `filters[:]` in `finally:` (no global state leak).

**Files**: [`cli.py:420-463`](../skills/xlsx/scripts/xlsx2md/cli.py#L420) (`_streaming_warnings_to_stderr`).

### 14.3. Atomic temp-file write (D-A18) + post-validate ordering

Original §5 prose said `_resolve_output_stream(output_path)` returns a stream opened on `output_path` directly. The shipped version returns `(stream, temp_path)` where `temp_path = output_path.with_suffix(output_path.suffix + ".partial")` — a sibling tempfile in the same directory (atomic `os.replace` semantics). M-NEW-2 iter-2 patch reordered validation: `_post_validate_output(temp_path)` runs BEFORE `os.replace`; failure → unlink temp + propagate. Result: validation failures NEVER publish bogus content to `output_path`. Stdout mode unchanged (`temp_path is None`).

**Files**: [`cli.py:355-373`](../skills/xlsx/scripts/xlsx2md/cli.py#L355) (`_resolve_output_stream`), [`cli.py:540-578`](../skills/xlsx/scripts/xlsx2md/cli.py#L540) (`main` finally block).

### 14.4. Env-flag re-parse gate (D-A19)

Original §2.1 F8 catalogue listed `PostValidateFailed (CODE=7)` as "env-flag post-validate gate" but provided no wiring. The shipped implementation adds `_post_validate_output(output_path)` consulted by `XLSX_XLSX2MD_POST_VALIDATE=1/true/yes/on` (case-insensitive). Re-reads the just-written markdown; asserts non-empty AND contains at least one `## ` / `|---` / `<table` marker; raises `PostValidateFailed` envelope code 7 on failure.

**Files**: [`cli.py:376-417`](../skills/xlsx/scripts/xlsx2md/cli.py#L376) (`_post_validate_output`).

### 14.5. Effective-streaming detection (D-A20)

Original §5.1 specified the hyperlink-unreliability warning fires when `args.memory_mode == "streaming"`. The shipped implementation reads `reader._read_only` post-open (after `open_workbook` returned) and sets `args._read_only_effective` — so the warning ALSO fires on `--memory-mode=auto` when the library auto-streamed for a ≥ 100 MiB workbook. Second documented D-A5 closed-API crossing (after `_wb` for Path C′).

**Files**: [`cli.py:531-533`](../skills/xlsx/scripts/xlsx2md/cli.py#L531), [`dispatch.py:315-323`](../skills/xlsx/scripts/xlsx2md/dispatch.py#L315) (gate consumes `_effective` with fallback to `_resolved is True`).

### 14.6. `--include-formulas` wiring (D-A21)

Original §5 had `--include-formulas` forwarding to `read_table(include_formulas=True)` but missed `keep_formulas=True` on `open_workbook` — so openpyxl's `data_only=True` default discarded formula strings before the library could surface them. M1 iter-2 patch: `cli.main` passes `keep_formulas=args.include_formulas`; `emit_html._emit_tbody` detects formula strings (`value.startswith("=")`) → emits `<td data-formula="=A1+B1" class="stale-cache">` with empty content per §1.4(g). M-NEW-1 iter-2 patch: when the same cell has BOTH a formula AND a hyperlink, the hyperlink-rendered `<a href="...">=A1+B1</a>` is preserved as cell content (was: silent link loss because `cell_text=""` blindly overwrote the link).

**Files**: [`cli.py:520-525`](../skills/xlsx/scripts/xlsx2md/cli.py#L520) (`keep_formulas` wiring), [`emit_html.py:247-272`](../skills/xlsx/scripts/xlsx2md/emit_html.py#L247) (formula + hyperlink preservation).

### 14.7. GFM angle-bracket completeness (D-A22)

Original M8 spec patched `[text](url)` → `[text](<url>)` for parens. Iter-2 sec-HIGH review surfaced that LF/CR/Tab/`<` in the URL ended the angle-form destination prematurely, allowing markdown-injection bypass of the scheme allowlist via `\n[evil](javascript:alert(1))` planted in a permitted https URL. The shipped patch percent-encodes the FULL set `<→%3C, >→%3E, \n→%0A, \r→%0D, \t→%09` inside the angle form.

**Files**: [`inline.py:221-235`](../skills/xlsx/scripts/xlsx2md/inline.py#L221).

### 14.8. Lazy cell_addr (D-A23)

Original M6 spec was "compute cell_addr per cell, pass to inline.render_cell_value for warning messages". The shipped version uses a `_make_cell_addr(c_idx)` closure invoked ONLY when `hl_href is not None` (the warning-path applies). Saves O(cells) `get_column_letter` + f-string allocations on workbooks without dense hyperlinks (3M unnecessary ops at R20a worst case).

**Files**: [`emit_gfm.py:228-240`](../skills/xlsx/scripts/xlsx2md/emit_gfm.py#L228), [`emit_html.py:214-224`](../skills/xlsx/scripts/xlsx2md/emit_html.py#L214).

### 14.9. Kwarg validation in `convert_xlsx_to_md` (D-A24)

Original §5.2 didn't specify kwarg validation. Argparse's `parser.error()` raised `SystemExit(2)` which `BaseException` — caught NEITHER by the Python-helper's documented integer-return contract NOR by `except Exception`. M4 iter-1 patch: validate kwargs against `_KNOWN_KWARGS` frozenset BEFORE building argv; raise `TypeError` for unknown.

**Files**: [`__init__.py:101-128`](../skills/xlsx/scripts/xlsx2md/__init__.py#L101).

### 14.10. Cumulative VDD review trail

| Round | Critic | Findings | Patched | Tests added |
|---|---|---|---|---|
| Sarcasmotron iter-1 | code-reviewer | 5 blockers | 5 | 0 (orchestrator) |
| vdd-multi iter-1 logic | critic-logic | 1 HIGH + 7 MED + 4 LOW + 5 INFO | HIGH+MED | 5 + 18 |
| vdd-multi iter-1 security | critic-security | 1 HIGH + 2 MED + 1 LOW + 4 INFO | HIGH+MED | (subsumed) |
| vdd-multi iter-1 performance | critic-performance | 2 HIGH + 3 MED + 2 LOW + 4 INFO | HIGH+MED | (subsumed) |
| vdd-multi iter-2 logic | critic-logic | 2 MED + 1 LOW + 1 INFO | all MED | 8 |
| vdd-multi iter-2 security | critic-security | 1 HIGH(esc) + 4 LOW | HIGH only | (subsumed) |
| vdd-multi iter-2 performance | critic-performance | 0 new | — | — |
| post-ship hot-patch 2026-05-14 | real-world fixture | 1 default-flag UX bug (masterdata `InconsistentHeaderDepth`) | 1 (D-A25 auto→smart fallback) | 4 |
| **Total** | — | 4 HIGH + 10 MED + 13 LOW + 13 INFO + 1 UX | 4 HIGH + 10 MED + 1 UX | **43 new regression tests** |

281 xlsx2md tests + 1243 xlsx-skill cumulative tests; 5 release gates clean throughout.

### 14.11. xlsx-8a-09 auto→smart fallback (D-A25)

Originally `iter_table_payloads` invoked `read_table(header_rows=args.header_rows)` once and yielded the result; if `auto` returned headers with non-uniform `_SEP`-count (the masterdata Timesheet banner-and-metadata pattern where columns shift from depth-1 to depth-4 across the data table), the downstream `validate_header_depth_uniformity` defensive raise (D-A11) fired during emit and the whole conversion aborted with exit 1. Users had to know to pass `--header-rows=smart` by hand. The hot-patch wraps the header validation inside dispatch, catches `InconsistentHeaderDepth` for the `auto` case, retries with `header_rows="smart"` (xlsx-8a-09 R11 / D-A13), and emits one `UserWarning` per affected region so the auto-shift is observable in stderr. Explicit `smart` / `<int>` bypass the gate — the user asked for that mode, the defensive raise still surfaces.

Real-world validation: `tmp4/masterdata_report_202604.xlsx` (Timesheet banner + 7-cell metadata block above the real header row) now succeeds on default flags; output byte-identical to the explicit `--header-rows=smart` invocation. 4 sibling workbooks (`Моделирование.xlsx`, `Ярли_cтатус (1).xlsx`, `Книга1.xlsx`, `0931_DarkStore_оценка_20260508_ AP.xlsx`) do NOT trigger the fallback (uniform header depths) — gate is tight.

**Files**: [`dispatch.py:366-394`](../skills/xlsx/scripts/xlsx2md/dispatch.py#L366) (fallback block in `iter_table_payloads`); imports `validate_header_depth_uniformity` from `.headers` and `InconsistentHeaderDepth` from `.exceptions`. **Tests**: 4 in `TestAutoToSmartFallback` (`test_dispatch.py`): retry on nonuniform, no-retry on uniform, explicit-smart no-retry, explicit-int no-retry.

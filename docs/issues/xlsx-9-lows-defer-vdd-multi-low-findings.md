---
id: XLSX-9-LOWS-DEFER
type: known-issue
status: open
opened_at: 2026-05-14
category: tech-debt
severity: LOW
component: xlsx
slug: xlsx-9-lows-defer-vdd-multi-low-findings
---

# XLSX-9-LOWS-DEFER — vdd-multi iter-1+2 LOW-tier findings (deferred to xlsx-9b)

**Status:** DEFERRED to a future `xlsx-9b` follow-up task.
**Backlog row:** none yet (open as `xlsx-9b` if user prioritises).
**Severity:** LOW (paper-cut tier; no HIGH or MEDIUM remain
unaddressed).
**Context:** vdd-multi iterations 1 and 2 (2026-05-14) ran 3 critics
in parallel and surfaced 4 HIGH + 10 MEDIUM + 13 LOW + 13 INFO
findings on the shipped xlsx-9 code. All HIGH + MEDIUM are fixed
with 39 new regression tests. The 13 LOW findings are intentionally
deferred — none are exploitable in the documented trust model, and
none are blockers. Catalogued below for posterity / future xlsx-9b
prioritisation.

## Logic-tier LOWs

- **L1 — `_has_body_merges` ignores vertical-merge col-0.** In
  `emit_hybrid.py:_has_body_merges`, the heuristic looks for `None`
  cells at `col_idx > 0` (horizontal merge detection). A vertical
  merge anchored at column 0 produces `None` at column 0 for
  subsequent rows — which the predicate skips. Hybrid mode would
  emit GFM (lossy) instead of promoting to HTML.
  **Fix path:** widen heuristic to also flag `col_idx==0 and row>0`
  with a column-history check, OR expose `reader.merges_in_region`
  from xlsx-10.B for accurate merge-span detection.
- **L2 — `INPUT=None` → `Internal error: TypeError`.** When the
  positional INPUT is omitted (`python3 xlsx2md.py`), `_resolve_paths`
  hits `Path(None).resolve(strict=True)` → `TypeError` → terminal
  catch-all → InternalError code 7. The error message is unhelpful
  ("Internal error: TypeError"). **Fix path:** add explicit
  `if args.INPUT is None: raise argparse.ArgumentTypeError("INPUT required")`
  at the top of `_resolve_paths`.
- **L7 — `--no-table-autodetect` bypasses R14h gate.** The
  `_validate_flag_combo` gate at `cli.py:296-310` checks
  `not args.no_table_autodetect AND not args.no_split` to permit
  int `--header-rows`. `--no-table-autodetect` filters to gap-detect
  regions only, which can still be multiple → int header-rows N
  applied uniformly is still a hazard. Currently locked by
  `test_cli_envelopes.py:91-96`. **Fix path:** tighten the gate to
  reject `--header-rows N + --no-table-autodetect` OR document the
  exception.
- **L8 — Empty sheet silently omits `## SheetName` H2.**
  `emit_workbook_md` only emits H2 when at least one region yields.
  Multi-sheet workbook with an intentionally-empty "Notes" sheet
  produces output that silently omits the sheet entirely.
  **Fix path:** emit `## SheetName\n\n*(empty sheet)*\n\n` for
  zero-region sheets, OR document in honest-scope §1.4.
- **L9 — `--sheet=all` collides with workbook sheet named `"all"`.**
  The sentinel value `"all"` is reserved; a workbook with a sheet
  literally named `"all"` cannot be targeted individually.
  **Fix path:** add a separate `--all-sheets` flag, OR document.

## Security-tier LOWs (all honest-scope per `references/security.md` §1 trust model)

- **Sec-LOW-1 — D-A9 cell-value markdown pass-through.** GFM mode
  passes `*`, `_`, `` ` ``, `[`, `]`, `(`, `)` through as
  "markdown-in-cell affordance". A workbook cell with value
  `"[click](javascript:alert(1))"` (literal string, no hyperlink
  object) emits as a parseable Markdown link in GFM, bypassing the
  scheme-allowlist (which only filters hyperlinks attached as
  workbook hyperlink objects). Pre-existing limitation, not iter-2
  regression. **Fix path:** add `references/security.md` §2.7 entry
  cataloguing this — or harden with `[`/`]`/`(`/`)` escaping at the
  cost of breaking the markdown-in-cell affordance.
- **Sec-LOW-2 — M5 `<output>.partial` symlink / TOCTOU.** `open(temp_path, "w")`
  follows symlinks. Attacker-controlled output directories where
  adversaries can pre-plant `<output>.md.partial` as a symlink are
  out of scope per `references/security.md` §1 (non-multi-tenant
  output directory). **Fix path:** O_NOFOLLOW per-component (xlsx-8d
  pattern); or document the trust assumption at the M5 code site.
- **Sec-LOW-3 — M3 `reader._read_only` closed-API crossing
  undocumented at architecture layer.** This is the second
  D-A5 exception (first being `reader._wb` in Path C′). A future
  xlsx_read rename would silently disable the streaming-mode
  warning. **Fix path:** promote `WorkbookReader.is_read_only` to
  public API in xlsx_read; consume the public property.
- **Sec-LOW-4 — `_post_validate_output` unbounded `read_text`.**
  Opt-in via `XLSX_XLSX2MD_POST_VALIDATE=1`. A 10 GB output OOMs
  the validator. **Fix path:** bound the read to 1 MiB head
  (`fp.read(1024*1024)`) — substring markers appear early.
- **Sec-LOW-5 — Log injection via CR/LF in sheet name reaching
  warning messages.** `cell_addr_prefix=f"{sheet_info.name}!"`
  feeds workbook sheet names (which can contain `\r\n` via raw XML
  edit) directly into warning text streamed to stderr. Defense in
  depth, not exploitable per trust model §1. **Fix path:**
  `.replace("\r", "\\r").replace("\n", "\\n")` on sheet names before
  log interpolation.
- **Sec-LOW-6 — `str(value or "")` truthiness bug with `value=0`.**
  Three sites in `inline.py` (lines 207, 227, 249): a cell value
  of integer `0` or boolean `False` with a hyperlink renders as
  empty display text. Correctness bug, not security. **Fix path:**
  use `str(value) if value is not None else ""`.

## Performance-tier LOWs

- **Perf-LOW-1 — `_make_cell_addr` closure rebuilt per row in HTML
  emit.** `emit_html._emit_tbody` defines the closure inside the
  `for r_idx, row` loop. ~80ms per 100K-row workbook (closure
  creation overhead). **Fix path:** hoist the function definition
  out of the row loop and pass `abs_row` as a positional argument.
- **Perf-LOW-2 — Defensive `list(table_data.rows)` /
  `list(table_data.headers)` copies in both emit modules.** Not
  mutated downstream; copies are pure waste. **Fix path:** remove
  the `list()` wrapping. ~50ms per 100K-row table; ~800KB peak
  memory delta.
- **Perf-LOW-3 — Hybrid mode 1-2 extra O(cells) scans.**
  `_has_body_merges`, `_is_multi_row_header`, `_has_formula_cells`
  each iterate the full table before emit decides GFM vs HTML.
  Architectural trade-off; documented in module docstring.
  **Fix path:** expose merge-count / formula-presence metadata
  from xlsx_read so the predicates become O(1) (requires
  xlsx-10.B-scope API extension).

**Workaround:** None — all items are LOW severity and the chain is
production-ready as of 2026-05-14. Promoting any item to a
follow-up task is at user discretion.

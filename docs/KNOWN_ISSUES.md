# Known Issues

Catalogue of **acknowledged but currently-unfixed** issues in this
repository. Each entry is a deliberate deferral, NOT a bug to
re-discover. Future agents (and humans) MUST read this file before
opening a new task that touches the same surface — see
[CLAUDE.agentic.md](../CLAUDE.agentic.md) §"Pipeline §1 Analysis
Phase" which mandates this read.

**Entry lifecycle**: an issue lives here while it is **documented +
deferred**. When a fix lands, the entry is moved to a section
"Resolved" with a commit-hash pointer, or simply deleted with the
fix commit referenced from the related task/backlog row.

---

## Performance

> **PERF-HIGH-1** (matrix size + cap) was **closed by xlsx-8a-06**
> on 2026-05-13: `_gap_detect` + `_build_claimed_mask` switched to
> `bytearray` flat buffers (8× memory reduction) and
> `_GAP_DETECT_MAX_CELLS` raised 1M → 50M. Entry removed in the
> commit that landed those changes. See `docs/PLAN.md` 011-06
> and `docs/ARCHITECTURE.md` §15.10.

### PERF-HIGH-2 — `payloads_list = list(payloads)` materialises generators (narrowed residual after xlsx-8a-07/08)

- **Status**: **Partially closed (2026-05-13, xlsx-8a-07 / xlsx-8a-08)**.
  - R9 / xlsx-8a-07 drops the `json.dumps`-string-buffer copy for
    JSON file output (one of three full-payload copies removed —
    `emit_json.py:79` reference below no longer holds; the
    `json.dump(fp)` path goes straight to the file).
  - R10 / xlsx-8a-08 **streams the emit-side R11.1 single-region**
    output (the most common large-table case) row-by-row — drops
    the full `shape` dict + `_rows_to_dicts` materialisation from
    the emit path. **Design target**: peak RSS ≤ 200 MB on
    3M-cell payloads vs 1-1.5 GB in v1. **As-shipped honest-scope**:
    upstream `read_table` + `apply_merge_policy` still materialise
    `table_data.rows` (~180 MB on 3M cells), so the realistic peak
    is closer to ~400-600 MB — still a 2-3× win over v1, but not
    the 200 MB design target. The 200 MB budget is **unmeasured
    at the 3M-cell scale** in xlsx-8a's test suite (see
    `docs/ARCHITECTURE.md` §15.10.6 honest-scope note); a future
    task can lift the read-side to a streaming generator or add
    a 3M-cell `tracemalloc` regression to pin the actual budget.
  - **Residual**: R11.2-4 multi-sheet / multi-region shapes still
    build the full `shape` dict in memory (`_shape_for_payloads`
    in `emit_json.py`); and CSV multi-region path's
    `payloads_list = list(payloads)` in
    [`emit_csv.py:59`](../skills/xlsx/scripts/xlsx2csv2json/emit_csv.py#L59)
    still materialises the **region list** (per-row writes already
    stream via `csv.writer.writerow`).
- **Severity**: MED (lowered from HIGH after the R11.1 closure).
- **Location** (residual after xlsx-8a):
  - [`skills/xlsx/scripts/xlsx2csv2json/emit_csv.py`](../skills/xlsx/scripts/xlsx2csv2json/emit_csv.py) line ~59:
    `payloads_list = list(payloads)` — **region-list materialisation
    only**; per-row writes already stream via `csv.writer.writerow`.
  - `_shape_for_payloads` R11.2-4 branches in `emit_json.py`
    build a full dict-of-arrays shape before serialisation.
- **Workaround for users**: prefer single-sheet single-region
  outputs (R11.1 path is fully streamed). For multi-sheet
  workbooks at 3M+ cells, split the input or use `--sheet <NAME>`
  to bound the working set.
- **Fix path** (when prioritised): per-sheet streaming for R11.2
  (multi-sheet single-region) — open ``{``, for each sheet write
  ``"name": [<stream rows>]`` + ``,``/``}`` closer. R11.3-4 nested
  dicts cannot be RFC-8259-streamed without inventing a chunked-
  encoding contract. CSV multi-region per-region streaming is
  feasible (each region writes its own file) but needs an
  ``n_regions`` pre-count for dispatch.
- **Related**: future ticket
  **`xlsx-8c-multi-sheet-stream`** (registered in
  [`docs/office-skills-backlog.md`](office-skills-backlog.md) on
  2026-05-13 by 011-08); open when a real R11.2 large-table
  workload is observed.
- **Do not**: claim this as "fixed" by trimming
  `--include-hyperlinks` or `--include-formulas` — those reduce
  per-cell payload size, not the structural materialisation cost.

---

## XLSX-10B-DEFER (xlsx-7 refactor to consume xlsx_read)

**Status:** DEFERRED (14-day timer started 2026-05-14, deadline
2026-05-28).
**Backlog row:** `xlsx-10.B` in
[`docs/office-skills-backlog.md`](office-skills-backlog.md).
**Context:** xlsx-7 (`xlsx_check_rules/`) duplicates a portion of
xlsx-10.A `xlsx_read/` reader logic. The refactor was deferred at
xlsx-10.A merge to bound the v1 surface; xlsx-9 merge starts the
14-day ownership-bounded timer. If unaddressed by 2026-05-28, the
duplication becomes a regression risk for any future
`xlsx_read` API change.
**Owner:** TBD (assigned at xlsx-10.B kickoff).
**Workaround:** None required for xlsx-7's current functionality;
the duplication is correctness-preserving as of 2026-05-14.

---

## XLSX-9-LOWS-DEFER (vdd-multi iter-1+2 LOW-tier findings, deferred to xlsx-9b)

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

### Logic-tier LOWs

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

### Security-tier LOWs (all honest-scope per `references/security.md` §1 trust model)

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

### Performance-tier LOWs

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

---

## How to add a new entry

1. Append below the relevant category (or create a new top-level
   `##` if necessary — `## Security`, `## Logic`, `## UX`, etc.).
2. Use the schema: ID • Status • Severity • Location • Symptom •
   Reproduction • Workaround • Fix path • Related • Do-not.
3. Cross-link to the backlog row that owns the deferral decision.
4. If a fix lands, **delete the entry** in the same commit that
   ships the fix; reference the KNOWN_ISSUES entry text in the
   commit body for posterity.

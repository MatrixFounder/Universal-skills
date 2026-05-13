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

## How to add a new entry

1. Append below the relevant category (or create a new top-level
   `##` if necessary — `## Security`, `## Logic`, `## UX`, etc.).
2. Use the schema: ID • Status • Severity • Location • Symptom •
   Reproduction • Workaround • Fix path • Related • Do-not.
3. Cross-link to the backlog row that owns the deferral decision.
4. If a fix lands, **delete the entry** in the same commit that
   ships the fix; reference the KNOWN_ISSUES entry text in the
   commit body for posterity.

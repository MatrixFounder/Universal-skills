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

### PERF-HIGH-1 — `_gap_detect` materialises an 8 MB `list[list[bool]]` occupancy matrix per sheet

- **Status**: Deferred (skipped from `xlsx-8a` hardening task per
  /vdd-multi-3 triage 2026-05-13; user confirmed < 5 MB workbook
  scale where the cost is invisible).
- **Severity**: HIGH (per `/vdd-multi-3` performance critic) — but
  only when workbook sheets push the `_GAP_DETECT_MAX_CELLS=1_000_000`
  cap. For typical office reports (≤ 25 × 1007 = 25K cells) the cost
  is sub-millisecond.
- **Location**: [`skills/xlsx/scripts/xlsx_read/_tables.py`](../skills/xlsx/scripts/xlsx_read/_tables.py)
  — `_gap_detect` lines ~307-345 (`occupancy: list[list[bool]] = []`)
  and `_build_claimed_mask` lines ~406-416
  (`mask = [[False] * w for _ in range(h)]`).
- **Symptom**: at the 1M-cell cap, allocates a `list[list[bool]]` of
  8 MB transient memory per sheet (8 bytes/ref + per-list overhead).
  100 sheets × concurrent CLI invocations on a CI box → ~800 MB
  transient resident.
- **Reproduction**: workbook with `<dimension ref="A1:ALL1048576"/>`
  declaring a near-cap bbox of legitimately-typed sparse data.
  Default `--tables auto` engages gap-detect; the cap blocks
  iteration extent but the matrix allocation runs first.
- **Workaround for users**: avoid `--tables auto` on workbooks with
  inflated `<dimension>` refs; use `--tables whole` (R23's in-loop
  cap protects that path) or `--tables tables-only`.
- **Fix path** (when prioritised): replace the
  `list[list[bool]]` with a `bytearray(n_rows * n_cols)` flat buffer
  indexed by `[r * n_cols + c]`. ~10 LOC change. 8x memory reduction
  (1 byte/cell vs 8 bytes/ref). Big-O unchanged
  (still O(n_rows × n_cols)). Apply the same transformation to
  `_build_claimed_mask`. **Add early-exit on `if not claimed: return None`**
  so the empty-claimed common case (Tier-1 + Tier-2 empty) skips
  the allocation entirely. Test: synthesise a workbook with the
  cap-near bbox and assert peak RSS stays under a budget (use
  `tracemalloc` for the measurement).
- **Related**: [`docs/office-skills-backlog.md`](office-skills-backlog.md)
  → row `xlsx-8a` notes this is **explicitly skipped** from the
  `xlsx-8a` hardening task scope (`Perf-HIGH-1 (bytearray) + Perf-HIGH-2 (streaming) НЕ
  включены в xlsx-8a`). Raise as a standalone task `xlsx-8b-perf-bytearray`
  if a real OOM or wall-clock budget breach is observed.
- **Do not**: silently fix this alongside an unrelated refactor —
  the bytearray switch changes the in-memory representation across
  `_gap_detect` ↔ `_build_claimed_mask` ↔ `_split_on_gap`
  ↔ `_tight_bbox` and needs paired updates. Keep it atomic.

---

### PERF-HIGH-2 — `payloads_list = list(payloads)` materialises the entire generator before any byte hits disk

- **Status**: Deferred (skipped from `xlsx-8a` per the same triage;
  user confirmed `< 5 MB` workbook scale where the cost is invisible).
- **Severity**: HIGH at scale (multi-GB resident memory on 50-sheet
  × 1000-region × 10K-row workbooks). Sub-second for typical inputs.
- **Location**:
  - [`skills/xlsx/scripts/xlsx2csv2json/emit_csv.py`](../skills/xlsx/scripts/xlsx2csv2json/emit_csv.py) line ~59:
    `payloads_list = list(payloads)`
  - [`skills/xlsx/scripts/xlsx2csv2json/emit_json.py`](../skills/xlsx/scripts/xlsx2csv2json/emit_json.py) line ~79:
    `payloads_list = list(payloads)`
- **Symptom**: every region's `TableData` (headers + all rows +
  hyperlinks_map) is held in memory before the emit loop writes
  the first byte. For JSON specifically there is a second
  full-document `dict[str, Any]` built by `_shape_for_payloads`,
  then `json.dumps(shape, indent=2)` builds the entire serialised
  string — **three resident copies** of the dataset before disk
  flush.
- **Reproduction**: workbook with 100 sheets × 1000 regions × 10K
  rows × 25 cols ≈ 25 billion cells claimed by `--tables auto`.
  Process RSS climbs to multi-GB before output begins.
- **Workaround for users**: limit `--tables whole` to single-region
  emits (per-sheet output is naturally one region). For multi-sheet
  + multi-region workbooks, split the input or use
  `--sheet <NAME>` to bound the working set.
- **Fix path** (when prioritised): the CSV multi-region path
  (`--output-dir DIR`) is the streaming-friendly candidate —
  every region writes to its own file, so we can emit-and-discard
  per region. Refactor `_emit_multi_region` to consume the
  generator directly without `list(payloads)`. The single-region
  path (`output=Path`) and JSON paths cannot stream because
  JSON has no structural form that fits R11.a-e and CSV
  single-region needs n_regions for the shape decision. ~80-120
  LOC across `emit_csv.py` + `dispatch.py`; add a streaming test
  that asserts peak memory stays bounded while N output files
  grow.
- **Honest scope of any fix**: JSON cannot be made streaming
  without breaking the documented R11.a..e output shapes
  (RFC 8259 doesn't define partial-write semantics). CSV
  single-region writing to a Path can be streamed if dispatch
  computes `n_regions` upfront via `peek` — keep that change
  scoped, do not retrofit JSON.
- **Related**: [`docs/office-skills-backlog.md`](office-skills-backlog.md)
  → row `xlsx-8a` Notes mention this explicit skip. Raise as
  `xlsx-8c-perf-streaming` if real OOM observed at scale.
- **Do not**: claim this as "fixed" by trimming `--include-hyperlinks`
  or `--include-formulas` — those reduce per-cell payload size, not
  the structural materialisation cost.

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

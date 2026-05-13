# Task 011 Review v3 — Performance Axis Extension (R8/R9/R10)

- **Date:** 2026-05-13
- **Reviewer:** Task-Reviewer Agent (subagent re-review after v2)
- **TASK file:** [`docs/TASK.md`](../TASK.md) (v3 — perf-axis extension)
- **Previous review:** [`docs/reviews/task-011-review.md`](task-011-review.md) (v2 — APPROVED WITH COMMENTS)
- **Status:** **APPROVED WITH COMMENTS** (1 MAJOR + 5 MINOR; no blocking issues)

---

## 1. General Assessment

The v3 scope extension layers three performance-axis fixes
(R8/R9/R10) on top of the v2 security-axis (R1-R7). The two-axis
structure is consistent across §0 meta, §1.1 goal, §1.2 motivation,
§2 RTM, §3 Use Cases (UC-06/07/08 added), §4.1 budgets, §5.1/§5.2
acceptance criteria, §7.3 locked decisions, §8 atomic chain, §9
risks. Counts agree (8 atomic fixes; 6 of 7 deferred items closed;
≥ 34 new tests).

The R10 streaming refactor (most complex of the three) is well-
specified: `_rows_to_dicts` becomes a generator, callers in R11.2-4
branches consume eagerly via `list(...)` at the call-site, and
`_shape_for_payloads` early-detects R11.1 to dispatch to the
streaming helper. The byte-identity invariant for non-empty
payloads is correct (I traced the indent math). One MAJOR clarity
issue on the §8 atomic-chain ordering rationale (technically wrong
explanation — see M1 below). Five minor consistency / cross-link
quibbles. No blocking issues.

---

## 2. Comments

### 🔴 CRITICAL (BLOCKING) — none.

### 🟡 MAJOR

#### M1 — §8 atomic-chain ordering rationale is technically wrong

**Section affected:** TASK §8 lines ~921-925.

TASK §8 says order 011-06 → 011-07 → 011-08 is required because
"bytearray refactor changes `_gap_detect` call shape that the JSON
paths also exercise". This is **technically wrong**: `_gap_detect`
is upstream of `detect_tables` → `read_table` → `iter_table_payloads`
→ `emit_json`. The JSON path consumes `TableData` (rows / headers
/ region / warnings), not the occupancy matrix. The bytearray flip
is an internal `_gap_detect` representation change that the JSON
emit path never sees.

The **real** ordering reason is **test fixture timing**: the R9
and R10 tests both synthesise 100K × 30 = 3M-cell fixtures
(`test_R9_file_output_no_string_buffer`,
`test_R10_stream_3M_cells_peak_rss_below_200MB`,
`test_R10_stream_byte_identical_to_v1_single_sheet_single_region`).
These fixtures cannot complete fixture-setup under the v1
`_GAP_DETECT_MAX_CELLS = 1_000_000` cap — the cap raises during
`detect_tables` before any data reaches `emit_json`. R8's cap raise
to 50M is therefore a **fixture-side prerequisite**, not a
runtime-call-shape prerequisite.

**Recommended fix:** rewrite §8 lines 921-925 as:

```
Order is **linear, not parallel**. 011-01..011-05 are the security
axis (any internal order valid; locked to match backlog row).
011-06..011-08 are the performance axis and must be executed in this
order because:

- 011-06 raises `_GAP_DETECT_MAX_CELLS` to 50M, which is a
  **fixture-side prerequisite** for the 3M-cell synthesised
  fixtures used by R9 and R10 tests (`test_R9_file_output_no_string_buffer`,
  `test_R10_stream_3M_cells_peak_rss_below_200MB`,
  `test_R10_stream_byte_identical_to_v1`). Without R8's raise, the v1
  1M-cell cap fires during `detect_tables` before any JSON emit code
  runs.
- 011-07 and 011-08 can in principle ship in either order
  (R9 covers R11.2-4 file-output; R10 supersedes R9 for R11.1).
  The recommended order is 07 → 08 so the simpler `json.dump(fp)`
  refactor stabilises before the larger generator refactor lands.
```

This is a clarity fix, not a logic bug — the ordering itself is
correct.

### 🟢 MINOR

#### N1 — `_whole_sheet_region` missing from §1.3 file-touch table for R8

**Section affected:** TASK §1.3 R8 file-touch rows.

R8 raises `_GAP_DETECT_MAX_CELLS` from 1M → 50M. The constant is
read by **two** call-sites in `_tables.py`:

- `_gap_detect` line ~346 (`if n_rows * n_cols > _GAP_DETECT_MAX_CELLS`)
- `_whole_sheet_region` line ~580 (`if cells_scanned > _GAP_DETECT_MAX_CELLS`)

The §1.3 file-touch table lists `_gap_detect`, `_build_claimed_mask`,
`_split_on_gap`, `_tight_bbox` but **not** `_whole_sheet_region`,
even though the constant lift directly raises the cap there too.
This is intentional behaviour (per §2 R8 sub-feature (e) "raises
to 50M alongside — no matrix change there — just the constant"),
but the file-touch table should reflect it explicitly so the
Planner / Developer knows the lift fans out to 5 functions, not 4.

**Recommended fix:** add a row to the §1.3 table:

```
| `xlsx-8a-06` | `scripts/xlsx_read/_tables.py` | ~564-600 |
  `_whole_sheet_region`: `cells_scanned > _GAP_DETECT_MAX_CELLS`
  in-loop cap reads the same lifted constant; no body change.
  Listed for traceability — silent-truncation threshold for
  `--tables whole` rises 50× alongside `_gap_detect`. |
```

#### N2 — `tracemalloc` is a new test pattern; flag as stdlib-only

**Section affected:** TASK §5.2 / §6.1.

R8, R9, R10 acceptance criteria all use `tracemalloc` snapshots
(`test_R8_bytearray_correctness`, `test_R9_file_output_no_string_buffer`,
`test_R10_stream_3M_cells_peak_rss_below_200MB`). Currently
`tracemalloc` is not imported anywhere under `skills/xlsx/scripts/*/tests/`.
It is **stdlib-only** (no `requirements.txt` change), but is a new
test pattern that future maintainers will encounter for the first
time in this task.

**Recommended fix:** add to §5.2 or §6.1: "R8/R9/R10 tests introduce
`tracemalloc` (stdlib, Python 3.4+) as a peak-RSS budget pattern;
no `requirements.txt` change. Test pattern: `tracemalloc.start();
... run code ...; current, peak = tracemalloc.get_traced_memory();
tracemalloc.stop(); self.assertLess(peak, BUDGET)`."

#### N3 — §4.1 1.5 GB R11.2-4 budget conflates production workload and test fixture

**Section affected:** TASK §4.1 lines ~664-668.

§4.1 lists "JSON R11.2-4 multi-sheet (R9): ≤ 60 s wall-clock; peak
RSS ≤ 1.5 GB" as a budget on a 3M-cell production workload, but the
R9 test (`test_R9_file_output_no_string_buffer`) uses a **1M-cell**
fixture per §2 R9 sub-feature (g). The 1.5 GB number is a
**production-workload guidance**, not a test-gate.

**Recommended fix:** clarify §4.1 line 666 as:
"JSON R11.2-4 multi-sheet (R9), **production workload guidance**:
≤ 60 s wall-clock; peak RSS ≤ 1.5 GB on a 3M-cell payload. **R9 test
gate**: 1M-cell fixture, peak RSS < v1 baseline by at least the
serialised-string-buffer size (~100 MB sanity-check on the savings)."

#### N4 — D8 cites non-existent "Q-15-1"

**Section affected:** TASK §7.3 D8 line ~865.

D8 says "Constant; no CLI / env-var (TASK Q-15-1: cap is policy)".
TASK §7.2 numbers questions Q-1, Q-2, Q-3 (not Q-15-1).
"Q-15-1" is the analogous question in ARCHITECTURE.md §15.8 — the
**architecture-side** policy precedent — not a TASK-side question.

**Recommended fix:** rewrite D8 line ~865 as: "Constant; no CLI /
env-var. Policy precedent from TASK §7.2 Q-1 (`TooManyMerges` cap
is also constant-only) and ARCHITECTURE.md §15.8 Q-15-1
(`_MAX_COLLISION_SUFFIX` / `_MAX_MERGES` are constants, not flags)."

#### N5 — Sub-task 011-08 acceptance gate missing PERF-HIGH-2 Location-subsection update

**Section affected:** TASK §8 011-08 line ~936 / KNOWN_ISSUES.md
PERF-HIGH-2 Location subsection.

TASK §8 011-08 says "narrow `PERF-HIGH-2` entry in
`docs/KNOWN_ISSUES.md` to 'multi-sheet / multi-region only'". The
narrowing direction is explicit, but `KNOWN_ISSUES.md` PERF-HIGH-2
**currently lists `emit_csv.py:59` as one of two Location**
subsections (`emit_csv.py:59` + `emit_json.py:79`). After R8 + R10
land, the CSV-single-region path is already streaming-friendly
(per the existing `_emit_single_region` row-by-row CSV writer); the
remaining `payloads_list = list(payloads)` in `emit_csv.py:59` only
materialises **the region list**, not per-row data. The
**KNOWN_ISSUES.md residual scope should be** explicit about: "JSON
R11.2-4 multi-sheet shape dict (full copy in memory); CSV
multi-region path's region-list materialisation (per-row writes
remain streaming-friendly)".

**Recommended fix:** §8 011-08 acceptance gate adds:
"`docs/KNOWN_ISSUES.md` PERF-HIGH-2 update touches BOTH the
`Status` line AND the `Location` subsection: drop the
`emit_json.py:79` reference (R10 closes that path); narrow the
`emit_csv.py:59` reference to 'region-list materialisation only —
per-row writes are streaming via `csv.writer.writerow`'."

---

## 3. Final Recommendation

**APPROVED WITH COMMENTS.** Required fixes before Planning:

1. **M1**: Rewrite §8 lines 921-925 with the fixture-timing
   rationale (5-line replacement).
2. **N1**: Add `_whole_sheet_region` to §1.3 R8 file-touch table.
3. **N2**: Add `tracemalloc` pattern note to §5.2 or §6.1.
4. **N3**: Disambiguate §4.1 1.5 GB budget (production vs test).
5. **N4**: Fix D8 dangling "Q-15-1" reference.
6. **N5**: Extend §8 011-08 acceptance gate with PERF-HIGH-2
   Location-subsection update.

The data-model deltas, RTM granularity, UC structure, acceptance
criteria verifiability, atomic-chain composability, locked
decisions D8/D9/D10, and KNOWN_ISSUES.md cross-links are all
sound. No blocking issues; Planner may proceed once the 6 fixes
above land. The carve-out into `xlsx_read/_tables.py` is bounded
(matches `KNOWN_ISSUES.md` PERF-HIGH-1's explicit atomic-update
requirement across `_gap_detect ↔ _build_claimed_mask ↔
_split_on_gap ↔ _tight_bbox`).

```json
{"has_critical_issues": false}
```

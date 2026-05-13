# Architecture Review v3 — §15.10 Performance Hardening (xlsx-8a R8/R9/R10)

- **Date:** 2026-05-13
- **Reviewer:** Architecture Reviewer (subagent re-review after v2)
- **Architecture file:** [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) §15.10 only (lines ~1479-1738). §15.1-§15.9 out of scope (already approved in v2).
- **Previous review:** [`docs/reviews/architecture-011-review.md`](architecture-011-review.md) (v2 — APPROVED WITH COMMENTS)
- **Status:** **APPROVED WITH COMMENTS** (1 MAJOR + 4 MINOR + 1 cross-cutting; no blocking issues)

---

## 1. General Assessment

§15.10 is a tight, additive scope extension that lands three
performance-axis fixes on top of the §15.1-§15.9 security axis.
The data-model deltas are minimal (one constant raise, two
matrix-representation flips), the JSON deltas are correctly
bounded to R11.1 (the structurally-streamable shape), and the
carve-out into `xlsx_read/_tables.py` is justified and atomic
per `KNOWN_ISSUES.md` PERF-HIGH-1's explicit instruction to update
`_gap_detect ↔ _build_claimed_mask ↔ _split_on_gap ↔ _tight_bbox`
together — §15.10.5 enumerates all four functions, respecting
that mandate.

The decision-record extension (D-A15..D-A18) is numerically
coherent (continues from D-A14, no reuse) and stylistically
consistent with D-A1..D-A14. The threat-model update in §15.10.4
correctly closes PERF-HIGH-1 and narrows PERF-HIGH-2 to a residual
surface; the cross-link to §14.7.4 resolves to the M2 fix anchor
introduced in the v2 review.

The byte-identity claim of the R10 streaming snippet (§15.10.2)
is **correct for non-empty single-region payloads** — I traced the
indent math for `[{"a": 1}, {"b": 2}]` and the streaming output
matches v1 `json.dumps(..., indent=2)` plus trailing newline. The
cap-raise security analysis (50M = 1/343 of XFD1048576) is
numerically sound.

No 🔴 CRITICAL / BLOCKING issues. One 🟡 MAJOR (M3 below) on the
empty-payload byte-identity invariant being overstated. Four
🟢 MINOR (m4-m7). Planner may proceed once M3 is addressed (one-line
fix in §15.10.2 pseudocode + §15.10.8 Q-15-4, not a redesign).

---

## 2. Comments

### 🔴 CRITICAL (BLOCKING) — none.

### 🟡 MAJOR

#### M3 — §15.10.2 / §15.10.4 overstate the R10 byte-identity invariant; empty-array case is NOT byte-identical

**Sections affected:** ARCHITECTURE.md §15.10.2 ("byte-identity
invariant" paragraph), §15.10.4 PERF-HIGH-2 row + §14.7.4 row,
§15.10.8 Q-15-4.

I traced the indent math on the §15.10.2 pseudocode for the
empty-payload case:

- v1: `json.dumps([], indent=2) = "[]"`, written as `"[]\n"` (3 bytes).
- §15.10.2 streaming pseudocode: `fp.write("[\n  ")` →
  `"[\n  "`; generator yields nothing; `first` stays `True`;
  `fp.write("\n]\n")` → `"\n]\n"`. Concatenated:
  `"[\n  \n]\n"` (7 bytes — `[`, `\n`, space, space, `\n`,
  `]`, `\n`).

That is **not** byte-identical to v1. §15.10.8 Q-15-4
acknowledges the empty-case but its narrative reports the
streaming output as `"[\n]\n"` (4 bytes) — also wrong; the
pseudocode writes two trailing spaces after the opening `[\n`
that Q-15-4 does not account for.

This matters because:

1. §15.10.2 states the streaming output is "byte-identical to
   the v1 path on **every** R11.1 fixture" and identifies
   `test_R10_stream_byte_identical_to_v1_single_sheet_single_region`
   as the locking gate. An R11.1 empty-table fixture (empty `[]`
   output) breaks that gate.
2. §15.10.4 marks `§14.7.4` "**Closed for R11.1**" by R10. If
   empty-payload byte-identity is sacrificed (Q-15-4 says
   "developer judgement at implementation time — accepts either
   form OR locks the streaming form"), then the closure is
   partial, not full.
3. The §15.10.6 test plan lists `test_R10_stream_empty_table`
   separately from
   `test_R10_stream_byte_identical_to_v1_single_sheet_single_region`
   — implying the empty case is segregated precisely because it
   cannot live under the byte-identity invariant.

**Recommended fix (in priority order):**

**(a) Lock the empty-payload behaviour in §15.10.2:** add a
one-line conditional in the streaming helper pseudocode for the
"empty generator" case to emit `"[]\n"` rather than `"\n]\n"`.
Remove Q-15-4's "developer judgement" hedge. Then the
byte-identity invariant holds unconditionally and the §14.7.4 /
PERF-HIGH-2 "Closed for R11.1" claim becomes accurate.

```python
def _stream_single_region_json(payload, output_path, ...):
    sheet_name, region, table_data, hl_map = payload
    rows_gen = _rows_to_dicts(table_data, hl_map, ...)
    rows_iter = iter(rows_gen)
    with output_path.open("w", encoding="utf-8") as fp:
        try:
            first_row = next(rows_iter)
        except StopIteration:
            # Empty payload — v1-compatible byte-identical output.
            fp.write("[]\n")
            return
        fp.write("[\n  ")
        first_row_json = json.dumps(
            first_row, ensure_ascii=False, indent=2,
            default=_json_default,
        ).replace("\n", "\n  ")
        fp.write(first_row_json)
        for row_dict in rows_iter:
            row_json = json.dumps(
                row_dict, ensure_ascii=False, indent=2,
                default=_json_default,
            ).replace("\n", "\n  ")
            fp.write(",\n  ")
            fp.write(row_json)
        fp.write("\n]\n")
```

**(b) If (a) is rejected:** soften §15.10.2 to "byte-identical
for non-empty R11.1 payloads; empty-payload case differs in
whitespace (`[]\n` vs `[\n  \n]\n`) and is accepted as a
documented divergence" AND soften §15.10.4 to "**Closed for
non-empty R11.1; partial for empty R11.1**" with a one-line
note pointing to Q-15-4. This is honest-scope but expands the
test matrix.

**(c) Independent of (a)/(b):** fix Q-15-4's narrative byte-string
from `"[\n]\n"` to `"[\n  \n]\n"` (matching the pseudocode) so
a future developer reading Q-15-4 doesn't implement to a wrong
target string.

Pick (a). The conditional is one branch, the gain is invariant
simplicity, and the streaming path becomes cleanly byte-identical.

### 🟢 MINOR

#### m4 — §15.10.3 D-A16 understates the consumer-chain update for the early-exit `None` return

**Section affected:** ARCHITECTURE.md §15.10.3 D-A16.

D-A16 says `_build_claimed_mask` may return `None` and "consumers
downstream rely on the matrix shape and the early-exit eliminates
the alloc when no caller would have read it." This is correct in
spirit but the current `_gap_detect` body at
[`_tables.py:372`](../../skills/xlsx/scripts/xlsx_read/_tables.py#L372)
reads `claimed_mask[r_idx][c_idx]` unconditionally — switching
to a `None`-return contract requires `_gap_detect` to guard with
`if claimed_mask is not None and claimed_mask[r * n_cols + c]:`
(or equivalent: a `claimed_mask = bytearray(0)` sentinel that is
iterable and safely-indexed-empty). The architecture leaves this
implementation choice unstated.

**Recommended fix:** add one line to §15.10.1 under the
`pre-guard` bullet:
"consumer guard in `_gap_detect` becomes
`if claimed_mask is None or not claimed_mask[r * n_cols + c]:`
(or whatever sentinel convention is chosen at implementation)."
Names the contract so the Planner has a deterministic decomposition.

#### m5 — §15.10.5 carve-out becomes 4 files in `xlsx_read/`; flag the boundary explicitly

**Section affected:** ARCHITECTURE.md §15.10.5 / §15.5 /
ARCHITECTURE.md §9.1.

§15.10.5's "Files modified" lists `_tables.py` as a fourth
`xlsx_read/` file re-opened (previously §15.5 listed `_merges.py`
+ `_exceptions.py` + `__init__.py`). The v2 review acknowledged
the §15.5 carve-out as "bounded (3 files), additive, justified".
Adding `_tables.py` as a 4th file is not by itself a redesign —
but the doc should explicitly extend the §15.5 sentence so future
readers do not think the carve-out is uncapped.

A future xlsx-8c adding a 5th re-opened file will face the same
drift question. The architecture should answer it explicitly:
**is the bound "any file in `xlsx_read/` may be re-opened on a
per-fix-with-rationale basis" or is it "no more than N files
total"?**

**Recommended fix:** one extra sentence at the end of §15.10.5
(before "No new files."):
"The §15.5 carve-out (3 files) is extended to 4 files by adding
`_tables.py`; the carve-out remains bounded by the rule 'each
re-opened file ships with a documented `KNOWN_ISSUES.md` entry or
§15.x decision record', not by a fixed file count."

#### m6 — Q-15-5 (R11.2 streaming deferral) lacks a backlog/KNOWN_ISSUES carrier

**Section affected:** ARCHITECTURE.md §15.10.8 Q-15-5.

§15.10.8 Q-15-5 defers R11.2 streaming to
`xlsx-8c-multi-sheet-stream`. That slug appears only inline in
`docs/TASK.md` and `docs/ARCHITECTURE.md`. It is **not** registered
as a backlog row in `docs/office-skills-backlog.md`, and
`KNOWN_ISSUES.md` PERF-HIGH-2 currently describes the **pre-fix**
state (full triple-copy materialisation). After 011-06..08 land,
PERF-HIGH-2 should narrow to "R11.2-4 multi-sheet/nested shapes
still materialise the shape dict; streaming deferred to
`xlsx-8c-multi-sheet-stream`" — and that follow-up needs an
actual backlog row, not just an inline mention.

**Recommended fix:** §15.10.8 Q-15-5 acceptance criterion:
"011-08 narrows PERF-HIGH-2 in `KNOWN_ISSUES.md` to **include** a
reference to the `xlsx-8c-multi-sheet-stream` follow-up by slug;
if no backlog row exists yet, 011-08 also creates a stub row in
`docs/office-skills-backlog.md`." Converts a soft mention into a
recorded follow-up.

#### m7 — §15.10.1 cap narrative ignores per-sheet vs per-invocation distinction

**Section affected:** ARCHITECTURE.md §15.10.1.

The §15.10.1 narrative says "50M cap → 50 MB transient per sheet"
and the threat-model row in §15.10.4 closes PERF-HIGH-1. Per-sheet
cost is correctly bounded. The cap is **per-sheet**, not
per-invocation. A workbook with 100 sheets each near the cap will
see cumulative-transient 50 MB × 100 = 5 GB on a single
invocation, sequentially allocated-and-freed. Each individual
peak is 50 MB so the **peak** RSS is bounded.

This is **not** a defect (peak RSS is what `tracemalloc` test
asserts) but a one-line clarification would prevent a future
reader from misreading "50 MB transient per sheet" as a
per-invocation aggregate budget.

**Recommended fix:** in §15.10.1 after "Big-O unchanged at
O(n_rows × n_cols)." add:
"Cap is per-sheet; peak RSS per invocation is bounded by 50 MB +
openpyxl working set even on 100-sheet workbooks because each
`_gap_detect` call frees its buffer before the next sheet's call
runs. Concurrent-invocation memory budget is the operator's
responsibility."

### Cross-cutting / consistency

#### CCN — §15.10.1 cite-chain to Q-15-1 is loose

**Section affected:** ARCHITECTURE.md §15.10.1.

§15.10.1 cites "Q-15-1: cap is policy" for the
`_GAP_DETECT_MAX_CELLS` raise. The original §15.8 Q-15-1 asks
"Should `_MAX_COLLISION_SUFFIX` / `_MAX_MERGES` be exposed as CLI
flags?" with a "No, caps are policy" answer. Reusing the
**rationale** for a different cap is fine, but the citation
`(Q-15-1)` reads as "this is settled by Q-15-1" when actually
D-A15 settles it and merely **echoes** the Q-15-1 policy stance.

**Recommended fix:** write "(precedent: §15.8 Q-15-1 / locked
here as D-A15)" or "(per the Q-15-1 policy-not-CLI principle,
locked here as D-A15)". Cosmetic only.

---

## 3. Final Recommendation

**APPROVED WITH COMMENTS.** The Architect should fix **M3** (lock
the empty-payload streaming output to `"[]\n"` in §15.10.2's
helper pseudocode, then drop Q-15-4's "developer judgement"
hedge). The four 🟢 minors (m4 consumer-guard contract, m5
carve-out boundary statement, m6 Q-15-5 backlog-row stub, m7
per-sheet vs per-invocation clarification) plus the cross-cutting
CCN (Q-15-1 cite tightening) are one-line edits that the Architect
should pick up in the same pass. None block Planning.

The data-model correctness (bytearray indexing math), security
analysis (50M cap = 1/343 of XFD attack envelope), decision-record
numbering (D-A15..D-A18 contiguous with D-A14), and cross-link
integrity (§14.7.4 anchor resolves) all check out. The R10
byte-identity invariant holds for non-empty payloads; only the
empty case needs the one-line fix.

```json
{"has_critical_issues": false}
```

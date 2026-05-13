# Task 011 Review — xlsx-8a Production Hardening

- **Date:** 2026-05-13
- **Reviewer:** Task-Reviewer Agent (sub-agent invocation, VDD start-feature workflow)
- **TASK file:** [`docs/TASK.md`](../TASK.md)
- **Backlog row:** `xlsx-8a` (line 198 of `docs/office-skills-backlog.md`)
- **Status:** **APPROVED WITH COMMENTS** (1 MAJOR + 6 MINOR; no blocking issues)

---

## 1. General Assessment

The technical specification is high-quality, well-structured, and
conforms tightly to the `xlsx-8a` backlog row (line 198 of
`office-skills-backlog.md`). All 5 atomic fixes (xlsx-8a-01..05) are
individually scoped with file:line references, regression-test
naming, and acceptance criteria. The RTM (§2) has dense sub-feature
breakdowns (5–7 sub-features per requirement). Use Cases UC-01..05
carry the full structure (Actors, Preconditions, Main Scenario,
Alternative Scenarios, Postconditions, Acceptance Criteria) and every
UC's acceptance criteria is mapped to grep-able / unit-testable
artifacts. The carve-out from the xlsx-10.A frozen surface (§1.3) is
appropriately bounded (3 files, additive-only) and justified by
reference to the backlog row's explicit re-opening. Honest-scope
§1.4 catalogues policy choices, and the out-of-scope items
(Perf-HIGH-1, Perf-HIGH-2, Unicode-norm, TOCTOU code-fix) are
documented in §1.3 with cross-links to `KNOWN_ISSUES.md` and
ARCH §14.7. Open Questions §7.1 is correctly empty-blocking; §7.2 /
§7.3 lock all design decisions. One MAJOR clarification needed on
JSON output-shape contract for blocked hyperlinks; the remainder are
minor labelling / cross-reference quibbles.

---

## 2. Comments

### 🔴 CRITICAL (BLOCKING) — none.

### 🟡 MAJOR

#### M1 — JSON output-shape contract for blocked hyperlinks is ambiguous

**Sections affected:** UC-03 step 5 / R3 sub-feature (c) / §1.4 (f).

The spec says blocked-scheme JSON cells emit `{"value": "Click",
"href": null}` and labels this "matches the no-hyperlink contract".
This is **inaccurate** with respect to the xlsx-8 baseline: cells
that *never had* a hyperlink emit a **bare scalar** value (per
`references/json-shapes.md §11`, the four read-back shapes), not
`{value, href: null}`. The blocked-scheme path therefore introduces
a **third, new shape** distinct from both:

- (a) "had hyperlink" → `{"value": V, "href": "url"}`
- (b) "never had hyperlink" → bare scalar `V`
- (c) **NEW (this task)** "had hyperlink but scheme blocked" →
  `{"value": V, "href": null}`

This may break downstream consumers (xlsx-2 v1 round-trip,
`references/json-shapes.md` contract, LLM-renderer schemas that
switch on the presence of `href` key). The analyst must either:

- **Option A** (preferred — preserves existing contract): emit a
  **bare scalar** for blocked-scheme cells (truly mirror the
  no-hyperlink case); the user already loses the URL anyway, so
  dropping the wrapper preserves the shape.
- **Option B** (preserves cell-level "this had a link"-ness signal):
  lock the new third shape and add an entry to
  `references/json-shapes.md §11` describing it, plus update the
  xlsx-2 v1 lossy-by-design honest-scope wording so reverse-
  restoration is not implicitly broken.

Recommend the analyst flip Option A unless there's a downstream
consumer that needs Option B's signal. Either choice should be
documented in §7.3 (Locked decisions) as **D7**, and reflected in
UC-03 step 5 + R3 sub-feature (c).

### 🟢 MINOR

#### N1 — "Closes 4 of 7 deferred items" math

**Section affected:** Meta §0 line 26-31.

The "7" total is correct (5 ARCH §14.7 items + 2 KNOWN_ISSUES
PERF-HIGH-1/2), but the labelling tags **Sec-HIGH-3** (collision-
suffix) and **Sec-MED-3** (merge-count) are **new findings from
the 2026-05-13 `/vdd-multi-3` triage**, NOT items in ARCH §14.7's
5-item catalogue. A reader chasing the count from ARCH §14.7 alone
will get confused (5 ≠ 7). Suggest a one-line footnote on line 26:
"7 = 5 from ARCH §14.7 + 2 from 2026-05-13 /vdd-multi-3 triage
(Sec-HIGH-3 collision-suffix, Sec-MED-3 merge-count)".

#### N2 — Out-of-scope location preference

**Sections affected:** §1.3 vs §1.4.

The user's review prompt asked §1.4 honest-scope to mention
Perf-HIGH-1/2, Unicode-norm, TOCTOU-code-fix. These are **present
and complete** in §1.3 under two consecutive "Out of scope"
sub-headings (deferred + acknowledged), not §1.4. Functionally
identical, but a future reader skimming for "honest scope" by
section number will need to look in two places. Either (a)
consolidate "Out of scope" into a §1.4.0 prelude and let §1.4
(a)-(g) remain policy-clauses, or (b) cross-reference from §1.4 to
§1.3. Optional polish.

#### N3 — R4 test-count arithmetic drift

**Sections affected:** UC-04 acceptance criteria / R4 sub-feature
(g) / §5.2.

UC-04 says "6 tests (one per sentinel) for quote" + "6 tests for
strip" + auxiliary off/json E2E. R4 sub-feature (g) says "6 tests"
total. §5.2 says "R4: 6 unit tests + 1 E2E DDE". Suggest the
analyst pick a single arithmetic and align all three places.

#### N4 — File:line drift defence

**Sections affected:** §1.2 / §1.3 / TASK header.

Several file:line citations are hard-coded (e.g.
`emit_csv.py:162-172`, `_merges.py:36-41`). These were verified
against the current HEAD and match, but any unrelated PR landing
between approval and implementation will drift the numbers.
Recommend either annotate "lines as of commit `<sha>`" once in §0,
or phrase as `_emit_multi_region` collision loop (no line numbers)
and let the Planner pin them.

#### N5 — Backlog row hard to grep

**Section affected:** `docs/office-skills-backlog.md` line 198.

The backlog row is a single very long line and unreadable when
grep'd. Not a TASK issue — flag for future analyst hygiene to
split that row's Notes column into a footnote.

#### N6 — §1.3 duplicate "Out of scope" H-level headings

**Section affected:** §1.3.

Two adjacent "Out of scope" sub-blocks under §1.3 (one for
deferred-to-future-task, one for acknowledged-not-in-this-task).
Distinction is meaningful but the parallel structure is visually
confusing. Suggest distinct titles like "Out of scope — deferred
to xlsx-8b/c (see KNOWN_ISSUES.md)" vs "Out of scope —
acknowledged limitation (not in this task or backlog)".

---

## 3. Final Recommendation

**APPROVED WITH COMMENTS.** No blocking issues. Proceed to
Architecture phase **after** the analyst resolves M1 (JSON
output-shape contract for blocked-scheme hyperlinks) — Option A
vs Option B is a 2-line edit in UC-03 + §1.4 (f) + R3 sub-feature
(c) and an entry under §7.3 as a locked decision. Minor items
N1–N6 can be polished during the same pass or deferred to the
Architecture-phase revisit. The TASK is well-scoped, traceable
end-to-end, and the carve-out from xlsx-10.A's frozen surface is
appropriately bounded.

```json
{"has_critical_issues": false}
```

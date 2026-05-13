# Plan Review — TASK 011 (xlsx-8a Production Hardening, 8 atomic fixes)

- **Date:** 2026-05-13
- **Reviewer:** Plan Reviewer (subagent invocation, `/vdd-plan` workflow)
- **Plan file:** [`docs/PLAN.md`](../PLAN.md)
- **Per-task files:** [`docs/tasks/task-011-01-collision-suffix-cap.md`](../tasks/task-011-01-collision-suffix-cap.md) through [`task-011-08-r11-1-streaming.md`](../tasks/task-011-08-r11-1-streaming.md) (8 files)
- **TASK source:** [`docs/TASK.md`](../TASK.md) v3
- **Architecture source:** [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) §15.1-§15.10
- **Status:** **APPROVED WITH COMMENTS** (no blocking issues; 2 MAJOR + 4 MINOR)

---

## 1. General Assessment

The plan decomposes TASK 011 v3 into **8 atomic beads** (011-01..011-08),
one bead per RTM requirement (R1, R2, R3, R4, R5, R8, R9, R10 — R6/R7
are meta-requirements absorbed into every code-changing bead).
Stage 1 (Security axis, 011-01..05) is internally order-independent;
Stage 2 (Performance axis, 011-06..08) is linearly ordered with the
**fixture-timing prerequisite** wording explicitly carried from the
v3 task-review M1 correction. Stage 3 (Integration) is canonical.

Each per-task file follows the skill-planning template (Use Case
Connection → Task Goal → Changes Description → Test Cases →
Acceptance Criteria → Stub-First Pass Breakdown → Notes). Every
task carries explicit binary acceptance gates. PLAN.md §4
"Stub-First Compliance Matrix" gives an at-a-glance view of
Pass 1 / Pass 2 for all 8 beads.

Architecture decisions D7 + D-A11..D-A18 from TASK §7.3 / ARCH
§15.3 + §15.10.3 are referenced explicitly inside the relevant
beads (011-03 cites D-A11/A12; 011-04 cites D-A13; 011-06 cites
D-A15/A16; 011-07 cites D-A17; 011-08 cites D-A18 +
Q-15-5/Q-15-6). KNOWN_ISSUES.md lifecycle (PERF-HIGH-1 deletion
in 011-06; PERF-HIGH-2 narrowing in 011-08) and the
`xlsx-8c-multi-sheet-stream` backlog stub creation in 011-08
(per arch-review m6 fix / Q-15-5) are anchored both in the
Changes Description AND the Acceptance Criteria of the relevant
beads.

---

## 2. RTM ↔ Use Case ↔ Bead Coverage (1:1)

| RTM ID | TASK §3 UC | Bead | Description File |
| --- | --- | --- | --- |
| R1 | UC-01 | 011-01 | `task-011-01-collision-suffix-cap.md` |
| R2 | UC-02 | 011-02 | `task-011-02-merges-cap.md` |
| R3 | UC-03 | 011-03 | `task-011-03-hyperlink-scheme-allowlist.md` |
| R4 | UC-04 | 011-04 | `task-011-04-escape-formulas.md` |
| R5 | UC-05 | 011-05 | `task-011-05-security-docs.md` |
| R6 | (meta) | absorbed into 011-01..04 ACs | — |
| R7 | (meta) | absorbed into 011-01, 011-02 ACs | — |
| R8 | UC-06 | 011-06 | `task-011-06-cap-raise-and-bytearray.md` |
| R9 | UC-08 | 011-07 | `task-011-07-json-dump-file-output.md` |
| R10 | UC-07 | 011-08 | `task-011-08-r11-1-streaming.md` |

**Verdict:** 10/10 RTM rows mapped; 8/8 use cases covered.

---

## 3. Comments by Criticality

### 🔴 CRITICAL (BLOCKING) — none.

### 🟡 MAJOR

#### M1. Bead 011-08 effort sits at L (~6 h), exceeding the 2-4 h atomicity envelope

**Section affected:** `task-011-08-r11-1-streaming.md:381` Notes.

The bead packs three coordinated changes (generator refactor of
three `_rows_to_*` functions + new `_stream_single_region_json`
helper + `_shape_for_payloads` early-detect dispatch) plus two
doc updates plus a backlog row creation. The Prime Directive in
`06_planner_prompt.md` §1 caps atomic tasks at 2-4 h.

**Recommendation:** either

- **(a)** split into 011-08a (generator refactor + sentinel +
  R11.2-4 `list(...)` wrappers + `NotImplementedError` stub
  body, ~3 h) and 011-08b (`_stream_single_region_json` body +
  sentinel dispatch + KNOWN_ISSUES narrow + backlog stub, ~3 h),
  OR
- **(b)** accept the L sizing and document the justification in
  PLAN.md §1 (the byte-identity risk in 011-08 is the highest-risk
  item per the plan's own §5 risk register; keeping the two
  passes inside one bead has a continuity benefit).

Either resolution is acceptable; the planner should decide and
surface the choice.

#### M2. Bead 011-05 does not reference the 12-line cross-skill `diff -q` gate in its Acceptance Criteria

**Section affected:** `task-011-05-security-docs.md:166-171` AC list.

The other 7 beads carry the gate line in their AC (or Regression
Tests). The omission is **technically harmless** — 011-05 touches
only `skills/xlsx/references/security.md`, `skills/xlsx/SKILL.md`,
and `docs/ARCHITECTURE.md`, none in the replicated set — so the
gate is auto-satisfied. PLAN.md §0.3 explicitly says docs-only
beads auto-satisfy the gate.

**Recommendation:** for uniformity / CI checklist hygiene, add
one acceptance line:
```
- [ ] 12-line cross-skill `diff -q` gate from ARCH §9.4 silent
      (auto-satisfied; no files in the replicated set touched).
```

### 🟢 MINOR

#### m1. Stale TC cross-reference in 011-04

**Section affected:** `task-011-04-escape-formulas.md:137` Component
Integration paragraph.

Paragraph asserts a hyperlink+escape edge case is "asserted by a
regression test in TC-E2E-07". TC-E2E-07 is actually
`test_escape_quote_prefixes_<\r>` (carriage-return sentinel),
not a hyperlink+escape test. Either add a dedicated test (TC-E2E-16
hyperlink-defang) or delete the cross-reference and rephrase as
"locked behaviour, documented but not separately tested".

#### m2. Prefer Python-import smoke-test over `grep -n "<symbol>"` for `__all__` exports

**Sections affected:** 011-01 line 105, 011-06 lines 167-171.

These beads use `grep -n` to assert symbol presence. 011-02 line 139
already uses `python3 -c "from xlsx_read import TooManyMerges"`
which is more robust. Not blocking; future-proofing recommendation.

#### m3. PLAN.md §6 dependency graph diagram + per-task `Dependencies` consistency

The PLAN.md §6 ASCII diagram says "Stage 1 (Security axis —
independent, can ship in parallel)"; all 5 task files say
"Dependencies: none". Consistent — just noting that the planner
could parallelise these. Acceptable.

#### m4. PLAN.md §4 row 011-07 vs task file wording drift

PLAN.md §4 says "half-step stub" while
`task-011-07-json-dump-file-output.md:146-153` Pass 1 description
is more detailed ("Splits the path into two branches but keeps v1
semantics inside the file branch"). Cosmetic — either match
wording in both places.

---

## 4. Verification of Review-Request Specific Items

| Criterion | Status |
| --- | --- |
| 1. RTM coverage 1:1 (R1-R10 ex. R6/R7) | ✅ |
| 2. Stub-First section in every task file | ✅ (011-05 collapse justified) |
| 3. Atomicity 2-4 h | 🟡 M1 (011-08 reports L ~6 h) |
| 4. Relative paths only | ✅ (zero absolute paths) |
| 5. Test verification per task with TC IDs | ✅ |
| 6. Dependency ordering 011-06 → 07 → 08 + fixture-timing wording | ✅ |
| 7. Acceptance binarity | ✅ |
| 8. Cross-skill 12-line `diff -q` gate | 🟡 M2 (7/8 reference it) |
| 9. KNOWN_ISSUES.md handling | ✅ |
| 10. `xlsx-8c-multi-sheet-stream` backlog stub creation | ✅ |

---

## 5. Final Recommendation

**APPROVED WITH COMMENTS.** The plan is structurally sound and
ready to enter the Development phase. The two MAJOR comments
(M1 atomicity sizing for 011-08; M2 missing diff-q line in 011-05
AC) are **not blocking** and can be addressed by the developer
during Pass 1 of the relevant beads, or by a thin planner
revision before development starts.

No critical issues. The RTM↔plan↔task triangulation is tight;
Stub-First methodology is consistently applied; relative paths
and binary acceptance criteria are in order; the v3
reviewer-corrected wording on the 011-06 → 07/08 fixture-timing
prerequisite is faithfully carried.

```json
{"has_critical_issues": false}
```

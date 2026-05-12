# Plan Review — TASK 010 (xlsx-8 read-back CLIs)

**Date:** 2026-05-12
**Reviewer:** Plan Reviewer (self-review per VDD verification loop)
**Status:** APPROVED — no critical issues

---

## 1. General Assessment

The plan decomposes TASK 010 into **8 atomic sub-tasks** (010-01..010-08)
under Stub-First. Phasing is canonical:
- Stage 1 (one task) = package skeleton + exception catalogue +
  smoke E2E.
- Stage 2 (five tasks) = logic per F-region (cross-cutting → CLI →
  dispatch → JSON-emit → CSV-emit). Emit tasks 010-05 / 010-06 are
  parallelisable (§6).
- Stage 3 (two tasks) = round-trip activation + 30 E2E cluster +
  final docs + gates.

Each task file follows `skill-planning-format` task_md_template:
**Use Case Connection** → **Task Goal** → **Changes Description**
(New / Existing / Integration) → **Test Cases** (E2E + Unit +
Regression) → **Acceptance Criteria** → **Notes**. Every task carries
explicit per-task acceptance gates AND the 12-line `diff -q` silent
gate (ARCH §9.4).

Atomicity check: every task targets a single F-region or a single
boundary concern; all within the 2–4 h envelope per planner-prompt
§1. Stub-First compliance is explicit in PLAN.md §4 (matrix) and in
the per-task tags (`[STUB CREATION]` / `[LOGIC IMPLEMENTATION]`).

---

## 2. Use Case Coverage

| Use Case | Covering Tasks | Status |
| --- | --- | --- |
| UC-01 (JSON happy path) | 010-03, 010-04, 010-05, 010-07 (E2E #1) | ✅ |
| UC-02 (CSV stdout) | 010-03, 010-04, 010-06, 010-07 (E2E #7) | ✅ |
| UC-03 (multi-table JSON nested) | 010-04, 010-05, 010-07 (E2E #10–14) | ✅ |
| UC-04 (multi-table CSV subdir) | 010-04, 010-06, 010-07 (E2E #15–17) | ✅ |
| UC-05 (multi-row header) | 010-03, 010-04, 010-05, 010-07 (E2E #18–21) | ✅ |
| UC-06 (hyperlinks) | 010-04, 010-05, 010-06, 010-07 (E2E #22–23) | ✅ |
| UC-07 (encrypted) | 010-02, 010-07 (E2E #24) | ✅ |
| UC-08 (same-path) | 010-02, 010-07 (E2E #25) | ✅ |
| UC-09 (json-errors envelope) | 010-02, 010-07 (E2E #26) | ✅ |
| UC-10 (round-trip) | 010-07 (E2E #27 + xlsx-2 `TestRoundTripXlsx8` live) | ✅ |

**Result:** 10/10 use cases covered.

---

## 3. RTM Coverage (Epic → Issue → Owner Task)

| RTM Issue | Owner Task(s) | Bead count |
| --- | --- | --- |
| R1 | 010-01 | 4 |
| R2 | 010-01, 010-02, 010-03 | 3 |
| R3 | 010-01 | 3 |
| R4 | 010-02, 010-03 | 4 |
| R5 | 010-03, 010-04 | 3 |
| R6 | 010-03, 010-07 | 2 |
| R7 | 010-02, 010-03, 010-04, 010-05 | 4 |
| R8 | 010-03, 010-04 | 1 |
| R9 | 010-03, 010-04 | 3 |
| R10 | 010-03, 010-04, 010-05, 010-06 | 4 |
| R11 | 010-04, 010-05 | 2 |
| R12 | 010-02, 010-03, 010-06 | 5 |
| R13 | 010-07 | 3 |
| R14 | 010-02 | 1 |
| R15 | 010-02 | 1 |
| R16 | 010-02, 010-03 | 3 |
| R17 | 010-02 | 2 |
| R18 | 010-07, 010-08 | 3 |
| R19 | 010-01..010-08 (distributed) | 3 |
| R20 | 010-02, 010-07 | 3 |

**Result:** 20/20 issues covered, 61 Beads total. PLAN.md §2 holds
the full Chainlink decomposition (Epic → Issue → Bead with Owner Task).

---

## 4. Stub-First Compliance Verification

| Task | Tag | Stub Gate | Logic Gate |
| --- | --- | --- | --- |
| 010-01 | `[STUB CREATION]` | Smoke E2E asserts `-999` sentinel + 12 module skeleton files + `__all__` lock | n/a |
| 010-02 | `[LOGIC IMPL]` | (sentinel `-999`) | Envelope helpers live; sentinel bumped `-998` |
| 010-03 | `[LOGIC IMPL]` | (sentinel `-998`) | Full argparse + dispatch trampoline; sentinel bumped `-997` |
| 010-04 | `[LOGIC IMPL]` | (sentinel `-997`) | `iter_table_payloads` live; emit stubs still `-997` |
| 010-05 | `[LOGIC IMPL]` | (sentinel `-997`) | `emit_json` returns 0 on success |
| 010-06 | `[LOGIC IMPL]` | (sentinel `-997`) | `emit_csv` returns 0 on success |
| 010-07 | `[LOGIC IMPL]` | (per-task stubs) | 30 E2E + round-trip live + post-validate hook |
| 010-08 | `[LOGIC IMPL]` | (per-task stubs) | Docs + 5 release gates green |

**Per `tdd-stub-first §2`:** every task either creates stubs (010-01)
OR updates the smoke test from previous task's sentinel to the new
sentinel / real behaviour. ✓

---

## 5. Task Description Depth Check

Spot-checked each of the 8 task files for:
- ✅ Exact file paths under `skills/xlsx/scripts/xlsx2csv2json/`.
- ✅ Exact function signatures (e.g.
  `_resolve_paths(input_arg, output_arg, output_dir_arg) -> tuple[...]`).
- ✅ Exact test case names with TC-UNIT-NN numbering.
- ✅ Acceptance criteria checkbox list.
- ✅ Cross-skill replication gate (12-line `diff -q`) per task.

---

## 6. Comments

### 🔴 Critical (BLOCKING)

— None.

### 🟡 Major

— None.

### 🟢 Minor

#### m1 — `[ID]`-prefix on §1 task bullets vs §2 Chainlink

**Section:** PLAN.md §1 vs §2.
**Observation:** Per `06_planner_prompt §4 Step 2`, "Checklist items
MUST start with the RTM ID (e.g., `[R1] Implement recurring logic`)."
The literal interpretation requires every PLAN.md bullet to be
`[R*] ...`. However:
- The plan splits this concern: **§1 Task Execution Sequence** is
  task-oriented (one bullet per atomic task, with RTM IDs listed in
  the `RTM:` subline); **§2 Chainlink** is RTM-oriented (one entry
  per R*, with Beads listed inside, each mapping to its Owner Task).
- The precedent plan-009 (xlsx-10.A, merged) uses the same split.
- All 20 RTM IDs are reachable through both views (§3 above
  verifies the §2 mapping).

**Decision:** ACCEPT the split. The strict letter would force
one-bullet-per-RTM in §1, which would either explode it to 20
bullets (one per R*) OR fragment by atomic task — the latter wins
on readability and matches the merged precedent.

#### m2 — `skill-tdd-strict` not invoked

**Observation:** The checklist asks whether `skill-tdd-strict` is
specified for critical components/bugs.
**Decision:** Not applicable — this is a new emit-only feature on
top of a frozen foundation (xlsx-10.A `xlsx_read/`), not a bug fix
or quality-hardening pass. Per `skill-tdd-strict` SKILL.md description
("Use when high-assurance reliability is required (Bug fixes, Critical
Features, Quality Hardening)"), the standard `skill-tdd-stub-first`
discipline is the right call. ACCEPT.

---

## 7. Final Decision

**APPROVED.** No critical or major issues. The two minor observations
are documented and accepted with rationale. Proceed to Development
phase (`/develop-all` or per-task `/develop`).

---

**Return payload:**
```json
{
  "review_file": "docs/reviews/plan-010-review.md",
  "has_critical_issues": false
}
```

# Plan Review — TASK 013 / `pdf-12` (PDF → Markdown guidance + `pdf_extract.py`)

- **Date:** 2026-05-21
- **Reviewer:** Plan-Reviewer Agent (VDD pipeline, prompt 07 / `plan-review-checklist`)
- **Artifacts reviewed:** `docs/PLAN.md`; `docs/tasks/task-013-{01..06}-*.md`
- **Verified against:** `docs/TASK.md` (RTM R1–R13, UC-1..3); `docs/ARCHITECTURE.md` (§4 data model, §5.4 signatures, §5.2 exit codes, §11 atomic-chain skeleton)
- **Status:** ✅ **APPROVED WITH COMMENTS** — 0 CRITICAL, 2 MAJOR, 3 MINOR. The Planning→Execution gate is **OPEN**.

## 1. Use Case Coverage

| Use Case | Tasks | Verdict |
|----------|-------|---------|
| **UC-1** — digital PDF → Markdown (main + A1/A2/A3) | 013-01 (smoke), 013-02 (dump core), 013-04 (CLI exit 0), 013-05 (reference recipe + pitfalls) | Covered. A1–A3 are agent-judgement remediations, routed to the reference (013-05) + the raw dump (013-02); `--layout` (A3) in 013-02. |
| **UC-2** — scanned PDF → loud signal (main + A1/A2/A3) | 013-01 (smoke), 013-03 (classifier: truth-table TC-UNIT-13..20), 013-04 (exit 10, A1 envelope, partial-scan warning) | Covered. A2 → TC-UNIT-16; A3 → TC-UNIT-18 + blank-page guard; A1 → TC-E2E-07. |
| **UC-3** — maintainer validation (main + A1) | 013-01 (test scaffold), 013-04 (full E2E green), 013-06 (`validate_skill.py`, `test_e2e.sh`, `diff -q`) | Covered. A1 fix-and-rerun loop noted in 013-06. |

No missing Use Case or Alternative Scenario.

## 2. RTM Coverage (R1–R13)

PLAN.md §2 is a proper traceability matrix — one `[Rn]`-prefixed checklist item
per RTM ID. R1–R4→013-05; R5→013-06+013-05; R6→013-02; R7→013-02/03/04;
R8→013-03; R9→013-04; R10→013-01; R11→013-01; R12→013-01+013-02/03/04+013-06;
R13→013-06. **No orphan requirement.**

## 3. Structure & Stub-First Verification

- **Stub-First — PASS.** Exactly one `[STUB CREATION]` task (013-01); three
  `[LOGIC IMPLEMENTATION]` tasks each replace one function-cluster and
  explicitly upgrade the E2E from stub- to real-assertions per
  `tdd-stub-first §2.4`. Frozen-surface contract prevents renames.
- **Phasing — PASS.** Structure → Logic → Doc → Integration, matches ARCH §11.
- **Dependencies — PASS.** `013-01→02→03→04→06`; `013-05` parallel-eligible
  (pure documentation, sound).
- **Completeness — PASS.** All 6 task files exist with concrete paths,
  signatures, test cases, acceptance criteria.
- **ARCH consistency — PASS.** §5.4 signatures, §4.3 rule + truth table, §5.2
  exit codes reproduced without drift. `report_error` kwargs cross-checked
  against the real `_errors.py`. No hallucinated detail.

## 4. Comments

### 🔴 CRITICAL — none

### 🟡 MAJOR

- **MAJOR-1 — 013-02/03/04 `> RTM:` headers understate their R12 share.**
  PLAN.md §2 says R12 is partly satisfied by these tasks turning the E2E green,
  but the task-file `> RTM:` lines list only R6/R7/R8/R9. A developer reading
  only the task file could treat the E2E upgrade as optional.
  *Fix:* append `; advances [R12] (E2E green per tdd-stub-first §2.4)` to the
  `> RTM:` line of 013-02, 013-03, 013-04.
- **MAJOR-2 — TC-UNIT-23 (013-04) has a self-acknowledged hole.** It claims to
  assert the `0/1/2/10` matrix but parenthetically excludes the `2` path; a
  direct `main([])` raises `SystemExit(2)` rather than returning 2.
  *Fix:* reword TC-UNIT-23 to assert `main` returns `0/1/10` directly and note
  the `2`/`UsageError` path is exercised by TC-E2E-11.

### 🟢 MINOR

- **MINOR-1** — 013-01 §Test Cases wording "ONE smoke E2E class + the unit
  cluster below" vs AC "All 6 unit tests + the smoke E2E" — clarify to
  "the 6-test unit cluster".
- **MINOR-2** — 013-05 `## Use Case Connection` could name UC-1/A1 (the
  inline-tuning path) explicitly.
- **MINOR-3** — the interim `pdf-12` → "🔄 PLANNED" backlog edit (PLAN §0.5/§5)
  is an orchestrator action owned by no task file; flagged so it is not dropped.

## 5. Final Decision

**APPROVED WITH COMMENTS.** The Planning→Execution gate is **OPEN**. The two
MAJOR items are documentation-accuracy defects, not structural defects — they
do not block development. The MINORs are optional polish.

```json
{"review_file": "docs/reviews/plan-013-review.md", "has_critical_issues": false}
```

---

## Resolution (Planner v2 — 2026-05-21)

Applied before closing the `/vdd-plan` phase:

- **MAJOR-1** → `> RTM:` line of `task-013-02/03/04` now appends
  `; advances [R12] (E2E green per tdd-stub-first §2.4)`.
- **MAJOR-2** → `task-013-04` TC-UNIT-23 reworded: asserts `main` returns
  `0/1/10` directly; the `2`/`UsageError` path is exercised by TC-E2E-11.
- **MINOR-1** → `task-013-01` wording clarified to "the 6-test unit cluster".
- **MINOR-2** → `task-013-05` `## Use Case Connection` now names UC-1/A1.
- **MINOR-3** → acknowledged: the interim `pdf-12` → "🔄 PLANNED — TASK 013"
  backlog status edit is performed by the orchestrator at the close of this
  `/vdd-plan` run; 013-06 flips it to ✅ DONE at merge.

Status after resolution: **APPROVED, all comments resolved** — ready for
`/vdd-develop` / `/vdd-develop-all`.

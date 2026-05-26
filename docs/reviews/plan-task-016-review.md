# Plan Review — TASK 016 (wiki-ingest cross-course promotion / demotion)

**Date**: 2026-05-26
**Reviewer**: plan-reviewer (subagent, VDD plan phase)
**Target**: [`docs/PLAN.md`](../PLAN.md) + 11 task files [`docs/tasks/task-016-00-vault-discovery-helpers.md`](../tasks/task-016-00-vault-discovery-helpers.md) through [`docs/tasks/task-016-10-e2e-docs-validators.md`](../tasks/task-016-10-e2e-docs-validators.md)
**Inputs reviewed**: TASK.md (R1..R13, UC-1..UC-5), ARCHITECTURE.md §3.2 + §11 + §13, both prior reviews (task-016, architecture-task-016), `.agent/skills/plan-review-checklist`, `.agent/skills/tdd-stub-first`, `.agent/skills/skill-planning-format`, `skills/wiki-ingest/scripts/tests/test_architecture.py`.
**Status**: **APPROVED WITH COMMENTS** — non-blocking. Plan is implementable as written; 2 MAJOR items are LoC-budget reconciliations, 8 MINOR are tightening nits, no CRITICAL items.

---

## General Assessment

The plan is high quality. It decomposes faithfully into 11 atomic beads (016.00..016.10), each independently revertable. The architect's 4 MAJOR items (A-M-1..A-M-4) are all addressed concretely:

- **A-M-1** (bead ordering): lint extensions moved from architect's slot 7 to slot 5 (016.04), lands BEFORE the first state-mutating bead (016.06 `promote --apply`). PLAN §1 documents the move; §6 gate 4 makes the assertion universal post-016.04; every downstream bead's task file carries the `lint <fixture> reports zero invariant_violation` acceptance criterion. **Verified**.
- **A-M-2** (`Lessons/` not hardcoded): contracts use `course_root.relative_to(vault_root)` in 016.04, 016.06, 016.07, 016.08, 016.09; non-`Lessons/` adversarial test cases present throughout. **Verified**.
- **A-M-3** (splice helper as own bead): 016.02 is discrete and lands before 016.06. **Verified**.
- **A-M-4** (`discover_courses` symlink + nested): 016.00 algorithm includes `followlinks=False`, nested-schema descent, filesystem-boundary check, sorted return. 10 unit tests cover the cases. **Verified**.

Open Questions (Q-1..Q-10) are resolved in PLAN §0 and threaded into task files. Honest-scope (R13) honoured uniformly — no bead introduces auto-promotion, semantic identity, root `log.md`, custom kinds, file-watch, full-path link normalisation, or configurable threshold. Stub-First adherence: `promote` is split (016.05 stub / 016.06 apply); `demote` is single-bead with documented rationale; helper beads follow Test-First + Move.

---

## RTM & UC Coverage Audit

| RTM | PLAN §5 claim | Verified |
|-----|---------------|----------|
| R1  | 016.00 | ✓ |
| R2  | 016.03 | ✓ |
| R3  | 016.05 preconditions; 016.06 logic | ✓ |
| R4  | 016.05 dry-run; 016.06 apply / idempotency | ✓ |
| R5  | 016.07 | ✓ (R5.1..R5.8 all addressed) |
| R6  | 016.04 | ✓ (R6.1, R6.2, R6.3, R6.4 each have TCs) |
| R7  | 016.08 | ✓ (R7.1..R7.4 each have TCs) |
| R8  | 016.09 | ✓ (R8.1..R8.5 each have explicit TCs incl. no-auto-promote) |
| R9  | 016.00 + 016.03 + 016.05..07 | ✓ |
| R10 | 016.00..016.10 | ✓ |
| R11 | 016.10 | ✓ |
| R12 | 016.10 | ✓ |
| R13 | absence of non-goal beads | ✓ |

| UC | Tasks | Verified |
|----|-------|----------|
| UC-1 | 00, 01, 02, 03, 04, 05, 06, 10 | ✓ |
| UC-2 | 00, 04, 07, 10 | ✓ |
| UC-3 | 00, 03, 04, 10 | ✓ |
| UC-4 | 00, 01, 06, 09, 10 | ✓ |
| UC-5 | 00, 03, 06, 08, 10 | ✓ |

All RTM rows and Use Cases trace to ≥1 bead. No orphans.

---

## Comments

### 🔴 CRITICAL — none

### 🟡 MAJOR (2)

**M-1 — `_page_merge.py` LoC budget mismatch.**

*Location*: [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) §3.2 row `wiki_ingest/_page_merge.py` states ≤150 LoC. [`docs/tasks/task-016-01-page-merge-extraction.md`](../tasks/task-016-01-page-merge-extraction.md) line 20 + Acceptance criterion say ≤250.

These contradict. ARCHITECTURE.md is the source of truth. A developer following the task file ships a 220-LoC module that the architecture-compliance reviewer rejects.

**Fix**: align both to a single number (recommend ≤200 — the four primitives + imports + docstring are ~120–160 LoC; reserve some headroom).

---

**M-2 — `upsert_page.py` LoC budget mismatch.**

*Location*: [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) §3.2 row `commands/upsert_page.py (extended)` says ≤250. [`docs/tasks/task-016-09-upsert-root-aware.md`](../tasks/task-016-09-upsert-root-aware.md) says ≤300 with arithmetic "current ~217 + ~50 LoC of root-aware branching" = ~267.

The arithmetic is wrong: 016.01 EXTRACTS the four merge primitives (~60 LoC), shrinking the baseline. Post-016.01 baseline is ~157 LoC; +50 LoC root-aware ≈ 207 LoC, which fits ≤250 comfortably.

**Fix**: re-do LoC accounting in 016.09's task file and align acceptance criterion to ≤250 (matching architecture).

---

### 🟢 MINOR (8)

**m-1 — PLAN.md §8 dependency diagram first line is misleading shorthand.** It shows `016.00 → 016.04 → 016.05 → 016.06 → 016.10` skipping 016.07/08/09 (the real intermediate beads). The second block is correct. Fix: replace the first line with `016.00 → 016.04 → 016.05 → 016.06 → {07, 08, 09} → 016.10`.

**m-2 — 016.04's dependency on 016.03 should be re-explained in §"Notes".** The PLAN line "016.03 (root scaffold required for `invariant_violation` test fixture)" is correct but the task file doesn't restate it. Add a one-liner.

**m-3 — 016.06 inline row-add helper creates known duplication with 016.07.** Acceptable for v1; the duplication should be visible to the code reviewer. Add to 016.07 acceptance criterion: "If inline row-management exceeds 40 LoC duplication across `promote.py` + `demote.py`, add a TODO comment in both files referencing a follow-up task."

**m-4 — 016.05 `--apply` stub uses `die(code=4)` — not in v1 vocabulary.** Pick code=2 (configuration-error class) or code=3 explicitly documented. Cheap fix.

**m-5 — 016.09 TC-UNIT-016-09-04's expected footnote is bound to `Lessons/Course C` literal.** Make the test compute the expected string from `course_root.relative_to(vault_root)`, not literal — consistent with the A-M-2 contract.

**m-6 — 016.07 `DemotionPlan` envelope should explicitly cite ARCHITECTURE §4.5.3 shape.** Tiny cross-link addition.

**m-7 — 016.10's `freezegun`-style date pinning would be a new test dep.** TASK §0 says "no new runtime dependency." Commit to the disjunct already mentioned: post-process the date pattern (regex `\[\d{4}-\d{2}-\d{2}\]` → `[YYYY-MM-DD]` before diff). State this in acceptance criteria.

**m-8 — 016.09's `:shared` suffix on `--touched` is a new CLI grammar — needs SKILL.md mention.** 016.10's SKILL.md update list enumerates `promote` + `demote` rows; add the `append-log :shared` suffix to the doc list.

---

## Cross-Cutting Gate Audit (PLAN §6)

| Gate | Universal? |
|------|-----------|
| 1. Per-bead unit tests green | ✓ |
| 2. `tests/test_architecture.py` green | ✓ |
| 3. `tests/test_r11_byte_identity.py` green | ✓ |
| 4. Post-016.04 lint clean | ✓ |
| 5. 016.10 only: validate_skill + skill-validator + diff -q | ✓ |

Gate coverage is uniform. No bead silently drops a gate.

---

## Honest-Scope Check (R13)

| R13 item | Plan honoured? | Where verified |
|----------|----------------|---------------|
| No auto-promotion | ✓ | 016.09 TC-UNIT-016-09-03 explicit lock |
| No semantic identity | ✓ | 016.06 Q-10 literal-line-diff only |
| No root `log.md` | ✓ | 016.03 step 5 explicit "Do NOT create" |
| No source-slug cross-vault collision detection | ✓ | 016.10 ref doc carries R13.3 honest-scope note |
| No custom page kinds | ✓ | 016.10 ref doc lists as v3+ |
| No file-watch | ✓ | No bead introduces it |
| No bidirectional full-path link normalisation | ✓ | 016.08 §Notes "Q-7 honest-scope: full-path links LEFT ALONE" |
| No configurable threshold | ✓ | No bead introduces configurability |

No bead silently re-introduces an R13 non-goal.

---

## Final Recommendation

**APPROVED WITH COMMENTS — proceed to Development phase.**

The two MAJOR items (M-1, M-2) are LoC-budget reconciliations resolvable in ~10 minutes of editing. The 8 MINOR items are tightening nits the developer can address inline.

Stub-First discipline is honoured. A-M-1..A-M-4 are universally honoured. The Development phase can begin with 016.00 as the first bead.

```json
{
  "review_file": "docs/reviews/plan-task-016-review.md",
  "has_critical_issues": false
}
```

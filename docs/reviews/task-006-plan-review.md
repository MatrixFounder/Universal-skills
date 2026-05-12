# Task-006 (docx-6 / `docx_replace.py`) — Plan Review Round 1

**Reviewer:** `plan-reviewer` subagent (read-only).
**Subject:** `docs/PLAN.md` (DRAFT v1) + 10 `docs/tasks/task-006-NN-*.md` files (written by `planner` subagent).
**Date:** 2026-05-11.
**Verdict:** **CHANGES_REQUESTED**. No CRIT findings; 3 MAJ + 3 MIN + 2 NIT items requested for inline polish before Development phase.
**Verdict JSON:** `{"has_critical_issues": false}`.

---

## Findings & fixes applied

| Sev | ID | Site | Issue | Fix landed |
|-----|----|------|-------|------------|
| MAJ | M1 | `docs/PLAN.md` RTM Coverage Matrix (R11 row) + missing closure in any task file | TASK §5 row R11 enumerates R11.a–R11.e; R11.e ("canary saboteur tests if applicable — docx-1 had none"). PLAN's RTM Coverage Matrix lists R11.a–R11.d only — R11.e unaccounted. | PLAN R11 row updated: explicit `R11.e — N/A (docx-1 had none; declared not applicable in 006-01b)`. 006-01b Notes gains a "Plan-review MAJ-1 closure — R11.e N/A" paragraph closing the row as N/A. RTM Coverage Matrix G2 gate also notes "(R11.e is N/A — declared in 006-01b)". |
| MAJ | M2 | `docs/tasks/task-006-01b-test-scaffolding.md` unit-test stubs (≈ line 32, 155) + E2E `echo SKIP T-<name>` markers (≈ line 186) | Pure `unittest.skip(...)` / `SkipTest` = 0 failures = false-green; Stub-First Red state invisible to CI. Violates Stub-First-Red-Green-Refactor methodology. | (a) Unit-test stubs converted to `self.fail("docx-6 stub — to be implemented in task-006-NN")` where `NN` names the downstream Phase-2 sub-task that turns it green. Per-class downstream mapping pinned in 006-01b skeleton. (b) E2E stubs gated behind `DOCX6_STUBS_ENABLED` env flag: default unset/0 → `echo SKIP` (CI stays exit-0); `DOCX6_STUBS_ENABLED=1` → `run_expect_fail` (case run, expect rc=stub-rc; flips to expected real rc as each region lands). (c) PLAN.md "Phase-Boundary Gates" gains a new §6 "Stub-First Red-state gate (MAJ-2 lock)" documenting the convention; CI red bar SHRINKS monotonically as Phase-2 tasks land. |
| MAJ | M3 | `docs/tasks/task-006-05-insert-after-action.md` unit test `test_extract_insert_paragraphs_warns_on_relationship_refs` (≈ line 263) | Test only asserts warning shape + paragraph still in returned list — does NOT assert "no live `r:embed` survives" per TASK R10.b (post-M3 rewording). Could miss a bug where the warning fires AND a live r:embed leaks through. | (Option A — preferred — applied.) Test extended to **three** assertions: (1) stderr warning shape matches ARCH §8 format; (2) paragraph survives in the returned list (warn-and-proceed Alt-6); (3) **R10.b survival check** — walk paragraph tree for `r:embed` attributes; assert either no live embeds OR all surviving embeds point at relationships absent from base doc's `document.xml.rels`. Cross-reference note added: full E2E regression lock for R10.b still lives in 006-08; unit-level check here pins function-boundary behaviour. |
| MIN | m1 | `docs/tasks/task-006-07-cli-and-post-validate.md` size + admission "LARGEST task in the chain" | Single task encompassing F7 full `_run` + F8 post-validate + UC-4 library mode (conditional) > 8 h work; conditional landing of UC-4 muddies the LOC-gate trigger. | Task **split** into **006-07a (mandatory F7+F8)** + **006-07b (conditional UC-4 library mode)**. Old `task-006-07-cli-and-post-validate.md` removed; replaced by `task-006-07a-cli-and-post-validate.md` (zip-mode pipeline + post-validate; soft 560 LOC ceiling) and `task-006-07b-unpacked-dir.md` (library mode with explicit pre-flight LOC check + deferral path to `docx-6.4` backlog row). Chain now has **11 sub-tasks** instead of 10; PLAN.md D5 closure, RTM matrix, UC coverage, Open-Question trail, and Acceptance Gates table all updated to reference 006-07a/07b. |
| MIN | m2 | `docs/PLAN.md` "Phase-Boundary Gates" §2 wording "after every commit" | Impractical at every commit; Task-005 precedent ran gates per-task boundary. Cadence mismatch. | PLAN.md "Phase-Boundary Gates" §2 reworded: "at each task boundary (i.e. after each `task-006-NN` lands and before the next begins — MIN-2 fix; NOT per-commit which would be impractical)". Mirrors Task-005 precedent cadence explicitly. |
| MIN | m3 | `docs/tasks/task-006-08-honest-scope-locks.md` Notes (≈ line 183) | Permits hand-crafted Q-U1 fixture with `<w:ins>` / `<w:del>` markup; violates TASK R11.d "fixtures derived from `md2docx.js` (no manually-crafted OOXML)". | Hand-crafted-OOXML deviation REJECTED. Replaced with a one-shot LibreOffice round-trip helper at `skills/docx/scripts/tests/build_tracked_change_fixture.py` (≈ 50-80 LOC, NOT in production paths; invoked at fixture-build time, output committed). Pipeline: md2docx baseline → headless soffice with RecordChanges → save with `<w:ins>`/`<w:del>` markup. Q-U1-build escalation path added to PLAN.md Open-Question Closure Trail: if LO automation proves impractical → escalate to Plan-Review round 2 (Word COM, or documented R11.d waiver). Do NOT silently hand-craft OOXML. |
| NIT | n1 | `docs/PLAN.md` RTM Matrix R6 row | R6.a description listed `_replace_in_run` as extracted from `docx_add_comment.py`; that helper is NEW (R6.d), not extracted. | RTM Matrix R6 row rewritten: explicitly attribute R6.a/b/c (extract `_is_simple_text_run` / `_rpr_key` / `_merge_adjacent_runs` + refactor; byte-identical) to 006-01a, and R6.d/e (new helpers `_replace_in_run` / `_concat_paragraph_text` / `_find_paragraphs_containing_anchor`) to 006-02. |
| NIT | n2 | `docs/PLAN.md` "eleven (actual 12)" narrative noise at lines 69, 294, 298, 423 | Acceptable per arch-review NIT-1 decision; cosmetic. | Left as-is (consistent with ARCH §9 reconciliation note; 006-09 DoD enumerates all 12 invocations explicitly to close NIT n1 from task-006-review). |

---

## Resulting PLAN.md status

**DRAFT v2** — Round-1 plan-review CHANGES_REQUESTED; MAJ-1/2/3 + MIN-1/2/3 fixes applied; NIT-1 fixed; NIT-2 left as-is.

The chain now has **11 sub-tasks** (MIN-1 split):
- 006-01a (anchor extraction, byte-identical refactor, all-green)
- 006-01b (test scaffolding, Stub-First Red state via `self.fail()` + `DOCX6_STUBS_ENABLED`)
- 006-02 (new anchor helpers + green helper unit tests)
- 006-03 (cross-cutting pre-flight + CLI skeleton)
- 006-04 (part walker + `--replace` action)
- 006-05 (`--insert-after` action with R10.b survival check)
- 006-06 (`--delete-paragraph` action)
- 006-07a (CLI full wiring + post-validate hook — MANDATORY)
- 006-07b (`--unpacked-dir` library mode — CONDITIONAL MVP=No)
- 006-08 (honest-scope regression locks + Q-U1 LO round-trip fixture + A4 TOCTOU)
- 006-09 (final docs + backlog ✅ DONE + 12 `diff -q` DoD)

Development phase unblocked. **Round-2 plan-review APPROVED WITH COMMENTS** — 0 CRIT / 0 MAJ / 2 MIN (cosmetic stale strings) / 1 NIT (cosmetic). Round-2 findings:

| Sev | ID | Site | Issue | Fix landed |
|-----|----|------|-------|------------|
| MIN | r2-m1 | `docs/PLAN.md:468` | Stale "DRAFT v1" footer despite header (line 3) reading "DRAFT v2". | Footer rewritten to "DRAFT v2 — Round-2 plan-review APPROVED; MAJ-1/2/3 + MIN-1/2/3 from Round 1 applied; Round-2 cosmetic MIN-1/MIN-2/NIT-1 absorbed." |
| MIN | r2-m2 | `docs/tasks/task-006-09-final-docs-and-backlog.md:50` | "10 sub-task IDs (006-01a → 006-09)" — stale count after MIN-1 split. | Updated to "11 sub-task IDs (006-01a, 006-01b, 006-02, 006-03, 006-04, 006-05, 006-06, 006-07a, 006-07b, 006-08, 006-09)". |
| NIT | r2-n1 | `docs/tasks/task-006-04-replace-action.md:184` | Inline code comment `# post-validate hook landing in 006-07` (should be `006-07a`). | Changed to `006-07a`. |

Round-2 verdict JSON: `{"has_critical_issues": false}` — **APPROVED to proceed to Execution phase**.

## Trace

- Round-1 review timestamp: 2026-05-11 (during `/vdd-start-feature` workflow).
- Round-1 reviewer agent id (transient): provided in the orchestrator feedback transcript.
- Planner (round-1 author) agent id: this session.
- Planner-side fixes: this file's "Fix landed" column documents the exact edits applied to `docs/PLAN.md` and `docs/tasks/task-006-NN-*.md`.

---

**End of `task-006-plan-review.md` — Round 1 CHANGES_REQUESTED → fixes applied → Round 2 APPROVED WITH COMMENTS → 3 cosmetic hot-fixes landed → PLAN.md DRAFT v2 ready for Development phase.**

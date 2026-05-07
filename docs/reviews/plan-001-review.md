# Plan Review — `docs/PLAN.md` (xlsx-6)

**Date:** 2026-05-07
**Reviewer:** plan-reviewer agent (subagent)
**Status:** **APPROVED WITH COMMENTS** — fix Major J-1..J-4 inline before Development; no re-planning round required.

## General Assessment

The plan correctly splits work into Stage-1 (5 stub tasks) + Stage-2 (10 logic tasks) per Stub-First, with a clean RTM-to-task mapping and explicit phase boundaries. Architecture-review M-1 (idmap-as-list), M-2 (DuplicateThreadedComment + 4-row matrix) and M-3 (A-Q1/A-Q2 absent as open questions) are faithfully absorbed. Minor m-1, m-3, m-4, m-5 routed correctly. Atomicity excellent — every Stage-2 task is 2–4 h with concrete file paths/signatures/verification commands. Two main gaps: (a) Stage-1 tasks lack the `No edits to skills/docx/scripts/office/` AC; (b) TASK round-1 m7 ("backlog use-case quoted in §1") not visibly absorbed.

## Critical Issues
*(none)*

## Major Issues

### J-1 — Stage-1 tasks missing `No edits to skills/docx/scripts/office/` AC
All five Stage-2 logic tasks (2.01–2.10) carry this AC; Stage-1 tasks 1.01–1.05 do not. Task 1.04 in particular touches `office_passwd.py` (creating `encrypted.xlsx`) and `office/validate.py` — without explicit guard, fixture-generation helpers could land inside `office/` and trigger the 4-skill replication burden. **Fix:** add the AC line to all five Stage-1 task files.

### J-2 — TASK round-1 m7 (backlog use-case quoted in §1) not absorbed
Searched all 15 task files; no instruction to embed the backlog xlsx-6 use-case verbatim as the opening of `references/comments-and-threads.md` §1. **Fix:** add AC to 1.05 — `[ ] §1 stub of references/comments-and-threads.md quotes the backlog xlsx-6 use-case verbatim (TASK round-1 m7 lock)`.

### J-3 — Stage-1 Red→Green wording is fuzzy (skipTest vs green-on-stubs)
`tdd-stub-first` allows both, and the plan correctly uses `skipTest` for unit tests + green-on-input-copy for E2E, but the Phase-boundary wording in PLAN.md line 136 conflates them. **Fix (optional):** tighten to *"unit tests are SKIPPED at end-of-Stage-1 and become real assertions one-by-one in their owning Stage-2 task; E2E tests pass on the input-copy stub and gain real assertions in their owning Stage-2 task."*

### J-4 — `OutputIntegrityFailure` envelope (added in 2.08) not in TASK §2.5 exit-code table
2.10's doc-cleanup currently only mentions adding `DuplicateThreadedComment` to the table. **Fix:** add to 2.10 AC — `[ ] Update TASK §2.5 Exit codes table with both DuplicateThreadedComment AND OutputIntegrityFailure under exit 1/2 as appropriate`.

## Minor Issues

- **m-A** (`task-001-09-legacy-write.md` line 61): empty-set `spid` baseline `1025` is reasonable (matches Excel convention) but conflicts with PLAN.md m-1 wording "max+1". One-line clarifying comment in 2.04 + reference doc.
- **m-B** (`task-001-09-legacy-write.md`): no mention that 2.07 will modify `single_cell_main` to insert a merged-cell pre-flight. One-line note: *"merged-cell + duplicate-cell pre-flight is added in 2.07 between steps 2 and 3"*.
- **m-C** (`task-001-15-final-docs.md`): doesn't enumerate WHICH tests get canonical-diff goldens. Add AC: only the 5 named goldens get c14n diff; other E2E rely on exit-code + lxml assertions.
- **m-D** (PLAN.md): `m-1`/`m-3` ID-space collision between architecture-review (hyphen) and TASK round-1 (no hyphen). Add a one-liner key at top of PLAN.md.
- **m-E** (`task-001-04-fixtures.md`): doesn't say what to do if Excel-365 authoring is unavailable. Add fallback note: synthetic openpyxl fixture with deviation flagged in `tests/golden/README.md`.

## RTM coverage table

| RTM | PLAN.md mapping | Stage-2 `[Rx]` tag | Verdict |
|---|---|---|---|
| R1 | 1.01, 2.03, 2.04 | 2.03 `[R1.h + M-1]`, 2.04 `[R1]` | ✅ |
| R2 | 1.01, 2.02 | 2.02 `[R2]` | ✅ |
| R3 | 1.01, 2.05 | 2.05 `[R3]` | ✅ |
| R4 | 1.01, 2.06 | 2.06 `[R4]` | ✅ |
| R5 | 2.07 | 2.07 `[R5][R6]` | ✅ |
| R6 | 2.07 | 2.07 `[R5][R6]` | ✅ |
| R7 | 1.01, 2.01 | 2.01 `[R7]` | ✅ |
| R8 | 2.08 | 2.08 `[R8]` | ✅ |
| R9 | 1.04, 2.09 | 2.09 `[R9]` | ✅ |
| R10 | 1.02, 1.03, 1.05, 2.10 | 2.10 `[R10]` | ✅ |

## Verification of architecture-review absorption

| Item | Verified? |
|---|---|
| M-1 (idmap-as-list, list parser + unit test on `data="1,5,9"`) | ✅ — `task-001-08-scanners.md` lines 23, 65, 76 |
| M-2 (4-row dup matrix + DuplicateThreadedComment envelope) | ✅ — `task-001-12-dup-and-merge.md` lines 42–48, 62 |
| M-3 (A-Q1/A-Q2 locked, not free-standing) | ✅ — only A-Q3 + m-1/m-3/m-4 in PLAN.md "Risks & decisions" |
| m-1 (spid workbook-wide max+1) | ✅ — `task-001-08-scanners.md` lines 8, 82 |
| m-3 (Default Extension="vml" idempotency) | ✅ — `task-001-09-legacy-write.md` lines 38, 84 |
| m-4 (8 MiB stdin cap exact-boundary) | ✅ — `task-001-11-batch.md` lines 22–24, 79 |
| m-5 (c14n vs c14n2) | ✅ — `task-001-15-final-docs.md` lines 39, 128 |
| TASK m1 casefold STRAẞE | ✅ — `task-001-10-threaded-write.md` lines 36, 81 |
| TASK m4 goldens README | ✅ — 1.04 lines 26–55 + 2.09 line 46 |
| TASK m5 case-sensitive dedup | ✅ — 2.04 line 28, 2.05 line 33 |
| TASK m6 SKILL.md §10 row template | ✅ — 1.05 line 78, 2.10 lines 21–22 |
| TASK m7 backlog use-case in §1 | ❌ — see J-2 |

## Final Recommendation

**APPROVED WITH COMMENTS — proceed to Development phase after a 15-minute planner patch pass for J-1..J-4 + optional minors.** No structural revision required.

```json
{ "review_file": "docs/reviews/plan-001-review.md", "has_critical_issues": false, "approved_for_development": true }
```

# Development Plan: xlsx-6 — `xlsx_add_comment.py`

> **TASK:** [`docs/TASK.md`](TASK.md) — Task ID 001, slug `xlsx-add-comment`.
> **ARCHITECTURE:** [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).
> **Reviews:** [`docs/reviews/task-001-review.md`](reviews/task-001-review.md) (round-2 APPROVED) + [`docs/reviews/architecture-001-review.md`](reviews/architecture-001-review.md) (APPROVED WITH COMMENTS) + [`docs/reviews/plan-001-review.md`](reviews/plan-001-review.md) (APPROVED WITH COMMENTS — J-1..J-4 folded into PLAN + task files).
> **Strategy:** Stub-First (per `tdd-stub-first` skill). Phase 1 lays the surface + green-on-stubs E2E (input-copy stub) + skipped unit tests; Phase 2 replaces stubs with real logic, RTM-tagged.

> **ID-space key (m-D plan-review):** `m-N` (with hyphen) = architecture-review minor-N (e.g. `m-1` = spid 1024-stride vs max+1). `mN` (no hyphen) = TASK round-1 minor-N (e.g. `m1` = casefold STRAẞE). Both ID spaces are independent.

## RTM ↔ Task mapping

| RTM | Tasks |
|---|---|
| R1 — Legacy comment insertion | 1.01, 2.03, 2.04 |
| R2 — Cell-syntax (cross-sheet, quoted) | 1.01, 2.02 |
| R3 — Threaded mode + personList | 1.01, 2.05 |
| R4 — Batch mode + xlsx-7 envelope | 1.01, 2.06 |
| R5 — Duplicate-cell semantics | 2.07 |
| R6 — Merged-cell policy | 2.07 |
| R7 — Cross-3/4/5/7-H1 hardening | 1.01, 2.01 |
| R8 — Output integrity + determinism | 2.08 |
| R9 — Honest scope locks | 1.04, 2.09 |
| R10 — Tests + docs | 1.02, 1.03, 1.05, 2.10 |

## Stage 1 — Structure & Stubs (Red → Green on hardcoded stubs)

- **Task 1.01** — Create `xlsx_add_comment.py` skeleton with all CLI flags + helper stubs
  - Use Cases: I1.1, I1.2, I1.3, I1.4, I1.5, I2.1, I2.2, I2.3, I3.1
  - Description File: [`docs/tasks/task-001-01-skeleton.md`](tasks/task-001-01-skeleton.md)
  - Priority: Critical
  - Dependencies: none

- **Task 1.02** — Add E2E test scaffolding to `tests/test_e2e.sh` (16 test cases, red on stubs)
  - Use Cases: ALL E2E ACs from TASK §3
  - Description File: [`docs/tasks/task-001-02-e2e-scaffolding.md`](tasks/task-001-02-e2e-scaffolding.md)
  - Priority: Critical
  - Dependencies: 1.01

- **Task 1.03** — Create `tests/test_xlsx_add_comment.py` unit-test scaffolding
  - Use Cases: I1.1, I1.2, I1.3, I1.4, I1.5, I2.1, I2.3, I4.1
  - Description File: [`docs/tasks/task-001-03-unit-scaffolding.md`](tasks/task-001-03-unit-scaffolding.md)
  - Priority: High
  - Dependencies: 1.01

- **Task 1.04** — Create `tests/golden/` directory + `README.md` + baseline input fixtures
  - Use Cases: R9.d (honest scope — agent-only goldens), I4.1
  - Description File: [`docs/tasks/task-001-04-fixtures.md`](tasks/task-001-04-fixtures.md)
  - Priority: High
  - Dependencies: none (parallel with 1.01)

- **Task 1.05** — SKILL.md updates + `references/comments-and-threads.md` + `examples/comments-batch.json` (doc stubs)
  - Use Cases: I4.2
  - Description File: [`docs/tasks/task-001-05-doc-stubs.md`](tasks/task-001-05-doc-stubs.md)
  - Priority: Medium
  - Dependencies: 1.01

## Stage 2 — Logic Implementation (RTM-tagged, replaces stubs with real code)

- **Task 2.01 [R7]** — Cross-3/4/5/7-H1 hardening (`assert_not_encrypted`, `warn_if_macros_will_be_dropped`, same-path guard, json-errors envelope routing)
  - Use Cases: I3.1
  - Description File: [`docs/tasks/task-001-06-cross-cutting.md`](tasks/task-001-06-cross-cutting.md)
  - Priority: Critical
  - Dependencies: 1.01, 1.02, 1.03

- **Task 2.02 [R2]** — Cell-syntax parser + sheet resolver (first-visible default, case-sensitive lookup, M2/M3)
  - Use Cases: I1.1
  - Description File: [`docs/tasks/task-001-07-cell-parser.md`](tasks/task-001-07-cell-parser.md)
  - Priority: Critical
  - Dependencies: 1.01, 1.03

- **Task 2.03 [R1.h + M-1]** — `<o:idmap data>` (list-aware) + `o:spid` workbook-wide scanners + `next_part_counter`
  - Use Cases: I1.2
  - Description File: [`docs/tasks/task-001-08-scanners.md`](tasks/task-001-08-scanners.md)
  - Priority: Critical
  - Dependencies: 1.01, 1.03

- **Task 2.04 [R1]** — Legacy comment write path (commentsN.xml + vmlDrawingK.xml + sheet rels + Content_Types overrides + `Default Extension="vml"` idempotency m-3)
  - Use Cases: I1.3
  - Description File: [`docs/tasks/task-001-09-legacy-write.md`](tasks/task-001-09-legacy-write.md)
  - Priority: Critical
  - Dependencies: 2.03

- **Task 2.05 [R3]** — Threaded write path (threadedComments<M>.xml + personList.xml on workbook-rels M6 + casefold userId m1 + Q7 fidelity dual-write)
  - Use Cases: I1.4
  - Description File: [`docs/tasks/task-001-10-threaded-write.md`](tasks/task-001-10-threaded-write.md)
  - Priority: Critical
  - Dependencies: 2.04

- **Task 2.06 [R4]** — Batch mode (flat-array + xlsx-7 envelope auto-detect + 8 MiB cap m2 + group-finding skip + batch dedup)
  - Use Cases: I2.1, I2.2, I2.3
  - Description File: [`docs/tasks/task-001-11-batch.md`](tasks/task-001-11-batch.md)
  - Priority: High
  - Dependencies: 2.04, 2.05

- **Task 2.07 [R5][R6]** — Duplicate-cell matrix (ARCHITECTURE §6.1 + new `DuplicateThreadedComment` envelope) + merged-cell resolver
  - Use Cases: I1.5, R5 corollary
  - Description File: [`docs/tasks/task-001-12-dup-and-merge.md`](tasks/task-001-12-dup-and-merge.md)
  - Priority: High
  - Dependencies: 2.04, 2.05

- **Task 2.08 [R8]** — Output integrity hooks (post-pack `office/validate.py` + `xlsx_validate.py --fail-empty`; `.xlsm` macro preservation verification)
  - Use Cases: I3.2
  - Description File: [`docs/tasks/task-001-13-integrity.md`](tasks/task-001-13-integrity.md)
  - Priority: High
  - Dependencies: 2.04, 2.05, 2.06

- **Task 2.09 [R9]** — Honest-scope regression tests (parentId absent, plain-text body, default VML anchor, UUIDv4 non-determinism, --unpacked-dir absent, --default-initials absent)
  - Use Cases: I4.1
  - Description File: [`docs/tasks/task-001-14-honest-scope.md`](tasks/task-001-14-honest-scope.md)
  - Priority: Medium
  - Dependencies: 2.05, 2.06

- **Task 2.10 [R10]** — Doc polish (SKILL.md final, references/comments-and-threads.md final with C1+M-1 pitfalls, examples/comments-batch.json) + `skill-creator/scripts/validate_skill.py skills/xlsx` exit-0 + golden-diff strategy (`c14n` per m-5)
  - Use Cases: I4.2
  - Description File: [`docs/tasks/task-001-15-final-docs.md`](tasks/task-001-15-final-docs.md)
  - Priority: Medium
  - Dependencies: 2.06, 2.07, 2.08, 2.09

## Use Case Coverage

| Use Case | Tasks |
|---|---|
| I1.1 (Cell-syntax parser) | 1.01, 1.03, 2.02 |
| I1.2 (Part-counter resolution) | 1.01, 1.03, 2.03 |
| I1.3 (Legacy write path) | 1.01, 1.02, 2.04 |
| I1.4 (Threaded write path) | 1.01, 1.02, 2.05 |
| I1.5 (Merged-cell resolver) | 1.01, 1.02, 2.07 |
| I2.1 (Batch shape auto-detect) | 1.01, 1.03, 2.06 |
| I2.2 (Envelope-mode field mapping) | 1.01, 1.03, 2.06 |
| I2.3 (Batch dedup & no-collision) | 1.02, 1.03, 2.06 |
| I3.1 (Cross-cutting gates) | 1.01, 1.02, 2.01 |
| I3.2 (Output validates clean) | 1.02, 2.08 |
| I4.1 (Honest-scope regressions) | 1.04, 2.09 |
| I4.2 (Skill docs + reference) | 1.05, 2.10 |

## Phase boundaries / verification gates

- **End of Stage 1 (post-1.05):** all stubs in place; `bash skills/xlsx/scripts/tests/test_e2e.sh` runs and **passes** on the input-copy stub from 1.01 (E2E green-on-stubs); `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests` runs and reports `OK (skipped=N)` — unit tests are SKIPPED at this point (J-3 plan-review clarification: skipTest, not red, per `tdd-stub-first` §1 which permits both). Both flip to real assertions one-by-one inside their owning Stage-2 task.

- **End of each Logic task (2.01..2.10):** the task's owned ACs flip from "asserts hardcoded value" to "asserts real value"; full E2E + unit + regression suites stay green; `office/validate.py` exits 0 on every output produced by the task's ACs.

- **End of Stage 2 (post-2.10):**
  - `bash skills/xlsx/scripts/tests/test_e2e.sh` → all 16 ACs green.
  - `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests` → green.
  - `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` → exit 0.
  - `cd skills/xlsx/scripts && diff -qr office ../../docx/scripts/office` → empty (no accidental edits to shared `office/` module per CLAUDE.md §2).
  - All TASK Acceptance Criteria checked off.

## Risks & decisions deferred to development

- **A-Q3 (PLAN-internal, m-5):** golden-diff strategy = `lxml.etree.tostring(..., method='c14n')` (NOT `c14n2`); ephemeral attributes (`<threadedComment id>` UUIDv4, unpinned `dT`) masked via XPath replace before comparison. **Locked in this PLAN.** Implementation in 2.10.
- **m-1:** `o:spid` allocator = workbook-wide max+1 (NOT Excel's 1024-stride convention). Documented in `references/comments-and-threads.md`. **Locked in this PLAN.** Implementation in 2.03.
- **m-3:** if input has `Default Extension="vml"`, do NOT emit redundant per-part `<Override>` (idempotency refinement). **Locked in this PLAN.** Implementation in 2.04.
- **m-4:** 8 MiB stdin cap: `read(8 * 1024 * 1024 + 1)` then `if len > 8 * 1024 * 1024`. **Locked in this PLAN.** Implementation in 2.06.

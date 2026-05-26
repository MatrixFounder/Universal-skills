# Development Plan — TASK 016 (wiki-ingest cross-course promotion / demotion)

> **Mode:** VDD (Verification-Driven Development).
> **Status:** DRAFT v1 (2026-05-26).
> **Parent docs:** [`docs/TASK.md`](TASK.md) · [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).
> **Source spec:** [`docs/wiki-ingest-promotion-spec.md`](wiki-ingest-promotion-spec.md).
> **Predecessor PLAN:** archived [`docs/plans/plan-015-wiki-ingest-modular-refactor.md`](plans/plan-015-wiki-ingest-modular-refactor.md).

This plan implements TASK 016 as **11 atomic beads** (016-00..016-10)
following the Chainlink Decomposition from
[`docs/ARCHITECTURE.md` §11](ARCHITECTURE.md#11-atomic-chain-skeleton-planner-handoff).
Each bead is independently revertable; the pipeline never has a long-lived
half-built feature on `main`.

## 0. Open Questions Resolved

Per TASK §5 and the architect's recommended-default lock-ins (§13 decision
record). The Planner adopts these defaults; the Developer does NOT re-open
them mid-execution.

| ID    | Resolution adopted in this plan                                                                                    |
|-------|--------------------------------------------------------------------------------------------------------------------|
| Q-1   | `init <vault> --root` (single subcommand with flag; see Task 016.03)                                                |
| Q-2   | `promote` defaults to dry-run; `--apply` required to commit (Task 016.05 dry-run; 016.06 apply)                     |
| Q-2b  | `demote` does NOT default to dry-run; `--dry-run` is opt-in (Task 016.07)                                            |
| Q-3   | Promotion threshold hard-coded at ≥2 courses (no schema configurability)                                            |
| Q-4   | No root-level `log.md` in v2 (per-course logs only)                                                                |
| Q-5   | No auto-promotion; operator-only (R8.5 / R13)                                                                       |
| Q-6   | Frontmatter `description:` merge picks the LONGER of the two source values                                          |
| Q-7   | Bidirectional `[[Course/Foo]]` full-path links: leave alone on reindex                                              |
| Q-8   | Course discovery via `discover_courses(vault_root)` — walks every descendant with `schema_version: 1.x`. `Lessons/` is conventional, not hardcoded. (Affects Tasks 016.00 / 016.05 / 016.06 / 016.07 footnote path computation.) |
| Q-9   | Root-page short-form footnote → `warning` (not error) in lint output (Task 016.04 lint extensions)                   |
| Q-10  | Promote-time contradiction detection: **literal-line-diff** (cheap; consistent with v1 `--contradicts` semantics). No predicate extraction. (Task 016.06.) |

## 1. Architect's MAJOR-item carry-forwards (applied to bead ordering and contracts)

| Item    | Carry-forward                                                                                                                       |
|---------|-------------------------------------------------------------------------------------------------------------------------------------|
| A-M-1   | Lint invariant-net (Task 016.04) lands BEFORE first state-mutating bead (Task 016.06 `promote --apply`). Order enforced by Dependencies. |
| A-M-2   | Vault-relative footnote form computed as `course_root.relative_to(vault_root)` — NOT literal `Lessons/`. Applies to Tasks 016.04 / 016.06 / 016.07 / 016.09. |
| A-M-3   | `_splice_frontmatter_fields` list-of-dicts extension is its own bead (Task 016.02), landing BEFORE Task 016.06.                      |
| A-M-4   | `discover_courses` skips symlinks (OVERLAP-5 carry-over), descends into matched course dirs (nested-schema support). Locked in Task 016.00. |

## 2. Stub-First adaptation (Phase 1 / Phase 2 within each command bead)

The classic Stub-First two-pass adapts to this feature as follows:

- **Phase 1 (Stubs + E2E)** lives in the *first* bead of each new command
  (016-05 for `promote`, opening of 016-07 for `demote`). The bead creates
  the module skeleton, `register` + `execute` symbols, dry-run JSON path
  (hardcoded plan), and a `tests/commands/test_<cmd>.py` that asserts the
  dry-run JSON contract on a fixture. E2E goes Red → Green on stubs.
- **Phase 2 (Logic)** lives in the *next* bead (016-06 for promote;
  remainder of 016-07 for demote). The dry-run path is replaced with real
  computation; `--apply` writes; existing E2E tests are extended to assert
  real values + post-write filesystem state.

Helper-module beads (016-00, 016-01, 016-02) follow the
**Test-First + Move** contract from PLAN 015 §"Stub-First adaptation for a
refactor": write the unit test against the new helper signature first,
confirm Red → Green, then promote callers.

Cross-bead invariant (TASK §8 risk 6 + A-M-1): once Task 016.04 ships,
every subsequent bead's verifies-gate runs `lint <fixture>` on the
two-course fixture vault and asserts zero `invariant_violation` findings.
If a regression slips in, the bead does NOT merge.

## 3. Task Execution Sequence

### Stage 0 — Pre-flight (vault-discovery helpers)

- **Task 016.00** — `find_vault_root` + `discover_courses` in `_vault.py`
  - RTM: **R1** (R1.1, R1.2, R1.3, R1.4) + **R10.6** (`test__vault.py` extensions).
  - UCs: foundation for UC-1..UC-5.
  - Description: [`docs/tasks/task-016-00-vault-discovery-helpers.md`](tasks/task-016-00-vault-discovery-helpers.md)
  - Priority: Critical
  - Dependencies: none

### Stage 1 — F2 helper extensions (no behavioural change to existing CLI)

- **Task 016.01** — Extract `_page_merge.py` from `commands/upsert_page.py`
  - RTM: **R3** preamble clarification (A-M-2 fixed `merge_into_existing` placeholder; reuse via F2 helper) + **R12.5** (import-graph invariant preserved).
  - UCs: foundation for UC-1 (promote reuses primitives) + UC-4 (root-aware upsert).
  - Description: [`docs/tasks/task-016-01-page-merge-extraction.md`](tasks/task-016-01-page-merge-extraction.md)
  - Priority: Critical
  - Dependencies: 016.00 (no shared symbols; ordering for revertability)

- **Task 016.02** — Extend `_splice_frontmatter_fields` for list-of-dicts
  - RTM: enables **R3.3** (`promoted_from:` union of `list[{course,date}]`) + **R5.4** (frontmatter restore on demote).
  - UCs: precondition for UC-1 / UC-2.
  - Description: [`docs/tasks/task-016-02-frontmatter-list-of-dicts.md`](tasks/task-016-02-frontmatter-list-of-dicts.md)
  - Priority: Critical
  - Dependencies: 016.01 (no shared symbols; ordering)
  - **Parallelism**: can land in parallel with 016.01 (different files).

### Stage 2 — Root-schema scaffold + invariant-enforcement net

- **Task 016.03** — Root-schema scaffold (`init --root`)
  - RTM: **R2** (R2.1, R2.2, R2.3, R2.4: `init <vault> --root` per Q-1).
  - UCs: precondition for UC-1 (operator scaffolds vault root before first promote).
  - Description: [`docs/tasks/task-016-03-root-schema-init.md`](tasks/task-016-03-root-schema-init.md)
  - Priority: Critical
  - Dependencies: 016.00

- **Task 016.04** — `lint.py` extensions (cross-course duplicate + invariant violation + cross-layer dangling refinement + root footnote-format warning)
  - RTM: **R6** (R6.1, R6.2, R6.3, R6.4, R6.5) + **R10.3**.
  - UCs: **UC-3** primary.
  - Description: [`docs/tasks/task-016-04-lint-cross-course.md`](tasks/task-016-04-lint-cross-course.md)
  - Priority: Critical (LANDS BEFORE first state-mutating bead per A-M-1)
  - Dependencies: 016.00 (uses `discover_courses`); 016.03 (root scaffold required for `invariant_violation` test fixture)

### Stage 3 — `promote` command (Stub-First two-pass)

- **Task 016.05** — `commands/promote.py` skeleton + dry-run path
  - RTM: **R3** (R3.1, R3.2, R3.7 preconditions) + **R4** (R4.1, R4.2 dry-run as default).
  - UCs: **UC-1** Main scenario steps 1–6.
  - Description: [`docs/tasks/task-016-05-promote-skeleton.md`](tasks/task-016-05-promote-skeleton.md)
  - Priority: Critical
  - Dependencies: 016.00, 016.01, 016.02, 016.03, 016.04

- **Task 016.06** — `promote --apply` write path + log append + footnote rewrite
  - RTM: **R3** (R3.3, R3.4, R3.5, R3.6, R3.7, R3.8, R3.9, R3.10) + **R4** (R4.3, R4.4) + **R10.1**.
  - UCs: **UC-1** Main scenario steps 7–8 + Alternative A1..A7.
  - Description: [`docs/tasks/task-016-06-promote-apply.md`](tasks/task-016-06-promote-apply.md)
  - Priority: Critical (FIRST STATE-MUTATING BEAD; covered by 016.04 net)
  - Dependencies: 016.05

### Stage 4 — `demote` command (single bead — smaller surface; uses 016.04 net)

- **Task 016.07** — `commands/demote.py` (full)
  - RTM: **R5** (R5.1..R5.8 — all preconditions, footnote rewrite, frontmatter restore, index/log update) + **R10.2**.
  - UCs: **UC-2** Main scenario + Alternative A1..A3.
  - Description: [`docs/tasks/task-016-07-demote.md`](tasks/task-016-07-demote.md)
  - Priority: High
  - Dependencies: 016.06 (round-trip test needs `promote --apply` to set up state)

### Stage 5 — `reindex` + `upsert_page` extensions (use existing fixture from earlier beads)

- **Task 016.08** — `commands/reindex.py` extensions
  - RTM: **R7** (R7.1, R7.2, R7.3, R7.4) + **R10.4** + **M-4** schema-version peek for mode detection.
  - UCs: **UC-5** Main scenario + A1.
  - Description: [`docs/tasks/task-016-08-reindex-extensions.md`](tasks/task-016-08-reindex-extensions.md)
  - Priority: High
  - Dependencies: 016.06 (needs root pages to exercise `## Shared * referenced`)
  - **Parallelism**: may land in parallel with 016.07 (different command modules; both consume the post-016.06 fixture).

- **Task 016.09** — `commands/upsert_page.py` root-aware lookup
  - RTM: **R8** (R8.1, R8.2, R8.3, R8.4, R8.5) + **R10.5**.
  - UCs: **UC-4** Main + A1.
  - Description: [`docs/tasks/task-016-09-upsert-root-aware.md`](tasks/task-016-09-upsert-root-aware.md)
  - Priority: High
  - Dependencies: 016.01 (helper extracted); 016.06 (root pages exist to look up).
  - Honest-scope note: byte-identity on single-course fixture is locked (TASK §4.4); two-tier behaviour is new and tested by 016.10 round-trip.

### Stage 6 — E2E round-trip + documentation + validators

- **Task 016.10** — End-to-end promotion round-trip, docs, validators
  - RTM: **R10.7** (two-course fixture) + **R10.8** (round-trip E2E) + **R11** (SKILL.md, references, AGENTS.md) + **R12** (validators + cross-skill diff).
  - UCs: all (UC-1..UC-5 exercised together).
  - Description: [`docs/tasks/task-016-10-e2e-docs-validators.md`](tasks/task-016-10-e2e-docs-validators.md)
  - Priority: Critical (final gate)
  - Dependencies: 016.07 + 016.08 + 016.09

---

## 4. Use Case Coverage

| Use Case | Tasks                                           |
|----------|-------------------------------------------------|
| UC-1 (promote duplicate)                | 016.00, 016.01, 016.02, 016.03, 016.04, 016.05, 016.06, 016.10 |
| UC-2 (demote root)                       | 016.00, 016.04, 016.07, 016.10                                  |
| UC-3 (lint cross-course)                 | 016.00, 016.03, 016.04, 016.10                                  |
| UC-4 (ingest into shared concept)        | 016.00, 016.01, 016.06, 016.09, 016.10                          |
| UC-5 (reindex shared sections)           | 016.00, 016.03, 016.06, 016.08, 016.10                          |

---

## 5. RTM Coverage

| RTM | Tasks                                |
|-----|--------------------------------------|
| R1  | 016.00                               |
| R2  | 016.03                               |
| R3  | 016.05 (preconditions), 016.06 (logic) |
| R4  | 016.05 (dry-run path), 016.06 (apply / idempotency / no-op) |
| R5  | 016.07                               |
| R6  | 016.04                               |
| R7  | 016.08                               |
| R8  | 016.09                               |
| R9  | 016.00 (find_vault_root schema-version check); 016.03 (root scaffold); 016.05 + 016.06 + 016.07 (refusal in commands) |
| R10 | 016.00, 016.01, 016.02, 016.03, 016.04, 016.05, 016.06, 016.07, 016.08, 016.09, 016.10 (R10.1..R10.8 distributed) |
| R11 | 016.10 (docs sweep)                  |
| R12 | 016.10 (validators + cross-skill)    |
| R13 | locked by absence of non-goal beads; verified by code-reviewer |

---

## 6. Cross-Cutting Verification Gates (run on every bead)

Each bead's verifies-section MUST satisfy ALL of the following before merge:

1. **Per-bead unit tests** green (`python -m unittest discover -s tests`).
2. **`tests/test_architecture.py`** green (import-graph invariant).
3. **`tests/test_r11_byte_identity.py`** green on single-course fixture (TASK 015 R11 — must NOT regress under no-root-schema condition).
4. **From 016.04 onwards**: `python3 scripts/wiki_ops.py lint <two-course-fixture>` shows zero `invariant_violation` findings.
5. **016.10 only**: `validate_skill.py` exit 0 + `skill-validator/validate.py` reports SAFE + cross-skill `diff -q` matrix silent.

---

## 7. Risk → Mitigation map (carried from TASK §8)

| TASK §8 risk                                                                 | Mitigation in plan |
|------------------------------------------------------------------------------|--------------------|
| 1. Footnote rewrite regex fragility                                          | 016.06 ships a `tests/test__markdown.py` adversarial case before wiring R3.5 (see task file §"Test Cases" TC-UNIT). |
| 2. `_splice_frontmatter_fields` list-of-dicts edge cases                     | 016.02 is its own bead, fully tested before 016.06 consumes it. |
| 3. Lint findings count blow-up                                               | 016.04 includes a `--limit N` flag (R6.6 — added as planning decision; see task file). |
| 4. Demote citation-scan O(courses × sources × footnotes)                     | 016.07 reuses `_extract_wikilinks_with_anchors` mask-once helper; performance budget locked (TASK §4.1 ≤0.4 s on 5×100 fixture). |
| 5. Re-promote (R3.7) semantics                                               | 016.06 JSON envelope distinguishes "first-time" vs "fold-in-additional" via `"mode": "first_promote" \| "merge_into_root"` discriminator. |
| 6. Hidden invariant break during dev                                         | A-M-1 fix: 016.04 lint invariant-net lands BEFORE any state-mutating bead. |

---

## 8. Parallelism / Sequencing summary

Hard sequential chain (cannot reorder):

```
016.00 ─┬─ 016.01 ─┐
        │          ├─ 016.05 ─ 016.06 ─┬─ 016.07 ─┐
        ├─ 016.02 ─┘                   ├─ 016.08 ─┼─ 016.10
        │                              └─ 016.09 ─┘
        └─ 016.03 ─ 016.04 ─ 016.05 (joins above)
```

Reading: 016.00 unblocks 016.01/02/03. 016.01+02 unblock 016.05. 016.03
unblocks 016.04, which unblocks 016.05 (invariant net live before any
state-mutating bead — A-M-1). 016.06 is the first state-mutating bead and
fans out into the three independent extensions (07/08/09) that all merge
into the final gate 016.10.

Parallelism opportunities (informational):

- **016.01 ∥ 016.02** — touch different modules (`_page_merge.py` vs `_frontmatter.py`).
- **016.07 ∥ 016.08 ∥ 016.09** — three independent extensions after 016.06; all merge into 016.10.

---

## 9. Deliverables checklist (Planner → Developer handoff)

- [ ] 11 task files under `docs/tasks/task-016-*.md` (one per bead).
- [ ] Each task file: Goal, Use-Case link, Changes (new files + edits with method-level granularity), Test Cases, Acceptance Criteria.
- [ ] Bead order respects A-M-1 (lint net before state-mutation).
- [ ] Helper extensions (016.01, 016.02) land before their consumers (016.06+).
- [ ] Final bead (016.10) gates the merge with validators + cross-skill `diff -q`.
- [ ] No bead introduces a non-R13 feature (no auto-promotion, no semantic identity, no root log, no custom kinds, no file-watch, no full-path link normalisation, no configurable threshold).

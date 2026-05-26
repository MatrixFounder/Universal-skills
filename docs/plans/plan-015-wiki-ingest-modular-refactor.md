# Development Plan — TASK 015 (wiki-ingest modular refactor)

> **Mode:** VDD. **Status:** DRAFT v1 (2026-05-25). **Predecessor:** see archived
> [`docs/plans/plan-014-pdf-outline-bookmarks.md`](plans/plan-014-pdf-outline-bookmarks.md).
> **Parent docs:** [`docs/TASK.md`](TASK.md) · [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).

This plan implements TASK 015 as **13 atomic beads** following the
Chainlink Decomposition from [`docs/ARCHITECTURE.md` §11](ARCHITECTURE.md#11-atomic-chain-skeleton-planner-handoff).
Each bead is independently revertable; the pipeline never has a long-lived
half-refactored `wiki_ops.py` on `main`.

## Stub-First adaptation for a refactor

The classic Stub-First two-pass (interface → logic) doesn't map onto a
pure refactor because no new logic is being added. The equivalent contract
for each bead is **Test-First + Move**:

1. **Phase 1 (Red→Green)** — before moving any code, write the unit
   test(s) against the **current** symbol location (e.g. `wiki_ops.read_text`
   for bead 015-01). Run and confirm green.
2. **Phase 2 (Move)** — extract the symbol to its new module, replace the
   original definition with a re-export `from wiki_ingest._safety import
   read_text`, and **update the test imports to the new location**. Run
   and confirm still-green. The shim re-export keeps `wiki_ops.read_text`
   working for any internal call site that hasn't been migrated yet within
   the same bead, so the bead is small.
3. **Phase 3 (Verify)** — run the deterministic-fixture `diff -q` gate
   (R11) and the validator pair (R10).

For Beads 015-06..015-11 (command modules) this becomes:
- **Phase 1** — write per-command tests that drive the command via
  `subprocess.run([..., "wiki_ops.py", "<cmd>", ...])` against a fixture
  vault, capture stdout + filesystem effects. Run; green.
- **Phase 2** — extract command logic to `wiki_ingest/commands/<cmd>.py`
  with `register` + `execute` symbols; wire `wiki_ops.py` to dispatch.
- **Phase 3** — re-run the tests; same stdout + same fs effects.

---

## Task Execution Sequence

### Stage 0 — Pre-flight (R11 prerequisite)

- **Task 015.00** — Determinism pre-check + fixture freeze
  - **Goal**: confirm `scan` / `lint` / `classify-folder` already produce
    deterministic stdout (sorted keys, sorted file iteration); commit
    frozen fixture vaults under `scripts/tests/fixtures/`.
  - RTM: precondition for **R11**.
  - Description: [`docs/tasks/task-015-00-determinism-check.md`](tasks/task-015-00-determinism-check.md)
  - Priority: Critical
  - Dependencies: none

### Stage 1 — Helper module extraction (F1 + F2 + F3-helpers)

> Each bead in this stage extracts a cohesive helper module behind the
> Test-First+Move contract above. After each bead `wiki_ops.py` shrinks
> by N lines and gains one `from wiki_ingest.<module> import …` block;
> the shim's CLI behaviour is unchanged.

- **Task 015.01** — Create package skeleton + extract `_safety.py`
  - RTM: **R1.1** (package layout) + **R2** (safety primitives) + **R8.1**
    (≥3 unit tests).
  - UCs: UC-3 (E2E smoke retains parity).
  - Description: [`docs/tasks/task-015-01-package-and-safety.md`](tasks/task-015-01-package-and-safety.md)
  - Priority: Critical
  - Dependencies: 015.00

- **Task 015.02** — Extract `_markdown.py`
  - RTM: **R3** + **R8.1** (markdown tests).
  - UCs: UC-2 (per-module critic loop).
  - Description: [`docs/tasks/task-015-02-markdown-module.md`](tasks/task-015-02-markdown-module.md)
  - Priority: Critical
  - Dependencies: 015.01

- **Task 015.03** — Extract `_frontmatter.py`
  - RTM: **R4** + **R8.1** (frontmatter tests).
  - UCs: UC-2.
  - Description: [`docs/tasks/task-015-03-frontmatter-module.md`](tasks/task-015-03-frontmatter-module.md)
  - Priority: Critical
  - Dependencies: 015.02 (imports `_safety`; no dep on `_markdown`)

- **Task 015.04** — Extract `_vault.py`
  - RTM: **R5** + **R8.1** (vault tests).
  - UCs: UC-2.
  - Description: [`docs/tasks/task-015-04-vault-module.md`](tasks/task-015-04-vault-module.md)
  - Priority: Critical
  - Dependencies: 015.03 (imports `_safety` + `_frontmatter`)

- **Task 015.05** — Extract `_classify.py`
  - RTM: **R6** + **R8.1** (classify tests).
  - UCs: UC-2.
  - Description: [`docs/tasks/task-015-05-classify-module.md`](tasks/task-015-05-classify-module.md)
  - Priority: High
  - Dependencies: 015.01 (imports only `_safety`; no dep on 015.02-04)
  - **Parallelism**: may land in parallel with 015.02 / 015.03 / 015.04
    — `_classify.py` has zero compile-time dependency on the markdown
    or frontmatter engines. A second developer can take this bead
    immediately after 015.01 merges.

### Stage 2 — Command module extraction (F3 drivers)

> Each bead extracts ≤3 commands per merge, with per-command tests
> driving via `subprocess.run`. After each bead `wiki_ops.py` shrinks by
> ~150 LoC per command and gains one `register()` + `execute()` dispatch.

- **Task 015.06** — Extract `commands/scan.py` + `commands/init.py`
  - RTM: **R7** (partial) + **R7.4** (architecture lint scaffold).
  - UCs: UC-1 (new-command-shape demo), UC-3 (smoke E2E).
  - Description: [`docs/tasks/task-015-06-commands-scan-init.md`](tasks/task-015-06-commands-scan-init.md)
  - Priority: Critical
  - Dependencies: 015.01..015.05

- **Task 015.07** — Extract `commands/upsert_page.py` + `commands/update_index.py`
  - RTM: **R7** (partial).
  - UCs: UC-3.
  - Description: [`docs/tasks/task-015-07-commands-upsert-update.md`](tasks/task-015-07-commands-upsert-update.md)
  - Priority: Critical
  - Dependencies: 015.06

- **Task 015.08** — Extract `commands/append_log.py` + `commands/log_event.py`
  - RTM: **R7** (partial).
  - UCs: UC-3.
  - Description: [`docs/tasks/task-015-08-commands-append-logevent.md`](tasks/task-015-08-commands-append-logevent.md)
  - Priority: High
  - Dependencies: 015.06 (independent of 015.07)

- **Task 015.09** — Extract `commands/register_summary.py`
  - RTM: **R7** (partial) — largest command; isolated bead.
  - UCs: UC-3 (adversarial register-summary smoke).
  - Description: [`docs/tasks/task-015-09-commands-register-summary.md`](tasks/task-015-09-commands-register-summary.md)
  - Priority: High
  - Dependencies: 015.07 (shares `_frontmatter` splice path with upsert/update)

- **Task 015.10** — Extract `commands/find.py` + `commands/lint.py` + `commands/reindex.py`
  - RTM: **R7** (partial).
  - UCs: UC-3 (full E2E init → upsert → lint → reindex byte-identity).
  - Description: [`docs/tasks/task-015-10-commands-find-lint-reindex.md`](tasks/task-015-10-commands-find-lint-reindex.md)
  - Priority: Critical
  - Dependencies: 015.09

- **Task 015.11** — Extract `commands/classify_folder.py`
  - RTM: **R7** (final command).
  - UCs: UC-3 (classify-folder smoke).
  - Description: [`docs/tasks/task-015-11-commands-classify-folder.md`](tasks/task-015-11-commands-classify-folder.md)
  - Priority: High
  - Dependencies: 015.10

### Stage 3 — Shim trim + docs + final validation

- **Task 015.12** — Trim `wiki_ops.py` ≤200 LoC + `references/architecture.md` + final validator pass
  - RTM: **R1.2/R1.3** (shim ≤200 LoC, no new entry points) + **R9** (cross-skill matrix silent) + **R10** (validator pass) + **R11** (final byte-identity gate on three fixtures) + **R12** (architecture reference doc).
  - UCs: UC-3 (final E2E + validator pass).
  - Description: [`docs/tasks/task-015-12-shim-docs-validate.md`](tasks/task-015-12-shim-docs-validate.md)
  - Priority: Critical
  - Dependencies: 015.11

---

## Use Case Coverage

| Use Case | Tasks                                            |
|----------|--------------------------------------------------|
| UC-1     | 015.06 (command-shape demo)                      |
| UC-2     | 015.01, 015.02, 015.03, 015.04, 015.05           |
| UC-3     | 015.00, 015.06, 015.07, 015.08, 015.09, 015.10, 015.11, 015.12 |

## RTM ↔ Task Coverage

| RTM ID | Description                                       | Task(s)                                                   |
|--------|---------------------------------------------------|------------------------------------------------------------|
| R1     | Package layout + shim ≤200 LoC + no new entry pts | 015.01 (package skeleton), 015.12 (final shim trim)        |
| R2     | `_safety.py`                                      | 015.01                                                     |
| R3     | `_markdown.py`                                    | 015.02                                                     |
| R4     | `_frontmatter.py`                                 | 015.03                                                     |
| R5     | `_vault.py`                                       | 015.04                                                     |
| R6     | `_classify.py`                                    | 015.05                                                     |
| R7     | Commands package + register/execute contract      | 015.06 (R7.4 lint scaffold), 015.07, 015.08, 015.09, 015.10, 015.11 |
| R8     | `tests/` directory + per-module + E2E             | 015.01..015.11 each adds its slice; 015.12 enforces totals |
| R9     | Cross-skill replication matrix silent             | 015.12                                                     |
| R10    | Validator pass (skill-creator + skill-validator)  | 015.12                                                     |
| R11    | Behavioural parity (`diff -q` silent)             | 015.00 (precondition + fixture freeze); 015.12 (final gate) |
| R12    | `references/architecture.md`                      | 015.12                                                     |

Every RTM item is covered. Every task ID has at least one RTM linkage.
No task is a "feature group" — each bead is one atomic change to one
module group, gated by tests + the R11 byte-identity check.

---

## Risk Register

| Risk                                                        | Mitigation                                                              | Owner-task |
|-------------------------------------------------------------|--------------------------------------------------------------------------|------------|
| `cmd_scan`'s `last_log_entries` drifts daily (TZ / append-log) | 015.00 freezes a static `log.md` in the fixture vault                    | 015.00     |
| A bead breaks an undocumented internal call chain            | Each bead keeps backward-compat re-exports inside `wiki_ops.py` until the shim trim in 015.12; tests exercise both old and new import paths during transition | 015.01..015.11 |
| `_classify.py` exceeds 350-LoC ceiling                       | The `_classify.py` extraction (015.05) is single-purpose; if size drifts above the budget the bead is split — adjust the plan rather than the architecture | 015.05     |
| Determinism pre-check finds drift (sorted-keys NOT set)      | 015.00 IS the fix bead — it lands the determinism fix as its first commit, then captures fixtures | 015.00     |
| `register_summary.py` exceeds 350-LoC ceiling                | After extracting `_splice_frontmatter_fields` to `_frontmatter.py` (015.03), the command is ≤220 LoC expected; the ≤350 ceiling has 130-LoC headroom | 015.09     |
| Hidden coupling between command handlers surfaces            | The R7.4 ast-walking `test_architecture.py` (015.06) fails-loudly on any forbidden import | 015.06+    |

---

## Phase-boundary checkpoint

At the end of each bead the developer MUST:

1. Run `python -m unittest discover -s tests` → 0 failures.
2. Run the R11 byte-identity check on the three deterministic fixtures
   (`scan`, `lint`, `classify-folder`).
3. Run `validate_skill.py skills/wiki-ingest` → exit 0.
4. Persist session state via
   `python3 .agent/skills/skill-session-state/scripts/update_state.py …`
   with the bead ID + status.

Only after these four checks pass is the bead considered "merged" (in
isolation; the actual merge is at the developer's discretion). A failed
check stops the chain — the developer reverts the bead and re-plans.

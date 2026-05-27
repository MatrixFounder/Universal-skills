# Development Plan — TASK 017 (wiki-ingest v1.1 contract alignment)

> **Mode:** VDD (Verification-Driven Development).
> **Status:** DRAFT v1 (2026-05-27).
> **Parent docs:** [`docs/TASK.md`](TASK.md) · [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).
> **External source spec:** [`obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md`](../../obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md)
> — mirrored verbatim into [`skills/wiki-ingest/references/manifest_schema.md`](../skills/wiki-ingest/references/manifest_schema.md) in 017-04.
> **Predecessor PLAN:** archived [`docs/plans/plan-016-wiki-ingest-cross-course-promotion.md`](plans/plan-016-wiki-ingest-cross-course-promotion.md).

This plan implements TASK 017 as **10 atomic beads** (017-00..017-09)
following the Chainlink Decomposition locked in
[`docs/ARCHITECTURE.md` §11](ARCHITECTURE.md#11-atomic-chain-skeleton-planner-handoff).
Each bead is independently revertable; the pipeline never has a long-lived
half-built feature on `main`.

## 0. Open Questions Resolved

Per TASK §5 and the architect's locked defaults in
[`docs/ARCHITECTURE.md` §12](ARCHITECTURE.md#12-open-questions) (TASK 017
table). The Planner adopts these defaults; the Developer does NOT re-open
them mid-execution.

| ID  | Resolution adopted in this plan                                                                                                                    |
|-----|----------------------------------------------------------------------------------------------------------------------------------------------------|
| Q-1 | **Per-step rollback + `exit 20` + `written_so_far[]`**. NO tempdir/rename staging. Locked in 017-06 (write path).                                    |
| Q-2 | **New `_dispatch.py` F3 helper with whitelist + local imports**. Locked in 017-03 (dispatch substrate lands before 017-05 orchestrator skeleton).  |
| Q-3 | `--source-hash` = sha256 of raw input bytes regardless of `type:` frontmatter. The skill trusts the caller; no recomputation. Locked in 017-05/07. |
| Q-4 | `summary-light` is NOT a manifest concept — it stays an index-layer-internal TYPE_MAPPING concern. Manifest `kind` enum locked to `source` / `concept` / `entity` / `index` / `log` (017-05). |
| Q-5 | Single-course vaults emit `course: null` AND `written[].scope: "course"` — verified by 017-06 against the existing single-course fixture.          |

## 1. Architect's MAJOR-item carry-forwards (applied to bead ordering and contracts)

| Item     | Carry-forward                                                                                                                                  |
|----------|------------------------------------------------------------------------------------------------------------------------------------------------|
| Arch-M-1 | The **manifest contract reference page** (017-04) lands BEFORE the orchestrator skeleton (017-05). Defends against external-contract drift; 017-05 tests use the embedded §1 JSON example block as a fixture (Architect §11 ordering rationale). |
| Arch-M-2 | The **dispatch substrate** (017-03) lands BEFORE the orchestrator (017-05). `commands/ingest.py` cannot exist without `_dispatch.py`; the AST-walker carve-out in `test_architecture.py` is also locked in 017-03. |
| Arch-M-3 | **`manifest_version: "1.1"` is structural**, not honor-system. Locked in 017-04 (reference page) AND verified by 017-05 (skeleton emits it). |
| Arch-M-4 | **Exit code 26 (TIMEOUT) is split from 21 (downstream-subprocess)**. Both codes carry a `phase:"…"` discriminator. Locked in 017-02 (`EXIT_*` constants) AND tested in 017-07 (timeout case). The v1.1 contract codes live in the 20..26 band — see [`skills/wiki-ingest/references/exit_codes.md`](../skills/wiki-ingest/references/exit_codes.md) for the audit. |
| Arch-M-5 | **Per-step rollback (Q-1)** governs 017-06's write path: each atomic-op dispatch commits independently; on mid-pipeline failure, emit `phase:"<phase>"` + `written_so_far[]` + exit 20. No staging tempdir. |
| Arch-M-6 | **No PyYAML**. `--config <path>` is parsed by a hand-rolled subset parser (T17-S5) following the `_frontmatter.py` style. Locked in 017-07.    |
| Arch-M-7 | **`_dispatch.dispatch()` validates `cmd_name` against `_ALLOWED_COMMANDS` BEFORE `importlib.import_module`** (T17-S9). Locked in 017-03.       |

## 2. Stub-First adaptation (Phase 1 / Phase 2 within the orchestrator beads)

The classic Stub-First two-pass adapts to this feature as follows:

- **Phase 1 (Stubs + E2E) = 017-05** — `commands/ingest.py` ships with the
  argparse contract complete, manifest emission well-formed (uses the §1
  JSON example block from 017-04 as a fixture), source-hash idempotency
  short-circuit working, vault_id routing emitting exit 23/24/25 correctly,
  but `written[]` is hardcoded EMPTY (no real writes via dispatch). Tests
  assert the dry-run-equivalent contract.
- **Phase 2 (Logic) = 017-06** — replace the empty `written[]` stub with
  real composition via `_dispatch.dispatch()` over the atomic ops; manifest
  `written[]` populated post-hoc from each dispatch return; tests assert
  the actual `git diff` of the fixture matches the manifest claim.

Helper-substrate beads (017-00, 017-01, 017-02, 017-03) follow the
**Test-First + Build** contract: write the unit test against the new
helper signature first, confirm Red → Green, then add callers.

Cross-bead invariant: from 017-03 onwards, `tests/test_architecture.py`
runs on every bead and asserts (a) the existing "no command imports
another command" rule AND (b) the new "`_dispatch.py` has no module-level
`wiki_ingest.commands.*` imports" rule. A regression in either gate ⇒
bead does NOT merge.

## 3. Task Execution Sequence

### Stage 0 — Pre-flight (version action + `--version` smoke)

- **Task 017.00** — `__version__ = "1.1.0"` + `wiki_ops.py --version`
  - RTM: **R2** (R2.1, R2.2, R2.3, R2.4).
  - UCs: precondition for UC-1 (the bridge runs `wiki-ingest --version`
    as its first call).
  - Description: [`docs/tasks/task-017-00-version-action.md`](tasks/task-017-00-version-action.md)
  - Priority: Critical
  - Dependencies: none

### Stage 1 — Shell wrapper + safety/vault helpers (no behavioural change to existing CLI)

- **Task 017.01** — Shell wrapper `scripts/wiki-ingest` (POSIX, no `.sh`)
  - RTM: **R1** (R1.1, R1.2, R1.3, R1.4) + **R13.3** (`tests/test_cli_wrapper.py`).
  - UCs: precondition for UC-1 (the bridge invokes `wiki-ingest` on PATH).
  - Description: [`docs/tasks/task-017-01-shell-wrapper.md`](tasks/task-017-01-shell-wrapper.md)
  - Priority: Critical
  - Dependencies: 017.00 (the wrapper's first test asserts `wiki-ingest
    --version` exits 0, which requires 017.00 to be live)

- **Task 017.02** — `_safety.EXIT_*` constants + `vault_id` helpers in `_vault.py`
  - RTM: **R3** (R3.2, R3.3, R3.4 helpers — enforcement wiring lives in 017-05/08) + **R4** (R4.1, R4.4 — `EXIT_*` constants).
  - UCs: foundation for UC-3 (strict-mode vault_id) + UC-5 (partial-success exit 20) + UC-6 (timeout exit 26).
  - Description: [`docs/tasks/task-017-02-safety-vault-helpers.md`](tasks/task-017-02-safety-vault-helpers.md)
  - Priority: Critical
  - Dependencies: 017.00

### Stage 2 — Dispatch substrate (must land before the orchestrator)

- **Task 017.03** — `_dispatch.py` F3 helper (resolves architecture Q-2)
  - RTM: **R5.2 substrate** (the dispatch primitive `ingest.py` composes over) + **R14.5** (architecture test extension) + **R4.5** security gate (whitelist + `phase` envelope harness).
  - UCs: foundation for UC-1 (orchestrator dispatch), UC-2 (operator-direct ingest), UC-5 (partial-success routing).
  - Description: [`docs/tasks/task-017-03-dispatch-helper.md`](tasks/task-017-03-dispatch-helper.md)
  - Priority: Critical (Arch-M-2 — must land before 017.05)
  - Dependencies: 017.02 (uses `EXIT_*` for error envelopes)

### Stage 3 — Contract reference page (architect's pre-orchestrator gate)

- **Task 017.04** — `references/manifest_schema.md` (verbatim contract mirror)
  - RTM: **R6.3** (full verbatim mirror) + **R12.3** (extended mirror of CONTRACT §1/§2/§3/§5/§6/§7/§8).
  - UCs: foundation for UC-1 (consumer reads the in-repo contract).
  - Description: [`docs/tasks/task-017-04-manifest-schema-reference.md`](tasks/task-017-04-manifest-schema-reference.md)
  - Priority: Critical (Arch-M-1 — must land before 017.05)
  - Dependencies: 017.00 (so the reference page can cite `__version__`)
  - **Parallelism**: can land in parallel with 017-01/02/03 (doc-only, no code surface).

### Stage 4 — Orchestrator (Stub-First two-pass)

- **Task 017.05** — `commands/ingest.py` skeleton (Phase 1 — argparse + manifest emission + vault_id routing; NO writes)
  - RTM: **R5.1** (argparse contract complete) + **R3.4–R3.5** (vault_id flag routing → exit 23/24/25) + **R6.1, R6.2, R6.4, R6.5** (manifest shape; `written[]` empty stub) + **R9.1, R9.2, R9.3** (source-hash short-circuit; UC-4 `action:"unchanged"`) + **R10.1** (TTY check), **R10.2** (`--quiet`) + **Arch-M-3** (`manifest_version: "1.1"`).
  - UCs: **UC-3** (strict-mode vault_id) + **UC-4** (source-hash short-circuit) + scaffolding for UC-1 / UC-2 / UC-5 (filled out in 017-06).
  - Description: [`docs/tasks/task-017-05-ingest-skeleton.md`](tasks/task-017-05-ingest-skeleton.md)
  - Priority: Critical
  - Dependencies: 017.02 (`EXIT_*` constants + vault_id helpers), 017.03 (dispatch — imported but not yet invoked with real ops; skeleton can pass a no-op pipeline), 017.04 (manifest schema reference to validate against)

- **Task 017.06** — `commands/ingest.py` write path (Phase 2 — orchestrator composition + per-step rollback)
  - RTM: **R5.2 full pipeline** (steps (a)–(h) wired via `_dispatch`) + **R5.3** (per-step rollback + `exit 20` + `written_so_far[]`) + **R5.5** (no auto-promotion) + **R6.4** (atomic emission + partial envelope) + **R8** (structured `log_event` with `log_md_byte_offset` captured post-`append-log`) + **Arch-M-5**.
  - UCs: **UC-1** Main scenario (steps 5(a)–5(h) + 6–9 — full bridge round-trip) + **UC-2** Main scenario (operator-direct ingest, human output) + **UC-5** Main scenario (partial-success recovery via exit 20) + **Q-5** verification (single-course vault → `course: null` + `scope: "course"`).
  - Description: [`docs/tasks/task-017-06-ingest-write-path.md`](tasks/task-017-06-ingest-write-path.md)
  - Priority: Critical (FIRST STATE-MUTATING BEAD via the orchestrator; covered by 017-03's dispatch whitelist)
  - Dependencies: 017.05 (skeleton must be live; this bead replaces the empty `written[]` stub)

### Stage 5 — Flag families + init extension (independent extensions after 017-06)

- **Task 017.07** — `--known-concepts-stdin/file` + `--source-hash` + `--config` + `--quiet` + `--timeout-seconds`
  - **Atomicity escape valve (pre-authorised)**: if 017-07's net LoC
    delta crosses ~400 or its test count exceeds ~15, split the
    `_vault.scan_vault_pages` extraction into a sub-bead
    `017-07a-scan-helper-extraction.md` (the remaining flag families
    stay in 017-07). See [`task-017-07-flag-families.md`](tasks/task-017-07-flag-families.md) §"Acceptance Criteria" for the trigger.
  - RTM: **R7** (R7.1–R7.5 known-concepts injection) + **R9** (R9.1, R9.2, R9.4 `--source-hash` integration with footer; 9.3 short-circuit was already in 017-05) + **R10** (R10.1, R10.2, R10.3, R10.4 — `--timeout-seconds` → exit 26 + `phase:"timeout"` per Arch-M-4) + **R11** (R11.1–R11.4 `--config` YAML subset; Arch-M-6 hand-rolled parser).
  - UCs: **UC-1** Main step 3 (`--known-concepts-stdin` injection) + **UC-1** Main step 4 (full flag set) + new **UC-6** (timeout: subprocess overrun → exit 26 + `phase:"timeout"`, tested as part of 017-07; UC-6 added inline in this plan because TASK 017 §3 originally documented timeout under UC-5; the planner splits it for testability).
  - Description: [`docs/tasks/task-017-07-flag-families.md`](tasks/task-017-07-flag-families.md)
  - Priority: High
  - Dependencies: 017.06 (full orchestrator must exist before its flags can be exercised end-to-end)
  - **Parallelism**: may land in parallel with 017-08 (different argparse surfaces; both consume the post-017-06 fixture).

- **Task 017.08** — `commands/init.py` extension (`--vault-id <slug>` flag)
  - RTM: **R3.1** (`init --root --vault-id <slug>` writes the slug in the root schema scaffold) + **R12.4** (`references/wiki_schema.md` extended with `vault_id` §"v1.1" — documentation lives in 017-09 final sweep, but the wiki_schema.md edit is locked here for traceability).
  - UCs: precondition for **UC-1** (operator scaffolds a vault with `vault_id:` in the root schema before first `/wiki-enrich`).
  - Description: [`docs/tasks/task-017-08-init-vault-id.md`](tasks/task-017-08-init-vault-id.md)
  - Priority: High
  - Dependencies: 017.02 (`validate_vault_id_pattern` lives there)
  - **Parallelism**: may land in parallel with 017-07 (different command modules; both merge into the final gate 017-09).

### Stage 6 — E2E v1.1 contract smoke + documentation + validators

- **Task 017.09** — End-to-end v1.1 contract smoke, docs, validators
  - RTM: **R13.4** (`tests/test_e2e_v1_1_contract.py`) + **R13.5** (regression — TASK 015/016 tests still green) + **R12.1, R12.2, R12.5, R12.6** (SKILL.md updates, ARCHITECTURE.md already updated, AGENTS.md updated) + **R14** (validators + cross-skill `diff -q` matrix silent).
  - UCs: all (UC-1..UC-5 exercised together end-to-end).
  - Description: [`docs/tasks/task-017-09-e2e-docs-validators.md`](tasks/task-017-09-e2e-docs-validators.md)
  - Priority: Critical (final gate)
  - Dependencies: 017.07 + 017.08

---

## 4. Use Case Coverage

| Use Case                                | Tasks                                                          |
|-----------------------------------------|----------------------------------------------------------------|
| UC-1 (bridge end-to-end)                | 017.00, 017.01, 017.02, 017.03, 017.04, 017.05, 017.06, 017.07, 017.08, 017.09 |
| UC-2 (operator-direct ingest)           | 017.01, 017.05, 017.06, 017.09                                 |
| UC-3 (strict-mode vault_id)             | 017.02, 017.05, 017.08, 017.09                                 |
| UC-4 (source-hash short-circuit)        | 017.05, 017.07, 017.09                                         |
| UC-5 (partial-success exit 20)           | 017.02, 017.06, 017.09                                         |
| UC-6 (timeout exit 26 — planner-split from UC-5) | 017.02, 017.07, 017.09                                 |

---

## 5. RTM Coverage

| RTM | Tasks                                                          |
|-----|----------------------------------------------------------------|
| R1  | 017.01                                                         |
| R2  | 017.00                                                         |
| R3  | 017.02 (helpers), 017.05 (flag routing → exit 23/24/25), 017.08 (`init --vault-id`) |
| R4  | 017.02 (`EXIT_*` constants), 017.06 (exit 20 envelope), 017.07 (exit 26 timeout) |
| R5  | 017.03 (dispatch substrate), 017.05 (skeleton — Phase 1), 017.06 (write path — Phase 2) |
| R6  | 017.04 (verbatim mirror), 017.05 (skeleton emits well-formed shape), 017.06 (write path populates `written[]`) |
| R7  | 017.07                                                         |
| R8  | 017.06 (post-`append-log` byte-offset capture)                  |
| R9  | 017.05 (short-circuit), 017.07 (`--source-hash` flag wiring)    |
| R10 | 017.05 (TTY check + `--quiet`), 017.07 (`--timeout-seconds` + env var) |
| R11 | 017.07 (`--config` YAML subset)                                 |
| R12 | 017.04 (reference page), 017.08 (`wiki_schema.md` `vault_id` §), 017.09 (SKILL.md + AGENTS.md sweep; ARCHITECTURE.md already updated) |
| R13 | 017.00 (cli wrapper smoke), 017.01 (wrapper test), 017.03 (dispatch test), 017.04 (schema test), 017.05 (skeleton tests), 017.06 (write-path tests), 017.07 (flag-family tests), 017.08 (init-vault-id tests), 017.09 (E2E v1.1 contract + regression) |
| R14 | 017.03 (`test_architecture.py` extension), 017.09 (validators + cross-skill diff matrix) |
| R15 | locked by absence of non-goal beads; verified by code-reviewer  |

---

## 6. Cross-Cutting Verification Gates (run on every bead)

Each bead's verifies-section MUST satisfy ALL of the following before merge:

1. **Per-bead unit tests** green (`python -m unittest discover -s tests`).
2. **`tests/test_architecture.py`** green — TASK 015 invariant (no
   `wiki_ingest/_*.py` imports `wiki_ingest.commands.*`; no
   `commands/<a>.py` imports `commands/<b>.py`) AND from 017-03 onwards
   the new "`_dispatch.py` has no module-level `wiki_ingest.commands.*`
   imports" assertion.
3. **TASK 015/016 regression suite** green (`tests/test_known_issues_resolved.py`,
   `tests/test_e2e_promotion.py`, etc. — no regression to merged features).
4. **From 017-04 onwards**: `tests/test_manifest_schema.py` parses the
   reference's §1 JSON example block and asserts it round-trips.
5. **From 017-05 onwards**: `wiki-ingest ingest …` against the
   `tests/fixtures/two_course_vault/` fixture (added by TASK 016)
   produces a manifest validating against
   `references/manifest_schema.md`.
6. **017.09 only**:
   - `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/wiki-ingest` exit 0.
   - `python3 .claude/skills/skill-validator/scripts/validate.py skills/wiki-ingest` reports SAFE.
   - Cross-skill `diff -q` matrix (CLAUDE.md §9) silent.
   - SKILL.md, `.AGENTS.md`, all references updated.

---

## 7. Risk → Mitigation map (carried from TASK §7)

| TASK §7 risk                                                                                  | Mitigation in plan                                                                                                                                |
|-----------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| 1. The new `ingest` orchestrator duplicates or contradicts atomic-op invariants.              | 017-03's whitelist + 017-05's "no direct writes" skeleton + 017-06's per-step rollback gate. `tests/test_architecture.py` import-graph assertion. |
| 2. Manifest schema drift between this skill and the index-layer consumer.                     | 017-04 ships the verbatim mirror BEFORE the orchestrator (Arch-M-1). `tests/test_manifest_schema.py` parses the example block as a fixture; 017-09 e2e cross-validates against `/wiki-enrich`. |
| 3. `vault_id` mandate breaks existing standalone wiki-ingest users.                            | R3 emit-don't-enforce; 017-08 tests verify single-course vaults without `vault_id` still pass. UC-3 alternative path (no `--vault-id` flag → manifest `vault_id: null`) tested in 017-05. |
| 4. `--known-concepts-stdin` payload too large.                                                | T17-S2: 1 MiB cap (configurable via env) BEFORE JSON parsing. Tested in 017-07 with a 2-MiB negative-path case. |
| 5. Partial-success state (`exit 20`) leaves the operator confused.                              | Manifest carries `phase`, `written_so_far[]`, `cleanup_advice`. 017-06 unit test asserts a mid-pipeline injected failure → exit 20 + non-empty `written_so_far[]`. |
| 6. CLI wrapper breaks on edge shells (zsh + symlinks + spaces in PATH).                        | 017-01 wrapper uses `readlink -f` + macOS fallback (T17-S8) + `"$@"` quoting. `tests/test_cli_wrapper.py` runs the wrapper from a symlinked path with spaces. |

---

## 8. Parallelism / Sequencing summary

Hard sequential chain (cannot reorder):

```
017.00 ──┬──── 017.01 ─┐
         │              │
         ├──── 017.02 ──┼─── 017.03 ──┐
         │              │              │
         └──── 017.04 ──┘              ├── 017.05 ── 017.06 ──┬── 017.07 ──┐
                                       │                       │            │
                                       │                       │            ├── 017.09
                                       │                       │            │
                                       │                       └── 017.08 ──┘
```

Reading: 017.00 unblocks every downstream bead (the `--version` action is
the smoke gate). 017.01/02/04 are mutually independent and can land in
any order. 017.03 requires 017.02 (`EXIT_*` constants). 017.05 needs
017.02 + 017.03 + 017.04. 017.06 strictly follows 017.05 (Phase 2 over
Phase 1). 017.07 and 017.08 are independent extensions over 017.06; both
merge into the final gate 017.09.

Parallelism opportunities (informational, no claim of orchestration):

- **017.01 ∥ 017.02 ∥ 017.04** — three independent files (`scripts/wiki-ingest`
  wrapper vs `_safety.py`/`_vault.py` helpers vs `references/manifest_schema.md`).
- **017.07 ∥ 017.08** — different command modules after 017.06.

---

## 9. Honest-scope locks (TASK §6 + §7 carry-forward)

- R15.1..R15.6 (no new LLM patterns; no three-tier vault; no automatic
  source-fetching; no new entity types; no daemon mode; no multi-source
  ingest) — verified by the code-reviewer at 017.09 final gate. Any bead
  that smuggles in a non-R15 feature does NOT merge.
- TASK 016 surface (promote/demote, two-tier model, root-aware upsert)
  preserved by `tests/test_e2e_promotion.py` regression (gate §6.3).
- Single-course byte-identity: 017-05/06 must verify on
  `tests/fixtures/` single-course fixtures that `wiki-ingest ingest`
  without `--vault-id` produces a manifest with `vault_id: null`,
  `course: null`, `scope: "course"` for every `written[]` entry — NO
  exit 23/24/25 paths fired.

---

## 10. Deliverables checklist (Planner → Developer handoff)

- [ ] 10 task files under `docs/tasks/task-017-*.md` (one per bead).
- [ ] Each task file: Goal, Use-Case link, Changes (new files + edits
      with method-level granularity), Test Cases (E2E + Unit +
      Regression), Acceptance Criteria.
- [ ] Bead order respects Arch-M-1 (reference before orchestrator) and
      Arch-M-2 (dispatch before orchestrator).
- [ ] Helper substrate (017-00..017-03) lands before the orchestrator
      (017-05+).
- [ ] Final bead (017-09) gates the merge with validators + cross-skill
      `diff -q` matrix.
- [ ] No bead introduces a non-R15 feature (no new LLM patterns, no
      three-tier vault, no automatic fetching, no new entity types, no
      daemon, no multi-source).
- [ ] Every bead's verifies-section runs `tests/test_architecture.py`
      AND the TASK 015/016 regression suite.

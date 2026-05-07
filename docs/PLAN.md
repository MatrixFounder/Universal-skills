# Development Plan: Task 002 — `xlsx_add_comment.py` Module Split

> **Source documents:**
> - [`docs/TASK.md`](TASK.md) — Task 002, draft v2 APPROVED.
> - [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — §3.2 (9-file package), §8 (Q1=A / Q2=A / Q3=helpers).
> - [`docs/reviews/task-002-review.md`](reviews/task-002-review.md) — task + architecture review trail.
>
> **Stub-First adaptation for refactor:** This is a structural-only
> change with TASK R8 locking "no behaviour change". The classical
> Stub-First "Red→Green" cycle does not apply because the
> implementation already exists. The adapted cycle is **Green→Green**:
> each task moves code byte-equivalent, re-runs the existing
> 75 unit + 112 E2E suite, and confirms the green state is
> preserved. The Stage-0 baseline capture (Task 002.1) is the
> regression-anchor; every later task's verification is "delta vs
> Stage-0 baseline = 0".
>
> **Predecessor PLAN.md** (Task 001 / xlsx-6) is preserved in the git
> history of this file; it is superseded in full by this document.
> Per-step task files for Task 001 remain at
> `docs/tasks/task-001-NN-*.md` for historical reference.

## Task Execution Sequence

### Stage 0: Pre-refactor evidence capture (regression anchor)

- **Task 002.1** — Capture baseline: E2E count, unit count, `--help` output, golden hashes, canonical 35-symbol grep
  - RTM coverage: **R3.a, R3.b, R3.d, R7.b, R7.c, NFR perf**
  - Description File: [`docs/tasks/task-002-01-baseline.md`](tasks/task-002-01-baseline.md)
  - Priority: Critical
  - Dependencies: none

### Stage 1: Package skeleton + leaf modules (zero internal deps)

- **Task 002.2** — Create `xlsx_comment/` package skeleton (empty stubs for all 9 modules + `__init__.py`)
  - RTM coverage: **R1.a**
  - Description File: [`docs/tasks/task-002-02-skeleton.md`](tasks/task-002-02-skeleton.md)
  - Priority: Critical
  - Dependencies: Task 002.1

- **Task 002.3** — Migrate `constants.py` and `exceptions.py` (the two zero-dep leaves) + first shim re-exports
  - RTM coverage: **R1.b, R1.c, R4.a, R4.c, R7.c**
  - Description File: [`docs/tasks/task-002-03-leaf-moves.md`](tasks/task-002-03-leaf-moves.md)
  - Priority: Critical
  - Dependencies: Task 002.2

### Stage 2: Independent feature modules (depend on leaves only)

- **Task 002.4** — Migrate `cell_parser.py` (F2)
  - RTM coverage: **R1.d, R4.b**
  - Description File: [`docs/tasks/task-002-04-cell-parser.md`](tasks/task-002-04-cell-parser.md)
  - Priority: High
  - Dependencies: Task 002.3

- **Task 002.5** — Migrate `batch.py` (F3)
  - RTM coverage: **R1.e, R4.b**
  - Description File: [`docs/tasks/task-002-05-batch.md`](tasks/task-002-05-batch.md)
  - Priority: High
  - Dependencies: Task 002.3

### Stage 3: The heavy module — OOXML editor (largest single move)

- **Task 002.6** — Migrate `ooxml_editor.py` (F4, ~776 LOC, single-file per Q1=A)
  - RTM coverage: **R1.f, R4.b, R7.c (verbatim move incl. `_VML_PARSER` security boundary)**
  - Description File: [`docs/tasks/task-002-06-ooxml-editor.md`](tasks/task-002-06-ooxml-editor.md)
  - Priority: High
  - Dependencies: Task 002.3

### Stage 4: Logic modules that depend on F4

- **Task 002.7** — Migrate `merge_dup.py` (F5)
  - RTM coverage: **R1.g, R4.b**
  - Description File: [`docs/tasks/task-002-07-merge-dup.md`](tasks/task-002-07-merge-dup.md)
  - Priority: High
  - Dependencies: Task 002.6

### Stage 5: CLI surface — orchestrator merges + shim reduction

- **Task 002.8** — Migrate `cli_helpers.py` (F-Helpers + Q3=helpers move of `_post_pack_validate`/`_post_validate_enabled`)
  - RTM coverage: **R1.h, R4.b**
  - Description File: [`docs/tasks/task-002-08-cli-helpers.md`](tasks/task-002-08-cli-helpers.md)
  - Priority: High
  - Dependencies: Task 002.7

- **Task 002.9** — Migrate `cli.py` (F1+F6 merged per Q2=A) AND reduce `xlsx_add_comment.py` to ≤200 LOC shim with full 35-symbol re-export contract
  - RTM coverage: **R1.i, R1.j, R2.a, R2.b, R2.c, R2.d, R4.b**
  - Description File: [`docs/tasks/task-002-09-cli-and-shim.md`](tasks/task-002-09-cli-and-shim.md)
  - Priority: Critical
  - Dependencies: Task 002.8

### Stage 6: Verification, locks, and documentation

- **Task 002.10** — Add honest-scope regression test + import-graph smoke test + delta-vs-baseline verification
  - RTM coverage: **R3.a, R3.b, R3.c, R3.d, R7.a, R7.d, R8.a, NFR perf**
  - Description File: [`docs/tasks/task-002-10-honest-scope-tests.md`](tasks/task-002-10-honest-scope-tests.md)
  - Priority: Critical
  - Dependencies: Task 002.9

- **Task 002.11** — Update `.AGENTS.md`, `references/comments-and-threads.md` §6, run `validate_skill.py`, `office/` byte-identity gate
  - RTM coverage: **R5.a, R5.b, R5.c, R5.d, R6.a, R6.b, R6.c, R6.d, R6.e, R8.b, R8.c, R8.d, R8.e**
  - Description File: [`docs/tasks/task-002-11-docs-and-validation.md`](tasks/task-002-11-docs-and-validation.md)
  - Priority: Critical
  - Dependencies: Task 002.10

## RTM Coverage Map

> **Per planner-prompt §4 Step 2 RTM Linking:** every TASK.md RTM
> sub-feature is mapped to **exactly one** planning task that delivers
> it (or to a small set of tasks where the sub-feature is genuinely
> distributed — e.g. R5.a "each new module gets a docstring" lives in
> every migration task and the final polish pass). Multiple sub-features
> under a single task are listed individually below; no feature-grouping.

| RTM ID | Sub-feature | PLAN Task |
|---|---|---|
| R1.a | Create `xlsx_comment/` package directory + `__init__.py` | 002.2 |
| R1.b | Migrate F-Constants → `constants.py` | 002.3 |
| R1.c | Migrate F-Errors → `exceptions.py` | 002.3 |
| R1.d | Migrate F2 → `cell_parser.py` | 002.4 |
| R1.e | Migrate F3 → `batch.py` | 002.5 |
| R1.f | Migrate F4 → `ooxml_editor.py` (single-file per Q1=A) | 002.6 |
| R1.g | Migrate F5 → `merge_dup.py` | 002.7 |
| R1.h | Migrate F-Helpers → `cli_helpers.py` (incl. Q3 move) | 002.8 |
| R1.i | Migrate F1 → `cli.py` (build_parser) | 002.9 |
| R1.j | Migrate F6 → `cli.py` (main / single_cell_main / batch_main, merged per Q2=A) | 002.9 |
| R2.a | Reduce shim to ≤200 LOC | 002.9 |
| R2.b | Shim re-exports 35-symbol test-compat surface | 002.9 |
| R2.c | Migrate shim docstring to `xlsx_comment/__init__.py` (or near-empty) | 002.9 |
| R2.d | Shim retains shebang + executable bit | 002.9 |
| R3.a | 75 unit tests pass with zero edits | 002.1 (baseline), 002.10 (delta=0 lock) |
| R3.b | 112 E2E checks pass | 002.1 (baseline), 002.10 (delta=0 lock) |
| R3.c | E2E with `XLSX_ADD_COMMENT_POST_VALIDATE=1` passes | 002.10 |
| R3.d | Goldens bit-equal OR `_golden_diff.py` zero structural delta | 002.1 (hash baseline), 002.10 (delta=0 lock) |
| R4.a | Each module declares `__all__` | 002.3 (constants/exceptions), 002.4..002.9 (per module) |
| R4.b | Cross-module imports use sibling-relative form, NOT shim | 002.3..002.9 (per migration) |
| R4.c | `_AppError` + 14 typed errors live in `exceptions.py` | 002.3 |
| R4.d | Module-private helpers keep `_` prefix; not in `__all__` | 002.3..002.9 (per module) |
| R5.a | Each new module gets a top-of-file docstring (≤30 LOC) | 002.3..002.9 (per module) + final pass 002.11 |
| R5.b | Update `skills/xlsx/scripts/.AGENTS.md` | 002.11 |
| R5.c | `skills/xlsx/SKILL.md` does NOT change (verification only) | 002.11 |
| R5.d | Append §6 "Internal module map" to `references/comments-and-threads.md` | 002.11 |
| R6.a | `validate_skill.py skills/xlsx` exits 0 | 002.11 |
| R6.b | `git status` shows only expected file moves + new package | 002.11 |
| R6.c | No new dependencies in `requirements.txt` | 002.11 |
| R6.d | `__pycache__` cleaned before commit | 002.11 |
| R6.e | `office/` byte-identical across all 4 office skills (`diff -qr`) | 002.11 |
| R7.a | Single self-contained PR / chain — no half-states on `main` | 002.10 |
| R7.b | `git diff main..HEAD --stat` shows clean file moves only | 002.1 (capture pre-state), 002.10 (verify delta) |
| R7.c | Migrated code is byte-equivalent (no re-indent / re-flow / re-name) | 002.3..002.9 (per migration with verbatim-move discipline) |
| R7.d | Each module move has a unit-level smoke test for import | 002.10 (`tests/test_xlsx_comment_imports.py`) |
| R8.a | No behaviour change; logic-bugs reproduced verbatim with `# XXX(task-002):` | 002.3..002.9 (per migration) + 002.10 (lock) |
| R8.b | `office/` is untouched | 002.11 (`diff -qr` gate) |
| R8.c | `_errors.py` / `preview.py` / `office_passwd.py` untouched | 002.11 (`diff -q` gate) |
| R8.d | `docx_add_comment.py` and `pptx_*` untouched | 002.11 (git status review) |
| R8.e | v2 follow-ups (R9.f, R9.g, parentId, rich text) explicitly out of scope | 002.10 (honest-scope test) |

## Stub-First Phasing Note (Adapted for Refactor)

| Classical Stub-First | This refactor's adaptation |
|---|---|
| **Phase 1: Stubs + E2E (Red→Green)** — write failing E2E, then stub the API, then make E2E pass against stubbed values. | **Phase 1 (Tasks 002.1–002.2): Skeleton + baseline capture.** Empty package stubs are created (Task 002.2) and pre-refactor green state is captured (Task 002.1). Tests still pass against the **unchanged** `xlsx_add_comment.py` because the new package is unused. This is the analog of "stubs do not change observable behaviour". |
| **Phase 2: Logic Implementation (Mock replacement)** — replace stubs with real logic, update E2E. | **Phase 2 (Tasks 002.3–002.9): Code migration.** Each task moves one F-region from `xlsx_add_comment.py` to its target module byte-equivalent and updates the shim re-exports. The "logic" doesn't change — what changes is **where the logic lives**. After every task, the test suite must remain green. |
| **Phase 3: Verification + Documentation.** | **Phase 3 (Tasks 002.10–002.11): Honest-scope locks + docs.** New regression tests lock in the post-refactor structure (shim ≤200 LOC, importable surface, `office/` non-touch). `.AGENTS.md` and `references/comments-and-threads.md` updated. |

The adapted phasing is **stricter** than classical Stub-First because every intermediate task (002.3–002.9) must keep all existing tests green — there is no "tests fail until logic ships" intermediate state.

## Execution discipline (per migration task)

Tasks 002.3–002.9 follow this micro-cycle. Each `task-002-NN-*.md` references this section instead of repeating it.

1. **Read** the source region in `xlsx_add_comment.py` (using `# region — F<N>` markers as boundaries). **n1 from plan-review:** the per-task line-number ranges (e.g. "lines 140–178") are correct as of the Task 001 final state but may drift if any earlier task in the chain edits the file. The canonical boundary is the `# region —` / `# endregion` marker pair, NOT the line numbers. If line numbers and markers disagree, **trust the markers**.
2. **Move** the code byte-equivalent into the target module:
   - Preserve indentation, comments, blank lines.
   - Convert `# region — …` opener into a module docstring.
   - Drop the `# endregion` marker.
   - Do NOT auto-format with black/ruff/isort during the move.
3. **Replace** the deleted region in `xlsx_add_comment.py` with a re-import (`from xlsx_comment.<module> import …`) covering the test-compat surface for that module.
4. **Update** internal cross-references inside the package: replace any `from <symbol>` style intra-module references that broke with sibling-relative imports (`from .exceptions import _AppError`).
5. **Run** `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests`.
6. **Run** `bash skills/xlsx/scripts/tests/test_e2e.sh`.
7. **If both green → commit; if any red → revert and investigate**. Do NOT advance to the next task with red tests.

## Use Case Coverage

| Use Case | Tasks |
|---|---|
| I1 (package skeleton) | 002.2 |
| I2 (constants + exceptions) | 002.3 |
| I3 (cell_parser) | 002.4 |
| I4 (batch) | 002.5 |
| I5 (ooxml_editor — largest move) | 002.6 |
| I6 (merge_dup) | 002.7 |
| I7 (cli_helpers) | 002.8 |
| I8 (cli + shim reduction) | 002.9 |
| I9 (test-suite full-pass evidence) | 002.1 (baseline), 002.10 (delta) |
| I10 (validator + clean-tree gate) | 002.11 |
| I11 (`.AGENTS.md` update) | 002.11 |
| I12 (locked non-goals as regression tests) | 002.10 |

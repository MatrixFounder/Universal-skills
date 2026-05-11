# Development Plan: Task 004 — `json2xlsx.py` (xlsx-2)

> **Source documents:**
> - [`docs/TASK.md`](TASK.md) — Task 004, draft v2 APPROVED (`docs/reviews/task-004-review.md`).
> - [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — F1–F8 / 7-module shim+package layout APPROVED (`docs/reviews/task-004-architecture-review.md`).
> - **Predecessor PLAN.md** (Task 003 / xlsx-7) archived at [`docs/plans/plan-002-xlsx-check-rules.md`](plans/plan-002-xlsx-check-rules.md).
> - **Predecessor PLAN.md** (Task 002 / xlsx-6 modular refactor) archived at [`docs/plans/plan-001-xlsx-add-comment-modular.md`](plans/plan-001-xlsx-add-comment-modular.md).
>
> **D5 closure (delivery shape):** **9 sub-tasks** — within the
> 8–12 envelope locked in TASK §0 D5. Order: 3 scaffolding tasks
> (Stage 0, Phase-1 Red→Green over stubs) then 5 logic tasks
> (Stage 1, Phase-2 Bead-by-Bead) then 1 finalization task
> (Stage 2 — docs, contract spec, validator gate).
>
> **Total LOC budget (architect-locked, ARCH §3.2):** ≤ 1 220 LOC
> across `json2xlsx.py` shim (≤ 220) + 7 package modules
> (≤ 30 + ≤ 200 + ≤ 220 + ≤ 220 + ≤ 100 + ≤ 80 + ≤ 320). Tests
> add ≈ 800 LOC (600 unit + 200 E2E append). Total deliverable
> ≈ 2 020 LOC including tests + ~ 250 LOC references/json-shapes.md
> + small fixtures.
>
> **Stub-First applies in canonical Red → Green → Refactor form**
> (this is a NEW component, not a refactor):
>
> - **Phase 1 (Tasks 004.01 – 004.03)** — Skeleton + test scaffolding
>   + cross-cutting glue (exceptions, envelope wiring, same-path
>   guard). Stubs `raise NotImplementedError("xlsx-2 stub — task-004-NN")`;
>   E2E + unit tests fail uniformly. CI is **expected red** for the
>   subset of E2E cases that exercise stubs; envelope / argparse / `--help` /
>   same-path-guard tests turn green at the end of Phase 1.
> - **Phase 2 (Tasks 004.04 – 004.08)** — Per-F-region implementation
>   in dependency order: loaders (F1+F2) → coerce (F3) → writer (F4)
>   → CLI orchestrator (F5+F7) → post-validate hook (F6 logic) + E2E
>   completion. Each task turns its slice of unit + E2E fixtures green.
> - **Phase 3 (Task 004.09)** — `references/json-shapes.md` contract
>   freeze + SKILL.md + `.AGENTS.md` + backlog mark ✅ DONE +
>   `validate_skill.py` gate + cross-skill replication diff gate +
>   perf-test wiring (opt-in `RUN_PERF_TESTS=1`).

## Task Execution Sequence

### Stage 0 — Scaffolding (Phase 1: tests must fail with `NotImplementedError`)

- **Task 004.01** — Package skeleton: 7 stub modules + ≤220-LOC shim + placeholder `.AGENTS.md` block + `validate_skill.py` green (boundary day-1 gate)
  - **RTM coverage:** **R13.a, R13.b, R13.c** (validator gate, byte-identity invariant, importable structure); **R12.c** (`.AGENTS.md` placeholder)
  - **Description:** [`docs/tasks/task-004-01-skeleton.md`](tasks/task-004-01-skeleton.md)
  - **Closes AQ-4** (locks `convert_json_to_xlsx` as public-helper symbol — no namespace collision with future xlsx-8 `convert_xlsx_to_json`)
  - **Priority:** Critical · **Dependencies:** none

- **Task 004.02** — E2E test scaffolding (≥ 10 named cases) + unit-test scaffolding (≥ 25 cases) + synthetic xlsx-8 round-trip fixture pin + style-constant drift assertion
  - **RTM coverage:** **R11.a, R11.b, R11.c, R11.d**
  - **Description:** [`docs/tasks/task-004-02-test-scaffolding.md`](tasks/task-004-02-test-scaffolding.md)
  - **Closes AQ-1** (drift-detection mechanism: `sys.path` injection + `csv2xlsx.HEADER_FILL.fgColor.rgb in ("F2F2F2", "00F2F2F2")` accept-both literal/normalised form)
  - **Closes AQ-5** (`@unittest.skipUnless(_xlsx2json_available(), …)` for `T-roundtrip-xlsx8-live`)
  - **Priority:** Critical · **Dependencies:** 004.01

- **Task 004.03** — Exceptions module (9 typed `_AppError` subclasses, plain `Exception` subclass model per ARCH m1 fix) + cross-cutting helpers (cross-5 envelope wiring, cross-7 H1 same-path guard, stdin-utf8 reader, post-validate enable-check)
  - **RTM coverage:** **R8.a, R8.b, R8.c, R8.d, R10.a, R10.d**
  - **Description:** [`docs/tasks/task-004-03-exceptions-cross-cutting.md`](tasks/task-004-03-exceptions-cross-cutting.md)
  - **Priority:** Critical · **Dependencies:** 004.01

### Stage 1 — Logic Implementation (Phase 2: Bead-by-Bead, per F-region)

- **Task 004.04** — `loaders.py` (F1 + F2): `read_input`, `detect_and_parse`, `_parse_jsonl`, `_dispatch_root`, `_validate_multi_sheet`. **First fixtures turn green** (UC-1 happy, UC-2 happy, UC-3 happy, UC-1 A5 JsonDecodeError, UC-1 A3 NoRowsToWrite, UC-2 A1 InvalidSheetName routing).
  - **RTM coverage:** **R1.a, R1.b, R1.c, R1.d, R1.e, R2.a, R2.b, R2.c, R2.d, R2.e, R2.f**
  - **Description:** [`docs/tasks/task-004-04-loaders.md`](tasks/task-004-04-loaders.md)
  - **Priority:** Critical · **Dependencies:** 004.03

- **Task 004.05** — `coerce.py` (F3): `coerce_cell`, `_try_iso_date`, `_try_iso_datetime`, `_handle_aware_tz`, `CellPayload`, `CoerceOptions` dataclasses. Implements D2 default-on date coercion + D7 strict-dates rejection. **Type-preservation fixtures turn green.**
  - **RTM coverage:** **R3.a, R3.b, R3.c, R3.d, R3.e, R3.f, R4.a, R4.b, R4.c, R4.d, R4.e, R4.f, R4.g, R5.a, R5.b, R5.c, R5.d**
  - **Description:** [`docs/tasks/task-004-05-coerce.md`](tasks/task-004-05-coerce.md)
  - **Priority:** Critical · **Dependencies:** 004.04 (so `ParsedInput` exists)

- **Task 004.06** — `writer.py` (F4): `write_workbook`, `_build_sheet`, `_union_headers`, `_style_header_row`, `_size_columns`, `_validate_sheet_name`. Style constants copied from `csv2xlsx.py` with `# Mirrors csv2xlsx.py — keep visually identical.` comment. **Styling + multi-sheet + sheet-name-validation fixtures turn green.**
  - **RTM coverage:** **R5.a, R5.b, R6.a-g, R7.a, R7.b, R7.c, R7.d**
  - **Description:** [`docs/tasks/task-004-06-writer.md`](tasks/task-004-06-writer.md)
  - **Priority:** Critical · **Dependencies:** 004.05

- **Task 004.07** — `cli.py` (F5 + F7): `build_parser`, `main`, `_run`. Wires all 8 R9 flags; top-of-`_run` `_AppError` → cross-5 envelope catch (AQ-3); `--help` text includes JSONL auto-detection rule (AQ-2). LOC budget ≤ 320 (ARCH M2). **CLI-surface + envelope + happy-path E2E fixtures turn green.**
  - **RTM coverage:** **R8.a (orchestration of envelope), R9.a-h**
  - **Description:** [`docs/tasks/task-004-07-cli-orchestrator.md`](tasks/task-004-07-cli-orchestrator.md)
  - **Closes AQ-2** (`--help` description text)
  - **Closes AQ-3** (top-of-`_run` catch)
  - **Priority:** Critical · **Dependencies:** 004.06

- **Task 004.08** — Post-validate hook logic + synthetic xlsx-8 round-trip green + remaining E2E cases green. `cli_helpers.run_post_validate` (subprocess invocation of `office/validators/xlsx.py`); wire into `_run`; finalize `T-roundtrip-xlsx8` (synthetic JSON → workbook → assert structure); cleanup-on-failure unlink. **All Stage-0 E2E cases now green.**
  - **RTM coverage:** **R10.a, R10.b, R10.c, R10.d** (logic — stub was 004.03); **R11.b, R11.c** (E2E completion)
  - **Description:** [`docs/tasks/task-004-08-post-validate-e2e-green.md`](tasks/task-004-08-post-validate-e2e-green.md)
  - **Priority:** High · **Dependencies:** 004.07

### Stage 2 — Finalization (Phase 3: docs, contract, gates, ✅ DONE)

- **Task 004.09** — `references/json-shapes.md` (round-trip contract freeze; closes DoD §7 m1 + ARCH §3.2 m4 lock) + SKILL.md update (§1 Red Flags + §2 Capabilities) + `scripts/.AGENTS.md` final block + backlog row marked ✅ DONE with status line + perf-test wiring under `RUN_PERF_TESTS=1` (no CI gate) + cross-skill `diff -q` × 11 invocations green + `validate_skill.py skills/xlsx` exit 0
  - **RTM coverage:** **R11.e (perf), R12.a, R12.b, R12.c, R12.d, R12.e, R13.a, R13.b, R13.c, R13.d**
  - **Description:** [`docs/tasks/task-004-09-final-docs-and-contract.md`](tasks/task-004-09-final-docs-and-contract.md)
  - **Priority:** High · **Dependencies:** 004.08

## RTM Coverage Matrix

| RTM Row | Sub-feature scope | Closing task(s) |
| :---: | :--- | :---: |
| **R1** | Read JSON from file path / stdin / `-encoding` / empty-input / invalid-JSON | 004.04 |
| **R2** | Shape detection (`.jsonl` ext / root token dispatch / empty array) | 004.04 |
| **R3** | Preserve native JSON types (int/float/bool/null/str + mixed-column rule) | 004.05 |
| **R4** | ISO-8601 date coercion (default-on, `--no-date-coerce`, `--date-format`, `--strict-dates`) | 004.05 (logic) + 004.07 (CLI flag wiring + envelope landing for R4.g) |
| **R5** | Schema heterogeneity → union keys (first-seen order, missing → empty cell) | 004.05 (header union logic) + 004.06 (sheet write) |
| **R6** | Output styling (bold header, fill, freeze, auto-filter, column widths) | 004.06 |
| **R7** | Multi-sheet write (sheet names, `--sheet` override behaviour) | 004.06 |
| **R8** | Cross-cutting (cross-5 envelope, cross-7 H1 same-path, stdin `-`) | 004.03 (helpers + exceptions) + 004.07 (CLI wiring) |
| **R9** | CLI argparse surface (8 flags, `--help`) | 004.07 |
| **R10** | Post-validate hook (`XLSX_JSON2XLSX_POST_VALIDATE=1`) | 004.03 (stub + enable-check) + 004.08 (logic + **11 E2E cases green + 1 dedicated post-validate unit test for the cleanup path** — full-E2E coverage of bad-workbook path is infeasible because xlsx-2 emits structurally valid workbooks; monkeypatch unit test is the honest substitute) |
| **R11** | Tests (unit ≥ 25, E2E ≥ 11, T-roundtrip-xlsx8 synthetic, **10K-row perf opt-in only — 100K-row JSONL budget DROPPED from v1 per honest-scope §11.3 / O4 deferral**) | 004.02 (scaffolding) + 004.08 (logic green) + 004.09 (10K perf) |
| **R12** | Docs (SKILL.md §1 + §2, `.AGENTS.md`, examples/, backlog row) | 004.01 (R12.c `.AGENTS.md` placeholder) + 004.09 (R12.a/b/c/d/e full) |
| **R13** | Validator + invariants (`validate_skill.py`, byte-identity, unit pass, E2E pass) | 004.01 (validator gate day-1) + 004.09 (final gate) |

## Use Case Coverage

| Use Case | Closing task(s) |
| :--- | :--- |
| UC-1 — LLM-emitted array-of-objects → workbook | 004.04 (parse) + 004.05 (coerce) + 004.06 (write) + 004.07 (CLI) |
| UC-2 — Multi-sheet dict → multi-sheet workbook | 004.04 (multi-sheet dispatch) + 004.06 (multi-sheet write) |
| UC-3 — JSONL streaming input | 004.04 (`_parse_jsonl`) |
| UC-4 — Stdin pipe with envelope error | 004.03 (envelope) + 004.07 (CLI `-` handling) |
| UC-5 — xlsx-8 round-trip (synthetic) | 004.02 (fixture pin) + 004.08 (synthetic green) + 004.09 (contract spec) |

## Open-Question Closure Trail

| Question (source) | Closing task | Resolution lock |
| :--- | :---: | :--- |
| AQ-1 — drift-detection mechanism | 004.02 | `sys.path` injection + 6/8-char ARGB accept-both literal |
| AQ-2 — `--help` JSONL auto-detect text | 004.07 | Brief mention in `input` positional + full rule in module docstring |
| AQ-3 — `_run` top-level catch | 004.07 | Single `except _AppError as exc: return _emit_envelope(...)` at the top of `_run` (xlsx-7 pattern) |
| AQ-4 — public helper symbol naming | 004.01 | `convert_json_to_xlsx` in `json2xlsx/__init__.py` (verbose-unambiguous; xlsx-8 will get `convert_xlsx_to_json`) |
| AQ-5 — round-trip-live skip pattern | 004.02 | `@unittest.skipUnless(_xlsx2json_available(), "xlsx-8 not landed yet")` |
| O1 — round-trip test ownership | 004.09 | xlsx-2 owns the contract; xlsx-8 commit adds the live test wiring in `tests/test_json2xlsx.py`; xlsx-2 does NOT change |

## Platform-IO Errors (envelope-only, NOT typed `_AppError`)

The 9 typed `_AppError` subclasses cover xlsx-2's logical error
taxonomy (empty input, unsupported shape, sheet-name violations,
post-validate failure, etc.). Platform-IO failures
(`FileNotFoundError`, generic `OSError` on read/write) are
**deliberately NOT** added to the taxonomy — they're caught at the
CLI layer in `_run` and surfaced via direct
`report_error(message, code=1, error_type="FileNotFound" | "IOError",
details={"path": …})` calls. This is intentional design per
TASK §10 / 004.04 task notes — platform errors are best surfaced
via free-form message rather than a synthetic typed-error class
that would just wrap `str(exc)`. Plan-reviewer #10 nit.

## Phase-Boundary Gates

Between each task, the orchestrator MUST verify:

1. **Validator gate:** `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0.
2. **Byte-identity gate (after every commit):** eleven `diff -q` invocations from ARCH §9 silent.
3. **Test gate:** `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests` exits 0; `bash skills/xlsx/scripts/tests/test_e2e.sh` exits 0.
4. **Session-state persistence:** `update_state.py` invoked at each task boundary (mode `VDD-Develop`, task `Task-004-json2xlsx`, status `Task-NN-Done`).

## Honest-Scope Carry-Forward (TASK §11 + ARCH §10)

The following limitations are **deliberately accepted in v1**. The
chain MUST NOT silently widen scope to close them. If implementation
work surfaces a limitation as blocking, **stop and escalate** — open
a new TASK Open Question or a v2 backlog row (`xlsx-2a`, `xlsx-2b`, …):

- Aware datetime → naive UTC under default (TASK §11.1 / R4.e). Under `--strict-dates`: hard-fail (D7 / R4.g).
- Leading `=` in JSON string values passes through to Excel (TASK §11.2 / C7). v2 joint fix with csv2xlsx (O6).
- 100K-row write-only mode deferred (TASK §11.3 / ARCH A1 / O4).
- Sheet-name auto-sanitization NOT in v1 (TASK §11.4 / R7.b).
- Duplicate top-level JSON keys collapsed by `json.loads()` (TASK §11.5 / UC-2 A2 / R7.c).
- TOCTOU on the same-path guard (TASK §11.6 / R8.b).
- Cell-value `=cmd|...` injection (TASK §11.7).
- No `--output -` (ARCH A2). No string truncation (ARCH A3). No format-inference for `"42.5%"` (ARCH A4). No `--split-sheets` (ARCH A5).

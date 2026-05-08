# Development Plan: Task 003 — `xlsx_check_rules.py` (xlsx-7)

> **Source documents:**
> - [`docs/TASK.md`](TASK.md) — Task 003, draft v2 APPROVED (`docs/reviews/task-003-review.md`).
> - [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — F1–F11 / 12-module shim+package layout APPROVED (`docs/reviews/architecture-003-review.md`).
> - [`skills/xlsx/references/xlsx-rules-format.md`](../skills/xlsx/references/xlsx-rules-format.md) — frozen SPEC contract.
> - **Predecessor PLAN.md** (Task 002 / xlsx-6 modular refactor) preserved at [`docs/plans/plan-001-xlsx-add-comment-modular.md`](plans/plan-001-xlsx-add-comment-modular.md).
>
> **D1 closure (delivery shape):** 20 sub-tasks per Q&A 2026-05-08. Initial draft was 17; plan-reviewer round-1 (`docs/reviews/plan-003-review.md`) applied **M-1/M-2/M-3 atomicity splits** — 003.04 → 003.04a + 003.04b; 003.14 → 003.14a + 003.14b; 003.16 → 003.16a + 003.16b. Final chain length is 20.
>
> **Total LOC budget (M-3 architect-locked):** ≤ 3560 LOC across the `xlsx_check_rules/` package (12 files; per-module caps in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) §3.2). +27 % over the 2200–2800 LOC point-estimate as engineering buffer for the hand-written DSL parser and Excel-Tables resolver.
>
> **Stub-First applies in canonical Red→Green→Refactor form** (this is a NEW system, not a refactor):
>
> - **Phase 1 (Tasks 003.01–003.04)** — Skeleton + test scaffolding. Stubs `raise NotImplementedError`; E2E + battery tests fail loudly and uniformly. CI is **expected red** during this phase. The deliverable is "all tests fail with 'NotImplementedError' (NOT TypeError / ImportError / SyntaxError)".
> - **Phase 2 (Tasks 003.05–003.15)** — Per-F-region implementation. Each task replaces one F's stubs with real logic and turns its slice of fixtures green. Tasks are ordered by dependency (constants → exceptions → ast → cell_types/scope → loader/parser → evaluator/aggregates → output → cli → remarks).
> - **Phase 3 (Tasks 003.16–003.17)** — Cross-skill integration (xlsx-6 envelope #39/#39a/#39b), perf fixture #31 (gated `RUN_PERF_TESTS=1`), 10 canary saboteurs functional, SPEC patch (D4 § 5.0), SKILL.md / `.AGENTS.md` / `examples/` / `THIRD_PARTY_NOTICES.md` updated, `validate_skill.py` green.

## Task Execution Sequence

### Stage 0 — Scaffolding (tests must fail with `NotImplementedError`)

- **Task 003.01** — Package skeleton: 12 stub modules + ≤200-LOC shim + `requirements.txt` deps + draft `THIRD_PARTY_NOTICES.md` entries
  - RTM coverage: **R1.h, R5 (envelope schema only), R6 (exit codes only), R14.b (`.AGENTS.md` placeholder)**, plus dep deltas (TASK §5)
  - Description: [`docs/tasks/task-003-01-skeleton.md`](tasks/task-003-01-skeleton.md)
  - Priority: Critical · Dependencies: none

- **Task 003.02** — E2E harness + battery driver scaffolding (red-state)
  - RTM coverage: **R12.a (battery driver shape), R5 (envelope shape only)**
  - Description: [`docs/tasks/task-003-02-e2e-scaffolding.md`](tasks/task-003-02-e2e-scaffolding.md)
  - Priority: Critical · Dependencies: 003.01

- **Task 003.03** — Unit-test scaffolding + fixture-generator skeleton (`_generate.py` declarative-manifest reader)
  - RTM coverage: **R12.a (manifest schema)**
  - Description: [`docs/tasks/task-003-03-unit-scaffolding.md`](tasks/task-003-03-unit-scaffolding.md)
  - Priority: Critical · Dependencies: 003.01

- **Task 003.04a** — Manifest schema + generator core + 10 happy-path fixtures (#1–#9 + #10b D4 anchor) [plan-review M-1 split]
  - RTM coverage: **R12.a partial (manifest schema + first 10 fixtures)**
  - Description: [`docs/tasks/task-003-04a-fixture-manifests-core.md`](tasks/task-003-04a-fixture-manifests-core.md)
  - Priority: Critical · Dependencies: 003.03

- **Task 003.04b** — Adversarial / cross-sheet / output / honest-scope manifests (32 fixtures: #10/#11–#21 type-edges, #22–#30 adversarial, #32a/b/c streaming-incompat, #33–#38 output, #39/#39a/#39b M2) [plan-review M-1 split — runs in parallel to 003.05–003.07]
  - RTM coverage: **R12.a (full inventory: 42 fixtures)**, **R13.l (manifest slots only; tests in 003.17)**
  - Description: [`docs/tasks/task-003-04b-fixture-manifests-extended.md`](tasks/task-003-04b-fixture-manifests-extended.md)
  - Priority: High · Dependencies: 003.04a (schema + generator)

### Stage 1 — Foundations (Phase 2 begins; tests start turning green)

- **Task 003.05** — `constants.py` + `exceptions.py` (F-Constants + F-Errors; full 16-typed exception tree, OPENPYXL_ERROR_CODES per D4, REDOS_REJECT_PATTERNS per D5)
  - RTM coverage: **R1.h (constants), R6.d (envelope wiring), R13 (D4/D5 enforcement points)**
  - Description: [`docs/tasks/task-003-05-constants-exceptions.md`](tasks/task-003-05-constants-exceptions.md)
  - Priority: Critical · Dependencies: 003.04a

- **Task 003.06** — `ast_nodes.py` (F4: 17 dataclass node types + `RuleSpec` + `to_canonical_str` for §5.5.3 cache-key normalisation)
  - RTM coverage: **R1.e (closed AST whitelist), R10.a (cache canonical-key normalisation)**
  - Description: [`docs/tasks/task-003-06-ast-nodes.md`](tasks/task-003-06-ast-nodes.md)
  - Priority: Critical · Dependencies: 003.05

### Stage 2 — Workbook view

- **Task 003.07** — `cell_types.py` (F5: 6 logical types, D4 7-code subset, Decimal→float, whitespace strip, dateutil text parsing)
  - RTM coverage: **R2.a, R2.b, R2.c, R2.d, R2.e (D4 partial), R4.d (text/date paths)**
  - Description: [`docs/tasks/task-003-07-cell-types.md`](tasks/task-003-07-cell-types.md)
  - Priority: Critical · Dependencies: 003.06

- **Task 003.08** — `scope_resolver.py` (F6: 10 scope forms, sheet qualifier, header semantics + Excel-Tables fallback, merged-cell anchor logic, hidden-row/col filter)
  - RTM coverage: **R3.a, R3.b, R3.c, R3.d, R3.e, R3.f, R3.g**
  - Description: [`docs/tasks/task-003-08-scope-resolver.md`](tasks/task-003-08-scope-resolver.md)
  - Priority: Critical · Dependencies: 003.07

### Stage 3 — Rule loading & DSL parsing

- **Task 003.09** — `rules_loader.py` (F2: JSON + ruamel.yaml hardened — alias / custom-tag / dup-key reject; 1 MiB pre-parse cap; Q7 hard `version: 1` exit 2)
  - RTM coverage: **R1.a, R1.b, R1.c, R1.h, R9.f (size cap)**
  - Description: [`docs/tasks/task-003-09-rules-loader.md`](tasks/task-003-09-rules-loader.md)
  - Priority: Critical · Dependencies: 003.05

- **Task 003.10** — `dsl_parser.py` (F3: hand-written recursive-descent over §5 grammar; closed 17-AST-node whitelist; composite depth cap 16; builtin whitelist; D5 4-shape ReDoS lint)
  - RTM coverage: **R1.d, R1.e, R1.f, R1.g, R9.a, R9.b, R9.c**
  - Description: [`docs/tasks/task-003-10-dsl-parser.md`](tasks/task-003-10-dsl-parser.md)
  - Priority: Critical · Dependencies: 003.06, 003.09

### Stage 4 — Rule evaluation

- **Task 003.11** — `evaluator.py` (F7: §5.0 cell triage + §5.0.1 stale-cache + §5.1–5.4 + §5.7 composite + `string.Template` for messages)
  - RTM coverage: **R2.e (D4 auto-emit), R4.a, R4.b, R4.c, R4.d, R4.g, R4.h, R9.d**
  - Description: [`docs/tasks/task-003-11-evaluator.md`](tasks/task-003-11-evaluator.md)
  - Priority: Critical · Dependencies: 003.07, 003.10

- **Task 003.12** — `aggregates.py` (F8: §5.5 cross-cell + §5.6 group-by + SHA-1 cache + replay determinism per §5.5.3)
  - RTM coverage: **R4.e, R4.f, R10.a, R10.b, R10.c, R10.d, R10.e**
  - Description: [`docs/tasks/task-003-12-aggregates.md`](tasks/task-003-12-aggregates.md)
  - Priority: Critical · Dependencies: 003.08, 003.11

### Stage 5 — Output JSON

- **Task 003.13** — `output.py` (F9: envelope `{ok, schema_version, summary, findings}` always-three-keys [M2], deterministic 5-tuple sort with sentinels per §7.1.2, `--max-findings`, `--summarize-after`, human stderr report)
  - RTM coverage: **R5.a, R5.b, R5.c, R5.d, R5.e, R5.f, R5.g**
  - Description: [`docs/tasks/task-003-13-output.md`](tasks/task-003-13-output.md)
  - Priority: Critical · Dependencies: 003.05

### Stage 6 — CLI surface & orchestration

- **Task 003.14a** — `cli.py` argparse builder + mutex/dep validation [plan-review M-2 split, ~200 LOC]
  - RTM coverage: **R7.a, R7.b, R7.c, R7.e (DEP-4/DEP-5 IncompatibleFlags), R6.c partial (parse-time exit 2)**
  - Description: [`docs/tasks/task-003-14a-cli-argparse.md`](tasks/task-003-14a-cli-argparse.md)
  - Priority: Critical · Dependencies: 003.09–003.13

- **Task 003.14b** — `cli.py` watchdog + `_run` orchestrator + cross-3/4/5/7 envelopes [plan-review M-2 split, ~300 LOC; **headline test: M-2 architect-locked `test_partial_flush_main_thread_not_signal_handler`**]
  - RTM coverage: **R6.a, R6.b, R6.d, R6.e, R6.f, R6.g, R6.h, R7.d, R11.a, R11.b, R11.c, R11.d**
  - Description: [`docs/tasks/task-003-14b-cli-orchestrator.md`](tasks/task-003-14b-cli-orchestrator.md)
  - Priority: Critical · Dependencies: 003.14a

### Stage 7 — Workbook output (remark column)

- **Task 003.15** — `remarks_writer.py` (F10: full-fidelity write path + **architect-locked dual-stream** streaming path [M-1: read source `read_only=True`, write dest `WriteOnlyWorkbook`, single pass])
  - RTM coverage: **R8.a, R8.b, R8.c, R8.d, R8.e, R8.f, R8.g**
  - Description: [`docs/tasks/task-003-15-remarks-writer.md`](tasks/task-003-15-remarks-writer.md)
  - Priority: High · Dependencies: 003.14b

### Stage 8 — Cross-skill integration & full battery

- **Task 003.16a** — Perf fixture (`huge-100k-rows.xlsx`, D6-gated) + xlsx-6 envelope cross-skill tests (#39 / #39a / #39b end-to-end); battery xfail final sweep — every fixture xpass [plan-review M-3 split]
  - RTM coverage: **R9.f (perf contract), R11.e (xlsx-6 pipeline), R12.a (full ≥ 21 fixtures), R12.c, R12.d**
  - Description: [`docs/tasks/task-003-16a-perf-and-envelope-tests.md`](tasks/task-003-16a-perf-and-envelope-tests.md)
  - Priority: Critical · Dependencies: 003.15

- **Task 003.16b** — 10 canary saboteurs functional + meta-test `bash tests/canary_check.sh` exits 0 [plan-review M-3 split]
  - RTM coverage: **R10.e (saboteur 09 anchor: aggregate_cache_hits counter), R12.b**
  - Description: [`docs/tasks/task-003-16b-canary-saboteurs.md`](tasks/task-003-16b-canary-saboteurs.md)
  - Priority: Critical · Dependencies: 003.16a

### Stage 9 — Honest scope, docs, validation

- **Task 003.17** — Honest-scope regression locks (R13.a–R13.l); SPEC §5.0 patch (D4: 10→7 codes, modern → §11); `examples/check-rules-timesheet.{json,xlsx}`; `SKILL.md` / `.AGENTS.md` updates; `THIRD_PARTY_NOTICES.md` for new direct deps; `validate_skill.py skills/xlsx` green
  - RTM coverage: **R13.a–R13.l, R14.a, R14.b, R14.c, R14.d, R14.e**
  - Description: [`docs/tasks/task-003-17-honest-scope-and-docs.md`](tasks/task-003-17-honest-scope-and-docs.md)
  - Priority: Critical · Dependencies: 003.16b

## RTM Coverage Map

> **Per planner-prompt §4 Step 2 RTM Linking:** every TASK.md RTM
> sub-feature is mapped to **exactly one** PLAN task that delivers it
> (or to a small set where the sub-feature is genuinely distributed —
> e.g. R13.l "regression tests lock each limitation" lives in 003.17
> but individual locks land in earlier tasks). Multiple sub-features
> in one task are listed individually below.

| RTM ID | Sub-feature | PLAN Task |
|---|---|---|
| R1.a | JSON/YAML detection by extension | 003.09 |
| R1.b | 1 MiB pre-parse size cap → exit 2 `RulesFileTooLarge` | 003.09 |
| R1.c | ruamel.yaml typ=safe / 1.2 / no anchors / no custom tags / no dup-keys / no YAML-1.1 bool | 003.09 |
| R1.d | Hand-written recursive-descent parser (NOT `ast.parse`) | 003.10 |
| R1.e | Closed 17-node AST whitelist | 003.06 (types), 003.10 (parser) |
| R1.f | Composite depth cap 16 → exit 2 `CompositeDepth` | 003.10 |
| R1.g | Builtin whitelist → exit 2 `UnknownBuiltin` | 003.10 |
| R1.h | `version: 1` enforcement (Q7 hard exit 2) | 003.09 |
| R2.a | 6 logical types `number/date/bool/text/error/empty` | 003.07 |
| R2.b | "Numbers stored as text" stays `text` | 003.07 |
| R2.c | `Decimal` → `float` for arithmetic | 003.07 |
| R2.d | Whitespace strip default-on | 003.07 |
| R2.e | `cell-error` auto-emit (D4 7 codes only) | 003.07 (classify), 003.11 (auto-emit) |
| R3.a | 10 scope forms | 003.08 |
| R3.b | Sheet qualifier (plain / quoted / apostrophe-escape) | 003.08 |
| R3.c | Header semantics (case-sensitive, whitespace-strip, `header_row` default 1) | 003.08 |
| R3.d | Duplicate header → `AmbiguousHeader`; missing → `HeaderNotFound`; merged → `MergedHeaderUnsupported` | 003.08 |
| R3.e | Excel-Tables auto-detect (`xl/tables/tableN.xml`) | 003.08 |
| R3.f | Merged-cell anchor + `merged-cell-resolution` info | 003.08 |
| R3.g | Hidden rows/cols included by default | 003.08 |
| R4.a | §5.1 comparisons (==/!=/</<=/>/>= + between/in) | 003.11 |
| R4.b | §5.2 type guards (is_number / is_date / is_text / is_bool / is_error / required) | 003.11 |
| R4.c | §5.3 text rules (regex / len / starts_with / ends_with) + ReDoS hardening | 003.10 (lint), 003.11 (eval) |
| R4.d | §5.4 dates + `--treat-numeric-as-date` + `--treat-text-as-date` | 003.07 (coerce), 003.11 (eval) |
| R4.e | §5.5 cross-cell aggregates (sum/avg/...) | 003.12 |
| R4.f | §5.6 group-by (sum_by / count_by / avg_by) | 003.12 |
| R4.g | §5.7 composite (and/or/not, depth ≤ 16) | 003.10 (parse), 003.11 (eval) |
| R4.h | §3 fields (severity / message / when / skip_empty / tolerance) | 003.06 (RuleSpec), 003.11 (eval) |
| R5.a | `{ok, schema_version: 1, summary, findings}` envelope | 003.13 |
| R5.b | summary keys (errors/warnings/.../truncated) | 003.13 |
| R5.c | Finding fields per §7.1.1 | 003.13 |
| R5.d | Deterministic 5-tuple sort with sentinels per §7.1.2 | 003.13 |
| R5.e | Grouped-finding shape per §7.1.3 (row/column null) | 003.13 |
| R5.f | `--max-findings N` cap + synthetic `max-findings-reached` | 003.13 |
| R5.g | `--summarize-after N` collapsed entries | 003.13 |
| R6.a | Exit 0 pass | 003.14b |
| R6.b | Exit 1 ≥ 1 error | 003.14b |
| R6.c | Exit 2 RulesParseError | 003.09, 003.10, 003.14a |
| R6.d | Exit 3 unreadable / encrypted (cross-3) | 003.14b |
| R6.e | Exit 4 `--strict` ∧ ≥ 1 warning | 003.14b |
| R6.f | Exit 5 IO error | 003.14b |
| R6.g | Exit 6 same-path (cross-7 H1) | 003.14b, 003.15 |
| R6.h | Exit 7 wall-clock timeout (`--timeout`) | 003.14b |
| R7.a | ≥ 22 flags (full TASK §2.5 list) | 003.14a |
| R7.b | Mutex pairs (MX-A, MX-B) | 003.14a |
| R7.c | Dependencies (DEP-1..DEP-7) | 003.14a |
| R7.d | `--remark-column-mode` default `new` | 003.15 |
| R7.e | Streaming-incompatible combos (DEP-4, DEP-5) → exit 2 `IncompatibleFlags` | 003.14a |
| R8.a | `--output` writes a copy + remark column | 003.15 |
| R8.b | `--remark-column auto` first-free letter | 003.15 |
| R8.c | `replace`/`append`/`new` modes | 003.15 |
| R8.d | PatternFill red/yellow/blue per severity | 003.15 |
| R8.e | `--streaming-output` (M-1 dual-stream) | 003.15 |
| R8.f | Same-path → exit 6 (cross-7 H1) | 003.15 |
| R8.g | Round-trip preservation on un-modified cells | 003.15 |
| R9.a | `regex` PyPI lib + per-cell `timeout=100ms` | 003.10 (compile), 003.11 (eval) |
| R9.b | D5 4-shape ReDoS lint at parse | 003.10 |
| R9.c | Compilation cache (one `regex.compile` per pattern per run) | 003.11 |
| R9.d | Per-cell budget overflow → finding `rule-eval-timeout` | 003.11 |
| R9.e | Wall-clock cap `--timeout` → exit 7 | 003.14b |
| R9.f | Perf contract (100K rows × 5 rules ≤ 30 s, ≤ 500 MB RSS) — D6 gate | 003.16a |
| R10.a | Canonical key SHA-1 of `(sheet, scope, fn)` | 003.06 (canonical_str), 003.12 (cache) |
| R10.b | Cache entry stores `(value, skipped_cells, error_cells, cache_hits)` | 003.12 |
| R10.c | Replay re-emits per-cell skip/error events | 003.12 |
| R10.d | Intra-rule replay dedup on `(rule_id, cell)`; inter-rule no dedup | 003.12 |
| R10.e | `summary.aggregate_cache_hits` counter (canary anchor) | 003.12 (counter), 003.16b (saboteur 09) |
| R11.a | cross-3 fail-fast on encrypted input → exit 3 | 003.14b |
| R11.b | cross-4 `.xlsm` warning to stderr | 003.14b |
| R11.c | cross-5 `--json-errors` envelope on fatal codes | 003.14a (argparse usage), 003.14b (orchestrator-time) |
| R11.d | cross-7 H1 `Path.resolve()` same-path → exit 6 | 003.14b, 003.15 |
| R11.e | xlsx-6 envelope contract (fixture #39 + M2 #39a/#39b) | 003.16a |
| R12.a | ≥ 21 xlsx-7 fixtures (manifest) | 003.04a + 003.04b (manifests), 003.16a (full battery green) |
| R12.b | 10 canary saboteurs in `tests/canary_check.sh` | 003.16b |
| R12.c | Adversarial fixtures #22–#30 reject ≤ 100 ms | 003.10 (parse-time rejects), 003.16a (assert) |
| R12.d | Deterministic golden output | 003.13 (sort order), 003.16a (assert) |
| R13.a | No JOIN-style lookups | 003.17 (honest-scope test) |
| R13.b | No datetime arithmetic | 003.17 (honest-scope test) |
| R13.c | No auto-fix | 003.17 (honest-scope test) |
| R13.d | No Python plugins / lambdas | 003.17 (honest-scope test) |
| R13.e | No native Excel `<dataValidations>` ingestion | 003.17 (honest-scope test) |
| R13.f | No message localisation | 003.17 (honest-scope test) |
| R13.g | No multi-row / merged headers | 003.17 (honest-scope test) |
| R13.h | No transposed layout | 003.17 (honest-scope test) |
| R13.i | No multi-area `definedName` | 003.17 (honest-scope test) |
| R13.j | Decimal precision-loss documented | 003.17 (docs) |
| R13.k | Cached-value dependency (run xlsx_recalc.py first) | 003.11 (warning), 003.17 (docs) |
| R13.l | Each limitation locked by negative test | 003.17 |
| R14.a | `skills/xlsx/SKILL.md` §2/§4/§10/§12 entries | 003.17 |
| R14.b | `skills/xlsx/scripts/.AGENTS.md` updated | 003.17 |
| R14.c | SPEC `xlsx-rules-format.md` Status header + §5.0 (D4 patch) | 003.17 |
| R14.d | `examples/check-rules-timesheet.{json,xlsx}` | 003.17 |
| R14.e | `tests/golden/README.md` provenance | 003.17 |

## Stub-First Phasing

| Classical Stub-First | This plan's mapping |
|---|---|
| **Phase 1: Stubs + E2E (Red→Green)** — write failing E2E, then stub the API, then make E2E pass against stubbed values. | **Tasks 003.01–003.04** — package skeleton with `NotImplementedError` everywhere, E2E + battery scaffolds that fail uniformly, fixture manifests in place. The test harness exists but every assertion fails. |
| **Phase 2: Logic Implementation (Mock replacement)** — replace stubs with real logic, update E2E. | **Tasks 003.05–003.15** — each task implements one F-region (constants → exceptions → ast → cell_types → scope → loader → parser → evaluator → aggregates → output → cli → remarks). Per-task verification = "the slice of fixtures owned by this F turns green; previously-green fixtures stay green". |
| **Phase 3: Verification + Documentation.** | **Tasks 003.16–003.17** — cross-skill envelope tests, perf fixture (gated `RUN_PERF_TESTS=1`), 10 canary saboteurs functional, honest-scope locks, SPEC patch (D4), SKILL.md / `.AGENTS.md` / `examples/` / `THIRD_PARTY_NOTICES.md`, `validate_skill.py` green. |

## Execution discipline (per task)

Each `task-003-NN-*.md` follows this micro-cycle. The full text is in each
task file's "Notes" section; reproduced once here as the canonical version:

1. **Read** the source and adjacent already-implemented modules to understand the contract surfaces. Do NOT auto-format other modules.
2. **Implement** the F-region per the task spec; preserve the architect-locked invariants (M2 envelope all-three-keys, M-1 dual-stream, M-2 main-thread `_partial_flush`).
3. **Run** `cd skills/xlsx/scripts && ./.venv/bin/python -m unittest discover -s tests` → unit tests for the new module + regression on prior modules pass.
4. **Run** `bash skills/xlsx/scripts/tests/test_e2e.sh` → the slice of E2E fixtures owned by this F turns green; previously-green fixtures stay green.
5. **Run** `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` → exits 0 (no structural drift).
6. **`git add`** the F's source file + its tests + any fixture-generator changes.
7. **`git commit`** with message `task-003-NN: <F-region> impl (R<X.x> R<Y.y>...)`.

If any step fails: **DO NOT advance to the next task**. Investigate, fix, re-run. The chain's integrity depends on per-task green state.

## Use Case Coverage

| Use Case (TASK §3) | Tasks |
|---|---|
| I1.1 (Rules file loader) | 003.09 |
| I1.2 (Hand-written DSL parser) | 003.10 |
| I2.1 (Cell-value canonicalisation) | 003.07 |
| I2.2 (Scope resolver) | 003.08 |
| I3.1–I3.7 (Check vocabulary) | 003.10 (parse), 003.11 (eval), 003.12 (aggregates) |
| I3.8 (Pre-rule cell triage + cached-value preflight) | 003.11 |
| I4.1 (Findings envelope schema + sort) | 003.13 |
| I4.2 (Finding caps) | 003.13 |
| I4.3 (Exit codes matrix) | 003.14a (parse-time exits 2), 003.14b (orchestrator-time exits 0/1/3/4/5/6/7) |
| I4.4 (Stdout/stderr split) | 003.13 (emit), 003.14b (route) |
| I5.1 (argparse with mutex/dep) | 003.14a |
| I5.2 (`--treat-*-as-date` `,`/`;` switch) | 003.14a |
| I5.3 (Streaming-incompatible combos) | 003.14a (DEP-4/DEP-5 reject), 003.15 (impl) |
| I6.1 (Output-copy + remark allocation) | 003.15 |
| I6.2 (Remark mode replace/append/new) | 003.15 |
| I6.3 (Streaming output dual-stream) | 003.15 |
| I7.1 (Regex hardening) | 003.10, 003.11 |
| I7.2 (Aggregate cache + `aggregate_cache_hits`) | 003.12 |
| I7.3 (Wall-clock timeout) | 003.14b |
| I7.4 (Perf contract) | 003.16a |
| I8.1 (cross-3/4/5/7 envelopes) | 003.14b, 003.15 |
| I8.2 (xlsx-6 envelope #39/#39a/#39b) | 003.16a |
| I9.1 (`_generate.py`) | 003.03 (skeleton), 003.04a + 003.04b (manifests), 003.16a (perf fixture) |
| I9.2 (`test_battery.py`) | 003.02 (driver), 003.16a (assertions) |
| I9.3 (canary saboteurs) | 003.02 (slot), 003.16b (functional) |
| I9.4 (honest-scope locks) | 003.17 |
| I9.5 (Docs) | 003.17 |

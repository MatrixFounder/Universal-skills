# Plan Review — Task 009 (`xlsx-10.A` `xlsx_read/` library)

- **Date:** 2026-05-12
- **Reviewer:** Plan Reviewer (self-review pass)
- **Targets:**
  - [`docs/PLAN.md`](../PLAN.md)
  - 8 × [`docs/tasks/task-009-*.md`](../tasks/)
- **Checklist:** `plan-review-checklist` (v1.0)
- **Status:** ✅ **APPROVED — NO BLOCKING ISSUES**

## General Assessment

Plan decomposes Task 009 into **1 stub task + 6 module-scoped logic
tasks + 1 integration/E2E task = 8 atomic units**, each within the
2–4-hour budget mandated by the planner prompt. Stub-First
methodology is **explicit** in PLAN §4 (Stub-First Compliance
table maps every F-region to its Phase-1/Phase-2 split). RTM
coverage (PLAN §2) is complete: every R1–R13 from TASK maps to
≥ 1 task. Use Case coverage (PLAN §3) is complete: UC-01..UC-06 all
covered.

## Use Case Coverage (mandatory)

| Use Case | Task(s) | Verified by |
| --- | --- | --- |
| UC-01 Open workbook | 009-01 (stub), 009-02 (logic), 009-08 (E2E) | TC-E2E-01..-08 in 009-02; scenarios 1–3 in 009-08 |
| UC-02 Enumerate sheets | 009-03 (logic), 009-08 (E2E) | TC-E2E-01..-04 in 009-03; scenarios 4–8 in 009-08 |
| UC-03 Detect tables | 009-05 (logic), 009-08 (E2E) | TC-E2E-01..-09 in 009-05; scenarios 12–17 in 009-08 |
| UC-04 Read table region | 009-04 + 009-06 + 009-07 + 009-08 | scenarios 9–11, 18–26 in 009-08 |
| UC-05 Thread-safety contract | 009-01 (doc), 009-08 (AST regression) | scenario 30 in 009-08 |
| UC-06 Closed-API enforcement | 009-01 | TC-UNIT-05 in 009-01; scenario 27 in 009-08 |

## Structure & Formalism

### Stub-First (mandatory)
- ✅ Task **009-01** is explicitly tagged `[STUB CREATION]` — stands
  up the package skeleton, toolchain, and all sentinel-returning
  stubs.
- ✅ Tasks **009-02..009-08** are explicitly tagged
  `[LOGIC IMPLEMENTATION]`.
- ✅ PLAN §4 tabulates every F-region with its specific Phase-1
  → Phase-2 transition gate (e.g. "After 009-01: `parse_merges()`
  returns `{}`. After 009-04: real merge map live").
- ✅ Each logic task explicitly **updates** the running E2E to
  assert real values (per `tdd-stub-first §2`), e.g. 009-02
  modifies `test_smoke_stub.py` TC-UNIT-04.

### Dependencies & Phasing
- ✅ PLAN §6 provides a Mermaid dependency graph; per-task `Dependencies:`
  fields are concrete (e.g. 009-05 depends on 009-01, 009-02, 009-03).
- ✅ Three stages: Stage 1 (Structure & Stubs), Stage 2 (per-module
  logic), Stage 3 (Integration + Final Gates).
- ✅ Critical-path nodes (009-01 → 009-02 → 009-08) clearly marked.

### Atomicity
- ✅ Each task targets exactly **one F-region** (one module + its
  tests), within the 2–4 hour budget per planner prompt §1.
- ✅ No task contains "implement everything" hand-waves.

## Task Descriptions

| Task File | Exists | Naming | Sections | Depth |
| --- | --- | --- | --- | --- |
| task-009-01-pkg-skeleton-and-toolchain.md | ✅ | ✅ | ✅ all 7 | ✅ method signatures + file paths |
| task-009-02-workbook-open-encrypt-macro.md | ✅ | ✅ | ✅ | ✅ |
| task-009-03-sheets-enumerate-resolve.md | ✅ | ✅ | ✅ | ✅ |
| task-009-04-merges-policy-overlap.md | ✅ | ✅ | ✅ | ✅ |
| task-009-05-tables-3tier-detect.md | ✅ | ✅ | ✅ | ✅ |
| task-009-06-headers-multi-row-flatten.md | ✅ | ✅ | ✅ | ✅ |
| task-009-07-values-extract-format.md | ✅ | ✅ | ✅ | ✅ |
| task-009-08-public-api-e2e-and-docs.md | ✅ | ✅ | ✅ | ✅ |

> **Section coverage per file (mandated by checklist §3):** Use Case
> Connection, RTM Coverage, Task Goal, Changes Description (New
> Files + Changes in Existing Files), Component Integration, Test
> Cases (E2E + Unit + Regression), Acceptance Criteria, Notes. All
> 8 task files comply.

## RTM Coverage (one-line per RTM ID — checklist §1.2 RTM Linking)

| RTM | First mention in PLAN.md | Verified |
| --- | --- | --- |
| [R1] | §1 (009-01 contract; 009-08 closure) | ✅ |
| [R2] | §1 (009-01) | ✅ |
| [R3] | §1 (009-02) | ✅ |
| [R4] | §1 (009-03) | ✅ |
| [R5] | §1 (009-05) | ✅ |
| [R6] | §1 (009-01 signature; 009-08 wiring) | ✅ |
| [R7] | §1 (009-06) | ✅ |
| [R8] | §1 (009-07) | ✅ |
| [R9] | §1 (009-04) | ✅ |
| [R10] | §1 (009-01) | ✅ |
| [R11] | §1 (009-01) | ✅ |
| [R12] | §1 (009-01 initial; 009-08 closure) | ✅ |
| [R13] | §1 (009-08) | ✅ |

> **Constraint check (`plan-review-checklist §1.2`):** every
> checklist item in PLAN §1 starts with `[Rx]` prefix. ✅

## Strict Mode (checklist §3 last bullet)
- **Not flagged.** This is a **foundation library** with extensive
  E2E (≥ 30 named scenarios) and unit coverage already enforced by
  the task descriptions; `tdd-strict` ceremony is appropriate for
  bug-fixes / critical-feature hardening, not for new library
  bring-up. The Stub-First chain + closed-API regression test +
  30-scenario E2E already constitute high-assurance coverage.

## Comments

### 🔴 Critical — none
### 🟡 Major — none
### 🟢 Minor — none

## Final Decision

**APPROVED.** Plan ready for the Developer phase. Recommended
execution order: **009-01 → (009-02 sequentially, then 009-03..-07
in parallel where deps allow) → 009-08**. See PLAN §6 dependency
graph for parallelism opportunities.

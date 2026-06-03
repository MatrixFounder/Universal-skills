# Plan Review — TASK 018 (`pdf-ocr` / pdf-4)

- **Date:** 2026-06-03
- **Reviewer:** Plan Reviewer Agent (VDD, `07_plan_reviewer` + `plan-review-checklist`)
- **Target:** [`docs/PLAN.md`](../PLAN.md) + [`docs/tasks/task-018-0{1..6}-*.md`](../tasks/)
- **Inputs:** [`docs/TASK.md`](../TASK.md), [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md),
  upstream reviews (task/architecture both APPROVED w/comments).
- **Status:** ✅ **APPROVED WITH COMMENTS** (no BLOCKING; 1 MAJOR DoD-tightening
  applied, 4 MINOR)

---

## General Assessment

Clean, faithful decomposition. Stub-First is correctly two-pass (018-01 lays the
frozen surface with real guards + stubbed engine/runner; 018-02/03 turn them
green). Every RTM item R1–R9 has a completing bead with the multi-bead splits
named explicitly; every Use Case (incl. UC-4 → 018-04) is covered; all six
`task-018-NN-*.md` files exist and carry Goal / Changes (with concrete
signatures) / Test Cases / Acceptance / Stub-First gate. The cross-skill
`diff -q` silent gate is replicated into every task's acceptance. The plan
correctly mirrors the TASK 013 `pdf_extract.py` shape and reuses its real code
idioms (`_OcrError` ↔ `_ExtractError`, `report_error`, `_same_path`).

The standout strength is the honest handling of the soft-optional engine
(§0.3): the plan does not pretend the engine is always present — it separates
engine-free gates (parser, mutex, guards, missing-engine/missing-pack envelopes,
exception-mapping via a fake module) from engine-gated real-OCR E2Es that
soft-skip. That same honesty creates the one MAJOR below.

---

## Use Case Coverage (traced)

| Use Case | Tasks | OK |
|----------|-------|----|
| UC-1 OCR scanned → searchable | 018-01 (smoke), 018-02 (engine/lang), 018-03 (runner + composition E2E), 018-06 (reference) | ✅ |
| UC-2 OCR + sidecar | 018-01 (guard), 018-03 (`--sidecar`) | ✅ |
| UC-3 re-OCR (redo/force) | 018-01 (mutex), 018-03 (behavior) | ✅ |
| UC-4 encrypted input | 018-04 (post-MVP) | ✅ |

No orphan Use Case. No orphan RTM item (R1–R9 all bound, §2 PLAN).

## Stub-First Verification

- ✅ Stubs scheduled **before** logic: 018-01 `[STUB CREATION]` → 018-02/03
  `[LOGIC IMPLEMENTATION]`.
- ✅ Frozen-surface contract in 018-01 prevents later symbol churn.
- ✅ Each logic task "updates the E2E/units per `tdd-stub-first §2.4`".
- ✅ Dependency order valid: 01 → 02 → 03 → 06; 04/05 after 03.

---

## Comments

### 🔴 CRITICAL (BLOCKING)

None.

### 🟡 MAJOR

- **PR-1 — DoD must not accept "skip-only" evidence for the core feature
  (APPLIED).** R4a (scan→OCR→`pdf_extract` digital re-read) is *the*
  architecture acceptance hinge, but it is engine-gated and soft-skips when
  ocrmypdf/tesseract/gs are absent. As written, a host without the engine could
  run the full suite green while the central behavior was **never executed**, and
  018-06 could still flip `pdf-4` → DONE. That is a false-green risk.
  **Fix:** tighten the MVP DoD (PLAN §6) and 018-06 acceptance — `pdf-4` may be
  marked ✅ DONE **only** after the composition E2E (TC-E2E-03) has actually run
  (not skipped) at least once on an engine-equipped host, with the result
  recorded in the 018-06 validation evidence. *(Applied this revision — see PLAN
  §6 and task-018-06 acceptance.)*

### 🟢 MINOR

- **PR-2 — Pin ocrmypdf in 018-02 before 018-03 relies on exception class
  names.** The 018-03 FC-6 mapping table ("confirm exact class names against the
  pinned ocrmypdf") depends on the version pinned in 018-02. The order (02→03)
  already guarantees this; just make 018-02's "finalize the floor" step explicit
  as a precondition for 018-03's mapping. (Note added to 018-02 already covers
  the pin; no structural change.)

- **PR-3 — Consider `tdd-strict` for the FC-6 exception-mapping surface.** The
  checklist asks whether strict TDD is warranted for critical components. The
  exception→`error_type`→exit mapping (018-03) is the highest-risk correctness
  surface (silent miscategorization would mislead agent wrappers). Recommend the
  developer apply `tdd-strict` discipline (write the mapping unit table first,
  red→green) for TC-UNIT-15 specifically. Non-blocking.

- **PR-4 — Surprise-flag UX for deferred knobs.** `--deskew`/`--rotate-pages`/
  `--clean` are parser-visible from 018-01 but raise a "bead 018-05" `_OcrError`
  until that bead lands. Good that it is loud (not silent), but ensure the
  `--help` text for those three flags says plainly "available after bead 018-05 /
  needs extra host tools" so a user reading `--help` is not surprised by a
  runtime error. (018-01 already marks them "needs extra host tools"; add the
  "not yet active" note.)

- **PR-5 — Watch 018-03 scope.** 018-03 is the meatiest bead (runner + full
  exception mapping + 3 E2E + 3 unit). It is within budget as one coherent unit
  (mapping wraps the runner call, so splitting would be artificial), but if it
  balloons during dev, split exception-mapping into a 018-03b. Advisory only.

---

## Checklist Result (`plan-review-checklist`)

| Section | Item | Verdict |
|---|---|---|
| 1 | Every Use Case mapped to ≥1 task | ✅ |
| 1 | Traceability/coverage table exists | ✅ (PLAN §2, §3) |
| 2 | Stub + Impl phases per component | ✅ |
| 2 | Task order respects dependencies | ✅ |
| 2 | Clear phasing (Structure→Logic→Test/Integ) | ✅ |
| 3 | Task file exists for every plan task | ✅ (6/6) |
| 3 | Naming `task-{ID}-{SubID}-{slug}.md` | ✅ |
| 3 | Goal / Changes / Test Cases / Acceptance present | ✅ |
| 3 | Specific paths + signatures (no coding) | ✅ |
| 3 | `tdd-strict` for critical components | ⚠️ PR-3 (recommended for FC-6 mapping) |
| — | RTM IDs prefix checklist items | ✅ (`[R1]`…) |
| — | False-green risk on engine-gated E2E | ⚠️ **PR-1** (DoD tightened) |

---

## Final Decision

**APPROVED** — proceed to the Development phase (`/vdd-develop` or
`/vdd-develop-all`). PR-1 is applied in this revision (DoD now forbids
skip-only evidence for `pdf-4` DONE); PR-2…PR-5 are advisory and folded into the
relevant task notes. Recommended execution: MVP chain `018-01 → 018-02 → 018-03
→ 018-06`, then the deferred beads 018-04 (R5) and 018-05 (R9) only if
prioritized.

# Development Plan: TASK 018 — `pdf-4` `pdf_ocr.py` (OCR scanned PDFs, eng+rus)

> **Mode:** VDD (Verification-Driven Development) + Stub-First.
> **Status:** DRAFT v1 — pending Plan-Reviewer approval.
> **TASK:** [TASK.md](TASK.md) (TASK 018, slug `pdf-ocr`, backlog row `pdf-4`).
> **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md) (single-file `pdf_ocr.py`
> ocrmypdf wrapper → searchable PDF; soft-optional `--with-ocr`; atomic-chain §11).
> **Reviews upstream:** [reviews/task-018-review.md](reviews/task-018-review.md)
> (APPROVED w/comments), [reviews/architecture-018-review.md](reviews/architecture-018-review.md)
> (APPROVED w/comments).
> **Prior plan:** wiki-ingest epic complete — last plan
> [plans/plan-017-wiki-ingest-v1.1-contract-alignment.md](plans/plan-017-wiki-ingest-v1.1-contract-alignment.md)
> (already archived; this is a NEW task, so `docs/PLAN.md` was free to write fresh).

---

## 0. Strategy Summary

### 0.1. Chainlink Decomposition Overview

Every RTM Issue from TASK §2 (R1..R9 across 4 Epics) is decomposed into
**Beads** — atomic sub-issues, each implementable in one 2–4 h sitting and
verifiable through a single test cluster. Beads are grouped into **6
module-scoped tasks** (`task-018-NN-*.md`), each tagged Stub-First per
`tdd-stub-first §1–§2`.

This is a small, single-script addition to an existing skill (mirrors the
TASK 013 `pdf_extract.py` shape): one new script
(`scripts/pdf_ocr.py`), one new optional-dep manifest
(`scripts/requirements-ocr.txt`), an `install.sh --with-ocr` branch, one new
reference (`references/ocr.md`), test fixtures + E2E, and skill-integration
edits. **No package, no cross-skill replication** (ARCH §3.1, §9): `pdf_ocr.py`
imports `_errors.py` read-only and touches no `office/` or shared helper.

### 0.2. Phasing (Stub-First)

- **Phase 1 — Structure & Stubs** — single bootstrap task **018-01**:
  `pdf_ocr.py` with the full frozen surface (argparse fully declared incl. the
  `--skip-text`/`--redo-ocr`/`--force-ocr` mutex; exit-matrix constants;
  path-resolve + self-overwrite guards **REAL**; engine-probe / lang-validate /
  OCR-runner / error-mapper as **stubs**); `requirements-ocr.txt`;
  `install.sh --with-ocr` probe+hints branch (config — real); the fixture
  builder `tests/_pdf_ocr_fixtures.py` (image-only scan PDF + digital PDF +
  mixed PDF, built-at-runtime per D-01); `tests/test_pdf_ocr.py` scaffolded
  with a `--help` smoke E2E + a RED unit cluster that passes on stubs
  (Red→Green per `tdd-stub-first §1`). Base `requirements.txt` is **NOT** touched
  (ARCH §6).

- **Phase 2 — Logic Implementation** — 2 MVP logic tasks, each replacing one
  function-cluster's stubs + adding its unit cluster + updating E2E assertions
  (`tdd-stub-first §2`):
  - **018-02** FC-3 engine probe (lazy import → `OcrEngineUnavailable`) + FC-4
    language validator (default `eng+rus`, `LanguagePackMissing`).
  - **018-03** FC-5 OCR runner (ocrmypdf delegate: skip/redo/force, `--sidecar`,
    `--jobs`, atomic write) + FC-6 exception→exit mapping + the **R4
    composition E2E** (scan→OCR→`pdf_extract` reads needle). **MVP gate.**

- **Phase 3 — Documentation & integration** — task **018-06**: `references/ocr.md`
  (usage + composition recipe + trust model + honest scope), `SKILL.md` surface,
  `pdf-to-markdown.md` cross-link, `THIRD_PARTY_NOTICES.md` (ocrmypdf / tesseract
  / ghostscript), the `test_e2e.sh` OCR block (**soft-skip** when engine absent),
  `validate_skill.py` exit 0, cross-skill `diff -q` silent gate, backlog row
  `pdf-4` → ✅ DONE. Depends on 018-03 (the runner must exist).

- **Phase 4 — Deferred beads (post-MVP, gated separately — D-A2 / ARCH §11)** —
  run only if prioritized; each is self-contained (own logic + own tests + own
  doc paragraph in `references/ocr.md`/`SKILL.md` + own validate/diff gate):
  - **018-04** R5 password: `pikepdf` decrypt-to-temp pre-stage + UC-4 tests.
  - **018-05** R9 image-prep pass-throughs (`--deskew`/`--rotate-pages`/`--clean`
    + `osd`/`unpaper` soft-probes — AM-3).

> **Atomicity check:** each task targets one function-cluster or one artifact +
> its tests — within the 2–4 h budget per `planning-decision-tree`. Each task
> file carries an explicit Stub-First gate.

### 0.3. Environment nuance — engine-gated tests (honest scope)

`ocrmypdf` + `tesseract` + `ghostscript` are **soft-optional** (D-2). The
Stub-First gate (018-01) and the pure-logic units (parser, mutex, path guards,
**engine-absent** envelopes from 018-02) run green **without** the engine. The
real OCR assertions — the 018-03 composition E2E and the 018-06 `test_e2e.sh`
OCR block — **soft-skip** when `ocrmypdf`/`tesseract`/`gs`/`eng`+`rus` are not
present (the `skip()` pattern already used for mermaid in `test_e2e.sh`). To turn
them genuinely green a developer runs `bash install.sh --with-ocr` **and**
installs the system `tesseract` (+ `eng`,`rus` traineddata) and `ghostscript`.
This split is documented in the relevant task files and `references/ocr.md`; it
is honest scope, not a coverage gap.

### 0.4. Cross-skill replication gate

**This task replicates nowhere.** All new/edited code lives under `skills/pdf/`
(+ `docs/`). `pdf_ocr.py` *imports* `_errors.py` read-only — it modifies none of
the 4-skill / 3-skill replicated files (ARCH §9). The 2-line `diff -q` silent
gate appears in every task file's Acceptance Criteria:

```bash
diff -q skills/docx/scripts/_errors.py  skills/pdf/scripts/_errors.py
diff -q skills/docx/scripts/preview.py  skills/pdf/scripts/preview.py
```

Both MUST produce no output.

### 0.5. Decisions locked from TASK + ARCHITECTURE (no blocking questions)

Recorded here in case the Plan-Reviewer would have asked — all resolved
upstream:

- **Exit codes (D-A1, ARCH §5.2):** all hard failures exit `1`, discriminated
  by the `--json-errors` envelope `type` field (`OcrEngineUnavailable` /
  `LanguagePackMissing` / `EncryptedInput` / `InputUnreadable` / `PriorOcrFound`
  / `OutputWriteFailed` / `InternalError`). No new codes; `6`
  SelfOverwriteRefused (parity); `2` usage; `10` stays exclusive to
  `pdf_extract.py`.
- **Envelope schema (ARCH §4.3, corrected for lockstep):** `_errors.py`'s
  `{v, error, code, type?, details?}`. Remediation text lives inside the `error`
  message string. `error_type=` → JSON `type`.
- **CLI shape (D-A5):** positional `INPUT OUTPUT`, OUTPUT required, no `-o`.
- **Default mode (D-3):** `--skip-text`. Modes mutually exclusive (argparse mutex).
- **Default lang (D-A4):** `eng+rus`; validate any requested pack before invoking.
- **R5 / R9 (D-A2):** post-MVP, gated separately; **not** in the MVP acceptance
  set. MVP = 018-01 + 018-02 + 018-03 + 018-06.
- **No engine bundling (ARCH §10):** tesseract/gs/lang packs detected, never
  installed by us.

---

## 1. Task Execution Sequence

### Stage 1 — Structure & Stubs

- **Task 018-01** — `[STUB CREATION]` `pdf_ocr.py` skeleton + packaging + fixtures + test scaffolding
  - RTM: scaffolds [R1][R2][R3]; **completes** [R3d] (mode mutex), [R6c][R6d]
    (path/self-overwrite + sidecar guards), [R7a][R7c][R7d] (manifest +
    install.sh probe + base untouched); scaffolds [R6a][R6b][R7b][R8].
  - Use Cases: UC-1, UC-2, UC-3 (stub-level smoke); UC-1 A3 (same-path) real.
  - Description file: [`docs/tasks/task-018-01-skeleton-packaging-fixtures.md`](tasks/task-018-01-skeleton-packaging-fixtures.md)
  - Priority: Critical
  - Dependencies: none (bootstrap).

### Stage 2 — Logic Implementation (MVP)

- **Task 018-02** — `[LOGIC IMPLEMENTATION]` Engine probe + language validator
  - RTM: **completes** [R2] (a/b/c), [R7b] (lazy-import fail-loud); [R6a][R6b]
    (the `OcrEngineUnavailable` / `LanguagePackMissing` envelopes).
  - Use Cases: UC-1 A1 (engine missing), UC-1 A2 (pack missing).
  - Description file: [`docs/tasks/task-018-02-engine-probe-lang-validate.md`](tasks/task-018-02-engine-probe-lang-validate.md)
  - Priority: High
  - Dependencies: 018-01.

- **Task 018-03** — `[LOGIC IMPLEMENTATION]` OCR runner + exception mapping + composition E2E
  - RTM: **completes** [R1] (a/b/c), [R3a][R3b][R3c] (skip/redo/force behavior),
    [R4a] (round-trip), [R4c] (`--sidecar`), [R6a][R6b] (full exit matrix +
    exception→type mapping).
  - Use Cases: UC-1 main, UC-2 (sidecar), UC-3 (re-OCR), UC-1 A4/A5/A6.
  - Description file: [`docs/tasks/task-018-03-ocr-runner-and-mapping.md`](tasks/task-018-03-ocr-runner-and-mapping.md)
  - Priority: High (MVP gate)
  - Dependencies: 018-02.

### Stage 3 — Documentation & integration (MVP)

- **Task 018-06** — `[INTEGRATION]` reference doc, skill surface, notices, E2E block, validation, backlog
  - RTM: **completes** [R4b] (composition recipe doc), [R8a] (`test_e2e.sh` OCR
    block, soft-skip), [R8c] (`references/ocr.md` + `SKILL.md` + trust model +
    cross-link), [R8d] (`validate_skill.py` + skill-validator + `diff -q`).
  - Use Cases: UC-3 (maintainer validation), UC-1 (agent-follows-reference).
  - Description file: [`docs/tasks/task-018-06-docs-integration-validation.md`](tasks/task-018-06-docs-integration-validation.md)
  - Priority: High
  - Dependencies: 018-03 (runner must exist before SKILL.md/docs describe it and
    validate runs).

### Stage 4 — Deferred beads (post-MVP — run only if prioritized)

- **Task 018-04** — `[LOGIC IMPLEMENTATION]` R5 password (pikepdf decrypt-to-temp)
  - RTM: **completes** [R5] (a/b/c).
  - Use Cases: UC-4.
  - Description file: [`docs/tasks/task-018-04-password-decrypt.md`](tasks/task-018-04-password-decrypt.md)
  - Priority: Medium (post-MVP, D-A2)
  - Dependencies: 018-03. Self-contained docs/tests/validate.

- **Task 018-05** — `[LOGIC IMPLEMENTATION]` R9 image-prep pass-throughs
  - RTM: **completes** [R9] (a/b/c).
  - Use Cases: (quality knobs — no new UC; extends UC-1).
  - Description file: [`docs/tasks/task-018-05-image-prep-knobs.md`](tasks/task-018-05-image-prep-knobs.md)
  - Priority: Low (deferrable, D-A2)
  - Dependencies: 018-03. Self-contained docs/tests/validate.

**Execution order (MVP):** `018-01 → 018-02 → 018-03 → 018-06`.
**Deferred:** `018-04`, then `018-05` — each after 018-06, only if prioritized.

---

## 2. RTM Coverage Matrix

One RTM Issue = one checklist item, prefixed with the RTM ID (planner prompt
§Step-2). "Bead" = the task that **completes** the requirement; multi-bead rows
name the primary bead and the split.

- [ ] **[R1]** Searchable PDF via ocrmypdf (a CLI / b text-layer / c geometry) → **018-03** (scaffolded 018-01)
- [ ] **[R2]** Language eng+rus default + pack validation (a `--lang` / b validate / c combos) → **018-02**
- [ ] **[R3]** Existing-text handling → **018-01** (3d mutex) + **018-03** (3a skip / 3b redo / 3c force behavior)
- [ ] **[R4]** Composition with `pdf_extract.py` → **018-03** (4a round-trip, 4c sidecar) + **018-06** (4b recipe doc)
- [ ] **[R5]** Encrypted/password input (a `--password` / b loud-fail / c argv honest-scope) → **018-04** (post-MVP)
- [ ] **[R6]** Exit/error contract → **018-01** (6c guards, 6d sidecar guard) + **018-02/03** (6a envelope, 6b exit matrix + types)
- [ ] **[R7]** Soft-optional packaging → **018-01** (7a manifest, 7c install.sh probe, 7d base untouched) + **018-02** (7b lazy-import fail-loud)
- [ ] **[R8]** Tests/docs/validator → **018-01** (8b unit scaffold, RED) + **018-02/03** (8b green) + **018-06** (8a E2E block, 8c docs, 8d validator)
- [ ] **[R9]** Image-prep knobs (a deskew / b rotate / c clean) → **018-05** (deferrable, post-MVP)

**No orphan requirement.** Every R1–R9 has a completing bead; multi-bead
requirements (R3, R4, R6, R7, R8) name the primary bead and the split
explicitly. R5/R9 complete in the post-MVP beads (D-A2).

---

## 3. Use Case Coverage

| Use Case | Tasks |
|----------|-------|
| UC-1 — OCR a scanned PDF (primary) | 018-01 (smoke), 018-02 (lang/engine), 018-03 (runner + composition E2E), 018-06 (reference) |
| UC-2 — OCR + sidecar | 018-03 (`--sidecar` + guard from 018-01) |
| UC-3 — re-OCR (`--redo-ocr`) | 018-01 (mutex), 018-03 (redo/force behavior) |
| UC-4 — encrypted input (post-MVP) | 018-04 |

---

## 4. Stub-First Gate Inventory

Per `tdd-stub-first §1–§2`, each task file specifies its gate. Summary:

| Task | Stub-First role |
|------|-----------------|
| 018-01 | Creates the frozen surface: argparse (incl. mode mutex) + path/self-overwrite guards **real**; engine-probe / lang-validate / OCR-runner / error-mapper **stubbed** (sentinels). `--help` smoke E2E + unit cluster pass on stubs (Red→Green). No public symbol renamed later. |
| 018-02 | Replaces engine-probe + lang-validator stubs; **updates** the unit cluster to assert real `OcrEngineUnavailable` / `LanguagePackMissing` envelopes (engine-absent path testable without the engine). |
| 018-03 | Replaces OCR-runner + error-mapper stubs; full exit matrix + the composition E2E (**soft-skip** without engine). MVP gate. |
| 018-06 | Integration/docs — no stub phase; verified by `validate_skill.py` exit 0 + suite green + `diff -q` silent. |
| 018-04 | Stub→logic for `--password` decrypt path (self-contained); UC-4 tests soft-skip without engine. |
| 018-05 | Stub→logic for `--deskew`/`--rotate-pages`/`--clean` + `osd`/`unpaper` soft-probes (self-contained). |

### Honest-scope locks (TASK §3bis / ARCH §10) — documented by the named task

- ocrmypdf engine not bundled; tesseract/gs/lang detected → `references/ocr.md` (018-06) + install.sh probe (018-01).
- `--password` argv-visible in `ps` → `--help` text (018-01) + `references/ocr.md` (018-06) + completed in 018-04.
- No global timeout / DoS hardening → `references/ocr.md` (018-06).
- `--skip-text` default never destroys vector text; `PriorOcrFound` unreachable on default path (AM-4) → docstring + 018-03.
- R5 output is unencrypted (re-encryption out of scope) → 018-04 docstring + `references/ocr.md`.

---

## 5. Backlog Update (`docs/office-skills-backlog.md`)

- **Now (end of planning):** the `pdf-4` row (line ~211) and its
  §7-prioritisation mention (line ~665) are annotated **🔄 PLANNED — TASK 018
  (VDD spec+arch+plan approved)**, noting the locked design (ocrmypdf→searchable
  PDF, eng+rus, soft-optional `--with-ocr`, composition with `pdf_extract.py`).
- **At merge:** task **018-06** flips the row to **✅ DONE** with the final
  validation evidence (R8d).

---

## 6. Definition of Done

- **MVP DoD:** task files 018-01/02/03/06 created and executed; RTM R1–R4, R6,
  R7, R8 bound to a completing bead (§2) — no orphan; Stub-First two-pass
  structure (§4); `validate_skill.py skills/pdf` exit 0; cross-skill `diff -q`
  silent.
  - **No false-green (PR-1):** the composition E2E **TC-E2E-03 must have
    actually run — not soft-skipped — at least once on an engine-equipped host**
    (ocrmypdf + tesseract eng+rus + ghostscript), with the pass recorded in the
    018-06 validation evidence. `pdf-4` may be flipped to ✅ DONE **only** on that
    real-run evidence; a suite that merely soft-skips the OCR block is NOT
    sufficient to mark the feature done.
- **Full DoD (incl. deferred):** 018-04 (R5) + 018-05 (R9) executed; UC-4 +
  R9 acceptance met.
- Plan-Reviewer approval recorded in `docs/reviews/plan-018-review.md`.

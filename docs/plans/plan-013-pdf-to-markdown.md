# Development Plan: TASK 013 — `pdf-12` PDF → Markdown guidance + `pdf_extract.py`

> **Mode:** VDD (Verification-Driven Development) + Stub-First.
> **Status:** DRAFT v1 — pending Plan-Reviewer approval.
> **TASK:** [TASK.md](TASK.md) (TASK 013, slug `pdf-to-markdown`, backlog row `pdf-12`).
> **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md) (pdf-13 — single-file
> `pdf_extract.py` dump + `pdf-to-markdown.md` reference).
> **Prior plan archived:** [plans/plan-012-xlsx-9-xlsx2md.md](plans/plan-012-xlsx-9-xlsx2md.md).
> **Atomic-chain hint (architect handoff):** [ARCHITECTURE.md §11](ARCHITECTURE.md).

---

## 0. Strategy Summary

### 0.1. Chainlink Decomposition Overview

Every RTM Issue from TASK §2 (R1..R13, 13 IDs across 3 Epics) is decomposed into
one or more **Beads** — atomic sub-issues, each implementable in a single sitting
(2–4 h) and verifiable through a single test cluster. Beads are grouped into
**6 module-scoped tasks** (`task-013-NN-*.md`), each tagged Stub-First per
`tdd-stub-first §1–§2`.

This is a small, single-script addition to an existing skill: one new script
(`scripts/pdf_extract.py`), one new reference (`references/pdf-to-markdown.md`),
test fixtures + E2E, and skill-integration edits. No package, no new dependency,
no cross-skill replication (ARCH §3.1, §9).

### 0.2. Phasing (Stub-First)

- **Phase 1 — Structure & Stubs** — single bootstrap task **013-01**:
  `pdf_extract.py` with the full frozen surface (all functions per ARCH §5.4
  stubbed to sentinels; argparse fully declared; exit-code + threshold
  constants); the fixture builder `tests/_pdf_extract_fixtures.py` + the 3
  committed fixtures (digital / scan-like / encrypted); `tests/test_pdf_extract.py`
  scaffolded with ONE smoke E2E asserting the hardcoded stub behaviour
  (Red → Green on stubs per `tdd-stub-first §1`). `requirements.txt` is **not**
  touched (ARCH §6 — `pdfplumber` / `reportlab` / `Pillow` / `pypdf` all already
  declared).

- **Phase 2 — Logic Implementation** — 3 logic tasks, each replacing one
  function-cluster's stubs with real behaviour + its unit cluster, and updating
  the E2E assertions per `tdd-stub-first §2`:
  - **013-02** extraction core (`_open_pdf`, `_extract_page`, `extract_pdf`).
  - **013-03** scan classifier (`_classify_page`, `_classify_document`).
  - **013-04** CLI glue + emitter (`main`, `_emit`, `--json-errors`, exit-code
    matrix, idempotency, `--password`).

- **Phase 3 — Reference document** — task **013-05**: write
  `references/pdf-to-markdown.md` (E1). Pure documentation; depends only on the
  CLI contract (frozen by ARCH §5 + 013-01) → may run in **parallel** with
  Phase 2.

- **Phase 4 — Integration & validation** — task **013-06**: `SKILL.md` surface
  (§2/§4/§10/§12 + §1/§3 review), `library-selection.md` cross-link, the
  `pdf-12` backlog-row update, `test_e2e.sh` smoke block, `validate_skill.py`
  exit 0, cross-skill `diff -q` silent gate.

> **Atomicity check:** each task targets one function-cluster or one artifact +
> its tests — within the 2–4 h budget per `planning-decision-tree`. Each task
> file carries an explicit Stub-First gate per `tdd-stub-first §2`.

### 0.3. Cross-skill replication gate

**This task replicates nowhere.** All new/edited files live under `skills/pdf/`
(+ `docs/`). `pdf_extract.py` *imports* `_errors.py` read-only — it does not
modify any of the 4-skill / 3-skill replicated files (ARCH §9). The 2-line
`diff -q` silent gate appears in **every** task file's Acceptance Criteria:

```bash
diff -q skills/docx/scripts/_errors.py  skills/pdf/scripts/_errors.py
diff -q skills/docx/scripts/preview.py  skills/pdf/scripts/preview.py
```

Both MUST produce no output.

### 0.4. Decisions locked from TASK + ARCHITECTURE (no blocking questions)

Recorded here in case the Plan-Reviewer would have asked — all resolved
upstream:

- **Scan threshold** `_SCANNED_CHAR_THRESHOLD = 10` (ARCH §4.3, TASK Q-3) —
  absolute extractable-char count per page; rationale dual-homed in the helper
  docstring (013-03) **and** `pdf-to-markdown.md` (013-05).
- **Exit code `10` = `DocumentScanned`** (ARCH §5.2) — exit codes are
  per-script; `pdf_fill_form.py` independently using 10/11/12 is not a
  collision.
- **Whole-doc scan** → exit 10 **and** the dump still emitted to stdout/`-o`;
  `--json-errors` governs only stderr (ARCH §5.2, reviewer M-3).
- **Single file**, no package (ARCH §3.1, D2).
- **`pdf-12` pre-exists** in the backlog — 013-06 *updates* it (refined design),
  does not create it (ARCH §13 identifier note).

### 0.5. Backlog update (user-requested in this `/vdd-plan` run)

Per the user's `+ update docs/office-skills-backlog.md`, task **013-06** updates
the existing `pdf-12` row from its original two-script (`pdf_extract_text.py` /
`pdf_extract_tables.py`, incl. a `--format markdown` mode) scope to TASK 013's
refined design. An interim status edit (`pdf-12` → "🔄 PLANNED — TASK 013")
lands at the end of this planning phase; the row is marked ✅ DONE at merge by
013-06. See §5.

---

## 1. Task Execution Sequence

### Stage 1 — Structure & Stubs

- **Task 013-01** — `[STUB CREATION]` `pdf_extract.py` skeleton + fixtures + test scaffolding
  - RTM: scaffolds [R6][R7][R8][R9]; **completes** [R10][R11]; scaffolds [R12].
  - Use Cases: UC-1, UC-2, UC-3 (all as stub-level smoke).
  - Description file: [`docs/tasks/task-013-01-skeleton-fixtures.md`](tasks/task-013-01-skeleton-fixtures.md)
  - Priority: Critical
  - Dependencies: none (bootstrap).

### Stage 2 — Logic Implementation

- **Task 013-02** — `[LOGIC IMPLEMENTATION]` Extraction core
  - RTM: **completes** [R6]; [R7] (7.1/7.2/7.4 — the per-page dict).
  - Use Cases: UC-1 main + A1–A3.
  - Description file: [`docs/tasks/task-013-02-extraction-core.md`](tasks/task-013-02-extraction-core.md)
  - Priority: High
  - Dependencies: 013-01.

- **Task 013-03** — `[LOGIC IMPLEMENTATION]` Scan classifier
  - RTM: **completes** [R8]; [R7] (7.5 — `scanned_pages`).
  - Use Cases: UC-2 main + A2 (mixed) + A3 (all-blank).
  - Description file: [`docs/tasks/task-013-03-scan-classifier.md`](tasks/task-013-03-scan-classifier.md)
  - Priority: High
  - Dependencies: 013-02.

- **Task 013-04** — `[LOGIC IMPLEMENTATION]` CLI glue + emitter
  - RTM: **completes** [R9]; [R7] (7.3 — output sink).
  - Use Cases: UC-1 main, UC-2 (all + A1 `--json-errors`), UC-3.
  - Description file: [`docs/tasks/task-013-04-cli-and-emit.md`](tasks/task-013-04-cli-and-emit.md)
  - Priority: High
  - Dependencies: 013-03.

### Stage 3 — Reference document

- **Task 013-05** — `[DOC]` `references/pdf-to-markdown.md`
  - RTM: **completes** [R1][R2][R3][R4]; [R5] (5.4 — back-links in the doc).
  - Use Cases: UC-1 (the agent-followed-the-reference acceptance criterion).
  - Description file: [`docs/tasks/task-013-05-reference-doc.md`](tasks/task-013-05-reference-doc.md)
  - Priority: High
  - Dependencies: 013-01 (CLI contract frozen). May run **parallel** to Stage 2.

### Stage 4 — Integration & validation

- **Task 013-06** — `[INTEGRATION]` Skill surface, backlog, validation
  - RTM: **completes** [R5] (5.1/5.2/5.3), [R12] (12.6), [R13].
  - Use Cases: UC-3 (maintainer validation).
  - Description file: [`docs/tasks/task-013-06-integration-validation.md`](tasks/task-013-06-integration-validation.md)
  - Priority: High
  - Dependencies: 013-04 **and** 013-05 (both artifacts must exist before
    `SKILL.md` links them and `validate_skill.py` runs).

**Execution order:** `013-01 → 013-02 → 013-03 → 013-04 → 013-06` ;
`013-05` after `013-01`, before `013-06` (parallel-eligible with Stage 2).

---

## 2. RTM Coverage Matrix

One RTM Issue = one checklist item, prefixed with the RTM ID (planner prompt
§Step-2). "Bead" = the task that **completes** the requirement.

- [ ] **[R1]** Decision tree (digital vs scan vs complex layout) → **013-05**
- [ ] **[R2]** Extraction recipe (per-page text+tables → dump → agent composition) → **013-05**
- [ ] **[R3]** Pitfalls catalogue (multi-column, borderless tables, cross-page stitching, image pages, headings, encrypted, GFM dialect) → **013-05**
- [ ] **[R4]** "MD assembly is the agent's job" framing + Non-goals → **013-05**
- [ ] **[R5]** Linkage / discoverability → **013-06** (5.1–5.3: `SKILL.md` §7.1/§12 + `library-selection.md` cross-link) + **013-05** (5.4: reference back-links `library-selection.md`/`forms.md`)
- [ ] **[R6]** Per-page extraction core (`pdfplumber`, `extract_text`+`extract_tables`, `--layout`, encryption guard) → **013-02**
- [ ] **[R7]** Structured JSON output → **013-02** (7.1/7.2/7.4 per-page dict) + **013-03** (7.5 `scanned_pages`) + **013-04** (7.3 stdout/`-o` sink)
- [ ] **[R8]** Scan detection (`_classify_page`, `_classify_document`, threshold, blank-page rule, exit-10) → **013-03**
- [ ] **[R9]** CLI / contract (argparse, `--json-errors`, exit-code matrix, idempotency) → **013-04**
- [ ] **[R10]** Naming & honesty (`pdf_extract.py`, dump-not-converter docstring + `--help`, JSON-only) → **013-01**
- [ ] **[R11]** Test fixtures (digital, scan-like, encrypted) → **013-01**
- [ ] **[R12]** E2E tests → **013-01** (scaffold, RED) + **013-02/03/04** (turn green per `tdd-stub-first §2.4`) + **013-06** (12.6: `test_e2e.sh` smoke block)
- [ ] **[R13]** `validate_skill.py` green + `SKILL.md` surface + backlog → **013-06**

**No orphan requirement.** Every R1–R13 has a completing bead; the multi-bead
requirements (R5, R7, R12) name the primary bead and the split explicitly.

---

## 3. Use Case Coverage

| Use Case | Tasks |
|----------|-------|
| UC-1 — digital PDF → Markdown | 013-01 (smoke), 013-02 (dump), 013-04 (CLI), 013-05 (reference) |
| UC-2 — scanned PDF → loud signal | 013-01 (smoke), 013-03 (classifier), 013-04 (exit 10 + `--json-errors`) |
| UC-3 — maintainer validation | 013-01 (test scaffold), 013-04 (full E2E green), 013-06 (`validate_skill.py`, `diff -q`) |

---

## 4. Stub-First Gate Inventory

Per `tdd-stub-first §1–§2`, each task file specifies its gate. Summary:

| Task | Stub-First role |
|------|-----------------|
| 013-01 | Creates ALL stubs (sentinel returns) + ONE smoke E2E that passes on stubs (Red→Green). Frozen surface — no later task renames a public symbol. |
| 013-02 | Replaces extraction stubs; **updates** the smoke E2E + adds the digital-fixture E2E asserting real values. |
| 013-03 | Replaces classifier stubs; updates E2E to assert real `scanned`/`doc_scanned` on the scan-like + all-blank fixtures. |
| 013-04 | Replaces `main`/`_emit` stubs; full E2E green incl. exit-code matrix, idempotency, encrypted path. |
| 013-05 | Documentation — no stub phase; verified by content checklist + the UC-1 "agent follows the reference" criterion. |
| 013-06 | Integration — no stub phase; verified by `validate_skill.py` exit 0 + full suite green. |

### Honest-scope locks (TASK §1.4 / ARCH §10)

Each is documented in the named file by the named task:

- §1.4(a) MD composition is agent's job → docstring (013-01) + reference (013-05).
- §1.4(b) OCR not bundled → reference decision tree (013-05).
- §1.4(c) default `extract_tables()` only → docstring (013-02) + reference (013-05).
- §1.4(d) `has_images` only, no image bytes → docstring (013-02).
- §1.4(e)/(f) `--layout` no reflow; `char_count` layout inflation → docstring (013-02) + ARCH §4.3 note echoed in 013-03.
- §1.4(g) no streaming emit → docstring (013-04).
- §1.4(h) no decompression-bomb hardening → docstring (013-02).
- §1.4(i) `--password` argv-only → `--help` text (013-01) + reference (013-05).

---

## 5. Backlog Update (`docs/office-skills-backlog.md`)

The user requested the backlog be updated in this `/vdd-plan` run.

- **Now (end of planning):** the existing `pdf-12` row (line ~219) and its
  §7-prioritisation mentions are rewritten from the two-script
  (`pdf_extract_text.py` / `pdf_extract_tables.py` + `--format markdown`) scope
  to TASK 013's refined design (single `pdf_extract.py` JSON dump +
  `references/pdf-to-markdown.md`, scan-detection, no markdown-from-script),
  and the row is marked **🔄 PLANNED — TASK 013 (VDD spec+arch+plan approved)**.
- **At merge:** task **013-06** flips the row to **✅ DONE** with the final
  validation evidence (per R13.4).

---

## 6. Definition of Done (plan-level)

- All 6 task files created under `docs/tasks/task-013-NN-*.md`.
- Every RTM item R1–R13 bound to a completing bead (§2) — no orphan.
- Stub-First two-pass structure (§4) — 013-01 stubs, 013-02/03/04 logic.
- Plan-Reviewer approval recorded in `docs/reviews/plan-013-review.md`.

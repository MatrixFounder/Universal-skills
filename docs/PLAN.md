# Development Plan: TASK 014 — `pdf-7` PDF outline (TOC bookmarks)

> **Mode:** VDD (Verification-Driven Development) + Stub-First.
> **Status:** DRAFT v1 — pending Plan-Reviewer approval.
> **TASK:** [TASK.md](TASK.md) (TASK 014, slug `pdf-outline-bookmarks`, backlog row `pdf-7`).
> **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md) (TASK 014 — verify-and-lock
> weasyprint outline + chrome-engine `page.pdf(outline=True, tagged=True)` parity).
> **Amended 2026-05-22 (v2):** during 014-02 development, Chromium was found to
> require `page.pdf(tagged=True)` alongside `outline=True` for the outline to
> appear (`outline` alone → 0 bookmarks). TASK/ARCH/this plan + task files were
> amended (user-confirmed scope amendment); the chrome change is now two
> keyword args. See TASK 014 §1.1a.
> **Prior plan archived:** [plans/plan-013-pdf-to-markdown.md](plans/plan-013-pdf-to-markdown.md).
> **Atomic-chain hint (architect handoff):** [ARCHITECTURE.md §11](ARCHITECTURE.md).

---

## 0. Strategy Summary

### 0.1. Chainlink Decomposition Overview

Every RTM Issue from TASK §2 (R1..R9, 9 IDs across 3 Epics) is decomposed into
**Beads** — atomic sub-issues, each implementable in a single sitting (2–4 h)
and verifiable through a single test cluster. Beads are grouped into **3
module-scoped tasks** (`task-014-NN-*.md`).

This is a small modification of one existing skill: one verified-and-locked
behaviour (weasyprint outline), one ~1-line code change (chrome engine), one
dependency-floor bump, one installer fix, a new test-only helper, three E2E
test blocks, and documentation. No new module, no new dependency, no
cross-skill replication (ARCH §3.1, §9).

### 0.2. Phasing (Stub-First — test-first adaptation)

This task has **no large new production surface to stub**, so the Stub-First
two-pass discipline maps onto a **test-first** ordering, exactly as
[ARCHITECTURE.md §3.1](ARCHITECTURE.md) sets out and the Architecture-Reviewer
approved:

- **Phase 1 — Structure & Tests (`[STUB + TEST]`) — task 014-01.** Create the
  test-only helper `tests/_outline_probe.py` and the two **weasyprint** outline
  test blocks in `test_e2e.sh`. These pass on the **unmodified** code — that
  Green run *is* the Part-A verification (R1): it proves `md2pdf.py` and
  `html2pdf.py` already emit the outline. The "stub" being verified is the
  current production behaviour itself; the test asserts the (already-correct)
  observed values, satisfying `tdd-stub-first §1.4`.

- **Phase 2 — Logic Implementation (`[LOGIC IMPLEMENTATION]`) — task 014-02.**
  Add the **chrome** outline test block (RED — chrome omits the outline),
  then make it GREEN by adding `outline=True` **and `tagged=True`** to
  `render_chrome()`'s `page.pdf()` call; bump the Playwright floor; fix
  `install.sh`. This is the
  literal Stub-First Red→Green gate (`tdd-stub-first §2`): the failing test is
  written first, the logic change turns it green — both inside 014-02 so the
  task ends Green.

- **Phase 3 — Integration & Documentation (`[INTEGRATION]`) — task 014-03.**
  `SKILL.md` surface, `references/html-conversion.md` note, the `pdf-7` backlog
  row, `validate_skill.py` exit 0, full regression, cross-skill `diff -q`
  silent gate. Pure docs + validation; no stub phase.

> **Atomicity check:** each task targets one coherent artifact cluster + its
> tests, within the 2–4 h budget per `planning-decision-tree`.

### 0.3. Cross-skill replication gate

**This task replicates nowhere.** Every new/edited file lives under
`skills/pdf/` (+ `docs/`). No replicated file (`office/`, `_soffice.py`,
`_errors.py`, `preview.py`, `office_passwd.py`) is touched (ARCH §9). The
2-line `diff -q` silent gate appears in **every** task file's Acceptance
Criteria:

```bash
diff -q skills/docx/scripts/_errors.py  skills/pdf/scripts/_errors.py
diff -q skills/docx/scripts/preview.py  skills/pdf/scripts/preview.py
```

Both MUST produce no output. (pdf has no `office/` directory → the `office/`
`diff -qr` is N/A.)

### 0.4. Decisions locked from TASK + ARCHITECTURE (no blocking questions)

Recorded here in case the Plan-Reviewer would have asked — all resolved
upstream:

- **`outline=True` + `tagged=True` hardcoded** at the `page.pdf()` call site —
  both required (Chromium couples them; TASK §1.1a — v2 amendment); no new
  `render_chrome()` parameter, no `--no-outline` CLI flag (ARCH D2, TASK Q-2).
- **Playwright floor `>=1.42`** — the release that added `page.pdf(outline=...)`
  **and `tagged=...`** (ARCH D3, TASK Q-4); plus `install.sh --with-chrome` installs with
  `--upgrade` so a pdf-11-era under-floor install is lifted (ARCH D4, TASK M-1).
- **`_outline_probe.py`** is a new **test-only** helper mirroring
  `tests/_acroform_fixture.py`; exit-3 is a private test sentinel, not an
  `_errors.py` code (ARCH D5, §5.4).
- **Fixtures inline** (heredoc into `$TMP`); no committed fixture / `.pdf`
  files (ARCH D6).
- **Chrome outline test soft-skips** when Playwright/Chromium is absent —
  mirrors the `mermaid_renders` pattern (ARCH D7).
- **Chrome test fixture is plain content** (no `position:fixed` chrome) so the
  assertion is not coupled to `_DOM_NORMALIZE_SCRIPT` (ARCH D8).
- **No `THIRD_PARTY_NOTICES.md` change** — a version-floor bump on an
  already-declared dependency is not a new dependency (ARCH §6, TASK R5.4).

### 0.5. Backlog update

Task **014-03** updates the existing `docs/office-skills-backlog.md` `pdf-7`
row (line ~214) to **✅ DONE**, corrects the stale *"Сейчас только in-page
links"* note, and reconciles every other `pdf-7` occurrence (the package list
~line 613, the P1 prioritisation bullet ~line 689, the day-3 schedule ~line
720 — **grep**, do not trust offsets). See §5.

---

## 1. Task Execution Sequence

### Stage 1 — Structure & Tests (verify-and-lock, Part A)

- **Task 014-01** — `[STUB + TEST]` `_outline_probe.py` helper + weasyprint outline E2E blocks
  - RTM: **completes** [R1][R2][R3].
  - Use Cases: UC-1 (main + A1 `--no-default-css`); UC-3 (test scaffold).
  - Description file: [`docs/tasks/task-014-01-outline-probe-and-weasyprint-tests.md`](tasks/task-014-01-outline-probe-and-weasyprint-tests.md)
  - Priority: High
  - Dependencies: none (bootstrap).

### Stage 2 — Logic Implementation (chrome parity, Part B)

- **Task 014-02** — `[LOGIC IMPLEMENTATION]` Chrome-engine `page.pdf(outline=True, tagged=True)` + Playwright floor + installer
  - RTM: **completes** [R4][R5][R6].
  - Use Cases: UC-2 (main + A1 chrome-absent + A2 old-Playwright).
  - Description file: [`docs/tasks/task-014-02-chrome-outline-parity.md`](tasks/task-014-02-chrome-outline-parity.md)
  - Priority: High
  - Dependencies: 014-01 (the `_outline_probe.py` helper + the `test_e2e.sh`
    outline section it extends must exist).

### Stage 3 — Integration & Documentation

- **Task 014-03** — `[INTEGRATION]` Skill surface, reference note, backlog, validation
  - RTM: **completes** [R7][R8][R9].
  - Use Cases: UC-3 (maintainer validation).
  - Description file: [`docs/tasks/task-014-03-docs-backlog-validation.md`](tasks/task-014-03-docs-backlog-validation.md)
  - Priority: High
  - Dependencies: 014-02 (the chrome behaviour + the full test surface must
    exist before docs describe them and `validate_skill.py` runs).

**Execution order:** `014-01 → 014-02 → 014-03` (strict linear).

---

## 2. RTM Coverage Matrix

One RTM Issue = one checklist item, prefixed with the RTM ID (planner prompt
§Step-2). "Bead" = the task that **completes** the requirement.

- [ ] **[R1]** Verify weasyprint emits the PDF outline out of the box (md2pdf, html2pdf, `--no-default-css`) → **014-01**
- [ ] **[R2]** `md2pdf.py` outline regression test (non-empty, nested, titled) → **014-01**
- [ ] **[R3]** `html2pdf.py` weasyprint-engine outline regression test (incl. `--no-default-css` variant) → **014-01**
- [ ] **[R4]** Chrome engine emits the PDF outline (`page.pdf(outline=True, tagged=True)`) → **014-02**
- [ ] **[R5]** Playwright version floor `>=1.42` + `install.sh --upgrade` + no `THIRD_PARTY_NOTICES.md` change → **014-02**
- [ ] **[R6]** Chrome-engine outline regression test (soft-skip + R6.4 capability probe) → **014-02**
- [ ] **[R7]** Documentation & honesty discipline (`SKILL.md` §2; `references/html-conversion.md` note; honest scope) → **014-03**
- [ ] **[R8]** Backlog update (`pdf-7` row → ✅ DONE; stale note corrected; all occurrences reconciled) → **014-03**
- [ ] **[R9]** Validation gate (`validate_skill.py` exit 0; full `test_e2e.sh` green; cross-skill `diff -q` silent; no regression) → **014-03**

**No orphan requirement.** Every R1–R9 has exactly one completing bead.

---

## 3. Use Case Coverage

| Use Case | Tasks |
|----------|-------|
| UC-1 — reader navigates a generated PDF via bookmarks (weasyprint) | 014-01 (R1/R2/R3 tests + verification) |
| UC-2 — agent renders HTML→PDF via chrome engine (parity fix) | 014-02 (R4/R5/R6 — `outline=True`+`tagged=True`, floor, chrome test) |
| UC-3 — maintainer validates the skill | 014-01 (test scaffold), 014-03 (`validate_skill.py`, full suite, `diff -q`) |

---

## 4. Stub-First Gate Inventory

Per `tdd-stub-first §1–§2`, each task file specifies its gate. Summary:

| Task | Stub-First role |
|------|-----------------|
| 014-01 | **Phase 1 (test-first).** Writes `_outline_probe.py` + the two weasyprint test blocks. They pass on the **unmodified** production code — the Green run asserts the already-correct observed outline (`tdd-stub-first §1.4`) and *is* the R1 verification. No production code is changed in this task. |
| 014-02 | **Phase 2 (Red→Green).** Adds the chrome outline test block (RED — chrome lacks the outline), then implements `page.pdf(outline=True, tagged=True)` to turn it GREEN — the literal `tdd-stub-first §2` gate, both halves inside one task so it ends Green. |
| 014-03 | Integration — no stub phase; verified by `validate_skill.py` exit 0 + full suite green. |

### Honest-scope locks (TASK §1.4 / ARCH §10)

Each is documented in the named file by the named task:

- §1.4(a) outline from real `h1`–`h6` only → `SKILL.md` §2 + reference (014-03).
- §1.4(b) reader-mode / preprocessing / `_DOM_NORMALIZE_SCRIPT` may hide
  headings → reference note (014-03); chrome test fixture is plain content
  (014-02).
- §1.4(c) PDF/UA tagging out of scope → `SKILL.md` §2 + reference (014-03).
- §1.4(d) cross-engine trees not byte-identical → test comments (014-01/02).
- §1.4(e) chrome opt-in → chrome test soft-skips (014-02).
- §1.4(f) headings in hidden chrome absent from outline → chrome test
  fixture + reference (014-02/03).
- §1.4(g) / A-6 `emulate_media("screen")` verification point → recorded by the
  014-02 chrome test.

---

## 5. Backlog Update (`docs/office-skills-backlog.md`)

Task **014-03** performs the update at merge:

- The `pdf-7` row (~line 214) `Status` → **✅ DONE** with a one-line evidence
  summary; the **`Notes` column** *"Сейчас только in-page links"* is corrected
  (weasyprint emits the outline out of the box; chrome parity added by this
  task).
- Every other `pdf-7` mention is reconciled — **grep `pdf-7`**, do not trust
  line offsets: the package list (~613), the P1 prioritisation bullet (~689),
  the day-3 schedule (~720).

---

## 6. Definition of Done (plan-level)

- All 3 task files created under `docs/tasks/task-014-NN-*.md`.
- Every RTM item R1–R9 bound to a completing bead (§2) — no orphan.
- Stub-First two-pass structure (§4) — 014-01 test-first verify, 014-02
  Red→Green logic.
- Plan-Reviewer approval recorded in `docs/reviews/plan-014-review.md`.

# TASK 014 — pdf-7: PDF outline (TOC bookmarks) for the pdf skill

> **Mode:** VDD (Verification-Driven Development).
> **Status:** DRAFT v2 — **amended 2026-05-22** during development (Task 014-02):
> Chromium emits the PDF outline **only** when `page.pdf(tagged=True)` is also
> set (`outline=True` alone → 0 bookmarks, empirically verified). The DRAFT-v1
> non-goal "no tagged PDF" is therefore revised — `tagged=True` is a *mandatory,
> accepted side-effect* of the chrome outline (user-confirmed via AskUserQuestion
> 2026-05-22). Changed: §1.1a (new), §1.2, §1.3, §1.4(c), R4, R7.3, §4, A-3, Q-3,
> §7, UC-2. Re-reviewed and **APPROVED** 2026-05-22 (see
> `docs/reviews/task-014-review.md`).
> **Predecessors (context, not dependencies):**
> - pdf-5 — `html2pdf.py` + `html2pdf_lib/` weasyprint converter — ✅ MERGED.
> - pdf-11 — `html2pdf.py --engine chrome` (Playwright/Chromium opt-in engine) — ✅ MERGED.
>   This TASK touches the chrome engine added by pdf-11.
> - TASK 013 / pdf-12 — PDF→Markdown — ✅ MERGED (archived
>   `docs/tasks/task-013-pdf-to-markdown-master.md`). Unrelated surface.

---

## 0. Meta Information

- **Task ID:** `014`
- **Slug:** `pdf-outline-bookmarks`
- **Target skill:** `skills/pdf/` (Proprietary — see root `CLAUDE.md` §3,
  `skills/pdf/LICENSE` / `skills/pdf/NOTICE`).
- **Backlog row:** `pdf-7` — **already exists** in
  [`docs/office-skills-backlog.md`](office-skills-backlog.md) line ~214:
  *"TOC bookmarks (PDF outline) — weasyprint умеет: добавить `<h1-h6>` → PDF
  outline. Уже из коробки или нужен CSS-флаг? Проверить и при необходимости
  добавить. Сейчас только in-page links."* Effort **S**, Value **M**. R8
  updates this row at merge.
- **Cross-skill replication:** **None.** Every file this task edits is
  pdf-only:
  - `skills/pdf/scripts/html2pdf_lib/chrome_engine.py` — pdf-only package module.
  - `skills/pdf/scripts/requirements-chrome.txt` — pdf-only (chrome engine).
  - `skills/pdf/scripts/tests/*` — pdf-only test surface.
  - `skills/pdf/SKILL.md`, `skills/pdf/references/*` — pdf-only docs.

  The CLAUDE.md §2 replication protocol is **not triggered**: this task touches
  **none** of the replicated files (`office/`, `_soffice.py`, `_errors.py`,
  `preview.py`, `office_passwd.py`). The cross-skill `diff -q` matrix MUST stay
  silent after this task lands (R9.3).
- **Mode flag:** Standard VDD (no `[LIGHT]`).
- **New dependency:** **None.** `requirements-chrome.txt` already declares
  `playwright`; this task only **raises its version floor** (`>=1.40` →
  `>=1.42`). A version-floor bump on an already-declared dependency is **not** a
  new dependency — no `THIRD_PARTY_NOTICES.md` change is required by this task
  (see R5.4).
- **Reference docs:**
  - Render orchestration (weasyprint path): [`skills/pdf/scripts/html2pdf_lib/render.py`](../skills/pdf/scripts/html2pdf_lib/render.py).
  - Chrome engine (the gap): [`skills/pdf/scripts/html2pdf_lib/chrome_engine.py`](../skills/pdf/scripts/html2pdf_lib/chrome_engine.py).
  - Markdown→PDF converter: [`skills/pdf/scripts/md2pdf.py`](../skills/pdf/scripts/md2pdf.py).
  - Existing E2E harness + the mermaid soft-skip pattern this task mirrors:
    [`skills/pdf/scripts/tests/test_e2e.sh`](../skills/pdf/scripts/tests/test_e2e.sh).

---

## 1. General Description

### 1.1. Goal

A PDF **outline** (a.k.a. *bookmarks* / *document outline* — the navigable
heading tree shown in a PDF viewer's sidebar) makes a multi-page PDF navigable.
Backlog row `pdf-7` asks a **verification question**: does the pdf skill's
PDF generation already emit an outline from `<h1>`–`<h6>`, or is a CSS flag /
code change needed? — *"Проверить и при необходимости добавить."*

**Verification result (established during this TASK's Analysis-phase
reconnaissance, 2026-05-22 — to be re-confirmed and locked by the
implementation):**

| Path | PDF outline today? |
|------|--------------------|
| `md2pdf.py` (weasyprint) | ✅ **Already emitted** — correct nested tree from `h1`–`h6` |
| `html2pdf.py` default engine (weasyprint) | ✅ **Already emitted** — same |
| `html2pdf.py --engine chrome` (Playwright) | ❌ **Gap** — `page.pdf()` omits `outline=True` **and the `tagged=True` Chromium requires alongside it** (see §1.1a) |

WeasyPrint's HTML5 user-agent stylesheet sets `bookmark-level` / `bookmark-label`
on `h1`–`h6`, so **both weasyprint paths produce the outline out of the box** —
**no CSS flag is needed**, and the bundled `DEFAULT_CSS` does not override those
properties. The backlog note *"Сейчас только in-page links"* is therefore
**stale** for the weasyprint paths and is corrected by this task (R8.2).

The one genuine gap is the **opt-in `--engine chrome`** path added by pdf-11:
its `page.pdf(...)` call in `render_chrome()` does not emit an outline, so a
chrome-rendered PDF has no bookmark tree. This task closes that gap so the
outline is **engine-agnostic**.

### 1.1a. Implementation finding (2026-05-22): Chromium couples `outline` to `tagged`

During development (Task 014-02) a controlled Playwright probe established that
Chromium's `page.pdf(outline=True)` produces a PDF outline **only when
`tagged=True` is also passed**:

| `page.pdf(...)` flags | Outline bookmarks emitted |
|-----------------------|---------------------------|
| `outline=True` only   | **0** |
| `tagged=True` only    | 0 |
| `outline=True, tagged=True` | **correct nested outline** |
| neither               | 0 |

Chromium builds the document outline from the **tagged-PDF structure tree**, so
`outline=True` is inert without `tagged=True`. Delivering the chrome outline
(R4) is therefore **impossible** without also passing `tagged=True` — which
makes the chrome-rendered PDF a *tagged PDF*. The DRAFT-v1 spec treated tagged
PDF as a non-goal; this is revised in §1.2 / Q-3 (user-confirmed amendment,
AskUserQuestion 2026-05-22). The weasyprint paths are **unaffected** — their
outline (`bookmark-level`) is independent of tagging.

This task therefore delivers, in two parts:

- **Part A — Verify & lock (no behaviour change).** Empirically confirm the
  weasyprint out-of-box behaviour and pin it with **regression tests** so a
  future CSS edit or a `--no-default-css` run cannot silently strip the outline.
- **Part B — Chrome-engine parity (behaviour change, user-confirmed in scope —
  2026-05-22).** Add `outline=True` **and `tagged=True`** to the chrome engine's
  `page.pdf()` call (both required — §1.1a) and raise the
  `requirements-chrome.txt` floor to the Playwright release that introduced
  those options.

### 1.2. What is deliberately NOT being built (Non-goals)

These are first-class requirements — the design must actively avoid them:

- **No PDF/UA accessibility *conformance*.** The chrome engine's outline is
  produced by `page.pdf(outline=True, tagged=True)`, and `tagged=True` is
  **mandatory** — Chromium builds the outline from the tagged-PDF structure
  tree, so `outline=True` alone yields zero bookmarks (§1.1a, A-3).
  Consequently a chrome-rendered PDF is now a **tagged PDF**: this is an
  **accepted, necessary side-effect** of delivering the outline, *not* a
  separately-pursued feature. What **remains out of scope**: any **PDF/UA
  conformance claim**, validation of the tagged structure's quality,
  screen-reader testing, and tagging of the **weasyprint** path (weasyprint's
  `bookmark-level` outline needs no tagging — it is left untagged). The skill
  states plainly that chrome PDFs are tagged but makes no accessibility-
  conformance promise (R7.3).
- **No `--no-outline` opt-out flag.** weasyprint emits the outline
  unconditionally and exposes no toggle; a chrome-only opt-out would be
  asymmetric, and a navigable outline is universally beneficial. No new CLI
  surface is added (see Q-2).
- **No custom outline labelling / depth control.** No mechanism to remap which
  tags become bookmarks, cap outline depth, or rewrite bookmark text. The
  outline is exactly the document's `h1`–`h6` tree as each engine derives it.
- **No new `md2pdf.py` / `html2pdf.py` behaviour beyond the chrome fix.** The
  weasyprint paths already work; this task **adds tests around them**, it does
  not change how they render.

### 1.3. Connection with the existing system

**Verifies & locks (no modification):**
- `md2pdf.py` — its weasyprint render already emits the outline; this task adds
  a regression test, no code change.
- `html2pdf_lib/render.py` weasyprint branch — already emits the outline; this
  task adds a regression test (incl. a `--no-default-css` variant), no code
  change.

**Modifies:**
- `html2pdf_lib/chrome_engine.py` — `render_chrome()`'s `page.pdf(...)` call
  gains `outline=True` **and `tagged=True`** (both required — §1.1a; the only
  behavioural code change).
- `requirements-chrome.txt` — Playwright version floor `>=1.40` → `>=1.42`.
- `install.sh` — the `--with-chrome` `requirements-chrome.txt` install gains
  `--upgrade` (R5.3).

**Adds:**
- Regression tests + fixtures for the outline on all three paths, wired into
  `test_e2e.sh`.
- Documentation of the (now engine-agnostic) outline behaviour in `SKILL.md`
  and the relevant `references/` doc.

**Out of scope (do NOT touch):**
- The replicated cross-skill files (`office/`, `_soffice.py`, `_errors.py`,
  `preview.py`, `office_passwd.py`) — untouched (Meta; R9.3).
- `pdf_merge.py`, `pdf_split.py`, `pdf_watermark.py`, `pdf_fill_form.py`,
  `pdf_extract.py`, `preview.py` — no behavioural change.
- The other three office skills (`docx`, `xlsx`, `pptx`) — untouched.
- The `html2pdf_lib/` preprocessing / reader-mode pipeline — not changed.

### 1.4. Honest scope (explicitly out of scope or deferred)

Each item below MUST be documented in the relevant file (SKILL.md / reference
prose) so documentation never overstates the deliverable:

- **(a)** The outline is derived **only from real `<h1>`–`<h6>` tags**. Visually
  "heading-like" content built from styled `<p>` / `<div>` / `<span>` does NOT
  appear in the outline. This is correct behaviour, not a bug.
- **(b)** In `html2pdf.py`, `--reader-mode` and the preprocessing pipeline
  (and, in the chrome engine, `_DOM_NORMALIZE_SCRIPT` — which `display:none`s
  non-substantial `position:fixed` chrome and hides non-portal body children
  when a modal is released) may remove or hide chrome/nav headings before
  render; the outline reflects whatever headings **survive visible** to the
  rendered document. This is correct behaviour — hidden chrome should not
  pollute the outline.
- **(c)** The chrome engine now emits a **tagged PDF** — Chromium requires
  `tagged=True` to produce the outline (§1.1a). This incidentally improves
  accessibility, but `pdf-7` makes **no PDF/UA conformance claim** and does not
  validate the tagged structure's quality. The weasyprint paths are **not**
  tagged — their `bookmark-level` outline needs no tagging.
- **(d)** The chrome-engine outline is produced by Chromium's own
  outline-from-headings logic via `page.pdf(outline=True)`; its grouping/nesting
  may differ in edge cases from weasyprint's `bookmark-level` algorithm. Parity
  is asserted at the level of *"a non-empty, hierarchically nested outline is
  present"* (R6.3), not byte-identical trees across engines.
- **(e)** The chrome engine remains an **opt-in** path requiring
  `install.sh --with-chrome`; when Playwright/Chromium is absent the chrome
  outline test **soft-skips** (R6.2) — exactly as the existing mermaid PNG test
  soft-skips a missing headless Chrome.

---

## 2. Requirements Traceability Matrix (RTM)

Requirements are grouped into **3 Epics**. MVP column: ✅ = required for this
task to be "done"; ⬜ = nice-to-have / may defer. All 9 are ✅.

### Epic E1 — Part A: Verify & regression-lock the weasyprint outline

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R1** | Verify weasyprint emits the PDF outline out of the box | ✅ | (1.1) Confirm `md2pdf.py` produces a non-empty, nested outline from `h1`–`h6` on a multi-heading fixture. Note: `md2pdf.py` exposes **no** CSS-suppression flag (`--no-default-css` exists only on `html2pdf.py`), so the R1.3 / R3.2 `--no-default-css` regression lock is inherently `html2pdf.py`-only — the R2 `md2pdf.py` outline test needs no `--no-default-css` variant. (1.2) Confirm `html2pdf.py` default (weasyprint) engine produces the same. (1.3) Confirm `html2pdf.py --no-default-css` still produces the outline — i.e. the outline is owned by weasyprint's UA stylesheet, **not** the bundled `DEFAULT_CSS` (the bundled CSS must not override `bookmark-level` / `bookmark-label`). (1.4) Record the verification outcome so R8.2 can correct the stale backlog note. |
| **R2** | `md2pdf.py` outline regression test | ✅ | (2.1) An automated test renders a Markdown fixture with `h1`/`h2`/`h3` headings and asserts the produced PDF has a **non-empty** outline. (2.2) Asserts **hierarchy**: an `h1 > h2 > h3` source yields a correspondingly **nested** bookmark tree (not a flat list). (2.3) Asserts bookmark **titles** match the heading text. (2.4) Wired so `bash skills/pdf/scripts/tests/test_e2e.sh` exercises it. |
| **R3** | `html2pdf.py` weasyprint-engine outline regression test | ✅ | (3.1) An automated test renders a multi-heading HTML fixture through `html2pdf.py` (default engine) and asserts a non-empty nested outline. (3.2) A second variant runs with `--no-default-css` and asserts the outline is **still** present (locks R1.3 — guards against a future regression where suppressing the bundled CSS is wrongly assumed to suppress bookmarks). (3.3) Wired into `test_e2e.sh`. |

### Epic E2 — Part B: Chrome-engine outline parity

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R4** | Chrome engine emits the PDF outline | ✅ | (4.1) `render_chrome()` in `chrome_engine.py` passes **`outline=True` and `tagged=True`** to the `page.pdf(...)` call. **Both are required** — Chromium builds the document outline from the tagged-PDF structure tree, so `outline=True` alone produces an empty outline (§1.1a, A-3); `tagged=True` makes the chrome PDF a tagged PDF, an accepted side-effect (§1.2). (4.2) Behavioural parity: a multi-heading HTML rendered via `html2pdf.py --engine chrome` produces a **non-empty, nested** outline — closing the gap identified in §1.1 (see A-6 re: the `emulate_media("screen")` interaction). (4.3) The chrome engine strips `<script>` tags and injects layout-normalisation CSS but **retains `<h1>`–`<h6>` content elements** — confirm headings survive script-stripping and CSS injection so Chromium's outline logic has input. **Honest-scope caveat:** a heading inside DOM-normalised hidden chrome (a `position:fixed` sidebar/header that `_DOM_NORMALIZE_SCRIPT` sets to `display:none`, or a non-portal body child hidden when a modal is released) is intentionally **absent** from the chrome outline — consistent with §1.4(b); the R6 fixture is plain content with no fixed-position chrome so the assertion is not coupled to this. (4.4) The change is additive — the two new keyword arguments (`outline`, `tagged`) are **appended after** the existing `page.pdf()` arguments (`path`, `format`, `print_background`, `scale`, `margin`), which are left unchanged in place; no other render path regresses. |
| **R5** | Playwright version floor | ✅ | (5.1) `requirements-chrome.txt` floor raised `playwright>=1.40,<2.0` → `playwright>=1.42,<2.0` — Playwright **1.42** is the release that added the `page.pdf()` **`outline` and `tagged`** options (both used by R4.1); `>=1.40` could resolve to 1.40/1.41 where `page.pdf(outline=True, tagged=True)` raises `TypeError`. (5.2) A comment in `requirements-chrome.txt` records *why* the floor is 1.42 (the `outline` option). (5.3) `install.sh --with-chrome` (the `pip install ... -r requirements-chrome.txt` line, ~107) MUST install with **`--upgrade`** so re-running the installer upgrades an already-present **too-old** Playwright (1.40/1.41 from a pdf-11-era install) — a plain `pip install -r` does **not** upgrade an already-satisfied package, so the floor bump alone would not protect that install path. The `ChromeEngineUnavailable` remediation text is reviewed for consistency. (5.4) Confirm a floor bump on an already-declared dependency requires **no** `THIRD_PARTY_NOTICES.md` edit (it is not a new dependency); any pre-existing Playwright-attribution gap from pdf-11 is **out of scope** for this task. |
| **R6** | Chrome-engine outline regression test (soft-skip) | ✅ | (6.1) An automated test renders a **plain-content** multi-heading HTML fixture (no fixed-position chrome — see R4.3) via `--engine chrome` and asserts a non-empty outline. (6.2) **Soft-skip** when Playwright / Chromium is not installed — mirror the existing `mermaid_renders` soft-skip in `test_e2e.sh` (a missing opt-in dependency is a coverage gap, **not** a suite failure / hard abort). (6.3) When the chrome engine **is** available, the test asserts the outline is non-empty **and** nested (parity with R3, at the §1.4(d) granularity), and records whether `emulate_media("screen")` altered the outline (A-6 verification point). (6.4) When chrome is available, the test **probes** that the resolved Playwright's `page.pdf()` accepts the `outline` keyword — e.g. `"outline" in inspect.signature(Page.pdf).parameters` — and fails **loudly** if it does not, turning a silent `TypeError` from an under-floor Playwright (R5.3) into a diagnosed failure. (Note: `playwright.__version__` is **not** a reliable probe — the module exposes no such attribute; use the `page.pdf` signature.) |

### Epic E3 — Documentation, skill surface, backlog, validation

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R7** | Documentation & honesty discipline | ✅ | (7.1) `SKILL.md` §2 Capabilities states that `md2pdf.py` / `html2pdf.py` produce a navigable PDF **outline (bookmarks)** from document headings. (7.2) `references/html-conversion.md` (the natural home — it already documents `--no-default-css` and the `--engine` flag) gains a short note: the outline is automatic from `h1`–`h6`, is engine-agnostic after this task, needs no CSS flag, and `--no-default-css` does not disable it; the note also records that the **chrome engine emits a tagged PDF** (the `tagged=True` mechanism — §1.1a). (7.3) The §1.4 honest-scope items are documented — explicitly that the chrome engine emits a **tagged PDF** (the outline mechanism), that this is **not** a PDF/UA conformance claim, and that the weasyprint paths are not tagged. (7.4) `SKILL.md` §10 Quick Reference / §12 Resources reviewed for consistency; updated only if an existing row is now inaccurate. |
| **R8** | Backlog update | ✅ | (8.1) `docs/office-skills-backlog.md` `pdf-7` row marked **✅ DONE** with a one-line evidence summary. (8.2) The stale *"Сейчас только in-page links"* note is corrected: the outline is emitted out of the box on the weasyprint paths; chrome-engine parity is added by this task. (8.3) Every other `pdf-7` occurrence in the backlog (grep the file — e.g. the §7 prioritisation list and the day-3 schedule; line offsets shift as the backlog is edited) is reconciled with the done status. |
| **R9** | Validation gate | ✅ | (9.1) `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/pdf` exits 0. (9.2) `bash skills/pdf/scripts/tests/test_e2e.sh` passes, including the new R2 / R3 / R6 outline checks (R6 soft-skipping cleanly when chrome is absent). (9.3) Cross-skill `diff -q` matrix stays **silent** — this task edits no replicated file: `diff -qr skills/docx/scripts/office skills/pdf/scripts/office` is N/A (pdf has no `office/`), and `diff -q` on `_errors.py` / `preview.py` between docx and pdf produces no output. (9.4) No regression in the pre-existing pdf test suites (`test_battery.py`, `test_preprocess.py`, `test_pdf_extract.py`). |

**RTM coverage:** 9 requirements across 3 Epics, all MVP-✅, no orphan
requirements.

---

## 3. List of Use Cases

### UC-1 — A reader navigates a generated PDF via its bookmark sidebar

#### 3.1.1. Actors
- **Agent** (Claude Code) — runs `md2pdf.py` / `html2pdf.py`.
- **System** — the pdf skill's converters + weasyprint.
- **End user** — opens the PDF in a viewer (Preview, Acrobat, browser).

#### 3.1.2. Preconditions
- A Markdown or HTML source with a real heading structure (`#`/`<h1>` …).
- The pdf skill is installed (`weasyprint` available).

#### 3.1.3. Main Scenario
1. The agent runs `python3 scripts/md2pdf.py report.md report.pdf` (or
   `html2pdf.py report.html report.pdf`).
2. The System renders via weasyprint; weasyprint's UA stylesheet maps each
   `h1`–`h6` to a `bookmark-level`, producing a nested PDF outline.
3. The end user opens `report.pdf`; the viewer's sidebar shows a clickable,
   hierarchically nested bookmark tree matching the document's headings.

#### 3.1.4. Alternative Scenarios
- **A1 — `--no-default-css`.** The agent suppresses the bundled stylesheet
  (`html2pdf.py --no-default-css`). The outline is **still present** — it is
  owned by weasyprint's UA stylesheet, not the bundled CSS (R1.3, R3.2).
- **A2 — Headingless document.** A source with no `h1`–`h6` produces a PDF with
  an **empty** outline. This is correct — there is nothing to outline; no error.
- **A3 — Reader-mode.** `html2pdf.py --reader-mode` extracts the main article;
  the outline reflects the headings inside the extracted content (§1.4(b)).

#### 3.1.5. Postconditions
- The PDF carries a navigable outline faithful to the source heading tree; no
  CSS flag or extra step was required of the agent.

#### 3.1.6. Acceptance Criteria
- ✅ `md2pdf.py` on a multi-heading fixture yields a PDF whose outline is
  non-empty, nested, and titled to match the headings (R1.1, R2).
- ✅ `html2pdf.py` (default engine) does the same, including under
  `--no-default-css` (R1.2, R1.3, R3).

### UC-2 — Agent renders HTML to PDF via the chrome engine (parity fix)

#### 3.2.1. Actors
- **Agent**, **System** (chrome engine — Playwright + Chromium), **End user**.

#### 3.2.2. Preconditions
- The opt-in chrome engine is installed (`install.sh --with-chrome`;
  Playwright **≥ 1.42**).
- An HTML source with a heading structure.

#### 3.2.3. Main Scenario
1. The agent runs `python3 scripts/html2pdf.py page.html page.pdf --engine
   chrome` (chosen because weasyprint mis-rendered the page — pdf-11 use case).
2. The System renders via headless Chromium; `render_chrome()` calls
   `page.pdf(..., outline=True, tagged=True)`.
3. Chromium derives the document outline from the tagged structure tree and
   embeds it in the PDF (which is consequently a tagged PDF).
4. The end user opens `page.pdf`; the bookmark sidebar is present — **parity**
   with a weasyprint-rendered PDF.

#### 3.2.4. Alternative Scenarios
- **A1 — chrome engine not installed.** `--engine chrome` without Playwright →
  the pre-existing `ChromeEngineUnavailable` error with its install
  remediation (unchanged behaviour). The R6 chrome outline **test** soft-skips
  in this environment (R6.2).
- **A2 — old Playwright (< 1.42).** A *fresh* `pip install -r
  requirements-chrome.txt` resolves `playwright >= 1.42` (R5.1). A developer
  who installed the chrome engine under pdf-11 (floor `>=1.40`) may still have
  1.40/1.41 in their `.venv`; re-running `install.sh --with-chrome` upgrades it
  because the installer now passes `--upgrade` (R5.3). Should an under-floor
  Playwright still be reached, `page.pdf(outline=True)` raises `TypeError` —
  the R6.4 capability probe turns that into a loud, diagnosed test failure
  rather than a silent skip.

#### 3.2.5. Postconditions
- A chrome-rendered PDF carries an outline, just like a weasyprint-rendered one.

#### 3.2.6. Acceptance Criteria
- ✅ `render_chrome()` passes `outline=True` **and `tagged=True`** to
  `page.pdf()`; a chrome-rendered multi-heading HTML yields a non-empty nested
  outline (R4).
- ✅ `requirements-chrome.txt` floor is `playwright>=1.42` with a rationale
  comment (R5).
- ✅ The chrome outline test passes when chrome is available and soft-skips
  cleanly when it is not (R6).

### UC-3 — Maintainer validates the skill after the change

#### 3.3.1. Actors
- **Maintainer / CI**, **System**.

#### 3.3.2. Preconditions
- TASK 014 implemented on a branch.

#### 3.3.3. Main Scenario
1. Maintainer runs `bash skills/pdf/scripts/tests/test_e2e.sh` — all
   pre-existing pdf tests pass; the new outline checks (R2, R3, R6) pass (R6
   soft-skipping if chrome is absent).
2. Maintainer runs
   `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/pdf`
   → exit 0.
3. Maintainer runs the cross-skill `diff -q` on `_errors.py` / `preview.py`
   (docx ↔ pdf) → silent.

#### 3.3.4. Alternative Scenarios
- **A1 — Validator flags a structural issue** (e.g. a `SKILL.md` link to a
  missing anchor) → fix and re-run until exit 0.

#### 3.3.5. Postconditions
- The skill is structurally valid; the cross-skill replication invariant holds;
  no existing test regressed.

#### 3.3.6. Acceptance Criteria
- ✅ `validate_skill.py skills/pdf` exits 0 (R9.1).
- ✅ `test_e2e.sh` passes including the new coverage (R9.2).
- ✅ `diff -q` on `_errors.py` / `preview.py` is silent (R9.3).
- ✅ `test_battery.py` / `test_preprocess.py` / `test_pdf_extract.py` show no
  regression (R9.4).

---

## 4. Non-functional Requirements

- **Performance:** `outline=True` / `tagged=True` add negligible cost to a
  chrome render (Chromium builds the outline + structure tree from the layout
  tree it already computes). No measurable change to weasyprint renders (no
  code change there). No throughput target.
- **Security:** No new attack surface. `outline=True` / `tagged=True` are
  static boolean arguments — no file content is interpolated, no remote fetch
  is added. The chrome engine's existing offline route-blocking and `<script>`
  stripping are unchanged.
- **Compatibility:** The weasyprint paths are unchanged → byte-for-byte
  identical PDFs for every existing `md2pdf.py` / `html2pdf.py` (weasyprint)
  invocation, **including the outline they already emit**. The chrome path
  gains an outline and becomes a **tagged PDF** — an additive change to that
  engine's output (a tagged PDF is a structural superset; existing visible
  content / layout is unchanged). Playwright floor `>=1.42` is satisfied by
  every current release (`<2.0`).
- **Maintainability:** The chrome change is a single keyword argument on an
  existing call. Tests follow the established `test_e2e.sh` conventions
  (`ok`/`nok`/`skip`, soft-skip gating). PDF outline is read back in tests via
  `pypdf` (`PdfReader.outline`) — `pypdf` is already an installed pdf-skill
  dependency.

## 5. Constraints and Assumptions

### Constraints
- **C-1** Files are edited **only** under `skills/pdf/` (+ `docs/`). No
  cross-skill replication is triggered (Meta; R9.3).
- **C-2** No new CLI flag, no new dependency. `requirements-chrome.txt` gets a
  floor bump only (R5).
- **C-3** The weasyprint render paths MUST NOT change behaviour — this task
  *verifies and locks* them, it does not modify `md2pdf.py` render logic or
  `render.py`'s weasyprint branch.
- **C-4** The pdf skill is Proprietary; edited/new files inherit
  `skills/pdf/LICENSE` / `NOTICE`. No new third-party dependency → no
  `THIRD_PARTY_NOTICES.md` change (C-4 ⇔ R5.4).
- **C-5** This task MUST NOT regress any existing pdf script or test.

### Assumptions
- **A-1 (verified during Analysis)** weasyprint emits the PDF outline from
  `h1`–`h6` out of the box for both `md2pdf.py` and `html2pdf.py` (weasyprint
  engine); the bundled `DEFAULT_CSS` does not override `bookmark-level` /
  `bookmark-label`. The implementation re-confirms this via R1/R2/R3 tests.
- **A-2 (resolved → Q-1)** The chrome-engine parity fix **is in scope** —
  user-confirmed via AskUserQuestion on 2026-05-22 ("Include chrome fix").
- **A-3 (corrected 2026-05-22 — supersedes the DRAFT-v1 assumption).**
  Playwright's `page.pdf()` gained **both** the `outline` and `tagged` options
  in release **1.42**. **Empirically verified during Task 014-02 (2026-05-22):**
  Chromium's `page.pdf(outline=True)` *alone* produces an **empty** outline
  (0 bookmarks) — the outline is built from the tagged-PDF structure tree, so
  `tagged=True` is **also required** (`outline=True, tagged=True` → the correct
  nested outline). The DRAFT-v1 assumption that `outline=True` alone suffices
  was wrong; §1.1a, §1.2, R4.1, Q-3 are amended accordingly. The floor bump
  targets 1.42 (both options landed there).
- **A-4** `pypdf` (used by `pdf_merge.py`, already in `requirements.txt`)
  exposes `PdfReader.outline` for the regression tests to read the outline
  back. No new test dependency.
- **A-5** The chrome engine's `<script>`-stripping (`_strip_script_tags`) and
  layout-normalisation CSS injection do not remove `<h1>`–`<h6>` content
  elements — confirmed by reading `chrome_engine.py`; R4.3 re-verifies via the
  chrome outline test. (`_DOM_NORMALIZE_SCRIPT` can *hide* a heading that sits
  inside non-substantial `position:fixed` chrome — that exclusion is
  intentional and documented in §1.4(b) / R4.3, not a regression.)
- **A-6 (open verification point)** Chromium's `page.pdf(outline=True)` derives
  the outline from the DOM heading structure independently of the emulated
  media; `render_chrome()`'s `page.emulate_media(media="screen")` (set for
  archive screen-capture fidelity) is **not expected** to change which
  `h1`–`h6` reach the outline. The R6 implementation confirms this empirically
  on its plain-content fixture and records the observation (R6.3). If
  `media: screen` is found to alter the outline, the finding is documented in
  honest-scope — the screen-media choice is load-bearing for pdf-11 archive
  fidelity and is **not** reverted by this task.

## 6. Open Questions

> All questions are **resolved with a documented default** and are
> **non-blocking** — listed for the Task-Reviewer / Architect to confirm or
> override.

- **Q-1 (resolved → A-2):** Is the `--engine chrome` outline fix in scope, or is
  pdf-7 weasyprint-only? **Resolved: in scope** — the user explicitly chose
  "Include chrome fix" (AskUserQuestion, 2026-05-22). Shipping pdf-7 with the
  chrome engine silently lacking the outline would be dishonest scope; the fix
  is ~2 lines (the `outline=True` arg + the requirements floor).
- **Q-2 (resolved):** Should a `--no-outline` opt-out CLI flag be added?
  **Resolved: no.** weasyprint emits the outline unconditionally with no toggle;
  a chrome-only opt-out would be asymmetric, and a navigable outline is
  universally beneficial (the whole point of `pdf-7`). Adding a flag is YAGNI.
  Override only if a concrete need for a flat, outline-free PDF is identified.
- **Q-3 (resolved — amended 2026-05-22):** Should `tagged=True` be set on the
  chrome engine's `page.pdf()` call? **DRAFT-v1 said no** (tagged PDF out of
  scope). **Amended: YES — `tagged=True` is mandatory.** Chromium emits the
  document outline *only* when the PDF is tagged: `outline=True` alone yields
  0 bookmarks (empirically verified — §1.1a, A-3). Delivering R4 (the chrome
  outline) is **impossible** without it. The user confirmed this scope
  amendment via AskUserQuestion on 2026-05-22 ("Add `tagged=True`"). The chrome
  PDF therefore becomes a tagged PDF — an accepted, necessary side-effect
  (§1.2). This does **not** extend the task to PDF/UA *conformance* — see
  §1.2 / §1.4(c).
- **Q-4 (resolved):** Bump the Playwright **floor** to 1.42 vs. add a runtime
  version-probe (`try: page.pdf(outline=True) except TypeError`)? **Resolved:
  floor bump.** Per the project memory feedback *"prefer dependency upgrades on
  a version mismatch"*, pinning `playwright>=1.42` is cleaner than a defensive
  feature-probe. `<2.0` upper bound is unchanged. Override only if a hard
  constraint pins an older Playwright.

---

## 7. Definition of Done

- All 9 RTM requirements satisfied; all Acceptance Criteria in UC-1..UC-3 pass.
- **Verified & locked:** `md2pdf.py` and `html2pdf.py` (weasyprint, incl.
  `--no-default-css`) emit a non-empty nested PDF outline — proven by R2/R3
  regression tests wired into `test_e2e.sh`.
- **Chrome parity:** `render_chrome()` passes `outline=True` **and
  `tagged=True`** (the latter required by Chromium for the outline — §1.1a); a
  chrome-rendered multi-heading HTML carries a non-empty nested outline;
  `requirements-chrome.txt` floor is `playwright>=1.42` with a rationale
  comment.
- **Tests:** R2 / R3 / R6 added; R6 soft-skips cleanly when chrome is absent;
  no pre-existing pdf test regressed.
- **Docs:** `SKILL.md` §2 + a `references/` note describe the outline behaviour
  and the honest-scope items (chrome PDFs are tagged — the outline mechanism;
  no PDF/UA conformance claim; weasyprint paths untagged).
- `validate_skill.py skills/pdf` exits 0; cross-skill `diff -q` is silent.
- `docs/office-skills-backlog.md` `pdf-7` row marked ✅ DONE and the stale
  "only in-page links" note corrected.

# Task 022-07 [INTEGRATION + DOC]: SKILL.md + license + install + fork-gates + dogfood

> **Predecessor:** 022-01…06 (all FCs live).
> **RTM:** [R7] packaging & isolation, [R8] CI fork-gate. Final guards G-1/G-2/G-4.
> **ARCH:** §5.4 (SKILL contract), §9 (all guards), §10 (honest scope), §11 (022-07).

## Use Case Connection
- All UCs — documented + dogfooded end-to-end on real fixtures.

## Task Goal
Ship the skill: docs, proprietary license, install script, third-party
attribution, backlog closure, and the **fork-free gates** (G-1 `diff -q`, G-2
smoke, G-4 CI), then dogfood on real URL + `.webarchive` + `.mhtml`.

## Changes Description
### Docs
- **`skills/html2md/SKILL.md`** — Gold-Standard: triggers ("html to markdown",
  "url to markdown", "web page to obsidian", "webarchive/mhtml to markdown",
  "scrape page to notes"), capabilities, CLI quick-ref (ARCH §5.1), setup
  (`install.sh`, `--with-chrome`), honest scope (ARCH §10).
- **`skills/html2md/references/html-to-markdown.md`** — decision tree
  (URL vs archive vs file; reader vs whole; lite vs chrome) + limitations.
- **`skills/html2md/scripts/.AGENTS.md`** — "REPLICATED, master=pdf for
  `web_clean/*`, master=docx for `html2md_core.js` + `_errors.py` +
  `_venv_bootstrap.py`; do not edit here, `diff -q` gated" banner.

### License / attribution (Proprietary — ARCH §9, CLAUDE.md §3)
- **`skills/html2md/LICENSE`** + **`NOTICE`** — mirror `skills/docx/` (Proprietary,
  All Rights Reserved); re-point root `THIRD_PARTY_NOTICES.md`.
- **`THIRD_PARTY_NOTICES.md`** — add `httpx`, `trafilatura`, `turndown`,
  `turndown-plugin-gfm`, `playwright` (+ note `html2md` scope).

### Install
- **`skills/html2md/scripts/install.sh`** — venv + `pip install -r
  requirements.txt` + `npm install`; `--with-chrome` → `requirements-chrome.txt`
  + `playwright install chromium`; dep-import verify.

### Backlog / governance
- `docs/office-skills-backlog.md` §2 «html2md»: mark html2md-1…5 progress/done.

### CI fork-gate (G-4, [R8])
- **`.github/workflows/office-skills.yml`**: add `html2md` to the skill matrix;
  add a `diff -q`/`diff -qr` step that fails on byte-drift for BOTH masters:
  - `_errors.py`, `_venv_bootstrap.py` (docx → html2md),
  - `html2md_core.js` (docx → html2md),
  - `web_clean/{archives,reader_mode,preprocess,dom_utils,normalize_css}.py`
    (pdf → html2md).

## Test Cases
### Gates
1. **G-1 `test_replication_diff`** — all `diff -q`/`diff -qr` above silent
   (after `__pycache__` clean) — both masters.
2. **G-2 `test_no_weasyprint_no_playwright`** — re-assert from 022-01 (closure).
3. **G-4** — the CI step is present and red on an injected byte-drift (a unit/CI
   self-test, or a documented manual verification).
4. **`validate_skill.py` ×5** — `for s in docx xlsx pptx pdf html2md` → all exit 0.
5. **Isolation** — package `skills/html2md` as `.skill` (or simulate: run with no
   sibling skill dir on `sys.path`) → CLI still runs (no sibling-skill import).

### Dogfood (real fixtures)
6. A real **URL** (lite) → dual MD + `_attachments/`; a real **`.webarchive`**
   and **`.mhtml`** → offline dual MD. Record results (page count, image count,
   any honest-scope degrade). Chrome-engine dogfood is host-gated (like pdf-11).

## Acceptance Criteria
- [ ] **[R7]** SKILL.md + references + install.sh + LICENSE/NOTICE +
      THIRD_PARTY_NOTICES updated; `validate_skill.py skills/html2md` exit 0.
- [ ] **[R6]** G-1 `diff -q` silent (both masters) + G-2 smoke green.
- [ ] **[R8]/G-4** CI gate added (html2md in matrix + diff step).
- [ ] `.skill` isolation: runs with no sibling skill present.
- [ ] Dogfood: real URL + `.webarchive` + `.mhtml` produce correct dual MD.
- [ ] backlog html2md-1…5 marked done; **no auto-commit**.

## Notes
- This bead edits docx-master-adjacent CI + may touch `THIRD_PARTY_NOTICES.md`
  (root). It does NOT edit any pdf/docx **source** master (those were edited in
  022-03 for the core; the web_clean copies are never edited).
- Full review pipeline (code-reviewer + security-auditor) before declaring done,
  per the Self-Improvement Mode rule for new core components.

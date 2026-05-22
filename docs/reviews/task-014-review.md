# Task Review — TASK 014 (pdf-7: PDF outline / TOC bookmarks)

**Date:** 2026-05-22
**Reviewer:** Task Reviewer (subagent)
**Status:** ✅ **APPROVED WITH COMMENTS**
**TASK file:** `docs/TASK.md`

## General Assessment

High-quality, well-scoped Technical Specification. It correctly reframes a
backlog *verification* task into a two-part deliverable (verify-and-lock
weasyprint + close the chrome-engine gap), and every load-bearing technical
claim was checked against the codebase and found accurate:

- **Chrome-engine gap confirmed.** `render_chrome()` in
  `skills/pdf/scripts/html2pdf_lib/chrome_engine.py` (lines 717–724) calls
  `page.pdf(path=..., format=..., print_background=..., scale=..., margin=...)`
  — `outline=True` is genuinely absent. R4.1 is real.
- **weasyprint path confirmed.** `render.py` `convert()` weasyprint branch
  (lines 193–206) does no outline suppression; `DEFAULT_CSS` in `md2pdf.py`
  (lines 169–198) styles `h1`–`h4` for color/size but never touches
  `bookmark-level`/`bookmark-label`.
- **`requirements-chrome.txt`** currently pins `playwright>=1.40,<2.0` — R5.1's
  floor bump is accurately described.
- **Test harness** `test_e2e.sh` carries the `mermaid_renders` soft-skip
  pattern (lines 23, 166–270) that R6.2 mirrors.
- **Backlog row** `pdf-7` is at line 214 with exactly the quoted text.
  Cross-skill replication scope correctly assessed as "none triggered".

RTM is granular (9 requirements, 3–5 verifiable sub-features each, all MVP-✅,
no orphans). Use Cases UC-1..UC-3 each have Actors / Preconditions / Main +
Alternative scenarios / Postconditions / verifiable Acceptance Criteria.
Non-goals (§1.2) and honest-scope (§1.4) are explicit and not aspirational.

No CRITICAL issues. MAJOR/MINOR comments are refinements, not blockers.

## 🔴 Critical Issues

None.

## 🟡 Major Comments

**M-1 — Floor bump does not protect the pre-existing-install path.**
`requirements-chrome.txt`'s floor only binds a *fresh* `pip install -r`. A
developer who installed the chrome engine under pdf-11 (floor `>=1.40`) with
1.40/1.41 already in `.venv` is not upgraded by editing the requirements file
— `pip install -r` does not upgrade an already-satisfied package without
`--upgrade`. `install.sh:107` runs `pip install --quiet -r
requirements-chrome.txt` (no `-U`). UC-2/A2 names the symptom but assigns no
remediating action.
**Fix:** require `install.sh --with-chrome` to pass `--upgrade`, **and** have
the R6 chrome test probe that the resolved Playwright's `page.pdf()` accepts
`outline` — turning a silent `TypeError` into a diagnosed failure.

**M-2 — `page.pdf(outline=True)` × `emulate_media("screen")` unverified.**
`render_chrome()` calls `page.emulate_media(media="screen")` before
`page.pdf()`. §1.4(d) covers cross-engine nesting differences but not whether
`media: screen` changes which headings Chromium emits into the outline.
**Fix:** add an explicit assumption (A-6) that `outline=True` operates on the
DOM heading structure independently of emulated media, and make R6 confirm it
empirically.

**M-3 — "headings survive chrome preprocessing" understates one strip path.**
The chrome engine also runs `_DOM_NORMALIZE_SCRIPT` (lines 233–341), which
`display:none`s non-substantial `position:fixed` elements and hides non-portal
body children when a modal is released. A heading inside hidden chrome is
excluded from the outline — arguably correct, but the TASK presents heading
survival as unconditional.
**Fix:** tighten R4.3 / §1.4(b); add an honest-scope item; use a
plain-content fixture (no fixed-position chrome) for the R6 test.

**M-4 — `md2pdf.py` has no `--no-default-css`; asymmetry should be stated.**
R1.3/R3.2 correctly scope the `--no-default-css` lock to `html2pdf.py`, but a
reader may wonder why R2 (`md2pdf.py`) has no such variant.
**Fix:** add a half-sentence to R1.1 noting `md2pdf.py` exposes no
CSS-suppression flag.

## 🟢 Minor Comments

- **m-1** — `docs/ARCHITECTURE.md` still describes TASK 013 (`pdf-12`).
  Expected — the Architecture phase has not run for TASK 014. The Architect
  must update it; no TASK change needed.
- **m-2** — R7.2's "and/or" defers a real decision; pin to one file
  (`html-conversion.md` is the natural home).
- **m-3** — UC-3 has only one Alternative scenario. Acceptable for a
  validation UC.
- **m-4** — §0 link styles mix `docs/`-relative and root-relative. Fine.
- **m-5** — R8.3's "~line 689 / ~line 720" — reword to "grep for `pdf-7`"
  since offsets shift.

## Final Recommendation

**APPROVED WITH COMMENTS — proceed to Architecture.** No CRITICAL issues; the
TASK is internally consistent, complete versus the user request and backlog
row `pdf-7`, and accurately grounded in the codebase. M-1 through M-4 were
routed back to the Analyst for a revision pass before Architecture; M-1
(the `pip install` non-upgrade gap) is a genuine honest-scope hole.

```json
{"review_file": "docs/reviews/task-014-review.md", "has_critical_issues": false}
```

---

## Revision log

**2026-05-22 — Analyst revision pass (post-review):** all 4 MAJOR comments
applied to `docs/TASK.md`:
- **M-1** → R5.3 rewritten to mandate `install.sh --with-chrome` install with
  `--upgrade`; new R6.4 (Playwright `page.pdf` `outline`-kwarg capability
  probe, loud-fail); UC-2/A2 rewritten.
- **M-2** → new Assumption A-6 (outline independent of emulated media; R6
  confirms empirically); R4.2 cross-references A-6.
- **M-3** → R4.3 tightened; §1.4(b) rewritten; R6 fixture pinned to
  plain-content (no fixed chrome).
- **M-4** → R1.1 extended with the `md2pdf.py`-has-no-`--no-default-css` note.
- **m-2** → R7.2 pinned to `references/html-conversion.md`.
- **m-5** → R8.3 reworded to "grep every `pdf-7` occurrence".

No re-review required (no CRITICAL issues; changes are spec refinements).
Status remains APPROVED → Architecture phase may proceed.

---

# Task Re-Review — TASK 014 v2 amendment (`tagged=True`)

**Date:** 2026-05-22
**Reviewer:** Task Reviewer (subagent, 2nd pass)
**Status:** ✅ **APPROVED**
**TASK file:** `docs/TASK.md` (DRAFT v2)

## Why a re-review

During Task 014-02 development a controlled Playwright probe established that
Chromium's `page.pdf(outline=True)` emits an outline **only** when `tagged=True`
is also passed (`outline` alone → 0 bookmarks; `outline+tagged` → 4). This
contradicted the v1 spec, which declared tagged PDF a non-goal. The user
confirmed the scope amendment (AskUserQuestion, 2026-05-22 — "Add tagged=True");
TASK 014 was amended to v2 (§1.1a new, §1.2/Q-3/A-3/R4/R7.3/§4/§7/UC-2 revised).

## Assessment

The v2 amendment is clean, internally consistent, and honest. All amended
cross-references (§1.2, §1.4(c), Q-3, A-3, R4.1/R4.4, R5.1, R7.3, §7, UC-2)
agree; no leftover v1 "tagged is out of scope" claim survives. The non-goal
revision draws a precise line — tagged PDF is an *accepted, necessary
mechanism*; PDF/UA *conformance claims* + tagging-quality validation + weasyprint
tagging stay out of scope. A-3 correctly supersedes the wrong v1 assumption.
R4 stays mechanically verifiable. Scope did not balloon — exactly one extra
kwarg, no new flag/dependency/requirement. RTM (R1–R9) intact, no orphan; Use
Cases coherent.

## Comments

🔴 Critical: none. 🟡 Major: none.

🟢 Minor (cosmetic / non-blocking):
- **m-6** — §1.4 heading still says "(v1 — …)"; the parenthetical is now
  slightly misleading since §1.4(c) was rewritten in v2. → **Applied** (heading
  de-versioned).
- **m-7** — the amendment header says "§1.1" where it means the new "§1.1a".
  → **Applied** (header corrected to "§1.1a").
- **m-8** — `requirements-chrome.txt`'s 1.42-rationale comment mentions
  `outline` only, not `tagged`; implementation note for 014-02. → **Applied**
  during 014-02 (comment extended to name both options).

## Final Recommendation

**APPROVED — development of Task 014-02 may resume to add `tagged=True`.** The
v2 spec is sound; the three MINOR items were applied as cheap polish. No
re-routing required.

```json
{"review_file": "docs/reviews/task-014-review.md", "has_critical_issues": false}
```

# Task 014-03 [INTEGRATION]: Skill surface, reference note, backlog, validation

> **Predecessor:** 014-02 (chrome behaviour + the full outline test surface
> exist).
> **RTM:** **completes** [R7][R8][R9].
> **ARCH:** §2.1 F7, §3.2 (doc rows), §9 (replication invariant), §10 (honest
> scope), §13.

## Use Case Connection

- **UC-3** — maintainer validates the skill after the change.

## Task Goal

Document the (now engine-agnostic) PDF-outline behaviour on the skill surface,
add a reference note, flip the `pdf-7` backlog row to ✅ DONE, and run the
validation gate — `validate_skill.py` exit 0, full `test_e2e.sh` green, no
regression in the other pdf test modules, cross-skill `diff -q` silent.

## Changes Description

### Changes in Existing Files

#### File: `skills/pdf/SKILL.md` — §2 Capabilities (R7.1)

Extend §2 so it states plainly that the converters produce a navigable PDF
**outline (bookmarks)** from document headings:

- The `md2pdf.py` capability bullet — add a clause: the rendered PDF carries a
  navigable **outline (bookmarks)** auto-generated from `h1`–`h6` headings.
- The `html2pdf.py` capability bullet — add the same, and note it is
  **engine-agnostic**: both the weasyprint engine and `--engine chrome` emit
  the outline.

Keep it to a concise clause per bullet — §2 is a capability list, not prose.
The honest-scope detail (real heading tags only; chrome PDFs are tagged; no
PDF/UA conformance claim) lives in the reference (next).

#### File: `skills/pdf/SKILL.md` — §10 / §12 review (R7.4)

- §10 Quick Reference — review; the outline is automatic (no flag), so **no new
  row is required**. Only touch a row if it became inaccurate (it did not).
- §12 Resources — the `references/html-conversion.md` entry already exists;
  optionally extend its one-line description to mention the outline note. No
  new resource entry needed.

#### File: `skills/pdf/references/html-conversion.md` (R7.2, R7.3)

Add a new section — **`## PDF outline (bookmarks)`** — placed before the
existing `## Honest scope (limitations)` section. Content:

- weasyprint emits the PDF outline automatically from `<h1>`–`<h6>` via its
  user-agent stylesheet (`bookmark-level` / `bookmark-label`); **no CSS flag is
  needed**, and `--no-default-css` does **not** disable it (the bundled
  `DEFAULT_CSS` does not own those properties).
- It is **engine-agnostic**: `--engine chrome` emits the outline too, via
  `page.pdf(outline=True, tagged=True)` (added for `pdf-7`). Note `tagged=True`
  is **required** — Chromium builds the outline from the tagged-PDF structure
  tree, so `outline=True` alone yields no bookmarks; consequently a
  chrome-rendered PDF is a **tagged PDF** (TASK §1.1a).
- **Honest scope** (TASK §1.4 / ARCH §10):
  - the outline derives from **real heading tags only** — styled `<p>`/`<div>`
    "visual headings" do not appear (§1.4(a));
  - `--reader-mode`, the preprocessing pipeline, and (chrome)
    `_DOM_NORMALIZE_SCRIPT` may remove or hide chrome/nav headings; the outline
    reflects what survives **visible** — this is correct, not a bug
    (§1.4(b)/(f));
  - cross-engine outline trees are not byte-identical (weasyprint vs. Chromium
    grouping may differ in edge cases) (§1.4(d));
  - the chrome engine emits a **tagged PDF** (the mechanism Chromium uses for
    the outline); this incidentally aids accessibility but `pdf-7` makes **no
    PDF/UA conformance claim** and does not validate tagging quality. The
    weasyprint paths are **not** tagged (§1.4(c)).

#### File: `docs/office-skills-backlog.md` (R8)

- **`pdf-7` row** (~line 214) — **grep `| pdf-7 |` to locate it**:
  - the name/status cell → `TOC bookmarks (PDF outline) ✅ DONE`;
  - the description cell → replace the open question with the outcome, e.g.:
    *"Verified: weasyprint emits the PDF outline from `<h1-h6>` out of the box
    (UA stylesheet `bookmark-level`) — `md2pdf` + `html2pdf` default engine, no
    CSS flag. `--engine chrome` gained `page.pdf(outline=True, tagged=True)`
    parity (Chromium needs `tagged=True` for the outline → chrome PDFs are
    tagged). Regression tests pin all three paths. TASK 014."*;
  - the **Notes** cell → correct the stale *"Сейчас только in-page links"* —
    e.g. *"weasyprint outline был out-of-box (backlog-заметка устарела);
    chrome-движок добавлен в TASK 014."*
- **Every other `pdf-7` occurrence** — **grep `pdf-7`** across the file; do
  not trust line offsets:
  - the **P1 prioritisation bullet** (~line 689, *"**pdf-7** TOC bookmarks
    …"*) → mark done (e.g. strike-through + ✅, matching how shipped items are
    marked elsewhere in §"Recommended порядок");
  - the **day-3 schedule line** (~line 720, `… → pdf-7 (S)`) → `pdf-7 (S) ✅`;
  - the **package-list mention** (~line 613, the `(pptx-2, … pdf-7, cross-2)`
    enumeration) is historical narrative of what the package contained — leave
    as-is (it is not an open-status list).

### Validation (R9)

Run, and confirm:

1. `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/pdf`
   → **exit 0** (R9.1).
2. `bash skills/pdf/scripts/tests/test_e2e.sh` → all green, including the
   014-01 weasyprint outline checks and the 014-02 chrome block (soft-skipping
   cleanly if Playwright/Chromium is absent) (R9.2).
3. `cd skills/pdf/scripts && ./.venv/bin/python -m unittest discover -s tests`
   → the pre-existing modules (`test_battery.py`, `test_preprocess.py`,
   `test_pdf_extract.py`) show **no regression** (R9.4). (`_outline_probe.py`
   is not a `test_*` module — `unittest discover` correctly ignores it.)
4. Cross-skill `diff -q` (R9.3 / ARCH §9):
   ```bash
   diff -q skills/docx/scripts/_errors.py  skills/pdf/scripts/_errors.py
   diff -q skills/docx/scripts/preview.py  skills/pdf/scripts/preview.py
   ```
   Both **silent**. (pdf has no `office/` directory → the `office/` `diff -qr`
   is N/A.)

## Component Integration

Pure documentation + validation. No code behaviour changes. The reference note
and `SKILL.md` describe behaviour already implemented in 014-01 (verified) and
014-02 (chrome parity).

## Test Cases

### Validation Evidence (this task IS the verification)

1. `validate_skill.py skills/pdf` exit 0.
2. `test_e2e.sh` full green.
3. `unittest discover -s tests` — pre-existing modules green.
4. `diff -q` matrix silent.

## Acceptance Criteria

- [ ] `SKILL.md` §2 states `md2pdf.py` / `html2pdf.py` produce a navigable PDF
      outline (bookmarks) from headings; html2pdf note is engine-agnostic
      ([R7] 7.1).
- [ ] `references/html-conversion.md` has a `## PDF outline (bookmarks)`
      section covering the mechanism, engine-agnosticism, the `tagged=True`
      requirement for the chrome engine, and the honest-scope points incl.
      **chrome PDFs are tagged / no PDF/UA conformance claim** ([R7] 7.2 / 7.3).
- [ ] `SKILL.md` §10 / §12 reviewed; changed only where inaccurate ([R7] 7.4).
- [ ] `docs/office-skills-backlog.md` `pdf-7` row → ✅ DONE; stale "only
      in-page links" note corrected; P1 bullet + day-3 schedule reconciled
      ([R8]).
- [ ] `validate_skill.py skills/pdf` exits 0 ([R9] 9.1).
- [ ] `bash skills/pdf/scripts/tests/test_e2e.sh` green incl. the new outline
      checks ([R9] 9.2).
- [ ] `test_battery.py` / `test_preprocess.py` / `test_pdf_extract.py` — no
      regression ([R9] 9.4).
- [ ] Cross-skill `diff -q` on `_errors.py` / `preview.py` silent ([R9] 9.3).
- [ ] Only `SKILL.md`, `references/html-conversion.md`, and
      `docs/office-skills-backlog.md` are modified.

## Stub-First Gate

Not applicable — integration + documentation task, no stub phase. Verified by
`validate_skill.py` exit 0 and the full suite green.

## Notes

- The §2 capability bullets are dense single paragraphs — append a clause,
  do not restructure the bullet.
- The backlog uses `✅ DONE` in the name/status cell (see the `pdf-5` /
  `pdf-6` rows for the house pattern) — follow it.

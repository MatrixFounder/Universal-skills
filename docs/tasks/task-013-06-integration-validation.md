# Task 013-06 [INTEGRATION]: Skill surface, backlog, validation

> **Predecessor:** 013-04 (helper complete) **and** 013-05 (reference exists).
> **RTM:** **completes** [R5] (5.1/5.2/5.3), [R12] (12.6), [R13].
> **ARCH:** §2.1 FC7, §9 (cross-skill gate).

## Use Case Connection

- UC-3 — maintainer validation: `test_e2e.sh` + `validate_skill.py` green.

## Task Goal

Wire the two new artifacts (`pdf_extract.py`, `references/pdf-to-markdown.md`)
into the skill so they are discoverable, exercised by the E2E harness, and
`validate_skill.py` stays green; cross-link `library-selection.md`; update the
existing `pdf-12` backlog row to DONE; confirm the cross-skill replication
invariant.

## Changes Description

### Changes in Existing Files

#### File: `skills/pdf/SKILL.md`

- **§2 Capabilities** — add a bullet: `pdf_extract.py` dumps a PDF's per-page
  text + tables to structured JSON, with **scan detection** (image-only
  documents → loud exit 10, not silent-empty). State it is a dump, not a
  Markdown converter.
- **§4 Script Contract** — add the command line:
  `python3 scripts/pdf_extract.py INPUT.pdf [-o OUT.json] [--layout]
  [--password PW] [--json-errors]`, plus the exit codes (0 / 1 / 2 / 10) and
  their meanings (ARCH §5.2).
- **§7.1** ("Pick the library, not the script first") — add a pointer: for
  PDF→Markdown follow [`references/pdf-to-markdown.md`](references/pdf-to-markdown.md);
  `pdf_extract.py` gives a structured dump but Markdown composition stays agent
  judgement ([R5] 5.1).
- **§3 Execution Mode** — review/reconcile: the skill still says extraction is
  "prompt-first". Add a clause that `pdf_extract.py` is a *script-first dump*
  while *composition* remains prompt-first — i.e. the deliberate-omission
  language now refers to a Markdown *converter*, which is still not bundled
  (ARCH D3, TASK R13.3).
- **§1 Red Flags** — review; optionally add: "I'll improvise a pdfplumber
  script for PDF→md → run `pdf_extract.py` for the dump and follow
  `references/pdf-to-markdown.md`; do not skip the scan check."
- **§10 Quick Reference** — add a row:
  `| Extract PDF text+tables to JSON | python3 scripts/pdf_extract.py in.pdf -o dump.json |`.
- **§12 Resources** — add two entries: `references/pdf-to-markdown.md` and
  `scripts/pdf_extract.py` ([R5] 5.2).

#### File: `skills/pdf/references/library-selection.md`

- Cross-link the new reference from the extraction-related rows / "What
  `pdfplumber` does well" section: a pointer that for the specific
  PDF→Markdown task, [`pdf-to-markdown.md`](pdf-to-markdown.md) holds the
  decision tree + recipe ([R5] 5.3).

#### File: `skills/pdf/scripts/tests/test_e2e.sh`

- Append a smoke block: build the fixtures via `_pdf_extract_fixtures.py` (or
  reuse the committed ones), run `pdf_extract.py` on `digital.pdf` (assert
  exit 0 + JSON on stdout) and on `scanlike.pdf` (assert exit 10), and run the
  `unittest` module `test_pdf_extract.py`. Keeps the bash harness as the single
  entry point ([R12] 12.6).

#### File: `docs/office-skills-backlog.md`

- The `pdf-12` row + its §7-prioritisation mentions are updated to TASK 013's
  refined design and marked **✅ DONE** with validation evidence (R13.4).
  *(Note: an interim "🔄 PLANNED — TASK 013" status was set at the end of the
  `/vdd-plan` phase per PLAN.md §5; this task flips it to DONE at merge.)*

### New Files

None.

## Test Cases

### E2E Tests

1. **TC-E2E-13 `test_e2e_sh_runs_pdf_extract`** — `bash
   skills/pdf/scripts/tests/test_e2e.sh` exercises the `pdf_extract` smoke
   block and exits 0.

### Validation

1. **TC-VAL-01** — `python3 .claude/skills/skill-creator/scripts/validate_skill.py
   skills/pdf` → exit 0 ([R13] 13.1).
2. **TC-VAL-02** — every file linked from `SKILL.md` (§7.1, §12) and from
   `pdf-to-markdown.md` exists (validator link check).

### Regression Tests

- `bash skills/pdf/scripts/tests/test_e2e.sh` — the **entire** pdf suite
  (md2pdf, merge, split, fill-form, html2pdf battery, `pdf_extract`) green.
- `python3 -m unittest skills.pdf.scripts.tests.test_pdf_extract` — green.

## Acceptance Criteria

- [ ] `SKILL.md` updated: §2, §4, §7.1, §10, §12 (+ §1/§3 reviewed) ([R5], [R13] 13.2/13.3).
- [ ] `library-selection.md` cross-links `pdf-to-markdown.md` ([R5] 5.3).
- [ ] `test_e2e.sh` exercises `pdf_extract.py` ([R12] 12.6).
- [ ] `validate_skill.py skills/pdf` exits 0 ([R13] 13.1).
- [ ] `docs/office-skills-backlog.md` `pdf-12` row updated + marked DONE ([R13] 13.4).
- [ ] Cross-skill `diff -q` silent — the invariant ([R13] 13.5, ARCH §9):
      ```bash
      diff -q skills/docx/scripts/_errors.py  skills/pdf/scripts/_errors.py
      diff -q skills/docx/scripts/preview.py  skills/pdf/scripts/preview.py
      ```
      Both produce no output.
- [ ] Full pdf E2E suite green — no regression in any pre-existing script.

## Stub-First Gate

Integration task — no stub phase. Verified by `validate_skill.py` exit 0 + the
full suite green.

## Notes

- `_errors.py` / `preview.py` are **not** edited — `pdf_extract.py` imports
  `_errors` read-only, so the replication invariant holds with no `cp` step.
- If `validate_skill.py` flags a structural issue (e.g. a SKILL.md link to a
  missing file), fix the link/file and re-run until exit 0 — do not suppress
  the check.
- The backlog row rewrite must remove the old `pdf_extract_text.py` /
  `pdf_extract_tables.py` / `--format markdown` wording — that two-script
  design was superseded by TASK 013 (ARCH D3 — no Markdown-emitting script).

# Task 018-06 [INTEGRATION]: reference doc, skill surface, notices, E2E block, validation, backlog

> **Predecessor:** 018-03 (MVP runner must exist).
> **RTM:** **completes** [R4b], [R8a], [R8c], [R8d].
> **ARCH:** §5.3 (composition), §7 (trust model → ocr.md), §9 (replication
> gate), §10 (honest scope), §11 (bead 018-06).

## Use Case Connection

- UC-3 — maintainer validation (validator + suite green).
- UC-1 — the "agent follows the reference" acceptance (recipe doc).

## Task Goal

Surface the MVP `pdf_ocr.py` to users and maintainers: write `references/ocr.md`
(usage + composition recipe + trust model + honest scope), add the `SKILL.md`
entry, cross-link from `references/pdf-to-markdown.md`, attribute the new
external tools in `THIRD_PARTY_NOTICES.md`, add the **soft-skipping** OCR block
to `test_e2e.sh`, pass `validate_skill.py`, keep the cross-skill `diff -q`
silent, and flip the backlog `pdf-4` row to ✅ DONE.

## Changes Description

### New Files

#### `skills/pdf/references/ocr.md`

Sections:
- **What it is / is not** — searchable-PDF maker, not a Markdown converter
  (point to `pdf-to-markdown.md`).
- **Install** — `bash install.sh --with-ocr` + the per-OS system-tool table
  (tesseract + eng/rus traineddata + ghostscript). Wording **identical** to the
  `_require_engine` remediation message (018-02).
- **Usage** — the CLI surface (ARCH §5.1) with examples; default `eng+rus`;
  `--lang`, mode flags, `--sidecar`, `--jobs`.
- **Composition recipe (R4b)** — the canonical three-liner (ARCH §5.3):
  `pdf_extract → exit 10 → pdf_ocr → pdf_extract` digital re-read.
- **Trust model (R8c / AM-2)** — single-tenant, operator-supplied input;
  `--password` argv-visible; no shell interpolation; output written atomically;
  no global timeout (honest scope).
- **Honest scope** — engine not bundled; OCR not bit-exact; R5/R9 status
  (password = available only after bead 018-04; image-prep = bead 018-05).

#### `skills/pdf/scripts/.AGENTS.md` (NEW — closes a skill gap)

The pdf skill has **no** `scripts/.AGENTS.md`, unlike `docx`/`xlsx` (which carry
a per-script agent-orientation log). 018-01 deliberately did **not** create one
(documenting the 8 pre-existing untouched scripts would be drive-by work outside
that bead's scope — developer-guidelines §1). Create it here at the correct
full-skill scope: a brief inventory of every `skills/pdf/scripts/*.py` (purpose +
1-line note) **plus** the new `pdf_ocr.py` (composition with `pdf_extract.py`,
soft-optional `--with-ocr`, exit contract). Match the docx `.AGENTS.md` shape.

### Changes in Existing Files

#### File: `skills/pdf/SKILL.md`
- Add `pdf_ocr.py` to the script inventory / capabilities section, with the
  one-line description, the `--with-ocr` install note, and a link to
  `references/ocr.md`. Mention the composition with `pdf_extract.py`.

#### File: `skills/pdf/references/pdf-to-markdown.md`
- In the scan / OCR branch of the decision tree, cross-link `references/ocr.md`
  (the existing text already points at "run OCR (e.g. ocrmypdf)" — make it a
  concrete link to the new tool + doc).

#### File: `THIRD_PARTY_NOTICES.md` (repo root)
- Add attribution entries for `ocrmypdf` (MPL-2.0), `tesseract` (Apache-2.0),
  and `ghostscript` (AGPL — note it is an **external CLI invoked**, not bundled
  or linked) under the pdf-skill scope (CLAUDE.md §3 — root file governs both
  license scopes). Re-point from `skills/pdf/NOTICE` if that file enumerates
  per-tool deps.

#### File: `skills/pdf/scripts/tests/test_e2e.sh`
- Add a `pdf_ocr:` block after the `pdf_extract` block. **Soft-skip** when the
  engine is absent (mirror the mermaid `skip()` idiom):
  ```bash
  echo "pdf_ocr:"
  if "$PY" -c 'import ocrmypdf' 2>/dev/null && command -v tesseract >/dev/null && command -v gs >/dev/null; then
      "$PY" tests/_pdf_ocr_fixtures.py "$TMP"        # build scan.pdf
      if "$PY" pdf_ocr.py "$TMP/scan.pdf" "$TMP/scan.ocr.pdf" >/dev/null 2>&1 \
         && "$PY" pdf_extract.py "$TMP/scan.ocr.pdf" >/dev/null 2>&1; then
          ok "scan → ocr → pdf_extract digital re-read"
      else
          nok "pdf_ocr composition" "OCR or re-read failed"
      fi
  else
      skip "pdf_ocr (engine absent — install.sh --with-ocr + tesseract/gs)"
  fi
  ```

#### File: `docs/office-skills-backlog.md`
- Flip the `pdf-4` row (line ~211) to **✅ DONE (TASK 018, VDD)** with a short
  delivery note (ocrmypdf→searchable PDF, eng+rus default, soft-optional
  `--with-ocr`, composition with `pdf_extract.py`; R5/R9 deferred to
  018-04/05). Update the §7-prioritisation mention (line ~665) + the day-3
  sequence note (line ~721).

## Test Cases

### E2E Tests
1. **TC-E2E-06 `test_e2e_sh_ocr_block`** — `bash test_e2e.sh` exits 0; the
   `pdf_ocr:` block either passes (engine present) or soft-skips (engine absent)
   — never fails the suite.

### Validation
2. **`validate_skill.py skills/pdf` exit 0** — Gold-Standard / CSO green.
3. **skill-validator** green on `skills/pdf`.

### Regression Tests
- Full pdf unittest suite green: `python3 -m unittest
  skills.pdf.scripts.tests.test_pdf_ocr` (+ existing `test_pdf_extract`, battery).
- `bash skills/pdf/scripts/tests/test_e2e.sh` — green.

## Acceptance Criteria

- [ ] `references/ocr.md` exists with all sections incl. composition recipe
      ([R4b]) and trust model ([R8c], AM-2).
- [ ] `SKILL.md` surfaces `pdf_ocr.py` + link; `pdf-to-markdown.md` cross-links
      `ocr.md` ([R8c]).
- [ ] `skills/pdf/scripts/.AGENTS.md` created (closes the pdf-skill gap vs
      docx/xlsx): inventories all pdf scripts + the new `pdf_ocr.py` ([R8c]).
- [ ] `THIRD_PARTY_NOTICES.md` attributes ocrmypdf + tesseract + ghostscript
      (CLAUDE.md §3).
- [ ] `test_e2e.sh` OCR block present and **soft-skips** when engine absent
      ([R8a]).
- [ ] `validate_skill.py skills/pdf` exit 0; skill-validator green ([R8d]).
- [ ] Cross-skill `diff -q` silent gate (ARCH §9):
      ```bash
      diff -q skills/docx/scripts/_errors.py  skills/pdf/scripts/_errors.py
      diff -q skills/docx/scripts/preview.py  skills/pdf/scripts/preview.py
      ```
      Both produce no output (confirms no shared-helper edit).
- [ ] **No false-green (PR-1):** the composition E2E **TC-E2E-03 actually ran
      (not soft-skipped) at least once on an engine-equipped host** and passed;
      the run is recorded in this task's validation evidence. `pdf-4` is flipped
      to ✅ DONE **only** on that real-run evidence — a soft-skipped OCR block is
      NOT sufficient.
- [ ] `pdf-4` backlog row = ✅ DONE with delivery note.

## Stub-First Gate

Integration task — no stub phase. Gate = `validate_skill.py` exit 0 + full suite
green + `diff -q` silent.

## Notes

- Ghostscript is **AGPL**; we invoke it as an external CLI via ocrmypdf — it is
  neither bundled nor statically linked. State this explicitly in the notice to
  keep the proprietary-skill licensing clean (CLAUDE.md §3).
- If the dev/CI host lacks the engine, the `test_e2e.sh` OCR block + the 018-03
  composition E2E soft-skip; the validator and unit suite (engine-free) still
  gate the merge. Document this split in `references/ocr.md`.

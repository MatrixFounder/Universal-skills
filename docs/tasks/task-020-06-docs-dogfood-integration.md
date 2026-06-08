# Task 020-06 [INTEGRATION + DOC]: SKILL.md, reference, notices, dogfood (6 decks), gates

> **Predecessor:** 020-04 (MVP), 020-05 (OCR).
> **RTM:** **completes** [R-E1][R-E2][R-E3][R-E4].
> **ARCH:** §5.4 (docs contract), §9 (replication assertion), §11 (bead 020-06); AR-8/AR-9.

## Use Case Connection
- All (final validation + documentation).

## Task Goal
Reconcile the written contract with the shipped code, document OCR setup, register
the backlog row as done, and **dogfood all 6 tmp8 decks** with the global gates green.

## Changes Description

### Changes in Existing Files

#### File: `skills/pptx/SKILL.md`
- **§2 Capabilities:** add a bullet — "Convert a `.pptx`/`.pptm` deck to structured
  Markdown (one section per slide; title→heading, bullets, tables→GFM, images→sidecar
  `media/` + links, optional speaker notes) via `pptx2md.py`; opt-in `--ocr` recovers
  text baked into images using system `tesseract` (`eng+rus`)."
- **§4 Script Contract:** add the `python3 scripts/pptx2md.py INPUT.pptx [OUTPUT.md|-]
  [flags]` command line (full surface from ARCH §5.1).
- **§7.5 Setup:** add the optional OCR system-tool note (`tesseract` + `eng`/`rus`
  traineddata; soft-optional, detected not installed), mirroring the pdf skill wording.
- **§10 Quick Reference:** add a `.pptx → Markdown` row (+ an `--ocr` row).
- **§12 Resources:** add `scripts/pptx2md.py` + `references/pptx-to-markdown.md` links.
- **Honest-scope line:** OCR optional; merged-table cells best-effort; SmartArt/charts
  → placeholders; marp/background-image decks may yield header-only bodies (ARCH §10).

#### File: `skills/pptx/scripts/requirements.txt`
- Raise the python-pptx floor `>=0.6.23` → **`>=1.0.2`** (AR-9; repo "prefer
  dependency upgrades" note). No other dep change (OCR is a system tool).

#### File: `skills/pptx/scripts/install.sh`
- Add a `--with-ocr` note/flag (parallel to the pdf skill): probe (not install)
  `command -v tesseract`, `tesseract --list-langs` for `eng`+`rus`, printing per-OS
  install hints. Base path (no flag) unchanged.

#### File: `THIRD_PARTY_NOTICES.md`
- Tesseract OCR row (line ~84): scope `pdf` → **`pdf, pptx`** (AR-9 / MAJOR-2). Do
  **not** add `ocrmypdf`/`ghostscript`/`pytesseract` (not used by pptx — D-5).

#### File: `docs/office-skills-backlog.md`
- Mark **pptx-5** (Presenter notes export) ✅ DONE (delivered by R-D1) and add a new
  row noting the `pptx2md` core converter shipped (TASK 020), mirroring the
  `xlsx-9`/`pptx-3` "✅ DONE" style.

### New Files

#### `skills/pptx/references/pptx-to-markdown.md`
- Mirror `pdf/references/pdf-to-markdown.md`: when to use `pptx2md` vs hand-editing;
  the output shape (per-slide sections, GFM tables, sidecar media, OCR blocks, notes);
  the `--ocr` decision tree (text-rich → skip; image-only/marp → `--ocr`); honest
  limitations (rich-text flattened, SmartArt/charts placeholders, merged cells,
  background-image decks).

### Component Integration / Dogfood (R-E3c)
Run on **all 6 tmp8 decks** and spot-check:
```bash
cd skills/pptx/scripts
# MINOR-4: fail loud if an executor "autocorrected" the slodes-3 [sic] typo:
test -f ../../../tmp8/slodes-3.pptx || { echo "FATAL: tmp8/slodes-3.pptx missing (do NOT rename to slides-3)"; exit 1; }
for d in slides-1 slides-2 slides-4 slodes-3; do      # text-rich
  ./.venv/bin/python pptx2md.py ../../../tmp8/$d.pptx /tmp/$d.md
done
time ./.venv/bin/python pptx2md.py ../../../tmp8/slodes-3.pptx /tmp/slodes-3.md  # MAJOR-5 baseline
# image-only (the --ocr cases; engine-gated):
./.venv/bin/python pptx2md.py ../../../tmp8/slides-5.pptx /tmp/slides-5.md --ocr
./.venv/bin/python pptx2md.py "../../../tmp8/FRAMEWORK_WEBINAR.marp.pptx" /tmp/webinar.md --ocr
```
Record the `slodes-3` core wall-time in the task close note (regression ceiling).

## Test Cases

### E2E / Integration
1. **TC-E2E-10 `test_validate_skill_exit_0`** — `validate_skill.py skills/pptx` → 0.
2. **TC-E2E-11 `test_replication_matrices_silent`** (ARCH §9):
   ```bash
   diff -q  skills/docx/scripts/_errors.py  skills/pptx/scripts/_errors.py
   diff -qr skills/docx/scripts/office      skills/pptx/scripts/office
   diff -q  skills/docx/scripts/office_passwd.py skills/pptx/scripts/office_passwd.py
   ```
   All silent (proves no shared file was edited).
3. **TC-E2E-12 `test_dogfood_six_decks`** — the 4 text-rich decks → non-empty `.md` +
   populated `.media/`; the 2 image-only decks → at least `## Slide N` headers (and,
   when tesseract present, `--ocr` yields ≥1 `<!-- ocr -->` block; else SKIP-documented).

### Regression
- Full pptx suite green: `scripts/tests`, `scripts/office/tests`, `pptx2md/tests`.

## Acceptance Criteria
- [ ] SKILL.md updated (capabilities/contract/quick-ref/setup/resources/honest-scope) ([R-E1]).
- [ ] `references/pptx-to-markdown.md` created ([R-E2]).
- [ ] `THIRD_PARTY_NOTICES.md` Tesseract row gains `pptx`; no new dep rows ([R-E4b]).
- [ ] `requirements.txt` floor → `>=1.0.2` (AR-9); `install.sh --with-ocr` note added.
- [ ] Backlog `pptx-5` ✅ DONE + `pptx2md` core row added.
- [ ] **Dogfood:** all 6 tmp8 decks convert; `slodes-3` wall-time recorded ([R-E3c]).
- [ ] `validate_skill` exit 0; `diff -q` matrices silent ([R-E4a], ARCH §9).
- [ ] No pptx `LICENSE`/`NOTICE` altered; `_errors.py`/`office/` byte-identical ([R-E4d]).

## Notes
- This bead writes **no** new replicated code — the only edits to shared-by-name files
  are `THIRD_PARTY_NOTICES.md` (repo-root doc, not a replicated code file) and per-skill
  pptx docs/requirements. The §9 `diff -q` assertion proves the office matrices stay silent.
- If tesseract is absent on the host, the OCR dogfood (slides-5 / marp) is recorded as
  **pending verification** (pdf-4 pattern), and the MVP (no-OCR) dogfood still must pass.

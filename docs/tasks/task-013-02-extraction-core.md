# Task 013-02 [LOGIC IMPLEMENTATION]: PDF extraction core

> **Predecessor:** 013-01 (frozen surface).
> **RTM:** **completes** [R6]; [R7] sub-features 7.1 / 7.2 / 7.4 (per-page dict); advances [R12] (E2E green per `tdd-stub-first §2.4`).
> **ARCH:** §2.1 FC3, §4.2, §5.4, §6.

## Use Case Connection

- UC-1 main — digital PDF → structured dump.
- UC-1 A1–A3 — borderless tables / cross-page tables / multi-column are
  *surfaced* in the dump (resolution is the agent's job).

## Task Goal

Replace the extraction-core stubs (`_open_pdf`, `_extract_page`, `extract_pdf`)
with real `pdfplumber` logic so the dump's per-page records (ARCH §4.2) are
correct on the digital fixture. Scan classification stays stubbed (013-03) — on
the imageless digital fixture the stub `_classify_page → False` is already the
correct answer, so the digital-fixture E2E goes fully green here.

## Changes Description

### Changes in Existing Files

#### File: `skills/pdf/scripts/pdf_extract.py`

**Function `_open_pdf(pdf_path, password)`** — implement:
- Open `pdfplumber.open(str(pdf_path), password=password or "")`.
- Translate `pdfminer` password exceptions (`PDFPasswordIncorrect`,
  `PDFEncryptionError`) into a caller-visible failure — raise a small internal
  exception (e.g. `_ExtractError(message, type="EncryptedPDF")`) carrying the
  envelope `type`; `main` (013-04) maps it to exit 1.
- A corrupt / non-PDF input raises inside `pdfplumber` — wrap into
  `_ExtractError(type="CorruptPdf")` (or `NotAPdf` for an obvious non-PDF).
- Return the opened `pdfplumber.PDF` for use as a context manager.

**Function `_extract_page(page, *, layout)`** — implement, returns the
`PageRecord` (ARCH §4.2):
- `text = page.extract_text(layout=layout) or ""`.
- `tables = page.extract_tables()` — default settings only (§1.4(c)); raw
  list-of-rows form, `None` cells preserved (→ JSON `null`).
- `char_count = len(text.strip())`.
- `has_images = bool(page.images)`.
- `scanned = _classify_page(char_count, has_images)` — calls the (still
  stubbed → `False`) classifier; becomes correct when 013-03 lands.
- `n` is filled by the caller (`extract_pdf`) — 1-indexed.

**Function `extract_pdf(pdf_path, *, password, layout)`** — implement:
- `with _open_pdf(pdf_path, password) as pdf:` — **owns** the handle; the
  `with` block guarantees the file descriptor is released even on a
  mid-extraction exception (ARCH §5.4, reviewer m-4).
- Build `pages = [_extract_page(p, layout=layout) with n = i+1 ...]`.
- `doc_scanned, scanned_pages = _classify_document(pages)` — stubbed `(False, [])`
  until 013-03.
- Return `{"page_count": len(pages), "doc_scanned": doc_scanned,
  "scanned_pages": scanned_pages, "pages": pages}`.

Add the small `_ExtractError` exception class (message + `type` attribute).

### Component Integration

`extract_pdf` is called by `main` (still a `-999` stub until 013-04). This task
verifies `extract_pdf` directly via unit tests + the updated E2E.

## Test Cases

### E2E Tests (updated from 013-01 per `tdd-stub-first §2.4`)

1. **TC-E2E-02 `test_digital_dump_correct`** — `extract_pdf(digital.pdf,
   password=None, layout=False)` → `page_count == 2`; `doc_scanned is False`;
   every page `text` non-empty; page 1 has ≥ 1 entry in `tables` whose cell
   content matches the fixture's known 3×3 table; `char_count == len(text.strip())`.

### Unit Tests

1. **TC-UNIT-07 `test_extract_page_fields`** — a digital page record has all 6
   keys with correct types; `has_images is False` for the text-only digital
   pages.
2. **TC-UNIT-08 `test_tables_raw_form`** — `tables` is a list of row-lists;
   empty cells are `None`.
3. **TC-UNIT-09 `test_layout_flag`** — `extract_pdf(..., layout=True)` yields
   `text` ≥ the `layout=False` length on a column-bearing page (padding
   inflation, ARCH §4.2).
4. **TC-UNIT-10 `test_open_encrypted_raises`** — `_open_pdf(encrypted.pdf,
   None)` raises `_ExtractError` with `type == "EncryptedPDF"`;
   `_open_pdf(encrypted.pdf, "test-pw")` succeeds.
5. **TC-UNIT-11 `test_open_corrupt_raises`** — `_open_pdf` on a non-PDF file
   raises `_ExtractError` (`type` in `{"CorruptPdf", "NotAPdf"}`).
6. **TC-UNIT-12 `test_file_handle_released`** — after `extract_pdf` raises
   mid-extraction (monkeypatched `_extract_page`), no `pdfplumber.PDF` handle
   leaks (the `with` block ran its `__exit__`).

### Regression Tests

- `python3 -m unittest skills.pdf.scripts.tests.test_pdf_extract` — green.
- `bash skills/pdf/scripts/tests/test_e2e.sh` — pre-existing suite green.

## Acceptance Criteria

- [ ] `_open_pdf`, `_extract_page`, `extract_pdf` fully implemented; no stub
      remains in the extraction core.
- [ ] Digital-fixture E2E (TC-E2E-02) green — correct `page_count`, `text`,
      `tables` ([R6], [R7] 7.1/7.2/7.4).
- [ ] Encrypted PDF without a valid password raises `_ExtractError`
      `type=EncryptedPDF`; with `test-pw` it opens ([R6] 6.4).
- [ ] `extract_pdf` owns + releases the `pdfplumber` handle via `with`.
- [ ] `_classify_page` / `_classify_document` still stubbed (013-03 owns them) —
      `scanned`/`doc_scanned` are `False`/`(False,[])`, correct for the
      imageless digital fixture.
- [ ] Cross-skill `diff -q` silent (`_errors.py`, `preview.py`).
- [ ] Only `pdf_extract.py` + `test_pdf_extract.py` modified.

## Stub-First Gate (`tdd-stub-first §2`)

Stubs replaced: `_open_pdf`, `_extract_page`, `extract_pdf`. The smoke E2E from
013-01 is upgraded to TC-E2E-02 (real digital-fixture assertions). Classifier
and `main`/`_emit` remain stubbed for 013-03 / 013-04.

## Notes

- Default `extract_tables()` only — no `table_settings` tuning (§1.4(c)); the
  reference doc (013-05) tells the agent to drop to inline code for borderless
  tables.
- The exact `pdfminer` exception class names are confirmed by the
  architecture-reviewer (`PDFPasswordIncorrect` / `PDFEncryptionError`); catch
  both, plus a defensive broad `Exception` → `CorruptPdf` for anything else
  inside `_open_pdf`.

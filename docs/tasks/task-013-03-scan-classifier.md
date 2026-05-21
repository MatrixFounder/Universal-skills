# Task 013-03 [LOGIC IMPLEMENTATION]: Scan classifier

> **Predecessor:** 013-02 (extraction core).
> **RTM:** **completes** [R8]; [R7] sub-feature 7.5 (`scanned_pages`); advances [R12] (E2E green per `tdd-stub-first §2.4`).
> **ARCH:** §2.1 FC4, §4.3 (derived rule + truth table).

## Use Case Connection

- UC-2 main — whole-document scan → `doc_scanned=true`.
- UC-2 A2 — mixed digital + scanned document.
- UC-2 A3 — all-blank document → `doc_scanned=false` (the blank-page guard).

## Task Goal

Replace the two classifier stubs with the real per-page and document-level scan
logic from ARCH §4.3, so the dump's `scanned`, `doc_scanned`, and
`scanned_pages` fields are correct. After this task the scan-like fixture
reports `doc_scanned=true` and the all-blank case reports `false`. Exit-code
*mapping* (`doc_scanned → exit 10`) is still 013-04 — this task makes the
verdict in the dump correct.

## Changes Description

### Changes in Existing Files

#### File: `skills/pdf/scripts/pdf_extract.py`

**Function `_classify_page(char_count, has_images)`** — implement:
```python
return (char_count <= _SCANNED_CHAR_THRESHOLD) and has_images
```
The ONLY site that reads `_SCANNED_CHAR_THRESHOLD`.

**Function `_classify_document(pages)`** — implement per ARCH §4.3:
```python
scanned_pages = [p["n"] for p in pages if p["scanned"]]
no_meaningful_text = all(
    p["char_count"] <= _SCANNED_CHAR_THRESHOLD for p in pages
)
doc_scanned = bool(scanned_pages) and no_meaningful_text
return doc_scanned, scanned_pages
```
- Empty `pages` (0-page PDF) → `all(...)` is `True`, `scanned_pages` is `[]` →
  `doc_scanned` is `False` (truth-table row "Empty PDF").

**Threshold rationale** — add to the module docstring the §4.3 rationale block
(why `10`, the `--layout`/image-only-page reconciliation). This is the
docstring half of the dual-homed R8.1a requirement; the reference doc (013-05)
carries the other half.

### Component Integration

`_classify_page` is already called by `_extract_page` (wired in 013-02);
`_classify_document` by `extract_pdf`. No new call sites — this task only fills
the two function bodies.

## Test Cases

### E2E Tests (updated per `tdd-stub-first §2.4`)

1. **TC-E2E-03 `test_scanlike_doc_scanned`** — `extract_pdf(scanlike.pdf, …)` →
   `doc_scanned is True`; every page `scanned is True`; `scanned_pages` lists
   every page; each page `char_count == 0`.
2. **TC-E2E-02 (re-confirm)** — `digital.pdf` still `doc_scanned is False`,
   `scanned_pages == []`.

### Unit Tests — the ARCH §4.3 truth table, row by row

1. **TC-UNIT-13 `test_classify_page_threshold`** — `_classify_page(0, True)`
   True; `_classify_page(10, True)` True (boundary, `<=`);
   `_classify_page(11, True)` False; `_classify_page(0, False)` False.
2. **TC-UNIT-14 `test_doc_all_image_only`** — all pages `char_count=0,
   has_images=True` → `doc_scanned True`.
3. **TC-UNIT-15 `test_doc_single_page_image_only`** — 1 page, image-only →
   `(True, [1])`.
4. **TC-UNIT-16 `test_doc_mixed`** — digital pages (`char_count>10`) + image
   pages → `doc_scanned False`, `scanned_pages` = the image pages only.
5. **TC-UNIT-17 `test_doc_every_page_images_but_one_has_text`** — all pages
   have images, ≥ 1 has `char_count>10` → `doc_scanned False` (the
   `no_meaningful_text` guard).
6. **TC-UNIT-18 `test_doc_all_blank`** — all pages `char_count=0,
   has_images=False` → `(False, [])` — **never** `doc_scanned` (blank-page
   guard, reviewer M-2 / TASK R8.2a).
7. **TC-UNIT-19 `test_doc_empty_pdf`** — `_classify_document([])` →
   `(False, [])`.
8. **TC-UNIT-20 `test_doc_one_scan_rest_blank`** — 1 image-only page + blank
   pages → `doc_scanned True` (≥ 1 scanned page, no meaningful text).

### Regression Tests

- `python3 -m unittest skills.pdf.scripts.tests.test_pdf_extract` — green.
- `bash skills/pdf/scripts/tests/test_e2e.sh` — green.

## Acceptance Criteria

- [ ] `_classify_page` / `_classify_document` fully implemented per ARCH §4.3;
      no classifier stub remains.
- [ ] All 7 truth-table rows from ARCH §4.3 covered by TC-UNIT-13..20.
- [ ] Scan-like fixture → `doc_scanned True`; all-blank → `False`; mixed →
      `False` with correct `scanned_pages` ([R8], [R7] 7.5).
- [ ] Threshold rationale present in the `pdf_extract.py` module docstring
      ([R8] 8.1a — docstring half).
- [ ] `main`/`_emit` still stubbed (013-04 owns them).
- [ ] Cross-skill `diff -q` silent (`_errors.py`, `preview.py`).
- [ ] Only `pdf_extract.py` + `test_pdf_extract.py` modified.

## Stub-First Gate (`tdd-stub-first §2`)

Stubs replaced: `_classify_page`, `_classify_document`. E2E gains TC-E2E-03
(scan-like) and re-confirms TC-E2E-02. `main`/`_emit` remain stubbed.

## Notes

- `<=` not `<` at the threshold: `char_count == 10` counts as scanned (ARCH
  §4.3 code block — boundary locked, tested by TC-UNIT-13).
- This task does NOT set the process exit code — `extract_pdf` returns the
  verdict in the dict; `main` (013-04) maps `doc_scanned=True → exit 10`.

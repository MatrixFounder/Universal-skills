# Task 018-03 [LOGIC IMPLEMENTATION]: OCR runner + exception mapping + composition E2E

> **Predecessor:** 018-02. **This is the MVP gate.**
> **RTM:** **completes** [R1] (a/b/c), [R3a][R3b][R3c], [R4a][R4c],
> [R6a][R6b] (full exit matrix + exception→type mapping).
> **ARCH:** §2.1 (FC-5, FC-6), §4.4 (I-1..I-3), §5.2 (exit matrix), §5.3
> (composition contract).

## Use Case Connection

- UC-1 main — OCR an image-only PDF → searchable PDF.
- UC-2 — OCR + `--sidecar` text.
- UC-3 — `--redo-ocr` re-OCR.
- UC-1 A4 (mixed/skip-text), A5 (corrupt input), A6 (output unwritable).

## Task Goal

Replace the `run_ocr` stub with the real ocrmypdf delegation (skip/redo/force,
`--sidecar`, `--jobs`, atomic write) and complete the FC-6 exception→exit
mapping. Land the **composition E2E** that is the architecture's primary
acceptance hinge: scan PDF → `pdf_ocr` → `pdf_extract` reports
`doc_scanned=false` and recovers the fixture needle.

## Changes Description

### Changes in Existing Files

#### File: `skills/pdf/scripts/pdf_ocr.py`

**Function `run_ocr(inp, outp, *, lang, mode, sidecar, jobs, password, deskew,
rotate_pages, clean) -> int`** (replace stub):
- `ocr = _require_engine()`.
- Build the kwargs for `ocr.ocr(...)`:
  - `input_file=inp`, `output_file=tmp_out` (a `.partial` sibling of `outp` in
    the same directory — atomic write, I-3),
  - `language=lang` (list from `_validate_languages`),
  - mode → exactly one of `skip_text=True` / `redo_ocr=True` / `force_ocr=True`
    (default `skip_text`),
  - `sidecar=sidecar` if given,
  - `jobs=jobs` if given,
  - `deskew`/`rotate_pages`/`clean` only if their flags are set **and** 018-05
    has landed (until then they are accepted by the parser but raise a clear
    `_OcrError` "not yet implemented (bead 018-05)" if used — keeps the surface
    honest). *(If 018-05 ships first, wire them through instead.)*
  - `progress_bar=False`.
- On success: `os.replace(tmp_out, outp)` (atomic); if `sidecar` requested,
  confirm it exists; return `_EXIT_OK`. Always `try/finally` unlink `tmp_out`
  if it still exists (I-3).
- **Exception mapping (FC-6)** — wrap the `ocr.ocr(...)` call and translate
  `ocrmypdf.exceptions.*` to `_OcrError`:
  | ocrmypdf exception | `error_type` | exit |
  |---|---|---|
  | `EncryptedPdfError` | `EncryptedInput` | 1 |
  | `PriorOcrFoundError` | `PriorOcrFound` | 1 |
  | `InputFileError` / `BadArgsError` (bad/corrupt PDF) | `InputUnreadable` | 1 |
  | `MissingDependencyError` | `OcrEngineUnavailable` | 1 |
  | `OSError` writing output | `OutputWriteFailed` | 1 |
  | any other `Exception` | `InternalError` | 1 |
  (Confirm exact class names against the pinned ocrmypdf in 018-02; the table is
  the contract, names may need a small adjust.)
- Silence noisy `ocrmypdf` / `pikepdf` / `pdfminer` loggers at module import
  (copy the `logging.getLogger(...).setLevel(logging.ERROR)` idiom from
  `pdf_extract.py:60-`).

**Function `main`** (replace `_STUB_SENTINEL`):
- After lang validation (018-02): `return run_ocr(inp, outp, lang=langs,
  mode=args.mode, sidecar=sidecar, jobs=args.jobs, password=args.password,
  deskew=args.deskew, rotate_pages=args.rotate_pages, clean=args.clean)` inside
  the `try/except _OcrError → _report` block. On success print a one-line
  `OcrResult` summary to stdout (ARCH §4.2). Remove `_STUB_SENTINEL`.

## Test Cases

### E2E Tests (engine-gated — **soft-skip** when ocrmypdf/tesseract/gs absent)

1. **TC-E2E-03 `test_composition_roundtrip`** (the hinge, R4a) — build
   `scan.pdf` (needle `"OCR ТЕСТ 2026 hello мир"`); run `pdf_ocr.py scan.pdf
   scan.ocr.pdf`; assert exit 0 and `scan.ocr.pdf` exists with the same page
   count as input (I-1). Then run `pdf_extract.py scan.ocr.pdf` (or call
   `pdf_extract.extract_pdf`): assert exit 0, `doc_scanned == False`, and the
   recovered text contains the needle **case-insensitively** as a tolerant
   substring (OCR not bit-exact — assert a robust subset like `"2026"` and
   `"hello"`; Cyrillic recovery asserted only if `rus` is installed).
2. **TC-E2E-04 `test_sidecar_emitted`** (R4c) — `--sidecar scan.txt` →
   `scan.txt` exists and contains the needle subset.
3. **TC-E2E-05 `test_skip_text_noop_on_digital`** (R3a, A4) — run on
   `digital.pdf` with default `--skip-text` → exit 0, no crash, vector text
   still extractable from output (no destruction).

### Unit Tests

1. **TC-UNIT-14 `test_run_ocr_atomic_no_partial_on_failure`** — force the
   inner `ocr.ocr` to raise; assert `run_ocr` raises `_OcrError` and leaves **no**
   `*.partial` and **no** OUTPUT (I-3). (Patch `_require_engine` to return a fake
   module whose `.ocr` raises — runs without the real engine.)
2. **TC-UNIT-15 `test_exception_mapping`** — parametrized: a fake ocrmypdf whose
   `.ocr` raises each mapped exception type → assert the resulting `_OcrError.
   error_type` per the table.
3. **TC-UNIT-16 `test_mode_kwarg_selection`** — assert exactly one of
   `skip_text/redo_ocr/force_ocr` is passed True for each `--mode` (inspect the
   kwargs captured by the fake module).

### Regression Tests

- Full `python3 -m unittest skills.pdf.scripts.tests.test_pdf_ocr` — green.
- `bash skills/pdf/scripts/tests/test_e2e.sh` — green (the OCR block is added in
  018-06; nothing existing changed here).

## Acceptance Criteria

- [ ] `run_ocr` produces a searchable PDF via ocrmypdf with the original raster
      + text layer, same page count/geometry (I-1, [R1a][R1b][R1c]).
- [ ] skip/redo/force modes wired to the correct ocrmypdf kwarg ([R3a][R3b][R3c]).
- [ ] `--sidecar` emits the text file ([R4c]); `--jobs` passed through.
- [ ] Atomic write — no partial/OUTPUT on failure (I-3, TC-UNIT-14).
- [ ] FC-6 exception→`error_type` mapping complete; all hard failures exit 1
      with the `_errors.py` envelope ([R6a][R6b], D-A1).
- [ ] **Composition E2E green with engine present**; soft-skips (clearly logged)
      when ocrmypdf/tesseract/gs absent ([R4a], §0.3 of PLAN).
- [ ] `_STUB_SENTINEL` removed; `main` returns real exit codes.
- [ ] Cross-skill `diff -q` silent gate (ARCH §9) — both produce no output.

## Stub-First Gate (`tdd-stub-first §2`)

After this task the MVP CLI is fully functional: scan→OCR→searchable PDF,
composition round-trip green (engine present). Unit tests exercise the mapping
+ atomicity **without** the engine via a fake module; the real-OCR E2E is
engine-gated and soft-skips otherwise.

## Notes

- `os.replace` (not `Path.rename`) for the atomic finalize — same-filesystem
  guaranteed because `tmp_out` is a sibling of `outp`.
- Cyrillic OCR quality depends on the `rus` traineddata version; keep the needle
  assertion tolerant (subset, case-insensitive) to avoid flake (TASK R8a).
- `--deskew`/`--rotate-pages`/`--clean` are parser-accepted but gated to a clear
  "bead 018-05" error until that bead lands — never silently ignored.

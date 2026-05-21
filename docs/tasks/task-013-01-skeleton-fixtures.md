# Task 013-01 [STUB CREATION]: `pdf_extract.py` skeleton + fixtures + test scaffolding

> **Predecessor:** none (bootstrap task of the chain).
> **RTM:** scaffolds [R6][R7][R8][R9]; **completes** [R10][R11]; scaffolds [R12].
> **ARCH:** §3.2, §5.1, §5.4, §11 (bead 013-01).

## Use Case Connection

- UC-1, UC-2, UC-3 — all scaffolded at stub level (smoke E2E only).

## Task Goal

Lay down the **frozen public surface** for `pdf_extract.py`: one self-contained
script `skills/pdf/scripts/pdf_extract.py` with every function from ARCH §5.4
present as a stub, the full argparse surface declared (ARCH §5.1), the exit-code
and threshold constants fixed; plus the reproducible fixture builder + the 3
committed test fixtures + a test file with ONE smoke E2E that passes on the
stubs (Red → Green per `tdd-stub-first §1`).

**Frozen surface contract (no later task may rename these):**

- Module constants: `_SCANNED_CHAR_THRESHOLD = 10`, `_EXIT_OK = 0`,
  `_EXIT_FAIL = 1`, `_EXIT_USAGE = 2`, `_EXIT_SCANNED = 10`,
  `_STUB_SENTINEL = -999` (removed when 013-04 lands real `main`).
- Functions (signatures per ARCH §5.4): `main`, `_build_parser`, `extract_pdf`,
  `_open_pdf`, `_extract_page`, `_classify_page`, `_classify_document`, `_emit`.
- Argparse surface: positional `INPUT`, options `-o/--output`, `--layout`,
  `--password`, `--json-errors`.

## Changes Description

### New Files

#### `skills/pdf/scripts/pdf_extract.py` (the stub script)

- **Module docstring** — states plainly (TASK R10.2, R10.4): *"Extracts a PDF
  into a structured per-page JSON **dump** (text + tables + scan flags). This is
  NOT a Markdown converter — it never emits Markdown. Final Markdown composition
  (headings, reading order, cross-page table stitching) is the caller's job; see
  `references/pdf-to-markdown.md`."* Also lists honest-scope items §1.4
  (a)/(b)/(c)/(d)/(h)/(i) as bullet comments.
- **Imports:** `argparse`, `json`, `sys`, `pathlib.Path`, `pdfplumber`; the
  sibling `_errors` module (`from _errors import add_json_errors_argument,
  report_error`) — with the `sys.path` insert idiom used by the other pdf
  scripts so `_errors` resolves.
- **Constants** as listed in the frozen contract.
- `_build_parser() -> argparse.ArgumentParser` — **REAL** (not a stub):
  declares the full surface per ARCH §5.1, calls
  `add_json_errors_argument(parser)`. `--help`/description text carries the
  "dump, not Markdown" disclaimer (R10.3) and the `--password` argv-visibility
  note (§1.4(i)).
- `_classify_page(char_count: int, has_images: bool) -> bool` — STUB `return False`.
- `_classify_document(pages: list[dict]) -> tuple[bool, list[int]]` — STUB
  `return (False, [])`.
- `_extract_page(page, *, layout: bool) -> dict` — STUB returning the sentinel
  record `{"n": 0, "text": "", "tables": [], "char_count": 0,
  "has_images": False, "scanned": False}`.
- `_open_pdf(pdf_path, password)` — STUB `raise NotImplementedError`.
- `extract_pdf(pdf_path: Path, *, password, layout) -> dict` — STUB returning
  the sentinel dump `{"page_count": 0, "doc_scanned": False,
  "scanned_pages": [], "pages": []}`.
- `_emit(dump: dict, out_path) -> None` — STUB `pass`.
- `main(argv=None) -> int` — STUB: builds the parser, `parse_args(argv)` (so
  `--help` works and a bad invocation exits 2 via the envelope), then
  `return _STUB_SENTINEL`.
- `if __name__ == "__main__": sys.exit(main())`.

#### `skills/pdf/scripts/tests/_pdf_extract_fixtures.py` (fixture builder)

Mirrors the existing `tests/_acroform_fixture.py` pattern. Functions:
- `build_digital_pdf(path)` — `reportlab` draws a **2-page** PDF: page 1 = a
  title + 2 paragraphs + one **lined** table (3×3, ruled so
  `extract_tables()` detects it); page 2 = a heading + a paragraph. Real
  selectable text.
- `build_scanlike_pdf(path)` — `Pillow` renders document-looking text to a PNG
  raster (no text layer), `reportlab` places that PNG **full-page**; 1 page.
  Result: image-only page, 0 extractable characters, `page.images` non-empty.
- `build_encrypted_pdf(path, password)` — build the digital PDF in a temp file,
  then `pypdf.PdfWriter` + `.encrypt(password)` → write `path`.
- `build_all(fixtures_dir)` + `if __name__ == "__main__"` — writes
  `digital.pdf`, `scanlike.pdf`, `encrypted.pdf` into the dir; idempotent
  (overwrites).

#### `skills/pdf/scripts/tests/fixtures/digital.pdf`, `scanlike.pdf`, `encrypted.pdf`

The 3 committed fixtures, produced by `_pdf_extract_fixtures.py build_all`
(provenance = the builder; TASK R11.3). `encrypted.pdf` password: `test-pw`.

#### `skills/pdf/scripts/tests/test_pdf_extract.py` (test scaffolding)

`unittest`-style. Phase-1 content = ONE smoke E2E (TC-E2E-01) + the 6-test
unit cluster below (TC-UNIT-01..06); later tasks (013-02/03/04) **update** the
assertions per `tdd-stub-first §2.4`.

### Changes in Existing Files

None. `requirements.txt` is **NOT** touched (ARCH §6 — `pdfplumber` /
`reportlab` / `Pillow` / `pypdf` already declared).

### Component Integration

`pdf_extract.py` sits alongside `pdf_split.py` / `pdf_fill_form.py` in
`skills/pdf/scripts/`; the fixture builder + tests sit in
`skills/pdf/scripts/tests/` next to `_acroform_fixture.py` / `test_battery.py`.

## Test Cases

### E2E Tests (smoke — stub phase)

1. **TC-E2E-01 `test_help_lists_surface`** — subprocess
   `python3 pdf_extract.py --help` → exit 0; stdout contains `-o`/`--output`,
   `--layout`, `--password`, `--json-errors`, and the word "dump" + a
   "not … Markdown"/"never emits Markdown" disclaimer.
   - Note: stub stage — `main` returns `-999`, but argparse handles `--help`.

### Unit Tests

1. **TC-UNIT-01 `test_module_imports`** — `import pdf_extract` succeeds.
2. **TC-UNIT-02 `test_constants_locked`** — `_SCANNED_CHAR_THRESHOLD == 10`;
   `_EXIT_OK/_EXIT_FAIL/_EXIT_USAGE/_EXIT_SCANNED == 0/1/2/10`.
3. **TC-UNIT-03 `test_main_returns_sentinel`** —
   `main(["<fixtures>/digital.pdf"])` returns `-999`.
4. **TC-UNIT-04 `test_classify_stubs`** — `_classify_page(0, True) is False`;
   `_classify_document([]) == (False, [])`.
5. **TC-UNIT-05 `test_extract_pdf_sentinel`** — `extract_pdf` stub returns a
   dict with keys `{page_count, doc_scanned, scanned_pages, pages}`.
6. **TC-UNIT-06 `test_fixtures_exist_and_valid`** — the 3 fixture files exist;
   `digital.pdf` opens via `pdfplumber` with ≥ 2 pages; `scanlike.pdf` opens
   with ≥ 1 page and page 1 has `page.images` non-empty and
   `(page.extract_text() or "").strip() == ""`; `encrypted.pdf` is detected as
   encrypted (open without password raises / `is_encrypted`).

### Regression Tests

- `bash skills/pdf/scripts/tests/test_e2e.sh` — pre-existing pdf suite still
  green (this task adds files, modifies none).
- `python3 -m unittest skills.pdf.scripts.tests.test_pdf_extract` — green.

## Acceptance Criteria

- [ ] `skills/pdf/scripts/pdf_extract.py` exists; all 8 functions from ARCH §5.4
      present; `_build_parser` is real; the rest are stubs.
- [ ] Module docstring + `--help` carry the "dump, not a Markdown converter"
      disclaimer ([R10]).
- [ ] `_pdf_extract_fixtures.py` exists and `build_all` regenerates the 3
      fixtures deterministically.
- [ ] `tests/fixtures/{digital,scanlike,encrypted}.pdf` committed ([R11]).
- [ ] All 6 unit tests + the smoke E2E pass on the stubs.
- [ ] `python3 pdf_extract.py --help` exit 0.
- [ ] Cross-skill `diff -q` silent gate (ARCH §9):
      ```bash
      diff -q skills/docx/scripts/_errors.py  skills/pdf/scripts/_errors.py
      diff -q skills/docx/scripts/preview.py  skills/pdf/scripts/preview.py
      ```
      Both produce no output.
- [ ] No existing file modified; `requirements.txt` untouched.

## Stub-First Gate (`tdd-stub-first §1`)

After this task: `import pdf_extract` works; `main(["…digital.pdf"]) == -999`;
`--help` exits 0; the 3 fixtures load. The smoke E2E IS the Phase-1 gate —
013-02/03/04 update it to real assertions.

## Notes

- The fixtures are committed for test speed; the builder is committed for
  provenance/regeneration (TASK R11.3 — "no opaque binary blobs").
- The scan-like fixture MUST contain **zero** selectable text (ARCH §4.3,
  reviewer M-4) — do not stamp a page number; its `char_count` must be an
  unambiguous 0.
- `_STUB_SENTINEL` is removed in 013-04 when `main` returns real exit codes.

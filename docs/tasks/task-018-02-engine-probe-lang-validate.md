# Task 018-02 [LOGIC IMPLEMENTATION]: Engine probe + language validator

> **Predecessor:** 018-01.
> **RTM:** **completes** [R2] (a/b/c), [R7b]; [R6a][R6b] (the
> `OcrEngineUnavailable` / `LanguagePackMissing` envelopes).
> **ARCH:** §2.1 (FC-3, FC-4), §4.3 (envelope), §12 (D-A1, D-A4).

## Use Case Connection

- UC-1 A1 — engine missing → `OcrEngineUnavailable` (exit 1).
- UC-1 A2 — language pack missing → `LanguagePackMissing` (exit 1).

## Task Goal

Replace the `_require_engine` and `_validate_languages` stubs from 018-01 with
real logic: lazy-import `ocrmypdf` and fail loud with remediation if absent;
validate every requested `--lang` token against the installed tesseract language
set (default `eng+rus`) and fail loud naming the missing pack. **Both failures
are testable without the engine present** (the missing-engine path needs
`ocrmypdf` absent; the missing-pack path is reachable by stubbing the
installed-set query).

## Changes Description

### Changes in Existing Files

#### File: `skills/pdf/scripts/pdf_ocr.py`

**Function `_require_engine() -> "module"`** (replace stub):
- `try: import ocrmypdf` inside the function; `except ImportError as exc:`
  `raise _OcrError(msg, error_type="OcrEngineUnavailable")` where `msg` carries
  the remediation (folded into the message string per ARCH §4.3):
  *"OCR engine not available (ocrmypdf not installed). Install it:
  `bash skills/pdf/scripts/install.sh --with-ocr`, and ensure system `tesseract`
  (+ eng,rus) and `ghostscript` are on PATH."* Return the imported module.
- Mirrors pdf-11 `_load_playwright` / `ChromeEngineUnavailable`
  (`html2pdf_lib/chrome_engine.py:435`).

**Function `_installed_languages(ocrmypdf_mod) -> set[str]`** (new helper):
- Return the installed tesseract language set. Prefer
  `ocrmypdf_mod.get_languages()` if available; else shell out to
  `tesseract --list-langs` via `subprocess.run([...], capture_output=True)` (no
  `shell=True`, S-1) and parse. On a tesseract-missing failure, raise
  `_OcrError(..., error_type="OcrEngineUnavailable")` with the gs/tesseract
  remediation (tesseract is part of the engine).

**Function `_validate_languages(lang: str, installed: set[str]) -> list[str]`**
(replace stub):
- `requested = [t for t in lang.split("+") if t]`; if empty → `_OcrError`
  usage-style (`error_type="LanguagePackMissing"`, message "no language given").
- `missing = [t for t in requested if t not in installed]`; if `missing` →
  `_OcrError(msg, error_type="LanguagePackMissing")` naming the missing tokens
  + per-OS hint (`details={"missing": missing, "requested": lang}` via the
  caller's `report_error`). Order of `requested` preserved (R2c).
- Return `requested`.

**Function `main` (wire 018-02 into the flow):**
- After `_resolve_paths`, inside the `try/except _OcrError → _report`:
  `ocr = _require_engine()`; `installed = _installed_languages(ocr)`;
  `langs = _validate_languages(args.lang, installed)`. (Then `run_ocr(...)` is
  still the 018-01 stub → `main` returns `_STUB_SENTINEL` until 018-03; that is
  acceptable — this task's gate is the two failure paths.)

## Test Cases

### E2E Tests

1. **TC-E2E-02 `test_engine_missing_envelope`** — run `pdf_ocr.py scan.pdf
   out.pdf --json-errors` in a subprocess whose `PYTHONPATH`/venv has **no**
   `ocrmypdf` (e.g. monkeypatch `sys.modules["ocrmypdf"]=None` via a tiny
   wrapper, or run with a venv lacking it) → exit 1; stderr JSON `type` ==
   `OcrEngineUnavailable`; message mentions `--with-ocr`.
   - Soft-skip note: if `ocrmypdf` IS installed, simulate absence by forcing the
     `ImportError` (patch builtins.__import__ in an in-process unit instead).

### Unit Tests (update the 018-01 cluster per `tdd-stub-first §2.4`)

1. **TC-UNIT-09 `test_require_engine_missing`** — patch `builtins.__import__` to
   raise `ImportError` for `ocrmypdf`; `_require_engine()` raises `_OcrError`
   with `error_type == "OcrEngineUnavailable"`; message contains "--with-ocr".
2. **TC-UNIT-10 `test_validate_languages_default`** —
   `_validate_languages("eng+rus", {"eng","rus","osd"}) == ["eng","rus"]`.
3. **TC-UNIT-11 `test_validate_languages_missing`** —
   `_validate_languages("eng+deu", {"eng","rus"})` raises `_OcrError`
   (`type == "LanguagePackMissing"`); message names `deu`.
4. **TC-UNIT-12 `test_validate_languages_order_preserved`** —
   `_validate_languages("rus+eng", {"eng","rus"}) == ["rus","eng"]`.
5. **TC-UNIT-13 `test_validate_languages_empty`** — `_validate_languages("+",
   {...})` raises `_OcrError` (`LanguagePackMissing`, "no language").
6. **Update TC-UNIT-07** — `main` on valid paths still returns `-999` **only
   when the engine + eng/rus are present**; otherwise it now returns 1 with the
   appropriate envelope (adjust the assertion to be engine-aware / soft-skip).

### Regression Tests

- `python3 -m unittest skills.pdf.scripts.tests.test_pdf_ocr` — green.
- `bash skills/pdf/scripts/tests/test_e2e.sh` — green (no existing CLI changed).

## Acceptance Criteria

- [ ] `_require_engine` lazy-imports `ocrmypdf`; missing → `_OcrError`
      `OcrEngineUnavailable` with `--with-ocr` remediation ([R7b][R6a][R6b]).
- [ ] `_validate_languages` validates against the installed set; default
      `eng+rus`; missing pack → `LanguagePackMissing` naming the pack; order
      preserved; empty rejected ([R2a][R2b][R2c]).
- [ ] No `shell=True`; `subprocess` (if used) takes an argv list (S-1).
- [ ] Engine-missing and pack-missing envelopes follow `_errors.py` schema
      (`{v,error,code,type,details?}`), exit 1 (ARCH §4.3, D-A1).
- [ ] Unit cluster updated + green; `import pdf_ocr` still works engine-absent.
- [ ] Cross-skill `diff -q` silent gate (ARCH §9) — both produce no output.

## Stub-First Gate (`tdd-stub-first §2`)

The two failure clusters are now real and green (engine-absent + pack-missing).
`run_ocr` remains stubbed → the happy path completes in 018-03.

## Notes

- Finalize the exact `ocrmypdf` floor in `requirements-ocr.txt` here, checked
  against the current PyPI release (memory "prefer dependency upgrades").
- Keep the missing-engine remediation message identical in wording to the
  `references/ocr.md` install section (018-06) so users see one consistent hint.

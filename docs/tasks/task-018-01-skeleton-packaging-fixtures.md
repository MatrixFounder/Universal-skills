# Task 018-01 [STUB CREATION]: `pdf_ocr.py` skeleton + packaging + fixtures + test scaffolding

> **Predecessor:** none (bootstrap task of the chain).
> **RTM:** scaffolds [R1][R2][R3]; **completes** [R3d][R6c][R6d][R7a][R7c][R7d];
> scaffolds [R6a][R6b][R7b][R8].
> **ARCH:** §2.1 (FC-1/FC-2), §3.2, §5.1, §5.2, §11 (bead 018-01).

## Use Case Connection

- UC-1, UC-2, UC-3 — scaffolded at stub level (`--help` smoke E2E).
- UC-1 A3 (same-path guard) — **real** in this task.

## Task Goal

Lay down the **frozen public surface** of `pdf_ocr.py`: one self-contained
script with the full argparse contract (ARCH §5.1) incl. the
`--skip-text`/`--redo-ocr`/`--force-ocr` mutex; the exit-matrix constants; the
path-resolve + self-overwrite + sidecar-collision guards **REAL**; and the
engine-probe / language-validator / OCR-runner / error-mapper as **stubs**.
Add the soft-optional packaging (`requirements-ocr.txt` + `install.sh --with-ocr`
probe), the reproducible fixture builder + runtime fixtures, and a test file
whose `--help` smoke E2E + unit cluster pass on the stubs (Red→Green per
`tdd-stub-first §1`).

**Frozen surface contract (no later task may rename these):**

- Module constants: `_EXIT_OK = 0`, `_EXIT_FAIL = 1`, `_EXIT_USAGE = 2`,
  `_EXIT_SELF_OVERWRITE = 6`, `_DEFAULT_LANG = "eng+rus"`,
  `_STUB_SENTINEL = -999` (removed when 018-03 lands the real `main`).
- Domain exception `_OcrError(Exception)` with `message` + `error_type`
  (mirrors `pdf_extract._ExtractError` at `pdf_extract.py:80`).
- Functions: `main`, `_build_parser`, `_resolve_paths`, `_same_path`,
  `_require_engine`, `_validate_languages`, `run_ocr`, `_report`.
- Argparse surface: positional `INPUT`, `OUTPUT`; options `--lang`,
  mutex group `--skip-text|--redo-ocr|--force-ocr`, `--sidecar`, `--jobs`,
  `--password`, `--deskew`, `--rotate-pages`, `--clean`, `--json-errors`.

## Changes Description

### New Files

#### `skills/pdf/scripts/pdf_ocr.py` (the stub script)

- **Module docstring** — states plainly: *"Wrap `ocrmypdf` to convert an
  image-only (scanned) PDF into a **searchable PDF** (original raster + invisible
  OCR text layer). Default languages `eng+rus`. Remediation hop for
  `pdf_extract.py` exit 10 `DocumentScanned`."* Lists honest-scope items
  (engine not bundled; `--password` argv-visible; no global timeout; default
  `--skip-text` never destroys vector text; output unencrypted). Includes the
  **Exit codes** block (D-A1): `0` ok / `1` fail (with envelope `type`
  discriminator) / `2` usage / `6` SelfOverwriteRefused.
- **Imports:** `argparse`, `os`, `sys`, `pathlib.Path`; the sibling `_errors`
  via the same `sys.path` insert idiom as `pdf_extract.py`
  (`from _errors import add_json_errors_argument, report_error`).
  **`ocrmypdf` is NOT imported at module top** — it is lazy-imported inside
  `_require_engine` (018-02), so the module imports without the optional dep.
- **Constants** + `_OcrError` as listed in the frozen contract.
- `_build_parser() -> argparse.ArgumentParser` — **REAL**:
  - positional `INPUT` (`type=Path`), `OUTPUT` (`type=Path`);
  - `--lang` (`default=_DEFAULT_LANG`, metavar `LANGS`, help notes the `+`-list
    and the eng+rus default);
  - a **mutually-exclusive group** for `--skip-text` (default semantics) /
    `--redo-ocr` / `--force-ocr` — implemented as
    `add_mutually_exclusive_group()` with three `store_const` into `dest="mode"`
    (`default="skip_text"`);
  - `--sidecar` (`type=Path`, metavar `PATH.txt`);
  - `--jobs` (`type=int`, default `None`);
  - `--password` (default `None`, help carries the argv-visibility note);
  - `--deskew`, `--rotate-pages`, `--clean` (`store_true`, help marks them
    "needs extra host tools; not active until bead 018-05 — see
    references/ocr.md" so a `--help` reader is not surprised by the interim
    "bead 018-05" `_OcrError` raised in 018-03 — PR-4);
  - `add_json_errors_argument(parser)`.
- `_same_path(a: Path, b: Path) -> bool` — **REAL** — `a.resolve() ==
  b.resolve()` (copy the `pdf_extract._same_path` idiom).
- `_resolve_paths(args) -> tuple[Path, Path, Path | None]` — **REAL** —
  existence check on INPUT (`_OcrError("Input not found", error_type=
  "InputNotFound")`); self-overwrite guard (`_same_path(INPUT, OUTPUT)` →
  `_OcrError(..., error_type="SelfOverwriteRefused")` with code 6); sidecar
  collision guard (sidecar ∈ {INPUT, OUTPUT} → SelfOverwriteRefused).
- `_require_engine()` — **STUB** `raise NotImplementedError` (018-02).
- `_validate_languages(lang: str) -> list[str]` — **STUB** `return
  lang.split("+")` (no validation yet; 018-02).
- `run_ocr(inp, outp, *, lang, mode, sidecar, jobs, password, deskew,
  rotate_pages, clean) -> int` — **STUB** `raise NotImplementedError` (018-03).
- `_report(exc: _OcrError, *, json_mode: bool) -> int` — **REAL** thin wrapper
  over `report_error(exc.message, code=<6 if SelfOverwriteRefused else 1>,
  error_type=exc.error_type, json_mode=json_mode)`.
- `main(argv=None) -> int` — **STUB-ish**: build parser, `parse_args` (so
  `--help` exits 0 and bad usage exits 2 via the envelope), run `_resolve_paths`
  (real guards active) inside `try/except _OcrError → _report`, then
  `return _STUB_SENTINEL`.
- `if __name__ == "__main__": sys.exit(main())`.

#### `skills/pdf/scripts/requirements-ocr.txt`

- Single pinned line `ocrmypdf>=16` (a current floor; finalize exact pin in
  018-02 against PyPI per ARCH §6 / memory "prefer dependency upgrades"). One
  header comment: "Soft-optional OCR engine — installed only via
  `install.sh --with-ocr`. Also needs system tesseract (+eng,rus) and
  ghostscript (checked, not installed)."

#### `skills/pdf/scripts/tests/_pdf_ocr_fixtures.py` (fixture builder)

Mirrors `tests/_pdf_extract_fixtures.py`. Functions:
- `build_scan_pdf(path, text="OCR ТЕСТ 2026 hello мир")` — `Pillow` renders a
  known ASCII+Cyrillic string to a PNG raster (no text layer), `reportlab`
  places it full-page; 1–2 pages. Image-only, 0 extractable chars. **The needle
  string is the contract for the 018-03 composition E2E.**
- `build_digital_pdf(path)` — `reportlab` draws a normal selectable-text PDF
  (for the `--skip-text` no-op / mixed test).
- `build_all(fixtures_dir)` + `__main__` — writes `scan.pdf`, `digital.pdf`;
  idempotent. **Build-at-runtime** (D-01: skill `.gitignore` ignores `*.pdf`).

#### `skills/pdf/scripts/tests/test_pdf_ocr.py` (test scaffolding)

`unittest`-style. Phase-1 = `--help` smoke E2E + the unit cluster below; later
tasks (018-02/03) **update** the assertions per `tdd-stub-first §2.4`.

### Changes in Existing Files

#### `skills/pdf/scripts/install.sh`

- Add a `--with-ocr` flag (parallel to the existing `--with-chrome`): when set,
  `pip install --upgrade -r requirements-ocr.txt` into `.venv`, then **probe**
  (not install) `command -v tesseract`, `tesseract --list-langs` for `eng` and
  `rus`, and `command -v gs`, printing per-OS install hints (macOS `brew install
  tesseract tesseract-lang ghostscript`; Debian `apt install tesseract-ocr
  tesseract-ocr-eng tesseract-ocr-rus ghostscript`; Fedora `dnf install
  tesseract tesseract-langpack-eng tesseract-langpack-rus ghostscript`). Set
  `missing_host=1` on any miss (consistent with the weasyprint probe). Extend
  the `--help` heredoc + the trailing "Usage" hints.
- **Base path (no flag) is unchanged** (R7d).

`requirements.txt` is **NOT** touched (R7d).

### Component Integration

`pdf_ocr.py` sits alongside `pdf_extract.py` in `skills/pdf/scripts/`; fixtures +
tests sit in `skills/pdf/scripts/tests/` next to `_pdf_extract_fixtures.py`.

## Test Cases

### E2E Tests (smoke — stub phase)

1. **TC-E2E-01 `test_help_lists_surface`** — `python3 pdf_ocr.py --help` → exit
   0; stdout contains `INPUT`, `OUTPUT`, `--lang`, `--skip-text`, `--redo-ocr`,
   `--force-ocr`, `--sidecar`, `--json-errors`, the word "searchable", and the
   `eng+rus` default.

### Unit Tests

1. **TC-UNIT-01 `test_module_imports_without_ocrmypdf`** — `import pdf_ocr`
   succeeds **even if `ocrmypdf` is absent** (asserts no top-level engine import).
2. **TC-UNIT-02 `test_constants_locked`** — `_EXIT_OK/_EXIT_FAIL/_EXIT_USAGE/
   _EXIT_SELF_OVERWRITE == 0/1/2/6`; `_DEFAULT_LANG == "eng+rus"`.
3. **TC-UNIT-03 `test_mode_mutex`** — `_build_parser().parse_args([...,
   "--redo-ocr","--force-ocr"])` raises SystemExit (argparse exit 2);
   default `parse_args(["in.pdf","out.pdf"]).mode == "skip_text"`.
4. **TC-UNIT-04 `test_same_path_guard`** — `main(["x.pdf","x.pdf"])` returns 6
   (`SelfOverwriteRefused`) and writes nothing; symlink alias also → 6.
5. **TC-UNIT-05 `test_sidecar_collision_guard`** —
   `main(["in.pdf","out.pdf","--sidecar","out.pdf"])` → 6.
6. **TC-UNIT-06 `test_input_not_found`** —
   `main(["nope.pdf","out.pdf"])` → 1 with `error_type`/`type` `InputNotFound`
   (parse stderr under `--json-errors`).
7. **TC-UNIT-07 `test_main_returns_sentinel_on_valid_paths`** — with a built
   `scan.pdf` and a fresh OUTPUT, `main([...])` returns `-999` (runner stubbed).
8. **TC-UNIT-08 `test_fixtures_build`** — `build_all` produces `scan.pdf`
   (image-only: `page.images` non-empty, `extract_text().strip()==""`) and
   `digital.pdf` (selectable text present).

### Regression Tests

- `bash skills/pdf/scripts/tests/test_e2e.sh` — pre-existing suite still green
  (this task adds files + an `install.sh` branch; modifies no existing CLI).
- `python3 -m unittest skills.pdf.scripts.tests.test_pdf_ocr` — green on stubs.

## Acceptance Criteria

- [ ] `skills/pdf/scripts/pdf_ocr.py` exists; all functions from the frozen
      contract present; `_build_parser`/`_same_path`/`_resolve_paths`/`_report`
      real; `_require_engine`/`_validate_languages`/`run_ocr` stubbed.
- [ ] `import pdf_ocr` works with `ocrmypdf` **absent** (lazy import) ([R7b] scaffold).
- [ ] Mode mutex enforced; default mode `skip_text` ([R3d]).
- [ ] Same-path + sidecar-collision guards return exit 6 ([R6c][R6d]).
- [ ] `requirements-ocr.txt` exists; `install.sh --with-ocr` installs it into
      `.venv` and probes tesseract/eng/rus/gs with hints; base `install.sh` and
      `requirements.txt` unchanged ([R7a][R7c][R7d]).
- [ ] `_pdf_ocr_fixtures.py build_all` regenerates `scan.pdf`/`digital.pdf`
      deterministically (build-at-runtime, D-01).
- [ ] `--help` smoke E2E + all 8 unit tests pass on stubs.
- [ ] Cross-skill `diff -q` silent gate (ARCH §9):
      ```bash
      diff -q skills/docx/scripts/_errors.py  skills/pdf/scripts/_errors.py
      diff -q skills/docx/scripts/preview.py  skills/pdf/scripts/preview.py
      ```
      Both produce no output.

## Stub-First Gate (`tdd-stub-first §1`)

After this task: `import pdf_ocr` works (engine absent); `--help` exits 0; the
real guards return 6/1 correctly; `main` on valid paths returns `-999`; fixtures
build. The smoke E2E + guard units ARE the Phase-1 gate — 018-02/03 update them.

## Notes

- The scan fixture MUST contain **zero** selectable text (so the 018-03
  composition assertion "`pdf_extract` reads the needle only after OCR" is
  unambiguous). The needle string is shared with 018-03.
- `_STUB_SENTINEL` is removed in 018-03 when `main` returns real exit codes.
- Do NOT import `ocrmypdf` at module top — TC-UNIT-01 locks this (keeps the base
  skill importable without the optional dep).

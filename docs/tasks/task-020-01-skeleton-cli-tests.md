# Task 020-01 [STUB CREATION]: `pptx2md/` package skeleton + shim + CLI surface + RED tests

> **Predecessor:** none (bootstrap task of the chain).
> **RTM:** scaffolds Epic A/B/C/D/E; **completes** [R-D2] (CLI contract surface),
> [R-D4a] (self-overwrite guard), the exit-code map.
> **ARCH:** §2.1 (FC-5), §3.2, §4 (model shapes), §5.1 (CLI), §5.3 (envelope), §11 (bead 020-01).

## Use Case Connection

- UC-1…UC-5 — scaffolded at stub level (`--help` smoke E2E).
- UC-3 self-overwrite path (R-D4a) — **real** in this task.

## Task Goal

Lay down the **frozen public surface** of the `pptx2md/` package + the
`pptx2md.py` shim: the full argparse contract (ARCH §5.1), the exit-matrix
constants, the `_AppError` exception hierarchy, the model dataclasses, and the
self-overwrite / path-resolution guards **REAL**; with `extract`/`images`/`ocr`/
`emit` as **stubs**. Write a test file whose `--help` smoke E2E + unit cluster pass
on the stubs (Red→Green per `tdd-stub-first §1`).

**Frozen surface contract (no later task may rename these):**

- **`pptx2md/exceptions.py`** — `_AppError(Exception)` base with class attr
  `CODE: int` + instance `error_type: str` + optional `details: dict`. Subclasses:
  `SelfOverwriteRefused(CODE=6)`, `OcrEngineUnavailable(CODE=1)`,
  `LanguagePackMissing(CODE=1)`, `BadInput(CODE=1)`, `InternalError(CODE=1)`.
  (`EncryptedFileError` is **imported from `office._encryption`**, not redefined;
  `main` maps it to code 3 — AR-1/MAJOR-1/D-6.)
- **Module/CLI constants** (in `cli.py`): `_EXIT_OK=0`, `_EXIT_USAGE=2`,
  `_EXIT_ENCRYPTED=3`, `_EXIT_SELF_OVERWRITE=6`, `_DEFAULT_OCR_LANG="eng+rus"`,
  `_STUB_SENTINEL=-999` (removed when 020-04 lands the real `main`).
- **Functions:** `cli.build_parser`, `cli._resolve_paths`, `cli._resolve_media_dir`,
  `cli.main`, `cli.convert`; `extract.assert_openable`, `extract.build_deck`;
  `images.safe_image_meta`, `images.materialise`; `ocr.probe`, `ocr.ocr_asset`;
  `emit.render_deck`. (`convert` is pptx's programmatic API name — it intentionally
  diverges from xlsx's `convert_xlsx_to_md`; MINOR-3, do not "consistency-fix".)
- **Argparse surface (ARCH §5.1):** positional `INPUT`, `OUTPUT` (nargs `?`,
  default `-`); `--no-images`, `--media-dir` (Path), `--no-notes`, `--include-hidden`,
  `--ocr`, `--ocr-lang` (default `eng+rus`), `--jobs` (int, default 1), `--ocr-timeout`
  (**`type=float`**, default `120`, MINOR-2), `--json-errors` (via `add_json_errors_argument`).
- **Model dataclasses (`pptx2md/model.py`)** per ARCH §4: `Deck`, `Slide`, the
  `Block` union (`Heading`, `Bullets`+`BulletItem`, `Table`, `ImageRef`,
  `Placeholder`), `MediaAsset`, `PlaceholderAsset`, `OcrResult` (frozen outer
  dataclasses; inner lists mutable — mirror xlsx_read M3 honest-scope).

## Changes Description

### New Files

#### `skills/pptx/scripts/pptx2md.py` (thin shim — CLI entrypoint)
- **`_venv_bootstrap` prelude (D-2)** as the **first executable statement**, before
  heavy imports (mirror docx CLI wiring):
  ```python
  import os, sys
  sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # scripts/
  import _venv_bootstrap; _venv_bootstrap.reexec_into_venv(requires=("pptx",))
  from pptx2md import main          # body lives in the package
  if __name__ == "__main__":
      sys.exit(main())
  ```
- Re-export `main` + the `_AppError` subclasses (mirror `xlsx2md.py` shim).

#### `skills/pptx/scripts/pptx2md/__init__.py`
- Closed public surface: `from .cli import main`; re-export `convert` (stub),
  `_AppError`, `SelfOverwriteRefused`, `OcrEngineUnavailable`, `LanguagePackMissing`,
  `BadInput`, `InternalError`. `__all__` locks it.

#### `skills/pptx/scripts/pptx2md/exceptions.py` — **REAL**
- `_AppError` + the 5 subclasses with `CODE`/`error_type` as in the frozen contract.

#### `skills/pptx/scripts/pptx2md/model.py` — **REAL** (dataclasses only, no logic)
- `@dataclass(frozen=True)` outer records per ARCH §4.1/§4.2; `Block` modeled as a
  small tagged-union (separate dataclasses + a `Block = Union[...]` alias). No
  behaviour — pure data shapes the emitter/extractor agree on.

#### `skills/pptx/scripts/pptx2md/cli.py`
- `build_parser() -> argparse.ArgumentParser` — **REAL**, full surface above;
  `prog="pptx2md.py"`, `description` + `epilog` noting OCR is opt-in & soft-optional.
- `_resolve_paths(args) -> tuple[Path, Path|None]` — **REAL**: INPUT
  `resolve(strict=True)` (missing → `BadInput`/exit 1); OUTPUT `-`/None → stdout
  mode (`None`); same-path guard → `SelfOverwriteRefused` (exit 6); output-parent
  auto-create. (Mirror `xlsx2md/cli.py:_resolve_paths`.)
- `_resolve_media_dir(args, output_path) -> tuple[Path, str]` — **REAL** shell:
  returns `(media_dir, link_base)` — file mode → `<out-stem>.media/` relative to the
  `.md`; stdout mode → `<input-stem>.media/` under CWD with CWD-relative link base
  (MAJOR-4/D-7). (Dir creation deferred to 020-03; here it only computes paths.)
- `main(argv=None) -> int` — **STUB-ish**: `build_parser().parse_args` (so `--help`
  exits 0, bad usage exits 2), `_resolve_paths` inside `try/except _AppError →
  report_error` / `except EncryptedFileError → report_error(code=3)` /
  terminal `except Exception → InternalError(code=1)` (AR-3), then `return
  _STUB_SENTINEL`. Imports `_errors` via the sibling `sys.path` idiom.
- `convert(...)` — **STUB** `raise NotImplementedError` (the programmatic API; wired
  in 020-04).

#### `skills/pptx/scripts/pptx2md/{extract,images,ocr,emit}.py` — **STUBS** (+ one REAL helper)
- `extract.assert_openable(path)` → `raise NotImplementedError` (020-02);
  `extract.build_deck(prs, opts)` → `raise NotImplementedError`.
- **`images.safe_image_meta(shape) -> tuple[bytes, str, str, str] | None`** — **REAL
  here (MAJOR-B, single owner).** Pure ~6-line guard: `blob, sha1 = shape.image.blob,
  shape.image.sha1` (safe), then `try: ext, ct = shape.image.ext, shape.image.content_type;
  return (blob, sha1, ext, ct)` `except (ValueError, UnidentifiedImageError, KeyError):
  return None`. Owned by 020-01 so **both** 020-02 (ImageRef-vs-Placeholder decision)
  and 020-03 (file write) consume the **same** helper — removes the cross-bead
  ownership inversion the plan review flagged. (`UnidentifiedImageError` imported from
  `PIL`; `shape.image` access itself wrapped so `ValueError`/no-blip → `None`.)
- `images.materialise(deck, media_dir, link_base, *, no_images=False)` → `raise
  NotImplementedError` (020-03).
- `ocr.probe(langs)` / `ocr.ocr_asset(asset, langs, timeout)` → `raise
  NotImplementedError` (020-05). **`ocr.py` must NOT import any heavy module at top**
  — `subprocess`/`Pillow`/`tesseract` are only touched inside the functions, and
  `cli` imports `ocr` lazily (only when `--ocr`), so the base CLI never needs tesseract.
- `emit.render_deck(deck, assets, ocr_text, opts)` → `raise NotImplementedError` (020-04).

#### `skills/pptx/scripts/pptx2md/tests/__init__.py` + `test_surface.py`
- Unit cluster (below). `unittest`-style.

#### `skills/pptx/scripts/tests/__init__.py` (MAJOR-A)
- **Empty file** — turns `scripts/tests/` into a Python package so
  `python -m unittest discover -s tests` reliably collects the new E2E module
  (the dir currently holds only the bash `test_e2e.sh`; mirror the xlsx precedent
  `skills/xlsx/scripts/tests/__init__.py`).

#### `skills/pptx/scripts/tests/test_pptx2md_e2e.py`
- E2E smoke (below); later beads (020-02…05) **update** assertions per `tdd-stub-first §2.4`.

### Changes in Existing Files
- **None.** No existing script is modified; no shared file is touched (ARCH §9).

### Component Integration
`pptx2md/` sits alongside `md2pptx.js`, `pptx_clean.py`, etc. in
`skills/pptx/scripts/`; consumes `_errors.py` + `office/_encryption.py` by import only.

## Test Cases

### E2E Tests (smoke — stub phase)
1. **TC-E2E-01 `test_help_lists_surface`** — `python3 pptx2md.py --help` → exit 0;
   stdout contains `INPUT`, `OUTPUT`, `--ocr`, `--ocr-lang`, `--no-images`,
   `--media-dir`, `--no-notes`, `--include-hidden`, `--json-errors`, and `eng+rus`.

### Unit Tests
1. **TC-UNIT-01 `test_module_imports_without_tesseract`** — `import pptx2md`
   succeeds with no OCR engine present (asserts `ocr.py` has no top-level
   subprocess/tesseract call; `cli` does not import `ocr` at module top).
2. **TC-UNIT-02 `test_exit_constants_locked`** — `_EXIT_OK/_EXIT_USAGE/_EXIT_ENCRYPTED/
   _EXIT_SELF_OVERWRITE == 0/2/3/6`; `_DEFAULT_OCR_LANG == "eng+rus"`;
   each `_AppError` subclass `.CODE` matches (SelfOverwriteRefused 6, others 1).
3. **TC-UNIT-03 `test_argparse_defaults`** — `build_parser().parse_args(["a.pptx"])`
   → `OUTPUT == "-"`, `ocr is False`, `ocr_lang == "eng+rus"`, `jobs == 1`,
   `no_images is False`, `include_hidden is False`.
4. **TC-UNIT-04 `test_self_overwrite_guard`** — `main(["x.pptx","x.pptx"])` → 6
   (`SelfOverwriteRefused`), writes nothing; symlink alias of INPUT → 6.
5. **TC-UNIT-05 `test_input_not_found`** — `main(["nope.pptx","out.md"])` → 1 with
   `type=="BadInput"` (parse stderr under `--json-errors`).
6. **TC-UNIT-06 `test_main_returns_sentinel_on_valid_paths`** — with a real fixture
   deck + fresh OUTPUT, `main([...])` returns `-999` (downstream stubbed).
7. **TC-UNIT-07 `test_model_dataclasses_shape`** — construct a `Slide` with a
   `Heading` + `Bullets([BulletItem(level=1,text="x")])` + `Table([["h"],["v"]])`;
   assert frozen outer (`dataclasses.FrozenInstanceError` on attr set) + readable fields.
8. **TC-UNIT-08 `test_stdout_media_link_base`** — `_resolve_media_dir` for stdout
   mode returns a CWD-relative link base; for file mode returns a `.md`-relative base.

### Regression Tests
- `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/pptx` → exit 0.
- Existing pptx suites untouched & green (`scripts/tests`, `scripts/office/tests`).
- `diff -q skills/docx/scripts/_errors.py skills/pptx/scripts/_errors.py` → silent;
  `diff -qr skills/docx/scripts/office skills/pptx/scripts/office` → silent.

## Acceptance Criteria
- [ ] `pptx2md.py` shim + `pptx2md/` package exist; all frozen-contract functions
      present; `build_parser`/`_resolve_paths`/`_resolve_media_dir`/exceptions/model
      **+ `images.safe_image_meta`** (MAJOR-B) **real**; remaining
      extract/images/ocr/emit **stubbed** (`NotImplementedError`).
- [ ] `scripts/tests/__init__.py` exists so `unittest discover -s tests` collects the
      new E2E module (MAJOR-A).
- [ ] `import pptx2md` works with tesseract **absent**; `ocr` not imported until `--ocr` (R-C1d scaffold).
- [ ] Self-overwrite (incl. symlink) → exit 6 ([R-D4a]).
- [ ] Argparse defaults locked ([R-D2]); `--help` exits 0; bad usage exits 2.
- [ ] `--help` smoke E2E + all 8 unit tests pass on stubs.
- [ ] `validate_skill.py skills/pptx` exit 0; cross-skill `diff` gates silent (ARCH §9).

## Stub-First Gate (`tdd-stub-first §1`)
After this task: `import pptx2md` works (engine absent); `--help` exits 0; real
guards return 6/1; `main` on valid paths returns `-999`. The smoke E2E + guard units
ARE the Phase-1 gate — 020-02…05 tighten them.

## Notes
- `_STUB_SENTINEL` is removed in 020-04 when `main` returns real exit codes.
- Do NOT import `pptx` at the top of `cli.py` heavy paths before the bootstrap
  prelude has run (the shim handles the re-exec; `cli` may import `pptx` normally
  since it only runs under the venv interpreter post-bootstrap).
- `requires=("pptx",)` in the bootstrap prelude is the venv-absent diagnostic signal
  (parity with TASK-019 §5.2 derivation rule).

# Task 022-01 [STUB CREATION]: `html2md/` scaffold + two-master replication + frozen surface + RED tests

> **Predecessor:** none (bootstrap task of the chain).
> **RTM:** scaffolds R1–R5; **lands** [R6] replication (copies + thin `__init__`
> + 4→5 helpers) and the [R6] **G-2 smoke-test**; freezes the [R7] CLI surface +
> exit-map + IR dataclasses.
> **ARCH:** §2.1 (FC-5 stub), §3.2 (component table), §4 (IR), §5.1 (CLI),
> §5.3 (envelope), §9 (replication boundary), §11 (bead 022-01).

## Use Case Connection

- UC-1…UC-4 — scaffolded at stub level (`--help` smoke E2E).
- UC-3 self-overwrite path — **real** in this task (exit 6).
- The §9 fork-free guarantee (G-2) — **real** in this task.

## Task Goal

Lay down the **frozen public surface** of `skills/html2md/` and **execute the
two-master replication** so every later bead builds on stable, in-sync code:

1. Scaffold the skill via `init_skill.py` (Proprietary license).
2. **Replicate** the gated clusters (copies, not edits):
   - `web_clean/{archives,reader_mode,preprocess,dom_utils,normalize_css}.py`
     ← `skills/pdf/scripts/html2pdf_lib/` (master=pdf). **Do NOT copy**
     `render.py`, `chrome_engine.py`, or `html2pdf_lib/__init__.py`.
   - `_errors.py`, `_venv_bootstrap.py` ← `skills/docx/scripts/` (master=docx).
3. Author the **html2md-owned** thin `web_clean/__init__.py` (re-exports only
   `preprocess_html`, `reader_mode_html`, `extract_archive`/`list_archive_frames`,
   and the `dom_utils` helpers — NOT gated, NOT a copy of pdf's `__init__`).
4. Freeze the CLI surface (ARCH §5.1), exit-map, `_AppError` hierarchy, and the
   `AcquireResult`/`CleanResult` IR dataclasses **REAL**; FC-1/2/3/4 as **stubs**.
5. Lay RED E2E/unit tests incl. **G-2** (the `__init__.py` trap guard).

**Frozen surface contract (no later bead may rename these):**

- **`html2md/exceptions.py`** — `_AppError(Exception)` base with class attr
  `CODE: int` + instance `error_type: str` + optional `details: dict`.
  Subclasses: `SelfOverwriteRefused(CODE=6)`, `EngineNotInstalled(CODE=3)`,
  `FetchFailed(CODE=10)`, `BadInput(CODE=1)`, `ConvertFailed(CODE=1)`,
  `InternalError(CODE=1)`.
- **CLI constants** (`cli.py`): `_EXIT_OK=0`, `_EXIT_USAGE=2`,
  `_EXIT_ENGINE=3`, `_EXIT_SELF_OVERWRITE=6`, `_EXIT_FETCH=10`,
  `_DEFAULT_ATTACH_DIR="_attachments"`, `_STUB_SENTINEL=-999` (removed in 022-05).
- **Functions:** `cli.build_parser`, `cli._resolve_paths`, `cli.main`,
  `cli.convert`; `acquire.acquire(input, opts) -> AcquireResult`,
  `acquire._dispatch_format(path) -> str`; `clean.clean(acq, *, reader) ->
  CleanResult`; `core_bridge.html_to_markdown(html) -> str` (spawns Node);
  `emit.emit(acq, clean, md_whole, md_reader, opts)`.
- **Argparse surface (ARCH §5.1):** positional `INPUT`, `OUTPUT_DIR`
  (nargs `?`); `--engine {lite,chrome,auto}` (default `auto`),
  `--reader-mode`/`--no-reader` (dest `reader`, default True),
  `--download-images`/`--no-download-images` (dest `download_images`,
  default True), `--attachments-dir` (default `_attachments`),
  `--archive-frame` (default `main`), `--max-bytes` (int), `--max-images`
  (int), `--stdout` (store_true), `--json-errors` (via
  `add_json_errors_argument`).
- **IR dataclasses (`html2md/model.py`)** per ARCH §4: `AcquireResult`
  (`html, base_url, mode, engine, source_meta: dict, images: dict`),
  `CleanResult` (`whole_html: str, reader_html: str|None`),
  `SourceMeta` helper (`url, title, date, author`). Frozen outer dataclasses.

## Changes Description

### New Files

#### `skills/html2md/SKILL.md`, `LICENSE`, `NOTICE`
- Scaffolded by `init_skill.py`; `LICENSE`/`NOTICE` mirror `skills/docx/` (full
  content authored in 022-07; here the files exist so `validate_skill` passes).

#### `skills/html2md/scripts/html2md.py` (thin shim — CLI entrypoint)
- `_venv_bootstrap` prelude as the **first executable statement**:
  ```python
  import os, sys
  sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # scripts/
  import _venv_bootstrap; _venv_bootstrap.reexec_into_venv(requires=("html2md",))
  from html2md import main
  if __name__ == "__main__":
      sys.exit(main())
  ```
- Re-export `main` + the `_AppError` subclasses (mirror `docx`/`pptx2md` shims).

#### `skills/html2md/scripts/html2md/__init__.py`
- Closed surface: `from .cli import main`; re-export `convert` (stub) +
  the `_AppError` subclasses. `__all__` locks it.

#### `skills/html2md/scripts/html2md/exceptions.py` — **REAL**
- `_AppError` + the 6 subclasses with `CODE`/`error_type` per the frozen contract.

#### `skills/html2md/scripts/html2md/model.py` — **REAL** (dataclasses only)
- `@dataclass(frozen=True)` `AcquireResult`, `CleanResult`, `SourceMeta` per
  ARCH §4 (inner dicts/lists mutable). No behaviour.

#### `skills/html2md/scripts/html2md/cli.py`
- `build_parser() -> argparse.ArgumentParser` — **REAL**, full surface above;
  `prog="html2md.py"`, epilog noting Chrome is opt-in/soft-optional.
- `_resolve_paths(args) -> tuple[str, str, Path|None, bool]` (=
  `(input, mode, output_dir|None, stdout_mode)`) — **REAL**: INPUT is a URL
  (scheme `http(s)`) OR a local path (`resolve(strict=True)`, missing →
  `BadInput`/1); OUTPUT_DIR `None`/`--stdout` → stdout mode; same-path/symlink guard →
  `SelfOverwriteRefused` (exit 6, `Path.resolve()`); output-parent auto-create.
- `main(argv=None) -> int` — **STUB-ish**: `build_parser().parse_args`
  (`--help`→0, bad usage→2), `_resolve_paths` inside `try/except _AppError →
  report_error` / terminal `except Exception → InternalError(1)`, then
  `return _STUB_SENTINEL`. Imports `_errors` via the sibling `sys.path` idiom.
- `convert(...)` — **STUB** `raise NotImplementedError` (wired in 022-05).

#### `skills/html2md/scripts/html2md/{acquire,clean,core_bridge,emit}.py` — **STUBS**
- `acquire.acquire(...)`, `acquire._dispatch_format(...)` →
  `NotImplementedError` (022-02/06). **No `httpx`/`trafilatura`/`playwright`
  import at module top** — only inside functions, imported lazily.
- `clean.clean(...)` → `NotImplementedError` (022-04). It will import from
  `web_clean` (the replica).
- `core_bridge.html_to_markdown(...)` → `NotImplementedError` (022-03).
- `emit.emit(...)` → `NotImplementedError` (022-05).

#### `skills/html2md/scripts/web_clean/__init__.py` — **REAL (html2md-owned, NOT gated)**
- Thin re-export of the clean public symbols only:
  ```python
  from .preprocess import preprocess_html
  from .reader_mode import reader_mode_html
  from .archives import extract_archive, list_archive_frames
  __all__ = ["preprocess_html", "reader_mode_html",
             "extract_archive", "list_archive_frames"]
  ```
  **Must NOT** import `render`/`chrome_engine` (they are not copied).

#### `skills/html2md/scripts/html2md/tests/test_surface.py` + `tests/__init__.py`
- Unit cluster (below). `unittest`-style.

#### `skills/html2md/scripts/tests/__init__.py` + `tests/test_e2e.py`
- Empty `__init__.py` (package the dir for `unittest discover`); E2E smoke.

### Replicated Files (copies — ARCH §9, master untouched)

```bash
# pdf-master cleaning cluster (the 5 clean modules ONLY):
for m in archives reader_mode preprocess dom_utils normalize_css; do
  cp skills/pdf/scripts/html2pdf_lib/$m.py skills/html2md/scripts/web_clean/$m.py
done
# docx-master shared helpers (4→5):
cp skills/docx/scripts/_errors.py         skills/html2md/scripts/_errors.py
cp skills/docx/scripts/_venv_bootstrap.py skills/html2md/scripts/_venv_bootstrap.py
find skills -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
> **Do NOT** copy `render.py`, `chrome_engine.py`, `html2pdf_lib/__init__.py`.

### Changes in Existing Files
- **None.** No master is edited (copies only). `docx2md.js` is touched in 022-03,
  not here.

## Test Cases

### E2E Tests (smoke — stub phase)
1. **TC-E2E-01 `test_help_lists_surface`** — `python3 html2md.py --help` → exit 0;
   stdout contains `INPUT`, `OUTPUT_DIR`, `--engine`, `--reader-mode`,
   `--no-reader`, `--download-images`, `--no-download-images`,
   `--attachments-dir`, `--archive-frame`, `--max-bytes`, `--stdout`,
   `--json-errors`, and `_attachments`.

### Unit Tests
1. **TC-UNIT-01 `test_import_no_browser_no_render`** — `import html2md`
   succeeds with neither `playwright` nor `weasyprint` installed (asserts
   `acquire.py` has no top-level `httpx`/`trafilatura`/`playwright` import).
2. **TC-UNIT-02 (G-2) `test_web_clean_no_weasyprint_no_playwright`** — after
   `import web_clean.archives` **and** `import web_clean.reader_mode` (the real
   leaf entrypoints, which pull `preprocess`→`dom_utils`+`normalize_css`),
   assert `"weasyprint" not in sys.modules and "playwright" not in sys.modules`.
   *(the `__init__.py` trap guard — ARCH §9 G-2.)*
3. **TC-UNIT-03 `test_exit_constants_locked`** — `_EXIT_OK/_EXIT_USAGE/
   _EXIT_ENGINE/_EXIT_SELF_OVERWRITE/_EXIT_FETCH == 0/2/3/6/10`;
   `_DEFAULT_ATTACH_DIR == "_attachments"`; each `_AppError.CODE` matches
   (SelfOverwriteRefused 6, EngineNotInstalled 3, FetchFailed 10, others 1).
4. **TC-UNIT-04 `test_argparse_defaults`** — `build_parser().parse_args(["x.html"])`
   → `engine=="auto"`, `reader is True`, `download_images is True`,
   `attachments_dir=="_attachments"`, `archive_frame=="main"`, `stdout is False`.
5. **TC-UNIT-05 `test_self_overwrite_guard`** — output dir == INPUT's dir with a
   colliding name → exit 6; symlink alias → exit 6; nothing written.
6. **TC-UNIT-06 `test_input_not_found`** — `main(["nope.html","out/"])` → 1,
   `type=="BadInput"` (parse stderr under `--json-errors`).
7. **TC-UNIT-07 `test_url_vs_path_dispatch`** — `_resolve_paths` treats
   `https://x/y` as URL mode (no `strict` stat) and `./a.html` as file mode.
8. **TC-UNIT-08 `test_ir_dataclasses_frozen`** — construct `AcquireResult(...)`
   + `CleanResult(whole_html="x", reader_html=None)`; assert
   `dataclasses.FrozenInstanceError` on attr set; readable fields.
9. **TC-UNIT-09 `test_main_returns_sentinel_on_valid_paths`** — valid local
   `.html` + fresh OUTPUT_DIR → `main` returns `-999` (downstream stubbed).

### Regression Tests
- `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/html2md` → exit 0.
- **G-1 (early)**: `diff -q skills/docx/scripts/_errors.py
  skills/html2md/scripts/_errors.py` silent; same for `_venv_bootstrap.py`;
  `for m in archives reader_mode preprocess dom_utils normalize_css; do diff -q
  skills/pdf/scripts/html2pdf_lib/$m.py skills/html2md/scripts/web_clean/$m.py;
  done` all silent (after `__pycache__` clean).

## Acceptance Criteria
- [ ] `html2md.py` shim + `html2md/` package exist; frozen surface REAL
      (parser/exceptions/model/`_resolve_paths`); FC-1/2/3/4 **stubbed**.
- [ ] `web_clean/` holds the **5** pdf modules byte-identical + an html2md-owned
      thin `__init__.py`; `render.py`/`chrome_engine.py`/pkg-`__init__` **absent**.
- [ ] `_errors.py` + `_venv_bootstrap.py` byte-identical to docx (G-1 silent).
- [ ] **G-2:** importing `web_clean.archives` + `web_clean.reader_mode` leaves
      `weasyprint`/`playwright` out of `sys.modules`.
- [ ] `import html2md` works with no browser/render deps; `acquire` imports
      `httpx`/`trafilatura`/`playwright` only inside functions.
- [ ] Self-overwrite (incl. symlink) → exit 6; `--help`→0; bad usage→2.
- [ ] `--help` smoke E2E + all 9 unit tests pass on stubs.
- [ ] `validate_skill.py skills/html2md` exit 0.

## Stub-First Gate (`tdd-stub-first §1`)
After this bead: `import html2md` works; `web_clean` imports clean (G-2 green);
`--help`→0; guards return 6/1; `main` on valid paths returns `-999`. The smoke
E2E + guard units ARE the Phase-1 gate — 022-02…06 tighten them.

## Notes
- `_STUB_SENTINEL` is removed in 022-05 when `main`/`convert` return real codes.
- `requires=("html2md",)` in the bootstrap prelude is the venv-absent diagnostic.
- The pdf cleaning modules are carried **whole** (incl. inert weasyprint-specific
  regex) — D-4; trimming would break G-1. `normalize_css.py` is a **hard import
  dep** of `preprocess.py`, not optional ballast.

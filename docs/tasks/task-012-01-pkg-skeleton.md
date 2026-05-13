# Task 012-01 [STUB CREATION]: Package skeleton, shim, exceptions catalogue, smoke E2E

> **Predecessor:** none (this is the bootstrap task of the chain).
> **RTM:** [R1], [R2] (scaffolded), [R3]; exception catalogue
> declared for [R10], [R10a] (flag declaration), [R13], [R14h],
> [R20a] (flag declaration), [R21], [R23], [R23f], [R24].
> **UCs scaffolded:** UC-01..UC-12 (all stubs returning sentinel).

## Use Case Connection

- UC-01..UC-12 (all scaffolded as stubs returning sentinel `-999`).
- UC-08 / UC-09 envelope plumbing skeleton (exception classes
  declared with `CODE` attribute — raise sites land in 012-02).

## Task Goal

Lay down the **frozen public surface** for xlsx-9: one shim
(`xlsx2md.py` ≤ 60 LOC, body verbatim from ARCH §3.2 C1) + one
in-skill package (`xlsx2md/` with 9 module files per ARCH §3.2 C2)
+ test scaffolding with ONE smoke E2E that asserts hardcoded
sentinel behaviour (Red → Green on stubs per `tdd-stub-first §1`).

**Frozen surface contract (no later task may change these names):**

- Public symbols in `xlsx2md/__init__.py.__all__`:
  `main`, `convert_xlsx_to_md`, `_AppError`, `SelfOverwriteRefused`,
  `GfmMergesRequirePolicy`, `IncludeFormulasRequiresHTML`,
  `PostValidateFailed`, `InconsistentHeaderDepth`,
  `HeaderRowsConflict`, `InternalError`.
- Exception `CODE` attributes per ARCH §2.1 F8:
  `SelfOverwriteRefused=6`, `GfmMergesRequirePolicy=2`,
  `IncludeFormulasRequiresHTML=2`, `PostValidateFailed=7`,
  `InconsistentHeaderDepth=2`, `HeaderRowsConflict=2`,
  `InternalError=7`.
- Module file names: `__init__.py`, `cli.py`, `dispatch.py`,
  `emit_hybrid.py`, `emit_gfm.py`, `emit_html.py`, `inline.py`,
  `headers.py`, `exceptions.py`.
- Argparse flag surface (per ARCH §5.1) DECLARED in `cli.py`
  (returns sentinel in stub phase; defaults wired so 012-08
  no-flag shape pin regression can succeed once logic lands).

## Changes Description

### New Files

#### `skills/xlsx/scripts/xlsx2md.py` (≤ 60 LOC shim)

Body verbatim from ARCH §3.2 C1 — shebang, module docstring,
`sys.path.insert(0, str(Path(__file__).resolve().parent))`, import
from `xlsx2md` (all 10 public symbols), `if __name__ == "__main__":
sys.exit(main())`.

Stub phase note: `main()` returns sentinel `-999` until 012-02 wires
argparse + dispatch. The shim itself is the final form — no later
task edits the shim.

#### `skills/xlsx/scripts/xlsx2md/__init__.py` (F9 — public surface)

- Module docstring covering TASK §1.4 honest-scope items
  (a)..(m) + R3-H1 as bullet-list comments (full text per
  ARCH §2.1 F9 + ARCH §10). Items (k), (l), (m) call out
  inheritance from xlsx-8a-09 / xlsx-8a-03 / xlsx-8a-11.
- `from .cli import main` re-export.
- `from .exceptions import _AppError, SelfOverwriteRefused,
  GfmMergesRequirePolicy, IncludeFormulasRequiresHTML,
  PostValidateFailed, InconsistentHeaderDepth, HeaderRowsConflict,
  InternalError` re-export.
- `convert_xlsx_to_md(input_path, output_path=None, **kwargs)` —
  STUB returning sentinel `-999`. Real wiring lands in 012-02
  (`--flag=value` atomic-token form via `_build_argv` helper;
  signature already declared per ARCH §5.2 including `memory_mode`
  and `hyperlink_scheme_allowlist` kwargs).
- `__all__` literal with exactly the 10 names listed above.

#### `skills/xlsx/scripts/xlsx2md/exceptions.py` (F8 — leaf module)

```python
"""Shim-level exception catalogue. CODE = exit code consumed by _errors.report_error."""
from __future__ import annotations


class _AppError(RuntimeError):
    CODE: int = 1


class SelfOverwriteRefused(_AppError):
    CODE = 6  # Cross-7 H1: INPUT and OUTPUT resolve to same path.


class GfmMergesRequirePolicy(_AppError):
    CODE = 2  # D14: --format gfm + merges + default policy.


class IncludeFormulasRequiresHTML(_AppError):
    CODE = 2  # M7 lock: --format gfm + --include-formulas.


class PostValidateFailed(_AppError):
    CODE = 7  # Env-flag post-validate gate (parity with xlsx-8 PostValidate).


class InconsistentHeaderDepth(_AppError):
    CODE = 2  # D-A11 defensive: multi-row reconstruction non-uniform.


class HeaderRowsConflict(_AppError):
    CODE = 2  # R14h: --header-rows N (int) + --tables != whole.


class InternalError(_AppError):
    CODE = 7  # R23f: terminal catch-all; raw message redacted.
```

#### `skills/xlsx/scripts/xlsx2md/cli.py` (F1 — argparse + main, STUB)

- `build_parser() -> argparse.ArgumentParser` — full flag surface
  per ARCH §5.1 (all 14 flags declared with correct defaults,
  types, and `metavar`). Help text is real and references
  `--help` epilogue notes for `--memory-mode` and
  `--hyperlink-scheme-allowlist` per TASK R20a(c) + R10a(d).
  Used by 012-02 onwards.
- `main(argv: list[str] | None = None) -> int` — STUB returning
  sentinel `-999`. Logic wired in 012-02 + 012-03 + 012-06.
- `_validate_flag_combo(args) -> None` — STUB (`pass`). Logic in
  012-02.
- `_resolve_paths(args) -> tuple[Path, Path | None]` — STUB
  (raises `NotImplementedError`). Logic in 012-02.

#### `skills/xlsx/scripts/xlsx2md/dispatch.py` (F2 — STUB)

- `iter_table_payloads(reader, args)` — STUB yielding nothing
  (empty generator).
- `_detect_mode_for_args(args)` — STUB returning `("auto", lambda
  r: True)`.
- `_resolve_read_only_mode(args)` — STUB returning `None`.
- `_gap_fallback_if_empty(...)` — STUB returning input unchanged.

Logic lands in 012-03.

#### `skills/xlsx/scripts/xlsx2md/emit_hybrid.py` (F3 — STUB)

- `select_format(table_data, args)` — STUB returning `"gfm"`.
- `emit_workbook_md(reader, args, out)` — STUB returning `0`.
- Predicates `_has_body_merges`, `_is_multi_row_header`,
  `_has_formula_cells`, `_is_synthetic_header` — STUBs returning
  `False`.

Logic in 012-06.

#### `skills/xlsx/scripts/xlsx2md/emit_gfm.py` (F4 — STUB)

- `emit_gfm_table(...)` — STUB (writes nothing).
- `_format_cell_gfm(v)` — STUB returning `str(v) if v is not None
  else ""`.
- `_emit_header_row_gfm(...)` — STUB.
- `_apply_gfm_merge_policy(...)` — STUB returning input unchanged.

Logic in 012-04.

#### `skills/xlsx/scripts/xlsx2md/emit_html.py` (F5 — STUB)

- `emit_html_table(...)` — STUB (writes nothing).
- `_emit_thead(...)`, `_emit_tbody(...)`, `_format_cell_html(...)`
  — STUBs.

Logic in 012-05.

#### `skills/xlsx/scripts/xlsx2md/inline.py` (F6 — STUB)

- `render_cell_value(...)` — STUB.
- `_escape_pipe_gfm(t)` — STUB returning `t`.
- `_escape_html_entities(t)` — STUB returning `t`.
- `_newlines_to_br(t)` — STUB returning `t`.
- `_render_hyperlink(...)` — STUB returning `str(value)`.

Logic in 012-04 (consumed by both 012-04 and 012-05).

#### `skills/xlsx/scripts/xlsx2md/headers.py` (F7 — STUB)

- `split_headers_to_rows(headers)` — STUB returning `[headers]`.
- `compute_colspan_spans(rows)` — STUB returning `[[1] * len(r)
  for r in rows]`.
- `validate_header_depth_uniformity(headers)` — STUB returning
  `1`.

Logic in 012-05.

#### `skills/xlsx/scripts/xlsx2md/tests/__init__.py`

Empty file.

#### `skills/xlsx/scripts/xlsx2md/tests/conftest.py`

Empty file (kept for future fixtures).

#### `skills/xlsx/scripts/xlsx2md/tests/test_smoke_stub.py`

Smoke E2E asserting:
1. `import xlsx2md` succeeds (package importable).
2. `set(xlsx2md.__all__) == { 10 frozen names }`.
3. Each exception class has the locked `CODE` attribute (per
   ARCH §2.1 F8).
4. `xlsx2md.convert_xlsx_to_md("ignored")` returns `-999`
   (sentinel).
5. `xlsx2md.main([])` returns `-999` (sentinel).
6. `python3 xlsx2md.py --help` (via subprocess) — exit 0 AND
   stdout contains all required flag names: `--sheet`,
   `--include-hidden`, `--format`, `--header-rows`,
   `--memory-mode`, `--hyperlink-scheme-allowlist`,
   `--no-table-autodetect`, `--no-split`, `--gap-rows`,
   `--gap-cols`, `--gfm-merge-policy`, `--datetime-format`,
   `--include-formulas`, `--json-errors`. This asserts the
   argparse surface is real in stub phase (defaults locked even
   if logic returns sentinel).

### Changes in Existing Files

None.

### Component Integration

- New component on top of xlsx-10.A. No existing files modified.
- Shim `xlsx2md.py` lives alongside `xlsx2csv.py` / `xlsx2json.py`
  / `md_tables2xlsx.py` in `skills/xlsx/scripts/`.
- Package `xlsx2md/` lives alongside `xlsx2csv2json/`,
  `md_tables2xlsx/`, `xlsx_read/`.

## Test Cases

### E2E Tests

This task binds NO test slugs from TASK §5.1 to real assertions
(all stubs). The smoke E2E is the Stub-First gate per
`tdd-stub-first §1` — later tasks UPDATE this file to real
assertions per `tdd-stub-first §2.4`.

### Unit Tests

1. **TC-UNIT-01 `test_package_importable`** — `import xlsx2md`
   succeeds.
2. **TC-UNIT-02 `test_all_public_symbols_present`** —
   `set(xlsx2md.__all__) == {"main", "convert_xlsx_to_md",
   "_AppError", "SelfOverwriteRefused", "GfmMergesRequirePolicy",
   "IncludeFormulasRequiresHTML", "PostValidateFailed",
   "InconsistentHeaderDepth", "HeaderRowsConflict",
   "InternalError"}`.
3. **TC-UNIT-03 `test_exception_codes_locked`** — each exception
   class's `CODE` attr matches the table above.
4. **TC-UNIT-04 `test_convert_helper_returns_sentinel`** —
   `convert_xlsx_to_md("ignored")` returns `-999`.
5. **TC-UNIT-05 `test_main_returns_sentinel`** — `main([])`
   returns `-999`.
6. **TC-UNIT-06 `test_shim_help_lists_all_flags`** — subprocess
   `python3 xlsx2md.py --help` exit 0; stdout contains the 14
   required flag names listed above.
7. **TC-UNIT-07 `test_shim_loc_le_60`** — count non-blank
   non-comment lines in `xlsx2md.py`; assert ≤ 60 (R1.d).

### Regression Tests

- Run `python3 -m unittest discover -s skills/xlsx/scripts/xlsx2md/tests`
  — all green.
- Run existing xlsx test suites (xlsx2csv2json, json2xlsx,
  md_tables2xlsx, xlsx_check_rules, xlsx_comment, xlsx_read) —
  no regression (this task does not modify existing code).
- `ruff check skills/xlsx/scripts/` green (banned-api from
  xlsx-10.A respected; new package imports nothing from
  `xlsx_read._*`).

## Acceptance Criteria

- [ ] `skills/xlsx/scripts/xlsx2md.py` exists and is ≤ 60 LOC
      (verified by TC-UNIT-07).
- [ ] `skills/xlsx/scripts/xlsx2md/` package exists with 9
      module files: `__init__.py`, `cli.py`, `dispatch.py`,
      `emit_hybrid.py`, `emit_gfm.py`, `emit_html.py`,
      `inline.py`, `headers.py`, `exceptions.py`.
- [ ] `xlsx2md/__init__.py` declares `__all__` with exactly the
      10 frozen names.
- [ ] All 7 exception classes declared with `CODE` attribute per
      ARCH §2.1 F8.
- [ ] All 7 unit tests in `test_smoke_stub.py` pass.
- [ ] `python3 -c "from xlsx2md import convert_xlsx_to_md, main,
      _AppError, SelfOverwriteRefused, GfmMergesRequirePolicy,
      IncludeFormulasRequiresHTML, PostValidateFailed,
      InconsistentHeaderDepth, HeaderRowsConflict, InternalError"`
      succeeds (imports the entire frozen surface).
- [ ] `python3 xlsx2md.py --help` exit 0 + stdout lists all 14
      argparse flags from ARCH §5.1.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] 5-line cross-skill `diff -q` silent gate (CLAUDE.md §2;
      ARCH §9.1):
      ```bash
      diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
      diff -q  skills/docx/scripts/_soffice.py      skills/xlsx/scripts/_soffice.py
      diff -q  skills/docx/scripts/_errors.py       skills/xlsx/scripts/_errors.py
      diff -q  skills/docx/scripts/preview.py       skills/xlsx/scripts/preview.py
      diff -q  skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
      ```
      All five must produce no output.
- [ ] No file under `skills/xlsx/scripts/xlsx_read/` modified.
- [ ] No file under `skills/xlsx/scripts/office/` modified.
- [ ] No file `skills/xlsx/scripts/requirements.txt` /
      `pyproject.toml` / `install.sh` modified.
- [ ] No file under `skills/xlsx/scripts/xlsx2csv2json/`,
      `md_tables2xlsx/`, `json2xlsx/` modified.

## Stub-First Gate (per `tdd-stub-first §1.4`)

The following imports MUST work after this task:

```python
from xlsx2md import (
    main,
    convert_xlsx_to_md,
    _AppError,
    SelfOverwriteRefused,
    GfmMergesRequirePolicy,
    IncludeFormulasRequiresHTML,
    PostValidateFailed,
    InconsistentHeaderDepth,
    HeaderRowsConflict,
    InternalError,
)
```

The following sentinel smoke tests MUST pass on stubs:

- `convert_xlsx_to_md("ignored") == -999`
- `main([]) == -999`
- `_AppError.CODE == 1`; subclass `CODE` per table.
- `python3 xlsx2md.py --help` → exit 0 (argparse builds even when
  `main()` returns sentinel — argparse runs in `main()` after the
  sentinel check OR argparse runs in `build_parser()` which is
  called before sentinel return per ARCH §2.1 F1).

## Notes

- **Strict-mode:** YES — every later task assumes the surface
  frozen here.
- The smoke test in `test_smoke_stub.py` IS the Phase-1 E2E per
  `tdd-stub-first §1`. Later tasks update / replace tests in this
  file as logic lands (per `tdd-stub-first §2.4`).
- The `sys.path.insert(0, parent)` boilerplate in the shim is
  REQUIRED — without it the package cannot resolve `_errors`
  (4-skill replicated file at `scripts/_errors.py`). Verified
  pattern from `json2xlsx.py` and the xlsx-8 shims.
- `xlsx2md.py` body is **locked verbatim** from ARCH §3.2 C1; the
  developer must NOT extend the shim — every logic addition goes
  into `xlsx2md/`.
- Argparse defaults declared here are the "no flags omitted" shape
  pin for R6.h (regression in 012-08 against a synthetic fixture).
  Defaults to lock: `--format=hybrid`, `--header-rows=auto`,
  `--memory-mode=auto`, `--hyperlink-scheme-allowlist=http,https,mailto`,
  `--gap-rows=2`, `--gap-cols=1`,
  `--gfm-merge-policy=fail`, `--datetime-format=ISO`,
  `--include-formulas` off, `--sheet=all`, `--no-table-autodetect`
  off, `--no-split` off, `--include-hidden` off, `--json-errors`
  off.
- Module docstring for `inline.py` MUST include §1.4 (l) honest-
  scope note about default allowlist `{http, https, mailto}` and
  the `'*'` / `""` special cases.
- Module docstring for `__init__.py` MUST include §1.4 (m)
  hyperlink-memory-cost note + `--memory-mode=streaming` escape
  hatch.

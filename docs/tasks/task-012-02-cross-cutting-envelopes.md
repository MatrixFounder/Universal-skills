# Task 012-02 [LOGIC IMPLEMENTATION]: Cross-cutting envelopes, `_validate_flag_combo`, `_resolve_paths`, terminal `InternalError`

> **Predecessor:** 012-01.
> **RTM:** [R4], [R6] (defaults wired in 012-01; this task wires
> the no-flag E2E path through `main()`), [R13], [R14h], [R21],
> [R22], [R23], [R23f], [R24]; declares the `convert_xlsx_to_md`
> programmatic helper (`--flag=value` atomic-token form per
> D-A3 / D7).
> **UCs:** UC-07 Scenario A (M7 lock), UC-08 (same-path),
> UC-09 (encrypted), UC-10 (macro).

## Use Case Connection

- UC-07 Scenario A: `--format gfm` + `--include-formulas` →
  exit 2 `IncludeFormulasRequiresHTML` before file I/O.
- UC-08: same-path → exit 6 `SelfOverwriteRefused` (cross-7 H1).
- UC-09: encrypted → exit 3 `EncryptedWorkbookError` envelope
  with basename-only `details.filename` (cross-3).
- UC-10: `.xlsm` macro → exit 0 + stderr warning (cross-4).
- Generic: `--json-errors` envelope shape v=1 across all fail
  paths (cross-5).
- Generic: any unhandled exception → code 7 `InternalError`
  redacted envelope (R23f, inherited from xlsx-8 §14.4 H3).

## Task Goal

Make every CLI exit path go through the cross-5 envelope helper
`_errors.report_error`. Implement the pre-flight validation gate
(`_validate_flag_combo`), the same-path canonical-resolve guard
(`_resolve_paths`), the cross-3 / cross-4 / cross-7 catch sites,
and the terminal `try/except Exception` catch-all that wraps
`main()` to render any unhandled exception as a redacted
`InternalError` code 7 envelope. Wire the
`convert_xlsx_to_md(...)` programmatic helper in `__init__.py`
with the `--flag=value` atomic-token form (D-A3 / D7 pattern,
mirrors `convert_md_tables_to_xlsx`).

The library-glue (`dispatch.iter_table_payloads`) and the emit
modules remain STUBs after this task — they land in 012-03,
012-04, 012-05, 012-06. But by the end of this task, every
cross-cutting failure path (encrypted, macro, same-path, M7
combo, `HeaderRowsConflict` combo, generic catch-all) must
deliver the correct envelope and exit code via mocked / minimal
fixtures.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2md/cli.py`

**Function `_validate_flag_combo(args) -> None`:**

- Replace stub. Run BEFORE any file I/O (called first in
  `main()`).
- **M7 lock — `IncludeFormulasRequiresHTML` (CODE=2):** if
  `args.format == "gfm" and args.include_formulas`, raise
  `IncludeFormulasRequiresHTML`.
- **R14h — `HeaderRowsConflict` (CODE=2):** if
  `args.header_rows` is an integer (not `"auto"`, not `"smart"`)
  AND `args.no_split is False` AND `args.no_table_autodetect is
  False` (i.e. multi-table mode active), raise
  `HeaderRowsConflict` with `details = {"n_requested": N,
  "table_count": "unknown_pre_open", "suggestion":
  "use --header-rows auto or --header-rows smart for
  multi-table workbooks"}`. Note: the `table_count` value is the
  string literal `"unknown_pre_open"` at validate-time because
  the workbook hasn't been opened yet; semantics of the lock
  match TASK R14.h (gate fires before file I/O).
- **R15 — `GfmMergesRequirePolicy` (CODE=2) gate D14:** if
  `args.format == "gfm" and args.gfm_merge_policy == "fail"`,
  do NOT raise here (must wait until a body merge is actually
  observed in emit-side). The raise-site for this lock lives in
  012-06 (`emit_hybrid.emit_workbook_md`). This task only
  documents that the gate is downstream; `_validate_flag_combo`
  does not validate it.

**Function `_resolve_paths(args) -> tuple[Path, Path | None]`:**

- Replace stub. Run AFTER `_validate_flag_combo` but BEFORE
  workbook open.
- Resolve `INPUT`: `input_path = Path(args.input).resolve(strict=True)`.
  If file not found, let `FileNotFoundError` propagate to the
  terminal handler (which produces `InternalError` code 7 — the
  outer Python `argparse` already prints a usage error for
  obviously-missing positionals via `type=str` + manual check; we
  rely on resolve-strict to fail-loud).
- Resolve `OUTPUT`:
  - If `args.output is None` or `args.output == "-"`:
    `output_path = None` (stdout mode).
  - Else: `output_path = Path(args.output).resolve()`.
    Note: NOT strict, because output file might not yet exist.
- **Cross-7 H1 same-path guard (R24, D8):** if
  `output_path is not None and output_path == input_path`,
  raise `SelfOverwriteRefused` with `details = {"path":
  input_path.name}` (basename only — no full-path leak).
- **Output-parent auto-create (R4d):** if `output_path is not
  None` and `output_path.parent` does not exist, create with
  `output_path.parent.mkdir(parents=True, exist_ok=True)`.
- Return `(input_path, output_path)`.

**Function `main(argv: list[str] | None = None) -> int`:**

- Replace sentinel return with the actual orchestration body.
  Skeleton:

  ```text
  parser = build_parser()
  args = parser.parse_args(argv)
  json_mode = bool(args.json_errors)
  try:
      _validate_flag_combo(args)
      input_path, output_path = _resolve_paths(args)
      # Workbook open + emit dispatch — stubs in this task; wired
      # in 012-03 (dispatch) + 012-06 (emit_workbook_md).
      from .dispatch import iter_table_payloads  # noqa: F401
      from .emit_hybrid import emit_workbook_md
      with warnings.catch_warnings(record=True) as captured:
          warnings.simplefilter("always")
          from xlsx_read import open_workbook, MacroEnabledWarning
          with open_workbook(input_path) as reader:
              exit_code = emit_workbook_md(reader, args, _resolve_output_stream(output_path))
          _emit_warnings_to_stderr(captured)
      return exit_code
  except _AppError as e:
      return _errors.report_error(
          str(e) or type(e).__name__,
          code=e.CODE,
          error_type=type(e).__name__,
          details=_extract_details(e),
          json_mode=json_mode,
          stream=sys.stderr,
      )
  except EncryptedWorkbookError as e:
      return _errors.report_error(
          f"Workbook is encrypted: {input_path.name}",
          code=3,
          error_type="EncryptedWorkbookError",
          details={"filename": input_path.name},
          json_mode=json_mode,
          stream=sys.stderr,
      )
  except SheetNotFound as e:
      return _errors.report_error(
          str(e),
          code=2,
          error_type="SheetNotFound",
          details={"sheet": getattr(e, "sheet", None) or str(e)},
          json_mode=json_mode,
          stream=sys.stderr,
      )
  except Exception as exc:  # noqa: BLE001 — terminal catch-all (R23f)
      # Raw message dropped to prevent absolute-path leaks from
      # openpyxl / xlsx_read internals. For local debugging,
      # re-run without --json-errors to see Python traceback.
      return _errors.report_error(
          f"Internal error: {type(exc).__name__}",
          code=InternalError.CODE,
          error_type="InternalError",
          details={},
          json_mode=json_mode,
          stream=sys.stderr,
      )
  ```

  - `_resolve_output_stream(output_path)` is a small helper that
    returns `sys.stdout` when `output_path is None`, else
    `open(output_path, "w", encoding="utf-8")`. The caller is
    responsible for closing.
  - `_emit_warnings_to_stderr(captured)` emits each captured
    warning to `sys.stderr` (one line per warning, prefixed with
    `"warning: "`); `MacroEnabledWarning` is handled here, NOT
    in a separate `except` branch.
  - `_extract_details(e)` reads `e.args[0]` if it is a dict, else
    returns `{}`. Used for `SelfOverwriteRefused` etc., which
    pass a `dict` as their constructor argument.

**Function `build_parser()`:**

- No changes (already declared in 012-01). This task adds the
  `add_json_errors_argument(parser)` call (delegates to the
  cross-5 helper from `_errors`).

#### File: `skills/xlsx/scripts/xlsx2md/__init__.py`

**Function `convert_xlsx_to_md(input_path, output_path=None,
**kwargs) -> int`:**

- Replace stub. Build argv with `--flag=value` atomic-token form
  (D-A3 / D7), then route through `main(argv)`.
- Skeleton:

  ```text
  argv = [str(input_path)]
  if output_path is not None:
      argv.append(str(output_path))
  for key, value in kwargs.items():
      flag = "--" + key.replace("_", "-")
      if isinstance(value, bool):
          if value:
              argv.append(flag)  # boolean True appends flag only
          # boolean False omits the flag entirely
      elif value is None:
          continue  # None skips the flag
      else:
          argv.append(f"{flag}={value}")  # --flag=value atomic-token
  return main(argv)
  ```

- Honest-scope docstring listing the kwargs (per ARCH §5.2):
  `sheet`, `include_hidden`, `format`, `header_rows`,
  `no_table_autodetect`, `no_split`, `gap_rows`, `gap_cols`,
  `gfm_merge_policy`, `datetime_format`, `include_formulas`,
  `memory_mode`, `hyperlink_scheme_allowlist`, `json_errors`.

### New Files

#### `skills/xlsx/scripts/xlsx2md/tests/test_cli_envelopes.py`

Unit tests for `cli._validate_flag_combo`, `cli._resolve_paths`,
and the cross-cutting catch sites in `main()`. Uses
`unittest.mock.patch` to monkey-patch
`xlsx_read.open_workbook` to raise the relevant typed
exceptions.

#### `skills/xlsx/scripts/xlsx2md/tests/test_public_api.py`

Unit tests for `convert_xlsx_to_md` (`--flag=value` atomic-token
form, boolean True → flag-only, None → skip).

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/encrypted.xlsx`

Reuse the existing encrypted fixture from
`xlsx2csv2json/tests/fixtures/` (copy or symlink — copying is
safer to keep xlsx-9 tests independent of xlsx-8 fixture moves).
Password-protected workbook; opening it must raise
`EncryptedWorkbookError`.

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/macro_simple.xlsm`

Hand-built `.xlsm` with a trivial macro module (no actual VBA
required — just the `.xlsm` extension + content type =
`spreadsheetml.sheet.macroEnabled.main+xml` so
`xlsx_read.open_workbook` raises `MacroEnabledWarning`).

#### `skills/xlsx/scripts/xlsx2md/tests/fixtures/single_cell.xlsx`

Minimal 1×1 workbook with cell `A1 = "hello"`. Used by
`test_same_path_*` tests (symlink point), `test_no_flag_*`
shape baseline, and downstream tasks.

### Component Integration

- `_errors.report_error` is the only exit-code path. Verified
  by greppign for `sys.exit(` outside `xlsx2md.py` shim's
  `if __name__ == "__main__": sys.exit(main())` line.
- `add_json_errors_argument(parser)` is the only way to add
  `--json-errors`; do not declare it manually in `build_parser`
  (avoids drift).

## Test Cases

### E2E Tests (binding TASK §5.1 slugs)

| # | Slug | Fixture | Assertion | Expected exit |
| --- | --- | --- | --- | --- |
| 2 | `T-stdout-when-output-omitted` | `single_cell.xlsx` | `python3 xlsx2md.py single_cell.xlsx` (no OUTPUT) → stdout receives `"## Sheet1\n\| A \|\n\|---\|\n\| hello \|\n"` (or current emit; final shape locked in 012-08 R6h regression). For 012-02 the exit code is the relevant assertion since emit is still STUB; updated to full content by 012-04 → 012-06 → 012-08. | 0 |
| 14 | `T-include-formulas-gfm-exits2` | any `.xlsx` (use `single_cell.xlsx`) | `python3 xlsx2md.py single_cell.xlsx --format=gfm --include-formulas` → no workbook open occurs (monkey-patch `open_workbook` to raise if called; assert it WASN'T called). Envelope `type == "IncludeFormulasRequiresHTML"`. | 2 |
| 16 | `T-same-path-via-symlink-exit6` | `single_cell.xlsx` + symlink `out.md → single_cell.xlsx` | `python3 xlsx2md.py single_cell.xlsx out.md` → assert exit before any write to `out.md`; envelope `type == "SelfOverwriteRefused"`. | 6 |
| 17 | `T-encrypted-workbook-exit3` | `encrypted.xlsx` | `python3 xlsx2md.py encrypted.xlsx` → envelope `{"v":1, "error":..., "code":3, "type":"EncryptedWorkbookError", "details":{"filename":"encrypted.xlsx"}}`. Assert `"/" not in details.filename`. | 3 |
| 18 | `T-xlsm-macro-warning` | `macro_simple.xlsm` | `python3 xlsx2md.py macro_simple.xlsm /tmp/out.md` → exit 0 + stderr contains `"macro-enabled"` (case-insensitive) + `/tmp/out.md` exists. | 0 |
| 22 | `T-json-errors-envelope-shape-v1` | `encrypted.xlsx` | `python3 xlsx2md.py encrypted.xlsx --json-errors` → stderr / stdout contains valid JSON parseable by `json.loads`; result has all five keys `v, error, code, type, details`; `v == 1`; `code != 0`. (Generic shape lock — verified again in 012-08 with multiple failure types.) | 3 |
| 27 | `T-header-rows-int-with-multi-table-exits-2-conflict` | any `.xlsx` (single_cell.xlsx) | `python3 xlsx2md.py single_cell.xlsx --header-rows=2` → assert no workbook open occurs (gate fires before file I/O); envelope `type == "HeaderRowsConflict"`. | 2 |
| 34 | `T-internal-error-envelope-redacts-raw-message` | `single_cell.xlsx` + monkey-patch | Monkey-patch `xlsx_read.open_workbook` to raise `PermissionError("/Users/secret/file.xlsx")`; run with `--json-errors`; assert envelope JSON `error == "Internal error: PermissionError"` AND `"/Users/secret"` NOT in `json.dumps(envelope)`. | 7 |

### Unit Tests

In `test_cli_envelopes.py` (≥ 12 tests; supplements TASK §5.2's
`cli.py` min count of 8):

1. **TC-UNIT-01** `test_validate_flag_combo_m7_gfm_plus_formulas_raises`.
2. **TC-UNIT-02** `test_validate_flag_combo_html_plus_formulas_ok`.
3. **TC-UNIT-03** `test_validate_flag_combo_hybrid_plus_formulas_ok`.
4. **TC-UNIT-04** `test_validate_flag_combo_header_rows_int_with_multi_table_raises`.
5. **TC-UNIT-05** `test_validate_flag_combo_header_rows_int_with_no_split_ok`.
6. **TC-UNIT-06** `test_validate_flag_combo_header_rows_auto_with_multi_table_ok`.
7. **TC-UNIT-07** `test_validate_flag_combo_header_rows_smart_with_multi_table_ok`.
8. **TC-UNIT-08** `test_resolve_paths_same_path_exits_6` (via symlink fixture).
9. **TC-UNIT-09** `test_resolve_paths_different_extension_same_inode_exits_6` (paranoia guard).
10. **TC-UNIT-10** `test_resolve_paths_creates_output_parent_dir` (`/tmp/new/dir/out.md`).
11. **TC-UNIT-11** `test_main_catches_encrypted_workbook_to_exit_3_basename_only`.
12. **TC-UNIT-12** `test_main_catches_sheet_not_found_to_exit_2`.
13. **TC-UNIT-13** `test_main_macro_warning_continues_with_exit_0`.
14. **TC-UNIT-14** `test_main_json_errors_envelope_shape_v1_all_five_keys`.
15. **TC-UNIT-15** `test_main_terminal_catchall_redacts_path_in_error_field`
    (monkey-patch `open_workbook` raising
    `PermissionError("/Users/secret/file.xlsx")`).
16. **TC-UNIT-16** `test_main_terminal_catchall_uses_internal_error_code_7`.

In `test_public_api.py` (≥ 5 tests):

1. **TC-UNIT-01** `test_convert_helper_no_kwargs_uses_defaults`.
2. **TC-UNIT-02** `test_convert_helper_flag_value_atomic_token`
   (`format="hybrid"` produces argv element `"--format=hybrid"`).
3. **TC-UNIT-03** `test_convert_helper_boolean_true_appends_flag_only`
   (`include_formulas=True` produces argv element
   `"--include-formulas"` with NO `=True`).
4. **TC-UNIT-04** `test_convert_helper_boolean_false_omits_flag`
   (`include_formulas=False` produces NO argv element).
5. **TC-UNIT-05** `test_convert_helper_none_kwarg_skipped`
   (`memory_mode=None` produces NO argv element).
6. **TC-UNIT-06** `test_convert_helper_underscore_to_dash_in_flag_name`
   (`hyperlink_scheme_allowlist="http,https"` →
   `"--hyperlink-scheme-allowlist=http,https"`).

### Regression Tests

- The 5-line `diff -q` silent gate (asserted in every task).
- Existing xlsx test suites unchanged.
- `ruff check skills/xlsx/scripts/` green.
- 012-01 smoke test still passes (sentinel UPDATED to real
  behaviour per `tdd-stub-first §2.4`: TC-UNIT-04 / -05
  REPLACED to assert correct exit codes through the envelope
  pipeline; remaining test cases unchanged).

## Acceptance Criteria

- [ ] `_validate_flag_combo` implemented: M7 raises before file
      I/O; R14h raises before file I/O; both with code 2.
- [ ] `_resolve_paths` implemented: same-path guard via
      `Path.resolve()` follows symlinks; output-parent
      auto-create.
- [ ] `main()` body wraps every fail path through
      `_errors.report_error`; no `sys.exit(N)` outside the shim
      `__main__` block.
- [ ] Terminal `except Exception` catch-all renders
      `InternalError` code 7 envelope; raw `str(exc)` NEVER
      appears in the `error` field.
- [ ] `convert_xlsx_to_md(...)` programmatic helper builds argv
      with `--flag=value` atomic-token form and routes through
      `main()`.
- [ ] All 8 E2E test slugs in the table above bound and passing.
- [ ] All ≥ 22 unit tests (16 + 6) pass.
- [ ] Existing tests still green; 012-01 smoke test updated and
      green.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] 5-line `diff -q` silent gate green:
      ```bash
      diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
      diff -q  skills/docx/scripts/_soffice.py      skills/xlsx/scripts/_soffice.py
      diff -q  skills/docx/scripts/_errors.py       skills/xlsx/scripts/_errors.py
      diff -q  skills/docx/scripts/preview.py       skills/xlsx/scripts/preview.py
      diff -q  skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
      ```
- [ ] No changes to `xlsx_read/`, `office/`, `_errors.py`,
      `_soffice.py`, `preview.py`, `office_passwd.py`,
      `requirements.txt`, `pyproject.toml`, `install.sh`,
      `xlsx2csv2json/`, `json2xlsx/`, `md_tables2xlsx/`.

## Stub-First Gate Update (per `tdd-stub-first §2.4`)

The 012-01 smoke E2E assertions for `main()` and
`convert_xlsx_to_md(...)` MUST be updated FROM sentinel asserts
TO real behaviour:

- 012-01 asserted `main([]) == -999` and
  `convert_xlsx_to_md("ignored") == -999`. After this task:
  - `main(["fixtures/single_cell.xlsx", "--format=gfm",
    "--include-formulas"])` returns `2` (M7 lock).
  - `convert_xlsx_to_md("fixtures/encrypted.xlsx")` returns `3`
    (cross-3 envelope).
  - The package-import / `__all__` / exception-CODE smoke
    asserts REMAIN unchanged.

## Notes

- The `dispatch.iter_table_payloads` and `emit_workbook_md`
  calls inside `main()` are still STUB-backed in this task
  (yield nothing / return 0). Real logic in 012-03 + 012-04 +
  012-05 + 012-06. The smoke E2E #2 `T-stdout-when-output-omitted`
  passes here because the stubs short-circuit to "no body
  output" but exit 0 is correct for a no-flag run.
- The cross-7 H1 guard MUST check `Path.resolve()` equality
  AFTER both paths are resolved — symlinks are followed. Test
  fixture: create a regular file `single_cell.xlsx`, then
  `os.symlink(single_cell.xlsx, out.md)`. `out.md.resolve()`
  must yield the canonical path of `single_cell.xlsx`.
- The `details = {}` redaction in the terminal catch-all is
  CRITICAL (R23f). If a future contributor adds `details = str(exc)`,
  the regression #34 (`T-internal-error-envelope-redacts-raw-message`)
  fails-loud. Keep the redaction.
- The R14h gate's `details.table_count` field is the literal
  string `"unknown_pre_open"` because the gate fires BEFORE
  workbook open — the count is genuinely unknown. TASK R14.h
  specifies `details {n_requested: N, table_count: M, ...}`;
  this plan interprets `M` as the string `"unknown_pre_open"`
  at validate-time. (If the developer prefers, an alternative
  is to omit `table_count` from `details` entirely. The plan
  recommends the explicit string for diagnostic clarity.)

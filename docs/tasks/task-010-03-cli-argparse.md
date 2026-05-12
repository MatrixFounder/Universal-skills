# Task 010-03 [LOGIC IMPLEMENTATION]: `cli.py` — full argparse surface + dispatch

## Use Case Connection
- UC-01..UC-06 (every CLI flag combination)
- UC-08 / UC-09 (envelope trigger sites)

## Task Goal

Implement the full argparse surface per ARCH §5.1; bind `format_lock`
at parse time; validate flag combos; dispatch to `dispatch.iter_table_payloads`
then to `emit_json` or `emit_csv` (the latter two land in 010-05 /
010-06; this task wires the **dispatch trampoline** only — the emit
functions remain stubs returning `-997`).

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2csv2json/cli.py`

**Functions:**

- Add `build_parser(*, format_lock: str | None) -> argparse.ArgumentParser`
  - Parameters: `format_lock` from shim entry.
  - Returns: configured parser.
  - Logic: builds full argparse surface (Table below). When `format_lock`
    is set, `--format` is added as `argparse.SUPPRESS`-help argument
    with a `type=` validator that raises `FormatLockedByShim` if the
    user supplies a value differing from the lock.

  **Flag table (ARCH §5.1 — locked):**

  | Flag | Type | Default | Notes |
  | --- | --- | --- | --- |
  | `INPUT` (positional) | str | required | |
  | `OUTPUT` (positional, optional) | str | None | Same as `--output`; can be `-` for stdout-explicit. |
  | `--output OUT` | str | None | Conflict with positional → error at parse-time. |
  | `--output-dir DIR` | str | None | For multi-region CSV. |
  | `--sheet NAME` | str | `"all"` | Sheet name OR `"all"`. |
  | `--include-hidden` | bool flag | `False` | |
  | `--header-rows N\|auto` | str | `"1"` | Custom type; `auto` or non-negative int. |
  | `--header-flatten-style` | choice | `"string"` | `"string" \| "array"` (JSON-only; ignored for CSV). |
  | `--merge-policy` | choice | `"anchor-only"` | `"anchor-only" \| "fill" \| "blank"`. |
  | `--tables` | choice | `"whole"` | `"whole" \| "listobjects" \| "gap" \| "auto"`. |
  | `--gap-rows N` | int | `2` | M4 fix default. |
  | `--gap-cols N` | int | `1` | M4 fix default. |
  | `--include-hyperlinks` | bool flag | `False` | |
  | `--include-formulas` | bool flag | `False` | |
  | `--datetime-format` | choice | `"ISO"` | `"ISO" \| "excel-serial" \| "raw"`. |
  | `--json-errors` | bool flag | `False` | Cross-5 envelope (wired via `_errors.add_json_errors_argument`). |

- Add `_validate_flag_combo(args) -> None`
  - Logic (parse-time cross-flag invariants):
    1. **H3 (header-rows conflict):** if `args.header_rows != "auto"` AND `args.tables != "whole"` → raise `HeaderRowsConflict("Multi-table layouts require --header-rows auto; per-table header counts differ.")`.
    2. **R12.f (multi-sheet CSV):** when called for CSV (`format_lock="csv"` OR `args.format == "csv"`): if `args.sheet == "all"` AND `args.output_dir is None` → raise `MultiSheetRequiresOutputDir`. NOTE: this assumes >1 visible sheet; the precise check (post sheet enumeration) lives in `dispatch`. **At parse time we use a conservative pre-check** because we don't have the workbook open yet — refine in `dispatch` if the workbook has only 1 visible sheet.
    3. **R12.d (multi-table CSV without output-dir):** parse-time pre-check is impossible (region count requires opening the workbook). Raise in `dispatch` instead.

  Per ARCH §2.1 F1 `_validate_flag_combo` docstring: "raises envelope
  exceptions for cross-flag invariants where determinable at parse
  time." Cases requiring workbook inspection are deferred to dispatch.

- Add `_dispatch_to_emit(args, format: str) -> int`
  - Parameters: parsed args; resolved format (csv/json).
  - Logic:
    1. Open workbook via `xlsx_read.open_workbook(input_path, keep_formulas=args.include_formulas)`.
    2. Use a `with` block (context manager — xlsx-10.A D-A1).
    3. Within `warnings.catch_warnings(record=True)` block:
       - Invoke `dispatch.iter_table_payloads(args, reader)`.
       - Dispatch to `emit_csv.emit_csv(...)` or `emit_json.emit_json(...)` per format.
    4. After body returns: call `_emit_warnings_to_stderr(captured)`.
    5. Return the emit function's exit code.

  > **NOTE:** `emit_json` / `emit_csv` are stubs in this task — they
  > return `-997` so the orchestrator round-trip is testable without
  > the real emit implementations.

- Update `main(argv, *, format_lock=None) -> int`:
  ```python
  def main(argv=None, *, format_lock=None) -> int:
      parser = build_parser(format_lock=format_lock)
      try:
          args = parser.parse_args(argv)
      except SystemExit as e:
          # argparse called sys.exit on bad args; let it through.
          return int(e.code) if e.code else 2
      try:
          _validate_flag_combo(args)
      except _AppError as exc:
          return _errors.report_error(
              str(exc), code=exc.CODE,
              json_mode=args.json_errors,
              type_=type(exc).__name__,
              details={"flag_combo": True},
          )
      effective_format = format_lock or args.format
      return _run_with_envelope(
          args,
          format_lock=effective_format,
          body=lambda: _dispatch_to_emit(args, effective_format),
      )
  ```

- Update `emit_json.emit_json` and `emit_csv.emit_csv` stubs:
  bump sentinel from `-999` to `-997` to signal "argparse plumbing
  in place, emit body pending".

#### File: `skills/xlsx/scripts/xlsx2csv2json/__init__.py`

**Wire** the public helpers:
```python
def convert_xlsx_to_csv(input_path, output_path=None, **kwargs) -> int:
    argv = _build_argv(input_path, output_path, kwargs)
    return main(argv, format_lock="csv")


def convert_xlsx_to_json(input_path, output_path=None, **kwargs) -> int:
    argv = _build_argv(input_path, output_path, kwargs)
    return main(argv, format_lock="json")


def _build_argv(input_path, output_path, kwargs) -> list[str]:
    """Map kwargs to CLI argv. Used by public helpers."""
    argv = [str(input_path)]
    if output_path is not None:
        argv += ["--output", str(output_path)]
    # Map every supported kwarg to its --flag equivalent.
    # See cli.build_parser flag table for the full mapping.
    KWARG_TO_FLAG = {
        "output_dir": "--output-dir",
        "sheet": "--sheet",
        "header_rows": "--header-rows",
        "header_flatten_style": "--header-flatten-style",
        "merge_policy": "--merge-policy",
        "tables": "--tables",
        "gap_rows": "--gap-rows",
        "gap_cols": "--gap-cols",
        "datetime_format": "--datetime-format",
    }
    BOOL_KWARG_TO_FLAG = {
        "include_hidden": "--include-hidden",
        "include_hyperlinks": "--include-hyperlinks",
        "include_formulas": "--include-formulas",
        "json_errors": "--json-errors",
    }
    for k, v in kwargs.items():
        if k in KWARG_TO_FLAG:
            argv += [KWARG_TO_FLAG[k], str(v)]
        elif k in BOOL_KWARG_TO_FLAG:
            if v:
                argv.append(BOOL_KWARG_TO_FLAG[k])
        else:
            raise TypeError(f"Unknown kwarg: {k!r}")
    return argv
```

### New Files

#### `skills/xlsx/scripts/xlsx2csv2json/tests/test_cli.py`

Unit tests for `cli.py`:

1. **TC-UNIT-01 (`test_build_parser_csv_lock_rejects_json`):** `build_parser(format_lock="csv")` → `parse_args(["in.xlsx", "--format", "json"])` raises `FormatLockedByShim`.
2. **TC-UNIT-02 (`test_build_parser_json_lock_rejects_csv`):** symmetric.
3. **TC-UNIT-03 (`test_build_parser_defaults_locked`):** every default per the flag table.
4. **TC-UNIT-04 (`test_header_rows_conflict_int_with_multi_table`):** `["in.xlsx", "--header-rows", "2", "--tables", "listobjects"]` → exit 2 envelope `HeaderRowsConflict`.
5. **TC-UNIT-05 (`test_header_rows_auto_with_multi_table_ok`):** `["in.xlsx", "--header-rows", "auto", "--tables", "listobjects"]` → no parse-time error.
6. **TC-UNIT-06 (`test_multi_sheet_csv_without_output_dir`):** `format_lock="csv"`, default `--sheet all`, no `--output-dir` → `MultiSheetRequiresOutputDir` raised. (Edge: if test fixture has only 1 visible sheet, this is deferred to dispatch — test uses synthetic 2-sheet fixture.)
7. **TC-UNIT-07 (`test_output_positional_and_flag_conflict`):** `["in.xlsx", "out.json", "--output", "other.json"]` → parser error.
8. **TC-UNIT-08 (`test_help_message_for_csv_shim`):** `python3 xlsx2csv.py --help` → exits 0 (stdout contains "INPUT").
9. **TC-UNIT-09 (`test_help_message_for_json_shim`):** symmetric.
10. **TC-UNIT-10 (`test_main_returns_dispatch_sentinel`):** with valid argv → `main` calls `_dispatch_to_emit` → emit stub returns `-997` → exit 0 (mapped via `_run_with_envelope` which doesn't transform a negative-sentinel positive return). _Alternative_: emit stub raises a marker exception caught at envelope; assert the return code matches.
11. **TC-UNIT-11 (`test_build_argv_maps_all_kwargs`):** `_build_argv("in.xlsx", "out.json", {"sheet": "Sheet1", "tables": "gap"})` produces argv with each flag.
12. **TC-UNIT-12 (`test_build_argv_rejects_unknown_kwarg`):** `_build_argv(..., foo="bar")` → `TypeError`.

#### `skills/xlsx/scripts/xlsx2csv2json/tests/fixtures/two_sheets_simple.xlsx`

Hand-built fixture: two visible sheets, single-row header, 3 data
rows each. Used by TC-UNIT-06 + later tasks. Generated by helper
script in 010-01 OR re-used from `xlsx_read/tests/fixtures/` if a
match exists.

#### `skills/xlsx/scripts/xlsx2csv2json/tests/test_smoke_stub.py`

**Update** `test_main_returns_sentinel_in_stub_phase` removed (or
renamed to `test_main_returns_dispatch_sentinel`); the new assertion
is that `main` reaches the dispatch trampoline and the emit stubs
return `-997`.

### Component Integration

- `cli.py:main()` now drives the entire CLI surface; both shims call
  `main(format_lock="csv"|"json")` after argparse.
- `_dispatch_to_emit` is the trampoline that 010-05 / 010-06 fill in;
  no change to this task's `main()` signature when those land.
- `__init__.py` public helpers `convert_xlsx_to_csv` / `convert_xlsx_to_json`
  delegate to `main()` via `_build_argv` — single source of truth for
  CLI semantics.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01:** `python3 xlsx2csv.py --help` → exit 0.
2. **TC-E2E-02:** `python3 xlsx2json.py --help` → exit 0.
3. **TC-E2E-03:** `python3 xlsx2csv.py in.xlsx --format json` →
   exit 2, stderr contains "FormatLockedByShim".
4. **TC-E2E-04:** `python3 xlsx2json.py in.xlsx --header-rows 2 --tables listobjects` → exit 2, "HeaderRowsConflict".

### Unit Tests

(12 listed above.)

### Regression Tests

- All 010-01 + 010-02 tests still green.
- `ruff check scripts/` green.
- Existing xlsx test suites green.

## Acceptance Criteria

- [ ] `build_parser` accepts every flag in the locked table.
- [ ] `format_lock` rejects mismatched `--format`.
- [ ] `_validate_flag_combo` raises `HeaderRowsConflict` /
  `MultiSheetRequiresOutputDir` per spec.
- [ ] `main()` routes through `_run_with_envelope`.
- [ ] Public helpers `convert_xlsx_to_csv` / `convert_xlsx_to_json`
  delegate to `main()` via `_build_argv`.
- [ ] All 12 unit tests in `test_cli.py` pass.
- [ ] All 4 E2E in this task pass.
- [ ] `--help` text mentions all flags.
- [ ] `ruff check scripts/` green.
- [ ] 12-line `diff -q` silent.

## Notes

- The `_build_argv` mapper is intentionally **TypeError-strict on
  unknown kwargs** — prevents silent typos at the Python-caller
  boundary.
- `--format` is **suppressed from `--help`** when `format_lock` is
  set (so `xlsx2csv.py --help` does not advertise `--format`).
- Header-rows custom type: accept `"auto"` verbatim OR any
  non-negative integer; reject negatives.
- `--gap-rows` / `--gap-cols` accept any non-negative int; library
  enforces upper bound (`_GAP_DETECT_MAX_CELLS` cap is in xlsx-10.A
  §13.4).

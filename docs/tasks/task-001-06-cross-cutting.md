# Task 2.01 [R7]: [LOGIC IMPLEMENTATION] Cross-3/4/5/7-H1 hardening

## Use Case Connection
- I3.1 (encryption / macro / same-path / json-errors gates).
- RTM: R7 — full cross-cutting hardening contract.

## Task Goal
Replace the stub `main()` from task 1.01 with a real entry point that wires the four cross-skill contracts byte-for-byte with `docx_add_comment.py`:
1. Encryption check (cross-3) — exit 3 `EncryptedFileError`.
2. Macro warning (cross-4) — `.xlsm → .xlsx` paths emit warning to stderr, no failure.
3. Same-path guard (cross-7 H1) — `Path.resolve()` equality → exit 6 `SelfOverwriteRefused`.
4. JSON-errors envelope routing (cross-5) — every failure path goes through `_errors.report_error` when `--json-errors` is set, including argparse usage errors.

Plus the MX-A / MX-B / DEP-1..DEP-4 mutex/dependency rules from TASK §2.5.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

**Function `main(argv)`:**
- Replace stub copy-of-input with the real orchestration sequence:
  1. `args = build_parser().parse_args(argv)` — parsing.
  2. **Post-parse mutex/dependency checks** (NEW helper `_validate_args(args)`):
     - MX-A: `args.cell xor args.batch` → if both or neither, raise `UsageError`.
     - MX-B: `args.threaded and args.no_threaded` → `UsageError`.
     - DEP-1: `--cell` requires `--text` and `--author`.
     - DEP-2: `--batch` envelope shape requires `--default-author` (deferred to F3 batch loader; this validation pass only checks the file exists or `-` for stdin).
     - DEP-3: `--default-threaded` with `--cell` → `UsageError`.
  3. **Cross-7 H1 same-path check** (NEW helper `_assert_distinct_paths(args.input, args.output)`):
     - `Path(args.input).resolve() == Path(args.output).resolve()` → exit 6 `SelfOverwriteRefused`.
     - Resolves through symlinks via `Path.resolve()`.
  4. **Cross-3 encryption check:** `assert_not_encrypted(args.input)` → on `EncryptedFileError` exit 3.
  5. **Cross-4 macro warning:** `warn_if_macros_will_be_dropped(args.input, args.output, sys.stderr)` (no failure path, just stderr).
  6. **Date resolution (Q5):** `args.date_iso = args.date or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")`.
  7. Dispatch to `single_cell_main(args)` or `batch_main(args)` (still stubs in this task — they'll just call the real F2/F3/F4/F5 handlers as those land).
  8. **Cross-5 JSON envelope routing:** wrap the whole orchestration in a try/except that, when `args.json_errors` is set, routes ALL exceptions through `_errors.report_error(args.json_errors, error_message, code, error_type, details)`. Argparse usage errors are routed via subclassing `argparse.ArgumentParser.error` to call `report_error` and `sys.exit(2)`.

**New helpers:**
- `_validate_args(args) -> None` — raises `UsageError` (a new local exception class) on rule violations.
- `_assert_distinct_paths(input_path, output_path) -> None` — raises `SelfOverwriteRefused` (local exception with code=6).
- `_resolve_date(date_arg) -> str` — returns ISO-8601 string with `Z` suffix (Q5).
- A `JsonErrorsArgumentParser(argparse.ArgumentParser)` subclass that overrides `error()` to route through `report_error` when `--json-errors` is detected in `sys.argv`.

### Component Integration
- All cross-cutting helpers are imported from existing modules:
  - `assert_not_encrypted`, `EncryptedFileError` from `office._encryption`.
  - `warn_if_macros_will_be_dropped` from `office._macros`.
  - `add_json_errors_argument`, `report_error` from `_errors`.
- `Path.resolve()` is the standard `pathlib` mechanism — handles symlinks via `strict=False` default.

## Test Cases

### End-to-end Tests
1. **TC-E2E-T-same-path:** `xlsx_add_comment.py file.xlsx file.xlsx --cell A5 --author Q --text msg --json-errors` → exit 6, stderr is single-line JSON `{"v":1,"code":6,"type":"SelfOverwriteRefused",...}`.
2. **TC-E2E-T-same-path-symlink:** Create `file2.xlsx → file.xlsx` symlink; `xlsx_add_comment.py file.xlsx file2.xlsx ...` → exit 6.
3. **TC-E2E-T-encrypted:** Pass `golden/inputs/encrypted.xlsx` → exit 3, JSON envelope `EncryptedFileError`.
4. **TC-E2E-T-macro-xlsm-warns:** Input `macro.xlsm`, output `out.xlsm` → exit 0 (no warning to stderr — same extension); input `macro.xlsm`, output `out.xlsx` → exit 0 BUT warning printed to stderr.
5. **TC-E2E-mutex-A:** `... --cell A5 --batch foo.json` → exit 2, JSON envelope `UsageError`, message mentions "mutually exclusive".
6. **TC-E2E-mutex-B:** `... --cell A5 --threaded --no-threaded` → exit 2, JSON envelope `UsageError`.

### Unit Tests
- Remove `skipTest` from `TestSamePathGuard.test_identical_path_exits_6` and `test_symlink_resolves_to_same_path` — assert real exit codes via `subprocess.run` or by catching the raised exception inside `main(argv)`.
- New: `TestArgValidation` — 4 sub-tests for MX-A, MX-B, DEP-1, DEP-3.

### Regression Tests
- `office/tests/test_encryption.py` and `office/tests/test_macros.py` MUST stay green.
- All existing E2E (csv2xlsx etc.) MUST stay green.

## Acceptance Criteria
- [ ] `main()` orchestration sequence in place (no more stub copy-of-input).
- [ ] All 6 TC-E2E above pass.
- [ ] All 6 unit tests above pass (no longer skipped).
- [ ] `--json-errors` envelope on argparse usage errors verified.
- [ ] `office/tests/` regression green.
- [ ] No edits to `skills/docx/scripts/office/` (CLAUDE.md §2 compliance — verify with `diff -qr office ../../docx/scripts/office`).

## Notes
- After this task, all 17 E2E tests still pass (most still on stubs), but the cross-cutting tests genuinely assert real behaviour.
- `JsonErrorsArgumentParser` is the trickiest piece — `argparse` calls `self.error()` BEFORE the parsed `args` exist, so we sniff `--json-errors` from raw `sys.argv` (mirrors how docx_add_comment.py does it; copy the pattern).
- Q2 (empty-text rejection) is enforced in 2.04 (legacy write path), NOT here — it's a content-level validation, not a cross-cutting one.

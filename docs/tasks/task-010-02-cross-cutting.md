# Task 010-02 [LOGIC IMPLEMENTATION]: Cross-cutting envelopes (cross-3 / cross-4 / cross-5 / cross-7)

## Use Case Connection
- UC-07 (encrypted workbook → exit 3 envelope)
- UC-08 (same-path canonical-resolve guard → exit 6)
- UC-09 (`--json-errors` envelope shape v=1)
- UC-01 A3 (`MacroEnabledWarning` propagation)

## Task Goal

Implement the cross-cutting envelope plumbing per TASK §R14–§R17 and
ARCH §7.2 — give every later task a uniform error-handling foundation
to call into. Touches `cli.py` (path resolve + envelope dispatch),
`dispatch.py` (helper for sheet-name path-component validation —
class defined here; raise sites later) and `exceptions.py` (already
declared in 010-01; this task wires the **raising paths** for cross-3,
cross-7, and the macro-warning capture).

> **NOTE:** Argument-parsing surface (`build_parser`, full flag set)
> lands in **010-03**. This task implements only the cross-cutting
> primitives (`_resolve_paths`, `_run_with_envelope`,
> `_emit_warnings_to_stderr`).

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2csv2json/cli.py`

**Functions:**
- Add `_resolve_paths(input_arg: str, output_arg: str | None,
  output_dir_arg: str | None) -> tuple[Path, Path | None, Path | None]`
  - Parameters:
    - `input_arg` — raw `INPUT` from argv.
    - `output_arg` — raw `--output` or `-` or `None`.
    - `output_dir_arg` — raw `--output-dir` or `None`.
  - Returns: `(resolved_input, resolved_output_or_None, resolved_output_dir_or_None)`.
  - Logic:
    1. Resolve INPUT via `Path(input_arg).resolve(strict=True)`;
       on `FileNotFoundError` re-raise as-is (caller maps to exit 1).
    2. If `output_arg in (None, "-")`: `resolved_output = None` (stdout).
    3. Else: `resolved_output = Path(output_arg).resolve()` —
       parent-dir auto-created if missing
       (`resolved_output.parent.mkdir(parents=True, exist_ok=True)`).
    4. If `resolved_output is not None` and `resolved_output == resolved_input`:
       raise `SelfOverwriteRefused(f"Refusing to overwrite input: {resolved_input.name}")`.
    5. If `output_dir_arg`:
       `resolved_output_dir = Path(output_dir_arg).resolve()`;
       `resolved_output_dir.mkdir(parents=True, exist_ok=True)`;
       additional same-path check: `resolved_output_dir != resolved_input.parent`
       is NOT required (different files; collision detected per-file later).

- Add `_run_with_envelope(args, *, format_lock, body: Callable[[], int]) -> int`
  - Parameters:
    - `args` — parsed `argparse.Namespace`.
    - `format_lock` — `"csv" | "json" | None`.
    - `body` — callable that performs the actual conversion; returns exit code on success.
  - Returns: exit code.
  - Logic: try/except wrapper that maps known exceptions to
    `_errors.report_error(msg, code, json_mode=args.json_errors, type_=type(exc).__name__, details={...})` and returns the code. Uses **basename-only** in `error` message and `details.filename = path.name` (parallel xlsx_read §13.2).

- Add `_emit_warnings_to_stderr(captured: list[warnings.WarningMessage]) -> None`
  - Parameters: captured warnings from `warnings.catch_warnings(record=True)`.
  - Logic: for each `w`: `warnings.showwarning(w.message, w.category,
    w.filename, w.lineno)` — Python default formatter. Per ARCH HS-7,
    warnings are NOT promoted to JSON envelope shape regardless of
    `--json-errors`.

**Imports added** (top of file):

```python
from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Callable

# _errors lives at scripts/ root (4-skill replicated). cli.py is
# imported from the package; the shim already did sys.path.insert(0, parent)
# so plain `import _errors` works.
import _errors

from .exceptions import (
    _AppError,
    SelfOverwriteRefused,
    MultiTableRequiresOutputDir,
    MultiSheetRequiresOutputDir,
    HeaderRowsConflict,
    InvalidSheetNameForFsPath,
    OutputPathTraversal,
    FormatLockedByShim,
    PostValidateFailed,
)
```

**Update `main()` signature**:
```python
def main(argv=None, *, format_lock=None) -> int:
    """Entry point — full argparse lands in 010-03; this task wires
    only the envelope helpers callable in tests.
    """
    return -998  # SENTINEL_010_02 — wired by 010-03
```

The sentinel changes from `-999` to `-998` to signal "envelope helpers
in place, argparse still pending".

#### File: `skills/xlsx/scripts/xlsx2csv2json/dispatch.py`

**Functions:**
- Add `_validate_sheet_path_components(name: str) -> None`
  - Parameters: `name` — sheet OR table name destined to be a path component.
  - Logic: reject if any of `{"/", "\\", "..", "\x00", ":", "*", "?", "<", ">", "|", "\""}` appears in `name` OR `name in (".", "")`. Raise `InvalidSheetNameForFsPath(f"Name unsafe for filesystem: {name!r}")`.

#### File: `skills/xlsx/scripts/xlsx2csv2json/tests/test_smoke_stub.py`

**Update** `test_main_returns_sentinel_in_stub_phase`:
- New assertion: `main([], format_lock="csv") == -998` (was -999).

### New Files

#### `skills/xlsx/scripts/xlsx2csv2json/tests/test_cross_cutting.py`

Unit tests for the cross-cutting primitives:

1. **TC-UNIT-01 (`test_resolve_paths_happy`):**
   `_resolve_paths(tmpfile, None, None)` returns `(resolved, None, None)`.
2. **TC-UNIT-02 (`test_resolve_paths_self_overwrite`):**
   `_resolve_paths(tmpfile, str(tmpfile), None)` raises
   `SelfOverwriteRefused`.
3. **TC-UNIT-03 (`test_resolve_paths_via_symlink`):**
   Create symlink `out.json -> input.xlsx`; resolve both → equal →
   raises `SelfOverwriteRefused`.
4. **TC-UNIT-04 (`test_resolve_paths_parent_dir_auto_create`):**
   `_resolve_paths(tmpfile, "/tmp/sub/dir/out.json", None)` creates
   `/tmp/sub/dir/` if missing.
5. **TC-UNIT-05 (`test_resolve_paths_input_not_found`):**
   `_resolve_paths("/nonexistent.xlsx", None, None)` raises
   `FileNotFoundError`.
6. **TC-UNIT-06 (`test_run_with_envelope_json_mode`):**
   `_run_with_envelope(args_json_errors=True, body=lambda: raise EncryptedWorkbookError("..."))` → stderr has JSON envelope with `code=3, type="EncryptedWorkbookError"`, returns 3.
7. **TC-UNIT-07 (`test_run_with_envelope_basename_only`):**
   Envelope `details.filename` equals basename, NOT full path
   (parallel xlsx_read §13.2 fix).
8. **TC-UNIT-08 (`test_validate_sheet_path_components_reject_list`):**
   Each character in `{/, \\, .., NUL, :, *, ?, <, >, |, "}` →
   `InvalidSheetNameForFsPath` raised.
9. **TC-UNIT-09 (`test_validate_sheet_path_components_dot_and_empty`):**
   `"."` and `""` → raise.
10. **TC-UNIT-10 (`test_validate_sheet_path_components_happy`):**
    `"My Sheet"`, `"Q1_2026"`, `"Sales (US)"` → no raise.
11. **TC-UNIT-11 (`test_emit_warnings_propagates_via_showwarning`):**
    Capture stderr; emit MacroEnabledWarning via
    `_emit_warnings_to_stderr`; assert stderr non-empty AND does NOT
    contain a JSON envelope (warnings are human-readable per HS-7).

### Component Integration

- `_run_with_envelope` is the canonical exit-code dispatcher used by
  010-03's `main()` body.
- `_resolve_paths` is the canonical path-resolution helper used by
  010-03 and 010-06.
- `_validate_sheet_path_components` is called by 010-04
  (`iter_table_payloads`) before yielding any region whose sheet/table
  name is destined to become a path component.

## Test Cases

### Unit Tests

(11 unit tests listed above.)

### Regression Tests

- Run `python3 -m unittest discover -s skills/xlsx/scripts/xlsx2csv2json/tests`
  — all green (5 smoke from 010-01 + 11 new = 16 total).
- Run existing xlsx test suites — no regression.
- Run `ruff check skills/xlsx/scripts/` — green.

## Acceptance Criteria

- [ ] `cli.py` exports `_resolve_paths`, `_run_with_envelope`, `_emit_warnings_to_stderr`.
- [ ] `dispatch.py` exports `_validate_sheet_path_components`.
- [ ] 11 unit tests in `test_cross_cutting.py` pass.
- [ ] `test_main_returns_sentinel_in_stub_phase` updated to expect `-998`.
- [ ] Envelope shape matches `_errors.py` v=1: `{v:1, error, code, type, details}`.
- [ ] `code` value is `3` for `EncryptedWorkbookError`, `6` for
  `SelfOverwriteRefused`, `2` for `_AppError` exit-2 subclasses, `7`
  for `PostValidateFailed`.
- [ ] Error messages use basename only — full paths NEVER leak
  (regression: `details.filename == path.name`).
- [ ] `python3 -m unittest discover` exits 0.
- [ ] `ruff check scripts/` green.
- [ ] 12-line `diff -q` silent gate (ARCH §9.4).
- [ ] No `xlsx_read/` modification.
- [ ] No `office/` / `_errors.py` / `_soffice.py` / `preview.py` / `office_passwd.py` modification.

## Notes

- **No `try: ... except Exception:` swallow.** Only listed exception
  types (cross-3 encrypted, `_AppError` subclasses, `FileNotFoundError`,
  `zipfile.BadZipFile`) are mapped. Unknown exceptions propagate (CI
  surfaces as crash; users see Python traceback — acceptable v1).
- The envelope dispatch table:
  | Exception | Code | Notes |
  | --- | --- | --- |
  | `EncryptedWorkbookError` (xlsx_read) | 3 | cross-3 |
  | `FileNotFoundError` | 1 | cross-1 |
  | `zipfile.BadZipFile` | 2 | malformed input |
  | `SheetNotFound` (xlsx_read) | 2 | mapped from KeyError |
  | `OverlappingMerges` (xlsx_read) | 2 | corrupted workbook |
  | `_AppError` subclasses | per `.CODE` attr | shim-level |
- `MacroEnabledWarning` is **not** raised — it's a warning. The
  capture pattern is `warnings.catch_warnings(record=True)` at the
  `convert_xlsx_to_*` boundary; 010-03 wires the boundary,
  `_emit_warnings_to_stderr` is the helper.
- The 4-skill replicated `_errors.py` already supplies
  `report_error(message, code, *, json_mode, type_=None, details=None)`
  — verified at `scripts/_errors.py:42-105` (xlsx-2 precedent).

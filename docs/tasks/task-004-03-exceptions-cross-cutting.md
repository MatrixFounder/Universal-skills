# Task 004.03: Exceptions module + cross-cutting helpers (envelope wiring, same-path guard, stdin reader, post-validate enable-check)

## Use Case Connection
- **UC-1 A2** (same-path collision exit 6), **UC-4** (stdin envelope), **UC-4 A1/A2** (truncated pipe / empty input), all UCs through the cross-5 envelope contract.

## Task Goal
Implement two narrow, mechanical pieces: (a) the closed `_AppError` exception hierarchy with full `(message, code, error_type, details)` attribute model; (b) the `cli_helpers.py` cross-cutting utilities — same-path guard, stdin UTF-8 reader, post-validate enable-check. **No JSON parsing, no cell coercion, no workbook writing in this task.** The point is to land all the cross-cutting glue so 004.04–004.07 can focus purely on their F-region.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/json2xlsx/exceptions.py`

Replace the stub bodies. `_AppError` is a **plain `Exception` subclass** (NOT `@dataclass(frozen=True)`; mirrors xlsx-6 `xlsx_comment/exceptions.py` precedent — see ARCH m1 fix).

```python
class _AppError(Exception):
    """Closed taxonomy for xlsx-2 user-facing errors.

    Carries the four fields `_errors.report_error` needs for the
    cross-5 envelope: a human-readable message, an integer exit
    code, a symbolic error_type, and a free-form details dict.
    """
    def __init__(
        self,
        message: str,
        *,
        code: int,
        error_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.error_type = error_type
        self.details = dict(details) if details else {}


class EmptyInput(_AppError):
    def __init__(self, source: str) -> None:
        super().__init__(
            f"Input is empty: {source}",
            code=2, error_type="EmptyInput",
            details={"source": source},
        )


class NoRowsToWrite(_AppError):
    def __init__(self, *, empty_sheet: str | None = None) -> None:
        details = {"empty_sheet": empty_sheet} if empty_sheet else {}
        super().__init__(
            "No rows to write — input would produce an empty workbook",
            code=2, error_type="NoRowsToWrite",
            details=details,
        )


class JsonDecodeError(_AppError):
    def __init__(self, *, line: int, column: int, msg: str) -> None:
        super().__init__(
            f"JSON decode failed at line {line}, column {column}: {msg}",
            code=2, error_type="JsonDecodeError",
            details={"line": line, "column": column, "msg": msg},
        )


class UnsupportedJsonShape(_AppError):
    def __init__(self, *, root_type: str, hint: str, first_element_type: str | None = None) -> None:
        details: dict[str, Any] = {"root_type": root_type, "hint": hint}
        if first_element_type is not None:
            details["first_element_type"] = first_element_type
        super().__init__(
            f"Unsupported JSON shape: {hint}",
            code=2, error_type="UnsupportedJsonShape",
            details=details,
        )


class InvalidSheetName(_AppError):
    def __init__(self, *, name: str, reason: str) -> None:
        super().__init__(
            f"Invalid sheet name {name!r}: {reason}",
            code=2, error_type="InvalidSheetName",
            details={"name": name, "reason": reason},
        )


class TimezoneNotSupported(_AppError):
    """Raised only under --strict-dates (D7 / R4.g)."""
    def __init__(self, *, value: str, sheet: str, row: int, column: str, tz_offset: str) -> None:
        super().__init__(
            f"Timezone-aware datetime not supported under --strict-dates "
            f"(sheet {sheet}, {column}{row}, value {value!r}, tz_offset {tz_offset})",
            code=2, error_type="TimezoneNotSupported",
            details={"value": value, "sheet": sheet, "row": row, "column": column, "tz_offset": tz_offset},
        )


class InvalidDateString(_AppError):
    """Raised only under --strict-dates (D7 / R4.g) — extends R4.f."""
    def __init__(self, *, value: str, sheet: str, row: int, column: str) -> None:
        super().__init__(
            f"Invalid date string under --strict-dates "
            f"(sheet {sheet}, {column}{row}, value {value!r})",
            code=2, error_type="InvalidDateString",
            details={"value": value, "sheet": sheet, "row": row, "column": column},
        )


class SelfOverwriteRefused(_AppError):
    def __init__(self, *, input_path: str, output_path: str) -> None:
        super().__init__(
            f"Input and output resolve to the same path: {input_path}",
            code=6, error_type="SelfOverwriteRefused",
            details={"input": input_path, "output": output_path},
        )


class PostValidateFailed(_AppError):
    def __init__(self, *, validator_output: str) -> None:
        super().__init__(
            "Post-validate hook (XLSX_JSON2XLSX_POST_VALIDATE) reported a non-zero exit",
            code=7, error_type="PostValidateFailed",
            details={"validator_output": validator_output[:8192]},
        )
```

#### File: `skills/xlsx/scripts/json2xlsx/cli_helpers.py`

Replace stub bodies:

```python
"""Cross-cutting helpers: same-path guard (F8), stdin reader,
post-validate enable-check + invocation (F6).

The post-validate hook itself is implemented in 004.08 — this task
only lands the enable-check and the function signature.
"""
import os
import subprocess
import sys
from pathlib import Path
from .exceptions import SelfOverwriteRefused, PostValidateFailed


_TRUTHY = frozenset({"1", "true", "yes", "on"})


def post_validate_enabled() -> bool:
    """Mirrors xlsx-6 `_post_validate_enabled` truthy allowlist
    (`xlsx_comment/cli_helpers.py:121-133`). Anything outside the
    allowlist (including '0', '', 'false') reads as off.
    """
    raw = os.environ.get("XLSX_JSON2XLSX_POST_VALIDATE", "").strip().lower()
    return raw in _TRUTHY


def assert_distinct_paths(input_path: str, output_path: Path) -> None:
    """Cross-7 H1 same-path guard. Skip when input is stdin '-'."""
    if input_path == "-":
        return
    try:
        in_resolved = Path(input_path).resolve(strict=False)
    except (OSError, RuntimeError):
        # Symlink loop or unreadable parent; treat as distinct (let
        # downstream read fail with the precise reason).
        return
    out_resolved = output_path.resolve(strict=False)
    if in_resolved == out_resolved:
        raise SelfOverwriteRefused(
            input_path=str(in_resolved), output_path=str(out_resolved),
        )


def read_stdin_utf8() -> bytes:
    """Read the entire stdin as bytes; downstream callers decode.

    Reading via `sys.stdin.buffer` avoids Windows newline translation
    that would corrupt JSONL inputs piped via `cat`.
    """
    return sys.stdin.buffer.read()


def run_post_validate(output: Path) -> tuple[bool, str]:
    """STUB — implemented in 004.08. Returns (passed, captured_output)."""
    raise NotImplementedError("xlsx-2 stub — task-004-08")
```

#### File: `skills/xlsx/scripts/json2xlsx/__init__.py`

Adjust re-exports if needed so that `from json2xlsx import _AppError, EmptyInput, …` resolves through `.exceptions`. No public-surface change.

### Component Integration

- `cli_helpers.assert_distinct_paths` is called from `cli._run` (which is still stub in this task — wiring lands in 004.07).
- Exception classes are importable from both the package root and `json2xlsx.exceptions`.
- The cross-5 envelope is produced by `_errors.report_error(message=exc.message, code=exc.code, error_type=exc.error_type, details=exc.details, json_mode=args.json_errors)`. **xlsx-2 NEVER builds the envelope dict by hand** — only via `_errors.report_error`.

## Test Cases

### Unit Tests (turn green in this task)

1. **TC-UNIT-EXC-01:** `EmptyInput("file.json")` has `.code == 2`, `.error_type == "EmptyInput"`, `.details == {"source": "file.json"}`, `.message` non-empty.
2. **TC-UNIT-EXC-02:** `SelfOverwriteRefused(input_path="a", output_path="b").code == 6`.
3. **TC-UNIT-EXC-03:** `PostValidateFailed(validator_output="x"*20000).details["validator_output"]` length ≤ 8192.
4. **TC-UNIT-EXC-04:** Every typed error is a subclass of `_AppError`, and `_AppError` is a subclass of `Exception` (not a frozen dataclass — ARCH m1 lock).
5. **TC-UNIT-CLIH-01:** `post_validate_enabled()` returns True for env value `"1"`, `"true"`, `"TRUE"`, `"yes"`, `"On"`; returns False for `"0"`, `""`, `"false"`, `"no"`, missing env var.
6. **TC-UNIT-CLIH-02:** `assert_distinct_paths("-", Path("out.xlsx"))` returns None (no raise).
7. **TC-UNIT-CLIH-03:** With a tempdir where `same.xlsx` exists, `assert_distinct_paths(str(same), same)` raises `SelfOverwriteRefused` with `.code == 6`.
8. **TC-UNIT-CLIH-04:** `assert_distinct_paths` with a symlink `link -> same.xlsx` raises `SelfOverwriteRefused` (verifies symlink-follow via `Path.resolve()`).
9. **TC-UNIT-CLIH-05:** `assert_distinct_paths` with two different absolute paths returns None.
10. **TC-UNIT-CLIH-06:** `read_stdin_utf8()` returns bytes when fed via a `subprocess.Popen` pipe (mock not allowed — runs a real child process).

### E2E test (turns green for SelfOverwriteRefused only)

- **T-same-path** from 004.02 turns green: `json2xlsx.py same.xlsx same.xlsx --json-errors` exits 6 with the cross-5 envelope payload.

### Regression Tests
- xlsx-6 / xlsx-7 / csv2xlsx unit + E2E green.

## Acceptance Criteria

- [ ] `exceptions.py` defines `_AppError` + 9 typed subclasses with the full `(message, code, error_type, details)` attribute model.
- [ ] `cli_helpers.py` implements `assert_distinct_paths`, `post_validate_enabled`, `read_stdin_utf8` (no logic for `run_post_validate` yet — stub remains).
- [ ] 10 unit tests for exceptions + helpers green (TC-UNIT-EXC-01..04, TC-UNIT-CLIH-01..06).
- [ ] E2E `T-same-path` green; `T-envelope-cross5-shape` shows correct envelope key set for the FileNotFound path (envelope wiring is exercised by `cli._run` which is still stub — so this E2E case may stay red until 004.07; document in test docstring).
- [ ] xlsx-6 / xlsx-7 / csv2xlsx green; `validate_skill.py` green; eleven `diff -q` silent.

## Notes

- The bool-before-int rule and ISO-date heuristics live in 004.05 — **do not** add date logic here.
- This task is intentionally narrow: glue only. Resist the temptation to fold loaders or coerce into this PR.
- The `_AppError` plain-`Exception` model (not `@dataclass`) is locked in ARCH §3.2 exceptions.py "Type model (m1 fix)". A frozen dataclass would require `eq=False, frozen=True` gymnastics to coexist with `Exception.__init__`; the plain pattern is cheaper and matches xlsx-6.

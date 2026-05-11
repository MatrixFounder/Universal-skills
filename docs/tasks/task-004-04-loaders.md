# Task 004.04: `loaders.py` — JSON / JSONL input reader + shape detection

## Use Case Connection
- **UC-1** (array-of-objects parse), **UC-2** (multi-sheet dict detection), **UC-3** (JSONL streaming parse + line-number diagnostics), **UC-1 A3 / A5** (empty input + invalid JSON envelope), **UC-2 A2** (duplicate top-level keys — honest scope only, NOT enforced).

## Task Goal
Implement F1 + F2 in `json2xlsx/loaders.py`: read raw bytes from file or stdin, decode UTF-8 strictly, detect which of the three shapes the JSON belongs to, parse it into the uniform `ParsedInput` representation. **All loader-related unit tests + E2E `T-invalid-json`, `T-empty-array`, partial happy-path tests turn green.**

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/json2xlsx/loaders.py`

Replace stub bodies with full F1+F2 implementation:

```python
"""Input acquisition + shape detection (F1 + F2).

F1 (Input Reader): pulls raw bytes from a file path or stdin.
F2 (Shape Detection & Parsing): dispatches on root token to one of
the three canonical JSON shapes (array-of-objects / multi-sheet dict
/ JSONL). Produces a uniform `ParsedInput` consumed by F4 (writer).

No openpyxl import; no Excel concept at this layer.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .exceptions import (
    EmptyInput, NoRowsToWrite, JsonDecodeError, UnsupportedJsonShape,
)


@dataclass(frozen=True)
class ParsedInput:
    shape: Literal["array_of_objects", "multi_sheet_dict", "jsonl"]
    sheets: dict[str, list[dict[str, Any]]]
    source_label: str


# -- F1 ----------------------------------------------------------------

def read_input(path: str, encoding: str = "utf-8") -> tuple[bytes, str]:
    """Read bytes from `path` (a filesystem path) or from stdin (`-`).

    Returns `(raw_bytes, source_label)` where `source_label` is the
    path or `"<stdin>"`. UTF-8 strict — caller decides whether to
    `.decode()` (we keep bytes here so JSONL line splitting is
    encoding-clean).
    """
    if path == "-":
        return sys.stdin.buffer.read(), "<stdin>"
    p = Path(path)
    if not p.is_file():
        # Re-use IOError exit-1 path via the CLI; here just propagate.
        raise FileNotFoundError(str(p))
    return p.read_bytes(), str(p)


# -- F2 ----------------------------------------------------------------

def detect_and_parse(
    raw: bytes,
    source: str,
    *,
    is_jsonl_hint: bool,
) -> ParsedInput:
    """Detect shape, parse, validate, return ParsedInput.

    Per ARCH m3 lock: `is_jsonl_hint=True` → JSONL path; otherwise
    decode as a single JSON document and dispatch on root type
    (root_token branch is in this function, NOT in F1).
    """
    if not raw or raw.strip() == b"":
        raise EmptyInput(source)

    if is_jsonl_hint:
        rows = _parse_jsonl(raw)
        if not rows:
            raise NoRowsToWrite()
        return ParsedInput(
            shape="jsonl",
            sheets={"Sheet1": rows},
            source_label=source,
        )

    try:
        doc = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise JsonDecodeError(line=exc.lineno, column=exc.colno, msg=exc.msg) from exc

    shape = _dispatch_root(doc)
    if shape == "array_of_objects":
        if not doc:
            raise NoRowsToWrite()
        return ParsedInput(
            shape="array_of_objects",
            sheets={"Sheet1": doc},
            source_label=source,
        )
    if shape == "multi_sheet_dict":
        if not doc:
            raise NoRowsToWrite()
        validated = _validate_multi_sheet(doc)
        for name, rows in validated.items():
            if not rows:
                raise NoRowsToWrite(empty_sheet=name)
        return ParsedInput(
            shape="multi_sheet_dict",
            sheets=validated,
            source_label=source,
        )
    # _dispatch_root raised already for the unsupported cases.
    raise AssertionError("unreachable")


def _parse_jsonl(raw: bytes) -> list[dict[str, Any]]:
    """One JSON object per line; blank lines tolerated (UC-3 A1).

    Mismatched root type (line is an array / scalar) → UnsupportedJsonShape
    with line N (UC-3 A3).

    Signature matches ARCH §5 exactly — `source` deliberately NOT
    passed; the JsonDecodeError envelope's `line` field is sufficient
    diagnostic context. If callers later want the source path in the
    envelope, plumb it via JsonDecodeError(details={"source": ...})
    at the call site in `detect_and_parse`, not via _parse_jsonl arg.
    """
    rows: list[dict[str, Any]] = []
    for idx, line in enumerate(raw.splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError as exc:
            raise JsonDecodeError(line=idx, column=exc.colno, msg=exc.msg) from exc
        if not isinstance(parsed, dict):
            raise UnsupportedJsonShape(
                root_type=type(parsed).__name__,
                hint=f"JSONL line {idx} is not an object",
            )
        rows.append(parsed)
    return rows


def _dispatch_root(doc: Any) -> Literal["array_of_objects", "multi_sheet_dict"]:
    if isinstance(doc, list):
        if doc and not all(isinstance(r, dict) for r in doc):
            first_bad = next(r for r in doc if not isinstance(r, dict))
            raise UnsupportedJsonShape(
                root_type="list",
                first_element_type=type(first_bad).__name__,
                hint="Array must contain only objects (rows). Wrap each row in {...}.",
            )
        return "array_of_objects"
    if isinstance(doc, dict):
        # Multi-sheet only when every value is a list (further validated by _validate_multi_sheet).
        if doc and all(isinstance(v, list) for v in doc.values()):
            return "multi_sheet_dict"
        raise UnsupportedJsonShape(
            root_type="dict",
            hint="Multi-sheet input requires every value to be a list of objects.",
        )
    raise UnsupportedJsonShape(
        root_type=type(doc).__name__,
        hint="Root must be array-of-objects or dict-of-arrays-of-objects.",
    )


def _validate_multi_sheet(doc: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Validate each sheet's rows are list[dict]. Sheet-name Excel
    rules are checked LATER (F4 writer) — here we only enforce the
    structural shape.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for name, rows in doc.items():
        if not isinstance(rows, list):
            raise UnsupportedJsonShape(
                root_type="dict",
                hint=f"Sheet {name!r} value is {type(rows).__name__}, expected list.",
            )
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                raise UnsupportedJsonShape(
                    root_type="dict",
                    first_element_type=type(row).__name__,
                    hint=f"Sheet {name!r} row {i} is {type(row).__name__}, expected object.",
                )
        out[name] = rows
    return out
```

### Component Integration

- `cli._run` (still stub) will dispatch:
  ```
  raw, src = read_input(args.input, args.encoding)
  parsed = detect_and_parse(raw, src, is_jsonl_hint=args.input.endswith(".jsonl") and args.input != "-")
  ```
- Wiring lands in 004.07.

## Test Cases

### Unit Tests (turn green in this task)

- All `TestLoaders` cases from 004.02 turn green:
  - `test_read_input_file_utf8` — reads file bytes correctly.
  - `test_read_input_stdin_dash` — `read_input("-")` reads `sys.stdin.buffer`.
  - `test_read_input_file_not_found` — raises `FileNotFoundError`.
  - `test_detect_array_of_objects` — `[{...}]` → `shape="array_of_objects"`, single sheet "Sheet1".
  - `test_detect_multi_sheet_dict` — `{"A":[{...}],"B":[{...}]}` → `shape="multi_sheet_dict"`, two sheets in order.
  - `test_detect_jsonl_by_extension` — bytes `b'{"a":1}\n{"a":2}\n'` with `is_jsonl_hint=True` → 2-row sheet.
  - `test_detect_unsupported_scalar` — `42` raises `UnsupportedJsonShape` with `root_type=="int"`.
  - `test_detect_unsupported_list_of_lists` — `[[1,2],[3,4]]` raises `UnsupportedJsonShape` with `first_element_type=="list"`.
  - `test_detect_empty_array_no_rows` — `[]` raises `NoRowsToWrite`.
  - `test_jsonl_blank_line_tolerated` — `b'{"a":1}\n\n{"a":2}\n'` produces 2 rows.
  - `test_jsonl_malformed_line_reports_line_number` — bad line 3 → `JsonDecodeError` with `details.line == 3`.

### E2E Tests (turn green this task)
- `T-invalid-json` — exit 2 envelope `JsonDecodeError` with line/column.
- `T-empty-array` — exit 2 envelope `NoRowsToWrite`.
- `T-happy-single-sheet` (parse part — full happy path needs writer + CLI, so this stays red until 004.07).
- `T-happy-multi-sheet` (parse part — same caveat).
- `T-happy-jsonl` (parse part — same caveat).

### Regression Tests
- All xlsx existing tests pass.

## Acceptance Criteria

- [ ] `loaders.py` implements `read_input`, `detect_and_parse`, `_parse_jsonl`, `_dispatch_root`, `_validate_multi_sheet` per signatures locked in ARCH §5.
- [ ] `ParsedInput` is a frozen dataclass with three attributes matching ARCH §4.1.
- [ ] All 11 TestLoaders cases green.
- [ ] E2E `T-invalid-json` + `T-empty-array` green; happy-path E2E tests parse correctly when invoked via `loaders.detect_and_parse` (logged via test debug; not yet fully green via CLI).
- [ ] LOC count of `loaders.py` ≤ 200.
- [ ] `validate_skill.py` green; eleven `diff -q` silent.

## Notes

- Honest scope §11.5 lock (duplicate top-level keys): `json.loads()` collapses them silently; we do NOT add `object_pairs_hook` in v1. Documented in TASK §11.5 + UC-2 A2.
- `read_input` raises `FileNotFoundError` (stdlib). The CLI layer in 004.07 maps it to exit 1 IOError via `_errors.report_error`. We deliberately do NOT define an `IOError` typed `_AppError` — IOErrors are platform-detail and best surfaced via the message directly.
- Sheet-name Excel-rule validation is `_validate_sheet_name` in `writer.py` (004.06) — keep loaders.py shape-only.
- This task is the **single biggest correctness win**: every E2E case below requires correct shape detection, and the error envelopes for the negative cases are user-visible.

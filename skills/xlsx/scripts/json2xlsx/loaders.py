"""xlsx-2 input acquisition + shape detection (F1 + F2).

F1 (Input Reader): acquires raw bytes from a file path or stdin.
F2 (Shape Detection & Parsing): dispatches on root token to one of
the three canonical JSON shapes (array-of-objects / multi-sheet dict
/ JSONL). Produces a uniform `ParsedInput` consumed by F4 (writer).

This module never imports openpyxl — Excel concepts (sheet-name
validation, cell typing, styling) live in F3/F4.

Honest scope:
  §11.5 — `json.loads()` collapses duplicate top-level keys silently
  (RFC 8259 §4 last-wins). xlsx-2 v1 does NOT detect this. Detection
  requires `json.JSONDecoder(object_pairs_hook=…)` and is deferred to
  v2.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .exceptions import (
    EmptyInput,
    JsonDecodeError,
    NoRowsToWrite,
    UnsupportedJsonShape,
)


class _NanInfRejected(Exception):
    """Internal sentinel — raised by `_reject_nan_inf` to halt
    `json.loads` when a non-finite literal appears in the input.
    Caught at the call site and translated to `JsonDecodeError` for
    a uniform cross-5 envelope.
    """

    def __init__(self, token: str) -> None:
        super().__init__(token)
        self.token = token


def _reject_nan_inf(token: str) -> None:
    """Parse-time guard against Python's non-strict JSON acceptance
    of `NaN`, `Infinity`, `-Infinity`. Passed to `json.loads(...,
    parse_constant=...)`. Raises `_NanInfRejected` so the loader
    can surface a typed envelope rather than letting the value
    flow through to openpyxl.
    """
    raise _NanInfRejected(token)


@dataclass(frozen=True)
class ParsedInput:
    """Shape-normalised representation produced by F2.

    `sheets` maps sheet name → list of row dicts. For shape
    `array_of_objects` / `jsonl` this is always `{"Sheet1": rows}`
    (the CLI's `--sheet NAME` override is applied later by F4). For
    shape `multi_sheet_dict` it preserves the input dict's insertion
    order.
    """
    shape: Literal["array_of_objects", "multi_sheet_dict", "jsonl"]
    sheets: dict[str, list[dict[str, Any]]]
    source_label: str


# ---------------------------------------------------------------------------
# F1 — Input Reader
# ---------------------------------------------------------------------------

def read_input(path: str, encoding: str = "utf-8") -> tuple[bytes, str]:
    """Read raw bytes from a filesystem path or from stdin (`-`).

    Returns `(raw_bytes, source_label)` where `source_label` is the
    path (for filesystem inputs) or `"<stdin>"` (for the stdin
    sentinel). Raw bytes are kept undecoded here so JSONL line-
    splitting is encoding-clean for the F2 dispatch.

    `encoding` is currently unused — stdin always reads as raw bytes
    via `sys.stdin.buffer.read`, and file reads also return raw bytes;
    the encoding parameter is reserved for future use (e.g.,
    locale-specific re-decoding before JSON parse) and accepted now
    so the public signature is stable.
    """
    if path == "-":
        return sys.stdin.buffer.read(), "<stdin>"
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return p.read_bytes(), str(p)


# ---------------------------------------------------------------------------
# F2 — Shape Detection & Parsing
# ---------------------------------------------------------------------------

def detect_and_parse(
    raw: bytes,
    source: str,
    *,
    is_jsonl_hint: bool,
) -> ParsedInput:
    """Detect shape, parse, validate, return a ParsedInput.

    Per ARCH m3 lock: `is_jsonl_hint=True` selects the JSONL parser
    path (line-by-line, blank lines tolerated). Otherwise the bytes
    are parsed as a single JSON document and dispatched on root type
    (the root-token branch lives in THIS function, not in F1).

    Error precedence (locked):
      1. All-whitespace / empty bytes → `EmptyInput` regardless of
         `is_jsonl_hint`. (`b'\\n\\n\\n'` reads as empty input, not
         as "JSONL with all blank lines".)
      2. JSON / JSONL parse errors → `JsonDecodeError` with line/col.
      3. Wrong shape → `UnsupportedJsonShape` with `root_type`.
      4. Empty-but-well-formed (`[]`, `{}`, or multi-sheet with a
         sheet whose row list is `[]`) → `NoRowsToWrite`. Multi-sheet
         empty-sheet variant carries `details.empty_sheet`.
    """
    if not raw or not raw.strip():
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

    # VDD-multi Security M-1 fix: surface UTF-8 decoding failures
    # through the same cross-5 envelope contract as JSON parse errors
    # (AQ-3 lock — every taxonomy error routes through report_error,
    # never raw Python tracebacks for malformed input). UTF-16 / latin-1
    # bytes / random binary land here.
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JsonDecodeError(
            line=1,
            column=exc.start + 1,
            msg=(
                f"invalid UTF-8 byte sequence at offset {exc.start} "
                f"({exc.reason})"
            ),
        ) from exc

    # VDD-multi Logic H2 fix: Python's json.loads is non-strict — it
    # silently accepts the literal tokens `NaN`, `Infinity`, and
    # `-Infinity`. These would flow through coerce_cell as `float`
    # and openpyxl would write them into the cell XML, producing a
    # workbook that Excel renders as #NUM! errors (or refuses to
    # open). parse_constant rejects them at decode time with a
    # typed envelope.
    try:
        doc = json.loads(text, parse_constant=_reject_nan_inf)
    except json.JSONDecodeError as exc:
        raise JsonDecodeError(line=exc.lineno, column=exc.colno, msg=exc.msg) from exc
    except _NanInfRejected as exc:
        raise JsonDecodeError(
            line=1, column=1,
            msg=(
                f"non-finite numeric literal {exc.token!r} is not valid "
                "for an Excel cell (NaN / Infinity / -Infinity not "
                "supported; emit `null` instead)"
            ),
        ) from exc

    shape = _dispatch_root(doc)
    if shape == "array_of_objects":
        if not doc:
            raise NoRowsToWrite()
        return ParsedInput(
            shape="array_of_objects",
            sheets={"Sheet1": doc},
            source_label=source,
        )
    # multi_sheet_dict
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


def _parse_jsonl(raw: bytes) -> list[dict[str, Any]]:
    """One JSON object per line; blank lines tolerated (UC-3 A1).

    Mismatched root type per line (array / scalar) → UnsupportedJsonShape
    with the offending line number (UC-3 A3). Per-line parse errors
    surface as JsonDecodeError with the same line number.

    Signature matches ARCH §5 exactly — `source` deliberately NOT
    passed; the JsonDecodeError envelope's `line` field is sufficient
    diagnostic context. If callers want the source path in details,
    the call site can wrap and re-raise.
    """
    rows: list[dict[str, Any]] = []
    for idx, line in enumerate(raw.splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        # UTF-8 decode first so an invalid byte sequence surfaces as
        # a typed JsonDecodeError envelope rather than an uncaught
        # UnicodeDecodeError traceback (VDD-multi Security M-1 lock,
        # applied to the JSONL path too).
        try:
            text = s.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise JsonDecodeError(
                line=idx,
                column=exc.start + 1,
                msg=(
                    f"invalid UTF-8 byte sequence at offset {exc.start} "
                    f"on JSONL line {idx} ({exc.reason})"
                ),
            ) from exc
        try:
            # Same NaN/Inf guard as the single-document path (VDD-multi
            # Logic H2 lock).
            parsed = json.loads(text, parse_constant=_reject_nan_inf)
        except json.JSONDecodeError as exc:
            raise JsonDecodeError(line=idx, column=exc.colno, msg=exc.msg) from exc
        except _NanInfRejected as exc:
            raise JsonDecodeError(
                line=idx, column=1,
                msg=(
                    f"non-finite numeric literal {exc.token!r} is not "
                    "valid for an Excel cell on JSONL line "
                    f"{idx} (NaN / Infinity / -Infinity not supported)"
                ),
            ) from exc
        if not isinstance(parsed, dict):
            raise UnsupportedJsonShape(
                root_type=type(parsed).__name__,
                hint=f"JSONL line {idx} is not an object",
            )
        rows.append(parsed)
    return rows


def _dispatch_root(
    doc: Any,
) -> Literal["array_of_objects", "multi_sheet_dict"]:
    """Pure shape classifier — never raises NoRowsToWrite (empty input
    is the caller's responsibility) but DOES raise UnsupportedJsonShape
    for any non-canonical structure.
    """
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
        # Multi-sheet requires every value to be a list; the actual
        # row-shape check happens in _validate_multi_sheet so the
        # error message can pinpoint the offending sheet.
        if doc and all(isinstance(v, list) for v in doc.values()):
            return "multi_sheet_dict"
        # Empty dict {} → multi_sheet_dict (caller raises NoRowsToWrite).
        if not doc:
            return "multi_sheet_dict"
        raise UnsupportedJsonShape(
            root_type="dict",
            hint="Multi-sheet input requires every value to be a list of objects.",
        )
    raise UnsupportedJsonShape(
        root_type=type(doc).__name__,
        hint="Root must be array-of-objects or dict-of-arrays-of-objects.",
    )


def _validate_multi_sheet(
    doc: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Validate that each sheet's rows are `list[dict]`.

    Sheet-name Excel-rule validation (≤ 31 chars, forbidden chars,
    reserved names) is OWNED by F4 (`writer._validate_sheet_name`).
    F2 only enforces the structural shape so the writer can rely on
    the row-of-dicts invariant.
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


__all__ = [
    "ParsedInput",
    "read_input",
    "detect_and_parse",
]

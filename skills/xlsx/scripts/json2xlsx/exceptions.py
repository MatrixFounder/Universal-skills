"""xlsx-2 typed error hierarchy.

Closed taxonomy: `_AppError` base + 9 typed subclasses. Each carries
the four fields `_errors.report_error` needs for the cross-5 envelope
(message, code, error_type, details). The orchestrator catches
`_AppError` once at the top of `cli._run` (AQ-3 lock) and routes
through `_errors.report_error` — xlsx-2 never builds the envelope
dict by hand.

Platform-IO errors (FileNotFoundError, OSError) are deliberately
NOT in this taxonomy — they're surfaced via direct
`report_error(error_type="FileNotFound" | "IOError", ...)` calls at
the CLI layer (see PLAN.md §"Platform-IO Errors").

Type model: plain `Exception` subclass per ARCH §3.2 m1 fix —
NOT `@dataclass(frozen=True)` (would require eq/frozen gymnastics
to coexist with `Exception.__init__`).
"""
from __future__ import annotations

from typing import Any


class _AppError(Exception):
    """Closed taxonomy for xlsx-2 user-facing errors.

    Carries the four fields `_errors.report_error` needs for the
    cross-5 envelope:
      - `message`: human-readable string (becomes envelope `error`).
      - `code`: integer exit code.
      - `error_type`: symbolic class name (becomes envelope `type`).
      - `details`: free-form dict (becomes envelope `details`).
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
        details: dict[str, Any] = {}
        if empty_sheet is not None:
            details["empty_sheet"] = empty_sheet
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
    def __init__(
        self,
        *,
        root_type: str,
        hint: str,
        first_element_type: str | None = None,
    ) -> None:
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
    """Raised only under `--strict-dates` (D7 / R4.g)."""

    def __init__(
        self,
        *,
        value: str,
        sheet: str,
        row: int,
        column: str,
        tz_offset: str,
    ) -> None:
        super().__init__(
            f"Timezone-aware datetime not supported under --strict-dates "
            f"(sheet {sheet}, {column}{row}, value {value!r}, tz_offset {tz_offset})",
            code=2, error_type="TimezoneNotSupported",
            details={
                "value": value,
                "sheet": sheet,
                "row": row,
                "column": column,
                "tz_offset": tz_offset,
            },
        )


class InvalidDateString(_AppError):
    """Raised only under `--strict-dates` (D7 / R4.g) — extends R4.f."""

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
            # VDD-multi Logic L5 fix: include both paths in the
            # human-readable message so users without --json-errors
            # see whether the typo was on the input or output side.
            (
                f"Input and output resolve to the same path "
                f"(input={input_path!r}, output={output_path!r})"
            ),
            code=6, error_type="SelfOverwriteRefused",
            details={"input": input_path, "output": output_path},
        )


def _truncate_utf8_bytes(s: str, limit: int) -> str:
    """Truncate `s` so that its UTF-8 encoding is at most `limit` BYTES.

    `s[:limit]` would count code points, not bytes, so multi-byte
    output (Cyrillic, CJK) would silently overflow the cap by up to
    4x. Encode → slice → decode-ignore picks a clean cut on the next
    encoding boundary.
    """
    encoded = s.encode("utf-8")
    if len(encoded) <= limit:
        return s
    return encoded[:limit].decode("utf-8", errors="ignore")


class PostValidateFailed(_AppError):
    def __init__(self, *, validator_output: str) -> None:
        super().__init__(
            "Post-validate hook (XLSX_JSON2XLSX_POST_VALIDATE) reported a non-zero exit",
            code=7, error_type="PostValidateFailed",
            details={"validator_output": _truncate_utf8_bytes(validator_output, 8192)},
        )


__all__ = [
    "_AppError",
    "EmptyInput",
    "NoRowsToWrite",
    "JsonDecodeError",
    "UnsupportedJsonShape",
    "InvalidSheetName",
    "TimezoneNotSupported",
    "InvalidDateString",
    "SelfOverwriteRefused",
    "PostValidateFailed",
]

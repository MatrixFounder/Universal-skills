"""xlsx-2 package public surface.

Single source of truth for `convert_json_to_xlsx`; the shim
(`json2xlsx.py`) re-exports — its body lives HERE.
"""
from __future__ import annotations

from .cli import main, _run
from .exceptions import (
    _AppError,
    EmptyInput,
    NoRowsToWrite,
    JsonDecodeError,
    UnsupportedJsonShape,
    InvalidSheetName,
    TimezoneNotSupported,
    InvalidDateString,
    SelfOverwriteRefused,
    PostValidateFailed,
)


def convert_json_to_xlsx(input_path: str, output_path: str, **kwargs: object) -> int:
    """Programmatic entry point. Mirrors `csv2xlsx.convert` semantics
    but routes through argparse so the same flag-handling code runs
    for both CLI and library callers.

    `kwargs` keys become long-form flags (`{"no_freeze": True}` →
    `--no-freeze`; `{"date_format": "DD/MM/YYYY"}` →
    `--date-format=DD/MM/YYYY`). Boolean True appends just the flag;
    any other type uses the `--flag=value` single-token form so an
    argparse value that happens to begin with `--` (e.g. an LLM-
    templated `date_format="--strict-dates"`) is NOT swallowed as a
    separate flag — VDD-multi Logic M4 lock. Returns the same exit
    code `main` would have returned.
    """
    argv: list[str] = [input_path, output_path]
    for key, value in kwargs.items():
        flag = "--" + key.replace("_", "-")
        if isinstance(value, bool):
            if value:
                argv.append(flag)
        else:
            # `--flag=value` form is atomic to argparse; a leading `--`
            # in `value` cannot poison the parse.
            argv.append(f"{flag}={value}")
    return main(argv)


__all__ = [
    "main",
    "_run",
    "convert_json_to_xlsx",
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

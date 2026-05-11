"""xlsx-3 package public surface.

Single source of truth for `convert_md_tables_to_xlsx` (ARCH M4 —
mirrors xlsx-2 `convert_json_to_xlsx`: `**kwargs -> int` via argparse
with `--flag=value` atomic-token form). Shim re-exports — body HERE.
"""
from __future__ import annotations

from pathlib import Path

from .cli import build_parser, main, _run
from .exceptions import (
    _AppError,
    EmptyInput,
    NoTablesFound,
    MalformedTable,
    InputEncodingError,
    InvalidSheetName,
    SelfOverwriteRefused,
    PostValidateFailed,
    NoSubstantialRowsAfterParse,
)


def convert_md_tables_to_xlsx(
    input_path: str | Path, output_path: str | Path, **kwargs: object,
) -> int:
    """Programmatic entry point. Mirrors `convert_json_to_xlsx`
    semantics: routes through argparse so the same flag-handling
    code runs for both CLI and library callers.

    `kwargs` keys become long-form flags (`{"no_freeze": True}` →
    `--no-freeze`; `{"sheet_prefix": "Report"}` →
    `--sheet-prefix=Report`). Boolean `True` appends just the flag;
    any other type uses the `--flag=value` single-token form so a
    kwarg value that happens to begin with `--` (e.g.
    `sheet_prefix="--evil-flag-attempt"`) is NOT swallowed as a
    separate flag — VDD-multi Logic M4 lock inherited from xlsx-2.

    Returns the same exit code `main` would have returned.
    """
    argv: list[str] = [str(input_path), str(output_path)]
    for key, value in kwargs.items():
        # vdd-multi M6 review-fix: skip None values — caller convention
        # is `sheet_prefix=None` means "use default heading-based
        # naming", NOT "literal sheet name 'None'".
        if value is None:
            continue
        flag = "--" + key.replace("_", "-")
        if isinstance(value, bool):
            if value:
                argv.append(flag)
        else:
            # `--flag=value` is atomic to argparse; leading `--` in
            # `value` cannot poison the parse.
            argv.append(f"{flag}={value}")
    return main(argv)


__all__ = [
    "build_parser",
    "main",
    "_run",
    "convert_md_tables_to_xlsx",
    "_AppError",
    "EmptyInput",
    "NoTablesFound",
    "MalformedTable",
    "InputEncodingError",
    "InvalidSheetName",
    "SelfOverwriteRefused",
    "PostValidateFailed",
    "NoSubstantialRowsAfterParse",
]

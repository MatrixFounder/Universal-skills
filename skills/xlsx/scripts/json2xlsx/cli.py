"""xlsx-2 argparse surface (F5) + linear orchestrator (F7).

Imports the cross-5 envelope helper from `_errors` (the 4-skill
replicated module at `scripts/_errors.py`). The shim
(`json2xlsx.py`) inserts `scripts/` into `sys.path` before importing
the package, so the `from _errors import …` line below resolves at
package-load time.

AQ-2 closure: the `input` positional's help text and the module
description together document the deterministic auto-detection rule
(`.jsonl` extension → JSONL; else dispatch on JSON root token).

AQ-3 closure: a single top-of-`_run` `except _AppError` catch routes
every typed taxonomy error through `_errors.report_error` — xlsx-2
NEVER constructs the envelope dict by hand.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _errors import add_json_errors_argument, report_error  # type: ignore[import-not-found]

from .cli_helpers import (
    assert_distinct_paths,
    post_validate_enabled,
    run_post_validate,
)
from .coerce import CoerceOptions
from .exceptions import _AppError
from .loaders import detect_and_parse, read_input
from .writer import write_workbook


_DESCRIPTION = (
    "Convert JSON / JSONL input into a styled .xlsx workbook. "
    "Three input shapes are auto-detected: array-of-objects "
    "(single sheet), dict-of-arrays-of-objects (multi-sheet), and "
    "JSONL (one JSON object per line — auto-detected via .jsonl "
    "extension; the JSON root token disambiguates the other two)."
)


def build_parser() -> argparse.ArgumentParser:
    """All 8 R9 flags. `--input-format` is intentionally absent (D6)."""
    p = argparse.ArgumentParser(
        prog="json2xlsx.py",
        description=_DESCRIPTION,
    )
    p.add_argument(
        "input", type=str,
        help=(
            "Source JSON / JSONL file (or '-' for stdin). "
            "JSONL auto-detected via .jsonl extension; otherwise "
            "the JSON root token (list vs dict) dispatches the shape."
        ),
    )
    p.add_argument("output", type=Path, help="Destination .xlsx file.")
    p.add_argument(
        "--sheet", default=None,
        help=(
            "Single-sheet name override (default: 'Sheet1'). Ignored "
            "for multi-sheet inputs with a stderr warning."
        ),
    )
    p.add_argument(
        "--no-freeze", action="store_true",
        help="Do not freeze the header row.",
    )
    p.add_argument(
        "--no-filter", action="store_true",
        help="Do not add an auto-filter over the data range.",
    )
    p.add_argument(
        "--no-date-coerce", action="store_true",
        help=(
            "Disable ISO-8601 date-string coercion to Excel datetime "
            "cells. Strings stay as text."
        ),
    )
    p.add_argument(
        "--date-format", default=None, metavar="NUMBER_FORMAT",
        help=(
            "Override the Excel number_format applied to coerced "
            "date cells (e.g. 'DD/MM/YYYY'). Applies uniformly to "
            "both date and datetime cells."
        ),
    )
    p.add_argument(
        "--strict-dates", action="store_true",
        help=(
            "Under --strict-dates, timezone-aware datetime strings "
            "AND invalid date-looking strings (YYYY- prefixed) "
            "hard-fail with exit 2 instead of silent fallback."
        ),
    )
    p.add_argument(
        "--encoding", default="utf-8",
        help=(
            "Input file encoding (default: utf-8). Ignored when "
            "input is '-' (stdin always read as UTF-8 bytes)."
        ),
    )
    add_json_errors_argument(p)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    """Linear pipeline (F7).

    Order is load-bearing:
      1. same-path guard (cheap; before reading 100K rows of JSONL)
      2. read_input (file or stdin)
      3. detect_and_parse (shape dispatch)
      4. multi-sheet --sheet warning
      5. write_workbook (F4)
      6. optional post-validate hook

    Single top-of-function `_AppError` catch (AQ-3 lock) routes every
    taxonomy error through `_errors.report_error`. Platform-IO errors
    (`FileNotFoundError` / `OSError`) are surfaced via ad-hoc
    `report_error(error_type="FileNotFound"|"IOError", ...)` calls per
    the PLAN.md platform-IO policy.
    """
    je: bool = args.json_errors

    try:
        # 1. Same-path guard (skipped when input is stdin '-').
        assert_distinct_paths(args.input, args.output)

        # 2. Read raw bytes.
        try:
            raw, source = read_input(args.input, args.encoding)
        except FileNotFoundError as exc:
            return report_error(
                f"Input not found: {exc}",
                code=1, error_type="FileNotFound",
                details={"path": str(args.input)}, json_mode=je,
            )
        except OSError as exc:
            return report_error(
                f"Failed to read input: {exc}",
                code=1, error_type="IOError",
                details={"path": str(args.input)}, json_mode=je,
            )

        # 3. Detect & parse.
        is_jsonl = args.input != "-" and args.input.endswith(".jsonl")
        parsed = detect_and_parse(raw, source, is_jsonl_hint=is_jsonl)

        # 4. R7.d: multi-sheet input ignores --sheet, warn loudly.
        if parsed.shape == "multi_sheet_dict" and args.sheet is not None:
            sys.stderr.write(
                "--sheet ignored when JSON root is multi-sheet dict.\n"
            )
        sheet_override = (
            args.sheet if parsed.shape != "multi_sheet_dict" else None
        )

        # 5. Build CoerceOptions from flags.
        coerce_opts = CoerceOptions(
            date_coerce=not args.no_date_coerce,
            strict_dates=args.strict_dates,
            date_format_override=args.date_format,
        )

        # 6. Write workbook.
        try:
            write_workbook(
                parsed, args.output,
                freeze=not args.no_freeze,
                auto_filter=not args.no_filter,
                sheet_override=sheet_override,
                coerce_opts=coerce_opts,
            )
        except OSError as exc:
            # VDD-multi Logic M2 fix: openpyxl's `wb.save()` writes the
            # output zip incrementally. A mid-save OSError (disk full,
            # revoked write permission) leaves a partial / corrupt
            # .xlsx on disk that downstream pipelines may mistakenly
            # consume. Clean up the partial file before surfacing the
            # envelope. Mirrors the post-validate cleanup pattern.
            if args.output.exists():
                try:
                    args.output.unlink()
                except OSError:
                    pass
            return report_error(
                f"Failed to write output: {exc}",
                code=1, error_type="IOError",
                details={"path": str(args.output)}, json_mode=je,
            )

        # 7. Optional post-validate hook.
        if post_validate_enabled():
            passed, hook_ok, captured = run_post_validate(args.output)
            if not passed:
                # VDD-multi Logic H1 fix: only unlink the workbook when
                # the validator ran to completion AND reported a real
                # workbook problem. If `hook_ok=False` (validator
                # missing / timed out / crashed), the workbook itself
                # is presumed valid; emit the envelope but DO NOT
                # delete the user's output.
                if hook_ok:
                    try:
                        args.output.unlink()
                    except OSError:
                        pass
                    err_type = "PostValidateFailed"
                    err_msg = "Post-validate hook failed"
                else:
                    err_type = "PostValidateHookError"
                    err_msg = (
                        "Post-validate hook could not run "
                        "(validator missing or timed out); "
                        "workbook left intact"
                    )
                return report_error(
                    err_msg,
                    code=7, error_type=err_type,
                    details={"validator_output": captured[:8192]},
                    json_mode=je,
                )

    except _AppError as exc:
        return report_error(
            exc.message,
            code=exc.code, error_type=exc.error_type,
            details=exc.details, json_mode=je,
        )

    return 0


__all__ = [
    "build_parser",
    "main",
    "_run",
]

"""xlsx-3 F9 — argparse + main + linear pipeline orchestrator.

task-005-09: full `_run` linear pipeline + post-validate hook
wiring. `build_parser` is locked at exactly 8 user-facing flags
(TASK §9). `main` wraps `_run` in cross-5 envelope catches.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _errors import add_json_errors_argument, report_error

from .cli_helpers import (
    assert_distinct_paths,
    post_validate_enabled,
    run_post_validate,
)
from .coerce import CoerceOptions, coerce_column
from .exceptions import (
    EmptyInput,
    InputEncodingError,
    NoTablesFound,
    SelfOverwriteRefused,
    _AppError,
)
from .loaders import (
    Heading,
    HtmlTable,
    PipeTable,
    iter_blocks,
    read_input,
    scrub_fenced_and_comments,
)
from .naming import SheetNameResolver
from .tables import parse_table
from .writer import ParsedTable, WriterOptions, write_workbook


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse surface. Locked at 8 flags per TASK §9."""
    parser = argparse.ArgumentParser(
        description=(
            "Convert markdown tables to a multi-sheet .xlsx workbook. "
            "Two table flavors auto-detected: GFM pipe tables (with "
            "per-column alignment) and HTML <table> blocks (with "
            "colspan/rowspan as merged cells). Sheet names derive "
            "from the nearest preceding heading; fallback Table-N."
        ),
    )
    parser.add_argument(
        "input",
        help="Path to .md/.markdown file, or '-' for stdin",
    )
    parser.add_argument(
        "output",
        type=Path,
        help="Destination .xlsx file",
    )
    parser.add_argument(
        "--no-coerce", action="store_true",
        help="Disable numeric / ISO-date coercion (force all cells to text)",
    )
    parser.add_argument(
        "--no-freeze", action="store_true",
        help="Disable freeze pane on header row",
    )
    parser.add_argument(
        "--no-filter", action="store_true",
        help="Disable auto-filter over data range",
    )
    parser.add_argument(
        "--allow-empty", action="store_true",
        help=(
            "When zero tables found, write an empty workbook (exit 0) "
            "instead of exit 2 NoTablesFound"
        ),
    )
    parser.add_argument(
        "--sheet-prefix", default=None,
        help="Override heading-based sheet naming with sequential STR-1, STR-2, ...",
    )
    parser.add_argument(
        "--encoding", default="utf-8",
        help="Input file encoding (default: utf-8; markdown is canonically UTF-8)",
    )
    add_json_errors_argument(parser)
    return parser


def _post_validate_or_zero(output: Path) -> int:
    """If XLSX_MD_TABLES_POST_VALIDATE=1 → run validator (may raise).
    Otherwise return 0 immediately.
    """
    if post_validate_enabled():
        run_post_validate(output)  # may raise PostValidateFailed (code 7)
    return 0


def _run(args) -> int:
    """Linear pipeline F1 → F2 → F3/F4 → F5 → F6 → F7 → F8 → F10."""
    # 1. Read input (file or stdin).
    try:
        text, source_label = read_input(args.input, encoding=args.encoding)
    except UnicodeDecodeError as exc:
        raise InputEncodingError(
            f"Input is not valid UTF-8: {exc}",
            code=2,
            error_type="InputEncodingError",
            details={"source": args.input, "offset": getattr(exc, "start", 0)},
        )

    if not text.strip():
        raise EmptyInput(
            f"Input is empty: {source_label}",
            code=2,
            error_type="EmptyInput",
            details={"source": source_label},
        )

    # 2. Pre-scan strip (fenced + comments + indented + style/script).
    scrubbed, _dropped_regions = scrub_fenced_and_comments(text)

    # 3. Iterate blocks; collect (heading, table) pairs in document order.
    pairs: list[tuple[Heading | None, object]] = []
    last_heading: Heading | None = None
    for block in iter_blocks(scrubbed):
        if isinstance(block, Heading):
            last_heading = block
        elif isinstance(block, (PipeTable, HtmlTable)):
            pairs.append((last_heading, block))

    if not pairs:
        if args.allow_empty:
            write_workbook(
                [], args.output,
                WriterOptions(
                    freeze=not args.no_freeze,
                    auto_filter=not args.no_filter,
                    sheet_prefix=args.sheet_prefix,
                    allow_empty=True,
                ),
            )
            return _post_validate_or_zero(args.output)
        raise NoTablesFound(
            f"No tables found in {source_label}",
            code=2,
            error_type="NoTablesFound",
            details={"source": source_label},
        )

    # 4. Parse each table; skip None (malformed-GFM emitted stderr warning).
    resolver = SheetNameResolver(sheet_prefix=args.sheet_prefix)
    parsed_tables: list[ParsedTable] = []
    coerce_opts = CoerceOptions(coerce=not args.no_coerce)
    for heading, block in pairs:
        raw = parse_table(block)
        if raw is None:
            continue
        sheet_name = resolver.resolve(heading.text if heading else None)
        # Coerce each column: gather column-strings, run coerce_column.
        coerced_cols: list[list[object]] = []
        for c in range(len(raw.header)):
            col_strings = [
                (row[c] if c < len(row) and row[c] is not None else "")
                for row in raw.rows
            ]
            coerced_cols.append(coerce_column(col_strings, coerce_opts))
        parsed_tables.append(ParsedTable(
            raw=raw, sheet_name=sheet_name, coerced_columns=coerced_cols,
        ))

    # 5. Handle the "all-malformed" edge case.
    if not parsed_tables:
        if args.allow_empty:
            write_workbook(
                [], args.output,
                WriterOptions(
                    freeze=not args.no_freeze,
                    auto_filter=not args.no_filter,
                    sheet_prefix=args.sheet_prefix,
                    allow_empty=True,
                ),
            )
            return _post_validate_or_zero(args.output)
        raise NoTablesFound(
            f"No valid tables found in {source_label} (all skipped as malformed)",
            code=2,
            error_type="NoTablesFound",
            details={"source": source_label},
        )

    # 6. Write workbook.
    write_workbook(
        parsed_tables, args.output,
        WriterOptions(
            freeze=not args.no_freeze,
            auto_filter=not args.no_filter,
            sheet_prefix=args.sheet_prefix,
            allow_empty=args.allow_empty,
        ),
    )

    # 7. Post-validate hook (opt-in via env).
    return _post_validate_or_zero(args.output)


def main(argv: list[str] | None = None) -> int:
    """argparse entrypoint. Wraps `_run` with cross-5 envelope catch."""
    raw_argv = argv if argv is not None else sys.argv[1:]
    json_mode = any(
        (a == "--json-errors" or a.startswith("--json-errors="))
        for a in raw_argv
    )
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # vdd-multi M5 review-fix: `SystemExit(None)` (rare: `sys.exit()`
        # with no arg) conventionally means "clean exit 0".
        if exc.code in (0, None):
            return 0
        return report_error(
            "Invalid command-line arguments (see --help)",
            code=2,
            error_type="UsageError",
            json_mode=json_mode,
        )

    # vdd-multi H2 review-fix: widen catch to OSError so `Path.resolve()`
    # failures (symlink loop, ENAMETOOLONG, weird /proc entries) route
    # through the cross-5 envelope instead of escaping as bare traceback.
    try:
        assert_distinct_paths(args.input, args.output)
    except SelfOverwriteRefused as exc:
        return report_error(
            exc.message,
            code=exc.code,
            error_type=exc.error_type,
            details=exc.details,
            json_mode=args.json_errors,
        )
    except OSError as exc:
        return report_error(
            f"Path resolution failed: {exc}",
            code=1,
            error_type="IOError",
            details={"path": getattr(exc, "filename", None)},
            json_mode=args.json_errors,
        )

    try:
        return _run(args)
    except _AppError as exc:
        return report_error(
            exc.message,
            code=exc.code,
            error_type=exc.error_type,
            details=exc.details,
            json_mode=args.json_errors,
        )
    except FileNotFoundError as exc:
        return report_error(
            f"Input not found: {exc.filename}",
            code=1,
            error_type="FileNotFound",
            details={"path": exc.filename},
            json_mode=args.json_errors,
        )
    except OSError as exc:
        return report_error(
            f"I/O error: {exc}",
            code=1,
            error_type="IOError",
            details={"path": getattr(exc, "filename", None)},
            json_mode=args.json_errors,
        )

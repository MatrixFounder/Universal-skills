"""F1 — CLI argparse + dispatch.

This module owns the **entire** CLI surface for both ``xlsx2csv.py``
and ``xlsx2json.py``. The two shims pass ``format_lock="csv"`` or
``format_lock="json"`` to :func:`main`; when ``format_lock`` is set,
``--format`` is added as a hidden argument whose only legal value is
the locked format (any other value raises :class:`FormatLockedByShim`
at parse time per ARCH D-A4).

Layers:

* :func:`build_parser` — argparse construction; locked flag table
  per ARCH §5.1.
* :func:`_validate_flag_combo` — parse-time cross-flag invariants
  (HeaderRowsConflict, MultiSheetRequiresOutputDir). Cases requiring
  workbook inspection (region count) are deferred to
  :mod:`dispatch`.
* :func:`_resolve_paths` — canonical-resolve INPUT, ``--output``,
  ``--output-dir``; cross-7 H1 same-path guard.
* :func:`_run_with_envelope` — exception → cross-5 envelope mapping
  table.
* :func:`_dispatch_to_emit` — open workbook, drive
  :func:`dispatch.iter_table_payloads`, hand off to
  :func:`emit_json.emit_json` or :func:`emit_csv.emit_csv`.
* :func:`main` — top-level orchestrator.
"""
from __future__ import annotations

import argparse
import sys
import warnings
import zipfile
from pathlib import Path
from typing import Any, Callable

# _errors lives at scripts/ root (4-skill replicated). Shims insert
# scripts/ into sys.path before importing the package; tests do the
# same via tests/test_*.py boilerplate.
import _errors  # type: ignore[import-untyped]

from .exceptions import (
    _AppError,
    FormatLockedByShim,
    HeaderRowsConflict,
    MultiSheetRequiresOutputDir,
    PostValidateFailed,
    SelfOverwriteRefused,
)

_TABLES_MODES = ("whole", "listobjects", "gap", "auto")
_MERGE_POLICIES = ("anchor-only", "fill", "blank")
_DATETIME_FORMATS = ("ISO", "excel-serial", "raw")
_HEADER_FLATTEN_STYLES = ("string", "array")
_VALID_FORMATS = ("csv", "json")

# xlsx-8a-11 (R13) — `--memory-mode` exposes openpyxl streaming mode
# choice to the CLI. Default `auto` preserves the existing
# size-threshold behaviour (`_DEFAULT_READ_ONLY_THRESHOLD = 100 MiB`
# in `xlsx_read._workbook`). `streaming` forces `read_only=True`
# (lower RAM, merge-aware features no-op per R12 honest-scope).
# `full` forces `read_only=False` (correct merges, RAM unbounded
# by file size).
_MEMORY_MODES = ("auto", "streaming", "full")

# xlsx-8a-04 (R4, Sec-MED-1) — `--escape-formulas` modes.
_ESCAPE_FORMULAS_MODES = ("off", "quote", "strip")
# OWASP-canonical CSV-injection sentinels (D-A13). Cell values
# whose stringified form starts with one of these are treated by
# Excel-on-double-click as DDE formulas. Unicode lookalikes (e.g.
# `＝` U+FF1D fullwidth equals) are explicitly out of scope here.
_FORMULA_SENTINELS = ("=", "+", "-", "@", "\t", "\r")


# ===========================================================================
# Argparse
# ===========================================================================
def _header_rows_type(value: str) -> Any:
    """Custom type for ``--header-rows``. Accepts ``"auto"``,
    ``"leaf"``, ``"smart"``, or a non-negative integer.

    Returns:
      - ``"auto"`` (str) — auto-detect the header band via merge-cell
        structure; concatenate all levels with ` › ` separator (R7).
      - ``"leaf"`` (str) — auto-detect the band, but keep ONLY the
        deepest non-empty level per column as the header key. Drops
        merged metadata-banner levels above the real column-name row
        on layout-heavy reports with merge cells.
      - ``"smart"`` (str, xlsx-8a-09 / R11; iter-3 2026-05-13) —
        type-pattern heuristic, "find-the-data-table" recipe.
        Scores each top row by `string_ratio + 1.5×coverage +
        2×stability + 0.5×depth` (max 5.0); when a candidate scores
        ≥ 3.5 AND has ≥ 2 sample rows below, the library shifts
        the region past the metadata block and treats the candidate
        as a 1-row header. **Does NOT defer to merge-based
        detection** — competes purely on score. On merged-banner
        fixtures, ``smart`` shifts to the sub-header row (leaf-like
        keys); callers needing merge-concatenated multi-level
        headers must use ``"auto"`` or ``"leaf"``.
      - ``int >= 0`` — explicit fixed header-row count.
    """
    if value == "auto":
        return "auto"
    if value == "leaf":
        return "leaf"
    if value == "smart":
        return "smart"
    try:
        n = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--header-rows must be 'auto', 'leaf', 'smart', or a "
            f"non-negative integer, got {value!r}"
        ) from exc
    if n < 0:
        raise argparse.ArgumentTypeError(
            f"--header-rows must be non-negative, got {n}"
        )
    return n


def _format_type_with_lock(format_lock: str | None) -> Callable[[str], str]:
    """Build a type validator for ``--format`` that raises
    :class:`FormatLockedByShim` when the user supplies a value differing
    from the shim's hard-bound format.
    """
    def _validator(value: str) -> str:
        if value not in _VALID_FORMATS:
            raise argparse.ArgumentTypeError(
                f"--format must be one of {_VALID_FORMATS}, got {value!r}"
            )
        if format_lock is not None and value != format_lock:
            raise FormatLockedByShim(
                f"This shim hard-binds --format={format_lock!r}; "
                f"got --format={value!r}"
            )
        return value
    return _validator


def _parse_scheme_allowlist(csv: str) -> frozenset[str]:
    """Parse the ``--hyperlink-scheme-allowlist`` CSV value.

    xlsx-8a-03 (R3, D-A11/A12): comma-separated list of allowed
    URL schemes. Whitespace stripped; case-folded to lower (RFC
    3986 §3.1 — scheme matching is case-insensitive). Empty
    entries dropped. Empty input → ``frozenset()`` (blocks ALL
    schemes).
    """
    return frozenset(
        s.strip().lower() for s in csv.split(",") if s.strip()
    )


def _delimiter_type(value: str) -> str:
    """Argparse `type=` callable for `--delimiter`.

    Accepts:
      - Literal characters: ``,`` ``;``  (passed through unchanged)
      - Symbolic aliases: ``tab`` → ``\\t``; ``pipe`` → ``|``
      - 2-char escape: ``\\t`` (literal backslash+t, useful when the
        shell can't easily emit a raw tab) → ``\\t``

    Returns the literal single-char delimiter ready for ``csv.writer``.
    Any other input raises ``argparse.ArgumentTypeError`` (which
    argparse renders as exit-2 with a usage error envelope).
    """
    canonical = {",": ",", ";": ";", "tab": "\t", "\\t": "\t", "pipe": "|"}
    if value in canonical:
        return canonical[value]
    raise argparse.ArgumentTypeError(
        f"--delimiter must be one of: ',', ';', 'tab' (or '\\t'), 'pipe'; "
        f"got {value!r}"
    )


def build_parser(*, format_lock: str | None) -> argparse.ArgumentParser:
    """Construct the argparse surface.

    When ``format_lock`` is set, ``--format`` is suppressed from
    ``--help`` (the shim documents the bound format in its own
    docstring) but is still parseable so the FormatLockedByShim guard
    can fire.
    """
    prog = "xlsx2csv2json"
    if format_lock == "csv":
        prog = "xlsx2csv.py"
    elif format_lock == "json":
        prog = "xlsx2json.py"

    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Convert an .xlsx workbook into CSV or JSON. "
            "Thin CLI on top of the xlsx-10.A xlsx_read foundation."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "input",
        metavar="INPUT",
        help="Path to the .xlsx / .xlsm workbook to read.",
    )
    parser.add_argument(
        "output",
        metavar="OUTPUT",
        nargs="?",
        default=None,
        help="Output file path. '-' for stdout (default if omitted).",
    )

    # --format with hard-binding. Always present so the FormatLockedByShim
    # guard can fire if the user passes a value through the shim.
    parser.add_argument(
        "--format",
        choices=_VALID_FORMATS if format_lock is None else None,
        default=format_lock,
        type=_format_type_with_lock(format_lock) if format_lock else None,
        help=(
            argparse.SUPPRESS
            if format_lock is not None
            else "Output format ('csv' or 'json')."
        ),
    )

    parser.add_argument(
        "--output",
        dest="output_flag",
        default=None,
        help="Alternative to the positional OUTPUT. Mutually exclusive.",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default=None,
        help="Directory for multi-region CSV layout (<dir>/<sheet>/<table>.csv).",
    )
    parser.add_argument(
        "--sheet",
        default="all",
        help="Sheet name to extract, or 'all' (default).",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden + veryHidden sheets (default: skip).",
    )
    parser.add_argument(
        "--header-rows",
        dest="header_rows",
        # M1 (vdd-multi): default is None to distinguish "user accepted
        # the default" from "user explicitly typed --header-rows 1".
        # _validate_flag_combo then materialises: when `--tables == whole`,
        # None → 1 (single-row header backward-compat); when
        # `--tables != whole`, None → "auto" (per-table detection).
        default=None,
        type=_header_rows_type,
        help=(
            "Header row count: 'auto', 'leaf', 'smart', or a "
            "non-negative int. 'auto' = merge-based detection (default). "
            "'leaf' = auto + keep deepest level per column (drops merged "
            "metadata banners). 'smart' (xlsx-8a-09) = type-pattern "
            "heuristic that locates the data table even WITHOUT merges, "
            "skipping unmerged metadata blocks above (e.g. config rows "
            "with parameters above the real column-name row). Defaults "
            "to 1 when --tables=whole; 'auto' otherwise."
        ),
    )
    parser.add_argument(
        "--header-flatten-style",
        dest="header_flatten_style",
        choices=_HEADER_FLATTEN_STYLES,
        default="string",
        help="JSON only: flat 'string' or 'array' keys for multi-row headers.",
    )
    parser.add_argument(
        "--merge-policy",
        dest="merge_policy",
        choices=_MERGE_POLICIES,
        default="anchor-only",
        help="Body merge policy.",
    )
    parser.add_argument(
        "--tables",
        choices=_TABLES_MODES,
        default="whole",
        help="Table detection mode.",
    )
    parser.add_argument(
        "--gap-rows",
        dest="gap_rows",
        type=int,
        default=2,
        help="Gap-detect threshold for empty rows.",
    )
    parser.add_argument(
        "--gap-cols",
        dest="gap_cols",
        type=int,
        default=1,
        help="Gap-detect threshold for empty columns.",
    )
    parser.add_argument(
        "--include-hyperlinks",
        action="store_true",
        dest="include_hyperlinks",
        help="Emit hyperlink targets (JSON dict-form, CSV markdown-form).",
    )
    parser.add_argument(
        "--include-formulas",
        action="store_true",
        dest="include_formulas",
        help="Emit formula strings instead of cached values.",
    )
    parser.add_argument(
        "--datetime-format",
        dest="datetime_format",
        choices=_DATETIME_FORMATS,
        default="ISO",
        help="Datetime rendering.",
    )
    parser.add_argument(
        "--encoding",
        dest="encoding",
        choices=("utf-8", "utf-8-sig"),
        default="utf-8",
        help=(
            "Output text encoding (CSV only). 'utf-8-sig' prepends a "
            "UTF-8 BOM so Excel on Windows / macOS auto-detects the "
            "charset; pandas, jq and other downstream tools that pin "
            "the first header cell may misread BOM as part of the "
            "value, so the default is plain 'utf-8'."
        ),
    )
    parser.add_argument(
        "--delimiter",
        dest="delimiter",
        type=_delimiter_type,
        default=",",
        metavar="DELIM",
        help=(
            "CSV field delimiter. Accepts: ',' (default), ';', 'tab' "
            "(or the 2-char escape '\\\\t'), 'pipe'. On RU / EU Excel "
            "locales (where ',' is the decimal separator), pass ';' "
            "so a double-click open parses into columns instead of "
            "stuffing every row into column A. The reverse-side "
            "csv2xlsx.py accepts the same set (plus literal `\\t` "
            "for legacy callers); the round-trip pair is symmetric."
        ),
    )
    parser.add_argument(
        "--drop-empty-rows",
        dest="drop_empty_rows",
        action="store_true",
        help=(
            "Skip rows where every value is None or empty string. "
            "Layout-heavy reports (mostly-blank separator rows, "
            "trailing empties left by Excel after row deletion) "
            "produce noisy mostly-null JSON dict blobs / blank CSV "
            "lines by default; this flag drops them. Conservative: "
            "only ALL-empty rows are dropped — rows with at least "
            "one non-null cell are preserved (e.g. a signature row "
            "with `A=Подпись, F=Подпись` survives). Default: off "
            "(preserves the source row count 1:1)."
        ),
    )

    # xlsx-8a-03 (R3, Sec-MED-2) — URL-scheme allowlist for hyperlinks.
    parser.add_argument(
        "--hyperlink-scheme-allowlist",
        dest="hyperlink_scheme_allowlist",
        default="http,https,mailto",
        metavar="CSV",
        help=(
            "Comma-separated list of allowed URL schemes for "
            "hyperlink cells. Disallowed-scheme hyperlinks drop "
            "to the no-hyperlink emit branch (JSON: bare scalar "
            "value; CSV: plain text). One stderr warning per "
            "distinct blocked scheme (deduped). Default: "
            "'http,https,mailto' (covers typical office workbook "
            "schemes). Pass an empty string to block ALL schemes. "
            "Case-insensitive per RFC 3986 §3.1."
        ),
    )

    # xlsx-8a-11 (R13) — openpyxl streaming-mode opt-in.
    parser.add_argument(
        "--memory-mode",
        dest="memory_mode",
        choices=_MEMORY_MODES,
        default="auto",
        help=(
            "Read-mode selection. 'auto' (default) lets the library "
            "pick based on file size threshold. 'streaming' minimizes "
            "RAM at the cost of merge-aware features (overlap "
            "detection, merge-policy fill, multi-row header band via "
            "merges) becoming no-ops — use on workbooks without "
            "merges OR where merge fidelity does not matter. "
            "'full' forces non-streaming — all merge features work, "
            "RAM scales ~10× with file size. Measured on a 15 MB "
            "multi-sheet workbook 2026-05-13: 'streaming' delivered "
            "7.6× RAM reduction (1188 MB → 156 MB) plus 2.6× "
            "wall-clock speedup vs 'full'. NOTE: "
            "`--include-hyperlinks` forces 'full' (a stderr warning "
            "fires if you also requested 'streaming') because "
            "hyperlink extraction needs the non-streaming cell "
            "object."
        ),
    )

    # xlsx-8a-04 (R4, Sec-MED-1) — CSV formula-injection defang.
    parser.add_argument(
        "--escape-formulas",
        dest="escape_formulas",
        choices=_ESCAPE_FORMULAS_MODES,
        default="off",
        help=(
            "Defang CSV cells starting with =/+/-/@/<TAB>/<CR> "
            "(OWASP CSV Injection). 'off' (default) passes through "
            "verbatim — backward-compatible. 'quote' prepends `'` "
            "so Excel renders as literal text. 'strip' replaces "
            "with empty string. CSV-only: passing to xlsx2json.py "
            "emits a stderr warning. See also --encoding utf-8-sig "
            "(both flags address 'what happens when Excel "
            "double-clicks the CSV')."
        ),
    )

    # Cross-5 envelope flag (4-skill replicated helper).
    _errors.add_json_errors_argument(parser)

    return parser


def _validate_flag_combo(args: argparse.Namespace, *, format_lock: str | None) -> None:
    """Run cross-flag invariants that don't need the workbook open.

    Raises:
        HeaderRowsConflict: ``--header-rows N`` (int) AND
            ``--tables != whole`` (TASK §R7.e).
        MultiSheetRequiresOutputDir: ``format_lock == "csv"`` AND
            ``--sheet all`` AND no ``--output-dir`` (TASK §R12.f).
            Conservative pre-check; ``dispatch`` refines after sheet
            enumeration in case the workbook actually has 1 visible
            sheet only.
    """
    # M1 (vdd-multi): materialise the --header-rows default per --tables mode.
    # `None` (not user-set) → 1 when --tables=whole; "auto" otherwise.
    if args.header_rows is None:
        args.header_rows = 1 if args.tables == "whole" else "auto"

    # H3 conflict applies only to EXPLICIT int values (user typed an int)
    # under a multi-table mode. Implicit defaults are now mode-aware and
    # never trigger this.
    if (
        isinstance(args.header_rows, int)
        and args.tables != "whole"
    ):
        raise HeaderRowsConflict(
            "Multi-table layouts require --header-rows auto "
            "(per-table header counts may differ)."
        )

    effective_format = format_lock or args.format
    if effective_format == "csv":
        # Reject ambiguous "--output OUT" + "OUTPUT" combo for CSV
        # without --output-dir.
        if (
            args.sheet == "all"
            and args.output_dir is None
            and args.output is None
            and args.output_flag is None
        ):
            # stdout multi-sheet CSV not possible — but only fail-loud
            # if the workbook actually has > 1 visible sheet. The
            # parse-time check is best-effort; defer the real raise to
            # `dispatch` after sheet enumeration.
            pass
        elif (
            args.sheet == "all"
            and args.output_dir is None
            and (args.output == "-" or args.output_flag == "-")
        ):
            # Explicit "-" for stdout with --sheet all → multiplex impossible.
            raise MultiSheetRequiresOutputDir(
                "CSV cannot multiplex multiple sheets into a single stream. "
                "Use --output-dir or --sheet <NAME>."
            )

    # **vdd-multi-2 MED fix:** `--encoding utf-8-sig` only affects CSV
    # file output; JSON emit hardcodes plain UTF-8 (no BOM convention
    # for JSON per RFC 8259). Surface a stderr warning so the user
    # isn't silently surprised when they expect BOM on a .json file.
    if effective_format == "json" and args.encoding == "utf-8-sig":
        print(
            "warning: --encoding utf-8-sig has no effect on JSON output "
            "(JSON files are written as plain UTF-8 per RFC 8259).",
            file=sys.stderr,
        )

    # **vdd-adversarial R26 HIGH-2 fix:** `--delimiter` is CSV-only. JSON
    # has its own structural separators (no field-delimiter concept).
    # Mirror the encoding-warning pattern above so the user knows their
    # flag was parsed but ignored.
    if effective_format == "json" and args.delimiter != ",":
        print(
            "warning: --delimiter has no effect on JSON output "
            "(JSON uses its own structural separators).",
            file=sys.stderr,
        )

    # **vdd-multi-3 Logic-LOW-1 fix:** `--encoding utf-8-sig` is silently
    # ignored when CSV output goes to stdout (the BOM-bytes-into-a-pipe
    # case is almost always a downstream-consumer bug, so emit_csv
    # deliberately drops the BOM there — see `_emit_single_region`).
    # Surface a stderr warning so the user isn't silently surprised
    # when they pipe CSV through `tee out.csv` and find no BOM.
    csv_stdout = (
        effective_format == "csv"
        and args.output_dir is None
        and args.output_flag in (None, "-")
        and args.output in (None, "-")
    )
    if csv_stdout and args.encoding == "utf-8-sig":
        print(
            "warning: --encoding utf-8-sig has no effect on stdout CSV "
            "output (BOM is dropped to avoid breaking piped consumers). "
            "Pass --output FILE.csv to get a BOM-prefixed file.",
            file=sys.stderr,
        )

    # xlsx-8a-04 (R4): `--escape-formulas` is CSV-only.
    if effective_format == "json" and args.escape_formulas != "off":
        print(
            "warning: --escape-formulas has no effect on JSON output "
            "(CSV-only flag — JSON has its own escape contract).",
            file=sys.stderr,
        )


# ===========================================================================
# Path resolution (010-02)
# ===========================================================================
def _resolve_paths(
    input_arg: str,
    output_arg: str | None,
    output_dir_arg: str | None,
) -> tuple[Path, Path | None, Path | None]:
    """Canonical-resolve INPUT, ``--output``, ``--output-dir``.

    See 010-02 for full semantics. Briefly:

    * INPUT is resolved with ``strict=True`` (FileNotFoundError on miss).
    * Output paths auto-create parents.
    * Output ``"-"`` or ``None`` means stdout.
    * Cross-7 H1 same-path guard fires after symlink-follow.
    """
    resolved_input = Path(input_arg).resolve(strict=True)

    if output_arg in (None, "-"):
        resolved_output: Path | None = None
    else:
        candidate = Path(output_arg)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        resolved_output = candidate.resolve()
        if resolved_output == resolved_input:
            raise SelfOverwriteRefused(
                f"Refusing to overwrite input: {resolved_input.name}"
            )

    if output_dir_arg is None:
        resolved_output_dir: Path | None = None
    else:
        candidate_dir = Path(output_dir_arg)
        candidate_dir.mkdir(parents=True, exist_ok=True)
        resolved_output_dir = candidate_dir.resolve()

    return resolved_input, resolved_output, resolved_output_dir


# ===========================================================================
# Envelope dispatch (010-02)
# ===========================================================================
def _run_with_envelope(
    args: Any,
    *,
    body: Callable[[], int],
) -> int:
    """Execute ``body``; route known exceptions through :func:`_errors.report_error`.

    See 010-02 for the dispatch table.
    """
    json_mode = bool(getattr(args, "json_errors", False))

    from xlsx_read import (
        EncryptedWorkbookError,
        OverlappingMerges,
        SheetNotFound,
        TooManyMerges,
    )

    try:
        return body()
    except FileNotFoundError as exc:
        filename = Path(getattr(exc, "filename", str(exc)) or "").name
        return _errors.report_error(
            f"Input not found: {filename}",
            code=1,
            error_type="FileNotFoundError",
            details={"filename": filename},
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except zipfile.BadZipFile as exc:
        return _errors.report_error(
            f"Input is not a valid OOXML archive: {exc}",
            code=2,
            error_type="BadZipFile",
            details={},
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except EncryptedWorkbookError as exc:
        return _errors.report_error(
            str(exc),
            code=3,
            error_type="EncryptedWorkbookError",
            details=_basename_details(exc),
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except SheetNotFound as exc:
        return _errors.report_error(
            f"Sheet not found: {exc}",
            code=2,
            error_type="SheetNotFound",
            details={"sheet": str(exc)},
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except OverlappingMerges as exc:
        return _errors.report_error(
            str(exc),
            code=2,
            error_type="OverlappingMerges",
            details={},
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except TooManyMerges as exc:
        # xlsx-8a-02 (R2, Sec-MED-3): library raised the cap.
        # Map to exit 2 with basename-only `details` (no path leak).
        return _errors.report_error(
            str(exc),
            code=2,
            error_type="TooManyMerges",
            details={},
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except _AppError as exc:
        return _errors.report_error(
            str(exc),
            code=exc.CODE,
            error_type=type(exc).__name__,
            details=_basename_details(exc),
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except (PermissionError, OSError) as exc:
        # H3 (vdd-multi): I/O errors (read-only filesystem, EACCES,
        # ENOSPC, etc.) previously escaped uncaught and surfaced as
        # Python tracebacks containing absolute paths — defeating the
        # basename-only promise in ARCH §7.2.
        filename = Path(getattr(exc, "filename", "") or "").name
        return _errors.report_error(
            f"I/O error: {filename or type(exc).__name__}",
            code=1,
            error_type=type(exc).__name__,
            details={"filename": filename} if filename else {},
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except Exception as exc:  # noqa: BLE001 — terminal envelope; redact details
        # H3 (vdd-multi): catch-all for any unanticipated exception so
        # the cross-5 envelope contract holds. We DELIBERATELY drop the
        # exception message (which may contain absolute paths from
        # openpyxl / xlsx_read internals) and surface only the class
        # name. Diagnosis path: re-run without `--json-errors` for the
        # raw traceback during local debugging.
        return _errors.report_error(
            f"Internal error: {type(exc).__name__}",
            code=1,
            error_type=type(exc).__name__,
            details={},
            json_mode=json_mode,
            stream=sys.stderr,
        )


def _basename_details(exc: BaseException) -> dict[str, Any]:
    """Extract a basename-only ``details.filename`` from an exception message."""
    msg = str(exc)
    for sep in ("/", "\\"):
        if sep in msg:
            return {"filename": Path(msg.rsplit(sep, 1)[1]).name}
    return {}


def _emit_warnings_to_stderr(captured: list) -> None:
    """Re-emit captured warnings via Python's default formatter (HS-7)."""
    for w in captured:
        warnings.showwarning(w.message, w.category, w.filename, w.lineno)


# ===========================================================================
# Output-arg reconciliation
# ===========================================================================
def _resolve_output_arg(args: argparse.Namespace) -> str | None:
    """Pick the effective output string from positional OUTPUT and --output.

    Mutual exclusivity: the user may supply only one of:

    * positional ``OUTPUT`` (``args.output``),
    * ``--output OUT`` flag (``args.output_flag``).

    If both are present, raise via parser error (caller turns that into
    cross-5 envelope when ``--json-errors`` is on).
    """
    if args.output is not None and args.output_flag is not None:
        raise _AppError(
            "Output specified twice (positional OUTPUT and --output). "
            "Pick one."
        )
    return args.output_flag if args.output_flag is not None else args.output


# ===========================================================================
# Reader-glue trampoline
# ===========================================================================
def _post_validate_json_output(output_path: Path | None) -> None:
    """Env-flag opt-in JSON round-trip via :func:`json.loads`.

    Triggered by ``XLSX_XLSX2CSV2JSON_POST_VALIDATE=1``. On failure
    unlink the output file and raise :class:`PostValidateFailed`
    (exit 7). CSV outputs are NOT validated — CSV has no schema.

    Mirror pattern: xlsx-2 ``XLSX_JSON2XLSX_POST_VALIDATE`` /
    xlsx-3 ``XLSX_MD_TABLES_POST_VALIDATE`` (env-flag opt-in,
    default OFF; ARCH §3.2 C7).
    """
    import json as _json
    import os
    if os.environ.get("XLSX_XLSX2CSV2JSON_POST_VALIDATE") != "1":
        return
    if output_path is None:
        return  # stdout — nothing to re-parse
    try:
        _json.loads(output_path.read_text(encoding="utf-8"))
    except (_json.JSONDecodeError, OSError) as exc:
        try:
            output_path.unlink()
        except OSError:
            pass
        raise PostValidateFailed(
            f"JSON re-parse failed: {output_path.name}"
        ) from exc


def _dispatch_to_emit(
    args: argparse.Namespace,
    effective_format: str,
) -> int:
    """Open workbook, iterate regions via dispatch, hand off to emitter.

    Returns the emitter's exit code (typically 0 on success). Sentinel
    ``-997`` may surface in the stub stage (010-03) when the emit
    bodies are not yet wired — 010-04 wires the reader-glue, 010-05
    wires emit_json, 010-06 wires emit_csv.
    """
    from xlsx_read import open_workbook
    from . import dispatch, emit_csv, emit_json

    output_str = _resolve_output_arg(args)
    input_path, output_path, output_dir = _resolve_paths(
        args.input, output_str, args.output_dir
    )
    # Stash resolved paths on args so dispatch can read them without
    # re-resolving (saves one stat call and keeps the cross-7 guard
    # single-source-of-truth).
    args._resolved_input = input_path  # noqa: SLF001
    args._resolved_output = output_path  # noqa: SLF001
    args._resolved_output_dir = output_dir  # noqa: SLF001

    # C1 (vdd-multi): --include-hyperlinks requires read_only=False.
    # openpyxl's ReadOnlyWorksheet streams cell values from the XML but
    # does NOT expose cell.hyperlink (lives in xl/worksheets/_rels/sheetN.xml.rels).
    # The library auto-selects read_only=True for files > 10 MiB; we override
    # only when hyperlink extraction is requested so the in-memory Cell objects
    # carry the .hyperlink attribute. Memory cost is bounded by the file size;
    # honest-scope: large workbook + --include-hyperlinks may need 5-10x the
    # workbook size in RAM. Caller-controlled flag, so the trade-off is opt-in.
    #
    # **xlsx-8a-11 (R13, 2026-05-13)**: `--memory-mode` exposes the
    # `read_only_mode` selection to the CLI. Translation table:
    #   - `auto`      → `read_only_mode=None` (size-threshold-driven)
    #   - `streaming` → `read_only_mode=True`  (force openpyxl streaming;
    #                   merge-aware features no-op per R12 honest-scope)
    #   - `full`      → `read_only_mode=False` (force non-streaming;
    #                   merges work, RAM unbounded by file size)
    # **Conflict**: `--include-hyperlinks --memory-mode streaming` is
    # structurally impossible (ReadOnlyWorksheet doesn't expose
    # `cell.hyperlink`). Emit a stderr warning and override to `full`
    # — matches the existing `--include-hyperlinks` → `read_only=False`
    # auto-coerce pattern.
    # **iter-2 fixes from /vdd-adversarial (SEC-LOW-1 + SEC-LOW-3)**:
    # - Direct attribute access (`args.memory_mode`) replaces the
    #   defensive `getattr(..., "auto")` — argparse always sets the
    #   default; any caller constructing a partial `Namespace` should
    #   fail loud rather than silently default to auto.
    # - The `memory_mode = "full"` reassignment in the conflict path
    #   was dead code (the next branch checks `args.include_hyperlinks`
    #   directly, not `memory_mode`); removed.
    memory_mode = args.memory_mode
    if args.include_hyperlinks and memory_mode == "streaming":
        print(
            "warning: --memory-mode streaming overridden to 'full' "
            "because --include-hyperlinks requires non-read-only mode "
            "(ReadOnlyWorksheet does not expose cell.hyperlink). "
            "Either drop --include-hyperlinks (lose hyperlink "
            "extraction) or use --memory-mode full/auto (lose RAM "
            "savings).",
            file=sys.stderr,
        )
    if args.include_hyperlinks:
        read_only_mode: bool | None = False
    elif memory_mode == "streaming":
        read_only_mode = True
    elif memory_mode == "full":
        read_only_mode = False
    else:  # "auto"
        read_only_mode = None

    # xlsx-8a-03 (R3): parse allowlist once per invocation.
    scheme_allowlist = _parse_scheme_allowlist(
        args.hyperlink_scheme_allowlist
    )

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        with open_workbook(
            input_path,
            keep_formulas=args.include_formulas,
            read_only_mode=read_only_mode,
        ) as reader:
            payloads = dispatch.iter_table_payloads(
                args, reader, format=effective_format,
                hyperlink_scheme_allowlist=scheme_allowlist,
            )
            if effective_format == "json":
                rc = emit_json.emit_json(
                    payloads,
                    output=output_path,
                    sheet_selector=args.sheet,
                    tables_mode=args.tables,
                    header_flatten_style=args.header_flatten_style,
                    include_hyperlinks=args.include_hyperlinks,
                    datetime_format=args.datetime_format,
                    drop_empty_rows=args.drop_empty_rows,
                )
            elif effective_format == "csv":
                # args.delimiter is already a literal char thanks to the
                # `_delimiter_type` argparse type callable — no further
                # translation needed here.
                rc = emit_csv.emit_csv(
                    payloads,
                    output=output_path,
                    output_dir=output_dir,
                    sheet_selector=args.sheet,
                    tables_mode=args.tables,
                    include_hyperlinks=args.include_hyperlinks,
                    datetime_format=args.datetime_format,
                    encoding=args.encoding,
                    delimiter=args.delimiter,
                    drop_empty_rows=args.drop_empty_rows,
                    escape_formulas=args.escape_formulas,
                )
            else:
                raise ValueError(f"Unknown format: {effective_format!r}")

    _emit_warnings_to_stderr(captured)

    # Env-flag opt-in post-validate (TASK §R20). JSON path only.
    if effective_format == "json" and rc == 0:
        _post_validate_json_output(output_path)

    return rc


# ===========================================================================
# main()
# ===========================================================================
def main(argv: list[str] | None = None, *, format_lock: str | None = None) -> int:
    """Top-level entry point. Shims pass ``format_lock``; library helpers
    pass ``argv``.

    Returns the process exit code.
    """
    parser = build_parser(format_lock=format_lock)

    # FormatLockedByShim is raised by the --format type validator
    # during parsing → argparse calls parser.error which exits 2. We
    # catch SystemExit to convert it to a cross-5 envelope when
    # --json-errors is on. The _errors.add_json_errors_argument helper
    # already monkey-patches parser.error for usage errors, so usage
    # mismatches DO emit the envelope correctly — but FormatLockedByShim
    # raises *before* parser.error is called (it's the type validator).
    # To keep behaviour uniform, we surface FormatLockedByShim via the
    # envelope path explicitly.
    try:
        args = parser.parse_args(argv)
    except FormatLockedByShim as exc:
        # Synthetic args so report_error can read json_errors from argv.
        json_mode = (argv is not None and "--json-errors" in argv) or (
            argv is None and "--json-errors" in sys.argv[1:]
        )
        return _errors.report_error(
            str(exc),
            code=exc.CODE,
            error_type="FormatLockedByShim",
            details={},
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except SystemExit as e:
        # argparse called sys.exit on bad args (e.g. missing required
        # positional). Convert to int return; default 2 for usage errors.
        if isinstance(e.code, int):
            return e.code
        return 2

    # Cross-flag validation (parse-time invariants).
    try:
        _validate_flag_combo(args, format_lock=format_lock)
    except _AppError as exc:
        return _errors.report_error(
            str(exc),
            code=exc.CODE,
            error_type=type(exc).__name__,
            details={},
            json_mode=bool(args.json_errors),
            stream=sys.stderr,
        )

    effective_format = format_lock or args.format
    if effective_format is None:
        return _errors.report_error(
            "Either --format or a format-binding shim is required.",
            code=2,
            error_type="FormatRequired",
            details={},
            json_mode=bool(args.json_errors),
            stream=sys.stderr,
        )

    return _run_with_envelope(
        args,
        body=lambda: _dispatch_to_emit(args, effective_format),
    )

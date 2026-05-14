"""F1 — CLI argparse + main() orchestration.

This module owns the **entire** CLI surface for ``xlsx2md.py``.
Full flag surface per ARCH §5.1 is declared in :func:`build_parser`;
``main()`` routes every failure path through :func:`_errors.report_error`.

Cross-cutting envelope wiring (task 012-02):

* :func:`_validate_flag_combo` — M7 lock (IncludeFormulasRequiresHTML)
  and R14h lock (HeaderRowsConflict). Fires BEFORE any file I/O.
* :func:`_resolve_paths` — canonical ``Path.resolve()`` + same-path
  guard (cross-7 H1) + output-parent auto-create (R4d).
* :func:`main` — full try/except envelope routing; terminal
  ``except Exception`` catch-all renders InternalError code-7 with
  redacted message (R23f).

Layers:

* :func:`build_parser` — argparse construction; full 14-flag surface
  per ARCH §5.1 with correct defaults and metavar strings.
* :func:`_validate_flag_combo` — cross-flag invariant checks before
  file I/O.
* :func:`_resolve_paths` — canonical path resolution with same-path
  guard and parent-dir auto-create.
* :func:`main` — full orchestration with cross-5 envelope on every
  failure path.
"""
from __future__ import annotations

import argparse
import contextlib
import sys
import warnings
from pathlib import Path
from typing import IO, Any, Iterator

import _errors
from xlsx_read import (
    EncryptedWorkbookError,
    SheetNotFound,
)

from .exceptions import (
    _AppError,
    HeaderRowsConflict,
    IncludeFormulasRequiresHTML,
    InternalError,
    PostValidateFailed,
    SelfOverwriteRefused,
)


# ---------------------------------------------------------------------------
# Argparse helpers
# ---------------------------------------------------------------------------

def _header_rows_type(value: str) -> Any:
    """Custom type for ``--header-rows``.

    Accepts:
      - ``"auto"`` — auto-detect header band via merge-cell structure
        (xlsx-8 / xlsx-read foundation default).
      - ``"smart"`` — type-pattern heuristic; skip metadata blocks above
        the data table (xlsx-8a-09 / R11; ARCH D-A13).
      - ``int >= 1`` — explicit fixed header-row count (R14h: conflicts
        with multi-table mode; validated in ``_validate_flag_combo``).

    Returns:
        ``"auto"`` (str), ``"smart"`` (str), or an ``int >= 1``.
    """
    if value in ("auto", "smart"):
        return value
    try:
        n = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--header-rows must be 'auto', 'smart', or an integer >= 1; "
            f"got {value!r}"
        ) from exc
    if n < 1:
        raise argparse.ArgumentTypeError(
            f"--header-rows integer must be >= 1, got {n}"
        )
    return n


# ---------------------------------------------------------------------------
# Public argparse surface
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse surface (all 14 named flags + 2 positional).

    Returns:
        A fully-configured :class:`argparse.ArgumentParser`. Defaults are
        locked per ARCH §5.1 — future tasks must not change defaults here
        (they are the 012-08 no-flag shape pin regression baseline).
    """
    p = argparse.ArgumentParser(
        prog="xlsx2md.py",
        description="xlsx-9: Convert an .xlsx workbook into Markdown.",
        epilog=(
            "MEMORY NOTE: hyperlinks are always extracted (D5 lock), which "
            "forces full openpyxl load (~5-10x file size in RAM). Use "
            "--memory-mode=streaming to suppress hyperlinks and reduce memory "
            "(trade-off: hyperlinks become unreliable per honest-scope §1.4(m)).\n\n"
            "HYPERLINK ALLOWLIST: comma-separated URL schemes allowed through. "
            "Pass '*' to allow all schemes (not recommended). Pass \"\" (empty "
            "string) to strip all hyperlinks to plain text."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # --- Positional arguments ---
    p.add_argument(
        "INPUT",
        nargs="?",
        default=None,
        help=(
            "Path to the .xlsx / .xlsm workbook to convert. "
            "REQUIRED at runtime — argparse declares as optional so "
            "--help works with no args; _resolve_paths enforces required."
        ),
    )
    p.add_argument(
        "OUTPUT",
        nargs="?",
        default="-",
        help="Output path for the .md file, or '-' for stdout (default: stdout).",
    )

    # --- Named flags (14 total per ARCH §5.1) ---
    p.add_argument(
        "--sheet",
        metavar="NAME|all",
        default="all",
        help=(
            "Process a single named sheet (NAME) or all visible sheets in "
            "document order (default: all). Missing NAME -> exit 2 SheetNotFound."
        ),
    )
    p.add_argument(
        "--include-hidden",
        action="store_true",
        default=False,
        help=(
            'Include sheets with state="hidden" or state="veryHidden" '
            "(default: skip hidden sheets)."
        ),
    )
    p.add_argument(
        "--format",
        choices=("gfm", "html", "hybrid"),
        default="hybrid",
        metavar="gfm|html|hybrid",
        help=(
            "Output format: 'gfm' (all tables as GFM pipe-tables), 'html' "
            "(all tables as <table>), 'hybrid' (per-table auto-select, default)."
        ),
    )
    p.add_argument(
        "--header-rows",
        type=_header_rows_type,
        default="auto",
        metavar="N|auto|smart",
        help=(
            "Header-row strategy: 'auto' (merge-based detection, default), "
            "'smart' (type-pattern heuristic to skip metadata banners, "
            "xlsx-8a-09 R11), or an integer >= 1 (fixed; conflicts with "
            "multi-table mode -> exit 2 HeaderRowsConflict)."
        ),
    )
    p.add_argument(
        "--memory-mode",
        choices=("auto", "streaming", "full"),
        default="auto",
        metavar="auto|streaming|full",
        help=(
            "openpyxl load strategy. 'auto': size-threshold (>= 100 MiB -> "
            "streaming). 'streaming': force read_only=True (lower RAM; "
            "hyperlinks unreliable). 'full': force read_only=False (correct "
            "merges, unbounded RAM). Inherited from xlsx-8a-11 (R20a)."
        ),
    )
    p.add_argument(
        "--hyperlink-scheme-allowlist",
        metavar="SCHEMES",
        default="http,https,mailto",
        help=(
            "Comma-separated URL schemes allowed through hyperlink rendering "
            "(default: http,https,mailto). Schemes outside the list emit "
            "text-only + warning (Sec-MED-2). "
            "Pass '*' to allow all schemes — DANGEROUS: enables "
            "'javascript:', 'data:', 'vbscript:', 'file:' which can "
            "execute scripts in HTML renderers (Marp, IDE preview panes, "
            "browser-based markdown viewers). Only use when emitting to "
            "a trusted text-only consumer. "
            "Pass \"\" to strip all hyperlinks to plain text."
        ),
    )
    p.add_argument(
        "--no-table-autodetect",
        action="store_true",
        default=False,
        help=(
            "Disable Tier-1 + Tier-2 table detection; only gap-detect regions "
            "are emitted (D-A2 post-call filter on r.source == 'gap_detect')."
        ),
    )
    p.add_argument(
        "--no-split",
        action="store_true",
        default=False,
        help=(
            "Treat the whole sheet as one table; uses detect_tables(mode='whole'). "
            "H3 heading ### Table-1 is still emitted."
        ),
    )
    p.add_argument(
        "--gap-rows",
        type=int,
        metavar="N",
        default=2,
        help=(
            "Gap-detect row threshold (default: 2). M4 fix: single empty row "
            "is not a reliable splitter; minimum 2 is the xlsx-8 parity default."
        ),
    )
    p.add_argument(
        "--gap-cols",
        type=int,
        metavar="N",
        default=1,
        help="Gap-detect column threshold (default: 1).",
    )
    p.add_argument(
        "--gfm-merge-policy",
        choices=("fail", "duplicate", "blank"),
        default="fail",
        metavar="fail|duplicate|blank",
        help=(
            "Body-merge handling in GFM mode. 'fail': exit 2 "
            "GfmMergesRequirePolicy (default). 'duplicate'/'blank': lossy "
            "GFM + warning. Ignored for HTML / hybrid (HTML handles merges "
            "natively)."
        ),
    )
    p.add_argument(
        "--datetime-format",
        choices=("ISO", "excel-serial", "raw"),
        default="ISO",
        metavar="ISO|excel-serial|raw",
        help=(
            "Datetime formatting forwarded to read_table(datetime_format=...). "
            "Default: ISO (xlsx-3 round-trip parity; ISO-8601 dates "
            "auto-coerced by md_tables2xlsx)."
        ),
    )
    p.add_argument(
        "--include-formulas",
        action="store_true",
        default=False,
        help=(
            "HTML + hybrid: emit formula strings as data-formula attributes "
            "on formula cells. GFM: exit 2 IncludeFormulasRequiresHTML (M7 lock)."
        ),
    )

    # Cross-5 envelope flag — wired via shared helper (replaces manual --json-errors).
    _errors.add_json_errors_argument(p)

    return p


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------

def _validate_flag_combo(args: argparse.Namespace) -> None:
    """Validate cross-flag invariants BEFORE any file I/O.

    Raises:
        IncludeFormulasRequiresHTML: M7 lock — ``--format gfm`` +
            ``--include-formulas`` is incompatible (code 2).
        HeaderRowsConflict: R14h — ``--header-rows N`` (int) combined
            with multi-table mode (``--no-split`` and
            ``--no-table-autodetect`` both False) is ambiguous (code 2).

    Note:
        R15 / GfmMergesRequirePolicy (D14): the gate for this lock is
        DOWNSTREAM — raise-site lives in 012-06
        ``emit_hybrid.emit_workbook_md`` because the check requires an
        actual body merge to be observed. This function does NOT raise
        GfmMergesRequirePolicy.
    """
    # M7 lock: --format gfm + --include-formulas is incompatible.
    if args.format == "gfm" and args.include_formulas:
        raise IncludeFormulasRequiresHTML()

    # R14h: --header-rows N (int) combined with multi-table mode.
    # Multi-table mode is active when NEITHER --no-split NOR
    # --no-table-autodetect is set (both default False).
    if (
        isinstance(args.header_rows, int)
        and not args.no_split
        and not args.no_table_autodetect
    ):
        raise HeaderRowsConflict(
            {
                "n_requested": args.header_rows,
                "table_count": "unknown_pre_open",
                "suggestion": (
                    "use --header-rows auto or --header-rows smart "
                    "for multi-table workbooks"
                ),
            }
        )


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path | None]:
    """Canonical-resolve INPUT and OUTPUT; apply same-path guard + auto-create.

    Raises:
        FileNotFoundError: INPUT does not exist (propagates to terminal handler).
        SelfOverwriteRefused: OUTPUT resolves to the same path as INPUT
            after symlink-follow (cross-7 H1, code 6).

    Returns:
        ``(input_path, output_path)`` where ``output_path`` is ``None``
        when stdout mode is active (no OUTPUT, or OUTPUT == ``"-"``).
    """
    input_path = Path(args.INPUT).resolve(strict=True)

    if args.OUTPUT is None or args.OUTPUT == "-":
        output_path: Path | None = None
    else:
        output_path = Path(args.OUTPUT).resolve()
        # Cross-7 H1: same-path guard (symlinks followed by resolve()).
        if output_path == input_path:
            raise SelfOverwriteRefused({"path": input_path.name})
        # R4d: output-parent auto-create.
        if not output_path.parent.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)

    return (input_path, output_path)


# ---------------------------------------------------------------------------
# Module-scope helpers
# ---------------------------------------------------------------------------

def _resolve_output_stream(output_path: Path | None) -> tuple[IO[str], Path | None]:
    """Return ``(stream, temp_path)`` — ``temp_path`` is None for stdout mode.

    M5 fix: when writing to a file, open a sibling tempfile (same dir,
    so ``os.replace`` is atomic) instead of the final path. The caller
    is responsible for ``os.replace(temp_path, output_path)`` on success
    OR ``temp_path.unlink(missing_ok=True)`` on failure. This prevents
    leaving a partial ``.md`` on disk when ``emit_workbook_md`` raises
    mid-write (e.g. ``GfmMergesRequirePolicy`` on the second table after
    the first has already been flushed).
    """
    if output_path is None:
        return sys.stdout, None
    # Sibling tempfile: same dir → atomic os.replace; ``.partial`` suffix
    # makes a leftover obvious if both the emit AND the unlink fail.
    temp_path = output_path.with_suffix(output_path.suffix + ".partial")
    fp = open(temp_path, "w", encoding="utf-8")  # noqa: WPS515
    return fp, temp_path


def _post_validate_output(output_path: Path) -> None:
    """M2 fix: env-flag re-parse gate (``XLSX_XLSX2MD_POST_VALIDATE=1``).

    When the env flag is set, re-open the just-written Markdown file
    and assert it parses as valid UTF-8 + has at least one ``## `` H2
    or ``| `` GFM-table marker. On failure, raise ``PostValidateFailed``
    (the caller unlinks the temp before propagation).

    Mirrors the env-flag gate documented for sibling skills (xlsx-2 D8
    pattern). The intent is a defensive smoke-test for CI pipelines
    that want a "did we actually emit something?" check without
    invoking the full xlsx-3 round-trip suite.

    Truthy values: ``1``, ``true``, ``yes``, ``on`` (case-insensitive).
    Any other value (including unset) → no-op.
    """
    import os  # noqa: PLC0415

    flag = os.environ.get("XLSX_XLSX2MD_POST_VALIDATE", "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        return
    try:
        text = output_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PostValidateFailed(
            {"path": output_path.name, "reason": f"unreadable: {type(exc).__name__}"}
        ) from exc
    if not text.strip():
        raise PostValidateFailed(
            {"path": output_path.name, "reason": "empty output"}
        )
    # Minimum-viable structural check: at least one H2 header or one
    # GFM table separator. (HTML-only output may have neither in some
    # synthetic-stub edge cases; the contract is "output is non-empty
    # and looks like markdown", not "passes a full CommonMark parser".)
    if "## " not in text and "|---" not in text and "<table" not in text:
        raise PostValidateFailed(
            {
                "path": output_path.name,
                "reason": "no recognisable markdown structure",
            }
        )


@contextlib.contextmanager
def _streaming_warnings_to_stderr() -> Iterator[None]:
    """Stream every ``warnings.warn(...)`` call directly to ``sys.stderr``.

    Replaces the prior ``warnings.catch_warnings(record=True)`` +
    end-of-run drain pattern. Two correctness wins (Sarcasmotron-driven
    fix H3):

    1. **Survives exceptions.** The prior pattern called the drain
       INSIDE the ``try:`` block after ``emit_workbook_md`` returned —
       if any exception propagated (e.g. ``GfmMergesRequirePolicy``),
       the captured warnings list was dropped on the floor. This
       handler writes each warning on the ``warnings.warn(...)`` call
       itself, so warnings reach the user even when the run terminates
       abnormally.

    2. **Per-warning streaming.** Each warning hits stderr immediately
       instead of being buffered until the workbook is fully emitted.
       Matches the per-table ``out.flush()`` contract from D-A7.

    The original `showwarning` is restored on context exit so the
    parent process's warning handler is unaffected.
    """
    original_showwarning = warnings.showwarning
    original_filters = warnings.filters[:]

    def _stream_to_stderr(
        message: Warning | str,
        category: type[Warning],
        filename: str,
        lineno: int,
        file: IO[str] | None = None,  # noqa: ARG001
        line: str | None = None,      # noqa: ARG001
    ) -> None:
        sys.stderr.write(f"warning: {message}\n")
        sys.stderr.flush()

    warnings.showwarning = _stream_to_stderr
    warnings.simplefilter("always")
    try:
        yield
    finally:
        warnings.showwarning = original_showwarning
        warnings.filters[:] = original_filters


def _extract_details(e: _AppError) -> dict:
    """Return ``e.args[0]`` if it is a dict, else ``{}``."""
    if e.args and isinstance(e.args[0], dict):
        return e.args[0]
    return {}


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Top-level orchestrator.

    Routes every failure path through :func:`_errors.report_error`.
    No ``sys.exit()`` is called here — the caller (shim ``xlsx2md.py``)
    does ``sys.exit(main())``.

    Returns:
        0 on success; 2-7 on documented failure modes per the envelope
        catalogue in ``docs/ARCHITECTURE.md §2.1 F8``.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    json_mode = bool(args.json_errors)

    # input_path may not be defined yet if _resolve_paths raises before
    # binding — use args.INPUT basename as fallback in EncryptedWorkbookError
    # handler.
    input_path: Path | None = None

    try:
        _validate_flag_combo(args)
        input_path, output_path = _resolve_paths(args)

        # H3 fix (Sarcasmotron-driven): replace
        # ``warnings.catch_warnings(record=True)`` buffering with a custom
        # ``showwarning`` hook that streams each warning to stderr
        # IMMEDIATELY. This (a) keeps warnings visible incrementally as
        # tables are emitted (parity with the ``out.flush()`` per-table
        # contract — D-A7), (b) ensures warnings reach stderr even when
        # ``emit_workbook_md`` raises (previously the
        # ``catch_warnings(record=True)`` block dropped the entire warning
        # buffer on the exception path).
        with _streaming_warnings_to_stderr():
            from .dispatch import _resolve_read_only_mode  # noqa: PLC0415
            read_only_mode = _resolve_read_only_mode(args)
            args._read_only_mode_resolved = read_only_mode
            from xlsx_read import open_workbook  # noqa: PLC0415
            # M1 fix: wire keep_formulas=True when --include-formulas is
            # set so xlsx_read.read_table(include_formulas=True) actually
            # surfaces formula strings in TableData.rows (otherwise the
            # library returns cached values via data_only=True and
            # data-formula attribute emission is a no-op).
            keep_formulas = bool(getattr(args, "include_formulas", False))
            with open_workbook(
                input_path,
                read_only_mode=read_only_mode,
                keep_formulas=keep_formulas,
            ) as reader:
                # M3 fix: detect EFFECTIVE streaming mode (whether picked
                # explicitly via --memory-mode=streaming OR by library's
                # size-threshold heuristic ≥ 100 MiB on auto). Expose to
                # dispatch via a side-channel so the unreliability warning
                # fires in both paths.
                args._read_only_effective = bool(
                    getattr(reader, "_read_only", False)
                )
                # M5 fix: write to a sibling tempfile then atomic
                # os.replace at success; unlink on any exception so a
                # partial .md is never left behind (previous behaviour
                # leaked orphan H2/H3 headings when emit_workbook_md
                # raised mid-write — e.g. GfmMergesRequirePolicy on the
                # second table after the first had already been flushed).
                out_stream, temp_path = _resolve_output_stream(output_path)
                emit_completed = False
                try:
                    from .emit_hybrid import emit_workbook_md  # noqa: PLC0415
                    exit_code = emit_workbook_md(reader, args, out_stream)
                    emit_completed = True
                finally:
                    # M5 + M-NEW-2 (iter 2): close stream, then either
                    # publish-after-validate (success) or unlink-temp
                    # (failure). Both paths run INSIDE this finally so
                    # they fire even when ``emit_workbook_md`` raises —
                    # the prior iter-2 attempt placed them outside the
                    # finally, breaking the unlink-on-failure contract.
                    if temp_path is not None:
                        out_stream.close()
                        if not emit_completed:
                            # Emit failed: drop temp, no publish.
                            temp_path.unlink(missing_ok=True)
                        else:
                            # M-NEW-2 fix: validate TEMP first, only
                            # publish on validation pass — otherwise the
                            # M5 "never leave a partial file" contract
                            # breaks at the validation boundary.
                            try:
                                if exit_code == 0:
                                    _post_validate_output(temp_path)
                                import os as _os  # noqa: PLC0415
                                _os.replace(temp_path, output_path)
                            except _AppError:
                                # Validation failed: drop temp; let the
                                # exception propagate to the outer
                                # envelope handler.
                                temp_path.unlink(missing_ok=True)
                                raise
        return exit_code

    except _AppError as e:
        return _errors.report_error(
            str(e) or type(e).__name__,
            code=e.CODE,
            error_type=type(e).__name__,
            details=_extract_details(e),
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except EncryptedWorkbookError:
        # input_path may be None if _resolve_paths failed; fall back to
        # args.INPUT basename to avoid leaking an absolute path.
        if input_path is not None:
            filename = input_path.name
        else:
            filename = Path(args.INPUT or "").name
        return _errors.report_error(
            f"Workbook is encrypted: {filename}",
            code=3,
            error_type="EncryptedWorkbookError",
            details={"filename": filename},
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except SheetNotFound as e:
        return _errors.report_error(
            str(e),
            code=2,
            error_type="SheetNotFound",
            details={"sheet": getattr(e, "sheet", None) or str(e)},
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except Exception as exc:  # noqa: BLE001 — terminal catch-all (R23f)
        # Raw message dropped to prevent absolute-path leaks from
        # openpyxl / xlsx_read internals. For local debugging,
        # re-run without --json-errors to see Python traceback.
        return _errors.report_error(
            f"Internal error: {type(exc).__name__}",
            code=InternalError.CODE,
            error_type="InternalError",
            details={},
            json_mode=json_mode,
            stream=sys.stderr,
        )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

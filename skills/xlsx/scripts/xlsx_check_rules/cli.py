"""F1 + F11 — CLI surface and pipeline orchestrator. M-2 watchdog
sets a flag only; `_partial_flush` runs main-thread post-loop.
Routes cross-3/4/5/7 H1 envelopes via `_emit_fatal`."""
from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_MAX_FINDINGS,
    DEFAULT_SUMMARIZE_AFTER,
    DEFAULT_TIMEOUT_SECONDS,
)

__all__ = [
    "build_parser",
    "parse_args",
    "main",
    "_run",
    "_partial_flush",
    "_TimeoutFlag",
    "_install_watchdog",
    "_cleanup_watchdog",
]


# === --treat-*-as-date separator auto-detect (DEP-6) =====================

def _split_treat_as_date(raw: str) -> list[str]:
    """SPEC §8.1: `,` separator default; `;` if any token contains `,`. Empty → []."""
    if not raw:
        return []
    sep = ";" if ";" in raw else ","
    return [t.strip() for t in raw.split(sep) if t.strip()]


# === argparse builder (TASK §2.5 — 22+ flags) =============================

def build_parser() -> argparse.ArgumentParser:
    """TASK §2.5 argparse surface; cross-checks in `_validate_mutex_dep`."""
    p = argparse.ArgumentParser(
        prog="xlsx_check_rules.py",
        description=(
            "Declarative business-rule validator for .xlsx workbooks "
            "(xlsx-7). Reads a rules.json|yaml file alongside an .xlsx "
            "and emits findings JSON + optional in-workbook remarks. "
            "See skills/xlsx/references/xlsx-rules-format.md for the "
            "rules-file SPEC."
        ),
    )
    p.add_argument("input", help="path to .xlsx workbook")
    p.add_argument("--rules", required=True,
                   help="path to rules.json|yaml (1 MiB cap)")

    # Output mode (MX-A): --json XOR --no-json
    output_mode = p.add_mutually_exclusive_group()
    output_mode.add_argument("--json", dest="json_mode", action="store_true",
                              default=False,
                              help="emit findings JSON to stdout (human report to stderr)")
    output_mode.add_argument("--no-json", dest="json_mode", action="store_false",
                              help="(default) human report to stdout; no JSON envelope")

    # Severity & gating
    p.add_argument("--strict", action="store_true",
                   help="promote any warning to non-zero exit (code 4)")
    p.add_argument("--require-data", dest="require_data", action="store_true",
                   help="exit 1 with synthetic `no-data-checked` if checked_cells == 0")
    p.add_argument("--severity-filter", dest="severity_filter",
                   default=None,
                   help="comma-separated subset of {error,warning,info}")

    # Findings volume
    p.add_argument("--max-findings", dest="max_findings", type=int,
                   default=DEFAULT_MAX_FINDINGS,
                   help=f"cap findings array length (default {DEFAULT_MAX_FINDINGS}; 0 = unbounded)")
    p.add_argument("--summarize-after", dest="summarize_after", type=int,
                   default=DEFAULT_SUMMARIZE_AFTER,
                   help=(f"per-rule_id collapse once N findings emitted "
                         f"(default {DEFAULT_SUMMARIZE_AFTER}; 0 = disabled)"))

    # Performance
    p.add_argument("--timeout", dest="timeout_seconds", type=int,
                   default=DEFAULT_TIMEOUT_SECONDS,
                   help=f"wall-clock cap in seconds (default {DEFAULT_TIMEOUT_SECONDS}; exit 7 on overrun)")

    # Sheet & header config
    p.add_argument("--sheet", dest="sheet_override", default=None,
                   help="override defaults.sheet")
    p.add_argument("--header-row", dest="header_row_override", type=int,
                   default=None,
                   help="override defaults.header_row (0 disables header resolution)")

    # Hidden rows/cols (MX-B)
    visibility = p.add_mutually_exclusive_group()
    visibility.add_argument("--include-hidden", dest="visible_only",
                             action="store_false", default=False,
                             help="(default) hidden rows/cols evaluated")
    visibility.add_argument("--visible-only", dest="visible_only",
                             action="store_true",
                             help="skip hidden rows/cols")

    # Workbook-content flags
    p.add_argument("--no-strip-whitespace", dest="no_strip_whitespace",
                   action="store_true",
                   help="disable default whitespace stripping on text cells")
    p.add_argument("--no-table-autodetect", dest="no_table_autodetect",
                   action="store_true",
                   help="disable Excel-Table fallback for col:HEADER")
    p.add_argument("--no-merge-info", dest="no_merge_info", action="store_true",
                   help="suppress merged-cell-resolution info findings")

    # Cache & error handling
    p.add_argument("--ignore-stale-cache", dest="ignore_stale_cache",
                   action="store_true",
                   help="suppress stale-cache warning (formulas without cached values)")
    p.add_argument("--strict-aggregates", dest="strict_aggregates",
                   action="store_true",
                   help="promote aggregate type-mismatch skips to error findings")

    # Date interpretation (DEP-6 separator auto-detect)
    p.add_argument("--treat-numeric-as-date", dest="treat_numeric_as_date",
                   default=None, type=_split_treat_as_date,
                   help=("comma-separated column letters/headers; "
                         "auto-switches to ';' if any token contains ','"))
    p.add_argument("--treat-text-as-date", dest="treat_text_as_date",
                   default=None, type=_split_treat_as_date,
                   help="same separator semantics as --treat-numeric-as-date")

    # Workbook output (DEP-1..3)
    p.add_argument("--output", dest="output_path", default=None,
                   help="write a copy of INPUT with remarks attached")
    p.add_argument("--remark-column", dest="remark_column", default=None,
                   help="auto | LETTER | HEADER (requires --output, DEP-1)")
    p.add_argument("--remark-column-mode", dest="remark_column_mode",
                   choices=("replace", "append", "new"), default=None,
                   help="(default 'new') replace / append / new (requires --remark-column, DEP-2)")
    p.add_argument("--streaming-output", dest="streaming_output",
                   action="store_true",
                   help=("openpyxl write-only path for >=100K cells "
                         "(requires --output, DEP-3; DEP-4: incompat with --remark-column auto; "
                         "DEP-5: incompat with --remark-column-mode append)"))

    # cross-5 — `--json-errors` wired via the shared helper.
    try:
        # `_errors` lives at scripts/_errors.py (sibling of this package).
        # Add the parent dir to sys.path so the import works regardless of cwd.
        import os
        scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from _errors import add_json_errors_argument
        add_json_errors_argument(p)
    except ImportError:
        # Fallback: bare flag without json-aware error routing.
        p.add_argument("--json-errors", dest="json_errors", action="store_true",
                       help="emit failures as JSON on stderr (cross-5 envelope)")

    return p


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse argv, then run the mutex/dependency cross-checks (MX-A,
    MX-B, DEP-1..7). On a cross-check violation, calls `parser.error`
    which exits 2 (and routes through cross-5 when `--json-errors` is set)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_mutex_dep(args, parser)
    return args


def _validate_mutex_dep(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Post-parse cross-checks for DEP-1..DEP-7 (MX-A and MX-B are
    enforced by argparse mutex groups directly)."""
    # DEP-1: --remark-column ⇒ --output
    if args.remark_column is not None and not args.output_path:
        parser.error("--remark-column requires --output (DEP-1)")
    # DEP-2: --remark-column-mode ⇒ --remark-column
    if args.remark_column_mode is not None and args.remark_column is None:
        parser.error("--remark-column-mode requires --remark-column (DEP-2)")
    # DEP-3: --streaming-output ⇒ --output
    if args.streaming_output and not args.output_path:
        parser.error("--streaming-output requires --output (DEP-3)")
    # DEP-4: --streaming-output ∧ --remark-column auto → IncompatibleFlags
    if args.streaming_output and args.remark_column == "auto":
        parser.error(
            "--streaming-output is incompatible with --remark-column auto "
            "(DEP-4 IncompatibleFlags); pass an explicit column letter"
        )
    # DEP-5: --streaming-output ∧ --remark-column-mode append → IncompatibleFlags
    if args.streaming_output and args.remark_column_mode == "append":
        parser.error(
            "--streaming-output is incompatible with --remark-column-mode append "
            "(DEP-5 IncompatibleFlags); use --remark-column-mode replace or new"
        )

    # Default remark-column-mode per TASK §2.5 (R7.d)
    if args.remark_column is not None and args.remark_column_mode is None:
        args.remark_column_mode = "new"

    # Severity filter parsing (validate subset).
    if args.severity_filter:
        levels = {x.strip() for x in args.severity_filter.split(",") if x.strip()}
        bad = levels - {"error", "warning", "info"}
        if bad:
            parser.error(
                f"--severity-filter accepts subset of error/warning/info; "
                f"got unknown {sorted(bad)}"
            )
        args.severity_filter = sorted(levels)


def main(argv: list[str] | None = None) -> int:
    """End-to-end entrypoint. M-2 line-buffer guarantees partial-flush atomicity."""
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass  # StringIO substitutes — already memory-resident
    args = parse_args(argv)
    try:
        return _run(args)
    except KeyboardInterrupt:
        return 130


# === Watchdog (M-2 architect lock — handler ONLY sets a flag) =============

class _TimeoutFlag:
    """Sentinel flipped by the watchdog handler. The handler MUST NOT
    write to stdout, MUST NOT call `_partial_flush` — only `flag.trip()`.
    `_partial_flush` runs in the main thread post-loop (M-2)."""

    def __init__(self) -> None:
        self.tripped = False

    def trip(self) -> None:
        self.tripped = True


def _install_watchdog(timeout_seconds: int, flag: _TimeoutFlag) -> Any:
    """POSIX: SIGALRM. Windows: daemon `threading.Timer`. The handler
    body is intentionally minimal — it ONLY calls `flag.trip()`."""
    if timeout_seconds <= 0:
        return None
    if hasattr(signal, "SIGALRM"):
        def _handler(*_unused: Any) -> None:
            # M-2: handler does ONLY this — no stdout, no _partial_flush.
            # `_unused` absorbs (signum, frame) per the SIGALRM contract.
            flag.trip()
        signal.signal(signal.SIGALRM, _handler)
        signal.alarm(timeout_seconds)
        return None
    timer = threading.Timer(timeout_seconds, flag.trip)
    timer.daemon = True
    timer.start()
    return timer


def _cleanup_watchdog(timer: Any) -> None:
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)
    elif timer is not None:
        timer.cancel()


def _partial_flush(findings: list[Any], summary: dict[str, Any], opts: Any,
                    timeout_seconds: int) -> None:
    """M-2 architect lock: MAIN THREAD post-loop only (json.dump is async-signal-unsafe)."""
    assert threading.current_thread() is threading.main_thread(), (
        "_partial_flush MUST run in main thread (M-2 architect lock)"
    )
    summary["elapsed_seconds"] = float(timeout_seconds)
    summary["truncated"] = False
    from .output import emit_findings
    emit_findings(findings, summary, opts)  # emit_findings flushes


# === End-to-end orchestrator (F11) ========================================

def _new_summary() -> dict[str, Any]:
    """SPEC §7.1.1 summary keys, all initialised to 0."""
    return {
        "errors": 0, "warnings": 0, "info": 0,
        "checked_cells": 0, "rules_evaluated": 0, "cell_errors": 0,
        "skipped_in_aggregates": 0, "regex_timeouts": 0, "eval_errors": 0,
        "aggregate_cache_hits": 0, "elapsed_seconds": 0.0, "truncated": False,
    }


def _emit_fatal(err: Any, args: Any | None) -> int:
    """cross-5 envelope wrap when `--json-errors` is set; otherwise plain
    stderr line. Returns the typed exit code (`err.code`)."""
    json_mode = bool(args is not None and getattr(args, "json_errors", False))
    try:
        import os as _os
        scripts_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from _errors import report_error
        return report_error(
            str(err), code=err.code, error_type=err.type_,
            details=getattr(err, "details", None) or None,
            json_mode=json_mode,
        )
    except ImportError:  # pragma: no cover — _errors always present
        sys.stderr.write(f"{err.type_}: {err}\n")
        return err.code


def _compute_exit_code(summary: dict[str, Any], args: Any) -> int:
    """SPEC §7.3 exit-code matrix (excluding 2/3/5/6/7 which are raised earlier)."""
    if summary["errors"] > 0:
        return 1
    if args.strict and summary["warnings"] > 0:
        return 4
    return 0


def _check_same_path(input_path: str, output_path: str | None) -> bool:
    """cross-7 H1: True iff input and output (after resolve) are the same inode."""
    if not output_path:
        return False
    try:
        return Path(input_path).resolve() == Path(output_path).resolve()
    except OSError:
        return False


def _run(args: Any) -> int:
    """End-to-end pipeline (architecture §2.1 F11)."""
    from openpyxl import load_workbook

    from .aggregates import AggregateCache
    from .cell_types import LogicalType
    from .dsl_parser import build_rule_spec
    from .evaluator import EvalContext, Finding, eval_rule
    from .exceptions import (
        CorruptInput, EncryptedInput, IOError as XlsxIOError,
        SelfOverwriteRefused, _AppError,
    )
    from .output import emit_findings
    from .rules_loader import load_rules_file
    from .scope_resolver import resolve_scope

    # 1) cross-7 H1 same-path guard.
    if _check_same_path(args.input, args.output_path):
        return _emit_fatal(SelfOverwriteRefused(
            f"--output resolves to the same path as input: {args.input}",
            input=args.input, output=args.output_path,
        ), args)

    # 2-3) Open workbook with cross-3 / cross-4 envelopes.
    try:
        from office._encryption import assert_not_encrypted, EncryptedFileError
        assert_not_encrypted(Path(args.input))
    except ImportError:  # pragma: no cover — office shared module always present
        EncryptedFileError = ()  # type: ignore[misc]
    except (EncryptedFileError, Exception) as e:  # noqa: BLE001 — boundary
        if e.__class__.__name__ == "EncryptedFileError":
            return _emit_fatal(EncryptedInput(
                f"workbook is encrypted: {args.input}", input=args.input,
            ), args)
        return _emit_fatal(XlsxIOError(f"unreadable workbook: {args.input} ({e})",
                                         input=args.input), args)

    if args.input.lower().endswith(".xlsm"):
        try:
            from office._macros import warn_if_macros_will_be_dropped
            warn_if_macros_will_be_dropped(
                Path(args.input),
                Path(args.output_path) if args.output_path else Path("/dev/null"),
                sys.stderr,
            )
        except ImportError:  # pragma: no cover
            sys.stderr.write(f"WARNING: .xlsm input may carry macros: {args.input}\n")

    try:
        wb = load_workbook(args.input, data_only=True)
    except FileNotFoundError as e:
        return _emit_fatal(XlsxIOError(f"workbook not found: {args.input}",
                                         input=args.input), args)
    except Exception as e:  # noqa: BLE001 — boundary on workbook open
        return _emit_fatal(CorruptInput(f"failed to open workbook: {e}",
                                          input=args.input), args)

    # 4) Load rules + build AST.
    try:
        rules_data = load_rules_file(args.rules)
        defaults = dict(rules_data.get("defaults") or {})
        if args.sheet_override is not None:
            defaults["sheet"] = args.sheet_override
        if args.header_row_override is not None:
            defaults["header_row"] = args.header_row_override
        rule_specs = [build_rule_spec(r) for r in rules_data["rules"]]
    except _AppError as e:
        return _emit_fatal(e, args)

    # 5-7) Watchdog + per-rule eval loop.
    findings: list[Finding] = []
    summary = _new_summary()
    cache = AggregateCache()
    flag = _TimeoutFlag()
    timer = _install_watchdog(args.timeout_seconds, flag)
    eval_opts = {
        "strip_whitespace": not args.no_strip_whitespace,
        "no_table_autodetect": args.no_table_autodetect,
        "no_merge_info": args.no_merge_info,
        "ignore_stale_cache": args.ignore_stale_cache,
        "treat_numeric_as_date": set(args.treat_numeric_as_date or ()),
        "treat_text_as_date": set(args.treat_text_as_date or ()),
        "visible_only": args.visible_only,
    }
    t0 = time.perf_counter()
    try:
        for rule in rule_specs:
            if flag.tripped:
                break
            try:
                sr = resolve_scope(rule.scope, wb, defaults, eval_opts)
            except _AppError as e:
                _cleanup_watchdog(timer)
                return _emit_fatal(e, args)
            ctx = EvalContext(
                workbook=wb, rule=rule, aggregate_cache=cache,
                defaults=defaults, eval_opts=eval_opts,
                strict_aggregates=args.strict_aggregates,
            )
            for f in eval_rule(rule, sr, ctx):
                if flag.tripped:
                    break
                findings.append(f)
                key = f.severity + "s"  # "errors" / "warnings" / "infos"
                if key in summary:
                    summary[key] += 1
            summary["checked_cells"] += sum(
                1 for c in sr.cells if c.logical_type is not LogicalType.EMPTY
            )
            summary["rules_evaluated"] += 1
            summary["cell_errors"] += ctx.cell_errors
            summary["skipped_in_aggregates"] += ctx.skipped_in_aggregates
            summary["regex_timeouts"] += ctx.regex_timeouts
            summary["eval_errors"] += ctx.eval_errors
            summary["aggregate_cache_hits"] = max(
                summary["aggregate_cache_hits"], ctx.aggregate_cache_hits,
            )
    finally:
        _cleanup_watchdog(timer)
    summary["elapsed_seconds"] = round(time.perf_counter() - t0, 3)

    # --require-data: synthesise a `no-data-checked` finding when nothing scanned.
    if args.require_data and summary["checked_cells"] == 0:
        findings.append(Finding(
            cell="", sheet="", row=None, column=None,
            rule_id="no-data-checked", severity="error", value=None,
            message="--require-data set; no cells were checked",
        ))
        summary["errors"] += 1

    # 8) Emit — partial-flush on timeout (M-2 main-thread invariant).
    if flag.tripped:
        _partial_flush(findings, summary, args, args.timeout_seconds)
        return 7
    emit_findings(findings, summary, args)

    # 9) Optional workbook output (003.15 ships F10).
    if args.output_path:
        try:
            from .remarks_writer import write_remarks, write_remarks_streaming
            findings_per_cell = _index_findings_per_cell(findings)
            writer = write_remarks_streaming if args.streaming_output else write_remarks
            writer(Path(args.input), Path(args.output_path), findings_per_cell, args)
        except NotImplementedError:
            sys.stderr.write(
                "NOTE: --output ignored — F10 (remarks writer) lands in 003.15.\n"
            )
        except _AppError as e:
            return _emit_fatal(e, args)

    return _compute_exit_code(summary, args)


def _index_findings_per_cell(findings: list[Any]) -> dict[tuple[str, int, str], list[Any]]:
    """Index per-cell findings for F10 — `{(sheet, row, col): [Finding, ...]}`.
    Grouped findings (`row=None`) are excluded — they have no anchor cell."""
    out: dict[tuple[str, int, str], list[Any]] = {}
    for f in findings:
        if f.row is None or f.column is None:
            continue
        out.setdefault((f.sheet, f.row, f.column), []).append(f)
    return out


if __name__ == "__main__":  # pragma: no cover - exercised via shim
    sys.exit(main())

# Task 003.14a: `cli.py` argparse builder + mutex/dep validation

> **Split origin:** plan-reviewer M-2 (`docs/reviews/plan-003-review.md`) split the original 003.14 (`cli.py` ≤ 500 LOC mega-task) into 003.14a (this — argparse + mutex/dep, target ~200 LOC) and 003.14b (watchdog + `_partial_flush` + `_run` orchestrator + cross-3/4/5/7 envelopes, target ~300 LOC). The M-2 architect-locked watchdog test becomes 003.14b's headline deliverable.

## Use Case Connection
- **I5.1** (argparse mutex/dep validation).
- **I5.2** (`--treat-*-as-date` `,`/`;` separator switch).
- **I5.3** (streaming-incompat combos DEP-4 / DEP-5).
- **R7.a–R7.e** (CLI flags + mutex pairs + dep rules).
- **R6.c partial** (exit 2 `IncompatibleFlags` paths).

## Task Goal
Implement only the **argparse layer** of `cli.py`: `build_parser()`, `parse_args(argv)`, `_HardenedArgParser` (cross-5 routing when `--json-errors`), `_validate_mutex_dep` (MX-A/MX-B + DEP-1..DEP-7 incl. DEP-4/DEP-5 streaming-incompat rejects), and the `--treat-*-as-date` `,`/`;` auto-detection. Wires the shim's re-exports for `build_parser`, `parse_args`, `Args`. **DOES NOT** implement the watchdog, `_run`, `_partial_flush`, or cross-3/4/5/7 envelope routing — those are 003.14b's deliverables. `main()` in this task delegates to `_run` which is still a `NotImplementedError` stub from 003.01.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_check_rules/cli.py`

```python
"""F1 + F11 — CLI surface and pipeline orchestrator.

Argparse builder enforces:
  - 22+ flags (TASK §2.5).
  - Mutex MX-A (--json XOR --no-json), MX-B (--include-hidden XOR --visible-only).
  - DEP-1..7 (TASK §2.5).
  - DEP-4/5 (--streaming-output incompat with --remark-column auto / --append).

Watchdog (architect-locked M-2):
  - SIGALRM (POSIX) or threading.Timer (Windows) sets _TimeoutFlag.
  - Per-rule loop checks the flag between rules / cells.
  - _partial_flush is called from MAIN THREAD post-loop, never from
    the signal handler. stdout opened line-buffered; flush after dump.
"""
from __future__ import annotations
import argparse
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any
from .constants import (DEFAULT_TIMEOUT_SECONDS, DEFAULT_MAX_FINDINGS,
                        DEFAULT_SUMMARIZE_AFTER, SEVERITY_LEVELS)
from .exceptions import (_AppError, RulesParseError, IncompatibleFlags := None,
                         SelfOverwriteRefused, TimeoutExceeded,
                         EncryptedInput, IOError as XlsxIOError)
# (IncompatibleFlags := None pseudo-import — IncompatibleFlags is a subtype
# of RulesParseError carried via details["subtype"]; written without
# walrus, just declarative comment)

__all__ = ["build_parser", "parse_args", "main", "_run", "_partial_flush"]

class _HardenedArgParser(argparse.ArgumentParser):
    """Routes argparse usage errors through _errors.report_error when
    --json-errors is set (DEP-7). Mirrors xlsx-6 cli.py pattern."""
    def __init__(self, *a, **kw):
        self._json_errors = False
        super().__init__(*a, **kw)
    def error(self, message: str):
        if self._json_errors:
            from _errors import report_error
            report_error(2, "RulesParseError", message, subtype="ArgparseUsage")
            sys.exit(2)
        super().error(message)

def build_parser() -> _HardenedArgParser:
    p = _HardenedArgParser(prog="xlsx_check_rules.py", description="...")
    p.add_argument("input", help="path to .xlsx workbook")
    p.add_argument("--rules", required=True, help="path to rules.json|yaml")
    # ... 21+ more flags per TASK §2.5 ...
    return p

def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    parser._json_errors = args.json_errors
    _validate_mutex_dep(args, parser)
    return args

def _validate_mutex_dep(args, parser):
    """MX-A, MX-B, DEP-1..7 cross-checks."""
    # DEP-4 / DEP-5: streaming + auto / append
    if args.streaming_output and args.remark_column == "auto":
        parser.error("--streaming-output requires explicit --remark-column LETTER (cannot auto-pick)")
    if args.streaming_output and args.remark_column_mode == "append":
        parser.error("--streaming-output is incompatible with --remark-column-mode append")
    # ... other cross-checks ...

class _TimeoutFlag:
    def __init__(self):
        self.tripped = False
    def trip(self):
        self.tripped = True

def _install_watchdog(timeout_seconds: int, flag: _TimeoutFlag) -> Any:
    """POSIX: SIGALRM. Windows: daemon Timer. Handler ONLY sets flag."""
    if hasattr(signal, "SIGALRM"):
        def _handler(signum, frame):
            flag.trip()
        signal.signal(signal.SIGALRM, _handler)
        signal.alarm(timeout_seconds)
        return None  # cleanup is signal.alarm(0)
    else:
        timer = threading.Timer(timeout_seconds, flag.trip)
        timer.daemon = True
        timer.start()
        return timer

def _cleanup_watchdog(timer: Any) -> None:
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)
    elif timer is not None:
        timer.cancel()

def _partial_flush(findings, summary, opts, timeout_seconds: int) -> None:
    """M-2 architect lock: called from MAIN THREAD post-loop.
    Sets summary.elapsed_seconds = timeout_seconds; emits all-three-keys
    envelope; flushes stdout."""
    summary["elapsed_seconds"] = timeout_seconds
    summary["truncated"] = False  # not truncated by --max-findings, by timeout
    from .output import emit_findings
    emit_findings(findings, summary, opts)  # emit_findings flushes

def main(argv=None) -> int:
    # Open stdout line-buffered for flush safety on partial-flush
    sys.stdout.reconfigure(line_buffering=True)
    try:
        args = parse_args(argv)
    except _AppError as e:
        return _emit_fatal(e, args=None)
    return _run(args)

def _run(args) -> int:
    """End-to-end pipeline.
    1. cross-3 fail-fast (encryption)
    2. cross-4 .xlsm warning
    3. cross-7 H1 same-path (only if --output)
    4. load rules + build AST (F2 + F3)
    5. unpack + scope-resolve workbook (F6)
    6. install watchdog (M-2 flag-only handler)
    7. for each rule: eval (F7) + aggregate (F8); check timeout flag between rules
    8. cleanup watchdog
    9. emit (F9) — happy path or _partial_flush on timeout
    10. write remarks (F10) if --output
    """
    raise NotImplementedError

def _emit_fatal(err: _AppError, args) -> int:
    """cross-5 envelope wrap when --json-errors. Routes to _errors."""
    raise NotImplementedError
```

#### File: `skills/xlsx/scripts/xlsx_check_rules.py` (shim)

Update the shim's `__all__` re-exports to match the now-implemented surface (final ~25 symbols). Run the shim LOC count check.

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Remove `@unittest.skip` from `TestCli` (argparse-side methods only). Tests for **this task** (003.14a):
- `test_help_prints_full_flag_table` — `--help` mentions every TASK §2.5 flag.
- `test_streaming_with_auto_rejected` (DEP-4) — `--streaming-output --remark-column auto` exits 2 `IncompatibleFlags`.
- `test_streaming_with_append_rejected` (DEP-5) — `--streaming-output --remark-column-mode append` exits 2.
- `test_treat_numeric_as_date_comma_separator` — `--treat-numeric-as-date Hours,Minutes` parses to `{"Hours", "Minutes"}`.
- `test_treat_numeric_as_date_semicolon_separator` — `--treat-numeric-as-date "Q1, 2026;Q2, 2026"` auto-detects `;` (because token contains `,`).
- `test_treat_numeric_as_date_empty_disables` — `--treat-numeric-as-date ''` empty list (per SPEC §8.1).
- `test_json_xor_no_json_mutex` (MX-A) — `--json --no-json` exits 2.
- `test_include_visible_xor_mutex` (MX-B) — `--include-hidden --visible-only` exits 2.
- `test_remark_column_requires_output` (DEP-1) — `--remark-column auto` without `--output` exits 2.
- `test_remark_column_mode_requires_remark_column` (DEP-2) — `--remark-column-mode append` without `--remark-column` exits 2.
- `test_streaming_requires_output` (DEP-3) — `--streaming-output` without `--output` exits 2.
- `test_json_errors_envelope_for_argparse_usage` (DEP-7) — `--json-errors` + bad mutex combo → cross-5 envelope on stderr (not argparse's default text).

The remaining tests (M-2 architect-lock, cross-3/4/5/7, partial-flush, require-data, strict) move to **003.14b**.

#### File: `skills/xlsx/scripts/xlsx_check_rules.py` (shim)

Update the shim's `__all__` to include the now-implemented `build_parser`, `parse_args`. (`main` and `_run` remain stubs delegating to the still-unimplemented orchestrator from 003.14b.)

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Append fixtures #36, #37, #38, #39a, #39b. Most fixtures from earlier tasks now turn green at the E2E level (the full pipeline is wired).

## Test Cases
- Unit: ~ 16 new tests; all pass.
- Battery: most fixtures (#1, #2, #3, #4, #7, #8, #9, #10, #10b, #11–#21, #36, #37, #38, #39a, #39b) green at the E2E level.

## Acceptance Criteria
- [ ] `cli.py` argparse layer complete (~ 200 LOC of the 500-LOC budget).
- [ ] All 22+ flags wired in `build_parser`.
- [ ] MX-A, MX-B mutex enforcement.
- [ ] DEP-1..DEP-7 dependency checks (incl. DEP-4 / DEP-5 streaming-incompat → exit 2 `IncompatibleFlags`).
- [ ] `--treat-*-as-date` `,`/`;` auto-detection works (incl. empty-string disable).
- [ ] `_HardenedArgParser` routes argparse usage errors through `_errors.report_error` when `--json-errors`.
- [ ] All argparse-side tests green; `_run`-dependent tests still skipped (003.14b).
- [ ] `validate_skill.py` exits 0.

## Notes
- Use `sys.stdout.reconfigure(line_buffering=True)` (Python 3.7+) instead of `os.fdopen(1, ...)`. Equivalent effect; cleaner code.
- For the M-2 `test_partial_flush_main_thread_not_signal_handler` test: use a global counter incremented by the handler. After timeout, assert counter == 1 (handler ran once) AND `_partial_flush.was_called_from_main_thread is True`. The latter can be enforced by setting a thread-local in `_partial_flush` checked against `threading.main_thread()`.
- Argparse usage error routing through `_errors.report_error` for `--json-errors` requires subclassing `ArgumentParser` and overriding `.error()`. The shim's existing helpers (in `_errors.py`) accept the kwargs `(code, type_, message, **details)`.
- `_run`'s body is the longest single function. The 500-LOC budget is tight; if you exceed, factor out `_setup`, `_per_rule_loop`, `_finalize` sub-functions. DO NOT spill into a new `orchestrator.py` — keep F1+F11 merged per architecture Q2=A.

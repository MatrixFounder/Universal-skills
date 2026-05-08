# Task 003.14b: `cli.py` watchdog + `_run` orchestrator + cross-3/4/5/7 envelopes

> **Split origin:** plan-reviewer M-2 split. 003.14a delivered the argparse + mutex/dep layer. This task delivers the **architect-locked watchdog pattern** (M-2: handler flag-only, `_partial_flush` main-thread post-loop), the `_run` end-to-end orchestrator, and the cross-3/4/5/7 envelope routing. Headline test: `test_partial_flush_main_thread_not_signal_handler`.

## Use Case Connection
- **I4.3** (exit-code matrix end-to-end).
- **I4.4 routing** (stdout/stderr split).
- **I7.3** (wall-clock timeout).
- **I8.1** (cross-3/4/5/7 envelopes).
- **R6.a–R6.h** (full exit-code matrix).
- **R11.a–R11.d** (cross-skill envelope routing).

## Task Goal
Implement F11 — the end-to-end pipeline orchestrator. Includes the **architect-locked M-2 watchdog**: SIGALRM/Timer **only sets a `_TimeoutFlag`**, the per-rule loop checks the flag, and `_partial_flush` runs in the **main thread** post-loop with stdout flush. cross-3 (encrypted) / cross-4 (.xlsm warning) / cross-5 (`--json-errors`) / cross-7 H1 (same-path) envelopes are routed here.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_check_rules/cli.py`

Add the orchestrator + watchdog pieces (argparse from 003.14a stays):

```python
class _TimeoutFlag:
    def __init__(self):
        self.tripped = False
    def trip(self):
        self.tripped = True

def _install_watchdog(timeout_seconds: int, flag: _TimeoutFlag):
    """POSIX: SIGALRM. Windows: daemon Timer. Handler ONLY sets flag —
    NEVER touches stdout, NEVER calls _partial_flush (M-2 architect lock)."""
    if hasattr(signal, "SIGALRM"):
        def _handler(signum, frame):
            flag.trip()
        signal.signal(signal.SIGALRM, _handler)
        signal.alarm(timeout_seconds)
        return None
    else:
        timer = threading.Timer(timeout_seconds, flag.trip)
        timer.daemon = True
        timer.start()
        return timer

def _cleanup_watchdog(timer):
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)
    elif timer is not None:
        timer.cancel()

def _partial_flush(findings, summary, opts, timeout_seconds: int) -> None:
    """M-2 architect lock: called from MAIN THREAD post-loop only.
    Sets summary.elapsed_seconds = timeout_seconds; emits all-three-keys
    envelope; flushes stdout."""
    # Defensive assertion — fixture #39a's negative case
    assert threading.current_thread() is threading.main_thread(), (
        "_partial_flush MUST run in main thread (M-2 architect lock)"
    )
    summary["elapsed_seconds"] = timeout_seconds
    summary["truncated"] = False
    from .output import emit_findings
    emit_findings(findings, summary, opts)  # emit_findings flushes

def main(argv=None) -> int:
    sys.stdout.reconfigure(line_buffering=True)
    try:
        args = parse_args(argv)
    except _AppError as e:
        return _emit_fatal(e, args=None)
    return _run(args)

def _run(args) -> int:
    """End-to-end pipeline:
    1. cross-3 fail-fast (encryption) -> exit 3
    2. cross-4 .xlsm warning to stderr (non-fatal)
    3. cross-7 H1 same-path (only if --output) -> exit 6
    4. load rules (F2) + build AST (F3)
    5. unpack + scope-resolve workbook (F6)
    6. install watchdog (M-2 flag-only handler)
    7. for each rule: check flag, eval (F7) + aggregate (F8)
    8. cleanup watchdog
    9. emit (F9) — happy path or _partial_flush on timeout
    10. write remarks (F10) if --output
    11. return exit code per matrix
    """
    findings = []
    summary = _new_summary()
    flag = _TimeoutFlag()
    timer = _install_watchdog(args.timeout_seconds, flag)
    try:
        # ... cross-3, cross-4, cross-7 checks ...
        # ... load rules + AST ...
        # ... unpack + workbook ...
        for rule in rule_specs:
            if flag.tripped:
                break
            for cell in iter_cells_for_rule(rule):
                if flag.tripped:
                    break
                # ... eval (F7) + aggregate (F8) ...
    finally:
        _cleanup_watchdog(timer)
    if flag.tripped:
        _partial_flush(findings, summary, args, args.timeout_seconds)
        return 7
    # Happy path
    from .output import emit_findings
    emit_findings(findings, summary, args)
    if args.output:
        _write_output(args, findings_per_cell)
    return _compute_exit_code(summary, args)

def _emit_fatal(err: _AppError, args) -> int:
    """cross-5 envelope wrap when --json-errors. Routes to _errors."""
    from _errors import report_error
    if args is not None and args.json_errors:
        report_error(err.code, err.type_, str(err), **err.details)
    else:
        sys.stderr.write(f"{err.type_}: {err}\n")
    return err.code

def _compute_exit_code(summary, args) -> int:
    """Exit-code matrix:
    0 if no errors and (no warnings OR not --strict)
    1 if errors > 0 OR (--require-data AND checked_cells == 0)
    4 if warnings > 0 AND --strict
    """
    if summary["errors"] > 0:
        return 1
    if args.require_data and summary["checked_cells"] == 0:
        return 1
    if args.strict and summary["warnings"] > 0:
        return 4
    return 0
```

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Remove `@unittest.skip` from the remaining `TestCli` methods (and `TestPartialFlushMainThread`):

- **`test_partial_flush_main_thread_not_signal_handler`** (M-2 architect lock anchor) — test setup runs `_partial_flush` from a forced-signal-handler context (use a small subprocess that catches `SIGALRM` and calls `_partial_flush` directly); assert that the defensive `assert threading.current_thread() is threading.main_thread()` fires `AssertionError`. Flip it: in the normal `_run` path, `_partial_flush` runs main-thread → no AssertionError.
- `test_timeout_emits_partial_envelope_with_three_keys` (M2 / fixture #39a) — `--timeout 0.001 --json` on a 100-rule fixture → exit 7; stdout JSON has `{ok, summary, findings}` all three keys.
- `test_max_findings_zero_emits_three_keys` (M2 / fixture #39b) — `--max-findings 0 --json` → all three keys present.
- `test_cross_3_encrypted_fails_fast` (fixture #38) — encrypted input → exit 3.
- `test_cross_4_xlsm_warning_to_stderr` — `.xlsm` input emits stderr warning; doesn't fail.
- `test_cross_5_json_errors_envelope_wraps_fatal` — `--json-errors` + intentionally bad rules → stdout has cross-5 envelope.
- `test_cross_7_same_path_exits_6` (fixture #37) — `--output` resolves to input → exit 6.
- `test_require_data_emits_no_data_finding` (fixture #36) — empty workbook + `--require-data` → exit 1, finding `no-data-checked`, finding always visible.
- `test_strict_promotes_warning_to_exit_4` — workbook with one warning + `--strict` → exit 4.
- `test_watchdog_handler_does_not_touch_stdout` (M-2 negative) — patch `sys.stdout.write` to track calls; trigger `signal.alarm(1)`; assert handler invocation count is 1 (flag set) AND stdout.write was NOT called from the handler frame.

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Append fixtures #36, #37, #38, #39a, #39b. Most fixtures from earlier tasks now turn green at the E2E level (the full pipeline is wired).

#### File: `skills/xlsx/scripts/tests/test_battery.py`

Remove `@unittest.expectedFailure` from fixtures owned by F1+F11 + cross envelopes: #36, #37, #38, #39, #39a, #39b. (Other fixtures remain xfail until 003.15 / 003.16 / 003.17 ship; final sweep in 003.16a.)

## Test Cases
- Unit: ~ 10 new tests; all pass.
- Battery: fixtures #36, #37, #38, #39, #39a, #39b transition from xfail to xpass.

## Acceptance Criteria
- [ ] `cli.py` orchestrator complete (~ 300 LOC of the 500-LOC budget; total `cli.py` now ~ 500).
- [ ] **M-2 architect lock test green** (`test_partial_flush_main_thread_not_signal_handler`).
- [ ] M2 fixtures #39a / #39b green (all-three-keys envelope on every code path).
- [ ] cross-3, cross-4, cross-5, cross-7 envelopes wired and tested.
- [ ] Exit-code matrix tests pass (R6.a–R6.h).
- [ ] All `TestCli` tests green.
- [ ] `@unittest.expectedFailure` removed from fixtures #36/#37/#38/#39/#39a/#39b in `test_battery.py`.
- [ ] `validate_skill.py` exits 0.

## Notes
- The defensive `assert threading.current_thread() is threading.main_thread()` in `_partial_flush` is belt-and-suspenders — if the architectural pattern is correct it will never fire. But its presence catches a regression that the test alone cannot (the test exercises one path; the assert covers all callers).
- Stdout `reconfigure(line_buffering=True)` at the top of `main()` is the M-2 flush-safety guarantee. If a Developer accidentally removes it the partial-flush envelope can be lost on `os._exit(7)`.
- For `test_watchdog_handler_does_not_touch_stdout`: this is a negative test. The handler should ONLY call `flag.trip()`. If a future Developer adds logging to the handler, this test catches it.
- `_run` does NOT directly call `write_remarks` / `write_remarks_streaming` from F10 in this task — F10 is implemented in 003.15. In 003.14b the `_write_output` call is a `NotImplementedError` stub; tests with `--output` are gated by 003.15 unsticking.

# Task 004.07: `cli.py` — argparse surface + `_run` orchestrator + envelope routing

## Use Case Connection
- **UC-1 / UC-2 / UC-3** (happy paths through the CLI), **UC-4** (stdin envelope), **UC-1 A2** (same-path → exit 6 surfacing through `_run`), every UC's argparse + envelope behaviour.

## Task Goal
Implement F5 + F7 in `json2xlsx/cli.py`: `build_parser()` with all 8 R9 flags, `main(argv)` entrypoint, `_run(args)` linear pipeline. Wire the cross-5 envelope via `_errors.add_json_errors_argument` + `_errors.report_error`. **Closes AQ-2** (`--help` JSONL auto-detect description). **Closes AQ-3** (top-of-`_run` `_AppError` → envelope catch). LOC budget ≤ 320 with `orchestrator.py` split guardrail. **All happy-path E2E tests turn green except `T-roundtrip-xlsx8-synthetic` (deferred to 004.08 along with post-validate).**

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/json2xlsx/cli.py`

Replace stub bodies with full F5+F7 implementation:

```python
"""CLI shim's brain: argparse construction (F5) + linear pipeline (F7).

Imports the cross-5 helper from `_errors` (4-skill replicated, never
edited from here).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# `_errors` lives at the scripts/ level, NOT inside the package.
# The shim (json2xlsx.py) inserts scripts/ into sys.path so this works.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _errors import add_json_errors_argument, report_error  # type: ignore  # noqa: E402

from .coerce import CoerceOptions
from .exceptions import _AppError
from .loaders import read_input, detect_and_parse
from .writer import write_workbook
from .cli_helpers import (
    assert_distinct_paths,
    post_validate_enabled,
    run_post_validate,
)


_DESCRIPTION = (
    "Convert JSON / JSONL input into a styled .xlsx workbook. "
    "Three input shapes are auto-detected: array-of-objects "
    "(single sheet), dict-of-arrays-of-objects (multi-sheet), and "
    "JSONL (one JSON object per line — auto-detected via .jsonl "
    "extension)."
)


def build_parser() -> argparse.ArgumentParser:
    """All 8 R9 flags. Note: `--input-format` is intentionally absent
    (D6 / TASK §0). Auto-detect is documented in the --help body.
    """
    p = argparse.ArgumentParser(
        prog="json2xlsx.py",
        description=_DESCRIPTION,
    )
    p.add_argument(
        "input", type=str,
        help=(
            "Source JSON / JSONL file (or '-' for stdin). "
            "JSONL auto-detected via .jsonl extension; "
            "otherwise dispatch on JSON root token."
        ),
    )
    p.add_argument("output", type=Path, help="Destination .xlsx file.")
    p.add_argument("--sheet", default=None,
                   help="Single-sheet name override (default: 'Sheet1'). "
                        "Ignored for multi-sheet inputs with stderr warning.")
    p.add_argument("--no-freeze", action="store_true",
                   help="Do not freeze the header row.")
    p.add_argument("--no-filter", action="store_true",
                   help="Do not add an auto-filter over the data range.")
    p.add_argument("--no-date-coerce", action="store_true",
                   help="Disable ISO-8601 date-string coercion to Excel "
                        "datetime cells. Strings stay as text.")
    p.add_argument("--date-format", default=None, metavar="NUMBER_FORMAT",
                   help="Override the Excel number_format applied to "
                        "coerced date cells (e.g. 'DD/MM/YYYY').")
    p.add_argument("--strict-dates", action="store_true",
                   help="Under --strict-dates, timezone-aware datetime "
                        "strings AND invalid date-looking strings hard-fail "
                        "with exit 2 instead of silent fallback.")
    p.add_argument("--encoding", default="utf-8",
                   help="Input file encoding (default: utf-8). Ignored when "
                        "input is '-' (stdin always read as UTF-8 bytes).")
    add_json_errors_argument(p)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    """Linear pipeline. Single top-of-function _AppError catch routes
    all typed errors through `_errors.report_error` (AQ-3 lock).
    """
    je: bool = args.json_errors

    try:
        # 1. Same-path guard BEFORE we read 100K rows of input.
        assert_distinct_paths(args.input, args.output)

        # 2. Read raw bytes.
        try:
            raw, source = read_input(args.input, args.encoding)
        except FileNotFoundError as exc:
            return report_error(
                f"Input not found: {exc}",
                code=1, error_type="FileNotFound",
                details={"path": str(exc)}, json_mode=je,
            )
        except OSError as exc:
            return report_error(
                f"Failed to read input: {exc}",
                code=1, error_type="IOError",
                details={"path": args.input}, json_mode=je,
            )

        # 3. Detect & parse.
        is_jsonl = args.input != "-" and args.input.endswith(".jsonl")
        parsed = detect_and_parse(raw, source, is_jsonl_hint=is_jsonl)

        # 4. R7.d: multi-sheet input ignores --sheet with a warning.
        if parsed.shape == "multi_sheet_dict" and args.sheet is not None:
            sys.stderr.write(
                "--sheet ignored when JSON root is multi-sheet dict.\n"
            )
        sheet_override = args.sheet if parsed.shape != "multi_sheet_dict" else None

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
            return report_error(
                f"Failed to write output: {exc}",
                code=1, error_type="IOError",
                details={"path": str(args.output)}, json_mode=je,
            )

        # 7. Optional post-validate hook.
        if post_validate_enabled():
            passed, captured = run_post_validate(args.output)
            if not passed:
                # Cleanup on failure (mirrors xlsx-6).
                try:
                    args.output.unlink()
                except OSError:
                    pass
                return report_error(
                    "Post-validate hook failed",
                    code=7, error_type="PostValidateFailed",
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


if __name__ == "__main__":
    sys.exit(main())
```

#### File: `skills/xlsx/scripts/json2xlsx.py` (shim)

Shim contents finalised in 004.01; in this task no behavioural change is needed — only confirm the shim re-exports the public surface from the package and does NOT contain a function body for `convert_json_to_xlsx` (plan-reviewer #3 lock: single source of truth in `json2xlsx/__init__.py`):

```python
#!/usr/bin/env python3
"""xlsx-2: Convert a JSON / JSONL document into a styled .xlsx workbook."""
from __future__ import annotations

import sys
from pathlib import Path

# Make the sibling scripts/ directory importable when running as
# `python3 json2xlsx.py …` so the package can import _errors / etc.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from json2xlsx import (  # noqa: E402  (re-exports — body lives in package)
    main,
    _run,
    convert_json_to_xlsx,
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


if __name__ == "__main__":
    sys.exit(main())
```

LOC count must stay ≤ 220. The body of `convert_json_to_xlsx` lives in `json2xlsx/__init__.py` (locked 004.01).

### Component Integration

- `cli._run` is the orchestrator; all CLI cases route through it.
- `cli_helpers.run_post_validate` is still stubbed in this task (its logic lands in 004.08); however `_run` already calls it under the `post_validate_enabled()` branch — set `XLSX_JSON2XLSX_POST_VALIDATE=` (off) in all test runs except the dedicated post-validate test (004.08).

## Test Cases

### Unit Tests (turn green in this task)

1. `test_build_parser_flags_locked` — `build_parser()` exposes exactly the 8 documented flags + the two positionals.
2. `test_help_mentions_jsonl_autodetect` — `--help` output contains the string `JSONL auto-detected via .jsonl extension` (AQ-2 lock).
3. `test_run_dispatches_multi_sheet_warning` — multi-sheet input + `--sheet=Custom` produces stderr warning "--sheet ignored when JSON root is multi-sheet dict.".
4. `test_run_single_top_level_apperror_catch` — synthetic `EmptyInput` raised from a mocked `read_input` is caught at the top of `_run` and routed through `report_error` (AQ-3 lock). Verifies the catch is single-point.
5. `test_run_filenotfound_maps_to_io_envelope` — missing input file → exit 1, envelope `type: FileNotFound`.
6. `test_run_writer_oserror_maps_to_io_envelope` — write to unwritable dir → exit 1, envelope `type: IOError`.
7. `test_convert_json_to_xlsx_helper` — programmatic entry point returns 0 on a happy-path call.

### E2E Tests (turn green this task — most of the inventory)

- `T-happy-single-sheet` — full green.
- `T-happy-multi-sheet` — full green.
- `T-happy-jsonl` — full green.
- `T-stdin-dash` — full green.
- `T-same-path` — full green (was green from 004.03; sanity recheck).
- `T-invalid-json` — full green (envelope payload now includes exit code).
- `T-empty-array` — full green.
- `T-iso-dates` — full green.
- `T-strict-dates-aware-rejected` — full green.
- `T-envelope-cross5-shape` — full green (FileNotFound path through `_run`).

### Pending E2E (turn green in 004.08)
- `T-roundtrip-xlsx8-synthetic` (logic green here; full assertion vs golden contract in 004.08).

### Regression Tests
- All xlsx existing tests pass.

## Acceptance Criteria

- [ ] `cli.py` implements `build_parser`, `main`, `_run`. LOC ≤ 320 (ARCH M2 budget).
- [ ] All 8 R9 flags wired and tested.
- [ ] AQ-2 closure: `--help` body mentions `.jsonl` auto-detection.
- [ ] AQ-3 closure: single top-of-`_run` `_AppError` catch.
- [ ] All 7 unit tests above green; 10 of 11 E2E cases green (round-trip synthetic deferred to 004.08).
- [ ] `validate_skill.py` green; eleven `diff -q` silent.
- [ ] **Guardrail check:** if `cli.py` LOC > 320, split `_run` into `orchestrator.py`. Mention the split in the AC notes.

## Notes

- The `sys.path.insert` for `_errors` is unfortunate but matches the precedent: csv2xlsx, xlsx_check_rules, xlsx_add_comment all import `_errors` via the same trick. It's the cost of having shared helpers at `scripts/` level rather than as an installed package.
- The order of operations in `_run` is **deliberate**: same-path guard FIRST (cheap), then read (potentially expensive for 100K-row JSONL), then write (potentially expensive disk I/O). This matches ARCH §2.2 m2 lock.
- Sheet override behaviour edge case: if user passes `--sheet "My Data"` and input is single-sheet, the sheet is named "My Data". If input is multi-sheet, the flag is silently ignored with a stderr warning. R7.d's "avoid silent override" requirement is satisfied by the warning.

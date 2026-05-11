# Task 004.05: `coerce.py` — Type coercion + ISO-date heuristic + strict-dates rejection

## Use Case Connection
- **UC-1** (date coercion + numeric types preserved), **UC-3** (mixed types within a JSONL stream), all UCs through per-cell coercion.

## Task Goal
Implement F3 in `json2xlsx/coerce.py`: per-cell type coercion (preserve native JSON types) + ISO-8601 date / datetime heuristic (default-on; opt-out via `--no-date-coerce`; strict-fail via `--strict-dates`). Boolean-before-int order check (Python `bool ⊂ int` — ARCH §4.1 business rule). Aware-datetime handling: default UTC-naive (R4.e); under `--strict-dates` raise `TimezoneNotSupported` (R4.g / D7). **All `TestCoerce` unit tests turn green.**

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/json2xlsx/coerce.py`

Replace stub bodies with full F3 implementation:

```python
"""Per-cell type coercion (F3).

Inputs: a JSON value (any) + CoerceOptions flags + CellContext for
error diagnostics. Output: a CellPayload — typed value + Excel
number_format string.

This module does NOT import openpyxl. F4 (writer) takes the
CellPayload and applies it to a Worksheet cell.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from dateutil.parser import isoparse  # type: ignore

from .exceptions import TimezoneNotSupported, InvalidDateString


# Date-only:    YYYY-MM-DD
# Datetime:     YYYY-MM-DD[T ]HH:MM:SS[.fff][±HH:MM | Z]
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$"
)

_DEFAULT_DATE_FMT = "YYYY-MM-DD"
_DEFAULT_DATETIME_FMT = "YYYY-MM-DD HH:MM:SS"


@dataclass(frozen=True)
class CellPayload:
    value: Any  # None | bool | int | float | str | date | datetime
    number_format: str | None = None


@dataclass(frozen=True)
class CoerceOptions:
    date_coerce: bool = True
    strict_dates: bool = False
    date_format_override: str | None = None


@dataclass(frozen=True)
class CellContext:
    """Diagnostic carrier used by TimezoneNotSupported / InvalidDateString."""
    sheet: str
    row: int       # 1-indexed (data row, not header)
    column: str    # Excel column letter (A, B, …)


def coerce_cell(value: Any, opts: CoerceOptions, *, ctx: CellContext) -> CellPayload:
    """Return a typed CellPayload for one JSON value.

    Type contract:
      None  → CellPayload(None, None)  -- empty cell
      bool  → CellPayload(bool, None)  -- Excel boolean (note: bool ⊂ int,
                                         so this branch MUST precede int)
      int   → CellPayload(int, None)
      float → CellPayload(float, None)
      str   → maybe date-coerced (see below); else CellPayload(str, None)
      other → CellPayload(repr(value), None)  -- defensive, should never hit
                                                 in practice because JSON
                                                 doesn't produce other types
    """
    if value is None:
        return CellPayload(None, None)
    # bool BEFORE int (Python bool ⊂ int).
    if isinstance(value, bool):
        return CellPayload(value, None)
    if isinstance(value, int):
        return CellPayload(value, None)
    if isinstance(value, float):
        return CellPayload(value, None)
    if isinstance(value, str):
        return _coerce_str(value, opts, ctx)
    # Defensive fallback (never reachable for json.loads output).
    return CellPayload(repr(value), None)


def _coerce_str(s: str, opts: CoerceOptions, ctx: CellContext) -> CellPayload:
    if not opts.date_coerce:
        return CellPayload(s, None)

    dt_payload = _try_iso_date(s) or _try_iso_datetime(s)
    if dt_payload is None:
        # Not a date-looking string.
        if opts.strict_dates and _looks_like_date_attempt(s):
            # Under --strict-dates, a string that looks like a date but
            # doesn't parse is an error rather than silent fall-through.
            raise InvalidDateString(value=s, sheet=ctx.sheet, row=ctx.row, column=ctx.column)
        return CellPayload(s, None)

    value, fmt = dt_payload
    # Aware-tz handling.
    if isinstance(value, datetime) and value.tzinfo is not None:
        if opts.strict_dates:
            raise TimezoneNotSupported(
                value=s, sheet=ctx.sheet, row=ctx.row, column=ctx.column,
                tz_offset=str(value.utcoffset()),
            )
        # Default: convert to UTC, drop tzinfo (Excel has no native tz).
        value = value.astimezone(timezone.utc).replace(tzinfo=None)

    if opts.date_format_override is not None:
        fmt = opts.date_format_override
    return CellPayload(value, fmt)


def _try_iso_date(s: str) -> tuple[date, str] | None:
    if not _DATE_RE.match(s):
        return None
    try:
        d = date.fromisoformat(s)
    except ValueError:
        return None
    return d, _DEFAULT_DATE_FMT


def _try_iso_datetime(s: str) -> tuple[datetime, str] | None:
    if not _DATETIME_RE.match(s):
        return None
    try:
        dt = isoparse(s)
    except (ValueError, TypeError):
        return None
    return dt, _DEFAULT_DATETIME_FMT


def _looks_like_date_attempt(s: str) -> bool:
    """Heuristic: starts with `YYYY-` (4 digits + dash). Used under
    --strict-dates to surface "this looks like a date but doesn't parse".
    """
    if len(s) < 5:
        return False
    return s[:4].isdigit() and s[4] == "-"
```

### Component Integration

- F4 (writer) calls `coerce_cell(value, opts, ctx=CellContext(sheet, row, col))` for every JSON value.
- `opts` is built once per CLI invocation in `cli._run` from argparse flags.
- `ctx` is constructed per-cell inside the writer's row loop (cheap; frozen dataclass).

## Test Cases

### Unit Tests (turn green in this task)

All `TestCoerce` cases from 004.02 turn green, plus a few additions:

1. `test_coerce_int_to_int` — `coerce_cell(42, opts, ctx).value == 42` (type `int`, not `bool`).
2. `test_coerce_bool_to_bool_not_int` — `coerce_cell(True, …).value is True` (type `bool`; CRITICAL bool-before-int ordering).
3. `test_coerce_float_to_float` — `coerce_cell(3.14, …).value == 3.14`.
4. `test_coerce_none_to_none` — `coerce_cell(None, …).value is None`, `.number_format is None`.
5. `test_coerce_iso_date_to_date` — `coerce_cell("2024-01-15", opts, ctx).value == date(2024,1,15)` and `.number_format == "YYYY-MM-DD"`.
6. `test_coerce_iso_datetime_to_datetime` — `coerce_cell("2024-01-15T09:00:00", …).value == datetime(2024,1,15,9,0,0)` and `.number_format == "YYYY-MM-DD HH:MM:SS"`.
7. `test_coerce_aware_dt_default_to_utc_naive` — `coerce_cell("2024-01-15T09:00:00+02:00", …).value == datetime(2024,1,15,7,0,0)` (UTC, naive).
8. `test_coerce_aware_dt_strict_dates_raises` — with `strict_dates=True`, raises `TimezoneNotSupported`.
9. `test_coerce_invalid_date_string_default_passthrough` — `"2024-13-99"` returns CellPayload(str, None).
10. `test_coerce_invalid_date_string_strict_raises` — with `strict_dates=True`, `"2024-13-99"` raises `InvalidDateString` (starts with `YYYY-` heuristic).
11. `test_coerce_no_date_coerce_flag` — with `date_coerce=False`, "2024-01-15" stays as `str`.
12. `test_coerce_date_format_override` — `date_format_override="DD/MM/YYYY"` applied.
13. `test_coerce_non_date_string_passthrough` — `"hello"` returns CellPayload("hello", None) regardless of flags.
14. `test_coerce_naive_dt_unchanged` — naive datetime not converted.

### E2E Tests (turn green this task)
- `T-iso-dates` (with writer landing in 004.06, this turns full-green there; here the coerce-half is verified by unit tests).
- `T-strict-dates-aware-rejected` (depends on CLI 004.07 for `--strict-dates` flag wiring; envelope verification deferred to 004.07).

### Regression Tests
- All existing xlsx tests pass.

## R4.g Split-Attribution Note (plan-reviewer #1)

R4.g (`--strict-dates` rejects aware datetime → `TimezoneNotSupported` exit 2 envelope) is **split** between this task and 004.07:

- **004.05 (this task):** The rejection logic itself. `coerce_cell` raises `TimezoneNotSupported` when `opts.strict_dates and value.tzinfo is not None`. Verified by direct unit test (`test_coerce_aware_dt_strict_dates_raises`) which constructs `CoerceOptions(strict_dates=True)` programmatically.
- **004.07:** The CLI flag wiring (`--strict-dates` argparse), the `_AppError → report_error` envelope routing at the top of `_run`, and the E2E test `T-strict-dates-aware-rejected` that exercises the full path through the CLI.

PLAN.md RTM matrix accurately reflects this split (R4 row attributes to both tasks).

## Acceptance Criteria

- [ ] `coerce.py` implements `coerce_cell`, `_try_iso_date`, `_try_iso_datetime`, `_coerce_str`, `_looks_like_date_attempt` per signatures locked in ARCH §5.
- [ ] `CellPayload`, `CoerceOptions`, `CellContext` are frozen dataclasses with attributes matching ARCH §4.1 + R4 / R3 / D7.
- [ ] All 14 TestCoerce cases green.
- [ ] bool-before-int rule verified by `test_coerce_bool_to_bool_not_int`.
- [ ] LOC count of `coerce.py` ≤ 220.
- [ ] `validate_skill.py` green; eleven `diff -q` silent.

## Notes

- `python-dateutil`'s `isoparse` handles the awkward bits of ISO-8601 (fractional seconds, `Z`, `±HH:MM`) that hand-rolled parsing screws up. Already pinned in `requirements.txt` from xlsx-7.
- The `_DATE_RE` / `_DATETIME_RE` regexes are intentionally narrow — they accept ONLY canonical ISO-8601 forms. `"2024-1-15"` (no zero-pad), `"15/01/2024"`, `"Jan 15 2024"` all fall through to plain string. Users wanting a different format use `--date-format` for OUTPUT formatting but xlsx-2 doesn't try to PARSE non-ISO inputs as dates (that road leads to madness — see `pd.to_datetime` locale heuristics).
- The `_looks_like_date_attempt` heuristic for `--strict-dates` is intentionally conservative: it flags strings starting with `YYYY-` so e.g. `"2024-13-99"` (typo) and `"2024-Jan-15"` (wrong format) both raise; but `"Tomorrow"` does not (no `YYYY-` prefix → passes through as string).
- Honest scope §11.1 carry-forward: a `--keep-timezone` flag that would store the offset as a sibling column is OUT of scope v1; documented in TASK §11.1.

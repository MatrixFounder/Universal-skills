"""xlsx-2 per-cell type coercion (F3).

Inputs: a JSON value (any) + CoerceOptions flags + CellContext for
error diagnostics. Output: a CellPayload — typed value + Excel
number_format string.

This module does NOT import openpyxl. F4 (writer) takes the
CellPayload and applies it to a Worksheet cell.

Type contract (R3 + R4 + D7):
  None  → CellPayload(None, None)              -- empty cell
  bool  → CellPayload(bool, None)              -- bool ⊂ int in Python;
                                                  bool branch MUST come
                                                  BEFORE int (ARCH §4.1)
  int   → CellPayload(int, None)
  float → CellPayload(float, None)
  str   → maybe date-coerced (see _coerce_str)
  other → repr(value) wrapped in CellPayload  -- defensive; json.loads
                                                  cannot produce these

Date-coercion is opt-in-default. ISO-date matches:
  YYYY-MM-DD
  YYYY-MM-DD[T ]HH:MM:SS(.fff)?(Z|±HH:MM)?

Aware datetimes:
  default       → astimezone(UTC).replace(tzinfo=None) (R4.e)
  --strict-dates → TimezoneNotSupported envelope exit 2 (D7 / R4.g)

Invalid date-looking strings:
  default       → silent passthrough as text (R4.f)
  --strict-dates → InvalidDateString envelope iff input starts with
                   `YYYY-` (the conservative "looks like a date attempt"
                   heuristic — strict mode rejects "2024-13-99" /
                   "2024-Jan-15" but ignores arbitrary plain strings).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from dateutil.parser import isoparse  # type: ignore[import-untyped]

from .exceptions import InvalidDateString, TimezoneNotSupported


# ISO-8601 narrow forms. Hand-written regexes pin the canonical shapes
# the spec promises to honour. Anything else (e.g., "2024-1-15" or
# "15/01/2024") falls through to plain string — see honest-scope note
# in module docstring.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$"
)

# Excel number-format strings (not strftime).
_DEFAULT_DATE_FMT = "YYYY-MM-DD"
_DEFAULT_DATETIME_FMT = "YYYY-MM-DD HH:MM:SS"


@dataclass(frozen=True)
class CellPayload:
    """Output of F3 for one JSON value. F4 applies (value, number_format)
    to an openpyxl cell — F3 never touches openpyxl directly.
    """
    value: Any  # None | bool | int | float | str | date | datetime
    number_format: str | None = None


@dataclass(frozen=True)
class CoerceOptions:
    """Per-invocation knobs F3 obeys, threaded through from CLI flags.

    `date_coerce`: when True (default), ISO-date strings → Excel dates.
    `strict_dates`: when True (D7), aware datetimes AND `YYYY-`-prefixed
        invalid strings hard-fail with typed `_AppError`s.
    `date_format_override`: when set, replaces the auto-picked Excel
        number_format for date AND datetime cells (single override
        applies uniformly to both; e.g., `"DD/MM/YYYY"` on a datetime
        value drops the time component in Excel's display — the
        underlying datetime is preserved but Excel renders only the
        date part). Document for v2: per-type override is out of scope.
    """
    date_coerce: bool = True
    strict_dates: bool = False
    date_format_override: str | None = None


@dataclass(frozen=True)
class CellContext:
    """Diagnostic carrier — populates the `details` payload of
    `TimezoneNotSupported` / `InvalidDateString` envelopes (R4.g).

    `row` is the 1-indexed DATA row (not the worksheet row — header
    is excluded; row 1 is the first data record).
    """
    sheet: str
    row: int
    column: str  # Excel column letter (A, B, …)


def coerce_cell(
    value: Any,
    opts: CoerceOptions,
    *,
    ctx: CellContext,
) -> CellPayload:
    """Return a typed CellPayload for one JSON value.

    See module docstring for the type-contract table.
    """
    if value is None:
        return CellPayload(None, None)
    # bool BEFORE int — Python's `bool` IS an `int`, so flipping the
    # order would classify True/False as numbers (Excel 'n' cell with
    # value 1/0) and silently lose the boolean semantic the user
    # encoded in JSON.
    if isinstance(value, bool):
        return CellPayload(value, None)
    if isinstance(value, int):
        return CellPayload(value, None)
    if isinstance(value, float):
        return CellPayload(value, None)
    if isinstance(value, str):
        return _coerce_str(value, opts, ctx)
    # Defensive — json.loads emits only None / bool / int / float / str
    # / list / dict. List/dict shouldn't reach here (F2 unrolls them).
    # Any other type (e.g., NaN from `parse_constant` overrides) gets
    # stringified rather than crashing the writer.
    return CellPayload(repr(value), None)


def _coerce_str(s: str, opts: CoerceOptions, ctx: CellContext) -> CellPayload:
    if not opts.date_coerce:
        return CellPayload(s, None)

    dt_payload = _try_iso_date(s) or _try_iso_datetime(s)
    if dt_payload is None:
        # Not a recognised ISO-date form. Under --strict-dates, surface
        # `YYYY-` prefixed garbage as InvalidDateString rather than
        # letting it silently land in a text cell.
        if opts.strict_dates and _looks_like_date_attempt(s):
            raise InvalidDateString(
                value=s, sheet=ctx.sheet, row=ctx.row, column=ctx.column,
            )
        return CellPayload(s, None)

    value, fmt = dt_payload
    if isinstance(value, datetime) and value.tzinfo is not None:
        # Aware datetime. D7: strict → hard-fail; default → drop tz.
        if opts.strict_dates:
            tz_offset = value.utcoffset()
            raise TimezoneNotSupported(
                value=s, sheet=ctx.sheet, row=ctx.row, column=ctx.column,
                tz_offset=str(tz_offset) if tz_offset is not None else "",
            )
        # Default: store the equivalent UTC instant, naive. Excel has
        # no native timezone type — any cross-tool fidelity is best-
        # effort. (Honest scope §11.1.)
        value = value.astimezone(timezone.utc).replace(tzinfo=None)

    if opts.date_format_override is not None:
        fmt = opts.date_format_override
    return CellPayload(value, fmt)


def _try_iso_date(s: str) -> tuple[date, str] | None:
    """Parse a strict `YYYY-MM-DD` string into a `date` + default fmt.

    Date-only path uses `date.fromisoformat` (stdlib, no dateutil) for
    speed — the hot path is hit once per cell in a 100K-row JSONL.
    """
    if not _DATE_RE.match(s):
        return None
    try:
        d = date.fromisoformat(s)
    except ValueError:
        return None
    return d, _DEFAULT_DATE_FMT


def _try_iso_datetime(s: str) -> tuple[datetime, str] | None:
    """Parse `YYYY-MM-DD[T ]HH:MM:SS[.fff][±HH:MM|Z]` into a `datetime`.

    Uses `dateutil.parser.isoparse` rather than `datetime.fromisoformat`
    so the rich variants (trailing `Z`, fractional seconds, offset
    forms) parse uniformly across CPython versions — `fromisoformat`
    accepted `Z` only from Python 3.11. xlsx-7 already pins
    `python-dateutil>=2.8.0` in `requirements.txt`.
    """
    if not _DATETIME_RE.match(s):
        return None
    try:
        dt = isoparse(s)
    except (ValueError, TypeError):
        return None
    return dt, _DEFAULT_DATETIME_FMT


def _looks_like_date_attempt(s: str) -> bool:
    """Heuristic for `--strict-dates` only: does this string look like
    the user TRIED to write a date and failed?

    Conservative: requires the first 4 characters to be digits followed
    by `-`. Catches "2024-13-99" / "2024-Jan-15" / "2024-99-01"; ignores
    "Tomorrow", "next-week", "2024" (no dash), "abc-def-ghi". The
    rationale is to avoid raising `InvalidDateString` on arbitrary
    plain strings under strict mode.
    """
    if len(s) < 5:
        return False
    return s[:4].isdigit() and s[4] == "-"


__all__ = [
    "CellPayload",
    "CoerceOptions",
    "CellContext",
    "coerce_cell",
]

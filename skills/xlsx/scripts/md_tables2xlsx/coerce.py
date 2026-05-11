"""xlsx-3 F6 — per-column cell coercion.

task-005-05: full bodies for `coerce_column`, `_coerce_cell_numeric`,
`_coerce_cell_date`, `_handle_aware_tz`, `_has_leading_zero`.

Mirrors csv2xlsx + json2xlsx behaviour:
- Leading-zero column → stays text (csv2xlsx parity; column-level
  gate runs BEFORE per-cell coercion — ARCH m10 lock).
- Numeric `^-?\\d+(?:[.,]\\d+)?$` → int/float (comma → dot).
- ISO-date strict-regex pre-filter → `dateutil.isoparse`.
- Aware datetime → UTC-naive (D7 default; v1 ships NO `--strict-dates`
  flag — R9.f lock).
- Empty string → `None` (not `""`).
- `--no-coerce` → every value kept as `str` (None for empty).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional


_NUMERIC_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"(\.\d+)?([+-]\d{2}:?\d{2}|Z)?$"
)


@dataclass(frozen=True)
class CoerceOptions:
    """F6 configuration."""
    coerce: bool = True
    encoding: str = "utf-8"


def _has_leading_zero(values: list[str]) -> bool:
    """csv2xlsx parity column-level gate.

    Returns True iff the FIRST non-empty value (after stripping an
    optional leading `-` sign per vdd-multi L1 review-fix) starts
    with `0` followed by a non-`.`/non-`,` digit AND has length > 1
    after sign-strip (e.g. `"007"`, `"-007"`, `"0123456789"`).
    Matches `csv2xlsx::_coerce_column` precedent extended to also
    catch negative leading-zero values.
    """
    non_empty = [v.strip() for v in values if v.strip()]
    if not non_empty:
        return False
    first = non_empty[0].lstrip("-")
    return (
        first.startswith("0")
        and len(first) > 1
        and first[1] not in ".,"
    )


def _coerce_cell_numeric(v: str) -> Optional[float]:
    """Strict numeric regex pre-filter, then int/float parse.
    Returns int / float / None (None means "not numeric")."""
    if not _NUMERIC_RE.match(v):
        return None
    normalised = v.replace(",", ".")
    if "." in normalised:
        return float(normalised)
    return int(normalised)


def _handle_aware_tz(dt: datetime) -> datetime:
    """Convert aware datetime to UTC then strip tzinfo (D7
    default-mode; R9.f lock — v1 ships NO `--strict-dates` flag)."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _coerce_cell_date(v: str):
    """Strict ISO regex pre-filter, then dateutil.isoparse.
    Returns datetime.date / datetime.datetime / None.

    The strict pre-filter ensures dateutil's lenient `"May 11"`-style
    parsing does NOT fire — only true ISO-8601 strings are coerced.
    """
    if _ISO_DATE_RE.match(v):
        # Pure date — return date, not datetime, so writer can apply
        # date-only number_format.
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    if _ISO_DATETIME_RE.match(v):
        # dateutil for tz support; lazy import to keep cold-start fast.
        from dateutil import parser as _dtu_parser
        try:
            dt = _dtu_parser.isoparse(v)
        except (ValueError, TypeError):
            return None
        if not isinstance(dt, datetime):
            return None
        return _handle_aware_tz(dt)
    return None


def coerce_column(values: list[str], opts: CoerceOptions) -> list[object]:
    """Column-level coercion entry point.

    Algorithm (ARCH m10 gate-then-coerce order):
      1. If `not opts.coerce` → `[v if v else None for v in values]`.
      2. Else if `_has_leading_zero(values)` → keep whole column as
         text (csv2xlsx parity).
      3. Else per-cell: try numeric → date → str fallthrough.
    """
    if not opts.coerce:
        return [v if v else None for v in values]
    if _has_leading_zero(values):
        return [v.strip() if v.strip() else None for v in values]

    # Detect mixed-numeric column (some values match numeric, some
    # don't) — if ANY non-empty value doesn't match numeric AND
    # doesn't match date, the column is mixed; keep all as their
    # natural per-cell coercion result (numeric stays numeric, str
    # stays str, etc.). This matches the simpler "best-effort" mode
    # for markdown which often has mixed content.
    out: list[object] = []
    for raw in values:
        s = raw.strip()
        if not s:
            out.append(None)
            continue
        num = _coerce_cell_numeric(s)
        if num is not None:
            out.append(num)
            continue
        dt = _coerce_cell_date(s)
        if dt is not None:
            out.append(dt)
            continue
        out.append(s)
    return out

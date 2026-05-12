"""F6 — cell value extraction with number-format heuristic.

`extract_cell(cell, *, include_formulas, include_hyperlinks,
datetime_format) -> tuple[value, warning_or_None]` is the workhorse
called once per cell. Pipeline:

1. **Formula handling.** If `data_type == "f"`:
   - If `include_formulas=True` → return the formula string verbatim.
   - Elif cached value is `None` → return `(None, "stale cache...")`.
   - Else → fall through to value-extraction on the cached value.
2. **Hyperlink.** If `include_hyperlinks=True` and `cell.hyperlink is
   not None` → return `cell.hyperlink.target`.
3. **Rich-text.** If `cell.value` is a `CellRichText` (or list of
   `TextBlock`-like spans) → concatenate `.text` of each span.
4. **Number format.** Apply the heuristic — decimal with thousands,
   percent, leading-zero string-coerce, date pattern → routed to
   `_apply_datetime_format`, else raw value.
5. **Datetime.** If the value is a `datetime` or `date` → format per
   `datetime_format` (`ISO` / `excel-serial` / `raw`).

Divergence from xlsx-7's `cell_types.py`:
- xlsx-7 uses a 6-type classifier (`number`, `date`, `text`,
  `boolean`, `error`, `empty`) for predicate-eval semantics. This
  module focuses on **emit-formatting** (returning the value the
  caller will serialise to JSON / CSV / Markdown), so its heuristic
  is simpler and format-string-driven.
- xlsx-7 has a `--treat-text-as-date` opt-in for locale-broken
  workbooks. This module does NOT — caller's `datetime_format`
  controls only the output shape, never the input parsing.
- This module surfaces `(value, warning_or_None)` so callers (009-08
  `read_table`) can lift warnings into `TableData.warnings`.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from ._types import DateFmt

# Excel's date epoch is 1899-12-30 (not 1900-01-01) — the off-by-2
# accounts for the 1900-leap-year bug Excel inherits from Lotus 1-2-3.
_EXCEL_EPOCH = datetime(1899, 12, 30)

# Heuristic regexes for openpyxl number-format strings.
_RE_DECIMAL_THOUSANDS = re.compile(r"^#,##0(\.0+)?(_\)|[ ;\)\$]*)?$")
_RE_DECIMAL_ONLY = re.compile(r"^0(\.0+)?$")
_RE_PERCENT = re.compile(r"^0(\.0+)?%$")
# Leading-zero text formats (e.g. "00000" for zip codes); must match
# `0+` exactly and NOT contain `.` (decimals) or `%` (percent).
_RE_LEADING_ZERO = re.compile(r"^0{2,}$")
# Date-format placeholders: any of y/m/d/h/s on their own (case-
# insensitive). The regex deliberately requires at least 1 placeholder
# but tolerates separators (`-`, `/`, `:`, space, `\`, `[`, `]`, etc.)
# common in Excel date formats.
_RE_DATE = re.compile(r"[yYmMdDhHsS]")


def extract_cell(
    cell: Any,
    *,
    include_formulas: bool = False,
    include_hyperlinks: bool = False,
    datetime_format: DateFmt = "ISO",
) -> tuple[Any, str | None]:
    """Extract a cell into `(value, warning_or_None)`.

    Formula handling depends on the workbook's `keep_formulas` flag
    (set at `open_workbook` time):

    - Default (`keep_formulas=False`, openpyxl `data_only=True`):
      `cell.value` is the **cached** computed value; formula strings
      are not preserved. `include_formulas=True` has no effect here —
      the formula was discarded at parse time.

    - `keep_formulas=True` (openpyxl `data_only=False`): `cell.value`
      is the **formula string** for formula cells (e.g. `"=A1+B1"`),
      and `cell.data_type == "f"`. Cached values are inaccessible.
      `include_formulas=True` returns the formula string verbatim;
      `include_formulas=False` returns `None` with a warning (the
      caller asked for a cached value the loader does not have).

    Stale-cache detection is a `keep_formulas=True` concept — when
    the formula string is present but the caller wanted a cached
    value, the warning informs them to reopen the workbook with
    `keep_formulas=False`.
    """
    # 1. Formula handling — only triggers in `keep_formulas=True` mode.
    data_type = getattr(cell, "data_type", None)
    raw_value = getattr(cell, "value", cell)
    if data_type == "f":
        if include_formulas:
            return (raw_value, None)
        # Caller wanted the cached value but the workbook was loaded
        # with formulas preserved → cached value is inaccessible.
        return (
            None,
            f"stale cache: formula at {getattr(cell, 'coordinate', '?')!r} "
            f"present but cached value inaccessible "
            f"(reopen with keep_formulas=False)",
        )

    # 2. Hyperlink takes precedence over display text when opted in.
    if include_hyperlinks:
        hl = getattr(cell, "hyperlink", None)
        if hl is not None:
            target = getattr(hl, "target", None)
            if target:
                return (target, None)

    # 3. Rich text.
    rich = _flatten_rich_text(raw_value)
    if rich is not raw_value:
        return (rich, None)

    # 4 + 5. Number format + datetime.
    number_format = getattr(cell, "number_format", "General") or "General"
    return (_apply_number_format(raw_value, number_format, datetime_format), None)


def _apply_number_format(value: Any, number_format: str, datetime_format: DateFmt) -> Any:
    """Route value through the format heuristic; return formatted value or raw."""
    if value is None:
        return None

    # Datetime / date path — number_format hints + Python type both
    # qualify (a datetime cell almost always carries a date-pattern
    # number format, but we don't require it).
    if isinstance(value, (datetime, date)):
        return _apply_datetime_format(value, datetime_format)

    # **S-L4 fix:** defensive cap. OOXML doesn't bound number-format
    # length and a malicious workbook could carry a multi-MB format
    # string. Real-world formats are < 64 chars; 256 is generous.
    if len(number_format) > 256:
        number_format = "General"

    # **L-H3 fix:** strip Excel quoted-literals (`"Day"`, `"$"USD`)
    # before testing for date placeholders — otherwise `_RE_DATE`
    # matches the literal `d` inside `"Day"` and routes a numeric ID
    # cell through the date pipeline. Strip `"..."` AND `\X` escapes
    # alongside the existing `[brackets]` prefix removal.
    stripped = re.sub(r'"[^"]*"', "", number_format)        # quoted literals
    stripped = re.sub(r"\\.", "", stripped)                  # backslash-escaped chars
    stripped = re.sub(r"\[[^\]]*\]", "", stripped)           # locale/colour
    # **L-M5 fix:** Excel uses `;` to separate positive / negative /
    # zero / text sections in number formats. We only classify on the
    # positive section (Excel applies it first; downstream callers
    # serialise non-negative values mostly).
    stripped = stripped.split(";", 1)[0].strip()

    # Pure date format → openpyxl gave us a float (Excel serial); this
    # branch is rarely hit because openpyxl usually returns datetime
    # objects directly, but defensive routing keeps the contract.
    if _RE_DATE.search(stripped) and not _RE_PERCENT.match(stripped):
        if isinstance(value, (int, float)):
            try:
                # **L-H2 fix:** preserve fractional time-of-day. The
                # historical `int(value)` truncated hh:mm to midnight.
                dt = _EXCEL_EPOCH + timedelta(days=float(value))
                return _apply_datetime_format(dt, datetime_format)
            except (ValueError, OverflowError):
                return value

    # Percent.
    if _RE_PERCENT.match(stripped):
        # Count decimals after the `.0...` group.
        m = re.search(r"\.(0+)%$", stripped)
        decimals = len(m.group(1)) if m else 0
        try:
            return f"{float(value) * 100:.{decimals}f}%"
        except (TypeError, ValueError):
            return value

    # Decimal with thousands separator.
    if _RE_DECIMAL_THOUSANDS.match(stripped) or _RE_DECIMAL_ONLY.match(stripped):
        m = re.search(r"\.(0+)$", stripped)
        decimals = len(m.group(1)) if m else 0
        try:
            return f"{float(value):,.{decimals}f}"
        except (TypeError, ValueError):
            return value

    # Leading-zero text format ("00000", "000", …).
    if _RE_LEADING_ZERO.match(stripped):
        try:
            return f"{int(value):0{len(stripped)}d}"
        except (TypeError, ValueError):
            return value

    # General / fallback → raw value verbatim.
    return value


def _apply_datetime_format(dt: datetime | date, fmt: DateFmt) -> Any:
    """Convert a datetime / date to the caller-requested form."""
    if fmt == "raw":
        return dt
    if fmt == "ISO":
        return dt.isoformat()
    if fmt == "excel-serial":
        if isinstance(dt, datetime):
            delta = dt - _EXCEL_EPOCH
        else:
            delta = datetime(dt.year, dt.month, dt.day) - _EXCEL_EPOCH
        return delta.total_seconds() / 86400.0
    raise ValueError(f"Unknown datetime_format: {fmt!r}")


def _flatten_rich_text(value: Any) -> Any:
    """Concatenate rich-text spans into a plain string; pass-through otherwise.

    openpyxl exposes rich-text as `CellRichText` — a list-like of
    `TextBlock` / `InlineFont`-wrapped strings. We duck-type on
    iter+`.text` because the class hierarchy varies by openpyxl
    minor release.
    """
    # Plain strings / numbers / None → no-op (identity-return so the
    # caller can detect "rich-text was processed" via `is`).
    if value is None or isinstance(value, (str, int, float, bool, datetime, date)):
        return value
    if not hasattr(value, "__iter__"):
        return value
    try:
        parts: list[str] = []
        for span in value:
            if isinstance(span, str):
                parts.append(span)
            else:
                text = getattr(span, "text", None)
                if text is not None:
                    parts.append(str(text))
                else:
                    parts.append(str(span))
        return "".join(parts)
    except TypeError:
        return value

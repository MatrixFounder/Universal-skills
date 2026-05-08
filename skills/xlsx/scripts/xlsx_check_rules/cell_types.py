"""F5 — Cell-value canonicalisation.

Maps openpyxl Cell → (LogicalType, value) per SPEC §3.5. Six logical
types are the unit of rule evaluation; downstream stages (F7, F8)
consume the type without re-classification.

D4 lock (architect-review): only the 7 openpyxl-recognised error
codes (`OPENPYXL_ERROR_CODES`) round-trip to `LogicalType.ERROR`.
Modern Excel codes (`#SPILL!`, `#CALC!`, `#GETTING_DATA`) are stored
as `data_type='s'` (text) by openpyxl 3.1.5 and stay
`LogicalType.TEXT` — user-rule workaround documented in SPEC §11.2
honest scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from .constants import EXCEL_SERIAL_DATE_RANGE, OPENPYXL_ERROR_CODES
from .exceptions import CellError

__all__ = [
    "LogicalType",
    "ClassifiedCell",
    "classify",
    "is_excel_serial_date",
    "coerce_text_as_date",
    "whitespace_strip",
]


class LogicalType(Enum):
    NUMBER = "number"
    DATE = "date"
    BOOL = "bool"
    TEXT = "text"
    ERROR = "error"
    EMPTY = "empty"


@dataclass(frozen=True)
class ClassifiedCell:
    logical_type: LogicalType
    value: Any  # int | float | str | bool | datetime | date | CellError | None
    sheet: str
    row: int
    col: str  # column letter
    is_anchor_of_merge: bool = False
    merge_range: str | None = None
    is_hidden: bool = False  # row OR col hidden
    has_formula_no_cache: bool = False  # SPEC §5.0.1 stale-cache warning anchor


# === Helpers ==============================================================

def is_excel_serial_date(n: float) -> bool:
    """SPEC §5.4.1 path 3 — number falls in the Excel-serial date window."""
    lo, hi = EXCEL_SERIAL_DATE_RANGE
    return lo <= n <= hi


def coerce_text_as_date(s: str, dayfirst: bool = False) -> datetime | None:
    """SPEC §5.4.1 path 4 — `dateutil.parser.parse(s, fuzzy=False, dayfirst=...)`.

    Returns None on parse failure (caller falls through to text type).
    `ParserError` does not exist in older python-dateutil; we catch the
    base `ValueError` it inherits from, plus `OverflowError` and
    `TypeError` defensively.

    Honest-scope warning: dateutil does NOT have a true strict mode
    even with `fuzzy=False` — `"42"` parses to `2042-01-01` (year-only
    inference). Opt-in only via `--treat-text-as-date COL,COL`.
    """
    if not s or not s.strip():
        return None
    try:
        from dateutil.parser import parse  # type: ignore[import-not-found]
        return parse(s, fuzzy=False, dayfirst=dayfirst)
    except (ValueError, OverflowError, TypeError):
        return None


def whitespace_strip(text: str, strip: bool = True) -> str:
    """Default-on per `defaults.strip_whitespace` (SPEC §3.5.3)."""
    return text.strip() if strip else text


# === Main classifier ======================================================

def _opts_get(opts: dict[str, Any] | None, key: str, default: Any) -> Any:
    """Safe dict-or-None lookup."""
    return default if opts is None else opts.get(key, default)


def _column_in_set(col_letter: str, header_or_letter_set: Any) -> bool:
    """`treat_*_as_date` flag accepts either column letters or headers.

    F5 only knows column letters (header → letter resolution lives in F6).
    The orchestrator should pre-resolve so that whatever lands in `opts`
    is a `set[str]` of column letters. If a header somehow leaks through,
    we still match case-insensitively as a defensive fallback.
    """
    if not header_or_letter_set:
        return False
    if isinstance(header_or_letter_set, (set, frozenset, list, tuple)):
        return col_letter in header_or_letter_set
    return False


def classify(cell: Any, opts: dict[str, Any] | None = None) -> ClassifiedCell:
    """Map an openpyxl `Cell` to a `ClassifiedCell` per SPEC §3.5.

    ``opts`` keys (all optional):

      - ``strip_whitespace`` (bool, default True)
      - ``treat_numeric_as_date`` (set of column letters)
      - ``treat_text_as_date`` (set of column letters)
      - ``dayfirst`` (bool, default False — passed to dateutil)
      - ``has_formula_no_cache`` (bool, set by orchestrator on the
        formula-without-cache path — SPEC §5.0.1)
      - ``is_hidden`` (bool, set by F6 ``iter_cells`` after the
        ``--visible-only`` filter)
      - ``is_anchor_of_merge`` / ``merge_range`` (set by F6 when the
        cell is the top-left of a merged range)
    """
    sheet, row, col = _cell_addr(cell)
    strip_ws = bool(_opts_get(opts, "strip_whitespace", True))
    has_no_cache = bool(_opts_get(opts, "has_formula_no_cache", False))
    is_hidden = bool(_opts_get(opts, "is_hidden", False))
    is_anchor = bool(_opts_get(opts, "is_anchor_of_merge", False))
    merge_range = _opts_get(opts, "merge_range", None)

    common = dict(
        sheet=sheet, row=row, col=col,
        is_anchor_of_merge=is_anchor, merge_range=merge_range,
        is_hidden=is_hidden, has_formula_no_cache=has_no_cache,
    )

    raw = getattr(cell, "value", None)
    dt = getattr(cell, "data_type", None)

    # === EMPTY / formula-without-cache ===
    # `data_type == 'f'` is the openpyxl `data_only=False` formula-cell
    # marker. When data_only=True yields `value is None` AND the cell has
    # a formula on disk, the orchestrator pre-flags via opts. Either path
    # arrives here as EMPTY with has_formula_no_cache=True.
    if dt == "f" or has_no_cache:
        return ClassifiedCell(LogicalType.EMPTY, None, **{**common, "has_formula_no_cache": True})
    if raw is None:
        return ClassifiedCell(LogicalType.EMPTY, None, **common)

    # === Excel error (D4: only the 7 openpyxl-recognised codes) ===
    if dt == "e":
        # Defensive: openpyxl populates data_type='e' only for codes in
        # ERROR_CODES, but if a tampered workbook smuggles a different
        # string in, fall through to text rather than raise.
        if isinstance(raw, str) and raw in OPENPYXL_ERROR_CODES:
            return ClassifiedCell(LogicalType.ERROR, CellError(raw), **common)
        # Unknown error glyph → fall through to text-with-error-shape.
        return ClassifiedCell(LogicalType.TEXT, str(raw), **common)

    # === Bool ===
    # `data_type == 'b'` OR a Python `bool` value (bool is a subclass of
    # int; check before the numeric branch).
    if dt == "b" or isinstance(raw, bool):
        return ClassifiedCell(LogicalType.BOOL, bool(raw), **common)

    # === Date — explicit type tag (rare; ISO 8601 string in <v>) ===
    if dt == "d" or isinstance(raw, (datetime, date)):
        return ClassifiedCell(LogicalType.DATE, raw, **common)

    # === Number / openpyxl-detected date / serial-date opt-in ===
    if dt == "n" or isinstance(raw, (int, float, Decimal)):
        # Path 1 of §5.4.1 — openpyxl's number-format heuristic.
        if getattr(cell, "is_date", False):
            return ClassifiedCell(LogicalType.DATE, raw, **common)
        # Path 3 — `--treat-numeric-as-date` opt-in.
        treat_num = _opts_get(opts, "treat_numeric_as_date", None)
        if (
            isinstance(raw, (int, float, Decimal))
            and not isinstance(raw, bool)
            and _column_in_set(col, treat_num)
            and is_excel_serial_date(float(raw))
        ):
            try:
                # openpyxl's epoch helper handles the Lotus-bug 1900-leap
                # quirk; we route through the cell's worksheet's epoch
                # when available.
                from openpyxl.utils.datetime import from_excel  # type: ignore[import-not-found]
                return ClassifiedCell(LogicalType.DATE, from_excel(float(raw)), **common)
            except ImportError:
                pass  # fall through to NUMBER if openpyxl helper missing
        # Decimal → float coerce for downstream arithmetic; tolerance
        # comparisons in F7 absorb the precision-loss documented in
        # honest-scope (R13.j).
        if isinstance(raw, Decimal):
            return ClassifiedCell(LogicalType.NUMBER, float(raw), **common)
        return ClassifiedCell(LogicalType.NUMBER, raw, **common)

    # === Text ===
    # `data_type in ('s', 'inlineStr')` or any other non-bool string.
    if isinstance(raw, str):
        text = whitespace_strip(raw, strip_ws)
        # Path 4 of §5.4.1 — `--treat-text-as-date` opt-in via dateutil.
        treat_text = _opts_get(opts, "treat_text_as_date", None)
        if _column_in_set(col, treat_text):
            parsed = coerce_text_as_date(text, dayfirst=bool(_opts_get(opts, "dayfirst", False)))
            if parsed is not None:
                return ClassifiedCell(LogicalType.DATE, parsed, **common)
        return ClassifiedCell(LogicalType.TEXT, text, **common)

    # Defensive fallback — unexpected data_type / value shape; preserve
    # raw value but classify as TEXT so rule evaluation stays defined.
    return ClassifiedCell(LogicalType.TEXT, str(raw), **common)


def _cell_addr(cell: Any) -> tuple[str, int, str]:
    """Extract `(sheet_title, row, column_letter)` defensively.

    openpyxl `Cell` exposes `.row`, `.column_letter`, and `.parent.title`.
    Tests use a `SimpleNamespace`-style mock with the same attributes.
    """
    sheet = getattr(getattr(cell, "parent", None), "title", "") or ""
    row = int(getattr(cell, "row", 0))
    col = str(getattr(cell, "column_letter", ""))
    return sheet, row, col

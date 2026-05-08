# Task 003.07: `cell_types.py` (F5 — six logical types + D4 7-code subset)

## Use Case Connection
- **I2.1** (cell-value canonicalisation).
- **R2.a–R2.e** (six logical types, "numbers stored as text" stays text, Decimal→float, whitespace strip, D4 auto-emit token).
- **R4.d partial** (`is_excel_serial_date`, `coerce_text_as_date`).

## Task Goal
Implement F5 — map openpyxl cells into the six logical types (`number/date/bool/text/error/empty`). Includes the D4 lock for the 7 openpyxl-recognised error codes and the dateutil text-as-date opt-in path.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_check_rules/cell_types.py`

```python
"""F5 — Cell-value canonicalisation.

Maps openpyxl Cell -> (LogicalType, value) per SPEC §3.5. Six
logical types are the unit of rule evaluation; downstream stages
(F7, F8) consume the type without re-classification.

D4 lock: only the 7 openpyxl-recognised error codes round-trip
to logical-type=error. Modern codes (#SPILL!, #CALC!,
#GETTING_DATA) stay logical-type=text — user-rule workaround.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from .constants import OPENPYXL_ERROR_CODES, EXCEL_SERIAL_DATE_RANGE
from .exceptions import CellError

__all__ = [
    "LogicalType", "ClassifiedCell", "classify",
    "is_excel_serial_date", "coerce_text_as_date",
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
    value: Any  # int|float|str|bool|datetime|CellError|None
    sheet: str
    row: int
    col: str  # column letter
    is_anchor_of_merge: bool = False
    merge_range: str | None = None
    is_hidden: bool = False  # row OR col hidden
    has_formula_no_cache: bool = False  # for §5.0.1 stale-cache warning

def classify(cell, opts) -> ClassifiedCell:
    """Map openpyxl Cell -> ClassifiedCell.

    `opts` is a dict with keys:
      - strip_whitespace (default True)
      - treat_numeric_as_date (set[str] of column letters)
      - treat_text_as_date (set[str] of column letters)
      - dayfirst (bool, for dateutil)
    """
    # ... full impl per SPEC §3.5
    raise NotImplementedError

def is_excel_serial_date(n: float) -> bool:
    """SPEC §5.4.1 path 3 — number in [25569, 73050] window."""
    lo, hi = EXCEL_SERIAL_DATE_RANGE
    return lo <= n <= hi

def coerce_text_as_date(s: str, dayfirst: bool = False) -> datetime | None:
    """SPEC §5.4.1 path 4 — dateutil with fuzzy=False.
    Returns None on parse failure (caller falls through to text type).

    Honest-scope warning: dateutil does NOT have a true strict mode
    even with fuzzy=False — '42' parses to 2042-01-01. Opt-in only.
    """
    from dateutil.parser import parse, ParserError
    try:
        return parse(s, fuzzy=False, dayfirst=dayfirst)
    except (ParserError, ValueError, OverflowError):
        return None

def whitespace_strip(text: str, strip: bool = True) -> str:
    """Default-on per `defaults.strip_whitespace` (§3.5.3)."""
    return text.strip() if strip else text
```

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Remove `@unittest.skip` from `TestCellTypes`. Add tests:
- `test_classify_number_cell` — openpyxl cell with `data_type='n'` and non-date format → `LogicalType.NUMBER`.
- `test_classify_text_42_stays_text` — cell with `value="42", data_type='s'` → `LogicalType.TEXT` (NOT auto-coerced to NUMBER per R2.b).
- `test_classify_decimal_to_float` — cell with `value=Decimal("3.14")` → `LogicalType.NUMBER` with `value=3.14` float.
- `test_classify_seven_error_codes` (D4 lock):
  ```python
  for code in ("#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A"):
      cell = mock_cell(value=code, data_type='e')
      result = classify(cell, opts={"strip_whitespace": True})
      assert result.logical_type == LogicalType.ERROR
      assert result.value.code == code
  ```
- `test_classify_modern_error_codes_as_text` (D4 honest scope):
  ```python
  for code in ("#SPILL!", "#CALC!", "#GETTING_DATA"):
      cell = mock_cell(value=code, data_type='s')  # stored as TEXT, not error
      result = classify(cell, opts={"strip_whitespace": True})
      assert result.logical_type == LogicalType.TEXT
      # NO cell-error auto-emit on this path
  ```
- `test_whitespace_strip_default_on` — `"  hello  "` → `"hello"`.
- `test_whitespace_strip_off` — `whitespace_strip(s, strip=False)` → unchanged.
- `test_excel_serial_date_window` — 25569 (1970-01-01) → True; 25568 → False; 73050 (2099-12-31) → True.
- `test_coerce_text_as_date_returns_none_on_garbage` — `"hello world"` → `None`.
- `test_coerce_text_as_date_strict_disclaimer` — `"42"` parses to a datetime (documented honest-scope).
- `test_classify_formula_no_cache_flag` — cell with `<f>` and no `<v>` → `has_formula_no_cache=True` and `LogicalType.EMPTY`.
- `test_classify_empty_cell` — `value=None` → `LogicalType.EMPTY`.

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Append fixture invocations for #10 (errors-as-values), #15 (localized-dates-ru-text), #16 (localized-dates-ru-text-flag), #17 (whitespace-values), and #10b (modern-error-text). Each fixture is auto-generated by 003.04's `_generate.py`. **These E2E tests will fail until 003.11 (evaluator) ships** — they assert evaluation outcomes, not just classification. In 003.07 the test_battery.py xfail decoration stays for these fixtures.

## Test Cases
- Unit: ~ 12 new tests; all pass.
- Regression: xlsx-6 + earlier xlsx-7 tests still green.

## Acceptance Criteria
- [ ] `cell_types.py` complete (≤ 200 LOC).
- [ ] All 6 logical types correctly mapped from openpyxl `data_type`.
- [ ] D4 lock: 7 codes only.
- [ ] D4 honest-scope: modern codes stay text.
- [ ] `coerce_text_as_date` returns None on parse failure (no exceptions leak).
- [ ] `TestCellTypes` un-skipped, all green.
- [ ] `validate_skill.py` exits 0.

## Notes
- Mock cells: build with a small helper `mock_cell(value, data_type, number_format='General', is_date=None)` that returns an object exposing the openpyxl attributes used by `classify()`. Keep the mock minimal — don't shim full `openpyxl.Cell`.
- For `is_date` heuristic detection: openpyxl exposes `cell.is_date` as a boolean derived from the number-format string. Our `classify` uses that directly for path 1 of §5.4.1; paths 2 (`<c t="d">`), 3 (numeric serial + flag), 4 (text + flag) are checked in order.
- `Decimal` cells round-trip through `float(d)` for arithmetic; equality comparisons in F7 use the rule's `tolerance` (default 1e-9). Document the precision-loss case in honest-scope (R13.j → 003.17).

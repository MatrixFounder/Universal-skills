"""F2 — sheet enumeration + resolver.

`enumerate_sheets(wb)` reads `xl/workbook.xml/<sheets>` document order
(openpyxl exposes this verbatim via `wb.sheetnames`) and returns a
`list[SheetInfo]`. `resolve_sheet(wb, query)` returns a single name
for exact-match, the full ordered list for `"all"`, or raises
`SheetNotFound`. No state filtering happens here — caller decides
how to handle hidden / veryHidden sheets (UC-02 main scenario).
"""

from __future__ import annotations

from typing import Any, Literal

from ._exceptions import SheetNotFound
from ._types import SheetInfo

# openpyxl 3.1.x stores `Worksheet.sheet_state` as one of these three
# string literals. If it ever emits something else, fail-loud rather
# than silently coerce — that would mask a contract drift.
_VALID_STATES: frozenset[str] = frozenset({"visible", "hidden", "veryHidden"})


def _state_from_openpyxl(ws: Any) -> Literal["visible", "hidden", "veryHidden"]:
    """Map openpyxl `sheet_state` to the public Literal."""
    state = getattr(ws, "sheet_state", "visible")
    if state not in _VALID_STATES:
        raise RuntimeError(
            f"openpyxl returned unexpected sheet_state {state!r}; "
            "expected one of visible / hidden / veryHidden"
        )
    return state  # type: ignore[return-value]


def enumerate_sheets(wb: Any) -> list[SheetInfo]:
    """Return one `SheetInfo` per worksheet, in document order."""
    return [
        SheetInfo(name=name, index=i, state=_state_from_openpyxl(wb[name]))
        for i, name in enumerate(wb.sheetnames)
    ]


def resolve_sheet(wb: Any, query: str) -> str | list[str]:
    """Resolve a sheet query.

    - `query == "all"` → full ordered list of names.
    - `query` exactly matches a sheet name (case-sensitive) → the name.
    - Otherwise → raise `SheetNotFound`.

    Case-sensitive match mirrors xlsx-7 / xlsx-6 conventions (Excel
    sheet names ARE case-sensitive at the storage level; some tools
    surface case-insensitive comparison, but the library returns the
    underlying-name verbatim).
    """
    if query == "all":
        return list(wb.sheetnames)
    if query in wb.sheetnames:
        return query
    raise SheetNotFound(
        f"Sheet not found: {query!r} (available: {list(wb.sheetnames)!r})"
    )

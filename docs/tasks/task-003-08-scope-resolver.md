# Task 003.08: `scope_resolver.py` (F6 — 10 scope forms + Excel-Tables fallback)

## Use Case Connection
- **I2.2** (scope resolver — all 10 forms).
- **R3.a–R3.g** (scope vocabulary, sheet qualifier, header semantics, Excel-Tables, merged cells, hidden rows/cols).

## Task Goal
Implement F6 — resolve all 10 SPEC §4 scope forms into concrete `(sheet_name, list[ClassifiedCell])` tuples. Owns sheet-qualifier parsing, header lookup with case-sensitive whitespace-strip, Excel-Tables (`xl/tables/tableN.xml`) fallback, merged-cell anchor logic, and the hidden-row/col filter. The largest single-module task in the chain (≤ 400 LOC).

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_check_rules/scope_resolver.py`

```python
"""F6 — Scope resolver: 10 scope forms -> concrete cell sequences.

Reads xl/tables/tableN.xml directly via lxml (defusedxml-parsed) for
Excel-Tables fallback. Sheet qualifier accepts plain identifiers,
quoted forms, and apostrophe-escaped (per Excel/ECMA-376).

Raises:
    AmbiguousHeader, HeaderNotFound, MergedHeaderUnsupported on
    parse-time scope errors. RulesParseError(MultiAreaName) on
    multi-area definedName. CorruptInput on malformed table XML.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterator, Optional, Sequence
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.utils.cell import coordinate_from_string
from .ast_nodes import (CellRef, RangeRef, ColRef, MultiColRef, RowRef,
                        SheetRef, NamedRef, TableRef)
from .cell_types import classify, ClassifiedCell
from .exceptions import (AmbiguousHeader, HeaderNotFound,
                          MergedHeaderUnsupported, RulesParseError,
                          CorruptInput)

__all__ = [
    "ScopeResult", "resolve_scope", "resolve_sheet",
    "resolve_header", "iter_cells", "resolve_named",
    "parse_sheet_qualifier",
]

@dataclass
class ScopeResult:
    sheet_name: str
    cells: list[ClassifiedCell]
    column_letter: str | None = None  # populated for col:HEADER / col:LETTER
    is_table_resolved: bool = False  # True iff Excel-Tables fallback fired

def parse_sheet_qualifier(text: str) -> tuple[str | None, str]:
    """Split 'Sheet!ref' / "'Quoted Sheet'!ref" / "'It''s'!ref" / 'ref'."""
    # Hand-written; reject `\ / ? * [ ] :` and leading/trailing apostrophes.
    raise NotImplementedError

def resolve_sheet(qualifier: str | None, workbook: Workbook) -> Worksheet:
    """SPEC §4.1. None -> first non-hidden in xl/workbook.xml order."""
    raise NotImplementedError

def resolve_header(name: str, sheet: Worksheet, defaults: dict,
                   allow_table_fallback: bool = True) -> str:
    """Returns the column letter; raises AmbiguousHeader / HeaderNotFound /
    MergedHeaderUnsupported. SPEC §4.2 + §4.3."""
    raise NotImplementedError

def iter_cells(scope_result: ScopeResult, opts: dict) -> Iterator[ClassifiedCell]:
    """Apply --visible-only filter; emit one merged-cell-resolution info
    per merge encountered (suppress with --no-merge-info)."""
    raise NotImplementedError

def resolve_named(name: str, workbook: Workbook) -> ScopeResult:
    """Reject multi-area definedName at parse time (SPEC §4 honest scope)."""
    raise NotImplementedError

def resolve_scope(scope_node, workbook: Workbook, defaults: dict,
                   opts: dict) -> ScopeResult:
    """Top-level dispatch over the 10 scope-node types."""
    raise NotImplementedError

def _read_excel_tables(workbook: Workbook) -> dict:
    """Parse xl/tables/tableN.xml parts via lxml + defusedxml; return
    a dict { table_name: TableMeta(sheet, range, header_letters) }."""
    raise NotImplementedError
```

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Remove `@unittest.skip` from `TestScopeResolver`. Add tests:

- `test_parse_sheet_qualifier_plain` — `"Sheet1!A5"` → `("Sheet1", "A5")`.
- `test_parse_sheet_qualifier_quoted` — `"'Q1 2026'!A5"` → `("Q1 2026", "A5")`.
- `test_parse_sheet_qualifier_apostrophe_escape` — `"'Bob''s Sheet'!A5"` → `("Bob's Sheet", "A5")`.
- `test_parse_sheet_qualifier_unqualified` — `"A5"` → `(None, "A5")`.
- `test_parse_sheet_qualifier_rejects_prohibited_chars` — `"Bad/Name!A5"` raises `RulesParseError`.
- `test_resolve_sheet_default_first_visible` — fixture with hidden Sheet1 + visible Sheet2 → returns Sheet2.
- `test_resolve_header_case_sensitive` — `"hours"` ≠ `"Hours"`.
- `test_resolve_header_whitespace_strip` — `"  Hours  "` matches `col:Hours`.
- `test_ambiguous_header_raises` — fixture #7 → `AmbiguousHeader`.
- `test_missing_header_raises_with_available_list` — fixture #8 → `HeaderNotFound` whose `details["available"]` is a list of present headers.
- `test_merged_header_raises` — fixture #5 → `MergedHeaderUnsupported`.
- `test_excel_tables_fallback_fires_when_in_table` — fixture #4: cell range inside Table T1; `col:Hours` resolves through Table header.
- `test_excel_tables_fallback_disabled_via_flag` — same fixture with `allow_table_fallback=False` → `HeaderNotFound`.
- `test_merged_data_cell_anchor_resolution` — fixture #13: B1 inside merged A1:C1; resolves to A1's value + emits `merged-cell-resolution` info.
- `test_visible_only_filter` — fixture with hidden row 2; `--visible-only` skips row 2; default (include hidden) does not.
- `test_named_range_multi_area_rejected` — defined name `Sheet1!A1:A10,Sheet1!B1:B10` raises `RulesParseError(MultiAreaName)`.

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Append fixture invocations for #3, #4, #5, #7, #8, #9, #13. Most still xfail until 003.13 (output emitter) ships; the assertion in this task is "the resolver does not crash on the fixture; raised exceptions match the expected error type".

## Test Cases
- Unit: ~ 16 new tests; all pass.
- Regression: prior tests stay green.
- Battery: fixtures #3, #4, #5, #7, #8, #9, #13 transition from xfail to xpass for the **resolution layer** (full assertion still pending output emitter).

## Acceptance Criteria
- [ ] `scope_resolver.py` complete (≤ 400 LOC).
- [ ] 10 scope forms dispatched correctly.
- [ ] Excel-Tables fallback works (read `xl/tables/tableN.xml` via lxml + defusedxml).
- [ ] All 16 `TestScopeResolver` tests green.
- [ ] `validate_skill.py` exits 0.
- [ ] LOC budget honoured.

## Notes
- **Hardened lxml parser**: when reading `xl/tables/tableN.xml`, use `lxml.etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)` (mirrors xlsx-6's `_VML_PARSER` security boundary). DO NOT trust the workbook XML — `office/unpack` already scans for path-traversal but the table XML reader is a fresh attack surface.
- For the visible-default vs first-non-hidden rule: read `xl/workbook.xml` directly via openpyxl's `wb.sheetnames` ordering (which matches XML order) but cross-reference each sheet's `state` attribute. Document why `wb.sheetnames` and `wb.worksheets` may diverge in older openpyxl.
- The `merged-cell-resolution` info finding is emitted as a stderr line at this stage; F9 handles JSON-side emission. Pass back via `iter_cells`'s side-channel (a list passed as part of `opts`).
- For `_read_excel_tables`: parse `xl/_rels/workbook.xml.rels` to discover which sheet rels point to `xl/tables/tableN.xml`; cache the mapping per-workbook (one parse per run).

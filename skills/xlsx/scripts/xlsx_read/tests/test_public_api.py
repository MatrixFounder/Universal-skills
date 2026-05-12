"""Task 009-08 — closed-API regression + AST guarantees.

Three regression locks for the R1 / R12 contracts:
1. `__all__` membership unchanged (TC-UNIT-01 of 009-01 re-asserted).
2. Public-API return values carry no `openpyxl.*` types
   (TC-UNIT-02).
3. No module-level mutable singletons in `xlsx_read/*.py`
   (TC-UNIT-03 — UC-05 acceptance criterion / L2 fix).
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import xlsx_read
from xlsx_read import TableRegion, open_workbook
from xlsx_read.tests.conftest import FIXTURES_DIR

EXPECTED_PUBLIC = [
    "AmbiguousHeaderBoundary",
    "DateFmt",
    "EncryptedWorkbookError",
    "MacroEnabledWarning",
    "MergePolicy",
    "OverlappingMerges",
    "SheetInfo",
    "SheetNotFound",
    "TableData",
    "TableDetectMode",
    "TableRegion",
    "WorkbookReader",
    "open_workbook",
]


class TestAllMembershipLockedAgainstDrift(unittest.TestCase):
    """Scenario 27 (TASK §5.5): public-API closed; nothing slips into __all__."""

    def test_all_matches_locked_list(self) -> None:
        self.assertEqual(sorted(xlsx_read.__all__), EXPECTED_PUBLIC)


class TestNoOpenpyxlLeakAcrossSurface(unittest.TestCase):
    """Scenario 27 cont.: walk public returns; assert no openpyxl types."""

    def _no_openpyxl_in(self, label: str, obj: object) -> None:
        # Test the object itself and its type's module.
        module = type(obj).__module__
        self.assertFalse(
            module.startswith("openpyxl"),
            f"{label}: type {type(obj).__name__} comes from openpyxl module {module!r}",
        )

    def test_sheets_list(self) -> None:
        with open_workbook(FIXTURES_DIR / "three_sheets_mixed.xlsx") as r:
            for info in r.sheets():
                self._no_openpyxl_in("SheetInfo", info)
                self._no_openpyxl_in("SheetInfo.name", info.name)
                self._no_openpyxl_in("SheetInfo.index", info.index)
                self._no_openpyxl_in("SheetInfo.state", info.state)

    def test_detect_tables_list(self) -> None:
        with open_workbook(FIXTURES_DIR / "listobject_one.xlsx") as r:
            for region in r.detect_tables("Sheet1", mode="auto"):
                self._no_openpyxl_in("TableRegion", region)

    def test_read_table_payload(self) -> None:
        with open_workbook(FIXTURES_DIR / "headers_single_row.xlsx") as r:
            region = TableRegion(
                sheet="Sheet",
                top_row=1,
                left_col=1,
                bottom_row=r._wb.active.max_row,
                right_col=r._wb.active.max_column,
                source="gap_detect",
            )
            td = r.read_table(region)
        self._no_openpyxl_in("TableData", td)
        for h in td.headers:
            self._no_openpyxl_in("header", h)
        for row in td.rows:
            for cell in row:
                if cell is not None:
                    self._no_openpyxl_in("data-cell", cell)


class TestNoModuleLevelMutableSingletons(unittest.TestCase):
    """Scenario 30 (TASK §5.5) / UC-05 / L2: AST scan for module-level mutables."""

    def _scan(self, path: Path) -> list[str]:
        tree = ast.parse(path.read_text())
        flagged: list[str] = []
        for node in tree.body:
            # Plain assignments at module level: `X = [...]`, `X = {...}`,
            # `X = set(...)`. Annotated assignments with literal RHS are
            # also flagged.
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                rhs = node.value if hasattr(node, "value") else None
                if rhs is None:
                    continue
                if isinstance(rhs, (ast.List, ast.Dict, ast.Set)):
                    flagged.append(f"{path.name}:{node.lineno}")
                elif isinstance(rhs, ast.Call):
                    func = rhs.func
                    name = getattr(func, "id", None) or getattr(func, "attr", None)
                    if name in {"list", "dict", "set"}:
                        flagged.append(f"{path.name}:{node.lineno}")
        return flagged

    def test_no_mutable_module_globals(self) -> None:
        pkg_dir = Path(xlsx_read.__file__).parent
        flagged: list[str] = []
        for py in pkg_dir.glob("*.py"):
            flagged.extend(self._scan(py))
        # Only `__all__ = [...]` is permitted (it's the public-surface
        # lock; treat as a special case via per-line whitelist).
        whitelisted = []
        for entry in flagged:
            fname, line = entry.split(":")
            text = (pkg_dir / fname).read_text().splitlines()[int(line) - 1]
            if text.lstrip().startswith("__all__"):
                continue
            whitelisted.append(entry)
        self.assertEqual(
            whitelisted, [],
            f"Module-level mutable globals detected (violates L2 contract): {whitelisted}",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

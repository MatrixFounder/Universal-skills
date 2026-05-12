"""Task 009-05 — F4 `_tables.py` E2E + unit tests."""

from __future__ import annotations

import unittest

from xlsx_read import TableRegion, open_workbook
from xlsx_read import _tables
from xlsx_read.tests.conftest import FIXTURES_DIR


class TestListObjectDetect(unittest.TestCase):
    """TC-E2E-01..-02: ListObject detection (with + without headers)."""

    def test_one_listobject(self) -> None:
        with open_workbook(FIXTURES_DIR / "listobject_one.xlsx") as r:
            regions = r.detect_tables("Sheet1", mode="auto")
        self.assertEqual(len(regions), 1)
        reg = regions[0]
        self.assertEqual(reg.source, "listobject")
        self.assertEqual(reg.name, "Revenue")
        self.assertEqual(reg.listobject_header_row_count, 1)
        self.assertEqual(
            (reg.top_row, reg.left_col, reg.bottom_row, reg.right_col), (1, 1, 5, 3)
        )

    def test_listobject_no_header(self) -> None:
        with open_workbook(FIXTURES_DIR / "listobject_no_header.xlsx") as r:
            regions = r.detect_tables("Sheet1", mode="auto")
        # Find the listobject region (gap-detect may also fire on remaining rows).
        listobjects = [reg for reg in regions if reg.source == "listobject"]
        self.assertEqual(len(listobjects), 1)
        self.assertEqual(listobjects[0].name, "NoHead")
        self.assertEqual(listobjects[0].listobject_header_row_count, 0)


class TestNamedRangeDetect(unittest.TestCase):
    """TC-E2E-03..-04: sheet-scope vs workbook-scope named ranges."""

    def test_sheet_scope_detected(self) -> None:
        with open_workbook(FIXTURES_DIR / "named_range_sheet_scope.xlsx") as r:
            regions = r.detect_tables("Sheet1", mode="tables-only")
        named = [reg for reg in regions if reg.source == "named_range"]
        self.assertEqual(len(named), 1)
        self.assertEqual(named[0].name, "KPI")

    def test_workbook_scope_ignored(self) -> None:
        with open_workbook(FIXTURES_DIR / "named_range_workbook_scope.xlsx") as r:
            regions = r.detect_tables("Sheet1", mode="tables-only")
        # No regions: workbook-scope name dropped per honest-scope (d).
        self.assertEqual(regions, [])


class TestGapDetect(unittest.TestCase):
    """TC-E2E-05..-06: gap-detection thresholds."""

    def test_two_tables_default_gap_rows_2(self) -> None:
        with open_workbook(FIXTURES_DIR / "gap_two_tables.xlsx") as r:
            regions = r.detect_tables("Sheet", mode="auto")
        self.assertEqual(len(regions), 2)
        for reg in regions:
            self.assertEqual(reg.source, "gap_detect")
        names = [reg.name for reg in regions]
        self.assertEqual(names, ["Table-1", "Table-2"])

    def test_one_col_separation(self) -> None:
        with open_workbook(FIXTURES_DIR / "gap_one_col.xlsx") as r:
            regions = r.detect_tables("Sheet", mode="auto")
        self.assertEqual(len(regions), 2)
        for reg in regions:
            self.assertEqual(reg.source, "gap_detect")

    def test_gap_rows_1_overrides_default(self) -> None:
        # With gap_rows=1, the same fixture splits into two regions
        # via single-empty-row separators — but our fixture has 2 empty
        # rows, so still 2 regions. Use a stricter test: gap_rows=2 on
        # a fixture with 1 empty row → ONE region.
        # gap_two_tables has 2 empty rows; with gap_rows=3, it should
        # collapse to ONE region.
        with open_workbook(FIXTURES_DIR / "gap_two_tables.xlsx") as r:
            regions = r.detect_tables("Sheet", mode="auto", gap_rows=3)
        self.assertEqual(len(regions), 1)


class TestListObjectWinsOverNamed(unittest.TestCase):
    """TC-E2E-07: Tier-1 wins over Tier-2 on overlap (UC-03 A4)."""

    def test_listobject_displaces_named(self) -> None:
        with open_workbook(FIXTURES_DIR / "listobject_overlap_named.xlsx") as r:
            regions = r.detect_tables("Sheet1", mode="tables-only")
        # Expect exactly one region — the listobject — and NO named_range.
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].source, "listobject")
        self.assertEqual(regions[0].name, "Revenue")


class TestModeWhole(unittest.TestCase):
    """TC-E2E-08: mode='whole' returns a single region spanning the dim."""

    def test_whole_on_gap_fixture(self) -> None:
        with open_workbook(FIXTURES_DIR / "gap_two_tables.xlsx") as r:
            regions = r.detect_tables("Sheet", mode="whole")
        self.assertEqual(len(regions), 1)
        reg = regions[0]
        self.assertEqual((reg.top_row, reg.left_col), (1, 1))
        # bottom_row is the sheet's max_row (≥ 8 for our fixture).
        self.assertGreaterEqual(reg.bottom_row, 8)


class TestModeTablesOnlySkipsGap(unittest.TestCase):
    """TC-E2E-09: mode='tables-only' skips Tier-3 (gap-detect)."""

    def test_no_gap_when_no_listobjects(self) -> None:
        with open_workbook(FIXTURES_DIR / "gap_two_tables.xlsx") as r:
            regions = r.detect_tables("Sheet", mode="tables-only")
        self.assertEqual(regions, [])


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestSplitOnGap(unittest.TestCase):
    """TC-UNIT-03 (M4 fix): threshold boundary."""

    def test_two_empty_split_with_gap2(self) -> None:
        # [T, F, F, T] with gap=2 → 2 bands.
        bands = _tables._split_on_gap([True, False, False, True], 2, base_index=1)
        self.assertEqual(bands, [(1, 1), (4, 4)])

    def test_one_empty_does_not_split_with_gap2(self) -> None:
        # M4 fix: a single empty row inside a table must NOT split
        # when gap=2 (the default).
        bands = _tables._split_on_gap([True, False, True], 2, base_index=1)
        self.assertEqual(bands, [(1, 3)])

    def test_one_empty_splits_with_gap1(self) -> None:
        bands = _tables._split_on_gap([True, False, True], 1, base_index=1)
        self.assertEqual(bands, [(1, 1), (3, 3)])


class TestHasOverlap(unittest.TestCase):
    """TC-UNIT-04: bounding-box intersection truth table."""

    def _mk(self, t, l, b, r):
        return TableRegion(sheet="S", top_row=t, left_col=l, bottom_row=b,
                           right_col=r, source="gap_detect")

    def test_adjacent_no_overlap(self) -> None:
        a = self._mk(1, 1, 3, 3)
        b = self._mk(4, 1, 6, 3)
        self.assertFalse(_tables._has_overlap(a, [b]))

    def test_corner_overlap(self) -> None:
        a = self._mk(1, 1, 3, 3)
        b = self._mk(3, 3, 5, 5)
        self.assertTrue(_tables._has_overlap(a, [b]))

    def test_contained(self) -> None:
        outer = self._mk(1, 1, 10, 10)
        inner = self._mk(2, 2, 5, 5)
        self.assertTrue(_tables._has_overlap(inner, [outer]))


class TestUnknownModeRejected(unittest.TestCase):
    def test_invalid_mode_raises(self) -> None:
        with open_workbook(FIXTURES_DIR / "empty.xlsx") as r:
            with self.assertRaises(ValueError):
                r.detect_tables("Sheet", mode="bogus")  # type: ignore[arg-type]


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

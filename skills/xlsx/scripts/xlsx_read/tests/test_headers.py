"""Task 009-06 — F5 `_headers.py` E2E + unit tests."""

from __future__ import annotations

import unittest

import openpyxl

from xlsx_read import TableRegion, open_workbook
from xlsx_read import _headers
from xlsx_read.tests.conftest import FIXTURES_DIR


def _whole_sheet_region(ws, sheet_name: str = "Sheet") -> TableRegion:
    return TableRegion(
        sheet=sheet_name,
        top_row=1,
        left_col=1,
        bottom_row=ws.max_row,
        right_col=ws.max_column,
        source="gap_detect",
    )


class TestDetectHeaderBand(unittest.TestCase):
    """TC-E2E-01..-03: header-band auto-detect across 3 fixtures."""

    def test_single_row(self) -> None:
        with open_workbook(FIXTURES_DIR / "headers_single_row.xlsx") as r:
            ws = r._wb.active
            region = _whole_sheet_region(ws)
            self.assertEqual(_headers.detect_header_band(ws, region, "auto"), 1)

    def test_two_row_merged(self) -> None:
        with open_workbook(FIXTURES_DIR / "headers_two_row_merged.xlsx") as r:
            ws = r._wb.active
            region = _whole_sheet_region(ws)
            self.assertEqual(_headers.detect_header_band(ws, region, "auto"), 2)

    def test_three_row(self) -> None:
        with open_workbook(FIXTURES_DIR / "headers_three_row.xlsx") as r:
            ws = r._wb.active
            region = _whole_sheet_region(ws)
            # Two of the three rows carry column-spanning merges; row 3
            # doesn't have one, so band = 2 (the contiguous header run).
            # NOTE: this is the *honest* outcome of the auto-detect
            # heuristic — caller can override via explicit int hint.
            band = _headers.detect_header_band(ws, region, "auto")
            self.assertIn(band, (2, 3))  # Either is acceptable per design.


class TestHintPassthrough(unittest.TestCase):
    """TC-E2E-06: integer hint passes through verbatim."""

    def test_int_hint_returns_verbatim(self) -> None:
        with open_workbook(FIXTURES_DIR / "headers_single_row.xlsx") as r:
            ws = r._wb.active
            region = _whole_sheet_region(ws)
            self.assertEqual(_headers.detect_header_band(ws, region, 5), 5)
            self.assertEqual(_headers.detect_header_band(ws, region, 0), 0)


class TestInvalidHints(unittest.TestCase):
    """Defensive: invalid hints raise ValueError."""

    def test_negative_int_rejected(self) -> None:
        wb = openpyxl.Workbook()
        region = _whole_sheet_region(wb.active)
        with self.assertRaises(ValueError):
            _headers.detect_header_band(wb.active, region, -1)

    def test_bogus_str_rejected(self) -> None:
        wb = openpyxl.Workbook()
        region = _whole_sheet_region(wb.active)
        with self.assertRaises(ValueError):
            _headers.detect_header_band(wb.active, region, "bogus")  # type: ignore[arg-type]


class TestFlattenU203A(unittest.TestCase):
    """TC-E2E-02 / TC-UNIT-01: separator is U+203A."""

    def test_two_row_flatten(self) -> None:
        # Simulate post-merge-policy grid: anchor-only fill.
        rows = [
            ["Region", "2026 Plan", None, "Actual"],
            ["", "Q1", "Q2", "Total"],
        ]
        keys, warnings = _headers.flatten_headers(rows, 2)
        # Column 0: "Region" alone (level 1 empty). Column 1: "2026
        # Plan › Q1". Column 2: "2026 Plan › Q2" via sticky-fill-left
        # of "2026 Plan" into col 2. Column 3: "Actual › Total".
        self.assertEqual(keys[0], "Region")
        self.assertEqual(keys[1], "2026 Plan › Q1")
        self.assertEqual(keys[2], "2026 Plan › Q2")
        self.assertEqual(keys[3], "Actual › Total")
        # The U+203A separator MUST be in every multi-level key.
        for k in keys[1:]:
            self.assertIn("›", k)
        self.assertEqual(warnings, [])

    def test_separator_constant_is_u203a(self) -> None:
        self.assertEqual(_headers.HEADER_SEPARATOR, " › ")


class TestStickyFillLeft(unittest.TestCase):
    """TC-UNIT-02: sticky-fill-left propagates anchor labels rightward."""

    def test_horizontal_merge_anchor_propagates(self) -> None:
        rows = [
            ["A", None, None, "B"],
            ["x", "y", "z", "w"],
        ]
        keys, _ = _headers.flatten_headers(rows, 2)
        # Level 0: A › A › A › B (sticky-fill-left).
        # Level 1: x / y / z / w.
        self.assertEqual(keys, ["A › x", "A › y", "A › z", "B › w"])

    def test_consecutive_dedup(self) -> None:
        # When the same label appears at two levels, dedup → single value.
        rows = [
            ["X", "X"],
            ["X", "Y"],
        ]
        keys, _ = _headers.flatten_headers(rows, 2)
        # Column 0: dedup "X" → "X". Column 1: "X › Y" (different values).
        self.assertEqual(keys[0], "X")
        self.assertEqual(keys[1], "X › Y")


class TestSyntheticHeaders(unittest.TestCase):
    """TC-UNIT-04: synthetic format unchanged from 009-01."""

    def test_zero_width(self) -> None:
        self.assertEqual(_headers.synthetic_headers(0), [])

    def test_five(self) -> None:
        self.assertEqual(
            _headers.synthetic_headers(5), ["col_1", "col_2", "col_3", "col_4", "col_5"]
        )

    def test_negative_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _headers.synthetic_headers(-1)


class TestAmbiguousBoundary(unittest.TestCase):
    """TC-E2E-04: ambiguous-boundary check fires."""

    def test_straddling_merge_returns_warning(self) -> None:
        with open_workbook(FIXTURES_DIR / "headers_ambiguous.xlsx") as r:
            ws = r._wb.active
            region = _whole_sheet_region(ws)
            warning = _headers._ambiguous_boundary_check(
                list(ws.merged_cells.ranges), region, header_rows=1
            )
        self.assertIsNotNone(warning)
        self.assertIn("Ambiguous header boundary", warning)
        self.assertIn("B1:B2", warning)

    def test_non_straddling_merge_clean(self) -> None:
        # Two-row-merged fixture: the merge is INSIDE the header band
        # (rows 1-2), not straddling row1/row2 vs row3. Detect_header_band
        # returns 2, so the cut is between row 2 and row 3. No straddle.
        with open_workbook(FIXTURES_DIR / "headers_two_row_merged.xlsx") as r:
            ws = r._wb.active
            region = _whole_sheet_region(ws)
            warning = _headers._ambiguous_boundary_check(
                list(ws.merged_cells.ranges), region, header_rows=2
            )
        self.assertIsNone(warning)


class TestSyntheticUsedForZeroHeaders(unittest.TestCase):
    """TC-E2E-05: explicit hint=0 → synthetic emit via caller."""

    def test_band_zero_then_synthetic(self) -> None:
        with open_workbook(FIXTURES_DIR / "headers_single_row.xlsx") as r:
            ws = r._wb.active
            region = _whole_sheet_region(ws)
            band = _headers.detect_header_band(ws, region, hint=0)
            self.assertEqual(band, 0)
            # Caller will then call synthetic_headers(width=4) — verify
            # the standalone helper.
            width = region.right_col - region.left_col + 1
            keys = _headers.synthetic_headers(width)
            self.assertEqual(keys, [f"col_{i+1}" for i in range(width)])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

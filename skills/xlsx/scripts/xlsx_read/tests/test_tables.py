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


class TestReservedNameFilter(unittest.TestCase):
    """TASK 010 §11 patch: Excel-reserved defined names must be excluded
    from Tier-2 named-range emission. Source-of-truth list lives in
    `xlsx_read/_reserved_names.json`.
    """

    def test_is_reserved_helper_matches_canonical_examples(self) -> None:
        from xlsx_read._tables import _is_reserved_name
        # OOXML §18.2.6 _xlnm.* built-ins
        self.assertTrue(_is_reserved_name("_xlnm.Print_Area"))
        self.assertTrue(_is_reserved_name("_xlnm._FilterDatabase"))
        self.assertTrue(_is_reserved_name("_xlnm.Print_Titles"))
        self.assertTrue(_is_reserved_name("_xlnm.Criteria"))
        # Custom-View artefacts — must match the strict GUID layout
        self.assertTrue(_is_reserved_name(
            "Z_DEADBEEF_1234_5678_9ABC_DEF012345678_.wvu.FilterData"
        ))
        self.assertTrue(_is_reserved_name(
            "Z_F5BF852F_D0BB_4165_A12A_8595FD3E6864_.wvu.PrintArea"
        ))
        # Legacy bare-form
        self.assertTrue(_is_reserved_name("Print_Area"))
        self.assertTrue(_is_reserved_name("_FilterDatabase"))
        # Genuine user names — NOT reserved
        self.assertFalse(_is_reserved_name("KPI"))
        self.assertFalse(_is_reserved_name("MyTable"))
        self.assertFalse(_is_reserved_name("Sales2026"))
        # Looks-like prefix but not actually reserved
        self.assertFalse(_is_reserved_name("_xlnmMisspelled"))
        # Z_-prefixed but not the canonical GUID layout
        self.assertFalse(_is_reserved_name("Z_NotAGuid_.wvu.FilterData"))

    def test_long_input_not_matched_no_redos_surface(self) -> None:
        """**/vdd-multi-3 HIGH-Sec-2 fix:** input length is bounded
        at `_MAX_DEFINED_NAME_LEN=255` (OOXML §18.2.6 max defined-
        name length). Names exceeding this skip the regex entirely
        — no per-pattern match cost on hostile input. Caps the
        ReDoS-via-length attack surface where a 50K-names × 100KB-
        each workbook would otherwise burn ~15 GB of regex work.
        """
        from xlsx_read._tables import _is_reserved_name, _MAX_DEFINED_NAME_LEN
        # 256+ chars: not matched (early return False).
        long_name = "_xlnm.Print_Area" + "A" * (_MAX_DEFINED_NAME_LEN + 10)
        self.assertFalse(_is_reserved_name(long_name))
        # 1 MB hostile probe: also not matched, instantly.
        huge_name = "_xlnm." + "X" * 1_000_000
        import time
        t0 = time.monotonic()
        self.assertFalse(_is_reserved_name(huge_name))
        elapsed = time.monotonic() - t0
        # Sanity perf bound: should be sub-millisecond (len-check only).
        self.assertLess(elapsed, 0.05,
                        f"_is_reserved_name on 1MB input took {elapsed:.3f}s "
                        f"— length cap is not short-circuiting")

    def test_zero_width_chars_stripped_before_match(self) -> None:
        """**/vdd-multi-3 MED-Sec-4 fix:** zero-width characters
        (U+200B/200C/200D/FEFF) are stripped alongside ASCII
        whitespace. Closes the filter-bypass vector where an
        attacker prepends a ZWSP to a reserved name to slip past
        the regex anchor.
        """
        from xlsx_read._tables import _is_reserved_name
        # ZWSP + reserved name still classified as reserved.
        self.assertTrue(_is_reserved_name("​_xlnm.Print_Area"))
        self.assertTrue(_is_reserved_name("﻿_xlnm._FilterDatabase​"))
        # Embedded ZWSP between _xlnm and . — NOT stripped (only
        # leading/trailing). Documents the conservative scope.
        self.assertFalse(_is_reserved_name("_xlnm​.Print_Area"))

    def test_legacy_bare_form_includes_disable_reset_and_data_form(self) -> None:
        """**/vdd-multi-3 Logic-LOW-5 fix:** the legacy bare-form
        pattern now covers `Disable_Reset` and `Data_Form` (parity
        with the documented `_xlnm.*` notes in `_reserved_names.json`).
        """
        from xlsx_read._tables import _is_reserved_name
        self.assertTrue(_is_reserved_name("Disable_Reset"))
        self.assertTrue(_is_reserved_name("Data_Form"))

    def test_empty_name_not_matched(self) -> None:
        from xlsx_read._tables import _is_reserved_name
        self.assertFalse(_is_reserved_name(""))
        self.assertFalse(_is_reserved_name("   "))
        self.assertFalse(_is_reserved_name("​‌"))

    def test_case_insensitive_match(self) -> None:
        """OOXML §18.2.5: defined names are case-insensitive in Excel.
        The filter must match `_XLNM.Print_Area`, `PRINT_AREA`, etc.
        Locks the defence-in-depth promise stated in `_reserved_names.json`.
        """
        from xlsx_read._tables import _is_reserved_name
        # Uppercase / mixed-case xlnm prefix
        self.assertTrue(_is_reserved_name("_XLNM.Print_Area"))
        self.assertTrue(_is_reserved_name("_Xlnm._FilterDatabase"))
        # Uppercase legacy bare-form
        self.assertTrue(_is_reserved_name("PRINT_AREA"))
        self.assertTrue(_is_reserved_name("_filterdatabase"))
        # Uppercase wvu literal
        self.assertTrue(_is_reserved_name(
            "Z_DEADBEEF_1234_5678_9ABC_DEF012345678_.WVU.FilterData"
        ))

    def test_whitespace_tolerant_match(self) -> None:
        """Leading/trailing whitespace must not bypass the filter.
        A hand-crafted or third-party-emitted `<definedName>` with
        ` _xlnm.Print_Area ` (legal-ish XML, openpyxl may pass through
        verbatim) must still be classified as reserved.
        """
        from xlsx_read._tables import _is_reserved_name
        self.assertTrue(_is_reserved_name(" _xlnm.Print_Area"))
        self.assertTrue(_is_reserved_name("_xlnm.Print_Area "))
        self.assertTrue(_is_reserved_name("\t_FilterDatabase\n"))
        self.assertTrue(_is_reserved_name("  Print_Area  "))

    def test_wvu_filter_data_excluded_from_detect_tables(self) -> None:
        import openpyxl
        from openpyxl.workbook.defined_name import DefinedName
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws["A1"] = "x"
        ws["B2"] = "y"
        reserved = DefinedName(
            name="Z_DEADBEEF_1234_5678_9ABC_DEF012345678_.wvu.FilterData",
            attr_text="Sheet1!$A$1:$B$2",
        )
        ws.defined_names[reserved.name] = reserved
        user = DefinedName(name="MyData", attr_text="Sheet1!$A$1:$B$2")
        ws.defined_names[user.name] = user
        from xlsx_read._tables import detect_tables
        regions = detect_tables(wb, "Sheet1", mode="tables-only")
        names = [r.name for r in regions]
        self.assertIn("MyData", names)
        self.assertNotIn(reserved.name, names)

    def test_redos_shape_rejected_at_load(self) -> None:
        """The loader must refuse a JSON pattern matching a known
        catastrophic-backtracking shape, mirroring the lint already
        applied to user-supplied rules in `xlsx_check_rules`.
        """
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from xlsx_read import _tables
        evil = {
            "schema_version": 1,
            "patterns": [
                {"regex": "^(a+)+$", "source": "test", "notes": "ReDoS"}
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fp:
            json.dump(evil, fp)
            tmp_path = Path(fp.name)
        try:
            with patch.object(_tables, "_RESERVED_NAMES_PATH", tmp_path):
                with self.assertRaisesRegex(ValueError, "ReDoS"):
                    _tables._load_reserved_name_matchers()
        finally:
            tmp_path.unlink()

    def test_missing_regex_key_raises_with_context(self) -> None:
        """A malformed JSON entry (missing 'regex' key) must fail loudly
        with the file path and pattern index in the error message.
        """
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from xlsx_read import _tables
        bad = {
            "schema_version": 1,
            "patterns": [{"source": "test", "notes": "no regex key"}],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fp:
            json.dump(bad, fp)
            tmp_path = Path(fp.name)
        try:
            with patch.object(_tables, "_RESERVED_NAMES_PATH", tmp_path):
                with self.assertRaisesRegex(KeyError, "patterns\\[0\\]"):
                    _tables._load_reserved_name_matchers()
        finally:
            tmp_path.unlink()

    def test_xlnm_builtin_excluded_from_detect_tables(self) -> None:
        import openpyxl
        from openpyxl.workbook.defined_name import DefinedName
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws["A1"] = "x"
        builtin = DefinedName(
            name="_xlnm.Print_Area", attr_text="Sheet1!$A$1:$A$1"
        )
        ws.defined_names[builtin.name] = builtin
        from xlsx_read._tables import detect_tables
        regions = detect_tables(wb, "Sheet1", mode="tables-only")
        self.assertEqual(regions, [])


class TestWholeSheetRegionTrim(unittest.TestCase):
    """TASK 010 §11 patch v2: `_whole_sheet_region` must trim to the
    actual non-empty content bbox rather than blindly using
    `ws.max_row` / `ws.max_column` (Excel inflates the dimension ref
    after row deletions and on legacy-formatted empty rows).
    """

    def test_trims_trailing_empty_rows(self) -> None:
        import openpyxl
        from xlsx_read._tables import _whole_sheet_region
        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "header"
        ws["A2"] = "data"
        # Force dimension to inflate by touching a far cell then
        # clearing it — openpyxl retains the dimension hint after
        # value-clear in 3.1.x. The precondition assert below makes
        # the test fail loudly if a future openpyxl shrinks max_row
        # after clear (in which case the test stops exercising the
        # trim and needs a real on-disk fixture instead).
        ws["A100"] = "x"
        ws["A100"] = None
        self.assertGreaterEqual(
            ws.max_row, 100,
            "openpyxl now shrinks max_row after cell-clear; this test "
            "no longer exercises the trim. Use an on-disk fixture with "
            "a hand-crafted <dimension ref='A1:A100'/> instead.",
        )
        region = _whole_sheet_region(ws, "Sheet")
        self.assertEqual(region.bottom_row, 2)

    def test_trims_trailing_empty_columns(self) -> None:
        import openpyxl
        from xlsx_read._tables import _whole_sheet_region
        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "x"
        ws["B1"] = "y"
        ws["Z1"] = "far"
        ws["Z1"] = None
        self.assertGreaterEqual(
            ws.max_column, 26,
            "openpyxl now shrinks max_column after cell-clear; "
            "test needs an on-disk fixture instead.",
        )
        region = _whole_sheet_region(ws, "Sheet")
        self.assertEqual(region.right_col, 2)

    def test_whole_sheet_region_handles_none_max_row(self) -> None:
        """**/vdd-multi-3 MED-Logic-2 fix:** in `read_only=True` mode
        with a missing/unparseable `<dimension>` XML element,
        openpyxl's `ReadOnlyWorksheet` returns `None` for `max_row`
        / `max_column`. `max(None, 1)` raises `TypeError`; the fix
        coalesces to 0 first via `max(... or 0, 1)`.
        """
        from types import SimpleNamespace
        from xlsx_read._tables import _whole_sheet_region
        # Stub ws with .max_row/.max_column = None (read_only quirk).
        fake_ws = SimpleNamespace(
            max_row=None, max_column=None,
            iter_rows=lambda **kw: iter(()),
        )
        region = _whole_sheet_region(fake_ws, "Sheet")
        # Empty sheet → degenerate 1×1 region (not TypeError crash).
        self.assertEqual(
            (region.top_row, region.left_col, region.bottom_row, region.right_col),
            (1, 1, 1, 1),
        )

    def test_in_loop_cap_emits_warning(self) -> None:
        """**/vdd-multi-3 HIGH (3-critic) fix:** when the in-loop
        cell-scan cap fires, emit a `UserWarning` so downstream
        callers (and the shim's `_emit_warnings_to_stderr`) can
        surface the truncation. Without this, hostile input
        (sparse data at row ≥ 1M with inflated `<dimension>`)
        silently produced a tiny region with no diagnostic.
        """
        import warnings as _warnings
        import openpyxl
        from unittest.mock import patch
        from xlsx_read import _tables
        from xlsx_read._tables import _whole_sheet_region
        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "x"
        with patch.object(
            type(ws), "max_row", new_callable=lambda: property(lambda self: 1_048_576)
        ), patch.object(
            type(ws), "max_column", new_callable=lambda: property(lambda self: 16_384)
        ), patch.object(_tables, "_GAP_DETECT_MAX_CELLS", 100), \
             _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            _whole_sheet_region(ws, "Sheet")
        cap_warnings = [w for w in caught
                        if "cell-scan cap" in str(w.message)]
        self.assertEqual(len(cap_warnings), 1,
                         f"expected 1 cap-fire warning, got: {caught}")
        self.assertIn("data beyond", str(cap_warnings[0].message))

    def test_in_loop_cap_does_not_emit_inflated_region(self) -> None:
        """**vdd-multi-2 HIGH fix:** when the in-loop cell-scan
        counter exceeds `_GAP_DETECT_MAX_CELLS`, the function must
        emit the best-effort TRIMMED bbox seen so far — NEVER the
        inflated dim bbox (which would produce 1M-row CSV garbage
        on hostile `<dimension ref='A1:XFD1048576'/>`).
        """
        import openpyxl
        from unittest.mock import patch
        from xlsx_read import _tables
        from xlsx_read._tables import _whole_sheet_region
        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "only-content"
        # Force an inflated dimension hint that exceeds the 1M cap.
        # Touch a far cell, then mock max_row/max_column so the scan
        # loop ranges over the full bogus bbox.
        with patch.object(
            type(ws), "max_row", new_callable=lambda: property(lambda self: 1_048_576)
        ), patch.object(
            type(ws), "max_column", new_callable=lambda: property(lambda self: 16_384)
        ), patch.object(_tables, "_GAP_DETECT_MAX_CELLS", 100):
            region = _whole_sheet_region(ws, "Sheet")
        # The cap fires after 100 cells scanned. A1 has content, so
        # last_row=1, last_col=1. Output is 1×1 — NOT 1048576×16384.
        self.assertLess(region.bottom_row, 1000)
        self.assertLess(region.right_col, 1000)
        self.assertEqual(region.top_row, 1)
        self.assertEqual(region.left_col, 1)

    def test_empty_sheet_returns_degenerate_1x1(self) -> None:
        import openpyxl
        from xlsx_read._tables import _whole_sheet_region
        wb = openpyxl.Workbook()
        ws = wb.active
        # No cell touched — empty sheet.
        region = _whole_sheet_region(ws, "Sheet")
        self.assertEqual(
            (region.top_row, region.left_col, region.bottom_row, region.right_col),
            (1, 1, 1, 1),
        )


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

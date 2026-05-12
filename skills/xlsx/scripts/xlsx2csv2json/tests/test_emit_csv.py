"""Unit tests for :mod:`xlsx2csv2json.emit_csv` (010-06).

Covers single-region (file + stdout), multi-region subdirectory
layout, hyperlink markdown emission, no-formula regression,
path-traversal guard, UTF-8, LF line terminator.
"""
from __future__ import annotations

import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_FIX = Path(__file__).resolve().parent / "fixtures"


def _td(headers, rows, *, sheet="S", region_name=None, source="gap_detect",
        top_row=1, left_col=1):
    n_rows = top_row + len(rows) + (1 if headers else 0)
    n_cols = left_col + (len(headers) if headers else (len(rows[0]) if rows else 0))
    region = SimpleNamespace(
        sheet=sheet,
        top_row=top_row,
        left_col=left_col,
        bottom_row=n_rows - 1 if rows else top_row,
        right_col=n_cols - 1,
        source=source,
        name=region_name,
        listobject_header_row_count=None,
    )
    table_data = SimpleNamespace(
        region=region,
        headers=list(headers),
        rows=[list(r) for r in rows],
        warnings=[],
    )
    return region, table_data


# ===========================================================================
# Single-region writer
# ===========================================================================
class TestEmitCsvSingleRegion(unittest.TestCase):

    def test_to_file(self) -> None:
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["a", "b"], [[1, 2], [3, 4]], sheet="S")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            rc = emit_csv(
                iter([("S", r, t, None)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
            )
            self.assertEqual(rc, 0)
            with out.open("r", encoding="utf-8") as fp:
                rows = list(csv.reader(fp))
            self.assertEqual(rows, [["a", "b"], ["1", "2"], ["3", "4"]])

    def test_to_stdout(self) -> None:
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["a", "b"], [[1, 2]], sheet="S")
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc = emit_csv(
                iter([("S", r, t, None)]),
                output=None, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
            )
        finally:
            sys.stdout = old
        self.assertEqual(rc, 0)
        rows = list(csv.reader(io.StringIO(buf.getvalue())))
        self.assertEqual(rows, [["a", "b"], ["1", "2"]])

    def test_quote_minimal_for_comma_in_value(self) -> None:
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["x"], [["foo, bar"]], sheet="S")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            emit_csv(
                iter([("S", r, t, None)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
            )
            raw = out.read_text("utf-8")
        # Value with comma must be quoted.
        self.assertIn('"foo, bar"', raw)

    def test_lineterminator_lf_only(self) -> None:
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["a"], [[1]], sheet="S")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            emit_csv(
                iter([("S", r, t, None)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
            )
            raw = out.read_bytes()
        # Must NOT contain CRLF; line terminator is LF only.
        self.assertNotIn(b"\r\n", raw)
        self.assertIn(b"\n", raw)

    def test_utf8_no_bom(self) -> None:
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["имя"], [["алиса"]], sheet="S")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            emit_csv(
                iter([("S", r, t, None)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
            )
            raw = out.read_bytes()
        self.assertNotEqual(raw[:3], b"\xef\xbb\xbf")
        self.assertIn("алиса".encode("utf-8"), raw)


# ===========================================================================
# Multi-region writer
# ===========================================================================
class TestEmitCsvMultiRegion(unittest.TestCase):

    def test_subdirectory_layout(self) -> None:
        from xlsx2csv2json.emit_csv import emit_csv
        r1, t1 = _td(["a"], [[1]], sheet="SheetA", region_name="T1",
                     source="listobject")
        r2, t2 = _td(["b"], [[2]], sheet="SheetB", region_name="T2",
                     source="listobject")
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            rc = emit_csv(
                iter([("SheetA", r1, t1, None), ("SheetB", r2, t2, None)]),
                output=None, output_dir=out_dir,
                sheet_selector="all", tables_mode="listobjects",
                include_hyperlinks=False, datetime_format="ISO",
            )
            self.assertEqual(rc, 0)
            self.assertTrue((out_dir / "SheetA" / "T1.csv").is_file())
            self.assertTrue((out_dir / "SheetB" / "T2.csv").is_file())

    def test_sheet_name_with_underscores_not_split(self) -> None:
        """L4 lock: '__' is NOT treated as a separator; sheet 'a__b'
        produces directory 'a__b/'.
        """
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["a"], [[1]], sheet="with__double_underscore",
                   region_name="T", source="listobject")
        # Force multi-region trigger by providing a second region.
        r2, t2 = _td(["a"], [[2]], sheet="with__double_underscore",
                     region_name="T2", source="listobject")
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            emit_csv(
                iter([
                    ("with__double_underscore", r, t, None),
                    ("with__double_underscore", r2, t2, None),
                ]),
                output=None, output_dir=out_dir,
                sheet_selector="all", tables_mode="listobjects",
                include_hyperlinks=False, datetime_format="ISO",
            )
            self.assertTrue(
                (out_dir / "with__double_underscore" / "T.csv").is_file()
            )

    def test_M2_colliding_region_names_get_numeric_suffix(self) -> None:
        """M2 regression: two regions with the same (sheet, name) must
        NOT silently overwrite. Second writes to ``<name>__2.csv``.
        """
        from xlsx2csv2json.emit_csv import emit_csv
        r1, t1 = _td(["a"], [[1]], sheet="S", region_name="Table-1",
                     source="listobject")
        r2, t2 = _td(["b"], [[2]], sheet="S", region_name="Table-1",
                     source="gap_detect")
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            rc = emit_csv(
                iter([("S", r1, t1, None), ("S", r2, t2, None)]),
                output=None, output_dir=out_dir,
                sheet_selector="S", tables_mode="auto",
                include_hyperlinks=False, datetime_format="ISO",
            )
            self.assertEqual(rc, 0)
            self.assertTrue((out_dir / "S" / "Table-1.csv").is_file())
            self.assertTrue((out_dir / "S" / "Table-1__2.csv").is_file())

    def test_defensive_multi_region_without_output_dir_raises(self) -> None:
        from xlsx2csv2json.emit_csv import emit_csv
        from xlsx2csv2json import MultiTableRequiresOutputDir
        r1, t1 = _td(["a"], [[1]], sheet="S", region_name="T1",
                     source="listobject")
        r2, t2 = _td(["b"], [[2]], sheet="S", region_name="T2",
                     source="listobject")
        with self.assertRaises(MultiTableRequiresOutputDir):
            emit_csv(
                iter([("S", r1, t1, None), ("S", r2, t2, None)]),
                output=None, output_dir=None,
                sheet_selector="S", tables_mode="listobjects",
                include_hyperlinks=False, datetime_format="ISO",
            )

    def test_path_traversal_via_region_name_raises(self) -> None:
        """D-A8 — defence-in-depth even though dispatch validates first.

        Layout is ``<output_dir>/<sheet>/<region>.csv``. A region name
        with one ``..`` only escapes the sheet dir (back to output_dir)
        — that resolves INSIDE out_dir. To actually escape we need a
        region name that traverses two levels up.
        """
        from xlsx2csv2json.emit_csv import emit_csv
        from xlsx2csv2json import OutputPathTraversal
        r1, t1 = _td(["a"], [[1]], sheet="S",
                     region_name="../../escape", source="listobject")
        r2, t2 = _td(["b"], [[2]], sheet="S",
                     region_name="other", source="listobject")
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            with self.assertRaises(OutputPathTraversal):
                emit_csv(
                    iter([("S", r1, t1, None), ("S", r2, t2, None)]),
                    output=None, output_dir=out_dir,
                    sheet_selector="S", tables_mode="listobjects",
                    include_hyperlinks=False, datetime_format="ISO",
                )


# ===========================================================================
# Hyperlinks
# ===========================================================================
class TestEmitCsvHyperlinks(unittest.TestCase):

    def test_hyperlink_markdown_format(self) -> None:
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["text"], [["click"]], sheet="S")
        hl = {(1, 0): "https://example.com"}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            emit_csv(
                iter([("S", r, t, hl)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=True, datetime_format="ISO",
            )
            with out.open("r", encoding="utf-8") as fp:
                rows = list(csv.reader(fp))
        self.assertEqual(rows, [["text"], ["[click](https://example.com)"]])

    def test_no_hyperlink_formula_emission(self) -> None:
        """R10.d lock: NEVER emit '=HYPERLINK(' formula syntax."""
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["x"], [["a"]], sheet="S")
        hl = {(1, 0): "https://example.com"}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            emit_csv(
                iter([("S", r, t, hl)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=True, datetime_format="ISO",
            )
            raw = out.read_text("utf-8")
        self.assertNotIn("=HYPERLINK", raw)

    def test_empty_text_hyperlink(self) -> None:
        from xlsx2csv2json.emit_csv import _format_hyperlink_csv
        self.assertEqual(
            _format_hyperlink_csv("", "https://x"), "[](https://x)"
        )

    def test_none_text_hyperlink(self) -> None:
        from xlsx2csv2json.emit_csv import _format_hyperlink_csv
        self.assertEqual(
            _format_hyperlink_csv(None, "https://x"), "[](https://x)"
        )


# ===========================================================================
# Edge cases
# ===========================================================================
class TestEmitCsvEdgeCases(unittest.TestCase):

    def test_empty_payloads_returns_zero(self) -> None:
        from xlsx2csv2json.emit_csv import emit_csv
        rc = emit_csv(
            iter([]), output=None, output_dir=None,
            sheet_selector="all", tables_mode="whole",
            include_hyperlinks=False, datetime_format="ISO",
        )
        self.assertEqual(rc, 0)


# ===========================================================================
# E2E via convert_xlsx_to_csv
# ===========================================================================
class TestEmitCsvE2E(unittest.TestCase):

    def test_single_sheet_stdout(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_csv
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc = convert_xlsx_to_csv(
                _FIX / "single_sheet_simple.xlsx",
                sheet="Data",
            )
        finally:
            sys.stdout = old
        self.assertEqual(rc, 0)
        rows = list(csv.reader(io.StringIO(buf.getvalue())))
        self.assertEqual(rows[0], ["id", "name", "score"])
        self.assertEqual(rows[1], ["1", "alice", "95"])
        self.assertEqual(rows[2], ["2", "bob", "87"])
        self.assertEqual(rows[3], ["3", "carol", "92"])

    def test_multi_table_subdir_layout_e2e(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_csv
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "csv-out"
            rc = convert_xlsx_to_csv(
                _FIX / "multi_table_listobjects.xlsx",
                output_dir=out_dir,
                tables="listobjects",
                header_rows="auto",
            )
            self.assertEqual(rc, 0)
            rev = out_dir / "Summary" / "RevenueTable.csv"
            cost = out_dir / "Summary" / "CostsTable.csv"
            self.assertTrue(rev.is_file())
            self.assertTrue(cost.is_file())
            with rev.open("r", encoding="utf-8") as fp:
                rev_rows = list(csv.reader(fp))
            self.assertEqual(rev_rows[0], ["quarter", "product", "revenue"])
            self.assertEqual(rev_rows[1], ["Q1", "widget", "1000"])

    def test_multi_sheet_csv_stdout_rejected(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_csv
        # Two-sheets fixture without --output-dir → exit 2.
        old = sys.stderr
        sys.stderr = io.StringIO()
        try:
            rc = convert_xlsx_to_csv(_FIX / "two_sheets_simple.xlsx")
        finally:
            sys.stderr = old
        self.assertEqual(rc, 2)

    def test_hyperlinks_csv_e2e(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_csv
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            rc = convert_xlsx_to_csv(
                _FIX / "with_hyperlinks.xlsx", out,
                sheet="Links", include_hyperlinks=True,
            )
            self.assertEqual(rc, 0)
            raw = out.read_text("utf-8")
        # The fixture has hyperlinks at A2 and B3.
        # Expected first data row: "[click here](https://example.com/a),second"
        self.assertIn("[click here](https://example.com/a)", raw)
        self.assertIn("[third](https://example.com/b)", raw)
        # No formula emission.
        self.assertNotIn("=HYPERLINK", raw)


if __name__ == "__main__":
    unittest.main()

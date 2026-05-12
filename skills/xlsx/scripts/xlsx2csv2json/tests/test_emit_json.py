"""Unit tests for :mod:`xlsx2csv2json.emit_json` (010-05).

Covers the four JSON shape rules (R11 a–e), hyperlink dict-form
emission, multi-row header flatten (string vs array style), UTF-8 / no
BOM, indent-2 output.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


# ===========================================================================
# Synthetic-payload helpers — _shape_for_payloads is a pure function so we
# can test it without spinning up xlsx_read.
# ===========================================================================
def _td(headers, rows, *, sheet="S", region_name=None, source="gap_detect",
        top_row=1, left_col=1):
    """Build a synthetic (TableData, TableRegion) without xlsx_read.

    TableRegion fields needed by emit_json: sheet, top_row, bottom_row,
    left_col, right_col, source, name.
    """
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
# _shape_for_payloads — Rule 1–4 coverage
# ===========================================================================
class TestShapeForPayloads(unittest.TestCase):

    def test_rule1_single_sheet_single_region_flat_array(self) -> None:
        from xlsx2csv2json.emit_json import _shape_for_payloads
        region, td = _td(["a", "b"], [[1, 2], [3, 4]])
        shape = _shape_for_payloads(
            [("S1", region, td, None)],
            sheet_selector="S1", tables_mode="whole",
            header_flatten_style="string", include_hyperlinks=False,
        )
        self.assertEqual(shape, [{"a": 1, "b": 2}, {"a": 3, "b": 4}])

    def test_rule2_multi_sheet_single_region_each_dict_of_arrays(self) -> None:
        from xlsx2csv2json.emit_json import _shape_for_payloads
        r1, t1 = _td(["a"], [[1]], sheet="S1")
        r2, t2 = _td(["b"], [[2]], sheet="S2")
        shape = _shape_for_payloads(
            [("S1", r1, t1, None), ("S2", r2, t2, None)],
            sheet_selector="all", tables_mode="whole",
            header_flatten_style="string", include_hyperlinks=False,
        )
        self.assertEqual(shape, {"S1": [{"a": 1}], "S2": [{"b": 2}]})

    def test_rule3_multi_sheet_multi_region_nested(self) -> None:
        from xlsx2csv2json.emit_json import _shape_for_payloads
        r1, t1 = _td(["a"], [[1]], sheet="S1", region_name="T1", source="listobject")
        r2, t2 = _td(["b"], [[2]], sheet="S1", region_name="T2", source="listobject")
        r3, t3 = _td(["c"], [[3]], sheet="S2")
        shape = _shape_for_payloads(
            [("S1", r1, t1, None), ("S1", r2, t2, None), ("S2", r3, t3, None)],
            sheet_selector="all", tables_mode="listobjects",
            header_flatten_style="string", include_hyperlinks=False,
        )
        self.assertEqual(
            shape,
            {
                "S1": {"tables": {"T1": [{"a": 1}], "T2": [{"b": 2}]}},
                "S2": [{"c": 3}],
            },
        )

    def test_rule4_single_sheet_multi_region_flat_dict(self) -> None:
        from xlsx2csv2json.emit_json import _shape_for_payloads
        r1, t1 = _td(["a"], [[1]], sheet="S", region_name="A", source="listobject")
        r2, t2 = _td(["b"], [[2]], sheet="S", region_name="B", source="listobject")
        shape = _shape_for_payloads(
            [("S", r1, t1, None), ("S", r2, t2, None)],
            sheet_selector="S", tables_mode="listobjects",
            header_flatten_style="string", include_hyperlinks=False,
        )
        self.assertEqual(shape, {"A": [{"a": 1}], "B": [{"b": 2}]})

    def test_empty_payloads_returns_empty_list(self) -> None:
        from xlsx2csv2json.emit_json import _shape_for_payloads
        shape = _shape_for_payloads(
            [], sheet_selector="all", tables_mode="whole",
            header_flatten_style="string", include_hyperlinks=False,
        )
        self.assertEqual(shape, [])

    def test_region_order_preserved(self) -> None:
        from xlsx2csv2json.emit_json import _shape_for_payloads
        r_a, t_a = _td(["x"], [[1]], sheet="S", region_name="Alpha", source="listobject")
        r_b, t_b = _td(["x"], [[2]], sheet="S", region_name="Beta", source="listobject")
        shape = _shape_for_payloads(
            [("S", r_a, t_a, None), ("S", r_b, t_b, None)],
            sheet_selector="S", tables_mode="listobjects",
            header_flatten_style="string", include_hyperlinks=False,
        )
        # dict insertion-order: Alpha before Beta.
        self.assertEqual(list(shape.keys()), ["Alpha", "Beta"])


# ===========================================================================
# Header-flatten styles
# ===========================================================================
class TestHeaderFlattenStyle(unittest.TestCase):

    def test_string_style_flat_keys(self) -> None:
        from xlsx2csv2json.emit_json import _shape_for_payloads
        r, t = _td(["2026 plan › Q1", "2026 plan › Q2"], [[100, 200]])
        shape = _shape_for_payloads(
            [("S", r, t, None)],
            sheet_selector="S", tables_mode="whole",
            header_flatten_style="string", include_hyperlinks=False,
        )
        self.assertEqual(shape, [{"2026 plan › Q1": 100, "2026 plan › Q2": 200}])

    def test_array_style_splits_on_U203A(self) -> None:
        from xlsx2csv2json.emit_json import _shape_for_payloads
        r, t = _td(["2026 plan › Q1", "2026 plan › Q2"], [[100, 200]])
        shape = _shape_for_payloads(
            [("S", r, t, None)],
            sheet_selector="S", tables_mode="whole",
            header_flatten_style="array", include_hyperlinks=False,
        )
        # array-style produces [[{key:[...], value: v}, ...], ...]
        self.assertEqual(len(shape), 1)
        row = shape[0]
        self.assertEqual(len(row), 2)
        self.assertEqual(row[0]["key"], ["2026 plan", "Q1"])
        self.assertEqual(row[0]["value"], 100)
        self.assertEqual(row[1]["key"], ["2026 plan", "Q2"])
        self.assertEqual(row[1]["value"], 200)

    def test_array_style_single_row_header_keeps_one_element(self) -> None:
        from xlsx2csv2json.emit_json import _shape_for_payloads
        r, t = _td(["a", "b"], [[1, 2]])
        shape = _shape_for_payloads(
            [("S", r, t, None)],
            sheet_selector="S", tables_mode="whole",
            header_flatten_style="array", include_hyperlinks=False,
        )
        row = shape[0]
        self.assertEqual(row[0]["key"], ["a"])
        self.assertEqual(row[1]["key"], ["b"])


# ===========================================================================
# Hyperlinks
# ===========================================================================
class TestHyperlinkEmission(unittest.TestCase):

    def test_hyperlink_dict_shape(self) -> None:
        from xlsx2csv2json.emit_json import _shape_for_payloads
        r, t = _td(["text", "label"], [["click", "first"], ["plain", "second"]])
        # Hyperlinks map keyed by (offset_within_region, col_offset).
        # Header is row 0 of the region; data rows start at offset 1.
        # `click` is at (1, 0), `second` is at (2, 1).
        hl = {(1, 0): "https://example.com/a", (2, 1): "https://example.com/b"}
        shape = _shape_for_payloads(
            [("S", r, t, hl)],
            sheet_selector="S", tables_mode="whole",
            header_flatten_style="string", include_hyperlinks=True,
        )
        self.assertEqual(shape[0]["text"], {"value": "click", "href": "https://example.com/a"})
        self.assertEqual(shape[0]["label"], "first")
        self.assertEqual(shape[1]["text"], "plain")
        self.assertEqual(shape[1]["label"], {"value": "second", "href": "https://example.com/b"})

    def test_hyperlink_off_by_default(self) -> None:
        from xlsx2csv2json.emit_json import _shape_for_payloads
        r, t = _td(["text"], [["click"]])
        hl = {(1, 0): "https://example.com"}
        # include_hyperlinks=False ⇒ hl ignored.
        shape = _shape_for_payloads(
            [("S", r, t, hl)],
            sheet_selector="S", tables_mode="whole",
            header_flatten_style="string", include_hyperlinks=False,
        )
        self.assertEqual(shape, [{"text": "click"}])


# ===========================================================================
# emit_json — writer + indent + UTF-8
# ===========================================================================
class TestEmitJsonWriter(unittest.TestCase):

    def test_writes_to_file(self) -> None:
        from xlsx2csv2json.emit_json import emit_json
        r, t = _td(["a"], [[1]])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = emit_json(
                iter([("S", r, t, None)]),
                output=out, sheet_selector="S", tables_mode="whole",
                header_flatten_style="string", include_hyperlinks=False,
                datetime_format="ISO",
            )
            self.assertEqual(rc, 0)
            text = out.read_text(encoding="utf-8")
            shape = json.loads(text)
            self.assertEqual(shape, [{"a": 1}])

    def test_writes_to_stdout_when_output_none(self) -> None:
        from xlsx2csv2json.emit_json import emit_json
        r, t = _td(["a"], [[42]])
        import io
        old = sys.stdout
        buf = io.StringIO()
        sys.stdout = buf
        try:
            rc = emit_json(
                iter([("S", r, t, None)]),
                output=None, sheet_selector="S", tables_mode="whole",
                header_flatten_style="string", include_hyperlinks=False,
                datetime_format="ISO",
            )
        finally:
            sys.stdout = old
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue()), [{"a": 42}])

    def test_utf8_no_bom(self) -> None:
        from xlsx2csv2json.emit_json import emit_json
        r, t = _td(["имя"], [["алиса"]])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            emit_json(
                iter([("S", r, t, None)]),
                output=out, sheet_selector="S", tables_mode="whole",
                header_flatten_style="string", include_hyperlinks=False,
                datetime_format="ISO",
            )
            raw = out.read_bytes()
        # No BOM at start.
        self.assertNotEqual(raw[:3], b"\xef\xbb\xbf")
        # Non-ASCII chars preserved as UTF-8.
        self.assertIn("имя".encode("utf-8"), raw)
        self.assertIn("алиса".encode("utf-8"), raw)

    def test_indent_2(self) -> None:
        from xlsx2csv2json.emit_json import emit_json
        r, t = _td(["a"], [[1]])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            emit_json(
                iter([("S", r, t, None)]),
                output=out, sheet_selector="S", tables_mode="whole",
                header_flatten_style="string", include_hyperlinks=False,
                datetime_format="ISO",
            )
            text = out.read_text(encoding="utf-8")
        # Indent-2 means lines starting with `  ` (two spaces).
        lines = text.splitlines()
        self.assertTrue(any(line.startswith("  ") for line in lines))


# ===========================================================================
# E2E via convert_xlsx_to_json against real fixtures
# ===========================================================================
class TestEmitJsonE2E(unittest.TestCase):

    _F = Path(__file__).resolve().parent / "fixtures"

    def test_single_sheet_flat_array(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(self._F / "single_sheet_simple.xlsx", out)
            self.assertEqual(rc, 0)
            shape = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(
                shape,
                [
                    {"id": 1, "name": "alice", "score": 95},
                    {"id": 2, "name": "bob", "score": 87},
                    {"id": 3, "name": "carol", "score": 92},
                ],
            )

    def test_multi_sheet_dict_of_arrays(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(self._F / "two_sheets_simple.xlsx", out)
            self.assertEqual(rc, 0)
            shape = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(list(shape.keys()), ["SheetA", "SheetB"])
            self.assertEqual(shape["SheetA"], [{"k": "a", "v": 1}, {"k": "b", "v": 2}])
            self.assertEqual(shape["SheetB"], [{"x": "p", "y": 10}, {"x": "q", "y": 20}])

    def test_multi_table_single_sheet_flat_dict(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                self._F / "multi_table_listobjects.xlsx", out,
                tables="listobjects", header_rows="auto",
            )
            self.assertEqual(rc, 0)
            shape = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(set(shape.keys()), {"RevenueTable", "CostsTable"})
            self.assertEqual(len(shape["RevenueTable"]), 3)
            self.assertEqual(len(shape["CostsTable"]), 2)

    def test_hyperlinks_dict_shape_e2e(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                self._F / "with_hyperlinks.xlsx", out,
                include_hyperlinks=True,
            )
            self.assertEqual(rc, 0)
            shape = json.loads(out.read_text(encoding="utf-8"))
        # Flat array (single sheet, single region).
        self.assertIsInstance(shape, list)
        self.assertEqual(len(shape), 2)  # 2 data rows
        # Row 0: text="click here" (hyperlinked), label="second" (plain).
        self.assertEqual(
            shape[0]["text"],
            {"value": "click here", "href": "https://example.com/a"},
        )
        self.assertEqual(shape[0]["label"], "second")
        # Row 1: text="plain" (plain), label="third" (hyperlinked).
        self.assertEqual(shape[1]["text"], "plain")
        self.assertEqual(
            shape[1]["label"],
            {"value": "third", "href": "https://example.com/b"},
        )


if __name__ == "__main__":
    unittest.main()

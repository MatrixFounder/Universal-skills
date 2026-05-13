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


def _materialised_shape(payloads, **kwargs):
    """Test helper: call `_shape_for_payloads` and, if it returns
    the R11.1 streaming sentinel (xlsx-8a-08), materialise the
    streaming output by routing the single payload through
    `_rows_to_dicts` and wrapping in `list(...)`. Lets existing
    R11.1 tests keep their list-comparison assertions without
    knowing about the sentinel.
    """
    from xlsx2csv2json.emit_json import (
        _R11_1_STREAM_SENTINEL, _rows_to_dicts, _shape_for_payloads,
    )
    shape = _shape_for_payloads(payloads, **kwargs)
    if shape is _R11_1_STREAM_SENTINEL:
        # R11.1 case: exactly one payload; reconstruct the list form.
        _, _, table_data, hl_map = payloads[0]
        return list(_rows_to_dicts(
            table_data, hl_map,
            kwargs["header_flatten_style"],
            kwargs["include_hyperlinks"],
            kwargs.get("drop_empty_rows", False),
        ))
    return shape


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
        region, td = _td(["a", "b"], [[1, 2], [3, 4]])
        shape = _materialised_shape(
            [("S1", region, td, None)],
            sheet_selector="S1", tables_mode="whole",
            header_flatten_style="string", include_hyperlinks=False,
        )
        self.assertEqual(shape, [{"a": 1, "b": 2}, {"a": 3, "b": 4}])

    def test_rule2_multi_sheet_single_region_each_dict_of_arrays(self) -> None:
        r1, t1 = _td(["a"], [[1]], sheet="S1")
        r2, t2 = _td(["b"], [[2]], sheet="S2")
        shape = _materialised_shape(
            [("S1", r1, t1, None), ("S2", r2, t2, None)],
            sheet_selector="all", tables_mode="whole",
            header_flatten_style="string", include_hyperlinks=False,
        )
        self.assertEqual(shape, {"S1": [{"a": 1}], "S2": [{"b": 2}]})

    def test_rule3_multi_sheet_multi_region_nested(self) -> None:
        r1, t1 = _td(["a"], [[1]], sheet="S1", region_name="T1", source="listobject")
        r2, t2 = _td(["b"], [[2]], sheet="S1", region_name="T2", source="listobject")
        r3, t3 = _td(["c"], [[3]], sheet="S2")
        shape = _materialised_shape(
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
        r1, t1 = _td(["a"], [[1]], sheet="S", region_name="A", source="listobject")
        r2, t2 = _td(["b"], [[2]], sheet="S", region_name="B", source="listobject")
        shape = _materialised_shape(
            [("S", r1, t1, None), ("S", r2, t2, None)],
            sheet_selector="S", tables_mode="listobjects",
            header_flatten_style="string", include_hyperlinks=False,
        )
        self.assertEqual(shape, {"A": [{"a": 1}], "B": [{"b": 2}]})

    def test_empty_payloads_returns_empty_list(self) -> None:
        shape = _materialised_shape(
            [], sheet_selector="all", tables_mode="whole",
            header_flatten_style="string", include_hyperlinks=False,
        )
        self.assertEqual(shape, [])

    def test_region_order_preserved(self) -> None:
        r_a, t_a = _td(["x"], [[1]], sheet="S", region_name="Alpha", source="listobject")
        r_b, t_b = _td(["x"], [[2]], sheet="S", region_name="Beta", source="listobject")
        shape = _materialised_shape(
            [("S", r_a, t_a, None), ("S", r_b, t_b, None)],
            sheet_selector="S", tables_mode="listobjects",
            header_flatten_style="string", include_hyperlinks=False,
        )
        # dict insertion-order: Alpha before Beta.
        self.assertEqual(list(shape.keys()), ["Alpha", "Beta"])


# ===========================================================================
# Header-flatten styles
# ===========================================================================
class TestDuplicateHeaderDisambiguation(unittest.TestCase):
    """**vdd-adversarial R27 fix:** `_rows_to_string_style` previously
    did naive ``d[header] = value`` which silently dropped data when
    two columns had the same header (the natural consequence of a
    wide title-merge sticky-fill on layout-heavy reports — `A1:F1`
    merge produces 6 columns with identical keys). 5 of 7 columns
    were lost per Timesheet row on the masterdata fixture.
    """

    def test_duplicate_headers_get_numeric_suffix_preserving_all_data(self) -> None:
        """Two columns with header 'title' should produce keys
        'title' and 'title__2' — neither value lost.
        """
        from xlsx2csv2json.emit_json import _rows_to_string_style
        result = list(_rows_to_string_style(
            headers=["title", "title", ""],
            rows=[["A1", "B1", "C1"], ["A2", "B2", "C2"]],
            hl_map=None, header_band=1, include_hyperlinks=False,
        ))
        self.assertEqual(len(result), 2)
        # Row 0: all 3 values preserved across 3 distinct keys.
        self.assertEqual(result[0]["title"], "A1")
        self.assertEqual(result[0]["title__2"], "B1")
        self.assertEqual(result[0][""], "C1")
        # Row 1: same disambiguation scheme.
        self.assertEqual(result[1]["title"], "A2")
        self.assertEqual(result[1]["title__2"], "B2")

    def test_six_duplicate_headers_get_2_through_6_suffix(self) -> None:
        """Worst-case from masterdata Timesheet: 6 columns sticky-filled
        from a single title merge `A1:F1`. Must produce
        ['title', 'title__2', 'title__3', 'title__4', 'title__5', 'title__6'].
        """
        from xlsx2csv2json.emit_json import _rows_to_string_style
        result = list(_rows_to_string_style(
            headers=["title"] * 6 + [""],
            rows=[["v1", "v2", "v3", "v4", "v5", "v6", "v7"]],
            hl_map=None, header_band=1, include_hyperlinks=False,
        ))
        row = result[0]
        self.assertEqual(row["title"], "v1")
        for i in range(2, 7):
            self.assertEqual(row[f"title__{i}"], f"v{i}")
        self.assertEqual(row[""], "v7")
        # CRITICAL: no value silently dropped.
        self.assertEqual(len(row), 7)

    def test_unique_headers_emitted_unchanged(self) -> None:
        """Regression guard: when headers are already unique, the
        disambiguation step is a no-op (no surprise __2 suffix).
        """
        from xlsx2csv2json.emit_json import _rows_to_string_style
        result = list(_rows_to_string_style(
            headers=["Дата", "Часы", "Описание"],
            rows=[["2026-04-01", 8, "task"]],
            hl_map=None, header_band=1, include_hyperlinks=False,
        ))
        self.assertEqual(
            result[0],
            {"Дата": "2026-04-01", "Часы": 8, "Описание": "task"},
        )

    def test_disambiguate_helper_isolated(self) -> None:
        from xlsx2csv2json.emit_json import _disambiguate_duplicate_headers
        self.assertEqual(
            _disambiguate_duplicate_headers(["a", "a", "b", "a", "b"]),
            ["a", "a__2", "b", "a__3", "b__2"],
        )
        self.assertEqual(
            _disambiguate_duplicate_headers([]), []
        )
        self.assertEqual(
            _disambiguate_duplicate_headers(["", "", ""]),
            ["", "__2", "__3"],
        )


class TestDropEmptyRows(unittest.TestCase):
    """**TASK 010 §11.7 R28:** `--drop-empty-rows` skips rows where
    every value is None or empty string. Conservative — rows with at
    least one non-null cell survive.
    """

    def test_string_style_drops_all_null_row(self) -> None:
        from xlsx2csv2json.emit_json import _rows_to_string_style
        result = list(_rows_to_string_style(
            headers=["a", "b", "c"],
            rows=[
                ["x", 1, "y"],     # full row → kept
                [None, None, None],  # all-null → DROPPED
                ["", "", ""],       # all-empty-string → DROPPED
                [None, "kept", None],  # partial → kept
            ],
            hl_map=None, header_band=1, include_hyperlinks=False,
            drop_empty_rows=True,
        ))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], {"a": "x", "b": 1, "c": "y"})
        self.assertEqual(result[1], {"a": None, "b": "kept", "c": None})

    def test_string_style_off_by_default_keeps_all(self) -> None:
        from xlsx2csv2json.emit_json import _rows_to_string_style
        result = list(_rows_to_string_style(
            headers=["a"],
            rows=[["x"], [None], ["y"]],
            hl_map=None, header_band=1, include_hyperlinks=False,
        ))
        self.assertEqual(len(result), 3)  # default: keep all

    def test_array_style_drops_all_null_row(self) -> None:
        from xlsx2csv2json.emit_json import _rows_to_array_style
        result = list(_rows_to_array_style(
            headers=["a", "b"],
            rows=[["x", 1], [None, None]],
            hl_map=None, header_band=1, include_hyperlinks=False,
            drop_empty_rows=True,
        ))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0]["value"], "x")

    def test_hyperlink_in_otherwise_empty_row_keeps_row(self) -> None:
        """A row with all None values BUT a hyperlink href IS NOT empty
        — the href payload is real content. Verifies the conservative
        predicate honours hyperlink presence.
        """
        from xlsx2csv2json.emit_json import _rows_to_string_style
        result = list(_rows_to_string_style(
            headers=["a", "b"],
            rows=[[None, None]],
            hl_map={(1, 0): "https://example.com"},
            header_band=1, include_hyperlinks=True,
            drop_empty_rows=True,
        ))
        self.assertEqual(len(result), 1)  # NOT dropped


class TestHeaderFlattenStyle(unittest.TestCase):

    def test_string_style_flat_keys(self) -> None:
        r, t = _td(["2026 plan › Q1", "2026 plan › Q2"], [[100, 200]])
        shape = _materialised_shape(
            [("S", r, t, None)],
            sheet_selector="S", tables_mode="whole",
            header_flatten_style="string", include_hyperlinks=False,
        )
        self.assertEqual(shape, [{"2026 plan › Q1": 100, "2026 plan › Q2": 200}])

    def test_array_style_splits_on_U203A(self) -> None:
        r, t = _td(["2026 plan › Q1", "2026 plan › Q2"], [[100, 200]])
        shape = _materialised_shape(
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
        r, t = _td(["a", "b"], [[1, 2]])
        shape = _materialised_shape(
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
        r, t = _td(["text", "label"], [["click", "first"], ["plain", "second"]])
        # Hyperlinks map keyed by (offset_within_region, col_offset).
        # Header is row 0 of the region; data rows start at offset 1.
        # `click` is at (1, 0), `second` is at (2, 1).
        hl = {(1, 0): "https://example.com/a", (2, 1): "https://example.com/b"}
        shape = _materialised_shape(
            [("S", r, t, hl)],
            sheet_selector="S", tables_mode="whole",
            header_flatten_style="string", include_hyperlinks=True,
        )
        self.assertEqual(shape[0]["text"], {"value": "click", "href": "https://example.com/a"})
        self.assertEqual(shape[0]["label"], "first")
        self.assertEqual(shape[1]["text"], "plain")
        self.assertEqual(shape[1]["label"], {"value": "second", "href": "https://example.com/b"})

    def test_hyperlink_off_by_default(self) -> None:
        r, t = _td(["text"], [["click"]])
        hl = {(1, 0): "https://example.com"}
        # include_hyperlinks=False ⇒ hl ignored.
        shape = _materialised_shape(
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


# ===========================================================================
# xlsx-8a-07 (R9, PERF-HIGH-2 partial) — `json.dump(fp)` file output
# ===========================================================================

class TestR9JsonDumpFileOutput(unittest.TestCase):
    """xlsx-8a-07 (R9): file-output branch switches from
    `json.dumps(shape, ...) + write_text` to
    `json.dump(shape, fp, ...) + fp.write('\\n')`. Byte-identical
    to v1 on every R11.2-4 fixture.
    """

    def _make_R11_2_payloads(self):
        """Build a 2-sheet single-region-each payload list (R11.2)."""
        r_a, td_a = _td(["id", "name"], [[1, "alice"]],
                        sheet="A", region_name="TA", source="listobject")
        r_b, td_b = _td(["k", "v"], [[2, "bob"]],
                        sheet="B", region_name="TB", source="listobject")
        return [("A", r_a, td_a, None), ("B", r_b, td_b, None)]

    def test_R9_file_byte_identical_to_v1(self) -> None:
        """Post-R9 file output is byte-identical to the v1 baseline."""
        from xlsx2csv2json.emit_json import _shape_for_payloads, emit_json

        payloads = self._make_R11_2_payloads()
        shape = _materialised_shape(
            payloads,
            sheet_selector="all", tables_mode="whole",
            header_flatten_style="string",
            include_hyperlinks=False, drop_empty_rows=False,
        )
        v1_bytes = (
            json.dumps(shape, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
        ).encode("utf-8")

        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "out.json"
            emit_json(
                iter(payloads),
                output=out_path,
                sheet_selector="all", tables_mode="whole",
                header_flatten_style="string",
                include_hyperlinks=False,
                datetime_format="ISO",
                drop_empty_rows=False,
            )
            r9_bytes = out_path.read_bytes()

        self.assertEqual(r9_bytes, v1_bytes)

    def test_R9_file_output_drops_string_buffer_copy(self) -> None:
        """tracemalloc-based assertion: the R9 file-output path's
        peak resident memory is strictly LESS than the v1 path that
        materialised the full `text = json.dumps(...)` string buffer.
        """
        import tracemalloc
        from xlsx2csv2json.emit_json import _shape_for_payloads, _json_default

        # Build a moderately-sized payload so savings are measurable
        # above the tracemalloc noise floor.
        payloads = []
        for i in range(20):
            r, td = _td(
                ["a", "b", "c", "d", "e"],
                [[r_idx, f"val_{r_idx}", r_idx * 2,
                  f"x_{r_idx}_{i}", r_idx * 1.5]
                 for r_idx in range(200)],
                sheet=f"S{i}", region_name=f"T{i}", source="listobject",
            )
            payloads.append((f"S{i}", r, td, None))

        shape = _materialised_shape(
            payloads,
            sheet_selector="all", tables_mode="whole",
            header_flatten_style="string",
            include_hyperlinks=False, drop_empty_rows=False,
        )

        with tempfile.TemporaryDirectory() as td:
            v1_path = Path(td) / "v1.json"
            tracemalloc.start()
            text = json.dumps(
                shape, ensure_ascii=False, indent=2, sort_keys=False,
                default=_json_default,
            )
            v1_path.write_text(text + "\n", encoding="utf-8")
            _, v1_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            del text  # free reference before R9 path measures.

            r9_path = Path(td) / "r9.json"
            tracemalloc.start()
            with r9_path.open("w", encoding="utf-8") as fp:
                json.dump(
                    shape, fp, ensure_ascii=False, indent=2,
                    sort_keys=False, default=_json_default,
                )
                fp.write("\n")
            _, r9_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            self.assertEqual(v1_path.read_bytes(), r9_path.read_bytes())
            self.assertLess(
                r9_peak, v1_peak,
                f"R9 peak {r9_peak} not < v1 peak {v1_peak} "
                f"(savings: {v1_peak - r9_peak} bytes)",
            )


# ===========================================================================
# xlsx-8a-08 (R10, PERF-HIGH-2 closure for R11.1) — streaming
# ===========================================================================

class TestR10R111Streaming(unittest.TestCase):
    """xlsx-8a-08 (R10): R11.1 single-region streaming via
    `_stream_single_region_json`. Byte-identity invariant: the file
    written by the streaming path is byte-identical to the v1
    `json.dumps(shape, indent=2) + "\\n"` baseline on every R11.1
    fixture, INCLUDING the empty-payload case (`[]\\n`, per
    arch-review M3 fix).
    """

    def _emit_via_streaming(self, payloads, output_path, **kw):
        from xlsx2csv2json.emit_json import emit_json
        emit_json(
            iter(payloads),
            output=output_path,
            sheet_selector=kw.get("sheet_selector", "S"),
            tables_mode=kw.get("tables_mode", "whole"),
            header_flatten_style=kw.get("header_flatten_style", "string"),
            include_hyperlinks=kw.get("include_hyperlinks", False),
            datetime_format="ISO",
            drop_empty_rows=kw.get("drop_empty_rows", False),
        )

    def _v1_reference(self, payloads, **kw):
        """v1 reference path — materialise the full shape and serialise
        via `json.dumps(shape, indent=2) + "\\n"`. Held inline so the
        R10 streaming output can be `diff`-ed against it byte-by-byte.
        """
        from xlsx2csv2json.emit_json import _rows_to_dicts, _json_default
        _, _, td, hl = payloads[0]
        shape = list(_rows_to_dicts(
            td, hl,
            kw.get("header_flatten_style", "string"),
            kw.get("include_hyperlinks", False),
            kw.get("drop_empty_rows", False),
        ))
        return (
            json.dumps(shape, ensure_ascii=False, indent=2,
                       sort_keys=False, default=_json_default) + "\n"
        ).encode("utf-8")

    def test_R10_stream_byte_identical_to_v1_simple(self) -> None:
        """Single sheet, single region, 2 rows × 2 cols — streaming
        output byte-identical to v1."""
        region, td = _td(["a", "b"], [[1, 2], [3, 4]], sheet="S",
                         region_name="T", source="listobject")
        payloads = [("S", region, td, None)]
        with tempfile.TemporaryDirectory() as tdir:
            out = Path(tdir) / "stream.json"
            self._emit_via_streaming(payloads, out)
            stream_bytes = out.read_bytes()
        v1_bytes = self._v1_reference(payloads)
        self.assertEqual(stream_bytes, v1_bytes)

    def test_R10_stream_empty_table_v1_byte_identical(self) -> None:
        """Empty-payload (no rows): streaming emits `[]\\n` (3 bytes)
        matching v1 `json.dumps([], indent=2) + '\\n'`. M3 fix locks
        the byte-identity invariant for the degenerate case.
        """
        region, td = _td(["a"], [], sheet="S", region_name="T",
                         source="listobject")
        payloads = [("S", region, td, None)]
        with tempfile.TemporaryDirectory() as tdir:
            out = Path(tdir) / "empty.json"
            self._emit_via_streaming(payloads, out)
            stream_bytes = out.read_bytes()
        self.assertEqual(stream_bytes, b"[]\n")

    def test_R10_stream_with_hyperlinks(self) -> None:
        """Hyperlink wrapper dicts (`{value, href}`) survive the
        streaming path unchanged.
        """
        region, td = _td(["url"], [["Click"]], sheet="S",
                         region_name="T", source="listobject")
        hl_map = {(1, 0): "https://example.com"}
        payloads = [("S", region, td, hl_map)]
        with tempfile.TemporaryDirectory() as tdir:
            out = Path(tdir) / "hl.json"
            self._emit_via_streaming(payloads, out, include_hyperlinks=True)
            stream_text = out.read_text(encoding="utf-8")
            v1_text = self._v1_reference(
                payloads, include_hyperlinks=True
            ).decode("utf-8")
        self.assertEqual(stream_text, v1_text)
        self.assertIn('"value": "Click"', stream_text)
        self.assertIn('"href": "https://example.com"', stream_text)

    def test_R10_stream_array_style(self) -> None:
        """`--header-flatten-style array` routes through
        `_rows_to_array_style` generator. Output byte-identical to v1.
        """
        region, td = _td(["a › b", "c"], [[1, 2]], sheet="S",
                         region_name="T", source="listobject")
        payloads = [("S", region, td, None)]
        with tempfile.TemporaryDirectory() as tdir:
            out = Path(tdir) / "arr.json"
            self._emit_via_streaming(
                payloads, out, header_flatten_style="array"
            )
            stream_bytes = out.read_bytes()
        v1_bytes = self._v1_reference(
            payloads, header_flatten_style="array"
        )
        self.assertEqual(stream_bytes, v1_bytes)

    def test_R10_R11_2_to_4_unchanged(self) -> None:
        """R11.2 (multi-sheet single-region per sheet) does NOT use
        streaming — it goes through R9 `json.dump(fp)`. The shape
        dict-of-arrays form is preserved.
        """
        r1, t1 = _td(["a"], [[1]], sheet="A")
        r2, t2 = _td(["b"], [[2]], sheet="B")
        payloads = [("A", r1, t1, None), ("B", r2, t2, None)]
        with tempfile.TemporaryDirectory() as tdir:
            out = Path(tdir) / "multi.json"
            self._emit_via_streaming(payloads, out)
            data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data, {"A": [{"a": 1}], "B": [{"b": 2}]})

    def test_R10_rows_to_dicts_is_generator(self) -> None:
        """`_rows_to_dicts` must return an iterator after the
        xlsx-8a-08 refactor.
        """
        from xlsx2csv2json.emit_json import _rows_to_dicts
        region, td = _td(["a"], [[1]], sheet="S")
        result = _rows_to_dicts(
            td, None, "string", include_hyperlinks=False,
        )
        self.assertTrue(hasattr(result, "__next__"))


if __name__ == "__main__":
    unittest.main()

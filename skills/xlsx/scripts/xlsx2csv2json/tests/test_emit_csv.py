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

    def test_encoding_utf8_sig_writes_bom(self) -> None:
        """TASK 010 §11 patch v2: `--encoding utf-8-sig` prepends the
        UTF-8 BOM (0xEF 0xBB 0xBF) so Excel on Windows/macOS auto-
        detects the charset on .csv open.
        """
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["Дата", "Часы"], [["2026-04-01", 8]], sheet="S")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            rc = emit_csv(
                iter([("S", r, t, None)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
                encoding="utf-8-sig",
            )
            self.assertEqual(rc, 0)
            raw = out.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            # Body decodes cleanly as UTF-8 (after stripping BOM).
            decoded = raw.decode("utf-8-sig")
            self.assertIn("Дата", decoded)

    def test_encoding_utf8_sig_multi_region_each_file_has_bom(self) -> None:
        """**vdd-multi-2 LOW fix:** every per-region file in
        `_emit_multi_region` must get the BOM, not just the first.
        Regression guard for an accidental drop of the kwarg in the
        plumbing chain.
        """
        from xlsx2csv2json.emit_csv import emit_csv
        r1, t1 = _td(["a", "b"], [["Привет", 1]], sheet="S1")
        r2, t2 = _td(["c", "d"], [["Мир", 2]], sheet="S2")
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            rc = emit_csv(
                iter([("S1", r1, t1, None), ("S2", r2, t2, None)]),
                output=None, output_dir=out_dir,
                sheet_selector="all", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
                encoding="utf-8-sig",
            )
            self.assertEqual(rc, 0)
            files = list(out_dir.rglob("*.csv"))
            self.assertEqual(len(files), 2)
            for f in files:
                self.assertTrue(
                    f.read_bytes().startswith(b"\xef\xbb\xbf"),
                    f"missing BOM in {f}",
                )

    def test_delimiter_semicolon_writes_semi_separated(self) -> None:
        """**TASK 010 §11.7 R26:** `--delimiter ;` (passed to emit_csv
        as `delimiter=";"`) emits semicolon-separated rows. Excel on
        RU / EU locales (where ',' is the decimal separator) needs
        ';' to parse the file into columns on double-click open.
        """
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["Дата", "Часы"], [["2026-04-01", 8]], sheet="S")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            emit_csv(
                iter([("S", r, t, None)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
                delimiter=";",
            )
            text = out.read_text(encoding="utf-8")
            self.assertIn("Дата;Часы", text)
            self.assertIn("2026-04-01;8", text)
            self.assertNotIn("Дата,Часы", text)

    def test_emit_csv_with_literal_tab_delimiter_writes_tsv(self) -> None:
        """`delimiter='\\t'` (raw char, not the 'tab' alias) produces
        TSV-style output. This is the **internal API** layer test —
        it bypasses the CLI alias-resolution at `_delimiter_type`; for
        the CLI-level path see
        `test_cli.py::TestCliDelimiterAliasResolution`.
        """
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["a", "b"], [[1, 2]], sheet="S")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.tsv"
            emit_csv(
                iter([("S", r, t, None)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
                delimiter="\t",
            )
            text = out.read_text(encoding="utf-8")
            self.assertIn("a\tb", text)
            self.assertIn("1\t2", text)

    def test_delimiter_default_is_comma(self) -> None:
        """Default delimiter when not passed is `,` (backward-compat)."""
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["a", "b"], [[1, 2]], sheet="S")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            emit_csv(
                iter([("S", r, t, None)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
            )
            self.assertIn("a,b", out.read_text(encoding="utf-8"))

    def test_delimiter_multi_region_each_file_gets_delimiter(self) -> None:
        """Multi-region emit applies the same delimiter to every per-region
        file (regression guard for accidental kwarg drop in the plumbing).
        """
        from xlsx2csv2json.emit_csv import emit_csv
        r1, t1 = _td(["a", "b"], [[1, 2]], sheet="S1")
        r2, t2 = _td(["c", "d"], [[3, 4]], sheet="S2")
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            emit_csv(
                iter([("S1", r1, t1, None), ("S2", r2, t2, None)]),
                output=None, output_dir=out_dir,
                sheet_selector="all", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
                delimiter=";",
            )
            for f in out_dir.rglob("*.csv"):
                text = f.read_text(encoding="utf-8")
                self.assertIn(";", text, f"missing ';' in {f}")
                # No commas should appear as separators (values themselves
                # don't contain commas in this fixture).
                self.assertNotIn(",", text)

    def test_drop_empty_rows_skips_all_null_lines(self) -> None:
        """`--drop-empty-rows` on the CSV side: rows where every value
        is None or '' are silently dropped. Conservative — partial-null
        rows are kept.
        """
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(
            ["a", "b"],
            [["x", 1], [None, None], ["", ""], [None, "y"]],
            sheet="S",
        )
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            rc = emit_csv(
                iter([("S", r, t, None)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
                drop_empty_rows=True,
            )
            self.assertEqual(rc, 0)
            rows = list(csv.reader(out.open(encoding="utf-8")))
            # Expect 3 rows: header + ["x","1"] + ["","y"]
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0], ["a", "b"])
            self.assertEqual(rows[1], ["x", "1"])
            self.assertEqual(rows[2], ["", "y"])

    def test_drop_empty_rows_off_by_default(self) -> None:
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["a"], [["x"], [None], ["y"]], sheet="S")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            emit_csv(
                iter([("S", r, t, None)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
            )
            rows = list(csv.reader(out.open(encoding="utf-8")))
            # default: keep all 4 (header + 3 data including the null row)
            self.assertEqual(len(rows), 4)

    def test_encoding_utf8_default_no_bom(self) -> None:
        """Default encoding is plain UTF-8 (no BOM) — pandas / jq do
        not need BOM and treat it as part of the first header cell.
        """
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["a", "b"], [[1, 2]], sheet="S")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            emit_csv(
                iter([("S", r, t, None)]),
                output=out, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
            )
            raw = out.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))

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

    def test_R1_collision_suffix_caps_at_1000(self) -> None:
        """xlsx-8a-01 (R1, Sec-HIGH-3): 1001 payloads sharing the
        same ``(sheet, region_name)`` trigger ``CollisionSuffixExhausted``
        before the per-region path-resolve loop blows wall-clock.
        Cap fires on the 1001st suffix attempt (D-A14 cap+1).
        """
        from xlsx2csv2json.emit_csv import emit_csv
        from xlsx2csv2json.exceptions import CollisionSuffixExhausted
        # Build 1001 payloads all named ``Table`` on sheet ``S``.
        payloads = []
        for _ in range(1001):
            r, t = _td(["a"], [[1]], sheet="S", region_name="Table",
                       source="listobject")
            payloads.append(("S", r, t, None))
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            with self.assertRaises(CollisionSuffixExhausted) as ctx:
                emit_csv(
                    iter(payloads),
                    output=None, output_dir=out_dir,
                    sheet_selector="S", tables_mode="listobjects",
                    include_hyperlinks=False, datetime_format="ISO",
                )
            # No absolute paths in the message (cross-5 envelope
            # contract — only basenames / region / sheet names).
            msg = str(ctx.exception)
            self.assertNotIn(str(out_dir), msg)
            self.assertIn("Table", msg)
            self.assertIn("S", msg)
            # Exit code is 2 per cross-5 envelope mapping.
            self.assertEqual(ctx.exception.CODE, 2)

    # ===================================================================
    # xlsx-8a-04 (R4, Sec-MED-1) — `--escape-formulas` defang transform
    # ===================================================================
    # Tests live in TestEmitCsvMultiRegion only for proximity to R1
    # tests; logically they exercise the single-region + _write_region_csv
    # path. The 15-test budget per R4 sub-feature (g) is delivered as:
    #   1 off-noop on 6-sentinel payload
    #   6 quote-prefix tests (one per sentinel)
    #   6 strip tests (one per sentinel)
    #   1 hyperlink-defang interaction (markdown wrapper survives)
    #   1 end-to-end DDE payload (`=cmd|'/C calc'!A1`)
    # The JSON-shim no-effect warning is hosted in test_cli.py.

    def _emit_single_csv_capturing(
        self, value: Any, escape_formulas: str,
    ) -> str:
        """Helper: emit a single-cell single-region CSV via emit_csv
        and return the resulting bytes (header row + 1 data row).
        """
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["h"], [[value]], sheet="S", region_name="T",
                   source="listobject")
        buf = io.StringIO()
        # We cannot pass buf directly through `output=Path`; route via
        # stdout-monkeypatch using `emit_csv(payloads, output=None)`.
        # `_emit_single_region` writes to sys.stdout when output is None.
        captured: list[str] = []
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            emit_csv(
                iter([("S", r, t, None)]),
                output=None, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=False, datetime_format="ISO",
                escape_formulas=escape_formulas,
            )
            captured.append(sys.stdout.getvalue())
        finally:
            sys.stdout = old_stdout
        return captured[0]

    def test_R4_escape_off_no_transform_on_6_sentinels(self) -> None:
        """`off` (default) leaves all 6 sentinel-prefixed cells
        verbatim — byte-identical to xlsx-8 baseline.
        """
        for sentinel in ("=", "+", "-", "@", "\t", "\r"):
            payload = sentinel + "cmd"
            out = self._emit_single_csv_capturing(payload, "off")
            # The cell appears in the output unchanged (csv may
            # quote the field if it contains delimiter-conflicting
            # characters, but the leading sentinel survives).
            self.assertIn(sentinel, out)

    def test_R4_escape_quote_prefixes_equals(self) -> None:
        out = self._emit_single_csv_capturing("=cmd", "quote")
        self.assertIn("'=cmd", out)

    def test_R4_escape_quote_prefixes_plus(self) -> None:
        out = self._emit_single_csv_capturing("+SUM(1)", "quote")
        self.assertIn("'+SUM(1)", out)

    def test_R4_escape_quote_prefixes_minus(self) -> None:
        out = self._emit_single_csv_capturing("-1", "quote")
        self.assertIn("'-1", out)

    def test_R4_escape_quote_prefixes_at(self) -> None:
        out = self._emit_single_csv_capturing("@SUM(A1)", "quote")
        self.assertIn("'@SUM(A1)", out)

    def test_R4_escape_quote_prefixes_tab(self) -> None:
        out = self._emit_single_csv_capturing("\tHTML", "quote")
        # CSV will quote the field because it contains a literal
        # tab/control char — check the quoted form has leading `'`
        # immediately after the opening quote.
        self.assertTrue("'\t" in out or '"\'\t' in out)

    def test_R4_escape_quote_prefixes_cr(self) -> None:
        out = self._emit_single_csv_capturing("\rOK", "quote")
        self.assertTrue("'\r" in out or '"\'\r' in out)

    def test_R4_escape_strip_drops_equals(self) -> None:
        out = self._emit_single_csv_capturing("=cmd", "strip")
        self.assertNotIn("=cmd", out)

    def test_R4_escape_strip_drops_plus(self) -> None:
        out = self._emit_single_csv_capturing("+SUM(1)", "strip")
        self.assertNotIn("+SUM(1)", out)

    def test_R4_escape_strip_drops_minus(self) -> None:
        out = self._emit_single_csv_capturing("-1", "strip")
        # The bare cell value `-1` becomes empty — no `-1` substring
        # appears in the data row.
        # (Header row is "h" and won't contain "-1".)
        data_row = out.splitlines()[-1] if out.splitlines() else ""
        self.assertNotIn("-1", data_row)

    def test_R4_escape_strip_drops_at(self) -> None:
        out = self._emit_single_csv_capturing("@SUM(A1)", "strip")
        self.assertNotIn("@SUM(A1)", out)

    def test_R4_escape_strip_drops_tab(self) -> None:
        out = self._emit_single_csv_capturing("\tHTML", "strip")
        self.assertNotIn("HTML", out)

    def test_R4_escape_strip_drops_cr(self) -> None:
        out = self._emit_single_csv_capturing("\rOK", "strip")
        self.assertNotIn("OK", out)

    def test_R4_escape_quote_does_not_mutate_hyperlink_cells(self) -> None:
        """Hyperlink cells emit as ``[text](url)`` — the leading
        ``[`` is not a sentinel, so the markdown wrapper naturally
        defangs any sentinel-prefixed text inside. Locked behaviour
        per task §1.2 R4 / D-A13.
        """
        from xlsx2csv2json.emit_csv import emit_csv
        r, t = _td(["h"], [["=cmd"]], sheet="S", region_name="T",
                   source="listobject")
        hl_map = {(1, 0): "https://example.com"}  # row 1 = data row
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            emit_csv(
                iter([("S", r, t, hl_map)]),
                output=None, output_dir=None,
                sheet_selector="S", tables_mode="whole",
                include_hyperlinks=True, datetime_format="ISO",
                escape_formulas="quote",
            )
        finally:
            sys.stdout = old_stdout
        out = captured.getvalue()
        # Hyperlink wrapper survives unchanged; embedded `=cmd` is
        # naturally defanged because the cell starts with `[`.
        self.assertIn("[=cmd](https://example.com)", out)
        # No bare `'=cmd` (the embedded text was not re-quoted).
        self.assertNotIn("'=cmd", out)

    def test_R4_dde_payload_e2e(self) -> None:
        """End-to-end: a literal `=cmd|'/C calc'!A1` DDE payload is
        defanged under `--escape-formulas quote`. Reopening the CSV
        in LibreOffice Calc renders the cell as text, not as a
        formula (manually verified; pinned by the leading-quote
        presence in this test).
        """
        out = self._emit_single_csv_capturing("=cmd|'/C calc'!A1", "quote")
        # Defanged form has leading `'`. CSV-quoting wraps the field
        # in `"..."` because it contains `"` characters from the
        # embedded `'/C calc'`. Check both possible serialisations:
        # (a) literal `'=cmd|...` somewhere in the row;
        # (b) inside a `"..."` quoted field, the leading `'` precedes
        # the `=`.
        self.assertTrue(
            "'=cmd|" in out,
            f"Expected leading-quote defang in output: {out!r}",
        )

    def test_R1_collision_suffix_999_succeeds(self) -> None:
        """xlsx-8a-01 (R1): 999 colliding payloads (one below the cap)
        write 999 files with suffixes ``__2 .. __999`` plus the
        un-suffixed first occurrence; no raise.
        """
        from xlsx2csv2json.emit_csv import emit_csv
        payloads = []
        for _ in range(999):
            r, t = _td(["a"], [[1]], sheet="S", region_name="Table",
                       source="listobject")
            payloads.append(("S", r, t, None))
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            rc = emit_csv(
                iter(payloads),
                output=None, output_dir=out_dir,
                sheet_selector="S", tables_mode="listobjects",
                include_hyperlinks=False, datetime_format="ISO",
            )
            self.assertEqual(rc, 0)
            # 1 un-suffixed + (999 - 1 = 998) suffixed = 999 files.
            written = sorted((out_dir / "S").glob("*.csv"))
            self.assertEqual(len(written), 999)
            # Last suffixed file is ``Table__999.csv``.
            self.assertTrue((out_dir / "S" / "Table__999.csv").is_file())


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

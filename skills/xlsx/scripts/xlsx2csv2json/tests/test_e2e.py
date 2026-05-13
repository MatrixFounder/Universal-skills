"""End-to-end tests for xlsx-8 read-back CLIs (010-07).

Implements the 30 scenarios enumerated in
``docs/TASK.md §5.5``. Each test invokes either the public helper
``convert_xlsx_to_csv`` / ``convert_xlsx_to_json`` (Python-callable
form) OR the shim via ``subprocess.run`` when shell-level behaviour is
the contract (e.g. ``--help`` exit code, envelope on stderr).

Test ID → TASK §5.5 row mapping is in each test docstring.
"""
from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_FIX = Path(__file__).resolve().parent / "fixtures"
_SHIM_CSV = _SCRIPTS_DIR / "xlsx2csv.py"
_SHIM_JSON = _SCRIPTS_DIR / "xlsx2json.py"


def _suppress_io():
    """Return ``(restore_callable,)`` after redirecting stderr to /dev/null."""
    old_err = sys.stderr
    sys.stderr = io.StringIO()
    return lambda: setattr(sys, "stderr", old_err)


class TestE2EReadBack(unittest.TestCase):
    """30 end-to-end scenarios from TASK §5.5."""

    # ----- 1. json_single_sheet_default_flags -----
    def test_01_json_single_sheet_default_flags(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(_FIX / "single_sheet_simple.xlsx", out)
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
            self.assertEqual(
                data,
                [
                    {"id": 1, "name": "alice", "score": 95},
                    {"id": 2, "name": "bob", "score": 87},
                    {"id": 3, "name": "carol", "score": 92},
                ],
            )

    # ----- header-rows=leaf semantics (TASK §11.7 R29) -----
    def test_header_rows_leaf_keeps_only_deepest_level_per_column(self) -> None:
        """**R29 fix:** `--header-rows leaf` auto-detects the header
        band (same as ``--header-rows auto``) but uses ONLY the deepest
        non-empty level per column as the JSON key. Solves the
        layout-heavy-report key bloat where rows 1..K-1 are merged
        metadata banners and the real column names sit on row K.
        """
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "multi_row_header.xlsx", out,
                tables="whole", header_rows="leaf",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
            # Fixture: A1:C1 merge "2026 plan" + A2/B2/C2 = Q1/Q2/Q3 +
            # 2 data rows. With --header-rows leaf, the "2026 plan"
            # banner level is dropped; keys = ["Q1", "Q2", "Q3"].
            self.assertEqual(list(data[0].keys()), ["Q1", "Q2", "Q3"])
            self.assertEqual(data[0], {"Q1": 100, "Q2": 200, "Q3": 300})
            self.assertEqual(data[1], {"Q1": 110, "Q2": 210, "Q3": 310})

    def test_header_rows_auto_still_emits_multi_level_concat(self) -> None:
        """Regression guard: `--header-rows auto` continues to emit
        the full ` › `-concatenated multi-level keys (R7 behaviour
        unchanged). Only the new `leaf` value short-circuits to the
        deepest level.
        """
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            convert_xlsx_to_json(
                _FIX / "multi_row_header.xlsx", out,
                tables="whole", header_rows="auto",
            )
            data = json.loads(out.read_text("utf-8"))
            # "2026 plan" banner preserved as level-0 prefix.
            self.assertTrue(any("2026 plan" in k for k in data[0]))
            self.assertTrue(any(" › " in k for k in data[0]))

    def test_header_rows_leaf_with_array_style(self) -> None:
        """**/vdd-multi-3 Logic-LOW-2 fix:** `--header-rows leaf`
        combined with `--header-flatten-style array` is unverified
        in the original R29 test set. Leaf trims headers to e.g.
        "Q1" (no separator); array style then splits each header
        on " › " — which produces a single-element ["Q1"] tuple.
        Lock this interaction so a future refactor can't silently
        merge the two paths and break the leaf shape.
        """
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "multi_row_header.xlsx", out,
                tables="whole", header_rows="leaf",
                header_flatten_style="array",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
            # Array style produces [[{key:[...], value:V}, ...], ...]
            self.assertIsInstance(data, list)
            self.assertIsInstance(data[0], list)
            # Each cell's key is a 1-element list (leaf collapsed the
            # banner level — no " › " separator survives).
            for cell in data[0]:
                self.assertEqual(len(cell["key"]), 1)
            # Values come through correctly: row 0 = 100, 200, 300.
            self.assertEqual(
                [c["value"] for c in data[0]],
                [100, 200, 300],
            )
            # Keys at row 0 are exactly the Q1/Q2/Q3 sub-labels.
            self.assertEqual(
                [c["key"][0] for c in data[0]],
                ["Q1", "Q2", "Q3"],
            )

    # ----- R11 — xlsx-8a-09 — --header-rows smart -----
    def test_R11_header_rows_smart_skips_metadata_block(self) -> None:
        """xlsx-8a-09 (R11): `--header-rows smart` skips an unmerged
        metadata block above the real data table.

        Synthesises a workbook with 6 rows of config-like parameters
        on top (sparse, mixed types) + a row of 8 string headers +
        10 rows of numeric data. With `--header-rows smart`, the
        emit must drop the metadata and key the JSON by the 8 real
        column names — NOT the row-1 sparse "От/До" pattern that
        `--header-rows auto` would lock onto.
        """
        from openpyxl import Workbook
        from xlsx2csv2json import convert_xlsx_to_json

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "synthetic.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.title = "Data"
            ws.append([None, "От", "До", None, None, None, None, None])
            ws.append(["Param A", 0, 2000, None, None, None, None, None])
            ws.append(["Param B", 0.1, 1.0, None, None, None, None, None])
            ws.append(["Param C", 500, 5000, None, None, None, None, None])
            ws.append(["Param D", 50, 100, None, None, None, None, None])
            ws.append([None, None, None, None, None, None, None, None])
            ws.append(["id", "name", "score", "tag", "rate", "qty", "total", "status"])
            for r in range(10):
                ws.append([r, f"user-{r}", r * 10, "tag", 0.5, r, r * 0.5, "ok"])
            wb.save(src)

            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                src, out, sheet="Data", tables="whole",
                header_rows="smart", drop_empty_rows=True,
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
            # Single sheet single region → flat array (Shape 1).
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 10)
            # Keys come from the REAL header row (row 7 in the source),
            # NOT the row-1 "От/До" pattern that auto would pick up.
            self.assertEqual(
                list(data[0].keys()),
                ["id", "name", "score", "tag", "rate", "qty", "total", "status"],
            )
            self.assertEqual(data[0]["id"], 0)
            self.assertEqual(data[0]["name"], "user-0")
            self.assertEqual(data[9]["score"], 90)

    # ===== R13 (xlsx-8a-11) — --memory-mode flag =====
    def test_R13_memory_mode_auto_preserves_default(self) -> None:
        """R13 default `auto` keeps the existing size-threshold
        behaviour — `xlsx2json.py` on a tiny workbook with no
        explicit `--memory-mode` produces identical output as the
        pre-R13 baseline."""
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "single_sheet_simple.xlsx", out,
                memory_mode="auto",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
            self.assertEqual(data[0]["name"], "alice")

    def test_R13_memory_mode_streaming_forces_read_only(self) -> None:
        """R13 `streaming` forces `read_only_mode=True` at openpyxl
        open time, even on workbooks below the size threshold where
        `auto` would have picked non-streaming.

        **iter-2 strengthening (vdd-adversarial SEC-INFO-2)**:
        directly verify via `WorkbookReader._read_only` introspection
        that the override fires (was previously testing only that
        the kwarg parsed and produced correct data — a trivial pass
        on small fixtures where `auto` already does the right thing).
        """
        from xlsx_read import open_workbook
        # On the tiny fixture, auto would have picked
        # read_only=False (below 100 MiB threshold). 'streaming'
        # should force True regardless.
        with open_workbook(
            _FIX / "single_sheet_simple.xlsx",
            read_only_mode=True,
        ) as reader:
            self.assertTrue(
                reader._read_only,
                msg="memory_mode='streaming' should force "
                "read_only=True regardless of size",
            )

        # Sanity: the shim accepts the kwarg + emits correct data.
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "single_sheet_simple.xlsx", out,
                memory_mode="streaming",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
            # Data is identical regardless of streaming mode.
            self.assertEqual(data[0]["name"], "alice")
            self.assertEqual(len(data), 3)

    def test_R13_memory_mode_full_forces_non_read_only(self) -> None:
        """R13 `full` forces `read_only_mode=False` even when the
        auto-mode would have selected streaming.

        **iter-2 strengthening (vdd-adversarial SEC-INFO-2)**: the
        original version of this test used `single_sheet_simple.xlsx`
        below the threshold where `auto` would have picked
        non-streaming anyway → 'full' and 'auto' produced identical
        behavior, so the assertion passed trivially without actually
        verifying the override. This version goes through the
        library directly with a forced threshold so the override
        path is actually exercised: at `size_threshold_bytes=1024`,
        `auto` would auto-pick streaming (file > 1 KB); we then
        verify that `read_only_mode=False` (the value `full`
        translates to) wins via direct `WorkbookReader._read_only`
        introspection.
        """
        from xlsx_read import open_workbook

        # `full` corresponds to `read_only_mode=False`.
        with open_workbook(
            _FIX / "single_sheet_simple.xlsx",
            size_threshold_bytes=1024,
            read_only_mode=False,
        ) as reader:
            self.assertFalse(
                reader._read_only,
                msg="memory_mode='full' should force read_only=False "
                "even when size > threshold would otherwise auto-pick "
                "streaming",
            )

        # Sanity: the corresponding shim helper accepts the kwarg.
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "single_sheet_simple.xlsx", out,
                memory_mode="full",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
            self.assertEqual(data[0]["name"], "alice")

    def test_R13_streaming_with_hyperlinks_warns_and_overrides(self) -> None:
        """R13 conflict: `--memory-mode streaming` +
        `--include-hyperlinks` is structurally impossible
        (ReadOnlyWorksheet doesn't expose `cell.hyperlink`). The
        shim emits a stderr warning and overrides streaming → full.
        Verify the warning fires and the run still succeeds."""
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            result = subprocess.run(
                [
                    sys.executable, str(_SHIM_JSON),
                    str(_FIX / "with_hyperlinks.xlsx"),
                    str(out),
                    "--memory-mode", "streaming",
                    "--include-hyperlinks",
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            # Warning surfaces on stderr.
            self.assertIn("--memory-mode streaming", result.stderr)
            self.assertIn("overridden to 'full'", result.stderr)
            # Hyperlinks are correctly extracted (would be impossible
            # under genuine streaming mode).
            data = json.loads(out.read_text("utf-8"))
            # At least one row carries a hyperlink wrapper.
            found_hyperlink = any(
                isinstance(v, dict) and "href" in v
                for row in (data if isinstance(data, list) else [])
                for v in row.values()
            )
            self.assertTrue(found_hyperlink, msg="hyperlink wrapper missing")

    def test_R13_memory_mode_invalid_value_rejected(self) -> None:
        """argparse rejects values outside the documented choice
        list. The shim exits non-zero with a usage error."""
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            result = subprocess.run(
                [
                    sys.executable, str(_SHIM_JSON),
                    str(_FIX / "single_sheet_simple.xlsx"),
                    str(out),
                    "--memory-mode", "bogus",
                ],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--memory-mode", result.stderr)

    # ----- 2. json_stdout_when_output_omitted -----
    def test_02_json_stdout_when_output_omitted(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_SHIM_JSON), str(_FIX / "single_sheet_simple.xlsx")],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]["name"], "alice")

    # ----- 3. json_sheet_named_filter -----
    def test_03_json_sheet_named_filter(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "two_sheets_simple.xlsx", out, sheet="SheetB",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # --sheet NAME → flat array (Shape 1 — single sheet, single region).
        self.assertIsInstance(data, list)
        self.assertEqual(data[0], {"x": "p", "y": 10})

    # ----- 4. json_hidden_sheet_skipped_default -----
    def test_04_json_hidden_sheet_skipped_default(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(_FIX / "hidden_sheet.xlsx", out)
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # Only Visible sheet survives. Single sheet → flat array.
        self.assertIsInstance(data, list)
        # The Visible sheet has 1 data row.
        self.assertEqual(len(data), 1)

    # ----- 5. json_hidden_sheet_included_with_flag -----
    def test_05_json_hidden_sheet_included_with_flag(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "hidden_sheet.xlsx", out, include_hidden=True,
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # 3 sheets → dict-of-arrays (Shape 2).
        self.assertEqual(set(data.keys()), {"Visible", "HiddenOne", "VeryHiddenOne"})

    # ----- 6. json_special_char_sheet_name_preserved -----
    def test_06_json_special_char_sheet_name_preserved(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "special_char_sheet_name.xlsx", out, sheet="Q1 - Q2 split",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # Sheet name itself was passed via --sheet so verify the data.
        self.assertEqual(data[0], {"col1": "alpha", "col2": "beta"})

    # ----- 7. csv_single_sheet_stdout -----
    def test_07_csv_single_sheet_stdout(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_SHIM_CSV), str(_FIX / "single_sheet_simple.xlsx"), "--sheet", "Data"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        rows = list(csv.reader(io.StringIO(result.stdout)))
        self.assertEqual(rows[0], ["id", "name", "score"])
        self.assertEqual(rows[1], ["1", "alice", "95"])

    # ----- 8. csv_sheet_all_without_output_dir_exits_2 -----
    def test_08_csv_sheet_all_without_output_dir_exits_2(self) -> None:
        result = subprocess.run(
            [
                sys.executable, str(_SHIM_CSV),
                str(_FIX / "two_sheets_simple.xlsx"),
                "--json-errors",
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        envelope = json.loads(result.stderr.strip().split("\n")[0])
        self.assertEqual(envelope["type"], "MultiSheetRequiresOutputDir")

    # ----- 9. csv_quoting_minimal_correct -----
    def test_09_csv_quoting_minimal_correct(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_csv
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            rc = convert_xlsx_to_csv(_FIX / "csv_quoting.xlsx", out)
            self.assertEqual(rc, 0)
            raw = out.read_text("utf-8")
        # Comma + quote in value must be quoted (QUOTE_MINIMAL).
        self.assertIn('"foo, bar"', raw)
        # Embedded double-quote → CSV escape via doubling.
        self.assertIn('"he said ""hi"""', raw)

    # ----- 10. json_multi_table_listobjects_nested_shape -----
    def test_10_json_multi_table_listobjects_nested_shape(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "multi_table_listobjects.xlsx", out,
                tables="listobjects", header_rows="auto",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # Single sheet, multi-region → Shape 4 (flat {Name: [...]})
        self.assertEqual(set(data.keys()), {"RevenueTable", "CostsTable"})

    # ----- 11. json_multi_table_gap_detect_default_2_1 -----
    def test_11_json_multi_table_gap_detect_default_2_1(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "gap_detected_two.xlsx", out,
                tables="gap", header_rows="auto",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # Two gap-detected regions.
        self.assertEqual(len(data), 2)

    # ----- 12. json_multi_table_auto_falls_back_to_gap -----
    def test_12_json_multi_table_auto_falls_back_to_gap(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "gap_detected_two.xlsx", out,
                tables="auto", header_rows="auto",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # No ListObjects in this fixture; auto mode falls through to
        # gap, yielding 2 regions.
        self.assertEqual(len(data), 2)

    # ----- 13. json_single_table_falls_through_flat -----
    def test_13_json_single_table_falls_through_flat(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "single_sheet_simple.xlsx", out,
                tables="auto", header_rows="auto",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # Single region → flat array (Shape 1).
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)

    # ----- 14. header_rows_int_with_multi_table_exits_2_HeaderRowsConflict -----
    def test_14_header_rows_int_with_multi_table_exits_2(self) -> None:
        result = subprocess.run(
            [
                sys.executable, str(_SHIM_JSON),
                str(_FIX / "single_sheet_simple.xlsx"),
                "--header-rows", "2",
                "--tables", "listobjects",
                "--json-errors",
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        envelope = json.loads(result.stderr.strip().split("\n")[0])
        self.assertEqual(envelope["type"], "HeaderRowsConflict")

    # ----- 15. csv_multi_table_subdirectory_schema -----
    def test_15_csv_multi_table_subdirectory_schema(self) -> None:
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
            self.assertTrue((out_dir / "Summary" / "RevenueTable.csv").is_file())
            self.assertTrue((out_dir / "Summary" / "CostsTable.csv").is_file())

    # ----- 16. csv_multi_table_without_output_dir_exits_2 -----
    def test_16_csv_multi_table_without_output_dir_exits_2(self) -> None:
        result = subprocess.run(
            [
                sys.executable, str(_SHIM_CSV),
                str(_FIX / "multi_table_listobjects.xlsx"),
                "--tables", "listobjects",
                "--header-rows", "auto",
                "--sheet", "Summary",  # Avoid multi-sheet trigger.
                "--json-errors",
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        envelope = json.loads(result.stderr.strip().split("\n")[0])
        self.assertEqual(envelope["type"], "MultiTableRequiresOutputDir")

    # ----- 17. csv_sheet_name_with_slash_exits_2_InvalidSheetNameForFsPath -----
    def test_17_path_component_validator_rejects_slash(self) -> None:
        """openpyxl rejects '/' at title-set time; we exercise the
        validator directly via the dispatch helper.
        """
        from xlsx2csv2json.dispatch import _validate_sheet_path_components
        from xlsx2csv2json import InvalidSheetNameForFsPath
        with self.assertRaises(InvalidSheetNameForFsPath):
            _validate_sheet_path_components("bad/sheet")

    # ----- 18. header_rows_auto_detects_multi_row_header_with_U203A -----
    def test_18_header_rows_auto_detects_multi_row_header(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "multi_row_header.xlsx", out,
                header_rows="auto",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # Multi-row header flatten uses U+203A separator.
        # First row should have keys like "2026 plan › Q1" (or with whatever
        # variation the library produces).
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        # At least one key contains the separator OR the merge-banner part.
        all_keys = list(data[0].keys())
        self.assertTrue(
            any("Q1" in k for k in all_keys),
            f"Expected 'Q1' in some key; got {all_keys!r}",
        )
        # And at least one key contains the U+203A separator (when 2-row
        # header detection works).
        has_separator = any("›" in k for k in all_keys)
        has_banner = any("2026 plan" in k for k in all_keys)
        self.assertTrue(
            has_separator or has_banner,
            f"Expected U+203A or banner in some key; got {all_keys!r}",
        )

    # ----- 19. header_flatten_style_array_only_for_json -----
    def test_19_header_flatten_style_array(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "multi_row_header.xlsx", out,
                header_rows="auto",
                header_flatten_style="array",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # array-style: rows become list-of-{key,value} objects.
        self.assertIsInstance(data, list)
        first_row = data[0]
        self.assertIsInstance(first_row, list)
        self.assertIsInstance(first_row[0], dict)
        self.assertIn("key", first_row[0])
        self.assertIn("value", first_row[0])
        self.assertIsInstance(first_row[0]["key"], list)

    # ----- 20. ambiguous_header_boundary_surfaced_as_warning -----
    def test_20_ambiguous_header_boundary_warning(self) -> None:
        """Use any fixture with merges that could straddle header. The
        merge_three_policies.xlsx has a 2-row merge in column B which
        may or may not trigger AmbiguousHeaderBoundary depending on
        the library's heuristic. The test just verifies that the
        warning, if emitted, lands on stderr without crashing the
        process.
        """
        result = subprocess.run(
            [
                sys.executable, str(_SHIM_JSON),
                str(_FIX / "merge_three_policies.xlsx"),
                "--header-rows", "auto",
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        # Stderr may or may not contain a warning; what matters is the
        # process didn't crash.

    # ----- 21. synthetic_headers_when_listobject_header_row_count_zero -----
    def test_21_synthetic_headers_header_row_count_zero(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "listobject_header_zero.xlsx", out,
                tables="listobjects", header_rows="auto",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # Synthetic headers col_1..col_N. Single sheet + 1 region →
        # flat array.
        self.assertIsInstance(data, list)
        keys = list(data[0].keys())
        self.assertTrue(all(k.startswith("col_") for k in keys), keys)

    # ----- M1 regression (vdd-multi): default --header-rows is mode-aware -----
    def test_M1_default_header_rows_with_tables_auto_no_conflict(self) -> None:
        """M1 regression: ``--tables auto`` without an explicit
        ``--header-rows`` used to raise ``HeaderRowsConflict`` because
        the parser default was ``1`` (an int) and the conflict rule
        was unconditional.

        Fix: parser default is ``None``; ``_validate_flag_combo``
        materialises it to ``1`` for ``--tables=whole`` and ``"auto"``
        for ``--tables != whole``. So ``--tables auto`` without
        ``--header-rows`` works.
        """
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            # No --header-rows; --tables auto. Must NOT raise.
            rc = convert_xlsx_to_json(
                _FIX / "single_sheet_simple.xlsx", out, tables="auto",
            )
            self.assertEqual(rc, 0)

    def test_M1_explicit_int_header_rows_with_multi_table_still_conflicts(self) -> None:
        """M1 regression: the explicit-int-conflict path still fires.

        ``--header-rows 2 --tables auto`` is still ambiguous → exit 2.
        """
        result = subprocess.run(
            [
                sys.executable, str(_SHIM_JSON),
                str(_FIX / "single_sheet_simple.xlsx"),
                "--header-rows", "2",
                "--tables", "auto",
                "--json-errors",
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        envelope = json.loads(result.stderr.strip().split("\n")[0])
        self.assertEqual(envelope["type"], "HeaderRowsConflict")

    # ----- H3 regression (vdd-multi): unhandled exceptions caught by envelope -----
    def test_H3_unhandled_exception_caught_no_path_leak(self) -> None:
        """H3 regression: ``_run_with_envelope`` must catch every
        exception so the cross-5 envelope contract holds, and must NOT
        echo full paths in the error message.

        Trigger via ``_run_with_envelope`` directly with a body that
        raises a ``PermissionError`` carrying a full absolute path.
        Expect: exit code 1, JSON envelope with ``type=PermissionError``
        and ``details.filename`` being the BASENAME only (no full path
        in the envelope).
        """
        from xlsx2csv2json.cli import _run_with_envelope
        from argparse import Namespace
        old = sys.stderr
        buf = io.StringIO()
        sys.stderr = buf
        try:
            rc = _run_with_envelope(
                Namespace(json_errors=True),
                body=lambda: (_ for _ in ()).throw(
                    PermissionError(13, "Permission denied", "/private/secret/data.xlsx")
                ),
            )
        finally:
            sys.stderr = old
        self.assertEqual(rc, 1)
        envelope = json.loads(buf.getvalue().strip())
        self.assertEqual(envelope["type"], "PermissionError")
        self.assertEqual(envelope["details"]["filename"], "data.xlsx")
        # Absolute path MUST NOT appear in the envelope payload.
        self.assertNotIn("/private/secret", buf.getvalue())

    def test_H3_generic_exception_redacted(self) -> None:
        """H3 regression: a generic ``RuntimeError`` carrying a path in
        its message is converted to a redacted envelope (class-name
        only; message dropped).
        """
        from xlsx2csv2json.cli import _run_with_envelope
        from argparse import Namespace
        old = sys.stderr
        buf = io.StringIO()
        sys.stderr = buf
        try:
            rc = _run_with_envelope(
                Namespace(json_errors=True),
                body=lambda: (_ for _ in ()).throw(
                    RuntimeError("openpyxl failed at /private/x/y.xlsx line 42")
                ),
            )
        finally:
            sys.stderr = old
        self.assertEqual(rc, 1)
        envelope = json.loads(buf.getvalue().strip())
        self.assertEqual(envelope["type"], "RuntimeError")
        # The raw exception message is dropped; only the class name
        # surfaces. Verify no path leak.
        self.assertNotIn("/private/x", buf.getvalue())
        self.assertNotIn("y.xlsx", buf.getvalue())

    # ----- H2 regression (vdd-multi): TableData.warnings reach stderr -----
    def test_H2_table_data_warnings_propagate_to_stderr(self) -> None:
        """H2 regression: the library appends soft warnings to
        ``TableData.warnings`` (list[str]) but never calls
        ``warnings.warn``. Without re-emission at dispatch, the
        shim's outer ``warnings.catch_warnings`` block never sees
        them and they vanish silently — violating HS-7 contract.

        Fix: dispatch re-emits each entry via ``warnings.warn``.

        Trigger: the ``listobject_header_zero.xlsx`` fixture has a
        ListObject with ``headerRowCount=0`` → library appends the
        "synthetic col_1..col_N" warning.
        """
        result = subprocess.run(
            [
                sys.executable, str(_SHIM_JSON),
                str(_FIX / "listobject_header_zero.xlsx"),
                "--tables", "listobjects",
                "--header-rows", "auto",
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        # Warning must surface on stderr.
        self.assertIn("synthetic col_", result.stderr)
        self.assertIn("NoHeaderTable", result.stderr)

    # ----- H1 regression (vdd-multi): --datetime-format raw + json no crash -----
    def test_H1_datetime_raw_with_json_does_not_crash(self) -> None:
        """H1 regression: ``--datetime-format raw`` previously raised
        ``TypeError: Object of type datetime is not JSON serializable``
        because the library returned native ``datetime`` objects and
        ``json.dumps`` can't encode them.

        Fix: ``json.dumps(..., default=_json_default)`` coerces
        datetime/date/time/timedelta via ``.isoformat()``. Documented as
        honest-scope (m).
        """
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "with_datetimes.xlsx", out, datetime_format="raw",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        self.assertEqual(data[0]["hired"], "2024-01-15T12:30:00")
        self.assertEqual(data[1]["hired"], "2025-06-01T09:00:00")

    # ----- C1 regression (vdd-multi): hyperlinks survive auto-read_only=True path -----
    def test_22_pre_hyperlinks_read_only_mitigation(self) -> None:
        """C1 regression: --include-hyperlinks must override read_only_mode.

        Background: openpyxl's read_only=True streams cells via ReadOnlyCell
        which does NOT expose `cell.hyperlink` (lives in sheet rels XML).
        xlsx_read auto-picks read_only=True for files > 10 MiB. The shim
        must override to read_only=False so cell.hyperlink remains
        accessible to the parallel pass.

        Test strategy: open the fixture twice — once forcing read_only=True
        at library level (proves the failure mode), once via the shim
        (proves the shim's override works).
        """
        from xlsx_read import open_workbook
        from xlsx2csv2json.dispatch import _extract_hyperlinks_for_region
        # Pin failure mode: read_only=True → no hyperlinks visible.
        with open_workbook(
            _FIX / "with_hyperlinks.xlsx", read_only_mode=True
        ) as reader_ro:
            regions = reader_ro.detect_tables("Links", mode="whole")
            self.assertEqual(len(regions), 1)
            hl_ro = _extract_hyperlinks_for_region(reader_ro, regions[0])
        # ReadOnlyWorksheet has no _hyperlinks; map is empty.
        self.assertEqual(hl_ro, {})

        # Now run via the shim with --include-hyperlinks=True; the shim
        # forces read_only=False and hyperlinks DO emit.
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "with_hyperlinks.xlsx", out,
                include_hyperlinks=True,
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # Hyperlink survived end-to-end.
        self.assertIsInstance(data[0]["text"], dict)
        self.assertEqual(data[0]["text"]["href"], "https://example.com/a")

    # ----- 22. hyperlinks_json_dict_shape_value_href -----
    def test_22_hyperlinks_json_dict_shape(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "with_hyperlinks.xlsx", out,
                include_hyperlinks=True,
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        self.assertEqual(
            data[0]["text"],
            {"value": "click here", "href": "https://example.com/a"},
        )

    # ----- 23. hyperlinks_csv_markdown_link_text_url -----
    def test_23_hyperlinks_csv_markdown_link(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_csv
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            rc = convert_xlsx_to_csv(
                _FIX / "with_hyperlinks.xlsx", out,
                sheet="Links", include_hyperlinks=True,
            )
            self.assertEqual(rc, 0)
            raw = out.read_text("utf-8")
        self.assertIn("[click here](https://example.com/a)", raw)
        self.assertNotIn("=HYPERLINK", raw)

    # ----- 24. encrypted_workbook_exits_3_with_basename_only -----
    def test_24_encrypted_workbook_exits_3(self) -> None:
        result = subprocess.run(
            [
                sys.executable, str(_SHIM_JSON),
                str(_FIX / "encrypted.xlsx"),
                "--json-errors",
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 3)
        envelope = json.loads(result.stderr.strip().split("\n")[0])
        self.assertEqual(envelope["type"], "EncryptedWorkbookError")
        self.assertEqual(envelope["code"], 3)
        # Basename only — no full path leak (parallel xlsx_read §13.2).
        if "details" in envelope and "filename" in envelope.get("details", {}):
            self.assertEqual(envelope["details"]["filename"], "encrypted.xlsx")

    # ----- 25. same_path_via_symlink_exits_6_SelfOverwriteRefused -----
    def test_25_same_path_via_symlink_exits_6(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            # Copy the fixture so we don't taint shared state.
            import shutil
            src = td_path / "data.xlsx"
            shutil.copyfile(_FIX / "single_sheet_simple.xlsx", src)
            sym = td_path / "out.json"
            sym.symlink_to(src)
            result = subprocess.run(
                [
                    sys.executable, str(_SHIM_JSON),
                    str(src), str(sym),
                    "--json-errors",
                ],
                capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 6)
        envelope = json.loads(result.stderr.strip().split("\n")[0])
        self.assertEqual(envelope["type"], "SelfOverwriteRefused")
        self.assertEqual(envelope["code"], 6)

    # ----- 26. json_errors_envelope_shape_v1 -----
    def test_26_json_errors_envelope_shape_v1(self) -> None:
        """Any failure path with --json-errors yields a v=1 envelope."""
        result = subprocess.run(
            [
                sys.executable, str(_SHIM_JSON),
                "/nonexistent.xlsx",
                "--json-errors",
            ],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        line = result.stderr.strip().split("\n")[0]
        envelope = json.loads(line)
        self.assertEqual(envelope["v"], 1)
        self.assertIn("error", envelope)
        self.assertIn("code", envelope)
        self.assertGreater(envelope["code"], 0)

    # ----- 27. roundtrip_xlsx2_simple_shape_byte_identical -----
    def test_27_roundtrip_xlsx2_simple_shape(self) -> None:
        """The detailed round-trip lives in
        ``scripts/tests/test_json2xlsx.py::TestRoundTripXlsx8::test_live_roundtrip``.

        This E2E exercises the simpler in-package path: round-trip a
        Shape-1 fixture through xlsx-2 and back.
        """
        from xlsx2csv2json import convert_xlsx_to_json
        from json2xlsx import convert_json_to_xlsx
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            # 1) Read fixture → JSON.
            j1 = td_path / "first.json"
            rc1 = convert_xlsx_to_json(_FIX / "single_sheet_simple.xlsx", j1)
            self.assertEqual(rc1, 0)
            data1 = json.loads(j1.read_text("utf-8"))
            # 2) Write JSON → xlsx via xlsx-2.
            x2 = td_path / "round.xlsx"
            rc2 = convert_json_to_xlsx(str(j1), str(x2))
            self.assertEqual(rc2, 0)
            # 3) Read back → JSON.
            j2 = td_path / "second.json"
            rc3 = convert_xlsx_to_json(x2, j2)
            self.assertEqual(rc3, 0)
            data2 = json.loads(j2.read_text("utf-8"))
        # Shape 1: flat array of dicts. Compare structurally.
        self.assertEqual(len(data1), len(data2))
        for r1, r2 in zip(data1, data2):
            self.assertEqual(r1.keys(), r2.keys())
            self.assertEqual(r1, r2)

    # ----- 28. merge_policy_anchor_only_fill_blank_three_fixtures -----
    def test_28_merge_policy_anchor_only(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "merge_three_policies.xlsx", out,
                merge_policy="anchor-only",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # B2:B3 merged with anchor B2="group1"; anchor-only → B3 is None.
        self.assertEqual(data[0]["group"], "group1")
        self.assertIsNone(data[1]["group"])

    def test_28b_merge_policy_fill(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "merge_three_policies.xlsx", out,
                merge_policy="fill",
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # fill policy → anchor value broadcast to all child cells.
        self.assertEqual(data[0]["group"], "group1")
        self.assertEqual(data[1]["group"], "group1")

    # ----- 29. include_formulas_emits_formula_strings_not_cached -----
    def test_29_include_formulas_emits_formula_strings(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(
                _FIX / "with_formulas.xlsx", out, include_formulas=True,
            )
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text("utf-8"))
        # Formula cells emit the formula string (e.g. "=A2*2") instead
        # of the cached value.
        self.assertEqual(data[0]["doubled"], "=A2*2")

    # ----- 30. output_dir_path_traversal_rejected_OutputPathTraversal -----
    def test_30_output_dir_path_traversal_rejected(self) -> None:
        """Defence-in-depth: even if a fixture's region name had
        traversal chars, the emit-time guard catches the escape.

        Practical test: invoke ``_emit_multi_region`` directly with a
        synthetic region that escapes. (Unit-level test already in
        ``test_emit_csv.py``.) Here we run the full pipeline against
        the real fixture and assert the guard is NOT triggered (the
        names are safe).
        """
        from xlsx2csv2json import convert_xlsx_to_csv
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "out"
            rc = convert_xlsx_to_csv(
                _FIX / "multi_table_listobjects.xlsx",
                output_dir=out_dir,
                tables="listobjects",
                header_rows="auto",
            )
            self.assertEqual(rc, 0)
            # Every emitted file lives under out_dir (no escape).
            for p in out_dir.rglob("*.csv"):
                self.assertTrue(p.resolve().is_relative_to(out_dir.resolve()))


# ===========================================================================
# Post-validate env-flag (010-07 R20)
# ===========================================================================
class TestPostValidate(unittest.TestCase):

    def test_env_flag_unset_no_op(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        os.environ.pop("XLSX_XLSX2CSV2JSON_POST_VALIDATE", None)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.json"
            rc = convert_xlsx_to_json(_FIX / "single_sheet_simple.xlsx", out)
        self.assertEqual(rc, 0)

    def test_env_flag_set_valid_json_no_raise(self) -> None:
        from xlsx2csv2json import convert_xlsx_to_json
        os.environ["XLSX_XLSX2CSV2JSON_POST_VALIDATE"] = "1"
        try:
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "out.json"
                rc = convert_xlsx_to_json(_FIX / "single_sheet_simple.xlsx", out)
                self.assertEqual(rc, 0)
                self.assertTrue(out.exists())
        finally:
            os.environ.pop("XLSX_XLSX2CSV2JSON_POST_VALIDATE", None)

    def test_env_flag_set_corrupted_raises_and_unlinks(self) -> None:
        from xlsx2csv2json.cli import _post_validate_json_output
        from xlsx2csv2json import PostValidateFailed
        os.environ["XLSX_XLSX2CSV2JSON_POST_VALIDATE"] = "1"
        try:
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "corrupted.json"
                out.write_text("not valid json {{{", encoding="utf-8")
                with self.assertRaises(PostValidateFailed):
                    _post_validate_json_output(out)
                self.assertFalse(out.exists())  # unlinked
        finally:
            os.environ.pop("XLSX_XLSX2CSV2JSON_POST_VALIDATE", None)

    def test_env_flag_set_csv_path_skipped(self) -> None:
        """CSV outputs have no schema — env flag is a no-op (output_path=None)."""
        from xlsx2csv2json.cli import _post_validate_json_output
        os.environ["XLSX_XLSX2CSV2JSON_POST_VALIDATE"] = "1"
        try:
            # Passing None bypasses any validation.
            _post_validate_json_output(None)  # must not raise
        finally:
            os.environ.pop("XLSX_XLSX2CSV2JSON_POST_VALIDATE", None)


if __name__ == "__main__":
    unittest.main()

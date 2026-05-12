"""Unit tests for :mod:`xlsx2csv2json.cli` (010-03).

Covers the full argparse surface, format-lock guard, cross-flag
validation, output-arg reconciliation, and the public-helper kwarg
marshaller.
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def _capture_stderr() -> tuple[io.StringIO, callable]:
    """Return ``(buf, restore)``. Use restore() in addCleanup."""
    buf = io.StringIO()
    old = sys.stderr
    sys.stderr = buf

    def restore() -> None:
        sys.stderr = old
    return buf, restore


def _make_workbook(td: Path, with_two_sheets: bool = False) -> Path:
    """Tiny .xlsx for tests that need a real input file."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = "id"
    ws["B1"] = "name"
    ws["A2"] = 1
    ws["B2"] = "alice"
    if with_two_sheets:
        ws2 = wb.create_sheet("Sheet2")
        ws2["A1"] = "x"
        ws2["A2"] = 99
    out = td / "in.xlsx"
    wb.save(out)
    return out


# ===========================================================================
# build_parser — flag table coverage + format-lock behaviour
# ===========================================================================
class TestBuildParser(unittest.TestCase):

    def test_defaults_locked(self) -> None:
        from xlsx2csv2json.cli import build_parser
        parser = build_parser(format_lock="csv")
        args = parser.parse_args(["fake.xlsx"])
        self.assertEqual(args.sheet, "all")
        self.assertFalse(args.include_hidden)
        # M1 (vdd-multi): parser-level default is None (mode-aware
        # materialisation happens in _validate_flag_combo).
        self.assertIsNone(args.header_rows)
        self.assertEqual(args.header_flatten_style, "string")
        self.assertEqual(args.merge_policy, "anchor-only")
        self.assertEqual(args.tables, "whole")
        self.assertEqual(args.gap_rows, 2)
        self.assertEqual(args.gap_cols, 1)
        self.assertFalse(args.include_hyperlinks)
        self.assertFalse(args.include_formulas)
        self.assertEqual(args.datetime_format, "ISO")
        self.assertFalse(args.json_errors)

    def test_format_lock_csv_rejects_json(self) -> None:
        from xlsx2csv2json.cli import build_parser
        from xlsx2csv2json import FormatLockedByShim
        parser = build_parser(format_lock="csv")
        with self.assertRaises(FormatLockedByShim):
            parser.parse_args(["fake.xlsx", "--format", "json"])

    def test_format_lock_json_rejects_csv(self) -> None:
        from xlsx2csv2json.cli import build_parser
        from xlsx2csv2json import FormatLockedByShim
        parser = build_parser(format_lock="json")
        with self.assertRaises(FormatLockedByShim):
            parser.parse_args(["fake.xlsx", "--format", "csv"])

    def test_format_lock_csv_accepts_csv(self) -> None:
        from xlsx2csv2json.cli import build_parser
        parser = build_parser(format_lock="csv")
        args = parser.parse_args(["fake.xlsx", "--format", "csv"])
        self.assertEqual(args.format, "csv")

    def test_no_format_lock_requires_format(self) -> None:
        from xlsx2csv2json.cli import build_parser
        parser = build_parser(format_lock=None)
        args = parser.parse_args(["fake.xlsx", "--format", "csv"])
        self.assertEqual(args.format, "csv")

    def test_header_rows_type_auto(self) -> None:
        from xlsx2csv2json.cli import build_parser
        parser = build_parser(format_lock="csv")
        args = parser.parse_args(["fake.xlsx", "--header-rows", "auto"])
        self.assertEqual(args.header_rows, "auto")

    def test_header_rows_type_int(self) -> None:
        from xlsx2csv2json.cli import build_parser
        parser = build_parser(format_lock="csv")
        args = parser.parse_args(["fake.xlsx", "--header-rows", "2"])
        self.assertEqual(args.header_rows, 2)

    def test_header_rows_rejects_negative(self) -> None:
        from xlsx2csv2json.cli import build_parser
        parser = build_parser(format_lock="csv")
        # argparse converts ArgumentTypeError into SystemExit.
        # Suppress the usage banner argparse emits on stderr.
        old = sys.stderr
        sys.stderr = io.StringIO()
        try:
            with self.assertRaises(SystemExit):
                parser.parse_args(["fake.xlsx", "--header-rows", "-1"])
        finally:
            sys.stderr = old

    def test_header_rows_rejects_garbage(self) -> None:
        from xlsx2csv2json.cli import build_parser
        parser = build_parser(format_lock="csv")
        old = sys.stderr
        sys.stderr = io.StringIO()
        try:
            with self.assertRaises(SystemExit):
                parser.parse_args(["fake.xlsx", "--header-rows", "not-a-num"])
        finally:
            sys.stderr = old


# ===========================================================================
# _validate_flag_combo — cross-flag invariants
# ===========================================================================
class TestValidateFlagCombo(unittest.TestCase):

    def _parse(self, format_lock: str | None, argv: list[str]) -> argparse.Namespace:
        from xlsx2csv2json.cli import build_parser
        return build_parser(format_lock=format_lock).parse_args(argv)

    def test_header_rows_int_with_multi_table_raises(self) -> None:
        from xlsx2csv2json.cli import _validate_flag_combo
        from xlsx2csv2json import HeaderRowsConflict
        args = self._parse(
            "csv",
            ["fake.xlsx", "--header-rows", "2", "--tables", "listobjects"],
        )
        with self.assertRaises(HeaderRowsConflict):
            _validate_flag_combo(args, format_lock="csv")

    def test_header_rows_auto_with_multi_table_ok(self) -> None:
        from xlsx2csv2json.cli import _validate_flag_combo
        args = self._parse(
            "csv",
            ["fake.xlsx", "--header-rows", "auto", "--tables", "listobjects"],
        )
        _validate_flag_combo(args, format_lock="csv")  # no raise

    def test_csv_sheet_all_dash_output_raises(self) -> None:
        from xlsx2csv2json.cli import _validate_flag_combo
        from xlsx2csv2json import MultiSheetRequiresOutputDir
        args = self._parse("csv", ["fake.xlsx", "-"])
        with self.assertRaises(MultiSheetRequiresOutputDir):
            _validate_flag_combo(args, format_lock="csv")

    def test_csv_sheet_all_no_output_no_raise_at_parse_time(self) -> None:
        """Conservative pre-check: with NO output, defer to dispatch."""
        from xlsx2csv2json.cli import _validate_flag_combo
        args = self._parse("csv", ["fake.xlsx"])
        _validate_flag_combo(args, format_lock="csv")  # no raise


# ===========================================================================
# _resolve_output_arg — mutual exclusivity
# ===========================================================================
class TestResolveOutputArg(unittest.TestCase):

    def test_positional_only(self) -> None:
        from xlsx2csv2json.cli import _resolve_output_arg
        ns = argparse.Namespace(output="out.json", output_flag=None)
        self.assertEqual(_resolve_output_arg(ns), "out.json")

    def test_flag_only(self) -> None:
        from xlsx2csv2json.cli import _resolve_output_arg
        ns = argparse.Namespace(output=None, output_flag="out.json")
        self.assertEqual(_resolve_output_arg(ns), "out.json")

    def test_both_raises(self) -> None:
        from xlsx2csv2json.cli import _resolve_output_arg
        from xlsx2csv2json import _AppError
        ns = argparse.Namespace(output="a.json", output_flag="b.json")
        with self.assertRaises(_AppError):
            _resolve_output_arg(ns)

    def test_neither_returns_none(self) -> None:
        from xlsx2csv2json.cli import _resolve_output_arg
        ns = argparse.Namespace(output=None, output_flag=None)
        self.assertIsNone(_resolve_output_arg(ns))


# ===========================================================================
# _build_argv — kwarg → flag marshaller
# ===========================================================================
class TestBuildArgv(unittest.TestCase):

    def test_basic(self) -> None:
        from xlsx2csv2json import _build_argv
        argv = _build_argv("in.xlsx", "out.json", {})
        self.assertEqual(argv, ["in.xlsx", "--output", "out.json"])

    def test_no_output(self) -> None:
        from xlsx2csv2json import _build_argv
        argv = _build_argv("in.xlsx", None, {})
        self.assertEqual(argv, ["in.xlsx"])

    def test_value_kwarg(self) -> None:
        from xlsx2csv2json import _build_argv
        argv = _build_argv("in.xlsx", None, {"sheet": "Sheet1", "tables": "gap"})
        self.assertIn("--sheet", argv)
        self.assertIn("Sheet1", argv)
        self.assertIn("--tables", argv)
        self.assertIn("gap", argv)

    def test_bool_kwarg_true(self) -> None:
        from xlsx2csv2json import _build_argv
        argv = _build_argv("in.xlsx", None, {"include_hyperlinks": True})
        self.assertIn("--include-hyperlinks", argv)

    def test_bool_kwarg_false_dropped(self) -> None:
        from xlsx2csv2json import _build_argv
        argv = _build_argv("in.xlsx", None, {"include_hyperlinks": False})
        self.assertNotIn("--include-hyperlinks", argv)

    def test_unknown_kwarg_raises(self) -> None:
        from xlsx2csv2json import _build_argv
        with self.assertRaises(TypeError):
            _build_argv("in.xlsx", None, {"foo": "bar"})


# ===========================================================================
# main — end-to-end (parse + dispatch trampoline up to emit stub)
# ===========================================================================
class TestMain(unittest.TestCase):

    def test_help_csv_shim_exits_zero(self) -> None:
        """`python3 xlsx2csv.py --help` should exit 0 (subprocess)."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "xlsx2csv.py"), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("INPUT", result.stdout)

    def test_help_json_shim_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "xlsx2json.py"), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("INPUT", result.stdout)

    def test_format_lock_violation_exits_2_envelope(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "xlsx2csv.py"),
                "/nonexistent.xlsx",
                "--format", "json",
                "--json-errors",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        envelope = json.loads(result.stderr.strip().split("\n")[0])
        self.assertEqual(envelope["type"], "FormatLockedByShim")
        self.assertEqual(envelope["code"], 2)

    def test_header_rows_conflict_exits_2_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            inp = _make_workbook(Path(td))
            result = subprocess.run(
                [
                    sys.executable,
                    str(_SCRIPTS_DIR / "xlsx2json.py"),
                    str(inp),
                    "--header-rows", "2",
                    "--tables", "listobjects",
                    "--json-errors",
                ],
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 2)
        envelope = json.loads(result.stderr.strip().split("\n")[0])
        self.assertEqual(envelope["type"], "HeaderRowsConflict")

    def test_main_reaches_emitter_and_writes_json(self) -> None:
        """010-05 wires emit_json — main() now produces real JSON output.

        Prior bump-history: 010-03 sentinel -997; replaced now that
        emit_json is live (returns 0 on success).
        """
        from xlsx2csv2json import main
        with tempfile.TemporaryDirectory() as td:
            inp = _make_workbook(Path(td))
            out = Path(td) / "out.json"
            buf, restore = _capture_stderr()
            self.addCleanup(restore)
            rc = main([str(inp), str(out)], format_lock="json")
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            # Single-sheet single-region: rule 1 → flat array.
            content = out.read_text("utf-8")
            self.assertTrue(content.startswith("["), content[:50])

    def test_main_missing_input_returns_1(self) -> None:
        """FileNotFoundError mapped to exit 1 via envelope."""
        from xlsx2csv2json import main
        buf, restore = _capture_stderr()
        self.addCleanup(restore)
        rc = main(["/nonexistent.xlsx"], format_lock="json")
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()

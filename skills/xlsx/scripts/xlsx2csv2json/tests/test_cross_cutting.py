"""Unit tests for the cross-cutting envelope helpers (010-02).

Covers:

* ``cli._resolve_paths`` — INPUT canonical-resolve, ``--output``
  parent-dir auto-create, cross-7 H1 same-path guard (including
  symlink-follow).
* ``cli._run_with_envelope`` — exception → ``_errors.report_error``
  dispatch table with basename-only ``details.filename``.
* ``cli._emit_warnings_to_stderr`` — re-emit via
  :func:`warnings.showwarning` (NOT a JSON envelope, per ARCH HS-7).
* ``dispatch._validate_sheet_path_components`` — cross-platform
  reject list.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


# ===========================================================================
# Helpers
# ===========================================================================
def _make_args(json_errors: bool = False) -> argparse.Namespace:
    """Minimal Namespace stand-in for cli._run_with_envelope tests."""
    return argparse.Namespace(json_errors=json_errors)


def _make_workbook(td: Path) -> Path:
    """Create a minimal valid .xlsx in ``td`` via openpyxl."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "hello"
    out = td / "input.xlsx"
    wb.save(out)
    return out


# ===========================================================================
# _resolve_paths
# ===========================================================================
class TestResolvePaths(unittest.TestCase):

    def test_resolve_paths_happy(self) -> None:
        from xlsx2csv2json.cli import _resolve_paths
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            inp = _make_workbook(td_path)
            ri, ro, rd = _resolve_paths(str(inp), None, None)
            self.assertEqual(ri, inp.resolve())
            self.assertIsNone(ro)
            self.assertIsNone(rd)

    def test_resolve_paths_self_overwrite(self) -> None:
        from xlsx2csv2json.cli import _resolve_paths
        from xlsx2csv2json import SelfOverwriteRefused
        with tempfile.TemporaryDirectory() as td:
            inp = _make_workbook(Path(td))
            with self.assertRaises(SelfOverwriteRefused):
                _resolve_paths(str(inp), str(inp), None)

    def test_resolve_paths_via_symlink(self) -> None:
        from xlsx2csv2json.cli import _resolve_paths
        from xlsx2csv2json import SelfOverwriteRefused
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            inp = _make_workbook(td_path)
            sym = td_path / "out.json"
            sym.symlink_to(inp)
            with self.assertRaises(SelfOverwriteRefused):
                _resolve_paths(str(inp), str(sym), None)

    def test_resolve_paths_parent_dir_auto_create(self) -> None:
        from xlsx2csv2json.cli import _resolve_paths
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            inp = _make_workbook(td_path)
            out = td_path / "sub" / "dir" / "out.json"
            self.assertFalse(out.parent.exists())
            ri, ro, _ = _resolve_paths(str(inp), str(out), None)
            self.assertTrue(out.parent.exists())
            self.assertEqual(ro, out.resolve())

    def test_resolve_paths_input_not_found(self) -> None:
        from xlsx2csv2json.cli import _resolve_paths
        with self.assertRaises(FileNotFoundError):
            _resolve_paths("/nonexistent-input.xlsx", None, None)

    def test_resolve_paths_dash_means_stdout(self) -> None:
        from xlsx2csv2json.cli import _resolve_paths
        with tempfile.TemporaryDirectory() as td:
            inp = _make_workbook(Path(td))
            _, ro, _ = _resolve_paths(str(inp), "-", None)
            self.assertIsNone(ro)

    def test_resolve_paths_output_dir_created(self) -> None:
        from xlsx2csv2json.cli import _resolve_paths
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            inp = _make_workbook(td_path)
            out_dir = td_path / "csv-out"
            self.assertFalse(out_dir.exists())
            _, _, rd = _resolve_paths(str(inp), None, str(out_dir))
            self.assertTrue(out_dir.exists())
            self.assertEqual(rd, out_dir.resolve())


# ===========================================================================
# _run_with_envelope
# ===========================================================================
class TestRunWithEnvelope(unittest.TestCase):

    def _capture_stderr(self) -> io.StringIO:
        buf = io.StringIO()
        self._old_stderr = sys.stderr
        sys.stderr = buf
        self.addCleanup(self._restore_stderr)
        return buf

    def _restore_stderr(self) -> None:
        sys.stderr = self._old_stderr

    def test_run_with_envelope_happy_path(self) -> None:
        from xlsx2csv2json.cli import _run_with_envelope
        rc = _run_with_envelope(_make_args(), body=lambda: 0)
        self.assertEqual(rc, 0)

    def test_run_with_envelope_self_overwrite_refused(self) -> None:
        from xlsx2csv2json.cli import _run_with_envelope
        from xlsx2csv2json import SelfOverwriteRefused
        buf = self._capture_stderr()

        def body():
            raise SelfOverwriteRefused("Refusing to overwrite input: foo.xlsx")

        rc = _run_with_envelope(_make_args(json_errors=True), body=body)
        self.assertEqual(rc, 6)
        envelope = json.loads(buf.getvalue().strip())
        self.assertEqual(envelope["v"], 1)
        self.assertEqual(envelope["code"], 6)
        self.assertEqual(envelope["type"], "SelfOverwriteRefused")

    def test_run_with_envelope_encrypted_workbook_basename_only(self) -> None:
        from xlsx2csv2json.cli import _run_with_envelope
        from xlsx_read import EncryptedWorkbookError
        buf = self._capture_stderr()

        def body():
            # Library now emits basename-only messages (xlsx_read §13.2)
            # but we still verify the envelope's details carry the
            # basename and not a full path. We construct a message that
            # contains a "/" so _basename_details strips it.
            raise EncryptedWorkbookError("Workbook is encrypted: /tmp/secret/encrypted.xlsx")

        rc = _run_with_envelope(_make_args(json_errors=True), body=body)
        self.assertEqual(rc, 3)
        envelope = json.loads(buf.getvalue().strip())
        self.assertEqual(envelope["code"], 3)
        self.assertEqual(envelope["type"], "EncryptedWorkbookError")
        # details.filename MUST be basename only.
        self.assertEqual(envelope["details"]["filename"], "encrypted.xlsx")

    def test_run_with_envelope_file_not_found(self) -> None:
        from xlsx2csv2json.cli import _run_with_envelope
        buf = self._capture_stderr()

        def body():
            # Mimic a FileNotFoundError with a filename attribute.
            exc = FileNotFoundError(2, "No such file", "/tmp/sub/missing.xlsx")
            raise exc

        rc = _run_with_envelope(_make_args(json_errors=True), body=body)
        self.assertEqual(rc, 1)
        envelope = json.loads(buf.getvalue().strip())
        self.assertEqual(envelope["code"], 1)
        self.assertEqual(envelope["type"], "FileNotFoundError")
        self.assertEqual(envelope["details"]["filename"], "missing.xlsx")

    def test_run_with_envelope_app_error_uses_class_code(self) -> None:
        from xlsx2csv2json.cli import _run_with_envelope
        from xlsx2csv2json import HeaderRowsConflict
        buf = self._capture_stderr()

        def body():
            raise HeaderRowsConflict(
                "Multi-table layouts require --header-rows auto"
            )

        rc = _run_with_envelope(_make_args(json_errors=True), body=body)
        self.assertEqual(rc, 2)
        envelope = json.loads(buf.getvalue().strip())
        self.assertEqual(envelope["code"], 2)
        self.assertEqual(envelope["type"], "HeaderRowsConflict")

    def test_run_with_envelope_unknown_exception_redacted_via_envelope(self) -> None:
        """H3 (vdd-multi) fix: unknown exceptions are caught by a terminal
        envelope branch and surfaced as ``Internal error: <ClassName>``
        with empty ``details`` so absolute paths in the raw message can
        never leak. Exit code 1.
        """
        from xlsx2csv2json.cli import _run_with_envelope
        buf = self._capture_stderr()

        def body():
            raise RuntimeError("unexpected error /private/secret/path.xlsx line 42")

        rc = _run_with_envelope(_make_args(json_errors=True), body=body)
        self.assertEqual(rc, 1)
        envelope = json.loads(buf.getvalue().strip())
        self.assertEqual(envelope["type"], "RuntimeError")
        self.assertEqual(envelope["code"], 1)
        # Raw message (which may carry paths) is NOT echoed.
        self.assertNotIn("/private/secret", buf.getvalue())


# ===========================================================================
# _emit_warnings_to_stderr
# ===========================================================================
class TestEmitWarnings(unittest.TestCase):

    def test_emit_warnings_propagates_via_showwarning(self) -> None:
        from xlsx2csv2json.cli import _emit_warnings_to_stderr
        from xlsx_read import MacroEnabledWarning

        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            warnings.warn("macros present: foo.xlsm", MacroEnabledWarning)

        # Now feed the captured records back through our helper and
        # confirm stderr receives something (default formatter).
        old_stderr = sys.stderr
        buf = io.StringIO()
        sys.stderr = buf
        try:
            _emit_warnings_to_stderr(captured)
        finally:
            sys.stderr = old_stderr

        text = buf.getvalue()
        self.assertIn("macros present", text)
        self.assertIn("MacroEnabledWarning", text)
        # Per ARCH HS-7, the output must NOT be a JSON envelope —
        # warnings are NEVER promoted to the cross-5 envelope shape.
        self.assertNotIn('"v": 1', text)
        self.assertNotIn('"v":1', text)


# ===========================================================================
# _validate_sheet_path_components
# ===========================================================================
class TestValidateSheetPathComponents(unittest.TestCase):

    def test_reject_each_forbidden_char(self) -> None:
        from xlsx2csv2json.dispatch import _validate_sheet_path_components
        from xlsx2csv2json import InvalidSheetNameForFsPath
        for ch in ("/", "\\", "\x00", ":", "*", "?", "<", ">", "|", '"'):
            with self.subTest(ch=ch):
                with self.assertRaises(InvalidSheetNameForFsPath):
                    _validate_sheet_path_components(f"bad{ch}name")

    def test_reject_dot_and_empty_and_dotdot(self) -> None:
        from xlsx2csv2json.dispatch import _validate_sheet_path_components
        from xlsx2csv2json import InvalidSheetNameForFsPath
        for name in (".", "..", ""):
            with self.subTest(name=name):
                with self.assertRaises(InvalidSheetNameForFsPath):
                    _validate_sheet_path_components(name)

    def test_reject_embedded_dotdot(self) -> None:
        from xlsx2csv2json.dispatch import _validate_sheet_path_components
        from xlsx2csv2json import InvalidSheetNameForFsPath
        with self.assertRaises(InvalidSheetNameForFsPath):
            _validate_sheet_path_components("my..file")

    def test_accept_happy_names(self) -> None:
        from xlsx2csv2json.dispatch import _validate_sheet_path_components
        for name in (
            "My Sheet",
            "Q1_2026",
            "Sales (US)",
            "with__double_underscore",  # L4 lock — '__' is NOT a separator.
            "中文报表",
        ):
            with self.subTest(name=name):
                _validate_sheet_path_components(name)  # must not raise


if __name__ == "__main__":
    unittest.main()

"""Cross-cutting envelope tests for xlsx2md (task 012-02).

Covers:
* `_validate_flag_combo` — M7 lock + R14h gate (UC-07 Scenario A, R13, R14h).
* `_resolve_paths` — same-path guard via `Path.resolve()` symlink-follow (UC-08).
* `main()` typed-exception routing — encrypted (UC-09), sheet-not-found, macro
  (UC-10), and the terminal `InternalError` catch-all with raw-message
  redaction (R23f, inherited from xlsx-8 §14.4 H3).

Test slugs bound from TASK §5.1: #14, #16, #17, #18, #22, #27, #34.
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# scripts/ root must be on sys.path so `_errors`, `xlsx_read`, and `xlsx2md`
# resolve. Mirrors the shim's `sys.path.insert(0, parent)` boilerplate.
_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

import xlsx2md  # noqa: E402
from xlsx2md.cli import (  # noqa: E402
    _resolve_paths,
    _validate_flag_combo,
    build_parser,
    main,
)
from xlsx2md.exceptions import (  # noqa: E402
    HeaderRowsConflict,
    IncludeFormulasRequiresHTML,
    SelfOverwriteRefused,
)


_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _parse(argv: list[str]):
    """Helper: parse argv via the real parser, return the Namespace."""
    return build_parser().parse_args(argv)


class TestValidateFlagCombo(unittest.TestCase):
    """`_validate_flag_combo` — pre-flight gates that fire before file I/O."""

    def test_validate_flag_combo_m7_gfm_plus_formulas_raises(self) -> None:
        """TC-UNIT-01 — M7 lock: --format=gfm + --include-formulas -> raises."""
        args = _parse([
            "dummy.xlsx", "--format=gfm", "--include-formulas",
        ])
        with self.assertRaises(IncludeFormulasRequiresHTML):
            _validate_flag_combo(args)

    def test_validate_flag_combo_html_plus_formulas_ok(self) -> None:
        """TC-UNIT-02 — --format=html + --include-formulas: no raise."""
        args = _parse([
            "dummy.xlsx", "--format=html", "--include-formulas",
        ])
        _validate_flag_combo(args)  # should not raise

    def test_validate_flag_combo_hybrid_plus_formulas_ok(self) -> None:
        """TC-UNIT-03 — --format=hybrid + --include-formulas: no raise (R2-M1)."""
        args = _parse([
            "dummy.xlsx", "--format=hybrid", "--include-formulas",
        ])
        _validate_flag_combo(args)  # should not raise

    def test_validate_flag_combo_header_rows_int_with_multi_table_raises(self) -> None:
        """TC-UNIT-04 — R14h: --header-rows=2 with multi-table mode -> raises."""
        args = _parse(["dummy.xlsx", "--header-rows=2"])
        with self.assertRaises(HeaderRowsConflict) as ctx:
            _validate_flag_combo(args)
        details = ctx.exception.args[0]
        self.assertEqual(details["n_requested"], 2)
        self.assertEqual(details["table_count"], "unknown_pre_open")
        self.assertIn("auto", details["suggestion"])
        self.assertIn("smart", details["suggestion"])

    def test_validate_flag_combo_header_rows_int_with_no_split_ok(self) -> None:
        """TC-UNIT-05 — R14h: --header-rows=2 + --no-split: NO raise."""
        args = _parse(["dummy.xlsx", "--header-rows=2", "--no-split"])
        _validate_flag_combo(args)

    def test_validate_flag_combo_header_rows_int_with_no_table_autodetect_ok(self) -> None:
        """TC-UNIT-05b — R14h: --header-rows=2 + --no-table-autodetect: NO raise."""
        args = _parse([
            "dummy.xlsx", "--header-rows=2", "--no-table-autodetect",
        ])
        _validate_flag_combo(args)

    def test_validate_flag_combo_header_rows_auto_with_multi_table_ok(self) -> None:
        """TC-UNIT-06 — R14h: --header-rows=auto + multi-table: no raise."""
        args = _parse(["dummy.xlsx", "--header-rows=auto"])
        _validate_flag_combo(args)

    def test_validate_flag_combo_header_rows_smart_with_multi_table_ok(self) -> None:
        """TC-UNIT-07 — R14h: --header-rows=smart + multi-table: no raise."""
        args = _parse(["dummy.xlsx", "--header-rows=smart"])
        _validate_flag_combo(args)


class TestResolvePaths(unittest.TestCase):
    """`_resolve_paths` — canonical resolution + same-path guard + auto-create."""

    def test_resolve_paths_same_path_exits_6_via_symlink(self) -> None:
        """TC-UNIT-08 — cross-7 H1: symlink OUTPUT -> INPUT -> SelfOverwriteRefused."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "single_cell.xlsx"
            src.write_bytes((_FIXTURES / "single_cell.xlsx").read_bytes())
            link = tdp / "out.md"
            os.symlink(src, link)
            args = _parse([str(src), str(link)])
            with self.assertRaises(SelfOverwriteRefused) as ctx:
                _resolve_paths(args)
            self.assertEqual(ctx.exception.args[0]["path"], src.name)
            # Basename only — no absolute path in details (sec note).
            self.assertNotIn("/", ctx.exception.args[0]["path"])

    def test_resolve_paths_different_extension_same_inode_exits_6(self) -> None:
        """TC-UNIT-09 — paranoia guard: extension mismatch still trips same-path."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "data.xlsx"
            src.write_bytes((_FIXTURES / "single_cell.xlsx").read_bytes())
            # Create a symlink with .md extension but pointing to the .xlsx.
            link = tdp / "data.md"
            os.symlink(src, link)
            args = _parse([str(src), str(link)])
            with self.assertRaises(SelfOverwriteRefused):
                _resolve_paths(args)

    def test_resolve_paths_creates_output_parent_dir(self) -> None:
        """TC-UNIT-10 — R4d: missing OUTPUT parent dir is auto-created."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "in.xlsx"
            src.write_bytes((_FIXTURES / "single_cell.xlsx").read_bytes())
            out = tdp / "new" / "nested" / "out.md"
            self.assertFalse(out.parent.exists())
            args = _parse([str(src), str(out)])
            _resolve_paths(args)
            self.assertTrue(out.parent.exists())

    def test_resolve_paths_stdout_mode_returns_none(self) -> None:
        """TC-UNIT-10b — OUTPUT='-' (or omitted) returns (input_path, None)."""
        args = _parse([str(_FIXTURES / "single_cell.xlsx"), "-"])
        in_path, out_path = _resolve_paths(args)
        self.assertIsNone(out_path)
        self.assertTrue(in_path.is_absolute())


class TestMainEnvelopeRouting(unittest.TestCase):
    """`main()` exception-to-envelope routing for cross-3/4/5/7 + InternalError."""

    def test_main_catches_encrypted_workbook_to_exit_3_basename_only(self) -> None:
        """TC-UNIT-11 + T-encrypted-workbook-exit3 (#17) — exit 3 + basename-only."""
        encrypted = _FIXTURES / "encrypted.xlsx"
        captured_stderr = io.StringIO()
        with patch.object(sys, "stderr", captured_stderr):
            result = main([str(encrypted), "--json-errors"])
        self.assertEqual(result, 3)
        envelope = json.loads(captured_stderr.getvalue().strip())
        self.assertEqual(envelope["v"], 1)
        self.assertEqual(envelope["code"], 3)
        self.assertEqual(envelope["type"], "EncryptedWorkbookError")
        self.assertEqual(envelope["details"]["filename"], "encrypted.xlsx")
        # Critical: no absolute path leak in details.filename.
        self.assertNotIn("/", envelope["details"]["filename"])

    def test_main_macro_warning_continues_with_exit_0(self) -> None:
        """TC-UNIT-13 + T-xlsm-macro-warning (#18) — .xlsm extracts + warns."""
        macro_xlsm = _FIXTURES / "macro_simple.xlsm"
        import tempfile
        captured_stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.md"
            with patch.object(sys, "stderr", captured_stderr):
                result = main([str(macro_xlsm), str(out)])
        self.assertEqual(result, 0)
        self.assertIn("macro", captured_stderr.getvalue().lower())

    def test_main_json_errors_envelope_shape_v1_all_five_keys(self) -> None:
        """TC-UNIT-14 + T-json-errors-envelope-shape-v1 (#22) — 5-key shape."""
        encrypted = _FIXTURES / "encrypted.xlsx"
        captured_stderr = io.StringIO()
        with patch.object(sys, "stderr", captured_stderr):
            result = main([str(encrypted), "--json-errors"])
        self.assertEqual(result, 3)
        envelope = json.loads(captured_stderr.getvalue().strip())
        self.assertEqual(envelope["v"], 1)
        self.assertIn("error", envelope)
        self.assertEqual(envelope["code"], 3)
        self.assertIn("type", envelope)
        self.assertIn("details", envelope)
        self.assertNotEqual(envelope["code"], 0)

    def test_main_terminal_catchall_redacts_path_in_error_field(self) -> None:
        """TC-UNIT-15 + T-internal-error-envelope-redacts-raw-message (#34)."""
        single_cell = _FIXTURES / "single_cell.xlsx"
        captured_stderr = io.StringIO()

        def _raise_permission(*args, **kwargs):
            raise PermissionError("/Users/secret/file.xlsx")

        # cli.main() imports `open_workbook` inside the function body via
        # `from xlsx_read import open_workbook`, so the name lives in the
        # `xlsx_read` module — patch the source.
        with patch("xlsx_read.open_workbook", side_effect=_raise_permission), \
             patch.object(sys, "stderr", captured_stderr):
            result = main([str(single_cell), "--json-errors"])
        self.assertEqual(result, 7)
        envelope = json.loads(captured_stderr.getvalue().strip())
        self.assertEqual(envelope["v"], 1)
        self.assertEqual(envelope["code"], 7)
        self.assertEqual(envelope["type"], "InternalError")
        self.assertEqual(envelope["error"], "Internal error: PermissionError")
        # The critical redaction assertion: raw exception args MUST NOT leak.
        self.assertNotIn("/Users/secret", json.dumps(envelope))
        self.assertNotIn("file.xlsx", envelope["error"])

    def test_main_terminal_catchall_uses_internal_error_code_7(self) -> None:
        """TC-UNIT-16 — terminal catch-all returns InternalError.CODE == 7."""
        from xlsx2md.exceptions import InternalError  # noqa: PLC0415
        self.assertEqual(InternalError.CODE, 7)

        single_cell = _FIXTURES / "single_cell.xlsx"
        captured_stderr = io.StringIO()
        with patch(
            "xlsx_read.open_workbook",
            side_effect=RuntimeError("openpyxl detail leak: /tmp/x"),
        ), patch.object(sys, "stderr", captured_stderr):
            result = main([str(single_cell)])
        self.assertEqual(result, 7)

    def test_main_m7_lock_exits_2_no_file_io(self) -> None:
        """T-include-formulas-gfm-exits2 (#14) — M7 fires before workbook open."""
        # If the gate works, the path doesn't matter because no file I/O occurs.
        result = main([
            "/tmp/never_opened.xlsx",
            "--format=gfm",
            "--include-formulas",
        ])
        self.assertEqual(result, 2)

    def test_main_header_rows_conflict_exits_2_no_file_io(self) -> None:
        """T-header-rows-int-with-multi-table-exits-2-conflict (#27)."""
        captured_stderr = io.StringIO()
        with patch.object(sys, "stderr", captured_stderr):
            result = main([
                "/tmp/never_opened.xlsx",
                "--header-rows=2",
                "--json-errors",
            ])
        self.assertEqual(result, 2)
        envelope = json.loads(captured_stderr.getvalue().strip())
        self.assertEqual(envelope["type"], "HeaderRowsConflict")
        self.assertEqual(envelope["details"]["n_requested"], 2)

    def test_main_same_path_via_symlink_exit_6(self) -> None:
        """T-same-path-via-symlink-exit6 (#16) — exit 6 SelfOverwriteRefused."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "single_cell.xlsx"
            src.write_bytes((_FIXTURES / "single_cell.xlsx").read_bytes())
            link = tdp / "out.md"
            os.symlink(src, link)
            captured_stderr = io.StringIO()
            with patch.object(sys, "stderr", captured_stderr):
                result = main([str(src), str(link), "--json-errors"])
            self.assertEqual(result, 6)
            envelope = json.loads(captured_stderr.getvalue().strip())
            self.assertEqual(envelope["type"], "SelfOverwriteRefused")
            self.assertEqual(envelope["details"]["path"], src.name)


class TestStreamingWarningsSurviveException(unittest.TestCase):
    """Sarcasmotron H3 fix: warnings reach stderr even when
    ``emit_workbook_md`` raises.

    Previously ``warnings.catch_warnings(record=True)`` buffered all
    warnings and drained them only on the success branch. Any exception
    propagating out of ``emit_workbook_md`` discarded the captured list
    silently — users lost scheme-allowlist blocks, streaming-mode
    hyperlink-unreliability notices, multi-row flatten warnings, etc.

    The fix replaces buffering with a custom ``warnings.showwarning``
    hook that streams each warning directly to stderr — fires per
    ``warnings.warn(...)`` call, surviving any downstream exception.
    """

    def test_warning_emitted_before_exception_reaches_stderr(self) -> None:
        """Warning emitted by xlsx_read BEFORE the exception propagates
        must reach stderr (not be silently dropped).
        """
        single_cell = _FIXTURES / "single_cell.xlsx"
        captured_stderr = io.StringIO()

        # Patch open_workbook to (1) emit a warning then (2) raise.
        # The H3 fix's streaming `showwarning` hook must write the
        # warning to stderr at step (1) — the exception at step (2)
        # would otherwise unwind the catch_warnings block before any
        # drain. The custom hook flushes immediately.
        from xlsx_read import open_workbook as _real_open_workbook  # noqa: PLC0415

        def _open_then_raise(*args, **kwargs):
            import warnings as _w
            _w.warn(
                "TEST_WARNING_BEFORE_RAISE",
                UserWarning, stacklevel=2,
            )
            raise RuntimeError("simulated openpyxl failure /Users/secret/x")

        with patch("xlsx_read.open_workbook", side_effect=_open_then_raise), \
             patch.object(sys, "stderr", captured_stderr):
            result = main([str(single_cell)])

        stderr_text = captured_stderr.getvalue()
        # H3 ASSERTION 1: warning must have reached stderr (NOT silently
        # dropped on the exception path).
        self.assertIn(
            "TEST_WARNING_BEFORE_RAISE", stderr_text,
            f"H3 FIX: warnings emitted before an exception MUST reach "
            f"stderr. Got stderr={stderr_text!r}. This is the "
            f"warnings-batched-then-lost bug — see Sarcasmotron H3.",
        )
        # H3 ASSERTION 2: the exception still produces an InternalError
        # envelope (the terminal catch-all from R23f still works).
        self.assertEqual(result, 7, "RuntimeError → InternalError code 7")
        # H3 ASSERTION 3: the raw exception message must NOT leak via the
        # warning (R23f redaction guarantee — the warning was emitted
        # by xlsx_read INTERNALS, not by the catch-all; verify the
        # path-leak guard still applies to the envelope, separately).
        self.assertNotIn(
            "/Users/secret", stderr_text.split("Internal error")[-1],
            "R23f: the InternalError envelope portion of stderr must "
            "NOT contain the raw exception path.",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

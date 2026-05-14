"""Programmatic helper `convert_xlsx_to_md` argv-builder tests (task 012-02).

Verifies the `--flag=value` atomic-token form (D-A3 / D7 lock) and the
True/False/None kwarg-to-flag conversion semantics. Mirrors xlsx-3's
`convert_md_tables_to_xlsx` and xlsx-2's `convert_json_to_xlsx` test
patterns — same M4 lock inherited.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

import xlsx2md  # noqa: E402


class TestConvertHelperArgvBuilder(unittest.TestCase):
    """`convert_xlsx_to_md` argv-builder contract (D-A3 / D7)."""

    def _captured_argv(self, *args, **kwargs) -> list[str]:
        """Patch `xlsx2md.main`, call `convert_xlsx_to_md`, return the
        argv passed into `main`. Returns 0 from the patch.
        """
        with patch("xlsx2md.main", return_value=0) as mock_main:
            xlsx2md.convert_xlsx_to_md(*args, **kwargs)
            self.assertEqual(mock_main.call_count, 1)
            return mock_main.call_args[0][0]

    def test_convert_helper_no_kwargs_uses_defaults(self) -> None:
        """TC-UNIT-01 — no kwargs => only positionals in argv."""
        argv = self._captured_argv("in.xlsx", "out.md")
        self.assertEqual(argv, ["in.xlsx", "out.md"])

    def test_convert_helper_no_output_omits_positional(self) -> None:
        """TC-UNIT-01b — output_path=None => only INPUT in argv."""
        argv = self._captured_argv("in.xlsx")
        self.assertEqual(argv, ["in.xlsx"])

    def test_convert_helper_flag_value_atomic_token(self) -> None:
        """TC-UNIT-02 — string kwarg => `--flag=value` atomic token (D7)."""
        argv = self._captured_argv("in.xlsx", format="hybrid")
        self.assertIn("--format=hybrid", argv)
        # Confirm it is ONE element (atomic) not two (`--format` then `hybrid`).
        self.assertNotIn("--format", argv)
        self.assertNotIn("hybrid", argv)

    def test_convert_helper_boolean_true_appends_flag_only(self) -> None:
        """TC-UNIT-03 — True => flag-only (no `=True`)."""
        argv = self._captured_argv("in.xlsx", include_formulas=True)
        self.assertIn("--include-formulas", argv)
        self.assertNotIn("--include-formulas=True", argv)

    def test_convert_helper_boolean_false_omits_flag(self) -> None:
        """TC-UNIT-04 — False => flag entirely omitted."""
        argv = self._captured_argv("in.xlsx", include_formulas=False)
        self.assertNotIn("--include-formulas", argv)
        self.assertNotIn("--include-formulas=False", argv)

    def test_convert_helper_none_kwarg_skipped(self) -> None:
        """TC-UNIT-05 — None => flag entirely omitted."""
        argv = self._captured_argv("in.xlsx", memory_mode=None)
        self.assertNotIn("--memory-mode", argv)
        self.assertNotIn("--memory-mode=None", argv)

    def test_convert_helper_underscore_to_dash_in_flag_name(self) -> None:
        """TC-UNIT-06 — `kwarg_name` => `--kwarg-name` (underscore -> dash)."""
        argv = self._captured_argv(
            "in.xlsx",
            hyperlink_scheme_allowlist="http,https",
        )
        self.assertIn("--hyperlink-scheme-allowlist=http,https", argv)

    def test_convert_helper_leading_dashes_in_value_safe(self) -> None:
        """TC-UNIT-07 (M4 lock) — value beginning with `--` is NOT swallowed.

        Inherited from xlsx-2 / xlsx-3 M4 lock: `--flag=value` is an atomic
        argparse token; a kwarg value that happens to begin with `--` (e.g.
        `sheet="--evil-flag-attempt"`) is NOT re-interpreted as a separate
        flag.
        """
        argv = self._captured_argv("in.xlsx", sheet="--evil-flag-attempt")
        self.assertIn("--sheet=--evil-flag-attempt", argv)
        self.assertNotIn("--evil-flag-attempt", argv)

    def test_convert_helper_routes_through_main(self) -> None:
        """TC-UNIT-08 — return value = main() return value (pass-through)."""
        with patch("xlsx2md.main", return_value=42) as mock_main:
            result = xlsx2md.convert_xlsx_to_md("in.xlsx")
            self.assertEqual(result, 42)
            mock_main.assert_called_once_with(["in.xlsx"])


class TestConvertHelperUnknownKwargRaisesTypeError(unittest.TestCase):
    """Sarcasmotron M4 fix: convert_xlsx_to_md validates kwargs against
    a known set and raises TypeError on unknown — NOT SystemExit(2) from
    argparse. Python callers must not have to catch SystemExit.
    """

    def test_unknown_kwarg_raises_typeerror_not_systemexit(self) -> None:
        with self.assertRaises(TypeError) as ctx:
            xlsx2md.convert_xlsx_to_md("in.xlsx", sheett="Sheet1")
        msg = str(ctx.exception)
        # Error message names the offending kwarg.
        self.assertIn("sheett", msg)

    def test_unknown_kwarg_does_not_invoke_main(self) -> None:
        """TypeError must be raised before main() is reached."""
        from unittest.mock import patch
        with patch("xlsx2md.main") as mock_main, self.assertRaises(TypeError):
            xlsx2md.convert_xlsx_to_md("in.xlsx", typo_arg="x")
        mock_main.assert_not_called()

    def test_known_kwargs_pass_through_to_main(self) -> None:
        """Sanity: all 14 documented kwargs are accepted by the validator."""
        from unittest.mock import patch
        all_known = {
            "sheet": "Sheet1",
            "include_hidden": True,
            "format": "html",
            "header_rows": 1,
            "memory_mode": "full",
            "hyperlink_scheme_allowlist": "http,https",
            "no_table_autodetect": True,
            "no_split": True,
            "gap_rows": 3,
            "gap_cols": 2,
            "gfm_merge_policy": "duplicate",
            "datetime_format": "ISO",
            "include_formulas": True,
            "json_errors": True,
        }
        with patch("xlsx2md.main", return_value=0) as mock_main:
            result = xlsx2md.convert_xlsx_to_md("in.xlsx", **all_known)
        self.assertEqual(result, 0)
        mock_main.assert_called_once()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

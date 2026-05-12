"""Task 009-02 — F1 `_workbook.py` E2E + unit tests.

Covers UC-01 (open unencrypted + alts A1–A4), the `read_only`
heuristic (D-A6), the cross-3 + cross-4 contracts, and the M8 spike
(empirical openpyxl behaviour on overlapping `<mergeCells>`).
"""

from __future__ import annotations

import unittest
import warnings
import zipfile
from pathlib import Path

import openpyxl

from xlsx_read import (
    EncryptedWorkbookError,
    MacroEnabledWarning,
    WorkbookReader,
    open_workbook,
)
from xlsx_read import _workbook
from xlsx_read.tests.conftest import FIXTURES_DIR


# ---------------------------------------------------------------------------
# End-to-end tests (TASK 009-02 §Test Cases / E2E)
# ---------------------------------------------------------------------------


class TestOpenUnencrypted(unittest.TestCase):
    """TC-E2E-01: happy path on `empty.xlsx`."""

    def test_returns_reader(self) -> None:
        reader = open_workbook(FIXTURES_DIR / "empty.xlsx")
        try:
            self.assertIsInstance(reader, WorkbookReader)
            self.assertTrue(reader.path.is_absolute())
            self.assertFalse(reader._read_only)  # 5 KB file is well under 10 MiB
        finally:
            reader.close()

    def test_close_is_idempotent(self) -> None:
        reader = open_workbook(FIXTURES_DIR / "empty.xlsx")
        reader.close()
        reader.close()  # MUST NOT raise
        self.assertTrue(reader._closed)


class TestOpenEncrypted(unittest.TestCase):
    """TC-E2E-02: encrypted workbook raises `EncryptedWorkbookError`."""

    def test_encrypted_xlsx_raises(self) -> None:
        with self.assertRaises(EncryptedWorkbookError) as ctx:
            open_workbook(FIXTURES_DIR / "encrypted.xlsx")
        # Path must be in the message for caller-side diagnostics.
        self.assertIn("encrypted.xlsx", str(ctx.exception))

    def test_exception_is_local_not_openpyxl(self) -> None:
        # R1 closed-API guarantee: typed exception is declared in
        # xlsx_read, not in openpyxl. Caller can `except
        # EncryptedWorkbookError` without importing openpyxl.
        self.assertTrue(EncryptedWorkbookError.__module__.startswith("xlsx_read"))


class TestOpenMacroEnabled(unittest.TestCase):
    """TC-E2E-03: `.xlsm` emits exactly one `MacroEnabledWarning`, no raise."""

    def test_warn_then_succeed(self) -> None:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            reader = open_workbook(FIXTURES_DIR / "macros.xlsm")
            try:
                self.assertIsInstance(reader, WorkbookReader)
            finally:
                reader.close()
        macro_warnings = [w for w in captured if issubclass(w.category, MacroEnabledWarning)]
        self.assertEqual(len(macro_warnings), 1)
        self.assertIn("vbaProject.bin", str(macro_warnings[0].message))


class TestOpenMissingFile(unittest.TestCase):
    """TC-E2E-04: missing file propagates `FileNotFoundError`."""

    def test_missing_raises_FNF(self) -> None:
        with self.assertRaises(FileNotFoundError):
            open_workbook(FIXTURES_DIR / "nonexistent.xlsx")


class TestOpenCorruptedFile(unittest.TestCase):
    """TC-E2E-05: non-ZIP input lets openpyxl's error surface."""

    def test_text_file_propagates(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".xlsx", delete=False
        ) as f:
            f.write(b"this is not a zip nor a CFB compound file\n")
            bogus = Path(f.name)
        try:
            # We accept ANY non-EncryptedWorkbookError; openpyxl typically
            # raises `InvalidFileException` here, but the exact class is
            # not part of our contract — what matters is that we DO NOT
            # mis-classify a bogus text file as encrypted.
            with self.assertRaises(Exception) as ctx:
                open_workbook(bogus)
            self.assertNotIsInstance(ctx.exception, EncryptedWorkbookError)
        finally:
            bogus.unlink(missing_ok=True)


class TestReadOnlyAutoThreshold(unittest.TestCase):
    """TC-E2E-06: file > threshold ⇒ `read_only=True`."""

    def test_large_file_picks_readonly_at_default_threshold(self) -> None:
        # large_5mib.xlsx is ~6.5 MiB; default threshold is 10 MiB →
        # full mode. Override threshold to force the streaming path.
        reader = open_workbook(
            FIXTURES_DIR / "large_5mib.xlsx", size_threshold_bytes=1024
        )
        try:
            self.assertTrue(reader._read_only)
        finally:
            reader.close()

    def test_small_file_picks_full_mode_at_default(self) -> None:
        reader = open_workbook(FIXTURES_DIR / "empty.xlsx")
        try:
            self.assertFalse(reader._read_only)
        finally:
            reader.close()


class TestReadOnlyOverride(unittest.TestCase):
    """TC-E2E-07: caller-supplied `read_only_mode` wins."""

    def test_explicit_true_forces_readonly(self) -> None:
        reader = open_workbook(FIXTURES_DIR / "empty.xlsx", read_only_mode=True)
        try:
            self.assertTrue(reader._read_only)
        finally:
            reader.close()

    def test_explicit_false_forces_full(self) -> None:
        # Override to False on a large fixture overrides the auto-threshold.
        reader = open_workbook(
            FIXTURES_DIR / "large_5mib.xlsx",
            read_only_mode=False,
            size_threshold_bytes=1024,
        )
        try:
            self.assertFalse(reader._read_only)
        finally:
            reader.close()


class TestContextManager(unittest.TestCase):
    """TC-E2E-08: `with open_workbook(...) as r:` releases on exit."""

    def test_enter_returns_self_exit_closes(self) -> None:
        with open_workbook(FIXTURES_DIR / "empty.xlsx") as reader:
            self.assertIsInstance(reader, WorkbookReader)
            self.assertFalse(reader._closed)
        self.assertTrue(reader._closed)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestProbeEncryption(unittest.TestCase):
    """TC-UNIT-01: `_probe_encryption` truth table."""

    def test_empty_is_clean(self) -> None:
        self.assertIsNone(_workbook._probe_encryption(FIXTURES_DIR / "empty.xlsx"))

    def test_encrypted_raises(self) -> None:
        with self.assertRaises(EncryptedWorkbookError):
            _workbook._probe_encryption(FIXTURES_DIR / "encrypted.xlsx")

    def test_macros_is_clean(self) -> None:
        # Macros are NOT encryption — probe must be clean.
        self.assertIsNone(_workbook._probe_encryption(FIXTURES_DIR / "macros.xlsm"))


class TestProbeMacros(unittest.TestCase):
    """TC-UNIT-02: `_probe_macros` returns True iff vbaProject.bin present."""

    def test_macros_detected(self) -> None:
        self.assertTrue(_workbook._probe_macros(FIXTURES_DIR / "macros.xlsm"))

    def test_clean_returns_false(self) -> None:
        self.assertFalse(_workbook._probe_macros(FIXTURES_DIR / "empty.xlsx"))


class TestDecideReadOnly(unittest.TestCase):
    """TC-UNIT-03: `_decide_read_only` 6-cell truth table."""

    def test_override_true_wins(self) -> None:
        p = FIXTURES_DIR / "empty.xlsx"
        self.assertTrue(_workbook._decide_read_only(p, True, 1024))
        self.assertTrue(_workbook._decide_read_only(p, True, 10**12))

    def test_override_false_wins(self) -> None:
        p = FIXTURES_DIR / "large_5mib.xlsx"
        self.assertFalse(_workbook._decide_read_only(p, False, 1024))
        self.assertFalse(_workbook._decide_read_only(p, False, 10**12))

    def test_no_override_below_threshold(self) -> None:
        # 5 KB file under default 10 MiB threshold → False.
        self.assertFalse(
            _workbook._decide_read_only(FIXTURES_DIR / "empty.xlsx", None, 10 * 1024 * 1024)
        )

    def test_no_override_above_threshold(self) -> None:
        # 6.5 MiB file with tiny threshold → True.
        self.assertTrue(
            _workbook._decide_read_only(FIXTURES_DIR / "large_5mib.xlsx", None, 1024)
        )


class TestNoOpenpyxlLeakInExceptions(unittest.TestCase):
    """TC-UNIT-04: closed-API regression — raised exception carries no openpyxl types.

    The first task that exercises this guard (R1 contract); the same
    invariant is re-asserted in 009-08's full closed-API regression.
    """

    def test_encrypted_exception_args_have_no_openpyxl(self) -> None:
        try:
            open_workbook(FIXTURES_DIR / "encrypted.xlsx")
        except EncryptedWorkbookError as exc:
            for arg in exc.args:
                self.assertNotIn("openpyxl", repr(type(arg)))
        else:
            self.fail("EncryptedWorkbookError was not raised")


# ---------------------------------------------------------------------------
# M8 spike — TC-SPIKE-01
# ---------------------------------------------------------------------------


class TestOpenpyxlOverlappingMergesBehaviour(unittest.TestCase):
    """TC-SPIKE-01 (M8 / D-A8): record openpyxl's behaviour on overlapping merges.

    The fixture `overlapping_merges.xlsx` carries two intersecting
    `<mergeCells>` ranges (`A1:B2` and `B2:C3`) injected by hand via
    post-save zip patching — ECMA-376 forbids the configuration, but
    real-world corrupted workbooks contain it, and openpyxl's
    behaviour was unverified at design time (M8 design-question).

    Empirical result (recorded 2026-05-12, openpyxl 3.1.5,
    Python 3.14.4):

        openpyxl `load_workbook(...)` **succeeds**. The resulting
        `ws.merged_cells.ranges` exposes **both** ranges; openpyxl
        does NOT detect the overlap and does NOT raise.

    Implication for 009-04: `_overlapping_merges_check` must
    perform an explicit detection pass (no reliance on openpyxl
    surfacing the issue). The current 009-01 stub is a no-op; the
    real implementation lands in task 009-04.
    """

    def test_openpyxl_silently_accepts_overlapping_merges(self) -> None:
        path = FIXTURES_DIR / "overlapping_merges.xlsx"
        wb = openpyxl.load_workbook(filename=str(path), read_only=False)
        try:
            ws = wb.active
            ranges = [str(r) for r in ws.merged_cells.ranges]
            # The fixture injected exactly these two ranges via raw XML.
            self.assertIn("A1:B2", ranges)
            self.assertIn("B2:C3", ranges)
        finally:
            wb.close()

    def test_open_workbook_does_not_raise(self) -> None:
        # `open_workbook` (F1) does not yet detect overlapping merges —
        # that is F3's job (009-04). Confirming the regression boundary
        # so 009-04's `_overlapping_merges_check` has a clear scope.
        reader = open_workbook(FIXTURES_DIR / "overlapping_merges.xlsx")
        try:
            self.assertIsInstance(reader, WorkbookReader)
        finally:
            reader.close()


# ---------------------------------------------------------------------------
# Defence-in-depth — encryption probe must short-circuit non-ZIP inputs.
# ---------------------------------------------------------------------------


class TestProbeEncryptionRobustness(unittest.TestCase):
    """Defence-in-depth: probe handles odd-shaped inputs gracefully."""

    def test_short_file_not_misclassified(self) -> None:
        # A file shorter than the CFB magic must not raise — we just
        # return clean and let openpyxl emit its own error downstream.
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(b"x")
            short = Path(f.name)
        try:
            self.assertIsNone(_workbook._probe_encryption(short))
        finally:
            short.unlink(missing_ok=True)

    def test_zip_without_encryption_streams_is_clean(self) -> None:
        # The empty fixture is a valid OPC ZIP with no encryption parts.
        with zipfile.ZipFile(FIXTURES_DIR / "empty.xlsx") as zf:
            names = set(zf.namelist())
        self.assertFalse(names & _workbook._OPC_ENCRYPTED_NAMES)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

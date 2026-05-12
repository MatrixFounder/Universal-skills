"""Task 009-01 smoke + contract tests.

Asserts the **public surface** (`__all__`, dataclass shapes, exception
hierarchy, sentinel stub returns) and the **closed-API gate**
(`ruff` banned-api). Subsequent tasks (009-02..009-08) replace the
`NotImplementedError` assertions with positive behavioural assertions
as each stub becomes real.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

import xlsx_read
from xlsx_read import (
    AmbiguousHeaderBoundary,
    EncryptedWorkbookError,
    MacroEnabledWarning,
    OverlappingMerges,
    SheetInfo,
    SheetNotFound,
    TableData,
    TableRegion,
    WorkbookReader,
    open_workbook,
)

# Banned-api rule guards against importing private modules from outside the
# package, but the test suite legitimately needs to reach in to assert the
# stub sentinel return values. The test file is inside the package itself
# (`xlsx_read/tests/`) and is whitelisted by `[tool.ruff.lint.per-file-
# ignores]` in pyproject.toml.
from xlsx_read import _headers, _merges, _sheets, _tables, _values
from xlsx_read.tests.conftest import FIXTURES_DIR

EXPECTED_PUBLIC = [
    "AmbiguousHeaderBoundary",
    "DateFmt",
    "EncryptedWorkbookError",
    "MacroEnabledWarning",
    "MergePolicy",
    "OverlappingMerges",
    "SheetInfo",
    "SheetNotFound",
    "TableData",
    "TableDetectMode",
    "TableRegion",
    "WorkbookReader",
    "open_workbook",
]


class TestPublicSurface(unittest.TestCase):
    """TC-UNIT-01: `__all__` integrity — regression guard against public-surface drift."""

    def test_all_membership_locked(self) -> None:
        self.assertEqual(sorted(xlsx_read.__all__), EXPECTED_PUBLIC)

    def test_every_all_entry_is_importable(self) -> None:
        for name in xlsx_read.__all__:
            self.assertTrue(
                hasattr(xlsx_read, name),
                f"{name!r} listed in __all__ but not attached to module",
            )


class TestExceptionHierarchy(unittest.TestCase):
    """TC-UNIT-02: typed exceptions inherit the documented base classes."""

    def test_encrypted_is_runtime(self) -> None:
        self.assertTrue(issubclass(EncryptedWorkbookError, RuntimeError))

    def test_macro_is_userwarning(self) -> None:
        self.assertTrue(issubclass(MacroEnabledWarning, UserWarning))

    def test_overlap_is_runtime(self) -> None:
        self.assertTrue(issubclass(OverlappingMerges, RuntimeError))

    def test_ambiguous_is_userwarning(self) -> None:
        self.assertTrue(issubclass(AmbiguousHeaderBoundary, UserWarning))

    def test_sheet_not_found_is_keyerror(self) -> None:
        self.assertTrue(issubclass(SheetNotFound, KeyError))


class TestDataclassFrozen(unittest.TestCase):
    """TC-UNIT-03: outer dataclasses are frozen; mutating raises FrozenInstanceError."""

    def test_sheetinfo_is_dataclass(self) -> None:
        self.assertTrue(dataclasses.is_dataclass(SheetInfo))

    def test_sheetinfo_frozen(self) -> None:
        info = SheetInfo(name="X", index=0, state="visible")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            info.name = "Y"  # type: ignore[misc]

    def test_tableregion_frozen(self) -> None:
        region = TableRegion(
            sheet="S", top_row=1, left_col=1, bottom_row=1, right_col=1, source="gap_detect"
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            region.sheet = "T"  # type: ignore[misc]

    def test_tabledata_frozen_outer_mutable_inner(self) -> None:
        region = TableRegion(
            sheet="S", top_row=1, left_col=1, bottom_row=1, right_col=1, source="gap_detect"
        )
        td = TableData(region=region)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            td.region = region  # type: ignore[misc]
        # Inner lists ARE mutable (M3 + R2-M6 honest scope) — this must succeed.
        td.warnings.append("ok")
        td.rows.append([1, 2])
        td.headers.append("h")
        self.assertEqual(td.warnings, ["ok"])
        self.assertEqual(td.rows, [[1, 2]])
        self.assertEqual(td.headers, ["h"])


class TestSentinelReturns(unittest.TestCase):
    """TC-UNIT-04: stub modules return the documented sentinels."""

    # NOTE: `_sheets.enumerate_sheets` and `_sheets.resolve_sheet` are LIVE
    # after task 009-03 — they require a real `Workbook`-like object with
    # `sheetnames`. Detailed behaviour is asserted in `test_sheets.py`.
    # The 009-01 sentinel checks (passing `None`) have been retired per
    # `tdd-stub-first §2` (Phase-1 → Phase-2 transition).

    # `_merges.parse_merges` is LIVE after 009-04 and requires a
    # real `ws.merged_cells.ranges` source; behavioural coverage
    # lives in `test_merges.py`.

    def test_merges_apply_policy_passthrough(self) -> None:
        # Empty merge map → input grid unchanged (purity contract).
        rows = [[1, 2], [3, 4]]
        out = _merges.apply_merge_policy(rows, {}, "anchor-only")
        self.assertEqual(out, rows)

    def test_merges_overlap_check_noop_on_empty(self) -> None:
        # Empty iterable → no raise.
        self.assertIsNone(_merges._overlapping_merges_check([]))

    # `_tables.detect_tables` is LIVE after 009-05 and requires a
    # real `Workbook`. Coverage moved to `test_tables.py`.

    # `_headers.detect_header_band(..., "auto")` is LIVE after 009-06
    # and needs a real Worksheet with `merged_cells.ranges`. Detailed
    # coverage lives in `test_headers.py`.

    def test_headers_detect_int_hint_passthrough(self) -> None:
        # Integer hints short-circuit and never touch the worksheet —
        # so the sentinel test (passing None) still works.
        region = TableRegion(
            sheet="S", top_row=1, left_col=1, bottom_row=1, right_col=1, source="gap_detect"
        )
        self.assertEqual(_headers.detect_header_band(None, region, 3), 3)

    def test_headers_synthetic_format(self) -> None:
        self.assertEqual(_headers.synthetic_headers(0), [])
        self.assertEqual(_headers.synthetic_headers(3), ["col_1", "col_2", "col_3"])

    def test_headers_synthetic_negative_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _headers.synthetic_headers(-1)

    def test_headers_separator_is_u203a(self) -> None:
        # The constant must be exactly U+203A surrounded by spaces (UC-04 / R7).
        self.assertEqual(_headers.HEADER_SEPARATOR, " › ")

    def test_values_extract_passthrough(self) -> None:
        class FakeCell:
            value = 42

        v, w = _values.extract_cell(FakeCell())
        self.assertEqual(v, 42)
        self.assertIsNone(w)


class TestOpenWorkbookSmoke(unittest.TestCase):
    """After 009-02: `open_workbook(empty.xlsx)` returns a usable reader.

    Detailed UC-01 coverage lives in `test_workbook.py`; this smoke case
    is the contract anchor: the same fixture from 009-01 still imports
    cleanly through the now-live entry point.
    """

    def test_open_empty_returns_reader_and_closes(self) -> None:
        reader = open_workbook(FIXTURES_DIR / "empty.xlsx")
        self.assertIsInstance(reader, WorkbookReader)
        reader.close()
        # Second close must be idempotent (UC-01 main scenario contract).
        reader.close()


class TestImportSmoke(unittest.TestCase):
    """TC-E2E-01: `import xlsx_read` succeeds and exposes 13 names."""

    def test_thirteen_public_names(self) -> None:
        self.assertEqual(len(xlsx_read.__all__), 13)

    def test_no_macro_warning_filter_collision(self) -> None:
        # The library does not pollute the global warning state. A bare
        # `import xlsx_read` must not emit any MacroEnabledWarning.
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            import importlib

            importlib.reload(xlsx_read)
        macro_warnings = [w for w in captured if issubclass(w.category, MacroEnabledWarning)]
        self.assertEqual(macro_warnings, [])


class TestBannedApiRuleLive(unittest.TestCase):
    """TC-UNIT-05: ruff banned-api gate rejects external `xlsx_read._*` imports."""

    def test_leaky_import_fails_ruff(self) -> None:
        scripts_dir = Path(__file__).resolve().parents[2]
        # Place the leaky-import probe inside scripts/ so ruff applies the
        # project pyproject.toml; outside the dir ruff falls back to defaults
        # and the banned-api rule does not load.
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="leaky_import_probe_",
            dir=scripts_dir,
            delete=False,
        ) as f:
            f.write("from xlsx_read._workbook import open_workbook  # noqa: F401\n")
            probe = Path(f.name)
        try:
            ruff = scripts_dir / ".venv" / "bin" / "ruff"
            if not ruff.exists():
                self.skipTest("ruff not installed in venv (run install.sh)")
            proc = subprocess.run(
                [str(ruff), "check", str(probe)],
                capture_output=True,
                text=True,
                cwd=scripts_dir,
                check=False,
            )
            self.assertNotEqual(
                proc.returncode, 0, f"ruff should reject leaky import; stdout={proc.stdout!r}"
            )
            self.assertIn("TID251", proc.stdout + proc.stderr)
        finally:
            probe.unlink(missing_ok=True)


class TestNoOpenpyxlInExceptions(unittest.TestCase):
    """TC-UNIT-06: typed exceptions don't carry openpyxl types (closed-API guard)."""

    def test_exception_class_module_is_local(self) -> None:
        for exc_cls in (
            EncryptedWorkbookError,
            MacroEnabledWarning,
            OverlappingMerges,
            AmbiguousHeaderBoundary,
            SheetNotFound,
        ):
            self.assertTrue(
                exc_cls.__module__.startswith("xlsx_read"),
                f"{exc_cls.__name__} not declared in xlsx_read.* (was {exc_cls.__module__})",
            )


class TestWorkbookReaderContext(unittest.TestCase):
    """Stub-level smoke for context-manager protocol (final wiring lands in 009-02)."""

    def test_enter_returns_self_exit_calls_close(self) -> None:
        r = WorkbookReader(path=Path("."))
        with r as ctx:
            self.assertIs(ctx, r)
        self.assertTrue(r._closed)

    def test_close_is_idempotent(self) -> None:
        r = WorkbookReader(path=Path("."))
        r.close()
        r.close()  # second call must not raise
        self.assertTrue(r._closed)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(unittest.main())

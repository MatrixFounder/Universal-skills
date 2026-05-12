# Task 010-01 [STUB CREATION]: Package skeleton, shims, exceptions catalogue, smoke E2E

## Use Case Connection
- UC-01..UC-10 (all scaffolded as stubs returning sentinels)
- UC-09 (envelope plumbing skeleton — empty function bodies; envelope
  classes declared with `CODE` attribute already set)

## Task Goal

Lay down the **frozen public surface** for the xlsx-8 read-back CLIs:
two shim files (`xlsx2csv.py`, `xlsx2json.py`) + one shared in-skill
package (`xlsx2csv2json/` with 6 module files) + test scaffolding
with ONE smoke E2E that asserts hardcoded sentinel behaviour (Red →
Green on stubs per `tdd-stub-first §1`).

**Frozen surface contract (no later task may change these names):**
- Public symbols in `__all__`: `main`, `convert_xlsx_to_csv`,
  `convert_xlsx_to_json`, `_AppError`, `SelfOverwriteRefused`,
  `MultiTableRequiresOutputDir`, `MultiSheetRequiresOutputDir`,
  `HeaderRowsConflict`, `InvalidSheetNameForFsPath`,
  `OutputPathTraversal`, `FormatLockedByShim`, `PostValidateFailed`.
- Exception `CODE` attributes per ARCH §2.1 F6.
- Module file names: `__init__.py`, `cli.py`, `dispatch.py`,
  `emit_json.py`, `emit_csv.py`, `exceptions.py`.

## Changes Description

### New Files

#### `skills/xlsx/scripts/xlsx2csv.py` (≤ 60 LOC)

Body verbatim from [ARCHITECTURE.md §3.2 C1](../ARCHITECTURE.md):
shebang, docstring, `sys.path.insert(0, parent)` boilerplate, import
from `xlsx2csv2json` (all symbols), `if __name__ == "__main__": sys.exit(main(format_lock="csv"))`.

#### `skills/xlsx/scripts/xlsx2json.py` (≤ 60 LOC)

Body verbatim from ARCH §3.2 C2: identical structure to xlsx2csv.py
except docstring + `format_lock="json"` + `convert_xlsx_to_json` in
the re-export list.

#### `skills/xlsx/scripts/xlsx2csv2json/__init__.py`

```python
"""xlsx-8: read-back CLI body — emit .xlsx as CSV or JSON.

Thin emit-side glue on top of the xlsx-10.A `xlsx_read/` foundation.
See docs/TASK.md §1.4 for the honest-scope catalogue (filled in by
task 010-07).
"""
from __future__ import annotations

from .cli import main
from .exceptions import (
    _AppError,
    SelfOverwriteRefused,
    MultiTableRequiresOutputDir,
    MultiSheetRequiresOutputDir,
    HeaderRowsConflict,
    InvalidSheetNameForFsPath,
    OutputPathTraversal,
    FormatLockedByShim,
    PostValidateFailed,
)


def convert_xlsx_to_csv(input_path, output_path=None, **kwargs):  # noqa: D401
    """Public helper — convert .xlsx to CSV. See TASK §5.2.

    Stub returns sentinel `-999` until task 010-03 wires the CLI.
    """
    return -999  # SENTINEL_010_01


def convert_xlsx_to_json(input_path, output_path=None, **kwargs):  # noqa: D401
    """Public helper — convert .xlsx to JSON. See TASK §5.2.

    Stub returns sentinel `-999` until task 010-03 wires the CLI.
    """
    return -999  # SENTINEL_010_01


__all__ = [
    "main",
    "convert_xlsx_to_csv",
    "convert_xlsx_to_json",
    "_AppError",
    "SelfOverwriteRefused",
    "MultiTableRequiresOutputDir",
    "MultiSheetRequiresOutputDir",
    "HeaderRowsConflict",
    "InvalidSheetNameForFsPath",
    "OutputPathTraversal",
    "FormatLockedByShim",
    "PostValidateFailed",
]
```

#### `skills/xlsx/scripts/xlsx2csv2json/exceptions.py`

```python
"""Shim-level exception catalogue. CODE = exit code consumed by _errors.report_error."""
from __future__ import annotations


class _AppError(RuntimeError):
    CODE: int = 1


class SelfOverwriteRefused(_AppError):
    CODE = 6


class MultiTableRequiresOutputDir(_AppError):
    CODE = 2


class MultiSheetRequiresOutputDir(_AppError):
    CODE = 2


class HeaderRowsConflict(_AppError):
    CODE = 2


class InvalidSheetNameForFsPath(_AppError):
    CODE = 2


class OutputPathTraversal(_AppError):
    CODE = 2


class FormatLockedByShim(_AppError):
    CODE = 2


class PostValidateFailed(_AppError):
    CODE = 7
```

#### `skills/xlsx/scripts/xlsx2csv2json/cli.py`

```python
"""F1 — CLI argparse + dispatch. STUB ONLY in 010-01.

Body lands in 010-03 (argparse) + 010-04 (dispatch glue).
"""
from __future__ import annotations


def main(argv=None, *, format_lock=None):  # noqa: D401
    """Entry point — returns exit code.

    Stub returns sentinel `-999` until 010-03 wires argparse.
    """
    return -999  # SENTINEL_010_01
```

#### `skills/xlsx/scripts/xlsx2csv2json/dispatch.py`

```python
"""F2 — reader-glue. STUB ONLY in 010-01. Body lands in 010-04."""
from __future__ import annotations


def iter_table_payloads(args, reader):  # noqa: D401
    """Stub — returns empty list until 010-04 wires xlsx_read."""
    return []
```

#### `skills/xlsx/scripts/xlsx2csv2json/emit_json.py`

```python
"""F3 — JSON emitter. STUB ONLY in 010-01. Body lands in 010-05."""
from __future__ import annotations


def emit_json(*args, **kwargs):  # noqa: D401
    """Stub — returns sentinel `-999` until 010-05 wires shapes."""
    return -999  # SENTINEL_010_01
```

#### `skills/xlsx/scripts/xlsx2csv2json/emit_csv.py`

```python
"""F4 — CSV emitter. STUB ONLY in 010-01. Body lands in 010-06."""
from __future__ import annotations


def emit_csv(*args, **kwargs):  # noqa: D401
    """Stub — returns sentinel `-999` until 010-06 wires writers."""
    return -999  # SENTINEL_010_01
```

#### `skills/xlsx/scripts/xlsx2csv2json/tests/__init__.py`

Empty file.

#### `skills/xlsx/scripts/xlsx2csv2json/tests/conftest.py`

Empty file (kept for future fixtures).

#### `skills/xlsx/scripts/xlsx2csv2json/tests/test_smoke_stub.py`

```python
"""Smoke E2E for stage 1 — asserts hardcoded sentinel behaviour.

Per `tdd-stub-first §1`: this test passes on stubs and is **updated**
in later tasks to assert real behaviour.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class TestSkeletonStubs(unittest.TestCase):
    def test_package_importable(self):
        import xlsx2csv2json
        self.assertIsNotNone(xlsx2csv2json)

    def test_all_public_symbols_present(self):
        import xlsx2csv2json
        expected = {
            "main", "convert_xlsx_to_csv", "convert_xlsx_to_json",
            "_AppError", "SelfOverwriteRefused",
            "MultiTableRequiresOutputDir", "MultiSheetRequiresOutputDir",
            "HeaderRowsConflict", "InvalidSheetNameForFsPath",
            "OutputPathTraversal", "FormatLockedByShim",
            "PostValidateFailed",
        }
        self.assertEqual(set(xlsx2csv2json.__all__), expected)

    def test_exception_codes_locked(self):
        from xlsx2csv2json import (
            SelfOverwriteRefused, MultiTableRequiresOutputDir,
            MultiSheetRequiresOutputDir, HeaderRowsConflict,
            InvalidSheetNameForFsPath, OutputPathTraversal,
            FormatLockedByShim, PostValidateFailed,
        )
        self.assertEqual(SelfOverwriteRefused.CODE, 6)
        self.assertEqual(MultiTableRequiresOutputDir.CODE, 2)
        self.assertEqual(MultiSheetRequiresOutputDir.CODE, 2)
        self.assertEqual(HeaderRowsConflict.CODE, 2)
        self.assertEqual(InvalidSheetNameForFsPath.CODE, 2)
        self.assertEqual(OutputPathTraversal.CODE, 2)
        self.assertEqual(FormatLockedByShim.CODE, 2)
        self.assertEqual(PostValidateFailed.CODE, 7)

    def test_helpers_return_sentinel_in_stub_phase(self):
        from xlsx2csv2json import convert_xlsx_to_csv, convert_xlsx_to_json
        self.assertEqual(convert_xlsx_to_csv("ignored"), -999)
        self.assertEqual(convert_xlsx_to_json("ignored"), -999)

    def test_main_returns_sentinel_in_stub_phase(self):
        from xlsx2csv2json import main
        self.assertEqual(main([], format_lock="csv"), -999)


if __name__ == "__main__":
    unittest.main()
```

### Changes in Existing Files

— none.

### Component Integration

This task introduces a NEW component on top of the xlsx-10.A
foundation. No existing files are modified. The shims live alongside
`csv2xlsx.py` / `json2xlsx.py` and import the new package.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (smoke):** Run `python3 skills/xlsx/scripts/xlsx2csv.py --help`
   → exit 0 (Python's argparse prints something even with stub `main`
   if no flags wired; in stub state, main returns -999 BEFORE help is
   printed — so the help test is deferred to 010-03; in 010-01 the
   shim just imports and exits with sentinel).
   - **Input Data:** none
   - **Expected Result:** `python3 -c "import xlsx2csv2json; print(xlsx2csv2json.__all__)"` prints the 12-name list.
   - **Note:** At stub stage, sentinel result `-999` is expected from `main`.

### Unit Tests

1. **TC-UNIT-01:** `test_package_importable` — `import xlsx2csv2json` succeeds.
2. **TC-UNIT-02:** `test_all_public_symbols_present` — `__all__` matches the locked 12-name list.
3. **TC-UNIT-03:** `test_exception_codes_locked` — `CODE` per ARCH §2.1 F6.
4. **TC-UNIT-04:** `test_helpers_return_sentinel_in_stub_phase` — helpers return `-999`.
5. **TC-UNIT-05:** `test_main_returns_sentinel_in_stub_phase` — `main()` returns `-999`.

### Regression Tests

- Run `python3 -m unittest discover -s skills/xlsx/scripts/xlsx2csv2json/tests`
  — all green.
- Run existing xlsx test suites (xlsx-2, xlsx-3, xlsx-6, xlsx-7,
  xlsx-10.A) — no regression (this task does not modify existing
  code).
- Run `ruff check skills/xlsx/scripts/` — green (banned-api from
  xlsx-10.A respected; new package imports nothing from
  `xlsx_read._*`).

## Acceptance Criteria

- [ ] Two shims exist: `xlsx2csv.py` (≤ 60 LOC) and `xlsx2json.py` (≤ 60 LOC).
- [ ] Package directory `xlsx2csv2json/` exists with 6 module files + `tests/`.
- [ ] `__init__.py` declares `__all__` with exactly 12 names (locked).
- [ ] All 8 exception classes declared with `CODE` attribute per ARCH §2.1 F6.
- [ ] 5 unit tests in `test_smoke_stub.py` pass.
- [ ] `python3 -c "import xlsx2csv2json"` works.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] 12-line `diff -q` cross-skill gate silent (ARCH §9.4).
- [ ] No file under `skills/xlsx/scripts/xlsx_read/` modified.
- [ ] No file under `skills/xlsx/scripts/office/` modified.
- [ ] No `requirements.txt` / `pyproject.toml` / `install.sh` change.

## Notes

- **Strict-mode:** YES — every later task assumes the surface frozen
  here.
- The smoke test in `test_smoke_stub.py` IS the Phase-1 E2E per
  `tdd-stub-first §1`. Later tasks update / replace tests in this
  file as logic lands.
- The `sys.path.insert(0, parent)` boilerplate in the shims is
  REQUIRED — without it the package cannot resolve `_errors`
  (4-skill replicated file at `scripts/_errors.py`). Verified pattern
  from `json2xlsx.py:33`.

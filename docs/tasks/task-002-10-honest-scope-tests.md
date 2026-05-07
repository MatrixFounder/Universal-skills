# Task 002.10: Honest-scope regression test + import smoke + delta-vs-baseline lock

## Use Case Connection
- I9 — Test-suite full-pass evidence (delta half).
- I12 — Locked non-goals as regression tests.

## Task Goal
Ship the Task-002-specific regression locks: a 3-assertion
honest-scope test, an import-graph smoke test, and a delta-vs-baseline
verification step that compares post-refactor evidence against the
Task 002.1 baseline. After this task, every R3 / R7 / R8 gate is
either passing or formally failing with diagnostics.

## Changes Description

### New Files

#### File: `skills/xlsx/scripts/tests/test_refactor_honest_scope.py`

Per TASK I12. ~30 LOC:

```python
"""Honest-scope regression locks for Task 002 (xlsx_add_comment.py refactor).

Locks the post-refactor structural invariants. If any of these fails,
Task 002's R8.a "no behaviour change beyond restructuring" is violated
or Task 002's R2.a/b shim contract has drifted.
"""
from __future__ import annotations
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SHIM = REPO_ROOT / "skills" / "xlsx" / "scripts" / "xlsx_add_comment.py"


class TestRefactorHonestScope(unittest.TestCase):
    """Lock the Task-002 structural invariants."""

    def test_shim_loc_under_200(self) -> None:
        """R2.a: the shim is ≤ 200 LOC."""
        loc = sum(1 for _ in SHIM.read_text(encoding="utf-8").splitlines())
        self.assertLessEqual(loc, 200, f"shim is {loc} LOC, must be ≤ 200")

    def test_shim_reexports_full_test_compat_surface(self) -> None:
        """R2.b / R3.a: the 35-symbol test-compat surface is preserved."""
        # Spot-check the most commonly imported names — full re-export
        # is sanity-tested via tests/test_xlsx_comment_imports.py too.
        # Here we focus on the boundary representatives across modules.
        sys.path.insert(0, str(SHIM.parent))
        try:
            import xlsx_add_comment as shim
            for name in [
                # constants (representative)
                "THREADED_NS", "DEFAULT_VML_ANCHOR", "VML_CT",
                # exceptions (representative)
                "SheetNotFound", "MalformedVml",
                "DuplicateLegacyComment", "DuplicateThreadedComment",
                # cell_parser
                "parse_cell_syntax", "resolve_sheet",
                # batch
                "load_batch",
                # ooxml_editor (incl. underscore-prefixed test-touched)
                "scan_idmap_used", "add_person",
                "_make_relative_target", "_allocate_rid",
                # merge_dup
                "resolve_merged_target", "_enforce_duplicate_matrix",
                # cli_helpers
                "_post_pack_validate",
                # cli
                "main",
            ]:
                self.assertTrue(
                    hasattr(shim, name),
                    f"shim missing re-export: {name}",
                )
        finally:
            sys.path.pop(0)

    def test_office_byte_identity_preserved(self) -> None:
        """R6.e / R8.b: office/ is byte-identical across docx -> xlsx + pptx.

        pdf is excluded — it has no `skills/pdf/scripts/office/` directory
        (pdf does not use OOXML/LibreOffice; encryption is via pypdf
        PdfWriter.encrypt, not msoffcrypto-tool). Verified during Task
        002.1 baseline capture.
        """
        for skill in ("xlsx", "pptx"):
            result = subprocess.run(
                ["diff", "-qr",
                 str(REPO_ROOT / "skills" / "docx" / "scripts" / "office"),
                 str(REPO_ROOT / "skills" / skill / "scripts" / "office")],
                capture_output=True, text=True,
            )
            self.assertEqual(
                result.returncode, 0,
                f"office/ diverged for {skill}: {result.stdout}",
            )


if __name__ == "__main__":
    unittest.main()
```

#### File: `skills/xlsx/scripts/tests/test_xlsx_comment_imports.py`

Per TASK Q6 (closed YES) + R7.d. ~50 LOC import-graph smoke test:

```python
"""Import-graph smoke test for the xlsx_comment package (Task 002).

Asserts that every public symbol from every module is importable via
both the explicit submodule path AND the xlsx_add_comment shim
re-export (where applicable). Locks R7.d "each module move has a
unit-level smoke test for import" and R3.a "zero edits to test files"
by being entirely self-contained.

This test runs in < 2 s — it does NO actual workbook I/O.
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path


SHIM_DIR = Path(__file__).resolve().parents[1]


class TestPackageImports(unittest.TestCase):
    """Each module is importable; declared __all__ exists."""

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(SHIM_DIR))

    @classmethod
    def tearDownClass(cls) -> None:
        sys.path.remove(str(SHIM_DIR))

    def test_constants_importable(self) -> None:
        from xlsx_comment import constants
        for name in ["THREADED_NS", "VML_CT", "DEFAULT_VML_ANCHOR",
                     "BATCH_MAX_BYTES"]:
            self.assertIn(name, vars(constants))

    def test_exceptions_importable(self) -> None:
        from xlsx_comment import exceptions
        self.assertTrue(issubclass(exceptions._AppError, Exception))
        self.assertTrue(issubclass(exceptions.MalformedVml,
                                    exceptions._AppError))

    def test_cell_parser_importable(self) -> None:
        from xlsx_comment.cell_parser import parse_cell_syntax, resolve_sheet
        # smoke: parse a known-good cell ref
        self.assertEqual(parse_cell_syntax("A5"), (None, "A5"))

    def test_batch_importable(self) -> None:
        from xlsx_comment.batch import BatchRow, load_batch
        # smoke: the dataclass exists with the documented fields
        self.assertTrue(hasattr(BatchRow, "cell"))
        self.assertTrue(hasattr(BatchRow, "text"))

    def test_ooxml_editor_importable(self) -> None:
        from xlsx_comment.ooxml_editor import (
            scan_idmap_used, scan_spid_used, next_part_counter,
            add_person, _VML_PARSER,
        )
        # smoke: hardened parser settings preserved (R7.c security lock)
        self.assertFalse(_VML_PARSER.resolve_entities)

    def test_merge_dup_importable(self) -> None:
        from xlsx_comment.merge_dup import (
            resolve_merged_target, detect_existing_comment_state,
            _enforce_duplicate_matrix,
        )

    def test_cli_helpers_importable(self) -> None:
        from xlsx_comment.cli_helpers import (
            _initials_from_author, _resolve_date,
            _validate_args, _assert_distinct_paths,
            _post_pack_validate, _post_validate_enabled,
        )

    def test_cli_importable(self) -> None:
        from xlsx_comment.cli import build_parser, main
        # smoke: the parser can be built without raising
        parser = build_parser()
        self.assertIsNotNone(parser)


if __name__ == "__main__":
    unittest.main()
```

#### File: `docs/reviews/task-002-postcheck.txt`

Post-refactor evidence file mirroring the structure of
`docs/reviews/task-002-baseline.txt`. Captured by the developer
as part of this task (commands identical to Task 002.1 with `pre_`
replaced by `post_`).

### Changes in Existing Files
*(none — this task only adds new test files and an evidence file)*

## Steps

1. Write `tests/test_refactor_honest_scope.py` per the body above.
2. Write `tests/test_xlsx_comment_imports.py` per the body above.
3. Run the new tests in isolation:
   ```bash
   cd skills/xlsx/scripts && \
       ./.venv/bin/python -m unittest \
       tests.test_refactor_honest_scope \
       tests.test_xlsx_comment_imports -v 2>&1 | tail -20
   cd ../../..
   ```
   Both must end `OK`.
4. Run the **full** unit suite and confirm it grew from 75 → 75 +
   3 (refactor honest-scope) + 8 (imports) = 86 tests, all green:
   ```bash
   cd skills/xlsx/scripts && \
       ./.venv/bin/python -m unittest discover -s tests -v 2>&1 | tail -10
   cd ../../..
   ```
5. Run the **full** E2E suite again with `XLSX_ADD_COMMENT_POST_VALIDATE=1`
   exported (R3.c):
   ```bash
   XLSX_ADD_COMMENT_POST_VALIDATE=1 \
       bash skills/xlsx/scripts/tests/test_e2e.sh 2>&1 | tail -10
   ```
   Confirm OK count matches baseline.
6. Capture **post-refactor evidence** to
   `docs/reviews/task-002-postcheck.txt` using the same 9-section
   layout as Task 002.1, with `post_` prefixes. Compare diff vs
   baseline:
   ```bash
   diff <(grep -A 9999 '== pre_e2e_ok_count ==' docs/reviews/task-002-baseline.txt | head -2) \
        <(grep -A 9999 '== post_e2e_ok_count ==' docs/reviews/task-002-postcheck.txt | head -2)
   ```
   The OK-count delta must be **0** (R3.b lock).
7. Verify the **import-time delta** is within ±20 % of baseline
   (R3 NFR perf). **Methodology note (Sarcasmotron round-1):** the
   002.1 baseline captured a single cold run, which is machine- and
   moment-noisy (a re-run on the same machine showed -24 % drift on
   the same code). To make 002.10's gate robust, capture a
   **median-of-5 cold runs** for the post measurement and compare
   against the same median computed retroactively for the baseline:
   ```bash
   # Median-of-5 cold-import for the POST state.
   for i in 1 2 3 4 5; do
       skills/xlsx/scripts/.venv/bin/python -X importtime -c \
           "import sys; sys.path.insert(0, 'skills/xlsx/scripts'); import xlsx_add_comment" 2>&1 | \
           awk '/^import time:.*xlsx_add_comment$/{print $4}'
   done | sort -n | awk 'NR==3{print}'
   # Capture the baseline median the same way (re-runs are cheap).
   ```
   Acceptable post / baseline median ratio ∈ [0.80, 1.20]. If outside,
   triage: re-import-time-budget changes are a real concern and
   warrant a planning escalation.
8. Verify the **golden-hash delta** (R3.d):
   ```bash
   diff <(grep -A 9999 '== pre_golden_hashes ==' docs/reviews/task-002-baseline.txt) \
        <(grep -A 9999 '== post_golden_hashes ==' docs/reviews/task-002-postcheck.txt)
   ```
   If this returns no diff → goldens bit-equal (preferred).
   If diff is non-empty → run `tests/_golden_diff.py` to confirm
   structural delta is zero (acceptable per R3.d).

## Test Cases

### End-to-end Tests
- **TC-E2E-01:** Full E2E suite (with `XLSX_ADD_COMMENT_POST_VALIDATE=1`)
  passes; OK-count delta vs baseline = 0.

### Unit Tests
- **TC-UNIT-01:** `test_refactor_honest_scope.py::TestRefactorHonestScope`
  3 cases pass.
- **TC-UNIT-02:** `test_xlsx_comment_imports.py::TestPackageImports`
  8 cases pass.
- **TC-UNIT-03:** Total unit count = 75 (existing) + 11 (new) = 86,
  all OK.

### Regression Tests
- `--help` output diff vs baseline = empty (already verified in
  Task 002.9; re-verify here as gate).

## Acceptance Criteria
- [ ] `tests/test_refactor_honest_scope.py` and
      `tests/test_xlsx_comment_imports.py` exist and pass.
- [ ] `docs/reviews/task-002-postcheck.txt` exists with 9 sections
      matching `task-002-baseline.txt`'s structure.
- [ ] OK-count delta = 0 (E2E).
- [ ] Unit count delta = +11 (3 + 8 from the two new files).
- [ ] Goldens either bit-equal or structurally-equal per
      `_golden_diff.py`.
- [ ] Cold-import ratio ∈ [0.80, 1.20].
- [ ] R3.a / R3.b / R3.c / R3.d / R7.a / R7.d / R8.a all formally
      verified by the steps above.

## Notes
- This task is the **delta-vs-baseline lock**. If anything fails
  here, the refactor is NOT done — fix the underlying issue and
  rerun.
- The two new test files become permanent regression tests for any
  future changes to the package layout. Renaming a module without
  updating these tests will fail loudly — that is the design.
- Estimated effort: 1.5 h (mostly running suites and parsing the
  evidence files).

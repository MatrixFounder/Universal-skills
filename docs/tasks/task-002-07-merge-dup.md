# Task 002.7: Migrate `merge_dup.py` (F5)

## Use Case Connection
- I6 — Move F5 (merged-cell + duplicate-cell matrix).

## Task Goal
Move the F5 region (lines 1426–1583, merged-cell resolver +
duplicate-cell matrix) to `xlsx_comment/merge_dup.py`. Update the
shim re-imports.

## Changes Description

### New Files
*(none — `merge_dup.py` was created empty in Task 002.2)*

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_comment/merge_dup.py`

Replace the 1-line stub with:

- Module docstring (≤ 30 LOC):
  ```python
  """Merged-cell resolver and duplicate-cell matrix (F5).

  Migrated from `xlsx_add_comment.py` F5 region during Task 002.

  Public API:
      resolve_merged_target(sheet_xml_root, ref, allow_redirect, stderr)
          -> str
          Detect <mergeCell ref="A1:C3"> ranges; if `ref` is non-anchor,
          either raise MergedCellTarget (default) or return anchor
          (when allow_redirect=True, also emits info `MergedCellRedirect`
          to stderr).
      detect_existing_comment_state(legacy_root, threaded_root, ref) -> dict
          Inspect the input workbook's existing legacy + threaded
          parts on the target cell. Returns
          {has_legacy: bool, has_threaded: bool, thread_size: int}.
      _enforce_duplicate_matrix(state, threaded_mode, sheet_name, ref)
          -> None
          Implements ARCH §6.1 duplicate-cell behaviour matrix.
          Raises DuplicateLegacyComment / DuplicateThreadedComment
          per the (existing-state × mode) cells of the matrix.
  """
  ```
- `__all__`:
  ```python
  __all__ = [
      "resolve_merged_target",
      "detect_existing_comment_state",
      "_enforce_duplicate_matrix",
      "_parse_merge_range", "_anchor_of_range",  # private but used by
                                                  # ooxml_editor + tests
  ]
  ```
- Imports:
  ```python
  from __future__ import annotations
  import re
  import sys
  from lxml import etree  # type: ignore
  from .exceptions import (
      MergedCellTarget,
      DuplicateLegacyComment, DuplicateThreadedComment,
  )
  from .constants import SS_NS, THREADED_NS
  ```
- Body: byte-equivalent move of F5.

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

- **Delete** the F5 region (lines 1426–1583).
- **Insert** re-import (2 names on the test-compat surface):
  ```python
  from xlsx_comment.merge_dup import (  # noqa: F401
      resolve_merged_target, _enforce_duplicate_matrix,
  )
  ```
- Plus internal-only re-imports for symbols still needed by F6 in
  the shim:
  ```python
  # Internal-only — needed by F6 (single_cell_main / batch_main)
  # still in this file; removed when F6 migrates in Task 002.9.
  from xlsx_comment.merge_dup import (  # noqa: F401
      detect_existing_comment_state, _parse_merge_range, _anchor_of_range,
  )
  ```
- **Remove** any internal-only re-imports from the F4 block (Task
  002.6) that F5's own code was using and are no longer referenced
  in the shim. Audit by `grep -n "function_name" xlsx_add_comment.py`
  for each name listed in the temp block of Task 002.6.

### Component Integration
- `merge_dup.py` depends on `constants.py` + `exceptions.py`.
- It does NOT import from `ooxml_editor.py` (verify against the
  original F5 — the F5 region is XML-only, no part-creation calls).
  *If F5 actually does call into F4, the developer adds
  `from .ooxml_editor import …` and the LOC budget rises slightly.*

## Test Cases

### End-to-end Tests
- **TC-E2E-01:** Re-run E2E. All 112 checks green. Specifically:
  `T-merged-cell-anchor-passthrough`, `T-merged-cell-redirect`,
  `T-merged-cell-target` (the R6 fail-fast case),
  `T-duplicate-threaded-append`, `T-DuplicateLegacyComment`,
  `T-DuplicateThreadedComment` pass.

### Unit Tests
- **TC-UNIT-01:** `Test*MergedCell*` and `Test*DuplicateMatrix*`
  cases pass unchanged. `tests/test_xlsx_add_comment.py::test_legacy_only_no_threaded_raises`
  and `test_threaded_exists_no_threaded_raises` directly call
  `_enforce_duplicate_matrix` from the shim — must still work.

### Regression Tests
- Per per-task micro-cycle: unit + E2E green.

## Acceptance Criteria
- [ ] `xlsx_comment/merge_dup.py` ≤ 200 LOC.
- [ ] `xlsx_add_comment.py` F5 region replaced by re-imports.
- [ ] R4.b lock holds.
- [ ] All 75 unit + 112 E2E green.
- [ ] `validate_skill.py skills/xlsx` exits 0.

## Notes
- The duplicate-cell matrix is a load-bearing piece of the public
  CLI contract (DuplicateLegacyComment / DuplicateThreadedComment
  exit-2 envelopes). ANY change to the matrix is a behaviour change
  and a hard violation of R8.a.
- Estimated effort: 1 h.

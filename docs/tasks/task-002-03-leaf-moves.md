# Task 002.3: Migrate `constants.py` and `exceptions.py` (zero-dep leaves)

## Use Case Connection
- I2 — Migrate the two leaf modules with zero internal dependencies first.

## Task Goal
Move the F-Constants region (lines 140–178) and the F-Errors region
(lines 181–356) from `xlsx_add_comment.py` into the package's two
zero-dep leaf modules. Update `xlsx_add_comment.py` so the moved
symbols are re-imported (preserving the test-compat surface). Tests
remain green.

## Changes Description

### New Files
*(none — files were created empty in Task 002.2; this task fills them)*

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_comment/constants.py`

Replace the 1-line stub with the **byte-equivalent** content of the
F-Constants region from `xlsx_add_comment.py` (lines 140–178), with:

- The `# region — Namespaces and content-type constants` line replaced
  by a module docstring (≤ 30 LOC per R5.a):
  ```python
  """XML namespaces, OOXML rel-types, content-types, and editor-wide
  constants used by the xlsx_comment package.

  Migrated from `xlsx_add_comment.py` F-Constants region during Task 002
  (module split). Verbatim move — no value changes. The constants are
  consumed by every other module in the package; this is the canonical
  source of truth.
  """
  ```
- The `# endregion` line dropped.
- Add an explicit `__all__` enumerating every public name (R4.a):
  ```python
  __all__ = [
      "SS_NS", "R_NS", "PR_NS", "CT_NS", "V_NS", "O_NS", "X_NS",
      "THREADED_NS",
      "COMMENTS_REL_TYPE", "COMMENTS_CT",
      "VML_REL_TYPE", "VML_CT",
      "THREADED_REL_TYPE", "THREADED_CT",
      "PERSON_REL_TYPE", "PERSON_CT",
      "DEFAULT_VML_ANCHOR",
      "BATCH_MAX_BYTES",
  ]
  ```

#### File: `skills/xlsx/scripts/xlsx_comment/exceptions.py`

Replace the 1-line stub with the byte-equivalent content of the
F-Errors region (lines 181–356) with:

- The `# region — Local exception classes …` line replaced by a
  module docstring (≤ 30 LOC):
  ```python
  """Typed exceptions raised across the xlsx_comment package.

  Migrated from `xlsx_add_comment.py` F-Errors region during Task 002.

  Hierarchy: `_AppError` (private base) → 14 typed leaves (UsageError,
  SheetNotFound, NoVisibleSheet, InvalidCellRef, MergedCellTarget,
  EmptyCommentBody, InvalidBatchInput, BatchTooLarge,
  MissingDefaultAuthor, DuplicateLegacyComment, DuplicateThreadedComment,
  SelfOverwriteRefused, OutputIntegrityFailure, MalformedVml).

  Each typed leaf carries class attributes `code` (exit code) and
  `envelope_type` (JSON envelope `type` field). The unified handler
  in `cli.main()` reads them and routes through `_errors.report_error`.

  Exception classes that take envelope-detail args
  (DuplicateLegacyComment, DuplicateThreadedComment, MergedCellTarget)
  preserve the (message, sheet, cell[, existing_thread_size])
  constructor signature — they are tested directly via the shim
  re-export, so ANY constructor change is a behaviour change forbidden
  by R8.a.
  """
  ```
- `# endregion` dropped.
- `__all__` lists all 15 names (the base + 14 typed leaves):
  ```python
  __all__ = [
      "_AppError",  # exposed for cross-module isinstance + tests
      "UsageError", "SheetNotFound", "NoVisibleSheet", "InvalidCellRef",
      "MergedCellTarget", "EmptyCommentBody", "InvalidBatchInput",
      "BatchTooLarge", "MissingDefaultAuthor",
      "DuplicateLegacyComment", "DuplicateThreadedComment",
      "SelfOverwriteRefused", "OutputIntegrityFailure", "MalformedVml",
  ]
  ```
  *(Note: `_AppError` IS in `__all__` despite the leading underscore
  — the name is used by other package modules' `except _AppError:`
  clauses and by `cli.main()`'s unified error handler. R4.a's
  "no leading-underscore symbols cross-module" rule has this single
  documented exception, called out in TASK §2.5 "Underscore-prefixed
  symbols on the list".)*

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

- **Delete** the F-Constants region (lines 140–178 inclusive of the
  `# region` and `# endregion` markers).
- **Delete** the F-Errors region (lines 181–356).
- **Insert**, immediately after the `from lxml import etree` import
  block (around current line 138), TWO re-import blocks (mirrors the
  "public + internal-only temp" pattern documented for Tasks 002.6
  / 002.7 / 002.8):

  **Public block — final TASK §2.5 contract (9 + 10 = 19 names):**
  ```python
  # --- Task-002 module-split: PUBLIC re-exports from xlsx_comment ---
  # These names are on the test-compat shim surface (TASK §2.5 — frozen
  # 35-symbol list). They must remain even after F4–F6 migrate out.
  from xlsx_comment.constants import (  # noqa: F401
      SS_NS, PR_NS, CT_NS, V_NS, O_NS, X_NS,
      THREADED_NS, VML_CT, DEFAULT_VML_ANCHOR,
  )
  from xlsx_comment.exceptions import (  # noqa: F401
      SheetNotFound, NoVisibleSheet, InvalidCellRef,
      MergedCellTarget, InvalidBatchInput, BatchTooLarge,
      DuplicateLegacyComment, DuplicateThreadedComment,
      OutputIntegrityFailure, MalformedVml,
  )
  ```

  **Internal-only temp block — pruned in 002.9 once F6 leaves:**
  ```python
  # --- Internal-only — referenced by F2/F3/F4/F5/F6 regions still in
  # this file. NOT on the public re-export contract; will be PRUNED
  # in Task 002.9 once cli.py absorbs F1+F6. Mirrors the same pattern
  # used by Tasks 002.6 / 002.7 / 002.8.
  from xlsx_comment.constants import (  # noqa: F401
      R_NS,  # used by F4 rels patches
      COMMENTS_REL_TYPE, COMMENTS_CT,
      VML_REL_TYPE,
      THREADED_REL_TYPE, THREADED_CT,
      PERSON_REL_TYPE, PERSON_CT,
      BATCH_MAX_BYTES,
  )
  from xlsx_comment.exceptions import (  # noqa: F401
      _AppError,
      UsageError, EmptyCommentBody, MissingDefaultAuthor,
      SelfOverwriteRefused,
  )
  ```

  *(The remaining F2–F6 regions in `xlsx_add_comment.py` continue to
  use these names without modification — they resolve via the
  re-imports.)*

  **Pruning checklist for Task 002.9** (developer verifies at the
  shim-reduction step): every name in the **internal-only** block
  above MUST be unreferenced in the final shim and removed. The
  **public** block stays.

### Component Integration
- `xlsx_comment/cell_parser.py`, `batch.py`, `ooxml_editor.py`,
  `merge_dup.py`, `cli_helpers.py`, `cli.py` are **still empty stubs**
  at the end of this task (their content arrives in Tasks 002.4–002.9).
  They do NOT yet import from `constants` / `exceptions` because they
  are empty — but the imports they will need are now available.
- `xlsx_add_comment.py` now `import`s from `xlsx_comment.constants` and
  `xlsx_comment.exceptions`. **No other internal restructuring** in
  this task.

## Test Cases

### End-to-end Tests
- **TC-E2E-01:** Re-run `bash skills/xlsx/scripts/tests/test_e2e.sh`.
  All 112 checks must remain green.

### Unit Tests
- **TC-UNIT-01:** Existing tests that import `THREADED_NS`, `SS_NS`,
  `CT_NS`, `V_NS`, `O_NS`, `X_NS`, `PR_NS`, `VML_CT`,
  `DEFAULT_VML_ANCHOR` from `xlsx_add_comment` must pass unchanged
  (R3.a — zero edits to test files).
- **TC-UNIT-02:** Existing tests that import `MalformedVml`,
  `InvalidCellRef`, `SheetNotFound`, `NoVisibleSheet`,
  `MergedCellTarget`, `BatchTooLarge`, `InvalidBatchInput`,
  `OutputIntegrityFailure`, `DuplicateLegacyComment`,
  `DuplicateThreadedComment` must pass unchanged.
- **TC-UNIT-03:** New cross-package import smoke (developer sanity
  check, NOT yet a committed test — the formal smoke test ships in
  Task 002.10):
  ```bash
  cd skills/xlsx/scripts && ./.venv/bin/python -c \
      "from xlsx_comment.constants import THREADED_NS, DEFAULT_VML_ANCHOR;
       from xlsx_comment.exceptions import _AppError, MalformedVml;
       assert _AppError.__module__ == 'xlsx_comment.exceptions'"
  ```
  Exits 0.

### Regression Tests
- Per the per-task micro-cycle in PLAN.md: run unit + E2E. Both must
  match the baseline counts captured in Task 002.1.

## Acceptance Criteria
- [ ] `xlsx_comment/constants.py` ≤ 60 LOC; carries the docstring +
      `__all__` + the 18 constant assignments.
- [ ] `xlsx_comment/exceptions.py` ≤ 220 LOC; carries the docstring +
      `__all__` + `_AppError` + 14 typed exception classes.
- [ ] `xlsx_add_comment.py` lines 140–356 (the two regions) are
      replaced by a single explicit re-import block.
- [ ] `git diff xlsx_add_comment.py` shows ONLY the deletion of the
      two regions + the insertion of the re-import block — no
      re-indentation of any other code.
- [ ] R4.b lock: `grep -nE 'from xlsx_add_comment' xlsx_comment/*.py`
      returns NO matches (the package never imports through the shim).
- [ ] All 75 unit tests pass; all 112 E2E pass.
- [ ] `validate_skill.py skills/xlsx` exits 0.

## Notes
- **Verbatim-move discipline (R7.c):** when copying the region body,
  do NOT touch indentation, blank-line patterns, or in-line `# NOTE`
  / `# XXX` comments. The tool of choice is straight cut-paste, NOT
  any auto-format tooling.
- **`_AppError` exception note:** the `@property details` definition
  on `_AppError` and the per-subclass `details` overrides MUST move
  byte-equivalent. ANY change to the `details` shape is a behaviour
  change (the JSON envelope `details` field is part of the public
  contract).
- Estimated effort: 1.5 h — the largest fraction is verifying the
  re-import surface manually before running tests.

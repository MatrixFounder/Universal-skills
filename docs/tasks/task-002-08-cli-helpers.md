# Task 002.8: Migrate `cli_helpers.py` (F-Helpers + Q3 move)

## Use Case Connection
- I7 — Move the cross-cutting glue.

## Task Goal
Move the F-Helpers region (lines 1586–1663) AND the F6 fragments
that ARCHITECTURE §8 Q3 reassigns to helpers
(`_post_pack_validate`, `_post_validate_enabled`,
`_content_types_path`) from `xlsx_add_comment.py` to
`xlsx_comment/cli_helpers.py`.

## Changes Description

### New Files
*(none — `cli_helpers.py` was created empty in Task 002.2)*

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_comment/cli_helpers.py`

Replace the 1-line stub with:

- Module docstring (≤ 30 LOC):
  ```python
  """Pure utilities used by cli.py: validation, date, post-pack guard.

  Migrated from `xlsx_add_comment.py` F-Helpers region (lines
  1586-1663) during Task 002, plus F6 fragments per ARCH §8 Q3
  (`_post_pack_validate`, `_post_validate_enabled`,
  `_content_types_path`).

  Public API (all `_`-prefixed; tests + cli.py call directly):
      _initials_from_author(name) -> str
      _resolve_date(arg) -> str (ISO-8601)
      _validate_args(args) -> None  (raises UsageError on MX/DEP violations)
      _assert_distinct_paths(input_path, output_path) -> None
      _content_types_path(tree_root_dir) -> Path
      _post_validate_enabled() -> bool  (env-var gate)
      _post_pack_validate(output_path) -> None  (raises OutputIntegrityFailure)
  """
  ```
- `__all__`:
  ```python
  __all__ = [
      "_initials_from_author", "_resolve_date",
      "_validate_args", "_assert_distinct_paths",
      "_content_types_path",
      "_post_validate_enabled", "_post_pack_validate",
  ]
  ```
- Imports:
  ```python
  from __future__ import annotations
  import os
  import subprocess
  import sys
  from datetime import datetime, timezone
  from pathlib import Path
  from .exceptions import (
      UsageError, SelfOverwriteRefused, OutputIntegrityFailure,
  )
  ```
  *(Trim against the actual moved code — the developer pares to
  what's used.)*
- Body: byte-equivalent move of F-Helpers + the three F6 fragments.

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

- **Delete** the F-Helpers region (lines 1586–1663).
- **Delete** the F6 fragments (`_content_types_path`,
  `_post_validate_enabled`, `_post_pack_validate` — currently at lines
  1764–1844 inside the F6 region).
- **Insert** re-imports: only `_post_pack_validate` is on the
  test-compat shim contract (TASK §2.5 `cli_helpers` row, 1 name).
  But `_validate_args`, `_assert_distinct_paths`, `_resolve_date`,
  `_initials_from_author`, `_content_types_path`,
  `_post_validate_enabled` are also called by the F6 region still in
  the shim — so an internal-only block too:
  ```python
  from xlsx_comment.cli_helpers import _post_pack_validate  # noqa: F401
  # Internal-only — needed by F6 still in this file; removed when
  # F6 migrates in Task 002.9.
  from xlsx_comment.cli_helpers import (  # noqa: F401
      _initials_from_author, _resolve_date,
      _validate_args, _assert_distinct_paths,
      _content_types_path, _post_validate_enabled,
  )
  ```

### Component Integration
- `cli_helpers.py` depends on `exceptions.py` only (Stage 1 leaf).
- F6 (still in shim) calls every function listed; internal-only
  re-imports satisfy these references until Task 002.9 migrates F6 out.

## Test Cases

### End-to-end Tests
- **TC-E2E-01:** Re-run E2E. All 112 checks green. Specifically:
  `T-real-failure-unlinks-output`, `T-truthy-zero-treated-as-off`,
  `T-truthy-alternates-treated-as-on`,
  `T-xlsm-unknown-extension-treated-as-no-op`,
  the integrity-pair invocations on the 17 sites that export
  `XLSX_ADD_COMMENT_POST_VALIDATE=1`.

### Unit Tests
- **TC-UNIT-01:** `Test*PostPackValidate*` and any
  `Test*ValidateArgs*` cases pass unchanged.
- **TC-UNIT-02:** `tests/test_xlsx_add_comment.py::test_post_pack_validate_*`
  imports `_post_pack_validate` from the shim — must still work.

### Regression Tests
- Per per-task micro-cycle: unit + E2E green.

## Acceptance Criteria
- [ ] `xlsx_comment/cli_helpers.py` ≤ 150 LOC.
- [ ] `xlsx_add_comment.py` F-Helpers region + the three F6 fragments
      are deleted; replaced by re-imports.
- [ ] `_post_pack_validate` is on the public re-export contract
      (TASK §2.5).
- [ ] R4.b lock holds.
- [ ] All 75 unit + 112 E2E green.
- [ ] `validate_skill.py skills/xlsx` exits 0.

## Notes
- `_post_validate_enabled()` reads
  `os.environ.get("XLSX_ADD_COMMENT_POST_VALIDATE")`. The truthy
  allowlist `{"1", "true", "yes", "on"}` MUST move byte-equivalent —
  see session-state recent-decisions: *"_post_validate_enabled()
  truthy allowlist (1/true/yes/on)"*.
- `_post_pack_validate` invokes `office/validate.py` via
  `subprocess.run(env=…)` — that env override (which mutes
  `XLSX_ADD_COMMENT_POST_VALIDATE` during the inner call to prevent
  recursion) MUST move byte-equivalent. See session-state:
  *"subprocess.run env= overrides POST_VALIDATE for hermeticity"*.
- Estimated effort: 1 h.

# Task 002.9: Migrate `cli.py` (F1+F6 merged) AND reduce shim to ≤200 LOC

## Use Case Connection
- I8 — Move CLI orchestration AND reduce the shim.

## Task Goal
Move the F1 region (lines 1666–1757, `build_parser`) AND the F6
region remainders (lines 1846–2334, `main`, `single_cell_main`,
`batch_main`) from `xlsx_add_comment.py` to `xlsx_comment/cli.py`
as a **single merged module** per ARCHITECTURE §8 Q2=A. Reduce
`xlsx_add_comment.py` to a ≤ 200 LOC shim that **only**:
1. Re-exports the canonical 35-symbol test-compat surface (TASK §2.5).
2. Calls `xlsx_comment.cli.main()` from `if __name__ == "__main__"`.

## Changes Description

### New Files
*(none — `cli.py` was created empty in Task 002.2)*

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_comment/cli.py`

Replace the 1-line stub with:

- Module docstring (≤ 30 LOC):
  ```python
  """argparse + main + single_cell_main + batch_main (F1+F6 merged per Q2=A).

  Migrated from `xlsx_add_comment.py` F1 region (lines 1666-1757)
  and F6 region (lines 1846-2334) during Task 002.

  Public API:
      build_parser() -> argparse.ArgumentParser
      main(argv: list[str] | None = None) -> int
  Internal:
      single_cell_main, batch_main — orchestration sub-routines.

  Per ARCH §8 Q2=A: F1 (argparse) and F6 (main + dispatchers) are
  KEPT MERGED. The state-sharing between argparse, MX/DEP validation,
  and the unified _AppError handler in main() makes splitting them
  produce a 90-LOC argparse stub that adds an import hop with zero
  coupling reduction.
  """
  ```
- `__all__`:
  ```python
  __all__ = ["build_parser", "main", "single_cell_main", "batch_main"]
  ```
- Imports (this is the heaviest import set — pulls every package module):
  ```python
  from __future__ import annotations
  import argparse
  import sys
  import tempfile
  from datetime import datetime, timezone
  from pathlib import Path
  from lxml import etree  # type: ignore

  # Cross-skill helpers
  from _errors import add_json_errors_argument, report_error
  from office._encryption import EncryptedFileError, assert_not_encrypted
  from office._macros import warn_if_macros_will_be_dropped
  from office.pack import pack
  from office.unpack import unpack

  # Package internals (sibling-relative per R4.b)
  from .constants import (
      # whatever subset cli.py uses
  )
  from .exceptions import (
      _AppError,
      UsageError, EmptyCommentBody, SelfOverwriteRefused,
      DuplicateLegacyComment, DuplicateThreadedComment,
      MissingDefaultAuthor,
      # ... full subset reconciled against the F1/F6 body
  )
  from .cell_parser import parse_cell_syntax, resolve_sheet
  from .batch import BatchRow, load_batch
  from .ooxml_editor import (
      _Allocation, _allocate_new_parts,
      _resolve_target, _sheet_part_path, _sheet_rels_path,
      ensure_legacy_comments_part, add_legacy_comment,
      ensure_vml_drawing, add_vml_shape,
      ensure_threaded_comments_part, ensure_person_list,
      add_person, add_threaded_comment,
      _patch_content_types,
      # full subset reconciled against the F1/F6 body
  )
  from .merge_dup import (
      resolve_merged_target, detect_existing_comment_state,
      _enforce_duplicate_matrix,
  )
  from .cli_helpers import (
      _initials_from_author, _resolve_date,
      _validate_args, _assert_distinct_paths,
      _content_types_path,
      _post_validate_enabled, _post_pack_validate,
  )
  ```
  *(The exact import set reconciles against what F1/F6 actually
  reference; the developer prunes unused names.)*
- Also: F6 originally imports `tempfile` as `_tempfile`; preserve
  that alias verbatim or change to `tempfile` consistently — but
  pick ONE and use it everywhere. Recommendation: `import tempfile`
  with use as `tempfile.TemporaryDirectory(...)`. The `_tempfile`
  alias in the original was just to avoid a name conflict; if that
  conflict no longer exists in the migrated module, drop the alias.
  This is a **micro-style** change, not a behaviour change — but
  flag it in the task PR description for the reviewer.
- Body: byte-equivalent move of F1 (build_parser, ~91 LOC) followed
  by the F6 body (single_cell_main, batch_main, main — ~580 LOC).

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

**Reduce to a ≤ 200 LOC shim.** The final structure is:

```python
#!/usr/bin/env python3
"""Insert a Microsoft Excel comment into a target cell of a .xlsx workbook.

Thin shim — implementation lives in the `xlsx_comment` package next
to this file. See `xlsx_comment/cli.py` for the entry point and
`xlsx_comment/{constants,exceptions,cell_parser,batch,ooxml_editor,
merge_dup,cli_helpers}.py` for the F1-F6 components.

This shim exists to:
  1. Provide a single user-facing entry point (`xlsx_add_comment.py`).
  2. Re-export the 35-symbol test-compat surface so the existing
     test suite at tests/test_xlsx_add_comment.py works without edits
     (TASK 002 R3.a contract — frozen list at TASK §2.5).

Honest-scope and architecture-locked decisions are documented in
`xlsx_comment/cli.py` and `docs/ARCHITECTURE.md` §6 / §7 / §8;
they are NOT duplicated here to avoid drift.
"""
from __future__ import annotations

import sys

# === Test-compat re-exports (TASK §2.5 — 35 symbols across 8 modules) ===
# DO NOT add or remove names here without updating TASK §2.5 first.
# DO NOT import through this shim from inside the xlsx_comment package
# (that would create a re-import cycle — TASK R4.b).

from xlsx_comment.constants import (  # noqa: F401
    SS_NS, PR_NS, CT_NS, V_NS, O_NS, X_NS,
    THREADED_NS, VML_CT, DEFAULT_VML_ANCHOR,
)
# Note: R_NS is NOT in this list — it is defined in
# xlsx_comment.constants but is not test-imported (verified by grep
# against tests/test_xlsx_add_comment.py — zero matches). Including
# it would push the shim re-export count to 36 and contradict the
# TASK §2.5 35-symbol contract. If a future test imports R_NS, add
# it here AND update TASK §2.5.
from xlsx_comment.exceptions import (  # noqa: F401
    SheetNotFound, NoVisibleSheet, InvalidCellRef,
    MergedCellTarget, InvalidBatchInput, BatchTooLarge,
    DuplicateLegacyComment, DuplicateThreadedComment,
    OutputIntegrityFailure, MalformedVml,
)
from xlsx_comment.cell_parser import (  # noqa: F401
    parse_cell_syntax, resolve_sheet,
)
from xlsx_comment.batch import load_batch  # noqa: F401
from xlsx_comment.ooxml_editor import (  # noqa: F401
    next_part_counter, scan_idmap_used, scan_spid_used,
    add_person, add_legacy_comment, add_vml_shape,
    _make_relative_target, _allocate_rid, _patch_content_types,
)
from xlsx_comment.merge_dup import (  # noqa: F401
    resolve_merged_target, _enforce_duplicate_matrix,
)
from xlsx_comment.cli_helpers import _post_pack_validate  # noqa: F401
from xlsx_comment.cli import main  # noqa: F401


if __name__ == "__main__":
    sys.exit(main())
```

**Total LOC after this task:** ~80 (well below the ≤ 200 cap).

### Component Integration
- All 8 implementation modules of `xlsx_comment/` now hold the
  complete F1–F6 implementation.
- `xlsx_add_comment.py` is the single user-facing entry point.
- The remaining temp re-imports added in Tasks 002.6 / 002.7 / 002.8
  are no longer needed (F4/F5/F6 internal-only references all live
  inside the package now); the shim's import block is exactly the
  35-symbol test-compat surface plus `main`.

## Test Cases

### End-to-end Tests
- **TC-E2E-01:** Re-run full E2E. All 112 checks must remain green.
- **TC-E2E-02:** `python3 skills/xlsx/scripts/xlsx_add_comment.py --help`
  produces output **byte-identical** to the `pre_help_output` section
  of `docs/reviews/task-002-baseline.txt`. Verification:
  ```bash
  cd skills/xlsx/scripts && \
      ./.venv/bin/python xlsx_add_comment.py --help 2>&1 \
      > /tmp/help_post.txt
  awk '/== pre_help_output ==/{flag=1; next} /^== /{flag=0} flag' \
      ../../../docs/reviews/task-002-baseline.txt > /tmp/help_pre.txt
  diff /tmp/help_pre.txt /tmp/help_post.txt && echo "BYTE EQUAL"
  ```
  Must print `BYTE EQUAL`.

### Unit Tests
- **TC-UNIT-01:** All 75 existing unit tests pass without edits.
- **TC-UNIT-02:** Specifically `test_xlsx_add_comment.py::test_main_*`
  cases that import `main` from the shim must still work.

### Regression Tests
- `wc -l skills/xlsx/scripts/xlsx_add_comment.py` ≤ 200 (R2.a hard
  gate).
- `git diff --stat` shows the F1/F6 deletion + cli.py creation +
  shim reduction; nothing else.

## Acceptance Criteria
- [ ] `xlsx_comment/cli.py` ≤ 700 LOC (target). **Budget escape valve (m1 from review):** if the realistic landing is 700–750 LOC because the docstring + `__all__` + heavy import block consumes 70–90 LOC of the budget, the developer MAY tighten the import block (drop unused names, fold multi-line imports) before declaring R1.j done. If still over 750 LOC, raise it as a planning escalation rather than over-aggressively splitting — the Q2=A "merged" decision is an architecture-locked invariant.
- [ ] `xlsx_add_comment.py` ≤ 200 LOC (target ~80 per the structure
      above).
- [ ] `--help` output byte-identical to baseline.
- [ ] All 75 unit + 112 E2E green.
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] `xlsx_add_comment.py` is still executable (`-rwxr-xr-x`); the
      shebang is preserved (R2.d).
- [ ] R4.b lock: `grep -nE 'from xlsx_add_comment' xlsx_comment/*.py`
      empty.

## Notes
- This is the second-largest move (~700 LOC). Estimated effort: 2 h.
- The `if __name__ == "__main__":` block at the bottom of the shim
  is the SINGLE call site of `main()` from a user perspective. The
  package's `cli.main()` is also callable programmatically via
  `from xlsx_comment.cli import main`.
- After this task, the package is **complete** in terms of
  F1–F6 placement. Tasks 002.10 + 002.11 add tests, docs, and the
  final repo-health gates.

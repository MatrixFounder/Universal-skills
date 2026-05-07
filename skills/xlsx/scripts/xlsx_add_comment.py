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

Usage and honest-scope details: see `xlsx_comment/cli.py` docstring,
`docs/ARCHITECTURE.md` §6/§7/§8, and `references/comments-and-threads.md`.
"""
from __future__ import annotations

import subprocess as _subprocess  # noqa: F401  # mock.patch target in tests/test_xlsx_add_comment.py::TestPostValidateGuard
import sys

# === Test-compat re-exports (TASK §2.5 — 35 symbols across 8 modules) ===
# DO NOT add or remove names here without updating TASK §2.5 first.
# DO NOT import through this shim from inside the xlsx_comment package
# (that would create a re-import cycle — TASK R4.b).

# constants (9)
from xlsx_comment.constants import (  # noqa: F401
    SS_NS, PR_NS, CT_NS, V_NS, O_NS, X_NS,
    THREADED_NS, VML_CT, DEFAULT_VML_ANCHOR,
)
# exceptions (10)
from xlsx_comment.exceptions import (  # noqa: F401
    SheetNotFound, NoVisibleSheet, InvalidCellRef,
    MergedCellTarget, InvalidBatchInput, BatchTooLarge,
    DuplicateLegacyComment, DuplicateThreadedComment,
    OutputIntegrityFailure, MalformedVml,
)
# cell_parser (2)
from xlsx_comment.cell_parser import (  # noqa: F401
    parse_cell_syntax, resolve_sheet,
)
# batch (1) — BatchRow intentionally NOT re-exported (Q5 closure).
from xlsx_comment.batch import load_batch  # noqa: F401
# ooxml_editor (9 — incl. 3 underscore-prefixed test-touched helpers)
from xlsx_comment.ooxml_editor import (  # noqa: F401
    next_part_counter, scan_idmap_used, scan_spid_used,
    add_person, add_legacy_comment, add_vml_shape,
    _make_relative_target, _allocate_rid, _patch_content_types,
)
# merge_dup (2 — incl. 1 underscore-prefixed test-touched helper)
from xlsx_comment.merge_dup import (  # noqa: F401
    resolve_merged_target, _enforce_duplicate_matrix,
)
# cli_helpers (1)
from xlsx_comment.cli_helpers import _post_pack_validate  # noqa: F401
# cli (1)
from xlsx_comment.cli import main  # noqa: F401


if __name__ == "__main__":
    sys.exit(main())

# Task 002.5: Migrate `batch.py` (F3)

## Use Case Connection
- I4 — Move F3 (BatchRow + load_batch).

## Task Goal
Move the F3 region (lines 519–644, batch loader + `BatchRow`
dataclass) from `xlsx_add_comment.py` to `xlsx_comment/batch.py`.
Update the shim to re-import the public names.

## Changes Description

### New Files
*(none — `batch.py` was created empty in Task 002.2)*

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_comment/batch.py`

Replace the 1-line stub with:

- Module docstring (≤ 30 LOC):
  ```python
  """--batch input loader: BatchRow dataclass + load_batch (F3).

  Migrated from `xlsx_add_comment.py` F3 region during Task 002.

  Public API:
      BatchRow            — dataclass(cell, text, author, initials, threaded).
      load_batch(path_or_dash, default_author, default_threaded,
                 stderr) -> list[BatchRow]
          Reads --batch JSON (or stdin via "-"), enforces 8 MiB
          pre-parse cap (BatchTooLarge), auto-detects flat-array vs
          xlsx-7 envelope shape (InvalidBatchInput on anything else),
          hydrates uniformly to BatchRow list. Skips group-findings
          (`row: null`) and counts them in the stderr summary.

  Per TASK 002 §2.5 row 5, BatchRow is NOT re-exported on the
  xlsx_add_comment.py shim (Q5 closure — programmatic callers use
  the explicit `from xlsx_comment.batch import BatchRow` path).
  Only `load_batch` is on the shim re-export contract.
  """
  ```
- `__all__ = ["BatchRow", "load_batch"]`.
- Imports:
  ```python
  from __future__ import annotations
  import json
  import sys
  from dataclasses import dataclass
  from pathlib import Path
  from .exceptions import (
      BatchTooLarge, InvalidBatchInput, MissingDefaultAuthor,
  )
  from .constants import BATCH_MAX_BYTES
  ```
- Body: byte-equivalent move of the F3 region.

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

- **Delete** the F3 region (lines 519–644).
- **Insert** re-import after the `cell_parser` re-import:
  ```python
  from xlsx_comment.batch import load_batch  # noqa: F401
  # (BatchRow is intentionally NOT re-exported — TASK §2.5 Q5.)
  ```

### Component Integration
- `batch.py` depends on `constants.py` + `exceptions.py` only.
- F6 (`batch_main`, still in `xlsx_add_comment.py` until Task 002.9)
  references `load_batch` (resolved via the new public re-import)
  and consumes `BatchRow` instances — but **only via attribute
  access** (`row.cell`, `row.text`, `row.author`, `row.threaded`,
  `row.initials`). No `BatchRow(...)` construction; no
  `isinstance(x, BatchRow)` check. Therefore Python does NOT need
  the class symbol bound in the shim's namespace, and **no
  F6-region-local `from xlsx_comment.batch import BatchRow` import
  is required**.
  Original m3 plan-review fix mandated such an import as a
  belt-and-braces measure; verified during 002.5 execution that it
  is unnecessary. The shim comment at the new re-import block
  documents the rationale (`xlsx_add_comment.py` ~lines 186-191).
  Q5's "BatchRow not re-exported from shim" still holds —
  `getattr(xlsx_add_comment, 'BatchRow')` raises `AttributeError`,
  so xlsx-7 callers can't accidentally couple to BatchRow via the
  shim.

## Test Cases

### End-to-end Tests
- **TC-E2E-01:** Re-run E2E. All 112 checks green.
- **TC-E2E-02:** Specifically verify the `BatchTooLarge` E2E
  fixture (9 MiB input → exit 2) — guards the pre-parse cap path.
- **TC-E2E-03:** `T-batch-50` and `T-batch-50-with-existing-vml` E2E
  cases pass — verifies the BatchRow flow end-to-end.

### Unit Tests
- **TC-UNIT-01:** `tests/test_xlsx_add_comment.py::Test*BatchLoader*`
  cases (flat-array, xlsx-7 envelope, group-finding skip, 9 MiB
  rejection, missing default-author) pass unchanged.

### Regression Tests
- Per per-task micro-cycle: unit + E2E green.

## Acceptance Criteria
- [ ] `xlsx_comment/batch.py` ≤ 160 LOC, with docstring + `__all__`
      + sibling-relative imports + F3 body.
- [ ] `xlsx_add_comment.py` no longer defines `BatchRow` or
      `load_batch` directly — they are re-imports.
- [ ] R4.b lock holds.
- [ ] All 75 unit + 112 E2E green.
- [ ] `validate_skill.py skills/xlsx` exits 0.

## Notes
- The 8 MiB cap is in `constants.BATCH_MAX_BYTES` (already moved in
  Task 002.3); `batch.py` MUST reference it via the constants module,
  NOT re-define a local copy.
- `load_batch` writes a one-line "skipped grouped findings: N"
  notice to a stderr-like file object — that contract MUST move
  byte-equivalent.
- Estimated effort: 1 h.

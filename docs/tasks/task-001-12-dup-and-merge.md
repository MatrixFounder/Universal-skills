# Task 2.07 [R5][R6]: [LOGIC IMPLEMENTATION] Duplicate-cell matrix + merged-cell resolver

## Use Case Connection
- I1.5 (Merged-cell target resolution).
- ARCHITECTURE §6.1 duplicate-cell matrix (R5 corollary, M-2 fix).
- New `DuplicateThreadedComment` envelope (ARCHITECTURE §6.2 / M-2).
- RTM: R5, R6.

## Task Goal
Implement `resolve_merged_target` (F5) and the duplicate-cell semantics matrix from ARCHITECTURE §6.1. The duplicate-cell logic sits inside `single_cell_main`/`batch_main` BEFORE the comment is appended — it inspects the existing comments/threaded parts on the target sheet/cell and applies the four-row matrix.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_add_comment.py`

**Function `resolve_merged_target(sheet_xml_root, ref, allow_redirect) -> str`:**
- Parameters:
  - `sheet_xml_root`: lxml root of `xl/worksheets/sheet<S>.xml`.
  - `ref`: target cell ref (e.g. `"B2"`).
  - `allow_redirect`: bool from `--allow-merged-target`.
- Returns: cell ref the comment should land on (anchor of merged range, or original if not merged or already anchor).
- Logic:
  1. Find all `<mergeCells><mergeCell ref="A1:C3">` ranges.
  2. For each range, parse `(min_col, min_row, max_col, max_row)`.
  3. Convert `ref` to `(col, row)`. If `(col, row) == (min_col, min_row)` → not in merged range OR is anchor → return original `ref`.
  4. If `min_col <= col <= max_col and min_row <= row <= max_row` and `(col, row) != (min_col, min_row)`:
     - If `allow_redirect` → emit info `MergedCellRedirect` to stderr (or as JSON-info when `--json-errors`) and return anchor's `ref` (e.g. `"A1"`).
     - Else raise `MergedCellTarget` exception with `details = {"target": ref, "anchor": anchor_ref, "range": "A1:C3"}`.
  5. If not in any merged range: return original `ref`.

**Function `detect_existing_comment_state(sheet_name, ref, tree) -> dict`:**
- Returns `{"has_legacy": bool, "has_threaded": bool, "thread_size": int}`.
- Logic:
  1. Find legacy `commentsN` part for the sheet (via rels). If exists, scan `<comment ref="A5">` entries → `has_legacy = True`.
  2. Find threaded `threadedComments<M>` part for the sheet. If exists, scan `<threadedComment ref="A5">` → `has_threaded = True`, `thread_size = count`.

**Inside `single_cell_main` and `batch_main`, BEFORE writing:**
1. Call `ref = resolve_merged_target(sheet_xml, ref, args.allow_merged_target)` (raises or returns).
2. Call `state = detect_existing_comment_state(sheet, ref, tree)`.
3. Apply the §6.1 matrix:
   - **Empty cell, `--threaded`** → write legacy stub + threaded (per Q7, already implemented in 2.05).
   - **Empty cell, `--no-threaded`** → write legacy only (default path from 2.04).
   - **Legacy only, `--threaded`** → ADD a new threaded entry + ALSO add a NEW matching legacy stub (Q7 fidelity for the new entry; do NOT touch the pre-existing legacy entry).
   - **Legacy only, `--no-threaded`** → exit 2 `DuplicateLegacyComment` (R5.b).
   - **Thread exists, `--threaded`** → append to thread (and add matching new legacy stub if `has_legacy` is True).
   - **Thread exists, `--no-threaded`** → exit 2 `DuplicateThreadedComment` (M-2 / ARCHITECTURE §6.2 — NEW envelope).
4. Helper `_emit_envelope(error_type, code, details)` consolidates the JSON-errors emission for both `MergedCellTarget` and `Duplicate*Comment` paths.

### Component Integration
- 2.04 + 2.05 main paths are unchanged for the empty-cell case; the matrix is enforced as a pre-flight guard.
- `office/validate.py` continues to be the post-write integrity check.

## Test Cases

### End-to-end Tests
- **TC-E2E-T-merged-cell-target:** `merged.xlsx --cell B2 --author Q --text "msg"` (where A1:C3 is merged) → exit 2 `MergedCellTarget` envelope; details has `anchor="A1"`, `range="A1:C3"`.
- **TC-E2E-T-merged-cell-redirect:** Same but with `--allow-merged-target` → exit 0; comment lands on `A1`; stderr has info `MergedCellRedirect` (or JSON details when `--json-errors`).
- **TC-E2E-T-merged-cell-anchor-passthrough:** `--cell A1` (the anchor of A1:C3) → no error, comment lands on A1 directly.
- **TC-E2E-T-duplicate-legacy:** `with_legacy.xlsx --cell <existing-cell> --no-threaded` → exit 2 `DuplicateLegacyComment`.
- **TC-E2E-T-duplicate-threaded-blocked:** Workbook with existing thread on `A5` + `--cell A5 --no-threaded` → exit 2 `DuplicateThreadedComment` (NEW envelope; M-2 lock).
- **TC-E2E-T-duplicate-threaded-append:** Workbook with existing thread on `A5` + `--cell A5 --threaded` → succeed; thread now has +1 entry.

### Unit Tests
- Remove `skipTest` from:
  - `TestMergedResolver.test_anchor_passes_through`: `resolve_merged_target(root, "A1", False)` on `<mergeCell ref="A1:C3">` → returns `"A1"`.
  - `TestMergedResolver.test_non_anchor_raises_default`: `resolve_merged_target(root, "B2", False)` → raises `MergedCellTarget`.
  - `TestMergedResolver.test_non_anchor_redirects_with_flag`: `resolve_merged_target(root, "B2", True)` → returns `"A1"`.
- New unit tests:
  - `TestDuplicateMatrix.test_legacy_only_no_threaded` → `DuplicateLegacyComment`.
  - `TestDuplicateMatrix.test_threaded_exists_no_threaded` → `DuplicateThreadedComment` (M-2).
  - `TestDuplicateMatrix.test_threaded_exists_threaded_appends` → success, thread size +1.

### Regression Tests
- 2.04 `T-clean-no-comments` MUST still pass (empty cell, no flag → default path, no extra envelope).
- 2.05 `T-threaded` MUST still pass (empty cell + `--threaded` → both parts).

## Acceptance Criteria
- [ ] 6 TC-E2E above pass.
- [ ] 6 unit tests above pass.
- [ ] `DuplicateThreadedComment` envelope appears in §6.2 of ARCHITECTURE.md is now genuinely emitted.
- [ ] M-2 matrix correctness verified by exhaustive 4-row test.
- [ ] `office/validate.py` exits 0 on every produced output (when no error).
- [ ] No edits to `skills/docx/scripts/office/`.

## Notes
- The merged-cell resolver only checks the *current* sheet's `<mergeCell>` list — merged-cell semantics are sheet-local.
- The duplicate-cell pre-flight is a READ pass before any write; it does not modify the tree.
- Update `TASK §2.5 Exit codes` table in a separate doc-cleanup pass (deferred to task 2.10): add `DuplicateThreadedComment` to the exit-2 envelope list. (Strictly not required for code-correctness but the table is the user-facing reference.)

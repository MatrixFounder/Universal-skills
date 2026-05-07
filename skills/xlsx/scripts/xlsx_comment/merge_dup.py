"""Merged-cell resolver and duplicate-cell matrix (F5).

Migrated from `xlsx_add_comment.py` F5 region (lines 235-392 of the
post-002.6 shim) during Task 002.

Public API:
    resolve_merged_target(sheet_xml_root, ref, allow_redirect) -> str
        Detect <mergeCell ref="A1:C3"> ranges; if `ref` is non-anchor,
        either raise MergedCellTarget (default) or return anchor (when
        allow_redirect=True, also emits info `MergedCellRedirect` to
        stderr). The anchor case + not-in-range case both pass `ref`
        through unchanged (R6.c).
    detect_existing_comment_state(tree_root_dir, sheet, ref) -> dict
        Read-only inspection of a sheet's existing comments and
        threadedComments at `ref`. Returns
        {has_legacy: bool, has_threaded: bool, thread_size: int}.
    _enforce_duplicate_matrix(state, threaded_mode, sheet_name, ref)
        -> None
        Implements ARCH §6.1 duplicate-cell behaviour matrix. Raises
        DuplicateLegacyComment / DuplicateThreadedComment per the
        (existing-state × mode) cells of the matrix.

Private helpers (`_parse_merge_range`, `_anchor_of_range`) are in
`__all__` for test access via the explicit submodule path.
"""
from __future__ import annotations

import re
import sys

from lxml import etree  # type: ignore
from pathlib import Path  # noqa: F401  # used in type annotations only

from .constants import (
    COMMENTS_REL_TYPE, SS_NS, THREADED_NS, THREADED_REL_TYPE,
)
from .exceptions import (
    DuplicateLegacyComment, DuplicateThreadedComment,
    InvalidCellRef, MergedCellTarget,
)
from .ooxml_editor import (
    _cell_ref_to_zero_based,
    _column_letters_to_index,
    _find_rel_of_type,
    _resolve_target,
    _sheet_part_path,
    _sheet_rels_path,
)

__all__ = [
    "resolve_merged_target",
    "detect_existing_comment_state",
    "_enforce_duplicate_matrix",
    "_parse_merge_range",
    "_anchor_of_range",
]

_MERGE_RANGE_RE = re.compile(r"^([A-Z]+)([0-9]+):([A-Z]+)([0-9]+)$")


def _parse_merge_range(range_ref: str) -> tuple[int, int, int, int]:
    """`A1:C3` → (min_col=0, min_row=0, max_col=2, max_row=2). 0-based."""
    m = _MERGE_RANGE_RE.match(range_ref)
    if not m:
        raise InvalidCellRef(f"malformed mergeCell range: {range_ref!r}")
    c1 = _column_letters_to_index(m.group(1))
    r1 = int(m.group(2)) - 1
    c2 = _column_letters_to_index(m.group(3))
    r2 = int(m.group(4)) - 1
    return c1, r1, c2, r2


def _anchor_of_range(range_ref: str) -> str:
    """`A1:C3` → `A1` (top-left cell of the range)."""
    m = _MERGE_RANGE_RE.match(range_ref)
    if not m:
        raise InvalidCellRef(f"malformed mergeCell range: {range_ref!r}")
    return f"{m.group(1)}{m.group(2)}"


def resolve_merged_target(
    sheet_xml_root: "etree._Element",
    ref: str,
    allow_redirect: bool,
) -> str:
    """If `ref` is a non-anchor of a `<mergeCell>` range:
        - allow_redirect=False (default) → raise `MergedCellTarget`.
        - allow_redirect=True → return the anchor cell ref + emit
          `MergedCellRedirect` info to stderr.

    The cell-IS-anchor case and the not-in-any-merged-range case both
    return `ref` unchanged (R6.c).

    Merge-range detection iterates `<mergeCells><mergeCell ref="...">`.
    Sheet-local: each call inspects only the sheet whose root was passed.
    """
    target_col, target_row = _cell_ref_to_zero_based(ref)
    for merge_el in sheet_xml_root.iter(f"{{{SS_NS}}}mergeCell"):
        range_ref = merge_el.get("ref", "") or ""
        if not range_ref:
            continue
        c1, r1, c2, r2 = _parse_merge_range(range_ref)
        in_range = (c1 <= target_col <= c2) and (r1 <= target_row <= r2)
        if not in_range:
            continue
        is_anchor = (target_col, target_row) == (c1, r1)
        if is_anchor:
            return ref  # R6.c — anchor passes through.
        anchor_ref = _anchor_of_range(range_ref)
        if allow_redirect:
            print(
                f"Note: MergedCellRedirect: {ref} is non-anchor of "
                f"merged range {range_ref}; redirecting to anchor {anchor_ref}",
                file=sys.stderr,
            )
            return anchor_ref
        raise MergedCellTarget(target=ref, anchor=anchor_ref, range_ref=range_ref)
    return ref


def detect_existing_comment_state(
    tree_root_dir: Path,
    sheet: dict,
    ref: str,
) -> dict:
    """Inspect a sheet's existing comments / threadedComments at `ref`.

    Returns `{"has_legacy": bool, "has_threaded": bool, "thread_size": int}`.

    Read-only — does NOT mutate the tree. Used as the pre-flight gate for
    the ARCH §6.1 duplicate-cell matrix in `single_cell_main` / `batch_main`.

    Resolution path: sheet rels → comments / threadedComments rels →
    parse part XML → count `ref` matches.
    """
    sheet_part_path = _sheet_part_path(tree_root_dir, sheet)
    sheet_rels_path = _sheet_rels_path(sheet_part_path)
    if not sheet_rels_path.is_file():
        return {"has_legacy": False, "has_threaded": False, "thread_size": 0}
    sheet_rels_root = etree.parse(str(sheet_rels_path)).getroot()

    has_legacy = False
    has_threaded = False
    thread_size = 0

    legacy_rel = _find_rel_of_type(sheet_rels_root, COMMENTS_REL_TYPE)
    if legacy_rel is not None:
        legacy_path = _resolve_target(
            sheet_rels_path, tree_root_dir, legacy_rel.get("Target", ""),
        )
        if legacy_path.is_file():
            legacy_root = etree.parse(str(legacy_path)).getroot()
            for c in legacy_root.iter(f"{{{SS_NS}}}comment"):
                if c.get("ref") == ref:
                    has_legacy = True
                    break

    threaded_rel = _find_rel_of_type(sheet_rels_root, THREADED_REL_TYPE)
    if threaded_rel is not None:
        threaded_path = _resolve_target(
            sheet_rels_path, tree_root_dir, threaded_rel.get("Target", ""),
        )
        if threaded_path.is_file():
            threaded_root = etree.parse(str(threaded_path)).getroot()
            for tc in threaded_root.iter(f"{{{THREADED_NS}}}threadedComment"):
                if tc.get("ref") == ref:
                    has_threaded = True
                    thread_size += 1

    return {
        "has_legacy": has_legacy,
        "has_threaded": has_threaded,
        "thread_size": thread_size,
    }


def _enforce_duplicate_matrix(
    state: dict,
    threaded_mode: bool,
    sheet_name: str,
    ref: str,
) -> None:
    """ARCH §6.1 duplicate-cell matrix — pre-flight raise gate.

    Six cells of the 3×2 matrix:
      - empty cell, either mode               → no-op (write paths handle).
      - legacy-only, --threaded               → no-op (Q7 fidelity dual-write).
      - legacy-only, --no-threaded            → DuplicateLegacyComment (R5.b).
      - thread exists, --threaded             → no-op (append to thread).
      - thread exists, --no-threaded          → DuplicateThreadedComment (M-2).

    `threaded_mode` is True when the caller will write a threaded entry
    (i.e. `args.threaded` is set, or default-threaded for envelope rows).
    """
    if state["has_threaded"] and not threaded_mode:
        # M-2: silent legacy write next to an existing thread is the
        # worst-of-both-worlds case (older clients see two unrelated
        # comments, Excel-365 sees an orphan legacy entry). Refuse fast.
        raise DuplicateThreadedComment(
            f"Cannot insert legacy-only comment on cell {ref} of sheet "
            f"{sheet_name!r}: a threaded comment thread already exists. "
            f"Use --threaded to append to the thread, or pick a different cell.",
            sheet=sheet_name, cell=ref,
            existing_thread_size=state["thread_size"],
        )
    if state["has_legacy"] and not state["has_threaded"] and not threaded_mode:
        # R5.b — duplicate legacy on --no-threaded.
        raise DuplicateLegacyComment(
            f"Cannot insert legacy comment on cell {ref} of sheet "
            f"{sheet_name!r}: a legacy comment already exists. "
            f"Use --threaded to attach a thread, or pick a different cell.",
            sheet=sheet_name, cell=ref,
        )

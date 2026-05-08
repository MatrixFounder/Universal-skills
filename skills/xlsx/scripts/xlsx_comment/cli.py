"""argparse + main + single_cell_main + batch_main (F1+F6 merged per Q2=A).

Migrated from `xlsx_add_comment.py` F1 region (lines 261-352) and F6
region (lines 355-851 of the post-002.8 shim) during Task 002.

Public API:
    build_parser() -> argparse.ArgumentParser
    main(argv: list[str] | None = None) -> int
Internal:
    single_cell_main, batch_main — orchestration sub-routines.

Per ARCH §8 Q2=A: F1 (argparse) and F6 (main + dispatchers) are KEPT
MERGED. The state-sharing between argparse, MX/DEP validation, and the
unified _AppError handler in main() makes splitting them produce a
90-LOC argparse stub that adds an import hop with zero coupling
reduction.
"""
from __future__ import annotations

import argparse
import sys
import tempfile as _tempfile
from pathlib import Path

from lxml import etree  # type: ignore

# Cross-skill helpers (live at skills/xlsx/scripts/ — sys.path-resolved
# from the shim entry point).
from _errors import add_json_errors_argument, report_error
from office._encryption import EncryptedFileError, assert_not_encrypted
from office._macros import warn_if_macros_will_be_dropped
from office.pack import pack
from office.unpack import unpack

# Package internals (sibling-relative per R4.b).
from .batch import load_batch
from .cell_parser import (
    _load_sheets_from_workbook,
    parse_cell_syntax,
    resolve_sheet,
)
from .cli_helpers import (
    _assert_distinct_paths,
    _content_types_path,
    _post_validate_enabled,
    _resolve_date,
    _validate_args,
)
# Note: `_post_pack_validate` is intentionally NOT imported at module
# scope here. It is looked up at call time via the shim's module
# attribute (`xlsx_add_comment._post_pack_validate`) so that
# `tests/test_xlsx_add_comment.py::TestPostValidateGuard.*` can mock
# `xlsx_add_comment._post_pack_validate` and have the mock take effect
# inside `main()`. R3.a (zero test edits) requires the test's mock
# target to remain on the shim. Documented R4.b deviation, bounded to
# one call site at the bottom of `main()`.
from .constants import COMMENTS_CT, PERSON_CT, THREADED_CT, VML_CT
from .exceptions import _AppError, EmptyCommentBody, SelfOverwriteRefused
from .merge_dup import (
    _enforce_duplicate_matrix,
    detect_existing_comment_state,
    resolve_merged_target,
)
from .constants import PR_NS, VML_REL_TYPE
from .ooxml_editor import (
    _allocate_new_parts,
    _patch_content_types,
    _sheet_part_path,
    _xml_serialize,
    add_legacy_comment,
    add_person,
    add_threaded_comment,
    add_vml_shape,
    ensure_legacy_comments_part,
    ensure_person_list,
    ensure_sheet_legacy_drawing_ref,
    ensure_threaded_comments_part,
    ensure_vml_drawing,
)


def _vml_rel_id(sheet_rels_root: "etree._Element") -> str:
    """Return the rId of the `vmlDrawing` Relationship in this sheet rels.

    INVARIANT (vdd-adversarial-r2 LOW#2): there is exactly ONE
    `vmlDrawing` rel per sheet. Excel itself never emits more than one;
    `ensure_vml_drawing` reuses any pre-existing rel via
    `_find_rel_of_type` instead of adding a second; `_patch_sheet_rels`
    is idempotent on (Type, Target) tuples. If a future change relaxes
    any of these, this `findall`-then-return-first becomes ambiguous
    and must grow a discriminator (e.g. by Target).

    `_patch_sheet_rels` returns the rId, but the call is buried inside
    `ensure_vml_drawing`. Looking up post-hoc here avoids an invasive
    signature change.
    """
    for rel in sheet_rels_root.findall(f"{{{PR_NS}}}Relationship"):
        if rel.get("Type") == VML_REL_TYPE:
            return rel.get("Id")
    raise RuntimeError(
        "VML rel missing from sheet rels — ensure_vml_drawing should have "
        "added it; this is a logic-bug, not a user-facing failure mode."
    )

__all__ = ["build_parser", "main", "single_cell_main", "batch_main"]


def build_parser() -> argparse.ArgumentParser:
    """Build the full TASK §2.5 CLI surface.

    Mutex / dependency rules (MX-A, MX-B, DEP-1..4) are enforced
    post-parse in `_validate_args` (task 2.01) — argparse cannot
    express the conditional "required-when" rules natively.
    """
    # Hardcoded user-facing description (was `__doc__.splitlines()[0]`
    # of the pre-002.9 shim, which carried the user-facing summary).
    # After the F1 migration to cli.py, `__doc__` here refers to the
    # internal cli.py docstring — pinning the literal preserves the
    # baseline `--help` byte-for-byte (TASK 002 R2 / TC-E2E-02).
    parser = argparse.ArgumentParser(
        description="Insert a Microsoft Excel comment into a target cell of a .xlsx workbook.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="Source .xlsx/.xlsm.")
    parser.add_argument("output", type=Path, help="Destination .xlsx/.xlsm (must differ from input).")

    # Single-cell mode (MX-A group)
    parser.add_argument(
        "--cell",
        default=None,
        metavar="REF",
        help="Target cell. Forms: A5, Sheet2!B5, 'Q1 2026'!A1, 'Bob''s Sheet'!A1.",
    )
    parser.add_argument(
        "--text",
        default=None,
        metavar="MSG",
        help="Comment body (plain text). Empty or whitespace-only → exit 2 EmptyCommentBody.",
    )
    parser.add_argument(
        "--author",
        default=None,
        metavar="NAME",
        help="Display name. Required when --cell.",
    )
    parser.add_argument(
        "--initials",
        default=None,
        metavar="INI",
        help="Override initials (default: first letter of each whitespace-token in --author).",
    )

    # Batch mode (MX-A group)
    parser.add_argument(
        "--batch",
        default=None,
        metavar="FILE",
        help="JSON file (or - for stdin). Auto-detects flat-array vs xlsx-7 envelope. 8 MiB cap.",
    )
    parser.add_argument(
        "--default-author",
        dest="default_author",
        default=None,
        metavar="NAME",
        help="Required when --batch is xlsx-7 envelope shape; ignored otherwise.",
    )
    parser.add_argument(
        "--default-threaded",
        dest="default_threaded",
        action="store_true",
        help="Default `threaded` for envelope-shape rows.",
    )

    # Threaded-mode group (MX-B)
    parser.add_argument(
        "--threaded",
        action="store_true",
        help="Force threaded write (writes BOTH legacy stub + threadedComment + personList per Q7).",
    )
    parser.add_argument(
        "--no-threaded",
        dest="no_threaded",
        action="store_true",
        help="Force legacy-only write (no threaded part, no personList).",
    )

    # Cross-cutting & cell-policy
    parser.add_argument(
        "--allow-merged-target",
        dest="allow_merged_target",
        action="store_true",
        help="Redirect comment to anchor of merged range instead of failing fast (R6.b).",
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="ISO",
        help="Override timestamp on <threadedComment dT>. Default: datetime.now(UTC).",
    )

    add_json_errors_argument(parser)
    return parser


def single_cell_main(
    args: argparse.Namespace,
    tree_root_dir: Path,
    all_sheets: list[dict],
) -> int:
    """Single-cell legacy write path (task 2.04 — `--no-threaded` default).

    Threaded layer is added in task 2.05; merged-cell + duplicate-cell
    pre-flight in task 2.07. At this stage `--threaded` is accepted by
    argparse but the threaded part is NOT yet emitted (will be in 2.05).
    """
    # Q2 closure: empty / whitespace-only --text → fail at parse-equivalent
    # boundary, BEFORE any OOXML mutation, so the workbook isn't half-written.
    if not args.text or not args.text.strip():
        raise EmptyCommentBody(
            "--text is empty or whitespace-only (Q2: comments must have content)"
        )

    # Cell-syntax + sheet resolution (F2; task 2.02).
    qualified, cell_ref = parse_cell_syntax(args.cell)
    sheet_name = resolve_sheet(qualified, all_sheets)
    sheet = next(s for s in all_sheets if s["name"] == sheet_name)

    # F5 (task 2.07): merged-cell pre-flight. Read-only — may rewrite
    # `cell_ref` to the anchor when --allow-merged-target, or raise
    # MergedCellTarget on a non-anchor without the flag.
    sheet_part_path = _sheet_part_path(tree_root_dir, sheet)
    sheet_xml_root = etree.parse(str(sheet_part_path)).getroot()
    cell_ref = resolve_merged_target(
        sheet_xml_root, cell_ref, args.allow_merged_target,
    )

    # F5 (task 2.07): duplicate-cell matrix pre-flight (ARCH §6.1).
    # Threaded mode = explicit --threaded (default-threaded only applies
    # to --batch envelope rows, not single-cell).
    state = detect_existing_comment_state(tree_root_dir, sheet, cell_ref)
    _enforce_duplicate_matrix(
        state, threaded_mode=bool(args.threaded),
        sheet_name=sheet_name, ref=cell_ref,
    )

    # ONE workbook-wide pre-scan per invocation (task 2.03 spec / ARCH §I2.3).
    alloc = _allocate_new_parts(tree_root_dir)

    # Legacy comments part: get-or-create + append our <comment>.
    comments_path, comments_root, sheet_rels_root, sheet_rels_path = (
        ensure_legacy_comments_part(tree_root_dir, sheet, alloc.next_comments_n)
    )
    add_legacy_comment(comments_root, cell_ref, args.author, args.text)
    _xml_serialize(comments_root, comments_path)

    # VML drawing: get-or-create + append our <v:shape>. The `idmap_data`
    # value passed in only matters for NEW VML parts; reused parts keep
    # their existing <o:idmap data>.
    new_idmap = max(alloc.idmap_used) + 1 if alloc.idmap_used else 1
    vml_path, vml_root, vml_is_new = ensure_vml_drawing(
        tree_root_dir, sheet, sheet_rels_root, sheet_rels_path,
        idmap_data=new_idmap,
        next_k=alloc.next_vml_k,
    )
    # Shape ID: max+1 over the existing workbook range (m-1 chosen rule;
    # 1025 baseline for empty workbooks matches Excel's `_x0000_s1025` start).
    new_spid = max(alloc.spid_used) + 1 if alloc.spid_used else 1025
    add_vml_shape(vml_root, cell_ref, new_spid)
    _xml_serialize(vml_root, vml_path)

    # Sheet rels file may have grown (new comments + vml relationships);
    # always serialise so the new parts are reachable from the worksheet.
    _xml_serialize(sheet_rels_root, sheet_rels_path)

    # Anchor the VML drawing to the worksheet itself via
    # `<legacyDrawing r:id=…/>`. Without this, Excel / LibreOffice see
    # the rel in `_rels/sheetN.xml.rels` but do NOT render the yellow
    # comment hover-bubbles. Post-Task-002 hot-fix.
    ensure_sheet_legacy_drawing_ref(
        sheet_part_path, _vml_rel_id(sheet_rels_root),
    )

    # Patch [Content_Types].xml: idempotent Override per new part. The
    # comments part is always per-part Override (no Default Extension
    # convention for the comments content-type). The VML part: skip the
    # per-part Override if `<Default Extension="vml">` is already present
    # (m-3 idempotency rule).
    ct_path = _content_types_path(tree_root_dir)
    ct_root = etree.parse(str(ct_path)).getroot()
    _patch_content_types(
        ct_root,
        "/" + str(comments_path.relative_to(tree_root_dir)).replace("\\", "/"),
        COMMENTS_CT,
    )
    if vml_is_new:
        _patch_content_types(
            ct_root,
            "/" + str(vml_path.relative_to(tree_root_dir)).replace("\\", "/"),
            VML_CT,
            default_extension="vml",
        )

    # Q7 Option A (Excel-365 fidelity): when --threaded, write BOTH
    # the legacy stub (already done above) AND the threaded layer +
    # personList. The legacy stub keeps the file readable in older
    # Excel and LibreOffice; the threaded layer drives the modern
    # Comments side-pane. M6 lock: personList rel goes on
    # workbook.xml.rels, NOT sheet rels.
    if args.threaded:
        # personList (workbook-scoped — M6).
        pl_path, pl_root, wb_rels_root, wb_rels_path, pl_is_new = (
            ensure_person_list(tree_root_dir)
        )
        person_id = add_person(pl_root, args.author)
        _xml_serialize(pl_root, pl_path)
        if pl_is_new:
            _xml_serialize(wb_rels_root, wb_rels_path)
            _patch_content_types(
                ct_root,
                "/" + str(pl_path.relative_to(tree_root_dir)).replace("\\", "/"),
                PERSON_CT,
            )

        # threadedComments (sheet-scoped).
        threaded_path, threaded_root, threaded_is_new = (
            ensure_threaded_comments_part(
                tree_root_dir, sheet, sheet_rels_root, sheet_rels_path,
                next_m=alloc.next_threaded_m,
            )
        )
        add_threaded_comment(
            threaded_root, cell_ref, person_id, args.text, args.date_iso,
        )
        _xml_serialize(threaded_root, threaded_path)
        if threaded_is_new:
            _patch_content_types(
                ct_root,
                "/" + str(threaded_path.relative_to(tree_root_dir)).replace("\\", "/"),
                THREADED_CT,
            )
        # threaded write may have grown sheet rels (new threadedComment rel)
        # — re-serialise to capture; for the personList path, wb_rels were
        # serialised above when pl_is_new fired.
        _xml_serialize(sheet_rels_root, sheet_rels_path)

    _xml_serialize(ct_root, ct_path)
    return 0


def batch_main(
    args: argparse.Namespace,
    tree_root_dir: Path,
    all_sheets: list[dict],
) -> int:
    """Batch write path: load JSON → single open/save cycle → N comments.

    The "single open/save cycle" requirement (TASK §2 R4 + I2.3 step 3)
    is the perf driver: ~50× faster than per-row repack on T-batch-50.
    Pre-scan workbook ONCE; sheet-scoped state (comments_root, vml_root,
    sheet_rels_root, threaded_root) is memoised so each sheet's parts
    are opened on first use only.

    Incremental allocator (R4.h): after each row's allocation, the freshly-
    chosen `idmap_data` / `spid` are added to the local `idmap_used` /
    `spid_used` sets so the next row's allocator sees them. Without this,
    a 50-row batch would allocate the same `spid` 50 times.
    """
    rows, skipped_grouped = load_batch(
        args.batch, args.default_author, args.default_threaded,
    )

    if skipped_grouped:
        # I2.2 Acceptance: stderr summary for skipped group-findings.
        print(
            f"Note: skipped {skipped_grouped} group-finding"
            f"{'s' if skipped_grouped != 1 else ''} (row=null) per R4.e",
            file=sys.stderr,
        )

    # Workbook-wide pre-scan ONCE per invocation (ARCH §I2.3).
    alloc = _allocate_new_parts(tree_root_dir)
    idmap_used = set(alloc.idmap_used)
    spid_used = set(alloc.spid_used)
    next_vml_k = alloc.next_vml_k
    next_comments_n = alloc.next_comments_n
    next_threaded_m = alloc.next_threaded_m

    # Per-sheet memoisation. Key = sheet name (case-sensitive).
    # Each entry holds the in-memory roots + paths so we serialise once.
    sheet_state: dict[str, dict] = {}
    person_list_state: dict | None = None

    # Content_Types is workbook-scoped — open once, patch repeatedly.
    ct_path = _content_types_path(tree_root_dir)
    ct_root = etree.parse(str(ct_path)).getroot()

    # Per-sheet sheet-xml memo for merged-cell resolution (read-only).
    sheet_xml_cache: dict[str, "etree._Element"] = {}
    # In-batch dup matrix: rows already written this run augment the
    # input-state seen by `detect_existing_comment_state` so two batch
    # rows targeting the same cell with mixed --threaded modes still
    # honour ARCH §6.1 (M-2 lock as an output-invariant, not just input).
    written_state: dict[tuple[str, str], dict] = {}

    for row in rows:
        if not row.text or not row.text.strip():
            # Q2 closure applies in batch too.
            raise EmptyCommentBody(
                f"--batch row cell={row.cell!r}: text is empty/whitespace-only"
            )

        qualified, cell_ref = parse_cell_syntax(row.cell)
        sheet_name = resolve_sheet(qualified, all_sheets)
        sheet = next(s for s in all_sheets if s["name"] == sheet_name)

        # F5: merged-cell pre-flight (ARCH R6 / task 2.07).
        sx = sheet_xml_cache.get(sheet_name)
        if sx is None:
            sx = etree.parse(
                str(_sheet_part_path(tree_root_dir, sheet))
            ).getroot()
            sheet_xml_cache[sheet_name] = sx
        cell_ref = resolve_merged_target(
            sx, cell_ref, args.allow_merged_target,
        )

        # F5: duplicate-cell matrix pre-flight (ARCH §6.1 / task 2.07).
        # In batch, "threaded mode" is per-row: row.threaded reflects the
        # row's own --threaded flag (or default-threaded for envelope rows).
        # Augment on-disk state with rows already written this run so the
        # M-2 invariant holds as an OUTPUT-invariant, not just input
        # (two batch rows on the same cell with mixed modes would
        # otherwise sneak past the gate).
        state = detect_existing_comment_state(tree_root_dir, sheet, cell_ref)
        prev = written_state.get((sheet_name, cell_ref))
        if prev is not None:
            state = {
                "has_legacy": state["has_legacy"] or prev["has_legacy"],
                "has_threaded": state["has_threaded"] or prev["has_threaded"],
                "thread_size": state["thread_size"] + prev["thread_size"],
            }
        _enforce_duplicate_matrix(
            state, threaded_mode=row.threaded,
            sheet_name=sheet_name, ref=cell_ref,
        )
        # Record THIS row's contribution for the next row's gate.
        written_state[(sheet_name, cell_ref)] = {
            "has_legacy": True,  # every row writes a legacy stub (Q7).
            "has_threaded": row.threaded or (
                prev["has_threaded"] if prev else False
            ),
            "thread_size": (prev["thread_size"] if prev else 0) + (
                1 if row.threaded else 0
            ),
        }

        # Lazy-initialise per-sheet state on first row that touches that sheet.
        st = sheet_state.get(sheet_name)
        if st is None:
            comments_path, comments_root, sheet_rels_root, sheet_rels_path = (
                ensure_legacy_comments_part(
                    tree_root_dir, sheet, next_comments_n,
                )
            )
            # `ensure_legacy_comments_part` returns the path it would write
            # but does NOT serialise. So `comments_path.is_file()` is False
            # for fresh parts, True for reused (already-on-disk) ones.
            comments_was_new = not comments_path.is_file()
            if comments_was_new:
                # Next sheet that creates a new comments part must take
                # the next counter value.
                next_comments_n += 1
            st = {
                "sheet": sheet,
                "comments_path": comments_path,
                "comments_root": comments_root,
                "sheet_rels_root": sheet_rels_root,
                "sheet_rels_path": sheet_rels_path,
                "vml_path": None,
                "vml_root": None,
                "vml_was_new": False,
                "threaded_path": None,
                "threaded_root": None,
                "threaded_was_new": False,
                "comments_part_was_new": comments_was_new,
            }
            sheet_state[sheet_name] = st

        # Append legacy <comment>.
        add_legacy_comment(st["comments_root"], cell_ref, row.author, row.text)

        # Get-or-create VML drawing for this sheet (memoised).
        if st["vml_root"] is None:
            new_idmap = (max(idmap_used) + 1) if idmap_used else 1
            vml_path, vml_root, vml_is_new = ensure_vml_drawing(
                tree_root_dir, st["sheet"],
                st["sheet_rels_root"], st["sheet_rels_path"],
                idmap_data=new_idmap,
                next_k=next_vml_k,
            )
            st["vml_path"] = vml_path
            st["vml_root"] = vml_root
            st["vml_was_new"] = vml_is_new
            if vml_is_new:
                # New part claims the chosen idmap value AND consumes the K.
                idmap_used.add(new_idmap)
                next_vml_k += 1
            # Existing parts already contributed to idmap_used in pre-scan.

        # Allocate fresh spid for this shape — incremental.
        new_spid = (max(spid_used) + 1) if spid_used else 1025
        spid_used.add(new_spid)
        add_vml_shape(st["vml_root"], cell_ref, new_spid)

        # Threaded layer (Q7 fidelity dual-write per row.threaded).
        if row.threaded:
            # Person list (workbook-scoped — M6).
            if person_list_state is None:
                pl_path, pl_root, wb_rels_root, wb_rels_path, pl_is_new = (
                    ensure_person_list(tree_root_dir)
                )
                person_list_state = {
                    "pl_path": pl_path,
                    "pl_root": pl_root,
                    "wb_rels_root": wb_rels_root,
                    "wb_rels_path": wb_rels_path,
                    "is_new": pl_is_new,
                }
            person_id = add_person(person_list_state["pl_root"], row.author)

            # Threaded comments part (sheet-scoped, memoised).
            if st["threaded_root"] is None:
                threaded_path, threaded_root, threaded_is_new = (
                    ensure_threaded_comments_part(
                        tree_root_dir, st["sheet"],
                        st["sheet_rels_root"], st["sheet_rels_path"],
                        next_m=next_threaded_m,
                    )
                )
                st["threaded_path"] = threaded_path
                st["threaded_root"] = threaded_root
                st["threaded_was_new"] = threaded_is_new
                if threaded_is_new:
                    next_threaded_m += 1
            add_threaded_comment(
                st["threaded_root"], cell_ref, person_id,
                row.text, args.date_iso,
            )

    # ---- Serialise once per part ----
    for sheet_name, st in sheet_state.items():
        _xml_serialize(st["comments_root"], st["comments_path"])
        if st["vml_root"] is not None:
            _xml_serialize(st["vml_root"], st["vml_path"])
        if st["threaded_root"] is not None:
            _xml_serialize(st["threaded_root"], st["threaded_path"])
        # Sheet rels may have grown via comments / vml / threaded patches.
        _xml_serialize(st["sheet_rels_root"], st["sheet_rels_path"])

        # Anchor the VML drawing to this sheet's worksheet via
        # `<legacyDrawing r:id=…/>` (post-Task-002 hot-fix). Without
        # this Excel sees the rel but does NOT render the comment
        # hover-bubbles. The sheet has a VML drawing iff its memoised
        # state has a non-None vml_root.
        if st["vml_root"] is not None:
            sheet_part_path = _sheet_part_path(tree_root_dir, st["sheet"])
            ensure_sheet_legacy_drawing_ref(
                sheet_part_path, _vml_rel_id(st["sheet_rels_root"]),
            )

        # Patch [Content_Types].xml for this sheet's NEW parts.
        if st["comments_part_was_new"]:
            _patch_content_types(
                ct_root,
                "/" + str(st["comments_path"].relative_to(tree_root_dir)).replace("\\", "/"),
                COMMENTS_CT,
            )
        if st["vml_was_new"]:
            _patch_content_types(
                ct_root,
                "/" + str(st["vml_path"].relative_to(tree_root_dir)).replace("\\", "/"),
                VML_CT,
                default_extension="vml",
            )
        if st["threaded_was_new"]:
            _patch_content_types(
                ct_root,
                "/" + str(st["threaded_path"].relative_to(tree_root_dir)).replace("\\", "/"),
                THREADED_CT,
            )

    if person_list_state is not None:
        _xml_serialize(
            person_list_state["pl_root"], person_list_state["pl_path"],
        )
        if person_list_state["is_new"]:
            _xml_serialize(
                person_list_state["wb_rels_root"],
                person_list_state["wb_rels_path"],
            )
            _patch_content_types(
                ct_root,
                "/" + str(person_list_state["pl_path"].relative_to(tree_root_dir)).replace("\\", "/"),
                PERSON_CT,
            )

    _xml_serialize(ct_root, ct_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Orchestration entry point.

    Order of operations (each step's failure mode bubbles through the
    unified `_AppError` / `EncryptedFileError` handler at the bottom,
    which routes through `_errors.report_error` with the correct exit
    code and envelope type):

    1. parse_args      — argparse, with `add_json_errors_argument`
                          monkey-patching `parser.error` for DEP-4.
    2. _validate_args  — MX-A/B, DEP-1, DEP-3 (shape-independent).
    3. file-exists     — INPUT must exist (FileNotFound, code 1).
    4. cross-7 H1      — same-path resolved through symlinks (code 6).
    5. cross-3         — encryption / legacy-CFB pre-flight (code 3).
    6. cross-4         — macro warning to stderr (no failure path).
    7. date resolution — Q5: --date overrides; default UTC now ISO-Z.
    8. dispatch        — single_cell_main (--cell) or batch_main (--batch).
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    je = args.json_errors

    try:
        _validate_args(args)

        if not args.input.is_file():
            return report_error(
                f"Input not found: {args.input}", code=1,
                error_type="FileNotFound",
                details={"path": str(args.input)}, json_mode=je,
            )

        _assert_distinct_paths(args.input, args.output)

        # cross-3: encrypted / legacy CFB → exit 3.
        assert_not_encrypted(args.input)

        # cross-4: emit warning to stderr if .xlsm → .xlsx would drop macros.
        warn_if_macros_will_be_dropped(args.input, args.output, sys.stderr)

        # Q5: stash resolved ISO-8601 date on args for downstream consumers.
        args.date_iso = _resolve_date(args.date)

        # Both single-cell and batch paths share the unpack → mutate → pack
        # frame. Dispatch to the per-row handler inside the temp tree so
        # the pack-failure cleanup (MAJ-2) covers both modes.
        with _tempfile.TemporaryDirectory(prefix="xlsx_add_comment-") as td:
            tree_root = Path(td) / "tree"
            unpack(args.input, tree_root)
            wb_root = etree.parse(
                str(tree_root / "xl" / "workbook.xml")
            ).getroot()
            all_sheets = _load_sheets_from_workbook(wb_root)
            if args.batch is not None:
                rc = batch_main(args, tree_root, all_sheets)
            else:
                rc = single_cell_main(args, tree_root, all_sheets)
            if rc != 0:
                return rc
            # MAJ-2 lock: if pack fails mid-write the output may be a
            # corrupt half-zip. Mirror office_passwd.py's M1 cleanup
            # pattern — if pack raises, unlink the partial output then
            # re-raise so the user sees a clean exit-code path with no
            # orphan to debug. (TemporaryDirectory cleans tree_root.)
            try:
                pack(tree_root, args.output)
            except Exception:
                try:
                    args.output.unlink()
                except (OSError, FileNotFoundError):
                    pass
                raise

        # R8 / 2.08: opt-in post-pack integrity guard. Defence-in-depth
        # against developer error during xlsx-6 implementation — NOT a
        # substitute for input validation. Off by default to avoid
        # doubling invocation latency on production runs; CI / E2E set
        # XLSX_ADD_COMMENT_POST_VALIDATE=1 (truthy semantics —
        # `_post_validate_enabled` only honours `1/true/yes/on`).
        if _post_validate_enabled():
            # R3.a / R4.b deviation — see import comment above:
            # tests mock `xlsx_add_comment._post_pack_validate`, so we
            # resolve via the shim module attribute at call time.
            import xlsx_add_comment as _shim
            _shim._post_pack_validate(args.output)
        return 0

    except _AppError as exc:
        # Compose contextual message + envelope for the typed error.
        message = str(exc)
        if isinstance(exc, SelfOverwriteRefused):
            message = (
                f"INPUT and OUTPUT resolve to the same path: {exc} "
                f"(would corrupt the source on a pack-time crash)"
            )
            details = {"input": str(args.input), "output": str(args.output)}
        else:
            details = exc.details or None
        return report_error(
            message, code=exc.code, error_type=exc.envelope_type,
            details=details, json_mode=je,
        )
    except EncryptedFileError as exc:
        return report_error(
            str(exc), code=3, error_type="EncryptedFileError",
            details={"path": str(args.input)}, json_mode=je,
        )

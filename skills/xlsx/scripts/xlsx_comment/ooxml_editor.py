"""OOXML scanners, part-counter, rels/CT, legacy/threaded writers (F4).

Migrated from `xlsx_add_comment.py` F4 region (lines 194-970 of the
post-002.5 shim) during Task 002.

Owns the workbook-wide invariants:
  - <o:idmap data> integers are workbook-wide unique (C1 + M-1):
      the attribute is a comma-separated LIST per ECMA-376; the
      scanner unions every integer from every <o:idmap> element
      across every xl/drawings/vmlDrawing*.xml part.
  - <v:shape o:spid> integers are workbook-wide unique (C1).
      DIFFERENT collision domain from idmap — they are TWO
      domains, conflating them is the round-1 bug C1.
  - personList rel attaches to xl/_rels/workbook.xml.rels (M6).
  - <author>/<person> dedup is case-sensitive on displayName (m5).

Security boundary:
    _VML_PARSER is an lxml XMLParser hardened against billion-laughs
    / XXE on tampered VML (resolve_entities=False, no_network=True,
    load_dtd=False, huge_tree=False). DO NOT mutate this constructor
    — the security argument from Task 2.04 is locked verbatim here.

Public API (re-exported from xlsx_add_comment.py shim per TASK §2.5):
    next_part_counter, scan_idmap_used, scan_spid_used,
    add_person, add_legacy_comment, add_vml_shape,
    _make_relative_target, _allocate_rid, _patch_content_types
Private (in __all__ for sibling-module + test import via shim):
    _vml_part_paths, _parse_vml, _Allocation, _allocate_new_parts,
    _column_letters_to_index, _cell_ref_to_zero_based,
    _resolve_target, _resolve_workbook_rels, _sheet_part_path,
    _sheet_rels_path, _open_or_create_rels, _find_rel_of_type,
    _patch_sheet_rels, ensure_legacy_comments_part,
    ensure_vml_drawing, _xml_serialize,
    ensure_threaded_comments_part, ensure_person_list,
    add_threaded_comment, _VML_PARSER
"""
from __future__ import annotations

import os as _os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from lxml import etree  # type: ignore

from .constants import (
    SS_NS, R_NS, PR_NS, CT_NS, V_NS, O_NS, X_NS, THREADED_NS,
    COMMENTS_REL_TYPE,
    VML_REL_TYPE,
    THREADED_REL_TYPE,
    PERSON_REL_TYPE,
    DEFAULT_VML_ANCHOR,
)
from .exceptions import InvalidCellRef, MalformedVml, SheetNotFound

__all__ = [
    # Scanners + part-counter
    "scan_idmap_used", "scan_spid_used", "next_part_counter",
    "_vml_part_paths", "_parse_vml",
    "_Allocation", "_allocate_new_parts",
    # Cell-ref helpers
    "_column_letters_to_index", "_cell_ref_to_zero_based",
    # Target/path resolution
    "_resolve_target", "_make_relative_target",
    "_resolve_workbook_rels", "_sheet_part_path", "_sheet_rels_path",
    # Rels + content-types
    "_open_or_create_rels", "_allocate_rid", "_find_rel_of_type",
    "_patch_sheet_rels", "_patch_content_types",
    # Legacy comments
    "ensure_legacy_comments_part", "add_legacy_comment",
    "ensure_vml_drawing", "add_vml_shape", "_xml_serialize",
    # Threaded comments
    "ensure_threaded_comments_part", "ensure_person_list",
    "add_person", "add_threaded_comment",
    # Worksheet anchor for VML legacy drawing (post-002 hot-fix —
    # without this Excel sees the vmlDrawing rel but does NOT render
    # the yellow comment hover-bubbles. ECMA-376 Part 1 §18.3.1.27.)
    "ensure_sheet_legacy_drawing_ref",
    # Security boundary — preserved verbatim from Task 001 (m4 from
    # plan-review). NOT a function but a module-level constant; in
    # __all__ so 002.10's smoke test + lint tools see it.
    "_VML_PARSER",
]

_SPID_RE = re.compile(r"^_x0000_s(\d+)$")
_PART_INT_RE = re.compile(r"(\d+)\.xml$")


def _vml_part_paths(tree_root_dir: Path) -> list[Path]:
    """All VML drawing parts in the workbook, deterministic order.

    Two filename conventions are in use across consumers:
      - Excel:    `xl/drawings/vmlDrawing<N>.xml`
      - openpyxl: `xl/drawings/<anyname><N>.vml`  (e.g. `commentsDrawing1.vml`)

    Both are valid VML drawings. The scanners must see ALL of them so
    the workbook-wide invariants on `<o:idmap data>` and `o:spid` hold
    regardless of who originally wrote the file.
    """
    vml_dir = tree_root_dir / "xl" / "drawings"
    if not vml_dir.is_dir():
        return []
    paths = set(vml_dir.glob("vmlDrawing*.xml")) | set(vml_dir.glob("*.vml"))
    return sorted(paths)

# Hardened parser for VML: tampered input must NOT be allowed to expand
# entities (billion-laughs / XXE). lxml default already disables network
# fetches, but resolve_entities and huge_tree need explicit lockdown for
# defensive code reading user-provided OOXML.
_VML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    huge_tree=False,
)


def _parse_vml(vml_path: Path) -> "etree._Element":
    """Parse a vmlDrawing*.xml file; raise MalformedVml on syntax error.

    Centralised so both scanners share the same defensive XML parse,
    AND so the hardened XMLParser (entity-expansion disabled — defense
    vs billion-laughs / XXE on tampered VML) is the single source of
    truth.
    """
    try:
        return etree.parse(str(vml_path), parser=_VML_PARSER).getroot()
    except etree.XMLSyntaxError as exc:
        raise MalformedVml(f"{vml_path}: XML parse error: {exc}") from exc


def scan_idmap_used(tree_root_dir: Path) -> set[int]:
    """Workbook-wide union of all integers claimed by `<o:idmap data>` lists.

    Per M-1: `<o:idmap data>` is a COMMA-SEPARATED LIST per ECMA-376 / VML 1.0
    (e.g. `data="1,5,9"` claims integers 1, 5, AND 9 for the drawing). A
    naive scalar parse silently corrupts heavily-edited workbooks. The
    scanner unions every integer from every `<o:idmap>` element across
    every `xl/drawings/vmlDrawing*.xml` part — that is the workbook-wide
    invariant the allocator must respect.

    Edge cases:
        - directory `xl/drawings/` absent → empty set (nothing to claim).
        - `<o:shapelayout>` without `<o:idmap>` child → contributes nothing.
        - `<o:idmap data="">` (empty list) → contributes nothing.
        - non-integer token in the list → raise `MalformedVml` (exit 1).
    """
    used: set[int] = set()
    # `_vml_part_paths` returns sorted Excel-style + openpyxl-style VML
    # parts. Sort is for deterministic `MalformedVml` error-path output
    # (goldens / regression diffs); set-union itself is order-independent.
    for vml_path in _vml_part_paths(tree_root_dir):
        root = _parse_vml(vml_path)
        # Use .iter() not .findall() so we don't have to know whether
        # <o:idmap> is wrapped in <o:shapelayout> or hoisted (Excel
        # is consistent; tampered files vary).
        for idmap_el in root.iter(f"{{{O_NS}}}idmap"):
            data_attr = idmap_el.get("data", "") or ""
            for token in data_attr.split(","):
                token = token.strip()
                if not token:
                    continue
                try:
                    used.add(int(token))
                except ValueError as exc:
                    raise MalformedVml(
                        f"{vml_path}: malformed integer in "
                        f"<o:idmap data>: {token!r}"
                    ) from exc
    return used


def scan_spid_used(tree_root_dir: Path) -> set[int]:
    """Workbook-wide set of NNNN integers from `<v:shape id="_x0000_sNNNN">`.

    DIFFERENT collision domain from idmap (C1): every `<v:shape>` across
    every VML part must have a unique NNNN. Mirrors Excel's own
    `_x0000_s1025`-then-`_x0000_s1026` allocator pattern.

    Non-conforming `id` attributes (anything that doesn't match
    `^_x0000_s\\d+$`) are skipped — Excel sometimes emits these for
    legacy AutoShapes that aren't in our managed range. The allocator
    is conservative: max+1 over the *managed* range only.
    """
    used: set[int] = set()
    for vml_path in _vml_part_paths(tree_root_dir):
        root = _parse_vml(vml_path)
        for shape_el in root.iter(f"{{{V_NS}}}shape"):
            shape_id = shape_el.get("id", "") or ""
            m = _SPID_RE.match(shape_id)
            if m:
                used.add(int(m.group(1)))
    return used


def next_part_counter(tree_root_dir: Path, glob_pattern: str) -> int:
    """`max(N) + 1` over filenames matching `glob_pattern`; `1` if none.

    Used INDEPENDENTLY for `xl/comments*.xml`, `xl/threadedComments*.xml`,
    and `xl/drawings/vmlDrawing*.xml` — the three counters do NOT share
    state. Gap-free is NOT a goal: a workbook with `comments1.xml` +
    `comments3.xml` (gap at 2) yields `4` (max+1), not `2` (gap-fill).
    Excel itself does max+1; gap-fill would create rels-target ambiguity
    on round-trip.

    > [!IMPORTANT]
    > **Callers MUST use `*.xml` not `?.xml`.** The task spec's literal
    > example `"xl/comments?.xml"` only matches single-digit names —
    > a workbook with `comments10.xml` would be invisible to the glob,
    > and the next allocation would silently collide with the existing
    > 10th part. Tasks 2.04 / 2.06 invoke this helper via the
    > convenience wrapper `_allocate_new_parts` below, which hardcodes
    > the three valid `*.xml` patterns. Direct callers in tests use
    > `*.xml` per the test layout.
    """
    nums: list[int] = []
    for p in tree_root_dir.glob(glob_pattern):
        m = _PART_INT_RE.search(p.name)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) + 1 if nums else 1


@dataclass(frozen=True)
class _Allocation:
    """Workbook-wide pre-scan results bundled into a single value.

    Used by `single_cell_main` (task 2.04) and `batch_main` (task 2.06) to
    do the pre-scan ONCE per invocation — never per-row in batch mode.
    The four fields are the inputs to every per-row part-allocation
    decision in F4 helpers (`ensure_legacy_comments_part`,
    `ensure_threaded_comments_part`, `ensure_vml_drawing`, `add_vml_shape`).
    """

    idmap_used: set[int]
    spid_used: set[int]
    next_comments_n: int
    next_threaded_m: int
    next_vml_k: int


def _allocate_new_parts(tree_root_dir: Path) -> _Allocation:
    """Run all three scanners + counters ONCE on the unpacked tree.

    Per ARCHITECTURE.md §I2.3: workbook-wide pre-scan happens once per
    `xlsx_add_comment.py` invocation, not per row in batch mode (which
    would be ~50× slower on `T-batch-50`). Hardcodes the three correct
    `*.xml` glob patterns so downstream callers cannot drift to the
    spec-literal `?.xml` foot-gun (see `next_part_counter` docstring).

    All four fields are READ-ONLY snapshots — Stage-2 task 2.06's
    incremental allocator MUTATES local copies of `idmap_used` /
    `spid_used` as new rows allocate, so the next row sees the already-
    chosen values. Do NOT mutate the returned dataclass in-place.
    """
    return _Allocation(
        idmap_used=scan_idmap_used(tree_root_dir),
        spid_used=scan_spid_used(tree_root_dir),
        next_comments_n=next_part_counter(tree_root_dir, "xl/comments*.xml"),
        next_threaded_m=next_part_counter(
            tree_root_dir, "xl/threadedComments*.xml"
        ),
        next_vml_k=next_part_counter(
            tree_root_dir, "xl/drawings/vmlDrawing*.xml"
        ),
    )


# --- F4: Path resolution + rels/CT idempotent patches (task 2.04) ---

_CELL_REF_SPLIT_RE = re.compile(r"^([A-Z]+)([0-9]+)$")


def _column_letters_to_index(letters: str) -> int:
    """`A` → 0, `B` → 1, `Z` → 25, `AA` → 26 (0-based, lex-base-26 over A..Z)."""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def _cell_ref_to_zero_based(cell_ref: str) -> tuple[int, int]:
    """`A5` → (col=0, row=4) — `<x:Column>` and `<x:Row>` in VML are 0-based."""
    m = _CELL_REF_SPLIT_RE.match(cell_ref)
    if not m:
        raise InvalidCellRef(f"cannot extract row/col from {cell_ref!r}")
    return _column_letters_to_index(m.group(1)), int(m.group(2)) - 1


def _resolve_target(
    rels_file_path: Path, tree_root_dir: Path, target: str,
) -> Path:
    """Resolve a Relationship `Target` attribute to an absolute file `Path`.

    OOXML allows two forms:
      - **Package-absolute**: `Target="/xl/comments/comment1.xml"` →
        path is `tree_root_dir / "xl/comments/comment1.xml"`.
      - **Relative**: `Target="../comments/comment1.xml"` → path is
        relative to the rels file's *document directory*, which is the
        rels file's parent minus the `_rels/` component (e.g.
        `xl/worksheets/_rels/sheet1.xml.rels` → doc dir is `xl/worksheets/`,
        so `../comments/comment1.xml` resolves to `xl/comments/comment1.xml`).
    """
    if target.startswith("/"):
        return tree_root_dir / target.lstrip("/")
    rels_parent = rels_file_path.parent
    doc_dir = rels_parent.parent if rels_parent.name == "_rels" else rels_parent
    return Path(_os.path.normpath(str(doc_dir / target)))


def _make_relative_target(
    rels_file_path: Path, target_part_path: Path,
) -> str:
    """Build a `Target=` value relative to the rels file's document directory.

    Inverse of `_resolve_target` for the relative form. We always emit the
    relative form because Excel itself does — keeps round-trips clean.

    **Forward-slash invariant** (Sarcasmotron MAJ-1 lock): OPC / ECMA-376
    Part 2 §9 mandates `/` as the path separator in `Target=` regardless
    of OS. `os.path.relpath` returns the platform-native separator
    (`\\` on Windows). We normalise to `/` here so emission is portable.
    """
    rels_parent = rels_file_path.parent
    doc_dir = rels_parent.parent if rels_parent.name == "_rels" else rels_parent
    rel = _os.path.relpath(str(target_part_path), start=str(doc_dir))
    return rel.replace(_os.sep, "/")


def _resolve_workbook_rels(tree_root_dir: Path) -> dict[str, str]:
    """Parse `xl/_rels/workbook.xml.rels` → `{rId: target}` (raw `Target` strings)."""
    rels_path = tree_root_dir / "xl" / "_rels" / "workbook.xml.rels"
    if not rels_path.is_file():
        return {}
    root = etree.parse(str(rels_path)).getroot()
    return {
        rel.get("Id"): rel.get("Target")
        for rel in root.findall(f"{{{PR_NS}}}Relationship")
    }


def _sheet_part_path(tree_root_dir: Path, sheet: dict) -> Path:
    """Return the absolute path to `xl/worksheets/sheet<S>.xml` for the sheet.

    Resolution: workbook.xml.rels[sheet.rId].Target → tree_root_dir/xl/<target>.
    Sheet metadata `dict` is shaped per `_load_sheets_from_workbook`.
    """
    wb_rels = _resolve_workbook_rels(tree_root_dir)
    target = wb_rels.get(sheet["rId"])
    if target is None:
        raise SheetNotFound(
            sheet["name"], available=[],
            suggestion=None,
        )
    rels_path = tree_root_dir / "xl" / "_rels" / "workbook.xml.rels"
    return _resolve_target(rels_path, tree_root_dir, target)


def _sheet_rels_path(worksheet_part_path: Path) -> Path:
    """`xl/worksheets/sheet1.xml` → `xl/worksheets/_rels/sheet1.xml.rels`."""
    return (
        worksheet_part_path.parent
        / "_rels"
        / f"{worksheet_part_path.name}.rels"
    )


def _open_or_create_rels(rels_path: Path) -> "etree._Element":
    """Load or create an empty `<Relationships>` root for a rels file."""
    if rels_path.is_file():
        return etree.parse(str(rels_path)).getroot()
    return etree.Element(f"{{{PR_NS}}}Relationships", nsmap={None: PR_NS})


def _allocate_rid(rels_root: "etree._Element") -> str:
    """`max(rIdN) + 1` over existing `<Relationship Id="rId...">` ids."""
    used: list[int] = []
    for rel in rels_root.findall(f"{{{PR_NS}}}Relationship"):
        rid = rel.get("Id", "")
        m = re.match(r"^rId(\d+)$", rid)
        if m:
            used.append(int(m.group(1)))
    return f"rId{max(used) + 1 if used else 1}"


def _find_rel_of_type(
    rels_root: "etree._Element", rel_type: str,
) -> "etree._Element | None":
    """Return the first `<Relationship>` whose `Type` matches, or None."""
    for rel in rels_root.findall(f"{{{PR_NS}}}Relationship"):
        if rel.get("Type") == rel_type:
            return rel
    return None


def _patch_sheet_rels(
    sheet_rels_path: Path,
    rels_root: "etree._Element",
    target_part_path: Path,
    rel_type: str,
) -> str:
    """Idempotent: ensure a `<Relationship>` for `target_part_path` of
    `rel_type` exists in `rels_root`. Returns the rId (existing or new).

    Caller is responsible for serialising `rels_root` back to disk; this
    function only mutates the in-memory tree.

    Note vs spec: task-001-09-legacy-write.md lists the signature as
    `_patch_sheet_rels(sheet_rels_root, target_part_path, rel_type)` —
    3 params. Implementation prepends `sheet_rels_path` (4 params) so
    `_make_relative_target` can compute the correct relative `Target=`
    string from the rels file location. Without that path, we'd have
    to hardcode the rels-document-dir relationship, which breaks for
    workbook-scoped rels (M6, used by 2.05's `personList` write path).
    Documented deviation; no behaviour drift from the contract.
    """
    target_str = _make_relative_target(sheet_rels_path, target_part_path)
    # Idempotent: if an identical (Type, Target) pair already exists, reuse.
    for rel in rels_root.findall(f"{{{PR_NS}}}Relationship"):
        if rel.get("Type") == rel_type and rel.get("Target") == target_str:
            return rel.get("Id")
    rid = _allocate_rid(rels_root)
    etree.SubElement(
        rels_root,
        f"{{{PR_NS}}}Relationship",
        Id=rid,
        Type=rel_type,
        Target=target_str,
    )
    return rid


def _patch_content_types(
    ct_root: "etree._Element",
    override_path: str,
    content_type: str,
    *,
    default_extension: str | None = None,
) -> None:
    """Idempotent: ensure `<Override PartName="...">` for `override_path` exists.

    m-3 idempotency rule: if `default_extension` is supplied AND the
    `[Content_Types].xml` already declares `<Default Extension="..." ContentType="..."/>`
    for that extension matching `content_type`, do NOT add a redundant
    per-part `<Override>` (Default already covers it). Per the
    `task-001-09-legacy-write.md` spec for VML drawings.
    """
    # Existing per-part Override → no-op.
    for ov in ct_root.findall(f"{{{CT_NS}}}Override"):
        if ov.get("PartName") == override_path:
            return
    # Default-Extension covers it (m-3) → no-op.
    if default_extension is not None:
        for de in ct_root.findall(f"{{{CT_NS}}}Default"):
            if (
                de.get("Extension") == default_extension
                and de.get("ContentType") == content_type
            ):
                return
    etree.SubElement(
        ct_root,
        f"{{{CT_NS}}}Override",
        PartName=override_path,
        ContentType=content_type,
    )


# --- F4: Legacy comments + VML write paths (task 2.04) ---


def ensure_legacy_comments_part(
    tree_root_dir: Path,
    sheet: dict,
    next_n: int,
) -> tuple[Path, "etree._Element", "etree._Element", Path]:
    """Get-or-create `xl/commentsN.xml` bound to `sheet`'s rels.

    Returns `(comments_path, comments_root, sheet_rels_root, sheet_rels_path)`.

    Look-up rule: read the sheet's rels file, find the existing
    `comments` Relationship if any, and resolve its `Target` to a real
    file path. Pre-existing parts are reused regardless of filename
    convention (Excel `xl/commentsN.xml` vs openpyxl `xl/comments/commentN.xml`).
    NEW parts are emitted in Excel convention (`xl/comments<N>.xml`)
    using the `next_n` counter from `_allocate_new_parts`.

    Caller is responsible for serialising the trees and writing the
    Content_Types Override (via `_patch_content_types`).

    Note vs spec: task-001-09-legacy-write.md lists the signature as
    `(tree_root, sheet_name) -> (path, root)` — 2-tuple, sheet name
    string. Implementation accepts a `sheet` dict (per
    `_load_sheets_from_workbook` shape) and an explicit `next_n`
    counter, and returns a 4-tuple including `sheet_rels_root` +
    `sheet_rels_path`. Reasons:
      - Sheet dict carries `rId` so we can resolve via
        `xl/_rels/workbook.xml.rels` instead of guessing filenames.
      - `next_n` is allocated ONCE per invocation by
        `_allocate_new_parts` — passing it in keeps the workbook-wide
        pre-scan invariant (ARCH §I2.3).
      - Returning the rels root + path saves the caller an extra
        round-trip parse/write when wiring the VML drawing rel
        immediately after.
    Documented deviation; no behaviour drift from the contract.
    """
    sheet_part_path = _sheet_part_path(tree_root_dir, sheet)
    sheet_rels_path = _sheet_rels_path(sheet_part_path)
    sheet_rels_root = _open_or_create_rels(sheet_rels_path)

    existing = _find_rel_of_type(sheet_rels_root, COMMENTS_REL_TYPE)
    if existing is not None:
        comments_path = _resolve_target(
            sheet_rels_path, tree_root_dir, existing.get("Target", "")
        )
        if not comments_path.is_file():
            raise MalformedVml(
                f"sheet rels references missing comments part: {comments_path}"
            )
        comments_root = etree.parse(str(comments_path)).getroot()
        return comments_path, comments_root, sheet_rels_root, sheet_rels_path

    # Create new in Excel convention.
    comments_path = tree_root_dir / "xl" / f"comments{next_n}.xml"
    comments_root = etree.Element(
        f"{{{SS_NS}}}comments", nsmap={None: SS_NS},
    )
    etree.SubElement(comments_root, f"{{{SS_NS}}}authors")
    etree.SubElement(comments_root, f"{{{SS_NS}}}commentList")
    _patch_sheet_rels(
        sheet_rels_path, sheet_rels_root, comments_path, COMMENTS_REL_TYPE,
    )
    return comments_path, comments_root, sheet_rels_root, sheet_rels_path


def add_legacy_comment(
    comments_root: "etree._Element",
    ref: str,
    author: str,
    text: str,
) -> int:
    """Append `<comment ref=... authorId=...>` with case-sensitive author dedup
    (m5). Returns the `authorId` chosen (existing if author-string already in
    `<authors>`, else newly appended index).

    Caller validates `text.strip() != ""` (Q2 / EmptyCommentBody) — this
    helper trusts pre-validated input.
    """
    authors_el = comments_root.find(f"{{{SS_NS}}}authors")
    if authors_el is None:
        authors_el = etree.SubElement(comments_root, f"{{{SS_NS}}}authors")
    existing_authors = list(authors_el.findall(f"{{{SS_NS}}}author"))
    author_id = None
    for i, a in enumerate(existing_authors):
        # Case-sensitive identity comparison on displayName (m5 lock).
        if (a.text or "") == author:
            author_id = i
            break
    if author_id is None:
        new_author = etree.SubElement(authors_el, f"{{{SS_NS}}}author")
        new_author.text = author
        author_id = len(existing_authors)

    comment_list = comments_root.find(f"{{{SS_NS}}}commentList")
    if comment_list is None:
        comment_list = etree.SubElement(
            comments_root, f"{{{SS_NS}}}commentList",
        )
    comment_el = etree.SubElement(
        comment_list, f"{{{SS_NS}}}comment",
        ref=ref, authorId=str(author_id),
    )
    text_el = etree.SubElement(comment_el, f"{{{SS_NS}}}text")
    r_el = etree.SubElement(text_el, f"{{{SS_NS}}}r")
    t_el = etree.SubElement(r_el, f"{{{SS_NS}}}t")
    t_el.text = text
    if text != text.strip() or "  " in text:
        # Preserve internal whitespace per ECMA-376 §17.4.5.
        t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return author_id


def ensure_vml_drawing(
    tree_root_dir: Path,
    sheet: dict,
    sheet_rels_root: "etree._Element",
    sheet_rels_path: Path,
    idmap_data: int,
    next_k: int,
) -> tuple[Path, "etree._Element", bool]:
    """Get-or-create `xl/drawings/vmlDrawingK.xml`.

    Returns `(vml_path, vml_root, is_new)`. When reusing an existing
    VML part (rels lookup hit), `idmap_data` and `next_k` are ignored —
    the existing `<o:idmap data>` is preserved and we only append
    new shapes.

    NEW parts use Excel convention (`vmlDrawing<K>.xml`) with a fresh
    `<o:idmap data="N">` value (workbook-wide unique per C1+M-1 — caller
    supplies `idmap_data` from `_allocate_new_parts`).
    """
    existing = _find_rel_of_type(sheet_rels_root, VML_REL_TYPE)
    if existing is not None:
        vml_path = _resolve_target(
            sheet_rels_path, tree_root_dir, existing.get("Target", "")
        )
        if not vml_path.is_file():
            raise MalformedVml(
                f"sheet rels references missing VML drawing: {vml_path}"
            )
        vml_root = _parse_vml(vml_path)
        return vml_path, vml_root, False

    # Create new VML in Excel convention.
    vml_dir = tree_root_dir / "xl" / "drawings"
    vml_dir.mkdir(parents=True, exist_ok=True)
    vml_path = vml_dir / f"vmlDrawing{next_k}.xml"
    # Build root with the standard skeleton: <o:shapelayout><o:idmap/></o:shapelayout>
    # plus the one-time <v:shapetype id="_x0000_t202"> definition shared by all
    # comment shapes appended later via add_vml_shape.
    nsmap = {"v": V_NS, "o": O_NS, "x": X_NS}
    vml_root = etree.Element("xml", nsmap=nsmap)
    shapelayout = etree.SubElement(vml_root, f"{{{O_NS}}}shapelayout")
    shapelayout.set(f"{{{V_NS}}}ext", "edit")
    idmap_el = etree.SubElement(shapelayout, f"{{{O_NS}}}idmap")
    idmap_el.set(f"{{{V_NS}}}ext", "edit")
    idmap_el.set("data", str(idmap_data))
    shapetype = etree.SubElement(vml_root, f"{{{V_NS}}}shapetype")
    shapetype.set("id", "_x0000_t202")
    shapetype.set("coordsize", "21600,21600")
    shapetype.set(f"{{{O_NS}}}spt", "202")
    shapetype.set("path", "m,l,21600r21600,l21600,xe")
    stroke = etree.SubElement(shapetype, f"{{{V_NS}}}stroke")
    stroke.set("joinstyle", "miter")
    path = etree.SubElement(shapetype, f"{{{V_NS}}}path")
    path.set("gradientshapeok", "t")
    path.set(f"{{{O_NS}}}connecttype", "rect")

    _patch_sheet_rels(
        sheet_rels_path, sheet_rels_root, vml_path, VML_REL_TYPE,
    )
    return vml_path, vml_root, True


def add_vml_shape(
    vml_root: "etree._Element",
    ref: str,
    spid: int,
) -> None:
    """Append `<v:shape>` for a comment with the locked default Excel anchor.

    Per R9.c (honest-scope lock): VML uses Excel's default anchor offsets
    only — no custom positioning. The anchor list `DEFAULT_VML_ANCHOR`
    matches what Excel emits for a fresh comment.
    """
    col, row = _cell_ref_to_zero_based(ref)
    sid = f"_x0000_s{spid}"
    shape = etree.SubElement(vml_root, f"{{{V_NS}}}shape")
    shape.set("id", sid)
    shape.set(f"{{{O_NS}}}spid", sid)
    shape.set("type", "#_x0000_t202")
    shape.set(
        "style",
        "position:absolute;margin-left:59.25pt;margin-top:1.5pt;"
        "width:144pt;height:79pt;z-index:1;visibility:hidden",
    )
    shape.set("fillcolor", "#ffffe1")
    shape.set(f"{{{O_NS}}}insetmode", "auto")
    fill = etree.SubElement(shape, f"{{{V_NS}}}fill")
    fill.set("color2", "#ffffe1")
    shadow = etree.SubElement(shape, f"{{{V_NS}}}shadow")
    shadow.set("color", "black")
    shadow.set("obscured", "t")
    pth = etree.SubElement(shape, f"{{{V_NS}}}path")
    pth.set(f"{{{O_NS}}}connecttype", "none")
    textbox = etree.SubElement(shape, f"{{{V_NS}}}textbox")
    textbox.set("style", "mso-direction-alt:auto")
    div = etree.SubElement(textbox, "div")
    div.set("style", "text-align:left")
    cd = etree.SubElement(shape, f"{{{X_NS}}}ClientData")
    cd.set("ObjectType", "Note")
    etree.SubElement(cd, f"{{{X_NS}}}MoveWithCells")
    etree.SubElement(cd, f"{{{X_NS}}}SizeWithCells")
    anchor = etree.SubElement(cd, f"{{{X_NS}}}Anchor")
    anchor.text = DEFAULT_VML_ANCHOR
    auto_fill = etree.SubElement(cd, f"{{{X_NS}}}AutoFill")
    auto_fill.text = "False"
    row_el = etree.SubElement(cd, f"{{{X_NS}}}Row")
    row_el.text = str(row)
    col_el = etree.SubElement(cd, f"{{{X_NS}}}Column")
    col_el.text = str(col)


def _xml_serialize(root: "etree._Element", path: Path) -> None:
    """Serialise an lxml tree to disk with a stable XML declaration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )
    )


# --- F4: Threaded comments + personList (task 2.05) ---


def ensure_threaded_comments_part(
    tree_root_dir: Path,
    sheet: dict,
    sheet_rels_root: "etree._Element",
    sheet_rels_path: Path,
    next_m: int,
) -> tuple[Path, "etree._Element", bool]:
    """Get-or-create `xl/threadedComments<M>.xml` bound to `sheet`'s rels.

    Returns `(threaded_path, threaded_root, is_new)`. Reuse rule mirrors
    `ensure_legacy_comments_part`: existing parts found via the sheet's
    rels file (NOT filename-glob), so non-Excel naming conventions
    (e.g. openpyxl-emitted) are respected. NEW parts in Excel convention.

    Note vs spec: task-001-10-threaded-write.md lists the signature as
    `(tree_root, sheet_name) -> (path, root)` — 2-tuple, sheet name
    string. Implementation follows the same expanded shape used by
    `ensure_legacy_comments_part` (sheet dict + rels root/path + next_m
    counter from `_allocate_new_parts`) — same justification (rels-driven
    resolution, ARCH §I2.3 single-pass pre-scan invariant).
    """
    existing = _find_rel_of_type(sheet_rels_root, THREADED_REL_TYPE)
    if existing is not None:
        threaded_path = _resolve_target(
            sheet_rels_path, tree_root_dir, existing.get("Target", ""),
        )
        if not threaded_path.is_file():
            raise MalformedVml(
                f"sheet rels references missing threaded part: {threaded_path}"
            )
        threaded_root = etree.parse(str(threaded_path)).getroot()
        return threaded_path, threaded_root, False

    threaded_path = tree_root_dir / "xl" / f"threadedComments{next_m}.xml"
    threaded_root = etree.Element(
        f"{{{THREADED_NS}}}ThreadedComments", nsmap={None: THREADED_NS},
    )
    _patch_sheet_rels(
        sheet_rels_path, sheet_rels_root, threaded_path, THREADED_REL_TYPE,
    )
    return threaded_path, threaded_root, True


def ensure_person_list(
    tree_root_dir: Path,
) -> tuple[Path, "etree._Element", "etree._Element", Path, bool]:
    """Get-or-create `xl/persons/personList.xml` (workbook-scoped per M6).

    Returns `(pl_path, pl_root, wb_rels_root, wb_rels_path, is_new)`.

    M6 — load-bearing: the `personList` Relationship lives on
    `xl/_rels/workbook.xml.rels`, NOT on a sheet rels file. Without
    this exact rel attachment Excel-365 fails to render the threaded
    UI even when `xl/persons/personList.xml` is present and well-formed.
    """
    wb_rels_path = tree_root_dir / "xl" / "_rels" / "workbook.xml.rels"
    wb_rels_root = _open_or_create_rels(wb_rels_path)

    existing = _find_rel_of_type(wb_rels_root, PERSON_REL_TYPE)
    if existing is not None:
        pl_path = _resolve_target(
            wb_rels_path, tree_root_dir, existing.get("Target", ""),
        )
        if not pl_path.is_file():
            raise MalformedVml(
                f"workbook rels references missing personList: {pl_path}"
            )
        pl_root = etree.parse(str(pl_path)).getroot()
        return pl_path, pl_root, wb_rels_root, wb_rels_path, False

    # M6 lock: workbook-scoped path.
    pl_path = tree_root_dir / "xl" / "persons" / "personList.xml"
    pl_root = etree.Element(
        f"{{{THREADED_NS}}}personList", nsmap={None: THREADED_NS},
    )
    # Patch via the existing helper — `_patch_sheet_rels` is rels-file
    # agnostic despite the name (documented under MAJ-3 in 2.04). M6
    # makes us point it at `xl/_rels/workbook.xml.rels`, not a sheet rels.
    _patch_sheet_rels(
        wb_rels_path, wb_rels_root, pl_path, PERSON_REL_TYPE,
    )
    return pl_path, pl_root, wb_rels_root, wb_rels_path, True


def add_person(person_list_root: "etree._Element", display_name: str) -> str:
    """Idempotent-add `<person>` to the registry; return its `id` GUID.

    Per spec / m1:
      - `id` is `{UUIDv5(NAMESPACE_URL, displayName)}` upper-cased + braced
        — STABLE across runs given the same displayName.
      - `userId` is `display_name.casefold()` — handles non-ASCII
        (German `ß` → `ss`, locale-aware lower) where `.lower()` would
        produce wrong results.
      - `providerId="None"` is the literal string (3 chars, capital N) —
        Excel uses this to mark "no SSO provider"; Python's `None` would
        serialise to the string "None" anyway via lxml but the lock test
        verifies the literal.
      - Dedup on `displayName` is **case-sensitive** (m5) — `Alice` and
        `alice` produce two distinct `<person>` records.
    """
    for p in person_list_root.findall(f"{{{THREADED_NS}}}person"):
        # m5: case-sensitive identity on displayName.
        if p.get("displayName") == display_name:
            return p.get("id")

    person_id = "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, display_name)).upper() + "}"
    user_id = display_name.casefold()
    etree.SubElement(
        person_list_root,
        f"{{{THREADED_NS}}}person",
        displayName=display_name,
        id=person_id,
        userId=user_id,
        providerId="None",
    )
    return person_id


# ECMA-376 Part 1 §18.3.1.99 worksheet child sequence — elements that
# MUST follow `<legacyDrawing>` per the schema. When inserting our
# element, we go BEFORE the first one of these found.
_AFTER_LEGACY_DRAWING_ELEMENTS = (
    "legacyDrawingHF", "drawingHF", "picture", "oleObjects",
    "controls", "webPublishItems", "tableParts", "extLst",
)


def ensure_sheet_legacy_drawing_ref(
    sheet_xml_path: "Path",
    vml_rel_id: str,
) -> None:
    """Ensure `<legacyDrawing r:id="..."/>` is present in worksheet XML.

    Without this anchor element, Excel / LibreOffice see the
    `vmlDrawing` Relationship in `_rels/sheetN.xml.rels` but do NOT
    render the comment hover-bubbles — the yellow speech-balloon
    indicators in the cell never appear because the worksheet itself
    doesn't bind the VML drawing to its render layer. ECMA-376 Part 1
    §18.3.1.27 requires this element on every worksheet that references
    a VML legacy drawing.

    Idempotent: if `<legacyDrawing>` already exists, its `r:id` is
    updated to the supplied value (rare — only relevant if the part
    was rewritten with a different rel id).

    Insertion point per the worksheet child sequence (§18.3.1.99): we
    place `<legacyDrawing>` BEFORE the first element that must follow
    it (legacyDrawingHF / drawingHF / picture / oleObjects / controls /
    webPublishItems / tableParts / extLst). If none of those are
    present we append at the end of the worksheet, which leaves it
    after pageSetup / headerFooter / rowBreaks / etc. — the schema-
    correct position.

    History: this helper was missing in the Task-001 implementation
    of `xlsx_add_comment.py`. The bug was invisible to the openpyxl-
    based unit tests (they read `xl/comments1.xml` directly without
    needing the VML anchor) but visible to actual Excel rendering on
    end-user files. Surfaced during real-world testing of the
    `tmp/Анализ релизов.xlsx` fixture; fix landed post-Task-002 chain.
    """
    tree = etree.parse(str(sheet_xml_path))
    root = tree.getroot()

    existing = root.find(f"{{{SS_NS}}}legacyDrawing")
    if existing is not None:
        # INVARIANT (vdd-adversarial-r2 LOW#1): updating r:id on an
        # existing element is safe because `ensure_vml_drawing` calls
        # `_find_rel_of_type` first and REUSES any existing vmlDrawing
        # rel verbatim — so `vml_rel_id` is the SAME rId the existing
        # `<legacyDrawing>` was already pointing at. We are NOT changing
        # the workbook semantics, just self-healing the attribute if it
        # had been hand-edited away from the rels target. If a future
        # change makes `ensure_vml_drawing` allocate a fresh rel even
        # when one exists, this branch becomes destructive — re-audit.
        existing.set(f"{{{R_NS}}}id", vml_rel_id)
    else:
        new_el = etree.Element(f"{{{SS_NS}}}legacyDrawing")
        new_el.set(f"{{{R_NS}}}id", vml_rel_id)
        anchor = None
        for tag in _AFTER_LEGACY_DRAWING_ELEMENTS:
            anchor = root.find(f"{{{SS_NS}}}{tag}")
            if anchor is not None:
                break
        if anchor is not None:
            anchor.addprevious(new_el)
        else:
            root.append(new_el)

    sheet_xml_path.write_bytes(
        etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True,
        )
    )


def add_threaded_comment(
    threaded_root: "etree._Element",
    ref: str,
    person_id: str,
    text: str,
    date_iso: str,
) -> str:
    """Append `<threadedComment ref=... dT=... personId=... id=...>{text}` and
    return the threadedComment `id`.

    R9.a — v1 does NOT emit `parentId`; every threadedComment is top-level.
    R9.b — body is plain text (no `<r>` / `<rPr>` rich-run wrappers).
    R9.e — `id` is UUIDv4: non-deterministic by design. Re-running the
        script produces a different `id` each time even with `--date`
        pinned. Goldens diff in task 2.10 masks this attribute via
        canonical-XML rewrite.
    """
    threaded_id = "{" + str(uuid.uuid4()).upper() + "}"
    tc = etree.SubElement(
        threaded_root,
        f"{{{THREADED_NS}}}threadedComment",
        ref=ref,
        dT=date_iso,
        personId=person_id,
        id=threaded_id,
    )
    text_el = etree.SubElement(tc, f"{{{THREADED_NS}}}text")
    text_el.text = text
    return threaded_id

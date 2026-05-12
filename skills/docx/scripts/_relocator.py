"""Asset relocation for `docx_replace.py --insert-after`.

Scope:
- Image / Relationship relocator (docx-6.5): media file copy, rels
  append with rId offset, r:embed/r:link/r:id remap, content-types
  merge, chart/OLE/SmartArt part copy.
- Numbering relocator (docx-6.6): abstractNum/num offset shift,
  w:numId remap, install verbatim if base has no numbering.xml.

Pattern source: docx_merge.py (re-used BY COPY per Decision D3 of
docs/TASK.md §0.1 — single-insert context vs N-extras context of
docx_merge). The regression-lock `test_relocator_does_not_import_docx_merge`
asserts the no-import invariant via AST walk.

Module is **docx-only** (not under `office/`), so the cross-skill
replication boundary (CLAUDE.md §2) is preserved. Sibling to
`docx_anchor.py`, `_actions.py`, `_app_errors.py`.

Stage 0 (task-008-01a) state: every function in this module is a
stub returning zero/empty defaults. Logic lands per sub-task per
docs/PLAN.md:
  - 008-01b: _assert_safe_target (F16)
  - 008-02: _copy_extra_media, _max_existing_rid, _merge_relationships,
            _remap_rids_in_clones, _merge_content_types_defaults
  - 008-03: _copy_nonmedia_parts, _read_rel_targets,
            _apply_nonmedia_rename_to_rels
  - 008-04: relocate_assets (E1 branch); _extract_insert_paragraphs wiring
  - 008-05: _merge_numbering, _ensure_numbering_part, _remap_numid_in_clones
  - 008-06: relocate_assets (E2 branch)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from lxml import etree  # type: ignore
from docx.oxml.ns import qn  # type: ignore

from _app_errors import Md2DocxOutputInvalid

# Hardened XML parser — defence vs XXE / external-entity / DTD-based
# attacks (CWE-611). Mirrors `_actions.py:_SAFE_PARSER`. Used for every
# etree.parse() AND etree.fromstring() in this module (vdd-multi Sec M2
# fix: roundtrip clones via tostring/fromstring also use _SAFE_PARSER).
_SAFE_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, load_dtd=False,
)


def _is_int(s: "str | None") -> bool:
    """Return True iff `s` parses as a base-10 integer. Used by F14 to
    pre-validate insert abstractNumId values before pass-2 dangling-ref
    check (vdd-multi H-4 fix)."""
    if s is None:
        return False
    try:
        int(s)
        return True
    except ValueError:
        return False

# Namespace constants — wordprocessingml + relationships + package.
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

# Mergeable relationship types — the eight rel types md2docx may produce
# whose targets we relocate from insert to base. Byte-port of
# `docx_merge.py:70-79` per Decision D3 (re-use by copy).
_MERGEABLE_REL_TYPES = frozenset({
    f"{R_NS}/image",
    f"{R_NS}/hyperlink",
    f"{R_NS}/diagramData",
    f"{R_NS}/diagramLayout",
    f"{R_NS}/diagramQuickStyle",
    f"{R_NS}/diagramColors",
    f"{R_NS}/chart",
    f"{R_NS}/oleObject",
})

# Attributes whose value is a single rId reference. Source: ECMA-376
# Part 1 §17 (WordprocessingML). Used by _remap_rids_in_clones.
_RID_ATTRS = (
    f"{{{R_NS}}}embed",
    f"{{{R_NS}}}link",
    f"{{{R_NS}}}id",
    f"{{{R_NS}}}dm",      # diagram data
    f"{{{R_NS}}}lo",      # diagram layout
    f"{{{R_NS}}}qs",      # diagram quick style
    f"{{{R_NS}}}cs",      # diagram colors
)


@dataclass(frozen=True)
class RelocationReport:
    """Summary of one --insert-after relocation pass. Returned from
    `relocate_assets` to `_extract_insert_paragraphs`. The caller
    `_run` uses these counts to format the stderr success-line
    annotation (Q-A2, lands in 008-07).

    Invariants (testable; see ARCH §12.3.1):
    - All eight fields >= 0.
    - rels_appended == len(rid_map) maintained inside `_merge_relationships`.
    - media_copied == count of present-file image rels.
    - nonmedia_parts_copied == count of present-file chart/OLE/SmartArt rels.
    - media_copied + nonmedia_parts_copied <= rels_appended.
    - num_added == len(num_id_remap).
    - A zero-relocation invocation produces RelocationReport(0, 0, 0, 0,
      0, 0, 0, 0).
    """
    media_copied: int
    rels_appended: int
    rid_rewrites: int
    content_types_added: int
    abstractnum_added: int
    num_added: int
    numid_rewrites: int
    nonmedia_parts_copied: int


# ---------------------------------------------------------------------------
# F9 — Orchestrator entry point
# ---------------------------------------------------------------------------

def relocate_assets(
    insert_tree_root: Path,
    base_tree_root: Path,
    clones: "list[etree._Element]",
) -> RelocationReport:
    """F9 — Orchestrate image (E1) then numbering (E2) relocation.
    See ARCH §12.4 F9. Mutates `base_tree_root` files in place;
    rewrites rid/numid attrs inside `clones`. Returns counts."""
    base_rels_path = base_tree_root / "word" / "_rels" / "document.xml.rels"
    insert_rels_path = insert_tree_root / "word" / "_rels" / "document.xml.rels"

    # --- E1: Image / Relationship relocator (docx-6.5) ---
    media_rename = _copy_extra_media(base_tree_root, insert_tree_root)
    rid_offset = 1
    if base_rels_path.is_file():
        rid_offset = _max_existing_rid(
            etree.parse(str(base_rels_path), _SAFE_PARSER).getroot()
        ) + 1
    insert_rel_targets = _read_rel_targets(insert_rels_path)
    rid_map = _merge_relationships(
        base_rels_path, insert_rels_path,
        media_rename, rid_offset, base_tree_root,
    )
    nonmedia_rename = _copy_nonmedia_parts(
        base_tree_root, insert_tree_root, insert_rel_targets,
    )
    _apply_nonmedia_rename_to_rels(base_rels_path, nonmedia_rename)
    rid_rewrites = _remap_rids_in_clones(clones, rid_map)
    ct_added = _merge_content_types_defaults(
        base_tree_root / "[Content_Types].xml",
        insert_tree_root / "[Content_Types].xml",
    )
    media_copied_count = sum(
        1 for (rtype, tgt) in insert_rel_targets
        if rtype == f"{R_NS}/image"
        and (insert_tree_root / "word" / tgt).is_file()
    )
    nonmedia_count = sum(
        1 for (rtype, tgt) in insert_rel_targets
        if rtype not in (f"{R_NS}/image", f"{R_NS}/hyperlink")
        and rtype in _MERGEABLE_REL_TYPES
        and (insert_tree_root / "word" / tgt).is_file()
    )

    # --- E2: Numbering relocator (docx-6.6) ---
    num_id_remap, abstractnum_added, num_added = _merge_numbering(
        base_tree_root, insert_tree_root,
    )
    numid_rewrites = _remap_numid_in_clones(clones, num_id_remap)

    return RelocationReport(
        media_copied=media_copied_count,
        rels_appended=len(rid_map),
        rid_rewrites=rid_rewrites,
        content_types_added=ct_added,
        abstractnum_added=abstractnum_added,
        num_added=num_added,
        numid_rewrites=numid_rewrites,
        nonmedia_parts_copied=nonmedia_count,
    )


# ---------------------------------------------------------------------------
# F10 — Media file copy (image relocator core, R1)
# ---------------------------------------------------------------------------

def _copy_extra_media(
    base_dir: Path, insert_dir: Path,
) -> "dict[str, str]":
    """F10 — Copy `insert/word/media/*` into `base/word/media/` with
    fixed `insert_` prefix; collision-safe via counter loop.

    Returns `{"media/<orig>": "media/insert_<orig>"}` map for every
    file actually copied (so callers can rewrite Target attrs in rels).
    Pattern source `docx_merge.py:155-181` (re-used by copy per D3),
    with `extra<i>_` prefix collapsed to fixed `insert_` (D3 rationale:
    single-insert context vs N-extras).
    """
    src_dir = insert_dir / "word" / "media"
    if not src_dir.is_dir():
        return {}
    dst_dir = base_dir / "word" / "media"
    dst_dir.mkdir(parents=True, exist_ok=True)
    rename_map: dict[str, str] = {}
    for src in sorted(src_dir.iterdir()):
        # vdd-multi Security H1 fix: reject symlinks (defence-in-depth
        # against an attacker who crafts insert/word/media/x.png pointing
        # at /etc/passwd via symlink-during-unpack).
        if src.is_symlink():
            continue
        if not src.is_file():
            continue
        # vdd-multi Security H1 fix: validate src.name through F16 to
        # reject malicious filenames (e.g., NUL bytes, traversal chars).
        _assert_safe_target(f"media/{src.name}", base_dir)
        new_name = f"insert_{src.name}"
        n = 1
        while (dst_dir / new_name).exists():
            n += 1
            new_name = f"insert_{n}_{src.name}"
        dst = dst_dir / new_name
        dst.write_bytes(src.read_bytes())
        rename_map[f"media/{src.name}"] = f"media/{new_name}"
    return rename_map


# ---------------------------------------------------------------------------
# F11 — Max-rId scan over base rels (R2)
# ---------------------------------------------------------------------------

def _max_existing_rid(rels_root: "etree._Element") -> int:
    """F11 — Return the largest numeric N in any `Id="rId<N>"` in
    `rels_root`. Returns 0 if no numeric rIds. Byte-port of
    `docx_merge.py:142-152` per Decision D3.
    """
    biggest = 0
    for rel in rels_root.findall(f"{{{PR_NS}}}Relationship"):
        rid = rel.get("Id") or ""
        m = re.match(r"rId(\d+)$", rid)
        if m:
            biggest = max(biggest, int(m.group(1)))
    return biggest


# ---------------------------------------------------------------------------
# F12 — Merge relationships (image relocator core, R3)
# ---------------------------------------------------------------------------

def _merge_relationships(
    base_rels_path: Path,
    insert_rels_path: Path,
    media_rename: "dict[str, str]",
    rid_offset: int,
    base_tree_root: Path,
) -> "dict[str, str]":
    """F12 — Append mergeable rels from insert to base with rId
    offset; rewrite Target attrs via `media_rename` (image rels only).
    Path-traversal guard `_assert_safe_target` invoked on every
    non-External Target.

    Returns `{old_extra_rId: new_base_rId}` map for EVERY mergeable rel
    encountered (MAJ-2 contract — every mergeable rel populates the map,
    regardless of whether its target file is copied).
    """
    if not insert_rels_path.is_file():
        return {}
    insert_tree = etree.parse(str(insert_rels_path), _SAFE_PARSER)
    insert_root = insert_tree.getroot()
    if base_rels_path.is_file():
        base_tree = etree.parse(str(base_rels_path), _SAFE_PARSER)
        base_root = base_tree.getroot()
    else:
        # No base rels yet — create the root and ensure the parent dir.
        base_rels_path.parent.mkdir(parents=True, exist_ok=True)
        base_root = etree.Element(f"{{{PR_NS}}}Relationships")
        base_tree = etree.ElementTree(base_root)
    existing_ids = {
        r.get("Id")
        for r in base_root.findall(f"{{{PR_NS}}}Relationship")
        if r.get("Id")
    }
    rid_map: dict[str, str] = {}
    next_n = rid_offset
    for rel in insert_root.findall(f"{{{PR_NS}}}Relationship"):
        rtype = rel.get("Type") or ""
        if rtype not in _MERGEABLE_REL_TYPES:
            continue
        target = rel.get("Target") or ""
        target_mode = rel.get("TargetMode")
        # External hyperlinks have TargetMode="External"; the Target is a
        # URL, not a filesystem path — skip the path-traversal guard.
        if target_mode != "External":
            _assert_safe_target(target, base_tree_root)
        old_id = rel.get("Id") or ""
        new_id = f"rId{next_n}"
        while new_id in existing_ids:
            next_n += 1
            new_id = f"rId{next_n}"
        existing_ids.add(new_id)
        next_n += 1
        # Populate rid_map for EVERY mergeable rel (MAJ-2 contract).
        rid_map[old_id] = new_id
        new_rel = etree.SubElement(base_root, f"{{{PR_NS}}}Relationship")
        new_rel.set("Id", new_id)
        new_rel.set("Type", rtype)
        # Image rels with collision rename → rewrite Target; otherwise
        # leave the Target unchanged (verbatim copies keep their path).
        if rtype == f"{R_NS}/image" and target in media_rename:
            new_rel.set("Target", media_rename[target])
        else:
            new_rel.set("Target", target)
        if target_mode is not None:
            new_rel.set("TargetMode", target_mode)
    base_tree.write(
        str(base_rels_path), xml_declaration=True,
        encoding="UTF-8", standalone=True,
    )
    return rid_map


# ---------------------------------------------------------------------------
# F13 — Non-media part copy (R3.5)
# ---------------------------------------------------------------------------

def _copy_nonmedia_parts(
    base_dir: Path, insert_dir: Path,
    rel_targets: "list[tuple[str, str]]",
) -> "dict[str, str]":
    """F13 — Copy chart (chartN.xml + chartN.xml.rels), OLE
    (oleObject*), and SmartArt (diagrams/*) parts from insert to base.
    Verbatim default; rename only on collision.

    Returns sparse `rename_map`: entries appear ONLY when
    `final_target != target` (MAJ-3 contract — verbatim copies are
    absent from the map). Sibling `_rels/<basename>.rels` files copied
    verbatim per Decision D7 (no recursive remap in v2).

    Note: `base_dir` doubles as the path-traversal guard root.
    """
    rename_map: dict[str, str] = {}
    for rtype, target in rel_targets:
        if rtype == f"{R_NS}/image":  # handled by F10
            continue
        if rtype == f"{R_NS}/hyperlink":  # no part to copy (external URL)
            continue
        if rtype not in _MERGEABLE_REL_TYPES:
            continue
        _assert_safe_target(target, base_dir)
        src = insert_dir / "word" / target
        # vdd-multi Security H1 fix: reject symlinks (defence-in-depth).
        if src.is_symlink():
            continue
        if not src.is_file():
            continue  # orphan rel — rid_map still populated by F12 (defensive).
        # Verbatim destination by default; rename only if it collides in base.
        dst = base_dir / "word" / target
        final_target = target
        n = 0
        while dst.exists():
            n += 1
            stem = Path(target).stem
            suffix = Path(target).suffix
            renamed_basename = (
                f"insert_{stem}{suffix}" if n == 1
                else f"insert_{n}_{stem}{suffix}"
            )
            parent = str(Path(target).parent)
            if parent == ".":
                final_target = renamed_basename
            else:
                final_target = f"{parent}/{renamed_basename}"
            dst = base_dir / "word" / final_target
        if final_target != target:
            rename_map[target] = final_target
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        # Copy sibling _rels/<basename>.rels verbatim (D7).
        sibling_rels = src.parent / "_rels" / (src.name + ".rels")
        if sibling_rels.is_file():
            dst_rels = dst.parent / "_rels" / (dst.name + ".rels")
            dst_rels.parent.mkdir(parents=True, exist_ok=True)
            dst_rels.write_bytes(sibling_rels.read_bytes())
    return rename_map


# ---------------------------------------------------------------------------
# Helpers — read rel targets, apply rename map to rels
# ---------------------------------------------------------------------------

def _read_rel_targets(rels_path: Path) -> "list[tuple[str, str]]":
    """Return `[(Type, Target), ...]` from a rels file, in document
    order. Empty list on missing/empty/unparseable file. Used by F9
    orchestrator to pre-scan insert rels for F13 non-media part copy.
    """
    if not rels_path.is_file():
        return []
    try:
        root = etree.parse(str(rels_path), _SAFE_PARSER).getroot()
    except etree.XMLSyntaxError:
        return []
    result: list[tuple[str, str]] = []
    for rel in root.findall(f"{{{PR_NS}}}Relationship"):
        rtype = rel.get("Type") or ""
        target = rel.get("Target") or ""
        if rtype and target:
            result.append((rtype, target))
    return result


def _apply_nonmedia_rename_to_rels(
    base_rels_path: Path,
    nonmedia_rename: "dict[str, str]",
) -> None:
    """Rewrite Target attrs in base rels for every entry in
    `nonmedia_rename`. No-op when map is empty (the common case —
    verbatim copies are NOT in the map per MAJ-3 contract). Called
    from F9 orchestrator AFTER `_merge_relationships` (which appends
    rels with the ORIGINAL Target) and AFTER F13 (which may rename
    on collision). Only collision-renamed Targets are rewritten.
    """
    if not nonmedia_rename:
        return
    if not base_rels_path.is_file():
        return
    tree = etree.parse(str(base_rels_path), _SAFE_PARSER)
    root = tree.getroot()
    changed = False
    for rel in root.findall(f"{{{PR_NS}}}Relationship"):
        old = rel.get("Target") or ""
        if old in nonmedia_rename:
            rel.set("Target", nonmedia_rename[old])
            changed = True
    if changed:
        tree.write(
            str(base_rels_path), xml_declaration=True,
            encoding="UTF-8", standalone=True,
        )


# ---------------------------------------------------------------------------
# rId remap in cloned paragraphs (R4)
# ---------------------------------------------------------------------------

def _remap_rids_in_clones(
    clones: "list[etree._Element]", rid_map: "dict[str, str]",
) -> int:
    """R4 — Rewrite every `r:embed/r:link/r:id/r:dm/r:lo/r:qs/r:cs`
    attribute in clones using `rid_map`. Returns rewrite count.
    Unmapped rIds are left alone (defensive — mirror docx_merge:259-273).
    """
    if not rid_map:
        return 0
    count = 0
    for clone in clones:
        for el in clone.iter():
            for attr in _RID_ATTRS:
                val = el.get(attr)
                if val and val in rid_map:
                    el.set(attr, rid_map[val])
                    count += 1
    return count


# ---------------------------------------------------------------------------
# Content-Types `<Default>` merge (R5)
# ---------------------------------------------------------------------------

def _merge_content_types_defaults(
    base_ct_path: Path, insert_ct_path: Path,
) -> int:
    """R5 — Copy `<Default Extension>` entries from insert into base
    where the extension (case-fold) does not already exist. Persist
    base CT file only if any entries were appended. Returns count.

    Without this, media files we copy from insert (e.g. .png when base
    only had .jpeg) have no MIME mapping → Word reports "unreadable
    content". Pattern source `docx_merge.py:469-503` (D3 by copy).
    """
    if not base_ct_path.is_file() or not insert_ct_path.is_file():
        return 0
    base_tree = etree.parse(str(base_ct_path), _SAFE_PARSER)
    insert_tree = etree.parse(str(insert_ct_path), _SAFE_PARSER)
    base_root = base_tree.getroot()
    insert_root = insert_tree.getroot()
    base_exts = {
        d.get("Extension", "").lower()
        for d in base_root.findall(f"{{{CT_NS}}}Default")
    }
    appended = 0
    for d in insert_root.findall(f"{{{CT_NS}}}Default"):
        ext = (d.get("Extension") or "").lower()
        if ext and ext not in base_exts:
            new = etree.SubElement(base_root, f"{{{CT_NS}}}Default")
            new.set("Extension", d.get("Extension") or ext)
            new.set("ContentType", d.get("ContentType") or "")
            base_exts.add(ext)
            appended += 1
    if appended:
        base_tree.write(
            str(base_ct_path), xml_declaration=True,
            encoding="UTF-8", standalone=True,
        )
    return appended


# ---------------------------------------------------------------------------
# F14 — Numbering merge (R9–R12)
# ---------------------------------------------------------------------------

def _merge_numbering(
    base_tree_root: Path, insert_tree_root: Path,
) -> "tuple[dict[str, str], int, int]":
    """F14 — Merge `insert/word/numbering.xml` into base, with
    abstractNumId/numId offset, preserving ECMA-376 §17.9.20
    abstractNum-before-num element ordering.

    If base has no `numbering.xml`: install insert's verbatim and call
    `_ensure_numbering_part`.

    Returns `(num_id_remap, abstractnum_count, num_count)`. Direct port
    of `docx_merge.py:332-466` per Decision D3 (re-use by copy), with
    pass-3 deferred to F15 `_remap_numid_in_clones` (caller's body
    rewriting is decoupled from this function).

    ECMA-376 §17.9.20 trap: every `<w:abstractNum>` MUST precede every
    `<w:num>`; `<w:numIdMacAtCleanup>` is the optional tail. Naïve
    `.append()` puts new abstractNums AFTER existing nums → schema
    violation → Word silent-repair rebinds list refs to wrong abstract
    defs (observed: headings render as bulleted "o" markers).
    """
    insert_path = insert_tree_root / "word" / "numbering.xml"
    if not insert_path.is_file():
        return ({}, 0, 0)
    # vdd-multi Security H2 fix: cap insert numbering.xml size at 8 MiB
    # to prevent DoS via OOM from malicious .docx with millions of
    # abstractNum defs (8 MiB is half the 16 MiB body cap in TASK §3.1).
    _insert_size = insert_path.stat().st_size  # cached (vdd-multi P1).
    if _insert_size > 8 * 1024 * 1024:
        raise Md2DocxOutputInvalid(
            f"insert numbering.xml exceeds 8 MiB cap "
            f"({_insert_size} bytes); refusing parse to prevent OOM DoS",
            code=1, error_type="Md2DocxOutputInvalid",
            details={
                "path": str(insert_path),
                "size_bytes": _insert_size,
                "reason": "numbering_size_cap",
            },
        )
    insert_root = etree.parse(str(insert_path), _SAFE_PARSER).getroot()
    insert_nums = insert_root.findall(qn("w:num"))
    insert_anums = insert_root.findall(qn("w:abstractNum"))
    if not insert_nums and not insert_anums:
        return ({}, 0, 0)

    base_path = base_tree_root / "word" / "numbering.xml"

    if not base_path.is_file():
        # Base has no numbering — install insert's whole numbering.xml as base's.
        # Wire it into [Content_Types].xml + word/_rels/document.xml.rels.
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.write_bytes(insert_path.read_bytes())
        _ensure_numbering_part(base_tree_root)
        # num_id_remap is identity (since no offset applied).
        identity_remap = {
            n.get(qn("w:numId")): n.get(qn("w:numId"))
            for n in insert_nums
            if n.get(qn("w:numId"))
        }
        return (identity_remap, len(insert_anums), len(insert_nums))

    base_root = etree.parse(str(base_path), _SAFE_PARSER).getroot()
    base_anum_ids = {
        a.get(qn("w:abstractNumId"))
        for a in base_root.findall(qn("w:abstractNum"))
        if a.get(qn("w:abstractNumId"))
    }
    base_num_ids = {
        n.get(qn("w:numId"))
        for n in base_root.findall(qn("w:num"))
        if n.get(qn("w:numId"))
    }

    def _max_int(strs: "set[str | None]") -> int:
        biggest = -1
        for s in strs:
            if s is None:
                continue
            try:
                biggest = max(biggest, int(s))
            except ValueError:
                continue
        return biggest

    anum_offset = _max_int(base_anum_ids) + 1
    num_offset = _max_int(base_num_ids) + 1

    # ECMA-376 §17.9.20 ordering: find insertion sites.
    # Order MUST be: abstractNum* > num* > numIdMacAtCleanup?
    # Insert sites are computed from a snapshot of children BEFORE any
    # inserts (we advance both indices by 1 per pass-1 insert).
    children = list(base_root)
    first_num_idx = next(
        (i for i, c in enumerate(children) if c.tag == qn("w:num")),
        None,
    )
    cleanup_idx = next(
        (i for i, c in enumerate(children)
         if c.tag == qn("w:numIdMacAtCleanup")),
        None,
    )
    last_num_idx = max(
        (i for i, c in enumerate(children) if c.tag == qn("w:num")),
        default=-1,
    )
    # vdd-multi C-2 fix (Logic critic HIGH): if base has cleanup but no
    # <w:num>, naïve `first_num_idx = len(children)` would append
    # abstractNums AFTER cleanup, violating §17.9.20. Insertion site for
    # abstractNum MUST be ≤ cleanup_idx AND ≤ first_num_idx (when present).
    if first_num_idx is None:
        # No <w:num> in base — abstractNums go BEFORE cleanup if present,
        # else at end.
        abstract_insert_at = cleanup_idx if cleanup_idx is not None else len(children)
        num_insert_idx = cleanup_idx if cleanup_idx is not None else len(children)
    else:
        abstract_insert_at = first_num_idx
        num_insert_idx = (
            cleanup_idx if cleanup_idx is not None else last_num_idx + 1
        )

    # Pass 1: insert abstractNum defs (silently skip malformed; remember
    # which insert-side abstractNumId values were skipped so pass-2 can
    # also skip dependent nums — vdd-multi H-4 fix).
    abstractnum_count = 0
    insert_at = abstract_insert_at
    skipped_insert_anum_ids: set[str] = set()
    for a in insert_anums:
        old = a.get(qn("w:abstractNumId"))
        if old is None:
            continue
        try:
            new = int(old) + anum_offset
        except ValueError:
            skipped_insert_anum_ids.add(old)
            continue
        # vdd-multi Sec M2 / Perf H1 fix: pass _SAFE_PARSER to preserve
        # XXE-hardened parser on the roundtrip clone.
        cloned = etree.fromstring(etree.tostring(a), _SAFE_PARSER)
        cloned.set(qn("w:abstractNumId"), str(new))
        base_root.insert(insert_at, cloned)
        insert_at += 1
        num_insert_idx += 1  # each insert before num_insert_idx pushes right.
        abstractnum_count += 1

    # Pass 2: insert num defs at num_insert_idx with both id-shifts.
    # vdd-multi H-4 fix: skip num whose <w:abstractNumId w:val> references
    # a skipped insert abstractNumId, OR whose target anum doesn't exist
    # in the insert tree (dangling-ref protection).
    insert_anum_ids_valid = {
        a.get(qn("w:abstractNumId"))
        for a in insert_anums
        if a.get(qn("w:abstractNumId")) is not None
        and a.get(qn("w:abstractNumId")) not in skipped_insert_anum_ids
        and _is_int(a.get(qn("w:abstractNumId")))
    }
    num_count = 0
    num_id_remap: dict[str, str] = {}
    for n in insert_nums:
        old_num = n.get(qn("w:numId"))
        anum_ref = n.find(qn("w:abstractNumId"))
        if old_num is None or anum_ref is None:
            continue
        anum_ref_val = anum_ref.get(qn("w:val"))
        if anum_ref_val is None:
            continue
        if anum_ref_val not in insert_anum_ids_valid:
            # Dangling reference — would point at a skipped or missing
            # abstractNum after offset-shift. Drop the num to avoid
            # Word silent-repair attaching the list to the wrong def.
            continue
        try:
            new_num = int(old_num) + num_offset
            new_anum_ref = int(anum_ref_val) + anum_offset
        except ValueError:
            continue
        cloned = etree.fromstring(etree.tostring(n), _SAFE_PARSER)
        cloned.set(qn("w:numId"), str(new_num))
        cloned.find(qn("w:abstractNumId")).set(qn("w:val"), str(new_anum_ref))
        base_root.insert(num_insert_idx, cloned)
        num_insert_idx += 1
        num_id_remap[old_num] = str(new_num)
        num_count += 1

    base_tree = etree.ElementTree(base_root)
    base_tree.write(
        str(base_path), xml_declaration=True,
        encoding="UTF-8", standalone=True,
    )
    return (num_id_remap, abstractnum_count, num_count)


def _ensure_numbering_part(base_dir: Path) -> None:
    """Wire `word/numbering.xml` into `[Content_Types].xml` Override +
    `word/_rels/document.xml.rels` Relationship, idempotently. Direct
    port of `docx_merge.py:506-544` per Decision D3.
    """
    ct_path = base_dir / "[Content_Types].xml"
    if ct_path.is_file():
        ct_tree = etree.parse(str(ct_path), _SAFE_PARSER)
        ct_root = ct_tree.getroot()
        if not any(
            o.get("PartName") == "/word/numbering.xml"
            for o in ct_root.findall(f"{{{CT_NS}}}Override")
        ):
            ovr = etree.SubElement(ct_root, f"{{{CT_NS}}}Override")
            ovr.set("PartName", "/word/numbering.xml")
            ovr.set(
                "ContentType",
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.numbering+xml",
            )
            ct_tree.write(
                str(ct_path), xml_declaration=True,
                encoding="UTF-8", standalone=True,
            )

    rels_path = base_dir / "word" / "_rels" / "document.xml.rels"
    if rels_path.is_file():
        rels_tree = etree.parse(str(rels_path), _SAFE_PARSER)
        rels_root = rels_tree.getroot()
        rtype = f"{R_NS}/numbering"
        if not any(
            r.get("Type") == rtype
            for r in rels_root.findall(f"{{{PR_NS}}}Relationship")
        ):
            existing = {
                r.get("Id")
                for r in rels_root.findall(f"{{{PR_NS}}}Relationship")
            }
            n = 1
            while f"rId{n}" in existing:
                n += 1
            new = etree.SubElement(rels_root, f"{{{PR_NS}}}Relationship")
            new.set("Id", f"rId{n}")
            new.set("Type", rtype)
            new.set("Target", "numbering.xml")
            rels_tree.write(
                str(rels_path), xml_declaration=True,
                encoding="UTF-8", standalone=True,
            )


# ---------------------------------------------------------------------------
# F15 — numId remap in cloned paragraphs (R13)
# ---------------------------------------------------------------------------

def _remap_numid_in_clones(
    clones: "list[etree._Element]", num_id_remap: "dict[str, str]",
) -> int:
    """F15 — Rewrite `<w:numId w:val=N>` attrs inside each clone via
    `num_id_remap`. Returns rewrite count. Unmapped values left alone
    (defensive).
    """
    if not num_id_remap:
        return 0
    count = 0
    for clone in clones:
        for el in clone.iter(qn("w:numId")):
            old = el.get(qn("w:val"))
            if old in num_id_remap:
                el.set(qn("w:val"), num_id_remap[old])
                count += 1
    return count


# ---------------------------------------------------------------------------
# F16 — Path-traversal security primitive (M7)
# ---------------------------------------------------------------------------

def _assert_safe_target(target: str, base_tree_root: Path) -> None:
    """F16 — Raise `Md2DocxOutputInvalid` if `target` is unsafe.

    Reject branches (each populates `details.reason` with a fixed token;
    see ARCH §12.4 F16 + §12.8):
      - absolute_or_empty: empty / starts with '/' / contains backslash
        / contains NUL byte / decodes to absolute (percent-encoded).
      - drive_letter: Windows-style 'C:' prefix (also catches decoded
        URL-encoded drive letters).
      - parent_segment: contains '..' segments (literal or
        percent-encoded as %2e%2e, %2E%2E).
      - outside_base: resolves outside `base_tree_root/word/`.

    Defence vs ZIP-slip path traversal (CWE-22). The percent-decode pass
    is vdd-multi Logic H-2 hardening: Word URL-decodes rels Target
    attributes per ECMA-376 Part 2 §9.2, so `%2e%2e/etc` written verbatim
    in rels would be opened as `../etc` by Word.
    """
    # vdd-multi Logic H-2 fix: decode any percent-encoded segments BEFORE
    # checking, so encoded traversal can't bypass. (urllib.parse.unquote
    # imported at module level — vdd-multi P3.)
    decoded = unquote(target)
    for check_target in (target, decoded):
        if (
            not check_target
            or check_target.startswith("/")
            or "\\" in check_target
            or "\x00" in check_target
        ):
            raise Md2DocxOutputInvalid(
                f"insert rels Target is invalid or absolute: {target!r}",
                code=1, error_type="Md2DocxOutputInvalid",
                details={"target": target, "reason": "absolute_or_empty"},
            )
        if re.match(r"^[A-Za-z]:", check_target):
            raise Md2DocxOutputInvalid(
                f"insert rels Target has a drive letter: {target!r}",
                code=1, error_type="Md2DocxOutputInvalid",
                details={"target": target, "reason": "drive_letter"},
            )
        if any(p == ".." for p in Path(check_target).parts):
            raise Md2DocxOutputInvalid(
                f"insert rels Target contains '..' segments: {target!r}",
                code=1, error_type="Md2DocxOutputInvalid",
                details={"target": target, "reason": "parent_segment"},
            )
    candidate = (base_tree_root / "word" / target).resolve()
    base_word = (base_tree_root / "word").resolve()
    if not candidate.is_relative_to(base_word):
        raise Md2DocxOutputInvalid(
            f"insert rels Target resolves outside base/word/: {target!r}",
            code=1, error_type="Md2DocxOutputInvalid",
            details={"target": target, "reason": "outside_base"},
        )

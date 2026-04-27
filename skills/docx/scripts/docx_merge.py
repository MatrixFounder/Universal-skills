#!/usr/bin/env python3
"""Merge N .docx files into one, preserving styles and content.

Why direct OOXML editing instead of `python-docx`: python-docx's
public API does not expose body-tree concatenation across documents
with style-id remapping. We unpack each input via `office.unpack`,
append body content from the extras into the base, copy missing
style definitions, and repack via `office.pack`.

Usage:
    docx_merge.py OUTPUT.docx INPUT1.docx INPUT2.docx [...]
        [--page-break-between]   # insert a page break before each appended doc
        [--no-merge-styles]      # keep base styles only; don't import from extras
        [--json-errors]

Honest scope (v1):
- Merges body text, paragraphs, tables, headings, and inline content.
- Copies style definitions (`<w:style>` elements) from extras that
  don't exist in the base, matched by `w:styleId`.
- **Does NOT** merge:
  - Numbering definitions (`<w:numId>` references survive but
    list-continuity may break across documents — flagged in stderr
    if extras have `numbering.xml`).
  - Headers / footers / endnotes / footnotes (only the first
    document's are kept — flagged in stderr).
  - Embedded images / media (a warning is emitted if extras have
    `word/media/`; their `<w:drawing>` references in the merged
    body will dangle).
  - Comments (cross-document comment-id collisions — feed inputs
    through `docx_accept_changes.py` first if you don't need them).
For documents with tables / headings / simple lists this covers the
common "preface + chapters + appendices" merge use-case.

Exit codes:
    0  — merged successfully
    1  — I/O / pack failure / unsupported input shape
    2  — argparse usage error
    3  — input is password-protected or legacy CFB (cross-3 contract)
    6  — OUTPUT resolves to the same path as one of the INPUTs
         (cross-7 H1 SelfOverwriteRefused parity)
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

from docx.oxml.ns import qn  # type: ignore
from lxml import etree  # type: ignore

from _errors import add_json_errors_argument, report_error
from office._encryption import EncryptedFileError, assert_not_encrypted
from office._macros import warn_if_macros_will_be_dropped
from office.pack import pack
from office.unpack import unpack


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

# Relationship types we DO carry over from extra into base. Anything not
# listed here (theme, footnotes, header, footer, settings, fontTable,
# webSettings, styles, numbering — those are merged via dedicated parts
# or intentionally dropped) is skipped during rels merge to avoid
# resolving extra's body refs against unrelated base parts.
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


def _body(doc_tree: etree._ElementTree) -> etree._Element:
    body = doc_tree.getroot().find(qn("w:body"))
    if body is None:
        raise RuntimeError("document.xml has no <w:body>")
    return body


def _section_pr(body: etree._Element) -> etree._Element | None:
    """The trailing `<w:sectPr>` — section properties for the document.
    All appended content goes BEFORE it (otherwise the appended pages
    inherit the prior section break and column layout breaks)."""
    last = list(body)[-1] if len(body) else None
    if last is not None and last.tag == qn("w:sectPr"):
        return last
    return None


def _make_page_break_paragraph() -> etree._Element:
    """Return `<w:p><w:r><w:br w:type="page"/></w:r></w:p>` — the
    minimal hard page break OOXML accepts."""
    p = etree.Element(qn("w:p"))
    r = etree.SubElement(p, qn("w:r"))
    br = etree.SubElement(r, qn("w:br"))
    br.set(qn("w:type"), "page")
    return p


def _merge_styles(base_styles_path: Path, extra_styles_path: Path) -> int:
    """Copy `<w:style>` definitions from extra into base when the
    `w:styleId` is not already present. Returns count of styles
    appended."""
    if not base_styles_path.is_file() or not extra_styles_path.is_file():
        return 0
    base_tree = etree.parse(str(base_styles_path))
    extra_tree = etree.parse(str(extra_styles_path))
    base_root = base_tree.getroot()
    extra_root = extra_tree.getroot()

    existing = {
        s.get(qn("w:styleId"))
        for s in base_root.findall(qn("w:style"))
        if s.get(qn("w:styleId"))
    }
    appended = 0
    for s in extra_root.findall(qn("w:style")):
        sid = s.get(qn("w:styleId"))
        if sid and sid not in existing:
            base_root.append(_clone(s))
            existing.add(sid)
            appended += 1
    if appended:
        base_tree.write(str(base_styles_path), xml_declaration=True,
                        encoding="UTF-8", standalone=True)
    return appended


def _clone(elem: etree._Element) -> etree._Element:
    return etree.fromstring(etree.tostring(elem))


def _max_existing_rid(rels_root: etree._Element) -> int:
    """Return the largest numeric N in any `Id="rId<N>"` attribute in
    base's relationships root. Used to compute the offset for the
    extra's rIds so they don't collide."""
    biggest = 0
    for rel in rels_root.findall(f"{{{PR_NS}}}Relationship"):
        rid = rel.get("Id") or ""
        m = re.match(r"rId(\d+)$", rid)
        if m:
            biggest = max(biggest, int(m.group(1)))
    return biggest


def _copy_extra_media(
    base_dir: Path, extra_dir: Path, extra_index: int,
) -> dict[str, str]:
    """Copy `extra/word/media/*` into `base/word/media/` with a unique
    prefix per extra to avoid filename collisions across inputs. Return
    a {old_target_relative: new_target_relative} map keyed by the value
    we'll find in extra's relationships (`Target="media/..."`)."""
    src_dir = extra_dir / "word" / "media"
    if not src_dir.is_dir():
        return {}
    dst_dir = base_dir / "word" / "media"
    dst_dir.mkdir(parents=True, exist_ok=True)
    rename_map: dict[str, str] = {}
    for src in sorted(src_dir.iterdir()):
        if not src.is_file():
            continue
        new_name = f"extra{extra_index}_{src.name}"
        # Loop in the unlikely case of double-merge with the same prefix.
        n = 1
        while (dst_dir / new_name).exists():
            n += 1
            new_name = f"extra{extra_index}_{n}_{src.name}"
        dst = dst_dir / new_name
        dst.write_bytes(src.read_bytes())
        rename_map[f"media/{src.name}"] = f"media/{new_name}"
    return rename_map


def _merge_relationships(
    base_rels_path: Path,
    extra_rels_path: Path,
    media_rename: dict[str, str],
    rid_offset: int,
) -> dict[str, str]:
    """Append extra's image / hyperlink / chart / OLE relationships to
    base's `word/_rels/document.xml.rels`. Returns
    {old_extra_rId: new_rId_in_base} so the caller can rewrite refs in
    extra's body before the body is grafted into base.

    Non-mergeable rel types (theme, footnotes, header, footer, settings,
    fontTable, webSettings, styles, numbering) are dropped — those are
    either base-owned or merged via dedicated passes."""
    if not extra_rels_path.is_file():
        return {}
    extra_tree = etree.parse(str(extra_rels_path))
    extra_root = extra_tree.getroot()

    base_tree = etree.parse(str(base_rels_path))
    base_root = base_tree.getroot()

    existing_ids = {
        rel.get("Id")
        for rel in base_root.findall(f"{{{PR_NS}}}Relationship")
        if rel.get("Id")
    }
    rid_map: dict[str, str] = {}
    next_n = rid_offset
    for rel in extra_root.findall(f"{{{PR_NS}}}Relationship"):
        rtype = rel.get("Type") or ""
        if rtype not in _MERGEABLE_REL_TYPES:
            continue
        old_id = rel.get("Id") or ""
        # Compute a fresh Id that doesn't collide with base.
        next_n += 1
        new_id = f"rId{next_n}"
        while new_id in existing_ids:
            next_n += 1
            new_id = f"rId{next_n}"
        existing_ids.add(new_id)
        rid_map[old_id] = new_id

        new_rel = etree.SubElement(base_root, f"{{{PR_NS}}}Relationship")
        new_rel.set("Id", new_id)
        new_rel.set("Type", rtype)
        target = rel.get("Target") or ""
        if rtype == f"{R_NS}/image" and target in media_rename:
            target = media_rename[target]
        new_rel.set("Target", target)
        target_mode = rel.get("TargetMode")
        if target_mode is not None:
            new_rel.set("TargetMode", target_mode)
    base_tree.write(str(base_rels_path), xml_declaration=True,
                    encoding="UTF-8", standalone=True)
    return rid_map


# Attributes whose value is a single rId reference. We rewrite all of
# them in extra's body via the rid_map. Sourced from ECMA-376 Part 1
# §17 (WordprocessingML) — `r:embed`, `r:link`, `r:id` are the common
# ones; OLE/diagram parts add a few more.
_RID_ATTRS = (
    f"{{{R_NS}}}embed",
    f"{{{R_NS}}}link",
    f"{{{R_NS}}}id",
    f"{{{R_NS}}}dm",      # diagram data
    f"{{{R_NS}}}lo",      # diagram layout
    f"{{{R_NS}}}qs",      # diagram quick style
    f"{{{R_NS}}}cs",      # diagram colors
)


def _remap_rids_in_subtree(
    subtree: etree._Element, rid_map: dict[str, str],
) -> int:
    """Rewrite every r:embed / r:link / r:id attribute value in
    `subtree` using `rid_map`. References to rIds that aren't in the
    map (e.g. extra's reference to a rel type we deliberately dropped,
    like a footnote) are LEFT ALONE — Word will surface a "couldn't
    read" error if those resolve to nothing in base, but rewriting
    them blindly to a base rId would corrupt cleanly-mergeable
    content too. Returns count of rewrites."""
    count = 0
    for el in subtree.iter():
        for attr in _RID_ATTRS:
            val = el.get(attr)
            if val and val in rid_map:
                el.set(attr, rid_map[val])
                count += 1
    return count


def _max_bookmark_id(body: etree._Element) -> int:
    """Largest numeric `<w:bookmarkStart w:id>` in the given body.
    Returns -1 if there are no bookmarks (so offset = 0 in callers)."""
    biggest = -1
    for bm in body.iter(qn("w:bookmarkStart")):
        try:
            biggest = max(biggest, int(bm.get(qn("w:id"), "-1")))
        except ValueError:
            continue
    return biggest


def _strip_paragraph_section_breaks(body: etree._Element) -> int:
    """Remove paragraph-level `<w:sectPr>` from `body` (these live inside
    `<w:pPr>` of the LAST paragraph of a section). Each carries
    `<w:headerReference r:id>` / `<w:footerReference r:id>` references
    to extra's own header/footer parts — and we do NOT merge those parts
    in v2, so the references end up resolving against base's rels (or
    nothing), which Word reports as "couldn't read content".

    Stripping the in-paragraph sectPr also drops extra's per-section
    page-size / orientation / margin overrides — appendix / chapter
    content reflows under base's section. That matches the "preface +
    chapters + appendices" use case (user didn't ask for sudden
    landscape mid-document) and is the cheapest correct behaviour for
    v2. Returns count of sectPr stripped."""
    removed = 0
    # Only paragraph-level sectPr — the body-tail sectPr (if any) is the
    # extra body's whole-document section properties and is dropped via
    # the existing `if child.tag == qn("w:sectPr"): continue` filter in
    # merge_into_base.
    for ppr in body.iter(qn("w:pPr")):
        sect_pr = ppr.find(qn("w:sectPr"))
        if sect_pr is not None:
            ppr.remove(sect_pr)
            removed += 1
    return removed


def _remap_bookmark_ids(body: etree._Element, offset: int) -> int:
    """Bump every `<w:bookmarkStart w:id>` and matching
    `<w:bookmarkEnd w:id>` by `offset`. Idempotent count returned."""
    if offset <= 0:
        return 0
    count = 0
    for tag in (qn("w:bookmarkStart"), qn("w:bookmarkEnd")):
        for bm in body.iter(tag):
            try:
                old = int(bm.get(qn("w:id"), ""))
            except ValueError:
                continue
            bm.set(qn("w:id"), str(old + offset))
            count += 1
    return count


def _merge_numbering(
    base_dir: Path, extra_dir: Path, extra_body: etree._Element,
) -> int:
    """Merge `<w:abstractNum>` and `<w:num>` from extra's numbering.xml
    into base's, with abstractNumId / numId offsets applied so extra's
    list definitions don't collide with base's. References inside
    extra's body (`<w:numId w:val="N">`) are bumped in-place.

    If base has no numbering.xml but extra does, copy extra's whole
    numbering.xml into base/word/, add the Override + Relationship.
    Returns count of `<w:num>` defs appended to base."""
    extra_path = extra_dir / "word" / "numbering.xml"
    if not extra_path.is_file():
        return 0
    extra_root = etree.parse(str(extra_path)).getroot()
    extra_nums = extra_root.findall(qn("w:num"))
    extra_anums = extra_root.findall(qn("w:abstractNum"))
    if not extra_nums and not extra_anums:
        return 0

    base_path = base_dir / "word" / "numbering.xml"

    if not base_path.is_file():
        # Base has no numbering — we can simply install extra's whole
        # numbering.xml as base's. We still need to wire it in
        # [Content_Types].xml + word/_rels/document.xml.rels.
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.write_bytes(extra_path.read_bytes())
        _ensure_numbering_part(base_dir)
        return len(extra_nums)

    base_root = etree.parse(str(base_path)).getroot()

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

    def _max_int(strs: set[str]) -> int:
        biggest = -1
        for s in strs:
            try:
                biggest = max(biggest, int(s))
            except ValueError:
                continue
        return biggest

    anum_offset = _max_int(base_anum_ids) + 1
    num_offset = _max_int(base_num_ids) + 1

    # ECMA-376 §17.9.20 element order: every <w:abstractNum> MUST
    # precede every <w:num>, and <w:numIdMacAtCleanup> is the optional
    # tail. Naïve `.append()` on the root puts new abstractNums AFTER
    # base's existing nums → schema violation → Word auto-repairs at
    # open time, and during the repair pass it may rebind base's list
    # references to the wrong abstract definitions (observed: base's
    # headings rendered as bulleted "o" markers post-repair).
    #
    # Fix: insert each new abstractNum BEFORE the first base <w:num>,
    # and each new <w:num> right AFTER the last base <w:num> but
    # before <w:numIdMacAtCleanup>.
    children = list(base_root)
    first_num_idx = next(
        (i for i, c in enumerate(children) if c.tag == qn("w:num")),
        len(children),
    )
    cleanup_idx = next(
        (i for i, c in enumerate(children)
         if c.tag == qn("w:numIdMacAtCleanup")),
        None,
    )
    last_num_idx = max(
        (i for i, c in enumerate(children) if c.tag == qn("w:num")),
        default=first_num_idx - 1,
    )
    # Where to insert new <w:num>: right after the last existing num,
    # which is also (when cleanup exists) right before cleanup.
    num_insert_idx = (cleanup_idx if cleanup_idx is not None
                      else last_num_idx + 1)

    # Pass 1: insert abstractNum defs at first_num_idx, advancing as we
    # go so each new one lands AFTER the previous insertion (preserving
    # extra's relative order and keeping all of them before any <w:num>).
    insert_at = first_num_idx
    for a in extra_anums:
        old = a.get(qn("w:abstractNumId"))
        try:
            new = int(old) + anum_offset
        except (TypeError, ValueError):
            continue
        cloned = _clone(a)
        cloned.set(qn("w:abstractNumId"), str(new))
        base_root.insert(insert_at, cloned)
        insert_at += 1
        # Each insert before first_num_idx pushes num_insert_idx right.
        num_insert_idx += 1

    # Pass 2: insert num defs at num_insert_idx with both id-shifts.
    appended = 0
    num_id_remap: dict[str, str] = {}
    for n in extra_nums:
        old_num = n.get(qn("w:numId"))
        anum_ref = n.find(qn("w:abstractNumId"))
        if old_num is None or anum_ref is None:
            continue
        try:
            new_num = int(old_num) + num_offset
            new_anum_ref = int(anum_ref.get(qn("w:val"), "")) + anum_offset
        except ValueError:
            continue
        cloned = _clone(n)
        cloned.set(qn("w:numId"), str(new_num))
        cloned.find(qn("w:abstractNumId")).set(qn("w:val"), str(new_anum_ref))
        base_root.insert(num_insert_idx, cloned)
        num_insert_idx += 1
        num_id_remap[old_num] = str(new_num)
        appended += 1

    # Pass 3: rewrite extra's body's `<w:numId w:val="N">` references.
    for num_id_el in extra_body.iter(qn("w:numId")):
        old = num_id_el.get(qn("w:val"))
        if old in num_id_remap:
            num_id_el.set(qn("w:val"), num_id_remap[old])

    # Persist
    base_tree = etree.ElementTree(base_root)
    base_tree.write(str(base_path), xml_declaration=True,
                    encoding="UTF-8", standalone=True)
    return appended


def _merge_content_types_defaults(
    base_dir: Path, extra_dir: Path,
) -> int:
    """Copy `<Default Extension>` entries from extra's `[Content_Types].xml`
    that don't exist in base. Without this, media files we copy from
    extra (e.g. .png when base only had .jpeg) have no MIME mapping →
    Word reports "unreadable content" and refuses to render the image.

    Returns the count of Default entries appended."""
    base_ct_path = base_dir / "[Content_Types].xml"
    extra_ct_path = extra_dir / "[Content_Types].xml"
    if not base_ct_path.is_file() or not extra_ct_path.is_file():
        return 0
    base_tree = etree.parse(str(base_ct_path))
    extra_tree = etree.parse(str(extra_ct_path))
    base_root = base_tree.getroot()
    extra_root = extra_tree.getroot()

    base_exts = {
        d.get("Extension", "").lower()
        for d in base_root.findall(f"{{{CT_NS}}}Default")
    }
    appended = 0
    for d in extra_root.findall(f"{{{CT_NS}}}Default"):
        ext = (d.get("Extension") or "").lower()
        if ext and ext not in base_exts:
            new = etree.SubElement(base_root, f"{{{CT_NS}}}Default")
            new.set("Extension", d.get("Extension") or ext)
            new.set("ContentType", d.get("ContentType") or "")
            base_exts.add(ext)
            appended += 1
    if appended:
        base_tree.write(str(base_ct_path), xml_declaration=True,
                        encoding="UTF-8", standalone=True)
    return appended


def _ensure_numbering_part(base_dir: Path) -> None:
    """Wire word/numbering.xml into [Content_Types].xml + document
    relationships, idempotently. Mirrors docx_add_comment's
    _ensure_content_type / _ensure_relationship pattern."""
    ct_path = base_dir / "[Content_Types].xml"
    if ct_path.is_file():
        ct_tree = etree.parse(str(ct_path))
        ct_root = ct_tree.getroot()
        if not any(o.get("PartName") == "/word/numbering.xml"
                   for o in ct_root.findall(f"{{{CT_NS}}}Override")):
            ovr = etree.SubElement(ct_root, f"{{{CT_NS}}}Override")
            ovr.set("PartName", "/word/numbering.xml")
            ovr.set("ContentType",
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.numbering+xml")
            ct_tree.write(str(ct_path), xml_declaration=True,
                          encoding="UTF-8", standalone=True)

    rels_path = base_dir / "word" / "_rels" / "document.xml.rels"
    if rels_path.is_file():
        rels_tree = etree.parse(str(rels_path))
        rels_root = rels_tree.getroot()
        rtype = f"{R_NS}/numbering"
        if not any(r.get("Type") == rtype
                   for r in rels_root.findall(f"{{{PR_NS}}}Relationship")):
            existing = {
                r.get("Id")
                for r in rels_root.findall(f"{{{PR_NS}}}Relationship")
            }
            n = 1
            while f"rId{n}" in existing:
                n += 1
            new = etree.SubElement(rels_root,
                                   f"{{{PR_NS}}}Relationship")
            new.set("Id", f"rId{n}")
            new.set("Type", rtype)
            new.set("Target", "numbering.xml")
            rels_tree.write(str(rels_path), xml_declaration=True,
                            encoding="UTF-8", standalone=True)


def _count_children(path: Path, child_local_name: str) -> int:
    """Count direct children of an XML root with the given w:-namespaced
    local name. Returns 0 if the file is missing or unparseable."""
    if not path.is_file():
        return 0
    try:
        root = etree.parse(str(path)).getroot()
    except etree.XMLSyntaxError:
        return 0
    return len(root.findall(qn(f"w:{child_local_name}")))


def _warn_unsupported_parts(
    extra_root: Path, label: str, stderr: object,
) -> None:
    """Warn only for parts that actually carry user content AND are
    NOT handled by the iter-2 reloc passes (media + relationships +
    numbering + bookmark ids are merged; footnotes / endnotes /
    headers / footers / comments are still v1-honest-scope drops)."""
    word = extra_root / "word"
    flags = []

    # footnotes.xml: Word ships 2 boilerplate footnotes (separator +
    # continuation-separator), id 0 and 1. Real footnotes start at id 2.
    if _count_children(word / "footnotes.xml", "footnote") > 2:
        flags.append("footnotes.xml (only base file's footnotes kept)")
    if _count_children(word / "endnotes.xml", "endnote") > 2:
        flags.append("endnotes.xml (only base file's endnotes kept)")

    # comments.xml: empty container ships routinely; only warn if it
    # actually contains comments.
    if _count_children(word / "comments.xml", "comment") > 0:
        flags.append("comments.xml (id-collision risk; not merged)")

    # Headers/footers are per-section and have their own rels graph;
    # we don't try to merge them in v2.
    if any(word.glob("header*.xml")):
        flags.append("headers (only base file's headers kept)")
    if any(word.glob("footer*.xml")):
        flags.append("footers (only base file's footers kept)")

    if flags:
        print(f"[docx_merge] WARNING: {label} contains unsupported parts "
              f"that will not be merged: " + "; ".join(flags),
              file=stderr)


def merge_into_base(
    base_dir: Path,
    extra_dir: Path,
    extra_index: int,
    *,
    page_break_before: bool,
    merge_styles: bool,
) -> dict[str, int]:
    """Append extra's body content into base's `word/document.xml`
    with full reference relocation:

    1. Copy `extra/word/media/*` into `base/word/media/` with a unique
       prefix (`extra<i>_…`) so filename collisions don't overwrite
       base assets.
    2. Append extra's image / hyperlink / chart / OLE relationships to
       base's `document.xml.rels` with rId-shifted ids; build an
       old-rId → new-rId map.
    3. Rewrite extra's body's `r:embed`/`r:link`/`r:id`/diagram refs
       through the rId map BEFORE the body is grafted into base.
    4. Bump every `<w:bookmarkStart/End w:id>` in extra's body by
       `max_existing_in_base + 1` to avoid Word's "couldn't read
       content" diagnostic on duplicate numeric ids.
    5. Merge `<w:abstractNum>` and `<w:num>` from extra's numbering.xml
       into base's, with abstractNumId / numId offsets, and rewrite
       `<w:numId w:val>` references in extra's body in the same pass.
    6. Append extra's body children into base's body (before
       base's `<w:sectPr>`), with optional hard page-break.
    7. Merge missing style definitions if `merge_styles`."""
    base_doc_path = base_dir / "word" / "document.xml"
    extra_doc_path = extra_dir / "word" / "document.xml"
    if not base_doc_path.is_file() or not extra_doc_path.is_file():
        raise RuntimeError(
            "input is not a wordprocessing document (missing "
            "word/document.xml)"
        )

    base_tree = etree.parse(str(base_doc_path))
    extra_tree = etree.parse(str(extra_doc_path))

    base_body = _body(base_tree)
    extra_body = _body(extra_tree)

    # 1+2. Copy media + extend relationships, getting an rId remap.
    # Also pull in any missing <Default Extension> entries from extra's
    # Content_Types so PNG/GIF/etc. media types we just imported have a
    # MIME mapping (Word's "couldn't read content" diagnostic fires when
    # a media file has no Default and no Override in [Content_Types].xml).
    base_rels_path = base_dir / "word" / "_rels" / "document.xml.rels"
    extra_rels_path = extra_dir / "word" / "_rels" / "document.xml.rels"
    media_rename = _copy_extra_media(base_dir, extra_dir, extra_index)
    if media_rename:
        _merge_content_types_defaults(base_dir, extra_dir)
    base_rels_root = etree.parse(str(base_rels_path)).getroot() \
        if base_rels_path.is_file() else None
    rid_offset = _max_existing_rid(base_rels_root) if base_rels_root is not None else 0
    rid_map = _merge_relationships(
        base_rels_path, extra_rels_path, media_rename, rid_offset,
    )

    # 3. Strip paragraph-level <w:sectPr> from extra body. Each carries
    # <w:headerReference>/<w:footerReference> r:id refs to extra's own
    # header/footer parts which we deliberately don't merge — leaving
    # them in place makes Word read them as references to base's rels
    # (different content type) and report "couldn't read content".
    sectpr_stripped = _strip_paragraph_section_breaks(extra_body)

    # 4. Apply rId remap to the in-memory extra body before insertion.
    rid_rewrites = _remap_rids_in_subtree(extra_body, rid_map)

    # 5. Bump bookmark ids beyond base's max to avoid duplicates.
    bookmark_offset = _max_bookmark_id(base_body) + 1
    bookmark_rewrites = _remap_bookmark_ids(extra_body, bookmark_offset)

    # 5. Merge numbering definitions and rewrite body numId refs.
    num_added = _merge_numbering(base_dir, extra_dir, extra_body)

    # 6. Graft body children. The extra's own sectPr is skipped.
    sect_pr = _section_pr(base_body)
    insert_before = sect_pr if sect_pr is not None else None
    appended = 0
    if page_break_before:
        pb = _make_page_break_paragraph()
        if insert_before is not None:
            insert_before.addprevious(pb)
        else:
            base_body.append(pb)
        appended += 1
    for child in list(extra_body):
        if child.tag == qn("w:sectPr"):
            continue
        cloned = _clone(child)
        if insert_before is not None:
            insert_before.addprevious(cloned)
        else:
            base_body.append(cloned)
        appended += 1

    base_tree.write(str(base_doc_path), xml_declaration=True,
                    encoding="UTF-8", standalone=True)

    # 7. Styles.
    style_count = 0
    if merge_styles:
        style_count = _merge_styles(
            base_dir / "word" / "styles.xml",
            extra_dir / "word" / "styles.xml",
        )

    return {
        "body_children": appended,
        "styles": style_count,
        "media": len(media_rename),
        "rels": len(rid_map),
        "rid_rewrites": rid_rewrites,
        "bookmark_rewrites": bookmark_rewrites,
        "numbering": num_added,
        "sectpr_stripped": sectpr_stripped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path)
    parser.add_argument("inputs", nargs="+", type=Path,
                        help="Two or more .docx files to merge, in order. "
                             "The first is the base — its styles, "
                             "headers/footers, sectPr, and metadata are "
                             "preserved.")
    parser.add_argument("--page-break-between", action="store_true",
                        help="Insert a hard page break before each "
                             "appended document.")
    parser.add_argument("--no-merge-styles", action="store_true",
                        help="Skip copying missing style definitions "
                             "from later inputs into the base. Useful "
                             "when you want strict base-only styling.")
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    if len(args.inputs) < 2:
        return report_error(
            f"need at least 2 inputs to merge, got {len(args.inputs)}",
            code=2, error_type="NotEnoughInputs",
            details={"count": len(args.inputs)}, json_mode=je,
        )

    for inp in args.inputs:
        if not inp.is_file():
            return report_error(
                f"input not found: {inp}", code=1,
                error_type="FileNotFound",
                details={"path": str(inp)}, json_mode=je,
            )
        try:
            assert_not_encrypted(inp)
        except EncryptedFileError as exc:
            return report_error(str(exc), code=3,
                                error_type="EncryptedFileError",
                                details={"path": str(inp)},
                                json_mode=je)

    # Refuse same-path I/O before any unpack/pack runs (parity with
    # office_passwd.py's H1 guard, cross-7). resolve() catches the
    # symlink case where literal paths differ but inodes match. If the
    # user names OUTPUT as one of the inputs, a pack-time crash leaves
    # them with neither the original nor a valid merge.
    try:
        out_resolved = args.output.resolve(strict=False)
    except OSError:
        out_resolved = args.output
    for inp in args.inputs:
        try:
            in_resolved = inp.resolve(strict=False)
        except OSError:
            in_resolved = inp
        if in_resolved == out_resolved:
            return report_error(
                f"INPUT {inp} and OUTPUT {args.output} resolve to the "
                f"same path: {in_resolved} (would corrupt the source on "
                f"a pack-time crash)",
                code=6, error_type="SelfOverwriteRefused",
                details={"input": str(inp),
                         "output": str(args.output)},
                json_mode=je,
            )

    # Use the first input as the macro-loss reference (output extension
    # vs first input is the most useful warning — the user picks the
    # output format based on the first input typically).
    warn_if_macros_will_be_dropped(args.inputs[0], args.output, sys.stderr)

    try:
        with tempfile.TemporaryDirectory(prefix="docx_merge-") as td:
            tdp = Path(td)
            base_dir = tdp / "base"
            unpack(args.inputs[0], base_dir)

            totals = {
                "body_children": 0, "styles": 0, "media": 0,
                "rels": 0, "rid_rewrites": 0,
                "bookmark_rewrites": 0, "numbering": 0,
            }
            for i, extra in enumerate(args.inputs[1:], start=1):
                extra_dir = tdp / f"extra_{i}"
                unpack(extra, extra_dir)
                _warn_unsupported_parts(extra_dir, str(extra), sys.stderr)
                stats = merge_into_base(
                    base_dir, extra_dir, extra_index=i,
                    page_break_before=args.page_break_between,
                    merge_styles=not args.no_merge_styles,
                )
                for k, v in stats.items():
                    totals[k] = totals.get(k, 0) + v

            pack(base_dir, args.output)
    except (RuntimeError, ValueError, OSError) as exc:
        return report_error(
            f"merge failed: {exc}", code=1,
            error_type=type(exc).__name__, json_mode=je,
        )

    print(f"{args.output}: merged {len(args.inputs)} inputs "
          f"(+{totals['body_children']} body children, "
          f"+{totals['styles']} styles, "
          f"+{totals['media']} media, "
          f"+{totals['rels']} rels, "
          f"+{totals['numbering']} num defs, "
          f"{totals['rid_rewrites']} rId rewrites, "
          f"{totals['bookmark_rewrites']} bookmark rewrites)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

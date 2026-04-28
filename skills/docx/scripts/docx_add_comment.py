#!/usr/bin/env python3
"""Insert a Word comment into a .docx by anchoring on text, with optional
threaded replies and an opt-in library mode for callers that already
hold an unpacked OOXML tree.

Why direct OOXML XML editing instead of `python-docx`: as of
python-docx 1.2 the high-level API exposes no way to add comments —
the `<w:comments>` part, the inline `<w:commentRangeStart/End>`
markers, the `<w:commentReference>` run, and (for replies) the
`<w15:commentEx w15:paraIdParent=…>` linkage in
`commentsExtended.xml` all need to be wired together by hand. We
unpack the .docx (`office.unpack`), edit the relevant XML parts via
lxml, and repack (`office.pack`) — the same pattern
`docx_fill_template.py` uses. Library mode skips the unpack/pack
when the caller already has a tree.

Usage:
    docx_add_comment.py INPUT.docx OUTPUT.docx \\
        --anchor-text "phrase to attach the comment to" \\
        --comment "Please verify formula X" \\
        [--author "Reviewer Bot"] [--initials RB] \\
        [--date 2026-04-27T12:34:56Z] [--all] \\
        [--json-errors]

    docx_add_comment.py INPUT.docx OUTPUT.docx \\
        --parent 0 --comment "Acknowledged, fixing." [--author "Dev"]

    docx_add_comment.py --unpacked-dir DIR \\
        --anchor-text "..." --comment "..." [--parent N]

`--anchor-text` must occur within a single `<w:t>` element of one
paragraph (after the same run-merge pass `docx_fill_template`
performs). When Word splits text across runs with different
formatting, the helper merges adjacent runs that share identical
`<w:rPr>`; if the anchor still spans formatting boundaries the
script exits 2 with a hint to pick a more uniform substring.

`--parent N` makes a *reply* to comment id N: the reply inherits the
parent's anchor range (no `--anchor-text` needed), gets its own
`<w:comment>` part with a fresh `w14:paraId`, and is threaded in
Word's review pane via `<w15:commentEx w15:paraIdParent=…>` in
`commentsExtended.xml`. Reply-mode also writes `commentsIds.xml`
and `commentsExtensible.xml` so Word 2016+ keeps stable cross-
document references.

`--unpacked-dir DIR` operates on an already-unpacked tree in-place
(no zip I/O, no encryption check, no same-path check). Useful when
chaining comment insertion into a larger pipeline that already
unpacked the file.

Exit codes:
    0  — comment added successfully
    1  — I/O / pack failure / malformed OOXML in input tree
    2  — argparse usage error / anchor not found / anchor spans
         formatting boundaries / parent comment or its range not found
    3  — input is password-protected or legacy CFB (cross-3 contract)
    6  — INPUT and OUTPUT resolve to the same path (cross-7 H1
         SelfOverwriteRefused parity, zip-mode only)

Honest scope (known limitations, not bugs):
    * **Library mode is NOT reentrant.** Two concurrent
      `--unpacked-dir DIR` invocations on the same tree race on every
      OOXML part they touch and silently drop one of the writes. There
      is no file locking — wrap external concurrency yourself
      (e.g. one-process-per-tree, or `flock` around the call).
    * **Reply chains are flattened.** `--parent N` where N is itself a
      reply gets re-targeted to the conversation root via the
      `commentsExtended.xml` `paraIdParent` chain, mirroring Word's
      review-pane render (a flat list under one root, not a tree).
    * **Comment body splits on `\\n`** into separate `<w:p>`
      paragraphs (per ECMA-376 §17.13.4.2). `\\r\\n` is normalized to
      `\\n` first. Use `--comment $'line1\\nline2'` for multi-line
      bodies. If you need richer formatting (bold inside body, links,
      etc.) build the `<w:comment>` element by hand and use library
      mode to insert it.
    * **paraId / durableId are random 31-bit hex.** No collision check
      against existing IDs; birthday-paradox probability is negligible
      below ~65k comments per document but not zero. Word tolerates
      collisions silently.
    * **Anchor must fit a single run** after the adjacent-run merge —
      same constraint as `docx_fill_template.py`. Spans crossing
      `<w:rPr>` boundaries (mixed bold+plain) cannot be wrapped.
"""
from __future__ import annotations

import argparse
import random
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from docx.oxml.ns import qn  # type: ignore
from lxml import etree  # type: ignore

from _errors import add_json_errors_argument, report_error
from office._encryption import EncryptedFileError, assert_not_encrypted
from office._macros import warn_if_macros_will_be_dropped
from office.pack import pack
from office.unpack import unpack


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W15_NS = "http://schemas.microsoft.com/office/word/2012/wordml"
W16CID_NS = "http://schemas.microsoft.com/office/word/2016/wordml/cid"
W16CEX_NS = "http://schemas.microsoft.com/office/word/2018/wordml/cex"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

COMMENTS_PART = "/word/comments.xml"
COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
COMMENTS_CT = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.comments+xml"
)

COMMENTS_EXT_PART = "/word/commentsExtended.xml"
COMMENTS_EXT_REL_TYPE = (
    "http://schemas.microsoft.com/office/2011/relationships/commentsExtended"
)
COMMENTS_EXT_CT = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.commentsExtended+xml"
)

COMMENTS_IDS_PART = "/word/commentsIds.xml"
COMMENTS_IDS_REL_TYPE = (
    "http://schemas.microsoft.com/office/2016/09/relationships/commentsIds"
)
COMMENTS_IDS_CT = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.commentsIds+xml"
)

COMMENTS_CEX_PART = "/word/commentsExtensible.xml"
COMMENTS_CEX_REL_TYPE = (
    "http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible"
)
COMMENTS_CEX_CT = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.commentsExtensible+xml"
)


def _initials_from_author(author: str) -> str:
    parts = re.findall(r"\w+", author)
    return ("".join(p[:1] for p in parts) or "R").upper()[:8]


def _rpr_key(run: etree._Element) -> bytes:
    rpr = run.find(qn("w:rPr"))
    return b"" if rpr is None else etree.tostring(rpr, method="c14n")


def _is_simple_text_run(run: etree._Element) -> bool:
    """A run is "simple" enough to safely split around an anchor when it
    contains only formatting (`<w:rPr>`), text (`<w:t>`), and Word's
    visual-empty render-cache markers. `<w:lastRenderedPageBreak>` is
    Word's hint for the position of the last page break it computed —
    purely a paginator cache, no glyph rendered, and re-emitted on
    every save. Real-world headings (e.g. "PURPOSE" right after a
    heading-induced page break) routinely look like
    `[rPr, lastRenderedPageBreak, t]` and were silently treated as
    non-simple by an earlier overly-strict filter."""
    for child in run:
        tag = etree.QName(child).localname
        if tag not in {"rPr", "t", "lastRenderedPageBreak"}:
            return False
    return True


def _merge_adjacent_runs(paragraph: etree._Element) -> None:
    """Same trick docx_fill_template.py uses — merge adjacent runs that
    share identical `<w:rPr>` so a substring split across runs by
    Word's autocorrect/spell-check gets reunited before we search."""
    runs = paragraph.findall(qn("w:r"))
    i = 0
    while i < len(runs) - 1:
        a, b = runs[i], runs[i + 1]
        if not (_is_simple_text_run(a) and _is_simple_text_run(b)):
            i += 1
            continue
        if _rpr_key(a) != _rpr_key(b):
            i += 1
            continue
        a_t, b_t = a.find(qn("w:t")), b.find(qn("w:t"))
        if a_t is None or b_t is None:
            i += 1
            continue
        a_t.text = (a_t.text or "") + (b_t.text or "")
        if " " in (a_t.text or ""):
            a_t.set(
                "{http://www.w3.org/XML/1998/namespace}space", "preserve"
            )
        b.getparent().remove(b)
        runs = paragraph.findall(qn("w:r"))


def _next_comment_id(comments_root: etree._Element) -> int:
    ids = [
        int(c.get(qn("w:id"), "-1"))
        for c in comments_root.findall(qn("w:comment"))
    ]
    return (max(ids) + 1) if ids else 0


def _random_hex_id() -> str:
    """8-char uppercase hex used by Word for w14:paraId / w16cid:durableId.
    Word's own files use the full 32-bit space minus the high bit to
    avoid sign confusion in legacy parsers — we mirror that."""
    return f"{random.randint(0, 0x7FFFFFFE):08X}"


def _build_comment_paragraph(
    text: str, *, para_id: str, with_annotation_ref: bool,
) -> etree._Element:
    """One `<w:p>` node inside `<w:comment>`. Each paragraph carries its
    own `w14:paraId` (Word's stable cross-document anchor) and a
    `<w:pStyle w:val="CommentText">`. Only the FIRST paragraph of a
    multi-paragraph comment carries the `<w:annotationRef/>` run — Word
    uses it to render the speech-bubble icon at the start of the
    side-pane entry; secondary paragraphs must NOT repeat it or Word
    duplicates the icon."""
    p = etree.Element(qn("w:p"))
    p.set(f"{{{W14_NS}}}paraId", para_id)
    p.set(f"{{{W14_NS}}}textId", "77777777")
    pPr = etree.SubElement(p, qn("w:pPr"))
    pStyle = etree.SubElement(pPr, qn("w:pStyle"))
    pStyle.set(qn("w:val"), "CommentText")
    if with_annotation_ref:
        anchor_run = etree.SubElement(p, qn("w:r"))
        anchor_rpr = etree.SubElement(anchor_run, qn("w:rPr"))
        anchor_style = etree.SubElement(anchor_rpr, qn("w:rStyle"))
        anchor_style.set(qn("w:val"), "CommentReference")
        etree.SubElement(anchor_run, qn("w:annotationRef"))
    text_run = etree.SubElement(p, qn("w:r"))
    text_rpr = etree.SubElement(text_run, qn("w:rPr"))
    text_style = etree.SubElement(text_rpr, qn("w:rStyle"))
    text_style.set(qn("w:val"), "CommentReference")
    t = etree.SubElement(text_run, qn("w:t"))
    t.text = text
    if text and (" " in text or text != text.strip()):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return p


def _build_comment_element(
    comment_id: int,
    body: str,
    author: str,
    initials: str,
    date_iso: str,
    para_id: str,
) -> etree._Element:
    """Build `<w:comment>`. Splits `body` on '\\n' into separate `<w:p>`
    paragraphs (per ECMA-376 §17.13.4.2 — comments are paragraph
    sequences, not single text runs). `\\r\\n` is normalized to `\\n`
    first. Empty paragraphs (consecutive newlines) are kept as
    visually empty paragraphs, matching Word's own export shape.

    Only the FIRST paragraph carries `w14:paraId` (the comment's
    public ID used by `commentsExtended.xml` / `commentsIds.xml`);
    subsequent paragraphs get fresh paraIds — Word does the same."""
    nsmap = {"w": W_NS, "w14": W14_NS}
    comment = etree.Element(qn("w:comment"), nsmap=nsmap)
    comment.set(qn("w:id"), str(comment_id))
    comment.set(qn("w:author"), author)
    comment.set(qn("w:initials"), initials)
    comment.set(qn("w:date"), date_iso)
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for idx, line in enumerate(lines):
        p_para_id = para_id if idx == 0 else _random_hex_id()
        comment.append(
            _build_comment_paragraph(
                line, para_id=p_para_id,
                with_annotation_ref=(idx == 0),
            )
        )
    return comment


def _ensure_comments_part(
    tree_root: Path,
) -> tuple[Path, etree._ElementTree]:
    """Return (path-to-comments.xml, parsed-tree). Create an empty one
    if the document doesn't have comments yet."""
    path = tree_root / "word" / "comments.xml"
    if path.is_file():
        return path, etree.parse(str(path))

    path.parent.mkdir(parents=True, exist_ok=True)
    root = etree.Element(qn("w:comments"), nsmap={"w": W_NS, "w14": W14_NS})
    tree = etree.ElementTree(root)
    tree.write(str(path), xml_declaration=True,
               encoding="UTF-8", standalone=True)
    return path, tree


def _ensure_extra_part(
    tree_root: Path,
    *,
    part_name: str,
    root_qname: str,
    nsmap: dict[str, str],
    rel_type: str,
    content_type: str,
) -> tuple[Path, etree._ElementTree]:
    """Generic helper for the three Word-2016+ comment side-parts
    (commentsExtended / commentsIds / commentsExtensible). Idempotent:
    creates the file with the right root element if missing, then wires
    relationship + content-type override."""
    path = tree_root / part_name.lstrip("/")
    if path.is_file():
        tree = etree.parse(str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        root = etree.Element(root_qname, nsmap=nsmap)
        tree = etree.ElementTree(root)
        tree.write(str(path), xml_declaration=True,
                   encoding="UTF-8", standalone=True)

    target = Path(part_name.lstrip("/")).relative_to("word").as_posix()
    _ensure_relationship(
        tree_root / "word" / "_rels" / "document.xml.rels",
        rel_type=rel_type, target=target,
    )
    _ensure_content_type(
        tree_root / "[Content_Types].xml",
        part_name=part_name, content_type=content_type,
    )
    return path, tree


def _ensure_comments_extended_part(
    tree_root: Path,
) -> tuple[Path, etree._ElementTree]:
    return _ensure_extra_part(
        tree_root,
        part_name=COMMENTS_EXT_PART,
        root_qname=f"{{{W15_NS}}}commentsEx",
        nsmap={"w15": W15_NS},
        rel_type=COMMENTS_EXT_REL_TYPE,
        content_type=COMMENTS_EXT_CT,
    )


def _ensure_comments_ids_part(
    tree_root: Path,
) -> tuple[Path, etree._ElementTree]:
    return _ensure_extra_part(
        tree_root,
        part_name=COMMENTS_IDS_PART,
        root_qname=f"{{{W16CID_NS}}}commentsIds",
        nsmap={"w16cid": W16CID_NS},
        rel_type=COMMENTS_IDS_REL_TYPE,
        content_type=COMMENTS_IDS_CT,
    )


def _ensure_comments_extensible_part(
    tree_root: Path,
) -> tuple[Path, etree._ElementTree]:
    return _ensure_extra_part(
        tree_root,
        part_name=COMMENTS_CEX_PART,
        root_qname=f"{{{W16CEX_NS}}}commentsExtensible",
        nsmap={"w16cex": W16CEX_NS},
        rel_type=COMMENTS_CEX_REL_TYPE,
        content_type=COMMENTS_CEX_CT,
    )


def _ensure_relationship(
    rels_path: Path, *, rel_type: str, target: str,
) -> None:
    """Make sure document.xml.rels has an entry of the given type pointing
    at the given target. Idempotent."""
    if not rels_path.is_file():
        raise RuntimeError(f"missing relationships file: {rels_path}")
    tree = etree.parse(str(rels_path))
    root = tree.getroot()
    for rel in root.findall(f"{{{PR_NS}}}Relationship"):
        if rel.get("Type") == rel_type and rel.get("Target") == target:
            return  # already wired

    existing_ids = {
        r.get("Id") for r in root.findall(f"{{{PR_NS}}}Relationship")
    }
    n = 1
    while f"rId{n}" in existing_ids:
        n += 1
    new = etree.SubElement(root, f"{{{PR_NS}}}Relationship")
    new.set("Id", f"rId{n}")
    new.set("Type", rel_type)
    new.set("Target", target)
    tree.write(str(rels_path), xml_declaration=True,
               encoding="UTF-8", standalone=True)


def _ensure_content_type(
    content_types_path: Path, *, part_name: str, content_type: str,
) -> None:
    """Make sure [Content_Types].xml has an Override for the given part."""
    tree = etree.parse(str(content_types_path))
    root = tree.getroot()
    for ovr in root.findall(f"{{{CT_NS}}}Override"):
        if ovr.get("PartName") == part_name:
            return
    new = etree.SubElement(root, f"{{{CT_NS}}}Override")
    new.set("PartName", part_name)
    new.set("ContentType", content_type)
    tree.write(str(content_types_path), xml_declaration=True,
               encoding="UTF-8", standalone=True)


def _append_comment_extended(
    ext_root: etree._Element,
    *,
    para_id: str,
    parent_para_id: str | None,
) -> None:
    el = etree.SubElement(ext_root, f"{{{W15_NS}}}commentEx")
    el.set(f"{{{W15_NS}}}paraId", para_id)
    if parent_para_id is not None:
        el.set(f"{{{W15_NS}}}paraIdParent", parent_para_id)
    el.set(f"{{{W15_NS}}}done", "0")


def _append_comment_id(
    ids_root: etree._Element,
    *,
    para_id: str,
    durable_id: str,
) -> None:
    el = etree.SubElement(ids_root, f"{{{W16CID_NS}}}commentId")
    el.set(f"{{{W16CID_NS}}}paraId", para_id)
    el.set(f"{{{W16CID_NS}}}durableId", durable_id)


def _append_comment_extensible(
    cex_root: etree._Element,
    *,
    durable_id: str,
    date_iso: str,
) -> None:
    el = etree.SubElement(cex_root, f"{{{W16CEX_NS}}}commentExtensible")
    el.set(f"{{{W16CEX_NS}}}durableId", durable_id)
    el.set(f"{{{W16CEX_NS}}}dateUtc", date_iso)


def _find_comment_element(
    comments_root: etree._Element, comment_id: int,
) -> etree._Element | None:
    for c in comments_root.findall(qn("w:comment")):
        if c.get(qn("w:id")) == str(comment_id):
            return c
    return None


def _get_comment_para_id(comment_el: etree._Element) -> str | None:
    p = comment_el.find(qn("w:p"))
    if p is None:
        return None
    return p.get(f"{{{W14_NS}}}paraId")


def _resolve_root_para_id(
    ext_root: etree._Element | None, immediate_para_id: str,
) -> str:
    """Walk `<w15:commentEx paraIdParent>` links in `commentsExtended.xml`
    until we reach a paraId that has no parent — that is the root of
    the conversation thread. Word flattens replies in the side pane:
    a reply to a reply is rendered as a sibling of the first reply,
    not nested two levels deep. Mirroring that on disk keeps our
    output canonical and round-trips cleanly through Word's "Reply"
    button. If `commentsExtended.xml` is missing/empty (older docs),
    we conservatively return the immediate parent."""
    if ext_root is None:
        return immediate_para_id
    by_para = {}
    for el in ext_root.findall(f"{{{W15_NS}}}commentEx"):
        pid = el.get(f"{{{W15_NS}}}paraId")
        parent = el.get(f"{{{W15_NS}}}paraIdParent")
        if pid:
            by_para[pid] = parent
    seen: set[str] = set()
    cur = immediate_para_id
    while cur in by_para and by_para[cur]:
        if cur in seen:
            return immediate_para_id  # cycle in malformed input
        seen.add(cur)
        cur = by_para[cur]
    return cur


def _make_text_run(text: str, rpr_src: etree._Element | None) -> etree._Element:
    r = etree.Element(qn("w:r"))
    if rpr_src is not None:
        r.append(_clone(rpr_src))
    tt = etree.SubElement(r, qn("w:t"))
    tt.text = text
    if text != text.strip() or " " in text:
        tt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return r


def _make_comment_ref_run(comment_id: int) -> etree._Element:
    """Build the speech-bubble commentReference run for the given id."""
    ref_run = etree.Element(qn("w:r"))
    ref_rpr = etree.SubElement(ref_run, qn("w:rPr"))
    ref_style = etree.SubElement(ref_rpr, qn("w:rStyle"))
    ref_style.set(qn("w:val"), "CommentReference")
    ref = etree.SubElement(ref_run, qn("w:commentReference"))
    ref.set(qn("w:id"), str(comment_id))
    return ref_run


def _wrap_anchors_in_paragraph(
    paragraph: etree._Element,
    anchor: str,
    comment_id_start: int,
    *,
    anchor_all: bool,
) -> int:
    """Wrap occurrences of `anchor` in this paragraph's runs. Returns the
    count of wraps performed (0..N).

    The match scan runs over each run's `<w:t>` text in a single pass —
    `re.finditer` style — so multiple occurrences in the SAME run get
    split out together. The original run is replaced by a sequence of
    [before, crs, hit, cre, ref, between, crs, hit, cre, ref, ..., tail].

    A snapshot of the run list is taken upfront via `list(...)` so the
    iteration is unaffected by structural mutations (the original runs
    are removed and replaced as we go).

    Anchor-spans-multiple-runs is the documented limitation: after the
    run-merge pass a `<w:t>` element holds one contiguous span of
    same-formatted text. Crossing formatting boundaries is out of scope
    for v1 — the caller still gets clean output, just no wrap there."""
    if not anchor:
        return 0
    runs = list(paragraph.findall(qn("w:r")))
    next_id = comment_id_start
    wraps = 0
    for run in runs:
        if not _is_simple_text_run(run):
            continue
        t = run.find(qn("w:t"))
        if t is None or t.text is None:
            continue
        text = t.text
        if anchor not in text:
            continue
        rpr_src = run.find(qn("w:rPr"))

        new_nodes: list[etree._Element] = []
        cursor = 0
        while True:
            idx = text.find(anchor, cursor)
            if idx < 0:
                tail = text[cursor:]
                if tail:
                    new_nodes.append(_make_text_run(tail, rpr_src))
                break
            if idx > cursor:
                new_nodes.append(_make_text_run(text[cursor:idx], rpr_src))
            cid = next_id + wraps
            crs = etree.Element(qn("w:commentRangeStart"))
            crs.set(qn("w:id"), str(cid))
            cre = etree.Element(qn("w:commentRangeEnd"))
            cre.set(qn("w:id"), str(cid))
            new_nodes.extend([
                crs,
                _make_text_run(anchor, rpr_src),
                cre,
                _make_comment_ref_run(cid),
            ])
            wraps += 1
            cursor = idx + len(anchor)
            if not anchor_all:
                tail = text[cursor:]
                if tail:
                    new_nodes.append(_make_text_run(tail, rpr_src))
                break

        run_idx = list(paragraph).index(run)
        paragraph.remove(run)
        for offset, node in enumerate(new_nodes):
            paragraph.insert(run_idx + offset, node)

        if not anchor_all and wraps:
            return wraps

    return wraps


def _wrap_reply_in_parent_range(
    doc_root: etree._Element,
    parent_id: int,
    reply_id: int,
) -> bool:
    """Nest the reply's range markers inside the parent's. Returns True
    if the parent's anchors were found and the reply's markers were
    inserted, False otherwise.

    The shape we produce mirrors what Word writes when a user clicks
    "Reply" in the review pane:

        <w:commentRangeStart w:id="parent"/>
        <w:commentRangeStart w:id="reply"/>
          ...anchor runs...
        <w:commentRangeEnd w:id="reply"/>
        <w:commentRangeEnd w:id="parent"/>
        <w:r>...commentReference w:id="parent"/></w:r>
        <w:r>...commentReference w:id="reply"/></w:r>

    The reply's commentReference run is inserted right after the
    parent's, so Word's reading order (parent → reply) matches the
    visual thread order in the side pane."""
    parent_str = str(parent_id)

    crs_parent = None
    cre_parent = None
    ref_parent = None
    for el in doc_root.iter(qn("w:commentRangeStart")):
        if el.get(qn("w:id")) == parent_str:
            crs_parent = el
            break
    for el in doc_root.iter(qn("w:commentRangeEnd")):
        if el.get(qn("w:id")) == parent_str:
            cre_parent = el
            break
    for el in doc_root.iter(qn("w:commentReference")):
        if el.get(qn("w:id")) == parent_str:
            ref_parent = el
            break

    if crs_parent is None or cre_parent is None or ref_parent is None:
        return False

    new_crs = etree.Element(qn("w:commentRangeStart"))
    new_crs.set(qn("w:id"), str(reply_id))
    crs_parent.addnext(new_crs)

    new_cre = etree.Element(qn("w:commentRangeEnd"))
    new_cre.set(qn("w:id"), str(reply_id))
    cre_parent.addprevious(new_cre)

    ref_run = ref_parent.getparent()  # the <w:r> wrapping the reference
    new_ref_run = _make_comment_ref_run(reply_id)
    ref_run.addnext(new_ref_run)
    return True


def _clone(elem: etree._Element) -> etree._Element:
    """Deep-copy via serialize/parse — preserves namespaces correctly."""
    return etree.fromstring(etree.tostring(elem))


def _add_top_level_comment(
    tree_root: Path,
    *,
    anchor_text: str,
    body: str,
    author: str,
    initials: str,
    date_iso: str,
    anchor_all: bool,
) -> int:
    """Anchor-wrap path. Returns count of comments created (0 on no-match)."""
    doc_path = tree_root / "word" / "document.xml"
    if not doc_path.is_file():
        raise RuntimeError(
            "input is not a wordprocessing document (missing "
            "word/document.xml)"
        )
    doc_tree = etree.parse(str(doc_path))

    comments_path, comments_tree = _ensure_comments_part(tree_root)
    comments_root = comments_tree.getroot()
    next_id = _next_comment_id(comments_root)

    # Reserve paraId/durableId per match upfront so we can write them
    # to comments.xml + commentsExtended/Ids/Extensible in one pass
    # after all matches are wrapped.
    new_para_ids: list[str] = []
    new_durable_ids: list[str] = []

    matches = 0
    for paragraph in doc_tree.iter(qn("w:p")):
        _merge_adjacent_runs(paragraph)
        n_in_p = _wrap_anchors_in_paragraph(
            paragraph, anchor_text, next_id + matches,
            anchor_all=anchor_all,
        )
        for k in range(n_in_p):
            para_id = _random_hex_id()
            durable_id = _random_hex_id()
            new_para_ids.append(para_id)
            new_durable_ids.append(durable_id)
            new_comment = _build_comment_element(
                next_id + matches + k, body, author, initials, date_iso,
                para_id=para_id,
            )
            comments_root.append(new_comment)
        matches += n_in_p
        if not anchor_all and matches:
            break

    if matches == 0:
        return 0

    doc_tree.write(str(doc_path), xml_declaration=True,
                   encoding="UTF-8", standalone=True)
    comments_tree.write(str(comments_path), xml_declaration=True,
                        encoding="UTF-8", standalone=True)

    # Wire side-parts so future replies can thread; also keeps Word
    # 2016+ happy (it gets confused if comments.xml has w14:paraId
    # but no commentsIds.xml partner).
    ext_path, ext_tree = _ensure_comments_extended_part(tree_root)
    ids_path, ids_tree = _ensure_comments_ids_part(tree_root)
    cex_path, cex_tree = _ensure_comments_extensible_part(tree_root)
    for para_id, durable_id in zip(new_para_ids, new_durable_ids):
        _append_comment_extended(
            ext_tree.getroot(), para_id=para_id, parent_para_id=None,
        )
        _append_comment_id(
            ids_tree.getroot(), para_id=para_id, durable_id=durable_id,
        )
        _append_comment_extensible(
            cex_tree.getroot(), durable_id=durable_id, date_iso=date_iso,
        )
    ext_tree.write(str(ext_path), xml_declaration=True,
                   encoding="UTF-8", standalone=True)
    ids_tree.write(str(ids_path), xml_declaration=True,
                   encoding="UTF-8", standalone=True)
    cex_tree.write(str(cex_path), xml_declaration=True,
                   encoding="UTF-8", standalone=True)

    _ensure_relationship(
        tree_root / "word" / "_rels" / "document.xml.rels",
        rel_type=COMMENTS_REL_TYPE, target="comments.xml",
    )
    _ensure_content_type(
        tree_root / "[Content_Types].xml",
        part_name=COMMENTS_PART, content_type=COMMENTS_CT,
    )
    return matches


class _ParentNotFound(Exception):
    """Parent comment id is not present in word/comments.xml."""


class _ParentRangeNotFound(Exception):
    """Parent comment exists but its range markers are missing in
    document.xml — the file is structurally inconsistent."""


def _add_reply(
    tree_root: Path,
    *,
    parent_id: int,
    body: str,
    author: str,
    initials: str,
    date_iso: str,
) -> int:
    """Reply path. Returns 1 on success, raises _ParentNotFound /
    _ParentRangeNotFound otherwise."""
    doc_path = tree_root / "word" / "document.xml"
    if not doc_path.is_file():
        raise RuntimeError(
            "input is not a wordprocessing document (missing "
            "word/document.xml)"
        )
    doc_tree = etree.parse(str(doc_path))
    doc_root = doc_tree.getroot()

    comments_path, comments_tree = _ensure_comments_part(tree_root)
    comments_root = comments_tree.getroot()

    parent_el = _find_comment_element(comments_root, parent_id)
    if parent_el is None:
        raise _ParentNotFound(parent_id)

    parent_para_id = _get_comment_para_id(parent_el)
    if parent_para_id is None:
        # Older comments.xml without w14:paraId — back-fill so the
        # reply has something to thread against. Word tolerates this.
        parent_para_id = _random_hex_id()
        parent_p = parent_el.find(qn("w:p"))
        if parent_p is not None:
            parent_p.set(f"{{{W14_NS}}}paraId", parent_para_id)
            parent_p.set(f"{{{W14_NS}}}textId", "77777777")

    reply_id = _next_comment_id(comments_root)
    reply_para_id = _random_hex_id()
    reply_durable_id = _random_hex_id()

    if not _wrap_reply_in_parent_range(doc_root, parent_id, reply_id):
        raise _ParentRangeNotFound(parent_id)

    reply_comment = _build_comment_element(
        reply_id, body, author, initials, date_iso,
        para_id=reply_para_id,
    )
    comments_root.append(reply_comment)

    doc_tree.write(str(doc_path), xml_declaration=True,
                   encoding="UTF-8", standalone=True)
    comments_tree.write(str(comments_path), xml_declaration=True,
                        encoding="UTF-8", standalone=True)

    ext_path, ext_tree = _ensure_comments_extended_part(tree_root)
    ids_path, ids_tree = _ensure_comments_ids_part(tree_root)
    cex_path, cex_tree = _ensure_comments_extensible_part(tree_root)
    # Flatten reply chains: if --parent points at a comment that is itself
    # a reply, walk up to the root of the conversation. Word's review
    # pane displays a single flat thread under the root regardless of
    # how the disk shape was nested, and writing chained paraIdParents
    # is what causes Word's "Reply" button to mis-target the next click.
    root_parent_para_id = _resolve_root_para_id(
        ext_tree.getroot(), parent_para_id,
    )
    _append_comment_extended(
        ext_tree.getroot(),
        para_id=reply_para_id, parent_para_id=root_parent_para_id,
    )
    _append_comment_id(
        ids_tree.getroot(),
        para_id=reply_para_id, durable_id=reply_durable_id,
    )
    _append_comment_extensible(
        cex_tree.getroot(),
        durable_id=reply_durable_id, date_iso=date_iso,
    )
    ext_tree.write(str(ext_path), xml_declaration=True,
                   encoding="UTF-8", standalone=True)
    ids_tree.write(str(ids_path), xml_declaration=True,
                   encoding="UTF-8", standalone=True)
    cex_tree.write(str(cex_path), xml_declaration=True,
                   encoding="UTF-8", standalone=True)

    _ensure_relationship(
        tree_root / "word" / "_rels" / "document.xml.rels",
        rel_type=COMMENTS_REL_TYPE, target="comments.xml",
    )
    _ensure_content_type(
        tree_root / "[Content_Types].xml",
        part_name=COMMENTS_PART, content_type=COMMENTS_CT,
    )
    return 1


def add_comment(
    tree_root: Path,
    *,
    body: str,
    author: str,
    initials: str,
    date_iso: str,
    anchor_text: str | None = None,
    anchor_all: bool = False,
    parent_id: int | None = None,
) -> int:
    """Top-level dispatch: anchor-wrap a new comment OR thread a reply
    onto an existing one. Returns count of comments added (0/1 for
    replies, 0..N for anchor mode)."""
    if parent_id is not None:
        return _add_reply(
            tree_root,
            parent_id=parent_id,
            body=body, author=author, initials=initials, date_iso=date_iso,
        )
    if not anchor_text:
        raise ValueError("anchor_text is required when parent_id is not set")
    return _add_top_level_comment(
        tree_root,
        anchor_text=anchor_text, body=body, author=author,
        initials=initials, date_iso=date_iso, anchor_all=anchor_all,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, nargs="?",
                        help="Source .docx file (omit when using --unpacked-dir).")
    parser.add_argument("output", type=Path, nargs="?",
                        help="Destination .docx (omit when using --unpacked-dir).")
    parser.add_argument("--unpacked-dir", type=Path, default=None,
                        help="Operate in-place on an already-unpacked OOXML "
                             "tree. Mutually exclusive with INPUT/OUTPUT. "
                             "Skips encryption and same-path checks.")
    parser.add_argument("--anchor-text", default=None,
                        help="Substring to attach a NEW comment to "
                             "(must fit within a single run after the "
                             "automatic adjacent-run merge). Required "
                             "unless --parent is given.")
    parser.add_argument("--comment", required=True,
                        help="Comment body text (plain).")
    parser.add_argument("--parent", type=int, default=None,
                        help="Reply to existing comment with this id. "
                             "Inherits the parent's anchor range; "
                             "--anchor-text is ignored when set.")
    parser.add_argument("--author", default="Robot",
                        help="Author name shown in Word's review pane. "
                             "Default: Robot.")
    parser.add_argument("--initials", default=None,
                        help="Author initials (max 8 chars). "
                             "Default: derived from --author.")
    parser.add_argument("--date", default=None,
                        help="ISO 8601 date string for the comment. "
                             "Default: current UTC time.")
    parser.add_argument("--all", dest="anchor_all", action="store_true",
                        help="Comment every occurrence of --anchor-text. "
                             "Default: comment only the first match. "
                             "Ignored when --parent is given.")
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    library_mode = args.unpacked_dir is not None
    if library_mode:
        if args.input is not None or args.output is not None:
            return report_error(
                "--unpacked-dir is mutually exclusive with INPUT/OUTPUT",
                code=2, error_type="UsageError", json_mode=je,
            )
    else:
        if args.input is None or args.output is None:
            return report_error(
                "INPUT and OUTPUT are required (or use --unpacked-dir)",
                code=2, error_type="UsageError", json_mode=je,
            )

    if args.parent is None and not args.anchor_text:
        return report_error(
            "--anchor-text is required when --parent is not given",
            code=2, error_type="UsageError", json_mode=je,
        )

    initials = args.initials or _initials_from_author(args.author)
    if args.date:
        date_iso = args.date
    else:
        date_iso = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    def _do_add(tree_root: Path) -> int:
        """Run add_comment; raise translated errors. Returns count."""
        return add_comment(
            tree_root,
            anchor_text=args.anchor_text,
            body=args.comment,
            author=args.author,
            initials=initials,
            date_iso=date_iso,
            anchor_all=args.anchor_all,
            parent_id=args.parent,
        )

    if library_mode:
        tree_root = args.unpacked_dir.resolve()
        if not (tree_root / "word" / "document.xml").is_file():
            return report_error(
                f"--unpacked-dir does not look like an unpacked .docx tree "
                f"(missing word/document.xml): {tree_root}",
                code=1, error_type="NotADocxTree",
                details={"path": str(tree_root)}, json_mode=je,
            )
        try:
            n = _do_add(tree_root)
        except _ParentNotFound as exc:
            return report_error(
                f"parent comment {exc} not found in word/comments.xml",
                code=2, error_type="ParentCommentNotFound",
                details={"parent_id": int(str(exc))}, json_mode=je,
            )
        except _ParentRangeNotFound as exc:
            return report_error(
                f"parent comment {exc} exists in comments.xml but its "
                f"range markers are missing in document.xml "
                f"(structurally inconsistent file)",
                code=2, error_type="ParentRangeNotFound",
                details={"parent_id": int(str(exc))}, json_mode=je,
            )
        except etree.XMLSyntaxError as exc:
            return report_error(
                f"OOXML parse error in input tree: {exc}",
                code=1, error_type="MalformedOOXML",
                details={"detail": str(exc)}, json_mode=je,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return report_error(
                f"add-comment failed: {exc}", code=1,
                error_type=type(exc).__name__, json_mode=je,
            )
        if n == 0:
            return report_error(
                f"anchor text not found: {args.anchor_text!r}",
                code=2, error_type="AnchorNotFound",
                details={"anchor_text": args.anchor_text}, json_mode=je,
            )
        if args.parent is not None:
            print(f"{tree_root}: added {n} reply(s) "
                  f"to comment {args.parent} (author={args.author!r})")
        else:
            print(f"{tree_root}: added {n} comment(s) "
                  f"(anchor={args.anchor_text!r}, author={args.author!r})")
        return 0

    # Zip-mode (INPUT.docx → OUTPUT.docx)
    if not args.input.is_file():
        return report_error(
            f"Input not found: {args.input}", code=1,
            error_type="FileNotFound",
            details={"path": str(args.input)}, json_mode=je,
        )

    try:
        in_resolved = args.input.resolve(strict=False)
        out_resolved = args.output.resolve(strict=False)
    except OSError:
        in_resolved = args.input
        out_resolved = args.output
    if in_resolved == out_resolved:
        return report_error(
            f"INPUT and OUTPUT resolve to the same path: {in_resolved} "
            f"(would corrupt the source on a pack-time crash)",
            code=6, error_type="SelfOverwriteRefused",
            details={"input": str(args.input),
                     "output": str(args.output)},
            json_mode=je,
        )

    try:
        assert_not_encrypted(args.input)
    except EncryptedFileError as exc:
        return report_error(str(exc), code=3,
                            error_type="EncryptedFileError",
                            details={"path": str(args.input)},
                            json_mode=je)

    warn_if_macros_will_be_dropped(args.input, args.output, sys.stderr)

    try:
        with tempfile.TemporaryDirectory(prefix="docx_add_comment-") as td:
            tree_root = Path(td) / "tree"
            unpack(args.input, tree_root)
            try:
                n = _do_add(tree_root)
            except _ParentNotFound as exc:
                return report_error(
                    f"parent comment {exc} not found in word/comments.xml",
                    code=2, error_type="ParentCommentNotFound",
                    details={"parent_id": int(str(exc))}, json_mode=je,
                )
            except _ParentRangeNotFound as exc:
                return report_error(
                    f"parent comment {exc} exists in comments.xml but its "
                    f"range markers are missing in document.xml "
                    f"(structurally inconsistent file)",
                    code=2, error_type="ParentRangeNotFound",
                    details={"parent_id": int(str(exc))}, json_mode=je,
                )
            if n == 0:
                return report_error(
                    f"anchor text not found: {args.anchor_text!r} "
                    f"(must fit within a single run; try a shorter / "
                    f"more uniform substring)",
                    code=2, error_type="AnchorNotFound",
                    details={"anchor_text": args.anchor_text},
                    json_mode=je,
                )
            pack(tree_root, args.output)
    except (RuntimeError, ValueError, OSError) as exc:
        return report_error(
            f"add-comment failed: {exc}", code=1,
            error_type=type(exc).__name__, json_mode=je,
        )

    if args.parent is not None:
        print(f"{args.output}: added {n} reply(s) "
              f"to comment {args.parent} (author={args.author!r})")
    else:
        print(f"{args.output}: added {n} comment(s) "
              f"(anchor={args.anchor_text!r}, author={args.author!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

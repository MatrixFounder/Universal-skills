#!/usr/bin/env python3
"""Insert a Word comment into a .docx by anchoring on text.

Why direct OOXML XML editing instead of `python-docx`: as of
python-docx 1.2 the high-level API exposes no way to add comments —
the `<w:comments>` part, the inline `<w:commentRangeStart/End>`
markers, and the `<w:commentReference>` run all need to be wired
together by hand. We unpack the .docx (`office.unpack`), edit the
relevant XML parts via lxml, and repack (`office.pack`) — the same
pattern `docx_fill_template.py` uses.

Usage:
    docx_add_comment.py INPUT.docx OUTPUT.docx \\
        --anchor-text "phrase to attach the comment to" \\
        --comment "Please verify formula X" \\
        [--author "Reviewer Bot"] [--initials RB] \\
        [--date 2026-04-27T12:34:56Z] [--all] \\
        [--json-errors]

`--anchor-text` must occur within a single `<w:t>` element of one
paragraph (after the same run-merge pass `docx_fill_template`
performs). When Word splits text across runs with different
formatting, the helper merges adjacent runs that share identical
`<w:rPr>`; if the anchor still spans formatting boundaries the
script exits 2 with a hint to pick a more uniform substring.

Exit codes:
    0  — comment added successfully
    1  — I/O / pack failure
    2  — argparse usage error / anchor not found / anchor spans
         formatting boundaries
    3  — input is password-protected or legacy CFB (cross-3 contract)
    6  — INPUT and OUTPUT resolve to the same path (cross-7 H1
         SelfOverwriteRefused parity)
"""
from __future__ import annotations

import argparse
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
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

COMMENTS_PART = "word/comments.xml"
COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
COMMENTS_CT = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.comments+xml"
)


def _initials_from_author(author: str) -> str:
    parts = re.findall(r"\w+", author)
    return ("".join(p[:1] for p in parts) or "R").upper()[:8]


def _rpr_key(run: etree._Element) -> bytes:
    rpr = run.find(qn("w:rPr"))
    return b"" if rpr is None else etree.tostring(rpr, method="c14n")


def _is_simple_text_run(run: etree._Element) -> bool:
    for child in run:
        tag = etree.QName(child).localname
        if tag not in {"rPr", "t"}:
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


def _build_comment_element(
    comment_id: int,
    body: str,
    author: str,
    initials: str,
    date_iso: str,
) -> etree._Element:
    nsmap = {"w": W_NS}
    comment = etree.Element(qn("w:comment"), nsmap=nsmap)
    comment.set(qn("w:id"), str(comment_id))
    comment.set(qn("w:author"), author)
    comment.set(qn("w:initials"), initials)
    comment.set(qn("w:date"), date_iso)
    p = etree.SubElement(comment, qn("w:p"))
    pPr = etree.SubElement(p, qn("w:pPr"))
    rStyle = etree.SubElement(pPr, qn("w:pStyle"))
    rStyle.set(qn("w:val"), "CommentText")
    r = etree.SubElement(p, qn("w:r"))
    rPr = etree.SubElement(r, qn("w:rPr"))
    annot = etree.SubElement(rPr, qn("w:rStyle"))
    annot.set(qn("w:val"), "CommentReference")
    t = etree.SubElement(r, qn("w:t"))
    t.text = body
    if " " in body or body != body.strip():
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
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
    root = etree.Element(qn("w:comments"), nsmap={"w": W_NS})
    tree = etree.ElementTree(root)
    tree.write(str(path), xml_declaration=True,
               encoding="UTF-8", standalone=True)
    return path, tree


def _ensure_relationship(rels_path: Path) -> None:
    """Make sure word/_rels/document.xml.rels has an entry pointing at
    comments.xml. Idempotent."""
    if not rels_path.is_file():
        raise RuntimeError(f"missing relationships file: {rels_path}")
    tree = etree.parse(str(rels_path))
    root = tree.getroot()
    for rel in root.findall(f"{{{PR_NS}}}Relationship"):
        if rel.get("Type") == COMMENTS_REL_TYPE:
            return  # already wired

    existing_ids = {
        r.get("Id") for r in root.findall(f"{{{PR_NS}}}Relationship")
    }
    n = 1
    while f"rId{n}" in existing_ids:
        n += 1
    new = etree.SubElement(root, f"{{{PR_NS}}}Relationship")
    new.set("Id", f"rId{n}")
    new.set("Type", COMMENTS_REL_TYPE)
    new.set("Target", "comments.xml")
    tree.write(str(rels_path), xml_declaration=True,
               encoding="UTF-8", standalone=True)


def _ensure_content_type(content_types_path: Path) -> None:
    """Make sure [Content_Types].xml has an Override for comments.xml."""
    tree = etree.parse(str(content_types_path))
    root = tree.getroot()
    for ovr in root.findall(f"{{{CT_NS}}}Override"):
        if ovr.get("PartName") == "/word/comments.xml":
            return
    new = etree.SubElement(root, f"{{{CT_NS}}}Override")
    new.set("PartName", "/word/comments.xml")
    new.set("ContentType", COMMENTS_CT)
    tree.write(str(content_types_path), xml_declaration=True,
               encoding="UTF-8", standalone=True)


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


def _clone(elem: etree._Element) -> etree._Element:
    """Deep-copy via serialize/parse — preserves namespaces correctly."""
    return etree.fromstring(etree.tostring(elem))


def add_comment(
    tree_root: Path,
    anchor_text: str,
    body: str,
    author: str,
    initials: str,
    date_iso: str,
    *,
    anchor_all: bool,
) -> int:
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

    matches = 0
    for paragraph in doc_tree.iter(qn("w:p")):
        _merge_adjacent_runs(paragraph)
        # Wrap every occurrence within the paragraph in a single pass.
        # `_wrap_anchors_in_paragraph` returns the count of wraps it
        # performed (1 in default mode, 0..N with --all).
        n_in_p = _wrap_anchors_in_paragraph(
            paragraph, anchor_text, next_id + matches,
            anchor_all=anchor_all,
        )
        for k in range(n_in_p):
            new_comment = _build_comment_element(
                next_id + matches + k, body, author, initials, date_iso,
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

    _ensure_relationship(tree_root / "word" / "_rels" / "document.xml.rels")
    _ensure_content_type(tree_root / "[Content_Types].xml")
    return matches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--anchor-text", required=True,
                        help="Substring to attach the comment to "
                             "(must fit within a single run after the "
                             "automatic adjacent-run merge).")
    parser.add_argument("--comment", required=True,
                        help="Comment body text (plain).")
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
                             "Default: comment only the first match.")
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    if not args.input.is_file():
        return report_error(
            f"Input not found: {args.input}", code=1,
            error_type="FileNotFound",
            details={"path": str(args.input)}, json_mode=je,
        )

    # Refuse same-path I/O before any unpack/pack runs. resolve() catches
    # the symlink case where input != output literally but they point at
    # the same inode. Mirrors office_passwd.py's H1 SelfOverwriteRefused
    # guard (cross-7 contract); on a pack-time crash the user otherwise
    # ends up with neither the original nor a valid output.
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

    initials = args.initials or _initials_from_author(args.author)
    if args.date:
        date_iso = args.date
    else:
        date_iso = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    try:
        with tempfile.TemporaryDirectory(prefix="docx_add_comment-") as td:
            tree_root = Path(td) / "tree"
            unpack(args.input, tree_root)
            n = add_comment(
                tree_root,
                anchor_text=args.anchor_text,
                body=args.comment,
                author=args.author,
                initials=initials,
                date_iso=date_iso,
                anchor_all=args.anchor_all,
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

    print(f"{args.output}: added {n} comment(s) "
          f"(anchor='{args.anchor_text}', author={args.author!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

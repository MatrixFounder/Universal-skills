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
    """Warn only for parts that actually carry user content. md2docx.js
    (and Word's default templates) ship empty / boilerplate
    `numbering.xml`, `footnotes.xml`, `comments.xml` even on documents
    that have no lists / footnotes / comments — flagging those would
    fire on every merge and train the user to ignore the warning."""
    word = extra_root / "word"
    flags = []

    # numbering.xml: the standard md2docx fixture ships exactly 1
    # default `<w:num>` definition. Warn only when the doc has its own
    # additional numbering instances that won't be merged.
    if _count_children(word / "numbering.xml", "num") > 1:
        flags.append("numbering.xml (list continuity may break)")

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

    # Media + headers/footers are present only when the user
    # deliberately added them — no boilerplate cases.
    if (word / "media").is_dir() and any((word / "media").iterdir()):
        flags.append("word/media/ (image references in body will dangle)")
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
    *,
    page_break_before: bool,
    merge_styles: bool,
) -> dict[str, int]:
    """Append every body child of extra/word/document.xml to
    base/word/document.xml (before base's `<w:sectPr>`), and copy
    missing style definitions if `merge_styles`."""
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
        # Skip the extra's own sectPr — only the base's sectPr matters.
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

    style_count = 0
    if merge_styles:
        style_count = _merge_styles(
            base_dir / "word" / "styles.xml",
            extra_dir / "word" / "styles.xml",
        )

    return {"body_children": appended, "styles": style_count}


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

            totals = {"body_children": 0, "styles": 0}
            for i, extra in enumerate(args.inputs[1:], start=1):
                extra_dir = tdp / f"extra_{i}"
                unpack(extra, extra_dir)
                _warn_unsupported_parts(extra_dir, str(extra), sys.stderr)
                stats = merge_into_base(
                    base_dir, extra_dir,
                    page_break_before=args.page_break_between,
                    merge_styles=not args.no_merge_styles,
                )
                totals["body_children"] += stats["body_children"]
                totals["styles"] += stats["styles"]

            pack(base_dir, args.output)
    except (RuntimeError, ValueError, OSError) as exc:
        return report_error(
            f"merge failed: {exc}", code=1,
            error_type=type(exc).__name__, json_mode=je,
        )

    print(f"{args.output}: merged {len(args.inputs)} inputs "
          f"(+{totals['body_children']} body children, "
          f"+{totals['styles']} styles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

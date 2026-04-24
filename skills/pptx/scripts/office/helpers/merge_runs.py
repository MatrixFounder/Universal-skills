"""Collapse adjacent `<w:r>` siblings that share identical `<w:rPr>`.

Word, Google Docs, and the `docx` npm library all produce DOCX files in
which a single logical run of text is sometimes stored as several
separate `<w:r>` elements with byte-identical formatting (spell-check
passes, autocorrect events, and interrupted typing are common
triggers). Merging them before any regex-driven editing prevents
placeholders such as `{{name}}` from being split across run boundaries
and becoming unfindable.

This helper is a no-op on anything that is not a WordprocessingML
`<w:body>`-rooted tree. It never touches runs containing non-text
children (breaks, field codes, images, tabs) so non-text content
cannot be damaged.

Public API:
    merge_runs_in_tree(tree: _ElementTree | _Element) -> int
        Returns the number of merges performed.

The implementation follows the rules in ECMA-376 Part 1 §17 and the
equivalent `[MS-DOCX]` section on run properties.
"""

from __future__ import annotations

from lxml import etree  # type: ignore

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"

_W = f"{{{W_NS}}}"
_XML_SPACE = f"{{{XML_NS}}}space"


def _is_mergeable_run(run: etree._Element) -> bool:
    for child in run:
        tag = etree.QName(child).localname
        if tag not in ("rPr", "t"):
            return False
    return True


def _rpr_key(run: etree._Element) -> bytes:
    rpr = run.find(f"{_W}rPr")
    if rpr is None:
        return b""
    return etree.tostring(rpr, method="c14n")


def _merge_pair(a: etree._Element, b: etree._Element) -> bool:
    a_t = a.find(f"{_W}t")
    b_t = b.find(f"{_W}t")
    if a_t is None or b_t is None:
        return False
    combined = (a_t.text or "") + (b_t.text or "")
    a_t.text = combined
    if combined != combined.strip():
        a_t.set(_XML_SPACE, "preserve")
    parent = b.getparent()
    if parent is not None:
        parent.remove(b)
    return True


def _merge_in_paragraph(paragraph: etree._Element) -> int:
    merges = 0
    runs = paragraph.findall(f"{_W}r")
    i = 0
    while i < len(runs) - 1:
        a, b = runs[i], runs[i + 1]
        if (
            _is_mergeable_run(a)
            and _is_mergeable_run(b)
            and _rpr_key(a) == _rpr_key(b)
            and _merge_pair(a, b)
        ):
            merges += 1
            runs = paragraph.findall(f"{_W}r")
        else:
            i += 1
    return merges


def merge_runs_in_tree(tree: etree._Element | etree._ElementTree) -> int:
    root = tree.getroot() if isinstance(tree, etree._ElementTree) else tree
    total = 0
    for paragraph in root.iter(f"{_W}p"):
        total += _merge_in_paragraph(paragraph)
    return total

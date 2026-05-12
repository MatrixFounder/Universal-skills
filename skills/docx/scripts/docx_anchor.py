"""Shared anchor-finding helpers for the docx skill.

Extracted from docx_add_comment.py at task 006-01a (chain: docx-6,
docx_replace.py). Imported by docx_add_comment.py and (in subsequent
sub-tasks 006-02..06) by docx_replace.py.

Module is **docx-only** (sibling to docx_add_comment.py inside
skills/docx/scripts/, NOT under office/) so the cross-skill replication
boundary in CLAUDE.md §2 is preserved.
"""

from __future__ import annotations

from docx.oxml.ns import qn  # type: ignore
from lxml import etree  # type: ignore


# === extracted from docx_add_comment.py (byte-identical bodies) ===

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


# === new helpers (006-02) ===

def _replace_in_run(
    paragraph: etree._Element,
    anchor: str,
    replacement: str,
    *,
    anchor_all: bool,
) -> int:
    """Cursor-loop replace inside simple text runs of `paragraph`.

    Returns the count of replacements performed. Stops after first match
    unless `anchor_all=True`. Caller must have already invoked
    `_merge_adjacent_runs(paragraph)`.

    Honest scope (D6 / B): anchor must fit within ONE <w:t> after the
    merge — cross-run anchors are NOT matched here.
    """
    # Empty anchor would loop infinitely (str.find("", n) always == n).
    if not anchor:
        return 0
    count = 0
    for run in paragraph.iter(qn("w:r")):
        if not _is_simple_text_run(run):
            continue
        t_elem = run.find(qn("w:t"))
        if t_elem is None or t_elem.text is None:
            continue
        text = t_elem.text
        if anchor not in text:
            continue
        # Cursor-loop: rebuild text by walking and splicing.
        cursor = 0
        parts: list[str] = []
        local_count = 0
        while True:
            idx = text.find(anchor, cursor)
            if idx == -1:
                parts.append(text[cursor:])
                break
            parts.append(text[cursor:idx])
            parts.append(replacement)
            local_count += 1
            cursor = idx + len(anchor)
            if not anchor_all:
                parts.append(text[cursor:])
                break
        new_text = "".join(parts)
        t_elem.text = new_text
        # xml:space="preserve" when result has leading/trailing space or
        # whitespace != stripped form (R1.g).
        if new_text != new_text.strip() or "  " in new_text:
            t_elem.set(
                "{http://www.w3.org/XML/1998/namespace}space", "preserve",
            )
        count += local_count
        if count > 0 and not anchor_all:
            return count
    return count


def _concat_paragraph_text(paragraph: etree._Element) -> str:
    """Concatenate all <w:t> descendants of `paragraph`, EXCLUDING
    content under <w:del> ancestors (Q-U1 default — `<w:del>` is
    tracked-deletion text and should not match).

    <w:ins> content is INCLUDED (tracked-insertion text is live).
    """
    parts: list[str] = []
    for t_elem in paragraph.iter(qn("w:t")):
        # Walk ancestors; if any is <w:del>, skip this <w:t>.
        skip = False
        anc = t_elem.getparent()
        while anc is not None and anc is not paragraph:
            if etree.QName(anc).localname == "del":
                skip = True
                break
            anc = anc.getparent()
        if skip:
            continue
        if t_elem.text:
            parts.append(t_elem.text)
    return "".join(parts)


def _find_paragraphs_containing_anchor(
    part_root: etree._Element,
    anchor: str,
) -> list[etree._Element]:
    """Return all <w:p> elements whose concat-text contains `anchor`,
    in document order. Used by paragraph-level actions (D6 / B).
    """
    # Empty anchor matches everything via str.__contains__; refuse early.
    if not anchor:
        return []
    matches: list[etree._Element] = []
    for p in part_root.iter(qn("w:p")):
        # Fast negative filter: skip paragraphs whose raw text (including
        # <w:del> content) doesn't contain the anchor at all.
        # itertext() is a STRICT SUPER-SET of _concat_paragraph_text() so
        # it is safe as a NEGATIVE filter only (no false negatives).
        raw = "".join(p.itertext())
        if anchor not in raw:
            continue
        if anchor in _concat_paragraph_text(p):
            matches.append(p)
    return matches

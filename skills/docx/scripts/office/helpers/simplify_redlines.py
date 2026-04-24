"""Merge adjacent tracked-change markers by the same author.

WordprocessingML records inserted text as `<w:ins>` and deleted text as
`<w:del>`. Editors frequently produce chains of such elements — a single
logical edit like "replace one word with another" might land as several
sequential `<w:ins>`/`<w:del>` siblings. This helper merges adjacent
markers of the same kind, same author, and same date (minute precision)
so downstream XML diffing is cleaner and files remain within Word's
display expectations.

Merging rules (conservative — preserves authorship/attribution):
- Only adjacent siblings with the same local tag (`w:ins` or `w:del`)
  are merged.
- They must have the same `w:author`, and their `w:date` values must be
  within one minute of each other.
- They must share the same parent paragraph — no cross-paragraph merge.
- Their `w:id` attributes are reassigned to a unique monotonic sequence
  after merging (ECMA-376 §17.13 requires uniqueness but no ordering).

Public API:
    simplify_redlines_in_tree(tree) -> int
"""

from __future__ import annotations

from lxml import etree  # type: ignore

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{W_NS}}}"


def _same_author_date(a: etree._Element, b: etree._Element) -> bool:
    if a.get(f"{_W}author") != b.get(f"{_W}author"):
        return False
    date_a = (a.get(f"{_W}date") or "")[:16]
    date_b = (b.get(f"{_W}date") or "")[:16]
    return date_a == date_b


def _merge_into(target: etree._Element, source: etree._Element) -> None:
    for child in list(source):
        target.append(child)
    parent = source.getparent()
    if parent is not None:
        parent.remove(source)


def _simplify_in_parent(parent: etree._Element) -> int:
    merges = 0
    children = list(parent)
    i = 0
    while i < len(children) - 1:
        a, b = children[i], children[i + 1]
        tag_a = etree.QName(a).localname if a.tag.startswith(f"{_W}") else None
        tag_b = etree.QName(b).localname if b.tag.startswith(f"{_W}") else None
        if tag_a in ("ins", "del") and tag_a == tag_b and _same_author_date(a, b):
            _merge_into(a, b)
            merges += 1
            children = list(parent)
        else:
            i += 1
    return merges


def _renumber(root: etree._Element) -> None:
    next_id = 1
    for el in root.iter():
        if el.tag in (f"{_W}ins", f"{_W}del"):
            el.set(f"{_W}id", str(next_id))
            next_id += 1


def simplify_redlines_in_tree(tree: etree._Element | etree._ElementTree) -> int:
    root = tree.getroot() if isinstance(tree, etree._ElementTree) else tree
    total = 0
    for parent in root.iter():
        if len(parent) > 1:
            total += _simplify_in_parent(parent)
    if total:
        _renumber(root)
    return total

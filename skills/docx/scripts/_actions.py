"""Action helpers for docx_replace.py — extracted at task 006-07a per
ARCH §3.2 Q-A1 guardrail (docx_replace.py exceeded 600 LOC after F6
landed). Module is docx-only (sibling to docx_replace.py inside
skills/docx/scripts/, NOT under office/) so the cross-skill replication
boundary in CLAUDE.md §2 is preserved.

This module owns F2 (part walker), F4 (replace), F5 (insert-after), F6
(delete-paragraph). docx_replace.py owns F1 (pre-flight), F7 (CLI
orchestration), F8 (post-validate).
"""
from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path
from typing import Iterator

from lxml import etree  # type: ignore
from docx.oxml.ns import qn  # type: ignore

# Hardened XML parser — mirrors office/validators/base.py; defangs XXE /
# external-entity expansion + DTD-based attacks (CWE-611). Used for every
# etree.parse() call on caller-supplied XML in this module.
_SAFE_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, load_dtd=False,
)

from _app_errors import (
    EmptyInsertSource,
    LastParagraphCannotBeDeleted,
    Md2DocxFailed,
    Md2DocxNotAvailable,
    Md2DocxOutputInvalid,
)
from docx_anchor import (
    _merge_adjacent_runs,
    _replace_in_run,
    _find_paragraphs_containing_anchor,
)


# ---------------------------------------------------------------------------
# F2: part-walker — searchable part enumeration (R5)
# ---------------------------------------------------------------------------

_WP_CONTENT_TYPES = {
    # Standard .docx main document part.
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml": "document",
    # Macro-enabled .docm main document part (R8.k support).
    "application/vnd.ms-word.document.macroEnabled.main+xml": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml": "header",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml": "footer",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml": "footnotes",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml": "endnotes",
}


def _fallback_glob_parts(
    tree_root: Path, parts_by_role: dict[str, list[Path]],
) -> None:
    """Populate parts_by_role by globbing word/ directory."""
    word = tree_root / "word"
    if not word.is_dir():
        return
    doc = word / "document.xml"
    if doc.is_file():
        parts_by_role["document"].append(doc)
    parts_by_role["header"].extend(sorted(word.glob("header*.xml")))
    parts_by_role["footer"].extend(sorted(word.glob("footer*.xml")))
    fn = word / "footnotes.xml"
    if fn.is_file():
        parts_by_role["footnotes"].append(fn)
    en = word / "endnotes.xml"
    if en.is_file():
        parts_by_role["endnotes"].append(en)


def _iter_searchable_parts(
    tree_root: Path,
    scope: "set[str] | None" = None,
) -> Iterator[tuple[Path, etree._Element]]:
    """Yield (part_path, root_element) for every searchable XML part
    in tree_root, in deterministic order (R5.g):
    document -> headers (sorted) -> footers (sorted) -> footnotes -> endnotes.

    Primary enumeration source = [Content_Types].xml Override entries
    (ARCH MIN-3). Filesystem glob is a fallback only if Content_Types
    is missing or malformed (stderr warning).

    `scope` (docx-6.7) restricts which roles are yielded. `None` = all
    roles (back-compat with pre-docx-6.7 callers). Otherwise must be a
    subset of {"document", "header", "footer", "footnotes", "endnotes"};
    parts whose role is not in the set are silently skipped. Order WITHIN
    the requested set is preserved.
    """
    ct_path = tree_root / "[Content_Types].xml"
    parts_by_role: dict[str, list[Path]] = {
        "document": [], "header": [], "footer": [],
        "footnotes": [], "endnotes": [],
    }
    if ct_path.is_file():
        try:
            ct_tree = etree.parse(str(ct_path), _SAFE_PARSER)
            ns = {"ct": "http://schemas.openxmlformats.org/package/2006/content-types"}
            for ov in ct_tree.iterfind(".//ct:Override", ns):
                ct_value = ov.get("ContentType", "")
                role = _WP_CONTENT_TYPES.get(ct_value)
                if role is None:
                    continue
                pname = ov.get("PartName", "")
                rel = pname.lstrip("/")
                parts_by_role[role].append(tree_root / rel)
        except etree.XMLSyntaxError as exc:
            print(
                f"[docx_replace] WARNING: [Content_Types].xml parse failed "
                f"({exc}); falling back to filesystem glob.",
                file=sys.stderr,
            )
            _fallback_glob_parts(tree_root, parts_by_role)
    else:
        print(
            "[docx_replace] WARNING: [Content_Types].xml missing; "
            "falling back to filesystem glob.",
            file=sys.stderr,
        )
        _fallback_glob_parts(tree_root, parts_by_role)

    # If CT parsed cleanly but yielded no document.xml entry, fall back to
    # glob. Covers "sanitised Content_Types" / "non-Word OOXML producer" cases.
    if not parts_by_role["document"] and (tree_root / "word" / "document.xml").is_file():
        print(
            "[docx_replace] WARNING: [Content_Types].xml has no WordprocessingML "
            "document Override; falling back to filesystem glob.",
            file=sys.stderr,
        )
        _fallback_glob_parts(tree_root, parts_by_role)

    # Sort headers/footers by part name — lexicographic (R5.g).
    parts_by_role["header"].sort(key=lambda p: p.name)
    parts_by_role["footer"].sort(key=lambda p: p.name)

    for role in ("document", "header", "footer", "footnotes", "endnotes"):
        if scope is not None and role not in scope:
            continue  # docx-6.7: skip roles not in --scope set
        for p in parts_by_role[role]:
            if not p.is_file():
                continue  # corrupt-package tolerance
            root = etree.parse(str(p), _SAFE_PARSER).getroot()
            yield (p, root)


# ---------------------------------------------------------------------------
# F4: --replace action
# ---------------------------------------------------------------------------

def _do_replace(
    tree_root: Path,
    anchor: str,
    replacement: str,
    *,
    anchor_all: bool,
    scope: "set[str] | None" = None,
) -> int:
    """Walk every searchable part; in each paragraph run
    _merge_adjacent_runs + _replace_in_run. Returns total replacement
    count. Without --all, stops after first matched part is written.

    `scope` (docx-6.7): if not None, restrict parts to the given role
    subset (see `_iter_searchable_parts`).
    """
    total = 0
    for part_path, part_root in _iter_searchable_parts(tree_root, scope=scope):
        modified = False
        part_count = 0
        for p in part_root.iter(qn("w:p")):
            _merge_adjacent_runs(p)
            n = _replace_in_run(p, anchor, replacement, anchor_all=anchor_all)
            if n > 0:
                modified = True
                part_count += n
                if not anchor_all:
                    break  # first-match wins within this part
        if modified:
            with part_path.open("wb") as f:
                f.write(etree.tostring(
                    part_root, xml_declaration=True,
                    encoding="UTF-8", standalone=True,
                ))
            total += part_count
            if not anchor_all:
                return total  # first-match wins across all parts
    return total


# ---------------------------------------------------------------------------
# F5: --insert-after helpers
# ---------------------------------------------------------------------------

def _materialise_md_source(
    md_path: Path, scripts_dir: Path, tmpdir: Path,
) -> Path:
    """Run `node md2docx.js MD OUT` in subprocess; return path to the
    materialised .docx. shell=False, timeout=60, capture_output=True.
    Non-zero rc → raise Md2DocxFailed (exit 1)."""
    md2docx = scripts_dir / "md2docx.js"
    if not md2docx.is_file():
        raise Md2DocxNotAvailable(
            f"md2docx.js not found at {md2docx}",
            code=1, error_type="Md2DocxNotAvailable",
            details={"path": str(md2docx)},
        )
    out_docx = tmpdir / "insert.docx"
    try:
        result = subprocess.run(
            ["node", str(md2docx), str(md_path), str(out_docx)],
            shell=False, timeout=60, capture_output=True, text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        # Node binary not on PATH.
        raise Md2DocxNotAvailable(
            f"node binary not found: {exc}",
            code=1, error_type="Md2DocxNotAvailable",
            details={"detail": str(exc)},
        )
    except subprocess.TimeoutExpired as exc:
        raise Md2DocxFailed(
            "md2docx.js timed out (60s)",
            code=1, error_type="Md2DocxFailed",
            details={"stderr": (exc.stderr or "")[:8192],
                     "returncode": None, "reason": "timeout"},
        )
    if result.returncode != 0:
        raise Md2DocxFailed(
            f"md2docx.js failed (rc={result.returncode})",
            code=1, error_type="Md2DocxFailed",
            details={"stderr": (result.stderr or "")[:8192],
                     "returncode": result.returncode},
        )
    if not out_docx.is_file():
        raise Md2DocxOutputInvalid(
            "md2docx.js produced no output file",
            code=1, error_type="Md2DocxOutputInvalid",
            details={"expected": str(out_docx)},
        )
    return out_docx


def _deep_clone(el: "etree._Element") -> "etree._Element":
    """Return a deep copy of `el` for cross-tree splicing."""
    return copy.deepcopy(el)


def _extract_insert_paragraphs(
    insert_tree_root: Path,
    *,
    base_has_numbering: bool,
) -> "list[etree._Element]":
    """Deep-clone body block children from insert tree's word/document.xml.
    Strip ALL <w:sectPr> body-direct children (Q-A3 lock). Emit stderr
    warnings on r:embed/r:id references (R10.b) and on <w:numId> when
    base doc has no numbering.xml (Q-A4 / R10.e)."""
    doc_xml = insert_tree_root / "word" / "document.xml"
    if not doc_xml.is_file():
        raise Md2DocxOutputInvalid(
            "insert docx has no word/document.xml",
            code=1, error_type="Md2DocxOutputInvalid",
            details={"path": str(doc_xml)},
        )
    tree = etree.parse(str(doc_xml), _SAFE_PARSER)
    body = tree.find(qn("w:body"))
    if body is None:
        raise Md2DocxOutputInvalid(
            "insert docx body element missing",
            code=1, error_type="Md2DocxOutputInvalid",
            details={"path": str(doc_xml)},
        )
    children: "list[etree._Element]" = []
    saw_relationship_ref = False
    saw_numid = False
    for child in body:
        local = etree.QName(child).localname
        if local == "sectPr":
            continue  # Q-A3 strip.
        clone = _deep_clone(child)
        # Scan for relationship-bearing attributes (R10.b precursor warning).
        for el in clone.iter():
            for attr_name in el.attrib:
                if attr_name.endswith("}embed") or attr_name.endswith("}id"):
                    saw_relationship_ref = True
                    break
            if etree.QName(el).localname == "numId":
                saw_numid = True
        children.append(clone)
    if saw_relationship_ref:
        print(
            "[docx_replace] WARNING: inserted body references "
            "relationships (r:embed/r:id) that are not copied to the "
            "base document — embedded objects may not render. Use "
            "--insert-after with image-free markdown in v1.",
            file=sys.stderr,
        )
    if saw_numid and not base_has_numbering:
        print(
            "[docx_replace] WARNING: inserted body contains "
            "<w:numId> references; base document has no numbering.xml "
            "— list items may render as plain text. Relocate numbering "
            "in a future update.",
            file=sys.stderr,
        )
    return children


def _do_insert_after(
    tree_root: Path,
    anchor: str,
    insert_paragraphs: "list[etree._Element]",
    *,
    anchor_all: bool,
    scope: "set[str] | None" = None,
) -> int:
    """Locate matching paragraphs in every searchable part; insert
    deep-cloned `insert_paragraphs` immediately after each match.

    Without --all, stops at first match across all parts. Returns the
    count of anchor paragraphs after which content was inserted.

    `scope` (docx-6.7): if not None, restrict parts to the given role
    subset (see `_iter_searchable_parts`).
    """
    match_count = 0
    for part_path, part_root in _iter_searchable_parts(tree_root, scope=scope):
        matches = _find_paragraphs_containing_anchor(part_root, anchor)
        if not matches:
            continue
        for matched_p in matches:
            # Deep-clone the insert list per match (no shared refs).
            clones = [_deep_clone(p) for p in insert_paragraphs]
            # Insert AFTER matched_p: walk reversed and call addnext.
            for clone in reversed(clones):
                matched_p.addnext(clone)
            match_count += 1
            if not anchor_all:
                # Write this part and return.
                with part_path.open("wb") as f:
                    f.write(etree.tostring(
                        part_root, xml_declaration=True,
                        encoding="UTF-8", standalone=True,
                    ))
                return match_count
        # All matches in this part processed; write back.
        with part_path.open("wb") as f:
            f.write(etree.tostring(
                part_root, xml_declaration=True,
                encoding="UTF-8", standalone=True,
            ))
    return match_count


# ---------------------------------------------------------------------------
# F6: --delete-paragraph action
# ---------------------------------------------------------------------------

def _safe_remove_paragraph(
    p: etree._Element,
    part_root: etree._Element,
    *,
    anchor: str,
) -> None:
    """Remove `p` from its parent.

    Guards: (1) last-body-paragraph refusal (raises LastParagraphCannotBeDeleted);
    (2) empty-cell placeholder insertion after removal (Q-A5, ECMA-376 §17.4.66).
    """
    parent = p.getparent()
    if parent is None:  # defensive: orphan element
        return
    body = part_root.find(qn("w:body"))
    if body is not None and parent is body:
        body_p_count = sum(1 for c in body if etree.QName(c).localname == "p")
        if body_p_count <= 1:
            raise LastParagraphCannotBeDeleted(
                f"Refusing to delete the only <w:p> in <w:body> "
                f"(anchor={anchor!r}).",
                code=2, error_type="LastParagraphCannotBeDeleted",
                details={"anchor": anchor},
            )
    parent.remove(p)
    if etree.QName(parent).localname == "tc":
        remaining_p = [c for c in parent if etree.QName(c).localname == "p"]
        if not remaining_p:
            parent.append(etree.Element(qn("w:p")))


def _do_delete_paragraph(
    tree_root: Path,
    anchor: str,
    *,
    anchor_all: bool,
    scope: "set[str] | None" = None,
) -> int:
    """Walk parts; remove every (or first) <w:p> containing `anchor`.

    Returns paragraph-deletion count. Snapshot prevents iterator
    invalidation when --all is set.

    `scope` (docx-6.7): if not None, restrict parts to the given role
    subset (see `_iter_searchable_parts`).
    """
    deleted = 0
    for part_path, part_root in _iter_searchable_parts(tree_root, scope=scope):
        matches = _find_paragraphs_containing_anchor(part_root, anchor)
        if not matches:
            continue
        for matched_p in matches:  # snapshot — safe to mutate tree
            _safe_remove_paragraph(matched_p, part_root, anchor=anchor)
            deleted += 1
            if not anchor_all:
                with part_path.open("wb") as f:
                    f.write(etree.tostring(
                        part_root, xml_declaration=True,
                        encoding="UTF-8", standalone=True,
                    ))
                return deleted
        with part_path.open("wb") as f:
            f.write(etree.tostring(
                part_root, xml_declaration=True,
                encoding="UTF-8", standalone=True,
            ))
    return deleted

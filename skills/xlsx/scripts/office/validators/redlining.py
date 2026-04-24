"""Compare a tracked-changes .docx against its original.

Plain `DocxValidator` checks structure (are tracked-change elements
well-formed?). This validator goes further: given BOTH the original
document and the edited/tracked version, it reports whether every
text change between them is properly wrapped in `<w:ins>` or `<w:del>`.

Coverage
--------
Scans the main body, headers, and footers. Text boxes (content nested
inside `<w:drawing>/<wp:txbxContent>`) are compared ONCE — the outer
placeholder paragraph is skipped to avoid double-counting edits made
inside a drawing.

Typical failure modes caught:

1. **Unmarked deletions.** Editor removed text without Track Changes
   enabled — the edited file has less text than the original, but no
   `<w:del>` marker records the removal.
2. **Unmarked insertions.** Editor added text without Track Changes —
   new text appears in the edited file but no `<w:ins>` wraps it.
3. **Unmarked rewrites.** Text changed in place; neither the deletion
   of old text nor the insertion of new text is marked.
4. **Unmarked moves** (heuristic). When a deletion and insertion of
   identical text appear at different paragraph positions, the pair is
   collapsed into a single "unmarked move" finding instead of reporting
   two unrelated errors — cuts noise on reordered documents.
5. **False-positive marks.** A `<w:del>` wraps text that is still
   present in the original at the same position (author "deleted"
   something that was never there) — usually means someone copy-pasted
   a pre-marked chunk into a different document.
6. **Author-attribution gaps.** Some `<w:ins>`/`<w:del>` have no
   `w:author` set.

The validator does NOT attempt to diff formatting (bold/italic/colour
changes); ECMA-376's `<w:rPrChange>` / `<w:pPrChange>` are acknowledged
but not compared — a later enhancement if needed.

Public API:
    RedliningValidator(schemas_dir=None, strict=False)
        .compare(original_path, edited_path) -> ValidationReport
"""

from __future__ import annotations

import difflib
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree  # type: ignore

from .base import BaseSchemaValidator, ValidationReport, _safe_parser


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{W_NS}}}"

# Whitespace normalisation for comparison. Paragraphs rendered identically
# but with different internal spacing should still compare equal; we
# collapse runs of whitespace and strip ends before matching.
_WS_RE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


@dataclass
class ExtractedParagraph:
    """One paragraph's text reconstructed as two ordered strings:
    what it looked like BEFORE edits and AFTER edits.

    Both strings are built by walking the paragraph's runs in document
    order so relative ordering of plain / deleted / inserted fragments
    is preserved.
    """
    original: str
    edited: str
    has_insertions: bool
    has_deletions: bool
    authors: set[str]

    def as_original(self) -> str:
        return _normalise(self.original)

    def as_edited(self) -> str:
        return _normalise(self.edited)


def _has_drawing_ancestor(p: etree._Element) -> bool:
    """True if `p` is nested inside a `<w:drawing>` / `<wp:txbxContent>`.

    `root.iter(w:p)` is a recursive walk and picks up paragraphs from
    inside text boxes / SmartArt callouts / chart captions. Those
    paragraphs are already visited when walking the outer body
    paragraph that contains the drawing, so we skip the nested copies
    here to avoid double-counting text-box content.
    """
    cur = p.getparent()
    while cur is not None:
        # `w:drawing` wraps every inline/anchored shape; its descendants
        # include `wp:txbxContent` (text boxes) whose children are
        # `w:p`. Anything below `w:drawing` is a nested paragraph.
        if cur.tag == f"{_W}drawing":
            return True
        # Fallback: any wordprocessingDrawing namespace element.
        if isinstance(cur.tag, str) and cur.tag.endswith("}drawing"):
            return True
        cur = cur.getparent()
    return False


def _extract_from_xml(xml_bytes: bytes) -> list[ExtractedParagraph]:
    """Parse any WordprocessingML part (body, header, footer) and
    reconstruct original/edited text per paragraph, preserving run
    order. Paragraphs inside `<w:drawing>` are skipped (counted once
    via their outer container)."""
    root = etree.fromstring(xml_bytes, _safe_parser())
    result: list[ExtractedParagraph] = []

    for p in root.iter(f"{_W}p"):
        if _has_drawing_ancestor(p):
            continue

        orig_parts: list[str] = []
        edit_parts: list[str] = []
        has_ins = False
        has_del = False
        authors: set[str] = set()

        for el in p.iter():
            if el.tag in (f"{_W}ins", f"{_W}del"):
                if el.tag == f"{_W}ins":
                    has_ins = True
                else:
                    has_del = True
                author = el.get(f"{_W}author")
                if author:
                    authors.add(author)
                continue

            if el.tag not in (f"{_W}t", f"{_W}delText"):
                continue
            text = el.text or ""
            state = _ancestor_state(el)

            if el.tag == f"{_W}t":
                if state == "ins":
                    edit_parts.append(text)
                elif state == "del":
                    orig_parts.append(text)
                elif state == "both":
                    # Inserted-then-deleted: appears in neither view.
                    continue
                else:
                    orig_parts.append(text)
                    edit_parts.append(text)
            else:
                # <w:delText>: canonical deletion container — original only.
                orig_parts.append(text)

        result.append(ExtractedParagraph(
            original="".join(orig_parts),
            edited="".join(edit_parts),
            has_insertions=has_ins,
            has_deletions=has_del,
            authors=authors,
        ))
    return result


def _ancestor_state(elem: etree._Element) -> str:
    """Walk up the parent chain, return 'ins', 'del', 'both', or 'none'."""
    in_ins = False
    in_del = False
    cur = elem.getparent()
    while cur is not None:
        if cur.tag == f"{_W}ins":
            in_ins = True
        elif cur.tag == f"{_W}del":
            in_del = True
        cur = cur.getparent()
    if in_ins and in_del:
        return "both"
    if in_ins:
        return "ins"
    if in_del:
        return "del"
    return "none"


# Parts whose tracked changes we also compare, not just the main body.
# ECMA-376 Part 1 allows header/footer/endnote/footnote parts to carry
# <w:ins>/<w:del>. Editors who forget Track Changes tend to do it
# everywhere, not only in the body.
_COMPARABLE_PARTS_RE = re.compile(
    r"^word/(document|header\d*|footer\d*|endnotes|footnotes)\.xml$"
)


def _extract_from_docx(path: Path) -> list[ExtractedParagraph]:
    """Concatenate paragraphs from body + headers + footers + notes
    in a deterministic order so the two documents compare apples-to-
    apples. Each part contributes its paragraphs back-to-back; the
    comparison diff treats part boundaries like any other paragraph
    boundary (a line break in the reconstructed string).
    """
    paragraphs: list[ExtractedParagraph] = []
    with zipfile.ZipFile(str(path)) as z:
        names = sorted(n for n in z.namelist() if _COMPARABLE_PARTS_RE.match(n))
        if "word/document.xml" not in names:
            raise ValueError(f"{path} is not a .docx (no word/document.xml)")
        # Always put document.xml first for stable diff alignment; keep
        # the remaining parts in sorted order.
        names = ["word/document.xml"] + [n for n in names if n != "word/document.xml"]
        for name in names:
            try:
                paragraphs.extend(_extract_from_xml(z.read(name)))
            except etree.XMLSyntaxError:
                continue
    return paragraphs


class RedliningValidator(BaseSchemaValidator):
    """Validates tracked-change coverage between two .docx files."""

    expected_parts = ("word/document.xml",)

    def compare(self, original_path: Path, edited_path: Path) -> ValidationReport:
        report = ValidationReport()

        if not original_path.is_file():
            report.errors.append(f"Original not found: {original_path}")
            return report
        if not edited_path.is_file():
            report.errors.append(f"Edited not found: {edited_path}")
            return report

        try:
            orig_paragraphs = _extract_from_docx(original_path)
            edit_paragraphs = _extract_from_docx(edited_path)
        except Exception as exc:
            report.errors.append(f"Parse failure: {exc}")
            return report

        orig_text = "\n".join(p.as_original() for p in orig_paragraphs)
        reconstructed = "\n".join(p.as_original() for p in edit_paragraphs)

        if orig_text != reconstructed:
            self._report_unmarked_differences(orig_text, reconstructed, report)

        # False-positive deletion detection.
        orig_bag = {p.as_original() for p in orig_paragraphs}
        for i, p in enumerate(edit_paragraphs, start=1):
            if not p.has_deletions:
                continue
            deleted_only = _normalise(
                "".join(ch for ch in p.original if ch) if p.original != p.edited else ""
            )
            if not deleted_only:
                continue
            if not any(deleted_only in par or par in deleted_only for par in orig_bag):
                report.warnings.append(
                    f"Edited paragraph {i}: <w:del> content not present in original "
                    f"(possible false-positive mark): {deleted_only[:80]!r}"
                )

        # Author coverage across the whole edited document — body, headers, footers.
        missing_author = 0
        all_authors: set[str] = set()
        with zipfile.ZipFile(str(edited_path)) as z:
            for name in z.namelist():
                if not _COMPARABLE_PARTS_RE.match(name):
                    continue
                try:
                    doc = etree.fromstring(z.read(name), _safe_parser())
                except etree.XMLSyntaxError:
                    continue
                for el in doc.iter():
                    if el.tag in (f"{_W}ins", f"{_W}del"):
                        author = el.get(f"{_W}author")
                        if not author or not author.strip():
                            missing_author += 1
                        else:
                            all_authors.add(author)
        if missing_author:
            report.warnings.append(
                f"{missing_author} tracked-change element(s) have no w:author attribute"
            )
        if not all_authors and any(p.has_insertions or p.has_deletions for p in edit_paragraphs):
            report.warnings.append(
                "Tracked changes are present but no distinct authors recorded"
            )

        return report

    def _report_unmarked_differences(
        self,
        orig_text: str,
        reconstructed: str,
        report: ValidationReport,
    ) -> None:
        """Diff reconstructed-original against actual original. Every
        non-equal chunk is an edit that happened without a
        Track-Changes marker. Delete+insert pairs with identical
        content are collapsed into a single 'unmarked move' finding.
        """
        orig_lines = orig_text.split("\n")
        recon_lines = reconstructed.split("\n")

        matcher = difflib.SequenceMatcher(a=orig_lines, b=recon_lines, autojunk=False)
        opcodes = list(matcher.get_opcodes())

        # Collect deletions and insertions separately so we can pair
        # identical-content chunks as "move" before emitting errors.
        deletions: list[tuple[int, str]] = []   # (orig_start_para, text)
        insertions: list[tuple[int, str]] = []  # (new_start_para, text)
        replaces: list[tuple[int, str, str]] = []

        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "equal":
                continue
            orig_chunk = " | ".join(orig_lines[i1:i2])
            edit_chunk = " | ".join(recon_lines[j1:j2])
            if tag == "delete":
                deletions.append((i1, orig_chunk))
            elif tag == "insert":
                insertions.append((j1, edit_chunk))
            else:
                replaces.append((i1, orig_chunk, edit_chunk))

        # Pair deletions and insertions with identical content => "move".
        moved_orig: set[int] = set()
        moved_edit: set[int] = set()
        moves: list[tuple[int, int, str]] = []
        for d_idx, (d_pos, d_text) in enumerate(deletions):
            for i_idx, (i_pos, i_text) in enumerate(insertions):
                if i_idx in moved_edit or d_idx in moved_orig:
                    continue
                if _normalise(d_text) == _normalise(i_text) and _normalise(d_text):
                    moves.append((d_pos, i_pos, d_text))
                    moved_orig.add(d_idx)
                    moved_edit.add(i_idx)
                    break

        for d_pos, i_pos, text in moves:
            report.errors.append(
                f"Unmarked move: content moved from paragraph {d_pos + 1} to "
                f"paragraph {i_pos + 1} without a tracked-change marker: "
                f"{text[:120]!r}"
            )
        for idx, (d_pos, d_text) in enumerate(deletions):
            if idx in moved_orig:
                continue
            report.errors.append(
                f"Unmarked deletion around paragraph {d_pos + 1}: "
                f"text present in original missing from edited (no <w:del>): "
                f"{d_text[:160]!r}"
            )
        for idx, (i_pos, i_text) in enumerate(insertions):
            if idx in moved_edit:
                continue
            report.errors.append(
                f"Unmarked insertion around paragraph {i_pos + 1}: "
                f"text present in edited absent from original (no <w:ins>): "
                f"{i_text[:160]!r}"
            )
        for i_pos, orig_chunk, edit_chunk in replaces:
            report.errors.append(
                f"Unmarked rewrite around paragraph {i_pos + 1}: "
                f"original={orig_chunk[:80]!r} vs edited={edit_chunk[:80]!r}"
            )


# Back-compat re-export so callers that used _extract_from_document
# continue to work.
_extract_from_document = _extract_from_xml

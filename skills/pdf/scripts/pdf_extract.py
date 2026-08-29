#!/usr/bin/env python3
"""Dump a PDF's per-page text and tables to structured JSON (NOT a Markdown converter).

`pdf_extract.py` produces a structured, machine-readable **dump** of a PDF:
per-page extracted text, extracted tables, and scan-detection flags. It is
deliberately NOT a Markdown converter and never emits Markdown — final Markdown
composition (heading levels, reading order, stitching a table split across
pages, describing diagrams) is LLM judgement and stays the caller's job. See
``references/pdf-to-markdown.md`` for the decision tree and recipe.

Its defining feature is **scan detection**: ``pdfplumber`` returns empty text
on an image-only (scanned) page *without raising* — this tool turns that silent
failure into a loud signal. A whole-document scan exits ``10`` and points at
OCR / the Read tool.

Scan-detection threshold: a page is ``scanned`` when its stripped extractable
character count is at or below ``_SCANNED_CHAR_THRESHOLD`` (10) AND it carries
an image. The threshold is 10 rather than 0 to tolerate the occasional
digitally-stamped page/Bates number on an otherwise image-only page; a digital
page with genuine content essentially always exceeds 10 stripped characters,
and the dual ``has_images`` condition prevents a sparse digital page from being
misread as scanned. A genuinely image-only page has no character objects at
all, so it scores 0 under both default and ``--layout`` extraction — the
classification is stable across modes. ``doc_scanned`` is true only when at
least one page is ``scanned`` AND no page yields meaningful text; a document
with zero scanned pages (including an all-blank PDF) is never ``doc_scanned``.

Figure-page detection (v1.2): the ``scanned`` predicate above is an
*absolute* char threshold, so a page whose whole content is one diagram is
missed as soon as it carries a running header (a confidentiality stamp plus a
page number is 30-70 characters — comfortably over 10). That page reaches the
caller as an ordinary text page and the diagram disappears silently. A second,
independent per-page signal covers it: ``figure_dominant`` is true when the
page's painted area — rasters (``image_coverage``) plus clustered vector
artwork (``vector_coverage``) — reaches ``_FIGURE_COVERAGE_THRESHOLD`` (0.25)
AND its stripped char count is below ``_FIGURE_CHAR_THRESHOLD`` (200). Both
conjuncts are load-bearing: area alone misses a *vector* figure's page only if
vector paint is ignored (hence the sum), and dropping the char cap makes table
ruling — which clusters into 42-85 % of a page — fire on most pages of a
healthy document. ``figure_dominant`` and ``scanned`` are disjoint by
construction (a ``scanned`` page is never ``figure_dominant``): they name the
same loss with different repairs — OCR for a scan, image extraction or a visual
read for a figure. ``figure_dominant`` is reported per page and summarised in
top-level ``figure_pages`` with an stderr warning; it deliberately does NOT
feed ``doc_scanned`` and does NOT change the exit code, because exit ``10``
means "the whole document is a scan" and that contract is public.

Lossy-text-layer detection (v1.2): a producer that embeds no fonts and writes
in an alphabet its single-byte Latin encoding cannot express drops those
characters *when the file is written* — the content stream holds spaces where
the words were. Extraction then returns a plausible-looking Latin skeleton
(headings without words, empty ToC entries) at exit 0, or, when the producer
substitutes a placeholder glyph, plausible-looking garbage (``nnnnnn 1.
nnnnn``) that no text-shape statistic can distinguish from prose. The detector
is therefore built on *font metadata*, not on the extracted text: the dump
carries a document-level ``fonts`` list (``name`` / ``subtype`` / ``embedded``
/ ``encoding`` / ``has_tounicode``), and ``text_layer_lossy`` is true when the
document yields some text AND no font is embedded AND no font carries
``/ToUnicode`` AND every font's encoding is a single-byte Latin one. Such a
document physically cannot carry non-Latin text — the verdict is deterministic,
with no threshold. This is data loss *inside the PDF*, not an extraction
defect: the glyphs were never drawn, so OCR cannot recover them either; the
repair is re-exporting the source with embedded fonts. Exit code unchanged
(stderr warning only) for the same public-contract reason as above.

Word/line grouping knobs (v1.2): ``--y-tolerance`` and ``--table-strategy``
expose the two pdfplumber defaults that misread real documents. pdfplumber's
``y_tolerance`` is *absolute* (3 pt), so a list marker set in a smaller point
size than its body text (7 pt marker against 10-12 pt text puts the marker's
box top ~3-4 pt lower) is read as its own line and sorted *after* the line it
belongs to — the Y-axis twin of the X-axis gluing that ``x_tolerance_ratio``
already fixes. A ratio cannot fix it (the ratio scales off the marker's own
small size), so the knob is absolute. Separately, the default ``lines`` table
strategy builds table edges from *every* ``page.rects`` entry including
``fill=True, stroke=False`` background shading, so zebra-striped paragraphs
become a phantom table and a shaded paragraph under a real table is glued on as
an extra row; ``--table-strategy lines_strict`` counts only stroked lines. Both
keep pdfplumber's default so no existing dump changes shape without an explicit
flag, and both are echoed at the top level of the dump.

Honest scope (v1):
  - Final Markdown composition is the caller's job — never scripted.
  - OCR is not bundled; scans are detected, not OCR'd.
  - Table detection defaults to pdfplumber's ``lines`` strategy;
    ``--table-strategy lines_strict`` is the only bundled alternative and
    borderless-table tuning (``snap_tolerance`` etc.) is inline-agent work,
    see the reference.
  - Image bytes are not extracted; only ``has_images`` / ``image_coverage``
    are reported — a flagged figure page still needs its image pulled out
    separately before it can go into Markdown.
  - ``vector_coverage`` is a quantised approximation: path objects are painted
    onto a ~4 pt grid and each connected cluster contributes its bounding box,
    so it measures "how much of the sheet the artwork spans", not exact ink.
    Page-sized background fills are excluded (see ``_is_backdrop``), but ruling
    and shading that merely *span* a page still read high — the char-count
    conjunct, not this number, is what keeps such pages unflagged.
  - Font-metadata collection is best-effort. A font dictionary that cannot be
    parsed is skipped, which can only *suppress* ``text_layer_lossy``, never
    raise a false alarm.
  - ``text_layer_lossy`` reports a *capability*, not a proven loss: it says the
    document's fonts cannot represent any non-Latin alphabet. A genuinely
    Latin-only document trips it too, correctly and harmlessly — what was lost
    is unknowable from the file, which is exactly why the signal is needed.
  - Decompression-bomb / adversarial-PDF hardening is not specifically done:
    a pathological PDF can hang (no timeout) as well as crash.
  - ``--password`` is read from argv only (visible in ``ps``).
  - "Encryption never silent" covers PDFs that *require* a password to open. A
    PDF encrypted with only an *owner* password but a blank *user* password is
    readable without a password — it opens normally and is treated as a digital
    PDF (no encryption signal); the content was genuinely extractable.

Word-gap handling (v1.1): pdfplumber's default word splitter uses an *absolute*
``x_tolerance`` (3 pt). Many born-digital PDFs — LaTeX/academic two-column
papers in particular — encode inter-word spacing as **positional gaps rather
than space glyphs**, and those gaps are often smaller than 3 pt, so every word
on the page glues together (``ASurveyonBlockchainInteroperability``). This tool
therefore defaults to a *font-relative* threshold via pdfplumber's
``x_tolerance_ratio`` (``_DEFAULT_X_TOLERANCE_RATIO`` = 0.15 → the split gap
scales with each character's font size). This is byte-identical to the legacy
behaviour on PDFs that use real space glyphs (a space character always splits a
word regardless of tolerance), so it does not regress normal documents. Pass
``--x-tolerance-ratio 0`` to disable it and fall back to the absolute tolerance.

Usage:
    python3 pdf_extract.py INPUT.pdf [-o OUT.json] [--layout]
                           [--password PW] [--x-tolerance-ratio R]
                           [--y-tolerance PT] [--table-strategy S]
                           [--json-errors]

Exit codes:
    0  — success: structured dump emitted (digital, mixed, or all-blank PDF)
    1  — failure: input missing / not a PDF / corrupt / encrypted-without-password
    2  — usage error (argparse)
    6  — SelfOverwriteRefused: the -o output path resolves to the input PDF
    10 — DocumentScanned: whole document is image-only; run OCR or the Read tool
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pdfplumber  # type: ignore
from pdfminer.pdftypes import resolve1  # type: ignore

from _errors import add_json_errors_argument, report_error

# A CLI owns its stderr: with --json-errors a wrapper parses stderr as JSON.
# pdfminer / pypdf log free-text warnings ("invalid pdf header", "EOF marker
# not found") on corrupt input — silence them so only our envelope is emitted.
for _noisy_logger in ("pdfminer", "pypdf"):
    logging.getLogger(_noisy_logger).setLevel(logging.ERROR)

_SCANNED_CHAR_THRESHOLD = 10
# Default word-gap threshold as a fraction of font size (pdfplumber's
# `x_tolerance_ratio`). 0.15 sits comfortably between intra-word letter gaps
# (≈0 em — glyphs abut) and the positional inter-word gap of a no-space-glyph
# PDF (≈0.2–0.3 em), so it separates words that pdfplumber's absolute 3 pt
# tolerance otherwise glues, while leaving real-space PDFs untouched. Empirically
# the sweet spot on academic two-column layouts: 0.10–0.20 split cleanly, ≥0.25
# starts re-gluing. The ONLY site that reads this constant is `extract_pdf`.
_DEFAULT_X_TOLERANCE_RATIO = 0.15

# --- figure-page detection --------------------------------------------------
# A page is `figure_dominant` when painted area (raster + clustered vector)
# reaches _FIGURE_COVERAGE_THRESHOLD *and* stripped text stays under
# _FIGURE_CHAR_THRESHOLD. The measured separating pair on the four documents in
# the defect report: real figure pages sit at 31-61 % coverage with 38-117
# chars, while a screenshot beside live prose sits at 15-23 % with 1459-1943
# chars. The char cap is not cosmetic — table ruling clusters into 42-85 % of a
# page, so without it the signal fires on 24 of 29 pages of a healthy document.
# The ONLY site that reads either constant is `_classify_figure_page`.
_FIGURE_COVERAGE_THRESHOLD = 0.25
_FIGURE_CHAR_THRESHOLD = 200
# `vector_coverage` grid: path objects are painted onto cells this many points
# across, connected clusters (8-connectivity) are found, and each cluster's
# bounding box counts toward the covered area. 4 pt is fine enough to keep two
# separate drawings apart and coarse enough that a table's ruling lines join
# into the single region a reader sees. _VECTOR_GRID_MAX_CELLS caps each axis so
# the scan stays bounded on an oversized page.
_VECTOR_CELL_PT = 4.0
_VECTOR_GRID_MAX_CELLS = 200
# A page-sized *unstroked fill* is a background wash, not artwork. Several
# producers (Google Docs Renderer among them) paint one on every page; counting
# it saturates `vector_coverage` to 1.0 on pages that hold nothing but prose,
# which is the same mistake the `lines` table strategy makes when it builds
# table edges out of background shading. Anything at or above this fraction of
# the sheet that is filled and NOT stroked is excluded from the measurement.
# The ONLY site that reads this constant is `_is_backdrop`.
_VECTOR_BACKDROP_RATIO = 0.9

# --- lossy-text-layer detection ---------------------------------------------
# Single-byte encodings whose code space is Latin: a font using one cannot
# address a Cyrillic/Greek/CJK codepoint at all.
_LATIN_SINGLE_BYTE_ENCODINGS = frozenset({
    "StandardEncoding", "WinAnsiEncoding", "MacRomanEncoding",
    "MacExpertEncoding", "PDFDocEncoding",
})
# Simple (single-byte) font subtypes. Type0 is composite — it can address a
# multi-byte code space — so it never counts as Latin-only.
_SIMPLE_FONT_SUBTYPES = frozenset({"Type1", "MMType1", "TrueType", "Type3"})
# FontDescriptor keys that prove the glyph program travels inside the PDF.
_EMBEDDED_FONT_KEYS = ("FontFile", "FontFile2", "FontFile3")
# Depth cap for the Form-XObject resource recursion (fonts can nest).
_MAX_RESOURCE_DEPTH = 8

_TABLE_STRATEGIES = ("lines", "lines_strict")
_DEFAULT_TABLE_STRATEGY = "lines"

_EXIT_OK = 0
_EXIT_FAIL = 1
_EXIT_USAGE = 2
_EXIT_SELF_OVERWRITE = 6  # cross-7 parity: -o path == input path
_EXIT_SCANNED = 10


class _ExtractError(Exception):
    """Domain failure inside the extraction core. `error_type` becomes the
    `--json-errors` envelope `type`; `main` maps it to exit code 1."""

    def __init__(self, message: str, *, error_type: str) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argparse CLI. REAL from the stub phase — the smoke test
    asserts the `--help` surface."""
    parser = argparse.ArgumentParser(
        prog="pdf_extract.py",
        description=(
            "Dump a PDF's per-page text and tables to structured JSON. "
            "This is a structured dump, NOT a Markdown converter — it never "
            "emits Markdown. Final Markdown composition is the caller's job; "
            "see references/pdf-to-markdown.md."
        ),
        epilog=(
            "Exit codes: 0 success; 1 failure (missing/not-a-PDF/corrupt/"
            "encrypted-without-password); 2 usage error; 6 SelfOverwriteRefused "
            "(-o path is the input PDF); 10 DocumentScanned (whole document is "
            "image-only — run OCR or the Read tool)."
        ),
    )
    parser.add_argument("INPUT", type=Path, help="Source PDF file.")
    parser.add_argument(
        "-o", "--output", type=Path, default=None, metavar="OUT.json",
        help="Write the JSON dump to this file (overwritten). Default: stdout.",
    )
    parser.add_argument(
        "--layout", action="store_true",
        help="Use extract_text(layout=True) — preserves column separation as "
             "whitespace (does not reflow columns into reading order).",
    )
    parser.add_argument(
        "--password", default=None, metavar="PW",
        help="Password for an encrypted PDF. NOTE: argv is visible in process "
             "listings (ps) — intended for local-CLI use.",
    )
    parser.add_argument(
        "--x-tolerance-ratio", type=float,
        default=_DEFAULT_X_TOLERANCE_RATIO, metavar="R",
        help="Word-split gap as a fraction of font size (default %(default)s). "
             "pdfplumber's absolute tolerance glues words on PDFs that position "
             "inter-word spacing instead of emitting space glyphs (LaTeX / "
             "academic two-column papers, e.g. 'ASurveyonBlockchain'); a "
             "font-relative ratio fixes that without regressing real-space "
             "PDFs. Pass 0 (or a negative value) to disable and fall back to "
             "pdfplumber's absolute x_tolerance.",
    )
    parser.add_argument(
        "--y-tolerance", type=float, default=None, metavar="PT",
        help="Absolute vertical tolerance in points for grouping characters "
             "into a line (default: pdfplumber's 3). Raise it (5 is the "
             "measured value) when a list marker set in a smaller point size "
             "than its body text is split onto its own line and sorted AFTER "
             "the line it belongs to. Too high a value merges adjacent lines "
             "on a dense layout — raise it deliberately, not by default.",
    )
    parser.add_argument(
        "--table-strategy", choices=_TABLE_STRATEGIES,
        default=_DEFAULT_TABLE_STRATEGY, metavar="S",
        help="Table edge strategy: %(choices)s (default %(default)s). "
             "'lines' is pdfplumber's default and builds edges from every "
             "rectangle including fill-only background shading, so zebra "
             "striping becomes a phantom table and a shaded paragraph can be "
             "glued onto a real table as an extra row. 'lines_strict' counts "
             "only stroked lines — use it on a page whose 'tables' look like "
             "shading, but note it drops tables drawn purely with fills.",
    )
    add_json_errors_argument(parser)
    return parser


def _pdf_name(value) -> str | None:
    """A PDF name object (``/WinAnsiEncoding``) → a plain `str` without the
    slash. Returns `None` for anything that is not a name-like scalar, so every
    caller can treat "absent" and "not a name" identically."""
    value = resolve1(value)
    if value is None:
        return None
    name = getattr(value, "name", value)  # pdfminer wraps names in PSLiteral
    if isinstance(name, bytes):
        name = name.decode("latin-1", "replace")
    if not isinstance(name, str):
        return None
    return name.lstrip("/") or None


def _as_dict(obj) -> dict | None:
    """Resolved PDF object → its dictionary, or `None`. A `PDFStream` (a Form
    XObject, say) carries its dictionary on `.attrs` rather than being one."""
    attrs = getattr(obj, "attrs", None)
    if isinstance(attrs, dict):
        return attrs
    return obj if isinstance(obj, dict) else None


def _encoding_label(encoding) -> str | None:
    """Font `/Encoding` → a short label for the dump, or `None` when absent
    (the font then uses its built-in encoding).

    A dictionary encoding is reported as its `BaseEncoding` plus the marker
    ``Differences`` when it remaps code points. That marker is load-bearing:
    a `/Differences` array can name non-Latin glyphs (``/afii10017``), which
    pdfminer maps back to Unicode — such a font is NOT Latin-only and must not
    count toward `text_layer_lossy`."""
    encoding = resolve1(encoding)
    if encoding is None:
        return None
    as_dict = _as_dict(encoding)
    if as_dict is not None:
        parts = []
        base = _pdf_name(as_dict.get("BaseEncoding"))
        if base:
            parts.append(base)
        differences = resolve1(as_dict.get("Differences"))
        if isinstance(differences, list) and differences:
            parts.append("Differences")
        return "+".join(parts) if parts else "dict"
    return _pdf_name(encoding)


def _font_descriptor(font: dict) -> dict | None:
    """The `/FontDescriptor` of a font, following a composite (Type0) font
    through its first descendant — that is where a Type0's descriptor, and
    therefore its embedded font file, actually lives."""
    descriptor = _as_dict(resolve1(font.get("FontDescriptor")))
    if descriptor is not None:
        return descriptor
    descendants = resolve1(font.get("DescendantFonts"))
    if isinstance(descendants, list) and descendants:
        first = _as_dict(resolve1(descendants[0]))
        if first is not None:
            return _as_dict(resolve1(first.get("FontDescriptor")))
    return None


def _font_record(font: dict) -> dict:
    """One font dictionary → the five-field record carried in the dump's
    document-level `fonts` list.

    `embedded` is true when the glyph program travels inside the PDF: a
    descriptor holding `FontFile`/`FontFile2`/`FontFile3`, or a Type3 font,
    whose glyphs *are* content streams in the file."""
    subtype = _pdf_name(font.get("Subtype"))
    descriptor = _font_descriptor(font)
    embedded = bool(
        (descriptor is not None
         and any(key in descriptor for key in _EMBEDDED_FONT_KEYS))
        or (subtype == "Type3" and "CharProcs" in font)
    )
    return {
        "name": _pdf_name(font.get("BaseFont")) or _pdf_name(font.get("Name")),
        "subtype": subtype,
        "embedded": embedded,
        "encoding": _encoding_label(font.get("Encoding")),
        "has_tounicode": "ToUnicode" in font,
    }


def _font_key(record: dict) -> tuple:
    """Identity of a font record for deduplication + deterministic ordering.
    The same font resource is referenced from every page that uses it; the dump
    lists each distinct font once, sorted."""
    return (record["name"] or "", record["subtype"] or "",
            record["embedded"], record["encoding"] or "",
            record["has_tounicode"])


def _walk_font_resources(resources, acc: dict, seen: set, depth: int) -> None:
    """Collect font records from a resource dictionary into `acc`, recursing
    into Form XObjects (a font used only inside one would otherwise be missed).

    `seen` holds visited indirect-object ids, which both avoids re-parsing a
    shared resource and makes a cyclic XObject reference terminate; `depth` is
    the belt-and-braces cap (`_MAX_RESOURCE_DEPTH`) for a cycle built entirely
    from direct objects, which carry no id to remember."""
    if depth > _MAX_RESOURCE_DEPTH:
        return
    resolved = _as_dict(resolve1(resources))
    if resolved is None:
        return

    fonts = _as_dict(resolve1(resolved.get("Font")))
    if fonts:
        for ref in fonts.values():
            objid = getattr(ref, "objid", None)
            if objid is not None:
                if ("font", objid) in seen:
                    continue
                seen.add(("font", objid))
            font = _as_dict(resolve1(ref))
            if font is not None:
                record = _font_record(font)
                acc.setdefault(_font_key(record), record)

    xobjects = _as_dict(resolve1(resolved.get("XObject")))
    if xobjects:
        for ref in xobjects.values():
            objid = getattr(ref, "objid", None)
            if objid is not None:
                if ("xobject", objid) in seen:
                    continue
                seen.add(("xobject", objid))
            xobject = _as_dict(resolve1(ref))
            if xobject is not None and "Resources" in xobject:
                _walk_font_resources(
                    xobject["Resources"], acc, seen, depth + 1)


def _collect_page_fonts(page, acc: dict, seen: set) -> None:
    """Best-effort font harvest for one page (see the module docstring's honest
    scope). A malformed font dictionary must never fail an extraction that
    would otherwise succeed, and losing a record can only *suppress*
    `text_layer_lossy` — the safe direction, since the flag is an alarm."""
    try:
        _walk_font_resources(page.page_obj.resources, acc, seen, 0)
    except Exception:  # noqa: BLE001 — diagnostic metadata, never fatal
        return


def _is_latin_single_byte(subtype: str | None, encoding: str | None) -> bool:
    """True when a font's code space is single-byte AND Latin — i.e. the font
    cannot address a Cyrillic/Greek/CJK code point at all.

    A composite (Type0) font is multi-byte, so never. A `/Differences` array may
    name non-Latin glyphs, so never. An absent `/Encoding` on a simple font
    means its built-in encoding, which for the non-embedded base-14 faces this
    predicate exists to catch is Latin (or symbolic — equally unable to carry
    another alphabet)."""
    if subtype not in _SIMPLE_FONT_SUBTYPES:
        return False
    if encoding is None:
        return True
    if "Differences" in encoding:
        return False
    return encoding in _LATIN_SINGLE_BYTE_ENCODINGS


def _classify_text_layer(fonts: list[dict], has_text: bool) -> bool:
    """Document-level `text_layer_lossy` verdict — deterministic, no thresholds.

    True when the document yields *some* text AND not one font is embedded AND
    not one carries `/ToUnicode` AND every font is Latin single-byte. Under
    those conditions the file physically cannot hold non-Latin text: if the
    source had any, the producer dropped it while writing the file, and it is
    unrecoverable from the text layer (and from OCR — the glyphs were never
    drawn). An empty `fonts` list yields False: nothing was measured, so
    nothing is claimed. The ONLY site that reads `_is_latin_single_byte`."""
    if not fonts or not has_text:
        return False
    if any(f["embedded"] or f["has_tounicode"] for f in fonts):
        return False
    return all(
        _is_latin_single_byte(f["subtype"], f["encoding"]) for f in fonts)


def _obj_box(obj: dict) -> tuple[float, float, float, float]:
    """A pdfplumber object dict → `(x0, top, x1, bottom)` as floats."""
    return (float(obj["x0"]), float(obj["top"]),
            float(obj["x1"]), float(obj["bottom"]))


def _image_coverage(images, width: float, height: float) -> float:
    """Fraction of the sheet covered by raster images — Σ(bbox area) / page
    area, clamped to 1.0 because overlapping images would otherwise sum past
    the page."""
    page_area = width * height
    if page_area <= 0:
        return 0.0
    total = 0.0
    for image in images:
        x0, top, x1, bottom = _obj_box(image)
        total += abs(x1 - x0) * abs(bottom - top)
    return min(1.0, total / page_area)


def _is_backdrop(obj: dict, page_area: float) -> bool:
    """True for a page-sized unstroked fill — a background wash rather than
    artwork. Excluding it is what keeps `vector_coverage` from reading 1.0 on a
    page of plain prose. The ONLY site that reads `_VECTOR_BACKDROP_RATIO`."""
    if obj.get("stroke") or not obj.get("fill"):
        return False
    x0, top, x1, bottom = _obj_box(obj)
    return abs(x1 - x0) * abs(bottom - top) >= _VECTOR_BACKDROP_RATIO * page_area


def _vector_coverage(objects, width: float, height: float) -> float:
    """Fraction of the sheet spanned by clustered vector artwork.

    Summing path bounding boxes directly is useless — a ruling line's box has
    ~zero area, yet a table of them plainly occupies a region of the page. So
    the paths are painted onto a `_VECTOR_CELL_PT` grid, connected clusters are
    found (8-connectivity, so a diagonal or dashed stroke still joins), and each
    cluster contributes its bounding box. That answers the question the figure
    signal actually asks: how much of the sheet does the artwork span. It is an
    approximation quantised to the cell size, and clusters whose boxes overlap
    double-count, hence the clamp.

    Page-sized background fills are dropped first (`_is_backdrop`) — one such
    rect would otherwise mark every cell and report a prose page as wholly
    artwork."""
    page_area = width * height
    if page_area <= 0 or not objects:
        return 0.0
    objects = [obj for obj in objects if not _is_backdrop(obj, page_area)]
    if not objects:
        return 0.0
    cell = max(_VECTOR_CELL_PT,
               width / _VECTOR_GRID_MAX_CELLS, height / _VECTOR_GRID_MAX_CELLS)
    cols = int(width / cell) + 1
    rows = int(height / cell) + 1
    grid = bytearray(cols * rows)

    for obj in objects:
        x0, top, x1, bottom = _obj_box(obj)
        c0 = min(max(int(min(x0, x1) / cell), 0), cols - 1)
        c1 = min(max(int(max(x0, x1) / cell), 0), cols - 1)
        r0 = min(max(int(min(top, bottom) / cell), 0), rows - 1)
        r1 = min(max(int(max(top, bottom) / cell), 0), rows - 1)
        span = b"\x01" * (c1 - c0 + 1)
        for row in range(r0, r1 + 1):
            base = row * cols
            grid[base + c0:base + c1 + 1] = span

    covered_cells = 0
    for start in range(cols * rows):
        if grid[start] != 1:
            continue
        grid[start] = 2  # 2 == already absorbed into a cluster
        stack = [start]
        min_r = max_r = start // cols
        min_c = max_c = start % cols
        while stack:
            index = stack.pop()
            row, col = divmod(index, cols)
            min_r, max_r = min(min_r, row), max(max_r, row)
            min_c, max_c = min(min_c, col), max(max_c, col)
            for d_row in (-1, 0, 1):
                near_row = row + d_row
                if not 0 <= near_row < rows:
                    continue
                base = near_row * cols
                for d_col in (-1, 0, 1):
                    near_col = col + d_col
                    if not 0 <= near_col < cols:
                        continue
                    neighbour = base + near_col
                    if grid[neighbour] == 1:
                        grid[neighbour] = 2
                        stack.append(neighbour)
        covered_cells += (max_r - min_r + 1) * (max_c - min_c + 1)
    return min(1.0, covered_cells / (cols * rows))


def _classify_figure_page(
    char_count: int, image_coverage: float, vector_coverage: float,
    scanned: bool,
) -> bool:
    """Per-page `figure_dominant` predicate: the sheet is mostly artwork and
    carries too little text to be a text page.

    Disjoint from `scanned` by construction — a scanned page trips the coverage
    test too, but it is already flagged, exits loudly at document level, and
    needs a different repair (OCR, not image extraction). The ONLY site that
    reads `_FIGURE_COVERAGE_THRESHOLD` / `_FIGURE_CHAR_THRESHOLD`."""
    if scanned:
        return False
    covered = min(1.0, image_coverage + vector_coverage)
    return (covered >= _FIGURE_COVERAGE_THRESHOLD
            and char_count < _FIGURE_CHAR_THRESHOLD)


def _classify_page(char_count: int, has_images: bool) -> bool:
    """Per-page scanned predicate (ARCH §4.3): a page is `scanned` when it has
    next-to-no extractable text AND carries an image. The ONLY site that reads
    `_SCANNED_CHAR_THRESHOLD`."""
    return char_count <= _SCANNED_CHAR_THRESHOLD and has_images


def _classify_document(pages: list[dict]) -> tuple[bool, list[int]]:
    """Document-level scan verdict (ARCH §4.3) → `(doc_scanned, scanned_pages)`.

    `doc_scanned` is true iff at least one page is `scanned` AND no page yields
    meaningful text (every page's `char_count` is at/below the threshold). The
    `bool(scanned_pages)` guard means a document with zero scanned pages —
    including an all-blank or empty (0-page) PDF — is never `doc_scanned`, so it
    is never wrongly routed to OCR."""
    scanned_pages = [p["n"] for p in pages if p["scanned"]]
    # `no_meaningful_text` is vacuously True for an empty `pages` list; the
    # `bool(scanned_pages)` conjunct (evaluated first) is what keeps a 0-page or
    # all-blank PDF out of `doc_scanned`. Keep that conjunct first on any edit.
    no_meaningful_text = all(
        p["char_count"] <= _SCANNED_CHAR_THRESHOLD for p in pages
    )
    doc_scanned = bool(scanned_pages) and no_meaningful_text
    return doc_scanned, scanned_pages


def _is_encrypted(pdf_path: Path) -> bool:
    """Probe whether the PDF is encrypted — used ONLY to label an already-failed
    `pdfplumber.open` as `EncryptedPDF` vs `CorruptPdf`. NOT a cheap probe: it
    constructs a full `pypdf.PdfReader` (a second parse of the file). Acceptable
    because it runs solely on the failure path, never on a successful
    extraction."""
    try:
        from pypdf import PdfReader  # type: ignore

        return bool(PdfReader(str(pdf_path)).is_encrypted)
    except Exception:
        return False


def _open_pdf(pdf_path: Path, password: str | None):
    """Open the PDF via pdfplumber and return the `pdfplumber.PDF` object.

    The SOLE caller (`extract_pdf`) owns closing it via a `with` block. A PDF
    that *requires* a password to open never fails silently: pdfplumber raises,
    and the file is reported as `EncryptedPDF` (recoverable with `--password`)
    or `CorruptPdf` — both raise `_ExtractError`, which `main` maps to exit 1.
    (An owner-only-encrypted PDF with a blank user password opens normally — see
    the module docstring's honest-scope note.)"""
    try:
        return pdfplumber.open(str(pdf_path), password=password or "")
    except Exception as exc:
        if _is_encrypted(pdf_path):
            raise _ExtractError(
                f"PDF is encrypted and could not be opened — supply a correct "
                f"--password: {pdf_path}",
                error_type="EncryptedPDF",
            ) from exc
        raise _ExtractError(
            f"Could not open PDF (corrupt or not a PDF): {pdf_path}: {exc}",
            error_type="CorruptPdf",
        ) from exc


def _extract_page(
    page, *, layout: bool,
    x_tolerance_ratio: float | None = _DEFAULT_X_TOLERANCE_RATIO,
    y_tolerance: float | None = None,
    table_strategy: str = _DEFAULT_TABLE_STRATEGY,
) -> dict:
    """Build one PageRecord (ARCH §4.2) from a pdfplumber page.

    `n` is filled by the caller. `char_count` is the *stripped* length of the
    extracted text (whitespace-only page → 0). `tables` is the raw
    `extract_tables()` form (list of row-lists of `str | None`). `scanned` is
    delegated to `_classify_page`, `figure_dominant` to `_classify_figure_page`.

    `x_tolerance_ratio` (font-relative word-split threshold) and `y_tolerance`
    (absolute line-grouping threshold) are applied to BOTH the page text and the
    table-cell text so words and lines are grouped consistently across the dump;
    `None` for either restores pdfplumber's own default. `table_strategy`
    changes table *detection* (which edges count), unlike the two tolerances,
    which only change how characters group into words and lines.

    Every knob is passed only when it is set, so the default configuration
    reaches pdfplumber as an untouched call and cannot drift from the legacy
    output."""
    text_kwargs: dict = {"layout": layout}
    if x_tolerance_ratio is not None:
        text_kwargs["x_tolerance_ratio"] = x_tolerance_ratio
    if y_tolerance is not None:
        text_kwargs["y_tolerance"] = y_tolerance
    text = page.extract_text(**text_kwargs) or ""

    table_settings: dict = {}
    if x_tolerance_ratio is not None:
        table_settings["text_x_tolerance_ratio"] = x_tolerance_ratio
    if y_tolerance is not None:
        table_settings["text_y_tolerance"] = y_tolerance
    if table_strategy != _DEFAULT_TABLE_STRATEGY:
        table_settings["vertical_strategy"] = table_strategy
        table_settings["horizontal_strategy"] = table_strategy
    if table_settings:
        tables = page.extract_tables(table_settings=table_settings)
    else:
        tables = page.extract_tables()

    char_count = len(text.strip())
    has_images = bool(page.images)
    width, height = float(page.width), float(page.height)
    image_coverage = round(_image_coverage(page.images, width, height), 4)
    vector_coverage = round(
        _vector_coverage(
            [*page.lines, *page.rects, *page.curves], width, height), 4)
    scanned = _classify_page(char_count, has_images)
    return {
        "n": 0,
        "text": text,
        "tables": tables,
        "char_count": char_count,
        "has_images": has_images,
        "image_coverage": image_coverage,
        "vector_coverage": vector_coverage,
        "scanned": scanned,
        "figure_dominant": _classify_figure_page(
            char_count, image_coverage, vector_coverage, scanned),
    }


def extract_pdf(
    pdf_path: Path, *, password: str | None, layout: bool,
    x_tolerance_ratio: float | None = _DEFAULT_X_TOLERANCE_RATIO,
    y_tolerance: float | None = None,
    table_strategy: str = _DEFAULT_TABLE_STRATEGY,
) -> dict:
    """Open the PDF, extract every page, classify, return the dump dict
    (ARCH §4.1 `DumpDocument`).

    Owns the pdfplumber handle: once `_open_pdf` returns a handle, the `with`
    block releases the file descriptor on every path, including a page raising
    mid-extraction. (A failure *inside* `_open_pdf`, before a handle exists,
    raises `_ExtractError` directly — no handle to leak here.)

    `x_tolerance_ratio` ≤ 0 (or `None`) is normalised to `None` (legacy
    absolute-tolerance word splitting), and so is `y_tolerance` ≤ 0 (legacy
    absolute 3 pt line grouping); the *effective* values, plus `table_strategy`,
    are echoed back at the top level so the dump is self-describing about how
    words, lines and table edges were derived.

    Font records are harvested during the same page walk — the resource
    dictionaries are only reachable through the open handle — and deduplicated
    into the document-level `fonts` list that `text_layer_lossy` is computed
    from."""
    ratio = x_tolerance_ratio if (
        x_tolerance_ratio and x_tolerance_ratio > 0) else None
    y_tol = y_tolerance if (y_tolerance and y_tolerance > 0) else None
    font_acc: dict[tuple, dict] = {}
    seen_objects: set = set()
    with _open_pdf(pdf_path, password) as pdf:
        pages: list[dict] = []
        for index, page in enumerate(pdf.pages, start=1):
            _collect_page_fonts(page, font_acc, seen_objects)
            record = _extract_page(
                page, layout=layout, x_tolerance_ratio=ratio,
                y_tolerance=y_tol, table_strategy=table_strategy)
            record["n"] = index
            pages.append(record)
    doc_scanned, scanned_pages = _classify_document(pages)
    fonts = [font_acc[key] for key in sorted(font_acc)]
    return {
        "page_count": len(pages),
        "doc_scanned": doc_scanned,
        "scanned_pages": scanned_pages,
        "figure_pages": [p["n"] for p in pages if p["figure_dominant"]],
        "text_layer_lossy": _classify_text_layer(
            fonts, any(p["char_count"] > 0 for p in pages)),
        "x_tolerance_ratio": ratio,
        "y_tolerance": y_tol,
        "table_strategy": table_strategy,
        "fonts": fonts,
        "pages": pages,
    }


def _same_path(a: Path, b: Path) -> bool:
    """True if `a` and `b` resolve to the same filesystem path (symlinks
    followed). `b` need not exist yet — `resolve()` is non-strict."""
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def _emit(dump: dict, out_path: Path | None) -> None:
    """Serialise `dump` as indented JSON straight to the sink (`json.dump`, no
    intermediate full-string copy). `out_path is None` → stdout; otherwise
    overwrite `out_path` (idempotent). stdout always carries the dump — never
    the `--json-errors` envelope, which goes to stderr."""
    if out_path is None:
        json.dump(dump, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        # Auto-create the parent dir (parity with pdf_split.py / preview.py).
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(dump, fh, ensure_ascii=False, indent=2)
            fh.write("\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse → extract → emit → return the exit code.

    Exit codes: 0 success; 1 failure (`InputNotFound` / `EncryptedPDF` /
    `CorruptPdf` / `OutputWriteFailed` / `InternalError`); 2 argparse usage
    error; 6 `SelfOverwriteRefused` (`-o` resolves to the input PDF); 10
    `DocumentScanned` (whole-document scan). On a whole-doc scan the dump is
    still emitted (to stdout or `-o`) — exit 10 + stderr is the loud signal."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    je = args.json_errors

    input_path: Path = args.INPUT
    if not input_path.is_file():
        return report_error(
            f"Input not found: {input_path}",
            code=_EXIT_FAIL, error_type="InputNotFound",
            details={"path": str(input_path)}, json_mode=je,
        )

    # cross-7 parity: refuse to overwrite the input PDF with the JSON dump.
    # `resolve()` also neutralises a symlinked `-o` pointing back at the input.
    if args.output is not None and _same_path(input_path, args.output):
        return report_error(
            f"Refusing to overwrite the input PDF with the JSON dump "
            f"(-o resolves to INPUT): {input_path}",
            code=_EXIT_SELF_OVERWRITE, error_type="SelfOverwriteRefused",
            details={"path": str(input_path)}, json_mode=je,
        )

    try:
        dump = extract_pdf(
            input_path, password=args.password, layout=args.layout,
            x_tolerance_ratio=args.x_tolerance_ratio,
            y_tolerance=args.y_tolerance,
            table_strategy=args.table_strategy)
    except _ExtractError as exc:
        return report_error(
            exc.message, code=_EXIT_FAIL, error_type=exc.error_type,
            details={"path": str(input_path)}, json_mode=je,
        )
    except Exception as exc:  # defensive catch-all — should not fire
        return report_error(
            f"Internal error: {type(exc).__name__}: {exc}",
            code=_EXIT_FAIL, error_type="InternalError", json_mode=je,
        )

    # The dump is written on every successful-extraction path, including a
    # whole-document scan (it has diagnostic value). A failure writing the
    # `-o` file surfaces as a clean envelope, never a raw traceback.
    try:
        _emit(dump, args.output)
    except OSError as exc:
        return report_error(
            f"Could not write output {args.output}: {exc}",
            code=_EXIT_FAIL, error_type="OutputWriteFailed",
            details={"path": str(args.output)}, json_mode=je,
        )

    if dump["doc_scanned"]:
        return report_error(
            f"Document appears scanned / image-only — {dump['page_count']} "
            f"page(s), no extractable text. Run OCR (e.g. ocrmypdf) or render "
            f"the pages as images with the Read tool; see "
            f"references/pdf-to-markdown.md.",
            code=_EXIT_SCANNED, error_type="DocumentScanned",
            details={"page_count": dump["page_count"]}, json_mode=je,
        )
    if dump["scanned_pages"]:
        pages = ", ".join(str(n) for n in dump["scanned_pages"])
        sys.stderr.write(
            f"warning: page(s) {pages} appear scanned / image-only "
            f"(no extractable text); the rest of the document extracted "
            f"normally.\n"
        )
    # Both warnings below leave the exit code at 0 on purpose: exit 10 means
    # "the whole document is a scan", and that contract is public.
    if dump["figure_pages"]:
        pages = ", ".join(str(n) for n in dump["figure_pages"])
        sys.stderr.write(
            f"warning: page(s) {pages} are mostly figure (see per-page "
            f"image_coverage / vector_coverage) with little text — the "
            f"diagram is NOT in this dump. Extract the image or read those "
            f"pages visually before composing Markdown.\n"
        )
    if dump["text_layer_lossy"]:
        sys.stderr.write(
            "warning: no font in this PDF is embedded or carries /ToUnicode, "
            "and every encoding is single-byte Latin — the file cannot "
            "represent a non-Latin alphabet. If the source had non-Latin "
            "text, the producer dropped it while writing the file: it is "
            "absent from the PDF and unrecoverable — OCR cannot bring it back, "
            "because the glyphs were never drawn. Re-export the source with "
            "embedded fonts. (Text inside embedded images is unaffected and "
            "still readable — render the pages to recover it.) See the dump's "
            "`fonts` list.\n"
        )
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

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

Layout hints (v1.4): two pdfplumber defaults misread documents real producers
emit, both have a documented remedy, and dogfooding showed a caller finds that
remedy only by reading the reference — so the dump now says it. Every dump
carries ``layout_hints`` (``orphan_list_markers`` / ``single_column_tables`` /
``tables``), and while the matching knob is still at its default the script
names it on stderr: ``--y-tolerance 5`` for markers a smaller point size pushed
onto their own line, ``--table-strategy lines_strict`` for background shading
read as a table. Advisory in the strict sense — the exit code never moves, and
the counters stay in the dump when the line is suppressed (it is, once the flag
has been passed: repeating advice the caller has taken is noise). Measured on
four real documents: 32 orphaned markers and 23-of-61 one-column tables on one
Google Docs export, silence on the other three. ``single_column_tables`` is a
*floor*, not a phantom census — ``lines_strict`` dropped 45 of those 61 tables,
and the multi-column phantoms among them are indistinguishable from data here —
and it fires on a genuinely ruled one-column table too, which the ``onecol.pdf``
fixture pins deliberately.

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

Image extraction (v1.3): flagging a figure page is only half the repair — the
diagram still has to leave the PDF before it can go into Markdown, and until now
the caller had to hand-write ``pypdf`` for that, choosing a library the skill had
already standardised for text and tables. ``--extract-images DIR`` closes it, and
there are **two classes of artwork, the second of which cannot be ignored**:

* **raster** — an embedded image XObject. The bytes exist in the file and are
  copied out as stored. Placements come from ``pdfplumber`` (which knows *where*
  each image is painted) and the bytes from ``pypdf`` (which knows how to decode
  the filter chain and fold an ``/SMask`` alpha plane into the pixels); the join
  key is the PDF object number. Enumerating pypdf's per-page images *instead*
  would report an image on every page whose resource dictionary mentions it —
  painted or not — and would emit each ``/SMask`` plane as a separate greyscale
  image. Both were measured on the dogfood corpus; the committed fixtures
  `nested.pdf` and `shadowed.pdf` cover the nesting and shadow-key cases.
* **vector** — a diagram or chart drawn with content-stream path operators.
  There is no image object to extract, so the only honest route is to rasterise
  the region: cluster the page's paths (the same ``_vector_clusters`` pass that
  produces ``vector_coverage``), keep the clusters that are figures rather than
  page furniture (``_is_figure_cluster``), and crop each through Poppler
  ``pdftocairo -png -r DPI -x -y -W -H``. Poppler's SVG output would preserve
  the vectors but ignores the crop rectangle and always emits a whole page, so a
  cropped figure is necessarily a raster.

**"Diagram" is not the same question as "vector".** Classification here is by
object model, never by appearance: block diagrams that look plainly vector turn
out, on measurement, to be RGBA PNGs at ~150 dpi with a transparent background
and zero path operators on the page — i.e. anything drawn in Figma/Canva or
pasted as a screenshot is fully served by the raster branch. A heuristic of the
form "this page looks like it has a diagram, so render vectors" fires falsely.

Each page gains an ``images`` list of ``{file, kind, bbox, name, width, height,
bytes, sha1}``, so Markdown composition references paths that exist instead of
guessing them, and the top level gains ``images_dir`` / ``image_dpi`` /
``images_summary``. Without the flag *nothing* changes: no ``images`` key is
emitted at all, which is a different statement from an empty list (``[]`` means
"looked and found none").

Three guards, each measured on a real document rather than imagined:
``sha1`` **dedup** (one document placed a single background raster 31 times
among 49 placements — the naive extractor writes 32 files nobody wants; here
every placement is still reported, they simply share one file), **page-sized
backdrop suppression** (6 of those 49 placements were sheet-sized background,
and a scanned page is a page-sized raster too — already reported by ``scanned``
and exit ``10``, whose repair is OCR, not a figure file), and a **mandatory
destination** — ``DIR`` has no default, so nothing is ever scattered into the
current directory, and a ``DIR`` that resolves to the input PDF is refused with
exit ``6`` exactly as ``-o`` is.

Honest scope (v1):
  - Final Markdown composition is the caller's job — never scripted.
  - OCR is not bundled; scans are detected, not OCR'd.
  - Table detection defaults to pdfplumber's ``lines`` strategy;
    ``--table-strategy lines_strict`` is the only bundled alternative and
    borderless-table tuning (``snap_tolerance`` etc.) is inline-agent work,
    see the reference.
  - Without ``--extract-images``, image bytes are not extracted; only
    ``has_images`` / ``image_coverage`` are reported.
  - A vector figure drawn **entirely with fills** and no stroked path is NOT
    extracted, and the omission is **silent** — no record, no counter, no
    warning, because nothing distinguishes it from the shading the same test
    exists to reject. ``_is_figure_cluster`` requires one stroked path because
    that is the single measurement separating artwork from shading — code-block
    backgrounds, heading rules, inline-code chips and the full-width cards a
    Notion/Confluence export paints behind every block are all fill-only, and
    admitting them turned a 9-page document into 13 spurious figures. A flat
    filled pie chart, a treemap or an unoutlined bar chart pays for that. Do
    **not** assume ``figure_dominant`` catches the page instead: that flag
    needs 25 % painted coverage, and a chart of this kind on an otherwise
    normal text page measures well under it (a 200x200 pt flat-fill pie on a
    letter sheet measures ``vector_coverage`` 0.07), so the page is not
    flagged either and the figure is invisible in the dump. The reliable fallback is rendering the sheet
    with ``preview.py`` and reading it.
  - Vector figure *detection* is a heuristic over the object model and can only
    ever approximate a reader's judgement. It is tuned for precision: a cluster
    it rejects is reported nowhere, so ``--no-vector-images`` and the
    ``figure_dominant`` flag remain the honest fallbacks.
  - Rendering a **whole page** stays ``preview.py``'s job. This extracts cropped
    figures only.
  - A vector crop is a raster (see above). No SVG output is produced.
  - ``pdftocairo`` absent, timing out, or failing on a page degrades to "no
    vector figures, said loudly on stderr and counted in ``images_summary``" —
    never to a silent omission, and never to a failed dump: the text and tables
    are the contract.
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
  - Decompression-bomb / adversarial-PDF hardening is not specifically done for
    the text path: a pathological PDF can hang (no timeout) as well as crash.
    The image path is the one exception, because ``--extract-images`` opens a
    decode that is sized by the stream's *declared* ``/Width`` and ``/Height``
    rather than by its length — a few hundred bytes can demand gigabytes — so
    the enumeration is deliberately decode-free (``_raster_streams`` walks
    ``page.images.keys()``, never ``page.images``, because iterating the latter
    decodes every entry as it goes) and ``_IMAGE_MAX_PIXELS`` refuses the
    allocation before ``_fetch_raster`` is reached. The declaration is read
    from the XObject dictionary rather than from pdfplumber's ``srcsize``,
    which a file can set independently via the ``/W``/``/H`` abbreviations.
    That guards the allocation this feature adds; it does not make the tool
    safe against a hostile PDF generally.
  - A raster pypdf cannot inflate within its own 75 MB ceiling
    (``ZLIB_MAX_OUTPUT_LENGTH``) is reported as ``undecodable`` rather than
    extracted. A legitimate ~25 MP RGB image exceeds that, so a large scan can
    be counted as undecodable even though nothing is wrong with it — loudly,
    never silently, but the file will not be in the directory.
  - ``--password`` is read from argv only (visible in ``ps``), and with
    ``--extract-images`` it is passed on to ``pdftocairo`` as ``-upw``, so it
    is visible in the child process's argv too.
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
                           [--extract-images DIR] [--image-dpi N]
                           [--no-vector-images] [--json-errors]

Exit codes:
    0  — success: structured dump emitted (digital, mixed, or all-blank PDF)
    1  — failure: input missing / not a PDF / corrupt / encrypted-without-password
         / --extract-images names an existing file / its directory is unwritable
    2  — usage error (argparse, including --image-dpi < 1)
    6  — SelfOverwriteRefused: the -o output path, or --extract-images,
         resolves to the input PDF
    10 — DocumentScanned: whole document is image-only; run OCR or the Read tool
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pdfplumber  # type: ignore
from pdfminer.pdftypes import resolve1  # type: ignore

from _errors import add_json_errors_argument, report_error, write_json_stdout

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

# --- image extraction (--extract-images) ------------------------------------
# Rasterisation resolution for a *vector* figure crop. 150 dpi keeps a
# letter-width figure near 1000 px wide — legible when a model reads it back and
# small enough to sit in a Markdown tree. Rasters are never re-rendered (their
# bytes are copied out as stored), so this knob only affects the vector branch.
_DEFAULT_IMAGE_DPI = 150
# A raster whose placement covers this much of the sheet is a background wash or
# a whole-page scan, not a figure. The measured case: one document repeated a
# single page-sized backdrop raster on 31 of its placements. A scanned page is a
# page-sized raster too — and is already reported by `scanned` / exit 10, whose
# repair is OCR, not a figure file. Deliberately a separate constant from
# `_VECTOR_BACKDROP_RATIO`: that one also requires "filled and not stroked",
# which is meaningless for an image XObject. The ONLY site that reads this
# constant is `_is_image_backdrop`.
_IMAGE_BACKDROP_RATIO = 0.9
# --- vector-figure predicates ----
# A cluster of path objects is a *figure* only if it clears all four tests
# below. Measured across 6 documents / ~50 pages (4 real dogfood PDFs from
# `tmp16/` plus the committed `figure.pdf` and `shaded.pdf`): the four genuine
# vector figures score area 0.054-0.311 with 5-29 stroked paths and zero table
# overlap, while every one of the ~30 spurious clusters is either fill-only
# (code-block shading, heading rules, inline-code chips, card backgrounds:
# 0 stroked paths), table ruling (overlap 0.98-1.00), or a speck (area 0.002).
# Both of the first two tests are load-bearing and neither subsumes the other:
# table ruling IS stroked (so only the overlap test rejects it), and a
# full-width shaded card overlaps no table at all (so only the stroke test
# rejects it).
# The overlap threshold sits in an empty measured gap: every genuine figure
# scored 0.00 and every table cluster 0.98-1.00, so anything in (0.0, 0.98)
# separates them. It is set near the TOP of that gap deliberately, because the
# error it guards against is asymmetric — a chart whose bars and axes partly
# read as a lattice would be silently dropped by a low threshold, while raising
# it costs nothing on the corpus (verified: 9/9 documents unchanged at 0.9).
# The ONLY site that reads these three is `_is_figure_cluster`.
_FIGURE_MIN_AREA_RATIO = 0.01
_FIGURE_MIN_SIDE_PT = 24.0
_FIGURE_TABLE_OVERLAP = 0.9
# Padding added around a cluster before it is cropped. A path's bounding box is
# its *centreline* box, so half a stroke width bleeds outside it (measured at
# 1.3-1.6 pt on a 3 pt stroke), and the cluster bbox is quantised to
# `_VECTOR_CELL_PT`. 4 pt covers both without pulling in neighbouring prose.
_FIGURE_PAD_PT = 4.0
# Per-page ceiling on rendered vector figures. A pathological page (a map, a
# CAD drawing) can cluster into hundreds of regions; rendering each is a
# subprocess per region. Anything dropped by this cap is reported on stderr —
# a silent cap would read as "there were no more figures".
_FIGURE_MAX_PER_PAGE = 20
# Document-level ceiling on files written. The per-page caps bound one page; a
# hostile file bounds nothing by having many pages, and unbounded output to
# someone else's disk is its own failure mode. 2000 is far above any real
# document's artwork (the 29-page dogfood export yields 2 files) and low enough
# to stop a fan-out. Anything dropped is reported, never silent. Read by
# `_ImageSink.store` (the budget itself) and by `main` (the warning text) —
# those two sites only.
_MAX_FILES_PER_DOCUMENT = 2000
# Seconds any single `pdftocairo` crop may take before it is abandoned (parity
# with preview.py's pdftoppm timeout).
_PDFTOCAIRO_TIMEOUT = 30
# Extensions an extracted raster may carry. pypdf decodes to these; anything
# else is written as `.bin` rather than given a plausible image extension. The
# ONLY site that reads this is `_image_suffix`.
_IMAGE_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".jp2", ".tiff", ".tif", ".bmp", ".gif", ".webp",
})
# Pixel ceiling for a raster the extractor will ask pypdf to decode. pypdf
# allocates from the stream's DECLARED /Width and /Height, not from the bytes on
# disk, so a few hundred bytes of Flate can demand gigabytes. The declaration is
# read from the image XObject dictionary (`_declared_size`) before anything is
# decoded — see `_raster_streams` for why enumeration must not go through
# `page.images`, which decodes as it walks.
#
# This is a backstop, not the only bound: pypdf 6.x refuses any Flate stream
# inflating past 75 MB (`ZLIB_MAX_OUTPUT_LENGTH`) and Pillow refuses ~89 MP on
# the JPEG path, so an oversized image usually fails inside the library first —
# loudly, as `undecodable`. 80 MP sits above every real document image (a 600
# dpi A0 scan is ~66 MP) so it never rejects genuine content; its job is to
# refuse the *allocation* for a filter those library limits do not cover.
# Read by `_extract_rasters` (the guard itself) and by `main` (the warning
# text) — those two sites only.
_IMAGE_MAX_PIXELS = 80_000_000

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

# Layout hints (advisory, exit code untouched). A caller who never reads the
# reference gets the same two remedies the reference documents, at the moment
# they are needed. Both thresholds are measured, not guessed — see
# `_orphan_list_markers` / `_single_column_tables`.
_LIST_MARKERS = frozenset("•●▪‣◦○□◆➔▸*-–—·+")
_ORPHAN_MARKER_HINT = 2      # one stray glyph is noise; a broken list repeats
_PHANTOM_TABLE_HINT = 2      # …or half the tables, whichever comes first
_PHANTOM_TABLE_RATIO = 0.5


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


def _named_dir(value: str) -> Path:
    """An argparse type for a directory that must actually be named.

    `Path("")` normalises to `PosixPath(".")`, so an empty argument silently
    becomes the working directory and artwork is scattered across it at exit 0
    — the accident of `--extract-images "$OUTDIR"` with `OUTDIR` unset, and
    exactly what "DIR is mandatory" promises cannot happen. The check has to
    live here, in the argparse type, because by the time the namespace exists
    the empty string is already indistinguishable from an explicit ".", which
    remains allowed."""
    if not value.strip():
        raise argparse.ArgumentTypeError(
            "requires a directory name; got an empty string (an unset shell "
            "variable?)")
    return Path(value)


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
            "encrypted-without-password / --extract-images names a file); "
            "2 usage error; 6 SelfOverwriteRefused (-o path, or "
            "--extract-images, is the input PDF); 10 DocumentScanned (whole "
            "document is image-only — run OCR or the Read tool)."
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
    parser.add_argument(
        "--extract-images", type=_named_dir, default=None, metavar="DIR",
        help="Also write the document's artwork into DIR (created if needed) "
             "and list it per page in the dump as `images`. Two classes come "
             "out: embedded rasters, copied byte-for-byte as stored, and "
             "vector figures (diagrams and charts drawn with path operators, "
             "for which no image object exists), cropped from the page at "
             "--image-dpi. Identical images are written once and shared by "
             "every placement; page-sized backdrops are skipped. DIR is "
             "mandatory — nothing is ever written to the current directory by "
             "default.",
    )
    parser.add_argument(
        "--image-dpi", type=int, default=_DEFAULT_IMAGE_DPI, metavar="N",
        help="Resolution for VECTOR figure crops (default %(default)s). "
             "Rasters are copied as stored and are unaffected.",
    )
    parser.add_argument(
        "--no-vector-images", dest="vector_images", action="store_false",
        help="With --extract-images, extract embedded rasters only and do not "
             "render vector figures. The escape hatch for a document where the "
             "figure heuristic misfires, and for a host without Poppler.",
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


def _vector_clusters(objects, width: float, height: float):
    """Cluster path objects into the regions a reader sees as one drawing.

    Returns `(clusters, grid_cells)` where each cluster is a dict with `bbox`
    (the union of its members' bounding boxes, in page coordinates), `cells`
    (the area of its *cell* bounding box, in grid cells) and `members` (the
    objects that fell into it); `grid_cells` is the total cell count of the
    page grid. `vector_coverage` is derived from `cells / grid_cells` and the
    figure crops from `bbox`, so the measurement and the extraction can never
    disagree about what a cluster is.

    Summing path bounding boxes directly is useless — a ruling line's box has
    ~zero area, yet a table of them plainly occupies a region of the page. So
    the paths are painted onto a `_VECTOR_CELL_PT` grid, connected clusters are
    found (8-connectivity, so a diagonal or dashed stroke still joins), and each
    cluster contributes its bounding box. That answers the question the figure
    signal actually asks: how much of the sheet does the artwork span. It is an
    approximation quantised to the cell size, and clusters whose boxes overlap
    double-count, hence the clamp applied by the caller.

    Page-sized background fills are dropped first (`_is_backdrop`) — one such
    rect would otherwise mark every cell and report a prose page as wholly
    artwork."""
    page_area = width * height
    if page_area <= 0 or not objects:
        return [], 0
    objects = [obj for obj in objects if not _is_backdrop(obj, page_area)]
    if not objects:
        return [], 0
    cell = max(_VECTOR_CELL_PT,
               width / _VECTOR_GRID_MAX_CELLS, height / _VECTOR_GRID_MAX_CELLS)
    cols = int(width / cell) + 1
    rows = int(height / cell) + 1
    grid = bytearray(cols * rows)
    # One representative cell per object, kept so the second pass can hand the
    # object to the cluster it landed in. Any of its cells will do: an object
    # paints a solid rectangle of cells, which is connected by construction, so
    # every one of them ends up in the same component.
    anchors: list[tuple[dict, int]] = []

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
        anchors.append((obj, r0 * cols + c0))

    # `labels[cell]` is the index of the cluster that owns it, or -1. The flood
    # fill is the original one; labelling is what lets members be recovered
    # exactly. It is sized by the GRID (bounded by `_VECTOR_GRID_MAX_CELLS`),
    # not by the object count, which is what keeps a page of thousands of paths
    # from blowing the mapping up.
    labels = [-1] * (cols * rows)
    clusters: list[dict] = []
    for start in range(cols * rows):
        if grid[start] != 1:
            continue
        grid[start] = 2  # 2 == already absorbed into a cluster
        index_of_cluster = len(clusters)
        stack = [start]
        min_r = max_r = start // cols
        min_c = max_c = start % cols
        while stack:
            index = stack.pop()
            labels[index] = index_of_cluster
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
        clusters.append({
            "bbox": None,
            "cells": (max_r - min_r + 1) * (max_c - min_c + 1),
            "members": [],
        })

    for obj, anchor in anchors:
        cluster = clusters[labels[anchor]]
        cluster["members"].append(obj)
        box = _obj_box(obj)
        current = cluster["bbox"]
        cluster["bbox"] = box if current is None else (
            min(current[0], box[0]), min(current[1], box[1]),
            max(current[2], box[2]), max(current[3], box[3]))
    return clusters, cols * rows


def _coverage_of(clusters: list, grid_cells: int) -> float:
    """Fraction of the sheet spanned by already-clustered vector artwork — the
    sum of the cell boxes over the page grid, clamped to 1.0 because
    overlapping cluster boxes would otherwise sum past the page.

    The ONE site that computes `vector_coverage`. It takes clusters rather than
    objects so `_extract_page`, which needs the clusters anyway for the figure
    crops, can share this expression instead of inlining a second copy — a
    duplicate here silently moves the dump's `vector_coverage` out from under
    whatever tests guard this function."""
    if not grid_cells:
        return 0.0
    return min(1.0, sum(c["cells"] for c in clusters) / grid_cells)


def _vector_coverage(objects, width: float, height: float) -> float:
    """`_coverage_of` over freshly clustered objects — the standalone form,
    used where the clusters are not needed for anything else."""
    return _coverage_of(*_vector_clusters(objects, width, height))


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


# --- image extraction (--extract-images) ------------------------------------

def _is_image_backdrop(image: dict, page_area: float) -> bool:
    """True for a raster whose placement covers essentially the whole sheet — a
    background wash or a whole-page scan, not a figure. The ONLY site that reads
    `_IMAGE_BACKDROP_RATIO`."""
    if page_area <= 0:
        return False
    x0, top, x1, bottom = _obj_box(image)
    return abs(x1 - x0) * abs(bottom - top) >= _IMAGE_BACKDROP_RATIO * page_area


def _table_boxes(page) -> list[tuple[float, float, float, float]]:
    """Bounding boxes of the tables pdfplumber finds on `page`.

    Deliberately uses pdfplumber's DEFAULT (`lines`) detection regardless of
    `--table-strategy`. The two uses pull in opposite directions: the dump's
    `tables` wants the strategy that reports the *real* tables, while this one
    wants the broadest possible notion of "this region is a table", because
    every box it returns is a *rejection* and the filter is tuned for
    precision. Keeping it fixed also means `--table-strategy` cannot silently
    change which figures come out.

    Best-effort: table detection is a heuristic over the same path objects the
    figure clusterer walks, and a malformed page can make it raise. A failure
    here may only *admit* a spurious figure, never suppress a real one, so it
    is swallowed rather than propagated."""
    try:
        return [tuple(float(v) for v in table.bbox)
                for table in page.find_tables()]
    except Exception:
        return []


def _overlap_ratio(box: tuple, other: tuple) -> float:
    """Fraction of `box`'s area that lies inside `other`. 0.0 when `box` is
    degenerate, so a zero-area cluster can never be called a table."""
    width = max(0.0, min(box[2], other[2]) - max(box[0], other[0]))
    height = max(0.0, min(box[3], other[3]) - max(box[1], other[1]))
    area = max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
    if area <= 0:
        return 0.0
    return (width * height) / area


def _is_figure_cluster(cluster: dict, page_width: float, page_height: float,
                       table_boxes: list) -> bool:
    """Is this cluster of paths a *figure* — something a reader would want as a
    picture — rather than page furniture?

    Four tests, all measured (see the constants). Two do the real work and
    neither subsumes the other:

    * **at least one stroked path.** Shading is drawn with fills and no stroke:
      code-block backgrounds, heading rules, inline-code chips, the full-width
      cards a Notion/Confluence export paints behind every block. Every one of
      the ~30 spurious clusters measured on the fill-only side scored 0 stroked
      paths; every one of the four genuine figures scored 5-29. The cost is
      stated in the module's honest-scope list: a figure drawn *entirely* with
      fills (a flat pie chart) is not extracted.
    * **not a table.** Table ruling IS stroked, so the test above cannot see it;
      it clusters into one region that overlaps pdfplumber's own table bbox by
      0.98-1.00, while no genuine figure overlapped a table at all.

    The remaining two drop specks: a cluster must span `_FIGURE_MIN_AREA_RATIO`
    of the sheet and be at least `_FIGURE_MIN_SIDE_PT` on both sides, which
    rejects inline-code chips (0.002 of a sheet) and hairline rules. The ONLY
    site that reads any of the three constants."""
    box = cluster["bbox"]
    if box is None or page_width <= 0 or page_height <= 0:
        return False
    width, height = box[2] - box[0], box[3] - box[1]
    if width < _FIGURE_MIN_SIDE_PT or height < _FIGURE_MIN_SIDE_PT:
        return False
    if (width * height) / (page_width * page_height) < _FIGURE_MIN_AREA_RATIO:
        return False
    if not any(member.get("stroke") for member in cluster["members"]):
        return False
    return not any(_overlap_ratio(box, table) >= _FIGURE_TABLE_OVERLAP
                   for table in table_boxes)


def _figure_boxes(page, box: tuple):
    """A cluster bbox → `(page_box, render_box)`, both padded and clamped.

    Two frames, returned together so they cannot drift apart. `page_box` is in
    the page coordinates every other bbox in the dump uses (`_obj_box`, the
    raster records) and is what gets reported; `render_box` is the same
    rectangle in the frame `pdftocairo` crops in, and never leaves this module.
    Reporting the render frame instead would put two coordinate systems in one
    JSON field, distinguishable only on a PDF whose MediaBox is not at (0, 0) —
    invisible on every ordinary document.

    Poppler draws the MediaBox with its origin at the top-left of the output
    image, while pdfplumber measures objects from the *unshifted* origin, so a
    PDF whose MediaBox does not start at (0, 0) offsets the two frames against
    each other and every crop lands on the wrong part of the sheet. Measured on
    a MediaBox of `(20, -30, 632, 762)`: a path pdfplumber reports at
    `(100, 142)` renders at `(78.7, 170.4)` — i.e. subtract the MediaBox origin
    from BOTH axes. On the usual `(0, 0)` page both corrections are the
    identity, which is exactly why the bug is invisible without
    `fixtures/shifted.pdf`, and why that fixture exists.

    Page rotation needs no handling: pdfplumber already reports coordinates in
    the rotated frame (a `/Rotate 90` letter page measures 792x612), and so does
    Poppler.

    The box is padded by `_FIGURE_PAD_PT` and clamped to the sheet."""
    origin_x = float(page.mediabox[0])
    origin_y = float(page.mediabox[1])
    x0 = box[0] - origin_x - _FIGURE_PAD_PT
    x1 = box[2] - origin_x + _FIGURE_PAD_PT
    top = box[1] - origin_y - _FIGURE_PAD_PT
    bottom = box[3] - origin_y + _FIGURE_PAD_PT
    render = (max(0.0, x0), max(0.0, top),
              min(float(page.width), x1), min(float(page.height), bottom))
    page_box = (render[0] + origin_x, render[1] + origin_y,
                render[2] + origin_x, render[3] + origin_y)
    return page_box, render


def _px(value: float, dpi: int) -> int:
    """Points → whole pixels at `dpi`."""
    return int(round(value * dpi / 72.0))


def _sha1(data: bytes) -> str:
    """Content identity for dedup and for the filename — NOT a security
    primitive. `usedforsecurity=False` says so, and keeps the call working on a
    FIPS-enforcing host, where an unflagged sha1 raises and would take the whole
    extraction with it."""
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()


class _ImageBudgetExceeded(Exception):
    """The document-level file budget is spent. Caught per page so the pages
    already extracted keep their records and the dump still emits."""


class _ImageSink:
    """Writes extracted artwork into the destination directory, deduplicated.

    One instance per document. Holds the sha1 → filename map that implements
    the dedup guard: a document measured for this feature placed a single
    background raster 31 times among 49 placements, so a naive extractor writes
    32 files nobody needs. Placements are still reported individually — each
    keeps its own page and bbox — they simply share one file on disk.

    Counters exist so `main` can report what did NOT come out: `undecodable`
    (a raster whose bytes pypdf could not produce) is kept apart from
    `render_failed` (a vector crop Poppler could not draw) because they have
    different repairs, and both from `dropped_capped` / `vector_unrendered`. A
    cap or a failure that says nothing reads as "there was nothing more to
    extract"."""

    def __init__(self, directory: Path, *, dpi: int) -> None:
        self.directory = directory
        self.dpi = dpi
        self._by_digest: dict[str, str] = {}
        self._by_objid: dict[int, tuple[str, str]] = {}
        self._per_page: dict[int, int] = {}
        self.written = 0
        self.deduped = 0
        self.undecodable = 0
        self.render_failed = 0
        self.oversized = 0
        self.page_failed = 0
        self.over_document_cap = 0
        self.dropped_backdrop = 0
        self.dropped_capped = 0
        self.vector_unrendered = 0

    def store(self, data: bytes, *, page_number: int, kind: str,
              suffix: str, objid: int | None = None) -> tuple[str, str]:
        """Write `data` (or reuse an identical earlier file) → `(path, sha1)`.

        The returned path is the destination directory joined with the file
        name *as the caller spelled the directory* — a relative
        `--extract-images out/img` yields `out/img/p005-r01-….png`, which
        resolves from the same working directory the CLI ran in, so a Markdown
        document can reference it verbatim.

        Dedup is keyed on the PDF object number first and the digest second.
        The digest is what makes two *different* objects sharing one image
        collapse, but hashing every placement means re-hashing the same buffer
        once per placement: one document placed a single image 31 times, and a
        crafted one can place a 75 MB image thousands of times, turning a small
        file into terabytes of hashing. An objid that has been stored before
        cannot have different bytes, so it short-circuits before the hash."""
        if objid is not None:
            remembered = self._by_objid.get(objid)
            if remembered is not None:
                self.deduped += 1
                return remembered
        digest = _sha1(data)
        existing = self._by_digest.get(digest)
        if existing is not None:
            self.deduped += 1
            if objid is not None:
                self._by_objid[objid] = (existing, digest)
            return existing, digest
        if self.written >= _MAX_FILES_PER_DOCUMENT:
            self.over_document_cap += 1
            raise _ImageBudgetExceeded()
        sequence = self._per_page.get(page_number, 0) + 1
        self._per_page[page_number] = sequence
        name = (f"p{page_number:03d}-{kind[0]}{sequence:02d}-"
                f"{digest[:8]}{suffix}")
        path = self.directory / name
        self._write(path, data)
        self.written += 1
        self._by_digest[digest] = str(path)
        if objid is not None:
            self._by_objid[objid] = (str(path), digest)
        return str(path), digest

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        """Create `path` and write `data`, refusing to follow a symlink.

        `Path.write_bytes` opens `O_WRONLY|O_CREAT|O_TRUNC` and follows
        symlinks, while every component of the file name — page, kind,
        sequence, digest prefix — is predictable to whoever supplied the PDF
        (they know their own images' digests). A symlink planted in a shared
        destination therefore redirects the write to its target, with
        attacker-chosen bytes. `O_NOFOLLOW | O_EXCL` refuses both that and a
        pre-existing regular file.

        Re-running into the same directory is still idempotent: an existing
        file holding exactly these bytes is accepted as already written, which
        makes the idempotence an explicit contract rather than a side effect of
        `O_TRUNC`. Anything else — same name, different content — is a genuine
        collision and raises."""
        try:
            handle = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600)
        except FileExistsError:
            if not path.is_symlink() and path.is_file() \
                    and path.read_bytes() == data:
                return
            raise
        with os.fdopen(handle, "wb") as sink:
            sink.write(data)


def _open_pypdf(pdf_path: Path, password: str | None):
    """A `pypdf` reader for the same file, or `None`.

    Imported lazily and failure-tolerantly on purpose. pdfplumber gives the
    *placements* (which image is painted where, with its bbox); only pypdf
    decodes an image XObject into bytes a file can hold, applying the filter
    chain and folding an /SMask alpha plane into the pixels. Neither library
    does both. Because this is needed only under `--extract-images`, a missing
    or unhappy pypdf must not change what the tool does without the flag — and
    must degrade to "no rasters, said loudly" rather than to a traceback."""
    try:
        import pypdf  # noqa: PLC0415 — deliberate: only the flag needs it
        reader = pypdf.PdfReader(str(pdf_path))
        if reader.is_encrypted and password is not None:
            reader.decrypt(password)
        return reader
    except Exception:
        return None


def _declared_size(entry) -> tuple[int, int]:
    """`/Width` x `/Height` as pypdf's decoder will read them, or `(0, 0)`.

    Deliberately NOT pdfplumber's `srcsize`. pdfminer resolves that through
    ``get_any(("W", "Width"))`` — first key present wins — while pypdf reads
    ``/Width`` only. An image XObject carrying the inline-image abbreviations
    *alongside* the real keys (``/W 1 /H 1 /Width 40000 /Height 40000``) is
    therefore reported by pdfplumber as 1x1 while pypdf allocates 1.6 G pixels:
    a 14-byte edit that makes the size guard and the decoder disagree. Measured
    on a crafted file: `srcsize` (1, 1), pypdf decode 400x300. A non-numeric or
    indirect value yields `(0, 0)` — "unknown", which the caller treats as
    uncapped rather than as zero."""
    try:
        width = int(entry.get("/Width", 0))
        height = int(entry.get("/Height", 0))
    except (TypeError, ValueError):
        return (0, 0)
    return (max(0, width), max(0, height))


def _raster_streams(reader, index: int) -> dict:
    """`{PDF object number: (image key, declared width, declared height)}`.

    Enumerates a page's images WITHOUT decoding any of them. `page.images` is
    tempting and wrong for this: iterating it calls pypdf's `_get_image` for
    every entry, which runs the whole filter chain and builds a Pillow image
    eagerly — so a size check performed afterwards guards nothing, and a
    hostile `/Width`/`/Height` has already driven the allocation. `keys()`
    costs nothing (measured at 0.000 s) and still walks nested Form XObjects,
    which a hand-rolled scan of `/Resources/XObject` does NOT: a page whose
    image lives inside a form exposes only the form at the top level, so
    rolling our own would silently lose it.

    Keyed by object number because that is the join back to pdfplumber's
    placements (`image["stream"].objid` == the XObject's `idnum`). Going
    through the placements is what keeps two pypdf artefacts out of the output:
    a page's resource dictionary lists images it never paints, and an /SMask
    alpha plane is enumerated as its own greyscale entry beside the RGBA image
    it belongs to. Decoding is deferred to `_fetch_raster`, which is called
    only for placements that survive every guard."""
    if reader is None:
        return {}
    streams: dict = {}
    try:
        page = reader.pages[index]
        keys = list(page.images.keys())
    except Exception:
        return {}
    for key in keys:
        # Accumulate outside any single try: one unresolvable key must not cost
        # the keys already resolved for this page.
        try:
            node = page["/Resources"]["/XObject"]
            reference = None
            for part in (key if isinstance(key, list) else [key]):
                reference = node.raw_get(part)
                entry = node[part].get_object()
                if entry.get("/Subtype") == "/Image":
                    idnum = getattr(reference, "idnum", None)
                    if idnum is not None:
                        streams[int(idnum)] = (key, *_declared_size(entry))
                    break
                node = entry["/Resources"]["/XObject"]
        except Exception:
            continue
    return streams


def _fetch_raster(reader, index: int, key):
    """Decode ONE image, by key. The only place a raster is decoded.

    Split out from enumeration so every guard — placement, backdrop, declared
    size — runs first. Returns `(bytes, suffix)` or `None`; pypdf raises for a
    filter it cannot handle, a truncated stream, and (in 6.x) for any Flate
    stream inflating past `ZLIB_MAX_OUTPUT_LENGTH` (75 MB), which a legitimate
    ~25 MP RGB image exceeds."""
    try:
        image = reader.pages[index].images[key]
        return image.data, _image_suffix(image.name)
    except Exception:
        return None


def _image_suffix(name) -> str:
    """The file extension for an extracted raster, from an allowlist.

    pypdf names the image after its resource key plus the format it decoded to.
    That name is PDF-controlled data, and `Path(...).suffix` on POSIX happily
    returns a backslash-bearing string for a crafted key — harmless here, but
    the filename is written to disk, so it is built only from values this module
    chose. An unrecognised format becomes `.bin` rather than a plausible `.png`:
    mislabelling an undecoded blob as an image is the same silent lie the rest
    of this tool exists to prevent."""
    suffix = Path(str(name)).suffix.lower()
    return suffix if suffix in _IMAGE_SUFFIXES else ".bin"


def _extract_rasters(page, streams: dict, sink: _ImageSink, *,
                     page_number: int, reader=None, index: int = 0
                     ) -> list[dict]:
    """Copy every raster *placement* on `page` out to a file.

    Guard order is the whole point and is load-bearing: a placement must clear
    the page-sized-backdrop test (`_is_image_backdrop`) AND the declared-pixel
    cap (`_IMAGE_MAX_PIXELS`) BEFORE anything is decoded, because the decode
    allocation is driven by the declaration rather than by the bytes on disk.
    `_raster_streams` therefore hands over declared sizes only, and
    `_fetch_raster` is called last, per surviving placement.

    An image whose bytes cannot be produced — a filter pypdf cannot decode, a
    truncated stream, a Flate stream over pypdf's 75 MB inflate ceiling — is
    counted in `sink.undecodable` and skipped, never faked."""
    records: list[dict] = []
    page_area = float(page.width) * float(page.height)
    for image in page.images:
        if _is_image_backdrop(image, page_area):
            sink.dropped_backdrop += 1
            continue
        stream = image.get("stream")
        objid = getattr(stream, "objid", None)
        source = streams.get(int(objid)) if objid is not None else None
        if source is None:
            sink.undecodable += 1
            continue
        key, width, height = source
        # `(0, 0)` means the declaration was missing or unreadable, not zero —
        # such an image is passed through to the decoder rather than silently
        # dropped, since dropping it would be the content loss this tool exists
        # to prevent.
        if width and height and width * height > _IMAGE_MAX_PIXELS:
            sink.oversized += 1
            continue
        fetched = _fetch_raster(reader, index, key)
        if fetched is None:
            sink.undecodable += 1
            continue
        data, suffix = fetched
        path, digest = sink.store(
            data, page_number=page_number, kind="raster", suffix=suffix,
            objid=objid)
        records.append({
            "file": path,
            "kind": "raster",
            "bbox": [round(v, 2) for v in _obj_box(image)],
            "name": image.get("name"),
            # From the XObject dict, NOT pdfplumber's `srcsize`: the two
            # disagree whenever a file carries the `/W`,`/H` abbreviations, and
            # reporting 1x1 for a 400x300 image is a lie in the dump itself.
            "width": width or None,
            "height": height or None,
            "bytes": len(data),
            "sha1": digest,
        })
    return records


def _figures_on(page, clusters: list) -> list:
    """The clusters on `page` that are figures — the ONE definition.

    Both the renderer and the "detected but not rendered" counter need this
    answer, and computing it twice means a fifth predicate could silently make
    the counter disagree with what would actually have been extracted.
    `find_tables()` is hoisted here because it re-runs pdfplumber's whole edge
    detection; evaluating it per cluster would run it hundreds of times on a
    dense page."""
    if not clusters:
        return []
    tables = _table_boxes(page)
    width, height = float(page.width), float(page.height)
    return [c for c in clusters
            if _is_figure_cluster(c, width, height, tables)]


def _extract_vectors(page, clusters: list, sink: _ImageSink, *,
                     page_number: int, pdf_path: Path, pdftocairo: str,
                     password: str | None) -> list[dict]:
    """Rasterise each vector figure on `page` into its own file.

    A vector figure is not an object in the file — it is a set of path
    operators — so there are no bytes to copy and the only honest extraction is
    to render the region it occupies. `pdftocairo` crops in *pixels* from the
    top-left of the rendered MediaBox, hence `_figure_boxes` + `_px`.

    Poppler's own SVG output would keep the artwork as vectors, but it ignores
    the crop rectangle and always emits the whole page (verified against
    poppler 26.06), so cropping to the figure means a raster."""
    # Hoisted deliberately: `find_tables()` re-runs pdfplumber's whole edge
    # detection, and evaluating it inside the comprehension would run it once
    # per cluster — hundreds of times on a dense page.
    figures = _figures_on(page, clusters)
    if len(figures) > _FIGURE_MAX_PER_PAGE:
        sink.dropped_capped += len(figures) - _FIGURE_MAX_PER_PAGE
        figures = figures[:_FIGURE_MAX_PER_PAGE]
    records: list[dict] = []
    for cluster in figures:
        page_box, box = _figure_boxes(page, cluster["bbox"])
        width = _px(box[2] - box[0], sink.dpi)
        height = _px(box[3] - box[1], sink.dpi)
        if width <= 0 or height <= 0:
            sink.render_failed += 1
            continue
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "figure"
            command = [
                pdftocairo, "-png", "-r", str(sink.dpi),
                "-f", str(page_number), "-l", str(page_number),
                "-singlefile",
                "-x", str(_px(box[0], sink.dpi)),
                "-y", str(_px(box[1], sink.dpi)),
                "-W", str(width), "-H", str(height),
            ]
            if password is not None:
                command += ["-upw", password]
            # resolve(): a relative INPUT that begins with "-" would be
            # parsed by poppler as an option, swallowing the next argument.
            command += [str(pdf_path.resolve()), str(prefix)]
            rendered = prefix.with_suffix(".png")
            try:
                subprocess.run(command, capture_output=True, check=True,
                               timeout=_PDFTOCAIRO_TIMEOUT)
                data = rendered.read_bytes()
            except (subprocess.SubprocessError, OSError):
                sink.render_failed += 1
                continue
        path, digest = sink.store(
            data, page_number=page_number, kind="vector", suffix=".png")
        records.append({
            "file": path,
            "kind": "vector",
            # Page coordinates, the same frame as a raster record's bbox —
            # NOT the pdftocairo crop rectangle (see `_figure_boxes`).
            "bbox": [round(v, 2) for v in page_box],
            "name": None,
            "width": width,
            "height": height,
            "bytes": len(data),
            "sha1": digest,
        })
    return records


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
    images: dict | None = None,
) -> dict:
    """Build one PageRecord (ARCH §4.2) from a pdfplumber page.

    `n` is filled by the caller. `char_count` is the *stripped* length of the
    extracted text (whitespace-only page → 0). `tables` is the raw
    `extract_tables()` form (list of row-lists of `str | None`). `scanned` is
    delegated to `_classify_page`, `figure_dominant` to `_classify_figure_page`.

    `images` carries the `--extract-images` context (sink, page number, source
    path, the resolved `pdftocairo`) or is `None`. When it is `None` the record
    has no `images` key at all, so a dump taken without the flag is byte-for-byte
    what it always was; when it is set, `images` is present and an empty list
    means "looked, found nothing" rather than "did not look".

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
    # One clustering pass feeds both the coverage number and the figure crops,
    # so the measurement and the extraction can never disagree about what a
    # cluster is.
    clusters, grid_cells = _vector_clusters(
        [*page.lines, *page.rects, *page.curves], width, height)
    vector_coverage = round(_coverage_of(clusters, grid_cells), 4)
    scanned = _classify_page(char_count, has_images)
    record = {
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
    if images is not None:
        try:
            record["images"] = _extract_page_images(page, clusters, images)
        except _ImageBudgetExceeded:
            # Distinct from a page failure: nothing is wrong with the page, the
            # document-level file budget is simply spent. Already counted in
            # `over_document_cap`.
            record["images"] = []
        except Exception:
            # The text and tables ARE the contract; artwork is an extra. A
            # hostile or malformed image must not cost the caller the dump, so
            # the page's extraction is abandoned, counted and reported rather
            # than propagated. Without this the docstring's "deliberately not
            # allowed to fail the dump" is a promise nothing keeps.
            images["sink"].page_failed += 1
            record["images"] = []
    return record


def _extract_page_images(page, clusters: list, images: dict) -> list[dict]:
    """Both extraction branches for one page, in page order: rasters first
    (they are copied out as stored), then vector figures (they are rendered).

    The vector branch is skipped entirely when Poppler is absent or
    `--no-vector-images` was passed; the count of figures that were *detected
    and not rendered* is accumulated so `main` can say so out loud."""
    sink: _ImageSink = images["sink"]
    page_number: int = images["page_number"]
    records = _extract_rasters(
        page, images["streams"], sink, page_number=page_number,
        reader=images["reader"], index=page_number - 1)
    pdftocairo = images["pdftocairo"]
    if pdftocairo is None:
        sink.vector_unrendered += len(_figures_on(page, clusters))
        return records
    return records + _extract_vectors(
        page, clusters, sink, page_number=page_number,
        pdf_path=images["pdf_path"], pdftocairo=pdftocairo,
        password=images["password"])


def extract_pdf(
    pdf_path: Path, *, password: str | None, layout: bool,
    x_tolerance_ratio: float | None = _DEFAULT_X_TOLERANCE_RATIO,
    y_tolerance: float | None = None,
    table_strategy: str = _DEFAULT_TABLE_STRATEGY,
    images_dir: Path | None = None,
    image_dpi: int = _DEFAULT_IMAGE_DPI,
    vector_images: bool = True,
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
    from.

    `images_dir` is the only switch for image extraction: `None` (the default)
    leaves every page record and the top level exactly as they were, so no
    existing caller sees a shape change. When it is set the directory is created
    if needed, each page gains an `images` list, and the top level gains
    `images_dir` / `image_dpi` / `images_summary`. The extraction is
    deliberately *not* allowed to fail the dump: the text and tables are the
    contract, so a missing Poppler or an undecodable image degrades to a
    counted, reported omission (see the `_ImageSink` counters, surfaced by
    `main`)."""
    ratio = x_tolerance_ratio if (
        x_tolerance_ratio and x_tolerance_ratio > 0) else None
    y_tol = y_tolerance if (y_tolerance and y_tolerance > 0) else None
    font_acc: dict[tuple, dict] = {}
    seen_objects: set = set()
    sink = None
    reader = None
    pdftocairo = None
    with _open_pdf(pdf_path, password) as pdf:
        # Created only after the PDF opens: a corrupt or wrongly-passworded
        # input should not leave an empty directory behind on a failed run.
        if images_dir is not None:
            try:
                images_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                # ONLY the directory creation earns this diagnosis. An OSError
                # from anywhere else in the walk (lazy page parsing, a network
                # mount) must keep its historical shape rather than telling the
                # caller to fix permissions on a directory that is fine.
                raise _ExtractError(
                    f"Could not create the image directory {images_dir}: "
                    f"{exc}", error_type="ImageDirWriteFailed") from exc
            sink = _ImageSink(images_dir, dpi=image_dpi)
            reader = _open_pypdf(pdf_path, password)
            pdftocairo = shutil.which("pdftocairo") if vector_images else None
        pages: list[dict] = []
        for index, page in enumerate(pdf.pages, start=1):
            _collect_page_fonts(page, font_acc, seen_objects)
            images = None if sink is None else {
                "sink": sink,
                "page_number": index,
                "streams": _raster_streams(reader, index - 1),
                "reader": reader,
                "pdf_path": pdf_path,
                "pdftocairo": pdftocairo,
                "password": password,
            }
            record = _extract_page(
                page, layout=layout, x_tolerance_ratio=ratio,
                y_tolerance=y_tol, table_strategy=table_strategy,
                images=images)
            record["n"] = index
            pages.append(record)
    doc_scanned, scanned_pages = _classify_document(pages)
    fonts = [font_acc[key] for key in sorted(font_acc)]
    dump = {
        "page_count": len(pages),
        "doc_scanned": doc_scanned,
        "scanned_pages": scanned_pages,
        "figure_pages": [p["n"] for p in pages if p["figure_dominant"]],
        "text_layer_lossy": _classify_text_layer(
            fonts, any(p["char_count"] > 0 for p in pages)),
        "x_tolerance_ratio": ratio,
        "y_tolerance": y_tol,
        "table_strategy": table_strategy,
        # Always present, like `figure_pages` / `scanned_pages`: a wrapper can
        # branch on the numbers even when the stderr hint was suppressed
        # (which happens once the caller has already turned the knob).
        "layout_hints": {
            "orphan_list_markers": _orphan_list_markers(pages),
            "single_column_tables": _single_column_tables(pages),
            "tables": sum(len(p["tables"]) for p in pages),
        },
        "fonts": fonts,
        "pages": pages,
    }
    if sink is not None:
        dump["images_dir"] = str(images_dir)
        dump["image_dpi"] = image_dpi
        # What did NOT come out is reported as data, not only as a warning: a
        # caller diffing two dumps can see that four images were undecodable
        # this time, which a stderr line nobody captured cannot tell them.
        dump["images_summary"] = {
            "files_written": sink.written,
            "placements": sum(len(p["images"]) for p in pages),
            "deduplicated": sink.deduped,
            "page_sized_skipped": sink.dropped_backdrop,
            "undecodable": sink.undecodable,
            "render_failed": sink.render_failed,
            "oversized": sink.oversized,
            "over_page_cap": sink.dropped_capped,
            "over_document_cap": sink.over_document_cap,
            "page_failed": sink.page_failed,
            "reader_unavailable": reader is None,
            "vector_unrendered": sink.vector_unrendered,
        }
    return dump


def _same_path(a: Path, b: Path) -> bool:
    """True if `a` and `b` resolve to the same filesystem path (symlinks
    followed). `b` need not exist yet — `resolve()` is non-strict."""
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def _orphan_list_markers(pages: list[dict]) -> int:
    """Count lines that hold a bare list marker and nothing else.

    pdfplumber groups words into lines with an *absolute* 3 pt tolerance. A
    bullet set a couple of points smaller than its item — the default in Google
    Docs and Confluence exports — falls outside that band, becomes its own
    line, and sorts AFTER the text it belongs to, so the Markdown a caller
    composes has the marker under the item instead of before it. Measured: 32
    such lines in a 29-page Google Docs export, 3 in the `bullets.pdf` fixture,
    0 in every other fixture; `--y-tolerance 5` takes all of them to 0.

    Counting is deliberately dumb — a stripped line of exactly one marker
    character — because that is the shape of the defect. It cannot see a marker
    glued to a wrong item, and a document that legitimately puts a lone `*` on
    its own line is counted here too; that is why the hint needs
    `_ORPHAN_MARKER_HINT` of them before it says anything.
    """
    return sum(
        1
        for page in pages
        for line in (page.get("text") or "").split("\n")
        if len(line.strip()) == 1 and line.strip() in _LIST_MARKERS
    )


def _single_column_tables(pages: list[dict]) -> int:
    """Count extracted tables whose every row holds exactly one cell.

    Under the default `lines` strategy pdfplumber treats a filled background
    rectangle as a table edge, so a shaded paragraph comes back as a "table" of
    one column. Measured: 23 of 61 tables in the Google Docs export, 5 of 6 on
    a Wikipedia print, 1 of 2 in the `shaded.pdf` fixture, 0 in every clean
    one; `--table-strategy lines_strict` takes all of them to 0.

    This is a *floor*, not the phantom count: the same export also produced
    multi-column phantoms, which look exactly like real tables from here (the
    strict run dropped 45 tables, of which only 23 were single-column). The
    hint says what was measured and points at the strategy that settles it.
    """
    return sum(
        1
        for page in pages
        for table in (page.get("tables") or [])
        if table and all(len(row) == 1 for row in table)
    )


def _hint_orphan_markers(hints: dict, y_tolerance: float | None) -> bool:
    """Should the orphaned-marker hint be printed?

    Two conditions, and the second is not cosmetic: once the caller has passed
    `--y-tolerance`, the decision is theirs and repeating the advice is noise.
    The count stays in the dump either way, so a wrapper can still see it.
    """
    return (hints["orphan_list_markers"] >= _ORPHAN_MARKER_HINT
            and y_tolerance is None)


def _hint_phantom_tables(hints: dict, table_strategy: str) -> bool:
    """Should the single-column-table hint be printed?

    Fires on `_PHANTOM_TABLE_HINT` tables **or** on half of them, whichever
    comes first: two one-column tables in a 60-table document is already worth
    a look (measured: 23 of 61 on a Google Docs export, a ratio of 0.38), and
    so is one of two (the `shaded.pdf` fixture). One of three is neither, and
    stays quiet. Silent under `lines_strict` for the same reason as above — the
    caller has already run the experiment this hint asks for.
    """
    if table_strategy != "lines" or not hints["tables"]:
        return False
    return (hints["single_column_tables"] >= _PHANTOM_TABLE_HINT
            or hints["single_column_tables"] / hints["tables"]
            >= _PHANTOM_TABLE_RATIO)


def _emit(dump: dict, out_path: Path | None) -> None:
    """Serialise `dump` as indented JSON to the sink. `out_path is None` →
    stdout; otherwise overwrite `out_path` (idempotent). stdout always
    carries the dump — never the `--json-errors` envelope, which goes to
    stderr.

    stdout is written as UTF-8 **bytes** by `_errors.write_json_stdout`,
    deliberately bypassing the text layer, because that layer encodes with
    the process locale and the dump is a machine-readable channel: measured
    under `PYTHONIOENCODING=ascii` the old text write aborted mid-stream with
    a raw `UnicodeEncodeError` traceback — 1264 bytes of truncated JSON
    already on stdout, exit 1, no envelope — and under `cp1252` it silently
    wrote an em dash as byte 0x97, i.e. a dump that is not valid UTF-8, at
    exit 0. JSON is UTF-8 by definition (RFC 8259 §8.1), so these bytes must
    not depend on the caller's locale. A stdout with no `.buffer` (a test's
    `StringIO`, a wrapper's proxy object) keeps the text path — there the
    caller owns the encoding and we cannot second-guess it.

    Serialisation on the stdout path is **one-shot**, not streamed: the whole
    document is built as one string, escaped, and encoded before any of it is
    written. That buys the guarantee that a payload which cannot be
    serialised leaves *nothing* on the wire rather than a truncated document.
    The `-o FILE` path streams into the file, as it always did.

    The price is **memory, not time**. Measured on the fixture the dead-pipe
    tests build (`tests/fixtures/digital.pdf` concatenated 150x = 300 pages,
    a 149 247-byte dump), HEAD's streaming loop against this code, both
    writing to /dev/null, CPython 3.14.4:

      * memory — `tracemalloc` peak 7 698 B streamed against 1 042 776 B
        one-shot: 0.05x the payload against 6.99x (on a 48-page real
        document, a 115 941-byte dump: 0.20x against 6.91x). The multiple is
        not one copy but three: `json.dumps(..., indent=2)` takes CPython's
        Python-level encoder, which builds a list of per-token chunks and
        joins it, and the encoded bytes then live alongside the joined
        string. It also tracks the payload's *widest* character — the same
        dump reduced to pure ASCII peaks at 3.00x, and one astral character
        anywhere in it takes the string to UCS-4 and the peak to 12.0x.
      * time — one-shot is *faster* on these payloads, not slower: median of
        9 runs, 2.61 ms streamed against 0.73 ms one-shot (0.75 ms against
        0.56 ms on the 116 KB dump). Streaming pays a `str.encode()` and a
        `write()` per encoder chunk, and an indented 300-page dump is tens of
        thousands of chunks. The surrogate escape is 0.34 ms of the one-shot
        figure: `_errors.py` matches with a compiled regex, where the
        per-character scan an earlier version used costs 3.12 ms on the same
        string, and `str.isascii()` skips both on an ASCII payload.

    Neither half shows at process level: max RSS 127.2-127.3 MB streamed
    against 127.3-127.5 MB one-shot (two runs each — the gap is inside the
    run-to-run spread) and 0.92-0.95 s against 0.86-0.88 s for the whole run,
    because pdfplumber's page objects dominate both. The memory multiple is
    real and scales with the dump; on this workload it is not the thing that
    decides whether the process fits.

    On a dead pipe `write_json_stdout` re-raises `BrokenPipeError` after
    pointing fd 1 at /dev/null; `main()` maps it to the `OutputWriteFailed`
    envelope. Nothing here catches it.

    The `-o FILE` path was never locale-dependent (`open(..., encoding=
    "utf-8")`) and is unchanged.
    """
    if out_path is None:
        write_json_stdout(dump, indent=2)
    else:
        # Auto-create the parent dir (parity with pdf_split.py / preview.py).
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(dump, fh, ensure_ascii=False, indent=2)
            fh.write("\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse → extract → emit → return the exit code.

    Exit codes: 0 success; 1 failure (`InputNotFound` / `EncryptedPDF` /
    `CorruptPdf` / `OutputWriteFailed` / `ImageDirNotADirectory` /
    `ImageDirWriteFailed` / `InternalError`); 2 usage error (argparse, plus the
    manual `--image-dpi < 1` and empty-`--extract-images` checks, both
    `UsageError`); 6 `SelfOverwriteRefused` — `-o` OR `--extract-images`
    resolves to the input PDF, with `details.flag` naming which; 10
    `DocumentScanned` (whole-document scan). On a whole-doc scan the dump is
    still emitted (to stdout or `-o`) — exit 10 + stderr is the loud signal.

    Two side effects of `--extract-images` a wrapper should know about, because
    "non-zero means nothing happened" is no longer true:

    * artwork is written during extraction, before the dump is serialised, so a
      later `OutputWriteFailed` exits 1 with files already in DIR and no dump
      indexing them. Point `-o` outside DIR and this cannot arise.
    * the exit-10 branch returns before every image warning, so on a
      whole-document scan the omission counters are in `images_summary` only —
      that is deliberate, since `--json-errors` promises a single JSON line on
      stderr and a warning printed beside the envelope would break it."""
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

    # cross-7 parity again, for the image destination: a `--extract-images`
    # pointing at the input PDF would have `mkdir` fail with a confusing errno
    # (or, if the path is a directory that happens to be the input's parent,
    # quietly scatter PNGs beside it). Refuse the same way `-o` does.
    if args.extract_images is not None and _same_path(
            input_path, args.extract_images):
        return report_error(
            f"Refusing to write extracted images over the input PDF "
            f"(--extract-images resolves to INPUT): {input_path}",
            code=_EXIT_SELF_OVERWRITE, error_type="SelfOverwriteRefused",
            # `flag` discriminates the two refusals: both are exit 6 with the
            # same type, and a wrapper should not have to parse English to
            # tell which destination it must change.
            details={"path": str(input_path), "flag": "--extract-images"},
            json_mode=je,
        )

    if (args.extract_images is not None and args.extract_images.exists()
            and not args.extract_images.is_dir()):
        return report_error(
            f"--extract-images must name a directory, but "
            f"{args.extract_images} is an existing file.",
            code=_EXIT_FAIL, error_type="ImageDirNotADirectory",
            details={"path": str(args.extract_images)}, json_mode=je,
        )

    if args.image_dpi < 1:
        return report_error(
            f"--image-dpi must be a positive integer, got {args.image_dpi}.",
            code=_EXIT_USAGE, error_type="UsageError",
            details={"image_dpi": args.image_dpi}, json_mode=je,
        )

    # cross-7 parity: refuse to overwrite the input PDF with the JSON dump.
    # `resolve()` also neutralises a symlinked `-o` pointing back at the input.
    if args.output is not None and _same_path(input_path, args.output):
        return report_error(
            f"Refusing to overwrite the input PDF with the JSON dump "
            f"(-o resolves to INPUT): {input_path}",
            code=_EXIT_SELF_OVERWRITE, error_type="SelfOverwriteRefused",
            details={"path": str(input_path), "flag": "-o"}, json_mode=je,
        )

    try:
        dump = extract_pdf(
            input_path, password=args.password, layout=args.layout,
            x_tolerance_ratio=args.x_tolerance_ratio,
            y_tolerance=args.y_tolerance,
            table_strategy=args.table_strategy,
            images_dir=args.extract_images,
            image_dpi=args.image_dpi,
            vector_images=args.vector_images)
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
    except BrokenPipeError:
        # Two sinks reach this arm, so name the one that actually broke: a
        # dead reader on stdout (`… | head`) and a `-o` FIFO whose reader is
        # gone both raise EPIPE, and an envelope that says "stdout" for the
        # second sends the caller after the wrong thing (measured: `-o FIFO`
        # with the reader closed reported `details.path: "stdout"`).
        #
        # No `dup2` here. On the stdout path `write_json_stdout` has already
        # pointed fd 1 at /dev/null (`_errors.abandon_stdout`), so the
        # interpreter's shutdown flush finds nothing to retry and the exit
        # status stays the one this envelope declares instead of 120. On the
        # `-o` path fd 1 was never written to and there is nothing to
        # redirect — a second, blind redirect would only hide that.
        target = str(args.output) if args.output is not None else "stdout"
        return report_error(
            f"{target} closed before the dump was fully written (broken pipe)",
            code=_EXIT_FAIL, error_type="OutputWriteFailed",
            details={"path": target}, json_mode=je,
        )
    except OSError as exc:
        # `args.output` is None when the dump goes to stdout; naming the sink
        # "None" told the reader nothing about which sink failed.
        target = str(args.output) if args.output is not None else "stdout"
        return report_error(
            f"Could not write output {target}: {exc}",
            code=_EXIT_FAIL, error_type="OutputWriteFailed",
            details={"path": target}, json_mode=je,
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
        # With --extract-images the artwork has just been written out, so the
        # instruction changes from "go and extract it" to "the text of this
        # dump still does not contain it — use the files".
        if not dump.get("images_dir"):
            remedy = ("the diagram is NOT in this dump. Extract the image "
                      "(--extract-images DIR) or read those pages visually "
                      "before composing Markdown.")
        else:
            # Naming the directory is only useful for pages that actually
            # produced a file. A flagged page can come back empty — Poppler
            # absent, --no-vector-images, a render failure, or a fill-only
            # cluster the figure predicate rejects — and pointing those at
            # "the extracted file(s)" would send the caller looking for
            # something that was never written.
            served = {p["n"] for p in dump["pages"] if p.get("images")}
            unserved = [n for n in dump["figure_pages"] if n not in served]
            if not unserved:
                remedy = (f"the diagram itself is not text and is NOT in this "
                          f"dump — see the per-page `images` entries for the "
                          f"extracted file(s) in {dump['images_dir']}.")
            else:
                missing = ", ".join(str(n) for n in unserved)
                remedy = (f"the diagram itself is not text and is NOT in this "
                          f"dump, and NOTHING was extracted for page(s) "
                          f"{missing} — read those visually (preview.py). Any "
                          f"other page's artwork is in {dump['images_dir']}.")
        sys.stderr.write(
            f"warning: page(s) {pages} are mostly figure (see per-page "
            f"image_coverage / vector_coverage) with little text — {remedy}\n"
        )
    if args.extract_images is None and (
            args.image_dpi != _DEFAULT_IMAGE_DPI or not args.vector_images):
        sys.stderr.write(
            "warning: --image-dpi / --no-vector-images do nothing without "
            "--extract-images; no artwork was written.\n"
        )
    summary = dump.get("images_summary")
    if summary is not None:
        # Report the omissions, never just the successes: a cap or a decode
        # failure that says nothing reads as "there was nothing more to get".
        if summary["undecodable"]:
            cause = (
                "pypdf could not be used at all (import or open failed), so no "
                "raster could be decoded"
                if summary.get("reader_unavailable") else
                "pypdf could not decode them (unsupported filter, truncated "
                "stream, or a single stream over pypdf's 75 MB inflate ceiling "
                "— a legitimate ~25 MP image exceeds it)"
            )
            sys.stderr.write(
                f"warning: {summary['undecodable']} raster placement(s) were "
                f"NOT written — {cause}. Their content is missing from "
                f"{dump['images_dir']}; render those pages with preview.py to "
                f"see what they held.\n"
            )
        if summary["render_failed"]:
            sys.stderr.write(
                f"warning: {summary['render_failed']} vector figure(s) failed "
                f"to render (pdftocairo errored or timed out) and are NOT in "
                f"{dump['images_dir']}.\n"
            )
        if summary["vector_unrendered"]:
            sys.stderr.write(
                f"warning: {summary['vector_unrendered']} vector figure(s) "
                f"were detected but NOT rendered"
                + (" (--no-vector-images)" if not args.vector_images else
                   " because pdftocairo (Poppler) is not on PATH; install "
                   "Poppler (brew install poppler / apt-get install "
                   "poppler-utils)")
                + ". Embedded rasters were still extracted.\n"
            )
        if summary["oversized"]:
            sys.stderr.write(
                f"warning: {summary['oversized']} raster(s) declare more than "
                f"{_IMAGE_MAX_PIXELS // 1_000_000} megapixels and were NOT "
                f"decoded — decoding is sized by the declaration, so a "
                f"malformed one can exhaust memory.\n"
            )
        if summary["over_page_cap"]:
            sys.stderr.write(
                f"warning: {summary['over_page_cap']} vector figure(s) past "
                f"the per-page cap of {_FIGURE_MAX_PER_PAGE} were NOT "
                f"rendered.\n"
            )
        if summary["over_document_cap"]:
            sys.stderr.write(
                f"warning: the document-level budget of "
                f"{_MAX_FILES_PER_DOCUMENT} files is spent — "
                f"{summary['over_document_cap']} further image(s) were NOT "
                f"written. The dump lists only what reached disk.\n"
            )
        if summary["page_failed"]:
            sys.stderr.write(
                f"warning: artwork extraction raised on "
                f"{summary['page_failed']} page(s); their `images` lists are "
                f"empty. The text and tables for those pages are unaffected.\n"
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
    # Layout hints, last because they are advisory: both leave the exit code
    # alone, and each fires only while its remedy is still on the table. A
    # caller who already passed the flag has made the call; repeating the
    # advice would be noise, and the counts stay in `layout_hints` regardless.
    hints = dump["layout_hints"]
    if _hint_orphan_markers(hints, dump["y_tolerance"]):
        sys.stderr.write(
            f"hint: {hints['orphan_list_markers']} line(s) contain nothing but "
            f"a list marker. pdfplumber groups lines with an absolute 3 pt "
            f"tolerance, so a bullet in a smaller point size becomes its own "
            f"line and sorts AFTER the item it belongs to — composing Markdown "
            f"from this dump puts the marker under its text. Re-run with "
            f"--y-tolerance 5 and compare.\n"
        )
    if _hint_phantom_tables(hints, dump["table_strategy"]):
        sys.stderr.write(
            f"hint: {hints['single_column_tables']} of {hints['tables']} "
            f"extracted table(s) have a single column, which is what a shaded "
            f"paragraph looks like once its background rectangle is read as a "
            f"table edge. Re-run with --table-strategy lines_strict to see "
            f"which of them survive; that count is a floor, multi-column "
            f"phantoms are indistinguishable from real tables here.\n"
        )
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

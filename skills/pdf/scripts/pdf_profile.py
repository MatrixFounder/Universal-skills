#!/usr/bin/env python3
"""Profile a born-digital PDF's typographic template before converting it.

What this answers
-----------------
Converting a typeset document to Markdown starts with a handful of questions
that are cheap to *measure* and expensive to guess: which point size is body
text, which sizes are headings, does the file emit space glyphs or position its
words, what are those shaded rectangles, are the tables ruled in a way
``extract_tables`` can see, and which of the tiny images are figures rather
than inline icons. Dogfooding a 1206-page conversion showed an agent spending
roughly a quarter of the job writing one-off pdfplumber probes to answer
exactly these, then re-deriving them for the next document.

This script is those probes, once, as a tool. It writes a report, changes
nothing, and makes no composition decisions — every finding names the evidence
so the caller can disagree with it.

The four findings that change the outcome most
----------------------------------------------
* **``furniture``** — running headers and footers are located by *position and
  repetition across pages*, never by point size and never by a y cut-off. A
  measured document set its legal-disclaimer chapter in the same 6 pt as its
  page footer; a size filter silently deleted the whole chapter. A y threshold
  is the same trap on a different axis, and it was measured failing in both
  directions at once: on a 3-column magazine, 113 line records started above
  the header band's lowest edge (y=52.7) and only 16 of them were furniture,
  so the cut-off would have deleted 97 real lines — while the DOI line that
  repeats on 18 of its 20 pages sits at y=66.1, *below* the cut, and would
  have survived. So the report names *patterns* — digit-masked text, region,
  pages, observed y range — and reports ``header_bottom`` / ``footer_top`` as
  geometry, not as a threshold to filter on. It still warns when the
  furniture's point sizes are also used by real body text.

* **``tables``** — ``extract_tables()`` finding zero tables does not mean the
  page has none. A producer that rules rows but not columns leaves no
  intersecting edges, so both ``lines`` and ``lines_strict`` return nothing
  while the page is visibly a table. The report compares what each strategy
  finds against how many *ruled regions* the geometry actually contains, and
  hands over the column signature to rebuild them with.

* **``spacing``** — the word-gap threshold is measured from this file's own
  bimodal gap distribution instead of assumed.

* **``ligatures``** — the count of duplicate char dicts pdfplumber will hand a
  caller that builds text from ``page.chars`` (see ``_textlines.dedupe``).

Usage
-----
    python3 scripts/pdf_profile.py INPUT.pdf [--pages N] [--json]
                                   [--columns SPEC] [--password PW]
                                   [--json-errors]

Exit codes: ``0`` profiled; ``1`` unreadable / encrypted without a password;
``2`` usage (an unparseable or unsatisfiable ``--columns`` SPEC included). A
profile is a *report*, so a document with alarming findings still exits ``0``
— the findings are the output, not an error.
"""

from __future__ import annotations

import _venv_bootstrap  # self-bootstrap into scripts/.venv (CLAUDE.md §2)
_venv_bootstrap.reexec_into_venv(requires=("pdfplumber",), _file=__file__)

import argparse
import collections
import re
from pathlib import Path

import pdfplumber  # type: ignore

import _textlines as tl
from _errors import (add_json_errors_argument, install_human_channel,
                     report_error, write_json_stdout, write_text_stdout)

_DEFAULT_SAMPLE = 40
_TOP_BAND = 0.12          # fraction of page height treated as the header band
_BOTTOM_BAND = 0.88       # ... and the footer band
_DIGITS = re.compile(r"\d+")

# A furniture pattern is the same digit-masked text, at the same height, in
# the same region, on most pages. Measured on two designed magazines: every
# real pattern held a bbox[1] spread of at most 0.3 pt across its pages, so
# 1.0 pt is a wide margin, not a tuned number.
_PATTERN_PAGE_SHARE = 0.5
_PATTERN_MIN_PAGES = 3
_PATTERN_Y_SPREAD = 1.0
_PAGE_REGION = "page"     # the region name used when --columns is absent
_TILE_TOL = 1.0           # pt of slack when named ranges must tile the page
_ADJ_TOL = 0.01           # ... and when one named range must meet the next


def _sample_count(value: str) -> int:
    """argparse type= validator for ``--pages``: a count, where 0 is the
    documented "every page".

    A negative N reached :func:`_textlines._sample` as ``count <= 0`` and
    silently meant every page too -- the opposite of the smallest sample the
    caller asked for, and something the help text does not offer.
    """
    try:
        pages = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"must be a whole number of pages, got {value!r}") from None
    if pages < 0:
        raise argparse.ArgumentTypeError(
            f"must be 0 or more (0 = every page), got {pages}")
    return pages



def _textlines_is_password_failure(exc: BaseException) -> bool:
    """True when `exc` means "wrong or missing PDF password".

    pdfplumber re-raises pdfminer's `PDFPasswordIncorrect` inside its own
    `PdfminerException`, and both stringify to nothing, so the class is matched
    through `args` and `__cause__` rather than the text. Kept in step with the
    identical helper in `pdf_verify_md.py`.
    """
    try:
        from pdfminer.pdfdocument import PDFPasswordIncorrect
    except ImportError:      # pragma: no cover - pdfplumber's own dependency
        return False
    seen: list = [exc]
    for _ in range(8):       # bounded: a wrapper chain, not a search
        if not seen:
            break
        current = seen.pop()
        if isinstance(current, PDFPasswordIncorrect):
            return True
        seen.extend(a for a in getattr(current, "args", ())
                    if isinstance(a, BaseException))
        if current.__cause__ is not None:
            seen.append(current.__cause__)
    return False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf_profile.py",
        description="Profile a digital PDF's template before converting it.")
    parser.add_argument("INPUT", type=Path, help="Source PDF file.")
    parser.add_argument(
        "--pages", type=_sample_count, default=_DEFAULT_SAMPLE, metavar="N",
        help="Sample N evenly spaced pages (default %(default)s; 0 = every "
             "page). Sampling keeps the profile fast on long documents; "
             "repetition-based findings scale with the sample, not the file.")
    parser.add_argument(
        "--columns", default=None, metavar="SPEC",
        help="Scope the running-furniture pattern probe to vertical regions, "
             "as either increasing cuts ('152.5,456.5', regions named "
             "col1..colN left to right) or named ranges tiling the page "
             "('side:0-158,body:158-458,notes:458-612'). Page coordinates in "
             "points. Without it the probe runs page-wide and labels its "
             "output 'region: page' -- on a multi-column page, lines welded "
             "across the gutter never repeat identically, so patterns are "
             "under-counted (a measured 3-column document: 1 pattern "
             "page-wide against 4 scoped). Scopes this one probe only; every "
             "other probe stays page-wide, and nothing is cropped on output.")
    parser.add_argument("--password", default=None, metavar="PW",
                        help="Password for an encrypted PDF.")
    parser.add_argument("--json", action="store_true",
                        help="Emit the profile as JSON instead of a report.")
    add_json_errors_argument(parser)
    return parser


# -------------------------------------------------------------------- regions

class _ColumnSpecError(ValueError):
    """A ``--columns`` SPEC that cannot be honoured, naming the bad token."""


def _parse_columns(spec: str):
    """``--columns`` SPEC -> ``('cuts', [x, ...])`` or ``('ranges', [(name, x0, x1), ...])``.

    Two accepted forms, by specification the same grammar ``pdf_extract.py
    --columns`` accepts:

    * bare increasing cuts, ``"152.5,456.5"`` — regions are named ``col1``
      ... ``colN`` left to right;
    * named ranges, ``"side:0-158,body:158-458,notes:458-612"`` — the ranges
      must tile ``[0, page.width]`` with no gap and no overlap.

    Mixing the two forms is an error, as is any unparseable token; the
    message names the token so the caller can fix it without guessing.
    Widths are page-dependent, so the tiling and in-range checks happen in
    ``_regions_for`` once a page is in hand.

    The grammar is parsed here, in full, with no import from
    ``pdf_extract.py``: the profiler only *probes* regions to see whether
    furniture repeats inside them, and never crops anything on output.
    """
    if not spec.strip():
        raise _ColumnSpecError("--columns: empty spec")
    tokens = [t.strip() for t in spec.split(",")]
    for t in tokens:
        if not t:
            raise _ColumnSpecError(f"--columns: empty token in {spec!r}")
    named = [":" in t for t in tokens]
    if any(named) and not all(named):
        raise _ColumnSpecError(
            "--columns: mixes bare cuts and named ranges; use one form or "
            f"the other in {spec!r}")
    if all(named):
        ranges = []
        seen = set()
        for t in tokens:
            name, _, span = t.partition(":")
            name = name.strip()
            if not name:
                raise _ColumnSpecError(f"--columns: token {t!r} has no region name")
            if name in seen:
                raise _ColumnSpecError(f"--columns: region name {name!r} used twice")
            seen.add(name)
            parts = span.split("-")
            if len(parts) != 2:
                raise _ColumnSpecError(
                    f"--columns: token {t!r} is not name:x0-x1")
            x0, x1 = (_coord(p, t) for p in parts)
            if not x1 > x0:
                raise _ColumnSpecError(
                    f"--columns: token {t!r} does not increase ({x0} -> {x1})")
            ranges.append((name, x0, x1))
        return ("ranges", ranges)
    cuts = [_coord(t, t) for t in tokens]
    for a, b in zip(cuts, cuts[1:]):
        if not b > a:
            raise _ColumnSpecError(
                f"--columns: cuts must increase, got {a} then {b}")
    return ("cuts", cuts)


def _coord(token: str, whole: str) -> float:
    try:
        return float(token.strip())
    except (TypeError, ValueError):
        bad = token.strip()
        where = "" if bad == whole.strip() else f" in {whole!r}"
        raise _ColumnSpecError(
            f"--columns: {bad!r}{where} is not a number") from None


def _regions_for(page, columns, page_number=None):
    """The regions to probe on this page: ``[(name, x0, x1), ...]``.

    Without a spec the single region is the whole page, named ``page`` — the
    caller can then see in the output that no scoping happened.
    """
    left, _, right, _ = (float(v) for v in page.bbox)
    where = f" on page {page_number}" if page_number is not None else ""
    if not columns:
        return [(_PAGE_REGION, left, right)]
    kind, data = columns
    if kind == "cuts":
        for cut in data:
            if not left < cut < right:
                raise _ColumnSpecError(
                    f"--columns: cut {cut} is outside the page's "
                    f"[{round(left, 1)}, {round(right, 1)}]{where}")
        edges = [left] + list(data) + [right]
        return [(f"col{i + 1}", edges[i], edges[i + 1])
                for i in range(len(edges) - 1)]
    ranges = sorted(data, key=lambda r: r[1])
    if abs(ranges[0][1] - left) > _TILE_TOL or abs(ranges[-1][2] - right) > _TILE_TOL:
        raise _ColumnSpecError(
            f"--columns: named ranges must tile the page's "
            f"[{round(left, 1)}, {round(right, 1)}]{where}, but they span "
            f"[{ranges[0][1]}, {ranges[-1][2]}]")
    for a, b in zip(ranges, ranges[1:]):
        if abs(a[2] - b[1]) > _ADJ_TOL:
            gap = "gap" if b[1] > a[2] else "overlap"
            raise _ColumnSpecError(
                f"--columns: {gap} between {a[0]!r} (ends {a[2]}) and "
                f"{b[0]!r} (starts {b[1]}){where}")
    return list(ranges)


def _region_page(page, x0, x1):
    """The page itself for the page-wide region, else ``page.crop()`` of the
    band. ``crop`` and never ``within_bbox``: a line half inside the band must
    contribute its inside half, not vanish."""
    left, top, right, bottom = (float(v) for v in page.bbox)
    box = (max(left, x0), top, min(right, x1), bottom)
    if box[0] <= left and box[2] >= right:
        return page
    if box[2] - box[0] <= 0:
        return None
    try:
        return page.crop(box)
    except Exception:
        return None


# --------------------------------------------------------------------- probes

def _fonts_and_sizes(pages, ratio):
    """Inventory of families and point sizes, with a body-text hypothesis."""
    sizes: collections.Counter = collections.Counter()
    fonts: collections.Counter = collections.Counter()
    size_font: dict = collections.defaultdict(collections.Counter)
    samples: dict = {}
    ligature_dupes = 0
    pua: collections.Counter = collections.Counter()
    rotated = 0
    for page in pages:
        try:
            chars = page.chars
        except Exception:
            continue
        rotated += sum(1 for c in chars if not c.get("upright", True))
        up = tl.upright(chars)
        ligature_dupes += len(up) - len(tl.dedupe(up))
        for c in up:
            text = c.get("text") or ""
            fam = tl.family(c.get("fontname"))
            if tl.is_pua(text):
                pua[fam] += 1
                continue
            if not text.strip():
                continue
            size = round(float(c.get("size") or 0), 1)
            sizes[size] += 1
            fonts[fam] += 1
            size_font[size][fam] += 1
    body = sizes.most_common(1)[0][0] if sizes else None
    # One sample line per size, so a caller can see what a size actually is.
    for page in pages:
        for line in tl.page_lines(page, ratio=ratio):
            size = line.get("size")
            if size is not None and size not in samples and line["text"].strip():
                samples[size] = line["text"][:70]
        if len(samples) >= 24:
            break
    return {
        "body_size": body,
        "sizes": [{"size": s, "chars": n,
                   "fonts": [f for f, _ in size_font[s].most_common(3)],
                   "role": _role(s, body, size_font[s]),
                   "sample": samples.get(s)}
                  for s, n in sorted(sizes.items(), key=lambda kv: -kv[1])[:14]],
        "fonts": [{"family": f, "chars": n, "style_guess": tl.classify_style(f)}
                  for f, n in fonts.most_common(12)],
        "ligature_duplicate_chars": ligature_dupes,
        "icon_font_glyphs": [{"family": f, "count": n} for f, n in pua.most_common(6)],
        "rotated_chars": rotated,
    }


def _role(size, body, fonts_at_size):
    """A hypothesis, stated as one, for what a point size is for."""
    if body is None:
        return "unknown"
    # startswith, not ==: classify_style also answers 'bold-italic', and a
    # bold-italic display face is a heading candidate exactly like a bold one.
    bold = any(tl.classify_style(f).startswith("bold") for f in fonts_at_size)
    if abs(size - body) < 0.05:
        return "body"
    if size > body + 0.5:
        return "heading candidate" if bold else "large text"
    return "small text (caption / table / footnote)"


def _furniture(pages, ratio, columns=None):
    """Running headers and footers, by position and repetition — never by
    point size, and never by a y cut-off.

    What the report hands over is a list of *patterns*: the same text with
    digits masked (page numbers vary), seen at the same height inside the same
    region on most pages. A pattern qualifies at ``_PATTERN_PAGE_SHARE`` of the
    sampled pages (at least ``_PATTERN_MIN_PAGES``) with a ``bbox[1]`` spread
    of at most ``_PATTERN_Y_SPREAD`` pt across its occurrences. A caller drops
    furniture by matching that masked text — the same test this probe used —
    and nothing here deletes anything.

    ``header_bottom`` / ``footer_top`` stay in the output as *reported
    geometry*, because knowing where the bands sit is useful, but they are not
    a threshold to filter on and this probe no longer recommends one: measured
    on a 3-column magazine, 113 line records started above y=52.7 and only 16
    were furniture (97 real lines would have been deleted), while a DOI line
    repeating on 18 of 20 pages sits at y=66.1, below the cut, and would have
    survived it. Both failures at once, on the same document.

    ``columns`` scopes the pattern census; without it the whole page is one
    region named ``page`` and the output says so. The scoping is not cosmetic:
    on that same magazine, lines welded across the gutters repeat 1 pattern
    page-wide against 4 when the three columns are probed separately.

    Honest scope: the cuts come from the caller and are used as given. This
    probe does not find them, and it does not check that one avoids splitting
    text — a cut through a line yields the two halves as two patterns in two
    regions, which is what a measured document did with a byline crossing its
    sidebar boundary. Patterns are the only thing scoping changes; every other
    probe in this file stays page-wide, and nothing is cropped on output.
    """
    band_counts: dict = collections.defaultdict(set)
    band_lines: dict = collections.defaultdict(list)
    pat_pages: dict = collections.defaultdict(set)
    pat_tops: dict = collections.defaultdict(list)
    body_sizes: collections.Counter = collections.Counter()
    sampled = 0
    ref_height = float(pages[0].height or 0) or 1.0
    region_names: list = []
    region_box: dict = {}
    for idx, page in enumerate(pages):
        height = float(page.height or 0) or 1.0
        regions = _regions_for(page, columns)
        saw_lines = False
        for name, x0, x1 in regions:
            if name not in region_names:
                region_names.append(name)
                region_box[name] = (round(x0, 1), round(x1, 1))
            src = _region_page(page, x0, x1)
            lines = tl.page_lines(src, ratio=ratio) if src is not None else []
            if not lines:
                continue
            saw_lines = True
            for line in lines:
                norm = _DIGITS.sub("#", line["text"]).strip().lower()[:80]
                if norm:
                    pat_pages[(name, norm)].add(idx)
                    pat_tops[(name, norm)].append(line["bbox"][1])
                _, top, _, bottom = line["bbox"]
                if top < _TOP_BAND * height:
                    band = "top"
                elif bottom > _BOTTOM_BAND * height:
                    band = "bottom"
                else:
                    if line.get("size") is not None:
                        body_sizes[line["size"]] += 1
                    continue
                band_counts[(band, norm)].add(idx)
                band_lines[(band, norm)].append(line)
        if saw_lines:
            sampled += 1
    if not sampled:
        return {"detected": False}
    threshold = max(_PATTERN_MIN_PAGES, int(sampled * _PATTERN_PAGE_SHARE))
    repeated = {k: v for k, v in band_counts.items() if len(v) >= threshold}
    patterns = []
    for (name, norm), page_ids in sorted(pat_pages.items(),
                                         key=lambda kv: (-len(kv[1]), kv[0])):
        if len(page_ids) < threshold:
            continue
        tops = pat_tops[(name, norm)]
        if max(tops) - min(tops) > _PATTERN_Y_SPREAD:
            continue
        mid = (max(tops) + min(tops)) / 2.0
        band = ("top" if mid < _TOP_BAND * ref_height
                else "bottom" if mid > _BOTTOM_BAND * ref_height else "body")
        patterns.append({"pattern": norm, "region": name, "band": band,
                         "pages": len(page_ids),
                         "y_min": round(min(tops), 1),
                         "y_max": round(max(tops), 1)})
    regions_out = [{"name": n, "x0": region_box[n][0], "x1": region_box[n][1]}
                   for n in region_names]
    if not repeated and not patterns:
        return {"detected": False, "sampled_pages": sampled,
                "region_scoped": bool(columns), "regions": regions_out,
                "patterns": []}
    header_bottom = None
    footer_top = None
    sizes_used: collections.Counter = collections.Counter()
    for (band, norm), page_ids in repeated.items():
        lines = band_lines[(band, norm)]
        tops = [l["bbox"][1] for l in lines]
        bottoms = [l["bbox"][3] for l in lines]
        for l in lines:
            if l.get("size") is not None:
                sizes_used[l["size"]] += 1
        if band == "top":
            header_bottom = max(bottoms) if header_bottom is None else max(header_bottom, max(bottoms))
        else:
            footer_top = min(tops) if footer_top is None else min(footer_top, min(tops))
    collisions = sorted(s for s in sizes_used if body_sizes.get(s, 0) > 0)
    return {
        "detected": True,
        "sampled_pages": sampled,
        "region_scoped": bool(columns),
        "regions": regions_out,
        # Reported geometry. NOT a filter threshold -- see the docstring.
        "header_bottom": round(header_bottom, 1) if header_bottom is not None else None,
        "footer_top": round(footer_top, 1) if footer_top is not None else None,
        "sizes": sorted(sizes_used),
        "size_collides_with_body_text": collisions,
        "patterns": patterns,
    }


def _regions(pages):
    """Filled boxes (callouts / code samples) and ruled rows (tables)."""
    colors: collections.Counter = collections.Counter()
    white = 0
    box_pages = 0
    rule_pages = 0
    ruled_regions = 0
    signatures: collections.Counter = collections.Counter()
    for page in pages:
        boxes = tl.fill_boxes(page)
        visible = [b for b in boxes if not _near_white(b["color"])]
        white += len(boxes) - len(visible)
        if visible:
            box_pages += 1
            for b in visible:
                colors[tuple(b["color"] or ())] += 1
        rows = tl.rule_rows(page)
        if rows:
            rule_pages += 1
            # Consecutive rows sharing a column signature are one ruled region.
            prev = None
            for row in rows:
                sig = tuple(row["x"])
                if prev is None or not _sig_compatible(sig, prev):
                    ruled_regions += 1
                    signatures[sig] += 1
                prev = sig if prev is None or len(sig) >= len(prev) else prev
    return {
        "fill_box_pages": box_pages,
        "white_boxes": white,
        "fill_colors": [{"color": list(c), "count": n}
                        for c, n in colors.most_common(6)],
        "ruled_pages": rule_pages,
        "ruled_regions": ruled_regions,
        "column_signatures": [{"x": list(s), "regions": n}
                              for s, n in signatures.most_common(5)],
    }


def _near_white(color):
    """A white-on-white rectangle is a mask or a page ground, never a visible
    callout, so it is kept out of the callout colour census."""
    return bool(color) and all(v >= 0.99 for v in color)


def _sig_compatible(a, b, tol=2.0):
    """Same table? A vertically merged cell rules only the columns it divides,
    so a continuation row's signature is a subset of the table's."""
    if not a or not b:
        return False
    if abs(max(a) - max(b)) > tol:
        return False
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return all(any(abs(x - y) <= tol for y in big) for x in small)


def _tables(pages):
    """What each detection strategy finds, against what the geometry holds.

    Zero tables from every strategy on pages that carry ruled regions is the
    signal to stop tuning strategies and rebuild from the rules instead.
    """
    found = {}
    for name, settings in (
            ("lines", None),
            ("lines_strict", {"vertical_strategy": "lines_strict",
                              "horizontal_strategy": "lines_strict"}),
            ("text", {"vertical_strategy": "text",
                      "horizontal_strategy": "text"})):
        total = 0
        for page in pages:
            try:
                tables = (page.extract_tables(table_settings=settings)
                          if settings else page.extract_tables())
                total += len(tables or [])
            except Exception:
                continue
        found[name] = total
    return found


def _lists(pages, ratio):
    """Bullet glyphs, their x positions, and orphaned markers."""
    marker_x: collections.Counter = collections.Counter()
    glyphs: collections.Counter = collections.Counter()
    orphans = 0
    for page in pages:
        for line in tl.page_lines(page, ratio=ratio):
            if line.get("marker_only"):
                orphans += 1
            first = line["text"][:1]
            if first and first in tl.BULLET_CHARS:
                glyphs[first] += 1
                marker_x[round(line["bbox"][0], 1)] += 1
    # A bullet inside a table cell sits at its own x and would fake an indent
    # step, so only positions carrying a real share of the markers count.
    total = sum(marker_x.values())
    floor = max(2, int(total * 0.05))
    xs = sorted(x for x, n in marker_x.items() if n >= floor)
    steps = [round(b - a, 1) for a, b in zip(xs, xs[1:]) if 4 < (b - a) < 60]
    return {
        "bullet_glyphs": [{"glyph": g, "count": n} for g, n in glyphs.most_common(4)],
        "marker_x": xs,
        "indent_step": min(steps) if steps else None,
        "orphan_marker_lines": orphans,
    }


def _images(pages):
    """Figures against inline icons: size plus how often the same image
    recurs. A navigation chevron repeated on 400 pages is not artwork."""
    census: dict = collections.defaultdict(lambda: {"count": 0, "w": 0.0, "h": 0.0})
    for page in pages:
        try:
            images = page.images
        except Exception:
            continue
        for im in images:
            w = round(float(im.get("x1", 0)) - float(im.get("x0", 0)), 1)
            h = round(float(im.get("bottom", 0)) - float(im.get("top", 0)), 1)
            key = (im.get("srcsize") or (im.get("width"), im.get("height")), w, h)
            try:
                entry = census[tuple(key[0]) + (w, h)]
            except TypeError:
                entry = census[(None, w, h)]
            entry["count"] += 1
            entry["w"], entry["h"] = w, h
    figure_like = [e for e in census.values() if min(e["w"], e["h"]) >= 45]
    icon_like = [e for e in census.values() if max(e["w"], e["h"]) < 24]
    repeated = sorted((e for e in census.values() if e["count"] > 3),
                      key=lambda e: -e["count"])[:5]
    return {
        "distinct_images": len(census),
        "figure_like": len(figure_like),
        "icon_like": len(icon_like),
        "most_repeated": [{"w": e["w"], "h": e["h"], "placements": e["count"]}
                          for e in repeated],
    }


# ------------------------------------------------------------- recommendations

def _recommend(profile) -> list[str]:
    out = []
    f = profile["fonts_and_sizes"]
    if f["ligature_duplicate_chars"]:
        out.append(
            f"{f['ligature_duplicate_chars']} duplicate char dicts from ligature "
            "glyphs: building text from page.chars without _textlines.dedupe() "
            "will produce 'Profifiles' / 'Offffers'.")
    sp = profile["spacing"]
    if sp["measured"] and sp.get("source") == "labelled":
        out.append(
            f"Use x_tolerance_ratio {sp['ratio']} when rebuilding text from chars: "
            f"it was scored against the {sp['labelled_boundaries']} word boundaries "
            f"this file marks with space glyphs, not read off the gap peaks, which "
            f"would have said {sp['fallback_ratio']}. The two populations are NOT "
            f"reliably bimodal -- on justified text they overlap.")
        band = sp.get("safe_band") or []
        if len(band) == 2 and band[0] == band[1]:
            out.append(
                f"The safe band for that ratio is a single bin ({band[0]}): there is "
                f"no margin either way, so treat it as the low end of a sweep, not an "
                f"answer. The score behind it is asymmetric (a glue costs three times "
                f"a split) and it is dominated by the body face, so a second, more "
                f"loosely tracked face -- bold headings are the usual one -- can be "
                f"over-split at this value while the body is correct.")
        out.append(
            "Check the rebuilt text in BOTH directions, because one ratio cannot serve "
            "two faces: tokens longer than 22 letters catch gluing, and a word broken "
            "by a space inside it ('Territor y', 'Ack nowledgments', 'GA Ns') catches "
            "splitting -- look at the headings, they are where it shows. Measured on a "
            "13 pt Times magazine: the recommended 0.09 over-split 10 headings and lost "
            "12 tokens against 0.10, which lost none in either direction.")
    elif sp["measured"]:
        out.append(
            f"Word gaps split cleanly (intra-word peak {sp['intra_word_peak']}, "
            f"inter-word peak {sp['inter_word_peak']} of point size): use "
            f"x_tolerance_ratio {sp['ratio']} when rebuilding text from chars. "
            f"This file labels too few boundaries with space glyphs to score the "
            f"threshold against them, so it is the peak midpoint -- verify by "
            f"counting tokens longer than 22 letters after the rebuild.")
    fu = profile["furniture"]
    if fu.get("detected"):
        pats = fu.get("patterns") or []
        if pats:
            shown = "; ".join(
                f"[{p['region']}] {p['pattern'][:56]!r} on {p['pages']}/"
                f"{fu['sampled_pages']} pages at y {p['y_min']}-{p['y_max']}"
                for p in pats[:6])
            more = (f" (+{len(pats) - 6} more, see --json)"
                    if len(pats) > 6 else "")
            scoped = ("" if fu.get("region_scoped") else
                      " The probe ran page-wide (region: page): on a "
                      "multi-column page, lines welded across a gutter never "
                      "repeat identically, so patterns are under-counted "
                      "here -- pass --columns to scope it (measured on a "
                      "3-column magazine: 1 pattern page-wide, 4 scoped).")
            out.append(
                f"Running furniture found on most pages as {len(pats)} "
                f"repeating pattern(s): {shown}{more}. Drop it by matching "
                "that digit-masked text, NOT by a y cut-off, and NOT by point "
                "size. A cut-off was measured failing in both directions on "
                "one document: of 113 line records above the header band's "
                "lowest edge only 16 were furniture, so cutting there deleted "
                "97 real lines -- and it still missed a DOI line repeating on "
                "18 of 20 pages 13 pt below the cut. header_bottom / "
                f"footer_top ({fu.get('header_bottom')} / "
                f"{fu.get('footer_top')}) are reported geometry, not a "
                f"threshold.{scoped}")
        else:
            out.append(
                "Lines repeat in the header/footer band but no furniture "
                "pattern qualified: nothing repeats at the same height "
                f"(within {_PATTERN_Y_SPREAD} pt) on at least "
                f"{max(_PATTERN_MIN_PAGES, int(fu['sampled_pages'] * _PATTERN_PAGE_SHARE))} "
                "of the sampled pages. Treat header_bottom / footer_top as "
                "geometry to look at, not as a cut-off to filter on -- a "
                "y cut-off was measured deleting 97 real lines on a document "
                "whose furniture it also failed to catch.")
        if fu.get("size_collides_with_body_text"):
            out.append(
                "DO NOT filter furniture by point size: sizes "
                f"{fu['size_collides_with_body_text']} are used BOTH by the "
                "running header/footer and by real body text elsewhere "
                "(a measured document hid its legal chapter this way).")
    reg = profile["regions"]
    tb = profile["tables"]
    if reg["ruled_regions"] and tb["lines"] == 0 and tb["lines_strict"] == 0:
        out.append(
            f"{reg['ruled_regions']} ruled region(s) on {reg['ruled_pages']} "
            "sampled page(s) but extract_tables() finds 0: the tables are "
            "ruled horizontally only. Rebuild them from the rule segment "
            "endpoints via explicit_vertical_lines -- see references/"
            "pdf-to-markdown.md section 3.2b.")
    elif reg["ruled_regions"] and tb["lines"] > tb["lines_strict"] * 2:
        out.append(
            f"'lines' finds {tb['lines']} tables, 'lines_strict' "
            f"{tb['lines_strict']}: the difference is fill-only shading read "
            "as table edges. Compare both before trusting either.")
    if reg["fill_box_pages"]:
        out.append(
            f"Filled boxes on {reg['fill_box_pages']} sampled page(s), colours "
            f"{[c['color'] for c in reg['fill_colors'][:3]]}: typically "
            "callouts (Note/Caution) and code samples. Classify by the "
            "fraction of monospaced characters inside, not by colour alone.")
    li = profile["lists"]
    if li["orphan_marker_lines"]:
        out.append(
            f"{li['orphan_marker_lines']} line(s) hold nothing but a list "
            "marker (a marker set in a different point size falls outside the "
            "line grouping). Merge each with its neighbouring line; "
            "--y-tolerance does not always reach them.")
    if f["icon_font_glyphs"]:
        total = sum(g["count"] for g in f["icon_font_glyphs"])
        out.append(
            f"{total} private-use glyph(s) from icon font(s) "
            f"{[g['family'] for g in f['icon_font_glyphs']]}: they carry no "
            "text and must be dropped, not transliterated.")
    im = profile["images"]
    if im["most_repeated"]:
        top = im["most_repeated"][0]
        if top["placements"] > 20 and max(top["w"], top["h"]) < 24:
            out.append(
                f"A {top['w']}x{top['h']} pt image is placed "
                f"{top['placements']} times: an inline icon (bullet, "
                "navigation chevron, external-link mark), not artwork. Filter "
                "small repeated images out of --extract-images output, and "
                "consider whether it carries meaning the text lost.")
    if f["rotated_chars"]:
        out.append(f"{f['rotated_chars']} rotated character(s): sideways cover "
                   "spines or table headers. Filter on char['upright'].")
    return out


# ---------------------------------------------------------------------- render

def _render(profile) -> str:
    L = []
    d = profile["document"]
    L.append(f"# PDF profile: {d['name']}")
    L.append(f"  {d['pages']} pages, {d['width']} x {d['height']} pt, "
             f"sampled {d['sampled']}")
    if d.get("producer"):
        L.append(f"  producer: {d['producer']}")
    f = profile["fonts_and_sizes"]
    L.append("")
    L.append(f"## Sizes  (body text = {f['body_size']} pt)")
    for s in f["sizes"]:
        sample = f" | {s['sample']}" if s["sample"] else ""
        L.append(f"  {str(s['size']).rjust(5)} pt  {str(s['chars']).rjust(7)} chars  "
                 f"{s['role']:<38}{sample}")
    L.append("")
    L.append("## Fonts")
    for x in f["fonts"]:
        L.append(f"  {x['family']:<34} {str(x['chars']).rjust(7)} chars  "
                 f"{x['style_guess'] or '-'}")
    sp = profile["spacing"]
    L.append("")
    L.append("## Word spacing")
    L.append(f"  recommended x_tolerance_ratio: {sp['ratio']}"
             f"{'  (measured)' if sp['measured'] else '  (default; not measurable)'}")
    if sp.get("source") == "labelled":
        band = sp.get("safe_band") or []
        L.append(f"  scored against {sp['labelled_boundaries']} boundaries the file "
                 f"marks with space glyphs: would glue {sp['false_glue']}, "
                 f"would split {sp['false_split']}")
        # Same length guard as _recommend: today a labelled source always
        # carries [lo, hi], and the two readers of the field must agree about
        # that rather than one of them crashing the report if it ever stops.
        if len(band) == 2:
            L.append(f"  safe band {band[0]}-{band[1]}"
                     f"{'  (one bin wide -- no margin)' if band[0] == band[1] else ''}"
                     f"; the gap peaks alone would have said {sp['fallback_ratio']}")
        else:
            L.append(f"  the gap peaks alone would have said "
                     f"{sp['fallback_ratio']}")
    L.append(f"  gap peaks: intra-word {sp['intra_word_peak']}, "
             f"inter-word {sp['inter_word_peak']} (fraction of point size)")
    L.append(f"  explicit space glyphs in sample: {sp['space_glyphs']}"
             f"{'  (words are positioned, not spaced)' if not sp['space_glyphs'] else ''}")
    fu = profile["furniture"]
    L.append("")
    L.append("## Running header / footer")
    if fu.get("detected"):
        regions = [r["name"] for r in fu.get("regions") or []]
        L.append(f"  region: {', '.join(regions) or _PAGE_REGION}"
                 f"{'' if fu.get('region_scoped') else '  (no --columns; probed page-wide)'}")
        bands = []
        if fu.get("header_bottom") is not None:
            bands.append(f"header ends at y={fu['header_bottom']}")
        if fu.get("footer_top") is not None:
            bands.append(f"footer starts at y={fu['footer_top']}")
        if bands:
            L.append("  " + ", ".join(bands) +
                     "  (reported geometry -- do NOT filter on it)")
        L.append(f"  point sizes: {fu['sizes']}")
        pats = fu.get("patterns") or []
        L.append(f"  {len(pats)} repeating pattern(s) over "
                 f"{fu['sampled_pages']} sampled page(s):")
        for p in pats[:10]:
            L.append(f"    [{p['region']}/{p['band']}] {p['pages']}/"
                     f"{fu['sampled_pages']} pages, y {p['y_min']}-{p['y_max']}"
                     f": {p['pattern'][:64]}")
        if len(pats) > 10:
            L.append(f"    (+{len(pats) - 10} more, see --json)")
    else:
        L.append("  none detected")
    reg = profile["regions"]
    tb = profile["tables"]
    L.append("")
    L.append("## Regions")
    L.append(f"  filled boxes on {reg['fill_box_pages']} pages, "
             f"colours {[c['color'] for c in reg['fill_colors'][:4]]}")
    L.append(f"  ruled rows on {reg['ruled_pages']} pages, "
             f"{reg['ruled_regions']} ruled region(s)")
    L.append(f"  extract_tables(): lines={tb['lines']} "
             f"lines_strict={tb['lines_strict']} text={tb['text']}")
    for sig in reg["column_signatures"][:3]:
        L.append(f"    column signature x={sig['x']}  ({sig['regions']} regions)")
    li = profile["lists"]
    L.append("")
    L.append("## Lists")
    L.append(f"  bullets: {[g['glyph'] for g in li['bullet_glyphs']]}  "
             f"marker x: {li['marker_x']}  indent step: {li['indent_step']}")
    L.append(f"  orphaned marker lines: {li['orphan_marker_lines']}")
    im = profile["images"]
    L.append("")
    L.append("## Images")
    L.append(f"  {im['distinct_images']} distinct, {im['figure_like']} figure-like, "
             f"{im['icon_like']} icon-like")
    for r in im["most_repeated"]:
        L.append(f"    {r['w']}x{r['h']} pt placed {r['placements']}x")
    L.append("")
    L.append("## Recommendations")
    if profile["recommendations"]:
        for i, r in enumerate(profile["recommendations"], 1):
            L.append(f"  {i}. {r}")
    else:
        L.append("  (nothing unusual measured)")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    # First statement, before parse_args: --help is printed by argparse, and
    # argparse does not catch UnicodeEncodeError (CLAUDE.md, CLI I/O encoding).
    install_human_channel()
    parser = _build_parser()
    args = parser.parse_args(argv)
    path: Path = args.INPUT
    try:
        # `is not None`, not truthiness: --columns "" is a spec the caller
        # meant and got wrong, not an absent flag.
        columns = (_parse_columns(args.columns)
                   if args.columns is not None else None)
    except _ColumnSpecError as exc:
        return report_error(str(exc), code=2, error_type="UsageError",
                            json_mode=args.json_errors)
    if not path.exists():
        return report_error(f"Input not found: {path}", code=1,
                            error_type="InputNotFound",
                            json_mode=args.json_errors)
    try:
        pdf = pdfplumber.open(str(path), password=args.password or "")
    except Exception as exc:
        # pdfminer's PDFPasswordIncorrect has an empty str(), so interpolating
        # it produced `Could not open FILE: ` and pointed nobody at --password.
        # Match the class the way pdf_verify_md.py does, and emit the same
        # envelope the other two CLIs emit for the same input.
        if _textlines_is_password_failure(exc):
            return report_error(
                f"PDF is encrypted and could not be opened — supply a correct "
                f"--password: {path}", code=1, error_type="EncryptedPDF",
                json_mode=args.json_errors)
        return report_error(f"Could not open {path}: {exc}", code=1,
                            error_type="InputUnreadable",
                            json_mode=args.json_errors)
    try:
        with pdf:
            pages = tl.sample_pages(pdf.pages, args.pages)
            if not pages:
                return report_error(f"{path} has no pages", code=1,
                                    error_type="InputUnreadable",
                                    json_mode=args.json_errors)
            if columns is not None:
                # Every sampled page, before any work: a spec that is wrong on
                # page 12 is a usage error there too, and finding that out
                # after the profile prints is finding it out too late.
                for number, page in enumerate(pages, 1):
                    _regions_for(page, columns, page_number=number)
            spacing = tl.space_ratio(pdf, sample_pages=min(len(pages), 24))
            ratio = spacing["ratio"]
            first = pages[0]
            meta = getattr(pdf, "metadata", None) or {}
            profile = {
                "document": {
                    "name": path.name,
                    "pages": len(pdf.pages),
                    "sampled": len(pages),
                    "width": round(float(first.width), 1),
                    "height": round(float(first.height), 1),
                    "producer": str(meta.get("Producer") or meta.get("Creator") or ""),
                },
                "spacing": spacing,
                "fonts_and_sizes": _fonts_and_sizes(pages, ratio),
                "furniture": _furniture(pages, ratio, columns),
                "regions": _regions(pages),
                "tables": _tables(pages),
                "lists": _lists(pages, ratio),
                "images": _images(pages),
            }
            profile["recommendations"] = _recommend(profile)
    except _ColumnSpecError as exc:  # the caller's spec, not the document
        return report_error(str(exc), code=2, error_type="UsageError",
                            json_mode=args.json_errors)
    except Exception as exc:  # a profile must never be the thing that breaks
        return report_error(f"Profiling failed on {path}: {exc}", code=1,
                            error_type="ProfileFailed",
                            json_mode=args.json_errors)
    if args.json:
        write_json_stdout(profile, indent=2)
    else:
        write_text_stdout(_render(profile) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

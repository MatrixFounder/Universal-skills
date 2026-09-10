"""Character-level line reconstruction, shared by ``pdf_extract.py --lines``
and ``pdf_profile.py``.

Why this module exists
----------------------
``page.extract_text()`` returns a flat string. That is enough to *read* a page
and not enough to *convert* one: heading level comes from point size, list
nesting from the x coordinate, inline emphasis from the font family, and none
of the three survives the flattening. An agent asked to "compose Markdown from
the dump" therefore had to drop to inline pdfplumber and re-derive the
character arithmetic every time — and re-meet the same three traps, each of
which corrupts text *silently*:

* **A ligature glyph arrives as one char dict per unicode point.** ``fi`` is a
  single glyph whose ``/ToUnicode`` maps to two characters, and pdfplumber
  emits two char dicts for it, both carrying ``"fi"`` and both with the *same*
  bbox. Concatenating ``char["text"]`` turns "Profiles" into "Profifiles" and
  "Offers" into "Offffers". Measured on an Antenna House export; any
  professionally typeset PDF has ligatures. :func:`dedupe`.

* **Word spacing is frequently positional.** Producers routinely advance the
  text matrix instead of emitting a space glyph, so text rebuilt from chars
  alone reads ``Formoreinformation,see``. The split threshold has to be
  font-relative (pdfplumber's ``x_tolerance_ratio`` rule); :func:`space_ratio`
  measures the document's own distribution rather than guessing. The two
  populations are NOT reliably bimodal, which is the trap: on a justified file
  they overlap, and the midpoint between the peaks then falls inside the
  inter-word population's own left tail and welds prose into one token. So the
  threshold is scored against the word boundaries the file itself labels with
  space glyphs wherever it labels enough of them, and only falls back to the
  peak split when it does not.

* **A marker set in a different point size lands on its own line.** Line
  grouping is an *absolute* y tolerance, so a 12 pt bullet against 9 pt body
  text falls outside it. The line is reported with ``marker_only`` set rather
  than merged: merging is a judgement about which item the marker belongs to,
  and this module records what the page holds.

Everything here is producer-agnostic. Font *roles* (which family means bold,
which point size is an h2) are deliberately NOT decided — the raw family and
size ride along on every run so the caller can map them, and ``pdf_profile.py``
reports the inventory to map from.
"""

from __future__ import annotations

import collections
import math
import re

# Subset prefixes ("IWLRHM+BentonSans-Book") carry no information about the
# face and differ per file, so they are stripped everywhere a family is named.
_SUBSET = re.compile(r"^[A-Z]{6}\+")

# Conservative, token-based style detection. "Medium" is deliberately absent:
# it is the regular weight in some families and an emphasis weight in others,
# so it is reported as its own family and left for the caller to map.
_MONO_TOKENS = (
    "courier", "mono", "consol", "menlo", "inconsolata", "sourcecodepro",
    "firacode", "jetbrains", "ibmplexmono", "andale", "lucidaconsole",
    "operatormono", "hack", "terminus",
)
_BOLD_TOKENS = ("bold", "black", "heavy", "semibold", "demibold", "extrabold",
                "ultrabold")
_ITALIC_TOKENS = ("italic", "oblique")

# Marker glyphs that open a list item. Hyphen/asterisk are excluded on purpose:
# they are ordinary punctuation far more often than they are bullets.
BULLET_CHARS = "•●▪◦▶‣⁃·■○"

_PUA_RANGES = ((0xE000, 0xF8FF), (0xF0000, 0xFFFFD), (0x100000, 0x10FFFD))

#: Fallback when a document offers too little evidence to measure its own
#: word-gap threshold. Matches ``pdf_extract.py``'s ``x_tolerance_ratio``.
DEFAULT_SPACE_RATIO = 0.15

# Line-ending hyphens. The rate counts only the three a typesetter breaks on;
# the verdict has to recognise all five, U+00AD and U+2012 included.
_HYPHEN_RATE_CHARS = "-\u2010\u2011"
_HYPHENS = "-\u00ad\u2010\u2011\u2012"
_SOFT_HYPHEN = "\u00ad"
_KEEP_HYPHENS = "\u2010\u2011\u2012"
# A stem carrying one of these is an identifier or a URL rather than a word,
# so its hyphen is content: ``sap.hana-`` + ``app`` must not lose it.
_STEM_PUNCT = "./:@"
_WORD_START = re.compile(r"\w")
_WORD_RUN = re.compile(r"\w*")

#: Below this many labelled gaps in either population the labelled pass does
#: not run: a file that positions nearly every word cannot be scored on the
#: handful of boundaries it does mark.
_LABELLED_MIN_SAMPLES = 200

#: A document hyphenating fewer lines than this is not hyphenating: a line
#: ending on a hyphen is then a real hyphen, and joining it away corrupts the
#: word. See :func:`hyphenation_rate` for the two measurements behind it.
HYPHENATION_MIN_RATE = 0.02


def family(fontname) -> str:
    """``"IWLRHM+BentonSans-Book"`` -> ``"BentonSans-Book"``."""
    return _SUBSET.sub("", str(fontname or ""))


def is_pua(text: str) -> bool:
    """True for a private-use codepoint — an icon-font glyph with no textual
    meaning (SAP-icons, Font Awesome, Material Icons). Such a glyph must be
    dropped from text, never transliterated: its codepoint says nothing."""
    if len(text) != 1:
        return False
    o = ord(text)
    return any(lo <= o <= hi for lo, hi in _PUA_RANGES)


def classify_style(fontname) -> str:
    """``'mono'`` / ``'bold-italic'`` / ``'bold'`` / ``'italic'`` / ``''``.

    Name-based by necessity — the PDF carries no semantic weight — and
    deliberately conservative, so a caller that needs a family-specific rule
    (a "Medium" face used for UI labels, say) can key off the raw family that
    every run carries instead of fighting a guess made here.

    Mono still wins outright and returns immediately: a monospaced face is a
    code face first, and its weight is a detail of the code style. Bold and
    italic are then tested *independently*, because testing bold first and
    returning dropped the italic on the floor: one measured document sets
    3045 characters in ``TimesNewRomanPS-BoldItalicMT``, every one of which
    reported ``'bold'``, so a caller mapping ``style == 'italic'`` to ``*…*``
    lost every bold-italic run and nothing said so. ``'bold-italic'`` is a
    NEW value, never a redefinition of ``'bold'`` — a call-site written as
    ``== "bold"`` therefore stops matching visibly instead of being silently
    re-classified.

    The return stays a plain ``str``. :func:`line_runs` merges adjacent runs
    by comparing ``style`` for equality, and a set or a list would quietly
    stop merging them.
    """
    low = family(fontname).lower()
    if any(t in low for t in _MONO_TOKENS):
        return "mono"
    bold = any(t in low for t in _BOLD_TOKENS)
    italic = any(t in low for t in _ITALIC_TOKENS)
    if bold and italic:
        return "bold-italic"
    if bold:
        return "bold"
    if italic:
        return "italic"
    return ""


def dedupe(chars):
    """Drop the duplicate char dicts pdfplumber emits for a ligature glyph.

    One glyph mapping to N unicode points yields N identical dicts (same text,
    same bbox). Position is the discriminator: two *real* characters can repeat
    a letter but cannot occupy the same box.
    """
    out = []
    for c in chars:
        if out:
            p = out[-1]
            if (c.get("text") == p.get("text")
                    and abs(c["x0"] - p["x0"]) < 0.15
                    and abs(c["x1"] - p["x1"]) < 0.15
                    and abs(c["top"] - p["top"]) < 0.15):
                continue
        out.append(c)
    return out


def upright(chars):
    """Only the horizontal text. Rotated glyphs (cover spines, sideways table
    headers) share a line's y range without belonging to it."""
    return [c for c in chars if c.get("upright", True)]


def hyphenation_rate(texts) -> float:
    """Share of lines ending on a hyphen — *does this document hyphenate?*

    Accepts one string or an iterable of them (page texts); blank lines do not
    count. Only U+002D, U+2010 and U+2011 count as evidence: U+00AD is
    discretionary by definition, and U+2012 FIGURE DASH is punctuation, so
    neither says anything about the typesetter's line-breaking.

    The two measured magazine PDFs sit two orders of magnitude apart on the
    ASCII-only reading (189x) and more than one order apart on the figure this
    function returns (18x), which is what makes :data:`HYPHENATION_MIN_RATE` an
    easy threshold rather than a tuned one: **doc A 0.1322** (208 of 1573 lines
    end on U+002D) against **doc B 0.0007** — that second figure is the count
    this function replaces, ASCII hyphens only (1 line of 1418); counting the
    family this function actually counts, doc B measures 0.0073 (13 lines of
    1778 ``extract_text`` lines). Both readings of doc B are far below the
    threshold and far below doc A, so the verdict is the same either way; the
    pair is named here in full because only one of the two numbers is what this
    code returns.

    Rounded to four places so the figures above are reproducible verbatim.
    """
    if isinstance(texts, str):
        texts = [texts]
    total = 0
    ends = 0
    for text in texts:
        for line in str(text or "").split("\n"):
            if not line.strip():
                continue
            total += 1
            if line[-1] in _HYPHEN_RATE_CHARS:
                ends += 1
    return round(ends / total, 4) if total else 0.0


def hyphen_verdict(head_line, next_line, *, hyphenating=True) -> str:
    r"""What to do with the hyphen ending ``head_line``, before ``next_line``.

    ``'drop'`` join without the hyphen, ``'keep'`` join with it, ``'space'``
    do not join at all, ``'report'`` *not a decision* — the caller must show
    the site to a human. Rules, first match wins:

    1. no final hyphen on ``head_line``, or ``next_line`` does not open on a
       word character -> ``'space'``;
    2. U+00AD SOFT HYPHEN -> ``'drop'`` (discretionary by definition);
    3. U+2010 / U+2011 / U+2012 -> ``'keep'``;
    4. the stem before the hyphen contains ``.``, ``/``, ``:`` or ``@``
       -> ``'report'`` (an identifier or a URL, where the hyphen is content);
    5. ``hyphenating`` is False -> ``'keep'``;
    6. otherwise -> ``'drop'``.

    Rule 3 is the whole point. Testing ``endswith("-")`` reads doc A right by
    luck — it ends 208 lines on U+002D and none on anything else — and reads
    doc B wrong 12 times out of 13, because doc B breaks on U+2011
    NON-BREAKING HYPHEN, which is exactly the character a typesetter emits to
    say *this hyphen is not a break*. Joining it away produced ``o‑ end``,
    ``h‑ order``, ``8‑ 023`` in shipped Markdown. The class is invisible to
    word-coverage verification by construction (``\w{3,}`` does not match a
    hyphen, so both spellings tokenise identically), so the verdict is the
    only guard there is.

    On doc B all 13 sites come out right: rule 3 answers the 12 U+2011 breaks,
    and the single U+002D is ``ti-i-i-i-…``, which rule 5 also joins with its
    hyphen because the document does not hyphenate.
    """
    head = head_line or ""
    if not head or head[-1] not in _HYPHENS:
        return "space"
    if not _WORD_START.match(next_line or ""):
        return "space"
    hyphen = head[-1]
    if hyphen == _SOFT_HYPHEN:
        return "drop"
    if hyphen in _KEEP_HYPHENS:
        return "keep"
    if any(ch in _stem_of(head) for ch in _STEM_PUNCT):
        return "report"
    if not hyphenating:
        return "keep"
    return "drop"


def dehyphenate(text, *, hyphenating=True) -> str:
    """Rejoin words split across a line break, per :func:`hyphen_verdict`.

    ``'report'`` is treated as ``'keep'`` here — the conservative reading, and
    the behaviour this replaces. A caller that wants to see those sites rather
    than guess at them asks :func:`hyphen_sites` for them.
    """
    out: list[str] = []
    for line in str(text or "").split("\n"):
        if out:
            verdict = hyphen_verdict(out[-1], line, hyphenating=hyphenating)
            if verdict == "drop":
                out[-1] = out[-1][:-1] + line
                continue
            if verdict in ("keep", "report"):
                out[-1] = out[-1] + line
                continue
        out.append(line)
    return "\n".join(out)


def hyphen_sites(text) -> list[dict]:
    """The line-break hyphens :func:`dehyphenate` could not decide alone.

    One dict per site — ``line_no`` (1-based, the line carrying the hyphen),
    ``hyphen`` (``"U+2011"``), ``stem``, ``tail``, ``verdict`` — for the
    ``'report'`` and ``'space'`` verdicts only, i.e. every site where the
    hyphen is content rather than typesetting, or where the join does not
    happen at all. Neither verdict depends on ``hyphenating`` (rule 5 can only
    produce ``'keep'``), which is why this takes no such argument.
    """
    lines = str(text or "").split("\n")
    sites: list[dict] = []
    for i, line in enumerate(lines):
        if not line or line[-1] not in _HYPHENS:
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        verdict = hyphen_verdict(line, nxt)
        if verdict not in ("report", "space"):
            continue
        sites.append({
            "line_no": i + 1,
            "hyphen": "U+%04X" % ord(line[-1]),
            "stem": _stem_of(line),
            "tail": _WORD_RUN.match(nxt).group(0),
            "verdict": verdict,
        })
    return sites


def _stem_of(head_line: str) -> str:
    """The token the trailing hyphen hangs off, hyphen excluded."""
    return re.split(r"[\s(\[]", head_line[:-1])[-1]


def space_ratio(pdf, *, sample_pages=24, default=DEFAULT_SPACE_RATIO) -> dict:
    """Measure this document's word-gap threshold instead of assuming one.

    Gaps between consecutive characters, normalised by point size, form two
    populations: intra-word (kerning, ~0.0) and inter-word (~0.2-0.3). Where
    the file *labels* its own word boundaries — it emits space glyphs and
    positions the rest — the two populations can be read off directly instead
    of inferred, and the threshold is then chosen against counted mistakes.
    That labelled pass is the primary answer; :func:`_valley`, which splits
    the two peaks, is the fallback for a file that labels too little.

    The labelled pass exists because the peak formula lands on the wrong side
    of the boundary on a justified document: it returned 0.125 for a file
    where the welded lines' own inter-word gaps run 1.57-1.60 pt against that
    0.125 * 13 pt = 1.625 pt threshold, so ``page_lines`` welded prose into
    ``Theflyingfishserveasanallegoryfortranscendingaphilosophical``. Those two
    lines are not the extreme: the same file's labelled inter-word population
    reaches down to 0.095 (1.24 pt at 13 pt) and puts 69 of its 11888
    boundaries at or below 0.125. Half an inter-word mode of 0.25 is a fine
    estimate for a file whose inter-word population starts at 0.147 and a
    broken one for that file — and the formula cannot tell the two apart,
    because it never looks below the peak.

    Returns the measurement AND the evidence, so a caller can see why the
    threshold is what it is (and ``pdf_profile.py`` can print it):
    ``source`` names which pass answered, ``false_glue``/``false_split`` are
    the labelled mistakes the returned ratio makes, ``safe_band`` is the
    plateau it was picked from, and ``fallback_ratio`` is what the peak
    formula would have said — so the change from one to the other is one
    diff to audit rather than an invisible re-tuning.
    """
    pages = _sample(pdf.pages, sample_pages)
    gaps: collections.Counter = collections.Counter()
    space_glyphs = 0
    total_chars = 0
    inter: list[float] = []
    intra: list[float] = []
    for page in pages:
        try:
            # Counted on page.chars, NOT on the line chars: the word extractor
            # consumes space glyphs, so a line-based count always reports zero
            # and would claim every document positions its words.
            page_chars = dedupe(upright(page.chars))
            space_glyphs += sum(1 for c in page.chars if c.get("text") == " ")
            lines = page.extract_text_lines()
        except Exception:
            continue
        _label_gaps(page_chars, inter, intra)
        for line in lines:
            cs = dedupe(upright(line.get("chars") or []))
            total_chars += len(cs)
            for a, b in zip(cs, cs[1:]):
                if a.get("text") == " " or b.get("text") == " ":
                    continue
                size = max(float(a.get("size") or 0), float(b.get("size") or 0))
                if size <= 0:
                    continue
                gaps[round((b["x0"] - a["x1"]) / size, 2)] += 1
    peaks = _valley(gaps, default)
    out = {
        "ratio": peaks["ratio"],
        "measured": peaks["measured"],
        "intra_word_peak": peaks["intra_peak"],
        "inter_word_peak": peaks["inter_peak"],
        "space_glyphs": space_glyphs,
        "sampled_chars": total_chars,
        "top_gaps": gaps.most_common(6),
        "source": "peaks" if peaks["measured"] else "default",
        "safe_band": None,
        "false_glue": None,
        "false_split": None,
        "labelled_boundaries": len(inter),
        "fallback_ratio": peaks["ratio"],
    }
    labelled = _labelled_split(inter, intra)
    if labelled is not None:
        out.update(labelled)
        out["measured"] = True
        out["source"] = "labelled"
    return out


def _label_gaps(chars, inter, intra) -> None:
    """Sort this page's character gaps into *known* word boundaries and *known*
    word interiors, using the file's own space glyphs as the labels.

    Walks the characters in stream order and compares each non-space glyph
    with the previous one on the same line (|dtop| < 1.0 pt): the gap goes to
    ``inter`` when a space glyph stood between them and to ``intra`` when none
    did. Gaps below ``-0.5 * size`` are dropped as a line or column restart
    rather than kerning. Nothing here is a threshold — this is the ground
    truth a threshold is later scored against.

    "Space glyph" means U+0020 only, the same test the peak pass uses. A
    NO-BREAK SPACE is therefore labelled as word interior, which is the right
    answer for what the ratio governs: that glyph carries its own text, so
    :func:`line_runs` never has to re-insert a space around it. Measured cost
    of the choice on doc B: 84 gaps of 8010 move between the populations and
    the chosen ratio does not move.
    """
    prev = None
    spaced = False
    for c in chars:
        if c.get("text") == " ":
            spaced = True
            continue
        if prev is not None and abs(float(c["top"]) - float(prev["top"])) < 1.0:
            size = max(float(c.get("size") or 0), float(prev.get("size") or 0))
            if size > 0:
                gap = float(c["x0"]) - float(prev["x1"])
                if gap > -0.5 * size:
                    (inter if spaced else intra).append(round(gap / size, 3))
        prev = c
        spaced = False


def _labelled_split(inter, intra):
    """Pick the ratio that makes the fewest labelled mistakes, or ``None``.

    ``None`` when either population is thinner than
    :data:`_LABELLED_MIN_SAMPLES` — a file that positions nearly all of its
    words labels too few boundaries to be scored on, and must fall back to the
    peaks. (A committed fixture labels 6 boundaries; it correctly falls back
    and its measured ratio does not move.)

    Over a 0.040-0.300 grid: ``false_glue`` is a labelled boundary the ratio
    would swallow, ``false_split`` a word interior it would break open. Glue
    is weighted three times a split because it is the unrecoverable failure —
    a split word is still two readable tokens and a verifier finds it, while
    ``Theflyingfish…`` is gone. The answer is the middle of the WIDEST plateau
    of minimum cost, not the first minimum: the widest plateau is the one
    furthest from both populations, and its width is itself the report — a
    one-bin plateau says the document has no comfortable threshold. That
    midpoint is rounded to two places for a readable recommendation and then
    clamped back inside the plateau, so ``ratio`` is always a value the scan
    itself endorsed: without the clamp a one-bin plateau at 0.095 published
    0.10, one bin past the band it names and — on a real document — twice the
    glue.
    """
    if len(inter) < _LABELLED_MIN_SAMPLES or len(intra) < _LABELLED_MIN_SAMPLES:
        return None
    grid = [round(0.040 + i * 0.005, 3) for i in range(53)]
    cost = {}
    for r in grid:
        glue = sum(1 for g in inter if g <= r)
        split = sum(1 for g in intra if g > r)
        cost[r] = 3 * glue + split
    best = min(cost.values())
    runs: list[list[float]] = []
    for r in grid:
        if cost[r] == best:
            if runs and abs(r - runs[-1][-1] - 0.005) < 1e-9:
                runs[-1].append(r)
            else:
                runs.append([r])
    widest = max(runs, key=len)          # ties keep the lower band: less glue
    lo, hi = widest[0], widest[-1]
    # Clamped back into the plateau: the midpoint is rounded to 2 places for a
    # readable recommendation, but the grid is 0.005, so a one-bin plateau on a
    # half step (0.095) rounds to 0.10 -- one full bin past ``hi``, and by
    # construction the next bin costs strictly more, in the glue direction.
    ratio = min(hi, max(lo, _round_half_up((lo + hi) / 2.0, 2)))
    return {
        "ratio": ratio,
        "safe_band": [lo, hi],
        "false_glue": sum(1 for g in inter if g <= ratio),
        "false_split": sum(1 for g in intra if g > ratio),
        "labelled_boundaries": len(inter),
    }


def _round_half_up(value: float, places: int) -> float:
    """Half-up rounding. ``round()`` is half-to-even on a value that is exactly
    representable and unpredictable on one that is not; a plateau midpoint
    lands on a half step often enough (0.0975) for that to matter."""
    scale = 10 ** places
    return math.floor(value * scale + 0.5) / scale


def _valley(gaps, default):
    """Split the two gap populations at the valley between their peaks.

    Taking ``max(intra)`` and ``min(inter)`` looked right on one document and
    collapsed on the next: a single stray gap anywhere in the empty band
    drags the estimate onto it, and a cover page or a footnote supplies one.
    Peaks carry mass, so they survive outliers; the minimum-count bin between
    them is the threshold.
    """
    if not gaps:
        return {"ratio": default, "measured": False,
                "intra_peak": None, "inter_peak": None}
    near = {g: n for g, n in gaps.items() if 0.0 <= g <= 0.05}
    far = {g: n for g, n in gaps.items() if 0.08 <= g <= 0.45}
    if not near or not far:
        return {"ratio": default, "measured": False,
                "intra_peak": max(near, key=near.get) if near else None,
                "inter_peak": max(far, key=far.get) if far else None}
    intra_peak = max(near, key=near.get)
    inter_peak = max(far, key=far.get)
    # A word-gap population that is a rounding error is not a population: the
    # document spaces its words with real glyphs and needs no split threshold.
    if far[inter_peak] < near[intra_peak] * 0.02 or inter_peak <= intra_peak:
        return {"ratio": default, "measured": False,
                "intra_peak": intra_peak, "inter_peak": inter_peak}
    # Split at half the word-gap mode. Peak-relative rather than
    # valley-seeking: the band between the populations is only *mostly* empty,
    # and three files from one producer picked three different valleys
    # (0.06 / 0.195 / 0.3) because a handful of stray bins moved the minimum.
    # Half the inter-word mode is far from both populations and stable.
    ratio = inter_peak / 2.0
    # ... but never below the bulk of the kerning gaps, for a face with loose
    # tracking where the two populations sit closer together.
    ratio = max(ratio, _percentile(near, 0.99) + 0.01)
    ratio = min(max(round(ratio, 3), 0.06), 0.30)
    return {"ratio": ratio, "measured": True,
            "intra_peak": intra_peak, "inter_peak": inter_peak}


def _percentile(counted: dict, q: float) -> float:
    """Weighted percentile over a {value: count} histogram."""
    if not counted:
        return 0.0
    total = sum(counted.values())
    target = total * q
    seen = 0
    for value in sorted(counted):
        seen += counted[value]
        if seen >= target:
            return value
    return max(counted)


def modal(values):
    counts = collections.Counter(v for v in values if v is not None)
    return counts.most_common(1)[0][0] if counts else None


def line_runs(chars, *, ratio=DEFAULT_SPACE_RATIO, links=()):
    """Ordered style runs for one line: ``{text, font, size, style, uri}``.

    A run breaks on a change of style, family, or covering link. Spaces absent
    from the character stream are re-inserted where the gap exceeds
    ``ratio * size`` — see :func:`space_ratio` for where ``ratio`` comes from.
    """
    runs: list[dict] = []
    prev = None
    for c in dedupe(chars):
        text = c.get("text") or ""
        if is_pua(text):
            prev = c                       # keeps the gap arithmetic honest
            continue
        if prev is not None and runs:
            size = max(float(c.get("size") or 0), float(prev.get("size") or 0))
            gap = c["x0"] - prev["x1"]
            if size > 0 and gap > ratio * size and not runs[-1]["text"].endswith(" "):
                runs[-1]["text"] += " "
        prev = c
        uri = _uri_at(c, links)
        fam = family(c.get("fontname"))
        style = classify_style(fam)
        size = round(float(c.get("size") or 0), 1)
        if (runs and runs[-1]["font"] == fam and runs[-1]["style"] == style
                and runs[-1]["uri"] == uri and runs[-1]["size"] == size):
            runs[-1]["text"] += text
        else:
            runs.append({"text": text, "font": fam, "size": size,
                         "style": style, "uri": uri})
    for r in runs:
        r["text"] = re.sub(r"[ \t]+", " ", r["text"])
    return [r for r in runs if r["text"].strip() or r["text"] == " "]


def _uri_at(char, links):
    if not links:
        return None
    cx = (char["x0"] + char["x1"]) / 2.0
    cy = (char["top"] + char["bottom"]) / 2.0
    for link in links:
        x0, top, x1, bottom = link["bbox"]
        if x0 - 1 <= cx <= x1 + 1 and top - 1 <= cy <= bottom + 1:
            return link["uri"]
    return None


def runs_text(runs) -> str:
    return re.sub(r"[ \t]+", " ", "".join(r["text"] for r in runs)).strip()


def page_lines(page, *, ratio=DEFAULT_SPACE_RATIO, y_tolerance=None, links=()):
    """Every horizontal text line on the page, with the data composition needs.

    Each record: ``text`` (spacing repaired, ligatures deduped), ``bbox``,
    modal ``size`` and ``font``, the ``styles`` present, ``marker_only`` (a
    line holding nothing but a list marker — see the module docstring), and
    ``runs`` *only when the line is not uniform*: a single-style line without
    links is fully described by ``text``/``font``/``size``, and emitting runs
    for it would double the size of a large dump for no information.
    """
    kwargs = {}
    if y_tolerance is not None:
        kwargs["y_tolerance"] = y_tolerance
    try:
        raw = page.extract_text_lines(**kwargs)
    except Exception:
        return []
    out = []
    for line in raw:
        chars = dedupe(upright(line.get("chars") or []))
        if not chars:
            continue
        runs = line_runs(chars, ratio=ratio, links=links)
        text = runs_text(runs)
        if not text:
            continue
        body = [c for c in chars
                if (c.get("text") or "").strip()
                and (c.get("text") not in BULLET_CHARS)
                and not is_pua(c.get("text") or "")]
        sizes = [round(float(c.get("size") or 0), 1) for c in body] or \
                [round(float(c.get("size") or 0), 1) for c in chars]
        fonts = [family(c.get("fontname")) for c in body] or \
                [family(c.get("fontname")) for c in chars]
        styles = sorted({r["style"] for r in runs if r["style"]})
        record = {
            "text": text,
            "bbox": [round(float(line["x0"]), 2), round(float(line["top"]), 2),
                     round(float(line["x1"]), 2), round(float(line["bottom"]), 2)],
            "size": modal(sizes),
            "font": modal(fonts),
            # len == 1 first: `in` on a str is substring membership, so a
            # line reading '▪◦' -- any 2+ character slice of the literal --
            # was reported as a bare list marker.
            "marker_only": len(text) == 1 and text in BULLET_CHARS,
        }
        if styles:
            record["styles"] = styles
        if len(runs) > 1 or any(r["uri"] for r in runs):
            record["runs"] = runs
        out.append(record)
    return out


def rule_rows(page, *, max_rows=400):
    """Horizontal rules grouped by y, each with the x boundaries of its
    segments — the column signature of a ruled table.

    This is the single most useful geometric fact about a typeset table and it
    is invisible in a text dump. Producers that rule rows but not columns
    (common in technical manuals) defeat *both* ``extract_tables`` strategies:
    ``lines`` needs intersecting edges and finds none. The segment endpoints,
    however, ARE the column boundaries — feed them to
    ``explicit_vertical_lines`` and the table extracts exactly. A row whose
    cells are vertically merged rules only the columns it divides, so its
    signature is a *subset* of the table's.
    """
    try:
        segments = [l for l in page.lines
                    if abs(l["top"] - l["bottom"]) < 0.8 and (l["x1"] - l["x0"]) > 3]
    except Exception:
        return []
    grouped: dict = collections.defaultdict(list)
    for seg in segments:
        grouped[round(float(seg["top"]), 1)].append(seg)
    rows = []
    for y in sorted(grouped)[:max_rows]:
        segs = grouped[y]
        xs = sorted({round(float(v), 1)
                     for s in segs for v in (s["x0"], s["x1"])})
        rows.append({
            "y": y,
            "x": merge_close(xs),
            "segments": len(segs),
            "width": round(max(float(s.get("linewidth") or 0) for s in segs), 2),
        })
    return rows


def merge_close(values, tol=2.0):
    """Collapse coordinates that differ only by a hairline join.

    Adjacent rule segments share a boundary reported as 184.2 on one and 184.3
    on the next; left unmerged the two values look like a one-point-wide column
    and every signature comparison against the table fails.
    """
    if not values:
        return []
    out = [values[0]]
    for v in values[1:]:
        if v - out[-1] > tol:
            out.append(v)
    return out


def fill_boxes(page, *, min_width=40.0, min_height=6.0, max_boxes=60):
    """Filled rectangles — the geometry behind callout blocks and code samples.

    A shaded box is how typeset documents mark a Note, a Caution or a code
    sample, and the fill colour separates the kinds. Reported as geometry, not
    as a verdict: which colour means what is a per-producer fact that
    ``pdf_profile.py`` inventories and the caller decides.
    """
    out = []
    try:
        rects = page.rects
    except Exception:
        return []
    for r in rects:
        if not r.get("fill"):
            continue
        if (r["x1"] - r["x0"]) < min_width or (r["bottom"] - r["top"]) < min_height:
            continue
        out.append({
            "bbox": [round(float(r["x0"]), 2), round(float(r["top"]), 2),
                     round(float(r["x1"]), 2), round(float(r["bottom"]), 2)],
            "color": _color(r.get("non_stroking_color")),
            "stroke": bool(r.get("stroke")),
        })
        if len(out) >= max_boxes:
            break
    return out


def _color(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return [round(float(value), 3)]
    try:
        return [round(float(v), 3) for v in value][:4]
    except (TypeError, ValueError):
        return None


def _sample(pages, count):
    """Evenly spaced sample of exactly ``count`` pages that ALWAYS keeps the
    first and last few.

    Front matter carries the title and the table of contents; back matter
    carries appendices and legal text. A measured document set its legal
    chapter in the same point size as its page footer, and a purely even
    sample missed those pages -- so the profile could not warn that filtering
    furniture by size would delete a chapter. The tails are cheap insurance.

    Exactly ``count``, because the caller measures per sampled page and a
    profile that says "6" must have read 6: the edge indices and the evenly
    spaced ones both claim index 0, and the union used to swallow the
    duplicate -- ``count`` of 1 returned 2 pages, 24 returned 21. The evenly
    spaced pages are therefore drawn from the indices the edges did not
    already take. ``count`` of 0 or ``None`` means every page; a negative
    count is a caller bug, rejected by the CLI parser rather than read here as
    another spelling of 0.
    """
    pages = list(pages)
    if count is None or count <= 0 or len(pages) <= count:
        return pages
    edge = min(3, max(1, count // 8))
    keep = set(range(min(edge, len(pages))))
    keep |= set(range(max(0, len(pages) - edge), len(pages)))
    while len(keep) > count:             # count below 2 * edge: the head wins
        keep.discard(max(keep))
    inner = [i for i in range(len(pages)) if i not in keep]
    need = count - len(keep)
    if need > 0 and inner:
        # need < len(inner) here (count < len(pages)), so the step is > 1 and
        # int(i * step) is strictly increasing: exactly `need` new indices.
        step = len(inner) / float(need)
        keep |= {inner[int(i * step)] for i in range(need)}
    return [pages[i] for i in sorted(keep)]


def sample_pages(pages, count):
    """Evenly spaced sample — public alias used by ``pdf_profile.py``."""
    return _sample(pages, count)

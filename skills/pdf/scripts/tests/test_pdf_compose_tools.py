"""Tests for the PDF→Markdown composition toolchain.

Covers the pieces added after a 1206-page dogfood run showed an agent
re-deriving the same character arithmetic on every document:

* ``_textlines``      -- ligature dedupe, measured word spacing, style runs,
                         rule signatures, and the line-ending hyphen family;
* ``pdf_extract``     -- the ``--lines`` line-level view and the guarantee
                         that a dump taken WITHOUT the flag is unchanged; the
                         column probe's geometry; what ``--extract-images``
                         does and does not promise;
* ``pdf_profile``     -- the report's furniture patterns, the ``--columns``
                         region grammar, and the recommendations it refuses
                         to make;
* ``pdf_verify_md``   -- token coverage of a conversion, and the
                         normalisation that keeps its report readable;
* ``SKILL.md`` and ``references/pdf-to-markdown.md`` -- the handful of claims
                         those documents make that were measured false, which
                         no other test in this repository covers.

Several tests here build their PDF in memory with reportlab rather than adding
a fixture: the page exists to make one measurement visible, and a page whose
construction sits three lines above the assertion cannot drift away from what
the assertion claims.

Run:
    cd skills/pdf/scripts
    ./.venv/bin/python -m unittest tests.test_pdf_compose_tools -v
"""

from __future__ import annotations

import collections
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import _textlines as tl  # noqa: E402
import pdf_extract  # noqa: E402
import pdf_profile as profile  # noqa: E402
import pdf_verify_md as verify  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PY = SCRIPTS_DIR / ".venv" / "bin" / "python"
EXTRACT = SCRIPTS_DIR / "pdf_extract.py"
PROFILE = SCRIPTS_DIR / "pdf_profile.py"
VERIFY = SCRIPTS_DIR / "pdf_verify_md.py"


def run(script, *args):
    return subprocess.run([str(PY), str(script), *map(str, args)],
                          capture_output=True, text=True)


def char(text, x0, x1, *, top=100.0, size=10.0, font="ABCDEF+Test", up=True):
    return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": top + size,
            "size": size, "fontname": font, "upright": up}


# --------------------------------------------------------------- _textlines

class TestLigatureDedupe(unittest.TestCase):
    """pdfplumber emits one char dict per unicode point of a ligature glyph;
    concatenating them turns 'Profiles' into 'Profifiles'."""

    def test_duplicate_bbox_pair_collapses(self):
        chars = [char("Pro", 0, 18), char("fi", 18, 23), char("fi", 18, 23),
                 char("les", 23, 40)]
        self.assertEqual("".join(c["text"] for c in tl.dedupe(chars)),
                         "Profiles")

    def test_real_repeated_letter_survives(self):
        """Two genuine characters can repeat but cannot share a box."""
        chars = [char("l", 0, 5), char("l", 5, 10)]
        self.assertEqual(len(tl.dedupe(chars)), 2)


class TestPositionalSpacing(unittest.TestCase):
    """Producers advance the text matrix instead of emitting a space glyph."""

    def test_wide_gap_becomes_a_space(self):
        chars = [char("For", 0, 15), char("more", 18, 40)]   # 3 pt gap @10 pt
        self.assertEqual(tl.runs_text(tl.line_runs(chars, ratio=0.15)),
                         "For more")

    def test_kerning_gap_does_not(self):
        chars = [char("Fo", 0, 10), char("r", 10.5, 15)]
        self.assertEqual(tl.runs_text(tl.line_runs(chars, ratio=0.15)), "For")

    def test_pua_glyph_is_dropped_but_still_spaces(self):
        """An icon glyph carries no text, yet it separates the words it sits
        between — dropping it must not glue them."""
        chars = [char("see", 0, 15), char("", 18, 27), char("Note", 30, 50)]
        self.assertEqual(tl.runs_text(tl.line_runs(chars, ratio=0.15)),
                         "see Note")


class TestStyleRuns(unittest.TestCase):
    def test_runs_split_on_family_and_carry_it(self):
        chars = [char("plain ", 0, 30, font="ABCDEF+Sans"),
                 char("bold", 30, 50, font="ABCDEF+Sans-Bold")]
        runs = tl.line_runs(chars)
        self.assertEqual([r["style"] for r in runs], ["", "bold"])
        self.assertEqual(runs[1]["font"], "Sans-Bold")

    def test_medium_is_not_guessed_as_bold(self):
        """'Medium' is the regular weight in some families and emphasis in
        others: it is reported as its own family, never silently bolded."""
        self.assertEqual(tl.classify_style("ABCDEF+BentonSans-Medium"), "")
        self.assertEqual(tl.classify_style("ABCDEF+BentonSans-Bold"), "bold")
        self.assertEqual(tl.classify_style("Courier"), "mono")

    def test_classify_style_learns_bold_italic(self):
        """Testing bold first and returning dropped the italic on the floor:
        one measured document sets 3045 characters in a BoldItalic face, all
        of which reported 'bold', so a caller mapping style == 'italic' to
        *...* lost every bold-italic run and nothing said so."""
        self.assertEqual(tl.classify_style("TimesNewRomanPS-BoldItalicMT"),
                         "bold-italic")
        self.assertEqual(tl.classify_style("ABCDEF+Helvetica-BoldOblique"),
                         "bold-italic")
        self.assertEqual(tl.classify_style("SomeSemiBoldOblique"), "bold-italic")
        # Mono still wins outright: a monospaced face is a code face first.
        self.assertEqual(tl.classify_style("Courier-BoldOblique"), "mono")
        # A plain str, never a set or a list: line_runs merges adjacent runs
        # by comparing `style` for equality and would silently stop merging.
        self.assertIsInstance(tl.classify_style("TimesNewRomanPS-BoldItalicMT"),
                              str)

    def test_classify_style_single_axis_values_are_unchanged(self):
        """'bold-italic' is a NEW value, never a redefinition of 'bold' -- a
        call-site written as == "bold" stops matching visibly instead of
        being silently re-classified."""
        self.assertEqual(tl.classify_style("Arial-Bold"), "bold")
        self.assertEqual(tl.classify_style("Georgia-Italic"), "italic")
        self.assertEqual(tl.classify_style("Helvetica"), "")
        self.assertEqual(tl.classify_style("Foo-Medium"), "")
        self.assertEqual(tl.classify_style("Foo-Light"), "")

    def test_link_breaks_a_run_and_rides_along(self):
        links = [{"uri": "https://example.com", "bbox": (28, 95, 52, 115)}]
        chars = [char("see ", 0, 26), char("docs", 30, 50)]
        runs = tl.line_runs(chars, links=links)
        self.assertEqual(runs[-1]["uri"], "https://example.com")
        self.assertIsNone(runs[0]["uri"])


class TestMergeClose(unittest.TestCase):
    def test_hairline_join_collapses(self):
        """Adjacent rule segments report 184.2 and 184.3 for one boundary;
        unmerged they look like a one-point column and split the table."""
        self.assertEqual(tl.merge_close([70.9, 184.2, 184.3, 297.6]),
                         [70.9, 184.2, 297.6])


# ------------------------------------------------ _textlines: the hyphen family

class TestHyphenPolicy(unittest.TestCase):
    """A line-ending hyphen is four different characters wanting four
    different answers, and `endswith("-")` sees only one of them.

    Measured: one magazine breaks 208 of 1573 lines on U+002D, the other
    breaks 12 of 13 on U+2011 NON-BREAKING HYPHEN -- the character a
    typesetter emits to say *this hyphen is not a break*. Joining those away
    shipped `o- end`, `h- order`, `8- 023`. The class is invisible to
    word-coverage verification by construction (see
    TestVerifyNormalisation.test_hyphenation_is_invisible_to_word_coverage),
    so the verdict is the only guard there is.
    """

    def test_a_soft_hyphen_is_always_dropped(self):
        """Rule 2 outranks rules 4 and 5: U+00AD is discretionary by
        definition and must never survive into the joined word."""
        self.assertEqual(tl.hyphen_verdict("multi­", "word"), "drop")

    def test_the_typographic_hyphens_are_kept(self):
        for ch in ("‐", "‑", "‒"):
            with self.subTest(hyphen="U+%04X" % ord(ch)):
                self.assertEqual(
                    tl.hyphen_verdict("two" + ch, "dimensional"), "keep")

    def test_a_hyphen_inside_an_identifier_is_reported_not_dropped(self):
        """Rule 4 must be consulted before rule 6, or a DOI silently becomes
        `s41598023` and an e-mail address loses a character."""
        self.assertEqual(
            tl.hyphen_verdict("see https://doi.org/10.1038/s41598-", "023"),
            "report")
        self.assertEqual(tl.hyphen_verdict("mail a@b.c-", "d"), "report")

    def test_the_identifier_rule_outranks_the_non_hyphenating_rule(self):
        """Rule 4 before rule 5, which is invisible at the default
        `hyphenating=True` -- there both orders answer 'report', so the
        assertion above passes against either. It is the non-hyphenating
        document that separates them, and that is the common case for the
        documents this rule was written for: swap the two and a DOI broken
        across a line in a document that does not hyphenate silently answers
        'keep' and is never shown to anyone, which is the whole difference
        between a decision and a site the caller must look at."""
        self.assertEqual(
            tl.hyphen_verdict("see https://doi.org/x-", "023",
                              hyphenating=False), "report")
        self.assertEqual(tl.hyphen_verdict("mail a@b.c-", "d",
                                           hyphenating=False), "report")

    def test_a_document_that_does_not_hyphenate_keeps_its_hyphens(self):
        self.assertEqual(
            tl.hyphen_verdict("rock-", "solid", hyphenating=False), "keep")
        self.assertEqual(
            tl.hyphen_verdict("cogni-", "tion", hyphenating=True), "drop")

    def test_no_join_across_a_non_word_tail(self):
        """Rule 1, plus the empty/None guards: an IndexError on a blank head
        line, and a dash welded onto the parenthetical it opens."""
        for head, tail in (("plain", "next"), ("dash-", "(paren)"),
                           ("", "x"), (None, None)):
            with self.subTest(head=head):
                self.assertEqual(tl.hyphen_verdict(head, tail), "space")

    def test_the_rate_separates_the_two_measured_documents(self):
        doc_a = "\n".join(["word-"] * 208 + ["word"] * 1365)      # 208 of 1573
        doc_b = "\n".join(["word‑"] * 12 + ["word-"]
                          + ["word"] * 1765)                      # 13 of 1778
        doc_b_ascii = "\n".join(["word-"] + ["word"] * 1417)      # 1 of 1418
        self.assertEqual(tl.hyphenation_rate(doc_a), 0.1322)
        # The same document read two ways: 0.0073 is what this function
        # counts (the U+002D/U+2010/U+2011 family), 0.0007 is what the
        # `endswith("-")` test it replaces could see. Both are far below the
        # threshold and two to three orders below doc A, so the verdict does
        # not depend on which reading a caller quotes.
        self.assertEqual(tl.hyphenation_rate(doc_b), 0.0073)
        self.assertEqual(tl.hyphenation_rate(doc_b_ascii), 0.0007)
        self.assertGreaterEqual(0.1322, tl.HYPHENATION_MIN_RATE)
        self.assertGreater(tl.HYPHENATION_MIN_RATE, 0.0073)
        # U+00AD is discretionary and U+2012 is punctuation: neither is
        # evidence about the typesetter's line breaking, so neither counts.
        self.assertEqual(tl.hyphenation_rate("a­\nb"), 0.0)
        self.assertEqual(tl.hyphenation_rate("a‒\nb"), 0.0)

    def test_the_rate_ignores_blank_lines_and_empty_input(self):
        self.assertEqual(tl.hyphenation_rate("a-\n\n\nb"), 0.5)
        self.assertEqual(tl.hyphenation_rate(["a-", "b"]), 0.5)
        self.assertEqual(tl.hyphenation_rate(""), 0.0)
        # Pinned as measured, and NOT as the slice report claimed (it said
        # 0.0): `None` is not a `str`, so the function iterates it and
        # raises. Recorded so that returning 0.0 instead is a deliberate,
        # visible change rather than a silent one.
        with self.assertRaises(TypeError):
            tl.hyphenation_rate(None)

    def test_dehyphenate_follows_the_verdict(self):
        self.assertEqual(tl.dehyphenate("cogni-\ntion plus"), "cognition plus")
        self.assertEqual(tl.dehyphenate("two‑\ndimensional"),
                         "two‑dimensional")
        self.assertEqual(tl.dehyphenate("rock-\nsolid", hyphenating=False),
                         "rock-solid")
        # 'space' does not join, and does not eat the line break either.
        self.assertEqual(tl.dehyphenate("plain\nnext"), "plain\nnext")

    def test_hyphen_sites_reports_only_the_undecidable_ones(self):
        sites = tl.hyphen_sites(
            "see https://doi.org/x-\n023 next\nplain-\n(paren)\ncogni-\ntion")
        self.assertEqual(len(sites), 2)
        self.assertEqual(sites[0], {"line_no": 1, "hyphen": "U+002D",
                                    "stem": "https://doi.org/x", "tail": "023",
                                    "verdict": "report"})
        self.assertEqual(sites[1]["verdict"], "space")
        self.assertEqual(sites[1]["stem"], "plain")
        self.assertEqual(sites[1]["tail"], "")
        # The 'drop' site is a decision, not a site: it must not be reported.
        self.assertNotIn("cogni", [s["stem"] for s in sites])


# ------------------------------------------ _textlines: the measured word gap

class TestSpaceRatioMeasurement(unittest.TestCase):
    """The peak formula lands inside the inter-word population's own left
    tail on a justified file and welds prose into one token. Where the file
    labels its own word boundaries with space glyphs, the threshold is scored
    against those labels instead."""

    def _ratio(self, name):
        import pdfplumber
        with pdfplumber.open(str(FIXTURES / name)) as pdf:
            return tl.space_ratio(pdf)

    def test_the_labelled_pass_declines_where_the_file_labels_too_little(self):
        """glued.pdf labels 6 boundaries. The fallback must be byte-identical
        to the behaviour that shipped, and the labelled statistics must read
        None -- not 0, which a consumer would mistake for 'measured zero'."""
        r = self._ratio("glued.pdf")
        self.assertEqual(r["source"], "peaks")
        self.assertEqual(r["ratio"], 0.14)
        self.assertEqual(r["ratio"], r["fallback_ratio"])
        self.assertEqual(r["labelled_boundaries"], 6)
        for key in ("safe_band", "false_glue", "false_split"):
            self.assertIsNone(r[key], key)

    def test_the_labelled_pass_overrides_the_peaks_and_keeps_the_audit_trail(self):
        r = self._ratio("columns.pdf")
        self.assertEqual(r["source"], "labelled")
        self.assertEqual(r["ratio"], 0.16)
        self.assertEqual(r["fallback_ratio"], 0.14)   # what _valley would say
        self.assertEqual(r["false_glue"], 0)
        self.assertEqual(r["labelled_boundaries"], 1040)
        self.assertIs(r["measured"], True)
        for key in ("ratio", "measured", "intra_word_peak", "inter_word_peak",
                    "space_glyphs", "sampled_chars", "top_gaps"):
            self.assertIn(key, r, "legacy key %r dropped" % key)

    def test_the_sample_floor_applies_to_both_populations(self):
        """Plenty of word interiors and almost no labelled boundaries must
        not buy a threshold picked from noise, nor the reverse."""
        self.assertIsNone(tl._labelled_split([0.2] * 199, [0.0] * 400))
        self.assertIsNone(tl._labelled_split([0.2] * 400, [0.0] * 199))
        wide = tl._labelled_split([0.2] * 400, [0.0] * 400)
        self.assertIsNotNone(wide)
        self.assertLess(wide["safe_band"][0], wide["safe_band"][1])

    def test_the_ratio_is_the_middle_of_the_band_not_an_edge(self):
        """One plateau, so this says nothing about WHICH plateau is chosen --
        see the test below for that -- only that the answer is its middle."""
        out = tl._labelled_split([0.25] * 400, [0.0] * 400)
        lo, hi = out["safe_band"]
        self.assertEqual(out["false_glue"], 0)
        self.assertEqual(out["false_split"], 0)
        self.assertLess(lo, hi)
        self.assertGreater(out["ratio"], lo)
        self.assertLess(out["ratio"], hi)

    def test_the_widest_plateau_is_picked_not_the_first_minimum(self):
        """Two bands of EQUAL minimum cost, the first narrower than the
        second -- which is what it takes to tell the two rules apart. A
        single-plateau input cannot: `runs[0]` and `max(runs, key=len)` are
        then the same object, and a test built on one passes against
        first-minimum selection unchanged.

        Cost 3 is reached on 0.090-0.150 (13 bins) and again on 0.200-0.300
        (21 bins). The widest is the one furthest from both populations, so
        the answer is 0.25; first-minimum selection answers 0.12 and parks
        the threshold four bins from a word interior."""
        out = tl._labelled_split([0.35] * 400 + [0.155],
                                 [0.0] * 400 + [0.200] * 3 + [0.090] * 4)
        self.assertEqual(out["safe_band"], [0.2, 0.3])
        self.assertEqual(out["ratio"], 0.25)

    def test_the_glue_is_weighted_above_the_split(self):
        """A split word is two readable tokens and a verifier finds it;
        `Theflyingfish...` is gone. So the threshold must not buy a lower
        split count by swallowing a boundary the file itself labelled with a
        space glyph: here moving up one bin would trade 2 splits for 1 glue,
        and weighting them equally takes that trade (band 0.100-0.295,
        false_glue 1) while the 3:1 weight refuses it."""
        out = tl._labelled_split([0.30] * 300 + [0.10],
                                 [0.0] * 300 + [0.0975] * 2)
        self.assertEqual(out["false_glue"], 0)
        self.assertEqual(out["false_split"], 2)
        self.assertEqual(out["safe_band"], [0.04, 0.095])

    def test_the_midpoint_rounds_half_up(self):
        """A plateau midpoint is a multiple of 0.0025 (both edges sit on the
        0.005 grid), so it lands on a half step -- x.xx5 -- often enough for
        the rule to move the published answer by a whole bin.

        NOTE, measured: 0.0975 does NOT demonstrate this, though
        `_round_half_up`'s own docstring offers it as the example. It is a
        half step at THREE places, not two, and `round(0.0975, 2)` is 0.1
        already; the values that actually separate the two rules are 0.105
        and 0.125. Reported rather than repeated, so this test is not a
        second copy of the same mistake."""
        self.assertEqual(tl._round_half_up(0.105, 2), 0.11)   # round() -> 0.1
        self.assertEqual(tl._round_half_up(0.125, 2), 0.13)   # round() -> 0.12
        self.assertEqual(round(0.0975, 2), tl._round_half_up(0.0975, 2))

    def test_a_one_bin_plateau_publishes_that_bin(self):
        """The rounding above is what made the answer readable and what took
        it out of its own band. The grid is 0.005 and the answer is rounded to
        two places, so a one-bin plateau sitting on an odd half step -- 0.045,
        0.055 ... 0.295, half of the 53 grid points -- rounded one FULL bin
        past `hi`. A one-bin plateau means that neighbour costs strictly more
        by construction, and the direction it costs more in is glue.

        Two populations 0.0002 apart, straddling 0.095: pre-fix this returned
        ratio 0.1 and glued all 400 labelled boundaries."""
        out = tl._labelled_split([0.0951] * 400, [0.0949] * 400)
        self.assertEqual(out["safe_band"], [0.095, 0.095])
        self.assertEqual(out["ratio"], 0.095)
        self.assertEqual(out["false_glue"], 0)
        self.assertEqual(out["false_split"], 0)

    def test_the_published_ratio_is_never_outside_the_plateau(self):
        """The invariant behind the case above, swept over the whole grid so
        no future rounding rule can slip a different half step through: every
        one-bin plateau the scan can produce, plus a few wide ones."""
        grid = [round(0.040 + i * 0.005, 3) for i in range(53)]
        for value in grid:
            with self.subTest(plateau=value):
                out = tl._labelled_split([value + 0.0001] * 400,
                                         [value - 0.0001] * 400)
                lo, hi = out["safe_band"]
                self.assertLessEqual(lo, out["ratio"])
                self.assertLessEqual(out["ratio"], hi)

    def test_the_two_error_counts_are_the_definitions_they_publish(self):
        """`would glue N, would split M` in the report, and the reference's
        sweep table, ARE these two sums at the published ratio. Anything else
        under those names is a different quantity wearing the same label."""
        inter = [0.05, 0.08, 0.12, 0.30] * 100
        intra = [0.0, 0.02, 0.09, 0.20] * 100
        out = tl._labelled_split(inter, intra)
        self.assertEqual(out["false_glue"],
                         sum(1 for g in inter if g <= out["ratio"]))
        self.assertEqual(out["false_split"],
                         sum(1 for g in intra if g > out["ratio"]))
        self.assertEqual(out["labelled_boundaries"], len(inter))

class TestPageSampling(unittest.TestCase):
    """`--pages N` must read N pages.

    The edge rule (keep the first and last few) and the evenly spaced set both
    claimed index 0, and the union swallowed the duplicate: `sample_pages(p, 1)`
    returned 2 pages, 24 returned 21, and `pdf_profile.py --pages 6` profiled
    5 -- so the spacing pass, called with `min(len(pages), 24)`, scored a
    DIFFERENT page set from the one the report named. Nothing was corrupted;
    the sample simply was not the one the caller asked for.
    """

    def test_sample_pages_returns_exactly_count(self):
        for total in range(2, 41):
            pages = ["p%02d" % i for i in range(total)]
            for count in range(1, total + 1):
                with self.subTest(total=total, count=count):
                    out = tl.sample_pages(pages, count)
                    self.assertEqual(len(out), min(count, total))
                    self.assertEqual(out, sorted(out, key=pages.index),
                                     "the sample must stay in page order")

    def test_the_edges_are_kept_whenever_there_is_room_for_both(self):
        """Front matter carries the title and the contents; back matter the
        appendices and the legal text, which is where a measured document put
        a whole chapter in its page footer's point size."""
        pages = ["p%02d" % i for i in range(30)]
        for count in range(2, 25):
            with self.subTest(count=count):
                out = tl.sample_pages(pages, count)
                self.assertIn(pages[0], out)
                self.assertIn(pages[-1], out)

    def test_zero_or_none_or_more_than_there_are_is_every_page(self):
        """0 and None are the documented "every page"; a count past the end is
        every page because there is nothing else to give."""
        pages = ["p%d" % i for i in range(10)]
        for count in (0, None, 10, 99):
            with self.subTest(count=count):
                self.assertEqual(tl.sample_pages(pages, count), pages)

    def test_the_pages_flag_rejects_a_negative_count(self):
        """A negative N reached `_sample` as `count <= 0` and silently meant
        every page -- the opposite of the smallest sample the caller asked
        for, and something the help text never offered."""
        out = run(PROFILE, FIXTURES / "digital.pdf", "--pages", "-1")
        self.assertEqual(out.returncode, 2)
        self.assertEqual(out.stdout, "")
        self.assertIn("--pages", out.stderr)
        self.assertIn("0 or more", out.stderr)
        word = run(PROFILE, FIXTURES / "digital.pdf", "--pages", "abc")
        self.assertEqual(word.returncode, 2)
        self.assertIn("whole number of pages", word.stderr)

    def test_zero_still_profiles_the_whole_document(self):
        """The documented spelling must keep working, or the rejection above
        would have taken the escape hatch with it."""
        out = run(PROFILE, FIXTURES / "columns.pdf", "--pages", "0", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        document = json.loads(out.stdout)["document"]
        self.assertEqual(document["sampled"], document["pages"])


class TestBulletMarkers(unittest.TestCase):
    def test_marker_only_needs_a_single_glyph(self):
        """`text in BULLET_CHARS` is substring membership against the literal
        "•●▪◦▶‣⁃·■○", so ANY contiguous 2+ character slice of it read as a
        bare list marker."""
        def one_line_page(text):
            chars = [char(g, 6.0 * i, 6.0 * (i + 1))
                     for i, g in enumerate(text)]
            line = {"x0": chars[0]["x0"], "x1": chars[-1]["x1"],
                    "top": chars[0]["top"], "bottom": chars[0]["bottom"],
                    "chars": chars}
            return mock.Mock(extract_text_lines=lambda **kw: [line])

        for text, expected in (("•", True), ("●", True), ("▪", True),
                               ("▪◦", False), ("•●▪", False), ("x", False)):
            with self.subTest(text=text):
                record = tl.page_lines(one_line_page(text))
                self.assertEqual(len(record), 1, record)
                self.assertEqual(record[0]["text"], text)
                self.assertIs(record[0]["marker_only"], expected)


# ---------------------------------------------------- pdf_extract --lines

class TestLinesFlag(unittest.TestCase):
    fixture = FIXTURES / "digital.pdf"

    def test_absent_without_the_flag(self):
        out = run(EXTRACT, self.fixture)
        self.assertEqual(out.returncode, 0, out.stderr)
        page = json.loads(out.stdout)["pages"][0]
        for key in ("lines", "rects", "rules"):
            self.assertNotIn(key, page)

    def test_default_dump_is_byte_identical(self):
        """The contract every optional feature here keeps: a caller that does
        not ask sees no shape change at all."""
        a = run(EXTRACT, self.fixture)
        b = run(EXTRACT, self.fixture)
        self.assertEqual(a.stdout, b.stdout)
        with_lines = json.loads(run(EXTRACT, self.fixture, "--lines").stdout)
        for page in with_lines["pages"]:
            for key in ("lines", "rects", "rules"):
                page.pop(key, None)
        self.assertEqual(with_lines, json.loads(a.stdout))

    def test_lines_carry_size_font_and_bbox(self):
        out = run(EXTRACT, self.fixture, "--lines")
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = json.loads(out.stdout)["pages"][0]["lines"]
        self.assertTrue(lines, "expected line records")
        first = lines[0]
        for key in ("text", "bbox", "size", "font", "marker_only"):
            self.assertIn(key, first)
        self.assertEqual(len(first["bbox"]), 4)
        self.assertGreater(first["size"], 0)

    def test_rules_expose_the_column_signature(self):
        """A horizontally ruled table is invisible to extract_tables but its
        rule endpoints are the column boundaries (reference section 3.2b)."""
        out = run(EXTRACT, FIXTURES / "ruling.pdf", "--lines")
        self.assertEqual(out.returncode, 0, out.stderr)
        rules = [r for p in json.loads(out.stdout)["pages"] for r in p["rules"]]
        self.assertTrue(rules, "expected ruled rows in ruling.pdf")
        self.assertTrue(all("x" in r and "y" in r for r in rules))


# ------------------------------------------------------------- pdf_profile

class TestProfile(unittest.TestCase):
    def test_reports_body_size_and_recommendations(self):
        out = run(PROFILE, FIXTURES / "digital.pdf", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        profile = json.loads(out.stdout)
        self.assertGreater(profile["fonts_and_sizes"]["body_size"], 0)
        self.assertIn("recommendations", profile)
        self.assertIsInstance(profile["spacing"]["ratio"], float)

    def test_measured_ratio_is_inside_the_safe_band(self):
        """The invariant this test's NAME promised and its body did not make.

        It asserted `0.06 <= ratio <= 0.30` against `glued.pdf`, whose source
        is `peaks` and which therefore carries no band at all -- so the band
        was never read, and a published ratio one full bin OUTSIDE its own
        plateau passed here 92 tests green: a one-bin plateau at 0.095
        published 0.10, the strictly more expensive neighbour, in the
        unrecoverable glue direction (measured on a real document: twice the
        false glue). `safe_band` is the plateau the answer was scored on. A
        ratio outside it is a number nothing scored.
        """
        labelled = 0
        for name in ("columns.pdf", "figure.pdf", "ruling.pdf", "split.pdf",
                     "glued.pdf", "digital.pdf"):
            with self.subTest(fixture=name):
                sp = json.loads(
                    run(PROFILE, FIXTURES / name, "--json").stdout)["spacing"]
                if sp["source"] != "labelled":
                    # Not measurable here, and the band must then read None --
                    # never a number a consumer would take for a measurement.
                    self.assertIsNone(sp["safe_band"])
                    continue
                labelled += 1
                band = sp["safe_band"]
                self.assertEqual(len(band), 2, band)
                self.assertLessEqual(band[0], sp["ratio"])
                self.assertLessEqual(sp["ratio"], band[1])
        self.assertGreaterEqual(
            labelled, 4,
            "no fixture reached the labelled pass -- the invariant above "
            "would be satisfied vacuously")

    def test_render_survives_a_short_safe_band(self):
        """`_recommend` guards this field with `len(band) == 2` and `_render`
        indexed `band[0]`/`band[1]` raw: two readers of one field disagreeing
        about whether it can be short, with the unguarded one in the human
        report. The guard is the agreement, not the crash that never came."""
        report = json.loads(
            run(PROFILE, FIXTURES / "columns.pdf", "--json").stdout)
        self.assertEqual(report["spacing"]["source"], "labelled")
        band_lines = [l for l in profile._render(report).splitlines()
                      if "safe band" in l]
        self.assertEqual(len(band_lines), 1,
                         "a two-element band must still print its band line")
        report["spacing"]["safe_band"] = [0.09]
        out = profile._render(report)          # pre-fix: IndexError
        self.assertNotIn("safe band", out)
        self.assertIn("the gap peaks alone would have said", out)
        self.assertIn("## Recommendations", out)

    def test_ruled_table_diagnostic_fires(self):
        profile = json.loads(run(PROFILE, FIXTURES / "ruling.pdf", "--json").stdout)
        self.assertGreater(profile["regions"]["ruled_regions"], 0)

    def test_human_report_renders(self):
        out = run(PROFILE, FIXTURES / "digital.pdf")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("## Recommendations", out.stdout)

    def test_the_profile_never_recommends_a_y_cutoff(self):
        """A y cut-off fails in BOTH directions on the same document: of 113
        line records above the header band's lowest edge only 16 were
        furniture (97 real lines deleted), and a DOI line repeating on 18 of
        20 pages sits 13 pt BELOW the cut and survives it. The probe reports
        patterns to match instead, and deletes nothing."""
        profile = json.loads(
            run(PROFILE, FIXTURES / "figure.pdf", "--json").stdout)
        self.assertIs(profile["furniture"]["detected"], True)
        for line in profile["recommendations"]:
            self.assertNotIn("drop lines", line)
            self.assertIsNone(re.search(r"drop lines (above|below) y=", line))

    def test_no_drop_furniture_flag_exists_and_columns_is_documented(self):
        """The prohibition, not an oversight: nothing in this tool deletes
        furniture, so a flag that did would be the y cut-off again."""
        out = run(PROFILE, "--help")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("--drop-furniture", out.stdout)
        self.assertIn("--columns SPEC", out.stdout)

    def test_furniture_patterns_carry_region_pages_and_y_range(self):
        furniture = json.loads(
            run(PROFILE, FIXTURES / "figure.pdf", "--json").stdout)["furniture"]
        self.assertIs(furniture["region_scoped"], False)
        self.assertEqual([r["name"] for r in furniture["regions"]], ["page"])
        self.assertTrue(furniture["patterns"])
        for pattern in furniture["patterns"]:
            self.assertEqual(set(pattern), {"pattern", "region", "band",
                                            "pages", "y_min", "y_max"})
            self.assertEqual(pattern["region"], "page")
        self.assertIn("confidential - example corp llc",
                      [p["pattern"] for p in furniture["patterns"]])

    def test_a_pattern_needs_a_tight_y_spread_and_most_pages(self):
        """The y-spread bound is what keeps a body line that happens to
        repeat from being reported as furniture."""
        furniture = json.loads(
            run(PROFILE, FIXTURES / "figure.pdf", "--json").stdout)["furniture"]
        floor = max(3, int(furniture["sampled_pages"] * 0.5))
        for pattern in furniture["patterns"]:
            with self.subTest(pattern=pattern["pattern"]):
                self.assertLessEqual(pattern["y_max"] - pattern["y_min"],
                                     1.0 + 1e-9)
                self.assertGreaterEqual(pattern["pages"], floor)

    def test_the_pattern_thresholds_are_the_measured_ones(self):
        """The test above checks the patterns a fixture DOES produce, which
        is blind to a loosened bound in the direction that matters: widen the
        y spread to 20 pt or drop the page share to 5 % and figure.pdf still
        yields the same one pattern, so every assertion there still passes
        while the rule now reports body text as furniture on some other
        document. The constants are the contract, and each was measured:

        * 1.0 pt of y spread -- the four patterns of a 20-page magazine hold
          to 0.2 pt, so a pt is already generous, and it is what separates a
          fixed slot from a line that merely recurs;
        * 50 % of the sampled pages, floor 3 -- a running header is on nearly
          every page, and 3 keeps a short document from making a pattern out
          of a coincidence.

        Nothing here deletes text, so a wrong pattern costs a line of report
        rather than a line of the document -- but it is reported to a caller
        who will act on it, so the bounds stay where the measurement put
        them."""
        self.assertEqual(profile._PATTERN_Y_SPREAD, 1.0)
        self.assertEqual(profile._PATTERN_PAGE_SHARE, 0.5)
        self.assertEqual(profile._PATTERN_MIN_PAGES, 3)

    def test_columns_scopes_the_probe_and_names_the_regions(self):
        """Both accepted grammars, and the crop path must not silently fall
        back to page-wide: on a multi-column page lines welded across the
        gutter never repeat identically, so patterns are under-counted
        page-wide (measured: 1 pattern page-wide against 4 scoped)."""
        cuts = json.loads(run(PROFILE, FIXTURES / "columns.pdf",
                              "--columns", "200,400", "--json").stdout)
        self.assertIs(cuts["furniture"]["region_scoped"], True)
        self.assertEqual(cuts["furniture"]["regions"],
                         [{"name": "col1", "x0": 0.0, "x1": 200.0},
                          {"name": "col2", "x0": 200.0, "x1": 400.0},
                          {"name": "col3", "x0": 400.0, "x1": 612.0}])
        named = json.loads(run(PROFILE, FIXTURES / "digital.pdf", "--columns",
                               "l:0-200,r:200-612", "--json").stdout)
        self.assertIs(named["furniture"]["region_scoped"], True)
        self.assertEqual([r["name"] for r in named["furniture"]["regions"]],
                         ["l", "r"])

    def test_a_bad_columns_spec_is_a_usage_error(self):
        """A malformed or unsatisfiable spec must never be profiled anyway --
        including the empty string, which is parsed because the flag is
        tested with `is not None` and not for truthiness."""
        bad = ["456.5,152.5", "abc", "0,300", "700",
               "side:0-158,body:200-458,notes:458-612", "side:0-158,body:158-458",
               "side:0-158,300,458-612", "body:158", "a:0-306,a:306-612",
               "", "152.5,"]
        for spec in bad:
            with self.subTest(spec=spec):
                out = run(PROFILE, FIXTURES / "digital.pdf",
                          "--columns", spec, "--json-errors")
                self.assertEqual(out.returncode, 2, out.stderr)
                envelope = json.loads(out.stderr.strip().splitlines()[-1])
                self.assertEqual(envelope["type"], "UsageError")
                self.assertEqual(envelope["code"], 2)
                self.assertTrue(envelope["error"].startswith("--columns:"))

    def test_the_size_collision_warning_survives_region_scoping(self):
        """The one warning that has ever prevented deleting a chapter: the
        furniture's point sizes are ALSO used by real body text elsewhere."""
        plain = json.loads(
            run(PROFILE, FIXTURES / "figure.pdf", "--json").stdout)
        self.assertEqual(plain["furniture"]["size_collides_with_body_text"],
                         [9.0, 10.0])
        self.assertTrue(any("DO NOT filter furniture by point size" in r
                            for r in plain["recommendations"]))
        scoped = run(PROFILE, FIXTURES / "figure.pdf",
                     "--columns", "200,400", "--json")
        self.assertEqual(scoped.returncode, 0, scoped.stderr)
        self.assertNotIn("Traceback", scoped.stderr)

    def test_role_treats_bold_italic_as_a_heading_candidate(self):
        """`== "bold"` silently demoted every bold-italic display face to
        'large text' the moment classify_style learned the fourth value."""
        self.assertEqual(
            profile._role(20.0, 10.0, {"TimesNewRomanPS-BoldItalicMT": 5}),
            "heading candidate")
        self.assertEqual(profile._role(20.0, 10.0, {"Helvetica-Bold": 5}),
                         "heading candidate")
        self.assertEqual(profile._role(20.0, 10.0, {"Helvetica": 5}),
                         "large text")

    def test_missing_input_is_a_clean_envelope(self):
        out = run(PROFILE, FIXTURES / "nope.pdf", "--json-errors")
        self.assertEqual(out.returncode, 1)
        envelope = json.loads(out.stderr.strip().splitlines()[-1])
        self.assertEqual(envelope["type"], "InputNotFound")

    def test_encrypted_input_fails_loudly(self):
        out = run(PROFILE, FIXTURES / "encrypted.pdf")
        self.assertEqual(out.returncode, 1)
        self.assertNotIn("Traceback", out.stderr)


# ----------------------------------------------------------- pdf_verify_md

class TestVerifyNormalisation(unittest.TestCase):
    def test_markdown_escapes_do_not_read_as_loss(self):
        self.assertEqual(verify.tokens(verify.strip_markdown(r"MKT\_AGENCY")),
                         verify.tokens("MKT_AGENCY"))

    def test_link_syntax_keeps_its_text(self):
        stripped = verify.strip_markdown("[Custom Fields](https://x.example/a)")
        self.assertIn("custom", verify.tokens(stripped))

    def test_dehyphenation_is_applied_to_both_sides(self):
        """A converter that correctly rejoins 'Orchestra-'/'tion' must not be
        scored as having lost 'orchestra' and 'tion'."""
        self.assertEqual(verify.tokens("Orchestra-\ntion"),
                         verify.tokens("Orchestration"))

    def test_real_hyphen_in_an_identifier_survives(self):
        joined = verify.dehyphenate("see sap.hana-\napp.cuan")
        self.assertIn("sap.hana-app.cuan", joined)

    def test_boundary_underscores_are_not_loss(self):
        """Python's \\w includes `_`, so italic emphasis tokenised as
        '_finnegans' + 'wake_' and neither matched the PDF: 202 distinct
        tokens / 314 occurrences on one measured document, a third of its
        whole reported loss."""
        self.assertEqual(verify.tokens(verify.strip_markdown("_Finnegans Wake_")),
                         verify.tokens("Finnegans Wake"))

    def test_interior_underscores_survive_the_strip(self):
        """The strip is applied to an already-matched token, symmetrically,
        and never as a substitution over the text -- `_` is deliberately NOT
        in _MD_STRIP, where it would split these in half."""
        self.assertEqual(verify.tokens("snake_case_name"),
                         collections.Counter({"snake_case_name": 1}))
        self.assertEqual(verify.tokens(verify.strip_markdown(r"MKT\_AGENCY")),
                         collections.Counter({"mkt_agency": 1}))

    def test_bare_underscores_are_not_a_token(self):
        """`len >= 3` is re-checked AFTER the strip, or a rule of underscores
        becomes an empty-string token."""
        self.assertEqual(verify.tokens("___"), collections.Counter())

    def test_a_soft_hyphen_is_always_dropped(self):
        """U+00AD is discretionary by definition, and the ./: identifier
        exception must not rescue one."""
        self.assertEqual(verify.dehyphenate("two­\ndimensional"),
                         "twodimensional")
        self.assertEqual(verify.dehyphenate("sap.hana­\napp"),
                         "sap.hanaapp")

    def test_typographic_hyphens_are_not_this_modules_job(self):
        """U+2010/U+2011/U+2012 are hyphens a converter is supposed to KEEP,
        and the module that judges them is _textlines.hyphen_verdict. Adding
        them here would silently change the reference side."""
        for ch in ("‐", "‑", "‒"):
            text = "two" + ch + "\ndimensional"
            with self.subTest(hyphen="U+%04X" % ord(ch)):
                self.assertEqual(verify.dehyphenate(text), text)

    def test_hyphenation_is_invisible_to_word_coverage(self):
        """A locked-in limitation, not an aspiration: `_WORD` is \\w{3,},
        which does not match a hyphen at all, so a correctly rejoined
        compound and a badly welded `two- dimensional` produce the SAME
        Counter whatever dehyphenate decided. No loss_pct figure in this
        module's report may ever be read as evidence about a hyphenation
        defect -- that question belongs to _textlines.hyphen_verdict."""
        self.assertEqual(verify.tokens("a two‑\ndimensional plane"),
                         verify.tokens("a two‑ dimensional plane"))

    def test_table_pipes_are_not_content(self):
        self.assertEqual(verify.tokens(verify.strip_markdown("| alpha | beta |")),
                         verify.tokens("alpha beta"))


class TestVerifyEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.dump = self.dir / "dump.json"
        out = run(EXTRACT, FIXTURES / "digital.pdf", "-o", self.dump)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.text = "\n".join(
            p.get("text") or ""
            for p in json.loads(self.dump.read_text())["pages"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_faithful_conversion_reports_no_loss(self):
        md = self.dir / "full.md"
        md.write_text(self.text, encoding="utf-8")
        report = json.loads(run(VERIFY, self.dump, md, "--json").stdout)
        self.assertEqual(report["missing_tokens"], 0)

    def test_truncated_conversion_is_caught(self):
        md = self.dir / "half.md"
        md.write_text(self.text[:len(self.text) // 4], encoding="utf-8")
        report = json.loads(run(VERIFY, self.dump, md, "--json").stdout)
        self.assertGreater(report["loss_pct"], 20)
        self.assertTrue(report["worst_pages"])

    def test_max_loss_gates(self):
        md = self.dir / "half.md"
        md.write_text(self.text[:len(self.text) // 4], encoding="utf-8")
        out = run(VERIFY, self.dump, md, "--max-loss", "5", "--json-errors")
        self.assertEqual(out.returncode, 1)
        envelope = json.loads(out.stderr.strip().splitlines()[-1])
        self.assertEqual(envelope["type"], "CoverageBelowThreshold")

    def test_pdf_source_works_too(self):
        md = self.dir / "full.md"
        md.write_text(self.text, encoding="utf-8")
        out = run(VERIFY, FIXTURES / "digital.pdf", md, "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("loss_pct", json.loads(out.stdout))

    def test_missing_file_is_a_clean_envelope(self):
        out = run(VERIFY, self.dump, self.dir / "nope.md", "--json-errors")
        self.assertEqual(out.returncode, 1)
        envelope = json.loads(out.stderr.strip().splitlines()[-1])
        self.assertEqual(envelope["type"], "InputNotFound")

    def test_the_max_loss_gate_is_inclusive_at_the_threshold(self):
        """`loss_pct > max_loss`, so a loss EQUAL to the limit passes. The
        documented derivation of the recommended `--max-loss 3` rests on it:
        2 is the smallest integer both measured documents pass (1.03 % and
        0.27 %), and 3 is that plus a point of headroom. Flipping this
        comparison to `>=` would quietly invalidate that sentence.

        100 tokens in the reference and 2 absent from the Markdown is exactly
        2.00 %, which is the only way to test a boundary."""
        words = ["tok%03d" % i for i in range(100)]
        source = self.dir / "exact.json"
        source.write_text(json.dumps({"pages": [{"n": 1,
                                                 "text": " ".join(words)}]}),
                          encoding="utf-8")
        md = self.dir / "exact.md"
        md.write_text(" ".join(words[:98]), encoding="utf-8")
        report = json.loads(run(VERIFY, source, md, "--json").stdout)
        self.assertEqual(report["pdf_tokens"], 100)
        self.assertEqual(report["missing_tokens"], 2)
        self.assertEqual(report["loss_pct"], 2.0)
        self.assertEqual(run(VERIFY, source, md, "--max-loss", "2").returncode,
                         0)
        self.assertEqual(run(VERIFY, source, md, "--max-loss", "1").returncode,
                         1)


class TestVerifyRefusesAReferenceItCannotScore(unittest.TestCase):
    """The acceptance gate for the whole toolchain failed OPEN.

    `_page_texts` read `dump.get("pages", [])`, so a stray JSON file scored
    `PDF tokens 0 ... missing 0 (0.0%)` and exited 0 EVEN UNDER `--max-loss 0`:
    `echo '{}' > bad.json` certified any Markdown as green, and
    `pdf_verify_md.py /tmp/dump.json out.md` is the recipe SKILL.md publishes.
    A gate that cannot fail is not a gate.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.md = self.dir / "tiny.md"
        self.md.write_text("hello world from a conversion\n", encoding="utf-8")

    def _refuse(self, name, payload, *flags):
        source = self.dir / name
        source.write_text(payload, encoding="utf-8")
        out = run(VERIFY, source, self.md, *flags, "--json-errors")
        self.assertEqual(out.returncode, 1, out.stdout)
        return json.loads(out.stderr.strip().splitlines()[-1]), source

    def test_a_source_that_is_not_a_dump_is_refused(self):
        for name, payload in (("bad.json", "{}"),
                              ("list.json", "[]"),
                              ("scalar.json", '"a dump, honest"'),
                              ("broken.json", "{not json at all")):
            with self.subTest(source=name):
                envelope, _ = self._refuse(name, payload, "--max-loss", "0")
                self.assertEqual(envelope["type"], "NotADump")
                self.assertIn("pdf_extract.py", envelope["error"])

    def test_a_dump_of_no_pages_is_refused(self):
        envelope, _ = self._refuse("nopages.json", '{"pages": []}',
                                   "--max-loss", "0")
        self.assertEqual(envelope["type"], "EmptyReference")
        self.assertEqual(envelope["details"]["pages"], 0)

    def test_the_refusal_does_not_depend_on_max_loss_being_passed(self):
        """`--max-loss` is what made the fail-open visible, not what caused
        it: a reference nothing can be scored against is a refusal whether or
        not a threshold was asked for."""
        envelope, _ = self._refuse("bare.json", "{}")
        self.assertEqual(envelope["type"], "NotADump")

    def test_a_reference_that_tokenises_to_nothing_is_refused(self):
        """The same fail-open by a different route: pages ARE present, and
        every one of them is empty (a scan, a PDF with no text layer) or is a
        contents page that the check skips by design. `lost / max(total, 1)`
        is then 0.0 -- the arithmetic of "nothing is missing" applied to
        "there was nothing to miss"."""
        blank = json.dumps({"pages": [{"n": i, "text": ""} for i in (1, 2, 3)]})
        envelope, _ = self._refuse("blank.json", blank, "--max-loss", "0")
        self.assertEqual(envelope["type"], "EmptyReference")
        self.assertEqual(envelope["details"]["pages"], 3)
        self.assertEqual(envelope["details"]["toc_pages_skipped"], 0)

        toc_page = ("Introduction . . . . . . . . 1\n"
                    "Methods . . . . . . . . . . 4\n"
                    "Results . . . . . . . . . . 9\n"
                    "Discussion . . . . . . . . 14\n")
        toc = json.dumps({"pages": [{"n": i, "text": toc_page}
                                    for i in (1, 2, 3)]})
        envelope, _ = self._refuse("toc.json", toc, "--max-loss", "0")
        self.assertEqual(envelope["type"], "EmptyReference")
        self.assertEqual(envelope["details"]["toc_pages_skipped"], 3)
        self.assertIn("OCR", envelope["error"])

    def test_a_real_dump_is_still_scored(self):
        """The control that bounds the four refusals above: the tool must
        still say 0.0 % about a conversion it CAN score."""
        dump = self.dir / "dump.json"
        out = run(EXTRACT, FIXTURES / "digital.pdf", "-o", dump)
        self.assertEqual(out.returncode, 0, out.stderr)
        text = "\n".join(p.get("text") or ""
                         for p in json.loads(dump.read_text())["pages"])
        md = self.dir / "full.md"
        md.write_text(text, encoding="utf-8")
        checked = run(VERIFY, dump, md, "--max-loss", "0")
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_an_encrypted_pdf_names_password_identically_in_both_clis(self):
        """`PDFPasswordIncorrect` carries an empty `str()` and pdfplumber
        wraps it in a `PdfminerException` that also does, so interpolating the
        exception produced `Verification failed: ` and sent nobody to
        `--password`. The two tools must not drift apart on it either: the
        dump and the check open the same file for the same reason."""
        args = ["tests/fixtures/encrypted.pdf"]
        checked = subprocess.run(
            [str(PY), str(VERIFY), *args, str(self.md), "--json-errors"],
            capture_output=True, text=True, cwd=str(SCRIPTS_DIR))
        dumped = subprocess.run(
            [str(PY), str(EXTRACT), *args, "--json-errors"],
            capture_output=True, text=True, cwd=str(SCRIPTS_DIR))
        self.assertEqual(checked.returncode, 1, checked.stderr)
        self.assertEqual(dumped.returncode, 1, dumped.stderr)
        a = json.loads(checked.stderr.strip().splitlines()[-1])
        b = json.loads(dumped.stderr.strip().splitlines()[-1])
        self.assertEqual(a["type"], "EncryptedPDF")
        self.assertEqual(b["type"], "EncryptedPDF")
        self.assertEqual(a["error"], b["error"])
        self.assertIn("--password", a["error"])
        # The empty-reason regression: something must follow the colon.
        self.assertTrue(a["error"].split(":")[-1].strip())


class TestJsonErrorsStderrContract(unittest.TestCase):
    """`--json-errors` promises stderr is ONE JSON line and nothing else.

    The furniture refusal was a bare `print(..., file=sys.stderr)` inside
    `verify()`, so a run that refused furniture AND tripped `--max-loss` put
    the warning above the envelope and stderr stopped parsing as JSON at all.
    `pdf_extract.py`'s own `main()` cites this rule as the reason it withholds
    a warning; the fix must not be a silent amputation on the human channel.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        # Ten pages of the same words in the same slots: the word-positional
        # rule would remove 100 % of the sheet, which is the refusal branch.
        def draw(c):
            for page in range(10):
                if page:                       # _canvas_pdf closes the last
                    c.showPage()
                c.setFont("Helvetica", 10)
                c.drawString(72, 740, "Quarterly Bulletin Confidential Draft")
                c.drawString(72, 700, "alpha bravo charlie delta echo foxtrot")
        cls.pdf = cls.dir / "furniture.pdf"
        cls.pdf.write_bytes(_canvas_pdf(draw))
        cls.md = cls.dir / "unrelated.md"
        cls.md.write_text("zulu yankee xray whiskey victor\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_stderr_stays_one_json_line_when_furniture_is_refused(self):
        out = run(VERIFY, self.pdf, self.md, "--max-loss", "0",
                  "--json-errors", "--json")
        self.assertEqual(out.returncode, 1)
        self.assertEqual(len(out.stderr.strip().splitlines()), 1, out.stderr)
        envelope = json.loads(out.stderr)          # pre-fix: JSONDecodeError
        self.assertEqual(envelope["type"], "CoverageBelowThreshold")
        self.assertIs(json.loads(out.stdout)["furniture_refused"], True)

    def test_the_refusal_is_still_loud_on_the_human_channel(self):
        """The other half: suppressing it under `--json-errors` must not
        suppress it everywhere, or the fix would have deleted the warning."""
        out = run(VERIFY, self.pdf, self.md, "--max-loss", "0")
        self.assertEqual(out.returncode, 1)
        self.assertIn("furniture detection refused", out.stderr)
        self.assertIn("falling back to no exclusion", out.stderr)
        self.assertIn("furniture: REFUSED", out.stdout)

    def test_the_fact_survives_in_the_report_either_way(self):
        """Nothing is lost when the line is withheld: it is data, not only a
        warning."""
        quiet = json.loads(run(VERIFY, self.pdf, self.md, "--json",
                               "--json-errors").stdout)
        loud = json.loads(run(VERIFY, self.pdf, self.md, "--json").stdout)
        self.assertIs(quiet["furniture_refused"], True)
        self.assertIs(loud["furniture_refused"], True)
        self.assertEqual(quiet["furniture_tokens"], 0)
        self.assertEqual(quiet["furniture_patterns"], 0)


class TestFurnitureDetection(unittest.TestCase):
    """Running furniture must be filtered by repetition, or a real defect
    drowns in thousands of header/footer tokens."""

    def _pages(self, n=12):
        bodies = ["alpha beta gamma delta", "kappa lambda mu nu",
                  "rho sigma tau upsilon", "phi chi psi omega"]
        return [(i, f"Chapter Guide PUBLIC {i}\n{bodies[i % len(bodies)]}\n"
                    f"third line of body {bodies[(i + 1) % len(bodies)]}\n"
                    f"Some Guide SAP PUBLIC {i}") for i in range(1, n + 1)]

    def test_repeated_edge_lines_are_furniture(self):
        patterns, vocabulary = verify._furniture(self._pages())
        self.assertTrue(patterns or vocabulary)
        self.assertTrue(verify._is_furniture(
            "Chapter Guide PUBLIC 3", patterns, vocabulary))

    def test_body_text_is_not(self):
        patterns, vocabulary = verify._furniture(self._pages())
        self.assertFalse(verify._is_furniture(
            "alpha beta gamma delta", patterns, vocabulary))

    def test_long_lines_are_never_furniture(self):
        """The vocabulary rule is blunt, so it is confined to short lines."""
        patterns, vocabulary = verify._furniture(self._pages())
        long_line = "guide public " * 12
        self.assertGreater(len(long_line), 90)
        self.assertFalse(verify._is_furniture(long_line, patterns, vocabulary))



class TestWordPositionalFurniture(unittest.TestCase):
    """From a PDF the rule is positional, per word instance.

    Reading order is not position: on a three-column sheet the running header
    sits in the left margin at reading-order indices 2-4, where the edge-line
    rule cannot see it, and `extract_text` welds most of it into body lines so
    no whole line repeats either -- a measured document with a four-line
    header on 19 of its 20 pages scored ZERO line patterns.

    No fixture is needed and none is built: `_page_words` is the whole
    dependency on pdfplumber, so replacing it with a list of plain dicts
    exercises the rule on geometry chosen to make each claim visible.
    """

    @staticmethod
    def _header(top=10.0):
        return [{"text": "Modes", "x0": 10.0, "top": top},
                {"text": "with", "x0": 50.0, "top": top},
                {"text": "Knoth", "x0": 90.0, "top": top}]

    def _run(self, pages_words):
        with mock.patch.object(verify, "_page_words",
                               lambda source, password: pages_words):
            return verify._pdf_pages(Path("in-memory.pdf"), None)

    def test_exclusion_is_per_instance_and_never_per_word_type(self):
        """'with' is in the running header on every page AND in body prose.
        A vocabulary rule deletes both; this one keeps the body occurrence
        and takes only the instance printed in the header's slot."""
        pages_words = []
        for n in range(1, 11):
            body = [{"text": "with", "x0": 10.0 + 7 * n, "top": 100.0 + 3 * n}]
            body += [{"text": "word%02d%d" % (i, n), "x0": 60.0 + 9 * i,
                      "top": 100.0 + 3 * n} for i in range(20)]
            pages_words.append((n, self._header() + body))
        pages, furniture = self._run(pages_words)
        self.assertEqual(furniture["furniture_granularity"], "word")
        self.assertEqual(furniture["reference_source"], "pdf-words")
        self.assertIs(furniture["furniture_refused"], False)
        self.assertEqual(sorted(furniture["furniture_vocabulary"]),
                         ["knoth", "modes", "with"])
        for number, full, body_text in pages:
            with self.subTest(page=number):
                self.assertEqual(verify.tokens(full)["with"], 2)
                self.assertEqual(verify.tokens(body_text)["with"], 1)

    def test_furniture_tokens_is_a_token_count_not_an_instance_count(self):
        """The key sits beside `pdf_tokens` and `missing_tokens`, which are
        token counts: reporting raw word instances under it made the three
        incomparable. 'of' and '7/18' are still excluded from the sheet --
        they just cost the comparison nothing, so counting them here would
        only inflate the number."""
        pages_words = []
        for n in range(1, 11):
            head = [{"text": "Modes", "x0": 10.0, "top": 10.0},
                    {"text": "of", "x0": 50.0, "top": 10.0},
                    {"text": "7/18", "x0": 70.0, "top": 10.0}]
            body = [{"text": "w%02d%d" % (i, n), "x0": 10.0 + 9 * i,
                     "top": 100.0 + 3 * n} for i in range(22)]
            pages_words.append((n, head + body))
        _, furniture = self._run(pages_words)
        self.assertEqual(furniture["furniture_patterns"], 3)   # three word keys
        self.assertEqual(furniture["furniture_vocabulary"], ["modes"])
        self.assertEqual(furniture["furniture_tokens"], 10)    # not 30

    def test_the_refusal_branch_is_a_loud_no_op(self):
        """Over 15 % of the document's word instances and the rule excludes
        NOTHING: something about the file breaks its assumption, and removing
        a sixth of the sheet on that basis would be worse than reporting
        furniture as loss. Neither real document comes near the guard (1.6 %
        and 6.1 %), so only a synthetic case can reach it."""
        pages_words = []
        for n in range(1, 11):
            words = [{"text": "head%d" % i, "x0": 10.0 * i, "top": 10.0}
                     for i in range(6)]
            words += [{"text": "body%d" % i, "x0": 10.0 * i, "top": 100.0}
                      for i in range(6)]
            pages_words.append((n, words))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            pages, furniture = self._run(pages_words)
        self.assertIs(furniture["furniture_refused"], True)
        self.assertEqual(furniture["furniture_patterns"], 0)
        self.assertEqual(furniture["furniture_vocabulary"], [])
        self.assertEqual(furniture["furniture_tokens"], 0)
        for number, full, body_text in pages:
            with self.subTest(page=number):
                self.assertEqual(full, body_text)     # nothing amputated
        self.assertIn("furniture detection refused", err.getvalue())
        self.assertIn("falling back to no exclusion", err.getvalue())

    def test_the_refusal_guard_fires_at_its_measured_share(self):
        """The degenerate 100 % case above still refuses whatever the share
        is set to, so it pins the branch but NOT the number. This one does:
        a three-word header over seven scattered body words is 30 % of the
        sheet -- comfortably furniture-shaped, and still refused, because the
        question the guard asks is how much of the document is about to be
        deleted and not whether the rule looks confident. Paired with the
        13 % control below, the two bracket the 15 % threshold."""
        pages_words = []
        for n in range(1, 11):
            head = [{"text": t, "x0": x, "top": 10.0} for t, x in
                    (("Modes", 10.0), ("Knoth", 50.0), ("Renner", 90.0))]
            body = [{"text": "word%02d%d" % (i, n), "x0": 60.0 + 9 * i,
                     "top": 100.0 + 3 * n} for i in range(7)]
            pages_words.append((n, head + body))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            _, furniture = self._run(pages_words)
        self.assertIs(furniture["furniture_refused"], True)
        self.assertEqual(furniture["furniture_tokens"], 0)
        self.assertIn("30.0%", err.getvalue())

    def test_a_word_must_repeat_on_the_measured_share_of_pages(self):
        """`max(3, pages * 0.35)`, both halves of it. Over ten pages that is
        3.5, so three occurrences are not enough and four are -- and the
        floor of 3 is what stops a two-page document making furniture out of
        anything that appears twice. Loosening either bound cannot be seen in
        the shape of the report, only in what it takes."""
        pages_words = []
        for n in range(1, 11):
            words = [{"text": "word%02d%d" % (i, n), "x0": 60.0 + 9 * i,
                      "top": 100.0 + 3 * n} for i in range(20)]
            if n <= 3:
                words.append({"text": "Thrice", "x0": 10.0, "top": 10.0})
            if n <= 4:
                words.append({"text": "Fourfold", "x0": 200.0, "top": 10.0})
            pages_words.append((n, words))
        _, furniture = self._run(pages_words)
        self.assertIs(furniture["furniture_refused"], False)
        self.assertEqual(furniture["furniture_vocabulary"], ["fourfold"])

    def test_a_fixed_header_over_scattered_body_does_not_refuse(self):
        """The control for the test above: the guard must not fire on the
        ordinary document it is meant to let through."""
        pages_words = []
        for n in range(1, 11):
            body = [{"text": "word%02d%d" % (i, n), "x0": 60.0 + 9 * i,
                     "top": 100.0 + 3 * n} for i in range(20)]
            pages_words.append((n, self._header() + body))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            _, furniture = self._run(pages_words)
        self.assertIs(furniture["furniture_refused"], False)
        self.assertEqual(err.getvalue(), "")
        self.assertGreater(furniture["furniture_tokens"], 0)


class TestDumpFurnitureContract(unittest.TestCase):
    """A dump carries no geometry -- and a dump without `--lines` is exactly
    the dump SKILL.md recommends -- so the positional rule is unavailable and
    the reading-order rule applies verbatim. The report must SAY which ran."""

    PAGES = [{"n": i,
              "text": "RUNNING HEADER\n"
                      "symbionts inhabit the reef zone %d\n"
                      "second body line about coral %d\n"
                      "third body line about tides %d\n"
                      "Page %d" % (i, i, i, i),
              # A --lines stream that DROPS a real upright token page['text']
              # keeps -- the measured failure, in miniature.
              "lines": [{"text": "RUNNING HEADER"},
                        {"text": "inhabit the reef zone %d" % i},
                        {"text": "second body line about coral %d" % i},
                        {"text": "third body line about tides %d" % i},
                        {"text": "Page %d" % i}]}
             for i in range(1, 11)]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dump = Path(self.tmp.name) / "dump.json"
        self.dump.write_text(json.dumps({"pages": self.PAGES}),
                             encoding="utf-8")
        self.pages, self.furniture = verify._dump_pages(self.dump)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_reading_order_rule_is_kept_and_named(self):
        self.assertEqual(self.furniture["reference_source"], "dump-text")
        self.assertEqual(self.furniture["furniture_granularity"],
                         "line-reading-order")
        self.assertIs(self.furniture["furniture_refused"], False)
        for number, full, body in self.pages:
            with self.subTest(page=number):
                self.assertIn("RUNNING HEADER", full)
                self.assertNotIn("RUNNING HEADER", body)

    def test_the_reference_never_reads_the_lines_stream(self):
        """Keying the reference on the converter's own line model destroys
        the independence this module exists for: that stream dropped 19 real
        upright tokens on a measured three-column document, and it inherits
        whatever x_tolerance_ratio the dump was taken at -- so an extraction
        ERROR would read as an improvement in the loss figure."""
        for number, full, body in self.pages:
            with self.subTest(page=number):
                self.assertEqual(verify.tokens(full)["symbionts"], 1)
                self.assertEqual(verify.tokens(body)["symbionts"], 1)


class TestFurnitureReporting(unittest.TestCase):
    """At word granularity the vocabulary IS the audit artefact -- the only
    defence against the one over-fire the measurements cannot rule out (a
    table header in a fixed slot on many pages). Truncating it in the JSON
    removes that defence."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        head = " ".join("hdr%02d" % i for i in range(15))
        pages = [{"n": i, "text": "%s\nalpha beta gamma page %d\n"
                                  "delta epsilon zeta page %d\n"
                                  "eta theta iota page %d\nFooter Line %d"
                                  % (head, i, i, i, i)} for i in range(1, 11)]
        self.dump = d / "dump.json"
        self.dump.write_text(json.dumps({"pages": pages}), encoding="utf-8")
        self.md = d / "out.md"
        self.md.write_text("\n".join(p["text"] for p in pages),
                           encoding="utf-8")
        self.report = verify.verify(self.dump, self.md)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_json_vocabulary_is_not_truncated(self):
        self.assertGreater(len(self.report["furniture_vocabulary"]), 12)

    def test_the_text_report_truncates_and_says_so(self):
        rendered = verify._render(self.report)
        extra = len(self.report["furniture_vocabulary"]) - 12
        self.assertIn("(+%d more, see --json)" % extra, rendered)

    def test_both_paths_count_furniture_in_the_same_unit(self):
        """The PDF path's counterpart is
        TestWordPositionalFurniture.test_furniture_tokens_is_a_token_count...,
        which feeds the SAME header -- `Modes of 7/18` on ten pages -- to the
        positional rule and also gets 10. One header, two rules, one number:
        that is the property the key needs to sit beside `pdf_tokens` and
        `missing_tokens`, and it is why `furniture_tokens` is not the raw
        count of what was removed. Only `modes` tokenises; `of` is two
        characters and `7/18` yields no \\w{3,} run, and both are still taken
        off the sheet -- they just cost the comparison nothing."""
        words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta",
                 "theta", "iota", "kappa", "lambda", "mu", "nu", "xi",
                 "omicron", "pi", "rho", "sigma", "tau", "upsilon", "phi",
                 "chi", "psi", "omega", "aleph", "bet", "gimel", "dalet",
                 "hey", "vav", "zayin", "het", "tet", "yod", "kaf", "lamed"]
        pages = []
        for i in range(1, 11):
            body = [" ".join(words[(i * 3 + j * 7 + k) % len(words)]
                             for k in range(4)) for j in range(4)]
            pages.append({"n": i, "text": "Modes of 7/18\n" + "\n".join(body)})
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "dump.json"
            dump.write_text(json.dumps({"pages": pages}), encoding="utf-8")
            _, furniture = verify._dump_pages(dump)
        self.assertEqual(verify.tokens("Modes of 7/18"),
                         collections.Counter({"modes": 1}))
        self.assertEqual(furniture["furniture_vocabulary"], ["modes"])
        self.assertEqual(furniture["furniture_tokens"], 10)     # not 30

    def test_the_report_names_the_unit_of_removal(self):
        """'per line' is what the reading-order rule can take; 'per instance'
        is what the word rule takes, and the difference is the whole point of
        the word rule."""
        self.assertIn("excluded per line", verify._render(self.report))
        as_words = dict(self.report, furniture_granularity="word",
                        furniture_vocabulary=["w%02d" % i for i in range(20)])
        self.assertIn("excluded per instance", verify._render(as_words))
        self.assertIn("(+8 more, see --json)", verify._render(as_words))
        refused = dict(as_words, furniture_refused=True)
        self.assertIn("furniture: REFUSED", verify._render(refused))


# ------------------------- pdf_extract: columns, rasters, and what --help says

def _canvas_pdf(draw, size=(612, 792)):
    """A one-page PDF built in memory with reportlab, as bytes.

    No fixture is added to the repository for these: the pages exist to make
    one measurement visible, and a page whose construction is three lines
    above the assertion cannot drift away from what the assertion claims.
    """
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size)
    draw(c)
    c.showPage()
    c.save()
    return buf.getvalue()


def _rotated_margin_page(c):
    """24 body lines in one column at x = 300, each with one rotated glyph
    printed down the left margin at x ~ 35-40.

    The +3.0 y offset is load-bearing: it puts every rotated glyph in the
    same `int(top / _COLUMN_LINE_TOL_PT)` bin as its body line, so the
    pre-fix code counts 24 of 24 lines as reaching left of the empty band --
    which is exactly how a magazine's rotated cover spine fabricated a gutter
    at x = 145.7 on a document whose real column band is 169.8-183.8.
    """
    for i in range(24):
        y = 700 - i * 20
        c.setFont("Helvetica", 9)
        c.drawString(300, y, "the body column line %02d here" % i)
        c.saveState()
        c.translate(40, y + 3.0)
        c.rotate(90)
        c.setFont("Helvetica", 6)
        c.drawString(0, 0, "S")
        c.restoreState()


def _two_columns_under_a_full_width_heading(c):
    c.setFont("Helvetica", 14)
    c.drawString(80, 720, "A FULL WIDTH HEADING THAT CROSSES THE CUT LINE")
    c.setFont("Helvetica", 9)
    for i in range(20):
        c.drawString(80, 690 - i * 20, "left column row %02d" % i)
        c.drawString(340, 690 - i * 20, "right column row %02d" % i)


class TestRotatedMarginText(unittest.TestCase):
    """A gutter is a vertical band nearly every text LINE respects. A column
    of rotated glyphs down the sheet's edge belongs to no line's baseline,
    but it drags `left_edge` out past the prose block, so every threshold is
    then measured against geometry that is not the prose's."""

    @classmethod
    def setUpClass(cls):
        import pdfplumber
        cls.pdf_bytes = _canvas_pdf(_rotated_margin_page)
        cls.pdf = pdfplumber.open(io.BytesIO(cls.pdf_bytes))
        cls.page = cls.pdf.pages[0]

    @classmethod
    def tearDownClass(cls):
        cls.pdf.close()

    def test_the_page_really_carries_rotated_text(self):
        """Without this the gutter assertion below could pass vacuously: a
        reportlab or pdfplumber change that dropped the rotated glyphs would
        leave it green while testing nothing."""
        self.assertEqual(sum(1 for c in self.page.chars if not c["upright"]), 24)
        self.assertEqual(round(min(c["x0"] for c in self.page.chars), 1), 35.2)
        self.assertEqual(min(c["x0"] for c in tl.upright(self.page.chars)),
                         300.0)

    def test_a_rotated_spine_does_not_fabricate_a_gutter(self):
        self.assertEqual(pdf_extract._page_gutters(self.page), [])

    def test_reading_the_chars_raw_is_what_fabricated_it(self):
        """The defect itself, so the assertion above cannot be satisfied by a
        detector that simply stopped working: read the same page WITHOUT the
        upright filter and a gutter appears at x = 170.7, in empty margin."""
        with mock.patch.object(pdf_extract._tl, "upright", lambda cs: list(cs)):
            self.assertEqual(pdf_extract._page_gutters(self.page), [170.7])

    def test_the_page_produces_no_column_hint(self):
        """The same thing at the level the caller sees. Pre-fix, the measured
        magazine printed a full hint naming a wrong x on pages 7, 15 and 19."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rotated.pdf"
            path.write_bytes(self.pdf_bytes)
            out = run(EXTRACT, path)
        self.assertEqual(out.returncode, 0, out.stderr)
        hints = json.loads(out.stdout)["layout_hints"]
        self.assertEqual(hints["multi_column_pages"], 0)
        self.assertNotIn("column_probe", hints)
        self.assertNotIn("column gutter", out.stderr)


class TestStraddlingLines(unittest.TestCase):
    def test_a_full_width_heading_is_not_counted_as_damage(self):
        """"Characters on both sides" IS the damage; "nothing crosses" is
        what keeps a heading spanning both columns out of the count. Such a
        line has text on both sides too, but it is ONE piece of text -- and
        without the qualifier the probe advises a crop on the strength of the
        very line the crop would sever (measured here: 21 instead of 20)."""
        import pdfplumber
        data = _canvas_pdf(_two_columns_under_a_full_width_heading)
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page = pdf.pages[0]
            word_kwargs = {k: v for k, v in
                           pdf_extract._text_kwargs(False, None, None).items()
                           if k != "layout"}
            heading = page.extract_text_lines(**word_kwargs)[0]
            # The heading really does cross the cut, or the test is vacuous.
            self.assertLess(heading["x0"], 300.0)
            self.assertGreater(heading["x1"], 300.0)
            self.assertEqual(
                pdf_extract._straddling_lines(page, [300.0], word_kwargs), 20)


class TestRasterExtraction(unittest.TestCase):
    def test_an_extracted_raster_is_not_the_stored_stream(self):
        """Both halves of the claim at once. pypdf re-encodes the DECODED
        pixels into a container that can hold them, so the written file is
        NOT the stored bytes (measured: 0 of 24 placements pass through) --
        and what IS true is that the pixels are the original ones at their
        native resolution, never resampled."""
        import pypdf
        with tempfile.TemporaryDirectory() as tmp:
            out = run(EXTRACT, FIXTURES / "figure.pdf",
                      "--extract-images", tmp)
            self.assertEqual(out.returncode, 0, out.stderr)
            dump = json.loads(out.stdout)
            rasters = [i for p in dump["pages"] for i in p.get("images", [])
                       if i.get("kind") == "raster"]
            self.assertTrue(rasters, "expected an embedded raster")
            record = rasters[0]
            written = Path(record["file"]).read_bytes()
        reader = pypdf.PdfReader(str(FIXTURES / "figure.pdf"))
        stored = None
        for page in reader.pages:
            for image in page.images:
                obj = image.indirect_reference.get_object()
                if (int(obj["/Width"]), int(obj["/Height"])) == \
                        (record["width"], record["height"]):
                    stored = obj
                    break
            if stored is not None:
                break
        self.assertIsNotNone(stored, "raster not found through pypdf")
        self.assertNotEqual(written, bytes(stored._data))
        self.assertEqual(record["width"], int(stored["/Width"]))
        self.assertEqual(record["height"], int(stored["/Height"]))


class TestHelpClaims(unittest.TestCase):
    """`--help` is what an agent reads first, so a false claim there is worse
    than the same sentence in a docstring."""

    def test_the_help_does_not_claim_rasters_are_copied_as_stored(self):
        out = run(EXTRACT, "--help")
        self.assertEqual(out.returncode, 0, out.stderr)
        norm = " ".join(out.stdout.split())     # argparse re-wraps
        self.assertNotIn("copied byte-for-byte as stored", norm)
        self.assertNotIn("copied as stored", norm)
        self.assertIn("not the PDF's stored filter", norm)
        self.assertIn("never resampled", norm)
        # ... and the one byte-for-byte claim that IS true -- about the DUMP,
        # not about a raster -- must survive an over-eager future sweep.
        self.assertIn("byte-for-byte unchanged", norm)


# ------------------------------- the CLI contracts every entry point shares

class TestHumanChannelInstallation(unittest.TestCase):
    """`install_human_channel()` takes no arguments, and that is not cosmetic.

    `_errors.install_human_channel` registers the `_quiet_a_dead_stdout` atexit
    hook ONLY on the no-argument path (`if not streams:`). The two new CLIs
    passed `(sys.stdout, sys.stderr)` explicitly -- reconfiguring the same two
    streams while skipping the hook whose own docstring says that without it
    CPython "replaces the exit status with 120" on a shutdown flush into a dead
    pipe. 34 other call sites in this repository pass nothing.
    """

    SCRIPTS = sorted(pth for pth in SCRIPTS_DIR.glob("*.py")
                     if "install_human_channel(" in
                     pth.read_text(encoding="utf-8"))

    def test_the_scan_found_the_scripts_it_is_about(self):
        """Without this the two assertions below pass over an empty list."""
        names = {pth.name for pth in self.SCRIPTS}
        for expected in ("pdf_extract.py", "pdf_profile.py",
                         "pdf_verify_md.py"):
            self.assertIn(expected, names)

    def test_no_script_passes_streams_explicitly(self):
        for path in self.SCRIPTS:
            with self.subTest(script=path.name):
                self.assertNotIn("install_human_channel(sys.",
                                 path.read_text(encoding="utf-8"))

    def test_it_is_the_first_executable_statement_of_main(self):
        """`--help` is printed by argparse, which catches `AttributeError` and
        `OSError` but NOT `UnicodeEncodeError` -- so one em dash in one `help=`
        string returns rc 1 and zero bytes unless the codec is fixed BEFORE
        `parse_args`. A docstring may precede it; nothing else may."""
        import ast

        checked = 0
        for path in self.SCRIPTS:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            main = next((n for n in tree.body
                         if isinstance(n, ast.FunctionDef) and n.name == "main"),
                        None)
            if main is None:                     # a module that only imports it
                continue
            checked += 1
            with self.subTest(script=path.name):
                body = list(main.body)
                if (isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    body = body[1:]              # the docstring
                first = body[0]
                self.assertIsInstance(first, ast.Expr)
                self.assertIsInstance(first.value, ast.Call)
                self.assertEqual(getattr(first.value.func, "id", None),
                                 "install_human_channel")
                self.assertEqual(first.value.args, [])
                self.assertEqual(first.value.keywords, [])
        self.assertGreaterEqual(checked, 8)

    def test_only_the_no_argument_form_registers_the_broken_pipe_hook(self):
        """The mechanism itself, so the source assertions above are not the
        only thing standing between this repo and exit status 120."""
        import atexit

        import _errors

        before = atexit._ncallbacks()
        _errors.install_human_channel(sys.stdout, sys.stderr)
        explicit = atexit._ncallbacks() - before
        _errors.install_human_channel()
        default = atexit._ncallbacks() - before - explicit
        self.addCleanup(atexit.unregister, _errors._quiet_a_dead_stdout)
        self.assertEqual(explicit, 0)
        self.assertEqual(default, 1)

    def _head_one(self, script, *args):
        """`script ... | head -1`: read one line, close the pipe, collect the
        exit status the way a shell's PIPESTATUS would."""
        proc = subprocess.Popen([str(PY), str(script), *map(str, args)],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        proc.stdout.readline()
        proc.stdout.close()
        stderr = proc.stderr.read()
        proc.stderr.close()
        return proc.wait(), stderr

    def test_both_new_clis_survive_a_dead_stdout(self):
        """120 is what CPython substitutes when the shutdown flush raises, and
        an "Exception ignored while flushing sys.stdout" traceback is what it
        prints on the way. Neither is an acceptable answer from a tool whose
        job is a machine-readable verdict.

        Honest scope: both reports here are under the 64 KB pipe buffer, so
        this pins the exit status and the silence, not a reproduced flush
        failure -- the hook count above is the mechanism."""
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "dump.json"
            md = Path(tmp) / "out.md"
            self.assertEqual(
                run(EXTRACT, FIXTURES / "digital.pdf", "-o", dump).returncode, 0)
            md.write_text("\n".join(pg.get("text") or "" for pg in
                                    json.loads(dump.read_text())["pages"]),
                          encoding="utf-8")
            cases = [(PROFILE, (FIXTURES / "digital.pdf",)),
                     (PROFILE, (FIXTURES / "digital.pdf", "--json")),
                     (VERIFY, (dump, md)),
                     (VERIFY, (dump, md, "--json", "--top", "100000"))]
            for script, args in cases:
                with self.subTest(script=script.name, args=args[1:]):
                    rc, stderr = self._head_one(script, *args)
                    self.assertNotEqual(rc, 120, stderr)
                    self.assertIn(rc, (0, 1), stderr)
                    self.assertNotIn("Exception ignored", stderr)
                    self.assertNotIn("Traceback", stderr)


class TestRotatedFurnitureAccounting(unittest.TestCase):
    """A rotated spine reaches `extract_words` REVERSED (`tfarcecaps`), so it
    can never match the Markdown and every occurrence is loss unless the
    positional rule takes it.

    §8 of the reference explains a 30-page magazine's 301 rotated tokens
    costing only 14 missing ones. What is reproducible here without that
    document is the mechanism the explanation rests on: a string printed in the
    same slot on most pages is furniture by position, whatever its rotation.
    """

    @staticmethod
    def _pdf(scatter):
        import random

        rnd = random.Random(7)

        def draw(c):
            for page in range(10):
                if page:
                    c.showPage()
                c.setFont("Helvetica", 10)
                for i in range(10):
                    x = 120 + (rnd.randint(0, 40) if scatter else 0)
                    y = 700 - i * 20 - (rnd.randint(0, 3) if scatter else 0)
                    c.drawString(x, y, "prose%02d%02d assorted wording %02d"
                                 % (page, i, i))
                c.saveState()
                c.translate(60, 300)
                c.rotate(90)
                c.setFont("Helvetica", 8)
                c.drawString(0, 0, "spacecraft")
                c.restoreState()
        return _canvas_pdf(draw)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _pair(self, scatter):
        import pdfplumber

        pdf = self.dir / "spine.pdf"
        pdf.write_bytes(self._pdf(scatter))
        words = []
        with pdfplumber.open(str(pdf)) as opened:
            for page in opened.pages:
                words += [w["text"] for w in page.extract_words()
                          if w["text"] != "tfarcecaps"]
        md = self.dir / "spine.md"
        md.write_text(" ".join(words), encoding="utf-8")
        return pdf, md

    def test_the_spine_really_arrives_reversed(self):
        """Without this the accounting below could pass because the glyphs
        never made it into the page at all."""
        import pdfplumber

        pdf = self.dir / "spine.pdf"
        pdf.write_bytes(self._pdf(scatter=True))
        with pdfplumber.open(str(pdf)) as opened:
            page = opened.pages[0]
            self.assertEqual(
                [w["text"] for w in page.extract_words()
                 if "craft" in w["text"] or "tfarc" in w["text"]],
                ["tfarcecaps"])

    def test_a_fixed_slot_spine_is_positional_furniture(self):
        """It repeats in one place on every page, so the rule takes it and it
        costs the report nothing -- which is why a document full of rotated
        margin text does not read as a failed conversion."""
        pdf, md = self._pair(scatter=True)
        report = json.loads(run(VERIFY, pdf, md, "--json").stdout)
        self.assertIs(report["furniture_refused"], False)
        self.assertIn("tfarcecaps", report["furniture_vocabulary"])
        self.assertEqual(report["missing_tokens"], 0)

    def test_when_the_rule_refuses_the_spine_is_counted_per_page(self):
        """The other side, and the reason the refusal is loud: with the rule
        off, ten pages of one rotated word are ten missing tokens under one
        reversed key -- never ten separate mysteries."""
        pdf, md = self._pair(scatter=False)
        report = json.loads(run(VERIFY, pdf, md, "--json").stdout)
        self.assertIs(report["furniture_refused"], True)
        self.assertEqual(report["top_missing"], [["tfarcecaps", 10]])


TMP18 = SCRIPTS_DIR.parent.parent.parent / "tmp18"
REAL_DOCS = sorted(TMP18.glob("*.pdf")) if TMP18.is_dir() else []


@unittest.skipUnless(REAL_DOCS, "tmp18/ is gitignored and not present here")
class TestRealDocumentProfile(unittest.TestCase):
    """The two fixed defects at the only level a user sees them: a recommended
    ratio outside its own band, printed next to a sample count that is not the
    one that was asked for."""

    def test_the_ratio_is_inside_its_band_and_the_sample_is_the_one_asked_for(self):
        for path in REAL_DOCS:
            for count in (6, 24):
                with self.subTest(document=path.name, pages=count):
                    out = run(PROFILE, path, "--json", "--pages", count)
                    self.assertEqual(out.returncode, 0, out.stderr)
                    report = json.loads(out.stdout)
                    document = report["document"]
                    self.assertEqual(document["sampled"],
                                     min(count, document["pages"]))
                    spacing = report["spacing"]
                    if spacing["source"] != "labelled":
                        continue
                    band = spacing["safe_band"]
                    self.assertEqual(len(band), 2)
                    self.assertLessEqual(band[0], spacing["ratio"])
                    self.assertLessEqual(spacing["ratio"], band[1])


# ------------------------------------------------- the claims the docs make

SKILL_DIR = SCRIPTS_DIR.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCE_MD = SKILL_DIR / "references" / "pdf-to-markdown.md"
BACKLOG_MD = SKILL_DIR.parent.parent / "docs" / "office-skills-backlog.md"


def _doc(path):
    """The document's text, or a skip. A packaged `.skill` archive carries no
    repository `docs/` tree, and the suite must stay green inside one."""
    if not path.exists():
        raise unittest.SkipTest("not in this checkout: %s" % path)
    return path.read_text(encoding="utf-8")


class TestDocumentationClaims(unittest.TestCase):
    """Two of these findings were measured *in the documentation*: a raster
    branch that promised bytes it does not copy, and a copy-paste gate that
    fails a conversion whose real loss is 15 tokens of 10664. Prose is not
    covered by any other test in this repository."""

    def test_the_docs_do_not_claim_raster_pass_through(self):
        skill, reference = _doc(SKILL_MD), _doc(REFERENCE_MD)
        for phrase in ("copied out byte-for-byte", "copied byte-for-byte",
                       "copied as stored"):
            self.assertNotIn(phrase, skill)
        self.assertNotIn("as stored", reference)
        # The two surviving uses are about the DUMP and are correct: an
        # over-eager sweep that deletes them is a regression too.
        self.assertIn("a dump taken without it is byte-for-byte unchanged",
                      skill)
        self.assertIn("the dump is byte-for-byte what it always was",
                      reference)

    def test_the_max_loss_example_is_three(self):
        """The published 5 exited 1 at loss_pct 8.08 on a good conversion.

        Re-measured: the smallest integer BOTH documents pass is 2 (`--max-loss
        1` exits 1 on the 1.03 % document, `--max-loss 2` exits 0 on both), and
        3 is that plus a point of headroom. This docstring used to claim 3 was
        the smallest, which is arithmetically wrong and is now corrected in the
        prose the assertions below guard."""
        skill, reference = _doc(SKILL_MD), _doc(REFERENCE_MD)
        self.assertNotIn("--max-loss 5", skill)
        self.assertNotIn("--max-loss 5", reference)
        self.assertIn("--max-loss 3", skill)
        self.assertIn("--max-loss 3", reference)

    def test_the_docs_carry_no_retired_measurement(self):
        """Eighteen quantitative claims in this diff's prose were re-measured
        and found false or unreproducible -- a URL/heading mix-up, a rotated
        census that does not reproduce from its own snippet, two crop deltas
        under a silently mixed counting convention, an ink ratio no shipped
        formula produces. Both source corpora are gitignored, so re-running the
        measurement is not available to CI; asserting the retired STRINGS are
        gone is the cheapest lock there is, and it catches the one failure mode
        that matters -- a revert or a copy-paste bringing them back."""
        skill, reference = _doc(SKILL_MD), _doc(REFERENCE_MD)
        retired = [
            "every one of those splits a URL",
            "a smaller one fails a good conversion",
            "tightest inter-word gap is 1.57",
            "tightest inter-word gap measures 1.57",
            "346 rotated tokens", "17 distinct strings", "163 and 15",
            "+1139", "76 218", "102 231", "0.9815",
            "64\u2013188", "0.157\u20130.406",
            "five Chicago-spaced ellipses", "7 URLs shipped",
            "40 line breaks inside URLs", "three orders of magnitude",
            "peak at 0.23 x point size", "pays for itself immediately",
        ]
        for phrase in retired:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, skill)
                self.assertNotIn(phrase, reference)

    def test_the_reference_states_the_provenance_of_its_numbers_once(self):
        """The claims rest on two corpora that ship with neither the repo nor
        the skill (a 1206-page dogfood run and two magazines under a gitignored
        `tmp18/`). Saying so once, at the top, is what keeps every number below
        it honest for a reader who cannot re-run any of them."""
        reference = _doc(REFERENCE_MD)
        self.assertIn("Provenance of the numbers on this page", reference)
        self.assertIn("scripts/tests/fixtures/", reference)

    def test_the_description_names_both_conversion_directions(self):
        """Three scripts and a 1000-line reference exist for pdf -> markdown
        while the trigger line named only the reverse."""
        skill = _doc(SKILL_MD)
        frontmatter = re.search(r"\A---\n(.*?)\n---", skill, re.S)
        self.assertIsNotNone(frontmatter, "SKILL.md has no frontmatter")
        description = re.search(r"^description:\s*(.*)$",
                                frontmatter.group(1), re.M).group(1)
        self.assertIn("markdown to pdf", description)
        # Exactly one copy: the description is already over the skill-creator
        # word guideline, so a second copy is a cost, not a safety margin.
        self.assertEqual(description.count("pdf to markdown"), 1)

    def test_the_reference_records_the_crop_trap_and_the_fourth_limit(self):
        reference = _doc(REFERENCE_MD)
        section = reference[reference.index("### 3.1 "):
                            reference.index("### 3.2 ")]
        # `page.crop` keeps a line's inside half; `within_bbox` deletes it.
        self.assertIn("within_bbox", section)
        # The gutter limit that fires FIRST and was documented nowhere.
        self.assertIn("_COLUMN_EDGE_MARGIN", section)
        # Character preservation checks a cut -- and is blind to a severed
        # table, which preserves every character at delta exactly 0.
        self.assertIn("ruling.pdf", section)

    def test_the_reference_pitfalls_are_numbered_contiguously(self):
        reference = _doc(REFERENCE_MD)
        numbers = [int(n) for n in
                   re.findall(r"^### 3\.(\d+)", reference, re.M)]
        # NOTE: `3.2b` is a lettered sibling of 3.2 and this pattern matches
        # it too, so 2 legitimately appears twice -- measured, and not what
        # the slice report predicted. Everything else must be 1..18, in order.
        self.assertEqual(sorted(set(numbers)), list(range(1, 19)))
        self.assertEqual(numbers, sorted(numbers))
        self.assertEqual(numbers.count(2), 2)
        self.assertEqual(reference.count("### 3.18 "), 1)
        # The numbered pitfalls live before the Non-goals, not after them.
        self.assertLess(reference.index("### 3.18 "), reference.index("## 4. "))

    def test_the_step_numbers_agree_across_the_reference(self):
        reference = _doc(REFERENCE_MD)
        self.assertIn("the value is in step 3 being *yours*", reference)
        self.assertIn("step 4 being a measurement", reference)
        self.assertIn("(§2 step 3)", reference)
        self.assertNotIn("step 5 being a measurement", reference)

    def test_the_backlog_pdf_rows_are_well_formed(self):
        backlog = _doc(BACKLOG_MD).split("\n")
        start = backlog.index("### pdf")
        end = next((i for i in range(start + 1, len(backlog))
                    if backlog[i].startswith("### ")), len(backlog))
        rows = {}
        for line in backlog[start:end]:
            if line.startswith("| pdf-"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                rows.setdefault(cells[0], []).append(cells)
        for ident in ("pdf-16", "pdf-17", "pdf-18", "pdf-19", "pdf-20"):
            with self.subTest(row=ident):
                self.assertIn(ident, rows)
                self.assertEqual(len(rows[ident]), 1, "duplicate row")
                cells = rows[ident][0]
                self.assertEqual(len(cells), 7)
                self.assertTrue(all(cells), "empty cell in %s" % ident)
        self.assertEqual(rows["pdf-20"][0][5], "pdf-16")
        # The expensive one: without this ordering note the hairline-frame
        # rule lands before --image-format and two figures end up with no
        # renderable file at all.
        self.assertIn("СТРОГО РАНЬШЕ", rows["pdf-18"][0][6])

if __name__ == "__main__":
    unittest.main()

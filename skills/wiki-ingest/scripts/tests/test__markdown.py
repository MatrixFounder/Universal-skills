"""Unit tests for `wiki_ingest._markdown` — TASK 015 bead 015-02.

Locks the F2 markdown-engine contract:
- Offset stability under masking (TC-02-1).
- `---` HR no longer terminates a section body (TC-02-2 / L-C3).
- Mask-once invariant in `find_all_sections` (TC-02-3 / OVERLAP-3).
- Wiki-link extraction skips inline code + HTML comments (TC-02-4 / L-H1).
- `_first_sentence` handles common abbreviations (TC-02-5 / L-M4).
"""
from __future__ import annotations

import time
import unittest

from wiki_ingest._markdown import (
    _extract_wikilinks_with_anchors,
    _first_sentence,
    _mask_code_fences,
    _mask_inline_constructs,
    find_all_sections,
    get_section_body,
)


class TestOffsetStabilityUnderMask(unittest.TestCase):
    """TC-UNIT-02-1 — masking must preserve byte offsets and newline positions."""

    SAMPLES = [
        "plain text without anything\n",
        "## Header\n\nbody\n\n## Another\nmore\n",
        "before\n\n```py\ncode here\n## fake header inside fence\n```\n\nafter\n",
        "inline `[[Foo]]` mention and <!-- [[Bar]] --> comment\n",
        "",
    ]

    def test_mask_code_fences_preserves_length(self):
        for s in self.SAMPLES:
            with self.subTest(sample=s[:30]):
                self.assertEqual(
                    len(_mask_code_fences(s)), len(s),
                    "masked length must equal original length",
                )

    def test_mask_code_fences_preserves_newline_positions(self):
        for s in self.SAMPLES:
            with self.subTest(sample=s[:30]):
                masked = _mask_code_fences(s)
                for i, ch in enumerate(s):
                    if ch == "\n":
                        self.assertEqual(
                            masked[i], "\n",
                            f"newline at offset {i} not preserved in mask",
                        )

    def test_mask_inline_constructs_preserves_length(self):
        for s in self.SAMPLES:
            with self.subTest(sample=s[:30]):
                self.assertEqual(len(_mask_inline_constructs(s)), len(s))


class TestSectionBoundaryNoLongerIncludesHR(unittest.TestCase):
    """TC-UNIT-02-2 — `---` horizontal rule must NOT terminate a section body.

    Locks the L-C3 fix from the May 2026 VDD-multi pass: standalone `---`
    inside a section is intentional Markdown content, not a section separator.
    """

    def test_hr_inside_section_is_preserved_in_body(self):
        content = (
            "## Notes\n\n"
            "First paragraph.\n\n"
            "---\n\n"
            "Second paragraph after HR.\n\n"
            "## Footnotes\n\n[^src-x]: foo\n"
        )
        body = get_section_body(content, "Notes")
        self.assertIsNotNone(body, "section must be located")
        assert body is not None  # for type-checkers
        self.assertIn("First paragraph", body)
        self.assertIn("---", body, "HR must be retained inside the section body")
        self.assertIn("Second paragraph after HR", body,
                      "content after the HR must NOT be silently truncated (L-C3)")
        self.assertNotIn("Footnotes", body,
                         "body must still terminate at the next `## ` header")


class TestFindAllSectionsMaskOnceInvariant(unittest.TestCase):
    """TC-UNIT-02-3 — find_all_sections must accept a pre-computed `masked` view
    and return identical results, AND run in linear time on a many-header doc.
    """

    def test_pre_masked_yields_identical_result(self):
        content = "## Foo\nA\n## Bar\nB\n## Foo\nC\n## Foo\nD\n"
        without = find_all_sections(content, "Foo")
        with_masked = find_all_sections(
            content, "Foo", masked=_mask_code_fences(content),
        )
        self.assertEqual(
            without, with_masked,
            "providing a pre-computed masked view must yield identical positions",
        )
        self.assertEqual(len(without), 3, "fixture has three `## Foo` occurrences")

    def test_linear_time_on_10k_headers(self):
        """Synthetic 10 000-`## ` document — must be truly linear (LOW-3).

        Pre-refactor (before OVERLAP-3) this was O(K²·L). The earlier 1.0 s
        ceiling was too loose — it allowed a 10× constant-factor regression
        to ship green. We now ALSO assert the N=10k/N=1k ratio is < 15 so a
        partial reintroduction of quadratic behaviour fails the test even
        on a slow machine where both runs are absolute-fast.
        """
        def _run(n: int) -> float:
            big = "\n".join(f"## H{i}\nbody{i}" for i in range(n))
            t0 = time.perf_counter()
            result = find_all_sections(big, f"H{n // 2}")
            elapsed = time.perf_counter() - t0
            self.assertEqual(len(result), 1)
            return elapsed

        t_small = _run(1_000)
        t_large = _run(10_000)
        # Absolute upper bound — tightened from 1.0 s to 0.25 s
        self.assertLess(
            t_large, 0.25,
            f"find_all_sections on 10k headers took {t_large:.3f}s — "
            f"mask-once invariant broken (OVERLAP-3)",
        )
        # Ratio bound — truly linear should be ~10×; allow 15× headroom for
        # measurement noise. A partial reintroduction of O(K²) would give
        # ~100×, well over the threshold.
        # Avoid divide-by-zero on very fast machines: floor at 1 ms.
        ratio = t_large / max(t_small, 0.001)
        self.assertLess(
            ratio, 15.0,
            f"N=10k vs N=1k ratio = {ratio:.1f}× — expected ~10× for linear "
            f"behaviour; quadratic regression suspected",
        )


class TestWikilinkExtractionMasksInlineAndComments(unittest.TestCase):
    """TC-UNIT-02-4 — `[[X]]` inside inline code / HTML comments / fenced code
    must NOT be reported as a wiki-link reference (L-H1).
    """

    def test_inline_code_link_skipped(self):
        body = "Real [[Foo]] but `[[Bar]]` is inline code only.\n"
        out = _extract_wikilinks_with_anchors(body)
        # Set-equality (not membership) catches over-masking: if the masker
        # over-greedily eats the REAL `[[Foo]]` too, `out` would be empty
        # and a plain `assertNotIn("Bar")` would pass vacuously (LOW-4).
        self.assertEqual(set(out.keys()), {"Foo"},
                         "exactly the real link surfaces; inline-code suppressed")

    def test_html_comment_link_skipped(self):
        body = "Real [[Foo]] and <!-- [[Baz]] --> commented out.\n"
        out = _extract_wikilinks_with_anchors(body)
        self.assertEqual(set(out.keys()), {"Foo"},
                         "HTML-commented link suppressed; real link preserved")

    def test_fenced_code_link_skipped(self):
        body = "Real [[Foo]]\n```\n[[FakeInsideFence]]\n```\n"
        out = _extract_wikilinks_with_anchors(body)
        self.assertEqual(set(out.keys()), {"Foo"},
                         "fenced-code link suppressed; real link preserved")

    def test_anchor_is_surfaced(self):
        body = "See [[Foo#API]] for details and bare [[Foo]] too.\n"
        out = _extract_wikilinks_with_anchors(body)
        self.assertEqual(out["Foo"], {"#API", ""},
                         "both anchored and bare references should aggregate "
                         "under the same target")


class TestFirstSentenceAbbreviations(unittest.TestCase):
    """TC-UNIT-02-5 — common abbreviations must NOT terminate the sentence (L-M4)."""

    CASES = [
        ("Dr. Smith proposed a method. The method worked.",
         "Dr. Smith proposed a method."),
        ("Mr. and Mrs. Foo agreed. Bar was happy.",
         "Mr. and Mrs. Foo agreed."),
        ("Use i.e. inline. Then continue.",
         "Use i.e. inline."),
        ("Just one sentence with no abbreviation here.",
         "Just one sentence with no abbreviation here."),
    ]

    def test_abbreviation_skip(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(_first_sentence(text), expected)

    def test_size_cap_truncates_input(self):
        """The 16 KiB input cap MUST be enforced — locks S-M3.

        Construct an input where the ONLY sentence terminator sits PAST
        offset 16384. If the cap is in place, the truncated text has no
        terminator and the function falls back to the 200-char prefix
        (which is all "x"s, no period). If the cap is removed (regression),
        the function would find the period at offset 20 000 and return a
        ~20 KiB string. Asserting the result is short AND has no period
        proves the cap was honoured.
        """
        # 20 000 x's, then ". And a sentence."
        huge = "x" * 20_000 + ". And a sentence."
        result = _first_sentence(huge)
        self.assertLessEqual(
            len(result), 200,
            "result must respect the 200-char fallback bound when the cap "
            "truncates before any sentence terminator",
        )
        self.assertNotIn(
            ".", result,
            "if `.` appears in the result, the 16 KiB cap was NOT enforced — "
            "the function looked past offset 16384 to find the terminator "
            "(S-M3 regression)",
        )

    def test_size_cap_does_not_OOM_on_huge_input(self):
        """1 MiB single-line input must complete fast (no memory blow-up)."""
        huge = "x" * (1 << 20)  # 1 MiB
        t0 = time.perf_counter()
        result = _first_sentence(huge)
        elapsed = time.perf_counter() - t0
        self.assertLessEqual(len(result), 200)
        self.assertLess(
            elapsed, 0.1,
            f"_first_sentence on 1 MiB took {elapsed:.3f}s — cap should "
            f"short-circuit before any expensive scan",
        )


if __name__ == "__main__":
    unittest.main()

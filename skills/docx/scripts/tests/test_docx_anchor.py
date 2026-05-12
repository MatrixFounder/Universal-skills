"""Unit tests for docx_anchor.py helpers (docx-6 chain).

These tests form the Red state established in task-006-01b.
They turn GREEN as task-006-02 implements and validates the helper
functions. Each stub body is ``self.fail()`` so the CI red bar
SHRINKS monotonically as downstream tasks flip individual stubs.
NOT ``unittest.skip`` — silent skip = 0 failures = false-green.
"""

import unittest

try:
    from docx_anchor import (
        _is_simple_text_run,
        _rpr_key,
        _merge_adjacent_runs,
    )
except ImportError:
    # Helpers added in 006-01a; should already be importable.
    # If import fails, tests still collectable for Red state.
    pass

try:
    from docx_anchor import (
        _replace_in_run,
        _concat_paragraph_text,
        _find_paragraphs_containing_anchor,
    )
except ImportError:
    # Helpers added in 006-02; tests still collectable for Red state.
    pass

from lxml import etree

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = f'xmlns:w="{_W}"'


def _p(inner_xml: str) -> etree._Element:
    """Build a <w:p> element from the given inner XML snippet."""
    return etree.fromstring(
        f'<w:p {_NS}>{inner_xml}</w:p>'
    )


def _run(inner_xml: str) -> etree._Element:
    """Build a <w:r> element from the given inner XML snippet."""
    return etree.fromstring(
        f'<w:r {_NS}>{inner_xml}</w:r>'
    )


class TestExtractedHelpers(unittest.TestCase):
    """Regression of the byte-identical extraction (006-01a).

    These 10 tests turn GREEN as part of 006-02 (when the helpers
    are confirmed importable and behavioural assertions are filled
    in). Until then, self.fail() makes the Red state observable.
    """

    def test_is_simple_text_run_accepts_t_only_run(self):
        run = _run('<w:t>x</w:t>')
        self.assertTrue(_is_simple_text_run(run))

    def test_is_simple_text_run_accepts_rPr_t_run(self):
        run = _run('<w:rPr><w:b/></w:rPr><w:t>x</w:t>')
        self.assertTrue(_is_simple_text_run(run))

    def test_is_simple_text_run_rejects_run_with_drawing(self):
        run = _run('<w:drawing/>')
        self.assertFalse(_is_simple_text_run(run))

    def test_is_simple_text_run_rejects_run_with_fldChar(self):
        run = _run('<w:fldChar w:fldCharType="begin"/>')
        self.assertFalse(_is_simple_text_run(run))

    def test_rpr_key_canonical_serialisation_stable(self):
        run_a = _run('<w:rPr><w:b/></w:rPr><w:t>hello</w:t>')
        run_b = _run('<w:rPr><w:b/></w:rPr><w:t>world</w:t>')
        self.assertEqual(_rpr_key(run_a), _rpr_key(run_b))

    def test_rpr_key_distinguishes_bold_vs_italic(self):
        run_bold = _run('<w:rPr><w:b/></w:rPr><w:t>x</w:t>')
        run_italic = _run('<w:rPr><w:i/></w:rPr><w:t>x</w:t>')
        self.assertNotEqual(_rpr_key(run_bold), _rpr_key(run_italic))

    def test_merge_adjacent_runs_coalesces_identical_rpr(self):
        p = _p(
            '<w:r><w:rPr><w:b/></w:rPr><w:t>foo</w:t></w:r>'
            '<w:r><w:rPr><w:b/></w:rPr><w:t>bar</w:t></w:r>'
        )
        _merge_adjacent_runs(p)
        runs = p.findall(f'{{{_W}}}r')
        self.assertEqual(len(runs), 1)
        t = runs[0].find(f'{{{_W}}}t')
        self.assertEqual(t.text, 'foobar')

    def test_merge_adjacent_runs_skips_non_simple_run(self):
        # Three runs: simple, non-simple (drawing), simple — middle blocks merge.
        p = _p(
            '<w:r><w:t>foo</w:t></w:r>'
            '<w:r><w:drawing/></w:r>'
            '<w:r><w:t>bar</w:t></w:r>'
        )
        _merge_adjacent_runs(p)
        runs = p.findall(f'{{{_W}}}r')
        self.assertEqual(len(runs), 3)

    def test_merge_adjacent_runs_idempotent(self):
        p = _p(
            '<w:r><w:rPr><w:b/></w:rPr><w:t>foo</w:t></w:r>'
            '<w:r><w:rPr><w:b/></w:rPr><w:t>bar</w:t></w:r>'
        )
        _merge_adjacent_runs(p)
        runs_after_first = len(p.findall(f'{{{_W}}}r'))
        _merge_adjacent_runs(p)
        runs_after_second = len(p.findall(f'{{{_W}}}r'))
        self.assertEqual(runs_after_first, runs_after_second)

    def test_merge_adjacent_runs_preserves_xml_space_preserve(self):
        # Merging two runs where combined text has a space should set preserve.
        p = _p(
            '<w:r><w:t>foo </w:t></w:r>'
            '<w:r><w:t>bar</w:t></w:r>'
        )
        _merge_adjacent_runs(p)
        runs = p.findall(f'{{{_W}}}r')
        self.assertEqual(len(runs), 1)
        t = runs[0].find(f'{{{_W}}}t')
        self.assertEqual(t.text, 'foo bar')
        xml_space = t.get('{http://www.w3.org/XML/1998/namespace}space')
        self.assertEqual(xml_space, 'preserve')


class TestReplaceInRun(unittest.TestCase):
    """Tests for ``_replace_in_run`` (added in 006-02)."""

    def test_empty_anchor_returns_zero(self):
        """FIX-1 regression: empty anchor must return 0; paragraph unchanged.

        An empty anchor would cause str.find("", cursor) == cursor forever,
        growing `parts` until OOM. The guard at the top of _replace_in_run
        must prevent that entirely.
        """
        p = _p('<w:r><w:t>hello world</w:t></w:r>')
        count = _replace_in_run(p, '', 'X', anchor_all=True)
        self.assertEqual(count, 0)
        # Paragraph text must be unchanged.
        t = p.find(f'.//{{{_W}}}t')
        self.assertEqual(t.text, 'hello world')

    def test_first_match_default(self):
        # anchor "ab" in "abab", anchor_all=False → count=1, text="Xab"
        p = _p('<w:r><w:t>abab</w:t></w:r>')
        count = _replace_in_run(p, 'ab', 'X', anchor_all=False)
        self.assertEqual(count, 1)
        t = p.find(f'.//{{{_W}}}t')
        self.assertEqual(t.text, 'Xab')

    def test_all_flag_replaces_every_occurrence(self):
        # anchor "ab" in "abab", anchor_all=True → count=2, text="XX"
        p = _p('<w:r><w:t>abab</w:t></w:r>')
        count = _replace_in_run(p, 'ab', 'X', anchor_all=True)
        self.assertEqual(count, 2)
        t = p.find(f'.//{{{_W}}}t')
        self.assertEqual(t.text, 'XX')

    def test_empty_replacement_strips_anchor(self):
        # anchor "foo" in "foobar", replacement="" → count=1, text="bar"
        p = _p('<w:r><w:t>foobar</w:t></w:r>')
        count = _replace_in_run(p, 'foo', '', anchor_all=False)
        self.assertEqual(count, 1)
        t = p.find(f'.//{{{_W}}}t')
        self.assertEqual(t.text, 'bar')

    def test_anchor_at_run_start_preserves_leading_space(self):
        # anchor "May 2024" in " May 2024" with leading space → replacement kept
        p = _p(
            '<w:r><w:t xml:space="preserve"> May 2024</w:t></w:r>'
        )
        count = _replace_in_run(p, 'May 2024', 'June 2024', anchor_all=False)
        self.assertEqual(count, 1)
        t = p.find(f'.//{{{_W}}}t')
        self.assertEqual(t.text, ' June 2024')
        # Leading space → xml:space must be set
        xml_space = t.get('{http://www.w3.org/XML/1998/namespace}space')
        self.assertEqual(xml_space, 'preserve')

    def test_xml_space_preserve_set_when_needed(self):
        # Replacement that produces leading-space text → preserve set.
        p = _p('<w:r><w:t>xfoo</w:t></w:r>')
        _replace_in_run(p, 'x', ' ', anchor_all=False)
        t = p.find(f'.//{{{_W}}}t')
        self.assertEqual(t.text, ' foo')
        xml_space = t.get('{http://www.w3.org/XML/1998/namespace}space')
        self.assertEqual(xml_space, 'preserve')

        # Replacement with no leading/trailing space → attr NOT set.
        p2 = _p('<w:r><w:t>hello world</w:t></w:r>')
        _replace_in_run(p2, 'world', 'there', anchor_all=False)
        t2 = p2.find(f'.//{{{_W}}}t')
        self.assertEqual(t2.text, 'hello there')
        xml_space2 = t2.get('{http://www.w3.org/XML/1998/namespace}space')
        self.assertIsNone(xml_space2)

    def test_no_infinite_loop_when_replacement_contains_anchor(self):
        # anchor "a" replacement "aaa" in "ababa", anchor_all=True → terminates, count=3
        # "ababa" has 'a' at positions 0, 2, 4 (3 occurrences).
        # Cursor advances by len(anchor)=1 past each match in original text,
        # so replacement content is never re-scanned.
        # parts: [""+"aaa", "b"+"aaa", "b"+"aaa", ""] → "aaabaaabaaa"
        p = _p('<w:r><w:t>ababa</w:t></w:r>')
        count = _replace_in_run(p, 'a', 'aaa', anchor_all=True)
        self.assertEqual(count, 3)
        t = p.find(f'.//{{{_W}}}t')
        self.assertEqual(t.text, 'aaabaaabaaa')

    def test_cursor_advances_past_replacement_for_all_flag(self):
        # Same as above — also verifies no double-replacement on inserted "aaa".
        p = _p('<w:r><w:t>ababa</w:t></w:r>')
        count = _replace_in_run(p, 'a', 'aaa', anchor_all=True)
        # Exactly 3 originals replaced (positions 0, 2, 4 in source text).
        self.assertEqual(count, 3)
        t = p.find(f'.//{{{_W}}}t')
        # No extra replacements from the inserted "aaa".
        self.assertEqual(t.text, 'aaabaaabaaa')

    def test_anchor_spanning_runs_returns_zero(self):
        # Anchor "Article 5" split across two runs with DIFFERENT rPr.
        # Merge cannot combine them (different rPr). _replace_in_run returns 0.
        p = _p(
            '<w:r><w:rPr><w:b/></w:rPr><w:t>Article </w:t></w:r>'
            '<w:r><w:rPr><w:i/></w:rPr><w:t>5</w:t></w:r>'
        )
        count = _replace_in_run(p, 'Article 5', 'X', anchor_all=False)
        self.assertEqual(count, 0)


class TestConcatParagraphText(unittest.TestCase):
    """Tests for ``_concat_paragraph_text`` (added in 006-02)."""

    def test_concat_simple_paragraph(self):
        p = _p('<w:r><w:t>hello</w:t></w:r>')
        self.assertEqual(_concat_paragraph_text(p), 'hello')

    def test_concat_includes_ins_content(self):
        p = _p(
            '<w:ins w:id="1" w:author="A" w:date="2024-01-01T00:00:00Z">'
            '<w:r><w:t>foo</w:t></w:r>'
            '</w:ins>'
            '<w:r><w:t>bar</w:t></w:r>'
        )
        self.assertEqual(_concat_paragraph_text(p), 'foobar')

    def test_concat_excludes_del_content(self):
        p = _p(
            '<w:del w:id="1" w:author="A" w:date="2024-01-01T00:00:00Z">'
            '<w:r><w:t>foo</w:t></w:r>'
            '</w:del>'
            '<w:r><w:t>bar</w:t></w:r>'
        )
        self.assertEqual(_concat_paragraph_text(p), 'bar')

    def test_concat_handles_empty_paragraph(self):
        p = etree.fromstring(f'<w:p {_NS}/>')
        self.assertEqual(_concat_paragraph_text(p), '')


class TestFindParagraphsContainingAnchor(unittest.TestCase):
    """Tests for ``_find_paragraphs_containing_anchor`` (added in 006-02)."""

    def _body(self, *paragraphs_xml: str) -> etree._Element:
        """Build a <w:body> containing the given <w:p> snippets."""
        inner = ''.join(paragraphs_xml)
        return etree.fromstring(
            f'<w:body {_NS}>{inner}</w:body>'
        )

    def test_empty_anchor_returns_empty_list(self):
        """FIX-1 regression: empty anchor must return [] not match everything.

        Without the guard, empty anchor would match every paragraph because
        '' in any_string is always True. The guard at the top of
        _find_paragraphs_containing_anchor must prevent this.
        """
        body = self._body(
            '<w:p><w:r><w:t>hello world</w:t></w:r></w:p>',
            '<w:p><w:r><w:t>foo bar</w:t></w:r></w:p>',
        )
        result = _find_paragraphs_containing_anchor(body, '')
        self.assertEqual(result, [])

    def test_returns_empty_list_when_no_match(self):
        body = self._body(
            '<w:p><w:r><w:t>hello world</w:t></w:r></w:p>',
            '<w:p><w:r><w:t>foo bar</w:t></w:r></w:p>',
        )
        result = _find_paragraphs_containing_anchor(body, 'Article 5')
        self.assertEqual(result, [])

    def test_returns_paragraphs_in_document_order(self):
        body = self._body(
            '<w:p><w:r><w:t>See Article 5 for details.</w:t></w:r></w:p>',
            '<w:p><w:r><w:t>No match here.</w:t></w:r></w:p>',
            '<w:p><w:r><w:t>Article 5 applies also here.</w:t></w:r></w:p>',
        )
        result = _find_paragraphs_containing_anchor(body, 'Article 5')
        self.assertEqual(len(result), 2)
        # Verify document order: first matched paragraph comes first.
        first_t = result[0].find(f'.//{{{_W}}}t')
        self.assertIn('See Article 5', first_t.text)
        second_t = result[1].find(f'.//{{{_W}}}t')
        self.assertIn('Article 5 applies', second_t.text)

    def test_concat_text_match_crosses_runs(self):
        # Paragraph with anchor "Article 5" split across 3 runs.
        body = self._body(
            '<w:p>'
            '<w:r><w:t>See </w:t></w:r>'
            '<w:r><w:t>Article </w:t></w:r>'
            '<w:r><w:t>5 for details.</w:t></w:r>'
            '</w:p>'
        )
        result = _find_paragraphs_containing_anchor(body, 'Article 5')
        self.assertEqual(len(result), 1)

    def test_skips_paragraphs_inside_del_runs(self):
        # Paragraph whose entire text is inside <w:del> → concat returns "" → no match.
        body = self._body(
            '<w:p>'
            '<w:del w:id="1" w:author="A" w:date="2024-01-01T00:00:00Z">'
            '<w:r><w:t>Article 5 deleted text</w:t></w:r>'
            '</w:del>'
            '</w:p>'
        )
        result = _find_paragraphs_containing_anchor(body, 'Article 5')
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()

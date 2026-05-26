"""Unit tests for `wiki_ingest._page_merge` — TASK 016 bead 016-01.

Tests the four additive-merge primitives in isolation (not via the CLI
surface). Existing `tests/commands/test_upsert_page.py` continues to
cover the CLI integration path.
"""
from __future__ import annotations

import unittest

from wiki_ingest._page_merge import (
    append_contradiction,
    append_fact,
    upsert_footnote,
    upsert_source_row,
)


PAGE_TEMPLATE = (
    "---\nname: Foo\nkind: concept\n---\n"
    "# Foo\n\n"
    "## Definition\n\n"
    "A thing.\n\n"
    "## Sources mentioning this\n\n"
    "- [[s1]] — 2024-01-01 — Source One\n\n"
    "## Footnotes\n\n"
    "[^src-s1]: [[s1]] — Source One\n"
)


class TestUpsertSourceRow(unittest.TestCase):
    """TC-UNIT-016-01-01..02"""

    def test_dedupes_by_slug(self):
        out = upsert_source_row(PAGE_TEMPLATE, "s1", "Source One", "2024-01-01")
        self.assertEqual(out, PAGE_TEMPLATE,
                         "re-adding the same slug must be a no-op")

    def test_appends_new_slug(self):
        out = upsert_source_row(PAGE_TEMPLATE, "s2", "Source Two", "2024-02-02")
        self.assertIn("[[s2]]", out)
        self.assertIn("Source Two", out)
        # Original row preserved
        self.assertIn("[[s1]]", out)


class TestAppendFact(unittest.TestCase):
    """TC-UNIT-016-01-03"""

    def test_appends_fact_with_citation(self):
        out = append_fact(PAGE_TEMPLATE, "X equals 42", "s1")
        self.assertIn("## Facts", out)
        self.assertIn("- X equals 42 [^src-s1]", out)

    def test_idempotent_on_duplicate_fact(self):
        once = append_fact(PAGE_TEMPLATE, "X equals 42", "s1")
        twice = append_fact(once, "X equals 42", "s1")
        self.assertEqual(once, twice,
                         "re-adding the same fact line must be a no-op")


class TestAppendContradiction(unittest.TestCase):
    """TC-UNIT-016-01-04"""

    def test_wraps_both_claims_in_block(self):
        out = append_contradiction(PAGE_TEMPLATE,
                                   "X equals 42 [^src-s1]",
                                   "X equals 43",
                                   "s2")
        self.assertIn("## Contradictions", out)
        self.assertIn("⚠️", out)
        self.assertIn("Existing claim: X equals 42", out)
        self.assertIn("New claim from [[s2]]: X equals 43 [^src-s2]", out)

    def test_idempotent_on_duplicate_contradiction(self):
        once = append_contradiction(PAGE_TEMPLATE,
                                    "X equals 42 [^src-s1]",
                                    "X equals 43",
                                    "s2")
        twice = append_contradiction(once,
                                     "X equals 42 [^src-s1]",
                                     "X equals 43",
                                     "s2")
        self.assertEqual(once, twice)


class TestUpsertFootnote(unittest.TestCase):
    """TC-UNIT-016-01-05..06"""

    def test_dedupes_by_full_line(self):
        out = upsert_footnote(PAGE_TEMPLATE, "s1", "Source One")
        self.assertEqual(out, PAGE_TEMPLATE)

    def test_dedupes_by_key_even_if_title_differs(self):
        # Existing line is `[^src-s1]: [[s1]] — Source One`
        # Caller passes the same key with a different title — must NOT
        # double-add (key-level dedupe).
        out = upsert_footnote(PAGE_TEMPLATE, "s1", "Different Title")
        self.assertEqual(out, PAGE_TEMPLATE)

    def test_appends_new_footnote(self):
        out = upsert_footnote(PAGE_TEMPLATE, "s2", "Source Two")
        self.assertIn("[^src-s2]: [[s2]] — Source Two", out)
        # Original footnote preserved
        self.assertIn("[^src-s1]: [[s1]] — Source One", out)


if __name__ == "__main__":
    unittest.main()

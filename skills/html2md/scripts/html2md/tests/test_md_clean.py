"""Post-turndown Markdown tidy pass (md_clean.tidy_markdown). Stdlib-only."""
from __future__ import annotations

import os
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md.md_clean import tidy_markdown  # noqa: E402


class TestTidyMarkdown(unittest.TestCase):
    def test_empty_heading_merged_with_following_text(self):
        out = tidy_markdown("### \n\nPagination\n\nBody text here.\n")
        self.assertIn("### Pagination", out)
        self.assertNotRegex(out, r"(?m)^#{1,6}[ \t]*$")  # no empty heading left

    def test_empty_heading_dropped_before_nonprose(self):
        out = tidy_markdown("### \n\n```\ncode\n```\n")
        self.assertNotRegex(out, r"(?m)^#{1,6}[ \t]*$")
        self.assertIn("```", out)
        self.assertIn("code", out)

    def test_real_headings_untouched(self):
        out = tidy_markdown("## Retrieve mids\n\ntext\n")
        self.assertIn("## Retrieve mids", out)

    def test_chrome_lines_removed(self):
        md = "Copy\n\nReal content.\n\nAsk AI\n\n⌘K\n\nWas this page helpful?\n\nYesNo\n"
        out = tidy_markdown(md)
        self.assertIn("Real content.", out)
        for noise in ("Copy", "Ask AI", "⌘K", "Was this page helpful?", "YesNo"):
            self.assertNotRegex(out, rf"(?m)^{__import__('re').escape(noise)}$")

    def test_chrome_prefix_removed(self):
        out = tidy_markdown("Built with Fern\n\nkeep me\n\nLast updated 2 months ago\n")
        self.assertIn("keep me", out)
        self.assertNotIn("Built with Fern", out)
        self.assertNotIn("Last updated", out)

    def test_content_links_and_tables_preserved(self):
        md = "[real link](https://x)\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
        out = tidy_markdown(md)
        self.assertIn("[real link](https://x)", out)
        self.assertIn("| A | B |", out)
        self.assertIn("| 1 | 2 |", out)

    def test_generic_words_preserved(self):
        """Bare generic words are NOT chrome (could be real content) — kept verbatim."""
        md = "Menu\n\nNavigation\n\nAssistant\n\nYes No\n"
        out = tidy_markdown(md)
        for word in ("Menu", "Navigation", "Assistant", "Yes No"):
            self.assertIn(word, out, f"{word!r} was wrongly stripped")

    def test_blank_runs_collapsed(self):
        out = tidy_markdown("a\n\n\n\n\nb\n")
        self.assertEqual(out, "a\n\nb\n")

    def test_copy_does_not_eat_word_inside_sentence(self):
        # "Copy" only stripped as a STANDALONE line, never mid-sentence.
        out = tidy_markdown("Click Copy to copy the snippet.\n")
        self.assertIn("Click Copy to copy the snippet.", out)


if __name__ == "__main__":
    unittest.main()

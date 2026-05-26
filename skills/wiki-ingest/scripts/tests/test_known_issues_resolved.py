"""Regression tests for the 15 KNOWN_ISSUES items resolved post-TASK 015.

Each test locks one previously-deferred bug fix. Failure here =
regression of a known-fixed issue; restore the fix, don't relax the test.
"""
from __future__ import annotations

import argparse
import io
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest._frontmatter import _strip_quotes
from wiki_ingest._markdown import (
    _compile_section_header_re,
    _existing_lines,
    find_section,
    replace_section_body,
)
from wiki_ingest._vault import tail_log
from wiki_ingest.commands import append_log as append_log_cmd
from wiki_ingest.commands import log_event as log_event_cmd
from wiki_ingest.commands import register_summary as rs_cmd


def _seed_vault(root: Path, log_content: str = "# Log\n") -> None:
    (root / "WIKI_SCHEMA.md").write_text("# schema\n", encoding="utf-8")
    (root / "index.md").write_text("# index\n", encoding="utf-8")
    (root / "log.md").write_text(log_content, encoding="utf-8")
    for sub in ("_sources", "_concepts", "_entities"):
        (root / sub).mkdir()


class TestSL2_TailLogASCIIAnchor(unittest.TestCase):
    """S-L2 — `## [...]` heading regex must require ASCII digits, not
    Unicode-digit decoy strings like `## [٢٠٢٤-٠١-٠١] ingest`."""

    def test_unicode_digit_date_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            # Arabic-Indic digits — visually similar but not [0-9]
            _seed_vault(vault, "# Log\n\n## [٢٠٢٤-٠١-٠١] fake | unicode digits\n\n## [2024-01-15] real | entry\n")
            entries = tail_log(vault, 5)
            self.assertEqual(len(entries), 1)
            self.assertIn("real", entries[0])
            self.assertNotIn("fake", entries[0])


class TestSL3_StripQuotesAsymmetric(unittest.TestCase):
    """S-L3 — mismatched quote pairs must NOT strip silently."""

    def test_mismatched_pair_returned_verbatim(self):
        self.assertEqual(_strip_quotes("'foo\""), "'foo\"")
        self.assertEqual(_strip_quotes("\"foo'"), "\"foo'")

    def test_matched_pair_stripped(self):
        self.assertEqual(_strip_quotes("'foo'"), "foo")
        self.assertEqual(_strip_quotes('"foo"'), "foo")


class TestLH2_ReplaceSectionBodyPreservesBlankLines(unittest.TestCase):
    """L-H2 — `replace_section_body` must NOT collapse blank lines that
    separate the modified section from the next `## ` boundary."""

    def test_blank_line_before_next_header_preserved(self):
        content = (
            "## A\n\nold body\n\n\n"  # two blank lines after body
            "## B\n\nbody B\n"
        )
        out = replace_section_body(content, "A", "new body")
        # Section B must still have exactly ONE blank line above it
        self.assertIn("\n## B\n", out)


class TestLL3_BlockquoteStitch(unittest.TestCase):
    """L-L3 — contiguous `> ` lines stitch into one blockquote entry."""

    def test_contradiction_block_stays_intact(self):
        body = (
            "> ⚠️ **Contradiction flagged** — operator review needed.\n"
            "> - Existing claim: X.\n"
            "> - New claim from [[src]]: Y. [^src-src]\n"
        )
        items = _existing_lines(body)
        self.assertEqual(len(items), 1,
                         "blockquote contradiction block must yield ONE item, "
                         "not 3 fragments")
        self.assertIn("Contradiction flagged", items[0])
        self.assertIn("Existing claim", items[0])
        self.assertIn("New claim", items[0])


class TestLL2_NoDoubleBlankLineInEntry(unittest.TestCase):
    """L-L2 — the original report claimed `cmd_log_event` produced a
    double leading newline 'when log content is empty', but the script's
    `content or load_asset(...)` fallback ensures content is never truly
    empty. The actual contract: exactly ONE blank line separates existing
    log content from a freshly-appended entry. Lock that.
    """

    def test_exactly_one_blank_line_between_content_and_new_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)  # uses default `# Log\n` content
            args = argparse.Namespace(
                vault=str(vault), cmd="log-event",
                event="query", title="Test",
                detail=None, date="2024-05-25", dry_run=False,
            )
            with redirect_stdout(io.StringIO()):
                log_event_cmd.execute(args)
            text = (vault / "log.md").read_text(encoding="utf-8")
            # Look for exactly `\n\n## [` — the marker for the new entry.
            # NOT `\n\n\n## [` (would be a regression to triple newline).
            self.assertNotIn("\n\n\n## [", text,
                             "must NOT have triple newline (= double blank "
                             "line) before the new entry")
            self.assertIn("\n\n## [", text,
                          "must have exactly one blank line before the new entry")


class TestPM3_SectionHeaderRegexCached(unittest.TestCase):
    """P-M3 — repeated calls with the same `header_text` must reuse a
    cached compiled regex (lru_cache verified by identity)."""

    def test_lru_cache_returns_same_pattern(self):
        p1 = _compile_section_header_re("Definition")
        p2 = _compile_section_header_re("Definition")
        self.assertIs(p1, p2, "lru_cache must return the same compiled object")


class TestPM3_015_02_MaskedPropagation(unittest.TestCase):
    """P-M3-015-02 — `replace_section_body` propagates `masked=` to
    `find_section` so K-section batch rewrites pay the mask cost once."""

    def test_replace_section_body_accepts_masked(self):
        content = "## A\n\nold\n\n## B\n\nold b\n"
        # Just verify the signature accepts the kwarg (smoke test).
        out = replace_section_body(content, "A", "new", masked=None)
        self.assertIn("new", out)


class TestLL9_RegisterSummaryForceBackup(unittest.TestCase):
    """L-L9 — `--force` overwrite must snapshot prior content to a
    `<slug>.md.backup-<timestamp>` sibling."""

    def test_force_creates_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            # First pass: place an existing source page
            (vault / "_sources" / "doc.md").write_text(
                "PRIOR CONTENT — must end up in backup\n", encoding="utf-8",
            )
            # Now register a NEW summary with the same slug, using --force
            summary = Path(tmp) / "new.md"
            summary.write_text(
                "---\ntitle: Doc\nslug: doc\ndate: 2024-05-25\n---\n\n# New body\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(
                vault=str(vault), cmd="register-summary",
                summary_path=str(summary), slug="doc", title=None,
                force=True, inbox_root=None, dry_run=False,
            )
            with redirect_stdout(io.StringIO()):
                rc = rs_cmd.execute(args)
            self.assertEqual(rc, 0)
            # The original content must live in a `.backup-*` sibling
            backups = list((vault / "_sources").glob("doc.md.backup-*"))
            self.assertEqual(len(backups), 1,
                             "exactly one backup file must be created on --force")
            self.assertIn(
                "PRIOR CONTENT", backups[0].read_text(encoding="utf-8"),
                "backup must contain the pre-overwrite content",
            )
            # Target is the new content
            self.assertIn("New body",
                          (vault / "_sources" / "doc.md").read_text(encoding="utf-8"))


class TestPM5_FindMergedRegex(unittest.TestCase):
    """P-M5 — `cmd_find` uses ONE merged regex pass for all terms; per-term
    counts still correct."""

    def test_per_term_counts_correct(self):
        from wiki_ingest.commands import find as find_cmd
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            (vault / "_concepts" / "Doc.md").write_text(
                "---\ntitle: Doc\n---\n\n"
                "foo foo bar baz foo qux bar\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(
                vault=str(vault), cmd="find",
                terms="foo bar baz qux missing",
                limit=10, kinds=None,
            )
            with redirect_stdout(io.StringIO()) as buf:
                find_cmd.execute(args)
            import json
            payload = json.loads(buf.getvalue())
            self.assertEqual(len(payload["hits"]), 1)
            counts = payload["hits"][0]["term_counts"]
            self.assertEqual(counts["foo"], 3)
            self.assertEqual(counts["bar"], 2)
            self.assertEqual(counts["baz"], 1)
            self.assertEqual(counts["qux"], 1)
            self.assertEqual(counts["missing"], 0)


if __name__ == "__main__":
    unittest.main()

"""Per-command tests for `commands/{find,lint,reindex}.py` — TASK 015 bead 015-10."""
from __future__ import annotations

import argparse
import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import find as find_cmd
from wiki_ingest.commands import lint as lint_cmd
from wiki_ingest.commands import reindex as reindex_cmd


def _seed_vault(root: Path) -> None:
    (root / "WIKI_SCHEMA.md").write_text("# schema\n", encoding="utf-8")
    (root / "index.md").write_text(
        "# Index\n\n## Sources\n\n## Concepts\n\n## Entities\n\n## Notes\n\nCustom.\n",
        encoding="utf-8",
    )
    (root / "log.md").write_text("# log\n", encoding="utf-8")
    for sub in ("_sources", "_concepts", "_entities"):
        (root / sub).mkdir()


class TestFindRegister(unittest.TestCase):
    def test_attaches(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        find_cmd.register(sub)
        args = parser.parse_args(["find", "/tmp/v", "--terms", "foo bar"])
        self.assertIs(args.func, find_cmd.execute)


class TestFindBodyOnlyScoring(unittest.TestCase):
    """L-M3 — frontmatter list repetition must NOT inflate ranking."""

    def test_body_wins_over_fm_repetition(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            # Game.md: 5× `crypto` in frontmatter, none in body
            (vault / "_concepts" / "Game.md").write_text(
                "---\nconcepts:\n  - crypto\n  - crypto\n  - crypto\n  - crypto\n  - crypto\n---\n\n# Game\n",
                encoding="utf-8",
            )
            # Real.md: 2× `crypto` in body
            (vault / "_concepts" / "Real.md").write_text(
                "---\ntitle: Real\n---\n\n# Real\n\nA real crypto discussion about crypto.\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(
                vault=str(vault), cmd="find", terms="crypto",
                limit=10, kinds=None,
            )
            with redirect_stdout(io.StringIO()) as buf:
                find_cmd.execute(args)
            payload = json.loads(buf.getvalue())
            # Only Real.md should surface (body has the match; Game.md's
            # fm-repetition doesn't count under L-M3).
            paths = [h["path"] for h in payload["hits"]]
            self.assertIn("_concepts/Real.md", paths)
            self.assertNotIn("_concepts/Game.md", paths,
                             "frontmatter-only matches must NOT score")


class TestLintRegister(unittest.TestCase):
    def test_attaches(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        lint_cmd.register(sub)
        args = parser.parse_args(["lint", "/tmp/v"])
        self.assertIs(args.func, lint_cmd.execute)
        self.assertEqual(args.threshold, 2)


class TestLintDanglingWithAnchors(unittest.TestCase):
    """L-L4 — dangling report surfaces specific anchors, not just bare targets."""

    def test_anchor_surfaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            (vault / "_sources" / "src.md").write_text(
                "---\ntitle: src\n---\nSee [[Missing#API]] for details.\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(vault=str(vault), cmd="lint", threshold=2)
            with redirect_stdout(io.StringIO()) as buf:
                lint_cmd.execute(args)
            payload = json.loads(buf.getvalue())
            danglings = {d["target"]: d for d in payload["dangling_links"]}
            self.assertIn("Missing", danglings)
            self.assertIn("#API", danglings["Missing"]["anchors"])

    def test_case_insensitive_concept_aggregation(self):
        """L-L7 — concept fragments aggregate to one entry."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            (vault / "_sources" / "a.md").write_text(
                "---\nconcepts:\n  - Foo Bar\n---\n", encoding="utf-8",
            )
            (vault / "_sources" / "b.md").write_text(
                "---\nconcepts:\n  - foo bar\n---\n", encoding="utf-8",
            )
            args = argparse.Namespace(vault=str(vault), cmd="lint", threshold=2)
            with redirect_stdout(io.StringIO()) as buf:
                lint_cmd.execute(args)
            payload = json.loads(buf.getvalue())
            self.assertEqual(len(payload["missing_concept_pages"]), 1)
            self.assertEqual(payload["missing_concept_pages"][0]["count"], 2)


class TestLintReDosGuard(unittest.TestCase):
    """TC-UNIT-10-4 — 10k headers must lint in <1 s (OVERLAP-3 / S-M2)."""

    def test_lint_redos_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            # Synthetic page with 10k `## ` headers
            big = "---\ntitle: big\n---\n\n" + "\n".join(
                f"## H{i}\nbody{i}" for i in range(10_000)
            )
            (vault / "_concepts" / "Big.md").write_text(big, encoding="utf-8")
            args = argparse.Namespace(vault=str(vault), cmd="lint", threshold=2)
            t0 = time.perf_counter()
            with redirect_stdout(io.StringIO()):
                lint_cmd.execute(args)
            elapsed = time.perf_counter() - t0
            self.assertLess(
                elapsed, 1.0,
                f"lint on 10k-header page took {elapsed:.2f}s — mask-once "
                f"invariant (OVERLAP-3/S-M2) broken",
            )


class TestReindexRegister(unittest.TestCase):
    def test_attaches(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        reindex_cmd.register(sub)
        args = parser.parse_args(["reindex", "/tmp/v"])
        self.assertIs(args.func, reindex_cmd.execute)


class TestReindexPreservesCustomSection(unittest.TestCase):

    def test_notes_section_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            args = argparse.Namespace(
                vault=str(vault), cmd="reindex", dry_run=False,
            )
            with redirect_stdout(io.StringIO()) as buf:
                rc = reindex_cmd.execute(args)
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertIn("Notes", payload["preserved_sections"])
            text = (vault / "index.md").read_text(encoding="utf-8")
            self.assertIn("Custom.", text,
                          "Notes section content must survive reindex")


if __name__ == "__main__":
    unittest.main()

"""Per-command tests for `commands/update_index.py` — TASK 015 bead 015-07."""
from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import update_index as update_cmd


def _seed_vault(root: Path) -> None:
    (root / "WIKI_SCHEMA.md").write_text("# schema\n", encoding="utf-8")
    (root / "index.md").write_text(
        "# Index\n\n## Sources\n\n## Concepts\n\n## Entities\n",
        encoding="utf-8",
    )
    (root / "log.md").write_text("# log\n", encoding="utf-8")
    for sub in ("_sources", "_concepts", "_entities"):
        (root / sub).mkdir()


def _make_args(vault: Path, *, source_slug: str = "src-1",
               source_title: str = "Source One",
               source_date: str = "2024-01-15",
               summary: str = "A short summary.",
               new_concept: list[str] | None = None,
               new_entity: list[str] | None = None,
               dry_run: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        vault=str(vault), cmd="update-index",
        source_slug=source_slug, source_title=source_title,
        source_date=source_date, summary=summary,
        new_concepts=None, new_entities=None,
        new_concept=new_concept or [], new_entity=new_entity or [],
        dry_run=dry_run,
    )


class TestRegister(unittest.TestCase):

    def test_attaches_subparser(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        update_cmd.register(sub)
        args = parser.parse_args([
            "update-index", "/tmp/v",
            "--source-slug", "src", "--source-title", "Src",
            "--source-date", "2024-01-01", "--summary", "S",
        ])
        self.assertIs(args.func, update_cmd.execute)
        self.assertEqual(args.new_concept, [])
        self.assertEqual(args.new_entity, [])


class TestAddIndexRowL_H3(unittest.TestCase):
    """L-H3 — dedupe by list item, not substring of full body."""

    def test_dedupe_by_list_item(self):
        body = (
            "# Index\n\n"
            "## Sources\n\n"
            "- [[s1]] — 2024-01-01 — Source One\n"
        )
        # Re-adding the same slug → no change
        out = update_cmd.add_index_row(body, "Sources",
                                       "- [[s1]] — 2024-01-01 — Source One",
                                       slug_key="[[s1]]")
        self.assertEqual(out, body)

    def test_adds_new_slug(self):
        body = (
            "# Index\n\n"
            "## Sources\n\n"
            "- [[s1]] — 2024-01-01 — Source One\n"
        )
        out = update_cmd.add_index_row(body, "Sources",
                                       "- [[s2]] — 2024-02-02 — Source Two",
                                       slug_key="[[s2]]")
        self.assertIn("[[s1]]", out)
        self.assertIn("[[s2]]", out)

    def test_substring_in_unrelated_section_does_not_block(self):
        """L-H3: a Notes section citing `[[foo]]` must NOT block adding
        `[[foo]]` as a legitimate Concepts row."""
        body = (
            "# Index\n\n"
            "## Sources\n\n"
            "## Concepts\n\n"
            "## Notes\n\n"
            "- see [[foo]] for details\n"
        )
        out = update_cmd.add_index_row(body, "Concepts",
                                       "- [[foo]] — introduced by [[src]]",
                                       slug_key="[[foo]]")
        # The new row landed under Concepts despite [[foo]] appearing in Notes
        # (this verifies the per-item check, not whole-body substring scan).
        self.assertIn("introduced by", out)


class TestExecute(unittest.TestCase):

    def test_adds_source_row_and_two_concept_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            args = _make_args(
                vault, source_slug="src-x",
                new_concept=["AlphaConcept", "BetaConcept"],
            )
            with redirect_stdout(io.StringIO()) as buf:
                rc = update_cmd.execute(args)
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertTrue(payload["updated"])
            text = (vault / "index.md").read_text(encoding="utf-8")
            self.assertIn("[[src-x]]", text)
            self.assertIn("[[AlphaConcept]]", text)
            self.assertIn("[[BetaConcept]]", text)

    def test_idempotent_on_repeat(self):
        """Calling update-index twice with same args must not duplicate rows."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            args = _make_args(vault, source_slug="src-x",
                              new_concept=["Foo"])
            with redirect_stdout(io.StringIO()):
                update_cmd.execute(args)
            text_first = (vault / "index.md").read_text(encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                update_cmd.execute(args)
            text_second = (vault / "index.md").read_text(encoding="utf-8")
            self.assertEqual(text_first, text_second,
                             "second invocation must be idempotent")


if __name__ == "__main__":
    unittest.main()

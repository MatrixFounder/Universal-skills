"""Per-command tests for `commands/demote.py` — TASK 016 bead 016-07."""
from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import demote as demote_cmd
from wiki_ingest.commands import promote as promote_cmd


def _write_schema(path: Path, version: str, kind: str) -> None:
    path.write_text(
        f"---\nschema_version: \"{version}\"\nkind: {kind}\n---\n# Schema\n",
        encoding="utf-8",
    )


def _seed_course(course_root: Path) -> None:
    course_root.mkdir(parents=True, exist_ok=True)
    _write_schema(course_root / "WIKI_SCHEMA.md", "1.0", "course")
    for sub in ("_sources", "_concepts", "_entities"):
        (course_root / sub).mkdir(exist_ok=True)
    (course_root / "index.md").write_text(
        "## Concepts\n\n## Entities\n", encoding="utf-8")
    (course_root / "log.md").write_text("# Log\n", encoding="utf-8")


def _seed_two_tier_with_promoted_page(tmp: Path) -> Path:
    """Build a vault where Sharpe has already been promoted to root."""
    vault = tmp / "vault"
    vault.mkdir()
    _write_schema(vault / "WIKI_SCHEMA.md", "2.0", "vault-root")
    (vault / "_concepts").mkdir()
    (vault / "_entities").mkdir()
    _seed_course(vault / "Lessons" / "A")
    _seed_course(vault / "Lessons" / "B")
    # Course A has the source page
    (vault / "Lessons" / "A" / "_sources" / "a-foo.md").write_text(
        "## a foo\n", encoding="utf-8")
    # Root has the promoted page (only A cites it; A's index has shared)
    (vault / "_concepts" / "Sharpe.md").write_text(
        "---\n"
        "name: Sharpe\n"
        "kind: concept\n"
        "created: 2026-01-01\n"
        "promoted_from:\n"
        "  - course: A\n"
        "    date: 2026-05-26\n"
        "---\n"
        "# Sharpe\n\n"
        "## Definition\n\n"
        "The Sharpe ratio. [^src-a-foo]\n\n"
        "## Footnotes\n\n"
        "[^src-a-foo]: [[Lessons/A/_sources/a-foo]] — Source A\n",
        encoding="utf-8",
    )
    # Course A index has Sharpe under Shared concepts referenced
    (vault / "Lessons" / "A" / "index.md").write_text(
        "## Concepts\n\n"
        "## Entities\n\n"
        "## Shared concepts referenced\n\n"
        "- [[Sharpe]]\n",
        encoding="utf-8",
    )
    # Root index has Sharpe
    (vault / "index.md").write_text(
        "# Vault\n\n## Concepts\n\n- [[Sharpe]]\n\n## Entities\n",
        encoding="utf-8")
    return vault


def _run_demote(name: str, vault: Path, to_course: str,
                dry_run: bool = False) -> tuple[int, dict | None]:
    args = argparse.Namespace(
        name=name, vault=str(vault), to_course=to_course,
        dry_run=dry_run, cmd="demote",
    )
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = demote_cmd.execute(args)
    except SystemExit as e:
        return int(e.code or 0), None
    return rc, json.loads(buf.getvalue())


class TestRegister(unittest.TestCase):

    def test_attaches_subparser(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        demote_cmd.register(sub)
        args = parser.parse_args(
            ["demote", "Foo", "--vault", "/tmp/v", "--to", "A"])
        self.assertEqual(args.name, "Foo")
        self.assertEqual(args.to_course, "A")
        self.assertFalse(args.dry_run, "Q-2b: not default for demote")


class TestDemoteHappyPath(unittest.TestCase):
    """TC-UNIT-016-07-01"""

    def test_demote_moves_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier_with_promoted_page(Path(tmp))
            rc, result = _run_demote("Sharpe", vault, "A")
            self.assertEqual(rc, 0)
            self.assertTrue(result["applied"])
            # Page moved
            self.assertFalse((vault / "_concepts" / "Sharpe.md").exists())
            self.assertTrue(
                (vault / "Lessons" / "A" / "_concepts" / "Sharpe.md").is_file()
            )
            # Footnotes restored to short form
            new_text = (vault / "Lessons" / "A" / "_concepts" / "Sharpe.md"
                        ).read_text(encoding="utf-8")
            self.assertIn("[[a-foo]]", new_text,
                          "footnote target restored to short form")
            self.assertNotIn("[[Lessons/A/_sources/a-foo]]", new_text)
            # promoted_from frontmatter removed
            self.assertNotIn("promoted_from:", new_text)


class TestCrossCourseRefusal(unittest.TestCase):
    """TC-UNIT-016-07-02"""

    def test_refuses_when_other_course_cites(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier_with_promoted_page(Path(tmp))
            # Add a source page in Course B that the root page would cite
            (vault / "Lessons" / "B" / "_sources" / "b-bar.md").write_text(
                "## B\n", encoding="utf-8")
            # And rewrite the root page to include a citation to b-bar
            rp = vault / "_concepts" / "Sharpe.md"
            t = rp.read_text(encoding="utf-8")
            t += "[^src-b-bar]: [[Lessons/B/_sources/b-bar]] — Source B\n"
            rp.write_text(t, encoding="utf-8")
            rc, _ = _run_demote("Sharpe", vault, "A")
            self.assertEqual(rc, 1, "non-target citation must refuse")
            # No mutations: root page still exists, course A copy not created
            self.assertTrue(rp.is_file())
            self.assertFalse(
                (vault / "Lessons" / "A" / "_concepts" / "Sharpe.md").exists())


class TestTargetCourseAbsent(unittest.TestCase):
    """TC-UNIT-016-07-03"""

    def test_unknown_course_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier_with_promoted_page(Path(tmp))
            rc, _ = _run_demote("Sharpe", vault, "Nonexistent")
            self.assertEqual(rc, 1)


class TestPageNotAtRoot(unittest.TestCase):
    """TC-UNIT-016-07-04"""

    def test_refuses_when_no_root_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier_with_promoted_page(Path(tmp))
            # Remove the root copy
            (vault / "_concepts" / "Sharpe.md").unlink()
            rc, _ = _run_demote("Sharpe", vault, "A")
            self.assertEqual(rc, 1)


class TestDryRun(unittest.TestCase):
    """TC-UNIT-016-07-08"""

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier_with_promoted_page(Path(tmp))
            rc, plan = _run_demote("Sharpe", vault, "A", dry_run=True)
            self.assertEqual(rc, 0)
            self.assertFalse(plan["applied"])
            # Files untouched
            self.assertTrue((vault / "_concepts" / "Sharpe.md").is_file())
            self.assertFalse(
                (vault / "Lessons" / "A" / "_concepts" / "Sharpe.md").exists())


if __name__ == "__main__":
    unittest.main()

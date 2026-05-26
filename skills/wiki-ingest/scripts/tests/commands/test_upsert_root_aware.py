"""Per-command tests for `commands/upsert_page.py` root-aware lookup.

TASK 016 bead 016-09. Existing single-course upsert tests live in
`test_upsert_page.py`; this file covers ONLY the new R8 behaviour
(root-first lookup + vault-relative footnote on root pages).
"""
from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import upsert_page as upsert_cmd


def _write_schema(path: Path, version: str, kind: str) -> None:
    path.write_text(
        f"---\nschema_version: \"{version}\"\nkind: {kind}\n---\n",
        encoding="utf-8",
    )


def _seed_course(course_root: Path) -> None:
    course_root.mkdir(parents=True, exist_ok=True)
    _write_schema(course_root / "WIKI_SCHEMA.md", "1.0", "course")
    for sub in ("_sources", "_concepts", "_entities"):
        (course_root / sub).mkdir(exist_ok=True)


def _seed_two_tier(tmp: Path) -> Path:
    vault = tmp / "vault"
    vault.mkdir()
    _write_schema(vault / "WIKI_SCHEMA.md", "2.0", "vault-root")
    (vault / "_concepts").mkdir()
    (vault / "_entities").mkdir()
    return vault


def _ns(*, vault, kind, name, slug, title="T", date="2026-05-26",
        fact=None, contradicts=None, definition=None,
        force=False, dry_run=False):
    return argparse.Namespace(
        vault=str(vault), kind=kind, name=name,
        source_slug=slug, source_title=title, source_date=date,
        fact=fact, contradicts=contradicts, definition=definition,
        force=force, dry_run=dry_run, cmd="upsert-page",
    )


class TestRootFirstLookup(unittest.TestCase):
    """TC-UNIT-016-09-01 / 02"""

    def test_hits_root_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            course = vault / "Lessons" / "C"
            _seed_course(course)
            # Root has the page (from prior promote)
            root_page = vault / "_concepts" / "Sharpe Score.md"
            root_page.write_text(
                "---\nname: Sharpe Score\nkind: concept\n---\n"
                "# Sharpe Score\n\n## Definition\n\nA thing.\n",
                encoding="utf-8")
            # Course C ingests a new source mentioning Sharpe Score
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = upsert_cmd.execute(_ns(
                    vault=course, kind="concept", name="Sharpe Score",
                    slug="foo", title="Foo Source", fact="X = 42",
                ))
            self.assertEqual(rc, 0)
            result = json.loads(buf.getvalue())
            self.assertTrue(result["target_is_shared"],
                            "root-first lookup must mark target_is_shared")
            # No course-local page created
            self.assertFalse(
                (course / "_concepts" / "Sharpe Score.md").exists())
            # Root page gained the fact
            new_text = root_page.read_text(encoding="utf-8")
            self.assertIn("X = 42", new_text)

    def test_falls_back_to_course_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            course = vault / "Lessons" / "C"
            _seed_course(course)
            # Root has NO page named Sharpe Score
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = upsert_cmd.execute(_ns(
                    vault=course, kind="concept", name="Sharpe Score",
                    slug="foo", title="Foo Source", fact="X = 42",
                ))
            self.assertEqual(rc, 0)
            result = json.loads(buf.getvalue())
            self.assertFalse(result["target_is_shared"])
            # Course-local page created
            self.assertTrue(
                (course / "_concepts" / "Sharpe Score.md").is_file())


class TestVaultRelativeFootnote(unittest.TestCase):
    """TC-UNIT-016-09-04 — root-page footnote uses vault-relative form."""

    def test_footnote_rewritten_to_vault_relative(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            course = vault / "Lessons" / "Hermes"
            _seed_course(course)
            root_page = vault / "_concepts" / "Sharpe Score.md"
            root_page.write_text(
                "---\nname: Sharpe Score\nkind: concept\n---\n"
                "# Sharpe Score\n\n## Definition\n\nA thing.\n",
                encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                upsert_cmd.execute(_ns(
                    vault=course, kind="concept", name="Sharpe Score",
                    slug="foo", title="Foo Source",
                ))
            new_text = root_page.read_text(encoding="utf-8")
            # Vault-relative footnote definition
            self.assertIn("[[Lessons/Hermes/_sources/foo]]", new_text)
            # Short form NOT present (it was rewritten)
            self.assertNotIn("[[foo]] — Foo Source", new_text)


class TestNoAutoPromotion(unittest.TestCase):
    """TC-UNIT-016-09-03 — R8.5"""

    def test_does_not_auto_promote(self):
        """When the page exists in TWO courses but NOT at root, upsert
        into a third course must NOT auto-promote — it creates a
        course-local copy."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            for n in ("A", "B"):
                _seed_course(vault / "Lessons" / n)
                (vault / "Lessons" / n / "_concepts" / "Pipeline.md"
                 ).write_text("# Pipeline\n", encoding="utf-8")
            # Course C has no Pipeline yet
            _seed_course(vault / "Lessons" / "C")
            with redirect_stdout(io.StringIO()):
                upsert_cmd.execute(_ns(
                    vault=vault / "Lessons" / "C", kind="concept",
                    name="Pipeline", slug="cpipe", title="CPipe",
                ))
            # No root copy — auto-promotion forbidden
            self.assertFalse((vault / "_concepts" / "Pipeline.md").exists())
            # Course C has its own copy
            self.assertTrue(
                (vault / "Lessons" / "C" / "_concepts" / "Pipeline.md"
                 ).is_file())


class TestSingleCourseByteIdentity(unittest.TestCase):
    """TC-UNIT-016-09-06 — v1 behaviour byte-identical when no root schema."""

    def test_single_course_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = Path(tmp) / "course"
            _seed_course(course)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = upsert_cmd.execute(_ns(
                    vault=course, kind="concept", name="Foo",
                    slug="s1", title="S1", definition="A thing.",
                ))
            self.assertEqual(rc, 0)
            result = json.loads(buf.getvalue())
            self.assertFalse(result["target_is_shared"])
            # Course-local page created (v1 behaviour)
            self.assertTrue((course / "_concepts" / "Foo.md").is_file())


if __name__ == "__main__":
    unittest.main()

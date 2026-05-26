"""Per-command tests for `commands/upsert_page.py` — TASK 015 bead 015-07.

Locks the additive-upsert contract:
- `register` + `execute` shape (TC-07).
- `render_stub_page` single-pass placeholder substitution (TC-07-1).
- `upsert_source_row` idempotency by slug (TC-07-2).
- `upsert_footnote` dedupe by line + by key (TC-07-3).
- End-to-end create-then-update preserves the definition and adds rows / footnotes (TC-E2E-07-1).
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


def _seed_vault(root: Path) -> None:
    (root / "WIKI_SCHEMA.md").write_text("# schema\n", encoding="utf-8")
    (root / "index.md").write_text("# index\n", encoding="utf-8")
    (root / "log.md").write_text("# log\n", encoding="utf-8")
    for sub in ("_sources", "_concepts", "_entities"):
        (root / sub).mkdir()


def _make_args(vault: Path, *, name: str, source_slug: str = "src-1",
               source_title: str = "Source One", source_date: str = "2024-01-15",
               definition: str | None = None, fact: str | None = None,
               contradicts: str | None = None, force: bool = False,
               dry_run: bool = False, kind: str = "concept",
               ) -> argparse.Namespace:
    return argparse.Namespace(
        vault=str(vault), cmd="upsert-page", kind=kind, name=name,
        source_slug=source_slug, source_title=source_title,
        source_date=source_date, definition=definition, fact=fact,
        contradicts=contradicts, force=force, dry_run=dry_run,
    )


class TestRegister(unittest.TestCase):

    def test_attaches_subparser(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        upsert_cmd.register(sub)
        args = parser.parse_args([
            "upsert-page", "/tmp/v",
            "--kind", "concept", "--name", "Foo",
            "--source-slug", "src", "--source-title", "Src",
            "--source-date", "2024-01-01",
        ])
        self.assertIs(args.func, upsert_cmd.execute)
        self.assertEqual(args.kind, "concept")


class TestRenderStubPagePlaceholderSubstitution(unittest.TestCase):
    """TC-07-1 — single-pass `{{KEY}}` substitution; no chained-replace bugs."""

    def test_basic_substitution(self):
        content = upsert_cmd.render_stub_page(
            kind="concept", name="Foo",
            definition="A foo is a thing.",
            source_slug="src-1", source_title="Src One",
            source_date="2024-01-15",
        )
        self.assertIn("# Foo", content)
        self.assertIn("kind: concept", content)
        self.assertIn("A foo is a thing.", content)
        self.assertIn("[[src-1]]", content)

    def test_definition_pending_when_absent(self):
        content = upsert_cmd.render_stub_page(
            kind="concept", name="Foo", definition=None,
            source_slug="s", source_title="t", source_date="d",
        )
        self.assertIn("Definition pending", content)

    def test_single_pass_substitution_does_not_recurse(self):
        """A definition value containing a literal `{{KIND}}` token must
        survive as-is — chained `.replace()` calls would catch the
        already-substituted text on a second pass. `_safe_name` blocks
        `{{` in names (separate defence-in-depth layer), but `definition`
        comes from `--definition` and is not name-validated; it goes
        through `_safe_inline` which only rejects newlines / `## ` /
        bare `---`. So the regex must be the gatekeeper here.
        """
        content = upsert_cmd.render_stub_page(
            kind="concept", name="Foo",
            definition="A {{KIND}} placeholder example",  # contains a meta-token
            source_slug="s", source_title="t", source_date="d",
        )
        # The literal `{{KIND}}` must survive in the body — single-pass
        # regex substitution doesn't recurse into already-substituted text.
        self.assertIn("{{KIND}}", content,
                      "literal `{{KIND}}` in --definition must NOT be "
                      "double-substituted on a second pass")
        # And `concept` (the real `{{KIND}}` substitution) appears once
        # in the frontmatter, NOT inside the definition.
        self.assertIn("kind: concept", content)


class TestUpsertSourceRowIdempotency(unittest.TestCase):
    """TC-07-2 — second call with the same source_slug must NOT duplicate."""

    def test_idempotent_on_same_slug(self):
        starter = (
            "## Sources mentioning this\n\n"
            "- [[s1]] — 2024-01-01 — Source One\n\n"
            "## Footnotes\n\n[^x]: bar\n"
        )
        out1 = upsert_cmd.upsert_source_row(starter, "s1", "Source One", "2024-01-01")
        self.assertEqual(out1, starter, "same-slug upsert must be a no-op")

    def test_adds_new_slug(self):
        starter = (
            "## Sources mentioning this\n\n"
            "- [[s1]] — 2024-01-01 — Source One\n\n"
            "## Footnotes\n\n[^x]: bar\n"
        )
        out = upsert_cmd.upsert_source_row(starter, "s2", "Source Two", "2024-02-02")
        self.assertIn("[[s1]]", out)
        self.assertIn("[[s2]]", out)


class TestUpsertFootnoteDedupe(unittest.TestCase):
    """TC-07-3 — footnote dedupe by exact line AND by key."""

    def test_dedupe_by_exact_line(self):
        starter = (
            "## Footnotes\n\n"
            "[^src-s1]: [[s1]] — Source One\n"
        )
        out = upsert_cmd.upsert_footnote(starter, "s1", "Source One")
        self.assertEqual(out, starter)

    def test_dedupe_by_key_only(self):
        # Same `[^src-s1]:` key but different title — still considered dup
        starter = "[^src-s1]: [[s1]] — Old Title\n"
        out = upsert_cmd.upsert_footnote(starter, "s1", "New Title")
        self.assertEqual(out, starter)


class TestExecuteCreateThenUpdate(unittest.TestCase):
    """TC-E2E-07-1 — create page, then additively update; assert all rows + footnotes."""

    def test_create_then_additive_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            # First call — creates the page
            args1 = _make_args(
                vault, name="AlphaConcept",
                source_slug="src-1", source_title="Source One",
                source_date="2024-01-15", definition="First definition.",
            )
            with redirect_stdout(io.StringIO()) as buf:
                rc = upsert_cmd.execute(args1)
            self.assertEqual(rc, 0)
            self.assertTrue(json.loads(buf.getvalue())["created"])
            page = vault / "_concepts" / "AlphaConcept.md"
            text_after_create = page.read_text(encoding="utf-8")
            self.assertIn("First definition.", text_after_create)
            self.assertIn("[[src-1]]", text_after_create)

            # Second call — different source, should be ADDITIVE
            args2 = _make_args(
                vault, name="AlphaConcept",
                source_slug="src-2", source_title="Source Two",
                source_date="2024-02-20",
                fact="Alpha is also great.",
            )
            with redirect_stdout(io.StringIO()) as buf:
                rc = upsert_cmd.execute(args2)
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertFalse(payload["created"])
            self.assertTrue(payload["added_fact"])

            text_after_update = page.read_text(encoding="utf-8")
            # Original definition still present (additive)
            self.assertIn("First definition.", text_after_update)
            # Both sources cited
            self.assertIn("[[src-1]]", text_after_update)
            self.assertIn("[[src-2]]", text_after_update)
            # Two footnotes
            self.assertIn("[^src-src-1]:", text_after_update)
            self.assertIn("[^src-src-2]:", text_after_update)
            # New fact landed
            self.assertIn("Alpha is also great.", text_after_update)


if __name__ == "__main__":
    unittest.main()

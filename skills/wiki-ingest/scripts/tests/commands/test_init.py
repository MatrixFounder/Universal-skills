"""Per-command tests for `commands/init.py` — TASK 015 bead 015-06."""
from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import init as init_cmd


class TestInitRegister(unittest.TestCase):

    def test_attaches_init_subparser(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        init_cmd.register(sub)
        args = parser.parse_args(["init", "/tmp/v"])
        self.assertEqual(args.vault, "/tmp/v")
        self.assertFalse(args.dry_run, "default `dry_run` must be False")
        self.assertIs(args.func, init_cmd.execute)

    def test_dry_run_flag_parses(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        init_cmd.register(sub)
        args = parser.parse_args(["init", "/tmp/v", "--dry-run"])
        self.assertTrue(args.dry_run)


class TestInitExecute(unittest.TestCase):

    def test_creates_expected_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "fresh"
            args = argparse.Namespace(
                vault=str(vault), cmd="init", dry_run=False,
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = init_cmd.execute(args)
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertIn("created", payload)
            self.assertIn("skipped", payload)
            # All files + subdirs should exist on disk
            for fname in ("WIKI_SCHEMA.md", "index.md", "log.md"):
                self.assertTrue((vault / fname).exists(), f"missing {fname}")
            for sub in ("_sources", "_concepts", "_entities"):
                self.assertTrue((vault / sub).is_dir(), f"missing {sub}/")

    def test_idempotent_on_existing_vault(self):
        """Re-running `init` on a populated vault must skip, not overwrite."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            args = argparse.Namespace(
                vault=str(vault), cmd="init", dry_run=False,
            )
            # First run: all created
            with redirect_stdout(io.StringIO()):
                init_cmd.execute(args)
            # Mutate index.md to confirm it isn't overwritten on second run
            (vault / "index.md").write_text("CUSTOM\n", encoding="utf-8")
            # Second run: should skip everything (including index.md)
            buf = io.StringIO()
            with redirect_stdout(buf):
                init_cmd.execute(args)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["created"], [],
                             "all files + subdirs already exist → nothing created")
            self.assertEqual(
                (vault / "index.md").read_text(encoding="utf-8"), "CUSTOM\n",
                "init must NOT overwrite the operator's edits",
            )

    def test_dry_run_creates_only_vault_root(self):
        """Under --dry-run:
        - vault root dir IS created unconditionally (need a place to land
          the dry-run plan against; this is intentional).
        - All THREE template files are NOT created (`write_text` honours
          `dry_run` by printing only).
        - All THREE subdirs are NOT created (`mkdir` is gated by
          `if not args.dry_run`).
        """
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "dryrun"
            args = argparse.Namespace(
                vault=str(vault), cmd="init", dry_run=True,
            )
            with redirect_stdout(io.StringIO()):
                init_cmd.execute(args)
            # Vault root IS created (unconditional `vault.mkdir`).
            self.assertTrue(vault.is_dir(),
                            "vault root IS created unconditionally")
            # Template files are NOT created under dry-run.
            self.assertFalse((vault / "WIKI_SCHEMA.md").exists())
            self.assertFalse((vault / "index.md").exists())
            self.assertFalse((vault / "log.md").exists())
            # Subdirs are NOT created under dry-run.
            self.assertFalse((vault / "_sources").exists(),
                             "subdirs MUST NOT be created under --dry-run")
            self.assertFalse((vault / "_concepts").exists())
            self.assertFalse((vault / "_entities").exists())


# =============================================================================
# TASK 016 bead 016-03 — init --root scaffold
# =============================================================================


class TestInitRoot(unittest.TestCase):
    """TC-UNIT-016-03-01..07 — vault-root scaffold."""

    def _ns(self, vault: Path, root: bool = True, dry_run: bool = False):
        return argparse.Namespace(
            vault=str(vault), cmd="init", root=root, dry_run=dry_run,
        )

    def test_happy_path_creates_minimal_root_layout(self):
        """TC-UNIT-016-03-01"""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = init_cmd.execute(self._ns(vault))
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["kind"], "vault-root")
            self.assertIn("WIKI_SCHEMA.md", payload["created"])
            self.assertIn("_concepts/", payload["created"])
            self.assertIn("_entities/", payload["created"])
            self.assertTrue((vault / "WIKI_SCHEMA.md").is_file())
            self.assertTrue((vault / "_concepts").is_dir())
            self.assertTrue((vault / "_entities").is_dir())
            # NO _sources/, NO log.md, NO index.md at root
            self.assertFalse((vault / "_sources").exists(),
                             "_sources/ MUST NOT exist at vault root")
            self.assertFalse((vault / "log.md").exists(),
                             "log.md MUST NOT exist at vault root (R13.2)")
            self.assertFalse((vault / "index.md").exists(),
                             "index.md NOT created on init --root; "
                             "first promote creates it lazily")
            # Schema declares schema_version 2.0
            schema_text = (vault / "WIKI_SCHEMA.md").read_text(encoding="utf-8")
            self.assertIn('schema_version: "2.0"', schema_text)
            self.assertIn("kind: vault-root", schema_text)

    def test_idempotent_rerun(self):
        """TC-UNIT-016-03-02 — re-running is a clean no-op."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            with redirect_stdout(io.StringIO()):
                init_cmd.execute(self._ns(vault))
            # Second run
            buf = io.StringIO()
            with redirect_stdout(buf):
                init_cmd.execute(self._ns(vault))
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["created"], [],
                             "all artefacts already exist → nothing created")
            self.assertEqual(
                sorted(payload["skipped"]),
                ["WIKI_SCHEMA.md", "_concepts/", "_entities/"],
            )

    def test_never_overwrites_existing_schema(self):
        """TC-UNIT-016-03-03"""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            existing = "---\nschema_version: \"99.0\"\n---\nhand-edited\n"
            (vault / "WIKI_SCHEMA.md").write_text(existing, encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                init_cmd.execute(self._ns(vault))
            after = (vault / "WIKI_SCHEMA.md").read_text(encoding="utf-8")
            self.assertEqual(after, existing,
                             "existing schema MUST NOT be overwritten")

    def test_refuses_nonexistent_target(self):
        """TC-UNIT-016-03-06"""
        with tempfile.TemporaryDirectory() as tmp:
            absent = Path(tmp) / "does-not-exist"
            with self.assertRaises(SystemExit) as cm:
                init_cmd.execute(self._ns(absent))
            self.assertEqual(cm.exception.code, 1)

    def test_course_mode_unchanged_when_root_flag_false(self):
        """TC-UNIT-016-03-05 — v1 byte-identity when --root is False."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "fresh-course"
            with redirect_stdout(io.StringIO()):
                init_cmd.execute(self._ns(vault, root=False))
            # v1 layout: schema, index, log, _sources, _concepts, _entities
            for name in ("WIKI_SCHEMA.md", "index.md", "log.md"):
                self.assertTrue((vault / name).is_file())
            for sub in ("_sources", "_concepts", "_entities"):
                self.assertTrue((vault / sub).is_dir())
            # schema_version 1.x (NOT 2.0)
            schema_text = (vault / "WIKI_SCHEMA.md").read_text(encoding="utf-8")
            self.assertNotIn('schema_version: "2.0"', schema_text)


if __name__ == "__main__":
    unittest.main()

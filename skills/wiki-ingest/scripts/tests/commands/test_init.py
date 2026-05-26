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


if __name__ == "__main__":
    unittest.main()

"""Per-command tests for `commands/classify_folder.py` — TASK 015 bead 015-11."""
from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import classify_folder as cf_cmd


class TestRegister(unittest.TestCase):
    def test_attaches(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        cf_cmd.register(sub)
        args = parser.parse_args(["classify-folder", "/tmp/f"])
        self.assertIs(args.func, cf_cmd.execute)
        self.assertFalse(args.force)


class TestExecute(unittest.TestCase):

    def test_refuses_vault_root_without_force(self):
        """MED-4 — refuse to classify-folder on a vault root."""
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "fake-vault"
            folder.mkdir()
            (folder / "WIKI_SCHEMA.md").write_text("# schema\n", encoding="utf-8")
            args = argparse.Namespace(
                folder=str(folder), cmd="classify-folder",
                group_by=None, force=False,
            )
            with self.assertRaises(SystemExit) as cm:
                cf_cmd.execute(args)
            self.assertEqual(cm.exception.code, 2)

    def test_force_bypasses_vault_root_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "fake-vault"
            folder.mkdir()
            (folder / "WIKI_SCHEMA.md").write_text("# schema\n", encoding="utf-8")
            (folder / "doc.md").write_text("hello\n", encoding="utf-8")
            args = argparse.Namespace(
                folder=str(folder), cmd="classify-folder",
                group_by=None, force=True,
            )
            with redirect_stdout(io.StringIO()) as buf:
                rc = cf_cmd.execute(args)
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertIn("groups", payload)

    def test_user_group_by_regex(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "src"
            folder.mkdir()
            for name in ("01-a.md", "01-b.md", "02-c.md"):
                (folder / name).write_text("content\n", encoding="utf-8")
            args = argparse.Namespace(
                folder=str(folder), cmd="classify-folder",
                group_by=r"^(\d+)\s*-\s*", force=False,
            )
            with redirect_stdout(io.StringIO()) as buf:
                cf_cmd.execute(args)
            payload = json.loads(buf.getvalue())
            keys = {g["group_key"] for g in payload["groups"]}
            self.assertEqual(keys, {"01", "02"})


if __name__ == "__main__":
    unittest.main()

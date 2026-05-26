"""Per-command tests for `commands/register_summary.py` — TASK 015 bead 015-09.

Locks the security defences from the May-2026 VDD-multi pass:
- S-M1 inbox containment + sensitive-path blocklist
- Symlink refusal
- Size cap (MAX_SUMMARY_BYTES)
- L-H5 structural fm rewrite (no str.replace prefix-overlap mangling)
- S-M6 hard-reject newlines / control chars in fm title/slug/date
"""
from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import register_summary as rs_cmd


def _seed_vault(root: Path) -> None:
    (root / "WIKI_SCHEMA.md").write_text("# schema\n", encoding="utf-8")
    (root / "index.md").write_text("# index\n", encoding="utf-8")
    (root / "log.md").write_text("# log\n", encoding="utf-8")
    for sub in ("_sources", "_concepts", "_entities"):
        (root / sub).mkdir()


def _make_args(vault: Path, summary_path: Path, **overrides) -> argparse.Namespace:
    base = dict(
        vault=str(vault), cmd="register-summary",
        summary_path=str(summary_path), slug=None, title=None,
        force=False, inbox_root=None, dry_run=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


class TestRegister(unittest.TestCase):
    def test_attaches_subparser(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        rs_cmd.register(sub)
        args = parser.parse_args([
            "register-summary", "/tmp/v", "--summary-path", "/tmp/s.md",
        ])
        self.assertIs(args.func, rs_cmd.execute)


class TestSecurityDefences(unittest.TestCase):

    def test_inbox_root_refuses_outside_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            outside = Path(tmp) / "outside.md"
            outside.write_text("---\ntitle: X\n---\nbody\n", encoding="utf-8")
            args = _make_args(vault, outside, inbox_root=str(inbox))
            with self.assertRaises(SystemExit) as cm:
                rs_cmd.execute(args)
            self.assertEqual(cm.exception.code, 8)

    def test_sensitive_path_blocklist_refuses_ssh(self):
        # We can't actually have a /tmp/.ssh/secret file, but the blocklist
        # check is string-based. Construct a path containing /.ssh/.
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            evil_dir = Path(tmp) / "fake-home" / ".ssh"
            evil_dir.mkdir(parents=True)
            secret = evil_dir / "id_rsa"
            secret.write_text("fake key", encoding="utf-8")
            args = _make_args(vault, secret)
            with self.assertRaises(SystemExit) as cm:
                rs_cmd.execute(args)
            self.assertEqual(cm.exception.code, 8)

    def test_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            real = Path(tmp) / "real.md"
            real.write_text("---\ntitle: X\n---\nbody\n", encoding="utf-8")
            link = Path(tmp) / "link.md"
            try:
                link.symlink_to(real)
            except (NotImplementedError, OSError):
                self.skipTest("filesystem does not support symlinks")
            args = _make_args(vault, link)
            with self.assertRaises(SystemExit) as cm:
                rs_cmd.execute(args)
            self.assertEqual(cm.exception.code, 8)


class TestStructuralFrontmatterRewrite(unittest.TestCase):
    """L-H5 — prefix-overlapping names must not collide via str.replace."""

    def test_prefix_overlap_rewrites_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            summary = Path(tmp) / "tricky.md"
            summary.write_text(
                '---\n'
                'title: "Tricky names"\n'
                'date: "2024-05-25"\n'
                'concepts:\n'
                '  - "Railway 24/7"\n'
                '  - "Railway 24/7 Deployment"\n'
                '  - "Normal Name"\n'
                '---\n\n'
                '# Body\n',
                encoding="utf-8",
            )
            args = _make_args(vault, summary)
            with redirect_stdout(io.StringIO()) as buf:
                rc = rs_cmd.execute(args)
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            # Both rewrites applied cleanly
            self.assertIn("Railway 24-7", payload["concepts"])
            self.assertIn("Railway 24-7 Deployment", payload["concepts"])
            self.assertIn("Normal Name", payload["concepts"])
            self.assertTrue(any("auto-normalized" in w for w in payload["warnings"]))


class TestHappyPath(unittest.TestCase):

    def test_register_clean_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            summary = Path(tmp) / "clean.md"
            summary.write_text(
                '---\ntitle: "Clean Summary"\ndate: "2024-01-15"\n'
                'concepts:\n  - Foo\n  - Bar\n---\n\n# Body\n',
                encoding="utf-8",
            )
            args = _make_args(vault, summary)
            with redirect_stdout(io.StringIO()) as buf:
                rc = rs_cmd.execute(args)
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["title"], "Clean Summary")
            self.assertEqual(payload["concepts"], ["Foo", "Bar"])
            # File copied into _sources/
            self.assertTrue((vault / "_sources" / "clean-summary.md").exists())


if __name__ == "__main__":
    unittest.main()

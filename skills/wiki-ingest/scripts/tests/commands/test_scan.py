"""Per-command tests for `commands/scan.py` — TASK 015 bead 015-06.

The R11 byte-identity gate (`test_r11_byte_identity.py`) already drives
`scan` end-to-end via subprocess. This file adds the **module-shape**
contract tests:

- `register(sub)` attaches a parser with the expected flags + sets
  `func=execute`.
- `execute(args)` honours its public contract (returns int, prints JSON,
  refuses non-directory targets).
"""
from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import scan as scan_cmd


def _seed_minimal_vault(root: Path) -> None:
    (root / "WIKI_SCHEMA.md").write_text("# schema\n", encoding="utf-8")
    (root / "index.md").write_text("# index\n", encoding="utf-8")
    (root / "log.md").write_text("# log\n", encoding="utf-8")
    for sub in ("_sources", "_concepts", "_entities"):
        (root / sub).mkdir()


class TestScanRegister(unittest.TestCase):

    def test_attaches_scan_subparser(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        scan_cmd.register(sub)
        args = parser.parse_args(["scan", "/tmp/x"])
        self.assertEqual(args.vault, "/tmp/x")
        self.assertIs(args.func, scan_cmd.execute,
                      "`scan` must dispatch to `commands.scan.execute`")

    def test_register_exposes_two_public_symbols(self):
        self.assertTrue(callable(scan_cmd.register))
        self.assertTrue(callable(scan_cmd.execute))


class TestScanExecute(unittest.TestCase):

    def test_emits_json_with_expected_top_level_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_minimal_vault(vault)
            args = argparse.Namespace(vault=str(vault), cmd="scan")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = scan_cmd.execute(args)
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            expected_keys = {
                "vault", "schema_present", "index_present", "log_present",
                "subdirs_present", "concepts", "entities", "sources",
                "counts", "last_log_entries",
            }
            self.assertEqual(set(payload.keys()), expected_keys)
            self.assertTrue(payload["schema_present"])
            self.assertEqual(payload["counts"]["concepts"], 0)

    def test_dies_on_non_directory(self):
        args = argparse.Namespace(vault="/nonexistent/path/here", cmd="scan")
        with self.assertRaises(SystemExit) as cm:
            scan_cmd.execute(args)
        self.assertNotEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()

"""Per-command tests for `commands/log_event.py` — TASK 015 bead 015-08."""
from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import log_event as log_event_cmd


def _seed_vault(root: Path) -> None:
    (root / "WIKI_SCHEMA.md").write_text("# schema\n", encoding="utf-8")
    (root / "index.md").write_text("# index\n", encoding="utf-8")
    (root / "log.md").write_text("# Log\n\n", encoding="utf-8")
    for sub in ("_sources", "_concepts", "_entities"):
        (root / sub).mkdir()


def _make_args(vault: Path, **overrides) -> argparse.Namespace:
    base = dict(
        vault=str(vault), cmd="log-event",
        event="query", title="Test",
        detail=None, date="2024-01-15", dry_run=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


class TestRegister(unittest.TestCase):
    def test_attaches_subparser(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        log_event_cmd.register(sub)
        args = parser.parse_args([
            "log-event", "/tmp/v",
            "--event", "query", "--title", "T",
        ])
        self.assertIs(args.func, log_event_cmd.execute)


class TestExecute(unittest.TestCase):

    def test_emits_event_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            with redirect_stdout(io.StringIO()) as buf:
                rc = log_event_cmd.execute(
                    _make_args(vault, event="lint", title="Health check")
                )
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertTrue(payload["appended"])
            text = (vault / "log.md").read_text(encoding="utf-8")
            self.assertIn("## [2024-01-15] lint | Health check", text)

    def test_renders_detail_key_value_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            with redirect_stdout(io.StringIO()):
                log_event_cmd.execute(_make_args(
                    vault,
                    detail=["foo=bar", "baz=qux"],
                ))
            text = (vault / "log.md").read_text(encoding="utf-8")
            self.assertIn("- foo: bar", text)
            self.assertIn("- baz: qux", text)

    def test_rejects_square_bracket_in_event(self):
        """S-L1 — `]` in --event must fail-close (would break log heading)."""
        with self.assertRaises(SystemExit):
            log_event_cmd.execute(_make_args(Path("/tmp/never"), event="ok]name"))

    def test_rejects_malformed_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            with self.assertRaises(SystemExit):
                log_event_cmd.execute(_make_args(vault, detail=["no-equals-sign"]))


if __name__ == "__main__":
    unittest.main()

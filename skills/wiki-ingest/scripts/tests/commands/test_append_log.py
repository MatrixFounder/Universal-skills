"""Per-command tests for `commands/append_log.py` — TASK 015 bead 015-08."""
from __future__ import annotations

import argparse
import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import append_log as append_log_cmd


def _seed_vault(root: Path) -> None:
    (root / "WIKI_SCHEMA.md").write_text("# schema\n", encoding="utf-8")
    (root / "index.md").write_text("# index\n", encoding="utf-8")
    (root / "log.md").write_text("# Log\n\n", encoding="utf-8")
    for sub in ("_sources", "_concepts", "_entities"):
        (root / sub).mkdir()


def _make_args(vault: Path, **overrides) -> argparse.Namespace:
    base = dict(
        vault=str(vault), cmd="append-log",
        title="Test Title", slug="test-slug",
        source_path="/tmp/source.md",
        touched=None, created=None,
        touch_name=[], create_name=[],
        contradictions=0, date="2024-01-15",
        force_log=False, dry_run=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


class TestRegister(unittest.TestCase):
    def test_attaches_subparser(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        append_log_cmd.register(sub)
        args = parser.parse_args([
            "append-log", "/tmp/v",
            "--title", "T", "--slug", "s", "--source-path", "p",
        ])
        self.assertIs(args.func, append_log_cmd.execute)


class TestExecute(unittest.TestCase):

    def test_appends_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            with redirect_stdout(io.StringIO()):
                rc = append_log_cmd.execute(_make_args(vault))
            self.assertEqual(rc, 0)
            text = (vault / "log.md").read_text(encoding="utf-8")
            self.assertIn("## [2024-01-15] ingest | Test Title", text)
            self.assertIn("Summary page: [[test-slug]]", text)

    def test_idempotent_on_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            with redirect_stdout(io.StringIO()):
                append_log_cmd.execute(_make_args(vault))
            text_after_first = (vault / "log.md").read_text(encoding="utf-8")
            with redirect_stdout(io.StringIO()) as buf:
                append_log_cmd.execute(_make_args(vault))
            payload = json.loads(buf.getvalue())
            self.assertFalse(payload["appended"])
            text_after_second = (vault / "log.md").read_text(encoding="utf-8")
            self.assertEqual(text_after_first, text_after_second,
                             "second call must not duplicate")

    def test_idempotency_no_redos_on_long_log(self):
        """L-H4: 50k-line log with the heading but no matching summary
        must complete in <50 ms (bounded-lookahead, no catastrophic
        regex backtracking)."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            _seed_vault(vault)
            heading = "## [2024-01-15] ingest | Test Title"
            # Plant the heading WITHOUT the matching summary line
            unrelated_lines = "\n".join(f"- entry {i}" for i in range(50_000))
            (vault / "log.md").write_text(
                f"# Log\n\n{heading}\n{unrelated_lines}\n",
                encoding="utf-8",
            )
            t0 = time.perf_counter()
            with redirect_stdout(io.StringIO()):
                append_log_cmd.execute(_make_args(vault))
            elapsed = time.perf_counter() - t0
            self.assertLess(
                elapsed, 0.2,
                f"append-log L-H4 idempotency took {elapsed:.3f}s — "
                f"bounded-lookahead invariant broken (catastrophic backtracking)",
            )

    def test_rejects_pipe_in_title(self):
        args = _make_args(Path("/tmp/never"), title="bad|title")
        with self.assertRaises(SystemExit):
            append_log_cmd.execute(args)


if __name__ == "__main__":
    unittest.main()

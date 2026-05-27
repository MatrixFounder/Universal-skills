"""End-to-end smoke test — v1.1 contract via the shell wrapper (TASK 017 bead 017-09).

This is the final gate. It invokes `wiki-ingest ingest` AS THE BRIDGE
WOULD: through the POSIX shell wrapper (017-01), against a two-tier
vault fixture, and parses the JSON manifest. Failure of any assertion
= the chain does NOT merge.

Locks the full v1.1 contract surface:
- `--version` shipping the locked string.
- Two-tier vault + `vault_id:` round-trip via the orchestrator manifest.
- Source-hash short-circuit on re-run (UC-4).
- Strict-mode `--vault-id` happy path (UC-3 positive).
- Architecture §4.5.5 WrittenEntry shape.
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import init as init_cmd


SCRIPTS_DIR = Path(__file__).resolve().parent.parent
WRAPPER = SCRIPTS_DIR / "wiki-ingest"
WIKI_OPS = SCRIPTS_DIR / "wiki_ops.py"


# --------------------------------------------------------------------- #
# Fixture builder                                                       #
# --------------------------------------------------------------------- #

def _build_two_tier_fixture(tmp: Path, *, vault_id: str = "trade-agents-e2e") -> Path:
    """Two-tier vault with one course `Lessons/Hermes` and `vault_id:` set."""
    vault = tmp / "trade-agents"
    vault.mkdir()
    with redirect_stdout(io.StringIO()):
        init_cmd.execute(argparse.Namespace(
            vault=str(vault), root=True, dry_run=False,
            vault_id=vault_id, cmd="init",
        ))
        course = vault / "Lessons" / "Hermes"
        init_cmd.execute(argparse.Namespace(
            vault=str(course), root=False, dry_run=False,
            vault_id=None, cmd="init",
        ))
    # Drop a passthrough summary source the orchestrator can ingest.
    source = course / "summary-2026-05-27.md"
    source.write_text(
        "---\n"
        "type: summary\n"
        "name: summary-2026-05-27\n"
        "title: 2026-05-27 standup\n"
        "date: 2026-05-27\n"
        "concepts:\n"
        "  - Sharpe Score\n"
        "  - Volatility\n"
        "related:\n"
        "  - Hermes Agent\n"
        "---\n"
        "# 2026-05-27 standup\n\n"
        "Mentioned [[Sharpe Score]] and [[Volatility]] inside [[Hermes Agent]].\n",
        encoding="utf-8",
    )
    return vault


# --------------------------------------------------------------------- #
# E2E assertions                                                        #
# --------------------------------------------------------------------- #

_REQUIRED_TOP_KEYS = frozenset({
    "manifest_version", "status", "vault_id", "vault_root", "course",
    "source", "written", "created", "touched", "contradictions",
    "summary_path", "log_event", "llm_tokens_used",
})

_WRITTEN_ACTIONS = frozenset({"created", "updated", "appended"})
_WRITTEN_KINDS = frozenset({"source", "concept", "entity", "index", "log"})
_WRITTEN_SCOPES = frozenset({"course", "vault"})


def _run_wrapper(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(WRAPPER), *args],
        capture_output=True, text=True, timeout=30, cwd=str(cwd) if cwd else None,
    )


class TestE2EVersionViaWrapper(unittest.TestCase):
    """Smoke gate — wrapper shells out cleanly to wiki_ops.py."""

    def test_version_round_trip(self):
        result = _run_wrapper(["--version"])
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        parts = result.stdout.strip().split()
        self.assertEqual(parts[0], "wiki-ingest")
        ver_tuple = tuple(int(p) for p in parts[1].split(".")[:2])
        self.assertGreaterEqual(ver_tuple, (1, 1))


class TestE2EFullIngestRoundTrip(unittest.TestCase):
    """TC-E2E-017-09-01 — bridge-shape invocation; manifest validates §1."""

    def test_two_tier_passthrough_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_tier_fixture(Path(tmp))
            course = vault / "Lessons" / "Hermes"
            source = course / "summary-2026-05-27.md"

            result = _run_wrapper([
                "ingest",
                "--source", str(source),
                "--vault", str(course),
                "--output-format", "json",
            ])
            self.assertEqual(result.returncode, 0,
                             f"stderr={result.stderr!r}")

            manifest = json.loads(result.stdout)

            # §1.1 success envelope keys
            missing = _REQUIRED_TOP_KEYS - set(manifest.keys())
            self.assertFalse(missing, f"missing keys: {sorted(missing)}")
            self.assertEqual(manifest["manifest_version"], "1.1")
            self.assertEqual(manifest["status"], "ok")
            self.assertEqual(manifest["vault_id"], "trade-agents-e2e")
            self.assertEqual(manifest["course"], "Hermes")
            self.assertIsNotNone(manifest["summary_path"])

            # written[] populated with the expected mix of kinds
            kinds = {w["kind"] for w in manifest["written"]}
            self.assertIn("source", kinds)
            self.assertIn("concept", kinds)  # 2 concepts in the fixture
            self.assertIn("index", kinds)
            self.assertIn("log", kinds)

            # WrittenEntry shape locked
            for entry in manifest["written"]:
                self.assertIn(entry["action"], _WRITTEN_ACTIONS)
                self.assertIn(entry["kind"], _WRITTEN_KINDS)
                self.assertIn(entry["scope"], _WRITTEN_SCOPES)

            # log_event populated; byte offset > 0 (real heading found)
            self.assertEqual(manifest["log_event"]["event_type"], "ingest")
            self.assertGreater(manifest["log_event"]["log_md_byte_offset"], 0)

    def test_second_call_short_circuits_via_recorded_hash(self):
        """017.07 footer-write enables natural idempotency on re-run."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_tier_fixture(Path(tmp))
            course = vault / "Lessons" / "Hermes"
            source = course / "summary-2026-05-27.md"

            first = _run_wrapper([
                "ingest", "--source", str(source), "--vault", str(course),
                "--output-format", "json",
            ])
            self.assertEqual(first.returncode, 0)
            first_manifest = json.loads(first.stdout)
            recorded_hash = first_manifest["source"]["hash"]

            second = _run_wrapper([
                "ingest", "--source", str(source), "--vault", str(course),
                "--source-hash", recorded_hash,
                "--output-format", "json",
            ])
            self.assertEqual(second.returncode, 0)
            manifest = json.loads(second.stdout)
            self.assertEqual(manifest.get("action"), "unchanged")
            self.assertEqual(manifest["written"], [])


class TestE2EStrictVaultIdPositive(unittest.TestCase):
    """TC-E2E-017-09-02 — `--vault-id` matches frontmatter → exit 0."""

    def test_strict_mode_happy_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_tier_fixture(Path(tmp), vault_id="my-vault")
            course = vault / "Lessons" / "Hermes"
            source = course / "summary-2026-05-27.md"

            result = _run_wrapper([
                "ingest", "--source", str(source), "--vault", str(course),
                "--vault-id", "my-vault",
                "--output-format", "json",
            ])
            self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["vault_id"], "my-vault")


class TestE2ENonSummaryRejection(unittest.TestCase):
    """User-approved scope: non-summary sources reject cleanly with phase."""

    def test_transcript_source_exits_21(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_tier_fixture(Path(tmp))
            course = vault / "Lessons" / "Hermes"
            raw = course / "raw-transcript.md"
            raw.write_text(
                "---\ntype: transcript\nname: raw-transcript\n---\n# raw\n",
                encoding="utf-8",
            )
            result = _run_wrapper([
                "ingest", "--source", str(raw), "--vault", str(course),
                "--output-format", "json",
            ])
            self.assertEqual(result.returncode, 21)
            self.assertIn("SOURCE_NEEDS_SUMMARIZATION", result.stderr)


if __name__ == "__main__":
    unittest.main()

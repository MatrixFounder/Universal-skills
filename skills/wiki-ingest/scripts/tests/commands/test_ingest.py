"""Per-command tests for `commands/ingest.py` — TASK 017 bead 017-05 (Phase 1).

Phase 1 has no writes; tests assert:
- argparse contract (mutually exclusive --known-concepts-*, defaults);
- manifest shape on a real fixture (matches `references/manifest_schema.md` §1);
- UC-3 vault_id routing → exit 23 / 24 / 25;
- UC-4 source-hash short-circuit → `action: "unchanged"`;
- `--source-hash` format check → exit 2;
- `--quiet` + piped-stdout suppression of decorative output;
- `_safe_for_json` sanitisation of manifest scalars;
- `summary_path is None` (Phase-1 anti-leak per plan-reviewer feedback).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from wiki_ingest.commands import ingest as ingest_cmd
from wiki_ingest.commands import init as init_cmd


SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent
WIKI_OPS = SCRIPTS_DIR / "wiki_ops.py"

_REQUIRED_TOP_KEYS = frozenset({
    "manifest_version", "status", "vault_id", "vault_root", "course",
    "source", "written", "created", "touched", "contradictions",
    "summary_path", "log_event", "llm_tokens_used",
})


# --------------------------------------------------------------------- #
# Fixture builders                                                      #
# --------------------------------------------------------------------- #

def _build_single_course_vault(tmp: Path) -> Path:
    """Single-course vault — no root schema; `course` should be null (Q-5)."""
    vault = tmp / "single-course"
    vault.mkdir()
    with redirect_stdout(io.StringIO()):
        init_cmd.execute(argparse.Namespace(
            vault=str(vault), root=False, dry_run=False, cmd="init",
        ))
    return vault


def _build_two_tier_vault(tmp: Path, *, vault_id: str | None = None) -> Path:
    """Two-tier vault with one course `Lessons/Hermes`. Optional `vault_id:`
    field is appended to the root schema's frontmatter."""
    vault = tmp / "trade-agents"
    vault.mkdir()
    with redirect_stdout(io.StringIO()):
        init_cmd.execute(argparse.Namespace(
            vault=str(vault), root=True, dry_run=False, cmd="init",
        ))
        course = vault / "Lessons" / "Hermes"
        init_cmd.execute(argparse.Namespace(
            vault=str(course), root=False, dry_run=False, cmd="init",
        ))
    if vault_id is not None:
        # Splice `vault_id: <slug>` after the `kind: vault-root` line so the
        # injection lands inside the frontmatter regardless of how the
        # template quotes `schema_version`.
        schema = vault / "WIKI_SCHEMA.md"
        text = schema.read_text(encoding="utf-8")
        text = text.replace(
            "kind: vault-root",
            f"kind: vault-root\nvault_id: {vault_id}",
            1,
        )
        schema.write_text(text, encoding="utf-8")
    return vault


def _write_source(vault_or_course: Path, name: str = "transcript-2026-05-27") -> Path:
    """Drop a small markdown source the orchestrator can hash."""
    p = vault_or_course / f"{name}.md"
    p.write_text(
        f"---\ntype: summary\nname: {name}\n---\n\n# {name}\n\nbody.\n",
        encoding="utf-8",
    )
    return p


def _ns(**kwargs) -> argparse.Namespace:
    """Build an argparse Namespace with all required ingest defaults."""
    defaults = dict(
        cmd="ingest",
        output_format="human",
        vault_id=None,
        known_concepts_file=None,
        known_concepts_stdin=False,
        source_hash=None,
        config=None,
        timeout_seconds=600,
        quiet=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _capture(args: argparse.Namespace) -> tuple[int, str, str]:
    """Run `ingest_cmd.execute(args)` capturing stdout / stderr; never raise."""
    out, err = io.StringIO(), io.StringIO()
    rc = 0
    try:
        with redirect_stdout(out), redirect_stderr(err):
            rc = ingest_cmd.execute(args)
    except SystemExit as e:
        rc = int(e.code or 0)
    return rc, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------- #
# argparse contract                                                     #
# --------------------------------------------------------------------- #

class TestIngestRegister(unittest.TestCase):

    def _build(self, argv):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        ingest_cmd.register(sub)
        return parser.parse_args(argv)

    def test_attaches_subparser_with_required_flags(self):
        args = self._build(["ingest", "--source", "/s", "--vault", "/v"])
        self.assertEqual(args.source, "/s")
        self.assertEqual(args.vault, "/v")
        self.assertEqual(args.output_format, "human")
        self.assertEqual(args.timeout_seconds, 600)
        self.assertFalse(args.quiet)
        self.assertIs(args.func, ingest_cmd.execute)

    def test_known_concepts_mutually_exclusive(self):
        """TC-UNIT-017-05-12 — both flags together → argparse exit 2."""
        with self.assertRaises(SystemExit) as cm:
            with redirect_stderr(io.StringIO()):
                self._build([
                    "ingest", "--source", "/s", "--vault", "/v",
                    "--known-concepts-file", "/k",
                    "--known-concepts-stdin",
                ])
        self.assertEqual(cm.exception.code, 2)

    def test_output_format_choices_locked(self):
        """Only `human` and `json` accepted."""
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                self._build([
                    "ingest", "--source", "/s", "--vault", "/v",
                    "--output-format", "xml",
                ])


# --------------------------------------------------------------------- #
# TC-UNIT-017-05-01 — Phase 1 manifest shape (two-tier fixture)         #
# --------------------------------------------------------------------- #

class TestPhase1ManifestShape(unittest.TestCase):

    def test_two_tier_vault_json_emission_phase2(self):
        """TC-E2E-017-06-01 — UC-1 round-trip on two-tier vault.

        Phase 2 (017-06) writes real files; manifest's `written[]` lists
        the source page, index update, and log append at minimum.
        """
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_tier_vault(Path(tmp), vault_id="trade-agents-test")
            course = vault / "Lessons" / "Hermes"
            source = _write_source(course)
            rc, stdout, stderr = _capture(_ns(
                source=str(source),
                vault=str(course),  # pass the course root for two-tier per-course ingest
                output_format="json",
            ))
            self.assertEqual(rc, 0, f"stderr={stderr!r}")
            manifest = json.loads(stdout)
            # Required keys
            missing = _REQUIRED_TOP_KEYS - set(manifest.keys())
            self.assertFalse(missing, f"missing keys: {sorted(missing)}")
            # Arch-M-3 / forward-compat
            self.assertEqual(manifest["manifest_version"], "1.1")
            # Phase 2: written[] non-empty (source + index + log at minimum)
            self.assertGreater(len(manifest["written"]), 0,
                               "Phase 2 must populate written[]")
            kinds = {w["kind"] for w in manifest["written"]}
            self.assertIn("source", kinds)
            self.assertIn("index", kinds)
            self.assertIn("log", kinds)
            # summary_path now real (not null)
            self.assertIsNotNone(manifest["summary_path"])
            self.assertTrue(manifest["summary_path"].startswith("_sources/"))
            # vault_id round-trips from fixture
            self.assertEqual(manifest["vault_id"], "trade-agents-test")
            # course derived from two-tier path
            self.assertEqual(manifest["course"], "Hermes")
            # source.hash is real sha256 hex
            self.assertEqual(len(manifest["source"]["hash"]), 64)
            # log_event populated
            self.assertIsNotNone(manifest["log_event"])
            self.assertEqual(manifest["log_event"]["event_type"], "ingest")
            self.assertGreater(manifest["log_event"]["log_md_byte_offset"], 0)


# --------------------------------------------------------------------- #
# Q-5: single-course vault → course=null, vault_id=null (without flag) #
# --------------------------------------------------------------------- #

class TestSingleCourseQ5(unittest.TestCase):
    """TC-UNIT-017-05-07."""

    def test_no_vault_id_no_strict_mode_returns_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            source = _write_source(vault)
            rc, stdout, _ = _capture(_ns(
                source=str(source),
                vault=str(vault),
                output_format="json",
            ))
            self.assertEqual(rc, 0)
            manifest = json.loads(stdout)
            self.assertIsNone(manifest["vault_id"])
            self.assertIsNone(manifest["course"])


# --------------------------------------------------------------------- #
# UC-3 vault_id routing — exits 23 / 24 / 25                            #
# --------------------------------------------------------------------- #

class TestVaultIdRouting(unittest.TestCase):

    def test_missing_vault_id_with_flag_exits_23(self):
        """TC-UNIT-017-05-03."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_tier_vault(Path(tmp), vault_id=None)  # no field
            source = _write_source(vault / "Lessons" / "Hermes")
            rc, _, stderr = _capture(_ns(
                source=str(source), vault=str(vault),
                vault_id="trade-agents",
                output_format="json",
            ))
            self.assertEqual(rc, 23)
            self.assertIn("MISSING_VAULT_ID", stderr)

    def test_flag_mismatch_exits_25(self):
        """TC-UNIT-017-05-04."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_tier_vault(Path(tmp), vault_id="foo")
            source = _write_source(vault / "Lessons" / "Hermes")
            rc, _, stderr = _capture(_ns(
                source=str(source), vault=str(vault),
                vault_id="bar",
                output_format="json",
            ))
            self.assertEqual(rc, 25)
            self.assertIn("VAULT_ID_FLAG_MISMATCH", stderr)
            self.assertIn("foo", stderr)
            self.assertIn("bar", stderr)

    def test_invalid_frontmatter_pattern_exits_24_with_flag(self):
        """TC-UNIT-017-05-05 (with flag)."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_tier_vault(Path(tmp), vault_id="1bad")
            source = _write_source(vault / "Lessons" / "Hermes")
            rc, _, stderr = _capture(_ns(
                source=str(source), vault=str(vault),
                vault_id="foo",
                output_format="json",
            ))
            self.assertEqual(rc, 24)
            self.assertIn("INVALID_VAULT_ID", stderr)
            self.assertIn("1bad", stderr)

    def test_invalid_frontmatter_pattern_exits_24_without_flag(self):
        """TC-UNIT-017-05-05 (without flag)."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_tier_vault(Path(tmp), vault_id="1bad")
            source = _write_source(vault / "Lessons" / "Hermes")
            rc, _, stderr = _capture(_ns(
                source=str(source), vault=str(vault),
                output_format="json",
            ))
            self.assertEqual(rc, 24, "frontmatter pattern fires regardless of --vault-id")
            self.assertIn("INVALID_VAULT_ID", stderr)

    def test_caller_supplied_malformed_flag_exits_24(self):
        """TC-UNIT-017-05-06."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_tier_vault(Path(tmp), vault_id="good-slug")
            source = _write_source(vault / "Lessons" / "Hermes")
            rc, _, stderr = _capture(_ns(
                source=str(source), vault=str(vault),
                vault_id="1bad",
                output_format="json",
            ))
            self.assertEqual(rc, 24,
                             "malformed-input wins over mismatch comparison")
            self.assertIn("INVALID_VAULT_ID", stderr)


# --------------------------------------------------------------------- #
# UC-4 source-hash short-circuit                                        #
# --------------------------------------------------------------------- #

class TestSourceHashShortCircuit(unittest.TestCase):

    def _sha256_file(self, path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    def _seed_recorded(self, vault: Path, slug: str, hex_hash: str) -> Path:
        """Write `_sources/<slug>.md` with the recorded `source_hash` field."""
        sources = vault / "_sources"
        sources.mkdir(exist_ok=True)
        target = sources / f"{slug}.md"
        target.write_text(
            f"---\nname: {slug}\nkind: source\nsource_hash: {hex_hash}\n---\n",
            encoding="utf-8",
        )
        return target

    def test_source_hash_match_emits_action_unchanged(self):
        """TC-UNIT-017-05-02 — recorded hash matches → no writes, exit 0."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            source = _write_source(vault, name="transcript-2026-05-27")
            real_hash = self._sha256_file(source)
            slug = "transcript-2026-05-27"  # matches _safety.slugify(source.stem)
            self._seed_recorded(vault, slug, real_hash)
            rc, stdout, _ = _capture(_ns(
                source=str(source), vault=str(vault),
                source_hash=real_hash,
                output_format="json",
            ))
            self.assertEqual(rc, 0)
            manifest = json.loads(stdout)
            self.assertEqual(manifest["action"], "unchanged")
            self.assertEqual(manifest["written"], [])

    def test_source_hash_mismatch_proceeds_to_full_pipeline(self):
        """Phase 2: mismatched hash → run pipeline, NO `action:"unchanged"`.

        Pre-seeded `_sources/<slug>.md` carries a sentinel hash; the live
        source resolves to a different sha256. The orchestrator's short-
        circuit does NOT fire — but register-summary then sees the file
        exists and refuses without `--force`, dying with the legacy code
        3 (slug-already-exists). The orchestrator wraps that in the
        partial envelope (exit 20). Locks the propagation contract.
        """
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            source = _write_source(vault)
            self._seed_recorded(vault, "transcript-2026-05-27", "0" * 64)
            real = self._sha256_file(source)
            rc, stdout, _ = _capture(_ns(
                source=str(source), vault=str(vault),
                source_hash=real,
                output_format="json",
            ))
            self.assertEqual(rc, 20, "mismatched + existing slug → partial (exit 20)")
            envelope = json.loads(stdout)
            self.assertEqual(envelope["status"], "error")
            self.assertEqual(envelope["phase"], "register-summary")
            self.assertNotIn("action", envelope,
                             "mismatch path must NOT emit `action:unchanged`")

    def test_source_hash_malformed_exits_2(self):
        """TC-UNIT-017-05-08."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            source = _write_source(vault)
            rc, _, stderr = _capture(_ns(
                source=str(source), vault=str(vault),
                source_hash="deadbeef",  # only 8 chars
                output_format="json",
            ))
            self.assertEqual(rc, 2)
            self.assertIn("INVALID_SOURCE_HASH", stderr)


# --------------------------------------------------------------------- #
# Decorum: --quiet + TTY check                                          #
# --------------------------------------------------------------------- #

class TestQuietAndTTY(unittest.TestCase):

    def test_quiet_suppresses_human_stdout(self):
        """TC-UNIT-017-05-09."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            source = _write_source(vault)
            rc, stdout, _ = _capture(_ns(
                source=str(source), vault=str(vault),
                output_format="human",
                quiet=True,
            ))
            self.assertEqual(rc, 0)
            self.assertEqual(stdout, "",
                             "human output must be suppressed under --quiet")

    def test_piped_stdout_suppresses_human_output(self):
        """TC-UNIT-017-05-10 — running via subprocess.PIPE forces non-TTY."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            source = _write_source(vault)
            result = subprocess.run(
                [sys.executable, str(WIKI_OPS), "ingest",
                 "--source", str(source), "--vault", str(vault),
                 "--output-format", "human"],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "",
                             "decorative stdout must be empty when piped")


# --------------------------------------------------------------------- #
# TC-UNIT-017-05-11 — _safe_for_json applied to manifest scalars       #
# --------------------------------------------------------------------- #

class TestSafeForJson(unittest.TestCase):
    """Locks the manifest emission going through `_safe_for_json` (S-M6).

    Constructs a frontmatter `vault_id` containing a control character —
    BUT that would fail `_VAULT_ID_RE` (rejected by 017-02). So instead
    we plant a control character in the source filename's slugified form.
    `_safety.slugify` already strips control chars via NFKC + regex; this
    test just verifies the manifest's `source.slug` doesn't carry raw
    control chars (defense in depth).
    """

    def test_slug_strips_control_chars(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            # filename without control chars (filesystem-restricted),
            # but with unicode confusables that NFKC normalises.
            source = _write_source(vault, name="café-1")
            rc, stdout, _ = _capture(_ns(
                source=str(source), vault=str(vault),
                output_format="json",
            ))
            self.assertEqual(rc, 0)
            manifest = json.loads(stdout)
            slug = manifest["source"]["slug"]
            # No control chars or unsanitised whitespace.
            for ch in slug:
                self.assertGreaterEqual(ord(ch), 0x20,
                                        f"control char {ch!r} in slug {slug!r}")


# --------------------------------------------------------------------- #
# Source path validation                                                #
# --------------------------------------------------------------------- #

class TestSourcePathValidation(unittest.TestCase):

    def test_missing_source_file_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            rc, _, stderr = _capture(_ns(
                source="/nonexistent/path/to/source.md",
                vault=str(vault),
                output_format="json",
            ))
            self.assertEqual(rc, 1)
            self.assertIn("source not found", stderr)


# --------------------------------------------------------------------- #
# Phase-2 specific tests (TASK 017 bead 017-06)                         #
# --------------------------------------------------------------------- #

class TestPhase2SingleCourseUC2(unittest.TestCase):
    """TC-E2E-017-06-02 — UC-2 operator-direct ingest on single-course vault."""

    def test_single_course_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            source = _write_source(vault)
            rc, stdout, stderr = _capture(_ns(
                source=str(source), vault=str(vault),
                output_format="json",
            ))
            self.assertEqual(rc, 0, f"stderr={stderr!r}")
            manifest = json.loads(stdout)
            # Q-5: single-course → course:null AND every scope is "course"
            self.assertIsNone(manifest["course"])
            for entry in manifest["written"]:
                self.assertEqual(entry["scope"], "course",
                                 f"single-course scope must be 'course': {entry}")
            # Vault actually mutated (`_sources/<slug>.md` exists)
            self.assertTrue((vault / "_sources" / "transcript-2026-05-27.md").is_file())


class TestPhase2PartialRecoveryUC5(unittest.TestCase):
    """TC-E2E-017-06-03 — UC-5 partial-success on monkey-patched failure.

    Inject a non-zero exit code from `upsert-page` mid-pipeline. The
    orchestrator must emit the partial envelope (exit 20) with
    `phase:"upsert-page"` + non-empty `written_so_far[]`.
    """

    def test_mid_pipeline_failure_emits_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            # Source frontmatter has 2 concepts so the upsert dispatch loop fires.
            source = vault / "rich-source.md"
            source.write_text(
                "---\ntype: summary\nname: rich-source\n"
                "concepts:\n  - Sharpe Score\n  - Volatility\n---\n# rich source\n",
                encoding="utf-8",
            )

            # Patch _dispatch_silent so the FIRST upsert-page call returns 1.
            from wiki_ingest.commands import ingest as ingest_cmd
            real_silent = ingest_cmd._dispatch_silent
            calls = []

            def patched(cmd_name, ns):
                calls.append(cmd_name)
                if cmd_name == "upsert-page" and len([c for c in calls if c == "upsert-page"]) == 1:
                    return 1  # inject failure on the FIRST upsert-page
                return real_silent(cmd_name, ns)

            ingest_cmd._dispatch_silent = patched
            try:
                rc, stdout, _ = _capture(_ns(
                    source=str(source), vault=str(vault),
                    output_format="json",
                ))
            finally:
                ingest_cmd._dispatch_silent = real_silent

            self.assertEqual(rc, 20, "exit 20 = EXIT_PARTIAL")
            envelope = json.loads(stdout)
            self.assertEqual(envelope["status"], "error")
            self.assertEqual(envelope["phase"], "upsert-page")
            self.assertEqual(envelope["code"], "PARTIAL_INDEX_FAILURE")
            # register-summary succeeded before the upsert failure → exactly
            # one entry in written_so_far[].
            self.assertGreaterEqual(len(envelope["written_so_far"]), 1)
            self.assertEqual(envelope["written_so_far"][0]["kind"], "source")
            self.assertIn("cleanup_advice", envelope)


class TestPhase2NeedsSummarization(unittest.TestCase):
    """Non-summary source → exit 21 with `phase:"needs-pre-summarization"`.

    Locks the user-approved option-1 contract (chain-deviation discussion
    2026-05-27): wiki-ingest v1.1 is summary-passthrough only; raw
    transcripts must be pre-summarised via /summarizing-meetings.
    """

    def test_non_summary_type_exits_21(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            # transcript-shape source (no `type:summary` frontmatter)
            source = vault / "raw-transcript.md"
            source.write_text(
                "---\ntype: transcript\nname: raw-transcript\n---\n"
                "# raw\nlots of words.\n",
                encoding="utf-8",
            )
            rc, _, stderr = _capture(_ns(
                source=str(source), vault=str(vault),
                output_format="json",
            ))
            self.assertEqual(rc, 21, "EXIT_SUBPROCESS for non-summary")
            self.assertIn("SOURCE_NEEDS_SUMMARIZATION", stderr)
            self.assertIn("needs-pre-summarization", stderr)


class TestLogEventByteOffset(unittest.TestCase):
    """R8.2 — `log_md_byte_offset` is the byte position of the appended
    `## [date] ingest | <title>` heading in the course's log.md."""

    def test_byte_offset_locates_appended_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            source = _write_source(vault)
            rc, stdout, _ = _capture(_ns(
                source=str(source), vault=str(vault),
                output_format="json",
            ))
            self.assertEqual(rc, 0)
            manifest = json.loads(stdout)
            offset = manifest["log_event"]["log_md_byte_offset"]
            log_bytes = (vault / "log.md").read_bytes()
            # Bytes at offset begin with the `## [` ingest heading marker.
            self.assertTrue(log_bytes[offset:offset + 4] == b"## [",
                            f"offset {offset} does not point at heading: "
                            f"{log_bytes[offset:offset + 30]!r}")


class TestIdempotencyRoundTrip(unittest.TestCase):
    """Phase-2 + 017.07 footer-write: re-run naturally short-circuits.

    First ingest writes `_sources/<slug>.md` AND records `source_hash:`
    in its frontmatter (017.07 R9 footer write). Second ingest with
    `--source-hash <same>` finds the recorded hash and emits
    `action:"unchanged"`.
    """

    def test_round_trip_writes_footer_and_short_circuits(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            source = _write_source(vault)
            real = hashlib.sha256(source.read_bytes()).hexdigest()

            # First ingest — pipeline runs, footer written.
            rc1, _, _ = _capture(_ns(
                source=str(source), vault=str(vault),
                output_format="json",
            ))
            self.assertEqual(rc1, 0)
            registered = vault / "_sources" / "transcript-2026-05-27.md"
            self.assertTrue(registered.is_file())

            # 017.07 R9: source_hash footer was written by the orchestrator.
            footer = registered.read_text(encoding="utf-8")
            self.assertIn(f"source_hash: {real}", footer,
                          "017.07 must record the source-hash footer "
                          "in _sources/<slug>.md after register-summary")

            # Second ingest with --source-hash → natural short-circuit.
            rc2, stdout2, _ = _capture(_ns(
                source=str(source), vault=str(vault),
                source_hash=real,
                output_format="json",
            ))
            self.assertEqual(rc2, 0)
            manifest2 = json.loads(stdout2)
            self.assertEqual(manifest2.get("action"), "unchanged")
            self.assertEqual(manifest2["written"], [])


class TestPrevalidateTitle(unittest.TestCase):
    """Logic-critic HIGH-2 (2026-05-27 vdd-multi): a title that survives
    register-summary + upsert-page but fails append-log would leave the
    vault partially mutated (source_hash footer ALREADY written → UC-4
    short-circuit traps re-runs). Guard fires BEFORE any dispatch."""

    def _ingest_with_title(self, tmp: Path, yaml_title_value: str) -> tuple[int, str]:
        """`yaml_title_value` is inserted verbatim into the frontmatter
        right of `title:` — pass quoted form for values containing `#`
        (YAML comment marker) or other YAML-significant chars."""
        vault = _build_single_course_vault(tmp)
        source = vault / "bad-title.md"
        source.write_text(
            f"---\ntype: summary\nname: bad-title\n"
            f"title: {yaml_title_value}\n---\n# x\n",
            encoding="utf-8",
        )
        rc, _, stderr = _capture(_ns(
            source=str(source), vault=str(vault),
            output_format="json",
        ))
        return rc, stderr

    def test_pipe_in_title_rejected_pre_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, stderr = self._ingest_with_title(Path(tmp), '"foo | bar"')
            self.assertEqual(rc, 2, "title with | must exit 2 (usage) BEFORE dispatch")
            self.assertIn("INVALID_TITLE", stderr)

    def test_log_heading_spoof_in_title_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Quote required: `#` is YAML's inline comment marker;
            # unquoted `## [...]` would parse as empty title.
            rc, stderr = self._ingest_with_title(Path(tmp), '"## [2099-01-01] foo"')
            self.assertEqual(rc, 2)
            self.assertIn("INVALID_TITLE", stderr)

    def test_no_vault_mutation_on_invalid_title(self):
        """The critical bit: NO files written before the guard fires."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            source = vault / "bad.md"
            source.write_text(
                "---\ntype: summary\nname: bad\ntitle: foo | bar\n---\n",
                encoding="utf-8",
            )
            rc, _, _ = _capture(_ns(
                source=str(source), vault=str(vault),
                output_format="json",
            ))
            self.assertEqual(rc, 2)
            # _sources/bad.md must NOT exist — register-summary never ran.
            self.assertFalse((vault / "_sources" / "bad.md").exists(),
                             "title-pre-validation must abort BEFORE register-summary")


class TestChildExitCodePropagation(unittest.TestCase):
    """Logic+Security critics (2026-05-27 vdd-multi): the partial envelope
    surfaces the dispatched atomic op's original exit code so consumers
    can distinguish security-class refusals from generic failures."""

    def test_child_exit_code_in_partial_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_single_course_vault(Path(tmp))
            source = vault / "source.md"
            source.write_text(
                "---\ntype: summary\nname: source\ntitle: t\n"
                "concepts:\n  - Foo\n---\n",
                encoding="utf-8",
            )
            from wiki_ingest.commands import ingest as ingest_cmd
            real_silent = ingest_cmd._dispatch_silent

            def patched(cmd_name, ns):
                if cmd_name == "upsert-page":
                    return 7  # simulate SYMLINK_OVERWRITE refusal
                return real_silent(cmd_name, ns)

            ingest_cmd._dispatch_silent = patched
            try:
                rc, stdout, _ = _capture(_ns(
                    source=str(source), vault=str(vault),
                    output_format="json",
                ))
            finally:
                ingest_cmd._dispatch_silent = real_silent

            self.assertEqual(rc, 20)
            envelope = json.loads(stdout)
            self.assertEqual(envelope["phase"], "upsert-page")
            self.assertEqual(envelope["child_exit_code"], 7,
                             "child_exit_code preserves the atomic op's "
                             "original exit code (here: 7 = SYMLINK_OVERWRITE)")


if __name__ == "__main__":
    unittest.main()

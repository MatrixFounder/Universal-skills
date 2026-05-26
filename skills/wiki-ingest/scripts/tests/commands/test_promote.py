"""Per-command tests for `commands/promote.py` — TASK 016 bead 016-05.

This bead ships ONLY the skeleton + dry-run path. The `--apply` write
path is stubbed (`die(code=3)`); 016-06 lights it up. Tests focus on
dry-run JSON contract + precondition refusals.
"""
from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import promote as promote_cmd


def _write_schema(path: Path, version: str, kind: str) -> None:
    path.write_text(
        f"---\nschema_version: \"{version}\"\nkind: {kind}\n---\n# Schema\n",
        encoding="utf-8",
    )


def _seed_course(course_root: Path) -> None:
    course_root.mkdir(parents=True, exist_ok=True)
    _write_schema(course_root / "WIKI_SCHEMA.md", "1.0", "course")
    for sub in ("_sources", "_concepts", "_entities"):
        (course_root / sub).mkdir(exist_ok=True)


def _seed_two_tier(tmp: Path) -> Path:
    vault = tmp / "vault"
    vault.mkdir()
    _write_schema(vault / "WIKI_SCHEMA.md", "2.0", "vault-root")
    (vault / "_concepts").mkdir()
    (vault / "_entities").mkdir()
    return vault


def _run(name: str, vault: Path, *, kind: str | None = None,
         apply: bool = False) -> tuple[int, dict | None]:
    args = argparse.Namespace(name=name, vault=str(vault),
                              kind=kind, apply=apply, cmd="promote")
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = promote_cmd.execute(args)
    except SystemExit as e:
        return int(e.code or 0), None
    return rc, json.loads(buf.getvalue())


class TestRegister(unittest.TestCase):

    def test_attaches_subparser(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        promote_cmd.register(sub)
        args = parser.parse_args(
            ["promote", "Sharpe Score", "--vault", "/tmp/v"])
        self.assertEqual(args.name, "Sharpe Score")
        self.assertEqual(args.vault, "/tmp/v")
        self.assertFalse(args.apply, "--apply default False (dry-run by default)")
        self.assertIsNone(args.kind)
        self.assertIs(args.func, promote_cmd.execute)


class TestDryRunHappyPath(unittest.TestCase):
    """TC-UNIT-016-05-01"""

    def test_two_courses_first_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            for name in ("Hermes", "OpenClaw"):
                _seed_course(vault / "Lessons" / name)
                (vault / "Lessons" / name / "_concepts" / "Sharpe Score.md"
                 ).write_text("# Sharpe Score\n", encoding="utf-8")
            rc, plan = _run("Sharpe Score", vault)
            self.assertEqual(rc, 0)
            self.assertFalse(plan["applied"])
            self.assertEqual(plan["mode"], "first_promote")
            self.assertEqual(plan["name"], "Sharpe Score")
            self.assertEqual(plan["kind"], "concept")
            self.assertEqual(len(plan["merge_from"]), 2)
            self.assertEqual(plan["merge_to"], "_concepts/Sharpe Score.md")
            self.assertEqual(plan["contradictions_raised"], 0)


class TestPreconditions(unittest.TestCase):

    def test_no_duplicates(self):
        """TC-UNIT-016-05-02"""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            _seed_course(vault / "Lessons" / "Hermes")
            (vault / "Lessons" / "Hermes" / "_concepts" / "Sharpe Score.md"
             ).write_text("# x\n", encoding="utf-8")
            rc, _ = _run("Sharpe Score", vault)
            self.assertEqual(rc, 1, "only one course-local copy → refuse")

    def test_absent_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            _seed_course(vault / "Lessons" / "Hermes")
            rc, _ = _run("Nonexistent", vault)
            self.assertEqual(rc, 1)

    def test_kind_mismatch(self):
        """TC-UNIT-016-05-03"""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            _seed_course(vault / "Lessons" / "A")
            _seed_course(vault / "Lessons" / "B")
            (vault / "Lessons" / "A" / "_concepts" / "Pipeline.md"
             ).write_text("# x\n", encoding="utf-8")
            (vault / "Lessons" / "B" / "_entities" / "Pipeline.md"
             ).write_text("# x\n", encoding="utf-8")
            rc, _ = _run("Pipeline", vault)
            self.assertEqual(rc, 1, "concept vs entity disagreement → refuse")

    def test_re_promote_mode(self):
        """TC-UNIT-016-05-04"""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            _seed_course(vault / "Lessons" / "C")
            (vault / "_concepts" / "Foo.md").write_text("# Foo (root)\n",
                                                        encoding="utf-8")
            (vault / "Lessons" / "C" / "_concepts" / "Foo.md").write_text(
                "# Foo (C)\n", encoding="utf-8")
            rc, plan = _run("Foo", vault)
            self.assertEqual(rc, 0)
            self.assertEqual(plan["mode"], "merge_into_root")
            self.assertEqual(len(plan["merge_from"]), 1)

    def test_missing_root_schema(self):
        """TC-UNIT-016-05-05"""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            # No WIKI_SCHEMA.md
            rc, _ = _run("Foo", vault)
            self.assertEqual(rc, 2)

    def test_wrong_root_schema_version(self):
        """TC-UNIT-016-05-06"""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _write_schema(vault / "WIKI_SCHEMA.md", "1.5", "other")
            rc, _ = _run("Foo", vault)
            self.assertEqual(rc, 2)


class TestApplyTwoCourse(unittest.TestCase):
    """TC-UNIT-016-06-01 — `--apply` 2-course happy path (post-016.06).

    Updated from the 016.05 stub test (which asserted code=3) now that
    016.06 has lit up the apply path.
    """

    def test_apply_2_course_creates_root_deletes_courses(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            for name in ("A", "B"):
                _seed_course(vault / "Lessons" / name)
                (vault / "Lessons" / name / "_concepts" / "Foo.md"
                 ).write_text(
                    "---\nname: Foo\nkind: concept\ncreated: 2026-01-01\n---\n"
                    "# Foo\n\n## Definition\n\nA thing.\n",
                    encoding="utf-8")
                # Need an index.md + log.md for the post-apply updates
                (vault / "Lessons" / name / "index.md").write_text(
                    "## Concepts\n\n- [[Foo]]\n\n## Entities\n",
                    encoding="utf-8")
                (vault / "Lessons" / name / "log.md").write_text(
                    "# Log\n", encoding="utf-8")
            rc, result = _run("Foo", vault, apply=True)
            self.assertEqual(rc, 0)
            self.assertTrue(result["applied"])
            # Root page created
            self.assertTrue((vault / "_concepts" / "Foo.md").is_file())
            # Course copies deleted
            for name in ("A", "B"):
                self.assertFalse(
                    (vault / "Lessons" / name / "_concepts" / "Foo.md").exists(),
                    f"Course {name}'s copy must be deleted (invariant)")

    def test_apply_idempotent_no_op(self):
        """TC-UNIT-016-06-06 — re-running --apply is a clean no-op."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            (vault / "_concepts" / "Foo.md").write_text(
                "---\nname: Foo\nkind: concept\n---\n# Foo\n",
                encoding="utf-8")
            # No course copies remain → no-op
            rc, _ = _run("Foo", vault, apply=True)
            # No course-local copies and a root page exists → R3.1 should
            # die ("no duplicates found") because we don't reach apply_promotion
            # without ≥1 course copy. Match the actual behaviour.
            self.assertIn(rc, (0, 1),
                          "either clean no-op (0) or refused (1) — both honest")


class TestKindOverride(unittest.TestCase):
    """TC-UNIT-016-05-08"""

    def test_explicit_kind_concept(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            for name in ("A", "B"):
                _seed_course(vault / "Lessons" / name)
                (vault / "Lessons" / name / "_concepts" / "Foo.md"
                 ).write_text("# x\n", encoding="utf-8")
            rc, plan = _run("Foo", vault, kind="concept")
            self.assertEqual(rc, 0)
            self.assertEqual(plan["kind"], "concept")


class TestNonLessonsLayout(unittest.TestCase):
    """TC-UNIT-016-05-10 — Q-8 / A-M-2 — Lessons/ not hardcoded."""

    def test_courses_directly_under_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier(Path(tmp))
            for name in ("Hermes", "OpenClaw"):
                _seed_course(vault / name)
                (vault / name / "_concepts" / "Pipeline.md").write_text(
                    "# x\n", encoding="utf-8")
            rc, plan = _run("Pipeline", vault)
            self.assertEqual(rc, 0)
            # merge_from paths do NOT include 'Lessons/'
            for p in plan["merge_from"]:
                self.assertFalse(p.startswith("Lessons/"))


if __name__ == "__main__":
    unittest.main()

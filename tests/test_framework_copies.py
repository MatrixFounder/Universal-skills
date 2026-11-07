#!/usr/bin/env python3
"""`scripts/check_framework_copies.py` reports each copy of a framework skill that drifted.

Six skills of `skills/` are full copies of skills that agentic-development maintains, and
nothing compared them: in 2026-11 five of the six differed, found by a manual `diff` (TASK 142
of agentic-development). The fixtures below cover each branch of the script. The last test runs
it on this repository; without the sibling repository, as in CI, that test is skipped and says
so.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_framework_copies.py"


def run(*args):
    """Run the script; return (exit code, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def write(path, data=b"x\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class Fixture:
    """A repository root with `skills/` and a canonical skills directory beside it."""

    def __init__(self, tmp):
        self.root = Path(tmp) / "repo"
        self.skills = self.root / "skills"
        self.canonical = Path(tmp) / "canonical" / ".agent" / "skills"
        self.skills.mkdir(parents=True)
        self.canonical.mkdir(parents=True)

    def skill(self, name, files, canonical_files=None):
        for rel, data in files.items():
            write(self.skills / name / rel, data)
        for rel, data in (files if canonical_files is None else canonical_files).items():
            write(self.canonical / name / rel, data)

    def check(self):
        return run("--root", str(self.root), "--canonical", str(self.canonical))


class TestBranches(unittest.TestCase):

    def test_identical_copy_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"SKILL.md": b"a\n", "references/r.md": b"r\n"})
            code, out, _ = fx.check()
        self.assertEqual(code, 0, out)
        self.assertIn("ok     alpha", out)
        self.assertIn("1 copy checked, 0 drifted, 0 not fully read", out)

    def test_a_differing_file_is_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"SKILL.md": b"copy\n"}, {"SKILL.md": b"canonical\n"})
            code, out, _ = fx.check()
        self.assertEqual(code, 1, out)
        self.assertIn("DRIFT  alpha: 1 entry", out)
        self.assertIn("differs: SKILL.md", out)

    def test_a_file_on_one_side_only_is_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"SKILL.md": b"a\n", "extra.md": b"e\n"},
                     {"SKILL.md": b"a\n", "scripts/new.py": b"n\n"})
            code, out, _ = fx.check()
        self.assertEqual(code, 1, out)
        self.assertIn("only in canonical: scripts/new.py", out)
        self.assertIn("only in copy: extra.md", out)

    def test_ignored_names_are_not_compared(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"SKILL.md": b"a\n"})
            for rel in (".DS_Store", "scripts/__pycache__/m.cpython-314.pyc.4372301", "scripts/m.pyc",
                        "scripts/.venv/bin/python", "scripts/node_modules/x/index.js",
                        ".pytest_cache/v", ".mypy_cache/x.json", ".ruff_cache/y"):
                write(fx.skills / "alpha" / rel, b"local\n")
            code, out, _ = fx.check()
        self.assertEqual(code, 0, out)

    def test_a_skill_canonical_does_not_carry_is_not_a_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"SKILL.md": b"a\n"})
            write(fx.skills / "own-skill" / "SKILL.md", b"only here\n")
            code, out, _ = fx.check()
        self.assertEqual(code, 0, out)
        self.assertNotIn("own-skill", out)

    def test_bytes_are_compared_not_text(self):
        """A line-ending change is drift: the copy must be byte-identical."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"SKILL.md": b"a\r\n"}, {"SKILL.md": b"a\n"})
            code, out, _ = fx.check()
        self.assertEqual(code, 1, out)

    def test_no_copy_found_is_an_error(self):
        """A canonical directory that shares no name with `skills/` compares nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            write(fx.skills / "alpha" / "SKILL.md")
            write(fx.canonical / "beta" / "SKILL.md")
            code, _, err = fx.check()
        self.assertEqual(code, 2)
        self.assertIn("no directory of", err)

    def test_canonical_that_is_not_a_directory_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            code, _, err = run("--root", str(fx.root), "--canonical", str(Path(tmp) / "absent"))
        self.assertEqual(code, 2)
        self.assertIn("is not a directory", err)

    def test_missing_skills_directory_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skills.rmdir()
            code, _, err = fx.check()
        self.assertEqual(code, 2)
        self.assertIn("is not a directory", err)

    def test_a_wrong_root_is_an_error_not_a_skip(self):
        """A mistyped --root has no skills/ and must not pass as SKIPPED."""
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run("--root", str(Path(tmp) / "typo"))
        self.assertEqual(code, 2, out)
        self.assertNotIn("SKIPPED", out)
        self.assertIn("is not a directory", err)

    def test_a_symlink_inside_a_skill_is_drift(self):
        """A link is not followed, so content behind it would go uncompared."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"SKILL.md": b"a\n"})
            write(Path(tmp) / "elsewhere" / "lib.py", b"x\n")
            try:
                os.symlink(Path(tmp) / "elsewhere", fx.skills / "alpha" / "lib",
                           target_is_directory=True)
                os.symlink(Path(tmp) / "elsewhere" / "lib.py", fx.canonical / "alpha" / "f.py")
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"no symlink on this platform: {exc}")
            code, out, _ = fx.check()
        self.assertEqual(code, 1, out)
        self.assertIn("symlink in copy: lib", out)
        self.assertIn("symlink in canonical: f.py", out)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "permission bits do not stop this user from reading")
    def test_an_unreadable_file_is_an_error_not_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"SKILL.md": b"a\n"})
            target = fx.skills / "alpha" / "SKILL.md"
            target.chmod(0)
            try:
                code, out, _ = fx.check()
            finally:
                target.chmod(0o644)
        self.assertEqual(code, 2, out)
        self.assertIn("unreadable: copy/SKILL.md", out)
        self.assertNotIn("DRIFT", out)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "permission bits do not stop this user from reading")
    def test_an_unreadable_directory_is_an_error(self):
        """os.walk skips a directory it cannot list unless told; the script must say so."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"SKILL.md": b"a\n", "refs/r.md": b"r\n"})
            target = fx.canonical / "alpha" / "refs"
            target.chmod(0)
            try:
                code, out, _ = fx.check()
            finally:
                target.chmod(0o755)
        self.assertEqual(code, 2, out)
        self.assertIn("unreadable: canonical/refs", out)
        self.assertNotIn("only in copy", out)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "permission bits do not stop this user from reading")
    def test_an_unlistable_skills_or_canonical_directory_is_an_error(self):
        for side in ("skills", "canonical"):
            with self.subTest(side=side), tempfile.TemporaryDirectory() as tmp:
                fx = Fixture(tmp)
                fx.skill("alpha", {"SKILL.md": b"a\n"})
                target = fx.skills if side == "skills" else fx.canonical
                target.chmod(0)
                try:
                    code, out, err = fx.check()
                finally:
                    target.chmod(0o755)
                self.assertEqual(code, 2, out + err)
                self.assertIn("cannot list", err)
                self.assertNotIn("Traceback", err)

    def test_a_copy_that_is_a_symlink_is_drift(self):
        """A copy linked into the unpublished sibling would dangle in the public repository."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            write(fx.canonical / "alpha" / "SKILL.md", b"a\n")
            try:
                os.symlink(fx.canonical / "alpha", fx.skills / "alpha", target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"no symlink on this platform: {exc}")
            code, out, _ = fx.check()
        self.assertEqual(code, 1, out)
        self.assertIn("DRIFT  alpha: the copy is a symlink", out)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFO on this platform")
    def test_a_fifo_is_reported_and_never_read(self):
        """Reading a FIFO would block forever; the script must not open one."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"SKILL.md": b"a\n"})
            os.mkfifo(fx.skills / "alpha" / "pipe")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(fx.root), "--canonical",
                 str(fx.canonical)], capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("special in copy: pipe", proc.stdout)

    @unittest.skipIf(os.name == "nt", "Windows has no executable bit")
    def test_a_lost_executable_bit_is_drift(self):
        """`cp` onto an existing file keeps the old mode, and git tracks the bit."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"run.sh": b"#!/bin/sh\n"})
            (fx.canonical / "alpha" / "run.sh").chmod(0o755)
            (fx.skills / "alpha" / "run.sh").chmod(0o644)
            code, out, _ = fx.check()
        self.assertEqual(code, 1, out)
        self.assertIn("mode differs: run.sh", out)

    def test_a_sibling_without_skills_is_an_error_not_a_skip(self):
        """`.agentic-development` that resolves to the wrong tree must not pass as SKIPPED."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            (fx.root / ".agentic-development").mkdir()
            code, out, err = run("--root", str(fx.root))
        self.assertEqual(code, 2, out)
        self.assertNotIn("SKIPPED", out)
        self.assertIn("is not a directory", err)

    def test_a_dangling_sibling_link_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            try:
                os.symlink(Path(tmp) / "gone", fx.root / ".agentic-development",
                           target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"no symlink on this platform: {exc}")
            code, out, _ = run("--root", str(fx.root))
        self.assertEqual(code, 0, out)
        self.assertIn("SKIPPED:", out)

    def test_a_closed_stdout_exits_2_without_a_second_error(self):
        """A reader that stops early (`| head -1`) gets exit 2 and a quiet stderr, not 120."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            files = {f"refs/r{i:05d}-a-long-name-that-fills-the-pipe.md": b"x" for i in range(3000)}
            fx.skill("alpha", dict(files, **{"SKILL.md": b"a\n"}), {"SKILL.md": b"a\n"})
            proc = subprocess.Popen(
                [sys.executable, str(SCRIPT), "--root", str(fx.root), "--canonical",
                 str(fx.canonical)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            proc.stdout.readline()
            proc.stdout.close()
            err = proc.stderr.read().decode("utf-8", "replace")
            proc.stderr.close()
            code = proc.wait(timeout=60)
        self.assertEqual(code, 2, err)
        self.assertNotIn("Exception ignored", err)
        self.assertNotIn("Traceback", err)

    def test_help_survives_an_ascii_locale(self):
        env = dict(os.environ, PYTHONIOENCODING="ascii", PYTHONUTF8="0", LC_ALL="C")
        proc = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--canonical", proc.stdout)

    def test_unresolved_default_canonical_is_skipped(self):
        """Without the sibling repository the script compares nothing and says so."""
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            code, out, _ = run("--root", str(fx.root))
        self.assertEqual(code, 0)
        self.assertIn("SKIPPED:", out)

    def test_default_canonical_follows_the_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"SKILL.md": b"copy\n"}, {"SKILL.md": b"canonical\n"})
            try:
                os.symlink(fx.canonical.parent.parent, fx.root / ".agentic-development",
                           target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"no symlink on this platform: {exc}")
            code, out, _ = run("--root", str(fx.root))
        self.assertEqual(code, 1, out)
        self.assertIn("differs: SKILL.md", out)

    def test_a_non_ascii_file_name_does_not_crash_an_ascii_stream(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(tmp)
            fx.skill("alpha", {"SKILL.md": b"a\n", "references/схема.md": b"c\n"},
                     {"SKILL.md": b"a\n"})
            env = dict(os.environ, PYTHONIOENCODING="ascii", PYTHONUTF8="0")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(fx.root),
                 "--canonical", str(fx.canonical)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
            )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("only in copy: references/", proc.stdout)


class TestThisRepository(unittest.TestCase):

    def test_every_copy_matches_canonical(self):
        canonical = REPO / ".agentic-development" / ".agent" / "skills"
        if not canonical.is_dir():
            self.skipTest(f"{canonical} does not resolve: the sibling repository is absent")
        code, out, err = run()
        self.assertEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main(verbosity=2)

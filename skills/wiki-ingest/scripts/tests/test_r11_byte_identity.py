"""R11 byte-identity gate for the TASK 015 wiki-ingest modular refactor.

Every bead 015.00..015.12 must run this test and see all four cases pass.
If any subcommand's stdout drifts even by a single byte from the captured
expected JSON, the refactor has introduced a behaviour change and the
bead must be reverted.

The `__VAULT_PATH__` placeholder in each expected JSON file is substituted
at runtime with the actual fixture path, so the gate is portable across
host machines and clone locations.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
WIKI_OPS = SCRIPTS_DIR / "wiki_ops.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

DETERMINISM_ITERATIONS = 10


def _run(cmd: str, target: Path, *, hash_seed: str | None = None) -> str:
    """Run `wiki_ops.py <cmd> <target>` and return stdout (raise on non-zero exit).

    `hash_seed` overrides `PYTHONHASHSEED` for this subprocess; used by the
    determinism loop to vary the seed across runs (defeats parent-env CI
    pinnings like `PYTHONHASHSEED=0` that would otherwise turn the loop
    into a tautology).

    `cwd` is pinned to SCRIPTS_DIR so any future relative-path drift in
    wiki_ops.py would surface as a test failure rather than a silent
    CI flake.
    """
    env = dict(os.environ)
    if hash_seed is not None:
        env["PYTHONHASHSEED"] = hash_seed
    result = subprocess.run(
        [sys.executable, str(WIKI_OPS), cmd, str(target)],
        capture_output=True, text=True, check=False,
        cwd=str(SCRIPTS_DIR), env=env,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"wiki_ops.py {cmd} {target} exited {result.returncode}:\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
    return result.stdout


def _expected(name: str, target: Path) -> str:
    """Load the expected JSON and substitute the placeholder with `target`'s absolute path."""
    raw = (FIXTURES / "expected" / f"{name}.json").read_text(encoding="utf-8")
    return raw.replace("__VAULT_PATH__", str(target.resolve()))


class R11ByteIdentity(unittest.TestCase):
    """One assertion per subcommand: stdout matches the captured expected."""

    def test_scan_byte_identity(self):
        target = FIXTURES / "scan_vault"
        got = _run("scan", target)
        expected = _expected("scan", target)
        self.assertEqual(got, expected,
                         "scan stdout drifted from tests/fixtures/expected/scan.json")

    def test_lint_byte_identity(self):
        target = FIXTURES / "lint_vault"
        got = _run("lint", target)
        expected = _expected("lint", target)
        self.assertEqual(got, expected,
                         "lint stdout drifted from tests/fixtures/expected/lint.json")

    def test_classify_byte_identity(self):
        target = FIXTURES / "classify_folder"
        got = _run("classify-folder", target)
        expected = _expected("classify", target)
        self.assertEqual(got, expected,
                         "classify-folder stdout drifted from "
                         "tests/fixtures/expected/classify.json")


class DeterminismAcrossRuns(unittest.TestCase):
    """Run each command N times under VARYING `PYTHONHASHSEED` values.

    Plain re-runs prove nothing if the parent shell pinned the seed
    (e.g. CI environments often export `PYTHONHASHSEED=0` for
    "reproducibility"). We explicitly set the seed to a different value
    on every iteration so any set→JSON path that omits `sorted()` is
    forced to manifest as a stdout diff.
    """

    def _assert_stable(self, cmd: str, target: Path):
        # First run uses seed "0" (baseline); subsequent runs cycle through
        # explicit seeds + the special "random" sentinel so we cover both
        # fixed-seed reproducibility AND per-run randomness.
        # PYTHONHASHSEED only accepts decimal integers in [0, 4294967295]
        # or the literal string "random". No hex literals.
        seeds = ["0", "1", "42", "12345", "65535", "random",
                 "999983", "2024", "3735928559", "random"]
        # Guarantee N seeds to match N iterations
        assert len(seeds) == DETERMINISM_ITERATIONS
        first = _run(cmd, target, hash_seed=seeds[0])
        for i, seed in enumerate(seeds[1:], start=2):
            other = _run(cmd, target, hash_seed=seed)
            self.assertEqual(
                first, other,
                f"{cmd} stdout drifted between PYTHONHASHSEED={seeds[0]!r} "
                f"and PYTHONHASHSEED={seed!r} (iteration {i}) — "
                f"non-deterministic ordering, likely a set iterated into "
                f"JSON without sorting",
            )

    def test_scan_stable_across_runs(self):
        self._assert_stable("scan", FIXTURES / "scan_vault")

    def test_lint_stable_across_runs(self):
        self._assert_stable("lint", FIXTURES / "lint_vault")

    def test_classify_stable_across_runs(self):
        self._assert_stable("classify-folder", FIXTURES / "classify_folder")


if __name__ == "__main__":
    unittest.main()

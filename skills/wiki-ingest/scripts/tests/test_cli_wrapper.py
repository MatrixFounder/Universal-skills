"""Unit + E2E tests for the wiki-ingest CLI wrapper surface (TASK 017).

This bead (017-00) locks:

- `wiki_ingest.__version__` is a well-formed semver string `>= "1.1.0"`.
- `wiki_ops.py --version` exits 0 with the exact stdout
  `"wiki-ingest <version>\\n"` (CONTRACT §7 minimum-version prefix
  match).
- The `--version` fast path does NOT eagerly load any
  `wiki_ingest.commands.*` module — defends the architecture §8
  ≤50 ms budget against future regressions.

Bead 017-01 extends with shell-wrapper assertions (executable bit,
no shell-injection surface, POSIX shebang, dispatch equivalence,
symlinked-with-spaces path).
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import wiki_ingest


SCRIPTS_DIR = Path(__file__).resolve().parent.parent
WIKI_OPS = SCRIPTS_DIR / "wiki_ops.py"
WRAPPER = SCRIPTS_DIR / "wiki-ingest"

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class TestVersionConstant(unittest.TestCase):
    """TC-UNIT-017-00-01 — single source of truth for the skill version."""

    def test_version_string_shape(self):
        self.assertTrue(hasattr(wiki_ingest, "__version__"),
                        "wiki_ingest must expose __version__")
        version = wiki_ingest.__version__
        self.assertIsInstance(version, str)
        self.assertRegex(version, _SEMVER_RE,
                         f"__version__={version!r} not semver MAJOR.MINOR.PATCH")

    def test_version_meets_minimum(self):
        """CONTRACT §7 — consumers may prefix-check `>= 1.1`."""
        parts = tuple(int(p) for p in wiki_ingest.__version__.split("."))
        self.assertGreaterEqual(parts, (1, 1, 0),
                                f"version {wiki_ingest.__version__} < 1.1.0")


class TestVersionActionNoEagerCommandImports(unittest.TestCase):
    """TC-UNIT-017-00-02 — `--version` does NOT pay the command-import tax.

    Spawns a child interpreter (clean `sys.modules`) that runs
    `wiki_ops.main(["--version"])` and reports which `wiki_ingest.commands.*`
    modules it ended up loading. The `main()` fast path SystemExits before
    dispatching to argparse / build_parser, so the report's `commands`
    subset must be empty.
    """

    def test_version_does_not_import_command_modules(self):
        # The child script invokes main(["--version"]) in a pristine
        # interpreter, then introspects sys.modules. The exit mechanism
        # (return-0 vs SystemExit(0)) is immaterial — what matters is the
        # commands subset stays empty.
        probe = (
            "import sys\n"
            f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
            "import wiki_ops\n"
            "try:\n"
            "    rc = wiki_ops.main(['--version'])\n"
            "except SystemExit as exc:\n"
            "    rc = exc.code\n"
            "cmds = sorted(k for k in sys.modules "
            "             if k.startswith('wiki_ingest.commands'))\n"
            "# Trailing sentinel survives any stdout from main() above.\n"
            "sys.stdout.write(f'\\nPROBE_RC={rc!r}|PROBE_CMDS={cmds!r}\\n')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0,
                         f"probe child failed: stderr={result.stderr!r}")
        # Extract the probe record (last line) — main() writes the version
        # banner first; we don't care about its position.
        record = next(line for line in result.stdout.splitlines()
                      if line.startswith("PROBE_RC="))
        self.assertIn("PROBE_RC=0|", record,
                      f"main(['--version']) did not return 0: {record}")
        self.assertIn("PROBE_CMDS=[]", record,
                      f"--version eagerly imported commands: {record}")


class TestVersionActionE2E(unittest.TestCase):
    """TC-E2E-017-00-01..02 — invoke `wiki_ops.py --version` as a subprocess."""

    def _run(self, args):
        return subprocess.run(
            [sys.executable, str(WIKI_OPS), *args],
            capture_output=True, text=True, timeout=10,
        )

    def test_version_stdout_exact_format(self):
        result = self._run(["--version"])
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        self.assertEqual(result.stderr, "")
        # Exact match including trailing newline.
        self.assertEqual(result.stdout, f"wiki-ingest {wiki_ingest.__version__}\n")

    def test_version_prefix_consumer_contract(self):
        """CONTRACT §7 minimum-version check using string-prefix +
        tuple compare — matches what `/wiki-enrich` does."""
        result = self._run(["--version"])
        self.assertEqual(result.returncode, 0)
        parts = result.stdout.strip().split()
        self.assertEqual(parts[0], "wiki-ingest")
        # Tuple-of-ints comparison ≥ (1, 1).
        ver_tuple = tuple(int(p) for p in parts[1].split(".")[:2])
        self.assertGreaterEqual(ver_tuple, (1, 1),
                                f"published version {parts[1]} below 1.1 floor")


class TestShellWrapperFile(unittest.TestCase):
    """TC-UNIT-017-01-01..04 — static properties of `scripts/wiki-ingest`."""

    def test_wrapper_is_executable(self):
        """TC-UNIT-017-01-01."""
        self.assertTrue(WRAPPER.exists(), f"wrapper missing: {WRAPPER}")
        mode = WRAPPER.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR,
                        f"wrapper not executable (mode={oct(mode)})")

    def test_wrapper_posix_shebang(self):
        """TC-UNIT-017-01-03."""
        first_line = WRAPPER.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first_line, "#!/bin/sh",
                         "wrapper must use POSIX /bin/sh shebang for portability")

    def test_wrapper_no_unquoted_argv(self):
        """TC-UNIT-017-01-02 — locks T17-S8 invariant.

        Static check: `$@` must always appear inside double quotes;
        `$0` must always appear inside double quotes. No bare `$@` or
        bare `$0` anywhere in the script body.
        """
        body = WRAPPER.read_text(encoding="utf-8")
        # Strip the comment lines so we don't false-positive on prose.
        code_lines = [ln for ln in body.splitlines()
                      if ln.strip() and not ln.lstrip().startswith("#")]
        code = "\n".join(code_lines)
        # Find every occurrence of `$@` and `$0` and require the
        # immediately preceding char to be `"`.
        for token in ("$@", "$0"):
            idx = 0
            while True:
                idx = code.find(token, idx)
                if idx < 0:
                    break
                self.assertGreater(idx, 0,
                                   f"{token!r} appears at position 0 of code")
                self.assertEqual(code[idx - 1], '"',
                                 f"unquoted {token!r} at offset {idx}: ...{code[max(0,idx-5):idx+5]!r}...")
                idx += len(token)


class TestShellWrapperDispatch(unittest.TestCase):
    """TC-E2E-017-01-01..03 — invoke the wrapper as a real subprocess."""

    def _run_wrapper(self, args, cwd=None):
        return subprocess.run(
            [str(WRAPPER), *args],
            capture_output=True, text=True, timeout=10, cwd=cwd,
        )

    def _run_direct(self, args):
        return subprocess.run(
            [sys.executable, str(WIKI_OPS), *args],
            capture_output=True, text=True, timeout=10,
        )

    def test_wrapper_version_roundtrip(self):
        """TC-E2E-017-01-01 — wrapper exits 0 with the exact version string."""
        result = self._run_wrapper(["--version"])
        self.assertEqual(result.returncode, 0,
                         f"stderr={result.stderr!r}")
        self.assertEqual(result.stdout, f"wiki-ingest {wiki_ingest.__version__}\n")

    def test_wrapper_dispatch_equivalent_to_direct(self):
        """TC-E2E-017-01-02 — `wrapper <sub>` ≡ `python3 wiki_ops.py <sub>`.

        Uses a benign subcommand (`scan` on a temp empty dir) so we
        exercise dispatch without state mutation. Both invocations must
        produce identical stdout / stderr / exit code.
        """
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            # `scan` on a vault without WIKI_SCHEMA.md exits non-zero —
            # but BOTH paths must produce the SAME non-zero result.
            via_wrapper = self._run_wrapper(["scan", str(vault)])
            via_direct = self._run_direct(["scan", str(vault)])
        self.assertEqual(via_wrapper.returncode, via_direct.returncode,
                         "exit codes diverge")
        self.assertEqual(via_wrapper.stdout, via_direct.stdout,
                         "stdout diverges")
        self.assertEqual(via_wrapper.stderr, via_direct.stderr,
                         "stderr diverges")

    def test_wrapper_resolves_from_symlink_with_spaces(self):
        """TC-E2E-017-01-03 — readlink -f + quoted "$@" cooperate.

        Creates a symlink in a directory whose name contains a space.
        Invoking the symlink must still resolve back to the real
        wrapper and exec wiki_ops.py.
        """
        with tempfile.TemporaryDirectory(prefix="wi spaced ") as tmp:
            link = Path(tmp) / "wiki-ingest"
            link.symlink_to(WRAPPER)
            result = subprocess.run(
                [str(link), "--version"],
                capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(result.returncode, 0,
                         f"stderr={result.stderr!r}")
        self.assertEqual(result.stdout,
                         f"wiki-ingest {wiki_ingest.__version__}\n")


if __name__ == "__main__":
    unittest.main()

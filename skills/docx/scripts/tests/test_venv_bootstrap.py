"""Unit tests for ``_venv_bootstrap.py`` (TASK 019-01).

Locks the self-bootstrap contract:
  * stdlib-only (importable under any interpreter);
  * position-independent ``scripts/`` resolution (scripts/*.py and office/*.py);
  * re-exec only when NOT already in the target venv — keyed on ``sys.prefix``,
    NOT ``realpath(sys.executable)`` (a pyenv venv symlinks to the same base
    binary, so the executable realpaths are identical — see module docstring);
  * legible failure when the venv is absent and a required dep is missing;
  * single re-exec (loop guard) — locks I-1.

Run::  cd skills/docx && ./.venv/bin/python -m unittest tests.test_venv_bootstrap -v
"""

import ast
import io
import os
import sys
import unittest
from contextlib import redirect_stderr

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tests/ -> scripts/
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import _venv_bootstrap  # noqa: E402

_FLAG = _venv_bootstrap._REEXEC_FLAG

# Tests that assert the "already in the venv" branch are only meaningful when the runner
# IS the skill's venv (sys.prefix == scripts/.venv). Under a bare `python3` they would see
# in_venv=False and (correctly) re-exec — skip rather than mislead.
_IN_TARGET_VENV = (os.path.realpath(sys.prefix)
                   == os.path.realpath(os.path.join(SCRIPTS, ".venv")))


class _ExecvRecorder:
    """Stand-in for os.execv that records calls instead of replacing the process."""

    def __init__(self):
        self.calls = []

    def __call__(self, path, argv):
        self.calls.append((path, list(argv)))


class BootstrapTestBase(unittest.TestCase):
    def setUp(self):
        self._saved_execv = os.execv
        self._saved_flag = os.environ.pop(_FLAG, None)

    def tearDown(self):
        os.execv = self._saved_execv
        if self._saved_flag is None:
            os.environ.pop(_FLAG, None)
        else:
            os.environ[_FLAG] = self._saved_flag


class TestStdlibOnly(BootstrapTestBase):
    def test_no_third_party_imports(self):
        with open(_venv_bootstrap.__file__, encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        allowed = {"os", "sys", "importlib", "importlib.util", "__future__"}
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        offending = {n for n in names if n.split(".")[0] not in
                     {"os", "sys", "importlib", "__future__"}}
        self.assertEqual(offending, set(),
                         f"helper must be stdlib-only; found {offending}")


class TestScriptsRoot(BootstrapTestBase):
    def test_scripts_level(self):
        self.assertEqual(
            _venv_bootstrap._scripts_root(os.path.join(SCRIPTS, "preview.py")),
            SCRIPTS)

    def test_office_level(self):
        # office/*.py lives one level below scripts/; the helper must still
        # resolve up to scripts/ (where .venv + install.sh live).
        self.assertEqual(
            _venv_bootstrap._scripts_root(os.path.join(SCRIPTS, "office", "unpack.py")),
            SCRIPTS)


class TestReexecDecision(BootstrapTestBase):
    @unittest.skipUnless(_IN_TARGET_VENV, "must run under the skill's scripts/.venv")
    def test_already_in_venv_is_noop(self):
        # The test runner IS the venv python -> sys.prefix == scripts/.venv,
        # so pointing at the real scripts dir must NOT re-exec.
        rec = _ExecvRecorder()
        os.execv = rec
        _venv_bootstrap.reexec_into_venv(
            requires=("PIL",), _file=os.path.join(SCRIPTS, "preview.py"))
        self.assertEqual(rec.calls, [], "must not re-exec when already in the venv")

    def test_reexec_when_not_in_venv(self):
        # A fake venv whose root != the real sys.prefix -> must re-exec exactly once.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            venv_bin = os.path.join(d, ".venv", "bin")
            os.makedirs(venv_bin)
            fake_py = os.path.join(venv_bin, "python")
            open(fake_py, "w").close()
            rec = _ExecvRecorder()
            os.execv = rec
            _venv_bootstrap.reexec_into_venv(
                requires=("PIL",), _file=os.path.join(d, "preview.py"))
            self.assertEqual(len(rec.calls), 1, "must re-exec exactly once")
            path, argv = rec.calls[0]
            self.assertEqual(path, fake_py)
            self.assertEqual(argv, [fake_py, *sys.argv], "argv must be preserved")
            self.assertEqual(os.environ.get(_FLAG), "1", "loop-guard flag must be set")

    def test_import_chain_idempotent_loop_guard(self):
        # I-1: with the loop-guard flag already set, a not-in-venv call must NOT
        # re-exec a second time (models an entrypoint that already bootstrapped
        # then imports a helper / re-enters).
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            venv_bin = os.path.join(d, ".venv", "bin")
            os.makedirs(venv_bin)
            open(os.path.join(venv_bin, "python"), "w").close()
            os.environ[_FLAG] = "1"
            rec = _ExecvRecorder()
            os.execv = rec
            _venv_bootstrap.reexec_into_venv(
                requires=("PIL",), _file=os.path.join(d, "preview.py"))
            self.assertEqual(rec.calls, [], "loop guard must prevent a second re-exec")

    @unittest.skipUnless(_IN_TARGET_VENV, "must run under the skill's scripts/.venv")
    def test_sentinel_consumed_not_propagated(self):
        # SEC-1: the loop-guard sentinel must be POPPED from os.environ on entry so a
        # correctly-bootstrapped process never leaks it to its children (a Python-of-Python
        # child must be free to bootstrap itself).
        os.environ[_FLAG] = "1"
        rec = _ExecvRecorder()
        os.execv = rec
        # in_venv path (real scripts dir; the test runner IS the venv) -> returns, no exec.
        _venv_bootstrap.reexec_into_venv(
            requires=("PIL",), _file=os.path.join(SCRIPTS, "preview.py"))
        self.assertEqual(rec.calls, [])
        self.assertNotIn(_FLAG, os.environ, "sentinel must be consumed, not propagated")


class TestVenvAbsent(BootstrapTestBase):
    def test_missing_dep_exits_legibly(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            # no .venv, no install.sh -> _scripts_root falls back to `here`
            buf = io.StringIO()
            with redirect_stderr(buf):
                with self.assertRaises(SystemExit) as cm:
                    _venv_bootstrap.reexec_into_venv(
                        requires=("definitely_absent_module_xyz",),
                        _file=os.path.join(d, "preview.py"))
            self.assertEqual(cm.exception.code, 1)
            msg = buf.getvalue()
            self.assertIn("run:", msg)
            self.assertIn("install.sh", msg)
            self.assertIn("definitely_absent_module_xyz", msg)

    def test_present_dep_returns(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            # "os" is always importable -> no exit, returns None
            result = _venv_bootstrap.reexec_into_venv(
                requires=("os",), _file=os.path.join(d, "preview.py"))
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

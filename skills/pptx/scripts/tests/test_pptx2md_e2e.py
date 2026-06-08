"""End-to-end CLI tests for pptx2md (bead 020-01 smoke; tightened in 020-02..05).

Subprocess the shim ``scripts/pptx2md.py`` so the real entrypoint (incl. the
_venv_bootstrap prelude) is exercised exactly as a user invokes it.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]  # skills/pptx/scripts
_SHIM = _SCRIPTS / "pptx2md.py"


def _run(args, **kw):
    return subprocess.run(
        [sys.executable, str(_SHIM), *args],
        capture_output=True, text=True, cwd=str(_SCRIPTS), **kw,
    )


class TestHelpSurface(unittest.TestCase):
    def test_help_lists_surface(self):
        r = _run(["--help"])
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        for token in (
            "INPUT", "OUTPUT", "--ocr", "--ocr-lang", "--no-images",
            "--media-dir", "--no-notes", "--include-hidden", "--json-errors",
            "eng+rus",
        ):
            self.assertIn(token, out, f"--help missing {token!r}")


if __name__ == "__main__":
    unittest.main()

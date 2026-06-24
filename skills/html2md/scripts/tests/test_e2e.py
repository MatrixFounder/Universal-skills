"""Bead 022-01 E2E smoke (stub phase): the CLI ``--help`` lists the frozen surface.

Later beads (022-02…06) add full-pipeline E2E here.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(SCRIPTS, "html2md.py")


class TestHelpSurface(unittest.TestCase):
    def test_help_lists_surface(self):
        """TC-E2E-01: `python3 html2md.py --help` exits 0 and lists the surface."""
        r = subprocess.run(
            [sys.executable, SHIM, "--help"], cwd=SCRIPTS,
            capture_output=True, text=True,
            env={**os.environ, "HTML2MD_NO_DOTENV": "1"},  # hermetic: ignore a dev's skill .env
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        for needle in (
            "INPUT", "OUTPUT_DIR", "--engine", "--reader-mode", "--no-reader",
            "--download-images", "--no-download-images", "--attachments-dir",
            "--archive-frame", "--max-bytes", "--stdout", "--json-errors",
            "_attachments",
        ):
            self.assertIn(needle, out, f"--help missing: {needle}")


if __name__ == "__main__":
    unittest.main()

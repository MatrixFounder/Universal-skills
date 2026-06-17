"""Bead 022-03 — FC-3 Node turndown core + Python bridge. Requires `node` + npm deps."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import core_bridge  # noqa: E402
from html2md.exceptions import ConvertFailed  # noqa: E402

_HAVE_NODE = shutil.which("node") is not None and os.path.isdir(
    os.path.join(SCRIPTS, "node_modules", "turndown")
)


@unittest.skipUnless(_HAVE_NODE, "node + turndown not installed (run install.sh)")
class TestCore(unittest.TestCase):
    def test_core_basic(self):
        """TC-03-01: headings/inline → GFM Markdown."""
        md = core_bridge.html_to_markdown(
            "<h1>Title</h1><p>Hello <strong>world</strong></p>")
        self.assertIn("# Title", md)
        self.assertIn("**world**", md)

    def test_core_gfm_table_rowspan(self):
        """TC-03-02: rowspan → flat grid (anchor value + empty slot)."""
        md = core_bridge.html_to_markdown(
            '<table><tr><td rowspan="2">A</td><td>b</td></tr>'
            "<tr><td>c</td></tr></table>")
        self.assertIn("| A | b |", md)
        self.assertIn("|  | c |", md)  # rowspan leaves the second-row first cell empty

    def test_core_pure_filter(self):
        """TC-03-03: html2md_core.js is a pure stdin→stdout filter, exit 0."""
        r = subprocess.run(
            ["node", os.path.join(SCRIPTS, "html2md_core.js")],
            input="<h1>x</h1>", capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# x", r.stdout)

    def test_bridge_roundtrip(self):
        """TC-03-04: bridge returns Markdown."""
        self.assertIn("hi", core_bridge.html_to_markdown("<p>hi</p>"))


class TestBridgeErrors(unittest.TestCase):
    def test_node_error_raises_convertfailed(self):
        """TC-03-04b: a failing core (bad script path) → ConvertFailed, not a crash."""
        saved = core_bridge._CORE_JS
        core_bridge._CORE_JS = os.path.join(SCRIPTS, "does_not_exist_core.js")
        try:
            with self.assertRaises(ConvertFailed):
                core_bridge.html_to_markdown("<p>x</p>")
        finally:
            core_bridge._CORE_JS = saved

    def test_node_missing_raises_convertfailed(self):
        """TC-03-04c: node executable absent (FileNotFoundError) → ConvertFailed."""
        saved = core_bridge.subprocess.run

        def _boom(*a, **k):
            raise FileNotFoundError("node")

        core_bridge.subprocess.run = _boom
        try:
            with self.assertRaises(ConvertFailed) as ctx:
                core_bridge.html_to_markdown("<p>x</p>")
            self.assertEqual(ctx.exception.details.get("reason"), "node-missing")
        finally:
            core_bridge.subprocess.run = saved


if __name__ == "__main__":
    unittest.main()

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

    def test_spaced_destination_wrapped_in_angle_brackets(self):
        """A src/href containing spaces or parens must emit a CommonMark
        angle-bracketed destination — bare it is invalid Markdown and emit.py's
        localization regex skips it (Confluence archives localize attachments
        to decoded filenames with spaces)."""
        md = core_bridge.html_to_markdown(
            '<p>x</p>'
            '<img src="Снимок экрана 2021-03-10 в 12.58.03.png" alt="">'
            '<img src="plain.png" alt="">'
            '<a href="page (v2).html">doc</a>')
        self.assertIn("![](<Снимок экрана 2021-03-10 в 12.58.03.png>)", md)
        self.assertIn("![](plain.png)", md)          # no-space src stays bare
        self.assertIn("[doc](<page (v2).html>)", md)

    def test_destination_angle_bracket_chars_encoded(self):
        """`<`/`>` inside a wrapped destination would terminate the bracket —
        they must be percent-encoded; tabs/newlines are stripped (URL spec)."""
        md = core_bridge.html_to_markdown('<img src="a &lt;b&gt; c.png" alt="">')
        self.assertIn("![](<a %3Cb%3E c.png>)", md)

    def test_destination_backslash_encoded(self):
        """`\\` is an ESCAPE inside <…> (CommonMark): a trailing one reads as
        `\\>` and unterminates the destination; `\\.`→`.` silently retargets.
        It must be percent-encoded alongside the bracket chars."""
        md = core_bridge.html_to_markdown(
            '<img src="a b\\.png" alt="p"><a href="..\\file (2)\\">win</a>')
        self.assertIn("![p](<a b%5C.png>)", md)
        self.assertIn("[win](<..%5Cfile (2)%5C>)", md)

    def test_destination_padding_trimmed(self):
        """Leading/trailing whitespace in href is junk padding (URL spec trims
        C0-control/space) — after the trim a space-free URL stays a bare
        destination instead of being <>-wrapped with the padding inside."""
        md = core_bridge.html_to_markdown(
            '<a href="    /display/~user@example.com\n   ">profile</a>')
        self.assertIn("[profile](/display/~user@example.com)", md)


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

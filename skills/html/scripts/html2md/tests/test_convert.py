"""html_convert.js wrapper: ARIA-role tables → GFM + chrome-button strip.

Exercised through the Python bridge (core_bridge → html_convert.js). Requires node.
"""
from __future__ import annotations

import os
import shutil
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import core_bridge  # noqa: E402

_HAVE_NODE = shutil.which("node") is not None and os.path.isdir(
    os.path.join(SCRIPTS, "node_modules", "turndown"))


@unittest.skipUnless(_HAVE_NODE, "node + turndown not installed")
class TestAriaTableAndChrome(unittest.TestCase):
    def test_aria_table_to_gfm(self):
        """role=table/columnheader/cell → a GFM table (not flattened paragraphs)."""
        html = (
            '<div role="table"><div role="rowgroup">'
            '<div role="row"><div role="columnheader">Name</div>'
            '<div role="columnheader">Type</div></div></div>'
            '<div role="rowgroup">'
            '<div role="row"><div role="cell"><p>type</p></div>'
            '<div role="cell"><p>String</p></div></div>'
            '<div role="row"><div role="cell"><p>dex</p></div>'
            '<div role="cell"><p>String</p></div></div>'
            "</div></div>")
        md = core_bridge.html_to_markdown(html)
        self.assertIn("| Name | Type |", md)
        self.assertIn("|---|---|", md)
        self.assertIn("| type | String |", md)
        self.assertIn("| dex | String |", md)

    def test_gitbook_sibling_headers(self):
        """Headers in a SIBLING rowgroup (GitBook) are pulled into the table."""
        html = (
            '<div class="wrap">'
            '<div role="rowgroup"><div role="row">'
            '<div role="columnheader">Name</div><div role="columnheader">Value</div>'
            "</div></div>"
            '<div role="table"><div role="rowgroup"><div role="row">'
            '<div role="cell">Content-Type</div><div role="cell">application/json</div>'
            "</div></div></div></div>")
        md = core_bridge.html_to_markdown(html)
        self.assertIn("| Name | Value |", md)
        self.assertIn("| Content-Type | application/json |", md)

    def test_buttons_and_copy_stripped(self):
        """<button>, role=button and aria-label^=Copy controls are removed."""
        html = ('<p>keep</p>'
                '<button type="button"><svg></svg><span>Copy</span></button>'
                '<div role="button" aria-label="Copy page">Copy page</div>')
        md = core_bridge.html_to_markdown(html)
        self.assertIn("keep", md)
        self.assertNotIn("Copy", md)

    def test_nested_aria_table_not_merged(self):
        """A nested role=table inside a cell stays separate — outer grid not polluted."""
        html = (
            '<div role="table"><div role="row">'
            '<div role="columnheader">Outer</div></div>'
            '<div role="row"><div role="cell">'
            '<div role="table"><div role="row"><div role="columnheader">Inner</div></div>'
            '<div role="row"><div role="cell">innerval</div></div></div>'
            "</div></div></div>")
        md = core_bridge.html_to_markdown(html)
        # Outer header row must NOT have absorbed the inner table's "Inner" column.
        self.assertNotIn("| Outer | Inner |", md)
        self.assertIn("Inner", md)  # inner table still rendered somewhere

    def test_two_tables_one_wrapper_headers_isolated(self):
        """Two tables under one wrapper keep their OWN preceding-sibling headers."""
        html = (
            '<div class="wrap">'
            '<div role="rowgroup"><div role="row">'
            '<div role="columnheader">HdrA</div></div></div>'
            '<div role="table"><div role="row"><div role="cell">valA</div></div></div>'
            '<div role="rowgroup"><div role="row">'
            '<div role="columnheader">HdrB</div></div></div>'
            '<div role="table"><div role="row"><div role="cell">valB</div></div></div>'
            "</div>")
        md = core_bridge.html_to_markdown(html)
        self.assertIn("| HdrA |", md)
        self.assertIn("| valA |", md)
        self.assertIn("| HdrB |", md)
        self.assertIn("| valB |", md)
        self.assertNotIn("| HdrA | HdrB |", md)  # headers not concatenated across tables

    def test_accordion_role_button_prose_preserved(self):
        """A role=button DIV wrapping real prose is kept; a leaf role=button is dropped."""
        md = core_bridge.html_to_markdown(
            '<div role="button"><p>Accordion prose marker</p></div>'
            '<div role="button">ExpandLeaf</div>')
        self.assertIn("Accordion prose marker", md)
        self.assertNotIn("ExpandLeaf", md)

    def test_multiline_link_collapsed_and_icon_anchor_dropped(self):
        """Block-content links collapse to one line; icon-only anchors are dropped."""
        md = core_bridge.html_to_markdown(
            '<a href="https://x/y"><div><div>Nav Item Text</div></div></a>'
            '<h2><a href="#sec"><svg></svg></a></h2>')
        self.assertIn("[Nav Item Text](https://x/y)", md)
        self.assertNotRegex(md, r"\]\(\s*\n")          # link never split across lines
        self.assertNotRegex(md, r"(?m)^#{1,6} \[")      # icon-only heading anchor dropped

    def test_real_link_text_preserved(self):
        """A normal inline link keeps its text + href."""
        md = core_bridge.html_to_markdown('<p>see <a href="https://x">the docs</a> now</p>')
        self.assertIn("[the docs](https://x)", md)

    def test_ltx_listing_to_code_block(self):
        """arXiv/LaTeXML ltx_listing → fenced code; line-number gutter dropped."""
        html = (
            '<div class="ltx_listing">'
            '<div class="ltx_listingline"><span class="ltx_tag ltx_tag_listingline">1</span>'
            '<span class="ltx_text ltx_font_typewriter">PROMPT = "hi"</span></div>'
            '<div class="ltx_listingline"><span class="ltx_tag ltx_tag_listingline">2</span></div>'
            '<div class="ltx_listingline"><span class="ltx_tag ltx_tag_listingline">3</span>'
            '<span class="ltx_text ltx_font_typewriter">end()</span></div>'
            "</div>")
        md = core_bridge.html_to_markdown(html)
        self.assertIn("```", md)
        self.assertIn('PROMPT = "hi"', md)
        self.assertIn("end()", md)
        self.assertNotIn("1PROMPT", md)             # gutter not glued onto first token
        self.assertNotRegex(md, r"(?m)^\s*[123]\s*$")  # bare gutter numbers dropped

    def test_data_uri_image_and_link_dropped(self):
        """base64 data: images/links don't dump blobs; real images survive."""
        md = core_bridge.html_to_markdown(
            '<p>keep</p>'
            '<img src="data:image/png;base64,AAAABBBBCCCC">'
            '<img src="https://x/real.png" alt="r">'
            '<a href="data:text/plain;base64,ZZZZ">dl</a>')
        self.assertNotIn("data:", md)
        self.assertIn("![r](https://x/real.png)", md)
        self.assertIn("keep", md)

    def test_plain_table_still_works(self):
        """A real <table> still converts (core path unaffected by the ARIA rule)."""
        md = core_bridge.html_to_markdown(
            "<table><tr><th>H</th></tr><tr><td>v</td></tr></table>")
        self.assertIn("| H |", md)
        self.assertIn("| v |", md)


if __name__ == "__main__":
    unittest.main()

"""Bead 022-04 — FC-2 web_clean wiring (preprocess + reader-mode). AC-R2 reader needle."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import acquire as acquire_mod  # noqa: E402
from html2md.clean import clean  # noqa: E402
from html2md.cli import build_parser  # noqa: E402
from html2md.model import AcquireResult  # noqa: E402

_FILLER = "Lorem ipsum dolor sit amet consectetur adipiscing elit. " * 40

_SPA_HTML = f"""<!doctype html><html><head><title>SPA</title>
<style>.x{{color:red}}</style></head><body>
  <nav role="navigation"><a href="#">SIDEBARNAVNEEDLE</a></nav>
  <header role="banner"><div>BANNERNEEDLE</div></header>
  <main role="main"><article><h1>The Article</h1>
    <p>ARTICLEBODYNEEDLE {_FILLER}</p></article></main>
  <footer role="contentinfo"><div>FOOTERNEEDLE</div></footer>
</body></html>"""


def _acq(html: str) -> AcquireResult:
    return AcquireResult(html=html, base_url="file:///t", mode="file")


class TestClean(unittest.TestCase):
    def test_preprocess_strips_chrome(self):
        """TC-04-01: preprocess removes nav chrome from the whole page."""
        res = clean(_acq(_SPA_HTML), reader=False)
        self.assertIn("ARTICLEBODYNEEDLE", res.whole_html)
        self.assertNotIn("SIDEBARNAVNEEDLE", res.whole_html)  # nav stripped
        self.assertIsNone(res.reader_html)

    def test_reader_needles_spa(self):
        """TC-04-02 (AC-R2): reader keeps the article body, drops nav/banner/footer."""
        res = clean(_acq(_SPA_HTML), reader=True)
        self.assertIsNotNone(res.reader_html)
        self.assertIn("ARTICLEBODYNEEDLE", res.reader_html)
        self.assertNotIn("SIDEBARNAVNEEDLE", res.reader_html)
        self.assertNotIn("BANNERNEEDLE", res.reader_html)
        self.assertNotIn("FOOTERNEEDLE", res.reader_html)

    def test_no_reader_returns_none(self):
        """TC-04-03: --no-reader → reader_html is None; whole still produced."""
        res = clean(_acq(_SPA_HTML), reader=False)
        self.assertIsNone(res.reader_html)
        self.assertTrue(res.whole_html.strip())

    def test_reader_degrade_keeps_whole(self):
        """TC-04-04: landmark-free page → whole_html is always a non-empty fallback."""
        bare = "<html><body><div>just some bare div soup with a little text</div></body></html>"
        res = clean(_acq(bare), reader=True)
        self.assertTrue(res.whole_html.strip())  # fallback always present


_TMP = Path("/Users/sergey/dev-projects/Universal-skills/tmp")
_REAL_SPA = _TMP / "elma365_activities_example.webarchive"


@unittest.skipUnless(_REAL_SPA.exists(), "real tmp/ SPA fixture not present")
class TestCleanRealFixture(unittest.TestCase):
    def test_real_spa_reader_shrinks(self):
        """TC-04-05: real SPA webarchive → reader extraction yields non-empty,
        smaller HTML than the whole page (chrome removed)."""
        args = build_parser().parse_args(["x", "--stdout"])
        acq = acquire_mod.acquire(str(_REAL_SPA), args)
        res = clean(acq, reader=True)
        self.assertTrue(res.whole_html.strip())
        self.assertIsNotNone(res.reader_html)
        self.assertTrue(res.reader_html.strip())
        self.assertLess(len(res.reader_html), len(res.whole_html))


if __name__ == "__main__":
    unittest.main()

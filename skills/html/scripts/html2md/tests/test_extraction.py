"""TASK 023 bead 023-05 — smarter extraction (X-Target-Selector + --remote-format markdown).

Offline via the _http_get_bytes seam + _host_is_public patch. cli-level tests use a temp
OUTPUT_DIR; the markdown trust path needs no Node (it bypasses turndown).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import acquire, cli  # noqa: E402
from html2md.exceptions import EngineNotInstalled, FetchFailed  # noqa: E402

TARGET = "https://x.com/a"
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_MD = ("Title: Hello World\n\nURL Source: https://x.com/a\n\nMarkdown Content:\n"
       "# Hello World\n\nA substantial markdown body with enough characters here.\n")
_ENV = ("HTML_READER_URL", "HTML_READER_PROVIDERS", "HTML_READER_TOKEN", "JINA_API_KEY")


def _opts(**over):
    args = cli.build_parser().parse_args([TARGET])
    for k, v in over.items():
        setattr(args, k, v)
    return args


class _Base(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(acquire, k) for k in
                       ("_http_get_bytes", "_fetch_chrome_html", "_host_is_public")}
        self._env = {k: os.environ.pop(k, None) for k in _ENV}
        acquire._host_is_public = lambda h: not h.startswith("10.")  # 10.* = internal
        acquire._fetch_chrome_html = lambda u, opts=None: (_ for _ in ()).throw(EngineNotInstalled("x"))

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(acquire, k, v)
        for k, v in self._env.items():
            (os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None))

    def _route(self, fn):
        acquire._http_get_bytes = lambda url, **kw: fn(url, **kw)


class TestTargetSelector(unittest.TestCase):
    def test_target_selector_header_sent(self):
        """TC-05-01: X-Target-Selector default + --target-selector override."""
        jina = acquire._RemoteReader("jina", acquire._JINA_READER_PREFIX, None)
        _, h = acquire._build_reader_request(jina, TARGET, _opts())
        self.assertEqual(h["X-Target-Selector"], "article, main, [role=main]")
        _, h2 = acquire._build_reader_request(jina, TARGET, _opts(target_selector=".content"))
        self.assertEqual(h2["X-Target-Selector"], ".content")


class TestTrustMarkdown(_Base):
    def test_remote_format_markdown_acquire(self):
        """TC-05-02: --remote-format markdown → content_kind markdown, body after preamble."""
        self._route(lambda url, **kw: _MD.encode() if "r.jina.ai" in url else b"")
        res = acquire.acquire(TARGET, _opts(engine="jina", remote_format="markdown"))
        self.assertEqual(res.content_kind, "markdown")
        self.assertEqual(res.engine, "jina")
        self.assertTrue(res.markdown.lstrip().startswith("# Hello World"))
        self.assertEqual(res.html, "")
        self.assertEqual(res.source_meta.title, "Hello World")

    def test_markdown_ask_but_reader_returns_html_falls_back(self):
        """TC-05-07: reader ignores the markdown ask and returns HTML → normal pipeline
        (content_kind html), not raw HTML emitted as 'markdown'."""
        good = b"<!doctype html><html><body><p>a substantial real article body here</p></body></html>"
        self._route(lambda url, **kw: good if "r.jina.ai" in url else b"")
        res = acquire.acquire(TARGET, _opts(engine="jina", remote_format="markdown"))
        self.assertEqual(res.content_kind, "html")

    def test_markdown_ask_html_no_doctype_falls_back(self):
        """L-2: reader returns HTML with NO doctype (leading <div>/<article>) → still
        detected as HTML → normal pipeline (not raw HTML emitted as markdown)."""
        for lead in (b"<div class='x'><p>body text here that is long</p></div>",
                     b"<article><h1>T</h1><p>body text here that is long enough</p></article>",
                     b"<!-- c --><body><p>a substantial real article body here</p></body>"):
            self._route(lambda url, _l=lead, **kw: _l if "r.jina.ai" in url else b"")
            res = acquire.acquire(TARGET, _opts(engine="jina", remote_format="markdown"))
            self.assertEqual(res.content_kind, "html", lead)

    def test_default_html_unchanged(self):
        """TC-05-05: default remote-format html → content_kind html (pipeline unchanged)."""
        good = b"<html><body><p>a substantial real article body here</p></body></html>"
        self._route(lambda url, **kw: good if "r.jina.ai" in url else b"")
        res = acquire.acquire(TARGET, _opts(engine="jina"))
        self.assertEqual(res.content_kind, "html")
        self.assertNotEqual(res.html, "")

    def test_trust_markdown_no_reader_variant_and_emit(self):
        """TC-05-03: trust-markdown writes exactly one <slug>.md (no .reader.md)."""
        self._route(lambda url, **kw: _MD.encode() if "r.jina.ai" in url else b"")
        with tempfile.TemporaryDirectory() as d:
            rc = cli.main([TARGET, d, "--engine", "jina", "--remote-format", "markdown"])
            self.assertEqual(rc, 0)
            mds = sorted(p.name for p in Path(d).glob("*.md"))
            self.assertEqual(len(mds), 1, mds)
            self.assertFalse(any(p.name.endswith(".reader.md") for p in Path(d).glob("*.md")))
            body = next(Path(d).glob("*.md")).read_text()
            self.assertIn("# Hello World", body)
            self.assertIn('source: "https://x.com/a"', body)

    def test_trust_markdown_images_localized(self):
        """TC-05-04: an http image in the reader Markdown is localized to _attachments/."""
        md = ("Markdown Content:\n# T\n\n![pic](https://img.example/p.png)\n\nbody text here.\n")

        def router(url, **kw):
            if "r.jina.ai" in url:
                return md.encode()
            if "img.example" in url:
                return _PNG
            raise AssertionError(url)
        self._route(router)
        with tempfile.TemporaryDirectory() as d:
            rc = cli.main([TARGET, d, "--engine", "jina", "--remote-format", "markdown"])
            self.assertEqual(rc, 0)
            body = next(Path(d).glob("*.md")).read_text()
            self.assertIn("_attachments/", body)
            self.assertTrue(list((Path(d) / "_attachments").glob("*.png")))

    def test_internal_image_url_in_markdown_dropped(self):
        """TC-05-06: an internal-IP image URL is NOT fetched (gate) → link left, not fatal."""
        md = ("Markdown Content:\n# T\n\n![x](https://10.0.0.5/secret.png)\n\nbody text here.\n")

        def router(url, **kw):
            if "r.jina.ai" in url:
                return md.encode()
            if "10.0.0.5" in url:  # the real gate refuses; simulate it on the seam
                raise FetchFailed("refused", details={"url": "x", "kind": "refused"})
            raise AssertionError(url)
        self._route(router)
        with tempfile.TemporaryDirectory() as d:
            rc = cli.main([TARGET, d, "--engine", "jina", "--remote-format", "markdown"])
            self.assertEqual(rc, 0)
            body = next(Path(d).glob("*.md")).read_text()
            self.assertIn("https://10.0.0.5/secret.png", body)  # left as-is (dropped, not localized)
            self.assertFalse((Path(d) / "_attachments").exists())


if __name__ == "__main__":
    unittest.main()

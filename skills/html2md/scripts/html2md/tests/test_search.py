"""TASK 023 bead 023-06 — web search (--search vendor-agnostic + per-result FETCH ladder).

Offline via the _http_get_bytes seam: the search provider returns JSON result URLs; each
result URL is then fetched through the real ladder (also on the seam). No network.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import acquire, cli  # noqa: E402
from html2md.exceptions import EngineNotInstalled, FetchFailed  # noqa: E402
from html2md.model import SourceMeta  # noqa: E402

GOOD = b"<html><head><title>R</title></head><body><p>a substantial result body here</p></body></html>"
_ENV = ("HTML2MD_SEARCH_URL", "HTML2MD_SEARCH_PROVIDERS", "HTML2MD_READER_URL",
        "HTML2MD_READER_PROVIDERS", "HTML2MD_READER_TOKEN", "JINA_API_KEY")


def _opts(**over):
    args = cli.build_parser().parse_args(["--search", "q"])
    for k, v in over.items():
        setattr(args, k, v)
    return args


def _json_urls(*urls):
    return json.dumps({"data": [{"url": u} for u in urls]}).encode()


class _Base(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(acquire, k) for k in
                       ("_http_get_bytes", "_fetch_chrome_html", "_looks_substantial",
                        "_trafilatura_meta", "_host_is_public", "_RATE_LIMITER")}
        self._env = {k: os.environ.pop(k, None) for k in _ENV}
        acquire._looks_substantial = lambda h: True
        acquire._trafilatura_meta = lambda h, u: SourceMeta(url=u)
        acquire._host_is_public = lambda h: True
        acquire._fetch_chrome_html = lambda u: (_ for _ in ()).throw(EngineNotInstalled("x"))
        acquire._RATE_LIMITER = None
        self.requested: list[str] = []

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(acquire, k, v)
        for k, v in self._env.items():
            (os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None))

    def _route(self, fn):
        def fake(url, **kw):
            self.requested.append(url)
            return fn(url, **kw)
        acquire._http_get_bytes = fake


class TestSearch(_Base):
    def test_search_provider_order(self):
        """TC-06-01: default [s.jina.ai]; HTML2MD_SEARCH_URL prepends a provider."""
        self.assertEqual([p.name for p in acquire._search_providers(_opts())], ["s.jina.ai"])
        os.environ["HTML2MD_SEARCH_URL"] = "https://srch.internal/"
        names = [p.name for p in acquire._search_providers(_opts())]
        self.assertEqual(names, ["search:srch.internal", "s.jina.ai"])

    def test_search_links_routes_each_through_ladder(self):
        """TC-06-02: links provider URLs are each fetched via the FETCH ladder."""
        def router(url, **kw):
            if "s.jina.ai" in url:
                return _json_urls("https://a.com/1", "https://b.com/2", "https://c.com/3")
            return GOOD
        self._route(router)
        results = acquire.run_search("q", _opts())
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.engine == "lite" for r in results))
        self.assertEqual({r.source_meta.url for r in results},
                         {"https://a.com/1", "https://b.com/2", "https://c.com/3"})

    def test_search_per_result_skip_on_fail(self):
        """TC-06-03: a result whose ladder fails is skipped, not fatal."""
        def router(url, **kw):
            if "s.jina.ai" in url:
                return _json_urls("https://a.com/1", "https://b.com/2", "https://c.com/3")
            if "b.com" in url:
                raise FetchFailed("gone", details={"url": "x", "kind": "not_found", "status": 404})
            return GOOD
        self._route(router)
        results = acquire.run_search("q", _opts())
        self.assertEqual(len(results), 2)

    def test_search_provider_fallback(self):
        """TC-06-04: primary search provider down (503) → secondary used."""
        os.environ["HTML2MD_SEARCH_PROVIDERS"] = "https://s1/ https://s2/"

        def router(url, **kw):
            if "://s1/" in url:
                raise FetchFailed("down", details={"url": "x", "kind": "server_error", "status": 503})
            if "://s2/" in url:
                return _json_urls("https://a.com/1")
            return GOOD
        self._route(router)
        results = acquire.run_search("q", _opts())
        self.assertEqual(len(results), 1)

    def test_search_all_fail_one_error(self):
        """TC-06-05: all search providers down → one FetchFailed(all_engines_failed)."""
        self._route(lambda url, **kw: (_ for _ in ()).throw(
            FetchFailed("down", details={"url": "x", "kind": "server_error", "status": 503})))
        with self.assertRaises(FetchFailed) as cm:
            acquire.run_search("q", _opts())
        self.assertEqual(cm.exception.details["kind"], "all_engines_failed")

    def test_search_max_results_bound(self):
        """TC-06-06: --max-results bounds the number of results fetched."""
        many = [f"https://x{i}.com/p" for i in range(10)]

        def router(url, **kw):
            return _json_urls(*many) if "s.jina.ai" in url else GOOD
        self._route(router)
        results = acquire.run_search("q", _opts(max_results=3))
        self.assertEqual(len(results), 3)

    def test_search_empty_results_exit0(self):
        """TC-06-08: a healthy search with zero results → [] (exit 0, no error)."""
        self._route(lambda url, **kw: b'{"data": []}' if "s.jina.ai" in url else GOOD)
        self.assertEqual(acquire.run_search("q", _opts()), [])

    def test_search_respects_rate_limit(self):
        """TC-06-09: --rate-limit configures the limiter on the search path."""
        self._route(lambda url, **kw: _json_urls("https://a.com/1") if "s.jina.ai" in url else GOOD)
        acquire.run_search("q", _opts(rate_limit=2.0))
        self.assertIsNotNone(acquire._RATE_LIMITER)

    def test_search_results_skip_chrome_in_auto(self):
        """S-1: in auto, an (attacker-influenceable) search-result URL never escalates to the
        un-network-hardened chrome tier; a thin result falls to remote instead."""
        acquire._looks_substantial = lambda h: False  # lite body is a JS shell → would escalate
        called = {"chrome": False}

        def chrome_spy(u):
            called["chrome"] = True
            raise EngineNotInstalled("x")
        acquire._fetch_chrome_html = chrome_spy

        def router(url, **kw):
            return _json_urls("https://a.com/1") if "s.jina.ai" in url else GOOD
        self._route(router)
        results = acquire.run_search("q", _opts())  # engine=auto
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].engine, "jina")  # recovered via remote, not chrome
        self.assertFalse(called["chrome"], "chrome must not run for a search result in auto")

    def test_search_query_crlf_refused(self):
        """A CR/LF in the query is refused before any request."""
        self._route(lambda url, **kw: GOOD)
        with self.assertRaises(FetchFailed) as cm:
            acquire.run_search("q\r\nHost: evil", _opts())
        self.assertEqual(cm.exception.details["kind"], "refused")
        self.assertEqual(self.requested, [])

    def test_e2e_search_emits_notes_with_query(self):
        """TC-E2E-06: cli --search writes one note per result with query+source frontmatter."""
        if not shutil.which("node"):
            self.skipTest("node not installed")

        def router(url, **kw):
            if "s.jina.ai" in url:
                return _json_urls("https://a.com/1", "https://b.com/2")
            return GOOD
        self._route(router)
        with tempfile.TemporaryDirectory() as d:
            rc = cli.main(["--search", "q", d, "--max-results", "2", "--no-download-images"])
            self.assertEqual(rc, 0)
            mds = list(Path(d).glob("*.md"))
            self.assertEqual(len(mds), 2, [p.name for p in mds])
            for p in mds:
                self.assertIn('query: "q"', p.read_text())


class TestSearchResultUrls(unittest.TestCase):
    """P-3 / L-4: result-URL extraction is bounded + deduped."""

    def test_json_bounded_and_deduped(self):
        body = json.dumps({"data": [{"url": f"https://x{i}.com"} for i in range(10)]
                           + [{"url": "https://x0.com"}]}).encode()
        out = acquire._search_result_urls(body, 3)
        self.assertEqual(len(out), 3)
        self.assertEqual(len(set(out)), 3)  # unique

    def test_regex_fallback_bounded_and_deduped(self):
        body = (b"see https://a.com and https://a.com then https://b.com "
                b"https://c.com https://d.com https://e.com")
        out = acquire._search_result_urls(body, 2)
        self.assertEqual(out, ["https://a.com", "https://b.com"])

    def test_non_http_items_ignored(self):
        body = json.dumps({"data": [{"url": "ftp://x"}, {"title": "no url"},
                                    {"url": "https://ok.com"}]}).encode()
        self.assertEqual(acquire._search_result_urls(body, 5), ["https://ok.com"])


if __name__ == "__main__":
    unittest.main()

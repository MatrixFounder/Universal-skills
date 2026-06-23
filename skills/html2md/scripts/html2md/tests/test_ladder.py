"""TASK 023 bead 023-03 — fallback-ladder orchestrator (tdd-strict).

Drives the ladder offline through the ``acquire._http_get_bytes`` seam (a per-URL router)
plus monkeypatched ``_fetch_chrome_html`` / ``_looks_substantial`` / ``_trafilatura_meta``.
No real network. Run from ``skills/html2md/scripts``.
"""
from __future__ import annotations

import os
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import acquire  # noqa: E402
from html2md.cli import build_parser  # noqa: E402
from html2md.exceptions import EngineNotInstalled, FetchFailed  # noqa: E402
from html2md.model import SourceMeta  # noqa: E402

_ENV_KEYS = ("HTML2MD_READER_URL", "HTML2MD_READER_PROVIDERS", "HTML2MD_READER_TOKEN",
             "JINA_API_KEY")
TARGET = "https://example.com/a"
GOOD = b"<html><head><title>T</title></head><body><p>real article body</p></body></html>"


def _opts(**over):
    args = build_parser().parse_args([TARGET])
    for k, v in over.items():
        setattr(args, k, v)
    return args


def _ff(kind, status=None):
    d = {"url": "redacted", "kind": kind}
    if status is not None:
        d["status"] = status
    return FetchFailed(f"{kind}", details=d)


class _Ladder(unittest.TestCase):
    """Saves/restores the network seam + chrome/heuristic patches + env."""

    def setUp(self):
        self._saved = {
            "_http_get_bytes": acquire._http_get_bytes,
            "_fetch_chrome_html": acquire._fetch_chrome_html,
            "_looks_substantial": acquire._looks_substantial,
            "_trafilatura_meta": acquire._trafilatura_meta,
            "_host_is_public": acquire._host_is_public,
        }
        self._env = {k: os.environ.pop(k, None) for k in _ENV_KEYS}
        # deterministic + HERMETIC: extraction is "substantial", metadata trivial (no trafilatura),
        # and _host_is_public is stubbed so the remote tier makes NO real DNS lookup for the
        # test targets (no external network in unit tests).
        acquire._looks_substantial = lambda h: True
        acquire._trafilatura_meta = lambda h, u: SourceMeta(url=u)
        acquire._host_is_public = lambda h: True
        self.requested: list[str] = []

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(acquire, k, v)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _route(self, fn):
        """Install a fake _http_get_bytes that records requested URLs and delegates to fn."""
        def fake(url, **kw):
            self.requested.append(url)
            return fn(url, **kw)
        acquire._http_get_bytes = fake

    def _chrome(self, action):
        def fake(url, opts=None):
            if isinstance(action, Exception):
                raise action
            return action
        acquire._fetch_chrome_html = fake


class TestLadder(_Ladder):
    def test_auto_lite_success(self):
        """TC-03-01: auto, lite substantial → engine 'lite'; remote never contacted."""
        self._route(lambda url, **kw: GOOD)  # any url returns good (only lite should run)
        res = acquire.acquire(TARGET, _opts(engine="auto"))
        self.assertEqual(res.engine, "lite")
        self.assertTrue(all("r.jina.ai" not in u for u in self.requested))

    def test_auto_403_escalates_to_remote(self):
        """TC-03-02: auto lite 403 → chrome absent → remote recovers (engine 'jina')."""
        self._chrome(EngineNotInstalled("no chrome"))

        def router(url, **kw):
            if "r.jina.ai" in url:
                return GOOD
            raise _ff("bot_blocked", 403)
        self._route(router)
        res = acquire.acquire(TARGET, _opts(engine="auto"))
        self.assertEqual(res.engine, "jina")

    def test_jina_outage_falls_back_to_lite(self):
        """TC-03-03: --engine jina, reader 503 → falls back to local lite (engine 'lite')."""
        def router(url, **kw):
            if "r.jina.ai" in url:
                raise _ff("server_error", 503)
            return GOOD
        self._route(router)
        res = acquire.acquire(TARGET, _opts(engine="jina"))
        self.assertEqual(res.engine, "lite")

    def test_all_tiers_fail_one_typed_error(self):
        """TC-03-04: every tier fails → exactly one FetchFailed(all_engines_failed) with a
        URL-free `tried` trace covering lite, chrome, remote."""
        self._chrome(EngineNotInstalled("no chrome"))

        def router(url, **kw):
            if "r.jina.ai" in url:
                raise _ff("server_error", 503)
            raise _ff("bot_blocked", 403)
        self._route(router)
        with self.assertRaises(FetchFailed) as cm:
            acquire.acquire(TARGET, _opts(engine="auto"))
        d = cm.exception.details
        self.assertEqual(d["kind"], "all_engines_failed")
        engines = [t["engine"] for t in d["tried"]]
        self.assertEqual(engines, ["lite", "chrome", "remote"])
        # privacy: no `tried` entry leaks a URL
        self.assertTrue(all("url" not in t for t in d["tried"]))

    def test_target_404_terminal_per_provider(self):
        """TC-03-05: a reader-reported target 404 does NOT try the next remote PROVIDER; the
        ladder ends terminal once lite also 404s. kind == not_found."""
        os.environ["HTML2MD_READER_PROVIDERS"] = "https://a/ https://b/"
        self._chrome(EngineNotInstalled("no chrome"))

        def router(url, **kw):
            return_404 = _ff("not_found", 404)
            raise return_404  # every hop (provider a, then lite) reports the target 404
        self._route(router)
        with self.assertRaises(FetchFailed) as cm:
            acquire.acquire(TARGET, _opts(engine="remote"))
        self.assertEqual(cm.exception.details["kind"], "not_found")
        # provider b must NOT have been contacted after a's target-block
        self.assertTrue(all("://b/" not in u for u in self.requested),
                        f"provider b was contacted: {self.requested}")

    def test_auto_engine_not_installed_falls_through(self):
        """TC-03-06: auto, lite thin + chrome absent → EngineNotInstalled is NOT fatal; remote
        recovers."""
        acquire._looks_substantial = lambda h: False  # lite body is a JS shell
        self._chrome(EngineNotInstalled("no chrome"))

        def router(url, **kw):
            if "r.jina.ai" in url:
                return GOOD
            return GOOD  # lite returns html but it's "thin" → escalate
        self._route(router)
        res = acquire.acquire(TARGET, _opts(engine="auto"))
        self.assertEqual(res.engine, "jina")

    def test_explicit_chrome_absent_exit3(self):
        """TC-03-07: explicit --engine chrome with no Playwright → EngineNotInstalled (exit 3),
        terminal (not a fall-through)."""
        self._chrome(EngineNotInstalled("no chrome"))
        self._route(lambda url, **kw: GOOD)
        with self.assertRaises(EngineNotInstalled):
            acquire.acquire(TARGET, _opts(engine="chrome"))

    def test_site_variant_preserved(self):
        """TC-03-08: arXiv /abs/ is still rewritten to /html/ in the lite tier."""
        arxiv = "https://arxiv.org/abs/2504.20838"
        self._route(lambda url, **kw: GOOD)
        res = acquire.acquire(arxiv, _opts(engine="auto"))
        self.assertEqual(res.engine, "lite+arxiv-html")
        self.assertTrue(any("/html/2504.20838" in u for u in self.requested))


if __name__ == "__main__":
    unittest.main()

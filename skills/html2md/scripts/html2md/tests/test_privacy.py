"""TASK 023 bead 023-04 — privacy / SSRF gate + injection guard (tdd-strict).

A private / internal target is NEVER forwarded to a remote reader; --no-remote disables
the tier; CR/LF in a target is refused. Offline via the seam + _host_is_public patch.
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
GOOD = b"<html><head><title>T</title></head><body><p>a real substantial body here</p></body></html>"


def _opts(target="https://x.com", **over):
    args = build_parser().parse_args([target])
    for k, v in over.items():
        setattr(args, k, v)
    return args


class _Base(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(acquire, k) for k in
                       ("_http_get_bytes", "_fetch_chrome_html", "_looks_substantial",
                        "_trafilatura_meta", "_host_is_public")}
        self._env = {k: os.environ.pop(k, None) for k in _ENV_KEYS}
        acquire._looks_substantial = lambda h: True
        acquire._trafilatura_meta = lambda h, u: SourceMeta(url=u)
        acquire._fetch_chrome_html = self._chrome_absent
        self.requested: list[str] = []

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(acquire, k, v)
        for k, v in self._env.items():
            (os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None))

    @staticmethod
    def _chrome_absent(url):
        raise EngineNotInstalled("no chrome")

    def _route(self, fn):
        def fake(url, **kw):
            self.requested.append(url)
            return fn(url, **kw)
        acquire._http_get_bytes = fake

    def _hit_jina(self):
        return any("r.jina.ai" in u for u in self.requested)


class TestPrivacyGate(_Base):
    def test_private_target_not_sent_remote(self):
        """TC-04-01: a private-resolving target is NEVER sent to the remote reader."""
        acquire._host_is_public = lambda h: h != "internal.example"
        self._route(lambda url, **kw: (_ for _ in ()).throw(
            FetchFailed("refused", details={"url": "x", "kind": "refused"})))
        with self.assertRaises(FetchFailed):
            acquire.acquire("https://internal.example/x", _opts("https://internal.example/x",
                                                                engine="jina"))
        self.assertFalse(self._hit_jina(), f"leaked to reader: {self.requested}")

    def test_no_remote_disables_tier(self):
        """TC-04-02: --no-remote → remote tier is 'disabled' in the trace, never contacted."""
        acquire._host_is_public = lambda h: True
        self._route(lambda url, **kw: (_ for _ in ()).throw(
            FetchFailed("blocked", details={"url": "x", "kind": "bot_blocked", "status": 403})))
        with self.assertRaises(FetchFailed) as cm:
            acquire.acquire("https://x.com/a", _opts("https://x.com/a",
                                                     engine="auto", no_remote=True))
        kinds = {t["engine"]: t["kind"] for t in cm.exception.details["tried"]}
        self.assertEqual(kinds.get("remote"), "disabled")
        self.assertFalse(self._hit_jina())

    def test_no_remote_engine_jina_is_local_only(self):
        """TC-04-03: --engine jina --no-remote → local-only; reader never contacted."""
        acquire._host_is_public = lambda h: True
        self._route(lambda url, **kw: GOOD)  # lite succeeds
        res = acquire.acquire("https://x.com/a", _opts("https://x.com/a",
                                                       engine="jina", no_remote=True))
        self.assertEqual(res.engine, "lite")
        self.assertFalse(self._hit_jina())

    def test_crlf_target_refused(self):
        """TC-04-04: a CR/LF in the target is refused before any request is made."""
        acquire._host_is_public = lambda h: True
        self._route(lambda url, **kw: GOOD)
        with self.assertRaises(FetchFailed) as cm:
            acquire.acquire("https://x.com/a\r\nHost: evil",
                            _opts("https://x.com/a", engine="jina"))
        self.assertEqual(cm.exception.details["kind"], "refused")
        self.assertEqual(self.requested, [])  # nothing was sent anywhere

    def test_public_target_allowed(self):
        """TC-04-05: a normal public target is NOT falsely blocked (no over-refusal)."""
        acquire._host_is_public = lambda h: True
        self._route(lambda url, **kw: GOOD)
        res = acquire.acquire("https://x.com/a", _opts("https://x.com/a", engine="auto"))
        self.assertEqual(res.engine, "lite")


if __name__ == "__main__":
    unittest.main()

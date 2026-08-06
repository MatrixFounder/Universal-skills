"""Egress proxy posture — `trust_env=False` by default + explicit `$HTML_PROXY` opt-in.

WHY THIS EXISTS. `_pin_host_addrs` overrides `socket.getaddrinfo` so httpx connects to the
EXACT address `_resolve_validated_addrs` validated — that is the anti-DNS-rebinding guarantee
the skill advertises. But `httpx.Client` honours `trust_env` by default, which silently mounts
`HTTP_PROXY`/`HTTPS_PROXY` **and**, on macOS, the System Configuration proxy — invisible to
`env | grep -i proxy`. When proxied, httpx connects to the PROXY and the proxy resolves the
target, so the override never fires for the target host and the pin is **decorative**.

MEASURED, not argued (2026-08-06, before the fix): pinning `example.com` to a blackholed
`192.0.2.1` and requesting it returned **HTTP 200** with an ambient proxy — the pin was
ignored — and `ConnectTimeout` with `trust_env=False` — the pin was honoured. This machine had
no proxy env vars at all; `urllib.request.getproxies()` still returned
`{'http': 'http://127.0.0.1:1082', ...}` from System Configuration.

So the client is now built `trust_env=False` ALWAYS and proxying is an explicit, announced
opt-in. These tests pin the kwargs; the end-to-end property is verified live (see
`scripts/.AGENTS.md`) because it needs a real socket.

Run from ``skills/html/scripts``:  python3 -m pytest html2md/tests/test_proxy.py
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import acquire  # noqa: E402

_real_httpx = __import__("httpx")


class _KwargSpy:
    """Minimal httpx stand-in that records the Client kwargs and serves one 200."""

    HTTPStatusError = _real_httpx.HTTPStatusError
    TransportError = _real_httpx.TransportError
    RequestError = _real_httpx.RequestError
    ConnectError = _real_httpx.ConnectError
    TimeoutException = _real_httpx.TimeoutException

    def __init__(self):
        self.client_kwargs: list[dict] = []

    def Client(self, **kw):  # noqa: N802 — mimic httpx.Client
        self.client_kwargs.append(dict(kw))
        return _Client(self)


class _Client:
    def __init__(self, spy):
        self._spy = spy

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def stream(self, method, url):
        return _Resp()


class _Resp:
    is_redirect = False
    headers: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        yield b"ok"


class _ProxyBase(unittest.TestCase):
    def setUp(self):
        self._saved_env = os.environ.pop(acquire._PROXY_ENV, None)
        self._saved_warned = acquire._proxy_warned
        self._saved_httpx = sys.modules.get("httpx")
        self._saved_pub = acquire._host_is_public
        self._saved_pin = acquire._resolve_validated_addrs
        acquire._host_is_public = lambda h: True
        acquire._resolve_validated_addrs = lambda host: None
        self.spy = _KwargSpy()
        sys.modules["httpx"] = self.spy

    def tearDown(self):
        os.environ.pop(acquire._PROXY_ENV, None)
        if self._saved_env is not None:
            os.environ[acquire._PROXY_ENV] = self._saved_env
        acquire._proxy_warned = self._saved_warned
        if self._saved_httpx is not None:
            sys.modules["httpx"] = self._saved_httpx
        else:
            sys.modules.pop("httpx", None)
        acquire._host_is_public = self._saved_pub
        acquire._resolve_validated_addrs = self._saved_pin

    def _fetch(self):
        with contextlib.redirect_stderr(io.StringIO()) as buf:
            acquire._http_get_bytes("https://ok.example/x", max_bytes=None, retries=0)
        return self.spy.client_kwargs[-1], buf.getvalue()


class TestProxySetting(_ProxyBase):
    def test_unset_means_direct(self):
        acquire._proxy_warned = False
        self.assertIsNone(acquire._proxy_setting())

    def test_empty_and_whitespace_mean_direct(self):
        for value in ("", "   ", "\t"):
            with self.subTest(value=value):
                acquire._proxy_warned = False
                os.environ[acquire._PROXY_ENV] = value
                self.assertIsNone(acquire._proxy_setting())

    def test_set_value_is_returned_stripped(self):
        acquire._proxy_warned = False
        os.environ[acquire._PROXY_ENV] = "  http://127.0.0.1:1082  "
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(acquire._proxy_setting(), "http://127.0.0.1:1082")

    def test_warns_once_not_per_request(self):
        """A per-request warning on a search fan-out would be pure noise, and noise is how a
        real warning gets ignored."""
        acquire._proxy_warned = False
        os.environ[acquire._PROXY_ENV] = "http://127.0.0.1:1082"
        with contextlib.redirect_stderr(io.StringIO()) as buf:
            for _ in range(3):
                acquire._proxy_setting()
        self.assertEqual(buf.getvalue().count("HTML_PROXY is set"), 1)

    def test_the_warning_names_the_consequence_not_just_the_fact(self):
        acquire._proxy_warned = False
        os.environ[acquire._PROXY_ENV] = "http://127.0.0.1:1082"
        with contextlib.redirect_stderr(io.StringIO()) as buf:
            acquire._proxy_setting()
        self.assertIn("pin does NOT apply", buf.getvalue())


class TestClientIsBuiltWithoutAmbientEnv(_ProxyBase):
    def test_trust_env_is_always_false(self):
        """★ THE LOAD-BEARING ASSERTION. Without this the DNS pin is decorative — httpx
        connects to an ambient proxy and the proxy, not us, resolves the target."""
        acquire._proxy_warned = True
        kwargs, _ = self._fetch()
        self.assertIs(kwargs["trust_env"], False)

    def test_trust_env_stays_false_even_when_a_proxy_is_configured(self):
        """The opt-in must route through OUR var, never through the ambient environment —
        otherwise `HTML_PROXY=''` would still silently inherit the system proxy."""
        acquire._proxy_warned = True
        os.environ[acquire._PROXY_ENV] = "http://127.0.0.1:1082"
        kwargs, _ = self._fetch()
        self.assertIs(kwargs["trust_env"], False)
        self.assertEqual(kwargs["proxy"], "http://127.0.0.1:1082")

    def test_no_proxy_by_default(self):
        acquire._proxy_warned = True
        kwargs, _ = self._fetch()
        self.assertIsNone(kwargs["proxy"])

    def test_ambient_env_vars_are_ignored(self):
        """`HTTP_PROXY`/`HTTPS_PROXY` in the environment must have NO effect now."""
        acquire._proxy_warned = True
        saved = {k: os.environ.get(k) for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}
        os.environ.update({"HTTP_PROXY": "http://evil.invalid:9",
                           "HTTPS_PROXY": "http://evil.invalid:9",
                           "ALL_PROXY": "http://evil.invalid:9"})
        try:
            kwargs, _ = self._fetch()
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v
        self.assertIsNone(kwargs["proxy"], "ambient proxy env must not leak in")
        self.assertIs(kwargs["trust_env"], False)


class TestGuardCanFire(unittest.TestCase):
    def test_the_kwarg_assertion_is_not_vacuous(self):
        """Non-vacuity: prove the spy would SEE a wrong value, so the assertions above are
        real rather than passing on an absent key."""
        spy = _KwargSpy()
        spy.Client(trust_env=True, proxy="http://x")
        self.assertEqual(spy.client_kwargs[-1],
                         {"trust_env": True, "proxy": "http://x"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

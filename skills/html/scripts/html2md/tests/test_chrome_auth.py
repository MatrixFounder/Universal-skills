"""TASK 024 — authenticated-Chrome surface (024-01) + RED contract stubs (filled per bead).

Surface tests are GREEN now (CLI flags, login verb-intercept, auth⇒chrome, R10 graceful
degradation). Behavioural tests are RED (skipped) until their logic bead lands.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import _chrome_auth, _cookies, acquire, cli  # noqa: E402

_ENV = ("HTML_CHROME_STORAGE_STATE", "HTML_CHROME_COOKIES_FILE",
        "HTML_CHROME_USER_DATA_DIR", "HTML_CHROME_AUTH_MAP",
        "HTML_CHROME_SCROLL", "HTML_CHROME_SCROLL_PASSES")


def _args(*argv):
    return cli.build_parser().parse_args(list(argv))


class _CleanEnv(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in _ENV}

    def tearDown(self):
        for k, v in self._saved.items():
            (os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None))


class TestChromeAuthSurface(_CleanEnv):
    def test_flags_parse(self):
        a = _args("https://x.com", "out", "--chrome-storage-state", "s.json",
                  "--chrome-scroll", "--chrome-scroll-passes", "12")
        self.assertEqual(a.chrome_storage_state, "s.json")
        self.assertIs(a.chrome_scroll, True)
        self.assertEqual(a.chrome_scroll_passes, 12)
        d = _args("x.html")
        self.assertIsNone(d.chrome_storage_state)
        self.assertIs(d.chrome_scroll, False)
        self.assertEqual(d.chrome_scroll_passes, 8)

    def test_auth_sources_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as cm:
            _args("https://x.com", "--chrome-storage-state", "s.json",
                  "--chrome-cookies-file", "c.txt")
        self.assertEqual(cm.exception.code, 2)

    def test_auth_flag_forces_chrome_engine(self):
        """TC-01-02: a valid auth file sets the effective engine to chrome."""
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s.json"
            f.write_text("{}", encoding="utf-8")
            a = _args("https://x.com", "out", "--engine", "auto",
                      "--chrome-storage-state", str(f))
            cli._validate_usage(a)
            self.assertEqual(a.engine, "chrome")

    def test_scroll_budget_constant_frozen(self):
        self.assertEqual(acquire._CHROME_SCROLL_BUDGET_S, 60.0)

    def test_auth_cannot_combine_with_search(self):
        """L-1: --chrome-* + --search → exit 2 (a session must not fan out over search results)."""
        rc = cli.main(["--search", "q", "out", "--chrome-storage-state", "whatever.json"])
        self.assertEqual(rc, 2)

    def test_login_verb_intercepted(self):
        """The `login` verb routes to its own parser (not mis-parsed as INPUT='login')."""
        with self.assertRaises(SystemExit) as cm:
            cli.main(["login", "--help"])
        self.assertEqual(cm.exception.code, 0)


class TestR10GracefulDegradation(_CleanEnv):
    def test_no_auth_no_engine_override(self):
        """R10: with no auth flag/env, _validate_usage leaves the engine untouched (auto)."""
        a = _args("https://x.com", "out")
        cli._validate_usage(a)
        self.assertEqual(a.engine, "auto")
        self.assertIsNone(a.chrome_storage_state)

    def test_missing_auth_file_typed_error(self):
        """R10: a --chrome-* file that does not exist → exit 1 BadInput (not a traceback)."""
        buf = io.StringIO()
        with redirect_stderr(buf):
            rc = cli.main(["https://x.com", "out", "--chrome-storage-state",
                           "/no/such/file.json", "--json-errors"])
        self.assertEqual(rc, 1)
        self.assertIn('"type": "BadInput"', buf.getvalue())

    # (the 024-01 `login` stub-graceful test was removed once 024-04 made `login` real —
    #  TestLoginMint covers the real mint with a fake browser; running the real one is a
    #  headful/network side effect tests must not trigger.)


# (TestScrollAndStale is defined at the bottom — it needs _ChromeBase, declared below.)


# --------------------------------------------------------------------------- #
# Fake Playwright (offline) — drives the chrome tier without a real browser.
# --------------------------------------------------------------------------- #
class _FakeRoute:
    def __init__(self):
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


class _FakeReq:
    def __init__(self, url):
        self.url = url


class _FakePage:
    def __init__(self, content, final_url):
        self._c, self._f, self.url, self.scrolls = content, final_url, None, 0

    def goto(self, url, **kw):
        self.url = self._f or url

    def content(self):
        return self._c

    def evaluate(self, *a, **k):  # 024-05 scroll seam
        self.scrolls += 1
        return 0

    def wait_for_load_state(self, *a, **k):
        return None


class _FakeContext:
    def __init__(self, page):
        self._page, self.routes, self.kwargs, self.added_cookies, self.closed = page, [], None, [], False
        self.init_scripts = []  # TASK 025: de-automation init scripts (navigator.webdriver mask)

    def add_init_script(self, script):
        self.init_scripts.append(script)

    def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    def new_page(self):
        return self._page

    def add_cookies(self, cookies):
        self.added_cookies.extend(cookies)

    def storage_state(self, path=None):  # 024-04 mint
        if path:
            Path(path).write_text('{"cookies": [], "origins": []}', encoding="utf-8")
        return {"cookies": [], "origins": []}

    def close(self):
        self.closed = True


class _FakeBrowser:
    def __init__(self, ctx):
        self._ctx = ctx

    def new_context(self, **kw):
        self._ctx.kwargs = kw
        return self._ctx

    def close(self):
        pass


class _FakeChromium:
    def __init__(self, ctx):
        self._ctx, self.persistent_kwargs = ctx, None

    def launch(self, **kw):
        return _FakeBrowser(self._ctx)

    def launch_persistent_context(self, **kw):  # 024-03 persistent-profile path
        self._ctx.kwargs = {"persistent": kw}
        return self._ctx


class _FakePW:
    def __init__(self, ctx):
        self.chromium = _FakeChromium(ctx)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_PRIVATE = {"127.0.0.1", "169.254.169.254", "10.0.0.5"}


class _ChromeBase(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(acquire, k) for k in ("_import_sync_playwright", "_host_is_public")}
        acquire._host_is_public = lambda h: h not in _PRIVATE and not h.startswith("10.")
        # Env isolation: a developer's exported HTML_CHROME_* (we instruct users to set these)
        # must NOT leak into _validate_usage's env fallbacks and perturb these tests.
        self._saved_env = {k: os.environ.pop(k, None) for k in _ENV}

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(acquire, k, v)
        for k, v in self._saved_env.items():
            (os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None))

    def _fake(self, *, content="<html><body><p>real authed body here ok</p></body></html>",
              final_url=None):
        ctx = _FakeContext(_FakePage(content, final_url))
        acquire._import_sync_playwright = lambda: (lambda: _FakePW(ctx))
        return ctx


class TestChromeSSRF(_ChromeBase):
    def test_private_target_refused_before_browser(self):
        """TC-02-01 (tdd-strict): a private TARGET is refused by the pre-goto gate (no browser)."""
        called = {"pw": False}
        acquire._import_sync_playwright = lambda: called.__setitem__("pw", True)
        with self.assertRaises(acquire.FetchFailed):
            acquire._fetch_chrome_html("https://127.0.0.1/x")
        self.assertFalse(called["pw"], "browser must not start for a private target")

    def test_private_redirect_subresource_aborted(self):
        """TC-02-02 (tdd-strict): the route guard aborts non-public hosts, allows public."""
        ctx = self._fake()
        acquire._fetch_chrome_html("https://example.com/x")  # public target, no redirect
        self.assertTrue(ctx.routes, "no route guard installed")
        handler = ctx.routes[0][1]
        r_priv = _FakeRoute(); handler(r_priv, _FakeReq("http://169.254.169.254/latest/meta-data/"))
        self.assertTrue(r_priv.aborted)
        r_pub = _FakeRoute(); handler(r_pub, _FakeReq("https://cdn.example.com/a.js"))
        self.assertTrue(r_pub.continued)

    def test_offtarget_public_redirect_refused(self):
        """TC-02-03 (tdd-strict): a public→public off-target redirect is refused before snapshot."""
        self._fake(final_url="https://evil-public.com/landing")
        with self.assertRaises(acquire.FetchFailed) as cm:
            acquire._fetch_chrome_html("https://example.com/article")
        self.assertEqual(cm.exception.details.get("kind"), "offsite_redirect")

    def test_same_site_www_redirect_allowed(self):
        """www.→apex (same eTLD+1) is NOT treated as off-target."""
        self._fake(final_url="https://www.example.com/article")
        html = acquire._fetch_chrome_html("https://example.com/article")
        self.assertIn("authed body", html)

    def test_public_render_ok_r10(self):
        """TC-02-04 (R10): a normal public render (no auth) returns content unchanged."""
        self._fake(content="<html><body><p>hello world body</p></body></html>")
        self.assertIn("hello world", acquire._fetch_chrome_html("https://example.com/p"))

    def test_playwright_absent_engine_not_installed(self):
        """Playwright missing → EngineNotInstalled (exit 3), after the public-target gate."""
        def _raise():
            raise acquire.EngineNotInstalled("no pw", details={"remediation": "install.sh --with-chrome"})
        acquire._import_sync_playwright = _raise
        with self.assertRaises(acquire.EngineNotInstalled):
            acquire._fetch_chrome_html("https://example.com/p")


class TestChromeAuthContext(_ChromeBase):
    """024-03: the authenticated context is built from the configured source + stays SSRF-gated."""

    def _opts(self, **kw):
        a = _args("https://example.com/x")
        for k, v in kw.items():
            setattr(a, k, v)
        return a

    def test_storage_state_context(self):
        """TC-03-01: --chrome-storage-state → new_context(storage_state=…)."""
        ctx = self._fake()
        acquire._fetch_chrome_html("https://example.com/x",
                                   self._opts(chrome_storage_state="state.json"))
        self.assertEqual(ctx.kwargs.get("storage_state"), "state.json")

    def test_persistent_profile_context(self):
        """TC-03-03: --chrome-user-data-dir → launch_persistent_context(user_data_dir=…, headless)."""
        ctx = self._fake()
        acquire._fetch_chrome_html("https://example.com/x",
                                   self._opts(chrome_user_data_dir="/prof"))
        self.assertIn("persistent", ctx.kwargs)
        self.assertEqual(ctx.kwargs["persistent"].get("user_data_dir"), "/prof")
        self.assertIs(ctx.kwargs["persistent"].get("headless"), True)

    def test_auth_context_still_ssrf_gated(self):
        """TC-03-04: SSRF guards apply to the AUTHENTICATED context too (private host aborted)."""
        ctx = self._fake()
        acquire._fetch_chrome_html("https://example.com/x",
                                   self._opts(chrome_storage_state="state.json"))
        handler = ctx.routes[0][1]
        r = _FakeRoute(); handler(r, _FakeReq("http://169.254.169.254/meta"))
        self.assertTrue(r.aborted)

    def test_no_auth_anonymous_context_r10(self):
        """R10: no auth source → plain context (no storage_state), render unchanged."""
        ctx = self._fake()
        acquire._fetch_chrome_html("https://example.com/x", self._opts())
        self.assertNotIn("storage_state", ctx.kwargs)
        self.assertNotIn("persistent", ctx.kwargs)

    def test_cookies_file_context(self):  # TC-03-02 (greened in 024-04)
        ctx = self._fake()
        with tempfile.TemporaryDirectory() as d:
            cf = Path(d) / "cookies.txt"
            cf.write_text("# Netscape HTTP Cookie File\n"
                          ".example.com\tTRUE\t/\tFALSE\t0\tsess\tabc123\n", encoding="utf-8")
            os.chmod(cf, 0o600)
            acquire._fetch_chrome_html("https://example.com/x",
                                       self._opts(chrome_cookies_file=str(cf)))
        self.assertTrue(ctx.added_cookies)
        self.assertEqual(ctx.added_cookies[0]["name"], "sess")


class TestCookieLoader(unittest.TestCase):
    """024-04 (tdd-strict): hardened cookies.txt loader + Playwright conversion."""

    def _write(self, d, mode=0o600,
               body="# Netscape HTTP Cookie File\n.x.com\tTRUE\t/\tFALSE\t0\tk\tv\n"):
        cf = Path(d) / "c.txt"
        cf.write_text(body, encoding="utf-8")
        os.chmod(cf, mode)
        return cf

    def test_rejects_group_world_perms(self):  # tdd-strict, write-first
        with tempfile.TemporaryDirectory() as d:
            for mode in (0o644, 0o640, 0o660):
                with self.assertRaises(acquire.BadInput):
                    _cookies.load_cookie_jar(self._write(d, mode))

    def test_accepts_0600_and_converts(self):
        with tempfile.TemporaryDirectory() as d:
            jar = _cookies.load_cookie_jar(self._write(d, 0o600))
            cookies = _cookies.to_playwright_cookies(jar)
            self.assertEqual(cookies[0]["name"], "k")
            self.assertEqual(cookies[0]["domain"], ".x.com")
            self.assertEqual(cookies[0]["path"], "/")

    def test_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            real = self._write(d, 0o600)
            link = Path(d) / "link.txt"
            link.symlink_to(real)
            with self.assertRaises(acquire.BadInput):
                _cookies.load_cookie_jar(link)

    def test_parse_error_is_sanitized(self):  # tdd-strict: no file-content leak
        with tempfile.TemporaryDirectory() as d:
            cf = self._write(d, 0o600, body="SECRETLINE this is not a cookie file\n")
            with self.assertRaises(acquire.BadInput) as cm:
                _cookies.load_cookie_jar(cf)
            self.assertNotIn("SECRETLINE", str(cm.exception))


class TestLoginMint(_ChromeBase):
    """024-04: `login` mints a 0600 storage_state via a headful browser."""

    def test_login_writes_0600_state(self):
        self._fake()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "x.json"
            with mock.patch("builtins.input", return_value=""):
                acquire._login_render("https://x.com", str(out), _args("https://x.com"))
            self.assertTrue(out.is_file())
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)

    def test_login_refuses_private_target(self):
        self._fake()
        with mock.patch("builtins.input", return_value=""):
            with self.assertRaises(acquire.FetchFailed):
                acquire._login_render("https://127.0.0.1/login", "x.json", _args("https://x"))

    def test_mint_prefers_chrome_channel_and_masks_webdriver(self):
        """TASK 025 R1/R2: the mint launch requests the real Chrome channel + de-automation arg,
        and the context masks navigator.webdriver."""
        ctx = _FakeContext(_FakePage('{"ok":1}', None))
        calls = []

        class _Rec(_FakeChromium):
            def launch(self, **kw):
                calls.append(kw)
                return _FakeBrowser(self._ctx)

        pw = _FakePW(ctx)
        pw.chromium = _Rec(ctx)
        acquire._import_sync_playwright = lambda: (lambda: pw)
        with tempfile.TemporaryDirectory() as d, mock.patch("builtins.input", return_value=""):
            acquire._login_render("https://x.com", str(Path(d) / "x.json"), _args("https://x.com"))
        self.assertEqual(calls[0].get("channel"), "chrome")
        self.assertIn("--disable-blink-features=AutomationControlled", calls[0].get("args", []))
        self.assertIn(acquire._WEBDRIVER_MASK_JS, ctx.init_scripts)


class TestChromeLaunchHardening(_ChromeBase):
    """TASK 025: real-Chrome-channel preference + de-automation on the headless render path."""

    def test_render_prefers_chrome_channel_and_masks_webdriver(self):
        """R1/R2: render launch requests channel='chrome' + the AutomationControlled arg, and
        the context masks navigator.webdriver."""
        ctx = _FakeContext(_FakePage("<html><body><p>real authed body ok</p></body></html>", None))
        calls = []

        class _Rec(_FakeChromium):
            def launch(self, **kw):
                calls.append(kw)
                return _FakeBrowser(self._ctx)

        pw = _FakePW(ctx)
        pw.chromium = _Rec(ctx)
        acquire._import_sync_playwright = lambda: (lambda: pw)
        acquire._fetch_chrome_html("https://example.com/x")
        self.assertEqual(calls[0].get("channel"), "chrome")
        self.assertIn("--disable-blink-features=AutomationControlled", calls[0].get("args", []))
        self.assertIn(acquire._WEBDRIVER_MASK_JS, ctx.init_scripts)

    def test_render_falls_back_to_bundled_when_channel_missing(self):
        """R1 (R10 parity): if the system Chrome channel is absent, launch falls back to bundled
        Chromium (still de-automated) — never a hard failure."""
        ctx = _FakeContext(_FakePage("<html><body><p>real authed body ok</p></body></html>", None))
        calls = []

        class _Flaky(_FakeChromium):
            def launch(self, **kw):
                calls.append(kw)
                if kw.get("channel"):
                    raise RuntimeError("Chromium distribution 'chrome' is not found")
                return _FakeBrowser(self._ctx)

        pw = _FakePW(ctx)
        pw.chromium = _Flaky(ctx)
        acquire._import_sync_playwright = lambda: (lambda: pw)
        html = acquire._fetch_chrome_html("https://example.com/x")  # must NOT raise
        self.assertIn("authed body", html)
        self.assertEqual(len(calls), 2)  # channel attempt, then bundled fallback
        self.assertEqual(calls[0].get("channel"), "chrome")
        self.assertIsNone(calls[1].get("channel"))
        self.assertIn("--disable-blink-features=AutomationControlled", calls[1].get("args", []))

    def test_persistent_falls_back_to_bundled_when_channel_missing(self):
        """R1 (persistent path): --chrome-user-data-dir also prefers channel='chrome', de-automates,
        and falls back to bundled Chromium (preserving user_data_dir) when system Chrome is absent."""
        ctx = _FakeContext(_FakePage("<html><body><p>real authed body ok</p></body></html>", None))
        calls = []

        class _FlakyP(_FakeChromium):
            def launch_persistent_context(self, **kw):
                calls.append(kw)
                if kw.get("channel"):
                    raise RuntimeError("Chromium distribution 'chrome' is not found")
                self._ctx.kwargs = {"persistent": kw}
                return self._ctx

        pw = _FakePW(ctx)
        pw.chromium = _FlakyP(ctx)
        acquire._import_sync_playwright = lambda: (lambda: pw)
        a = _args("https://example.com/x")
        a.chrome_user_data_dir = "/prof"
        html = acquire._fetch_chrome_html("https://example.com/x", a)  # must NOT raise
        self.assertIn("authed body", html)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].get("channel"), "chrome")
        self.assertIsNone(calls[1].get("channel"))
        self.assertEqual(calls[1].get("user_data_dir"), "/prof")
        self.assertIn("--disable-blink-features=AutomationControlled", calls[1].get("args", []))
        self.assertIn(acquire._WEBDRIVER_MASK_JS, ctx.init_scripts)


class TestScrollAndStale(_ChromeBase):
    """024-05: scroll-to-load (bounded, never hangs) + stale-session login-wall detection."""

    def _opts(self, **kw):
        a = _args("https://example.com/x")
        for k, v in kw.items():
            setattr(a, k, v)
        return a

    def test_scroll_bounded_by_passes(self):
        ctx = self._fake()
        acquire._fetch_chrome_html("https://example.com/x",
                                   self._opts(chrome_scroll=True, chrome_scroll_passes=3))
        self.assertEqual(ctx._page.scrolls, 3)

    def test_scroll_never_hangs_wallclock(self):
        """A never-settling page is bounded by the wall-clock budget, not the pass count."""
        ctx = self._fake()
        saved = acquire._monotonic
        ticks = iter([0.0] + [acquire._CHROME_SCROLL_BUDGET_S + 1] * 50)  # deadline=60, then expired
        acquire._monotonic = lambda: next(ticks)
        try:
            acquire._fetch_chrome_html("https://example.com/x",
                                       self._opts(chrome_scroll=True, chrome_scroll_passes=1000))
        finally:
            acquire._monotonic = saved
        self.assertEqual(ctx._page.scrolls, 0)  # budget exceeded before any scroll

    def test_stale_session_login_wall_auth_required(self):
        """R5c: a login wall (X 'Continue with Google/Apple' pair) → FetchFailed auth_required."""
        self._fake(content="<html><body>See what's happening. Continue with Google. "
                           "Continue with Apple.</body></html>")
        with self.assertRaises(acquire.FetchFailed) as cm:
            acquire._fetch_chrome_html("https://x.com/i/article/1", self._opts())
        self.assertEqual(cm.exception.details.get("kind"), "auth_required")

    def test_login_path_redirect_auth_required(self):
        self._fake(final_url="https://x.com/i/flow/login")
        with self.assertRaises(acquire.FetchFailed) as cm:
            acquire._fetch_chrome_html("https://x.com/i/article/1", self._opts())
        self.assertEqual(cm.exception.details.get("kind"), "auth_required")

    def test_real_authed_render_not_misclassified(self):
        """A genuine article render (no wall markers, on-target) is returned, not flagged."""
        self._fake(content="<html><body><article><p>full authed article body here</p>"
                           "</article></body></html>")
        html = acquire._fetch_chrome_html("https://x.com/i/article/1", self._opts())
        self.assertIn("full authed article", html)

    def test_is_login_wall_unit(self):
        self.assertTrue(_chrome_auth.is_login_wall("javascript is not available", "https://x.com/"))
        self.assertFalse(_chrome_auth.is_login_wall(
            "<article>a normal article that mentions sign in once</article>",
            "https://x.com/i/article/1"))

    def test_chrome_render_max_bytes(self):  # perf P-1: chrome body bounded by --max-bytes
        self._fake(content="<html><body>" + "x" * 5000 + "</body></html>")
        with self.assertRaises(acquire.FetchFailed) as cm:
            acquire._fetch_chrome_html("https://example.com/x", self._opts(max_bytes=100))
        self.assertEqual(cm.exception.details.get("kind"), "max_bytes")


class TestChromeAuthMap(_ChromeBase):
    """TASK 026: per-domain auth map — route the right credential by the target's eTLD+1, force
    chrome only for mapped domains, hardened map loader (0600 / symlink / JSON shape)."""

    @staticmethod
    def _write(d, name, text, mode=0o600):
        p = Path(d) / name
        p.write_text(text, encoding="utf-8")
        os.chmod(p, mode)
        return p

    def _cookies_txt(self, d, name="x-cookies.txt"):
        body = ("# Netscape HTTP Cookie File\n"
                ".x.com\tTRUE\t/\tTRUE\t9999999999\tauth_token\tSEKRET\n")
        return self._write(d, name, body)

    def _opts_map(self, url, amap):
        a = _args(url, "/tmp/out")
        a.chrome_auth_map = str(amap)
        return a

    def test_map_routes_cookies_by_domain(self):
        with tempfile.TemporaryDirectory() as d:
            cookies = self._cookies_txt(d)
            amap = self._write(d, "auth.json", json.dumps({"x.com": {"cookies_file": str(cookies)}}))
            ctx = self._fake()
            acquire._fetch_chrome_html("https://x.com/i/article/1",
                                       self._opts_map("https://x.com/i/article/1", amap))
            self.assertTrue(any(c["name"] == "auth_token" for c in ctx.added_cookies))

    def test_map_no_match_is_anonymous(self):
        """An unmapped target gets NO credential (small blast radius, R10)."""
        with tempfile.TemporaryDirectory() as d:
            cookies = self._cookies_txt(d)
            amap = self._write(d, "auth.json", json.dumps({"x.com": {"cookies_file": str(cookies)}}))
            ctx = self._fake()
            acquire._fetch_chrome_html("https://example.com/p",
                                       self._opts_map("https://example.com/p", amap))
            self.assertEqual(ctx.added_cookies, [])

    def test_map_matches_registrable_subdomain(self):
        with tempfile.TemporaryDirectory() as d:
            cookies = self._cookies_txt(d)
            amap = self._write(d, "auth.json", json.dumps({"x.com": {"cookies_file": str(cookies)}}))
            ctx = self._fake()
            acquire._fetch_chrome_html("https://mobile.x.com/i/article/1",
                                       self._opts_map("https://mobile.x.com/i/article/1", amap))
            self.assertTrue(ctx.added_cookies, "mobile.x.com should match the x.com key")

    def test_map_storage_state_entry(self):
        with tempfile.TemporaryDirectory() as d:
            ss = self._write(d, "m-state.json", '{"cookies":[],"origins":[]}')
            amap = self._write(d, "auth.json", json.dumps({"medium.com": {"storage_state": str(ss)}}))
            ctx = self._fake()
            acquire._fetch_chrome_html("https://medium.com/p",
                                       self._opts_map("https://medium.com/p", amap))
            self.assertEqual(ctx.kwargs.get("storage_state"), str(ss))

    def test_map_rejects_group_world_perms(self):
        with tempfile.TemporaryDirectory() as d:
            amap = self._write(d, "auth.json", json.dumps({"x.com": {"cookies_file": "x"}}), mode=0o644)
            with self.assertRaises(acquire.BadInput):
                _chrome_auth.load_auth_map(amap)

    def test_map_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            real = self._write(d, "real.json", json.dumps({"x.com": {"cookies_file": "x"}}))
            link = Path(d) / "link.json"
            link.symlink_to(real)
            with self.assertRaises(acquire.BadInput):
                _chrome_auth.load_auth_map(link)

    def test_map_rejects_bad_structure(self):
        with tempfile.TemporaryDirectory() as d:
            amap = self._write(d, "auth.json", json.dumps({"x.com": {"foo": "bar"}}))  # neither key
            with self.assertRaises(acquire.BadInput):
                _chrome_auth.load_auth_map(amap)

    def test_cli_map_forces_chrome_only_when_mapped(self):
        with tempfile.TemporaryDirectory() as d:
            cookies = self._cookies_txt(d)
            amap = self._write(d, "auth.json", json.dumps({"x.com": {"cookies_file": str(cookies)}}))
            hit = _args("https://x.com/i/article/1", d, "--chrome-auth-map", str(amap))
            cli._validate_usage(hit)
            self.assertEqual(hit.engine, "chrome")
            miss = _args("https://example.com/p", d, "--chrome-auth-map", str(amap))
            cli._validate_usage(miss)
            self.assertNotEqual(miss.engine, "chrome")  # unmapped target → normal ladder

    def test_cli_map_rejects_search_combo(self):
        with tempfile.TemporaryDirectory() as d:
            amap = self._write(d, "auth.json", json.dumps({"x.com": {"cookies_file": "x"}}))
            a = _args("--search", "q", d, "--chrome-auth-map", str(amap))
            with self.assertRaises(cli.Usage):
                cli._validate_usage(a)

    def test_cli_map_rejects_fixed_source_combo_via_env(self):
        """Env-level: a fixed source + map cannot coexist (argparse guards the flag-level case)."""
        with tempfile.TemporaryDirectory() as d:
            cookies = self._cookies_txt(d)
            amap = self._write(d, "auth.json", json.dumps({"x.com": {"cookies_file": str(cookies)}}))
            a = _args("https://x.com/p", d, "--chrome-auth-map", str(amap))
            a.chrome_cookies_file = str(cookies)  # simulate HTML_CHROME_COOKIES_FILE present
            with self.assertRaises(cli.Usage):
                cli._validate_usage(a)

    # ── vdd-multi-026 fixes: F-1 (storage_state hardening) / F-2 (suffix match) / dup+both keys ──

    def test_map_does_not_match_shared_apex_sibling(self):
        """F-2: a key for ONE tenant of a shared apex (s3/github.io/…) must NOT leak to a sibling."""
        with tempfile.TemporaryDirectory() as d:
            cookies = self._cookies_txt(d)
            amap = self._write(d, "auth.json",
                               json.dumps({"mybucket.s3.amazonaws.com": {"cookies_file": str(cookies)}}))
            ctx = self._fake()
            acquire._fetch_chrome_html("https://evil.s3.amazonaws.com/x",
                                       self._opts_map("https://evil.s3.amazonaws.com/x", amap))
            self.assertEqual(ctx.added_cookies, [], "credential leaked to a sibling tenant")

    def test_map_matches_own_subdomain_on_shared_apex(self):
        """Flip side of F-2: the keyed tenant and its subdomains DO match."""
        with tempfile.TemporaryDirectory() as d:
            cookies = self._cookies_txt(d)
            amap = self._write(d, "auth.json",
                               json.dumps({"mybucket.s3.amazonaws.com": {"cookies_file": str(cookies)}}))
            ctx = self._fake()
            acquire._fetch_chrome_html("https://cdn.mybucket.s3.amazonaws.com/x",
                                       self._opts_map("https://cdn.mybucket.s3.amazonaws.com/x", amap))
            self.assertTrue(ctx.added_cookies)

    def test_map_most_specific_key_wins(self):
        with tempfile.TemporaryDirectory() as d:
            broad = self._cookies_txt(d, "broad.txt")
            specific = self._cookies_txt(d, "specific.txt")
            amap = self._write(d, "auth.json", json.dumps(
                {"x.com": {"cookies_file": str(broad)},
                 "api.x.com": {"cookies_file": str(specific)}}))
            loaded = _chrome_auth.load_auth_map(amap)
            self.assertEqual(_chrome_auth._match_host("api.x.com", loaded)["cookies_file"], str(specific))
            self.assertEqual(_chrome_auth._match_host("www.x.com", loaded)["cookies_file"], str(broad))

    def test_map_rejects_entry_with_both_credentials(self):
        """F-1: an entry naming BOTH cookies_file and storage_state is rejected (no silent pick)."""
        with tempfile.TemporaryDirectory() as d:
            amap = self._write(d, "auth.json", json.dumps(
                {"x.com": {"cookies_file": "a.txt", "storage_state": "b.json"}}))
            with self.assertRaises(acquire.BadInput):
                _chrome_auth.load_auth_map(amap)

    def test_map_rejects_duplicate_host(self):
        """F-2: two keys that normalize identically are rejected (no silent last-wins)."""
        with tempfile.TemporaryDirectory() as d:
            amap = self._write(d, "auth.json", json.dumps(
                {"x.com": {"cookies_file": "a.txt"}, "X.com.": {"cookies_file": "b.txt"}}))
            with self.assertRaises(acquire.BadInput):
                _chrome_auth.load_auth_map(amap)

    def test_map_rejects_empty_host_key(self):
        """An empty/whitespace host key would be a silent dead entry → rejected."""
        with tempfile.TemporaryDirectory() as d:
            amap = self._write(d, "auth.json", json.dumps({"  ": {"cookies_file": "x"}}))
            with self.assertRaises(acquire.BadInput):
                _chrome_auth.load_auth_map(amap)

    def test_map_key_whitespace_tolerated(self):
        """Surrounding whitespace in a host key is stripped (no silent non-match)."""
        with tempfile.TemporaryDirectory() as d:
            cookies = self._cookies_txt(d)
            amap = self._write(d, "auth.json", json.dumps({"  x.com  ": {"cookies_file": str(cookies)}}))
            self.assertIn("x.com", _chrome_auth.load_auth_map(amap))

    def test_map_storage_state_rejects_bad_perms(self):
        """F-1: a group/world-readable storage_state referenced by the map is refused (parity)."""
        with tempfile.TemporaryDirectory() as d:
            ss = self._write(d, "m-state.json", '{"cookies":[],"origins":[]}', mode=0o644)
            amap = self._write(d, "auth.json", json.dumps({"medium.com": {"storage_state": str(ss)}}))
            with self.assertRaises(acquire.BadInput):
                acquire._fetch_chrome_html("https://medium.com/p",
                                           self._opts_map("https://medium.com/p", amap))

    def test_map_env_fallback_real(self):
        """The actual HTML_CHROME_AUTH_MAP env fallback forces chrome for a mapped target."""
        with tempfile.TemporaryDirectory() as d:
            cookies = self._cookies_txt(d)
            amap = self._write(d, "auth.json", json.dumps({"x.com": {"cookies_file": str(cookies)}}))
            a = _args("https://x.com/i/article/1", d)  # NO --chrome-auth-map flag
            with mock.patch.dict(os.environ, {"HTML_CHROME_AUTH_MAP": str(amap)}):
                cli._validate_usage(a)
            self.assertEqual(a.chrome_auth_map, str(amap))
            self.assertEqual(a.engine, "chrome")

    def test_map_local_file_input_is_noop(self):
        """A set-and-forget map must NOT force chrome for a LOCAL file input."""
        with tempfile.TemporaryDirectory() as d:
            cookies = self._cookies_txt(d)
            amap = self._write(d, "auth.json", json.dumps({"x.com": {"cookies_file": str(cookies)}}))
            a = _args("./page.html", d)
            with mock.patch.dict(os.environ, {"HTML_CHROME_AUTH_MAP": str(amap)}):
                cli._validate_usage(a)
            self.assertNotEqual(a.engine, "chrome")

    def test_auth_map_env_path_is_expanduser(self):
        """A `~`-path in HTML_CHROME_AUTH_MAP (e.g. from the auto-loaded .env) is expanded."""
        a = _args("https://x.com/p", "/tmp/out")
        with mock.patch.dict(os.environ, {"HTML_CHROME_AUTH_MAP": "~/nope/auth-map.json"}):
            # ~ must be expanded before the file check (else it'd fail on a literal '~' dir)
            try:
                cli._validate_usage(a)
            except acquire.BadInput:
                pass  # file legitimately absent — fine; we only assert the path was expanded
            self.assertFalse(a.chrome_auth_map.startswith("~"))
            self.assertTrue(a.chrome_auth_map.startswith(os.path.expanduser("~")))

    def test_chrome_scroll_env_fallback(self):
        """HTML_CHROME_SCROLL(+_PASSES) enables scroll for env-only callers (wiki-import)."""
        with tempfile.TemporaryDirectory() as d:
            a = _args("https://example.com/p", d)
            self.assertFalse(a.chrome_scroll)
            with mock.patch.dict(os.environ, {"HTML_CHROME_SCROLL": "1",
                                              "HTML_CHROME_SCROLL_PASSES": "12"}):
                cli._validate_usage(a)
            self.assertTrue(a.chrome_scroll)
            self.assertEqual(a.chrome_scroll_passes, 12)

    def test_chrome_scroll_flag_beats_env_default(self):
        """An explicit --chrome-scroll-passes is not overridden by the env (env fills only default)."""
        with tempfile.TemporaryDirectory() as d:
            a = _args("https://example.com/p", d, "--chrome-scroll-passes", "3")
            with mock.patch.dict(os.environ, {"HTML_CHROME_SCROLL_PASSES": "12"}):
                cli._validate_usage(a)
            self.assertEqual(a.chrome_scroll_passes, 3)


if __name__ == "__main__":
    unittest.main()

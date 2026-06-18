"""Bead 022-06 — FC-1 URL fetch (httpx+trafilatura lite, Chrome fallback, SSRF caps).

Network is fully mocked: the single seam ``acquire._http_get_bytes`` is patched (or a
fake ``httpx`` is injected). ``trafilatura`` runs for real on the in-memory fixture
(it makes no network call when given HTML directly). No real egress.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import acquire, cli  # noqa: E402
from html2md.exceptions import EngineNotInstalled, FetchFailed  # noqa: E402

_ARTICLE = (
    "<!doctype html><html><head>"
    '<meta property="og:title" content="The Real Title">'
    '<meta name="author" content="Jane Doe">'
    '<meta property="article:published_time" content="2026-06-17">'
    "<title>fallback</title></head><body><article><h1>The Real Title</h1>"
    "<p>" + ("This is a substantial article paragraph with plenty of words. " * 12)
    + "</p></article></body></html>"
)


def _opts(**over):
    args = cli.build_parser().parse_args(["x"])
    for k, v in over.items():
        setattr(args, k, v)
    return args


import httpx as _real_httpx  # real exception classes for the fake to re-export  # noqa: E402


class _CtxResp:
    """Wrap a real httpx.Response as a context manager (so `with client.stream():` works)."""

    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self._resp

    def __exit__(self, *a):
        return False


class _FakeClient:
    def __init__(self, fake):
        self._fake = fake

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def stream(self, method, url):  # noqa: D401 — mimic httpx.Client.stream
        self._fake.seen_urls.append(url)
        step = self._fake.next_step()
        if isinstance(step, BaseException):
            raise step
        status, content, headers = step
        resp = _real_httpx.Response(status, headers=headers or {}, content=content,
                                    request=_real_httpx.Request(method, url))
        return _CtxResp(resp)


class _FakeHttpx:
    """Drop-in httpx replacement. Re-exports the REAL exception classes (so the code's
    ``except httpx.HTTPStatusError`` / ``TransportError`` resolve to the same class the
    fake raises) and replays a scripted sequence of responses across retry attempts +
    redirect hops. Records the User-Agents / URLs / headers it was asked for."""

    HTTPStatusError = _real_httpx.HTTPStatusError
    TransportError = _real_httpx.TransportError
    RequestError = _real_httpx.RequestError
    ConnectError = _real_httpx.ConnectError
    TimeoutException = _real_httpx.TimeoutException

    def __init__(self, script):
        self._script = list(script)
        self._i = 0
        self.seen_uas: list = []
        self.seen_urls: list = []
        self.seen_headers: list = []

    def next_step(self):
        step = self._script[min(self._i, len(self._script) - 1)]
        self._i += 1
        return step

    def Client(self, **kw):  # noqa: N802 — mimic httpx.Client
        hdrs = kw.get("headers") or {}
        self.seen_headers.append(dict(hdrs))
        self.seen_uas.append(hdrs.get("User-Agent"))
        return _FakeClient(self)


def _script_from(content, exc, responses):
    if responses is not None:
        return responses
    if exc is not None:
        return [exc]
    return [(200, content if content is not None else b"", {})]


class _patch_httpx:
    """Inject a fake httpx + bypass the public-IP gate so the fetch logic is exercised.

    Modes: ``content=bytes`` (single 200) | ``exc=Exception`` (raised) |
    ``responses=[step,…]`` where each step is an Exception (raised) or a
    ``(status, content_bytes, headers)`` tuple, replayed across retry attempts + hops.
    """

    def __init__(self, *, public: bool = True, content=None, exc=None, responses=None):
        self._fake = _FakeHttpx(_script_from(content, exc, responses))
        self._public = public

    def __enter__(self):
        self._saved_httpx = sys.modules.get("httpx")
        sys.modules["httpx"] = self._fake
        self._saved_pub = acquire._host_is_public
        if self._public:
            acquire._host_is_public = lambda h: True
        return self

    def __exit__(self, *a):
        if self._saved_httpx is not None:
            sys.modules["httpx"] = self._saved_httpx
        else:
            sys.modules.pop("httpx", None)
        acquire._host_is_public = self._saved_pub
        return False


class _no_backoff:
    """Patch acquire._sleep to a no-op recorder (no real retry/backoff waiting)."""

    def __enter__(self):
        self.slept: list = []
        self._saved = acquire._sleep
        acquire._sleep = lambda d=0: self.slept.append(d)
        return self

    def __exit__(self, *a):
        acquire._sleep = self._saved
        return False


class TestLite(unittest.TestCase):
    def test_lite_fetch_and_metadata(self):
        """TC-06-01: lite fetch returns raw HTML + trafilatura metadata."""
        saved = acquire._http_get_bytes
        acquire._http_get_bytes = lambda url, **k: _ARTICLE.encode("utf-8")
        try:
            res = acquire.acquire("https://example.com/post", _opts(engine="lite"))
        finally:
            acquire._http_get_bytes = saved
        self.assertEqual(res.mode, "url")
        self.assertEqual(res.engine, "lite")
        self.assertIn("substantial article paragraph", res.html)
        self.assertEqual(res.source_meta.title, "The Real Title")
        self.assertEqual(res.source_meta.author, "Jane Doe")

    def test_auto_fallback_on_empty_body(self):
        """TC-06-02: auto + JS shell (thin) → Chrome path invoked."""
        saved_lite = acquire._fetch_lite_html
        saved_chrome = acquire._fetch_chrome_html
        acquire._fetch_lite_html = lambda url, mb, retries=2: "<html><body><div id='app'></div></body></html>"
        acquire._fetch_chrome_html = lambda url: "<html><body><article><p>HYDRATED CONTENT</p></article></body></html>"
        try:
            res = acquire.acquire("https://spa.example/app", _opts(engine="auto"))
        finally:
            acquire._fetch_lite_html = saved_lite
            acquire._fetch_chrome_html = saved_chrome
        self.assertEqual(res.engine, "chrome")
        self.assertIn("HYDRATED CONTENT", res.html)


    def test_nojs_variant_hackernoon(self):
        """R-1: HackerNoon canonical → /lite/ variant; already-/lite/ and other hosts → None."""
        self.assertEqual(acquire._nojs_variant("https://hackernoon.com/some-slug"),
                         "https://hackernoon.com/lite/some-slug")
        self.assertIsNone(acquire._nojs_variant("https://hackernoon.com/lite/some-slug"))
        self.assertIsNone(acquire._nojs_variant("https://example.com/post"))

    def test_auto_uses_nojs_variant_proactively(self):
        """R-1: auto fetches the /lite/ variant for a known JS-gated host (not the canonical)."""
        seen: list = []
        saved_lite, saved_sub = acquire._fetch_lite_html, acquire._looks_substantial
        acquire._fetch_lite_html = lambda url, mb, retries=2: (seen.append(url), "<html><body><article>body</article></body></html>")[1]
        acquire._looks_substantial = lambda h: True
        try:
            res = acquire.acquire("https://hackernoon.com/some-slug", _opts(engine="auto"))
        finally:
            acquire._fetch_lite_html, acquire._looks_substantial = saved_lite, saved_sub
        self.assertEqual(res.engine, "lite+nojs")
        self.assertTrue(any(u.endswith("/lite/some-slug") for u in seen), seen)


class TestChrome(unittest.TestCase):
    def test_chrome_absent_envelope(self):
        """TC-06-03: --engine chrome with Playwright absent → EngineNotInstalled (3)."""
        if "playwright" in sys.modules or _playwright_installed():
            self.skipTest("playwright is installed; absent-path not exercisable")
        with self.assertRaises(EngineNotInstalled) as ctx:
            acquire.acquire("https://x.example/y", _opts(engine="chrome"))
        self.assertEqual(ctx.exception.CODE, 3)
        # end-to-end through main → exit 3 + envelope (tempdir, never written to)
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as out, redirect_stderr(err):
            rc = cli.main(["https://x.example/y", os.path.join(out, "o"),
                           "--engine", "chrome", "--json-errors"])
        self.assertEqual(rc, 3)
        self.assertIn('"type": "EngineNotInstalled"', err.getvalue())


class TestSsrfAndErrors(unittest.TestCase):
    def test_ssrf_host_blocked(self):
        """TC-06-SSRF: loopback / private / link-local / metadata hosts are refused
        (and re-checked per redirect hop). A public literal IP passes."""
        for u in ("http://127.0.0.1/x", "http://169.254.169.254/latest/meta-data/",
                  "http://10.0.0.5/x", "http://192.168.1.1/x", "http://localhost/x",
                  "http://[::1]/x"):
            with self.assertRaises(FetchFailed, msg=u):
                acquire._assert_public_http(u)
        acquire._assert_public_http("http://8.8.8.8/")  # public IP → no raise

    def test_maxbytes_exceeded_streaming(self):
        """TC-06-04: streamed body over --max-bytes → FetchFailed (aborts mid-stream)."""
        with _patch_httpx(content=b"x" * 50000):
            with self.assertRaises(FetchFailed):
                acquire._http_get_bytes("https://public.example/big", max_bytes=100)

    def test_pdf_and_binary_rejected_cleanly(self):
        """TC-06-06: a PDF / binary payload fails with a clear FetchFailed, NOT a Node
        stack overflow (turndown must never see binary)."""
        with _patch_httpx(content=b"%PDF-1.7\n%\xe2\xe3\xcf\xd3 binary..."):
            with self.assertRaises(FetchFailed) as ctx:
                acquire._fetch_lite_html("https://public.example/doc.pdf", None)
        self.assertEqual(ctx.exception.details.get("kind"), "pdf")
        with _patch_httpx(content=b"PK\x03\x04\x00\x00 binary zip bytes"):
            with self.assertRaises(FetchFailed) as ctx2:
                acquire._fetch_lite_html("https://public.example/x.zip", None)
        self.assertEqual(ctx2.exception.details.get("kind"), "binary")

    def test_absolutize_img_srcs(self):
        """url-mode: relative <img src> → absolute (honouring <base href>); data:/http left alone."""
        html = ('<base href="https://arxiv.org/html/2504.20838v1/">'
                '<img src="x1.png">'
                '<img src="data:image/png;base64,A">'
                '<img src="https://cdn/y.png">')
        out = acquire._absolutize_img_srcs(html, "https://arxiv.org/html/2504.20838")
        self.assertIn('src="https://arxiv.org/html/2504.20838v1/x1.png"', out)
        self.assertIn('src="data:image/png;base64,A"', out)   # data: untouched
        self.assertIn('src="https://cdn/y.png"', out)          # already-absolute untouched
        # no <base> → resolve against the page URL's directory
        out2 = acquire._absolutize_img_srcs('<img src="fig.png">', "https://site.test/docs/page")
        self.assertIn('src="https://site.test/docs/fig.png"', out2)

    def test_fetch_failure_exit10(self):
        """TC-06-05: transport error → FetchFailed; redacts query string + userinfo."""
        with _patch_httpx(exc=OSError("conn refused")):
            with self.assertRaises(FetchFailed) as ctx:
                acquire._http_get_bytes(
                    "https://alice:s3cr3t@public.example/p?token=SECRET", max_bytes=None)
        msg = str(ctx.exception) + str(ctx.exception.details)
        self.assertNotIn("SECRET", msg)
        self.assertNotIn("s3cr3t", msg)

    def test_redact_keeps_query_redacts_secrets(self):
        """R-2.3: meaningful query survives error messages; only secrets + userinfo go."""
        self.assertEqual(
            acquire._redact("https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4200414"),
            "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4200414")
        red = acquire._redact("https://user:pw@x.com/a?token=SECRET&id=9")
        self.assertNotIn("SECRET", red)
        self.assertNotIn("pw@", red)
        self.assertIn("token=REDACTED", red)
        self.assertIn("id=9", red)

    def test_fetch_failure_has_status_and_kind(self):
        """R-2.1/2.2: FetchFailed carries details.status + details.kind so a caller can
        decide manual-vs-retry; the meaningful query survives into details.url."""
        with _patch_httpx(responses=[(403, b"", {}), (403, b"", {})]):
            with self.assertRaises(FetchFailed) as ctx:
                acquire._http_get_bytes("https://public.example/p", max_bytes=None)
        self.assertEqual(ctx.exception.details.get("status"), 403)
        self.assertEqual(ctx.exception.details.get("kind"), "bot_blocked")
        with _patch_httpx(responses=[(404, b"", {})]):
            with self.assertRaises(FetchFailed) as ctx2:
                acquire._http_get_bytes("https://public.example/p?abstract_id=7", max_bytes=None)
        self.assertIn("abstract_id=7", ctx2.exception.details.get("url", ""))
        self.assertEqual(ctx2.exception.details.get("kind"), "not_found")

    def test_redact_value_embedded_secret(self):
        """Adversarial: a token in a NON-sensitive param's value must still be redacted."""
        red = acquire._redact("https://x.com/p?next=https%3A%2F%2Fy%2Fcb%3Ftoken%3DSECRET123&id=9")
        self.assertNotIn("SECRET123", red)
        self.assertIn("id=9", red)

    def test_jsonld_date_scoped_to_ldjson(self):
        """Adversarial: a stray datePublished in plain <script>/body must NOT be picked;
        only a real JSON-LD block counts."""
        stray = '<script>var m={"datePublished":"1999-01-01"};</script><p>body</p>'
        self.assertIsNone(acquire._jsonld_date(stray))
        self.assertIsNone(acquire._structured_date(stray))
        real = ('<script type="application/ld+json">{"@type":"Article",'
                '"datePublished":"2025-04-30"}</script>')
        self.assertEqual(acquire._jsonld_date(real), "2025-04-30")

    def test_arxiv_date_from_id(self):
        """R-4: arXiv id encodes YYMM — derive a correct date, ignore trafilatura's heuristic."""
        self.assertEqual(acquire._arxiv_date_from_url("https://arxiv.org/html/2504.20838"), "2025-04")
        self.assertEqual(acquire._arxiv_date_from_url("https://arxiv.org/abs/2204.00251"), "2022-04")
        self.assertIsNone(acquire._arxiv_date_from_url("https://example.com/post"))

    def test_non_http_scheme_refused(self):
        """TC-06-04b: non-http(s) top-level INPUT is not fetched (routed local→BadInput)."""
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as out, redirect_stderr(err):
            rc = cli.main(["gopher://evil/x", os.path.join(out, "o"), "--json-errors"])
        self.assertEqual(rc, 1)
        self.assertIn('"type": "BadInput"', err.getvalue())

    def test_resolve_url_image_scheme_and_failure(self):
        """url-image resolver: http → bytes; file:// → None; failure → None."""
        with _patch_httpx(content=b"\x89PNGdata"):
            self.assertEqual(
                acquire._resolve_url_image("https://x/a.png", _opts()), b"\x89PNGdata")
        self.assertIsNone(acquire._resolve_url_image("file:///etc/passwd", _opts()))
        with _patch_httpx(exc=OSError("down")):
            self.assertIsNone(acquire._resolve_url_image("https://x/b.png", _opts()))

    def test_max_images_bounds_remote_fetches(self):
        """TC-06-04c (SSRF amplification): --max-images bounds the number of REMOTE
        fetch attempts, not just disk writes."""
        import tempfile, shutil as _sh
        from pathlib import Path as _P
        from html2md import emit
        from html2md.model import AcquireResult

        calls: list[str] = []

        def _resolver(src: str) -> bytes:
            calls.append(src)
            return b"\x89PNG-distinct-" + src.encode()  # distinct bytes ⇒ no dedup masking

        md = "".join(f"![](http://internal.host/img{i}.png)" for i in range(6))
        d = tempfile.mkdtemp()
        self.addCleanup(_sh.rmtree, d, ignore_errors=True)
        acq = AcquireResult(html="", base_url="http://internal.host", mode="url")
        emit._download_and_rewrite(
            [md], acq, attach_dir=_P(d) / "_attachments", attach_name="_attachments",
            max_images=2, remote_resolver=_resolver)
        self.assertLessEqual(len(calls), 2, f"max-images did not bound fetches: {calls}")


class TestRetryUAandEngines(unittest.TestCase):
    """Borrowed-from-last30days robustness: retry/backoff/429, 403→browser-UA, Jina, rate-limit."""

    def test_retry_then_success(self):
        with _no_backoff() as nb, _patch_httpx(responses=[
                _real_httpx.ConnectError("boom"), (200, b"<html>ok</html>", {})]):
            out = acquire._http_get_bytes("https://public.example/p", max_bytes=None)
        self.assertEqual(out, b"<html>ok</html>")
        self.assertEqual(len(nb.slept), 1)  # one backoff before the single retry

    def test_retry_exhausted_is_fetchfailed(self):
        with _no_backoff(), _patch_httpx(responses=[_real_httpx.ConnectError("x")]):
            with self.assertRaises(FetchFailed):
                acquire._http_get_bytes("https://public.example/p", max_bytes=None, retries=2)

    def test_403_escalates_to_browser_ua(self):
        with _patch_httpx(responses=[(403, b"", {}), (200, b"<html>ok</html>", {})]) as px:
            out = acquire._http_get_bytes("https://public.example/p", max_bytes=None)
        self.assertEqual(out, b"<html>ok</html>")
        self.assertEqual(px._fake.seen_uas, [acquire._UA, acquire._BROWSER_UA])

    def test_403_both_uas_terminal(self):
        with _patch_httpx(responses=[(403, b"", {}), (403, b"", {})]) as px:
            with self.assertRaises(FetchFailed):
                acquire._http_get_bytes("https://public.example/p", max_bytes=None)
        self.assertEqual(px._fake.seen_uas, [acquire._UA, acquire._BROWSER_UA])  # escalated once

    def test_429_honours_retry_after(self):
        with _no_backoff() as nb, _patch_httpx(responses=[
                (429, b"", {"retry-after": "0"}), (200, b"<html>ok</html>", {})]):
            out = acquire._http_get_bytes("https://public.example/p", max_bytes=None)
        self.assertEqual(out, b"<html>ok</html>")
        self.assertEqual(nb.slept, [0.0])  # honoured Retry-After: 0

    def test_5xx_retried(self):
        with _no_backoff(), _patch_httpx(responses=[(503, b"", {}), (200, b"<html>ok</html>", {})]):
            out = acquire._http_get_bytes("https://public.example/p", max_bytes=None)
        self.assertEqual(out, b"<html>ok</html>")

    def test_4xx_terminal_no_retry(self):
        with _no_backoff() as nb, _patch_httpx(responses=[(404, b"", {})]) as px:
            with self.assertRaises(FetchFailed):
                acquire._http_get_bytes("https://public.example/p", max_bytes=None, retries=2)
        self.assertEqual(px._fake._i, 1)   # exactly ONE attempt — 4xx is terminal
        self.assertEqual(nb.slept, [])

    def test_jina_engine_endpoint_and_format(self):
        with _patch_httpx(content=b"<html>jina rendered</html>") as px:
            html = acquire._fetch_jina_html("https://example.com/article", None)
        self.assertIn("jina rendered", html)
        self.assertTrue(px._fake.seen_urls[0].startswith(
            "https://r.jina.ai/https://example.com/article"))
        self.assertEqual(px._fake.seen_headers[0].get("X-Return-Format"), "html")

    def test_rate_limiter_sleeps_between_requests(self):
        clock = [100.0]
        saved_m, saved_s = acquire._monotonic, acquire._sleep
        slept: list = []
        acquire._monotonic = lambda: clock[0]
        acquire._sleep = lambda d: (slept.append(d), clock.__setitem__(0, clock[0] + d))
        try:
            rl = acquire._RateLimiter(2.0)  # 0.5s min interval
            rl.wait()   # first: now(100) >= next(0) → no sleep
            rl.wait()   # second: now(100) < next(100.5) → sleep 0.5
        finally:
            acquire._monotonic, acquire._sleep = saved_m, saved_s
        self.assertAlmostEqual(sum(slept), 0.5, places=3)


class TestProactiveVariants(unittest.TestCase):
    """R-7 (Wikipedia REST) / R-9 (arXiv /html) proactive URL rewrites + link absolutize."""

    def test_mediawiki_rest_variant(self):
        self.assertEqual(
            acquire._mediawiki_rest_variant("https://en.wikipedia.org/wiki/Value_averaging"),
            "https://en.wikipedia.org/api/rest_v1/page/html/Value_averaging")
        self.assertEqual(
            acquire._mediawiki_rest_variant(
                "https://ru.wikipedia.org/wiki/Long-Term_Capital_Management"),
            "https://ru.wikipedia.org/api/rest_v1/page/html/Long-Term_Capital_Management")
        # mobile host normalised to the API host
        self.assertEqual(
            acquire._mediawiki_rest_variant("https://en.m.wikipedia.org/wiki/Foo"),
            "https://en.wikipedia.org/api/rest_v1/page/html/Foo")
        # virtual namespaces + non-wiki hosts → no rewrite
        self.assertIsNone(
            acquire._mediawiki_rest_variant("https://en.wikipedia.org/wiki/Special:Search"))
        self.assertIsNone(acquire._mediawiki_rest_variant("https://example.com/wiki/Foo"))

    def test_arxiv_html_variant(self):
        for src in ("https://arxiv.org/abs/2505.12345", "https://arxiv.org/pdf/2505.12345",
                    "https://arxiv.org/pdf/2505.12345.pdf"):
            self.assertEqual(acquire._arxiv_html_variant(src),
                             "https://arxiv.org/html/2505.12345", src)
        self.assertEqual(acquire._arxiv_html_variant("https://arxiv.org/abs/2505.12345v2"),
                         "https://arxiv.org/html/2505.12345v2")
        # adversarial: a ?context= query / #fragment must NOT defeat the rewrite (matched
        # on the parsed path, not the whole URL).
        self.assertEqual(
            acquire._arxiv_html_variant("https://arxiv.org/abs/2505.12345?context=cs.LG"),
            "https://arxiv.org/html/2505.12345")
        self.assertEqual(
            acquire._arxiv_html_variant("https://arxiv.org/abs/2505.12345#S1"),
            "https://arxiv.org/html/2505.12345")
        self.assertIsNone(acquire._arxiv_html_variant("https://arxiv.org/html/2505.12345"))
        self.assertIsNone(acquire._arxiv_html_variant("https://example.com/abs/2505.12345"))

    def test_absolutize_links_only_with_base(self):
        html = ('<base href="//en.wikipedia.org/wiki/">'
                '<a href="./Foo#x">f</a><a href="#frag">g</a>'
                '<a href="https://y/z">h</a><a href="mailto:a@b">m</a>')
        out = acquire._absolutize_links(html, "https://en.wikipedia.org/wiki/Bar")
        self.assertIn('href="https://en.wikipedia.org/wiki/Foo#x"', out)
        self.assertIn('href="#frag"', out)          # in-page anchor preserved
        self.assertIn('href="https://y/z"', out)     # already-absolute preserved
        self.assertIn('href="mailto:a@b"', out)      # non-nav scheme preserved
        # no <base href> → returned untouched (no behaviour change for the common case)
        nobase = '<a href="./Foo">f</a>'
        self.assertEqual(acquire._absolutize_links(nobase, "https://x/y"), nobase)

    def test_absolutize_links_ignores_attr_prefixed_href(self):
        """Adversarial: data-href must NOT be matched (it would hijack the match from the
        real href on the same <a> and leave THAT one relative)."""
        html = ('<base href="//en.wikipedia.org/wiki/">'
                '<a data-href="./LAZY" href="./Real">x</a>')
        out = acquire._absolutize_links(html, "https://en.wikipedia.org/wiki/Bar")
        self.assertIn('data-href="./LAZY"', out)                                   # untouched
        self.assertIn('href="https://en.wikipedia.org/wiki/Real"', out)            # real one fixed

    def test_auto_uses_arxiv_html_variant(self):
        """R-9: auto fetches /html/<id> (not /abs/), reports engine lite+arxiv-html."""
        seen: list = []
        saved_lite, saved_sub = acquire._fetch_lite_html, acquire._looks_substantial
        acquire._fetch_lite_html = lambda url, mb, retries=2: (
            seen.append(url), "<html><body><article>full text</article></body></html>")[1]
        acquire._looks_substantial = lambda h: True
        try:
            res = acquire.acquire("https://arxiv.org/abs/2505.12345", _opts(engine="auto"))
        finally:
            acquire._fetch_lite_html, acquire._looks_substantial = saved_lite, saved_sub
        self.assertEqual(res.engine, "lite+arxiv-html")
        self.assertTrue(any(u.endswith("/html/2505.12345") for u in seen), seen)

    def test_arxiv_404_gives_pdf_hint(self):
        """R-9: a 404 on the /html/ variant becomes an actionable arxiv_no_html error."""
        saved_lite = acquire._fetch_lite_html

        def _raise(url, mb, retries=2):
            raise FetchFailed("nope", details={"url": url, "status": 404, "kind": "not_found"})

        acquire._fetch_lite_html = _raise
        try:
            with self.assertRaises(FetchFailed) as ctx:
                acquire.acquire("https://arxiv.org/abs/2204.00251", _opts(engine="lite"))
        finally:
            acquire._fetch_lite_html = saved_lite
        self.assertEqual(ctx.exception.details.get("kind"), "arxiv_no_html")
        self.assertIn("pdf skill", str(ctx.exception).lower())

    def test_wikipedia_proactive_rest_fetch(self):
        """R-7: a Wikipedia article fetches the REST page/html; provenance stays canonical."""
        seen: list = []
        saved_lite, saved_sub = acquire._fetch_lite_html, acquire._looks_substantial
        acquire._fetch_lite_html = lambda url, mb, retries=2: (
            seen.append(url),
            '<base href="//en.wikipedia.org/wiki/"><html><body>'
            '<p>real article body text</p></body></html>')[1]
        acquire._looks_substantial = lambda h: True
        try:
            res = acquire.acquire(
                "https://en.wikipedia.org/wiki/Value_averaging", _opts(engine="auto"))
        finally:
            acquire._fetch_lite_html, acquire._looks_substantial = saved_lite, saved_sub
        self.assertEqual(res.engine, "lite+restapi")
        self.assertTrue(
            any("/api/rest_v1/page/html/Value_averaging" in u for u in seen), seen)
        self.assertEqual(res.base_url, "https://en.wikipedia.org/wiki/Value_averaging")


class TestEmptyExtractionGuard(unittest.TestCase):
    """R-7a: a substantial source → near-empty body is a typed exit 11, never silent 0."""

    def test_predicate(self):
        self.assertTrue(cli._extraction_is_empty("\n", "x" * 3000))
        self.assertTrue(cli._extraction_is_empty("   \n  ", "x" * 3000))
        self.assertFalse(cli._extraction_is_empty("a real body of content", "x" * 3000))
        self.assertFalse(cli._extraction_is_empty("\n", "tiny source"))  # small src → ok
        self.assertFalse(cli._extraction_is_empty("![](http://x/y.png)", "x" * 3000))  # img

    def test_empty_extraction_exit11_envelope(self):
        """Big source HTML that converts to nothing → exit 11 + EmptyExtraction envelope."""
        from html2md import acquire as A, core_bridge, model
        saved_acq, saved_core = A.acquire, core_bridge.html_to_markdown
        A.acquire = lambda ref, opts: model.AcquireResult(
            html="<html><body>" + "x" * 5000 + "</body></html>", base_url=ref, mode="url",
            engine="lite", source_meta=model.SourceMeta(url=ref, title="T"))
        core_bridge.html_to_markdown = lambda h: ""  # conversion collapses to empty
        try:
            err = io.StringIO()
            with tempfile.TemporaryDirectory() as out, redirect_stderr(err):
                rc = cli.main(["https://x.example/big", os.path.join(out, "o"),
                               "--json-errors"])
        finally:
            A.acquire, core_bridge.html_to_markdown = saved_acq, saved_core
        self.assertEqual(rc, 11)
        self.assertIn('"type": "EmptyExtraction"', err.getvalue())


def _playwright_installed() -> bool:
    import importlib.util
    return importlib.util.find_spec("playwright") is not None


if __name__ == "__main__":
    unittest.main()

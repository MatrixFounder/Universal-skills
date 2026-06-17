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


class _FakeStream:
    """Mimics httpx's streaming response context manager."""

    def __init__(self, content: bytes):
        self._content = content
        self.is_redirect = False
        self.headers: dict = {}
        self.status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_bytes(self, chunk_size: int = 65536):
        for i in range(0, len(self._content), 4096):
            yield self._content[i:i + 4096]


class _FakeClient:
    def __init__(self, content: bytes, exc: Exception | None):
        self._content, self._exc = content, exc

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def stream(self, method, url):  # noqa: D401 — mimic httpx.Client.stream
        if self._exc:
            raise self._exc
        return _FakeStream(self._content)


class _FakeHttpx:
    def __init__(self, content: bytes = b"", exc: Exception | None = None):
        self._content, self._exc = content, exc

    def Client(self, **kw):  # noqa: N802 — mimic httpx.Client
        return _FakeClient(self._content, self._exc)


class _patch_httpx:
    """Inject a fake httpx + bypass the public-IP gate so the fetch logic is exercised."""

    def __init__(self, *, public: bool = True, **kw):
        self._fake = _FakeHttpx(**kw)
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
        acquire._fetch_lite_html = lambda url, mb: "<html><body><div id='app'></div></body></html>"
        acquire._fetch_chrome_html = lambda url: "<html><body><article><p>HYDRATED CONTENT</p></article></body></html>"
        try:
            res = acquire.acquire("https://spa.example/app", _opts(engine="auto"))
        finally:
            acquire._fetch_lite_html = saved_lite
            acquire._fetch_chrome_html = saved_chrome
        self.assertEqual(res.engine, "chrome")
        self.assertIn("HYDRATED CONTENT", res.html)


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

    def test_fetch_failure_exit10(self):
        """TC-06-05: transport error → FetchFailed; redacts query string + userinfo."""
        with _patch_httpx(exc=OSError("conn refused")):
            with self.assertRaises(FetchFailed) as ctx:
                acquire._http_get_bytes(
                    "https://alice:s3cr3t@public.example/p?token=SECRET", max_bytes=None)
        msg = str(ctx.exception) + str(ctx.exception.details)
        self.assertNotIn("SECRET", msg)
        self.assertNotIn("s3cr3t", msg)

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


def _playwright_installed() -> bool:
    import importlib.util
    return importlib.util.find_spec("playwright") is not None


if __name__ == "__main__":
    unittest.main()

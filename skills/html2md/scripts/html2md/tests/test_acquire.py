"""Bead 022-02 — FC-1 offline acquisition (file + archive dispatch). Stdlib-only."""
from __future__ import annotations

import os
import plistlib
import socket
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import acquire  # noqa: E402
from html2md.cli import build_parser  # noqa: E402


def _opts(**over):
    args = build_parser().parse_args(["x.html"])
    for k, v in over.items():
        setattr(args, k, v)
    return args


def _make_webarchive(main_html: str, subframes: tuple[str, ...] = ()) -> bytes:
    def res(html: str, url: str) -> dict:
        return {
            "WebResourceData": html.encode("utf-8"),
            "WebResourceURL": url,
            "WebResourceMIMEType": "text/html",
            "WebResourceTextEncodingName": "UTF-8",
        }

    plist: dict = {"WebMainResource": res(main_html, "https://example.com/")}
    if subframes:
        plist["WebSubframeArchives"] = [
            {"WebMainResource": res(h, f"https://example.com/frame{i}")}
            for i, h in enumerate(subframes, 1)
        ]
    return plistlib.dumps(plist, fmt=plistlib.FMT_BINARY)


def _substantial_frame(needle: str) -> str:
    body = (f"<p>{needle}</p>" + "<p>The quick brown fox jumps over the lazy dog. </p>" * 40)
    return f"<html><head><title>{needle}</title></head><body>{body}</body></html>"


class TestDispatch(unittest.TestCase):
    def test_dispatch_by_extension_and_magic(self):
        """TC-02-01: extension + magic-byte classification; url routes via acquire."""
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "a.html"
            html.write_text("<html><body>x</body></html>", encoding="utf-8")
            wa = Path(d) / "a.webarchive"
            wa.write_bytes(_make_webarchive("<html><body>x</body></html>"))
            noext = Path(d) / "page"
            noext.write_text("<!doctype html><html><body>x</body></html>", encoding="utf-8")
            noext_wa = Path(d) / "blob"
            noext_wa.write_bytes(b"bplist00" + b"\x00" * 16)

            self.assertEqual(acquire._dispatch_format(str(html)), "file")
            self.assertEqual(acquire._dispatch_format(str(wa)), "archive")
            self.assertEqual(acquire._dispatch_format(str(noext)), "file")
            self.assertEqual(acquire._dispatch_format(str(noext_wa)), "archive")

    def test_url_routes_to_url_branch(self):
        """TC-02-01b: http(s) INPUT routes to the url branch (mocked fetch — no egress)."""
        saved = acquire._http_get_bytes
        acquire._http_get_bytes = lambda url, **k: b"<html><body><p>routed ok</p></body></html>"
        try:
            res = acquire.acquire("https://example.com/x", _opts(engine="lite"))
        finally:
            acquire._http_get_bytes = saved
        self.assertEqual(res.mode, "url")
        self.assertEqual(res.engine, "lite")


class TestFileBranch(unittest.TestCase):
    def test_file_charset_fallback(self):
        """TC-02-02: windows-1251 page decodes to correct Cyrillic."""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "ru.html"
            body = "Привет, мир — тест кодировки"
            raw = (
                '<html><head><meta charset="windows-1251">'
                "<title>RU</title></head><body><p>" + body + "</p></body></html>"
            ).encode("cp1251")
            src.write_bytes(raw)
            res = acquire.acquire(str(src), _opts())
            self.assertEqual(res.mode, "file")
            self.assertIn("Привет, мир", res.html)
            self.assertTrue(res.base_url.startswith("file://"))

    def test_source_meta_best_effort(self):
        """TC-02-05: og:title/author/date populate SourceMeta; absent → None."""
        with tempfile.TemporaryDirectory() as d:
            rich = Path(d) / "rich.html"
            rich.write_text(
                '<html><head>'
                '<meta property="og:title" content="Hello World">'
                '<meta name="author" content="Jane Doe">'
                '<meta property="article:published_time" content="2026-06-17">'
                "<title>fallback</title></head><body>x</body></html>",
                encoding="utf-8",
            )
            res = acquire.acquire(str(rich), _opts())
            self.assertEqual(res.source_meta.title, "Hello World")
            self.assertEqual(res.source_meta.author, "Jane Doe")
            self.assertEqual(res.source_meta.date, "2026-06-17")

            bare = Path(d) / "bare.html"
            bare.write_text("<html><body>no meta</body></html>", encoding="utf-8")
            res2 = acquire.acquire(str(bare), _opts())
            self.assertIsNone(res2.source_meta.title)
            self.assertIsNone(res2.source_meta.author)


class TestArchiveBranch(unittest.TestCase):
    def test_archive_frame_selection(self):
        """TC-02-03: --archive-frame main vs 1 vs all changes the extracted HTML."""
        main_html = "<html><head><title>Main</title></head><body><p>main shell</p></body></html>"
        wa_bytes = _make_webarchive(
            main_html,
            subframes=(_substantial_frame("FRAME_ONE_NEEDLE"),
                       _substantial_frame("FRAME_TWO_NEEDLE")),
        )
        with tempfile.TemporaryDirectory() as d:
            wa = Path(d) / "page.webarchive"
            wa.write_bytes(wa_bytes)

            res_main = acquire.acquire(str(wa), _opts(archive_frame="main"))
            self.assertEqual(res_main.mode, "archive")
            self.assertNotIn("FRAME_ONE_NEEDLE", res_main.html)

            res_one = acquire.acquire(str(wa), _opts(archive_frame="1"))
            self.assertIn("FRAME_ONE_NEEDLE", res_one.html)

            res_all = acquire.acquire(str(wa), _opts(archive_frame="all"))
            self.assertIn("FRAME_ONE_NEEDLE", res_all.html)
            self.assertIn("FRAME_TWO_NEEDLE", res_all.html)

    def test_offline_zero_network(self):
        """TC-02-04 (I-3): file + archive acquisition makes ZERO network calls."""
        blocked = []

        def _boom(*a, **k):
            blocked.append(a)
            raise AssertionError("network call attempted in offline acquire")

        saved = (socket.create_connection, socket.getaddrinfo)
        socket.create_connection, socket.getaddrinfo = _boom, _boom
        try:
            with tempfile.TemporaryDirectory() as d:
                html = Path(d) / "a.html"
                html.write_text("<html><body>offline</body></html>", encoding="utf-8")
                self.assertIn("offline", acquire.acquire(str(html), _opts()).html)
                wa = Path(d) / "a.webarchive"
                wa.write_bytes(_make_webarchive(
                    "<html><body>archive offline</body></html>"))
                self.assertEqual(
                    acquire.acquire(str(wa), _opts(archive_frame="main")).mode,
                    "archive")
        finally:
            socket.create_connection, socket.getaddrinfo = saved
        self.assertEqual(blocked, [])


if __name__ == "__main__":
    unittest.main()

"""OP1 `html fetch` — artifact shape, the untrusted-HTML sanitizer (CWE-22 file:// strip),
image localization, sidecar round-trip, and authed-write 0600 (TASK 027).

Run from ``skills/html/scripts``:  python -m unittest discover -s html2md/tests
"""
import argparse
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import cli, serialize  # noqa: E402
from html2md.exceptions import SelfOverwriteRefused  # noqa: E402
from html2md.model import AcquireResult, SourceMeta  # noqa: E402


def _opts(**kw):
    base = dict(download_images=True, attachments_dir="_attachments", max_images=None,
                chrome_storage_state=None, chrome_cookies_file=None,
                chrome_user_data_dir=None, chrome_auth_map=None, max_bytes=None, retries=0)
    base.update(kw)
    return argparse.Namespace(**base)


class TestSanitizer(unittest.TestCase):
    def test_strips_file_and_script_schemes(self):
        h = ('<img src="file:///etc/passwd">'
             '<a href="javascript:alert(1)">x</a>'
             '<link href="vbscript:evil">'
             '<object data="file:///secret"></object>')
        out = serialize.sanitize_untrusted_html(h)
        self.assertNotIn("file:", out)
        self.assertNotIn("javascript:", out)
        self.assertNotIn("vbscript:", out)

    def test_strips_srcset_and_css_file_urls(self):
        h = ('<img srcset="file:///a 1x, file:///b 2x">'
             '<div style="background:url(file:///etc/hosts)">y</div>')
        out = serialize.sanitize_untrusted_html(h)
        self.assertNotIn("file:", out)

    def test_strips_private_host_refs(self):
        h = ('<img src="http://169.254.169.254/latest/meta-data/">'
             '<a href="http://localhost:8080/admin">x</a>'
             '<img src="http://10.0.0.5/x.png">')
        out = serialize.sanitize_untrusted_html(h)
        self.assertNotIn("169.254.169.254", out)
        self.assertNotIn("localhost:8080", out)
        self.assertNotIn("10.0.0.5", out)

    def test_keeps_data_uri_and_public_http(self):
        h = ('<img src="data:image/png;base64,iVBORw0KGgo=">'
             '<img src="https://example.com/real.png">')
        out = serialize.sanitize_untrusted_html(h)
        self.assertIn("data:image/png", out)            # inline, not a file read → kept
        self.assertIn("https://example.com/real.png", out)


class TestWriteArtifact(unittest.TestCase):
    def test_artifact_shape_and_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            acq = AcquireResult(
                html="<html><body><h1>Hi</h1><p>text</p></body></html>",
                base_url="", mode="file", engine="lite",
                source_meta=SourceMeta(url="https://ex.com/a", title="A Title",
                                       date="2026-01-01", author="Me"))
            art = serialize.write_artifact(acq, Path(d), _opts(download_images=False),
                                           input_ref="https://ex.com/a")
            self.assertTrue(art.html_path.is_file())
            self.assertTrue(art.meta_path.is_file())
            meta = json.loads(art.meta_path.read_text())
            self.assertEqual(meta["schema"], "html/fetch-artifact@1")
            self.assertEqual(meta["source"], "https://ex.com/a")
            self.assertEqual(meta["title"], "A Title")
            self.assertEqual(meta["engine"], "lite")
            self.assertEqual(meta["content_kind"], "html")

    def test_file_uri_img_stripped_from_saved_html(self):
        with tempfile.TemporaryDirectory() as d:
            acq = AcquireResult(
                html='<html><body><img src="file:///etc/passwd"><p>x</p></body></html>',
                base_url="", mode="file")
            art = serialize.write_artifact(acq, Path(d), _opts(download_images=True),
                                           input_ref="evil.html")
            self.assertNotIn("file:", art.html_path.read_text())

    def test_images_localized_to_attachments(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "src"
            base.mkdir()
            (base / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\nDATA")
            acq = AcquireResult(
                html='<html><body><img src="pic.png"><p>x</p></body></html>',
                base_url=str(base), mode="file")
            out = Path(d) / "out"
            art = serialize.write_artifact(acq, out, _opts(), input_ref=str(base / "p.html"))
            saved = art.html_path.read_text()
            self.assertIn("_attachments/", saved)          # <img> rewritten to local rel
            self.assertNotIn('src="pic.png"', saved)
            self.assertIsNotNone(art.attachments_dir)
            self.assertEqual(len(list(art.attachments_dir.glob("*.png"))), 1)

    def test_authenticated_fetch_writes_0600(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "src"
            base.mkdir()
            (base / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\nDATA")
            acq = AcquireResult(
                html='<html><body><img src="pic.png"><p>secret</p></body></html>',
                base_url=str(base), mode="file", engine="chrome",
                source_meta=SourceMeta(url="https://x.com/private"))
            art = serialize.write_artifact(
                acq, Path(d) / "out",
                _opts(download_images=True, chrome_storage_state="/secrets/x.json"),
                input_ref="https://x.com/private")
            mode = stat.S_IMODE(os.stat(art.html_path).st_mode)
            self.assertEqual(mode, 0o600, f"authed body must be 0600, got {oct(mode)}")
            self.assertEqual(stat.S_IMODE(os.stat(art.meta_path).st_mode), 0o600)
            # the localized image bytes must also be owner-only (no group/world read)
            img = next(art.attachments_dir.glob("*.png"))
            self.assertEqual(stat.S_IMODE(os.stat(img).st_mode), 0o600,
                             "authed localized image must be 0600")

    def test_refuses_overwriting_the_input(self):
        # `html2md ./page.html .` resolves the artifact path back onto the input → must
        # refuse (else the combined command would overwrite then DELETE the user's source).
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            src = out / "page.html"
            src.write_text("<html><body><p>x</p></body></html>", encoding="utf-8")
            acq = AcquireResult(html=src.read_text(), base_url="", mode="file",
                                source_meta=SourceMeta())
            with self.assertRaises(SelfOverwriteRefused):
                serialize.write_artifact(acq, out, _opts(download_images=False),
                                         input_ref=str(src))
            self.assertTrue(src.is_file(), "input must NOT be clobbered/deleted")


class TestReadArtifact(unittest.TestCase):
    def test_round_trip_via_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            acq = AcquireResult(
                html="<html><body><h1>RT</h1></body></html>", base_url="", mode="file",
                engine="lite+arxiv-html",
                source_meta=SourceMeta(url="https://arxiv.org/html/2504.20838",
                                       title="Paper", date="2025-04", author="Authors"))
            art = serialize.write_artifact(acq, Path(d), _opts(download_images=False),
                                           input_ref="https://arxiv.org/html/2504.20838")
            back = serialize.read_artifact(art.html_path)
            self.assertEqual(back.source_meta.url, "https://arxiv.org/html/2504.20838")
            self.assertEqual(back.source_meta.title, "Paper")
            self.assertEqual(back.source_meta.author, "Authors")
            self.assertEqual(back.engine, "lite+arxiv-html")
            self.assertEqual(back.content_kind, "html")

    def test_no_sidecar_falls_back_to_html_meta(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "hand-saved.html"
            p.write_text("<html><head><title>Hand Saved</title></head>"
                         "<body><p>x</p></body></html>", encoding="utf-8")
            back = serialize.read_artifact(p)
            self.assertEqual(back.source_meta.title, "Hand Saved")
            self.assertEqual(back.mode, "file")


class TestFetchCli(unittest.TestCase):
    def _sample(self, d):
        p = Path(d) / "in.html"
        p.write_text("<html><head><title>T</title></head>"
                     "<body><h1>T</h1><p>plenty of body text here for substance</p>"
                     "</body></html>", encoding="utf-8")
        return p

    def test_fetch_verb_writes_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            src = self._sample(d)
            out = Path(d) / "out"
            rc = cli.main(["fetch", str(src), str(out), "--json-errors"])
            self.assertEqual(rc, 0)
            self.assertEqual(len(list(out.glob("*.html"))), 1)
            self.assertEqual(len(list(out.glob("*.meta.json"))), 1)

    def test_fetch_refuses_remote_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            src = self._sample(d)
            rc = cli.main(["fetch", str(src), str(Path(d) / "o"),
                           "--remote-format", "markdown", "--json-errors"])
            self.assertEqual(rc, 2)  # Usage

    def test_fetch_stdout_emits_html_no_files(self):
        with tempfile.TemporaryDirectory() as d:
            src = self._sample(d)
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["fetch", str(src), "--stdout"])
            self.assertEqual(rc, 0)
            self.assertIn("<h1>T</h1>", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

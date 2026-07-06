"""Bead 022-05 — FC-4 emit (frontmatter + _attachments + dual-output) + MVP pipeline."""
from __future__ import annotations

import base64
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.parse import quote as urllib_quote

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import cli, emit  # noqa: E402
from html2md.model import SourceMeta  # noqa: E402

_HAVE_NODE = shutil.which("node") is not None and os.path.isdir(
    os.path.join(SCRIPTS, "node_modules", "turndown"))
_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes-payload"
_PNG2 = b"\x89PNG\r\n\x1a\n" + b"different-fake-png-payload"


class TestFrontmatter(unittest.TestCase):
    def test_frontmatter_shape(self):
        """TC-05-01: frontmatter has present keys + tags:[]; absent keys omitted."""
        fm = emit._frontmatter(SourceMeta(url="https://x/y", title="Hello", date="2026-06-17"))
        self.assertIn('source: "https://x/y"', fm)
        self.assertIn('title: "Hello"', fm)
        self.assertIn('date: "2026-06-17"', fm)
        self.assertIn("tags: []", fm)
        self.assertNotIn("author:", fm)  # absent → omitted
        self.assertTrue(fm.startswith("---\n") and "\n---\n" in fm)

    def test_slugify(self):
        self.assertEqual(emit._slugify("Hello, World!"), "hello-world")
        self.assertEqual(emit._slugify("  "), "untitled")


@unittest.skipUnless(_HAVE_NODE, "node + turndown not installed")
class TestEmitPipeline(unittest.TestCase):
    def _run(self, html: str, argv_extra: list[str], *, files: dict | None = None):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        src = Path(d) / "page.html"
        src.write_text(html, encoding="utf-8")
        for name, data in (files or {}).items():
            (Path(d) / name).write_bytes(data)
        out = Path(d) / "out"
        rc = cli.main([str(src), str(out), *argv_extra])
        return rc, out

    def test_image_download_dedup(self):
        """TC-05-02 (AC-R4): two srcs with identical bytes → ONE _attachments file."""
        html = ('<html><body><p>x</p>'
                '<img src="a.png"><img src="b.png"></body></html>')
        rc, out = self._run(html, ["--no-reader"], files={"a.png": _PNG, "b.png": _PNG})
        self.assertEqual(rc, 0)
        attach = out / "_attachments"
        self.assertTrue(attach.is_dir())
        pngs = list(attach.glob("*"))
        self.assertEqual(len(pngs), 1, f"expected 1 deduped file, got {pngs}")
        md = (out / "page.md").read_text(encoding="utf-8")
        self.assertIn("_attachments/", md)
        self.assertNotIn("](a.png)", md)

    def test_image_traversal_blocked(self):
        """SEC (CWE-22/73): attacker <img src> cannot read files outside base_dir."""
        # A secret file that is a SIBLING of the input dir (reachable via ../).
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        sibling = Path(d).parent / f"h2m_secret_{os.path.basename(d)}.txt"
        sibling.write_bytes(b"TOPSECRET-EXFIL")
        self.addCleanup(sibling.unlink, missing_ok=True)
        src_dir = Path(d) / "in"
        src_dir.mkdir()
        page = src_dir / "page.html"
        page.write_text(
            "<html><body><p>x</p>"
            f'<img src="../../{sibling.name}">'      # relative traversal
            '<img src="/etc/hostname">'              # absolute
            '<img src="file:///etc/hostname">'       # file:// scheme
            "</body></html>", encoding="utf-8")
        out = Path(d) / "out"
        rc = cli.main([str(page), str(out), "--no-reader"])
        self.assertEqual(rc, 0)
        # Nothing was exfiltrated into the vault.
        attach = out / "_attachments"
        leaked = []
        if attach.exists():
            for f in attach.iterdir():
                if b"TOPSECRET-EXFIL" in f.read_bytes():
                    leaked.append(f.name)
        self.assertEqual(leaked, [], f"secret exfiltrated: {leaked}")
        md = (out / "page.md").read_text(encoding="utf-8")
        self.assertNotIn("TOPSECRET", md)
        self.assertNotIn("_attachments/", md)  # no traversal src was downloaded

    def test_no_download_keeps_urls(self):
        """TC-05-03 (AC-R4): --no-download-images keeps remote URLs; no _attachments."""
        html = '<html><body><p>x</p><img src="https://example.com/z.png"></body></html>'
        rc, out = self._run(html, ["--no-reader", "--no-download-images"])
        self.assertEqual(rc, 0)
        self.assertFalse((out / "_attachments").exists())
        md = (out / "page.md").read_text(encoding="utf-8")
        self.assertIn("https://example.com/z.png", md)

    def test_decode_data_uri_unit(self):
        """_decode_data_uri: base64 + percent-encoded images decode; sub-threshold /
        non-image / empty-garbage → None (never written)."""
        big = _PNG + b"\x00" * 1200                       # 1.2 KB of bytes
        b64 = base64.b64encode(big).decode()
        uri = f"data:image/png;base64,{b64}"
        self.assertGreaterEqual(len(uri), emit._DATA_URI_MIN_LEN)
        self.assertEqual(emit._decode_data_uri(uri), big)

        # percent-encoded (non-base64) SVG image, padded past the threshold.
        svg = "<svg xmlns='http://www.w3.org/2000/svg'>" + ("<rect/>" * 200) + "</svg>"
        pe = "data:image/svg+xml," + urllib_quote(svg)
        self.assertGreaterEqual(len(pe), emit._DATA_URI_MIN_LEN)
        self.assertEqual(emit._decode_data_uri(pe), svg.encode())

        # media-type PARAMETERS before ;base64 (RFC 2397) must still decode (adversarial B).
        param = "data:image/svg+xml;charset=utf-8;base64," + base64.b64encode(big).decode()
        self.assertEqual(emit._decode_data_uri(param), big)
        # ...but a non-image mime WITH params is still rejected.
        self.assertIsNone(emit._decode_data_uri("data:text/html;charset=utf-8;base64," + "QQ==" * 300))

        # vdd-multi regression: a percent-encoded TINY icon can clear the ENCODED floor
        # (%XX is ~3× expansion) yet be small DECODED → the decoded floor must still drop it.
        tiny_pe = "data:image/png," + ("%FF" * 342)   # 1026 enc chars (≥1024), 342 dec bytes (<512)
        self.assertGreaterEqual(len(tiny_pe), emit._DATA_URI_MIN_LEN)
        self.assertIsNone(emit._decode_data_uri(tiny_pe))

        # sub-threshold tiny icon → None
        self.assertIsNone(emit._decode_data_uri("data:image/png;base64,iVBORw0KGgo="))
        # long but NON-image mime → None (don't localize data:text/* etc.)
        self.assertIsNone(emit._decode_data_uri("data:text/html;base64," + "QQ==" * 300))
        # not a data: URI at all → None
        self.assertIsNone(emit._decode_data_uri("https://example.com/x.png"))
        # all-garbage base64 past threshold decodes to b"" → None (no 0-byte file)
        self.assertIsNone(emit._decode_data_uri("data:image/png;base64," + "@" * 1100))

    @unittest.skipUnless(_HAVE_NODE, "needs node + turndown for the convert step")
    def test_stdout_strips_data_images(self):
        """Adversarial A: --stdout must NOT dump a content-sized data: blob (agent-step
        bloat). The data: image is stripped; a remote URL image is left as a (short) link."""
        big_b64 = base64.b64encode(_PNG + b"\x00" * 1200).decode()
        html = (
            "<html><head><title>T</title></head><body><article><h1>Hi</h1>"
            "<p>" + ("real body words here " * 20) + "</p>"
            f'<img src="data:image/png;base64,{big_b64}" alt="diagram">'
            '<img src="https://x/r.png" alt="r">'
            "</article></body></html>")
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        src = Path(d) / "page.html"
        src.write_text(html, encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main([str(src), "--stdout", "--no-reader"])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertNotIn("data:image", out, "content data: blob must be stripped from stdout")
        self.assertNotIn(big_b64[:40], out, "no base64 payload may leak into stdout")
        self.assertIn("https://x/r.png", out, "remote image link is still kept in stdout")

    @unittest.skipUnless(_HAVE_NODE, "needs node + turndown for the convert step")
    def test_data_uri_image_localized_or_dropped(self):
        """TF-IMG: a CONTENT-sized inline data: image is decoded into _attachments/ (download
        ON) or kept inline (download OFF); a TINY icon data: image is dropped in both modes.

        Regression for the Vitalik `.eth.limo` case — diagrams inlined as data: PNGs were
        being silently dropped by the converter's blanket data:-image strip."""
        big_b64 = base64.b64encode(_PNG + b"\x00" * 1200).decode()
        tiny_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        html = (
            "<html><head><title>T</title></head><body><article><h1>Hi</h1>"
            "<p>" + ("real body words here " * 20) + "</p>"
            f'<img src="data:image/png;base64,{tiny_b64}" alt="icon">'
            f'<img src="data:image/png;base64,{big_b64}" alt="diagram">'
            "</article></body></html>")

        # download ON (default): big → _attachments, tiny → gone.
        rc, out = self._run(html, ["--no-reader"])
        self.assertEqual(rc, 0)
        md = (out / "page.md").read_text(encoding="utf-8")
        self.assertIn("_attachments/", md)
        self.assertNotIn("data:image", md, "data: URI must be localized, not left inline")
        self.assertNotIn("icon", md, "sub-threshold icon blob must be dropped")
        pngs = list((out / "_attachments").glob("*"))
        self.assertEqual(len(pngs), 1, f"expected exactly the one content image, got {pngs}")

        # download OFF: big stays a self-contained data: link, tiny still dropped.
        rc2, out2 = self._run(html, ["--no-reader", "--no-download-images"])
        self.assertEqual(rc2, 0)
        md2 = (out2 / "page.md").read_text(encoding="utf-8")
        self.assertEqual(md2.count("data:image"), 1, "content data: image kept inline")
        self.assertNotIn("icon", md2)
        self.assertFalse((out2 / "_attachments").exists())

    def test_dual_output_default_and_no_reader(self):
        """TC-05-04 (AC-R4): default → both .md + .reader.md; --no-reader → one."""
        html = ("<html><head><title>T</title></head><body><article><h1>Hi</h1>"
                "<p>" + ("body words " * 50) + "</p></article></body></html>")
        rc, out = self._run(html, [])
        self.assertEqual(rc, 0)
        self.assertTrue((out / "page.md").exists())
        self.assertTrue((out / "page.reader.md").exists())

        rc2, out2 = self._run(html, ["--no-reader"])
        self.assertEqual(rc2, 0)
        self.assertTrue((out2 / "page.md").exists())
        self.assertFalse((out2 / "page.reader.md").exists())

    def test_slug_collision_and_idempotency(self):
        """SLUG: two different inputs with the same slug → distinct files
        (page.md + page-2.md); re-running both is idempotent (still exactly 2)."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        out = Path(d) / "out"
        (Path(d) / "a").mkdir()
        (Path(d) / "b").mkdir()
        (Path(d) / "a" / "page.html").write_text(
            "<html><body><h1>AAA</h1><p>alpha</p></body></html>", encoding="utf-8")
        (Path(d) / "b" / "page.html").write_text(
            "<html><body><h1>BBB</h1><p>beta</p></body></html>", encoding="utf-8")
        common = ["--no-reader", "--no-download-images"]
        for sub in ("a", "b"):
            self.assertEqual(
                cli.main([str(Path(d) / sub / "page.html"), str(out), *common]), 0)
        self.assertEqual(sorted(p.name for p in out.glob("*.md")),
                         ["page-2.md", "page.md"])
        self.assertIn("AAA", (out / "page.md").read_text(encoding="utf-8"))
        self.assertIn("BBB", (out / "page-2.md").read_text(encoding="utf-8"))
        # re-run BOTH → idempotent: still exactly two files, same assignment
        for sub in ("a", "b"):
            self.assertEqual(
                cli.main([str(Path(d) / sub / "page.html"), str(out), *common]), 0)
        self.assertEqual(sorted(p.name for p in out.glob("*.md")),
                         ["page-2.md", "page.md"])
        self.assertIn("AAA", (out / "page.md").read_text(encoding="utf-8"))
        self.assertIn("BBB", (out / "page-2.md").read_text(encoding="utf-8"))

    def test_stdout_and_json_errors(self):
        """TC-05-05 (AC-R5): --stdout → md on stdout, no files; failure → JSON envelope."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        src = Path(d) / "page.html"
        src.write_text("<html><body><h1>Hi</h1><p>hello</p></body></html>", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main([str(src), "--stdout", "--no-reader", "--no-download-images"])
        self.assertEqual(rc, 0)
        self.assertIn("# Hi", buf.getvalue())
        self.assertEqual(list(Path(d).glob("out*")), [])  # no output dir created

        err = io.StringIO()
        with redirect_stderr(err):
            rc2 = cli.main(["nonexistent-xyz.html", "outdir", "--json-errors"])
        self.assertEqual(rc2, 1)
        self.assertIn('"type": "BadInput"', err.getvalue())


class TestSpacedDestinations(unittest.TestCase):
    """Srcs with spaces (decoded archive attachment names, e.g. Confluence's
    "Снимок экрана … 12.58.03.png") flow as CommonMark <…>-wrapped destinations;
    _IMG_RE must match both alternatives and localization must resolve them."""

    def test_img_re_bracketed_and_bare(self):
        cases = {
            "![](<Снимок экрана в 12.58.03.png>)": "Снимок экрана в 12.58.03.png",
            "![](<a (1).png>)": "a (1).png",
            "![a](x.png)": "x.png",
            '![a](x.png "t")': "x.png",
        }
        for md, want_src in cases.items():
            m = emit._IMG_RE.search(md)
            self.assertIsNotNone(m, md)
            self.assertEqual(emit._img_src(m), want_src, md)
        # title group survives the alternation
        m = emit._IMG_RE.search('![a](x.png "t")')
        self.assertEqual(m.group(4), ' "t"')

    def test_strip_data_images_bracketed(self):
        uri = "data:image/png;base64," + "A" * 2048
        self.assertEqual(emit._strip_data_images(f"x ![]({uri}) y"), "x  y")
        self.assertEqual(emit._strip_data_images("x ![](<a b.png>) y"),
                         "x ![](<a b.png>) y")  # non-data untouched

    @unittest.skipUnless(_HAVE_NODE, "node + turndown not installed")
    def test_space_named_local_image_localized(self):
        """E2E (file mode): <img src> with spaces + Cyrillic → _attachments/<sha1>.png."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        name = "Снимок экрана 2021-03-10 в 12.58.03.png"
        (Path(d) / name).write_bytes(_PNG)
        src = Path(d) / "page.html"
        src.write_text(f'<html><body><p>x</p><img src="{name}"></body></html>',
                       encoding="utf-8")
        out = Path(d) / "out"
        rc = cli.main([str(src), str(out), "--no-reader"])
        self.assertEqual(rc, 0)
        md = (out / "page.md").read_text(encoding="utf-8")
        self.assertNotIn("Снимок", md.replace("![](_attachments/", ""))
        self.assertIn("](_attachments/", md)
        (link,) = re.findall(r"!\[\]\((_attachments/[^)]+)\)", md)
        self.assertTrue((out / link).is_file(), link)
        self.assertTrue(link.endswith(".png"))

    @unittest.skipUnless(_HAVE_NODE, "node + turndown not installed")
    def test_bracketed_invalid_host_does_not_abort(self):
        """Regression: a src like https://[cdn host]/x (bracketed placeholder,
        not IPv6) is now regex-matchable — urlparse raises ValueError on it,
        which must resolve to 'image left as-is', never abort the conversion."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        src = Path(d) / "page.html"
        src.write_text('<html><body><p>x</p>'
                       '<img src="https://[cdn host]/logo.png"></body></html>',
                       encoding="utf-8")
        out = Path(d) / "out"
        rc = cli.main([str(src), str(out), "--no-reader"])
        self.assertEqual(rc, 0)
        md = (out / "page.md").read_text(encoding="utf-8")
        self.assertIn("[cdn host]", md)  # untouched, not localized, not crashed

    @unittest.skipUnless(_HAVE_NODE, "node + turndown not installed")
    def test_webarchive_spaced_attachment_and_pseudo_ext(self):
        """E2E (archive mode): a webarchive whose subresource URL is percent-encoded
        Cyrillic-with-spaces + query (Confluence shape) localizes to _attachments/,
        and a pseudo-extension resource (atl.site.logo, PNG bytes) gets .png."""
        import plistlib
        origin = "https://wiki.example.com"
        img_url = (origin + "/download/attachments/6037496/"
                   + urllib_quote("Снимок экрана 2021-03-10 в 12.58.03.png")
                   + "?version=1&modificationDate=1615381100002&api=v2")
        logo_url = origin + "/download/attachments/393218/atl.site.logo?version=2&api=v2"
        html = ("<html><body><p>Пример расчета ниже:</p>"
                f'<img src="{img_url.replace("&", "&amp;")}">'
                f'<img src="{logo_url.replace("&", "&amp;")}">'
                "</body></html>")
        plist = {
            "WebMainResource": {
                "WebResourceData": html.encode("utf-8"),
                "WebResourceMIMEType": "text/html",
                "WebResourceTextEncodingName": "UTF-8",
                "WebResourceURL": origin + "/spaces/PMO/pages/6037496",
            },
            "WebSubresources": [
                {"WebResourceData": _PNG, "WebResourceMIMEType": "image/png",
                 "WebResourceURL": img_url},
                {"WebResourceData": _PNG2, "WebResourceMIMEType": "image/png",
                 "WebResourceURL": logo_url},
            ],
        }
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        wa = Path(d) / "page.webarchive"
        wa.write_bytes(plistlib.dumps(plist, fmt=plistlib.FMT_BINARY))
        out = Path(d) / "out"
        rc = cli.main([str(wa), str(out), "--no-reader"])
        self.assertEqual(rc, 0)
        md = (out / "page.md").read_text(encoding="utf-8")
        links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)
        self.assertEqual(len(links), 2, md)
        for link in links:
            self.assertTrue(link.startswith("_attachments/"), f"not localized: {link}")
            self.assertTrue(link.endswith(".png"), f"wrong ext: {link}")
            self.assertTrue((out / link).is_file(), link)


class TestSniffExt(unittest.TestCase):
    def test_pseudo_extension_defers_to_magic(self):
        """Confluence "atl.site.logo" (PNG bytes) → .png, not .logo."""
        self.assertEqual(
            emit._sniff_ext("https://x/download/attachments/393218/atl.site.logo?v=2",
                            _PNG), ".png")

    def test_known_ext_trusted(self):
        self.assertEqual(emit._sniff_ext("https://x/a.png", b"whatever"), ".png")
        self.assertEqual(emit._sniff_ext("https://x/b.jpeg", b""), ".jpeg")

    def test_unknown_ext_unknown_bytes_lax_fallback(self):
        self.assertEqual(emit._sniff_ext("https://x/global.logo", b"unknown"), ".logo")

    def test_no_ext_magic_and_neutral(self):
        self.assertEqual(emit._sniff_ext("https://x/noext", _PNG), ".png")
        self.assertEqual(emit._sniff_ext("https://x/noext", b"unknown"), ".img")


_TMP = Path("/Users/sergey/dev-projects/Universal-skills/tmp")
_REAL_WA = _TMP / "test_email_elma365.webarchive"


@unittest.skipUnless(_HAVE_NODE and _REAL_WA.exists(), "node + real tmp/ fixture required")
class TestEmitRealFixture(unittest.TestCase):
    def test_real_webarchive_dual_output(self):
        """TC-E2E-05a: real .webarchive → dual md + _attachments, exit 0."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        out = Path(d) / "out"
        rc = cli.main([str(_REAL_WA), str(out)])
        self.assertEqual(rc, 0)
        mds = list(out.glob("*.md"))
        self.assertTrue(mds, "no markdown produced")
        whole = next((m for m in mds if not m.name.endswith(".reader.md")), None)
        self.assertIsNotNone(whole)
        self.assertTrue(whole.read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    unittest.main()

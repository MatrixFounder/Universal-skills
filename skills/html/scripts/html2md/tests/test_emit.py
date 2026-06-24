"""Bead 022-05 — FC-4 emit (frontmatter + _attachments + dual-output) + MVP pipeline."""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import cli, emit  # noqa: E402
from html2md.model import SourceMeta  # noqa: E402

_HAVE_NODE = shutil.which("node") is not None and os.path.isdir(
    os.path.join(SCRIPTS, "node_modules", "turndown"))
_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes-payload"


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

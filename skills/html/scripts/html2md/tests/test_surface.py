"""Bead 022-01 surface + replication unit cluster (stub phase).

Run from ``skills/html2md/scripts``:
    python -m unittest discover -s html2md/tests
or via the repo harness. Each test is stdlib-only (no heavy deps needed in 022-01).
"""
from __future__ import annotations

import dataclasses
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import html2md  # noqa: E402
from html2md import cli  # noqa: E402
from html2md.exceptions import (  # noqa: E402
    BadInput,
    EngineNotInstalled,
    FetchFailed,
    InternalError,
    SelfOverwriteRefused,
)
from html2md.model import AcquireResult, CleanResult  # noqa: E402


class TestImportHygiene(unittest.TestCase):
    def test_import_no_browser_no_render(self):
        """TC-UNIT-01: package imports clean with no heavy deps loaded."""
        code = (
            "import sys, html2md, html2md.acquire, html2md.clean, "
            "html2md.core_bridge, html2md.emit;"
            "bad=[m for m in ('httpx','trafilatura','playwright','weasyprint') "
            "if m in sys.modules];"
            "assert not bad, bad; print('OK')"
        )
        r = subprocess.run([sys.executable, "-c", code], cwd=SCRIPTS,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK", r.stdout)

    def test_web_clean_no_weasyprint_no_playwright(self):
        """TC-UNIT-02 (G-2): the __init__.py trap — import the real leaf modules and
        assert weasyprint/playwright stay out of sys.modules (ARCH §9 G-2)."""
        code = (
            "import sys, web_clean.archives, web_clean.reader_mode;"
            "assert 'weasyprint' not in sys.modules, 'weasyprint leaked';"
            "assert 'playwright' not in sys.modules, 'playwright leaked';"
            "print('OK')"
        )
        r = subprocess.run([sys.executable, "-c", code], cwd=SCRIPTS,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK", r.stdout)


class TestFrozenSurface(unittest.TestCase):
    def test_exit_constants_locked(self):
        """TC-UNIT-03: exit-code map + attach-dir default + exception CODEs."""
        self.assertEqual(
            (cli._EXIT_OK, cli._EXIT_USAGE, cli._EXIT_ENGINE,
             cli._EXIT_SELF_OVERWRITE, cli._EXIT_FETCH),
            (0, 2, 3, 6, 10),
        )
        self.assertEqual(cli._DEFAULT_ATTACH_DIR, "_attachments")
        self.assertEqual(BadInput.CODE, 1)
        self.assertEqual(EngineNotInstalled.CODE, 3)
        self.assertEqual(SelfOverwriteRefused.CODE, 6)
        self.assertEqual(FetchFailed.CODE, 10)
        self.assertEqual(InternalError.CODE, 1)

    def test_argparse_defaults(self):
        """TC-UNIT-04: frozen argparse defaults."""
        args = cli.build_parser().parse_args(["x.html"])
        self.assertEqual(args.engine, "auto")
        self.assertIs(args.reader, True)
        self.assertIs(args.download_images, True)
        self.assertEqual(args.attachments_dir, "_attachments")
        self.assertEqual(args.archive_frame, "main")
        self.assertIs(args.stdout, False)
        self.assertIsNone(args.max_bytes)

    def test_no_reader_and_no_download_flags(self):
        """TC-UNIT-04b: the mutually-exclusive toggles flip the defaults."""
        args = cli.build_parser().parse_args(
            ["x.html", "--no-reader", "--no-download-images"])
        self.assertIs(args.reader, False)
        self.assertIs(args.download_images, False)


class TestPathGuards(unittest.TestCase):
    def test_url_vs_path_dispatch(self):
        """TC-UNIT-07: http(s) → url mode (no stat); local path → local mode."""
        args = cli.build_parser().parse_args(["https://example.com/a", "--stdout"])
        ref, mode, out, stdout_mode = cli._resolve_paths(args)
        self.assertEqual(mode, "url")
        self.assertEqual(ref, "https://example.com/a")
        self.assertTrue(stdout_mode)

    def test_input_not_found(self):
        """TC-UNIT-06: missing local input → exit 1, BadInput envelope."""
        buf = io.StringIO()
        with redirect_stderr(buf):
            rc = cli.main(["does-not-exist.html", "out_dir", "--json-errors"])
        self.assertEqual(rc, 1)
        self.assertIn('"type": "BadInput"', buf.getvalue())
        self.assertIn('"v": 1', buf.getvalue())

    def test_self_overwrite_guard(self):
        """TC-UNIT-05: OUTPUT_DIR resolving to the INPUT file → exit 6."""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "page.html"
            src.write_text("<html><body>x</body></html>", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stderr(buf):
                rc = cli.main([str(src), str(src), "--json-errors"])
            self.assertEqual(rc, 6)
            self.assertIn('"type": "SelfOverwriteRefused"', buf.getvalue())

    def test_main_converts_valid_local_input(self):
        """TC-UNIT-09: valid local html + fresh OUTPUT_DIR → exit 0 + a .md written."""
        if not shutil.which("node"):
            self.skipTest("node not installed")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "page.html"
            src.write_text(
                "<html><head><title>T</title></head><body><h1>Hi</h1>"
                "<p>hello world</p></body></html>", encoding="utf-8")
            out = Path(d) / "out"
            rc = cli.main([str(src), str(out)])
            self.assertEqual(rc, 0)
            self.assertTrue(list(out.glob("*.md")), "no .md written")


class TestModel(unittest.TestCase):
    def test_ir_dataclasses_frozen(self):
        """TC-UNIT-08: IR dataclasses are frozen + readable."""
        acq = AcquireResult(html="<p>x</p>", base_url="file:///t", mode="file")
        cr = CleanResult(whole_html="x", reader_html=None)
        self.assertEqual(acq.mode, "file")
        self.assertIsNone(cr.reader_html)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            acq.mode = "url"  # type: ignore[misc]


class TestTask023Surface(unittest.TestCase):
    """TASK 023 frozen CLI/IR surface (bead 023-01)."""

    def _clean_env(self):
        for k in ("HTML2MD_READER_URL", "HTML2MD_READER_PROVIDERS",
                  "HTML2MD_SEARCH_URL", "HTML2MD_SEARCH_PROVIDERS"):
            os.environ.pop(k, None)

    def test_parser_accepts_new_flags(self):
        """TC-01-01: every new flag parses with the expected value."""
        a = cli.build_parser().parse_args([
            "https://x.com", "out", "--engine", "remote", "--no-remote",
            "--remote-format", "markdown", "--target-selector", ".content",
            "--max-results", "3",
        ])
        self.assertEqual(a.engine, "remote")
        self.assertIs(a.no_remote, True)
        self.assertEqual(a.remote_format, "markdown")
        self.assertEqual(a.target_selector, ".content")
        self.assertEqual(a.max_results, 3)
        b = cli.build_parser().parse_args(["--search", "berachain ibgt"])
        self.assertEqual(b.search, "berachain ibgt")
        # defaults
        d = cli.build_parser().parse_args(["x.html"])
        self.assertIs(d.no_remote, False)
        self.assertEqual(d.remote_format, "html")
        self.assertIsNone(d.target_selector)
        self.assertIsNone(d.search)
        self.assertEqual(d.max_results, 5)

    def test_search_input_mutual_exclusion(self):
        """TC-01-02: --search + a URL positional → exit 2 (Usage)."""
        buf = io.StringIO()
        with redirect_stderr(buf):
            rc = cli.main(["--search", "q", "https://example.com", "--json-errors"])
        self.assertEqual(rc, 2)
        self.assertIn('"type": "Usage"', buf.getvalue())

    def test_acquireresult_new_fields(self):
        """TC-01-03: AcquireResult defaults content_kind='html', markdown=None."""
        acq = AcquireResult(html="<p>x</p>")
        self.assertEqual(acq.content_kind, "html")
        self.assertIsNone(acq.markdown)
        acq2 = AcquireResult(html="", content_kind="markdown", markdown="# hi")
        self.assertEqual(acq2.content_kind, "markdown")
        self.assertEqual(acq2.markdown, "# hi")

    def test_engine_remote_requires_config(self):
        """TC-01-07: --engine remote with no reader env → exit 2 (not a jina fall-back)."""
        self._clean_env()
        rc = cli.main(["https://x.com", "out", "--engine", "remote"])
        self.assertEqual(rc, 2)

    def test_max_results_must_be_positive(self):
        """TC-01-08: --max-results <= 0 → exit 2."""
        self.assertEqual(cli.main(["x.html", "--max-results", "0"]), 2)
        self.assertEqual(cli.main(["x.html", "--max-results", "-1"]), 2)

    def test_frontmatter_engine_field(self):
        """TC-01-10 (AC-R6): frontmatter records the real engine + query; offline → no engine."""
        from html2md import emit
        from html2md.model import SourceMeta
        fm = emit._frontmatter(SourceMeta(url="https://x.com"), query="q", engine="jina")
        self.assertIn('engine: "jina"', fm)
        self.assertIn('query: "q"', fm)
        self.assertIn('source: "https://x.com"', fm)
        off = emit._frontmatter(SourceMeta(url="file:///t"))
        self.assertNotIn("engine:", off)  # offline (engine=None) → no engine line

    def test_search_outputdir_resolution(self):
        """TC-01-09: --search resolves OUTPUT_DIR without an INPUT-required error."""
        a = cli.build_parser().parse_args(["--search", "q"])
        out, stdout_mode = cli._resolve_search_paths(a)
        self.assertFalse(stdout_mode)
        self.assertTrue(str(out).endswith(os.path.join("tmp", "html2md_out")))
        b = cli.build_parser().parse_args(["--search", "q", "mydir"])
        out_b, _ = cli._resolve_search_paths(b)
        self.assertTrue(str(out_b).endswith("mydir"))
        c = cli.build_parser().parse_args(["--search", "q", "--stdout"])
        out_c, stdout_c = cli._resolve_search_paths(c)
        self.assertIsNone(out_c)
        self.assertTrue(stdout_c)


if __name__ == "__main__":
    unittest.main()

"""OP2 `html md` + the combined `html2md` command + round-trip safety (TASK 027):
sidecar-hydrated frontmatter, no-leftover-HTML cleanup, self-overwrite refusal, and
stale `.reader.md` cleanup.

Run from ``skills/html/scripts``:  python -m unittest discover -s html2md/tests
"""
import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import cli, emit, naming  # noqa: E402
from html2md.exceptions import SelfOverwriteRefused  # noqa: E402
from html2md.model import AcquireResult, SourceMeta  # noqa: E402


def _emit_opts(**kw):
    base = dict(download_images=False, attachments_dir="_attachments", max_images=None,
                reader=True)
    base.update(kw)
    return argparse.Namespace(**base)


class TestMdVerbSidecar(unittest.TestCase):
    def test_md_prefers_sidecar_over_html_derived_meta(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            # An artifact whose sidecar source/title differ from anything in the HTML, so a
            # pass proves the sidecar was used (not re-derived from the local file).
            (out / "x.html").write_text(
                "<html><head><title>HTML Title</title></head>"
                "<body><h1>HTML Title</h1><p>plenty of body text for substance</p>"
                "</body></html>", encoding="utf-8")
            (out / "x.meta.json").write_text(json.dumps({
                "schema": "html/fetch-artifact@1", "source": "https://real.example/x",
                "title": "Sidecar Title", "date": "2025-09-09", "author": "Sidecar Author",
                "engine": "lite", "content_kind": "html"}), encoding="utf-8")
            rc = cli.main(["md", str(out / "x.html"), str(out), "--json-errors"])
            self.assertEqual(rc, 0)
            md = (out / "x.md").read_text()
            self.assertIn('source: "https://real.example/x"', md)
            self.assertIn('title: "Sidecar Title"', md)
            self.assertIn('engine: "lite"', md)

    def test_md_no_sidecar_uses_html_meta(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "hand.html").write_text(
                "<html><head><title>Hand Title</title></head>"
                "<body><p>plenty of body text for substance here</p></body></html>",
                encoding="utf-8")
            rc = cli.main(["md", str(out / "hand.html"), str(out)])
            self.assertEqual(rc, 0)
            self.assertIn('title: "Hand Title"', (out / "hand.md").read_text())


class TestCombined(unittest.TestCase):
    def test_combined_leaves_no_intermediate_html(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.html"
            src.write_text("<html><head><title>C</title></head>"
                           "<body><h1>C</h1><p>plenty of body text for substance</p>"
                           "</body></html>", encoding="utf-8")
            out = Path(d) / "out"
            rc = cli.combined_main([str(src), str(out)])
            self.assertEqual(rc, 0)
            names = sorted(p.name for p in out.iterdir())
            self.assertIn("in.md", names)
            self.assertNotIn("in.html", names)        # intermediate HTML deleted
            self.assertNotIn("in.meta.json", names)   # sidecar deleted

    def test_combined_validates_before_search_dispatch(self):
        # combined_main must run _validate_usage BEFORE the --search branch, so the
        # security guard "--chrome-* auth cannot be combined with --search" still fires.
        rc = cli.combined_main(["--search", "kubernetes", "--chrome-storage-state",
                                "/secrets/x.json", "--json-errors"])
        self.assertEqual(rc, 2)  # Usage, not a silently-bypassed search


class TestSelfOverwriteGuard(unittest.TestCase):
    def test_emit_refuses_output_equals_input(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            # input_ref resolves to <out>/x.md ⇒ the emitted <slug>.md would clobber it.
            # Seed the file with OUR provenance marker so resolve_base reuses base "x"
            # (its idempotent-overwrite branch) and out_md == input_ref → the guard fires.
            target = out / "x.md"
            marker = naming.src_marker(str(target))
            target.write_text("body\n\n" + marker + "\n", encoding="utf-8")
            acq = AcquireResult(html="<p>x</p>", base_url="", mode="file",
                                source_meta=SourceMeta())
            with self.assertRaises(SelfOverwriteRefused):
                emit.emit(acq, None, "body", None, _emit_opts(),
                          output_dir=out, stdout_mode=False, input_ref=str(target))


class TestStaleReaderCleanup(unittest.TestCase):
    def test_no_reader_rerun_removes_stale_reader_md(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            acq = AcquireResult(html="<p>x</p>", base_url="", mode="file",
                                source_meta=SourceMeta())  # url=None ⇒ marker keys on input_ref
            ref = str(out / "page.input")
            # 1) emit WITH reader → page.md + page.reader.md
            emit.emit(acq, None, "whole", "reader text", _emit_opts(),
                      output_dir=out, stdout_mode=False, input_ref=ref)
            self.assertTrue((out / "page.reader.md").is_file())
            # 2) re-emit SAME input with --no-reader → the stale reader variant is removed
            emit.emit(acq, None, "whole", None, _emit_opts(),
                      output_dir=out, stdout_mode=False, input_ref=ref)
            self.assertTrue((out / "page.md").is_file())
            self.assertFalse((out / "page.reader.md").exists())


class TestReaderOnly(unittest.TestCase):
    def _ro_opts(self, **kw):
        base = dict(download_images=False, attachments_dir="_attachments", max_images=None,
                    reader=True, reader_only=True)
        base.update(kw)
        return argparse.Namespace(**base)

    def test_single_md_is_reader_and_no_reader_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            acq = AcquireResult(html="<p>x</p>", base_url="", mode="file",
                                source_meta=SourceMeta(url="https://e/x"))
            emit.emit(acq, None, "WHOLE PAGE BODY with nav chrome",
                      "READER EXTRACTED ARTICLE BODY " * 10, self._ro_opts(),
                      output_dir=out, stdout_mode=False, input_ref="https://e/x")
            mds = sorted(out.glob("*.md"))
            self.assertEqual(len(mds), 1, "reader-only must write exactly one .md")
            self.assertFalse(mds[0].name.endswith(".reader.md"))
            body = mds[0].read_text()
            self.assertIn("READER EXTRACTED ARTICLE BODY", body)
            self.assertNotIn("WHOLE PAGE BODY", body)

    def test_falls_back_to_whole_when_reader_empty(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            acq = AcquireResult(html="<p>x</p>", base_url="", mode="file",
                                source_meta=SourceMeta(url="https://e/y"))
            # reader over-stripped to a tiny body (< _READER_ONLY_MIN_BODY) ⇒ fall back to whole
            emit.emit(acq, None, "SUBSTANTIAL WHOLE PAGE BODY " * 20, "tiny", self._ro_opts(),
                      output_dir=out, stdout_mode=False, input_ref="https://e/y")
            mds = sorted(out.glob("*.md"))
            self.assertEqual(len(mds), 1)
            self.assertFalse(mds[0].name.endswith(".reader.md"))
            self.assertIn("SUBSTANTIAL WHOLE PAGE BODY", mds[0].read_text(),
                          "empty reader must fall back to the whole page — never an empty note")

    def test_reader_only_removes_stale_reader_md(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            acq = AcquireResult(html="<p>x</p>", base_url="", mode="file",
                                source_meta=SourceMeta())  # url=None ⇒ marker keys on input_ref
            ref = str(out / "page.input")
            # 1) dual-output run leaves page.md + page.reader.md
            emit.emit(acq, None, "whole", "reader body " * 30,
                      argparse.Namespace(download_images=False, attachments_dir="_attachments",
                                         max_images=None, reader=True, reader_only=False),
                      output_dir=out, stdout_mode=False, input_ref=ref)
            self.assertTrue((out / "page.reader.md").is_file())
            # 2) reader-only re-run of the same input drops the stale .reader.md
            emit.emit(acq, None, "whole", "reader body " * 30, self._ro_opts(),
                      output_dir=out, stdout_mode=False, input_ref=ref)
            self.assertTrue((out / "page.md").is_file())
            self.assertFalse((out / "page.reader.md").exists())

    def test_cli_md_reader_only_one_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "art.html").write_text(
                "<html><head><title>T</title></head><body><nav>Home Menu Copy</nav>"
                "<article><h1>Real Title</h1><p>" + ("Substantial article body sentence. " * 20)
                + "</p></article></body></html>", encoding="utf-8")
            rc = cli.main(["md", str(out / "art.html"), str(out), "--reader-only", "--json-errors"])
            self.assertEqual(rc, 0)
            self.assertEqual(len(list(out.glob("art.md"))), 1)
            self.assertEqual(len(list(out.glob("*.reader.md"))), 0)


if __name__ == "__main__":
    unittest.main()

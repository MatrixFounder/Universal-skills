"""Bead 020-05 — ocr.py: tesseract probe + per-image subprocess OCR."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from PIL import Image

from pptx2md import cli, images, ocr
from pptx2md.exceptions import LanguagePackMissing, OcrEngineUnavailable
from pptx2md.tests._fixtures import (
    build_deck_with_duplicate_image,
    build_deck_with_two_images,
    build_minimal_deck,
)

_TMP8 = _SCRIPTS.parents[2] / "tmp8"
_HAS_TESSERACT = shutil.which("tesseract") is not None


def _png_blob() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (24, 24), (255, 255, 255)).save(buf, "PNG")
    return buf.getvalue()


def _run(argv):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        code = cli.main(argv)
    return code, err.getvalue()


class TestProbe(unittest.TestCase):
    def test_probe_missing_engine(self):
        with mock.patch.object(ocr.shutil, "which", return_value=None):
            with self.assertRaises(OcrEngineUnavailable):
                ocr.probe("eng+rus")

    def test_probe_missing_lang_dual_stream(self):
        # eng installed, rus not → LanguagePackMissing naming rus. Verify the parse
        # works whether --list-langs prints to stdout OR stderr.
        for stream in ("stdout", "stderr"):
            payload = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="List of available languages\neng\n" if stream == "stdout" else "",
                stderr="List of available languages\neng\n" if stream == "stderr" else "",
            )
            with mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
                 mock.patch.object(ocr.subprocess, "run", return_value=payload):
                with self.assertRaises(LanguagePackMissing) as ctx:
                    ocr.probe("eng+rus")
                self.assertIn("rus", str(ctx.exception))

    def test_probe_empty_lang(self):
        with mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"):
            with self.assertRaises(LanguagePackMissing):
                ocr.probe("")


class TestOcrAsset(unittest.TestCase):
    def test_argv_is_list_no_shell(self):
        captured = {}

        def fake_run(argv, **kw):
            captured["argv"] = argv
            captured["shell"] = kw.get("shell", False)
            return subprocess.CompletedProcess(argv, 0, stdout="HELLO", stderr="")

        with mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
             mock.patch.object(ocr.subprocess, "run", side_effect=fake_run):
            out = ocr.ocr_asset(_png_blob(), "eng", 30.0)
        self.assertEqual(out, "HELLO")
        self.assertIsInstance(captured["argv"], list)
        self.assertEqual(captured["argv"][0], "/usr/bin/tesseract")
        self.assertIn("stdout", captured["argv"])
        self.assertFalse(captured["shell"])

    def test_empty_result_no_marker(self):
        def fake_run(argv, **kw):
            return subprocess.CompletedProcess(argv, 0, stdout="   \n  ", stderr="")

        with mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
             mock.patch.object(ocr.subprocess, "run", side_effect=fake_run):
            self.assertEqual(ocr.ocr_asset(_png_blob(), "eng", 30.0), "")

    def test_timeout_warns_continues(self):
        def fake_run(argv, **kw):
            raise subprocess.TimeoutExpired(argv, kw.get("timeout"))

        err = io.StringIO()
        with mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
             mock.patch.object(ocr.subprocess, "run", side_effect=fake_run), \
             contextlib.redirect_stderr(err):
            self.assertEqual(ocr.ocr_asset(_png_blob(), "eng", 5.0), "")
        self.assertIn("timed out", err.getvalue())

    def test_unreadable_blob_returns_empty(self):
        with mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(ocr.ocr_asset(b"not an image", "eng", 5.0), "")

    def test_decompression_bomb_band_skips_via_size_guard(self):
        # vdd-multi INFO-1: an over-threshold (warn-band+) image is rejected by the
        # THREAD-LOCAL header-size check BEFORE the full-decode .save() → "" (skip),
        # never a memory blow-up. (Thread-local, not warnings.catch_warnings — so it
        # is race-free under --jobs>1; see test_jobs_parallel_real_bomb_guard.)
        big = mock.MagicMock()
        big.size = (10 ** 5, 10 ** 5)  # 10^10 px ≫ Image.MAX_IMAGE_PIXELS → bomb
        with mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
             mock.patch("PIL.Image.open", return_value=big), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ocr.ocr_asset(b"x", "eng", 5.0), "")
        big.save.assert_not_called()  # rejected before the full-decode .save()


class TestRasteriseVector(unittest.TestCase):
    """images.rasterise_vector — soffice WMF/EMF → PNG bytes (shared by materialise + ocr)."""

    def test_non_vector_format_returns_none(self):
        # a raster format (e.g. a decompression-bomb PNG) must NOT invoke soffice.
        self.assertIsNone(images.rasterise_vector(b"x", "PNG", 60))
        self.assertIsNone(images.rasterise_vector(b"x", "", 60))

    def test_soffice_absent_returns_none(self):
        import _soffice
        with mock.patch.object(_soffice, "find_soffice",
                               side_effect=_soffice.SofficeError("not installed")):
            self.assertIsNone(images.rasterise_vector(b"wmf", "WMF", 60))

    def test_wmf_success_returns_png_bytes(self):
        import _soffice

        def fake_convert(src, out_dir, target, *, timeout=180):
            p = Path(out_dir) / f"{Path(src).stem}.{target}"
            p.write_bytes(b"\x89PNG-rendered")
            return p

        with mock.patch.object(_soffice, "find_soffice", return_value="/x/soffice"), \
             mock.patch.object(_soffice, "convert_to", side_effect=fake_convert):
            self.assertEqual(images.rasterise_vector(b"wmfbytes", "WMF", 60),
                             b"\x89PNG-rendered")

    def test_conversion_failure_returns_none(self):
        import _soffice
        with mock.patch.object(_soffice, "find_soffice", return_value="/x/soffice"), \
             mock.patch.object(_soffice, "convert_to",
                               side_effect=_soffice.SofficeError("boom")):
            self.assertIsNone(images.rasterise_vector(b"wmf", "WMF", 60))

    def test_runtime_warning_does_not_escape(self):
        # AR-1: _soffice.run can surface a RuntimeWarning (macOS hardened-shim path);
        # under a RuntimeWarning-as-error filter it is raised. The bare except must
        # catch it → None, never raising.
        import warnings

        import _soffice

        def warn_then_fail(src, out_dir, target, *, timeout=180):
            warnings.warn("hardened shim", RuntimeWarning)  # → raised under the filter
            raise AssertionError("unreachable under error filter")

        with mock.patch.object(_soffice, "find_soffice", return_value="/x/soffice"), \
             mock.patch.object(_soffice, "convert_to", side_effect=warn_then_fail), \
             warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            self.assertIsNone(images.rasterise_vector(b"wmf", "WMF", 60))

    def test_ocr_asset_uses_rasterise_for_wmf(self):
        # When Pillow can't .save() a WMF, ocr_asset routes to rasterise_vector, writes
        # the returned PNG bytes to the temp, then OCRs it. Mock Pillow + the helper.
        from PIL import Image as PILImage

        bad_img = mock.MagicMock()
        bad_img.format = "WMF"
        bad_img.size = (100, 100)
        bad_img.save.side_effect = OSError("cannot find loader for this WMF file")

        def fake_run(argv, **kw):
            return subprocess.CompletedProcess(argv, 0, stdout="WMF TEXT", stderr="")

        with mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
             mock.patch.object(PILImage, "open", return_value=bad_img), \
             mock.patch.object(ocr, "rasterise_vector", return_value=b"\x89PNGbytes"), \
             mock.patch.object(ocr.subprocess, "run", side_effect=fake_run):
            self.assertEqual(ocr.ocr_asset(b"wmfblob", "eng", 60), "WMF TEXT")


class TestOcrPipeline(unittest.TestCase):
    def test_engine_absent_fails_loud_only_with_ocr(self):
        with tempfile.TemporaryDirectory() as d:
            deck = build_minimal_deck(Path(d) / "m.pptx")
            out = Path(d) / "out.md"
            # Without --ocr: converts fine even with no engine (R-C1d / I-3).
            with mock.patch.object(ocr.shutil, "which", return_value=None):
                code, _ = _run([str(deck), str(out)])
                self.assertEqual(code, 0)
                # With --ocr + no engine: exit 1 OcrEngineUnavailable, no partial.
                out2 = Path(d) / "out2.md"
                code2, err2 = _run([str(deck), str(out2), "--ocr", "--json-errors"])
            self.assertEqual(code2, 1)
            self.assertEqual(
                json.loads(err2.strip().splitlines()[-1])["type"], "OcrEngineUnavailable")
            self.assertFalse(out2.exists())

    def test_jobs_parallel_branch_two_distinct_images(self):
        # R-D2e: --jobs>1 parallel OCR over 2 DISTINCT images — both OCR'd, exit 0,
        # and output byte-identical to the serial run (I-1 determinism under threads).
        with tempfile.TemporaryDirectory() as d:
            deck = build_deck_with_two_images(Path(d) / "two.pptx")
            out = Path(d) / "out.md"  # SAME path both runs (media dir identical)
            # give each distinct blob a distinct OCR text so ordering is observable.
            def _fake(b, l, t, **kw):  # **kw: tolerate the denoise kwargs (TASK 021)
                return f"OCR:{len(b)}"
            with mock.patch.object(ocr, "probe"), \
                 mock.patch.object(ocr, "ocr_asset", side_effect=_fake):
                code_s, _ = _run([str(deck), str(out), "--ocr", "--jobs", "1"])
            serial = out.read_text()
            with mock.patch.object(ocr, "probe"), \
                 mock.patch.object(ocr, "ocr_asset", side_effect=_fake) as mp:
                code_p, _ = _run([str(deck), str(out), "--ocr", "--jobs", "2"])
            self.assertEqual((code_s, code_p), (0, 0))
            self.assertEqual(mp.call_count, 2, "both distinct blobs OCR'd in parallel")
            self.assertEqual(serial, out.read_text(),
                             "--jobs 2 output must equal --jobs 1 (determinism)")

    def test_jobs_parallel_real_bomb_guard(self):
        # Drive the REAL ocr_asset under --jobs 2 (no ocr_asset mock): lower
        # Image.MAX_IMAGE_PIXELS so BOTH distinct images trip the thread-local size
        # guard → both skipped (no tesseract call), exit 0, no OCR blocks. Locks that
        # the bomb guard is race-free under parallelism (the prior catch_warnings
        # approach was not). No real tesseract needed — the guard fires first.
        from PIL import Image as PILImage

        with tempfile.TemporaryDirectory() as d:
            deck = build_deck_with_two_images(Path(d) / "two.pptx")
            out = Path(d) / "out.md"
            orig = PILImage.MAX_IMAGE_PIXELS
            try:
                PILImage.MAX_IMAGE_PIXELS = 10  # 32x32 = 1024 px > 10 → both trip
                with mock.patch.object(ocr, "probe"), \
                     mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
                     contextlib.redirect_stderr(io.StringIO()):
                    code, _ = _run([str(deck), str(out), "--ocr", "--jobs", "2"])
            finally:
                PILImage.MAX_IMAGE_PIXELS = orig
            self.assertEqual(code, 0)
            self.assertNotIn("<!-- ocr -->", out.read_text())

    def test_ocr_dedup_cache_one_call_per_unique_blob(self):
        # Same blob on 2 slides + --ocr → ocr_asset invoked ONCE (R-C4d).
        with tempfile.TemporaryDirectory() as d:
            deck = build_deck_with_duplicate_image(Path(d) / "dup.pptx")[0]
            out = Path(d) / "out.md"
            with mock.patch.object(ocr, "probe"), \
                 mock.patch.object(ocr, "ocr_asset", return_value="TXT") as m:
                code, _ = _run([str(deck), str(out), "--ocr"])
            self.assertEqual(code, 0)
            self.assertEqual(m.call_count, 1, "deduped blob must be OCR'd once")
            self.assertIn("<!-- ocr -->", out.read_text())


@unittest.skipUnless(_HAS_TESSERACT and (_TMP8 / "slides-5.pptx").exists(),
                     "tesseract or tmp8/slides-5.pptx absent")
class TestOcrDogfoodImageOnly(unittest.TestCase):
    def test_ocr_on_image_only_deck(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "slides5.md"
            code, _ = _run([str(_TMP8 / "slides-5.pptx"), str(out), "--ocr"])
            self.assertEqual(code, 0)
            # Image-only deck: real tesseract should recover SOME text → an OCR block.
            # (If the image genuinely has no text, this asserts at least a clean run.)
            text = out.read_text()
            self.assertIn("## Slide 1", text)


if __name__ == "__main__":
    unittest.main()

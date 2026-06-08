"""TASK 021 — `--ocr-denoise`: size-gate (R1), confidence-gate (R2), dedup (R3).

Every filter is OPT-IN; the default path is covered (unchanged) by the rest of the
suite. These tests drive the denoise branches directly and assert (a) the noise is
removed and (b) real text / non-OCR output is never touched.
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from PIL import Image

from pptx2md import emit, model, ocr


def _img_blob(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 255, 255)).save(buf, "PNG")
    return buf.getvalue()


_TSV_HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
    "left\ttop\twidth\theight\tconf\ttext"
)


def _tsv(words) -> str:
    """Build a tesseract-shaped TSV from (block, par, line, conf, text) tuples."""
    rows = [_TSV_HEADER]
    for i, (block, par, line, conf, text) in enumerate(words, start=1):
        rows.append(
            f"5\t1\t{block}\t{par}\t{line}\t{i}\t0\t0\t10\t10\t{conf}\t{text}"
        )
    return "\n".join(rows) + "\n"


def _fake_proc(stdout: str, rc: int = 0):
    return mock.Mock(returncode=rc, stdout=stdout, stderr="")


# --------------------------------------------------------------------------- #
# R1 — size-gate
# --------------------------------------------------------------------------- #
class TestSizeGate(unittest.TestCase):
    def test_tiny_image_skipped_under_denoise(self):
        # 24x24 < min_px 48 → no tesseract call, "" returned.
        with mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
             mock.patch.object(ocr.subprocess, "run") as mrun:
            out = ocr.ocr_asset(_img_blob(24, 24), "eng", 5.0, denoise=True, min_px=48)
        self.assertEqual(out, "")
        mrun.assert_not_called()

    def test_large_image_runs_under_denoise(self):
        # 100x100 >= min_px → tesseract IS invoked (in tsv mode).
        with mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
             mock.patch.object(ocr.subprocess, "run",
                               return_value=_fake_proc(
                                   _tsv([(1, 1, 1, 90, "Hi"), (1, 1, 1, 88, "there")]))) as mrun:
            out = ocr.ocr_asset(_img_blob(100, 100), "eng", 5.0, denoise=True, min_px=48)
        self.assertEqual(out, "Hi there")
        mrun.assert_called_once()
        # tsv config requested under denoise; outputbase stays "stdout"
        self.assertIn("tsv", mrun.call_args.args[0])
        self.assertIn("stdout", mrun.call_args.args[0])

    def test_tiny_image_NOT_skipped_without_denoise(self):
        # Default path: the size-gate is inert — a 24x24 image is still OCR'd (stdout).
        with mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
             mock.patch.object(ocr.subprocess, "run",
                               return_value=_fake_proc("plain text")) as mrun:
            out = ocr.ocr_asset(_img_blob(24, 24), "eng", 5.0)  # denoise=False
        self.assertEqual(out, "plain text")
        mrun.assert_called_once()
        self.assertIn("stdout", mrun.call_args.args[0])

    def test_small_wmf_NOT_size_gated(self):
        # critic-logic MED-1: Pillow OPENS a WMF and exposes a tiny logical .size, but
        # the diagram is full-size once rendered. A WMF/EMF must be EXEMPT from the
        # size-gate (else a real diagram is silently dropped). Here the 20x20 WMF must
        # reach the vector fallback + OCR, NOT be size-gated to "".
        fake_wmf = mock.Mock()
        fake_wmf.size = (20, 20)          # tiny logical units < min_px 48
        fake_wmf.format = "WMF"
        fake_wmf.save.side_effect = OSError("cannot find loader for this WMF file")
        tsv = _tsv([(1, 1, 1, 90, "Diagram"), (1, 1, 1, 88, "label")])
        with mock.patch("PIL.Image.open", return_value=fake_wmf), \
             mock.patch.object(ocr, "rasterise_vector", return_value=b"PNGdata") as mras, \
             mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
             mock.patch.object(ocr.subprocess, "run", return_value=_fake_proc(tsv)):
            out = ocr.ocr_asset(b"wmfblob", "eng", 60, denoise=True, min_px=48)
        self.assertEqual(out, "Diagram label")  # rendered + OCR'd, not size-gated
        mras.assert_called_once()  # the vector fallback was reached


# --------------------------------------------------------------------------- #
# R2 — confidence-gate (_filter_tsv is a pure function)
# --------------------------------------------------------------------------- #
class TestFilterTsv(unittest.TestCase):
    def test_high_confidence_block_kept_full(self):
        tsv = _tsv([
            (1, 1, 1, 95, "Hello"),
            (1, 1, 1, 92, "World"),
            (1, 1, 2, 88, "second"),
            (1, 1, 2, 90, "line"),
        ])
        self.assertEqual(ocr._filter_tsv(tsv, 50.0), "Hello World\nsecond line")

    def test_low_confidence_block_dropped(self):
        # All words below threshold → 0 survivors < 2 → "" (the N2 noise class).
        tsv = _tsv([(1, 1, 1, 10, "io"), (1, 1, 1, 14, "GSiercicne")])
        self.assertEqual(ocr._filter_tsv(tsv, 50.0), "")

    def test_single_confident_word_dropped_as_noise(self):
        # The real-data discriminator: a noise banner had exactly ONE word >= 50.
        # One confident word (< min_words 2) → dropped.
        tsv = _tsv([(1, 1, 1, 88, "Лого"), (1, 1, 1, 12, "io"), (1, 1, 1, 8, "x")])
        self.assertEqual(ocr._filter_tsv(tsv, 50.0), "")

    def test_paragraph_boundary_inserts_blank_line(self):
        tsv = _tsv([
            (1, 1, 1, 90, "para1"),
            (1, 2, 1, 90, "para2"),  # par_num changed → blank line between
        ])
        self.assertEqual(ocr._filter_tsv(tsv, 50.0), "para1\n\npara2")

    def test_low_conf_garble_stripped_inside_real_block(self):
        # A real (multi-confident-word) block keeps its high-conf words and DROPS the
        # low-conf garble in between — the within-block cleaning behaviour.
        tsv = _tsv([
            (1, 1, 1, 95, "good"),
            (1, 1, 1, 20, "Гж"),    # mojibake glyph, conf 20 → stripped
            (1, 1, 1, 92, "text"),
        ])
        self.assertEqual(ocr._filter_tsv(tsv, 50.0), "good text")

    def test_no_word_rows_returns_empty(self):
        self.assertEqual(ocr._filter_tsv(_TSV_HEADER + "\n", 50.0), "")

    def test_conf_minus_one_rows_ignored(self):
        # tesseract emits conf=-1 structural rows with blank text — excluded (and
        # below-threshold). Two real words survive → kept.
        tsv = _tsv([(1, 1, 1, -1, ""), (1, 1, 1, 80, "real"), (1, 1, 1, 75, "text")])
        self.assertEqual(ocr._filter_tsv(tsv, 50.0), "real text")

    # R5 — malformed input never raises
    def test_empty_string(self):
        self.assertEqual(ocr._filter_tsv("", 50.0), "")

    def test_headerless_garbage_returns_empty(self):
        self.assertEqual(ocr._filter_tsv("not a tsv\njust junk\n", 50.0), "")

    def test_short_rows_skipped_not_crash(self):
        tsv = _TSV_HEADER + "\n5\t1\t1\n"  # truncated row → skipped
        self.assertEqual(ocr._filter_tsv(tsv, 50.0), "")

    def test_comma_decimal_conf_parsed(self):
        # critic-logic LOW-1: a non-C LC_NUMERIC host can emit conf with a comma decimal
        # ("88,5") — it must still parse, not silently drop real confident words.
        tsv = (_TSV_HEADER + "\n"
               + "5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t88,5\tHello\n"
               + "5\t1\t1\t1\t1\t2\t0\t0\t10\t10\t90,0\tWorld\n")
        self.assertEqual(ocr._filter_tsv(tsv, 50.0), "Hello World")


# --------------------------------------------------------------------------- #
# R3 — dedup (emit.render_deck)
# --------------------------------------------------------------------------- #
class _DenoiseOpts:
    no_notes = False
    ocr_denoise = True


class _PlainOpts:
    no_notes = False
    ocr_denoise = False


def _deck_three_logo_slides():
    """3 slides, each an ImageRef to its own MediaAsset, all with identical OCR text."""
    refs, assets, ocr_text = [], {}, {}
    for n in (1, 2, 3):
        ref = model.ImageRef(slide=n, shape=1, sha1=f"s{n}", ext="png", alt="logo")
        asset = model.MediaAsset(sha1=f"s{n}", filename=f"slide{n}-img1.png",
                                 rel_path=f"m/slide{n}-img1.png", content_type="image/png")
        refs.append((n, ref))
        assets[ref] = asset
        ocr_text[asset] = "LOGO NOISE"
    deck = model.Deck(slides=[model.Slide(index=n, blocks=[ref]) for n, ref in refs])
    return deck, assets, ocr_text


class TestDedup(unittest.TestCase):
    def test_identical_ocr_emitted_once_under_denoise(self):
        deck, assets, ocr_text = _deck_three_logo_slides()
        md = "".join(emit.render_deck(deck, assets, ocr_text, _DenoiseOpts()))
        # all three image links survive…
        self.assertEqual(md.count("![logo]("), 3)
        # …but the identical OCR block is shown only once.
        self.assertEqual(md.count("<!-- ocr -->"), 1)
        self.assertEqual(md.count("> LOGO NOISE"), 1)

    def test_no_dedup_without_denoise(self):
        deck, assets, ocr_text = _deck_three_logo_slides()
        md = "".join(emit.render_deck(deck, assets, ocr_text, _PlainOpts()))
        self.assertEqual(md.count("![logo]("), 3)
        self.assertEqual(md.count("<!-- ocr -->"), 3)  # default: every block emitted

    def test_distinct_ocr_not_deduped(self):
        # Different OCR text on each slide → all kept even under denoise.
        deck, assets, ocr_text = _deck_three_logo_slides()
        for i, a in enumerate(ocr_text):
            ocr_text[a] = f"distinct {i}"
        md = "".join(emit.render_deck(deck, assets, ocr_text, _DenoiseOpts()))
        self.assertEqual(md.count("<!-- ocr -->"), 3)


if __name__ == "__main__":
    unittest.main()

"""Bead 020-03 — images.materialise: sidecar extraction, sha1 dedup, link base."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from pptx2md import extract, images, model
from pptx2md.tests._fixtures import (
    build_deck_with_duplicate_image,
    build_deck_with_jpeg,
    build_minimal_deck,
)


class _Opts:
    include_hidden = False


def _build(path):
    return extract.build_deck(extract.open_deck(Path(path)), _Opts())


class TestMaterialise(unittest.TestCase):
    def test_dedup_first_occurrence_wins(self):
        # Same blob on slides 1 and 2 → exactly ONE file; both refs share the name.
        with tempfile.TemporaryDirectory() as d:
            p, _blob = build_deck_with_duplicate_image(Path(d) / "dup.pptx")
            deck = _build(p)
            media = Path(d) / "out.media"
            assets = images.materialise(deck, media, "out.media")

            img_refs = [b for s in deck.slides for b in s.blocks if isinstance(b, model.ImageRef)]
            self.assertEqual(len(img_refs), 2)
            names = {assets[r].filename for r in img_refs}
            self.assertEqual(len(names), 1, "duplicate blob must yield one canonical file")
            files = list(media.glob("*"))
            self.assertEqual(len(files), 1, "exactly one file on disk")
            # canonical name is the first occurrence (slide 1).
            self.assertTrue(next(iter(names)).startswith("slide1-img1."))

            # Determinism: materialise the SAME deck again → identical filename
            # (re-run materialise, not re-parse — targets materialise determinism).
            media2 = Path(d) / "out2.media"
            assets2 = images.materialise(deck, media2, "out2.media")
            names2 = {assets2[r].filename for r in img_refs}
            self.assertEqual(names, names2)

    def test_no_images_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            p, _ = build_deck_with_duplicate_image(Path(d) / "dup.pptx")
            deck = _build(p)
            media = Path(d) / "out.media"
            assets = images.materialise(deck, media, "out.media", no_images=True)
            self.assertEqual(assets, {})
            self.assertFalse(media.exists(), "media dir must not be created with --no-images")

    def test_link_base_joined_posix(self):
        with tempfile.TemporaryDirectory() as d:
            p, _ = build_deck_with_duplicate_image(Path(d) / "dup.pptx")
            deck = _build(p)
            assets = images.materialise(deck, Path(d) / "deck.media", "deck.media")
            rel = next(iter(assets.values())).rel_path
            self.assertTrue(rel.startswith("deck.media/"))
            self.assertNotIn("\\", rel)

    def test_extension_png_and_jpeg(self):
        # PNG → .png, JPEG → .jpg (R-B1c / TC-UNIT-21 — both formats nailed down).
        with tempfile.TemporaryDirectory() as d:
            deck_png = _build(build_deck_with_duplicate_image(Path(d) / "dup.pptx")[0])
            a_png = next(iter(images.materialise(deck_png, Path(d) / "mp", "mp").values()))
            self.assertTrue(a_png.filename.endswith(".png"), a_png.filename)

            deck_jpg = _build(build_deck_with_jpeg(Path(d) / "j.pptx"))
            a_jpg = next(iter(images.materialise(deck_jpg, Path(d) / "mj", "mj").values()))
            self.assertTrue(a_jpg.filename.endswith(".jpg"), a_jpg.filename)

    def test_cwd_relative_link_base_propagates(self):
        # materialise forwards a CWD-relative link base into rel_path (stdout mode).
        with tempfile.TemporaryDirectory() as d:
            deck = _build(build_deck_with_duplicate_image(Path(d) / "dup.pptx")[0])
            assets = images.materialise(deck, Path(d) / "deck.media", "deck.media")
            self.assertTrue(all(a.rel_path.startswith("deck.media/") for a in assets.values()))

    def test_minimal_deck_has_no_images(self):
        with tempfile.TemporaryDirectory() as d:
            deck = _build(build_minimal_deck(Path(d) / "m.pptx"))
            media = Path(d) / "m.media"
            assets = images.materialise(deck, media, "m.media")
            self.assertEqual(assets, {})
            self.assertFalse(media.exists())


class TestVectorRasterise(unittest.TestCase):
    def test_materialise_renders_wmf_to_png(self):
        # A WMF ImageRef → materialise rasterises to PNG (via mocked rasterise_vector):
        # the media file is .png, the link is .png, deck.blobs is updated so OCR reuses
        # the PNG, and the original WMF bytes are NOT written.
        from unittest import mock

        ref = model.ImageRef(slide=1, shape=1, sha1="w", ext="wmf", alt="diagram")
        deck = model.Deck(
            slides=[model.Slide(index=1, blocks=[ref])],
            source_name="t.pptx",
            blobs={"w": (b"WMF-RAW-BYTES", "image/wmf")},
        )
        with tempfile.TemporaryDirectory() as d:
            media = Path(d) / "m"
            with mock.patch.object(images, "rasterise_vector", return_value=b"\x89PNGdata"):
                assets = images.materialise(deck, media, "m")
            asset = assets[ref]
            self.assertTrue(asset.filename.endswith(".png"), asset.filename)
            self.assertTrue(asset.rel_path.endswith(".png"))
            self.assertEqual(asset.content_type, "image/png")
            # PNG written, not the raw WMF
            self.assertEqual((media / asset.filename).read_bytes(), b"\x89PNGdata")
            # deck.blobs updated so --ocr OCRs the PNG (no second soffice call)
            self.assertEqual(deck.blobs["w"], (b"\x89PNGdata", "image/png"))

    def test_materialise_keeps_wmf_when_soffice_absent(self):
        # rasterise_vector returns None (no soffice) → keep the original .wmf.
        from unittest import mock

        ref = model.ImageRef(slide=1, shape=1, sha1="w", ext="wmf", alt="x")
        deck = model.Deck(slides=[model.Slide(index=1, blocks=[ref])],
                          blobs={"w": (b"WMF-RAW", "image/wmf")})
        with tempfile.TemporaryDirectory() as d:
            media = Path(d) / "m"
            with mock.patch.object(images, "rasterise_vector", return_value=None):
                assets = images.materialise(deck, media, "m")
            asset = assets[ref]
            self.assertTrue(asset.filename.endswith(".wmf"), asset.filename)
            self.assertEqual((media / asset.filename).read_bytes(), b"WMF-RAW")


class TestSafeImageMeta(unittest.TestCase):
    def test_unreadable_returns_none(self):
        class _Bad:
            @property
            def image(self):
                raise ValueError("no embedded image")

        self.assertIsNone(images.safe_image_meta(_Bad()))

    def test_decompression_bomb_degrades_not_crash(self):
        # HIGH: DecompressionBombError subclasses Exception (not ValueError) and is
        # raised inside the Pillow-backed .ext/.content_type read — it must degrade
        # to None (→ Placeholder), never crash the deck (AR-1).
        from PIL import Image as PILImage

        class _BombImage:
            blob = b"\x89PNG"
            sha1 = "deadbeef"

            @property
            def ext(self):
                raise PILImage.DecompressionBombError("578396800 pixels")

            @property
            def content_type(self):
                return "image/png"

        class _BombShape:
            image = _BombImage()

        self.assertIsNone(images.safe_image_meta(_BombShape()))


class TestDefensivePlaceholder(unittest.TestCase):
    def test_imageref_without_blob_yields_placeholder_no_raise(self):
        # The defensive branch: an ImageRef whose sha1 is absent from deck.blobs
        # (normally unreachable) → PlaceholderAsset keyed by (slide,shape), no raise.
        ref = model.ImageRef(slide=2, shape=3, sha1="missing", ext="png", alt="x")
        deck = model.Deck(
            slides=[model.Slide(index=2, blocks=[ref])],
            source_name="t.pptx",
            blobs={},  # no entry for "missing"
        )
        with tempfile.TemporaryDirectory() as d:
            assets = images.materialise(deck, Path(d) / "m", "m")
            self.assertIsInstance(assets[ref], model.PlaceholderAsset)
            self.assertEqual((assets[ref].slide, assets[ref].shape), (2, 3))
            self.assertFalse((Path(d) / "m").exists())  # no file/dir for a placeholder


if __name__ == "__main__":
    unittest.main()

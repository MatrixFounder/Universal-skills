"""Bead 020-02 — extract.py document-model logic.

Synthetic python-pptx fixtures + fake-shape unit tests for the parts that are
hard to synthesise (group recursion, unreadable images). The tmp8 dogfood deck is
an opt-in integration check (skipped when absent)."""
from __future__ import annotations

import itertools
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from pptx.enum.shapes import MSO_SHAPE_TYPE

from pptx2md import extract, model
from pptx2md.tests._fixtures import (
    build_deck_with_background_image,
    build_deck_with_hidden_slide,
    build_deck_with_notes,
    build_deck_with_picture_placeholder,
    build_deck_with_table,
    build_minimal_deck,
)

_REPO_ROOT = _SCRIPTS.parents[2]
_TMP8 = _REPO_ROOT / "tmp8"


class _Opts:
    """Minimal stand-in for the argparse namespace build_deck reads."""

    def __init__(self, include_hidden=False):
        self.include_hidden = include_hidden


def _open(path):
    return extract.open_deck(Path(path))


# --------------------------------------------------------------------------- #
# Fake shapes for _walk_shapes (group recursion / unreadable image)
# --------------------------------------------------------------------------- #
class _FakeTextFrame:
    def __init__(self, paras):
        self.paragraphs = paras


class _FakePara:
    def __init__(self, text, level=0):
        self.text = text
        self.level = level


class _FakeShape:
    def __init__(self, shape_type, *, text=None, level=0, shapes=None, image=None):
        self.shape_type = shape_type
        self.name = "fake"
        self._image = image
        self.has_table = False
        self.has_chart = False
        if shapes is not None:
            self.shapes = shapes
        self.has_text_frame = text is not None
        if text is not None:
            self.text_frame = _FakeTextFrame([_FakePara(text, level)])

    @property
    def image(self):
        if self._image is None:
            raise ValueError("no embedded image")
        return self._image


class TestWalkShapes(unittest.TestCase):
    def test_group_recursion(self):
        inner = _FakeShape(MSO_SHAPE_TYPE.TEXT_BOX, text="grouped text")
        group = _FakeShape(MSO_SHAPE_TYPE.GROUP, shapes=[inner])
        blocks: list = []
        extract._walk_shapes([group], blocks, 1, None, itertools.count(1), {})
        self.assertEqual(len(blocks), 1)
        self.assertIsInstance(blocks[0], model.Bullets)
        self.assertEqual(blocks[0].items[0].text, "grouped text")

    def test_unreadable_image_becomes_placeholder(self):
        # A real picture IS a Picture instance (the production check is now
        # isinstance(shape, Picture), which also catches picture-placeholders); use a
        # Picture-spec mock whose .image raises so safe_image_meta degrades to None.
        from unittest import mock

        from pptx.shapes.picture import Picture

        pic = mock.MagicMock(spec=Picture)
        pic.shape_type = MSO_SHAPE_TYPE.PICTURE
        pic.shape_id = 99
        type(pic).image = mock.PropertyMock(side_effect=ValueError("no embedded image"))
        blocks: list = []
        extract._walk_shapes([pic], blocks, 3, None, itertools.count(1), {})
        self.assertEqual(len(blocks), 1)
        self.assertIsInstance(blocks[0], model.Placeholder)
        self.assertEqual(blocks[0].slide, 3)
        self.assertEqual(blocks[0].kind, "image")


# --------------------------------------------------------------------------- #
# build_deck on synthetic decks
# --------------------------------------------------------------------------- #
class _RaisingShape:
    """A shape whose shape_type access raises (python-pptx does this for shapes it
    cannot classify) — used to lock the C1 never-crash guard."""

    name = "weird"

    @property
    def shape_type(self):
        raise NotImplementedError("unknown shape kind")


class _RaisingGroup:
    """A GROUP shape whose .shapes collection raises (malformed grpSp) — locks the
    N1 guard so the group descent can never crash the deck."""

    name = "badgroup"
    shape_type = MSO_SHAPE_TYPE.GROUP

    @property
    def shapes(self):
        raise KeyError("malformed group")


class TestRobustness(unittest.TestCase):
    def test_unclassifiable_shape_type_becomes_placeholder(self):
        blocks: list = []
        extract._walk_shapes([_RaisingShape()], blocks, 5, None, itertools.count(1), {})
        self.assertEqual(len(blocks), 1)
        self.assertIsInstance(blocks[0], model.Placeholder)
        self.assertEqual(blocks[0].kind, "unclassifiable")
        self.assertEqual(blocks[0].slide, 5)

    def test_unreadable_group_shapes_becomes_placeholder(self):
        # N1: a GROUP whose .shapes access raises must degrade, not crash.
        blocks: list = []
        extract._walk_shapes([_RaisingGroup()], blocks, 7, None, itertools.count(1), {})
        self.assertEqual(len(blocks), 1)
        self.assertIsInstance(blocks[0], model.Placeholder)
        self.assertEqual(blocks[0].kind, "unclassifiable")

    def test_escape_cell_backslash_before_pipe_and_trim(self):
        # backslash escaped before pipe; outer newlines trimmed (no <br> litter).
        self.assertEqual(extract._escape_cell("a|b"), "a\\|b")
        self.assertEqual(extract._escape_cell("c\\|d"), "c\\\\\\|d")  # \ then | both escaped
        self.assertEqual(extract._escape_cell("\n\nx\n\n"), "x")
        self.assertEqual(extract._escape_cell("a\nb"), "a<br>b")

    def test_bullet_level_clamped_to_8(self):
        tf = _FakeTextFrame([_FakePara("deep", level=12), _FakePara("neg", level=0)])
        bullets = extract._bullets(tf)
        self.assertEqual(bullets.items[0].level, 8)  # clamped from 12
        self.assertEqual(bullets.items[1].level, 0)

    def test_hidden_slide_show_false_variant(self):
        with tempfile.TemporaryDirectory() as d:
            p = build_deck_with_hidden_slide(Path(d) / "h.pptx")
            from pptx import Presentation
            prs = Presentation(str(p))
            prs.slides[1]._element.set("show", "false")  # XSD-boolean spelling
            prs.save(str(p))
            self.assertEqual(len(extract.build_deck(_open(p), _Opts()).slides), 1)


class TestBuildDeck(unittest.TestCase):
    def test_title_first_and_bullet_levels(self):
        with tempfile.TemporaryDirectory() as d:
            deck = extract.build_deck(_open(build_minimal_deck(Path(d) / "m.pptx")), _Opts())
            self.assertEqual(len(deck.slides), 1)
            blocks = deck.slides[0].blocks
            self.assertIsInstance(blocks[0], model.Heading)  # title first
            self.assertEqual(blocks[0].text, "Hello Title")
            bullets = next(b for b in blocks if isinstance(b, model.Bullets))
            levels = [it.level for it in bullets.items]
            self.assertIn(0, levels)
            self.assertIn(1, levels)  # nested bullet preserved
            # Regression: the title must NOT also appear as a bullet (shape_id skip).
            all_bullet_text = [
                it.text for b in blocks if isinstance(b, model.Bullets) for it in b.items
            ]
            self.assertNotIn("Hello Title", all_bullet_text)
            self.assertEqual(sum(isinstance(b, model.Heading) for b in blocks), 1)

    def test_table_to_rows_escaped(self):
        with tempfile.TemporaryDirectory() as d:
            deck = extract.build_deck(_open(build_deck_with_table(Path(d) / "t.pptx")), _Opts())
            tbl = next(b for b in deck.slides[0].blocks if isinstance(b, model.Table))
            self.assertEqual(tbl.rows[0], ["H1", "H2"])
            self.assertEqual(tbl.rows[1][0], "a\\|b")          # pipe escaped
            self.assertEqual(tbl.rows[1][1], "line1<br>line2")  # newline → <br>

    def test_notes_present_and_no_sideeffect(self):
        with tempfile.TemporaryDirectory() as d:
            prs = _open(build_deck_with_notes(Path(d) / "n.pptx"))
            deck = extract.build_deck(prs, _Opts())
            self.assertEqual(deck.slides[0].notes, "Rehearse this point.")
            # notes-free minimal deck → None, and no create-on-access side effect.
            prs2 = _open(build_minimal_deck(Path(d) / "m.pptx"))
            deck2 = extract.build_deck(prs2, _Opts())
            self.assertIsNone(deck2.slides[0].notes)
            self.assertFalse(prs2.slides[0].has_notes_slide)

    def test_picture_placeholder_emits_imageref(self):
        # Fix A: a picture-placeholder (shape_type==PLACEHOLDER but isinstance Picture)
        # must be extracted as an ImageRef, not silently skipped.
        with tempfile.TemporaryDirectory() as d:
            deck = extract.build_deck(_open(build_deck_with_picture_placeholder(
                Path(d) / "pph.pptx")), _Opts())
            refs = [b for s in deck.slides for b in s.blocks if isinstance(b, model.ImageRef)]
            self.assertEqual(len(refs), 1, "picture-placeholder image must be captured")
            self.assertIn(refs[0].sha1, deck.blobs)

    def test_background_image_collected(self):
        # Fix B: a slide-background image (p:cSld/p:bg blip, no shapes) must be
        # collected as an ImageRef so the (otherwise empty) slide carries content.
        with tempfile.TemporaryDirectory() as d:
            deck = extract.build_deck(_open(build_deck_with_background_image(
                Path(d) / "bg.pptx")), _Opts())
            refs = [b for s in deck.slides for b in s.blocks if isinstance(b, model.ImageRef)]
            self.assertEqual(len(refs), 1, "slide-background image must be collected")
            self.assertEqual(refs[0].alt, "background")
            self.assertIn(refs[0].sha1, deck.blobs)

    def test_hidden_slide_skipped_then_included(self):
        with tempfile.TemporaryDirectory() as d:
            p = build_deck_with_hidden_slide(Path(d) / "h.pptx")
            self.assertEqual(len(extract.build_deck(_open(p), _Opts()).slides), 1)
            inc = extract.build_deck(_open(p), _Opts(include_hidden=True))
            self.assertEqual(len(inc.slides), 2)


# --------------------------------------------------------------------------- #
# Encryption / bad input guards (CFB-signature + non-OOXML)
# --------------------------------------------------------------------------- #
class TestInputGuards(unittest.TestCase):
    # CFB signature ([MS-CFB] §2.2) — encrypted OOXML AND legacy .ppt share it.
    _CFB = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

    def test_encrypted_or_legacy_raises_single_type(self):
        # The exit-3 *mapping* through cli.main is exercised in 020-04 (where the
        # pipeline calls assert_openable). Here we assert the 020-02 contract: one
        # EncryptedFileError for both the encrypted and the legacy case.
        from office._encryption import EncryptedFileError

        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "enc.pptx"
            f.write_bytes(self._CFB + b"\x00" * 64)
            with self.assertRaises(EncryptedFileError):
                extract.assert_openable(f)
            with self.assertRaises(EncryptedFileError):
                extract.open_deck(f)

    def test_bad_input_not_pptx(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "fake.pptx"
            f.write_text("this is plain text, not a zip")
            with self.assertRaises(extract.BadInput):
                extract.open_deck(f)


@unittest.skipUnless((_TMP8 / "slides-4.pptx").exists(), "tmp8/slides-4.pptx absent")
class TestDogfoodSlides4(unittest.TestCase):
    def test_extract_model_on_real_deck(self):
        deck = extract.build_deck(_open(_TMP8 / "slides-4.pptx"), _Opts())
        self.assertEqual(len(deck.slides), 21)
        # At least one slide has a title Heading, and bullets exist somewhere.
        self.assertTrue(any(
            isinstance(b, model.Heading) for s in deck.slides for b in s.blocks
        ))
        self.assertTrue(any(
            isinstance(b, model.Bullets) for s in deck.slides for b in s.blocks
        ))
        # No title is ever emitted twice: a Heading's text never also appears as a
        # same-slide level-0 bullet (the shape_id-skip regression lock).
        for s in deck.slides:
            headings = [b.text for b in s.blocks if isinstance(b, model.Heading)]
            bullet_texts = [
                it.text for b in s.blocks if isinstance(b, model.Bullets) for it in b.items
            ]
            for h in headings:
                self.assertNotIn(h, bullet_texts, f"title {h!r} duplicated as a bullet")


if __name__ == "__main__":
    unittest.main()

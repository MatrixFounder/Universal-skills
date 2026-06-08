"""Bead 020-04 — emit.render_deck + cli.main glue (MVP gate)."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from pptx2md import cli, emit, model
from pptx2md.tests._fixtures import (
    build_deck_with_duplicate_image,
    build_deck_with_hidden_slide,
    build_deck_with_notes,
    build_deck_with_table,
    build_minimal_deck,
)

_TMP8 = _SCRIPTS.parents[2] / "tmp8"


def _run(argv):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, err.getvalue()


class _Opts:
    no_notes = False


class TestRenderDeck(unittest.TestCase):
    def test_table_to_gfm(self):
        deck = model.Deck(slides=[model.Slide(index=1, blocks=[
            model.Table(rows=[["H1", "H2"], ["a", "b"]])])])
        md = "".join(emit.render_deck(deck, {}, {}, _Opts()))
        self.assertIn("| H1 | H2 |", md)
        self.assertIn("| --- | --- |", md)
        self.assertIn("| a | b |", md)

    def test_bullet_indentation(self):
        deck = model.Deck(slides=[model.Slide(index=1, blocks=[
            model.Bullets(items=[
                model.BulletItem(level=0, text="zero"),
                model.BulletItem(level=1, text="one"),
                model.BulletItem(level=2, text="two"),
            ])])])
        md = "".join(emit.render_deck(deck, {}, {}, _Opts()))
        self.assertIn("- zero\n", md)
        self.assertIn("  - one\n", md)
        self.assertIn("    - two\n", md)

    def test_placeholder_marker(self):
        deck = model.Deck(slides=[model.Slide(index=1, blocks=[
            model.Placeholder(slide=1, shape=1, kind="chart")])])
        md = "".join(emit.render_deck(deck, {}, {}, _Opts()))
        self.assertIn("[chart]", md)

    def test_notes_emitted_and_suppressed(self):
        deck = model.Deck(slides=[model.Slide(index=1, blocks=[], notes="rehearse")])
        self.assertIn("> **Notes:**", "".join(emit.render_deck(deck, {}, {}, _Opts())))

        class NoNotes:
            no_notes = True
        self.assertNotIn("Notes", "".join(emit.render_deck(deck, {}, {}, NoNotes())))

    def test_image_link_and_ocr_block(self):
        ref = model.ImageRef(slide=1, shape=1, sha1="s", ext="png", alt="diagram")
        asset = model.MediaAsset(sha1="s", filename="slide1-img1.png",
                                 rel_path="out.media/slide1-img1.png", content_type="image/png")
        deck = model.Deck(slides=[model.Slide(index=1, blocks=[ref])])
        md = "".join(emit.render_deck(deck, {ref: asset}, {asset: "OCR LINE"}, _Opts()))
        self.assertIn("![diagram](out.media/slide1-img1.png)", md)
        self.assertIn("<!-- ocr -->", md)
        self.assertIn("> OCR LINE", md)


class TestMainPipeline(unittest.TestCase):
    def test_full_convert_text_rich(self):
        with tempfile.TemporaryDirectory() as d:
            deck = build_minimal_deck(Path(d) / "m.pptx")
            out = Path(d) / "out.md"
            code, _ = _run([str(deck), str(out)])
            self.assertEqual(code, 0)
            text = out.read_text()
            self.assertTrue(text.startswith("## Slide 1"))
            self.assertIn("### Hello Title", text)
            self.assertIn("- First bullet", text)
            self.assertFalse((Path(d) / "out.md.partial").exists())

    def test_idempotent_run_twice(self):
        # R-A5/I-1: identical input + same output path → byte-identical .md.
        with tempfile.TemporaryDirectory() as d:
            deck = build_deck_with_duplicate_image(Path(d) / "dup.pptx")[0]
            out = Path(d) / "out.md"
            _run([str(deck), str(out)])
            first = out.read_text()
            _run([str(deck), str(out)])
            self.assertEqual(first, out.read_text())

    def test_images_to_sidecar_resolve(self):
        with tempfile.TemporaryDirectory() as d:
            deck = build_deck_with_duplicate_image(Path(d) / "dup.pptx")[0]
            out = Path(d) / "out.md"
            _run([str(deck), str(out)])
            media = Path(d) / "out.media"
            self.assertTrue(media.is_dir())
            # every ![](...) link resolves relative to the .md
            for line in out.read_text().splitlines():
                if line.startswith("!["):
                    rel = line.split("](", 1)[1].rstrip(")")
                    self.assertTrue((out.parent / rel).exists(), rel)

    def test_no_images_flag(self):
        with tempfile.TemporaryDirectory() as d:
            deck = build_deck_with_duplicate_image(Path(d) / "dup.pptx")[0]
            out = Path(d) / "out.md"
            _run([str(deck), str(out), "--no-images"])
            self.assertFalse((Path(d) / "out.media").exists())
            self.assertNotIn("![", out.read_text())

    def test_stdout_mode(self):
        with tempfile.TemporaryDirectory() as d:
            deck = build_minimal_deck(Path(d) / "m.pptx")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                code = cli.main([str(deck), "-"])
            self.assertEqual(code, 0)
            self.assertTrue(buf.getvalue().startswith("## Slide 1"))

    def test_atomic_no_partial_on_failure(self):
        # Force render to raise mid-stream → no out.md and no out.md.partial.
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.md"

            def boom(*a, **k):
                yield "## Slide 1\n"
                raise RuntimeError("boom")

            with self.assertRaises(RuntimeError):
                cli._write_output(out, boom())
            self.assertFalse(out.exists())
            self.assertFalse(Path(str(out) + ".partial").exists())
            self.assertFalse((out.with_suffix(".md.partial")).exists())

    def test_internal_error_exit_1_redacted(self):
        # An unexpected failure in the pipeline → exit 1, type InternalError, no path leak.
        with tempfile.TemporaryDirectory() as d:
            deck = build_minimal_deck(Path(d) / "m.pptx")
            out = Path(d) / "out.md"
            orig = emit.render_deck
            try:
                emit.render_deck = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("/secret/path"))
                code, err = _run([str(deck), str(out), "--json-errors"])
            finally:
                emit.render_deck = orig
            self.assertEqual(code, 1)
            env = json.loads(err.strip().splitlines()[-1])
            self.assertEqual(env["type"], "InternalError")
            self.assertNotIn("/secret/path", err)

    def test_notes_block_in_output(self):
        with tempfile.TemporaryDirectory() as d:
            deck = build_deck_with_notes(Path(d) / "n.pptx")
            out = Path(d) / "out.md"
            _run([str(deck), str(out)])
            self.assertIn("> **Notes:**", out.read_text())
            out2 = Path(d) / "out2.md"
            _run([str(deck), str(out2), "--no-notes"])
            self.assertNotIn("Notes", out2.read_text())

    def test_encrypted_exit_3_via_main(self):
        # Now that main wires the pipeline, the encryption guard maps to exit 3.
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "enc.pptx"
            f.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
            out = Path(d) / "o.md"
            code, err = _run([str(f), str(out), "--json-errors"])
            self.assertEqual(code, 3)
            self.assertEqual(json.loads(err.strip().splitlines()[-1])["type"], "EncryptedFileError")
            self.assertFalse(out.exists())
            # vdd-multi LOW-1: the envelope must NOT leak the absolute input path
            # (basename only — parity with every other error path).
            self.assertNotIn(str(f.parent), err)

    def test_include_hidden_end_to_end(self):
        # R-A1d: --include-hidden wired through real argparse → hidden slide appears.
        with tempfile.TemporaryDirectory() as d:
            deck = build_deck_with_hidden_slide(Path(d) / "h.pptx")
            out = Path(d) / "out.md"
            _run([str(deck), str(out)])
            self.assertEqual(out.read_text().count("## Slide "), 1)  # hidden skipped
            out2 = Path(d) / "out2.md"
            _run([str(deck), str(out2), "--include-hidden"])
            self.assertEqual(out2.read_text().count("## Slide "), 2)  # hidden included

    def test_media_self_overwrite_exit_6(self):
        # R-D4a: a media file resolving onto INPUT → exit 6, INPUT never clobbered.
        # Contrived: a real .pptx deliberately named like a media file, with
        # --media-dir = its own parent, so slide1-img1.png would land on INPUT.
        with tempfile.TemporaryDirectory() as d:
            dd = Path(d)
            deck_path = dd / "slide1-img1.png"  # a pptx with a .png name
            build_deck_with_duplicate_image(deck_path)  # embeds a PNG on slides 1 & 2
            size_before = deck_path.stat().st_size
            out = dd / "out.md"
            code, err = _run([str(deck_path), str(out), "--media-dir", str(dd), "--json-errors"])
            self.assertEqual(code, 6)
            self.assertEqual(
                json.loads(err.strip().splitlines()[-1])["type"], "SelfOverwriteRefused")
            self.assertEqual(deck_path.stat().st_size, size_before)  # not clobbered

    def test_gfm_table_present(self):
        with tempfile.TemporaryDirectory() as d:
            deck = build_deck_with_table(Path(d) / "t.pptx")
            out = Path(d) / "out.md"
            _run([str(deck), str(out)])
            self.assertIn("| --- |", out.read_text())


@unittest.skipUnless((_TMP8 / "slodes-3.pptx").exists(), "tmp8/slodes-3.pptx absent")
class TestDogfoodSlodes3(unittest.TestCase):
    def test_gfm_tables_from_slodes3(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "slodes3.md"
            code, _ = _run([str(_TMP8 / "slodes-3.pptx"), str(out)])
            self.assertEqual(code, 0)
            text = out.read_text()
            self.assertIn("| --- |", text)  # slodes-3 has 2 tables
            self.assertEqual(text.count("## Slide "), 82)


if __name__ == "__main__":
    unittest.main()

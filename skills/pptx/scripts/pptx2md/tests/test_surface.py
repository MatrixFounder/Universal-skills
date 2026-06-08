"""Bead 020-01 frozen-surface unit tests (Stub-First Phase 1).

These assert the frozen public surface (argparse, exit codes, exception hierarchy,
model dataclasses, path guards) and pass on the stubs. Later beads (020-02..05)
TIGHTEN these (e.g. the ``-999`` sentinel → real exit codes) per tdd-stub-first §2.4.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make scripts/ importable (so `import pptx2md`, `_errors`, `office` resolve)
# regardless of CWD: scripts/ = parent of the pptx2md package dir.
_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import pptx2md
from pptx2md import cli, model
from pptx2md.tests._fixtures import build_minimal_deck


def _run(argv):
    """Run main(argv) capturing stderr; return (code, stderr_text)."""
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        code = cli.main(argv)
    return code, buf.getvalue()


class TestImportsAndConstants(unittest.TestCase):
    def test_module_imports_without_tesseract(self):
        # Real contract (R-C1d): `import pptx2md` works with no OCR engine present,
        # because (a) cli imports `ocr` lazily (only under --ocr) and (b) ocr.py
        # imports nothing *engine-coupled* at module top — Pillow + tesseract are
        # touched only inside the functions. (stdlib subprocess/shutil at module top
        # is fine: always importable, needs no tesseract, and lets tests patch them.)
        import pptx2md.ocr as ocr_mod  # import succeeds with no engine present

        def _header(path):
            out = []
            for line in Path(path).read_text().splitlines():
                if line.startswith(("def ", "class ")):
                    break
                out.append(line)
            return "\n".join(out)

        ocr_header = _header(ocr_mod.__file__)
        self.assertNotIn("import PIL", ocr_header, "ocr.py must import Pillow lazily")
        self.assertNotIn("from PIL", ocr_header, "ocr.py must import Pillow lazily")
        # cli must not import ocr at MODULE level (it's lazy, inside _build_ocr_text).
        self.assertNotIn("import ocr", _header(cli.__file__),
                         "cli must import ocr lazily, not at module top")

    def test_exit_constants_locked(self):
        self.assertEqual(cli._EXIT_OK, 0)
        self.assertEqual(cli._EXIT_USAGE, 2)
        self.assertEqual(cli._EXIT_ENCRYPTED, 3)
        self.assertEqual(cli._EXIT_SELF_OVERWRITE, 6)
        self.assertEqual(cli._DEFAULT_OCR_LANG, "eng+rus")
        self.assertEqual(pptx2md.SelfOverwriteRefused.CODE, 6)
        self.assertEqual(pptx2md.OcrEngineUnavailable.CODE, 1)
        self.assertEqual(pptx2md.LanguagePackMissing.CODE, 1)
        self.assertEqual(pptx2md.BadInput.CODE, 1)
        self.assertEqual(pptx2md.InternalError.CODE, 1)


class TestArgparse(unittest.TestCase):
    def test_argparse_defaults(self):
        args = cli.build_parser().parse_args(["a.pptx"])
        self.assertEqual(args.OUTPUT, "-")
        self.assertFalse(args.ocr)
        self.assertEqual(args.ocr_lang, "eng+rus")
        self.assertEqual(args.jobs, 1)
        self.assertEqual(args.ocr_timeout, 120.0)
        self.assertFalse(args.no_images)
        self.assertFalse(args.include_hidden)
        self.assertFalse(args.no_notes)
        self.assertIsNone(args.media_dir)


class TestPathGuards(unittest.TestCase):
    def test_self_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "deck.pptx"
            f.write_bytes(b"PK\x03\x04stub")  # exists; not opened in 020-01
            code, _ = _run([str(f), str(f)])
            self.assertEqual(code, 6)

    def test_self_overwrite_symlink_alias(self):
        with tempfile.TemporaryDirectory() as d:
            real = Path(d) / "deck.pptx"
            real.write_bytes(b"PK\x03\x04stub")
            link = Path(d) / "alias.pptx"
            os.symlink(real, link)
            code, _ = _run([str(real), str(link)])
            self.assertEqual(code, 6)

    def test_input_not_found(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "nope.pptx"
            out = Path(d) / "out.md"
            code, err = _run([str(missing), str(out), "--json-errors"])
            self.assertEqual(code, 1)
            env = json.loads(err.strip().splitlines()[-1])
            self.assertEqual(env["type"], "BadInput")

    def test_main_converts_valid_deck(self):
        # Tightened from the 020-01 sentinel: main now runs the real pipeline → 0
        # and writes a non-empty .md (tdd-stub-first §2.4).
        with tempfile.TemporaryDirectory() as d:
            deck = build_minimal_deck(Path(d) / "in.pptx")
            out = Path(d) / "out.md"
            code, _ = _run([str(deck), str(out)])
            self.assertEqual(code, 0)
            self.assertTrue(out.exists() and out.read_text().startswith("## Slide 1"))

    def test_stdout_media_link_base(self):
        # stdout mode → link base relative to CWD; file mode → relative to the .md.
        p_stdout = cli.build_parser().parse_args(["in.pptx", "-"])
        p_stdout.INPUT = "in.pptx"
        media_dir, link_base = cli._resolve_media_dir(p_stdout, None)
        self.assertTrue(link_base.endswith("in.media"))
        self.assertNotIn("\\", link_base)  # POSIX separators

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "deck.md"
            p_file = cli.build_parser().parse_args(["in.pptx", str(out)])
            p_file.INPUT = "in.pptx"
            media_dir2, link_base2 = cli._resolve_media_dir(p_file, out.resolve())
            self.assertEqual(link_base2, "deck.media")


class TestModel(unittest.TestCase):
    def test_model_dataclasses_shape(self):
        slide = model.Slide(
            index=1,
            blocks=[
                model.Heading(level=3, text="T"),
                model.Bullets(items=[model.BulletItem(level=1, text="x")]),
                model.Table(rows=[["h"], ["v"]]),
            ],
            notes=None,
        )
        self.assertEqual(slide.index, 1)
        self.assertIsInstance(slide.blocks[0], model.Heading)
        self.assertEqual(slide.blocks[1].items[0].level, 1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            slide.index = 2  # frozen outer record


if __name__ == "__main__":
    unittest.main()

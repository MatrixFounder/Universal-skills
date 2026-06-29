"""Tests for multi-format caption parsing (`sources._captions`) — TF-X-4.

Pure-function tests (no network, no yt-dlp): SRT → plain, TTML → plain, the
format dispatcher, the XXE/billion-laughs DTD guard, and the size cap.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from sources import _captions as cap  # noqa: E402


_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:02,000\n"
    "Hello world\n\n"
    "2\n"
    "00:00:02,000 --> 00:00:04,000\n"
    "this is a caption\n"
)

_TTML = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<tt xmlns="http://www.w3.org/ns/ttml">\n'
    "  <body><div>\n"
    '    <p begin="00:00:00.000" end="00:00:02.000">Hello world</p>\n'
    '    <p begin="00:00:02.000" end="00:00:04.000">first<br/>second</p>\n'
    "  </div></body>\n"
    "</tt>\n"
)

# DFXP/TTML with a malicious internal entity (billion-laughs shape).
_TTML_BILLION_LAUGHS = (
    '<?xml version="1.0"?>\n'
    "<!DOCTYPE lolz [\n"
    '  <!ENTITY lol "lol">\n'
    '  <!ENTITY lol2 "&lol;&lol;&lol;">\n'
    "]>\n"
    '<tt xmlns="http://www.w3.org/ns/ttml"><body><div>'
    '<p>&lol2;</p></div></body></tt>'
)


class TestSRT(unittest.TestCase):
    def test_srt_to_plain(self) -> None:
        out = cap.srt_text_to_plain(_SRT)
        self.assertIn("Hello world", out)
        self.assertIn("this is a caption", out)
        # No timecodes / index numbers leak into prose.
        self.assertNotIn("-->", out)
        self.assertNotIn("00:00:00", out)

    def test_srt_speaker_turn_marker_preserved(self) -> None:
        srt = (
            "1\n00:00:00,000 --> 00:00:02,000\n>> Alice speaking\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\n>> Bob replies\n"
        )
        out = cap.srt_text_to_plain(srt)
        self.assertIn(">> Alice speaking", out)
        self.assertIn(">> Bob replies", out)

    def test_srt_file_meta(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.en.srt"
            p.write_text(_SRT, encoding="utf-8")
            text, codec = cap.srt_file_to_plain_meta(p)
            self.assertIn("Hello world", text)
            self.assertIn(codec, ("utf-8", "utf-8-sig"))


class TestTTML(unittest.TestCase):
    def test_ttml_to_plain(self) -> None:
        out = cap.ttml_text_to_plain(_TTML)
        self.assertIn("Hello world", out)
        # <br/> becomes a space — words must not fuse.
        self.assertIn("first second", out)
        self.assertNotIn("firstsecond", out)

    def test_ttml_namespaced_and_nested_spans(self) -> None:
        ttml = (
            '<tt xmlns="http://www.w3.org/ns/ttml"><body><div>'
            '<p><span>Hello</span> <span>there</span></p>'
            "</div></body></tt>"
        )
        self.assertEqual(cap.ttml_text_to_plain(ttml), "Hello there")

    def test_ttml_dtd_entity_refused(self) -> None:
        with self.assertRaises(ValueError):
            cap.ttml_text_to_plain(_TTML_BILLION_LAUGHS)

    def test_ttml_malformed_raises_valueerror(self) -> None:
        with self.assertRaises(ValueError):
            cap.ttml_text_to_plain("<tt><body><p>unclosed")

    def test_ttml_oversize_file_refused(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.en.ttml"
            # Write just over the cap with valid-ish bytes.
            p.write_bytes(b"<tt>" + b" " * (cap._MAX_TTML_BYTES + 1) + b"</tt>")
            with self.assertRaises(ValueError):
                cap.ttml_file_to_plain_meta(p)


class TestDispatch(unittest.TestCase):
    def test_dispatch_by_extension(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            srt = Path(d) / "a.en.srt"
            srt.write_text(_SRT, encoding="utf-8")
            ttml = Path(d) / "a.en.ttml"
            ttml.write_text(_TTML, encoding="utf-8")
            vtt = Path(d) / "a.en.vtt"
            vtt.write_text(
                "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nvtt body\n",
                encoding="utf-8",
            )
            self.assertIn("Hello world", cap.captions_file_to_plain_meta(srt)[0])
            self.assertIn("Hello world", cap.captions_file_to_plain_meta(ttml)[0])
            self.assertIn("vtt body", cap.captions_file_to_plain_meta(vtt)[0])

    def test_explicit_fmt_overrides_suffix(self) -> None:
        # A .txt file whose content is SRT, parsed as srt via explicit fmt.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.en.txt"
            p.write_text(_SRT, encoding="utf-8")
            text, _ = cap.captions_file_to_plain_meta(p, "srt")
            self.assertIn("Hello world", text)

    def test_supported_exts_contract(self) -> None:
        for ext in ("vtt", "srt", "ttml", "dfxp", "xml"):
            self.assertIn(ext, cap.SUPPORTED_CAPTION_EXTS)


if __name__ == "__main__":
    unittest.main()

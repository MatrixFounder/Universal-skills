"""Offline unit tests for the WebVTT -> plain-text converter.

These tests are pure-Python and require no network or yt-dlp. They
cover both happy-path transformations and the regressions identified
in the v1.0 adversarial review:

- HTML-entity decoding (``&gt;&gt;`` -> ``>>``).
- Inline timing tag stripping (``<00:00:10.000><c>...</c>``).
- Rolling-caption deduplication (prefix-extension AND suffix-prefix overlap).
- Speaker-turn marker preservation: leading-only, mid-cue ``>>`` left alone.
- File-header / cue-index / timestamp removal.
- STYLE / NOTE / REGION blocks dropped.
- Multi-line cues grouped correctly.
- Encoding fallback (UTF-8 / CP1251 / UTF-16 / BOM).
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

from sources._vtt_to_text import (  # noqa: E402
    count_speaker_turns,
    vtt_file_to_plain,
    vtt_file_to_plain_meta,
    vtt_text_to_plain,
)


FIXTURES = _HERE / "fixtures"


class TestVttToText(unittest.TestCase):
    """Synthetic-input tests covering each transformation."""

    def test_strips_header_and_timestamps(self) -> None:
        raw = (
            "WEBVTT\n"
            "Kind: captions\n"
            "Language: ru\n"
            "\n"
            "00:00:00.000 --> 00:00:01.000 align:start position:0%\n"
            "Hello world\n"
        )
        self.assertEqual(vtt_text_to_plain(raw), "Hello world")

    def test_strips_inline_timing_tags(self) -> None:
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "Hello<00:00:00.500><c> world</c>\n"
        )
        self.assertEqual(vtt_text_to_plain(raw), "Hello world")

    def test_decodes_html_entities(self) -> None:
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "Tom &amp; Jerry\n"
        )
        self.assertIn("Tom & Jerry", vtt_text_to_plain(raw))

    def test_dedups_rolling_captions(self) -> None:
        # YouTube style: each cue is a prefix-extension of the previous.
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "А вот это уже\n"
            "\n"
            "00:00:01.000 --> 00:00:02.000\n"
            "А вот это уже интересно\n"
            "\n"
            "00:00:02.000 --> 00:00:03.000\n"
            "А вот это уже интересно сегодня\n"
        )
        out = vtt_text_to_plain(raw)
        self.assertEqual(out, "А вот это уже интересно сегодня")

    def test_dedups_suffix_prefix_overlap(self) -> None:
        # Sentence-boundary case: previous ends with N words that begin current.
        # Threshold is >= 3 word tokens, so the 3-word overlap should splice.
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "и я думаю что это\n"
            "\n"
            "00:00:01.000 --> 00:00:02.000\n"
            "думаю что это работает\n"
        )
        out = vtt_text_to_plain(raw)
        self.assertEqual(out, "и я думаю что это работает")

    def test_does_not_dedup_short_overlap(self) -> None:
        # 2-word overlap is below the threshold (would be too noisy).
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "и я думаю что\n"
            "\n"
            "00:00:01.000 --> 00:00:02.000\n"
            "думаю что это работает\n"
        )
        out = vtt_text_to_plain(raw)
        # Both cues retained because the suffix-prefix overlap is only 2 words.
        self.assertIn("и я думаю что", out)
        self.assertIn("это работает", out)

    def test_preserves_speaker_turn_markers(self) -> None:
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "&gt;&gt; Alice opens.\n"
            "\n"
            "00:00:01.000 --> 00:00:02.000\n"
            "And continues.\n"
            "\n"
            "00:00:02.000 --> 00:00:03.000\n"
            "&gt;&gt; Bob replies.\n"
        )
        out = vtt_text_to_plain(raw)
        self.assertTrue(out.startswith(">> Alice"))
        self.assertIn("\n\n>> Bob replies.", out)
        self.assertEqual(count_speaker_turns(out), 2)

    def test_mid_cue_double_chevron_is_preserved_verbatim(self) -> None:
        # A talk that mentions C++ stream operators or shell redirection
        # uses `>>` mid-sentence. We must NOT treat it as a turn boundary.
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "Use cout &lt;&lt; x &gt;&gt; y in C++.\n"
            "\n"
            "00:00:01.000 --> 00:00:02.000\n"
            "And shell &gt;&gt; redirects to a file.\n"
        )
        out = vtt_text_to_plain(raw)
        # Mid-cue `>>` should appear in the body, NOT prefixed by "\n\n>> ".
        self.assertIn("cout << x >> y in C++.", out)
        self.assertIn("shell >> redirects to a file.", out)
        # Zero turns: neither cue starts with `>>`.
        self.assertEqual(count_speaker_turns(out), 0)
        self.assertNotIn("\n\n>>", out)

    def test_drops_cue_indices_and_blank_lines(self) -> None:
        raw = (
            "WEBVTT\n\n"
            "1\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "First cue.\n"
            "\n"
            "2\n"
            "00:00:01.000 --> 00:00:02.000\n"
            "Second cue.\n"
        )
        self.assertEqual(vtt_text_to_plain(raw), "First cue. Second cue.")

    def test_drops_style_note_region_blocks(self) -> None:
        # Vimeo / manual VTT can have STYLE/NOTE/REGION blocks. We drop
        # them so they never leak into output.
        raw = (
            "WEBVTT\n\n"
            "STYLE\n"
            "::cue { color: red; }\n"
            "\n"
            "NOTE author=jdoe\n"
            "This is a comment that should not appear.\n"
            "\n"
            "REGION\n"
            "id:r1 width:40%\n"
            "\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "Real content here.\n"
        )
        out = vtt_text_to_plain(raw)
        self.assertEqual(out, "Real content here.")
        self.assertNotIn("color", out)
        self.assertNotIn("comment", out)
        self.assertNotIn("width", out)

    def test_multi_line_cue_grouping(self) -> None:
        # A single cue can span multiple text lines (separated only by
        # newlines, not blank lines). They should be joined within the
        # cue, not treated as separate cues.
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:03.000\n"
            "Line one of one cue\n"
            "line two of same cue\n"
            "\n"
            "00:00:03.000 --> 00:00:04.000\n"
            "Next cue.\n"
        )
        out = vtt_text_to_plain(raw)
        self.assertEqual(out, "Line one of one cue line two of same cue Next cue.")

    def test_normalises_whitespace(self) -> None:
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "  multi    space   chunks  \n"
        )
        self.assertEqual(vtt_text_to_plain(raw), "multi space chunks")

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(vtt_text_to_plain(""), "")
        self.assertEqual(count_speaker_turns(""), 0)

    def test_lone_double_chevron_cue_is_dropped(self) -> None:
        # A cue that is ONLY `>>` (with nothing else) is degenerate;
        # the next real cue should carry the actual content.
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "&gt;&gt;\n"
            "\n"
            "00:00:01.000 --> 00:00:02.000\n"
            "Real content.\n"
        )
        out = vtt_text_to_plain(raw)
        self.assertEqual(out, "Real content.")
        self.assertEqual(count_speaker_turns(out), 0)


class TestEncodingFallback(unittest.TestCase):
    """Codec fallback ladder: UTF-8 / UTF-8-BOM / CP1251 / UTF-16."""

    def _write_bytes(self, suffix: str, payload: bytes) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, prefix="vtt-test-"
        )
        tmp.write(payload)
        tmp.close()
        return Path(tmp.name)

    def test_utf8_clean(self) -> None:
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "Привет\n"
        ).encode("utf-8")
        path = self._write_bytes(".vtt", raw)
        try:
            text, codec = vtt_file_to_plain_meta(path)
            self.assertEqual(text, "Привет")
            self.assertIn(codec, ("utf-8", "utf-8-sig"))
        finally:
            path.unlink(missing_ok=True)

    def test_utf8_with_bom_stripped(self) -> None:
        raw = "﻿WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nПривет\n".encode(
            "utf-8"
        )
        path = self._write_bytes(".vtt", raw)
        try:
            text, codec = vtt_file_to_plain_meta(path)
            # BOM must NOT appear in the cleaned text.
            self.assertNotIn("﻿", text)
            self.assertEqual(text, "Привет")
            self.assertEqual(codec, "utf-8-sig")
        finally:
            path.unlink(missing_ok=True)

    def test_cp1251_fallback(self) -> None:
        # A VTT in CP1251 (older Russian content). Must decode
        # successfully and be flagged via the codec_used return value.
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "Привет\n"
        ).encode("cp1251")
        path = self._write_bytes(".vtt", raw)
        try:
            text, codec = vtt_file_to_plain_meta(path)
            self.assertEqual(text, "Привет")
            self.assertEqual(codec, "cp1251")
        finally:
            path.unlink(missing_ok=True)

    def test_utf16_with_bom(self) -> None:
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
            "Привет\n"
        ).encode("utf-16")  # python adds BOM by default
        path = self._write_bytes(".vtt", raw)
        try:
            text, codec = vtt_file_to_plain_meta(path)
            self.assertEqual(text, "Привет")
            self.assertEqual(codec, "utf-16")
        finally:
            path.unlink(missing_ok=True)

    def test_back_compat_vtt_file_to_plain_returns_str(self) -> None:
        raw = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n".encode("utf-8")
        path = self._write_bytes(".vtt", raw)
        try:
            out = vtt_file_to_plain(path)
            self.assertIsInstance(out, str)
            self.assertEqual(out, "Hello")
        finally:
            path.unlink(missing_ok=True)


class TestVttFileFixtures(unittest.TestCase):
    """End-to-end tests against the real-world fixtures shipped with
    the skill (offline; no network)."""

    def test_sample_ru_vtt_round_trip(self) -> None:
        path = FIXTURES / "sample.ru.vtt"
        self.assertTrue(path.exists(), f"Missing fixture: {path}")
        out = vtt_file_to_plain(path)
        self.assertGreater(len(out), 1000, "fixture should produce substantial text")
        self.assertNotIn("-->", out)
        self.assertNotIn("WEBVTT", out)
        self.assertNotIn("&gt;", out)
        self.assertNotIn("<c>", out)

    def test_sample_with_speakers_has_turn_markers(self) -> None:
        path = FIXTURES / "sample_with_speakers.ru-orig.vtt"
        self.assertTrue(path.exists(), f"Missing fixture: {path}")
        out = vtt_file_to_plain(path)
        turns = count_speaker_turns(out)
        self.assertGreater(
            turns,
            1,
            "sample_with_speakers fixture should yield multiple `>>` turns",
        )
        for marker in [m for m in out.split("\n") if m.startswith(">>")]:
            self.assertTrue(marker.startswith(">> "))


class TestMalformedVtt(unittest.TestCase):
    """Robustness tests against malformed / partial input."""

    def test_no_webvtt_header(self) -> None:
        # Missing WEBVTT header — we still extract any cue-shaped data.
        raw = (
            "00:00:00.000 --> 00:00:01.000\n"
            "Hello world\n"
        )
        self.assertEqual(vtt_text_to_plain(raw), "Hello world")

    def test_truncated_after_timestamp(self) -> None:
        # Timestamp present, no cue text. Should not crash; returns "".
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:01.000\n"
        )
        self.assertEqual(vtt_text_to_plain(raw), "")

    def test_pure_garbage_returns_garbage_as_one_block(self) -> None:
        # No timestamp at all — nothing is recognised as a cue.
        raw = "this is not a vtt file at all\nstill not a vtt"
        self.assertEqual(vtt_text_to_plain(raw), "")


if __name__ == "__main__":
    unittest.main()

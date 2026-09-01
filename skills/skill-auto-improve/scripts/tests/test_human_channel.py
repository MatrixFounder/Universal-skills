"""The human channel: reports and `--help` survive a non-UTF-8 locale.

Counterpart to this skill's machine-channel tests. The two contracts are
opposites and that is the point: JSON on stdout must ignore the caller's
locale (RFC 8259 §8.1), while prose must OBEY it — writing UTF-8 into a
terminal that declared cp1252 is mojibake, not robustness.

The defect: stderr is opened errors="backslashreplace" and survives, but
stdout gets "surrogateescape" (or "strict" under an explicit
PYTHONIOENCODING), and neither can represent an em dash — surrogateescape
rescues lone surrogates and nothing else. One `—` or `✓` in a report, or in an
argparse help= string, took the whole command down.

Issue: docs/issues/human-cli-output-locale-class.md.
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import common as H  # noqa: E402

GLYPHS = {"—": "--", "…": "...", "→": "->", "✓": "+", "✗": "x", "⚠": "!", "§": "S"}


class _FakeSink:
    """A text sink reporting an arbitrary `encoding`. `io.StringIO` cannot
    stand in: its `encoding` is a read-only `None`, which is exactly the case
    that must SKIP degradation."""

    def __init__(self, encoding):
        self.encoding = encoding
        self._parts = []

    def write(self, text):
        self._parts.append(text)
        return len(text)

    def flush(self):
        pass

    def value(self):
        return "".join(self._parts)


def _strict(encoding):
    return io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors="strict")


class TestAsciiFallback(unittest.TestCase):
    def test_a_codec_that_copes_gets_the_string_back_by_identity(self):
        """The UTF-8 case — nearly every real run. Not merely equal: the same
        object, so this fix provably moves no bytes on a working machine."""
        text = "доклад — ECMA §2 [✓] [✗] → café"
        self.assertIs(H.ascii_fallback(text, "utf-8"), text)

    def test_every_glyph_has_an_ascii_spelling(self):
        for glyph, expected in GLYPHS.items():
            with self.subTest(glyph=glyph):
                self.assertEqual(H.ascii_fallback(glyph, "ascii"), expected)

    def test_degradation_is_per_character(self):
        """A codec must keep everything it CAN represent. cp1251 has Cyrillic
        and an em dash; it lacks a check mark. Only the check mark may move."""
        got = H.ascii_fallback("доклад — ✓", "cp1251")
        self.assertEqual(got, "доклад — +")
        got.encode("cp1251")

    def test_the_result_always_encodes(self):
        cases = {"cyrillic": "Привет", "latin1": "café", "astral": "\U0001F600",
                 "cjk": "日本語", "lone surrogate": "/tmp/out\udcff.md"}
        for label, text in cases.items():
            for enc in ("ascii", "cp1251", "cp1252", "utf-8", "latin-1"):
                with self.subTest(text=label, encoding=enc):
                    H.ascii_fallback(text, enc).encode(enc)

    def test_a_lone_surrogate_survives_even_under_utf8(self):
        """UTF-8 is the one codec with no representation for U+DC80-DCFF, and
        POSIX puts them into str(path) via surrogateescape. So this crashed on
        a correctly configured machine."""
        path = "/tmp/out\udcff.md"
        with self.assertRaises(UnicodeEncodeError):
            path.encode("utf-8")
        self.assertEqual(H.ascii_fallback(path, "utf-8"), "/tmp/out\\udcff.md")

    def test_a_bogus_codec_name_degrades_instead_of_raising(self):
        """A crash-preventer that crashes is worse than none. `.encoding` is
        only conventionally a valid codec name."""
        for enc in ("not-a-codec", "base64", "", None, 123):
            with self.subTest(encoding=enc):
                self.assertEqual(H.ascii_fallback("a — b", enc), "a -- b")

    def test_text_encodable_holds_on_its_own(self):
        """Reached through ascii_fallback it never sees a bad codec, because
        _usable_codec normalises those first — so without a direct test its
        guards are unverified."""
        for enc in ("not-a-codec", "base64", None, 123):
            with self.subTest(encoding=enc):
                self.assertIs(H._text_encodable("a — b", enc), False)
        self.assertIs(H._text_encodable("plain", "ascii"), True)
        self.assertIs(H._text_encodable("—", "ascii"), False)


class TestSay(unittest.TestCase):
    CASES = [({}, "a b\n"), ({"sep": None}, "a b\n"), ({"end": None}, "a b\n"),
             ({"sep": "-"}, "a-b\n"), ({"end": "!"}, "a b!"),
             ({"flush": False}, "a b\n"), ({"sep": "", "end": ""}, "ab")]

    def test_it_matches_print_for_every_keyword(self):
        """The keyword is `file`, as in print, precisely so a mechanical
        print( -> say( migration cannot introduce a TypeError."""
        for kwargs, expected in self.CASES:
            with self.subTest(kwargs=kwargs):
                mine, theirs = io.StringIO(), io.StringIO()
                H.say("a", "b", file=mine, **kwargs)
                print("a", "b", file=theirs, **kwargs)
                self.assertEqual(mine.getvalue(), expected)
                self.assertEqual(mine.getvalue(), theirs.getvalue())

    def test_it_never_raises_on_a_strict_stream(self):
        stream = _strict("ascii")
        H.say("доклад — готов ✓", file=stream)
        stream.flush()
        stream.buffer.getvalue().decode("ascii")

    def test_it_honours_the_callers_codec(self):
        stream = _strict("cp1251")
        H.say("доклад — ✓", file=stream)
        stream.flush()
        self.assertEqual(stream.buffer.getvalue().decode("cp1251"), "доклад — +\n")

    def test_a_sink_without_a_codec_is_left_alone(self):
        sink = _FakeSink(None)
        H.say("✓ done — ok", file=sink)
        self.assertEqual(sink.value(), "✓ done — ok\n")

    def test_a_closed_stdout_is_a_silent_no_op_like_print(self):
        saved = sys.stdout
        sys.stdout = None
        try:
            H.say("✓ nobody is listening")
        finally:
            sys.stdout = saved


class TestHumanArgumentParser(unittest.TestCase):
    def _parser(self):
        p = H.HumanArgumentParser(prog="demo", description="Report — §2")
        p.add_argument("--x", help="does a thing → fast")
        return p

    def test_help_reaches_a_strict_ascii_stream(self):
        stream = _strict("ascii")
        self._parser().print_help(stream)
        stream.flush()
        text = stream.buffer.getvalue().decode("ascii")
        self.assertIn("Report -- S2", text)
        self.assertIn("does a thing -> fast", text)

    def test_help_is_untouched_when_the_codec_copes(self):
        stream = _strict("utf-8")
        self._parser().print_help(stream)
        stream.flush()
        self.assertIn("Report — §2", stream.buffer.getvalue().decode("utf-8"))

    def test_subparsers_inherit_the_class(self):
        """argparse does `kwargs.setdefault('parser_class', type(self))`, so a
        subcommand's --help is covered by the top-level swap. Pinned because it
        is load-bearing and undocumented: if CPython ever stops doing it, every
        subcommand's help silently regains the crash."""
        p = self._parser()
        sub = p.add_subparsers().add_parser("go", description="sub — prose")
        self.assertIsInstance(sub, H.HumanArgumentParser)
        stream = _strict("ascii")
        sub.print_help(stream)
        stream.flush()
        self.assertIn(b"sub -- prose", stream.buffer.getvalue())

    def test_the_funnel_this_override_depends_on_still_exists(self):
        self.assertTrue(hasattr(argparse.ArgumentParser, "_print_message"))
        for m in ("print_help", "print_usage"):
            with self.subTest(method=m):
                self.assertIn("_print_message", getattr(argparse.ArgumentParser, m).__code__.co_names)


if __name__ == "__main__":
    unittest.main()

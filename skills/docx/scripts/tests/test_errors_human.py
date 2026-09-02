"""The HUMAN side of `_errors.py` — the ASCII-fallback codec error handler.

Sibling of `test_errors_stdout.py`, which pins the MACHINE channel. The two
contracts are opposites and that is the point: `write_json_stdout` must ignore
the caller's locale (JSON is UTF-8 by RFC 8259 §8.1), while everything here
must OBEY it — writing UTF-8 into a terminal that declared cp1252 is mojibake,
not robustness.

`_errors.py` is replicated byte-identically into xlsx, pptx, pdf and html
(CLAUDE.md §2, docx is the master), so this file lives only in docx — the same
placement `test_errors_stdout.py` uses.

Three properties, in the order they were broken:

  1. **The command produced its output.** `--help` on four docx entry points
     and the `validate` report died under `LC_ALL=C` with 0 bytes.
  2. **It did not change its answer.** The exit status under a legacy codec
     must equal the exit status under UTF-8.
  3. **It did not change its bytes on a working machine.** Under UTF-8 the
     real glyphs must still be there. A "fix" that ASCII-ifies everyone's
     terminal to protect the LC_ALL=C minority is a regression.

Much of this is subprocess work because the codec is chosen when the
interpreter builds `sys.stdout`; an in-process test that patches it with a
`StringIO` gets a sink with no `encoding` at all and cannot see the defect.

The fix is `codecs.register_error` plus `reconfigure(errors=...)`, installed on
the stream by `install_human_channel()`, so there is no wrapper to unit-test
here: what these tests check is that each entry point installs it and that the
report comes out degraded rather than absent. The handler's own behaviour is
pinned in the Apache-2.0 skills' `tests/test_human_channel.py`, which can state
the same expectations without a proprietary import.

Issue: docs/issues/human-cli-output-locale-class.md.

Run:
    cd skills/docx/scripts
    ./.venv/bin/python -m unittest tests.test_errors_human -v
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import _errors  # noqa: E402
import _errors as H  # noqa: E402

EXAMPLES = SCRIPTS.parent / "examples"

#: The decoration these skills actually print. An explicit inventory rather
#: than a loop over `_errors._ASCII_FALLBACK`, so deleting a table entry breaks
#: a test instead of silently shrinking the coverage.
GLYPHS = {
    "—": "--", "…": "...", "→": "->", "✓": "+", "✗": "x", "⚠": "!", "§": "S",
}


def _env(**extra: str) -> dict:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONUTF8": "0"}
    env.update(extra)
    return env


def _ascii_env(**extra: str) -> dict:
    e = _env(PYTHONIOENCODING="ascii", LC_ALL="C", LANG="C")
    e.update(extra)
    return e


def _utf8_env(**extra: str) -> dict:
    e = _env(PYTHONIOENCODING="utf-8", LC_ALL="en_US.UTF-8", PYTHONUTF8="1")
    e.update(extra)
    return e


def _run(argv: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=str(SCRIPTS), env=env, timeout=180,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _strict(encoding: str) -> io.TextIOWrapper:
    """A real strict text stream — what `sys.stdout` is under an explicit
    PYTHONIOENCODING, and what a `StringIO` is not."""
    return io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors="strict")


class _FakeSink:
    """A text sink reporting an arbitrary `encoding`. `io.StringIO` cannot
    stand in: its `encoding` is a read-only `None`, which is exactly the case
    that skips degradation."""

    def __init__(self, encoding: object) -> None:
        self.encoding = encoding
        self._parts: list = []

    def write(self, text: str) -> int:
        self._parts.append(text)
        return len(text)

    def flush(self) -> None:
        pass

    def value(self) -> str:
        return "".join(self._parts)


# --------------------------------------------------------------------- #
# the codec error handler
# --------------------------------------------------------------------- #
class TestTheHandlerItself(unittest.TestCase):
    """`HUMAN_ERRORS` is a registered codec error handler, so every expectation
    here is written as an ordinary `errors=` argument rather than by calling
    into `_errors` — the same way the codec reaches it at runtime."""

    def test_a_codec_that_copes_is_never_consulted(self):
        """The UTF-8 case — nearly every real run. The handler only fires on a
        character the codec rejects, so a working machine's bytes are the bytes
        it always had."""
        text = "доклад — ECMA §2 [✓] [✗] → café"
        self.assertEqual(text.encode("utf-8", H.HUMAN_ERRORS).decode("utf-8"), text)

    def test_every_glyph_has_an_ascii_spelling(self):
        for glyph, expected in {"—": "--", "…": "...", "→": "->", "✓": "+",
                                "✗": "x", "⚠": "!", "§": "S"}.items():
            with self.subTest(glyph=glyph):
                self.assertEqual(glyph.encode("ascii", H.HUMAN_ERRORS).decode("ascii"),
                                 expected)

    def test_an_emoji_variation_selector_is_dropped_not_escaped(self):
        """`⚠️` is U+26A0 U+FE0F — one grapheme, two code points. Mapping only
        the base glyph left the selector to backslashreplace and a report read
        `!\ufe0f`."""
        self.assertEqual("⚠️".encode("ascii", H.HUMAN_ERRORS).decode("ascii"), "!")

    def test_a_multi_character_run_is_spelled_per_character(self):
        """The codec hands the handler a RUN, not a character. A handler that
        looked at `exc.object[exc.start]` alone would drop the rest, and
        `— ✓ →` in a report is exactly such a run."""
        self.assertEqual("a—✓→b".encode("ascii", H.HUMAN_ERRORS).decode("ascii"),
                         "a--+->b")

    def test_degradation_is_per_character_under_a_partial_codec(self):
        """cp1251 has Cyrillic and an em dash; it lacks a check mark. Only the
        check mark may move."""
        got = "доклад — ✓".encode("cp1251", H.HUMAN_ERRORS).decode("cp1251")
        self.assertEqual(got, "доклад — +")

    def test_a_charmap_codec_does_not_break_the_escape(self):
        """Every charmap codec — cp1251, cp1252, latin-1, cp850, cp932 —
        reports `exc.encoding == "charmap"`, the literal string, not its own
        name. Escaping through *that* silently returns the RAW BYTE rather than
        an escape, so `café` under cp1251 produced b"\xe9" and the following
        decode blew up. Measured; the handler escapes against ASCII instead."""
        for enc in ("cp1251", "cp1252", "latin-1", "cp850"):
            with self.subTest(encoding=enc):
                got = "café".encode(enc, H.HUMAN_ERRORS).decode(enc)
                got.encode(enc)

    def test_the_result_always_encodes(self):
        for label, text in {"cyrillic": "Привет", "latin1": "café",
                            "astral": "\U0001F600", "cjk": "日本語",
                            "lone surrogate": "/tmp/out\udcff.md"}.items():
            for enc in ("ascii", "cp1251", "cp1252", "utf-8", "latin-1"):
                with self.subTest(text=label, encoding=enc):
                    text.encode(enc, H.HUMAN_ERRORS).decode(enc).encode(enc)

    def test_a_lone_surrogate_survives_even_under_utf8(self):
        """UTF-8 is the one codec with no representation for U+DC80-DCFF, and
        POSIX puts them into str(path) via surrogateescape — so this crashed on
        a correctly configured machine."""
        path = "/tmp/out\udcff.md"
        with self.assertRaises(UnicodeEncodeError):
            path.encode("utf-8")
        self.assertEqual(path.encode("utf-8", H.HUMAN_ERRORS).decode("utf-8"),
                         "/tmp/out\\udcff.md")

    def test_a_decode_error_is_re_raised_rather_than_guessed_at(self):
        """Installed on a readable stream the handler would be asked to invent
        input rather than tidy output. Refuse."""
        with self.assertRaises(UnicodeDecodeError):
            b"\xe2\x80\x94".decode("ascii", H.HUMAN_ERRORS)


class TestInstallHumanChannel(unittest.TestCase):
    def test_it_points_the_stream_at_the_handler(self):
        stream = _strict("ascii")
        H.install_human_channel(stream)
        self.assertEqual(stream.errors, H.HUMAN_ERRORS)
        stream.write("report — ✓\n")
        stream.flush()
        self.assertEqual(stream.buffer.getvalue().decode("ascii"), "report -- +\n")

    def test_it_leaves_the_encoding_alone(self):
        """The distinction the whole fix rests on. `reconfigure(encoding=)`
        would override the caller's codec and produce mojibake in a cp1252
        terminal; `reconfigure(errors=)` changes only what happens to a
        character that codec cannot represent."""
        stream = _strict("cp1251")
        H.install_human_channel(stream)
        self.assertEqual(stream.encoding, "cp1251")

    def test_a_stream_that_cannot_be_reconfigured_is_not_an_error(self):
        for sink in (io.StringIO(), None, object(), _FakeSink("ascii")):
            with self.subTest(sink=type(sink).__name__):
                H.install_human_channel(sink)

    def test_stock_argparse_help_needs_no_subclass(self):
        """`--help` was 31 of the 102 measured findings, and the skill's own
        code never does that writing — argparse does, with a bare `file.write`
        whose guard catches AttributeError and OSError but not
        UnicodeEncodeError. With the handler on the stream the stock class is
        already safe."""
        stream = _strict("ascii")
        H.install_human_channel(stream)
        parser = argparse.ArgumentParser(prog="demo", description="Report — §2")
        parser.add_argument("--x", help="does a thing → fast")
        parser.print_help(stream)
        stream.flush()
        text = stream.buffer.getvalue().decode("ascii")
        self.assertIn("Report -- S2", text)
        self.assertIn("does a thing -> fast", text)


class TestDocxEntryPointsSurviveALegacyLocale(unittest.TestCase):
    """Property 1 and 2 end to end. Was: rc 1 and 0 bytes."""

    HELP = ["docx_replace.py", "docx_merge.py", "preview.py", "office_passwd.py",
            "docx_accept_changes.py", "docx_add_comment.py", "docx_fill_template.py"]

    def test_help_is_printed_in_full_and_the_exit_code_does_not_move(self):
        for script in self.HELP:
            with self.subTest(script=script):
                argv = [sys.executable, str(SCRIPTS / script), "--help"]
                ascii_run = _run(argv, _ascii_env())
                utf8_run = _run(argv, _utf8_env())
                self.assertEqual(ascii_run.returncode, utf8_run.returncode)
                self.assertEqual(ascii_run.returncode, 0)
                self.assertGreater(len(ascii_run.stdout), 0)
                self.assertNotIn(b"UnicodeEncodeError", ascii_run.stderr)
                ascii_run.stdout.decode("ascii")       # the assertion
                self.assertIn(b"usage:", ascii_run.stdout)

    def test_help_keeps_its_real_glyphs_under_utf8(self):
        """Property 3: the regression this fix most plausibly causes is
        ASCII-ifying everybody."""
        proc = _run([sys.executable, str(SCRIPTS / "docx_replace.py"), "--help"], _utf8_env())
        self.assertEqual(proc.returncode, 0)
        self.assertIn("—", proc.stdout.decode("utf-8"))


class TestValidateReportSurvivesUserData(unittest.TestCase):
    """The report path, not the help path. A VALID .docx that merely carries a
    scratch member with a non-ASCII name was enough to kill the whole report:
    measured rc 1 / 0 bytes where UTF-8 gives rc 0 and a 119-byte WARN. The
    member name comes from the package, so no amount of ASCII-ifying the
    source literals would have covered it."""

    def setUp(self) -> None:
        src = EXAMPLES / "docx_replace_body.docx"
        if not src.exists():
            self.skipTest(f"fixture missing: {src}")
        self.tmp = tempfile.mkdtemp(prefix="docx-human-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.leak = Path(self.tmp) / "leak.docx"
        shutil.copy(src, self.leak)
        with zipfile.ZipFile(self.leak, "a") as z:
            z.writestr("черновик-café.txt", "scratch\n")

    def test_the_warn_is_reported_and_the_verdict_is_unchanged(self):
        argv = [sys.executable, str(SCRIPTS / "office" / "validate.py"), str(self.leak)]
        for encoding in ("ascii", "cp1251"):
            with self.subTest(encoding=encoding):
                degraded = _run(argv, _ascii_env(PYTHONIOENCODING=encoding))
                reference = _run(argv, _utf8_env())
                self.assertNotIn(b"UnicodeEncodeError", degraded.stderr)
                self.assertEqual(degraded.returncode, reference.returncode)
                self.assertIn(b"WARN:", degraded.stdout)
                degraded.stdout.decode(encoding)       # the assertion
                # Not merely non-empty: the same number of report lines.
                self.assertEqual(len(degraded.stdout.splitlines()),
                                 len(reference.stdout.splitlines()))

    def test_utf8_still_prints_the_member_name_verbatim(self):
        proc = _run([sys.executable, str(SCRIPTS / "office" / "validate.py"), str(self.leak)],
                    _utf8_env())
        self.assertIn("черновик-café.txt", proc.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()

"""The HUMAN side of `_errors.py` — `ascii_fallback`, `say`, `HumanArgumentParser`.

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
# ascii_fallback
# --------------------------------------------------------------------- #
class TestAsciiFallbackLeavesWorkingCodecsAlone(unittest.TestCase):
    """Property 3 at the unit level: on a codec that can carry the string the
    function is the identity — not merely equal, the same object."""

    def test_utf8_text_is_returned_by_identity(self):
        text = "ECMA-376 §2 — доклад [✓] [✗] → ⚠ café"
        self.assertIs(_errors.ascii_fallback(text, "utf-8"), text)

    def test_pure_ascii_is_returned_by_identity_under_every_codec(self):
        text = "ECMA-376 S2 -- report [+] [x] -> ! ok"
        for enc in ("ascii", "utf-8", "cp1252", "cp1251", "utf-16"):
            with self.subTest(encoding=enc):
                self.assertIs(_errors.ascii_fallback(text, enc), text)


class TestAsciiFallbackSpellsTheDecoration(unittest.TestCase):
    def test_every_glyph_has_an_ascii_spelling(self):
        """No glyph may fall through to a `\\uXXXX` escape: the escape is the
        backstop for unforeseeable user data, not an acceptable rendering of
        the skills' own furniture."""
        for glyph, expected in GLYPHS.items():
            with self.subTest(glyph=glyph):
                self.assertEqual(_errors.ascii_fallback(glyph, "ascii"), expected)


class TestAsciiFallbackIsPerCharacter(unittest.TestCase):
    """Why this is not a blanket `.encode(errors=...)`: a codec must keep
    everything it CAN represent."""

    def test_cp1252_keeps_what_cp1252_has(self):
        got = _errors.ascii_fallback("café — ✓", "cp1252")
        self.assertEqual(got, "café — +")
        got.encode("cp1252")  # the assertion: still writable to that stream

    def test_cp1251_keeps_cyrillic_and_the_em_dash(self):
        got = _errors.ascii_fallback("доклад — ✓", "cp1251")
        self.assertEqual(got, "доклад — +")
        got.encode("cp1251")

    def test_ascii_degrades_the_same_strings_further(self):
        self.assertEqual(_errors.ascii_fallback("café — ✓", "ascii"), "caf\\xe9 -- +")


class TestAsciiFallbackAlwaysProducesWritableText(unittest.TestCase):
    """The backstop. Whatever goes in, the result must encode — otherwise
    `say` would still raise and the fix would be a narrower crash, not a fix."""

    CASES = {
        "cyrillic": "Привет",
        "latin1": "café naïve",
        "astral": "\U0001F600 done",
        "cjk": "日本語",
        "lone surrogate": "/tmp/out\udcff.docx",
        "ooxml member": "'черновик-café.txt' (scratch-file leak)",
    }

    def test_result_encodes_under_every_codec_a_caller_can_set(self):
        for label, text in self.CASES.items():
            for enc in ("ascii", "cp1252", "cp1251", "utf-8", "latin-1", "cp932"):
                with self.subTest(text=label, encoding=enc):
                    _errors.ascii_fallback(text, enc).encode(enc)

    def test_a_lone_surrogate_is_survivable_even_under_utf8(self):
        """UTF-8 is the one codec with no representation for U+DC80-DCFF, and
        POSIX puts them into `str(path)` via surrogateescape whenever a
        filename holds undecodable bytes. So this crashed on a *correctly*
        configured machine, with no exotic locale involved."""
        path = "/tmp/out\udcff.docx"
        with self.assertRaises(UnicodeEncodeError):
            path.encode("utf-8")                       # the defect, restated
        self.assertEqual(_errors.ascii_fallback(path, "utf-8"), "/tmp/out\\udcff.docx")


class TestTheCodecNameIsNotTrusted(unittest.TestCase):
    """A crash-preventer that crashes is worse than no preventer. `.encoding`
    is only conventionally a valid text-codec name."""

    BAD = {"unknown": "not-a-codec", "bytes codec": "base64", "not a str": 123}
    NO_CODEC = {"None": None, "empty": ""}

    def test_text_encodable_answers_false_instead_of_raising(self):
        """`_text_encodable` is guarded separately from `_usable_codec` and must
        hold on its own. Reached through `ascii_fallback` it never sees a bad
        codec — `_usable_codec` normalises those first — so without a direct
        test its guards are unverified: a mutation removing the `TypeError`
        catch survived the whole suite until this existed."""
        for label, enc in {**self.BAD, **self.NO_CODEC}.items():
            with self.subTest(encoding=label):
                self.assertIs(_errors._text_encodable("a — b", enc), False)
        self.assertIs(_errors._text_encodable("plain", "ascii"), True)
        self.assertIs(_errors._text_encodable("—", "ascii"), False)

    def test_ascii_fallback_degrades_instead_of_raising(self):
        for label, enc in {**self.BAD, **self.NO_CODEC}.items():
            with self.subTest(encoding=label):
                self.assertEqual(_errors.ascii_fallback("a — b", enc), "a -- b")

    def test_say_degrades_when_the_sink_claims_an_unusable_codec(self):
        for label, enc in self.BAD.items():
            with self.subTest(encoding=label):
                sink = _FakeSink(enc)
                _errors.say("✓ done — ok", file=sink)
                self.assertEqual(sink.value(), "+ done -- ok\n")

    def test_say_leaves_a_sink_that_claims_no_codec_alone(self):
        """`None` means "pure str sink", not "broken codec" — a StringIO
        reports exactly that, and degrading for it would mangle output that was
        never in danger."""
        for label, enc in self.NO_CODEC.items():
            with self.subTest(encoding=label):
                sink = _FakeSink(enc)
                _errors.say("✓ done — ok", file=sink)
                self.assertEqual(sink.value(), "✓ done — ok\n")


# --------------------------------------------------------------------- #
# say
# --------------------------------------------------------------------- #
class TestSayIsAPrintDropIn(unittest.TestCase):
    """The parameter is `file`, not `stream`, precisely so a mechanical
    `print(` -> `say(` migration cannot introduce a TypeError on a rare
    branch. Parity has to be tested, not asserted."""

    CASES = [
        ({}, "a b\n"), ({"sep": None}, "a b\n"), ({"end": None}, "a b\n"),
        ({"sep": "-"}, "a-b\n"), ({"end": "!"}, "a b!"),
        ({"flush": True}, "a b\n"), ({"flush": False}, "a b\n"),
        ({"sep": "", "end": ""}, "ab"),
    ]

    def test_say_matches_print_for_every_keyword_combination(self):
        for kwargs, expected in self.CASES:
            with self.subTest(kwargs=kwargs):
                mine, theirs = io.StringIO(), io.StringIO()
                _errors.say("a", "b", file=mine, **kwargs)
                print("a", "b", file=theirs, **kwargs)
                self.assertEqual(mine.getvalue(), expected)
                self.assertEqual(mine.getvalue(), theirs.getvalue(), "say diverged from print")

    def test_non_strings_are_stringified(self):
        buf = io.StringIO()
        _errors.say(7, None, file=buf)
        self.assertEqual(buf.getvalue(), "7 None\n")


class TestSayOnRealStreams(unittest.TestCase):
    def test_it_never_raises_on_a_strict_stream(self):
        stream = _strict("ascii")
        _errors.say("WARN:  non-OOXML package member: 'черновик-café.txt'", file=stream)
        stream.flush()
        self.assertIn(b"WARN:", stream.buffer.getvalue())
        stream.buffer.getvalue().decode("ascii")   # the assertion

    def test_it_does_not_write_utf8_into_a_cp1252_stream(self):
        """`write_json_stdout` forces UTF-8 bytes; this channel must not. A
        caller that declared cp1252 is entitled to cp1252."""
        stream = _strict("cp1252")
        _errors.say("café — done", file=stream)
        stream.flush()
        self.assertEqual(stream.buffer.getvalue(), b"caf\xe9 \x97 done\n")

    def test_a_closed_fd_1_is_a_silent_no_op_like_print(self):
        """`prog >&-`: CPython sets sys.stdout to None and print() quietly does
        nothing. Match that — the machine channel deliberately raises instead."""
        saved = sys.stdout
        sys.stdout = None
        try:
            _errors.say("✓ nobody is listening")   # must not raise
        finally:
            sys.stdout = saved

    def test_a_dead_pipe_redirects_the_fd_before_re_raising(self):
        """Without the redirect the interpreter flushes the same dead fd at
        shutdown, prints "Exception ignored while flushing sys.stdout" and
        replaces the exit status with 120."""
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        stream = io.TextIOWrapper(open(write_fd, "wb", buffering=0), encoding="ascii")
        self.addCleanup(stream.close)
        with self.assertRaises(BrokenPipeError):
            _errors.say("✓ into the void", file=stream)
        # The fd now points at /dev/null, so a second write succeeds where the
        # first died. That is the mechanism, not merely its symptom.
        stream.write("second write")
        stream.flush()


# --------------------------------------------------------------------- #
# HumanArgumentParser
# --------------------------------------------------------------------- #
class TestHumanArgumentParser(unittest.TestCase):
    """`--help` is human output too — the most-run of all, and the one no
    audit of `print()` call sites finds, because argparse does the writing."""

    def _parser(self) -> _errors.HumanArgumentParser:
        p = _errors.HumanArgumentParser(prog="demo", description="Validate — ECMA-376 §2")
        p.add_argument("--x", help="does a thing → fast")
        return p

    def test_help_reaches_a_strict_ascii_stream(self):
        stream = _strict("ascii")
        self._parser().print_help(stream)
        stream.flush()
        text = stream.buffer.getvalue().decode("ascii")
        self.assertIn("Validate -- ECMA-376 S2", text)
        self.assertIn("does a thing -> fast", text)

    def test_help_is_untouched_on_a_stream_that_can_take_it(self):
        stream = _strict("utf-8")
        self._parser().print_help(stream)
        stream.flush()
        text = stream.buffer.getvalue().decode("utf-8")
        self.assertIn("Validate — ECMA-376 §2", text)
        self.assertIn("does a thing → fast", text)

    def test_the_funnel_this_override_depends_on_still_exists(self):
        """A guard, not a tautology. `_print_message` is private by name; if a
        future CPython renames it or stops routing print_help through it, this
        fails loudly here instead of silently restoring the crash."""
        self.assertTrue(hasattr(argparse.ArgumentParser, "_print_message"))
        for method in ("print_help", "print_usage"):
            with self.subTest(method=method):
                self.assertIn("_print_message",
                              getattr(argparse.ArgumentParser, method).__code__.co_names)

    def test_it_composes_with_add_json_errors_argument(self):
        """`add_json_errors_argument` patches `parser.error` on the instance;
        this class overrides `_print_message`. They must not fight."""
        p = self._parser()
        _errors.add_json_errors_argument(p)
        stream = _strict("ascii")
        p.print_help(stream)
        stream.flush()
        self.assertIn(b"--json-errors", stream.buffer.getvalue())


# --------------------------------------------------------------------- #
# The real CLIs, real file descriptors, real locales
# --------------------------------------------------------------------- #
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

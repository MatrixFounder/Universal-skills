"""The human channel's contract: it degrades, it never dies, and it never
overrides the caller's codec.

The mirror image of ``test_stdout_channel``. That file pins the MACHINE
channel (JSON on stdout, UTF-8 regardless of locale); this one pins the
PRESENTATION channel (``fetch.py doctor`` and ``install_components.py``
without flags), whose contract is the opposite: obey the caller's codec, and
lose only what that codec genuinely cannot carry.

Three properties, in the order they were broken:

  1. **It produced its report.** Both commands used to die on their FIRST line
     under ``LC_ALL=C`` — 0 bytes, rc 1, ``UnicodeEncodeError`` on an em dash
     in a heading. A doctor that cannot say what is missing is worse than no
     doctor.
  2. **It did not change its answer.** The exit status under ``ascii`` must
     equal the exit status under UTF-8. A locale is a rendering choice; it is
     not allowed to alter the verdict.
  3. **It did not change its bytes on a working machine.** Under UTF-8 the
     pretty glyphs must still be there, byte for byte. A "fix" that ASCII-ifies
     everyone's terminal to protect the ``LC_ALL=C`` minority is a regression.

Why so much of this is subprocess work: the codec is chosen when the
interpreter builds ``sys.stdout``. An in-process test that patches
``sys.stdout`` with a ``StringIO`` gets a sink with no ``encoding`` at all and
cannot see the defect — which is exactly why the pre-existing doctor tests in
``test_doctor.py`` stayed green while the command was returning 0 bytes.

Issue: ``docs/issues/tf-human-report-locale-crash.md``.
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import _human  # noqa: E402

_FETCH = _SCRIPTS / "fetch.py"
_INSTALL = _SCRIPTS / "install_components.py"

# The exact characters the two reports print. Kept as an explicit inventory
# rather than a loop over `_human._ASCII_FALLBACK`, so that deleting a table
# entry breaks a test instead of silently shrinking its coverage.
GLYPHS = {
    "—": "--",    # em dash        headings, component labels
    "…": "...",   # ellipsis       "Installing ... "
    "→": "->",    # arrow          install hints
    "✓": "+",     # check mark     present / ready
    "✗": "x",     # ballot x       missing
    "⚠": "!",     # warning        no-ASR warning
}


def _base_env(**extra: str) -> dict:
    """A hermetic environment: no developer ``.env``, no tools on ``PATH``.

    An empty ``PATH`` is load-bearing, not hygiene. The non-ASCII decoration in
    these reports is densest where something is MISSING (the ``[✗]`` rows and
    their ``→`` hints); on a fully-equipped laptop the output would be nearly
    all-ASCII and the test would pass for the wrong reason.
    """
    env = {
        "PATH": "/nonexistent",
        "TRANSCRIPT_FETCHER_NO_DOTENV": "1",
        "PYTHONUTF8": "0",
    }
    env.update(extra)
    return env


def _ascii_env(**extra: str) -> dict:
    env = _base_env(PYTHONIOENCODING="ascii", LC_ALL="C", LANG="C")
    env.update(extra)
    return env


def _utf8_env(**extra: str) -> dict:
    env = _base_env(PYTHONIOENCODING="utf-8", LC_ALL="en_US.UTF-8")
    env.update(extra)
    return env


def _run(argv: list[str], env: dict, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, cwd=str(_SCRIPTS), env=env, timeout=timeout,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _run_with_dead_reader(argv: list[str], env: dict, timeout: int = 120):
    """Run ``argv`` with an fd 1 that has **no reader at all**, return (rc, stderr).

    Closing both ends in the parent is deliberate: with ``| head`` the outcome
    depends on whether the report happened to fit in the kernel pipe buffer
    before the reader exited, and a test that only sometimes reaches the defect
    is not a test. With zero readers the first write is guaranteed ``EPIPE``.
    """
    read_fd, write_fd = os.pipe()
    try:
        proc = subprocess.Popen(
            argv, cwd=str(_SCRIPTS), env=env,
            stdout=write_fd, stderr=subprocess.PIPE,
        )
    finally:
        os.close(write_fd)
        os.close(read_fd)
    _, err = proc.communicate(timeout=timeout)
    return proc.returncode, err


class _FakeSink:
    """A text sink that reports an arbitrary ``encoding``.

    ``io.StringIO`` cannot stand in here: its ``encoding`` is a read-only
    ``None``, which is precisely the case that skips degradation. To exercise
    a stream that CLAIMS a codec we need one we can set.
    """

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


def _strict(encoding: str) -> io.TextIOWrapper:
    """A real strict text stream — what ``sys.stdout`` actually is under
    ``LC_ALL=C``, and what a ``StringIO`` is not."""
    return io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors="strict")


# --------------------------------------------------------------------- #
# ascii_fallback — the pure function
# --------------------------------------------------------------------- #
class TestAsciiFallbackLeavesWorkingLocalesAlone(unittest.TestCase):
    """Property 3, at the unit level: on a codec that can carry the string,
    the function is the identity — not merely equal, but the same object."""

    def test_utf8_text_is_returned_unchanged_by_identity(self):
        text = "transcript-fetcher — doctor  [✓] [✗] → ⚠ café Привет"
        self.assertIs(_human.ascii_fallback(text, "utf-8"), text)

    def test_pure_ascii_is_returned_unchanged_under_every_codec(self):
        text = "transcript-fetcher -- doctor [+] [x] -> ! ok"
        for encoding in ("ascii", "utf-8", "cp1252", "utf-16"):
            with self.subTest(encoding=encoding):
                self.assertIs(_human.ascii_fallback(text, encoding), text)


class TestAsciiFallbackSpellsTheDecorations(unittest.TestCase):
    def test_every_glyph_the_reports_print_has_an_ascii_spelling(self):
        """No glyph may fall through to a ``\\uXXXX`` escape: the escape is the
        backstop for unforeseeable user data, not an acceptable rendering of
        the skill's own furniture."""
        for glyph, expected in GLYPHS.items():
            with self.subTest(glyph=glyph):
                self.assertEqual(_human.ascii_fallback(glyph, "ascii"), expected)

    def test_the_heading_that_used_to_kill_both_commands(self):
        self.assertEqual(
            _human.ascii_fallback("transcript-fetcher — doctor", "ascii"),
            "transcript-fetcher -- doctor",
        )


class TestAsciiFallbackIsPerCharacter(unittest.TestCase):
    """The reason this is not a blanket ``.encode(errors=...)``: a codec must
    keep everything it CAN represent. cp1252 has an em dash (0x97) and an é;
    it lacks a check mark. Only the check mark may move."""

    def test_cp1252_keeps_what_cp1252_has(self):
        got = _human.ascii_fallback("café — ✓", "cp1252")
        self.assertEqual(got, "café — +")
        got.encode("cp1252")  # the assertion: still writable to that stream

    def test_ascii_degrades_the_same_string_further(self):
        self.assertEqual(_human.ascii_fallback("café — ✓", "ascii"),
                         "caf\\xe9 -- +")


class TestAsciiFallbackAlwaysProducesWritableText(unittest.TestCase):
    """The backstop. Whatever comes in, the result must encode — otherwise
    ``say`` would still raise and the fix would be a narrower crash, not a fix."""

    CASES = {
        "cyrillic": "Привет",
        "latin1": "café naïve",
        "astral": "\U0001F600 done",
        "cjk": "日本語",
        "lone surrogate": "/tmp/out\udcff.txt",
        "mixed with glyphs": "✓ Привет — \U0001F600",
    }

    def test_result_encodes_under_every_codec_a_caller_can_set(self):
        for label, text in self.CASES.items():
            for encoding in ("ascii", "cp1252", "utf-8", "latin-1", "iso-2022-jp"):
                with self.subTest(text=label, encoding=encoding):
                    _human.ascii_fallback(text, encoding).encode(encoding)

    def test_a_lone_surrogate_is_survivable_even_under_utf8(self):
        """UTF-8 is the one codec with no representation for U+DC80-DCFF, and
        POSIX puts them into ``str(out_path)`` via ``surrogateescape`` whenever
        a filename holds undecodable bytes. So this crashed on a *correctly*
        configured machine, with no exotic locale involved."""
        path = "/tmp/out\udcff.txt"
        with self.assertRaises(UnicodeEncodeError):
            path.encode("utf-8")                       # the defect, restated
        self.assertEqual(_human.ascii_fallback(path, "utf-8"), "/tmp/out\\udcff.txt")


# --------------------------------------------------------------------- #
# say — the writer
# --------------------------------------------------------------------- #
class TestTheCodecNameIsNotTrusted(unittest.TestCase):
    """A crash-preventer that crashes is worse than no preventer.

    ``.encoding`` is only conventionally a valid text-codec name. A wrapper or
    proxy can report an unknown name, an empty string, a non-``str``, or a
    bytes-to-bytes codec like ``base64`` that ``str.encode`` refuses outright.
    Every ``encode`` in the degradation path would then raise — from inside
    the function whose entire purpose is to stop that exception.
    """

    #: Truthy but unusable — the sink CLAIMS a codec that cannot encode text.
    BAD = {"unknown": "not-a-codec", "bytes codec": "base64",
           "bytes codec 2": "rot13", "not a str": 123}
    #: Falsy — the sink claims NO codec, which is a different thing entirely.
    NO_CODEC = {"None": None, "empty": ""}

    def test_encodable_answers_false_instead_of_raising(self):
        """``_encodable`` is guarded separately from ``_usable`` and must hold
        on its own. Reached through ``ascii_fallback`` it never sees a bad
        codec — ``_usable`` normalises those first — so without a direct test
        its guards are unverified: a mutation removing the ``TypeError`` catch
        survived the whole suite until this existed."""
        for label, encoding in {**self.BAD, **self.NO_CODEC}.items():
            with self.subTest(encoding=label):
                self.assertIs(_human._encodable("a — b", encoding), False)
        self.assertIs(_human._encodable("plain", "ascii"), True)
        self.assertIs(_human._encodable("—", "ascii"), False)

    def test_ascii_fallback_degrades_instead_of_raising(self):
        """At the function level every one of these must degrade, because
        ``ascii_fallback`` has been asked to target that codec explicitly."""
        for label, encoding in {**self.BAD, **self.NO_CODEC}.items():
            with self.subTest(encoding=label):
                self.assertEqual(_human.ascii_fallback("a — b", encoding), "a -- b")

    def test_say_degrades_when_the_sink_claims_an_unusable_codec(self):
        for label, encoding in self.BAD.items():
            with self.subTest(encoding=label):
                sink = _FakeSink(encoding)
                _human.say("✓ done — ok", file=sink)
                self.assertEqual(sink.value(), "+ done -- ok\n")

    def test_say_leaves_a_sink_that_claims_no_codec_alone(self):
        """``None`` (and its degenerate twin ``""``) means "pure ``str`` sink",
        not "broken codec" — a ``StringIO`` reports exactly that. Degrading for
        it would mangle output that was never in danger, and would break the
        in-process doctor tests in ``test_doctor.py`` that assert on real check
        marks. The distinction is deliberate, so pin it."""
        for label, encoding in self.NO_CODEC.items():
            with self.subTest(encoding=label):
                sink = _FakeSink(encoding)
                _human.say("✓ done — ok", file=sink)
                self.assertEqual(sink.value(), "✓ done — ok\n")


class TestSayReallyIsAPrintDropIn(unittest.TestCase):
    """The docstring argues at length for signature parity with ``print`` (it
    is why the keyword is ``file``). Parity has to be tested, not asserted:
    ``print`` accepts ``sep=None``/``end=None`` as "use the default" and takes
    a ``flush`` keyword, and callers pass those through from their own
    optionals."""

    CASES = [
        ({}, "a b\n"),
        ({"sep": None}, "a b\n"),
        ({"end": None}, "a b\n"),
        ({"sep": "-"}, "a-b\n"),
        ({"end": "!"}, "a b!"),
        ({"flush": True}, "a b\n"),
        ({"flush": False}, "a b\n"),
        ({"sep": "", "end": ""}, "ab"),
    ]

    def test_say_matches_print_for_every_keyword_combination(self):
        for kwargs, expected in self.CASES:
            with self.subTest(kwargs=kwargs):
                mine, theirs = io.StringIO(), io.StringIO()
                _human.say("a", "b", file=mine, **kwargs)
                print("a", "b", file=theirs, **kwargs)
                self.assertEqual(mine.getvalue(), expected)
                self.assertEqual(mine.getvalue(), theirs.getvalue(),
                                 "say diverged from print")


class TestSayNeverRaisesOnAStrictStream(unittest.TestCase):
    def test_the_two_headings_reach_a_strict_ascii_stream(self):
        for heading in ("transcript-fetcher — doctor",
                        "transcript-fetcher — component status"):
            with self.subTest(heading=heading):
                stream = _strict("ascii")
                _human.say(heading, file=stream)
                stream.flush()
                self.assertEqual(stream.buffer.getvalue(),
                                 heading.replace("—", "--").encode("ascii") + b"\n")

    def test_user_data_no_table_can_anticipate(self):
        """``TRANSCRIPT_FETCHER_MW_BIN`` is interpolated straight into a
        component label. ASCII-ifying the source literals would not have
        covered this — measured: an all-ASCII format string with a Cyrillic
        argument still raises."""
        stream = _strict("ascii")
        _human.say("  [x] MacWhisper CLI ('/opt/шёпот/mw')", file=stream)
        stream.flush()
        self.assertIn(b"\\u0448", stream.buffer.getvalue())


class TestHumanArgumentParser(unittest.TestCase):
    """``--help`` is human output too — the most-run of all, and the one no
    audit of ``print()`` sites finds, because argparse does the writing."""

    def _parser(self) -> _human.HumanArgumentParser:
        p = _human.HumanArgumentParser(prog="demo", description="A tool — with prose.")
        p.add_argument("--timeout", help="seconds — 0 disables it → forever")
        return p

    def test_help_reaches_a_strict_ascii_stream(self):
        stream = _strict("ascii")
        self._parser().print_help(stream)
        stream.flush()
        text = stream.buffer.getvalue().decode("ascii")
        self.assertIn("A tool -- with prose.", text)
        self.assertIn("0 disables it -> forever", text)

    def test_help_is_untouched_on_a_stream_that_can_take_it(self):
        stream = _strict("utf-8")
        self._parser().print_help(stream)
        stream.flush()
        text = stream.buffer.getvalue().decode("utf-8")
        self.assertIn("A tool — with prose.", text)
        self.assertIn("0 disables it → forever", text)

    def test_usage_and_error_go_through_the_same_override(self):
        """``error()`` reaches ``_print_message`` via ``exit()``, not via
        ``print_help`` — which is why the override is on the funnel and not on
        the public methods."""
        stream = _strict("ascii")
        parser = self._parser()
        with self.assertRaises(SystemExit) as caught:
            parser._print_message("boom — now\n", stream)
            raise SystemExit(2)
        self.assertEqual(caught.exception.code, 2)
        stream.flush()
        self.assertIn(b"boom -- now", stream.buffer.getvalue())

    def test_the_funnel_this_override_depends_on_still_exists(self):
        """A guard, not a tautology. ``_print_message`` is private by name; if
        a future CPython renames it or stops routing ``print_help`` through it,
        this fails loudly here instead of silently restoring the crash in
        production."""
        self.assertTrue(hasattr(argparse.ArgumentParser, "_print_message"))
        self.assertIn(
            "_print_message",
            argparse.ArgumentParser.print_help.__code__.co_names,
        )
        self.assertIn(
            "_print_message",
            argparse.ArgumentParser.print_usage.__code__.co_names,
        )


class TestSayHonoursTheCallersCodec(unittest.TestCase):
    def test_it_does_not_write_utf8_into_a_cp1252_stream(self):
        """The machine channel forces UTF-8 bytes; this channel must not.
        Writing 0xE2 0x80 0x94 to a cp1252 terminal is mojibake — the caller
        declared a codec and is entitled to it."""
        stream = _strict("cp1252")
        _human.say("café — done", file=stream)
        stream.flush()
        self.assertEqual(stream.buffer.getvalue(), b"caf\xe9 \x97 done\n")

    def test_a_sink_without_an_encoding_gets_the_text_verbatim(self):
        """A ``StringIO`` holds ``str``, not bytes, so there is no codec to
        respect and nothing to degrade. This is what keeps the in-process
        doctor tests in ``test_doctor.py`` asserting on real check marks."""
        buf = io.StringIO()
        _human.say("✓ Ready.", file=buf)
        self.assertEqual(buf.getvalue(), "✓ Ready.\n")


class TestSayMatchesPrintsSignature(unittest.TestCase):
    def test_sep_and_end(self):
        buf = io.StringIO()
        _human.say("a", "b", sep="-", end="!", file=buf)
        self.assertEqual(buf.getvalue(), "a-b!")

    def test_no_arguments_is_a_blank_line(self):
        buf = io.StringIO()
        _human.say(file=buf)
        self.assertEqual(buf.getvalue(), "\n")

    def test_non_strings_are_stringified(self):
        buf = io.StringIO()
        _human.say(7, None, file=buf)
        self.assertEqual(buf.getvalue(), "7 None\n")

    def test_the_keyword_is_file_exactly_as_in_print(self):
        """Not bikeshedding — a guard. Every call site is a converted
        ``print``, and ``install_components._install_whisper`` converts one
        that passes ``file=sys.stderr``. Naming this parameter anything else
        turns that line into a ``TypeError`` on a branch reachable only when
        pip fails, which is why no existing test would have caught it."""
        buf = io.StringIO()
        _human.say("✗ pip install failed", file=buf)
        self.assertEqual(buf.getvalue(), "✗ pip install failed\n")


class TestTheRarelyReachedBranchesStillRun(unittest.TestCase):
    """The report paths a happy-path suite never enters. These carry the same
    decorations as the main report and were converted in the same sweep, so
    they need the same proof that the conversion did not break them."""

    def test_the_pip_failure_line(self):
        import install_components as ic

        out, err = _strict("ascii"), _strict("ascii")
        with mock.patch.object(ic.subprocess, "run",
                               return_value=mock.Mock(returncode=1)), \
                mock.patch.object(sys, "stderr", err), \
                mock.patch.object(sys, "stdout", out):
            rc = ic._install_whisper()
        self.assertEqual(rc, 1)
        err.flush()
        self.assertIn(b"x pip install failed", err.buffer.getvalue())

    def test_the_pip_success_line(self):
        """The other half of `_install_whisper`, and the reason the sink here
        is a STRICT ascii stream rather than a `StringIO`: a `StringIO` holds
        ``str``, so `print` and `say` are indistinguishable against it and a
        mutation reverting this call site to `print` survives. Against a
        strict stream `print` raises and `say` degrades — which is the whole
        property under test."""
        import install_components as ic

        out, err = _strict("ascii"), _strict("ascii")
        with mock.patch.object(ic.subprocess, "run",
                               return_value=mock.Mock(returncode=0)), \
                mock.patch.object(sys, "stderr", err), \
                mock.patch.object(sys, "stdout", out):
            rc = ic._install_whisper()
        self.assertEqual(rc, 0)
        out.flush()
        self.assertIn(b"+ openai-whisper installed", out.buffer.getvalue())

    def test_the_dry_run_system_install_report(self):
        import install_components as ic

        out = io.StringIO()
        components = [{"key": "ffmpeg", "label": "ffmpeg — needed", "present": False,
                       "required": False, "kind": "system", "sys_cmd": "brew install ffmpeg"}]
        with mock.patch.object(sys, "stdout", out):
            rc = ic._system_install(components, run=False)
        self.assertEqual(rc, 0)
        self.assertIn("brew install ffmpeg", out.getvalue())
        self.assertIn("Dry run", out.getvalue())


class TestSayOnAVanishedStdout(unittest.TestCase):
    def test_a_closed_fd_1_is_a_silent_no_op_like_print(self):
        """``prog >&-``: CPython sets ``sys.stdout`` to None and ``print()``
        quietly does nothing. Match that rather than raising — a dropped
        progress line is not a broken promise, and an AttributeError inside a
        report loop would be a new crash where we just removed one. (The
        machine channel deliberately makes the opposite choice.)"""
        saved = sys.stdout
        sys.stdout = None
        try:
            _human.say("✓ nobody is listening")   # must not raise
        finally:
            sys.stdout = saved


class TestSayOnADeadPipe(unittest.TestCase):
    def test_it_redirects_the_fd_before_re_raising(self):
        """Without the redirect the interpreter flushes the same dead fd at
        shutdown, prints ``Exception ignored while flushing sys.stdout`` and
        **replaces the exit status with 120**."""
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        stream = io.TextIOWrapper(open(write_fd, "wb", buffering=0), encoding="ascii")
        self.addCleanup(stream.close)
        with self.assertRaises(BrokenPipeError):
            _human.say("✓ into the void", file=stream)
        # The fd now points at /dev/null, so a second write succeeds where the
        # first died. That is the mechanism, not merely its symptom — a test
        # that only asserted "rc is not 120" would pass against a no-op.
        stream.write("second write")
        stream.flush()


# --------------------------------------------------------------------- #
# The real commands, real file descriptors, real locales
# --------------------------------------------------------------------- #
class TestTheReportsSurviveALegacyLocale(unittest.TestCase):
    """Property 1. Was: rc 1 and 0 bytes for both, on a clean install."""

    # `--system` without `--run` is the documented dry-run form (SKILL.md):
    # it prints the package-manager commands and executes nothing. It reaches
    # `_system_install`'s own decorations, a second crash site behind the same
    # `_print_report` that kills the plain invocation first.
    COMMANDS = {
        "install_components.py": [sys.executable, str(_INSTALL)],
        "install_components.py --system": [sys.executable, str(_INSTALL), "--system"],
        "fetch.py doctor": [sys.executable, str(_FETCH), "doctor"],
    }

    def test_the_report_is_produced_and_is_readable_in_the_callers_codec(self):
        for label, argv in self.COMMANDS.items():
            for encoding in ("ascii", "cp1252"):
                with self.subTest(command=label, encoding=encoding):
                    proc = _run(argv, _ascii_env(PYTHONIOENCODING=encoding))
                    self.assertGreater(len(proc.stdout), 0, "no report at all")
                    self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
                    proc.stdout.decode(encoding)       # the assertion
                    self.assertIn(b"transcript-fetcher", proc.stdout)

    def test_the_exit_status_does_not_depend_on_the_locale(self):
        """Property 2. The doctor's verdict is a fact about the machine, not
        about the terminal; rc 1 (an encoding crash) where UTF-8 says 7 is the
        command contradicting itself."""
        for label, argv in self.COMMANDS.items():
            with self.subTest(command=label):
                self.assertEqual(_run(argv, _ascii_env()).returncode,
                                 _run(argv, _utf8_env()).returncode)

    def test_non_ascii_user_data_does_not_bring_it_back(self):
        """The env override lands inside a printed component label. This is the
        axis an ASCII-literals-only fix would have left open."""
        env = _ascii_env(TRANSCRIPT_FETCHER_MW_BIN="/opt/шёпот/mw")
        for label, argv in self.COMMANDS.items():
            with self.subTest(command=label):
                proc = _run(argv, env)
                self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
                self.assertGreater(len(proc.stdout), 0)
                proc.stdout.decode("ascii")


class TestHelpSurvivesALegacyLocale(unittest.TestCase):
    """Was: ``fetch.py --help`` → rc 1, **0 bytes**, killed by one em dash 2350
    characters into the listing (the ``--media-timeout-sec`` help)."""

    HELP = {
        "fetch.py --help": [sys.executable, str(_FETCH), "--help"],
        "fetch.py doctor --help": [sys.executable, str(_FETCH), "doctor", "--help"],
        "install_components.py --help": [sys.executable, str(_INSTALL), "--help"],
    }

    def test_help_is_printed_in_full_under_ascii(self):
        for label, argv in self.HELP.items():
            with self.subTest(command=label):
                proc = _run(argv, _ascii_env())
                self.assertEqual(proc.returncode, 0)
                self.assertGreater(len(proc.stdout), 0)
                self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
                proc.stdout.decode("ascii")
                self.assertIn(b"usage:", proc.stdout)

    def test_help_keeps_its_em_dashes_under_utf8(self):
        proc = _run([sys.executable, str(_FETCH), "--help"], _utf8_env())
        self.assertEqual(proc.returncode, 0)
        self.assertIn("—", proc.stdout.decode("utf-8"))

    def test_the_argparse_error_path_still_behaves_like_argparse(self):
        """Fixing the encoding must not change the CLI contract: an unknown
        flag is still rc 2, still usage on stderr, still nothing on stdout."""
        proc = _run([sys.executable, str(_FETCH), "--nope"], _ascii_env())
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, b"")
        self.assertIn(b"usage:", proc.stderr)
        self.assertNotIn(b"UnicodeEncodeError", proc.stderr)


class TestTheReportIsWholeNotMerelyNonEmpty(unittest.TestCase):
    """The gap a "did it print anything?" assertion cannot see.

    The defect was a crash PART WAY THROUGH a write sequence, so "stdout is
    non-empty" is satisfied by a fix that emits the heading and then dies —
    which is exactly what the pre-fix code did under cp1251 (39 bytes of
    `install_components.py`, 161 of `doctor`, then UnicodeEncodeError). These
    tests pin the whole report instead: same number of lines as the UTF-8 run,
    and the LAST line present, not just the first.
    """

    COMMANDS = {
        "install_components.py": [sys.executable, str(_INSTALL)],
        "install_components.py --system": [sys.executable, str(_INSTALL), "--system"],
        "fetch.py doctor": [sys.executable, str(_FETCH), "doctor"],
        "fetch.py --help": [sys.executable, str(_FETCH), "--help"],
    }

    def test_the_degraded_report_has_as_many_lines_as_the_utf8_one(self):
        for label, argv in self.COMMANDS.items():
            for encoding in ("ascii", "cp1251", "cp932"):
                with self.subTest(command=label, encoding=encoding):
                    degraded = _run(argv, _ascii_env(PYTHONIOENCODING=encoding))
                    reference = _run(argv, _utf8_env())
                    self.assertEqual(
                        degraded.stdout.decode(encoding).splitlines().__len__(),
                        reference.stdout.decode("utf-8").splitlines().__len__(),
                        f"{label} under {encoding} is truncated, not degraded",
                    )

    def test_the_last_line_survives_not_only_the_heading(self):
        """cp1251 got 39 bytes out before dying — the heading alone. Pin the
        tail so a fix that only rescues the first write cannot pass."""
        for label, argv in self.COMMANDS.items():
            for encoding in ("ascii", "cp1251"):
                with self.subTest(command=label, encoding=encoding):
                    reference = _run(argv, _utf8_env()).stdout.decode("utf-8").splitlines()
                    degraded = _run(argv, _ascii_env(PYTHONIOENCODING=encoding)).stdout.decode(encoding).splitlines()
                    self.assertTrue(reference and degraded)
                    # Compare on the ASCII skeleton: the decoration differs by
                    # design, the words must not.
                    self.assertEqual(
                        "".join(c for c in degraded[-1] if c.isalnum()),
                        "".join(c for c in reference[-1] if c.isalnum()),
                    )


class TestTheComponentsPresentBranch(unittest.TestCase):
    """`PATH=/nonexistent` everywhere else means every component is MISSING, so
    the `✓` rows and the "at least one ASR backend" summary — a different set
    of literals, on a branch the rest of this file never enters — went
    untested. Give the probes something to find."""

    TOOLS = ("yt-dlp", "ffmpeg", "mw", "whisper", "whisper-cli")

    def _stub_path(self) -> str:
        d = tempfile.mkdtemp(prefix="tf-human-stubs-")
        self.addCleanup(shutil.rmtree, d, True)
        for tool in self.TOOLS:
            exe = Path(d) / tool
            exe.write_text("#!/bin/sh\necho 0.0.0\n")
            exe.chmod(0o755)
        return d

    def test_the_present_branch_degrades_instead_of_crashing(self):
        env = _ascii_env(PATH=self._stub_path())
        for label, argv in {
            "install_components.py": [sys.executable, str(_INSTALL)],
            "fetch.py doctor": [sys.executable, str(_FETCH), "doctor"],
        }.items():
            with self.subTest(command=label):
                proc = _run(argv, env)
                self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
                text = proc.stdout.decode("ascii")
                self.assertIn("[+]", text)          # the degraded check mark
                # Raw string on purpose. The point is that the check mark was
                # SPELLED "+", not escaped to the six characters backslash-u-2-7-1-3.
                # Written as a normal literal this would BE the ✓ character, which
                # ASCII-decoded text can never contain — a vacuously passing test.
                self.assertNotIn(r"\u2713", text)

    def test_the_ready_verdict_line_is_reached(self):
        """`fetch.py doctor` ends in `✓ Ready.` only when nothing is missing —
        unreachable while every other subprocess test pins PATH=/nonexistent.
        A mutation reverting that one `say` to `print` survived the whole suite
        until this test existed."""
        proc = _run([sys.executable, str(_FETCH), "doctor"],
                    _ascii_env(PATH=self._stub_path()))
        self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
        self.assertIn("+ Ready.", proc.stdout.decode("ascii"))

    def test_the_same_run_under_utf8_still_shows_a_real_check_mark(self):
        proc = _run([sys.executable, str(_INSTALL)], _utf8_env(PATH=self._stub_path()))
        self.assertIn("✓", proc.stdout.decode("utf-8"))


class TestAWorkingLocaleIsUntouched(unittest.TestCase):
    """Property 3, end to end. The regression this fix most plausibly causes is
    ASCII-ifying everybody, so pin the glyphs rather than merely 'it ran'."""

    def test_utf8_output_still_carries_the_real_glyphs(self):
        proc = _run([sys.executable, str(_INSTALL)], _utf8_env())
        self.assertEqual(proc.returncode, 0)
        text = proc.stdout.decode("utf-8")
        # `✓` is absent by construction, not by accident: PATH=/nonexistent
        # means no ASR backend, so the report takes its `⚠` branch. The check
        # mark is covered under a working locale by `test_doctor`.
        for glyph in ("—", "✗", "→", "⚠"):
            with self.subTest(glyph=glyph):
                self.assertIn(glyph, text)

    def test_utf8_output_shows_no_sign_of_the_ascii_fallback(self):
        """Anchored on the exact strings the fallback would produce, NOT on a
        bare search for `--` or `x`: this report legitimately contains
        `--asr-allow-cloud` and `--install-whisper`, and a naive negative
        assertion fails on those instead of on a regression."""
        proc = _run([sys.executable, str(_INSTALL)], _utf8_env())
        text = proc.stdout.decode("utf-8")
        for degraded in ("transcript-fetcher -- component status",
                         "REQUIRED -- metadata", "[x]", "[+]", "\\u"):
            with self.subTest(degraded=degraded):
                self.assertNotIn(degraded, text)


class TestTheHumanReportsDoNotRewriteTheExitStatus(unittest.TestCase):
    """The pipe axis, closed for JSON by ``_stdout`` and left open here:
    ``fetch.py doctor | <reader that exits>`` reported 120 while its real
    answer was 7, and ``install_components.py`` reported 120 for 0."""

    def test_a_dead_reader_does_not_produce_120(self):
        for label, argv in {
            "install_components.py": [sys.executable, str(_INSTALL)],
            "fetch.py doctor": [sys.executable, str(_FETCH), "doctor"],
        }.items():
            with self.subTest(command=label):
                rc, err = _run_with_dead_reader(argv, _utf8_env())
                self.assertNotEqual(rc, 120)
                self.assertNotIn(b"Exception ignored", err)


if __name__ == "__main__":
    unittest.main()

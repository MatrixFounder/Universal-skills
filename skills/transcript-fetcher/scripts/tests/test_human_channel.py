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


def _installed(encoding: str) -> io.TextIOWrapper:
    """A strict stream with the human channel installed on it.

    Under the wrapper-based fix each call site degraded for itself, so a bare
    strict stream was enough to tell `print` from `say`. The fix now belongs to
    the STREAM, so a test that patches `sys.stdout` has to configure what it
    patched in — otherwise it is measuring an unconfigured stream and would
    fail against perfectly correct code.
    """
    stream = _strict(encoding)
    _human.install_human_channel(stream)
    return stream


def _strict(encoding: str) -> io.TextIOWrapper:
    """A real strict text stream — what ``sys.stdout`` actually is under
    ``LC_ALL=C``, and what a ``StringIO`` is not."""
    return io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors="strict")


# --------------------------------------------------------------------- #
# the codec error handler
# --------------------------------------------------------------------- #
class TestTheRarelyReachedBranchesStillRun(unittest.TestCase):
    """The report paths a happy-path suite never enters. These carry the same
    decorations as the main report and were converted in the same sweep, so
    they need the same proof that the conversion did not break them."""

    def test_the_pip_failure_line(self):
        import install_components as ic

        out, err = _installed("ascii"), _installed("ascii")
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
        is a real byte stream rather than a `StringIO`: a `StringIO` holds
        ``str``, so it accepts an em dash whatever the locale says and the
        property under test cannot fail. Against a strict ascii stream with
        the handler installed, the line degrades; against one without it, the
        same line raises."""
        import install_components as ic

        out, err = _installed("ascii"), _installed("ascii")
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

    def _stub_dirs(self) -> dict:
        """PATH and PYTHONPATH in which every component probe succeeds.

        Two probes, two mechanisms. The ASR backends are looked up on PATH, so
        a stub executable satisfies them. **yt-dlp is not**: `doctor` asks
        `importlib.metadata.version("yt-dlp")`, which reads installed
        *distributions* and never consults PATH. Stubbing only the executable
        left yt-dlp MISSING, the "Ready." line unreachable, and this class's
        verdict test passing or failing with whatever the developer's
        interpreter happened to have installed. A `.dist-info` directory on
        PYTHONPATH is what `importlib.metadata` actually scans, so this makes
        the run hermetic instead of hopeful.
        """
        d = tempfile.mkdtemp(prefix="tf-human-stubs-")
        self.addCleanup(shutil.rmtree, d, True)
        for tool in self.TOOLS:
            exe = Path(d) / tool
            exe.write_text("#!/bin/sh\necho 0.0.0\n")
            exe.chmod(0o755)
        site = Path(d) / "site"
        dist = site / "yt_dlp-0.0.0.dist-info"
        dist.mkdir(parents=True)
        (dist / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: yt-dlp\nVersion: 0.0.0\n")
        return {"PATH": d, "PYTHONPATH": str(site)}

    def _stub_env(self, **extra: str) -> dict:
        return _ascii_env(**self._stub_dirs(), **extra)

    def test_the_present_branch_degrades_instead_of_crashing(self):
        env = self._stub_env()
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
        proc = _run([sys.executable, str(_FETCH), "doctor"], self._stub_env())
        self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
        self.assertIn("+ Ready.", proc.stdout.decode("ascii"))

    def test_the_same_run_under_utf8_still_shows_a_real_check_mark(self):
        proc = _run([sys.executable, str(_INSTALL)], _utf8_env(**self._stub_dirs()))
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

    def test_utf8_output_shows_no_sign_of_the_degradation(self):
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

    COMMANDS = {
        "install_components.py": [sys.executable, str(_INSTALL)],
        "fetch.py doctor": [sys.executable, str(_FETCH), "doctor"],
    }

    def test_a_dead_reader_does_not_produce_120(self):
        for label, argv in self.COMMANDS.items():
            with self.subTest(command=label):
                rc, err = _run_with_dead_reader(argv, _utf8_env())
                self.assertNotEqual(rc, 120)
                self.assertNotIn(b"Exception ignored", err)

    def test_a_dead_reader_is_reported_rather_than_passed_off_as_success(self):
        """The half `assertNotEqual(rc, 120)` cannot see.

        `install_human_channel` closes this in two independent steps, and only
        one of them shows up in the exit code. The atexit guard stops the
        shutdown flush from rewriting the status — but on its own it would let
        a BLOCK-buffered stdout swallow the failure entirely: nothing raises
        while `main()` runs, the CLI's `except BrokenPipeError` arm never runs,
        and the command exits 0 having delivered nothing. Reporting success for
        a report that reached no one is worse than reporting 120.

        `line_buffering=True` is what makes the write itself fail where the
        CLI can see it. Dropping it survived every other test in this file.
        """
        for label, argv in self.COMMANDS.items():
            with self.subTest(command=label):
                rc, err = _run_with_dead_reader(argv, _utf8_env())
                self.assertIn(b"broken pipe", err.lower(),
                              "%s exited %d without saying its output was lost"
                              % (label, rc))
                self.assertNotEqual(rc, 0,
                                    "%s reported success with a dead reader" % label)


if __name__ == "__main__":
    unittest.main()

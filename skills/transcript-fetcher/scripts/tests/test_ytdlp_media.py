"""Tests for the shared yt-dlp media core (`_ytdlp_media`).

Subprocess is mocked — these assert argv shape for the clip (--download-sections),
browser-cookie passthrough, and ffprobe duration parsing. No network, no yt-dlp.

The `download_audio` tests fake `subprocess.Popen` rather than `subprocess.run`:
that path runs through `run_in_process_group` (TF-X-7), so the real
process-group teardown code stays under test instead of being mocked away. One
test in `TestTimeoutKillsProcessGroup` DOES spawn real processes (a `/bin/sh`
stand-in for the yt-dlp→ffmpeg parent/child pair) — it is the only honest
reproduction of the orphan the fix exists to prevent, and it is POSIX-gated.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import _procgroup  # noqa: E402
from sources import _ytdlp_media as ytm  # noqa: E402

_HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _proc(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _fake_popen(captured=None, *, on_start=None, returncode=0, stdout="", stderr="",
                hangs=False, pid=424242):
    """Build a `subprocess.Popen` replacement for `run_in_process_group`.

    Implements only the surface that helper touches: `communicate`, `wait`,
    `kill`, `pid`, `returncode`, and the context-manager protocol. `hangs=True`
    makes every `communicate`/`wait` raise `TimeoutExpired` until something
    sets `returncode` — which is how a test simulates "the group kill worked".
    `captured` receives `argv`, `kwargs` and the live `proc` object.
    """
    class _FakeProc:
        def __init__(self, args, **kwargs):
            self.args = list(args)
            self.pid = pid
            self.returncode = None
            self.direct_kills = 0
            self.stdout = self.stderr = self.stdin = None
            if captured is not None:
                captured["argv"] = list(args)
                captured["kwargs"] = dict(kwargs)
                captured["proc"] = self
            if on_start is not None:
                on_start(list(args))

        def communicate(self, timeout=None):
            if hangs and self.returncode is None:
                raise subprocess.TimeoutExpired(self.args, timeout)
            if self.returncode is None:
                self.returncode = returncode
            return stdout, stderr

        def wait(self, timeout=None):
            if self.returncode is None:
                raise subprocess.TimeoutExpired(self.args, timeout)
            return self.returncode

        def kill(self):
            self.direct_kills += 1
            self.returncode = -9

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return _FakeProc


class TestDownloadAudioArgv(unittest.TestCase):
    def test_clip_and_browser_cookies_with_ffmpeg(self) -> None:
        captured: dict = {}
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)

            def touch(argv):
                (workdir / "media.mp4").write_bytes(b"x")

            with mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(_procgroup.subprocess, "Popen",
                                   _fake_popen(captured, on_start=touch)):
                media, err = ytm.download_audio(
                    "https://x.com/i/broadcasts/z", workdir,
                    max_duration_min=30, cookies_from_browser="chrome",
                )
            argv = captured["argv"]
            # ffmpeg present → audio-only extraction
            self.assertIn("-x", argv)
            self.assertIn("--audio-format", argv)
            # clip: first 30 min == 1800 s
            self.assertIn("--download-sections", argv)
            self.assertIn("*0-1800", argv)
            # browser cookies passed through to yt-dlp
            self.assertIn("--cookies-from-browser", argv)
            self.assertIn("chrome", argv)
            self.assertIsNotNone(media)

    def test_no_clip_without_ffmpeg(self) -> None:
        captured: dict = {}
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)

            def touch(argv):
                (workdir / "media.mp4").write_bytes(b"x")

            with mock.patch.object(ytm, "ffmpeg_available", return_value=False), \
                 mock.patch.object(_procgroup.subprocess, "Popen",
                                   _fake_popen(captured, on_start=touch)):
                ytm.download_audio(
                    "https://x.com/i/broadcasts/z", workdir, max_duration_min=30,
                )
            argv = captured["argv"]
            # the clip lives inside the ffmpeg branch → absent without ffmpeg
            self.assertNotIn("--download-sections", argv)
            self.assertNotIn("-x", argv)


class TestConcurrentFragments(unittest.TestCase):
    """`--concurrent-fragments` argv wiring on the media download (arch-016 §10.1,
    task-029.01 TC-01..04). ffmpeg is mocked absent so the argv assertions stay
    independent of whether the host actually has ffmpeg installed."""

    @staticmethod
    def _download_argv(**kwargs) -> list:
        captured: dict = {}
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)

            def touch(argv):
                (workdir / "media.mp4").write_bytes(b"x")

            with mock.patch.object(ytm, "ffmpeg_available", return_value=False), \
                 mock.patch.object(_procgroup.subprocess, "Popen",
                                   _fake_popen(captured, on_start=touch)):
                ytm.download_audio("https://x.com/i/broadcasts/z", workdir, **kwargs)
        return captured["argv"]

    def test_default_emits_8(self) -> None:
        argv = self._download_argv()
        self.assertIn("--concurrent-fragments", argv)
        i = argv.index("--concurrent-fragments")
        self.assertEqual(argv[i + 1], "8")
        # Regression: the pre-existing non-concurrency argv shape is unchanged.
        self.assertIn("-f", argv)
        self.assertIn("--output", argv)
        self.assertIn("--no-playlist", argv)

    def test_explicit_value_passed_through(self) -> None:
        argv = self._download_argv(concurrent_fragments=16)
        i = argv.index("--concurrent-fragments")
        self.assertEqual(argv[i + 1], "16")

    def test_over_range_clamped_to_32(self) -> None:
        argv = self._download_argv(concurrent_fragments=99)
        i = argv.index("--concurrent-fragments")
        self.assertEqual(argv[i + 1], "32")

    def test_serial_value_of_1_reproduces_pre_029_behaviour(self) -> None:
        argv = self._download_argv(concurrent_fragments=1)
        i = argv.index("--concurrent-fragments")
        self.assertEqual(argv[i + 1], "1")


class TestProcgroupStaysSourceNeutral(unittest.TestCase):
    """`_procgroup` must not import from `sources/` or `asr/` (TF-X-8).

    That rule is the whole reason the runner lives in a top-level module: both
    packages import it, and `sources/x.py` + `sources/yandex.py` already do a
    module-level `from asr._base import DEFAULT_ASR_TIMEOUT_SEC`, so a single
    edge back the other way closes an import cycle. Nothing else in this repo
    would catch that — there is no import-lint gate for this skill — so the
    rule is locked in here, the way CLAUDE.md locks the html skill's
    weasyprint/playwright exclusion with a sys.modules assertion.
    """

    def test_no_first_party_imports_in_the_source(self) -> None:
        import ast

        tree = ast.parse(Path(_procgroup.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:      # any relative import is first-party
                    imported.add(f".{node.module or ''}")
                elif node.module:
                    imported.add(node.module.split(".")[0])
        self.assertEqual(
            imported & {"sources", "asr", "_config", "fetch"}, set(),
            f"_procgroup must stay source-neutral; found {sorted(imported)}",
        )
        self.assertFalse([m for m in imported if m.startswith(".")])

    def test_importing_it_pulls_in_no_first_party_module(self) -> None:
        # Belt-and-braces against a deferred/function-local import sneaking in.
        import subprocess as _sp
        out = _sp.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r); import _procgroup; "
             "print([m for m in sys.modules if m.split('.')[0] "
             "in ('sources', 'asr')])" % str(_SCRIPTS)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "[]", out.stdout)


class TestTimeoutKillsProcessGroup(unittest.TestCase):
    """TF-X-7: a media-download timeout must reap yt-dlp's ffmpeg GRANDchild.

    `subprocess.run(timeout=…)` SIGKILLs only the PID it launched, so the
    ffmpeg yt-dlp spawned (HLS external downloader / `-x` postprocessor)
    survived the kill and kept writing into a workdir `fetch_x_transcript`'s
    `finally` block was already `rmtree`-ing. `download_audio` now goes through
    `run_in_process_group`, which puts yt-dlp in its own session and signals
    the whole group.
    """

    _URL = "https://x.com/i/broadcasts/z"

    # -- launch shape ------------------------------------------------------
    @unittest.skipUnless(os.name == "posix", "start_new_session is POSIX-only")
    def test_child_is_launched_in_its_own_session(self) -> None:
        captured: dict = {}
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            with mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(
                     _procgroup.subprocess, "Popen",
                     _fake_popen(captured,
                                 on_start=lambda a: (workdir / "media.m4a").write_bytes(b"x")),
                 ):
                media, err = ytm.download_audio(self._URL, workdir)
        # Without start_new_session the child shares OUR group and the kill
        # below would either miss the grandchild or hit the CLI itself.
        self.assertTrue(captured["kwargs"].get("start_new_session"))
        self.assertIsNotNone(media)
        self.assertIsNone(err)

    # -- timeout teardown --------------------------------------------------
    def _timeout_run(self, *, getpgid, killpg, captured=None):
        """Drive `download_audio` into the TimeoutExpired branch.

        Pass `captured` when the killpg stub needs to reach the live fake
        process (e.g. to mark it dead once the SIGKILL lands) — it is filled in
        at Popen-construction time, i.e. before any signal is sent.
        """
        captured = {} if captured is None else captured
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(_procgroup.subprocess, "Popen",
                                   _fake_popen(captured, hangs=True)), \
                 mock.patch.object(_procgroup.os, "getpgid", side_effect=getpgid), \
                 mock.patch.object(_procgroup.os, "getpgrp", return_value=1), \
                 mock.patch.object(_procgroup.os, "killpg", side_effect=killpg):
                media, err = ytm.download_audio(self._URL, Path(d), timeout_sec=7)
        return media, err, captured["proc"]

    def test_sigterm_then_sigkill_to_the_group(self) -> None:
        sent: list = []

        box: dict = {}

        def killpg(pgid, sig):
            sent.append((pgid, sig))
            if sig == signal.SIGKILL:
                box["proc"].returncode = -9   # the group is gone for real now

        media, err, proc = self._timeout_run(
            getpgid=lambda pid: 4242, killpg=killpg, captured=box,
        )
        self.assertEqual(sent, [(4242, signal.SIGTERM), (4242, signal.SIGKILL)])
        # The SIGKILL is unconditional: the direct child exiting says nothing
        # about the ffmpeg grandchild, which is the process being reaped here.
        self.assertEqual(proc.direct_kills, 0)
        self.assertIsNone(media)
        # Sentinel string preserved verbatim -> "transient" classification and
        # its retry remediation are untouched by this fix.
        self.assertEqual(err, "timeout downloading audio (>7s)")
        self.assertEqual(ytm.classify_failure(err), "transient")

    def test_never_signals_our_own_process_group(self) -> None:
        # If start_new_session silently did not take effect, the child shares
        # OUR group — killpg would take the whole CLI down. Fall back to the
        # direct PID instead.
        sent: list = []
        media, err, proc = self._timeout_run(
            getpgid=lambda pid: 1,                       # == our (patched) pgrp
            killpg=lambda pgid, sig: sent.append((pgid, sig)),
        )
        self.assertEqual(sent, [])
        self.assertEqual(proc.direct_kills, 1)
        self.assertEqual(err, "timeout downloading audio (>7s)")

    def test_group_already_gone_is_not_an_error(self) -> None:
        def killpg(pgid, sig):
            raise ProcessLookupError(3, "No such process")

        media, err, proc = self._timeout_run(getpgid=lambda pid: 4242, killpg=killpg)
        self.assertEqual(proc.direct_kills, 1)   # best-effort fallback
        self.assertEqual(err, "timeout downloading audio (>7s)")

    def test_child_gone_before_the_kill_is_not_an_error(self) -> None:
        def getpgid(pid):
            raise ProcessLookupError(3, "No such process")

        sent: list = []
        media, err, proc = self._timeout_run(
            getpgid=getpgid,
            killpg=lambda pgid, sig: sent.append((pgid, sig)),
        )
        self.assertEqual(sent, [])
        self.assertEqual(proc.direct_kills, 1)
        self.assertEqual(err, "timeout downloading audio (>7s)")

    def test_keyboard_interrupt_also_tears_down_the_group(self) -> None:
        # start_new_session detaches the child from the terminal's foreground
        # group, so Ctrl-C no longer reaches yt-dlp. Without the BaseException
        # arm this fix would have traded a timeout orphan for a Ctrl-C orphan.
        sent: list = []

        class _InterruptingProc:
            def __init__(self, args, **kwargs):
                self.args, self.pid, self.returncode = list(args), 424242, None
                self.stdout = self.stderr = self.stdin = None

            def communicate(self, timeout=None):
                raise KeyboardInterrupt

            def wait(self, timeout=None):
                self.returncode = -9
                return self.returncode

            def kill(self):
                self.returncode = -9

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with mock.patch.object(_procgroup.subprocess, "Popen", _InterruptingProc), \
             mock.patch.object(_procgroup.os, "getpgid", return_value=4242), \
             mock.patch.object(_procgroup.os, "getpgrp", return_value=1), \
             mock.patch.object(_procgroup.os, "killpg",
                               side_effect=lambda p, s: sent.append((p, s))):
            with self.assertRaises(KeyboardInterrupt):
                ytm.run_in_process_group(["yt-dlp"], timeout=7, grace_sec=0.01)
        self.assertEqual(sent, [(4242, signal.SIGTERM), (4242, signal.SIGKILL)])

    # -- the teardown must not be abortable or exception-clobbering --------
    def test_second_ctrl_c_during_the_grace_does_not_skip_the_sigkill(self) -> None:
        """A signal landing in the grace wait must not abort the escalation.

        `start_new_session=True` means the FIRST Ctrl-C never reaches yt-dlp,
        so a stuck-looking download is exactly when a user mashes the key. If
        the interrupt aborted `_kill_process_group` between the SIGTERM and the
        SIGKILL, anything ignoring SIGTERM would survive — the very orphan this
        whole helper exists to reap.
        """
        sent: list = []

        class _InterruptDuringWait:
            stdout = stderr = stdin = None

            def __init__(self, args, **kwargs):
                self.args, self.pid, self.returncode = list(args), 424242, None
                self.direct_kills = 0

            def communicate(self, timeout=None):
                raise subprocess.TimeoutExpired(self.args, timeout)

            def wait(self, timeout=None):
                raise KeyboardInterrupt          # the user's second Ctrl-C

            def kill(self):
                self.direct_kills += 1

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with mock.patch.object(_procgroup.subprocess, "Popen", _InterruptDuringWait), \
             mock.patch.object(_procgroup.os, "getpgid", return_value=4242), \
             mock.patch.object(_procgroup.os, "getpgrp", return_value=1), \
             mock.patch.object(_procgroup.os, "killpg",
                               side_effect=lambda p, s: sent.append((p, s))):
            with self.assertRaises(subprocess.TimeoutExpired):
                ytm.run_in_process_group(["yt-dlp"], timeout=7, grace_sec=5)
        self.assertEqual(sent, [(4242, signal.SIGTERM), (4242, signal.SIGKILL)])

    def test_teardown_failure_never_replaces_the_original_exception(self) -> None:
        """`_kill_process_group` runs inside an `except` — it must not raise.

        Anything escaping it replaces the `TimeoutExpired` that `download_audio`
        catches (returning the retryable "transient" sentinel) with an
        unhandled crash on a merely slow download. Simulated with an `os` that
        has `killpg`/`getpgid` but no `getpgrp`, i.e. an AttributeError from
        inside the own-group guard.
        """
        crippled_os = types.SimpleNamespace(
            name="posix", killpg=lambda p, s: None, getpgid=lambda p: 4242,
        )   # deliberately NO getpgrp

        captured: dict = {}
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(_procgroup.subprocess, "Popen",
                                   _fake_popen(captured, hangs=True)), \
                 mock.patch.object(_procgroup, "os", crippled_os):
                media, err = ytm.download_audio(self._URL, Path(d), timeout_sec=7)

        # Degraded to the direct-PID kill rather than crashing the CLI.
        self.assertEqual(captured["proc"].direct_kills, 1)
        self.assertIsNone(media)
        self.assertEqual(err, "timeout downloading audio (>7s)")
        self.assertEqual(ytm.classify_failure(err), "transient")

    # -- the real thing ----------------------------------------------------
    @unittest.skipUnless(os.name == "posix", "process groups are POSIX-only")
    def test_real_grandchild_dies_with_the_group(self) -> None:
        """End-to-end reproduction with real processes (no yt-dlp needed).

        `/bin/sh` stands in for yt-dlp and its background loop for the ffmpeg
        child: the loop appends to a marker file, so "still running after the
        timeout" is observable as a file that keeps growing. Under the old
        `subprocess.run(timeout=…)` the loop survived the kill and this
        assertion failed. The loop is self-limiting (~20 s) so a regression
        cannot leave a permanent orphan behind.
        """
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "grandchild-alive"
            # The grandchild writes BEFORE any other fork (no `$(seq …)`
            # subprocess first), so a loaded CI box cannot lose the race
            # between the 0.6 s timeout and the first marker byte.
            script = (
                f"( echo x >> '{marker}'; i=0;"
                f" while [ $i -lt 200 ]; do sleep 0.1; echo x >> '{marker}';"
                " i=$((i+1)); done ) & sleep 30"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                ytm.run_in_process_group(
                    ["/bin/sh", "-c", script], timeout=0.6, grace_sec=0.5
                )
            self.assertTrue(marker.exists(), "the grandchild never started")
            size_at_kill = marker.stat().st_size
            time.sleep(0.8)   # several loop iterations' worth
            self.assertEqual(
                marker.stat().st_size, size_at_kill,
                "ffmpeg stand-in survived the timeout and kept writing (TF-X-7)",
            )


class TestClassifyFailureTransient(unittest.TestCase):
    """`classify_failure()` "transient" bucket (arch-016 §10, task 029.02, R7).

    Scoped to the media-download socket-timeout phrase ONLY — a metadata-probe
    timeout must NOT be classified as transient (the concurrency/media-budget
    remediation cannot fix a slow probe)."""

    def test_audio_download_timeout_is_transient(self) -> None:
        self.assertEqual(
            ytm.classify_failure("timeout downloading audio (>1800s)"),
            "transient",
        )

    def test_probe_timeout_is_not_transient(self) -> None:
        self.assertNotEqual(
            ytm.classify_failure("timeout probing metadata (>180s)"),
            "transient",
        )

    def test_auth_rate_hard_still_intact(self) -> None:
        # Regression: adding the transient bucket must not disturb the
        # pre-existing auth/rate/hard classification.
        self.assertEqual(
            ytm.classify_failure("ERROR: This account is protected"), "auth"
        )
        self.assertEqual(
            ytm.classify_failure("ERROR: HTTP Error 429: Too Many Requests"), "rate"
        )
        self.assertEqual(
            ytm.classify_failure("ERROR: This broadcast is unavailable"), "hard"
        )

    def test_mid_string_embedded_phrase_from_server_text_not_transient(self) -> None:
        # INFO-2 lock: the sentinel is matched via startswith, not substring.
        # A server-influenced free-text stderr that happens to CONTAIN the
        # phrase mid-string (not as the whole authored message) must NOT be
        # classified transient.
        self.assertNotEqual(
            ytm.classify_failure(
                "ERROR: server said timeout downloading audio was reported "
                "upstream, please retry"
            ),
            "transient",
        )

    def test_authored_message_still_transient(self) -> None:
        # The internally-authored TimeoutExpired message (download_audio
        # replaces stderr wholesale on timeout) — startswith is an exact
        # match for it.
        self.assertEqual(
            ytm.classify_failure("timeout downloading audio (>1800s)"),
            "transient",
        )

    def test_authored_style_string_with_auth_phrase_auth_wins(self) -> None:
        # An authored-shaped string that ALSO carries an auth phrase must
        # classify as auth, not transient — auth/rate/hard are checked first.
        self.assertEqual(
            ytm.classify_failure(
                "timeout downloading audio: this account is protected"
            ),
            "auth",
        )


class TestMediaTimeoutFor(unittest.TestCase):
    """Pure-helper table test for `media_timeout_for()` (arch-016 §10.2, TC-05)."""

    def test_no_duration_falls_back_to_generous_default(self) -> None:
        self.assertEqual(ytm.media_timeout_for(None), 1800)
        self.assertEqual(ytm.media_timeout_for(0), 1800)

    def test_short_duration_floors_at_600(self) -> None:
        self.assertEqual(ytm.media_timeout_for(100), 600)

    def test_long_duration_scales_by_4x(self) -> None:
        self.assertEqual(ytm.media_timeout_for(4200), 16800)

    def test_absurd_duration_capped_at_21600(self) -> None:
        # F3/F7 lock: a pathological/un-clipped duration must not yield a
        # multi-day budget — 36000s*4 = 144000s uncapped, but capped at 21600.
        self.assertEqual(ytm.media_timeout_for(36000), 21600)

    def test_numeric_string_accepted(self) -> None:
        # INFO-1 lock: yt-dlp's -J JSON value may arrive as a numeric string
        # via a direct-library caller; media_timeout_for must coerce it.
        self.assertEqual(ytm.media_timeout_for("4200"), 16800)

    def test_non_finite_and_unparseable_fall_back_to_1800(self) -> None:
        # INFO-1 lock: OverflowError on int(inf*4) / TypeError on a bad str
        # must both fall back to the generous default, never raise.
        self.assertEqual(ytm.media_timeout_for(float("inf")), 1800)
        self.assertEqual(ytm.media_timeout_for(float("nan")), 1800)
        self.assertEqual(ytm.media_timeout_for("abc"), 1800)

    def test_astronomical_finite_duration_capped_without_overflow(self) -> None:
        # cycle-2 INFO lock: a FINITE duration whose x4 product would overflow
        # to float `inf` (e.g. 1e308) must still return the 21600 cap, not
        # raise OverflowError out of `int(d * 4)`.
        self.assertEqual(ytm.media_timeout_for(1e308), 21600)
        self.assertEqual(ytm.media_timeout_for(4.5e307), 21600)
        self.assertEqual(ytm.media_timeout_for(1.7e308), 21600)
        # Boundary: exactly at the 5400s early-return threshold (5400*4 ==
        # 21600, so this is a no-op boundary check, not a behaviour change).
        self.assertEqual(ytm.media_timeout_for(5400), 21600)


class TestProbeMetadataBrowserCookies(unittest.TestCase):
    def test_browser_cookies_in_probe_argv(self) -> None:
        captured: dict = {}

        def fake_run(args, **kw):
            captured["argv"] = list(args)
            return _proc(0, stdout='{"id":"z","subtitles":{},"automatic_captions":{}}')

        with mock.patch.object(ytm, "run_in_process_group", side_effect=fake_run):
            info, err = ytm.probe_metadata(
                "https://x.com/i/broadcasts/z", cookies_from_browser="safari",
            )
        self.assertIn("--cookies-from-browser", captured["argv"])
        self.assertIn("safari", captured["argv"])
        self.assertIsNotNone(info)


class TestProbeMediaDuration(unittest.TestCase):
    def test_parses_float_seconds(self) -> None:
        with mock.patch.object(ytm.subprocess, "run",
                               return_value=_proc(0, stdout="1834.56\n")):
            self.assertEqual(ytm.probe_media_duration(Path("/x/m.m4a")), 1834)

    def test_nonzero_exit_returns_none(self) -> None:
        with mock.patch.object(ytm.subprocess, "run",
                               return_value=_proc(1, stdout="")):
            self.assertIsNone(ytm.probe_media_duration(Path("/x/m.m4a")))

    def test_missing_ffprobe_returns_none(self) -> None:
        with mock.patch.object(ytm.subprocess, "run",
                               side_effect=FileNotFoundError("ffprobe")):
            self.assertIsNone(ytm.probe_media_duration(Path("/x/m.m4a")))

    def test_garbage_output_returns_none(self) -> None:
        with mock.patch.object(ytm.subprocess, "run",
                               return_value=_proc(0, stdout="N/A\n")):
            self.assertIsNone(ytm.probe_media_duration(Path("/x/m.m4a")))


class TestDownloadCaptions(unittest.TestCase):
    def test_argv_format_list_and_detection(self) -> None:
        captured: dict = {}
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)

            def fake_run(args, **kw):
                captured["argv"] = list(args)
                (workdir / "vid.en.srt").write_text("1\n", encoding="utf-8")
                return _proc(0)

            with mock.patch.object(ytm, "run_in_process_group",
                                   side_effect=fake_run):
                ok, path, fmt, note = ytm.download_captions(
                    url="https://x.com/jack/status/20", lang="en", kind="auto",
                    workdir=workdir, pre_existing=set(),
                    cookies_file=Path("/c/cookies.txt"),
                    cookies_from_browser="chrome",
                )
            argv = captured["argv"]
            self.assertIn("--sub-format", argv)
            self.assertIn("vtt/srt/ttml/best", argv)   # preference list, not vtt-only
            self.assertIn("--write-auto-subs", argv)
            self.assertIn("--cookies", argv)
            self.assertIn("--cookies-from-browser", argv)
            self.assertIn("chrome", argv)
            self.assertTrue(ok)
            self.assertEqual(fmt, "srt")
            self.assertEqual(path.name, "vid.en.srt")

    def test_auth_failure_classified(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            with mock.patch.object(
                ytm, "run_in_process_group",
                return_value=_proc(1, stderr="ERROR: This account is protected"),
            ):
                ok, path, fmt, note = ytm.download_captions(
                    url="https://x.com/i/broadcasts/z", lang="en", kind="auto",
                    workdir=workdir, pre_existing=set(),
                )
            self.assertFalse(ok)
            self.assertIsNone(path)
            self.assertIn("auth", note)

    def test_no_file_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            with mock.patch.object(ytm, "run_in_process_group", return_value=_proc(0)):
                ok, path, fmt, note = ytm.download_captions(
                    url="https://x.com/jack/status/20", lang="en", kind="manual",
                    workdir=workdir, pre_existing=set(),
                )
            self.assertFalse(ok)
            self.assertIn("no subtitle", note)


class TestCaptionFinder(unittest.TestCase):
    def test_prefers_vtt_over_srt(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            (workdir / "v.en.srt").write_text("x", encoding="utf-8")
            (workdir / "v.en.vtt").write_text("x", encoding="utf-8")
            found = ytm._find_new_caption(workdir, "en", set())
            self.assertEqual(found.suffix, ".vtt")

    def test_excludes_pre_existing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            old = workdir / "v.en.vtt"
            old.write_text("x", encoding="utf-8")
            pre = {old.resolve()}
            self.assertIsNone(ytm._find_new_caption(workdir, "en", pre))

    def test_existing_caption_files_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            (workdir / "v.en.vtt").write_text("x", encoding="utf-8")
            (workdir / "v.en.srt").write_text("x", encoding="utf-8")
            (workdir / "v.info.json").write_text("{}", encoding="utf-8")  # not a caption
            snap = ytm.existing_caption_files(workdir)
            names = {p.name for p in snap}
            self.assertEqual(names, {"v.en.vtt", "v.en.srt"})


class TestPickAnyCaption(unittest.TestCase):
    def test_prefers_manual_over_auto(self) -> None:
        info = {"subtitles": {"en": [{}], "de": [{}]},
                "automatic_captions": {"fr": [{}]}}
        self.assertEqual(ytm.pick_any_caption(info), ("manual", "en"))

    def test_falls_to_auto_when_no_manual(self) -> None:
        info = {"subtitles": {}, "automatic_captions": {"ja": [{}]}}
        self.assertEqual(ytm.pick_any_caption(info), ("auto", "ja"))

    def test_none_when_no_captions(self) -> None:
        self.assertIsNone(
            ytm.pick_any_caption({"subtitles": {}, "automatic_captions": {}})
        )


class TestRemoveSilence(unittest.TestCase):
    def test_skips_gracefully_without_ffmpeg(self) -> None:
        with mock.patch.object(ytm, "ffmpeg_available", return_value=False):
            out, note = ytm.remove_silence(Path("/x/m.m4a"), Path("/x"))
        self.assertIsNone(out)
        self.assertIn("ffmpeg not available", note)

    def test_argv_and_success(self) -> None:
        captured: dict = {}
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            media = workdir / "media.m4a"
            media.write_bytes(b"x")

            def fake_run(args, **kw):
                captured["argv"] = list(args)
                (workdir / "media.desilenced.m4a").write_bytes(b"yy")
                return _proc(0)

            with mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(ytm, "probe_media_duration",
                                   side_effect=[100, 40]):
                out, note = ytm.remove_silence(media, workdir)
            argv = captured["argv"]
            self.assertIn("-af", argv)
            af = next(a for a in argv if "silenceremove=" in a)
            # Threshold MUST keep the dB suffix — silenceremove parses "dB"
            # natively; a bare negative number makes ffmpeg error "Result too
            # large" (empirically verified). Regression lock against a "convert
            # to linear" change that would break the filter.
            self.assertIn("threshold=-45dB", af)
            # Durations carry an explicit `s` unit.
            self.assertIn("stop_duration=1.0s", af)
            self.assertIn("stop_silence=0.3s", af)
            self.assertIsNotNone(out)
            self.assertEqual(out.name, "media.desilenced.m4a")
            self.assertIn("stripped ~60s", note)

    def test_no_silence_removed_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            media = workdir / "media.m4a"
            media.write_bytes(b"x")

            def fake_run(args, **kw):
                (workdir / "media.desilenced.m4a").write_bytes(b"yy")
                return _proc(0)

            with mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(ytm, "probe_media_duration",
                                   side_effect=[40, 40]):
                out, note = ytm.remove_silence(media, workdir)
            self.assertIsNone(out)
            self.assertIn("no long silence", note)
            # the useless re-encode was cleaned up
            self.assertFalse((workdir / "media.desilenced.m4a").exists())

    def test_ffmpeg_nonzero_exit_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            media = workdir / "media.m4a"
            media.write_bytes(b"x")
            with mock.patch.object(ytm, "ffmpeg_available", return_value=True), \
                 mock.patch.object(ytm.subprocess, "run",
                                   return_value=_proc(1, stderr="boom")):
                out, note = ytm.remove_silence(media, workdir)
            self.assertIsNone(out)
            self.assertIn("no usable output", note)

    @unittest.skipUnless(_HAVE_FFMPEG, "ffmpeg/ffprobe required for the live filter test")
    def test_real_ffmpeg_strips_silence(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            src = workdir / "media.m4a"
            # 4s digital silence + 2s 440Hz tone + 4s silence = 10s.
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-y",
                    "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=4",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2:sample_rate=16000",
                    "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=4",
                    "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1",
                    str(src),
                ],
                check=True, capture_output=True,
            )
            before = ytm.probe_media_duration(src)
            out, note = ytm.remove_silence(src, workdir)
            self.assertIsNotNone(out, note)
            after = ytm.probe_media_duration(out)
            self.assertLess(after, before)   # dead air collapsed
            self.assertLessEqual(after, 5)    # ~2s tone + a little kept silence


if __name__ == "__main__":
    unittest.main()

"""The stdout byte contract: locale-independent UTF-8, and a dead reader that
does not rewrite the exit status.

Covers ``_stdout.write_json_stdout`` plus every machine-readable stdout site in
the skill: ``fetch.py doctor --json``, the single-URL stat record, the batch
JSONL stream (success **and** error records), and ``install_components.py
--json``.

Why so many of these are subprocess tests: the codec is chosen when the
interpreter builds ``sys.stdout``, and a broken pipe needs a real pipe. Neither
is reachable from a test that patches ``sys.stdout`` with a ``StringIO`` — which
is exactly why the pre-existing in-process batch tests in ``test_fetch_cli.py``
stayed green while ``LC_ALL=C`` was turning three fetched transcripts into
``3/3 URLs failed``. The heavy work is stubbed in ``tests/_stdout_child.py``;
nothing here touches the network.

Issue: ``docs/issues/pdf-cli-stdout-json-locale-class.md``.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import _stdout  # noqa: E402

_CHILD = _HERE / "_stdout_child.py"
_FETCH = _SCRIPTS / "fetch.py"
_INSTALL = _SCRIPTS / "install_components.py"

# The em dash is the exact character that broke every measured site.
EM_DASH = "—"
EM_DASH_UTF8 = b"\xe2\x80\x94"

# A pipe on this machine holds well over 64 KiB, so a small payload can slip
# entirely into the kernel buffer before the reader is gone and the defect
# never fires. 360 KB is past every threshold measured (the first failures
# appeared at ~105 KB).
BIG_RECORD_BYTES = 360_000


def _base_env(**extra: str) -> dict:
    """A hermetic environment: no developer ``.env``, no tools on ``PATH``.

    Both matter for the doctor payload — its non-ASCII text is the remediation
    block, which only appears when something is *missing*. Without this the
    test would pass on a fully-equipped laptop for the wrong reason (an
    all-ASCII payload).
    """
    env = {
        "PATH": "/nonexistent",
        "TRANSCRIPT_FETCHER_NO_DOTENV": "1",
        "PYTHONUTF8": "0",
    }
    env.update(extra)
    return env


def _run(argv: list[str], env: dict, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, cwd=str(_SCRIPTS), env=env, timeout=timeout,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _run_with_dead_reader(
    argv: list[str], env: dict, timeout: int = 120
) -> tuple[int, bytes]:
    """Run `argv` with an fd 1 that has **no reader at all**, return (rc, stderr).

    Closing both ends of the pipe in the parent is deliberate: with ``| head``
    the outcome depends on whether the payload happened to fit in the kernel
    buffer before the reader exited, and a test that only sometimes reaches the
    defect is not a test. With zero readers the first write is guaranteed
    ``EPIPE``.
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


def _stderr_lines(err: bytes) -> list[str]:
    """Stderr lines minus the child harness's own ``CALLS=`` bookkeeping."""
    text = err.decode("utf-8", "replace")
    return [ln for ln in text.splitlines() if ln and not ln.startswith("CALLS=")]


def _calls(err: bytes) -> int:
    """How many URLs the child actually fetched (0 if it never got that far)."""
    for line in err.decode("utf-8", "replace").splitlines():
        if line.startswith("CALLS="):
            return int(line.split("=", 1)[1])
    return 0


# --------------------------------------------------------------------- #
# _stdout, in-process
# --------------------------------------------------------------------- #
class TestErrorEnvelopeEncoding(unittest.TestCase):
    """`--json-errors` promises ONE parseable JSON line on stderr. stderr is
    opened errors="backslashreplace", so a non-ASCII envelope never crashed —
    it quietly stopped being JSON."""

    def _envelope(self, url: str, encoding: str) -> subprocess.CompletedProcess:
        env = _base_env(PYTHONIOENCODING=encoding, LC_ALL="C", LANG="C")
        return _run([sys.executable, str(_FETCH), url, "--json-errors"], env)

    def test_the_envelope_parses_under_a_legacy_locale(self):
        """Was: a Latin-1 message came out as `caf\\xe9` and an emoji as
        `\\U0001f600` — neither is a legal JSON escape — and Cyrillic under
        cp1252 raised outright. The URL is echoed into the message, so an
        unsupported one is the cheapest carrier."""
        for label, url in (("latin1", "https://example.com/caf\u00e9-na\u00efve"),
                           ("bmp", "https://example.com/\u041f\u0440\u0438\u0432\u0435\u0442"),
                           ("astral", "https://example.com/\U0001F600")):
            for encoding in ("ascii", "cp1252"):
                with self.subTest(text=label, encoding=encoding):
                    proc = self._envelope(url, encoding)
                    line = proc.stderr.decode("utf-8").strip().splitlines()[-1]
                    envelope = json.loads(line)          # the assertion
                    self.assertIn("error", envelope)
                    self.assertEqual(envelope["v"], 1)

    def test_the_envelope_is_ascii_only_on_the_wire(self):
        """Pure ASCII is the only form every codec a caller can name can
        encode; the escapes parse back to the same string."""
        proc = self._envelope("https://example.com/\u041f\u0440\u0438\u0432\u0435\u0442", "ascii")
        self.assertTrue(proc.stderr.decode("utf-8").isascii())


class TestClosedStdout(unittest.TestCase):
    """`prog >&-` leaves `sys.stdout` as None, where `print()` is a silent
    no-op and an unguarded `.write` is an AttributeError raised inside an
    `except` block — which in batch mode aborts the run and loses the URLs
    still queued."""

    def test_a_closed_stdout_raises_broken_pipe_not_attribute_error(self):
        code = ("import sys\n"
                "sys.path.insert(0, %r)\n"
                "from _stdout import write_json_stdout\n"
                "try:\n"
                "    write_json_stdout({'a': 1})\n"
                "except BrokenPipeError:\n"
                "    sys.exit(7)\n"
                "except Exception as exc:\n"
                "    sys.stderr.write(type(exc).__name__)\n"
                "    sys.exit(8)\n"
                "sys.exit(0)\n" % str(_SCRIPTS))
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
            fh.write(code)
            driver = fh.name
        self.addCleanup(os.unlink, driver)
        proc = subprocess.run(["sh", "-c", 'exec "$0" "$1" >&-', sys.executable,
                               driver], capture_output=True)
        self.assertEqual(proc.returncode, 7,
                         proc.stderr.decode("utf-8", "replace"))


class TestWriteJsonStdout(unittest.TestCase):
    def test_the_bytes_are_utf8_even_when_the_text_layer_is_ascii(self) -> None:
        # The whole point: the wrapper's codec must not reach the payload.
        # Kills a revert to `print(json.dumps(...))` / `stream.write(text)`.
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="ascii", errors="strict")
        _stdout.write_json_stdout({"hint": f"ffmpeg {EM_DASH} install it"}, stream=stream)
        self.assertIn(EM_DASH_UTF8, raw.getvalue())
        self.assertEqual(
            json.loads(raw.getvalue().decode("utf-8"))["hint"],
            f"ffmpeg {EM_DASH} install it",
        )

    def test_non_ascii_is_written_as_itself_not_escaped(self) -> None:
        # Kills the "simple" fix of ensure_ascii=True, which stops the crash by
        # changing every non-ASCII byte of the output on every locale.
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="utf-8")
        _stdout.write_json_stdout({"title": f"Лекция {EM_DASH} 1"}, stream=stream)
        self.assertIn("Лекция".encode("utf-8"), raw.getvalue())
        self.assertNotIn(b"\\u", raw.getvalue())

    def test_a_lone_surrogate_is_escaped_rather_than_raising(self) -> None:
        # `TranscriptStat.output_path` is str(out_path), and POSIX hands back
        # undecodable filename bytes as surrogates. UTF-8 cannot encode them.
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="utf-8")
        _stdout.write_json_stdout({"output_path": "/tmp/o\udcff.txt"}, stream=stream)
        self.assertIn(b"\\udcff", raw.getvalue())
        self.assertEqual(
            json.loads(raw.getvalue().decode("utf-8"))["output_path"],
            "/tmp/o\udcff.txt",
        )

    def test_a_stream_without_a_buffer_keeps_the_text_path(self) -> None:
        # in-process tests and wrapper proxies pass a StringIO; the value must
        # be identical to the byte path's, surrogate escape included.
        buf = io.StringIO()
        _stdout.write_json_stdout({"output_path": "/tmp/o\udcff.txt"}, stream=buf)
        self.assertEqual(
            json.loads(buf.getvalue())["output_path"], "/tmp/o\udcff.txt"
        )

    def test_each_record_reaches_the_reader_at_once(self) -> None:
        # Batch mode is a live JSONL stream; a record buffered until exit is a
        # behaviour change, not an optimisation. Kills a dropped flush.
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)   # no flush -> BlockingIOError, not a hang
        stream = os.fdopen(write_fd, "w", encoding="utf-8")
        try:
            _stdout.write_json_stdout({"n": 1}, stream=stream)
            self.assertEqual(json.loads(os.read(read_fd, 4096))["n"], 1)
        finally:
            stream.close()
            os.close(read_fd)

    def test_a_dead_pipe_reaches_the_caller_and_abandons_the_fd(self) -> None:
        # The caller owns the exit code and the envelope shape, so the error
        # must propagate; the fd must also be neutralised, or the interpreter's
        # shutdown flush replaces the exit status with 120.
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        stream = os.fdopen(write_fd, "w", encoding="utf-8")
        try:
            with self.assertRaises(BrokenPipeError):
                _stdout.write_json_stdout({"n": 1}, stream=stream)
            # Now pointed at /dev/null: writing again must not raise.
            os.write(stream.fileno(), b"x")
        finally:
            stream.close()   # closes the fd; /dev/null takes the flush


# --------------------------------------------------------------------- #
# fetch.py doctor --json
# --------------------------------------------------------------------- #
class TestDoctorJsonStdout(unittest.TestCase):
    def test_an_ascii_locale_yields_the_report_not_a_traceback(self) -> None:
        # Measured before the fix: 0 bytes on stdout, a 733-byte
        # UnicodeEncodeError traceback on stderr, rc 1.
        env = _base_env(PYTHONIOENCODING="ascii", LC_ALL="C")
        proc = _run([sys.executable, str(_FETCH), "doctor", "--json"], env)
        # 0 = ready, 7 = yt-dlp itself absent (a venv without requirements
        # installed). Either is a *report*; 1 is the crash.
        self.assertIn(proc.returncode, (0, 7), proc.stderr.decode("utf-8", "replace"))
        payload = json.loads(proc.stdout.decode("utf-8"))
        self.assertTrue(
            any(EM_DASH in line for line in payload["remediation"]),
            "hermetic env should have produced a non-ASCII remediation block; "
            "without one this test cannot see the defect",
        )

    def test_a_legacy_locale_does_not_emit_non_utf8_bytes(self) -> None:
        # Measured before the fix: cp1252 gave 1009 bytes against UTF-8's 1013,
        # the em dash written as the single byte 0x97, at exit 0.
        utf8 = _run(
            [sys.executable, str(_FETCH), "doctor", "--json"],
            _base_env(PYTHONIOENCODING="utf-8"),
        )
        legacy = _run(
            [sys.executable, str(_FETCH), "doctor", "--json"],
            _base_env(PYTHONIOENCODING="cp1252"),
        )
        legacy.stdout.decode("utf-8")   # must not raise
        self.assertEqual(utf8.stdout, legacy.stdout)

    def test_a_dead_reader_exits_with_the_code_the_message_declares(self) -> None:
        # Measured before the fix: rc 120 and two non-JSON stderr lines.
        rc, err = _run_with_dead_reader(
            [sys.executable, str(_FETCH), "doctor", "--json"],
            _base_env(PYTHONIOENCODING="utf-8"),
        )
        self.assertEqual(rc, 1)
        self.assertNotIn(b"Exception ignored", err)
        self.assertNotIn(b"Traceback", err)
        self.assertEqual(len(_stderr_lines(err)), 1, err)


# --------------------------------------------------------------------- #
# fetch.py, single URL
# --------------------------------------------------------------------- #
class TestSingleUrlStdout(unittest.TestCase):
    def test_an_ascii_locale_does_not_lose_the_stat_record(self) -> None:
        # Measured before the fix: rc 1, 0 bytes of stat, and the transcript
        # already on disk — the caller learns nothing about a file that exists.
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "o.txt"
            proc = _run(
                [sys.executable, str(_CHILD), "single",
                 "https://youtu.be/aaaaaaaaaaa", str(out)],
                _base_env(PYTHONIOENCODING="ascii", LC_ALL="C", HOME=td),
            )
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
            self.assertTrue(out.exists())
            record = json.loads(proc.stdout.decode("utf-8"))
            self.assertEqual(record["output_path"], str(out))
            self.assertIn(EM_DASH, record["title"])

    def test_a_dead_reader_names_the_output_that_was_written(self) -> None:
        # Measured before the fix: rc 120 and a 13-line traceback. The file is
        # on disk either way, so the message has to say where it went.
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "o.txt"
            rc, err = _run_with_dead_reader(
                [sys.executable, str(_CHILD), "single",
                 "https://youtu.be/aaaaaaaaaaa", str(out)],
                _base_env(PYTHONIOENCODING="utf-8", HOME=td),
            )
            self.assertEqual(rc, 1)
            self.assertNotIn(b"Exception ignored", err)
            lines = _stderr_lines(err)
            self.assertEqual(len(lines), 1, err)
            self.assertIn(str(out), lines[0])


# --------------------------------------------------------------------- #
# fetch.py, batch JSONL stream
# --------------------------------------------------------------------- #
class TestBatchStdout(unittest.TestCase):
    def _batch(self, td: str, n: int = 3) -> Path:
        path = Path(td) / "urls.txt"
        path.write_text(
            "".join(f"https://youtu.be/{chr(97 + i) * 11}\n" for i in range(n)),
            encoding="utf-8",
        )
        return path

    def test_an_ascii_locale_does_not_turn_fetched_transcripts_into_failures(self) -> None:
        # THE defect: UnicodeEncodeError is a ValueError, so the success write
        # was caught by the loop's `except ValueError`, relabelled UsageError
        # and counted. Measured before the fix: 3 transcripts on disk, three
        # `"type": "UsageError"` records on stdout, `3/3 URLs failed`, rc 4.
        with tempfile.TemporaryDirectory() as td:
            batch, out_dir = self._batch(td), Path(td) / "out"
            proc = _run(
                [sys.executable, str(_CHILD), "ok", str(batch), str(out_dir)],
                _base_env(PYTHONIOENCODING="ascii", LC_ALL="C", HOME=td),
            )
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
            records = [
                json.loads(ln)
                for ln in proc.stdout.decode("utf-8").splitlines() if ln
            ]
            self.assertEqual(len(records), 3)
            self.assertEqual([r["source"] for r in records], ["youtube"] * 3)
            self.assertTrue(all(EM_DASH in r["title"] for r in records))
            self.assertEqual(len(list(out_dir.glob("*.txt"))), 3)

    def test_an_unencodable_error_record_does_not_abort_the_run(self) -> None:
        # The five error writes sit inside `except` blocks, where a raise has
        # no clause to catch it. Measured before the fix: 3 URLs in, 0 records
        # out, rc 1, and URLs 2-3 never fetched — minutes of network + ASR work
        # thrown away by a report line.
        with tempfile.TemporaryDirectory() as td:
            batch, out_dir = self._batch(td), Path(td) / "out"
            proc = _run(
                [sys.executable, str(_CHILD), "err", str(batch), str(out_dir)],
                _base_env(PYTHONIOENCODING="ascii", LC_ALL="C", HOME=td),
            )
            self.assertEqual(proc.returncode, 4)      # 3/3 failed, reported
            self.assertEqual(_calls(proc.stderr), 3)  # ...but all 3 attempted
            records = [
                json.loads(ln)
                for ln in proc.stdout.decode("utf-8").splitlines() if ln
            ]
            self.assertEqual(len(records), 3)
            self.assertEqual(
                [r["type"] for r in records], ["MissingDependencyError"] * 3
            )
            self.assertTrue(all(EM_DASH in r["remediation"] for r in records))
            # The batch error record's shape is its own — no `code` field, in
            # contrast to the stderr envelope from `_emit_error`.
            self.assertNotIn("code", records[0])

    def test_a_lone_surrogate_in_the_output_path_does_not_fail_the_record(self) -> None:
        # Measured before the fix under a plain UTF-8 locale: rc 4,
        # `3/3 URLs failed`, three UsageError records — no locale needed.
        with tempfile.TemporaryDirectory() as td:
            batch, out_dir = self._batch(td), Path(td) / "out"
            proc = _run(
                [sys.executable, str(_CHILD), "surrogate", str(batch), str(out_dir)],
                _base_env(PYTHONIOENCODING="utf-8", HOME=td),
            )
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
            records = [
                json.loads(ln)
                for ln in proc.stdout.decode("utf-8").splitlines() if ln
            ]
            self.assertEqual(len(records), 3)
            self.assertTrue(all(r["output_path"].endswith("\udcff") for r in records))

    def test_a_dead_reader_stops_the_run_with_the_code_it_declares(self) -> None:
        # Measured before the fix, with 360 KB records: rc 120 and a 13-line
        # raw traceback. The remaining URLs must not be fetched either — nobody
        # can receive them, and each one costs a download plus maybe an ASR run.
        with tempfile.TemporaryDirectory() as td:
            batch, out_dir = self._batch(td), Path(td) / "out"
            rc, err = _run_with_dead_reader(
                [sys.executable, str(_CHILD), "big", str(batch), str(out_dir)],
                _base_env(
                    PYTHONIOENCODING="utf-8", HOME=td,
                    TF_PAD_BYTES=str(BIG_RECORD_BYTES),
                ),
            )
            self.assertEqual(rc, 1)
            self.assertNotIn(b"Exception ignored", err)
            self.assertNotIn(b"Traceback", err)
            self.assertEqual(len(_stderr_lines(err)), 1, err)
            self.assertEqual(_calls(err), 1)


# --------------------------------------------------------------------- #
# install_components.py --json
# --------------------------------------------------------------------- #
class TestInstallComponentsStdout(unittest.TestCase):
    def test_the_payload_is_ascii_by_construction(self) -> None:
        # Characterisation, not a regression kill: this site is MEASURED IMMUNE
        # on the locale axis (330 identical bytes under utf-8 / ascii / cp1252,
        # before and after the change), because the payload is component keys
        # and booleans. It is here so the claim stays checkable — if a future
        # field brings a non-ASCII character in, this test stops being true and
        # the byte-level guarantee moves to `write_json_stdout`.
        outputs = {
            enc: _run(
                [sys.executable, str(_INSTALL), "--json"],
                _base_env(PYTHONIOENCODING=enc, LC_ALL="C"),
            ).stdout
            for enc in ("utf-8", "ascii", "cp1252")
        }
        self.assertEqual(outputs["utf-8"], outputs["ascii"])
        self.assertEqual(outputs["utf-8"], outputs["cp1252"])
        self.assertTrue(outputs["utf-8"].isascii())
        json.loads(outputs["utf-8"].decode("utf-8"))

    def test_a_dead_reader_exits_with_a_named_failure_not_120(self) -> None:
        # This IS the half that bit here. Measured before the fix: rc 120 and
        # 85 bytes of `Exception ignored while flushing sys.stdout`.
        rc, err = _run_with_dead_reader(
            [sys.executable, str(_INSTALL), "--json"],
            _base_env(PYTHONIOENCODING="utf-8"),
        )
        self.assertEqual(rc, 1)
        self.assertNotIn(b"Exception ignored", err)
        self.assertEqual(len(_stderr_lines(err)), 1, err)
        self.assertIn(b"broken pipe", err)


if __name__ == "__main__":
    unittest.main()

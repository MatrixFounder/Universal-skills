"""Tests for the stdout side of `_errors.py` — `write_json_stdout`,
`abandon_stdout`, and the ASCII-only error envelope.

`_errors.py` is replicated byte-identically into xlsx, pptx, pdf and html
(CLAUDE.md §2, docx is the master), so this file lives only in docx —
the same placement `test_venv_bootstrap.py` uses for the other replicated
scripts/-level module.

The point of most of these tests is what lands on fd 1 as BYTES under a
locale that is not UTF-8, so they run the real interpreter in a subprocess
with PYTHONIOENCODING set; an in-process test cannot observe that layer.

Run:
    cd skills/docx/scripts
    ./.venv/bin/python -m unittest tests.test_errors_stdout -v
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import _errors  # noqa: E402

# One string per hazard class the envelope and the payload have to survive.
BMP = "em dash — cyrillic Приве́т"          # U+0100..U+FFFF
LATIN1 = "café naïve"                        # U+0080..U+00FF
ASTRAL = "emoji \U0001F600 done"             # U+10000+
PAYLOAD = {"bmp": BMP, "latin1": LATIN1, "astral": ASTRAL}

LEGACY_LOCALES = ("ascii", "cp1252")


def _run(code: str, *, encoding: str | None = None, stdin_closed: bool = False):
    """Run `code` in a subprocess with `_errors` importable, optionally under
    a legacy stdio codec. Returns CompletedProcess with BYTES streams."""
    env = dict(os.environ, PYTHONPATH=str(SCRIPTS_DIR))
    if encoding is not None:
        env.update(PYTHONIOENCODING=encoding, PYTHONUTF8="0",
                   LC_ALL="C", LANG="C")
    else:
        env.update(PYTHONUTF8="1")
    return subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True)


WRITE_PAYLOAD = f"""
import sys
from _errors import write_json_stdout
write_json_stdout({PAYLOAD!r}, indent=2)
"""


class TestWriteJsonStdout(unittest.TestCase):
    """Regression lock for PDF-CLI-STDOUT-JSON-LOCALE-CLASS: the payload on
    stdout is UTF-8 whatever codec the caller's locale names."""

    def test_a_legacy_locale_cannot_change_a_single_byte(self):
        """Was (per site, measured): `print(json.dumps(x, ensure_ascii=False))`
        aborted mid-write under `ascii` leaving truncated JSON on stdout, and
        under `cp1252` emitted an em dash as the single byte 0x97 at exit 0."""
        native = _run(WRITE_PAYLOAD)
        self.assertEqual(native.returncode, 0, native.stderr[-400:])
        self.assertEqual(json.loads(native.stdout.decode("utf-8")), PAYLOAD)
        for encoding in LEGACY_LOCALES:
            with self.subTest(encoding=encoding):
                proc = _run(WRITE_PAYLOAD, encoding=encoding)
                self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
                # Byte equality, not just "parses": a fix that quietly
                # switched to ensure_ascii=True would still parse.
                self.assertEqual(proc.stdout, native.stdout)

    def test_the_dump_keeps_its_characters_rather_than_escaping_them(self):
        """`ensure_ascii=False` is the point — the helper fixes the *encoding*
        of the output, it does not fall back to ASCII escapes."""
        proc = _run(WRITE_PAYLOAD, encoding="ascii")
        self.assertIn("—".encode("utf-8"), proc.stdout)
        self.assertIn("Приве́т".encode("utf-8"), proc.stdout)

    def test_a_lone_surrogate_becomes_a_json_escape(self):
        """UTF-8 cannot carry U+D800-DFFF. POSIX puts them in paths
        (surrogateescape) and a broken PDF /ToUnicode CMap in text, so the
        helper must not abort — JSON carries them as `\\udXXX`."""
        code = ("import sys\n"
                "from _errors import write_json_stdout\n"
                "write_json_stdout({'t': 'a\\ud800b'})\n")
        proc = _run(code)
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        self.assertEqual(json.loads(proc.stdout.decode("utf-8"))["t"],
                         "a\ud800b")

    def test_a_stream_without_a_buffer_keeps_the_text_path(self):
        """`redirect_stdout(StringIO())` in tests, proxy objects in wrappers."""
        sink = io.StringIO()
        _errors.write_json_stdout(PAYLOAD, indent=2, stream=sink)
        self.assertEqual(json.loads(sink.getvalue()), PAYLOAD)

    def test_both_paths_carry_the_identical_value(self):
        """The surrogate escape is applied before the byte/text branch, so the
        two sinks cannot disagree."""
        text_sink = io.StringIO()
        _errors.write_json_stdout({"t": "a\ud800b — ok"}, stream=text_sink)

        class _ByteStream:
            """A real object: `getattr(mock, "buffer", None)` on a Mock
            auto-creates a child and would silently take the wrong branch."""

            def __init__(self):
                self.buffer = io.BytesIO()

            def flush(self):
                pass

        byte_sink = _ByteStream()
        _errors.write_json_stdout({"t": "a\ud800b — ok"}, stream=byte_sink)
        self.assertEqual(byte_sink.buffer.getvalue().decode("utf-8"),
                         text_sink.getvalue())

    def test_earlier_text_output_stays_ahead_of_the_payload(self):
        """The text layer buffers; bytes pushed straight at the fd would
        overtake anything a caller already printed, splicing the JSON into the
        middle of an earlier line."""
        code = ("import sys\n"
                "from _errors import write_json_stdout\n"
                "print('status line', end='\\n')\n"
                "write_json_stdout({'a': 1})\n")
        proc = _run(code)
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        self.assertEqual(proc.stdout, b'status line\n{"a": 1}\n')

    def test_the_serialisation_arguments_reach_json_dumps(self):
        """indent / separators / default / newline are the four knobs the call
        sites need; `default` is what pdf_fill_form passes to render Paths."""
        sink = io.StringIO()
        _errors.write_json_stdout({"p": Path("/tmp/x")}, default=str,
                                  stream=sink)
        self.assertEqual(json.loads(sink.getvalue()), {"p": "/tmp/x"})

        sink = io.StringIO()
        _errors.write_json_stdout({"a": 1, "b": 2}, separators=(",", ":"),
                                  newline=False, stream=sink)
        self.assertEqual(sink.getvalue(), '{"a":1,"b":2}')

        sink = io.StringIO()
        _errors.write_json_stdout({"a": 1}, indent=2, stream=sink)
        self.assertEqual(sink.getvalue(), '{\n  "a": 1\n}\n')

    def test_nothing_is_written_when_the_payload_cannot_be_serialised(self):
        """One-shot, not streamed: a payload that fails halfway must not leave
        a truncated document on the wire."""
        sink = io.StringIO()
        with self.assertRaises(TypeError):
            _errors.write_json_stdout({"ok": 1, "bad": object()}, stream=sink)
        self.assertEqual(sink.getvalue(), "")


# Exit codes are the assertion channel: 7 = the fd was redirected (which is
# what stops the interpreter's shutdown flush from substituting 120), 8 = the
# BrokenPipeError arrived but fd 1 is still the dead pipe, 9 = no error at all.
BIG_WRITE = """
import os, sys
from _errors import write_json_stdout
try:
    write_json_stdout({"pad": ["x" * 64] * 4000}, indent=2)
except BrokenPipeError:
    try:
        os.write(1, b"x")      # /dev/null after abandon_stdout; EPIPE without it
    except OSError:
        sys.exit(8)
    sys.exit(7)
sys.exit(9)
"""


class TestUtf8StdoutStream(unittest.TestCase):
    """The streaming sink for producers that cannot materialise the document
    (xlsx2csv2json serialises a 3M-cell workbook row by row)."""

    def test_a_streamed_document_is_utf8_under_a_legacy_locale(self):
        code = ("import sys\n"
                "from _errors import utf8_stdout\n"
                "with utf8_stdout() as fp:\n"
                "    fp.write('[\\n  ')\n"
                "    fp.write('\"em dash \u2014 cyrillic \u041f\u0440\u0438\u0432\u0435\u0442\"')\n"
                "    fp.write('\\n]\\n')\n")
        native = _run(code)
        self.assertEqual(native.returncode, 0, native.stderr[-400:])
        for encoding in LEGACY_LOCALES:
            with self.subTest(encoding=encoding):
                proc = _run(code, encoding=encoding)
                self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
                self.assertEqual(proc.stdout, native.stdout)
                json.loads(proc.stdout.decode("utf-8"))

    def test_the_stream_writes_lf_and_leaves_stdout_usable(self):
        """`newline="\n"` (not os.linesep), and detach-not-close: a caller that
        prints after the stream closes must not hit a closed file."""
        code = ("import sys\n"
                "from _errors import utf8_stdout\n"
                "with utf8_stdout() as fp:\n"
                "    fp.write('{\"a\": 1}\\n')\n"
                "sys.stdout.write('after\\n')\n"
                "sys.stdout.flush()\n")
        proc = _run(code)
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        self.assertEqual(proc.stdout, b'{"a": 1}\nafter\n')

    def test_a_text_stream_without_a_buffer_is_yielded_unchanged(self):
        sink = io.StringIO()
        with mock.patch.object(_errors.sys, "stdout", sink):
            with _errors.utf8_stdout() as fp:
                self.assertIs(fp, sink)
                fp.write("x")
        self.assertEqual(sink.getvalue(), "x")


class TestBrokenPipe(unittest.TestCase):
    """Regression lock for the exit-120 substitution: the interpreter's
    shutdown flush must not get a second go at the dead fd."""

    def test_the_exit_code_survives_a_dead_reader(self):
        """Was: the shutdown flush printed `Exception ignored while flushing
        sys.stdout` and replaced the status with 120 — measured as a
        size-dependent band, so callers could not even reason about it."""
        env = dict(os.environ, PYTHONPATH=str(SCRIPTS_DIR), PYTHONUTF8="1")
        proc = subprocess.Popen([sys.executable, "-c", BIG_WRITE], env=env,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        proc.stdout.read(20)
        proc.stdout.close()              # the `| head` moment
        err = proc.stderr.read().decode("utf-8", "replace")
        proc.stderr.close()
        rc = proc.wait(timeout=120)

        # 7 means the fd really was redirected: writing to fd 1 succeeded after
        # the failure. That is the mechanism — asserting only "not 120" passes
        # against a no-op `abandon_stdout` whenever the buffer happens to be
        # empty at shutdown, which is how a mutation of it survived once.
        self.assertEqual(rc, 7, f"rc={rc} (8 = fd still dead, 9 = no EPIPE)")
        self.assertNotIn("Exception ignored", err)
        self.assertEqual(err.strip(), "")

    def test_a_closed_stdout_is_reported_rather_than_crashing(self):
        """`prog >&-` leaves CPython with `sys.stdout is None`, where `print()`
        is a *silent no-op* — the one outcome this module exists to prevent.
        The helper must report the sink as gone, through the same exception
        every call site already maps to its envelope."""
        code = ("import sys\n"
                "from _errors import write_json_stdout\n"
                "try:\n"
                "    write_json_stdout({'a': 1})\n"
                "except BrokenPipeError:\n"
                "    sys.exit(7)\n"
                "except Exception as exc:\n"
                "    sys.stderr.write(type(exc).__name__)\n"
                "    sys.exit(8)\n"
                "sys.exit(0)\n")
        env = dict(os.environ, PYTHONPATH=str(SCRIPTS_DIR), PYTHONUTF8="1")
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
            fh.write(code)
            driver = fh.name
        self.addCleanup(os.unlink, driver)
        proc = subprocess.run(["sh", "-c", f'exec "$0" "$1" >&-', sys.executable,
                               driver], env=env, capture_output=True)
        self.assertEqual(proc.returncode, 7,
                         proc.stderr.decode("utf-8", "replace"))

    def test_abandon_stdout_survives_a_stream_with_no_descriptor(self):
        """Best-effort: an in-process test's StringIO has no fd, and that must
        not turn into a second exception on the failure path."""
        _errors.abandon_stdout(io.StringIO())        # must not raise


ENVELOPE = """
import sys
from _errors import report_error
report_error({msg!r}, code=3, error_type="T",
             details={{"path": {msg!r}}}, json_mode=True)
"""


class TestEnvelopeEncoding(unittest.TestCase):
    """The stderr envelope is the other half of the same contract."""

    def test_the_envelope_parses_under_every_legacy_locale(self):
        """Was: stderr's `errors="backslashreplace"` kept the process alive but
        silently produced NON-JSON — `caf\\xe9` for Latin-1 and `\\U0001f600`
        for astral characters, neither of which is a JSON escape; BMP text
        survived only because Python's `\\uXXXX` happens to match JSON's. And
        under cp1252, text outside that codec raised outright."""
        for encoding in LEGACY_LOCALES:
            for label, msg in (("bmp", BMP), ("latin1", LATIN1),
                               ("astral", ASTRAL)):
                with self.subTest(encoding=encoding, text=label):
                    proc = _run(ENVELOPE.format(msg=msg), encoding=encoding)
                    line = proc.stderr.decode("utf-8").strip()
                    envelope = json.loads(line)      # the assertion
                    self.assertEqual(envelope["error"], msg)
                    self.assertEqual(envelope["details"]["path"], msg)
                    self.assertEqual(envelope["code"], 3)

    def test_the_envelope_is_ascii_only_on_the_wire(self):
        """Pure ASCII is the only output every codec a caller can name is able
        to encode; the escapes parse back to the same string."""
        proc = _run(ENVELOPE.format(msg=BMP), encoding="ascii")
        self.assertTrue(proc.stderr.decode("utf-8").isascii())

    def test_a_utf8_locale_gets_the_same_envelope(self):
        """The fix must not make the envelope depend on the locale in the
        other direction either."""
        legacy = _run(ENVELOPE.format(msg=BMP), encoding="ascii").stderr
        native = _run(ENVELOPE.format(msg=BMP)).stderr
        self.assertEqual(legacy, native)



class TestWriteTextStdout(unittest.TestCase):
    """Non-JSON MACHINE output — a TSV row, a listing a tool greps. Same byte
    contract as the JSON writer, minus the serialisation."""

    def test_bytes_do_not_depend_on_the_stream_codec(self):
        row = "0\tmain\tyes\thttps://ex.com/\u0441\u0442\u0440-caf\u00e9"
        seen = set()
        for enc in ("utf-8", "ascii", "cp1251", "cp1252"):
            with self.subTest(encoding=enc):
                sink = io.TextIOWrapper(io.BytesIO(), encoding=enc, errors="strict")
                _errors.write_text_stdout(row, stream=sink)
                raw = sink.buffer.getvalue()
                seen.add(raw)
                self.assertEqual(raw.decode("utf-8"), row + "\n")
        self.assertEqual(len(seen), 1, "the same row produced different bytes")

    def test_a_strict_ascii_stream_would_have_raised_with_print(self):
        """The defect, restated: this is why the TSV writer exists."""
        sink = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict")
        with self.assertRaises(UnicodeEncodeError):
            print("url\thttps://ex.com/\u0441\u0442\u0440", file=sink)
            sink.flush()

    def test_newline_can_be_suppressed(self):
        sink = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict")
        _errors.write_text_stdout("row", newline=False, stream=sink)
        self.assertEqual(sink.buffer.getvalue(), b"row")


class TestWritePathStdout(unittest.TestCase):
    """A path list is a MACHINE channel (`skills/pdf/SKILL.md`: "All stdout goes
    to the output path list"), and it needs `os.fsencode`, not UTF-8.

    The distinction is not pedantry. POSIX filenames are bytes; Python carries
    an undecodable one as a lone surrogate. `os.fsencode` turns it back into
    the ORIGINAL bytes, so the path the caller captures actually opens.
    `.encode("utf-8")` raises on it, and `say()` would degrade it to a
    plausible-looking string that opens nothing.
    """

    def test_bytes_do_not_depend_on_the_stream_codec(self):
        path = "/tmp/\u0442\u0435\u0441\u0442-caf\u00e9/out.pdf"
        seen = set()
        for enc in ("utf-8", "ascii", "cp1251"):
            with self.subTest(encoding=enc):
                sink = io.TextIOWrapper(io.BytesIO(), encoding=enc, errors="strict")
                _errors.write_path_stdout(path, stream=sink)
                seen.add(sink.buffer.getvalue())
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen.pop(), os.fsencode(path) + b"\n")

    def test_the_emitted_path_actually_opens(self):
        """The property that matters. A transliterated path would pass a
        "did it print something" test and still be useless."""
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "\u0442\u0435\u0441\u0442-caf\u00e9.pdf"
            target.write_bytes(b"%PDF-1.4\n")
            sink = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict")
            _errors.write_path_stdout(target, stream=sink)
            emitted = os.fsdecode(sink.buffer.getvalue().rstrip(b"\n"))
            self.assertTrue(Path(emitted).is_file(), f"emitted path does not open: {emitted!r}")

    def test_an_undecodable_filename_round_trips(self):
        """`.encode("utf-8")` cannot do this — the whole reason for fsencode."""
        path = "/tmp/out\udcff.pdf"
        with self.assertRaises(UnicodeEncodeError):
            path.encode("utf-8")
        sink = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict")
        _errors.write_path_stdout(path, stream=sink)
        self.assertEqual(sink.buffer.getvalue(), os.fsencode(path) + b"\n")

    def test_a_dead_pipe_is_reported_not_swallowed(self):
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        sink = io.TextIOWrapper(open(write_fd, "wb", buffering=0), encoding="ascii")
        self.addCleanup(sink.close)
        with self.assertRaises(BrokenPipeError):
            _errors.write_path_stdout("/tmp/x.pdf", stream=sink)


if __name__ == "__main__":
    unittest.main()

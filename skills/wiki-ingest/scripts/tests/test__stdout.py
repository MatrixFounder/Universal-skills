"""Unit + integration tests for `wiki_ingest._stdout`.

Locks the two independent stdout defects the module closes, plus the
promise it makes about NOT changing anything else. Every number below was
measured on macOS 26.5 / CPython 3.14.4 against a HEAD copy of this
package and against the fixed tree; the fixture is the vault the module
docstring describes (three pages, Cyrillic plus `Böhm-Bawerk`).

- **Axis A — the process locale picked the codec.** `print(json.dumps(…,
  ensure_ascii=False))` hands text to `sys.stdout`'s `TextIOWrapper`,
  which encodes with `PYTHONIOENCODING` and then the locale. At HEAD,
  `scan` on that vault exited **1** with an 11-line `UnicodeEncodeError`
  traceback and **0 bytes** of manifest under `PYTHONIOENCODING=ascii`;
  on a second vault holding only `Böhm-Bawerk.md` it exited **0** while
  writing 382 bytes instead of 383 under `cp1252` — the `ö` left as the
  single byte `0xF6` at offset 247, so the "successful" output was not
  valid UTF-8. `TestLocaleIndependence` and the `scan` / `find` cases in
  `TestCommandsRouteThroughTheHelper` fail if any of that comes back.

- **Axis B — a closed reader replaced the exit code.** An unflushed
  buffer on a dead fd is flushed again during interpreter shutdown;
  CPython prints `Exception ignored while flushing sys.stdout` and
  **substitutes exit status 120**.

  **Payload size is not the gate**, and no test here may rest on it. A
  reader that is *already gone* takes EPIPE at any size: HEAD `scan` on
  the 463-byte fixture vault exited 120 in 10 runs out of 10.
  `TestDeadReaderKeepsTheVerdict.test_an_already_gone_reader…` and
  `TestCommandsRouteThroughTheHelper.test_scan_keeps_its_verdict_when_the_reader_is_already_gone`
  use exactly that shape, on payloads of 128 bytes and 463 bytes.

  Size only decides *which* wrong answer a **still-draining** reader
  gets, so the two tests that do use `head -c 20` assert their own
  payload size first. Sweep of a HEAD-shaped writer against that reader:
  the declared exit code survived up to 64 820 B (this machine's pipe
  holds 65 536 B), was replaced by **120** from 70 220 B through
  129 620 B, and from 135 020 B a raw `BrokenPipeError` traceback escaped
  for exit **1**. `TestDeadReaderKeepsTheVerdict` therefore drives that
  reader at 108 020 B and 432 020 B — one band each, both verified stable
  5 runs out of 5 at HEAD — and `assertEqual`s the byte count so a
  refactor of the payload generator cannot silently drop it into the band
  where broken code passes.

- **Nothing else moves.** `TestSerialisationShape` pins the bytes to what
  `json.dumps` produced before, so a future "simplification" to
  `ensure_ascii=True` (which fixes axis A by rewriting every byte of
  every locale's output) fails here as well as in
  `test_r11_byte_identity.py`.

The axis-A and axis-B cases run the writer in a **subprocess**: both
defects live below the Python level — one in the text layer's codec, one
in the interpreter's shutdown path — and neither is observable from an
in-process `StringIO`.
"""
from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest._stdout import _escape_lone_surrogates, write_json


SCRIPTS_DIR = Path(__file__).resolve().parent.parent
WIKI_OPS = SCRIPTS_DIR / "wiki_ops.py"
PKG = SCRIPTS_DIR / "wiki_ingest"

# A payload the old code could not encode under a non-UTF-8 locale: an em
# dash (present in cp1252 as 0x97, absent from ascii) plus Cyrillic
# (absent from both). Page names in a personal wiki look exactly like this.
NON_ASCII_PAYLOAD = {
    "concepts": ["Кривая доходности", "Спред — кредитный"],
    "note": "Определение — зависимость ставки от срока.",
}


def _run_driver(source: str, *, encoding: str) -> subprocess.CompletedProcess:
    """Run `source` in a subprocess whose stdout codec is `encoding`.

    `PYTHONUTF8=0` is required: PEP 540 UTF-8 mode, on by default in some
    environments, would override `PYTHONIOENCODING` and quietly turn the
    ascii/cp1252 cases into UTF-8 runs that pass against broken code.
    """
    with tempfile.TemporaryDirectory() as tmp:
        driver = Path(tmp) / "driver.py"
        driver.write_text(source, encoding="utf-8")
        env = dict(os.environ,
                   PYTHONPATH=str(SCRIPTS_DIR),
                   PYTHONIOENCODING=encoding,
                   PYTHONUTF8="0")
        env.pop("LC_ALL", None)
        return subprocess.run([sys.executable, str(driver)],
                              capture_output=True, env=env, check=False)


_WRITE_PAYLOAD_DRIVER = """
import sys
sys.path.insert(0, {scripts!r})
from wiki_ingest._stdout import write_json
write_json({payload!r}, indent=2, ensure_ascii=False)
"""


def _write_payload(payload, *, encoding: str) -> subprocess.CompletedProcess:
    return _run_driver(
        _WRITE_PAYLOAD_DRIVER.format(scripts=str(SCRIPTS_DIR), payload=payload),
        encoding=encoding,
    )


class TestLocaleIndependence(unittest.TestCase):
    """Axis A — the bytes on stdout must not depend on the caller's codec."""

    def test_an_ascii_locale_neither_truncates_nor_tracebacks(self):
        got = _write_payload(NON_ASCII_PAYLOAD, encoding="ascii")
        self.assertEqual(got.returncode, 0,
                         f"stderr was:\n{got.stderr.decode('utf-8', 'replace')}")
        self.assertEqual(got.stderr, b"",
                         "an ascii locale must not produce a traceback on a "
                         "channel the CLI promises is one JSON document")
        self.assertEqual(json.loads(got.stdout.decode("utf-8")),
                         NON_ASCII_PAYLOAD)

    def test_a_legacy_locale_does_not_emit_non_utf8_bytes(self):
        got = _write_payload(NON_ASCII_PAYLOAD, encoding="cp1252")
        self.assertEqual(got.returncode, 0)
        # The pre-fix failure mode was silent: exit 0 with an em dash
        # written as the single byte 0x97.
        got.stdout.decode("utf-8")   # raises UnicodeDecodeError if it regressed
        self.assertNotIn(b"\x97", got.stdout)

    def test_the_bytes_are_identical_across_three_locales(self):
        runs = {enc: _write_payload(NON_ASCII_PAYLOAD, encoding=enc).stdout
                for enc in ("utf-8", "ascii", "cp1252")}
        self.assertEqual(runs["ascii"], runs["utf-8"])
        self.assertEqual(runs["cp1252"], runs["utf-8"])

    def test_a_lone_surrogate_is_escaped_rather_than_crashing(self):
        # POSIX decodes an undecodable filename byte to a lone surrogate
        # (`surrogateescape`), and that filename becomes a `path` field in
        # scan / lint / find output. UTF-8 cannot encode it; JSON can.
        payload = {"path": "_concepts/bad\udcff.md"}
        got = _write_payload(payload, encoding="utf-8")
        self.assertEqual(got.returncode, 0,
                         f"stderr was:\n{got.stderr.decode('utf-8', 'replace')}")
        self.assertEqual(json.loads(got.stdout.decode("utf-8")), payload,
                         "the escape must round-trip to the same string")

    def test_the_escape_is_a_no_op_for_ordinary_text(self):
        self.assertIs(_escape_lone_surrogates("plain ascii"), "plain ascii")
        self.assertEqual(_escape_lone_surrogates("Спред — кредитный"),
                         "Спред — кредитный")


class TestSerialisationShape(unittest.TestCase):
    """The module fixes *how* the bytes reach the fd, never *which* bytes."""

    def _captured(self, payload, **kw) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertTrue(write_json(payload, **kw))
        return buf.getvalue()

    def test_indent_is_preserved(self):
        payload = {"a": 1, "b": [2, 3]}
        self.assertEqual(self._captured(payload, indent=2),
                         json.dumps(payload, indent=2) + "\n")

    def test_no_indent_stays_compact(self):
        payload = {"a": 1, "b": [2, 3]}
        self.assertEqual(self._captured(payload), json.dumps(payload) + "\n")

    def test_ensure_ascii_true_matches_json_dumps_byte_for_byte(self):
        # The sites that had the `json.dumps` default (upsert-page,
        # append-log, init, log-event, update-index, ingest) are immune on
        # axis A and must not have their bytes rewritten by the fix.
        payload = {"page": "_concepts/Дюрация.md", "created": False}
        self.assertEqual(self._captured(payload, indent=2),
                         json.dumps(payload, indent=2) + "\n")
        self.assertIn("\\u0414", self._captured(payload, indent=2))

    def test_ensure_ascii_false_matches_json_dumps_byte_for_byte(self):
        self.assertEqual(
            self._captured(NON_ASCII_PAYLOAD, indent=2, ensure_ascii=False),
            json.dumps(NON_ASCII_PAYLOAD, indent=2, ensure_ascii=False) + "\n")

    def test_a_stream_without_a_buffer_keeps_the_text_path(self):
        # `commands/ingest.py::_dispatch_op` and the `reindex` cascade
        # swallow a sub-op's report with `redirect_stdout(StringIO())`.
        # A writer that reached for `sys.stdout.buffer` eagerly, or bound
        # `sys.stdout` at import time, would leak those reports onto the
        # real stdout and corrupt the caller's single JSON document.
        buf = io.StringIO()
        self.assertIsNone(getattr(buf, "buffer", None))
        with redirect_stdout(buf):
            write_json({"swallowed": True})
        self.assertEqual(json.loads(buf.getvalue()), {"swallowed": True})

    def test_an_explicit_stream_argument_is_honoured(self):
        buf = io.StringIO()
        write_json({"x": 1}, stream=buf)
        self.assertEqual(buf.getvalue(), '{"x": 1}\n')

    def test_an_unserialisable_payload_writes_nothing(self):
        # One-shot serialisation, unlike `json.dump(obj, sys.stdout)`,
        # which leaves half a document on the wire before it raises.
        buf = io.StringIO()
        with self.assertRaises(TypeError):
            write_json({"bad": {1, 2}}, stream=buf)
        self.assertEqual(buf.getvalue(), "")

    def test_a_successful_write_reports_true(self):
        self.assertTrue(write_json({"x": 1}, stream=io.StringIO()))


_EXIT_CODE_DRIVER = """
import json, sys
sys.path.insert(0, {scripts!r})
from wiki_ingest._stdout import write_json
payload = {{"pages": ["Концепт — понятие %05d " % i + "x" * 60
                     for i in range({count})]}}
if {report_size}:
    sys.stderr.write("size=%d\\n" % len(
        (json.dumps(payload, indent=2, ensure_ascii=False) + "\\n")
        .encode("utf-8")))
reached = write_json(payload, indent=2, ensure_ascii=False)
if {report_reached}:
    sys.stderr.write("reached=%s\\n" % reached)
sys.exit(7)
"""


class TestDeadReaderKeepsTheVerdict(unittest.TestCase):
    """Axis B — a reader that goes away must not rewrite the exit code.

    Two reader shapes, because they fail differently:

    * **already gone** — the read end is closed before the writer starts.
      EPIPE at any size, so this is the shape that needs no threshold.
    * **drains 20 bytes, then closes** — `… | head -c 20`. Here the
      payload must clear the pipe buffer or the kernel absorbs the whole
      document and the test is green against broken code, which is why
      both cases assert the byte count the driver actually produced
      (measured by the driver itself, not recomputed here, so the two
      cannot drift apart).
    """

    # Bands measured against a HEAD-shaped writer and the draining reader
    # on this machine, 5 runs each: 108 020 B sits inside the
    # 70 220-129 620 B window that exited 120; 432 020 B is past the
    # 135 020 B point where a raw traceback escaped for exit 1. The pipe
    # itself holds 65 536 B.
    PIPE_CAPACITY = 65_536
    BAND_120_ITEMS, BAND_120_BYTES = 1000, 108_020
    BAND_TRACEBACK_ITEMS, BAND_TRACEBACK_BYTES = 4000, 432_020
    # An already-gone reader needs no size at all: HEAD `scan` reproduced
    # exit 120 on a 463-byte manifest, 10 runs out of 10.
    TINY_ITEMS, TINY_BYTES = 1, 128

    def _driver(self, count, *, report_size=False, report_reached=False):
        return _EXIT_CODE_DRIVER.format(
            scripts=str(SCRIPTS_DIR), count=count,
            report_size="True" if report_size else "False",
            report_reached="True" if report_reached else "False")

    def _measured_bytes(self, count):
        """Byte count of the document the driver writes, from the driver."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "driver.py"
            path.write_text(self._driver(count, report_size=True),
                            encoding="utf-8")
            got = subprocess.run(
                [sys.executable, str(path)], stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, check=False,
                env=dict(os.environ, PYTHONPATH=str(SCRIPTS_DIR),
                         PYTHONIOENCODING="utf-8"))
        line = got.stderr.decode("utf-8", "replace").strip()
        self.assertTrue(line.startswith("size="), line)
        return int(line.removeprefix("size="))

    def _run(self, count, *, reader, report_reached=False):
        """Run the driver with `reader` on the other end of its stdout.

        `reader="gone"` closes the read end before the child can write;
        `reader="drain20"` reads 20 bytes and then closes, the shape a
        `… | head -c 20` pipeline produces.
        """
        source = self._driver(count, report_reached=report_reached)
        with tempfile.TemporaryDirectory() as tmp:
            driver = Path(tmp) / "driver.py"
            driver.write_text(source, encoding="utf-8")
            read_fd, write_fd = os.pipe()
            proc = subprocess.Popen(
                [sys.executable, str(driver)], stdout=write_fd,
                stderr=subprocess.PIPE,
                env=dict(os.environ, PYTHONPATH=str(SCRIPTS_DIR),
                         PYTHONIOENCODING="utf-8"))
            os.close(write_fd)
            try:
                if reader == "drain20":
                    os.read(read_fd, 20)
            finally:
                os.close(read_fd)
            stderr = proc.stderr.read().decode("utf-8", "replace")
            proc.stderr.close()
            return proc.wait(), stderr

    def test_an_already_gone_reader_does_not_replace_the_exit_code(self):
        # The size-independent case: 128 bytes, 512× smaller than the
        # pipe buffer, and still exit 120 at HEAD.
        measured = self._measured_bytes(self.TINY_ITEMS)
        self.assertEqual(measured, self.TINY_BYTES)
        self.assertLess(measured, self.PIPE_CAPACITY,
                        "this case exists to show a payload that FITS the "
                        "pipe still loses its exit code")
        rc, _ = self._run(self.TINY_ITEMS, reader="gone")
        self.assertEqual(rc, 7, "the exit status must stay the one the "
                                "command declared, not CPython's 120")

    def test_a_draining_reader_does_not_replace_the_exit_code_in_the_120_band(self):
        measured = self._measured_bytes(self.BAND_120_ITEMS)
        self.assertEqual(measured, self.BAND_120_BYTES,
                         "the payload must stay in the 70 220-129 620 B "
                         "band that exited 120 at HEAD; below the pipe "
                         "buffer this test passes against broken code")
        rc, _ = self._run(self.BAND_120_ITEMS, reader="drain20")
        self.assertEqual(rc, 7)

    def test_a_draining_reader_does_not_replace_the_exit_code_in_the_traceback_band(self):
        measured = self._measured_bytes(self.BAND_TRACEBACK_ITEMS)
        self.assertEqual(measured, self.BAND_TRACEBACK_BYTES,
                         "the payload must stay past 135 020 B, where a "
                         "raw BrokenPipeError traceback escaped at HEAD")
        rc, _ = self._run(self.BAND_TRACEBACK_ITEMS, reader="drain20")
        self.assertEqual(rc, 7)

    def test_a_dead_reader_leaves_stderr_untouched(self):
        for count, reader in ((self.TINY_ITEMS, "gone"),
                              (self.BAND_120_ITEMS, "drain20"),
                              (self.BAND_TRACEBACK_ITEMS, "drain20")):
            with self.subTest(payload_items=count, reader=reader):
                _, stderr = self._run(count, reader=reader)
                self.assertEqual(stderr, "", "a walked-away reader is not an "
                                            "error to report to anyone")

    def test_write_json_reports_false_when_the_reader_is_gone(self):
        rc, stderr = self._run(self.BAND_TRACEBACK_ITEMS, reader="drain20",
                               report_reached=True)
        self.assertEqual(rc, 7)
        self.assertEqual(stderr.strip(), "reached=False",
                         "the caller must be able to tell the document did "
                         "not land, even though nothing raised")


def _print_json_dumps_sites(path: Path) -> list[int]:
    """Line numbers of `print(json.dumps(...))` / `json.dump(..., sys.stdout)`.

    Both forms encode through the text layer and are exactly what this
    module replaced. `json.dumps(...)` on its own is NOT flagged: it is
    legitimate for `_frontmatter`'s YAML scalars and for
    `ingest._json_error_envelope`, whose product goes to stderr.
    """
    hits: list[int] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "print" and node.args:
            inner = node.args[0]
            if (isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "dumps"):
                hits.append(node.lineno)
        if isinstance(func, ast.Attribute) and func.attr == "dump" and \
                len(node.args) >= 2:
            sink = node.args[1]
            if isinstance(sink, ast.Attribute) and sink.attr == "stdout":
                hits.append(node.lineno)
    return hits


class TestEveryStdoutSiteIsRouted(unittest.TestCase):
    """Structural gate — a new command must not reintroduce the defect.

    The fix is 23 call sites wide; a test that only exercises `scan` would
    let the twenty-fourth ship broken.
    """

    def test_no_command_writes_json_through_the_text_layer(self):
        offenders = {
            str(p.relative_to(SCRIPTS_DIR)): lines
            for p in sorted(PKG.rglob("*.py"))
            if (lines := _print_json_dumps_sites(p))
        }
        self.assertEqual(offenders, {},
                         "use `wiki_ingest._stdout.write_json`: "
                         "`print(json.dumps(...))` and "
                         "`json.dump(..., sys.stdout)` encode with the "
                         "process locale and lose the exit code on a dead "
                         "pipe")

    def test_the_detector_itself_sees_a_planted_offender(self):
        with tempfile.TemporaryDirectory() as tmp:
            planted = Path(tmp) / "planted.py"
            planted.write_text(
                "import json, sys\n"
                "print(json.dumps({'a': 1}))\n"
                "json.dump({'a': 1}, sys.stdout)\n"
                "x = json.dumps({'a': 1})\n",       # allowed: not written here
                encoding="utf-8")
            self.assertEqual(_print_json_dumps_sites(planted), [2, 3])


class TestCommandsRouteThroughTheHelper(unittest.TestCase):
    """Integration — the real CLI, the real defect, on a real vault.

    These are the cases that fail if a call site is reverted to
    `print(json.dumps(...))`; everything above tests the helper itself.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.vault = Path(cls._tmp.name) / "vault"
        cls._cli("init", str(cls.vault))
        for name in ("Кривая доходности", "Спред — кредитный"):
            cls._cli("upsert-page", str(cls.vault), "--kind", "concept",
                     "--name", name, "--source-slug", "урок-01",
                     "--source-title", "Урок 1 — облигации",
                     "--source-date", "2026-08-30",
                     "--definition", "Форма — зависимость ставки от срока.")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @classmethod
    def _cli(cls, *argv, encoding="utf-8", check=True):
        env = dict(os.environ, PYTHONIOENCODING=encoding, PYTHONUTF8="0")
        env.pop("LC_ALL", None)
        got = subprocess.run([sys.executable, str(WIKI_OPS), *argv],
                             capture_output=True, cwd=str(SCRIPTS_DIR),
                             env=env, check=False)
        if check and got.returncode != 0:
            raise AssertionError(
                f"wiki_ops.py {' '.join(argv)} exited {got.returncode}\n"
                f"--- stderr ---\n{got.stderr.decode('utf-8', 'replace')}")
        return got

    def test_scan_emits_the_same_bytes_under_ascii_and_cp1252(self):
        baseline = self._cli("scan", str(self.vault)).stdout
        self.assertIn("Спред".encode("utf-8"), baseline, "fixture sanity")
        for encoding in ("ascii", "cp1252"):
            with self.subTest(encoding=encoding):
                got = self._cli("scan", str(self.vault), encoding=encoding,
                                check=False)
                self.assertEqual(got.returncode, 0,
                                 got.stderr.decode("utf-8", "replace"))
                self.assertEqual(got.stderr, b"")
                self.assertEqual(got.stdout, baseline)

    def test_find_survives_an_ascii_locale(self):
        got = self._cli("find", str(self.vault), "--terms", "Спред",
                        encoding="ascii", check=False)
        self.assertEqual(got.returncode, 0,
                         got.stderr.decode("utf-8", "replace"))
        # `find` case-folds its terms; the point here is that the Cyrillic
        # survives the ascii stdout codec at all.
        self.assertEqual(json.loads(got.stdout.decode("utf-8"))["query_terms"],
                         ["спред"])

    def test_an_ascii_only_site_keeps_its_escaped_bytes(self):
        # `upsert-page` had the `ensure_ascii` default: immune on axis A
        # and measured byte-identical before and after the fix. Locked so
        # nobody "completes" the change by flipping it to ensure_ascii=False.
        got = self._cli("upsert-page", str(self.vault), "--kind", "concept",
                        "--name", "Дюрация", "--source-slug", "урок-01",
                        "--source-title", "Урок 1", "--source-date",
                        "2026-08-30", "--fact", "Факт — первый.",
                        encoding="ascii")
        self.assertIn(b"\\u0414\\u044e\\u0440", got.stdout)
        self.assertEqual(json.loads(got.stdout.decode("ascii"))["page"],
                         "_concepts/Дюрация.md")

    def test_scan_keeps_its_verdict_when_the_reader_walks_away(self):
        """A 343 KB manifest piped into a reader that reads 20 bytes.

        At HEAD this exited 1 with an 11-line `BrokenPipeError` traceback
        where `scan`'s contract is exit 0 and one JSON document.
        """
        big = Path(self._tmp.name) / "big"
        self._cli("init", str(big))
        pad = "a" * 100
        for i in range(2600):
            (big / "_concepts" / f"Концепт — {i:04d} {pad}.md").write_text(
                "---\nkind: concept\n---\n\n# x\n", encoding="utf-8")
        self.assertGreater(len(self._cli("scan", str(big)).stdout), 300_000,
                           "the manifest must dwarf the 64 KiB pipe buffer "
                           "or this test is green against broken code")

        read_fd, write_fd = os.pipe()
        proc = subprocess.Popen(
            [sys.executable, str(WIKI_OPS), "scan", str(big)],
            stdout=write_fd, stderr=subprocess.PIPE, cwd=str(SCRIPTS_DIR),
            env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        os.close(write_fd)
        try:
            os.read(read_fd, 20)
        finally:
            os.close(read_fd)
        stderr = proc.stderr.read().decode("utf-8", "replace")
        proc.stderr.close()
        self.assertEqual(proc.wait(), 0,
                         "scan's contract verdict is 0; a dead reader must "
                         "not turn it into 120 or 1")
        self.assertEqual(stderr, "")

    def test_scan_keeps_its_verdict_when_the_reader_is_already_gone(self):
        """The 463-byte fixture manifest, into a reader that never reads.

        The case that proves payload size is not the gate: this document
        is 140× smaller than the pipe buffer, `… | head -c 20` absorbs it
        entirely and exits 0 even at HEAD — yet against a reader that has
        already closed, HEAD exited **120** with two non-JSON stderr
        lines, 10 runs out of 10.
        """
        manifest = self._cli("scan", str(self.vault)).stdout
        self.assertLess(len(manifest), 65_536,
                        "this case is about a payload that FITS the pipe "
                        "buffer; if it grew past it, it is testing the "
                        "other failure mode")

        read_fd, write_fd = os.pipe()
        proc = subprocess.Popen(
            [sys.executable, str(WIKI_OPS), "scan", str(self.vault)],
            stdout=write_fd, stderr=subprocess.PIPE, cwd=str(SCRIPTS_DIR),
            env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        os.close(write_fd)
        os.close(read_fd)          # gone before the child can write a byte
        stderr = proc.stderr.read().decode("utf-8", "replace")
        proc.stderr.close()
        self.assertEqual(proc.wait(), 0,
                         "scan declared 0; the interpreter's shutdown flush "
                         "must not substitute 120")
        self.assertEqual(stderr, "")


if __name__ == "__main__":
    unittest.main()

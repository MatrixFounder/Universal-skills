"""Tests for the stdout channel of `pdf_fill_form.py`.

Regression lock for PDF-CLI-STDOUT-JSON-LOCALE-CLASS on this script's three
JSON-on-stdout sites — `--check`, `--extract-fields` (the stdout half), and
the fill report — plus the one human-readable line the `--extract-fields -o
FILE` branch prints, which is not JSON but shares fd 1 with it. The JSON
sites used to hand a text-layer write the job of encoding a machine-readable
channel; the defect has two independent axes:

  (A) ENCODING — the process locale picked the codec. Measured on HEAD before
      the fix, with a field value of `Café — Приве́т 😀`:
      `--check` under `PYTHONIOENCODING=ascii` exited 1 with 114 bytes of
      truncated JSON already on stdout and an 11-line traceback where
      `--json-errors` promises one line of JSON; the two `print(...)` sites
      exited 1 with 0 bytes on stdout and an 8-line traceback. Under
      `cp1252`, with a value the codec can encode (`Cafe — dash`), all three
      exited 0 having written the em dash as the single byte 0x97 — 140 bytes
      that no UTF-8 reader can decode, against 142 correct ones.
  (B) BROKEN PIPE — the interpreter's shutdown flush hit the dead fd, printed
      `Exception ignored while flushing sys.stdout` on stderr and replaced
      the exit status.

**Payload size is not the gate on axis B.** A reader that is already gone
when the write happens raises EPIPE whatever the payload weighs: measured on
HEAD, `--check` on the *small* form (a 158-byte payload) through an fd 1 with
no reader exited **120** with 85 bytes of `Exception ignored while flushing
sys.stdout` — the same outcome as the 352933-byte payload, which exited 120
with an 880-byte traceback on top. Size only decides which failure mode shows
up, so both forms are exercised here: `_run_with_dead_reader` (no reader at
all, deterministic, any size) and the `| head` form (`.read(20)` then close),
which needs a payload past this machine's pipe buffer — well over the POSIX
minimum 64 KiB; the first EPIPE observed here was around 105 KB — and whose
fixtures `test_the_payloads_exceed_this_machines_pipe_buffer` guards.

Most assertions are about the BYTES on fd 1 under a locale that is not
UTF-8, so they run the real interpreter in a subprocess; an in-process test
cannot observe that layer.

Run:
    cd skills/pdf/scripts
    ./.venv/bin/python -m unittest tests.test_pdf_fill_form -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import pdf_fill_form  # noqa: E402

SCRIPT = SCRIPTS_DIR / "pdf_fill_form.py"

# One field value per hazard class the payload has to survive: Latin-1, BMP
# beyond it, and astral. `cp1252` can encode none of Приве́т/😀, so the
# silent-corruption half of axis A needs its own value the codec *can* encode.
RICH_VALUE = "Café — Приве́т \U0001F600"
CP1252_VALUE = "Cafe — dash"

# 3000 fields ≈ a 352 KB payload. The pipe buffer on the development machine
# holds well over the POSIX-minimum 64 KiB (the first measured EPIPE was at
# ~105 KB), so a small fixture would make the axis-B tests pass against the
# unfixed code.
BIG_FIELD_COUNT = 3000
UNKNOWN_KEY_COUNT = 40000


def _build_form(out: Path, *, value: str, fields: int = 1) -> Path:
    """A minimal AcroForm PDF whose text fields carry `value` as `/V`.

    reportlab draws the widgets but refuses a value its base-14 font cannot
    escape, so the value is written afterwards with pypdf as a plain text
    string object — which is what a real form filled by any other tool
    carries, and what `--check` reads back.
    """
    from reportlab.lib.colors import black, white  # type: ignore
    from reportlab.pdfgen import canvas  # type: ignore
    import pypdf  # type: ignore
    from pypdf.generic import NameObject, TextStringObject  # type: ignore

    out.parent.mkdir(parents=True, exist_ok=True)
    raw = out.with_suffix(".raw.pdf")
    c = canvas.Canvas(str(raw), pagesize=(612, 792))
    c.setFont("Helvetica", 14)
    c.drawString(72, 740, "Test invoice")
    form = c.acroForm
    for i in range(fields):
        form.textfield(name=f"customer_name_{i}", x=160, y=692, width=280,
                       height=22, borderColor=black, fillColor=white,
                       maxlen=80, fontSize=11)
    c.save()

    reader = pypdf.PdfReader(str(raw))
    writer = pypdf.PdfWriter(clone_from=reader)
    for ref in writer.root_object["/AcroForm"]["/Fields"]:
        ref.get_object()[NameObject("/V")] = TextStringObject(value)
    with open(out, "wb") as fh:
        writer.write(fh)
    raw.unlink()
    return out


def _run(args: list[str], *, encoding: str | None = None):
    """Run the CLI in a subprocess, optionally under a legacy stdio codec.
    Bytes, not text: the point of these tests is what lands on fd 1."""
    env = dict(os.environ)
    if encoding is None:
        env.update(PYTHONUTF8="1")
        env.pop("PYTHONIOENCODING", None)
    else:
        env.update(PYTHONIOENCODING=encoding, PYTHONUTF8="0",
                   LC_ALL="C", LANG="C")
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          cwd=str(SCRIPTS_DIR), capture_output=True, env=env)


def _run_with_dead_reader(args: list[str]) -> tuple[int, bytes]:
    """Run the CLI with an fd 1 that has **no reader at all**; (rc, stderr).

    Both ends of the pipe are closed in the parent, so the very first write
    is EPIPE regardless of payload size — unlike `| head`, where the outcome
    depends on whether the payload happened to fit in the kernel buffer
    before the reader exited. This is the form that shows the defect on a
    158-byte payload (HEAD: rc 120).
    """
    env = dict(os.environ, PYTHONUTF8="1")
    read_fd, write_fd = os.pipe()
    try:
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT), *args], cwd=str(SCRIPTS_DIR),
            stdout=write_fd, stderr=subprocess.PIPE, env=env)
    finally:
        os.close(write_fd)
        os.close(read_fd)
    _, err = proc.communicate(timeout=180)
    return proc.returncode, err


class _FormFixtures(unittest.TestCase):
    """Shared, built once: the AcroForms and data files the cases below use."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        cls.form = _build_form(root / "form.pdf", value=RICH_VALUE)
        cls.form_1252 = _build_form(root / "form1252.pdf", value=CP1252_VALUE)
        cls.out_pdf = root / "out.pdf"
        cls.root = root

        cls.data = root / "data.json"
        cls.data.write_text(json.dumps(
            {"customer_name_0": "ok", "неизвестное — поле \U0001F600": "x"},
            ensure_ascii=False), encoding="utf-8")
        cls.data_1252 = root / "data1252.json"
        cls.data_1252.write_text(json.dumps(
            {"customer_name_0": "ok", "unknown — field": "x"},
            ensure_ascii=False), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _sites(self, *, value_1252: bool = False):
        """The three stdout-JSON sites as (label, argv) pairs."""
        form = self.form_1252 if value_1252 else self.form
        data = self.data_1252 if value_1252 else self.data
        return [
            ("check", ["--check", str(form)]),
            ("extract_fields", ["--extract-fields", str(form)]),
            ("fill_report", [str(form), str(data), "-o", str(self.out_pdf)]),
        ]


class TestStdoutEncoding(_FormFixtures):
    """Axis A: the bytes of the payload must not depend on the caller's
    locale. JSON is UTF-8 by definition (RFC 8259 §8.1)."""

    def test_an_ascii_locale_does_not_truncate_the_payload(self):
        """Was: `--check` left 114 bytes of truncated JSON on stdout and an
        11-line `UnicodeEncodeError` traceback at exit 1; the two `print(...)`
        sites left 0 bytes and an 8-line traceback. `--json-errors` promises
        exactly one line of JSON on stderr in either case."""
        for label, argv in self._sites():
            with self.subTest(site=label):
                proc = _run(argv + ["--json-errors"], encoding="ascii")
                self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
                self.assertNotIn(b"Traceback", proc.stderr)
                payload = json.loads(proc.stdout.decode("utf-8"))
                if label == "fill_report":
                    self.assertEqual(payload["skipped_unknown_fields"],
                                     ["неизвестное — поле \U0001F600"])
                else:
                    self.assertEqual(payload["fields"][0]["value"], RICH_VALUE)

    def test_a_legacy_locale_cannot_change_a_single_byte(self):
        """Was: exit 0 with the em dash written as cp1252's single byte 0x97 —
        140 bytes no UTF-8 reader can decode, against 142 correct ones, and
        nothing on stderr said so. Byte equality with the UTF-8 run is the
        assertion, not merely `json.loads` succeeding: a fix that quietly
        switched to `ensure_ascii=True` would parse fine and still be wrong."""
        for label, argv in self._sites(value_1252=True):
            with self.subTest(site=label):
                native = _run(argv)
                legacy = _run(argv, encoding="cp1252")
                self.assertEqual(native.returncode, 0, native.stderr[-400:])
                self.assertEqual(legacy.returncode, 0, legacy.stderr[-400:])
                legacy.stdout.decode("utf-8")   # raises on the 0x97 mojibake
                self.assertEqual(legacy.stdout, native.stdout)
                # The em dash as its own three UTF-8 bytes. (Asserting 0x97 is
                # absent would be wrong — it is a legal continuation byte.)
                self.assertIn("—".encode("utf-8"), legacy.stdout)

    def test_the_payload_keeps_its_characters_rather_than_escaping_them(self):
        """`ensure_ascii=False` is the point: the fix changes how the payload
        is *encoded*, it does not fall back to ASCII escapes."""
        proc = _run(["--check", str(self.form)], encoding="ascii")
        self.assertIn("—".encode("utf-8"), proc.stdout)
        self.assertIn("Приве́т".encode("utf-8"), proc.stdout)
        # ...and NOT as the `\u2014` escape ensure_ascii=True would emit.
        self.assertNotIn(rb"\u2014", proc.stdout)

    def test_extract_fields_writes_the_same_bytes_to_stdout_and_to_a_file(self):
        """The `-o` half was already UTF-8 (`encoding="utf-8"`) and is the
        reference. The two halves now serialise separately, so lock them
        together — a drift in either one's arguments shows up here."""
        target = self.root / "fields.json"
        proc = _run(["--extract-fields", str(self.form), "-o", str(target)],
                    encoding="ascii")
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        to_stdout = _run(["--extract-fields", str(self.form)],
                         encoding="ascii")
        self.assertEqual(target.read_bytes(), to_stdout.stdout)


class TestBrokenPipe(_FormFixtures):
    """Axis B: a reader that hangs up must not make the process contradict
    the envelope it just wrote."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.big_form = _build_form(cls.root / "bigform.pdf",
                                   value=RICH_VALUE, fields=BIG_FIELD_COUNT)
        cls.big_data = cls.root / "bigdata.json"
        cls.big_data.write_text(json.dumps(
            {"customer_name_0": "ok",
             **{"unknown—%06d" % i: "x" for i in range(UNKNOWN_KEY_COUNT)}},
            ensure_ascii=False), encoding="utf-8")

    def _big_sites(self):
        return [
            ("check", ["--check", str(self.big_form)]),
            ("extract_fields", ["--extract-fields", str(self.big_form)]),
            ("fill_report", [str(self.form), str(self.big_data),
                             "-o", str(self.out_pdf)]),
        ]

    def test_the_payloads_exceed_this_machines_pipe_buffer(self):
        """Guard on the guard: if a future change shrinks these fixtures the
        axis-B cases below go green against broken code without saying so.
        Measured sizes were 352933 / 352933 / 960241 bytes; the first EPIPE
        observed on this machine was at ~105 KB."""
        for label, argv in self._big_sites():
            with self.subTest(site=label):
                proc = _run(argv)
                self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
                self.assertGreater(len(proc.stdout), 300_000)

    def test_a_dead_pipe_exits_with_the_code_the_envelope_declares(self):
        """Was: `--check` exited 120 (the shutdown flush's substitution) and
        the two `print(...)` sites exited 1 with a raw `BrokenPipeError`
        traceback — 13 and 8 lines on stderr where `--json-errors` promises
        one, and an exit status a wrapper cannot reconcile with it."""
        env = dict(os.environ, PYTHONUTF8="1")
        for label, argv in self._big_sites():
            with self.subTest(site=label):
                proc = subprocess.Popen(
                    [sys.executable, str(SCRIPT), *argv, "--json-errors"],
                    cwd=str(SCRIPTS_DIR), stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, env=env)
                proc.stdout.read(20)
                proc.stdout.close()          # the `| head` moment
                err = proc.stderr.read().decode("utf-8", "replace")
                proc.stderr.close()
                rc = proc.wait(timeout=180)

                self.assertNotIn("Exception ignored", err)
                lines = [ln for ln in err.splitlines() if ln.strip()]
                self.assertEqual(len(lines), 1, err)   # only the envelope
                envelope = json.loads(lines[0])
                self.assertEqual(envelope["type"], "OutputWriteFailed")
                self.assertEqual(envelope["details"]["path"], "stdout")
                self.assertEqual(rc, envelope["code"])  # never 120, never 1
                self.assertEqual(rc, pdf_fill_form.EXIT_OUTPUT_WRITE)

    def test_a_reader_that_is_already_gone_does_not_need_a_big_payload(self):
        """Payload size is not the gate. The small form's `--check` payload is
        158 bytes — it fits in the kernel's pipe buffer many times over — and
        on HEAD it still exited **120** with 85 bytes of `Exception ignored
        while flushing sys.stdout`, because the reader was gone before the
        write. A fix that only handled 'big enough to block' would pass the
        `| head` cases above and fail here."""
        payload = _run(["--check", str(self.form)]).stdout
        self.assertLess(len(payload), 4096, "fixture grew; the point of this "
                                            "case is a payload that fits")
        rc, err = _run_with_dead_reader(
            ["--check", str(self.form), "--json-errors"])
        self.assertNotIn(b"Exception ignored", err)
        self.assertNotIn(b"Traceback", err)
        lines = [ln for ln in err.decode("utf-8", "replace").splitlines()
                 if ln.strip()]
        self.assertEqual(len(lines), 1, err)
        envelope = json.loads(lines[0])
        self.assertEqual(envelope["type"], "OutputWriteFailed")
        self.assertEqual(rc, envelope["code"])
        self.assertEqual(rc, pdf_fill_form.EXIT_OUTPUT_WRITE)

    def test_the_broken_pipe_code_collides_with_no_other_exit_code(self):
        """`EXIT_OUTPUT_WRITE` has to stay distinguishable from a fill that
        actually failed (10), XFA (11), no-form (12), argparse (2) and
        success (0) — a wrapper routes on the number alone."""
        codes = [pdf_fill_form.EXIT_OK, pdf_fill_form.EXIT_FILL_ERROR,
                 pdf_fill_form.EXIT_XFA, pdf_fill_form.EXIT_NO_FORM,
                 pdf_fill_form.EXIT_OUTPUT_WRITE, 2]
        self.assertEqual(len(codes), len(set(codes)))


class TestExtractFieldsStatusLine(_FormFixtures):
    """The `--extract-fields -o FILE` branch writes the schema to the file and
    one human-readable line to stdout. That line is not JSON and is NOT part
    of the byte contract — the caller's codec still renders it — but it must
    not fail a run whose file is already on disk, and it must not let the
    interpreter rewrite the exit status."""

    def test_an_unrenderable_output_path_does_not_fail_a_written_file(self):
        """Was: `-o 'поля—fields.json'` under `PYTHONIOENCODING=ascii` wrote
        the schema correctly and then died on the status line — an 8-line
        `UnicodeEncodeError` traceback at exit 1, telling the caller the run
        failed about a file that exists."""
        target = self.root / "поля—fields.json"
        proc = _run(["--extract-fields", str(self.form), "-o", str(target),
                     "--json-errors"], encoding="ascii")
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        self.assertNotIn(b"Traceback", proc.stderr)
        # The file is the deliverable and is unaffected by the locale.
        written = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(written["fields"][0]["value"], RICH_VALUE)
        # The status line survives, with what ascii cannot render escaped
        # rather than dropped or fatal.
        self.assertTrue(proc.stdout.startswith(b"Wrote 1 field(s) to "),
                        proc.stdout)
        self.assertTrue(proc.stdout.isascii(), proc.stdout)
        # Every character ascii cannot render arrives as a `backslashreplace`
        # escape (`п…—fields.json`), not dropped and not fatal.
        self.assertIn(target.name.encode("ascii", "backslashreplace"),
                      proc.stdout)

    def test_a_dead_reader_on_the_status_line_names_the_file_it_wrote(self):
        """Was: exit **120** with 85 bytes of `Exception ignored while
        flushing sys.stdout` — no envelope at all, and an exit status a
        wrapper cannot reconcile with anything. The reader is already gone, so
        no payload size is needed (the line is ~60 bytes)."""
        target = self.root / "fields_deadpipe.json"
        rc, err = _run_with_dead_reader(
            ["--extract-fields", str(self.form), "-o", str(target),
             "--json-errors"])
        self.assertNotIn(b"Exception ignored", err)
        self.assertNotIn(b"Traceback", err)
        lines = [ln for ln in err.decode("utf-8", "replace").splitlines()
                 if ln.strip()]
        self.assertEqual(len(lines), 1, err)
        envelope = json.loads(lines[0])
        self.assertEqual(envelope["type"], "OutputWriteFailed")
        self.assertEqual(rc, envelope["code"])
        self.assertEqual(rc, pdf_fill_form.EXIT_OUTPUT_WRITE)
        # The schema went to the file; an envelope that only said "stdout"
        # would send the caller looking for a payload that is not there.
        self.assertEqual(envelope["details"]["output_path"], str(target))
        self.assertIn(str(target), envelope["error"])
        self.assertTrue(target.is_file())
        self.assertEqual(
            json.loads(target.read_text(encoding="utf-8"))["type"], "acroform")


if __name__ == "__main__":
    unittest.main()

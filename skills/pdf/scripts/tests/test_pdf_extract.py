"""Tests for `pdf_extract.py` — the PDF → structured-JSON-dump helper (TASK 013).

Stub-First (`tdd-stub-first`): task 013-01 lands the smoke E2E + the stub-phase
unit cluster (assert sentinel behaviour on stubs); tasks 013-02 / 013-03 / 013-04
UPDATE the assertions to real values as logic lands.

Run:
    cd skills/pdf/scripts
    ./.venv/bin/python -m unittest tests.test_pdf_extract -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import pdf_extract  # noqa: E402

from tests import _pdf_extract_fixtures as fixtures  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SCRIPT = SCRIPTS_DIR / "pdf_extract.py"


NEEDED_FIXTURES = [
    "digital.pdf", "scanlike.pdf", "encrypted.pdf", "glued.pdf",
    "unmapped.pdf", "embedded.pdf", "bullets.pdf", "shaded.pdf", "figure.pdf",
]


def _ensure_fixtures() -> None:
    """Build the fixtures if any is missing (they are gitignored — the builder
    module is the committed provenance)."""
    if not all((FIXTURES_DIR / n).is_file() for n in NEEDED_FIXTURES):
        fixtures.build_all(FIXTURES_DIR)


def _run_cli(args: list[str]):
    """Run `pdf_extract.py` as a subprocess from the scripts dir."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(SCRIPTS_DIR), capture_output=True, text=True,
    )


@contextlib.contextmanager
def _silence_fd_stderr():
    """Capture writes to OS fd 2 (real stderr). `_errors.report_error` binds
    `sys.stderr` as an import-time default, so `redirect_stderr` cannot reach
    it — only fd-level redirection keeps in-process `main()` tests quiet."""
    saved = os.dup(2)
    with tempfile.TemporaryFile(mode="w+") as sink:
        os.dup2(sink.fileno(), 2)
        try:
            yield sink
        finally:
            os.dup2(saved, 2)
            os.close(saved)


class TestStubSmoke(unittest.TestCase):
    """013-01 smoke E2E — passes on the stubs (Red → Green)."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_fixtures()

    def test_help_lists_surface(self):
        """TC-E2E-01 — `--help` exits 0 and lists the full CLI surface +
        the 'dump, not a Markdown converter' disclaimer."""
        r = _run_cli(["--help"])
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        for flag in ("INPUT", "-o", "--output", "--layout", "--password",
                     "--x-tolerance-ratio", "--y-tolerance", "--table-strategy",
                     "--json-errors"):
            self.assertIn(flag, out)
        # Collapse argparse line-wrapping before phrase checks.
        norm = " ".join(out.split())
        self.assertIn("dump", norm.lower())
        self.assertIn("NOT a Markdown converter", norm)


class TestStubUnits(unittest.TestCase):
    """013-01 stub-phase unit cluster."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_fixtures()

    def test_module_imports(self):
        """TC-UNIT-01."""
        self.assertTrue(hasattr(pdf_extract, "main"))
        self.assertTrue(hasattr(pdf_extract, "extract_pdf"))

    def test_constants_locked(self):
        """TC-UNIT-02 — frozen constants."""
        self.assertEqual(pdf_extract._SCANNED_CHAR_THRESHOLD, 10)
        self.assertEqual(pdf_extract._EXIT_OK, 0)
        self.assertEqual(pdf_extract._EXIT_FAIL, 1)
        self.assertEqual(pdf_extract._EXIT_USAGE, 2)
        self.assertEqual(pdf_extract._EXIT_SELF_OVERWRITE, 6)
        self.assertEqual(pdf_extract._EXIT_SCANNED, 10)
        self.assertEqual(pdf_extract._FIGURE_COVERAGE_THRESHOLD, 0.25)
        self.assertEqual(pdf_extract._FIGURE_CHAR_THRESHOLD, 200)
        self.assertEqual(pdf_extract._DEFAULT_TABLE_STRATEGY, "lines")
        self.assertEqual(
            pdf_extract._TABLE_STRATEGIES, ("lines", "lines_strict"))

    # TC-UNIT-03 (test_main_returns_sentinel) retired by 013-04 per
    # tdd-stub-first §2.4 — `main` now returns real exit codes; covered by
    # TestCliAndEmit (TC-UNIT-23 + TC-E2E-04..12).
    # TC-UNIT-04 (test_classify_stubs) retired by 013-03 per tdd-stub-first
    # §2.4 — the classifier is no longer stubbed; real behaviour is covered by
    # TestScanClassifier (TC-UNIT-13..20).

    def test_extract_pdf_sentinel(self):
        """TC-UNIT-05 — the DumpDocument carries exactly its 10 top-level keys,
        so a consumer can rely on the shape and a dropped signal is caught."""
        dump = pdf_extract.extract_pdf(
            FIXTURES_DIR / "digital.pdf", password=None, layout=False)
        self.assertEqual(
            set(dump),
            {"page_count", "doc_scanned", "scanned_pages", "figure_pages",
             "text_layer_lossy", "x_tolerance_ratio", "y_tolerance",
             "table_strategy", "fonts", "pages"})

    def test_fixtures_exist_and_valid(self):
        """TC-UNIT-06 — every fixture is present and well-formed."""
        import pdfplumber  # type: ignore

        for name in NEEDED_FIXTURES:
            self.assertTrue((FIXTURES_DIR / name).is_file(), name)

        with pdfplumber.open(str(FIXTURES_DIR / "digital.pdf")) as pdf:
            self.assertGreaterEqual(len(pdf.pages), 2)

        with pdfplumber.open(str(FIXTURES_DIR / "scanlike.pdf")) as pdf:
            page = pdf.pages[0]
            self.assertTrue(page.images, "scan-like page must have an image")
            self.assertEqual((page.extract_text() or "").strip(), "",
                             "scan-like page must have zero extractable text")

        with self.assertRaises(Exception):
            pdfplumber.open(str(FIXTURES_DIR / "encrypted.pdf"))
        with pdfplumber.open(str(FIXTURES_DIR / "encrypted.pdf"),
                             password=fixtures.ENCRYPTED_PASSWORD) as pdf:
            self.assertGreaterEqual(len(pdf.pages), 2)


class TestExtractionCore(unittest.TestCase):
    """013-02 — `_open_pdf` / `_extract_page` / `extract_pdf` real logic."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_fixtures()
        cls.digital = FIXTURES_DIR / "digital.pdf"
        cls.encrypted = FIXTURES_DIR / "encrypted.pdf"

    def test_digital_dump_correct(self):
        """TC-E2E-02 — digital PDF yields a correct structured dump."""
        dump = pdf_extract.extract_pdf(
            self.digital, password=None, layout=False)
        self.assertEqual(dump["page_count"], 2)
        self.assertIs(dump["doc_scanned"], False)
        for page in dump["pages"]:
            self.assertTrue(page["text"].strip(), "digital page text non-empty")
            self.assertEqual(page["char_count"], len(page["text"].strip()))
        page1 = dump["pages"][0]
        self.assertGreaterEqual(len(page1["tables"]), 1)
        flat = [str(c) for tbl in page1["tables"] for row in tbl for c in row]
        for token in ("Region", "North", "South"):
            self.assertIn(token, flat)

    def test_extract_page_fields(self):
        """TC-UNIT-07 — a PageRecord has all 9 keys; digital pages imageless."""
        dump = pdf_extract.extract_pdf(
            self.digital, password=None, layout=False)
        for page in dump["pages"]:
            self.assertEqual(
                set(page),
                {"n", "text", "tables", "char_count", "has_images",
                 "image_coverage", "vector_coverage", "scanned",
                 "figure_dominant"})
            self.assertIsInstance(page["n"], int)
            self.assertIs(page["has_images"], False)
        self.assertEqual([p["n"] for p in dump["pages"]], [1, 2])

    # TC-UNIT-27 folded into TC-UNIT-05 — the top-level dump shape has one
    # canonical assertion, not two copies that can drift apart.

    def test_tables_raw_form(self):
        """TC-UNIT-08 — `tables` is a list of row-lists of cells."""
        dump = pdf_extract.extract_pdf(
            self.digital, password=None, layout=False)
        tables = dump["pages"][0]["tables"]
        self.assertIsInstance(tables, list)
        for table in tables:
            for row in table:
                self.assertIsInstance(row, list)

    def test_layout_flag(self):
        """TC-UNIT-09 — `--layout` text is >= non-layout length."""
        plain = pdf_extract.extract_pdf(
            self.digital, password=None, layout=False)
        laid = pdf_extract.extract_pdf(
            self.digital, password=None, layout=True)
        self.assertGreaterEqual(
            len(laid["pages"][0]["text"]), len(plain["pages"][0]["text"]))

    def test_open_encrypted_raises(self):
        """TC-UNIT-10 — encrypted PDF: no password raises EncryptedPDF;
        correct password opens."""
        with self.assertRaises(pdf_extract._ExtractError) as ctx:
            pdf_extract._open_pdf(self.encrypted, None)
        self.assertEqual(ctx.exception.error_type, "EncryptedPDF")
        with pdf_extract._open_pdf(
                self.encrypted, fixtures.ENCRYPTED_PASSWORD) as pdf:
            self.assertGreaterEqual(len(pdf.pages), 2)

    def test_open_corrupt_raises(self):
        """TC-UNIT-11 — a non-PDF file raises `_ExtractError`."""
        with tempfile.NamedTemporaryFile(
                suffix=".pdf", delete=False) as tmp:
            tmp.write(b"this is plainly not a PDF file")
            bad = Path(tmp.name)
        try:
            with self.assertRaises(pdf_extract._ExtractError) as ctx:
                pdf_extract._open_pdf(bad, None)
            self.assertEqual(ctx.exception.error_type, "CorruptPdf")
        finally:
            bad.unlink()

    def test_extract_page_none_text(self):
        """TC-UNIT-26 — a page whose extract_text() yields None → text '' (R6.3)."""
        class _FakePage:
            images: list = []
            lines: list = []
            rects: list = []
            curves: list = []
            width = 612
            height = 792

            def extract_text(self, **kwargs):
                return None

            def extract_tables(self, **kwargs):
                return []

        rec = pdf_extract._extract_page(_FakePage(), layout=False)
        self.assertEqual(rec["text"], "")
        self.assertEqual(rec["char_count"], 0)
        self.assertIs(rec["has_images"], False)
        self.assertEqual(rec["image_coverage"], 0.0)
        self.assertEqual(rec["vector_coverage"], 0.0)
        self.assertIs(rec["figure_dominant"], False)

    def test_file_handle_released(self):
        """TC-UNIT-12 — a mid-extraction exception still closes the handle."""
        opened = {}
        real_open = pdf_extract._open_pdf

        def tracking_open(path, password):
            pdf = real_open(path, password)
            opened["pdf"] = pdf
            return pdf

        def boom(*args, **kwargs):
            raise RuntimeError("boom mid-extraction")

        with mock.patch.object(pdf_extract, "_open_pdf", tracking_open), \
                mock.patch.object(pdf_extract, "_extract_page", boom):
            with self.assertRaises(RuntimeError):
                pdf_extract.extract_pdf(
                    self.digital, password=None, layout=False)
        self.assertTrue(
            opened["pdf"].stream.closed,
            "pdfplumber handle must be closed after a mid-extraction error")


def _page(n: int, char_count: int, has_images: bool) -> dict:
    """Synthetic PageRecord with `scanned` / `figure_dominant` computed exactly
    as `_extract_page` would, for direct `_classify_document` tests."""
    scanned = pdf_extract._classify_page(char_count, has_images)
    return {
        "n": n,
        "text": "x" * char_count,
        "tables": [],
        "char_count": char_count,
        "has_images": has_images,
        "image_coverage": 0.0,
        "vector_coverage": 0.0,
        "scanned": scanned,
        "figure_dominant": pdf_extract._classify_figure_page(
            char_count, 0.0, 0.0, scanned),
    }


class TestScanClassifier(unittest.TestCase):
    """013-03 — `_classify_page` / `_classify_document` (ARCH §4.3 truth table)."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_fixtures()

    def test_scanlike_doc_scanned(self):
        """TC-E2E-03 — scan-like PDF → doc_scanned, every page scanned."""
        dump = pdf_extract.extract_pdf(
            FIXTURES_DIR / "scanlike.pdf", password=None, layout=False)
        self.assertIs(dump["doc_scanned"], True)
        self.assertEqual(dump["scanned_pages"],
                         [p["n"] for p in dump["pages"]])
        for page in dump["pages"]:
            self.assertIs(page["scanned"], True)
            self.assertEqual(page["char_count"], 0)

    def test_classify_page_threshold(self):
        """TC-UNIT-13 — per-page predicate incl. the `<=` boundary."""
        cp = pdf_extract._classify_page
        self.assertIs(cp(0, True), True)
        self.assertIs(cp(10, True), True)    # boundary: <=
        self.assertIs(cp(11, True), False)
        self.assertIs(cp(0, False), False)   # blank, no image

    def test_doc_all_image_only(self):
        """TC-UNIT-14 — every page image-only ≈0 text → doc_scanned."""
        pages = [_page(1, 0, True), _page(2, 3, True)]
        self.assertEqual(pdf_extract._classify_document(pages), (True, [1, 2]))

    def test_doc_single_page_image_only(self):
        """TC-UNIT-15 — single image-only page → (True, [1])."""
        self.assertEqual(
            pdf_extract._classify_document([_page(1, 0, True)]), (True, [1]))

    def test_doc_mixed(self):
        """TC-UNIT-16 — digital + image-only pages → not doc_scanned."""
        pages = [_page(1, 500, False), _page(2, 800, False),
                 _page(3, 0, True), _page(4, 0, True)]
        self.assertEqual(
            pdf_extract._classify_document(pages), (False, [3, 4]))

    def test_doc_every_page_images_but_one_has_text(self):
        """TC-UNIT-17 — all pages have images, ≥1 has text → not doc_scanned
        (the `no_meaningful_text` guard)."""
        pages = [_page(1, 0, True), _page(2, 300, True), _page(3, 0, True)]
        doc_scanned, scanned_pages = pdf_extract._classify_document(pages)
        self.assertIs(doc_scanned, False)
        self.assertEqual(scanned_pages, [1, 3])

    def test_doc_all_blank(self):
        """TC-UNIT-18 — all-blank PDF (no text, no images) → never doc_scanned."""
        pages = [_page(1, 0, False), _page(2, 0, False)]
        self.assertEqual(pdf_extract._classify_document(pages), (False, []))

    def test_doc_empty_pdf(self):
        """TC-UNIT-19 — 0-page PDF → (False, [])."""
        self.assertEqual(pdf_extract._classify_document([]), (False, []))

    def test_doc_one_scan_rest_blank(self):
        """TC-UNIT-20 — one image-only page + blank pages → doc_scanned."""
        pages = [_page(1, 0, True), _page(2, 0, False), _page(3, 0, False)]
        self.assertEqual(pdf_extract._classify_document(pages), (True, [1]))

    def test_scanlike_layout_stable(self):
        """TC-UNIT-25 — scan-like PDF stays doc_scanned under `--layout`
        (ARCH §4.3 / reviewer M-4: classification stable across extraction
        modes — an image-only page has 0 chars regardless of layout)."""
        dump = pdf_extract.extract_pdf(
            FIXTURES_DIR / "scanlike.pdf", password=None, layout=True)
        self.assertIs(dump["doc_scanned"], True)
        for page in dump["pages"]:
            self.assertEqual(page["char_count"], 0)
            self.assertIs(page["scanned"], True)


class TestCliAndEmit(unittest.TestCase):
    """013-04 — `main` (exit-code matrix, --json-errors) + `_emit`."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_fixtures()
        cls.digital = FIXTURES_DIR / "digital.pdf"
        cls.scanlike = FIXTURES_DIR / "scanlike.pdf"
        cls.encrypted = FIXTURES_DIR / "encrypted.pdf"

    # --- E2E (subprocess) -------------------------------------------------

    def test_cli_digital_stdout(self):
        """TC-E2E-04 — digital PDF → exit 0, JSON dump on stdout."""
        r = _run_cli([str(self.digital)])
        self.assertEqual(r.returncode, 0, r.stderr)
        dump = json.loads(r.stdout)
        self.assertIs(dump["doc_scanned"], False)
        self.assertEqual(dump["page_count"], 2)

    def test_cli_digital_file_output(self):
        """TC-E2E-05 — `-o` writes the dump to a file; stdout stays empty."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "dump.json"
            r = _run_cli([str(self.digital), "-o", str(out)])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), "")
            dump = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(dump["page_count"], 2)

    def test_cli_scanned_exit10(self):
        """TC-E2E-06 — scan-like PDF → exit 10, dump still on stdout, stderr
        points at OCR / the Read tool."""
        r = _run_cli([str(self.scanlike)])
        self.assertEqual(r.returncode, 10, r.stderr)
        dump = json.loads(r.stdout)
        self.assertIs(dump["doc_scanned"], True)
        self.assertIn("OCR", r.stderr)
        self.assertIn("Read tool", r.stderr)

    def test_cli_scanned_json_errors(self):
        """TC-E2E-07 — scan-like + --json-errors → exit 10, JSON envelope on
        stderr, dump still on stdout."""
        r = _run_cli([str(self.scanlike), "--json-errors"])
        self.assertEqual(r.returncode, 10, r.stderr)
        env = json.loads(r.stderr.strip())
        self.assertEqual(env["v"], 1)
        self.assertEqual(env["code"], 10)
        self.assertEqual(env["type"], "DocumentScanned")
        self.assertIs(json.loads(r.stdout)["doc_scanned"], True)

    def test_cli_encrypted_success(self):
        """TC-E2E-08 — encrypted PDF + correct password → exit 0, dump."""
        r = _run_cli([str(self.encrypted), "--password", "test-pw"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["page_count"], 2)

    def test_cli_encrypted_fail(self):
        """TC-E2E-09 — encrypted PDF, no password → exit 1, EncryptedPDF."""
        r = _run_cli([str(self.encrypted)])
        self.assertEqual(r.returncode, 1)
        r2 = _run_cli([str(self.encrypted), "--json-errors"])
        self.assertEqual(r2.returncode, 1)
        self.assertEqual(json.loads(r2.stderr.strip())["type"], "EncryptedPDF")

    def test_cli_missing_input(self):
        """TC-E2E-10 — missing input → exit 1, InputNotFound."""
        r = _run_cli(["/no/such/file.pdf", "--json-errors"])
        self.assertEqual(r.returncode, 1)
        self.assertEqual(
            json.loads(r.stderr.strip())["type"], "InputNotFound")

    def test_cli_usage_error(self):
        """TC-E2E-11 — no INPUT + --json-errors → exit 2, UsageError."""
        r = _run_cli(["--json-errors"])
        self.assertEqual(r.returncode, 2)
        self.assertEqual(json.loads(r.stderr.strip())["type"], "UsageError")

    def test_cli_idempotent(self):
        """TC-E2E-12 — two runs to the same `-o` → byte-identical output."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "dump.json"
            _run_cli([str(self.digital), "-o", str(out)])
            first = out.read_bytes()
            _run_cli([str(self.digital), "-o", str(out)])
            self.assertEqual(first, out.read_bytes())

    # --- unit -------------------------------------------------------------

    def test_emit_stdout(self):
        """TC-UNIT-21 — `_emit(dump, None)` writes valid JSON to stdout."""
        dump = {"page_count": 0, "doc_scanned": False,
                "scanned_pages": [], "pages": []}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pdf_extract._emit(dump, None)
        self.assertEqual(json.loads(buf.getvalue()), dump)

    def test_emit_file_overwrite(self):
        """TC-UNIT-22 — `_emit` to a file overwrites idempotently."""
        dump = {"page_count": 1, "doc_scanned": False,
                "scanned_pages": [], "pages": []}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "d.json"
            out.write_text("STALE", encoding="utf-8")
            pdf_extract._emit(dump, out)
            first = out.read_bytes()
            pdf_extract._emit(dump, out)
            self.assertEqual(first, out.read_bytes())
            self.assertEqual(json.loads(out.read_text()), dump)

    def test_main_exit_matrix(self):
        """TC-UNIT-23 — `main` returns 0 / 1 / 10 directly (digital /
        missing-input / whole-doc-scan). The `2`/UsageError path raises
        SystemExit from argparse and is covered by TC-E2E-11."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out), _silence_fd_stderr():
            rc_ok = pdf_extract.main([str(self.digital)])
            rc_fail = pdf_extract.main(["/no/such/file.pdf"])
            rc_scan = pdf_extract.main([str(self.scanlike)])
        self.assertEqual(rc_ok, 0)
        self.assertEqual(rc_fail, 1)
        self.assertEqual(rc_scan, 10)

    def test_emit_json_indent(self):
        """TC-UNIT-24 — emitted JSON is indent=2 + ensure_ascii=False."""
        dump = {"page_count": 1, "doc_scanned": False, "scanned_pages": [],
                "pages": [{"n": 1, "text": "Café — résumé ☕", "tables": [],
                           "char_count": 15, "has_images": False,
                           "scanned": False}]}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pdf_extract._emit(dump, None)
        text = buf.getvalue()
        self.assertIn("\n  ", text)               # indented
        self.assertIn("Café — résumé ☕", text)    # non-ASCII preserved

    def test_cli_self_overwrite_refused(self):
        """TC-E2E-13 — `-o` resolving to the input PDF → exit 6 (cross-7
        SelfOverwriteRefused parity; refuses to truncate the input)."""
        r = _run_cli([str(self.digital), "-o", str(self.digital),
                      "--json-errors"])
        self.assertEqual(r.returncode, 6, r.stderr)
        self.assertEqual(
            json.loads(r.stderr.strip())["type"], "SelfOverwriteRefused")

    def test_cli_corrupt_json_errors_clean(self):
        """TC-E2E-14 — corrupt PDF + --json-errors → stderr is exactly ONE
        JSON line (no stray pdfminer/pypdf chatter leaking past the envelope)."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4 this is not a real pdf body, no xref, no EOF")
            bad = Path(tmp.name)
        try:
            r = _run_cli([str(bad), "--json-errors"])
        finally:
            bad.unlink()
        self.assertEqual(r.returncode, 1)
        lines = [ln for ln in r.stderr.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1,
                         f"stderr must be a single JSON line, got: {r.stderr!r}")
        self.assertEqual(json.loads(lines[0])["type"], "CorruptPdf")

    def test_cli_output_creates_parent_dir(self):
        """TC-E2E-15 — `-o` into a missing directory → parent auto-created
        (parity with pdf_split.py / preview.py), exit 0."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "new" / "sub" / "dump.json"
            r = _run_cli([str(self.digital), "-o", str(out)])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(out.is_file())

    def test_cli_output_unwritable(self):
        """TC-E2E-16 — an unwritable `-o` → exit 1 / OutputWriteFailed
        (a clean envelope, never a raw traceback)."""
        with tempfile.TemporaryDirectory() as td:
            # `-o` pointing at an existing directory → open(dir,"w") raises.
            r = _run_cli([str(self.digital), "-o", td, "--json-errors"])
        self.assertEqual(r.returncode, 1)
        self.assertEqual(
            json.loads(r.stderr.strip())["type"], "OutputWriteFailed")


class TestWordGapSplitting(unittest.TestCase):
    """Word-gap splitting (v1.1) — `x_tolerance_ratio` fixes the LaTeX/academic
    no-space-glyph gluing bug (`ASurveyonBlockchain…`) without regressing
    real-space PDFs. Exercised against the deterministic `glued.pdf` fixture."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_fixtures()
        cls.glued = FIXTURES_DIR / "glued.pdf"
        cls.spaced = " ".join(fixtures.GLUED_WORDS)        # "A Survey on …"
        cls.concat = "".join(fixtures.GLUED_WORDS)         # "ASurveyon…"
        cls.control = fixtures.GLUED_CONTROL_LINE

    def _page1(self, **kw) -> str:
        dump = pdf_extract.extract_pdf(
            self.glued, password=None, layout=False, **kw)
        return dump["pages"][0]["text"]

    def test_default_splits_glued_words(self):
        """TC-WG-01 — the default (ratio on) recovers spaced words, NOT the
        glued concatenation — this is the reported-bug fix."""
        text = self._page1()
        self.assertIn(self.spaced, text)
        self.assertNotIn(self.concat, text)

    def test_disabled_reproduces_glue(self):
        """TC-WG-02 — `--x-tolerance-ratio 0` disables the fix and reproduces
        the legacy glue, locking in that the knob actually controls behaviour
        (and documenting the bug it cures)."""
        text = self._page1(x_tolerance_ratio=0)
        self.assertIn(self.concat, text)
        self.assertNotIn(self.spaced, text)

    def test_negative_ratio_disables(self):
        """TC-WG-03 — a negative ratio normalises to disabled (legacy glue)."""
        self.assertIn(self.concat, self._page1(x_tolerance_ratio=-1.0))

    def test_real_space_line_unaffected(self):
        """TC-WG-04 — the real-space control line extracts identically whether
        the ratio is on or off (a space glyph always splits a word)."""
        self.assertIn(self.control, self._page1())
        self.assertIn(self.control, self._page1(x_tolerance_ratio=0))

    def test_dump_echoes_effective_ratio(self):
        """TC-WG-05 — the dump is self-describing: top-level `x_tolerance_ratio`
        is the *effective* value (the default float when on, `None` when
        disabled or normalised away)."""
        on = pdf_extract.extract_pdf(self.glued, password=None, layout=False)
        self.assertEqual(
            on["x_tolerance_ratio"], pdf_extract._DEFAULT_X_TOLERANCE_RATIO)
        off = pdf_extract.extract_pdf(
            self.glued, password=None, layout=False, x_tolerance_ratio=0)
        self.assertIsNone(off["x_tolerance_ratio"])

    def test_layout_mode_also_splits(self):
        """TC-WG-06 — the fix also applies under `--layout` (column-preserving
        mode shares the same word splitter)."""
        dump = pdf_extract.extract_pdf(
            self.glued, password=None, layout=True)
        # collapse layout whitespace before the phrase check
        flat = " ".join(dump["pages"][0]["text"].split())
        self.assertIn(self.spaced, flat)
        self.assertNotIn(self.concat, flat)

    def test_default_constant_value(self):
        """TC-WG-07 — the documented default ratio is 0.15 (frozen)."""
        self.assertEqual(pdf_extract._DEFAULT_X_TOLERANCE_RATIO, 0.15)

    # --- E2E (subprocess) -------------------------------------------------

    def test_cli_default_splits(self):
        """TC-E2E-17 — the CLI default emits spaced words on stdout."""
        r = _run_cli([str(self.glued)])
        self.assertEqual(r.returncode, 0, r.stderr)
        dump = json.loads(r.stdout)
        self.assertEqual(dump["x_tolerance_ratio"], 0.15)
        self.assertIn(self.spaced, dump["pages"][0]["text"])

    def test_cli_disable_flag_glues(self):
        """TC-E2E-18 — `--x-tolerance-ratio 0` on the CLI reproduces the glue
        and reports a null effective ratio in the dump."""
        r = _run_cli([str(self.glued), "--x-tolerance-ratio", "0"])
        self.assertEqual(r.returncode, 0, r.stderr)
        dump = json.loads(r.stdout)
        self.assertIsNone(dump["x_tolerance_ratio"])
        self.assertIn(self.concat, dump["pages"][0]["text"])


class TestLossyTextLayer(unittest.TestCase):
    """PDF-EXTRACT-UNMAPPED-FONT-TEXT-LOSS (v1.2) — a producer that embeds no
    fonts and writes through a single-byte Latin encoding destroys non-Latin
    text *while writing the file*. The dump used to report exit 0 and thousands
    of plausible characters with no signal at all. Detection is by font
    metadata, never by the shape of the extracted text."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_fixtures()
        cls.unmapped = FIXTURES_DIR / "unmapped.pdf"
        cls.embedded = FIXTURES_DIR / "embedded.pdf"

    # --- the defect itself ------------------------------------------------

    def test_lossy_document_flagged(self):
        """TC-LTL-01 — the reported defect: a non-embedded, Latin-encoded,
        /ToUnicode-less document is flagged `text_layer_lossy`."""
        dump = pdf_extract.extract_pdf(
            self.unmapped, password=None, layout=False)
        self.assertIs(dump["text_layer_lossy"], True)
        self.assertTrue(dump["fonts"], "fonts list must not be empty")
        self.assertFalse(any(f["embedded"] for f in dump["fonts"]))
        self.assertFalse(any(f["has_tounicode"] for f in dump["fonts"]))

    def test_text_shape_alone_would_not_catch_it(self):
        """TC-LTL-02 — why the detector reads metadata, not text: the Latin
        line survives and the Cyrillic line comes back as a placeholder-glyph
        run that reads like a word. No statistic over this text separates it
        from prose."""
        dump = pdf_extract.extract_pdf(
            self.unmapped, password=None, layout=False)
        text = dump["pages"][0]["text"]
        self.assertIn(fixtures.UNMAPPED_LATIN_LINE, text)
        self.assertNotIn(fixtures.UNMAPPED_CYRILLIC_LINE, text)
        self.assertNotIn("Раздел", text)
        # The placeholder run: letters and digits only, no empty-looking gap.
        self.assertRegex(text, r"[A-Za-z]{4,} 1\. [A-Za-z]{4,}")

    def test_embedded_font_document_not_flagged(self):
        """TC-LTL-03 — no-regression control: one embedded font carrying
        /ToUnicode clears the flag for the whole document."""
        dump = pdf_extract.extract_pdf(
            self.embedded, password=None, layout=False)
        self.assertIs(dump["text_layer_lossy"], False)
        self.assertTrue(any(f["embedded"] for f in dump["fonts"]))
        self.assertTrue(any(f["has_tounicode"] for f in dump["fonts"]))

    def test_scanned_document_not_flagged(self):
        """TC-LTL-04 — a document with no extractable text is never
        `text_layer_lossy`: there is no text layer to call lossy, and the scan
        signal already owns that failure."""
        dump = pdf_extract.extract_pdf(
            FIXTURES_DIR / "scanlike.pdf", password=None, layout=False)
        self.assertIs(dump["doc_scanned"], True)
        self.assertIs(dump["text_layer_lossy"], False)

    # --- the `fonts` fact -------------------------------------------------

    def test_font_record_shape(self):
        """TC-LTL-05 — every font record carries exactly the five documented
        fields, with the documented types."""
        dump = pdf_extract.extract_pdf(
            self.unmapped, password=None, layout=False)
        for font in dump["fonts"]:
            self.assertEqual(
                set(font),
                {"name", "subtype", "embedded", "encoding", "has_tounicode"})
            self.assertIsInstance(font["embedded"], bool)
            self.assertIsInstance(font["has_tounicode"], bool)
            for key in ("name", "subtype", "encoding"):
                self.assertIsInstance(font[key], (str, type(None)))

    def test_fonts_deduplicated_and_deterministic(self):
        """TC-LTL-06 — the same font resource is referenced from every page
        that uses it; the dump lists each distinct font once, in a stable
        order, so two runs produce identical JSON."""
        first = pdf_extract.extract_pdf(
            FIXTURES_DIR / "digital.pdf", password=None, layout=False)
        second = pdf_extract.extract_pdf(
            FIXTURES_DIR / "digital.pdf", password=None, layout=False)
        self.assertEqual(first["fonts"], second["fonts"])
        keys = [pdf_extract._font_key(f) for f in first["fonts"]]
        self.assertEqual(len(keys), len(set(keys)), "fonts must be deduped")
        self.assertEqual(keys, sorted(keys), "fonts must be sorted")
        self.assertIn("Helvetica", [f["name"] for f in first["fonts"]])

    # --- classifier truth tables ------------------------------------------

    @staticmethod
    def _font(name="F", subtype="Type1", embedded=False,
              encoding="WinAnsiEncoding", has_tounicode=False) -> dict:
        return {"name": name, "subtype": subtype, "embedded": embedded,
                "encoding": encoding, "has_tounicode": has_tounicode}

    def test_classify_text_layer_truth_table(self):
        """TC-LTL-07 — `_classify_text_layer` fires only on the full
        conjunction; any single escape hatch clears it."""
        ctl = pdf_extract._classify_text_layer
        latin = self._font()
        self.assertIs(ctl([latin], True), True)
        self.assertIs(ctl([latin], False), False)         # no text layer
        self.assertIs(ctl([], True), False)               # nothing measured
        self.assertIs(ctl([latin, self._font(embedded=True)], True), False)
        self.assertIs(ctl([latin, self._font(has_tounicode=True)], True), False)
        self.assertIs(ctl([latin, self._font(subtype="Type0",
                                             encoding="Identity-H")], True),
                      False)
        self.assertIs(
            ctl([latin, self._font(encoding="WinAnsiEncoding+Differences")],
                True),
            False)

    def test_is_latin_single_byte_truth_table(self):
        """TC-LTL-08 — the per-font predicate: composite fonts and remapped
        encodings can carry non-Latin text and must never count."""
        f = pdf_extract._is_latin_single_byte
        self.assertIs(f("Type1", "WinAnsiEncoding"), True)
        self.assertIs(f("TrueType", "MacRomanEncoding"), True)
        self.assertIs(f("Type1", None), True)      # built-in base-14 encoding
        self.assertIs(f("Type0", "Identity-H"), False)
        self.assertIs(f("Type0", None), False)
        self.assertIs(f("Type1", "Differences"), False)
        self.assertIs(f("Type1", "WinAnsiEncoding+Differences"), False)
        self.assertIs(f("Type1", "UniGB-UCS2-H"), False)
        self.assertIs(f(None, "WinAnsiEncoding"), False)

    def test_encoding_label(self):
        """TC-LTL-09 — `_encoding_label` collapses the three /Encoding forms
        into one comparable string, keeping the load-bearing `Differences`
        marker."""
        label = pdf_extract._encoding_label
        self.assertIsNone(label(None))
        self.assertEqual(label({"BaseEncoding": "/WinAnsiEncoding"}),
                         "WinAnsiEncoding")
        self.assertEqual(
            label({"BaseEncoding": "/WinAnsiEncoding",
                   "Differences": [128, "/afii10017"]}),
            "WinAnsiEncoding+Differences")
        self.assertEqual(label({"Differences": [128, "/afii10017"]}),
                         "Differences")
        self.assertEqual(label({}), "dict")

    def test_font_record_type0_descendant_embedding(self):
        """TC-LTL-10 — a composite font keeps its FontDescriptor (and therefore
        its embedded font file) on the *descendant*; `embedded` must follow it
        there, or every CID font would look non-embedded."""
        font = {
            "BaseFont": "/ABCDEF+NotoSans",
            "Subtype": "/Type0",
            "Encoding": "/Identity-H",
            "DescendantFonts": [
                {"Subtype": "/CIDFontType2",
                 "FontDescriptor": {"FontFile2": object()}},
            ],
        }
        record = pdf_extract._font_record(font)
        self.assertIs(record["embedded"], True)
        self.assertEqual(record["subtype"], "Type0")
        self.assertEqual(record["encoding"], "Identity-H")
        self.assertIs(record["has_tounicode"], False)

    def test_font_record_type3_counts_as_embedded(self):
        """TC-LTL-11 — a Type3 font's glyphs ARE content streams in the file,
        so it is embedded even without a FontFile."""
        record = pdf_extract._font_record(
            {"Subtype": "/Type3", "CharProcs": {}, "Name": "/T3"})
        self.assertIs(record["embedded"], True)

    def test_walk_font_resources_recurses_into_xobjects(self):
        """TC-LTL-12 — a font used only inside a Form XObject is still found;
        missing it would silently clear the flag on a document whose real text
        lives in forms."""
        acc: dict = {}
        resources = {
            "Font": {"F1": {"BaseFont": "/Helvetica", "Subtype": "/Type1",
                            "Encoding": "/WinAnsiEncoding"}},
            "XObject": {"Fm0": {
                "Resources": {"Font": {"F2": {
                    "BaseFont": "/ABCDEF+NotoSans", "Subtype": "/Type0",
                    "DescendantFonts": [
                        {"FontDescriptor": {"FontFile2": object()}}],
                }}},
            }},
        }
        pdf_extract._walk_font_resources(resources, acc, set(), 0)
        names = sorted(r["name"] for r in acc.values())
        self.assertEqual(names, ["ABCDEF+NotoSans", "Helvetica"])

    def test_walk_font_resources_depth_capped(self):
        """TC-LTL-13 — a self-nesting resource chain of *direct* objects has no
        object id to remember, so only the depth cap stops it. It must
        terminate rather than blow the stack."""
        resources: dict = {"Font": {"F1": {"BaseFont": "/Helvetica",
                                           "Subtype": "/Type1"}}}
        resources["XObject"] = {"Fm0": {"Resources": resources}}
        acc: dict = {}
        pdf_extract._walk_font_resources(resources, acc, set(), 0)
        self.assertEqual(len(acc), 1)

    def test_collect_page_fonts_never_fatal(self):
        """TC-LTL-14 — font metadata is diagnostic: a page whose resources
        explode must not fail an extraction that would otherwise succeed (the
        documented safe direction — a missing record can only *suppress* the
        alarm)."""
        class _ExplodingPage:
            @property
            def page_obj(self):
                raise RuntimeError("broken resource dictionary")

        acc: dict = {}
        pdf_extract._collect_page_fonts(_ExplodingPage(), acc, set())
        self.assertEqual(acc, {})

    # --- E2E (subprocess) -------------------------------------------------

    def test_cli_warns_without_changing_exit_code(self):
        """TC-E2E-19 — the loud signal: exit stays 0 (exit 10 means "the whole
        document is a scan" and that contract is public), the dump still
        lands on stdout, and stderr names the repair — and rules OCR out."""
        r = _run_cli([str(self.unmapped)])
        self.assertEqual(r.returncode, 0, r.stderr)
        dump = json.loads(r.stdout)
        self.assertIs(dump["text_layer_lossy"], True)
        self.assertIs(dump["doc_scanned"], False)
        self.assertIn("warning:", r.stderr)
        self.assertIn("/ToUnicode", r.stderr)
        self.assertIn("OCR does not help", r.stderr)
        self.assertIn("Re-export", r.stderr)

    def test_cli_silent_on_embedded_fonts(self):
        """TC-E2E-20 — the control emits no lossy warning at all."""
        r = _run_cli([str(self.embedded)])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIs(json.loads(r.stdout)["text_layer_lossy"], False)
        self.assertNotIn("/ToUnicode", r.stderr)


class TestLineTolerance(unittest.TestCase):
    """PDF-EXTRACT-TOLERANCE-ARTIFACTS half A (v1.2) — pdfplumber's *absolute*
    3 pt `y_tolerance` splits a list marker set in a smaller point size onto
    its own line and sorts it AFTER the item it introduces. `--y-tolerance`
    is the Y-axis twin of the already-shipped `--x-tolerance-ratio`; a ratio
    cannot fix it, because it would scale off the marker's own small size."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_fixtures()
        cls.bullets = FIXTURES_DIR / "bullets.pdf"
        cls.marker = fixtures.BULLET_MARKER

    def _lines(self, **kw) -> list[str]:
        dump = pdf_extract.extract_pdf(
            self.bullets, password=None, layout=False, **kw)
        return dump["pages"][0]["text"].splitlines()

    def test_default_reproduces_orphaned_markers(self):
        """TC-YT-01 — the defect, locked in: at pdfplumber's default every
        marker is its own line, placed AFTER its item."""
        lines = self._lines()
        self.assertEqual(lines.count(self.marker), len(fixtures.BULLET_ITEMS))
        for item in fixtures.BULLET_ITEMS:
            self.assertEqual(lines[lines.index(item) + 1], self.marker)

    def test_raised_tolerance_reunites_markers(self):
        """TC-YT-02 — the fix: `y_tolerance=5` puts every marker back in front
        of its own item and leaves no orphan behind."""
        lines = self._lines(y_tolerance=5)
        self.assertNotIn(self.marker, lines)
        for item in fixtures.BULLET_ITEMS:
            self.assertIn(f"{self.marker} {item}", lines)

    def test_trailing_line_not_merged(self):
        """TC-YT-03 — the control: raising the tolerance must not swallow the
        ordinary paragraph line that follows the list."""
        for lines in (self._lines(), self._lines(y_tolerance=5)):
            self.assertIn(fixtures.BULLET_TRAILING_LINE, lines)

    def test_no_regression_on_normal_documents(self):
        """TC-YT-04 — the reason the default is left alone AND the evidence
        that 5 is safe: on documents with uniform type the raised tolerance
        changes neither text nor tables, character for character."""
        for name in ("digital.pdf", "glued.pdf"):
            base = pdf_extract.extract_pdf(
                FIXTURES_DIR / name, password=None, layout=False)
            raised = pdf_extract.extract_pdf(
                FIXTURES_DIR / name, password=None, layout=False,
                y_tolerance=5)
            self.assertEqual([p["text"] for p in base["pages"]],
                             [p["text"] for p in raised["pages"]], name)
            self.assertEqual([p["tables"] for p in base["pages"]],
                             [p["tables"] for p in raised["pages"]], name)

    def test_dump_echoes_effective_tolerance(self):
        """TC-YT-05 — the dump stays self-describing: `None` when pdfplumber's
        own default is in force, the number when it is not, and a
        zero/negative request normalises to `None` rather than being passed
        through as a nonsense tolerance."""
        def echo(**kw):
            return pdf_extract.extract_pdf(
                self.bullets, password=None, layout=False, **kw)["y_tolerance"]

        self.assertIsNone(echo())
        self.assertEqual(echo(y_tolerance=5), 5)
        self.assertIsNone(echo(y_tolerance=0))
        self.assertIsNone(echo(y_tolerance=-3))

    def test_layout_mode_honours_tolerance(self):
        """TC-YT-06 — the knob also applies under `--layout`, which shares the
        same line grouping."""
        dump = pdf_extract.extract_pdf(
            self.bullets, password=None, layout=True, y_tolerance=5)
        flat = " ".join(dump["pages"][0]["text"].split())
        self.assertIn(f"{self.marker} {fixtures.BULLET_ITEMS[0]}", flat)

    def test_cli_y_tolerance(self):
        """TC-E2E-21 — `--y-tolerance 5` end to end."""
        r = _run_cli([str(self.bullets), "--y-tolerance", "5"])
        self.assertEqual(r.returncode, 0, r.stderr)
        dump = json.loads(r.stdout)
        self.assertEqual(dump["y_tolerance"], 5)
        self.assertIn(f"{self.marker} {fixtures.BULLET_ITEMS[0]}",
                      dump["pages"][0]["text"])


class TestTableStrategy(unittest.TestCase):
    """PDF-EXTRACT-TOLERANCE-ARTIFACTS half B (v1.2) — pdfplumber's default
    `lines` strategy builds table edges from every rectangle, background fills
    included, so shading becomes a phantom table and a shaded paragraph can be
    glued onto a real table as an extra row. That is the worse half of the
    defect: invented content entering a *structured* dump silently."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_fixtures()
        cls.shaded = FIXTURES_DIR / "shaded.pdf"

    def _tables(self, page_index: int, **kw) -> list:
        dump = pdf_extract.extract_pdf(
            self.shaded, password=None, layout=False, **kw)
        return dump["pages"][page_index]["tables"]

    def test_default_invents_a_table_from_shading(self):
        """TC-TS-01 — the defect: a page with no table at all comes back with
        one, assembled out of zebra-striped paragraph backgrounds."""
        tables = self._tables(0)
        self.assertGreaterEqual(len(tables), 1)
        cells = [c for t in tables for row in t for c in row if c]
        for row_text in fixtures.SHADED_ZEBRA_ROWS:
            self.assertIn(row_text, cells)

    def test_strict_rejects_the_phantom_table(self):
        """TC-TS-02 — the fix: `lines_strict` counts only stroked lines, so the
        page reports no tables."""
        self.assertEqual(self._tables(0, table_strategy="lines_strict"), [])

    def test_default_glues_shading_onto_a_real_table(self):
        """TC-TS-03 — the worse symptom: a shaded paragraph x-aligned under a
        real table is returned as a fourth row of that table, i.e. text that
        was never in the table is now inside it."""
        tables = self._tables(1)
        self.assertEqual(len(tables), 1)
        self.assertEqual(len(tables[0]), len(fixtures.DIGITAL_TABLE) + 1)
        self.assertEqual(tables[0][-1][0], fixtures.SHADED_NOTE_LINE)

    def test_strict_keeps_the_real_table_and_drops_the_note(self):
        """TC-TS-04 — `lines_strict` returns the real table exactly, with the
        shaded paragraph nowhere in it."""
        tables = self._tables(1, table_strategy="lines_strict")
        self.assertEqual(tables, [fixtures.DIGITAL_TABLE])

    def test_strict_does_not_regress_ruled_tables(self):
        """TC-TS-05 — the no-regression control: a genuinely ruled table is
        byte-identical under both strategies, on both fixtures that have one."""
        for name in ("digital.pdf", "glued.pdf"):
            base = pdf_extract.extract_pdf(
                FIXTURES_DIR / name, password=None, layout=False)
            strict = pdf_extract.extract_pdf(
                FIXTURES_DIR / name, password=None, layout=False,
                table_strategy="lines_strict")
            self.assertEqual([p["tables"] for p in base["pages"]],
                             [p["tables"] for p in strict["pages"]], name)

    def test_dump_echoes_strategy(self):
        """TC-TS-06 — the dump names the strategy that produced its tables;
        the default stays pdfplumber's `lines` (the defect report explicitly
        refuses `lines_strict` as a new default on one document's evidence)."""
        default = pdf_extract.extract_pdf(
            self.shaded, password=None, layout=False)
        self.assertEqual(default["table_strategy"], "lines")
        strict = pdf_extract.extract_pdf(
            self.shaded, password=None, layout=False,
            table_strategy="lines_strict")
        self.assertEqual(strict["table_strategy"], "lines_strict")

    def test_cli_table_strategy(self):
        """TC-E2E-22 — `--table-strategy lines_strict` end to end."""
        r = _run_cli([str(self.shaded), "--table-strategy", "lines_strict"])
        self.assertEqual(r.returncode, 0, r.stderr)
        dump = json.loads(r.stdout)
        self.assertEqual(dump["table_strategy"], "lines_strict")
        self.assertEqual(dump["pages"][0]["tables"], [])

    def test_cli_rejects_unknown_strategy(self):
        """TC-E2E-23 — an unsupported strategy is a usage error (exit 2), not
        a silent fall-through to the default."""
        r = _run_cli([str(self.shaded), "--table-strategy", "text"])
        self.assertEqual(r.returncode, 2)


class TestFigurePages(unittest.TestCase):
    """PDF-EXTRACT-FIGURE-PAGE-UNFLAGGED (v1.2) — a page whose whole content is
    one diagram escapes the `scanned` heuristic as soon as it carries a running
    header, because that heuristic counts characters absolutely. The page then
    arrives as ordinary text and the diagram vanishes without a signal."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_fixtures()
        cls.dump = pdf_extract.extract_pdf(
            FIXTURES_DIR / "figure.pdf", password=None, layout=False)
        cls.pages = cls.dump["pages"]

    def test_figure_pages_listed(self):
        """TC-FIG-01 — exactly the two figure pages are reported, and the
        top-level list agrees with the per-page flags."""
        self.assertEqual(self.dump["figure_pages"],
                         fixtures.FIGURE_DOMINANT_PAGES)
        self.assertEqual(
            self.dump["figure_pages"],
            [p["n"] for p in self.pages if p["figure_dominant"]])

    def test_raster_figure_page_flagged_where_old_heuristic_misses(self):
        """TC-FIG-02 — the reported defect exactly: a running header alone puts
        the page over the 10-char scan threshold, so `scanned` stays False and
        the old signal is silent — `figure_dominant` catches it."""
        page = self.pages[1]
        self.assertGreater(page["char_count"],
                           pdf_extract._SCANNED_CHAR_THRESHOLD)
        self.assertIs(page["scanned"], False)
        self.assertIs(page["figure_dominant"], True)
        self.assertGreaterEqual(page["image_coverage"],
                                pdf_extract._FIGURE_COVERAGE_THRESHOLD)

    def test_vector_figure_page_flagged(self):
        """TC-FIG-03 — the correction the defect record makes to its own first
        draft: this page has ZERO images, so a coverage signal counting only
        `page.images` would miss it. Vector paint has to be counted too."""
        page = self.pages[2]
        self.assertEqual(page["image_coverage"], 0.0)
        self.assertGreaterEqual(page["vector_coverage"],
                                pdf_extract._FIGURE_COVERAGE_THRESHOLD)
        self.assertIs(page["figure_dominant"], True)

    def test_screenshot_beside_prose_not_flagged(self):
        """TC-FIG-04 — false-positive control for the coverage conjunct: an
        illustration accompanying live text stays under the threshold."""
        page = self.pages[3]
        self.assertGreater(page["image_coverage"], 0.0)
        self.assertLess(page["image_coverage"] + page["vector_coverage"],
                        pdf_extract._FIGURE_COVERAGE_THRESHOLD)
        self.assertIs(page["figure_dominant"], False)

    def test_ruled_table_page_saved_only_by_the_char_conjunct(self):
        """TC-FIG-05 — the measured reason the char cap is load-bearing rather
        than cosmetic: table ruling clusters into most of the sheet, clearing
        the coverage threshold on its own. Only the text count keeps a healthy
        document's table pages unflagged."""
        page = self.pages[4]
        self.assertGreaterEqual(page["vector_coverage"],
                                pdf_extract._FIGURE_COVERAGE_THRESHOLD)
        self.assertGreaterEqual(page["char_count"],
                                pdf_extract._FIGURE_CHAR_THRESHOLD)
        self.assertIs(page["figure_dominant"], False)

    def test_prose_page_not_flagged(self):
        """TC-FIG-06 — an ordinary text page has no coverage and no flag."""
        page = self.pages[0]
        self.assertEqual(page["image_coverage"], 0.0)
        self.assertEqual(page["vector_coverage"], 0.0)
        self.assertIs(page["figure_dominant"], False)

    def test_scan_contract_untouched(self):
        """TC-FIG-07 — the public contract is not widened: figure pages feed
        neither `scanned_pages` nor `doc_scanned`."""
        self.assertIs(self.dump["doc_scanned"], False)
        self.assertEqual(self.dump["scanned_pages"], [])

    def test_scanned_page_is_not_also_figure_dominant(self):
        """TC-FIG-08 — the two flags are disjoint: a scan trips the coverage
        test too, but it is already flagged and needs OCR, not image
        extraction."""
        dump = pdf_extract.extract_pdf(
            FIXTURES_DIR / "scanlike.pdf", password=None, layout=False)
        self.assertEqual(dump["figure_pages"], [])
        for page in dump["pages"]:
            self.assertIs(page["scanned"], True)
            self.assertIs(page["figure_dominant"], False)

    def test_coverage_fields_are_fractions(self):
        """TC-FIG-09 — both coverage fields are reported on every page as
        fractions of the sheet."""
        for page in self.pages:
            for key in ("image_coverage", "vector_coverage"):
                self.assertIsInstance(page[key], float)
                self.assertGreaterEqual(page[key], 0.0)
                self.assertLessEqual(page[key], 1.0)

    def test_classify_figure_page_truth_table(self):
        """TC-FIG-10 — the predicate at its boundaries: coverage is `>=` the
        threshold, char count strictly `<` it, the two coverages add, and a
        scanned page is excluded outright."""
        cf = pdf_extract._classify_figure_page
        self.assertIs(cf(0, 0.25, 0.0, False), True)      # boundary: >=
        self.assertIs(cf(0, 0.24, 0.0, False), False)
        self.assertIs(cf(0, 0.13, 0.12, False), True)     # the sum matters
        self.assertIs(cf(199, 0.9, 0.0, False), True)     # boundary: <
        self.assertIs(cf(200, 0.9, 0.0, False), False)
        self.assertIs(cf(0, 1.0, 1.0, True), False)       # scanned wins

    def test_coverage_helpers_edge_cases(self):
        """TC-FIG-11 — the measurement helpers on degenerate input: nothing to
        measure is 0.0, a zero-area page cannot divide, and overlapping boxes
        clamp instead of exceeding the sheet."""
        box = {"x0": 0, "top": 0, "x1": 612, "bottom": 792}
        self.assertEqual(pdf_extract._image_coverage([], 612, 792), 0.0)
        self.assertEqual(pdf_extract._vector_coverage([], 612, 792), 0.0)
        self.assertEqual(pdf_extract._image_coverage([box], 0, 0), 0.0)
        self.assertEqual(pdf_extract._vector_coverage([box], 0, 0), 0.0)
        self.assertEqual(
            pdf_extract._image_coverage([box, box, box], 612, 792), 1.0)
        self.assertEqual(pdf_extract._vector_coverage([box], 612, 792), 1.0)

    def test_vector_coverage_clusters_rather_than_summing_boxes(self):
        """TC-FIG-12 — why the measure clusters: a ruling line's own bounding
        box has ~zero area, yet a grid of them plainly occupies a region of the
        page. Summing boxes would report ~0; clustering reports the region."""
        lines = []
        for i in range(5):                    # a 300x300 pt grid at (100,100)
            offset = 100 + i * 75
            lines.append({"x0": 100, "top": offset, "x1": 400,
                          "bottom": offset})  # horizontal, zero height
            lines.append({"x0": offset, "top": 100, "x1": offset,
                          "bottom": 400})     # vertical, zero width
        summed = sum(abs(o["x1"] - o["x0"]) * abs(o["bottom"] - o["top"])
                     for o in lines)
        self.assertEqual(summed, 0.0)
        coverage = pdf_extract._vector_coverage(lines, 612, 792)
        self.assertAlmostEqual(coverage, (300 * 300) / (612 * 792), delta=0.02)

    def test_cli_warns_without_changing_exit_code(self):
        """TC-E2E-24 — the loud signal: exit stays 0 (exit 10 means the whole
        document is a scan) and stderr names the affected pages and the
        repair."""
        r = _run_cli([str(FIXTURES_DIR / "figure.pdf")])
        self.assertEqual(r.returncode, 0, r.stderr)
        dump = json.loads(r.stdout)
        self.assertEqual(dump["figure_pages"], fixtures.FIGURE_DOMINANT_PAGES)
        self.assertIn("warning:", r.stderr)
        self.assertIn("mostly figure", r.stderr)
        self.assertIn("2, 3", r.stderr)

    def test_cli_silent_on_a_text_document(self):
        """TC-E2E-25 — no figure warning on a document that has none."""
        r = _run_cli([str(FIXTURES_DIR / "digital.pdf")])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("mostly figure", r.stderr)


if __name__ == "__main__":
    unittest.main()

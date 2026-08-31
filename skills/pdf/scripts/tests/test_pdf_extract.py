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
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
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
    "shifted.pdf", "flatfill.pdf", "shadowed.pdf", "nested.pdf",
    "hugedecl.pdf", "onecol.pdf",
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
        self.assertEqual(pdf_extract._VECTOR_BACKDROP_RATIO, 0.9)
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
        """TC-UNIT-05 — the DumpDocument carries exactly its 11 top-level keys,
        so a consumer can rely on the shape and a dropped signal is caught.

        `layout_hints` joined the set when the advisory counters landed; the
        `--extract-images` keys (`images_dir` / `image_dpi` / `images_summary`)
        are deliberately NOT here — they appear only with the flag, and this
        run does not pass it."""
        dump = pdf_extract.extract_pdf(
            FIXTURES_DIR / "digital.pdf", password=None, layout=False)
        self.assertEqual(
            set(dump),
            {"page_count", "doc_scanned", "scanned_pages", "figure_pages",
             "text_layer_lossy", "x_tolerance_ratio", "y_tolerance",
             "table_strategy", "layout_hints", "fonts", "pages"})

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
        self.assertIn("OCR cannot bring it back", r.stderr)
        self.assertIn("Re-export", r.stderr)
        # The warning must not overstate the damage: text inside embedded
        # images survives and is recoverable by rendering the page.
        self.assertIn("inside embedded images", r.stderr)

    def test_cli_silent_on_embedded_fonts(self):
        """TC-E2E-20 — the control emits no lossy warning at all."""
        r = _run_cli([str(self.embedded)])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIs(json.loads(r.stdout)["text_layer_lossy"], False)
        self.assertNotIn("/ToUnicode", r.stderr)

    def test_lossy_warning_scopes_the_damage_to_the_text_layer(self):
        """TC-LTL-15 — dogfooding correction: the warning used to read "OCR does
        not help" flat, which reads as "nothing here is recoverable". The prose
        is gone, but text drawn inside embedded images is untouched — on the
        document that prompted this signal, the diagrams carried most of the
        content. The warning must say so rather than send the caller away."""
        r = _run_cli([str(self.unmapped)])
        self.assertIn("glyphs were never drawn", r.stderr)
        self.assertIn("inside embedded images", r.stderr)
        self.assertIn("render the pages", r.stderr)


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

    def test_page_backdrop_is_not_artwork(self):
        """TC-FIG-13 — the regression this fix exists for: several producers
        paint a page-sized unstroked fill behind every sheet. Counting it read
        a page of plain prose as 100 % artwork (measured: 29 of 29 pages of a
        real Google Docs export), which left the char cap carrying the whole
        signal. The wash must measure as nothing."""
        page = self.pages[5]
        self.assertEqual(page["vector_coverage"], 0.0)
        self.assertGreater(page["char_count"],
                           pdf_extract._FIGURE_CHAR_THRESHOLD)
        self.assertIs(page["figure_dominant"], False)

    def test_backdrop_does_not_hide_a_real_figure(self):
        """TC-FIG-14 — the other direction: dropping the wash must not cost us
        the artwork on top of it. Page 7 is page 3's figure over a backdrop and
        must measure identically."""
        with_backdrop = self.pages[6]
        without = self.pages[2]
        self.assertEqual(with_backdrop["vector_coverage"],
                         without["vector_coverage"])
        self.assertIs(with_backdrop["figure_dominant"], True)
        self.assertIn(7, self.dump["figure_pages"])

    def test_is_backdrop_truth_table(self):
        """TC-FIG-15 — only a page-sized *unstroked fill* is a backdrop. A
        stroked page-sized rect is a frame someone drew, a small fill is a
        highlight, and an unfilled box is an outline — none are washes."""
        area = 612 * 792
        full = {"x0": 0, "top": 0, "x1": 612, "bottom": 792}
        half = {"x0": 0, "top": 0, "x1": 612, "bottom": 396}
        ib = pdf_extract._is_backdrop
        self.assertIs(ib({**full, "stroke": False, "fill": True}, area), True)
        self.assertIs(ib({**full, "stroke": True, "fill": True}, area), False)
        self.assertIs(ib({**full, "stroke": False, "fill": False}, area), False)
        self.assertIs(ib({**half, "stroke": False, "fill": True}, area), False)

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
        self.assertIn(
            ", ".join(str(n) for n in fixtures.FIGURE_DOMINANT_PAGES),
            r.stderr)

    def test_cli_silent_on_a_text_document(self):
        """TC-E2E-25 — no figure warning on a document that has none."""
        r = _run_cli([str(FIXTURES_DIR / "digital.pdf")])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("mostly figure", r.stderr)

class TestImageExtraction(unittest.TestCase):
    """`--extract-images DIR` — the raster and vector branches (pdf-13).

    `figure.pdf` is the ground-truth fixture: page 1 prose (nothing), page 2 a
    raster diagram, page 3 a vector diagram, page 4 the SAME raster as page 2
    beside prose (the sha1-dedup case), page 5 a heavily ruled table (nothing —
    table ruling is stroked, so only the table test rejects it), page 6 prose
    behind a page-sized wash (nothing), page 7 a vector figure ON that wash
    (the wash must not cost us the figure)."""

    @classmethod
    def setUpClass(cls):
        _ensure_fixtures()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "images"
        self.addCleanup(self.tmp.cleanup)

    def _extract(self, name="figure.pdf", **kwargs):
        kwargs.setdefault("images_dir", self.out)
        return pdf_extract.extract_pdf(
            FIXTURES_DIR / name, password=None, layout=False, **kwargs)

    def _images(self, dump, page):
        return dump["pages"][page - 1]["images"]

    # --- the flag is off by default -------------------------------------
    def test_no_flag_leaves_the_dump_shape_untouched(self):
        """Without the flag nothing about the dump changes — no per-page
        `images` key, no top-level image keys, no directory created."""
        dump = pdf_extract.extract_pdf(
            FIXTURES_DIR / "figure.pdf", password=None, layout=False)
        for page in dump["pages"]:
            self.assertNotIn("images", page)
        for key in ("images_dir", "image_dpi", "images_summary"):
            self.assertNotIn(key, dump)
        self.assertFalse(self.out.exists())

    def test_empty_list_means_looked_and_found_nothing(self):
        """With the flag, a page with no artwork carries `images: []` — which
        is a different statement from the key being absent."""
        dump = self._extract()
        self.assertEqual(self._images(dump, 1), [])
        self.assertIn("images", dump["pages"][0])

    # --- raster branch ---------------------------------------------------
    def test_raster_placement_extracted_verbatim(self):
        dump = self._extract()
        records = self._images(dump, 2)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["kind"], "raster")
        path = Path(record["file"])
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_size, record["bytes"])
        self.assertEqual(
            hashlib.sha1(path.read_bytes()).hexdigest(), record["sha1"])

    def test_raster_record_carries_placement_geometry(self):
        """bbox is the *placement* on the page (points); width/height are the
        source image's pixels. They answer different questions and a caller
        needs both."""
        record = self._images(self._extract(), 2)[0]
        x0, top, x1, bottom = record["bbox"]
        self.assertGreater(x1 - x0, 100)
        self.assertGreater(bottom - top, 100)
        self.assertEqual((record["width"], record["height"]), (900, 700))
        self.assertIsNotNone(record["name"])

    def test_identical_images_share_one_file(self):
        """The dedup guard. Pages 2 and 4 place the same PNG: two placements,
        one file. A naive extractor writes it twice — the measured document
        behind this guard placed one raster 31 times."""
        dump = self._extract()
        first = self._images(dump, 2)[0]
        second = self._images(dump, 4)[0]
        self.assertEqual(first["sha1"], second["sha1"])
        self.assertEqual(first["file"], second["file"])
        self.assertEqual(dump["images_summary"]["deduplicated"], 1)
        self.assertLess(dump["images_summary"]["files_written"],
                        dump["images_summary"]["placements"])

    def test_page_sized_raster_is_not_a_figure(self):
        """`scanlike.pdf` is one page-sized raster — a scan, whose repair is
        OCR (exit 10), not a figure file. Nothing is written."""
        dump = self._extract("scanlike.pdf")
        self.assertEqual(self._images(dump, 1), [])
        self.assertEqual(dump["images_summary"]["page_sized_skipped"], 1)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_smask_planes_are_not_emitted_as_images(self):
        """pypdf enumerates a page's image *resources*, which includes /SMask
        alpha planes and images the page never paints. Going through
        pdfplumber's placements is what keeps them out: page 2 paints one
        image, so exactly one file appears for it."""
        dump = self._extract()
        self.assertEqual(len(self._images(dump, 2)), 1)

    def test_one_bad_key_does_not_cost_the_rest_of_the_page(self):
        """Enumeration resolves keys one at a time; a key that cannot be
        resolved must not discard the keys that could."""
        class _Broken:
            def get_object(self):
                raise ValueError("corrupt object")

        class _Node(dict):
            def raw_get(self, key):
                return _Ref(7 if key == "/good" else 9)

        class _Ref:
            def __init__(self, idnum):
                self.idnum = idnum

        class _Images:
            @staticmethod
            def keys():
                return ["/bad", "/good"]

        class _Page(dict):
            images = _Images()

        node = _Node()
        node["/bad"] = _Broken()
        node["/good"] = mock.Mock(**{
            "get_object.return_value": {"/Subtype": "/Image",
                                        "/Width": 40, "/Height": 30}})
        page = _Page()
        page["/Resources"] = {"/XObject": node}

        class _Reader:
            pages = [page]

        streams = pdf_extract._raster_streams(_Reader(), 0)
        self.assertIn(7, streams,
                      "the resolvable key was discarded with the broken one")

    def test_oversized_raster_is_refused_BEFORE_it_is_decoded(self):
        """The allocation is driven by the DECLARED dimensions, so the guard is
        worthless unless it runs first. Asserted by making the decode itself
        fail the test if it is ever reached — the previous version of this test
        used a `property` on a Mock *instance*, which never fires, so its
        negative control could not detect the ordering it advertised."""
        def _boom(*args, **kwargs):
            raise AssertionError("the image was decoded despite the cap")

        with mock.patch.object(pdf_extract, "_fetch_raster", _boom):
            dump = self._extract("hugedecl.pdf")
        self.assertEqual(self._images(dump, 1), [])
        self.assertEqual(dump["images_summary"]["oversized"], 1)
        self.assertEqual(dump["images_summary"]["files_written"], 0)

    def test_declared_size_is_read_where_the_decoder_reads_it(self):
        """`/W`,`/H` shadow `/Width`,`/Height` for pdfminer but not for pypdf.
        Sizing the guard from pdfplumber's `srcsize` therefore reads a number
        the file can set independently of the allocation — and reports it in
        the dump as the image's size."""
        import pdfplumber
        with pdfplumber.open(FIXTURES_DIR / "shadowed.pdf") as pdf:
            srcsize = pdf.pages[0].images[0].get("srcsize")
        self.assertEqual(tuple(srcsize), (1, 1),
                         "fixture no longer carries the shadow keys")
        record = self._images(self._extract("shadowed.pdf"), 1)[0]
        self.assertEqual((record["width"], record["height"]), (400, 300),
                         "the dump reported the shadowed size, not the real one")

    def test_shadowed_declaration_cannot_slip_past_the_cap(self):
        with mock.patch.object(pdf_extract, "_IMAGE_MAX_PIXELS", 1000):
            def _boom(*args, **kwargs):
                raise AssertionError("decoded despite the cap")
            with mock.patch.object(pdf_extract, "_fetch_raster", _boom):
                dump = self._extract("shadowed.pdf")
        self.assertEqual(dump["images_summary"]["oversized"], 1)

    def test_image_nested_in_a_form_xobject_is_still_found(self):
        """Enumeration must walk into Form XObjects. A scan of the page's own
        `/Resources/XObject` sees only the form and loses the image."""
        dump = self._extract("nested.pdf")
        records = self._images(dump, 1)
        self.assertEqual(len(records), 1, "the nested image was lost")
        self.assertEqual(records[0]["kind"], "raster")
        self.assertEqual((records[0]["width"], records[0]["height"]), (300, 200))
        self.assertTrue(Path(records[0]["file"]).is_file())

    def test_a_planted_symlink_is_refused_not_followed(self):
        """Every component of the filename is predictable to whoever supplied
        the PDF, so a symlink planted in the destination would redirect the
        write to its target with attacker-chosen bytes."""
        self.out.mkdir(parents=True, exist_ok=True)
        victim = Path(self.tmp.name) / "victim.txt"
        victim.write_text("ORIGINAL", encoding="utf-8")
        sink = pdf_extract._ImageSink(self.out, dpi=150)
        digest = pdf_extract._sha1(b"payload")
        planted = self.out / f"p001-r01-{digest[:8]}.png"
        planted.symlink_to(victim)
        with self.assertRaises(OSError):
            sink.store(b"payload", page_number=1, kind="raster", suffix=".png")
        self.assertEqual(victim.read_text(encoding="utf-8"), "ORIGINAL",
                         "the write followed the symlink to its target")

    def test_rewriting_identical_bytes_is_accepted(self):
        """The idempotent re-run must stay idempotent under O_EXCL."""
        sink = pdf_extract._ImageSink(self.out, dpi=150)
        self.out.mkdir(parents=True, exist_ok=True)
        first, _ = sink.store(b"same", page_number=1, kind="raster",
                              suffix=".png")
        again = pdf_extract._ImageSink(self.out, dpi=150)
        second, _ = again.store(b"same", page_number=1, kind="raster",
                                suffix=".png")
        self.assertEqual(first, second)
        self.assertEqual(Path(first).read_bytes(), b"same")

    def test_an_image_branch_failure_never_costs_the_dump(self):
        """`extract_pdf` promises the text and tables are the contract. An
        exception from the artwork branch must be contained, counted and
        reported — not propagated into a lost dump."""
        with mock.patch.object(pdf_extract, "_extract_rasters",
                               side_effect=RuntimeError("hostile image")):
            dump = self._extract()
        self.assertEqual(dump["page_count"], 7)
        self.assertTrue(any(p["text"] for p in dump["pages"]),
                        "the text extraction was lost")
        self.assertGreaterEqual(dump["images_summary"]["page_failed"], 1)
        for page in dump["pages"]:
            self.assertEqual(page["images"], [])

    def test_document_file_budget_is_bounded_and_reported(self):
        """A per-page cap bounds one page; a document with many pages bounds
        nothing. The budget stops unbounded output and says what it dropped."""
        with mock.patch.object(pdf_extract, "_MAX_FILES_PER_DOCUMENT", 2):
            dump = self._extract()
        summary = dump["images_summary"]
        self.assertEqual(summary["files_written"], 2)
        self.assertGreaterEqual(summary["over_document_cap"], 1)
        self.assertEqual(len(list(self.out.iterdir())), 2)
        # A spent budget is not a page failure.
        self.assertEqual(summary["page_failed"], 0)

    def test_digest_dedup_covers_two_distinct_objects(self):
        """The objid short-circuit handles the same object placed twice; the
        DIGEST path is what collapses two *different* PDF objects that happen to
        hold identical bytes. `figure.pdf` pages 2 and 4 share one object, so
        nothing there exercises this — hence the explicit case."""
        sink = pdf_extract._ImageSink(self.out, dpi=150)
        self.out.mkdir(parents=True, exist_ok=True)
        first, digest_a = sink.store(b"identical", page_number=1,
                                     kind="raster", suffix=".png", objid=11)
        second, digest_b = sink.store(b"identical", page_number=2,
                                      kind="raster", suffix=".png", objid=22)
        self.assertEqual(digest_a, digest_b)
        self.assertEqual(first, second, "two distinct objects wrote two files")
        self.assertEqual(sink.written, 1)
        self.assertEqual(sink.deduped, 1)
        self.assertEqual(len(list(self.out.iterdir())), 1)

    def test_dedup_short_circuits_on_object_number(self):
        """Hashing every placement re-hashes the same buffer once per
        placement; an object already stored cannot have different bytes."""
        sink = pdf_extract._ImageSink(self.out, dpi=150)
        self.out.mkdir(parents=True, exist_ok=True)
        sink.store(b"payload", page_number=1, kind="raster", suffix=".png",
                   objid=42)
        with mock.patch.object(pdf_extract, "_sha1",
                               side_effect=AssertionError("re-hashed")):
            path, _ = sink.store(b"payload", page_number=2, kind="raster",
                                 suffix=".png", objid=42)
        self.assertIn("p001-r01-", path)
        self.assertEqual(sink.deduped, 1)


    def test_undecodable_image_is_counted_never_faked(self):
        with mock.patch.object(pdf_extract, "_raster_streams",
                               return_value={}):
            dump = self._extract()
        self.assertEqual(self._images(dump, 2), [])
        self.assertGreaterEqual(dump["images_summary"]["undecodable"], 1)

    # --- vector branch ---------------------------------------------------
    def test_vector_figure_is_rendered(self):
        dump = self._extract()
        records = self._images(dump, 3)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["kind"], "vector")
        self.assertIsNone(record["name"])
        self.assertTrue(Path(record["file"]).is_file())

    def test_recorded_pixel_size_matches_the_written_png(self):
        """The record's width/height are computed from the crop rectangle, not
        read back from the file — so assert they agree with the real PNG."""
        record = self._images(self._extract(), 3)[0]
        data = Path(record["file"]).read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        self.assertEqual((width, height), (record["width"], record["height"]))

    def test_table_page_yields_no_figure(self):
        """Page 5's ruling is *stroked*, so the stroke test cannot reject it;
        only the table-overlap test can. Deleting that test resurrects this
        false positive."""
        self.assertEqual(self._images(self._extract(), 5), [])

    def test_prose_behind_a_backdrop_yields_no_figure(self):
        self.assertEqual(self._images(self._extract(), 6), [])

    def test_backdrop_does_not_swallow_a_real_figure(self):
        """Page 7 is page 3's figure drawn on the page-sized wash. Excluding
        the wash must not cost us the figure."""
        records = self._images(self._extract(), 7)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["kind"], "vector")

    def test_the_phantom_table_fixture_yields_no_figure(self):
        """`shaded.pdf` is the worst false-positive trap in the fixture set:
        page 1 is zebra shading the `lines` strategy already misreads as a
        table, page 2 a real ruled table with shading glued under it. Neither
        is artwork, and nothing may be written for either."""
        dump = self._extract("shaded.pdf")
        self.assertEqual(self._images(dump, 1), [])
        self.assertEqual(self._images(dump, 2), [])
        self.assertEqual(dump["images_summary"]["files_written"], 0)

    def test_an_ordinary_ruled_table_yields_no_figure(self):
        dump = self._extract("digital.pdf")
        self.assertEqual([i for p in dump["pages"] for i in p["images"]], [])

    def test_shifted_mediabox_crop_frames_the_figure(self):
        """The crop-geometry regression. On a MediaBox that does not start at
        (0, 0) an uncorrected transform crops the wrong region — and does so
        silently, since the file is still a valid PNG. The figure is drawn well
        inside the sheet, so a correct crop touches neither edge; an
        uncorrected one runs off the top."""
        dump = self._extract("shifted.pdf")
        records = self._images(dump, 1)
        self.assertEqual(len(records), 1)
        x0, top, x1, bottom = records[0]["bbox"]
        self.assertGreater(top, 0.0)
        self.assertGreater(x0, 0.0)
        page_height = 792.0
        self.assertLess(bottom, page_height)
        # The drawn figure is 3 boxes 110 pt wide with 30 pt connectors, so
        # 390 pt across and 80 pt tall, plus 4 pt of padding on each side.
        # Literal numbers on purpose: reading the padding constant back would
        # make the assertion agree with any value the code happens to hold.
        self.assertAlmostEqual(x1 - x0, 398.0, delta=2.0)
        self.assertAlmostEqual(bottom - top, 88.0, delta=2.0)

    def _ink_margins(self, path):
        """(left, top, right, bottom) whitespace, in points, around the drawing
        inside a rendered crop."""
        from PIL import Image, ImageOps
        with Image.open(path) as image:
            grey = image.convert("L")
        ink = ImageOps.invert(grey).getbbox()
        self.assertIsNotNone(ink, "the crop is blank — it framed nothing")
        scale = 72.0 / pdf_extract._DEFAULT_IMAGE_DPI
        width, height = grey.size
        return (ink[0] * scale, ink[1] * scale,
                (width - ink[2]) * scale, (height - ink[3]) * scale)

    def test_crop_is_centred_on_the_figure_in_both_axes(self):
        """The assertion that actually pins the crop geometry. A translation
        error — dropping either MediaBox correction, or swapping them — moves
        the crop off the figure while leaving its WIDTH and HEIGHT correct, so
        a size assertion cannot see it. Measuring the whitespace on all four
        sides can: a correct crop leaves `_FIGURE_PAD_PT` of margin all round
        (less half a stroke width, which bleeds outside the path box).

        Run on the shifted-MediaBox fixture, where every correction is
        non-zero, so no term can silently drop out."""
        record = self._images(self._extract("shifted.pdf"), 1)[0]
        # 4.0 pt hardcoded on purpose: reading `_FIGURE_PAD_PT` back would make
        # the assertion agree with whatever value the code happens to hold, so
        # a changed pad would pass silently.
        for side, margin in zip(("left", "top", "right", "bottom"),
                                self._ink_margins(record["file"])):
            with self.subTest(side):
                self.assertAlmostEqual(
                    margin, 4.0, delta=2.5,
                    msg=f"{side} margin {margin:.1f}pt != ~4.0pt — the crop "
                        f"is translated off the figure")

    def test_vector_bbox_is_in_page_coordinates(self):
        """A vector record's bbox must be in the same frame as a raster's, not
        in pdftocairo's crop frame. They differ by the MediaBox origin, so on
        an ordinary page the two are indistinguishable — only this fixture
        separates them."""
        import pdfplumber
        dump = self._extract("shifted.pdf")
        record = self._images(dump, 1)[0]
        with pdfplumber.open(FIXTURES_DIR / "shifted.pdf") as pdf:
            page = pdf.pages[0]
            origin_x = float(page.mediabox[0])
            cluster = pdf_extract._vector_clusters(
                [*page.lines, *page.rects, *page.curves],
                float(page.width), float(page.height))[0][0]
        self.assertNotEqual(origin_x, 0.0, "fixture no longer shifted")
        # The reported bbox is the cluster's own frame (padded), NOT the frame
        # the crop was taken in — those differ by exactly the MediaBox origin.
        pad = pdf_extract._FIGURE_PAD_PT
        self.assertAlmostEqual(record["bbox"][0], cluster["bbox"][0] - pad,
                               delta=0.01)
        self.assertAlmostEqual(record["bbox"][1], cluster["bbox"][1] - pad,
                               delta=0.01)

    def test_crop_padding_keeps_the_stroke_off_the_edge(self):
        """A path's bounding box is its *centreline* box, so half the stroke
        width sits outside it. Without padding the crop clips the outer half of
        the frame — measured at 1.3-1.6 pt on a 3 pt stroke — and the figure
        comes out with shaved edges. Every border pixel of the crop must be
        background."""
        from PIL import Image
        record = self._images(self._extract(), 3)[0]
        with Image.open(record["file"]) as image:
            pixels = image.convert("L")
        width, height = pixels.size
        data = pixels.load()
        border = (
            [data[x, 0] for x in range(width)]
            + [data[x, height - 1] for x in range(width)]
            + [data[0, y] for y in range(height)]
            + [data[width - 1, y] for y in range(height)]
        )
        self.assertGreater(min(border), 200,
                           "the figure's stroke reaches the crop border — "
                           "the crop is clipping the drawing")

    def test_figure_boxes_are_the_identity_on_an_ordinary_page(self):
        """The MediaBox correction must not perturb the common case."""
        import pdfplumber
        with pdfplumber.open(FIXTURES_DIR / "figure.pdf") as pdf:
            page = pdf.pages[2]
            box = (100.0, 200.0, 300.0, 400.0)
            page_box, render_box = pdf_extract._figure_boxes(page, box)
        pad = pdf_extract._FIGURE_PAD_PT
        expected = (100.0 - pad, 200.0 - pad, 300.0 + pad, 400.0 + pad)
        self.assertEqual(render_box, expected)
        self.assertEqual(page_box, expected)

    # --- the figure predicate, directly ---------------------------------
    def _cluster(self, bbox, *, stroked=1, filled=0):
        members = [{"x0": bbox[0], "top": bbox[1], "x1": bbox[2],
                    "bottom": bbox[3], "stroke": True, "fill": False}
                   for _ in range(stroked)]
        members += [{"x0": bbox[0], "top": bbox[1], "x1": bbox[2],
                     "bottom": bbox[3], "stroke": False, "fill": True}
                    for _ in range(filled)]
        return {"bbox": bbox, "cells": 1, "members": members}

    def test_is_figure_cluster_truth_table(self):
        page = (612.0, 792.0)
        big = (100.0, 100.0, 400.0, 400.0)
        cases = [
            ("stroked, roomy, no table", self._cluster(big), [], True),
            ("fill-only shading", self._cluster(big, stroked=0, filled=3),
             [], False),
            ("mixed, at least one stroke",
             self._cluster(big, stroked=1, filled=5), [], True),
            ("inside a table", self._cluster(big), [big], False),
            ("beside a table", self._cluster(big),
             [(0.0, 500.0, 600.0, 700.0)], True),
            ("too small", self._cluster((10.0, 10.0, 30.0, 30.0)), [], False),
            # 40x40 pt clears the min-side test (24 pt) but covers 0.0033 of
            # the sheet, under the 0.01 floor — the case that isolates the area
            # test from the side test.
            ("wide enough, still a speck",
             self._cluster((10.0, 10.0, 50.0, 50.0)), [], False),
            ("hairline rule", self._cluster((10.0, 10.0, 500.0, 20.0)),
             [], False),
            ("degenerate", {"bbox": None, "cells": 0, "members": []},
             [], False),
        ]
        for label, cluster, tables, expected in cases:
            with self.subTest(label):
                self.assertEqual(
                    pdf_extract._is_figure_cluster(cluster, *page, tables),
                    expected)

    def test_both_rejection_tests_are_load_bearing(self):
        """Neither the stroke test nor the table test subsumes the other: a
        shaded card overlaps no table (only the stroke test rejects it) and
        table ruling is stroked (only the table test rejects it)."""
        page = (612.0, 792.0)
        box = (60.0, 60.0, 550.0, 400.0)
        card = self._cluster(box, stroked=0, filled=8)
        ruling = self._cluster(box, stroked=40)
        self.assertFalse(pdf_extract._is_figure_cluster(card, *page, []))
        self.assertFalse(pdf_extract._is_figure_cluster(ruling, *page, [box]))
        # …and each is admitted by the test that does not target it.
        self.assertFalse(pdf_extract._is_figure_cluster(card, *page, [box]))
        self.assertTrue(pdf_extract._is_figure_cluster(ruling, *page, []))

    def test_overlap_ratio_of_a_degenerate_box_is_zero(self):
        self.assertEqual(
            pdf_extract._overlap_ratio((5.0, 5.0, 5.0, 5.0),
                                       (0.0, 0.0, 10.0, 10.0)), 0.0)

    def test_table_strategy_does_not_change_which_figures_come_out(self):
        """The figure filter always uses pdfplumber's default table detection,
        so `--table-strategy lines_strict` (which reports fewer tables) cannot
        silently admit a table page as a figure."""
        default = self._extract()
        strict_out = Path(self.tmp.name) / "strict"
        strict = pdf_extract.extract_pdf(
            FIXTURES_DIR / "figure.pdf", password=None, layout=False,
            images_dir=strict_out, table_strategy="lines_strict")
        self.assertEqual(
            [[i["kind"] for i in p["images"]] for p in default["pages"]],
            [[i["kind"] for i in p["images"]] for p in strict["pages"]])
        self.assertEqual(strict["pages"][4]["images"], [])

    def test_flat_fill_figure_is_missed_and_the_docs_say_so(self):
        """Pins the honest-scope claim, in the direction that matters: a
        flat-fill chart is extracted by nothing AND flagged by nothing, so the
        documentation must not promise `figure_dominant` as the safety net. If
        a future change rescues it, this test fails and the docs get updated."""
        dump = self._extract("flatfill.pdf")
        page = dump["pages"][0]
        self.assertEqual(page["images"], [])
        self.assertFalse(page["figure_dominant"])
        self.assertEqual(dump["figure_pages"], [])
        self.assertLess(page["vector_coverage"],
                        pdf_extract._FIGURE_COVERAGE_THRESHOLD)
        # …and nothing reports it, which is exactly why it is documented.
        summary = dump["images_summary"]
        self.assertEqual(summary["files_written"], 0)
        self.assertEqual(summary["vector_unrendered"], 0)

    def test_live_coverage_path_is_the_shared_expression(self):
        """`vector_coverage` is a public dump field. When `_extract_page`
        inlined its own copy of the formula, the tests for the helper guarded a
        function the dump no longer called — mutating the live copy survived.
        This asserts the dump's value against the helper on a real document."""
        import pdfplumber
        dump = pdf_extract.extract_pdf(
            FIXTURES_DIR / "figure.pdf", password=None, layout=False)
        with pdfplumber.open(FIXTURES_DIR / "figure.pdf") as pdf:
            for record, page in zip(dump["pages"], pdf.pages):
                expected = round(pdf_extract._vector_coverage(
                    [*page.lines, *page.rects, *page.curves],
                    float(page.width), float(page.height)), 4)
                self.assertEqual(record["vector_coverage"], expected)

    def test_default_image_dpi_value_is_pinned(self):
        self.assertEqual(pdf_extract._DEFAULT_IMAGE_DPI, 150)

    def test_px_rounds_rather_than_truncates(self):
        self.assertEqual(pdf_extract._px(1.4, 72), 1)
        self.assertEqual(pdf_extract._px(1.6, 72), 2)
        self.assertEqual(pdf_extract._px(1.0, 144), 2)

    def test_pixel_cap_boundary_is_exclusive(self):
        """At exactly the cap the image is kept; one pixel over, it is not.

        Driven through `_extract_rasters` rather than asserted arithmetically —
        the previous version compared the constant with itself, which is true
        for every possible value and therefore proved nothing."""
        self.assertEqual(pdf_extract._IMAGE_MAX_PIXELS, 80_000_000)

        class _Stream:
            objid = 1

        def page_with(width, height):
            return mock.Mock(
                width=612.0, height=792.0,
                images=[{"x0": 0, "top": 0, "x1": 100, "bottom": 100,
                         "name": "X1", "stream": _Stream(), "srcsize": None}])

        cap = pdf_extract._IMAGE_MAX_PIXELS
        for label, side, expect_kept in (("exactly at the cap", cap, True),
                                         ("one pixel over", cap + 1, False)):
            with self.subTest(label):
                sink = pdf_extract._ImageSink(self.out, dpi=150)
                self.out.mkdir(parents=True, exist_ok=True)
                with mock.patch.object(pdf_extract, "_fetch_raster",
                                       return_value=(b"x", ".png")):
                    records = pdf_extract._extract_rasters(
                        page_with(side, 1), {1: ("/k", side, 1)}, sink,
                        page_number=1)
                self.assertEqual(bool(records), expect_kept)
                self.assertEqual(sink.oversized, 0 if expect_kept else 1)

    def test_per_page_figure_cap_uses_its_real_value(self):
        """`test_per_page_cap_reports_what_it_dropped` patches the constant to
        0, so it proves the branch exists but is blind to its value. This runs
        the real constant against more clusters than it allows."""
        page = mock.Mock(width=612.0, height=792.0, mediabox=(0, 0, 612, 792))
        page.find_tables.return_value = []
        clusters = [{"bbox": (10.0 + i, 10.0, 210.0 + i, 210.0), "cells": 1,
                     "members": [{"x0": 10.0 + i, "top": 10.0, "x1": 210.0 + i,
                                  "bottom": 210.0, "stroke": True,
                                  "fill": False}]}
                    for i in range(pdf_extract._FIGURE_MAX_PER_PAGE + 5)]
        sink = pdf_extract._ImageSink(self.out, dpi=150)
        self.out.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(pdf_extract, "_fetch_raster", return_value=None):
            with mock.patch.object(pdf_extract.subprocess, "run",
                                   side_effect=subprocess.SubprocessError):
                pdf_extract._extract_vectors(
                    page, clusters, sink, page_number=1,
                    pdf_path=FIXTURES_DIR / "figure.pdf",
                    pdftocairo="/bin/true", password=None)
        self.assertEqual(sink.dropped_capped, 5)
        self.assertEqual(pdf_extract._FIGURE_MAX_PER_PAGE, 20)

    def test_table_boxes_never_raises(self):
        class _Exploding:
            def find_tables(self):
                raise RuntimeError("boom")
        self.assertEqual(pdf_extract._table_boxes(_Exploding()), [])

    # --- clustering refactor --------------------------------------------
    def test_clusters_and_coverage_agree(self):
        """`vector_coverage` is derived from the same clusters the crops come
        from, so the number and the files can never disagree."""
        import pdfplumber
        with pdfplumber.open(FIXTURES_DIR / "figure.pdf") as pdf:
            for page in pdf.pages:
                objects = [*page.lines, *page.rects, *page.curves]
                width, height = float(page.width), float(page.height)
                clusters, cells = pdf_extract._vector_clusters(
                    objects, width, height)
                expected = (min(1.0, sum(c["cells"] for c in clusters) / cells)
                            if cells else 0.0)
                self.assertAlmostEqual(
                    pdf_extract._vector_coverage(objects, width, height),
                    expected, places=9)

    def test_cluster_members_carry_every_object(self):
        """Every path object lands in exactly one cluster — a member lost to
        overpainting would shrink the crop."""
        import pdfplumber
        with pdfplumber.open(FIXTURES_DIR / "figure.pdf") as pdf:
            page = pdf.pages[2]
            objects = [*page.lines, *page.rects, *page.curves]
            clusters, _ = pdf_extract._vector_clusters(
                objects, float(page.width), float(page.height))
        self.assertEqual(sum(len(c["members"]) for c in clusters),
                         len(objects))

    # --- degradation and guards ------------------------------------------
    def test_no_vector_images_keeps_rasters_and_counts_the_rest(self):
        dump = self._extract(vector_images=False)
        self.assertEqual(self._images(dump, 3), [])
        self.assertEqual(len(self._images(dump, 2)), 1)
        self.assertEqual(dump["images_summary"]["vector_unrendered"], 2)

    def test_missing_poppler_degrades_loudly_not_silently(self):
        with mock.patch.object(pdf_extract.shutil, "which", return_value=None):
            dump = self._extract()
        self.assertEqual(self._images(dump, 3), [])
        self.assertEqual(len(self._images(dump, 2)), 1)
        self.assertEqual(dump["images_summary"]["vector_unrendered"], 2)

    def test_pdftocairo_failure_is_counted_not_faked(self):
        with mock.patch.object(pdf_extract.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("x", 1)):
            dump = self._extract()
        self.assertEqual(self._images(dump, 3), [])
        # A failed *render* is a different fact from an undecodable raster —
        # different cause, different repair — so it has its own counter, and
        # the raster branch is untouched by Poppler failing.
        self.assertGreaterEqual(dump["images_summary"]["render_failed"], 2)
        self.assertEqual(dump["images_summary"]["undecodable"], 0)
        self.assertEqual(len(self._images(dump, 2)), 1)

    def test_password_reaches_the_renderer(self):
        """An encrypted PDF's vector figures still render — pdftocairo needs
        the password as `-upw` or it refuses to open the file. Asserted on the
        command line because the committed encrypted fixture holds no vector
        figure to render."""
        seen = []

        def _capture(command, **kwargs):
            seen.append(command)
            raise subprocess.SubprocessError("stop here")

        with mock.patch.object(pdf_extract.subprocess, "run",
                               side_effect=_capture):
            pdf_extract.extract_pdf(
                FIXTURES_DIR / "figure.pdf", password="test-pw", layout=False,
                images_dir=self.out)
        self.assertTrue(seen, "pdftocairo was never invoked")
        for command in seen:
            self.assertIn("-upw", command)
            self.assertEqual(command[command.index("-upw") + 1], "test-pw")

    def test_image_suffix_is_allowlisted(self):
        """The written filename is built only from values this module chose;
        an unrecognised format becomes `.bin`, never a plausible `.png`."""
        cases = [
            ("img1.png", ".png"), ("Im2.JPG", ".jpg"), ("x.jp2", ".jp2"),
            ("weird.exe", ".bin"), ("no-extension", ".bin"),
            ("evil.\\..\\..\\sh", ".bin"), ("", ".bin"),
        ]
        for name, expected in cases:
            with self.subTest(name):
                self.assertEqual(pdf_extract._image_suffix(name), expected)

    def test_written_filenames_stay_inside_the_destination(self):
        dump = self._extract()
        for page in dump["pages"]:
            for image in page["images"]:
                path = Path(image["file"]).resolve()
                self.assertEqual(path.parent, self.out.resolve())

    def test_per_page_cap_reports_what_it_dropped(self):
        with mock.patch.object(pdf_extract, "_FIGURE_MAX_PER_PAGE", 0):
            dump = self._extract()
        self.assertEqual(self._images(dump, 3), [])
        self.assertGreaterEqual(dump["images_summary"]["over_page_cap"], 1)

    def test_rerun_into_the_same_directory_is_idempotent(self):
        first = self._extract()
        names = sorted(p.name for p in self.out.iterdir())
        second = self._extract()
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), names)
        self.assertEqual(
            [i["file"] for p in first["pages"] for i in p["images"]],
            [i["file"] for p in second["pages"] for i in p["images"]])

    def test_filenames_are_deterministic_and_content_addressed(self):
        record = self._images(self._extract(), 3)[0]
        name = Path(record["file"]).name
        self.assertTrue(name.startswith("p003-v01-"))
        self.assertIn(record["sha1"][:8], name)
        self.assertTrue(name.endswith(".png"))

    # --- CLI -------------------------------------------------------------
    def test_cli_writes_images_and_reports_the_directory(self):
        result = _run_cli([str(FIXTURES_DIR / "figure.pdf"),
                           "--extract-images", str(self.out)])
        self.assertEqual(result.returncode, 0)
        dump = json.loads(result.stdout)
        self.assertEqual(dump["images_dir"], str(self.out))
        self.assertEqual(dump["image_dpi"], pdf_extract._DEFAULT_IMAGE_DPI)
        self.assertEqual(dump["images_summary"]["files_written"],
                         len(list(self.out.iterdir())))

    def test_cli_refuses_to_write_images_over_the_input(self):
        target = FIXTURES_DIR / "figure.pdf"
        result = _run_cli([str(target), "--extract-images", str(target),
                           "--json-errors"])
        self.assertEqual(result.returncode, pdf_extract._EXIT_SELF_OVERWRITE)
        self.assertEqual(json.loads(result.stderr)["type"],
                         "SelfOverwriteRefused")

    def test_cli_refuses_an_empty_destination(self):
        """`--extract-images "$OUTDIR"` with OUTDIR unset must not become the
        working directory. `Path("")` normalises to `.`, which passes every
        later check and scatters artwork across the caller's cwd at exit 0 —
        the accident "DIR is mandatory" exists to prevent."""
        workdir = Path(self.tmp.name) / "cwd"
        workdir.mkdir()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(FIXTURES_DIR / "figure.pdf"),
             "--extract-images", "", "--json-errors"],
            cwd=str(workdir), capture_output=True, text=True)
        self.assertEqual(result.returncode, pdf_extract._EXIT_USAGE)
        self.assertEqual(json.loads(result.stderr)["type"], "UsageError")
        self.assertEqual(list(workdir.iterdir()), [],
                         "artwork was scattered into the working directory")

    def test_cli_self_overwrite_envelope_names_the_flag(self):
        """Both refusals are exit 6 with the same `type`; a wrapper should not
        have to parse English to learn which destination to change."""
        target = FIXTURES_DIR / "figure.pdf"
        by_images = _run_cli([str(target), "--extract-images", str(target),
                              "--json-errors"])
        by_output = _run_cli([str(target), "-o", str(target), "--json-errors"])
        for result in (by_images, by_output):
            self.assertEqual(result.returncode,
                             pdf_extract._EXIT_SELF_OVERWRITE)
        self.assertEqual(
            json.loads(by_images.stderr)["details"]["flag"], "--extract-images")
        self.assertEqual(
            json.loads(by_output.stderr)["details"]["flag"], "-o")

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_cli_unwritable_destination_reports_the_directory(self):
        """The one OSError that genuinely belongs to the image directory."""
        parent = Path(self.tmp.name) / "locked"
        parent.mkdir(mode=0o500)
        self.addCleanup(parent.chmod, 0o700)
        result = _run_cli([str(FIXTURES_DIR / "figure.pdf"),
                           "--extract-images", str(parent / "out"),
                           "--json-errors"])
        self.assertEqual(result.returncode, pdf_extract._EXIT_FAIL)
        self.assertEqual(json.loads(result.stderr)["type"],
                         "ImageDirWriteFailed")

    def test_an_unrelated_oserror_is_not_blamed_on_the_image_directory(self):
        """An OSError from the page walk must keep its historical shape rather
        than telling the caller to fix a directory that is fine."""
        with mock.patch.object(pdf_extract, "_extract_page",
                               side_effect=OSError(5, "Input/output error")):
            with _silence_fd_stderr() as sink:
                code = pdf_extract.main([
                    str(FIXTURES_DIR / "figure.pdf"),
                    "--extract-images", str(self.out), "--json-errors"])
                sink.seek(0)
                payload = json.loads(sink.read())
        self.assertEqual(code, pdf_extract._EXIT_FAIL)
        self.assertEqual(payload["type"], "InternalError")

    def test_cli_refuses_a_destination_that_is_a_file(self):
        target = Path(self.tmp.name) / "not-a-dir"
        target.write_text("x", encoding="utf-8")
        result = _run_cli([str(FIXTURES_DIR / "figure.pdf"),
                           "--extract-images", str(target), "--json-errors"])
        self.assertEqual(result.returncode, pdf_extract._EXIT_FAIL)
        self.assertEqual(json.loads(result.stderr)["type"],
                         "ImageDirNotADirectory")

    def test_cli_rejects_a_non_positive_dpi(self):
        result = _run_cli([str(FIXTURES_DIR / "figure.pdf"),
                           "--extract-images", str(self.out),
                           "--image-dpi", "0", "--json-errors"])
        self.assertEqual(result.returncode, pdf_extract._EXIT_USAGE)

    def test_cli_creates_a_missing_destination(self):
        nested = Path(self.tmp.name) / "a" / "b" / "c"
        result = _run_cli([str(FIXTURES_DIR / "figure.pdf"),
                           "--extract-images", str(nested)])
        self.assertEqual(result.returncode, 0)
        self.assertTrue(nested.is_dir())

    def test_cli_dpi_changes_only_the_vector_crop(self):
        low = Path(self.tmp.name) / "low"
        _run_cli([str(FIXTURES_DIR / "figure.pdf"),
                  "--extract-images", str(low), "--image-dpi", "72"])
        result = _run_cli([str(FIXTURES_DIR / "figure.pdf"),
                           "--extract-images", str(self.out),
                           "--image-dpi", "150"])
        dump = json.loads(result.stdout)
        vector = self._images(dump, 3)[0]
        low_dump = json.loads(_run_cli(
            [str(FIXTURES_DIR / "figure.pdf"), "--extract-images", str(low),
             "--image-dpi", "72"]).stdout)
        low_vector = low_dump["pages"][2]["images"][0]
        self.assertGreater(vector["width"], low_vector["width"])
        # The dump echoes the EFFECTIVE dpi, not the default.
        self.assertEqual(low_dump["image_dpi"], 72)
        self.assertEqual(dump["image_dpi"], 150)
        # The raster is copied as stored, so dpi cannot touch it.
        self.assertEqual(dump["pages"][1]["images"][0]["sha1"],
                         low_dump["pages"][1]["images"][0]["sha1"])

    def test_cli_figure_warning_points_at_the_extracted_files(self):
        result = _run_cli([str(FIXTURES_DIR / "figure.pdf"),
                           "--extract-images", str(self.out)])
        self.assertIn("mostly figure", result.stderr)
        self.assertIn(str(self.out), result.stderr)

    def test_figure_warning_does_not_point_at_files_that_were_not_written(self):
        """A flagged page whose figure was not rendered has no file. Telling
        the caller to look in the directory for it sends them after something
        that was never written — the failure mode this whole feature exists to
        remove."""
        result = _run_cli([str(FIXTURES_DIR / "figure.pdf"),
                           "--extract-images", str(self.out),
                           "--no-vector-images"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("NOTHING was extracted for page(s)", result.stderr)
        self.assertIn("3", result.stderr)

    def test_figure_warning_points_at_files_when_they_all_exist(self):
        result = _run_cli([str(FIXTURES_DIR / "figure.pdf"),
                           "--extract-images", str(self.out)])
        self.assertEqual(result.returncode, 0)
        self.assertIn("see the per-page `images` entries", result.stderr)
        self.assertNotIn("NOTHING was extracted", result.stderr)

    def test_cli_scan_contract_is_untouched_by_extraction(self):
        """Exit 10 is public: extracting images must not change it, and a
        whole-page scan raster must not be written out as a figure."""
        result = _run_cli([str(FIXTURES_DIR / "scanlike.pdf"),
                           "--extract-images", str(self.out)])
        self.assertEqual(result.returncode, pdf_extract._EXIT_SCANNED)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_stderr_is_an_envelope_xor_warnings_never_both(self):
        """`--json-errors` promises stderr parses as ONE line of JSON. Every
        warning this feature adds must therefore stay on the exit-0 path: a
        warning printed before an envelope silently breaks `jq` for every
        wrapper that parses it."""
        result = _run_cli([str(FIXTURES_DIR / "scanlike.pdf"),
                           "--extract-images", str(self.out), "--json-errors"])
        self.assertEqual(result.returncode, pdf_extract._EXIT_SCANNED)
        payload = json.loads(result.stderr)   # raises if a warning preceded it
        self.assertEqual(payload["type"], "DocumentScanned")
        self.assertEqual(len(result.stderr.strip().splitlines()), 1)

    def test_cli_encrypted_pdf_extracts_with_the_password(self):
        result = _run_cli([str(FIXTURES_DIR / "encrypted.pdf"),
                           "--password", fixtures.ENCRYPTED_PASSWORD,
                           "--extract-images", str(self.out)])
        self.assertEqual(result.returncode, 0)
        self.assertIn("images", json.loads(result.stdout)["pages"][0])

class TestStdoutChannel(unittest.TestCase):
    """The dump on stdout is a machine-readable channel, so its bytes must not
    depend on the caller's locale and a dead pipe must not contradict the
    envelope. Regression lock for PDF-EXTRACT-STDOUT-LOCALE-ENCODING and
    PDF-EXTRACT-BROKEN-PIPE-EXIT-120."""

    @classmethod
    def setUpClass(cls):
        _ensure_fixtures()

    def _run_under_locale(self, encoding: str):
        """Run the CLI with the C locale and `encoding` as the stdio codec.
        Bytes, not text: the point of these tests is what lands on fd 1."""
        env = dict(os.environ, PYTHONIOENCODING=encoding, PYTHONUTF8="0",
                   LC_ALL="C", LANG="C")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(FIXTURES_DIR / "digital.pdf"),
             "--json-errors"],
            cwd=str(SCRIPTS_DIR), capture_output=True, env=env,
        )

    def test_an_ascii_locale_does_not_truncate_the_dump(self):
        """Was: `json.dump` into the text layer raised UnicodeEncodeError on
        the em dash in page 2 — 1264 bytes of truncated JSON already on
        stdout, exit 1, and a traceback where `--json-errors` promises an
        envelope."""
        proc = self._run_under_locale("ascii")
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        dump = json.loads(proc.stdout.decode("utf-8"))
        self.assertEqual(dump["page_count"], 2)
        self.assertIn("—", dump["pages"][1]["text"])

    def test_a_legacy_locale_does_not_emit_non_utf8_bytes(self):
        """Was: exit 0 with the em dash written as the cp1252 byte 0x97 — a
        dump no UTF-8 reader can decode, and nothing on stderr said so."""
        proc = self._run_under_locale("cp1252")
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        # .decode("utf-8") is the assertion: mojibake raises here.
        text = proc.stdout.decode("utf-8")
        # And the em dash must be its own three UTF-8 bytes, not cp1252's
        # single 0x97. (Asserting 0x97 is *absent* would be wrong — it is a
        # legal UTF-8 continuation byte inside other characters.)
        self.assertIn("—".encode("utf-8"), proc.stdout)
        self.assertIn("—", text)

    def test_the_utf8_bytes_match_the_dump_written_under_a_utf8_locale(self):
        """The locale must change nothing at all — not the encoding, not the
        indentation, not a single byte. (A fix that silently switched to
        `ensure_ascii=True` would pass the two tests above and fail here.)"""
        native = subprocess.run(
            [sys.executable, str(SCRIPT), str(FIXTURES_DIR / "digital.pdf")],
            cwd=str(SCRIPTS_DIR), capture_output=True,
        )
        self.assertEqual(native.returncode, 0)
        self.assertEqual(self._run_under_locale("ascii").stdout, native.stdout)

    def test_a_dead_pipe_exits_with_the_code_the_envelope_declares(self):
        """Was: envelope `"code": 1`, process exit 120 — the interpreter's
        shutdown flush hit the same dead fd, printed `Exception ignored while
        flushing sys.stdout` as a second, non-JSON line on stderr, and
        replaced the exit status. A wrapper then had two contradicting
        sources of truth for one failure."""
        big = self._big_pdf()  # a dump larger than the 64 KiB pipe buffer
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT), str(big), "--json-errors"],
            cwd=str(SCRIPTS_DIR), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc.stdout.read(20)
        proc.stdout.close()          # the `| head` moment
        err = proc.stderr.read().decode("utf-8", "replace")
        proc.stderr.close()
        rc = proc.wait(timeout=120)

        self.assertNotIn("Exception ignored", err)
        lines = [ln for ln in err.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, err)      # nothing but the envelope
        envelope = json.loads(lines[0])
        self.assertEqual(envelope["type"], "OutputWriteFailed")
        self.assertEqual(envelope["details"]["path"], "stdout")
        self.assertEqual(rc, envelope["code"])    # 1, and never 120
        self.assertEqual(rc, pdf_extract._EXIT_FAIL)

    def _big_pdf(self) -> Path:
        """A PDF whose dump exceeds one pipe buffer — otherwise the whole
        dump fits in the kernel's 64 KiB and the write never sees EPIPE, so
        the test would pass against the unfixed code."""
        import pypdf

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        writer = pypdf.PdfWriter()
        reader = pypdf.PdfReader(str(FIXTURES_DIR / "digital.pdf"))
        for _ in range(150):         # 300 pages ≈ a 150 KiB dump, 0.9 s
            for page in reader.pages:
                writer.add_page(page)
        out = Path(tmp.name) / "big.pdf"
        with open(out, "wb") as fh:
            writer.write(fh)
        return out

    def test_a_failing_stdout_is_named_stdout_not_none(self):
        """Was: `Could not write output None: [Errno 28] No space left` with
        `details.path = "None"` — the sink was reported as the string "None"
        because `-o` was absent."""
        with mock.patch.object(pdf_extract, "_emit",
                               side_effect=OSError(28, "No space left")):
            with _silence_fd_stderr() as sink:
                rc = pdf_extract.main(
                    [str(FIXTURES_DIR / "digital.pdf"), "--json-errors"])
                sink.seek(0)
                envelope = json.loads(sink.read().strip().splitlines()[-1])
        self.assertEqual(rc, pdf_extract._EXIT_FAIL)
        self.assertEqual(envelope["details"]["path"], "stdout")
        self.assertIn("stdout", envelope["error"])

    def test_a_dead_o_fifo_is_named_by_the_envelope_not_stdout(self):
        """Two sinks raise `BrokenPipeError` — a dead reader on stdout and a
        `-o` FIFO whose reader hung up — and the arm used to hard-code
        "stdout" for both. Measured before the fix, `-o FIFO` with the reader
        gone reported `"stdout closed before the dump was fully written"` and
        `details.path: "stdout"` at exit 1, for a run whose stdout was never
        written to at all.

        The reader is opened non-blocking *before* the writer starts (a
        blocking `open()` on a readerless FIFO never returns), held until the
        first bytes prove the writer is attached, then closed — after which
        every further write is EPIPE regardless of the buffer.
        """
        big = self._big_pdf()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fifo = Path(tmp.name) / "dump.fifo"
        os.mkfifo(fifo)

        read_fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        proc = None
        try:
            proc = subprocess.Popen(
                [sys.executable, str(SCRIPT), str(big), "-o", str(fifo),
                 "--json-errors"],
                cwd=str(SCRIPTS_DIR), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            deadline = time.monotonic() + 120
            while True:
                try:
                    if os.read(read_fd, 20):
                        break
                except BlockingIOError:
                    pass
                self.assertLess(time.monotonic(), deadline,
                                "the writer never opened the FIFO")
                time.sleep(0.02)
        finally:
            os.close(read_fd)          # the `| head` moment, on a `-o` sink
        out, err = proc.communicate(timeout=180)
        rc = proc.returncode

        text = err.decode("utf-8", "replace")
        self.assertNotIn("Exception ignored", text)
        lines = [ln for ln in text.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, text)
        envelope = json.loads(lines[0])
        self.assertEqual(envelope["type"], "OutputWriteFailed")
        self.assertEqual(envelope["details"]["path"], str(fifo))
        self.assertIn(str(fifo), envelope["error"])
        # The sink that did NOT break must not be blamed for it.
        self.assertNotIn("stdout", envelope["error"])
        self.assertEqual(b"", out)
        self.assertEqual(rc, envelope["code"])
        self.assertEqual(rc, pdf_extract._EXIT_FAIL)

    def test_a_lone_surrogate_is_escaped_rather_than_crashing_the_dump(self):
        """UTF-8 cannot carry U+D800-DFFF, and a broken `/ToUnicode` CMap can
        hand us exactly that. JSON can carry it as the `\\udXXX` escape, so
        the dump must stay parseable instead of aborting mid-stream."""
        class _FakeStdout:
            """A real object, not a Mock: `getattr(..., "buffer", None)` on a
            Mock auto-creates a child mock and the byte path would silently
            not be exercised."""

            def __init__(self):
                self.buffer = io.BytesIO()

            def flush(self):
                pass

        fake = _FakeStdout()
        with mock.patch.object(pdf_extract.sys, "stdout", fake):
            pdf_extract._emit({"text": "a\ud800b"}, None)
        raw = fake.buffer.getvalue()
        parsed = json.loads(raw.decode("utf-8"))   # raises on WTF-8 bytes
        self.assertEqual(parsed["text"], "a\ud800b")

    def test_a_stdout_without_a_buffer_still_gets_the_dump(self):
        """`redirect_stdout(StringIO())` — every in-process test in this file,
        and some wrappers — has no `.buffer`. The text path must stay."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pdf_extract._emit({"text": "— ok"}, None)
        self.assertEqual(json.loads(buf.getvalue())["text"], "— ok")

    def test_the_stdout_writer_is_the_shared_helper_not_a_local_copy(self):
        """The encoder, the surrogate escape and the dead-pipe redirect used
        to live here as `_utf8_chunk` / `_abandon_stdout`. They are
        `_errors.py`'s job — it is byte-identical across five skills, and the
        whole point of PDF-CLI-STDOUT-JSON-LOCALE-CLASS is that this defect
        gets ONE home rather than a private copy per script."""
        import _errors

        self.assertIs(pdf_extract.write_json_stdout, _errors.write_json_stdout)
        for gone in ("_utf8_chunk", "_abandon_stdout"):
            self.assertFalse(hasattr(pdf_extract, gone),
                             f"{gone} is back — see the issue record's Do-not")

    def test_an_unserialisable_dump_leaves_nothing_on_stdout(self):
        """The local writer streamed `iterencode` chunks straight to fd 1, so
        a payload that failed to serialise part-way through left a truncated
        document on the wire under a traceback. The shared helper serialises
        one-shot: the exception arrives with stdout still untouched. (This is
        a defensive property — `extract_pdf` only builds JSON-native types —
        which is why it is asserted rather than assumed.)"""
        class _ByteStdout:
            """A real object: `getattr(mock, "buffer", None)` on a Mock
            auto-creates a child and the byte path would not be exercised."""

            def __init__(self):
                self.buffer = io.BytesIO()

            def flush(self):
                pass

        fake = _ByteStdout()
        with mock.patch.object(pdf_extract.sys, "stdout", fake):
            with self.assertRaises(TypeError):
                pdf_extract._emit({"pages": [{"text": "ok"}],
                                   "bad": object()}, None)
        self.assertEqual(fake.buffer.getvalue(), b"")


class TestLayoutHints(unittest.TestCase):
    """The two pdfplumber defaults that misread real documents are documented
    in the reference — and dogfooding showed a caller only finds out by reading
    it. These hints say the same thing at the moment it matters, without
    touching the exit code."""

    @classmethod
    def setUpClass(cls):
        _ensure_fixtures()

    def _run(self, fixture, *flags):
        proc = _run_cli([str(FIXTURES_DIR / fixture), *flags])
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        return json.loads(proc.stdout), proc.stderr

    def test_layout_hints_are_always_in_the_dump(self):
        """Like `figure_pages` / `scanned_pages`: a wrapper can branch on the
        numbers even when the stderr line was suppressed."""
        dump, _ = self._run("digital.pdf")
        self.assertEqual(
            sorted(dump["layout_hints"]),
            ["orphan_list_markers", "single_column_tables", "tables"])

    def test_a_document_with_neither_problem_gets_no_hint(self):
        """The negative control: hints that fire on clean documents get
        ignored, and then they are worse than none."""
        dump, stderr = self._run("digital.pdf")
        self.assertEqual(dump["layout_hints"]["orphan_list_markers"], 0)
        self.assertEqual(dump["layout_hints"]["single_column_tables"], 0)
        self.assertNotIn("hint:", stderr)

    def test_orphaned_list_markers_are_counted_and_named(self):
        """`bullets.pdf` is the fixture for §3.1: its markers are a smaller
        point size, so pdfplumber's absolute 3 pt grouping puts each on its own
        line AFTER its item."""
        dump, stderr = self._run("bullets.pdf")
        self.assertEqual(dump["layout_hints"]["orphan_list_markers"], 3)
        self.assertIn("hint:", stderr)
        self.assertIn("--y-tolerance 5", stderr)

    def test_the_marker_hint_is_silent_once_the_knob_is_turned(self):
        """Repeating advice the caller has already taken is noise.

        `3.5` is deliberate, and the first version of this test was wrong for
        using `5`: at `5` the markers are reunited, the count falls to 0 and the
        hint would be silent even with the gate deleted — a mutation proved it
        (the test passed against the mutant). At `3.5` the tolerance is raised
        but too little to fix anything, so the count stays at 3 and the gate is
        the only thing that can silence the line."""
        dump, stderr = self._run("bullets.pdf", "--y-tolerance", "3.5")
        self.assertEqual(dump["layout_hints"]["orphan_list_markers"], 3)
        self.assertNotIn("hint:", stderr)

    def test_the_marker_count_drops_to_zero_at_the_advised_value(self):
        """The other half: the advice the hint gives has to actually work."""
        dump, stderr = self._run("bullets.pdf", "--y-tolerance", "5")
        self.assertEqual(dump["layout_hints"]["orphan_list_markers"], 0)
        self.assertNotIn("hint:", stderr)

    def test_shading_phantom_tables_are_counted_and_named(self):
        """`shaded.pdf` is the fixture for §3.2: a filled background rectangle
        is read as a table edge, so the paragraph comes back as a one-column
        table."""
        dump, stderr = self._run("shaded.pdf")
        hints = dump["layout_hints"]
        self.assertGreaterEqual(hints["single_column_tables"], 1)
        self.assertGreater(hints["tables"], 0)
        self.assertIn("--table-strategy lines_strict", stderr)

    def test_the_table_hint_is_silent_under_lines_strict(self):
        """`onecol.pdf`, not `shaded.pdf`: under `lines_strict` the shaded
        fixture's count falls to 0, so that version of this test passed against
        a mutant with the strategy gate deleted. The one-column fixture is
        genuinely ruled, so strict KEEPS it — the count stays 1 and only the
        gate can silence the hint."""
        dump, stderr = self._run("onecol.pdf", "--table-strategy",
                                 "lines_strict")
        self.assertEqual(dump["layout_hints"]["single_column_tables"], 1)
        self.assertNotIn("hint:", stderr)

    def test_the_table_hint_also_fires_on_a_real_one_column_table(self):
        """The hint's honest failure mode, pinned so nobody 'fixes' it blind.

        Shading read as a table and a real one-column table are the same shape
        by the time extraction is done. The hint says "compare the two runs"
        rather than "this is shading" precisely because of this case: here the
        comparison shows the table surviving `lines_strict`, which is the
        answer."""
        dump, stderr = self._run("onecol.pdf")
        self.assertEqual(dump["layout_hints"]["single_column_tables"], 1)
        self.assertIn("--table-strategy lines_strict", stderr)

    def test_a_hint_never_moves_the_exit_code(self):
        """Advisory means advisory: exit 0 stays exit 0, and exit 10 keeps
        meaning `DocumentScanned` and nothing else."""
        proc = _run_cli([str(FIXTURES_DIR / "bullets.pdf")])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("hint:", proc.stderr)

    def test_the_marker_count_ignores_markers_that_are_not_alone(self):
        """A marker glued to its item is the CORRECT layout — counting it
        would fire the hint on every well-formed bulleted document."""
        pages = [{"text": "• First item\n•\n• Third item\n*\nplain line"}]
        self.assertEqual(pdf_extract._orphan_list_markers(pages), 2)

    def test_the_marker_count_ignores_ordinary_one_character_lines(self):
        """`1`, `A`, `#` are not list markers; only the bullet glyphs are."""
        pages = [{"text": "1\nA\n#\nx"}]
        self.assertEqual(pdf_extract._orphan_list_markers(pages), 0)

    def test_the_table_count_ignores_real_multi_column_tables(self):
        """The signal is EVERY row being one cell, not any of them.

        The ragged table here is the case that matters and the one the first
        version of this test missed: extraction routinely returns a table whose
        last row has a single cell (a totals line, a merged footer). Counting
        `any` such row instead of `all` would flag it as shading — a mutation
        proved the earlier data could not tell the two apart."""
        ragged = [["a", "b"], ["c", "d"], ["total"]]
        pages = [{"tables": [[["a"], ["b"]], ragged,
                             [["a", "b"], ["c", "d"]], []]}]
        self.assertEqual(pdf_extract._single_column_tables(pages), 1)

    def test_the_table_hint_fires_on_count_or_on_ratio(self):
        """The threshold pair, tested as numbers because no fixture covers the
        count-without-ratio corner: 23 of 61 (ratio 0.38) is the measured shape
        of the Google Docs export, and it has to fire."""
        fire = lambda single, total: pdf_extract._hint_phantom_tables(
            {"single_column_tables": single, "tables": total}, "lines")
        self.assertTrue(fire(23, 61))    # count wins, ratio 0.38
        self.assertTrue(fire(1, 2))      # ratio wins, count 1 (shaded.pdf)
        self.assertFalse(fire(1, 3))     # neither: 1 table, ratio 0.33
        self.assertFalse(fire(0, 9))     # nothing to say
        self.assertFalse(fire(0, 0))     # no tables at all — no division
        self.assertFalse(pdf_extract._hint_phantom_tables(
            {"single_column_tables": 23, "tables": 61}, "lines_strict"))

    def test_the_marker_hint_needs_more_than_one_stray_glyph(self):
        """A lone `*` on its own line happens in real prose; a broken list
        repeats. The gate on `y_tolerance` is tested here as a number too."""
        fire = pdf_extract._hint_orphan_markers
        self.assertTrue(fire({"orphan_list_markers": 2}, None))
        self.assertFalse(fire({"orphan_list_markers": 1}, None))
        self.assertFalse(fire({"orphan_list_markers": 32}, 5))



if __name__ == "__main__":
    unittest.main()

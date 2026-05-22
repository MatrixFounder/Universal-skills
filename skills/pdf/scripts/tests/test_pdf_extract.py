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


def _ensure_fixtures() -> None:
    """Build the 3 fixtures if any is missing (they are normally committed)."""
    needed = ["digital.pdf", "scanlike.pdf", "encrypted.pdf"]
    if not all((FIXTURES_DIR / n).is_file() for n in needed):
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

    # TC-UNIT-03 (test_main_returns_sentinel) retired by 013-04 per
    # tdd-stub-first §2.4 — `main` now returns real exit codes; covered by
    # TestCliAndEmit (TC-UNIT-23 + TC-E2E-04..12).
    # TC-UNIT-04 (test_classify_stubs) retired by 013-03 per tdd-stub-first
    # §2.4 — the classifier is no longer stubbed; real behaviour is covered by
    # TestScanClassifier (TC-UNIT-13..20).

    def test_extract_pdf_sentinel(self):
        """TC-UNIT-05 — stub `extract_pdf` returns the dump-shaped sentinel."""
        dump = pdf_extract.extract_pdf(
            FIXTURES_DIR / "digital.pdf", password=None, layout=False)
        self.assertEqual(
            set(dump), {"page_count", "doc_scanned", "scanned_pages", "pages"})

    def test_fixtures_exist_and_valid(self):
        """TC-UNIT-06 — the 3 committed fixtures are present and well-formed."""
        import pdfplumber  # type: ignore

        for name in ("digital.pdf", "scanlike.pdf", "encrypted.pdf"):
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
        """TC-UNIT-07 — a PageRecord has all 6 keys; digital pages imageless."""
        dump = pdf_extract.extract_pdf(
            self.digital, password=None, layout=False)
        for page in dump["pages"]:
            self.assertEqual(
                set(page),
                {"n", "text", "tables", "char_count", "has_images", "scanned"})
            self.assertIsInstance(page["n"], int)
            self.assertIs(page["has_images"], False)
        self.assertEqual([p["n"] for p in dump["pages"]], [1, 2])

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

            def extract_text(self, **kwargs):
                return None

            def extract_tables(self):
                return []

        rec = pdf_extract._extract_page(_FakePage(), layout=False)
        self.assertEqual(rec["text"], "")
        self.assertEqual(rec["char_count"], 0)
        self.assertIs(rec["has_images"], False)

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
    """Synthetic PageRecord with `scanned` computed exactly as `_extract_page`
    would, for direct `_classify_document` tests."""
    return {
        "n": n,
        "text": "x" * char_count,
        "tables": [],
        "char_count": char_count,
        "has_images": has_images,
        "scanned": pdf_extract._classify_page(char_count, has_images),
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


if __name__ == "__main__":
    unittest.main()

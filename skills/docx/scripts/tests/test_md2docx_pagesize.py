"""Regression tests for md2docx.js page geometry (TASK 019-03, RTM B1-B5/F1a/F1d).

Shells out to `node md2docx.js` and inspects `word/document.xml` via stdlib zipfile.
Self-contained fixture (a heading + a 3-column table) so the load-bearing
`contentWidthDxa`/table-overflow assertions don't depend on examples/fixture-simple.md.

Run::  cd skills/docx && ./.venv/bin/python -m unittest tests.test_md2docx_pagesize -v

Manual dogfood (committed fixture, NOT tmp7-dependent — renders 3 Mermaid diagrams +
wide tables, so it is kept out of the fast CI path):

    node scripts/md2docx.js examples/fixture-mermaid-a4.md /tmp/df.docx --page-size A4
    python3 scripts/office/validate.py /tmp/df.docx            # OK
    python3 scripts/preview.py /tmp/df.docx /tmp/df.png --cols 2   # tables within A4 margins

Expect <w:pgSz w:w="11906" w:h="16838"> and every <w:tblW> == 9026 (no overflow).
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tests/ -> scripts/
MD2DOCX = os.path.join(SCRIPTS, "md2docx.js")
VALIDATE = os.path.join(SCRIPTS, "office", "validate.py")

_FIXTURE_MD = """# Geometry Fixture

A paragraph of body text to give the document some content.

| Port | Protocol | Description |
|------|----------|-------------|
| 8080 | HTTP     | application traffic |
| 8443 | HTTPS    | TLS-terminated traffic |
| 5432 | TCP      | database connections |
"""


def _have_node():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


@unittest.skipUnless(_have_node(), "node not on PATH")
class Md2DocxPageGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="md2docx_pgsz_")
        cls._md = os.path.join(cls._tmp, "fixture.md")
        with open(cls._md, "w", encoding="utf-8") as fh:
            fh.write(_FIXTURE_MD)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._tmp, ignore_errors=True)

    # --- helpers ---------------------------------------------------------
    def _run(self, *flags):
        """Run md2docx.js with `flags`; return (returncode, out_path, stderr)."""
        out = os.path.join(self._tmp, "out.docx")
        if os.path.exists(out):
            os.remove(out)
        proc = subprocess.run(
            ["node", MD2DOCX, self._md, out, *flags],
            capture_output=True, text=True)
        return proc.returncode, out, proc.stderr

    def _docxml(self, path):
        return zipfile.ZipFile(path).read("word/document.xml").decode()

    def _pgsz(self, xml):
        m = re.search(r'<w:pgSz\b[^>]*>', xml)
        self.assertIsNotNone(m, "no <w:pgSz> in document")
        s = m.group(0)
        w = int(re.search(r'w:w="(\d+)"', s).group(1))
        h = int(re.search(r'w:h="(\d+)"', s).group(1))
        om = re.search(r'w:orient="(\w+)"', s)
        return w, h, (om.group(1) if om else None)

    def _table_width(self, xml):
        m = re.search(r'<w:tblW\b[^>]*w:w="(\d+)"', xml)
        return int(m.group(1)) if m else None

    def _grid_cols(self, xml):
        return [int(x) for x in re.findall(r'<w:gridCol\s+w:w="(\d+)"', xml)]

    def _pgmar(self, xml):
        m = re.search(r'<w:pgMar\b[^>]*>', xml)
        s = m.group(0)
        return {k: int(re.search(r'w:%s="(\d+)"' % k, s).group(1))
                for k in ("top", "right", "bottom", "left")}

    # --- tests -----------------------------------------------------------
    def test_a4_pgsz(self):  # B1 / F1a
        rc, out, err = self._run("--page-size", "A4")
        self.assertEqual(rc, 0, err)
        self.assertEqual(self._pgsz(self._docxml(out))[:2], (11906, 16838))

    def test_letter_default_pgsz_exact(self):  # B5c / F1d
        rc, out, err = self._run()
        self.assertEqual(rc, 0, err)
        self.assertEqual(self._pgsz(self._docxml(out))[:2], (12240, 15840))

    def test_letter_content_width_unchanged(self):  # F1d / I-3 (load-bearing regression)
        rc, out, err = self._run()
        self.assertEqual(rc, 0, err)
        self.assertEqual(self._table_width(self._docxml(out)), 9360,
                         "no-flag table width MUST stay Letter's 9360 (backward-compat)")

    def test_a4_table_no_overflow(self):  # B5b
        rc, out, err = self._run("--page-size", "A4")
        self.assertEqual(rc, 0, err)
        xml = self._docxml(out)
        self.assertEqual(self._table_width(xml), 9026, "A4 content width = 11906-2*1440")
        cols = self._grid_cols(xml)
        self.assertTrue(cols, "expected gridCol widths")
        self.assertLessEqual(sum(cols), 9026, "columns must fit A4 content width (no overflow)")

    def test_landscape(self):  # B2
        rc, out, err = self._run("--page-size", "A4", "--landscape")
        self.assertEqual(rc, 0, err)
        self.assertEqual(self._pgsz(self._docxml(out)), (16838, 11906, "landscape"))

    def test_margins_dxa(self):  # B3
        rc, out, err = self._run("--page-size", "A4", "--margins", "1134,1134,1134,1134")
        self.assertEqual(rc, 0, err)
        xml = self._docxml(out)
        self.assertEqual(self._pgmar(xml), {"top": 1134, "right": 1134, "bottom": 1134, "left": 1134})
        self.assertEqual(self._table_width(xml), 11906 - 2 * 1134)  # 9638

    def test_margins_mm(self):  # B3 (mm suffix)
        rc, out, err = self._run("--page-size", "A4", "--margins", "20mm,20mm,20mm,20mm")
        self.assertEqual(rc, 0, err)
        # 20 mm * 56.7 = 1134
        self.assertEqual(self._pgmar(self._docxml(out))["left"], 1134)

    def test_unknown_flag_rejected(self):  # B1c / MINOR#7
        rc, _out, _err = self._run("--page-sizes", "A4")  # typo
        self.assertNotEqual(rc, 0)

    def test_bad_pagesize_rejected(self):
        rc, _out, _err = self._run("--page-size", "A3")
        self.assertNotEqual(rc, 0)

    def test_bad_margins_rejected(self):
        rc, _out, _err = self._run("--margins", "1,2,3")  # only 3 values
        self.assertNotEqual(rc, 0)

    def test_missing_flag_value(self):  # vdd-multi MEDIUM: precise "missing value" diagnostic
        rc, _out, err = self._run("--page-size")  # flag with no following value
        self.assertNotEqual(rc, 0)
        self.assertIn("Missing value", err)
        self.assertNotIn("Unknown option", err)

    def test_oversized_margins_rejected(self):  # vdd-multi MEDIUM/LOW: margins > page width
        rc, _out, err = self._run("--page-size", "A4", "--margins", "9000,9000,9000,9000")
        self.assertNotEqual(rc, 0)
        self.assertIn("no content area", err)

    def test_a4_validates(self):  # B5a
        rc, out, err = self._run("--page-size", "A4")
        self.assertEqual(rc, 0, err)
        proc = subprocess.run([sys.executable, VALIDATE, out], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()

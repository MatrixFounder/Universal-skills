"""Regression tests for math ($…$ / $$…$$) support in md2docx.js (TASK 031, RTM R1-R9).

Two levels: unit-level calls into _math_lib.js directly (via a small `node -e` subprocess
that prints JSON), and E2E-level calls through `node md2docx.js` on examples/fixture-math.md,
inspecting word/document.xml via stdlib zipfile — same house pattern as
test_md2docx_pagesize.py / test_obsidian2md.py.

Run::  cd skills/docx && ./.venv/bin/python -m unittest tests.test_md2docx_math -v
"""

import json
import os
import re
import subprocess
import tempfile
import unittest
import zipfile

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tests/ -> scripts/
SKILL_ROOT = os.path.dirname(SCRIPTS)
MD2DOCX = os.path.join(SCRIPTS, "md2docx.js")
MATH_LIB = os.path.join(SCRIPTS, "_math_lib.js")
VALIDATE = os.path.join(SCRIPTS, "office", "validate.py")
FIXTURE = os.path.join(SKILL_ROOT, "examples", "fixture-math.md")

SENTINEL_OPEN = ""
SENTINEL_CLOSE = ""


def _have_node():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def _call_math_lib(js_body):
    """Run `js_body` with `lib` bound to require('./_math_lib.js'), cwd=scripts/. The body
    must assign its result to a variable named `result` and this returns json.loads(result)."""
    script = (
        f"const lib = require({json.dumps(MATH_LIB)});\n"
        + js_body
        + "\nprocess.stdout.write(JSON.stringify(result));"
    )
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, cwd=SCRIPTS)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout)


@unittest.skipUnless(_have_node(), "node not on PATH")
class MathLibExtraction(unittest.TestCase):
    """R1, R2 — extraction, sentinel substitution, dedup, DoS guard."""

    def _pp(self, text, opts="undefined"):
        return _call_math_lib(
            f"const r = lib.preprocessMath({json.dumps(text)}, {opts}); "
            "result = {text: r.text, count: r.formulas.length, "
            "formulas: r.formulas.map(f => ({tex: f.tex, display: f.display, "
            "hasOmml: !!f.omml, hasError: !!f.error}))};"
        )

    def test_inline_and_display_both_found(self):  # R1(a)(e)
        r = self._pp("inline $x^2$ then display\n\n$$y = mx$$\n")
        self.assertEqual(r["count"], 2)
        displays = [f["display"] for f in r["formulas"]]
        self.assertIn(True, displays)
        self.assertIn(False, displays)

    def test_escaped_dollar_is_not_math(self):  # R1(c)
        r = self._pp(r"an escaped \$5 is never math")
        self.assertEqual(r["count"], 0)
        self.assertIn(r"\$5", r["text"])

    def test_bare_currency_is_not_math(self):  # R1(d)
        r = self._pp("costs $5 and $10 total")
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["text"], "costs $5 and $10 total")

    def test_fenced_code_is_excluded(self):  # R1(b)
        r = self._pp("prose $a$ then\n\n```\n$x$ literal\n```\n\nmore $b$")
        self.assertEqual(r["count"], 2)  # only a and b, not the fenced $x$
        self.assertIn("$x$ literal", r["text"])

    def test_inline_code_span_is_excluded(self):  # R1(b)
        r = self._pp("prose `$x$` and real $a$")
        self.assertEqual(r["count"], 1)
        self.assertIn("`$x$`", r["text"])

    def test_repeated_formula_dedups(self):  # R2(a)
        r = self._pp("$x^2$ appears twice: $x^2$ again")
        self.assertEqual(r["count"], 1)

    def test_display_before_inline_no_double_count(self):  # R1(e)
        r = self._pp("$$a + b$$")
        self.assertEqual(r["count"], 1)
        self.assertTrue(r["formulas"][0]["display"])

    def test_no_dollar_is_byte_identical(self):  # R6(d) / A8(i)
        text = "no math here at all, just prose"
        r = self._pp(text)
        self.assertEqual(r["text"], text)
        self.assertEqual(r["count"], 0)

    def test_dense_dollar_document_skips_preprocessing(self):  # R2(c)
        text = "$" * 10001
        r = self._pp(text)
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["text"], text)

    def test_stray_sentinel_bytes_are_stripped(self):  # R2, defence in depth
        text = f"pre-existing {SENTINEL_OPEN}7{SENTINEL_CLOSE} bytes and $x$ math"
        r = self._pp(text)
        self.assertNotIn(SENTINEL_OPEN, r["text"].replace(SENTINEL_OPEN + "0" + SENTINEL_CLOSE, ""))


@unittest.skipUnless(_have_node(), "node not on PATH")
class MathLibRendering(unittest.TestCase):
    """R3 — KaTeX -> MathML -> OMML batch render, failure handling."""

    def test_valid_formula_renders_omml(self):
        r = _call_math_lib(
            "const r = lib.preprocessMath('$x^2$'); "
            "result = {hasOmml: !!r.formulas[0].omml, hasError: !!r.formulas[0].error, "
            "omml: r.formulas[0].omml};"
        )
        self.assertTrue(r["hasOmml"])
        self.assertFalse(r["hasError"])
        self.assertIn("m:oMath", r["omml"])
        self.assertNotIn("<span", r["omml"])  # KaTeX's wrapper must not leak into the OMML

    def test_malformed_formula_degrades_without_strict(self):  # R3(a)(c)
        r = _call_math_lib(
            r"const r = lib.preprocessMath('$\\left($'); "
            "result = {count: r.formulas.length, hasError: !!r.formulas[0].error, "
            "raw: r.formulas[0].raw};"
        )
        self.assertEqual(r["count"], 1)
        self.assertTrue(r["hasError"])
        self.assertEqual(r["raw"], r"$\left($")

    def test_strict_math_throws_on_failure(self):  # R3(b)
        malformed = r"$\left($"
        script = (
            f"const lib = require({json.dumps(MATH_LIB)});\n"
            f"lib.preprocessMath({json.dumps(malformed)}, {{strict: true}});"
        )
        proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, cwd=SCRIPTS)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(r"\left(", proc.stderr)


@unittest.skipUnless(_have_node(), "node not on PATH")
class Md2DocxMathE2E(unittest.TestCase):
    """R4-R6, A1-A11 — full pipeline through md2docx.js on examples/fixture-math.md."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="md2docx_math_")

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _run(self, *flags, md_path=None):
        out = os.path.join(self._tmp, f"out-{len(flags)}-{hash(flags) & 0xffff}.docx")
        proc = subprocess.run(
            ["node", MD2DOCX, md_path or FIXTURE, out, *flags],
            capture_output=True, text=True)
        return proc.returncode, out, proc.stderr

    def _docxml(self, path):
        return zipfile.ZipFile(path).read("word/document.xml").decode()

    def _omath_count(self, xml):
        return len(re.findall(r"<m:oMath\b", xml))

    # --- A1: happy path, valid package -----------------------------------
    def test_a1_default_run_exits_zero_and_validates(self):
        rc, out, err = self._run()
        self.assertEqual(rc, 0, err)
        proc = subprocess.run(["python3", VALIDATE, out], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OK", proc.stdout)

    # --- A2: at least one oMath per math-bearing fixture case -------------
    def test_a2_omath_count_covers_every_case(self):
        rc, out, err = self._run()
        self.assertEqual(rc, 0, err)
        xml = self._docxml(out)
        # inline E=mc^2, inline x_t, display sum, bold alpha+beta, table y=mx+b == 5
        self.assertGreaterEqual(self._omath_count(xml), 4)

    # --- A3 / A4: malformed formula degrade-and-warn vs --strict-math -----
    def test_a3_malformed_formula_degrades_with_warning(self):
        rc, out, err = self._run()
        self.assertEqual(rc, 0, err)
        self.assertIn(r"\left(", err)
        xml = self._docxml(out)
        self.assertIn(r"$\left($", xml)

    def test_a4_strict_math_exits_nonzero(self):
        rc, out, err = self._run("--strict-math")
        self.assertNotEqual(rc, 0)
        self.assertIn(r"\left(", err)

    # --- A5: sentinel-leak regression --------------------------------------
    def test_a5_no_sentinel_bytes_leak(self):
        rc, out, err = self._run()
        self.assertEqual(rc, 0, err)
        xml = self._docxml(out)
        self.assertNotIn(SENTINEL_OPEN, xml)
        self.assertNotIn(SENTINEL_CLOSE, xml)

    def test_a5_no_leak_with_no_math_either(self):
        rc, out, err = self._run("--no-math")
        self.assertEqual(rc, 0, err)
        xml = self._docxml(out)
        self.assertNotIn(SENTINEL_OPEN, xml)
        self.assertNotIn(SENTINEL_CLOSE, xml)

    # --- A6: fenced code block formula survives literally ------------------
    def test_a6_fenced_code_formula_is_literal(self):
        rc, out, err = self._run()
        self.assertEqual(rc, 0, err)
        xml = self._docxml(out)
        self.assertIn("formula-looking text: $x$ stays literal in a fence", xml)

    # --- A7: --no-math reproduces the pre-TASK-031 literal shape ----------
    def test_a7_no_math_keeps_literal_dollar_text(self):
        rc, out, err = self._run("--no-math")
        self.assertEqual(rc, 0, err)
        xml = self._docxml(out)
        self.assertEqual(self._omath_count(xml), 0)
        self.assertIn("E = mc", xml)  # the raw $E = mc^2$ text, unconverted

    # --- A8: a $-free document is a true no-op ------------------------------
    def test_a8_dollar_free_document_default_equals_no_math(self):
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", dir=self._tmp, delete=False, encoding="utf-8") as fh:
            fh.write("# No math here\n\nJust ordinary prose, no dollar signs at all.\n")
            md_path = fh.name
        rc1, out1, err1 = self._run(md_path=md_path)
        rc2, out2, err2 = self._run("--no-math", md_path=md_path)
        self.assertEqual(rc1, 0, err1)
        self.assertEqual(rc2, 0, err2)
        self.assertEqual(self._docxml(out1), self._docxml(out2))

    # --- A9 lives outside the repo tree (tmp15/); not wired here, see TASK §4 ---

    # --- A11: currency negative cases never become math --------------------
    def test_a11_currency_and_escaped_dollar_stay_literal(self):
        rc, out, err = self._run()
        self.assertEqual(rc, 0, err)
        xml = self._docxml(out)
        self.assertIn("$5 and $10", xml)
        # the currency line itself has no formula of its own
        self.assertEqual(self._omath_count(xml.split("$5 and $10")[1].split("fenced code")[0]), 0)

    # --- R4(d): standalone display formula gets its own centred paragraph --
    def test_display_paragraph_is_centered(self):
        rc, out, err = self._run()
        self.assertEqual(rc, 0, err)
        xml = self._docxml(out)
        self.assertNotIn(r"\sum", xml)  # the raw TeX must not appear; it should be real OMML
        # the standalone $$…$$ paragraph's <w:pPr> carries center alignment immediately
        # before its <m:oMath> — an inline formula's surrounding paragraph never does.
        self.assertRegex(xml, r'<w:jc w:val="center"/></w:pPr><m:oMath\b')

    # --- equation-array table gets asymmetric column widths, not an equal split -----
    # Found during A9 (the tmp15 reference-document manual gate): an equal 4-way split of
    # the Pandoc "|  | $$…$$ |  | (N) |" equation-table shape left the formula column only
    # ~1/4 of the page width, clipping every non-trivial equation. Locked in here against
    # the small fixture table so a regression doesn't require the external reference doc.
    def test_equation_array_table_gets_asymmetric_columns(self):
        rc, out, err = self._run()
        self.assertEqual(rc, 0, err)
        xml = self._docxml(out)
        cols = [int(w) for w in re.findall(r'<w:gridCol\s+w:w="(\d+)"', xml)]
        self.assertEqual(len(cols), 4)
        # the formula column (index 1) must dominate; the two spacer columns must be small
        self.assertGreater(cols[1], cols[0] * 5)
        self.assertGreater(cols[1], cols[2] * 5)
        self.assertGreater(cols[1], cols[3])

    # --- R7: dependencies present --------------------------------------------
    def test_dependencies_installed(self):
        pkg = os.path.join(SCRIPTS, "package.json")
        with open(pkg, encoding="utf-8") as fh:
            data = json.load(fh)
        deps = data.get("dependencies", {})
        self.assertIn("katex", deps)
        self.assertIn("mathml2omml", deps)


if __name__ == "__main__":
    unittest.main()

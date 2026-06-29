"""md2pdf math preprocessing: `$…$`/`$$…$$` TeX → MathML (KaTeX), currency/code-safe.

Two layers:
  • node-free: delimiter detection (currency NOT matched), code/fence protection, and
    graceful degradation when the KaTeX renderer is unavailable;
  • node-gated E2E: real KaTeX render → MathML injected, the raw-TeX <annotation> stripped.

Run:
    cd skills/pdf/scripts
    ./.venv/bin/python -m unittest tests.test_md2pdf_math -v
"""
from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import md2pdf  # noqa: E402

_HAVE_KATEX = (
    shutil.which("node") is not None
    and (Path(md2pdf.SCRIPT_DIR) / "node_modules" / "katex").is_dir()
)


class TestMathDelimiterDetection(unittest.TestCase):
    def test_inline_and_display_matched(self):
        self.assertEqual(
            [m.group(1) for m in md2pdf._MATH_INLINE_RE.finditer(r"a $x_1+y$ b")], ["x_1+y"])
        self.assertEqual(
            [m.group(1).strip() for m in md2pdf._MATH_DISPLAY_RE.finditer(r"$$\sum x$$")], [r"\sum x"])

    def test_currency_not_matched(self):
        # The classic false-positive: "$5 and $10" must NOT be read as inline math.
        self.assertEqual(list(md2pdf._MATH_INLINE_RE.finditer("it costs $5 and $10 total")), [])

    def test_escaped_dollar_not_a_delimiter(self):
        self.assertEqual(list(md2pdf._MATH_INLINE_RE.finditer(r"price is \$5 each")), [])


class TestMathPreprocessNodeFree(unittest.TestCase):
    def test_no_dollar_is_noop(self):
        md = "# Title\n\nplain prose, no math.\n"
        self.assertEqual(md2pdf.preprocess_math(md), md)

    def test_code_and_currency_preserved_when_renderer_absent(self):
        md = ("inline $x_1$ here\n\n`shell $VAR`\n\n```\nprice=$5\n```\n\n"
              "costs $5 and $10\n")
        with mock.patch.object(md2pdf, "_node_path", return_value=None):
            out = md2pdf.preprocess_math(md)
        # Renderer unavailable → unchanged (graceful), so EVERYTHING is preserved literally.
        self.assertEqual(out, md)

    def test_strict_raises_when_renderer_absent(self):
        with mock.patch.object(md2pdf, "_node_path", return_value=None):
            with self.assertRaises(RuntimeError):
                md2pdf.preprocess_math("an equation $a+b$\n", strict=True)

    def test_dollar_cap_skips_pathological_input(self):
        # vdd-multi perf: a `$`-dense doc must not trigger the O(n²) inline scan — skip it.
        big = "$" * (md2pdf._MATH_DOLLAR_CAP + 1)
        self.assertEqual(md2pdf.preprocess_math(big), big)  # returned unchanged, no hang

    def test_strict_dollar_cap_raises(self):
        with self.assertRaises(RuntimeError):
            md2pdf.preprocess_math("$" * (md2pdf._MATH_DOLLAR_CAP + 1), strict=True)


@unittest.skipUnless(_HAVE_KATEX, "needs node + scripts/node_modules/katex")
class TestMathFailedDisplayNoCrash(unittest.TestCase):
    def test_failed_display_with_inner_dollar_does_not_crash(self):
        # vdd-multi regression: a display formula that FAILS KaTeX leaves `$$…$$`; an inner
        # `$` previously made the inline pass look up an uncollected formula → KeyError crash.
        # Must now degrade gracefully: the bad display stays literal, the good math renders.
        md = r"ok $a+b$ and bad $$\frobnicate{$y$}$$ end" + "\n"
        out = md2pdf.preprocess_math(md)          # must not raise
        self.assertIn('class="math-inline"', out)  # the good $a+b$ rendered
        self.assertIn("$$", out)                    # the failed display kept as literal $$…$$


@unittest.skipUnless(_HAVE_KATEX, "needs node + scripts/node_modules/katex")
class TestMathPreprocessE2E(unittest.TestCase):
    def test_inline_display_rendered_currency_code_untouched(self):
        md = (
            r"Inline $s * C_1 \approx m_1$ holds." + "\n\n"
            r"$$\sum_{i=1}^n x_i \approx \frac{a}{b}$$" + "\n\n"
            "Costs $5 and $10 total.\n\n"
            "`let x = $foo`\n\n```\nprice=$5\n```\n"
        )
        out = md2pdf.preprocess_math(md)
        # Math → MathML (no raw-TeX annotation duplicated, no leftover delimiters in prose).
        self.assertIn("<math", out)
        self.assertIn('class="math-display"', out)
        self.assertNotIn("<annotation", out)        # accessibility annotation stripped
        self.assertNotIn(r"\approx", out)            # inline formula consumed
        self.assertNotIn(r"\sum", out)               # display formula consumed
        # Currency + code preserved verbatim.
        self.assertIn("Costs $5 and $10 total.", out)
        self.assertIn("`let x = $foo`", out)
        self.assertIn("price=$5", out)

    def test_bad_formula_kept_as_literal(self):
        # An unparseable formula must not abort; it stays as the literal `$…$`.
        md = r"good $a+b$ and bad $\frobnicate{$ end" + "\n"
        out = md2pdf.preprocess_math(md)
        self.assertIn("<math", out)  # the good one rendered


if __name__ == "__main__":
    unittest.main()

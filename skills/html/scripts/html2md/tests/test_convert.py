"""html_convert.js wrapper: ARIA-role tables → GFM + chrome-button strip.

Exercised through the Python bridge (core_bridge → html_convert.js). Requires node.
"""
from __future__ import annotations

import os
import shutil
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import core_bridge  # noqa: E402

_HAVE_NODE = shutil.which("node") is not None and os.path.isdir(
    os.path.join(SCRIPTS, "node_modules", "turndown"))


@unittest.skipUnless(_HAVE_NODE, "node + turndown not installed")
class TestAriaTableAndChrome(unittest.TestCase):
    def test_aria_table_to_gfm(self):
        """role=table/columnheader/cell → a GFM table (not flattened paragraphs)."""
        html = (
            '<div role="table"><div role="rowgroup">'
            '<div role="row"><div role="columnheader">Name</div>'
            '<div role="columnheader">Type</div></div></div>'
            '<div role="rowgroup">'
            '<div role="row"><div role="cell"><p>type</p></div>'
            '<div role="cell"><p>String</p></div></div>'
            '<div role="row"><div role="cell"><p>dex</p></div>'
            '<div role="cell"><p>String</p></div></div>'
            "</div></div>")
        md = core_bridge.html_to_markdown(html)
        self.assertIn("| Name | Type |", md)
        self.assertIn("|---|---|", md)
        self.assertIn("| type | String |", md)
        self.assertIn("| dex | String |", md)

    def test_gitbook_sibling_headers(self):
        """Headers in a SIBLING rowgroup (GitBook) are pulled into the table."""
        html = (
            '<div class="wrap">'
            '<div role="rowgroup"><div role="row">'
            '<div role="columnheader">Name</div><div role="columnheader">Value</div>'
            "</div></div>"
            '<div role="table"><div role="rowgroup"><div role="row">'
            '<div role="cell">Content-Type</div><div role="cell">application/json</div>'
            "</div></div></div></div>")
        md = core_bridge.html_to_markdown(html)
        self.assertIn("| Name | Value |", md)
        self.assertIn("| Content-Type | application/json |", md)

    def test_buttons_and_copy_stripped(self):
        """<button>, role=button and aria-label^=Copy controls are removed."""
        html = ('<p>keep</p>'
                '<button type="button"><svg></svg><span>Copy</span></button>'
                '<div role="button" aria-label="Copy page">Copy page</div>')
        md = core_bridge.html_to_markdown(html)
        self.assertIn("keep", md)
        self.assertNotIn("Copy", md)

    def test_nested_aria_table_not_merged(self):
        """A nested role=table inside a cell stays separate — outer grid not polluted."""
        html = (
            '<div role="table"><div role="row">'
            '<div role="columnheader">Outer</div></div>'
            '<div role="row"><div role="cell">'
            '<div role="table"><div role="row"><div role="columnheader">Inner</div></div>'
            '<div role="row"><div role="cell">innerval</div></div></div>'
            "</div></div></div>")
        md = core_bridge.html_to_markdown(html)
        # Outer header row must NOT have absorbed the inner table's "Inner" column.
        self.assertNotIn("| Outer | Inner |", md)
        self.assertIn("Inner", md)  # inner table still rendered somewhere

    def test_two_tables_one_wrapper_headers_isolated(self):
        """Two tables under one wrapper keep their OWN preceding-sibling headers."""
        html = (
            '<div class="wrap">'
            '<div role="rowgroup"><div role="row">'
            '<div role="columnheader">HdrA</div></div></div>'
            '<div role="table"><div role="row"><div role="cell">valA</div></div></div>'
            '<div role="rowgroup"><div role="row">'
            '<div role="columnheader">HdrB</div></div></div>'
            '<div role="table"><div role="row"><div role="cell">valB</div></div></div>'
            "</div>")
        md = core_bridge.html_to_markdown(html)
        self.assertIn("| HdrA |", md)
        self.assertIn("| valA |", md)
        self.assertIn("| HdrB |", md)
        self.assertIn("| valB |", md)
        self.assertNotIn("| HdrA | HdrB |", md)  # headers not concatenated across tables

    def test_accordion_role_button_prose_preserved(self):
        """A role=button DIV wrapping real prose is kept; a leaf role=button is dropped."""
        md = core_bridge.html_to_markdown(
            '<div role="button"><p>Accordion prose marker</p></div>'
            '<div role="button">ExpandLeaf</div>')
        self.assertIn("Accordion prose marker", md)
        self.assertNotIn("ExpandLeaf", md)

    def test_multiline_link_collapsed_and_icon_anchor_dropped(self):
        """Block-content links collapse to one line; icon-only anchors are dropped."""
        md = core_bridge.html_to_markdown(
            '<a href="https://x/y"><div><div>Nav Item Text</div></div></a>'
            '<h2><a href="#sec"><svg></svg></a></h2>')
        self.assertIn("[Nav Item Text](https://x/y)", md)
        self.assertNotRegex(md, r"\]\(\s*\n")          # link never split across lines
        self.assertNotRegex(md, r"(?m)^#{1,6} \[")      # icon-only heading anchor dropped

    def test_real_link_text_preserved(self):
        """A normal inline link keeps its text + href."""
        md = core_bridge.html_to_markdown('<p>see <a href="https://x">the docs</a> now</p>')
        self.assertIn("[the docs](https://x)", md)

    def test_ltx_listing_to_code_block(self):
        """arXiv/LaTeXML ltx_listing → fenced code; line-number gutter dropped."""
        html = (
            '<div class="ltx_listing">'
            '<div class="ltx_listingline"><span class="ltx_tag ltx_tag_listingline">1</span>'
            '<span class="ltx_text ltx_font_typewriter">PROMPT = "hi"</span></div>'
            '<div class="ltx_listingline"><span class="ltx_tag ltx_tag_listingline">2</span></div>'
            '<div class="ltx_listingline"><span class="ltx_tag ltx_tag_listingline">3</span>'
            '<span class="ltx_text ltx_font_typewriter">end()</span></div>'
            "</div>")
        md = core_bridge.html_to_markdown(html)
        self.assertIn("```", md)
        self.assertIn('PROMPT = "hi"', md)
        self.assertIn("end()", md)
        self.assertNotIn("1PROMPT", md)             # gutter not glued onto first token
        self.assertNotRegex(md, r"(?m)^\s*[123]\s*$")  # bare gutter numbers dropped

    def test_data_uri_image_and_link_dropped(self):
        """Sub-threshold base64 data: images + data: links don't dump blobs; real images
        survive. (Content-sized data: images are kept — see test_data_uri_content_image_kept.)"""
        md = core_bridge.html_to_markdown(
            '<p>keep</p>'
            '<img src="data:image/png;base64,AAAABBBBCCCC">'   # tiny → dropped
            '<img src="https://x/real.png" alt="r">'
            '<a href="data:text/plain;base64,ZZZZ">dl</a>')
        self.assertNotIn("data:", md)
        self.assertIn("![r](https://x/real.png)", md)
        self.assertIn("keep", md)

    def test_data_uri_content_image_kept(self):
        """A CONTENT-sized data: image (>= DATA_URI_MIN_LEN) survives conversion as an
        ![](data:…) link (emit.py localizes it later); the tiny one beside it is dropped."""
        big = "data:image/png;base64," + "A" * 1100
        tiny = "data:image/png;base64,AAAABBBBCCCC"
        md = core_bridge.html_to_markdown(
            f'<p>keep</p><img src="{tiny}" alt="icon"><img src="{big}" alt="diagram">')
        self.assertIn(big, md, "content-sized data: image must be preserved")
        self.assertNotIn("icon", md, "tiny icon blob must be dropped")

    def test_mathjax_pandoc_spans_to_dollar(self):
        """MathJax/Pandoc `class=math inline|display` spans → `$…$`/`$$…$$` with RAW TeX
        (no markdown-escaping of `_ * [ ]`, no leftover `\\(…\\)`). Regression for the
        vitalik.eth.limo article whose 562 inline formulas were being escaped/corrupted."""
        md = core_bridge.html_to_markdown(
            '<p>see <span data-evaluate="no"><span class="math inline">'
            '\\(C_1 + C_2\\)</span></span> and</p>'
            '<p><span class="math display">\\[\\sum_{i=1}^n x_i \\approx m_1\\]</span></p>')
        self.assertIn("$C_1 + C_2$", md)            # real subscripts/operator, $-delimited
        self.assertNotIn("\\(", md)                  # no leftover MathJax delimiter
        self.assertNotIn("\\_", md)                  # subscripts not markdown-escaped
        self.assertNotIn("\\*", md)                  # operator not escaped
        self.assertRegex(md, r"\$\$\s*\\sum_\{i=1\}\^n x_i \\approx m_1\s*\$\$")  # display block

    def test_math_filter_no_false_positive(self):
        """Adversarial C: a class merely CONTAINING the token `math` (e.g. `not-math`,
        `math-box`) but lacking inline|display must NOT be treated as math — its text
        passes through normally, never wrapped in `$…$`."""
        for cls in ("not-math", "math-box", "aftermath"):
            md = core_bridge.html_to_markdown(f'<p>x</p><span class="{cls}">hello world</span>')
            self.assertNotIn("$hello world$", md, f"class={cls} wrongly treated as math")
            self.assertIn("hello world", md)

    def test_mathml_alttext_to_dollar(self):
        """TASK 028 / HTML2MD-12: arXiv/LaTeXML `<math alttext="TeX">` (presentation MathML,
        NO class=math span) → clean `$…$` / `$$…$$` lifted from `alttext`, never the
        interleaved Unicode-glyph + escaped-TeX garble turndown dumps by default."""
        md = core_bridge.html_to_markdown(
            '<p>inline <math class="ltx_Math" display="inline" alttext="\\alpha_{k}">'
            '<semantics><mrow><mi>α</mi><mi>k</mi></mrow></semantics></math> done</p>'
            '<p><math class="ltx_Math" display="block" alttext="\\sum_{i=1}^{n}x_{i}">'
            '<semantics><mrow><mo>∑</mo></mrow></semantics></math></p>')
        self.assertIn("$\\alpha_{k}$", md)              # inline, clean single-backslash TeX
        # display OUTSIDE a table cell → blank-line-wrapped block (same shape as htmlMath)
        self.assertIn("$$\n\\sum_{i=1}^{n}x_{i}\n$$", md)
        self.assertNotIn("\\_", md)                      # body NOT markdown-escaped
        self.assertNotIn("αk", md)                       # NO presentation-glyph leak

    def test_mathml_annotation_fallback(self):
        """A `<math>` with no `alttext` falls back to the `<annotation encoding=
        "application/x-tex">` child; `alttext` wins when both are present."""
        md1 = core_bridge.html_to_markdown(
            '<p>a <math display="inline"><semantics><mi>y</mi>'
            '<annotation encoding="application/x-tex">y^{2}</annotation>'
            '</semantics></math> b</p>')
        self.assertIn("$y^{2}$", md1)
        md2 = core_bridge.html_to_markdown(
            '<p><math display="inline" alttext="FROM_ALTTEXT"><semantics>'
            '<annotation encoding="application/x-tex">FROM_ANNOTATION</annotation>'
            '</semantics></math></p>')
        self.assertIn("$FROM_ALTTEXT$", md2)
        self.assertNotIn("FROM_ANNOTATION", md2)

    def test_mathml_display_in_table_cell(self):
        """R3: a display `<math>` inside an arXiv equation `<table>` stays SINGLE-LINE `$$…$$`
        so it does not break the GFM row (newline-wrapped block form would)."""
        md = core_bridge.html_to_markdown(
            '<table><tr><td></td>'
            '<td><math display="block" alttext="a^{2}+b^{2}=c^{2}"><mi>x</mi></math></td>'
            '<td>(1)</td></tr></table>')
        row = [ln for ln in md.splitlines() if "$$a^{2}+b^{2}=c^{2}$$" in ln]
        self.assertEqual(len(row), 1, "display math must be on ONE line inside the table row")
        self.assertIn("|", row[0])                       # still a GFM table row

    def test_mathml_pipe_in_table_cell_not_corrupted(self):
        """Adversarial (critic MED-1): a `|` / `\\|` in display math inside a `<table>` cell
        must NOT be corrupted by the GFM cell's `|`→`\\|` escaper (which KaTeX misreads as a
        line break). We pre-map to pipe-free LaTeX (`\\|`→`\\Vert`, `|`→`\\vert`), so no bare
        or backslash-pipe survives to be escaped."""
        md = core_bridge.html_to_markdown(
            '<table><tr><td></td>'
            '<td><math display="block" alttext="\\mathrm{KL}(q\\|p),|x|">'
            '<mi>x</mi></math></td><td>(9)</td></tr></table>')
        row = [ln for ln in md.splitlines() if "$$" in ln][0]
        self.assertNotIn("\\|", row)                 # no backslash-pipe (KaTeX line-break)
        self.assertIn("\\Vert", row)                 # norm bar preserved as \Vert (‖)
        self.assertIn("\\vert", row)                 # abs bar preserved as \vert (|)

    def test_pseudocode_listing_renders_math(self):
        """R6: a LaTeXML algorithm listing (`ltx_listing` carrying inline `<math>`) renders as
        TEXT with rendered `$…$` math + `**bold**` keywords + hard line breaks — NOT a fenced
        code block (where `$…$` would show as literal LaTeX). Presentation glyphs never leak."""
        md = core_bridge.html_to_markdown(
            '<div class="ltx_listing">'
            '<div class="ltx_listingline"><span class="ltx_tag ltx_tag_listingline">1:</span>'
            '<span class="ltx_p"><span class="ltx_font_bold">Input:</span> Dataset '
            '<math alttext="\\mathcal{D}"><mi>𝒟</mi></math></span></div>'
            '<div class="ltx_listingline"><span class="ltx_tag ltx_tag_listingline">2:</span>'
            '<span class="ltx_p">return <math alttext="g_{\\phi}"><mi>g</mi></math></span></div>'
            '</div>')
        self.assertNotIn("```", md)                       # NOT a fenced code block
        self.assertIn("$\\mathcal{D}$", md)               # math renders as $…$ (KaTeX)
        self.assertIn("$g_{\\phi}$", md)
        self.assertIn("**Input:**", md)                   # bold keyword preserved
        self.assertNotIn("𝒟", md)                          # NO presentation-glyph leak
        self.assertNotIn("1:", md)                        # gutter dropped
        self.assertRegex(md, r"Input:.*\n.*return")       # both lines present, hard-broken

    def test_ltx_listing_code_no_math_stays_fenced(self):
        """A real code listing (`ltx_listing` with NO `<math>`) still becomes a fenced code
        block — the pseudocode branch is gated on inline `<math>` presence."""
        md = core_bridge.html_to_markdown(
            '<div class="ltx_listing">'
            '<div class="ltx_listingline"><span class="ltx_tag ltx_tag_listingline">1</span>'
            '<span class="ltx_font_typewriter">x = f(a)</span></div>'
            '</div>')
        self.assertIn("```", md)                          # fenced (real code)
        self.assertIn("x = f(a)", md)
        self.assertNotIn("$", md)

    def test_mathml_no_tex_falls_back_to_glyphs(self):
        """R4 (critic MED-2): a presentation-only `<math>` (no `alttext`, no x-tex annotation —
        e.g. hand-authored Wikipedia/MDN) keeps turndown's default glyph rendering rather than
        VANISHING silently. No `$` delimiters are emitted (nothing to delimit), but content is
        preserved (no silent data loss)."""
        md = core_bridge.html_to_markdown(
            '<p>before <math display="inline"><mi>z</mi></math> after</p>')
        self.assertNotIn("$", md)                        # no $-delimiters (no TeX to wrap)
        self.assertIn("before", md)
        self.assertIn("after", md)
        self.assertIn("z", md)                           # glyph preserved, NOT silently dropped

    def test_mathml_array_colspec_not_corrupted_outside_table(self):
        """Adversarial (logic MED-1, 2026-07-09): `|` in a `\\begin{array}{c|c}` column spec
        is a vertical RULE — KaTeX's column parser accepts only `l c r | :`, so the old
        unconditional `|`→`\\vert` remap threw "Unknown column alignment: \\vert". Outside a
        GFM table cell there is no cell escaper, so pipes must pass through UNTOUCHED."""
        md = core_bridge.html_to_markdown(
            '<p><math display="inline" '
            'alttext="\\begin{array}{c|c}a&amp;b\\end{array}"><mi>x</mi></math></p>')
        self.assertIn("{c|c}", md)                       # column spec intact (KaTeX-valid)
        self.assertNotIn("\\vert", md)                    # NO remap outside a table cell
        md2 = core_bridge.html_to_markdown(
            '<p>norm <math display="inline" alttext="|x|+\\|y\\|"><mi>x</mi></math></p>')
        self.assertIn("$|x|+\\|y\\|$", md2)               # plain pipes untouched outside cells

    def test_mathml_array_preamble_exempt_from_cell_pipe_map(self):
        """Inside a GFM cell, body pipes are remapped (`|`→`\\vert`) but a
        `\\begin{array}{…}` column preamble is EXEMPT — `\\vert` is invalid there. The cell
        escaper then escapes the preamble pipe to `\\|` (accepted honest-scope: an
        array-with-rules inside a GFM cell is unrepresentable either way)."""
        md = core_bridge.html_to_markdown(
            '<table><tr><td><math display="block" '
            'alttext="\\begin{array}{c|c}|x|&amp;y\\end{array}"><mi>x</mi></math></td>'
            '<td>(2)</td></tr></table>')
        row = [ln for ln in md.splitlines() if "$$" in ln][0]
        self.assertIn("{c\\|c}", row)                     # preamble pipe NEVER TeX-remapped
        self.assertNotIn("c\\vert c}", row)               # (only cell-escaped, honest-scope)
        self.assertIn("\\vert x\\vert", row)              # body pipes remapped as before

    @staticmethod
    def _beacon_escapes_math(md):
        """Oracle: does an ![](…evil…) survive OUTSIDE a math span? Mirrors a $-math renderer
        with processEscapes — a `$` behind an ODD backslash run is a literal, not a delimiter;
        `$$…$$` may span lines. Returns True iff a beacon leaks into live Markdown."""
        def is_delim(i):
            if md[i] != "$":
                return False
            bs, j = 0, i - 1
            while j >= 0 and md[j] == "\\":
                bs += 1
                j -= 1
            return bs % 2 == 0
        out, i, mode = [], 0, 0   # mode 0=text, 1=inline, 2=display
        while i < len(md):
            if is_delim(i):
                dbl = i + 1 < len(md) and md[i + 1] == "$" and is_delim(i + 1)
                if mode == 0:
                    mode = 2 if dbl else 1
                    i += 2 if dbl else 1
                    continue
                if (mode == 2 and dbl) or (mode == 1 and not dbl):
                    mode = 0
                    i += 2 if dbl else 1
                    continue
                i += 2 if dbl else 1
                continue
            if mode == 0:
                out.append(md[i])
            i += 1
        return "evil" in "".join(out)

    def test_mathml_dollar_injection_neutralized(self):
        """Adversarial (security 2026-07-09, both review iterations): a crafted `alttext`
        containing `$` must not TERMINATE the `$…$`/`$$…$$` wrapper and inject live Markdown
        (an exfil image beacon). Covers all three entry points found across two vdd-multi
        rounds: (1) simple mid-string `$`; (2) EVEN backslash run before `$` (`\\\\$` — the
        naive `/\\?\\$/g` was a no-op on it → parity hole); (3) TeX ending in an ODD backslash
        run that would escape the ABUTTING closing delimiter. None may leak a live beacon."""
        vectors = [
            'x$ ![](http://evil/leak) $y',        # simple
            '\\\\$![](http://evil/leak)$',        # even (2) backslashes before $
            'x$ ![](http://evil/leak) $y\\',      # trailing odd backslash escapes closer
            'a\\\\\\\\$![](http://evil/x)$',      # even (4) backslashes
        ]
        for alt in vectors:
            for disp in ("inline", "block"):
                md = core_bridge.html_to_markdown(
                    f'<p><math display="{disp}" alttext="{alt}"><mi>x</mi></math></p>')
                self.assertFalse(self._beacon_escapes_math(md),
                                 f"beacon leaked: alt={alt!r} display={disp}\n{md!r}")
        # the sibling Pandoc `htmlMath` rule is the SAME channel — must be hardened too
        for html in (
            '<p><span class="math inline">\\(a$ ![](http://evil/b) $b\\)</span></p>',
            '<p><span class="math inline">\\(\\\\$![](http://evil/b)$\\)</span></p>',
            '<div class="math display">\\[q$ ![](http://evil/b) $r\\]</div>',
            # display span with newline+$$ smuggling
            '<div class="math display">\\[a\n$$\n![](http://evil/b)\n$$\nb\\]</div>',
            # INTERIOR BLANK LINE in an inline math span (iteration-4 finding): a blank line is
            # a BLOCK paragraph split — it would orphan the opening `$` and drop the beacon into
            # the next paragraph as live Markdown. htmlMath must collapse interior whitespace.
            '<p><span class="math inline">\\(a\n\n![](http://evil/b)\\)</span></p>',
            '<p><span class="math inline">\\(a\n![](http://evil/b)\\)</span></p>',
        ):
            md = core_bridge.html_to_markdown(html)
            self.assertFalse(self._beacon_escapes_math(md), f"htmlMath beacon leaked:\n{md!r}")
            self.assertNotRegex(md, r"\n\n!\[", "beacon dropped into a new paragraph")
        # TABLE-CELL trailing-backslash (iteration-3 finding): `_texPipesForCell`'s trailing
        # `.trim()` used to strip the boundary-guard space, re-exposing the trailing `\` that
        # escapes the abutting closing `$`; a following beacon math node then rendered live.
        bs = "\\"
        for wrap in ('<td>{0}</td>', '<td><div class="ltx_listing"><div class="ltx_listingline">'
                     '<span class="ltx_tag ltx_tag_listingline">1:</span>{0}</div></div></td>'):
            cell = wrap.format(
                f'<math alttext="x{bs}"></math><math alttext="![](http://evil/cell)"></math>')
            md = core_bridge.html_to_markdown(f'<table><tr>{cell}</tr></table>')
            self.assertFalse(self._beacon_escapes_math(md),
                             f"cell trailing-backslash beacon leaked:\n{md!r}")
        # an honest escaped dollar in TeX is IDENTITY-mapped, not doubled
        md2 = core_bridge.html_to_markdown(
            '<p><math display="inline" alttext="\\$5+\\$6"><mi>x</mi></math></p>')
        self.assertIn("$\\$5+\\$6$", md2)

    def test_pseudocode_adjacent_math_separated(self):
        """Two adjacent inline `<math>` siblings in one pseudocode line (no separating text)
        must not fuse into an ambiguous `$a$$b$` delimiter run."""
        md = core_bridge.html_to_markdown(
            '<div class="ltx_listing">'
            '<div class="ltx_listingline"><span class="ltx_tag ltx_tag_listingline">1:</span>'
            '<math alttext="a"><mi>a</mi></math><math alttext="b"><mi>b</mi></math></div>'
            '</div>')
        self.assertIn("$a$ $b$", md)
        self.assertNotIn("$a$$b$", md)

    def test_data_uri_newline_in_src_collapsed(self):
        """Adversarial D: a data: src whose base64 wraps across lines is collapsed to one
        line, so the emitted Markdown image link is single-line + parseable downstream."""
        b = "A" * 1100
        md = core_bridge.html_to_markdown(
            f'<p>x</p><img src="data:image/png;base64,{b[:500]}\n{b[500:]}" alt="d">')
        # No newline inside the data: URI, and the whole link is on one line.
        img_line = [ln for ln in md.splitlines() if "data:image" in ln]
        self.assertEqual(len(img_line), 1, "data: image link must be on exactly one line")
        self.assertRegex(img_line[0], r'!\[d\]\(data:image/png;base64,A+\)')

    def test_plain_table_still_works(self):
        """A real <table> still converts (core path unaffected by the ARIA rule)."""
        md = core_bridge.html_to_markdown(
            "<table><tr><th>H</th></tr><tr><td>v</td></tr></table>")
        self.assertIn("| H |", md)
        self.assertIn("| v |", md)


if __name__ == "__main__":
    unittest.main()

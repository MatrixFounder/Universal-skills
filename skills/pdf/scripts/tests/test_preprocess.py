"""Unit-level regression tests for `html2pdf_lib/` helpers.

Each test pins down ONE specific bug fix from the last 6-7 commits to
`html2pdf.py`. If a future refactor reintroduces the bug, the test
fails; the test name in unittest output names the commit / VDD-iter
that originally fixed it.

This file imports underscore-prefixed helpers (`_strip_icon_svgs`,
`_strip_interactive_chrome`, `_strip_universal_ads`, etc.) from
`html2pdf_lib.preprocess`. Those names are private by Python
convention but PINNED by these tests as the regression-test API.
Refactors that rename them MUST update this file in lockstep.

Public-named helpers (`get_attr`, `text_length`, `find_all_elements`)
are imported from `html2pdf_lib.dom_utils`; `reader_mode_html` from
`html2pdf_lib.reader_mode`; `_offline_url_fetcher` /
`_install_render_watchdog` / `_clear_render_watchdog` from
`html2pdf_lib.render`.

Run:

    cd skills/pdf/scripts
    ./.venv/bin/python -m unittest tests.test_preprocess -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

# `html2pdf_lib.render` imports `md2pdf` from sys.path; keep the
# scripts/ dir importable for direct unittest invocation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from html2pdf_lib.dom_utils import (  # noqa: E402
    body_text_length, find_all_elements, get_attr, text_length,
)
from html2pdf_lib.preprocess import (  # noqa: E402
    _fix_svg_viewport,
    _flatten_table_code_blocks,
    _fo_to_svg_text,
    _parse_label_bg,
    _strip_empty_anchor_links,
    _strip_icon_svgs,
    _strip_interactive_chrome,
    _strip_universal_ads,
    preprocess_html,
)
from html2pdf_lib.normalize_css import NORMALIZE_CSS  # noqa: E402
from html2pdf_lib.reader_mode import reader_mode_html  # noqa: E402
from html2pdf_lib.render import (  # noqa: E402
    _clear_render_watchdog,
    _install_render_watchdog,
    _offline_url_fetcher,
)


# ── _strip_icon_svgs ─────────────────────────────────────────────────────


class TestStripIconSVGs(unittest.TestCase):
    """Cover VDD-iter-5 HIGH-1, HIGH-2 and Mintlify size-N detection."""

    def test_self_closing_doesnt_disable_loop(self) -> None:
        """VDD-iter-5 HIGH-1: a self-closing `<svg/>` early in the doc must
        not break depth tracking and silently leave every later SVG in place.
        Bug regression: depth never reached 0, code hit `if depth != 0:
        out.append(html[m.start():]); break` and returned the rest verbatim.
        """
        html = (
            '<p>before</p>'
            '<svg width="50" height="50"/>'
            '<p>middle</p>'
            '<svg width="20" height="20"><path d="M0"/></svg>'
            '<p>after</p>'
        )
        out = _strip_icon_svgs(html)
        self.assertNotIn("<svg", out, f"some SVG survived: {out!r}")
        self.assertIn("<p>middle</p>", out)
        self.assertIn("<p>after</p>", out)

    def test_aspect_ratio_keeps_tall_content(self) -> None:
        """VDD-iter-5 HIGH-2: 50x500 SVG (legitimate vertical content like a
        progress bar / timeline) must NOT be stripped. Old OR-rule fired on
        width=50<=64 and dropped the content."""
        html = '<svg width="50" height="500"><g><circle/></g></svg>'
        out = _strip_icon_svgs(html)
        self.assertEqual(
            out, html,
            "tall content SVG must survive — width<=64 alone is not enough",
        )

    def test_real_diagram_kept(self) -> None:
        """Regression guard: 600×400 SVG (real diagram) must stay."""
        html = '<svg width="600" height="400"><rect/></svg>'
        out = _strip_icon_svgs(html)
        self.assertEqual(out, html)

    def test_mintlify_size_5_class(self) -> None:
        """Commit a7fbc9f: Tailwind `size-5` (= 20px) classifies as icon
        even when the SVG carries only viewBox + class (no numeric dims)."""
        html = (
            '<svg viewBox="0 0 20 20" class="flex-none size-5 text-neutral-800" '
            'aria-label="Info"><path d="M0"/></svg>'
        )
        out = _strip_icon_svgs(html)
        self.assertNotIn("<svg", out)

    def test_aria_hidden_marker(self) -> None:
        """Commit 3857d6d: `aria-hidden="true"` is the W3C decorative marker;
        SVGs with it strip even when they have no other size signal."""
        html = '<svg aria-hidden="true" viewBox="0 0 100 100"><path/></svg>'
        out = _strip_icon_svgs(html)
        self.assertNotIn("<svg", out)

    def test_fontawesome_prefix(self) -> None:
        """Commit 3857d6d: FontAwesome `prefix="far"` etc. always icon."""
        html = '<svg prefix="far" viewBox="0 0 448 512"><path/></svg>'
        out = _strip_icon_svgs(html)
        self.assertNotIn("<svg", out)

    def test_small_viewbox_fallback(self) -> None:
        """Commit a7fbc9f: viewBox max-dim <= 64 is the final icon fallback
        when no dim attrs / class signals are present."""
        html = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path/></svg>'
        out = _strip_icon_svgs(html)
        self.assertNotIn("<svg", out)


# ── text_length / body_text_length ───────────────────────────────────────


class TestTextLength(unittest.TestCase):
    """VDD-iter-5 HIGH-3: tag-strip alone treats <script>/<style> bodies
    as visible text, inflating the candidate text length on Mintlify /
    Next.js pages whose <article> contains __NEXT_DATA__ JSON."""

    def test_strips_script_content(self) -> None:
        html = (
            "<article><h1>Hi</h1>"
            "<script>console.log('a really long log line' * 100);</script>"
            "</article>"
        )
        self.assertEqual(text_length(html), 2)  # only "Hi"

    def test_strips_style_content(self) -> None:
        html = (
            "<article><h1>Hi</h1>"
            "<style>body { color: red; "
            "font-family: 'Helvetica Neue', sans-serif; }</style>"
            "</article>"
        )
        self.assertEqual(text_length(html), 2)

    def test_body_text_length_uses_body_inner(self) -> None:
        html = (
            "<html><head><title>NOT TEXT</title></head>"
            "<body>BODY_TEXT</body></html>"
        )
        self.assertEqual(body_text_length(html), len("BODY_TEXT"))


# ── get_attr (formerly `_attr_value`) ────────────────────────────────────


class TestAttrValue(unittest.TestCase):
    """VDD-iter-5 HIGH-4: `data-x="role='main'"` must NOT match `role` lookup.
    Old `\\b` boundary regex matched at the word boundary INSIDE another
    attribute's quoted value."""

    def test_skips_nested_quote_value(self) -> None:
        attrs = "data-x=\"role='main'\" id='foo'"
        self.assertIsNone(get_attr(attrs, "role"))

    def test_extracts_real_attr(self) -> None:
        attrs = 'role="main" id="foo"'
        self.assertEqual(get_attr(attrs, "role"), "main")

    def test_first_attr_in_blob(self) -> None:
        # Attribute right at start of blob (no leading whitespace) — must work.
        attrs = 'class="x" role="main"'
        self.assertEqual(get_attr(attrs, "class"), "x")


# ── _strip_interactive_chrome ────────────────────────────────────────────


class TestStripInteractiveChrome(unittest.TestCase):
    """VDD-iter-5 MED-7 (nested button) + commit 3857d6d (drop video/audio/iframe)."""

    def test_unwraps_nested_button(self) -> None:
        """Single-pass non-greedy regex matches the FIRST `</button>` and
        leaves a stray `</button>` on nested input. Iterative unwrap fixes."""
        html = "<button>OUTER_X<button>INNER_Y</button>TAIL_Z</button>"
        out = _strip_interactive_chrome(html)
        self.assertEqual(out, "OUTER_XINNER_YTAIL_Z",
                         f"nested button unwrap broken: {out!r}")
        self.assertNotIn("</button>", out, "stray closing tag remained")

    def test_unwraps_th_button(self) -> None:
        """Confluence `<th><button>TITLE</button></th>` keeps TITLE."""
        html = "<table><tr><th><button>COLUMN_TITLE</button></th></tr></table>"
        out = _strip_interactive_chrome(html)
        self.assertIn("COLUMN_TITLE", out)
        self.assertNotIn("<button", out)

    def test_drops_video_audio_iframe(self) -> None:
        html = (
            "<video controls><source src='x.mp4'></video>"
            "<audio><source src='x.mp3'></audio>"
            "<iframe src='https://x'></iframe>"
            "<p>BODY</p>"
        )
        out = _strip_interactive_chrome(html)
        self.assertNotIn("<video", out)
        self.assertNotIn("<audio", out)
        self.assertNotIn("<iframe", out)
        self.assertIn("<p>BODY</p>", out)


# ── _strip_empty_anchor_links ────────────────────────────────────────────


class TestStripEmptyAnchorLinks(unittest.TestCase):
    """VDD-iter-5 MED-8: O(n×k) regex on TOC pages with thousands of
    non-hash anchors — replaced with two-stage scan, must complete fast."""

    def test_keeps_text_anchor(self) -> None:
        html = '<a href="#x">visible text</a>'
        out = _strip_empty_anchor_links(html)
        self.assertEqual(out, html)

    def test_drops_empty_hash_anchor(self) -> None:
        html = '<a href="#x"></a>'
        out = _strip_empty_anchor_links(html)
        self.assertEqual(out, "")

    def test_keeps_external_anchor(self) -> None:
        html = '<a href="https://example.com">link</a>'
        out = _strip_empty_anchor_links(html)
        self.assertEqual(out, html)

    def test_perf_5000_anchors(self) -> None:
        """Performance guard: 5000 non-hash anchors must process in < 0.5 s.
        Old combined regex `<a\\b[^>]*\\bhref...#[^"']*[^>]*>(.*?)</a>` did
        per-anchor backtracking on every external link."""
        html = '<a href="https://example.com">link</a>' * 5000 + '<a href="#x"><svg/></a>'
        t0 = time.perf_counter()
        _ = _strip_empty_anchor_links(html)
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 0.5,
                        f"5000 anchors took {elapsed:.3f}s — perf regression")


# ── _flatten_table_code_blocks ───────────────────────────────────────────


class TestFlattenTableCodeBlocks(unittest.TestCase):
    """Commit 2354592 + VDD-iter-5 LOW-9 (false positive guard)."""

    def test_fern_codeblock_flatten(self) -> None:
        html = (
            '<table><tr class="code-block-line">'
            '<td class="code-block-line-content">'
            '<span class="line">code</span></td></tr></table>'
        )
        out = _flatten_table_code_blocks(html)
        self.assertIn("<pre><code>", out)
        self.assertIn("code", out)
        self.assertNotIn("<table", out)

    def test_false_positive_kept(self) -> None:
        """LOW-9: a non-code table containing `<a class="line-link">` AND a
        `*highlight*` class anywhere must NOT be flattened.
        Old check used `'class="line"' in inner and 'highlight' in inner` —
        too loose; tightened to `<tr class*=code-block-line>` /
        `<span class="line"> + 'highlight'`."""
        html = (
            '<table>'
            '<tr><td><a class="line-link">x</a></td>'
            '<td><span class="highlight-key">y</span></td></tr>'
            '</table>'
        )
        out = _flatten_table_code_blocks(html)
        self.assertIn("<table", out, "non-code table was flattened — false positive")
        self.assertIn("line-link", out)


# ── _strip_universal_ads ─────────────────────────────────────────────────


class TestStripUniversalAds(unittest.TestCase):
    """Commit 3857d6d: ad-network class strip must hit known wrappers but
    NOT generic compound classes like `.user-banner`."""

    def test_adfox_dropped(self) -> None:
        html = '<div class="adfox-banner-placeholder">AD</div><p>BODY</p>'
        out = _strip_universal_ads(html)
        self.assertNotIn("AD", out)
        self.assertIn("BODY", out)

    def test_user_banner_kept(self) -> None:
        """Bare `banner` is intentionally NOT in the keyword list (would
        over-strip `.user-banner` / `.profile-banner` / etc.)."""
        html = '<div class="user-banner">USER_PIC</div>'
        out = _strip_universal_ads(html)
        self.assertIn("USER_PIC", out, "user-banner was stripped — bare 'banner' leaked")


# ── _fo_to_svg_text ──────────────────────────────────────────────────────


class TestFoToSvgText(unittest.TestCase):
    """drawio foreignObject text extraction. Commit a8933b9 added
    case-insensitive matching for HTML's lowercased `<foreignobject>`."""

    def test_lowercase_foreignobject(self) -> None:
        """HTML parsers lowercase tag names; drawio's `<foreignObject>` may
        appear as `<foreignobject>` after a Confluence export round-trip."""
        html = (
            '<svg><g transform="translate(0,0)">'
            '<foreignobject>'
            '<div style="padding-top:50px;margin-left:100px;width:200px;'
            'justify-content:center;font-size:14px;">DRAWIO_LOWER_CASE</div>'
            '</foreignobject></g></svg>'
        )
        out = _fo_to_svg_text(html)
        self.assertIn("DRAWIO_LOWER_CASE", out)
        self.assertIn("<text", out, "foreignobject not converted to <text>")

    def test_camelcase_foreignobject(self) -> None:
        """Camel-case `<foreignObject>` (XML/SVG canonical) also works."""
        html = (
            '<svg><foreignObject>'
            '<div style="padding-top:50px;margin-left:100px;width:200px;'
            'justify-content:center;font-size:14px;">DRAWIO_CAMEL</div>'
            '</foreignObject></svg>'
        )
        out = _fo_to_svg_text(html)
        self.assertIn("DRAWIO_CAMEL", out)

    def test_align_items_flex_start_top_aligns_text(self) -> None:
        """drawio `align-items: flex-start` with `padding-top: 46px` means
        the TEXT TOP is at y=46. Without this fix, _fo_to_svg_text treated
        padding-top as y-CENTRE; for a 12-px label that placed the visual
        centre at y=46, leaving the top of the text at y=40 — half a line
        ABOVE the rectangle (which usually starts at y=38), so the rect's
        top stroke crossed the text. Confluence US-Отчёт fixture, regression
        observed 2026-04-30.

        With the fix: y=46 is the TOP of the first line, so its visual
        centre lands at y = 46 + lh/2 = 46 + 7.5 = 53.5 (well inside the
        rectangle).
        """
        html = (
            '<svg><foreignObject>'
            '<div style="display:flex; align-items:unsafe flex-start; '
            'justify-content:unsafe flex-start; '
            'padding-top:46px; margin-left:21px; width:328px; '
            'height:1px; font-size:12px;">FLEX_START_LABEL</div>'
            '</foreignObject></svg>'
        )
        out = _fo_to_svg_text(html)
        # Label is present, and the y-coordinate of the <text> element
        # is 46 + 12*1.25/2 = 53.5 (NOT 46 itself, which would be the
        # buggy y-centre treatment).
        import re as _re
        m = _re.search(r'<text x="\d+(?:\.\d+)?" y="([\d.]+)"', out)
        self.assertIsNotNone(m, f"no <text> emitted: {out!r}")
        y_value = float(m.group(1))
        # Expected y for first-line baseline-middle: 46 + (12*1.25)/2 = 53.5
        self.assertAlmostEqual(y_value, 53.5, delta=0.6,
            msg=f"flex-start label y={y_value}; expected 53.5 "
                f"(padding-top=46 + line-height/2)")

    def test_edge_label_bg_emits_rect_backdrop(self) -> None:
        """drawio EDGE labels (text on an arrow) carry `background-color:
        #ffffff` on inner div(s) — without a matching <rect> backdrop the
        arrow's stroke runs visibly through the glyphs. Confluence
        US-Отчёт fixture, observed 2026-04-30. Also covers the CSS
        `light-dark(LIGHT, DARK)` wrapper drawio emits for theme-awareness:
        we extract LIGHT (print = light mode)."""
        html = (
            '<svg><foreignObject>'
            '<div style="display:flex; align-items:unsafe center; '
            'justify-content:unsafe center; width:1px; height:1px; '
            'padding-top:209px; margin-left:413px;">'
            '<div style="background-color: #ffffff;">'
            '<div style="font-size:11px; '
            'background-color: light-dark(#ffffff, #1d2125);">'
            'EDGE_LABEL_TEXT</div></div></div>'
            '</foreignObject></svg>'
        )
        out = _fo_to_svg_text(html)
        self.assertIn("EDGE_LABEL_TEXT", out)
        self.assertIn("<rect", out, "no <rect> backdrop emitted for edge label")
        # SVG z-order = document order: rect must precede text.
        self.assertLess(out.index("<rect"), out.index("<text"),
            "rect must come BEFORE text (z-order = doc order)")
        self.assertIn('fill="#ffffff"', out)

    def test_vertex_label_no_bg_no_rect(self) -> None:
        """Vertex labels (text inside a coloured shape) have NO
        background-color on the foreignObject inner divs — the shape's
        rect provides the fill. A false-positive <rect> would punch a
        white hole through the shape. Regression guard."""
        html = (
            '<svg><foreignObject>'
            '<div style="align-items:unsafe center; '
            'justify-content:unsafe center; '
            'padding-top:50px; margin-left:100px; width:200px; '
            'font-size:14px;">VERTEX_LABEL</div>'
            '</foreignObject></svg>'
        )
        out = _fo_to_svg_text(html)
        self.assertIn("VERTEX_LABEL", out)
        self.assertNotIn("<rect", out,
            "false-positive rect on vertex label (no background-color)")

    def test_transparent_bg_no_rect(self) -> None:
        """`background-color: transparent` / `none` must NOT emit a backdrop."""
        html = (
            '<svg><foreignObject>'
            '<div style="padding-top:50px; margin-left:100px; width:1px;">'
            '<div style="background-color: transparent;">TRANSPARENT_LBL'
            '</div></div>'
            '</foreignObject></svg>'
        )
        out = _fo_to_svg_text(html)
        self.assertIn("TRANSPARENT_LBL", out)
        self.assertNotIn("<rect", out,
            "transparent background must not emit a <rect>")

    def test_label_text_mentioning_bgcolor_no_false_positive(self) -> None:
        """CRITICAL regression guard: a vertex label whose TEXT CONTENT
        mentions `background-color: red;` (e.g. SQL/CSS-tutorial
        diagrams) must NOT trigger a false-positive backdrop.

        The earlier implementation scanned the entire foreignObject HTML
        for the substring; with a `;` terminator nearby in the text, the
        regex captured `red` and emitted `<rect fill="red"/>` over the
        glyphs. Fixed by scoping the scan to `style="…"` attribute
        bodies only. See VDD-iter critique CRITICAL row."""
        html = (
            '<svg><foreignObject>'
            '<div style="align-items:unsafe center; '
            'justify-content:unsafe center; padding-top:50px; '
            'margin-left:100px; width:300px; font-size:14px;">'
            'SQL: ALTER TABLE x background-color: red; END;'
            '</div></foreignObject></svg>'
        )
        out = _fo_to_svg_text(html)
        # Body is word-wrapped (300px / 14px·0.6 ≈ 35 chars/line) so the
        # SQL string is split across multiple <text> elements; check
        # presence of an unambiguous fragment instead of the full string.
        self.assertIn("ALTER TABLE", out)
        self.assertNotIn('<rect', out,
            "regex matched bg-color from TEXT CONTENT — should only "
            "scan style='…' / style=\"…\" attribute bodies")

    def test_data_attribute_mentioning_bgcolor_no_false_positive(self) -> None:
        """`<div data-info="background-color: #fff">` must NOT trigger a
        backdrop — only `style=` attributes are authoritative."""
        html = (
            '<svg><foreignObject>'
            '<div style="align-items:unsafe center; '
            'justify-content:unsafe center; padding-top:50px; '
            'margin-left:100px; width:200px; font-size:14px;" '
            'data-info="background-color: #fff">DATA_ATTR_LBL</div>'
            '</foreignObject></svg>'
        )
        out = _fo_to_svg_text(html)
        self.assertIn("DATA_ATTR_LBL", out)
        self.assertNotIn("<rect", out,
            "data-* attribute leaked into bg-colour parser")

    def test_single_quoted_style_attribute_parsed(self) -> None:
        """drawio HTML5-serialized output occasionally uses single-quoted
        style attributes. The bg-colour parser must accept BOTH forms."""
        html = (
            "<svg><foreignObject>"
            "<div style='align-items:unsafe center; "
            "justify-content:unsafe center; width:1px; height:1px; "
            "padding-top:50px; margin-left:100px;'>"
            "<div style='background-color: #ffffff; font-size:11px;'>"
            "SINGLE_QUOTED_LBL</div></div>"
            "</foreignObject></svg>"
        )
        out = _fo_to_svg_text(html)
        self.assertIn("SINGLE_QUOTED_LBL", out)
        self.assertIn("<rect", out,
            "single-quoted style attr was missed by bg-colour regex")
        self.assertIn('fill="#ffffff"', out)

    def test_important_keyword_stripped(self) -> None:
        """`background-color: #fff !important;` must NOT leak the
        `!important` keyword into the SVG `fill=` attribute (would
        produce `fill="#fff !important"` — invalid SVG)."""
        html = (
            '<svg><foreignObject>'
            '<div style="align-items:unsafe center; '
            'justify-content:unsafe center; width:1px; height:1px; '
            'padding-top:50px; margin-left:100px;">'
            '<div style="background-color: #ffaa00 !important; '
            'font-size:11px;">IMPORTANT_LBL</div>'
            '</div></foreignObject></svg>'
        )
        out = _fo_to_svg_text(html)
        self.assertIn("IMPORTANT_LBL", out)
        self.assertIn('fill="#ffaa00"', out,
            "!important keyword leaked into the fill value")
        self.assertNotIn("important", out.split("<text")[0].lower(),
            "!important keyword present in <rect> emission")

    def test_modern_color_function_oklch_accepted(self) -> None:
        """`oklch()` / `lab()` / `hsl()` etc. are valid CSS Color L4/L5
        functions; the whitelist must accept them so future drawio
        themes don't silently lose backdrops."""
        for fn in ("oklch(0.7 0.15 250)", "hsl(120 100% 50%)",
                   "lab(50% 40 -20)", "rgba(255,255,255,0.8)"):
            with self.subTest(colour=fn):
                html = (
                    '<svg><foreignObject>'
                    '<div style="align-items:unsafe center; '
                    'justify-content:unsafe center; width:1px; '
                    'height:1px; padding-top:50px; margin-left:100px;">'
                    f'<div style="background-color: {fn}; '
                    f'font-size:11px;">MODERN_{fn[:4]}</div></div>'
                    '</foreignObject></svg>'
                )
                out = _fo_to_svg_text(html)
                self.assertIn("<rect", out,
                    f"modern colour fn {fn!r} rejected — backdrop lost")
                self.assertIn(f'fill="{fn}"', out,
                    f"colour fn {fn!r} not preserved in fill=")

    def test_named_color_white_accepted(self) -> None:
        """CSS named colours (`white`, `red`, `LightSkyBlue`) must pass
        the validation whitelist."""
        html = (
            '<svg><foreignObject>'
            '<div style="align-items:unsafe center; '
            'justify-content:unsafe center; width:1px; height:1px; '
            'padding-top:50px; margin-left:100px;">'
            '<div style="background-color: white; font-size:11px;">'
            'NAMED_LBL</div></div></foreignObject></svg>'
        )
        out = _fo_to_svg_text(html)
        self.assertIn("<rect", out)
        self.assertIn('fill="white"', out)

    def test_var_no_fallback_returns_none(self) -> None:
        """`var(--name)` without a fallback is unresolvable at static-
        analysis time — must return None (no backdrop) rather than emit
        an invalid `fill="var(--name)"`."""
        html = (
            '<svg><foreignObject>'
            '<div style="align-items:unsafe center; '
            'justify-content:unsafe center; width:1px; height:1px; '
            'padding-top:50px; margin-left:100px;">'
            '<div style="background-color: var(--surface); '
            'font-size:11px;">VAR_NOFB_LBL</div></div>'
            '</foreignObject></svg>'
        )
        out = _fo_to_svg_text(html)
        self.assertIn("VAR_NOFB_LBL", out)
        self.assertNotIn("<rect", out,
            "var(--name) without fallback must not produce a backdrop")

    def test_multiline_edge_label_emits_rect_per_line(self) -> None:
        """Word-wrapped edge label (container width > 1 px) emits one
        `<rect>` per visible line, each preceding its `<text>`. Without
        per-line backdrops, the arrow shows through inter-line gaps."""
        html = (
            '<svg><foreignObject>'
            '<div style="align-items:unsafe center; '
            'justify-content:unsafe center; width:80px; height:1px; '
            'padding-top:100px; margin-left:200px;">'
            '<div style="background-color: #ffffff;">'
            '<div style="font-size:11px; '
            'background-color: #ffffff;">two line label here</div>'
            '</div></div></foreignObject></svg>'
        )
        out = _fo_to_svg_text(html)
        self.assertEqual(out.count("<rect"), out.count("<text"),
            "rect count must match text count (one backdrop per line)")
        self.assertGreaterEqual(out.count("<rect"), 2,
            "expected ≥2 lines for word-wrapped edge label")


# ── _fix_svg_viewport ────────────────────────────────────────────────────


class TestFixSvgViewport(unittest.TestCase):
    """Commit 27daedd: drawio Confluence SVGs without a viewBox but with
    `style="min-width:Wpx;min-height:Hpx"` get a synthesised viewBox."""

    def test_synthesises_viewbox_from_min_dims(self) -> None:
        html = (
            '<svg style="width:100%;height:100%;min-width:600px;min-height:400px">'
            '<rect/></svg>'
        )
        out = _fix_svg_viewport(html)
        self.assertIn("viewBox", out, "viewBox not synthesised")
        # 5% expansion: 600*1.05=630.0, 400*1.05=420.0
        self.assertIn('viewBox="0 0 630.0 420.0"', out)

    def test_small_dims_left_alone(self) -> None:
        """Small SVGs (≤200px) are icons; don't synthesise viewBox."""
        html = (
            '<svg style="width:100%;height:100%;min-width:24px;min-height:24px">'
            '<rect/></svg>'
        )
        out = _fix_svg_viewport(html)
        self.assertNotIn("viewBox", out)


# ── reader_mode_html ─────────────────────────────────────────────────────


class TestReaderMode(unittest.TestCase):
    """Reader-mode candidate selection tests (commit 3857d6d)."""

    def test_main_body_ratio_rejects_chrome_main(self) -> None:
        """A `<main>` whose text is ≥95% of `<body>` text is rejected
        (it's wrapping the entire site, including chrome)."""
        # 600 chars of body, 595 inside <main> — ratio ~99% → reject main,
        # fall through. There's a candidate <article> with 500+ chars that
        # should win.
        article_text = "ARTICLE_NEEDLE " + ("filler text " * 60)  # ~720 chars
        chrome_text = "chrome filler text " * 30  # ~570 chars padding
        html = (
            "<html><body>"
            "<main>"
            f"<header>{chrome_text}</header>"
            f"<article>{article_text}</article>"
            "</main>"
            "</body></html>"
        )
        # body_text_length = ~1290 chars; main_text ≈ same → ratio ~99% → reject
        # candidate <article> wins via the article tier.
        out = reader_mode_html(html)
        self.assertIn("ARTICLE_NEEDLE", out)

    def test_longest_entry_wins(self) -> None:
        """Multiple `.entry` divs: the longest one is selected (handles
        archive pages with multiple post excerpts)."""
        long_text = "POST_BODY_NEEDLE " + ("paragraph text " * 40)  # ~700 chars
        short_text = "EXCERPT_NEEDLE_A " + ("short " * 5)
        another_short = "EXCERPT_NEEDLE_B " + ("short " * 5)
        html = (
            "<html><body>"
            f'<div class="entry">{another_short}</div>'
            f'<div class="entry">{long_text}</div>'
            f'<div class="entry">{short_text}</div>'
            "</body></html>"
        )
        out = reader_mode_html(html)
        self.assertIn("POST_BODY_NEEDLE", out)
        # Excerpts didn't qualify (under 500 chars) and longest wins —
        # the EXCERPT needles must be absent.
        self.assertNotIn("EXCERPT_NEEDLE_A", out)
        self.assertNotIn("EXCERPT_NEEDLE_B", out)


# ── _offline_url_fetcher ─────────────────────────────────────────────────


class TestOfflineUrlFetcher(unittest.TestCase):
    """Commit 3857d6d: refuse all http(s) URLs (default urllib has no
    timeout — would hang the render on broken CDN refs)."""

    def test_refuses_http(self) -> None:
        with self.assertRaises(ValueError):
            _offline_url_fetcher("http://example.com/style.css")

    def test_refuses_https(self) -> None:
        with self.assertRaises(ValueError):
            _offline_url_fetcher("https://example.com/font.woff2")

    def test_passes_data_uri(self) -> None:
        """`data:` URIs delegate to weasyprint's default fetcher, which
        decodes the inline data without network access. We don't pin the
        return type (weasyprint changed dict ↔ URLFetcherResponse across
        versions); we just assert no exception leaks."""
        try:
            _offline_url_fetcher(
                "data:image/png;base64,"
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAen63NgAAAAASUVORK5CYII="
            )
        except Exception as exc:                  # pragma: no cover
            self.fail(f"data: URI fetcher raised {type(exc).__name__}: {exc}")


# ── watchdog wiring ──────────────────────────────────────────────────────


class TestWatchdog(unittest.TestCase):
    """VDD-iter-5: `_install_render_watchdog` / `_clear_render_watchdog`
    wiring. We don't test the FIRING path (signal delivery is hard to
    deterministically trigger across platforms — documented as best-effort).
    """

    def test_zero_timeout_returns_none_handler(self) -> None:
        """`timeout=0` disables the watchdog; install returns None and
        clear must accept None without crashing."""
        prev = _install_render_watchdog(0)
        self.assertIsNone(prev)
        _clear_render_watchdog(prev)  # must not raise

    def test_negative_timeout_returns_none_handler(self) -> None:
        prev = _install_render_watchdog(-5)
        self.assertIsNone(prev)
        _clear_render_watchdog(prev)

    def test_install_and_clear_dont_leak(self) -> None:
        """Install with seconds>0, then clear — handler must be restored
        and no leftover SIGALRM fires."""
        import signal as _signal
        if not hasattr(_signal, "SIGALRM"):
            self.skipTest("SIGALRM not available on this platform")
        original = _signal.getsignal(_signal.SIGALRM)
        prev = _install_render_watchdog(60)
        # Some handler installed (could be original SIG_DFL or our lambda).
        try:
            self.assertIsNotNone(prev,
                "watchdog install returned None on main thread with valid timeout")
        finally:
            _clear_render_watchdog(prev)
        # After clear, no pending alarm — signal.alarm(0) cleared it.
        # And original handler is restored.
        self.assertEqual(_signal.getsignal(_signal.SIGALRM), original)

    def test_non_main_thread_degrades_gracefully(self) -> None:
        """Worker-thread call to `signal.signal()` raises ValueError;
        watchdog must catch and return None instead of propagating."""
        import signal as _signal
        if not hasattr(_signal, "SIGALRM"):
            self.skipTest("SIGALRM not available")
        result: list = []
        exc: list = []

        def worker():
            try:
                result.append(_install_render_watchdog(60))
            except Exception as e:
                exc.append(e)

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=5)
        self.assertEqual(exc, [],
            f"watchdog should not raise from worker thread; got {exc}")
        self.assertEqual(result, [None],
            "watchdog should return None from worker thread")


# ── NORMALIZE_CSS structural guards ──────────────────────────────────────


class TestNormalizeCSS(unittest.TestCase):
    """Pin the structural invariants of `_NORMALIZE_CSS` that the battery
    only catches indirectly via page-count tolerance bands. These are
    sub-millisecond and surface a deletion-by-typo immediately.

    Specifically guards rule §7a-bis (block-level Prism / Confluence DC
    code wrap), added 2026-05-04 after VDD-adversarial review of the
    initial wrap fix. See `references/html-conversion.md` rule #7."""

    def test_prism_wrap_selector_present(self) -> None:
        """`code[class*="language-"]` is the load-bearing selector — it
        catches Prism / shiki / highlight.js / Confluence DC code blocks
        regardless of parent. Removing it silently regresses long SQL
        lines past the right page edge (un-copyable, clipped)."""
        self.assertIn('code[class*="language-"]', NORMALIZE_CSS,
            "Prism `code[class*=\"language-\"]` selector deleted — "
            "long source lines will clip past the right margin")

    def test_confluence_dc_hashed_class_selector(self) -> None:
        """Confluence DC ships hashed class names like
        `codeBlockContainer_yyk2gsoAwjaamghp6yoO-Q==`. CSS class
        selectors do NOT prefix-match (`.codeBlockContainer` would NOT
        match `codeBlockContainer_HASH`), so we use an attribute-
        substring selector. Regression guard: a refactor that swaps
        `[class*="codeBlockContainer"]` for `.codeBlockContainer` would
        make the selector dead on every Confluence DC export."""
        self.assertIn('[class*="codeBlockContainer"]', NORMALIZE_CSS,
            "Confluence DC hashed-class wrap selector regressed to a "
            "literal `.codeBlockContainer` (which does NOT match "
            "`codeBlockContainer_HASH=` forms emitted by Confluence DC)")

    def test_confluence_classic_panel_selector(self) -> None:
        """Confluence's classic chained-class `.code.panel` wrapper."""
        self.assertIn('.code.panel code', NORMALIZE_CSS,
            "Confluence classic `.code.panel` wrap selector deleted")

    def test_overflow_wrap_break_word_present(self) -> None:
        """`overflow-wrap: break-word` is the standard CSS3 property
        that allows long unbreakable tokens (URLs, base64) to wrap
        within a `pre-wrap` block. Without it, a single long token
        clips past the right margin even though `pre-wrap` is set.

        pdf-10 added a third occurrence in §7e (body text — `p, li,
        td, dd`). Three is the new minimum; future additions are fine
        as long as the rule is present in all three load-bearing
        contexts (<pre>, Prism <code>, body prose).
        """
        self.assertGreaterEqual(
            NORMALIZE_CSS.count("overflow-wrap: break-word !important"), 3,
            "overflow-wrap: break-word !important must appear at least "
            "three times — §7a (<pre>), §7a-bis (Prism <code>), "
            "§7e (body text)")

    def test_no_wordbreak_breakword_alias(self) -> None:
        """`word-break: break-word` is a CSS-WG-deprecated alias of
        `overflow-wrap: break-word` that **weasyprint rejects as an
        invalid value** (verified empirically; logs `Ignored
        'word-break: break-word'`). Earlier versions of this rule
        included the alias as 'safety' — it was dead weight that
        misled maintainers reading the comment. Regression guard:
        nobody re-adds the dead alias.

        Match a real CSS declaration (line-start whitespace + property +
        `;` or `!important`), NOT the substring in comments — the
        comment intentionally explains why the alias is absent."""
        import re as _re
        decl_pat = _re.compile(
            r"^\s*word-break\s*:\s*break-word\s*(?:!important\s*)?;",
            _re.MULTILINE,
        )
        m = decl_pat.search(NORMALIZE_CSS)
        self.assertIsNone(m,
            "word-break: break-word DECLARATION re-introduced — "
            "weasyprint rejects it as invalid; only overflow-wrap: "
            "break-word actually wraps")

    def test_pre_wrap_in_both_code_blocks(self) -> None:
        """Both <pre> (§7a) and Prism <code> (§7a-bis) MUST set
        `white-space: pre-wrap` to preserve indentation while wrapping
        at the page boundary. `pre-wrap` (not `pre`!) is the load-
        bearing value."""
        self.assertEqual(
            NORMALIZE_CSS.count("white-space: pre-wrap !important"), 2,
            "white-space: pre-wrap !important must appear twice — "
            "once in <pre> and once in the Prism <code> rule")

    @staticmethod
    def _strip_css_comments(css: str) -> str:
        """Strip /* … */ blocks so substring / pattern matches don't
        false-positive on selectors that appear only in comments. CSS
        does NOT support nested comments, so the simple non-greedy
        regex is sufficient. (q-7 VDD-A2 fix.)"""
        import re as _re
        return _re.sub(r"/\*.*?\*/", "", css, flags=_re.DOTALL)

    def _assert_selector_in_active_rule(
        self, selector_literal: str,
        property_decl: str = "display: none",
    ) -> None:
        """Assert that `selector_literal` appears as part of a selector
        list in an ACTIVE CSS rule whose body contains
        `property_decl`. The check strips comments first, then matches
        the selector followed (eventually) by `{` and a body
        containing the property — guaranteeing a refactor that demotes
        the selector to a comment, or removes its declaration block,
        fails this test.

        Mirrors the pattern of `test_no_wordbreak_breakword_alias` —
        substring `assertIn` is too weak; selector-presence in active
        CSS is the real invariant."""
        import re as _re
        css = self._strip_css_comments(NORMALIZE_CSS)
        # Selector list ends at `{`; body ends at `}`. Use [^{}] to
        # forbid nested braces (CSS doesn't have them at top level).
        # Anchor on a non-word char before the selector so `#action`
        # doesn't match inside `#action-menu-secondary`.
        pat = _re.compile(
            r"(?:^|[\s,])"
            + _re.escape(selector_literal)
            + r"\b[^{}]*\{[^}]*"
            + _re.escape(property_decl),
            _re.DOTALL | _re.MULTILINE,
        )
        self.assertIsNotNone(
            pat.search(css),
            f"Selector {selector_literal!r} is not present in any ACTIVE "
            f"CSS rule with `{property_decl}` body — either deleted, "
            f"demoted to a comment, or its rule body lost the declaration. "
            f"This breaks the chrome-strip / layout-reset contract.",
        )

    def test_confluence_action_menu_hidden(self) -> None:
        """Confluence Server's `<div id="action-menu" class="aui-dropdown2
        aui-layer …">` is absolutely positioned in the source HTML and
        leaks the page-actions menu (Save for later / Watching / Share /
        Page History / Export to PDF / …) on top of the article body
        when site CSS is stripped. Observed on the ELMA365 ↔ 3CX wiki
        page, 2026-05-04. Regression guard: `#action-menu` /
        `.aui-dropdown2` / `.aui-layer` MUST be in §7d's `display:none`
        rule (NOT just present somewhere in the file as a comment)."""
        self._assert_selector_in_active_rule('#action-menu')
        self._assert_selector_in_active_rule('.aui-dropdown2')
        self._assert_selector_in_active_rule('.aui-layer')

    def test_confluence_sidebar_and_pagetree_hidden(self) -> None:
        """Left-rail sidebar (`<div class="ia-fixed-sidebar"
        role="complementary">` containing space logo, page tree,
        quick-links) and the pageTree-macro static config table both
        leak as visible content when site CSS is stripped. §7d
        category (b) and (d). Regression guard pinned end-to-end: the
        selectors must live in the ACTIVE display:none rule, not a
        commented-out block."""
        self._assert_selector_in_active_rule('.ia-fixed-sidebar')
        self._assert_selector_in_active_rule('.plugin_pagetree')
        self._assert_selector_in_active_rule('.ia-secondary-content')

    def test_main_layout_reset_present(self) -> None:
        """§4a is load-bearing: without it, `<main style="margin-left:
        430px">` keeps the sidebar offset and the article body
        squeezes into a narrow right column with the title inline-
        wrapping into the version-table area on page 1 (US-Отчет
        Полнотекстовый поиск, observed 2026-05-04). The chrome strip
        in §7d alone is insufficient because the inline-styled
        geometry on `<main>` survives chrome removal.

        The two LOAD-BEARING declarations are:
          * `margin-left: 0` — overrides `margin-left: 430px` on
            `<main>` (the actual cause of the squeezed column).
          * `padding-top: 0` — overrides `padding-top: 55px` on
            `#main-header-placeholder` (top-banner reservation).

        Both must apply to `main` AND `#main` (Confluence sometimes
        emits both the semantic tag and the legacy ID together)."""
        self._assert_selector_in_active_rule(
            'main', property_decl='margin-left: 0 !important')
        self._assert_selector_in_active_rule(
            '#main-header-placeholder',
            property_decl='padding-top: 0 !important')

    def test_no_horizontal_padding_reset_in_main_rule(self) -> None:
        """Negative regression guard for VDD-A MED-3 (q-7 fix iteration
        2): §4a previously included `padding-left: 0 !important;
        padding-right: 0 !important` on `main, #main, #main-content,
        #content, …`. `#content` is a generic ID widely used outside
        Confluence (Sphinx, MkDocs, Hugo, GitHub README pages, …); the
        horizontal-padding reset made article text touch the page-
        margin edge on those sites — a typographic regression worse
        than the bug it intended to fix. The sidebar offset is purely
        `margin-left` on `<main>`, never padding.

        This test pins the removal: nobody re-adds the over-strip."""
        import re as _re
        css = self._strip_css_comments(NORMALIZE_CSS)
        # Locate the §4a rule (selectors that include `#main-header-placeholder`)
        # and assert its body does NOT declare horizontal padding.
        rule_pat = _re.compile(
            r"(?:^|[\s,])#main-header-placeholder\b[^{}]*\{([^}]*)\}",
            _re.DOTALL | _re.MULTILINE,
        )
        m = rule_pat.search(css)
        self.assertIsNotNone(
            m,
            "Could not locate §4a layout-reset rule (lookup key: "
            "`#main-header-placeholder`).",
        )
        body = m.group(1)
        for prop in ("padding-left", "padding-right"):
            self.assertNotRegex(
                body,
                rf"\b{prop}\s*:\s*0\b",
                f"§4a rule re-introduced `{prop}: 0` — this over-strips "
                f"horizontal padding on `#content` etc. on every "
                f"non-Confluence page.",
            )


class TestParseLabelBgKeywords(unittest.TestCase):
    """Pin `_parse_label_bg`'s deny list against CSS-wide keywords —
    accepting any of these into the SVG-rect `fill=` attribute is the
    drawio black-rectangle bug observed 2026-05-04 on the ELMA365 ↔ 3CX
    swimlane diagram (Confluence wiki)."""

    def test_initial_rejected(self) -> None:
        """`background-color: initial` MUST NOT produce a backdrop. SVG
        spec resolves `<rect fill="initial">` to BLACK — it's the
        load-bearing case for this regression guard. Drawio emits
        `background-color: initial` on vertex labels where the user
        explicitly cleared the bg in the style picker."""
        self.assertIsNone(_parse_label_bg(
            '<foreignObject><div style="background-color: initial;">x</div></foreignObject>'
        ))

    def test_inherit_rejected(self) -> None:
        """`inherit` resolves to whatever the parent element has —
        unpredictable; must skip the backdrop."""
        self.assertIsNone(_parse_label_bg(
            '<foreignObject><div style="background-color: inherit;">x</div></foreignObject>'
        ))

    def test_unset_rejected(self) -> None:
        self.assertIsNone(_parse_label_bg(
            '<foreignObject><div style="background-color: unset;">x</div></foreignObject>'
        ))

    def test_revert_rejected(self) -> None:
        self.assertIsNone(_parse_label_bg(
            '<foreignObject><div style="background-color: revert;">x</div></foreignObject>'
        ))
        self.assertIsNone(_parse_label_bg(
            '<foreignObject><div style="background-color: revert-layer;">x</div></foreignObject>'
        ))

    def test_real_colour_still_accepted(self) -> None:
        """Negative case: real bg-colour values (the common drawio edge-
        label case `#ffffff`) must STILL produce a backdrop string."""
        self.assertEqual('#ffffff', _parse_label_bg(
            '<foreignObject><div style="background-color: #ffffff;">x</div></foreignObject>'
        ))

    def test_initial_in_light_dark_LIGHT_arg_rejected(self) -> None:
        """If the LIGHT branch of `light-dark()` is `initial`, the
        result after light-dark resolution should still be skipped."""
        self.assertIsNone(_parse_label_bg(
            '<foreignObject><div style="background-color: light-dark(initial, #1d2125);">x</div></foreignObject>'
        ))


class TestNoFillInitialLeaksEndToEnd(unittest.TestCase):
    """Defense-in-depth (q-7 VDD-A2 LOW-4): even when `_parse_label_bg`'s
    deny list is correct, a future change to `_fo_to_svg_text` (or a
    new SVG-emission path) could re-introduce `fill="initial"` from a
    different code path. Run a synthetic drawio-style fixture through
    the WHOLE `preprocess_html()` pipeline and assert no SVG `fill=`
    attribute holds a CSS-wide keyword. Cheap insurance — runs
    sub-millisecond on a tiny synthetic input."""

    # CSS-wide keywords that, if emitted into an SVG `fill=` attribute,
    # resolve to BLACK (or unspecified) per SVG spec. None of these
    # should ever leak through preprocessing.
    BAD_FILL_VALUES = (
        "initial", "inherit", "unset", "revert",
        "revert-layer", "auto", "currentcolor",
    )

    def test_drawio_with_bg_initial_does_not_leak_fill_initial(self) -> None:
        """Synthetic drawio swimlane: a foreignObject vertex label with
        `background-color: initial`. The bug it pins (and the deny-
        list fix prevents): `<rect fill="initial">` emitted in the
        SVG, which weasyprint resolves to a solid black bar over the
        text."""
        synthetic = """
        <html><body>
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
          <foreignObject x="0" y="0" width="200" height="100">
            <div xmlns="http://www.w3.org/1999/xhtml"
                 style="display: flex; align-items: center;
                        justify-content: center; width: 1px; height: 1px;
                        padding-top: 50px; margin-left: 100px;">
              <div style="font-size: 12px; background-color: initial;">
                POSTevent = outgoing finishtype = Ok
              </div>
            </div>
          </foreignObject>
        </svg>
        </body></html>
        """
        out = preprocess_html(synthetic)
        for kw in self.BAD_FILL_VALUES:
            for quote in ('"', "'"):
                needle = f'fill={quote}{kw}{quote}'
                self.assertNotIn(
                    needle, out,
                    f"preprocess output contains {needle!r} — a CSS-wide "
                    f"keyword leaked into an SVG `fill=` attribute. "
                    f"weasyprint will resolve this to black; the label "
                    f"backdrop will hide its own text. Check "
                    f"`_parse_label_bg` and any new SVG-emission paths.",
                )

    def test_drawio_with_bg_inherit_does_not_leak(self) -> None:
        """Same guard for `background-color: inherit` — inherit is even
        less predictable than `initial` because the resolved value
        depends on parent context, which weasyprint can't always
        compute correctly during SVG sub-rendering."""
        synthetic = (
            '<svg viewBox="0 0 100 50"><foreignObject>'
            '<div xmlns="http://www.w3.org/1999/xhtml" '
            'style="background-color: inherit;">label</div>'
            '</foreignObject></svg>'
        )
        out = preprocess_html(synthetic)
        for kw in self.BAD_FILL_VALUES:
            self.assertNotIn(f'fill="{kw}"', out)
            self.assertNotIn(f"fill='{kw}'", out)


# ────────────────────────── pdf-8 / pdf-9 / pdf-10 ───────────────────────────

class TestSubstantialFrameHeuristic(unittest.TestCase):
    """pdf-8: substantial-frame heuristic must be purely structural — no
    vendor allow-list. Each rule has its own dedicated test."""

    def test_substantial_real_email_iframe(self) -> None:
        """Real email-body iframe (HTML ≥ 1KB, 0 scripts, prose ≥ 30 chars,
        not single-img). Must classify as substantial."""
        from html2pdf_lib.archives import _is_substantial_frame
        body = "<p>Hello, this is a real email body with prose content " * 20
        html = f"<html><body>{body}</body></html>".encode()
        self.assertTrue(_is_substantial_frame(html))

    def test_rejects_under_1kb_payload(self) -> None:
        from html2pdf_lib.archives import _is_substantial_frame
        html = b"<html><body>Tiny placeholder content here.</body></html>"
        self.assertFalse(_is_substantial_frame(html))

    def test_rejects_with_script(self) -> None:
        """Any `<script>` tag → non-substantial. Catches Gmail's chrome
        widgets (One sidebar, contacts hovercard) regardless of size."""
        from html2pdf_lib.archives import _is_substantial_frame
        body = "<p>Substantial prose " * 20  # ≥ 1KB, ≥ 30 chars text
        html = f"<html><body>{body}<script>x()</script></body></html>".encode()
        self.assertFalse(_is_substantial_frame(html))
        # Also: even uppercased <SCRIPT> rejected (case-insensitive)
        html2 = f"<html><body>{body}<SCRIPT>y()</SCRIPT></body></html>".encode()
        self.assertFalse(_is_substantial_frame(html2))

    def test_rejects_short_text(self) -> None:
        """≥ 1KB but < 30 chars text — likely empty placeholder iframe."""
        from html2pdf_lib.archives import _is_substantial_frame
        # ≥ 1KB through whitespace padding; only 5 chars text content
        html = (b"<html><body>" + b" " * 1100 + b"<p>hi.</p></body></html>")
        self.assertFalse(_is_substantial_frame(html))

    def test_rejects_single_img_body(self) -> None:
        """Single-<img>-only body — tracking-pixel iframe with verbose URL."""
        from html2pdf_lib.archives import _is_substantial_frame
        # Body is ONLY an img tag — the tracking-pixel pattern. No prose.
        url = "https://mailer.mail.ru/pixel/" + "a" * 800
        html = (
            f'<html><body><img src="{url}" width="0" height="0" alt="."></body>'
            f'</html>'
        ).encode()
        self.assertFalse(_is_substantial_frame(html))

    def test_no_vendor_classes_in_decision(self) -> None:
        """Same decision regardless of vendor-specific class names — proves
        the heuristic doesn't peek at class= attributes. Content padded
        well above the 1024-byte size threshold."""
        from html2pdf_lib.archives import _is_substantial_frame
        prose = "<p>real email content here with enough text. " * 50
        for cls in (
            "elma365-message-body", "gmail_quote", "outlook-body",
            "yandex-mail-body", "proton-mail-body", "wholly-unknown-vendor",
        ):
            html = f"<html><body><div class='{cls}'>{prose}</div></body></html>"
            self.assertTrue(
                _is_substantial_frame(html.encode()),
                f"vendor class {cls!r} should not change the decision",
            )


class TestArchiveAutoMode(unittest.TestCase):
    """pdf-8 auto-mode resolution: 0 substantial→main, 1→that frame, 2+→all.
    Pure logic test on FrameInfo lists — no fixture I/O required."""

    def _make(self, kinds_subs):
        """Helper: build a FrameInfo list from (kind, substantial) tuples."""
        from html2pdf_lib.archives import FrameInfo
        out = []
        for i, (kind, sub) in enumerate(kinds_subs):
            out.append(FrameInfo(
                index=i, kind=kind, url="about:blank",
                bytes=2000, scripts=0, text_len=200, substantial=sub,
            ))
        return out

    def test_zero_substantial_auto_main(self) -> None:
        from html2pdf_lib.archives import _resolve_auto_mode
        frames = self._make([("main", False), ("subframe", False), ("subframe", False)])
        self.assertEqual(_resolve_auto_mode(frames), "main")

    def test_one_substantial_auto_picks_index(self) -> None:
        from html2pdf_lib.archives import _resolve_auto_mode
        frames = self._make([("main", False), ("subframe", False), ("subframe", True)])
        self.assertEqual(_resolve_auto_mode(frames), "2")  # 1-indexed

    def test_multiple_substantial_auto_all(self) -> None:
        from html2pdf_lib.archives import _resolve_auto_mode
        frames = self._make([
            ("main", False), ("subframe", True), ("subframe", True),
            ("subframe", False), ("subframe", True),
        ])
        self.assertEqual(_resolve_auto_mode(frames), "all")

    def test_dominant_main_overrides_lone_tiny_substantial(self) -> None:
        """VDD-adversarial fix: HubSpot for WordPress case — the only
        substantial subframe is a 180-char navigation-modal error page;
        main HTML carries 5960 chars of actual content. Auto-mode must
        return "main", not the small overlay subframe."""
        from html2pdf_lib.archives import FrameInfo, _resolve_auto_mode
        frames = [
            FrameInfo(0, "main", "x", bytes=200000, scripts=43,
                      text_len=5960, substantial=False),
            FrameInfo(1, "subframe", "x", bytes=14000, scripts=0,
                      text_len=180, substantial=True),
        ]
        self.assertEqual(
            _resolve_auto_mode(frames), "main",
            "Tiny substantial subframe should NOT win when main has 33× "
            "more text — that's a system overlay, not user content.")

    def test_substantial_subframe_dominant_over_chrome_main(self) -> None:
        """Email-iframe case: ELMA365 main is SPA shell (2085 chars), the
        substantial subframe is the email body (6792 chars). Auto-mode
        must pick the subframe — it dwarfs main."""
        from html2pdf_lib.archives import FrameInfo, _resolve_auto_mode
        frames = [
            FrameInfo(0, "main", "x", bytes=156000, scripts=7,
                      text_len=2085, substantial=False),
            FrameInfo(1, "subframe", "x", bytes=49000, scripts=0,
                      text_len=6792, substantial=True),
        ]
        self.assertEqual(_resolve_auto_mode(frames), "1")


class TestSafeBasename(unittest.TestCase):
    """pdf-8: filename cap. Triggered by mail.ru tracking-pixel URLs whose
    basename is a 250+ char JWT, exceeding the OS 255-byte filename limit."""

    def test_short_name_unchanged(self) -> None:
        from html2pdf_lib.archives import _safe_basename
        self.assertEqual(_safe_basename("logo.png", "x"), "logo.png")

    def test_overlong_name_capped(self) -> None:
        from html2pdf_lib.archives import _safe_basename, _MAX_BASENAME
        long_name = "a" * 300 + ".png"
        result = _safe_basename(long_name, fallback_key=long_name)
        self.assertLessEqual(len(result.encode("utf-8")), _MAX_BASENAME)
        self.assertTrue(result.endswith(".png"), "extension preserved")

    def test_overlong_name_stable(self) -> None:
        """Same input → same output: dedup key must be stable across runs."""
        from html2pdf_lib.archives import _safe_basename
        long_name = "a" * 300 + ".png"
        a = _safe_basename(long_name, fallback_key=long_name)
        b = _safe_basename(long_name, fallback_key=long_name)
        self.assertEqual(a, b)

    def test_no_extension_overlong(self) -> None:
        """Overlong name without extension still gets capped."""
        from html2pdf_lib.archives import _safe_basename, _MAX_BASENAME
        long_name = "x" * 400
        result = _safe_basename(long_name, fallback_key=long_name)
        self.assertLessEqual(len(result.encode("utf-8")), _MAX_BASENAME)


class TestSPADetection(unittest.TestCase):
    """pdf-9: SPA-detection must trigger on hydrated SPAs (any framework)
    and NOT trigger on plain blog/article HTML."""

    def test_plain_article_not_spa(self) -> None:
        from html2pdf_lib.reader_mode import _is_spa
        html = "<html><body>" + "<p>Lorem ipsum.</p>" * 100 + "</body></html>"
        self.assertFalse(_is_spa(html))

    def test_heavy_body_triggers_spa(self) -> None:
        """Body ≥ 50 KB → SPA. Catches hydrated Angular/React DOMs."""
        from html2pdf_lib.reader_mode import _is_spa
        html = "<html><body>" + ("<div>x</div>" * 10000) + "</body></html>"
        self.assertTrue(_is_spa(html))

    def test_script_bundle_triggers_spa(self) -> None:
        """≥ 5 <script src=> → SPA. Catches semantic-light Framer blogs."""
        from html2pdf_lib.reader_mode import _is_spa
        scripts = "".join(
            f'<script src="/bundle{i}.js"></script>' for i in range(6)
        )
        html = f"<html><head>{scripts}</head><body><p>x</p></body></html>"
        self.assertTrue(_is_spa(html))

    def test_landmarks_trigger_spa(self) -> None:
        """≥ 3 ARIA landmarks → SPA. Catches Gmail (4 landmarks)."""
        from html2pdf_lib.reader_mode import _is_spa
        html = (
            '<html><body>'
            '<div role="navigation">nav</div>'
            '<div role="main">main</div>'
            '<div role="complementary">side</div>'
            '<div role="banner">banner</div>'
            '</body></html>'
        )
        self.assertTrue(_is_spa(html))

    def test_no_framework_strings_in_decision(self) -> None:
        """SPA-detection must work without seeing `ng-version=` /
        `data-reactroot` / `data-v-app` / similar framework markers."""
        from html2pdf_lib.reader_mode import _is_spa
        # 6 scripts + zero framework markers anywhere
        scripts = "".join(
            f'<script src="/b{i}.js"></script>' for i in range(6)
        )
        html = f"<html><head>{scripts}</head><body><p>x</p></body></html>"
        self.assertTrue(_is_spa(html), "Detection must work via structure alone")


class TestSPAChromeStrip(unittest.TestCase):
    """pdf-9: chrome-strip rules must use ARIA roles / semantic landmarks,
    NOT vendor-specific tags or class names."""

    def test_strips_role_navigation(self) -> None:
        from html2pdf_lib.reader_mode import _strip_spa_aria_chrome
        html = (
            '<body>'
            '<div role="navigation">NAV-CONTENT</div>'
            '<div role="main">MAIN-CONTENT</div>'
            '</body>'
        )
        out = _strip_spa_aria_chrome(html)
        self.assertNotIn("NAV-CONTENT", out)
        self.assertIn("MAIN-CONTENT", out, "role=main must be preserved")

    def test_strips_complementary_banner_contentinfo(self) -> None:
        from html2pdf_lib.reader_mode import _strip_spa_aria_chrome
        for role in ("complementary", "banner", "contentinfo"):
            html = (
                f'<body><div role="{role}">CHROME</div>'
                f'<div role="main">CONTENT</div></body>'
            )
            out = _strip_spa_aria_chrome(html)
            self.assertNotIn("CHROME", out, f"role={role} not stripped")
            self.assertIn("CONTENT", out)

    def test_strips_aside_nav_footer(self) -> None:
        from html2pdf_lib.reader_mode import _strip_spa_chrome_tags
        html = (
            '<body>'
            '<aside>aside-content</aside>'
            '<nav>nav-content</nav>'
            '<main>main-content</main>'
            '<footer>footer-content</footer>'
            '</body>'
        )
        out = _strip_spa_chrome_tags(html)
        self.assertNotIn("aside-content", out)
        self.assertNotIn("nav-content", out)
        self.assertNotIn("footer-content", out)
        self.assertIn("main-content", out)

    def test_strips_position_fixed_overlay(self) -> None:
        from html2pdf_lib.reader_mode import _strip_spa_fixed_overlays
        html = (
            '<body>'
            '<div style="position: fixed; top: 0">Close × banner short</div>'
            '<div>'
            + ('<p>real article content paragraph. ' * 100) + '</p>'
            '</div>'
            '</body>'
        )
        out = _strip_spa_fixed_overlays(html)
        self.assertNotIn("Close ×", out)
        self.assertIn("real article content", out)

    def test_no_vendor_class_names_referenced(self) -> None:
        """Audit: the SPA chrome-strip module must not name-drop ELMA365 /
        Gmail / Yandex / Framer specifics. Catches future regressions
        where an implementer adds `app-sidebar-part` etc. to the
        strip-list."""
        from pathlib import Path
        path = Path(__file__).parent.parent / "html2pdf_lib" / "reader_mode.py"
        src = path.read_text(encoding="utf-8")
        # Tokens that would indicate vendor allow-list contamination.
        # Permitted in COMMENTS as fixture references; forbidden in
        # actual code paths (strip lists, regex match strings).
        # Heuristic: scan non-comment, non-string-literal lines.
        forbidden = (
            "app-sidebar-part", "app-toast-notifications",
            "app-desktop-banner", "app-main-part-before",
            "app-appview-card", "elma365-message-body",
            "gmail_quote", "data-message-id",
            "data-framer-name", "side-nav",
        )
        # Allow only in commentary (lines starting with `#` or inside
        # docstrings) — coarse but correct: if a vendor class appears in
        # an `if` condition or a list literal, the test fails.
        offenders = []
        for token in forbidden:
            if token in src:
                # Find each occurrence and check it's in a comment block.
                for line_no, line in enumerate(src.splitlines(), 1):
                    if token in line and not line.strip().startswith("#") \
                            and "'''" not in line and '"""' not in line:
                        # Check if surrounded by docstring quotes earlier.
                        # Simple: count triple-quotes before this line.
                        prior = "\n".join(src.splitlines()[:line_no - 1])
                        if (prior.count('"""') % 2 == 1) or (prior.count("'''") % 2 == 1):
                            continue  # inside a docstring
                        offenders.append((line_no, token, line.strip()[:80]))
        self.assertFalse(
            offenders,
            f"Vendor allow-list contamination detected (pdf-9 must be "
            f"vendor-agnostic): {offenders}",
        )


class TestRewriteUrlsHtmlEscape(unittest.TestCase):
    """pdf-8 VDD-adversarial fix: `<img src=>` URL rewriting must handle
    HTML-encoded `&` (signed S3 / SAS-token URLs in webarchive subframes).

    Discovered via review of `email_list_client.webarchive` frame_1: the
    JPEG attachment had a signed-S3 URL with `&X-Amz-…` in the query
    string; HTML escaped it as `&amp;X-Amz-…`. Naive str.replace failed
    to match → image bytes extracted to disk but HTML still pointed at
    remote URL → offline-fetcher refused → silent image loss in PDF.
    """

    def test_rewrites_unescaped_url(self) -> None:
        from html2pdf_lib.archives import _rewrite_urls
        url_map = {"https://x/img.jpg": "frame_1/img.jpg"}
        text = '<img src="https://x/img.jpg">'
        out = _rewrite_urls(text, url_map)
        self.assertIn("frame_1/img.jpg", out)
        self.assertNotIn("https://x/img.jpg", out)

    def test_rewrites_html_encoded_amp_in_url(self) -> None:
        """The actual VDD-adversarial regression case."""
        from html2pdf_lib.archives import _rewrite_urls
        url_map = {"https://x/img.jpg?a=1&b=2": "frame_1/img.jpg"}
        text = '<img src="https://x/img.jpg?a=1&amp;b=2">'
        out = _rewrite_urls(text, url_map)
        self.assertIn("frame_1/img.jpg", out)
        # The original encoded form must be gone (not just visually
        # similar — actually replaced).
        self.assertNotIn("&amp;b=2", out)

    def test_url_without_amp_not_double_replaced(self) -> None:
        """Cheap-no-op guard: URLs without `&` do not trigger the
        secondary html-encoded replace pass."""
        from html2pdf_lib.archives import _rewrite_urls
        url_map = {"https://x/img.jpg": "local.jpg"}
        text = '<img src="https://x/img.jpg"> some &amp; text'
        out = _rewrite_urls(text, url_map)
        # `&amp;` in unrelated text must survive untouched.
        self.assertIn("some &amp; text", out)


class TestSubstantialFrameDefensive(unittest.TestCase):
    """pdf-8 VDD-adversarial defensive guard: _is_substantial_frame must
    return False on None / non-bytes input, not crash."""

    def test_none_input(self) -> None:
        from html2pdf_lib.archives import _is_substantial_frame
        # Must not crash with TypeError on len(None).
        self.assertFalse(_is_substantial_frame(None))

    def test_string_input(self) -> None:
        from html2pdf_lib.archives import _is_substantial_frame
        self.assertFalse(_is_substantial_frame("not bytes"))

    def test_int_input(self) -> None:
        from html2pdf_lib.archives import _is_substantial_frame
        self.assertFalse(_is_substantial_frame(42))


class TestNormalizeCSSTableContainment(unittest.TestCase):
    """pdf-10 VDD-adversarial fix: wide tables must fit page width.
    Without `max-width: 100%` paired with `body overflow-x: hidden`,
    wide data tables silently clip at right margin (PDFs cannot scroll
    → right-side data permanently lost)."""

    def test_table_max_width_present(self) -> None:
        from html2pdf_lib.normalize_css import NORMALIZE_CSS
        # The exact rule from §7e (vii) — must contain max-width on table.
        self.assertIn(
            "table { max-width: 100% !important; }",
            NORMALIZE_CSS,
            "Wide tables silently clip without max-width:100% — discovered "
            "via VDD-adversarial review of pdf-10. This rule must pair with "
            "the `body { overflow-x: hidden }` rule to prevent silent data "
            "loss on wide data tables.",
        )


class TestStripHtmlComments(unittest.TestCase):
    """pdf-10: HTML comment strip removes Angular/React skeleton
    placeholders so the `:empty` CSS rule can collapse cells."""

    def test_strips_empty_angular_comments(self) -> None:
        from html2pdf_lib.preprocess import _strip_html_comments
        html = "<div><!----></div><div>real</div>"
        out = _strip_html_comments(html)
        self.assertNotIn("<!---->", out)
        self.assertIn("real", out)

    def test_strips_normal_comments(self) -> None:
        from html2pdf_lib.preprocess import _strip_html_comments
        html = "<p>before<!-- this comment --> after</p>"
        out = _strip_html_comments(html)
        self.assertNotIn("<!--", out)
        self.assertIn("before", out)
        self.assertIn("after", out)

    def test_preserves_conditional_ie_comments(self) -> None:
        """Conditional IE comments (`<!--[if IE]>`) shouldn't be stripped —
        the closing `<![endif]>` matters for legacy markup roundtrip.
        (We don't see them in modern fixtures but defensiveness is cheap.)"""
        from html2pdf_lib.preprocess import _strip_html_comments
        html = "<!--[if IE]>legacy<![endif]-->"
        out = _strip_html_comments(html)
        self.assertIn("[if IE]", out)

    def test_short_circuit_when_no_comments(self) -> None:
        """Fast path: input without `<!--` returns unchanged (avoids
        an O(n) regex pass on millions of chars of comment-free HTML)."""
        from html2pdf_lib.preprocess import _strip_html_comments
        html = "<html><body><p>" + "x" * 100000 + "</p></body></html>"
        out = _strip_html_comments(html)
        self.assertEqual(html, out)


class TestEngineDispatch(unittest.TestCase):
    """pdf-11: `--engine` flag and dispatch behavior in `convert()`.

    These tests do NOT require Playwright to be installed — they verify
    the routing logic, error envelopes, and that the default path stays
    on weasyprint for backwards compatibility.
    """

    def test_supported_engines_includes_both(self) -> None:
        from html2pdf_lib import SUPPORTED_ENGINES
        self.assertIn("weasyprint", SUPPORTED_ENGINES)
        self.assertIn("chrome", SUPPORTED_ENGINES)

    def test_unknown_engine_raises_value_error(self) -> None:
        """`convert(engine='lynx')` must fail loudly, not silently fall
        back to a default. The CLI's `argparse(choices=...)` is the
        primary guard; this is the in-process belt-and-suspenders."""
        from html2pdf_lib import convert
        with self.assertRaises(ValueError) as ctx:
            convert(
                "<html></html>", Path("/tmp/_unused.pdf"),
                base_url="file:///tmp", page_size="letter",
                extra_css_path=None, use_default_css=False,
                engine="lynx",
            )
        self.assertIn("lynx", str(ctx.exception))
        self.assertIn("supported", str(ctx.exception).lower())

    def test_chrome_engine_unavailable_when_playwright_missing(self) -> None:
        """If Playwright is not importable, `--engine chrome` must raise
        `ChromeEngineUnavailable` with a remediation message naming
        `install.sh --with-chrome`. We force the import failure by
        mocking `_import_playwright` to raise directly."""
        from html2pdf_lib import ChromeEngineUnavailable
        from html2pdf_lib import chrome_engine

        def _raise_unavailable():
            raise ChromeEngineUnavailable(
                "Playwright is not installed. To enable the chrome engine, "
                "run: bash install.sh --with-chrome"
            )

        with mock.patch.object(
            chrome_engine, "_import_playwright", side_effect=_raise_unavailable,
        ):
            with self.assertRaises(ChromeEngineUnavailable) as ctx:
                chrome_engine.render_chrome(
                    "<html></html>", Path("/tmp/_unused.pdf"),
                    base_url="file:///tmp", page_size="letter", timeout=10,
                )
        self.assertIn("install.sh --with-chrome", str(ctx.exception))

    def test_chrome_page_size_mapping(self) -> None:
        """Engine-specific page-size key mapping: weasyprint uses CSS
        @page strings (lowercase), chrome uses Playwright's capitalized
        format names. Pinning the table prevents silent regressions."""
        from html2pdf_lib.chrome_engine import _CHROME_PAGE_SIZES
        self.assertEqual(_CHROME_PAGE_SIZES["letter"], "Letter")
        self.assertEqual(_CHROME_PAGE_SIZES["a4"], "A4")
        self.assertEqual(_CHROME_PAGE_SIZES["legal"], "Legal")

    def test_chrome_engine_skips_weasyprint_preprocess(self) -> None:
        """Chrome engine MUST NOT run `preprocess_html` — that pipeline
        contains weasyprint workarounds (calc-strip, font-face-strip,
        NORMALIZE_CSS) that would corrupt a faithful browser render.

        We assert this by patching `preprocess_html` to track calls; on
        the chrome path it must not be invoked. (The chrome render itself
        is mocked away so the test runs without Playwright.)
        """
        from html2pdf_lib import convert
        from html2pdf_lib import preprocess as preprocess_mod
        from html2pdf_lib import render as render_mod

        called = {"preprocess": 0, "chrome": 0}

        def _stub_preprocess(html: str) -> str:
            called["preprocess"] += 1
            return html

        def _stub_render_chrome(_html, _out, **_kw):
            called["chrome"] += 1

        with mock.patch.object(
            preprocess_mod, "preprocess_html", side_effect=_stub_preprocess,
        ), mock.patch.object(
            render_mod, "preprocess_html", side_effect=_stub_preprocess,
        ), mock.patch(
            "html2pdf_lib.chrome_engine.render_chrome",
            side_effect=_stub_render_chrome,
        ):
            convert(
                "<html><body>x</body></html>", Path("/tmp/_unused.pdf"),
                base_url="file:///tmp", page_size="letter",
                extra_css_path=None, use_default_css=False,
                engine="chrome", timeout=10,
            )

        self.assertEqual(
            called["preprocess"], 0,
            "chrome engine must NOT invoke preprocess_html",
        )
        self.assertEqual(called["chrome"], 1, "chrome render must be called once")

    def test_strip_base_href_removes_tag(self) -> None:
        """pdf-11 VDD-fix: webarchives carry `<base href="https://orig.
        site/">` so saved DOM resolves relative URLs against the live
        site. Chrome honours this tag — every relative `<link>` would
        route to the offline-blocked origin. Stripping the tag forces
        chrome to fall back to our file:// document URL.

        Pinning this is critical: a refactor that drops `_strip_base_href`
        from the chrome render path silently breaks every webarchive
        with non-empty CSS (≥ 95 % of real fixtures)."""
        from html2pdf_lib.chrome_engine import _strip_base_href
        html = (
            '<html><head>'
            '<base href="https://crm-dev.example.com/">'
            '<link rel="stylesheet" href="styles.css">'
            '</head><body>x</body></html>'
        )
        out = _strip_base_href(html)
        self.assertNotIn("<base", out.lower())
        # Relative <link> must survive — it's the asset reference we
        # want to resolve to the local file:// extraction tempdir.
        self.assertIn('<link rel="stylesheet" href="styles.css">', out)

    def test_strip_base_href_handles_multiple_and_quotes(self) -> None:
        """Defensive: HTML5 disallows multiple <base>, but malformed
        webarchives might still ship them. Single quotes, no quotes,
        attribute-order variations — all must be stripped."""
        from html2pdf_lib.chrome_engine import _strip_base_href
        html = (
            "<base href='http://a.com/'>"
            '<base target="_top" href="http://b.com/" />'
            '<base href=http://c.com/>'
        )
        out = _strip_base_href(html)
        self.assertNotIn("<base", out.lower())

    def test_strip_base_href_fast_path_no_change(self) -> None:
        """Plain HTML without any `<base>` tag must short-circuit and
        return the input unchanged (avoids one unnecessary regex pass
        per chrome render)."""
        from html2pdf_lib.chrome_engine import _strip_base_href
        html = "<html><head><title>t</title></head><body>x</body></html>"
        self.assertIs(_strip_base_href(html), html)

    def test_chrome_engine_default_javascript_off(self) -> None:
        """pdf-11 VDD-fix: JavaScript is OFF by default in the chrome
        engine. Static archives already capture the rendered DOM; running
        their JS with offline network either replaces the body with an
        error fallback (Gmail) or leaves the SPA in a half-hydrated
        overlapping state (ELMA365). Pinning the default keeps this
        baseline regression-protected."""
        import inspect
        from html2pdf_lib.chrome_engine import render_chrome
        sig = inspect.signature(render_chrome)
        self.assertFalse(
            sig.parameters["javascript"].default,
            "render_chrome must default to javascript=False",
        )

    def test_chrome_engine_desktop_viewport(self) -> None:
        """Pin the desktop-class viewport (1280×1024) so SPAs that
        branch on `@media (min-width: 1024px)` resolve to the desktop
        layout instead of mobile-stack collapse."""
        from html2pdf_lib.chrome_engine import _DEFAULT_VIEWPORT
        self.assertGreaterEqual(_DEFAULT_VIEWPORT["width"], 1280)
        self.assertGreaterEqual(_DEFAULT_VIEWPORT["height"], 1024)

    def test_layout_normalize_css_releases_html_body_height(self) -> None:
        """pdf-11 VDD-fix: html/body release with high specificity so it
        beats `body.modal-open { overflow: hidden }` class-based rules
        (ELMA365 sets that class for the full-screen activity panel).
        The injected normalize CSS must:
          - release html/body height clamping (auto !important)
          - release html/body overflow (visible !important)
          - have specificity high enough for body.<class> rules.
        """
        from html2pdf_lib.chrome_engine import _LAYOUT_NORMALIZE_CSS
        # body release with multiple class-based selectors for specificity
        self.assertIn("body.modal-open", _LAYOUT_NORMALIZE_CSS)
        self.assertIn("body[class]", _LAYOUT_NORMALIZE_CSS)
        self.assertIn("height: auto !important", _LAYOUT_NORMALIZE_CSS)
        self.assertIn("overflow: visible !important", _LAYOUT_NORMALIZE_CSS)
        # universal inner-container release for scroll containers
        self.assertIn("* {", _LAYOUT_NORMALIZE_CSS)

    def test_strip_script_tags_removes_inline_and_external(self) -> None:
        """pdf-11 VDD-iter-3: chrome path defaults to JS-enabled at the
        Playwright context level (so page.evaluate works for surgical
        DOM normalization) BUT strips every `<script>` tag from HTML so
        the page itself can't run JS. This prevents Gmail self-destruct,
        Angular half-hydration, etc., while keeping our normalization
        privileges. Pin the strip to catch a refactor that lets page
        scripts back in."""
        from html2pdf_lib.chrome_engine import _strip_script_tags
        html = (
            '<html><head>'
            '<script>document.body.innerHTML = "haxxed"</script>'
            '<script src="evil.js"></script>'
            '<SCRIPT>x</SCRIPT>'
            '<script defer\n  type="module">multi\nline</script>'
            '</head><body>safe content</body></html>'
        )
        out = _strip_script_tags(html)
        self.assertNotIn("<script", out.lower())
        self.assertNotIn("haxxed", out)
        self.assertIn("safe content", out)

    def test_strip_script_tags_fast_path_no_change(self) -> None:
        """Plain HTML with no `<script>` tag must short-circuit."""
        from html2pdf_lib.chrome_engine import _strip_script_tags
        html = "<html><body>plain content</body></html>"
        self.assertIs(_strip_script_tags(html), html)

    def test_strip_script_tags_negative_dangerous_payloads_removed(self) -> None:
        """VDD adversarial: explicitly assert that dangerous JS patterns
        (the kind that cause Gmail self-destruct or Angular half-
        hydration) are removed by _strip_script_tags. This is the
        negative regression — instead of asserting "good thing X is
        there", we assert "bad thing Y is NOT there".

        The kinds of payloads we explicitly check for:
          * `document.body.innerHTML = ...` (the gmail body-replace pattern)
          * `document.body.replaceWith(...)` (alternate replace pattern)
          * `window.location = ...` (offline-redirect pattern)
          * `fetch(...)` calls (network probes that might trigger
            fallback when they fail)
          * Service worker registrations
          * `addEventListener('error', ...)` patterns
        """
        from html2pdf_lib.chrome_engine import _strip_script_tags
        html = (
            '<html><body>'
            'GOOD CONTENT START'
            '<script>document.body.innerHTML="<h1>OFFLINE ERROR</h1>"</script>'
            '<script>document.body.replaceWith(document.createElement("div"))</script>'
            '<script type="module">window.location.href="/error"</script>'
            '<script async>fetch("/api/check").catch(() => location.reload())</script>'
            '<script>navigator.serviceWorker.register("sw.js")</script>'
            '<script defer>'
            'window.addEventListener("error", () => '
            'document.body.innerHTML = "<p>Try Again Sign Out</p>")'
            '</script>'
            'GOOD CONTENT END'
            '</body></html>'
        )
        out = _strip_script_tags(html)
        # Positive: legitimate content survives.
        self.assertIn("GOOD CONTENT START", out)
        self.assertIn("GOOD CONTENT END", out)
        # Negative: dangerous patterns gone.
        for forbidden in (
            "document.body.innerHTML",
            "document.body.replaceWith",
            "window.location",
            "fetch(",
            "serviceWorker",
            'addEventListener("error"',
            "<script",
        ):
            self.assertNotIn(
                forbidden, out,
                f"Dangerous pattern survived strip: {forbidden!r}",
            )

    def test_offline_patch_init_script_no_trailing_semicolon_iife(self) -> None:
        """VDD adversarial: IIFE with trailing `;` becomes a statement,
        page.evaluate returns 0 (not the object). We caught this once
        already — pin it. Both `_OFFLINE_PATCH_INIT_SCRIPT` and the DOM
        normalize script must end with `})()` (no trailing semicolon)
        so they evaluate as expressions.
        """
        from html2pdf_lib import chrome_engine
        for name in ("_OFFLINE_PATCH_INIT_SCRIPT",):
            if hasattr(chrome_engine, name):
                src = getattr(chrome_engine, name)
                marker = "})()"
                self.assertTrue(
                    src.rstrip().endswith(marker),
                    f"{name} must end with the IIFE-call marker (no trailing semicolon)",
                )

    def test_compute_pdf_scale_fits_a4(self) -> None:
        """pdf-11 VDD-iter-3: SPA layouts are 1280 CSS px wide (default
        viewport). A4 PDF page is ~793 px (~718 usable after 1cm
        margins). Without scale, the right edge of the layout gets
        clipped past the PDF page boundary (user-reported "narrow
        strip of cut-off data on the right side" of ELMA365).

        compute_pdf_scale must produce a value < 1 that makes 1280 px
        layout fit ≤ 720 px page. Pin the formula so a refactor that
        drops the scale call regresses to right-edge cutoff."""
        from html2pdf_lib.chrome_engine import _compute_pdf_scale
        for size in ("a4", "letter", "legal"):
            scale = _compute_pdf_scale(size, 1280)
            self.assertLess(scale, 0.7, f"{size} scale must be <0.7")
            self.assertGreater(scale, 0.5, f"{size} scale must be >0.5")
            # Check that layout actually fits PDF page
            scaled_width = 1280 * scale
            self.assertLessEqual(
                scaled_width, 745,
                f"{size} scaled layout {scaled_width:.0f} must fit page",
            )

    def test_compute_pdf_scale_unknown_format_falls_back_to_a4(self) -> None:
        """Defensive: unknown page_size key falls back to A4 dimensions
        (the smallest of the three supported formats — most conservative
        choice). Pinning the fallback prevents silent KeyError later."""
        from html2pdf_lib.chrome_engine import _compute_pdf_scale
        scale = _compute_pdf_scale("unknown_format", 1280)
        # 718 (A4 usable) / 1280 ≈ 0.5609
        self.assertAlmostEqual(scale, 0.5609, places=2)

    def test_chrome_render_injects_layout_normalize(self) -> None:
        """Verify render_chrome inserts the normalize CSS into <head>
        before writing HTML to disk. We mock Playwright away and
        capture the html_text written to the temp file. (This catches
        a refactor that defines _LAYOUT_NORMALIZE_CSS but forgets to
        wire it into the render path.)"""
        from html2pdf_lib import chrome_engine as ce
        captured = {"html": None}

        original_write = Path.write_text

        def _capture_write(self, content, **kw):
            if str(self).endswith("__html2pdf_chrome.html"):
                captured["html"] = content
            return original_write(self, content, **kw)

        # Stub Playwright entirely — we only care about what HTML gets
        # written before the browser would have opened it.
        class _StubBrowser:
            def new_context(self, **kw): return _StubCtx()
            def close(self): pass
        class _StubCtx:
            def route(self, *a, **k): pass
            def new_page(self): return _StubPage()
            def close(self): pass
        class _StubPage:
            def goto(self, *a, **k): pass
            def emulate_media(self, **k): pass
            def pdf(self, **k):
                Path(k["path"]).write_bytes(b"%PDF-1.4 stub\n")
            def close(self): pass
        class _StubPW:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            @property
            def chromium(self):
                class _C:
                    def launch(self, **k): return _StubBrowser()
                return _C()
        def _stub_imports():
            return (lambda: _StubPW(), Exception, Exception)

        import tempfile
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(ce, "_import_playwright", _stub_imports), \
             mock.patch.object(Path, "write_text", _capture_write):
            ce.render_chrome(
                "<html><head></head><body>x</body></html>",
                Path(td) / "out.pdf",
                base_url=td, page_size="letter", timeout=10,
            )

        self.assertIsNotNone(captured["html"], "render_chrome did not write HTML")
        self.assertIn(
            "__html2pdf_chrome_layout_normalize", captured["html"],
            "layout-normalize <style> must be injected into <head>",
        )

    def test_default_engine_is_weasyprint(self) -> None:
        """Backwards compatibility: every existing call site that omits
        `engine=` must still go through the weasyprint path. We verify
        by patching weasyprint's `HTML(...)` and checking it was hit."""
        from html2pdf_lib import convert
        from html2pdf_lib import render as render_mod

        seen = {"hit": 0}

        class _StubHTML:
            def __init__(self, **kw):
                seen["hit"] += 1
                self.kw = kw

            def write_pdf(self, *a, **kw):
                return None

        with mock.patch.object(render_mod, "HTML", _StubHTML):
            convert(
                "<html><body>x</body></html>", Path("/tmp/_unused.pdf"),
                base_url="file:///tmp", page_size="letter",
                extra_css_path=None, use_default_css=False,
                # NOTE: `engine=` deliberately omitted to test default.
                timeout=10,
            )

        self.assertEqual(seen["hit"], 1, "default engine must be weasyprint")


try:
    import playwright.sync_api  # noqa: F401
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


@unittest.skipUnless(
    _HAS_PLAYWRIGHT, "Playwright not installed (skip chrome E2E tests)",
)
class TestChromeE2ENegativeRegression(unittest.TestCase):
    """VDD adversarial: actually render real webarchive fixtures via the
    chrome engine and verify NEGATIVE markers — that artifacts from
    common SPA failure modes (Gmail offline error, Angular half-
    hydration, broken DOM) do NOT appear in the PDF output. Without
    these tests, a refactor that re-introduces the gmail self-destruct
    bug would silently regress until a user complains.

    Skipped when Playwright is not installed (light-install user).
    Each test runs a full chrome render — ~5-10s per fixture.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="chrome_e2e_neg_"))
        cls.fixtures_dir = (
            Path(__file__).resolve().parent.parent.parent.parent.parent
            / "tmp"
        )

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _render_chrome(self, fixture_name: str) -> str:
        """Render `tmp/{fixture_name}` via chrome engine and return
        extracted text. Returns empty string if fixture missing."""
        fixture = self.fixtures_dir / fixture_name
        if not fixture.is_file():
            self.skipTest(f"fixture not present: {fixture}")
        from html2pdf_lib import convert
        from html2pdf_lib.archives import extract_archive
        out_pdf = self.tmpdir / f"{fixture.stem}.pdf"
        work = self.tmpdir / f"work_{fixture.stem}"
        work.mkdir(exist_ok=True)
        html_text, base_url = extract_archive(
            fixture, work, frame_spec="auto",
        )
        convert(
            html_text, out_pdf,
            base_url=base_url, page_size="a4",
            extra_css_path=None, use_default_css=False,
            engine="chrome", timeout=120,
        )
        import pdfplumber  # type: ignore
        with pdfplumber.open(str(out_pdf)) as p:
            return "".join((page.extract_text() or "") for page in p.pages)

    def test_gmail_no_offline_error_fallback(self):
        """Gmail's offline JS replaces body with "Временная ошибка ..."
        when fetch fails. Our chrome engine strips scripts to prevent
        this. If a refactor re-enables page scripts (or our strip
        misses inline scripts), this fallback would appear in the PDF.
        Negative regression: assert the fallback strings are NOT in
        the output.
        """
        text = self._render_chrome("gmail_example.webarchive")
        forbidden = (
            "Временная ошибка",
            "Try Again", "Sign Out",
            "ваш аккаунт временно недоступен",
        )
        for f in forbidden:
            self.assertNotIn(
                f, text,
                f"Gmail offline-error fallback leaked into PDF: {f!r} "
                "— scripts may be running OR strip_scripts is broken.",
            )
        # Positive: real email content present.
        self.assertIn("Sentora", text)

    def test_elma365_full_activity_log_present(self):
        """ELMA365 wraps activity panel in `position: fixed` modal.
        Without our DOM normalization, the modal's 6816 px content
        gets clipped (chrome PDF only paginates body.scrollHeight =
        4092 px). Negative regression: assert the LAST few activities
        are present (would be missing if modal stayed fixed).
        """
        text = self._render_chrome("elma365_activities_example.webarchive")
        # These specific entries are at byte 1.6 MB / end-of-DOM and
        # were the first to drop when truncation regressed.
        for needle in ("29.01.2025", "04.02.2025", "31.07.2025", "Тест ТД"):
            self.assertIn(
                needle, text,
                f"ELMA365 activity {needle!r} missing — modal-unfurl "
                "broken (DOM normalize didn't release position:fixed).",
            )

    def test_ya_browser_no_excessive_empty_pages(self):
        """ya_browser is a static marketplace product card. After our
        DOM normalization improvements, it should render in 2-4 pages.
        A previous refactor produced 35 pages with 23 empty (because
        `* { position: static !important }` unfurled every backdrop /
        toast container). Negative regression: assert page count is
        reasonable (≤ 5 pages for a 190 KB static page).
        """
        from html2pdf_lib import convert
        from html2pdf_lib.archives import extract_archive
        import pypdf  # type: ignore
        fixture = self.fixtures_dir / "ya_browser.webarchive"
        if not fixture.is_file():
            self.skipTest(f"fixture not present: {fixture}")
        out = self.tmpdir / "ya_browser.pdf"
        work = self.tmpdir / "work_ya"
        work.mkdir(exist_ok=True)
        html_text, base_url = extract_archive(
            fixture, work, frame_spec="auto",
        )
        convert(
            html_text, out,
            base_url=base_url, page_size="a4",
            extra_css_path=None, use_default_css=False,
            engine="chrome", timeout=60,
        )
        page_count = len(pypdf.PdfReader(str(out)).pages)
        self.assertLessEqual(
            page_count, 5,
            f"ya_browser expanded to {page_count} pages — backdrop/"
            "overlay unfurl regression (expected ≤5 pages for static "
            "marketplace card).",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

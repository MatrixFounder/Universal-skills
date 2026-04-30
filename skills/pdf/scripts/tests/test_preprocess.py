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
    _strip_empty_anchor_links,
    _strip_icon_svgs,
    _strip_interactive_chrome,
    _strip_universal_ads,
)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)

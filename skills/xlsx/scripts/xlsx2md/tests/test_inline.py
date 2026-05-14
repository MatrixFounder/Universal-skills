"""Unit tests for xlsx2md/inline.py — cell-value inline rendering (012-04).

10 tests per TASK §5.2:
1.  _escape_pipe_gfm escapes | → \\|
2.  _newlines_to_br joins lines with <br> (no trailing)
3.  _render_hyperlink GFM allowed scheme emits [text](url)
4.  _render_hyperlink HTML allowed scheme emits <a href>
5.  _render_hyperlink empty scheme treated as http
6.  _render_hyperlink javascript: blocked → plain text + warning
7.  _render_hyperlink None sentinel (allow all) allows javascript:
8.  _render_hyperlink frozenset() (block all) blocks https://
9.  _render_hyperlink case-insensitive scheme match (HTTPS allowed)
10. _render_hyperlink empty value "" produces [](url) / <a href="url"></a>
"""
from __future__ import annotations

import sys
import unittest
import warnings
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from xlsx2md.inline import (
    _escape_html_entities,
    _escape_pipe_gfm,
    _newlines_to_br,
    _render_hyperlink,
    render_cell_value,
)

_DEFAULT_SCHEMES = frozenset({"http", "https", "mailto"})


class TestEscapePipeGfm(unittest.TestCase):
    """TC-INLINE-01 — _escape_pipe_gfm escapes | → \\|."""

    def test_pipe_escaped(self) -> None:
        self.assertEqual(_escape_pipe_gfm("a|b|c"), r"a\|b\|c")

    def test_no_pipe_unchanged(self) -> None:
        self.assertEqual(_escape_pipe_gfm("hello world"), "hello world")

    def test_multiple_pipes(self) -> None:
        self.assertEqual(_escape_pipe_gfm("|"), r"\|")

    def test_other_special_chars_pass_through(self) -> None:
        """* _ ` are not escaped (markdown-in-cell affordance)."""
        self.assertEqual(_escape_pipe_gfm("*bold* _italic_ `code`"), "*bold* _italic_ `code`")


class TestNewlinesToBr(unittest.TestCase):
    """TC-INLINE-02 — _newlines_to_br joins lines with <br>."""

    def test_single_newline(self) -> None:
        self.assertEqual(_newlines_to_br("first\nsecond"), "first<br>second")

    def test_multiple_newlines(self) -> None:
        self.assertEqual(_newlines_to_br("a\nb\nc"), "a<br>b<br>c")

    def test_no_newline_unchanged(self) -> None:
        self.assertEqual(_newlines_to_br("plain"), "plain")

    def test_trailing_newline_produces_trailing_br(self) -> None:
        self.assertEqual(_newlines_to_br("line\n"), "line<br>")


class TestRenderHyperlinkGfmAllowed(unittest.TestCase):
    """TC-INLINE-03 — GFM allowed scheme emits [text](url)."""

    def test_https_gfm(self) -> None:
        result = _render_hyperlink(
            "click here",
            "https://example.com",
            mode="gfm",
            allowed_schemes=_DEFAULT_SCHEMES,
        )
        self.assertEqual(result, "[click here](https://example.com)")

    def test_mailto_gfm(self) -> None:
        result = _render_hyperlink(
            "email me",
            "mailto:user@example.com",
            mode="gfm",
            allowed_schemes=_DEFAULT_SCHEMES,
        )
        self.assertEqual(result, "[email me](mailto:user@example.com)")


class TestRenderHyperlinkHtmlAllowed(unittest.TestCase):
    """TC-INLINE-04 — HTML allowed scheme emits <a href>."""

    def test_https_html(self) -> None:
        result = _render_hyperlink(
            "click here",
            "https://example.com",
            mode="html",
            allowed_schemes=_DEFAULT_SCHEMES,
        )
        self.assertEqual(
            result,
            '<a href="https://example.com">click here</a>',
        )

    def test_html_href_escaping(self) -> None:
        """Ampersands and quotes in href must be escaped."""
        result = _render_hyperlink(
            "link",
            'https://example.com/path?a=1&b="2"',
            mode="html",
            allowed_schemes=_DEFAULT_SCHEMES,
        )
        self.assertIn("&amp;", result)
        self.assertIn("&quot;", result)


class TestRenderHyperlinkEmptySchemeAsHttp(unittest.TestCase):
    """TC-INLINE-05 — empty scheme treated as http."""

    def test_relative_url_treated_as_http(self) -> None:
        """'page.html' has no scheme → treated as http → allowed."""
        result = _render_hyperlink(
            "local page",
            "page.html",
            mode="gfm",
            allowed_schemes=_DEFAULT_SCHEMES,  # includes http
        )
        self.assertEqual(result, "[local page](page.html)")

    def test_relative_url_blocked_when_http_not_in_allowlist(self) -> None:
        """Empty scheme → 'http'; not in frozenset({'https'}) → blocked."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _render_hyperlink(
                "local page",
                "page.html",
                mode="gfm",
                allowed_schemes=frozenset({"https"}),
            )
        self.assertEqual(result, "local page")
        self.assertTrue(any(issubclass(w.category, UserWarning) for w in caught))


class TestRenderHyperlinkJavascriptBlocked(unittest.TestCase):
    """TC-INLINE-06 — javascript: blocked → plain text + warning."""

    def test_javascript_blocked_gfm(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _render_hyperlink(
                "text",
                "javascript:alert(1)",
                mode="gfm",
                allowed_schemes=_DEFAULT_SCHEMES,
            )
        self.assertEqual(result, "text")
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        self.assertTrue(
            len(user_warnings) >= 1,
            "Expected a UserWarning for blocked javascript: scheme",
        )
        # Warning must mention the scheme.
        warning_texts = [str(w.message) for w in user_warnings]
        self.assertTrue(
            any("javascript" in t for t in warning_texts),
            f"Expected 'javascript' in warning; got {warning_texts!r}",
        )

    def test_javascript_blocked_html(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _render_hyperlink(
                "text",
                "javascript:void(0)",
                mode="html",
                allowed_schemes=_DEFAULT_SCHEMES,
            )
        self.assertEqual(result, "text")
        self.assertTrue(
            any(issubclass(w.category, UserWarning) for w in caught),
        )

    def test_cell_addr_prefix_in_warning(self) -> None:
        """cell_addr appears in warning message when provided."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _render_hyperlink(
                "text",
                "javascript:alert(1)",
                mode="gfm",
                allowed_schemes=_DEFAULT_SCHEMES,
                cell_addr="Sheet1!A2",
            )
        texts = [str(w.message) for w in caught if issubclass(w.category, UserWarning)]
        self.assertTrue(
            any("Sheet1!A2" in t for t in texts),
            f"Expected cell address in warning; got {texts!r}",
        )


class TestRenderHyperlinkNoneSentinelAllowsAll(unittest.TestCase):
    """TC-INLINE-07 — None sentinel (allow all) allows javascript:."""

    def test_none_allows_javascript_gfm(self) -> None:
        """allowed_schemes=None → allow all; javascript: goes through.

        M8 fix: href with ``(`` or ``)`` uses angle-bracket form
        ``[text](<url>)`` per CommonMark §6.3 — prevents markdown
        injection via embedded ``)`` (dual-link bypass).
        """
        result = _render_hyperlink(
            "text",
            "javascript:alert(1)",
            mode="gfm",
            allowed_schemes=None,
        )
        # Angle-bracket form because href contains '(' and ')'.
        self.assertEqual(result, "[text](<javascript:alert(1)>)")

    def test_none_allows_ftp_html(self) -> None:
        result = _render_hyperlink(
            "ftp link",
            "ftp://files.example.com",
            mode="html",
            allowed_schemes=None,
        )
        self.assertIn("ftp://files.example.com", result)
        self.assertIn("<a href=", result)


class TestRenderHyperlinkEmptyFrozensetBlocksAll(unittest.TestCase):
    """TC-INLINE-08 — frozenset() (block all) blocks https://."""

    def test_empty_frozenset_blocks_https_gfm(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _render_hyperlink(
                "safe link",
                "https://example.com",
                mode="gfm",
                allowed_schemes=frozenset(),
            )
        self.assertEqual(result, "safe link")
        self.assertTrue(
            any(issubclass(w.category, UserWarning) for w in caught),
        )

    def test_empty_frozenset_blocks_mailto(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _render_hyperlink(
                "email",
                "mailto:x@y.com",
                mode="gfm",
                allowed_schemes=frozenset(),
            )
        self.assertEqual(result, "email")
        self.assertTrue(
            any(issubclass(w.category, UserWarning) for w in caught),
        )


class TestRenderHyperlinkCaseInsensitiveScheme(unittest.TestCase):
    """TC-INLINE-09 — case-insensitive scheme match (HTTPS allowed)."""

    def test_uppercase_https_in_href(self) -> None:
        """'HTTPS://example.com' scheme is lowercased → matches 'https'."""
        result = _render_hyperlink(
            "UPPER LINK",
            "HTTPS://example.com",
            mode="gfm",
            allowed_schemes=frozenset({"https"}),
        )
        self.assertEqual(result, "[UPPER LINK](HTTPS://example.com)")

    def test_mixed_case_ftp_blocked(self) -> None:
        """'FTP://...' → scheme 'ftp' → not in {'http','https','mailto'} → blocked."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = _render_hyperlink(
                "ftp",
                "FTP://archive.org",
                mode="gfm",
                allowed_schemes=_DEFAULT_SCHEMES,
            )
        self.assertEqual(result, "ftp")


class TestRenderHyperlinkEmptyValue(unittest.TestCase):
    """TC-INLINE-10 — empty value '' produces [](url) / <a href="url"></a>."""

    def test_empty_value_gfm(self) -> None:
        result = _render_hyperlink(
            "",
            "https://example.com",
            mode="gfm",
            allowed_schemes=_DEFAULT_SCHEMES,
        )
        self.assertEqual(result, "[](https://example.com)")

    def test_empty_value_html(self) -> None:
        result = _render_hyperlink(
            "",
            "https://example.com",
            mode="html",
            allowed_schemes=_DEFAULT_SCHEMES,
        )
        self.assertEqual(result, '<a href="https://example.com"></a>')

    def test_none_value_gfm(self) -> None:
        """None value is coerced to '' → same as empty string."""
        result = _render_hyperlink(
            None,
            "https://example.com",
            mode="gfm",
            allowed_schemes=_DEFAULT_SCHEMES,
        )
        self.assertEqual(result, "[](https://example.com)")


class TestRenderCellValue(unittest.TestCase):
    """render_cell_value dispatcher tests."""

    def test_none_returns_empty_string(self) -> None:
        result = render_cell_value(
            None, mode="gfm", allowed_schemes=_DEFAULT_SCHEMES
        )
        self.assertEqual(result, "")

    def test_plain_text_gfm_pipe_escaped(self) -> None:
        result = render_cell_value(
            "a|b", mode="gfm", allowed_schemes=_DEFAULT_SCHEMES
        )
        self.assertEqual(result, r"a\|b")

    def test_plain_text_html_entity_escaped(self) -> None:
        result = render_cell_value(
            "<b>bold</b>", mode="html", allowed_schemes=_DEFAULT_SCHEMES
        )
        self.assertEqual(result, "&lt;b&gt;bold&lt;/b&gt;")

    def test_hyperlink_href_routes_to_render_hyperlink(self) -> None:
        result = render_cell_value(
            "click",
            mode="gfm",
            hyperlink_href="https://example.com",
            allowed_schemes=_DEFAULT_SCHEMES,
        )
        self.assertEqual(result, "[click](https://example.com)")

    def test_newline_to_br_in_gfm(self) -> None:
        result = render_cell_value(
            "line1\nline2", mode="gfm", allowed_schemes=_DEFAULT_SCHEMES
        )
        self.assertEqual(result, "line1<br>line2")

    def test_newline_to_br_in_html(self) -> None:
        result = render_cell_value(
            "line1\nline2", mode="html", allowed_schemes=_DEFAULT_SCHEMES
        )
        self.assertEqual(result, "line1<br>line2")


class TestEscapeHtmlEntities(unittest.TestCase):
    """_escape_html_entities delegates to html.escape."""

    def test_ampersand(self) -> None:
        self.assertEqual(_escape_html_entities("a & b"), "a &amp; b")

    def test_lt_gt(self) -> None:
        self.assertEqual(_escape_html_entities("<tag>"), "&lt;tag&gt;")

    def test_quote(self) -> None:
        self.assertIn("&quot;", _escape_html_entities('"'))


class TestRenderHyperlinkBlockedBranchHtmlEscape(unittest.TestCase):
    """Sarcasmotron H2 fix: blocked-scheme HTML mode MUST html.escape the
    cell value before returning. Previously the blocked branch returned
    `value_text` (only pipe-escape applied) — a value containing
    ``<script>`` would have survived raw into a ``<td>`` element (XSS
    vector for direct API callers bypassing the dispatch-side filter).
    """

    def test_blocked_html_scheme_with_html_payload_in_value_is_escaped(
        self,
    ) -> None:
        """The bug: value containing ``<script>`` returned unescaped."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = _render_hyperlink(
                "<script>alert(1)</script>",
                "javascript:alert(2)",
                mode="html",
                allowed_schemes=frozenset({"http", "https"}),
            )
        # Critical: raw <script> tag must NOT survive into HTML output.
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)
        self.assertIn("&lt;/script&gt;", result)

    def test_blocked_html_scheme_with_lt_gt_amp_quote_in_value(self) -> None:
        """Edge case: all four HTML special chars in the value."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = _render_hyperlink(
                '<&">',
                "javascript:alert(1)",
                mode="html",
                allowed_schemes=frozenset({"https"}),
            )
        self.assertNotIn("<", result)
        self.assertNotIn(">", result)
        self.assertIn("&lt;", result)
        self.assertIn("&gt;", result)
        self.assertIn("&amp;", result)

    def test_blocked_gfm_scheme_path_unchanged(self) -> None:
        """The GFM blocked branch is NOT affected (pipe escape only,
        no html.escape — markdown renderers handle their own escaping)."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = _render_hyperlink(
                "click here",
                "javascript:alert(1)",
                mode="gfm",
                allowed_schemes=frozenset({"http", "https"}),
            )
        # GFM blocked branch: returns plain text without [text](url) wrapper.
        self.assertEqual(result, "click here")


class TestRenderHyperlinkGfmHrefAngleBracketEscape(unittest.TestCase):
    """Sarcasmotron M8 fix: GFM hrefs containing ``)``, ``(``, ``\\n``,
    ``<``, ``>``, or whitespace must use angle-bracket form
    ``[text](<url>)`` per CommonMark §6.3. Prevents markdown-injection
    bypass of the scheme-allowlist via dual-link payloads with embedded
    ``)``.
    """

    def test_href_with_closing_paren_uses_angle_form(self) -> None:
        """Wikipedia-style URL with parens degrades cleanly via angle form."""
        result = _render_hyperlink(
            "Page",
            "https://wiki.example.com/Page_(disambiguation)",
            mode="gfm",
            allowed_schemes=None,
        )
        self.assertEqual(
            result,
            "[Page](<https://wiki.example.com/Page_(disambiguation)>)",
        )

    def test_href_with_dual_link_injection_payload_neutralised(self) -> None:
        """Adversarial: href = ``https://ok.com/) [click](javascript:alert(1)``.

        Without M8 fix: emits as two markdown links, second pointing to
        javascript:. With angle-form: the entire string is bound inside
        ``<...>`` — no nested link possible.
        """
        evil = "https://ok.com/) [click](javascript:alert(1)"
        result = _render_hyperlink(
            "safe text",
            evil,
            mode="gfm",
            allowed_schemes=frozenset({"http", "https"}),
        )
        # Angle-form: the entire payload is INSIDE <...>, so it's a
        # single link target with no markdown-link breakout.
        self.assertTrue(result.startswith("[safe text](<https://ok.com/)"))
        self.assertTrue(result.endswith(">)"))
        # Critical: no second `[click](javascript:` markdown link parsed.
        # The string still CONTAINS the literal substring "[click](" but
        # it's INSIDE the angle brackets — not a markdown construct.
        self.assertEqual(result.count("](<"), 1)

    def test_href_with_whitespace_uses_angle_form(self) -> None:
        """Whitespace in href requires angle-bracket form."""
        result = _render_hyperlink(
            "text",
            "https://ok.com/path with space",
            mode="gfm",
            allowed_schemes=None,
        )
        self.assertEqual(
            result, "[text](<https://ok.com/path with space>)"
        )

    def test_href_with_gt_percent_encoded_in_angle_form(self) -> None:
        """'>' inside href would close the angle bracket — percent-encode."""
        result = _render_hyperlink(
            "text",
            "https://ok.com/a>b",
            mode="gfm",
            allowed_schemes=None,
        )
        # '>' must be %3E so the angle-bracket form parses correctly.
        self.assertIn("%3E", result)
        self.assertNotIn("a>b", result)

    def test_simple_href_no_angle_form(self) -> None:
        """Clean href (no metacharacters) uses the simple form."""
        result = _render_hyperlink(
            "text",
            "https://ok.com/path",
            mode="gfm",
            allowed_schemes=None,
        )
        self.assertEqual(result, "[text](https://ok.com/path)")

    def test_href_with_newline_neutralised(self) -> None:
        """**Iter-2 HIGH fix (Sec-1/M8 incomplete)**: literal LF in href
        must be percent-encoded as %0A — otherwise CommonMark renderers
        end the angle-form destination at the LF and parse the remainder
        as fresh markdown, bypassing the scheme-allowlist via a
        ``\\n[evil](javascript:...)`` payload in the first allowed URL.
        """
        evil_href = "https://ok.com/\n[evil](javascript:alert(1))"
        result = _render_hyperlink(
            "text",
            evil_href,
            mode="gfm",
            allowed_schemes=frozenset({"http", "https"}),
        )
        # LF must NOT survive into the angle-form output.
        self.assertNotIn("\n", result)
        # Percent-encoded as %0A instead.
        self.assertIn("%0A", result)
        # The `[evil](javascript:` payload survives as TEXT inside the
        # angle brackets, but the markdown parser sees a single
        # angle-form URL — no second link is parseable.
        self.assertEqual(result.count("](<"), 1)

    def test_href_with_lt_percent_encoded(self) -> None:
        """Iter-2 HIGH fix: `<` in href must be percent-encoded as %3C.

        CommonMark §6.3: unescaped `<` inside `<...>` ends the link
        destination. The iter-1 M8 fix percent-encoded `>` only — a
        bare `<` would still close the angle-form early.
        """
        result = _render_hyperlink(
            "text",
            "https://ok.com/<script>",
            mode="gfm",
            allowed_schemes=None,
        )
        self.assertIn("%3C", result)
        self.assertIn("%3E", result)
        # No raw `<` or `>` inside the URL portion.
        # (The closing `>` of the angle-form remains, but that's the
        # angle-form delimiter, not URL content.)
        url_inside_angle = result[result.index("<") + 1: result.rindex(">")]
        self.assertNotIn("<", url_inside_angle)
        self.assertNotIn(">", url_inside_angle)

    def test_href_with_carriage_return_neutralised(self) -> None:
        """Iter-2 HIGH fix: `\\r` in href must be percent-encoded as %0D."""
        result = _render_hyperlink(
            "text",
            "https://ok.com/\rinjection",
            mode="gfm",
            allowed_schemes=None,
        )
        self.assertNotIn("\r", result)
        self.assertIn("%0D", result)

    def test_href_with_tab_neutralised(self) -> None:
        """Iter-2 HIGH fix: `\\t` in href must be percent-encoded as %09."""
        result = _render_hyperlink(
            "text",
            "https://ok.com/\tinjection",
            mode="gfm",
            allowed_schemes=None,
        )
        self.assertNotIn("\t", result)
        self.assertIn("%09", result)


if __name__ == "__main__":
    unittest.main()

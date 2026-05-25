"""Tests for :mod:`sources._prosemirror`.

The converter is deliberately small — these tests cover each supported
node type plus the unsupported-node fallback so changes to the
emit shape are picked up immediately.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from sources._prosemirror import (  # noqa: E402
    ProseMirrorError,
    prosemirror_to_markdown,
    strip_version_prefix,
)


def _md(payload) -> str:
    out, _unsupported = prosemirror_to_markdown(payload)
    return out


def _unsupported(payload) -> list[str]:
    _, unsupported = prosemirror_to_markdown(payload)
    return unsupported


class TestVersionPrefix(unittest.TestCase):
    def test_strip_v2(self) -> None:
        self.assertEqual(strip_version_prefix("[v2][1,2]"), "[1,2]")

    def test_strip_v10(self) -> None:
        self.assertEqual(strip_version_prefix("[v10][1]"), "[1]")

    def test_no_prefix_returns_none(self) -> None:
        self.assertIsNone(strip_version_prefix("[1,2]"))


class TestPlainParagraph(unittest.TestCase):
    def test_text_passthrough(self) -> None:
        self.assertEqual(_md([
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]},
        ]), "Hello")

    def test_two_paragraphs_join_with_blank_line(self) -> None:
        self.assertEqual(_md([
            {"type": "paragraph", "content": [{"type": "text", "text": "First"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "Second"}]},
        ]), "First\n\nSecond")

    def test_empty_paragraph_collapses(self) -> None:
        out = _md([
            {"type": "paragraph"},
            {"type": "paragraph", "content": [{"type": "text", "text": "X"}]},
        ])
        # leading empty paragraph should not produce three newlines
        self.assertEqual(out, "X")


class TestInlineMarks(unittest.TestCase):
    def test_bold(self) -> None:
        self.assertEqual(_md([
            {"type": "paragraph", "content": [
                {"type": "text", "text": "yes", "marks": [{"type": "bold"}]},
            ]},
        ]), "**yes**")

    def test_italic(self) -> None:
        self.assertEqual(_md([
            {"type": "paragraph", "content": [
                {"type": "text", "text": "x", "marks": [{"type": "italic"}]},
            ]},
        ]), "*x*")

    def test_code_inline(self) -> None:
        self.assertEqual(_md([
            {"type": "paragraph", "content": [
                {"type": "text", "text": "f()", "marks": [{"type": "code"}]},
            ]},
        ]), "`f()`")

    def test_link(self) -> None:
        self.assertEqual(_md([
            {"type": "paragraph", "content": [
                {"type": "text", "text": "anchor", "marks": [
                    {"type": "link", "attrs": {"href": "https://example.com"}}
                ]},
            ]},
        ]), "[anchor](https://example.com)")

    def test_bold_and_italic_compose(self) -> None:
        # italic applied inside bold (per the order map in _apply_marks)
        out = _md([
            {"type": "paragraph", "content": [
                {"type": "text", "text": "x", "marks": [
                    {"type": "bold"}, {"type": "italic"}
                ]},
            ]},
        ])
        self.assertEqual(out, "***x***")

    def test_strike(self) -> None:
        self.assertEqual(_md([
            {"type": "paragraph", "content": [
                {"type": "text", "text": "old", "marks": [{"type": "strike"}]},
            ]},
        ]), "~~old~~")


class TestBlockNodes(unittest.TestCase):
    def test_heading_level_clamping(self) -> None:
        self.assertEqual(_md([
            {"type": "heading", "attrs": {"level": 2},
             "content": [{"type": "text", "text": "T"}]},
        ]), "## T")
        # level 9 clamps to 6
        self.assertEqual(_md([
            {"type": "heading", "attrs": {"level": 9},
             "content": [{"type": "text", "text": "T"}]},
        ]), "###### T")

    def test_horizontal_rule(self) -> None:
        self.assertEqual(_md([{"type": "horizontalRule"}]), "---")

    def test_code_block(self) -> None:
        out = _md([{
            "type": "codeBlock",
            "attrs": {"language": "python"},
            "content": [{"type": "text", "text": "print('hi')"}],
        }])
        self.assertEqual(out, "```python\nprint('hi')\n```")

    def test_code_block_no_language(self) -> None:
        out = _md([{
            "type": "codeBlock",
            "content": [{"type": "text", "text": "raw"}],
        }])
        self.assertEqual(out, "```\nraw\n```")

    def test_bullet_list(self) -> None:
        out = _md([{
            "type": "bulletList",
            "content": [
                {"type": "listItem", "content": [
                    {"type": "paragraph", "content": [
                        {"type": "text", "text": "alpha"},
                    ]},
                ]},
                {"type": "listItem", "content": [
                    {"type": "paragraph", "content": [
                        {"type": "text", "text": "beta"},
                    ]},
                ]},
            ],
        }])
        self.assertEqual(out, "- alpha\n- beta")

    def test_bullet_list_aliases(self) -> None:
        # TipTap/Skool emits ``unorderedList`` / ``bullet_list`` /
        # ``unordered_list`` in addition to the canonical ``bulletList``.
        # Regression: all four must render identical Markdown.
        for type_name in (
            "bulletList", "unorderedList", "bullet_list", "unordered_list",
        ):
            out = _md([{
                "type": type_name,
                "content": [
                    {"type": "listItem", "content": [
                        {"type": "paragraph", "content": [
                            {"type": "text", "text": "alpha"},
                        ]},
                    ]},
                ],
            }])
            self.assertEqual(out, "- alpha", f"failed for type={type_name!r}")

    def test_ordered_list_aliases(self) -> None:
        for type_name in ("orderedList", "ordered_list"):
            out = _md([{
                "type": type_name,
                "content": [
                    {"type": "listItem", "content": [
                        {"type": "paragraph", "content": [
                            {"type": "text", "text": "alpha"},
                        ]},
                    ]},
                ],
            }])
            self.assertEqual(out, "1. alpha", f"failed for type={type_name!r}")

    def test_ordered_list(self) -> None:
        out = _md([{
            "type": "orderedList",
            "content": [
                {"type": "listItem", "content": [
                    {"type": "paragraph", "content": [
                        {"type": "text", "text": "first"},
                    ]},
                ]},
                {"type": "listItem", "content": [
                    {"type": "paragraph", "content": [
                        {"type": "text", "text": "second"},
                    ]},
                ]},
            ],
        }])
        self.assertEqual(out, "1. first\n2. second")

    def test_blockquote(self) -> None:
        out = _md([{
            "type": "blockquote",
            "content": [
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "wisdom"},
                ]},
            ],
        }])
        self.assertEqual(out, "> wisdom")

    def test_image(self) -> None:
        out = _md([{
            "type": "image",
            "attrs": {"src": "https://x/y.png", "alt": "Diagram"},
        }])
        self.assertEqual(out, "![Diagram](https://x/y.png)")


class TestUnsupportedNodes(unittest.TestCase):
    def test_unknown_block_emits_comment_and_records(self) -> None:
        out, unsupported = prosemirror_to_markdown([
            {"type": "tableOfContents"},
            {"type": "paragraph", "content": [{"type": "text", "text": "after"}]},
        ])
        self.assertIn("<!-- unsupported node: type=tableOfContents -->", out)
        self.assertIn("after", out)
        self.assertEqual(unsupported, ["tableOfContents"])


class TestRealSkoolDescriptor(unittest.TestCase):
    """Smoke test against the actual sanitized fixture."""

    def test_fixture_desc_converts_without_unsupported_nodes(self) -> None:
        import json
        import re
        fixture = _HERE / "fixtures" / "skool_lesson_youtube_embed.html"
        html = fixture.read_text(encoding="utf-8")
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
            html, re.DOTALL,
        )
        data = json.loads(m.group(1))
        lesson = (
            data["props"]["pageProps"]["course"]
                ["children"][0]["children"][0]["course"]
        )
        desc_raw = lesson["metadata"]["desc"]
        out, unsupported = prosemirror_to_markdown(desc_raw)
        self.assertTrue(out, "expected non-empty markdown")
        # We know from the sample that only paragraph/text/bold/codeBlock/
        # horizontalRule appear — no unsupported nodes expected.
        self.assertEqual(unsupported, [],
                         f"unexpected unsupported types: {unsupported}")
        # Body should contain the horizontal rule and a code fence.
        self.assertIn("---", out)
        self.assertIn("```", out)


class TestInputCoercion(unittest.TestCase):
    def test_dict_with_doc_wrapper(self) -> None:
        out = _md({
            "type": "doc",
            "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "hi"}]}],
        })
        self.assertEqual(out, "hi")

    def test_raw_v2_string(self) -> None:
        raw = '[v2][{"type":"paragraph","content":[{"type":"text","text":"x"}]}]'
        self.assertEqual(_md(raw), "x")

    def test_malformed_json_raises(self) -> None:
        with self.assertRaises(ProseMirrorError):
            prosemirror_to_markdown("[v2][not-json")

    def test_unsupported_payload_type_raises(self) -> None:
        with self.assertRaises(ProseMirrorError):
            prosemirror_to_markdown(42)


class TestEscaping(unittest.TestCase):
    def test_markdown_special_chars_escaped(self) -> None:
        # Plain "*" should not become a list marker / italic when raw.
        out = _md([{"type": "paragraph", "content": [
            {"type": "text", "text": "5*4 = 20"}
        ]}])
        self.assertEqual(out, r"5\*4 = 20")


class TestImageLinkBreakoutDefense(unittest.TestCase):
    """SEC-H2 regressions: image/link URLs must not break out of Markdown."""

    def test_image_src_parens_percent_encoded(self) -> None:
        # A malicious src with ')' would otherwise close the link early
        # and inject a second image as a tracking pixel.
        out = _md([{"type": "image", "attrs": {
            "src": "https://evil/x.png) ![](https://attacker/exfil",
            "alt": "ok",
        }}])
        # The whole src must remain inside one set of parens — count `(` opens.
        self.assertEqual(out.count("("), 1)
        self.assertEqual(out.count(")"), 1)
        self.assertIn("%29", out)  # closing paren got percent-encoded

    def test_image_alt_brackets_escaped(self) -> None:
        out = _md([{"type": "image", "attrs": {
            "src": "https://safe/x.png",
            "alt": "x](javascript:alert(1))[also_x",
        }}])
        # Both `]` and `[` in alt must be backslash-escaped.
        self.assertIn(r"\]", out)
        self.assertIn(r"\[", out)

    def test_javascript_scheme_dropped(self) -> None:
        out = _md([{"type": "image", "attrs": {
            "src": "javascript:alert(1)", "alt": "x",
        }}])
        self.assertEqual(out, "")

    def test_data_scheme_dropped(self) -> None:
        out = _md([{"type": "image", "attrs": {
            "src": "data:text/html,<script>alert(1)</script>",
            "alt": "x",
        }}])
        self.assertEqual(out, "")

    def test_link_href_parens_percent_encoded(self) -> None:
        out = _md([{"type": "paragraph", "content": [
            {"type": "text", "text": "x", "marks": [
                {"type": "link", "attrs": {
                    "href": "https://evil/?q=)](https://attacker/exfil"
                }}
            ]},
        ]}])
        self.assertEqual(out.count("("), 1)
        self.assertEqual(out.count(")"), 1)

    def test_recursion_error_caught_gracefully(self) -> None:
        # Build a deeply nested bulletList beyond _MAX_BLOCK_DEPTH.
        # The renderer must return SOME string + record the cap rather
        # than letting RecursionError escape.
        from sources._prosemirror import _MAX_BLOCK_DEPTH
        node: dict = {
            "type": "bulletList",
            "content": [{"type": "listItem", "content": [
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "leaf"}
                ]}
            ]}]
        }
        for _ in range(_MAX_BLOCK_DEPTH + 50):
            node = {
                "type": "bulletList",
                "content": [{"type": "listItem", "content": [node]}],
            }
        out, unsupported = prosemirror_to_markdown([node])
        # We don't care exactly what came out — just that it returned.
        self.assertIsInstance(out, str)
        # At least one entry should mark the depth cap.
        self.assertTrue(
            any("max-depth" in u or "recursion" in u for u in unsupported),
            f"expected depth-cap marker, got {unsupported}",
        )


if __name__ == "__main__":
    unittest.main()

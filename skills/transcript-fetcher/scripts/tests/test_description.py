"""Tests for :mod:`sources._description`.

The writer is a pure function that does file I/O — exercise both the
YAML rendering rules and the path derivation logic.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from sources._description import (  # noqa: E402
    description_path_for,
    write_description_md,
)


class TestDescriptionPath(unittest.TestCase):
    def test_strips_txt_suffix(self) -> None:
        self.assertEqual(
            description_path_for(Path("/tmp/a/out.txt")),
            Path("/tmp/a/out.description.md"),
        )

    def test_no_suffix(self) -> None:
        # Non-.txt -> append .description.md to the full name.
        self.assertEqual(
            description_path_for(Path("/tmp/a/out")),
            Path("/tmp/a/out.description.md"),
        )

    def test_double_dot_passthrough(self) -> None:
        self.assertEqual(
            description_path_for(Path("/tmp/foo.bar.txt")),
            Path("/tmp/foo.bar.description.md"),
        )


class TestYamlEscaping(unittest.TestCase):
    """The frontmatter must round-trip via a YAML parser."""

    def _round_trip(self, frontmatter: dict, body: str = "body") -> dict:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "x.txt"
            desc = write_description_md(
                out, frontmatter=frontmatter, title="Title", body=body
            )
            text = desc.read_text(encoding="utf-8")
            # Slice off the frontmatter (first --- ... ---).
            parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
            self.assertEqual(len(parts), 3, f"unexpected frontmatter shape: {text!r}")
            yaml_block = parts[1]
            return _tiny_yaml_loads(yaml_block)

    def test_simple_string_unquoted(self) -> None:
        out = self._round_trip({"key": "Plain Value"})
        self.assertEqual(out["key"], "Plain Value")

    def test_string_with_colon_is_quoted(self) -> None:
        # Colon in value would otherwise look like a nested key.
        out = self._round_trip({"key": "a: thing"})
        self.assertEqual(out["key"], "a: thing")

    def test_string_with_double_quote(self) -> None:
        out = self._round_trip({"key": 'say "hi"'})
        self.assertEqual(out["key"], 'say "hi"')

    def test_string_with_hash(self) -> None:
        out = self._round_trip({"key": "before # after"})
        self.assertEqual(out["key"], "before # after")

    def test_int_unquoted(self) -> None:
        out = self._round_trip({"duration_sec": 3120})
        self.assertEqual(out["duration_sec"], 3120)

    def test_bool_serialised(self) -> None:
        out = self._round_trip({"flag": True})
        self.assertEqual(out["flag"], True)

    def test_none_values_omitted(self) -> None:
        out = self._round_trip({"keep": "yes", "drop": None})
        self.assertIn("keep", out)
        self.assertNotIn("drop", out)


class TestListAndDictFrontmatter(unittest.TestCase):
    def test_list_renders(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "x.txt"
            desc = write_description_md(
                out,
                frontmatter={"tags": ["a", "b", "c"]},
                title=None,
                body="hello",
            )
            text = desc.read_text(encoding="utf-8")
            self.assertIn("tags:\n  - a\n  - b\n  - c", text)

    def test_empty_list_inline(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "x.txt"
            desc = write_description_md(
                out,
                frontmatter={"tags": []},
                title=None,
                body="hello",
            )
            self.assertIn("tags: []", desc.read_text(encoding="utf-8"))


class TestYamlBreakInjection(unittest.TestCase):
    """SEC-H1: YAML line-break chars (CR / LS / PS / NEL) must be escaped."""

    def _line_count(self, frontmatter: dict) -> int:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "x.txt"
            desc = write_description_md(
                out, frontmatter=frontmatter, title=None, body="b"
            )
            text = desc.read_text(encoding="utf-8")
            parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
            return len(parts[1].strip().splitlines())

    def test_cr_does_not_split_scalar(self) -> None:
        # A single key with a CR-containing value must still be ONE line.
        self.assertEqual(self._line_count({"k": "before\rafter"}), 1)

    def test_line_separator_does_not_split_scalar(self) -> None:
        self.assertEqual(self._line_count({"k": "before after"}), 1)

    def test_paragraph_separator_does_not_split_scalar(self) -> None:
        self.assertEqual(self._line_count({"k": "before after"}), 1)

    def test_nel_does_not_split_scalar(self) -> None:
        self.assertEqual(self._line_count({"k": "beforeafter"}), 1)

    def test_dict_key_with_newline_is_quoted(self) -> None:
        # Attacker-controlled key (from Skool resources[*]) must not
        # break out of the frontmatter via embedded ':\n'.
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "x.txt"
            desc = write_description_md(
                out,
                frontmatter={"resources": {"name\ninjected": "v"}},
                title=None, body="b",
            )
            text = desc.read_text(encoding="utf-8")
            # The newline must be escaped, so the malicious "injected:"
            # never appears as a bare top-level key.
            self.assertNotRegex(text, r"^injected:", )
            # The escaped form should appear in the frontmatter.
            self.assertIn("\\n", text)


class TestBodyAndHeading(unittest.TestCase):
    def test_h1_emitted_when_title_set(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "x.txt"
            desc = write_description_md(
                out,
                frontmatter={"k": "v"},
                title="Lecture 5",
                body="body text",
            )
            text = desc.read_text(encoding="utf-8")
            self.assertIn("# Lecture 5", text)
            self.assertIn("body text", text)

    def test_no_heading_when_title_none(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "x.txt"
            desc = write_description_md(
                out,
                frontmatter={"k": "v"},
                title=None,
                body="body",
            )
            text = desc.read_text(encoding="utf-8")
            self.assertNotIn("# ", text)
            self.assertIn("body", text)

    def test_title_with_leading_hash_normalised(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "x.txt"
            desc = write_description_md(
                out,
                frontmatter={},
                title="### Already a heading",
                body="b",
            )
            text = desc.read_text(encoding="utf-8")
            # Leading hashes get stripped so the heading is always H1
            self.assertIn("# Already a heading", text)


# --------------------------------------------------------------------- #
# Helpers: a tiny single-doc YAML parser for the round-trip assertions.
# Supports only what the writer emits: bare scalars, quoted strings,
# integers, booleans, and indented list/dict (one level).
# --------------------------------------------------------------------- #


def _tiny_yaml_loads(text: str) -> dict:
    result: dict = {}
    lines = text.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("  - "):
            # leftover bullets without a key — shouldn't happen at top level
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, sep, raw = line.partition(":")
        key = key.strip()
        raw = raw.strip()
        if raw == "":
            # Look for nested block (list-of-bullets or dict-of-keys).
            children = []
            i += 1
            while i < len(lines) and (lines[i].startswith("  - ") or lines[i].startswith("    ")):
                if lines[i].startswith("  - "):
                    children.append(_tiny_yaml_scalar(lines[i][4:].strip()))
                i += 1
            result[key] = children
            continue
        result[key] = _tiny_yaml_scalar(raw)
        i += 1
    return result


def _tiny_yaml_scalar(text: str):
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if text == "true":
        return True
    if text == "false":
        return False
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1].replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


if __name__ == "__main__":
    unittest.main()

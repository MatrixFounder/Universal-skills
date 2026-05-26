"""Unit tests for `wiki_ingest._frontmatter` — TASK 015 bead 015-03.

Locks the F2 frontmatter contract:
- Line-anchored close delimiter (TC-03-1 / L-C2).
- `warnings` out-parameter surfaces malformed lines (TC-03-2 / L-M5).
- `_splice_frontmatter_fields` leaves untouched fields byte-identical (TC-03-3).
- Splice preserves the trailing newline before the closer (TC-03-4 / L-H5).
- `_parse_flow_list` handles quoted entries containing commas (TC-03-5).
"""
from __future__ import annotations

import unittest

from wiki_ingest._frontmatter import (
    _parse_flow_list,
    _splice_frontmatter_fields,
    _strip_frontmatter_fast,
    split_frontmatter,
)


class TestCloseDelimiterLineAnchored(unittest.TestCase):
    """TC-UNIT-03-1 — the closer regex must be line-anchored (L-C2).

    The pre-May-2026 implementation used `content.find("\\n---", 3)`, which
    matched the FIRST `\\n---` substring anywhere — including `\\n----` (4
    dashes used as a markdown HR-style separator) and `\\n--- foo` (text
    after the dashes). These fixtures are written so the OLD implementation
    would terminate the frontmatter PREMATURELY; the new line-anchored
    `^---[ \\t]*$` regex must locate the real closer instead.
    """

    def test_four_dash_divider_inside_fm_does_not_close(self):
        """A `\\n----` substring (4 dashes) would defeat the old non-anchored
        scan but must be rejected as a closer by the new regex."""
        content = (
            "---\n"
            "title: real\n"
            "note: 'see ---- divider next'\n"
            "----\n"            # 4 dashes — NOT a valid closer (must be exactly ---)
            "title2: after\n"
            "---\n\n"
            "# Body\n"
        )
        fm, body = split_frontmatter(content)
        self.assertIn("title2", fm,
                      "if `----` (4 dashes) closed the frontmatter early, "
                      "`title2: after` would NOT be in the parsed dict — "
                      "L-C2 regression")
        self.assertEqual(fm.get("title"), "real")
        self.assertEqual(fm.get("title2"), "after")
        self.assertEqual(body, "\n# Body\n",
                         "body must begin AFTER the real `---` closer line")

    def test_dash_with_trailing_text_inside_fm_does_not_close(self):
        """A `\\n--- ` followed by text would also match the old find(), but
        must be rejected by the new regex (trailing `[ \\t]*$` is strict)."""
        content = (
            "---\n"
            "title: real\n"
            "--- this is not a closer, it has text after the dashes\n"
            "title2: after\n"
            "---\n\n"
            "BODY\n"
        )
        fm, _ = split_frontmatter(content)
        self.assertIn("title2", fm,
                      "trailing-text `---` line must not close the frontmatter "
                      "(L-C2)")

    def test_strip_fast_uses_same_delimiter_logic(self):
        """`_strip_frontmatter_fast` must mirror `split_frontmatter`'s closer
        detection so the body it returns is consistent."""
        content = (
            "---\n"
            "title: real\n"
            "----\n"            # 4 dashes — not a closer
            "title2: after\n"
            "---\n"
            "BODY\n"
        )
        self.assertEqual(_strip_frontmatter_fast(content), "BODY\n",
                         "fast strip must also skip the 4-dash false-closer")


class TestSplitFrontmatterWarningsOutParameter(unittest.TestCase):
    """TC-UNIT-03-2 — malformed top-level lines must be surfaced via the
    `warnings` out-parameter rather than silently dropped (L-M5)."""

    def test_malformed_line_recorded_in_warnings(self):
        content = (
            "---\n"
            "title: Good\n"
            "concepts;wrong\n"  # typo: ; instead of :
            "date: 2024-01-01\n"
            "---\n\n"
            "body\n"
        )
        warnings: list[str] = []
        fm, _ = split_frontmatter(content, warnings=warnings)
        self.assertEqual(fm.get("title"), "Good")
        self.assertEqual(fm.get("date"), "2024-01-01")
        self.assertNotIn("concepts", fm,
                         "the malformed line must NOT produce a key")
        self.assertEqual(len(warnings), 1,
                         "exactly one warning recorded")
        self.assertIn("concepts;wrong", warnings[0],
                      "warning must mention the offending line")

    def test_no_warnings_argument_silently_skips(self):
        content = (
            "---\n"
            "title: Good\n"
            "malformed-line-here\n"
            "---\n\n"
            "body\n"
        )
        # No `warnings=` → silent backward-compat behaviour
        fm, _ = split_frontmatter(content)
        self.assertEqual(fm, {"title": "Good"})


class TestSplicePreservesUnchangedFields(unittest.TestCase):
    """TC-UNIT-03-3 — `_splice_frontmatter_fields` rebuilds ONLY the named
    fields; every other line is byte-identical to the input."""

    INPUT = (
        "---\n"
        'title: "Source A"\n'
        "date: 2024-01-15\n"
        "concepts:\n"
        "  - Alpha\n"
        "  - Beta\n"
        "---\n\n"
        "# Body of Source A\n"
        "\n"
        "## TL;DR\n"
        "\n"
        "Body content that must survive byte-identical.\n"
    )

    def test_only_concepts_rebuilt(self):
        fm, _ = split_frontmatter(self.INPUT)
        fm["concepts"] = ["AlphaNew", "BetaNew", "GammaNew"]
        out = _splice_frontmatter_fields(self.INPUT, ["concepts"], fm)
        # title + date lines preserved verbatim
        self.assertIn('title: "Source A"', out)
        self.assertIn("date: 2024-01-15", out)
        # new concepts present, old ones absent
        self.assertIn("AlphaNew", out)
        self.assertIn("GammaNew", out)
        self.assertNotIn("- Alpha\n", out, "old Alpha must be gone after splice")
        # body completely unchanged
        body_after = out.split("---\n", 2)[-1]
        body_before = self.INPUT.split("---\n", 2)[-1]
        self.assertEqual(body_after, body_before,
                         "body must be byte-identical to input")

    def test_field_not_present_is_noop(self):
        """Splice is REPLACE-only: if the field doesn't already exist in
        the frontmatter, the splice is a no-op (the text is returned
        unchanged). Callers needing insertion must add the key line first.
        """
        fm, _ = split_frontmatter(self.INPUT)
        fm["new_field"] = ["X"]
        out = _splice_frontmatter_fields(self.INPUT, ["new_field"], fm)
        # No `new_field:` line existed → splice has nothing to replace → text unchanged
        self.assertEqual(out, self.INPUT,
                         "missing field must be a no-op (splice is replace-only)")


class TestSpliceKeepsCloserNewline(unittest.TestCase):
    """TC-UNIT-03-4 — regression for the `Normal Name---` collision bug
    discovered during the May 2026 VDD-multi interactive smoke test (L-H5)."""

    def test_rebuilt_list_does_not_collide_with_closer(self):
        content = (
            "---\n"
            'title: "Tricky"\n'
            "concepts:\n"
            "  - One\n"
            "  - Two\n"
            "  - Normal Name\n"
            "---\n\n"
            "# Body\n"
        )
        fm, _ = split_frontmatter(content)
        # Replace one entry; simulate the normalise-and-re-splice path
        fm["concepts"] = ["One", "Two", "Renamed Name"]
        out = _splice_frontmatter_fields(content, ["concepts"], fm)
        self.assertIn("Renamed Name\n---", out,
                      "the last list item must be followed by `\\n---`, not "
                      "`Renamed Name---` (collision bug)")
        self.assertNotIn("Name---", out,
                         "no item-name immediately concatenated with `---`")

    def test_round_trip_idempotent(self):
        """Splice once → parse → splice again with same data → unchanged.

        Exercises the collision-prone path with an entry whose name ends
        in `Name` (mirrors the May-2026 `Normal Name---` collision-bug
        fixture). LOW-1 hardening: locks idempotency on the same fixture
        class that the L-H5 fix had to address, not on the trivial path.
        """
        content = (
            "---\n"
            "concepts:\n"
            "  - One\n"
            "  - Two\n"
            "  - Renamed Name\n"
            "---\n"
            "body\n"
        )
        fm, _ = split_frontmatter(content)
        out1 = _splice_frontmatter_fields(content, ["concepts"], fm)
        fm2, _ = split_frontmatter(out1)
        out2 = _splice_frontmatter_fields(out1, ["concepts"], fm2)
        self.assertEqual(out1, out2,
                         "splice must be idempotent under round-trip on the "
                         "collision-prone Renamed-Name fixture")
        # Defense in depth — the `\n---` boundary must NOT regress in out2.
        self.assertIn("Renamed Name\n---", out2,
                      "after round-trip, last item must still be followed "
                      "by `\\n---`, not collide with the closer")


class TestParseFlowListQuoting(unittest.TestCase):
    """TC-UNIT-03-5 — quoted entries containing commas must NOT be split."""

    def test_quoted_with_comma(self):
        result = _parse_flow_list('[a, "b, c", d]')
        self.assertEqual(result, ["a", "b, c", "d"])

    def test_single_quoted(self):
        result = _parse_flow_list("[a, 'b, c', d]")
        self.assertEqual(result, ["a", "b, c", "d"])

    def test_empty_list(self):
        self.assertEqual(_parse_flow_list("[]"), [])

    def test_no_quotes(self):
        self.assertEqual(_parse_flow_list("[alpha, beta, gamma]"),
                         ["alpha", "beta", "gamma"])

    def test_strips_inner_whitespace(self):
        self.assertEqual(_parse_flow_list("[  a  ,  b  ,  c  ]"),
                         ["a", "b", "c"])


# =============================================================================
# TASK 016 bead 016-02 — _splice_frontmatter_fields list[dict] support
# =============================================================================


class TestSpliceListOfDicts(unittest.TestCase):
    """TC-UNIT-016-02-01..07"""

    def test_write_new_list_of_dicts(self):
        """TC-UNIT-016-02-01"""
        text = (
            "---\n"
            "name: Foo\n"
            "promoted_from:\n"
            "---\n"
            "# body\n"
        )
        fm = {"promoted_from": [{"course": "A", "date": "2026-05-26"}]}
        out = _splice_frontmatter_fields(text, ["promoted_from"], fm)
        self.assertIn("promoted_from:", out)
        self.assertIn("- course:", out)
        # Round-trip parse — the on-disk YAML form may or may not quote
        # plain-string scalars (quoting kicks in only for values with
        # metacharacters); what matters is round-trip equivalence.
        new_fm, _ = split_frontmatter(out)
        self.assertEqual(new_fm["promoted_from"],
                         [{"course": "A", "date": "2026-05-26"}])

    def test_update_existing_list_of_dicts(self):
        """TC-UNIT-016-02-02"""
        text = (
            "---\n"
            "promoted_from:\n"
            "  - course: A\n"
            "    date: 2026-05-26\n"
            "---\n"
            "body\n"
        )
        fm = {"promoted_from": [
            {"course": "A", "date": "2026-05-26"},
            {"course": "B", "date": "2026-05-26"},
        ]}
        out = _splice_frontmatter_fields(text, ["promoted_from"], fm)
        new_fm, _ = split_frontmatter(out)
        self.assertEqual(len(new_fm["promoted_from"]), 2)
        names = sorted(item["course"] for item in new_fm["promoted_from"])
        self.assertEqual(names, ["A", "B"])

    def test_remove_field_when_value_is_none(self):
        """TC-UNIT-016-02-03"""
        text = (
            "---\n"
            "name: Foo\n"
            "promoted_from:\n"
            "  - course: A\n"
            "    date: 2026-05-26\n"
            "kind: concept\n"
            "---\n"
            "body\n"
        )
        out = _splice_frontmatter_fields(text, ["promoted_from"],
                                         {"promoted_from": None})
        new_fm, _ = split_frontmatter(out)
        self.assertNotIn("promoted_from", new_fm,
                         "value=None must REMOVE the field entirely")
        # Other fields preserved
        self.assertEqual(new_fm.get("name"), "Foo")
        self.assertEqual(new_fm.get("kind"), "concept")

    def test_round_trip_parse_splice_parse(self):
        """TC-UNIT-016-02-04"""
        text = (
            "---\n"
            "promoted_from:\n"
            "---\n"
            "body\n"
        )
        fm = {"promoted_from": [
            {"course": "Hermes", "date": "2026-01-01"},
            {"course": "OpenClaw", "date": "2026-05-26"},
        ]}
        once = _splice_frontmatter_fields(text, ["promoted_from"], fm)
        parsed_fm, _ = split_frontmatter(once)
        # Splice the same data back in: should be byte-identical (idempotent)
        twice = _splice_frontmatter_fields(once, ["promoted_from"], parsed_fm)
        self.assertEqual(once, twice)

    def test_course_name_with_spaces_round_trips(self):
        """TC-UNIT-016-02-05 — course names containing spaces round-trip.

        The parser handles unquoted multi-word values; explicit quoting is
        not required. The contract is round-trip equivalence, not literal
        quote form.
        """
        text = "---\npromoted_from:\n---\nbody\n"
        fm = {"promoted_from": [{"course": "Course A", "date": "2026-05-26"}]}
        out = _splice_frontmatter_fields(text, ["promoted_from"], fm)
        new_fm, _ = split_frontmatter(out)
        self.assertEqual(new_fm["promoted_from"][0]["course"], "Course A")
        self.assertEqual(new_fm["promoted_from"][0]["date"], "2026-05-26")

    def test_list_of_strings_path_unchanged(self):
        """TC-UNIT-016-02-06 — regression: list[str] behaviour preserved."""
        text = "---\nconcepts:\n  - old\n---\nbody\n"
        fm = {"concepts": ["a", "b", "c"]}
        out = _splice_frontmatter_fields(text, ["concepts"], fm)
        new_fm, _ = split_frontmatter(out)
        self.assertEqual(new_fm["concepts"], ["a", "b", "c"])
        # No accidental dict-style emission for scalar list
        self.assertNotIn("- a:", out)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for `wiki_ingest._classify` — TASK 015 bead 015-05.

Locks the F3-helper classify contract:
- `_count_md_structure` rejects NUL-byte / high-replacement-ratio binaries (TC-05-1 / L-M8).
- `_filename_hint_score` is segment-aware (TC-05-2).
- `_detect_grouping` distinguishes prefix / sibling / flat (TC-05-3).
- `_UNGROUPED_SENTINEL` is a process-unique object that cannot collide
  with any literal regex capture (TC-05-4).
- `_looks_like_wiki_summary` streams only the first 1 KiB (TC-05-5 / P-L6).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wiki_ingest._classify import (
    _UNGROUPED_LABEL,
    _UNGROUPED_SENTINEL,
    _count_md_structure,
    _detect_grouping,
    _filename_hint_score,
    _group_files,
    _looks_like_wiki_summary,
)


class TestCountMdStructureRejectsBinaryMasquerade(unittest.TestCase):
    """TC-UNIT-05-1 — NUL-byte and high-replacement-ratio binary files
    must NOT win `_pick_primary` over real markdown (L-M8)."""

    def test_nul_byte_file_is_non_prose(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "binary.bin"
            path.write_bytes(b"some text before\x00the nul byte\n")
            size, h2, fences, prose = _count_md_structure(path)
            self.assertFalse(prose,
                             "file containing a NUL byte must NOT be marked prose")
            self.assertEqual(h2, 0)
            self.assertEqual(fences, 0)
            self.assertGreater(size, 0,
                               "size is still reported (caller may need it)")

    def test_high_replacement_ratio_is_non_prose(self):
        """Random binary that decodes to >5% U+FFFD characters → non-prose."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "random.bin"
            # 8 KiB of high-bit-set bytes that won't decode cleanly as UTF-8
            path.write_bytes(bytes(range(128, 256)) * 64)  # 128 unique bytes × 64 = 8 KiB
            _, _, _, prose = _count_md_structure(path)
            self.assertFalse(prose,
                             "high replacement-ratio binary must NOT be marked prose")

    def test_real_markdown_is_prose(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "real.md"
            path.write_text(
                "# Title\n\nThis is a long sentence that ends with a period so the "
                "heuristic prose check finds it.\n\n## Section\n\n```py\nprint(1)\n```\n",
                encoding="utf-8",
            )
            _, h2, fences, prose = _count_md_structure(path)
            self.assertTrue(prose, "real markdown must be marked prose")
            self.assertEqual(h2, 1)
            self.assertEqual(fences, 2, "two ``` lines → fence_count=2")


class TestFilenameHintScoreSegmentAware(unittest.TestCase):
    """TC-UNIT-05-2 — segment match must be EXACT, not substring."""

    def test_speculation_does_not_match_spec(self):
        # `spec` is in _NON_PRIMARY_HINTS; substring would falsely tag `speculation`
        self.assertEqual(_filename_hint_score("speculation"), 0,
                         "`speculation` must NOT score as negative; segment != hint")

    def test_transcript_hits_primary(self):
        # `transcript` is in _PRIMARY_HINTS; right-most segment → 3× weight × +2
        self.assertGreater(_filename_hint_score("transcript"), 0)

    def test_segment_split_on_separators(self):
        # `lesson-notes` → segments [lesson, notes]; rightmost (notes) is non-primary
        # → −6; lesson is positive but with weight 1 → +2; total = −4
        self.assertEqual(_filename_hint_score("lesson-notes"), -4)

    def test_rightmost_segment_is_most_weighted(self):
        # Right-most segment carries 3× weight; others carry 1×
        right_only = _filename_hint_score("transcript")  # +2 × 3 = +6
        left_only = _filename_hint_score("transcript-meta")  # +2 (1×) + 0 = +2
        self.assertGreater(right_only, left_only,
                           "right-most segment must dominate the score")


class TestDetectGroupingPattern(unittest.TestCase):
    """TC-UNIT-05-3 — three patterns: prefix, sibling, flat."""

    def test_prefix_pattern(self):
        files = ["01-intro.txt", "02-body.txt", "03-summary.md"]
        pattern, info = _detect_grouping(files)
        self.assertEqual(pattern, "prefix")
        self.assertIn("regex", info)
        self.assertIn("matched", info)

    def test_sibling_pattern(self):
        # Multiple files sharing a base before the first dot
        files = ["lesson.txt", "lesson.description.md", "lesson.txt.stat.json"]
        pattern, info = _detect_grouping(files)
        self.assertEqual(pattern, "sibling")
        self.assertIn("shared_bases", info)
        self.assertIn("lesson", info["shared_bases"])

    def test_flat_pattern(self):
        # Unrelated files: no prefix, no shared base
        files = ["alpha.txt", "beta.md", "gamma.json"]
        pattern, _ = _detect_grouping(files)
        self.assertEqual(pattern, "flat")

    def test_empty_input(self):
        pattern, info = _detect_grouping([])
        self.assertEqual(pattern, "flat")
        self.assertIsNone(info)


class TestUngroupedSentinelNoCollision(unittest.TestCase):
    """TC-UNIT-05-4 — the sentinel must not collide with any string key."""

    def test_sentinel_is_not_a_string(self):
        self.assertNotIsInstance(_UNGROUPED_SENTINEL, str,
                                 "sentinel must be a plain object, not a str")
        # It must NOT equal any literal regex-capture string
        for candidate in ("_ungrouped", "<ungrouped>", _UNGROUPED_LABEL, "", "0", "01"):
            self.assertNotEqual(
                _UNGROUPED_SENTINEL, candidate,
                f"sentinel must NOT compare equal to literal {candidate!r}",
            )

    def test_grouping_uses_sentinel_for_unmatched_files(self):
        # Mix of prefix-matched and unmatched filenames
        files = ["01-a.txt", "02-b.txt", "stray.txt", "another.txt"]
        groups = _group_files(files, "prefix")
        # `01` and `02` are strings; `stray.txt`/`another.txt` go under sentinel
        string_keys = [k for k in groups if isinstance(k, str)]
        self.assertEqual(set(string_keys), {"01", "02"})
        self.assertIn(_UNGROUPED_SENTINEL, groups,
                      "files that didn't match must land under the sentinel")
        self.assertEqual(set(groups[_UNGROUPED_SENTINEL]),
                         {"stray.txt", "another.txt"})

    def test_sentinel_identity_across_imports(self):
        # The sentinel must be the SAME object on re-import (module-level singleton)
        from wiki_ingest._classify import _UNGROUPED_SENTINEL as resaved
        self.assertIs(_UNGROUPED_SENTINEL, resaved,
                      "sentinel must be a module-level singleton (same identity)")


class TestLooksLikeWikiSummaryStreams1KB(unittest.TestCase):
    """TC-UNIT-05-5 — file must be streamed (max 1024 bytes read), not slurped."""

    def test_detects_summary_in_first_1kb(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.md"
            path.write_text(
                "---\ntitle: Foo\ntype: lesson-summary\n---\n\n# Body\n",
                encoding="utf-8",
            )
            self.assertTrue(_looks_like_wiki_summary(path))

    def test_detects_kind_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.md"
            path.write_text(
                "---\nkind: source\n---\n\nbody\n",
                encoding="utf-8",
            )
            self.assertTrue(_looks_like_wiki_summary(path))

    def test_does_not_read_past_1kb(self):
        """The function MUST call `f.read(1024)` — not `f.read()` or
        `read_text()`. Verified by monkeypatching `read` on the file
        handle to assert the requested byte count is exactly 1024.
        """
        seen_sizes: list = []

        original_open = Path.open

        def tracking_open(self, *args, **kwargs):
            f = original_open(self, *args, **kwargs)
            real_read = f.read

            def tracking_read(n=-1):
                seen_sizes.append(n)
                return real_read(n)
            f.read = tracking_read
            return f

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.md"
            # 2 MB file — function must NOT slurp the whole thing
            path.write_text("x" * (2 * 1024 * 1024), encoding="utf-8")
            with mock.patch.object(Path, "open", tracking_open):
                _looks_like_wiki_summary(path)
        # The first read call should be for 1024 bytes (P-L6)
        self.assertEqual(
            seen_sizes[0], 1024,
            f"first read() should request 1024 bytes (P-L6); got {seen_sizes[0]}. "
            f"All reads: {seen_sizes}",
        )

    def test_missing_file_returns_false(self):
        self.assertFalse(_looks_like_wiki_summary(Path("/nonexistent/file.md")))


if __name__ == "__main__":
    unittest.main()

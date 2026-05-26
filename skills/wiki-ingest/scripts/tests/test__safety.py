"""Unit tests for `wiki_ingest._safety` — TASK 015 bead 015-01.

Locks the F1 safety contract:
- NFKC normalisation in `slugify` (TC-01-1).
- Traversal / control-char / metacharacter rejection in `_safe_name` (TC-01-2).
- Atomicity of `_atomic_write_text` under mid-write failure (TC-01-3).
- Symlink refusal in `read_text` (TC-01-4).
- Control-char strip + length cap in `_safe_for_json` (TC-01-5).

These tests target `wiki_ingest._safety` directly (not the historical
`wiki_ops.<symbol>` re-export). If a future bead deletes the re-export
shim in `wiki_ops.py`, these tests do NOT need to change.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wiki_ingest._safety import (
    MAX_VALUE_BYTES,
    _atomic_write_text,
    _safe_for_json,
    _safe_name,
    read_text,
    slugify,
)


class TestSlugifyNFKC(unittest.TestCase):
    """TC-UNIT-01-1 — composed vs decomposed Unicode collapse onto the same slug."""

    def test_nfkc_composed_decomposed_collapse(self):
        # "Café" in NFC (composed: é = U+00E9) vs NFD (decomposed: e + U+0301)
        composed = "Café"
        decomposed = "Café"
        self.assertNotEqual(composed, decomposed,
                            "fixture sanity: the two inputs must differ as raw strings")
        self.assertEqual(slugify(composed), slugify(decomposed),
                         "NFKC normalisation must collapse composed/decomposed forms")

    def test_nfkc_fullwidth_collapse(self):
        # Fullwidth digits (NFKC-compatible) should normalise to ASCII
        self.assertEqual(slugify("ＡＢＣ"), slugify("ABC"))

    def test_cyrillic_a_vs_latin_a_are_distinct(self):
        # Cyrillic А (U+0410) is NOT NFKC-equivalent to Latin A (U+0041);
        # the slug should still differ — defends against silent confusable
        # collapse where two different concepts share one filename.
        self.assertNotEqual(slugify("Аnchor"), slugify("Anchor"))


class TestSafeNameRejects(unittest.TestCase):
    """TC-UNIT-01-2 — every malicious / structural input must trigger die()."""

    REJECTIONS = [
        "../etc",
        "/etc",
        "\\windows",
        ".hidden",
        "foo\x00bar",
        "foo|bar",
        "{{name}}",
        "with[bracket",
        "with]bracket",
        "with^caret",
    ]

    def test_rejects_each_unsafe_input(self):
        for bad in self.REJECTIONS:
            with self.subTest(input=bad):
                with self.assertRaises(SystemExit) as cm:
                    _safe_name(bad, kind="name")
                self.assertNotEqual(
                    cm.exception.code, 0,
                    f"_safe_name({bad!r}) must die() with non-zero exit",
                )

    def test_accepts_clean_unicode_name(self):
        # Should round-trip cleanly (returns NFKC-normalised form)
        self.assertEqual(_safe_name("Hermes Agent", "name"), "Hermes Agent")
        self.assertEqual(_safe_name("Café", "name"), "Café")


class TestAtomicWriteUnderFailure(unittest.TestCase):
    """TC-UNIT-01-3 — mid-write failure must leave old content intact.

    Under `os.fsync` failure, the temp file is created and (possibly)
    written, but `os.replace` is never reached. The original file at
    `path` must still hold its previous content.
    """

    def test_fsync_failure_preserves_old_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "page.md"
            target.write_text("old content", encoding="utf-8")
            real_fsync = os.fsync

            def boom(fd):  # noqa: ARG001
                raise OSError("simulated fsync failure")

            with mock.patch("wiki_ingest._safety.os.fsync", side_effect=boom):
                with self.assertRaises(OSError):
                    _atomic_write_text(target, "new content that must not land")

            # restore for any subsequent tests run in the same process
            self.assertEqual(os.fsync, real_fsync, "fsync patch must be reverted")
            # The KEY assertion: the original is untouched.
            self.assertEqual(
                target.read_text(encoding="utf-8"), "old content",
                "old content must be preserved after fsync failure",
            )
            # M2-015-01 — the tmp file MUST be cleaned up, not orphaned.
            orphans = list(Path(tmp).glob(".page.md.*.tmp"))
            self.assertEqual(
                orphans, [],
                f"M2-015-01: orphan tmp files leaked on fsync failure: {orphans}",
            )


class TestReadTextRefusesSymlink(unittest.TestCase):
    """TC-UNIT-01-4 — symlinked entries inside the vault must NOT be followed."""

    def test_symlink_returns_empty_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target = tmp_path / "real_secret.txt"
            target.write_text("would-be-exfiltrated secret", encoding="utf-8")
            link = tmp_path / "looks_innocent.md"
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError):
                self.skipTest("filesystem does not support symlinks")
            # The link itself is a symlink → read_text must skip it.
            self.assertEqual(
                read_text(link), "",
                "read_text must refuse to follow a symlink (returns '')",
            )

    def test_regular_file_still_readable(self):
        # Sanity: the symlink-refusal does not break legitimate reads.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "page.md"
            target.write_text("hello world", encoding="utf-8")
            self.assertEqual(read_text(target), "hello world")


class TestSafeForJson(unittest.TestCase):
    """TC-UNIT-01-5 — control-char strip + length cap on every JSON-bound scalar."""

    def test_strips_control_characters(self):
        out = _safe_for_json("Hi\x07there\x01end")
        self.assertEqual(out, "Hithereend")

    def test_truncates_long_strings(self):
        long = "x" * (MAX_VALUE_BYTES + 500)
        out = _safe_for_json(long)
        self.assertTrue(
            out.startswith("x" * MAX_VALUE_BYTES),
            "truncated output must begin with MAX_VALUE_BYTES of original",
        )
        self.assertIn("[truncated,", out, "must mark truncation explicitly")

    def test_recurses_into_lists_and_dicts(self):
        out = _safe_for_json({"title": "Hi\x07there", "items": ["a\x07b", "c"]})
        self.assertEqual(out, {"title": "Hithere", "items": ["ab", "c"]})

    def test_passes_through_non_strings(self):
        self.assertEqual(_safe_for_json(42), 42)
        self.assertEqual(_safe_for_json(True), True)
        self.assertEqual(_safe_for_json(None), None)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for `wiki_ingest._vault` — TASK 015 bead 015-04.

Locks the F3-helper vault contract:
- `_walk_pages` skips symlinks (TC-04-1 / OVERLAP-5).
- `load_vault_pages` buckets pages by subdir correctly (TC-04-2).
- `tail_log` ignores `## [date]` headings inside fenced examples (TC-04-3 / L-M6).
- `load_asset` resolves to the bundled `assets/` directory (TC-04-4).
- `ensure_schema` exits with code 2 when `WIKI_SCHEMA.md` is missing (TC-04-5).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wiki_ingest._vault import (
    ASSETS_DIR,
    DEFAULT_SUBDIRS,
    SCHEMA_FILE,
    _walk_pages,
    ensure_schema,
    load_asset,
    load_vault_pages,
    tail_log,
)


def _seed_vault(root: Path) -> None:
    """Minimal vault skeleton for tests that need the directory layout."""
    (root / SCHEMA_FILE).write_text("# Schema\n", encoding="utf-8")
    (root / "index.md").write_text("# Index\n", encoding="utf-8")
    (root / "log.md").write_text("# Log\n", encoding="utf-8")
    for sub in DEFAULT_SUBDIRS:
        (root / sub).mkdir()


class TestWalkPagesSkipsSymlinks(unittest.TestCase):
    """TC-UNIT-04-1 — symlinks inside the vault must NOT be yielded
    by `_walk_pages` (OVERLAP-5)."""

    def test_symlink_to_outside_target_not_yielded(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _seed_vault(vault)
            # Plant a benign real concept and a malicious symlink alongside.
            real = vault / "_concepts" / "Real.md"
            real.write_text(
                "---\nname: Real\nkind: concept\n---\n# Real\n",
                encoding="utf-8",
            )
            outside = Path(tmp) / "secret.md"
            outside.write_text("would-be exfiltrated", encoding="utf-8")
            link = vault / "_concepts" / "MALICIOUS.md"
            try:
                link.symlink_to(outside)
            except (NotImplementedError, OSError):
                self.skipTest("filesystem does not support symlinks")
            yielded = [p.name for p in _walk_pages(vault)]
            self.assertIn("Real.md", yielded,
                          "the real concept must be yielded")
            self.assertNotIn("MALICIOUS.md", yielded,
                             "the symlinked concept MUST be skipped (OVERLAP-5)")

    def test_yields_pages_in_sorted_order(self):
        """Determinism guarantee — `_walk_pages` must return paths in
        sorted order so JSON outputs downstream are stable."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _seed_vault(vault)
            for name in ("Zulu", "Alpha", "Mike"):
                (vault / "_concepts" / f"{name}.md").write_text(
                    "# x\n", encoding="utf-8",
                )
            names = [p.stem for p in _walk_pages(vault)
                     if p.parent.name == "_concepts"]
            self.assertEqual(names, sorted(names),
                             "concepts must be yielded in sorted order")


class TestLoadVaultPagesBuckets(unittest.TestCase):
    """TC-UNIT-04-2 — `load_vault_pages` puts pages into the right buckets."""

    def test_subdir_buckets(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _seed_vault(vault)
            (vault / "_concepts" / "C1.md").write_text(
                "---\ntitle: C1\nkind: concept\n---\nbody\n", encoding="utf-8",
            )
            (vault / "_concepts" / "C2.md").write_text(
                "---\ntitle: C2\nkind: concept\n---\nbody\n", encoding="utf-8",
            )
            (vault / "_entities" / "E1.md").write_text(
                "---\ntitle: E1\nkind: entity\n---\nbody\n", encoding="utf-8",
            )
            (vault / "_sources" / "S1.md").write_text(
                "---\ntitle: S1\nkind: source\n---\nbody\n", encoding="utf-8",
            )
            # root-level stray page → goes into "other"
            (vault / "stray.md").write_text(
                "---\ntitle: Stray\n---\nbody\n", encoding="utf-8",
            )
            out = load_vault_pages(vault)
            self.assertEqual(set(out["concepts"].keys()), {"C1", "C2"})
            self.assertEqual(set(out["entities"].keys()), {"E1"})
            self.assertEqual(set(out["sources"].keys()), {"S1"})
            self.assertEqual(len(out["other"]), 1)
            self.assertEqual(out["other"][0]["title"], "Stray")

    def test_index_log_schema_excluded_from_other(self):
        """The 3 root-level system files must NOT surface in `other`."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _seed_vault(vault)
            out = load_vault_pages(vault)
            self.assertEqual(out["other"], [],
                             "no stray pages → 'other' bucket is empty even "
                             "though index.md/log.md/WIKI_SCHEMA.md exist")


class TestTailLogIgnoresFencedCode(unittest.TestCase):
    """TC-UNIT-04-3 — `## [date]` headings inside fenced examples must NOT
    be surfaced as real log entries (L-M6)."""

    def test_fenced_heading_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _seed_vault(vault)
            (vault / "log.md").write_text(
                "---\nname: log\n---\n\n# Log\n\n"
                "## [2024-01-01] real | initial seed\n\n"
                "```\n"
                "## [2024-02-02] fake | inside fence — must NOT surface\n"
                "```\n\n"
                "## [2024-03-03] also-real | second entry\n",
                encoding="utf-8",
            )
            entries = tail_log(vault, 5)
            self.assertEqual(len(entries), 2,
                             "exactly two REAL headings (fenced one skipped)")
            self.assertIn("real", entries[0])
            self.assertIn("also-real", entries[1])
            for entry in entries:
                self.assertNotIn("fake", entry,
                                 "the fenced-example heading must NOT leak")

    def test_missing_log_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            # no log.md created
            self.assertEqual(tail_log(vault, 5), [])


class TestLoadAsset(unittest.TestCase):
    """TC-UNIT-04-4 — `load_asset` resolves bundled templates via ASSETS_DIR."""

    def test_resolves_known_template(self):
        # `WIKI_SCHEMA.template.md` is committed under assets/.
        text = load_asset("WIKI_SCHEMA.template.md")
        self.assertTrue(text, "asset must be non-empty")
        # Verify it routed through the actual bundle dir, not somewhere else.
        self.assertTrue(
            ASSETS_DIR.is_dir(),
            f"ASSETS_DIR must resolve to a real directory; got {ASSETS_DIR}",
        )

    def test_missing_asset_dies(self):
        with self.assertRaises(SystemExit) as cm:
            load_asset("absolutely-not-a-real-asset.md")
        self.assertNotEqual(cm.exception.code, 0,
                            "missing asset must die() with non-zero exit")


class TestEnsureSchema(unittest.TestCase):
    """TC-UNIT-04-5 — `ensure_schema` exits with code 2 when missing."""

    def test_dies_with_code_2_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "empty"
            vault.mkdir()
            # no WIKI_SCHEMA.md created
            with self.assertRaises(SystemExit) as cm:
                ensure_schema(vault)
            self.assertEqual(
                cm.exception.code, 2,
                "missing schema must exit with code 2 (the documented "
                "'missing schema' code)",
            )

    def test_passes_silently_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            vault.mkdir()
            (vault / SCHEMA_FILE).write_text("# schema\n", encoding="utf-8")
            # Should NOT raise
            ensure_schema(vault)


if __name__ == "__main__":
    unittest.main()

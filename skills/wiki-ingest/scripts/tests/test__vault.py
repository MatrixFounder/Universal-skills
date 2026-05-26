"""Unit tests for `wiki_ingest._vault`.

TASK 015 bead 015-04 — F3-helper vault contract:
- `_walk_pages` skips symlinks (TC-04-1 / OVERLAP-5).
- `load_vault_pages` buckets pages by subdir correctly (TC-04-2).
- `tail_log` ignores `## [date]` headings inside fenced examples (TC-04-3 / L-M6).
- `load_asset` resolves to the bundled `assets/` directory (TC-04-4).
- `ensure_schema` exits with code 2 when `WIKI_SCHEMA.md` is missing (TC-04-5).

TASK 016 bead 016-00 — two-tier discovery contract (TC-016-00-01..10):
- `find_vault_root` discovers `(course_root, vault_root_or_None)` walking up.
- `discover_courses` enumerates v1.x course roots under a v2.0 vault root.
- Both refuse symlinks; `find_vault_root` refuses cross-fs traversal.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from wiki_ingest._vault import (
    ASSETS_DIR,
    DEFAULT_SUBDIRS,
    SCHEMA_FILE,
    _walk_pages,
    discover_courses,
    ensure_schema,
    find_vault_root,
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


# =============================================================================
# TASK 016 bead 016-00 — two-tier discovery
# =============================================================================


def _write_schema(path: Path, version: str, kind: str = "wiki-root") -> None:
    """Helper: write a `WIKI_SCHEMA.md` with the given schema_version."""
    path.write_text(
        f"---\nschema_version: \"{version}\"\nkind: {kind}\n---\n# Schema\n",
        encoding="utf-8",
    )


def _seed_course(course_root: Path, version: str = "1.0") -> None:
    """Helper: minimal course-local layer."""
    course_root.mkdir(parents=True, exist_ok=True)
    _write_schema(course_root / SCHEMA_FILE, version, kind="course")
    for sub in DEFAULT_SUBDIRS:
        (course_root / sub).mkdir(exist_ok=True)


class TestPeekSchemaVersion(unittest.TestCase):
    """Direct unit tests for the private `_peek_schema_version` probe."""

    def test_reads_v2_root_schema(self):
        from wiki_ingest._vault import _peek_schema_version
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "WIKI_SCHEMA.md"
            _write_schema(p, "2.0", kind="vault-root")
            self.assertEqual(_peek_schema_version(p), "2.0")

    def test_reads_v1_course_schema(self):
        from wiki_ingest._vault import _peek_schema_version
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "WIKI_SCHEMA.md"
            _write_schema(p, "1.0", kind="course")
            self.assertEqual(_peek_schema_version(p), "1.0")

    def test_returns_none_on_missing_file(self):
        from wiki_ingest._vault import _peek_schema_version
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(
                _peek_schema_version(Path(tmp) / "absent.md"),
            )

    def test_returns_none_on_binary_file(self):
        """Binary content decodes via `errors='replace'` but split_frontmatter
        finds no `---` opener → returns empty dict; helper returns None."""
        from wiki_ingest._vault import _peek_schema_version
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "binary.md"
            p.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd")
            self.assertIsNone(_peek_schema_version(p))

    def test_returns_none_on_frontmatter_without_schema_version(self):
        from wiki_ingest._vault import _peek_schema_version
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "WIKI_SCHEMA.md"
            p.write_text(
                "---\nname: foo\nkind: course\n---\n# x\n",
                encoding="utf-8",
            )
            self.assertIsNone(_peek_schema_version(p))


class TestFindVaultRoot(unittest.TestCase):
    """TC-UNIT-016-00-01..05 — `find_vault_root` discovery semantics."""

    def test_single_course_vault_returns_none_vault_root(self):
        """TC-UNIT-016-00-01: single-course (no outer schema) → vault_root=None."""
        with tempfile.TemporaryDirectory() as tmp:
            course = Path(tmp) / "course-a"
            _seed_course(course)
            inner = course / "_concepts" / "Foo.md"
            inner.write_text("# Foo\n", encoding="utf-8")
            cr, vr = find_vault_root(inner)
            self.assertEqual(cr.resolve(), course.resolve())
            self.assertIsNone(vr,
                              "single-course vault must yield vault_root=None")

    def test_two_tier_vault_returns_both(self):
        """TC-UNIT-016-00-02: two-tier layout discovers both roots."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _write_schema(vault / SCHEMA_FILE, "2.0", kind="vault-root")
            course = vault / "Lessons" / "Hermes"
            _seed_course(course)
            inner = course / "_sources" / "foo.md"
            inner.write_text("# Foo\n", encoding="utf-8")
            cr, vr = find_vault_root(inner)
            self.assertEqual(cr.resolve(), course.resolve())
            self.assertIsNotNone(vr)
            self.assertEqual(vr.resolve(), vault.resolve())

    def test_outer_schema_wrong_version_yields_none(self):
        """TC-UNIT-016-00-03: outer schema with schema_version=1.5 → vault_root=None."""
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp) / "outer"
            outer.mkdir()
            _write_schema(outer / SCHEMA_FILE, "1.5", kind="other")
            course = outer / "Lessons" / "Hermes"
            _seed_course(course)
            inner = course / "_concepts" / "Foo.md"
            inner.write_text("# Foo\n", encoding="utf-8")
            cr, vr = find_vault_root(inner)
            self.assertEqual(cr.resolve(), course.resolve())
            self.assertIsNone(vr,
                              "outer schema_version != 2.0 must be treated as "
                              "'not a vault root' (single-course mode).")

    def test_no_schema_anywhere_dies_code_2(self):
        """TC-UNIT-016-00-04: no WIKI_SCHEMA.md in any ancestor → die(code=2)."""
        with tempfile.TemporaryDirectory() as tmp:
            deep = Path(tmp) / "a" / "b" / "c"
            deep.mkdir(parents=True)
            inner = deep / "file.md"
            inner.write_text("orphan\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as cm:
                find_vault_root(inner)
            self.assertEqual(cm.exception.code, 2,
                             "vault-not-found must exit code 2")

    def test_symlinked_ancestor_aborts_walk(self):
        """TC-UNIT-016-00-05: symlinked ancestor in the chain stops the walk."""
        with tempfile.TemporaryDirectory() as tmp:
            real_course = Path(tmp) / "real_course"
            _seed_course(real_course)
            (real_course / "_concepts" / "Foo.md").write_text(
                "# Foo\n", encoding="utf-8",
            )
            link_course = Path(tmp) / "linked_course"
            try:
                link_course.symlink_to(real_course)
            except (NotImplementedError, OSError):
                self.skipTest("filesystem does not support symlinks")
            inner = link_course / "_concepts" / "Foo.md"
            # Walking up from `inner` (under a symlinked ancestor) must
            # either die (no schema visible) or never see beyond the link.
            with self.assertRaises(SystemExit) as cm:
                find_vault_root(inner)
            self.assertEqual(cm.exception.code, 2,
                             "symlinked ancestor must NOT be traversed; "
                             "expected vault-not-found")


class TestDiscoverCourses(unittest.TestCase):
    """TC-UNIT-016-00-06..10 — `discover_courses` enumeration semantics."""

    def test_discovers_lessons_layout(self):
        """TC-UNIT-016-00-06: classic Lessons/<Course> two-tier vault."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _write_schema(vault / SCHEMA_FILE, "2.0", kind="vault-root")
            for name in ("Hermes", "OpenClaw", "Sharpe"):
                _seed_course(vault / "Lessons" / name)
            courses = discover_courses(vault)
            self.assertEqual(len(courses), 3)
            names = sorted(c.name for c in courses)
            self.assertEqual(names, ["Hermes", "OpenClaw", "Sharpe"])
            # Sort discipline: list should be sorted by str(path).
            self.assertEqual(courses, sorted(courses, key=lambda p: str(p)))

    def test_discovers_non_lessons_layout(self):
        """TC-UNIT-016-00-07: Q-8 — courses at <vault>/<Course> directly."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _write_schema(vault / SCHEMA_FILE, "2.0", kind="vault-root")
            _seed_course(vault / "Hermes")
            _seed_course(vault / "OpenClaw")
            courses = discover_courses(vault)
            self.assertEqual(len(courses), 2,
                             "Lessons/ is NOT hardcoded; any descendant "
                             "qualifies (Q-8 resolution)")
            names = sorted(c.name for c in courses)
            self.assertEqual(names, ["Hermes", "OpenClaw"])

    def test_discovers_nested_schemas(self):
        """TC-UNIT-016-00-08: A-M-4 — nested course-of-courses returns flat list."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _write_schema(vault / SCHEMA_FILE, "2.0", kind="vault-root")
            _seed_course(vault / "Lessons" / "2026" / "Spring" / "Hermes")
            _seed_course(vault / "Lessons" / "2026" / "Fall" / "OpenClaw")
            courses = discover_courses(vault)
            self.assertEqual(len(courses), 2,
                             "nested schemas are flat-listed independently")
            stems = sorted(c.name for c in courses)
            self.assertEqual(stems, ["Hermes", "OpenClaw"])

    def test_skips_symlinked_subdir(self):
        """TC-UNIT-016-00-09: symlinked subdir is NOT descended (OVERLAP-5)."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _write_schema(vault / SCHEMA_FILE, "2.0", kind="vault-root")
            # Real course visible:
            _seed_course(vault / "Lessons" / "Real")
            # External (outside-vault) course pretended-attached via symlink:
            external_course = Path(tmp) / "external_course"
            _seed_course(external_course)
            try:
                (vault / "linked").symlink_to(external_course)
            except (NotImplementedError, OSError):
                self.skipTest("filesystem does not support symlinks")
            courses = discover_courses(vault)
            names = [c.name for c in courses]
            self.assertIn("Real", names)
            self.assertNotIn("external_course", names,
                             "symlinked subdir must not be descended")

    def test_refuses_non_v2_root(self):
        """TC-UNIT-016-00-10: passing a 1.x course root to discover_courses dies."""
        with tempfile.TemporaryDirectory() as tmp:
            course = Path(tmp) / "course-a"
            _seed_course(course, version="1.0")
            with self.assertRaises(SystemExit) as cm:
                discover_courses(course)
            self.assertEqual(cm.exception.code, 2,
                             "discover_courses must refuse a non-v2.0 root")

    def test_refuses_missing_schema(self):
        """TC-UNIT-016-00-10b: passing a dir without WIKI_SCHEMA.md dies."""
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "no-schema"
            empty.mkdir()
            with self.assertRaises(SystemExit) as cm:
                discover_courses(empty)
            self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

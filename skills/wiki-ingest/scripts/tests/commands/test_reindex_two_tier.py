"""Per-command tests for `commands/reindex.py` two-tier extensions.

TASK 016 bead 016-08. Existing single-course reindex tests live in
`test_find_lint_reindex.py`; this file covers ONLY the new modes.
"""
from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import reindex as reindex_cmd


def _write_schema(path: Path, version: str, kind: str) -> None:
    path.write_text(
        f"---\nschema_version: \"{version}\"\nkind: {kind}\n---\n",
        encoding="utf-8",
    )


def _seed_course(course_root: Path) -> None:
    course_root.mkdir(parents=True, exist_ok=True)
    _write_schema(course_root / "WIKI_SCHEMA.md", "1.0", "course")
    for sub in ("_sources", "_concepts", "_entities"):
        (course_root / sub).mkdir(exist_ok=True)
    (course_root / "index.md").write_text(
        "# Index\n\n## Sources\n\n## Concepts\n\n## Entities\n",
        encoding="utf-8")
    (course_root / "log.md").write_text("# Log\n", encoding="utf-8")


def _seed_two_tier_with_promoted(tmp: Path) -> Path:
    vault = tmp / "vault"
    vault.mkdir()
    _write_schema(vault / "WIKI_SCHEMA.md", "2.0", "vault-root")
    (vault / "_concepts").mkdir()
    (vault / "_entities").mkdir()
    _seed_course(vault / "Lessons" / "A")
    # Course A has a source that cites a root concept page
    (vault / "Lessons" / "A" / "_sources" / "a-foo.md").write_text(
        "## a-foo\n", encoding="utf-8")
    (vault / "_concepts" / "Sharpe.md").write_text(
        "---\nname: Sharpe\nkind: concept\n---\n"
        "# Sharpe\n\n## Definition\n\nA thing.\n\n"
        "## Footnotes\n\n"
        "[^src-a-foo]: [[Lessons/A/_sources/a-foo]] — Source A\n",
        encoding="utf-8")
    return vault


def _run(vault: Path, cascade: bool = False) -> tuple[int, dict]:
    args = argparse.Namespace(
        vault=str(vault), cmd="reindex", dry_run=False, cascade=cascade,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = reindex_cmd.execute(args)
    # In cascade mode multiple JSON objects print — take the LAST (root mode)
    text = buf.getvalue().strip()
    decoder = json.JSONDecoder()
    payloads = []
    idx = 0
    while idx < len(text):
        # Skip whitespace
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        obj, end = decoder.raw_decode(text, idx)
        payloads.append(obj)
        idx = end
    return rc, payloads[-1]


class TestCourseModeSharedReferenced(unittest.TestCase):
    """TC-UNIT-016-08-01"""

    def test_shared_concepts_referenced_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier_with_promoted(Path(tmp))
            rc, payload = _run(vault / "Lessons" / "A")
            self.assertEqual(rc, 0)
            self.assertEqual(payload["mode"], "course")
            self.assertIn("Sharpe",
                          payload["shared_referenced"]["concepts"])
            # Index has the new section
            idx_text = (vault / "Lessons" / "A" / "index.md"
                        ).read_text(encoding="utf-8")
            self.assertIn("Shared concepts referenced", idx_text)
            self.assertIn("[[Sharpe]] — (shared)", idx_text)


class TestRootMode(unittest.TestCase):
    """TC-UNIT-016-08-03 / 04 / 06"""

    def test_root_mode_rebuilds_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = tmp_path = Path(tmp) / "vault"
            vault.mkdir()
            _write_schema(vault / "WIKI_SCHEMA.md", "2.0", "vault-root")
            (vault / "_concepts").mkdir()
            (vault / "_entities").mkdir()
            (vault / "_concepts" / "Foo.md").write_text("# Foo\n",
                                                        encoding="utf-8")
            (vault / "_concepts" / "Bar.md").write_text("# Bar\n",
                                                        encoding="utf-8")
            (vault / "_entities" / "Hermes.md").write_text("# Hermes\n",
                                                           encoding="utf-8")
            rc, payload = _run(vault)
            self.assertEqual(rc, 0)
            self.assertEqual(payload["mode"], "root")
            self.assertEqual(payload["concepts"], 2)
            self.assertEqual(payload["entities"], 1)
            idx = (vault / "index.md").read_text(encoding="utf-8")
            self.assertIn("[[Foo]]", idx)
            self.assertIn("[[Bar]]", idx)
            self.assertIn("[[Hermes]]", idx)
            # No `## Sources` H2 at root
            self.assertNotIn("## Sources", idx)

    def test_root_mode_creates_index_if_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _write_schema(vault / "WIKI_SCHEMA.md", "2.0", "vault-root")
            (vault / "_concepts").mkdir()
            (vault / "_entities").mkdir()
            rc, payload = _run(vault)
            self.assertEqual(rc, 0)
            self.assertTrue((vault / "index.md").is_file())

    def test_cascade_reindexes_courses(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _seed_two_tier_with_promoted(Path(tmp))
            rc, payload = _run(vault, cascade=True)
            self.assertEqual(rc, 0)
            self.assertEqual(payload["mode"], "root")
            self.assertEqual(len(payload["cascaded"]), 1)


class TestNonLessonsLayout(unittest.TestCase):
    """TC-UNIT-016-08-10"""

    def test_non_lessons_course_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            _write_schema(vault / "WIKI_SCHEMA.md", "2.0", "vault-root")
            (vault / "_concepts").mkdir()
            (vault / "_entities").mkdir()
            # Course at <vault>/Hermes (no Lessons/ parent)
            _seed_course(vault / "Hermes")
            (vault / "Hermes" / "_sources" / "h-foo.md").write_text(
                "## h-foo\n", encoding="utf-8")
            (vault / "_concepts" / "Sharpe.md").write_text(
                "---\nname: Sharpe\nkind: concept\n---\n"
                "# Sharpe\n\n## Footnotes\n\n"
                "[^src-h-foo]: [[Hermes/_sources/h-foo]] — Source\n",
                encoding="utf-8")
            rc, payload = _run(vault, cascade=True)
            self.assertEqual(rc, 0)
            # Course was reindexed
            self.assertIn("Hermes", payload["cascaded"])


if __name__ == "__main__":
    unittest.main()

"""End-to-end round-trip test for TASK 016 cross-course promotion.

Final gate (bead 016-10). Drives the full ingest → lint → promote →
lint → demote → lint workflow against a two-course fixture vault.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from wiki_ingest.commands import demote as demote_cmd
from wiki_ingest.commands import init as init_cmd
from wiki_ingest.commands import lint as lint_cmd
from wiki_ingest.commands import promote as promote_cmd
from wiki_ingest.commands import reindex as reindex_cmd
from wiki_ingest.commands import upsert_page as upsert_cmd


def _capture(func, args) -> tuple[int, str]:
    buf = io.StringIO()
    rc = 0
    try:
        with redirect_stdout(buf):
            rc = func(args)
    except SystemExit as e:
        rc = int(e.code or 0)
    return rc, buf.getvalue()


def _build_two_course_vault(tmp: Path) -> Path:
    """Set up the canonical two-course fixture used by 016-10 round-trip."""
    vault = tmp / "trade-agents"
    vault.mkdir()
    with redirect_stdout(io.StringIO()):
        # 1. Root via `init --root`
        init_cmd.execute(argparse.Namespace(
            vault=str(vault), root=True, dry_run=False, cmd="init",
        ))
        # 2. Each course
        for name in ("Hermes", "OpenClaw"):
            course = vault / "Lessons" / name
            init_cmd.execute(argparse.Namespace(
                vault=str(course), root=False, dry_run=False, cmd="init",
            ))
    # 3. Source pages
    (vault / "Lessons" / "Hermes" / "_sources" / "h-foo.md").write_text(
        "---\nname: h-foo\nkind: source\nconcepts:\n  - Sharpe Score\n"
        "  - Sharpe Score\n---\n# h-foo\n\nMentions [[Sharpe Score]].\n",
        encoding="utf-8")
    (vault / "Lessons" / "OpenClaw" / "_sources" / "o-bar.md").write_text(
        "---\nname: o-bar\nkind: source\nconcepts:\n  - Sharpe Score\n"
        "  - Sharpe Score\n---\n# o-bar\n\nMentions [[Sharpe Score]].\n",
        encoding="utf-8")
    # 4. Concept pages in BOTH courses (will be the promotion target)
    (vault / "Lessons" / "Hermes" / "_concepts" / "Sharpe Score.md").write_text(
        "---\nname: Sharpe Score\nkind: concept\ncreated: 2026-01-01\n---\n"
        "# Sharpe Score\n\n"
        "## Definition\n\n"
        "The Sharpe ratio is (R - Rf) / sigma. [^src-h-foo]\n\n"
        "## Facts\n\n"
        "- annualized via sqrt(252) [^src-h-foo]\n\n"
        "## Sources mentioning this\n\n"
        "- [[h-foo]] — 2026-01-01 — Hermes Foo\n\n"
        "## Footnotes\n\n"
        "[^src-h-foo]: [[h-foo]] — Hermes Foo\n",
        encoding="utf-8")
    (vault / "Lessons" / "OpenClaw" / "_concepts" / "Sharpe Score.md").write_text(
        "---\nname: Sharpe Score\nkind: concept\ncreated: 2026-02-15\n---\n"
        "# Sharpe Score\n\n"
        "## Definition\n\n"
        "Risk-adjusted return metric. [^src-o-bar]\n\n"
        "## Facts\n\n"
        "- annualized via sqrt(365) [^src-o-bar]\n\n"
        "## Sources mentioning this\n\n"
        "- [[o-bar]] — 2026-02-15 — OpenClaw Bar\n\n"
        "## Footnotes\n\n"
        "[^src-o-bar]: [[o-bar]] — OpenClaw Bar\n",
        encoding="utf-8")
    # 5. Update each course's index.md to list the concept
    for course in ("Hermes", "OpenClaw"):
        idx = vault / "Lessons" / course / "index.md"
        idx_text = idx.read_text(encoding="utf-8")
        # Add row under ## Concepts (the v1 init template has the heading)
        new_idx = re.sub(
            r"## Concepts\n",
            "## Concepts\n\n- [[Sharpe Score]]\n",
            idx_text,
        )
        idx.write_text(new_idx, encoding="utf-8")
    return vault


def _strip_dates(text: str) -> str:
    """Normalise YYYY-MM-DD dates so log diffs are stable across days."""
    return re.sub(r"\d{4}-\d{2}-\d{2}", "YYYY-MM-DD", text)


class TestE2ERoundTrip(unittest.TestCase):
    """TC-E2E-016-10-01"""

    def test_full_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_course_vault(Path(tmp))

            # Step 1: lint flags the cross-course duplicate
            rc, out = _capture(lint_cmd.execute, argparse.Namespace(
                vault=str(vault), cmd="lint", threshold=2, limit=None,
            ))
            self.assertEqual(rc, 0)
            payload = json.loads(out)
            self.assertEqual(payload["mode"], "two-tier")
            self.assertEqual(
                payload["totals"]["cross_course_duplicate"], 1,
                "lint must detect the duplicate Sharpe Score",
            )
            self.assertEqual(
                payload["totals"]["invariant_violation"], 0,
                "no invariant violation before promote",
            )

            # Step 2: promote --apply
            rc, out = _capture(promote_cmd.execute, argparse.Namespace(
                name="Sharpe Score", vault=str(vault),
                kind=None, apply=True, cmd="promote",
            ))
            self.assertEqual(rc, 0)
            promote_result = json.loads(out)
            self.assertTrue(promote_result["applied"])
            # Contradiction detected (Hermes vs OpenClaw differ on annualization)
            self.assertGreaterEqual(
                promote_result["contradictions_raised"], 1,
                "literal-line-diff should flag the annualization disagreement",
            )

            # Step 3: lint clean
            rc, out = _capture(lint_cmd.execute, argparse.Namespace(
                vault=str(vault), cmd="lint", threshold=2, limit=None,
            ))
            self.assertEqual(rc, 0)
            payload = json.loads(out)
            self.assertEqual(payload["totals"]["cross_course_duplicate"], 0)
            self.assertEqual(payload["totals"]["invariant_violation"], 0)

            # Step 4: inspect merged page
            root_page = vault / "_concepts" / "Sharpe Score.md"
            self.assertTrue(root_page.is_file())
            text = root_page.read_text(encoding="utf-8")
            # Vault-relative footnotes for BOTH sources
            self.assertIn("[[Lessons/Hermes/_sources/h-foo]]", text)
            self.assertIn("[[Lessons/OpenClaw/_sources/o-bar]]", text)
            # promoted_from lists both courses
            self.assertIn("promoted_from:", text)
            self.assertIn("course: Hermes", text)
            self.assertIn("course: OpenClaw", text)
            # Contradictions block emitted
            self.assertIn("## Contradictions", text)

            # Step 5: demote refused (both courses cite the page)
            rc, _ = _capture(demote_cmd.execute, argparse.Namespace(
                name="Sharpe Score", vault=str(vault),
                to_course="Hermes", dry_run=False, cmd="demote",
            ))
            self.assertEqual(rc, 1,
                             "demote --to Hermes refused — OpenClaw still cites")

            # Step 6: clean OpenClaw's citation, then demote succeeds
            (vault / "Lessons" / "OpenClaw" / "_sources" / "o-bar.md").unlink()
            rc, out = _capture(demote_cmd.execute, argparse.Namespace(
                name="Sharpe Score", vault=str(vault),
                to_course="Hermes", dry_run=False, cmd="demote",
            ))
            self.assertEqual(rc, 0,
                             "demote --to Hermes succeeds after OpenClaw's "
                             "source removed")

            # Final state: page in Course Hermes only, short-form footnotes
            self.assertFalse(root_page.exists())
            demoted = (vault / "Lessons" / "Hermes" / "_concepts" /
                       "Sharpe Score.md")
            self.assertTrue(demoted.is_file())
            demoted_text = demoted.read_text(encoding="utf-8")
            self.assertIn("[[h-foo]]", demoted_text,
                          "short-form footnote restored")
            self.assertNotIn("[[Lessons/Hermes/_sources/h-foo]]", demoted_text)
            self.assertNotIn("promoted_from:", demoted_text)

            # Step 7: final lint clean
            rc, out = _capture(lint_cmd.execute, argparse.Namespace(
                vault=str(vault), cmd="lint", threshold=2, limit=None,
            ))
            self.assertEqual(rc, 0)


class TestE2EUpsertRoutesToRoot(unittest.TestCase):
    """TC-E2E-016-10-02 — ingest after promote routes to root."""

    def test_upsert_into_third_course_routes_to_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_course_vault(Path(tmp))
            # Promote
            _capture(promote_cmd.execute, argparse.Namespace(
                name="Sharpe Score", vault=str(vault),
                kind=None, apply=True, cmd="promote",
            ))
            # Add Course C
            with redirect_stdout(io.StringIO()):
                init_cmd.execute(argparse.Namespace(
                    vault=str(vault / "Lessons" / "C"),
                    root=False, dry_run=False, cmd="init",
                ))
            # Upsert into Course C
            _capture(upsert_cmd.execute, argparse.Namespace(
                vault=str(vault / "Lessons" / "C"),
                kind="concept", name="Sharpe Score",
                source_slug="cbaz", source_title="C Baz",
                source_date="2026-05-26",
                definition=None, fact="Z = 99", contradicts=None,
                force=False, dry_run=False, cmd="upsert-page",
            ))
            # Root page gained the fact
            root_text = (vault / "_concepts" / "Sharpe Score.md"
                         ).read_text(encoding="utf-8")
            self.assertIn("Z = 99", root_text)
            self.assertIn("[[Lessons/C/_sources/cbaz]]", root_text)
            # No course-local page in C
            self.assertFalse(
                (vault / "Lessons" / "C" / "_concepts" / "Sharpe Score.md"
                 ).exists())


class TestE2EReindexSharedReferenced(unittest.TestCase):
    """TC-E2E-016-10-03"""

    def test_reindex_emits_shared_referenced(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = _build_two_course_vault(Path(tmp))
            _capture(promote_cmd.execute, argparse.Namespace(
                name="Sharpe Score", vault=str(vault),
                kind=None, apply=True, cmd="promote",
            ))
            # Reindex Course Hermes
            _capture(reindex_cmd.execute, argparse.Namespace(
                vault=str(vault / "Lessons" / "Hermes"),
                cmd="reindex", dry_run=False, cascade=False,
            ))
            idx = (vault / "Lessons" / "Hermes" / "index.md"
                   ).read_text(encoding="utf-8")
            self.assertIn("Shared concepts referenced", idx)
            self.assertIn("[[Sharpe Score]]", idx)


if __name__ == "__main__":
    unittest.main()

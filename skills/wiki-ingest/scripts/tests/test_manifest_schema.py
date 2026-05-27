"""Parses `references/manifest_schema.md` and locks the v1.1 contract shape
(TASK 017 bead 017-04).

This file is the structural gate between the in-repo contract mirror and
the downstream orchestrator (017-05). The §1.1 success envelope and
§1.3 partial envelope are extracted as fixtures and asserted against the
field reference table. A reference-doc edit that drops a required field
will fail HERE before it can propagate into `commands/ingest.py`.

Locks:
- TC-UNIT-017-04-01: §1 example block parses as valid JSON.
- TC-UNIT-017-04-02: §1 example has the required top-level keys.
- TC-UNIT-017-04-03: §1 example has `manifest_version == "1.1"`.
- TC-UNIT-017-04-04: `written[]` entries have the right shape +
  allowed enum values.
- TC-UNIT-017-04-05: §3 contains the v1.1 exit-code table (codes
  20..26 all present).
- TC-UNIT-017-04-06: provenance headers are present for every §.
- TC-UNIT-017-04-07: no bracket-style placeholders left in the file.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REFS_DIR = Path(__file__).resolve().parent.parent.parent / "references"
MANIFEST_DOC = REFS_DIR / "manifest_schema.md"

_REQUIRED_TOP_LEVEL_KEYS = frozenset({
    "manifest_version", "status", "vault_id", "vault_root", "course",
    "source", "written", "created", "touched", "contradictions",
    "summary_path", "log_event", "llm_tokens_used",
})

_WRITTEN_ENTRY_KEYS = frozenset({"path", "action", "kind", "scope"})
_WRITTEN_ACTIONS = frozenset({"created", "updated", "appended"})
_WRITTEN_KINDS = frozenset({"source", "concept", "entity", "index", "log"})
_WRITTEN_SCOPES = frozenset({"course", "vault"})

_REQUIRED_SECTIONS = ("§1", "§2", "§3", "§5", "§6", "§7", "§8")
_REQUIRED_V11_EXIT_CODES = (20, 21, 22, 23, 24, 25, 26)

_PROVENANCE_RE = re.compile(
    r"^> sourced from `obsidian-llm-wiki/docs/WIKI-INGEST-V1\.1-CONTRACT\.md` "
    r"§\d+ \(\d{4}-\d{2}-\d{2}\)$"
)


def _read_doc() -> str:
    return MANIFEST_DOC.read_text(encoding="utf-8")


def _extract_first_json_block(body: str, after_heading_substring: str) -> dict:
    """Return the first parsed ```json fenced block AFTER the given
    substring (which is usually a `## §N` heading)."""
    idx = body.find(after_heading_substring)
    if idx < 0:
        raise AssertionError(f"section heading not found: {after_heading_substring!r}")
    rest = body[idx:]
    m = re.search(r"```json\s*\n(.+?)\n```", rest, re.DOTALL)
    if not m:
        raise AssertionError(f"no ```json block after {after_heading_substring!r}")
    return json.loads(m.group(1))


# --------------------------------------------------------------------------- #
# Existence + JSON well-formedness                                            #
# --------------------------------------------------------------------------- #

class TestManifestSchemaDocExists(unittest.TestCase):

    def test_file_present(self):
        self.assertTrue(MANIFEST_DOC.is_file(),
                        f"missing in-repo contract mirror: {MANIFEST_DOC}")


class TestSection1JsonExamples(unittest.TestCase):
    """TC-UNIT-017-04-01..04 — §1 example block round-trips."""

    @classmethod
    def setUpClass(cls):
        cls.body = _read_doc()
        cls.success = _extract_first_json_block(cls.body, "## §1")

    def test_01_parses_as_json(self):
        # setUpClass already calls json.loads via _extract_first_json_block;
        # a parse failure surfaces there. Re-asserting for clarity.
        self.assertIsInstance(self.success, dict)

    def test_02_required_top_level_keys(self):
        missing = _REQUIRED_TOP_LEVEL_KEYS - set(self.success.keys())
        self.assertFalse(missing,
                         f"§1.1 example missing required keys: {sorted(missing)}")

    def test_03_manifest_version_locked(self):
        self.assertEqual(self.success.get("manifest_version"), "1.1",
                         "§1.1 example must stamp manifest_version=\"1.1\" (Arch-M-3)")

    def test_04_written_entry_shape(self):
        written = self.success["written"]
        self.assertIsInstance(written, list)
        self.assertGreater(len(written), 0,
                           "§1.1 success example must populate written[]")
        for entry in written:
            with self.subTest(entry=entry):
                missing = _WRITTEN_ENTRY_KEYS - set(entry.keys())
                self.assertFalse(missing,
                                 f"WrittenEntry missing keys: {sorted(missing)}")
                self.assertIn(entry["action"], _WRITTEN_ACTIONS)
                self.assertIn(entry["kind"], _WRITTEN_KINDS)
                self.assertIn(entry["scope"], _WRITTEN_SCOPES)


class TestPartialEnvelopeExample(unittest.TestCase):
    """§1.3 partial envelope shape lock — TASK 017 R5.3."""

    def test_partial_envelope_keys(self):
        body = _read_doc()
        partial = _extract_first_json_block(body, "Partial-success envelope")
        for key in ("manifest_version", "status", "phase", "code",
                    "written_so_far", "cleanup_advice", "vault_id", "vault_root"):
            self.assertIn(key, partial, f"§1.3 partial envelope missing {key!r}")
        self.assertEqual(partial.get("status"), "error")
        self.assertEqual(partial.get("code"), "PARTIAL_INDEX_FAILURE")


# --------------------------------------------------------------------------- #
# Exit-code table + provenance headers + no-placeholder check                 #
# --------------------------------------------------------------------------- #

class TestSection3ExitCodes(unittest.TestCase):
    """TC-UNIT-017-04-05 — §3 names every v1.1 exit code."""

    def test_all_v11_codes_present(self):
        body = _read_doc()
        idx = body.find("## §3")
        self.assertGreaterEqual(idx, 0, "§3 heading missing")
        # Scope the search to the §3 body (until the next §-heading).
        rest = body[idx:]
        next_heading = rest.find("\n## §", 4)  # skip the §3 heading itself
        section3 = rest[:next_heading] if next_heading >= 0 else rest
        for code in _REQUIRED_V11_EXIT_CODES:
            with self.subTest(code=code):
                self.assertRegex(
                    section3, rf"\b{code}\b",
                    f"§3 must mention exit code {code}",
                )


class TestProvenanceHeaders(unittest.TestCase):
    """TC-UNIT-017-04-06 — every required § has a provenance header."""

    def test_every_section_has_provenance(self):
        body = _read_doc()
        for sec in _REQUIRED_SECTIONS:
            with self.subTest(section=sec):
                heading = f"## {sec}"
                idx = body.find(heading)
                self.assertGreaterEqual(idx, 0, f"missing heading {heading!r}")
                # The provenance line must appear within the next ~10 lines.
                rest = body[idx:idx + 800].splitlines()
                hits = [ln for ln in rest if _PROVENANCE_RE.match(ln)]
                self.assertTrue(
                    hits,
                    f"no provenance header under heading {heading!r}; "
                    f"expected `> sourced from ...{sec} (YYYY-MM-DD)`",
                )


class TestNoPlaceholders(unittest.TestCase):
    """TC-UNIT-017-04-07 — no TODO / FIXME / `<verbatim copy>` markers."""

    BANNED = ("TODO", "FIXME", "<verbatim copy", "<TBD>", "<…>")

    def test_no_bracket_style_placeholders(self):
        body = _read_doc()
        for needle in self.BANNED:
            with self.subTest(needle=needle):
                self.assertNotIn(needle, body,
                                 f"placeholder {needle!r} leaked into the contract mirror")


if __name__ == "__main__":
    unittest.main()

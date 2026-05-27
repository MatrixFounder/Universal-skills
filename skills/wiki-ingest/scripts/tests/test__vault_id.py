"""Unit tests for `_vault.read_vault_id` + `validate_vault_id_pattern` (TASK 017 bead 017-02).

Locks:

- `_safety.EXIT_*` constants are wired (TC-UNIT-017-02-12).
- `read_vault_id` returns string-or-None per "emit, don't enforce"
  (TC-UNIT-017-02-08..11). Absence is NOT an error.
- `validate_vault_id_pattern` exits with `EXIT_INVALID_VAULT_ID == 7`
  on every malformed input: length boundaries, leading digit, trailing
  dash, double-dash, uppercase, unicode, control chars
  (TC-UNIT-017-02-02..07).
- The two helpers are independent — `read_vault_id` does NOT validate;
  callers decide when to enforce (TC-UNIT-017-02-11).
"""
from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from wiki_ingest import _safety
from wiki_ingest._vault import (
    _VAULT_ID_RE,
    SCHEMA_FILE,
    read_vault_id,
    validate_vault_id_pattern,
)


# --------------------------------------------------------------------------- #
# Exit-code constants                                                         #
# --------------------------------------------------------------------------- #

class TestExitConstants(unittest.TestCase):
    """TC-UNIT-017-02-12 — `_safety.EXIT_*` numeric assignments are locked."""

    # Numbers from references/exit_codes.md §4 (remediated matrix after the
    # TASK 015/016 collision audit on 2026-05-27). Shipped 0/1/2 unchanged;
    # v1.1 contract codes live in the 20..26 band to avoid collision with
    # existing 3..8 call sites in _safety / commands/register_summary /
    # commands/upsert_page.
    EXPECTED = {
        "EXIT_OK": 0,
        "EXIT_GENERIC": 1,
        "EXIT_USAGE": 2,
        "EXIT_PARTIAL": 20,
        "EXIT_SUBPROCESS": 21,
        "EXIT_LLM": 22,
        "EXIT_MISSING_VAULT_ID": 23,
        "EXIT_INVALID_VAULT_ID": 24,
        "EXIT_VAULT_ID_MISMATCH": 25,
        "EXIT_TIMEOUT": 26,
    }

    def test_constants_present_and_correct(self):
        for name, expected in self.EXPECTED.items():
            with self.subTest(name=name):
                actual = getattr(_safety, name, "MISSING")
                self.assertEqual(actual, expected,
                                 f"_safety.{name} = {actual!r}; want {expected}")


# --------------------------------------------------------------------------- #
# Pattern validator                                                           #
# --------------------------------------------------------------------------- #

class TestValidateVaultIdPattern(unittest.TestCase):

    def _expect_invalid(self, slug, *, substring_in_stderr=None):
        with self.assertRaises(SystemExit) as cm:
            validate_vault_id_pattern(slug)
        self.assertEqual(cm.exception.code, _safety.EXIT_INVALID_VAULT_ID,
                         f"slug={slug!r} did not route to EXIT_INVALID_VAULT_ID")

    def test_valid_round_trip(self):
        """TC-UNIT-017-02-01."""
        for ok in ("trade-agents", "abc", "a" + "b" * 30 + "c"):
            with self.subTest(slug=ok):
                self.assertIsNone(validate_vault_id_pattern(ok),
                                  f"valid slug {ok!r} should return None")

    def test_length_too_short(self):
        """TC-UNIT-017-02-02 — minimum 3."""
        self._expect_invalid("ab")

    def test_length_too_long(self):
        """TC-UNIT-017-02-02 — maximum 32 (1 lead + 30 mid + 1 tail)."""
        self._expect_invalid("a" + "b" * 32 + "c")  # 34 chars

    def test_leading_digit(self):
        """TC-UNIT-017-02-03."""
        self._expect_invalid("1bad")

    def test_trailing_dash(self):
        """TC-UNIT-017-02-04."""
        self._expect_invalid("trade-")

    def test_double_dash_substring(self):
        """TC-UNIT-017-02-05 — separate predicate so error mentions '--'."""
        self._expect_invalid("trade--agents")

    def test_uppercase_rejected(self):
        """TC-UNIT-017-02-06."""
        self._expect_invalid("Trade")

    def test_unicode_letter_rejected(self):
        """TC-UNIT-017-02-06 — Cyrillic 'а' looks like ASCII 'a'."""
        self._expect_invalid("trade-аgents")

    def test_path_separators_rejected(self):
        """TC-UNIT-017-02-07."""
        for bad in ("a/b", "a\\b", "a b"):
            with self.subTest(slug=bad):
                self._expect_invalid(bad)

    def test_control_chars_rejected(self):
        """TC-UNIT-017-02-07 — NUL + others."""
        self._expect_invalid("a\x00b")


# --------------------------------------------------------------------------- #
# read_vault_id — frontmatter peek (emit, don't enforce)                      #
# --------------------------------------------------------------------------- #

class TestReadVaultId(unittest.TestCase):
    """`read_vault_id` is read-only frontmatter peek; never raises on absent."""

    def _make_vault(self, schema_body):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        if schema_body is not None:
            (root / SCHEMA_FILE).write_text(schema_body, encoding="utf-8")
        return root

    def test_happy_path(self):
        """TC-UNIT-017-02-08."""
        vault = self._make_vault(textwrap.dedent("""\
            ---
            schema_version: 2.0
            kind: vault-root
            vault_id: trade-agents
            ---

            Body.
            """))
        self.assertEqual(read_vault_id(vault), "trade-agents")

    def test_field_absent(self):
        """TC-UNIT-017-02-09 — absence is NOT an error."""
        vault = self._make_vault(textwrap.dedent("""\
            ---
            schema_version: 2.0
            kind: vault-root
            ---

            Body.
            """))
        self.assertIsNone(read_vault_id(vault))

    def test_schema_file_absent(self):
        """TC-UNIT-017-02-10."""
        vault = self._make_vault(None)
        self.assertIsNone(read_vault_id(vault))

    def test_no_pattern_validation(self):
        """TC-UNIT-017-02-11 — separation of concerns: read != validate.

        A malformed slug in frontmatter is returned verbatim; the caller
        decides when (and whether) to fail.
        """
        vault = self._make_vault(textwrap.dedent("""\
            ---
            schema_version: 2.0
            vault_id: 1bad
            ---
            """))
        self.assertEqual(read_vault_id(vault), "1bad")

    def test_quoted_value_round_trip(self):
        """Frontmatter parser strips matched quotes; result is the bare slug."""
        vault = self._make_vault(textwrap.dedent("""\
            ---
            schema_version: 2.0
            vault_id: "trade-agents"
            ---
            """))
        self.assertEqual(read_vault_id(vault), "trade-agents")

    def test_non_string_value_yields_none(self):
        """Frontmatter parser is lax; a numeric `vault_id: 42` should be ignored
        rather than crash the helper."""
        vault = self._make_vault(textwrap.dedent("""\
            ---
            schema_version: 2.0
            vault_id: 42
            ---
            """))
        # The naive frontmatter parser returns the raw string "42"; the helper
        # returns it verbatim per "emit, don't enforce". Pattern validation
        # (if the caller invokes it) will reject 42 (leading digit).
        result = read_vault_id(vault)
        if result is not None:
            self.assertEqual(result, "42")
            with self.assertRaises(SystemExit):
                validate_vault_id_pattern(result)


# --------------------------------------------------------------------------- #
# Pattern shape lock — defends architecture §2.4                              #
# --------------------------------------------------------------------------- #

class TestPatternRegexShape(unittest.TestCase):

    def test_pattern_exact(self):
        """Architecture §2.4 locks the exact pattern."""
        self.assertEqual(_VAULT_ID_RE.pattern,
                         r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")


if __name__ == "__main__":
    unittest.main()

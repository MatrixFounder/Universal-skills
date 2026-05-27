"""Unit tests for `_dispatch.dispatch` (TASK 017 bead 017-03).

Locks:
- TC-UNIT-017-03-01: known command propagates the dispatched exit code.
- TC-UNIT-017-03-02: unknown name → SystemExit code 2 BEFORE any
  `importlib.import_module` call (T17-S9 — whitelist-first).
- TC-UNIT-017-03-03: whitelist excludes orchestrator + operator-facing
  commands (`ingest`, `init`, `promote`, `demote`, `lint`, `reindex`,
  `scan`, `find`, `classify-folder`).
- TC-UNIT-017-03-04: hyphen → underscore translation (CLI form
  `"upsert-page"` → module `wiki_ingest.commands.upsert_page`).
- TC-UNIT-017-03-05: `_dispatch.py` has no module-level
  `wiki_ingest.commands.*` imports (defense-in-depth complement to the
  architecture-test gate).
- TC-UNIT-017-03-06: `_ALLOWED_COMMANDS` is a frozenset of exactly 5
  entries (defends T17-S9 against accidental runtime mutation).
"""
from __future__ import annotations

import argparse
import ast
import unittest
from pathlib import Path
from unittest import mock

from wiki_ingest import _dispatch, _safety


SCRIPTS_DIR = Path(__file__).resolve().parent.parent
DISPATCH_PATH = SCRIPTS_DIR / "wiki_ingest" / "_dispatch.py"


class TestWhitelistShape(unittest.TestCase):
    """TC-UNIT-017-03-06 — `_ALLOWED_COMMANDS` shape lock."""

    def test_is_frozenset_of_five(self):
        self.assertIsInstance(_dispatch._ALLOWED_COMMANDS, frozenset)
        self.assertEqual(len(_dispatch._ALLOWED_COMMANDS), 5)
        self.assertEqual(_dispatch._ALLOWED_COMMANDS, frozenset({
            "register-summary",
            "upsert-page",
            "update-index",
            "append-log",
            "log-event",
        }))


class TestDispatchHappyPath(unittest.TestCase):
    """TC-UNIT-017-03-01 — known command propagates exit code.

    Uses `unittest.mock.patch.object` on `importlib.import_module` so
    we don't have to construct a real argparse Namespace matching every
    atomic-op's surface.
    """

    def test_happy_path_returns_target_exit_code(self):
        fake_mod = mock.MagicMock()
        fake_mod.execute.return_value = 0
        args = argparse.Namespace()
        with mock.patch.object(
            _dispatch.importlib, "import_module", return_value=fake_mod,
        ) as imp:
            rc = _dispatch.dispatch("register-summary", args)
        self.assertEqual(rc, 0)
        imp.assert_called_once_with("wiki_ingest.commands.register_summary")
        fake_mod.execute.assert_called_once_with(args)

    def test_non_zero_exit_propagates(self):
        fake_mod = mock.MagicMock()
        fake_mod.execute.return_value = 7
        args = argparse.Namespace()
        with mock.patch.object(
            _dispatch.importlib, "import_module", return_value=fake_mod,
        ):
            rc = _dispatch.dispatch("upsert-page", args)
        self.assertEqual(rc, 7)


class TestHyphenToUnderscoreTranslation(unittest.TestCase):
    """TC-UNIT-017-03-04 — CLI hyphen form → module underscore form.

    All five whitelist entries are hyphenated; the module names use
    underscores. Verify the translation per entry without dispatching
    the real commands.
    """

    EXPECTED = {
        "register-summary": "wiki_ingest.commands.register_summary",
        "upsert-page":      "wiki_ingest.commands.upsert_page",
        "update-index":     "wiki_ingest.commands.update_index",
        "append-log":       "wiki_ingest.commands.append_log",
        "log-event":        "wiki_ingest.commands.log_event",
    }

    def test_every_whitelist_entry_translates(self):
        args = argparse.Namespace()
        fake_mod = mock.MagicMock()
        fake_mod.execute.return_value = 0
        for cli_form, mod_name in self.EXPECTED.items():
            with self.subTest(cli_form=cli_form):
                with mock.patch.object(
                    _dispatch.importlib, "import_module",
                    return_value=fake_mod,
                ) as imp:
                    _dispatch.dispatch(cli_form, args)
                imp.assert_called_once_with(mod_name)


class TestWhitelistEnforcement(unittest.TestCase):
    """TC-UNIT-017-03-02 + -03 — unknown / non-whitelisted name → exit 2,
    BEFORE any `importlib.import_module` call."""

    def _assert_rejected(self, cmd_name: str):
        with mock.patch.object(_dispatch.importlib, "import_module") as imp:
            with self.assertRaises(SystemExit) as cm:
                _dispatch.dispatch(cmd_name, argparse.Namespace())
            imp.assert_not_called()
        self.assertEqual(cm.exception.code, _safety.EXIT_USAGE,
                         f"{cmd_name!r} should route to EXIT_USAGE (2)")

    def test_completely_unknown_name(self):
        """TC-UNIT-017-03-02 — `rm-rf-vault` doesn't exist anywhere."""
        self._assert_rejected("rm-rf-vault")

    def test_orchestrator_and_broader_commands_rejected(self):
        """TC-UNIT-017-03-03 — these exist in commands/ but are NOT
        dispatchable. Whitelist documents the orchestrator's call graph."""
        for name in (
            "ingest",            # orchestrator — must not recurse via dispatch
            "init",
            "promote",
            "demote",
            "lint",
            "reindex",
            "scan",
            "find",
            "classify-folder",
        ):
            with self.subTest(cmd_name=name):
                self._assert_rejected(name)

    def test_empty_string_rejected(self):
        self._assert_rejected("")

    def test_underscore_form_not_accepted(self):
        """The whitelist uses the CLI hyphen form. Passing the
        underscore-module-name form (`"upsert_page"`) is a programmer
        error and must be rejected."""
        self._assert_rejected("upsert_page")


class TestModuleLevelImportShape(unittest.TestCase):
    """TC-UNIT-017-03-05 — `_dispatch.py` has no module-level
    `wiki_ingest.commands.*` imports.

    Complements the architecture-test gate by parking the rule next
    to the helper's own tests; easier to find when grepping for the
    dispatch contract.
    """

    def test_no_top_level_command_imports(self):
        tree = ast.parse(DISPATCH_PATH.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                self.assertFalse(
                    module.startswith("wiki_ingest.commands"),
                    f"_dispatch.py module-level `from {module} import …` "
                    f"violates the carve-out — function-body imports only.",
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(
                        alias.name.startswith("wiki_ingest.commands"),
                        f"_dispatch.py module-level `import {alias.name}` "
                        f"violates the carve-out — function-body imports only.",
                    )


if __name__ == "__main__":
    unittest.main()

"""R7.4 — architecture invariant lint.

Enforces the one-way dependency rule from `docs/ARCHITECTURE.md` via the
stdlib `ast` module (no `import-linter` dep, ~30 LoC of real logic):

1. No `wiki_ingest/_*.py` (F1/F2/F3-helper) imports
   `wiki_ingest.commands.*`. Helpers stay below commands in the DAG.

2. No `wiki_ingest/commands/<a>.py` imports `wiki_ingest/commands/<b>.py`.
   Cross-command shared code must live in F1/F2/F3-helper, not be
   smuggled across the command boundary.

**Known blind spot (LOW-2 / Sarcasmotron 015-06)**: dynamic imports via
`importlib.import_module(...)`, `__import__(...)`, or attribute access
through a stashed module reference are NOT detected by AST walk. Keep
those out of helper modules by code review; flag them in PR review.

A test failure here = the layered model has been compromised; fix the
import, don't relax the test.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "wiki_ingest"


def _imports_of(path: Path) -> set[str]:
    """Return every top-level module imported by `path` (via `ast`)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            for n in node.names:
                out.add(n.name)
    return out


class ImportGraphInvariant(unittest.TestCase):

    def test_no_helper_imports_commands(self):
        """F1 / F2 / F3-helper modules must NOT depend on commands."""
        # `rglob` so a future nested helper sub-package (`_classify/*.py`)
        # would also be scanned (LOW-3 / Sarcasmotron 015-06).
        helpers = [
            p for p in PKG.rglob("_*.py")
            if "commands" not in p.parts
        ]
        for helper in helpers:
            mods = _imports_of(helper)
            for m in sorted(mods):
                self.assertFalse(
                    m.startswith("wiki_ingest.commands"),
                    f"{helper.name} imports {m!r} — helpers must not "
                    f"depend on commands (one-way DAG violated). "
                    f"Move the shared symbol to a lower-tier helper.",
                )

    def test_no_command_imports_another_command(self):
        """Each command module is independent of every other command."""
        cmds_dir = PKG / "commands"
        # `rglob` so a future nested command group (`commands/lint/*.py`)
        # is also covered (LOW-3 / Sarcasmotron 015-06).
        for cmd in cmds_dir.rglob("*.py"):
            if cmd.name == "__init__.py":
                continue
            mods = _imports_of(cmd)
            for m in sorted(mods):
                if m.startswith("wiki_ingest.commands.") \
                        and m.split(".")[-1] != cmd.stem:
                    self.fail(
                        f"{cmd.name} imports {m!r} — commands must not "
                        f"import each other (R7.3). Promote the shared "
                        f"helper to F1 (_safety) / F2 (_markdown / "
                        f"_frontmatter) / F3-helper (_vault / _classify)."
                    )

    def test_package_has_init(self):
        """Sanity guard: the package roots exist and parse cleanly."""
        self.assertTrue((PKG / "__init__.py").exists(),
                        "wiki_ingest/__init__.py is required")
        self.assertTrue((PKG / "commands" / "__init__.py").exists(),
                        "wiki_ingest/commands/__init__.py is required")

    def test_dispatch_no_module_level_command_imports(self):
        """TASK 017 R14.5 / Arch Q-2 — `_dispatch.py` is the F3-helper that
        lets `commands/ingest.py` invoke other atomic commands via
        `importlib.import_module` AT CALL TIME. The deliberate
        carve-out: function-body imports are allowed; module-level
        `from wiki_ingest.commands import …` or
        `import wiki_ingest.commands.X` are forbidden.

        The existing `test_no_helper_imports_commands` (above) also
        catches this via `ast.walk` (which recurses into function
        bodies for `ast.Import` / `ast.ImportFrom` nodes), but the
        design uses `importlib.import_module(...)` — a `Call`, not an
        `Import` — which is invisible to the walker. This test
        documents the carve-out explicitly so future maintainers
        don't accidentally lift the local import to module level.
        """
        dispatch_path = PKG / "_dispatch.py"
        # If the helper is not yet present (older revision), skip.
        if not dispatch_path.is_file():
            self.skipTest("wiki_ingest/_dispatch.py not present yet")
        tree = ast.parse(dispatch_path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                self.assertFalse(
                    module.startswith("wiki_ingest.commands"),
                    f"_dispatch.py has a module-level `from {module} "
                    f"import ...` — this violates the dispatch carve-out. "
                    f"Move the import inside `dispatch()` and use "
                    f"`importlib.import_module(...)`.",
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(
                        alias.name.startswith("wiki_ingest.commands"),
                        f"_dispatch.py has a module-level "
                        f"`import {alias.name}` — this violates the "
                        f"dispatch carve-out.",
                    )


if __name__ == "__main__":
    unittest.main()

# Task 015.06 — Extract `commands/scan.py` + `commands/init.py` + R7.4 lint scaffold

## Use Case Connection
- UC-1 (demonstrates the `commands/` module shape on the simplest commands).
- UC-3 (E2E smoke through dispatch).

## Task Goal

Establish the `wiki_ingest/commands/` sub-package and the per-command
`(register, execute)` contract. Move the two trivial subcommands (`scan`,
`init`) first to validate the shape, then lock the import-graph invariant
with the ast-walking lint test (R7.4).

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/wiki_ingest/commands/__init__.py` — empty.
- `skills/wiki-ingest/scripts/wiki_ingest/commands/scan.py` (≤100 LoC).
- `skills/wiki-ingest/scripts/wiki_ingest/commands/init.py` (≤100 LoC).
- `skills/wiki-ingest/scripts/tests/commands/__init__.py`.
- `skills/wiki-ingest/scripts/tests/commands/test_scan.py`.
- `skills/wiki-ingest/scripts/tests/commands/test_init.py`.
- `skills/wiki-ingest/scripts/tests/test_architecture.py` — ast-walking
  invariant test (R7.4).

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

**Symbols to move:**

- `cmd_scan` → `wiki_ingest/commands/scan.py::execute`
- `cmd_init` → `wiki_ingest/commands/init.py::execute`

Add a `register(sub)` function to each command module that takes a
`SubParsersAction` and reproduces the current argparse block for that
subcommand. Move ONLY that subcommand's argparse lines out of
`build_parser`.

In `wiki_ops.py::build_parser`, replace the moved blocks with:

```python
from wiki_ingest.commands import scan, init
scan.register(sub)
init.register(sub)
```

Dispatch keeps using `args.func(args)` (each `register` sets
`func=execute`).

### Command Module Shape

```python
# wiki_ingest/commands/scan.py
import argparse
import json
from pathlib import Path

from wiki_ingest._safety import die
from wiki_ingest._vault import (
    DEFAULT_SUBDIRS, INDEX_FILE, LOG_FILE, SCHEMA_FILE,
    load_vault_pages, tail_log,
)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("scan", help="dump vault state as JSON")
    p.add_argument("vault")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    # ... moved cmd_scan body ...
```

### test_architecture.py invariant

```python
# tests/test_architecture.py
import ast
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "wiki_ingest"

class ImportGraphInvariant(unittest.TestCase):
    def _imports_of(self, path: Path) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        out = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                out.add(node.module)
            elif isinstance(node, ast.Import):
                for n in node.names:
                    out.add(n.name)
        return out

    def test_no_helper_imports_commands(self):
        for helper in PKG.glob("_*.py"):
            mods = self._imports_of(helper)
            for m in mods:
                self.assertFalse(
                    m.startswith("wiki_ingest.commands"),
                    f"{helper.name} imports {m} (helpers must not "
                    f"depend on commands)",
                )

    def test_no_command_imports_another_command(self):
        cmds_dir = PKG / "commands"
        for cmd in cmds_dir.glob("*.py"):
            if cmd.name == "__init__.py":
                continue
            mods = self._imports_of(cmd)
            for m in mods:
                if m.startswith("wiki_ingest.commands.") and \
                        m.split(".")[-1] != cmd.stem:
                    self.fail(
                        f"{cmd.name} imports {m} (commands must not "
                        f"import each other)"
                    )
```

## Test Cases

### Unit Tests

1. **TC-UNIT-06-1**: `test_scan_register_attaches_subparser` — call
   `register(sub)` on a fresh `ArgumentParser`; assert `--help` for
   `scan` is reachable.
2. **TC-UNIT-06-2**: `test_init_register_attaches_subparser` — same.
3. **TC-UNIT-06-3**: `test_architecture.test_no_helper_imports_commands`.
4. **TC-UNIT-06-4**: `test_architecture.test_no_command_imports_another_command`.

### End-to-end Tests

1. **TC-E2E-06-1**: `test_scan.test_scan_byte_identity` — drive
   `python3 wiki_ops.py scan tests/fixtures/scan_vault` via subprocess;
   assert stdout matches expected (alternative wiring to R11 — same
   contract).
2. **TC-E2E-06-2**: `test_init.test_init_creates_layout` — drive
   `wiki_ops.py init /tmp/...`; assert `WIKI_SCHEMA.md`, `index.md`,
   `log.md`, `_sources/`, `_concepts/`, `_entities/` exist.

### Regression Tests

- `tests.test_r11_byte_identity` still green.

## Acceptance Criteria

- [ ] Both command files exist; ≤100 LoC each; expose `register` +
      `execute` only.
- [ ] `test_architecture` passes (R7.4).
- [ ] R11 gate green; `validate_skill.py` exits 0.

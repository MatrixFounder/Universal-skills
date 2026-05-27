# Task 017.03 — `_dispatch.py` F3 helper (resolves architecture Q-2)

## Use Case Connection

- Foundation for **UC-1**, **UC-2**, **UC-5** (every UC where the
  orchestrator composes atomic ops). Without this helper, 017-05 cannot
  exist.

## Task Goal

Ship the new F3-boundary helper `wiki_ingest/_dispatch.py` that lets
`commands/ingest.py` invoke other atomic commands without violating the
"no command imports another command" invariant
([`docs/ARCHITECTURE.md` §3.2](../ARCHITECTURE.md#32-system-components)).
The helper exposes a single public function `dispatch(cmd_name, args)`
that validates `cmd_name` against a whitelist (T17-S9), imports the
target `wiki_ingest.commands.<cmd>` module **at call time inside the
function body** (so the module-level AST stays clean), and invokes its
`execute(args)`. Errors route through `_safety.die` with the new
`EXIT_*` constants.

The bead also extends `tests/test_architecture.py` with the new
"`_dispatch.py` has no module-level `wiki_ingest.commands.*` imports"
assertion (R14.5 + Arch-M-2).

Per Stub-First: this is a substrate helper — Test-First. Write the
assertions (whitelist enforcement, propagation of `execute` return,
unknown-name routing), confirm Red, then implement.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/wiki_ingest/_dispatch.py` (≤ 80 LoC per
  architecture §3.2 budget).
- `skills/wiki-ingest/scripts/tests/test__dispatch.py` — unit-test
  module.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/tests/test_architecture.py`

- Add a new test method `test_dispatch_no_module_level_command_imports`
  that walks `_dispatch.py` via `ast.parse` and asserts ZERO of the
  module-level `ast.Import` / `ast.ImportFrom` nodes reference
  `wiki_ingest.commands` (any submodule). Local imports inside function
  bodies are visited and SHOULD be found — the test does NOT flag them
  (they are the intended pattern).
- The existing test methods (TASK 015 import-graph rules) are unchanged.

### File contents (`wiki_ingest/_dispatch.py`)

**Module-level**:

```python
"""F3-boundary dispatch helper.

Lets commands/ingest.py invoke other atomic commands without
violating the "no command imports another command" invariant. The
target command is imported at CALL TIME inside dispatch() — never at
module level. test_architecture.py asserts this.

Whitelist enforced before importlib.import_module (T17-S9).
"""

import argparse
import importlib

from . import _safety

_ALLOWED_COMMANDS: frozenset[str] = frozenset({
    "register-summary",
    "upsert-page",
    "update-index",
    "append-log",
    "log-event",
})
```

**Function `dispatch(cmd_name: str, args: argparse.Namespace) -> int`:**
- Parameters:
  - `cmd_name` — hyphenated CLI form (e.g. `"upsert-page"`).
  - `args` — already-built argparse Namespace; passed through verbatim
    to the target's `execute(args)`.
- Returns: the target's exit code (int).
- Logic:
  1. If `cmd_name not in _ALLOWED_COMMANDS`:
     `_safety.die(f"UNKNOWN_COMMAND: {cmd_name!r}", code=_safety.EXIT_USAGE)`.
  2. Translate to module name: `module_name = cmd_name.replace("-", "_")`.
  3. Local import: `mod = importlib.import_module(f"wiki_ingest.commands.{module_name}")`.
  4. Return `mod.execute(args)`.

### Component Integration

- `_dispatch.py` lives at F3-helper tier (sibling of `_vault.py`,
  `_classify.py`). It imports only `argparse`, `importlib`, and
  `_safety` at module level — no command modules.
- Local-inside-function `importlib.import_module` is the entire reason
  this helper exists. `test_architecture.py` extension locks the
  invariant.
- The whitelist is small (5 entries — exactly the atomic ops the
  orchestrator composes). Adding a new dispatchable command in a future
  task requires explicitly adding it to `_ALLOWED_COMMANDS` (review-gate
  by design).
- Consumers (017-06) call `_dispatch.dispatch("upsert-page", args)` and
  propagate the return code into `written[]` / partial-envelope logic.

## Test Cases

### Unit Tests (`tests/test__dispatch.py` — new)

1. **TC-UNIT-017-03-01:** Happy path — known command propagates exit 0
   - Setup: `args` = a real `argparse.Namespace` matching the
     `register-summary` command's expectations on a fixture vault.
   - Run: `dispatch("register-summary", args)`.
   - Expected: exit code from `commands.register_summary.execute(args)`
     returned verbatim (0 in the happy case).
2. **TC-UNIT-017-03-02:** Whitelist enforcement — unknown name → exit 2
   - Run: `dispatch("rm-rf-vault", args)`.
   - Expected: SystemExit with `code == EXIT_USAGE == 2`; stderr
     contains `UNKNOWN_COMMAND`. NO import of any module attempted.
3. **TC-UNIT-017-03-03:** Whitelist boundary — `init`, `promote`,
   `demote`, `lint`, `reindex`, `scan`, `find`, `classify-folder`,
   `ingest` are NOT in the whitelist (only the 5 atomic ops are)
   - For each of the above names: `dispatch(name, args)` → SystemExit
     code 2. Reason: the orchestrator must NOT recurse via dispatch
     into itself or into broader commands; the whitelist documents the
     intended call graph.
4. **TC-UNIT-017-03-04:** Hyphen-to-underscore translation
   - Mock `importlib.import_module` to assert it receives
     `"wiki_ingest.commands.upsert_page"` (underscore form) when
     `dispatch("upsert-page", args)` is called.
5. **TC-UNIT-017-03-05:** Module-level import shape (defense-in-depth
   test, complements the architecture test)
   - Read `_dispatch.py` via `ast.parse`. Assert NO top-level
     `ImportFrom` with `module.startswith("wiki_ingest.commands")` AND
     NO top-level `Import` of a name starting with
     `"wiki_ingest.commands"`.
   - Reason: locks the invariant inside the helper's own test file too
     — easier to find when grepping for the dispatch contract.
6. **TC-UNIT-017-03-06:** Whitelist contents are a frozenset
   - Assert `isinstance(_ALLOWED_COMMANDS, frozenset)` and
     `len(_ALLOWED_COMMANDS) == 5`.
   - Reason: prevents accidental runtime mutation; mutability would
     defeat T17-S9.

### Architecture Tests (`tests/test_architecture.py` — extended)

1. **TC-ARCH-017-03-01:** `_dispatch.py` has no module-level
   `wiki_ingest.commands.*` imports
   - The new test method walks `_dispatch.py` via `ast.parse`, iterates
     `tree.body`, and asserts every `ast.Import` / `ast.ImportFrom`
     node is either (a) a stdlib import, (b) a `wiki_ingest._*` helper
     import, or (c) NOT a `wiki_ingest.commands.*` reference.
   - Function-body imports (inside `dispatch()`) are NOT visited (the
     walker stops at `tree.body`).
2. Existing TASK 015/016 assertions unchanged and green.

### Regression Tests

- Run all TASK 015/016 existing tests — no regression.
- `tests/test_architecture.py` green (existing + new assertion).

## Acceptance Criteria

- [ ] `_dispatch.py` exists at ≤ 80 LoC.
- [ ] `_ALLOWED_COMMANDS` is a frozenset of exactly 5 entries
      (TC-UNIT-017-03-06).
- [ ] Unknown name → SystemExit code 2 with `UNKNOWN_COMMAND` envelope
      BEFORE any `importlib.import_module` call (TC-UNIT-017-03-02).
- [ ] Hyphen-to-underscore translation correct (TC-UNIT-017-03-04).
- [ ] No module-level `wiki_ingest.commands.*` imports
      (TC-UNIT-017-03-05 + TC-ARCH-017-03-01).
- [ ] Whitelist explicitly excludes broader commands (TC-UNIT-017-03-03).
- [ ] All TASK 015/016 tests still green.

## Notes

- **Why local-imports-only is sustainable**: the AST walker pattern in
  `test_architecture.py` parses each `.py` file's `tree.body` (top-level
  statements only). Function-body imports are nested under
  `FunctionDef → Import / ImportFrom` and are NOT visited by the walker.
  A future maintainer would have to LIFT the `importlib.import_module`
  call from inside the function body to module level to trigger a
  regression — which is a deliberate, hard-to-miss change.
- The whitelist is short by design. Adding `lint` or `reindex` to it
  later requires a TASK / ADR — these are operator-facing commands the
  orchestrator should not recurse into.
- `importlib.import_module` caches imports in `sys.modules` after the
  first call (CPython invariant). The "cold ≤5 ms + warm ≤0.1 ms"
  performance budget from architecture §8 holds: ingest's pipeline pays
  the cold cost once per atomic op kind, then warm dispatches are
  effectively a dict lookup + attribute access.

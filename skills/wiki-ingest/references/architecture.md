# wiki-ingest — module architecture

Maintainer-facing reference for the post-TASK-015 layout. For the full
rationale + risk register, see [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md)
and [`docs/TASK.md`](../../../docs/TASK.md) at the repo root.

## Layout

```
skills/wiki-ingest/
├── SKILL.md                            # public agent contract (unchanged)
├── assets/                             # markdown templates
├── examples/
├── references/                         # ← you are here
├── evals/                              # eval suite + fixtures
└── scripts/
    ├── wiki_ops.py                     # 69-LoC argparse shim — argparse + dispatch only
    ├── wiki_ingest/                    # internal package (NOT a public API)
    │   ├── __init__.py
    │   ├── _safety.py                  # F1 — atomic I/O, NFKC, sanitised JSON
    │   ├── _markdown.py                # F2 — code-fence + inline masking, sections, wikilinks
    │   ├── _frontmatter.py             # F2 — YAML parse + structural splice
    │   ├── _vault.py                   # F3-helper — layout constants, walk, tail_log
    │   ├── _classify.py                # F3-helper — folder-classify helpers
    │   └── commands/
    │       ├── __init__.py
    │       ├── scan.py
    │       ├── init.py
    │       ├── upsert_page.py
    │       ├── update_index.py
    │       ├── append_log.py
    │       ├── register_summary.py
    │       ├── log_event.py
    │       ├── find.py
    │       ├── lint.py
    │       ├── reindex.py
    │       └── classify_folder.py
    └── tests/                          # unittest suite (128 tests, 1 skipped)
        ├── __init__.py · .AGENTS.md
        ├── fixtures/                   # R11 byte-identity fixtures (frozen)
        ├── test__safety.py
        ├── test__markdown.py
        ├── test__frontmatter.py
        ├── test__vault.py
        ├── test__classify.py
        ├── test_architecture.py        # R7.4 ast-walking import-graph lint
        ├── test_r11_byte_identity.py   # byte-identity gate against fixtures
        └── commands/                   # per-command tests
            ├── __init__.py
            ├── test_scan.py · test_init.py
            ├── test_upsert_page.py · test_update_index.py
            ├── test_append_log.py · test_log_event.py
            ├── test_register_summary.py
            ├── test_find_lint_reindex.py
            └── test_classify_folder.py
```

## Dependency rule (one-way only)

```
        F3 commands/*.py · _vault.py · _classify.py
                          ↑
        F2 _markdown.py · _frontmatter.py
                          ↑
        F1 _safety.py
```

Enforced by `tests/test_architecture.py` via stdlib `ast` walk:
- **No `_*.py` helper imports `commands.*`** (F1/F2/F3-helper stays below).
- **No `commands/<a>.py` imports `commands/<b>.py`** (commands are independent).

A test failure = the DAG is broken; fix the import, don't relax the test.
**Known blind spot**: dynamic imports (`importlib`, `__import__`) are not
detected by AST walk — keep those out of helper modules by code review.

## Command module contract

Every file in `commands/` exposes EXACTLY two public symbols:

```python
def register(sub: argparse._SubParsersAction) -> None:
    """Attach this command's subparser. Called once at CLI startup."""
    p = sub.add_parser("<cmd-name>", help="...")
    p.add_argument(...)
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """Run the command. Return process exit code (0 = success)."""
    ...
```

`wiki_ops.py` iterates `_COMMAND_MODULES = (scan, init, …)` and calls
`mod.register(sub)` on each. Dispatch happens via `args.func(args)`
after `parser.parse_args(argv)`.

## Adding a new command

1. Create `scripts/wiki_ingest/commands/<your_cmd>.py` exposing
   `register` + `execute`.
2. Add it to the `_COMMAND_MODULES` tuple in `wiki_ops.py` (2-line change:
   one import, one tuple entry).
3. Add `tests/commands/test_<your_cmd>.py` with at least:
   - one `test_register_*` (attaches subparser correctly)
   - one `test_execute_*` (happy path)
   - one adversarial test if the command takes user input

## Where does a new helper go?

| Used by … | Goes in … |
|-----------|-----------|
| Exactly one command, no security/markdown content | Keep it command-local in `commands/<cmd>.py` (private with `_` prefix) |
| ≥2 commands, atomic I/O / NFKC / safe-name etc. | `_safety.py` (F1) |
| ≥2 commands, markdown structure | `_markdown.py` (F2) |
| ≥2 commands, YAML frontmatter | `_frontmatter.py` (F2) |
| ≥2 commands, vault path / walk / log | `_vault.py` (F3-helper) |
| `classify-folder` only | `_classify.py` (F3-helper) |
| ≥2 commands, cross-tier | usually means the abstraction is wrong; ask first |

## R11 byte-identity gate

The CLI behaviour is locked by `tests/test_r11_byte_identity.py`:
- `wiki_ops.py scan tests/fixtures/scan_vault` stdout matches `expected/scan.json`
- `wiki_ops.py lint tests/fixtures/lint_vault` matches `expected/lint.json`
- `wiki_ops.py classify-folder tests/fixtures/classify_folder` matches `expected/classify.json`

Each test runs the command via `subprocess.run` with varied
`PYTHONHASHSEED` so any nondeterministic set-iteration leak into JSON
output would manifest as a failure.

**If you change ANY command and R11 fails**: your refactor is not
behaviour-preserving — fix it, don't update the expected file. The
expected files are intentionally frozen.

## Running the suite locally

```bash
cd skills/wiki-ingest/scripts
python3 -m venv .venv && source .venv/bin/activate
python -m unittest discover -s tests
```

128 tests should pass (1 skipped — pre-existing S-M1b symlink-resolve
order bug, logged in `docs/KNOWN_ISSUES.md`).

Plus the two validators:
```bash
python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/wiki-ingest
python3 .claude/skills/skill-validator/scripts/validate.py skills/wiki-ingest
```

Both must pass before merging any change to the package.

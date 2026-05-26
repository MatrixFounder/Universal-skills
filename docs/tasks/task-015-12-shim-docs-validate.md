# Task 015.12 — Trim `wiki_ops.py` to ≤200 LoC + `references/architecture.md` + final validator pass

## Use Case Connection
- UC-3 (final E2E + validator pass).

## Task Goal

The "final boss" bead — close out the refactor:

1. Remove every back-compat re-export from `wiki_ops.py`; the shim becomes
   pure argparse + dispatch.
2. Drop dead code that the back-compat shims were keeping alive.
3. Add `skills/wiki-ingest/references/architecture.md` — the
   maintainer-facing reference doc (≤200 LoC, distilled from
   `docs/ARCHITECTURE.md` §2-§3 and §13).
4. Run the full validator pair + R11 + cross-skill matrix; confirm all
   green; capture a "before/after LoC" diff in the PR description.

## Changes Description

### New Files

- `skills/wiki-ingest/references/architecture.md` (≤200 LoC).

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

**Before (post-015-11):** ~600-800 LoC of argparse + re-exports + dispatch.

**After:** ≤200 LoC of:

```python
#!/usr/bin/env python3
"""wiki_ops.py — argparse shim for the wiki-ingest skill.

Every subcommand lives in `wiki_ingest/commands/<name>.py`. See
`references/architecture.md` for the module layout and the
`F1 → F2 → F3` dependency rule. This shim does only:
  1. parse argv via argparse,
  2. dispatch to the selected command's `execute(args)`.
"""
from __future__ import annotations

import argparse
import sys

from wiki_ingest.commands import (
    scan, init, upsert_page, update_index, append_log, register_summary,
    log_event, find, lint, reindex, classify_folder,
)

_COMMAND_MODULES = (
    scan, init, upsert_page, update_index, append_log, register_summary,
    log_event, find, lint, reindex, classify_folder,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wiki_ops", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    for mod in _COMMAND_MODULES:
        mod.register(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

**Symbols to DROP from `wiki_ops.py`:** every `from wiki_ingest.* import …`
line introduced as a back-compat re-export across 015-01..015-11. After
this bead, the shim's only `from wiki_ingest.*` import is the command
modules.

### `references/architecture.md` content

A ≤200-line maintainer reference distilling:
- The module graph diagram (copy from `docs/ARCHITECTURE.md` §2.2).
- The dependency rule (F3 → F2 → F1) with a "Decision rule" subsection
  for "where does a new helper go?" (matches UC-1-alt).
- The command-module contract (`register` + `execute` signatures).
- The R11 / R7.4 invariants and how to run them locally.
- A pointer back to `docs/TASK.md` and `docs/ARCHITECTURE.md` for the
  full rationale.

This document is the **only** wiki-ingest-specific doc that lives in
the skill folder (not in `docs/`); future maintainers see it via
`grep architecture skills/wiki-ingest/references/`.

## Test Cases

### Unit Tests

1. **TC-UNIT-12-1**: `test_shim_loc_ceiling` — open
   `skills/wiki-ingest/scripts/wiki_ops.py`, count non-blank/non-comment
   lines, assert ≤200. (Locks R1.2.)

2. **TC-UNIT-12-2**: `test_architecture_doc_exists` — assert
   `references/architecture.md` exists and is non-empty.

### End-to-end Tests

The full test suite + R11 + validator runs here:

1. `python -m unittest discover -s tests` — 0 failures.
2. `tests.test_r11_byte_identity.*` — all three pass.
3. `tests.test_architecture.*` — both invariant tests pass.
4. `python3 .claude/skills/skill-creator/scripts/validate_skill.py
   skills/wiki-ingest` — exits 0.
5. `python3 .claude/skills/skill-validator/scripts/validate.py
   skills/wiki-ingest` — risk `SAFE`, 0 Critical / 0 Errors.

### Cross-skill replication matrix check (R9)

```bash
find skills/wiki-ingest/scripts -name "*.py" -exec basename {} \; \
  | sort -u > /tmp/wi.txt
for s in docx xlsx pptx pdf; do
  echo "--- $s ---"
  find skills/$s/scripts -name "*.py" -exec basename {} \; | sort -u \
    | comm -12 - /tmp/wi.txt
done
```

Expected: each `--- $s ---` section is empty (no shared filenames).

### Regression Tests

Run every fixture-driven test from 015-00..015-11; all must pass.

## Acceptance Criteria

- [ ] `wiki_ops.py` ≤200 LoC.
- [ ] `references/architecture.md` exists, ≤200 LoC.
- [ ] All unit + E2E + R11 + architecture tests pass.
- [ ] `validate_skill.py` exits 0.
- [ ] `skill-validator/validate.py` reports SAFE, 0 Critical / 0 Errors.
- [ ] Cross-skill replication matrix silent (R9).
- [ ] Merge commit message references this Task ID (`015`), the §0
      Meta predecessor commits, and links to `docs/TASK.md` +
      `docs/ARCHITECTURE.md`.
- [ ] PR description includes a "Before / After" LoC table:
      `wiki_ops.py 2661 → ≤200`, total `scripts/` LoC delta, new
      `tests/` LoC, validator outputs.

## Notes

- This is the only bead that touches `references/architecture.md`. The
  doc is final and may be referenced from future tasks; it is the
  source of truth for "how do I add a new wiki-ingest feature."
- Do NOT bundle behavioural changes into this bead. If any cosmetic
  finding from `KNOWN_ISSUES.md` (L-H2, L-L2/L3/L8/L9, etc.) is
  tempting — DEFER. Land it as a follow-up cosmetic task once the
  refactor is merged.

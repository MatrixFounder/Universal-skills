#!/usr/bin/env python3
"""
wiki_ops.py — deterministic vault operations for the wiki-ingest skill.

Subcommands:
  scan          dump vault state as JSON (existing concepts/entities/sources, schema presence)
  init          scaffold a fresh vault (WIKI_SCHEMA.md, index.md, log.md, subdirs) — idempotent
  upsert-page   create or additively update a concept/entity page
  update-index  add/update rows in index.md
  append-log    append a grep-friendly entry to log.md

Design notes:
- Pure stdlib; no external deps.
- Mutating subcommands accept --dry-run (prints diff to stdout, no write).
- upsert-page and update-index dedupe by slug; append-log is intentionally non-idempotent.
- Frontmatter is parsed/written naively (block between leading '---' lines).
- WIKI_SCHEMA.md presence is a precondition for upsert-page/update-index/append-log
  (exit code 2 if missing) — run `init` first.
"""
from __future__ import annotations

import argparse
import sys

# All command logic lives in `wiki_ingest/commands/<cmd>.py`. Each module
# exposes `register(subparser)` and `execute(args) -> int`. This shim does
# only argparse wiring + dispatch. See `wiki_ingest/__init__.py` for the
# layered DAG (F1 _safety → F2 _markdown/_frontmatter → F3 _vault/_classify
# + commands/). Tests in ../tests/ enforce the import-graph invariant.
from wiki_ingest.commands import (
    append_log,
    classify_folder,
    find,
    init,
    lint,
    log_event,
    register_summary,
    reindex,
    scan,
    update_index,
    upsert_page,
)

_COMMAND_MODULES = (
    scan, init,
    upsert_page, update_index,
    append_log, register_summary, log_event,
    find, lint, reindex,
    classify_folder,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki_ops", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for mod in _COMMAND_MODULES:
        mod.register(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

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

from wiki_ingest import __version__ as _WIKI_INGEST_VERSION


def build_parser() -> argparse.ArgumentParser:
    # Command modules are imported lazily INSIDE build_parser() so that the
    # top-level `--version` fast path in main() does not pay the ~13×
    # module-import cost (TASK 017 R2 / architecture §8 ≤50 ms budget).
    # The argparse `--version` action below is reachable ONLY through
    # `--help` discoverability (humans listing top-level flags); when the
    # user actually runs `wiki_ops.py --version`, main()'s fast path
    # short-circuits before this parser is built.
    from wiki_ingest.commands import (
        append_log,
        classify_folder,
        demote,
        find,
        ingest,
        init,
        lint,
        log_event,
        promote,
        register_summary,
        reindex,
        scan,
        update_index,
        upsert_page,
    )

    command_modules = (
        scan, init,
        upsert_page, update_index,
        append_log, register_summary, log_event,
        find, lint, reindex,
        classify_folder,
        promote, demote,
        ingest,
    )

    p = argparse.ArgumentParser(prog="wiki_ops", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version",
                   version=f"wiki-ingest {_WIKI_INGEST_VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)
    for mod in command_modules:
        mod.register(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    # Fast path for `wiki-ingest --version` (TASK 017 R2 / CONTRACT §7):
    # avoid importing the ~13 command modules for a single-string read.
    # Output format is locked: consumers prefix-match `wiki-ingest <ver>`.
    if argv and argv[0] == "--version":
        sys.stdout.write(f"wiki-ingest {_WIKI_INGEST_VERSION}\n")
        return 0
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

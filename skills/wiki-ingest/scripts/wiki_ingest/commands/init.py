"""`init` subcommand — scaffold a fresh wiki vault.

Idempotent: existing files / subdirs are reported as `skipped` rather
than overwritten. The three bundled templates (`WIKI_SCHEMA.template.md`,
`index.template.md`, `log.template.md`) are loaded via `load_asset`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from wiki_ingest._safety import write_text
from wiki_ingest._vault import (
    DEFAULT_SUBDIRS,
    INDEX_FILE,
    LOG_FILE,
    SCHEMA_FILE,
    load_asset,
)


def register(sub: argparse._SubParsersAction) -> None:
    """Attach the `init` subparser. Called once at CLI startup."""
    p = sub.add_parser("init", help="scaffold a fresh vault (idempotent)")
    p.add_argument("vault")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """Create vault skeleton (schema / index / log / subdirs); return 0."""
    vault = Path(args.vault).resolve()
    vault.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    skipped: list[str] = []

    for fname, asset in (
        (SCHEMA_FILE, "WIKI_SCHEMA.template.md"),
        (INDEX_FILE, "index.template.md"),
        (LOG_FILE, "log.template.md"),
    ):
        target = vault / fname
        if target.exists():
            skipped.append(fname)
            continue
        write_text(target, load_asset(asset), args.dry_run)
        created.append(fname)

    for sd in DEFAULT_SUBDIRS:
        d = vault / sd
        if d.is_dir():
            skipped.append(f"{sd}/")
        else:
            if not args.dry_run:
                d.mkdir(parents=True, exist_ok=True)
            created.append(f"{sd}/")

    print(json.dumps({"created": created, "skipped": skipped}, indent=2))
    return 0

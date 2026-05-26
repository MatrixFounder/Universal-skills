"""`init` subcommand — scaffold a fresh wiki vault.

Idempotent: existing files / subdirs are reported as `skipped` rather
than overwritten. The course-local path is the TASK 015 default — schema
+ index + log + `_sources/_concepts/_entities/`. TASK 016 bead 016-03
added `--root`: scaffolds the vault-root layer (schema_version: 2.0,
`_concepts/_entities/` only — NO `_sources/`, NO `log.md`).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from wiki_ingest._safety import die, write_text
from wiki_ingest._vault import (
    DEFAULT_SUBDIRS,
    INDEX_FILE,
    LOG_FILE,
    SCHEMA_FILE,
    load_asset,
)

# Subdirs scaffolded at the vault ROOT (no _sources/ — sources live only
# in courses). NOT a `DEFAULT_SUBDIRS` reuse: roots have a different shape.
_ROOT_SUBDIRS = ("_concepts", "_entities")
_ROOT_SCHEMA_ASSET = "WIKI_SCHEMA.root.template.md"


def register(sub: argparse._SubParsersAction) -> None:
    """Attach the `init` subparser. Called once at CLI startup."""
    p = sub.add_parser("init", help="scaffold a fresh vault (idempotent)")
    p.add_argument("vault")
    p.add_argument("--root", action="store_true",
                   help="scaffold a vault-ROOT schema (schema_version: 2.0) "
                        "instead of a course-local one. Creates _concepts/ "
                        "and _entities/ ONLY — no _sources/, no log.md.")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """Create vault skeleton; return 0. Branches on `--root`."""
    # `getattr` shim for direct callers that build a Namespace manually
    # without going through `register()` (existing TASK 015 unit tests).
    if getattr(args, "root", False):
        return _execute_root(args)
    return _execute_course(args)


def _execute_course(args: argparse.Namespace) -> int:
    """v1 course-local scaffold (TASK 015 baseline)."""
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


def _execute_root(args: argparse.Namespace) -> int:
    """TASK 016 vault-root scaffold (schema_version: 2.0)."""
    vault = Path(args.vault)
    if not vault.exists():
        die(f"target directory does not exist: {vault}", code=1)
    vault = vault.resolve()
    created: list[str] = []
    skipped: list[str] = []

    # Root schema (the only file written — no log.md, no index.md, no _sources/)
    schema_target = vault / SCHEMA_FILE
    if schema_target.exists():
        skipped.append(SCHEMA_FILE)
    else:
        write_text(schema_target, load_asset(_ROOT_SCHEMA_ASSET), args.dry_run)
        created.append(SCHEMA_FILE)

    # _concepts/ + _entities/ — empty directories, no sentinel files
    for sd in _ROOT_SUBDIRS:
        d = vault / sd
        if d.is_dir():
            skipped.append(f"{sd}/")
        else:
            if not args.dry_run:
                d.mkdir(parents=True, exist_ok=True)
            created.append(f"{sd}/")

    print(json.dumps(
        {"created": created, "skipped": skipped, "kind": "vault-root"},
        indent=2,
    ))
    return 0

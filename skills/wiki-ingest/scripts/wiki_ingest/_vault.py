"""F3-helper · Vault layout constants + walk + tail_log for wiki-ingest.

Single source of truth for the on-disk vault shape (Obsidian-style
`_sources/`, `_concepts/`, `_entities/` system folders + `WIKI_SCHEMA.md`
/ `index.md` / `log.md` at the root). Symlinks are refused at the walk
boundary (OVERLAP-5). `tail_log` is code-fence aware (L-M6).

Imports F1 (`_safety`) and F2 (`_frontmatter`, `_markdown`) per the
layered DAG. Tested by `../tests/test__vault.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

from wiki_ingest._frontmatter import split_frontmatter
from wiki_ingest._markdown import _mask_code_fences
from wiki_ingest._safety import _skip_symlink, die, read_text


# Folder names use the Obsidian system-folder convention: a leading underscore
# sorts them at the top of the file tree and signals "vault meta-content,
# not user notes." Display labels in index.md stay human-readable
# (Sources / Concepts / Entities) — see SUBDIR_TO_DISPLAY below.
DEFAULT_SUBDIRS = ("_sources", "_concepts", "_entities")
SUBDIR_TO_KIND = {"_sources": "source", "_concepts": "concept", "_entities": "entity"}
SUBDIR_TO_DISPLAY = {"_sources": "Sources", "_concepts": "Concepts", "_entities": "Entities"}
SCHEMA_FILE = "WIKI_SCHEMA.md"
INDEX_FILE = "index.md"
LOG_FILE = "log.md"

# ASSETS_DIR resolves to `skills/wiki-ingest/assets/`. This file lives at
# `skills/wiki-ingest/scripts/wiki_ingest/_vault.py`, so we walk three
# parents up (`_vault.py` → `wiki_ingest/` → `scripts/` → `wiki-ingest/`).
ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"


def _walk_pages(vault: Path):
    """Yield every `.md` page in the vault, EXCLUDING symlinks.

    Symlinks are skipped to refuse exfiltration via a malicious vault entry
    like `_concepts/secrets.md -> /etc/passwd` or `_sources/x.md -> ~/.aws/credentials`.
    """
    for sub in DEFAULT_SUBDIRS:
        d = vault / sub
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            if _skip_symlink(md):
                continue
            yield md
    for md in sorted(vault.glob("*.md")):
        if md.name in (INDEX_FILE, LOG_FILE, SCHEMA_FILE):
            continue
        if _skip_symlink(md):
            continue
        yield md


def load_vault_pages(vault: Path) -> dict:
    """Walk the vault and collect frontmatter from every .md page.

    Pages are keyed by filename stem (which IS unique on a case-sensitive
    filesystem), not by `title:` — two files with the same `title:` should
    both surface in `scan`/known-concepts. The displayed name carries the
    title separately so callers can render it.

    Skips symlinks — a malicious vault could contain
    `_concepts/secrets.md -> /etc/passwd`; following it would surface
    arbitrary user files in the agent's view of the wiki.
    """
    pages = {"concepts": {}, "entities": {}, "sources": {}, "other": []}
    for kind, subdir, bucket in (
        ("concept", "_concepts", "concepts"),
        ("entity", "_entities", "entities"),
        ("source", "_sources", "sources"),
    ):
        d = vault / subdir
        if not d.exists():
            continue
        for md in d.glob("*.md"):
            if _skip_symlink(md):
                continue
            fm, _ = split_frontmatter(read_text(md))
            title = fm.get("title") or md.stem
            pages[bucket][md.stem] = {
                "path": str(md.relative_to(vault)),
                "title": title,
                "frontmatter": fm,
            }
    # also scan root-level pages that aren't index/log/schema
    for md in vault.glob("*.md"):
        if md.name in (INDEX_FILE, LOG_FILE, SCHEMA_FILE):
            continue
        if _skip_symlink(md):
            continue
        fm, _ = split_frontmatter(read_text(md))
        pages["other"].append({
            "path": str(md.relative_to(vault)),
            "title": fm.get("title") or md.stem,
        })
    return pages


def ensure_schema(vault: Path) -> None:
    """Refuse to run mutating commands on a vault that lacks `WIKI_SCHEMA.md`.

    Exits with code 2 (the documented "missing schema" exit code) so callers
    can distinguish this from other failures.
    """
    if not (vault / SCHEMA_FILE).exists():
        die(f"{SCHEMA_FILE} not found in {vault}. Run `wiki_ops.py init {vault}` first.", code=2)


def load_asset(name: str) -> str:
    """Load a packaged template asset from `skills/wiki-ingest/assets/`.

    Fails closed via `die()` if the asset is missing — every bundled asset
    is required for the skill to function (e.g., `WIKI_SCHEMA.template.md`).
    """
    path = ASSETS_DIR / name
    if not path.exists():
        die(f"missing bundled asset: {path}")
    return path.read_text(encoding="utf-8")


def tail_log(vault: Path, n: int) -> list[str]:
    """Return the last `n` `## [YYYY-MM-DD] …` heading lines from `log.md`.

    Code-fence aware: a `## [date]` heading inside a fenced example
    block is NOT surfaced as a real log entry (L-M6). The `[^\\n]`
    upper-bound on the line tail keeps the regex linear.
    """
    log = vault / LOG_FILE
    if not log.exists():
        return []
    raw = read_text(log)
    masked = _mask_code_fences(raw)
    entries: list[str] = []
    for m in re.finditer(r"^## \[[^\n]+$", masked, flags=re.M):
        # use the ORIGINAL content's slice (offsets are preserved by masking)
        entries.append(raw[m.start():m.end()])
    return entries[-n:]

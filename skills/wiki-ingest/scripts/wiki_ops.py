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
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ASSETS_DIR = SKILL_DIR / "assets"

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


# ---------- helpers ----------

def die(msg: str, code: int = 1) -> None:
    print(f"wiki_ops: error: {msg}", file=sys.stderr)
    sys.exit(code)


def slugify(text: str) -> str:
    """Unicode-aware slug. Preserves non-ASCII letters (Cyrillic, CJK, etc.)."""
    text = text.strip().lower()
    # \w is Unicode-aware in Python 3 — keeps letters, digits, underscore;
    # collapses everything else into a single dash.
    text = re.sub(r"[^\w-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-+", "-", text)
    return text.strip("-_")


_UNSAFE_NAME_RE = re.compile(r"[\x00-\x1f/\\]")


def _safe_name(name: str, kind: str = "name") -> str:
    """Validate that `name` is safe to use as a filename component.

    Rejects: empty, leading dot, path separators, traversal, control chars,
    and template placeholders that would confuse stub rendering.
    Returns the name unchanged if safe; calls die() otherwise.
    """
    if not name or not name.strip():
        die(f"--{kind} is empty")
    name = name.strip()
    if name in (".", "..") or name.startswith("."):
        die(f"--{kind}={name!r}: must not start with '.' or be a traversal token")
    if _UNSAFE_NAME_RE.search(name):
        die(f"--{kind}={name!r}: must not contain '/', '\\', or control chars")
    if ".." in name:
        die(f"--{kind}={name!r}: must not contain '..'")
    if "{{" in name or "}}" in name:
        die(f"--{kind}={name!r}: must not contain template placeholders '{{{{' or '}}}}'")
    if len(name) > 200:
        die(f"--{kind}: too long ({len(name)} chars; max 200)")
    return name


def _check_case_collision(target_dir: Path, name: str) -> str | None:
    """Return the existing filename if a different-casing file already exists, else None."""
    if not target_dir.is_dir():
        return None
    want = (name + ".md").lower()
    for existing in target_dir.iterdir():
        if existing.name.lower() == want and existing.name != name + ".md":
            return existing.name
    return None


def _mask_code_fences(text: str) -> str:
    """Replace the content of ``` fenced code blocks with spaces, preserving offsets.

    This lets section/header regexes operate on a 'logical' view of the document
    where markdown examples inside code fences don't trigger false header matches.
    Non-fence content is untouched.
    """
    out = []
    in_fence = False
    fence_marker = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = True
                fence_marker = stripped[:3]
                out.append(line)
            else:
                out.append(line)
        else:
            if stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = None
                out.append(line)
            else:
                # Replace with spaces of equal length to preserve byte offsets,
                # keeping the trailing newline so line positions are stable.
                if line.endswith("\n"):
                    out.append(" " * (len(line) - 1) + "\n")
                else:
                    out.append(" " * len(line))
    return "".join(out)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_text(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        print(f"--- WOULD WRITE: {path} ---")
        print(content)
        print(f"--- END {path} ---")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


SECTION_BOUNDARY_RE = re.compile(r"^(## |---\s*$)", re.M)


def find_section(content: str, header_text: str,
                 occurrence: int = 0) -> tuple[int, int, int] | None:
    """Locate a '## <header_text>' section, ignoring headers inside code fences.

    Returns (header_start, body_start, body_end). The body spans from the
    character after the header line up to (but not including) the next
    '## ' line OR a standalone '---' line OR EOF (positions are valid in
    the original content, since the masked view preserves offsets).
    Returns None if the requested `occurrence` (0-indexed) is not present.
    """
    masked = _mask_code_fences(content)
    matches = list(re.finditer(rf"^## {re.escape(header_text)}[ \t]*$",
                               masked, re.M))
    if occurrence < 0 or occurrence >= len(matches):
        return None
    h = matches[occurrence]
    body_start = h.end()
    if body_start < len(masked) and masked[body_start] == "\n":
        body_start += 1
    rest = masked[body_start:]
    nxt = SECTION_BOUNDARY_RE.search(rest)
    body_end = body_start + (nxt.start() if nxt else len(rest))
    return h.start(), body_start, body_end


def find_all_sections(content: str, header_text: str) -> list[tuple[int, int, int]]:
    """Return positions for ALL occurrences of a `## <header_text>` section."""
    out: list[tuple[int, int, int]] = []
    n = 0
    while True:
        loc = find_section(content, header_text, occurrence=n)
        if loc is None:
            break
        out.append(loc)
        n += 1
    return out


def get_all_section_bodies(content: str, header_text: str) -> list[str]:
    """Return body text for every occurrence of a `## <header_text>` section."""
    return [content[body_start:body_end]
            for _, body_start, body_end in find_all_sections(content, header_text)]


def get_section_body(content: str, header_text: str) -> str | None:
    loc = find_section(content, header_text)
    if loc is None:
        return None
    _, body_start, body_end = loc
    return content[body_start:body_end]


def replace_section_body(content: str, header_text: str, new_body: str) -> str:
    """Replace the body of an existing section. Preserves surrounding whitespace."""
    loc = find_section(content, header_text)
    if loc is None:
        return content
    _, body_start, body_end = loc
    # normalise: exactly one blank line above/below body
    normalised = "\n" + new_body.strip("\n") + "\n\n"
    return content[:body_start] + normalised + content[body_end:].lstrip("\n")


def insert_section_before(content: str, anchor_header_text: str,
                          new_section_md: str) -> str:
    """Insert `new_section_md` immediately before the section with `anchor_header_text`.

    If the anchor section is not found, append at the end of the document
    (but before any trailing standalone '---' + footnote block).
    """
    anchor = re.search(rf"^## {re.escape(anchor_header_text)}\s*$", content, re.M)
    block = "\n" + new_section_md.strip("\n") + "\n\n"
    if anchor:
        return content[:anchor.start()] + block + content[anchor.start():]
    # fall back: insert before the first footnote definition or before a standalone --- + footnote
    fn = re.search(r"^\[\^[^\]]+\]: ", content, re.M)
    if fn:
        # walk back to skip any leading '---' separator
        cut = fn.start()
        pre = content[:cut].rstrip()
        if pre.endswith("---"):
            cut = pre.rfind("---")
            pre = content[:cut].rstrip()
        return pre + "\n\n" + new_section_md.strip("\n") + "\n\n" + content[cut:]
    return content.rstrip() + "\n\n" + new_section_md.strip("\n") + "\n"


PLACEHOLDER_RE = re.compile(r"^_Additional .*?_$", re.M)


def split_frontmatter(content: str) -> tuple[dict, str]:
    """Naive YAML frontmatter parser — handles flat scalars and list items only."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    fm_raw = content[3:end].strip("\n")
    body = content[end + 4:].lstrip("\n")
    fm: dict = {}
    current_key = None
    for line in fm_raw.splitlines():
        if not line.strip():
            continue
        stripped = line.lstrip()
        if stripped.startswith("- ") and current_key is not None:
            fm.setdefault(current_key, [])
            if isinstance(fm[current_key], list):
                value = stripped[2:].strip().strip('"').strip("'")
                fm[current_key].append(value)
            continue
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            current_key = key
            if value == "":
                fm[key] = []
            elif value.startswith("[") and value.endswith("]"):
                # YAML flow-style list: [a, b, "c, d"]
                inner = value[1:-1]
                items = []
                # split on commas not inside quotes
                cur = []
                in_q: str | None = None
                for ch in inner:
                    if in_q:
                        if ch == in_q:
                            in_q = None
                        else:
                            cur.append(ch)
                    elif ch in ("'", '"'):
                        in_q = ch
                    elif ch == ",":
                        items.append("".join(cur).strip())
                        cur = []
                    else:
                        cur.append(ch)
                if cur:
                    items.append("".join(cur).strip())
                fm[key] = [it.strip('"').strip("'") for it in items if it]
            else:
                fm[key] = value.strip('"').strip("'")
    return fm, body


def load_vault_pages(vault: Path) -> dict:
    """Walk the vault and collect frontmatter from every .md page."""
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
            fm, _ = split_frontmatter(read_text(md))
            title = fm.get("title") or md.stem
            pages[bucket][title] = {
                "path": str(md.relative_to(vault)),
                "frontmatter": fm,
            }
    # also scan root-level pages that aren't index/log/schema
    for md in vault.glob("*.md"):
        if md.name in (INDEX_FILE, LOG_FILE, SCHEMA_FILE):
            continue
        fm, _ = split_frontmatter(read_text(md))
        pages["other"].append({
            "path": str(md.relative_to(vault)),
            "title": fm.get("title") or md.stem,
        })
    return pages


def ensure_schema(vault: Path) -> None:
    if not (vault / SCHEMA_FILE).exists():
        die(f"{SCHEMA_FILE} not found in {vault}. Run `wiki_ops.py init {vault}` first.", code=2)


def load_asset(name: str) -> str:
    path = ASSETS_DIR / name
    if not path.exists():
        die(f"missing bundled asset: {path}")
    return path.read_text(encoding="utf-8")


# ---------- scan ----------

def cmd_scan(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        die(f"vault not a directory: {vault}")

    pages = load_vault_pages(vault)
    state = {
        "vault": str(vault),
        "schema_present": (vault / SCHEMA_FILE).exists(),
        "index_present": (vault / INDEX_FILE).exists(),
        "log_present": (vault / LOG_FILE).exists(),
        "subdirs_present": {sd: (vault / sd).is_dir() for sd in DEFAULT_SUBDIRS},
        "concepts": sorted(pages["concepts"].keys()),
        "entities": sorted(pages["entities"].keys()),
        "sources": sorted(pages["sources"].keys()),
        "counts": {
            "concepts": len(pages["concepts"]),
            "entities": len(pages["entities"]),
            "sources": len(pages["sources"]),
        },
        "last_log_entries": tail_log(vault, 5),
    }
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


def tail_log(vault: Path, n: int) -> list[str]:
    log = vault / LOG_FILE
    if not log.exists():
        return []
    entries = re.findall(r"^## \[.+$", log.read_text(encoding="utf-8"), flags=re.M)
    return entries[-n:]


# ---------- init ----------

def cmd_init(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    vault.mkdir(parents=True, exist_ok=True)
    created = []
    skipped = []

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


# ---------- upsert-page ----------

CONCEPT_KIND, ENTITY_KIND = "concept", "entity"
KIND_TO_SUBDIR = {CONCEPT_KIND: "_concepts", ENTITY_KIND: "_entities"}


def page_path(vault: Path, kind: str, name: str) -> Path:
    subdir = KIND_TO_SUBDIR[kind]
    return vault / subdir / f"{name}.md"


def render_stub_page(kind: str, name: str, definition: str | None,
                     source_slug: str, source_title: str, source_date: str) -> str:
    tpl_name = "concept_page.template.md" if kind == CONCEPT_KIND else "entity_page.template.md"
    tpl = load_asset(tpl_name)
    today = datetime.today().strftime("%Y-%m-%d")
    def_section = ""
    if definition:
        def_section = f"{definition.strip()} [^src-{source_slug}]"
    else:
        def_section = "_Definition pending — first ingest did not extract a one-sentence summary._"

    # Single-pass placeholder substitution: previous chained .replace() calls
    # would substitute into a prior value's text if it contained '{{KIND}}'
    # etc. _safe_name now blocks that for names, but use a regex-based
    # single-pass lookup for defense-in-depth.
    subs = {
        "NAME": name,
        "KIND": kind,
        "CREATED_DATE": today,
        "DEFINITION": def_section,
        "FIRST_SOURCE_ROW": f"- [[{source_slug}]] — {source_date} — {source_title}",
        "FIRST_FOOTNOTE": f"[^src-{source_slug}]: [[{source_slug}]] — {source_title}",
    }
    return re.sub(r"\{\{([A-Z_]+)\}\}",
                  lambda m: subs.get(m.group(1), m.group(0)), tpl)


def _existing_lines(body: str) -> list[str]:
    """Return existing non-placeholder, non-blank list items in a section body."""
    out = []
    for line in body.splitlines():
        s = line.strip()
        if not s or PLACEHOLDER_RE.match(s):
            continue
        out.append(s)
    return out


def upsert_source_row(content: str, source_slug: str, source_title: str,
                      source_date: str) -> str:
    row = f"- [[{source_slug}]] — {source_date} — {source_title}"
    body = get_section_body(content, "Sources mentioning this")
    if body is None:
        # create the section before Footnotes (or end)
        new_section = f"## Sources mentioning this\n\n{row}\n"
        return insert_section_before(content, "Footnotes", new_section)
    rows = _existing_lines(body)
    # dedupe by slug
    if any(f"[[{source_slug}]]" in r for r in rows):
        return content
    rows.append(row)
    new_body = "\n".join(rows)
    return replace_section_body(content, "Sources mentioning this", new_body)


def append_fact(content: str, fact: str, source_slug: str) -> str:
    line = f"- {fact.strip()} [^src-{source_slug}]"
    body = get_section_body(content, "Facts")
    if body is None:
        new_section = f"## Facts\n\n{line}\n"
        # insert before Contradictions (preferred) or Sources mentioning this or Footnotes
        for anchor in ("Contradictions", "Sources mentioning this", "Footnotes"):
            if get_section_body(content, anchor) is not None:
                return insert_section_before(content, anchor, new_section)
        return content.rstrip() + "\n\n" + new_section
    rows = _existing_lines(body)
    rows.append(line)
    return replace_section_body(content, "Facts", "\n".join(rows))


def append_contradiction(content: str, existing_claim: str, new_fact: str,
                         source_slug: str) -> str:
    block = (
        "> ⚠️ **Contradiction flagged** — operator review needed.\n"
        f"> - Existing claim: {existing_claim.strip()}\n"
        f"> - New claim from [[{source_slug}]]: {new_fact.strip()} [^src-{source_slug}]\n"
    )
    body = get_section_body(content, "Contradictions")
    if body is None:
        new_section = f"## Contradictions\n\n{block}"
        for anchor in ("Sources mentioning this", "Footnotes"):
            if get_section_body(content, anchor) is not None:
                return insert_section_before(content, anchor, new_section)
        return content.rstrip() + "\n\n" + new_section
    existing = body.strip("\n")
    return replace_section_body(content, "Contradictions", existing + "\n\n" + block)


def upsert_footnote(content: str, source_slug: str, source_title: str) -> str:
    fn_line = f"[^src-{source_slug}]: [[{source_slug}]] — {source_title}"
    # dedupe by full line OR by key
    if fn_line in content:
        return content
    if re.search(rf"^\[\^src-{re.escape(source_slug)}\]: ", content, re.M):
        return content
    body = get_section_body(content, "Footnotes")
    if body is None:
        # append a Footnotes section at the very end
        return content.rstrip() + "\n\n## Footnotes\n\n" + fn_line + "\n"
    rows = _existing_lines(body)
    rows.append(fn_line)
    return replace_section_body(content, "Footnotes", "\n".join(rows))


def cmd_upsert_page(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_schema(vault)
    if args.kind not in (CONCEPT_KIND, ENTITY_KIND):
        die(f"--kind must be 'concept' or 'entity', got {args.kind!r}")

    safe_name = _safe_name(args.name, kind="name")
    # also sanitize source_slug since it's embedded into paths/links
    safe_slug = _safe_name(args.source_slug, kind="source-slug")

    target_dir = vault / KIND_TO_SUBDIR[args.kind]
    collision = _check_case_collision(target_dir, safe_name)
    if collision:
        die(f"case-collision: '{safe_name}.md' would collide with existing "
            f"'{collision}' on a case-insensitive filesystem; rename one or "
            f"pass --force to override", code=4)

    target = target_dir / f"{safe_name}.md"
    # final containment check after resolving symlinks etc.
    if not str(target.resolve()).startswith(str(target_dir.resolve()) + os.sep):
        die(f"refusing to write outside {target_dir}: {target}")

    created = not target.exists()

    # verify --contradicts text actually appears on the page (unless creating)
    contradiction_warning = None
    if args.contradicts and not created:
        page_text = read_text(target)
        if args.contradicts.strip() not in page_text:
            if not args.force:
                die(f"--contradicts text {args.contradicts!r} not found on "
                    f"{target.relative_to(vault)}; pass --force to record anyway",
                    code=5)
            contradiction_warning = "contradicted text not found on page; recorded anyway via --force"

    if created:
        content = render_stub_page(
            kind=args.kind, name=safe_name, definition=args.definition,
            source_slug=safe_slug, source_title=args.source_title,
            source_date=args.source_date,
        )
    else:
        content = read_text(target)
        content = upsert_source_row(
            content, safe_slug, args.source_title, args.source_date
        )
        content = upsert_footnote(content, safe_slug, args.source_title)

    if args.fact:
        content = append_fact(content, args.fact, safe_slug)

    if args.contradicts:
        if not args.fact:
            die("--contradicts requires --fact (the new claim that disagrees)")
        content = append_contradiction(content, args.contradicts, args.fact, safe_slug)

    write_text(target, content, args.dry_run)
    result = {
        "page": str(target.relative_to(vault)),
        "created": created,
        "added_fact": bool(args.fact),
        "contradiction_flagged": bool(args.contradicts),
    }
    if contradiction_warning:
        result["warning"] = contradiction_warning
    print(json.dumps(result, indent=2))
    return 0


# ---------- update-index ----------

INDEX_SECTIONS = {
    "sources": "Sources",
    "concepts": "Concepts",
    "entities": "Entities",
}


def add_index_row(content: str, section_header_text: str, row: str, slug_key: str) -> str:
    """Add row under '## <section_header_text>' if not already present (deduped by slug_key)."""
    body = get_section_body(content, section_header_text)
    if body is None:
        # append section at end of file
        return content.rstrip() + f"\n\n## {section_header_text}\n\n{row}\n"
    if slug_key in body:
        return content  # already present
    rows = _existing_lines(body)
    rows.append(row)
    return replace_section_body(content, section_header_text, "\n".join(rows))


def _collect_names(comma_arg: str | None, repeated_arg: list[str] | None) -> list[str]:
    """Combine `--new-X "a,b,c"` and repeated `--new-X-name "a"` into one list.

    Repeated args are safe for names containing commas; the comma-arg is kept
    for back-compat but should be used only when names are guaranteed
    comma-free. Repeated args win on overlap.
    """
    out: list[str] = []
    seen: set[str] = set()
    for n in (repeated_arg or []):
        n = n.strip()
        if n and n not in seen:
            out.append(n); seen.add(n)
    if comma_arg:
        for n in comma_arg.split(","):
            n = n.strip()
            if n and n not in seen:
                out.append(n); seen.add(n)
    return out


def cmd_update_index(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_schema(vault)
    index = vault / INDEX_FILE
    content = read_text(index) or load_asset("index.template.md")

    source_row = (f"- [[{args.source_slug}]] — {args.source_date} — "
                  f"{args.source_title} — {args.summary}")
    content = add_index_row(content, INDEX_SECTIONS["sources"], source_row,
                            slug_key=f"[[{args.source_slug}]]")

    concept_names = _collect_names(args.new_concepts, args.new_concept)
    entity_names = _collect_names(args.new_entities, args.new_entity)

    for name in concept_names:
        row = f"- [[{name}]] — introduced by [[{args.source_slug}]]"
        content = add_index_row(content, INDEX_SECTIONS["concepts"], row,
                                slug_key=f"[[{name}]]")

    for name in entity_names:
        row = f"- [[{name}]] — introduced by [[{args.source_slug}]]"
        content = add_index_row(content, INDEX_SECTIONS["entities"], row,
                                slug_key=f"[[{name}]]")

    write_text(index, content, args.dry_run)
    print(json.dumps({"index": str(index.relative_to(vault)), "updated": True}, indent=2))
    return 0


# ---------- append-log ----------

def cmd_append_log(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_schema(vault)
    log = vault / LOG_FILE
    content = read_text(log) or load_asset("log.template.md")

    date = args.date or datetime.today().strftime("%Y-%m-%d")
    heading = f"## [{date}] ingest | {args.title}"
    summary_line = f"- Summary page: [[{args.slug}]]"

    # Idempotency: if an entry with the same date+ingest+title heading AND the
    # same summary-page line already exists, skip (unless --force-log).
    if not args.force_log:
        # search for both heading and matching summary-page line in proximity
        m = re.search(rf"^{re.escape(heading)}\s*$\n(?:- .*\n)*?{re.escape(summary_line)}",
                      content, re.M)
        if m:
            print(json.dumps({
                "log": str(log.relative_to(vault)),
                "appended": False,
                "skipped_reason": "duplicate (same heading + summary-page line already present); pass --force-log to append anyway",
                "date": date,
            }, indent=2))
            return 0

    entry = [
        f"\n{heading}",
        f"- Source path: `{args.source_path}`",
        summary_line,
    ]
    if args.touched:
        entry.append("- Pages touched: " + ", ".join(f"[[{x.strip()}]]" for x in args.touched.split(",") if x.strip()))
    if args.created:
        entry.append("- Pages created: " + ", ".join(f"[[{x.strip()}]]" for x in args.created.split(",") if x.strip()))
    entry.append(f"- Contradictions flagged: {args.contradictions}")
    entry.append("")

    new_content = content.rstrip() + "\n" + "\n".join(entry) + "\n"
    write_text(log, new_content, args.dry_run)
    print(json.dumps({"log": str(log.relative_to(vault)), "appended": True, "date": date}, indent=2))
    return 0


# ---------- register-summary (ingest a pre-made summary) ----------

SUMMARY_KIND_HINTS = ("lesson-summary", "meeting-summary", "source", "summary")


def cmd_register_summary(args: argparse.Namespace) -> int:
    """Copy a pre-made summary file into _sources/ and return its metadata.

    Use this when the operator already has a summary (e.g. from a prior run
    of `summarizing-meetings`) and wants to ingest it into the wiki without
    regenerating. After this, the agent does Phase 3+ as usual.
    """
    vault = Path(args.vault).resolve()
    ensure_schema(vault)
    summary_path = Path(args.summary_path).resolve()
    if not summary_path.is_file():
        die(f"summary file not found: {summary_path}")

    text = summary_path.read_text(encoding="utf-8")
    fm, _ = split_frontmatter(text)

    # Auto-normalize concept/entity names that contain '/' or '\\' — these are
    # rejected by _safe_name in upsert-page, so summaries written by an LLM
    # that happily emit 'Railway 24/7 Deployment' would otherwise be unusable.
    # We replace '/' and '\\' with '-' in the in-memory text (which is then
    # written to _sources/) and surface a single warning listing the rewrites.
    name_rewrites: dict[str, str] = {}

    def _normalize_for_fs(name: str) -> str:
        s = name.replace("/", "-").replace("\\", "-").replace("~", "")
        s = re.sub(r"\s*-\s*", "-", s)
        s = re.sub(r"-+", "-", s).strip("- ")
        while s.startswith("."):
            s = s[1:]
        return s

    for field in ("concepts", "related"):
        for entry in (fm.get(field) or []):
            # for related[] entries, strip [[...]] before checking
            m = re.match(r"^\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]$", entry.strip())
            bare = m.group(1).strip() if m else entry.strip()
            if "/" in bare or "\\" in bare:
                norm = _normalize_for_fs(bare)
                if norm and norm != bare:
                    name_rewrites[bare] = norm

    warnings = []
    if name_rewrites:
        # apply the rewrites to the in-memory text BEFORE writing to _sources/
        for old, new in name_rewrites.items():
            text = text.replace(old, new)
        # re-parse fm so downstream code sees the normalized values
        fm, _ = split_frontmatter(text)
        warnings.append(
            "auto-normalized concept/entity names containing '/' or '\\' "
            "(filesystem-unsafe): " + ", ".join(f"{o!r} → {n!r}"
                                                for o, n in name_rewrites.items())
        )

    fm_title = fm.get("title")
    if args.title:
        title = args.title
    elif fm_title and fm_title != "⚠️ UNKNOWN":
        title = fm_title
    else:
        title = summary_path.stem
        warnings.append(
            f"summary has no `title:` frontmatter (or it's ⚠️ UNKNOWN); "
            f"falling back to filename stem {title!r}. Pass --title to override."
        )
    if not title:
        die("summary has no usable title; pass --title")
    fm_type = (fm.get("type") or fm.get("kind") or "").lower()
    if fm_type and fm_type not in SUMMARY_KIND_HINTS:
        warnings.append(
            f"frontmatter type/kind={fm_type!r} not in known summary hints "
            f"{SUMMARY_KIND_HINTS}; proceeding anyway"
        )
    if not fm.get("concepts") and not fm.get("related"):
        warnings.append(
            "summary frontmatter has no `concepts:` and no `related:` — "
            "Phase 3 will have nothing to upsert. Operator should review."
        )

    raw_slug = args.slug or slugify(title)
    if not raw_slug:
        die("could not derive slug from title; pass --slug")
    slug = _safe_name(raw_slug, kind="slug")
    sources_dir = vault / "_sources"
    target = sources_dir / f"{slug}.md"
    # containment check after Path.resolve()
    if not str(target.resolve()).startswith(str(sources_dir.resolve()) + os.sep):
        die(f"refusing to write outside {sources_dir}: {target}")

    # Skip copy if already inside _sources/ at the target path
    already_in_place = (summary_path == target)
    target_exists = target.exists()

    action = "skipped"
    if already_in_place:
        action = "in-place (already at target)"
    elif target_exists and not args.force:
        die(f"_sources/{slug}.md already exists; pass --force to overwrite "
            f"(or use a different --slug)", code=3)
    else:
        if not args.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        action = "overwritten" if target_exists else "copied"

    # extract upsert hints
    concepts = list(fm.get("concepts") or [])
    related_raw = list(fm.get("related") or [])
    # strip [[...]] from related entries to get bare names
    related = []
    for r in related_raw:
        m = re.match(r"^\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]$", r.strip())
        related.append(m.group(1).strip() if m else r.strip())

    result = {
        "summary_source": str(summary_path),
        "target_page": str(target.relative_to(vault)),
        "action": action,
        "slug": slug,
        "title": title,
        "date": fm.get("date") or "",
        "concepts": concepts,
        "related": related,
        "warnings": warnings,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


# ---------- log-event (generalized log) ----------

_LOG_FORBIDDEN_IN_DETAIL = re.compile(r"[\n\r]|^## \[")


def cmd_log_event(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_schema(vault)
    log = vault / LOG_FILE
    content = read_text(log) or load_asset("log.template.md")

    safe_event = args.event.strip()
    if "\n" in safe_event or "|" in safe_event or "[" in safe_event:
        die(f"--event {safe_event!r}: must not contain newline, pipe, or '['")
    safe_title = args.title.strip()
    if "\n" in safe_title:
        die("--title must not contain newlines")

    date = args.date or datetime.today().strftime("%Y-%m-%d")
    header = f"\n## [{date}] {safe_event} | {safe_title}"
    lines = [header]
    for kv in (args.detail or []):
        if "=" not in kv:
            die(f"--detail expects key=value, got {kv!r}")
        k, v = kv.split("=", 1)
        k = k.strip()
        v = v.strip()
        # reject control chars and a leading '## [' that could spoof a log header
        if _LOG_FORBIDDEN_IN_DETAIL.search(k) or _LOG_FORBIDDEN_IN_DETAIL.search(v):
            die(f"--detail {kv!r}: newlines and log-header prefixes are not allowed "
                f"(would break grep-friendly log format)")
        if "\n" in k or "\n" in v:
            die(f"--detail {kv!r}: newlines are not allowed")
        lines.append(f"- {k}: {v}")
    lines.append("")

    new_content = content.rstrip() + "\n" + "\n".join(lines) + "\n"
    write_text(log, new_content, args.dry_run)
    print(json.dumps({"log": str(log.relative_to(vault)), "appended": True,
                      "date": date, "event": safe_event}, indent=2))
    return 0


# ---------- find (keyword search) ----------

WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]|#]+?)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
WORD_RE = re.compile(r"[A-Za-z][\w-]*")


def _walk_pages(vault: Path):
    for sub in DEFAULT_SUBDIRS:
        d = vault / sub
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            yield md
    for md in sorted(vault.glob("*.md")):
        if md.name in (INDEX_FILE, LOG_FILE, SCHEMA_FILE):
            continue
        yield md


def cmd_find(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        die(f"vault not a directory: {vault}")

    terms = [t.strip().lower() for t in args.terms.split() if t.strip()]
    if not terms:
        die("--terms is empty")

    kind_filter = set((args.kinds or "").split(",")) if args.kinds else None
    if kind_filter:
        kind_filter = {k.strip().lower() for k in kind_filter if k.strip()}

    hits = []
    for md in _walk_pages(vault):
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        fm, body = split_frontmatter(text)
        if kind_filter:
            page_kind = (fm.get("kind") or "").lower()
            if not page_kind:
                page_kind = SUBDIR_TO_KIND.get(md.parent.name, "")
            if page_kind not in kind_filter:
                continue
        haystack = (text or "").lower()
        score = 0
        per_term = {}
        for t in terms:
            c = haystack.count(t)
            per_term[t] = c
            score += c
        if score == 0:
            continue
        title = fm.get("title") or fm.get("name") or md.stem
        hits.append({
            "path": str(md.relative_to(vault)),
            "title": title,
            "kind": fm.get("kind") or SUBDIR_TO_KIND.get(md.parent.name, "unknown"),
            "score": score,
            "term_counts": per_term,
        })

    hits.sort(key=lambda h: (-h["score"], h["path"]))
    top = hits[:args.limit]
    print(json.dumps({"query_terms": terms, "hits": top, "total_matches": len(hits)},
                     indent=2, ensure_ascii=False))
    return 0


# ---------- lint (health check) ----------

def _extract_wikilinks(body: str) -> set[str]:
    return {m.group(1).strip() for m in WIKILINK_RE.finditer(body)}


def _page_exists_anywhere(vault: Path, name: str) -> str | None:
    """Return relative path if a page with this name exists in any standard location."""
    for sub in DEFAULT_SUBDIRS + (".",):
        candidate = vault / sub / f"{name}.md"
        if candidate.exists():
            return str(candidate.relative_to(vault))
    return None


def cmd_lint(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        die(f"vault not a directory: {vault}")

    pages: dict[str, dict] = {}   # name → {path, body, fm}
    inbound: dict[str, set[str]] = {}
    contradictions: list[dict] = []
    concept_freq: dict[str, list[str]] = {}  # concept_name → [source_slugs]

    for md in _walk_pages(vault):
        text = md.read_text(encoding="utf-8")
        fm, body = split_frontmatter(text)
        name = md.stem
        pages[name] = {
            "path": str(md.relative_to(vault)),
            "raw": text,
            "fm": fm,
            "kind": fm.get("kind") or SUBDIR_TO_KIND.get(md.parent.name, "unknown"),
        }
        # contradictions detection
        contra_body = get_section_body(text, "Contradictions")
        if contra_body and contra_body.strip():
            count = contra_body.count("⚠️")
            contradictions.append({
                "page": str(md.relative_to(vault)),
                "count": count or 1,
            })
        # collect concept mentions from source-page frontmatter
        if SUBDIR_TO_KIND.get(md.parent.name) == "source":
            for c in (fm.get("concepts") or []):
                concept_freq.setdefault(c, []).append(name)

    # inbound link counts — scan FULL text (body + frontmatter wiki-links)
    # AND treat frontmatter `concepts:` / `related:` entries as implicit
    # inbound links, since they declare "this source is about X" even when
    # the body doesn't bracket the name as [[X]].
    for name, info in pages.items():
        targets = _extract_wikilinks(info["raw"])
        # frontmatter implicit inbounds
        fm = info["fm"]
        for entry in (fm.get("concepts") or []):
            targets.add(entry.strip())
        for entry in (fm.get("related") or []):
            m = re.match(r"^\[\[([^\]|#]+?)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]$",
                         entry.strip())
            targets.add((m.group(1) if m else entry).strip())
        for t in targets:
            if not t or t == name:
                continue  # self-reference doesn't count as inbound
            inbound.setdefault(t, set()).add(name)

    # orphans: pages with no inbound link (excluding source pages, which are root-of-truth)
    orphans = []
    for name, info in pages.items():
        if info["kind"] == "source":
            continue  # source pages don't need inbound links
        if not inbound.get(name):
            orphans.append({"page": info["path"], "kind": info["kind"]})

    # dangling: link targets that have no corresponding page
    dangling: dict[str, set[str]] = {}  # target → set of source pages
    for name, info in pages.items():
        for target in _extract_wikilinks(info["raw"]):
            if target in pages:
                continue
            if _page_exists_anywhere(vault, target):
                continue
            dangling.setdefault(target, set()).add(info["path"])

    # missing concept pages: concepts mentioned in ≥threshold sources without a page
    threshold = args.threshold
    missing_concept_pages = []
    for concept, sources in concept_freq.items():
        if concept in pages:
            continue
        if _page_exists_anywhere(vault, concept):
            continue
        if len(sources) >= threshold:
            missing_concept_pages.append({
                "name": concept,
                "mentioned_in": sources,
                "count": len(sources),
            })

    report = {
        "vault": str(vault),
        "totals": {
            "pages": len(pages),
            "orphans": len(orphans),
            "dangling_link_targets": len(dangling),
            "pages_with_open_contradictions": len(contradictions),
            "missing_concept_pages": len(missing_concept_pages),
        },
        "orphans": sorted(orphans, key=lambda x: x["page"]),
        "dangling_links": [
            {"target": t, "referenced_by": sorted(s)} for t, s in sorted(dangling.items())
        ],
        "open_contradictions": sorted(contradictions, key=lambda x: x["page"]),
        "missing_concept_pages": sorted(missing_concept_pages, key=lambda x: -x["count"]),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


# ---------- reindex (rebuild index.md from disk) ----------

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_TLDR_BOLD_RE = re.compile(r"\*\*TL;DR\*\*:?\s*", re.I)


def _first_sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    # strip leading blockquote markers, bold-TL;DR labels, and inline comments
    text = _HTML_COMMENT_RE.sub("", text).strip()
    while text.startswith(">"):
        text = text.lstrip("> ").strip()
    text = _TLDR_BOLD_RE.sub("", text).strip()
    # skip any leading markdown header lines (## Executive Summary etc.)
    while text.startswith("#"):
        nl = text.find("\n")
        if nl == -1:
            return ""
        text = text[nl + 1:].lstrip("> ").strip()
        text = _HTML_COMMENT_RE.sub("", text).strip()
        text = _TLDR_BOLD_RE.sub("", text).strip()
    # take everything until first period/newline-block
    m = re.search(r"[.!?](\s|$)|\n\n", text)
    if not m:
        return text[:200].rstrip().replace("\n", " ")
    return text[:m.start() + 1].rstrip().replace("\n", " ")


def _page_one_line(text: str, fm: dict, kind: str) -> str:
    # Sources: prefer summary frontmatter, else first sentence of TL;DR / Executive Summary / first paragraph
    if kind == "source":
        for key in ("summary", "tldr", "description"):
            v = fm.get(key)
            if v:
                return str(v).strip().replace("\n", " ")
        body = split_frontmatter(text)[1]
        # try TL;DR section, then Executive Summary (common summarizing-meetings output)
        for section in ("TL;DR", "Executive Summary"):
            body_text = get_section_body(text, section)
            if body_text and body_text.strip():
                cleaned = _first_sentence(body_text)
                if cleaned:
                    return cleaned
        # fall back to first non-empty paragraph that isn't a header/comment/separator
        for para in body.split("\n\n"):
            para = _HTML_COMMENT_RE.sub("", para).strip()
            if not para or para.startswith("#") or para.startswith("---"):
                continue
            cleaned = _first_sentence(para)
            if cleaned:
                return cleaned
        return ""
    # concept/entity pages: first sentence of Definition section
    defn = get_section_body(text, "Definition")
    if defn:
        return _first_sentence(defn.strip())
    return ""


def cmd_reindex(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_schema(vault)

    # Bucket pages by the on-disk subdir (with underscore prefix), then map
    # to user-facing display section labels when rendering the index.
    rows_by_subdir: dict[str, list[str]] = {sd: [] for sd in DEFAULT_SUBDIRS}
    for md in _walk_pages(vault):
        text = md.read_text(encoding="utf-8")
        fm, _ = split_frontmatter(text)
        subdir = md.parent.name
        if subdir not in rows_by_subdir:
            continue
        kind = fm.get("kind") or SUBDIR_TO_KIND.get(subdir, "unknown")
        title = fm.get("title") or fm.get("name") or md.stem
        date = fm.get("date") or fm.get("created") or ""
        one_line = _page_one_line(text, fm, kind)
        slug = md.stem
        if kind == "source":
            row = f"- [[{slug}]]"
            if date:
                row += f" — {date}"
            row += f" — {title}"
            if one_line:
                row += f" — {one_line}"
        else:
            row = f"- [[{slug}]]"
            if one_line:
                row += f" — {one_line}"
        rows_by_subdir[subdir].append(row)

    # Build new index from template; each on-disk subdir maps to a display
    # section label ("_sources" → "Sources", etc.) in index.md.
    display_section_names = set(SUBDIR_TO_DISPLAY.values())
    new_content = load_asset("index.template.md")
    for subdir, rows in rows_by_subdir.items():
        display = SUBDIR_TO_DISPLAY[subdir]
        body = "\n".join(rows) if rows else ""
        new_content = replace_section_body(new_content, display, body)

    # Preserve ALL custom sections from the existing index — anything outside
    # the default display sections (Sources/Concepts/Entities) the operator
    # added gets carried through. Duplicate header names get their bodies
    # MERGED (separated by a markdown HR) into one section, and a warning is
    # emitted so the operator can rename one of them if that wasn't intended.
    existing = read_text(vault / INDEX_FILE)
    preserved_sections: list[str] = []
    merge_warnings: list[str] = []
    if existing:
        # Walk header occurrences in document order; track which non-default
        # names we've already handled so each unique name is processed once
        # and ALL its occurrences are collected.
        handled: set[str] = set()
        for m in re.finditer(r"^## (.+?)[ \t]*$",
                             _mask_code_fences(existing), re.M):
            header_text = m.group(1).strip()
            if header_text in display_section_names:
                continue
            if header_text in handled:
                continue
            handled.add(header_text)

            bodies = [b.strip("\n") for b in get_all_section_bodies(existing, header_text)]
            bodies = [b for b in bodies if b]  # drop empty
            if not bodies:
                continue
            if len(bodies) == 1:
                merged_body = bodies[0]
            else:
                # Merge duplicates with a horizontal-rule separator
                merged_body = "\n\n---\n\n".join(bodies)
                merge_warnings.append(
                    f"merged {len(bodies)} duplicate `## {header_text}` "
                    f"sections from existing index — consider renaming one "
                    f"if the duplication was unintended"
                )

            # Insert (or replace) in new_content
            if get_section_body(new_content, header_text) is not None:
                new_content = replace_section_body(new_content, header_text, merged_body)
            else:
                new_content = (new_content.rstrip()
                               + f"\n\n## {header_text}\n\n{merged_body}\n")
            preserved_sections.append(header_text)

    write_text(vault / INDEX_FILE, new_content, args.dry_run)
    result = {
        "index": INDEX_FILE,
        "rebuilt": True,
        "counts": {SUBDIR_TO_DISPLAY[k]: len(v) for k, v in rows_by_subdir.items()},
        "preserved_sections": preserved_sections,
    }
    if merge_warnings:
        result["warnings"] = merge_warnings
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


# ---------- argparse ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki_ops", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="dump vault state as JSON")
    s.add_argument("vault")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("init", help="scaffold a fresh vault (idempotent)")
    s.add_argument("vault")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("upsert-page", help="create or additively update a concept/entity page")
    s.add_argument("vault")
    s.add_argument("--kind", required=True, choices=[CONCEPT_KIND, ENTITY_KIND])
    s.add_argument("--name", required=True)
    s.add_argument("--source-slug", required=True)
    s.add_argument("--source-title", required=True)
    s.add_argument("--source-date", required=True)
    s.add_argument("--definition", help="one-sentence definition (for stub creation)")
    s.add_argument("--fact", help="new fact to append under ## Facts")
    s.add_argument("--contradicts", help="existing claim that disagrees with --fact")
    s.add_argument("--force", action="store_true",
                   help="bypass safety checks: case-collision, --contradicts-not-found")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_upsert_page)

    s = sub.add_parser("update-index", help="add/update rows in index.md")
    s.add_argument("vault")
    s.add_argument("--source-slug", required=True)
    s.add_argument("--source-title", required=True)
    s.add_argument("--source-date", required=True)
    s.add_argument("--summary", required=True)
    s.add_argument("--new-concepts",
                   help="comma-separated names (DEPRECATED for names containing commas — use --new-concept instead)")
    s.add_argument("--new-entities",
                   help="comma-separated names (DEPRECATED for names containing commas — use --new-entity instead)")
    s.add_argument("--new-concept", action="append", default=[],
                   help="one concept name; repeat the flag for each name (safe for names containing commas)")
    s.add_argument("--new-entity", action="append", default=[],
                   help="one entity name; repeat the flag for each name (safe for names containing commas)")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_update_index)

    s = sub.add_parser("append-log", help="append an ingest entry to log.md (shortcut for log-event ingest)")
    s.add_argument("vault")
    s.add_argument("--title", required=True)
    s.add_argument("--slug", required=True)
    s.add_argument("--source-path", required=True)
    s.add_argument("--touched", help="comma-separated slugs")
    s.add_argument("--created", help="comma-separated slugs")
    s.add_argument("--contradictions", type=int, default=0)
    s.add_argument("--date", help="YYYY-MM-DD (default: today)")
    s.add_argument("--force-log", action="store_true",
                   help="append even if an identical entry (heading + summary-page) is already present")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_append_log)

    s = sub.add_parser("register-summary",
                       help="ingest an already-generated summary file into _sources/ (skip summarizing-meetings)")
    s.add_argument("vault")
    s.add_argument("--summary-path", required=True,
                   help="path to the pre-made summary markdown file")
    s.add_argument("--slug", help="override slug (default: slugify of title)")
    s.add_argument("--title", help="override title (default: from frontmatter)")
    s.add_argument("--force", action="store_true",
                   help="overwrite _sources/<slug>.md if it already exists")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_register_summary)

    s = sub.add_parser("log-event", help="append a generic event entry to log.md (query, lint, etc.)")
    s.add_argument("vault")
    s.add_argument("--event", required=True,
                   help="event type label, e.g. 'query', 'lint', 'reindex'")
    s.add_argument("--title", required=True,
                   help="short title shown after the event label in the heading")
    s.add_argument("--detail", action="append",
                   help="key=value detail line; pass multiple times for multiple lines")
    s.add_argument("--date", help="YYYY-MM-DD (default: today)")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_log_event)

    s = sub.add_parser("find", help="keyword search across vault pages (returns ranked JSON)")
    s.add_argument("vault")
    s.add_argument("--terms", required=True,
                   help="space-separated search terms; case-insensitive substring match")
    s.add_argument("--limit", type=int, default=10,
                   help="max hits to return (default: 10)")
    s.add_argument("--kinds", help="comma-separated kinds filter: source,concept,entity")
    s.set_defaults(func=cmd_find)

    s = sub.add_parser("lint", help="health check: orphans, dangling links, contradictions, missing pages")
    s.add_argument("vault")
    s.add_argument("--threshold", type=int, default=2,
                   help="min sources mentioning a concept to flag missing-page (default: 2)")
    s.set_defaults(func=cmd_lint)

    s = sub.add_parser("reindex", help="rebuild index.md from disk (preserves Notes section)")
    s.add_argument("vault")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_reindex)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

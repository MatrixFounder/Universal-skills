"""`upsert-page` subcommand — create or additively update a concept/entity page.

Mid-complexity command: builds (or extends) one markdown page per call.
Local helpers (`render_stub_page`, `upsert_source_row`, `append_fact`,
`append_contradiction`, `upsert_footnote`, `page_path`) are intentionally
kept inside this module — they have no other caller and don't belong in
F2/F3-helper. The contract is additive: an existing page's definition,
footnotes, and source rows are preserved across re-ingest.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from wiki_ingest._markdown import (
    _existing_lines,
    get_section_body,
    insert_section_before,
    replace_section_body,
)
from wiki_ingest._safety import (
    _check_case_collision,
    _is_relative_to,
    _safe_inline,
    _safe_name,
    die,
    read_text,
    write_text,
)
from wiki_ingest._vault import ensure_schema, load_asset

CONCEPT_KIND, ENTITY_KIND = "concept", "entity"
KIND_TO_SUBDIR = {CONCEPT_KIND: "_concepts", ENTITY_KIND: "_entities"}


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
    # idempotent: don't duplicate the exact same fact+source pairing
    if line in rows:
        return content
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
    # idempotent: skip if the same (existing_claim, new_fact, source_slug) tuple
    # is already present. Check by looking for the unique "New claim from" line.
    new_claim_line = (f"> - New claim from [[{source_slug}]]: "
                      f"{new_fact.strip()} [^src-{source_slug}]")
    if new_claim_line in body:
        return content
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


def register(sub: argparse._SubParsersAction) -> None:
    """Attach the `upsert-page` subparser."""
    p = sub.add_parser("upsert-page",
                       help="create or additively update a concept/entity page")
    p.add_argument("vault")
    p.add_argument("--kind", required=True, choices=[CONCEPT_KIND, ENTITY_KIND])
    p.add_argument("--name", required=True)
    p.add_argument("--source-slug", required=True)
    p.add_argument("--source-title", required=True)
    p.add_argument("--source-date", required=True)
    p.add_argument("--definition", help="one-sentence definition (for stub creation)")
    p.add_argument("--fact", help="new fact to append under ## Facts")
    p.add_argument("--contradicts", help="existing claim that disagrees with --fact")
    p.add_argument("--force", action="store_true",
                   help="bypass safety checks: case-collision, --contradicts-not-found")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """Create or additively update the named concept / entity page."""
    vault = Path(args.vault).resolve()
    ensure_schema(vault)
    if args.kind not in (CONCEPT_KIND, ENTITY_KIND):
        die(f"--kind must be 'concept' or 'entity', got {args.kind!r}")

    safe_name = _safe_name(args.name, kind="name")
    # also sanitize source_slug since it's embedded into paths/links
    safe_slug = _safe_name(args.source_slug, kind="source-slug")
    # Reject newlines / structural-markup in user-supplied prose fields —
    # otherwise an attacker can spoof fake section headers or separators
    # via crafted --definition / --fact / --contradicts / --source-title.
    safe_title = _safe_inline(args.source_title, "source-title")
    safe_date = _safe_inline(args.source_date, "source-date")
    safe_definition = _safe_inline(args.definition, "definition") if args.definition else None
    safe_fact = _safe_inline(args.fact, "fact") if args.fact else None
    safe_contradicts = _safe_inline(args.contradicts, "contradicts") if args.contradicts else None

    target_dir = vault / KIND_TO_SUBDIR[args.kind]
    collision = _check_case_collision(target_dir, safe_name)
    if collision:
        die(f"case-collision: '{safe_name}.md' would collide with existing "
            f"'{collision}' on a case-insensitive filesystem; rename one or "
            f"pass --force to override", code=4)

    target = target_dir / f"{safe_name}.md"
    # final containment check after resolving symlinks etc. — use
    # is_relative_to so a sibling like `_concepts_evil/` cannot match
    # via string-prefix confusion (S-H1).
    if not _is_relative_to(target, target_dir):
        die(f"refusing to write outside {target_dir}: {target}")

    created = not target.exists()

    # verify --contradicts text actually appears on the page (unless creating)
    contradiction_warning = None
    if safe_contradicts and not created:
        page_text = read_text(target)
        if safe_contradicts not in page_text:
            if not args.force:
                die(f"--contradicts text {safe_contradicts!r} not found on "
                    f"{target.relative_to(vault)}; pass --force to record anyway",
                    code=5)
            contradiction_warning = "contradicted text not found on page; recorded anyway via --force"

    if created:
        content = render_stub_page(
            kind=args.kind, name=safe_name, definition=safe_definition,
            source_slug=safe_slug, source_title=safe_title,
            source_date=safe_date,
        )
    else:
        content = read_text(target)
        content = upsert_source_row(
            content, safe_slug, safe_title, safe_date
        )
        content = upsert_footnote(content, safe_slug, safe_title)

    if safe_fact:
        content = append_fact(content, safe_fact, safe_slug)

    if safe_contradicts:
        if not safe_fact:
            die("--contradicts requires --fact (the new claim that disagrees)")
        content = append_contradiction(content, safe_contradicts, safe_fact, safe_slug)

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

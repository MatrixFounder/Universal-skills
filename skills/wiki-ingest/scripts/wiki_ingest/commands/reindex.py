"""`reindex` subcommand — rebuild index.md from disk.

Parses + masks each page exactly once (P-H4). Preserves custom sections
from the existing index (anything outside the default
Sources/Concepts/Entities). Inline-construct masking on the existing
index defeats L-H6 ghost headers inside backticks / HTML comments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from wiki_ingest._frontmatter import split_frontmatter
from wiki_ingest._markdown import (
    _H2_HEADER_RE,
    _HTML_COMMENT_RE,
    _ensure_masked,
    _first_sentence,
    _mask_code_fences,
    _mask_inline_constructs,
    get_all_section_bodies,
    get_section_body,
    replace_section_body,
)
from wiki_ingest._safety import read_text, write_text
from wiki_ingest._vault import (
    DEFAULT_SUBDIRS,
    INDEX_FILE,
    SUBDIR_TO_DISPLAY,
    SUBDIR_TO_KIND,
    _walk_pages,
    ensure_schema,
    load_asset,
)


def _page_one_line(text: str, fm: dict, kind: str,
                   body: str | None = None,
                   masked: str | None = None) -> str:
    """One-line page summary for the index. Reuses pre-parsed body/masked view.

    `body` and `masked` are optional pre-extracted artifacts from the caller
    (P-H4: avoid re-parsing frontmatter and re-masking the page).
    """
    masked = _ensure_masked(text, masked)
    # Sources: prefer summary frontmatter, else first sentence of TL;DR / Executive Summary / first paragraph
    if kind == "source":
        for key in ("summary", "tldr", "description"):
            v = fm.get(key)
            if v:
                return str(v).strip().replace("\n", " ")
        if body is None:
            body = split_frontmatter(text)[1]
        # try TL;DR section, then Executive Summary (common summarizing-meetings output)
        for section in ("TL;DR", "Executive Summary"):
            body_text = get_section_body(text, section, masked=masked)
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
    defn = get_section_body(text, "Definition", masked=masked)
    if defn:
        return _first_sentence(defn.strip())
    return ""


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("reindex",
                       help="rebuild index.md from disk (preserves Notes section)")
    p.add_argument("vault")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    ensure_schema(vault)

    # Bucket pages by the on-disk subdir (with underscore prefix), then map
    # to user-facing display section labels when rendering the index.
    # Parse frontmatter + mask each page exactly ONCE — pass `body` and
    # `masked` through to `_page_one_line` (P-H4).
    rows_by_subdir: dict[str, list[str]] = {sd: [] for sd in DEFAULT_SUBDIRS}
    for md in _walk_pages(vault):
        try:
            text = read_text(md)
        except OSError:
            continue
        fm, body = split_frontmatter(text)
        subdir = md.parent.name
        if subdir not in rows_by_subdir:
            continue
        masked = _mask_inline_constructs(_mask_code_fences(text))
        kind = fm.get("kind") or SUBDIR_TO_KIND.get(subdir, "unknown")
        title = fm.get("title") or fm.get("name") or md.stem
        date = fm.get("date") or fm.get("created") or ""
        one_line = _page_one_line(text, fm, kind, body=body, masked=masked)
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
        # Mask existing once for the entire preserve-loop — and ALSO mask
        # inline constructs so `## Foo` inside an inline backtick or HTML
        # comment is not mis-treated as a real header (L-H6 mitigation).
        existing_masked = _mask_inline_constructs(_mask_code_fences(existing))
        # Walk header occurrences in document order; track which non-default
        # names we've already handled so each unique name is processed once
        # and ALL its occurrences are collected.
        handled: set[str] = set()
        for m in _H2_HEADER_RE.finditer(existing_masked):
            header_text = m.group(1).strip()
            if header_text in display_section_names:
                continue
            if header_text in handled:
                continue
            handled.add(header_text)

            bodies = [b.strip("\n") for b in
                      get_all_section_bodies(existing, header_text,
                                             masked=existing_masked)]
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

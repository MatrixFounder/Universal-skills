"""`lint` subcommand — health check: orphans, dangling, contradictions, missing.

One-pass enrichment (OVERLAP-2 + P-H2): each page read once, masked once,
parsed once, wikilinks extracted once. Subsequent passes consume cached
data. O(1) in-memory `known_names` set replaces the pre-fix stat-storm
(P-H3). Concept aggregation is case-insensitive (L-L7). Dangling reports
surface anchor info (L-L4). Output sanitised via `_safe_for_json` (S-M6).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from wiki_ingest._frontmatter import split_frontmatter
from wiki_ingest._markdown import (
    _extract_wikilinks_with_anchors,
    _mask_code_fences,
    _mask_inline_constructs,
    get_section_body,
)
from wiki_ingest._safety import _safe_for_json, die, read_text
from wiki_ingest._vault import SUBDIR_TO_KIND, _walk_pages


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("lint",
                       help="health check: orphans, dangling links, "
                            "contradictions, missing pages")
    p.add_argument("vault")
    p.add_argument("--threshold", type=int, default=2,
                   help="min sources mentioning a concept to flag missing-page (default: 2)")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        die(f"vault not a directory: {vault}")

    pages: dict[str, dict] = {}   # name → {path, raw, fm, kind, masked, wikilinks}
    inbound: dict[str, set[str]] = {}
    contradictions: list[dict] = []
    # L-L7: aggregate concept mentions case-insensitively so
    # "Hermes Agent" vs "hermes agent" don't fragment the missing-page
    # heuristic. Store both the canonical display form and the sources.
    concept_freq: dict[str, dict] = {}  # lc_name → {display, sources: set}

    # ONE-PASS enrichment: read each page once, mask once, parse fm once,
    # extract wikilinks once, run contradictions check using the cached
    # masked view. Subsequent passes consume cached data — no re-mask,
    # no re-parse (OVERLAP-2 + P-H2).
    for md in _walk_pages(vault):
        try:
            text = read_text(md)
        except OSError:
            continue
        fm, body = split_frontmatter(text)
        masked_full = _mask_inline_constructs(_mask_code_fences(text))
        wikilinks_with_anchors = _extract_wikilinks_with_anchors(text,
                                                                 masked=masked_full)
        wikilinks = set(wikilinks_with_anchors.keys())
        name = md.stem
        pages[name] = {
            "path": str(md.relative_to(vault)),
            "raw": text,
            "fm": fm,
            "masked": masked_full,
            "wikilinks": wikilinks,
            # {target: {anchor, ...}} — anchors used for L-L4 dangling display
            "wikilinks_anchors": wikilinks_with_anchors,
            "kind": fm.get("kind") or SUBDIR_TO_KIND.get(md.parent.name, "unknown"),
        }
        # contradictions detection — reuse the cached masked view
        contra_body = get_section_body(text, "Contradictions", masked=masked_full)
        if contra_body and contra_body.strip():
            count = contra_body.count("⚠️")
            contradictions.append({
                "page": str(md.relative_to(vault)),
                "count": count or 1,
            })
        # collect concept mentions from source-page frontmatter — keyed by
        # lowercase form (L-L7) so casing variants aggregate together.
        if SUBDIR_TO_KIND.get(md.parent.name) == "source":
            for c in (fm.get("concepts") or []):
                if not isinstance(c, str):
                    continue
                c = c.strip()
                if not c:
                    continue
                lc = c.lower()
                entry = concept_freq.setdefault(lc, {"display": c, "sources": set()})
                entry["sources"].add(name)

    # In-memory page-name set for O(1) existence checks — replaces the
    # stat-storming `_page_exists_anywhere` (P-H3).
    known_names: set[str] = set(pages.keys())

    # inbound link counts — reuse cached wikilinks + frontmatter
    # AND treat frontmatter `concepts:` / `related:` entries as implicit
    # inbound links, since they declare "this source is about X" even when
    # the body doesn't bracket the name as [[X]].
    for name, info in pages.items():
        targets = set(info["wikilinks"])
        fm = info["fm"]
        for entry in (fm.get("concepts") or []):
            if not isinstance(entry, str):
                continue
            e = entry.strip()
            if e:
                targets.add(e)
        for entry in (fm.get("related") or []):
            if not isinstance(entry, str):
                continue
            m = re.match(r"^\[\[([^\]|#]+?)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]$",
                         entry.strip())
            t = (m.group(1) if m else entry).strip()
            if t:
                targets.add(t)
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

    # dangling: link targets that have no corresponding page (O(1) membership
    # check via known_names, no filesystem stat needed). For each broken
    # target we also surface any anchors that were referenced (L-L4) so the
    # operator sees `Foo#API` instead of bare `Foo`.
    dangling: dict[str, dict] = {}
    for name, info in pages.items():
        for target, anchors in info["wikilinks_anchors"].items():
            if target in known_names:
                continue
            entry = dangling.setdefault(target, {"referenced_by": set(),
                                                 "anchors": set()})
            entry["referenced_by"].add(info["path"])
            entry["anchors"].update(a for a in anchors if a)

    # missing concept pages: concepts mentioned in ≥threshold sources without
    # a page. Case-insensitive aggregation (L-L7) — entries are keyed by
    # lowercase form, but we surface the first-seen display casing.
    threshold = args.threshold
    known_lc = {n.lower() for n in known_names}
    missing_concept_pages = []
    for lc, entry in concept_freq.items():
        if lc in known_lc:
            continue
        sources = sorted(entry["sources"])
        if len(sources) >= threshold:
            missing_concept_pages.append({
                "name": entry["display"],
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
            {"target": t,
             "referenced_by": sorted(d["referenced_by"]),
             # Surface specific anchors so the operator sees Foo#API (L-L4)
             "anchors": sorted(d["anchors"]) if d["anchors"] else []}
            for t, d in sorted(dangling.items())
        ],
        "open_contradictions": sorted(contradictions, key=lambda x: x["page"]),
        "missing_concept_pages": sorted(missing_concept_pages, key=lambda x: -x["count"]),
    }
    print(json.dumps(_safe_for_json(report), indent=2, ensure_ascii=False))
    return 0

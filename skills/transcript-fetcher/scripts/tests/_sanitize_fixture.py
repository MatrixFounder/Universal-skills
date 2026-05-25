#!/usr/bin/env python3
"""Sanitize a Skool lesson HTML snapshot in place.

Usage::

    python3 scripts/tests/_sanitize_fixture.py \\
        scripts/tests/fixtures/skool_lesson_youtube_embed.html

Reads the file, isolates the ``__NEXT_DATA__`` JSON, strips PII and
sensitive build-time configuration (API URLs, Stripe / FB / Google
keys, real user metadata), trims the course tree to ONLY the lesson
node identified by ``pageProps.selectedModule`` (wrapped in a
two-level chain so :func:`_find_node_by_id`-style recursion still has
something to walk), and rewrites the file as a compact HTML wrapper.

The script is idempotent — re-running it on an already-sanitized file
is safe.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional


_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
    re.DOTALL,
)

# Synthetic ProseMirror v2 body used by sanitized fixtures. Exercises
# paragraph + bold + horizontalRule + codeBlock + ordered list so the
# Markdown converter has something to walk, but contains zero IP from
# the original course and no shell-command strings.
_SYNTHETIC_DESC = (
    "[v2]"
    + json.dumps([
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "This lesson covers the topic in detail."},
            ],
        },
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Key idea: ", "marks": [{"type": "bold"}]},
                {"type": "text", "text": "stay focused on the fundamentals."},
            ],
        },
        {"type": "horizontalRule"},
        {
            "type": "codeBlock",
            "attrs": {"language": "python"},
            "content": [{"type": "text", "text": "print('hello world')"}],
        },
        {
            "type": "orderedList",
            "content": [
                {"type": "listItem", "content": [
                    {"type": "paragraph", "content": [
                        {"type": "text", "text": "Item one"},
                    ]},
                ]},
                {"type": "listItem", "content": [
                    {"type": "paragraph", "content": [
                        {"type": "text", "text": "Item two"},
                    ]},
                ]},
            ],
        },
    ], ensure_ascii=False, separators=(",", ":"))
)

# Synthetic identifiers used to replace every real UUID / slug we
# find in the source HTML. These are stable across runs so test
# expectations stay reproducible.
_SYNTHETIC = {
    "community_slug": "example-community",
    "classroom_id": "aaaaaaaa",  # was "a60f0bd2"
    "lesson_id": "00000000000000000000000000000001",
    "group_id":  "00000000000000000000000000000002",
    "user_id":   "00000000000000000000000000000003",
    "parent_id": "00000000000000000000000000000004",
    "root_id":   "00000000000000000000000000000005",
    "page_title": "Fixture Lesson",
    "lesson_title": "Fixture Lesson",
    "video_link": "https://youtu.be/aaaaaaaaaaa",  # synthetic 11-char id
    "video_thumbnail": "",  # drop completely
}

# Keys whose VALUES (anywhere in the env block) we always clobber.
_ENV_KEYS_TO_CLOBBER = {
    "CLIENT_ID_KEY",
    "API_URL",
    "PUBSUB_URL",
    "FACEBOOK_APP_ID",
    "STRIPE_PUBLISHABLE_KEY",
    "BILLING_STRIPE_PUBLISHABLE_KEY",
    "GIPHY_KEY",
    "FB_PIXEL_ID",
    "TELEMETRY_URL",
    "STREAM_CLIENT_KEY",
    "GOOGLE_MAPS_API_KEY",
    "HORMOZI_META_PIXEL_ID",
}


def sanitize_html(raw_html: str) -> str:
    m = _NEXT_DATA_RE.search(raw_html)
    if not m:
        raise SystemExit("input has no __NEXT_DATA__ — nothing to sanitize")
    payload = json.loads(m.group(1))
    payload = _scrub(payload)
    rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return _wrap(rendered, page_title=_extract_title(payload))


def _scrub(data: Any) -> dict:
    """Trim ``props.pageProps`` to the bare minimum the adapter needs.

    We keep:
        - settings.pageTitle (drop pageMeta, which leaks excerpts) and
          REWRITE it to a synthetic value so the title doesn't tie the
          fixture to any real Skool community / course.
        - selectedModule (RENAMED to a synthetic UUID)
        - currentPage (query + path + pageKey, with ids / slugs scrubbed)
        - currentGroup as ``{id, name}`` only, BOTH replaced with
          synthetic values.
        - course rewritten as a 2-level wrapper around the single lesson;
          the lesson's `id` / `userId` / `groupId` / `parentId` / `rootId`
          are all replaced with synthetic UUIDs, the title is replaced,
          the description body is replaced with synthetic ProseMirror,
          and the videoThumbnail is dropped.
        - env with sensitive values REDACTED.

    Dropped: renderData, growthBookData, pixelId, self, referer, host,
    userAgent, videos, pinnedPosts, inProgressDuplication, editing,
    isMobile, isApp, maintenance, video.

    PII goal: a sanitised fixture must be safe to commit to a public
    repo — no real user/group/lesson UUIDs, no real community slugs,
    no embedded YouTube/Vimeo thumbnails that could be reverse-engineered.
    """
    if not isinstance(data, dict) or "props" not in data:
        raise SystemExit("input JSON missing 'props' — not a Next.js page")
    props = data["props"]
    if not isinstance(props, dict) or "pageProps" not in props:
        raise SystemExit("input JSON missing 'props.pageProps'")
    pp = props["pageProps"]
    if not isinstance(pp, dict):
        raise SystemExit("pageProps is not a dict")

    out: dict = {}

    # settings.pageTitle (drop everything else under settings — pageMeta
    # contains a snippet of the lesson body).
    settings = pp.get("settings")
    if isinstance(settings, dict) and isinstance(settings.get("pageTitle"), str):
        out["settings"] = {"pageTitle": _SYNTHETIC["page_title"]}

    # selectedModule — REWRITE to synthetic so it can't be cross-correlated
    # with real Skool data leaks.
    real_selected = pp.get("selectedModule")
    if isinstance(real_selected, str):
        out["selectedModule"] = _SYNTHETIC["lesson_id"]

    # currentPage — scrub ids/slugs inside path + query.
    cp = pp.get("currentPage")
    if isinstance(cp, dict):
        out["currentPage"] = {
            "pageKey": "synthetic",
            "path": f"/{_SYNTHETIC['community_slug']}/classroom/{_SYNTHETIC['classroom_id']}",
            "isPostDetails": cp.get("isPostDetails"),
            "isChat": cp.get("isChat"),
            "query": {
                "md": _SYNTHETIC["lesson_id"],
                "group": _SYNTHETIC["community_slug"],
                "course": _SYNTHETIC["classroom_id"],
            },
        }

    # currentGroup — REWRITE both id and name.
    if isinstance(pp.get("currentGroup"), dict):
        out["currentGroup"] = {
            "id": _SYNTHETIC["group_id"],
            "name": _SYNTHETIC["community_slug"],
        }

    # course — extract the lesson node, rewrap minimally, scrub all ids.
    if isinstance(real_selected, str):
        lesson = _find_node_by_id(pp.get("course"), real_selected)
        if lesson is not None:
            sanitised_lesson = _scrub_lesson_node(lesson)
            out["course"] = {"children": [{"children": [{"course": sanitised_lesson}]}]}

    # env — keep keys, redact values.
    env = pp.get("env")
    if isinstance(env, dict):
        out["env"] = {
            k: ("REDACTED" if k in _ENV_KEYS_TO_CLOBBER else v)
            for k, v in env.items()
        }

    return {
        "props": {"pageProps": out},
        "page": "/[group]/classroom/[course]",
        # Top-level `query` is the Next.js page query; it carries the
        # community slug, classroom id, lesson `md`, and any UTM params
        # the user landed with. Replace wholesale with synthetic values.
        "query": {
            "md": _SYNTHETIC["lesson_id"],
            "group": _SYNTHETIC["community_slug"],
            "course": _SYNTHETIC["classroom_id"],
        },
        "buildId": "sanitized",
    }


def _find_node_by_id(node: Any, target_id: str) -> Optional[dict]:
    """Recursively locate the dict whose ``id`` equals ``target_id``."""
    if isinstance(node, dict):
        if node.get("id") == target_id:
            return node
        for value in node.values():
            found = _find_node_by_id(value, target_id)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_node_by_id(item, target_id)
            if found is not None:
                return found
    return None


def _scrub_lesson_node(lesson: dict) -> dict:
    """Return a copy of the lesson dict with every UUID/title replaced.

    Keeps the structural shape adapter tests rely on (``id``, ``name``,
    ``metadata``, ``unitType``, ``parentId``, ``rootId``, ``userId``,
    ``groupId``, ``state``, ``public``) but swaps every identifier for
    a stable synthetic value and replaces the description body with
    synthetic ProseMirror content.
    """
    out = dict(lesson)
    out["id"] = _SYNTHETIC["lesson_id"]
    out["name"] = "synthetic"
    if "parentId" in out:
        out["parentId"] = _SYNTHETIC["parent_id"]
    if "rootId" in out:
        out["rootId"] = _SYNTHETIC["root_id"]
    if "userId" in out:
        out["userId"] = _SYNTHETIC["user_id"]
    if "groupId" in out:
        out["groupId"] = _SYNTHETIC["group_id"]
    md = out.get("metadata")
    if isinstance(md, dict):
        new_md = dict(md)
        new_md["title"] = _SYNTHETIC["lesson_title"]
        new_md["desc"] = _SYNTHETIC_DESC
        new_md["videoLink"] = _SYNTHETIC["video_link"]
        new_md["videoThumbnail"] = _SYNTHETIC["video_thumbnail"]
        new_md.pop("transcript", None)
        out["metadata"] = new_md
    return out


def _extract_title(data: dict) -> Optional[str]:
    pp = (
        data.get("props", {}).get("pageProps", {})
        if isinstance(data, dict)
        else {}
    )
    settings = pp.get("settings") if isinstance(pp, dict) else None
    if isinstance(settings, dict):
        t = settings.get("pageTitle")
        if isinstance(t, str):
            return t
    return None


def _wrap(json_payload: str, *, page_title: Optional[str]) -> str:
    title = (page_title or "Skool Lesson Fixture").replace("<", "").replace(">", "")
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\"><head>"
        f"<title>{title}</title>"
        "<meta charset=\"utf-8\">"
        "</head><body>"
        "<!-- sanitized Skool lesson fixture — do not edit by hand -->"
        f'<script id="__NEXT_DATA__" type="application/json">{json_payload}</script>'
        "</body></html>\n"
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sanitize a Skool lesson HTML snapshot in place."
    )
    parser.add_argument("path", type=Path, help="HTML file to sanitize (overwritten).")
    args = parser.parse_args(argv)
    src = args.path
    if not src.exists():
        print(f"file not found: {src}", file=sys.stderr)
        return 2
    raw = src.read_text(encoding="utf-8", errors="replace")
    out = sanitize_html(raw)
    src.write_text(out, encoding="utf-8")
    print(f"sanitized {src} ({len(raw):,} -> {len(out):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

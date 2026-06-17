"""Depth-tracked DOM scanning helpers (regex-based, no parser dependency).

Used by both `preprocess` (universal ad-strip) and `reader_mode` (article
root extraction + widget strip). The helpers operate on raw HTML strings,
return byte offsets, and intentionally avoid pulling in lxml/BeautifulSoup
— html2pdf already depends on weasyprint (which embeds its own parser),
and adding a second tree builder for the preprocessing pass would cost
more than the regex approach saves.
"""
from __future__ import annotations

import re

# Generic any-tag opener — captures tag name, attribute blob, and the
# self-closing slash. Used to enumerate every element start, then per-match
# attribute checks decide which ones to keep.
ANY_OPEN_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9-]*)(\s[^>]*)?(/?)>", re.DOTALL)

# HTML void elements that have no closing tag (skip depth tracking).
VOID_ELEMENTS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})


def get_attr(attrs: str, name: str) -> str | None:
    """Return the value of attribute `name` from a tag's attribute blob, or None.

    Anchors at the start of the blob OR at a whitespace boundary — without
    this, `data-foo="role='main'"` would return `"main"` for a `role` lookup
    (the `\\b` word boundary plus search-anywhere matches inside the
    `data-foo` value). Tag attribute names ALWAYS follow whitespace or
    start-of-blob; nothing else can be interpreted as an attribute. (VDD-iter-5
    fix.)
    """
    m = re.search(
        rf'(?:^|\s){re.escape(name)}\s*=\s*["\']([^"\']*)["\']',
        attrs,
        flags=re.IGNORECASE,
    )
    return m.group(1) if m else None


# NB: keyword names below (`tag`, `class_token`, `class_substring_any`,
# `attr_name`, `attr_value`) are part of the call API — `reader_mode.py`
# stores selector specs as dicts and splats them via `**cand["lookup"]`.
# Renaming any kwarg silently breaks every selector tier whose dict uses
# that key; E2E does not exercise every tier, so the break can land green.
def find_all_elements(
    html: str,
    *,
    tag: str | None = None,
    class_token: str | None = None,
    class_substring_any: list[str] | None = None,
    attr_name: str | None = None,
    attr_value: str | None = None,
) -> list[tuple[int, int]]:
    """Find all elements matching the given constraints; depth-tracked.

    Returns a list of (start, end) byte offsets into `html` for the outer
    HTML of each match. Multiple constraints AND together. Returns nested
    matches too (parent + child both included if both qualify); callers
    decide whether to keep all (longest-match) or only outermost (strip).

      * `tag`                 → tag name equals (case-insensitive).
      * `class_token`         → class= attribute contains exact token (CSS `.X`).
      * `class_substring_any` → class= attribute contains ANY of the given
                                substrings as substring (CSS `[class*=X]`).
      * `attr_name`+`attr_value` → exact attribute value match (id, role, …).
    """
    out: list[tuple[int, int]] = []
    for m in ANY_OPEN_RE.finditer(html):
        name = m.group(1).lower()
        if name in VOID_ELEMENTS:
            continue
        attrs = m.group(2) or ""
        if m.group(3) == "/":          # self-closing form, no body
            continue
        if tag and name != tag.lower():
            continue
        if class_token is not None:
            cv = get_attr(attrs, "class") or ""
            if class_token not in cv.split():
                continue
        if class_substring_any:
            cv = get_attr(attrs, "class") or ""
            if not any(kw in cv for kw in class_substring_any):
                continue
        if attr_name and attr_value is not None:
            av = get_attr(attrs, attr_name)
            if av is None or av.strip() != attr_value:
                continue
        # Find the matching close tag with depth tracking.
        start = m.start()
        pos = m.end()
        depth = 1
        open_n = re.compile(
            rf"<{re.escape(name)}(?:\s[^>]*)?(/?)>",
            re.IGNORECASE,
        )
        close_n = re.compile(rf"</{re.escape(name)}\s*>", re.IGNORECASE)
        while pos < len(html) and depth > 0:
            o = open_n.search(html, pos)
            c = close_n.search(html, pos)
            if c is None:
                break
            if o is not None and o.start() < c.start():
                if o.group(1) != "/":
                    depth += 1
                pos = o.end()
            else:
                depth -= 1
                pos = c.end()
        if depth == 0:
            out.append((start, pos))
    return out


def text_length(fragment: str) -> int:
    """Length of `fragment` after stripping all tags + script/style content,
    leading/trailing whitespace.

    Tag-strip alone leaves `<script>...JS body...</script>` content visible
    as "text" — which inflates the length on Mintlify / Next.js docs whose
    `<article>` wrappers contain `<script id="__NEXT_DATA__">{...JSON...}
    </script>` hydration blobs of 100s of KB. Without the script/style
    pre-strip, the candidate trivially passes any `min_text` gate even when
    the visible prose is 0 chars. (VDD-iter-5 fix.)
    """
    fragment = re.sub(
        r"<script\b[^>]*>.*?</script>", "", fragment,
        flags=re.DOTALL | re.IGNORECASE,
    )
    fragment = re.sub(
        r"<style\b[^>]*>.*?</style>", "", fragment,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return len(re.sub(r"<[^>]+>", "", fragment).strip())


def body_text_length(html: str) -> int:
    """Text-content length of the document `<body>` (or whole doc if no body)."""
    body_m = re.search(r"<body\b[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    inner = body_m.group(1) if body_m else html
    return max(1, text_length(inner))

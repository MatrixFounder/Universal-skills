"""html2md-OWNED post-turndown Markdown tidy pass (FC-4 helper).

Cleans artifacts that survive the HTML→MD core because doc-site SPAs
(GitBook/Mintlify/Fern/Discord) wrap content in widgets the turndown core can't know
about, and the pdf-mastered reader-mode (tuned for blog articles) barely trims them:

  • **Empty ATX headings** — these sites render a heading as an element holding only an
    anchor link, with the title text in a SEPARATE sibling, so turndown emits ``### ``
    then the text on its own line. We merge them back into ``### Title``.
  • **Standalone chrome lines** — exact-match boilerplate (``Copy`` / ``Search…`` /
    ``Ask AI`` / feedback / AI-assistant widget text) that leaks as stray paragraphs.

Conservative by design: only EXACT-match chrome strings and genuinely-empty headings
are touched; real prose, links, code, lists and tables are never *removed*.

Known limitation (empty-heading merge): the merge re-levels the line that follows an
empty heading into that heading's text. For the targeted doc-site pattern (empty
heading + its detached title sibling) this is correct; in the rare case where an empty
heading is instead followed directly by a body paragraph, that paragraph is promoted to
a heading (mis-leveled, never deleted). ``_NOT_MERGEABLE`` blocks lists/fences/tables/
quotes/other-headings from being absorbed.
"""
from __future__ import annotations

import re

_HEADING_EMPTY = re.compile(r"^(#{1,6})[ \t]*$")
# Lines an empty heading must NOT absorb (another heading / code fence / table / list / quote).
_NOT_MERGEABLE = re.compile(r"^(#{1,6}[ \t]|```|~~~|\||[-*+][ \t]|>[ \t]?|\d+\.[ \t])")

# Exact standalone chrome strings (compared case-insensitively, whitespace-stripped).
# Deliberately HIGH-CONFIDENCE only: bare generic words that could be legitimate
# content on their own line (e.g. "Menu", "Navigation", "Assistant", "Yes No") are NOT
# listed — better to leave a stray chrome word than to delete real content.
_CHROME_EXACT = frozenset({
    "copy", "copy page", "copy code", "ask ai", "search...", "search…",
    "on this page", "skip to main content",
    "was this page helpful?", "yesno",
    "responses are generated using ai and may contain mistakes.",
    "hi, i'm an ai assistant with access to documentation and other content.",
    "tip: you can toggle this pane with",
    "⌘ctrlk", "⌘k", "⌘i", "⌘",
})
_CHROME_PREFIX = ("built with", "powered by", "last updated")


def _is_chrome(line: str) -> bool:
    s = line.strip().lower()
    if not s:
        return False
    if s in _CHROME_EXACT:
        return True
    return any(s.startswith(p) for p in _CHROME_PREFIX)


def tidy_markdown(md: str) -> str:
    """Merge empty ATX headings, drop standalone chrome lines, collapse blank runs."""
    lines = md.split("\n")
    out: list[str] = []
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        m = _HEADING_EMPTY.match(line)
        if m:
            j = i + 1
            while j < n and lines[j].strip() == "":
                j += 1
            nxt = lines[j].strip() if j < n else ""
            if nxt and not _NOT_MERGEABLE.match(nxt) and not _is_chrome(lines[j]):
                out.append(f"{m.group(1)} {nxt}")  # ### + "Title" → "### Title"
                i = j + 1
                continue
            i += 1  # genuinely-empty heading → drop it
            continue
        if _is_chrome(line):
            i += 1
            continue
        out.append(line)
        i += 1
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return text.strip() + "\n"

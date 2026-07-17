"""html-OWNED post-turndown Markdown tidy pass (FC-4 helper).

Cleans artifacts that survive the HTML→MD core because doc-site SPAs
(GitBook/Mintlify/Fern/Discord) wrap content in widgets the turndown core can't know
about, and the pdf-mastered reader-mode (tuned for blog articles) barely trims them:

  • **Empty ATX headings** — these sites render a heading as an element holding only an
    anchor link, with the title text in a SEPARATE sibling, so turndown emits ``### ``
    then the text on its own line. We merge them back into ``### Title``.
  • **Standalone chrome lines** — exact-match boilerplate (``Copy`` / ``Search…`` /
    ``Ask AI`` / feedback / AI-assistant widget text) that leaks as stray paragraphs.
  • **Tracking-redirect link wrappers** — publishing platforms launder every external
    link through a redirect endpoint (vc.ru: ``https://api.vc.ru/v2.8/redirect?to=
    <url-encoded target>&postId=…``); the article's REAL link is the decoded ``to=``
    value. Unwrapped only on a double signal (redirect-ish path segment AND a query
    param whose value is a url-encoded absolute http(s) URL) — a documented OAuth
    ``…/authorize?redirect_uri=…`` example has no redirect path segment and stays.
  • **HTML tags inside image alt text** — alt is a plain-text context by spec, so any
    tag in ``![…]`` is converter residue (observed: a raw ``<a …>SVG</a>`` caption
    leaking into alt on vc.ru). Tags are dropped, their inner text kept.

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

# Leaked HTML tag innards: X (and similar SPA) buttons carry Tailwind arbitrary-variant classes
# like ``[&>svg]:size-5`` whose ``>`` prematurely closes the tag, spilling the remaining attributes
# (``aria-label=… type="button" data-state="closed">``) into the page as visible text. We drop a
# non-code line ONLY when it carries an interactive-widget attribute AND ≥2 HTML attribute tokens —
# a signature that never occurs in legitimate article prose (and code samples live in fences, which
# this pass skips). Deliberately narrow, per this module's "leave a stray word before deleting real
# content" rule.
_ATTR_TOKEN = re.compile(r'[A-Za-z][\w:-]*="[^"]*"')
_WIDGET_ATTR = re.compile(
    r'\b(?:aria-(?:pressed|expanded|haspopup|controls|selected|checked)|data-state|data-testid)="'
)
_FENCE = re.compile(r"^[ \t]*(?:```|~~~)")

# --------------------------------------------------------------------------- #
# Math-delimiter normalization → Obsidian/KaTeX `$…$` / `$$…$$`
# --------------------------------------------------------------------------- #
# Defense-in-depth + the remote-reader 'trust markdown' path (jina), which bypasses the
# DOM math rule in html_convert.js: a reader may emit MathJax/Pandoc `\(…\)` / `\[…\]`
# that Obsidian can't render. We normalize the delimiters here, on EVERY produced
# Markdown (turndown output is already `$`-delimited by the DOM rule, so this is a no-op
# there). Code spans / fenced blocks are protected (a `\(` in a code sample is not math).
#
# Two source forms:
#   • single backslash  \( … \)  — a reader's raw MathJax; body is clean LaTeX, kept as-is.
#   • double backslash  \\( … \\) — turndown-escaped raw `\(…\)` text; the body was also
#     md-escaped, so we additionally reverse turndown's escaping of NON-letter specials
#     (`\_`→`_`, `\*`→`*`, …) — never touching LaTeX commands (`\approx`, `\sum`, which are
#     backslash+LETTER and were never escaped) and NOT `\\` (a LaTeX line-break / matrix-row
#     separator: turndown-escaping it to `\\\\` then collapsing to `\` would corrupt the math).
#
# Bracket forms gate on `_looks_like_math`: turndown escapes plain-text `[recipient]` /
# `[1]` to `\[recipient\]` / `\[1\]`, so an unconditional `\[…\]`→`$$…$$` would turn ordinary
# bracketed prose and citations into display math. Real display math from the lite path comes
# via the DOM rule (already `$`-delimited), so the only `\[…\]` reaching here are escaped
# brackets (skip unless mathy) or a remote reader's raw MathJax (mathy → convert). Paren forms
# are NOT gated: turndown does not escape `(`/`)` in prose, so `\(…\)` is always real math.
_CODE_SPLIT = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)")
_MATH_DISPLAY_ESC = re.compile(r"\\\\\[([\s\S]+?)\\\\\]")        # \\[ … \\]  (turndown)
_MATH_INLINE_ESC = re.compile(r"\\\\\((.+?)\\\\\)")              # \\( … \\)  (turndown)
_MATH_DISPLAY = re.compile(r"(?<!\\)\\\[([\s\S]+?)(?<!\\)\\\]")  # \[ … \]   (raw/jina)
_MATH_INLINE = re.compile(r"(?<!\\)\\\((.+?)(?<!\\)\\\)")        # \( … \)   (raw/jina)
_MD_UNESCAPE = re.compile(r"\\([_*\[\]()#+\-.!~`>])")            # reverse turndown md-escape (NOT \\)
# A delimited body is treated as math only with a positive signal: a LaTeX command, a
# sub/superscript/brace, a binary operator between operands, or a math/greek glyph. Plain
# words ("recipient"), citations ("1"), and lists ("a, b, c") have none → left untouched.
_MATH_SIGNAL = re.compile(
    r"\\[a-zA-Z]"                                    # \command  (\sum \frac \approx)
    r"|[\^_{}]"                                       # ^  _  {  }
    r"|(?<=[\w)\]])\s*[=+*/<>|]\s*(?=[\w(\\])"         # binary operator between operands
    r"|[←-⇿∀-⋿⨀-⫿]"      # arrows + mathematical operators
    r"|[Α-Ωα-ω]"                   # Greek letters
)
# Pathological-input guard: O(n²) worst case scales with delimiter count (each opener may
# scan to EOF). A doc with thousands of `\(`/`\[` is not real math → skip (degraded, not hung).
_MATH_DELIM_CAP = 5000


# --------------------------------------------------------------------------- #
# Link hygiene: tracking-redirect unwrap + image-alt tag strip
# --------------------------------------------------------------------------- #
# Both are CLASS-based (no site list) and double-gated, per this module's "leave junk
# before deleting real content" rule. The unwrap fires only when a URL token has BOTH
# (a) a redirect-ish segment in its PATH (…/redirect, /redir/, /away, /leaving, /exit,
# /outlink) — so a documented `…/oauth/authorize?redirect_uri=…` example is never
# touched — AND (b) a query param whose value is a url-encoded ABSOLUTE http(s) URL.
# The token is then replaced by that decoded target (unquoted exactly once; a decoded
# value that is not http(s) leaves the token alone). Applied outside code fences only.
_URL_TOKEN = re.compile(r"https?://[^\s()<>\"'\]]+")
_REDIRECT_PATH = re.compile(r"/[a-z0-9._-]*(?:redirect|redir|away|leaving|exit|outlink)[a-z0-9._-]*(?:/|$)", re.I)
_REDIRECT_TARGET = re.compile(
    r"(?:^|[?&])(?:to|url|u|target|dest|goto|link|redirect_to)=(https?%3[Aa]%2[Ff]%2[Ff][^&\s]+)"
)
# Any tag inside an image's alt brackets. Alt is plain text by spec — a `<a …>` (or any
# tag) there is turndown residue from a rich figure caption, never authored content.
_IMG_ALT = re.compile(r"!\[([^\]]*)\]")
_TAG = re.compile(r"</?[A-Za-z][^>]*>")


def _unwrap_tracking_redirects(line: str) -> str:
    def _one(m: "re.Match[str]") -> str:
        url = m.group(0)
        path, sep, query = url.partition("?")
        if not sep or not _REDIRECT_PATH.search(path):
            return url
        tm = _REDIRECT_TARGET.search(query)
        if not tm:
            return url
        from urllib.parse import unquote
        target = unquote(tm.group(1))
        return target if target.lower().startswith(("http://", "https://")) else url

    return _URL_TOKEN.sub(_one, line)


def _strip_tags_in_image_alt(line: str) -> str:
    return _IMG_ALT.sub(lambda m: "![" + _TAG.sub("", m.group(1)) + "]", line)


def _looks_like_math(s: str) -> bool:
    return bool(_MATH_SIGNAL.search(s))


def _normalize_math(md: str) -> str:
    """Convert surviving ``\\(…\\)`` / ``\\[…\\]`` math delimiters to ``$…$`` / ``$$…$$``,
    skipping code spans and fenced blocks. Bracket forms convert only when the body looks
    like math (escaped plain-text brackets are left alone). Idempotent; no ``\\(``/``\\[`` → no-op."""
    if "\\(" not in md and "\\[" not in md:
        return md  # fast path: no MathJax delimiters at all
    if md.count("\\(") + md.count("\\[") > _MATH_DELIM_CAP:
        return md  # pathological delimiter density → skip rather than risk an O(n²) scan

    def _disp_esc(m):
        tex = _MD_UNESCAPE.sub(r"\1", m.group(1)).strip()
        return f"$${tex}$$" if _looks_like_math(tex) else m.group(0)

    def _disp(m):
        tex = m.group(1).strip()
        return f"$${tex}$$" if _looks_like_math(tex) else m.group(0)

    parts = _CODE_SPLIT.split(md)
    for i in range(0, len(parts), 2):  # even = prose; odd = code (kept verbatim)
        seg = parts[i]
        seg = _MATH_DISPLAY_ESC.sub(_disp_esc, seg)                                       # \\[ … \\]  (gated)
        seg = _MATH_INLINE_ESC.sub(lambda m: "$" + _MD_UNESCAPE.sub(r"\1", m.group(1)).strip() + "$", seg)
        seg = _MATH_DISPLAY.sub(_disp, seg)                                               # \[ … \]   (gated)
        seg = _MATH_INLINE.sub(lambda m: "$" + m.group(1).strip() + "$", seg)
        parts[i] = seg
    return "".join(parts)


def _is_chrome(line: str) -> bool:
    s = line.strip().lower()
    if not s:
        return False
    if s in _CHROME_EXACT:
        return True
    return any(s.startswith(p) for p in _CHROME_PREFIX)


def _is_attr_soup(line: str) -> bool:
    """A line that is leaked HTML tag innards (see ``_WIDGET_ATTR`` note), not prose."""
    return bool(_WIDGET_ATTR.search(line)) and len(_ATTR_TOKEN.findall(line)) >= 2


def tidy_markdown(md: str) -> str:
    """Merge empty ATX headings, drop standalone chrome / leaked-markup lines, collapse blank runs.
    Fenced code blocks are passed through untouched (never treated as chrome or markup soup)."""
    lines = md.split("\n")
    out: list[str] = []
    n = len(lines)
    i = 0
    in_fence = False
    while i < n:
        line = lines[i]
        if _FENCE.match(line):  # code fences are inviolable — toggle, keep verbatim
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue
        if in_fence:
            out.append(line)
            i += 1
            continue
        m = _HEADING_EMPTY.match(line)
        if m:
            j = i + 1
            while j < n and lines[j].strip() == "":
                j += 1
            nxt = lines[j].strip() if j < n else ""
            if (nxt and not _NOT_MERGEABLE.match(nxt)
                    and not _is_chrome(lines[j]) and not _is_attr_soup(lines[j])):
                out.append(f"{m.group(1)} {nxt}")  # ### + "Title" → "### Title"
                i = j + 1
                continue
            i += 1  # genuinely-empty heading → drop it
            continue
        if _is_chrome(line) or _is_attr_soup(line):
            i += 1
            continue
        # Link hygiene (outside fences only): alt-tag strip FIRST — a redirect href inside
        # an alt-text `<a>` vanishes with its tag, so the unwrap then sees only real link
        # targets (order matters; reversed, the dead alt href would be unwrapped for nothing).
        line = _unwrap_tracking_redirects(_strip_tags_in_image_alt(line))
        out.append(line)
        i += 1
    text = _normalize_math("\n".join(out))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"

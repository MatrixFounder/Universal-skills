"""Reader-mode article extraction (Safari Reader View parity).

Walks a tiered priority list of article-root selectors (Confluence /
wiki conventions first, generic semantic tags last), strips known widget
classes (recommendation carousels, comment threads, share bars), and
returns a clean DOCTYPE + minimal `<head>` + extracted body. Reader mode
renders with only the bundled DEFAULT_CSS + NORMALIZE_CSS for consistent
typography across sites.

pdf-9: extends reader-mode with universal SPA-chrome heuristic. When the
input HTML is detected as a hydrated SPA (bundle size + landmark count,
no framework-string sniffing), strip elements by ARIA `role` / semantic
landmark tag / inline `position:fixed` heuristic — vendor-agnostic. For
landmark-free SPAs (no ARIA, no `<aside>`/`<nav>`), fall back to "largest
contentful subtree by text density" as best-effort. Validated across 4
SPA stacks: Angular (ELMA365), Closure (Gmail), Framer (Sentora), bare
Yandex Cloud Console.
"""
from __future__ import annotations

import re
import sys

from .dom_utils import (
    ANY_OPEN_RE,
    body_text_length,
    find_all_elements,
    get_attr,
    text_length,
)

# Tiered article-root selectors with per-row text-length thresholds.
#
#   * High-confidence (Confluence/wiki conventions): `min_text=1` because
#     diagram-heavy KB pages legitimately have <500 chars and we trust the
#     selector. `id="main-content"` / `.wiki-content` rarely false-positive.
#   * Specific CMS / blog classes: `min_text=500` to skip excerpts on archive
#     index pages and small metadata divs (`.entry-meta`, `.post-meta`).
#   * Generic semantics (`<article>`, `[role=main]`): `min_text=500` because
#     false positives are common (sites use `<article>` for comments, etc.).
#   * Bare `<main>` is INTENTIONALLY OMITTED — it's tried separately with a
#     body-ratio guard (see `reader_mode_html`). On news/blog SPAs `<main>`
#     often wraps the entire site (header + body + footer + recommendations).
#
# Within each row, the LONGEST qualifying match wins — handles archive pages
# with multiple `.entry` divs (post body is longer than excerpts) and Disqus
# comment threads (post body is longer than any single comment article).
_READER_CANDIDATES: list[dict] = [
    {"lookup": {"attr_name": "id",   "attr_value": "main-content"},   "min_text": 1},
    {"lookup": {"class_token": "wiki-content"},                       "min_text": 1},
    {"lookup": {"attr_name": "id",   "attr_value": "content"},        "min_text": 1},
    {"lookup": {"class_token": "entry"},                              "min_text": 500},
    {"lookup": {"class_token": "post-content"},                       "min_text": 500},
    {"lookup": {"class_token": "article-content"},                    "min_text": 500},
    {"lookup": {"class_token": "main-content"},                       "min_text": 500},
    {"lookup": {"tag": "div", "class_token": "article"},              "min_text": 500},
    {"lookup": {"tag": "article"},                                    "min_text": 500},
    {"lookup": {"attr_name": "role", "attr_value": "main"},           "min_text": 500},
]

# Reader-mode-only widget strip. Match SPA-blog inline widgets that
# `.entry` / `<article>` wrappers commonly include alongside the post body
# — vc.ru's `<div class="entry">` contains the article PLUS recommendation
# carousels, comments threads, and emoji-reaction bars all as siblings.
# Without this strip, reader-mode picks `.entry` correctly but the resulting
# PDF still has 3-4× the legitimate text plus tail emoji counters.
#
# Substring matching via class= contains (mirror of CSS [class*=KEYWORD]) —
# catches plurals and compound forms (`reaction` matches `content__reactions`,
# `reactions-bar`, `like-reaction`). Generic words (`sidebar`, `widget`,
# `share`, `meta`, `tags`) are EXCLUDED because they appear in BEM modifier
# positions on Habr (e.g. `tm-page__main_has-sidebar` is the MAIN article
# wrapper, not a sidebar). Use compound forms (`share-button`, `post-meta`)
# to target actual widget classes.
#
# Honest scope: substring matching can over-strip on niche articles where the
# topic literally mentions the keyword (e.g. a chemistry article with
# `<figure class="reaction-diagram">`). Reader-mode is an opt-in degraded view.
_READER_STRIP_KEYWORDS: list[str] = [
    # Recommendation widgets / related-articles blocks
    "rotator", "recommend", "related-post", "related-article",
    # Comment threads (whole section)
    "comments", "discussion-list", "replies-list",
    # Post-footer meta widgets: tags, share, subscribe
    "post-meta", "entry-meta", "post-tags", "entry-tags",
    "post-share", "entry-share", "share-button", "share-bar",
    "social-share", "social-button",
    "subscribe-block", "subscribe-form", "newsletter",
    # vc.ru-style article-footer engagement widgets: emoji reactions
    # (`.content__reactions`), floating engagement bar
    # (`.content__floating`), and post-footer with comment-counter +
    # share buttons. Same patterns appear on generic blogs as
    # `.entry-footer` / `.post-footer`.
    "reaction", "floating-bar", "floating-engage",
    "content-footer", "post-footer", "entry-footer",
    # Ad / promo / sponsored blocks
    "ad-banner", "ad-block", "advert", "sponsor-block",
    "promo-block", "ya-ai",
    # Cookie / GDPR consent prompts
    "cookie-banner", "cookie-consent", "gdpr-",
]

# Bare `<main>` body-ratio threshold: if `<main>` text is ≥95% of the
# original `<body>` text, `<main>` is wrapping the entire site (chrome
# included) and we reject it. Calibrated empirically — mobile-review's
# article-only `<main>` is ~89% of body; chrome-wrapping `<main>` on
# tested SPA blogs sits at 96-99%.
_MAIN_BODY_RATIO_MAX = 0.95


# ───────────────────────── pdf-9: SPA-chrome heuristic ─────────────────────

# Structural SPA-detection thresholds (NO framework strings — pure shape).
# A page is treated as "SPA chrome wrapping content" when ANY of:
#   * <body> HTML payload ≥ 50 KB (heavy hydrated DOM)
#   * ≥ 5 <script src=…> tags (hydrated bundle; bundle-size threshold below)
#   * ≥ 3 ARIA-landmark elements (role="navigation|complementary|banner|
#     contentinfo|main")
# Calibrated against 7 real fixtures: Gmail (4.7 MB body, 4 landmarks),
# ELMA365 activities (1.6 MB, no roles but heavy SPA), Sentora Framer
# (316 KB, no landmarks), Yandex Cloud Console (190 KB, no landmarks).
# Blog platforms (Confluence, GitBook, vc.ru, Habr) typically have
# <body> 30-100 KB so the script-count rule is the discriminator.
_SPA_BODY_BYTES_MIN     = 50 * 1024
_SPA_SCRIPT_COUNT_MIN   = 5
_SPA_LANDMARK_COUNT_MIN = 3

# ARIA roles we strip as chrome (universal, vendor-agnostic). Role="main"
# is INTENTIONALLY NOT in this set — we *want* to preserve the main region
# (and prefer it for content extraction).
_SPA_STRIP_ROLES = (
    "navigation", "complementary", "banner", "contentinfo", "search",
    "alert", "alertdialog", "dialog",
)

# Semantic landmark tags stripped as chrome. `<header>` is depth-restricted
# in `_strip_spa_chrome_tags` (depth ≤ 2) to avoid stripping in-article
# section headers; the others are stripped wherever they occur.
_SPA_STRIP_TAGS = ("aside", "nav", "footer")
_SPA_STRIP_TAGS_SHALLOW = ("header",)   # only at <body> depth ≤ 2

# Inline `position:fixed` chrome heuristic: an element with style="… position:
# fixed …" containing very little text is likely a toast/banner overlay (Gmail
# loader splash, Confluence cookie strip, "download desktop app" promo).
_SPA_FIXED_TEXT_MAX = 200

# Promo/banner button-text patterns — vendor-agnostic close-buttons. An
# element containing a button/link with this text and total ≤ 200 chars of
# prose is treated as a promo banner. Catches "× / Закрыть / Dismiss /
# Close / Got it / OK".
_SPA_PROMO_BUTTON_RE = re.compile(
    r">\s*(?:×|✕|Close|Dismiss|Закрыть|Got it|OK|Понятно|Skip)\s*<",
    re.IGNORECASE,
)


def _count_landmarks(html: str) -> int:
    """Count ARIA-landmark roles + semantic landmark tags in the document.

    Used by SPA-detection: a page with ≥ _SPA_LANDMARK_COUNT_MIN distinct
    landmark elements is a chrome+content SPA (Gmail = 4: main, navigation,
    complementary, banner). Landmark-poor SPAs (Yandex Cloud, Framer
    blogs) trigger SPA-detection through other gates.
    """
    n = 0
    for m in ANY_OPEN_RE.finditer(html):
        tag = m.group(1).lower()
        attrs = m.group(2) or ""
        if tag in {"main", "aside", "nav", "header", "footer"}:
            n += 1
            continue
        role = get_attr(attrs, "role")
        if role and role.strip().lower() in {
            "main", "navigation", "complementary", "banner", "contentinfo",
        }:
            n += 1
    return n


def _is_spa(html: str) -> bool:
    """Detect whether the input is a hydrated SPA (chrome + content) vs a
    plain article page.

    Three OR'd structural rules (no framework strings — Angular, React,
    Vue, Svelte all trigger the same path):

      1. body HTML ≥ 50 KB (heavy hydrated DOM)
      2. ≥ 5 <script src=…> tags (bundled SPA)
      3. ≥ 3 ARIA-landmarks (typical SPA shell)

    Calibrated against 7 fixtures + the existing blog-platform regression
    set; blog pages (Confluence, GitBook, vc.ru, Habr) trigger 0 of the
    three conditions and follow the existing reader-mode path.
    """
    body_m = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    body_html = body_m.group(1) if body_m else html
    if len(body_html.encode("utf-8")) >= _SPA_BODY_BYTES_MIN:
        return True
    n_scripts = len(re.findall(
        r'<script\b[^>]*\bsrc\s*=', html, re.IGNORECASE,
    ))
    if n_scripts >= _SPA_SCRIPT_COUNT_MIN:
        return True
    if _count_landmarks(html) >= _SPA_LANDMARK_COUNT_MIN:
        return True
    return False


def _strip_spa_aria_chrome(html: str) -> str:
    """Strip elements whose role= matches a chrome-landmark role.

    Role-by-role matching: each role gets its own pass via
    `find_all_elements(attr_name="role", attr_value=ROLE)`. Outermost-only
    splice (mirror of `_strip_reader_widgets`) so nested chrome doesn't
    cause double-removal.
    """
    matches: list[tuple[int, int]] = []
    for role in _SPA_STRIP_ROLES:
        matches.extend(find_all_elements(html, attr_name="role", attr_value=role))
    if not matches:
        return html
    matches.sort(key=lambda se: (se[0], -se[1]))
    outer: list[tuple[int, int]] = []
    last_end = -1
    for s, e in matches:
        if s >= last_end:
            outer.append((s, e))
            last_end = e
    out = html
    for s, e in reversed(outer):
        out = out[:s] + out[e:]
    return out


def _strip_spa_chrome_tags(html: str) -> str:
    """Strip `<aside>`, `<nav>`, `<footer>` outright; `<header>` only at
    shallow depth (≤ 2) so in-article section headers survive.

    The shallow-only rule for `<header>` matters because article HTML
    legitimately contains `<header>` elements as section headers — Habr
    posts wrap each H2 section in `<header>...<h2>...</h2></header>`.
    Only top-level `<header>` (immediate child of `<body>` or single
    nested div) is page chrome.
    """
    # Pass 1: strip ALL of _SPA_STRIP_TAGS at any depth.
    matches: list[tuple[int, int]] = []
    for tag in _SPA_STRIP_TAGS:
        matches.extend(find_all_elements(html, tag=tag))

    # Pass 2: strip _SPA_STRIP_TAGS_SHALLOW only when their start offset
    # falls within the first ~5% of the document OR when they're the
    # outermost matches (depth ≤ 2 from `<body>`). Approximation: if a
    # `<header>` is among the first 3 outermost block-level elements after
    # `<body>`, treat it as shallow. Implemented via a simple offset
    # threshold against the body-start offset — works for chrome `<header>`
    # which always sits near the top of the body.
    body_m = re.search(r"<body[^>]*>", html, re.IGNORECASE)
    body_offset = body_m.end() if body_m else 0
    body_len    = len(html) - body_offset
    shallow_cutoff = body_offset + max(2048, body_len // 10)
    for tag in _SPA_STRIP_TAGS_SHALLOW:
        for s, e in find_all_elements(html, tag=tag):
            if s <= shallow_cutoff:
                matches.append((s, e))

    if not matches:
        return html
    matches.sort(key=lambda se: (se[0], -se[1]))
    outer: list[tuple[int, int]] = []
    last_end = -1
    for s, e in matches:
        if s >= last_end:
            outer.append((s, e))
            last_end = e
    out = html
    for s, e in reversed(outer):
        out = out[:s] + out[e:]
    return out


def _strip_spa_fixed_overlays(html: str) -> str:
    """Strip elements with inline `position:fixed/sticky` and ≤ 200 chars text.

    Catches "Download Desktop App" banners, cookie strips, toast
    notifications, splash loaders. Vendor-agnostic — the rule is that any
    fixed-positioned overlay carrying very little prose is chrome
    (Gmail's loading-explosion div has 0 prose; ELMA365 desktop banner
    has ~80 chars; Confluence cookie strip ~150).

    Higher text counts are deliberately left in place — a fixed-positioned
    article header (rare but legit) might exceed 200 chars.
    """
    out = html
    pat = re.compile(
        r'<(?P<tag>[a-zA-Z][a-zA-Z0-9-]*)\s[^>]*style\s*=\s*["\'][^"\']*'
        r'position\s*:\s*(?:fixed|sticky)[^"\']*["\'][^>]*>',
        re.IGNORECASE,
    )
    matches: list[tuple[int, int]] = []
    for m in pat.finditer(out):
        tag = m.group("tag").lower()
        elements = find_all_elements(out, tag=tag)
        for s, e in elements:
            if s != m.start():
                continue
            if text_length(out[s:e]) <= _SPA_FIXED_TEXT_MAX:
                matches.append((s, e))
            break
    if not matches:
        return out
    matches.sort(key=lambda se: (se[0], -se[1]))
    outer: list[tuple[int, int]] = []
    last_end = -1
    for s, e in matches:
        if s >= last_end:
            outer.append((s, e))
            last_end = e
    for s, e in reversed(outer):
        out = out[:s] + out[e:]
    return out


def _largest_contentful_subtree(html: str) -> str:
    """Best-effort content extraction for landmark-free SPAs.

    Scans `<main>` and `<div>` elements in the body, scores each by
    (text_length × depth-weighted text-density), and returns the
    highest-scoring subtree's HTML (clipped to the original
    `<body>...</body>` if found).

    `<main>` is included as a candidate (in addition to `<div>`) so
    that SPAs which DO have a semantic root (e.g. Yandex Cloud
    Console: `<main class="app-wrap">` wrapping multiple sibling
    content sections — description, advantages, pricing) prefer it
    over picking just one of those sibling subtrees. Without this,
    on ya_browser the heuristic landed on a single feature-list
    subtree and missed the title + intro + pricing options.

    "Honest scope" path — for ya_browser-class SPAs (zero ARIA, zero
    semantic landmarks beyond `<main>`, just `<div>`-soup), this is
    the last fallback before returning the full body. May include
    sidebar text if it competes with main content for density.
    Documented in pdf-9 spec.
    """
    body_m = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    if not body_m:
        return html

    # VDD-adversarial fix: density-weighted scoring (text × text/size)
    # systematically picked small dense subsections over larger parents
    # that contain ALL article sections. On ya_browser the heuristic
    # landed on one feature paragraph (1.5KB / dense) instead of the
    # 22KB `cc-marketplace-product-detail-v2-content` wrapper holding
    # title + description + advantages + pricing.
    #
    # New scoring: maximize TEXT LENGTH directly. Chrome was already
    # stripped via `_spa_chrome_pipeline`, so density isn't needed to
    # distinguish prose from nav anymore. The text-richest qualifying
    # subtree is the closest approximation to the full article body.
    # `<main>` keeps its 2× bonus.
    candidates = []
    for s, e in find_all_elements(html, tag="main"):
        if s < body_m.start() or e > body_m.end():
            continue
        size = e - s
        if size < 1024:
            continue
        tl = text_length(html[s:e])
        if tl < 200:
            continue
        candidates.append((tl * 2, s, e, tl))

    for s, e in find_all_elements(html, tag="div"):
        if s < body_m.start() or e > body_m.end():
            continue
        size = e - s
        if size < 1024:
            continue
        tl = text_length(html[s:e])
        if tl < 200:
            continue
        candidates.append((tl, s, e, tl))

    if not candidates:
        return body_m.group(1)
    candidates.sort(reverse=True)
    _, s, e, _ = candidates[0]
    return html[s:e]


def _spa_chrome_pipeline(html: str) -> str:
    """Run all three SPA-chrome strip passes (ARIA, landmark tags, fixed
    overlays) in order. Idempotent — safe to call on already-stripped HTML.
    """
    html = _strip_spa_aria_chrome(html)
    html = _strip_spa_chrome_tags(html)
    html = _strip_spa_fixed_overlays(html)
    return html


def _candidate_score(fragment: str, title: str) -> int:
    """Score a candidate root for max-pick: text-length × title-match bonus.

    Returns an integer "weight" comparable across candidates. Bonus tier:
    if the candidate's first ≤ 200 chars of plain text contain ≥ 8
    consecutive characters of the page `<title>`, multiply by 4.
    Otherwise return raw text-length.

    The 8-char threshold filters incidental matches (single words like
    "Gold" that appear in many articles on a finance feed) while still
    catching real title echoes ("XAUUSD – Bearish Rejection" — 25 chars
    of overlap with the page title).

    Universal — works on any page where the SAVED title contains the
    article's heading, regardless of platform. No vendor heuristic.
    """
    base_len = text_length(fragment)
    if not title or not fragment:
        return base_len
    # Take the first ~200 chars of plain text from the fragment as the
    # heading region (cheap surrogate for "the article's H1/title").
    plain = re.sub(r"<[^>]+>", " ", fragment[:4000])
    plain = re.sub(r"\s+", " ", plain).strip()
    head_region = plain[:200]
    # Find the longest common substring of head_region and title.
    longest = _longest_common_substring(head_region, title)
    if len(longest) >= 8:
        return base_len * 4
    return base_len


def _longest_common_substring(a: str, b: str) -> str:
    """Find the longest substring present in both `a` and `b`.

    O(n × m) DP — small `head_region` (≤ 200) × small `title` (≤ 200)
    ≈ 40K cells per comparison, runs once per candidate. Acceptable
    for the scoring path.
    """
    if not a or not b:
        return ""
    n, m = len(a), len(b)
    # Single 1D row to keep memory O(min(n, m)) — typical title 50-100
    # chars so 100 ints per row.
    prev = [0] * (m + 1)
    best_len = 0
    best_end_a = 0
    for i in range(1, n + 1):
        curr = [0] * (m + 1)
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > best_len:
                    best_len = curr[j]
                    best_end_a = i
        prev = curr
    return a[best_end_a - best_len:best_end_a]


def _strip_reader_widgets(html: str) -> str:
    """Remove elements whose class= attr contains any _READER_STRIP_KEYWORDS substring.

    Outermost-only: when a stripped element contains another stripped element,
    only the outer one is removed (the inner range is already gone). Splices
    from the END of the document backwards so offsets remain valid.
    """
    matches = find_all_elements(html, class_substring_any=_READER_STRIP_KEYWORDS)
    if not matches:
        return html
    matches.sort(key=lambda se: (se[0], -se[1]))
    outer: list[tuple[int, int]] = []
    last_end = -1
    for s, e in matches:
        if s >= last_end:
            outer.append((s, e))
            last_end = e
    out = html
    for s, e in reversed(outer):
        out = out[:s] + out[e:]
    return out


def reader_mode_html(html: str) -> str:
    """Extract main article content and return a clean HTML document.

    Pipeline:
      1. Snapshot body-text length BEFORE the widget strip — the bare-`<main>`
         body-ratio guard compares against the original body, otherwise the
         empirically-calibrated 0.95 threshold drifts as the keyword list grows.
      2. Strip widget keywords (recommendation carousels, share bars, comment
         threads, etc.) from the full document — vc.ru's `.entry` wrapper
         contains them as siblings of the article body, so they survive the
         later root-extraction step unless removed first.
      3. Walk `_READER_CANDIDATES` in priority order; within each row pick the
         LONGEST qualifying match (handles archive pages with multiple
         `.entry` divs and Disqus comment threads).
      4. If nothing matched, try bare `<main>` with body-ratio guard.
      5. Fall back to the full HTML if still nothing qualifies.

    The returned document keeps the original `<head>` (for charset/lang) but
    strips `<link rel=stylesheet>` and `<script>` tags so the PDF is rendered
    with only the bundled default CSS and NORMALIZE_CSS — clean, consistent
    typography free of site-specific layout rules.
    """
    body_text_len = body_text_length(html)
    html = _strip_reader_widgets(html)

    # pdf-9: SPA-chrome strip BEFORE root selection. If the input is a
    # hydrated SPA (Gmail / ELMA365 / Yandex Cloud / generic Angular-
    # React-Vue app), strip ARIA-landmark roles, semantic chrome tags
    # (<aside>, <nav>, <footer>, shallow <header>), and inline fixed-
    # position overlays with little text. This runs IN ADDITION to the
    # existing widget strip — _READER_STRIP_KEYWORDS is class-based
    # (vc.ru/Habr blogs), this is structural (any SPA framework).
    spa_detected = _is_spa(html)
    if spa_detected:
        html = _spa_chrome_pipeline(html)

    # Extract the page title once for the title-match tie-breaker. On
    # feed/listing pages (TradingView ideas, RSS-like Discord/forum
    # archives, blog index pages) multiple `<article>` siblings sit at
    # comparable text length; the user's intended target is the one whose
    # heading echoes the saved page's `<title>`. Without the tie-break,
    # `max(qualifying, key=length)` picks an arbitrary "longest article"
    # which on a feed page tends to be a recommended/recent post rather
    # than the actual focus.
    title_m = re.search(r"<title[^>]*>([^<]*)</title>", html, re.IGNORECASE)
    title_text = (title_m.group(1) if title_m else "").strip()

    best = ""
    selector_used = ""
    for cand in _READER_CANDIDATES:
        matches = find_all_elements(html, **cand["lookup"])
        if not matches:
            continue
        qualifying = [
            (s, e) for s, e in matches
            if text_length(html[s:e]) >= cand["min_text"]
        ]
        if not qualifying:
            continue
        s, e = max(
            qualifying,
            key=lambda se: _candidate_score(html[se[0]:se[1]], title_text),
        )
        best = html[s:e]
        selector_used = repr(cand["lookup"])
        break

    if not best:
        # Bare `<main>` with body-ratio guard. HTML5 forbids multiple `<main>`
        # per document but real-world pages violate this — prefer the FIRST
        # `<main>` satisfying the guard. Note: post SPA-chrome strip, the
        # body-ratio is computed against the ORIGINAL body length (snapshot
        # at top of function), so the 0.95 threshold means "<main> is most
        # of the post-strip body" rather than "of the original chrome+body".
        for s, e in find_all_elements(html, tag="main"):
            t_len = text_length(html[s:e])
            if t_len >= 500 and t_len / body_text_len < _MAIN_BODY_RATIO_MAX:
                best = html[s:e]
                selector_used = f"main (body-ratio<{_MAIN_BODY_RATIO_MAX})"
                break

    if not best and spa_detected:
        # pdf-9 final fallback for landmark-free SPAs (ya_browser-class):
        # zero ARIA roles, zero semantic landmark tags, zero <main>. Pick
        # the largest contentful subtree by text-length × density. Honest
        # scope: best-effort, sidebar text may bleed into output.
        best = _largest_contentful_subtree(html)
        if best and best != html:
            selector_used = "spa-largest-contentful-subtree"

    if not best:
        return html  # nothing qualified: return unchanged (full HTML + CSS)

    # Strip site-injected styling from the extracted article body. Reader
    # mode renders with only DEFAULT_CSS + NORMALIZE_CSS for clean,
    # consistent typography — site stylesheets reintroduce the chrome we
    # are trying to remove. Universal across sites:
    #
    #   * <style> blocks survive head-strip below; sites also embed style
    #     blocks INSIDE the article body (Confluence's tablesorter, GitHub
    #     <details>, etc.) which paint grey rounded rectangles on table
    #     headers, button-shaped <th>s, "copy heading link" hover targets.
    #   * <button> elements are NEVER article content — they're voting
    #     widgets (Хабр), share/anchor toggles (Confluence), navigation
    #     ("back to top", prev/next), "copy code" overlays. Default <button>
    #     styling renders as a grey rounded rectangle when the site CSS is
    #     stripped, so they appear as visible blank pills next to headings
    #     and at article boundaries.
    #   * Inline `style="..."` attributes on tags inside the body that
    #     reference colors / backgrounds / fonts can also leak; we keep
    #     them for now (some are legitimate, e.g. cell alignment) and rely
    #     on NORMALIZE_CSS overriding the worst offenders with !important.
    best = re.sub(
        r"<style\b[^>]*>.*?</style>",
        "",
        best,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # NB: <button>/<video>/<audio>/<iframe> chrome strip is handled by
    # `preprocess._strip_interactive_chrome` in `preprocess_html` (universal
    # — applies in regular mode too). No reader-specific duplicate needed here.

    # Preserve original <head> for charset/lang but strip ALL external CSS
    # AND inline <style> blocks. Reader mode uses only our bundled default
    # CSS + NORMALIZE_CSS so the PDF has clean, consistent typography
    # regardless of source site.
    head_m = re.search(r"<head[^>]*>.*?</head>", html, re.DOTALL | re.IGNORECASE)
    if head_m:
        head = re.sub(
            r"<(link|script|style)\b[^>]*>(?:.*?</\1>)?",
            "",
            head_m.group(0),
            flags=re.DOTALL | re.IGNORECASE,
        )
    else:
        head = '<head><meta charset="utf-8"></head>'

    print(f"html2pdf: reader-mode root via {selector_used}", file=sys.stderr)
    return f"<!DOCTYPE html>\n{head}\n<body>\n{best}\n</body>\n</html>"

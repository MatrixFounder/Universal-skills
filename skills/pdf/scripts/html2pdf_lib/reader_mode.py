"""Reader-mode article extraction (Safari Reader View parity).

Walks a tiered priority list of article-root selectors (Confluence /
wiki conventions first, generic semantic tags last), strips known widget
classes (recommendation carousels, comment threads, share bars), and
returns a clean DOCTYPE + minimal `<head>` + extracted body. Reader mode
renders with only the bundled DEFAULT_CSS + NORMALIZE_CSS for consistent
typography across sites.
"""
from __future__ import annotations

import re
import sys

from .dom_utils import body_text_length, find_all_elements, text_length

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
        s, e = max(qualifying, key=lambda se: se[1] - se[0])
        best = html[s:e]
        selector_used = repr(cand["lookup"])
        break

    if not best:
        # Bare `<main>` with body-ratio guard. HTML5 forbids multiple `<main>`
        # per document but real-world pages violate this — prefer the FIRST
        # `<main>` satisfying the guard.
        for s, e in find_all_elements(html, tag="main"):
            t_len = text_length(html[s:e])
            if t_len >= 500 and t_len / body_text_len < _MAIN_BODY_RATIO_MAX:
                best = html[s:e]
                selector_used = f"main (body-ratio<{_MAIN_BODY_RATIO_MAX})"
                break

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

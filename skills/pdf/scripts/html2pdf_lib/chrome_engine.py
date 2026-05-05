"""Chrome-engine HTML→PDF renderer (Playwright + bundled Chromium).

VDD-fix note (post-pdf-11 v1): the naive implementation broke on real
webarchives because Chrome's URL resolution differs from weasyprint's.
weasyprint takes a `base_url` parameter and uses it for relative-URL
resolution, ignoring any `<base>` tag in the HTML. Chrome (correctly
per HTML spec) honours the `<base href>` tag — and webarchives almost
always have `<base href="https://original-site.com/">` because that's
what the browser saw when the archive was made. Result: every relative
`<link rel="stylesheet" href="styles.css">` resolves to `https://
original-site.com/styles.css`, which our offline route handler blocks
→ page renders without CSS → layout collapses (tabs become inline
text, sidebars overlap). Fix: strip the `<base>` tag before handing
HTML to Chrome (`_strip_base_href`). Chrome then falls back to the
document's URL (our `file:///tmp/__html2pdf_chrome.html`) as the base,
and relative refs resolve to local extracted assets.

Opt-in alternative to weasyprint for cases where weasyprint's layout engine
fails or produces poor output:

  * Material 3 / Polymer pages with deep `calc()` + `var()` chains
    (Gmail-style web apps trigger weasyprint's NumberToken bug).
  * Heavy SPA layouts where weasyprint's box-layout engine hangs (Framer
    builder bundles, vc.ru-style nested flex/grid).
  * Pages with proprietary font stacks where weasyprint produces garbled
    glyphs even after CDN font-face stripping.

Trade-offs vs. weasyprint:
  + Real browser engine — renders modern CSS faithfully (grid, calc, fonts).
  + Handles JavaScript (waits for `networkidle`).
  + No layout pathology timeouts.
  − Heavyweight: ~150 MB Chromium binary (opt-in install).
  − Slower: 1-3s per page including browser startup.
  − Network access by default — must be controlled to stay offline.

Honest scope:
  * This engine renders the HTML as the browser sees it. We do NOT apply
    weasyprint compatibility fixes (calc-strip, font-face-strip, NORMALIZE_CSS) —
    those are workarounds for weasyprint bugs that Chrome doesn't have.
  * Reader-mode (`reader_mode_html`) IS applied before the engine, since that's
    a content-extraction step orthogonal to rendering.
  * Network is BLOCKED by default — sub-resources must be inlined or
    extracted to the base_url directory. This matches the offline-rendering
    model of weasyprint via `_offline_url_fetcher`.

Layout (where this fits in the pipeline):

    html2pdf.py CLI
        ↓ --engine chrome
    render.convert(..., engine="chrome")
        ↓
    chrome_engine.render_chrome(...)
        ↓
    Playwright sync_api → headless Chromium → page.pdf()
"""
from __future__ import annotations

import re
from pathlib import Path

# Layout-normalisation CSS injected into every chrome-rendered page.
#
# Problem: SPAs are designed for a fixed-viewport screen interaction —
# `<html style="height: 100%">`, `<body style="height: 100vh; overflow:
# hidden">`, content inside `<main style="overflow: auto">`. When the
# user scrolls, the inner container scrolls; the outer html/body never
# grow. Chrome's `page.pdf()` paginates the document, BUT the document
# height is clamped to the viewport because of these `100vh`/`overflow:
# hidden` rules. Result: only the visible viewport-sized slice ends up
# in the PDF; the rest of the email / activity list / SPA content is
# cut off.
#
# Fix strategy:
#
#   1. **Release html/body** — outer-frame height/overflow clamping is
#      always wrong for PDF rendering; the document MUST grow with its
#      content for chrome to paginate correctly.
#
#   2. **Universal `* { overflow: visible !important; max-height: none
#      !important }`** — required because real-world SPAs use diverse
#      scroll-container patterns: inline-style absolute-positioned
#      wrappers (Gmail's `explosion_clipper_div`), class-based scroll
#      containers (Material Design), nested overflow:hidden chains.
#      A targeted attribute selector misses class-based patterns; a
#      `body > *` selector misses inner scrollers. Universal release
#      is the only rule that catches all three SPA archives we
#      validated (Gmail 4.7 MB main, ELMA365 1.6 MB Angular shell,
#      ya_browser 190 KB Yandex Cloud Console).
#
# Honest scope (real trade-off, validated empirically):
#
#   * Sidebars that hide text labels via `overflow: hidden` (Yandex
#     Cloud Console icon-only nav, with its EXPANDED state hidden by
#     a clipping ancestor) WILL leak their labels. Visible side
#     effect: text labels overlap main content area in the PDF.
#   * Carousels with `overflow: hidden` to show one slide at a time
#     will expand to show all slides at once.
#   * Rounded-corner clipping via `overflow: hidden` will be lost.
#
# The alternative (omit the `*` rule) was tried and rejected:
# Gmail truncated to 1 page, ELMA365 cut content. The PDF user wants
# the full archive content visible — sidebar-label cosmetic overlap
# is the lesser harm.
#
# Recommendations (per content type, see references/html-conversion.md):
#   * Article/email/newsletter archives → `--engine chrome --reader-mode`
#     (extract main content first, then chrome render — sidesteps the
#     trade-off entirely).
#   * Dashboard / data registry archives → `--engine chrome` alone
#     (chrome's `*-overflow` release is the right call; sidebar leak
#     is acceptable).
#   * Static marketplace pages where weasyprint already renders well
#     (ya_browser-class) → use the default `weasyprint` engine, not
#     chrome — no overflow release needed and no trade-off.
_LAYOUT_NORMALIZE_CSS = """\
<style id="__html2pdf_chrome_layout_normalize">
html, body {
  height: auto !important;
  min-height: 0 !important;
  max-height: none !important;
  overflow: visible !important;
}
* {
  overflow: visible !important;
  max-height: none !important;
}
</style>
"""


# `<base href="...">` matcher. We strip the tag entirely (rather than
# rewriting its href) because chrome will fall back to the document's
# URL — which is the file:// URL we control — for relative resolution.
# Pattern is intentionally lax: HTML5 allows `<base>` to be self-closing
# or unclosed, with arbitrary attribute order, single or double quotes.
_BASE_TAG_RE = re.compile(r"<base\b[^>]*>", re.IGNORECASE)


def _strip_base_href(html: str) -> str:
    """Remove every `<base>` tag from the HTML.

    Webarchives saved by Safari/Chrome typically embed `<base href="https
    ://original-site.com/">` so that the saved DOM still resolves
    relative URLs against the live site. When we open the archive locally
    via `file://`, we want relative URLs to resolve against the local
    extraction tempdir (where archives.py wrote the sub-resources) — the
    `<base>` tag would override that and route every CSS/script reference
    to the original https:// origin, which our offline route handler
    blocks.

    Multiple `<base>` tags are technically illegal per HTML spec but we
    handle them anyway (defensive). Returns html unchanged if no `<base>`
    tag is present (fast path — most plain .html inputs).
    """
    if "<base" not in html.lower():
        return html
    return _BASE_TAG_RE.sub("", html)


# Page sizes follow the Playwright `page.pdf(format=...)` convention
# (capitalized). weasyprint uses CSS @page strings (lowercase + units);
# our CLI takes lowercase keys ("letter"/"a4"/"legal") and each engine
# maps to its own native format.
_CHROME_PAGE_SIZES = {
    "letter": "Letter",
    "a4": "A4",
    "legal": "Legal",
}


class ChromeEngineUnavailable(RuntimeError):
    """Raised when the chrome engine is requested but Playwright isn't installed.

    The CLI catches this and emits a concrete remediation message pointing
    the user at `install.sh --with-chrome` or `pip install playwright &&
    playwright install chromium`.
    """


def _import_playwright():
    """Import Playwright lazily; raise ChromeEngineUnavailable on failure.

    Playwright is an optional dependency (separate `requirements-chrome.txt`).
    Default installs do NOT pull in the ~150 MB Chromium binary. We delay
    the import so a user who never touches `--engine chrome` doesn't pay
    the import-error cost on every CLI invocation.
    """
    try:
        from playwright.sync_api import (  # type: ignore
            Error as PlaywrightError,
            TimeoutError as PlaywrightTimeoutError,
            sync_playwright,
        )
    except ImportError as exc:
        raise ChromeEngineUnavailable(
            "Playwright is not installed. To enable the chrome engine, run:\n"
            "  cd skills/pdf/scripts && bash install.sh --with-chrome\n"
            "or manually:\n"
            "  ./.venv/bin/pip install -r requirements-chrome.txt && "
            "./.venv/bin/playwright install chromium"
        ) from exc
    return sync_playwright, PlaywrightTimeoutError, PlaywrightError


def _block_remote_routes(route, request):
    """Playwright route handler — block remote network, allow local schemes.

    Mirrors weasyprint's `_offline_url_fetcher` policy: file:// and data:
    URLs pass through, http(s):// requests are aborted. Subresources baked
    into the archive (extracted to base_url) load fine; CDN fonts and
    tracking pixels are dropped silently.

    `request.resource_type` could narrow this further (e.g., allow images
    but block scripts) but we want behavioural parity with the weasyprint
    path: any remote fetch refused.
    """
    url = request.url
    if url.startswith(("file://", "data:", "about:")):
        route.continue_()
    else:
        route.abort()


def _resolve_temp_html_path(base_url: str) -> Path:
    """Pick a writable location for the preprocessed HTML.

    Strategy:
      1. If `base_url` is a file:// URL pointing to a directory we can write
         to (the typical archive-extraction case), write there. This keeps
         relative refs in the HTML resolving naturally.
      2. Else, fall back to a system tempdir AND copy `base_url`'s contents?
         No — that's expensive and asset-fragile. We just write to system
         tempdir and accept that relative refs may break for plain .html
         inputs whose directory we can't write to (rare; emit warning).

    For v1 we always try (1); failures bubble up as IOError and the CLI
    reports them. This covers archive inputs (where base_url is always a
    fresh temp dir we own) and well-behaved plain .html inputs.
    """
    if base_url.startswith("file://"):
        candidate = Path(base_url[len("file://"):])
    else:
        candidate = Path(base_url)
    if candidate.is_dir():
        return candidate / "__html2pdf_chrome.html"
    # base_url points to a file (rare for our pipeline but possible);
    # write next to it.
    return candidate.parent / "__html2pdf_chrome.html"


# Why JavaScript is OFF by default
# --------------------------------
# Webarchives and MHTML are static snapshots — by the time the user saves
# the page, the HTML already represents the rendered state of the SPA.
# Re-running the embedded JS with network access blocked produces TWO
# common failure modes that we observed empirically on real fixtures
# (VDD adversarial round, post-pdf-11 v1):
#
#   * SPA self-destruction — the page's offline-detection JS sees fetch
#     failures and replaces the body with an error fallback. Real
#     instance: Gmail archive renders "Временная ошибка — ваш аккаунт
#     временно недоступен" instead of the saved inbox.
#
#   * Half-hydrated DOM — Angular/React initializes against the saved
#     HTML, sees backend calls fail, and leaves the layout in a
#     transitional state where horizontal navigation collapses to plain
#     text concatenation, sidebars overlap main content, click handlers
#     paint stale buttons in wrong positions. Real instance: ELMA365
#     activities-fixture renders "ОбзорКонтактыОтношенияЗаметкиАктивности"
#     as a single line of text.
#
# The whole reason chrome engine helps over weasyprint is that Chrome has
# a real modern CSS engine (calc, var, grid, custom properties, container
# queries) — NOT that it executes JavaScript. For static archives, JS
# off is strictly better. For the rare cases where JS-rendered content
# matters (TradingView <canvas> charts, archives that capture pre-
# hydration HTML), `--chrome-js` opts back in.
# Desktop-class viewport so SPAs that branch on `@media (min-width:
# 1024px)` resolve to desktop layout, not a mobile-stack collapse.
# Height matches a typical workstation; the actual pagination math
# happens against `page.pdf(format=...)` regardless of viewport
# dimensions — Playwright re-emulates the page at PDF dimensions
# during the print path, so a tall viewport alone won't unfurl
# inner scroll containers. The CSS in `_LAYOUT_NORMALIZE_CSS`
# handles that.
_DEFAULT_VIEWPORT = {"width": 1280, "height": 1024}


def render_chrome(
    html_text: str,
    output_path: Path,
    *,
    base_url: str,
    page_size: str,
    timeout: int,
    print_background: bool = True,
    javascript: bool = False,
) -> None:
    """Render `html_text` to `output_path` via headless Chromium.

    Args:
      html_text: preprocessed HTML (reader-mode already applied if requested).
      output_path: destination .pdf path.
      base_url: directory whose contents are referenced by relative URLs in
        `html_text`. Typically the archive-extraction tempdir or the input
        HTML's parent. We write the HTML to this directory so file://
        relative resolution works naturally.
      page_size: lowercase CLI key ("letter"/"a4"/"legal").
      timeout: render watchdog deadline in seconds; 0 disables. Mapped to
        Playwright's `goto` and `pdf` timeouts (in ms).
      print_background: pass-through to `page.pdf(print_background=...)`.
        Default True so CSS backgrounds (the typical "looks like the
        browser" expectation) appear in the PDF.
      javascript: if True, execute the page's JavaScript. Default False
        (see module-level rationale): static archives render cleanly
        without JS, and JS-on with offline network typically corrupts
        the DOM (SPA self-destruct, half-hydration). Use True only when
        the saved HTML is pre-hydration or contains canvas charts that
        need JS to draw.

    Raises:
      ChromeEngineUnavailable: Playwright not installed.
      RenderTimeout: Chromium didn't finish within `timeout` seconds.
        Caller (CLI) re-maps this to its own RenderTimeout exception
        type for uniform error envelopes.
    """
    sync_playwright, PlaywrightTimeoutError, _PlaywrightError = _import_playwright()

    # Lazy import: weasyprint isn't on the import path of the chrome engine,
    # so we can't reuse RenderTimeout from render.py without a circular
    # import. We import it here at call time (after Playwright import has
    # succeeded) to keep the dependency direction one-way.
    from .render import RenderTimeout  # noqa: PLC0415

    fmt = _CHROME_PAGE_SIZES.get(page_size, "Letter")
    timeout_ms = max(0, timeout * 1000)  # 0 disables in Playwright too

    # Webarchive HTML usually carries `<base href="https://orig.site/">`
    # which would override our file:// base and send every relative URL
    # to the offline-blocked origin. Strip it so chrome falls back to the
    # document URL we control. (See _strip_base_href docstring.)
    html_text = _strip_base_href(html_text)

    # Inject layout-normalisation CSS (see _LAYOUT_NORMALIZE_CSS docstring
    # at module top). Tears down `100vh`/`overflow:hidden` outer-frame
    # clamping so the document grows with its content and chrome paginates
    # the full archive instead of the viewport-sized slice. Inject at end
    # of <head> so we win specificity ties; if no <head>, prepend.
    if "</head>" in html_text:
        html_text = html_text.replace(
            "</head>", _LAYOUT_NORMALIZE_CSS + "</head>", 1,
        )
    else:
        html_text = _LAYOUT_NORMALIZE_CSS + html_text

    tmp_html = _resolve_temp_html_path(base_url)
    try:
        tmp_html.write_text(html_text, encoding="utf-8")
        url = f"file://{tmp_html.resolve()}"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                # Explicit desktop-class viewport (1280×1024). Default
                # Playwright viewport is 1280×720, but we set it
                # deliberately so SPAs that branch on viewport-width media
                # queries (`@media (min-width: 1024px)`) resolve to the
                # desktop layout, not a mobile-stack collapse. PDF page
                # dimensions come from `format=...` below; Chrome's print
                # path scales the laid-out content onto the PDF page,
                # similar to a real browser's print dialog.
                context = browser.new_context(
                    viewport=_DEFAULT_VIEWPORT,
                    java_script_enabled=javascript,
                )
                context.route("**/*", _block_remote_routes)
                page = context.new_page()
                try:
                    # `wait_until="load"` (not "networkidle") because we
                    # block network — networkidle waits for 500 ms of zero
                    # in-flight requests, which always fires immediately
                    # under our route blocker, but `load` is more semantic.
                    page.goto(url, wait_until="load", timeout=timeout_ms)
                    # Force `media: screen` BEFORE page.pdf(). Default
                    # behaviour of `page.pdf()` is to call
                    # `emulate_media({media: "print"})`, which switches
                    # the page to its `@media print` stylesheet. Modern
                    # SPAs (ELMA365 Angular, ya_browser, anything React/
                    # Material) ship `@media print` rules that hide
                    # navigation tabs, collapse sidebars, and reset
                    # absolute positioning — designed for clean
                    # paper-style printing of pre-rendered articles, not
                    # for archiving the SPA-as-the-user-saw-it. Result:
                    # tabs collapse to plain-text concatenation
                    # ("ОбзорКонтактыОтношения…"), sidebars overlap main
                    # content, the layout looks broken.
                    #
                    # We're rendering archives — the user wants the page
                    # to look like the screen capture, not like a
                    # paper-print. Force media:screen.
                    page.emulate_media(media="screen")
                    page.pdf(
                        path=str(output_path),
                        format=fmt,
                        print_background=print_background,
                        margin={"top": "1cm", "right": "1cm",
                                "bottom": "1cm", "left": "1cm"},
                    )
                except PlaywrightTimeoutError as exc:
                    raise RenderTimeout(
                        f"chrome engine exceeded {timeout}s on {url}: {exc}"
                    ) from exc
                finally:
                    page.close()
                    context.close()
            finally:
                browser.close()
    finally:
        try:
            tmp_html.unlink()
        except OSError:
            pass

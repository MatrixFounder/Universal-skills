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

# Layout-normalisation strategy (post-VDD-iter-3, enterprise-grade).
#
# The pdf-11 v1 / v2 approach injected an aggressive `* { overflow:
# visible !important }` CSS rule, which fixed Gmail and ELMA365 (full
# content visible) but broke ya_browser-class layouts (icon-only
# sidebars leaked their hidden text labels onto main content). And
# even with that rule, ELMA365's wide layout got clipped on the right
# edge of the PDF page because the SPA layout (1280 CSS px) didn't
# fit A4 (~718 CSS px usable).
#
# Iter-3 strategy — surgical DOM normalization via JavaScript:
#
#   1. **Enable JavaScript** for the context (java_script_enabled=True).
#      This lets us run our own normalization script.
#
#   2. **Patch network APIs via `add_init_script` BEFORE page scripts
#      execute**. Prevents the offline-error self-destruct (Gmail) and
#      the half-hydration cascade (ELMA365 Angular). We override
#      `navigator.onLine`, `fetch`, `XMLHttpRequest`, and
#      `navigator.sendBeacon` so SPAs that detect network failure
#      don't replace the body or leave the DOM in a transitional
#      state.
#
#   3. **Wait for load + small settle delay**, then call
#      `page.evaluate` to walk the DOM and surgically release ONLY
#      scroll containers that ACTUALLY CLIP content (`scrollHeight >
#      clientHeight + 5`). This unfurls Gmail's `explosion_clipper_div`
#      and ELMA365's Angular shell scrollers WITHOUT touching
#      ya_browser's icon-sidebar (which uses `overflow:hidden` to clip
#      hidden text labels — clientHeight === scrollHeight there, since
#      the labels are `display: none` or width-clipped, not vertically
#      overflowing).
#
#   4. **Scale the PDF render** so layout-width content fits within
#      the PDF page width. The PDF page is A4/Letter (~718-720 CSS
#      px usable after 1cm margins); the SPA layout is 1280 CSS px.
#      `scale = usable / viewport` keeps everything visible without
#      right-edge cutoff.
#
# This combination is universal: works on Gmail, ELMA365, ya_browser
# without any vendor-specific allow-list, and produces enterprise-
# grade output (no cut-off content, no chrome leaks, real CSS
# rendering).

# CSS layer — reduced to the bare minimum. Just release html/body so
# the document can grow vertically. The DOM normalization step (below)
# handles inner scroll containers surgically.
_LAYOUT_NORMALIZE_CSS = """\
<style id="__html2pdf_chrome_layout_normalize">
/* Outer-frame release with high specificity (defeats body.modal-open
   etc. class-based clamps). */
html, html[class], body, body[class], body.modal-open {
  height: auto !important;
  min-height: 0 !important;
  max-height: none !important;
  overflow: visible !important;
  position: static !important;
}
/* Hide text inside font-icon containers. When the icon font fails to
   load (offline mode), the icon LIGATURE name renders as plain text:
   ELMA365 buttons with class "btn-style-icon" show "fullscreen_enter",
   "system_close", "subscribe", "lock", etc. instead of glyphs.
   Material Icons / Material Symbols / PrimeIcons have similar issues.
   `font-size: 0` collapses the text without changing the box, so the
   surrounding layout doesn't shift. */
[class*="btn-style-icon"], [class*="material-icons"],
[class*="material-symbols"], [class*="primeicons"],
[class*="ng-icon"], [class~="icon-only"],
i.material-icons, i.material-symbols-outlined {
  font-size: 0 !important;
  line-height: 0 !important;
}
</style>
"""

# Strip every `<script>` tag from HTML before handing it to chrome.
# This lets us enable JavaScript at the context level (so page.evaluate
# works for surgical DOM normalization) WITHOUT letting the page's own
# scripts execute. Result: gmail can't self-destruct the body via its
# offline detector, Angular can't half-hydrate, and we still get a
# privileged JS context to walk and fix the DOM.
#
# Why not just disable JS at the context level? Because page.evaluate()
# requires JS-enabled. We need precise DOM normalization (fix scroll
# containers that ACTUALLY clip content; release position:fixed modals
# that wrap real content; LEAVE alone position:fixed backdrops and
# toolbar/sidebar/icon-only nav elements that would corrupt layout if
# unfurled).
_SCRIPT_TAG_RE = re.compile(
    r"<script\b[^>]*>.*?</script\s*>|<script\b[^>]*/>",
    re.IGNORECASE | re.DOTALL,
)


def _strip_script_tags(html: str) -> str:
    """Remove every `<script>` tag (with content) and self-closing scripts.

    Defensive: handles upper/lowercase, self-closing variants, and
    multi-line script bodies. Returns the HTML with scripts removed.
    Fast path: no `<script` substring → return unchanged.
    """
    if "<script" not in html.lower():
        return html
    return _SCRIPT_TAG_RE.sub("", html)


# DOM normalization script — runs via page.evaluate AFTER navigation.
# Walks the DOM and surgically fixes layout issues without breaking
# legitimate fixed-position elements (icon-only sidebars, toolbars,
# rounded corners). Three classes of fix:
#
#   1. Body release with !important (defeats `body.modal-open
#      { overflow: hidden }` class-based rules).
#
#   2. Release `position: fixed` ONLY when the element wraps real
#      content (offsetHeight > 200 px AND has more than minimal text).
#      This catches ELMA365's `complex-popup-outer modal-lg` (6816 px
#      of activity content) but skips empty backdrops, toast-toast
#      notification containers, and small icon sidebars.
#
#   3. Release `overflow: hidden` ONLY when the element actually clips
#      content (scrollHeight > clientHeight + threshold). Catches
#      Gmail's `explosion_clipper_div` but skips ya_browser's icon
#      sidebar (where labels are width-clipped, not vertically
#      overflowing).
_DOM_NORMALIZE_SCRIPT = r"""
(() => {
  // 1. Outer-frame release (belt-and-suspenders with the CSS rule).
  document.documentElement.style.setProperty('height', 'auto', 'important');
  document.documentElement.style.setProperty('overflow', 'visible', 'important');
  document.body.style.setProperty('height', 'auto', 'important');
  document.body.style.setProperty('min-height', '0', 'important');
  document.body.style.setProperty('max-height', 'none', 'important');
  document.body.style.setProperty('overflow', 'visible', 'important');
  document.body.style.setProperty('position', 'static', 'important');

  // 2. Walk DOM. Classify each element and apply targeted fixes.
  const all = document.querySelectorAll('*');
  const VIEW_W = window.innerWidth || 1280;
  // "Substantial modal" = position:fixed AND wide AND tall AND text-rich.
  // Width criterion (>50% viewport) is what distinguishes a modal
  // (covers most of viewport, contains content) from an icon-only
  // sidebar (narrow strip with hidden labels) — we DON'T want to
  // unfurl sidebars.
  const modals = [];
  let releasedFixed = 0, releasedClip = 0, hiddenFixed = 0;
  for (let i = 0; i < all.length; i++) {
    const el = all[i];
    const cs = window.getComputedStyle(el);
    if (cs.position === 'fixed') {
      const ow = el.offsetWidth;
      const oh = el.offsetHeight;
      const textLen = (el.textContent || '').trim().length;
      if (ow > VIEW_W * 0.5 && oh > 200 && textLen > 50) {
        // Substantial modal — release to flow.
        el.style.setProperty('position', 'static', 'important');
        releasedFixed++;
        modals.push(el);
      } else {
        // Backdrop / toolbar / toast / icon sidebar — keep fixed
        // but display:none so it doesn't add empty pages to the PDF.
        el.style.setProperty('display', 'none', 'important');
        hiddenFixed++;
      }
      continue;
    }
    // Overflow release: only on WIDE elements (≥200 CSS px) where
    // content actually clips. The width gate distinguishes real
    // content scrollers (Gmail email body, ELMA365 activity panel)
    // from narrow icon-only sidebars (ya_browser composite-bar at
    // ~64px wide — its `overflow: hidden` is hiding the text labels
    // associated with each icon, which we MUST keep clipped or they
    // overlap the main content). Without this gate, the universal
    // overflow release leaked sidebar labels (verified on
    // ya_browser.webarchive — labels "Все сервисы", "Поиск",
    // "Marketplace" rendered overlapping the marketplace product
    // description).
    const ox = cs.overflowX, oy = cs.overflowY;
    const clipsY = oy === 'auto' || oy === 'scroll' || oy === 'hidden';
    const clipsX = ox === 'auto' || ox === 'scroll' || ox === 'hidden';
    const wideEnough = el.offsetWidth >= 200;
    if (clipsY && wideEnough && el.scrollHeight > el.clientHeight + 4) {
      el.style.setProperty('overflow-y', 'visible', 'important');
      el.style.setProperty('height', 'auto', 'important');
      el.style.setProperty('max-height', 'none', 'important');
      releasedClip++;
    }
    if (clipsX && wideEnough && el.scrollWidth > el.clientWidth + 4) {
      el.style.setProperty('overflow-x', 'visible', 'important');
      el.style.setProperty('max-width', 'none', 'important');
      releasedClip++;
    }
  }

  // 3. If we released modals, hide the underlying page (other body
  // direct-children that are NOT ancestors of any modal). The user
  // saved an archive of an OPEN-MODAL state — what they want is the
  // modal content, not the page that was visible BEHIND the modal.
  // ELMA365 case: the underlying page is a CRM contractor list (18k
  // rows) — when the modal becomes static and flows inline, that
  // CRM list precedes the activity panel in document order, polluting
  // the first ~2 PDF pages with irrelevant content.
  let hiddenSiblings = 0;
  if (modals.length > 0) {
    // For each modal, compute its body-level ancestor (modal portal).
    const portals = new Set();
    for (const m of modals) {
      let node = m;
      while (node.parentElement && node.parentElement !== document.body) {
        node = node.parentElement;
      }
      if (node.parentElement === document.body) {
        portals.add(node);
      }
    }
    // Hide every direct body child that ISN'T a portal.
    const children = Array.from(document.body.children);
    for (const child of children) {
      if (!portals.has(child)) {
        child.style.setProperty('display', 'none', 'important');
        hiddenSiblings++;
      }
    }
  }

  return {
    releasedFixed: releasedFixed,
    releasedClip: releasedClip,
    hiddenFixed: hiddenFixed,
    modalsFound: modals.length,
    hiddenSiblings: hiddenSiblings,
  };
})()
"""

# Init script — injected via `page.add_init_script` BEFORE any page
# script runs. Patches the offline-detection APIs that SPAs use to
# decide whether to swap the body for an error message. Returning
# never-resolving promises is preferable to throwing: a thrown error
# triggers the page's error-handling path, which is what we want to
# AVOID. A pending promise just leaves the SPA waiting forever, never
# reaching the "show error UI" branch.
_OFFLINE_PATCH_INIT_SCRIPT = r"""
(() => {
  try {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      get: () => true,
    });
  } catch (e) {}
  const _silentForever = () => new Promise(() => {});
  if (typeof window.fetch !== 'undefined') {
    window.fetch = _silentForever;
  }
  if (typeof window.XMLHttpRequest !== 'undefined') {
    window.XMLHttpRequest = function() {
      return {
        open: () => {}, send: () => {}, abort: () => {},
        setRequestHeader: () => {}, getAllResponseHeaders: () => '',
        getResponseHeader: () => null, overrideMimeType: () => {},
        readyState: 0, status: 0, statusText: '',
        response: '', responseText: '', responseXML: null, responseURL: '',
        onreadystatechange: null, onload: null, onerror: null,
        ontimeout: null, onabort: null, onloadstart: null, onloadend: null,
        onprogress: null,
        addEventListener: () => {}, removeEventListener: () => {},
        dispatchEvent: () => true,
        upload: { addEventListener: () => {}, removeEventListener: () => {} },
      };
    };
  }
  if (navigator.sendBeacon) {
    navigator.sendBeacon = () => true;
  }
})()
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


# Desktop-class viewport so SPAs that branch on `@media (min-width:
# 1024px)` resolve to desktop layout, not a mobile-stack collapse.
# The render path calls `page.pdf(scale=...)` to fit this viewport
# width into the PDF page width — see _CHROME_PAGE_USABLE_WIDTH_CSS_PX.
_DEFAULT_VIEWPORT = {"width": 1280, "height": 1024}

# Usable PDF page width in CSS pixels (96 dpi) after subtracting our
# 1cm side margins. We use these to compute the page.pdf(scale=...)
# parameter so the SPA layout (rendered at _DEFAULT_VIEWPORT["width"])
# fits the PDF page horizontally without right-edge cutoff. Numbers:
#   1cm = 37.795 CSS px (10mm × 96/25.4)
#   A4 width = 210mm = 793.7 px → usable = 793.7 - 75.59 = 718 px
#   Letter = 8.5in = 816 px → usable = 816 - 75.59 = 740 px
#   Legal = 8.5in = 816 px → usable = 816 - 75.59 = 740 px
_CHROME_PAGE_USABLE_WIDTH_CSS_PX = {
    "letter": 740,
    "a4": 718,
    "legal": 740,
}


def _compute_pdf_scale(page_size: str, viewport_width: int) -> float:
    """Compute the `page.pdf(scale=...)` value so layout fits page width.

    SPA layouts target desktop viewports (≥1024 CSS px). Our default
    viewport is 1280 px. The PDF page (A4/Letter/Legal) is much
    narrower (~718-740 CSS px usable after margins). Without scaling,
    chrome's print path lays out the page at viewport width and then
    clips content past the PDF page boundary on the right edge.

    Setting `scale = pdf_usable / viewport` makes chrome project each
    CSS pixel of layout onto `scale` PDF pixels, so 1280 layout pixels
    fit into ~718 PDF pixels (A4). All content visible, horizontal
    cutoff eliminated.

    Returns a float in [0.1, 2.0] — Playwright clamps outside that
    range, but our typical value is 0.55-0.60, well within bounds.
    """
    usable = _CHROME_PAGE_USABLE_WIDTH_CSS_PX.get(page_size, 718)
    return round(usable / max(viewport_width, 1), 4)


def render_chrome(
    html_text: str,
    output_path: Path,
    *,
    base_url: str,
    page_size: str,
    timeout: int,
    print_background: bool = True,
    javascript: bool = False,
    strip_scripts: bool = True,
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
      javascript: if True (default), execute the page's JavaScript with
        an offline-API patch installed BEFORE page scripts run (see
        `_OFFLINE_PATCH_INIT_SCRIPT`). The patch returns never-resolving
        promises for fetch/XHR and reports `navigator.onLine = true`,
        which prevents SPAs from self-destructing the body or leaving
        the DOM half-hydrated. Set False to skip JS entirely; equivalent
        to a static-CSS-only render.

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

    # Strip `<script>` tags by default. We enable JS at the context
    # level (so page.evaluate works for surgical DOM normalization)
    # but disable the page's OWN scripts by removing them from the
    # HTML. Result: no Gmail self-destruct, no Angular half-hydration,
    # but we still get a privileged JS context for our normalization
    # walk. `strip_scripts=False` disables this and runs page scripts
    # naturally (used when the user passes `--chrome-js` for canvas
    # charts / pre-hydration HTML).
    if strip_scripts and not javascript:
        html_text = _strip_script_tags(html_text)
    elif javascript:
        # User explicitly asked for page JS — leave scripts intact.
        pass

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
                # JS-enabled at context level so page.evaluate works for
                # surgical DOM normalization. The page's own scripts have
                # been stripped from the HTML (see _strip_script_tags
                # call above); only our injected `page.evaluate` runs.
                # When the user explicitly passes `javascript=True`, we
                # also leave page scripts intact (canvas / hydration
                # cases).
                context = browser.new_context(
                    viewport=_DEFAULT_VIEWPORT,
                    java_script_enabled=True,
                )
                context.route("**/*", _block_remote_routes)
                # Inject the offline-API patch BEFORE any page script
                # runs. With JS enabled, page scripts (Gmail's offline
                # detector, Angular's bootstrap calls) will hit our
                # stubbed fetch/XHR and stall on never-resolving
                # promises instead of detecting failure and corrupting
                # the DOM. add_init_script must be called on context
                # (not page) to apply to ALL navigations, including
                # the upcoming `page.goto`.
                if javascript:
                    context.add_init_script(_OFFLINE_PATCH_INIT_SCRIPT)
                page = context.new_page()
                try:
                    # `wait_until="load"` (not "networkidle") because we
                    # block network — networkidle waits for 500 ms of zero
                    # in-flight requests, which always fires immediately
                    # under our route blocker, but `load` is more semantic.
                    page.goto(url, wait_until="load", timeout=timeout_ms)
                    # Force `media: screen` BEFORE page.pdf(). Default
                    # `page.pdf()` calls `emulate_media({media: "print"})`,
                    # which triggers the page's `@media print` rules —
                    # typically designed for clean paper printing of
                    # articles (hide nav, collapse sidebars). For archive
                    # rendering we want screen-capture fidelity.
                    page.emulate_media(media="screen")
                    # Surgical DOM normalization. Walks the DOM and
                    # releases scroll containers + position:fixed wrappers
                    # only where they actually clip content. Best-effort:
                    # if the script throws (rare; e.g. exotic HTML breaks
                    # the walker), continue to PDF render.
                    try:
                        page.evaluate(_DOM_NORMALIZE_SCRIPT)
                    except Exception:
                        pass
                    # Surgical DOM normalization: walk the DOM and
                    # release ONLY scroll containers that actually clip
                    # content (scrollHeight > clientHeight). Skips
                    # overflow:hidden used for sidebar label clipping
                    # (where clientHeight === scrollHeight). Requires
                    # JS — when javascript=False, fall back to the
                    # CSS-only release of html/body (already injected).
                    if javascript:
                        try:
                            # Give the page a tiny settle window in case
                            # an animation is still mid-frame. 100ms is
                            # enough for static archives.
                            page.wait_for_timeout(100)
                            page.evaluate(_DOM_NORMALIZE_SCRIPT)
                        except Exception:
                            # Normalization is best-effort; if it fails
                            # we still want to produce a PDF.
                            pass
                    # Compute scale so layout-width content fits PDF
                    # page width. Without this, SPA layouts at 1280
                    # CSS px get clipped on the right edge of A4
                    # (~718 CSS px usable). See _compute_pdf_scale.
                    pdf_scale = _compute_pdf_scale(
                        page_size, _DEFAULT_VIEWPORT["width"],
                    )
                    page.pdf(
                        path=str(output_path),
                        format=fmt,
                        print_background=print_background,
                        scale=pdf_scale,
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

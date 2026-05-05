"""Chrome-engine HTML→PDF renderer (Playwright + bundled Chromium).

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

import tempfile
from pathlib import Path

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


def render_chrome(
    html_text: str,
    output_path: Path,
    *,
    base_url: str,
    page_size: str,
    timeout: int,
    print_background: bool = True,
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

    tmp_html = _resolve_temp_html_path(base_url)
    try:
        tmp_html.write_text(html_text, encoding="utf-8")
        url = f"file://{tmp_html.resolve()}"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                # `device_scale_factor` defaults to 1; viewport defaults to
                # 1280x720. PDF rendering uses CSS `@page` size, not
                # viewport, so the viewport mostly affects JS-driven layout.
                # Default is fine for static archive content.
                context = browser.new_context()
                context.route("**/*", _block_remote_routes)
                page = context.new_page()
                try:
                    # `wait_until="load"` (not "networkidle") because we
                    # block network — networkidle waits for 500 ms of zero
                    # in-flight requests, which always fires immediately
                    # under our route blocker, but `load` is more semantic.
                    page.goto(url, wait_until="load", timeout=timeout_ms)
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

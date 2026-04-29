"""weasyprint render orchestration with offline URL fetcher and SIGALRM watchdog.

`convert()` is the single entry point used by both the CLI and any future
in-process consumer. The watchdog (`RenderTimeout` + `_install_render_watchdog`)
and `_offline_url_fetcher` are kept in this module because they're tightly
coupled to one `convert()` invocation:
  * the alarm handler is installed/cleared around exactly one render,
  * the URL fetcher is passed as a callback into the same weasyprint call.
"""
from __future__ import annotations

import signal
from pathlib import Path

from weasyprint import CSS, HTML, default_url_fetcher  # type: ignore

# `md2pdf` is a sibling module in `skills/pdf/scripts/`, not part of this
# package. It's on sys.path because the CLI is run from that directory.
from md2pdf import DEFAULT_CSS, PAGE_SIZES

from .preprocess import preprocess_html
from .reader_mode import reader_mode_html

SUPPORTED_EXTENSIONS = (".html", ".htm", ".mhtml", ".mht", ".webarchive")


def _offline_url_fetcher(url: str) -> dict:
    """weasyprint URL fetcher that refuses remote (http/https) URLs.

    Default weasyprint behaviour is to fetch any external URL with no timeout
    (urllib's blocking call). On real-world web pages with dozens of CDN
    references (fonts, analytics pixels, social-media badges) this hangs the
    whole conversion for 10+ minutes per stalled request.

    Local schemes (`file://`, `data:`) fall through to weasyprint's default —
    we explicitly raise to force weasyprint to skip the remote resource and
    continue rendering. Skipped resources produce an "Failed to load X"
    weasyprint warning to stderr but the PDF still renders with whatever
    fonts / images were resolvable locally.
    """
    if url.startswith(("file://", "data:")):
        return default_url_fetcher(url)
    raise ValueError(f"remote fetch refused (offline mode): {url}")


class RenderTimeout(Exception):
    """Raised when weasyprint render exceeds the watchdog deadline."""


def _install_render_watchdog(seconds: int):
    """Install a SIGALRM-based watchdog that raises RenderTimeout after `seconds`.

    Returns the previous handler so the caller can restore it after the
    protected region. macOS / Linux only (signal.alarm is POSIX); on Windows
    the install is a no-op and the watchdog disables itself.

    Honest scope (best-effort, NOT a hard guarantee):

      * SIGALRM interrupts blocking syscalls and fires between Python
        bytecodes — works for pure-Python loops and network reads.
      * BUT cairo (PDF backend) and lxml (HTML parser) hold the GIL inside
        their C extension calls. SIGALRM is queued and delivered only when
        control returns to Python. A pathological cairo layout that stays
        in C code for minutes won't be interrupted until the C call
        completes. Real-world stuck PIDs of 6+ hours observed on vc.ru
        SPA pages.
      * The watchdog is the LAST line of defence; the primary fix is the
        site-CSS strip in `_strip_external_stylesheets` which neutralises
        most pathological layouts before render starts.

    Non-main thread: `signal.signal()` raises ValueError outside the main
    thread (web-server / multiprocessing wrappers). We catch and degrade
    gracefully — the call returns None and the watchdog is disabled for
    this invocation.
    """
    if not hasattr(signal, "SIGALRM") or seconds <= 0:
        return None

    def _on_alarm(signum, frame):
        raise RenderTimeout(
            f"html2pdf render exceeded {seconds}s — "
            "input may be too large or its CSS pathological for layout. "
            "Try --reader-mode (strips site CSS) or set HTML2PDF_TIMEOUT=0 "
            "to disable the watchdog."
        )

    try:
        prev = signal.signal(signal.SIGALRM, _on_alarm)
    except (ValueError, OSError):
        # Non-main thread or platform without signal support. Degrade
        # gracefully — pipeline runs uncapped but doesn't crash.
        return None
    signal.alarm(seconds)
    return prev


def _clear_render_watchdog(prev) -> None:
    if not hasattr(signal, "SIGALRM"):
        return
    signal.alarm(0)
    if prev is not None:
        signal.signal(signal.SIGALRM, prev)


def convert(
    html_text: str,
    output_path: Path,
    *,
    base_url: str,
    page_size: str,
    extra_css_path: Path | None,
    use_default_css: bool,
    reader_mode: bool = False,
    timeout: int = 0,
) -> None:
    # Watchdog wraps the FULL pipeline (reader-mode extraction + preprocessing
    # + weasyprint render). Preprocessing involves ~12 regex passes; on
    # adversarial 4 MB HTML some of them have O(n²) characteristics
    # (`_strip_empty_anchor_links` over thousands of <a> tags) and could
    # exceed the deadline before render even starts. (VDD-iter-5 fix.)
    prev_handler = _install_render_watchdog(timeout)
    try:
        if reader_mode:
            html_text = reader_mode_html(html_text)
        html_text = preprocess_html(html_text)
        stylesheets = []
        if use_default_css:
            css = DEFAULT_CSS.replace("{page_size}", PAGE_SIZES.get(page_size, "letter"))
            stylesheets.append(CSS(string=css))
        if extra_css_path is not None:
            stylesheets.append(CSS(filename=str(extra_css_path)))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        HTML(
            string=html_text,
            base_url=base_url,
            url_fetcher=_offline_url_fetcher,
        ).write_pdf(str(output_path), stylesheets=stylesheets)
    finally:
        _clear_render_watchdog(prev_handler)

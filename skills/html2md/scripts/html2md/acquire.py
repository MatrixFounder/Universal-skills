"""FC-1 — input dispatch + HTML acquisition (ARCH §2.1, §4.1).

Offline branches (file + archive) — bead 022-02. The URL branch
(``httpx``+``trafilatura`` lite + Chrome fallback) lands in 022-06.

Import hygiene (G-2 sibling rule): ``httpx`` / ``trafilatura`` / ``playwright`` are
imported only INSIDE the URL helpers (never at module top), so the package imports
cleanly with none of them installed and the offline path stays dependency-free.

Offline determinism (I-3): the file/archive branches make ZERO network calls.
"""
from __future__ import annotations

import atexit
import html as _html
import ipaddress
import re
import shutil
import socket
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

from web_clean import extract_archive

from .exceptions import BadInput, EngineNotInstalled, FetchFailed
from .model import AcquireResult, SourceMeta

# Honest default UA — what is actually fetching. A browser UA is used ONLY as a 403
# escalation (see _http_get_bytes) and for the Chrome/Jina engines.
_UA = "Mozilla/5.0 (compatible; html2md/0.1; +https://example.invalid/html2md)"
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_LITE_SUBSTANTIAL_CHARS = 200  # auto-fallback: < this much extracted text ⇒ JS shell
_RETRY_BACKOFF_BASE = 1.0      # seconds; transient-retry delay = base * 2**attempt
_RETRY_AFTER_CAP = 30.0        # never honour a Retry-After longer than this
_MAX_429_RETRIES = 2           # separate cap so rate-limited hosts don't burn the budget

_sleep = time.sleep            # indirection so tests patch out real backoff waits
_monotonic = time.monotonic    # ditto — lets the rate limiter run on a fake clock in tests


class _RateLimiter:
    """Minimal min-interval limiter (the *idea* of last30days' RateLimiter, reimplemented).

    Opt-in via ``--rate-limit`` (requests/sec); default disabled. Single-process,
    single-invocation — bounds the one real burst on a page: its image downloads.
    """

    def __init__(self, per_sec: float):
        self._interval = (1.0 / per_sec) if per_sec and per_sec > 0 else 0.0
        self._next = 0.0

    def wait(self) -> None:
        if self._interval <= 0:
            return
        now = _monotonic()
        if now < self._next:
            _sleep(self._next - now)
        self._next = max(now, self._next) + self._interval


_RATE_LIMITER: "_RateLimiter | None" = None  # set per-invocation from opts.rate_limit


def _retry_after_seconds(resp) -> float | None:
    """Parse a numeric ``Retry-After`` header (seconds), capped. HTTP-date form ignored."""
    val = resp.headers.get("retry-after") if getattr(resp, "headers", None) else None
    if val and str(val).strip().isdigit():
        return min(float(val), _RETRY_AFTER_CAP)
    return None


def _fetch_kind(status: int | None) -> str:
    """Classify a fetch failure so the calling agent can decide manual-vs-retry (R-2.2).
    Surfaced as ``details.kind`` alongside ``details.status`` in the FetchFailed envelope."""
    if status is None:
        return "unreachable"        # transport / DNS / timeout
    if status == 403:
        return "bot_blocked"        # WAF / anti-scraper → try --engine jina / chrome
    if status in (401, 407):
        return "auth_required"      # login / paywall → manual
    if status in (404, 410):
        return "not_found"
    if status == 429:
        return "rate_limited"       # back off / --rate-limit
    if 500 <= status < 600:
        return "server_error"       # transient → retry
    return "http_error"

_ARCHIVE_EXT = {".webarchive", ".mhtml", ".mht"}
_FILE_EXT = {".html", ".htm"}

# --------------------------------------------------------------------------- #
# Temp-dir lifecycle (archive sub-resources live until process exit, so emit can
# read the localized images; cleaned atomically at exit).
# --------------------------------------------------------------------------- #
_TEMP_DIRS: list[str] = []
_cleanup_registered = False


def _new_work_dir() -> Path:
    global _cleanup_registered
    d = tempfile.mkdtemp(prefix="html2md_")
    _TEMP_DIRS.append(d)
    if not _cleanup_registered:
        atexit.register(_cleanup_work_dirs)
        _cleanup_registered = True
    return Path(d)


def _cleanup_work_dirs() -> None:
    for d in _TEMP_DIRS:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Format dispatch
# --------------------------------------------------------------------------- #
def _dispatch_format(path: str) -> str:
    """Classify a LOCAL input path as ``"file"`` or ``"archive"``.

    Extension first; magic-byte fallback for extension-less inputs
    (``bplist00`` → webarchive; MIME multipart → mhtml).
    """
    ext = Path(path).suffix.lower()
    if ext in _ARCHIVE_EXT:
        return "archive"
    if ext in _FILE_EXT:
        return "file"
    try:
        with open(path, "rb") as f:
            head = f.read(256)
    except OSError:
        return "file"
    if head.startswith(b"bplist00"):
        return "archive"
    low = head.lstrip().lower()
    if (low.startswith(b"from ")
            or low.startswith(b"mime-version")
            or b"multipart/related" in low):
        return "archive"
    return "file"


# --------------------------------------------------------------------------- #
# Decoding + metadata (best-effort, stdlib-only, no network)
# --------------------------------------------------------------------------- #
def _decode_bytes(raw: bytes) -> str:
    """Decode page bytes → str using BOM / ``<meta charset>`` / utf-8 fallback."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    head = raw[:2048].decode("ascii", errors="replace")
    m = re.search(r'charset=["\']?\s*([\w-]+)', head, re.I)
    enc = m.group(1) if m else "utf-8"
    try:
        return raw.decode(enc, errors="replace")
    except (LookupError, ValueError):
        return raw.decode("utf-8", errors="replace")


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", _html.unescape(value)).strip() or None


def _meta_content(html: str, attr: str, value: str) -> str | None:
    """Return the ``content`` of the first ``<meta>`` whose ``attr`` == ``value``.

    Order-agnostic: handles both ``<meta property=… content=…>`` and the equally
    common ``<meta content=… property=…>`` attribute orderings.
    """
    needle = re.compile(rf'\b{re.escape(attr)}\s*=\s*["\']{re.escape(value)}["\']', re.I)
    for m in re.finditer(r"<meta\b[^>]*>", html, re.I):
        tag = m.group(0)
        if needle.search(tag):
            cm = re.search(r'\bcontent\s*=\s*["\']([^"\']*)["\']', tag, re.I)
            if cm:
                return cm.group(1)
    return None


def _jsonld_date(html: str) -> str | None:
    """First ``"datePublished"`` found INSIDE a JSON-LD ``<script>`` block. Scoped to
    ld+json (NOT a whole-document grep) so a stray ``datePublished`` in inline JS / body
    text / a widget config cannot hijack the date (adversarial finding 2026-06-18)."""
    for m in re.finditer(
            r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.I | re.S):
        dm = re.search(r'"datePublished"\s*:\s*"([^"]+)"', m.group(1))
        if dm:
            return dm.group(1)
    return None


def _arxiv_date_from_url(url: str | None) -> str | None:
    """Derive year-month from an arXiv id (``2504.20838`` → ``2025-04``). arXiv HTML
    carries no ``article:published_time`` and trafilatura mis-dates it (R-4), but the id
    itself encodes YYMM under the post-2007 scheme — the most reliable signal we have."""
    if not url:
        return None
    m = re.search(r"arxiv\.org/(?:abs|pdf|html)/(\d{2})(\d{2})\.\d+", url, re.I)
    if not m:
        return None
    yy, mm = int(m.group(1)), int(m.group(2))
    if 1 <= mm <= 12 and yy >= 7:  # new-id scheme began 2007-04
        return f"20{yy:02d}-{mm:02d}"
    return None


def _structured_date(html: str) -> str | None:
    """A trustworthy publication date from explicit page metadata (NOT body heuristics)."""
    return (
        _meta_content(html, "property", "article:published_time")
        or _meta_content(html, "property", "og:published_time")
        or _meta_content(html, "itemprop", "datePublished")
        or _jsonld_date(html)
        or _meta_content(html, "name", "date")
    )


def _meta_from_html(html: str, *, url: str | None = None) -> SourceMeta:
    """Best-effort frontmatter source from `<title>` / OpenGraph / `<meta>` tags."""
    title_tag = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = (
        _meta_content(html, "property", "og:title")
        or (title_tag.group(1) if title_tag else None)
    )
    author = (
        _meta_content(html, "name", "author")
        or _meta_content(html, "property", "article:author")
    )
    date = _structured_date(html) or _arxiv_date_from_url(url)
    og_url = _meta_content(html, "property", "og:url")
    return SourceMeta(
        url=og_url or url,
        title=_clean_text(title),
        date=_clean_text(date),
        author=_clean_text(author),
    )


# --------------------------------------------------------------------------- #
# Acquisition branches
# --------------------------------------------------------------------------- #
def _acquire_file(src: Path, opts) -> AcquireResult:
    raw = src.read_bytes()
    html_text = _decode_bytes(raw)
    return AcquireResult(
        html=html_text,
        base_url=src.parent.as_uri(),
        mode="file",
        engine=None,
        source_meta=_meta_from_html(html_text, url=src.as_uri()),
        images={},
    )


def _acquire_archive(src: Path, opts) -> AcquireResult:
    work_dir = _new_work_dir()
    frame_spec = getattr(opts, "archive_frame", "main") or "main"
    try:
        html_text, base_url = extract_archive(src, work_dir, frame_spec=frame_spec)
    except Exception as exc:  # noqa: BLE001 — surface as a clean domain error
        raise BadInput(
            f"archive extraction failed for {src.name}: {type(exc).__name__}: {exc}",
            details={"path": src.name, "frame": frame_spec},
        ) from exc
    # Images are already localized into work_dir by the extractor; emit resolves
    # relative <img src> against base_url. (The extractor does not return a
    # URL→local table, so `images` stays empty — base_url is the resolution root.)
    return AcquireResult(
        html=html_text,
        base_url=base_url,
        mode="archive",
        engine=None,
        source_meta=_meta_from_html(html_text),
        images={},
    )


_SENSITIVE_QS = re.compile(
    r"(?i)(token|key|secret|password|passwd|pwd|auth|sig|signature|"
    r"access[_-]?token|api[_-]?key|session|bearer)")


def _redact(url: str) -> str:
    """For error messages: drop userinfo and redact only SENSITIVE query params, while
    KEEPING the rest of the query — e.g. ``?abstract_id=4200414`` is the only thing that
    identifies an SSRN page, so losing it makes the error useless (feedback R-2.3)."""
    p = urlparse(url)
    netloc = p.hostname or ""
    if p.port:
        netloc += f":{p.port}"
    out = f"{p.scheme}://{netloc}{p.path}"
    if p.query:
        # Redact a param when its KEY or its VALUE looks sensitive — the latter catches a
        # token embedded in an otherwise-innocent value, e.g. ?next=…token=SECRET
        # (adversarial finding 2026-06-18). ?abstract_id=4200414 stays intact.
        kept = [(k, "REDACTED" if (_SENSITIVE_QS.search(k) or _SENSITIVE_QS.search(v)) else v)
                for k, v in parse_qsl(p.query, keep_blank_values=True)]
        if kept:
            out += "?" + urlencode(kept)
    return out


def _host_is_public(host: str) -> bool:
    """True only if EVERY resolved address of ``host`` is a public, routable IP.

    Blocks SSRF to loopback / private / link-local (incl. 169.254.169.254 cloud
    metadata) / reserved / multicast targets. Conservative: an unresolvable host, or a
    host that resolves to *any* non-public address, is rejected.

    Residual (honest scope, ARCH §10): this is a resolve-then-connect check, so a
    determined DNS-rebinding attacker controlling the authoritative DNS could still
    flip the address between this lookup and httpx's own connect. Run untrusted
    conversions in a network-egress-restricted sandbox for full assurance.
    """
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def _assert_public_http(url: str) -> None:
    """Reject non-http(s) or private/internal targets (raises FetchFailed)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchFailed(
            f"refused non-http(s) target: {_redact(url)}",
            details={"url": _redact(url), "kind": "refused"},
        )
    if not _host_is_public(parsed.hostname or ""):
        raise FetchFailed(
            f"refused private/internal/unresolvable target: {_redact(url)}",
            details={"url": _redact(url), "kind": "refused"},
        )


def _http_get_bytes(url: str, *, max_bytes: int | None, timeout: float = 20.0,
                    max_redirects: int = 5, retries: int = 2, ua: str = _UA,
                    extra_headers: dict | None = None) -> bytes:
    """Fetch ``url`` over HTTP(S) → bytes. SSRF-safe, streaming, bounded, retrying.

    SSRF/DoS posture (§7): http(s) only; **every** hop (initial + each redirect) is
    re-checked against :func:`_host_is_public`; redirects are followed manually (cap
    ``max_redirects``); the body is streamed and aborted the moment it passes
    ``max_bytes``; bounded timeout; no credential forwarding. Raises
    :class:`FetchFailed` (exit 10). This is the single network seam — tests monkeypatch
    it (or inject a fake ``httpx``) for offline runs.

    Robustness (borrowed pattern from last30days, reimplemented): transient failures
    (transport errors, HTTP 5xx, 429) are retried with exponential backoff (``retries``
    attempts; 429 honours ``Retry-After`` up to a cap and has its own small budget); a
    **403** triggers ONE immediate escalation to a browser User-Agent (the honest
    ``_UA`` is the default; only a refusal swaps it). Other 4xx are terminal.
    """
    import httpx

    if _RATE_LIMITER is not None:
        _RATE_LIMITER.wait()

    def _one_pass(use_ua: str) -> bytes:
        """One full request (manual redirects + streaming). Raises httpx errors for the
        outer loop to classify, or FetchFailed for terminal conditions."""
        headers = {"User-Agent": use_ua}
        if extra_headers:
            headers.update(extra_headers)
        current = url
        with httpx.Client(follow_redirects=False, timeout=timeout, headers=headers) as client:
            for _ in range(max_redirects + 1):
                _assert_public_http(current)  # re-checked on every hop (anti-SSRF)
                with client.stream("GET", current) as resp:
                    if resp.is_redirect and "location" in resp.headers:
                        current = urljoin(current, resp.headers["location"])
                        continue
                    resp.raise_for_status()
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if max_bytes is not None and total > max_bytes:
                            raise FetchFailed(
                                f"response exceeds --max-bytes ({max_bytes}) for "
                                f"{_redact(current)}",
                                details={"url": _redact(current), "max_bytes": max_bytes},
                            )
                        chunks.append(chunk)
                    return b"".join(chunks)
        raise FetchFailed(
            f"too many redirects (> {max_redirects}) for {_redact(url)}",
            details={"url": _redact(url)},
        )

    def _fail(exc, status=None) -> FetchFailed:
        detail = {"url": _redact(url), "kind": _fetch_kind(status)}
        if status is not None:
            detail["status"] = status
        suffix = f"HTTP {status}" if status is not None else type(exc).__name__
        return FetchFailed(f"fetch failed for {_redact(url)}: {suffix}", details=detail)

    use_ua = ua
    browser_ua_tried = ua is _BROWSER_UA
    attempt = 0
    n_429 = 0
    while True:
        try:
            return _one_pass(use_ua)
        except FetchFailed:
            raise  # terminal: SSRF refusal / max_bytes / too many redirects
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code == 403 and not browser_ua_tried:
                browser_ua_tried, use_ua = True, _BROWSER_UA
                continue  # one immediate UA swap — does NOT consume the retry budget
            retryable = code == 429 or 500 <= code < 600
            if not retryable:
                raise _fail(exc, status=code) from exc          # 404/410/451/403(both UAs)…
            if code == 429:
                n_429 += 1
                if n_429 > _MAX_429_RETRIES:
                    raise _fail(exc, status=code) from exc
            if attempt >= retries:
                raise _fail(exc, status=code) from exc
            delay = (_retry_after_seconds(exc.response) if code == 429 else None)
            _sleep(delay if delay is not None else _RETRY_BACKOFF_BASE * (2 ** attempt))
            attempt += 1
        except httpx.TransportError as exc:  # connect / read / timeout / DNS
            if attempt >= retries:
                raise _fail(exc) from exc
            _sleep(_RETRY_BACKOFF_BASE * (2 ** attempt))
            attempt += 1
        except Exception as exc:  # noqa: BLE001 — anything else → terminal clean error
            raise _fail(exc) from exc


def _looks_substantial(page_html: str) -> bool:
    """auto-mode heuristic (ARCH §13 OQ-2): does the lite-fetched HTML carry real
    article text, or is it a JS shell that needs the Chrome engine?"""
    try:
        import trafilatura
        text = trafilatura.extract(page_html, include_comments=False) or ""
    except Exception:  # noqa: BLE001 — extraction failure ⇒ treat as thin
        text = ""
    return len(text.strip()) >= _LITE_SUBSTANTIAL_CHARS


def _trafilatura_meta(page_html: str, url: str) -> SourceMeta:
    """Frontmatter metadata via trafilatura (title/author), but the DATE prefers explicit
    structured metadata / arXiv-id over trafilatura's body-text heuristic (R-4: trafilatura
    mis-dated arXiv 2504.20838 as 2021-08-16 from a citation in the body)."""
    reliable_date = _clean_text(_structured_date(page_html) or _arxiv_date_from_url(url))
    try:
        import trafilatura
        doc = trafilatura.extract_metadata(page_html)
    except Exception:  # noqa: BLE001
        doc = None
    if doc is not None and _clean_text(getattr(doc, "title", None)):
        return SourceMeta(
            url=_clean_text(getattr(doc, "url", None)) or url,
            title=_clean_text(getattr(doc, "title", None)),
            date=reliable_date or _clean_text(getattr(doc, "date", None)),
            author=_clean_text(getattr(doc, "author", None)),
        )
    return _meta_from_html(page_html, url=url)


def _fetch_lite_html(url: str, max_bytes: int | None, retries: int = 2) -> str:
    """httpx GET → decoded raw page HTML (offline cleaning is done later by web_clean).

    Guards against non-HTML payloads: a PDF or other binary blob must fail with a clear
    message — NOT be fed to turndown (which blows the Node call stack on binary input).
    """
    raw = _http_get_bytes(url, max_bytes=max_bytes, retries=retries)
    head = raw[:1024]
    if head[:5] == b"%PDF-":
        raise FetchFailed(
            f"{_redact(url)} returns a PDF, not an HTML page — extract it with the pdf "
            "skill (scripts/pdf_extract.py) instead.",
            details={"url": _redact(url), "kind": "pdf"},
        )
    if b"\x00" in head:
        raise FetchFailed(
            f"{_redact(url)} returns non-HTML binary content (not convertible to Markdown).",
            details={"url": _redact(url), "kind": "binary"},
        )
    return _decode_bytes(raw)


def _fetch_chrome_html(url: str) -> str:
    """Render ``url`` via headless Chromium (Playwright) → hydrated DOM HTML.

    Soft-optional: missing Playwright → :class:`EngineNotInstalled` (exit 3) with
    remediation. Honest scope (ARCH §10): this is a **basic** ``launch + goto`` render
    — it does NOT yet block beacons / route remote sub-resources, and Chromium follows
    redirects (incl. to internal hosts) without the public-IP gate the lite path
    enforces. Run untrusted ``--engine chrome`` conversions in an egress-restricted
    sandbox. Full network hardening is deferred (a future bead).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise EngineNotInstalled(
            "Chrome engine requires Playwright. Install with: "
            "bash scripts/install.sh --with-chrome",
            details={"remediation": "install.sh --with-chrome"},
        ) from exc
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page(user_agent=_BROWSER_UA)
                page.goto(url, wait_until="load", timeout=30000)
                html = page.content()
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        raise FetchFailed(
            f"chrome fetch failed for {_redact(url)}: {type(exc).__name__}",
            details={"url": _redact(url)},
        ) from exc
    return html


_JINA_READER_PREFIX = "https://r.jina.ai/"


def _fetch_jina_html(url: str, max_bytes: int | None, retries: int = 2) -> str:
    """Fetch via Jina Reader (``r.jina.ai``) → rendered HTML, for JS/SPA / anti-bot pages
    WITHOUT a local browser. Borrowed (keyless) idea from last30days' web_fetch_keyless.

    We request ``X-Return-Format: html`` so Jina returns rendered HTML (not its default
    markdown), letting the page flow through the SAME pipeline as every other engine
    (web_clean → turndown → frontmatter → _attachments). An optional ``JINA_API_KEY``
    env raises the (otherwise keyless, rate-limited) quota.

    PRIVACY / honest scope: the **target URL leaves the machine** — Jina fetches it
    server-side. Hence this engine is explicit-only (``--engine jina``), never part of
    ``auto``. The local connection is to public ``r.jina.ai`` (passes the SSRF gate).
    """
    import os

    if urlparse(url).scheme not in ("http", "https"):
        raise FetchFailed(f"--engine jina needs an http(s) URL, got {_redact(url)}",
                          details={"url": _redact(url)})
    headers = {"X-Return-Format": "html"}
    key = os.environ.get("JINA_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    raw = _http_get_bytes(_JINA_READER_PREFIX + url, max_bytes=max_bytes,
                          retries=retries, extra_headers=headers)
    return _decode_bytes(raw)


def _nojs_variant(url: str) -> str | None:
    """A host-specific no-JS URL variant whose canonical page gates the article body
    behind JavaScript (R-1). HackerNoon serves the full body at ``/lite/<slug>`` while the
    canonical URL is a JS shell that **Chrome rendering does not unlock** (lazy-load /
    "Read on Terminal" gate) — so the URL rewrite, not the browser, is the fix."""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if host == "hackernoon.com" or host.endswith(".hackernoon.com"):
        if "/lite/" not in p.path and p.path.strip("/"):
            return f"{p.scheme}://{p.netloc}/lite{p.path}"
    return None


def _resolve_url_image(src: str, opts) -> bytes | None:
    """Fetch a remote image (for emit's url-mode download). None on any failure —
    a broken image must never abort the conversion. Bounded by ``--max-bytes``."""
    if urlparse(src).scheme not in ("http", "https"):
        return None
    try:
        return _http_get_bytes(src, max_bytes=getattr(opts, "max_bytes", None),
                               retries=getattr(opts, "retries", 2))
    except FetchFailed:
        return None


_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=["\'])([^"\']+)(["\'])', re.IGNORECASE)
_BASE_HREF_RE = re.compile(r'<base\b[^>]*\bhref=["\']([^"\']+)["\']', re.IGNORECASE)


def _absolutize_img_srcs(html: str, page_url: str) -> str:
    """Resolve relative ``<img src>`` to absolute URLs so url-mode image download works.

    Honours an in-document ``<base href>`` (arXiv/ar5iv ship
    ``<base href="https://arxiv.org/html/NNNN/">``); falls back to the fetched page URL.
    Already-absolute, ``data:`` and protocol-relative srcs are left untouched. Offline
    archive/file modes don't need this — ``web_clean.archives`` already absolutises them.
    """
    m = _BASE_HREF_RE.search(html)
    base = urljoin(page_url, m.group(1)) if m else page_url

    def _sub(mt: "re.Match[str]") -> str:
        src = mt.group(2)
        if re.match(r"^(?:[a-z][a-z0-9+.\-]*:|//)", src, re.IGNORECASE):
            return mt.group(0)  # scheme: / data: / protocol-relative → already absolute
        return f"{mt.group(1)}{urljoin(base, src)}{mt.group(3)}"

    return _IMG_SRC_RE.sub(_sub, html)


def _acquire_url(input_ref: str, opts) -> AcquireResult:
    """URL fetch: lite (httpx+trafilatura) by default, auto-fallback to Chrome for
    JS/SPA shells, explicit ``--engine chrome``, or explicit ``--engine jina`` (Jina
    Reader, external). Returns RAW page HTML (web_clean does the uniform cleaning
    downstream); trafilatura supplies frontmatter metadata."""
    engine = (getattr(opts, "engine", "auto") or "auto").lower()
    max_bytes = getattr(opts, "max_bytes", None)
    retries = getattr(opts, "retries", 2)

    page_html: str | None = None
    used: str | None = None
    if engine == "jina":
        page_html = _fetch_jina_html(input_ref, max_bytes, retries=retries)
        used = "jina"
    elif engine in ("lite", "auto"):
        # Known JS-gated hosts (HackerNoon) serve only a chrome shell at the canonical URL
        # — and that shell is text-heavy enough to pass _looks_substantial, so we can't
        # rely on auto-escalation. Fetch the no-JS variant PROACTIVELY (R-1). Chrome does
        # not unlock these bodies; the URL rewrite does.
        fetch_url = _nojs_variant(input_ref) or input_ref
        page_html = _fetch_lite_html(fetch_url, max_bytes, retries=retries)
        used = "lite+nojs" if fetch_url != input_ref else "lite"
        if engine == "auto" and not _looks_substantial(page_html):
            page_html, used = None, None  # genuine JS shell → escalate to Chrome
    if page_html is None:  # explicit chrome, or auto-fallback
        page_html = _fetch_chrome_html(input_ref)
        used = "chrome"

    page_html = _absolutize_img_srcs(page_html, input_ref)
    return AcquireResult(
        html=page_html,
        base_url=input_ref,
        mode="url",
        engine=used,
        source_meta=_trafilatura_meta(page_html, input_ref),
        images={},
    )


def acquire(input_ref: str, opts) -> AcquireResult:
    """Acquire raw HTML + source metadata from a URL / archive / file (FC-1)."""
    global _RATE_LIMITER
    rate = getattr(opts, "rate_limit", None)
    # Configure (or clear) the throttle for the WHOLE run — covers the page fetch AND the
    # image-download burst, in url-mode and offline-with-remote-images alike; reset every
    # invocation so a prior in-process call cannot leak a stale limiter.
    _RATE_LIMITER = _RateLimiter(rate) if rate else None
    scheme = urlparse(input_ref).scheme.lower()
    if scheme in ("http", "https"):
        return _acquire_url(input_ref, opts)
    fmt = _dispatch_format(input_ref)
    if fmt == "archive":
        return _acquire_archive(Path(input_ref), opts)
    return _acquire_file(Path(input_ref), opts)

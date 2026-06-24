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
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path
from typing import NamedTuple
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse

from web_clean import extract_archive

from ._env import env as _env

from .exceptions import BadInput, EngineNotInstalled, FetchFailed
from .model import AcquireResult, SourceMeta

# Honest default UA — what is actually fetching. A browser UA is used ONLY as a 403
# escalation (see _http_get_bytes) and for the Chrome/Jina engines.
_UA = "Mozilla/5.0 (compatible; html/0.1; +https://example.invalid/html)"
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
    d = tempfile.mkdtemp(prefix="html_")
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


_CHROME_SCROLL_BUDGET_S = 60.0  # wall-clock cap for --chrome-scroll (TASK 024 R4; internal, not a flag)


def _login_render(url: str, save_state_path: str, opts) -> None:
    """`login` mint helper (TASK 024 R3): open ``url`` in a HEADFUL browser, block for a manual
    login (2FA ok), then write the Playwright ``storage_state`` JSON and ``chmod 0600``. This is
    the ONE interactive/headful path — runtime fetches stay headless. The target must be public."""
    _assert_public_http(url)
    sync_playwright = _import_sync_playwright()
    try:
        with sync_playwright() as pw:
            browser = _launch_chrome_browser(pw, headless=False)  # real Chrome + de-automation (R1/R2)
            try:
                context = browser.new_context(user_agent=_BROWSER_UA)
                context.add_init_script(_WEBDRIVER_MASK_JS)  # mask the residual webdriver flag (R2)
                page = context.new_page()
                page.goto(url, wait_until="load", timeout=120000)
                sys.stderr.write(
                    "html: a browser window opened — log in there, then press Enter "
                    "here to save the session...\n")
                sys.stderr.flush()
                input()  # block for the manual login
                _old_umask = os.umask(0o077)  # create the session 0600 from the start (no race)
                try:
                    context.storage_state(path=save_state_path)
                finally:
                    os.umask(_old_umask)
            finally:
                browser.close()
    except (FetchFailed, EngineNotInstalled):
        raise
    except Exception as exc:  # noqa: BLE001
        raise FetchFailed(f"login render failed: {type(exc).__name__}",
                          details={"url": _redact(url)}) from exc
    os.chmod(save_state_path, 0o600)  # the saved session is a bearer credential


def _import_sync_playwright():
    """Return Playwright's ``sync_playwright`` (soft-optional) or raise EngineNotInstalled.
    A module-level seam so tests inject a fake without a real browser."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise EngineNotInstalled(
            "Chrome engine requires Playwright. Install with: "
            "bash scripts/install.sh --with-chrome",
            details={"remediation": "install.sh --with-chrome"},
        ) from exc
    return sync_playwright


# --- Chrome launch hardening (TASK 025) --------------------------------------------- #
# Bundled Chromium under CDP automation sets ``navigator.webdriver = true``, which first-party
# logins (X email/password) and authed renders flag as bot traffic ("JavaScript is not available"
# wall / Google's "this browser may not be secure"). Prefer the user's REAL system Chrome channel
# and suppress the automation signal; fall back to bundled Chromium when system Chrome is absent —
# never a hard failure (R10 parity). NB: Google's OAuth bot-detection is intentionally strong and
# may STILL refuse — the sanctioned path for Google-SSO accounts is cookie export (manual §5b),
# NOT a fingerprint arms race.
_CHROME_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
_WEBDRIVER_MASK_JS = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"


def _launch_chrome_browser(pw, *, headless: bool):
    """Launch a Chromium browser preferring the real system Chrome channel (TASK 025 R1/R2);
    fall back to bundled Chromium if that channel is not installed (R10 — never a hard failure)."""
    try:
        return pw.chromium.launch(headless=headless, channel="chrome", args=_CHROME_LAUNCH_ARGS)
    except Exception:  # noqa: BLE001 — system Chrome absent → bundled Chromium fallback
        return pw.chromium.launch(headless=headless, args=_CHROME_LAUNCH_ARGS)


def _launch_chrome_persistent(pw, *, headless: bool, kwargs: dict):
    """Persistent-profile variant of :func:`_launch_chrome_browser` (``--chrome-user-data-dir``):
    same system-Chrome-then-bundled fallback; returns a context directly. Pairing the real Chrome
    channel with the user's own Chrome profile is what makes the persistent-profile path usable."""
    try:
        return pw.chromium.launch_persistent_context(
            headless=headless, channel="chrome", args=_CHROME_LAUNCH_ARGS, **kwargs)
    except Exception:  # noqa: BLE001 — system Chrome absent → bundled Chromium fallback
        return pw.chromium.launch_persistent_context(
            headless=headless, args=_CHROME_LAUNCH_ARGS, **kwargs)


def _registrable(host: str | None) -> str:
    """Approx eTLD+1 = last two labels — allows ``www.``↔apex same-site redirects while refusing
    off-target hosts. Honest-scope (TASK 024 §16.1): multi-level public suffixes (e.g. ``co.uk``)
    over-match (no public-suffix-list dependency); acceptable for the auth-replay use case."""
    host = (host or "").lower().strip(".")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _install_chrome_guards(context) -> None:
    """Install BEFORE ``goto`` (TASK 024 R1): abort ANY request — navigation, sub-resource, JS
    ``fetch``/``sendBeacon`` — whose host is NOT public, so a credentialed render cannot exfil to
    an internal/metadata host or follow a redirect to one. Public-IP results are cached per host
    to bound the ``getaddrinfo`` cost inside the route callback. Fails CLOSED (abort) on any
    guard error — never lets a request through on an exception. (Same-site / off-target-public
    enforcement is post-snapshot in :func:`_fetch_chrome_html`, not here.)"""
    cache: dict[str, bool] = {}

    def _ok(host: str) -> bool:
        if host not in cache:
            cache[host] = _host_is_public(host)
        return cache[host]

    def _route(route, request):
        try:
            host = (urlparse(getattr(request, "url", "")).hostname or "").lower()
            if host and _ok(host):
                route.continue_()
            else:
                route.abort()
        except Exception:  # noqa: BLE001 — fail closed
            try:
                route.abort()
            except Exception:  # noqa: BLE001
                pass

    context.route("**/*", _route)


def _chrome_scroll(page, passes: int) -> None:
    """Scroll to the bottom up to ``passes`` times to trigger lazy content (e.g. replies),
    bounded by ``_CHROME_SCROLL_BUDGET_S`` wall-clock — never hangs (TASK 024 R4). Best-effort:
    any scroll/wait error stops the loop, never aborts the fetch."""
    deadline = _monotonic() + _CHROME_SCROLL_BUDGET_S
    for _ in range(max(0, int(passes))):
        if _monotonic() >= deadline:
            break
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:  # noqa: BLE001 — best-effort
            break


def _fetch_chrome_html(url: str, opts=None) -> str:
    """Render ``url`` via headless Chromium (Playwright) → hydrated DOM HTML.

    Soft-optional: missing Playwright → :class:`EngineNotInstalled` (exit 3) with
    remediation. ``opts`` (TASK 024) carries the authenticated-context source + scroll
    settings; the SSRF gate (024-02), auth context (024-03), and scroll/staleness (024-05)
    consume it. With ``opts`` carrying no auth, behaviour is the prior bare render (R10).

    SSRF-gated (024-02): the target is public-IP-checked before navigation; a context-level
    route guard aborts any request (sub-resource / ``fetch`` / ``beacon`` / redirect) to a
    non-public host; an off-target public redirect (final origin ≠ target eTLD+1) is refused;
    a stale-session login wall → ``auth_required``. Honest-scope residuals (ARCH §16.1):
    DNS-rebind TOCTOU is inherited (resolve-then-connect); ``storage_state`` localStorage is
    origin-restored; ``page.content()`` is bounded by ``--max-bytes`` only POST-render (Chromium's
    own DOM memory is uncapped). Run fully-untrusted conversions in an egress-restricted sandbox.
    """
    _assert_public_http(url)  # gate the TARGET before any browser work (TASK 024 R1)
    from . import _chrome_auth
    target_host = urlparse(url).hostname
    target_reg = _registrable(target_host)
    # R2 (None ⇒ R10 anon); target_host drives the per-domain auth map (TASK 026, suffix match)
    spec = _chrome_auth.resolve_context_kwargs(opts, target_host) if opts is not None else None
    sync_playwright = _import_sync_playwright()
    final_url = url
    try:
        with sync_playwright() as pw:
            # Context (not new_page) so the SSRF route-guard + auth state attach to ALL
            # pages/popups/workers; guards installed BEFORE goto (no first-request TOCTOU).
            if spec and spec["mode"] == "persistent":
                context = _launch_chrome_persistent(  # real Chrome + de-automation (R1/R2)
                    pw, headless=True, kwargs={"user_agent": _BROWSER_UA, **spec["kwargs"]})
                browser = None
            else:
                browser = _launch_chrome_browser(pw, headless=True)  # real Chrome + de-automation
                context = browser.new_context(
                    user_agent=_BROWSER_UA, **(spec["kwargs"] if spec else {}))
                if spec and spec.get("cookies"):
                    context.add_cookies(spec["cookies"])
            context.add_init_script(_WEBDRIVER_MASK_JS)  # mask the residual webdriver flag (R2)
            try:
                _install_chrome_guards(context)
                page = context.new_page()
                page.goto(url, wait_until="load", timeout=30000)
                if opts is not None and getattr(opts, "chrome_scroll", False):
                    _chrome_scroll(page, getattr(opts, "chrome_scroll_passes", 8) or 8)  # R4
                final_url = page.url or url
                html = page.content()
            finally:
                browser.close() if browser is not None else context.close()
    except (FetchFailed, EngineNotInstalled):
        raise
    except Exception as exc:  # noqa: BLE001
        raise FetchFailed(
            f"chrome fetch failed for {_redact(url)}: {type(exc).__name__}",
            details={"url": _redact(url)},
        ) from exc
    # Off-target PUBLIC redirect guard (R1): a public→public off-target landing is refused so a
    # credentialed session is never carried to a different site.
    if _registrable(urlparse(final_url).hostname) != target_reg:
        raise FetchFailed(
            f"chrome landed off-target for {_redact(url)} (→ {_redact(final_url)})",
            details={"url": _redact(url), "kind": "offsite_redirect"},
        )
    # --max-bytes parity with the lite tier (perf P-1): bound the rendered body we pass
    # downstream (turndown / absolutize). NB: this is POST-render — Chromium's own DOM memory
    # is not capped by it; it prevents a giant scrolled SPA from overflowing downstream work.
    max_bytes = getattr(opts, "max_bytes", None) if opts is not None else None
    if max_bytes is not None and len(html.encode("utf-8", "replace")) > max_bytes:
        raise FetchFailed(
            f"chrome render exceeds --max-bytes ({max_bytes}) for {_redact(url)}",
            details={"url": _redact(url), "max_bytes": max_bytes, "kind": "max_bytes"},
        )
    # Stale-session detection (R5c): a logged-out login wall is NOT returned as content.
    if opts is not None and _chrome_auth.is_login_wall(html, final_url):
        raise FetchFailed(
            f"chrome landed on a login wall for {_redact(url)} (stale/expired session — re-mint)",
            details={"url": _redact(url), "kind": "auth_required"},
        )
    return html


_JINA_READER_PREFIX = "https://r.jina.ai/"

# --------------------------------------------------------------------------- #
# Remote-reader + search provider layer (TASK 023) — vendor-agnostic, pluggable.
# Records + the fall-through signal are frozen here (023-01); behaviour lands in
# 023-02 (providers), 023-03 (ladder), 023-04 (privacy), 023-06 (search).
# --------------------------------------------------------------------------- #
_DEFAULT_TARGET_SELECTOR = "article, main, [role=main]"  # X-Target-Selector default (023-05)


class _RemoteReader(NamedTuple):
    """A remote URL→content reader provider (e.g. Jina Reader). ``name`` is the engine
    label (``jina`` or ``remote:<host>``); ``base`` is concatenated with the target URL
    (literal join, Jina's ``r.jina.ai/https://…`` convention)."""

    name: str
    base: str
    token: str | None = None


class _SearchProvider(NamedTuple):
    """A web-search provider. ``shape`` is ``"combined"`` (returns merged Markdown of the
    top results server-side, e.g. ``s.jina.ai``) or ``"links"`` (returns result URLs →
    each fetched through the FETCH ladder so it inherits per-result fallback)."""

    name: str
    base: str
    shape: str
    token: str | None = None


class _TierUnavailable(Exception):
    """Internal fall-through signal: a fetch TIER (remote provider / engine) is unavailable,
    so the ladder should try the next one. Carries the classification for the ``tried``
    trace. NEVER surfaced to the user (distinct from :class:`FetchFailed`)."""

    def __init__(self, kind: str, status: int | None = None):
        super().__init__(kind)
        self.kind = kind
        self.status = status


# Preserve URL structure when appending the target to a reader base (Jina's
# ``r.jina.ai/https://…`` convention); only space/control/<>" and other truly-unsafe
# bytes are percent-encoded. ``%`` is in the safe set so an already-encoded target is not
# double-encoded. (The hard CRLF/injection rejection is 023-04.)
_READER_TARGET_SAFE = "%:/?#[]@!$&'()*+,;=~"


def _norm_base(base: str) -> str:
    """Normalise a reader base for literal ``base + target`` joins. Ensures a trailing
    ``/`` unless the base ends with ``=`` (a ``?url=``-style reader) so the join is valid."""
    base = base.strip()
    if not base.endswith(("/", "=")):
        base += "/"
    return base


def _reader_from_base(base: str) -> "_RemoteReader":
    """Build a provider record from a base URL, picking the right name + auth env.

    ``r.jina.ai`` → name ``jina`` + ``JINA_API_KEY``; any other host → ``remote:<host>`` +
    ``HTML_READER_TOKEN`` (per-provider, not interchangeable — TASK 023 R2)."""
    nb = _norm_base(base)
    host = (urlparse(nb).hostname or "").lower()
    if host == "r.jina.ai":
        return _RemoteReader("jina", nb, os.environ.get("JINA_API_KEY"))
    return _RemoteReader(f"remote:{host}" if host else "remote", nb,
                         _env("READER_TOKEN"))


def _configured_providers() -> "tuple[list[_RemoteReader], str]":
    """The env-configured reader list + a kind tag (``"list"``/``"single"``/``"none"``).

    ``HTML_READER_PROVIDERS`` (comma/space list) is the exact operator order;
    else ``HTML_READER_URL`` (single); else none."""
    provs = _env("READER_PROVIDERS")
    if provs and provs.strip():
        return [_reader_from_base(b) for b in re.split(r"[,\s]+", provs.strip()) if b], "list"
    single = _env("READER_URL")
    if single and single.strip():
        return [_reader_from_base(single)], "single"
    return [], "none"


def _remote_providers(opts) -> "list[_RemoteReader]":
    """Ordered remote-reader providers for ``opts.engine`` (TASK 023 R2).

    - ``jina``   → the built-in ``jina`` provider only.
    - ``remote`` → the env-configured providers ONLY (never a silent jina fall-back —
      privacy; usage-guarded non-empty in cli).
    - ``auto``   → an explicit ``HTML_READER_PROVIDERS`` list verbatim; else
      ``HTML_READER_URL`` then the built-in ``jina``; else just ``jina``.
    De-duped by base, order preserved.
    """
    engine = (getattr(opts, "engine", "auto") or "auto").lower()
    jina = _RemoteReader("jina", _JINA_READER_PREFIX, os.environ.get("JINA_API_KEY"))
    if engine == "jina":
        out = [jina]
    else:
        configured, kind = _configured_providers()
        if engine == "remote":
            out = list(configured)                 # configured only — no jina fall-back
        elif kind == "list":
            out = list(configured)                 # auto: exact operator order
        elif kind == "single":
            out = configured + [jina]              # auto: url then jina fallback
        else:
            out = [jina]                           # auto: built-in default
    seen: set[str] = set()
    dedup: list[_RemoteReader] = []
    for p in out:
        if p.base not in seen:
            seen.add(p.base)
            dedup.append(p)
    return dedup


def _build_reader_request(provider: "_RemoteReader", target: str, opts) -> "tuple[str, dict]":
    """Build ``(reader_url, headers)`` for a provider + target URL.

    URL = ``provider.base`` + URL-encoded ``target`` (literal join). Headers:
    ``X-Return-Format`` follows ``opts.remote_format`` (default ``html``);
    ``Authorization: Bearer`` when the provider has a token. (``X-Target-Selector`` is
    added in 023-05; the CRLF/injection guard in 023-04.)"""
    # A `?url=`-style reader base (ends with `=`) takes the target as a SINGLE query value →
    # encode it fully so its `&`/`=`/`#`/`?` cannot break out into the reader's own query
    # (CWE-88). The path-append (Jina `/`-ending) convention keeps URL structure readable.
    safe = "" if provider.base.endswith("=") else _READER_TARGET_SAFE
    reader_url = provider.base + quote(target, safe=safe)
    selector = (getattr(opts, "target_selector", None) or _DEFAULT_TARGET_SELECTOR)
    if any(ord(c) < 0x20 or ord(c) == 0x7f for c in selector):  # header-injection guard (L-3)
        raise FetchFailed("refused control characters in --target-selector",
                          details={"kind": "refused"})
    headers = {
        "X-Return-Format": (getattr(opts, "remote_format", None) or "html"),
        # Extract just the article block server-side (TASK 023 R4); single-source default.
        "X-Target-Selector": selector,
    }
    if provider.token:
        headers["Authorization"] = f"Bearer {provider.token}"
    return reader_url, headers


_REMOTE_MIN_CHARS = 32           # a remote-reader body shorter than this ⇒ provider miss
# A lite/chrome FetchFailed with one of these kinds is a TERMINAL target condition (no
# other tier can fix it) → the ladder surfaces it instead of escalating.
_TERMINAL_TARGET_KINDS = {"not_found", "auth_required", "pdf", "binary"}
# A reader 4xx reflecting the TARGET's own state (not the provider being down) → stop
# trying more remote PROVIDERS and let the ladder try a different TIER.
_READER_TARGET_BLOCK_KINDS = {"not_found", "auth_required", "bot_blocked"}


def _fetch_remote_html(target: str, opts) -> "tuple[str, str]":
    """Remote-reader TIER: try each provider in order; return ``(content, engine_label)``.

    Classification (TASK 023 R3): provider-down / transient (429 / 402 / 5xx / transport /
    empty body) → try the next provider; a reader-reported **target** block (403 / 401 /
    404) → stop trying providers and raise :class:`_TierUnavailable` so the ladder can try a
    DIFFERENT tier (provider-terminal ≠ tier-terminal); all providers exhausted →
    :class:`_TierUnavailable("remote_exhausted")`. Never raises a bare exception.

    PRIVACY (TASK 023 R5): the remote tier is skipped (``disabled`` via ``--no-remote``, or
    ``skipped_private`` for a non-public target) BEFORE any request — a private / internal /
    unresolvable target URL is NEVER forwarded to an external reader."""
    if getattr(opts, "no_remote", False):
        raise _TierUnavailable("disabled")
    host = (urlparse(target).hostname or "").lower()
    if not _host_is_public(host):
        raise _TierUnavailable("skipped_private")  # never send a non-public URL to a reader
    providers = _remote_providers(opts)
    if not providers:
        raise _TierUnavailable("no_remote_provider")
    max_bytes = getattr(opts, "max_bytes", None)
    retries = getattr(opts, "retries", 2)
    for prov in providers:
        url, headers = _build_reader_request(prov, target, opts)
        try:
            raw = _http_get_bytes(url, max_bytes=max_bytes, retries=retries,
                                  extra_headers=headers)
        except FetchFailed as exc:
            kind = exc.details.get("kind")
            if kind in _READER_TARGET_BLOCK_KINDS:
                raise _TierUnavailable(kind, exc.details.get("status")) from exc
            continue  # provider-down / transient → next provider
        content = _decode_bytes(raw)
        if len(content.strip()) < _REMOTE_MIN_CHARS:
            continue  # provider miss (blank / tiny error body) → next provider
        return content, prov.name
    raise _TierUnavailable("remote_exhausted")


_JINA_SEARCH_PREFIX = "https://s.jina.ai/"


def _search_from_base(base: str) -> "_SearchProvider":
    nb = _norm_base(base)
    host = (urlparse(nb).hostname or "").lower()
    if host == "s.jina.ai":
        return _SearchProvider("s.jina.ai", nb, "links", os.environ.get("JINA_API_KEY"))
    return _SearchProvider(f"search:{host}" if host else "search", nb, "links",
                           _env("READER_TOKEN"))


def _search_providers(opts) -> "list[_SearchProvider]":
    """Ordered search providers (R9): ``HTML_SEARCH_PROVIDERS`` (list) else
    ``HTML_SEARCH_URL`` then the built-in ``s.jina.ai``. De-duped by base."""
    provs = _env("SEARCH_PROVIDERS")
    if provs and provs.strip():
        out = [_search_from_base(b) for b in re.split(r"[,\s]+", provs.strip()) if b]
    else:
        single = _env("SEARCH_URL")
        out = [_search_from_base(single)] if (single and single.strip()) else []
        out.append(_SearchProvider("s.jina.ai", _JINA_SEARCH_PREFIX, "links",
                                   os.environ.get("JINA_API_KEY")))
    seen: set[str] = set()
    dedup: list[_SearchProvider] = []
    for p in out:
        if p.base not in seen:
            seen.add(p.base)
            dedup.append(p)
    return dedup


def _assert_safe_query(query: str) -> None:
    """Reject CR/LF/control chars in a search query before it is put on the wire (R5)."""
    if any(ord(c) < 0x20 or ord(c) == 0x7f for c in query):
        raise FetchFailed("refused control characters in search query",
                          details={"kind": "refused"})


def _search_result_urls(raw: bytes, limit: int) -> "list[str]":
    """Extract up to ``limit`` UNIQUE result URLs from a search-provider response: JSON
    ``data[]``/``results[]`` objects with a ``url`` field (Jina ``s.jina.ai`` JSON), or a
    bare list of URL strings, else a regex sweep of ``http(s)`` URLs. Bounded + deduped so a
    huge / HTML-error body can't materialise an unbounded junk list (P-3) and the same URL
    isn't fetched twice (L-4)."""
    text = _decode_bytes(raw)
    out: list[str] = []
    seen: set[str] = set()

    def _add(u) -> None:
        if isinstance(u, str) and u.startswith(("http://", "https://")) and u not in seen:
            seen.add(u)
            out.append(u)

    try:
        data = json.loads(text)
    except ValueError:
        for m in re.finditer(r'https?://[^\s)>"\'\]]+', text):  # bounded: stop at `limit`
            _add(m.group(0))
            if len(out) >= limit:
                break
        return out
    items: list = []
    if isinstance(data, dict):
        items = data.get("data") or data.get("results") or []
    elif isinstance(data, list):
        items = data
    for it in items:
        _add(it.get("url") if isinstance(it, dict) else it)
        if len(out) >= limit:
            break
    return out


def run_search(query: str, opts) -> "list[AcquireResult]":
    """Web search → top-N results → list of :class:`AcquireResult` (R9).

    Vendor-agnostic: tries each search provider in order, falling through on provider-down;
    extracts result URLs and fetches EACH through the full FETCH ladder (:func:`_acquire_url`)
    so every result inherits per-result Jina/local fallback. A result whose own ladder fails
    is skipped (not fatal). A healthy search with zero results returns ``[]`` (caller emits a
    note, exit 0); only an all-providers-down state raises one typed FetchFailed."""
    global _RATE_LIMITER
    rate = getattr(opts, "rate_limit", None)
    _RATE_LIMITER = _RateLimiter(rate) if rate else None  # throttle covers the whole search run
    _assert_safe_query(query)
    max_results = getattr(opts, "max_results", 5) or 5
    max_bytes = getattr(opts, "max_bytes", None)
    retries = getattr(opts, "retries", 2)

    urls: list[str] | None = None
    any_ok = False
    tried: list[dict] = []
    for prov in _search_providers(opts):
        req = prov.base + quote(query, safe=_READER_TARGET_SAFE)
        headers = {"Accept": "application/json", "X-Respond-With": "no-content"}
        if prov.token:
            headers["Authorization"] = f"Bearer {prov.token}"
        try:
            raw = _http_get_bytes(req, max_bytes=max_bytes, retries=retries,
                                  extra_headers=headers)
        except FetchFailed as exc:
            tried.append({"engine": prov.name, "kind": exc.details.get("kind", "unreachable")})
            continue  # provider-down → next search provider
        any_ok = True
        found = _search_result_urls(raw, max_results)
        if found:
            urls = found
            break
    if urls is None:
        if any_ok:
            return []  # healthy search, zero results → not an error
        raise FetchFailed(
            f"search failed for query {query!r} (all providers exhausted)",
            details={"kind": "all_engines_failed", "tried": tried},
        )

    # SSRF (S-1): a search result URL is attacker-influenceable, so do NOT let it escalate to
    # the un-network-hardened chrome tier in non-explicit-chrome modes — chrome follows
    # redirects to internal hosts. chrome is allowed only if the user explicitly chose it.
    allow_chrome = (getattr(opts, "engine", "auto") or "auto").lower() == "chrome"
    results: list[AcquireResult] = []
    for u in urls[:max_results]:
        try:
            results.append(_acquire_url(u, opts, allow_chrome=allow_chrome))
        except (FetchFailed, EngineNotInstalled):
            continue  # a result whose own ladder fails is skipped, not fatal
    return results


# NOTE: the former ``_fetch_jina_html`` is gone — the ``jina`` engine now flows through the
# generic remote-reader tier (``_fetch_remote_html`` → ``_remote_providers`` →
# ``_build_reader_request``), where ``jina`` is one provider among many (TASK 023 R2/R3).


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


_MW_NONCONTENT_NS = {"special", "media"}  # virtual namespaces with no Parsoid REST HTML


def _mediawiki_rest_variant(url: str) -> str | None:
    """Wikipedia ``/wiki/<Title>`` → the Parsoid REST ``page/html`` endpoint (R-7).

    The canonical ``/wiki/`` page is chrome-heavy and our (pdf-mastered) ``preprocess``
    strips its body to nothing — a silent-empty conversion. The REST endpoint
    ``/api/rest_v1/page/html/<Title>`` returns just the clean article HTML, which flows
    through the normal pipeline. Provenance (``base_url`` / ``source``) stays the canonical
    ``/wiki/`` URL; the REST HTML's ``<base href>`` resolves its relative links/images.

    Scoped to article namespaces — ``Special:`` / ``Media:`` (search, uploads) have no
    stable REST HTML, so they are left to the normal path."""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if not (host == "wikipedia.org" or host.endswith(".wikipedia.org")):
        return None
    m = re.match(r"/wiki/(.+)$", p.path)
    if not m:
        return None
    title = m.group(1)
    if title.split(":", 1)[0].lower() in _MW_NONCONTENT_NS:
        return None
    host = host.replace(".m.wikipedia.org", ".wikipedia.org")  # mobile host → API host
    return f"https://{host}/api/rest_v1/page/html/{title}"


def _arxiv_html_variant(url: str) -> str | None:
    """arXiv ``/abs/<id>`` or ``/pdf/<id>`` → the full-text ``/html/<id>`` rendering (R-9).

    ``/abs/`` is only the abstract landing page and ``/pdf/`` is a binary PDF; ``/html/``
    carries the full article — when it exists. Older PDF-only papers 404 on ``/html/``,
    which :func:`_acquire_url` turns into an actionable "use the pdf skill" hint.

    Matched on the parsed PATH (not the whole URL) so a ``?context=cs.LG`` query or ``#S1``
    fragment — both common on real arXiv links — does not defeat the rewrite."""
    p = urlparse(url)
    if (p.hostname or "").lower() not in ("arxiv.org", "www.arxiv.org"):
        return None
    m = re.match(r"(?i)/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?/?$", p.path)
    if not m:
        return None
    return f"https://arxiv.org/html/{m.group(1)}"


# The (?<![\w-]) lookbehind keeps this from matching an attribute-PREFIXED href (e.g.
# data-href / x-href): \b alone treats the `-` as a boundary, so it would otherwise hijack
# the match from the real href on the same tag and leave that one un-absolutized.
_A_HREF_RE = re.compile(r'(<a\b[^>]*?(?<![\w-])href=["\'])([^"\']+)(["\'])', re.IGNORECASE)


def _absolutize_links(html: str, page_url: str) -> str:
    """Resolve relative ``<a href>`` against an in-document ``<base href>`` — but ONLY when
    the page declares one. Parsoid/Wikipedia-REST + arXiv ship ``<base href>`` and emit
    ``./Title`` relative links that are dead in a clipped note; resolving them per the HTML
    ``<base>`` spec makes them real URLs. Pages WITHOUT ``<base>`` are returned untouched
    (no behaviour change for the common case). In-page ``#frag`` anchors and
    non-navigational schemes (``mailto:`` / ``tel:`` / ``javascript:`` / ``data:`` /
    protocol-relative) are preserved verbatim."""
    m = _BASE_HREF_RE.search(html)
    if not m:
        return html
    base = urljoin(page_url, m.group(1))

    def _sub(mt: "re.Match[str]") -> str:
        href = mt.group(2)
        if href.startswith("#") or re.match(r"^(?:[a-z][a-z0-9+.\-]*:|//)", href, re.I):
            return mt.group(0)  # fragment / scheme: / protocol-relative → leave alone
        return f"{mt.group(1)}{urljoin(base, href)}{mt.group(3)}"

    return _A_HREF_RE.sub(_sub, html)


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


_MD_CONTENT_MARK = re.compile(r'(?ims)^Markdown Content:\s*\n')
# A reader that ignored the markdown ask returns HTML. Detect it broadly (doctype / xml-decl /
# common block tags) so trust-mode falls back to the pipeline (L-2). Biased toward detecting
# HTML: a false positive (markdown-with-inline-HTML) is SAFE — it just routes through turndown.
_LOOKS_HTML = re.compile(
    r'(?is)<(?:!doctype\b|\?xml\b|html\b|head\b|body\b|div\b|article\b|main\b|'
    r'section\b|nav\b|header\b|footer\b|table\b|ul\b|ol\b|h[1-6]\b)')


def _split_remote_markdown(md: str, url: str) -> "tuple[SourceMeta, str]":
    """Trust-markdown helper (R4): lift a Jina-style ``Title:`` / ``URL Source:`` preamble
    into :class:`SourceMeta` and return the body after ``Markdown Content:`` (if present).
    A reader that returns pure Markdown (no preamble) → ``(SourceMeta(url), md)`` unchanged."""
    head = md[:2000]
    tm = re.search(r'(?im)^Title:\s*(.+)$', head)
    um = re.search(r'(?im)^URL Source:\s*(\S+)$', head)
    title = _clean_text(tm.group(1)) if tm else None
    src = (_clean_text(um.group(1)) if um else None) or url
    cm = _MD_CONTENT_MARK.search(md)
    body = md[cm.end():] if cm else md
    return SourceMeta(url=src, title=title), body


def _assert_safe_target(target: str) -> None:
    """Reject CR/LF/control chars in a target URL before it is concatenated onto a reader
    base (TASK 023 R5 — request-splitting / header-injection / SSRF-via-injection guard).
    The operator-set reader base is trusted; the target is not. Raises FetchFailed(refused)."""
    if any(ord(c) < 0x20 or ord(c) == 0x7f for c in target):
        raise FetchFailed(
            f"refused control characters in target URL: {_redact(target)}",
            details={"url": _redact(target), "kind": "refused"})


# --------------------------------------------------------------------------- #
# Fetch tiers (TASK 023 R1/R3) — each returns (html, engine_label) or raises
# _TierUnavailable (escalate) / FetchFailed (terminal target) / EngineNotInstalled.
# --------------------------------------------------------------------------- #
def _tier_lite(target: str, opts) -> "tuple[str, str]":
    """Local lite tier: httpx + trafilatura, with proactive clean-source site-variant
    rewrites (arXiv/Wikipedia/HackerNoon) preserved. In ``auto`` a thin/JS-shell body
    escalates (raise _TierUnavailable("thin")). Terminal target conditions (arXiv-no-html /
    pdf / binary / 404 / auth) raise FetchFailed; provider/transient blocks (403/429/5xx/
    transport) raise _TierUnavailable for the ladder to fall through."""
    max_bytes = getattr(opts, "max_bytes", None)
    retries = getattr(opts, "retries", 2)
    arxiv_v = _arxiv_html_variant(target)
    mw_v = _mediawiki_rest_variant(target)
    nojs_v = _nojs_variant(target)
    fetch_url = arxiv_v or mw_v or nojs_v or target
    try:
        page_html = _fetch_lite_html(fetch_url, max_bytes, retries=retries)
    except FetchFailed as exc:
        status = exc.details.get("status")
        kind = exc.details.get("kind")
        if arxiv_v and status == 404:
            raise FetchFailed(
                f"arXiv has no HTML version for {_redact(target)} (older PDF-only paper). "
                "Fetch the PDF and convert it with the pdf skill (scripts/pdf_extract.py).",
                details={"url": _redact(target), "kind": "arxiv_no_html", "status": 404},
            ) from exc
        if kind in _TERMINAL_TARGET_KINDS:
            raise  # terminal target condition (no other tier can fix it)
        raise _TierUnavailable(kind or "unreachable", status) from exc
    label = ("lite+arxiv-html" if arxiv_v else "lite+restapi" if mw_v
             else "lite+nojs" if nojs_v else "lite")
    if (getattr(opts, "engine", "auto") or "auto").lower() == "auto" \
            and not _looks_substantial(page_html):
        raise _TierUnavailable("thin")  # JS shell → escalate
    return page_html, label


def _tier_chrome(target: str, opts) -> "tuple[str, str]":
    """Headless-Chrome tier. EngineNotInstalled propagates (the ladder makes it terminal for
    explicit ``--engine chrome``, fall-through otherwise); a render error becomes
    _TierUnavailable."""
    try:
        page_html = _fetch_chrome_html(target, opts)
    except FetchFailed as exc:
        raise _TierUnavailable(exc.details.get("kind") or "chrome_failed",
                               exc.details.get("status")) from exc
    return page_html, "chrome"


def _tier_remote(target: str, opts) -> "tuple[str, str]":
    """Remote-reader tier (vendor-agnostic; jina default). Delegates to
    :func:`_fetch_remote_html` (provider loop + classification)."""
    return _fetch_remote_html(target, opts)


def _url_tiers(engine: str, allow_chrome: bool = True):
    """Ordered (name, tier_fn) for the engine (TASK 023 §15.2). ``auto`` is local-first;
    ``jina``/``remote`` are remote-first with local fallback; ``lite``/``chrome`` are a
    single explicit tier. ``allow_chrome=False`` drops the chrome tier (used for
    attacker-influenceable search-result fetches — S-1)."""
    if engine in ("jina", "remote"):
        tiers = [("remote", _tier_remote), ("lite", _tier_lite), ("chrome", _tier_chrome)]
    elif engine == "lite":
        tiers = [("lite", _tier_lite)]
    elif engine == "chrome":
        tiers = [("chrome", _tier_chrome)]
    else:
        tiers = [("lite", _tier_lite), ("chrome", _tier_chrome), ("remote", _tier_remote)]
    if not allow_chrome:
        tiers = [t for t in tiers if t[0] != "chrome"]
    return tiers


def _acquire_url(input_ref: str, opts, *, allow_chrome: bool = True) -> AcquireResult:
    """URL fetch via the resilient tier ladder (TASK 023 R1/R3/R6): try each tier in order,
    falling through on provider/engine unavailability, surfacing a terminal target condition
    immediately, and raising exactly ONE typed FetchFailed (kind=all_engines_failed, with a
    ``tried`` trace) only when every viable tier is exhausted — never a bare traceback.
    Returns RAW page HTML (web_clean cleans downstream); trafilatura supplies metadata."""
    _assert_safe_target(input_ref)  # CR/LF/control-char injection guard (R5)
    engine = (getattr(opts, "engine", "auto") or "auto").lower()
    explicit_chrome = engine == "chrome"
    tried: list[dict] = []

    def _record(name: str, kind: str, status: int | None = None) -> None:
        entry: dict = {"engine": name, "kind": kind}  # NB: no URL in the trace (no leak)
        if status is not None:
            entry["status"] = status
        tried.append(entry)

    for name, tier_fn in _url_tiers(engine, allow_chrome):
        try:
            page_html, label = tier_fn(input_ref, opts)
        except _TierUnavailable as tu:
            _record(name, tu.kind, tu.status)
            continue
        except EngineNotInstalled:
            if explicit_chrome:
                raise  # explicit --engine chrome with no Playwright → terminal exit 3
            _record(name, "engine_not_installed")
            continue
        except FetchFailed as ff:  # terminal target condition (arxiv_no_html/pdf/binary/404/auth)
            _record(name, ff.details.get("kind") or "fetch_failed", ff.details.get("status"))
            ff.details["tried"] = tried
            raise
        remote_md = (name == "remote"
                     and (getattr(opts, "remote_format", "html") or "html") == "markdown")
        # Trust-mode (R4): use the reader's own clean Markdown; bypass web_clean+turndown.
        # Defensive: if the reader IGNORED the markdown ask and returned HTML, fall back to the
        # normal pipeline rather than emitting raw HTML as "markdown".
        if remote_md and not _LOOKS_HTML.search(page_html[:512].lstrip("﻿ \t\r\n")):
            meta, body = _split_remote_markdown(page_html, input_ref)
            return AcquireResult(
                html="", base_url=input_ref, mode="url", engine=label,
                content_kind="markdown", markdown=body, source_meta=meta, images={},
            )
        page_html = _absolutize_links(_absolutize_img_srcs(page_html, input_ref), input_ref)
        return AcquireResult(
            html=page_html, base_url=input_ref, mode="url", engine=label,
            source_meta=_trafilatura_meta(page_html, input_ref), images={},
        )

    raise FetchFailed(
        f"all fetch engines failed for {_redact(input_ref)} (tried "
        f"{', '.join(t['engine'] for t in tried) or 'none'})",
        details={"url": _redact(input_ref), "kind": "all_engines_failed", "tried": tried},
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

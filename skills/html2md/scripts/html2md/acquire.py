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
from pathlib import Path
from urllib.parse import urljoin, urlparse

from web_clean import extract_archive

from .exceptions import BadInput, EngineNotInstalled, FetchFailed
from .model import AcquireResult, SourceMeta

_UA = "Mozilla/5.0 (compatible; html2md/0.1; +https://example.invalid/html2md)"
_LITE_SUBSTANTIAL_CHARS = 200  # auto-fallback: < this much extracted text ⇒ JS shell

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
    date = (
        _meta_content(html, "property", "article:published_time")
        or _meta_content(html, "name", "date")
    )
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


def _redact(url: str) -> str:
    """Drop query/userinfo from a URL for error messages (no secret/token leak)."""
    p = urlparse(url)
    netloc = p.hostname or ""
    if p.port:
        netloc += f":{p.port}"
    return f"{p.scheme}://{netloc}{p.path}"


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
            details={"url": _redact(url)},
        )
    if not _host_is_public(parsed.hostname or ""):
        raise FetchFailed(
            f"refused private/internal/unresolvable target: {_redact(url)}",
            details={"url": _redact(url)},
        )


def _http_get_bytes(url: str, *, max_bytes: int | None, timeout: float = 20.0,
                    max_redirects: int = 5) -> bytes:
    """Fetch ``url`` over HTTP(S) → bytes. SSRF-safe, streaming, bounded.

    SSRF/DoS posture (§7): http(s) only; **every** hop (initial + each redirect) is
    re-checked against :func:`_host_is_public` so a redirect to an internal/metadata
    host is refused; redirects are followed manually (cap ``max_redirects``); the body
    is read as a **stream** and aborted the moment it passes ``max_bytes`` (so a
    malicious server cannot OOM the process); bounded timeout; no credential
    forwarding (httpx default). Raises :class:`FetchFailed` (exit 10). This is the
    single network seam — tests monkeypatch it for offline runs.
    """
    import httpx

    current = url
    with httpx.Client(follow_redirects=False, timeout=timeout,
                      headers={"User-Agent": _UA}) as client:
        for _ in range(max_redirects + 1):
            _assert_public_http(current)  # re-checked on every hop (anti-SSRF)
            try:
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
            except FetchFailed:
                raise
            except Exception as exc:  # noqa: BLE001 — transport/HTTP error → clean error
                raise FetchFailed(
                    f"fetch failed for {_redact(current)}: {type(exc).__name__}",
                    details={"url": _redact(current)},
                ) from exc
    raise FetchFailed(
        f"too many redirects (> {max_redirects}) for {_redact(url)}",
        details={"url": _redact(url)},
    )


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
    """Frontmatter metadata via trafilatura (title/date/author), OG-parser fallback."""
    try:
        import trafilatura
        doc = trafilatura.extract_metadata(page_html)
    except Exception:  # noqa: BLE001
        doc = None
    if doc is not None:
        meta = SourceMeta(
            url=_clean_text(getattr(doc, "url", None)) or url,
            title=_clean_text(getattr(doc, "title", None)),
            date=_clean_text(getattr(doc, "date", None)),
            author=_clean_text(getattr(doc, "author", None)),
        )
        if meta.title:
            return meta
    return _meta_from_html(page_html, url=url)


def _fetch_lite_html(url: str, max_bytes: int | None) -> str:
    """httpx GET → decoded raw page HTML (offline cleaning is done later by web_clean).

    Guards against non-HTML payloads: a PDF or other binary blob must fail with a clear
    message — NOT be fed to turndown (which blows the Node call stack on binary input).
    """
    raw = _http_get_bytes(url, max_bytes=max_bytes)
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
                page = browser.new_page(user_agent=_UA)
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


def _resolve_url_image(src: str, opts) -> bytes | None:
    """Fetch a remote image (for emit's url-mode download). None on any failure —
    a broken image must never abort the conversion. Bounded by ``--max-bytes``."""
    if urlparse(src).scheme not in ("http", "https"):
        return None
    try:
        return _http_get_bytes(src, max_bytes=getattr(opts, "max_bytes", None))
    except FetchFailed:
        return None


def _acquire_url(input_ref: str, opts) -> AcquireResult:
    """URL fetch: lite (httpx+trafilatura) by default, auto-fallback to Chrome for
    JS/SPA shells, or explicit ``--engine chrome``. Returns RAW page HTML (web_clean
    does the uniform cleaning downstream); trafilatura supplies frontmatter metadata."""
    engine = (getattr(opts, "engine", "auto") or "auto").lower()
    max_bytes = getattr(opts, "max_bytes", None)

    page_html: str | None = None
    used: str | None = None
    if engine in ("lite", "auto"):
        page_html = _fetch_lite_html(input_ref, max_bytes)
        used = "lite"
        if engine == "auto" and not _looks_substantial(page_html):
            page_html, used = None, None  # JS shell → escalate to Chrome
    if page_html is None:  # explicit chrome, or auto-fallback
        page_html = _fetch_chrome_html(input_ref)
        used = "chrome"

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
    scheme = urlparse(input_ref).scheme.lower()
    if scheme in ("http", "https"):
        return _acquire_url(input_ref, opts)
    fmt = _dispatch_format(input_ref)
    if fmt == "archive":
        return _acquire_archive(Path(input_ref), opts)
    return _acquire_file(Path(input_ref), opts)

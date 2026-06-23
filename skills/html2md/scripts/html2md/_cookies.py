"""TASK 024 — hardened cookie-file loading for the Chrome auth path (html2md-owned, NOT gated).

The file-hardening half (symlink-reject, **reject group AND world bits via `st_mode & 0o077`**,
sanitized errors) is LIFTED from `skills/transcript-fetcher/scripts/sources/_cookies.py` and
**tightened** (that source rejects world-only) for the multi-tenant server threat model. The
Netscape→Playwright-cookie-dict conversion is NEW html2md code (the source's urllib opener /
redirect handler is irrelevant to the Playwright transport).

TRACKING NOTE (do NOT silently fork): keep `load_cookie_jar` in sync with the transcript-fetcher
loader when its hardening changes. Implemented in 024-04.
"""
from __future__ import annotations

import stat as _stat
from http.cookiejar import MozillaCookieJar
from pathlib import Path

from .exceptions import BadInput


def load_cookie_jar(path: Path) -> MozillaCookieJar:
    """Load a Netscape ``cookies.txt`` into a :class:`MozillaCookieJar`, hardened.

    Lifted from ``transcript-fetcher/_cookies.py`` and **tightened**: rejects symlinks, and
    rejects **group- AND world-accessible** files (``st_mode & 0o077`` — the source rejects
    world-only) for the multi-tenant server threat model. Error messages are sanitised — never
    echo the file's contents or the stdlib LoadError's line snippet. Raises :class:`BadInput`."""
    path = Path(path)
    name = path.name
    if path.is_symlink():
        raise BadInput(f"cookies file must not be a symlink: {name}", details={"path": name})
    if not path.is_file():
        raise BadInput(f"cookies file not found / not a regular file: {name}",
                       details={"path": name})
    try:
        st = path.stat()
    except OSError as exc:
        raise BadInput(f"cannot stat cookies file: {name}", details={"path": name}) from exc
    if st.st_mode & 0o077:  # group OR world accessible → bearer-credential leak risk
        raise BadInput(
            f"cookies file is group/world-accessible: {name} — chmod 600 before re-running",
            details={"path": name})
    jar = MozillaCookieJar()
    try:
        jar.load(str(path), ignore_discard=True, ignore_expires=True)
    except (OSError, ValueError) as exc:  # sanitized — do NOT echo exc (LoadError leaks lines)
        raise BadInput(
            f"failed to parse cookies file {name}: {type(exc).__name__} "
            "— expected Netscape cookies.txt format",
            details={"path": name}) from None
    return jar


def to_playwright_cookies(jar: MozillaCookieJar) -> list:
    """Convert jar entries → Playwright ``add_cookies`` dicts. Domain/path/Secure are preserved
    so Chromium's native cookie-domain matching keeps each cookie scoped to its own host."""
    out: list = []
    for c in jar:
        cookie = {
            "name": c.name,
            "value": c.value or "",
            "domain": c.domain,
            "path": c.path or "/",
            "secure": bool(c.secure),
            "httpOnly": False,        # Netscape format does not encode httpOnly
            "sameSite": "Lax",
        }
        if c.expires:
            cookie["expires"] = int(c.expires)
        out.append(cookie)
    return out

"""Netscape cookies.txt loader for auth-walled sources.

The Skool adapter needs authenticated requests, but pulling in
``requests`` just for cookie handling would be wasteful — stdlib's
:class:`http.cookiejar.MozillaCookieJar` reads the same format
that browser extensions like *Get cookies.txt LOCALLY* export.

This module wraps that and builds a ready-to-use
``urllib.request.OpenerDirector`` with:

- The provided cookie jar.
- Only ``HTTPHandler`` + ``HTTPSHandler`` registered — no ``FileHandler``
  or ``FTPHandler`` from the default chain, so a redirect to a
  ``file://`` URL cannot be honored.
- A restricted redirect handler that enforces the host allowlist
  passed by the caller and rejects non-``http``/``https`` schemes.

These defenses matter because the auth cookies make the opener a
high-trust handle: a misbehaving (or compromised) origin that issues a
``302`` to an internal address, a metadata endpoint, or a file URL
must not be followed.
"""
from __future__ import annotations

import os
import stat as _stat
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Iterable, Optional
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import (
    HTTPCookieProcessor,
    HTTPDefaultErrorHandler,
    HTTPErrorProcessor,
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    OpenerDirector,
)


# A current desktop UA — Skool's CDN refuses obvious curl/python signatures.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.5 Safari/605.1.15"
)


class CookieFileError(RuntimeError):
    """Raised when the cookies file cannot be loaded."""


def load_cookie_jar(path: Path) -> MozillaCookieJar:
    """Load a Netscape cookies.txt into a :class:`MozillaCookieJar`.

    Hardening:
        - Refuses to follow symlinks (``Path.is_symlink``).
        - Refuses world-readable files (any "other" read/write/execute
          bit set) — cookie files are bearer credentials and should
          live at mode ``0600``.
        - Sanitises error messages: never echoes the offending file's
          contents or the loader's exception text (which may include
          a line snippet on parse failure).

    Raises :class:`CookieFileError` with a non-revealing message on any
    failure.
    """
    path = Path(path)
    name = path.name  # for use in user-facing error messages
    if path.is_symlink():
        raise CookieFileError(
            f"cookies file must not be a symlink: {name}"
        )
    if not path.exists():
        raise CookieFileError(f"cookies file not found: {name}")
    if not path.is_file():
        raise CookieFileError(f"cookies path is not a regular file: {name}")
    try:
        st = path.stat()
    except OSError:
        raise CookieFileError(f"cannot stat cookies file: {name}")
    if st.st_mode & (_stat.S_IROTH | _stat.S_IWOTH | _stat.S_IXOTH):
        raise CookieFileError(
            f"cookies file is world-readable: {name} — "
            "tighten permissions to 0600 before re-running"
        )
    jar = MozillaCookieJar()
    try:
        # ignore_discard=True ensures session cookies (Skool's main login)
        # actually get used; the default would drop them.
        jar.load(str(path), ignore_discard=True, ignore_expires=True)
    except (OSError, ValueError) as e:
        # Do NOT echo `e` — stdlib's LoadError includes file line snippets
        # on parse failure, which leaks unrelated file contents if the
        # path was symlink-swapped or the user pointed at the wrong file.
        raise CookieFileError(
            f"failed to parse cookies file {name}: {type(e).__name__} — "
            "expected Netscape cookies.txt format"
        ) from None
    return jar


class _RestrictedRedirectHandler(HTTPRedirectHandler):
    """Enforce an allowlist on every redirect target host + scheme."""

    def __init__(self, allowed_hosts: Iterable[str]) -> None:
        super().__init__()
        self._allowed = frozenset(h.lower() for h in allowed_hosts)

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        parsed = urlparse(newurl)
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").lower()
        if scheme not in ("http", "https"):
            raise HTTPError(
                req.full_url, code,
                f"refusing redirect to non-http(s) scheme: {scheme!r}",
                headers, fp,
            )
        if self._allowed and host not in self._allowed:
            raise HTTPError(
                req.full_url, code,
                f"refusing redirect off-allowlist: {host!r}",
                headers, fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_authenticated_opener(
    cookies_file: Optional[Path],
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    allowed_hosts: Optional[Iterable[str]] = None,
) -> OpenerDirector:
    """Build a minimal-handler opener with cookies + UA installed.

    The returned :class:`OpenerDirector` is built from scratch (NOT via
    :func:`urllib.request.build_opener`) so the default handler chain's
    ``FileHandler``/``FTPHandler`` are NOT present — a redirect to a
    ``file://`` or ``ftp://`` URL will fail rather than be honored.

    Args:
        cookies_file: Optional Netscape cookies.txt path. ``None`` builds
            an opener with no cookie jar.
        user_agent: ``User-Agent`` header to send on every request.
        allowed_hosts: Iterable of lowercase hostnames; redirects to any
            host NOT in this set raise :class:`urllib.error.HTTPError`.
            ``None`` or empty disables host filtering (still scheme-checked).
    """
    opener = OpenerDirector()
    opener.add_handler(HTTPHandler())
    opener.add_handler(HTTPSHandler())
    opener.add_handler(HTTPDefaultErrorHandler())
    opener.add_handler(HTTPErrorProcessor())
    opener.add_handler(_RestrictedRedirectHandler(allowed_hosts or ()))
    if cookies_file is not None:
        jar = load_cookie_jar(cookies_file)
        opener.add_handler(HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", user_agent),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    return opener

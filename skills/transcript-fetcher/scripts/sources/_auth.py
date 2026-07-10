"""Skill-local per-host cookie resolution via ``~/.transcript-fetcher/``.

Mirrors the **`html` skill's `~/.html/` auth-map** convention (TASK 024/026), but
cookies-only — every source here authenticates with a Netscape ``cookies.txt``
that yt-dlp consumes via ``--cookies`` (and the Skool adapter via its stdlib
opener). The home folder ``~/.transcript-fetcher/`` holds the cookie files and an
optional ``auth-map.json``::

    { "x.com":      {"cookies_file": "~/.transcript-fetcher/x-cookies.txt"},
      "youtube.com":{"cookies_file": "~/.transcript-fetcher/yt-cookies.txt"} }

Resolution order for a given URL (first match wins):

  1. an explicit ``--cookies-file`` (passed through verbatim — the operator's
     deliberate choice; unchanged behaviour);
  2. an **auth-map** entry (``--auth-map`` / ``TRANSCRIPT_FETCHER_AUTH_MAP`` /
     ``~/.transcript-fetcher/auth-map.json``) matched to the URL host by
     label-boundary suffix (most-specific key wins — NOT eTLD+1, so a key
     ``x.com`` never leaks onto ``evil-x.com``);
  3. the **convention** file ``~/.transcript-fetcher/<host>-cookies.txt`` if it
     exists;
  4. the SAME convention file with a single well-known **mirror-prefix** label
     stripped from the host (``www``/``mobile``/``m`` — e.g. ``www.x.com`` and
     ``mobile.x.com`` both also try ``x.com-cookies.txt``) if THAT file exists
     and step 3 did not already match. This mirrors the auth-map's
     label-boundary suffix semantics for the three well-known mirror prefixes
     ONLY — a generic parent-domain walk (trying every suffix of the host)
     would widen the cookie-leak surface far beyond what a single
     conventional mirror label warrants, so it is deliberately NOT
     implemented;
  5. ``None`` (anonymous — the skill then surfaces ``SourceAuthError`` only if
     the source actually returns 401/403).

Auth-map and convention-discovered files are hardened like a bearer credential
(symlink-reject + regular-file + ``0600``); a tamperable map/cookies file could
redirect an authenticated fetch to an attacker's session. Malformed input fails
loud (``AuthMapError`` → CLI exit 2), never silently routes the wrong credential.

Trust model: ``~/.transcript-fetcher/`` lives under the invoking user's home, so the
hardening defends against a *too-loose-permission* mistake, not a same-UID attacker
(anyone who can write into that dir already owns the account). The check is path-based,
so a same-UID adversary on a shared host could in principle win a symlink-swap TOCTOU
race between the stat here and yt-dlp's later ``open`` of ``--cookies`` — accepted as
out-of-scope (same-UID trust), mirroring the ``html`` skill's posture; the Skool opener
re-hardens at open time. Error messages are sanitised to the **basename** for
credential-file checks; map-*structure* errors echo the offending host key (a domain,
not a secret).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

DEFAULT_AUTH_DIR = Path("~/.transcript-fetcher").expanduser()
_ENV_AUTH_MAP = "TRANSCRIPT_FETCHER_AUTH_MAP"


class AuthMapError(ValueError):
    """Malformed / insecure auth-map or convention cookies file (CLI exit 2)."""


def _assert_secure_credential_file(path: Path, kind: str) -> None:
    """Bearer-credential gate: symlink-reject, regular-file, ``0600`` (no group/world).

    Errors are sanitised to the basename (the path may sit under a private dir).
    """
    name = path.name
    if path.is_symlink():
        raise AuthMapError(f"{kind} must not be a symlink: {name}")
    if not path.is_file():
        raise AuthMapError(f"{kind} not found / not a regular file: {name}")
    try:
        st = path.stat()
    except OSError as exc:
        raise AuthMapError(f"cannot stat {kind}: {name}") from exc
    if st.st_mode & 0o077:  # any group/world bit → credential leak / tamper risk
        raise AuthMapError(
            f"{kind} is group/world-accessible: {name} — chmod 600 before re-running"
        )


def _match_host(host: Optional[str], amap: dict) -> Optional[dict]:
    """Match ``host`` to a map entry by label-boundary domain suffix; most-specific wins.

    A key ``x.com`` matches ``x.com`` and ``*.x.com``; it never matches a sibling
    like ``evil-x.com`` or ``x.com.evil.com``. ``None`` if nothing matches. **Key the
    EXACT domain you control** — a public-suffix key like ``co.uk`` (or, were it not
    rejected at load, a bare TLD) would match every tenant under it and leak the cookie
    cross-tenant. This is deliberately NOT eTLD+1 for the same reason.
    """
    host = (host or "").lower().strip(".")
    if not host:
        return None
    best = None
    for key in amap:  # keys already lowercased/stripped at load
        if host == key or host.endswith("." + key):
            if best is None or len(key) > len(best):
                best = key
    return amap.get(best) if best else None


_MIRROR_LABELS = ("www", "mobile", "m")


def _strip_mirror_prefix(host: str) -> Optional[str]:
    """Strip a single well-known mirror-prefix label from ``host``, e.g.
    ``www.x.com`` -> ``x.com``, ``mobile.twitter.com`` -> ``twitter.com``.

    Only the three conventional mirror labels (``www``, ``mobile``, ``m``) are
    recognised, and only when they form the ENTIRE first label — ``wwwx.com``
    (no dot right after ``www``) is left untouched, never partially stripped.
    Returns ``None`` when the first label isn't one of the three, or there is
    no remaining host after it (a bare ``m``/``www`` with nothing after the
    dot is nonsensical).
    """
    label, sep, rest = host.partition(".")
    if sep and rest and label in _MIRROR_LABELS:
        return rest
    return None


def load_auth_map(path: Path) -> dict:
    """Load + harden ``auth-map.json`` (host → ``{"cookies_file": <path>}``).

    Hardened like the cookie loader (symlink / regular-file / ``0600``). Keys are
    lowercased + dot-stripped; ``cookies_file`` values are ``~``-expanded. An entry
    missing ``cookies_file``, an empty host key, or a duplicate host → ``AuthMapError``.
    """
    name = path.name
    _assert_secure_credential_file(path, "auth-map")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AuthMapError(
            f"failed to parse auth-map {name}: {type(exc).__name__} — expected a "
            "JSON object of host → {\"cookies_file\": <path>}"
        ) from None
    if not isinstance(raw, dict):
        raise AuthMapError(f"auth-map {name} must be a JSON object of host → cookies_file")
    out: dict = {}
    for host, entry in raw.items():
        if not isinstance(entry, dict):
            raise AuthMapError(f"auth-map entry for {host!r} must be an object")
        cf = entry.get("cookies_file")
        if not isinstance(cf, str) or not cf:
            raise AuthMapError(
                f"auth-map entry for {host!r} needs a string 'cookies_file' path"
            )
        key = str(host).strip().lower().strip(".")
        if not key:
            raise AuthMapError(f"auth-map has an empty host key: {host!r}")
        if "." not in key:
            # A bare label / TLD (e.g. "com") would match EVERY subdomain via the
            # label-boundary suffix rule and leak a cookie cross-tenant. Reject it —
            # key the exact domain you control (e.g. "x.com"). (A public suffix like
            # "co.uk" still has a dot; the warning in _match_host covers that case.)
            raise AuthMapError(
                f"auth-map host key {key!r} has no dot — key the EXACT domain you "
                "control (e.g. 'x.com'), never a bare label/TLD"
            )
        if key in out:
            raise AuthMapError(f"auth-map has a duplicate host entry: {key!r}")
        out[key] = {"cookies_file": os.path.expanduser(cf)}
    return out


def _auth_map_path(explicit: Optional[str]) -> Optional[Path]:
    """Pick the auth-map: explicit flag → env var → default file (only if it exists)."""
    if explicit:
        return Path(explicit).expanduser()
    env_val = os.environ.get(_ENV_AUTH_MAP)
    if env_val:
        return Path(env_val).expanduser()
    default = DEFAULT_AUTH_DIR / "auth-map.json"
    return default if default.is_file() or default.is_symlink() else None


def load_configured_auth_map(auth_map_arg: Optional[str] = None) -> Optional[dict]:
    """Resolve the configured auth-map (flag → env → default file) and load it ONCE.

    Returns the validated host→spec dict, or ``None`` when no auth-map is configured.
    Raises :class:`AuthMapError` on a malformed/insecure map. Call this once at the CLI
    entry point (before a batch loop) so a bad map fails fast (exit 2) and is not
    re-parsed per URL — then pass the result to :func:`resolve_cookies_file`.
    """
    amp = _auth_map_path(auth_map_arg)
    return load_auth_map(amp) if amp is not None else None


def resolve_cookies_file(
    url: str,
    *,
    explicit_cookies_file: Optional[Path] = None,
    auth_map: Optional[dict] = None,
) -> Optional[Path]:
    """Resolve the effective Netscape cookies.txt for ``url`` (see module docstring).

    ``auth_map`` is a **pre-loaded** dict (from :func:`load_configured_auth_map`), or
    ``None``. Returns the explicit file unchanged when given; otherwise consults the
    pre-loaded auth-map, then the ``~/.transcript-fetcher/<host>-cookies.txt`` convention
    (falling back to the same file with a well-known ``www``/``mobile``/``m`` mirror-prefix
    label stripped — see the module docstring's resolution order, step 4 — so the auth-hint
    path printed by a source adapter's exit-5 message, which already strips that label, is
    guaranteed to round-trip through this resolver).
    Auth-map / convention hits are hardened (symlink/0600). ``None`` when nothing applies.
    """
    if explicit_cookies_file is not None:
        return Path(explicit_cookies_file)

    host = (urlparse(url).hostname or "").lower().strip(".")
    if not host:
        return None

    if auth_map:
        entry = _match_host(host, auth_map)
        if entry is not None:
            cf = Path(entry["cookies_file"])
            _assert_secure_credential_file(cf, "cookies file (auth-map)")
            return cf

    conv = DEFAULT_AUTH_DIR / f"{host}-cookies.txt"
    if conv.is_file() or conv.is_symlink():
        _assert_secure_credential_file(conv, "cookies file (~/.transcript-fetcher)")
        return conv

    # Narrow mirror-prefix fallback (exact-host file above always wins when
    # both exist) — see module docstring / `_strip_mirror_prefix`.
    stripped_host = _strip_mirror_prefix(host)
    if stripped_host is not None:
        conv_stripped = DEFAULT_AUTH_DIR / f"{stripped_host}-cookies.txt"
        if conv_stripped.is_file() or conv_stripped.is_symlink():
            _assert_secure_credential_file(
                conv_stripped, "cookies file (~/.transcript-fetcher)"
            )
            return conv_stripped
    return None


__all__ = (
    "DEFAULT_AUTH_DIR",
    "AuthMapError",
    "load_auth_map",
    "load_configured_auth_map",
    "resolve_cookies_file",
)

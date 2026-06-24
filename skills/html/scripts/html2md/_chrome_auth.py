"""TASK 024 — authenticated Chrome context + login-wall detection (html-owned, NOT gated).

Resolves ONE auth source (storage_state / cookies.txt / persistent-profile) into Playwright
context kwargs (024-03), and detects a stale-session login wall (024-05). Heavy deps
(playwright) are NOT imported at module level — the offline package import stays clean.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

from .exceptions import BadInput


def _assert_secure_credential_file(path: Path, kind: str) -> None:
    """Bearer-credential file gate (symlink-reject, regular-file, ``0600``) — the SAME hardening
    `_cookies.load_cookie_jar` applies, factored out so the map's ``storage_state`` gets it too
    (vdd-multi-026 F-1). Errors sanitized to the basename (path may sit under a private dir)."""
    name = path.name
    if path.is_symlink():
        raise BadInput(f"{kind} must not be a symlink: {name}", details={"path": name})
    if not path.is_file():
        raise BadInput(f"{kind} not found / not a regular file: {name}", details={"path": name})
    try:
        st = path.stat()
    except OSError as exc:
        raise BadInput(f"cannot stat {kind}: {name}", details={"path": name}) from exc
    if st.st_mode & 0o077:  # group OR world accessible → bearer-credential leak / tamper risk
        raise BadInput(f"{kind} is group/world-accessible: {name} — chmod 600 before re-running",
                       details={"path": name})


def _cookies_spec(cookies_file: str) -> dict:
    """Hardened cookies.txt → a context spec (cookies injected, no kwargs)."""
    from . import _cookies
    jar = _cookies.load_cookie_jar(Path(cookies_file))  # hardened (024-04): symlink/0600/format
    return {"mode": "context", "kwargs": {}, "cookies": _cookies.to_playwright_cookies(jar)}


def resolve_context_kwargs(opts, target_host: str | None = None):
    """Resolve the configured auth source → a context spec, or ``None`` when no auth applies
    (anonymous render — R10 graceful degradation). Returns a dict:

      - storage_state: ``{"mode":"context", "kwargs":{"storage_state": <path>}}``
      - cookies.txt:   ``{"mode":"context", "kwargs":{}, "cookies":[<playwright dicts>]}``
      - persistent:    ``{"mode":"persistent", "kwargs":{"user_data_dir": <dir>}}``

    Precedence: a fixed single source (``--chrome-storage-state`` / ``--chrome-cookies-file`` /
    ``--chrome-user-data-dir``) wins; otherwise a per-domain **auth map** (TASK 026) is matched
    against ``target_host`` by :func:`_match_host` (label-boundary suffix; most-specific key wins)
    and the matching entry's credential is used. No match → ``None`` (anonymous render, not someone
    else's session — small blast radius). A map ``cookies_file`` is hardened by
    `_cookies.load_cookie_jar`; a map ``storage_state`` is hardened here (F-1).
    """
    ss = getattr(opts, "chrome_storage_state", None)
    cf = getattr(opts, "chrome_cookies_file", None)
    ud = getattr(opts, "chrome_user_data_dir", None)
    am = getattr(opts, "chrome_auth_map", None)
    if ss:
        return {"mode": "context", "kwargs": {"storage_state": ss}}
    if cf:
        return _cookies_spec(cf)
    if ud:
        return {"mode": "persistent", "kwargs": {"user_data_dir": ud}}
    if am and target_host:
        entry = _match_host(target_host, load_auth_map(Path(am)))
        if entry:
            if entry.get("cookies_file"):
                return _cookies_spec(entry["cookies_file"])
            if entry.get("storage_state"):
                p = Path(entry["storage_state"])
                _assert_secure_credential_file(p, "storage_state file")  # F-1: harden the map's ss
                return {"mode": "context", "kwargs": {"storage_state": str(p)}}
    return None


def _match_host(host: str | None, amap: dict):
    """Match a target host to a map entry by **label-boundary domain suffix**, most-specific key
    wins; ``None`` if nothing matches (vdd-multi-026 F-2). A key ``x.com`` matches ``x.com`` and
    ``*.x.com``; a key ``me.github.io`` matches only itself / its subdomains — NEVER a sibling
    ``evil.github.io``. This is why we DON'T use eTLD+1 (last-2-labels): that would collapse
    ``me.github.io`` / ``mybucket.s3.amazonaws.com`` to the shared apex and leak a credential
    across tenants. Key the exact domain you control."""
    host = (host or "").lower().strip(".")
    if not host:
        return None
    best = None
    for key in amap:  # keys already lowercased/stripped at load
        if host == key or host.endswith("." + key):
            if best is None or len(key) > len(best):  # most specific (longest) key wins
                best = key
    return amap.get(best) if best else None


def host_in_map(url: str, amap: dict) -> bool:
    """Does the target URL's host match an entry in a loaded auth map (suffix match)?"""
    return _match_host(urlparse(url or "").hostname, amap) is not None


def load_auth_map(path: Path) -> dict:
    """Load + harden a per-domain auth map (TASK 026). JSON object mapping a host to **exactly one**
    credential::

        { "x.com":     {"cookies_file":  "~/.html/x-cookies.txt"},
          "medium.com": {"storage_state": "~/.html/medium-state.json"} }

    Keys are lowercased + dot-stripped (matched by label-boundary suffix — :func:`_match_host`, NOT
    eTLD+1); value paths are ``~``-expanded. Hardened like the cookie loader — reject symlink /
    non-file / group-or-world access (require ``0600``) — because a tamperable map could redirect a
    render to an attacker's session. An entry naming BOTH or NEITHER credential, or a duplicate
    host key, is rejected (F-1/F-2 — fail loud, never silently route the wrong credential). A map
    ``cookies_file``/``storage_state`` is itself hardened when used (`_cookies_spec` /
    `_assert_secure_credential_file`). Errors are sanitized to the basename."""
    name = path.name
    _assert_secure_credential_file(path, "auth-map")  # symlink / regular-file / 0600
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise BadInput(f"failed to parse auth-map {name}: {type(exc).__name__} — expected a JSON "
                       "object of host → {cookies_file|storage_state}", details={"path": name}) from exc
    if not isinstance(raw, dict):
        raise BadInput(f"auth-map {name} must be a JSON object of host → "
                       "{cookies_file|storage_state}", details={"path": name})
    out: dict = {}
    for host, entry in raw.items():
        if not isinstance(entry, dict):
            raise BadInput(f"auth-map entry for {host!r} must be an object", details={"path": name})
        spec = {k: os.path.expanduser(str(entry[k]))
                for k in ("cookies_file", "storage_state") if entry.get(k)}
        if not spec:
            raise BadInput(f"auth-map entry for {host!r} needs cookies_file or storage_state",
                           details={"path": name})
        if len(spec) > 1:  # F-1: ONE credential per host — never silently pick one
            raise BadInput(f"auth-map entry for {host!r} must name ONE credential "
                           "(cookies_file OR storage_state, not both)", details={"path": name})
        key = str(host).strip().lower().strip(".")  # tolerate surrounding whitespace too
        if not key:  # an empty host key would be a silent dead entry — fail loud
            raise BadInput(f"auth-map has an empty host key: {host!r}", details={"path": name})
        if key in out:  # F-2: duplicate host → fail loud, never silently last-wins
            raise BadInput(f"auth-map has a duplicate host entry: {key!r}", details={"path": name})
        out[key] = spec
    return out


_LOGIN_PATH_SEGS = ("/login", "/signin", "/sign-in", "/i/flow/login", "/auth/login",
                    "/account/login", "/u/login")
# STRONG, conservative markers — a false positive would drop real content, so each is a phrase
# unlikely to occur in genuine article text (X-tuned first; extend per-site cautiously).
_WALL_MARKERS = ("javascript is not available",)
_WALL_PAIRS = (("continue with google", "continue with apple"),
               ("continue with phone", "continue with google"))


def is_login_wall(html: str, final_url: str) -> bool:
    """Best-effort, per-site heuristic: did a stale/expired session land on a login wall?
    Conservative (avoid dropping real content): True only on a strong signal — (a) the final URL
    is a login-class path, or (b) an unambiguous wall marker / login-provider button pair.
    Honest-scope (R5c): tuned for X first; needles kept conservative + tested. The third spec'd
    signal — "the requested ``--target-selector`` is absent from the DOM" — is **deferred**
    (reliable CSS-selector matching needs a DOM parse; a weak string heuristic would risk
    false positives that drop real content). Two strong signals only, for now."""
    from urllib.parse import urlparse
    path = (urlparse(final_url or "").path or "").lower()
    if any(seg in path for seg in _LOGIN_PATH_SEGS):
        return True
    low = (html or "")[:8000].lower()
    if any(m in low for m in _WALL_MARKERS):
        return True
    return any(a in low and b in low for a, b in _WALL_PAIRS)

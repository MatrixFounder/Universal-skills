"""TASK 024 — authenticated Chrome context + login-wall detection (html2md-owned, NOT gated).

Resolves ONE auth source (storage_state / cookies.txt / persistent-profile) into Playwright
context kwargs (024-03), and detects a stale-session login wall (024-05). Heavy deps
(playwright) are NOT imported at module level — the offline package import stays clean.
"""
from __future__ import annotations

from pathlib import Path


def resolve_context_kwargs(opts):
    """Resolve the ONE configured auth source → a context spec, or ``None`` when no auth is set
    (anonymous render — R10 graceful degradation). Returns a dict:

      - storage_state: ``{"mode":"context", "kwargs":{"storage_state": <path>}}``
      - cookies.txt:   ``{"mode":"context", "kwargs":{}, "cookies":[<playwright dicts>]}``
      - persistent:    ``{"mode":"persistent", "kwargs":{"user_data_dir": <dir>}}``

    The cookies path uses the 024-04 hardened loader (`_cookies.load_cookie_jar`).
    """
    ss = getattr(opts, "chrome_storage_state", None)
    cf = getattr(opts, "chrome_cookies_file", None)
    ud = getattr(opts, "chrome_user_data_dir", None)
    if ss:
        return {"mode": "context", "kwargs": {"storage_state": ss}}
    if cf:
        from . import _cookies
        jar = _cookies.load_cookie_jar(Path(cf))  # hardened (024-04)
        return {"mode": "context", "kwargs": {}, "cookies": _cookies.to_playwright_cookies(jar)}
    if ud:
        return {"mode": "persistent", "kwargs": {"user_data_dir": ud}}
    return None


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

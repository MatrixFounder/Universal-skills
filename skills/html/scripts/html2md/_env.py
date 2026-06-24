"""Accessor for the skill's ``HTML_*`` configuration environment variables.

A single seam for reading the ``HTML_<suffix>`` config vars (reader/search providers,
chrome auth, scroll, the no-dotenv flag) so call sites stay short and the prefix lives in
one place.
"""
from __future__ import annotations

import os


def env(suffix: str, *, default: str | None = None) -> str | None:
    """Read ``HTML_<suffix>`` from the environment (``default`` when unset or empty)."""
    value = os.environ.get("HTML_" + suffix)
    return value if value not in (None, "") else default

"""Debug-only stage logger.

Without ``--debug`` (and without ``TRANSCRIPT_FETCHER_DEBUG=1``) this is a
no-op: the success path writes NOTHING to stderr and stdout stays the pure
one-JSON-stat-per-URL contract. With debug enabled, stage lines go to **stderr**
(never stdout) so machine consumers parsing stdout are unaffected.
"""
from __future__ import annotations

import os
import sys
from typing import Callable

_TRUTHY = {"1", "true", "yes", "on"}


def debug_enabled(flag: bool) -> bool:
    """Resolve the effective debug state from the CLI flag or the env var."""
    if flag:
        return True
    return os.environ.get("TRANSCRIPT_FETCHER_DEBUG", "").strip().lower() in _TRUTHY


def make_logger(enabled: bool) -> Callable[[str], None]:
    """Return a ``log(msg)`` callable. No-op when ``enabled`` is False."""

    def _log(msg: str) -> None:
        if enabled:
            sys.stderr.write(f"[transcript-fetcher] {msg}\n")
            sys.stderr.flush()

    return _log

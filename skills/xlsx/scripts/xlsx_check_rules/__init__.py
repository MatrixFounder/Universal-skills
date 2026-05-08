"""xlsx_check_rules — declarative business-rule validator (xlsx-7).

Public entrypoint is `main()`, re-exported for the shim. Internal
modules use sibling-relative imports; importing through the shim
from inside this package is forbidden (re-import cycle).
"""
from __future__ import annotations

from .cli import main  # noqa: F401

__all__ = ["main"]

"""xlsx_check_rules — declarative business-rule validator (xlsx-7).

Public entrypoint is `main()`, re-exported for the shim. Internal
modules use sibling-relative imports; importing through the shim
from inside this package is forbidden (re-import cycle).

S1 (Sarcasmotron iter-2): `defusedxml.defuse_stdlib()` is invoked at
PACKAGE-import time so the hardened parsers are installed BEFORE any
submodule imports openpyxl/lxml. Defense-in-depth — openpyxl prefers
lxml which has its own hardening, but if openpyxl ever falls back to
stdlib `xml.etree.ElementTree`, our patch is in place.
"""
from __future__ import annotations

try:  # pragma: no cover — defusedxml is in requirements.txt
    import defusedxml
    defusedxml.defuse_stdlib()
except ImportError:
    pass

from .cli import main  # noqa: F401

__all__ = ["main"]

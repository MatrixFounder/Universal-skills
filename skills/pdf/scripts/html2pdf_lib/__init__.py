"""html2pdf internals — preprocessing, reader-mode, archive extractors, render.

The CLI lives at `skills/pdf/scripts/html2pdf.py` and delegates to:
  * `archives.extract_mhtml` / `archives.extract_webarchive` for archive inputs
  * `render.convert` for the actual weasyprint pipeline

`SUPPORTED_EXTENSIONS` and `RenderTimeout` are re-exported here so the CLI
imports a single name (`html2pdf_lib`) for everything except archive helpers.

sys.path requirement: `render.py` does `from md2pdf import DEFAULT_CSS,
PAGE_SIZES`. `md2pdf` is a sibling module in `skills/pdf/scripts/`, NOT part
of this package. When the CLI is launched directly (`python3 html2pdf.py …`),
Python adds the script's directory to `sys.path` and the import resolves
naturally. In-process consumers (`from html2pdf_lib import convert` from a
notebook or another tool) MUST add `skills/pdf/scripts/` to `sys.path` BEFORE
importing this package, or the import will fail at package-load time with
`ModuleNotFoundError: md2pdf`. Same applies to `_errors` (cross-skill error
envelope) used by the CLI shim itself.
"""
from .chrome_engine import ChromeEngineUnavailable
from .render import RenderTimeout, SUPPORTED_ENGINES, SUPPORTED_EXTENSIONS, convert

__all__ = [
    "ChromeEngineUnavailable",
    "RenderTimeout",
    "SUPPORTED_ENGINES",
    "SUPPORTED_EXTENSIONS",
    "convert",
]

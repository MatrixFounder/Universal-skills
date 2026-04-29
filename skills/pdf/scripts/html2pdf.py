#!/usr/bin/env python3
"""Render a web page or HTML document to a typeset PDF via weasyprint.

Supported input formats:

  .html / .htm    — standard HTML file with optional sibling assets.
  .mhtml / .mht   — MIME HTML archive (browser "Save as → Webpage, Single File").
  .webarchive     — Apple WebKit archive (Safari "Save as → Web Archive").

Parallel of `md2pdf.py` for HTML inputs — common for BI-dashboard
exports, Confluence pages, pre-rendered reports, and saved web pages.
Reuses md2pdf's `DEFAULT_CSS` so an unstyled `<h1>…<p>` renders the
same as Markdown output; embedded `<style>` blocks cascade after the
weasyprint stylesheet and naturally override defaults.

Usage:
    python3 html2pdf.py INPUT OUTPUT.pdf
        [--page-size letter|a4|legal] [--css EXTRA.css]
        [--base-url DIR] [--no-default-css] [--reader-mode]

For .mhtml and .webarchive inputs, sub-resources (images, CSS, fonts)
are extracted to a temporary directory that is removed after conversion.
`--base-url` is still accepted and overrides the automatic base for
plain .html inputs; it is ignored for archive formats (the extracted
temp dir always serves as the base).

`--no-default-css` skips the bundled stylesheet for HTML that ships
its own complete styling (BI dashboards, branded reports). The
`--css EXTRA.css` flag is independent and stacks regardless.
Structural normalisation CSS (NORMALIZE_CSS) is always injected
regardless of `--no-default-css` — it fixes layout bugs, not
visual styling.

`--reader-mode` extracts the main article content (first <article>,
<main>, or known content container) and renders it with only the
bundled clean CSS — strips navigation, ads, and sidebars.

Pre-render preprocessing handles real-world compatibility issues
automatically (no flags needed):

  - draw.io / Confluence inline SVG diagrams: foreignObject labels are
    converted to SVG <text> elements (weasyprint discards foreignObject
    content), and oversized diagrams get a synthesised viewBox so they
    scale to fit the page instead of being clipped.
  - CSS light-dark() is resolved to the light variant (weasyprint does
    not implement CSS Color Level 5).
  - Web-font @font-face declarations are stripped; system fonts are used
    instead to avoid garbled glyphs from CDN-subsetted fonts.

Same-path I/O (input == output, including via symlink) is refused
with exit 6 / SelfOverwriteRefused.

Internal layout: this CLI is a thin shim over `html2pdf_lib/`
(preprocess, reader_mode, archives, render). The CLI surface is the
public contract; the package layout is internal and may evolve.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from md2pdf import PAGE_SIZES

from _errors import add_json_errors_argument, report_error
from html2pdf_lib import RenderTimeout, SUPPORTED_EXTENSIONS, convert
from html2pdf_lib.archives import extract_mhtml, extract_webarchive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "input", type=Path,
        help="Source file: .html/.htm, .mhtml/.mht, or .webarchive",
    )
    parser.add_argument("output", type=Path, help="Destination .pdf file")
    parser.add_argument("--page-size", choices=list(PAGE_SIZES.keys()), default="letter")
    parser.add_argument("--css", type=Path, default=None,
                        help="Extra CSS file appended after defaults.")
    parser.add_argument("--base-url", default=None,
                        help="Base URL for resolving relative assets in plain "
                             ".html inputs (default: input's directory). "
                             "Ignored for .mhtml / .webarchive — the extracted "
                             "temp dir is used automatically.")
    parser.add_argument("--no-default-css", dest="no_default_css",
                        action="store_true",
                        help="Skip the bundled stylesheet (use only the "
                             "input's embedded styles + --css if given). "
                             "Structural normalisation CSS is still injected.")
    parser.add_argument("--reader-mode", dest="reader_mode",
                        action="store_true",
                        help="Extract only the main article content before "
                             "rendering (like Safari Reader View). Strips "
                             "navigation, ads, and sidebars by finding the "
                             "first <article>, <main>, or known content "
                             "container. Implies --no-default-css is NOT set "
                             "— the bundled clean stylesheet is always used.")
    # Watchdog default: 180s. SPA pages with pathological CSS (vc.ru-style
    # nested flex/grid layouts) can hang weasyprint's box-layout engine for
    # tens of minutes on otherwise-modest HTML — without a timeout the whole
    # pipeline stalls. Override via --timeout SECONDS or HTML2PDF_TIMEOUT env;
    # set to 0 to disable. Honest scope: timeout fires only on POSIX
    # (signal.SIGALRM); on Windows it's a no-op.
    parser.add_argument(
        "--timeout", dest="timeout", type=int,
        default=int(os.environ.get("HTML2PDF_TIMEOUT", "180")),
        help="Render watchdog deadline in seconds (default 180; "
             "$HTML2PDF_TIMEOUT overrides; 0 disables). Kills weasyprint "
             "if its layout exceeds the deadline (POSIX only).",
    )
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    if not args.input.is_file():
        return report_error(
            f"Input not found: {args.input}",
            code=1, error_type="FileNotFound",
            details={"path": str(args.input)}, json_mode=je,
        )

    ext = args.input.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return report_error(
            f"Unsupported input format {ext!r}. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
            code=1, error_type="UnsupportedFormat",
            details={"path": str(args.input), "ext": ext}, json_mode=je,
        )

    if args.css is not None and not args.css.is_file():
        return report_error(
            f"CSS file not found: {args.css}",
            code=1, error_type="FileNotFound",
            details={"path": str(args.css)}, json_mode=je,
        )

    # cross-7 H1 same-path guard (catches symlinks via .resolve()).
    try:
        same = args.input.resolve() == args.output.resolve()
    except OSError:
        same = False
    if same:
        return report_error(
            f"INPUT and OUTPUT resolve to the same path: {args.input.resolve()} "
            "(would corrupt the source mid-write).",
            code=6, error_type="SelfOverwriteRefused",
            details={"input": str(args.input), "output": str(args.output)},
            json_mode=je,
        )

    tmp_dir: str | None = None
    try:
        if ext in (".html", ".htm"):
            html_text = args.input.read_text(encoding="utf-8")
            base_url  = args.base_url or str(args.input.parent.resolve())
        elif ext in (".mhtml", ".mht"):
            tmp_dir   = tempfile.mkdtemp(prefix="html2pdf_mhtml_")
            html_text, base_url = extract_mhtml(args.input, Path(tmp_dir))
        else:  # .webarchive
            tmp_dir   = tempfile.mkdtemp(prefix="html2pdf_webarchive_")
            html_text, base_url = extract_webarchive(args.input, Path(tmp_dir))

        convert(
            html_text, args.output,
            base_url=base_url,
            page_size=args.page_size,
            extra_css_path=args.css,
            use_default_css=not args.no_default_css,
            reader_mode=args.reader_mode,
            timeout=args.timeout,
        )
    except RenderTimeout as exc:
        return report_error(
            str(exc), code=1, error_type="RenderTimeout",
            details={"timeout": args.timeout}, json_mode=je,
        )
    except Exception as exc:
        return report_error(
            f"Conversion failed: {exc}",
            code=1, error_type=type(exc).__name__, json_mode=je,
        )
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())

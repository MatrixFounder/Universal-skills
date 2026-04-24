#!/usr/bin/env python3
"""Render Markdown to a well-typeset PDF via weasyprint.

Pipeline:
    Markdown --(markdown2)--> HTML --(weasyprint)--> PDF

Supports GFM tables, fenced code blocks with basic styling, and
custom CSS via `--css`. A sensible default stylesheet handles
page size, margins, typography, code blocks, and tables.

Usage:
    python3 md2pdf.py INPUT.md OUTPUT.pdf
        [--css EXTRA.css] [--page-size letter|a4|legal]
        [--base-url DIR]

`--base-url DIR` controls how relative image paths resolve. Defaults
to the directory containing the input Markdown file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import markdown2  # type: ignore
from weasyprint import CSS, HTML  # type: ignore


DEFAULT_CSS = """
@page {
    size: {page_size};
    margin: 18mm 20mm 22mm 20mm;
    @bottom-right { content: counter(page) " / " counter(pages); font-size: 9pt; color: #6b7280; }
}

html {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.45;
    color: #1f2937;
}

h1, h2, h3, h4 { color: #111827; line-height: 1.25; margin: 1.2em 0 0.4em; }
h1 { font-size: 22pt; border-bottom: 2px solid #1f2937; padding-bottom: 0.2em; }
h2 { font-size: 16pt; }
h3 { font-size: 13pt; }

p { margin: 0.5em 0; }

ul, ol { margin: 0.5em 0 0.5em 1.3em; padding: 0; }
li { margin: 0.15em 0; }

blockquote {
    border-left: 3px solid #2563eb;
    padding: 0.2em 0.9em;
    margin: 0.7em 0;
    color: #374151;
    background: #f3f4f6;
}

code {
    font-family: "Menlo", "Consolas", monospace;
    font-size: 9.5pt;
    background: #f3f4f6;
    padding: 0 0.25em;
    border-radius: 3px;
}

pre {
    background: #f3f4f6;
    padding: 0.6em 0.9em;
    border-radius: 4px;
    overflow-x: auto;
    page-break-inside: avoid;
}

pre code { background: transparent; padding: 0; font-size: 9pt; }

table {
    width: 100%;
    border-collapse: collapse;
    margin: 0.6em 0;
    font-size: 10pt;
    page-break-inside: avoid;
}
th, td { border: 1px solid #e5e7eb; padding: 0.35em 0.55em; text-align: left; vertical-align: top; }
th { background: #dbeafe; color: #111827; }

img { max-width: 100%; height: auto; }

a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
"""

PAGE_SIZES = {"letter": "letter", "a4": "A4", "legal": "legal"}


def convert(
    input_path: Path,
    output_path: Path,
    *,
    page_size: str,
    extra_css_path: Path | None,
    base_url: str | None,
) -> None:
    md_text = input_path.read_text(encoding="utf-8")
    html_body = markdown2.markdown(
        md_text,
        extras=["fenced-code-blocks", "tables", "strike", "cuddled-lists", "code-friendly"],
    )

    html = (
        "<!DOCTYPE html>\n"
        '<html><head><meta charset="utf-8"><title>doc</title></head><body>\n'
        + html_body
        + "\n</body></html>"
    )

    default = DEFAULT_CSS.replace("{page_size}", PAGE_SIZES.get(page_size, "letter"))
    stylesheets = [CSS(string=default)]
    if extra_css_path is not None:
        stylesheets.append(CSS(filename=str(extra_css_path)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    base = base_url or str(input_path.parent.resolve())
    HTML(string=html, base_url=base).write_pdf(str(output_path), stylesheets=stylesheets)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="Source .md file")
    parser.add_argument("output", type=Path, help="Destination .pdf file")
    parser.add_argument("--page-size", choices=list(PAGE_SIZES.keys()), default="letter")
    parser.add_argument("--css", type=Path, default=None, help="Extra CSS file appended after defaults")
    parser.add_argument("--base-url", default=None, help="Base URL for resolving relative images (default: input's dir)")
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    try:
        convert(
            args.input,
            args.output,
            page_size=args.page_size,
            extra_css_path=args.css,
            base_url=args.base_url,
        )
    except Exception as exc:
        print(f"Conversion failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

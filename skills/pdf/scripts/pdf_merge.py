#!/usr/bin/env python3
"""Merge multiple PDFs into a single file.

Usage:
    python3 pdf_merge.py OUTPUT.pdf INPUT1.pdf INPUT2.pdf [INPUT3.pdf ...]

The first positional argument is the output; the rest are inputs, in
order. Preserves bookmarks (outlines) from each source file, nesting
them under a top-level entry named after the source's stem.

Exit codes:
    0 — merged successfully
    1 — missing inputs, pypdf errors
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter  # type: ignore

from _errors import add_json_errors_argument, report_error


def merge(output: Path, inputs: list[Path]) -> None:
    writer = PdfWriter()
    for src in inputs:
        reader = PdfReader(str(src))
        start_index = len(writer.pages)
        for page in reader.pages:
            writer.add_page(page)
        writer.add_outline_item(src.stem, start_index)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "wb") as fh:
        writer.write(fh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path, help="Destination merged PDF")
    parser.add_argument("inputs", nargs="+", type=Path, help="Source PDFs in merge order")
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    missing = [str(p) for p in args.inputs if not p.is_file()]
    if missing:
        return report_error(
            f"Missing inputs: {', '.join(missing)}",
            code=1, error_type="FileNotFound",
            details={"missing": missing}, json_mode=je,
        )

    try:
        merge(args.output, args.inputs)
    except Exception as exc:
        return report_error(
            f"Merge failed: {exc}",
            code=1, error_type=type(exc).__name__, json_mode=je,
        )

    print(f"Merged {len(args.inputs)} PDFs into {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

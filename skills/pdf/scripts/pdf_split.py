#!/usr/bin/env python3
"""Split a PDF into multiple files by page ranges.

Page ranges are 1-indexed and inclusive. A range is a comma-separated
list of `START-END:OUTPUT.pdf` entries. A single page is written as
`N-N:OUTPUT.pdf` or the shorthand `N:OUTPUT.pdf`.

For Windows paths that contain a drive-letter colon (``C:\\…``), use
``=>`` as the separator instead: ``1-5=>C:\\out.pdf,6-10=>C:\\out2.pdf``.
The script picks up either separator per entry.

Usage examples:
    python3 pdf_split.py INPUT.pdf --ranges "1-5:part1.pdf,6-10:part2.pdf"
    python3 pdf_split.py INPUT.pdf --ranges "1-5=>C:\\out.pdf"
    python3 pdf_split.py INPUT.pdf --each-page OUTDIR/
    python3 pdf_split.py INPUT.pdf --every N OUTDIR/    # chunks of N pages

Exit codes:
    0 — split successful
    1 — invalid range spec, page out of bounds, pypdf error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter  # type: ignore

from _errors import add_json_errors_argument, report_error


def _parse_ranges(spec: str) -> list[tuple[int, int, Path]]:
    out: list[tuple[int, int, Path]] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        # Prefer '=>' when present (disambiguates Windows drive-letter paths).
        if "=>" in chunk:
            lhs, rhs = chunk.split("=>", 1)
        elif ":" in chunk:
            # Split on the FIRST ':' so the range (always digits + '-') stays intact
            # and anything after — including Windows paths — ends up in rhs.
            lhs, rhs = chunk.split(":", 1)
        else:
            raise ValueError(f"Missing ':output' or '=>output' in range '{chunk}'")
        lhs, rhs = lhs.strip(), rhs.strip()
        if "-" in lhs:
            start_s, end_s = lhs.split("-", 1)
            try:
                start, end = int(start_s), int(end_s)
            except ValueError:
                raise ValueError(f"Invalid page range in '{chunk}'") from None
        else:
            try:
                start = end = int(lhs)
            except ValueError:
                raise ValueError(f"Invalid page range in '{chunk}'") from None
        if start < 1 or end < start:
            raise ValueError(f"Invalid page range in '{chunk}'")
        if not rhs:
            raise ValueError(f"Missing output path in '{chunk}'")
        out.append((start, end, Path(rhs)))
    return out


def split_by_ranges(reader: PdfReader, ranges: list[tuple[int, int, Path]]) -> list[Path]:
    written: list[Path] = []
    total = len(reader.pages)
    for start, end, out_path in ranges:
        if end > total:
            raise ValueError(f"Page {end} out of range (document has {total} pages)")
        writer = PdfWriter()
        for i in range(start - 1, end):
            writer.add_page(reader.pages[i])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as fh:
            writer.write(fh)
        written.append(out_path)
    return written


def split_every_page(reader: PdfReader, out_dir: Path, stem: str) -> list[Path]:
    written: list[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    width = max(3, len(str(len(reader.pages))))
    for i, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)
        path = out_dir / f"{stem}-{i:0{width}d}.pdf"
        with open(path, "wb") as fh:
            writer.write(fh)
        written.append(path)
    return written


def split_every_n(reader: PdfReader, out_dir: Path, stem: str, n: int) -> list[Path]:
    written: list[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(reader.pages)
    chunk_idx = 1
    for start in range(0, total, n):
        end = min(start + n, total)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])
        path = out_dir / f"{stem}-chunk-{chunk_idx:03d}.pdf"
        with open(path, "wb") as fh:
            writer.write(fh)
        written.append(path)
        chunk_idx += 1
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="Source PDF")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--ranges", help="Comma-separated ranges like '1-5:part1.pdf,6-10:part2.pdf'")
    mode.add_argument("--each-page", type=Path, metavar="OUTDIR", help="Write one PDF per page into OUTDIR")
    mode.add_argument("--every", nargs=2, metavar=("N", "OUTDIR"),
                      help="Write chunks of N pages into OUTDIR")
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    if not args.input.is_file():
        return report_error(
            f"Input not found: {args.input}",
            code=1, error_type="FileNotFound",
            details={"path": str(args.input)}, json_mode=je,
        )

    try:
        reader = PdfReader(str(args.input))
        if args.ranges:
            ranges = _parse_ranges(args.ranges)
            written = split_by_ranges(reader, ranges)
        elif args.each_page:
            written = split_every_page(reader, args.each_page, args.input.stem)
        else:
            n = int(args.every[0])
            if n < 1:
                raise ValueError("--every N must be >= 1")
            written = split_every_n(reader, Path(args.every[1]), args.input.stem, n)
    except Exception as exc:
        return report_error(
            f"Split failed: {exc}",
            code=1, error_type=type(exc).__name__, json_mode=je,
        )

    for p in written:
        print(str(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())

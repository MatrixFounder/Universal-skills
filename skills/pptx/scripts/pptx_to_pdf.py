#!/usr/bin/env python3
"""Convert a .pptx to a .pdf via headless LibreOffice.

Thin wrapper around `soffice --convert-to pdf`. Useful for generating
print-ready decks and as the pre-step for `pptx_thumbnails.py`.

Usage:
    python3 pptx_to_pdf.py INPUT.pptx [OUTPUT.pdf] [--timeout 180]

If OUTPUT.pdf is omitted, writes `<stem>.pdf` next to the input.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from _soffice import SofficeError, convert_to
from office._encryption import EncryptedFileError, assert_not_encrypted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="Source .pptx file")
    parser.add_argument("output", nargs="?", type=Path, default=None, help="Destination .pdf (optional)")
    parser.add_argument("--timeout", type=int, default=180, help="soffice timeout in seconds (default 180)")
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1
    try:
        assert_not_encrypted(args.input)
    except EncryptedFileError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    out_dir = (args.output.parent if args.output else args.input.parent).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        produced = convert_to(args.input, out_dir, "pdf", timeout=args.timeout)
    except SofficeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.output and produced != args.output.resolve():
        shutil.move(str(produced), str(args.output))
        produced = args.output.resolve()

    print(str(produced))
    return 0


if __name__ == "__main__":
    sys.exit(main())

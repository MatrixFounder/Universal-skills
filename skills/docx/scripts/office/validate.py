#!/usr/bin/env python3
"""CLI validator for OOXML containers (.docx / .xlsx / .pptx).

Picks the right validator by extension, runs it, and prints either a
human report or a JSON object (`--json`).

Usage (module):
    python -m office.validate file.docx [--strict] [--json] [--schemas-dir <path>]
Usage (script):
    python office/validate.py file.docx

Exit codes:
    0 — no errors (warnings allowed unless --strict)
    1 — errors present (or warnings present when --strict)
    2 — input missing or unknown extension
    3 — input is a CFB container (password-protected OOXML or legacy
        .doc/.xls/.ppt). Same exit code and message as every other
        reader in the office skills (cross-3 consistency).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from office._encryption import EncryptedFileError, assert_not_encrypted
    from office.validators.base import ValidationReport
    from office.validators.docx import DocxValidator
    from office.validators.pptx import PptxValidator
    from office.validators.redlining import RedliningValidator
    from office.validators.xlsx import XlsxValidator
else:
    from ._encryption import EncryptedFileError, assert_not_encrypted
    from .validators.base import ValidationReport
    from .validators.docx import DocxValidator
    from .validators.pptx import PptxValidator
    from .validators.redlining import RedliningValidator
    from .validators.xlsx import XlsxValidator


_VALIDATOR_BY_EXT = {
    ".docx": DocxValidator,
    ".xlsx": XlsxValidator,
    ".pptx": PptxValidator,
}


def _resolve_schemas_dir(cli_value: Path | None) -> Path | None:
    if cli_value is not None:
        return cli_value if cli_value.is_dir() else None
    guess = Path(__file__).resolve().parent / "schemas"
    return guess if guess.is_dir() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="OOXML file to validate")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors and do full XSD validation")
    parser.add_argument("--json", action="store_true", help="Emit JSON report instead of plain text")
    parser.add_argument(
        "--schemas-dir",
        type=Path,
        default=None,
        help="Directory containing XSD schemas (default: office/schemas next to this script)",
    )
    parser.add_argument(
        "--compare-to",
        type=Path,
        default=None,
        metavar="ORIGINAL.docx",
        help="Run redlining validator: compare INPUT.docx against ORIGINAL.docx and "
             "report any text change that is not wrapped in <w:ins>/<w:del>. "
             "Catches 'editor forgot to enable Track Changes' scenarios. .docx only.",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 2

    # cross-3 consistency: every reader emits the same exit-3 message on a
    # CFB container (encrypted OOXML or legacy .doc/.xls/.ppt). Without this,
    # encrypted inputs fail later as "Not a ZIP-based OOXML container",
    # which gives the user a different (and misleading) remediation hint
    # than every other reader in the office skills.
    try:
        assert_not_encrypted(args.input)
    except EncryptedFileError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    ext = args.input.suffix.lower()
    cls = _VALIDATOR_BY_EXT.get(ext)
    if cls is None:
        print(f"Unknown extension: {ext}", file=sys.stderr)
        return 2

    schemas_dir = _resolve_schemas_dir(args.schemas_dir)
    validator = cls(schemas_dir=schemas_dir, strict=args.strict)
    report: ValidationReport = validator.validate(args.input)

    if args.compare_to is not None:
        if ext != ".docx":
            print(f"--compare-to only supports .docx (got {ext})", file=sys.stderr)
            return 2
        redliner = RedliningValidator(schemas_dir=schemas_dir, strict=args.strict)
        redline_report = redliner.compare(args.compare_to, args.input)
        report.merge(redline_report)

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        for err in report.errors:
            print(f"ERROR: {err}")
        for warn in report.warnings:
            print(f"WARN:  {warn}")
        if report.ok and not report.warnings:
            print("OK")

    if report.errors:
        return 1
    if args.strict and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

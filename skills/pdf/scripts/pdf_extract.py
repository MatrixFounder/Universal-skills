#!/usr/bin/env python3
"""Dump a PDF's per-page text and tables to structured JSON (NOT a Markdown converter).

`pdf_extract.py` produces a structured, machine-readable **dump** of a PDF:
per-page extracted text, extracted tables, and scan-detection flags. It is
deliberately NOT a Markdown converter and never emits Markdown — final Markdown
composition (heading levels, reading order, stitching a table split across
pages, describing diagrams) is LLM judgement and stays the caller's job. See
``references/pdf-to-markdown.md`` for the decision tree and recipe.

Its defining feature is **scan detection**: ``pdfplumber`` returns empty text
on an image-only (scanned) page *without raising* — this tool turns that silent
failure into a loud signal. A whole-document scan exits ``10`` and points at
OCR / the Read tool.

Scan-detection threshold: a page is ``scanned`` when its stripped extractable
character count is at or below ``_SCANNED_CHAR_THRESHOLD`` (10) AND it carries
an image. The threshold is 10 rather than 0 to tolerate the occasional
digitally-stamped page/Bates number on an otherwise image-only page; a digital
page with genuine content essentially always exceeds 10 stripped characters,
and the dual ``has_images`` condition prevents a sparse digital page from being
misread as scanned. A genuinely image-only page has no character objects at
all, so it scores 0 under both default and ``--layout`` extraction — the
classification is stable across modes. ``doc_scanned`` is true only when at
least one page is ``scanned`` AND no page yields meaningful text; a document
with zero scanned pages (including an all-blank PDF) is never ``doc_scanned``.

Honest scope (v1):
  - Final Markdown composition is the caller's job — never scripted.
  - OCR is not bundled; scans are detected, not OCR'd.
  - Default ``extract_tables()`` settings only — borderless-table tuning
    (``snap_tolerance`` etc.) is inline-agent work, see the reference.
  - Image bytes are not extracted; only ``has_images`` is reported.
  - Decompression-bomb / adversarial-PDF hardening is not specifically done:
    a pathological PDF can hang (no timeout) as well as crash.
  - ``--password`` is read from argv only (visible in ``ps``).
  - "Encryption never silent" covers PDFs that *require* a password to open. A
    PDF encrypted with only an *owner* password but a blank *user* password is
    readable without a password — it opens normally and is treated as a digital
    PDF (no encryption signal); the content was genuinely extractable.

Usage:
    python3 pdf_extract.py INPUT.pdf [-o OUT.json] [--layout]
                           [--password PW] [--json-errors]

Exit codes:
    0  — success: structured dump emitted (digital, mixed, or all-blank PDF)
    1  — failure: input missing / not a PDF / corrupt / encrypted-without-password
    2  — usage error (argparse)
    6  — SelfOverwriteRefused: the -o output path resolves to the input PDF
    10 — DocumentScanned: whole document is image-only; run OCR or the Read tool
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pdfplumber  # type: ignore

from _errors import add_json_errors_argument, report_error

# A CLI owns its stderr: with --json-errors a wrapper parses stderr as JSON.
# pdfminer / pypdf log free-text warnings ("invalid pdf header", "EOF marker
# not found") on corrupt input — silence them so only our envelope is emitted.
for _noisy_logger in ("pdfminer", "pypdf"):
    logging.getLogger(_noisy_logger).setLevel(logging.ERROR)

_SCANNED_CHAR_THRESHOLD = 10
_EXIT_OK = 0
_EXIT_FAIL = 1
_EXIT_USAGE = 2
_EXIT_SELF_OVERWRITE = 6  # cross-7 parity: -o path == input path
_EXIT_SCANNED = 10


class _ExtractError(Exception):
    """Domain failure inside the extraction core. `error_type` becomes the
    `--json-errors` envelope `type`; `main` maps it to exit code 1."""

    def __init__(self, message: str, *, error_type: str) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argparse CLI. REAL from the stub phase — the smoke test
    asserts the `--help` surface."""
    parser = argparse.ArgumentParser(
        prog="pdf_extract.py",
        description=(
            "Dump a PDF's per-page text and tables to structured JSON. "
            "This is a structured dump, NOT a Markdown converter — it never "
            "emits Markdown. Final Markdown composition is the caller's job; "
            "see references/pdf-to-markdown.md."
        ),
        epilog=(
            "Exit codes: 0 success; 1 failure (missing/not-a-PDF/corrupt/"
            "encrypted-without-password); 2 usage error; 6 SelfOverwriteRefused "
            "(-o path is the input PDF); 10 DocumentScanned (whole document is "
            "image-only — run OCR or the Read tool)."
        ),
    )
    parser.add_argument("INPUT", type=Path, help="Source PDF file.")
    parser.add_argument(
        "-o", "--output", type=Path, default=None, metavar="OUT.json",
        help="Write the JSON dump to this file (overwritten). Default: stdout.",
    )
    parser.add_argument(
        "--layout", action="store_true",
        help="Use extract_text(layout=True) — preserves column separation as "
             "whitespace (does not reflow columns into reading order).",
    )
    parser.add_argument(
        "--password", default=None, metavar="PW",
        help="Password for an encrypted PDF. NOTE: argv is visible in process "
             "listings (ps) — intended for local-CLI use.",
    )
    add_json_errors_argument(parser)
    return parser


def _classify_page(char_count: int, has_images: bool) -> bool:
    """Per-page scanned predicate (ARCH §4.3): a page is `scanned` when it has
    next-to-no extractable text AND carries an image. The ONLY site that reads
    `_SCANNED_CHAR_THRESHOLD`."""
    return char_count <= _SCANNED_CHAR_THRESHOLD and has_images


def _classify_document(pages: list[dict]) -> tuple[bool, list[int]]:
    """Document-level scan verdict (ARCH §4.3) → `(doc_scanned, scanned_pages)`.

    `doc_scanned` is true iff at least one page is `scanned` AND no page yields
    meaningful text (every page's `char_count` is at/below the threshold). The
    `bool(scanned_pages)` guard means a document with zero scanned pages —
    including an all-blank or empty (0-page) PDF — is never `doc_scanned`, so it
    is never wrongly routed to OCR."""
    scanned_pages = [p["n"] for p in pages if p["scanned"]]
    # `no_meaningful_text` is vacuously True for an empty `pages` list; the
    # `bool(scanned_pages)` conjunct (evaluated first) is what keeps a 0-page or
    # all-blank PDF out of `doc_scanned`. Keep that conjunct first on any edit.
    no_meaningful_text = all(
        p["char_count"] <= _SCANNED_CHAR_THRESHOLD for p in pages
    )
    doc_scanned = bool(scanned_pages) and no_meaningful_text
    return doc_scanned, scanned_pages


def _is_encrypted(pdf_path: Path) -> bool:
    """Probe whether the PDF is encrypted — used ONLY to label an already-failed
    `pdfplumber.open` as `EncryptedPDF` vs `CorruptPdf`. NOT a cheap probe: it
    constructs a full `pypdf.PdfReader` (a second parse of the file). Acceptable
    because it runs solely on the failure path, never on a successful
    extraction."""
    try:
        from pypdf import PdfReader  # type: ignore

        return bool(PdfReader(str(pdf_path)).is_encrypted)
    except Exception:
        return False


def _open_pdf(pdf_path: Path, password: str | None):
    """Open the PDF via pdfplumber and return the `pdfplumber.PDF` object.

    The SOLE caller (`extract_pdf`) owns closing it via a `with` block. A PDF
    that *requires* a password to open never fails silently: pdfplumber raises,
    and the file is reported as `EncryptedPDF` (recoverable with `--password`)
    or `CorruptPdf` — both raise `_ExtractError`, which `main` maps to exit 1.
    (An owner-only-encrypted PDF with a blank user password opens normally — see
    the module docstring's honest-scope note.)"""
    try:
        return pdfplumber.open(str(pdf_path), password=password or "")
    except Exception as exc:
        if _is_encrypted(pdf_path):
            raise _ExtractError(
                f"PDF is encrypted and could not be opened — supply a correct "
                f"--password: {pdf_path}",
                error_type="EncryptedPDF",
            ) from exc
        raise _ExtractError(
            f"Could not open PDF (corrupt or not a PDF): {pdf_path}: {exc}",
            error_type="CorruptPdf",
        ) from exc


def _extract_page(page, *, layout: bool) -> dict:
    """Build one PageRecord (ARCH §4.2) from a pdfplumber page.

    `n` is filled by the caller. `char_count` is the *stripped* length of the
    extracted text (whitespace-only page → 0). `tables` is the raw
    `extract_tables()` form (list of row-lists of `str | None`). `scanned` is
    delegated to `_classify_page`."""
    text = page.extract_text(layout=layout) or ""
    tables = page.extract_tables()
    char_count = len(text.strip())
    has_images = bool(page.images)
    return {
        "n": 0,
        "text": text,
        "tables": tables,
        "char_count": char_count,
        "has_images": has_images,
        "scanned": _classify_page(char_count, has_images),
    }


def extract_pdf(pdf_path: Path, *, password: str | None, layout: bool) -> dict:
    """Open the PDF, extract every page, classify, return the dump dict
    (ARCH §4.1 `DumpDocument`).

    Owns the pdfplumber handle: once `_open_pdf` returns a handle, the `with`
    block releases the file descriptor on every path, including a page raising
    mid-extraction. (A failure *inside* `_open_pdf`, before a handle exists,
    raises `_ExtractError` directly — no handle to leak here.)"""
    with _open_pdf(pdf_path, password) as pdf:
        pages: list[dict] = []
        for index, page in enumerate(pdf.pages, start=1):
            record = _extract_page(page, layout=layout)
            record["n"] = index
            pages.append(record)
    doc_scanned, scanned_pages = _classify_document(pages)
    return {
        "page_count": len(pages),
        "doc_scanned": doc_scanned,
        "scanned_pages": scanned_pages,
        "pages": pages,
    }


def _same_path(a: Path, b: Path) -> bool:
    """True if `a` and `b` resolve to the same filesystem path (symlinks
    followed). `b` need not exist yet — `resolve()` is non-strict."""
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def _emit(dump: dict, out_path: Path | None) -> None:
    """Serialise `dump` as indented JSON straight to the sink (`json.dump`, no
    intermediate full-string copy). `out_path is None` → stdout; otherwise
    overwrite `out_path` (idempotent). stdout always carries the dump — never
    the `--json-errors` envelope, which goes to stderr."""
    if out_path is None:
        json.dump(dump, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        # Auto-create the parent dir (parity with pdf_split.py / preview.py).
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(dump, fh, ensure_ascii=False, indent=2)
            fh.write("\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse → extract → emit → return the exit code.

    Exit codes: 0 success; 1 failure (`InputNotFound` / `EncryptedPDF` /
    `CorruptPdf` / `OutputWriteFailed` / `InternalError`); 2 argparse usage
    error; 6 `SelfOverwriteRefused` (`-o` resolves to the input PDF); 10
    `DocumentScanned` (whole-document scan). On a whole-doc scan the dump is
    still emitted (to stdout or `-o`) — exit 10 + stderr is the loud signal."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    je = args.json_errors

    input_path: Path = args.INPUT
    if not input_path.is_file():
        return report_error(
            f"Input not found: {input_path}",
            code=_EXIT_FAIL, error_type="InputNotFound",
            details={"path": str(input_path)}, json_mode=je,
        )

    # cross-7 parity: refuse to overwrite the input PDF with the JSON dump.
    # `resolve()` also neutralises a symlinked `-o` pointing back at the input.
    if args.output is not None and _same_path(input_path, args.output):
        return report_error(
            f"Refusing to overwrite the input PDF with the JSON dump "
            f"(-o resolves to INPUT): {input_path}",
            code=_EXIT_SELF_OVERWRITE, error_type="SelfOverwriteRefused",
            details={"path": str(input_path)}, json_mode=je,
        )

    try:
        dump = extract_pdf(
            input_path, password=args.password, layout=args.layout)
    except _ExtractError as exc:
        return report_error(
            exc.message, code=_EXIT_FAIL, error_type=exc.error_type,
            details={"path": str(input_path)}, json_mode=je,
        )
    except Exception as exc:  # defensive catch-all — should not fire
        return report_error(
            f"Internal error: {type(exc).__name__}: {exc}",
            code=_EXIT_FAIL, error_type="InternalError", json_mode=je,
        )

    # The dump is written on every successful-extraction path, including a
    # whole-document scan (it has diagnostic value). A failure writing the
    # `-o` file surfaces as a clean envelope, never a raw traceback.
    try:
        _emit(dump, args.output)
    except OSError as exc:
        return report_error(
            f"Could not write output {args.output}: {exc}",
            code=_EXIT_FAIL, error_type="OutputWriteFailed",
            details={"path": str(args.output)}, json_mode=je,
        )

    if dump["doc_scanned"]:
        return report_error(
            f"Document appears scanned / image-only — {dump['page_count']} "
            f"page(s), no extractable text. Run OCR (e.g. ocrmypdf) or render "
            f"the pages as images with the Read tool; see "
            f"references/pdf-to-markdown.md.",
            code=_EXIT_SCANNED, error_type="DocumentScanned",
            details={"page_count": dump["page_count"]}, json_mode=je,
        )
    if dump["scanned_pages"]:
        pages = ", ".join(str(n) for n in dump["scanned_pages"])
        sys.stderr.write(
            f"warning: page(s) {pages} appear scanned / image-only "
            f"(no extractable text); the rest of the document extracted "
            f"normally.\n"
        )
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

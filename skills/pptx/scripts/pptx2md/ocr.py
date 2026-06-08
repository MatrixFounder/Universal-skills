"""Per-image OCR via system tesseract (FC-3, opt-in, bead 020-05).

Reuses the engine + conventions of ``skills/pdf/scripts/pdf_ocr.py`` (``eng+rus``
default, soft-optional, fail-loud, dual-stream ``--list-langs`` parse) but calls
``tesseract`` **directly per image** via ``subprocess`` — NOT via ``ocrmypdf`` /
``ghostscript`` / ``pytesseract`` (D-5, AGPL-clean, preserves slide↔image structure).

IMPORTANT: nothing heavy is imported at module top — ``subprocess`` / ``Pillow`` are
imported lazily inside the functions, and ``cli`` imports this module only under
``--ocr``. So the base CLI never needs the OCR engine (R-C1d).
"""
from __future__ import annotations

import shutil
import subprocess  # noqa: S404 — fixed argv, no shell (S-2)
import sys

from .exceptions import LanguagePackMissing, OcrEngineUnavailable


def _installed_languages(exe: str) -> set[str]:
    """Return the installed tesseract language codes (dual-stream parse, AR-9).

    ``--list-langs`` prints to stdout on some tesseract builds and stderr on others,
    so both streams are parsed (parity with ``pdf_ocr._installed_languages``)."""
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell, trusted exe
            [exe, "--list-langs"], capture_output=True, text=True, check=False,
        )
    except OSError as exc:
        raise OcrEngineUnavailable(
            f"Could not run `tesseract --list-langs`: {exc}",
        ) from exc
    langs: set[str] = set()
    for line in f"{proc.stdout}\n{proc.stderr}".splitlines():
        token = line.strip()
        if not token or token.lower().startswith("list of"):
            continue
        langs.add(token)
    return langs


def probe(langs: str) -> None:
    """Fail loud, BEFORE any output, if tesseract or a requested language is missing.

    Raises:
        OcrEngineUnavailable (exit 1): ``tesseract`` not on PATH.
        LanguagePackMissing  (exit 1): a requested ``--ocr-lang`` token not installed.
    """
    exe = shutil.which("tesseract")
    if exe is None:
        raise OcrEngineUnavailable(
            "tesseract not found on PATH (required by --ocr). Install it — macOS: "
            "`brew install tesseract tesseract-lang`; Debian: `apt install "
            "tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus`; Fedora: `dnf "
            "install tesseract tesseract-langpack-eng tesseract-langpack-rus`. "
            "See references/pptx-to-markdown.md.",
        )
    requested = [t for t in langs.split("+") if t]
    if not requested:
        raise LanguagePackMissing(
            "No OCR language given (--ocr-lang was empty).",
            details={"requested": langs},
        )
    installed = _installed_languages(exe)
    missing = [t for t in requested if t not in installed]
    if missing:
        deb = " ".join(f"tesseract-ocr-{m}" for m in missing)
        fed = " ".join(f"tesseract-langpack-{m}" for m in missing)
        raise LanguagePackMissing(
            f"tesseract language pack(s) not installed: {', '.join(missing)} "
            f"(requested --ocr-lang {langs!r}). Install — macOS: `brew install "
            f"tesseract-lang`; Debian: `apt install {deb}`; Fedora: `dnf install "
            f"{fed}`.",
            details={"missing": missing, "requested": langs},
        )


def ocr_asset(blob: bytes, langs: str, timeout: float) -> str:
    """OCR one image blob → recovered text (``""`` on empty/failure).

    Pillow-normalises the blob to a temp PNG (handles JPEG/GIF/BMP/TIFF/WMF
    uniformly), then runs ``tesseract <png> stdout -l <langs>`` as an argv list (no
    shell, S-2), bounded by ``timeout``. Any per-image failure (unreadable blob,
    tesseract non-zero, timeout, OSError) is a warning + ``""`` — one bad image never
    aborts the deck (R-C4c). The temp file is always unlinked.
    """
    import os
    import tempfile

    from PIL import Image

    exe = shutil.which("tesseract")
    if exe is None:  # defensive — probe() runs first, but stay self-contained
        return ""

    fd, png_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        try:
            import io

            # The .save() forces a full decode, so a decompression-bomb image is a
            # real memory-amplification vector here (unlike the header-only .ext read
            # on the extract side). Guard with a THREAD-LOCAL header-size check before
            # the decode — NOT warnings.catch_warnings(), which mutates process-global
            # filter state and races under --jobs>1 (a sibling thread's context-exit
            # could drop our escalation mid-decode). `Image.open` is lazy (no raster
            # decode), so `.size` is the declared dimensions from the header; reject
            # anything over Pillow's warn threshold before the full-decode .save().
            img = Image.open(io.BytesIO(blob))
            limit = Image.MAX_IMAGE_PIXELS
            if limit is not None:
                w, h = img.size
                if w * h > limit:
                    raise Image.DecompressionBombError(
                        f"{w * h} pixels exceeds the {limit}px OCR cap"
                    )
            img.save(png_path, "PNG")
        except Exception as exc:  # noqa: BLE001 — unreadable/bomb image → skip, never crash
            sys.stderr.write(f"warning: OCR skipped an unreadable image ({type(exc).__name__})\n")
            return ""
        try:
            proc = subprocess.run(  # noqa: S603 — fixed argv, no shell (S-2)
                [exe, png_path, "stdout", "-l", langs],
                capture_output=True, text=True, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            sys.stderr.write(f"warning: OCR timed out after {timeout}s on one image\n")
            return ""
        except OSError as exc:
            sys.stderr.write(f"warning: OCR failed to run tesseract ({type(exc).__name__})\n")
            return ""
        if proc.returncode != 0:
            sys.stderr.write(f"warning: tesseract exited {proc.returncode} on one image\n")
            return ""
        return proc.stdout.strip()
    finally:
        try:
            os.unlink(png_path)
        except OSError:
            pass

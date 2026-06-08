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
from .images import rasterise_vector  # shared WMF/EMF → PNG (LibreOffice) helper


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


def ocr_asset(
    blob: bytes,
    langs: str,
    timeout: float,
    *,
    denoise: bool = False,
    min_px: int = 48,
    min_conf: float = 50.0,
) -> str:
    """OCR one image blob → recovered text (``""`` on empty/failure).

    Pillow-normalises the blob to a temp PNG (handles JPEG/GIF/BMP/TIFF/WMF
    uniformly), then runs ``tesseract <png> stdout -l <langs>`` as an argv list (no
    shell, S-2), bounded by ``timeout``. Any per-image failure (unreadable blob,
    tesseract non-zero, timeout, OSError) is a warning + ``""`` — one bad image never
    aborts the deck (R-C4c). The temp file is always unlinked.

    ``denoise`` (TASK 021, opt-in — default OFF keeps the path above byte-identical):
    * **size-gate (R1):** a raster image whose smaller side is ``< min_px`` is skipped
      (``""``) before tesseract runs — decorative icons/glyphs are never body text.
      Vector-rasterised images (WMF/EMF → PNG) are exempt: they are diagrams, not icons.
    * **confidence-gate (R2):** tesseract is invoked in ``tsv`` mode and
      :func:`_filter_tsv` keeps only words with ``conf >= min_conf``, dropping the
      whole image when fewer than two survive (a text-free/low-contrast image yields
      ≤1 confident word; a real screenshot yields dozens) and stripping low-confidence
      garble from the blocks it keeps.
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
        img = None  # bound before the try so the except's getattr(img, ...) is safe
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
            w, h = img.size
            limit = Image.MAX_IMAGE_PIXELS
            if limit is not None and w * h > limit:
                raise Image.DecompressionBombError(
                    f"{w * h} pixels exceeds the {limit}px OCR cap"
                )
            # R1 size-gate: a tiny raster is a decorative icon/glyph, not body text —
            # skip OCR before tesseract can emit edge noise. (Opt-in; default min_px=48
            # is below readable slide-text size.) Vectors are EXEMPT: Pillow *opens* a
            # WMF/EMF and exposes a tiny logical-unit `.size`, but `.save()` below raises
            # → the except branch rasterises the (full-size) diagram. Gating on that
            # placeholder `.size` would wrongly drop a real diagram (critic-logic MED-1).
            fmt = (img.format or "").upper()
            if denoise and fmt not in ("WMF", "EMF") and min(w, h) < min_px:
                return ""
            img.save(png_path, "PNG")
        except Exception as exc:  # noqa: BLE001 — non-rasterisable/bomb image → fallback or skip
            # Pillow couldn't rasterise. For a vector image it CAN identify but not
            # decode (WMF/EMF), try LibreOffice as a soft-optional fallback so its text
            # can still be OCR'd; otherwise (bomb = raster format → ext gate rejects it;
            # soffice absent; conversion fails) skip OCR for this one image.
            fmt = (getattr(img, "format", "") or "").upper()
            png = rasterise_vector(blob, fmt, timeout)
            if png is None:
                reason = " ".join(str(exc).split()) or type(exc).__name__
                sys.stderr.write(
                    f"warning: OCR skipped a non-rasterisable image: {reason}\n"
                )
                return ""
            with open(png_path, "wb") as fh:
                fh.write(png)
        # tesseract argv = <image> <outputbase> [options] [configfile]. The outputbase
        # is ALWAYS "stdout" (prints to stdout); under denoise we APPEND the built-in
        # "tsv" config (after -l) so the same stdout carries per-word confidence for the
        # R2 gate. (Putting "tsv" in the outputbase slot would write a file, not stdout.)
        argv = [exe, png_path, "stdout", "-l", langs]
        if denoise:
            argv.append("tsv")
        try:
            proc = subprocess.run(  # noqa: S603 — fixed argv, no shell (S-2)
                argv,
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
        if denoise:
            return _filter_tsv(proc.stdout, min_conf)
        return proc.stdout.strip()
    finally:
        try:
            os.unlink(png_path)
        except OSError:
            pass


_MIN_CONFIDENT_WORDS = 2  # a kept OCR block must have at least this many high-conf words


def _filter_tsv(tsv: str, min_conf: float, min_words: int = _MIN_CONFIDENT_WORDS) -> str:
    """R2 confidence-gate: reduce tesseract ``tsv`` output to denoised text.

    Pure function (no I/O) so it is unit-testable on synthetic TSV. tesseract's
    ``tsv`` output is one tab-separated row per layout node with a header row; word
    rows carry a ``conf`` in 0–100 (structural rows are ``-1``/blank-text).

    Policy (calibrated on real dogfood data — a *mean*-confidence gate wrongly
    dropped dense real screenshots whose UI chrome drags the mean down, so the
    discriminator is the **count** of confident words, not their average):

    * keep word rows with non-empty text and ``conf >= min_conf`` (the *survivors*);
    * if **fewer than ``min_words``** survive, return ``""`` — the image is noise
      (a text-free / low-contrast image yields ≤1 confident word: the N2 class; a
      real screenshot yields dozens);
    * otherwise reconstruct text **from the survivors only** — this also strips the
      low-confidence garble (UI glyphs, mojibake) *inside* an otherwise-real block —
      grouping words by ``(block, par, line)`` into lines with a blank line at each
      paragraph/block boundary.

    Malformed/empty/headerless TSV degrades to ``""`` and never raises (AR-1/R5).
    """
    rows = tsv.splitlines()
    if not rows:
        return ""
    header = rows[0].split("\t")
    try:
        ci = header.index("conf")
        ti = header.index("text")
        bi = header.index("block_num")
        pi = header.index("par_num")
        li = header.index("line_num")
    except ValueError:
        return ""  # not the expected tesseract TSV schema → no usable text
    need = max(ci, ti, bi, pi, li)
    survivors: list[tuple[str, str, str, str]] = []  # (block, par, line, text)
    for row in rows[1:]:
        cols = row.split("\t")
        if len(cols) <= need:
            continue
        text = cols[ti].strip()
        if not text:
            continue
        try:
            # ".replace(',', '.')": tesseract conf is 0–100 (no thousands separator), so
            # tolerate a comma decimal from a non-C LC_NUMERIC host (critic-logic LOW-1).
            conf = float(cols[ci].replace(",", "."))
        except ValueError:
            continue
        if conf < min_conf:  # drops conf=-1 structural rows AND low-confidence junk
            continue
        survivors.append((cols[bi], cols[pi], cols[li], text))
    if len(survivors) < min_words:
        return ""
    out_lines: list[str] = []
    cur_line_key = None
    cur_para_key = None
    cur: list[str] = []
    for block, par, line, text in survivors:
        line_key = (block, par, line)
        para_key = (block, par)
        if line_key != cur_line_key:
            if cur:
                out_lines.append(" ".join(cur))
                cur = []
            if cur_para_key is not None and para_key != cur_para_key:
                out_lines.append("")  # blank line between paragraphs/blocks
            cur_line_key = line_key
            cur_para_key = para_key
        cur.append(text)
    if cur:
        out_lines.append(" ".join(cur))
    return "\n".join(out_lines).strip()

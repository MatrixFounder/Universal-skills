#!/usr/bin/env python3
"""Render a docx / xlsx / pptx / pdf as a single PNG-grid preview.

Pipeline:

    .pdf                 → pdftoppm (Poppler) → per-page JPEG → PIL grid
    .docx / .xlsx / .pptx → soffice headless --convert-to pdf → above
    .docm / .xlsm / .pptm → same as .x* (read-only)

Usage:
    python3 preview.py INPUT OUTPUT.jpg [--cols 3] [--dpi 110]
        [--gap 12] [--padding 24] [--label-font-size 14]
        [--json-errors]

This is the "show me what it looks like" CLI. It is byte-identical
across the four office skills (`docx`, `xlsx`, `pptx`, `pdf`). A
single skill installation is enough — preview works for any of the
four file types regardless of which skill owns the script.

Requires:
    - LibreOffice (`soffice`) on PATH for OOXML inputs.
    - Poppler (`pdftoppm`) on PATH for both OOXML and PDF inputs.
    - Pillow (Python; bundled in each skill's `requirements.txt`).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont  # type: ignore

from _errors import add_json_errors_argument, report_error


SUPPORTED_OOXML = frozenset({".docx", ".xlsx", ".pptx",
                             ".docm", ".xlsm", ".pptm"})
SUPPORTED_PDF = frozenset({".pdf"})
SUPPORTED = SUPPORTED_OOXML | SUPPORTED_PDF


_SOFFICE_LOCATIONS = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/opt/homebrew/bin/soffice",
    "/opt/libreoffice/program/soffice",
)


def _find(binary_name: str, fallbacks: tuple[str, ...] = ()) -> str | None:
    found = shutil.which(binary_name)
    if found:
        return found
    for fallback in fallbacks:
        if Path(fallback).is_file():
            return fallback
    return None


def _convert_via_soffice(src: Path, out_dir: Path, *, timeout: int) -> Path:
    soffice = _find("soffice", _SOFFICE_LOCATIONS)
    if soffice is None:
        raise RuntimeError(
            "soffice (LibreOffice) not found on PATH. Install it: "
            "macOS `brew install --cask libreoffice`, "
            "Debian/Ubuntu `apt install libreoffice`."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="preview-soffice-") as profile:
        env = os.environ.copy()
        env.setdefault("SAL_USE_VCLPLUGIN", "svp")
        cmd = [
            soffice,
            "--headless",
            "--norestore",
            "--nologo",
            "--nodefault",
            f"-env:UserInstallation={Path(profile).as_uri()}",
            "--convert-to", "pdf",
            "--outdir", str(out_dir),
            str(src),
        ]
        try:
            subprocess.run(cmd, env=env, capture_output=True, text=True,
                           timeout=timeout, check=True)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"soffice timed out after {timeout}s") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"soffice failed (exit {exc.returncode}): "
                f"{(exc.stderr or '').strip() or '(no stderr)'}"
            ) from exc
    produced = out_dir / f"{src.stem}.pdf"
    if not produced.is_file():
        raise RuntimeError(f"Expected PDF not found: {produced}")
    return produced


def _render_pdf_to_jpegs(pdf: Path, out_dir: Path, dpi: int) -> list[Path]:
    pdftoppm = _find("pdftoppm")
    if pdftoppm is None:
        raise RuntimeError(
            "pdftoppm not found on PATH. Install Poppler: "
            "macOS `brew install poppler`, "
            "Debian/Ubuntu `apt install poppler-utils`."
        )
    prefix = out_dir / "page"
    subprocess.run(
        [pdftoppm, "-jpeg", "-r", str(dpi), str(pdf), str(prefix)],
        check=True,
    )
    files = sorted(
        out_dir.glob("page-*.jpg"),
        key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)),  # type: ignore[union-attr]
    )
    if not files:
        raise RuntimeError(f"pdftoppm produced no images for {pdf}")
    return files


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    # Fallback. Pillow >= 10.1 honours `size=` on `load_default`; older
    # builds ignore it and produce a fixed-size bitmap, which would
    # invalidate `label_h = label_font_size + 10` in the layout math.
    # We try the modern signature first and fall back if Pillow rejects it.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _label_for(input_path: Path) -> str:
    suffix = input_path.suffix.lower()
    if suffix in {".pptx", ".pptm"}:
        return "Slide"
    if suffix in {".xlsx", ".xlsm"}:
        return "Sheet"
    return "Page"


def _compose_grid(
    tiles: list[Path],
    output: Path,
    label_text: str,
    cols: int,
    gap: int,
    padding: int,
    label_font_size: int,
) -> None:
    # Open images one-at-a-time inside an ExitStack: if `Image.open(p_5)`
    # raises, p_1..p_4 still get closed. The previous list-comprehension
    # path leaked file descriptors on partial failure.
    with contextlib.ExitStack() as stack:
        images: list[Image.Image] = [
            stack.enter_context(Image.open(p)) for p in tiles
        ]
        thumb_w, thumb_h = images[0].size
        label_h = label_font_size + 10
        rows = (len(images) + cols - 1) // cols
        width = padding * 2 + cols * thumb_w + (cols - 1) * gap
        height = padding * 2 + rows * (thumb_h + label_h) + (rows - 1) * gap

        canvas = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(canvas)
        font = _load_font(label_font_size)

        for idx, img in enumerate(images):
            row = idx // cols
            col = idx % cols
            x = padding + col * (thumb_w + gap)
            y = padding + row * (thumb_h + label_h + gap)
            canvas.paste(img, (x, y))
            label = f"{label_text} {idx + 1}"
            draw.text((x + 4, y + thumb_h + 2), label,
                      fill="#1f2937", font=font)
        canvas.save(output, "JPEG", quality=92, optimize=True)


def build(
    input_path: Path,
    output_path: Path,
    *,
    cols: int,
    dpi: int,
    gap: int,
    padding: int,
    label_font_size: int,
    soffice_timeout: int,
) -> None:
    suffix = input_path.suffix.lower()
    label = _label_for(input_path)
    with tempfile.TemporaryDirectory(prefix="preview-") as tmp_dir:
        tmp = Path(tmp_dir)
        if suffix in SUPPORTED_OOXML:
            pdf = _convert_via_soffice(input_path, tmp, timeout=soffice_timeout)
        elif suffix in SUPPORTED_PDF:
            pdf = input_path
        else:
            raise RuntimeError(f"Unsupported input extension: {suffix}")
        tiles = _render_pdf_to_jpegs(pdf, tmp, dpi)
        _compose_grid(tiles, output_path, label,
                      cols, gap, padding, label_font_size)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cols", type=int, default=3)
    parser.add_argument("--dpi", type=int, default=110)
    parser.add_argument("--gap", type=int, default=12)
    parser.add_argument("--padding", type=int, default=24)
    parser.add_argument("--label-font-size", type=int, default=14)
    parser.add_argument("--soffice-timeout", type=int, default=240,
                        help="Timeout (seconds) for the OOXML→PDF "
                             "conversion. Increase for very large decks. "
                             "Ignored on .pdf input. Default 240.")
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    # Validate numeric arguments before they reach PIL / pdftoppm —
    # otherwise cols=0 is a ZeroDivisionError, label-font-size<=0 is a
    # PIL ValueError, dpi<=0 is a pdftoppm internal error, all leaking
    # tracebacks past the JSON envelope.
    for name, value, minimum in (
        ("cols", args.cols, 1),
        ("dpi", args.dpi, 1),
        ("gap", args.gap, 0),
        ("padding", args.padding, 0),
        ("label-font-size", args.label_font_size, 1),
        ("soffice-timeout", args.soffice_timeout, 1),
    ):
        if value < minimum:
            return report_error(
                f"--{name} must be >= {minimum} (got {value})",
                code=2, error_type="InvalidArgument",
                details={"flag": name, "value": value, "minimum": minimum},
                json_mode=je,
            )

    if args.input.exists() and not args.input.is_file():
        return report_error(
            f"Input is not a regular file: {args.input}",
            code=1, error_type="NotARegularFile",
            details={"path": str(args.input)}, json_mode=je,
        )
    if not args.input.is_file():
        return report_error(
            f"Input not found: {args.input}",
            code=1, error_type="FileNotFound",
            details={"path": str(args.input)}, json_mode=je,
        )

    suffix = args.input.suffix.lower()
    if suffix not in SUPPORTED:
        return report_error(
            f"Unsupported input extension: {suffix}. "
            f"Supported: {sorted(SUPPORTED)}",
            code=2, error_type="UnsupportedFormat",
            details={"path": str(args.input), "suffix": suffix},
            json_mode=je,
        )

    # Encrypted/legacy CFB pre-flight for OOXML inputs. Imported lazily
    # because the pdf skill ships preview.py without `office/` — when
    # an OOXML file is fed to pdf's preview.py, the encryption check
    # is unavailable. Surface a one-line note so the user understands
    # they may get a confusing soffice failure instead of a clear
    # EncryptedFileError; do NOT promote it to a hard error, since
    # most OOXML inputs to pdf-preview are perfectly valid.
    if suffix in SUPPORTED_OOXML:
        try:
            from office._encryption import (  # type: ignore[import-not-found]
                EncryptedFileError, assert_not_encrypted,
            )
        except ImportError:
            print(
                "Note: encryption pre-flight is unavailable in this skill "
                "(no office/ module). If the input is password-protected "
                "or a legacy .doc/.xls/.ppt, soffice will fail with an "
                "opaque error rather than the usual exit-3 message.",
                file=sys.stderr,
            )
        else:
            try:
                assert_not_encrypted(args.input)
            except EncryptedFileError as exc:
                return report_error(
                    str(exc), code=3, error_type="EncryptedFileError",
                    details={"path": str(args.input)}, json_mode=je,
                )

    try:
        build(args.input, args.output,
              cols=args.cols, dpi=args.dpi, gap=args.gap,
              padding=args.padding,
              label_font_size=args.label_font_size,
              soffice_timeout=args.soffice_timeout)
    except RuntimeError as exc:
        return report_error(str(exc), code=1, error_type="PreviewError",
                            json_mode=je)
    except subprocess.CalledProcessError as exc:
        return report_error(f"External tool failed: {exc}",
                            code=1, error_type="ExternalToolError",
                            json_mode=je)
    print(str(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())

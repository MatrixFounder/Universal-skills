#!/usr/bin/env python3
"""Generate a thumbnail grid JPEG for a .pptx.

Pipeline:
    .pptx --(LibreOffice)--> .pdf --(Poppler pdftoppm)--> per-slide JPEGs
    --(Pillow)--> single grid image.

Useful for visual QA — a reviewing sub-agent can load the grid image
and spot slides with missing placeholders, cut-off content, or wrong
layouts at a glance.

Usage:
    python3 pptx_thumbnails.py INPUT.pptx OUTPUT.jpg
        [--cols 3] [--dpi 110] [--gap 12] [--padding 24]
        [--label-font-size 14]
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont  # type: ignore

from _soffice import SofficeError, convert_to


def _find_pdftoppm() -> str:
    for name in ("pdftoppm",):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise RuntimeError("pdftoppm not found. Install Poppler: brew install poppler / apt install poppler-utils")


def _render_pdf_to_jpegs(pdf: Path, out_dir: Path, dpi: int) -> list[Path]:
    prefix = out_dir / "slide"
    subprocess.run(
        [_find_pdftoppm(), "-jpeg", "-r", str(dpi), str(pdf), str(prefix)],
        check=True,
    )
    files = sorted(
        out_dir.glob("slide-*.jpg"),
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
    return ImageFont.load_default()


def _compose_grid(
    tiles: list[Path],
    output: Path,
    cols: int,
    gap: int,
    padding: int,
    label_font_size: int,
) -> None:
    images = [Image.open(p) for p in tiles]
    try:
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
            label = f"Slide {idx + 1}"
            draw.text((x + 4, y + thumb_h + 2), label, fill="#1f2937", font=font)
        canvas.save(output, "JPEG", quality=92, optimize=True)
    finally:
        for img in images:
            img.close()


def build(
    input_path: Path,
    output_path: Path,
    *,
    cols: int,
    dpi: int,
    gap: int,
    padding: int,
    label_font_size: int,
) -> None:
    with tempfile.TemporaryDirectory(prefix="pptx-thumb-") as tmp_dir:
        tmp = Path(tmp_dir)
        pdf = convert_to(input_path, tmp, "pdf", timeout=240)
        tiles = _render_pdf_to_jpegs(pdf, tmp, dpi)
        _compose_grid(tiles, output_path, cols, gap, padding, label_font_size)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cols", type=int, default=3, help="Grid columns (default 3)")
    parser.add_argument("--dpi", type=int, default=110, help="Render DPI (default 110 — ~150px wide slides)")
    parser.add_argument("--gap", type=int, default=12)
    parser.add_argument("--padding", type=int, default=24)
    parser.add_argument("--label-font-size", type=int, default=14)
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    try:
        build(
            args.input,
            args.output,
            cols=args.cols,
            dpi=args.dpi,
            gap=args.gap,
            padding=args.padding,
            label_font_size=args.label_font_size,
        )
    except (SofficeError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(str(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())

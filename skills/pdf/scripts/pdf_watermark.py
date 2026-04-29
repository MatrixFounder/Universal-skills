#!/usr/bin/env python3
"""Stamp every page of a PDF with a text or image watermark.

Two modes (mutually exclusive, exactly one required):

  pdf_watermark.py IN.pdf OUT.pdf --text "DRAFT" [...]
  pdf_watermark.py IN.pdf OUT.pdf --image stamp.png [...]

Common flags:

  --opacity 0.0..1.0          Watermark alpha (default 0.3).
  --position center | top-left | top-right | bottom-left
           | bottom-right | diagonal       (default: diagonal)
  --rotation DEG              Override rotation (default: 0; 45 for "diagonal").
  --pages "all" | "1-5,8,12-end"  Restrict to a subset of pages (default: all).

Text-only flags:
  --font-size 60              Helvetica point size (default 60).
  --color "#888888"           Hex colour (default neutral grey).

Image-only flags:
  --scale 0.5                 Image width as fraction of page width (default 0.5).

Pipeline:
    For each unique page mediabox in the input, build one reportlab
    overlay PDF (one page) at exactly that size; then merge each
    in-scope page of the input with the matching overlay via
    pypdf.merge_page. Heterogeneous decks (mixed Letter+A4) keep
    correct watermark proportions.

Same-path I/O (input == output, including via symlink) is refused
with exit 6 / SelfOverwriteRefused — merging on top of the source
mid-write would corrupt it.
"""
from __future__ import annotations

import argparse
import re
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image as _PILImage  # type: ignore
from pypdf import PdfReader, PdfWriter  # type: ignore
from reportlab.lib.colors import HexColor  # type: ignore
from reportlab.pdfgen import canvas  # type: ignore

from _errors import add_json_errors_argument, report_error


POSITIONS = ("center", "top-left", "top-right",
             "bottom-left", "bottom-right", "diagonal")


class PageSpecError(ValueError):
    """Raised by _parse_pages for a syntactically invalid --pages spec.

    Kept separate from plain ValueError so main()'s except clause does
    not swallow pypdf's own ValueErrors (e.g. corrupt page tree) and
    misreport them as UsageError / exit 2."""


def _parse_pages(spec: str, total: int) -> set[int]:
    """Resolve a 1-indexed page spec to a 0-indexed set of indices.

    Accepts `"all"`, single pages (`"7"`), and ranges (`"1-5"`,
    `"3-end"`). Multiple parts are comma-separated. Empty parts and
    out-of-bounds endpoints raise ValueError so the CLI can emit a
    UsageError envelope with a precise message.
    """
    if spec.strip().lower() == "all":
        return set(range(total))
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise PageSpecError(f"empty page spec component in {spec!r}")
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            try:
                lo = int(lo_s)
                hi = total if hi_s.strip().lower() == "end" else int(hi_s)
            except ValueError:
                raise PageSpecError(
                    f"invalid page spec component {part!r} "
                    f"(expected N, N-M, or N-end)"
                )
        else:
            try:
                lo = hi = int(part)
            except ValueError:
                raise PageSpecError(
                    f"invalid page spec component {part!r} "
                    f"(expected a page number or 'all')"
                )
        if lo < 1 or hi < 1 or lo > total or hi > total or lo > hi:
            raise PageSpecError(
                f"page range {part!r} is out of bounds (1..{total})"
            )
        out.update(range(lo - 1, hi))
    return out


def _anchor(position: str, w: float, h: float, margin: float = 36.0) -> tuple[float, float]:
    """Return the (x, y) PDF point at which to place the watermark
    centre. PDF origin is bottom-left; `margin` is a 0.5-inch safe
    inset for corner positions so the stamp doesn't kiss the edge."""
    if position == "center" or position == "diagonal":
        return w / 2, h / 2
    if position == "top-left":
        return margin, h - margin
    if position == "top-right":
        return w - margin, h - margin
    if position == "bottom-left":
        return margin, margin
    if position == "bottom-right":
        return w - margin, margin
    # argparse choices guards this; defensive default.
    return w / 2, h / 2


def _build_text_overlay(
    page_size: tuple[float, float],
    *,
    text: str,
    opacity: float,
    position: str,
    rotation: float,
    font_size: int,
    color: str,
) -> bytes:
    """Render a one-page PDF with the text drawn at `position`,
    rotated, at `opacity`. Returns the raw PDF bytes — the caller
    wraps them in a PdfReader for merge_page."""
    buf = BytesIO()
    w, h = page_size
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.saveState()
    c.setFillAlpha(opacity)
    c.setFillColor(HexColor(color))
    c.setFont("Helvetica", font_size)
    x, y = _anchor(position, w, h)
    c.translate(x, y)
    c.rotate(rotation)
    c.drawCentredString(0, 0, text)
    c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()


def _build_image_overlay(
    page_size: tuple[float, float],
    *,
    image_path: Path,
    opacity: float,
    position: str,
    rotation: float,
    scale: float,
) -> bytes:
    """Render a one-page PDF with the image drawn at `position`,
    rotated, at `opacity`. Aspect ratio preserved via reportlab's
    drawImage(preserveAspectRatio=True)."""
    buf = BytesIO()
    w, h = page_size
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.saveState()
    c.setFillAlpha(opacity)
    img_w = w * scale
    # Pre-compute exact target height from the image's true aspect ratio so
    # --scale reliably means "rendered width = scale × page_width" for any
    # image orientation. Without this, preserveAspectRatio clips portrait
    # images by page height and --scale becomes meaningless for tall stamps.
    with _PILImage.open(image_path) as _im:
        iw, ih = _im.size
    aspect = iw / ih if ih else 1.0
    img_h = img_w / aspect
    x, y = _anchor(position, w, h)
    c.translate(x, y)
    c.rotate(rotation)
    # Centre the image around the anchor: shift by -half so rotation
    # pivots at the anchor too, not the image's bottom-left.
    c.drawImage(
        str(image_path), -img_w / 2, -img_h / 2, img_w, img_h,
        mask="auto", preserveAspectRatio=False,
    )
    c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()


def watermark(
    input_pdf: Path,
    output_pdf: Path,
    *,
    text: str | None,
    image: Path | None,
    opacity: float,
    position: str,
    rotation: float | None,
    font_size: int,
    color: str,
    scale: float,
    pages_spec: str,
) -> dict:
    reader = PdfReader(str(input_pdf))
    total = len(reader.pages)
    in_scope = _parse_pages(pages_spec, total)

    # Auto-rotation: "diagonal" → 45° unless caller overrode.
    effective_rotation = rotation if rotation is not None else (
        45.0 if position == "diagonal" else 0.0
    )

    # Cache one overlay PdfReader per unique mediabox so heterogeneous
    # decks (mixed Letter+A4) get correctly proportioned watermarks.
    overlay_cache: dict[tuple[float, float], PdfReader] = {}

    def get_overlay(w: float, h: float) -> PdfReader:
        key = (round(w, 3), round(h, 3))
        cached = overlay_cache.get(key)
        if cached is not None:
            return cached
        if text is not None:
            blob = _build_text_overlay(
                (w, h),
                text=text, opacity=opacity, position=position,
                rotation=effective_rotation,
                font_size=font_size, color=color,
            )
        else:
            if image is None:
                raise ValueError("image path must be provided when text is None")
            blob = _build_image_overlay(
                (w, h),
                image_path=image, opacity=opacity, position=position,
                rotation=effective_rotation, scale=scale,
            )
        rdr = PdfReader(BytesIO(blob))
        overlay_cache[key] = rdr
        return rdr

    writer = PdfWriter(clone_from=reader)
    stamped = 0
    for i, page in enumerate(writer.pages):
        if i not in in_scope:
            continue
        mb = page.mediabox
        w = float(mb.width)
        h = float(mb.height)
        overlay = get_overlay(w, h).pages[0]
        page.merge_page(overlay)
        stamped += 1

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with open(output_pdf, "wb") as fh:
        writer.write(fh)

    return {
        "input": str(input_pdf),
        "output": str(output_pdf),
        "pages_total": total,
        "pages_stamped": stamped,
        "mode": "text" if text is not None else "image",
    }


def _hex_colour(s: str) -> str:
    """argparse type= validator: accept only 6-digit hex colours."""
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", s):
        raise argparse.ArgumentTypeError(
            f"must be a 6-digit hex colour like #888888, got {s!r}"
        )
    return s


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="Source .pdf")
    parser.add_argument("output", type=Path, help="Destination .pdf")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--text", type=str, help="Watermark text (e.g. DRAFT, CONFIDENTIAL).")
    mode.add_argument("--image", type=Path, help="Watermark image (PNG/JPG).")
    parser.add_argument("--opacity", type=float, default=0.3,
                        help="Alpha 0.0..1.0 (default 0.3).")
    parser.add_argument("--position", choices=POSITIONS, default="diagonal",
                        help="Anchor position (default: diagonal).")
    parser.add_argument("--rotation", type=float, default=None,
                        help="Rotation in degrees. Default 0; "
                             "auto-set to 45 when --position diagonal.")
    parser.add_argument("--font-size", type=int, default=60,
                        help="Text mode: Helvetica point size (default 60).")
    parser.add_argument("--color", type=_hex_colour, default="#888888",
                        help='Text mode: 6-digit hex colour (default "#888888").')
    parser.add_argument("--scale", type=float, default=0.5,
                        help="Image mode: width as fraction of page width "
                             "(default 0.5).")
    parser.add_argument("--pages", type=str, default="all",
                        help='Pages to stamp: "all" or "1-5,8,12-end" '
                             "(1-indexed, inclusive). Default: all.")
    add_json_errors_argument(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    if not (0.0 <= args.opacity <= 1.0):
        parser.error(f"--opacity must be in [0.0, 1.0], got {args.opacity}")
    if args.scale <= 0 or args.scale > 1.0:
        parser.error(f"--scale must be in (0.0, 1.0], got {args.scale}")
    if args.font_size <= 0:
        parser.error(f"--font-size must be > 0, got {args.font_size}")

    if not args.input.is_file():
        return report_error(
            f"Input not found: {args.input}",
            code=1, error_type="FileNotFound",
            details={"path": str(args.input)}, json_mode=je,
        )
    if args.image is not None and not args.image.is_file():
        return report_error(
            f"Image not found: {args.image}",
            code=1, error_type="FileNotFound",
            details={"path": str(args.image)}, json_mode=je,
        )

    # cross-7 H1 same-path guard (catches symlinks via .resolve()).
    try:
        same = args.input.resolve() == args.output.resolve()
    except OSError:
        same = False
    if same:
        return report_error(
            f"INPUT and OUTPUT resolve to the same path: {args.input.resolve()} "
            "(would corrupt the source mid-write).",
            code=6, error_type="SelfOverwriteRefused",
            details={"input": str(args.input), "output": str(args.output)},
            json_mode=je,
        )

    try:
        report = watermark(
            args.input, args.output,
            text=args.text, image=args.image,
            opacity=args.opacity, position=args.position,
            rotation=args.rotation, font_size=args.font_size,
            color=args.color, scale=args.scale,
            pages_spec=args.pages,
        )
    except PageSpecError as exc:
        # Only PageSpecError from _parse_pages maps to UsageError / exit 2.
        # Plain ValueErrors from pypdf (corrupt PDF, malformed page tree)
        # fall through to the except Exception clause below → exit 1.
        return report_error(
            f"Invalid --pages spec: {exc}",
            code=2, error_type="UsageError",
            details={"flag": "pages", "spec": args.pages}, json_mode=je,
        )
    except Exception as exc:
        return report_error(
            f"Watermark failed: {exc}",
            code=1, error_type=type(exc).__name__, json_mode=je,
        )

    print(f"Stamped {report['pages_stamped']}/{report['pages_total']} "
          f"page(s) of {args.input} → {args.output} ({report['mode']} mode).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

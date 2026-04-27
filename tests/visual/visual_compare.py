#!/usr/bin/env python3
"""Visual regression: compare a PDF page against a golden PNG.

Pipeline:

    PDF --(pdftoppm -jpeg -r DPI -f N -l N)--> JPEG
        --(Pillow re-encode)--> PNG (captured)
    PNG (captured) vs PNG (golden) --(magick compare -metric AE
        -fuzz N%)--> pixel-diff count
    pixel-diff <= threshold → exit 0; else exit 1.

Usage:
    visual_compare.py --pdf PATH --golden PATH
        [--page N] [--dpi N] [--fuzz N]
        [--threshold-px N | --threshold-pct F]
        [--update] [--json-errors]

Updating goldens:
    --update                 (single golden)
    UPDATE_GOLDENS=1 ...     (env override; lets `tests/run_all_e2e.sh`
                              regenerate the whole set in one pass)

Skipping when ImageMagick is missing:
    Default: print a one-line warning and exit 0 — local devs without
    ImageMagick installed are not blocked.
    STRICT_VISUAL=1 in env: missing `compare` is a hard error (exit 4).
    CI sets STRICT_VISUAL=1.

Exit codes:
    0 = match (within threshold), or `compare` missing in non-strict
    1 = mismatch (pixel-diff > threshold)
    2 = bad CLI usage
    3 = pdftoppm failed (rasterisation)
    4 = ImageMagick `compare` missing in STRICT_VISUAL mode, or its
        invocation failed
    5 = golden not found, --update not set, AND STRICT_VISUAL=1
        (without strict mode, missing golden warns + exits 0)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image  # type: ignore


SCHEMA_VERSION = 1


def _report(message: str, *, code: int, error_type: str | None = None,
            details: dict[str, Any] | None = None,
            json_mode: bool = False) -> int:
    """Local copy of the office-skills cross-5 error envelope. We don't
    import scripts/_errors.py — visual_compare lives outside any skill
    and mustn't tie itself to a specific skill's checkout.
    """
    if json_mode:
        envelope: dict[str, Any] = {"v": SCHEMA_VERSION,
                                    "error": message, "code": code}
        if error_type is not None:
            envelope["type"] = error_type
        if details:
            envelope["details"] = details
        sys.stderr.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    else:
        sys.stderr.write(message)
        if not message.endswith("\n"):
            sys.stderr.write("\n")
    sys.stderr.flush()
    return code


def _route_argparse_errors_through_envelope(
    parser: argparse.ArgumentParser,
) -> None:
    """Mirror cross-5's `add_json_errors_argument`: when --json-errors is
    on argv, argparse's own usage failures (missing required, bad type,
    parser.error) emit the same JSON envelope instead of the multi-line
    `usage: ...` banner. Without this, wrappers parsing stderr line-by-
    line as JSON would choke on a usage error.
    """
    _orig_error = parser.error

    def _json_aware_error(message: str) -> None:
        if "--json-errors" in sys.argv[1:]:
            envelope = {
                "v": SCHEMA_VERSION,
                "error": message,
                "code": 2,
                "type": "UsageError",
                "details": {"prog": parser.prog},
            }
            sys.stderr.write(
                json.dumps(envelope, ensure_ascii=False) + "\n"
            )
            sys.stderr.flush()
            sys.exit(2)
        _orig_error(message)

    parser.error = _json_aware_error  # type: ignore[method-assign]


def _find_compare() -> list[str] | None:
    """Resolve ImageMagick's compare CLI. IMv7 ships `magick compare`;
    IMv6 ships standalone `compare`. Prefer v7 when both exist.

    Returns the argv prefix (a list) or None if neither is available.
    """
    magick = shutil.which("magick")
    if magick is not None:
        # `magick compare ...` is the v7 idiom.
        return [magick, "compare"]
    compare = shutil.which("compare")
    if compare is not None:
        return [compare]
    return None


def _rasterise_page(pdf: Path, page: int, dpi: int, out_dir: Path,
                    *, timeout: int = 60) -> Path:
    """Run pdftoppm for a single page, return the produced JPEG path."""
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm is None:
        raise RuntimeError(
            "pdftoppm not found on PATH. Install Poppler: "
            "macOS `brew install poppler`, "
            "Debian/Ubuntu `apt install poppler-utils`."
        )
    prefix = out_dir / "captured"
    cmd = [pdftoppm, "-jpeg", "-r", str(dpi),
           "-f", str(page), "-l", str(page),
           str(pdf), str(prefix)]
    try:
        subprocess.run(cmd, capture_output=True, text=True,
                       timeout=timeout, check=True)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"pdftoppm timed out after {timeout}s on {pdf}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"pdftoppm failed (exit {exc.returncode}): "
            f"{(exc.stderr or '').strip() or '(no stderr)'}"
        ) from exc
    files = sorted(out_dir.glob("captured-*.jpg"),
                   key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)))  # type: ignore[union-attr]
    if not files:
        raise RuntimeError(f"pdftoppm produced no images for {pdf}")
    return files[0]


def _to_png(jpeg: Path, png: Path) -> tuple[int, int]:
    """Re-encode JPEG → PNG (deterministic, lossless)."""
    with Image.open(jpeg) as im:
        im = im.convert("RGB")
        im.save(png, "PNG", optimize=True)
        return im.size


def _ae_count(compare_argv: list[str], golden: Path, captured: Path,
              fuzz_pct: float) -> int:
    """Run ImageMagick `compare -metric AE -fuzz F%` and parse stderr.
    Returns the absolute count of pixels that differ beyond the fuzz
    tolerance.

    `compare` exits 1 when the images differ (any AE > 0) and 2 on
    error. We accept both 0 and 1; the actual number on stderr is the
    signal we care about.
    """
    cmd = compare_argv + [
        "-metric", "AE",
        "-fuzz", f"{fuzz_pct}%",
        str(golden), str(captured),
        "null:",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    # IM compare prints the metric to stderr (NOT stdout). Exit 0 = identical,
    # 1 = differ, 2 = error (e.g. dimension mismatch).
    if proc.returncode == 2:
        raise RuntimeError(
            f"`compare` failed (exit 2): {proc.stderr.strip() or '(no stderr)'}"
        )
    raw = (proc.stderr or "").strip()
    # IM emits the count followed by " (relative)" for some metrics; for AE
    # it's a bare integer. Be tolerant of either.
    m = re.search(r"^(\d+)", raw)
    if not m:
        raise RuntimeError(f"could not parse AE count from: {raw!r}")
    return int(m.group(1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Visual regression for PDF first-page rendering"
    )
    parser.add_argument("--pdf", type=Path, required=True,
                        help="Path to the PDF whose page should be compared.")
    parser.add_argument("--golden", type=Path, required=True,
                        help="Path to the golden PNG (created or updated "
                             "with --update / UPDATE_GOLDENS=1).")
    parser.add_argument("--page", type=int, default=1,
                        help="1-based page number to capture (default 1).")
    parser.add_argument("--dpi", type=int, default=80,
                        help="pdftoppm rasterisation DPI (default 80).")
    parser.add_argument("--fuzz", type=float, default=5.0,
                        help="Per-pixel color-tolerance percentage passed "
                             "to `compare -fuzz` (default 5).")
    thr = parser.add_mutually_exclusive_group()
    thr.add_argument("--threshold-px", type=int, default=None,
                     help="Allowed AE pixel-diff count (absolute). "
                          "Mutually exclusive with --threshold-pct.")
    thr.add_argument("--threshold-pct", type=float, default=None,
                     help="Allowed AE pixel-diff as a fraction of total "
                          "pixels (e.g. 0.5 for 0.5%%). Default if neither "
                          "is given: 0.5%% (cross-platform font drift).")
    parser.add_argument("--update", action="store_true",
                        help="Write the captured PNG to --golden and exit 0. "
                             "Equivalent to UPDATE_GOLDENS=1 in env.")
    parser.add_argument("--json-errors", action="store_true",
                        dest="json_errors")
    _route_argparse_errors_through_envelope(parser)
    args = parser.parse_args(argv)
    je = args.json_errors

    if args.page < 1:
        return _report(f"--page must be >= 1 (got {args.page})",
                       code=2, error_type="InvalidArgument", json_mode=je)
    if args.dpi < 1:
        return _report(f"--dpi must be >= 1 (got {args.dpi})",
                       code=2, error_type="InvalidArgument", json_mode=je)
    if not args.pdf.is_file():
        return _report(f"PDF not found: {args.pdf}",
                       code=2, error_type="FileNotFound",
                       details={"path": str(args.pdf)}, json_mode=je)

    update = args.update or os.environ.get("UPDATE_GOLDENS") == "1"
    strict = os.environ.get("STRICT_VISUAL") == "1"

    with tempfile.TemporaryDirectory(prefix="visual-") as tmp:
        tmp_dir = Path(tmp)
        try:
            jpeg = _rasterise_page(args.pdf, args.page, args.dpi, tmp_dir)
        except RuntimeError as exc:
            return _report(str(exc), code=3, error_type="RasterisationError",
                           json_mode=je)
        captured_png = tmp_dir / "captured.png"
        try:
            width, height = _to_png(jpeg, captured_png)
        except OSError as exc:
            return _report(f"PNG re-encode failed: {exc}", code=3,
                           error_type=type(exc).__name__, json_mode=je)

        if update:
            args.golden.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(captured_png, args.golden)
            print(f"updated golden: {args.golden} ({width}x{height})")
            return 0

        if not args.golden.is_file():
            msg = (f"golden not found: {args.golden} (run with --update or "
                   f"UPDATE_GOLDENS=1 to create it)")
            if strict:
                return _report(msg, code=5, error_type="GoldenMissing",
                               details={"path": str(args.golden)},
                               json_mode=je)
            sys.stderr.write(f"[visual_compare] WARN: {msg} — skipping.\n")
            return 0

        compare_argv = _find_compare()
        if compare_argv is None:
            msg = ("ImageMagick `compare` not found on PATH. "
                   "Install: macOS `brew install imagemagick`, "
                   "Debian/Ubuntu `apt install imagemagick`.")
            if strict:
                return _report(msg, code=4,
                               error_type="ImageMagickMissing", json_mode=je)
            sys.stderr.write(f"[visual_compare] WARN: {msg} — skipping.\n")
            return 0

        # Resolve threshold: explicit --threshold-px wins; --threshold-pct
        # converts to absolute against captured dimensions; default 0.5%
        # of total pixels (forgiving enough for fontconfig/anti-alias drift,
        # tight enough to catch real layout/style regressions).
        total = width * height
        if args.threshold_px is not None:
            threshold = args.threshold_px
        elif args.threshold_pct is not None:
            threshold = int(total * (args.threshold_pct / 100.0))
        else:
            threshold = int(total * 0.005)

        try:
            diff = _ae_count(compare_argv, args.golden, captured_png,
                             args.fuzz)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            return _report(f"compare invocation failed: {exc}",
                           code=4, error_type="CompareError", json_mode=je)

        if diff <= threshold:
            print(f"OK: diff={diff} threshold={threshold} "
                  f"({width}x{height}, fuzz={args.fuzz}%)")
            return 0
        return _report(
            f"visual diff {diff} > threshold {threshold} "
            f"({width}x{height} px, fuzz={args.fuzz}%)",
            code=1, error_type="VisualDiff",
            details={"diff_px": diff, "threshold_px": threshold,
                     "width": width, "height": height,
                     "fuzz_pct": args.fuzz,
                     "golden": str(args.golden), "pdf": str(args.pdf)},
            json_mode=je,
        )


if __name__ == "__main__":
    sys.exit(main())

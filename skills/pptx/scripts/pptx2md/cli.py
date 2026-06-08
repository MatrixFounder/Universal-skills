"""CLI surface + orchestration for the pptx → Markdown converter (FC-5).

Owns the argparse contract (ARCH §5.1), path resolution (self-overwrite guard +
stdout link-base), and the ``_errors`` envelope routing on every failure path —
mirroring ``xlsx2md/cli.py``. ``main`` is wired end-to-end in bead 020-04; in the
stub phase (020-01) it runs the real path guards then returns ``_STUB_SENTINEL``.

Exit-code map (ARCH §5.1): 0 ok · 1 OCR-engine/generic/internal · 2 usage ·
3 EncryptedFileError (encrypted or legacy ``.ppt``) · 6 SelfOverwriteRefused.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import _errors
from office._encryption import EncryptedFileError

from . import emit, extract, images
from .exceptions import BadInput, InternalError, SelfOverwriteRefused, _AppError
from .model import MediaAsset

_EXIT_OK = 0
_EXIT_USAGE = 2
_EXIT_ENCRYPTED = 3
_EXIT_SELF_OVERWRITE = 6  # documented in the §5.1 map; SelfOverwriteRefused.CODE owns the raise
_DEFAULT_OCR_LANG = "eng+rus"


# --------------------------------------------------------------------------- #
# Argparse surface (ARCH §5.1)
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    """Construct the full CLI surface. Defaults are the 020-01 frozen baseline."""
    p = argparse.ArgumentParser(
        prog="pptx2md.py",
        description="TASK 020: Convert a .pptx/.pptm deck into structured Markdown.",
        epilog=(
            "Images are extracted to a sidecar media/ folder and linked. "
            "OCR is OPT-IN (--ocr) and soft-optional: it shells out to the system "
            "`tesseract` (eng+rus by default) per image; without --ocr the tool "
            "never needs tesseract."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "INPUT",
        nargs="?",
        default=None,
        help="Path to the .pptx / .pptm deck to convert (required at runtime).",
    )
    p.add_argument(
        "OUTPUT",
        nargs="?",
        default="-",
        help="Output .md path, or '-' for stdout (default: stdout).",
    )
    p.add_argument(
        "--no-images",
        action="store_true",
        default=False,
        help="Do not extract images; emit text + tables + notes only (no media dir).",
    )
    p.add_argument(
        "--media-dir",
        metavar="DIR",
        type=Path,
        default=None,
        help="Sidecar directory for extracted images (default: <output-stem>.media/).",
    )
    p.add_argument(
        "--no-notes",
        action="store_true",
        default=False,
        help="Suppress speaker-notes blocks (default: include notes when present).",
    )
    p.add_argument(
        "--include-hidden",
        action="store_true",
        default=False,
        help='Include hidden slides (p:sld show="0"); default: skip hidden.',
    )
    p.add_argument(
        "--ocr",
        action="store_true",
        default=False,
        help="Opt-in: OCR each extracted image with system tesseract (default: off).",
    )
    p.add_argument(
        "--ocr-lang",
        metavar="LANGS",
        default=_DEFAULT_OCR_LANG,
        help=f"tesseract language(s), '+'-joined (default: {_DEFAULT_OCR_LANG}).",
    )
    p.add_argument(
        "--jobs",
        metavar="N",
        type=int,
        default=1,
        help="OCR parallelism across images (default: 1 = serial).",
    )
    p.add_argument(
        "--ocr-timeout",
        metavar="SEC",
        type=float,
        default=120.0,
        help="Per-image OCR timeout in seconds (default: 120).",
    )
    p.add_argument(
        "--ocr-denoise",
        action="store_true",
        default=False,
        help=(
            "Opt-in: filter OCR noise from decorative images (off by default — the "
            "plain per-image text path is unchanged). Enables a size-gate "
            "(--ocr-min-px), a confidence-gate (--ocr-min-confidence), and dedup of "
            "identical OCR blocks. Subtractive of noise only; never alters non-OCR text."
        ),
    )
    p.add_argument(
        "--ocr-min-px",
        metavar="N",
        type=int,
        default=48,
        help=(
            "With --ocr-denoise: skip OCR on an image whose smaller side is < N px "
            "(decorative icons/glyphs are never body text; default: 48). No-op without "
            "--ocr-denoise."
        ),
    )
    p.add_argument(
        "--ocr-min-confidence",
        metavar="C",
        type=float,
        default=50.0,
        help=(
            "With --ocr-denoise: keep only tesseract words with confidence >= C and "
            "drop an image whose OCR has fewer than two such words (0–100; default: "
            "50). No-op without --ocr-denoise."
        ),
    )

    _errors.add_json_errors_argument(p)
    return p


# --------------------------------------------------------------------------- #
# Path resolution
# --------------------------------------------------------------------------- #
def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path | None]:
    """Resolve INPUT/OUTPUT; apply same-path guard + output-parent auto-create.

    Returns ``(input_path, output_path)`` where ``output_path`` is ``None`` in
    stdout mode (OUTPUT omitted or ``"-"``).

    Raises:
        BadInput: INPUT omitted or does not exist (exit 1).
        SelfOverwriteRefused: OUTPUT resolves to INPUT after symlink-follow (exit 6).
    """
    if args.INPUT is None:
        raise BadInput("INPUT is required (path to a .pptx/.pptm deck).")
    try:
        input_path = Path(args.INPUT).resolve(strict=True)
    except FileNotFoundError as exc:
        raise BadInput(
            f"Input not found: {Path(args.INPUT).name}",
            details={"path": Path(args.INPUT).name},
        ) from exc

    if args.OUTPUT is None or args.OUTPUT == "-":
        return input_path, None

    output_path = Path(args.OUTPUT).resolve()
    if output_path == input_path:
        raise SelfOverwriteRefused(
            f"OUTPUT resolves to INPUT: {input_path.name}",
            details={"path": input_path.name},
        )
    if not output_path.parent.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
    return input_path, output_path


def _resolve_media_dir(
    args: argparse.Namespace, output_path: Path | None
) -> tuple[Path, str]:
    """Return ``(media_dir, link_base)`` (D-7 / MAJOR-4).

    * file mode  — media_dir defaults to ``<out-stem>.media/`` beside the .md;
      ``link_base`` is the media dir path *relative to the .md*.
    * stdout mode — media_dir defaults to ``<input-stem>.media/`` under CWD;
      ``link_base`` is *relative to CWD*.

    A custom ``--media-dir`` is honoured in both modes; ``link_base`` is then the
    relative path from the reference dir (the .md's parent, or CWD) to it.
    ``link_base`` always uses POSIX separators so the emitted ``![](...)`` link is
    portable.
    """
    input_path = Path(args.INPUT) if args.INPUT is not None else Path(".")
    if output_path is not None:
        ref_dir = output_path.parent
        default_stem = output_path.stem
    else:
        ref_dir = Path.cwd()
        default_stem = input_path.stem

    if args.media_dir is not None:
        media_dir = args.media_dir.resolve()
    else:
        media_dir = (ref_dir / f"{default_stem}.media").resolve()

    link_base = os.path.relpath(media_dir, start=ref_dir).replace(os.sep, "/")
    return media_dir, link_base


# --------------------------------------------------------------------------- #
# Pipeline + output
# --------------------------------------------------------------------------- #
def _build_ocr_text(deck, assets: dict, args: argparse.Namespace) -> dict:
    """Build ``{MediaAsset: ocr_text}`` over the unique materialised assets.

    Lazy-imports ``ocr`` (so the base path never needs tesseract), probes the engine
    once (fail-loud before any output), then OCRs each distinct ``MediaAsset`` (cached
    by identity). The per-image OCR body lands in bead 020-05; here we wire the call
    site so the no-OCR MVP path is fully exercised.
    """
    from . import ocr  # lazy — only under --ocr (R-C1d)

    ocr.probe(args.ocr_lang)
    unique = [a for a in dict.fromkeys(assets.values()) if isinstance(a, MediaAsset)]

    def _ocr_one(a: MediaAsset) -> tuple[MediaAsset, str]:
        entry = deck.blobs.get(a.sha1)  # (blob, content_type) — always present for an asset
        if entry is None:
            return a, ""
        return a, ocr.ocr_asset(
            entry[0], args.ocr_lang, args.ocr_timeout,
            denoise=args.ocr_denoise, min_px=args.ocr_min_px,
            min_conf=args.ocr_min_confidence,
        )

    if args.jobs and args.jobs > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            pairs = list(pool.map(_ocr_one, unique))
    else:
        pairs = [_ocr_one(a) for a in unique]
    return {a: t for a, t in pairs if t}


def _write_output(output_path: Path | None, chunks) -> None:
    """Stream ``chunks`` to stdout (stdout mode) or atomically to ``output_path``.

    File mode (R-D4 / I-4): write to a sibling ``.partial`` then ``os.replace``; any
    exception mid-write unlinks the temp so no partial ``.md`` is ever left behind.

    Honest scope: the temp uses a fixed ``.partial`` suffix, so two *concurrent*
    invocations targeting the same OUTPUT are unsupported (single-tenant local-CLI
    trust model — concurrent same-target runs are not a claimed use case).
    """
    if output_path is None:
        for chunk in chunks:
            sys.stdout.write(chunk)
        return
    temp = output_path.with_suffix(output_path.suffix + ".partial")
    try:
        with open(temp, "w", encoding="utf-8") as fp:
            for chunk in chunks:
                fp.write(chunk)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    os.replace(temp, output_path)


def convert(
    input_path: Path,
    output_path: Path | None,
    args: argparse.Namespace,
) -> int:
    """Run the full pipeline for already-resolved paths. Returns 0 on success.

    pptx's programmatic API name (intentionally not ``convert_pptx_to_md`` — diverges
    from xlsx's ``convert_xlsx_to_md`` by design, MINOR-3).
    """
    media_dir, link_base = _resolve_media_dir(args, output_path)
    prs = extract.open_deck(input_path)
    deck = extract.build_deck(prs, args, source_name=input_path.name)
    assets = images.materialise(
        deck, media_dir, link_base, no_images=args.no_images, input_path=input_path,
        vector_timeout=args.ocr_timeout, jobs=args.jobs,
    )
    ocr_text = _build_ocr_text(deck, assets, args) if args.ocr else {}
    if (
        output_path is None
        and not args.no_images
        and any(isinstance(a, MediaAsset) for a in assets.values())
    ):
        sys.stderr.write(f"note: media written to {media_dir}\n")
    _write_output(output_path, emit.render_deck(deck, assets, ocr_text, args))
    return _EXIT_OK


# --------------------------------------------------------------------------- #
# main()
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    """Top-level orchestrator. Routes every failure through ``_errors.report_error``.

    Exit map (§5.1): 0 ok · 1 OCR-engine/generic/internal · 2 usage · 3
    EncryptedFileError · 6 SelfOverwriteRefused.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    json_mode = bool(args.json_errors)

    try:
        input_path, output_path = _resolve_paths(args)
        return convert(input_path, output_path, args)
    except EncryptedFileError:
        # Build a BASENAME-only message — do NOT echo str(exc): the shared
        # EncryptedFileError embeds the resolved ABSOLUTE input path, and every other
        # error path here sanitises to the basename (vdd-multi security LOW-1).
        return _errors.report_error(
            f"{_input_path_name(args)}: encrypted or legacy CFB container "
            "(password-protected OOXML, or a legacy .doc/.xls/.ppt). Remediate "
            "upstream — remove the password (office_passwd.py) or re-save as .pptx.",
            code=_EXIT_ENCRYPTED,
            error_type="EncryptedFileError",
            details={"filename": _input_path_name(args)},
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except _AppError as exc:
        return _errors.report_error(
            str(exc),
            code=exc.CODE,
            error_type=exc.error_type,
            details=exc.details,
            json_mode=json_mode,
            stream=sys.stderr,
        )
    except Exception as exc:  # noqa: BLE001 — terminal catch-all, redacted (AR-3)
        return _errors.report_error(
            f"Internal error: {type(exc).__name__}",
            code=InternalError.CODE,
            error_type="InternalError",
            json_mode=json_mode,
            stream=sys.stderr,
        )


def _input_path_name(args: argparse.Namespace) -> str:
    """Basename of INPUT for error context (never an absolute path)."""
    return Path(args.INPUT).name if args.INPUT else ""


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

"""CLI surface + orchestration for the html2md Web/HTML → Markdown converter (FC-5).

Owns the argparse contract (ARCH §5.1), INPUT (URL-or-path) + OUTPUT_DIR resolution
(self-overwrite guard + stdout mode), and the ``_errors`` envelope routing on every
failure path — mirroring ``pptx2md/cli.py``. ``main``/``convert`` are wired
end-to-end in bead 022-05; in the stub phase (022-01) ``main`` runs the real path
guards then returns ``_STUB_SENTINEL``.

Exit-code map (ARCH §5.1): 0 ok · 1 BadInput/ConvertFailed/internal · 2 usage ·
3 EngineNotInstalled · 6 SelfOverwriteRefused · 10 FetchFailed.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# scripts/ on sys.path so the sibling ``_errors`` helper imports under any entry
# (the shim inserts it at runtime; tests run with scripts/ as cwd).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _errors  # noqa: E402

from .exceptions import BadInput, InternalError, SelfOverwriteRefused, _AppError  # noqa: E402

_EXIT_OK = 0
_EXIT_USAGE = 2
_EXIT_ENGINE = 3
_EXIT_SELF_OVERWRITE = 6  # SelfOverwriteRefused.CODE owns the raise
_EXIT_FETCH = 10
_DEFAULT_ATTACH_DIR = "_attachments"


# --------------------------------------------------------------------------- #
# Argparse surface (ARCH §5.1)
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    """Construct the full CLI surface. Defaults are the 022-01 frozen baseline."""
    p = argparse.ArgumentParser(
        prog="html2md.py",
        description="TASK 022: Convert a web URL or saved HTML/MHTML/webarchive into Markdown.",
        epilog=(
            "INPUT is a URL or a local .html/.htm/.mhtml/.mht/.webarchive. By default "
            "BOTH <slug>.md (whole page) and <slug>.reader.md (reader-extracted) are "
            "written, and images are downloaded into _attachments/. The Chrome engine "
            "(--engine chrome) is OPT-IN and soft-optional."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "INPUT", nargs="?", default=None,
        help="URL or path to .html/.htm/.mhtml/.mht/.webarchive (required at runtime).",
    )
    p.add_argument(
        "OUTPUT_DIR", nargs="?", default=None,
        help="Directory to write Markdown + _attachments into (default: stdout mode).",
    )
    p.add_argument(
        "--engine", choices=("lite", "chrome", "auto"), default="auto",
        help="URL fetch engine: lite (httpx+trafilatura), chrome (Playwright), or "
             "auto (lite then chrome fallback). Default: auto.",
    )
    reader = p.add_mutually_exclusive_group()
    reader.add_argument(
        "--reader-mode", dest="reader", action="store_true", default=True,
        help="Also emit <slug>.reader.md (default: on).",
    )
    reader.add_argument(
        "--no-reader", dest="reader", action="store_false",
        help="Suppress the reader-extracted variant; emit a single .md only.",
    )
    dl = p.add_mutually_exclusive_group()
    dl.add_argument(
        "--download-images", dest="download_images", action="store_true", default=True,
        help="Download images into the attachments dir (default: on).",
    )
    dl.add_argument(
        "--no-download-images", dest="download_images", action="store_false",
        help="Keep remote image URLs verbatim (no download).",
    )
    p.add_argument(
        "--attachments-dir", metavar="DIR", default=_DEFAULT_ATTACH_DIR,
        help=f"Attachments folder name (default: {_DEFAULT_ATTACH_DIR}).",
    )
    p.add_argument(
        "--archive-frame", metavar="SPEC", default="main",
        help="For .webarchive/.mhtml: which subframe (main|N|all|auto; default main).",
    )
    p.add_argument(
        "--max-bytes", metavar="N", type=int, default=None,
        help="Cap bytes fetched per request (SSRF/DoS bound; default: unbounded).",
    )
    p.add_argument(
        "--max-images", metavar="N", type=int, default=None,
        help="Cap the number of images downloaded (default: unbounded).",
    )
    p.add_argument(
        "--stdout", action="store_true", default=False,
        help="Emit whole-page Markdown to stdout (agent-step mode).",
    )
    _errors.add_json_errors_argument(p)
    return p


# --------------------------------------------------------------------------- #
# Path / URL resolution
# --------------------------------------------------------------------------- #
def _resolve_paths(args: argparse.Namespace) -> tuple[str, str, Path | None, bool]:
    """Resolve INPUT (URL or local) + OUTPUT_DIR.

    Returns ``(input_ref, mode, output_dir|None, stdout_mode)`` where ``mode`` is
    ``"url"`` (scheme http/https — no filesystem stat) or ``"local"`` (resolved,
    must exist; ``acquire`` later refines local → file/archive).

    Raises:
        BadInput (1): INPUT omitted, or a local path that does not exist.
        SelfOverwriteRefused (6): OUTPUT_DIR resolves to the INPUT file (incl. symlink).
    """
    if args.INPUT is None:
        raise BadInput("INPUT is required (a URL or a local .html/.mhtml/.webarchive).")

    scheme = urlparse(args.INPUT).scheme.lower()
    if scheme in ("http", "https"):
        mode = "url"
        input_ref = args.INPUT
    else:
        mode = "local"
        try:
            input_ref = str(Path(args.INPUT).resolve(strict=True))
        except FileNotFoundError as exc:
            raise BadInput(
                f"Input not found: {Path(args.INPUT).name}",
                details={"path": Path(args.INPUT).name},
            ) from exc

    if bool(args.stdout):
        return input_ref, mode, None, True

    # Default output (no OUTPUT_DIR, no --stdout): a folder under ./tmp/, matching the
    # docx/pdf convention of writing files to an explicit working-dir path (never
    # silently to stdout). An explicit OUTPUT_DIR overrides; --stdout opts into stdout.
    output_dir = (Path(args.OUTPUT_DIR) if args.OUTPUT_DIR
                  else Path.cwd() / "tmp" / "html2md_out").resolve()
    if mode == "local" and output_dir == Path(input_ref):
        raise SelfOverwriteRefused(
            f"OUTPUT_DIR resolves to INPUT: {Path(input_ref).name}",
            details={"path": Path(input_ref).name},
        )
    # NB: the directory is created lazily by emit() right before writing — a run
    # that fails earlier (fetch error, EngineNotInstalled, …) leaves no empty dir.
    return input_ref, mode, output_dir, False


# --------------------------------------------------------------------------- #
# Pipeline (wired in 022-05)
# --------------------------------------------------------------------------- #
def convert(args: argparse.Namespace) -> int:
    """Run the full pipeline for parsed ``args``: acquire → clean → core → emit.

    Returns 0 on success.
    """
    from . import acquire as acquire_mod
    from . import clean as clean_mod
    from . import core_bridge, emit as emit_mod
    from .md_clean import tidy_markdown

    input_ref, mode, output_dir, stdout_mode = _resolve_paths(args)
    acq = acquire_mod.acquire(input_ref, args)
    cleaned = clean_mod.clean(acq, reader=bool(args.reader))
    md_whole = tidy_markdown(core_bridge.html_to_markdown(cleaned.whole_html))
    md_reader = (
        tidy_markdown(core_bridge.html_to_markdown(cleaned.reader_html))
        if cleaned.reader_html is not None else None
    )
    emit_mod.emit(
        acq, cleaned, md_whole, md_reader, args,
        output_dir=output_dir, stdout_mode=stdout_mode, input_ref=input_ref,
    )
    return _EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Top-level orchestrator. Routes every failure through ``_errors.report_error``.

    Exit map (§5.1): 0 ok · 1 BadInput/ConvertFailed/internal · 2 usage ·
    3 EngineNotInstalled · 6 SelfOverwriteRefused · 10 FetchFailed.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    json_mode = bool(args.json_errors)

    try:
        return convert(args)
    except _AppError as exc:
        return _errors.report_error(
            str(exc), code=exc.CODE, error_type=exc.error_type,
            details=exc.details, json_mode=json_mode, stream=sys.stderr,
        )
    except Exception as exc:  # noqa: BLE001 — terminal catch-all, redacted
        return _errors.report_error(
            f"Internal error: {type(exc).__name__}",
            code=InternalError.CODE, error_type="InternalError",
            json_mode=json_mode, stream=sys.stderr,
        )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

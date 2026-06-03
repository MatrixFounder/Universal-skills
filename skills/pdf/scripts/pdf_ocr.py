#!/usr/bin/env python3
"""OCR a scanned (image-only) PDF into a **searchable PDF** (eng+rus by default).

`pdf_ocr.py` is a thin, contract-compliant CLI wrapper around `ocrmypdf`. It
takes an image-only (scanned) PDF and produces a searchable PDF: the original
page raster is preserved verbatim and an invisible OCR text layer is overlaid so
the text becomes selectable/extractable. The default OCR languages are English +
Russian (``eng+rus``); use ``--lang`` to change them.

It is the remediation hop for ``pdf_extract.py`` exit ``10 DocumentScanned``::

    pdf_extract.py scan.pdf            # exit 10 DocumentScanned (the trigger)
    pdf_ocr.py     scan.pdf scan.ocr.pdf     # → searchable PDF (eng+rus)
    pdf_extract.py scan.ocr.pdf        # exit 0, doc_scanned=false, text present

Engine packaging is **soft-optional**: `ocrmypdf` is NOT a base dependency and is
imported lazily. Install it (plus the system tools) with
``bash install.sh --with-ocr`` — see ``references/ocr.md``. A missing engine or
language pack fails loud with remediation, never silently.

Honest scope (v1):
  - The OCR engine is not bundled: system ``tesseract`` (+ ``eng``,``rus``
    traineddata) and ``ghostscript`` are detected, never installed by us.
  - Not a Markdown converter — final Markdown composition stays
    ``pdf_extract.py`` + LLM judgement (see ``references/pdf-to-markdown.md``).
  - Default ``--skip-text`` never destroys an existing vector-text layer and
    never errors on a mixed PDF; ``PriorOcrFound`` is unreachable on the default
    path (only ``--redo-ocr`` / ``--force-ocr`` can hit it).
  - ``--password`` is read from argv only (visible in ``ps``); the OCR'd output
    is unencrypted (re-encryption is out of scope).
  - No global timeout / decompression-bomb hardening beyond what ocrmypdf and
    ghostscript do themselves: a pathological PDF can run long.

Usage:
    pdf_ocr.py INPUT.pdf OUTPUT.pdf
               [--lang LANGS]                          # default "eng+rus"
               [--skip-text | --redo-ocr | --force-ocr]  # default --skip-text
               [--sidecar PATH.txt] [--jobs N] [--password PW]
               [--deskew] [--rotate-pages] [--clean] [--json-errors]

Exit codes (D-A1 — all hard failures are 1, discriminated by the --json-errors
envelope `type`; no new codes; `10` stays exclusive to pdf_extract.py):
    0  — success: searchable PDF written
    1  — failure: OcrEngineUnavailable / LanguagePackMissing / EncryptedInput /
         InputUnreadable / PriorOcrFound / OutputWriteFailed / InternalError /
         InputNotFound
    2  — usage error (argparse; incl. the --skip-text/--redo-ocr/--force-ocr mutex)
    6  — SelfOverwriteRefused: OUTPUT (or --sidecar) resolves to INPUT
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _errors import add_json_errors_argument, report_error

# A CLI owns its stderr: with --json-errors a wrapper parses stderr as JSON.
# The OCR engine libraries emit free-text progress/warnings — silence them so
# only our envelope is written.
for _noisy_logger in ("ocrmypdf", "pikepdf", "pdfminer", "PIL"):
    logging.getLogger(_noisy_logger).setLevel(logging.ERROR)

_EXIT_OK = 0
_EXIT_FAIL = 1
_EXIT_USAGE = 2
_EXIT_SELF_OVERWRITE = 6  # cross-7 parity: OUTPUT/sidecar resolves to INPUT
_DEFAULT_LANG = "eng+rus"


class _OcrError(Exception):
    """Domain failure inside the OCR pipeline. `error_type` becomes the
    `--json-errors` envelope `type`; `_report` maps it to the exit code
    (`code`, default 1; 6 for SelfOverwriteRefused)."""

    def __init__(
        self,
        message: str,
        *,
        error_type: str,
        code: int = _EXIT_FAIL,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.code = code
        self.details = details


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argparse CLI. REAL from the stub phase — the smoke test
    asserts the `--help` surface; the mode group enforces the mutex."""
    parser = argparse.ArgumentParser(
        prog="pdf_ocr.py",
        description=(
            "OCR a scanned (image-only) PDF into a searchable PDF (default "
            "languages eng+rus). The original page raster is preserved and an "
            "invisible OCR text layer is overlaid. Remediation hop for "
            "pdf_extract.py exit 10 DocumentScanned; see references/ocr.md."
        ),
        epilog=(
            "Exit codes: 0 success; 1 failure (envelope `type` discriminates: "
            "OcrEngineUnavailable / LanguagePackMissing / EncryptedInput / "
            "InputUnreadable / PriorOcrFound / OutputWriteFailed / InputNotFound); "
            "2 usage error; 6 SelfOverwriteRefused (OUTPUT or --sidecar resolves "
            "to INPUT). Engine is soft-optional: `bash install.sh --with-ocr`."
        ),
    )
    parser.add_argument("INPUT", type=Path, help="Source (scanned) PDF file.")
    parser.add_argument(
        "OUTPUT", type=Path,
        help="Destination searchable PDF (overwritten).",
    )
    parser.add_argument(
        "--lang", default=_DEFAULT_LANG, metavar="LANGS",
        help="OCR languages as a tesseract '+'-joined list (default: "
             f"{_DEFAULT_LANG!r}). Every pack must be installed; e.g. eng+rus+deu.",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--skip-text", dest="mode", action="store_const", const="skip_text",
        help="OCR only pages that have no text; leave existing vector text "
             "untouched (DEFAULT). Never errors on a mixed PDF.",
    )
    mode_group.add_argument(
        "--redo-ocr", dest="mode", action="store_const", const="redo_ocr",
        help="Strip any existing OCR text layer and OCR again.",
    )
    mode_group.add_argument(
        "--force-ocr", dest="mode", action="store_const", const="force_ocr",
        help="Rasterise and OCR every page, even pages with real vector text "
             "(lossy for born-digital pages).",
    )
    parser.set_defaults(mode="skip_text")

    parser.add_argument(
        "--sidecar", type=Path, default=None, metavar="PATH.txt",
        help="Also write the recognised plain text to this file.",
    )
    parser.add_argument(
        "--jobs", type=int, default=None, metavar="N",
        help="Number of OCR worker processes (default: ocrmypdf auto = CPUs).",
    )
    parser.add_argument(
        "--password", default=None, metavar="PW",
        help="Password for an encrypted input PDF (decrypted before OCR; the "
             "output is unencrypted). NOTE: argv is visible in process listings "
             "(ps) — intended for local-CLI use.",
    )
    parser.add_argument(
        "--deskew", action="store_true",
        help="Straighten skewed scans before OCR.",
    )
    parser.add_argument(
        "--rotate-pages", action="store_true",
        help="Auto-orient pages via OSD (needs the tesseract 'osd' data).",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Despeckle scans before OCR (needs the 'unpaper' binary).",
    )
    add_json_errors_argument(parser)
    return parser


def _same_path(a: Path, b: Path) -> bool:
    """True if `a` and `b` resolve to the same filesystem path (symlinks
    followed). `b` need not exist yet — `resolve()` is non-strict."""
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path | None]:
    """Validate INPUT existence and refuse destructive path aliasing.

    Raises `_OcrError` (`InputNotFound`, or `SelfOverwriteRefused` with code 6)
    on a problem; returns `(input, output, sidecar)` otherwise. Existence is
    checked before the overwrite guards (parity with `pdf_extract.py`)."""
    inp: Path = args.INPUT
    outp: Path = args.OUTPUT
    sidecar: Path | None = args.sidecar

    if not inp.is_file():
        raise _OcrError(
            f"Input not found: {inp}",
            error_type="InputNotFound", details={"path": str(inp)},
        )
    # cross-7 parity: refuse to overwrite the input PDF with the OCR output.
    # `resolve()` also neutralises a symlinked OUTPUT pointing back at INPUT.
    if _same_path(inp, outp):
        raise _OcrError(
            f"Refusing to overwrite the input PDF with the OCR output "
            f"(OUTPUT resolves to INPUT): {inp}",
            error_type="SelfOverwriteRefused", code=_EXIT_SELF_OVERWRITE,
            details={"path": str(inp)},
        )
    if sidecar is not None and (_same_path(sidecar, inp) or _same_path(sidecar, outp)):
        raise _OcrError(
            f"Refusing to write the --sidecar over the input or output: {sidecar}",
            error_type="SelfOverwriteRefused", code=_EXIT_SELF_OVERWRITE,
            details={"path": str(sidecar)},
        )
    return inp, outp, sidecar


def _require_engine():  # noqa: ANN202 — returns the ocrmypdf module
    """Lazy-import the optional `ocrmypdf` engine; raise `OcrEngineUnavailable`
    with remediation if it is missing.

    The import is deliberately inside this function (not at module top) so the
    base pdf skill imports without the optional dependency. Mirrors pdf-11's
    `ChromeEngineUnavailable` discipline."""
    try:
        import ocrmypdf  # noqa: PLC0415 — lazy by design (soft-optional engine)
    except ImportError as exc:
        raise _OcrError(
            "OCR engine not available (ocrmypdf is not installed). Install it: "
            "`bash skills/pdf/scripts/install.sh --with-ocr`, and ensure the "
            "system tools `tesseract` (with the eng + rus language packs) and "
            "`ghostscript` are on PATH. See references/ocr.md.",
            error_type="OcrEngineUnavailable",
        ) from exc
    return ocrmypdf


def _installed_languages() -> set[str]:
    """Return the set of installed tesseract language codes.

    Queried straight from the `tesseract` CLI (the source of truth that ocrmypdf
    itself consults, and the same tool `install.sh --with-ocr` probes) rather
    than an ocrmypdf-internal helper — keeps this verifiable and version-stable.
    `--list-langs` prints to stdout on some tesseract builds and stderr on
    others, so both streams are parsed (parity with the install.sh probe)."""
    exe = shutil.which("tesseract")
    if exe is None:
        raise _OcrError(
            "tesseract not found on PATH (required by ocrmypdf for OCR). Install "
            "it (macOS `brew install tesseract tesseract-lang`; Debian `apt "
            "install tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus`). See "
            "references/ocr.md.",
            error_type="OcrEngineUnavailable",
        )
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell, trusted exe
            [exe, "--list-langs"], capture_output=True, text=True, check=False,
        )
    except OSError as exc:
        raise _OcrError(
            f"Could not run `tesseract --list-langs`: {exc}",
            error_type="OcrEngineUnavailable",
        ) from exc
    langs: set[str] = set()
    for line in f"{proc.stdout}\n{proc.stderr}".splitlines():
        token = line.strip()
        # Skip the banner line ("List of available languages ...") and blanks.
        if not token or token.lower().startswith("list of"):
            continue
        langs.add(token)
    return langs


def _validate_languages(lang: str, installed: set[str] | None = None) -> list[str]:
    """Split `lang` on '+' and validate each token against the installed
    tesseract language set, returning the requested list in order.

    Raises `LanguagePackMissing` (an empty `--lang`, or any uninstalled pack)
    with a per-OS remediation hint. `installed` defaults to a live
    `_installed_languages()` query; tests pass an explicit set to run without a
    real tesseract."""
    requested = [t for t in lang.split("+") if t]
    if not requested:
        raise _OcrError(
            "No OCR language given (--lang was empty).",
            error_type="LanguagePackMissing", details={"requested": lang},
        )
    if installed is None:
        installed = _installed_languages()
    missing = [t for t in requested if t not in installed]
    if missing:
        deb = " ".join(f"tesseract-ocr-{m}" for m in missing)
        fed = " ".join(f"tesseract-langpack-{m}" for m in missing)
        raise _OcrError(
            f"tesseract language pack(s) not installed: {', '.join(missing)} "
            f"(requested --lang {lang!r}). Install — macOS: `brew install "
            f"tesseract-lang`; Debian: `apt install {deb}`; Fedora: `dnf install "
            f"{fed}`. See references/ocr.md.",
            error_type="LanguagePackMissing",
            details={"missing": missing, "requested": lang},
        )
    return requested


# ocrmypdf exception class-name → (envelope `type`, message prefix). Matched by
# MRO class-name (not by importing the classes) so the mapping is robust across
# ocrmypdf versions and does not require the engine to be importable here. Verify
# the names against the pinned ocrmypdf when the engine is available.
_ENGINE_EXC_MAP: dict[str, tuple[str, str]] = {
    "EncryptedPdfError": (
        "EncryptedInput",
        "Input PDF is encrypted; supply the password with --password",
    ),
    "PriorOcrFoundError": (
        "PriorOcrFound",
        "Input already has a text layer; use --redo-ocr or --force-ocr",
    ),
    "InputFileError": ("InputUnreadable", "Input PDF could not be read"),
    "BadArgsError": ("InputUnreadable", "ocrmypdf rejected the input/arguments"),
    "UnsupportedImageFormatError": (
        "InputUnreadable", "Unsupported image format in the input PDF",
    ),
    "DpiError": ("InputUnreadable", "Input image DPI could not be determined"),
    "MissingDependencyError": (
        "OcrEngineUnavailable",
        "A required OCR system tool is missing (tesseract / ghostscript / unpaper)",
    ),
    "OutputFileAccessError": ("OutputWriteFailed", "Could not write the output PDF"),
}


def _map_engine_exception(exc: Exception) -> _OcrError:
    """Translate an exception raised by `ocrmypdf.ocr()` into an `_OcrError`
    with the right envelope `type`. Already-`_OcrError` passes through; `OSError`
    (output write) maps to `OutputWriteFailed`; unknown → `InternalError`."""
    if isinstance(exc, _OcrError):
        return exc
    names = {cls.__name__ for cls in type(exc).__mro__}
    for key, (etype, prefix) in _ENGINE_EXC_MAP.items():
        if key in names:
            return _OcrError(f"{prefix}: {exc}", error_type=etype)
    if isinstance(exc, OSError):
        return _OcrError(
            f"Could not write the output PDF: {exc}",
            error_type="OutputWriteFailed",
        )
    return _OcrError(
        f"Internal OCR error: {type(exc).__name__}: {exc}",
        error_type="InternalError",
    )


def _decrypt_to_temp(inp: Path, password: str, out_dir: Path) -> Path:
    """Decrypt `inp` with `password` to a 0600 scratch PDF in `out_dir` and
    return its path. ocrmypdf has no native input-password path, so we decrypt
    with `pikepdf` first (D-A3). The scratch is 0600 and lives in the OUTPUT dir
    (not a world-readable /tmp), and is removed by `run_ocr`'s `finally` (S-3).

    Scope note: only the scratch is mode-0600. The final searchable PDF is, for
    an encrypted input, the **decrypted** content with whatever mode ocrmypdf
    writes (operator's responsibility per the single-tenant trust model; see
    references/ocr.md). Re-encryption of the output is out of scope.

    Raises `EncryptedInput` on a wrong/absent password, `OcrEngineUnavailable`
    if `pikepdf` is missing (it ships with ocrmypdf)."""
    try:
        import pikepdf  # noqa: PLC0415 — lazy (ships with the soft-optional engine)
    except ImportError as exc:
        raise _OcrError(
            "pikepdf is not available (it ships with ocrmypdf). Install the OCR "
            "engine: `bash skills/pdf/scripts/install.sh --with-ocr`.",
            error_type="OcrEngineUnavailable",
        ) from exc

    # mkstemp creates the file with 0600; pikepdf.save() then overwrites it.
    fd, tmp_name = tempfile.mkstemp(dir=str(out_dir), suffix=".dec.pdf")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with pikepdf.open(str(inp), password=password) as pdf:
            pdf.save(str(tmp_path))
    except pikepdf.PasswordError as exc:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise _OcrError(
            "Wrong or missing password for the encrypted input PDF.",
            error_type="EncryptedInput",
        ) from exc
    except Exception as exc:  # noqa: BLE001 — corrupt PDF etc. → clean envelope
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise _OcrError(
            f"Could not read or decrypt the input PDF: {exc}",
            error_type="InputUnreadable",
        ) from exc
    return tmp_path


def run_ocr(
    inp: Path,
    outp: Path,
    *,
    lang: list[str],
    mode: str,
    sidecar: Path | None,
    jobs: int | None,
    password: str | None,
    deskew: bool,
    rotate_pages: bool,
    clean: bool,
    installed: set[str] | None = None,
) -> int:
    """Drive `ocrmypdf` to produce the searchable PDF (atomic write), mapping
    engine exceptions to `_OcrError`. Returns `_EXIT_OK` on success.

    `installed` is the set of installed tesseract languages (for the
    `--rotate-pages` osd check); when None it is queried lazily — pass the set
    `main` already computed to avoid a second `tesseract --list-langs` spawn.

    The output is written to an O_EXCL `.partial` scratch (mkstemp) in the
    OUTPUT dir and `os.replace`d into place; every temp (the `.partial`, plus a
    decrypted scratch when `--password` is used) is removed on every exit path —
    so a failure leaves no partial or stale OUTPUT (invariant I-3). The image-prep
    knobs have host
    prerequisites checked up front (loud, never silent): `--rotate-pages` needs
    the tesseract `osd` data and `--clean` needs the `unpaper` binary;
    `--deskew` needs no extra tool."""
    ocr = _require_engine()

    # R9 prerequisites — fail loud before doing any work.
    if rotate_pages and "osd" not in (
        installed if installed is not None else _installed_languages()
    ):
        raise _OcrError(
            "--rotate-pages needs the tesseract 'osd' data, which is not "
            "installed. Install — macOS: `brew install tesseract-lang`; Debian: "
            "`apt install tesseract-ocr-osd`; Fedora: `dnf install "
            "tesseract-langpack-osd`. See references/ocr.md.",
            error_type="LanguagePackMissing", details={"missing": ["osd"]},
        )
    if clean and shutil.which("unpaper") is None:
        raise _OcrError(
            "--clean needs the 'unpaper' binary, which is not on PATH. Install — "
            "macOS: `brew install unpaper`; Debian/Fedora: `apt/dnf install "
            "unpaper`. See references/ocr.md.",
            error_type="OcrEngineUnavailable",
        )

    # Exactly one OCR mode (argparse enforces the mutex). `mode` IS the ocrmypdf
    # kwarg name; validate membership so an out-of-band caller gets a clean
    # envelope, not a raw KeyError.
    if mode not in ("skip_text", "redo_ocr", "force_ocr"):
        raise _OcrError(
            f"Unknown OCR mode: {mode!r}.", error_type="InternalError",
        )
    kwargs: dict = {"language": lang, "progress_bar": False, mode: True}
    if sidecar is not None:
        kwargs["sidecar"] = str(sidecar)
    if jobs is not None:
        kwargs["jobs"] = jobs
    if deskew:
        kwargs["deskew"] = True
    if rotate_pages:
        kwargs["rotate_pages"] = True
    if clean:
        kwargs["clean"] = True

    # Atomic write via an O_EXCL, 0600 scratch in the OUTPUT dir (mkstemp →
    # unpredictable name, no symlink-follow/TOCTOU on a pre-planted `.partial`),
    # then os.replace into place. The decrypt-to-temp (R5) AND the ocr call live
    # inside the try so any failure — including a raw OSError from mkstemp/decrypt
    # or a NON-ZERO ExitCode RETURNED (not raised) by ocrmypdf — is mapped to a
    # clean envelope and never leaves a partial or decrypted scratch behind (I-3).
    tmp_out: Path | None = None
    decrypted: Path | None = None
    try:
        # mkstemp is INSIDE the try so an OSError on an unwritable/nonexistent
        # OUTPUT dir maps to a clean OutputWriteFailed envelope instead of
        # escaping `main` (which only catches `_OcrError`) as a raw traceback.
        fd, tmp_name = tempfile.mkstemp(dir=str(outp.parent), suffix=".partial.pdf")
        os.close(fd)
        tmp_out = Path(tmp_name)

        # R5: ocrmypdf has no input-password path — decrypt to a 0600 scratch in
        # the OUTPUT dir first, then OCR that (D-A3). The output is unencrypted.
        if password is not None:
            decrypted = _decrypt_to_temp(inp, password, outp.parent)
        source = decrypted if decrypted is not None else inp

        # `ocrmypdf.ocr(input_file_or_options, output_file, *, ...)` takes the two
        # paths POSITIONALLY (verified against ocrmypdf 17). It RETURNS a non-zero
        # ExitCode for some failures (e.g. invalid_output_pdf) instead of raising
        # — never promote a bad output to success.
        rc = ocr.ocr(str(source), str(tmp_out), **kwargs)
        if rc is not None and int(rc) != 0:
            raise _OcrError(
                f"ocrmypdf reported a non-zero exit code ({int(rc)}); the output "
                "was not produced cleanly.",
                error_type="OutputWriteFailed",
                details={"ocrmypdf_exit": int(rc)},
            )
        os.replace(tmp_out, outp)
    except _OcrError:
        raise
    except Exception as exc:  # noqa: BLE001 — mapped to a clean _OcrError
        raise _map_engine_exception(exc) from exc
    finally:
        # I-3 / S-3: never leave the partial or the decrypted scratch behind
        # (success already moved the partial away).
        for scratch in (tmp_out, decrypted):
            if scratch is not None:
                with contextlib.suppress(OSError):
                    scratch.unlink(missing_ok=True)
    return _EXIT_OK


def _report(exc: _OcrError, *, json_mode: bool) -> int:
    """Emit `exc` through the shared `_errors` envelope and return its code."""
    return report_error(
        exc.message, code=exc.code, error_type=exc.error_type,
        details=exc.details, json_mode=json_mode,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse → resolve/guard → engine → validate langs → OCR.

    Returns the exit code (see the module docstring's matrix). Domain failures
    flow through `_OcrError` → `_report` (the `--json-errors` envelope)."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    je = args.json_errors

    try:
        inp, outp, sidecar = _resolve_paths(args)
        _require_engine()                  # → OcrEngineUnavailable if absent
        # Query the installed tesseract languages ONCE and thread the set into
        # both validation and run_ocr's osd check (avoids a 2nd --list-langs spawn).
        installed = _installed_languages()
        langs = _validate_languages(args.lang, installed)
        code = run_ocr(
            inp, outp, lang=langs, mode=args.mode, sidecar=sidecar,
            jobs=args.jobs, password=args.password, deskew=args.deskew,
            rotate_pages=args.rotate_pages, clean=args.clean, installed=installed,
        )
    except _OcrError as exc:
        return _report(exc, json_mode=je)

    summary = (
        f"OCR complete: {outp} (lang={'+'.join(langs)}, mode={args.mode}"
        + (f", sidecar={sidecar}" if sidecar is not None else "")
        + ")"
    )
    print(summary)
    return code


if __name__ == "__main__":
    sys.exit(main())

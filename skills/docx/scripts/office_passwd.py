#!/usr/bin/env python3
"""Set or remove password protection on .docx/.xlsx/.pptx files.

Three modes:

    office_passwd.py INPUT OUTPUT --encrypt PASSWORD
    office_passwd.py INPUT OUTPUT --decrypt PASSWORD
    office_passwd.py INPUT --check

Encryption uses MS-OFB / Agile (Office 2010+) via msoffcrypto-tool.
The encrypted output is a CFB (Compound File Binary) container that
opens in Word/Excel/PowerPoint with the chosen password; the decrypted
output is a plain OOXML zip that the rest of the office skills can
read directly.

Password input:
- Pass the password as the flag argument: `--encrypt hunter2`.
- Pass `-` to read from stdin (one line, no trailing newline). This
  keeps the password out of `ps`/shell history; combine with shell
  process substitution: `--encrypt - <<<"$PASS"` or `--encrypt -
  </path/to/secret`.

Replication: this file is byte-identical across the three OOXML office
skills (`skills/docx/scripts/`, `…/xlsx/…`, `…/pptx/…`). docx is the
master copy. PDF has its own password mechanism (PdfWriter.encrypt)
and does not use this script.

Exit codes:
    0    success (also: --check on encrypted file)
    1    generic failure (msoffcrypto raised something unexpected)
    2    argparse usage error (auto, see _errors.py)
    3    missing dependency (msoffcrypto-tool not installed)
    4    wrong password supplied to --decrypt
    5    state mismatch (--encrypt on already-encrypted, --decrypt on clean)
    6    refused: INPUT and OUTPUT resolve to the same path
    10   --check: file is NOT encrypted (clean OOXML or other)
    11   input file not found
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _errors import add_json_errors_argument, report_error
from office._encryption import is_cfb_container


def _read_password(value: str, *, source_label: str = "stdin") -> str:
    """Resolve the password argument to a real string.

    `-` means "read one line from stdin" so callers can avoid putting
    the secret on the command line (visible in `ps` and shell history).
    Any trailing newline is stripped, but trailing spaces / tabs are
    preserved (real passwords may end in whitespace; we cannot disambiguate
    "the user meant a trailing space" from "their pipeline added one").
    A one-time stderr warning is emitted in the latter case so users who
    accidentally fed `echo "$PASS"` with a leaky env var get a hint
    instead of an opaque exit-4 later.
    """
    if value != "-":
        return value
    raw = sys.stdin.readline()
    pw = raw.rstrip("\r\n")
    if pw and pw != pw.rstrip(" \t"):
        sys.stderr.write(
            f"warning: {source_label} password ends in whitespace; "
            "trailing chars will be encoded into the password "
            "(this is the most common cause of later 'wrong password' "
            "exits when the user types the visible string).\n"
        )
        sys.stderr.flush()
    return pw


def _import_msoffcrypto(json_mode: bool):
    try:
        import msoffcrypto  # type: ignore
        return msoffcrypto
    except ImportError as exc:
        sys.exit(
            report_error(
                "msoffcrypto-tool is not installed in this skill's venv. "
                "Install it via `pip install msoffcrypto-tool` or re-run "
                "scripts/install.sh.",
                code=3,
                error_type="MissingDependency",
                details={"package": "msoffcrypto-tool", "import_error": str(exc)},
                json_mode=json_mode,
            )
        )


def _msoffcrypto_runtime_errors(msoffcrypto):
    """Tuple of msoffcrypto-tool exception classes that can escape from
    encrypt() / decrypt() / load_key() and are NOT subclasses of OSError
    or ValueError. Without catching these explicitly they would propagate
    as a bare Python traceback — corrupting the JSON envelope contract
    of cross-5 (`--json-errors` promises one line of JSON on failure).
    `InvalidKeyError` and `FileFormatError` are caught separately because
    they map to dedicated exit codes (4 and 1+state) with custom messages.
    """
    exc = msoffcrypto.exceptions
    return (exc.ParseError, exc.DecryptionError, exc.EncryptionError)


def _refuse_self_overwrite(
    input_path: Path,
    output_path: Path,
    json_mode: bool,
) -> int | None:
    """Refuse INPUT == OUTPUT before any open() is called.

    On *nix, `open(P, "wb")` truncates the inode while a sibling
    `open(P, "rb")` still holds a fd against it; the read then sees the
    truncated (now empty) file and msoffcrypto raises FileFormatError —
    by which point the user's source has already been destroyed. The
    fix is a pre-flight refusal: if both arguments resolve to the same
    filesystem path, exit 6 with a dedicated message and DO NOT touch
    either file.

    `Path.resolve(strict=False)` follows symlinks where they exist but
    does not require the target to exist (output usually doesn't yet),
    so we get the right answer regardless of whether OUTPUT is fresh.
    """
    try:
        if input_path.resolve(strict=False) == output_path.resolve(strict=False):
            return report_error(
                f"refusing in-place rewrite: INPUT and OUTPUT resolve to "
                f"the same path ({input_path}). Pick a different OUTPUT "
                "or move the source first; same-path I/O would truncate "
                "the source before encrypt/decrypt streams it.",
                code=6,
                error_type="SelfOverwriteRefused",
                details={
                    "input": str(input_path),
                    "output": str(output_path),
                },
                json_mode=json_mode,
            )
    except OSError as exc:
        # Path.resolve can fail if a parent dir is missing AND
        # strict=True; with strict=False it should not, but we guard
        # anyway so a weird FS doesn't bypass the safety check.
        return report_error(
            f"Cannot resolve input/output paths: {exc}",
            code=1,
            error_type="OSError",
            details={"input": str(input_path), "output": str(output_path)},
            json_mode=json_mode,
        )
    return None


def _format_msoffcrypto_error(exc: BaseException) -> str:
    """Map opaque msoffcrypto/CPython errors into user-actionable text.

    The notable case: CPython 3.11+ guards `int()` on long digit strings
    and raises a ValueError mentioning `int_max_str_digits`. msoffcrypto
    parses some CFB internal field as an integer; on a malformed CFB
    that field is huge garbage and the user sees the cryptic
    `"Exceeds the limit (4300 digits) for integer string conversion;
    use sys.set_int_max_str_digits()"`. The right remediation is "this
    isn't a real encrypted Office file", not "set sys.set_int_max_str_digits".
    """
    msg = str(exc)
    if "digits" in msg and "integer string conversion" in msg:
        return (
            "input does not look like a real encrypted Office file "
            "(internal CFB integer field overflowed CPython's "
            "int-string-conversion limit while parsing). The file is "
            "almost certainly malformed or not actually encrypted."
        )
    return msg


def cmd_check(input_path: Path, json_mode: bool) -> int:
    if not input_path.exists():
        return report_error(
            f"Input not found: {input_path}",
            code=11,
            error_type="FileNotFound",
            details={"path": str(input_path)},
            json_mode=json_mode,
        )
    if is_cfb_container(input_path):
        if not json_mode:
            print(f"{input_path}: encrypted (or legacy CFB)")
        return 0
    if not json_mode:
        print(f"{input_path}: not encrypted")
    return 10


def cmd_encrypt(
    input_path: Path,
    output_path: Path,
    password: str,
    json_mode: bool,
) -> int:
    if not input_path.exists():
        return report_error(
            f"Input not found: {input_path}",
            code=11,
            error_type="FileNotFound",
            details={"path": str(input_path)},
            json_mode=json_mode,
        )
    self_overwrite = _refuse_self_overwrite(input_path, output_path, json_mode)
    if self_overwrite is not None:
        return self_overwrite
    if is_cfb_container(input_path):
        return report_error(
            f"{input_path}: looks already encrypted (or legacy CFB). "
            "Use --decrypt first, or --check to confirm state.",
            code=5,
            error_type="AlreadyEncrypted",
            details={"path": str(input_path)},
            json_mode=json_mode,
        )
    if not password:
        return report_error(
            "--encrypt requires a non-empty password.",
            code=2,
            error_type="UsageError",
            json_mode=json_mode,
        )

    msoffcrypto = _import_msoffcrypto(json_mode)
    runtime_errors = _msoffcrypto_runtime_errors(msoffcrypto)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return report_error(
            f"Cannot create output directory: {exc}",
            code=1,
            error_type="OSError",
            details={"path": str(output_path.parent)},
            json_mode=json_mode,
        )
    # Mirror cmd_decrypt: every failure arm unlinks the half-written
    # output. Without this, a non-OOXML input or a disk-full mid-stream
    # leaves a 0-byte decoy at the output path that masquerades as
    # "not encrypted" to a subsequent --check.
    try:
        with input_path.open("rb") as f_in, output_path.open("wb") as f_out:
            msoffcrypto.OfficeFile(f_in).encrypt(password, f_out)
    except msoffcrypto.exceptions.FileFormatError as exc:
        output_path.unlink(missing_ok=True)
        return report_error(
            f"{input_path}: not a recognised OOXML file ({exc}).",
            code=1,
            error_type="FileFormatError",
            details={"path": str(input_path)},
            json_mode=json_mode,
        )
    except runtime_errors as exc:
        output_path.unlink(missing_ok=True)
        return report_error(
            f"Encryption failed: {_format_msoffcrypto_error(exc)}",
            code=1,
            error_type=type(exc).__name__,
            details={"input": str(input_path), "output": str(output_path)},
            json_mode=json_mode,
        )
    except (OSError, ValueError) as exc:
        output_path.unlink(missing_ok=True)
        return report_error(
            f"Encryption failed: {_format_msoffcrypto_error(exc)}",
            code=1,
            error_type=type(exc).__name__,
            details={"input": str(input_path), "output": str(output_path)},
            json_mode=json_mode,
        )

    if not json_mode:
        size = output_path.stat().st_size
        print(f"Encrypted: {output_path} ({size} bytes)")
    return 0


def cmd_decrypt(
    input_path: Path,
    output_path: Path,
    password: str,
    json_mode: bool,
) -> int:
    if not input_path.exists():
        return report_error(
            f"Input not found: {input_path}",
            code=11,
            error_type="FileNotFound",
            details={"path": str(input_path)},
            json_mode=json_mode,
        )
    self_overwrite = _refuse_self_overwrite(input_path, output_path, json_mode)
    if self_overwrite is not None:
        return self_overwrite
    if not is_cfb_container(input_path):
        return report_error(
            f"{input_path}: not encrypted (no CFB signature). "
            "Nothing to decrypt; pass --check to confirm.",
            code=5,
            error_type="NotEncrypted",
            details={"path": str(input_path)},
            json_mode=json_mode,
        )

    msoffcrypto = _import_msoffcrypto(json_mode)
    runtime_errors = _msoffcrypto_runtime_errors(msoffcrypto)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return report_error(
            f"Cannot create output directory: {exc}",
            code=1,
            error_type="OSError",
            details={"path": str(output_path.parent)},
            json_mode=json_mode,
        )
    # InvalidKeyError can come from either load_key() (Agile/standard
    # encryption verifies eagerly) or decrypt() (some variants only
    # check during block decryption). Catch it at the outer scope so
    # both surfaces fold into the same exit-4 path. Always remove a
    # half-written output so a wrong password never leaves a 0-byte
    # decoy that callers might mistake for success.
    try:
        with input_path.open("rb") as f_in, output_path.open("wb") as f_out:
            of = msoffcrypto.OfficeFile(f_in)
            of.load_key(password=password)
            of.decrypt(f_out)
    except msoffcrypto.exceptions.InvalidKeyError:
        output_path.unlink(missing_ok=True)
        return report_error(
            f"Wrong password for {input_path}.",
            code=4,
            error_type="InvalidPassword",
            details={"path": str(input_path)},
            json_mode=json_mode,
        )
    except msoffcrypto.exceptions.FileFormatError as exc:
        output_path.unlink(missing_ok=True)
        return report_error(
            f"{input_path}: not a recognised encrypted Office file ({exc}). "
            "Legacy .doc/.xls/.ppt are CFB but not OOXML — convert them "
            "via `soffice --headless --convert-to docx INPUT` first.",
            code=1,
            error_type="FileFormatError",
            details={"path": str(input_path)},
            json_mode=json_mode,
        )
    except runtime_errors as exc:
        output_path.unlink(missing_ok=True)
        return report_error(
            f"Decryption failed: {_format_msoffcrypto_error(exc)}",
            code=1,
            error_type=type(exc).__name__,
            details={"input": str(input_path), "output": str(output_path)},
            json_mode=json_mode,
        )
    except (OSError, ValueError) as exc:
        output_path.unlink(missing_ok=True)
        return report_error(
            f"Decryption failed: {_format_msoffcrypto_error(exc)}",
            code=1,
            error_type=type(exc).__name__,
            details={"input": str(input_path), "output": str(output_path)},
            json_mode=json_mode,
        )

    if not json_mode:
        print(f"Decrypted: {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="office_passwd",
        description=(
            "Set or remove password protection on .docx/.xlsx/.pptx files "
            "via msoffcrypto-tool (MS-OFB Agile, Office 2010+)."
        ),
    )
    parser.add_argument("input", type=Path, help="Input .docx/.xlsx/.pptx")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Output path (required for --encrypt/--decrypt)",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--encrypt",
        metavar="PASSWORD",
        help="Encrypt INPUT into OUTPUT with PASSWORD. Pass '-' to read "
        "the password from stdin (avoids leaking via ps/shell history).",
    )
    mode.add_argument(
        "--decrypt",
        metavar="PASSWORD",
        help="Decrypt INPUT into OUTPUT using PASSWORD. Pass '-' to read "
        "from stdin.",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Detect whether INPUT is encrypted. Exit 0 if encrypted, "
        "10 if clean OOXML, 11 if missing.",
    )
    add_json_errors_argument(parser)

    args = parser.parse_args(argv)
    json_mode = args.json_errors

    if args.check:
        return cmd_check(args.input, json_mode)

    if args.output is None:
        parser.error("OUTPUT path is required for --encrypt/--decrypt")

    if args.encrypt is not None:
        password = _read_password(args.encrypt)
        return cmd_encrypt(args.input, args.output, password, json_mode)

    password = _read_password(args.decrypt)
    return cmd_decrypt(args.input, args.output, password, json_mode)


if __name__ == "__main__":
    sys.exit(main())

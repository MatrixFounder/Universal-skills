"""Pure utilities used by cli.py: validation, date, post-pack guard.

Migrated from `xlsx_add_comment.py` F-Helpers region (lines 251-328
of the post-002.7 shim) during Task 002, plus F6 fragments per
ARCH §8 Q3 (`_post_pack_validate`, `_post_validate_enabled`,
`_content_types_path`, `_TRUTHY_ENV`, and the `_subprocess` alias).

Public API (all `_`-prefixed; tests + cli.py call directly):
    _initials_from_author(name) -> str
    _resolve_date(arg) -> str (ISO-8601)
    _validate_args(args) -> None  (raises UsageError on MX/DEP violations)
    _assert_distinct_paths(input_path, output_path) -> None
    _content_types_path(tree_root_dir) -> Path
    _post_validate_enabled() -> bool  (env-var gate)
    _post_pack_validate(output_path) -> None  (raises OutputIntegrityFailure)
"""
from __future__ import annotations

import argparse
import os as _os
import re
import subprocess as _subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .exceptions import (
    OutputIntegrityFailure, SelfOverwriteRefused, UsageError,
)

__all__ = [
    "_initials_from_author", "_resolve_date",
    "_validate_args", "_assert_distinct_paths",
    "_content_types_path",
    "_post_validate_enabled", "_post_pack_validate",
]


def _initials_from_author(author: str) -> str:
    """Derive initials = first letter of each whitespace-separated token."""
    parts = re.findall(r"\S+", author)
    return ("".join(p[:1] for p in parts) or "R").upper()[:8]


def _resolve_date(date_arg: str | None) -> str:
    """Q5 closure: --date overrides, else UTC now ISO-8601 with Z suffix."""
    if date_arg:
        return date_arg
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_args(args: argparse.Namespace) -> None:
    """Enforce MX-A/MX-B + DEP-1, DEP-3 from TASK §2.5. Raises `UsageError`.

    DEP-2 (xlsx-7 envelope shape requires --default-author) is shape-
    dependent and runs inside `load_batch` (task 2.06) AFTER the JSON
    is parsed; this validator only enforces the shape-independent rules.

    DEP-4 (json-errors envelope on argparse usage errors) is already
    wired by `_errors.add_json_errors_argument` via the parser.error
    monkey-patch — this validator does not handle it.
    """
    # MX-A: --cell XOR --batch (exactly one required).
    cell_given = args.cell is not None
    batch_given = args.batch is not None
    if cell_given and batch_given:
        raise UsageError("--cell and --batch are mutually exclusive")
    if not cell_given and not batch_given:
        raise UsageError("one of --cell or --batch is required")

    # MX-B: --threaded XOR --no-threaded.
    if args.threaded and args.no_threaded:
        raise UsageError("--threaded and --no-threaded are mutually exclusive")

    # DEP-1: --cell requires --text and --author.
    if cell_given:
        missing = [f for f, v in (("--text", args.text), ("--author", args.author))
                   if v is None]
        if missing:
            raise UsageError(
                f"--cell requires {' and '.join(missing)} (DEP-1)"
            )

    # DEP-3: --default-threaded only makes sense in --batch mode.
    if args.default_threaded and cell_given:
        raise UsageError(
            "--default-threaded must not be combined with --cell (DEP-3)"
        )

    # DEP-2 partial: if --batch points at a real path, verify it exists
    # (the shape-dependent --default-author check runs in load_batch).
    if batch_given and args.batch != "-":
        if not Path(args.batch).is_file():
            raise UsageError(f"--batch file not found: {args.batch}")


def _assert_distinct_paths(input_path: Path, output_path: Path) -> None:
    """Cross-7 H1 SelfOverwriteRefused — resolves through symlinks.

    Both paths are run through `Path.resolve(strict=False)` so a
    symlink whose target is INPUT (or vice versa) is caught — protects
    against the pack-time-crash-corrupts-source failure mode. On
    resolve OSError (broken symlink chain), falls back to literal-path
    compare. Locks: T-same-path, T-same-path-symlink,
    T-encrypted-same-path, TestSamePathGuard.
    """
    try:
        in_resolved = input_path.resolve(strict=False)
        out_resolved = output_path.resolve(strict=False)
    except OSError:
        in_resolved = input_path
        out_resolved = output_path
    if in_resolved == out_resolved:
        raise SelfOverwriteRefused(str(in_resolved))


def _content_types_path(tree_root_dir: Path) -> Path:
    return tree_root_dir / "[Content_Types].xml"


_TRUTHY_ENV = {"1", "true", "yes", "on"}


def _post_validate_enabled() -> bool:
    """Truthy parser for `XLSX_ADD_COMMENT_POST_VALIDATE`.

    Sarcasmotron MIN-1 lock: bare `bool(env.get(...))` accepts `"0"` /
    `"false"` / `"no"` as TRUE, which is the opposite of user intent.
    Allowlist `1/true/yes/on` (case-insensitive); any other value is
    treated as disabled.
    """
    raw = _os.environ.get("XLSX_ADD_COMMENT_POST_VALIDATE", "")
    return raw.strip().lower() in _TRUTHY_ENV


def _post_pack_validate(output_path: Path) -> None:
    """R8 / 2.08 post-pack guard: invoke `office/validate.py` as a
    subprocess; raise `OutputIntegrityFailure` on real validation failure.

    Subprocess invocation is intentional for **process isolation**:
    `office/` is a byte-identical copy across docx/xlsx/pptx (CLAUDE.md
    §2), so we get clean module state, no shared lxml registries, and a
    stable boundary against future `office/validate` evolutions.

    Failure semantics (Sarcasmotron MAJ-1 lock):
      - exit 0          → ok, return.
      - exit 2 with
        "Unknown extension: .xlsm"
                        → no-op + stderr note. validate.py has no
                          macro-aware validator; .xlsm structural
                          validation is structurally beyond this guard's
                          scope. The vbaProject.bin sha256 invariant in
                          T-macro-xlsm-preserves covers macro round-trip.
      - non-zero        → `OutputIntegrityFailure` (exit 1) AND unlink
                          the corrupted output (Sarcasmotron MAJ-3 lock —
                          mirrors pack-failure cleanup pattern).
    """
    # `__file__` is `xlsx_comment/cli_helpers.py` — go up two to reach
    # the `skills/xlsx/scripts/` directory where `office/validate.py` lives.
    # NOTE: do NOT `.resolve()` here — preserves the pre-002.8 behaviour
    # of staying inside a symlinked package directory (Task 002 vdd-
    # adversarial finding #3).
    validate_script = Path(__file__).parent.parent / "office" / "validate.py"
    if not validate_script.is_file():
        # Sarcasmotron NIT-3 lock: don't launch subprocess against a
        # non-existent script — give a clearer failure mode.
        raise OutputIntegrityFailure(
            f"post-pack guard: office/validate.py missing at {validate_script}"
        )
    cmd = [sys.executable, str(validate_script), str(output_path)]
    try:
        result = _subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
    except _subprocess.TimeoutExpired as exc:
        # Task 002 vdd-adversarial finding #2: a 60s hang in office/
        # validate.py would otherwise escape main()'s _AppError handler
        # and surface as a raw traceback with exit 1. Convert to a
        # typed OutputIntegrityFailure so the JSON envelope path covers
        # this failure mode like every other guard outcome.
        try:
            output_path.unlink()
        except (OSError, FileNotFoundError):
            pass
        raise OutputIntegrityFailure(
            f"post-pack validate.py timed out after 60s on {output_path}"
        ) from exc
    if result.returncode == 0:
        return

    combined = (result.stdout.strip() + "\n" + result.stderr.strip()).strip()
    if (
        result.returncode == 2
        and "Unknown extension" in combined
        and output_path.suffix.lower() in {".xlsm"}
    ):
        # .xlsm: no validator available. Log + continue.
        print(
            f"Note: post-pack validate skipped for {output_path.name} "
            f"(.xlsm structural validation is not supported by office/validate.py; "
            f"macro round-trip is covered by the vbaProject.bin sha256 invariant)",
            file=sys.stderr,
        )
        return

    # Real validation failure — unlink the corrupted output before raising
    # so a downstream consumer cannot mistake a half-broken artefact for
    # a usable workbook (mirrors pack-failure cleanup pattern).
    try:
        output_path.unlink()
    except (OSError, FileNotFoundError):
        pass
    raise OutputIntegrityFailure(
        f"post-pack validate.py rejected {output_path}: {combined[:8192]}"
    )

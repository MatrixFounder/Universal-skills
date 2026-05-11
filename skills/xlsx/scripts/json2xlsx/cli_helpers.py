"""xlsx-2 cross-cutting helpers (F6 + F8).

This task (004.03) lands the synchronous helpers:
  - `assert_distinct_paths` (F8 — cross-7 H1 same-path guard).
  - `post_validate_enabled` (F6 — XLSX_JSON2XLSX_POST_VALIDATE env-var
    enable check; truthy allowlist matches xlsx-6 precedent at
    `xlsx_comment/cli_helpers.py:121-133`).
  - `read_stdin_utf8` (F1 helper used by `loaders.read_input` when
    input is the stdin sentinel `-`; bytes-level read avoids Windows
    newline translation breaking JSONL).

`run_post_validate` (F6 subprocess invocation) remains a STUB —
implemented in 004.08 once the writer/CLI pipeline can actually
produce a workbook to validate.

Honest scope §11.6 — TOCTOU on the same-path guard: a symlink
mutated between `resolve()` and `open(output, 'wb')` is OUT of
scope v1 (parity with xlsx-7 architect-review m6). The guard catches
static collisions and stable symlink chains.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .exceptions import SelfOverwriteRefused


# Mirrors xlsx-6 `_post_validate_enabled` truthy allowlist
# (`xlsx_comment/cli_helpers.py:121-133`). Anything outside the
# allowlist (including '0', '', 'false', 'no') reads as off.
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def post_validate_enabled() -> bool:
    """Return True iff XLSX_JSON2XLSX_POST_VALIDATE is set to one of
    the truthy-allowlist values ('1', 'true', 'yes', 'on';
    case-insensitive). Missing or any other value reads as off.
    """
    raw = os.environ.get("XLSX_JSON2XLSX_POST_VALIDATE", "").strip().lower()
    return raw in _TRUTHY


def assert_distinct_paths(input_path: str, output_path: Path) -> None:
    """Cross-7 H1 same-path guard.

    Raise `SelfOverwriteRefused` (exit 6) if input and output resolve
    to the same filesystem path. `Path.resolve(strict=False)` follows
    symlinks, so a typo like `json2xlsx.py same.xlsx same.xlsx` AND
    a symlink chain (`out_link -> in.json`) both trip the guard.

    Skipped when `input_path == "-"` (stdin has no resolvable path).

    Honest scope §11.6: A symlink mutated between this `resolve()`
    and the downstream `open(output, "wb")` is out of scope v1.
    """
    if input_path == "-":
        return
    try:
        in_resolved = Path(input_path).resolve(strict=False)
    except (OSError, RuntimeError):
        # Symlink loop or unreadable parent — let the downstream read
        # fail with the precise platform-IO reason. We can't compare
        # if we can't resolve.
        return
    try:
        out_resolved = output_path.resolve(strict=False)
    except (OSError, RuntimeError):
        return
    if in_resolved == out_resolved:
        raise SelfOverwriteRefused(
            input_path=str(in_resolved),
            output_path=str(out_resolved),
        )


def read_stdin_utf8() -> bytes:
    """Read the entire stdin as raw bytes.

    Bytes-level via `sys.stdin.buffer` avoids the platform-specific
    newline-translation layer that Python's text-mode stdin applies
    on Windows (which would silently mangle JSONL streams). Caller
    decodes as UTF-8.
    """
    return sys.stdin.buffer.read()


def run_post_validate(output: Path) -> tuple[bool, str]:
    """Invoke `office/validate.py` on `output` via subprocess.

    Returns `(passed, captured_output)`. Captured output is the
    concatenation of stdout + stderr decoded as UTF-8 (errors replaced).
    The caller truncates to ≤ 8192 bytes when embedding into the
    cross-5 envelope's `details.validator_output`.

    The entry point is `office/validate.py` (the cross-format
    dispatcher that picks the per-extension validator), NOT
    `office/validators/xlsx.py` directly — the latter is a library
    module that requires the `office` package context and can't run
    as a script. Mirrors xlsx-6 `_post_pack_validate` precedent.

    Hermeticity: env is constructed from scratch — only `PATH` (so
    `subprocess.run` can locate Python's helpers if needed) leaks in.
    `XLSX_JSON2XLSX_POST_VALIDATE` is explicitly NOT propagated so
    the validator can't recurse into another post-validate
    invocation. No `PYTHONPATH` either — `office/validate.py`'s top-
    of-file path setup (`sys.path.insert(0, parent)`) handles its
    own import resolution.

    Defensive: if the validator file is missing (skill broken),
    return `(False, "validator not found: ...")` rather than crashing.

    Timeout: 60 s. The validator should complete in milliseconds on
    typical workbooks; a longer wait indicates a validator bug.
    """
    pkg_dir = Path(__file__).resolve().parent       # …/scripts/json2xlsx
    scripts_dir = pkg_dir.parent                     # …/scripts
    validator = scripts_dir / "office" / "validate.py"

    if not validator.is_file():
        return False, f"validator not found: {validator}"

    try:
        proc = subprocess.run(
            [sys.executable, str(validator), str(output)],
            capture_output=True,
            timeout=60,
            env={"PATH": os.environ.get("PATH", "")},
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "validator timed out after 60s"

    captured = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    return proc.returncode == 0, captured

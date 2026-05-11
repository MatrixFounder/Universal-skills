"""xlsx-3 F10 — cross-cutting helpers.

Stage-2 (task-005-03): full bodies for `assert_distinct_paths`,
`post_validate_enabled`, `read_stdin_utf8`. `run_post_validate` stays
a stub until task-005-09 (where it gets the subprocess body).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .exceptions import PostValidateFailed, SelfOverwriteRefused


def assert_distinct_paths(input_path: str, output_path: Path) -> None:
    """Cross-7 H1 same-path guard. Resolves both paths via
    `Path.resolve(strict=False)` (follows symlinks) and raises
    `SelfOverwriteRefused` (code 6) on collision. Stdin sentinel
    `"-"` bypasses the guard (no on-disk input to compare).
    """
    if input_path == "-":
        return
    in_resolved = Path(input_path).resolve(strict=False)
    out_resolved = Path(output_path).resolve(strict=False)
    if in_resolved == out_resolved:
        raise SelfOverwriteRefused(
            f"Input and output resolve to the same path: {in_resolved}",
            code=6,
            error_type="SelfOverwriteRefused",
            details={
                "input": str(in_resolved),
                "output": str(out_resolved),
            },
        )


_POST_VALIDATE_TRUTHY = {"1", "true", "yes", "on"}


def post_validate_enabled() -> bool:
    """Truthy allowlist check on `XLSX_MD_TABLES_POST_VALIDATE` env.

    Truthy: `{"1", "true", "yes", "on"}` after `.strip().lower()`.
    Anything else (incl. unset / empty / "0" / "false" / "no" / "off")
    → False. Mirrors xlsx-2 + xlsx-6 precedent for consistency.
    """
    raw = os.environ.get("XLSX_MD_TABLES_POST_VALIDATE", "").strip().lower()
    return raw in _POST_VALIDATE_TRUTHY


def run_post_validate(output: Path) -> tuple[bool, str]:
    """Subprocess invocation of `office/validate.py` on `output`.

    On non-zero exit OR timeout: unlink `output` and raise
    `PostValidateFailed` (code 7). On success: return `(True, stdout)`.

    Mirrors xlsx-2 + xlsx-6 precedent: subprocess.run with
    `shell=False`, `timeout=60`, `capture_output=True`, `text=True`.
    """
    import subprocess
    office_validate = (
        Path(__file__).resolve().parent.parent / "office" / "validate.py"
    )
    if not office_validate.is_file():
        # Defensive — should never happen because skill ships office/.
        try:
            output.unlink()
        except OSError:
            pass
        raise PostValidateFailed(
            f"office/validate.py not found at {office_validate}",
            code=7,
            error_type="PostValidateFailed",
            details={"output": str(output), "reason": "validate_script_missing"},
        )
    try:
        # vdd-multi M7 review-fix: pass `--` separator BEFORE the
        # user-controlled output path so a path like `--help` cannot
        # be interpreted as a flag by office/validate.py's argparse.
        result = subprocess.run(
            [sys.executable, str(office_validate), "--", str(output)],
            shell=False, timeout=60, capture_output=True, text=True,
        )
    except subprocess.TimeoutExpired:
        try:
            output.unlink()
        except OSError:
            pass
        raise PostValidateFailed(
            f"Post-validate timeout (60s) on {output}",
            code=7,
            error_type="PostValidateFailed",
            details={"output": str(output), "reason": "timeout"},
        )
    if result.returncode != 0:
        snippet = ((result.stderr or "") + (result.stdout or ""))[:8192]
        try:
            output.unlink()
        except OSError:
            pass
        raise PostValidateFailed(
            f"Post-validate failed on {output}",
            code=7,
            error_type="PostValidateFailed",
            details={
                "output": str(output),
                "stderr": snippet,
                "returncode": result.returncode,
            },
        )
    return (True, result.stdout or "")


def read_stdin_utf8() -> str:
    """Single source of stdin decode (ARCH m5 lock).

    Reads `sys.stdin.buffer.read()` bytes-level then decodes UTF-8
    strict (raises `UnicodeDecodeError` on bad bytes; orchestrator
    maps to `InputEncodingError` envelope).
    """
    return sys.stdin.buffer.read().decode("utf-8")


# Re-export PostValidateFailed for callers that import via this
# module (mirrors xlsx-2 cli_helpers).
__all__ = [
    "assert_distinct_paths",
    "post_validate_enabled",
    "run_post_validate",
    "read_stdin_utf8",
    "PostValidateFailed",
]

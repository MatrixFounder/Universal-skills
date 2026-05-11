"""xlsx-3 typed error hierarchy.

Closed taxonomy: `_AppError` base + 8 typed subclasses. Each carries
the four fields `_errors.report_error` needs for the cross-5 envelope
(message, code, error_type, details). The orchestrator catches
`_AppError` once at the top of `cli._run` and routes through
`_errors.report_error` — xlsx-3 never builds the envelope dict by hand.

Platform-IO errors (FileNotFoundError, OSError) are deliberately NOT
in this taxonomy — they're surfaced via direct `report_error(
error_type="FileNotFound" | "IOError", ...)` calls at the CLI layer.

Type model: plain `Exception` subclass (mirrors xlsx-2 m1 lock) —
NOT `@dataclass(frozen=True)` (would require eq/frozen gymnastics to
coexist with `Exception.__init__`).

Stage-1 skeleton (task-005-01): class definitions exist so
`from md_tables2xlsx import NoTablesFound` succeeds. Class bodies
are minimal stubs — full message/code locks land in task-005-03.
"""
from __future__ import annotations

from typing import Any


class _AppError(Exception):
    """Closed taxonomy base for xlsx-3 user-facing errors.

    Carries the four fields `_errors.report_error` needs for the
    cross-5 envelope:
      - `message`: human-readable string (becomes envelope `error`).
      - `code`: integer exit code.
      - `error_type`: symbolic class name (becomes envelope `type`).
      - `details`: free-form dict (becomes envelope `details`).
    """

    def __init__(
        self,
        message: str,
        *,
        code: int,
        error_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.error_type = error_type
        self.details = dict(details) if details else {}


class EmptyInput(_AppError):
    """Input body is empty (zero non-whitespace bytes). Exit code 2."""


class NoTablesFound(_AppError):
    """Markdown document contains zero recognisable tables. Exit 2.

    Caller may pass `--allow-empty` to suppress and write a placeholder
    `Empty` sheet instead.
    """


class MalformedTable(_AppError):
    """Internal-use: a single pipe-table block failed structural
    validation (column-count mismatch between header and separator).
    Orchestrator typically maps to a stderr warning and continues with
    remaining tables; only raised at envelope level if EVERY table is
    malformed and `--allow-empty` is not set. Exit 2.
    """


class InputEncodingError(_AppError):
    """Source bytes are not valid UTF-8. Exit 2.

    `details` carries `{source, offset}` where `offset` is the byte
    position of the first decode failure.
    """


class InvalidSheetName(_AppError):
    """Sheet-name sanitisation/dedup exhausted retries (e.g., 99 dedup
    collisions for the same base name). Exit 2.

    `details` may carry `{original, retry_cap, first_collisions}` for
    diagnostics (ARCH Q3 lock).
    """


class SelfOverwriteRefused(_AppError):
    """Resolved input path matches resolved output path (cross-7 H1).
    Exit code 6. Follows symlinks via `Path.resolve()`.
    """


class PostValidateFailed(_AppError):
    """Post-validate hook (`XLSX_MD_TABLES_POST_VALIDATE=1`) reported a
    structurally-invalid output workbook. Exit code 7. Output file is
    unlinked before this is raised.
    """


class NoSubstantialRowsAfterParse(_AppError):
    """Every table parsed but each produced zero data rows after
    coercion (vanishingly rare; honest-scope edge). Exit 2.
    Treated as `NoTablesFound`-equivalent by the orchestrator.
    """

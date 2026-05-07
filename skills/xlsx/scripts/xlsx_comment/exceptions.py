"""Typed exceptions raised across the xlsx_comment package.

Migrated from `xlsx_add_comment.py` F-Errors region (lines 181-356)
during Task 002.

Hierarchy: `_AppError` (private base) -> 14 typed leaves (UsageError,
SheetNotFound, NoVisibleSheet, InvalidCellRef, MergedCellTarget,
EmptyCommentBody, InvalidBatchInput, BatchTooLarge,
MissingDefaultAuthor, DuplicateLegacyComment, DuplicateThreadedComment,
SelfOverwriteRefused, OutputIntegrityFailure, MalformedVml).

Each typed leaf carries class attributes `code` (exit code) and
`envelope_type` (JSON envelope `type` field). The unified handler
in `cli.main()` reads them and routes through `_errors.report_error`.

Exception classes that take envelope-detail args
(DuplicateLegacyComment, DuplicateThreadedComment, MergedCellTarget,
SheetNotFound, BatchTooLarge) preserve the constructor signatures
verbatim — they are tested directly via the shim re-export, so ANY
constructor change is a behaviour change forbidden by R8.a.
"""
__all__ = [
    "_AppError",  # exposed for cross-module isinstance + tests
    "UsageError", "SheetNotFound", "NoVisibleSheet", "InvalidCellRef",
    "MergedCellTarget", "EmptyCommentBody", "InvalidBatchInput",
    "BatchTooLarge", "MissingDefaultAuthor",
    "DuplicateLegacyComment", "DuplicateThreadedComment",
    "SelfOverwriteRefused", "OutputIntegrityFailure", "MalformedVml",
]

#
# Each typed error carries class attributes `code` (exit code) and
# `envelope_type` (the JSON envelope `type` field). The unified handler
# in `main()` reads them and routes through `_errors.report_error` —
# avoids one `except` clause per error class.
class _AppError(Exception):
    """Base for app-level typed errors that translate to JSON envelopes."""

    code: int = 1
    envelope_type: str = "InternalError"

    @property
    def details(self) -> dict:
        """Subclasses override to populate envelope `details` field."""
        return {}


class UsageError(_AppError):
    """MX-A/MX-B/DEP-1..4 violations and other CLI misuse."""

    code = 2
    envelope_type = "UsageError"


class SheetNotFound(_AppError):
    """Sheet name in --cell does not match any <sheet> in workbook.xml."""

    code = 2
    envelope_type = "SheetNotFound"

    def __init__(self, name: str, available: list[str], suggestion: str | None = None):
        self.name = name
        self.available = available
        self.suggestion = suggestion
        super().__init__(name)

    @property
    def details(self) -> dict:
        d = {"name": self.name, "available": list(self.available)}
        if self.suggestion is not None:
            d["suggestion"] = self.suggestion
        return d


class NoVisibleSheet(_AppError):
    """All sheets are state=hidden or veryHidden; no default available."""

    code = 2
    envelope_type = "NoVisibleSheet"


class InvalidCellRef(_AppError):
    """Cell reference does not match A1 syntax."""

    code = 2
    envelope_type = "InvalidCellRef"


class MergedCellTarget(_AppError):
    """Target cell is a non-anchor of a merged range; --allow-merged-target absent."""

    code = 2
    envelope_type = "MergedCellTarget"

    def __init__(self, target: str, anchor: str, range_ref: str):
        self.target = target
        self.anchor = anchor
        self.range_ref = range_ref
        super().__init__(f"{target} is non-anchor of merged {range_ref}")

    @property
    def details(self) -> dict:
        return {"target": self.target, "anchor": self.anchor, "range": self.range_ref}


class EmptyCommentBody(_AppError):
    """--text is empty or whitespace-only (Q2 closure)."""

    code = 2
    envelope_type = "EmptyCommentBody"


class InvalidBatchInput(_AppError):
    """--batch JSON neither flat-array nor xlsx-7 envelope shape."""

    code = 2
    envelope_type = "InvalidBatchInput"


class BatchTooLarge(_AppError):
    """--batch input exceeds the 8 MiB pre-parse cap."""

    code = 2
    envelope_type = "BatchTooLarge"

    def __init__(self, size_bytes: int):
        self.size_bytes = size_bytes
        super().__init__(f"batch exceeds 8 MiB cap: {size_bytes} bytes")

    @property
    def details(self) -> dict:
        return {"size_bytes": self.size_bytes, "cap_bytes": 8 * 1024 * 1024}


class MissingDefaultAuthor(_AppError):
    """xlsx-7 envelope shape requires --default-author."""

    code = 2
    envelope_type = "MissingDefaultAuthor"


class DuplicateLegacyComment(_AppError):
    """--no-threaded against a cell that already has a legacy <comment>."""

    code = 2
    envelope_type = "DuplicateLegacyComment"

    def __init__(self, message: str, sheet: str, cell: str):
        self.sheet = sheet
        self.cell = cell
        super().__init__(message)

    @property
    def details(self) -> dict:
        return {"sheet": self.sheet, "cell": self.cell}


class DuplicateThreadedComment(_AppError):
    """--no-threaded against a cell with an existing threaded thread (M-2)."""

    code = 2
    envelope_type = "DuplicateThreadedComment"

    def __init__(
        self, message: str, sheet: str, cell: str, existing_thread_size: int,
    ):
        self.sheet = sheet
        self.cell = cell
        self.existing_thread_size = existing_thread_size
        super().__init__(message)

    @property
    def details(self) -> dict:
        return {
            "sheet": self.sheet,
            "cell": self.cell,
            "existing_thread_size": self.existing_thread_size,
        }


class SelfOverwriteRefused(_AppError):
    """INPUT and OUTPUT resolve to the same path (cross-7 H1)."""

    code = 6
    envelope_type = "SelfOverwriteRefused"


class OutputIntegrityFailure(_AppError):
    """Post-pack office.validate.py rejected the produced workbook (2.08 guard)."""

    code = 1
    envelope_type = "OutputIntegrityFailure"


class MalformedVml(_AppError):
    """VML drawing has unparseable XML or a non-integer in `<o:idmap data>`.

    Defensive: Excel-emitted VML always has well-formed integers; this
    error fires only on tampered / corrupted workbooks. Treated as exit
    1 (I/O / malformed input) rather than exit 2 (user CLI error).
    """

    code = 1
    envelope_type = "MalformedVml"

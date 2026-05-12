"""Application error taxonomy for docx_replace.py.

Extracted at task-006-07a per ARCH §3.2 Q-A1 guardrail to avoid
circular imports between docx_replace.py and _actions.py.

Both docx_replace.py and _actions.py import from this module.
"""
from __future__ import annotations


class _AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: int,
        error_type: str,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.error_type = error_type
        self.details = details or {}


class AnchorNotFound(_AppError):
    pass


class SelfOverwriteRefused(_AppError):
    pass


class InsertSourceTooLarge(_AppError):
    pass


class EmptyInsertSource(_AppError):
    pass


class Md2DocxFailed(_AppError):
    pass


class Md2DocxOutputInvalid(_AppError):
    pass


class Md2DocxNotAvailable(_AppError):
    pass


class LastParagraphCannotBeDeleted(_AppError):
    pass


class NotADocxTree(_AppError):
    pass


class PostValidateFailed(_AppError):
    pass

"""Application error hierarchy for the html2md skill (stdlib-only).

Each subclass carries a class-level ``CODE`` (the process exit status) and an
``error_type`` string surfaced in the ``_errors`` JSON envelope. The exit-code map
(ARCH §5.1) is the single source of truth:

    0  ok
    1  BadInput / ConvertFailed / InternalError (generic failure)
    2  usage (argparse)
    3  EngineNotInstalled (Chrome requested, Playwright absent)
    6  SelfOverwriteRefused (OUTPUT collides with INPUT, incl. symlink)
    10 FetchFailed (URL unreachable / blocked / over cap)
"""
from __future__ import annotations

from typing import Any


class _AppError(Exception):
    """Base for all html2md domain errors. ``main`` maps ``CODE``/``error_type``."""

    CODE: int = 1
    error_type: str = "InternalError"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}


class BadInput(_AppError):
    CODE = 1
    error_type = "BadInput"


class ConvertFailed(_AppError):
    CODE = 1
    error_type = "ConvertFailed"


class InternalError(_AppError):
    CODE = 1
    error_type = "InternalError"


class EngineNotInstalled(_AppError):
    CODE = 3
    error_type = "EngineNotInstalled"


class SelfOverwriteRefused(_AppError):
    CODE = 6
    error_type = "SelfOverwriteRefused"


class FetchFailed(_AppError):
    CODE = 10
    error_type = "FetchFailed"

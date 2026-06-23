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
    11 EmptyExtraction (substantial source HTML → near-empty Markdown body)
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


class Usage(_AppError):
    """A post-parse usage error (semantic, not an argparse syntax error) — exit 2.

    Used for validations argparse cannot express: ``--search`` ⊥ a URL positional,
    ``--engine remote`` with no provider configured, ``--max-results`` ≤ 0. Flows
    through ``main``'s ``_AppError`` handler exactly like every other domain error,
    so it returns CODE 2 (matching the argparse usage convention)."""

    CODE = 2
    error_type = "Usage"


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


class EmptyExtraction(_AppError):
    """A substantial source page converted to a near-empty Markdown body (silent content
    loss). Surfaced as a typed exit 11 — NEVER exit 0 — so a caller can retry with another
    engine / a site-specific endpoint instead of importing an empty note (feedback R-7)."""

    CODE = 11
    error_type = "EmptyExtraction"

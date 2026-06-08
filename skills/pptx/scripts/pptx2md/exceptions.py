"""Shim-level exception catalogue for the pptx → Markdown converter (TASK 020).

Every domain failure derives from :class:`_AppError` and carries a class
attribute :attr:`CODE` (process exit code). :func:`_errors.report_error`
(4-skill replicated ``skills/<skill>/scripts/_errors.py``) consumes ``CODE``
when emitting the ``--json-errors`` envelope or the human-readable stderr line.

Catalogue (CODE in parentheses) — see ``docs/ARCHITECTURE.md §5.1`` exit map:

* ``SelfOverwriteRefused`` (6) — OUTPUT (or a media path) resolves to INPUT.
* ``OcrEngineUnavailable`` (1) — ``--ocr`` but ``tesseract`` not on PATH.
* ``LanguagePackMissing``  (1) — ``--ocr`` but a requested language is absent.
* ``BadInput``             (1) — INPUT missing / not a usable .pptx (non-CFB).
* ``InternalError``        (1) — terminal catch-all; message redacted (no path leak).

``EncryptedFileError`` (exit 3) is **not** defined here — it is imported from
``office._encryption`` and mapped to code 3 in ``cli.main`` (D-6 / MAJOR-1: one
type for encrypted *and* legacy ``.ppt``, parity with ``pptx_to_pdf.py``).
"""
from __future__ import annotations


class _AppError(RuntimeError):
    """Base for all shim-level errors. Sub-classes set ``CODE``.

    The exit code is read by :func:`_errors.report_error` via the ``code=``
    argument the caller passes; sub-classes pin a class-level ``CODE`` so
    callers can write ``code=exc.CODE`` uniformly. ``error_type`` defaults to
    the class name (used as the envelope ``type``); ``details`` is optional
    free-form context folded into the envelope.
    """

    CODE: int = 1

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.error_type = type(self).__name__
        self.details = details or {}


class SelfOverwriteRefused(_AppError):
    """OUTPUT (or an extracted media path) resolves to the INPUT file."""

    CODE = 6


class OcrEngineUnavailable(_AppError):
    """``--ocr`` requested but the ``tesseract`` binary is not on PATH."""

    CODE = 1


class LanguagePackMissing(_AppError):
    """``--ocr`` requested but a requested language pack is not installed."""

    CODE = 1


class BadInput(_AppError):
    """INPUT does not exist, or is not a usable (non-encrypted) ``.pptx``."""

    CODE = 1


class InternalError(_AppError):
    """Terminal catch-all. Raw message is redacted to prevent path leaks."""

    CODE = 1

"""Shim-level exception catalogue for xlsx-9 read-back CLI.

Every exception derives from :class:`_AppError` and carries a class
attribute :attr:`CODE` (process exit code). The
:func:`_errors.report_error` helper (4-skill replicated under
``skills/<skill>/scripts/_errors.py``) consumes ``CODE`` when emitting
the cross-5 ``--json-errors`` envelope or the human-readable stderr
line.

Catalogue (CODE in parentheses) — see ``docs/ARCHITECTURE.md §2.1
F8`` and ``docs/TASK.md §1.4 / §2 Epic E1``:

* ``SelfOverwriteRefused`` (6) — cross-7 H1 same-path guard.
* ``GfmMergesRequirePolicy`` (2) — D14: ``--format gfm`` + body merges
  + default ``--gfm-merge-policy fail``.
* ``IncludeFormulasRequiresHTML`` (2) — M7 lock: ``--format gfm``
  + ``--include-formulas`` is incompatible.
* ``PostValidateFailed`` (7) — env-flag post-validate gate (parity with
  xlsx-8 ``PostValidateFailed``).
* ``InconsistentHeaderDepth`` (2) — D-A11 defensive: multi-row header
  reconstruction found non-uniform `` › `` separator counts.
* ``HeaderRowsConflict`` (2) — R14h: ``--header-rows N`` (int) combined
  with multi-table mode (``--tables != whole``).
* ``InternalError`` (7) — terminal catch-all; raw message redacted to
  prevent path leaks (R23f, inherited from xlsx-8 §14.4 H3 fix).
"""
from __future__ import annotations


class _AppError(RuntimeError):
    """Base for all shim-level errors. Sub-classes set ``CODE``.

    The exit code is read by :func:`_errors.report_error` via the
    ``code=`` argument the caller passes. Sub-classes pin a class-
    level ``CODE`` so callers can write ``code=exc.CODE`` uniformly.
    """

    CODE: int = 1


class SelfOverwriteRefused(_AppError):
    """Output path resolves to the input file (cross-7 H1)."""

    CODE = 6  # Cross-7 H1: INPUT and OUTPUT resolve to same path.


class GfmMergesRequirePolicy(_AppError):
    """``--format gfm`` + body merges require an explicit merge policy.

    D14 rename of backlog ``MergedCellsRequireHTML``. Policy must be
    ``duplicate`` or ``blank`` to permit lossy GFM; ``fail`` (default)
    raises this exception before any output is written.
    """

    CODE = 2  # D14: --format gfm + merges + default policy.


class IncludeFormulasRequiresHTML(_AppError):
    """``--format gfm`` + ``--include-formulas`` is not supported.

    M7 lock: formula annotations require HTML ``data-formula``
    attributes which are not representable in GFM pipe-tables.
    Use ``--format html`` or ``--format hybrid`` (which promotes
    formula-containing tables to HTML automatically).
    """

    CODE = 2  # M7 lock: --format gfm + --include-formulas.


class PostValidateFailed(_AppError):
    """Env-flag post-validate gate found a corrupted output.

    Parity with xlsx-8 ``PostValidateFailed`` — the XLSX_XLSX2MD_POST_VALIDATE
    environment flag triggers a re-parse of the produced Markdown; if
    the re-parse fails, this exception is raised and the output file
    is unlinked before the exception propagates.
    """

    CODE = 7  # Env-flag post-validate gate (parity with xlsx-8 PostValidate).


class InconsistentHeaderDepth(_AppError):
    """Multi-row header reconstruction found non-uniform separator depth.

    D-A11 defensive check: :func:`headers.validate_header_depth_uniformity`
    counts `` › `` separators per header cell; if the counts differ
    across columns, the `` › ``-split reconstruction is ambiguous.
    ``xlsx_read`` should enforce uniformity upstream; this is a
    second safety layer.
    """

    CODE = 2  # D-A11 defensive: multi-row reconstruction non-uniform.


class HeaderRowsConflict(_AppError):
    """``--header-rows N`` (int) is incompatible with multi-table mode.

    R14h: per-table header counts may differ on a multi-table sheet.
    Use ``--header-rows auto`` or ``--no-split`` to resolve.
    """

    CODE = 2  # R14h: --header-rows N (int) + --tables != whole.


class InternalError(_AppError):
    """Terminal catch-all for any unhandled exception reaching ``main()``.

    R23f: raw exception message is redacted to prevent path leaks from
    openpyxl / ``xlsx_read`` internals; emitted via ``_errors.report_error``
    as ``{"v":1,"error":"Internal error: <ClassName>","code":7,...}``.
    """

    CODE = 7  # R23f: terminal catch-all; raw message redacted.


__all__ = [
    "_AppError",
    "SelfOverwriteRefused",
    "GfmMergesRequirePolicy",
    "IncludeFormulasRequiresHTML",
    "PostValidateFailed",
    "InconsistentHeaderDepth",
    "HeaderRowsConflict",
    "InternalError",
]

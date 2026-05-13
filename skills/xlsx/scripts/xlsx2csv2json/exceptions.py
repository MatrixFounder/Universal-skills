"""Shim-level exception catalogue for xlsx-8 read-back CLIs.

Every exception derives from :class:`_AppError` and carries a class
attribute :pyattr:`CODE` (process exit code). The
:func:`_errors.report_error` helper (4-skill replicated under
``skills/<skill>/scripts/_errors.py``) consumes ``CODE`` when emitting
the cross-5 ``--json-errors`` envelope or the human-readable stderr
line.

Catalogue (CODE in parentheses) — see ``docs/ARCHITECTURE.md §2.1
F6`` and ``docs/TASK.md §R12 / §R14–§R17``:

* ``SelfOverwriteRefused`` (6) — cross-7 H1 same-path guard.
* ``MultiTableRequiresOutputDir`` (2) — TASK §R12.d (multi-region
  CSV needs ``--output-dir``).
* ``MultiSheetRequiresOutputDir`` (2) — TASK §R12.f (``--sheet all``
  CSV cannot multiplex into a single stream).
* ``HeaderRowsConflict`` (2) — TASK §R7.e (``--header-rows N`` int
  conflicts with multi-table layouts).
* ``InvalidSheetNameForFsPath`` (2) — sheet / table name carries a
  character forbidden in a filesystem path component.
* ``OutputPathTraversal`` (2) — D-A8 path-traversal defence-in-depth.
* ``FormatLockedByShim`` (2) — user supplied ``--format`` to a shim
  that hard-binds the format.
* ``PostValidateFailed`` (7) — env-flag opt-in JSON round-trip
  validator detected a corrupted output.
* ``CollisionSuffixExhausted`` (2) — xlsx-8a-01 Sec-HIGH-3
  mitigation: per-region filename collision-suffix loop in
  ``_emit_multi_region`` attempted more than ``_MAX_COLLISION_SUFFIX``
  variants without finding a unique path.
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

    CODE = 6


class MultiTableRequiresOutputDir(_AppError):
    """CSV emit with ``--tables != whole`` AND >1 region needs ``--output-dir``."""

    CODE = 2


class MultiSheetRequiresOutputDir(_AppError):
    """CSV emit with ``--sheet all`` AND >1 visible sheet needs ``--output-dir``."""

    CODE = 2


class HeaderRowsConflict(_AppError):
    """``--header-rows N`` (int) is incompatible with ``--tables != whole``.

    Per-table header counts may differ on a multi-table sheet
    (revenue 1-row vs KPI 2-row vs notes 0-row). The library
    ``xlsx_read`` exposes per-table auto-detection through
    ``header_rows="auto"``; the shim raises this exception to force
    callers to opt in.
    """

    CODE = 2


class InvalidSheetNameForFsPath(_AppError):
    """Sheet or table name contains a character forbidden in path components.

    Reject list (cross-platform): ``/``, ``\\``, ``..``, NUL,
    ``:``, ``*``, ``?``, ``<``, ``>``, ``|``, ``"``, plus the names
    ``"."`` and ``""``. See ``docs/TASK.md §4.2``.
    """

    CODE = 2


class OutputPathTraversal(_AppError):
    """Computed write path escapes ``--output-dir`` after canonical resolve.

    Defence-in-depth: even if a sheet / table name passes
    :class:`InvalidSheetNameForFsPath` validation, the final
    ``<output-dir>/<sheet>/<table>.csv`` is re-checked via
    :meth:`pathlib.Path.is_relative_to` before opening for write.
    """

    CODE = 2


class FormatLockedByShim(_AppError):
    """User passed ``--format <other>`` to a shim that hard-binds the format.

    ``xlsx2csv.py`` binds ``--format csv``; ``xlsx2json.py`` binds
    ``--format json``. Mismatching values are a category error rather
    than a recoverable arg.
    """

    CODE = 2


class PostValidateFailed(_AppError):
    """``XLSX_XLSX2CSV2JSON_POST_VALIDATE=1`` triggered and re-parse failed.

    JSON path: ``json.loads(output_path.read_text())`` raised. The
    output file is unlinked before this exception escapes so the
    caller sees a clean stage.
    """

    CODE = 7


class CollisionSuffixExhausted(_AppError):
    """Per-region filename collision-suffix loop exceeded the cap.

    xlsx-8a-01 (Sec-HIGH-3 DoS mitigation): the
    ``_emit_multi_region`` collision-suffix loop in
    :mod:`xlsx2csv2json.emit_csv` is bounded at
    ``_MAX_COLLISION_SUFFIX`` (= 1000) attempts. A crafted
    workbook with thousands of regions sharing the same
    ``(sheet, region_name)`` tuple would otherwise force an
    unbounded O(N²) ``Path.resolve()`` + ``is_relative_to`` loop
    before the natural wall-clock timeout. The cap fails loud via
    this exception, routed through the cross-5 envelope as exit 2.

    Policy-locked at 1000 per TASK §7.3 D1 / ARCH §15.3 D-A14
    (cap fires on the (cap+1)-th iteration).
    """

    CODE = 2


__all__ = [
    "_AppError",
    "SelfOverwriteRefused",
    "MultiTableRequiresOutputDir",
    "MultiSheetRequiresOutputDir",
    "HeaderRowsConflict",
    "InvalidSheetNameForFsPath",
    "OutputPathTraversal",
    "FormatLockedByShim",
    "PostValidateFailed",
    "CollisionSuffixExhausted",
]

"""xlsx-8: read-back CLI body — emit ``.xlsx`` as CSV or JSON.

Thin emit-side glue on top of the xlsx-10.A :mod:`xlsx_read` foundation.
Two shims (``xlsx2csv.py`` / ``xlsx2json.py``, ~53 LOC each) hard-bind
the output format and delegate every reader concern (merge resolution,
ListObjects, gap-detect, multi-row headers, hyperlinks, stale-cache,
encryption / macro probes) to the foundation library.

Honest scope (v1) — see :file:`docs/TASK.md §1.4` for the rationale
of each item:

* **(a)** Cached value only. ``--include-formulas`` opts in to formula
  strings, but the workbook is opened with ``keep_formulas=True``
  which makes cached values inaccessible (xlsx-10.A §13.1).
* **(b)** Rich-text spans → plain-text concat (delegated to
  :func:`xlsx_read._values.extract_cell`).
* **(c)** Cell styles dropped (color / font / fill / border /
  alignment / conditional formatting).
* **(d)** Comments dropped. v2 may add a sidecar
  ``<output>.comments.json`` à la docx-4.
* **(e)** Charts / images / shapes / pivot-source / data-validation
  dropped.
* **(f)** ListObject ``headerRowCount`` ≠ 1 falls back to gap-detect
  for header determination (delegated to ``xlsx_read``).
* **(g)** Workbook-scope named ranges ignored; only sheet-scope feeds
  Tier-2 of ``detect_tables``.
* **(h)** Shared / array formulas → cached value only.
* **(i)** ``AmbiguousHeaderBoundary`` is a warning, never raised.
  Surfaced via Python's default :func:`warnings.showwarning` hook.
* **(j)** ``--write-listobjects`` round-trip dependency on xlsx-2 v2;
  shapes 3 + 4 are lossy on xlsx-2 v1 consume.
* **(k)** No ``eval`` / no shell / no subprocess / no network.
* **(l)** ``--tables listobjects`` silently bundles Tier-2 sheet-scope
  named ranges (the library's ``tables-only`` mode returns both Tier-1
  and Tier-2); ``--tables gap`` is implemented as library ``auto`` +
  post-filter ``r.source == "gap_detect"``.
* **(m)** ``--include-hyperlinks`` forces ``read_only_mode=False`` at
  workbook open. The library auto-picks ``read_only=True`` for files
  > 10 MiB to stream cells, but openpyxl's ``ReadOnlyCell`` does NOT
  expose ``cell.hyperlink`` (the data lives in
  ``xl/worksheets/_rels/sheetN.xml.rels``). To make the flag actually
  work, the shim forces ``read_only=False``. Trade-off: memory cost
  for large workbooks. Caller-controlled — opt-in via the flag.
* **(n)** ``--datetime-format raw`` (JSON only): the library returns
  native ``datetime`` objects, which the stdlib ``json`` module cannot
  encode. The shim coerces via ``.isoformat()`` (same ISO-8601 string
  form as ``--datetime-format ISO`` for the date portion). Net effect:
  ``raw`` and ``ISO`` produce **identical** JSON output today. The
  flag distinction is meaningful for downstream Python callers using
  the library directly, NOT for CLI JSON output. Documented here so
  downstream tooling doesn't assume native ``datetime`` survives the
  serialisation boundary.
* **(o)** Multi-region CSV with same-name regions: the shim appends a
  ``__2`` / ``__3`` / ... suffix to the file name to prevent silent
  overwrites. Region names with the literal ``__`` substring are
  unaffected — only the file-name-collision path uses the suffix.
* **(p)** Internal errors not in the documented dispatch table
  (``PermissionError``, ``OSError``, generic ``RuntimeError``, etc.)
  surface as ``Internal error: <ClassName>`` envelopes with empty
  ``details`` to prevent path leaks. For local debugging, run without
  ``--json-errors`` to see the Python traceback.

Path-component reject list (when CSV multi-region mode in effect):
``/``, ``\\``, ``..``, NUL, ``:``, ``*``, ``?``, ``<``, ``>``, ``|``,
``"``, plus the names ``"."`` and ``""``.

``--tables`` enum mapping (ARCH D-A2):

================  ===============  ===============================
shim ``--tables`` library mode     post-filter
================  ===============  ===============================
``whole``         ``whole``        none
``listobjects``   ``tables-only``  none (Tier-2 named ranges bundled)
``gap``           ``auto``         ``r.source == "gap_detect"``
``auto``          ``auto``         none
================  ===============  ===============================

This package is the **first consumer** of the xlsx-10.A
:mod:`xlsx_read` closed-API contract (ARCH D-A5). Imports come
exclusively from ``xlsx_read.<public>``; the ruff ``banned-api`` rule
in ``scripts/pyproject.toml`` blocks any ``xlsx_read._*`` import.
"""
from __future__ import annotations

from .cli import main
from .exceptions import (
    _AppError,
    SelfOverwriteRefused,
    MultiTableRequiresOutputDir,
    MultiSheetRequiresOutputDir,
    HeaderRowsConflict,
    InvalidSheetNameForFsPath,
    OutputPathTraversal,
    FormatLockedByShim,
    PostValidateFailed,
)


# ---------------------------------------------------------------------------
# Public helpers — Python-caller facing surface.
#
# `convert_xlsx_to_csv` and `convert_xlsx_to_json` are thin kwarg → argv
# marshallers that delegate to :func:`cli.main` with the matching
# ``format_lock``. Same semantics as invoking the shims from the
# shell, but Python-callable for embedding / unit tests.
# ---------------------------------------------------------------------------

# Mapping from public-helper kwargs to CLI long flags. Kept in one
# place (here, in `__init__.py`) so CLI semantics remain the single
# source of truth — the helper merely marshals.
_KWARG_TO_FLAG = {
    "output_dir": "--output-dir",
    "sheet": "--sheet",
    "header_rows": "--header-rows",
    "header_flatten_style": "--header-flatten-style",
    "merge_policy": "--merge-policy",
    "tables": "--tables",
    "gap_rows": "--gap-rows",
    "gap_cols": "--gap-cols",
    "datetime_format": "--datetime-format",
    # **vdd-adversarial R26 HIGH-3 fix:** R26 added `--delimiter` to
    # the CLI but the public Python helper raised `TypeError: Unknown
    # kwarg: 'delimiter'` because this mapping was not updated.
    "delimiter": "--delimiter",
    "encoding": "--encoding",
}
_BOOL_KWARG_TO_FLAG = {
    "include_hidden": "--include-hidden",
    "include_hyperlinks": "--include-hyperlinks",
    "include_formulas": "--include-formulas",
    "json_errors": "--json-errors",
    "drop_empty_rows": "--drop-empty-rows",
}


def _build_argv(input_path, output_path, kwargs):
    """Map kwargs to CLI argv. Used by public helpers.

    Raises:
        TypeError: an unknown kwarg slipped through (intentional
            strict-mode: prevents silent typos at the Python-caller
            boundary).
    """
    argv = [str(input_path)]
    if output_path is not None:
        argv += ["--output", str(output_path)]
    for k, v in kwargs.items():
        if k in _KWARG_TO_FLAG:
            argv += [_KWARG_TO_FLAG[k], str(v)]
        elif k in _BOOL_KWARG_TO_FLAG:
            if v:
                argv.append(_BOOL_KWARG_TO_FLAG[k])
        else:
            raise TypeError(f"Unknown kwarg: {k!r}")
    return argv


def convert_xlsx_to_csv(input_path, output_path=None, **kwargs):
    """Public helper — convert ``.xlsx`` to CSV. See ``docs/TASK.md §5.2``.

    Equivalent to ``python3 xlsx2csv.py INPUT [OUTPUT] [--flag value ...]``.
    Returns the process-style exit code (0 on success, non-zero on
    documented failure modes).
    """
    argv = _build_argv(input_path, output_path, kwargs)
    return main(argv, format_lock="csv")


def convert_xlsx_to_json(input_path, output_path=None, **kwargs):
    """Public helper — convert ``.xlsx`` to JSON. See ``docs/TASK.md §5.2``.

    Equivalent to ``python3 xlsx2json.py INPUT [OUTPUT] [--flag value ...]``.
    """
    argv = _build_argv(input_path, output_path, kwargs)
    return main(argv, format_lock="json")


__all__ = [
    "main",
    "convert_xlsx_to_csv",
    "convert_xlsx_to_json",
    "_AppError",
    "SelfOverwriteRefused",
    "MultiTableRequiresOutputDir",
    "MultiSheetRequiresOutputDir",
    "HeaderRowsConflict",
    "InvalidSheetNameForFsPath",
    "OutputPathTraversal",
    "FormatLockedByShim",
    "PostValidateFailed",
]

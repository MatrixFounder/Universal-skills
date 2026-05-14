"""xlsx-9: read-back CLI body — emit ``.xlsx`` as Markdown.

Thin emit-side glue on top of the xlsx-10.A :mod:`xlsx_read` foundation.
One shim (``xlsx2md.py``, ≤ 60 LOC) delegates every reader concern
(merge resolution, ListObjects, gap-detect, multi-row headers,
hyperlinks, stale-cache, encryption / macro probes) to the foundation
library; this package owns only emit-side concerns.

Honest scope (v1) — TASK §1.4 full catalogue. Items deliberately deferred:

* **(a)** Rich-text spans (bold/italic runs inside a single cell) →
  plain-text concat. Delegated to ``xlsx_read._values.extract_cell``.
  No bold/italic markup emitted in v1.

* **(b)** Cell styles (color / font / fill / border / alignment /
  conditional formatting) → dropped without warning. Markdown has no
  cell-style representation.

* **(c)** Comments → dropped. Deferred to v2 sidecar pattern à la
  docx-4 (``xlsx2md.comments.json``).

* **(d)** Charts / images / shapes → dropped. ``preview.py`` remains
  the canonical visual path.

* **(e)** Pivot tables → unfold to static cached values (requires
  ``xlsx_recalc.py`` upstream for fresh values).

* **(f)** Data validation dropdowns → dropped without warning.

* **(g)** Formulas without cached value → warning + empty cell; OR
  formula string emitted in ``data-formula`` HTML attribute when
  ``--include-formulas`` is active.

* **(h)** Shared / array formulas → cached value only.

* **(i)** ListObjects ``headerRowCount=0`` handling — delegated to
  ``xlsx_read.tables`` (R2-M3 / single source of truth, NOT duplicated
  here). ``headerRowCount=0`` → synthetic ``col_1..col_N`` headers
  emitted by the library. GFM: emit synthetic visible header row;
  HTML: synthetic ``<thead>`` with ``col_1..col_N`` ``<th>`` cells
  (D13 lock); Hybrid: auto-promote to HTML; all modes: warning in
  ``summary.warnings``.

* **(j)** Diagonal borders / sparklines / camera objects → dropped
  without warning (not renderable in markdown).

* **(k)** ``--header-rows smart`` vs ``--header-rows auto`` behaviour.
  ``smart`` shifts past metadata banners and emits a flat leaf-key
  header; ``auto`` keeps merge-derived multi-level form (`` › ``-
  flattened in GFM, ``<thead>`` with multiple ``<tr>`` in HTML).
  Intentional — ``smart`` for "skip the metadata I don't want",
  ``auto`` for "preserve the multi-level header band". Inherited
  honest-scope from xlsx-8a-09 / TASK 011 R11.

* **(l)** Hyperlink scheme allowlist defaults to ``{http, https, mailto}``.
  Schemes outside the allowlist emit text-only with a warning (NOT a
  fail). To allow all schemes (NOT recommended), pass
  ``--hyperlink-scheme-allowlist '*'``. To strip all hyperlinks, pass
  ``--hyperlink-scheme-allowlist ""``. Parity with xlsx-8a-03 / Sec-MED-2.

* **(m)** Hyperlinks are always extracted (D5 lock — no
  ``--include-hyperlinks`` opt-out flag). Always opens workbook in
  ``read_only_mode=False`` (or the ``--memory-mode`` override) because
  openpyxl ``ReadOnlyCell`` does not expose ``cell.hyperlink``. Memory
  cost: ~5-10× the workbook file size on disk (75-150 MB Python heap on
  15 MB workbooks; ~0.5-1 GB on 100 MB workbooks). Inherited honest-scope
  from xlsx-8 §14.1 C1 fix. **Workaround for memory-constrained CI**:
  pass ``--memory-mode=streaming`` (hyperlinks become unreliable per (l);
  explicit trade-off).

* **(R3-H1 lock)** ``--sanitize-sheet-names`` option dropped entirely.
  xlsx-3's ``naming.py`` sanitisation (e.g., ``History`` → ``History_``,
  >31 UTF-16 chars truncated) is xlsx-3's write-side contract. xlsx-9
  reads sheet names verbatim and emits them verbatim in ``## H2``
  headings. The asymmetry (``History`` → ``## History`` in xlsx-9,
  ``## History_`` after xlsx-3 round-trip) is expected, documented in
  ``xlsx-md-shapes.md``, and NOT a regression.

This package is the **second consumer** of the xlsx-10.A
:mod:`xlsx_read` closed-API contract (ARCH D-A5). Imports come
exclusively from ``xlsx_read.<public>``; the ruff ``banned-api`` rule
in ``scripts/pyproject.toml`` blocks any ``xlsx_read._*`` import.
``lxml`` is NOT imported at all (xlsx-9 emits HTML, does not parse it
— D-A4).
"""
from __future__ import annotations

from .cli import main
from .exceptions import (
    _AppError,
    GfmMergesRequirePolicy,
    HeaderRowsConflict,
    IncludeFormulasRequiresHTML,
    InconsistentHeaderDepth,
    InternalError,
    PostValidateFailed,
    SelfOverwriteRefused,
)


# ---------------------------------------------------------------------------
# Public helper — Python-caller facing surface.
#
# ``convert_xlsx_to_md`` is a thin kwarg → argv marshaller that delegates
# to :func:`cli.main`. Same semantics as invoking the shim from the shell,
# but Python-callable for embedding / unit tests.
#
# Signature mirrors ``convert_xlsx_to_csv`` / ``convert_xlsx_to_json``
# in xlsx2csv2json (D-A3 / D7 pattern). Boolean True kwargs append the
# flag only (no ``=True``); None kwargs are skipped.
# ---------------------------------------------------------------------------

_KNOWN_KWARGS: frozenset[str] = frozenset({
    "sheet",
    "include_hidden",
    "format",
    "header_rows",
    "memory_mode",
    "hyperlink_scheme_allowlist",
    "no_table_autodetect",
    "no_split",
    "gap_rows",
    "gap_cols",
    "gfm_merge_policy",
    "datetime_format",
    "include_formulas",
    "json_errors",
})


def convert_xlsx_to_md(
    input_path: object,
    output_path: object = None,
    **kwargs: object,
) -> int:
    """Public helper — convert ``.xlsx`` to Markdown. See ``docs/TASK.md §5.2``.

    Equivalent to ``python3 xlsx2md.py INPUT [OUTPUT] [--flag value ...]``.
    Returns the process-style exit code (0 on success, non-zero on
    documented failure modes per the envelope catalogue).

    ``kwargs`` keys become long-form flags: ``{"no_split": True}`` →
    ``--no-split``; ``{"format": "hybrid"}`` → ``--format=hybrid``.
    Boolean True appends just the flag; False or None skip the flag
    entirely; any other value uses the ``--flag=value`` atomic-token form
    so kwargs containing leading ``--`` cannot be swallowed as a separate
    flag (D-A3 / D7 lock, inherited from xlsx-2 M4).

    Supported kwargs (per ARCH §5.2): sheet, include_hidden, format,
    header_rows, memory_mode, hyperlink_scheme_allowlist,
    no_table_autodetect, no_split, gap_rows, gap_cols, gfm_merge_policy,
    datetime_format, include_formulas, json_errors.

    Raises:
        TypeError: any kwarg name outside the supported set (M4 fix —
            prevents ``SystemExit(2)`` propagation when argparse rejects
            an unknown flag; the helper documents an integer return and
            Python callers should not have to catch ``SystemExit``).
    """
    unknown = set(kwargs) - _KNOWN_KWARGS
    if unknown:
        raise TypeError(
            f"convert_xlsx_to_md got unexpected keyword argument(s): "
            f"{sorted(unknown)!r}. Supported: {sorted(_KNOWN_KWARGS)!r}."
        )
    argv: list[str] = [str(input_path)]
    if output_path is not None:
        argv.append(str(output_path))
    for key, value in kwargs.items():
        if value is None or value is False:
            continue
        flag = "--" + key.replace("_", "-")
        if value is True:
            argv.append(flag)
        else:
            argv.append(f"{flag}={value}")
    return main(argv)


__all__ = [
    "main",
    "convert_xlsx_to_md",
    "_AppError",
    "SelfOverwriteRefused",
    "GfmMergesRequirePolicy",
    "IncludeFormulasRequiresHTML",
    "PostValidateFailed",
    "InconsistentHeaderDepth",
    "HeaderRowsConflict",
    "InternalError",
]

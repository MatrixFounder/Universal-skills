"""F3 — Per-table format selector (GFM/HTML auto-select). LIVE since 012-06.

For each ``(sheet_info, region, table_data, hyperlinks_map)`` 4-tuple yielded
by :mod:`dispatch`, chooses GFM or HTML emit format, writes H2 / H3
headings, routes to the matching emitter, and flushes to the output sink.

Promotion rules applied by :func:`select_format` when ``--format hybrid``
(D2 lock — ARCH §5.1):

1. ``table_data.rows`` contains a ``None`` cell after column position 0 in
   any row (body-merge heuristic) → ``"html"`` (D3 / R12.a)
2. Any header contains `` › `` separator (multi-row header) → ``"html"``
   (D12 / R14.c)
3. ``--include-formulas`` AND table has >= 1 formula cell (starts with
   ``"="``) → ``"html"`` (D14 / R12.b)
4. ``listobject_header_row_count == 0`` (synthetic headers) → ``"html"``
   (D13 / R12.c)

Returns ``"gfm"`` if none apply. For ``--format gfm`` or ``--format html``,
returns the fixed value directly (no promotion check needed).

GfmMergesRequirePolicy raise-site (R15 / D14):
    Fired inside :func:`emit_workbook_md` after a table is read (merge
    presence is unknown pre-open) when ``--format gfm``,
    ``--gfm-merge-policy fail`` (default), and body merges are detected.
    Callers catch this as CODE=2.

Honest-scope note:
    The ``None``-run merge heuristic (A-A3): a cell explicitly set to
    ``None`` by the spreadsheet author is indistinguishable from a merge
    child at the ``TableData`` layer. Follow-up xlsx-10.B may add a merges
    side-channel to remove the ambiguity.
"""
from __future__ import annotations

from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    pass


def _has_body_merges(table_data: object) -> bool:
    """True iff ``table_data.rows`` contains a probable merge-child cell.

    Heuristic: a ``None`` cell at column position > 0 in any row signals
    a horizontal merge child (the anchor is the last non-``None`` cell to
    the left).  A ``None`` in column 0 is treated as an empty cell, not a
    merge child.

    Honest-scope (A-A3): a cell explicitly set to ``None`` by the author
    is indistinguishable from a merge child here.  Follow-up xlsx-10.B may
    add a merges side-channel.
    """
    rows = getattr(table_data, "rows", [])
    for row in rows:
        for col_idx, cell in enumerate(row):
            if col_idx > 0 and cell is None:
                return True
    return False


def _is_multi_row_header(table_data: object) -> bool:
    """True iff any element of ``table_data.headers`` contains `` › ``.

    The `` › `` separator (U+203A with surrounding spaces) is the D6
    locked multi-row header encoding written by ``xlsx_read``.

    Honest-scope (A-A3): a workbook with a literal `` › `` in a
    single-row header will trigger this predicate.
    """
    headers = getattr(table_data, "headers", [])
    return any(" › " in h for h in headers)


def _has_formula_cells(table_data: object) -> bool:
    """True iff any cell value in ``table_data.rows`` is a formula string.

    A formula string starts with ``"="``  (the Excel formula marker).
    This is only meaningful when ``reader.read_table(include_formulas=True)``
    was used; otherwise the library surfaces the cached value and this
    predicate always returns ``False`` — which is the correct behaviour
    (no promotion when formulas are not requested).
    """
    rows = getattr(table_data, "rows", [])
    for row in rows:
        for cell in row:
            if isinstance(cell, str) and cell.startswith("="):
                return True
    return False


def _is_synthetic_header(table_data: object) -> bool:
    """True iff ``table_data.region.listobject_header_row_count == 0``.

    This signals that ``xlsx_read`` synthesised col_1..col_N header labels
    because the ListObject had no explicit header row (D13 / R12.c).
    Only fires for ``source == "listobject"`` regions.
    """
    region = getattr(table_data, "region", None)
    if region is None:
        return False
    return (
        getattr(region, "source", None) == "listobject"
        and getattr(region, "listobject_header_row_count", None) == 0
    )


def select_format(table_data: object, args: object) -> str:
    """Return ``"gfm"`` or ``"html"`` for this table.

    Short-circuits on ``args.format == "gfm"`` or ``"html"``.  For
    ``"hybrid"`` applies four promotion rules in priority order per
    ARCH §2.1 F3 / TASK lines 90-108:

    1. Body merges detected → ``"html"``
    2. Multi-row header ( `` › `` ) → ``"html"``
    3. ``--include-formulas`` AND formula cell present → ``"html"``
    4. Synthetic header (``listobject_header_row_count == 0``) → ``"html"``

    Falls back to ``"gfm"`` if none apply.
    """
    fmt = getattr(args, "format", "hybrid")
    if fmt == "gfm":
        return "gfm"
    if fmt == "html":
        return "html"
    # fmt == "hybrid": apply four promotion rules in priority order.
    if _has_body_merges(table_data):
        return "html"
    if _is_multi_row_header(table_data):
        return "html"
    if getattr(args, "include_formulas", False) and _has_formula_cells(table_data):
        return "html"
    if _is_synthetic_header(table_data):
        return "html"
    return "gfm"


def _gap_detect_label(state: dict[str, int], sheet_name: str) -> str:
    """Return the next ``"Table-N"`` label for *sheet_name*.

    Maintains a per-sheet counter inside *state*.  The counter is
    incremented on every call for the same sheet name, giving
    ``"Table-1"``, ``"Table-2"``, etc., in discovery order.  The counter
    resets implicitly when the sheet changes (different key in *state*).

    For ``--no-split`` whole-sheet single region with ``region.name is None``,
    this always returns ``"Table-1"`` (ARCH Q-A1 closed decision).
    """
    state[sheet_name] = state.get(sheet_name, 0) + 1
    return f"Table-{state[sheet_name]}"


def emit_workbook_md(reader: object, args: object, out: IO[str]) -> int:
    """Outer orchestration loop: H2 per sheet, H3 per table, emit to ``out``.

    Iterates the ``(SheetInfo, TableRegion, TableData, hyperlinks_map)``
    4-tuples produced by :func:`dispatch.iter_table_payloads`.

    H2 / H3 heading rules:
    - ``## SheetName`` emitted at first table for each new sheet, UNLESS
      ``args.sheet != "all"`` (single-sheet mode: caller knows the sheet,
      R7.d suppresses the H2 wrapper).
    - ``### TableName`` (ListObject / named range) or ``### Table-N``
      (gap-detect / ``--no-split``) always emitted (ARCH Q-A1 closed).

    R15 raise-site (D14):
    - ``--format gfm`` + body merges + ``gfm_merge_policy == "fail"``
      raises :class:`GfmMergesRequirePolicy` (CODE=2) after the table is
      read (merge presence is unknown until the table is materialised by
      the library).

    D-A7 streaming: :meth:`out.flush` called after each table so piped
    consumers see output incrementally.

    Returns:
        ``0`` on success.  Failure paths raise ``_AppError`` subclasses
        (caught by :func:`cli.main` envelope).
    """
    from .dispatch import iter_table_payloads  # noqa: PLC0415
    from .emit_gfm import emit_gfm_table  # noqa: PLC0415
    from .emit_html import emit_html_table  # noqa: PLC0415
    from .exceptions import GfmMergesRequirePolicy  # noqa: PLC0415

    current_sheet: str | None = None
    emitted_any = False
    single_sheet_mode = (getattr(args, "sheet", "all") != "all")
    gap_state: dict[str, int] = {}  # per-sheet counter for unnamed regions

    for sheet_info, region, table_data, hyperlinks_map in iter_table_payloads(
        reader, args
    ):
        # R7.d: --sheet NAME suppresses H2 wrapper.
        if not single_sheet_mode:
            if current_sheet != sheet_info.name:
                if emitted_any:
                    out.write("\n")
                out.write(f"## {sheet_info.name}\n\n")
                current_sheet = sheet_info.name

        # H3 per table (ARCH Q-A1 closed: emit even for --no-split).
        table_label = region.name or _gap_detect_label(gap_state, sheet_info.name)
        out.write(f"### {table_label}\n\n")

        # R15 raise-site (D14): --format=gfm + body merges + fail policy.
        if (
            getattr(args, "format", "hybrid") == "gfm"
            and getattr(args, "gfm_merge_policy", "fail") == "fail"
            and _has_body_merges(table_data)
        ):
            raise GfmMergesRequirePolicy({
                "table": table_label,
                "sheet": sheet_info.name,
                "suggestion": (
                    "use --format hybrid, --format html, or "
                    "--gfm-merge-policy duplicate/blank"
                ),
            })

        fmt = select_format(table_data, args)
        if fmt == "gfm":
            emit_gfm_table(
                table_data, out,
                gfm_merge_policy=getattr(args, "gfm_merge_policy", "fail"),
                hyperlink_allowlist=getattr(args, "_hyperlink_allowlist", None),
                hyperlinks_map=hyperlinks_map,
                cell_addr_prefix=f"{sheet_info.name}!",
            )
        else:  # "html"
            emit_html_table(
                table_data, out,
                include_formulas=getattr(args, "include_formulas", False),
                hyperlink_allowlist=getattr(args, "_hyperlink_allowlist", None),
                hyperlinks_map=hyperlinks_map,
                cell_addr_prefix=f"{sheet_info.name}!",
            )
        out.write("\n")
        out.flush()  # D-A7 streaming flush
        emitted_any = True

    return 0

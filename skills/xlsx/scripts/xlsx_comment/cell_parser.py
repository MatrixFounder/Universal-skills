"""Cell-syntax parser and sheet resolver (F2).

Migrated from `xlsx_add_comment.py` F2 region during Task 002.

Public API:
    parse_cell_syntax(text) -> tuple[str | None, str]
        Parses A5, Sheet2!B5, 'Q1 2026'!A1, 'Bob''s Sheet'!A1.
        Apostrophe escape `''` -> `'`. Returns (None, ref) for
        unqualified, (sheet_name, ref) otherwise. Raises
        InvalidCellRef on syntax error.
    resolve_sheet(qualified, all_sheets) -> sheet_name
        Applies M2 first-VISIBLE-sheet rule when qualifier is None;
        case-sensitive lookup with M3 suggestion when qualifier is
        given; raises SheetNotFound or NoVisibleSheet.
    _load_sheets_from_workbook(workbook_xml_root) -> list[dict]
        Parses <sheet> elements from xl/workbook.xml; private but
        used by both resolve_sheet here AND by the unpack/edit/pack
        pipeline at call sites further up the stack. NOT in __all__
        — callers reach it via the explicit
        `xlsx_comment.cell_parser._load_sheets_from_workbook` path.
"""
from __future__ import annotations

import re
import sys

from lxml import etree  # type: ignore  # noqa: F401  # used in type annotations only

from .constants import R_NS, SS_NS
from .exceptions import InvalidCellRef, NoVisibleSheet, SheetNotFound

__all__ = ["parse_cell_syntax", "resolve_sheet"]

_CELL_REF_RE = re.compile(r"^[A-Z]+[0-9]+$")


def parse_cell_syntax(text: str) -> tuple[str | None, str]:
    """Parse a `--cell` value into `(sheet_name | None, cell_ref)`.

    Forms accepted:
        "A5"                   -> (None, "A5")          # default sheet
        "Sheet2!B5"            -> ("Sheet2", "B5")      # cross-sheet
        "'Q1 2026'!A1"         -> ("Q1 2026", "A1")     # quoted with space
        "'Bob''s Sheet'!A1"    -> ("Bob's Sheet", "A1") # apostrophe escape

    Cell-ref normalisation: trims whitespace, strips `$` (absolute-ref
    prefix), uppercases. Sheet-name preserves case verbatim (M3
    case-sensitive lookup happens downstream in `resolve_sheet`).

    Raises `InvalidCellRef` on:
        - empty / whitespace-only input
        - unterminated quoted sheet (`'Foo` without closing `'`)
        - quoted sheet name not followed by `!` (`'Foo'A1` — missing `!`)
        - cell-ref not matching `^[A-Z]+[0-9]+$` after normalisation
    """
    text = text.strip()
    if not text:
        raise InvalidCellRef("empty --cell value")

    sheet: str | None = None
    cell_ref = text

    if text.startswith("'"):
        # Quoted-sheet form: walk char-by-char to find the closing quote,
        # treating `''` (two consecutive single-quotes) as an escaped
        # apostrophe. Mirrors Excel formula-syntax convention.
        sheet_chars: list[str] = []
        i = 1
        terminated = False
        while i < len(text):
            ch = text[i]
            if ch == "'":
                # Peek ahead: '' = escape, '! = end-of-name, anything
                # else = malformed (unescaped quote inside name).
                if i + 1 < len(text) and text[i + 1] == "'":
                    sheet_chars.append("'")
                    i += 2
                    continue
                if i + 1 >= len(text) or text[i + 1] != "!":
                    raise InvalidCellRef(
                        f"quoted sheet name must be followed by '!': {text!r}"
                    )
                sheet = "".join(sheet_chars)
                cell_ref = text[i + 2:]
                terminated = True
                break
            sheet_chars.append(ch)
            i += 1
        if not terminated:
            raise InvalidCellRef(f"unterminated quoted sheet name: {text!r}")
    elif "!" in text:
        # Unquoted-sheet form: split on first `!`. A second `!` inside
        # cell_ref will fail the regex below — clear error.
        sheet, cell_ref = text.split("!", 1)

    # Sarcasmotron MAJ-1: empty sheet name (from `"''!A1"` quoted-empty
    # or `"!A5"` unquoted-empty) is malformed input, not "sheet not
    # found" — fail at parse time with the right error class.
    if sheet == "":
        raise InvalidCellRef(f"empty sheet name in {text!r}")

    cell_ref_norm = cell_ref.strip().replace("$", "").upper()
    if not _CELL_REF_RE.match(cell_ref_norm):
        raise InvalidCellRef(
            f"cell ref does not match A1 syntax: {cell_ref!r}"
        )
    return sheet, cell_ref_norm


def _load_sheets_from_workbook(
    workbook_root: "etree._Element",
) -> list[dict]:
    """Return list of `{name, sheetId, rId, state}` dicts in document order.

    Reads `<sheet>` children of `<sheets>` from `xl/workbook.xml`. The
    `state` attribute defaults to `"visible"` per ECMA-376 §18.2.20
    when absent (matches Excel's own treatment of unset state).

    Reused by `resolve_sheet` here AND by the unpack→edit→pack pipeline
    in tasks 2.04 / 2.05 (do not inline this helper at call sites).
    """
    sheets: list[dict] = []
    for el in workbook_root.findall(f"{{{SS_NS}}}sheets/{{{SS_NS}}}sheet"):
        name = el.get("name")
        # Sarcasmotron MAJ-2: a `<sheet>` missing the `name` attribute
        # is a malformed workbook (Excel never emits this; xlsx-5
        # validator rejects it). Skip rather than poison `name_map`
        # with `None` keys — downstream `resolve_sheet` would silently
        # return None or AttributeError on `.lower()` of a None name.
        if name is None or name == "":
            continue
        sheets.append({
            "name": name,
            "sheetId": el.get("sheetId"),
            "rId": el.get(f"{{{R_NS}}}id"),
            "state": el.get("state") or "visible",
        })
    return sheets


def resolve_sheet(qualified: str | None, all_sheets: list[dict]) -> str:
    """Resolve target sheet name.

    - `qualified is None` → return first sheet whose `state` is `"visible"`
      (M2 first-VISIBLE rule). If every sheet is hidden / veryHidden →
      raise `NoVisibleSheet`.
    - `qualified` given → **case-sensitive** match against `<sheet name>`
      (M3). On match: if the resolved sheet is hidden / veryHidden, emit
      a stderr info note (the user explicitly qualified a hidden sheet —
      do not silently rewrite their target, just warn). On miss: raise
      `SheetNotFound` with `available = [all names]` and (when a
      case-insensitive match exists) `suggestion = <correctly-cased name>`.

    Note vs spec: task-001-07-cell-parser.md lists the signature as
    `(workbook_root, qualified, all_sheets)`. The `workbook_root` param
    is dropped here — `all_sheets` (built by `_load_sheets_from_workbook`)
    already carries every field this function reads, so threading the
    raw lxml root through every call site is unused-coupling. Documented
    deviation; no behaviour change.
    """
    name_map = {s["name"]: s for s in all_sheets}

    if qualified is None:
        for s in all_sheets:
            if s["state"] in (None, "", "visible"):
                return s["name"]
        raise NoVisibleSheet(
            "all sheets are hidden or veryHidden; no default available"
        )

    if qualified in name_map:
        s = name_map[qualified]
        if s["state"] in ("hidden", "veryHidden"):
            sys.stderr.write(
                f"Note: target sheet {qualified!r} has state="
                f"{s['state']!r} — proceeding (explicit qualifier).\n"
            )
        return qualified

    suggestion = next(
        (s["name"] for s in all_sheets
         if s["name"].lower() == qualified.lower()),
        None,
    )
    raise SheetNotFound(
        qualified,
        [s["name"] for s in all_sheets],
        suggestion,
    )

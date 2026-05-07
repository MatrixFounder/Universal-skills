#!/usr/bin/env python3
"""Insert a Microsoft Excel comment into a target cell of a .xlsx workbook.

This is the xlsx parity script for `docx_add_comment.py`. It edits the
OOXML directly via `office.unpack` + lxml + `office.pack` (the same
pattern docx_add_comment.py uses), because the openpyxl `Comment` API
does not support threaded comments and produces non-deterministic VML.

Why direct OOXML editing instead of openpyxl: as of openpyxl 3.1 the
high-level API (a) only writes legacy `<comment>` (no Excel-365
threaded comments), (b) re-emits the entire workbook on save (so
pre-existing comments and styles get re-serialised — diffs become
unreadable), and (c) does not maintain `<o:idmap data>` / `o:spid`
collision invariants when multiple VML drawings exist. We unpack,
edit specific parts via lxml, and repack — the same surgical pattern
`docx_add_comment.py` and `docx_fill_template.py` use.

Usage (single comment, legacy default):
    xlsx_add_comment.py INPUT.xlsx OUTPUT.xlsx \\
        --cell A5 --author "Reviewer" --text "Please verify formula"

Usage (single comment, threaded — Excel 365 fidelity, writes BOTH a
legacy stub AND a threadedComment + personList per Q7 closure in
ARCHITECTURE.md §6):
    xlsx_add_comment.py INPUT.xlsx OUTPUT.xlsx \\
        --cell Sheet2!B5 --author "Reviewer" --text "Date out of range" \\
        --threaded

Usage (cross-sheet, quoted sheet name with apostrophe-escape):
    xlsx_add_comment.py INPUT.xlsx OUTPUT.xlsx \\
        --cell "'Q1 2026'!A1" --author "Validator" --text "Header missing"

Usage (batch — auto-detects flat-array vs xlsx-7 envelope):
    xlsx_add_comment.py INPUT.xlsx OUTPUT.xlsx \\
        --batch findings.json --default-author "Validator"

    # Or piped from xlsx-7:
    xlsx_check_rules.py file.xlsx --rules rules.json --json | \\
        xlsx_add_comment.py file.xlsx out.xlsx --batch - --default-author "Bot"

Cell syntax (`--cell`):
    A5                       — first VISIBLE sheet (workbook order, skipping
                               state="hidden" and state="veryHidden")
    Sheet2!B5                — A1-style cross-sheet
    'Q1 2026'!A1             — quoted sheet name (whitespace allowed)
    'Bob''s Sheet'!A1        — apostrophe escape `''` → `'`

Batch (`--batch`):
    Two input shapes auto-detected by JSON root type:
        list  →  flat-array `[{cell, author, text, [initials], [threaded]}, ...]`
        dict  →  xlsx-7 envelope `{ok, summary, findings: [...]}` — fields are
                 mapped: cell ← finding.cell, text ← finding.message,
                 author ← --default-author (REQUIRED), initials ← derived,
                 threaded ← --default-threaded.
    Group-findings (`row: null`) are skipped and counted in stderr summary.
    Pre-parse size cap: 8 MiB; larger → exit 2 `BatchTooLarge`.

Mutex / dependency rules (enforced post-parse):
    MX-A : --cell  XOR  --batch
    MX-B : --threaded  XOR  --no-threaded
    DEP-1: --text + --author REQUIRED when --cell
    DEP-2: --default-author REQUIRED when --batch is xlsx-7-envelope shape
    DEP-3: --default-threaded MUST NOT be combined with --cell
    DEP-4: --json-errors routes argparse usage errors through
           _errors.report_error (already wired by add_json_errors_argument).

Exit codes:
    0  — comment(s) added successfully
    1  — I/O / pack failure / malformed OOXML
    2  — usage error / not-found / batch-shape error
         (UsageError, SheetNotFound, NoVisibleSheet, InvalidCellRef,
          MergedCellTarget, EmptyCommentBody, InvalidBatchInput,
          BatchTooLarge, MissingDefaultAuthor, DuplicateLegacyComment,
          DuplicateThreadedComment)
    3  — input is password-protected or legacy CFB (cross-3 contract)
    6  — INPUT and OUTPUT resolve to the same path, including via
         symlink (cross-7 H1 SelfOverwriteRefused)

Honest scope (v1, locked by tests/test_xlsx_add_comment.py::TestHonestScope):
    R9.a — reply-threads not supported; every threadedComment is top-level
           (no `parentId` attribute).
    R9.b — comment body is plain text only — no bold/italic/links.
    R9.c — VML shape uses Excel's default anchor offsets only — no custom
           positioning.
    R9.d — Excel 365 may silently mutate legacy → threaded on save → goldens
           are AGENT-OUTPUT-ONLY, never round-tripped through Excel
           (see tests/golden/README.md).
    R9.e — `<threadedComment id>` is UUIDv4 — non-deterministic by design.
           `<person id>` is UUIDv5(NAMESPACE_URL, displayName) — stable.
    R9.f — per-row `initials` override only via BatchRow.initials in
           flat-array mode; envelope-mode initials are derived from
           --default-author. A separate --default-initials flag is v2.
    R9.g — `--unpacked-dir DIR` library mode (parity with
           docx_add_comment.py) is v2; pipeline integration in v1 is via
           --batch path.json.

Architecture-locked decisions (closes ARCHITECTURE.md §6 / §6.1 / §6.2):
    Q2 — `--text ""` or whitespace-only → exit 2 `EmptyCommentBody`.
    Q5 — `--date ISO` overrides; default = `datetime.now(timezone.utc)`
         in `YYYY-MM-DDTHH:MM:SSZ` form.
    Q7 — `--threaded` writes BOTH legacy stub + threadedComment + personList
         (Excel-365 fidelity). `--no-threaded` writes legacy only.
         Defaults to legacy-only (--no-threaded implicit).

OOXML pitfalls (see references/comments-and-threads.md §3):
    `<o:idmap data>` is a comma-separated LIST workbook-wide; `<v:shape o:spid>`
    is per-shape integer workbook-wide. They are NOT the same collision
    domain. `personList` rel goes on `xl/_rels/workbook.xml.rels` (NOT a sheet
    rels file); `threadedComment` rel goes on the sheet rels.

Status: v1 — single-cell + batch modes; legacy `<comment>` + Excel-365
threaded `<threadedComment>` + `<personList>` parts; merged-cell
resolver (`--allow-merged-target`); duplicate-cell pre-flight matrix
(`DuplicateLegacyComment` / `DuplicateThreadedComment`); cross-3/4/5/7
hardening (encrypted / macro-warn / json-errors / same-path); env-gated
post-pack `office/validate.py` integrity guard. Honest-scope locks at
`tests/test_xlsx_add_comment.py::TestHonestScope`. Goldens diff at
`tests/_golden_diff.py` + `tests/golden/outputs/`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree  # type: ignore

from _errors import add_json_errors_argument, report_error
from office._encryption import EncryptedFileError, assert_not_encrypted
from office._macros import warn_if_macros_will_be_dropped
from office.pack import pack
from office.unpack import unpack


# region — Namespaces and content-type constants
SS_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
V_NS = "urn:schemas-microsoft-com:vml"
O_NS = "urn:schemas-microsoft-com:office:office"
X_NS = "urn:schemas-microsoft-com:office:excel"
THREADED_NS = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"

COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
COMMENTS_CT = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml"
)
VML_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/vmlDrawing"
)
VML_CT = "application/vnd.openxmlformats-officedocument.vmlDrawing"
THREADED_REL_TYPE = (
    "http://schemas.microsoft.com/office/2017/10/relationships/threadedComment"
)
THREADED_CT = (
    "application/vnd.ms-excel.threadedcomments+xml"
)
PERSON_REL_TYPE = (
    "http://schemas.microsoft.com/office/2017/10/relationships/person"
)
PERSON_CT = "application/vnd.ms-excel.person+xml"

# Default Excel-style VML anchor (R9.c — locked, no custom offsets in v1).
# Order: from-col, from-col-off, from-row, from-row-off, to-col, to-col-off,
# to-row, to-row-off (1024-twip units, per Excel convention).
DEFAULT_VML_ANCHOR = "3, 15, 0, 5, 5, 31, 4, 8"

# 8 MiB pre-parse cap on --batch input (TASK m2 / m-4 boundary).
BATCH_MAX_BYTES = 8 * 1024 * 1024
# endregion


# region — Local exception classes (raised inside main; converted to envelopes)
#
# Each typed error carries class attributes `code` (exit code) and
# `envelope_type` (the JSON envelope `type` field). The unified handler
# in `main()` reads them and routes through `_errors.report_error` —
# avoids one `except` clause per error class.
class _AppError(Exception):
    """Base for app-level typed errors that translate to JSON envelopes."""

    code: int = 1
    envelope_type: str = "InternalError"

    @property
    def details(self) -> dict:
        """Subclasses override to populate envelope `details` field."""
        return {}


class UsageError(_AppError):
    """MX-A/MX-B/DEP-1..4 violations and other CLI misuse."""

    code = 2
    envelope_type = "UsageError"


class SheetNotFound(_AppError):
    """Sheet name in --cell does not match any <sheet> in workbook.xml."""

    code = 2
    envelope_type = "SheetNotFound"

    def __init__(self, name: str, available: list[str], suggestion: str | None = None):
        self.name = name
        self.available = available
        self.suggestion = suggestion
        super().__init__(name)

    @property
    def details(self) -> dict:
        d = {"name": self.name, "available": list(self.available)}
        if self.suggestion is not None:
            d["suggestion"] = self.suggestion
        return d


class NoVisibleSheet(_AppError):
    """All sheets are state=hidden or veryHidden; no default available."""

    code = 2
    envelope_type = "NoVisibleSheet"


class InvalidCellRef(_AppError):
    """Cell reference does not match A1 syntax."""

    code = 2
    envelope_type = "InvalidCellRef"


class MergedCellTarget(_AppError):
    """Target cell is a non-anchor of a merged range; --allow-merged-target absent."""

    code = 2
    envelope_type = "MergedCellTarget"

    def __init__(self, target: str, anchor: str, range_ref: str):
        self.target = target
        self.anchor = anchor
        self.range_ref = range_ref
        super().__init__(f"{target} is non-anchor of merged {range_ref}")

    @property
    def details(self) -> dict:
        return {"target": self.target, "anchor": self.anchor, "range": self.range_ref}


class EmptyCommentBody(_AppError):
    """--text is empty or whitespace-only (Q2 closure)."""

    code = 2
    envelope_type = "EmptyCommentBody"


class InvalidBatchInput(_AppError):
    """--batch JSON neither flat-array nor xlsx-7 envelope shape."""

    code = 2
    envelope_type = "InvalidBatchInput"


class BatchTooLarge(_AppError):
    """--batch input exceeds the 8 MiB pre-parse cap."""

    code = 2
    envelope_type = "BatchTooLarge"

    def __init__(self, size_bytes: int):
        self.size_bytes = size_bytes
        super().__init__(f"batch exceeds 8 MiB cap: {size_bytes} bytes")

    @property
    def details(self) -> dict:
        return {"size_bytes": self.size_bytes, "cap_bytes": 8 * 1024 * 1024}


class MissingDefaultAuthor(_AppError):
    """xlsx-7 envelope shape requires --default-author."""

    code = 2
    envelope_type = "MissingDefaultAuthor"


class DuplicateLegacyComment(_AppError):
    """--no-threaded against a cell that already has a legacy <comment>."""

    code = 2
    envelope_type = "DuplicateLegacyComment"

    def __init__(self, message: str, sheet: str, cell: str):
        self.sheet = sheet
        self.cell = cell
        super().__init__(message)

    @property
    def details(self) -> dict:
        return {"sheet": self.sheet, "cell": self.cell}


class DuplicateThreadedComment(_AppError):
    """--no-threaded against a cell with an existing threaded thread (M-2)."""

    code = 2
    envelope_type = "DuplicateThreadedComment"

    def __init__(
        self, message: str, sheet: str, cell: str, existing_thread_size: int,
    ):
        self.sheet = sheet
        self.cell = cell
        self.existing_thread_size = existing_thread_size
        super().__init__(message)

    @property
    def details(self) -> dict:
        return {
            "sheet": self.sheet,
            "cell": self.cell,
            "existing_thread_size": self.existing_thread_size,
        }


class SelfOverwriteRefused(_AppError):
    """INPUT and OUTPUT resolve to the same path (cross-7 H1)."""

    code = 6
    envelope_type = "SelfOverwriteRefused"


class OutputIntegrityFailure(_AppError):
    """Post-pack office.validate.py rejected the produced workbook (2.08 guard)."""

    code = 1
    envelope_type = "OutputIntegrityFailure"


class MalformedVml(_AppError):
    """VML drawing has unparseable XML or a non-integer in `<o:idmap data>`.

    Defensive: Excel-emitted VML always has well-formed integers; this
    error fires only on tampered / corrupted workbooks. Treated as exit
    1 (I/O / malformed input) rather than exit 2 (user CLI error).
    """

    code = 1
    envelope_type = "MalformedVml"
# endregion


# region — F2: Cell-syntax parser + sheet resolver (impl: task 2.02)
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
# endregion


# region — F3: Batch loader (impl: task 2.06)
@dataclass(frozen=True)
class BatchRow:
    """One row of a --batch input, normalised across both shapes."""

    cell: str
    text: str
    author: str
    initials: str | None
    threaded: bool


_BATCH_CAP_BYTES = 8 * 1024 * 1024  # m2 / m-4


def load_batch(
    path_or_dash: str,
    default_author: str | None,
    default_threaded: bool,
) -> tuple[list[BatchRow], int]:
    """Return `(rows, skipped_grouped)`.

    Accepts `path_or_dash`:
        - a filesystem path → enforce 8 MiB cap via `Path.stat().st_size`
        - "-"                → read stdin with `read(8 * MiB + 1)` boundary check

    Auto-detects shape by JSON root type:
        list → flat-array `[{cell, author, text, [initials], [threaded]}, ...]`
        dict-with-{ok,summary,findings} → xlsx-7 envelope; map fields per
            ARCHITECTURE.md §I2.2; require `default_author` else
            `MissingDefaultAuthor`.

    Group-findings (`row: null`) skipped; counted into the second tuple
    element so `main()` can emit the stderr summary.
    """
    # ---- Step 1: Pre-parse size cap (m2 / m-4 boundary) ----
    if path_or_dash == "-":
        # Read up to cap+1; if we managed to read more than cap, reject.
        # Boundary: exactly-8-MiB stdin is accepted; 8 MiB + 1 byte rejected.
        data = sys.stdin.buffer.read(_BATCH_CAP_BYTES + 1)
        if len(data) > _BATCH_CAP_BYTES:
            raise BatchTooLarge(len(data))
    else:
        p = Path(path_or_dash)
        size = p.stat().st_size
        if size > _BATCH_CAP_BYTES:
            raise BatchTooLarge(size)
        data = p.read_bytes()

    # ---- Step 2: Parse JSON ----
    try:
        root = json.loads(data)
    except json.JSONDecodeError as exc:
        raise InvalidBatchInput(f"--batch input is not valid JSON: {exc}") from exc

    rows: list[BatchRow] = []
    skipped_grouped = 0

    # ---- Step 3: Shape detection (I2.1) ----
    if isinstance(root, list):
        # Flat-array shape.
        for i, item in enumerate(root):
            if not isinstance(item, dict):
                raise InvalidBatchInput(
                    f"flat-array row {i}: expected object, got {type(item).__name__}"
                )
            # Required keys must be present AND non-null (None/null would
            # produce stringified "None" downstream — refuse fast).
            missing = [k for k in ("cell", "text", "author")
                       if item.get(k) in (None, "")]
            if missing:
                raise InvalidBatchInput(
                    f"flat-array row {i}: missing or null required key(s): "
                    f"{', '.join(missing)}"
                )
            rows.append(BatchRow(
                cell=str(item["cell"]),
                text=str(item["text"]),
                author=str(item["author"]),
                initials=(str(item["initials"]) if "initials" in item
                          and item["initials"] is not None else None),
                threaded=bool(item.get("threaded", default_threaded)),
            ))
        return rows, skipped_grouped

    if isinstance(root, dict) and {"ok", "summary", "findings"} <= set(root.keys()):
        # xlsx-7 envelope shape (I2.2).
        if not default_author:
            raise MissingDefaultAuthor(
                "--default-author is required for xlsx-7 envelope shape "
                "(R4.c / DEP-2)"
            )
        derived_initials = _initials_from_author(default_author)
        findings = root["findings"]
        if not isinstance(findings, list):
            raise InvalidBatchInput(
                f"envelope.findings must be a list, got {type(findings).__name__}"
            )
        for i, finding in enumerate(findings):
            if not isinstance(finding, dict):
                raise InvalidBatchInput(
                    f"envelope.findings[{i}]: expected object, "
                    f"got {type(finding).__name__}"
                )
            # R4.e: skip group-findings whose anchor cell is undefined.
            if finding.get("row") is None:
                skipped_grouped += 1
                continue
            if "cell" not in finding or "message" not in finding:
                raise InvalidBatchInput(
                    f"envelope.findings[{i}]: missing 'cell' or 'message'"
                )
            rows.append(BatchRow(
                cell=str(finding["cell"]),
                text=str(finding["message"]),
                author=default_author,
                initials=derived_initials,
                threaded=default_threaded,
            ))
        return rows, skipped_grouped

    raise InvalidBatchInput(
        "JSON root is neither a flat array nor an xlsx-7 envelope "
        "(expected list, or dict with keys {ok, summary, findings})"
    )
# endregion


# region — F4: OOXML editor (scanners + part-counter — task 2.03)
_SPID_RE = re.compile(r"^_x0000_s(\d+)$")
_PART_INT_RE = re.compile(r"(\d+)\.xml$")


def _vml_part_paths(tree_root_dir: Path) -> list[Path]:
    """All VML drawing parts in the workbook, deterministic order.

    Two filename conventions are in use across consumers:
      - Excel:    `xl/drawings/vmlDrawing<N>.xml`
      - openpyxl: `xl/drawings/<anyname><N>.vml`  (e.g. `commentsDrawing1.vml`)

    Both are valid VML drawings. The scanners must see ALL of them so
    the workbook-wide invariants on `<o:idmap data>` and `o:spid` hold
    regardless of who originally wrote the file.
    """
    vml_dir = tree_root_dir / "xl" / "drawings"
    if not vml_dir.is_dir():
        return []
    paths = set(vml_dir.glob("vmlDrawing*.xml")) | set(vml_dir.glob("*.vml"))
    return sorted(paths)

# Hardened parser for VML: tampered input must NOT be allowed to expand
# entities (billion-laughs / XXE). lxml default already disables network
# fetches, but resolve_entities and huge_tree need explicit lockdown for
# defensive code reading user-provided OOXML.
_VML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    huge_tree=False,
)


def _parse_vml(vml_path: Path) -> "etree._Element":
    """Parse a vmlDrawing*.xml file; raise MalformedVml on syntax error.

    Centralised so both scanners share the same defensive XML parse,
    AND so the hardened XMLParser (entity-expansion disabled — defense
    vs billion-laughs / XXE on tampered VML) is the single source of
    truth.
    """
    try:
        return etree.parse(str(vml_path), parser=_VML_PARSER).getroot()
    except etree.XMLSyntaxError as exc:
        raise MalformedVml(f"{vml_path}: XML parse error: {exc}") from exc


def scan_idmap_used(tree_root_dir: Path) -> set[int]:
    """Workbook-wide union of all integers claimed by `<o:idmap data>` lists.

    Per M-1: `<o:idmap data>` is a COMMA-SEPARATED LIST per ECMA-376 / VML 1.0
    (e.g. `data="1,5,9"` claims integers 1, 5, AND 9 for the drawing). A
    naive scalar parse silently corrupts heavily-edited workbooks. The
    scanner unions every integer from every `<o:idmap>` element across
    every `xl/drawings/vmlDrawing*.xml` part — that is the workbook-wide
    invariant the allocator must respect.

    Edge cases:
        - directory `xl/drawings/` absent → empty set (nothing to claim).
        - `<o:shapelayout>` without `<o:idmap>` child → contributes nothing.
        - `<o:idmap data="">` (empty list) → contributes nothing.
        - non-integer token in the list → raise `MalformedVml` (exit 1).
    """
    used: set[int] = set()
    # `_vml_part_paths` returns sorted Excel-style + openpyxl-style VML
    # parts. Sort is for deterministic `MalformedVml` error-path output
    # (goldens / regression diffs); set-union itself is order-independent.
    for vml_path in _vml_part_paths(tree_root_dir):
        root = _parse_vml(vml_path)
        # Use .iter() not .findall() so we don't have to know whether
        # <o:idmap> is wrapped in <o:shapelayout> or hoisted (Excel
        # is consistent; tampered files vary).
        for idmap_el in root.iter(f"{{{O_NS}}}idmap"):
            data_attr = idmap_el.get("data", "") or ""
            for token in data_attr.split(","):
                token = token.strip()
                if not token:
                    continue
                try:
                    used.add(int(token))
                except ValueError as exc:
                    raise MalformedVml(
                        f"{vml_path}: malformed integer in "
                        f"<o:idmap data>: {token!r}"
                    ) from exc
    return used


def scan_spid_used(tree_root_dir: Path) -> set[int]:
    """Workbook-wide set of NNNN integers from `<v:shape id="_x0000_sNNNN">`.

    DIFFERENT collision domain from idmap (C1): every `<v:shape>` across
    every VML part must have a unique NNNN. Mirrors Excel's own
    `_x0000_s1025`-then-`_x0000_s1026` allocator pattern.

    Non-conforming `id` attributes (anything that doesn't match
    `^_x0000_s\\d+$`) are skipped — Excel sometimes emits these for
    legacy AutoShapes that aren't in our managed range. The allocator
    is conservative: max+1 over the *managed* range only.
    """
    used: set[int] = set()
    for vml_path in _vml_part_paths(tree_root_dir):
        root = _parse_vml(vml_path)
        for shape_el in root.iter(f"{{{V_NS}}}shape"):
            shape_id = shape_el.get("id", "") or ""
            m = _SPID_RE.match(shape_id)
            if m:
                used.add(int(m.group(1)))
    return used


def next_part_counter(tree_root_dir: Path, glob_pattern: str) -> int:
    """`max(N) + 1` over filenames matching `glob_pattern`; `1` if none.

    Used INDEPENDENTLY for `xl/comments*.xml`, `xl/threadedComments*.xml`,
    and `xl/drawings/vmlDrawing*.xml` — the three counters do NOT share
    state. Gap-free is NOT a goal: a workbook with `comments1.xml` +
    `comments3.xml` (gap at 2) yields `4` (max+1), not `2` (gap-fill).
    Excel itself does max+1; gap-fill would create rels-target ambiguity
    on round-trip.

    > [!IMPORTANT]
    > **Callers MUST use `*.xml` not `?.xml`.** The task spec's literal
    > example `"xl/comments?.xml"` only matches single-digit names —
    > a workbook with `comments10.xml` would be invisible to the glob,
    > and the next allocation would silently collide with the existing
    > 10th part. Tasks 2.04 / 2.06 invoke this helper via the
    > convenience wrapper `_allocate_new_parts` below, which hardcodes
    > the three valid `*.xml` patterns. Direct callers in tests use
    > `*.xml` per the test layout.
    """
    nums: list[int] = []
    for p in tree_root_dir.glob(glob_pattern):
        m = _PART_INT_RE.search(p.name)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) + 1 if nums else 1


@dataclass(frozen=True)
class _Allocation:
    """Workbook-wide pre-scan results bundled into a single value.

    Used by `single_cell_main` (task 2.04) and `batch_main` (task 2.06) to
    do the pre-scan ONCE per invocation — never per-row in batch mode.
    The four fields are the inputs to every per-row part-allocation
    decision in F4 helpers (`ensure_legacy_comments_part`,
    `ensure_threaded_comments_part`, `ensure_vml_drawing`, `add_vml_shape`).
    """

    idmap_used: set[int]
    spid_used: set[int]
    next_comments_n: int
    next_threaded_m: int
    next_vml_k: int


def _allocate_new_parts(tree_root_dir: Path) -> _Allocation:
    """Run all three scanners + counters ONCE on the unpacked tree.

    Per ARCHITECTURE.md §I2.3: workbook-wide pre-scan happens once per
    `xlsx_add_comment.py` invocation, not per row in batch mode (which
    would be ~50× slower on `T-batch-50`). Hardcodes the three correct
    `*.xml` glob patterns so downstream callers cannot drift to the
    spec-literal `?.xml` foot-gun (see `next_part_counter` docstring).

    All four fields are READ-ONLY snapshots — Stage-2 task 2.06's
    incremental allocator MUTATES local copies of `idmap_used` /
    `spid_used` as new rows allocate, so the next row sees the already-
    chosen values. Do NOT mutate the returned dataclass in-place.
    """
    return _Allocation(
        idmap_used=scan_idmap_used(tree_root_dir),
        spid_used=scan_spid_used(tree_root_dir),
        next_comments_n=next_part_counter(tree_root_dir, "xl/comments*.xml"),
        next_threaded_m=next_part_counter(
            tree_root_dir, "xl/threadedComments*.xml"
        ),
        next_vml_k=next_part_counter(
            tree_root_dir, "xl/drawings/vmlDrawing*.xml"
        ),
    )


# --- F4: Path resolution + rels/CT idempotent patches (task 2.04) ---

import os as _os  # for normpath; avoids touching the existing import block
import shutil as _shutil
import tempfile as _tempfile

_CELL_REF_SPLIT_RE = re.compile(r"^([A-Z]+)([0-9]+)$")


def _column_letters_to_index(letters: str) -> int:
    """`A` → 0, `B` → 1, `Z` → 25, `AA` → 26 (0-based, lex-base-26 over A..Z)."""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def _cell_ref_to_zero_based(cell_ref: str) -> tuple[int, int]:
    """`A5` → (col=0, row=4) — `<x:Column>` and `<x:Row>` in VML are 0-based."""
    m = _CELL_REF_SPLIT_RE.match(cell_ref)
    if not m:
        raise InvalidCellRef(f"cannot extract row/col from {cell_ref!r}")
    return _column_letters_to_index(m.group(1)), int(m.group(2)) - 1


def _resolve_target(
    rels_file_path: Path, tree_root_dir: Path, target: str,
) -> Path:
    """Resolve a Relationship `Target` attribute to an absolute file `Path`.

    OOXML allows two forms:
      - **Package-absolute**: `Target="/xl/comments/comment1.xml"` →
        path is `tree_root_dir / "xl/comments/comment1.xml"`.
      - **Relative**: `Target="../comments/comment1.xml"` → path is
        relative to the rels file's *document directory*, which is the
        rels file's parent minus the `_rels/` component (e.g.
        `xl/worksheets/_rels/sheet1.xml.rels` → doc dir is `xl/worksheets/`,
        so `../comments/comment1.xml` resolves to `xl/comments/comment1.xml`).
    """
    if target.startswith("/"):
        return tree_root_dir / target.lstrip("/")
    rels_parent = rels_file_path.parent
    doc_dir = rels_parent.parent if rels_parent.name == "_rels" else rels_parent
    return Path(_os.path.normpath(str(doc_dir / target)))


def _make_relative_target(
    rels_file_path: Path, target_part_path: Path,
) -> str:
    """Build a `Target=` value relative to the rels file's document directory.

    Inverse of `_resolve_target` for the relative form. We always emit the
    relative form because Excel itself does — keeps round-trips clean.

    **Forward-slash invariant** (Sarcasmotron MAJ-1 lock): OPC / ECMA-376
    Part 2 §9 mandates `/` as the path separator in `Target=` regardless
    of OS. `os.path.relpath` returns the platform-native separator
    (`\\` on Windows). We normalise to `/` here so emission is portable.
    """
    rels_parent = rels_file_path.parent
    doc_dir = rels_parent.parent if rels_parent.name == "_rels" else rels_parent
    rel = _os.path.relpath(str(target_part_path), start=str(doc_dir))
    return rel.replace(_os.sep, "/")


def _resolve_workbook_rels(tree_root_dir: Path) -> dict[str, str]:
    """Parse `xl/_rels/workbook.xml.rels` → `{rId: target}` (raw `Target` strings)."""
    rels_path = tree_root_dir / "xl" / "_rels" / "workbook.xml.rels"
    if not rels_path.is_file():
        return {}
    root = etree.parse(str(rels_path)).getroot()
    return {
        rel.get("Id"): rel.get("Target")
        for rel in root.findall(f"{{{PR_NS}}}Relationship")
    }


def _sheet_part_path(tree_root_dir: Path, sheet: dict) -> Path:
    """Return the absolute path to `xl/worksheets/sheet<S>.xml` for the sheet.

    Resolution: workbook.xml.rels[sheet.rId].Target → tree_root_dir/xl/<target>.
    Sheet metadata `dict` is shaped per `_load_sheets_from_workbook`.
    """
    wb_rels = _resolve_workbook_rels(tree_root_dir)
    target = wb_rels.get(sheet["rId"])
    if target is None:
        raise SheetNotFound(
            sheet["name"], available=[],
            suggestion=None,
        )
    rels_path = tree_root_dir / "xl" / "_rels" / "workbook.xml.rels"
    return _resolve_target(rels_path, tree_root_dir, target)


def _sheet_rels_path(worksheet_part_path: Path) -> Path:
    """`xl/worksheets/sheet1.xml` → `xl/worksheets/_rels/sheet1.xml.rels`."""
    return (
        worksheet_part_path.parent
        / "_rels"
        / f"{worksheet_part_path.name}.rels"
    )


def _open_or_create_rels(rels_path: Path) -> "etree._Element":
    """Load or create an empty `<Relationships>` root for a rels file."""
    if rels_path.is_file():
        return etree.parse(str(rels_path)).getroot()
    return etree.Element(f"{{{PR_NS}}}Relationships", nsmap={None: PR_NS})


def _allocate_rid(rels_root: "etree._Element") -> str:
    """`max(rIdN) + 1` over existing `<Relationship Id="rId...">` ids."""
    used: list[int] = []
    for rel in rels_root.findall(f"{{{PR_NS}}}Relationship"):
        rid = rel.get("Id", "")
        m = re.match(r"^rId(\d+)$", rid)
        if m:
            used.append(int(m.group(1)))
    return f"rId{max(used) + 1 if used else 1}"


def _find_rel_of_type(
    rels_root: "etree._Element", rel_type: str,
) -> "etree._Element | None":
    """Return the first `<Relationship>` whose `Type` matches, or None."""
    for rel in rels_root.findall(f"{{{PR_NS}}}Relationship"):
        if rel.get("Type") == rel_type:
            return rel
    return None


def _patch_sheet_rels(
    sheet_rels_path: Path,
    rels_root: "etree._Element",
    target_part_path: Path,
    rel_type: str,
) -> str:
    """Idempotent: ensure a `<Relationship>` for `target_part_path` of
    `rel_type` exists in `rels_root`. Returns the rId (existing or new).

    Caller is responsible for serialising `rels_root` back to disk; this
    function only mutates the in-memory tree.

    Note vs spec: task-001-09-legacy-write.md lists the signature as
    `_patch_sheet_rels(sheet_rels_root, target_part_path, rel_type)` —
    3 params. Implementation prepends `sheet_rels_path` (4 params) so
    `_make_relative_target` can compute the correct relative `Target=`
    string from the rels file location. Without that path, we'd have
    to hardcode the rels-document-dir relationship, which breaks for
    workbook-scoped rels (M6, used by 2.05's `personList` write path).
    Documented deviation; no behaviour drift from the contract.
    """
    target_str = _make_relative_target(sheet_rels_path, target_part_path)
    # Idempotent: if an identical (Type, Target) pair already exists, reuse.
    for rel in rels_root.findall(f"{{{PR_NS}}}Relationship"):
        if rel.get("Type") == rel_type and rel.get("Target") == target_str:
            return rel.get("Id")
    rid = _allocate_rid(rels_root)
    etree.SubElement(
        rels_root,
        f"{{{PR_NS}}}Relationship",
        Id=rid,
        Type=rel_type,
        Target=target_str,
    )
    return rid


def _patch_content_types(
    ct_root: "etree._Element",
    override_path: str,
    content_type: str,
    *,
    default_extension: str | None = None,
) -> None:
    """Idempotent: ensure `<Override PartName="...">` for `override_path` exists.

    m-3 idempotency rule: if `default_extension` is supplied AND the
    `[Content_Types].xml` already declares `<Default Extension="..." ContentType="..."/>`
    for that extension matching `content_type`, do NOT add a redundant
    per-part `<Override>` (Default already covers it). Per the
    `task-001-09-legacy-write.md` spec for VML drawings.
    """
    # Existing per-part Override → no-op.
    for ov in ct_root.findall(f"{{{CT_NS}}}Override"):
        if ov.get("PartName") == override_path:
            return
    # Default-Extension covers it (m-3) → no-op.
    if default_extension is not None:
        for de in ct_root.findall(f"{{{CT_NS}}}Default"):
            if (
                de.get("Extension") == default_extension
                and de.get("ContentType") == content_type
            ):
                return
    etree.SubElement(
        ct_root,
        f"{{{CT_NS}}}Override",
        PartName=override_path,
        ContentType=content_type,
    )


# --- F4: Legacy comments + VML write paths (task 2.04) ---


def ensure_legacy_comments_part(
    tree_root_dir: Path,
    sheet: dict,
    next_n: int,
) -> tuple[Path, "etree._Element", "etree._Element", Path]:
    """Get-or-create `xl/commentsN.xml` bound to `sheet`'s rels.

    Returns `(comments_path, comments_root, sheet_rels_root, sheet_rels_path)`.

    Look-up rule: read the sheet's rels file, find the existing
    `comments` Relationship if any, and resolve its `Target` to a real
    file path. Pre-existing parts are reused regardless of filename
    convention (Excel `xl/commentsN.xml` vs openpyxl `xl/comments/commentN.xml`).
    NEW parts are emitted in Excel convention (`xl/comments<N>.xml`)
    using the `next_n` counter from `_allocate_new_parts`.

    Caller is responsible for serialising the trees and writing the
    Content_Types Override (via `_patch_content_types`).

    Note vs spec: task-001-09-legacy-write.md lists the signature as
    `(tree_root, sheet_name) -> (path, root)` — 2-tuple, sheet name
    string. Implementation accepts a `sheet` dict (per
    `_load_sheets_from_workbook` shape) and an explicit `next_n`
    counter, and returns a 4-tuple including `sheet_rels_root` +
    `sheet_rels_path`. Reasons:
      - Sheet dict carries `rId` so we can resolve via
        `xl/_rels/workbook.xml.rels` instead of guessing filenames.
      - `next_n` is allocated ONCE per invocation by
        `_allocate_new_parts` — passing it in keeps the workbook-wide
        pre-scan invariant (ARCH §I2.3).
      - Returning the rels root + path saves the caller an extra
        round-trip parse/write when wiring the VML drawing rel
        immediately after.
    Documented deviation; no behaviour drift from the contract.
    """
    sheet_part_path = _sheet_part_path(tree_root_dir, sheet)
    sheet_rels_path = _sheet_rels_path(sheet_part_path)
    sheet_rels_root = _open_or_create_rels(sheet_rels_path)

    existing = _find_rel_of_type(sheet_rels_root, COMMENTS_REL_TYPE)
    if existing is not None:
        comments_path = _resolve_target(
            sheet_rels_path, tree_root_dir, existing.get("Target", "")
        )
        if not comments_path.is_file():
            raise MalformedVml(
                f"sheet rels references missing comments part: {comments_path}"
            )
        comments_root = etree.parse(str(comments_path)).getroot()
        return comments_path, comments_root, sheet_rels_root, sheet_rels_path

    # Create new in Excel convention.
    comments_path = tree_root_dir / "xl" / f"comments{next_n}.xml"
    comments_root = etree.Element(
        f"{{{SS_NS}}}comments", nsmap={None: SS_NS},
    )
    etree.SubElement(comments_root, f"{{{SS_NS}}}authors")
    etree.SubElement(comments_root, f"{{{SS_NS}}}commentList")
    _patch_sheet_rels(
        sheet_rels_path, sheet_rels_root, comments_path, COMMENTS_REL_TYPE,
    )
    return comments_path, comments_root, sheet_rels_root, sheet_rels_path


def add_legacy_comment(
    comments_root: "etree._Element",
    ref: str,
    author: str,
    text: str,
) -> int:
    """Append `<comment ref=... authorId=...>` with case-sensitive author dedup
    (m5). Returns the `authorId` chosen (existing if author-string already in
    `<authors>`, else newly appended index).

    Caller validates `text.strip() != ""` (Q2 / EmptyCommentBody) — this
    helper trusts pre-validated input.
    """
    authors_el = comments_root.find(f"{{{SS_NS}}}authors")
    if authors_el is None:
        authors_el = etree.SubElement(comments_root, f"{{{SS_NS}}}authors")
    existing_authors = list(authors_el.findall(f"{{{SS_NS}}}author"))
    author_id = None
    for i, a in enumerate(existing_authors):
        # Case-sensitive identity comparison on displayName (m5 lock).
        if (a.text or "") == author:
            author_id = i
            break
    if author_id is None:
        new_author = etree.SubElement(authors_el, f"{{{SS_NS}}}author")
        new_author.text = author
        author_id = len(existing_authors)

    comment_list = comments_root.find(f"{{{SS_NS}}}commentList")
    if comment_list is None:
        comment_list = etree.SubElement(
            comments_root, f"{{{SS_NS}}}commentList",
        )
    comment_el = etree.SubElement(
        comment_list, f"{{{SS_NS}}}comment",
        ref=ref, authorId=str(author_id),
    )
    text_el = etree.SubElement(comment_el, f"{{{SS_NS}}}text")
    r_el = etree.SubElement(text_el, f"{{{SS_NS}}}r")
    t_el = etree.SubElement(r_el, f"{{{SS_NS}}}t")
    t_el.text = text
    if text != text.strip() or "  " in text:
        # Preserve internal whitespace per ECMA-376 §17.4.5.
        t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return author_id


def ensure_vml_drawing(
    tree_root_dir: Path,
    sheet: dict,
    sheet_rels_root: "etree._Element",
    sheet_rels_path: Path,
    idmap_data: int,
    next_k: int,
) -> tuple[Path, "etree._Element", bool]:
    """Get-or-create `xl/drawings/vmlDrawingK.xml`.

    Returns `(vml_path, vml_root, is_new)`. When reusing an existing
    VML part (rels lookup hit), `idmap_data` and `next_k` are ignored —
    the existing `<o:idmap data>` is preserved and we only append
    new shapes.

    NEW parts use Excel convention (`vmlDrawing<K>.xml`) with a fresh
    `<o:idmap data="N">` value (workbook-wide unique per C1+M-1 — caller
    supplies `idmap_data` from `_allocate_new_parts`).
    """
    existing = _find_rel_of_type(sheet_rels_root, VML_REL_TYPE)
    if existing is not None:
        vml_path = _resolve_target(
            sheet_rels_path, tree_root_dir, existing.get("Target", "")
        )
        if not vml_path.is_file():
            raise MalformedVml(
                f"sheet rels references missing VML drawing: {vml_path}"
            )
        vml_root = _parse_vml(vml_path)
        return vml_path, vml_root, False

    # Create new VML in Excel convention.
    vml_dir = tree_root_dir / "xl" / "drawings"
    vml_dir.mkdir(parents=True, exist_ok=True)
    vml_path = vml_dir / f"vmlDrawing{next_k}.xml"
    # Build root with the standard skeleton: <o:shapelayout><o:idmap/></o:shapelayout>
    # plus the one-time <v:shapetype id="_x0000_t202"> definition shared by all
    # comment shapes appended later via add_vml_shape.
    nsmap = {"v": V_NS, "o": O_NS, "x": X_NS}
    vml_root = etree.Element("xml", nsmap=nsmap)
    shapelayout = etree.SubElement(vml_root, f"{{{O_NS}}}shapelayout")
    shapelayout.set(f"{{{V_NS}}}ext", "edit")
    idmap_el = etree.SubElement(shapelayout, f"{{{O_NS}}}idmap")
    idmap_el.set(f"{{{V_NS}}}ext", "edit")
    idmap_el.set("data", str(idmap_data))
    shapetype = etree.SubElement(vml_root, f"{{{V_NS}}}shapetype")
    shapetype.set("id", "_x0000_t202")
    shapetype.set("coordsize", "21600,21600")
    shapetype.set(f"{{{O_NS}}}spt", "202")
    shapetype.set("path", "m,l,21600r21600,l21600,xe")
    stroke = etree.SubElement(shapetype, f"{{{V_NS}}}stroke")
    stroke.set("joinstyle", "miter")
    path = etree.SubElement(shapetype, f"{{{V_NS}}}path")
    path.set("gradientshapeok", "t")
    path.set(f"{{{O_NS}}}connecttype", "rect")

    _patch_sheet_rels(
        sheet_rels_path, sheet_rels_root, vml_path, VML_REL_TYPE,
    )
    return vml_path, vml_root, True


def add_vml_shape(
    vml_root: "etree._Element",
    ref: str,
    spid: int,
) -> None:
    """Append `<v:shape>` for a comment with the locked default Excel anchor.

    Per R9.c (honest-scope lock): VML uses Excel's default anchor offsets
    only — no custom positioning. The anchor list `DEFAULT_VML_ANCHOR`
    matches what Excel emits for a fresh comment.
    """
    col, row = _cell_ref_to_zero_based(ref)
    sid = f"_x0000_s{spid}"
    shape = etree.SubElement(vml_root, f"{{{V_NS}}}shape")
    shape.set("id", sid)
    shape.set(f"{{{O_NS}}}spid", sid)
    shape.set("type", "#_x0000_t202")
    shape.set(
        "style",
        "position:absolute;margin-left:59.25pt;margin-top:1.5pt;"
        "width:144pt;height:79pt;z-index:1;visibility:hidden",
    )
    shape.set("fillcolor", "#ffffe1")
    shape.set(f"{{{O_NS}}}insetmode", "auto")
    fill = etree.SubElement(shape, f"{{{V_NS}}}fill")
    fill.set("color2", "#ffffe1")
    shadow = etree.SubElement(shape, f"{{{V_NS}}}shadow")
    shadow.set("color", "black")
    shadow.set("obscured", "t")
    pth = etree.SubElement(shape, f"{{{V_NS}}}path")
    pth.set(f"{{{O_NS}}}connecttype", "none")
    textbox = etree.SubElement(shape, f"{{{V_NS}}}textbox")
    textbox.set("style", "mso-direction-alt:auto")
    div = etree.SubElement(textbox, "div")
    div.set("style", "text-align:left")
    cd = etree.SubElement(shape, f"{{{X_NS}}}ClientData")
    cd.set("ObjectType", "Note")
    etree.SubElement(cd, f"{{{X_NS}}}MoveWithCells")
    etree.SubElement(cd, f"{{{X_NS}}}SizeWithCells")
    anchor = etree.SubElement(cd, f"{{{X_NS}}}Anchor")
    anchor.text = DEFAULT_VML_ANCHOR
    auto_fill = etree.SubElement(cd, f"{{{X_NS}}}AutoFill")
    auto_fill.text = "False"
    row_el = etree.SubElement(cd, f"{{{X_NS}}}Row")
    row_el.text = str(row)
    col_el = etree.SubElement(cd, f"{{{X_NS}}}Column")
    col_el.text = str(col)


def _xml_serialize(root: "etree._Element", path: Path) -> None:
    """Serialise an lxml tree to disk with a stable XML declaration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )
    )


# --- F4: Threaded comments + personList (task 2.05) ---


def ensure_threaded_comments_part(
    tree_root_dir: Path,
    sheet: dict,
    sheet_rels_root: "etree._Element",
    sheet_rels_path: Path,
    next_m: int,
) -> tuple[Path, "etree._Element", bool]:
    """Get-or-create `xl/threadedComments<M>.xml` bound to `sheet`'s rels.

    Returns `(threaded_path, threaded_root, is_new)`. Reuse rule mirrors
    `ensure_legacy_comments_part`: existing parts found via the sheet's
    rels file (NOT filename-glob), so non-Excel naming conventions
    (e.g. openpyxl-emitted) are respected. NEW parts in Excel convention.

    Note vs spec: task-001-10-threaded-write.md lists the signature as
    `(tree_root, sheet_name) -> (path, root)` — 2-tuple, sheet name
    string. Implementation follows the same expanded shape used by
    `ensure_legacy_comments_part` (sheet dict + rels root/path + next_m
    counter from `_allocate_new_parts`) — same justification (rels-driven
    resolution, ARCH §I2.3 single-pass pre-scan invariant).
    """
    existing = _find_rel_of_type(sheet_rels_root, THREADED_REL_TYPE)
    if existing is not None:
        threaded_path = _resolve_target(
            sheet_rels_path, tree_root_dir, existing.get("Target", ""),
        )
        if not threaded_path.is_file():
            raise MalformedVml(
                f"sheet rels references missing threaded part: {threaded_path}"
            )
        threaded_root = etree.parse(str(threaded_path)).getroot()
        return threaded_path, threaded_root, False

    threaded_path = tree_root_dir / "xl" / f"threadedComments{next_m}.xml"
    threaded_root = etree.Element(
        f"{{{THREADED_NS}}}ThreadedComments", nsmap={None: THREADED_NS},
    )
    _patch_sheet_rels(
        sheet_rels_path, sheet_rels_root, threaded_path, THREADED_REL_TYPE,
    )
    return threaded_path, threaded_root, True


def ensure_person_list(
    tree_root_dir: Path,
) -> tuple[Path, "etree._Element", "etree._Element", Path, bool]:
    """Get-or-create `xl/persons/personList.xml` (workbook-scoped per M6).

    Returns `(pl_path, pl_root, wb_rels_root, wb_rels_path, is_new)`.

    M6 — load-bearing: the `personList` Relationship lives on
    `xl/_rels/workbook.xml.rels`, NOT on a sheet rels file. Without
    this exact rel attachment Excel-365 fails to render the threaded
    UI even when `xl/persons/personList.xml` is present and well-formed.
    """
    wb_rels_path = tree_root_dir / "xl" / "_rels" / "workbook.xml.rels"
    wb_rels_root = _open_or_create_rels(wb_rels_path)

    existing = _find_rel_of_type(wb_rels_root, PERSON_REL_TYPE)
    if existing is not None:
        pl_path = _resolve_target(
            wb_rels_path, tree_root_dir, existing.get("Target", ""),
        )
        if not pl_path.is_file():
            raise MalformedVml(
                f"workbook rels references missing personList: {pl_path}"
            )
        pl_root = etree.parse(str(pl_path)).getroot()
        return pl_path, pl_root, wb_rels_root, wb_rels_path, False

    # M6 lock: workbook-scoped path.
    pl_path = tree_root_dir / "xl" / "persons" / "personList.xml"
    pl_root = etree.Element(
        f"{{{THREADED_NS}}}personList", nsmap={None: THREADED_NS},
    )
    # Patch via the existing helper — `_patch_sheet_rels` is rels-file
    # agnostic despite the name (documented under MAJ-3 in 2.04). M6
    # makes us point it at `xl/_rels/workbook.xml.rels`, not a sheet rels.
    _patch_sheet_rels(
        wb_rels_path, wb_rels_root, pl_path, PERSON_REL_TYPE,
    )
    return pl_path, pl_root, wb_rels_root, wb_rels_path, True


def add_person(person_list_root: "etree._Element", display_name: str) -> str:
    """Idempotent-add `<person>` to the registry; return its `id` GUID.

    Per spec / m1:
      - `id` is `{UUIDv5(NAMESPACE_URL, displayName)}` upper-cased + braced
        — STABLE across runs given the same displayName.
      - `userId` is `display_name.casefold()` — handles non-ASCII
        (German `ß` → `ss`, locale-aware lower) where `.lower()` would
        produce wrong results.
      - `providerId="None"` is the literal string (3 chars, capital N) —
        Excel uses this to mark "no SSO provider"; Python's `None` would
        serialise to the string "None" anyway via lxml but the lock test
        verifies the literal.
      - Dedup on `displayName` is **case-sensitive** (m5) — `Alice` and
        `alice` produce two distinct `<person>` records.
    """
    for p in person_list_root.findall(f"{{{THREADED_NS}}}person"):
        # m5: case-sensitive identity on displayName.
        if p.get("displayName") == display_name:
            return p.get("id")

    person_id = "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, display_name)).upper() + "}"
    user_id = display_name.casefold()
    etree.SubElement(
        person_list_root,
        f"{{{THREADED_NS}}}person",
        displayName=display_name,
        id=person_id,
        userId=user_id,
        providerId="None",
    )
    return person_id


def add_threaded_comment(
    threaded_root: "etree._Element",
    ref: str,
    person_id: str,
    text: str,
    date_iso: str,
) -> str:
    """Append `<threadedComment ref=... dT=... personId=... id=...>{text}` and
    return the threadedComment `id`.

    R9.a — v1 does NOT emit `parentId`; every threadedComment is top-level.
    R9.b — body is plain text (no `<r>` / `<rPr>` rich-run wrappers).
    R9.e — `id` is UUIDv4: non-deterministic by design. Re-running the
        script produces a different `id` each time even with `--date`
        pinned. Goldens diff in task 2.10 masks this attribute via
        canonical-XML rewrite.
    """
    threaded_id = "{" + str(uuid.uuid4()).upper() + "}"
    tc = etree.SubElement(
        threaded_root,
        f"{{{THREADED_NS}}}threadedComment",
        ref=ref,
        dT=date_iso,
        personId=person_id,
        id=threaded_id,
    )
    text_el = etree.SubElement(tc, f"{{{THREADED_NS}}}text")
    text_el.text = text
    return threaded_id
# endregion


# region — F5: Merged-cell resolver + duplicate-cell matrix (task 2.07)
_MERGE_RANGE_RE = re.compile(r"^([A-Z]+)([0-9]+):([A-Z]+)([0-9]+)$")


def _parse_merge_range(range_ref: str) -> tuple[int, int, int, int]:
    """`A1:C3` → (min_col=0, min_row=0, max_col=2, max_row=2). 0-based."""
    m = _MERGE_RANGE_RE.match(range_ref)
    if not m:
        raise InvalidCellRef(f"malformed mergeCell range: {range_ref!r}")
    c1 = _column_letters_to_index(m.group(1))
    r1 = int(m.group(2)) - 1
    c2 = _column_letters_to_index(m.group(3))
    r2 = int(m.group(4)) - 1
    return c1, r1, c2, r2


def _anchor_of_range(range_ref: str) -> str:
    """`A1:C3` → `A1` (top-left cell of the range)."""
    m = _MERGE_RANGE_RE.match(range_ref)
    if not m:
        raise InvalidCellRef(f"malformed mergeCell range: {range_ref!r}")
    return f"{m.group(1)}{m.group(2)}"


def resolve_merged_target(
    sheet_xml_root: "etree._Element",
    ref: str,
    allow_redirect: bool,
) -> str:
    """If `ref` is a non-anchor of a `<mergeCell>` range:
        - allow_redirect=False (default) → raise `MergedCellTarget`.
        - allow_redirect=True → return the anchor cell ref + emit
          `MergedCellRedirect` info to stderr.

    The cell-IS-anchor case and the not-in-any-merged-range case both
    return `ref` unchanged (R6.c).

    Merge-range detection iterates `<mergeCells><mergeCell ref="...">`.
    Sheet-local: each call inspects only the sheet whose root was passed.
    """
    target_col, target_row = _cell_ref_to_zero_based(ref)
    for merge_el in sheet_xml_root.iter(f"{{{SS_NS}}}mergeCell"):
        range_ref = merge_el.get("ref", "") or ""
        if not range_ref:
            continue
        c1, r1, c2, r2 = _parse_merge_range(range_ref)
        in_range = (c1 <= target_col <= c2) and (r1 <= target_row <= r2)
        if not in_range:
            continue
        is_anchor = (target_col, target_row) == (c1, r1)
        if is_anchor:
            return ref  # R6.c — anchor passes through.
        anchor_ref = _anchor_of_range(range_ref)
        if allow_redirect:
            print(
                f"Note: MergedCellRedirect: {ref} is non-anchor of "
                f"merged range {range_ref}; redirecting to anchor {anchor_ref}",
                file=sys.stderr,
            )
            return anchor_ref
        raise MergedCellTarget(target=ref, anchor=anchor_ref, range_ref=range_ref)
    return ref


def detect_existing_comment_state(
    tree_root_dir: Path,
    sheet: dict,
    ref: str,
) -> dict:
    """Inspect a sheet's existing comments / threadedComments at `ref`.

    Returns `{"has_legacy": bool, "has_threaded": bool, "thread_size": int}`.

    Read-only — does NOT mutate the tree. Used as the pre-flight gate for
    the ARCH §6.1 duplicate-cell matrix in `single_cell_main` / `batch_main`.

    Resolution path: sheet rels → comments / threadedComments rels →
    parse part XML → count `ref` matches.
    """
    sheet_part_path = _sheet_part_path(tree_root_dir, sheet)
    sheet_rels_path = _sheet_rels_path(sheet_part_path)
    if not sheet_rels_path.is_file():
        return {"has_legacy": False, "has_threaded": False, "thread_size": 0}
    sheet_rels_root = etree.parse(str(sheet_rels_path)).getroot()

    has_legacy = False
    has_threaded = False
    thread_size = 0

    legacy_rel = _find_rel_of_type(sheet_rels_root, COMMENTS_REL_TYPE)
    if legacy_rel is not None:
        legacy_path = _resolve_target(
            sheet_rels_path, tree_root_dir, legacy_rel.get("Target", ""),
        )
        if legacy_path.is_file():
            legacy_root = etree.parse(str(legacy_path)).getroot()
            for c in legacy_root.iter(f"{{{SS_NS}}}comment"):
                if c.get("ref") == ref:
                    has_legacy = True
                    break

    threaded_rel = _find_rel_of_type(sheet_rels_root, THREADED_REL_TYPE)
    if threaded_rel is not None:
        threaded_path = _resolve_target(
            sheet_rels_path, tree_root_dir, threaded_rel.get("Target", ""),
        )
        if threaded_path.is_file():
            threaded_root = etree.parse(str(threaded_path)).getroot()
            for tc in threaded_root.iter(f"{{{THREADED_NS}}}threadedComment"):
                if tc.get("ref") == ref:
                    has_threaded = True
                    thread_size += 1

    return {
        "has_legacy": has_legacy,
        "has_threaded": has_threaded,
        "thread_size": thread_size,
    }


def _enforce_duplicate_matrix(
    state: dict,
    threaded_mode: bool,
    sheet_name: str,
    ref: str,
) -> None:
    """ARCH §6.1 duplicate-cell matrix — pre-flight raise gate.

    Six cells of the 3×2 matrix:
      - empty cell, either mode               → no-op (write paths handle).
      - legacy-only, --threaded               → no-op (Q7 fidelity dual-write).
      - legacy-only, --no-threaded            → DuplicateLegacyComment (R5.b).
      - thread exists, --threaded             → no-op (append to thread).
      - thread exists, --no-threaded          → DuplicateThreadedComment (M-2).

    `threaded_mode` is True when the caller will write a threaded entry
    (i.e. `args.threaded` is set, or default-threaded for envelope rows).
    """
    if state["has_threaded"] and not threaded_mode:
        # M-2: silent legacy write next to an existing thread is the
        # worst-of-both-worlds case (older clients see two unrelated
        # comments, Excel-365 sees an orphan legacy entry). Refuse fast.
        raise DuplicateThreadedComment(
            f"Cannot insert legacy-only comment on cell {ref} of sheet "
            f"{sheet_name!r}: a threaded comment thread already exists. "
            f"Use --threaded to append to the thread, or pick a different cell.",
            sheet=sheet_name, cell=ref,
            existing_thread_size=state["thread_size"],
        )
    if state["has_legacy"] and not state["has_threaded"] and not threaded_mode:
        # R5.b — duplicate legacy on --no-threaded.
        raise DuplicateLegacyComment(
            f"Cannot insert legacy comment on cell {ref} of sheet "
            f"{sheet_name!r}: a legacy comment already exists. "
            f"Use --threaded to attach a thread, or pick a different cell.",
            sheet=sheet_name, cell=ref,
        )
# endregion


# region — Helpers (cross-cutting glue; impl: task 2.01)
def _initials_from_author(author: str) -> str:
    """Derive initials = first letter of each whitespace-separated token."""
    parts = re.findall(r"\S+", author)
    return ("".join(p[:1] for p in parts) or "R").upper()[:8]


def _resolve_date(date_arg: str | None) -> str:
    """Q5 closure: --date overrides, else UTC now ISO-8601 with Z suffix."""
    if date_arg:
        return date_arg
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_args(args: argparse.Namespace) -> None:
    """Enforce MX-A/MX-B + DEP-1, DEP-3 from TASK §2.5. Raises `UsageError`.

    DEP-2 (xlsx-7 envelope shape requires --default-author) is shape-
    dependent and runs inside `load_batch` (task 2.06) AFTER the JSON
    is parsed; this validator only enforces the shape-independent rules.

    DEP-4 (json-errors envelope on argparse usage errors) is already
    wired by `_errors.add_json_errors_argument` via the parser.error
    monkey-patch — this validator does not handle it.
    """
    # MX-A: --cell XOR --batch (exactly one required).
    cell_given = args.cell is not None
    batch_given = args.batch is not None
    if cell_given and batch_given:
        raise UsageError("--cell and --batch are mutually exclusive")
    if not cell_given and not batch_given:
        raise UsageError("one of --cell or --batch is required")

    # MX-B: --threaded XOR --no-threaded.
    if args.threaded and args.no_threaded:
        raise UsageError("--threaded and --no-threaded are mutually exclusive")

    # DEP-1: --cell requires --text and --author.
    if cell_given:
        missing = [f for f, v in (("--text", args.text), ("--author", args.author))
                   if v is None]
        if missing:
            raise UsageError(
                f"--cell requires {' and '.join(missing)} (DEP-1)"
            )

    # DEP-3: --default-threaded only makes sense in --batch mode.
    if args.default_threaded and cell_given:
        raise UsageError(
            "--default-threaded must not be combined with --cell (DEP-3)"
        )

    # DEP-2 partial: if --batch points at a real path, verify it exists
    # (the shape-dependent --default-author check runs in load_batch).
    if batch_given and args.batch != "-":
        if not Path(args.batch).is_file():
            raise UsageError(f"--batch file not found: {args.batch}")


def _assert_distinct_paths(input_path: Path, output_path: Path) -> None:
    """Cross-7 H1 SelfOverwriteRefused — resolves through symlinks.

    Both paths are run through `Path.resolve(strict=False)` so a
    symlink whose target is INPUT (or vice versa) is caught — protects
    against the pack-time-crash-corrupts-source failure mode. On
    resolve OSError (broken symlink chain), falls back to literal-path
    compare. Locks: T-same-path, T-same-path-symlink,
    T-encrypted-same-path, TestSamePathGuard.
    """
    try:
        in_resolved = input_path.resolve(strict=False)
        out_resolved = output_path.resolve(strict=False)
    except OSError:
        in_resolved = input_path
        out_resolved = output_path
    if in_resolved == out_resolved:
        raise SelfOverwriteRefused(str(in_resolved))
# endregion


# region — F1: Argparse
def build_parser() -> argparse.ArgumentParser:
    """Build the full TASK §2.5 CLI surface.

    Mutex / dependency rules (MX-A, MX-B, DEP-1..4) are enforced
    post-parse in `_validate_args` (task 2.01) — argparse cannot
    express the conditional "required-when" rules natively.
    """
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else "Insert an Excel comment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="Source .xlsx/.xlsm.")
    parser.add_argument("output", type=Path, help="Destination .xlsx/.xlsm (must differ from input).")

    # Single-cell mode (MX-A group)
    parser.add_argument(
        "--cell",
        default=None,
        metavar="REF",
        help="Target cell. Forms: A5, Sheet2!B5, 'Q1 2026'!A1, 'Bob''s Sheet'!A1.",
    )
    parser.add_argument(
        "--text",
        default=None,
        metavar="MSG",
        help="Comment body (plain text). Empty or whitespace-only → exit 2 EmptyCommentBody.",
    )
    parser.add_argument(
        "--author",
        default=None,
        metavar="NAME",
        help="Display name. Required when --cell.",
    )
    parser.add_argument(
        "--initials",
        default=None,
        metavar="INI",
        help="Override initials (default: first letter of each whitespace-token in --author).",
    )

    # Batch mode (MX-A group)
    parser.add_argument(
        "--batch",
        default=None,
        metavar="FILE",
        help="JSON file (or - for stdin). Auto-detects flat-array vs xlsx-7 envelope. 8 MiB cap.",
    )
    parser.add_argument(
        "--default-author",
        dest="default_author",
        default=None,
        metavar="NAME",
        help="Required when --batch is xlsx-7 envelope shape; ignored otherwise.",
    )
    parser.add_argument(
        "--default-threaded",
        dest="default_threaded",
        action="store_true",
        help="Default `threaded` for envelope-shape rows.",
    )

    # Threaded-mode group (MX-B)
    parser.add_argument(
        "--threaded",
        action="store_true",
        help="Force threaded write (writes BOTH legacy stub + threadedComment + personList per Q7).",
    )
    parser.add_argument(
        "--no-threaded",
        dest="no_threaded",
        action="store_true",
        help="Force legacy-only write (no threaded part, no personList).",
    )

    # Cross-cutting & cell-policy
    parser.add_argument(
        "--allow-merged-target",
        dest="allow_merged_target",
        action="store_true",
        help="Redirect comment to anchor of merged range instead of failing fast (R6.b).",
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="ISO",
        help="Override timestamp on <threadedComment dT>. Default: datetime.now(UTC).",
    )

    add_json_errors_argument(parser)
    return parser
# endregion


# region — F6: main() / single_cell_main / batch_main
import subprocess as _subprocess


def _content_types_path(tree_root_dir: Path) -> Path:
    return tree_root_dir / "[Content_Types].xml"


_TRUTHY_ENV = {"1", "true", "yes", "on"}


def _post_validate_enabled() -> bool:
    """Truthy parser for `XLSX_ADD_COMMENT_POST_VALIDATE`.

    Sarcasmotron MIN-1 lock: bare `bool(env.get(...))` accepts `"0"` /
    `"false"` / `"no"` as TRUE, which is the opposite of user intent.
    Allowlist `1/true/yes/on` (case-insensitive); any other value is
    treated as disabled.
    """
    raw = _os.environ.get("XLSX_ADD_COMMENT_POST_VALIDATE", "")
    return raw.strip().lower() in _TRUTHY_ENV


def _post_pack_validate(output_path: Path) -> None:
    """R8 / 2.08 post-pack guard: invoke `office/validate.py` as a
    subprocess; raise `OutputIntegrityFailure` on real validation failure.

    Subprocess invocation is intentional for **process isolation**:
    `office/` is a byte-identical copy across docx/xlsx/pptx (CLAUDE.md
    §2), so we get clean module state, no shared lxml registries, and a
    stable boundary against future `office/validate` evolutions.

    Failure semantics (Sarcasmotron MAJ-1 lock):
      - exit 0          → ok, return.
      - exit 2 with
        "Unknown extension: .xlsm"
                        → no-op + stderr note. validate.py has no
                          macro-aware validator; .xlsm structural
                          validation is structurally beyond this guard's
                          scope. The vbaProject.bin sha256 invariant in
                          T-macro-xlsm-preserves covers macro round-trip.
      - non-zero        → `OutputIntegrityFailure` (exit 1) AND unlink
                          the corrupted output (Sarcasmotron MAJ-3 lock —
                          mirrors pack-failure cleanup pattern).
    """
    validate_script = Path(__file__).parent / "office" / "validate.py"
    if not validate_script.is_file():
        # Sarcasmotron NIT-3 lock: don't launch subprocess against a
        # non-existent script — give a clearer failure mode.
        raise OutputIntegrityFailure(
            f"post-pack guard: office/validate.py missing at {validate_script}"
        )
    cmd = [sys.executable, str(validate_script), str(output_path)]
    result = _subprocess.run(
        cmd, capture_output=True, text=True, timeout=60,
    )
    if result.returncode == 0:
        return

    combined = (result.stdout.strip() + "\n" + result.stderr.strip()).strip()
    if (
        result.returncode == 2
        and "Unknown extension" in combined
        and output_path.suffix.lower() in {".xlsm"}
    ):
        # .xlsm: no validator available. Log + continue.
        print(
            f"Note: post-pack validate skipped for {output_path.name} "
            f"(.xlsm structural validation is not supported by office/validate.py; "
            f"macro round-trip is covered by the vbaProject.bin sha256 invariant)",
            file=sys.stderr,
        )
        return

    # Real validation failure — unlink the corrupted output before raising
    # so a downstream consumer cannot mistake a half-broken artefact for
    # a usable workbook (mirrors pack-failure cleanup pattern).
    try:
        output_path.unlink()
    except (OSError, FileNotFoundError):
        pass
    raise OutputIntegrityFailure(
        f"post-pack validate.py rejected {output_path}: {combined[:8192]}"
    )


def single_cell_main(
    args: argparse.Namespace,
    tree_root_dir: Path,
    all_sheets: list[dict],
) -> int:
    """Single-cell legacy write path (task 2.04 — `--no-threaded` default).

    Threaded layer is added in task 2.05; merged-cell + duplicate-cell
    pre-flight in task 2.07. At this stage `--threaded` is accepted by
    argparse but the threaded part is NOT yet emitted (will be in 2.05).
    """
    # Q2 closure: empty / whitespace-only --text → fail at parse-equivalent
    # boundary, BEFORE any OOXML mutation, so the workbook isn't half-written.
    if not args.text or not args.text.strip():
        raise EmptyCommentBody(
            "--text is empty or whitespace-only (Q2: comments must have content)"
        )

    # Cell-syntax + sheet resolution (F2; task 2.02).
    qualified, cell_ref = parse_cell_syntax(args.cell)
    sheet_name = resolve_sheet(qualified, all_sheets)
    sheet = next(s for s in all_sheets if s["name"] == sheet_name)

    # F5 (task 2.07): merged-cell pre-flight. Read-only — may rewrite
    # `cell_ref` to the anchor when --allow-merged-target, or raise
    # MergedCellTarget on a non-anchor without the flag.
    sheet_part_path = _sheet_part_path(tree_root_dir, sheet)
    sheet_xml_root = etree.parse(str(sheet_part_path)).getroot()
    cell_ref = resolve_merged_target(
        sheet_xml_root, cell_ref, args.allow_merged_target,
    )

    # F5 (task 2.07): duplicate-cell matrix pre-flight (ARCH §6.1).
    # Threaded mode = explicit --threaded (default-threaded only applies
    # to --batch envelope rows, not single-cell).
    state = detect_existing_comment_state(tree_root_dir, sheet, cell_ref)
    _enforce_duplicate_matrix(
        state, threaded_mode=bool(args.threaded),
        sheet_name=sheet_name, ref=cell_ref,
    )

    # ONE workbook-wide pre-scan per invocation (task 2.03 spec / ARCH §I2.3).
    alloc = _allocate_new_parts(tree_root_dir)

    # Legacy comments part: get-or-create + append our <comment>.
    comments_path, comments_root, sheet_rels_root, sheet_rels_path = (
        ensure_legacy_comments_part(tree_root_dir, sheet, alloc.next_comments_n)
    )
    add_legacy_comment(comments_root, cell_ref, args.author, args.text)
    _xml_serialize(comments_root, comments_path)

    # VML drawing: get-or-create + append our <v:shape>. The `idmap_data`
    # value passed in only matters for NEW VML parts; reused parts keep
    # their existing <o:idmap data>.
    new_idmap = max(alloc.idmap_used) + 1 if alloc.idmap_used else 1
    vml_path, vml_root, vml_is_new = ensure_vml_drawing(
        tree_root_dir, sheet, sheet_rels_root, sheet_rels_path,
        idmap_data=new_idmap,
        next_k=alloc.next_vml_k,
    )
    # Shape ID: max+1 over the existing workbook range (m-1 chosen rule;
    # 1025 baseline for empty workbooks matches Excel's `_x0000_s1025` start).
    new_spid = max(alloc.spid_used) + 1 if alloc.spid_used else 1025
    add_vml_shape(vml_root, cell_ref, new_spid)
    _xml_serialize(vml_root, vml_path)

    # Sheet rels file may have grown (new comments + vml relationships);
    # always serialise so the new parts are reachable from the worksheet.
    _xml_serialize(sheet_rels_root, sheet_rels_path)

    # Patch [Content_Types].xml: idempotent Override per new part. The
    # comments part is always per-part Override (no Default Extension
    # convention for the comments content-type). The VML part: skip the
    # per-part Override if `<Default Extension="vml">` is already present
    # (m-3 idempotency rule).
    ct_path = _content_types_path(tree_root_dir)
    ct_root = etree.parse(str(ct_path)).getroot()
    _patch_content_types(
        ct_root,
        "/" + str(comments_path.relative_to(tree_root_dir)).replace("\\", "/"),
        COMMENTS_CT,
    )
    if vml_is_new:
        _patch_content_types(
            ct_root,
            "/" + str(vml_path.relative_to(tree_root_dir)).replace("\\", "/"),
            VML_CT,
            default_extension="vml",
        )

    # Q7 Option A (Excel-365 fidelity): when --threaded, write BOTH
    # the legacy stub (already done above) AND the threaded layer +
    # personList. The legacy stub keeps the file readable in older
    # Excel and LibreOffice; the threaded layer drives the modern
    # Comments side-pane. M6 lock: personList rel goes on
    # workbook.xml.rels, NOT sheet rels.
    if args.threaded:
        # personList (workbook-scoped — M6).
        pl_path, pl_root, wb_rels_root, wb_rels_path, pl_is_new = (
            ensure_person_list(tree_root_dir)
        )
        person_id = add_person(pl_root, args.author)
        _xml_serialize(pl_root, pl_path)
        if pl_is_new:
            _xml_serialize(wb_rels_root, wb_rels_path)
            _patch_content_types(
                ct_root,
                "/" + str(pl_path.relative_to(tree_root_dir)).replace("\\", "/"),
                PERSON_CT,
            )

        # threadedComments (sheet-scoped).
        threaded_path, threaded_root, threaded_is_new = (
            ensure_threaded_comments_part(
                tree_root_dir, sheet, sheet_rels_root, sheet_rels_path,
                next_m=alloc.next_threaded_m,
            )
        )
        add_threaded_comment(
            threaded_root, cell_ref, person_id, args.text, args.date_iso,
        )
        _xml_serialize(threaded_root, threaded_path)
        if threaded_is_new:
            _patch_content_types(
                ct_root,
                "/" + str(threaded_path.relative_to(tree_root_dir)).replace("\\", "/"),
                THREADED_CT,
            )
        # threaded write may have grown sheet rels (new threadedComment rel)
        # — re-serialise to capture; for the personList path, wb_rels were
        # serialised above when pl_is_new fired.
        _xml_serialize(sheet_rels_root, sheet_rels_path)

    _xml_serialize(ct_root, ct_path)
    return 0


def batch_main(
    args: argparse.Namespace,
    tree_root_dir: Path,
    all_sheets: list[dict],
) -> int:
    """Batch write path: load JSON → single open/save cycle → N comments.

    The "single open/save cycle" requirement (TASK §2 R4 + I2.3 step 3)
    is the perf driver: ~50× faster than per-row repack on T-batch-50.
    Pre-scan workbook ONCE; sheet-scoped state (comments_root, vml_root,
    sheet_rels_root, threaded_root) is memoised so each sheet's parts
    are opened on first use only.

    Incremental allocator (R4.h): after each row's allocation, the freshly-
    chosen `idmap_data` / `spid` are added to the local `idmap_used` /
    `spid_used` sets so the next row's allocator sees them. Without this,
    a 50-row batch would allocate the same `spid` 50 times.
    """
    rows, skipped_grouped = load_batch(
        args.batch, args.default_author, args.default_threaded,
    )

    if skipped_grouped:
        # I2.2 Acceptance: stderr summary for skipped group-findings.
        print(
            f"Note: skipped {skipped_grouped} group-finding"
            f"{'s' if skipped_grouped != 1 else ''} (row=null) per R4.e",
            file=sys.stderr,
        )

    # Workbook-wide pre-scan ONCE per invocation (ARCH §I2.3).
    alloc = _allocate_new_parts(tree_root_dir)
    idmap_used = set(alloc.idmap_used)
    spid_used = set(alloc.spid_used)
    next_vml_k = alloc.next_vml_k
    next_comments_n = alloc.next_comments_n
    next_threaded_m = alloc.next_threaded_m

    # Per-sheet memoisation. Key = sheet name (case-sensitive).
    # Each entry holds the in-memory roots + paths so we serialise once.
    sheet_state: dict[str, dict] = {}
    person_list_state: dict | None = None

    # Content_Types is workbook-scoped — open once, patch repeatedly.
    ct_path = _content_types_path(tree_root_dir)
    ct_root = etree.parse(str(ct_path)).getroot()

    # Per-sheet sheet-xml memo for merged-cell resolution (read-only).
    sheet_xml_cache: dict[str, "etree._Element"] = {}
    # In-batch dup matrix: rows already written this run augment the
    # input-state seen by `detect_existing_comment_state` so two batch
    # rows targeting the same cell with mixed --threaded modes still
    # honour ARCH §6.1 (M-2 lock as an output-invariant, not just input).
    written_state: dict[tuple[str, str], dict] = {}

    for row in rows:
        if not row.text or not row.text.strip():
            # Q2 closure applies in batch too.
            raise EmptyCommentBody(
                f"--batch row cell={row.cell!r}: text is empty/whitespace-only"
            )

        qualified, cell_ref = parse_cell_syntax(row.cell)
        sheet_name = resolve_sheet(qualified, all_sheets)
        sheet = next(s for s in all_sheets if s["name"] == sheet_name)

        # F5: merged-cell pre-flight (ARCH R6 / task 2.07).
        sx = sheet_xml_cache.get(sheet_name)
        if sx is None:
            sx = etree.parse(
                str(_sheet_part_path(tree_root_dir, sheet))
            ).getroot()
            sheet_xml_cache[sheet_name] = sx
        cell_ref = resolve_merged_target(
            sx, cell_ref, args.allow_merged_target,
        )

        # F5: duplicate-cell matrix pre-flight (ARCH §6.1 / task 2.07).
        # In batch, "threaded mode" is per-row: row.threaded reflects the
        # row's own --threaded flag (or default-threaded for envelope rows).
        # Augment on-disk state with rows already written this run so the
        # M-2 invariant holds as an OUTPUT-invariant, not just input
        # (two batch rows on the same cell with mixed modes would
        # otherwise sneak past the gate).
        state = detect_existing_comment_state(tree_root_dir, sheet, cell_ref)
        prev = written_state.get((sheet_name, cell_ref))
        if prev is not None:
            state = {
                "has_legacy": state["has_legacy"] or prev["has_legacy"],
                "has_threaded": state["has_threaded"] or prev["has_threaded"],
                "thread_size": state["thread_size"] + prev["thread_size"],
            }
        _enforce_duplicate_matrix(
            state, threaded_mode=row.threaded,
            sheet_name=sheet_name, ref=cell_ref,
        )
        # Record THIS row's contribution for the next row's gate.
        written_state[(sheet_name, cell_ref)] = {
            "has_legacy": True,  # every row writes a legacy stub (Q7).
            "has_threaded": row.threaded or (
                prev["has_threaded"] if prev else False
            ),
            "thread_size": (prev["thread_size"] if prev else 0) + (
                1 if row.threaded else 0
            ),
        }

        # Lazy-initialise per-sheet state on first row that touches that sheet.
        st = sheet_state.get(sheet_name)
        if st is None:
            comments_path, comments_root, sheet_rels_root, sheet_rels_path = (
                ensure_legacy_comments_part(
                    tree_root_dir, sheet, next_comments_n,
                )
            )
            # `ensure_legacy_comments_part` returns the path it would write
            # but does NOT serialise. So `comments_path.is_file()` is False
            # for fresh parts, True for reused (already-on-disk) ones.
            comments_was_new = not comments_path.is_file()
            if comments_was_new:
                # Next sheet that creates a new comments part must take
                # the next counter value.
                next_comments_n += 1
            st = {
                "sheet": sheet,
                "comments_path": comments_path,
                "comments_root": comments_root,
                "sheet_rels_root": sheet_rels_root,
                "sheet_rels_path": sheet_rels_path,
                "vml_path": None,
                "vml_root": None,
                "vml_was_new": False,
                "threaded_path": None,
                "threaded_root": None,
                "threaded_was_new": False,
                "comments_part_was_new": comments_was_new,
            }
            sheet_state[sheet_name] = st

        # Append legacy <comment>.
        add_legacy_comment(st["comments_root"], cell_ref, row.author, row.text)

        # Get-or-create VML drawing for this sheet (memoised).
        if st["vml_root"] is None:
            new_idmap = (max(idmap_used) + 1) if idmap_used else 1
            vml_path, vml_root, vml_is_new = ensure_vml_drawing(
                tree_root_dir, st["sheet"],
                st["sheet_rels_root"], st["sheet_rels_path"],
                idmap_data=new_idmap,
                next_k=next_vml_k,
            )
            st["vml_path"] = vml_path
            st["vml_root"] = vml_root
            st["vml_was_new"] = vml_is_new
            if vml_is_new:
                # New part claims the chosen idmap value AND consumes the K.
                idmap_used.add(new_idmap)
                next_vml_k += 1
            # Existing parts already contributed to idmap_used in pre-scan.

        # Allocate fresh spid for this shape — incremental.
        new_spid = (max(spid_used) + 1) if spid_used else 1025
        spid_used.add(new_spid)
        add_vml_shape(st["vml_root"], cell_ref, new_spid)

        # Threaded layer (Q7 fidelity dual-write per row.threaded).
        if row.threaded:
            # Person list (workbook-scoped — M6).
            if person_list_state is None:
                pl_path, pl_root, wb_rels_root, wb_rels_path, pl_is_new = (
                    ensure_person_list(tree_root_dir)
                )
                person_list_state = {
                    "pl_path": pl_path,
                    "pl_root": pl_root,
                    "wb_rels_root": wb_rels_root,
                    "wb_rels_path": wb_rels_path,
                    "is_new": pl_is_new,
                }
            person_id = add_person(person_list_state["pl_root"], row.author)

            # Threaded comments part (sheet-scoped, memoised).
            if st["threaded_root"] is None:
                threaded_path, threaded_root, threaded_is_new = (
                    ensure_threaded_comments_part(
                        tree_root_dir, st["sheet"],
                        st["sheet_rels_root"], st["sheet_rels_path"],
                        next_m=next_threaded_m,
                    )
                )
                st["threaded_path"] = threaded_path
                st["threaded_root"] = threaded_root
                st["threaded_was_new"] = threaded_is_new
                if threaded_is_new:
                    next_threaded_m += 1
            add_threaded_comment(
                st["threaded_root"], cell_ref, person_id,
                row.text, args.date_iso,
            )

    # ---- Serialise once per part ----
    for sheet_name, st in sheet_state.items():
        _xml_serialize(st["comments_root"], st["comments_path"])
        if st["vml_root"] is not None:
            _xml_serialize(st["vml_root"], st["vml_path"])
        if st["threaded_root"] is not None:
            _xml_serialize(st["threaded_root"], st["threaded_path"])
        # Sheet rels may have grown via comments / vml / threaded patches.
        _xml_serialize(st["sheet_rels_root"], st["sheet_rels_path"])

        # Patch [Content_Types].xml for this sheet's NEW parts.
        if st["comments_part_was_new"]:
            _patch_content_types(
                ct_root,
                "/" + str(st["comments_path"].relative_to(tree_root_dir)).replace("\\", "/"),
                COMMENTS_CT,
            )
        if st["vml_was_new"]:
            _patch_content_types(
                ct_root,
                "/" + str(st["vml_path"].relative_to(tree_root_dir)).replace("\\", "/"),
                VML_CT,
                default_extension="vml",
            )
        if st["threaded_was_new"]:
            _patch_content_types(
                ct_root,
                "/" + str(st["threaded_path"].relative_to(tree_root_dir)).replace("\\", "/"),
                THREADED_CT,
            )

    if person_list_state is not None:
        _xml_serialize(
            person_list_state["pl_root"], person_list_state["pl_path"],
        )
        if person_list_state["is_new"]:
            _xml_serialize(
                person_list_state["wb_rels_root"],
                person_list_state["wb_rels_path"],
            )
            _patch_content_types(
                ct_root,
                "/" + str(person_list_state["pl_path"].relative_to(tree_root_dir)).replace("\\", "/"),
                PERSON_CT,
            )

    _xml_serialize(ct_root, ct_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Orchestration entry point.

    Order of operations (each step's failure mode bubbles through the
    unified `_AppError` / `EncryptedFileError` handler at the bottom,
    which routes through `_errors.report_error` with the correct exit
    code and envelope type):

    1. parse_args      — argparse, with `add_json_errors_argument`
                          monkey-patching `parser.error` for DEP-4.
    2. _validate_args  — MX-A/B, DEP-1, DEP-3 (shape-independent).
    3. file-exists     — INPUT must exist (FileNotFound, code 1).
    4. cross-7 H1      — same-path resolved through symlinks (code 6).
    5. cross-3         — encryption / legacy-CFB pre-flight (code 3).
    6. cross-4         — macro warning to stderr (no failure path).
    7. date resolution — Q5: --date overrides; default UTC now ISO-Z.
    8. dispatch        — single_cell_main (--cell) or batch_main (--batch).
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    je = args.json_errors

    try:
        _validate_args(args)

        if not args.input.is_file():
            return report_error(
                f"Input not found: {args.input}", code=1,
                error_type="FileNotFound",
                details={"path": str(args.input)}, json_mode=je,
            )

        _assert_distinct_paths(args.input, args.output)

        # cross-3: encrypted / legacy CFB → exit 3.
        assert_not_encrypted(args.input)

        # cross-4: emit warning to stderr if .xlsm → .xlsx would drop macros.
        warn_if_macros_will_be_dropped(args.input, args.output, sys.stderr)

        # Q5: stash resolved ISO-8601 date on args for downstream consumers.
        args.date_iso = _resolve_date(args.date)

        # Both single-cell and batch paths share the unpack → mutate → pack
        # frame. Dispatch to the per-row handler inside the temp tree so
        # the pack-failure cleanup (MAJ-2) covers both modes.
        with _tempfile.TemporaryDirectory(prefix="xlsx_add_comment-") as td:
            tree_root = Path(td) / "tree"
            unpack(args.input, tree_root)
            wb_root = etree.parse(
                str(tree_root / "xl" / "workbook.xml")
            ).getroot()
            all_sheets = _load_sheets_from_workbook(wb_root)
            if args.batch is not None:
                rc = batch_main(args, tree_root, all_sheets)
            else:
                rc = single_cell_main(args, tree_root, all_sheets)
            if rc != 0:
                return rc
            # MAJ-2 lock: if pack fails mid-write the output may be a
            # corrupt half-zip. Mirror office_passwd.py's M1 cleanup
            # pattern — if pack raises, unlink the partial output then
            # re-raise so the user sees a clean exit-code path with no
            # orphan to debug. (TemporaryDirectory cleans tree_root.)
            try:
                pack(tree_root, args.output)
            except Exception:
                try:
                    args.output.unlink()
                except (OSError, FileNotFoundError):
                    pass
                raise

        # R8 / 2.08: opt-in post-pack integrity guard. Defence-in-depth
        # against developer error during xlsx-6 implementation — NOT a
        # substitute for input validation. Off by default to avoid
        # doubling invocation latency on production runs; CI / E2E set
        # XLSX_ADD_COMMENT_POST_VALIDATE=1 (truthy semantics —
        # `_post_validate_enabled` only honours `1/true/yes/on`).
        if _post_validate_enabled():
            _post_pack_validate(args.output)
        return 0

    except _AppError as exc:
        # Compose contextual message + envelope for the typed error.
        message = str(exc)
        if isinstance(exc, SelfOverwriteRefused):
            message = (
                f"INPUT and OUTPUT resolve to the same path: {exc} "
                f"(would corrupt the source on a pack-time crash)"
            )
            details = {"input": str(args.input), "output": str(args.output)}
        else:
            details = exc.details or None
        return report_error(
            message, code=exc.code, error_type=exc.envelope_type,
            details=details, json_mode=je,
        )
    except EncryptedFileError as exc:
        return report_error(
            str(exc), code=3, error_type="EncryptedFileError",
            details={"path": str(args.input)}, json_mode=je,
        )


if __name__ == "__main__":
    sys.exit(main())

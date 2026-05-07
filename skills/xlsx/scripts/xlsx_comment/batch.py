"""--batch input loader: BatchRow dataclass + load_batch (F3).

Migrated from `xlsx_add_comment.py` F3 region during Task 002.

Public API:
    BatchRow            — dataclass(cell, text, author, initials, threaded).
    load_batch(path_or_dash, default_author, default_threaded)
        -> tuple[list[BatchRow], int]
        Reads --batch JSON (or stdin via "-"), enforces 8 MiB
        pre-parse cap (BatchTooLarge), auto-detects flat-array vs
        xlsx-7 envelope shape (InvalidBatchInput on anything else),
        hydrates uniformly to BatchRow list. Skips group-findings
        (`row: null`) and counts them in the second tuple element.

Per TASK 002 §2.5 row 5, BatchRow is NOT re-exported on the
xlsx_add_comment.py shim (Q5 closure — programmatic callers use
the explicit `from xlsx_comment.batch import BatchRow` path).
Only `load_batch` is on the shim re-export contract. The F6 region
still in the shim references BatchRow via an F6-region-local import
(per m3 plan-review fix); that local import is removed in Task 002.9.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .cli_helpers import _initials_from_author
from .constants import BATCH_MAX_BYTES
from .exceptions import (
    BatchTooLarge, InvalidBatchInput, MissingDefaultAuthor,
)

__all__ = ["BatchRow", "load_batch"]


@dataclass(frozen=True)
class BatchRow:
    """One row of a --batch input, normalised across both shapes."""

    cell: str
    text: str
    author: str
    initials: str | None
    threaded: bool


_BATCH_CAP_BYTES = BATCH_MAX_BYTES  # m2 / m-4 boundary


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

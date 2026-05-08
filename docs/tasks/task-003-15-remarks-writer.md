# Task 003.15: `remarks_writer.py` (F10 — full + dual-stream M-1 streaming)

## Use Case Connection
- **I6.1, I6.2, I6.3** (output-copy + remark allocation; mode `replace`/`append`/`new`; streaming output).
- **R8.a–R8.g** (output workbook + remark column; M-1 dual-stream).

## Task Goal
Implement F10 — write a copy of the input workbook with optional remark column. Two write paths: full-fidelity (default; openpyxl `load_workbook` + per-cell write + `save()`) and streaming (`--streaming-output`; **architect-locked M-1 dual-stream design**: `read_only=True` source iter + `WriteOnlyWorkbook` dest, single pass each, remark column letter need not be rightmost).

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_check_rules/remarks_writer.py`

```python
"""F10 — Workbook output writer (remarks column).

Two paths:
  - Full-fidelity (`write_remarks`): openpyxl load_workbook + per-cell
    write + save. Preserves comments/drawings/charts/defined names on
    cells NOT modified by xlsx-7 (R8.g).
  - Streaming (`write_remarks_streaming`): M-1 architect-locked dual-
    stream design. Open source via load_workbook(read_only=True),
    dest via WriteOnlyWorkbook. Per source row, build
    [cell_or_remark for col in range(1, max_col_or_remark_idx+1)]
    and append. Remark column letter need NOT be rightmost.

Same-path guard (cross-7 H1): Path.resolve() on input vs output;
exit 6 SelfOverwriteRefused.
"""
from __future__ import annotations
from pathlib import Path
from typing import Iterable
from openpyxl import load_workbook, Workbook
from openpyxl.styles import PatternFill
from openpyxl.utils import column_index_from_string, get_column_letter
from .evaluator import Finding
from .exceptions import SelfOverwriteRefused

__all__ = [
    "write_remarks", "write_remarks_streaming",
    "allocate_remark_column", "apply_remark_mode",
    "apply_pattern_fill", "assert_distinct_paths",
]

# PatternFill colours per severity (R8.d)
_FILL_ERROR = PatternFill(start_color="FFFFC7CE", end_color="FFFFC7CE", fill_type="solid")  # red
_FILL_WARNING = PatternFill(start_color="FFFFEB9C", end_color="FFFFEB9C", fill_type="solid")  # yellow
_FILL_INFO = PatternFill(start_color="FFB7DEE8", end_color="FFB7DEE8", fill_type="solid")  # blue

def assert_distinct_paths(input_path: Path, output_path: Path) -> None:
    """cross-7 H1 — Path.resolve() with symlink follow.
    TOCTOU between resolve() and open() is honest scope (xlsx-6 parity).
    """
    if input_path.resolve() == output_path.resolve():
        raise SelfOverwriteRefused(
            f"--output resolves to the same path as input: {input_path.resolve()}",
            subtype="SelfOverwriteRefused",
        )

def allocate_remark_column(sheet, mode: str, explicit: str | None,
                            existing_max_col: int) -> str:
    """SPEC §8.1 — auto / LETTER / HEADER. Returns column letter."""
    if mode == "auto":
        return get_column_letter(existing_max_col + 1)
    if explicit and len(explicit) <= 3 and explicit.isalpha() and explicit.isupper():
        return explicit  # treat as letter
    # else treat as header — find or append
    raise NotImplementedError

def apply_remark_mode(existing_value: str | None, new_message: str,
                       mode: str, severity: str) -> str:
    """replace / append / new (new uses _2 suffix at column-allocation time;
    here we just write the new_message)."""
    if mode == "replace" or existing_value is None:
        return new_message
    if mode == "append":
        return f"{existing_value}\n{new_message}"
    if mode == "new":
        return new_message  # column already disambiguated to LETTER_2
    raise ValueError(f"unknown mode: {mode}")

def apply_pattern_fill(cell, severity: str) -> None:
    fills = {
        "error": _FILL_ERROR,
        "warning": _FILL_WARNING,
        "info": _FILL_INFO,
    }
    cell.fill = fills.get(severity, _FILL_INFO)

def write_remarks(input_path: Path, output_path: Path,
                   findings_per_cell: dict, opts) -> None:
    """Full-fidelity write path. R8.a/b/c/d/g."""
    assert_distinct_paths(input_path, output_path)
    wb = load_workbook(input_path)
    for sheet in wb.worksheets:
        # ... per-sheet processing ...
        pass
    wb.save(output_path)

def write_remarks_streaming(input_path: Path, output_path: Path,
                              findings_per_cell: dict, opts) -> None:
    """M-1 architect-locked dual-stream design.
    Single-pass over source (read_only=True iter_rows), single-pass to
    dest (WriteOnlyWorkbook). Remark column letter need NOT be rightmost.
    """
    assert_distinct_paths(input_path, output_path)
    src = load_workbook(input_path, read_only=True, data_only=False)
    dst = Workbook(write_only=True)
    for src_sheet in src.worksheets:
        dst_sheet = dst.create_sheet(title=src_sheet.title)
        remark_col_letter = opts.remark_column or "A"  # streaming requires explicit
        remark_col_idx = column_index_from_string(remark_col_letter)
        src_max_col = src_sheet.max_column or 1
        max_idx = max(src_max_col, remark_col_idx)
        for src_row_idx, src_row in enumerate(src_sheet.iter_rows(values_only=False), start=1):
            row_vec = []
            for col_idx in range(1, max_idx + 1):
                col_letter = get_column_letter(col_idx)
                cell_key = (src_sheet.title, src_row_idx, col_letter)
                if col_idx == remark_col_idx and cell_key in findings_per_cell:
                    msg = "; ".join(f.message for f in findings_per_cell[cell_key])
                    row_vec.append(msg)
                elif col_idx <= src_max_col and (col_idx - 1) < len(src_row):
                    row_vec.append(src_row[col_idx - 1].value)
                else:
                    row_vec.append(None)  # extending past source max_col
            dst_sheet.append(row_vec)
    dst.save(output_path)
```

#### File: `skills/xlsx/scripts/xlsx_check_rules/cli.py`

Wire `--output` paths into `_run` after evaluation: route to `write_remarks` (full-fidelity, default) or `write_remarks_streaming` (when `--streaming-output`). Same-path guard runs BEFORE `write_remarks_streaming` opens the source (otherwise the source open could fail with a more confusing error).

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Remove `@unittest.skip` from `TestRemarksWriter`. Critical tests:
- `test_full_fidelity_round_trip_preserves_comments` — input with cell comments on un-modified cells; output has same comments byte-equivalent (R8.g).
- `test_remark_column_auto_picks_first_free` — input with data in A..F; `--remark-column auto` picks G.
- `test_remark_column_explicit_letter` — `--remark-column Z` writes to Z.
- `test_remark_column_mode_new_appends_underscore_2` — input already has Remarks column; `--remark-column-mode new` (default) writes to `Remarks_2`.
- `test_remark_column_mode_replace_overwrites` — existing remarks discarded.
- `test_remark_column_mode_append_concatenates` — existing + newline + new.
- `test_pattern_fill_red_for_error` — error finding cell has `_FILL_ERROR`.
- `test_pattern_fill_yellow_for_warning`.
- **`test_m1_dual_stream_remark_column_NOT_rightmost`** (architect-lock M-1 anchor) — input with data in A..F; `--remark-column B --streaming-output --remark-column-mode replace`; output has the original A, the **new remark in B**, and the original C..F intact. Locks the dual-stream design that lets B (not the rightmost) be the remark column.
- `test_streaming_remark_past_max_col` — `--remark-column J` with input only A..F → output has empty G..I + remark in J.
- `test_same_path_exits_6` (fixture #37) — `--output INPUT` → `SelfOverwriteRefused`.
- `test_same_path_via_symlink_exits_6` — symlink in `--output` path resolving to input → exit 6.

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Append fixtures #32 (streaming), #32a (incompatible auto), #32b (incompatible append), #32c (streaming replace explicit Z), #34 (round-trip remarks), #35 (re-run suffix), #37 (same-path).

## Test Cases
- Unit: ~ 12 new tests; all pass.
- Battery: fixtures #32, #32a, #32b, #32c, #34, #35, #37 transition from xfail to xpass.

## Acceptance Criteria
- [ ] `remarks_writer.py` complete (≤ 350 LOC).
- [ ] **M-1 architect-lock test green** (`test_m1_dual_stream_remark_column_NOT_rightmost`).
- [ ] Full-fidelity round-trip preserves comments / drawings / charts / defined names on un-modified cells.
- [ ] Streaming path single-pass each direction.
- [ ] cross-7 H1 same-path guard works including symlinks.
- [ ] All `TestRemarksWriter` tests green.
- [ ] `validate_skill.py` exits 0.

## Notes
- For `test_full_fidelity_round_trip_preserves_comments`: prepare input via openpyxl with `cell.comment = Comment("note", "author")`; assert output's same cell has the same comment text and author.
- The `_FILL_*` colour codes match xlsx-6's convention (red=error, yellow=warning, blue=info). If openpyxl rejects the colour codes above, swap to `start_color="C7CE"` form.
- WriteOnlyWorkbook **does not support per-cell styles like `PatternFill`** in some openpyxl versions — the streaming path's "fidelity trade-off" (SPEC §11.2) is precisely that PatternFill MAY degrade in streaming mode. Document with a stderr warning when `--streaming-output` is set: `WARNING: streaming-output mode does not support cell formatting; remark messages will be plain text.`
- For symlink testing: create a temp symlink with `Path.symlink_to`; `Path.resolve()` follows it.

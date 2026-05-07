# Task 1.01: [STUB CREATION] `xlsx_add_comment.py` skeleton + CLI flags

## Use Case Connection
- I1.1, I1.2, I1.3, I1.4, I1.5, I2.1, I2.2, I2.3, I3.1 — establishes the surface that all later logic tasks fill in.
- RTM: prepares R1, R2, R3, R4, R7 surface.

## Task Goal
Create `skills/xlsx/scripts/xlsx_add_comment.py` with the full argparse CLI surface from TASK §2.5, all helper-function stubs (return hardcoded values or raise `NotImplementedError`), full module docstring (mirroring `docx_add_comment.py`'s 80+ line docstring), and importable `main(argv)` entry point. After this task, `python3 xlsx_add_comment.py --help` MUST work, and `python3 xlsx_add_comment.py FIXTURE.xlsx /tmp/out.xlsx --cell A5 --author "Q" --text "msg"` MUST exit 0 producing a hardcoded "stub" output (a copy of the input is acceptable).

## Changes Description

### New Files
- `skills/xlsx/scripts/xlsx_add_comment.py` — single-file CLI, ≥ 250 LOC including docstring + argparse + stubs. Sections delimited by `# region` markers per ARCHITECTURE §3.1.

### Changes in Existing Files
*(none — Stage 1 file structure only)*

### Module skeleton (concrete shape)

```python
"""Insert an Excel comment into a target cell..."""  # 80+ line docstring mirroring docx_add_comment.py
from __future__ import annotations
import argparse, json, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
from lxml import etree
from _errors import add_json_errors_argument, report_error
from office._encryption import EncryptedFileError, assert_not_encrypted
from office._macros import warn_if_macros_will_be_dropped
from office.pack import pack
from office.unpack import unpack

# region Namespaces and content-type constants
SS_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
THREADED_NS = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"
# ... (full set per ARCHITECTURE §4.1)
# endregion

# region F2 — Cell-syntax parser
def parse_cell_syntax(text: str) -> tuple[str | None, str]:
    """Parse '--cell' value into (sheet_name|None, cell_ref)."""
    raise NotImplementedError("Implemented in task 2.02")

def resolve_sheet(workbook_xml_root, qualified_or_none, sheet_visibility=None):
    """Return target sheet name; first-VISIBLE if unqualified."""
    raise NotImplementedError("Implemented in task 2.02")
# endregion

# region F3 — Batch loader
def load_batch(path_or_dash: str, default_author: str | None, default_threaded: bool) -> list:
    raise NotImplementedError("Implemented in task 2.06")
# endregion

# region F4 — OOXML editor stubs (all NotImplementedError; impl in 2.03/2.04/2.05)
def scan_idmap_used(tree) -> set[int]: raise NotImplementedError
def scan_spid_used(tree) -> set[int]: raise NotImplementedError
def next_part_counter(tree, pattern: str) -> int: raise NotImplementedError
def ensure_legacy_comments_part(tree, sheet_name): raise NotImplementedError
def ensure_threaded_comments_part(tree, sheet_name): raise NotImplementedError
def ensure_person_list(tree): raise NotImplementedError
def ensure_vml_drawing(tree, sheet_name, idmap_data): raise NotImplementedError
def add_legacy_comment(part, ref, author, text): raise NotImplementedError
def add_threaded_comment(part, ref, person_id, text, date_iso) -> str: raise NotImplementedError
def add_person(part, display_name) -> str: raise NotImplementedError
def add_vml_shape(part, ref, spid, sheet_index): raise NotImplementedError
# endregion

# region F5 — Merged-cell resolver
def resolve_merged_target(sheet_xml_root, ref: str, allow_redirect: bool) -> str:
    raise NotImplementedError("Implemented in task 2.07")
# endregion

# region F1 — Argparse
def build_parser() -> argparse.ArgumentParser:
    """Full TASK §2.5 surface; mutex MX-A/MX-B; dependency DEP-1..4."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cell", default=None)
    parser.add_argument("--text", default=None)
    parser.add_argument("--author", default=None)
    parser.add_argument("--initials", default=None)
    parser.add_argument("--threaded", action="store_true")
    parser.add_argument("--no-threaded", dest="no_threaded", action="store_true")
    parser.add_argument("--date", default=None, help="ISO-8601 timestamp; default = UTC now (Q5)")
    parser.add_argument("--batch", default=None)
    parser.add_argument("--default-author", default=None)
    parser.add_argument("--default-threaded", action="store_true")
    parser.add_argument("--allow-merged-target", action="store_true")
    add_json_errors_argument(parser)
    return parser
# endregion

# region F6 — main()
def main(argv=None) -> int:
    """STUB: copy input to output, return 0. Real impl in 2.01..2.08."""
    args = build_parser().parse_args(argv)
    # STUB: trivial copy for stub-stage E2E green-on-stubs
    Path(args.output).write_bytes(Path(args.input).read_bytes())
    return 0
# endregion

if __name__ == "__main__":
    sys.exit(main())
```

### Component Integration
- `_errors`, `office._encryption`, `office._macros`, `office.pack`, `office.unpack` are existing modules — imports already work in `skills/xlsx/scripts/`.
- Script lives next to existing CLIs (csv2xlsx, xlsx_add_chart, xlsx_recalc, xlsx_validate).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01:** `python3 xlsx_add_comment.py --help` exits 0 and prints "Insert an Excel comment".
   - Note: stub stage — only argparse exists.
2. **TC-E2E-02:** `python3 xlsx_add_comment.py examples/fixture.csv.xlsx /tmp/out.xlsx --cell A5 --author "Q" --text "msg"` exits 0 and `/tmp/out.xlsx` exists with `len(read_bytes) > 0`.
   - Note: at stub stage, the script just copies input → output. Real assertions arrive in 2.04.

### Unit Tests
*(not in this task — see 1.03)*

### Regression Tests
- Existing `tests/test_e2e.sh` (csv2xlsx, xlsx_recalc, xlsx_validate, xlsx_add_chart paths) MUST stay green.

## Acceptance Criteria
- [ ] `xlsx_add_comment.py` exists with the skeleton above.
- [ ] All flags in TASK §2.5 are declared in `build_parser()`.
- [ ] All F2..F5 helpers are stubbed with `NotImplementedError` and a TODO referencing the task that implements them.
- [ ] `main()` produces a valid copy-of-input output file (so E2E in 1.02 has a green-on-stub baseline).
- [ ] Module docstring is present and ≥ 80 lines (mirrors docx_add_comment.py shape).
- [ ] `python3 xlsx_add_comment.py --help` exits 0.
- [ ] Existing test_e2e.sh still passes.
- [ ] No edits to `skills/docx/scripts/office/` (CLAUDE.md §2 — verify with `diff -qr office ../../docx/scripts/office`).

## Notes
- Mutex MX-A/MX-B and DEP-1..4 enforcement is INTENTIONALLY deferred to task 2.01 — at stub stage the parser accepts any combination so that 1.02's red-on-stub tests can declare-then-assert later.
- `_errors.add_json_errors_argument` is the existing helper — do NOT redefine.

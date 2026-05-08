# Task 003.06: `ast_nodes.py` (F4 — closed 17-type AST + RuleSpec + canonical-str)

## Use Case Connection
- **R1.e** (closed 17-node AST whitelist).
- **R10.a** (canonical key for §5.5.3 cache normalisation — `to_canonical_str`).

## Task Goal
Implement F4 — the type vocabulary consumed by F3 (parser), F7 (evaluator), and F8 (cache canonical key). 17 node dataclasses + `RuleSpec` wrapper + `to_canonical_str(node)` for SHA-1 cache-key inputs. Pure data; zero logic; no openpyxl, no `regex`, no I/O.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_check_rules/ast_nodes.py`

Implement per ARCHITECTURE §2.1 F4 + §3.2 row:

```python
"""F4 — Closed 17-node AST type vocabulary.

Consumed by F3 (parser), F7 (evaluator), F8 (aggregate cache).
Pure data; no logic. `to_canonical_str(node)` produces the
canonical string used as input to the SHA-1 cache key in F8.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from .constants import COMPOSITE_MAX_DEPTH

__all__ = [
    # Leaf types
    "Literal", "CellRef", "RangeRef", "ColRef", "MultiColRef",
    "RowRef", "SheetRef", "NamedRef", "TableRef",
    # Operators
    "BinaryOp", "UnaryOp", "BuiltinCall",
    # Set ops
    "In", "Between",
    # Logical
    "Logical",
    # Predicates
    "TypePredicate", "RegexPredicate", "LenPredicate",
    "StringPredicate", "DatePredicate",
    # Group-by
    "GroupByCheck",
    # Top-level wrapper
    "RuleSpec",
    # Helper
    "to_canonical_str",
]

@dataclass(frozen=True)
class Literal:
    value: Any  # int, float, str, bool, None, ISO date string

@dataclass(frozen=True)
class CellRef:
    sheet: str | None
    ref: str  # "A5"

@dataclass(frozen=True)
class RangeRef:
    sheet: str | None
    start: str
    end: str

@dataclass(frozen=True)
class ColRef:
    sheet: str | None
    name_or_letter: str
    is_letter: bool  # True for col:B, False for col:Hours

# ... (similar for MultiColRef, RowRef, SheetRef, NamedRef, TableRef)

@dataclass(frozen=True)
class BinaryOp:
    op: str  # one of "==", "!=", "<", "<=", ">", ">=", "+", "-", "*", "/"
    left: "AnyNode"
    right: "AnyNode"

@dataclass(frozen=True)
class UnaryOp:
    op: str  # "-" or "not"
    operand: "AnyNode"

@dataclass(frozen=True)
class BuiltinCall:
    name: str  # validated against BUILTIN_WHITELIST
    args: tuple["AnyNode", ...]

@dataclass(frozen=True)
class In:
    needle: "AnyNode"
    haystack: tuple[Any, ...]
    negate: bool

@dataclass(frozen=True)
class Between:
    operand: "AnyNode"
    low: float
    high: float
    inclusive: bool

@dataclass(frozen=True)
class Logical:
    op: str  # "and" / "or" / "not"
    children: tuple["AnyNode", ...]
    depth: int  # validated ≤ COMPOSITE_MAX_DEPTH at parse

@dataclass(frozen=True)
class TypePredicate:
    name: str  # "is_number" / "is_date" / "is_text" / "is_bool" / "is_error" / "required"

@dataclass(frozen=True)
class RegexPredicate:
    pattern: str
    unsafe_regex: bool = False  # rule-level opt-out of D5 lint

@dataclass(frozen=True)
class LenPredicate:
    op: str  # "<", "<=", ...
    n: int

@dataclass(frozen=True)
class StringPredicate:
    name: str  # "starts_with" / "ends_with" / "not_empty"
    arg: str = ""

@dataclass(frozen=True)
class DatePredicate:
    name: str  # "date_in_month" / "date_in_range" / "date_before" / "date_after" / "date_weekday"
    args: tuple[str, ...]  # always strings; eval-time parses

@dataclass(frozen=True)
class GroupByCheck:
    fn: str  # "sum_by" / "count_by" / "avg_by"
    key: str  # column header or letter
    op: str  # comparison operator
    rhs: "AnyNode"

# ScopeNode = ColRef | RangeRef | CellRef | RowRef | SheetRef | NamedRef | TableRef | MultiColRef
# AnyNode = ScopeNode | Literal | BinaryOp | UnaryOp | BuiltinCall | In | Between | Logical
#         | TypePredicate | RegexPredicate | LenPredicate | StringPredicate | DatePredicate
#         | GroupByCheck

@dataclass(frozen=True)
class RuleSpec:
    id: str
    scope: "ScopeNode"
    check: "AnyNode"
    severity: str = "error"  # one of SEVERITY_LEVELS
    message: str | None = None
    when: "AnyNode | None" = None
    skip_empty: bool = True
    tolerance: float = 1e-9
    header_row: int | None = None
    visible_only: bool | None = None
    treat_numeric_as_date: bool | None = None
    treat_text_as_date: bool | None = None
    unsafe_regex: bool = False  # rule-level D5 opt-out

def to_canonical_str(node: Any) -> str:
    """Produce the canonical string consumed by the F8 cache SHA-1.
    Folds whitespace and quote-style; resolves sheet qualifier (caller
    must pre-resolve default sheet); resolves header→letter (caller
    pre-resolves Table-fallback equivalence). The result is suitable
    as input to hashlib.sha1.
    """
    # Type-dispatched serialisation; deterministic across runs.
    # See SPEC §5.5.3 cache canonicalisation for the rules.
    ...
```

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Remove `@unittest.skip` from `TestAstNodes`. Add:
- `test_all_17_types_are_frozen_dataclasses` — assert each is `@dataclass(frozen=True)` (immutability invariant).
- `test_to_canonical_str_deterministic` — same input → same output across runs.
- `test_to_canonical_str_normalises_whitespace` — `sum( col:Hours )` and `sum(col:Hours)` produce same canonical string.
- `test_to_canonical_str_normalises_quote_style` — `'Sheet1'!col:H` and `Sheet1!col:H` produce same canonical string when sheet name is unambiguous.
- `test_logical_depth_field_present` — `Logical.depth` exists and is set by callers.
- `test_rulespec_defaults_match_spec` — severity="error", skip_empty=True, tolerance=1e-9, etc.
- `test_no_imports_from_dsl_parser_or_evaluator` — assert `ast_nodes.py` does not import from `dsl_parser` or `evaluator` (one-way dataflow gate).

## Test Cases
- Unit: ~ 7 new tests; all pass.
- Regression: xlsx-6 + earlier xlsx-7 tests still green.

## Acceptance Criteria
- [ ] All 17 node types + `RuleSpec` defined as frozen dataclasses.
- [ ] `to_canonical_str` implemented with deterministic, whitespace/quote-folding behaviour.
- [ ] `TestAstNodes` un-skipped and passing.
- [ ] No imports from `dsl_parser` / `evaluator` (one-way dataflow gate).
- [ ] LOC ≤ 250.
- [ ] `validate_skill.py` exits 0.

## Notes
- The `to_canonical_str` semantics are subtle. The full rules are in SPEC §5.5.3. Implementation hint: use `repr`-style dispatch with explicit ordering of children for `Logical(and/or)` (children sorted by `to_canonical_str`); `BinaryOp` does NOT sort (order matters for `<`).
- Header→letter and Table-fallback resolution happen BEFORE `to_canonical_str` is called (the caller in F8 does the resolution; F4 sees the resolved form).
- This module is the test-compat surface anchor — its `__all__` symbols are re-exported by the shim. Adding a 18th type would be a breaking change requiring a TASK update.

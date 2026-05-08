# Task 003.11: `evaluator.py` (F7 — rule evaluator + Template messages)

## Use Case Connection
- **I3.1–I3.7** (compare, type guards, text+regex, dates, composite eval).
- **I3.8** (pre-rule cell triage + cached-value preflight).
- **R2.e** (D4 cell-error auto-emit).
- **R4.a–R4.h** (check vocabulary).
- **R9.c, R9.d** (regex compile cache; per-cell timeout → `rule-eval-timeout` finding).

## Task Goal
Implement F7 — evaluate AST nodes against `ClassifiedCell` values and produce findings. Includes the §5.0 cell triage that auto-emits `cell-error` for D4-recognised error cells (and short-circuits other rules), the §5.0.1 stale-cache warning, and the `string.Template` message formatter.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_check_rules/evaluator.py`

```python
"""F7 — Rule evaluator.

Walks the AST against per-cell values; produces Finding objects.
Includes §5.0 pre-rule cell triage (error cells short-circuit; empty
cells skip per skip_empty), §5.0.1 stale-cache one-time warning,
per-cell regex timeout (R9.d), and string.Template message formatter
(R9 / SPEC §6.3 — NOT str.format, format-string-injection guard).
"""
from __future__ import annotations
import string
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterator
from regex import compile as regex_compile  # PyPI `regex`, NOT stdlib re
from .ast_nodes import (
    Literal, CellRef, ColRef, BinaryOp, UnaryOp, BuiltinCall,
    In, Between, Logical, TypePredicate, RegexPredicate,
    LenPredicate, StringPredicate, DatePredicate, RuleSpec,
)
from .cell_types import LogicalType, ClassifiedCell
from .constants import DEFAULT_REGEX_TIMEOUT_MS, OPENPYXL_ERROR_CODES
from .exceptions import RuleEvalError, AggregateTypeMismatch, CellError

__all__ = [
    "Finding", "EvalContext", "eval_rule", "eval_check",
    "eval_regex", "eval_arithmetic", "format_message",
]

@dataclass
class Finding:
    cell: str  # "Sheet!Ref" for per-cell; bare sheet for grouped
    sheet: str
    row: int | None  # null for grouped findings (M2 envelope)
    column: str | None  # null for grouped findings
    rule_id: str
    severity: str
    value: Any
    message: str
    expected: Any | None = None  # only set when computable RHS
    tolerance: float | None = None  # only set when consumed
    group: str | None = None  # set for *_by: aggregates

@dataclass
class EvalContext:
    workbook: Any  # openpyxl Workbook (read-only)
    rule: RuleSpec
    aggregate_cache: Any  # F8 cache; passed in by F11 orchestrator
    regex_compile_cache: dict[str, Any] = field(default_factory=dict)
    stale_cache_warned: bool = False
    regex_timeouts: int = 0
    eval_errors: int = 0
    cell_errors: int = 0
    skipped_in_aggregates: int = 0
    aggregate_cache_hits: int = 0

def eval_rule(rule_spec: RuleSpec, scope_result, ctx: EvalContext) -> Iterator[Finding]:
    """Outer loop over scope's cells. Triage per §5.0; emit findings."""
    raise NotImplementedError

def eval_check(node, classified_cell: ClassifiedCell, ctx: EvalContext) -> bool | Finding:
    """Dispatch on AST type. Returns True/False for the predicate, OR
    a synthetic Finding (rule-eval-timeout / rule-eval-error / etc.).
    """
    raise NotImplementedError

def eval_regex(pattern: str, value: str, timeout_ms: int,
                ctx: EvalContext, rule_id: str) -> bool | Finding:
    """R9.c + R9.d. Compile once per pattern (cache); timeout per cell."""
    raise NotImplementedError

def eval_arithmetic(binop: BinaryOp, left: Any, right: Any,
                     ctx: EvalContext) -> Any:
    """SPEC §5.5.2: +/-/*/. No **, no %, no bitwise (parse-blocked).
    Date arithmetic between two dates -> Finding(rule-eval-error).
    Division by zero -> Finding(rule-eval-error).
    """
    raise NotImplementedError

def format_message(template_str: str | None, classified_cell: ClassifiedCell,
                    rule_id: str, value: Any, group: str | None = None) -> str:
    """Use string.Template (NOT str.format) per SPEC §6.3.
    Substitutions: $value, $row, $col, $cell, $sheet, $group.
    Unknown placeholders pass through literally (Template default behavior).
    """
    if template_str is None:
        template_str = f"rule {rule_id} failed"
    t = string.Template(template_str)
    mapping = {
        "value": str(value),
        "row": str(classified_cell.row) if classified_cell else "",
        "col": classified_cell.col if classified_cell else "",
        "cell": (f"{classified_cell.sheet}!{classified_cell.col}{classified_cell.row}"
                 if classified_cell else ""),
        "sheet": classified_cell.sheet if classified_cell else "",
        "group": str(group) if group is not None else "",
    }
    return t.safe_substitute(mapping)
```

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Remove `@unittest.skip` from `TestEvaluator`. Add:
- `test_eval_compare_value_gt_zero` — `value > 0` against numeric `5` → `True`.
- `test_eval_in_list` — `value in [Approved, Pending]` against `"Pending"` → `True`.
- `test_eval_type_guard_is_number_against_text_42` — `is_number` against text `"42"` → `False` (R2.b lock).
- `test_eval_required` — `required` against empty cell → `False`.
- `test_eval_regex_with_timeout_emits_finding` — `^(a+)+$` (with `unsafe_regex=True` to bypass parse lint) against `"aaaa!"` → emits `Finding(rule_id=rule.id, message="regex evaluation timed out")` and increments `ctx.regex_timeouts`.
- `test_eval_regex_compile_cache_one_per_pattern` — same pattern across 100 cells compiles `regex` ONCE (assert `len(ctx.regex_compile_cache) == 1`).
- `test_eval_cell_error_auto_emit_d4_seven_codes` — `#REF!` cell → synthetic `cell-error` finding; other rules on the cell are skipped.
- `test_eval_cell_error_modern_codes_text_no_auto_emit` (D4 honest scope) — `"#SPILL!"` text cell → no `cell-error`; rules run normally against it as `text`.
- `test_format_message_string_template_not_format` — message `"got: ${value} from ${cell}"` interpolates safely; `"got: {0.__class__.__mro__}"` does NOT execute attribute access (lock R9 / SPEC §6.3).
- `test_format_message_unknown_placeholder_passes_through` — `"$frob"` stays literal `$frob`.
- `test_eval_arithmetic_division_by_zero_emits_finding` — `value / 0` → `Finding(rule-eval-error)` not crash.
- `test_eval_arithmetic_date_minus_date_emits_finding` — `cell:D1 - cell:D2` (both dates) → `Finding(rule-eval-error)`.
- `test_eval_composite_and_short_circuits_on_first_false` — `and: [false, expensive]` does not evaluate the expensive child.
- `test_stale_cache_warning_emitted_once` — fixture #14 (formulas-no-cache); warning fires for first cell only; `ctx.stale_cache_warned` set.

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Append fixtures #2, #11, #14, #15, #16, #17, #29.

## Test Cases
- Unit: ~ 15 new tests; all pass.
- Battery: fixtures #2, #10, #10b, #11, #14, #15, #16, #17 transition from xfail to xpass for the evaluator layer.

## Acceptance Criteria
- [ ] `evaluator.py` complete (≤ 450 LOC).
- [ ] `string.Template` used (NOT `str.format`).
- [ ] `regex` PyPI lib imported (NOT `import re` — except in dsl_parser for parse-time lint).
- [ ] Per-cell timeout = 100 ms; emits `rule-eval-timeout` Finding on overflow.
- [ ] D4 7-code auto-emit honoured; modern codes do not auto-emit.
- [ ] All `TestEvaluator` tests green.
- [ ] `validate_skill.py` exits 0.

## Notes
- The `eval_check` dispatcher uses `match`/`case` (Python 3.10+) for AST node dispatch — concise and matches the closed-set design.
- `regex_compile_cache` is on `EvalContext` (not module-global) so concurrent runs (theoretical; xlsx-7 is single-threaded by design) don't cross-contaminate. Tests for the cache use the ctx directly.
- For the `rule-eval-timeout` finding: the `regex` lib raises `TimeoutError` (Python builtin) when the matcher exceeds wall-clock. `eval_regex` catches that and returns a synthetic `Finding`; the caller `eval_check` propagates the Finding instead of `True`/`False`.
- Stale-cache warning is emitted to stderr from `eval_rule` (the outer loop) when `classified_cell.has_formula_no_cache` and `not ctx.stale_cache_warned`. After emission, set `ctx.stale_cache_warned = True`.

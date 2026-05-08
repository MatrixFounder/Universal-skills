# Task 003.10: `dsl_parser.py` (F3 — recursive-descent parser + ReDoS lint)

## Use Case Connection
- **I1.2** (hand-written DSL parser).
- **R1.d–R1.g** (no `ast.parse`, closed 17-AST whitelist, composite depth cap, builtin whitelist).
- **R9.a, R9.b** (regex compile, D5 ReDoS lint).
- **R4.c** (text rules + regex hardening).

## Task Goal
Implement F3 — hand-written recursive-descent parser over the §5 SPEC grammar. Builds 17-node AST trees from `RuleSpec.check`/`scope` strings. Enforces composite depth cap 16, builtin whitelist (12 names), and the D5 4-shape ReDoS lint at parse time.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_check_rules/dsl_parser.py`

```python
"""F3 — DSL parser & AST builder.

Hand-written recursive-descent over the SPEC §5 grammar. NEVER calls
`ast.parse` (would expose Python-syntax surface). NO attribute access,
no `**`, no `%`, no bitwise, no lambda — these tokens raise
RulesParseError(BadGrammar).

D5 ReDoS lint: at parse time, regex patterns are checked against the
4-shape REDOS_REJECT_PATTERNS hand-coded reject-list. `recheck`
(JVM CLI) is NOT used.
"""
from __future__ import annotations
import re as _re_stdlib  # ONLY for parse-time pattern lint, NEVER for rule eval
from typing import Any
from .ast_nodes import (
    Literal, CellRef, RangeRef, ColRef, MultiColRef, RowRef,
    SheetRef, NamedRef, TableRef, BinaryOp, UnaryOp, BuiltinCall,
    In, Between, Logical, TypePredicate, RegexPredicate,
    LenPredicate, StringPredicate, DatePredicate, GroupByCheck,
    RuleSpec,
)
from .constants import (
    BUILTIN_WHITELIST, COMPOSITE_MAX_DEPTH, REDOS_REJECT_PATTERNS,
)
from .exceptions import RulesParseError, RegexLintFailed

__all__ = [
    "parse_check", "parse_scope", "parse_composite",
    "validate_builtin", "lint_regex", "build_rule_spec",
]

class _Tokenizer:
    """Minimal hand-written tokenizer for DSL strings."""
    # tokens: NUMBER, STRING, IDENT, LPAREN, RPAREN, LBRACK, RBRACK,
    # COMMA, COLON, OP (==/!=/<=/>=/</>/+/-/*/), DOT (rejected),
    # BANG (rejected unless inside string), KEYWORD (in / not / and / or)
    ...

def parse_check(text: str, depth: int = 0) -> Any:
    """Parse a string-form `check` field. Object-form (composite) goes
    through parse_composite. Raises RulesParseError on grammar errors."""
    raise NotImplementedError

def parse_composite(d: dict, depth: int = 0) -> Logical:
    """Parse object form: {and: [...]}, {or: [...]}, {not: ...}.
    Raises CompositeDepth if depth > COMPOSITE_MAX_DEPTH."""
    if depth > COMPOSITE_MAX_DEPTH:
        raise RulesParseError(
            f"composite depth > {COMPOSITE_MAX_DEPTH}",
            subtype="CompositeDepth", depth=depth,
        )
    raise NotImplementedError

def parse_scope(text: str) -> Any:
    """Parse a scope string into a ScopeNode (CellRef/RangeRef/...).
    Handles sheet qualifier (delegates to scope_resolver.parse_sheet_qualifier)."""
    raise NotImplementedError

def validate_builtin(name: str) -> None:
    """Raise UnknownBuiltin if name not in BUILTIN_WHITELIST."""
    if name not in BUILTIN_WHITELIST:
        raise RulesParseError(
            f"unknown builtin: {name!r}",
            subtype="UnknownBuiltin", name=name,
        )

def lint_regex(pattern: str, unsafe_regex: bool = False) -> None:
    """D5 closure (architect-review m1): hand-coded reject-list for
    the 4 classic ReDoS shapes is the SOLE parse-time check.
    `recheck` is not used. Per-cell timeout in F7 is the runtime
    safety net.

    `unsafe_regex=True` opts out of the parse-time lint (still subject
    to the per-cell timeout).
    """
    if unsafe_regex:
        return
    for shape in REDOS_REJECT_PATTERNS:
        if _re_stdlib.search(shape, pattern):
            raise RegexLintFailed(
                f"regex matches catastrophic-backtracking shape: {shape}",
                subtype="ReDoSLint", pattern=pattern, shape=shape,
            )

def build_rule_spec(d: dict) -> RuleSpec:
    """Top-level: dict from rules-file -> RuleSpec dataclass.
    Calls parse_check, parse_scope, lint_regex as needed.
    Raises RulesParseError on missing required fields (id, scope, check).
    """
    raise NotImplementedError
```

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Remove `@unittest.skip` from `TestDslParser`. Add:
- `test_no_ast_parse_in_module` — grep test.
- `test_simple_compare_parses` — `"value > 0"` → `BinaryOp("==>", left=value-ref, right=Literal(0))`.
- `test_in_list_parses` — `"value in [Approved, Pending, Rejected]"` → `In(needle=..., haystack=("Approved","Pending","Rejected"), negate=False)`.
- `test_between_parses` — `"between:0,24"` → `Between(...)`.
- `test_aggregate_parses` — `"sum(col:Hours)"` → `BuiltinCall("sum", (ColRef(...),))`.
- `test_aggregate_unknown_builtin_raises` — `"foo(col:X)"` → `RulesParseError(UnknownBuiltin)`.
- `test_composite_and_parses` — `{"and": ["a", "b"]}` → `Logical("and", (..., ...), depth=1)`.
- `test_composite_depth_capped` — 17-level nesting → `RulesParseError(CompositeDepth)`.
- `test_attribute_access_rejected` — `"value.__class__"` → `RulesParseError(BadGrammar)`.
- `test_power_operator_rejected` — `"value ** 2"` → `RulesParseError(BadGrammar)`.
- `test_modulo_operator_rejected` — `"value % 2"` → `RulesParseError(BadGrammar)`.
- `test_redos_4_shapes_rejected_at_parse` — each of the 4 REDOS_REJECT_PATTERNS triggers `RegexLintFailed`.
- `test_unsafe_regex_opts_out_of_lint` — same pattern with `unsafe_regex=True` does not raise.
- `test_recheck_not_imported` — grep: `assert "import recheck" not in <package source>`.
- `test_subprocess_not_imported_for_recheck` — grep: `assert "subprocess" not in <package source>` (D5 closure).

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Append fixtures #22 (regex-dos), #27 (deep-composite), #30 (unknown-builtin), #29 (format-string-injection — partial; full assertion in 003.13).

## Test Cases
- Unit: ~ 15 new tests; all pass.
- Battery: fixtures #22, #27, #30 transition from xfail to xpass for the parser layer.

## Acceptance Criteria
- [ ] `dsl_parser.py` complete (≤ 400 LOC).
- [ ] `ast.parse` not imported (CI grep).
- [ ] `recheck` not imported, `subprocess` not used in dsl_parser (CI grep).
- [ ] Stdlib `re` used ONLY for parse-time `REDOS_REJECT_PATTERNS` matching, never for rule evaluation.
- [ ] D5 lint covers all 4 shapes; `unsafe_regex` opt-out works.
- [ ] All `TestDslParser` tests green.
- [ ] `validate_skill.py` exits 0.

## Notes
- The hand-written tokenizer is the security boundary. Errors there must be specific (`RulesParseError(BadGrammar)` with line/column hints when feasible) — not opaque `IndexError` / `AttributeError` from a half-written parser.
- For depth tracking: `parse_composite` increments depth for each level; `parse_check` calls `parse_composite` for `dict`-shaped checks; depth is also passed through to `Logical(depth=depth)` so F7 evaluator can sanity-check.
- The "no Python attribute access" rejection is enforced by the tokenizer refusing `.` outside numeric literals (e.g. `3.14` is allowed; `value.attr` is not). Document the corner case in the docstring.
- For ReDoS shape detection: the regex patterns in `REDOS_REJECT_PATTERNS` are themselves regex — note the meta-level. They are crafted to match WITHIN the rule's pattern string, NOT to evaluate against the rule's pattern. Use `_re_stdlib.search`, not `match`.

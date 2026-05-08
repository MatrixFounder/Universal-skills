"""F3 — DSL parser & AST builder.

Hand-written prefix-dispatch + small recursive-descent parser over
the SPEC §5 grammar. NEVER calls `ast.parse`. Forbidden tokens
at the comparison/arithmetic level: `.` outside numeric literals,
`**`, `%`, bitwise (`&`, `|`, `^`, `~`, `<<`, `>>`), `lambda`.
(Prefix-dispatched forms — `regex:`, `starts_with:`, etc. — are
EXEMPT: their payloads are opaque strings and may contain `^`/`$`/
`&`/`|` legitimately.)

D5 (architect-review m1): hand-coded reject-list for the 4 classic
ReDoS shapes is the SOLE parse-time check. `recheck` (JVM CLI) and
`subprocess` are NOT used — per-cell `regex.fullmatch(timeout=)` in
F7 is the runtime safety net.

Grammar (subset — v1):

    rule_check  := type_pred | "regex:" PAT | "len" CMP NUM
                 | "starts_with:" S | "ends_with:" S | "not_empty"
                 | "between[_excl]:" NUM "," NUM
                 | "date_in_month:" YYYY-MM | "date_in_range:" D "," D
                 | "date_before:" D | "date_after:" D | "date_weekday:" L
                 | sum_by | count_by | avg_by
                 | "value" ("not")? "in" "[" LIST "]"
                 | comparison                   # left CMP_OP right
    operand     := "value" | LITERAL | scope_ref | builtin_call

Multi-operator arithmetic chains (`value / cell:Cap * 1.05`) are
deferred to v2 — every comparison today carries exactly one operator
each side.
"""
from __future__ import annotations

import re as _re_stdlib
from typing import Any

from .ast_nodes import (
    Between, BinaryOp, BuiltinCall, CellRef, ColRef, DatePredicate,
    GroupByCheck, In, LenPredicate, Literal, Logical, MultiColRef,
    NamedRef, RangeRef, RegexPredicate, RowRef, RuleSpec, SheetRef,
    StringPredicate, TableRef, TypePredicate, UnaryOp, ValueRef,
)
from .constants import (
    BUILTIN_WHITELIST, COMPOSITE_MAX_DEPTH, REDOS_REJECT_PATTERNS,
)
from .exceptions import RegexLintFailed, RulesParseError

__all__ = [
    "parse_check",
    "parse_composite",
    "parse_scope",
    "validate_builtin",
    "lint_regex",
    "build_rule_spec",
]

_TYPE_PREDICATES = {"is_number", "is_date", "is_text", "is_bool", "is_error", "required"}
_CMP_OPS = ("==", "!=", "<=", ">=", "<", ">")
_WEEKDAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
# Forbidden Python source-level tokens (R1.d / SPEC §6 closed-AST guard).
_FORBIDDEN_TOKENS = ("**", "%", "&", "|", "^", "~", "<<", ">>", "lambda", "import")
_VALUE_REF = ValueRef()  # singleton — the implicit `value` identifier


# === Public top-level entry points ========================================

def parse_check(text: Any, depth: int = 0) -> Any:
    """Parse a `check` field — string (DSL) or dict (composite)."""
    if isinstance(text, dict):
        return parse_composite(text, depth)
    if not isinstance(text, str):
        raise RulesParseError(
            f"check must be string or dict; got {type(text).__name__}",
            subtype="BadGrammar",
        )
    return _dispatch_check(text.strip())


def parse_composite(d: dict[str, Any], depth: int = 0) -> Logical:
    # depth is incoming level; the Logical we create lives at depth+1.
    # COMPOSITE_MAX_DEPTH=16 → max 16 nested levels allowed; the 17th trips.
    if depth >= COMPOSITE_MAX_DEPTH:
        raise RulesParseError(
            f"composite depth > {COMPOSITE_MAX_DEPTH}",
            subtype="CompositeDepth", depth=depth + 1,
        )
    keys = set(d.keys())
    if keys not in ({"and"}, {"or"}, {"not"}):
        raise RulesParseError(
            f"composite must have exactly one of and/or/not as its sole key; got {sorted(keys)}",
            subtype="BadGrammar",
        )
    op = next(iter(keys))
    if op == "not":
        child = parse_check(d["not"], depth + 1)
        return Logical("not", (child,), depth=depth + 1)
    children_raw = d[op]
    if not isinstance(children_raw, list) or not children_raw:
        raise RulesParseError(
            f"`{op}` must be a non-empty list",
            subtype="BadGrammar",
        )
    children = tuple(parse_check(c, depth + 1) for c in children_raw)
    return Logical(op, children, depth=depth + 1)


def parse_scope(text: str) -> Any:
    """Parse a scope string into a ScopeNode."""
    if not isinstance(text, str):
        raise RulesParseError(
            f"scope must be a string; got {type(text).__name__}",
            subtype="BadGrammar",
        )
    return _parse_scope(text.strip())


def validate_builtin(name: str) -> None:
    if name not in BUILTIN_WHITELIST:
        raise RulesParseError(
            f"unknown builtin: {name!r}",
            subtype="UnknownBuiltin", name=name,
        )


def lint_regex(pattern: str, unsafe_regex: bool = False) -> None:
    """D5 — sole parse-time ReDoS lint; `unsafe_regex=True` opts out."""
    if unsafe_regex:
        return
    for shape in REDOS_REJECT_PATTERNS:
        if _re_stdlib.search(shape, pattern):
            raise RegexLintFailed(
                f"regex matches catastrophic-backtracking shape: {shape}",
                subtype="ReDoSLint", pattern=pattern, shape=shape,
            )


def build_rule_spec(d: dict[str, Any]) -> RuleSpec:
    """Dict → fully-parsed `RuleSpec`. Raises on missing required fields."""
    if not isinstance(d, dict):
        raise RulesParseError(
            f"rule must be a mapping; got {type(d).__name__}",
            subtype="BadGrammar",
        )
    for required in ("id", "scope", "check"):
        if required not in d:
            raise RulesParseError(
                f"rule missing required field: {required!r}",
                subtype="BadGrammar", missing=required,
            )
    return RuleSpec(
        id=str(d["id"]),
        scope=parse_scope(d["scope"]),
        check=parse_check(d["check"]),
        severity=str(d.get("severity", "error")),
        message=d["message"] if "message" in d else None,
        when=parse_check(d["when"]) if "when" in d else None,
        skip_empty=bool(d.get("skip_empty", True)),
        tolerance=float(d.get("tolerance", 1e-9)),
        header_row=d.get("header_row"),
        visible_only=d.get("visible_only"),
        treat_numeric_as_date=d.get("treat_numeric_as_date"),
        treat_text_as_date=d.get("treat_text_as_date"),
        unsafe_regex=bool(d.get("unsafe_regex", False)),
    )


# === Forbidden-token rejection ============================================

def _reject_forbidden_tokens(s: str) -> None:
    for tok in _FORBIDDEN_TOKENS:
        if tok in s:
            raise RulesParseError(
                f"forbidden token in DSL expression: {tok!r}",
                subtype="BadGrammar", token=tok, expression=s,
            )


def _reject_attribute_access(s: str) -> None:
    """`.` outside numeric literals → BadGrammar (covers `value.attr`)."""
    n = len(s)
    i = 0
    while i < n:
        c = s[i]
        if c == ".":
            prev_digit = i > 0 and s[i - 1].isdigit()
            next_digit = i + 1 < n and s[i + 1].isdigit()
            if not (prev_digit or next_digit):
                raise RulesParseError(
                    f"attribute access not allowed: {s!r}",
                    subtype="BadGrammar", expression=s, position=i,
                )
        i += 1


# === Check dispatch =======================================================

def _dispatch_check(s: str) -> Any:
    # Type predicates (exact match — no payload).
    if s in _TYPE_PREDICATES:
        return TypePredicate(s)
    if s == "not_empty":
        return StringPredicate("not_empty")

    # Prefix-dispatched forms with payload.
    if s.startswith("regex:"):
        pattern = s[len("regex:"):]
        lint_regex(pattern)
        return RegexPredicate(pattern)
    if s.startswith("starts_with:"):
        return StringPredicate("starts_with", s[len("starts_with:"):])
    if s.startswith("ends_with:"):
        return StringPredicate("ends_with", s[len("ends_with:"):])
    if s.startswith("between:"):
        lo, hi = _parse_two_numbers(s[len("between:"):], "between:")
        return Between(_VALUE_REF, lo, hi, inclusive=True)
    if s.startswith("between_excl:"):
        lo, hi = _parse_two_numbers(s[len("between_excl:"):], "between_excl:")
        return Between(_VALUE_REF, lo, hi, inclusive=False)
    if s.startswith("date_in_month:"):
        return DatePredicate("date_in_month", (s[len("date_in_month:"):],))
    if s.startswith("date_in_range:"):
        lo, hi = _split_two_strings(s[len("date_in_range:"):], "date_in_range:")
        return DatePredicate("date_in_range", (lo, hi))
    if s.startswith("date_before:"):
        return DatePredicate("date_before", (s[len("date_before:"):],))
    if s.startswith("date_after:"):
        return DatePredicate("date_after", (s[len("date_after:"):],))
    if s.startswith("date_weekday:"):
        days = tuple(d.strip() for d in s[len("date_weekday:"):].split(","))
        bad = [d for d in days if d not in _WEEKDAYS]
        if bad:
            raise RulesParseError(
                f"unknown weekday(s): {bad}; expected subset of {sorted(_WEEKDAYS)}",
                subtype="BadGrammar", got=bad,
            )
        return DatePredicate("date_weekday", days)
    if s.startswith("len ") or s.startswith("len\t"):
        return _parse_len(s[3:].lstrip())
    for fn in ("sum_by:", "count_by:", "avg_by:"):
        if s.startswith(fn):
            return _parse_group_by(fn[:-1], s[len(fn):])

    # `value in [...]` / `value not in [...]`
    m = _re_stdlib.match(r"\s*value\s+(not\s+)?in\s+\[(.*)\]\s*$", s)
    if m:
        items_raw = m.group(2)
        items = tuple(_parse_in_item(it.strip()) for it in items_raw.split(","))
        return In(_VALUE_REF, items, negate=bool(m.group(1)))

    # Comparison / arithmetic — `left CMP_OP right` (no chained comparisons).
    return _parse_comparison(s)


# === Helpers — value-list, len, group-by, comparison ======================

def _parse_in_item(token: str) -> Any:
    """`In.haystack` items — strip optional surrounding quotes."""
    if (len(token) >= 2) and token[0] in ("'", '"') and token[-1] == token[0]:
        return token[1:-1]
    return _coerce_literal(token)


def _parse_two_numbers(payload: str, label: str) -> tuple[float, float]:
    parts = payload.split(",")
    if len(parts) != 2:
        raise RulesParseError(
            f"{label} expects exactly two numbers; got {payload!r}",
            subtype="BadGrammar",
        )
    try:
        return float(parts[0].strip()), float(parts[1].strip())
    except ValueError as e:
        raise RulesParseError(
            f"{label} numeric parse failed: {e}",
            subtype="BadGrammar",
        ) from e


def _split_two_strings(payload: str, label: str) -> tuple[str, str]:
    parts = [p.strip() for p in payload.split(",")]
    if len(parts) != 2:
        raise RulesParseError(
            f"{label} expects two ISO dates separated by a comma",
            subtype="BadGrammar",
        )
    return parts[0], parts[1]


def _parse_len(rest: str) -> LenPredicate:
    for op in _CMP_OPS:
        if rest.startswith(op):
            num_text = rest[len(op):].strip()
            try:
                return LenPredicate(op, int(num_text))
            except ValueError as e:
                raise RulesParseError(
                    f"len predicate expects integer: {num_text!r}",
                    subtype="BadGrammar",
                ) from e
    raise RulesParseError(
        f"len predicate missing comparison operator: 'len {rest!r}'",
        subtype="BadGrammar",
    )


def _parse_group_by(fn: str, rest: str) -> GroupByCheck:
    """`sum_by:KEY OP X` — KEY is the column header/letter; OP is a CMP_OP."""
    for op in _CMP_OPS:
        idx = rest.find(op)
        if idx > 0:
            key = rest[:idx].strip()
            rhs_text = rest[idx + len(op):].strip()
            return GroupByCheck(fn=fn, key=key, op=op, rhs=_parse_operand(rhs_text))
    raise RulesParseError(
        f"{fn}: KEY OP X — missing comparison operator in {rest!r}",
        subtype="BadGrammar",
    )


def _parse_comparison(s: str) -> Any:
    """`left CMP_OP right` — Python-attribute / forbidden-token rejection
    happens HERE (not at top-level dispatch) so prefix-dispatched payloads
    like `regex:^[A-Z]+$` keep their `^` / `$` anchors intact."""
    _reject_forbidden_tokens(s)
    _reject_attribute_access(s)
    op, idx = _find_top_level_cmp_op(s)
    if op is None:
        raise RulesParseError(
            f"check expression has no comparison operator: {s!r}",
            subtype="BadGrammar",
        )
    left = _parse_operand(s[:idx].strip())
    right = _parse_operand(s[idx + len(op):].strip())
    return BinaryOp(op, left, right)


def _find_top_level_cmp_op(s: str) -> tuple[str | None, int]:
    """Find LAST CMP_OP at top level (not in parens/brackets); two-char ops
    take precedence over single (`<=` not `<` then `=`)."""
    depth = 0
    last_op: str | None = None
    last_idx = -1
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif depth == 0:
            for op in ("<=", ">=", "==", "!="):
                if s.startswith(op, i):
                    last_op, last_idx = op, i
                    i += len(op) - 1
                    break
            else:
                if c in "<>" and (i + 1 >= n or s[i + 1] not in "="):
                    last_op, last_idx = c, i
        i += 1
    return last_op, last_idx


def _parse_operand(s: str) -> Any:
    """A single operand: `value`, literal, scope ref, or builtin call."""
    s = s.strip()
    if not s:
        raise RulesParseError("empty operand", subtype="BadGrammar")
    if s == "value":
        return _VALUE_REF
    # Builtin call: NAME(args)
    m = _re_stdlib.match(r"^([a-zA-Z_][a-zA-Z_0-9]*)\((.*)\)$", s)
    if m:
        name = m.group(1)
        validate_builtin(name)
        arg_text = m.group(2).strip()
        arg = _parse_scope(arg_text)
        return BuiltinCall(name, (arg,))
    # Scope ref: cell: / col: / cols: / row: / sheet: / named: / table: / RANGE / A1 / 'Sheet'!...
    if (":" in s and not s.startswith("'")) or "!" in s or _looks_like_range(s) or _looks_like_a1(s):
        return _parse_scope(s)
    return Literal(_coerce_literal(s))


def _coerce_literal(s: str) -> Any:
    """Bare literal: number or unquoted string. Strips surrounding quotes."""
    if not s:
        return ""
    if (len(s) >= 2) and s[0] in ("'", '"') and s[-1] == s[0]:
        return s[1:-1]
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s in ("null", "None", ""):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s  # bare identifier / unquoted text


# === Scope parsing ========================================================

def _looks_like_range(s: str) -> bool:
    return bool(_re_stdlib.match(r"^[A-Z]+\d+:[A-Z]+\d+$", s.replace("$", "")))


def _looks_like_a1(s: str) -> bool:
    return bool(_re_stdlib.match(r"^[A-Z]+\d+$", s.replace("$", "")))


def _parse_scope(text: str) -> Any:
    # Sheet qualifier delegated to scope_resolver (single source of truth).
    # Forms: cell:/col:/cols:/row:/sheet:/named:/table:; bare A1 / RANGE.
    from .scope_resolver import parse_sheet_qualifier
    sheet, rest = parse_sheet_qualifier(text)
    return _parse_scope_body(sheet, rest.strip())


def _parse_scope_body(sheet: str | None, body: str) -> Any:
    if body.startswith("cell:"):
        return CellRef(sheet, body[len("cell:"):])
    if body.startswith("col:"):
        name = body[len("col:"):]
        is_letter = bool(_re_stdlib.match(r"^[A-Z]+$", name))
        return ColRef(sheet, name, is_letter)
    if body.startswith("cols:"):
        children = []
        for tok in body[len("cols:"):].split(","):
            tok = tok.strip()
            is_letter = bool(_re_stdlib.match(r"^[A-Z]+$", tok))
            children.append(ColRef(sheet, tok, is_letter))
        return MultiColRef(sheet, tuple(children))
    if body.startswith("row:"):
        try:
            return RowRef(sheet, int(body[len("row:"):]))
        except ValueError as e:
            raise RulesParseError(f"row: expects integer; got {body!r}",
                                    subtype="BadGrammar") from e
    if body.startswith("sheet:"):
        return SheetRef(body[len("sheet:"):])
    if body.startswith("named:"):
        return NamedRef(body[len("named:"):])
    if body.startswith("table:"):
        return _parse_table_ref(body[len("table:"):])
    cleaned = body.replace("$", "")
    if _looks_like_range(cleaned):
        start, end = cleaned.split(":")
        return RangeRef(sheet, start, end)
    if _looks_like_a1(cleaned):
        return CellRef(sheet, cleaned)
    raise RulesParseError(
        f"unrecognised scope form: {body!r}",
        subtype="BadGrammar",
    )


def _parse_table_ref(rest: str) -> TableRef:
    m = _re_stdlib.match(r"^([^\[]+)(?:\[([^\]]+)\])?$", rest)
    if not m:
        raise RulesParseError(f"unrecognised table scope: {rest!r}",
                                subtype="BadGrammar")
    return TableRef(m.group(1), m.group(2))

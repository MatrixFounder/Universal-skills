"""F4 — Closed AST type vocabulary for xlsx-7.

Consumed by F3 (parser), F7 (evaluator), F8 (aggregate cache).
Pure data: every node is a frozen dataclass. No openpyxl, no
`regex`, no I/O — this module sits at the top of the F2/F3
import chain right after `constants` and `exceptions`.

Adding a new node type is a breaking change requiring a SPEC
update and an architect-locked decision: the closed vocabulary
is what guarantees that no Python attribute access, `**`, `%`,
bitwise, or lambda escape hatch can be smuggled into a rules file
(SPEC §6).

`to_canonical_str(node)` produces the deterministic string consumed
by the F8 aggregate cache SHA-1 key (SPEC §5.5.3). The caller
pre-resolves sheet qualifiers (None → explicit) and header lookups
(`col:Hours` → `col:#B` after Table-fallback equivalence) so the
canonical form encodes only what's load-bearing for cache identity.

Identity rules (SPEC §5.5.3):

  - Commutative-by-design nodes have children sorted before
    serialisation: ``Logical("and"|"or", ...)``, ``In(haystack=...)``.
  - Non-commutative nodes preserve operand order:
    ``BinaryOp("<", a, b)`` ≠ ``BinaryOp("<", b, a)``,
    ``BuiltinCall`` arguments stay positional.
  - ``None`` becomes the literal ``"~"``; ``bool`` dispatches
    before ``int`` (else ``True`` collides with ``Literal(1)``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    # Leaf / scope (9)
    "Literal",
    "CellRef",
    "RangeRef",
    "ColRef",
    "MultiColRef",
    "RowRef",
    "SheetRef",
    "NamedRef",
    "TableRef",
    # Magic implicit "value" identifier in the DSL (1)
    "ValueRef",
    # Operators (3)
    "BinaryOp",
    "UnaryOp",
    "BuiltinCall",
    # Set ops (2)
    "In",
    "Between",
    # Logical (1)
    "Logical",
    # Predicates (5)
    "TypePredicate",
    "RegexPredicate",
    "LenPredicate",
    "StringPredicate",
    "DatePredicate",
    # Group-by (1)
    "GroupByCheck",
    # Top-level wrapper
    "RuleSpec",
    # Helper
    "to_canonical_str",
]


# === Leaf / scope nodes (9) ===============================================

@dataclass(frozen=True)
class Literal:
    value: Any  # int | float | str | bool | None | ISO date string


@dataclass(frozen=True)
class CellRef:
    sheet: str | None  # None pre-resolution; F8 caller resolves
    ref: str           # A1-style, e.g. "A5"


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


@dataclass(frozen=True)
class MultiColRef:
    sheet: str | None
    children: tuple["ColRef", ...]


@dataclass(frozen=True)
class RowRef:
    sheet: str | None
    n: int


@dataclass(frozen=True)
class SheetRef:
    name: str


@dataclass(frozen=True)
class NamedRef:
    name: str  # multi-area definedNames rejected at parse


@dataclass(frozen=True)
class TableRef:
    name: str
    column: str | None = None  # None = whole-table; str = single column


@dataclass(frozen=True)
class ValueRef:
    """The magic implicit `value` identifier in the DSL — refers to the
    cell currently being evaluated. The evaluator (F7) substitutes the
    classified-cell's value at eval time. No fields; presence is the
    signal."""


# === Operators (3) ========================================================

@dataclass(frozen=True)
class BinaryOp:
    op: str    # ==, !=, <, <=, >, >=, +, -, *, /  (no **, %, bitwise)
    left: Any
    right: Any


@dataclass(frozen=True)
class UnaryOp:
    op: str  # "-" (negation) or "not"
    operand: Any


@dataclass(frozen=True)
class BuiltinCall:
    name: str  # validated against constants.BUILTIN_WHITELIST at parse
    args: tuple[Any, ...]


# === Set ops (2) ==========================================================

@dataclass(frozen=True)
class In:
    needle: Any
    haystack: tuple[Any, ...]
    negate: bool


@dataclass(frozen=True)
class Between:
    operand: Any
    low: float
    high: float
    inclusive: bool


# === Logical (1) ==========================================================

@dataclass(frozen=True)
class Logical:
    op: str                      # "and" | "or" | "not"
    children: tuple[Any, ...]
    depth: int                   # ≤ COMPOSITE_MAX_DEPTH; set by parser


# === Predicates (5) =======================================================

@dataclass(frozen=True)
class TypePredicate:
    name: str  # is_number / is_date / is_text / is_bool / is_error / required


@dataclass(frozen=True)
class RegexPredicate:
    pattern: str
    unsafe_regex: bool = False  # rule-level opt-out of D5 parse-time lint


@dataclass(frozen=True)
class LenPredicate:
    op: str  # ==, !=, <, <=, >, >=
    n: int


@dataclass(frozen=True)
class StringPredicate:
    name: str  # starts_with / ends_with / not_empty
    arg: str = ""


@dataclass(frozen=True)
class DatePredicate:
    name: str  # date_in_month / date_in_range / date_before / date_after / date_weekday
    args: tuple[str, ...]


# === Group-by (1) =========================================================

@dataclass(frozen=True)
class GroupByCheck:
    fn: str   # sum_by | count_by | avg_by
    key: str  # column header or letter
    op: str
    rhs: Any


# === Top-level wrapper ====================================================

@dataclass(frozen=True)
class RuleSpec:
    """Fully-parsed rule (one entry of the `rules: [...]` list).
    Defaults match SPEC §3 exactly; per-rule None for header_row /
    visible_only / treat_*_as_date means "inherit from `defaults`."""

    id: str
    scope: Any
    check: Any
    severity: str = "error"  # one of constants.SEVERITY_LEVELS
    message: str | None = None
    when: Any = None
    skip_empty: bool = True
    tolerance: float = 1e-9
    header_row: int | None = None
    visible_only: bool | None = None
    treat_numeric_as_date: bool | None = None
    treat_text_as_date: bool | None = None
    unsafe_regex: bool = False


# === Canonical-string helper (F8 cache-key input) =========================

def to_canonical_str(node: Any) -> str:
    """Deterministic canonical string consumed by `hashlib.sha1` in F8.

    See module docstring for the identity rules. The closed-AST guard
    raises ``TypeError`` for unknown node types (defensive — also the
    test anchor that catches a future Developer adding a new node
    without updating the dispatch table).
    """
    return _canonical(node)


def _canonical(node: Any) -> str:  # noqa: C901 — flat dispatch over a closed AST
    if node is None:
        return "~"
    if isinstance(node, Literal):
        v = node.value
        if isinstance(v, bool):  # MUST be checked before int (bool ⊂ int)
            return f"L:b:{v}"
        if isinstance(v, int):
            return f"L:i:{v}"
        if isinstance(v, float):
            return f"L:f:{v!r}"
        if isinstance(v, str):
            return f"L:s:{v}"
        if v is None:
            return "L:~"
        return f"L:?:{v!r}"
    if isinstance(node, CellRef):
        return f"Cell:{node.sheet or ''}!{node.ref}"
    if isinstance(node, RangeRef):
        return f"Range:{node.sheet or ''}!{node.start}:{node.end}"
    if isinstance(node, ColRef):
        prefix = "#" if node.is_letter else ""
        return f"Col:{node.sheet or ''}!{prefix}{node.name_or_letter}"
    if isinstance(node, MultiColRef):
        kids = ",".join(_canonical(c) for c in node.children)
        return f"MultiCol:{node.sheet or ''}!({kids})"
    if isinstance(node, RowRef):
        return f"Row:{node.sheet or ''}!{node.n}"
    if isinstance(node, SheetRef):
        return f"Sheet:{node.name}"
    if isinstance(node, NamedRef):
        return f"Named:{node.name}"
    if isinstance(node, TableRef):
        col = f"[{node.column}]" if node.column else ""
        return f"Table:{node.name}{col}"
    if isinstance(node, ValueRef):
        return "Value"
    if isinstance(node, BuiltinCall):
        args = ",".join(_canonical(a) for a in node.args)
        return f"Call:{node.name}({args})"
    if isinstance(node, BinaryOp):
        return f"Op:{node.op}({_canonical(node.left)},{_canonical(node.right)})"
    if isinstance(node, UnaryOp):
        return f"UnaryOp:{node.op}({_canonical(node.operand)})"
    if isinstance(node, In):
        items = sorted(repr(h) for h in node.haystack)
        prefix = "NotIn" if node.negate else "In"
        return f"{prefix}:{_canonical(node.needle)}/[{','.join(items)}]"
    if isinstance(node, Between):
        kind = "BetweenInc" if node.inclusive else "BetweenExc"
        return f"{kind}:{_canonical(node.operand)}/{node.low!r},{node.high!r}"
    if isinstance(node, Logical):
        if node.op == "not":
            inner = _canonical(node.children[0]) if node.children else "~"
            return f"Logical:not({inner})"
        kids = sorted(_canonical(c) for c in node.children)
        return f"Logical:{node.op}({','.join(kids)})"
    if isinstance(node, TypePredicate):
        return f"Type:{node.name}"
    if isinstance(node, RegexPredicate):
        flag = "U" if node.unsafe_regex else "S"
        return f"Regex:{flag}:{node.pattern}"
    if isinstance(node, LenPredicate):
        return f"Len:{node.op}{node.n}"
    if isinstance(node, StringPredicate):
        return f"Str:{node.name}({node.arg})"
    if isinstance(node, DatePredicate):
        args = ",".join(node.args)
        return f"Date:{node.name}({args})"
    if isinstance(node, GroupByCheck):
        return f"GroupBy:{node.fn}/{node.key}/{node.op}/{_canonical(node.rhs)}"
    raise TypeError(f"to_canonical_str: unknown AST node type {type(node).__name__}")

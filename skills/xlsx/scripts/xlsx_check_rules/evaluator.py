"""F7 — Rule evaluator. SPEC §5.0 cell triage + §5.0.1 stale-cache
warning + per-cell `regex.fullmatch(timeout=100ms)` (R9.d) +
`string.Template` message format (SPEC §6.3 injection guard).
Aggregates routed via `ctx.aggregate_cache.eval_aggregate`."""
from __future__ import annotations

import string
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterator

from regex import compile as regex_compile  # PyPI `regex`, NOT stdlib re

from .ast_nodes import (
    Between, BinaryOp, BuiltinCall, CellRef, ColRef, DatePredicate,
    GroupByCheck, In, LenPredicate, Literal, Logical, RegexPredicate,
    RuleSpec, StringPredicate, TypePredicate, UnaryOp, ValueRef,
)
from .cell_types import ClassifiedCell, LogicalType, classify
from .constants import DEFAULT_REGEX_TIMEOUT_MS
from .exceptions import CellError

__all__ = [
    "Finding",
    "EvalContext",
    "eval_rule",
    "eval_check",
    "eval_regex",
    "eval_arithmetic",
    "format_message",
]


@dataclass
class Finding:
    cell: str  # "Sheet!Ref" for per-cell; bare sheet for grouped
    sheet: str
    row: int | None
    column: str | None
    rule_id: str
    severity: str
    value: Any
    message: str
    expected: Any | None = None
    tolerance: float | None = None
    group: str | None = None


@dataclass
class EvalContext:
    workbook: Any = None  # openpyxl Workbook (read-only)
    rule: RuleSpec | None = None
    aggregate_cache: Any = None  # F8 cache (003.12)
    regex_compile_cache: dict[str, Any] = field(default_factory=dict)
    stale_cache_warned: bool = False
    regex_timeouts: int = 0
    eval_errors: int = 0
    cell_errors: int = 0
    skipped_in_aggregates: int = 0
    aggregate_cache_hits: int = 0
    regex_timeout_seconds: float = DEFAULT_REGEX_TIMEOUT_MS / 1000.0
    stderr: Any = None  # injectable for tests; falls back to sys.stderr
    # F8 (003.12) additions:
    strict_aggregates: bool = False
    pending_findings: list = field(default_factory=list)
    defaults: dict = field(default_factory=dict)  # rules-file `defaults` block
    eval_opts: dict = field(default_factory=dict)  # opts forwarded to scope_resolver
    # Per-rule group-by cache: row → (group, aggregate_value). Populated
    # by eval_rule when the rule's check is a GroupByCheck; reused by
    # eval_check's per-cell GroupByCheck dispatch so eval_group_by
    # runs once per rule instead of once per cell.
    group_by_row_map: dict[int, Any] | None = None
    group_by_result: dict[Any, float] | None = None

    def append_finding(self, finding: "Finding") -> None:
        """F8 sink — replayed type-mismatch / nan findings drained by F7's outer loop."""
        self.pending_findings.append(finding)


def eval_rule(rule_spec: RuleSpec, scope_result: Any, ctx: EvalContext) -> Iterator[Finding]:
    """Outer loop over scope's cells. Triage per §5.0 + §5.0.1; emit findings."""
    ctx.rule = rule_spec
    skip_empty = rule_spec.skip_empty
    # SPEC §5.6 — group-by yields one finding per VIOLATING GROUP
    # (NOT per cell, NOT per row). Compute once, emit grouped findings,
    # and short-circuit the per-cell loop.
    if isinstance(rule_spec.check, GroupByCheck):
        yield from _eval_group_by_rule(rule_spec, scope_result, ctx)
        return
    ctx.group_by_result = None
    ctx.group_by_row_map = None
    # L2 (Sarcasmotron iter-1): wire `--visible-only` through to the
    # per-cell loop. Previously `iter_cells` existed but was never
    # called, so hidden rows/cols were always evaluated. Now eval_rule
    # filters at the only iteration point. Explicit hidden-SHEET names
    # are still honored at `resolve_sheet` (SPEC §4 honest-scope —
    # naming a hidden sheet is opt-in).
    visible_only = bool(ctx.eval_opts.get("visible_only", False)) if ctx.eval_opts else False
    cells_iter = (c for c in scope_result.cells if not (visible_only and c.is_hidden))
    for cell in cells_iter:
        # SPEC §5.0.1 — stale-cache one-time warning.
        # L1: emit warning at most once per RUN (cli.py hoists
        # stale_cache_warned across rules) AND only when the user has
        # NOT opted out via `--ignore-stale-cache`.
        if (cell.has_formula_no_cache and not ctx.stale_cache_warned
                and not ctx.eval_opts.get("ignore_stale_cache", False)):
            stderr = ctx.stderr or sys.stderr
            print(
                "WARNING: workbook has formulas without cached values; "
                "run xlsx_recalc.py before xlsx_check_rules.py for accurate "
                "results.",
                file=stderr,
            )
            ctx.stale_cache_warned = True

        # SPEC §5.0 — error-cell short-circuit (D4 7-code subset).
        if cell.logical_type is LogicalType.ERROR:
            ctx.cell_errors += 1
            err_value = cell.value.code if isinstance(cell.value, CellError) else str(cell.value)
            yield Finding(
                cell=f"{cell.sheet}!{cell.col}{cell.row}",
                sheet=cell.sheet, row=cell.row, column=cell.col,
                rule_id="cell-error", severity="error", value=err_value,
                message=f"Cell contains Excel error: {err_value}",
            )
            continue  # other rules on this cell are suppressed

        # `skip_empty` triage.
        if cell.logical_type is LogicalType.EMPTY and skip_empty:
            # Special case: `required` MUST run on empty cells per SPEC §3 / §5.2.
            if not _is_required_predicate(rule_spec.check):
                continue

        # `when` filter (per-row pre-filter).
        if rule_spec.when is not None:
            when_result = eval_check(rule_spec.when, cell, ctx)
            if isinstance(when_result, Finding) or not when_result:
                continue

        result = eval_check(rule_spec.check, cell, ctx)
        # Drain F8 pending findings (type-mismatch, replay events) before
        # yielding the rule's own finding for this cell.
        while ctx.pending_findings:
            yield ctx.pending_findings.pop(0)
        if isinstance(result, Finding):
            yield result
            continue
        if not result:
            yield _make_finding(rule_spec, cell, ctx, value=cell.value)


def _is_required_predicate(check: Any) -> bool:
    """`required` / `not_empty` must fire on EMPTY cells; everything else
    skips per SPEC §5.2."""
    if isinstance(check, TypePredicate) and check.name == "required":
        return True
    if isinstance(check, StringPredicate) and check.name == "not_empty":
        return True
    return False


def _make_finding(rule: RuleSpec, cell: ClassifiedCell, ctx: EvalContext,
                   value: Any = None, expected: Any = None,
                   group: str | None = None) -> Finding:
    """Build a per-cell `Finding` from the rule + cell + optional expected/group."""
    msg = format_message(rule.message, cell, rule.id, value, group=group)
    return Finding(
        cell=f"{cell.sheet}!{cell.col}{cell.row}",
        sheet=cell.sheet, row=cell.row, column=cell.col,
        rule_id=rule.id, severity=rule.severity,
        value=_jsonable(value),
        message=msg,
        expected=_jsonable(expected) if expected is not None else None,
        tolerance=rule.tolerance if expected is not None else None,
        group=group,
    )


def _jsonable(v: Any) -> Any:
    """Coerce to a JSON-serialisable form for Finding.value / .expected."""
    if isinstance(v, CellError):
        return v.code
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


# === eval_check dispatcher ================================================

def eval_check(node: Any, cell: ClassifiedCell, ctx: EvalContext) -> bool | Finding:
    """Dispatch on AST type. Returns True/False, or a Finding for synthetic
    error/timeout/eval-error short-circuits."""
    if isinstance(node, TypePredicate):
        return _eval_type_predicate(node, cell)
    if isinstance(node, RegexPredicate):
        return _eval_regex_predicate(node, cell, ctx)
    if isinstance(node, LenPredicate):
        return _eval_len_predicate(node, cell)
    if isinstance(node, StringPredicate):
        return _eval_string_predicate(node, cell)
    if isinstance(node, DatePredicate):
        return _eval_date_predicate(node, cell)
    if isinstance(node, In):
        return _eval_in(node, cell, ctx)
    if isinstance(node, Between):
        return _eval_between(node, cell, ctx)
    if isinstance(node, BinaryOp):
        return _eval_binary_op(node, cell, ctx)
    if isinstance(node, UnaryOp):
        return _eval_unary_op(node, cell, ctx)
    if isinstance(node, Logical):
        return _eval_logical(node, cell, ctx)
    if isinstance(node, GroupByCheck):
        # GroupByCheck is dispatched at rule level (eval_rule short-
        # circuits before per-cell loop) — see _eval_group_by_rule.
        return _aggregate_unimplemented(ctx, cell, "GroupByCheck must be the rule's top-level check")
    raise TypeError(f"eval_check: unsupported AST node {type(node).__name__}")


# === Type / String / Date / Len predicates ================================

def _eval_type_predicate(node: TypePredicate, cell: ClassifiedCell) -> bool:
    name = node.name
    lt = cell.logical_type
    if name == "is_number":
        return lt is LogicalType.NUMBER
    if name == "is_date":
        return lt is LogicalType.DATE
    if name == "is_text":
        return lt is LogicalType.TEXT
    if name == "is_bool":
        return lt is LogicalType.BOOL
    if name == "is_error":
        return lt is LogicalType.ERROR
    if name == "required":
        return lt is not LogicalType.EMPTY
    raise TypeError(f"unknown TypePredicate: {name!r}")


def _eval_string_predicate(node: StringPredicate, cell: ClassifiedCell) -> bool:
    if cell.logical_type is not LogicalType.TEXT:
        return False
    text = cell.value or ""
    if node.name == "starts_with":
        return text.startswith(node.arg)
    if node.name == "ends_with":
        return text.endswith(node.arg)
    if node.name == "not_empty":
        return bool(text)
    raise TypeError(f"unknown StringPredicate: {node.name!r}")


def _eval_len_predicate(node: LenPredicate, cell: ClassifiedCell) -> bool:
    if cell.logical_type is not LogicalType.TEXT:
        return False
    return _cmp(len(cell.value or ""), node.op, node.n)


def _eval_date_predicate(node: DatePredicate, cell: ClassifiedCell) -> bool:
    if cell.logical_type is not LogicalType.DATE:
        return False
    cell_date = cell.value
    if isinstance(cell_date, datetime):
        cell_date = cell_date.date()
    name = node.name
    if name == "date_in_month":
        ym = node.args[0]  # "YYYY-MM"
        try:
            year, month = (int(p) for p in ym.split("-"))
        except (ValueError, IndexError):
            return False
        return cell_date.year == year and cell_date.month == month
    if name == "date_in_range":
        lo = _parse_iso(node.args[0])
        hi = _parse_iso(node.args[1])
        return lo is not None and hi is not None and lo <= cell_date <= hi
    if name == "date_before":
        d = _parse_iso(node.args[0])
        return d is not None and cell_date < d
    if name == "date_after":
        d = _parse_iso(node.args[0])
        return d is not None and cell_date > d
    if name == "date_weekday":
        weekday_names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        return weekday_names[cell_date.weekday()] in node.args
    raise TypeError(f"unknown DatePredicate: {name!r}")


def _parse_iso(s: str) -> date | None:
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


# === Group-by rule (SPEC §5.6) =============================================

def _eval_group_by_rule(rule_spec: RuleSpec, scope_result: Any,
                          ctx: EvalContext) -> Iterator[Finding]:
    """Emit one finding per VIOLATING GROUP per SPEC §7.1.3 grouped-
    finding shape: `cell` is the bare sheet name (no `!Ref`),
    `row`/`column` are `None`, `group` carries the group label."""
    from .aggregates import eval_group_by
    node: GroupByCheck = rule_spec.check  # type: ignore[assignment]
    try:
        groups = eval_group_by(node, scope_result, ctx)
    except Exception as e:  # noqa: BLE001 — F8 boundary
        # Surface a single rule-eval-error scoped to the rule's sheet.
        sheet_name = scope_result.sheet_name
        ctx.eval_errors += 1
        yield Finding(
            cell=sheet_name, sheet=sheet_name, row=None, column=None,
            rule_id="rule-eval-error", severity="error", value=None,
            message=f"group-by eval failed: {e}",
        )
        return

    # The threshold may reference $value/etc; build a synthetic cell-less
    # context for `_resolve_operand` (literals work; references to cells
    # in a group-by RHS are not in scope per SPEC §5.6 grammar).
    sentinel_cell = ClassifiedCell(
        sheet=scope_result.sheet_name, row=0, col="A",
        value=None, logical_type=LogicalType.EMPTY,
        has_formula_no_cache=False,
    )
    threshold_value = _resolve_operand(node.rhs, sentinel_cell, ctx)
    if isinstance(threshold_value, Finding):
        yield threshold_value
        return

    rule_id = rule_spec.id
    sheet_name = scope_result.sheet_name
    for group_key, aggregate_value in groups.items():
        if not _cmp(aggregate_value, node.op, threshold_value):
            # SPEC §7.1.1: `findings[].group` MUST serialise as `null`
            # for the synthetic empty-key group. The Finding dataclass
            # field is None → output.py emits null. The `$group`
            # placeholder substitution gets the human-readable label
            # `<empty>` separately so the message stays readable.
            group_label = "<empty>" if group_key is None else str(group_key)
            wire_group: str | None = None if group_key is None else str(group_key)
            agg_cell = ClassifiedCell(
                sheet=sheet_name, row=0, col="",
                value=aggregate_value, logical_type=LogicalType.NUMBER,
                has_formula_no_cache=False,
            )
            msg = format_message(rule_spec.message, agg_cell, rule_id,
                                  value=aggregate_value, group=group_label)
            yield Finding(
                cell=sheet_name, sheet=sheet_name, row=None, column=None,
                rule_id=rule_id, severity=rule_spec.severity,
                value=aggregate_value, message=msg, group=wire_group,
            )


# === In / Between =========================================================

def _eval_in(node: In, cell: ClassifiedCell, ctx: EvalContext) -> bool:
    operand_value = _resolve_operand(node.needle, cell, ctx)
    if isinstance(operand_value, Finding):
        return operand_value
    in_list = operand_value in node.haystack
    return (not in_list) if node.negate else in_list


def _eval_between(node: Between, cell: ClassifiedCell, ctx: EvalContext) -> bool:
    operand_value = _resolve_operand(node.operand, cell, ctx)
    if isinstance(operand_value, Finding):
        return operand_value
    if not isinstance(operand_value, (int, float)) or isinstance(operand_value, bool):
        return False
    if node.inclusive:
        return node.low <= operand_value <= node.high
    return node.low < operand_value < node.high


# === BinaryOp / UnaryOp / Logical ==========================================

_CMP_OPS = ("==", "!=", "<", "<=", ">", ">=")
_ARITH_OPS = ("+", "-", "*", "/")


def _eval_binary_op(node: BinaryOp, cell: ClassifiedCell, ctx: EvalContext) -> bool | Finding:
    if node.op in _ARITH_OPS:
        # Pure arithmetic in a check expression isn't a predicate — but
        # could appear as part of a larger compare. Defer to eval_arithmetic
        # which returns a numeric value.
        return _arith_to_pred(node, cell, ctx)
    if node.op not in _CMP_OPS:
        raise TypeError(f"unknown BinaryOp: {node.op!r}")
    left = _resolve_operand(node.left, cell, ctx)
    if isinstance(left, Finding):
        return left
    right = _resolve_operand(node.right, cell, ctx)
    if isinstance(right, Finding):
        return right
    # Tolerance applies to == and != per SPEC §5.5.4.
    if node.op in ("==", "!="):
        tol = ctx.rule.tolerance if ctx.rule is not None else 1e-9
        if isinstance(left, (int, float)) and isinstance(right, (int, float)) \
                and not isinstance(left, bool) and not isinstance(right, bool):
            equal = abs(float(left) - float(right)) <= tol
            return equal if node.op == "==" else (not equal)
    return _cmp(left, node.op, right)


def _arith_to_pred(node: BinaryOp, cell: ClassifiedCell, ctx: EvalContext) -> Finding:
    """Bare arithmetic outside a comparison context — defensive eval-error."""
    return _eval_error(ctx, cell, "arithmetic expression used as predicate")


def _eval_unary_op(node: UnaryOp, cell: ClassifiedCell, ctx: EvalContext) -> bool | Finding:
    inner = eval_check(node.operand, cell, ctx)
    if isinstance(inner, Finding):
        return inner
    if node.op == "not":
        return not inner
    if node.op == "-":
        # Negation of a predicate result doesn't make sense; treat as eval-error.
        return _eval_error(ctx, cell, "unary - on predicate")
    raise TypeError(f"unknown UnaryOp: {node.op!r}")


def _eval_logical(node: Logical, cell: ClassifiedCell, ctx: EvalContext) -> bool | Finding:
    if node.op == "and":
        for child in node.children:
            r = eval_check(child, cell, ctx)
            if isinstance(r, Finding):
                return r
            if not r:
                return False
        return True
    if node.op == "or":
        for child in node.children:
            r = eval_check(child, cell, ctx)
            if isinstance(r, Finding):
                return r
            if r:
                return True
        return False
    if node.op == "not":
        if not node.children:
            return True
        r = eval_check(node.children[0], cell, ctx)
        if isinstance(r, Finding):
            return r
        return not r
    raise TypeError(f"unknown Logical op: {node.op!r}")


# === Operand resolution (Literal / ValueRef / scope refs / aggregates) =====

def _resolve_operand(node: Any, cell: ClassifiedCell, ctx: EvalContext) -> Any:
    if isinstance(node, Literal):
        return node.value
    if isinstance(node, ValueRef):
        return cell.value
    if isinstance(node, BuiltinCall):
        return _resolve_aggregate(node, ctx, cell)
    if isinstance(node, CellRef):
        # L5 (Sarcasmotron iter-1): single-cell lookup against the
        # active workbook. The cell's value is classified the same way
        # as scope cells so type-aware comparisons work (e.g.
        # `value == cell:H1` with H1 holding a number).
        return _resolve_cell_ref(node, cell, ctx)
    if isinstance(node, ColRef):
        # ColRef as a scalar operand is genuinely ambiguous — a column
        # is a sequence, not a value. Surface eval-error rather than
        # silently picking row 1.
        return _eval_error(ctx, cell,
                            "column reference cannot be used as a scalar operand; "
                            "use cell:Sheet!A1 or an aggregate like sum(col:Hours)")
    if isinstance(node, BinaryOp) and node.op in _ARITH_OPS:
        return eval_arithmetic(node, cell, ctx)
    return node  # raw value (test convenience)


def _resolve_cell_ref(node: CellRef, cell: ClassifiedCell, ctx: EvalContext) -> Any:
    """Resolve `cell:Sheet!A1` against `ctx.workbook`. Returns the
    cell's value coerced through `cell_types.classify` so date/error/
    number semantics match the rest of the evaluator. Falls back to an
    eval-error finding when the workbook is missing or the address is
    invalid.

    Honest scope: returns the bare value, NOT the `ClassifiedCell`.
    Cross-type comparisons (e.g. number-vs-date via `value > cell:H1`)
    fall through `_cmp`'s `except TypeError: return False` — same
    behaviour as every other comparison in the evaluator. This is
    documented and locked by `TestHonestScopeCmpTypeMismatch`."""
    if ctx.workbook is None:
        return _eval_error(ctx, cell, "cell-reference operand requires an active workbook")
    sheet_name = node.sheet or cell.sheet
    try:
        ws = ctx.workbook[sheet_name]
    except KeyError:
        return _eval_error(ctx, cell, f"cell-reference target sheet not found: {sheet_name!r}")
    try:
        target = ws[node.ref]
    except (KeyError, ValueError):
        return _eval_error(ctx, cell, f"cell-reference target invalid: {node.ref!r}")
    classified = classify(target, ctx.eval_opts or {})
    if classified.logical_type is LogicalType.ERROR:
        # Compare against an error cell — treat as eval-error rather
        # than silently swallowing the comparison.
        return _eval_error(ctx, cell,
                            f"cell-reference target is an Excel error cell: "
                            f"{sheet_name}!{node.ref}")
    return classified.value


def _resolve_aggregate(call: BuiltinCall, ctx: EvalContext, cell: ClassifiedCell) -> Any:
    if ctx.aggregate_cache is None:
        return _aggregate_unimplemented(ctx, cell, f"aggregate {call.name!r} requires F8 (003.12)")
    try:
        scope_node = call.args[0]
        entry = ctx.aggregate_cache.eval_aggregate(call, scope_node, ctx)
        # F8 owns its own counter increments; F7 only consumes entry.value.
        return getattr(entry, "value", None)
    except Exception as e:  # noqa: BLE001 — F8 surface boundary
        return _eval_error(ctx, cell, f"aggregate eval failed: {e}")


def _aggregate_unimplemented(ctx: EvalContext, cell: ClassifiedCell, why: str) -> Finding:
    return Finding(
        cell=f"{cell.sheet}!{cell.col}{cell.row}",
        sheet=cell.sheet, row=cell.row, column=cell.col,
        rule_id="rule-eval-error", severity="error", value=None,
        message=f"rule evaluation error: {why}",
    )


# === Arithmetic eval =======================================================

def eval_arithmetic(node: BinaryOp, cell: ClassifiedCell, ctx: EvalContext) -> Any:
    """SPEC §5.5.2 `+`/`-`/`*`/`/`; date-date → eval-error; div-by-zero → eval-error."""
    left = _resolve_operand(node.left, cell, ctx)
    if isinstance(left, Finding):
        return left
    right = _resolve_operand(node.right, cell, ctx)
    if isinstance(right, Finding):
        return right
    if isinstance(left, (datetime, date)) and isinstance(right, (datetime, date)):
        return _eval_error(ctx, cell, "date arithmetic between two dates not supported in v1")
    try:
        if node.op == "+":
            return left + right
        if node.op == "-":
            return left - right
        if node.op == "*":
            return left * right
        if node.op == "/":
            if right == 0:
                return _eval_error(ctx, cell, "division by zero in rule expression")
            return left / right
    except TypeError as e:
        return _eval_error(ctx, cell, f"type mismatch in arithmetic: {e}")
    raise TypeError(f"unknown arithmetic op: {node.op!r}")


def _eval_error(ctx: EvalContext, cell: ClassifiedCell, why: str) -> Finding:
    ctx.eval_errors += 1
    return Finding(
        cell=f"{cell.sheet}!{cell.col}{cell.row}",
        sheet=cell.sheet, row=cell.row, column=cell.col,
        rule_id="rule-eval-error", severity="error", value=None,
        message=f"rule evaluation error: {why}",
    )


# === Comparison helper ====================================================

def _cmp(left: Any, op: str, right: Any) -> bool:
    try:
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
    except TypeError:
        return False
    raise TypeError(f"unknown comparison op: {op!r}")


# === Regex eval (R9.c + R9.d) =============================================

def eval_regex(pattern: str, value: str, timeout_ms: int,
                ctx: EvalContext, rule_id: str) -> bool | Finding:
    """Compile-cached; per-cell timeout → `rule-eval-timeout` finding (R9.d)."""
    cached = ctx.regex_compile_cache.get(pattern)
    if cached is None:
        cached = regex_compile(pattern)
        ctx.regex_compile_cache[pattern] = cached
    try:
        return bool(cached.fullmatch(value, timeout=timeout_ms / 1000.0))
    except TimeoutError:
        ctx.regex_timeouts += 1
        return Finding(
            cell="", sheet="", row=None, column=None,
            rule_id=rule_id, severity="error", value=value,
            message=f"regex evaluation timed out (>{timeout_ms}ms)",
        )


def _eval_regex_predicate(node: RegexPredicate, cell: ClassifiedCell,
                            ctx: EvalContext) -> bool | Finding:
    if cell.logical_type is not LogicalType.TEXT:
        return False
    rule_id = ctx.rule.id if ctx.rule is not None else ""
    timeout_ms = int(ctx.regex_timeout_seconds * 1000)
    result = eval_regex(node.pattern, cell.value or "", timeout_ms, ctx, rule_id)
    if isinstance(result, Finding):
        # Re-stamp the synthetic finding with the cell's location.
        result.cell = f"{cell.sheet}!{cell.col}{cell.row}"
        result.sheet = cell.sheet
        result.row = cell.row
        result.column = cell.col
    return result


# === Message formatter (string.Template, NOT str.format) ==================

def format_message(template_str: str | None, cell: ClassifiedCell,
                    rule_id: str, value: Any, group: str | None = None) -> str:
    """SPEC §6.3 — `string.Template.safe_substitute` ($value/$row/$col/$cell/$sheet/$group).
    NOT `str.format` (attribute-access escape via `{0.__class__.__mro__}` is the vector)."""
    if template_str is None:
        template_str = f"rule {rule_id} failed"
    template = string.Template(template_str)
    cell_ref = f"{cell.sheet}!{cell.col}{cell.row}" if cell else ""
    mapping = {
        "value": "" if value is None else str(_jsonable(value)),
        "row": str(cell.row) if cell else "",
        "col": cell.col if cell else "",
        "cell": cell_ref,
        "sheet": cell.sheet if cell else "",
        "group": str(group) if group is not None else "",
    }
    return template.safe_substitute(mapping)

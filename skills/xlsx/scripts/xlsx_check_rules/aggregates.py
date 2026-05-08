"""F8 — Aggregate cache + evaluator.

SPEC §5.5 (cross-cell aggregates) + §5.6 (group-by) + §5.5.3 (cache).
Cache key = SHA-1 of canonical `(sheet_resolved | scope_canonical |
fn_name)` AFTER scope-canonicalisation via F4 `to_canonical_str`. The
caller MUST pre-resolve sheet (None → explicit) before computing the
key; F8 reads the resolved sheet from the resolved scope tree.

Replay determinism (R10.c, R10.d):
  - Per-cell skip / error events captured at first compute.
  - Subsequent rule consumers receive a "replay" stream.
  - Intra-rule dedup on `(rule_id, cell)` (defensive — recursive
    aggregates).
  - Inter-rule: NO dedup. Same cell skipped under N rules counts N
    times in `summary.skipped_in_aggregates` (one finding per rule).
"""
from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .ast_nodes import BuiltinCall, GroupByCheck, to_canonical_str
from .cell_types import LogicalType
from .exceptions import CellError

__all__ = [
    "AggregateCacheEntry",
    "AggregateCache",
    "eval_group_by",
    "_canonical_cache_key",
]


@dataclass
class AggregateCacheEntry:
    value: Any  # int | float | None (NaN if all-empty avg)
    skipped_cells: list[tuple[str, int, str]] = field(default_factory=list)
    error_cells: list[tuple[str, int, str]] = field(default_factory=list)
    cache_hits: int = 0
    # Intra-rule replay dedup state: (rule_id, (sheet, row, col))
    replay_dedup: set[tuple[str, tuple[str, int, str]]] = field(default_factory=set)


class AggregateCache:
    """Process-local cache; one instance per `_run` invocation."""

    def __init__(self) -> None:
        self._entries: dict[str, AggregateCacheEntry] = {}

    def eval_aggregate(self, call: BuiltinCall, scope_node: Any, ctx: Any) -> AggregateCacheEntry:
        """Cache-hit-or-compute. Replays per-cell skip/error events on hit."""
        key = _canonical_cache_key(call, scope_node)
        cached = self._entries.get(key)
        if cached is None:
            entry = _compute(call, scope_node, ctx)
            self._entries[key] = entry
            return entry
        cached.cache_hits += 1
        ctx.aggregate_cache_hits += 1
        _replay_events(cached, ctx)
        return cached


def _canonical_cache_key(call: BuiltinCall, scope_node: Any) -> str:
    """SHA-1 of `(sheet|scope_canonical|fn_name)`. The caller has already
    resolved sheet defaults (None → first visible) into the scope node
    via F6's resolver, so `to_canonical_str` produces a stable form."""
    sheet = getattr(scope_node, "sheet", "") or ""
    canonical = f"{sheet}|{to_canonical_str(scope_node)}|{call.name}"
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def _compute(call: BuiltinCall, scope_node: Any, ctx: Any) -> AggregateCacheEntry:
    """Walk scope cells once; partition numeric / error / skipped; reduce."""
    from .scope_resolver import resolve_scope

    fn = call.name
    sr = resolve_scope(scope_node, ctx.workbook, ctx.defaults, ctx.eval_opts)

    numeric: list[float] = []
    distinct: set[str] = set()
    skipped: list[tuple[str, int, str]] = []
    errors: list[tuple[str, int, str]] = []
    n_total = 0
    n_nonempty = 0
    n_errors = 0

    for cell in sr.cells:
        n_total += 1
        addr = (cell.sheet, cell.row, cell.col)
        if cell.logical_type is LogicalType.ERROR:
            errors.append(addr)
            n_errors += 1
            continue
        if cell.logical_type is LogicalType.EMPTY:
            continue
        n_nonempty += 1
        # count_distinct collects every non-empty cell as a canonical string.
        if fn == "count_distinct":
            distinct.add(_distinct_key(cell))
            continue
        if cell.logical_type is LogicalType.NUMBER:
            numeric.append(float(cell.value))
        elif cell.logical_type is LogicalType.BOOL:
            numeric.append(float(bool(cell.value)))
        else:
            # Non-numeric in a numeric aggregate — skip per SPEC §5.5.1.
            skipped.append(addr)

    value = _reduce(fn, numeric, n_total=n_total, n_nonempty=n_nonempty,
                    n_errors=n_errors, distinct=distinct)
    entry = AggregateCacheEntry(value=value, skipped_cells=skipped, error_cells=errors)
    # Replay events for the FIRST consuming rule too — same dedup contract
    # as cache hits; otherwise the first rule sees nothing while subsequent
    # rules see N type-mismatch findings (inconsistent semantics).
    _replay_events(entry, ctx)
    return entry


def _reduce(fn: str, numeric: list[float], *, n_total: int, n_nonempty: int,
             n_errors: int, distinct: set[str]) -> Any:
    if fn == "count":
        return n_total
    if fn == "count_nonempty":
        return n_nonempty
    if fn == "count_errors":
        return n_errors
    if fn == "count_distinct":
        return len(distinct)
    if not numeric:
        # SPEC §5.5.2: empty aggregate → nan for avg/median/stdev; for
        # min/max, return None (caller emits rule-eval-nan).
        return float("nan") if fn in ("avg", "mean", "median", "stdev") else None
    if fn == "sum":
        return sum(numeric)
    if fn in ("avg", "mean"):
        return statistics.mean(numeric)
    if fn == "median":
        return statistics.median(numeric)
    if fn == "stdev":
        if len(numeric) < 2:
            return float("nan")  # sample stdev needs n ≥ 2
        return statistics.stdev(numeric)
    if fn == "min":
        return min(numeric)
    if fn == "max":
        return max(numeric)
    if fn == "len":
        # `len(scope)` is documented but rarely used; alias of count_nonempty.
        return n_nonempty
    raise ValueError(f"unknown aggregate function: {fn!r}")


def _distinct_key(cell: Any) -> str:
    v = cell.value
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, CellError):
        return f"#err:{v.code}"
    return str(v)


def _replay_events(entry: AggregateCacheEntry, ctx: Any) -> None:
    """Re-emit per-cell skip events into the consuming rule's context.

    Intra-rule dedup on `(rule_id, addr)` keeps recursive aggregates
    from double-counting; inter-rule has no dedup (R10.d).

    Error cells (`error_cells`) do NOT get re-emitted here — the F7
    cell-error auto-emit path handles them on first encounter; replay
    must NOT double-count `summary.cell_errors`.
    """
    rule_id = ctx.rule.id if ctx.rule is not None else ""
    for addr in entry.skipped_cells:
        key = (rule_id, addr)
        if key in entry.replay_dedup:
            continue  # intra-rule dedup
        entry.replay_dedup.add(key)
        ctx.skipped_in_aggregates += 1
        if ctx.strict_aggregates:
            ctx.append_finding(_aggregate_type_mismatch_finding(addr, rule_id))


def _aggregate_type_mismatch_finding(addr: tuple[str, int, str], rule_id: str) -> Any:
    """Build a `Finding` (lazy import — F7 owns the dataclass)."""
    from .evaluator import Finding
    sheet, row, col = addr
    return Finding(
        cell=f"{sheet}!{col}{row}", sheet=sheet, row=row, column=col,
        rule_id="aggregate-type-mismatch", severity="error", value=None,
        message=(f"non-numeric cell skipped from aggregate (rule "
                 f"{rule_id!r} under --strict-aggregates)"),
    )


def eval_group_by(node: GroupByCheck, scope_result: Any, ctx: Any) -> dict[str | None, float]:
    """SPEC §5.6 — partition `scope_result.cells` by the value of column
    `node.key` in the same row, aggregate per group.

    Empty group-key cells form a synthetic group keyed `None` (rendered
    as `null` / `<empty>` in JSON). Error group-key cells are skipped
    and counted in `summary.skipped_in_aggregates`.
    """
    from .scope_resolver import resolve_scope
    from .ast_nodes import ColRef

    # Resolve the key column (case-sensitive header lookup).
    is_letter = node.key.isalpha() and node.key.isupper()
    key_col_node = ColRef(scope_result.sheet_name, node.key, is_letter)
    key_sr = resolve_scope(key_col_node, ctx.workbook, ctx.defaults, ctx.eval_opts)
    # L2 follow-up (Sarcasmotron iter-2): the parent eval_rule filter
    # for `--visible-only` is bypassed for group-by because eval_rule
    # short-circuits at the rule level. Apply the same filter here on
    # BOTH the key column and the data scope so hidden rows do NOT
    # contribute to group totals (matches per-cell rule semantics).
    visible_only = bool((ctx.eval_opts or {}).get("visible_only", False))
    # Map row -> group key (or sentinel).
    row_to_group: dict[int, Any] = {}
    for c in key_sr.cells:
        if visible_only and c.is_hidden:
            continue
        if c.logical_type is LogicalType.ERROR:
            row_to_group[c.row] = "__ERROR__"
        elif c.logical_type is LogicalType.EMPTY:
            row_to_group[c.row] = None
        else:
            row_to_group[c.row] = c.value

    # Partition the scope cells into groups (skipping ERROR-group rows).
    groups: dict[Any, list[float]] = {}
    skipped: list[tuple[str, int, str]] = []
    for cell in scope_result.cells:
        if visible_only and cell.is_hidden:
            continue
        g = row_to_group.get(cell.row)
        if g == "__ERROR__":
            skipped.append((cell.sheet, cell.row, cell.col))
            continue
        if cell.logical_type is LogicalType.NUMBER:
            groups.setdefault(g, []).append(float(cell.value))
        elif cell.logical_type is LogicalType.BOOL:
            groups.setdefault(g, []).append(float(bool(cell.value)))
        elif cell.logical_type is LogicalType.EMPTY:
            continue
        else:
            skipped.append((cell.sheet, cell.row, cell.col))

    fn = node.fn  # "sum_by" / "count_by" / "avg_by"
    result: dict[Any, float] = {}
    for g, nums in groups.items():
        if fn == "sum_by":
            result[g] = sum(nums)
        elif fn == "count_by":
            result[g] = len(nums)
        elif fn == "avg_by":
            result[g] = statistics.mean(nums) if nums else float("nan")
        else:
            raise ValueError(f"unknown group-by function: {fn!r}")
    # Surface skipped cells via ctx (consistent with cross-cell aggregates).
    rule_id = ctx.rule.id if ctx.rule is not None else ""
    for addr in skipped:
        ctx.skipped_in_aggregates += 1
        if ctx.strict_aggregates:
            ctx.append_finding(_aggregate_type_mismatch_finding(addr, rule_id))
    return result

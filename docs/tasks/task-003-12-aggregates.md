# Task 003.12: `aggregates.py` (F8 — cross-cell + group-by + SHA-1 cache + replay)

## Use Case Connection
- **R4.e, R4.f** (§5.5 cross-cell aggregates, §5.6 group-by).
- **R10.a–R10.e** (cache canonical key, entry shape, replay determinism, intra-rule dedup, `aggregate_cache_hits` counter).

## Task Goal
Implement F8 — the aggregate evaluator + cache layer. Computes `sum/avg/min/max/median/stdev/count*` with SHA-1 cache key normalisation, captures per-cell skip/error events, and replays them deterministically into each consuming rule (intra-rule dedup; inter-rule no-dedup).

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_check_rules/aggregates.py`

```python
"""F8 — Aggregate cache + evaluator.

SPEC §5.5 (cross-cell aggregates) + §5.6 (group-by) + §5.5.3 (cache).
Cache key = SHA-1 of canonical (sheet_resolved, scope_canonical,
fn_name) AFTER whitespace/quote normalisation, header→letter
resolution, and Excel-Tables fallback equivalence.

Replay determinism (R10.c, R10.d):
  - Per-cell skip/error events captured at first compute.
  - Subsequent rule consumers receive a "replay" stream of those
    events into their own finding context.
  - Intra-rule dedup on (rule_id, cell) pair (defensive, e.g.
    recursive aggregates).
  - Inter-rule: no dedup. Same cell skipped under N rules counts
    N times in summary.skipped_in_aggregates (one finding per rule).
"""
from __future__ import annotations
import hashlib
import statistics
from dataclasses import dataclass, field
from typing import Any
from .ast_nodes import BuiltinCall, ColRef, GroupByCheck, RuleSpec, to_canonical_str
from .cell_types import LogicalType
from .exceptions import AggregateTypeMismatch

__all__ = [
    "AggregateCacheEntry", "AggregateCache",
    "eval_aggregate", "eval_group_by", "_canonical_cache_key",
]

@dataclass
class AggregateCacheEntry:
    value: Any  # int | float | None (NaN if all-empty avg)
    skipped_cells: list[tuple[str, int, str]]  # (sheet, row, col)
    error_cells: list[tuple[str, int, str]]
    cache_hits: int = 0
    # Intra-rule replay dedup state: (rule_id, (sheet,row,col)) pairs already replayed
    replay_dedup: set[tuple[str, tuple[str, int, str]]] = field(default_factory=set)

class AggregateCache:
    """Process-local cache. Not persisted across runs."""
    def __init__(self):
        self._entries: dict[str, AggregateCacheEntry] = {}

    def get_or_compute(self, key: str, compute_fn) -> AggregateCacheEntry:
        if key in self._entries:
            entry = self._entries[key]
            entry.cache_hits += 1
            return entry
        entry = compute_fn()
        self._entries[key] = entry
        return entry

def _canonical_cache_key(call_node: BuiltinCall, scope_node, ctx) -> str:
    """SHA-1 of canonical (sheet_resolved, scope_canonical, fn_name).
    All header→letter and Table-fallback resolution happens BEFORE
    canonicalisation (caller resolves; this fn just hashes)."""
    sheet = ctx.resolve_sheet_for_scope(scope_node)
    scope_str = to_canonical_str(scope_node)  # F4 helper
    fn = call_node.name
    canonical = f"{sheet}|{scope_str}|{fn}"
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()

def eval_aggregate(call_node: BuiltinCall, scope_node, ctx) -> AggregateCacheEntry:
    """Cache-hit-or-compute. R10.b cache-entry shape.

    On cache hit, replay per-cell skip/error events into ctx (intra-rule
    dedup; inter-rule no-dedup per R10.d).
    """
    key = _canonical_cache_key(call_node, scope_node, ctx)
    entry = ctx.aggregate_cache.get_or_compute(key, lambda: _compute(call_node, scope_node, ctx))
    if entry.cache_hits > 0:  # this is a replay
        ctx.aggregate_cache_hits += 1
        _replay_events(entry, ctx)
    return entry

def _compute(call_node: BuiltinCall, scope_node, ctx) -> AggregateCacheEntry:
    """First-time compute. Walk scope cells, separate numeric/error/skip."""
    raise NotImplementedError

def _replay_events(entry: AggregateCacheEntry, ctx) -> None:
    """Re-emit per-cell skip/error events into the consuming rule's
    finding stream. Intra-rule dedup on (rule_id, (sheet,row,col))."""
    rule_id = ctx.rule.id
    for cell_tuple in entry.skipped_cells:
        if (rule_id, cell_tuple) in entry.replay_dedup:
            continue  # intra-rule dedup
        entry.replay_dedup.add((rule_id, cell_tuple))
        ctx.skipped_in_aggregates += 1
        if ctx.strict_aggregates:
            ctx.append_finding(_aggregate_type_mismatch_finding(cell_tuple, rule_id))
    for cell_tuple in entry.error_cells:
        # error_cells contribute to summary.cell_errors via the F7 auto-emit
        # path on first encounter; replay does NOT double-count cell_errors.
        pass

def eval_group_by(node: GroupByCheck, scope_result, ctx) -> dict[str, float]:
    """SPEC §5.6 — partition by KEY column, aggregate per group.
    Empty group key forms a synthetic <empty> group (group=None in JSON)."""
    raise NotImplementedError
```

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Remove `@unittest.skip` from `TestAggregates`. Add:
- `test_canonical_cache_key_normalises_whitespace` — `sum( col:Hours )` and `sum(col:Hours)` produce same key.
- `test_canonical_cache_key_table_fallback_equivalence` — `col:Hours` (resolved through Table T1) and `table:T1[Hours]` (same cells) produce same key.
- `test_cache_replay_increments_counter` (R10.e canary anchor) — fixture #19 (5 rules sharing `sum(col:Hours)`) → `summary.aggregate_cache_hits == 4` (5 references − 1 fresh compute = 4 replays).
- `test_cache_replay_dedups_intra_rule` — single rule with recursive aggregate; replay counted ONCE per `(rule_id, cell)` pair.
- `test_cache_replay_no_dedup_inter_rule` (fixture #19a) — 1 cell × 2 rules sharing scope, `--strict-aggregates` → `summary.skipped_in_aggregates == 2`; 2 findings with `rule_id: aggregate-type-mismatch`.
- `test_disable_cache_drops_counter` (saboteur #9 anchor) — manually disabled cache; `summary.aggregate_cache_hits == 0`; counter assertion is CI-deterministic regardless of timing.
- `test_group_by_empty_key_creates_empty_group` — group-key column has empties → synthetic group with `group=None` in finding JSON.
- `test_group_by_error_key_skipped` — group-key cell is `error` → counted in `skipped_in_aggregates`.
- `test_aggregate_skips_text_cells_silently` (R4.e) — `sum(col:Hours)` over column with one text cell skips silently; counted in `skipped_in_aggregates`.
- `test_aggregate_strict_mode_emits_findings` — same fixture with `--strict-aggregates` → finding `aggregate-type-mismatch`.

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Append fixtures #11, #12, #18, #19, #19a, #20, #21.

## Test Cases
- Unit: ~ 11 new tests; all pass.
- Battery: fixtures #11, #12, #18, #19, #19a, #20, #21 transition from xfail to xpass.

## Acceptance Criteria
- [ ] `aggregates.py` complete (≤ 250 LOC).
- [ ] `summary.aggregate_cache_hits` is the canary anchor (saboteur #9 trips it).
- [ ] Replay dedup intra-rule yes / inter-rule no (R10.d locked).
- [ ] All `TestAggregates` tests green.
- [ ] `validate_skill.py` exits 0.

## Notes
- The cache lifetime is the run — one `AggregateCache()` instantiation per `_run` invocation. Tests instantiate ad-hoc.
- `_compute` walks scope cells once; classifies each via `cell_types.classify`; partitions into numeric / error / skipped (for `sum/avg/...` only — `count` counts everything including empty/error).
- For `count_distinct`: collect into a `set` of canonical-string-form values (date as ISO string, numeric as Python `int`/`float`, text as the raw string after whitespace strip).
- `stdev` uses `statistics.stdev` (sample stdev, n-1); aggregates of 0 or 1 numeric cells → `nan` → emit finding `rule-eval-nan` per SPEC §5.5.2.

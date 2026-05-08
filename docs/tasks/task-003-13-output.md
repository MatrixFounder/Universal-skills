# Task 003.13: `output.py` (F9 — JSON envelope + sentinel sort + caps + M2 invariant)

## Use Case Connection
- **I4.1** (findings envelope schema + sort).
- **I4.2** (finding caps).
- **I4.4** (stderr/stdout split — emit side; routing side in F11).
- **R5.a–R5.g** (envelope, summary keys, finding fields, sort, grouped shape, max-findings, summarize-after).

## Task Goal
Implement F9 — produce the `{ok, schema_version, summary, findings}` JSON envelope (stdout when `--json`) and the human-readable stderr report. Owns deterministic 5-tuple sort with type-homogeneous sentinels per §7.1.2, finding caps, `--summarize-after` collapse, and the **M2 architect-locked invariant**: emit all-three-keys on every code path so xlsx-6 batch.py:122 round-trips cleanly.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx_check_rules/output.py`

```python
"""F9 — Output emitter (JSON envelope + stderr human report).

M2 invariant (architect-locked): the JSON envelope MUST always carry
{ok, summary, findings} top-level keys, on every code path including
--max-findings 0, --severity-filter, --require-data on empty workbook,
and --timeout partial-flush. xlsx-6 batch.py:122 requires exactly this
shape; deviations break the pipe contract.

Sort key per SPEC §7.1.2: 5-tuple (sheet, row, column, rule_id, group)
with type-homogeneous sentinels for grouped findings — row=2**31-1,
column='￿', group=str. Per-cell findings: group="".
"""
from __future__ import annotations
import json
import sys
from dataclasses import asdict
from typing import Any, Iterable, TextIO
from .constants import (
    SCHEMA_VERSION, SEVERITY_LEVELS,
    MAX_FINDINGS_SENTINEL_ROW, MAX_FINDINGS_SENTINEL_COL,
    DEFAULT_MAX_FINDINGS, DEFAULT_SUMMARIZE_AFTER,
)
from .evaluator import Finding

__all__ = [
    "emit_findings", "apply_max_findings", "apply_summarize_after",
    "emit_human_report", "build_envelope", "_sort_key",
]

def _sort_key(f: Finding) -> tuple:
    """Type-homogeneous 5-tuple per SPEC §7.1.2."""
    is_grouped = (f.row is None)
    return (
        f.sheet,
        MAX_FINDINGS_SENTINEL_ROW if is_grouped else f.row,
        MAX_FINDINGS_SENTINEL_COL if is_grouped else f.column,
        f.rule_id,
        f.group if (is_grouped and f.group is not None) else "",
    )

def apply_max_findings(findings: list[Finding], n: int) -> tuple[list[Finding], bool]:
    """Cap; append synthetic max-findings-reached when truncated.
    n=0 disables cap (returns full list, truncated=False).
    """
    if n == 0:
        return findings, False
    if len(findings) <= n:
        return findings, False
    capped = findings[: n - 1]  # leave room for synthetic
    capped.append(Finding(
        cell="",
        sheet="",
        row=MAX_FINDINGS_SENTINEL_ROW,
        column=MAX_FINDINGS_SENTINEL_COL,
        rule_id="max-findings-reached",
        severity="info",
        value=None,
        message=f"Output truncated; {n} findings shown of {len(findings)} total",
    ))
    return capped, True

def apply_summarize_after(findings: list[Finding], n_per_rule: int) -> list[Finding]:
    """Collapse runs of same rule_id once N emitted.
    Synthetic entry carries `count` and `sample_cells[10]`.
    n=0 disables.
    """
    raise NotImplementedError

def build_envelope(findings: list[Finding], summary: dict, severity_filter: set | None) -> dict:
    """M2: ALWAYS produces {ok, schema_version, summary, findings}.

    severity_filter: optional set of severities to retain in findings[];
    summary.* counters are NOT filtered (they are unfiltered totals
    per SPEC §12.1).
    """
    visible = findings
    if severity_filter:
        visible = [f for f in findings if f.severity in severity_filter]
    return {
        "ok": summary["errors"] == 0,
        "schema_version": SCHEMA_VERSION,
        "summary": summary,
        "findings": [_finding_to_dict(f) for f in visible],
    }

def _finding_to_dict(f: Finding) -> dict:
    """Convert Finding -> JSON dict per SPEC §7.1.1.
    Per-cell findings emit row/column as int/str; grouped findings
    emit row=null, column=null. Sentinels exist only inside _sort_key.
    """
    d = {
        "cell": f.cell,
        "sheet": f.sheet,
        "row": f.row,  # null for grouped (already None in dataclass)
        "column": f.column,
        "rule_id": f.rule_id,
        "severity": f.severity,
        "value": f.value,
        "message": f.message,
    }
    if f.expected is not None:
        d["expected"] = f.expected
    if f.tolerance is not None:
        d["tolerance"] = f.tolerance
    if f.group is not None:
        d["group"] = f.group
    return d

def emit_findings(findings: list[Finding], summary: dict, opts,
                   stdout: TextIO = None, stderr: TextIO = None) -> None:
    """Emit JSON envelope to stdout when opts.json_mode; emit human
    report to stderr in either mode.

    Always flushes after emit (M-2 architect lock for partial-flush
    safety on timeout — _partial_flush in F11 calls emit_findings then
    fp.flush()).
    """
    if stdout is None:
        stdout = sys.stdout
    if stderr is None:
        stderr = sys.stderr
    sorted_f = sorted(findings, key=_sort_key)
    capped, truncated = apply_max_findings(sorted_f, opts.max_findings)
    summary["truncated"] = truncated
    if opts.summarize_after > 0:
        capped = apply_summarize_after(capped, opts.summarize_after)
    severity_filter = (set(opts.severity_filter)
                        if opts.severity_filter else None)
    envelope = build_envelope(capped, summary, severity_filter)
    if opts.json_mode:
        json.dump(envelope, stdout, separators=(",", ":"), sort_keys=False, default=_json_default)
        stdout.write("\n")
        stdout.flush()
    emit_human_report(capped, severity_filter, stderr)

def emit_human_report(findings, severity_filter, stderr) -> None:
    """rule_id / cell / severity / message lines."""
    raise NotImplementedError

def _json_default(o: Any) -> Any:
    """Handle datetime, CellError, Decimal -> JSON-friendly forms."""
    raise NotImplementedError
```

#### File: `skills/xlsx/scripts/tests/test_xlsx_check_rules.py`

Remove `@unittest.skip` from `TestOutput`. Critical tests:
- `test_envelope_always_three_keys` (M2 anchor) — `build_envelope([], {"errors":0,...}, None)` returns dict with `{ok, schema_version, summary, findings}` keys regardless of input.
- `test_sort_key_type_homogeneous` — mixed per-cell and grouped findings sort without `TypeError`.
- `test_sort_per_cell_before_grouped` — per-cell findings come first within a sheet (sentinel `row=2**31-1` pushes grouped to end).
- `test_sort_deterministic_across_runs` — same input, two `sorted()` calls produce identical output.
- `test_max_findings_zero_disables_cap` (M2 / fixture #39b anchor) — `apply_max_findings([f]*5000, 0)` → all 5000, `truncated=False`.
- `test_max_findings_appends_synthetic` — N=2 with 5 findings → returns 2 entries, last is `max-findings-reached`.
- `test_summarize_after_collapses_per_rule_id` — 200 findings of same rule_id, N=10 → 11 entries (10 originals + 1 summary with `count=190`, `sample_cells=[first 10]`).
- `test_grouped_finding_emits_null_row_column` — finding with `row=None` → JSON dict has `"row": None` (becomes `null`).
- `test_severity_filter_does_not_change_summary` (R5.b stability promise) — `severity_filter={'error'}` filters `findings[]` but `summary.warnings` stays unfiltered.
- `test_envelope_ok_true_iff_no_errors` — summary `errors=0, warnings=N` → `ok=True`; `errors=1` → `ok=False`.
- `test_partial_flush_envelope_well_formed` (M2) — simulate timeout midway: a partial findings list still produces a well-formed all-three-keys envelope.
- `test_envelope_xlsx6_round_trip` (M2 / fixture #39 contract) — `json.dumps(envelope) | json.loads(...)` reconstructs a dict whose keyset is a superset of `{"ok","summary","findings"}` (xlsx-6 batch.py:122 gate).

#### File: `skills/xlsx/scripts/tests/test_e2e.sh`

Append fixture #1 (clean-pass) full E2E — `xlsx_check_rules.py clean-pass.xlsx --rules simple.rules.json --json` exits 0 and outputs valid envelope.

## Test Cases
- Unit: ~ 12 new tests; all pass.
- Battery: fixture #1 transitions from xfail to xpass; deterministic golden output asserted.

## Acceptance Criteria
- [ ] `output.py` complete (≤ 250 LOC).
- [ ] M2 invariant test passes.
- [ ] Type-homogeneous sort (no `TypeError` on grouped+per-cell mix).
- [ ] `--max-findings 0` disables cap; `--max-findings N>0` appends synthetic.
- [ ] All `TestOutput` tests green.
- [ ] `validate_skill.py` exits 0.

## Notes
- `json.dump(..., separators=(",", ":"))` keeps the output compact (no extra whitespace) — golden-file-friendly. `sort_keys=False` because we want our explicit ordering (`ok, schema_version, summary, findings`), not alphabetical.
- The `_finding_to_dict` order matters for golden comparisons. Use a deterministic dict order that Python 3.7+ preserves (insertion order). The order in the function body IS the JSON order.
- For `_json_default`: `datetime` → ISO string; `CellError` → its `code` string; `Decimal` → `float(d)`; anything else → `str(o)` as a fallback rather than raising (defense against unexpected value types reaching the JSON serializer).
- The synthetic `max-findings-reached` finding uses sentinel `row` and `column` so it sorts AFTER all grouped findings. Document this; tests pin it.

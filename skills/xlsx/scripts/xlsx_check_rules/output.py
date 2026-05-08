"""F9 — Output emitter (JSON envelope + stderr human report).

M2 invariant (architect-locked, `docs/reviews/architecture-003-review.md`):
the JSON envelope MUST always carry `{ok, summary, findings}` top-level
keys, on every code path including `--max-findings 0`,
`--severity-filter`, `--require-data` on empty workbook, and
`--timeout` partial-flush. xlsx-6 batch.py:122 requires exactly this
shape; deviations break the pipe contract.

Sort key per SPEC §7.1.2: 5-tuple `(sheet, row, column, rule_id,
group)` with type-homogeneous sentinels for grouped findings —
`row=2**31-1`, `column='\\uFFFF'`, `group=str`. Per-cell findings carry
`group=""` so the tuples are comparable.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any, TextIO

from .constants import (
    MAX_FINDINGS_SENTINEL_COL,
    MAX_FINDINGS_SENTINEL_ROW,
    SCHEMA_VERSION,
)
from .evaluator import Finding
from .exceptions import CellError

__all__ = [
    "emit_findings",
    "apply_max_findings",
    "apply_summarize_after",
    "emit_human_report",
    "build_envelope",
]


# === Sort key (SPEC §7.1.2 type-homogeneous sentinels) ====================

def _sort_key(f: Finding) -> tuple[Any, ...]:
    is_grouped = (f.row is None)
    return (
        f.sheet or "",
        MAX_FINDINGS_SENTINEL_ROW if is_grouped else f.row,
        MAX_FINDINGS_SENTINEL_COL if is_grouped else (f.column or ""),
        f.rule_id,
        f.group if (is_grouped and f.group is not None) else "",
    )


# === Finding caps ==========================================================

def apply_max_findings(findings: list[Finding], n: int) -> tuple[list[Finding], bool]:
    """Cap at `n` findings; append synthetic `max-findings-reached`.

    `n=0` disables the cap (returns full list, `truncated=False`).
    `n>0` AND `len(findings) > n`: returns `n` entries; the last one is
    the synthetic info finding. Otherwise returns the input unchanged.
    """
    if n == 0 or len(findings) <= n:
        return findings, False
    capped = list(findings[: n - 1])  # leave room for synthetic
    capped.append(Finding(
        cell="", sheet="",
        row=MAX_FINDINGS_SENTINEL_ROW,
        column=MAX_FINDINGS_SENTINEL_COL,
        rule_id="max-findings-reached", severity="info", value=None,
        message=f"Output truncated; {n} findings shown of {len(findings)} total",
    ))
    return capped, True


def apply_summarize_after(findings: list[Finding], n_per_rule: int) -> list[Finding]:
    """Per-`rule_id` collapse: once N findings of a rule have been emitted,
    the remainder collapse into a single synthetic entry carrying `count`
    (number collapsed) and `sample_cells` (first 10 collapsed cell refs).

    `n_per_rule=0` disables the collapse (returns input unchanged).
    """
    if n_per_rule <= 0:
        return findings

    seen: dict[str, int] = {}
    overflow: dict[str, list[Finding]] = {}
    out: list[Finding] = []
    for f in findings:
        seen[f.rule_id] = seen.get(f.rule_id, 0) + 1
        if seen[f.rule_id] <= n_per_rule:
            out.append(f)
        else:
            overflow.setdefault(f.rule_id, []).append(f)
    for rule_id, extras in overflow.items():
        sample_cells = [e.cell for e in extras[:10]]
        # Place the synthetic where the FIRST overflow would have lived.
        synthetic = Finding(
            cell=extras[0].sheet or "",
            sheet=extras[0].sheet or "",
            row=MAX_FINDINGS_SENTINEL_ROW,
            column=MAX_FINDINGS_SENTINEL_COL,
            rule_id=rule_id,
            severity=extras[0].severity,
            value=None,
            message=(f"{len(extras)} additional findings of rule_id "
                     f"{rule_id!r} collapsed by --summarize-after"),
        )
        # Stash count + sample_cells on the synthetic via attribute attach
        # (Finding is a dataclass; we extend ad-hoc fields via setattr,
        # surfaced through `_finding_to_dict` below).
        synthetic.count = len(extras)  # type: ignore[attr-defined]
        synthetic.sample_cells = sample_cells  # type: ignore[attr-defined]
        out.append(synthetic)
    return out


# === Envelope construction (M2 invariant) =================================

def build_envelope(findings: list[Finding], summary: dict[str, Any],
                    severity_filter: set[str] | None) -> dict[str, Any]:
    """M2 architect-locked invariant — ALWAYS emit
    `{ok, schema_version, summary, findings}` top-level keys.

    `severity_filter`: optional set of severities to retain in
    `findings[]`. `summary.*` counters are NOT filtered (they are
    unfiltered totals per SPEC §12.1 stability promise).
    """
    visible = findings
    if severity_filter:
        visible = [f for f in findings if f.severity in severity_filter]
    return {
        "ok": summary.get("errors", 0) == 0,
        "schema_version": SCHEMA_VERSION,
        "summary": summary,
        "findings": [_finding_to_dict(f) for f in visible],
    }


def _finding_to_dict(f: Finding) -> dict[str, Any]:
    """Convert `Finding` → JSON dict per SPEC §7.1.1.

    Per-cell findings emit `row`/`column` as int/str. Grouped findings
    (row is None) emit `row=null`, `column=null` — sentinels live ONLY
    in `_sort_key`, never on the wire.
    """
    is_grouped = (f.row is None) or (f.row == MAX_FINDINGS_SENTINEL_ROW)
    d: dict[str, Any] = {
        "cell": f.cell,
        "sheet": f.sheet,
        "row": None if is_grouped else f.row,
        "column": None if is_grouped else f.column,
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
    # Optional summarize-after extension fields.
    count = getattr(f, "count", None)
    if count is not None:
        d["count"] = count
    sample_cells = getattr(f, "sample_cells", None)
    if sample_cells is not None:
        d["sample_cells"] = sample_cells
    return d


# === Top-level emit (stdout JSON + stderr human) ==========================

def emit_findings(findings: list[Finding], summary: dict[str, Any], opts: Any,
                   stdout: TextIO | None = None, stderr: TextIO | None = None) -> None:
    """Sort, cap, summarise, then emit. Stdout = JSON envelope when
    `opts.json_mode`; stderr = human report in either mode. Always
    flushes (M-2 architect lock for partial-flush safety on timeout)."""
    if stdout is None:
        stdout = sys.stdout
    if stderr is None:
        stderr = sys.stderr

    sorted_f = sorted(findings, key=_sort_key)
    capped, truncated = apply_max_findings(sorted_f, getattr(opts, "max_findings", 0))
    summary["truncated"] = truncated
    n_per_rule = getattr(opts, "summarize_after", 0)
    if n_per_rule > 0:
        capped = apply_summarize_after(capped, n_per_rule)

    sf = getattr(opts, "severity_filter", None)
    severity_filter = set(sf) if sf else None
    envelope = build_envelope(capped, summary, severity_filter)

    if getattr(opts, "json_mode", False):
        json.dump(envelope, stdout, separators=(",", ":"),
                  sort_keys=False, default=_json_default)
        stdout.write("\n")
        stdout.flush()

    emit_human_report(capped, severity_filter, stderr)


def emit_human_report(findings: list[Finding], severity_filter: set[str] | None,
                        stderr: TextIO) -> None:
    """One line per finding: `severity rule_id @ cell — message`."""
    visible = findings
    if severity_filter:
        visible = [f for f in findings if f.severity in severity_filter]
    for f in visible:
        ref = f.cell or f.sheet or ""
        stderr.write(f"{f.severity:7s} {f.rule_id} @ {ref} — {f.message}\n")
    stderr.flush()


def _json_default(o: Any) -> Any:
    """Coerce non-JSON-native values to a serialisable form."""
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, date):
        return o.isoformat()
    if isinstance(o, CellError):
        return o.code
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, set):
        return sorted(o)
    return str(o)  # defensive fallback — never raise from the serializer

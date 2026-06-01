#!/usr/bin/env python3
"""Append one row to improvement_history.tsv (modeled on autoresearch results.tsv).

Columns (tab-separated):
  iter  score  delta  status  tier  change_summary  snapshot_ref

`delta` is printed with a sign (e.g. +0.050) or "—" for the baseline row.
The header is written automatically when the file does not yet exist.
"""

from __future__ import annotations

import argparse
from pathlib import Path

COLUMNS = ["iter", "score", "delta", "status", "tier", "change_summary", "snapshot_ref"]


def _fmt_delta(delta: float | None) -> str:
    return "—" if delta is None else f"{delta:+.3f}"


def _sanitize(value: str) -> str:
    """Tabs/newlines would break the TSV; collapse them to spaces."""
    return str(value).replace("\t", " ").replace("\n", " ").strip()


def log_iteration(
    workspace: Path,
    *,
    iteration: int,
    score: float,
    delta: float | None,
    status: str,
    tier: str = "",
    change_summary: str = "",
    snapshot_ref: str = "",
) -> Path:
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    tsv = workspace / "improvement_history.tsv"
    new_file = not tsv.exists()
    row = [
        str(iteration),
        f"{score:.3f}",
        _fmt_delta(delta),
        _sanitize(status),
        _sanitize(tier),
        _sanitize(change_summary),
        _sanitize(snapshot_ref),
    ]
    with tsv.open("a", encoding="utf-8") as f:
        if new_file:
            f.write("\t".join(COLUMNS) + "\n")
        f.write("\t".join(row) + "\n")
    return tsv


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a row to improvement_history.tsv")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--iter", type=int, required=True)
    parser.add_argument("--score", type=float, required=True)
    parser.add_argument("--delta", type=float, default=None)
    parser.add_argument("--status", required=True)
    parser.add_argument("--tier", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument("--snapshot-ref", default="")
    args = parser.parse_args()
    path = log_iteration(
        Path(args.workspace),
        iteration=args.iter,
        score=args.score,
        delta=args.delta,
        status=args.status,
        tier=args.tier,
        change_summary=args.summary,
        snapshot_ref=args.snapshot_ref,
    )
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

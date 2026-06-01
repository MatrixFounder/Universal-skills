#!/usr/bin/env python3
"""Deterministically classify a proposal's tier from its size.

Tier is computed here — NOT chosen by the Proposer — to avoid the conflict of
interest where a Proposer under-reports size to get an easier pipeline.

Rules (first match wins):
  - large   : touches >= 2 sections, OR >= 50 changed lines (big single-section
              rewrite / deletion still counts as large so it gets extra review)
  - medium  : >= 20 changed lines
  - small   : >= 5 changed lines
  - trivial : otherwise

Reads a proposal JSON (file arg or stdin) and prints the tier.
"""

from __future__ import annotations

import argparse
import json
import sys

try:
    from scripts.common import (  # type: ignore
        DIFF_DATASET_OP, DIFF_FRONTMATTER_FIELD, DIFF_SECTION_REPLACE, DIFF_TEXT_REPLACE,
        TIER_LARGE, TIER_MEDIUM, TIER_SMALL, TIER_TRIVIAL,
    )
except ImportError:
    from common import (
        DIFF_DATASET_OP, DIFF_FRONTMATTER_FIELD, DIFF_SECTION_REPLACE, DIFF_TEXT_REPLACE,
        TIER_LARGE, TIER_MEDIUM, TIER_SMALL, TIER_TRIVIAL,
    )


def _diff_stats(proposal: dict, old_section_lines: int = 0) -> tuple[int, int]:
    """Return (sections_changed, changed_lines).

    For section-replace, changed_lines counts the LARGER of added vs removed
    lines so a big deletion (replacing a 50-line section with 3 lines) is
    classified by its true blast radius — `old_section_lines` is the size of
    the section being replaced (0 when unknown).
    """
    fmt = proposal.get("diff_format")

    if fmt == DIFF_SECTION_REPLACE:
        added = len((proposal.get("new_content", "") or "").splitlines())
        return 1, max(added, old_section_lines)

    if fmt == DIFF_FRONTMATTER_FIELD:
        return 1, 1  # a single scalar field — always trivial

    if fmt == DIFF_TEXT_REPLACE:
        find_lines = len((proposal.get("find", "") or "").splitlines())
        repl_lines = len((proposal.get("replace", "") or "").splitlines())
        return 1, max(find_lines, repl_lines)

    if fmt == DIFF_DATASET_OP:
        ops = proposal.get("dataset_ops", []) or []
        return (2 if len(ops) >= 2 else 1), len(ops)

    # Unknown format → treat conservatively as a single small change.
    return 1, 1


def measure_tier(proposal: dict, old_section_lines: int = 0) -> str:
    sections, lines = _diff_stats(proposal, old_section_lines)
    if sections >= 2 or lines >= 50:
        return TIER_LARGE
    if lines >= 20:
        return TIER_MEDIUM
    if lines >= 5:
        return TIER_SMALL
    return TIER_TRIVIAL


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify proposal tier by size")
    parser.add_argument("proposal", nargs="?", help="proposal JSON file (default: stdin)")
    args = parser.parse_args()
    raw = open(args.proposal, encoding="utf-8").read() if args.proposal else sys.stdin.read()
    print(measure_tier(json.loads(raw)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

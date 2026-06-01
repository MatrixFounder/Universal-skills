#!/usr/bin/env python3
"""Deterministic quality scorer for an eval dataset (evals.json).

Produces a score in [0, 1] from five transparent components. No LLM, no API —
this is a pure function of the file, so it is fully unit-testable and gives a
stable signal for the dataset-improvement loop.

Components (weighted):
  schema      0.30  every case has id + prompt-text + an expectation signal
  forbidden   0.25  negative coverage (should_trigger=false / forbidden_expectations)
  uniqueness  0.20  fraction of non-duplicate prompts
  diversity   0.15  1 - average pairwise bigram overlap (Jaccard)
  count       0.10  min(1, n / TARGET_N)

Handles both trigger-style cases ({query, should_trigger}) and functional-style
cases ({id, prompt, expectations, forbidden_expectations}).
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

try:
    from scripts.common import resolve_dataset_items  # type: ignore
except ImportError:
    from common import resolve_dataset_items

TARGET_N = 5
WEIGHTS = {"schema": 0.30, "forbidden": 0.25, "uniqueness": 0.20, "diversity": 0.15, "count": 0.10}
# Above this many cases the exact O(n^2) pairwise diversity is replaced by a
# deterministic fixed-stride sample to keep scoring cheap as a dataset grows.
DIVERSITY_PAIR_CAP = 100


def _load_items(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items, _key = resolve_dataset_items(data)
    return [d for d in items if isinstance(d, dict)]


def _prompt_text(item: dict) -> str:
    return str(item.get("query") or item.get("prompt") or "").strip()


def _has_expectation(item: dict) -> bool:
    return bool(item.get("expectations")) or ("should_trigger" in item)


def _is_negative(item: dict) -> bool:
    if item.get("should_trigger") is False:
        return True
    return bool(item.get("forbidden_expectations"))


def _bigrams(text: str) -> set[str]:
    tokens = text.lower().split()
    return set(zip(tokens, tokens[1:])) if len(tokens) > 1 else set(tokens)


def score_dataset(path: Path) -> dict:
    items = _load_items(path)
    n = len(items)
    if n == 0:
        return {"score": 0.0, "n": 0, "components": {k: 0.0 for k in WEIGHTS}}

    schema = sum(
        1 for it in items if it.get("id") and _prompt_text(it) and _has_expectation(it)
    ) / n

    trigger_style = any("should_trigger" in it for it in items)
    if trigger_style:
        pos = sum(1 for it in items if it.get("should_trigger") is True)
        neg = sum(1 for it in items if it.get("should_trigger") is False)
        forbidden = 1.0 if (pos and neg) else (0.5 if (pos or neg) else 0.0)
    else:
        forbidden = sum(1 for it in items if it.get("forbidden_expectations")) / n

    prompts = [_prompt_text(it).lower() for it in items]
    unique = len({p for p in prompts if p})
    uniqueness = unique / n

    grams = [_bigrams(p) for p in prompts if p]
    if len(grams) < 2:
        diversity = 1.0
    else:
        if len(grams) <= DIVERSITY_PAIR_CAP:
            pairs = combinations(grams, 2)
        else:
            # Deterministic fixed-stride sampling of consecutive pairs — bounds
            # the work to O(n) while staying reproducible (no RNG).
            pairs = ((grams[i], grams[(i + 1) % len(grams)]) for i in range(len(grams)))
        overlaps = []
        for a, b in pairs:
            union = a | b
            overlaps.append(len(a & b) / len(union) if union else 0.0)
        diversity = 1.0 - (sum(overlaps) / len(overlaps))

    count = min(1.0, n / TARGET_N)

    components = {
        "schema": round(schema, 4),
        "forbidden": round(forbidden, 4),
        "uniqueness": round(uniqueness, 4),
        "diversity": round(diversity, 4),
        "count": round(count, 4),
    }
    score = round(sum(WEIGHTS[k] * components[k] for k in WEIGHTS), 4)
    return {"score": score, "n": n, "components": components}


def main() -> int:
    parser = argparse.ArgumentParser(description="Score an eval dataset's quality")
    parser.add_argument("path")
    args = parser.parse_args()
    print(json.dumps(score_dataset(Path(args.path)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

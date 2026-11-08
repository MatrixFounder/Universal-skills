#!/usr/bin/env python3
"""Deterministic quality scorer for an eval dataset (evals.json).

Produces a score in [0, 1] from six transparent components. No LLM, no API —
this is a pure function of the file, so it is fully unit-testable and gives a
stable signal for the dataset-improvement loop.

Components (weighted):
  schema      0.20  every case has id + prompt-text + an expectation signal
  forbidden   0.20  negative coverage: for trigger sets, the BALANCE of
                    negatives (full credit at a 0.4-0.6 negative share); for
                    functional sets, the share of cases with
                    forbidden_expectations
  near_miss   0.15  trigger sets only: share of negatives that share at least
                    one content word with some positive (the negatives that
                    actually test the trigger boundary)
  uniqueness  0.15  fraction of non-duplicate prompts
  diversity   0.10  1 - average pairwise bigram overlap (Jaccard)
  count       0.20  min(1, n / target_n), target_n = 20 by default

`near_miss` is not defined for functional-style sets; there the score is the
weighted mean of the remaining five components (weights renormalized), and
`components["near_miss"]` is None.

Why these numbers: skill-creator recommends about 20 trigger queries, roughly
half negative, including near misses. The previous scorer (target 5, any
negative = full credit) gave 4 positives + 1 unrelated negative a perfect 1.0,
so the loop stopped as `optimal` on exactly the small homogeneous set the
manual warns against.

Handles both trigger-style cases ({query, should_trigger}) and functional-style
cases ({id, prompt, expectations, forbidden_expectations}).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import combinations
from pathlib import Path

try:
    from scripts.common import (  # type: ignore
        emit_json, install_human_channel, is_negative_case, resolve_dataset_items,
    )
except ImportError:
    from common import emit_json, install_human_channel, is_negative_case, resolve_dataset_items

TARGET_N = 20
WEIGHTS = {
    "schema": 0.20, "forbidden": 0.20, "near_miss": 0.15,
    "uniqueness": 0.15, "diversity": 0.10, "count": 0.20,
}
# Negative share that earns full `forbidden` credit on a trigger set.
BALANCE_LOW, BALANCE_HIGH = 0.4, 0.6
# Above this many cases the exact O(n^2) pairwise diversity is replaced by a
# deterministic fixed-stride sample to keep scoring cheap as a dataset grows.
DIVERSITY_PAIR_CAP = 100

# Words that carry no topic: a negative sharing only these with a positive is
# not a near miss. Kept short and explicit; tokens shorter than 3 characters
# are ignored anyway.
_STOPWORDS = frozenset("""
the and for with this that these those from into onto your you are was were
can could would should will shall may might must have has had not but any all
some what which who whom how why when where there here than then them they
their its it's our ours out about over under please help make get give want
need just like also very more most such only own same both each other one two
""".split())
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_+#.-]*")


def _load_items(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items, _key = resolve_dataset_items(data)
    return [d for d in items if isinstance(d, dict)]


def _prompt_text(item: dict) -> str:
    return str(item.get("query") or item.get("prompt") or "").strip()


def _has_expectation(item: dict) -> bool:
    return bool(item.get("expectations")) or ("should_trigger" in item)


def _content_words(text: str) -> set[str]:
    words = {w.strip(".-") for w in _WORD_RE.findall(text.lower())}
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _bigrams(text: str) -> set[str]:
    tokens = text.lower().split()
    return set(zip(tokens, tokens[1:])) if len(tokens) > 1 else set(tokens)


def _balance(neg_share: float) -> float:
    """1.0 inside [BALANCE_LOW, BALANCE_HIGH], falling linearly to 0 at 0 and 1."""
    if neg_share < BALANCE_LOW:
        return neg_share / BALANCE_LOW
    if neg_share > BALANCE_HIGH:
        return (1.0 - neg_share) / (1.0 - BALANCE_HIGH)
    return 1.0


def score_dataset(path: Path, *, target_n: int = TARGET_N) -> dict:
    items = _load_items(path)
    n = len(items)
    if n == 0:
        return {"score": 0.0, "n": 0, "components": {k: 0.0 for k in WEIGHTS}}

    schema = sum(
        1 for it in items if it.get("id") and _prompt_text(it) and _has_expectation(it)
    ) / n

    trigger_style = any("should_trigger" in it for it in items)
    near_miss: float | None = None
    if trigger_style:
        positives = [it for it in items if it.get("should_trigger") is True]
        negatives = [it for it in items if it.get("should_trigger") is False]
        labelled = len(positives) + len(negatives)
        forbidden = _balance(len(negatives) / labelled) if labelled else 0.0
        if negatives and positives:
            pos_words = set().union(*(_content_words(_prompt_text(p)) for p in positives))
            near = sum(1 for it in negatives if _content_words(_prompt_text(it)) & pos_words)
            near_miss = near / len(negatives)
        else:
            near_miss = 0.0
    else:
        forbidden = sum(1 for it in items if is_negative_case(it)) / n

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

    count = min(1.0, n / max(int(target_n), 1))

    components = {
        "schema": round(schema, 4),
        "forbidden": round(forbidden, 4),
        "near_miss": None if near_miss is None else round(near_miss, 4),
        "uniqueness": round(uniqueness, 4),
        "diversity": round(diversity, 4),
        "count": round(count, 4),
    }
    applicable = {k: w for k, w in WEIGHTS.items() if components[k] is not None}
    total_w = sum(applicable.values())
    score = round(sum(w * components[k] for k, w in applicable.items()) / total_w, 4)
    return {"score": score, "n": n, "components": components}


def main() -> int:
    install_human_channel()
    parser = argparse.ArgumentParser(description="Score an eval dataset's quality")
    parser.add_argument("path")
    parser.add_argument("--target-n", type=int, default=TARGET_N,
                        help=f"case count that earns full `count` credit (default {TARGET_N})")
    args = parser.parse_args()
    emit_json(score_dataset(Path(args.path), target_n=args.target_n))
    return 0


if __name__ == "__main__":
    sys.exit(main())

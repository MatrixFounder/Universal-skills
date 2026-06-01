# Example — Improving a skill's CSO description (trigger accuracy)

**Scenario**: `evals/fixtures/test-skill-broken` is a `json-tidy` skill whose
description is just `"formats json"`. It under-triggers (and false-triggers).
Its `evals/evals.json` is a trigger set: 3 should-trigger + 3 should-not.

**Input (command):**
```
python3 scripts/auto_improve.py \
  --artifact-path evals/fixtures/test-skill-broken \
  --artifact-type skill --target description \
  --eval-set evals/fixtures/test-skill-broken/evals/evals.json \
  --workspace /tmp/desc-run --max-iterations 3 --git-isolation
```

**Mechanics:**
- Evaluator = the Claude agent-eval backend: it runs `claude -p` per query and
  detects whether the skill triggers, returning trigger accuracy as the score.
  It also stashes the raw failed/false-trigger detail in a shared holder.
- Proposer = the single-shot description optimizer. It reads the holder's
  failures and emits `{"diff_format":"frontmatter-field","field":"description","value":"..."}`.
  The OUTER loop owns the budget — `run_loop.py` is NOT nested.
- Immutability: `name`/`tier` stay fixed; only the `description` field changes.

**Output (`improvement_history.tsv`, illustrative):**
```
iter	score	delta	status	tier	change_summary	snapshot_ref
0	0.500	—	baseline		baseline	
1	0.833	+0.333	keep	trivial	intent-focused JSON-formatting description	.../iter-1/...
2	0.833	+0.000	no-signal	trivial	reworded again	.../iter-2/...
```

**Result**: trigger accuracy 0.50 → 0.83; the second within-noise reword is
reverted (`no-signal`). The winning description lives on branch
`auto-improve/test-skill-broken/run`; merge it explicitly when satisfied.

> Without a provider API key / the `claude` CLI, use the `dataset` example for a
> fully offline demonstration, or inject fakes via `run_improvement_loop` (see
> `scripts/tests/test_auto_improve.py`).

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

**Preflight** (exit 2 before anything changes): the `claude` CLI and
skill-creator's `run_eval.py` must be present (no LLM-grading substitute), the
provider key and SDK must be set, and with `--git-isolation` the tree must be a
clean git repository. The run defaults to `--max-duration 60m`, because the
`claude -p` tokens are not metered.

**Mechanics:**
- Evaluator = the Claude agent-eval backend: it runs `claude -p` per query and
  detects whether the skill triggers, returning trigger accuracy as the score.
  It also stashes the raw failed/false-trigger detail in a shared holder.
- Noise: the baseline is measured 3 times (`--calibrate-noise 3`); σ = 1.64·√2·sd.
  Each KEEP is re-measured 3 times and must still clear σ/√3. The 6-case set is
  below the 10-case holdout minimum, so all cases are train cases.
- Guard: `validate_skill.py` must keep passing; a KEEP that breaks it is reverted.
- Proposer = the single-shot description optimizer. It reads the holder's
  failures and emits `{"diff_format":"frontmatter-field","field":"description","value":"..."}`.
  The OUTER loop owns the budget — `run_loop.py` is NOT nested.
- Immutability: `name`/`tier` stay fixed; only the `description` field changes.

**Output (`improvement_history.tsv`, illustrative):**
```
iter	score	delta	status	tier	change_summary	snapshot_ref	secondary
0	0.556	—	baseline		baseline (mean of 3; sd=0.0962; sigma=0.2231 calibrated)		1.000
1	0.889	+0.333	keep	trivial	intent-focused JSON-formatting description [gate 0.833, re-measured 0.889 x3]	.../iter-1/...	1.000
2	0.833	-0.056	no-signal	trivial	reworded again	.../iter-2/...	1.000
```

Iteration 1: the gate delta 0.833 − 0.556 = 0.277 clears σ = 0.223, and the
re-measured mean (0.889) clears σ/√3 = 0.129, so the KEEP stands and 0.889
becomes the champion score.

**Result**: trigger accuracy 0.56 → 0.89; the second within-noise reword is
reverted (`no-signal`). The report then gives the final confirmation: the
winner and the baseline snapshot measured 5 times each, with a bootstrap 95 %
CI of the difference and a `confirmed` / `not confirmed` verdict. The winning
description lives on branch
`auto-improve/test-skill-broken/<UTC timestamp>`; merge it explicitly when the
verdict is `confirmed`.

> Without a provider API key / the `claude` CLI, use the `dataset` example for a
> fully offline demonstration, or inject fakes via `run_improvement_loop` (see
> `scripts/tests/test_auto_improve.py`).

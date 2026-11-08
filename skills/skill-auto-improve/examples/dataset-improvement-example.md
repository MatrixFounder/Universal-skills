# Example — Improving an eval dataset (offline path)

**Scenario**: `evals/fixtures/thin-dataset.json` has only 3 positive cases and
no negatives. `grade_dataset.py` scores it 0.480: `forbidden` 0.0 (no
negatives), `near_miss` 0.0, `count` 0.15 (3 of the 20-case target). We want a
dataset that actually tests the trigger boundary.

**Input (command):**
```
python3 scripts/auto_improve.py \
  --artifact-path evals/fixtures/thin-dataset.json \
  --artifact-type dataset \
  --workspace /tmp/ds-run \
  --max-iterations 5
```

The dataset path needs no agentic backend: the Evaluator is `grade_dataset.py`
(pure, deterministic), so σ = 0 is correct here, the baseline is measured once,
a KEEP is not re-measured, and there is no final confirmation (`--final-runs`
defaults to 0). Only the Proposer calls an LLM, proposing `dataset-op` additions.
The provider key and SDK are checked before the baseline: without them the run
exits 2.

**What the loop does each iteration:**
1. Proposer returns `{"diff_format":"dataset-op","dataset_ops":[{"op":"add","item":{...}}]}`.
2. A repeat of an already rejected summary or edit is discarded (`duplicate`).
3. `validate_proposal` confirms it adds (not modifies/removes) cases and touches no immutable id/grader.
4. Snapshot → apply → `grade_dataset.py` re-scores.
5. KEEP if the score rose; else REVERT.

**Output (`improvement_history.tsv`, scores computed with `grade_dataset.py`):**
```
iter	score	delta	status	tier	change_summary	snapshot_ref	secondary
0	0.480	—	baseline		baseline		
1	0.763	+0.283	keep	trivial	add near-miss negative (JSON to YAML)	.../iter-1/thin-dataset.json	
2	0.849	+0.086	keep	trivial	add near-miss negative (JSON schema validation)	.../iter-2/thin-dataset.json	
3	0.804	-0.045	revert	large	add 3 positives	.../iter-3/thin-dataset.json	
4	0.868	+0.019	keep	large	add a positive and a near-miss negative (minify)	.../iter-4/thin-dataset.json	
5	0.852	-0.017	revert	large	add a positive and an unrelated negative (web scraper)	.../iter-5/thin-dataset.json	
```

**Why the reverts:** iteration 3 drops the negative share to 0.25, below the
0.4–0.6 band that earns full `forbidden` credit. Iteration 5 adds a negative
that shares no content word with any positive, so `near_miss` falls from 1.0 to
0.75 and outweighs the `count` gain: an unrelated negative does not test the
trigger boundary.

**Result**: quality 0.480 → 0.868; `exit_reason=budget_iterations`. The scorer
keeps rewarding growth toward 20 balanced cases with near misses, so a thin set
no longer exits as `optimal` (4 positives + 1 unrelated negative score 0.60).
Existing cases' `id`/`grader` are untouched (immutability subset check); only
additions landed. Iterations with two or more ops are tier `large`, so
`adversarial_review.md` is written at the end.

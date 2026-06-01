# Example — Improving an eval dataset (offline path)

**Scenario**: `evals/fixtures/thin-dataset.json` has only 3 positive cases and
no negatives. `grade_dataset.py` scores it 0.835 (forbidden coverage 0.5,
count 0.6). We want a higher-quality dataset.

**Input (command):**
```
python3 scripts/auto_improve.py \
  --artifact-path evals/fixtures/thin-dataset.json \
  --artifact-type dataset \
  --workspace /tmp/ds-run \
  --max-iterations 5
```

The dataset path needs no agentic backend: the Evaluator is `grade_dataset.py`
(pure, deterministic). Only the Proposer calls an LLM, proposing `dataset-op`
additions of realistic negative and diverse positive cases.

**What the loop does each iteration:**
1. Proposer returns `{"diff_format":"dataset-op","dataset_ops":[{"op":"add","item":{...}}]}`.
2. `validate_proposal` confirms it adds (not modifies/removes) cases and touches no immutable id/grader.
3. Snapshot → apply → `grade_dataset.py` re-scores.
4. KEEP if the score rose beyond σ; else REVERT.

**Output (`improvement_history.tsv`):**
```
iter	score	delta	status	tier	change_summary	snapshot_ref
0	0.835	—	baseline		baseline	
1	0.980	+0.145	keep	trivial	add negative case (Rust server)	.../iter-1/thin-dataset.json
2	1.000	+0.020	keep	trivial	add negative case (PDF summary)	.../iter-2/thin-dataset.json
```

**Result**: quality 0.835 → 1.0; `exit_reason=optimal`. Existing cases'
`id`/`grader` are untouched (immutability subset check); only additions landed.

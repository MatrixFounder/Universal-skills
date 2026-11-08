# Example — Improving arbitrary text against a quality rubric

**Scenario**: improve a weak cold email against a weighted rubric, using the
**debiased pairwise gate** + **best-of-N** (the capability adapted from
ExternalTools/auto-improve, but vendor-agnostic).

**Input (command):**
```
python3 scripts/auto_improve.py \
  --artifact-path drafts/cold-email.txt \
  --artifact-type text \
  --criteria examples/cold-email-rubric.md \
  --candidates 3 \
  --workspace /tmp/email-run \
  --max-iterations 8 --threshold 0.9
```

**Mechanics (per iteration):**
1. **Proposer** (`text_mutator`, temp 0.9) drafts `--candidates 3` surgical
   `text-replace` edits, each targeting a different weak rubric dimension
   (informed by the previous breakdown's `top_improvement`).
2. **Best-of-N**: each candidate is applied to a copy and scored by the rubric
   judge; the highest-scoring one becomes the proposal.
3. **Decision** = debiased **pairwise gate**: the judge compares the champion
   (pre-edit) vs the candidate in BOTH orderings; KEEP only if the candidate
   wins more orderings (position-bias cancelled). The rubric score is logged for
   the trajectory and the `--threshold 0.9` early stop.
4. A KEEP also needs the length guard (length within ±50 % of the baseline,
   `--length-guard`) and is re-measured by one independent 2-pass rubric call:
   the best-of-N score is the maximum of N noisy scores, so it is not used as
   the champion score or for the `--threshold` check.
5. KEEP → commit (with `--git-isolation`) / REVERT → restore the snapshot.

The rubric (`--criteria`) is the **immutable harness** — a separate file the
loop never edits. `text` artifacts have no internal immutable parts.

**Output (`improvement_history.tsv`, illustrative):**
```
iter	score	delta	status	tier	change_summary	snapshot_ref	secondary
0	0.480	—	baseline		baseline		1.000
1	0.620	+0.140	keep	trivial	specific opener beats generic "Hi" [gate 0.650, re-measured 0.620 x1]	.../iter-1/cold-email.txt	1.000
2	0.620	+0.000	revert	trivial	reworded CTA (lost pairwise both orderings)	.../iter-2/cold-email.txt	1.000
3	0.910	+0.290	keep	small	concrete outcome + single ask [gate 0.930, re-measured 0.910 x1]	.../iter-3/cold-email.txt	1.000
```

**Result**: 0.48 → 0.91; `exit_reason=optimal`. Every KEEP is a verified
pairwise win, not a roll-of-the-dice rewrite. The report's final confirmation
re-scores the winner and the baseline 5 times each with the rubric judge and
gives the bootstrap 95 % CI of the difference. Grade with another model family
than the mutator (`--grader-provider`, `--grader-model`): a judge rates its own
model's style higher. Vendor-agnostic: set
`DEFAULT_PROVIDER=openai|gemini|anthropic`. Fully offline-tested via injected
proposer/evaluator/judge (see `scripts/tests/test_auto_improve.py::TestTextQuality`).

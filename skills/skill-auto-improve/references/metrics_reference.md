# Metrics Reference

Every artifact type has a **primary** metric (optimized; higher = better).
Deterministic metrics are computed by scripts the orchestrator calls directly
(no LLM middle-man so the number is never mis-transcribed); subjective metrics
use the LLM grader.

| Artifact / target | Primary metric | How measured | Agnostic? |
|---|---|---|---|
| skill — description | CSO trigger accuracy = passed/total | agent-eval backend (`claude -p` trigger detection) | Claude only |
| skill — instructions / full | trigger pass_rate | agent-eval backend | Claude only |
| prompt (`--prompt-eval executed`, default) | pass_rate of the RESPONSES | `executor` runs the prompt on each case; `grader` sees inputs + responses, never the prompt | ✅ full |
| prompt (`--prompt-eval static`) | predicted pass_rate | `grader` reads the prompt and predicts | ✅ full |
| workflow | predicted pass_rate (static) | `grader` reads the workflow and predicts; no backend executes workflows | ✅ full |
| dataset | quality score 0–1 | `grade_dataset.py` (deterministic) | ✅ full |
| text | rubric score 0–1 (weighted dims/100) + **pairwise** keep decision | rubric LLM judge + debiased pairwise gate | ✅ full |

The report names the mode (`Metric:` line). A static score is a prediction of
the grader, not a measurement: a prompt that recites its expectations scores
well statically even when the model does not meet them.

With a non-Claude vendor a `skill` / `full-skill` run exits 2 before the
baseline. An LLM estimate of trigger accuracy is a different quantity and is
never substituted.

## Noise band (`--calibrate-noise K`, `--noise-sigma`)

A delta is the difference of two noisy measurements, so its spread is √2 times
the spread `sd` of one measurement. The keep threshold is therefore

    σ = z · √2 · sd,   z = 1.64   (≈ 2.3 · sd; ~5 % of no-effect deltas clear it)

- The baseline is measured `K` times (default 3 for skill/prompt/workflow; 0 for
  dataset, which is deterministic, and for text, whose KEEP is the pairwise
  gate). The champion score is their mean; `sd` and σ go to the report and to the
  TSV baseline row (`baseline (mean of 3; sd=…; sigma=… calibrated)`).
- `--noise-sigma` sets σ explicitly and wins over the calibration. It is a
  threshold for a DIFFERENCE, not the noise of one run.
- σ = 0 with a non-deterministic evaluator prints a warning: every positive
  delta, noise included, can then be kept.

Measured (no-effect edits, evaluator sd 0.05, 10 iterations, default window):
without calibration 74 % of runs keep at least one null edit and `best_score` is
inflated by ≈ +0.06; with `--calibrate-noise 3` it is 7–8 % and ≈ +0.005.

## Decision rule (in `run_improvement_loop`)

**Default (absolute-delta)** — used for deterministic/typed metrics. Let
`delta = score − champion`.
- `delta > σ` **and** guard not regressed → candidate KEEP, then **re-measured**
  `K` times. It stays KEPT only if `mean − champion > σ/√K`; otherwise it is
  `no-signal` ("not confirmed") and reverted. The champion score becomes the
  re-measured mean, so one lucky measurement can neither raise the bar nor keep
  an edit.
- `|delta| ≤ σ` → **NO_SIGNAL** → **REVERT** (noise is not kept as drift)
- otherwise (`delta < −σ`, or guard regressed) → **REVERT**

**Debiased pairwise gate** (`--artifact-type text`; adapted from
ExternalTools/auto-improve) — for subjective text quality, an absolute judge
score is noisy and position-biased. Instead, after applying a candidate the
loop asks an LLM judge to compare champion (pre-apply snapshot) vs candidate in
**both orderings** and **KEEPs only when the candidate nets more wins** than the
champion (ties → keep champion), and the length guard holds. With `--candidates
N`, N edits are drafted per iteration and the best-scoring one is gated
(best-of-N). The best-of-N score is the maximum of N noisy scores (+0.85·sd at
N = 3, +1.16·sd at N = 5), so a KEEP is re-measured by one independent rubric
call; that value drives the trajectory and the early-stop threshold
(`--threshold`, text default 0.9).

Rejected before any evaluation:
- `immutability-violation` — touches an immutable part or a `--protect` section;
- `shrink-guard` — removes more than half of a section's non-blank lines, a whole
  section, or a line containing MUST/NEVER (`--allow-deletions` turns it off);
- `duplicate` — repeats the change summary or the exact edit of an attempt that
  was already reverted/rejected. The Proposer receives the full deduplicated
  list of rejected summaries (`rejected_ideas`) plus the last five attempts.

A grader that returns no usable verdict (bad JSON, wrong case count, out of
range) is retried once; then the iteration is an `error` row with the artifact
restored. It is never a score of 0.

## Guard (secondary) metric

Cheap, deterministic, no LLM. A KEEP needs `guard ≥ best_guard − σ`; the guards
are 1.0 / 0.0, so a broken guard reverts the edit. Shown in the TSV `secondary`
column.

| Artifact | Guard = 1.0 when |
|---|---|
| skill / full-skill | `skill-creator/scripts/validate_skill.py` exits 0 and `SKILL.md` has ≤ 500 lines (located as a sibling skill or via `AUTO_IMPROVE_VALIDATE_SKILL`; absent → no guard) |
| text | length within ±`--length-guard` (default 0.5) of the baseline (0 = off) |
| others | no guard |

## Holdout (`--holdout F`)

Default `0.4` for a skill/prompt/workflow eval set of ≥ 10 cases, else 0. Not
applicable to `dataset` (the dataset is the artifact) or `text` (no eval set).
The split is stratified by negative cases (`should_trigger: false` or
`forbidden_expectations`) with a fixed seed (42). Iterations see only the train
part; the Proposer never sees holdout failures. The holdout is measured only in
the final confirmation — never per iteration, or it would be tuned too.

## Final confirmation (`--final-runs N`)

After the loop, when at least one change was kept: the baseline snapshot
(`snapshots/baseline/`) and the winner are measured alternately, `N` times each
(default 5; 0 for dataset), on the holdout when there is one (then at least
once each), else in-sample — on the cases / rubric the loop tuned on (only
when N ≥ 2; a weaker check, since that set is what the loop optimized). The report gives both
means, the delta, a percentile bootstrap 95 % CI of the delta and a verdict:
`confirmed` (CI low > 0) / `not confirmed`. With a holdout it also gives the
train delta and `overfit_warning` (holdout delta ≤ 0 while train delta > σ).

## Convergence (any one)
- `score ≥ --threshold` after a KEEP → `optimal` (or `already_optimal` at baseline)
- `--min-improvement` (default 0.01) not exceeded for `--convergence-window`
  (default 3) consecutive iterations → `stagnation`
- the window (or every iteration) is `error` rows → `errors`, exit code 1
- budget exhausted → `budget_iterations` / `budget_tokens` / `budget_duration`

## `grade_dataset.py` components (weights)
`schema 0.20 · forbidden 0.20 · near_miss 0.15 · uniqueness 0.15 · diversity 0.10 · count 0.20`,
each in [0,1].
- `forbidden`: trigger sets — balance of negatives, 1.0 at a 0.4–0.6 negative
  share, falling linearly to 0 at 0 and 1; functional sets — share of cases with
  `forbidden_expectations`.
- `near_miss` (trigger sets): share of negatives that share at least one content
  word (≥ 3 letters, not a stopword) with some positive. Not defined for
  functional sets; the other weights are renormalized.
- `diversity` is `1 − avg pairwise bigram Jaccard`; `count` is
  `min(1, n / target_n)`, `target_n = 20` (`grade_dataset.py --target-n`).

4 positives + 1 unrelated negative score 0.60 (the old scorer gave 1.0); a
balanced 20-case set with near misses scores ≥ 0.9.

## Token and time budget
`--max-tokens` sums measured `usage.total_tokens` from `LLMConfigManager`
(Proposer, graders, executor, pairwise judge, failed grader attempts).
Agent-eval subprocess (`claude -p`) tokens are NOT counted: `run_eval.py`
(skill-creator) does not report them. Skill runs therefore default to
`--max-duration 60m`, and the report says the token total excludes them.

Once a change is kept, the loop stops early enough to leave room for the final
confirmation: 2·N evaluations, costed from the baseline measurements (time and
tokens per evaluation). The confirmation itself stops when the real budget is
exhausted and reports the runs it completed.

## Text-quality cost notes
A text iteration with `--candidates N` costs ≈ `1` (mutate) `+ N` (best-of-N
ranking, single-pass) `+ 2` (pairwise judge) LLM calls, plus one 2-pass rubric
re-measure per KEEP. Best-of-N ranking uses single-pass scoring (relative order
is enough; the pairwise gate is the real keep decision). Candidate scoring is
currently sequential — parallelizing it (bounded thread pool, as upstream
auto-improve does) is a known future wall-clock optimization, deferred pending
an LLM-client thread-safety check.

# Metrics Reference

Every artifact type has a **primary** metric (optimized; higher = better).
Deterministic metrics are computed by scripts the orchestrator calls directly
(no LLM middle-man so the number is never mis-transcribed); subjective metrics
use the LLM grader.

| Artifact / target | Primary metric | How measured | Agnostic? |
|---|---|---|---|
| skill — description | CSO trigger accuracy = passed/total | agent-eval backend (`claude -p` trigger detection) | per-vendor |
| skill — instructions / full | trigger pass_rate | agent-eval backend | per-vendor |
| prompt | rubric pass_rate | LLM grader (`grader` profile) | ✅ full |
| workflow | task completion / trigger | hybrid | per-vendor |
| dataset | quality score 0–1 | `grade_dataset.py` (deterministic) | ✅ full |
| text | rubric score 0–1 (weighted dims/100) + **pairwise** keep decision | rubric LLM judge + debiased pairwise gate | ✅ full |

> **Secondary no-regress gate (reserved, not yet wired).** The loop supports a
> secondary metric that must not regress for a change to be KEPT
> (`secondary ≥ best_secondary − σ`), but no production evaluator currently
> populates `secondary` (all return `None`, which disables the gate). It is a
> deliberate extension point — e.g. a future full-skill evaluator could set
> `secondary = 1 − structural_gap_count`. Until then, optimization is
> single-objective on the primary metric.

## Decision rule (in `run_improvement_loop`)

**Default (absolute-delta)** — used for deterministic/typed metrics. Let
`delta = score - best_score`, `σ = --noise-sigma`.
- `delta > σ` **and** secondary not regressed (`secondary ≥ best_secondary − σ`) → **KEEP**
- `|delta| ≤ σ` → **NO_SIGNAL** → **REVERT** (noise is not kept as drift)
- otherwise (`delta < −σ`, or secondary regressed) → **REVERT**

**Debiased pairwise gate** (`--artifact-type text`; adapted from
ExternalTools/auto-improve) — for subjective text quality, an absolute judge
score is noisy and position-biased. Instead, after applying a candidate the
loop asks an LLM judge to compare champion (pre-apply snapshot) vs candidate in
**both orderings** and **KEEPs only when the candidate nets more wins** than the
champion (ties → keep champion). The rubric score is still tracked for the chart
and the early-stop threshold (`--threshold`, text default 0.9). With
`--candidates N`, N edits are drafted per iteration and the best-scoring one is
gated (best-of-N).

## Convergence (any one)
- `score ≥ 1.0` after a KEEP → `optimal` (or `already_optimal` at baseline)
- `--min-improvement` not exceeded for `--convergence-window` (default 3) iters → `stagnation`
- budget exhausted → `budget_iterations` / `budget_tokens` / `budget_duration`

## `grade_dataset.py` components (weights)
`schema 0.30 · forbidden 0.25 · uniqueness 0.20 · diversity 0.15 · count 0.10`,
each in [0,1]. `forbidden` rewards negative coverage (should_trigger=false or
`forbidden_expectations`); `diversity` is `1 − avg pairwise bigram Jaccard`;
`count` is `min(1, n/5)`.

## Statistical honesty
LLM/agent metrics carry noise σ≈0.05–0.10. The inner loop (`runs_per_query≈3`)
optimizes **direction**, not a precise value; treat a single inner score as a
hint. A reliable measurement requires a final multi-run (≈5) + bootstrap CI
(`aggregate_benchmark.py --bootstrap`). Set `--noise-sigma` so within-noise
moves are reverted rather than accumulated.

## Token budget
`--max-tokens` sums measured `usage.total_tokens` from `LLMConfigManager`
(Proposer + LLM grader + the pairwise judge calls). Agent-eval subprocess
(`claude -p`) token usage is not yet aggregated into the budget — a known
limitation; budget primarily bounds the LLM-completion spend.

## Text-quality cost notes
A text iteration with `--candidates N` costs ≈ `1` (mutate) `+ N` (best-of-N
ranking, single-pass) `+ 2` (pairwise judge) LLM calls — the winning candidate's
ranking score is reused for the trajectory/threshold (no redundant post-apply
re-score). Best-of-N ranking uses single-pass scoring (relative order is enough;
the pairwise gate is the real keep decision). Candidate scoring is currently
sequential — parallelizing it (bounded thread pool, as upstream auto-improve
does) is a known future wall-clock optimization, deferred pending an LLM-client
thread-safety check.

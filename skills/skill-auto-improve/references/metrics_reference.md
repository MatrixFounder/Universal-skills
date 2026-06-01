# Metrics Reference

Every artifact type has a **primary** metric (optimized; higher = better) and,
for composites, a **secondary** no-regress gate. Deterministic metrics are
computed by scripts the orchestrator calls directly (no LLM middle-man so the
number is never mis-transcribed); subjective metrics use the LLM grader.

| Artifact / target | Primary metric | Secondary gate | How measured | Agnostic? |
|---|---|---|---|---|
| skill — description | CSO trigger accuracy = passed/total | — | agent-eval backend (`claude -p` trigger detection) | per-vendor |
| skill — instructions / full | trigger pass_rate | structural-gap count not worse | agent-eval backend | per-vendor |
| prompt | rubric pass_rate | — | LLM grader (`grader` profile) | ✅ full |
| workflow | task completion / trigger | trigger rate | hybrid | per-vendor |
| dataset | quality score 0–1 | — | `grade_dataset.py` (deterministic) | ✅ full |

## Decision rule (in `run_improvement_loop`)
Let `delta = score - best_score`, `σ = --noise-sigma`.
- `delta > σ` **and** secondary not regressed (`secondary ≥ best_secondary − σ`) → **KEEP**
- `|delta| ≤ σ` → **NO_SIGNAL** → **REVERT** (noise is not kept as drift)
- otherwise (`delta < −σ`, or secondary regressed) → **REVERT**

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
(Proposer + LLM grader). Agent-eval subprocess (`claude -p`) token usage is not
yet aggregated into the budget — a known limitation; budget primarily bounds
the LLM-completion spend.

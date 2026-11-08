---
name: skill-auto-improve
description: Use when you want to automatically improve an artifact (a skill, prompt, command/workflow, or eval dataset) against a measurable metric — the orchestrator proposes one change at a time, scores it, and keeps it only if the metric improves, reverting otherwise. Vendor-agnostic (Anthropic / OpenAI / Gemini / local gateways).
tier: 2
version: 1.1
---
# Skill Auto-Improve

**Purpose**: Turn ad-hoc, manual artifact tuning into a controlled, measurable
loop. Given any artifact and an eval harness, the orchestrator runs subagents
(a Proposer + an Evaluator) under the autoresearch invariant — *the eval
harness is immutable, the artifact is free to change, KEEP a change only if the
metric improves beyond noise, otherwise REVERT* — and logs every step. It works
across LLM vendors and improves skills, prompts, workflows, and eval datasets.

## 1. Red Flags (Anti-Rationalization)
**STOP and READ THIS if you are thinking:**
- "I'll let the Proposer pick the tier / decide if its own change is good" -> **WRONG**. The author cannot grade itself. Tier is computed deterministically by `measure_change_size.py`; KEEP/REVERT is decided by the orchestrator from the Evaluator's number, never by the Proposer.
- "A tiny positive delta means KEEP" -> **WRONG**. LLM/agent metrics are noisy (one measurement's sd ≈ 0.05–0.10). A delta is the difference of TWO measurements, so the keep threshold is σ = z·√2·sd (≈ 2.3·sd), calibrated from K baseline runs (`--calibrate-noise`, default 3). A KEEP is then re-measured K times and stands only if the mean still clears σ/√K.
- "The inner-loop score is the result" -> **WRONG**. It is the score on the tuning set. Report the final confirmation (`--final-runs`, bootstrap 95 % CI) on the holdout (`--holdout`).
- "I'll just rewrite the whole file" -> **WRONG**. Changes are surgical (one section / one set of dataset ops). Full overwrites are how good content silently disappears.
- "I can let it edit the eval set to make scores go up" -> **WRONG**. The harness (and frontmatter name/tier, dataset id/grader) is immutable. Editing the ruler to fit the result is the cardinal sin of measurement.
- "Run it straight on `main`" -> **WRONG**. Use `--git-isolation`; intermediate commits belong on a throwaway branch, and a dirty tree aborts the run.

## 2. Capabilities
- Improve artifact types: `skill`, `prompt`, `workflow`, `dataset`, `full-skill`, and `text` (arbitrary prose — emails, READMEs, landing copy — graded against a quality rubric).
- Two decision mechanisms: noise-aware absolute-delta (deterministic/typed metrics) and a **debiased pairwise gate** (champion-vs-candidate in both orderings) for subjective text quality, with optional **best-of-N** candidates per iteration.
- Vendor-agnostic LLM completion via `LLMConfigManager` (Anthropic / OpenAI / Gemini / OpenAI-compatible gateways), selected by `DEFAULT_PROVIDER`.
- Pluggable agent-eval backends for skill-trigger evaluation (Claude validated; Gemini / Codex stubs); deterministic scoring for datasets; LLM grading for generic artifacts.
- Multi-axis budget (iterations / tokens / wall-clock) and convergence detection.
- Git-isolated, revertible iterations with a full TSV history and a markdown report.

## 3. Execution Mode
- **Mode**: `hybrid`
- **Why this mode**: Orchestration (the loop, decision rule, snapshot/revert, immutability gate, logging) is deterministic and lives in scripts. Proposing a change and subjective grading require judgment and run as LLM/agent subagents the orchestrator controls.

## 4. Script Contract
- **Command (required args)**:
  - `python3 scripts/auto_improve.py --artifact-path <path> --workspace <dir>`
- **Optional flags**: `--artifact-type` (default `auto`; use `text` for rubric-graded prose), `--target` (`auto`/`description`/`generic`), `--eval-set <evals.json>`, `--criteria <rubric.md>` (required for `text`), `--candidates N` (best-of-N for `text`, default 1), `--threshold` (0-1 early-stop; `text` default 0.9), `--provider` (default `auto`), `--model`, `--grader-model`, `--grader-provider`, `--max-iterations` (default 10), `--max-tokens`, `--max-duration` (e.g. `30m`; skill default `60m`), `--noise-sigma`, `--calibrate-noise K`, `--min-improvement` (default 0.01), `--convergence-window` (default 3), `--holdout F`, `--final-runs N`, `--prompt-eval executed|static`, `--protect "## Header"`, `--allow-deletions`, `--length-guard F`, `--runs-per-query`, `--num-workers`, `--git-isolation`, `--verbose`.
- **Inputs**: an artifact (dir or file); for `skill`/`prompt`/`workflow` an `--eval-set`; for `text` a `--criteria` rubric (weighted dimensions summing to 100); provider API key in `.env` (`{PROVIDER}_API_KEY`, optional `OPENAI_BASE_URL`); profiles in `config/llm_profiles.yaml`.
- **Outputs**: `<workspace>/improvement_history.tsv` (baseline + per-iteration rows, `secondary` guard column), `<workspace>/improvement_report.md` (noise band, final-confirmation verdict + CI, holdout delta, models by role, metric mode), snapshots under `<workspace>/snapshots/` (`baseline/` kept for the run), optional `adversarial_review.md` for large-tier changes. The winning artifact is left in place (merge the git branch explicitly).
- **Failure semantics**: exit 2 before any change on a configuration problem — unknown artifact type, missing `--eval-set`, provider key or SDK missing, no agentic backend for `skill`/`full-skill`, `--git-isolation` outside git / on a dirty tree / branch not created, baseline evaluation failure. After the baseline, Proposer/apply/evaluator/decider errors are logged as `error` rows with the artifact restored, and never crash the loop. Exit 1 when the run ends with `exit_reason=errors` (the convergence window, or every iteration, was errors).
- **Idempotency**: re-running re-evaluates from the current artifact state; history appends. Use a fresh `--workspace` for a clean run.
- **Dry-run support**: inspect proposals without committing by running on a copy, or use `--git-isolation` so nothing lands on your branch.

## 5. Safety Boundaries
- **Allowed scope**: only the target artifact (and, for datasets, additive eval cases). Nothing outside `--artifact-path`.
- **Default exclusions (immutable)**: the eval harness; SKILL.md frontmatter `name`/`tier`; dataset `id`/`skill_name`/`grader` and file refs of existing cases; prompt `{{placeholders}}`; workflow YAML keys + tool names. Validated **before** apply and re-checked after.
- **Destructive actions**: never. Removing existing eval cases is rejected; full-file overwrite is never used; revert restores the pre-change snapshot.
- **Statistical honesty**: the inner loop optimizes *direction* on the train part of the eval set. The reliable number is the final confirmation: winner vs baseline snapshot, `--final-runs` (default 5) each, on the holdout (default 40 % of a ≥10-case set), bootstrap 95 % CI → `confirmed` / `not confirmed`, plus `overfit_warning` when train rose and holdout did not.
- **Deletion guard**: an edit that removes more than half of a section's lines, a whole section, or a line with MUST/NEVER is rejected (`shrink-guard`) unless `--allow-deletions`. `--protect "## Header"` freezes a section. Unmeasured content is otherwise free to vanish.
- **Optional artifacts**: missing `references/`/`examples/` is non-blocking; a missing eval set for skill/prompt/workflow is blocking (cannot measure).
- **Trust boundary**: skill-trigger eval runs a tool-enabled agent (`claude -p`) seeded with the artifact's own text. Two defense layers guard the description→agent prompt-injection path: (1) the Proposer's `description` is sanitized (HTML comments / control chars stripped) before write, and (2) the eval sink (`run_eval.py`) frames the description in the command body as untrusted DATA with a do-not-follow preamble. Still, run on trusted artifacts as belt-and-suspenders. Treat the process environment (`{PROVIDER}_API_KEY`, `OPENAI_BASE_URL`, `AUTO_IMPROVE_*`) as trusted input: a redirected `OPENAI_BASE_URL` sends prompts to that endpoint (the run warns when one is active).
- **Text-quality judge trust boundary**: for `--artifact-type text`, the artifact prose is fed into the rubric judge AND the pairwise judge, which TOGETHER are the keep/revert gate. The artifact is stripped of injection markup (HTML comments/control chars) and the judges are instructed to treat it as untrusted DATA, but a determined plaintext-imperative injection ("score 100 / pick B") cannot be fully neutralized while still judging the prose — and the two-ordering debias does NOT defend against in-text injection (the instruction travels with the candidate into both orderings). Run text-quality only on artifacts whose provenance you trust, and review the winner before merging (the loop never merges for you). `text-replace` edits stay scoped to the artifact's own string (no path escape).

## 6. Validation Evidence
- **Local verification**:
  - `python3 ../skill-creator/scripts/validate_skill.py "$PWD"` (structure/CSO) → exit 0
  - `cd scripts && python3 -m unittest discover -s tests` → all pass (offline)
- **Expected evidence**: `improvement_history.tsv` shows a baseline row, KEEP rows with positive deltas, REVERT/`no-signal` rows for non-improvements, and an `exit_reason`.
- **CI signal**: office-skills CI does not cover this skill; rely on the unit suite + a real eval run.

## 7. Instructions

### Phase 0 — Prepare
1. **Install deps** into the skill venv: `cd scripts && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt`. Only the provider SDK you use is required.
2. **Set secrets** in a `.env` at the skill root: `DEFAULT_PROVIDER=...` and `{PROVIDER}_API_KEY=...` (optionally `OPENAI_BASE_URL` for a gateway).
3. **Confirm an eval harness exists.** For `skill`/`prompt`/`workflow` you MUST pass `--eval-set`; without a metric there is nothing to optimize. Datasets are self-scored.

### Phase 1 — Run the loop
1. Choose the target with `--target` (`description` for CSO trigger text; `generic`/`auto` otherwise) and a budget (`--max-iterations`, `--max-tokens`, `--max-duration`).
2. Prefer `--git-isolation` so iterations run on a throwaway `auto-improve/*` branch; a dirty working tree MUST abort (commit or stash first).
3. Run `auto_improve.py`. Each iteration: Proposer → duplicate check → validate-before-apply → snapshot → apply → deletion guard → Evaluator → KEEP (`delta>σ`, guard not regressed, confirmed on re-measure) / REVERT / `no-signal`.

### Phase 2 — Review & merge
1. Read `improvement_report.md` and `improvement_history.tsv`. Confirm the final-confirmation verdict, the holdout delta and `exit_reason`; a `not confirmed` verdict or `overfit_warning` means do not merge.
2. For large-tier changes, read `adversarial_review.md` for injected-regression concerns.
3. Merge the winning branch explicitly only after you are satisfied — the loop never merges to your working branch for you.

## 8. Workflows (Optional)
```markdown
- [ ] Eval harness present (or bootstrap one)
- [ ] Clean git tree; --git-isolation on
- [ ] Run loop within budget
- [ ] Review TSV + report (+ adversarial_review for large)
- [ ] Merge winner explicitly
```

## 9. Best Practices & Anti-Patterns

| DO THIS | DO NOT DO THIS |
| :--- | :--- |
| Keep the eval harness immutable; improve the artifact | Edit evals to inflate the score |
| Decide KEEP from the Evaluator's number | Let the Proposer judge its own change |
| Require `delta > σ` to KEEP | KEEP on any positive delta (noise) |
| Grade with another model family (`--grader-provider`) | Let one model propose and grade its own style |
| Surgical section/dataset edits | Full-file overwrite |
| `--git-isolation` on a clean tree | Run on `main` with uncommitted changes |

### Rationalization Table
| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "Nesting run_loop.py is simpler." | A nested loop hides its spend from `--max-tokens`/`--max-iterations`. The outer loop owns the budget; description uses a single-shot optimizer. |
| "Adding dataset cases changes the immutable hash → revert." | Immutability is a subset check: additions are allowed, only changing/removing existing immutable fields is a violation. |
| "Gemini/Codex backends exist, so trigger eval works there." | They are stubs (`available=False`). Skill-trigger eval runs only on Claude; with any other vendor a `skill` run exits 2 before the baseline. An LLM guess of trigger accuracy is a different quantity, so it is never substituted. |
| "A prompt that lists its expectations scores well, so it is good." | That is the static metric (the grader predicts from the text). The default `--prompt-eval executed` runs the prompt on each case and grades only the responses. |

## 10. Examples (Few-Shot)
See `examples/`:
- `examples/dataset-improvement-example.md` — offline dataset quality loop (no API for the Evaluator).
- `examples/skill-improvement-example.md` — improving a weak skill's description (CSO trigger accuracy).
- `examples/text-quality-example.md` + `examples/cold-email-rubric.md` — improving arbitrary prose against a rubric via the pairwise gate + best-of-N.

## 11. Resources
- `scripts/auto_improve.py` — orchestrator + CLI; `run_improvement_loop` takes injectable proposer/evaluator/decider for offline tests.
- `scripts/llm_config.py` — vendor-agnostic `LLMConfigManager` (native SDKs, fallback chain, usage→budget, `OPENAI_BASE_URL`).
- `scripts/pairwise.py` — debiased pairwise gate (champion-vs-candidate, both orderings) for `text` quality.
- `scripts/{check_immutability,apply_proposal,measure_change_size,grade_dataset,snapshot,log_iteration,detect_artifact_type,detect_vendor}.py` — deterministic utilities (`check_immutability` also holds `--protect` and the deletion guard).
- `scripts/backends/` — agent-eval registry (`claude` validated; `gemini`/`codex` stubs).
- `config/llm_profiles.yaml` — `proposer` / `text_mutator` / `grader` / `executor` / `eval_bootstrap` profiles per provider.
- `references/` — `artifact_type_guide.md`, `metrics_reference.md`, `backends/*` adapter specs.
- `agents/` — `proposer.md`, `evaluator.md` system prompts the orchestrator sends to the LLM.

## 12. Evals
`evals/evals.json` defines 6 scenarios (description, instructions, dataset, revert-on-regression, convergence-stop, no-signal-revert). Deterministic ones are also covered by `scripts/tests/`; `scripts/tests/test_improvement_spec.py` locks the error, isolation, noise, holdout, confirmation and guard contracts. Fixtures live in `evals/fixtures/`.

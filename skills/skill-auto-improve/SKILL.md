---
name: skill-auto-improve
description: Use when you want to automatically improve an artifact (a skill, prompt, command/workflow, or eval dataset) against a measurable metric — the orchestrator proposes one change at a time, scores it, and keeps it only if the metric improves, reverting otherwise. Vendor-agnostic (Anthropic / OpenAI / Gemini / local gateways).
tier: 2
version: 1.0
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
- "A tiny positive delta means KEEP" -> **WRONG**. LLM/agent metrics are noisy (σ≈0.05–0.10). A change is only KEPT when `delta > sigma`; within-noise moves are reverted so noise never accumulates as drift.
- "I'll just rewrite the whole file" -> **WRONG**. Changes are surgical (one section / one set of dataset ops). Full overwrites are how good content silently disappears.
- "I can let it edit the eval set to make scores go up" -> **WRONG**. The harness (and frontmatter name/tier, dataset id/grader) is immutable. Editing the ruler to fit the result is the cardinal sin of measurement.
- "Run it straight on `main`" -> **WRONG**. Use `--git-isolation`; intermediate commits belong on a throwaway branch, and a dirty tree aborts the run.

## 2. Capabilities
- Improve four artifact types: `skill`, `prompt`, `workflow`, `dataset` (+ `full-skill`).
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
- **Optional flags**: `--artifact-type` (default `auto`), `--target` (`auto`/`description`/`generic`), `--eval-set <evals.json>`, `--provider` (default `auto`), `--model`, `--max-iterations` (default 10), `--max-tokens`, `--max-duration` (e.g. `30m`), `--noise-sigma`, `--runs-per-query`, `--git-isolation`, `--verbose`.
- **Inputs**: an artifact (dir or file); for `skill`/`prompt`/`workflow` an `--eval-set`; provider API key in `.env` (`{PROVIDER}_API_KEY`, optional `OPENAI_BASE_URL`); profiles in `config/llm_profiles.yaml`.
- **Outputs**: `<workspace>/improvement_history.tsv` (baseline + per-iteration rows), `<workspace>/improvement_report.md`, snapshots under `<workspace>/snapshots/`, optional `adversarial_review.md` for large-tier changes. The winning artifact is left in place (merge the git branch explicitly).
- **Failure semantics**: non-zero exit on a dirty tree under `--git-isolation` (code 2) or an unknown artifact type; Proposer/apply/eval errors are logged as iteration rows and never crash the loop.
- **Idempotency**: re-running re-evaluates from the current artifact state; history appends. Use a fresh `--workspace` for a clean run.
- **Dry-run support**: inspect proposals without committing by running on a copy, or use `--git-isolation` so nothing lands on your branch.

## 5. Safety Boundaries
- **Allowed scope**: only the target artifact (and, for datasets, additive eval cases). Nothing outside `--artifact-path`.
- **Default exclusions (immutable)**: the eval harness; SKILL.md frontmatter `name`/`tier`; dataset `id`/`skill_name`/`grader` and file refs of existing cases; prompt `{{placeholders}}`; workflow YAML keys + tool names. Validated **before** apply and re-checked after.
- **Destructive actions**: never. Removing existing eval cases is rejected; full-file overwrite is never used; revert restores the pre-change snapshot.
- **Statistical honesty**: the inner loop (`runs_per_query≈3`) optimizes *direction*; only a final 5-run + bootstrap pass is a reliable measurement. This limitation is real — do not over-trust a single inner-loop score.
- **Optional artifacts**: missing `references/`/`examples/` is non-blocking; a missing eval set for skill/prompt/workflow is blocking (cannot measure).

## 6. Validation Evidence
- **Local verification**:
  - `python3 ../skill-creator/scripts/validate_skill.py .` (structure/CSO) → exit 0
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
3. Run `auto_improve.py`. Each iteration: Proposer → validate-before-apply → snapshot → apply → Evaluator → KEEP (`delta>σ` and secondary not regressed) / REVERT / `no-signal`.

### Phase 2 — Review & merge
1. Read `improvement_report.md` and `improvement_history.tsv`. Confirm the score trajectory and `exit_reason`.
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
| Surgical section/dataset edits | Full-file overwrite |
| `--git-isolation` on a clean tree | Run on `main` with uncommitted changes |

### Rationalization Table
| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "Nesting run_loop.py is simpler." | A nested loop hides its spend from `--max-tokens`/`--max-iterations`. The outer loop owns the budget; description uses a single-shot optimizer. |
| "Adding dataset cases changes the immutable hash → revert." | Immutability is a subset check: additions are allowed, only changing/removing existing immutable fields is a violation. |
| "Gemini/Codex backends exist, so trigger eval works there." | They are stubs (`available=False`). Skill-trigger eval is validated only on Claude; other vendors fall back to LLM grading. |

## 10. Examples (Few-Shot)
See `examples/`:
- `examples/dataset-improvement-example.md` — offline dataset quality loop (no API for the Evaluator).
- `examples/skill-improvement-example.md` — improving a weak skill's description (CSO trigger accuracy).

## 11. Resources
- `scripts/auto_improve.py` — orchestrator + CLI; `run_improvement_loop` takes injectable proposer/evaluator for offline tests.
- `scripts/llm_config.py` — vendor-agnostic `LLMConfigManager` (native SDKs, fallback chain, usage→budget, `OPENAI_BASE_URL`).
- `scripts/{check_immutability,apply_proposal,measure_change_size,grade_dataset,snapshot,log_iteration,detect_artifact_type,detect_vendor}.py` — deterministic utilities.
- `scripts/backends/` — agent-eval registry (`claude` validated; `gemini`/`codex` stubs).
- `config/llm_profiles.yaml` — `proposer` / `grader` / `eval_bootstrap` profiles per provider.
- `references/` — `artifact_type_guide.md`, `metrics_reference.md`, `backends/*` adapter specs.
- `agents/` — `proposer.md`, `evaluator.md` system prompts the orchestrator sends to the LLM.

## 12. Evals
`evals/evals.json` defines 6 scenarios (description, instructions, dataset, revert-on-regression, convergence-stop, no-signal-revert). Deterministic ones are also covered by `scripts/tests/`. Fixtures live in `evals/fixtures/`.

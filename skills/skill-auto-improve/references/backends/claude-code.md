# Backend adapter — Claude Code (validated)

**Status**: validated. `available=True` when `run_eval.py` is locatable.

## What it does
Implements skill-trigger evaluation (capability B) by wrapping skill-creator's
`run_eval.py`, which runs `claude -p --output-format stream-json` per query with
the skill exposed as a temporary command, and detects whether the skill fired
by parsing `tool_use` stream events for `Skill`/`Read`.

## Resolution order for `run_eval.py`
1. `AUTO_IMPROVE_RUN_EVAL` env var (explicit path)
2. sibling skill-creator: `<skill-auto-improve>/../skill-creator/scripts/run_eval.py`

If neither resolves, `available=False` → the orchestrator falls back to LLM-only
grading (generic artifacts) and cannot run skill-trigger eval.

## Interface
```
trigger_eval(skill_path, eval_set, *, runs_per_query=3, timeout=30, model=None)
  -> {"passed": int, "total": int, "pass_rate": float, "raw": <run_eval output>}
```
`eval_set` is a JSON list of `{"query": str, "should_trigger": bool}`. `raw`
carries per-query results so the description-Proposer can read failed/false
triggers.

## Detection of vendor
`detect_vendor.py` returns `claude` when the `claude` CLI is on PATH (or via the
`CLAUDE.md` marker / `AUTO_IMPROVE_VENDOR` override).

## Notes
- Nested `claude -p` strips `CLAUDECODE` from the child env so it can run inside
  a Claude Code session (handled by `run_eval.py`).
- This is the only fully validated agent-eval path; treat Gemini/Codex as stubs.

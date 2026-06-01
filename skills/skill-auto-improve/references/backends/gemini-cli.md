# Backend adapter — Gemini CLI (STUB, unvalidated)

**Status**: stub. `GeminiBackend.available = False`. Until implemented and
validated on a real Gemini CLI runtime, the orchestrator degrades to LLM-only
grading rather than emitting unverified skill-trigger numbers.

## To implement
1. For each `{query, should_trigger}`, invoke Gemini CLI in headless/print mode
   with the skill exposed (the Gemini equivalent of a `.claude/commands/` entry
   — see `GEMINI.md` conventions in the host repo).
2. Parse Gemini's transcript/output for a skill- or file-load event that proves
   the skill triggered (the analogue of Claude's `Skill`/`Read` `tool_use`).
3. Aggregate to `{passed, total, pass_rate, raw}` exactly like `ClaudeBackend`.
4. Validate on a real runtime against known should/should-not cases, then set
   `available=True`.

## Detection
`detect_vendor.py` returns `gemini` when the `gemini` CLI is on PATH or a
`GEMINI.md` marker is found (and no higher-priority vendor CLI exists).

## Caveat
"Did the skill trigger?" only has meaning in a harness with a skill-loading
mechanism. If Gemini CLI lacks an equivalent, prefer the vendor-agnostic
LLM-grading path for generic artifacts instead of forcing a trigger metric.

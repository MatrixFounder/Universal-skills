# Backend adapter — Codex CLI (STUB, unvalidated)

**Status**: stub. `CodexBackend.available = False`. Degrades to LLM-only grading
until implemented and validated.

## To implement
1. Run `codex exec` (headless) per `{query, should_trigger}` with the skill
   exposed in whatever mechanism the Codex CLI supports.
2. Parse the run transcript for evidence the skill/instruction set was loaded
   and used (the Codex analogue of Claude's `Skill`/`Read` tool call).
3. Aggregate to `{passed, total, pass_rate, raw}` like `ClaudeBackend`.
4. Validate on a real runtime, then set `available=True`.

## Detection
`detect_vendor.py` returns `codex` when the `codex` CLI is on PATH (lower
priority than claude/gemini in the fingerprint order).

## Caveat
Codex's tooling model differs from Claude Code's skill system; skill-trigger
detection may not map cleanly. When in doubt, use the vendor-agnostic
LLM-grading path for generic artifacts rather than a forced trigger metric.

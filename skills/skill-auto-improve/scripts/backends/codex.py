"""Codex CLI agent-eval backend — STUB (not yet validated on a real runtime).

Mirrors ClaudeBackend's shape. Trigger detection for Codex CLI's output format
is unimplemented; `available` is False so the orchestrator degrades to LLM-only
grading rather than emitting unverified skill-trigger numbers.

To implement: run `codex exec` (headless) per query with the skill exposed,
parse the transcript for a skill/file load event, validate on a real runtime,
then set available=True. See references/backends/codex-cli.md.
"""

from __future__ import annotations

from pathlib import Path


class CodexBackend:
    name = "codex"
    available = False

    def trigger_eval(self, skill_path: Path, eval_set: list[dict], **kwargs) -> dict:
        raise NotImplementedError(
            "Codex agent-eval backend is a stub. Implement headless invocation + "
            "transcript trigger-detection, validate on a real runtime, then set "
            "available=True. See references/backends/codex-cli.md."
        )

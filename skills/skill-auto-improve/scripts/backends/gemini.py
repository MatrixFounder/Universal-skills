"""Gemini CLI agent-eval backend — STUB (not yet validated on a real runtime).

The structure mirrors ClaudeBackend so wiring is identical, but trigger
detection for Gemini CLI's output format is unimplemented. Until validated on a
real Gemini CLI runtime, treat this as a proposed code path: `available` is
False, so a `skill` / `full-skill` run under this vendor stops before the
baseline with exit code 2 rather than producing unverified skill-trigger
numbers. There is no LLM-grading fallback.

To implement: run `gemini` in headless/print mode on each query with the skill
exposed, then parse its transcript for a skill/file load event. See
references/backends/gemini-cli.md.
"""

from __future__ import annotations

from pathlib import Path


class GeminiBackend:
    name = "gemini"
    available = False  # flip to True once trigger detection is implemented + tested

    def unavailable_reason(self) -> str:
        return "the gemini backend is a stub: trigger detection is not implemented"

    def trigger_eval(self, skill_path: Path, eval_set: list[dict], **kwargs) -> dict:
        raise NotImplementedError(
            "Gemini agent-eval backend is a stub. Implement headless invocation + "
            "transcript trigger-detection, validate on a real runtime, then set "
            "available=True. See references/backends/gemini-cli.md."
        )

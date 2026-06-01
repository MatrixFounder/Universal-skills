"""Agent-eval backend registry (capability B).

A backend runs the *agentic* part of evaluation — spawning a subagent that
exercises the artifact with tool use — for a specific host vendor. Generic,
non-agentic grading (prompts/datasets) does NOT go through a backend; it uses
the vendor-agnostic LLM grader directly.

Backends implement:
    available: bool
    trigger_eval(skill_path, eval_set, *, runs_per_query, timeout, model) -> dict
        returns {"passed": int, "total": int, "pass_rate": float, "raw": ...}

`get_backend(vendor)` returns the adapter for the detected vendor, or the
FallbackBackend (no agentic capability) when none is available.
"""

from __future__ import annotations

try:
    from scripts.detect_vendor import (  # type: ignore
        VENDOR_CLAUDE, VENDOR_CODEX, VENDOR_GEMINI, VENDOR_FALLBACK,
    )
except ImportError:
    from detect_vendor import (
        VENDOR_CLAUDE, VENDOR_CODEX, VENDOR_GEMINI, VENDOR_FALLBACK,
    )


class FallbackBackend:
    """No agentic CLI available. skill-trigger eval cannot run."""

    name = VENDOR_FALLBACK
    available = False

    def trigger_eval(self, *args, **kwargs) -> dict:
        raise NotImplementedError(
            "No agentic backend available — skill-trigger eval requires a vendor "
            "CLI (claude/gemini/codex). Generic LLM grading still works."
        )


def get_backend(vendor: str):
    if vendor == VENDOR_CLAUDE:
        try:
            from scripts.backends.claude import ClaudeBackend  # type: ignore
        except ImportError:
            from backends.claude import ClaudeBackend
        return ClaudeBackend()
    if vendor == VENDOR_GEMINI:
        try:
            from scripts.backends.gemini import GeminiBackend  # type: ignore
        except ImportError:
            from backends.gemini import GeminiBackend
        return GeminiBackend()
    if vendor == VENDOR_CODEX:
        try:
            from scripts.backends.codex import CodexBackend  # type: ignore
        except ImportError:
            from backends.codex import CodexBackend
        return CodexBackend()
    return FallbackBackend()

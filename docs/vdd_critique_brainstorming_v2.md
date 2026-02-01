# VDD Adversarial Review: Brainstorming Spec v2.0

**Target**: `docs/spec_brainstorming_universal.md` (v2.0)
**Reviewer**: Antigravity (Adversarial Persona)
**Date**: 2026-02-01

## Executive Summary
Spec v2.0 is a significant improvement over v1 regarding adaptability and safety. The "3-Tier Assessment" logic directly solves the "Process Overkill" issue found in prior reviews. However, the "Tool Agnosticism" section introduces a new class of risk: **Ambiguity Paralysis**, where an agent may hallucinate capability boundaries.

## 1. Safety & Robustness Scores

| Metric | Score | Analysis |
| :--- | :--- | :--- |
| **Safety** | **High** | The "Final Gate" Checklist prevents unapproved code. "Red Flags" cover common pitfalls. |
| **Adaptability** | **High** | The Trivial/Medium/Complex tiered logic is the "Killer Feature" that prevents user frustration. |
| **Clarity** | **Medium** | "Environment's search capability" is vague. Agents might hallucinate tool names. |
| **Universality** | **High** | No vendor lock-in specific tool names. |

## 2. Identified Risks & Fragilities

### ⚠️ Risk 1: "Abstract Capability" Hallucination
*   **Spec**: "Use your environment's search capability...".
*   **Attack Vector**: An agent in a restrictive environment (no shell) might hallucinate a `search_code` tool call or apologize endlessly for not having it.
*   **Fix**: Add an explicit instruction for the "No Tool" case: *"If no search tool is available, explicitly ask the user for the relevant files."* (The current spec hints at this but needs to be a hard rule).

### ⚠️ Risk 2: The "Mermaid" Fallback Gap
*   **Spec**: "Fallback: ASCII Art if the environment is known to break Mermaid".
*   **Attack Vector**: The agent *doesn't know* if the environment breaks Mermaid. It just knows "I am an agent". It will default to Mermaid, which renders as raw text in standard terminals.
*   **Fix**: Change the default: *"Default to Mermaid for complex flows, but ALWAYS offer a brief text summary/list regardless."* Or: *"Use Mermaid only if you are confident the UI supports it; otherwise usage ASCII."*

### ⚠️ Risk 3: "Demo" Overload
*   **Spec**: "Refactor `examples/` to include 3 distinct files".
*   **Attack Vector**: Large examples consume context window. Reading 3 separate files might distract the model or cause context eviction.
*   **Fix**: Consolidate into **one** file (`examples/brainstorming_levels.md`) with clean separation headers. This saves tokens and keeps context focused.

## 3. Recommended Polish (Pre-Implementation)

1.  **Refine Tool Instructions**:
    *   Change: "Use your environment's capability..."
    *   To: "If you have search tools (`grep`, `mcp`), use them. **IF NOT**, skip research and ask the user for file paths." (Explicit branching).

2.  **Consolidate Examples**:
    *   Instead of 3 files, use one file `examples/brainstorming_lifecycle.md` with:
        *   `## Level 1: Trivial`
        *   `## Level 2: Medium`
        *   `## Level 3: Complex`

3.  **Explicit "Design Doc" Naming**:
    *   Ensure the spec defines a conflict-free naming convention (e.g., `docs/design/YYYY-MM-feature.md`) to avoid overwriting old designs if a generic name is reused.

---
**Verdict**: **GREEN LIGHT** to proceed, subject to the minor clarifications above. The "Adaptive Complexity" model is robust enough to handle the "Idea vs Design" conflict.

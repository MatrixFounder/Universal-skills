# Slash Command: /heal

**Trigger**: `/auto-heal-external-skill <skill_path>`

**Description**: Automatically audits and fixes a skill using the `skill-validator` validation loop.

## Instructions for Claude

When the user types `/auto-heal-external-skill <skill_path>`, perform the following steps:

1.  **Context Loading**:
    *   Read the target skill's `SKILL.md`: `<skill_path>/SKILL.md`.

2.  **Workflow Execution**:
    
    **Phase 1: Initial Audit**
    *   **Audit Security**: Use the `skill-validator` skill to scan the target path.
    *   **Audit Structure**: Use the `skill-enhancer` skill to analyze gaps.
    
    **Phase 2: Refinement Loop (Max 3 Iterations)**
    *   Analyze the reports from Phase 1.
    *   **IF** Critical Issues OR Gaps exist:
        *   Switch to `skill-enhancer` persona.
        *   **Apply Fixes**: Fix the specific lines causing errors (Security first, then Compliance).
        *   **Re-run Phase 1** (Validator + Enhancer) to verify.
    *   **ELSE** (No issues):
        *   Stop. The skill is Gold Standard.

3.  **Completion**:
    *   Report the final status.

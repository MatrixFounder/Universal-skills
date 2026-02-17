---
description: Automatically audit and fix a skill using Validator and Enhancer.
---

# Auto-Healing Skill Workflow

To run this workflow, replace `<skill_path>` with the target skill directory.

## Phase 1: Initial Audit

1. **Security Check**:
   - Agent instruction: "Use the **skill-validator** skill to audit `<skill_path>`."
   - Requirement: Request JSON output for machine parsing.

2. **Structure Check**:
   - Agent instruction: "Use the **skill-enhancer** skill to analyze gaps in `<skill_path>`."
   - Requirement: Request JSON output.

## Phase 2: Refinement Loop (Max 3 Iterations)

3. **Analysis**:
   - Review the JSON reports from Phase 1.
   - If `critical_issues == 0` AND `gaps == 0`: **STOP**. The skill is Gold Standard.

4. **Enhancement**:
   - **Context**: You are now the **skill-enhancer**.
   - **Input**: Take the *Security Report* and *Gap Analysis* from Phase 1.
   - **Action**: Apply fixes to `<skill_path>`.
     - **Priority 1**: Fix Critical Security Issues (refer to `security_refactoring.md` in skill-enhancer).
     - **Priority 2**: Fix Structural Gaps (add Red Flags, Rationalization, etc).
   - **Constraint**: Use `replace_file_content` for surgical edits.

5. **Re-Verify**:
   - Re-run Phase 1 (Validator + Enhancer) to verify fixes.

6. **Loop**: Repeat Steps 3-5 up to 3 times.

## Phase 3: Final Report

7. Generate a summary in `auto_fix_report.md`:
   - Summary of fixes applied.
   - Remaining warnings (if any).
   - Use `render_diffs` to show changes.

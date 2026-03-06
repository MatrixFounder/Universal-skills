---
name: auto-heal-external-skill
description: "Use when a skill has validation errors, security issues, or structural gaps and needs automated fixing. Triggers on /auto-heal-external-skill."
version: 1.0
---

# Slash Command: /auto-heal-external-skill

**Trigger**: `/auto-heal-external-skill <skill_path>`

**Description**: Automatically audits and fixes a skill using `skill-validator` and `skill-enhancer` in a validation loop.

## Safety Boundaries

- MUST NOT modify files outside `<skill_path>` — all changes are scoped to the target skill directory.
- MUST NOT delete any files — only edit existing files or create new ones within `<skill_path>`.
- MUST NOT bypass validation errors — every fix requires re-validation to confirm resolution.

## Instructions for Claude

When the user types `/auto-heal-external-skill <skill_path>`, execute the following steps:

### 1. Pre-flight Checks

1. Verify `<skill_path>/SKILL.md` exists. If it does not exist — stop and report: "SKILL.md not found at `<skill_path>`. Cannot heal a skill without SKILL.md."
2. Read `<skill_path>/SKILL.md` to understand the skill's purpose and structure.

### 2. Phase 1: Initial Audit

1. **Security audit**: Run the `skill-validator` skill against `<skill_path>`. Capture the list of issues with their severity (critical / warning / info).
2. **Structure audit**: Run the `skill-enhancer` skill in analysis mode against `<skill_path>`. Capture the list of structural gaps.

### 3. Phase 2: Refinement Loop (Max 3 Iterations)

For each iteration:

1. Review the combined output from Phase 1:
   - Count critical security issues from `skill-validator`.
   - Count structural gaps from `skill-enhancer`.
2. **IF** critical issues > 0 OR structural gaps > 0:
   - Apply fixes using the `skill-enhancer` skill. Fix security issues first, then structural gaps — security violations take priority because they can cause runtime harm.
   - Re-run both `skill-validator` and `skill-enhancer` to verify fixes resolved the issues.
3. **ELSE** (0 critical issues AND 0 gaps):
   - Exit loop. The skill passes validation.

If after 3 iterations issues remain — stop and report the unresolved issues to the user. Do not loop indefinitely.

### 4. Completion

Report the final status:
- **Pass**: "Skill at `<skill_path>` passes all validation checks. 0 critical issues, 0 structural gaps."
- **Partial**: "Skill at `<skill_path>` improved but N issues remain after 3 iterations:" followed by the list of unresolved issues.

## Exit Criteria

The command succeeds when `skill-validator` returns 0 critical issues AND `skill-enhancer` returns 0 structural gaps.

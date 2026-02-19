# Skill Writing Manual

**Tools for Agentic Development**

This manual describes how to use **Skill Creator** and **Skill Enhancer** to build authoritative, high-quality agent skills. The tooling is project-agnostic and configurable.

---

## 1. Overview

The meta-skill toolchain has two primary components:

1. **Skill Creator**: bootstraps new skills with a standardized structure and validates base compliance.
   - Scripts: `init_skill.py`, `validate_skill.py`, `skill_utils.py`
2. **Skill Enhancer**: analyzes existing skills for quality/compliance gaps and suggests refactoring direction.
   - Script: `analyze_gaps.py`

Standard rich-skill structure:

```text
skill-name/
├── SKILL.md
├── scripts/
├── examples/
├── assets/
└── references/
```

Note: `resources/` is deprecated. Use `assets/` (output materials) and `references/` (knowledge materials).

---

## 2. Configuration Model

The tools are driven by merged configuration.

Resolution order:

1. Bundled defaults: `skills/skill-creator/scripts/skill_standards_default.yaml`
2. Project overlay: `.agent/rules/skill_standards.yaml`
3. Runtime fallbacks inside scripts (only when keys are missing)

### Why this matters

- New parameters may appear in defaults, overlay, or script-level fallback logic.
- If you only inspect one file, you may miss active behavior.

---

## 3. Default Parameters (Single Reference)

Use this file as the canonical quick reference for defaults and fallback behavior:

- `skills/skill-creator/references/default_parameters.md`

It documents:

- full default key set,
- runtime fallback values,
- project-level extensions,
- inspection command for effective merged config.

### Mandatory maintenance rule

When introducing any new config parameter in `init_skill.py`, `validate_skill.py`, or standards YAML, update:

- `skills/skill-creator/references/default_parameters.md`

in the same change.

---

## 4. Inspect Effective Configuration

To see active merged configuration (defaults + project overlay):

```bash
python3 skills/skill-creator/scripts/skill_utils.py
```

Use this before debugging validation behavior or tier choices.

---

## 5. Usage Guide

### 5.1 Create a New Skill

Always inspect available tiers first:

```bash
python3 skills/skill-creator/scripts/init_skill.py --help
```

Then create the skill:

```bash
python3 skills/skill-creator/scripts/init_skill.py my-new-skill --tier 2
```

What it does:

- creates `scripts/`, `examples/`, `assets/`, `references/`,
- generates `SKILL.md` from template,
- prints catalog update reminder (if configured).

### 5.2 Validate a Skill

Standard validation:

```bash
python3 skills/skill-creator/scripts/validate_skill.py skills/my-new-skill
```

Strict execution-policy mode:

```bash
python3 skills/skill-creator/scripts/validate_skill.py skills/my-new-skill --strict-exec-policy
```

Core checks:

- `SKILL.md` and frontmatter correctness,
- folder structure and prohibited files,
- description prefix and metadata compliance,
- inline efficiency limits,
- execution-policy coverage (warning-first by default).

### 5.3 Enhance an Existing Skill

```bash
python3 skills/skill-enhancer/scripts/analyze_gaps.py skills/my-new-skill
```

Gap analysis includes:

- weak language,
- missing required sections,
- token-efficiency issues,
- execution-policy gaps (missing contract/safety/evidence sections).

---

## 6. Best Practices (Gold Standard)

1. **Script-first for logic**: if a step needs >5 lines of conditional text, move it to script.
2. **Imperative language**: prefer `MUST`, `EXECUTE`, `VERIFY`; avoid weak modal wording.
3. **Examples first**: keep realistic examples in `examples/`.
4. **Deterministic evidence**: include validation commands and expected outputs.
5. **No hidden defaults**: every new parameter must be documented in `references/default_parameters.md`.

---

## 7. Command Path Notes

This repository uses paths like `skills/skill-creator/...`.

If your project mounts skills under `.agent/skills/`, run the same scripts through that path layout. The behavior is identical; only root path differs.

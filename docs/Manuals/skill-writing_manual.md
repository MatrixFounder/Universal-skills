# Skill Writing Manual

**Tools for Agentic Development**

This manual describes how to use **Skill Creator** and **Skill Enhancer** to build authoritative, high-quality agent skills. The tooling is project-agnostic and configurable.

---

## 1. Overview

The meta-skill toolchain has two primary components:

1. **Skill Creator**: bootstraps new skills with a standardized structure, validates base compliance, and provides eval automation.
   - Scripts: `init_skill.py`, `validate_skill.py`, `aggregate_benchmark.py`, `generate_report.py`, `generate_review.py`, `skill_utils.py`
2. **Skill Enhancer**: analyzes existing skills for quality/compliance gaps and suggests refactoring direction.
   - Script: `analyze_gaps.py`, `skill_utils.py`

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
2. **Graduated Instructions**: Use strict imperatives (`MUST`, `NEVER`) ONLY for safety-critical boundaries. For general behavioral steps, use softer verbs (`Apply`, `Consider`, `Review`). This prevents "pushy" behavior from LLMs.
3. **Behavioral Analysis**: Pay attention to *how* the skill instructs the agent to act. Skills shouldn't make the agent unnecessarily aggressive or robotic. The `analyze_gaps.py` tool will flag overly rigid language outside of safety rules.
4. **Description Pushiness (CSO)**: Keep `description:` fields under 50 words. Start with an action prefix (like `Use when`, `Standards for`). Avoid selling the skill ("This amazing skill will...").
5. **Examples first**: keep realistic examples in `examples/`.
6. **Deterministic evidence**: include validation commands and expected outputs.
7. **No hidden defaults**: every new parameter must be documented in `references/default_parameters.md`.

---

## 7. Structured Evals Workflow

You should define test cases (evals) to ensure your skill works reliably.

### Defining Evals
Create `evals/evals.json` in your skill directory. Define realistic user prompts and expected outcomes. Schema details are in `references/eval_schemas.md`.

### Running the Evals
The full eval cycle is vendor-agnostic and relies on standard LLM execution logic:

1. **Execute**: Run the test prompt using your preferred LLM/CLI.
2. **Grade**: Run the test transcript and output through `agents/grader.md`. This produces `grading.json`.
3. **Compare** *(Optional)*: If making changes, run both old and new versions. Ask `agents/comparator.md` to run a blind A/B test. This produces `comparison.json`.
4. **Analyze** *(Optional)*: If you want to know *why* one version won, run `agents/analyzer.md` on the comparison results.

### Benchmark Automation Scripts
We provide vendor-agnostic scripts in `skill-creator/scripts/` to automate processing of benchmark results:

*   **`aggregate_benchmark.py <run-directory>`**: Reads all `grading.json` files and computes statistical summaries (pass margins, times, token usage). Outputs `benchmark.json` and a Markdown summary.
*   **`generate_report.py benchmark.json`**: Reads the aggregated benchmark and builds a visual HTML report.
*   **`generate_review.py <workspace-path>`**: Launches a minimal local HTTP server offering a rich, browser-based UI (`viewer.html`) to visually inspect run transcripts, grade outputs, and leave structured feedback.

### Using Eval-Viewer (`generate_review.py`)
To use the visual eval-viewer, structure your test runs into a workspace folder:

```text
eval-workspace/
├── eval_1_basic_usage/
│   ├── transcript.md      # Must contain the prompt under a "## Eval Prompt" header
│   ├── grading.json       # (Optional) JSON with Pass/Fail grades from the grader agent
│   └── outputs/           # Must contain generated files (code, images, etc.)
├── eval_2_edge_case/
│   ├── transcript.md
│   └── outputs/
```

Run the server pointing to your workspace:
```bash
python3 .agent/skills/skill-creator/scripts/generate_review.py path/to/eval-workspace --skill-name "my-skill"
```
The script will output a `localhost` URL. Open it in your browser to:
1. **Navigate** through all test runs.
2. **Inspect** the exact prompt sent and view generated files (`outputs/`) natively in the browser.
3. **Leave Feedback** using the bottom text area. Your notes are auto-saved to `feedback.json` within your workspace.
4. **Compare Iterations**: If you have an older workspace, append `--previous-workspace path/to/old-workspace` to instantly compare before-and-after outputs and past feedback.

---

## 8. Command Path Notes

This repository uses paths like `skills/skill-creator/...` in examples.

If your project mounts skills under `.agent/skills/` (the standard Agent deployment model), run the same scripts through that path layout (`.agent/skills/skill-creator/...`). The behavior is identical; only the root path differs.

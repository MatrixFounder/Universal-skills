# Universal-Skills

**Universal-Skills** is a collection of high-leverage "Meta-Skills" designed to upgrade AI Agents from simple chat bots to autonomous engineers.

Unlike standard prompts, these skills are **Agent-Agnostic** and **Architecture-Agnostic**. They function as plug-and-play modules that give an agent specific capabilities (e.g., "Review Code like a Sarcastic Senior Engineer", "Generate production-ready MCP servers", "Humanize AI text").

## Table of Contents
- [Universal-Skills](#universal-skills)
  - [Table of Contents](#table-of-contents)
  - [Installation](#installation)
    - [Antigravity (Recommended)](#antigravity-recommended)
    - [Cursor](#cursor)
    - [Claude (Projects)](#claude-projects)
  - [Skill Registry](#skill-registry)
    - [Core Meta-Skills](#core-meta-skills)
    - [Development Skills](#development-skills)
    - [Content Skills](#content-skills)
    - [Office Skills](#office-skills)
    - [Verification Skills (VDD)](#verification-skills-vdd)
    - [Agentic Workflows](#agentic-workflows)
    - [Custom Commands Deployment](#custom-commands-deployment)
  - [Contributing](#contributing)
  - [Documentation](#documentation)

## Installation

First, clone this repository to your machine:
```bash
git clone https://github.com/MatrixFounder/Universal-skills
```

Then, choose your platform below.

### Antigravity (Recommended)
**Where skills live**
| Location | Scope |
| :--- | :--- |
| `<workspace-root>/.agent/skills/<skill-folder>/` | Workspace-specific (Skills) |
| `<workspace-root>/.agent/workflows/<workflow.md>` | Workspace-specific (Workflows) |
| `~/.gemini/antigravity/global_skills/<skill-folder>/` | Global (Skills) |

**Setup**
1.  Copy the `skills` folder content into one of the locations above.
2.  The agent will automatically index and load the skills.
3.  See [Antigravity Skills Docs](https://antigravity.google/docs/skills).

### Cursor
**Where skills live**

Skills are automatically loaded from these locations:

| Location | Scope |
| :--- | :--- |
| `.cursor/skills/` | Project-level |
| `.claude/skills/` | Project-level (Claude compatibility) |
| `.codex/skills/` | Project-level (Codex compatibility) |
| `~/.cursor/skills/` | User-level (global) |
| `~/.claude/skills/` | User-level (global, Claude compatibility) |
| `~/.codex/skills/` | User-level (global, Codex compatibility) |

**Setup**
1.  Copy the `skills` folder content into one of the locations above.
2.  Cursor will automatically recognize these as distinct capabilities.
3.  See [Cursor Skills Docs](https://cursor.com/docs/context/skills).

### Claude Code
**Where skills live**
| Location | Scope |
| :--- | :--- |
| `<workspace-root>/.claude/skills/<skill-folder>/` | Workspace-specific (Project) |
| `~/.claude/skills/<skill-folder>/` | Global (Personal) |

**Setup**
1.  Copy the `skills` folder content into one of the locations above.
2.  See [Claude Code Skills Docs](https://code.claude.com/docs/en/skills).

## Skill Registry

### Core Meta-Skills

| Skill | Description | Tier |
| :--- | :--- | :--- |
| **[Brainstorming](skills/brainstorming/SKILL.md)** | Explores user intent, clarifies requirements, and designs solutions with domain-specific research and self-correction. Use before writing code. | 2 |
| **[Skill Enhancer](skills/skill-enhancer/SKILL.md)** | A meta-skill to audit, fix, and improve other skills. Enforces "Gold Standard" compliance (TDD, CSO, Script-First). Implements rules from [Skill Execution Policy](docs/SKILL_EXECUTION_POLICY.md). | 2 |
| **[Skill Creator](/skills/skill-creator/SKILL.md)** | Authoritative guidelines for creating NEW skills. Ensures compliant directory structure and philosophy. Implements rules from [Skill Execution Policy](docs/SKILL_EXECUTION_POLICY.md). | 2 |
| **[Summarizing Meetings](skills/summarizing-meetings/SKILL.md)** | Meta-skill for generating meeting summaries from transcriptions. Auto-detects meeting type (standup, retro, discovery), selects template, and produces a two-level pyramid Markdown document optimized for people, AI agents, RAG, and Obsidian. | 2 |

### Development Skills

| Skill | Description | Tier |
| :--- | :--- | :--- |
| **[MCP Builder](skills/mcp-builder/SKILL.md)** | Comprehensive guide for building Model Context Protocol (MCP) servers in Python or TypeScript. Includes best practices for tool design. | - |
| **[Hooks Creator](skills/hooks-creator/SKILL.md)** | Generates secure, compliant Gemini CLI hooks (Bash/Node) with automated config and VDD-verified security gates. | 2 |

### Content Skills

| Skill | Description | Tier |
| :--- | :--- | :--- |
| **[Post Writing](skills/post-writing/SKILL.md)** | 4-step editorial pipeline for LinkedIn/Telegram posts: analyze → hook → draft → review. Includes brand voice guides (RU/EN), 7 hook formulas, platform formatting, and review checklist. | 2 |
| **[Text Humanizer](skills/text-humanizer/SKILL.md)** | Rewrites text to remove "AI slop" or generates prompt tailored to specific genres (Wiki, Crypto, etc.). | 2 |
| **[Marp Slide Creator](skills/marp-slide/SKILL.md)** | Creates professional Marp presentation slides with 7 pre-designed themes. Supports image layouts, custom CSS, and "make it look good" requests with automatic theme inference. | 2 |

### Office Skills

Open-source replacements for Anthropic's proprietary `docx` / `xlsx`
/ `pptx` / `pdf` skills. Built from public specifications (ECMA-376,
Microsoft Open Specification Promise, W3C, PDF ISO 32000-2) and
open-source libraries — Apache-2.0 licensed; full attribution in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

| Skill | Description | Tier |
| :--- | :--- | :--- |
| **[docx](skills/docx/SKILL.md)** | Create / edit / convert / validate `.docx`. Markdown ↔ DOCX, template fill (`{{placeholders}}`), accept tracked changes (LibreOffice), unpack/pack OOXML, **redlining validator** (`--compare-to ORIGINAL.docx`) catches "editor forgot Track Changes" scenarios. | 2 |
| **[xlsx](skills/xlsx/SKILL.md)** | CSV → styled `.xlsx` (bold header, frozen row, auto-filter, leading-zero preservation), force formula recalculation via LibreOffice, scan for `#REF!`/`#DIV/0!` errors. | 2 |
| **[pptx](skills/pptx/SKILL.md)** | Markdown → PPTX (built-in pptxgenjs renderer with auto-pagination, mermaid diagrams, accent stripes — OR `--via-marp` delegation to marp-slide for editorial polish), pptx → PDF, slide thumbnail grids. | 2 |
| **[pdf](skills/pdf/SKILL.md)** | Markdown → PDF (weasyprint), PDF merge / split (by ranges, per-page, fixed chunks), bookmark preservation. | 2 |

The three OOXML skills (docx/xlsx/pptx) share an identical
`scripts/office/` module + `_soffice.py` LibreOffice wrapper. The
`docx` skill is the **MASTER** — modifications must follow the
strict replication protocol in
[CONTRIBUTING.md §3](docs/CONTRIBUTING.md#3-office-skills-modification-protocol-strict).

For practical usage of all four skills, see the
[Office Skills Manual](docs/Manuals/office-skills_manual.md).

### Verification Skills (VDD)

| Skill | Description | Tier |
| :--- | :--- | :--- |
| **[VDD Adversarial](skills/vdd-adversarial/SKILL.md)** | Verification-Driven Development. Challenges assumptions, simulates failures, and rejects "happy path" thinking. | 2 |
| **[VDD Sarcastic](skills/vdd-sarcastic/SKILL.md)** | The "Sarcasmotron". Same rigor as VDD Adversarial, but with a provocative tone to force the agent/user to defend their logic. | 2 |
| **[Skill Validator](skills/skill-validator/SKILL.md)** | Automated security & compliance scanner for skills. Detects malware, obfuscation, Base64 payloads, and structural violations. | 2 |

### Agentic Workflows

| Workflow | Description |
| :--- | :--- |
| **[Auto-Healing Skill](.agent/workflows/auto-heal-skill.md)** | Automated "Doctor" loop. Runs `skill-validator` to find issues, then activates `skill-enhancer` to fix them using VDD-verified patterns. |

### Custom Commands Deployment

To make the **Auto-Healing Workflow** available as a native command (`/auto-heal-external-skill`), follow these steps:

#### Gemini CLI
Create a symlink to the custom command definition:

```bash
mkdir -p ~/.gemini/commands
ln -s $(pwd)/custom-commands/auto-heal-external-skill.toml ~/.gemini/commands/auto-heal-external-skill.toml
```

**Usage**: `/auto-heal-external-skill <path/to/skill>`

#### Claude
Create a symlink to the slash command definition:

```bash
mkdir -p ~/.claude/commands
ln -s $(pwd)/commands/auto-heal-external-skill.md ~/.claude/commands/auto-heal-external-skill.md
```

**Usage**: `/auto-heal-external-skill <path/to/skill>`

## Contributing

Before opening a PR or modifying any skill, read
[**docs/CONTRIBUTING.md**](docs/CONTRIBUTING.md). It covers:

- Project layout and per-skill structure conventions.
- Universal change checklist (tests, validator, examples, gitignore).
- **STRICT** Office-skills modification protocol — all changes to
  `scripts/office/` or `_soffice.py` must be made in the `docx`
  master skill and then byte-replicated to `xlsx` and `pptx` in the
  same commit. `diff -qr` between the three is enforced.
- Adding a new skill via `skill-creator`.
- Commit hygiene (no `node_modules/`, `.venv/`, compiled binaries,
  ECMA schemas in tree).

Agent-facing rules (development environment behaviours, replication
protocol enforcement) live in [CLAUDE.md](CLAUDE.md) and
[GEMINI.md](GEMINI.md), which are kept in sync.

## Documentation

Detailed manuals for specific components can be found in `docs/Manuals`:

- **[Text Humanizer Manual](docs/Manuals/text_humanizer_manual.md)**: Deep dive into the Humanizer's taxonomy and patterns.
- **[Post Writing Manual](docs/Manuals/post-writing_manual.md)**: Prompt formulas, IDE/Agent examples, and automated content pipeline architecture.
- **[Skill Writing Manual](docs/Manuals/skill-writing_manual.md)**: Detailed guide on the philosophy of "Rich Skills".
- **[Hooks Creator Manual](docs/Manuals/hooks-creator_manual.md)**: Guide to generating lifecycle hooks and security blockers.
- **[Skill Validator Manual](docs/Manuals/skill-validator_manual.md)**: Security auditing guide — CLI reference, architecture, pattern catalog, and CI/CD integration.
- **[Auto-Healing Workflow](docs/manuals/auto-fix-workflow.md)**: Guide to using the automated repair loop for skills.
- **[Summarizing Meetings Manual](docs/Manuals/summarizing-meetings_manual.md)**: Guide to the meeting summary meta-skill — templates, autodetect, tag taxonomy, and Obsidian integration.
- **[Marp Slide Creator Manual](docs/Manuals/marp-slide_manual.md)**: Guide to creating Marp presentations — theme selection, image patterns, CSS customization, and quality checklist.
- **[Marp CLI Manual](docs/Manuals/marp-cli_manual.md)**: Installation, dependencies, core commands, configuration, and troubleshooting for Marp CLI renderer.
- **[Office Skills Manual](docs/Manuals/office-skills_manual.md)**: Practical reference for `docx` / `xlsx` / `pptx` / `pdf` — install, common workflows, the redlining validator (`--compare-to`), and the LD_PRELOAD AF_UNIX shim for sandboxed deployment.

Project-level guides:

- **[CONTRIBUTING.md](docs/CONTRIBUTING.md)**: How to modify skills (universal checklist) and the **strict** office-skills replication protocol (`docx` → `xlsx`/`pptx`, byte-identical).
- **[Office Skills Refactoring Plan](docs/refactoring-office-skills.md)**: Original design rationale for the open-source office skill architecture (historical reference; do not edit, supersede via CONTRIBUTING.md).
- **[SKILL_EXECUTION_POLICY.md](docs/SKILL_EXECUTION_POLICY.md)**: When to use script-first vs prompt-first, Tier definitions used by `skill-validator`.

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
    - [Verification Skills (VDD)](#verification-skills-vdd)
    - [Agentic Workflows](#agentic-workflows)
    - [Custom Commands Deployment](#custom-commands-deployment)
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

## Documentation

Detailed manuals for specific components can be found in `docs/Manuals`:

- **[Text Humanizer Manual](docs/Manuals/text_humanizer_manual.md)**: Deep dive into the Humanizer's taxonomy and patterns.
- **[Post Writing Manual](docs/Manuals/post-writing_manual.md)**: Prompt formulas, IDE/Agent examples, and automated content pipeline architecture.
- **[Skill Writing Manual](docs/Manuals/skill-writing_manual.md)**: Detailed guide on the philosophy of "Rich Skills".
- **[Hooks Creator Manual](docs/Manuals/hooks-creator_manual.md)**: Guide to generating lifecycle hooks and security blockers.
- **[Skill Validator Manual](docs/Manuals/skill-validator_manual.md)**: Security auditing guide — CLI reference, architecture, pattern catalog, and CI/CD integration.
- **[Auto-Healing Workflow](docs/manuals/auto-fix-workflow.md)**: Guide to using the automated repair loop for skills.
- **[Summarizing Meetings Manual](docs/Manuals/summarizing-meetings_manual.md)**: Guide to the meeting summary meta-skill — templates, autodetect, tag taxonomy, and Obsidian integration.

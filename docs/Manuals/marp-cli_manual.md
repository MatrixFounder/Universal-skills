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
# Use custom theme
marp --theme ./my-theme.css slides.md -o slides.html

# Use theme from URL
marp --theme https://example.com/theme.css slides.md
```

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
allowLocalFiles: true
theme: ./assets/custom-theme.css
html: true
pdf: false
options:
  loggingLevel: warn
```

Supported configuration formats: `.marprc.yml`, `.marprc.yaml`, `.marprc.json`, `.marprc.js`, `marp.config.js`, `marp.config.mjs`.

## Integration with marp-slide Skill

The `marp-slide` skill and Marp CLI work **independently** but complement each other:

```
┌─────────────────┐         ┌─────────────┐         ┌──────────────┐
│   marp-slide    │         │  Marp CLI   │         │   Output     │
│   (AI skill)    │ ──MD──▶ │  (renderer) │ ──▶──▶  │  HTML/PDF/   │
│                 │         │             │         │  PPTX/PNG    │
│ Generates .md   │         │ Converts to │         │              │
│ with embedded   │         │ final format│         │ Ready to     │
│ CSS & content   │         │             │         │ present      │
└─────────────────┘         └─────────────┘         └──────────────┘
```

- **marp-slide** generates the `.md` file with embedded CSS, structured content, and proper Marp markup
- **Marp CLI** converts that file into the final format
- **Alternative to CLI** — the Marp for VS Code extension (preview: `Cmd+Shift+V`, export via Command Palette)

### Typical Workflow

```bash
# 1. Ask the AI to generate slides (marp-slide skill)
# → Output: presentation.md

# 2. Preview in VS Code
#    Cmd+Shift+V

# 3. Export to PDF for sharing
marp presentation.md --pdf

# 4. Or start a dev server for live presentation
marp -s . --port 3000
```

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

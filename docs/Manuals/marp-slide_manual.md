# Marp Slide Creator Manual

The **marp-slide** skill creates professional Marp presentation slides with 7 pre-designed themes, embedded CSS, and built-in quality guidelines. It handles everything from theme selection to image layouts, including vague requests like "make it look good."

## Table of Contents
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Quick Usage](#quick-usage)
  - [Rendering Output](#rendering-output)
- [Theme Selection](#theme-selection)
  - [Decision Flow](#decision-flow)
  - [Theme Files](#theme-files)
- [Slide Structure](#slide-structure)
  - [Title Slide](#title-slide)
  - [Content Slides](#content-slides)
  - [Guidelines](#guidelines)
  - [Recommended Flow](#recommended-flow)
- [Image Patterns](#image-patterns)
  - [Common Layouts](#common-layouts)
  - [Filters](#filters)
- [Using External Themes](#using-external-themes)
  - [Where to Find Themes](#where-to-find-themes)
  - [How to Use an External Theme](#how-to-use-an-external-theme)
- [Adding New Themes to the Skill](#adding-new-themes-to-the-skill)
- [Developing Custom Themes](#developing-custom-themes)
  - [Theme Structure](#theme-structure)
  - [Minimal Theme Skeleton](#minimal-theme-skeleton)
  - [Extending an Official Theme](#extending-an-official-theme)
  - [CSS Custom Properties (Variables)](#css-custom-properties-variables)
  - [Custom Slide Classes](#custom-slide-classes)
  - [Design Checklist](#design-checklist)
- [Quality Checklist](#quality-checklist)
- [Advanced Features](#advanced-features)
- [Troubleshooting](#troubleshooting)
- [Skill Resources](#skill-resources)

## Getting Started

### Prerequisites

Pick **one** of the two options:

**Option 1 — Skill renderer (recommended, no global installs)**
From the skill root, run `bash scripts/install.sh` once. It creates `scripts/.venv/` (Python venv) and `scripts/node_modules/` (local marp-cli + mermaid-cli + Puppeteer Chromium). All subsequent renders go through `scripts/render deck.md`. This is the only path that preprocesses mermaid diagrams.

**Option 2 — Global marp-cli**
`npm install -g @marp-team/marp-cli` (plus the "Marp for VS Code" extension for in-editor preview). Quick to set up, but mermaid blocks will render as raw code — marp-core has no mermaid support.

### Quick Usage
Ask the agent to create a presentation:
> "Create a 10-slide presentation about microservices architecture for a tech meetup"

> "Make slides for our Q3 business review, keep it professional"

> "良い感じにスライド作って" (Make nice slides)

The skill automatically:
1. Infers the best theme from your content type
2. Loads the template with tested, embedded CSS
3. Structures content following best practices
4. Outputs a ready-to-render `.md` file

### Rendering Output

**Preferred — via the skill's renderer** (handles mermaid, runs from a local venv, no global installs):

```bash
scripts/render presentation.md --format html       # → presentation.html
scripts/render presentation.md --format pdf        # → presentation.pdf
scripts/render presentation.md --format pptx       # → presentation.pptx (default)
scripts/render presentation.md --format png        # → presentation.png
scripts/render presentation.md --format jpeg       # → presentation.jpeg
```

Flags: `--output PATH`, `--no-mermaid` (skip preprocessing), `--strict-mermaid` (fail on mermaid error instead of warning), `--theme NAME`, `--mermaid-config PATH` (Cyrillic/CJK font fix). See `scripts/README.md` for the full reference and exit codes.

**Alternative — raw marp-cli** (power users; no mermaid preprocessing):

```bash
marp presentation.md -o presentation.html
marp presentation.md -o presentation.pdf
marp presentation.md -o presentation.pptx
marp presentation.md --images png
```

## Theme Selection

The skill includes 7 themes, each with a complete CSS file and Markdown template.

| Theme | Colors | Best For | Atmosphere |
|:---|:---|:---|:---|
| **Default** | Beige bg, navy text, blue headings | General seminars, lectures | Calm, elegant |
| **Minimal** | White bg, gray text, black headings | Academic talks, content-focused | Clean, simple |
| **Colorful** | Pink gradients, multi-color accents | Creative projects, youth events | Fun, energetic |
| **Dark** | Black bg, cyan/purple accents | Tech talks, evening events | Cool, modern |
| **Gradient** | Per-slide gradient backgrounds | Visual presentations, keynotes | Vivid, dynamic |
| **Tech** | GitHub-style dark, blue/green accents | Dev meetups, programming courses | Technical, developer |
| **Business** | White bg, navy headings, blue accents | Proposals, reports, reviews | Formal, professional |

### Decision Flow

1. **What's the content type?**
   - Technical/Developer → **Tech**
   - Business/Corporate → **Business**
   - Creative/Event → **Colorful** or **Gradient**
   - Academic/Simple → **Minimal**
   - General/Unsure → **Default**

2. **What background does the user prefer?**
   - Bright/Light → Default, Minimal, Business
   - Dark → Dark, Tech
   - Colorful/Dynamic → Colorful, Gradient

3. **Still unsure?** → Use **Default**. It works for most use cases.

### Theme Files

Each theme has two files in the skill's `assets/` directory:
- **Template** (`template-*.md`): Complete Marp file with embedded CSS and sample slides
- **CSS** (`theme-*.css`): Standalone CSS for reference

The templates are self-contained — CSS is embedded directly, so the output file needs no external dependencies.

## Slide Structure

### Title Slide
Every presentation starts with a lead-class title slide:
```markdown
<!-- _class: lead -->

# Presentation Title
## Subtitle or tagline

Author | Date
```

### Content Slides
Separated by `---`, each content slide follows this pattern:
```markdown
---

## Slide Title

- First key point
- Second key point
- Third key point
```

### Guidelines

| Rule | Japanese | English |
|:---|:---|:---|
| **Title length** | 5-7 characters | 2-5 words |
| **Bullets per slide** | 3-5 items | 3-5 items |
| **Text per bullet** | 15-25 characters | 8-15 words |
| **Slide count (5 min)** | 5-8 slides | 5-8 slides |
| **Slide count (10 min)** | 10-15 slides | 10-15 slides |
| **Slide count (20 min)** | 15-25 slides | 15-25 slides |

### Recommended Flow
1. **Title slide** — `<!-- _class: lead -->` + h1
2. **Agenda** — overview of topics
3. **Content slides** — one topic per slide
4. **Summary** — key takeaways
5. **Closing slide** — `<!-- _class: lead -->` + thank you / Q&A

## Image Patterns

Marp uses special image syntax that differs from standard Markdown. These patterns are documented in detail in `references/image-patterns.md`.

### Common Layouts

**Side image (text left, image right):**
```markdown
## Slide Title

![bg right:40%](product-photo.png)

- Point about the product
- Another key detail
- Final observation
```

**Full background:**
```markdown
![bg](hero-image.jpg)

# Overlay Title
```

**Sized inline image:**
```markdown
## Architecture Diagram

![w:600px](architecture.png)
```

**Split comparison (two images):**
```markdown
![bg left:50%](before.png)
![bg right:50%](after.png)
```

### Filters
Apply CSS-like filters to background images:
```markdown
![bg brightness:0.5](hero.png)        <!-- darken -->
![bg blur:5px](background.png)        <!-- blur -->
![bg grayscale:1](photo.png)          <!-- black & white -->
![bg sepia:0.8](vintage-photo.png)    <!-- sepia tone -->
```

## Using External Themes

Beyond the 7 built-in themes, the Marp community offers dozens of ready-made themes.

### Where to Find Themes

| Source | Description |
|:---|:---|
| [Awesome Marp](https://github.com/marp-team/awesome-marp) | Official curated list — themes, plugins, tools |
| [Marp Community Themes](https://rnd195.github.io/marp-community-themes/) | Visual gallery with live previews |
| [MarpX](https://github.com/cunhapaulo/MarpX) | Professional themes for academics and researchers |
| [Marpstyle](https://github.com/cunhapaulo/marpstyle) | Clean, minimalist designs |
| [Awesome-Marp (favourhong)](https://github.com/favourhong/Awesome-Marp) | LaTeX Beamer replacement — 12+ academic themes |
| [GitHub: marp-themes](https://github.com/topics/marp-themes) | All community repos tagged `marp-themes` |

Notable individual themes: **Beam** (LaTeX Beamer), **Dracula** (dark), **Nord** (cold palette), **Rose Pine** (soft dark), **Graph Paper** (grid background).

### How to Use an External Theme

**Method 1: Download CSS and apply via CLI**
```bash
# Download theme
curl -O https://raw.githubusercontent.com/rnd195/my-marp-themes/main/themes/academic.css

# Apply when converting
marp --theme ./academic.css slides.md -o slides.html
```

**Method 2: Use --theme-set for a folder of themes**
```bash
# Place multiple .css files in a folder
marp --theme-set ./themes/ slides.md --pdf
```

**Method 3: Embed CSS directly in the Markdown file**

Download the theme CSS, then paste it inside a `<style>` block. This makes the file self-contained — no external files needed at render time:
```markdown
---
marp: true
theme: default
paginate: true
---

<style>
/* Paste the full theme CSS here */
section { background: #1a1a2e; color: #eee; }
h1, h2 { color: #e94560; }
/* ... */
</style>

<!-- _class: lead -->
# My Presentation
```

> **Tip:** Method 3 is what the `marp-slide` skill uses — all 7 built-in templates embed their CSS directly so the output file has zero external dependencies.

### Security Note

Only use themes from trusted sources. A malicious CSS file can exfiltrate data via external URL requests (see `content: url("https://evil.com/...")`). Review CSS before applying. The built-in skill themes in `assets/` are safe.

**Renderer security:** `scripts/render.py` invokes marp with `--allow-local-files` **unconditionally** — unlike raw marp-cli, where this flag is off by default. The flag is needed so marp can embed the skill's own cached SVGs under `<input>_assets/`, but a side effect is that a malicious `.md` can read any file the current user can read (e.g. `![bg](/etc/passwd)`). **Render only decks you trust** via `scripts/render`; for untrusted input, use raw `marp` with default-safe flags instead.

## Adding New Themes to the Skill

To extend the `marp-slide` skill with a new theme:

### Step 1: Create the CSS File

Save the theme CSS to `assets/theme-<name>.css`:

```css
/* @theme my-corporate */

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

section {
  background-color: #ffffff;
  color: #1a1a1a;
  font-family: 'Inter', sans-serif;
  font-size: 22px;
  padding: 60px;
}

h1, h2 { color: #0066cc; font-weight: 700; }

h2 {
  border-bottom: 2px solid #0066cc;
  padding-bottom: 8px;
  margin-bottom: 32px;
}

section.lead {
  background: linear-gradient(135deg, #0066cc, #004499);
  color: #ffffff;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

section.lead h1, section.lead h2 { color: #ffffff; }
```

### Step 2: Create the Template

Save a ready-to-use Markdown template to `assets/template-<name>.md`:

```markdown
---
marp: true
theme: default
paginate: true
---

<style>
/* Paste the FULL CSS from theme-<name>.css here */
</style>

<!-- _class: lead -->

# Presentation Title
## Subtitle

Author | Date

---

## Agenda

- Topic 1
- Topic 2
- Topic 3

---

## Slide Title

- Key point 1
- Key point 2
- Key point 3
```

The template must embed the full CSS — this ensures the output file is self-contained.

### Step 3: Register in SKILL.md

Add the new theme to the "Available Themes" section and the theme selection rules:

```markdown
### 8. Corporate Theme
**Colors**: White background, blue headings, Inter font
**Style**: Clean corporate with gradient lead slides
**Use for**: Internal presentations, corporate reports
**Template**: `template-corporate.md`
```

Update the Quick Start theme selection:
```markdown
- **Corporate/Internal** → corporate theme
```

### Step 4: Verify

- Open the template in VS Code with Marp extension (`Cmd+Shift+V`)
- Check that lead slides, content slides, lists, and code blocks render correctly
- Export to PDF: `marp --theme ./assets/theme-<name>.css template-<name>.md --pdf`

## Developing Custom Themes

Full CSS reference: `references/theme-css-guide.md` and [Marpit Theme CSS docs](https://marpit.marp.app/theme-css).

### Theme Structure

Every Marp theme CSS file must start with the `@theme` metadata comment:

```css
/* @theme my-theme */
```

Without this line, Marp will not recognize the file as a theme.

### Minimal Theme Skeleton

```css
/* @theme my-theme */

/* --- Base slide --- */
section {
  background-color: #ffffff;
  color: #333333;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 22px;
  padding: 60px;
  width: 1280px;          /* 16:9 default */
  height: 720px;
}

/* --- Typography --- */
h1 { font-size: 48px; color: #1a1a1a; }
h2 { font-size: 36px; color: #333333; margin-bottom: 24px; }
h3 { font-size: 28px; color: #555555; }

/* --- Lists --- */
ul, ol { padding-left: 1.5em; }
li { margin-bottom: 8px; }
li::marker { color: #3b82f6; }

/* --- Code --- */
pre {
  background-color: #f5f5f5;
  border-radius: 6px;
  padding: 16px;
  font-size: 16px;
}
code {
  font-family: 'Fira Code', monospace;
  background-color: #f0f0f0;
  padding: 2px 6px;
  border-radius: 3px;
}

/* --- Lead (title) slides --- */
section.lead {
  display: flex;
  flex-direction: column;
  justify-content: center;
  text-align: center;
}

/* --- Page numbers --- */
section::after {
  content: attr(data-marpit-pagination) ' / ' attr(data-marpit-pagination-total);
  position: absolute;
  right: 30px;
  bottom: 20px;
  font-size: 14px;
  color: #999;
}
```

### Extending an Official Theme

Instead of writing from scratch, inherit from an official theme and override:

```css
/* @theme my-extended-default */
@import-theme 'default';

/* Override just what you need */
section {
  font-family: 'Inter', sans-serif;
  background-color: #fafafa;
}

h1, h2 { color: #0055aa; }

section.lead {
  background: linear-gradient(135deg, #0055aa, #003377);
  color: #fff;
}
section.lead h1 { color: #fff; }
```

Available base themes: `default`, `gaia`, `uncover`.

### CSS Custom Properties (Variables)

Use variables for consistent theming and easy customization:

```css
/* @theme configurable */

:root {
  --bg: #ffffff;
  --fg: #333333;
  --heading: #0066cc;
  --accent: #e94560;
  --font: 'Inter', sans-serif;
  --font-code: 'Fira Code', monospace;
}

section { background: var(--bg); color: var(--fg); font-family: var(--font); }
h1, h2 { color: var(--heading); }
strong { color: var(--accent); }
code { font-family: var(--font-code); }
```

Users can then override variables per-slide with `<style scoped>`:
```markdown
<style scoped>
:root { --bg: #1a1a2e; --fg: #eee; --heading: #e94560; }
</style>

## This Slide Has Dark Background
```

### Custom Slide Classes

Define reusable class variations beyond `lead` and `invert`:

```css
/* Section break slide */
section.section-break {
  background: linear-gradient(135deg, var(--heading), var(--accent));
  color: #fff;
  display: flex;
  justify-content: center;
  align-items: center;
}

/* Quote slide */
section.quote {
  background-color: #f8f8f8;
  font-style: italic;
  font-size: 28px;
  display: flex;
  justify-content: center;
  align-items: center;
}
```

Use in Markdown:
```markdown
<!-- _class: section-break -->
# Part 2: Implementation

---

<!-- _class: quote -->
> "Any sufficiently advanced technology is indistinguishable from magic."
> — Arthur C. Clarke
```

### Design Checklist

Before finalizing a custom theme, verify:

- [ ] Contrast ratio between background and text is 4.5:1 or higher
- [ ] Body font size is 22-24px, h1 is 40-60px
- [ ] Padding is 60px or more (content should not touch edges)
- [ ] `section.lead` class is styled for title slides
- [ ] `section::after` is styled for page numbers
- [ ] Code blocks (`pre`, `code`) have distinct background
- [ ] Lists (`ul`, `ol`, `li::marker`) are styled
- [ ] Fallback fonts are specified (system fonts after web fonts)
- [ ] Theme renders correctly in both HTML preview and PDF export

### Google Fonts
All built-in templates import Noto Sans JP for Japanese support:
```css
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&display=swap');
```

## Quality Checklist

Before delivering slides, verify all items pass:

- [ ] Theme selected based on content type (not defaulted lazily)
- [ ] CSS theme is embedded in the output file
- [ ] Title slide uses `<!-- _class: lead -->`
- [ ] Slide titles are concise (5-7 chars JP / 2-5 words EN)
- [ ] Bullet points are 3-5 items per slide
- [ ] Images use Marp syntax (not standard Markdown)
- [ ] File saved to user's working directory
- [ ] Content follows logical flow (intro, body, conclusion)

## Advanced Features

### Math Notation (KaTeX)
```markdown
Inline: $E = mc^2$

Block:
$$
\int_0^\infty f(x) dx = F(\infty) - F(0)
$$
```

### Emoji
Use GitHub emoji notation:
```markdown
:rocket: Launch day!
:warning: Important caveat
:chart_with_upwards_trend: Growth metrics
```

### Fragmented Lists
Progressive reveal in HTML export (requires `--html` flag):
```markdown
* First point
* Second point (appears next)
* Third point (appears last)
```

### Marp CLI Watch Mode
Live preview during development:
```bash
marp -w presentation.md -o presentation.html
```

### VS Code Preview
1. Open the `.md` file in VS Code
2. Press `Ctrl+Shift+V` (or `Cmd+Shift+V` on Mac)
3. The Marp preview renders automatically

### Mermaid Diagram Rendering

**Marp Core does not render mermaid natively.** Mermaid fenced blocks passed to vanilla marp-cli come out as unstyled code. The skill's renderer (`scripts/render.py`) closes that gap: it calls `mmdc` on each ` ```mermaid ` block, produces SVGs under `<input>_assets/diagram-<sha1>.svg`, and rewrites the block as a Marp image directive before handing the file to marp-cli.

**Before** (source `.md`):

    ```mermaid
    mindmap
      root((Product))
        Users
          onboarding
        Engineering
          reliability
    ```

**After** (what marp actually embeds):

    ![w:900](deck_assets/diagram-<sha1>.svg)

Flags:

| Flag | Effect |
|------|--------|
| *(default)* | Preprocess mermaid; warn and fall back to code if `mmdc` is missing |
| `--no-mermaid` | Skip preprocessing entirely (faster; diagrams remain as raw code) |
| `--strict-mermaid` | Exit 4 if any mermaid block cannot be rendered |
| `--mermaid-config PATH` | Pass `-c PATH` to `mmdc` (auto-loads `scripts/mermaid-config.json` when present). Required for Cyrillic/CJK content. |

The SVG cache key includes `mmdc --version` output and `mermaid-config.json` content, so toolchain upgrades or config edits invalidate cached SVGs automatically.

See `scripts/README.md` for the full operator guide and `skills/marp-slide/examples/fixture-mermaid-{minimal,full-deck,multi}.md` for concrete sources.

## Troubleshooting

| Problem | Cause | Fix |
|:---|:---|:---|
| No styling in preview | CSS not embedded in file | Use a template from `assets/` — it includes embedded CSS |
| Images not showing | Using standard Markdown syntax | Use Marp syntax: `![bg right:40%](image.png)` |
| Fonts look wrong | Google Fonts not imported | Add `@import url(...)` in the `<style>` block |
| PDF export fails | Chromium not installed | Run `marp --pdf` which auto-downloads Chromium, or install manually |
| Slides not splitting | Missing `---` separators | Add `---` between each slide |
| Page numbers missing | `paginate` not set | Add `paginate: true` to YAML frontmatter |
| Mermaid block renders as code, not a diagram | `mmdc` not on PATH or install didn't run | `bash scripts/install.sh`, or pass `--no-mermaid` for intentional fallback |
| Diagram looks stale after editing the mermaid source | `<input>_assets/` SHA1 cache still points at an old SVG | Delete the `<input>_assets/` directory; next render will rebuild every SVG |
| Cyrillic / CJK text in a mermaid diagram renders as boxes | `mmdc`'s default font lacks those glyphs | Create `scripts/mermaid-config.json` with `{ "themeVariables": { "fontFamily": "Arial, sans-serif" } }` (auto-loaded on next render) |
| `scripts/render` exits with code 2 (`marp CLI not found`) | Local venv wasn't built | `bash scripts/install.sh` |
| `scripts/render` exits with code 3 (`marp timed out after 300s`) | Headless Chromium hung, usually on a malformed slide | Check marp's stderr output; simplify the offending slide; re-run |

## Skill Resources

All reference materials are in the skill directory (`.claude/skills/marp-slide/`):

| Resource | Path | Purpose |
|:---|:---|:---|
| Marp syntax | `references/marp-syntax.md` | Directives, frontmatter, pagination |
| Image patterns | `references/image-patterns.md` | Background, split, filter syntax |
| Theme CSS guide | `references/theme-css-guide.md` | Custom theme creation |
| Advanced features | `references/advanced-features.md` | Math, emoji, CLI, VS Code |
| Official themes | `references/official-themes.md` | default, gaia, uncover docs |
| Theme selection | `references/theme-selection.md` | Decision flow for choosing themes |
| Best practices | `references/best-practices.md` | Quality guidelines |
| Templates | `assets/template-*.md` | 7 ready-to-use templates |
| CSS files | `assets/theme-*.css` | 7 standalone CSS themes |

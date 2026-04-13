# Marp Slide Creator Manual

The **marp-slide** skill creates professional Marp presentation slides with 7 pre-designed themes, embedded CSS, and built-in quality guidelines. It handles everything from theme selection to image layouts, including vague requests like "make it look good."

## Table of Contents
- [Getting Started](#getting-started)
- [Theme Selection](#theme-selection)
- [Slide Structure](#slide-structure)
- [Image Patterns](#image-patterns)
- [Custom Themes](#custom-themes)
- [Quality Checklist](#quality-checklist)
- [Advanced Features](#advanced-features)
- [Troubleshooting](#troubleshooting)

## Getting Started

### Prerequisites
- **Marp CLI** or **Marp for VS Code** for rendering slides
- Install CLI: `npm install -g @marp-team/marp-cli`
- VS Code: Install the "Marp for VS Code" extension

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
```bash
# HTML (for browser viewing)
marp presentation.md -o presentation.html

# PDF (for sharing)
marp presentation.md -o presentation.pdf

# PowerPoint
marp presentation.md -o presentation.pptx

# PNG images (one per slide)
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

## Custom Themes

For advanced customization beyond the 7 built-in themes, consult `references/theme-css-guide.md`.

### Quick CSS Override
Add a `<style>` block to override specific properties without modifying the theme:
```markdown
---
marp: true
theme: default
---

<style>
section {
  background-color: #1e3a5f;
  color: #ffffff;
}
h2 { color: #ffd700; }
</style>
```

### Key CSS Selectors
| Selector | Target |
|:---|:---|
| `section` | Each slide |
| `section h1, h2, h3` | Headings |
| `section ul, ol` | Lists |
| `section.lead` | Title/lead slides |
| `section::after` | Page numbers |

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

## Troubleshooting

| Problem | Cause | Fix |
|:---|:---|:---|
| No styling in preview | CSS not embedded in file | Use a template from `assets/` — it includes embedded CSS |
| Images not showing | Using standard Markdown syntax | Use Marp syntax: `![bg right:40%](image.png)` |
| Fonts look wrong | Google Fonts not imported | Add `@import url(...)` in the `<style>` block |
| PDF export fails | Chromium not installed | Run `marp --pdf` which auto-downloads Chromium, or install manually |
| Slides not splitting | Missing `---` separators | Add `---` between each slide |
| Page numbers missing | `paginate` not set | Add `paginate: true` to YAML frontmatter |

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

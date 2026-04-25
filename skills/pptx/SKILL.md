---
name: pptx
description: Use when the user asks to create, edit, convert, or preview Microsoft PowerPoint .pptx presentations. Triggers include "markdown to pptx", "slides from outline", "render a deck", "pptx to pdf", "generate slide thumbnails", "edit this .pptx", and related presentation generation or OOXML round-trip tasks.
tier: 2
version: 1.0
license: LicenseRef-Proprietary
---
# pptx skill

**Purpose**: Turn Markdown into presentable `.pptx` decks in one
command, convert decks to PDF or thumbnail grids for review, and give
the agent a safe path to edit existing `.pptx` files. Inline
`pptxgenjs` or `python-pptx` coding regresses on layout, padding, and
typography every time; wrapping the common operations in scripts
removes that variance.

## 1. Red Flags (Anti-Rationalization)

**STOP and READ THIS if you are thinking:**
- "I'll hand-write pptxgenjs calls for this small deck." → **WRONG**. Layout, padding, and bullet indent defaults in `md2pptx.js` encode lessons learned across many decks. Inline code reinvents those and forgets half.
- "I'll pack 7 bullets into a slide, the user wants information density." → **WRONG**. 3–5 bullets max. Dense slides are unreadable. See [references/design-principles.md](references/design-principles.md).
- "Thumbnails are optional, I don't need to review visually." → **WRONG**. Structural validators do not catch white-on-white text, clipped content, or placeholder leftovers. Always render `pptx_thumbnails.py` before calling the deck done.
- "I'll edit the .pptx with python-pptx, it's simpler." → **WRONG** for anything touching the slide master, theme, or relationships. Use `office/unpack.py` + hand-edit + `office/pack.py` for those — see [references/editing-workflow.md](references/editing-workflow.md).

## 2. Capabilities
- Convert Markdown (split by `---`) into a `.pptx` with consistent typography, bullet styling, and theme via `md2pptx.js`. Mermaid diagrams render with a bundled Cyrillic-capable font stack via `scripts/mermaid-config.json` (override with `--mermaid-config PATH`).
- Sketch a slide skeleton from a heading-only Markdown outline (`outline2pptx.js`) — `#` becomes a title slide, `##` becomes a content slide with TODO placeholder. Useful for brainstorming the deck structure before writing prose.
- Convert a `.pptx` to PDF via headless LibreOffice for print, email, or review pipelines.
- Produce a labelled thumbnail grid (JPEG) for rapid visual QA of all slides at once.
- Drop orphan slides / media / charts / themes after manual editing or template substitution (`pptx_clean.py`, BFS over the `.rels` graph; `--dry-run` previews without writing).
- Unpack, patch, and repack raw OOXML for changes not covered by high-level APIs (theme swaps, master edits, custom XML parts).
- Structurally validate a `.pptx` (relationships, content types, required parts) via the shared `office/` module.
- Reject password-protected and legacy `.ppt` (CFB-container) inputs early with a clear remediation message (exit 3) instead of a `BadZipFile` traceback.
- Detect macro-enabled inputs (`.pptm`, with `ppt/vbaProject.bin`) and warn when the chosen output extension would silently drop the macros (`pptm` → `pptx`).
- Render any `.pptx`/`.pptm`/`.pdf` (or peer-skill `.docx`/`.xlsx`) into a single PNG-grid preview via `preview.py` (LibreOffice + Poppler).
- Emit failures as machine-readable JSON to stderr with `--json-errors` (uniform across all four office skills).

## 3. Execution Mode
- **Mode**: `script-first`.
- **Why this mode**: Writing consistent slides is a layout problem with many small details (margin, indent, font size, colour contrast). Scripts let the agent focus on *what* to put on the slides instead of *how* to draw them.

## 4. Script Contract

- **Commands**:
  - `node scripts/md2pptx.js INPUT.md OUTPUT.pptx [--size 16:9|4:3] [--theme theme.json] [--via-marp] [--marp-theme NAME] [--mermaid-config PATH | --no-mermaid-config]`
  - `node scripts/outline2pptx.js INPUT.md OUTPUT.pptx [--size 16:9|4:3] [--theme theme.json]`
  - `python3 scripts/pptx_to_pdf.py INPUT.pptx [OUTPUT.pdf] [--timeout 180]`
  - `python3 scripts/pptx_thumbnails.py INPUT.pptx OUTPUT.jpg [--cols 3] [--dpi 110]`
  - `python3 scripts/pptx_clean.py INPUT.pptx [--output OUT.pptx] [--dry-run]`
  - `python3 scripts/office/unpack.py INPUT.pptx OUTDIR/`
  - `python3 scripts/office/pack.py INDIR/ OUTPUT.pptx`
  - `python3 scripts/office/validate.py INPUT.pptx [--json] [--strict]`
  - `python3 scripts/preview.py INPUT OUTPUT.jpg [--cols 3] [--dpi 110] [--gap 12] [--padding 24] [--label-font-size 14] [--soffice-timeout 240] [--pdftoppm-timeout 60]`
  - All scripts above accept `--json-errors` to emit failures as a single line of JSON on stderr (`{v, error, code, type?, details?}`). The schema version `v` is currently `1`; argparse usage errors are routed through the same envelope (`type:"UsageError"`).
- **Inputs**: positional paths; optional flags per command.
- **Outputs**: single files at the named paths (`.pptx`, `.pdf`, `.jpg`); `office/unpack.py` produces a directory tree; validator prints a report.
- **Failure semantics**: non-zero exit on missing input, soffice errors, pdftoppm errors, or pptxgenjs assembly failures. Error detail to stderr.
- **Idempotency**: `md2pptx.js` produces the same deck for the same input; `pptx_to_pdf.py` and `pptx_thumbnails.py` overwrite their outputs on re-run.
- **Dry-run support**: not applicable.

## 5. Safety Boundaries
- **Allowed scope**: only paths named on the command line.
- **Default exclusions**: do not fetch remote images unless the user explicitly pastes a URL; `md2pptx.js` assumes local paths relative to the input `.md`.
- **Destructive actions**: all three scripts overwrite their outputs without prompting — do not reuse an important file name as output.
- **Optional artifacts**: `office/schemas/` is optional.

## 6. Validation Evidence
- **Local verification**:
  - `cd skills/pptx/scripts && npm install` — installs pptxgenjs and marked into `scripts/node_modules/`.
  - `python3 -m venv .venv && source .venv/bin/activate && pip install -r scripts/requirements.txt` — installs python-pptx, Pillow, lxml, defusedxml.
  - `node scripts/md2pptx.js examples/fixture-slides.md /tmp/deck.pptx` — writes 6 slides.
  - `python3 scripts/office/validate.py /tmp/deck.pptx` — structural `OK`.
  - `python3 scripts/pptx_to_pdf.py /tmp/deck.pptx /tmp/deck.pdf` — produces PDF (requires LibreOffice).
  - `python3 scripts/pptx_thumbnails.py /tmp/deck.pptx /tmp/deck.jpg --cols 3` — produces grid JPEG (requires LibreOffice + Poppler).
- **Expected evidence**: `/tmp/deck.pptx`, `/tmp/deck.pdf`, `/tmp/deck.jpg`; each non-empty; validator reports `OK`.
- **CI signal**: `python3 ../../.claude/skills/skill-creator/scripts/validate_skill.py skills/pptx` — exit 0.

## 7. Instructions

### 7.1 Reach for `md2pptx.js` first

1. Shape the user's content into a Markdown document with slides separated by `---` on their own line.
2. **MUST** keep slides under 5 bullets each and 40 words of body text — otherwise the slide overflows.
3. Use heading level 1 for the title, optional level 2 immediately after for a subtitle, and body content below.
4. `node scripts/md2pptx.js input.md output.pptx`.

### 7.2 Visual QA

1. **MUST** generate a thumbnail grid with `python3 scripts/pptx_thumbnails.py deck.pptx grid.jpg` and review it. Structural validators do not catch layout issues like text running off a slide or white-on-white contrast.
2. Flag placeholders (`XXX`, `Lorem ipsum`, `[insert …]`, "Click to edit") before handing the deck back — search `ppt/slides/` after `office/unpack.py` if needed.

### 7.3 Editing existing `.pptx`

See [references/editing-workflow.md](references/editing-workflow.md).
Rule: use `python-pptx` for text content inside placeholders and
tables; use `office/unpack.py` for anything involving the master,
theme, or relationships.

### 7.4 Converting to PDF

`python3 scripts/pptx_to_pdf.py deck.pptx` — requires LibreOffice.
Useful for shipping to anyone who shouldn't need PowerPoint, and as a
pre-step for thumbnail generation.

### 7.5 Setup

1. **MUST** run the bootstrap script once: `bash scripts/install.sh`. It creates `scripts/.venv/` and `scripts/node_modules/` locally (nothing global), prints a banner for any missing system tool, and is idempotent.
2. **System tools the skill depends on** (checked by `install.sh`, installed manually):
   - **LibreOffice** (`soffice`) — required by `pptx_to_pdf.py`, `pptx_thumbnails.py`, and `md2pptx.js --via-marp`. macOS: `brew install --cask libreoffice`. Debian: `sudo apt install libreoffice --no-install-recommends`. Fedora: `sudo dnf install libreoffice`.
   - **Poppler** (`pdftoppm`) — required by `pptx_thumbnails.py`. macOS: `brew install poppler`. Debian: `sudo apt install poppler-utils`.
   External deps are NOT bundled (per project plan §3.3 "внешние инструменты — не бандлятся") — install them once with your package manager; commands that need them will fail with a clear error message until you do.

## 8. Workflows (Optional)

Generate a deck from Markdown:

```markdown
- [ ] Draft slides in Markdown, separated by `---`
- [ ] `node scripts/md2pptx.js deck.md deck.pptx`
- [ ] `python3 scripts/office/validate.py deck.pptx`
- [ ] `python3 scripts/pptx_thumbnails.py deck.pptx deck.jpg`
- [ ] Review the thumbnail grid, fix layout issues
```

Edit an incoming deck:

```markdown
- [ ] Back up the source: `cp deck.pptx deck.pptx.bak`
- [ ] Text-only edits: use python-pptx
- [ ] Master/theme edits: `office/unpack.py` → patch → `office/pack.py`
- [ ] `python3 scripts/office/validate.py edited.pptx`
- [ ] `python3 scripts/pptx_thumbnails.py edited.pptx grid.jpg` for visual QA
```

Convert to PDF:

```markdown
- [ ] `python3 scripts/pptx_to_pdf.py deck.pptx`
- [ ] Inspect PDF (page-break behaviour, colour fidelity)
```

## 9. Best Practices & Anti-Patterns

| DO THIS | DO NOT DO THIS |
| :--- | :--- |
| Use `md2pptx.js` for Markdown-driven decks. | Hand-write pptxgenjs calls for each deck — layout drifts. |
| 3–5 bullets per slide, 1–2 lines each. | Pack 7+ bullets to "add information density". |
| Run `pptx_thumbnails.py` before declaring done. | Ship without a visual check; structural validators miss layout. |
| Use pptxgenjs defaults unless the user specifies otherwise. | Invent new colour palettes without contrast testing. |
| `office/unpack.py` for theme or master edits. | Edit `.pptx` ZIP in place — relationships and Content Types break. |

### Rationalization Table

| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "The user wants a lot of information per slide." | If information density is the goal, use a document, not a deck. Decks are visual cues for a talker. |
| "python-pptx can do everything." | python-pptx does not touch slide masters or custom parts safely. Use the unpack workflow for those. |
| "Validator says OK, I'm done." | Validator checks structure; a slide can still be visually broken. Check thumbnails too. |
| "I can skip LibreOffice for PDF, just write pptxgenjs and inspect the xml." | Without a rendered PDF or image the deck is untested. Render visually. |

## 10. Quick Reference

| Task | Command |
|---|---|
| Markdown → .pptx (programmatic, built-in) | `node scripts/md2pptx.js deck.md deck.pptx` |
| Markdown → .pptx (professional quality via marp-slide) | `node scripts/md2pptx.js deck.md deck.pptx --via-marp` |
| .pptx → PDF | `python3 scripts/pptx_to_pdf.py deck.pptx [deck.pdf]` |
| Thumbnail grid (JPG) | `python3 scripts/pptx_thumbnails.py deck.pptx grid.jpg` |
| Unpack for XML editing | `python3 scripts/office/unpack.py deck.pptx unpacked/` |
| Repack | `python3 scripts/office/pack.py unpacked/ deck.pptx` |
| Structural validate | `python3 scripts/office/validate.py deck.pptx` |

## 11. Examples (Few-Shot)

Fixture: [examples/fixture-slides.md](examples/fixture-slides.md).

**Input** — user request:
> Make a short end-of-quarter deck from these notes.

**Output** — agent action:
```bash
node scripts/md2pptx.js notes.md q1-review.pptx
python3 scripts/office/validate.py q1-review.pptx
python3 scripts/pptx_thumbnails.py q1-review.pptx q1-review.jpg --cols 3
```
Surface `q1-review.jpg` to the user or to a reviewing sub-agent.

**Input** — user request:
> Convert this deck to PDF.

**Output** — agent action:
```bash
python3 scripts/pptx_to_pdf.py deck.pptx
```
The script writes `deck.pdf` next to the source.

## 12. Resources

- [references/pptxgenjs-basics.md](references/pptxgenjs-basics.md) — API primer: slide sizes, text options, lists, tables, images, common pitfalls.
- [references/editing-workflow.md](references/editing-workflow.md) — python-pptx vs unpack/patch/pack vs LibreOffice dispatch; placeholder cleanup.
- [references/design-principles.md](references/design-principles.md) — typography, colour contrast, bullet density, default palette, exit criteria.
- [scripts/md2pptx.js](scripts/md2pptx.js) — Markdown → .pptx wrapper over pptxgenjs.
- [scripts/pptx_to_pdf.py](scripts/pptx_to_pdf.py) — LibreOffice-based PDF export.
- [scripts/pptx_thumbnails.py](scripts/pptx_thumbnails.py) — thumbnail grid generator (LibreOffice + Poppler + Pillow).
- [scripts/office/](scripts/office/) — OOXML unpack/pack/validate, identical copy from the docx skill.

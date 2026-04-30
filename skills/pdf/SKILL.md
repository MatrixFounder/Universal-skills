---
name: pdf
description: Use when the user asks to create, combine, split, preview, or extract content from PDF files. Triggers include "markdown to pdf", "mermaid in pdf", "merge PDFs", "split a PDF", "extract text from pdf", "fill AcroForm", "preview pdf as image", and similar PDF generation or manipulation tasks.
tier: 2
version: 1.0
license: LicenseRef-Proprietary
---
# pdf skill

**Purpose**: Give the agent a small, deterministic set of CLIs for the
common PDF operations: render Markdown to a well-typeset PDF, merge
PDFs, split them by page range or into individual pages, and (via
references) extract text or fill forms. Picking the right library on
the fly is the single biggest source of PDF bugs; delegating to
scripts that embed those choices removes the variance.

## 1. Red Flags (Anti-Rationalization)

**STOP and READ THIS if you are thinking:**
- "I'll use `pypdf` to extract the text." → **WRONG** for layout-dependent content. `pypdf`'s text extraction is famously unreliable on anything with columns or complex layout; use `pdfplumber`. See [references/library-selection.md](references/library-selection.md).
- "I'll reach for `playwright` for Markdown → PDF because it handles everything." → **WRONG**. Playwright pulls a 200 MB Chromium install. `weasyprint` handles 95% of Markdown/HTML inputs with a fraction of the footprint.
- "I'll fill this XFA form with `pypdf`." → **WRONG**. `pypdf` doesn't fill XFA — only AcroForm. Detect the form type first (see [references/forms.md](references/forms.md)) and fail loudly if it's XFA rather than silently writing an unchanged file.
- "I'll skip checking exit codes from `pdf_merge.py`." → **WRONG**. Missing an input file produces exit 1 and the output is absent — silently assuming success ships a broken deliverable.

## 2. Capabilities
- Render Markdown (+ optional custom CSS) to a typeset PDF via `weasyprint`. Fenced ```mermaid blocks pre-render to PNG via `mmdc`; bundled `scripts/mermaid-config.json` ships an office-friendly Cyrillic-capable font stack (override with `--mermaid-config PATH`, opt out with `--no-mermaid-config`).
- **Render HTML / web archives to PDF** via `html2pdf.py` — same weasyprint pipeline, natively handles `.html`/`.htm`, `.mhtml`/`.mht`, and `.webarchive`. Validated across **Fern (OpenRouter), Mintlify (Anthropic Claude Code, Discord, Berachain), GitBook (Hyperliquid), Confluence (Atlassian wikis), Хабр, vc.ru** and generic blogs — 34/34 fixtures pass in both modes. Bundled stylesheet on by default; `--no-default-css` for fully-styled inputs (BI dashboards, branded reports); `--css EXTRA.css` stacks on top. `--reader-mode` extracts the main article body (Safari Reader View parity). `--timeout 180` SIGALRM watchdog with `$HTML2PDF_TIMEOUT` override. Universal preprocessing handles draw.io/Confluence SVG diagrams, table-based code blocks (Fern/Mintlify shiki), Tailwind/FontAwesome icon strip, ARIA-role tables (GitBook), ad-network removal, and pathological-CSS protection (Хабр content-drop bug, vc.ru CPU-loop bug). Full pipeline + flag semantics + per-platform notes documented in [references/html-conversion.md](references/html-conversion.md).
- Merge multiple PDFs into one preserving bookmarks (`pdf_merge.py`).
- Split a PDF by explicit page ranges, one-per-page, or fixed-size chunks (`pdf_split.py`).
- **Stamp a text or image watermark on every (or selected) page** via `pdf_watermark.py` (drafts, "CONFIDENTIAL", brand stamps). `--position center|top-left|top-right|bottom-left|bottom-right|diagonal`, `--opacity`, `--rotation`, `--pages "1-5,8"`. Builds one overlay per unique page mediabox, so heterogeneous decks (Letter+A4) keep correct proportions.
- **Detect, inspect, and fill AcroForm fields** via `pdf_fill_form.py` — three modes: `--check` (form-type triage with exit codes 0/11/12 = AcroForm/XFA/none), `--extract-fields` (dump field schema as JSON for editing), and fill mode (`INPUT.pdf DATA.json -o OUT.pdf [--flatten]`). XFA forms are detected and refused with a clear message.
- Extract text, tables, and layout via `pdfplumber` (documented; inline usage from the agent is fine).
- Render any `.pdf` (or peer-skill `.docx`/`.xlsx`/`.pptx`) into a single PNG-grid preview via `preview.py` (uses Poppler directly for `.pdf`; LibreOffice + Poppler for OOXML).
- Emit failures as machine-readable JSON to stderr with `--json-errors` (uniform across all four office skills).

## 3. Execution Mode
- **Mode**: `script-first` for the bundled operations, `prompt-first` with library references for extraction and form filling.
- **Why this mode**: The bundled operations (render, merge, split) are stable recipes. Extraction and form filling depend heavily on the specific document and deserve inspection before running — the references guide the inline work.

## 4. Script Contract

- **Commands**:
  - `python3 scripts/md2pdf.py INPUT.md OUTPUT.pdf [--page-size letter|a4|legal] [--css EXTRA.css] [--base-url DIR] [--no-mermaid] [--strict-mermaid] [--mermaid-config PATH | --no-mermaid-config]`
  - `python3 scripts/html2pdf.py INPUT OUTPUT.pdf [--page-size letter|a4|legal] [--css EXTRA.css] [--base-url DIR] [--no-default-css] [--reader-mode] [--timeout SECONDS]`  — INPUT may be `.html`/`.htm`, `.mhtml`/`.mht`, or `.webarchive`; sub-resources in archives are extracted to a temp dir automatically. `--reader-mode` extracts the main article content (Confluence-priority candidate list with body-ratio guard for `<main>`; longest-match per selector handles archive pages with multiple `.entry` divs and Disqus comment threads), stripping navigation, ads, and sidebars — ideal for browser-saved news/blog/docs pages. `--timeout` (default 180s, `$HTML2PDF_TIMEOUT` env, 0 disables) caps weasyprint render via `signal.SIGALRM` for pathological inputs. Exit 1 with `RenderTimeout` envelope on watchdog fire.
  - `python3 scripts/pdf_merge.py OUTPUT.pdf INPUT1.pdf INPUT2.pdf [INPUT3.pdf ...]`
  - `python3 scripts/pdf_split.py INPUT.pdf --ranges "1-5:part1.pdf,6-10:part2.pdf"`
  - `python3 scripts/pdf_split.py INPUT.pdf --each-page OUTDIR/`
  - `python3 scripts/pdf_split.py INPUT.pdf --every N OUTDIR/`
  - `python3 scripts/pdf_watermark.py INPUT.pdf OUTPUT.pdf (--text "DRAFT" | --image STAMP.png) [--opacity 0.3] [--position center|top-left|top-right|bottom-left|bottom-right|diagonal] [--rotation 45] [--font-size 60] [--color "#888"] [--scale 0.5] [--pages "all"|"1-5,8,12-end"]`
  - `python3 scripts/pdf_fill_form.py --check INPUT.pdf` — exit 0/11/12 = AcroForm/XFA/none. (Custom codes start at 10 to leave 0–9 for argparse / shell convention.)
  - `python3 scripts/pdf_fill_form.py --extract-fields INPUT.pdf -o fields.json`
  - `python3 scripts/pdf_fill_form.py INPUT.pdf DATA.json -o OUTPUT.pdf [--flatten]`
  - `python3 scripts/preview.py INPUT OUTPUT.jpg [--cols 3] [--dpi 110] [--gap 12] [--padding 24] [--label-font-size 14] [--soffice-timeout 240] [--pdftoppm-timeout 60]`
  - All scripts above accept `--json-errors` to emit failures as a single line of JSON on stderr (`{v, error, code, type?, details?}`). The schema version `v` is currently `1`; argparse usage errors are routed through the same envelope (`type:"UsageError"`).
- **Inputs**: positional paths; optional flags per command.
- **Outputs**: single PDF files (`md2pdf`, `pdf_merge`) or multiple PDFs under a directory (`pdf_split`). All stdout goes to the output path list.
- **Failure semantics**: non-zero exit on missing inputs, invalid range specs, or library errors. Error detail to stderr.
- **Idempotency**: all three scripts overwrite their outputs on re-run.
- **Dry-run support**: not applicable.

## 5. Safety Boundaries
- **Allowed scope**: only paths named on the command line.
- **Default exclusions**: do not fetch remote resources unless the user explicitly provides URLs; `md2pdf.py --base-url` defaults to the input's directory.
- **Destructive actions**: all three scripts overwrite their outputs without prompting.
- **Optional artifacts**: custom CSS via `md2pdf.py --css` is optional; defaults produce a reasonable layout.

## 6. Validation Evidence
- **Local verification**:
  - `python3 -m venv .venv && source .venv/bin/activate && pip install -r scripts/requirements.txt` — installs pypdf, pdfplumber, weasyprint, markdown2, reportlab.
  - `bash scripts/tests/test_e2e.sh` — runs the end-to-end smoke suite (md2pdf, merge, split, fill-form, mermaid). Includes the html2pdf regression battery: ~37 unit tests for `html2pdf_lib/` helpers + data-driven fixture battery (6 synthetic micro-fixtures + 6 hand-stripped real-platform slices + N tmp/ originals when present on disk; per-fixture page-count / size / required+forbidden-needle assertions, see [tests/battery_signatures.json](scripts/tests/battery_signatures.json)).
  - **Adding a new platform fixture** (e.g. you found a Notion/Stripe page that breaks): drop the `.webarchive`/`.html`/`.mhtml` file into `tmp/`, run `python3 scripts/tests/capture_signatures.py` (auto-captures page count + needles + size band; only ADDs new fixtures unless `--refresh` is passed), hand-add chrome strings to `forbidden_needles` in [battery_signatures.json](scripts/tests/battery_signatures.json), commit the JSON delta. Total ~5 min per new site. Detailed in [references/html-conversion.md](references/html-conversion.md) §Regression coverage.
  - `python3 scripts/md2pdf.py examples/fixture.md /tmp/invoice.pdf --page-size letter` — produces a non-empty PDF.
  - `python3 -c "from pypdf import PdfReader; r=PdfReader('/tmp/invoice.pdf'); print(len(r.pages))"` — returns at least 1.
  - `python3 scripts/pdf_merge.py /tmp/merged.pdf /tmp/invoice.pdf /tmp/invoice.pdf && python3 -c "from pypdf import PdfReader; print(len(PdfReader('/tmp/merged.pdf').pages))"` — 2× the page count.
  - `python3 scripts/pdf_split.py /tmp/invoice.pdf --each-page /tmp/pages/` — produces `/tmp/pages/invoice-001.pdf`.
- **Expected evidence**: `/tmp/invoice.pdf`, `/tmp/merged.pdf`, `/tmp/pages/invoice-001.pdf`.
- **CI signal**: `python3 ../../.claude/skills/skill-creator/scripts/validate_skill.py skills/pdf` — exit 0.

## 7. Instructions

### 7.1 Pick the library, not the script first

Extraction and form filling are not in the bundled scripts deliberately.
1. Check [references/library-selection.md](references/library-selection.md) for which library matches the task.
2. For extraction: write inline `pdfplumber` code in your response.
3. For form filling: follow [references/forms.md](references/forms.md) — detect AcroForm vs XFA first.

### 7.2 Creating PDFs from Markdown

1. `python3 scripts/md2pdf.py input.md output.pdf` covers the common case.
2. Pass `--css custom.css` when the user provides brand styling.
3. For images referenced with relative paths, either put them next to the Markdown file or pass `--base-url /absolute/image/root`.
4. For HTML-heavy inputs (embedded `<style>`, flexbox, columns), weasyprint handles those in the script — no extra work needed.

### 7.3 Merging PDFs

1. Order matters: `python3 scripts/pdf_merge.py out.pdf file1.pdf file2.pdf file3.pdf` appends in that order.
2. Bookmarks from each input are preserved and nested under a parent named after the source's stem.

### 7.4 Splitting PDFs

Three modes, exclusive:
- `--ranges "1-3:intro.pdf,4-8:body.pdf,9-12:appendix.pdf"`
- `--each-page OUTDIR/` — one PDF per input page, zero-padded filenames.
- `--every N OUTDIR/` — chunks of N pages each.

Page numbers are 1-indexed and inclusive. Invalid ranges exit 1.

### 7.5 Setup

1. **MUST** run `bash scripts/install.sh` once. It creates `scripts/.venv/` locally, installs `requirements.txt`, probes whether weasyprint can find its native libraries, and prints install hints if not. Idempotent.
2. **External system libraries** (checked by `install.sh`, installed manually per project plan §3.3 "внешние инструменты — не бандлятся"):
   - **pango, cairo, gdk-pixbuf** — weasyprint native runtime; required by `md2pdf.py`. macOS: `brew install pango gdk-pixbuf libffi`. Debian: `sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libcairo2 libgdk-pixbuf2.0-0`. See [references/weasyprint-setup.md](references/weasyprint-setup.md) for fuller notes.
   Commands that need them fail with a clear error until installed.

## 8. Workflows (Optional)

Markdown-driven PDF:

```markdown
- [ ] Draft the Markdown content
- [ ] `python3 scripts/md2pdf.py doc.md doc.pdf`
- [ ] Open the PDF, check layout (orphans/widows, table page breaks)
- [ ] Iterate on CSS if needed (`--css brand.css`)
```

Merge + split for distribution:

```markdown
- [ ] `python3 scripts/pdf_merge.py combined.pdf intro.pdf body.pdf appendix.pdf`
- [ ] `python3 scripts/pdf_split.py combined.pdf --each-page out/`  (if per-page delivery is needed)
- [ ] Verify page count with pypdf or Preview
```

Extract text (inline, no bundled script):

```markdown
- [ ] Read references/library-selection.md, pick pdfplumber
- [ ] Inline: open the file, call page.extract_text(layout=True)
- [ ] For tables, page.extract_tables() with appropriate snap_tolerance
```

## 9. Best Practices & Anti-Patterns

| DO THIS | DO NOT DO THIS |
| :--- | :--- |
| Use `weasyprint` for Markdown/HTML → PDF. | Reach for `playwright` unless you actually need JS/modern CSS. |
| Use `pdfplumber` for text/table extraction. | Trust `pypdf.extract_text()` on column layouts — output is often garbled. |
| Detect AcroForm vs XFA before filling. | Try to fill XFA with `pypdf` and ship an unchanged file. |
| Pass `--base-url` so relative images resolve. | Assume weasyprint reads relative paths the same way your shell does. |
| Check exit codes of the bundled scripts. | Assume success because no exception was raised. |

### Rationalization Table

| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "All PDFs can be read with the same library." | Reading vs creation vs editing vs rendering are four different problem spaces; pick per task. |
| "The Markdown renderer doesn't matter, they're all similar." | `weasyprint` supports `@page` and page-break-inside; `markdown-pdf` and `mdpdf` don't. |
| "My script worked on one PDF, it'll work on all of them." | PDFs are wildly heterogeneous — scanned, image-only, XFA, flattened. Always test on the actual file. |

## 10. Quick Reference

| Task | Command |
|---|---|
| Markdown → PDF | `python3 scripts/md2pdf.py doc.md doc.pdf --page-size letter` |
| Markdown → PDF with custom mermaid theme | `python3 scripts/md2pdf.py doc.md doc.pdf --mermaid-config theme.json` |
| HTML → PDF | `python3 scripts/html2pdf.py report.html report.pdf` |
| HTML → PDF (skip bundled CSS, only embedded styles) | `python3 scripts/html2pdf.py dashboard.html out.pdf --no-default-css` |
| Web page / archive → PDF (reader mode, strips nav/ads) | `python3 scripts/html2pdf.py page.webarchive article.pdf --reader-mode` |
| HTML → PDF with custom render deadline | `python3 scripts/html2pdf.py page.html out.pdf --timeout 300` (or `HTML2PDF_TIMEOUT=300 python3 …`) |
| HTML → PDF, watchdog disabled (large book webarchive) | `HTML2PDF_TIMEOUT=0 python3 scripts/html2pdf.py book.webarchive book.pdf` |
| Merge PDFs | `python3 scripts/pdf_merge.py out.pdf a.pdf b.pdf c.pdf` |
| Split by ranges | `python3 scripts/pdf_split.py in.pdf --ranges "1-5:intro.pdf,6-10:body.pdf"` |
| Split one-per-page | `python3 scripts/pdf_split.py in.pdf --each-page pages/` |
| Split in chunks of N | `python3 scripts/pdf_split.py in.pdf --every N out/` |
| Text watermark on every page | `python3 scripts/pdf_watermark.py in.pdf out.pdf --text "DRAFT"` |
| Image watermark, bottom-right corner | `python3 scripts/pdf_watermark.py in.pdf out.pdf --image stamp.png --position bottom-right --scale 0.2` |
| Watermark only specific pages | `python3 scripts/pdf_watermark.py in.pdf out.pdf --text CONFIDENTIAL --pages "1-5,8"` |
| Inspect AcroForm fields | `python3 scripts/pdf_fill_form.py --check form.pdf` |
| Extract field schema as JSON | `python3 scripts/pdf_fill_form.py --extract-fields form.pdf -o fields.json` |
| Fill AcroForm from JSON | `python3 scripts/pdf_fill_form.py form.pdf data.json -o filled.pdf [--flatten]` |
| Preview as PNG-grid | `python3 scripts/preview.py file.pdf preview.jpg [--cols 3] [--dpi 110]` |
| Machine-readable failures | append `--json-errors` to any of the above |

## 11. Examples (Few-Shot)

Fixture: [examples/fixture.md](examples/fixture.md).

**Input** — user request:
> Turn this invoice Markdown into a letter-sized PDF.

**Output** — agent action:
```bash
python3 scripts/md2pdf.py invoice.md invoice.pdf --page-size letter
```

**Input** — user request:
> Join these three quarterly reports into one annual PDF.

**Output** — agent action:
```bash
python3 scripts/pdf_merge.py annual.pdf q1.pdf q2.pdf q3.pdf q4.pdf
```

**Input** — user request:
> Split the 120-page handbook into chapters of roughly 10 pages each.

**Output** — agent action:
```bash
python3 scripts/pdf_split.py handbook.pdf --every 10 chapters/
```

**Input** — user request:
> Convert this Confluence-export HTML report to PDF.

**Output** — agent action:
```bash
python3 scripts/html2pdf.py q1-report.html q1-report.pdf --base-url ./q1-report_files/
```

**Input** — user request:
> Stamp every page of this draft contract with "DRAFT" diagonally.

**Output** — agent action:
```bash
python3 scripts/pdf_watermark.py contract.pdf contract-draft.pdf --text "DRAFT"
```

## 12. Resources

- [references/library-selection.md](references/library-selection.md) — which PDF library for which task, installation shortcuts.
- [references/forms.md](references/forms.md) — AcroForm vs XFA, filling with pypdf, flattening, visual overlay fallback.
- [references/weasyprint-setup.md](references/weasyprint-setup.md) — install platform notes, `@page` recipes, font embedding, page breaks.
- [references/html-conversion.md](references/html-conversion.md) — `html2pdf.py` deep dive: 10-step preprocessing pipeline, `_NORMALIZE_CSS` rules, reader-mode candidate list with body-ratio guard, render-time hardening (offline URL fetcher + SIGALRM watchdog), per-platform notes (Fern / Mintlify / GitBook / Confluence / Хабр / vc.ru), honest-scope limitations.
- [scripts/md2pdf.py](scripts/md2pdf.py) — Markdown → PDF via weasyprint + markdown2; mermaid blocks pre-rendered to PNG via `mmdc`.
- [scripts/html2pdf.py](scripts/html2pdf.py) — HTML → PDF via the same weasyprint pipeline; reuses md2pdf's default stylesheet (opt-out via `--no-default-css`).
- [scripts/pdf_merge.py](scripts/pdf_merge.py) — bookmark-preserving merger via pypdf.
- [scripts/pdf_split.py](scripts/pdf_split.py) — range, per-page, or fixed-chunk splitter.
- [scripts/pdf_watermark.py](scripts/pdf_watermark.py) — text/image watermark overlay via reportlab + pypdf; per-mediabox overlay caching for heterogeneous decks; cross-7 same-path guard.
- [scripts/pdf_fill_form.py](scripts/pdf_fill_form.py) — AcroForm inspect/extract/fill/flatten via pypdf; XFA forms detected and refused.
- [scripts/preview.py](scripts/preview.py) — universal `INPUT → PNG-grid` renderer for `.pdf` (via Poppler) and `.docx`/`.xlsx`/`.pptx` (via LibreOffice + Poppler). Byte-identical across all four office skills.
- [scripts/mermaid-config.json](scripts/mermaid-config.json) — bundled office-friendly mermaid config (Cyrillic-capable font stack, auto-applied unless overridden via `--mermaid-config`).
- [scripts/_errors.py](scripts/_errors.py) — `--json-errors` envelope helper (schema `v=1`).

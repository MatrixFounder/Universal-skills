# pptx → Markdown (`pptx2md.py`)

Convert a `.pptx`/`.pptm` deck into structured, LLM-/RAG-friendly Markdown. The
read-back counterpart to `md2pptx.js`, and the pptx analogue of `xlsx2md`.

```bash
python3 scripts/pptx2md.py INPUT.pptx [OUTPUT.md|-] [flags]
```

## What you get

One section per slide, in presentation order:

- `## Slide N` per slide.
- The slide **title** → `### …` (emitted first, regardless of its z-order).
- Body text frames → nested `-` bullets (paragraph indent level → 2 spaces/level).
- Tables → **GFM pipe tables** (cells escaped; `|`→`\|`, newlines→`<br>`).
- Images → extracted to a sidecar `<output-stem>.media/` folder and linked as
  `![alt](…/slideN-imgM.ext)`. Identical images are written once (sha1-deduped) and
  all references point at the canonical first-occurrence file.
- Speaker notes (when present) → a `> **Notes:**` block (suppress with `--no-notes`).
- Charts / EMF·WMF·SVG / video → a `[kind]` placeholder marker + a warning (never a
  hard failure). **SmartArt diagrams are silently skipped** (see Limitations).

## When to reach for `--ocr`

OCR is **opt-in** and **off by default** — the common case (a text-rich deck) needs
no OCR and no engine. Add `--ocr` when text you care about is **baked into images**
(screenshots, scanned slides, diagram labels):

```bash
python3 scripts/pptx2md.py deck.pptx out.md --ocr [--ocr-lang eng+rus] [--jobs 4]
```

`--ocr` runs the system **`tesseract`** engine (the same engine the `pdf` skill's OCR
is built on; default languages `eng+rus`) **directly on each extracted image**, and
inserts the recovered text under that image as a `<!-- ocr -->`-tagged blockquote so
it is distinguishable from authored text. It does **not** route through `ocrmypdf`/
`ghostscript` (that is PDF-page-oriented and would lose the per-image placement).

### Decision tree

```
Is the slide content extractable text (you saw bullets/titles in the no-OCR run)?
  yes → done, no --ocr needed.
Is the text baked into an image / screenshot?
  yes → re-run with --ocr (needs tesseract + the eng/rus packs installed).
Is the deck a marp/Keynote export whose slides are full-slide BACKGROUND images?
  → see Limitations: background fills are not surfaced as pictures in v1.
```

## Setup (OCR is soft-optional)

The base converter needs only `python-pptx` + `Pillow` (in `scripts/requirements.txt`,
installed by `bash scripts/install.sh`). `--ocr` additionally needs the **system**
`tesseract` binary + the `eng`/`rus` language data — **detected, never installed by
us**:

- macOS: `brew install tesseract tesseract-lang`
- Debian/Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus`
- Fedora: `sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-rus`

A missing engine or language pack fails **loud** with a remediation hint (exit 1),
never silently.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | OCR engine/lang missing (`--ocr`), bad input, or internal error (redacted) |
| 2 | usage error (argparse) |
| 3 | encrypted **or** legacy `.ppt` input (decrypt via `office_passwd.py` / re-save as `.pptx`) |
| 6 | self-overwrite refused (OUTPUT, or a media file, resolves onto INPUT) |

Append `--json-errors` for a single-line JSON envelope on stderr.

## Limitations (honest scope, v1)

- **Rich-text styling** (bold/italic/colour) is flattened to plain text.
- **Charts** → `[chart]` placeholder, not reconstructed.
- **SmartArt** is **not surfaced** in v1 — python-pptx exposes no reliable SmartArt
  classifier, so a SmartArt diagram is **silently skipped** (no marker, no warning;
  its text is lost). Use `pptx_thumbnails.py` for a visual if a deck leans on SmartArt.
- **Merged table cells** → anchor value + blanks (no rowspan/colspan reconstruction).
- **EMF/WMF/SVG/video** → placeholder markers, not rasterised.
- **Background-image / marp decks**: content carried as a slide-*background* fill is
  **not** surfaced by python-pptx as a `PICTURE` shape, so such a slide yields a
  header with an empty body even under `--ocr`. Use the deck's source, or
  `pptx_thumbnails.py` for a visual, in that case.
- **OCR** is best-effort flat text per image — no in-image layout/table reconstruction.
- Inline HTML inside a cell value is passed through (Markdown renders it); this matches
  the single-tenant local-CLI trust model and `xlsx2md` behaviour.

## Examples

```bash
# Text-rich deck → Markdown + sidecar images
python3 scripts/pptx2md.py quarter-review.pptx quarter-review.md

# Image-only / scanned deck → recover text with OCR
python3 scripts/pptx2md.py scanned.pptx scanned.md --ocr --jobs 4

# To stdout (media still written beside CWD, with a stderr note)
python3 scripts/pptx2md.py deck.pptx - --no-notes
```

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
- Charts / SVG / video → a `[kind]` placeholder marker + a warning (never a hard
  failure). WMF/EMF vector images are rendered to inline PNG via LibreOffice (see
  Limitations). **SmartArt diagrams are silently skipped** (see Limitations).

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
  → handled: slide-background + shape-fill + picture-placeholder images are all
    extracted; re-run with --ocr to recover their text.
```

### Reducing OCR noise — `--ocr-denoise`

`tesseract` will emit garbage for decorative images that contain no real text —
logos, icon glyphs, blank banners, brand wordmarks. By default every such block is
kept (the recovered text is verified-good for *real* images; the noise is purely
additive). Add **`--ocr-denoise`** (opt-in, off by default — never changes the
non-denoise output) to filter it:

```bash
python3 scripts/pptx2md.py deck.pptx out.md --ocr --ocr-denoise [--jobs 4]
```

It applies three subtractive-of-noise-only filters:

- **size-gate** (`--ocr-min-px`, default 48) — skips OCR on an image whose smaller
  side is below the threshold (decorative icons/glyphs are never body text).
- **confidence-gate** (`--ocr-min-confidence`, default 50) — runs tesseract in `tsv`
  mode, keeps only words at/above the confidence threshold, and **drops an image
  whose OCR has fewer than two confident words** (a text-free/low-contrast image
  yields ≤1; a real screenshot yields dozens). It also strips low-confidence garble
  *inside* the blocks it keeps, so kept screenshots come out cleaner.
- **dedup** — an OCR block whose text was already emitted earlier (a logo OCR'd
  identically on many slides) is shown once; the image link still renders on each
  slide.

Tuning: raise `--ocr-min-confidence` to be stricter (more dropped), lower it to keep
more low-contrast text. The gate keys on the *count* of confident words, not their
average, so it does **not** drop a dense real screenshot whose UI chrome has many
low-confidence glyphs. It is best-effort (tesseract's per-word confidence is
heuristic) — for a verbatim dump of everything tesseract sees, omit `--ocr-denoise`.

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
- **SVG / video** (and any EMF Pillow can't identify at all) → `[image]`/`[media]`
  placeholder markers (no file written). WMF — and the EMF variants Pillow *does*
  identify — are handled by the vector bullet below.
- **WMF / EMF** (vector) → **rendered to an inline `.png`** via **LibreOffice**
  (`soffice`) and linked, so the diagram **displays inline** in any Markdown viewer
  (most won't render raw `.wmf`/`.emf`). The render happens at extraction time
  (regardless of `--ocr`); under `--ocr` the same PNG is OCR'd, so text inside a
  WMF/EMF diagram **is** recovered with no second LibreOffice call. The render is
  **soft-optional and fail-closed**: if `soffice` is absent (or the render fails) the
  original `.wmf`/`.emf` bytes are written instead and, under `--ocr`, that one image's
  OCR is skipped with `warning: OCR skipped a non-rasterisable image: …` — the run
  always continues. Each render is profile-isolated, so it parallelises safely; vectors
  are pre-rendered up front across `--jobs` workers (default `--jobs 1` = serial, ~2–3 s
  of LibreOffice startup *per unique vector* — raise `--jobs` on vector-heavy decks).
  Identical vectors (same sha1) are rendered once. *Note:* the inline PNG **bytes** are
  not byte-reproducible across runs (LibreOffice stamps render metadata), but the
  emitted `.md` and the media **filenames** are stable — don't byte-diff `media/` between
  runs, diff the `.md`.
- **Background-image / marp decks are handled**: slide-*background* images
  (`p:cSld/p:bg`), shape-*fill* images, and *picture-placeholders* are all extracted
  to the sidecar `media/` folder and linked (as `background` alt); run `--ocr` to
  recover the text they carry. *Only* a background inherited from the slide
  **layout/master** (not set on the slide itself) is not collected — rare; deferred.
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

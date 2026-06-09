# OCR scanned PDFs — `pdf_ocr.py`

`pdf_ocr.py` turns an **image-only (scanned) PDF** into a **searchable PDF**:
the original page raster is kept verbatim and an invisible OCR text layer is
overlaid so the text becomes selectable and extractable. It is a thin wrapper
around [`ocrmypdf`](https://ocrmypdf.readthedocs.io/) and defaults to OCR
languages **English + Russian** (`eng+rus`).

It is **not** a Markdown converter. After OCR, run `pdf_extract.py` on the
output (or the Read tool) and compose Markdown yourself — see
[pdf-to-markdown.md](pdf-to-markdown.md).

## When to use it

`pdf_extract.py` exits **`10 DocumentScanned`** on an image-only PDF. That is
the trigger:

```bash
pdf_extract.py scan.pdf            # exit 10 DocumentScanned  (no text layer)
pdf_ocr.py     scan.pdf scan.ocr.pdf     # → searchable PDF (eng+rus)
pdf_extract.py scan.ocr.pdf        # exit 0, doc_scanned=false, text present
```

## Install (soft-optional)

The OCR engine is **not** part of the base pdf skill — it is installed only on
request, and the system tools are your install choice:

```bash
bash skills/pdf/scripts/install.sh --with-ocr
```

That installs `ocrmypdf` into the skill venv and **probes** (does not install)
the required system tools, printing per-OS hints if any are missing:

| OS | Install the system tools |
|----|--------------------------|
| macOS | `brew install tesseract tesseract-lang ghostscript` |
| Debian/Ubuntu | `sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus ghostscript` |
| Fedora | `sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-rus ghostscript` |

If the engine or a language pack is missing, `pdf_ocr.py` fails **loud** (never
silent): `OcrEngineUnavailable` or `LanguagePackMissing` in the `--json-errors`
envelope, with the remediation in the message.

### Troubleshooting: `tesseract` "image file not found" / `SubprocessOutputError`

If `ocrmypdf` aborts with leptonica errors like
`Error in fopenReadStream: ... image file not found: <TMPDIR>/ocrmypdf.io.*/…png`
(surfaced by `pdf_ocr.py` as an `InternalError` / `OutputWriteFailed` envelope),
the engine is fine but the **spawned `tesseract` process cannot read ocrmypdf's
intermediate files** under your `TMPDIR`. This happens in **sandboxed / SIP- or
seatbelt-restricted environments** where a third-party `tesseract` binary is
denied access to the system temp dir. Point `TMPDIR` at a directory the
`tesseract` binary is permitted to read (e.g. a project-local one):

```bash
TMPDIR="$PWD/.ocrtmp" mkdir -p "$PWD/.ocrtmp" && \
TMPDIR="$PWD/.ocrtmp" python3 scripts/pdf_ocr.py scan.pdf out.pdf
```

On an unrestricted shell the default `TMPDIR` works and no override is needed.

### Troubleshooting: `--force-ocr` + a very large embedded image

`--force-ocr` rasterizes **every** page; a PDF with a very large embedded image
(e.g. a full-page figure) can exceed Pillow's decompression-bomb safety limit,
surfaced as an `InputUnreadable` envelope ("an embedded image is too large to
process safely"). For a **mostly-digital** PDF with only a few image/figure
pages, prefer the default `--skip-text` (it OCRs only the image-only pages and
keeps the crisp vector text on the rest), or OCR just the figure pages — rather
than `--force-ocr` over the whole document.

## Usage

```text
pdf_ocr.py INPUT.pdf OUTPUT.pdf
           [--lang LANGS]                          # default "eng+rus"
           [--skip-text | --redo-ocr | --force-ocr]  # default --skip-text
           [--sidecar PATH.txt] [--jobs N] [--json-errors]
```

- `--lang` — tesseract `+`-joined language list; every pack must be installed
  (validated up front). Examples: `--lang eng`, `--lang eng+rus+deu`.
- `--skip-text` (default) — OCR only pages with no text; existing vector text is
  left untouched and a mixed PDF never errors.
- `--redo-ocr` — strip an existing OCR text layer and OCR again.
- `--force-ocr` — rasterise and OCR every page, even born-digital pages (lossy).
- `--sidecar PATH.txt` — also write the recognised plain text to a file.
- `--jobs N` — OCR worker processes (default: ocrmypdf auto = CPU count).
- `--password PW` — decrypt an encrypted input before OCR (the output is
  unencrypted). NOTE: argv is visible in `ps` — intended for local-CLI use.
- `--deskew` — straighten skewed scans before OCR (no extra tool).
- `--rotate-pages` — auto-orient pages via OSD; needs the tesseract `osd` data
  (`brew install tesseract-lang` / `apt install tesseract-ocr-osd`).
- `--clean` — despeckle scans before OCR; needs the `unpaper` binary
  (`brew install unpaper` / `apt install unpaper`). Missing `osd`/`unpaper` fails
  loud, never silent.

### Improving OCR quality on noisy or skewed scans

If the recognised text is garbled, the fix is almost always to **clean the source
image before OCR**, not to filter the result. `pdf_ocr` writes the OCR text into an
**invisible searchable layer** behind the original page image, so OCR noise mostly
shows up as bad `Ctrl+F` hits or messy copy-paste — and a cleaner input image fixes
it at the source. Reach for these three (in roughly this order of impact) when a scan
OCRs poorly:

- **`--clean`** — despeckle: removes scanner speckles, dust, and stray lines that
  tesseract otherwise reads as junk characters. The single biggest quality lever for
  a noisy scan. (Needs `unpaper`.)
- **`--deskew`** — straighten: a few degrees of tilt badly degrades line detection.
- **`--rotate-pages`** — auto-orient sideways / upside-down pages (a wrong-orientation
  page OCRs to near-total garbage). (Needs the tesseract `osd` data.)

For a poor scan, combine all three. They affect only the OCR pipeline — the **visible**
page image is unchanged (`--clean` despeckles the copy fed to tesseract, not the page
you see). There is intentionally **no** confidence/word-level filter on the output text
layer: ocrmypdf owns that layer, and a few low-confidence words in an invisible layer
are not worth post-processing the PDF for. Fixing the input is both simpler and better.

### Examples

```bash
# Default eng+rus OCR
pdf_ocr.py contract-scan.pdf contract-ocr.pdf

# Russian only, with a plain-text sidecar
pdf_ocr.py письмо.pdf письмо.ocr.pdf --lang rus --sidecar письмо.txt

# Re-OCR a badly-OCR'd file; deskew + auto-rotate
pdf_ocr.py old.pdf new.pdf --redo-ocr --deskew --rotate-pages

# Noisy / skewed scan: clean the source image before OCR (best quality lever)
pdf_ocr.py noisy-scan.pdf clean-ocr.pdf --clean --deskew --rotate-pages

# Encrypted scan
pdf_ocr.py secret-scan.pdf out.pdf --password s3cr3t
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | success — searchable PDF written |
| 1 | failure — `--json-errors` envelope `type` discriminates: `OcrEngineUnavailable`, `LanguagePackMissing`, `EncryptedInput`, `InputUnreadable`, `PriorOcrFound`, `OutputWriteFailed`, `InternalError`, `InputNotFound` |
| 2 | usage error (argparse; incl. the mode mutex) |
| 6 | `SelfOverwriteRefused` — `OUTPUT` (or `--sidecar`) resolves to `INPUT` |

`10` is **not** used here — it stays exclusive to `pdf_extract.py`
(`DocumentScanned`).

## Trust model & honest scope

The pdf skill has no dedicated `references/security.md`; the OCR trust model is
stated here:

- **Single-tenant, operator-supplied input; non-multi-tenant output directory.**
- `pdf_ocr.py` invokes `ocrmypdf` via its **Python API** (no shell string
  interpolation); requested languages are validated against the installed set
  before use.
- The output is written atomically (a `.partial` sibling is `os.replace`d into
  place); a failure leaves no partial or stale output.
- **No global timeout / decompression-bomb hardening** beyond what ocrmypdf and
  ghostscript do themselves — a pathological PDF can run long or use a lot of
  memory.
- The OCR engine is **not bundled**: tesseract / ghostscript / language packs
  are detected, never installed by us.
- OCR is **not bit-exact** — recognised text approximates the scan; verify
  important values.

## Composition with the other pdf tools

- **Read loop:** `pdf_extract.py` → exit 10 → `pdf_ocr.py` → `pdf_extract.py`
  → compose Markdown ([pdf-to-markdown.md](pdf-to-markdown.md)).
- `pdf_ocr.py` imports `_errors.py` read-only; it shares no replicated helper
  and triggers no cross-skill replication.

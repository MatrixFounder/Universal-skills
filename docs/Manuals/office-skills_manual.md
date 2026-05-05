# Office Skills Manual

Practical reference for the four office-document skills:
[`docx`](../../skills/docx/), [`xlsx`](../../skills/xlsx/),
[`pptx`](../../skills/pptx/), [`pdf`](../../skills/pdf/).

This manual is for **users** of the skills. For the contributor /
maintenance protocol (especially the strict docx → xlsx/pptx
replication rule), see [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## 1. What each skill does

| Skill | Primary use | Key scripts |
|---|---|---|
| **docx** | Create, edit, convert, validate `.docx` (Word) | `md2docx.js`, `docx2md.js`, `docx_fill_template.py`, `docx_accept_changes.py`, `office/validate.py` |
| **xlsx** | CSV/JSON → styled `.xlsx`, recalc formulas, scan errors, **add charts** | `csv2xlsx.py`, `xlsx_recalc.py`, `xlsx_validate.py`, `xlsx_add_chart.py` |
| **pptx** | Markdown → `.pptx`, thumbnails, PDF, **clean orphans**, **outline skeleton** | `md2pptx.js` (incl. `--via-marp`), `outline2pptx.js`, `pptx_to_pdf.py`, `pptx_thumbnails.py`, `pptx_clean.py` |
| **pdf** | Markdown → PDF (with mermaid), merge, split, **fill AcroForms** | `md2pdf.py`, `pdf_merge.py`, `pdf_split.py`, `pdf_fill_form.py` |

The four office skills are governed by a per-skill **Proprietary**
licence (effective 2026-04-25, see [LICENSE](../../skills/docx/LICENSE)
and siblings). Runtime deps and external-tool attributions remain
under their original licences in
[THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).

### Cross-cutting safeguards

Every reader script in `docx`/`xlsx`/`pptx` calls
`office._encryption.assert_not_encrypted(path)` before opening its
input. The check sniffs the first 8 bytes for the Compound File
Binary (CFB) signature `D0CF11E0A1B11AE1`, which catches both:

- **password-protected OOXML** (Office 2010+ encryption wraps the
  package in CFB), and
- **legacy `.doc` / `.xls` / `.ppt`** (Office 97-2003 native format
  is also CFB).

Either case exits with code **3** and a message that names both
possibilities so users hitting the legacy case aren't sent looking
for a non-existent password. Remediation is upstream: remove the
password (`msoffcrypto-tool` or office app) OR convert with
`soffice --headless --convert-to docx INPUT`.

---

## 2. One-time setup per skill

Each skill has its own bootstrap script that creates a local
`scripts/.venv/` and (for skills that use Node) `scripts/node_modules/`,
then probes for required system tools and prints install hints if any
are missing.

```bash
bash skills/docx/scripts/install.sh    # docx
bash skills/xlsx/scripts/install.sh    # xlsx
bash skills/pptx/scripts/install.sh    # pptx
bash skills/pdf/scripts/install.sh     # pdf
```

The scripts are idempotent — re-running on a fully-installed system
just re-verifies and prints the version banner.

### System tools (NOT bundled — install per platform)

Per project plan §3.3 "внешние инструменты — не бандлятся":

| Tool | Required by | macOS | Debian/Ubuntu | Fedora |
|---|---|---|---|---|
| **LibreOffice** (`soffice`) | `docx_accept_changes`, `xlsx_recalc`, `pptx_to_pdf`, `pptx_thumbnails`, `md2pptx --via-marp` | `brew install --cask libreoffice` | `sudo apt install libreoffice --no-install-recommends` | `sudo dnf install libreoffice` |
| **Poppler** (`pdftoppm`) | `pptx_thumbnails` | `brew install poppler` | `sudo apt install poppler-utils` | `sudo dnf install poppler-utils` |
| **pango/cairo/gdk-pixbuf** | weasyprint (used by `md2pdf`) | `brew install pango gdk-pixbuf libffi` | `sudo apt install libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libpangoft2-1.0-0 libharfbuzz0b` | `sudo dnf install pango gdk-pixbuf2 cairo libffi` |
| **gcc/clang** | Compiling the AF_UNIX shim (only if running in a sandbox that blocks AF_UNIX — see §6) | Xcode CLT | `sudo apt install build-essential` | `sudo dnf groupinstall "Development Tools"` |

`install.sh` does NOT install these for you. It only checks and
prints the right command. The skill scripts that depend on a missing
tool fail with a clear error pointing back to the install command.

### Chromium for mermaid (`~/.cache/puppeteer/`)

`mmdc` (mermaid-cli) is bundled per skill (~6 MB of JS wrapper each
under `scripts/node_modules/`), but the actual Chromium binary it
drives is NOT — Puppeteer auto-downloads it to a **user-level shared
cache** at `~/.cache/puppeteer/` on first use (~1 GB, one Chromium
revision per puppeteer major). All four office skills + `marp-slide`
share this cache, so the disk hit is paid once per machine.

| What | Where | Size | Per-skill or shared? |
|---|---|---|---|
| `mmdc` JS wrapper | `skills/<skill>/scripts/node_modules/@mermaid-js/` | ~6 MB | per-skill |
| Chromium binary | `~/.cache/puppeteer/` | ~1 GB | **shared user-wide** |

The first `npm install` (per skill) doesn't download Chromium; it's
the first `mmdc` invocation that triggers the download. To force a
clean re-fetch (e.g. after a puppeteer upgrade lands a different
Chromium revision):

```bash
rm -rf ~/.cache/puppeteer
# Next mmdc call will redownload
```

---

## 3. docx — common workflows

### 3.1 Markdown → DOCX

```bash
node skills/docx/scripts/md2docx.js INPUT.md OUTPUT.docx \
    [--header "Header text"] [--footer "Footer text"]
```

Handles GFM tables, lists, fenced code, mermaid diagrams (auto-renders
to PNG via local `mmdc`), images (max 620×800 px to fit US Letter
content area).

### 3.2 DOCX → Markdown (extract for editing)

```bash
node skills/docx/scripts/docx2md.js INPUT.docx OUTPUT.md \
    [--metadata-json PATH] [--no-metadata] [--no-footnotes] [--json-errors]
```

Produces a sibling `OUTPUT_images/` directory if the source contains
embedded media. Uses mammoth (HTML conversion) + turndown (HTML → MD)
internally.

**Sidecar JSON for comments & tracked changes (docx-4).** Mammoth strips
`<w:comment>`, `<w:ins>`, `<w:del>` on its way to HTML, so the markdown
loses them. `docx2md.js` writes a `<OUTPUT-stem>.docx2md.json` sidecar
alongside the markdown when the source has any comments or revisions:

```json
{
  "v": 1,
  "source": "Контракт.docx",
  "comments": [
    {"id": 0, "paraId": "77E1E8F3", "parentParaId": null,
     "author": "Auditor", "initials": "AU", "date": "2026-04-28T15:22:00Z",
     "text": "verify against source",
     "anchorText": "абзаца",
     "anchorTextBefore": "Типа текст ", "anchorTextAfter": "",
     "paragraphIndex": 2}
  ],
  "revisions": [
    {"type": "insertion", "id": 100, "author": "Alice",
     "date": "2024-06-01T10:00:00Z", "text": "added clause",
     "paragraphIndex": 12, "runIndex": 3}
  ],
  "unsupported": {"rPrChange": 0, "pPrChange": 0, "moveFrom": 0,
                  "moveTo": 0, "cellIns": 0, "cellDel": 0}
}
```

The schema is versioned (`v: 1`); thread linkage for replies comes from
`paraIdParent` (matched against `commentsExtended.xml`); `paragraphIndex`
+ `anchorTextBefore` / `anchorTextAfter` give a stable locator even
when the anchor text appears multiple times in the document. The
`unsupported` field counts revision elements not yet captured (formatting
changes, content moves, table-cell ins/del) so callers know what was
lost — this is **honest scope**, not data loss reported as success. For
the full schema and field semantics see
[`skills/docx/references/docx2md-sidecar.md`](../../skills/docx/references/docx2md-sidecar.md).
**No sidecar is written if the source has no comments, no revisions,
and zero unsupported counts** — clean docs stay clean.

Flags:

- `--metadata-json PATH` overrides the sidecar location (default:
  `<OUTPUT-stem>.docx2md.json` next to the markdown).
- `--no-metadata` skips the comment/revision pass entirely (no sidecar
  ever written).
- `--no-footnotes` skips the footnote/endnote pandoc conversion
  described below (mammoth's default rendering takes over).
- `--json-errors` routes failures through the cross-5 envelope
  (`{v, error, code, type?, details?}`).

**Pandoc-style footnotes & endnotes (docx-5).** Word's
`<w:footnoteReference>` / `<w:endnoteReference>` markers are converted
to pandoc `[^fn-N]` / `[^en-N]` references inline, with definitions
appended at the end of the markdown:

```markdown
…body text with footnote[^fn-2] and endnote[^en-1].

[^fn-2]: A footnote about something important.
[^en-1]: An endnote referenced in the body.
```

Word's separator / continuationSeparator / continuationNotice entries
(boilerplate id `-1` and `0`) are filtered out as not user content.
Footnote/endnote text is captured as **plain text only** — formatting
inside the footnote (bold, links, nested lists) flattens. To keep
mammoth's older `[1](#fn1) → 1. ↑ text` rendering instead of pandoc
syntax, pass `--no-footnotes`.

**Same-path safety.** `node docx2md.js foo.docx foo.docx` (typo) used
to silently overwrite the input with markdown, destroying the source.
Now exits 6 with a `SelfOverwriteRefused` envelope. Symlinks resolving
to the same inode are caught too.

Use case for the sidecar: contract audit. Auditors get a clean
markdown they can diff side-by-side, plus a structured JSON file that
preserves the audit trail (who commented what, where, when; what the
reviewer inserted/deleted). The markdown is **not** polluted with
inline `<!-- COMMENT 1 -->` or `^[c1]` annotations — locator info
lives in the sidecar so md→docx round-trips don't propagate noise.

### 3.3 Fill a `{{placeholder}}` template

```bash
./.venv/bin/python skills/docx/scripts/docx_fill_template.py \
    template.docx data.json output.docx [--strict]
```

Supports `{{key}}` and `{{nested.key}}`. Performs `merge_runs`
canonicalisation first so placeholders fragmented by Word's
spell-checker still match. `--strict` exits non-zero if any
placeholder remains unresolved.

### 3.4 Accept all tracked changes (clean copy)

```bash
./.venv/bin/python skills/docx/scripts/docx_accept_changes.py IN.docx OUT.docx
```

Uses headless LibreOffice with a throw-away user profile and a
StarBasic macro that dispatches `.uno:AcceptAllTrackedChanges`.

### 3.5 Validate `.docx` structure

```bash
./.venv/bin/python skills/docx/scripts/office/validate.py FILE.docx \
    [--strict] [--json]
```

Checks: ZIP integrity, `[Content_Types].xml` parsing, relationship
targets, duplicate IDs across `<w:comment>`/`<w:bookmarkStart>`,
`<w:t>`-vs-`<w:delText>` placement, comment-marker pairing.

### 3.6 Compare tracked-change coverage vs an original

```bash
./.venv/bin/python skills/docx/scripts/office/validate.py edited.docx \
    --compare-to original.docx
```

Catches the **"editor forgot to enable Track Changes"** scenario:

- **Unmarked deletions/insertions/rewrites** → reported as `error`
- **Unmarked moves** (delete + insert of identical text at different
  positions) → collapsed into one "Unmarked move" finding
- **False-positive `<w:del>` marks** (deleting text that never
  existed in the original) → reported as `warning`
- **Authorship gaps** (`<w:ins>`/`<w:del>` without `w:author`) →
  reported as `warning`

Coverage includes `word/document.xml` AND `word/header*.xml` /
`word/footer*.xml` / `word/endnotes.xml` / `word/footnotes.xml`.
Text-box content (inside `<w:drawing>/<wp:txbxContent>`) is counted
once, not twice.

### 3.7 Round-trip XML editing

```bash
./.venv/bin/python skills/docx/scripts/office/unpack.py IN.docx unpacked/
# edit XML files under unpacked/word/ ...
./.venv/bin/python skills/docx/scripts/office/pack.py unpacked/ OUT.docx
./.venv/bin/python skills/docx/scripts/office/validate.py OUT.docx
```

`unpack.py` pretty-prints XML, merges adjacent runs, escapes smart
quotes/dashes into numeric XML entities so regex edits don't get
broken by encoding inconsistencies. `pack.py` reverses the entity
mapping.

---

## 4. xlsx — common workflows

### 4.1 CSV → styled .xlsx

```bash
./.venv/bin/python skills/xlsx/scripts/csv2xlsx.py data.csv out.xlsx \
    [--delimiter auto|,|;|\t] [--no-freeze] [--no-filter]
```

Bold header, frozen first row, auto-filter, auto column widths,
**preserves leading zeros** in code-like columns. Detects formula-
error tokens (`#REF!`, etc.) typed by user and stores as text (not
classified as cached formula errors by openpyxl).

### 4.2 Force formula recalculation

```bash
./.venv/bin/python skills/xlsx/scripts/xlsx_recalc.py file.xlsx \
    [--scan-errors] [--json]
```

openpyxl writes formulas as strings with no cached values; consumers
that read with `data_only=True` see `None` until some spreadsheet
engine resaves the file. This script invokes headless LibreOffice
with a `calculateAll()` macro to populate the cache.

### 4.3 Scan for formula errors (no recalc)

```bash
./.venv/bin/python skills/xlsx/scripts/xlsx_validate.py file.xlsx \
    [--fail-empty] [--json]
```

Counts cells whose Excel `data_type == "e"` (true formula errors).
Pairs with `xlsx_recalc.py` — recalc first, then validate.

### 4.4 Attach a chart to a range

```bash
./.venv/bin/python skills/xlsx/scripts/xlsx_add_chart.py file.xlsx \
    --type bar|line|pie \
    --data "B2:B11" \
    [--categories "A2:A11"] \
    [--title "Revenue"] \
    [--sheet "Sheet1"] \
    [--anchor "F2"] \
    [--titles-from-data | --no-titles-from-data] \
    [--output out.xlsx]
```

Wraps `openpyxl.chart` so the chart stays editable in
Excel/LibreOffice (no rasterisation). Defaults are tuned for the most
common follow-up to `csv2xlsx`:

- `--type` selects the chart class (BarChart, LineChart, PieChart).
- `--data` is the value range; multi-column blocks become multiple
  series.
- `--titles-from-data` is auto-detected from the top-left cell — if
  it's text, the first row is treated as series titles. Use
  `--no-titles-from-data` to override when your data has a header
  cell that's accidentally numeric (e.g. `2024`).
- `--anchor` defaults to two columns to the right of the data block.

Bad range syntax exits 1 with a hint; bad anchor likewise.

---

## 5. pptx — common workflows

### 5.1 Markdown → PPTX (built-in, programmatic)

```bash
node skills/pptx/scripts/md2pptx.js INPUT.md OUTPUT.pptx \
    [--size 16:9|4:3] [--theme theme.json] \
    [--mermaid-config PATH | --no-mermaid-config]
```

pptxgenjs-based renderer. Auto-paginates dense slides, mermaid
blocks render to PNG via local `mmdc`, adaptive font sizing for
high-density slides, accent colour stripe on every slide.

The mermaid flags mirror `md2pdf.py` exactly (see §6.1): the
bundled `scripts/mermaid-config.json` (Cyrillic-capable font stack)
is the default; `--mermaid-config PATH` overrides it; and
`--no-mermaid-config` opts out of the bundle so mmdc uses its
built-in Trebuchet MS theme. Both skills ship a byte-identical
config so non-English diagrams render consistently across PDF
and PPTX outputs.

### 5.2 Markdown → PPTX (delegated to marp-slide for editorial polish)

```bash
node skills/pptx/scripts/md2pptx.js INPUT.md OUTPUT.pptx --via-marp \
    [--marp-theme default|business|tech|...]
```

Pre-renders mermaid blocks to PNG (so they appear as proper image
shapes in the editable PPTX, not lost in marp's slide rasterisation),
then delegates to `skills/marp-slide/scripts/render.py` with
`--pptx-editable`. Requires LibreOffice (`marp-cli` uses it for
editable PPTX export).

### 5.3 PPTX → PDF

```bash
./.venv/bin/python skills/pptx/scripts/pptx_to_pdf.py deck.pptx [out.pdf]
```

### 5.4 Slide thumbnail grid

```bash
./.venv/bin/python skills/pptx/scripts/pptx_thumbnails.py deck.pptx grid.jpg \
    [--cols 3] [--dpi 110]
```

Pipeline: pptx → pdf (LibreOffice) → per-slide JPEGs (`pdftoppm`) →
labelled grid (Pillow). Useful for visual QA and as a deliverable to
sub-agents who can read images.

### 5.5 Markdown outline → slide skeleton

```bash
node skills/pptx/scripts/outline2pptx.js outline.md skeleton.pptx \
    [--size 16:9|4:3] [--theme theme.json]
```

For brainstorming the deck *structure* before writing slide content.
Promotion rules:

- `#` → title slide (large heading, accent stripe)
- `##` → content slide (heading + bulleted body, or `TODO: add content`
  placeholder if no bullets follow)
- `###`+ → demoted to **bold** bullets under the most-recent `##` slide
- prose paragraphs / list items under a heading → bullets

Output is a fully editable `.pptx` — open in PowerPoint / Keynote /
LibreOffice and replace placeholders with real content.

### 5.6 Clean orphaned parts

```bash
./.venv/bin/python skills/pptx/scripts/pptx_clean.py deck.pptx \
    [--output cleaned.pptx] [--dry-run]
```

A common artefact of hand-editing or template substitution: a
deletion removes the `<p:sldId>` reference but leaves the slide XML
plus its media in the zip. The package gets larger, diff tools get
noisier, and consumers may render hidden content.

`pptx_clean.py` walks the OOXML relationship graph from
`ppt/presentation.xml` outward (BFS through `.rels`), keeps only
parts reachable from `<p:sldIdLst>` plus the always-required
skeleton (`[Content_Types].xml`, `_rels/.rels`, `docProps/`), and
drops the rest. `[Content_Types].xml` Override entries pointing at
removed parts are stripped in the same pass.

`--dry-run` prints the keep / remove report as JSON without writing
the output file (idempotent — re-runs on a clean file produce no
changes).

---

## 6. pdf — common workflows

### 6.1 Markdown → PDF (with optional mermaid)

```bash
./.venv/bin/python skills/pdf/scripts/md2pdf.py doc.md doc.pdf \
    [--page-size letter|a4|legal] [--css extra.css] \
    [--no-mermaid] [--strict-mermaid] \
    [--mermaid-config PATH | --no-mermaid-config]
```

Uses weasyprint. Default stylesheet includes `@page` margins, footer
page numbers, and a `.mermaid-diagram` rule that constrains diagrams
to fit the page (`max-width: 100%; max-height: 7in`).

Fenced ```mermaid blocks are pre-rendered to **PNG** (not SVG —
weasyprint's SVG path doesn't honour mermaid's font chain, leaving
Cyrillic / CJK text invisible). Rendering is cached by SHA1 of the
diagram body **mixed with the config fingerprint** in
`<output_stem>_assets/`, so a config swap invalidates the cache
automatically.

Mermaid flags:

- `--no-mermaid` skips the preprocessing entirely (blocks render as
  code).
- `--strict-mermaid` exits non-zero if any block fails to render
  (default: warn and degrade to code).
- `--mermaid-config PATH` overrides the default config. If omitted,
  the bundled `scripts/mermaid-config.json` (Cyrillic-capable font
  stack: Arial Unicode MS → Noto Sans → DejaVu Sans → Liberation
  Sans → Arial) is used — perfect for non-English office documents
  on Linux servers where mmdc's default Trebuchet MS has no Cyrillic
  glyphs. A non-existent path triggers a warning and falls back to
  mmdc's defaults (or fails in `--strict-mermaid`).
- `--no-mermaid-config` opts out of the bundled default and lets
  `mmdc` use its built-in config (Trebuchet MS-based). Mutually
  exclusive with `--mermaid-config`.
- Without `mmdc` on `PATH` or in `scripts/node_modules/.bin/`, the
  step prints a friendly hint and falls through.

The same `--mermaid-config` / `--no-mermaid-config` / bundled-default
mechanism is mirrored in `md2pptx.js`; both skills ship a
byte-identical `mermaid-config.json` so non-English diagrams render
consistently across PDF and PPTX outputs. Both skills run mmdc
**11.x** (aligned with `marp-slide`), so all five mermaid renderers
in the repo share a single Chromium revision in
`~/.cache/puppeteer/`.

### 6.2 Merge / split

```bash
./.venv/bin/python skills/pdf/scripts/pdf_merge.py OUT.pdf A.pdf B.pdf C.pdf

./.venv/bin/python skills/pdf/scripts/pdf_split.py IN.pdf \
    --ranges "1-5:part1.pdf,6-10:part2.pdf"

./.venv/bin/python skills/pdf/scripts/pdf_split.py IN.pdf \
    --each-page OUTDIR/

./.venv/bin/python skills/pdf/scripts/pdf_split.py IN.pdf \
    --every 10 OUTDIR/
```

Range syntax accepts both `:` and `=>` separators (the latter is
useful when output paths contain `:` themselves, e.g. Windows drive
letters: `1-5=>C:\out.pdf`).

### 6.3 Inspect / fill / flatten an AcroForm

```bash
# 1. Detect form type — exit codes are the gate
./.venv/bin/python skills/pdf/scripts/pdf_fill_form.py --check FORM.pdf
#   exit 0  → AcroForm (fillable)
#   exit 11 → XFA (Adobe LiveCycle, NOT fillable via pypdf)
#   exit 12 → no form fields

# 2. Extract field schema for editing
./.venv/bin/python skills/pdf/scripts/pdf_fill_form.py \
    --extract-fields FORM.pdf -o fields.json

# 3. Fill from JSON (flat {field_name: value} map)
./.venv/bin/python skills/pdf/scripts/pdf_fill_form.py \
    FORM.pdf data.json -o FILLED.pdf [--flatten]
```

The exit codes start at 10 to leave 0–9 for argparse / shell
convention (so a usage error → exit 2, while an XFA refusal → exit
11). Checkbox values accept `true`/`false`, `1`/`0`, `"/Yes"`/`"/Off"`,
or bare `"Yes"`/`"Off"` — the script normalises to pypdf's
NameObject vocabulary. Unknown field names are reported as warnings
in stderr but don't fail the run (typo'd-field is the most common
source of "fill looked right, field stays empty"). `--flatten` drops
the `/AcroForm` dictionary so the values stick but the form is no
longer interactively editable.

XFA forms are detected and refused — pypdf cannot fill them. See
[`skills/pdf/references/forms.md`](../../skills/pdf/references/forms.md)
for the visual-overlay fallback when the document has no fillable
fields at all.

### 6.4 HTML / web-archive → PDF

```bash
./.venv/bin/python skills/pdf/scripts/html2pdf.py INPUT OUTPUT.pdf \
    [--page-size letter|a4|legal] [--css EXTRA.css] [--base-url DIR] \
    [--no-default-css] [--reader-mode] \
    [--archive-frame N|main|all|auto] [--list-frames] \
    [--timeout SECONDS] [--engine weasyprint|chrome]
```

INPUT may be `.html`/`.htm` (plain HTML), `.mhtml`/`.mht` (Chrome
"Save as → Single File"), or `.webarchive` (Safari "Save as → Web
Archive"). Sub-resources in archive formats are extracted to a
temporary directory automatically; URL references are rewritten to
local filenames before weasyprint sees them.

**Reader-mode vs regular** (defaults to regular — site CSS preserved):

- **Regular** (default) — keeps `<style>` blocks + inline styles;
  strips external `<link rel=stylesheet>` (because some real-world
  CSS hangs weasyprint or drops paragraphs — Хабр, vc.ru). Site
  layout largely preserved. Use for: invoices, reports with brand
  styling, BI dashboards, Confluence pages where the page styles
  matter for legibility.
- **`--reader-mode`** — Safari Reader View parity. Strips ALL site
  CSS + finds the article-body root via tiered candidate list
  (Confluence `#main-content` / `.wiki-content` first, then
  `.entry`/`.post-content`, then bare `<article>` / `[role=main]`,
  then bare `<main>` with body-ratio guard, then for hydrated SPAs
  with no semantic anchors — largest contentful subtree). Strips
  recommendation widgets, share bars, comment threads, ARIA
  navigation/banner/complementary landmarks. Use for: news/blog
  archives, GitBook docs, Discord docs, vc.ru/Хабр articles where
  site chrome matters less than typography consistency.

**Archive-frame selection (`--archive-frame N|main|all|auto`)** —
new in pdf-8 (2026-05-05). Webarchive/MHTML inputs may contain
multiple inner frames (e.g. ELMA365 email viewer renders each email
in its own iframe; HubSpot Marketplace has 6 chrome subframes around
the main page; Gmail has 5 system-widget subframes around the inbox
DOM). The flag selects which frame's content to render:

| Value | Behaviour |
|---|---|
| `main` (default) | Main resource only. Compatible with previous behaviour. |
| `N` (1-indexed) | Inner frame N — pick a specific email/document. |
| `all` | Concat all "substantial" inner frames with `<hr><h2>Frame N</h2>` separators. Useful for printing entire email threads. |
| `auto` | Deterministic: 0 substantial → `main`; 1 substantial → that frame; 2+ → `all`. With dominance guard: if 1 substantial subframe has < 10 % of main's text, falls back to `main` (HubSpot for WordPress case where the only substantial subframe is a system error overlay, not user content). |

"Substantial" is purely structural (zero vendor allow-list): inner
frame is substantial iff `bytes ≥ 1024` AND `<script>` count = 0
AND plain text ≥ 30 chars AND not a single-`<img>` body. Validated
on 9 real fixtures across 4 SPA stacks (Angular ELMA365, Closure
Gmail, Framer Sentora, bare Yandex Cloud Console) without a single
vendor name in the heuristic.

**Frame inventory (`--list-frames`)** — new in pdf-8. Prints a
tab-separated table (`index | kind | substantial | bytes | scripts |
text-len | url`) and exits, without rendering. Use to pick `N`
deterministically:

```bash
./.venv/bin/python skills/pdf/scripts/html2pdf.py \
    --list-frames email-thread.webarchive
# index  kind      substantial  bytes  scripts  text  url
# 0      main      no           1163772  10     25985 https://crm-dev.npkyarli.ru/index.html
# 1      subframe  yes          5388     0      686   about:blank
# 2      subframe  yes          1604     0      47    about:blank
# ...
./.venv/bin/python skills/pdf/scripts/html2pdf.py \
    --archive-frame 1 email-thread.webarchive first-email.pdf
```

**Render watchdog**: `--timeout SECONDS` (default 180,
`$HTML2PDF_TIMEOUT` env override, `0` disables) caps weasyprint via
`signal.SIGALRM`. Pathological CSS (Framer-built sites — Sentora,
some marketing pages) can put weasyprint into a multi-minute layout
loop; the watchdog kills it and exits 1 with a `RenderTimeout`
envelope. Reader-mode strips CSS so it usually completes under any
deadline; if regular mode times out, fall back to reader-mode.

**Exit codes**:
- `0` — render success
- `1` — render failure (weasyprint exception, timeout, format error)
- `2` — usage error (bad args, `NoSubstantialFrames` for
  `--archive-frame all` on archives with zero substantial frames,
  `FrameIndexOutOfRange` for `--archive-frame N` past the count)
- `6` — same-path I/O guard (input == output, including via symlink)

**Known weasyprint pathology — when reader-mode is mandatory**: <br>
(a) **Material 3 / GM3 CSS with `calc(...)` + bare-number args** —
weasyprint upstream bug `'NumberToken' object has no attribute 'unit'`.
Pdf-10 ships a `_strip_problematic_calc` workaround (replaces calc()
with `auto`), so Gmail no longer crashes; precision lost. <br>
(b) **Framer-built sites** (sentora.com, framer.io customer sites) —
infinite layout loop on weasyprint, watchdog fires after 180s.
Reader-mode strips Framer CSS; rendering completes. <br>
(c) **ELMA365 hydrated Angular DOM** (>1 MB main HTML with
virtualized `<app-appview-card>` lists) — weasyprint inline-layout
bug `tuple index out of range` on `inline.py:231`. Reader-mode
extracts text content cleanly; regular mode crashes. <br>
For these classes of input, prefer `--reader-mode` or use the chrome
render engine (see below).

**Render engine (`--engine weasyprint|chrome`)** — new in pdf-11
(2026-05-05). The default `weasyprint` engine is fast and pure-Python
but has hard limits on modern web SPAs (cases (a)/(b)/(c) above plus
JS-hydrated content and `<canvas>` charts). The opt-in `chrome`
engine renders through a real headless Chromium via Playwright,
producing browser-faithful output where weasyprint fails:

```bash
# 1. Install Chromium once (~150 MB, cached after):
bash skills/pdf/scripts/install.sh --with-chrome

# 2. Render through Chrome:
./.venv/bin/python skills/pdf/scripts/html2pdf.py \
    page.webarchive out.pdf --engine chrome
```

When to switch engines:

| Symptom (weasyprint output) | Use |
|---|---|
| Exit 1 `'NumberToken' object has no attribute 'unit'` | `--engine chrome` |
| Exit 1 `tuple index out of range` from `inline.py` | `--engine chrome` |
| `RenderTimeout` after watchdog fires (Framer-built page) | `--engine chrome` (or first try `--reader-mode`) |
| `<canvas>` chart appears blank in PDF | `--engine chrome` |
| Page shows `(loading…)` placeholder text | `--engine chrome` |
| Output looks fine | leave default `weasyprint` (5-10× faster) |

The chrome path skips weasyprint preprocessing (calc-strip,
font-face-strip, NORMALIZE_CSS) — those are weasyprint workarounds
Chrome doesn't need; reader-mode and `--css EXTRA.css` still apply
because they're engine-agnostic. Network is blocked in both engines:
chrome uses Playwright `context.route()` to abort `http(s)://`
requests, mirroring weasyprint's `_offline_url_fetcher`.

Without Playwright installed, `--engine chrome` exits 1 with a
`ChromeEngineUnavailable` envelope naming the install command.

---

## 7. Sandboxed deployment notes (LD_PRELOAD shim)

If you deploy these skills inside a seccomp-tightened sandbox that
**blocks `socket(AF_UNIX, ...)`** (some managed-agent runners,
nsjail with restrictive profiles, certain Docker security configs),
LibreOffice fails to start with `EACCES` on its self-check.

[`skills/docx/scripts/office/shim/lo_socket_shim.c`](../../skills/docx/scripts/office/shim/lo_socket_shim.c)
is a `LD_PRELOAD`/`DYLD_INSERT_LIBRARIES` shim that intercepts
`socket(AF_UNIX)` and substitutes `socketpair()`. The wrapper
`_soffice.py` auto-detects sandbox conditions and, if needed,
compiles the shim on first use and injects it.

### Honest scope

The shim enables LibreOffice **start-up** in such sandboxes. It is
sufficient for headless single-process operations:

- `soffice --headless --convert-to pdf …`
- `soffice --headless --convert-to xlsx …`
- The recalc / accept-changes macros used by `xlsx_recalc.py` and
  `docx_accept_changes.py`.

The shim does **NOT** provide cross-process AF_UNIX IPC. Each
`socket()` call yields an isolated `socketpair()` with no shared
path→fd registry, so a worker process that calls `connect()` to a
sun_path the parent bound to receives no actual data flow. The
limitation is locked in by the test
`TestShimCrossProcessIPCLimitation` in
[`scripts/office/tests/test_shim.py`](../../skills/docx/scripts/office/tests/test_shim.py)
— if you need real IPC, grant AF_UNIX in the sandbox policy
instead. See [`scripts/office/tests/test_shim.md`](../../skills/docx/scripts/office/tests/test_shim.md)
for nsjail / Docker validation procedure.

### Override

Force shim even when AF_UNIX is available (for testing or when
auto-detection misfires):

```bash
LO_SHIM_FORCE=1 ./.venv/bin/python skills/docx/scripts/docx_accept_changes.py …
```

Verbose tracing of intercepts:

```bash
LO_SHIM_VERBOSE=1 LO_SHIM_FORCE=1 …
```

### macOS hardened-runtime caveat

Apple strips `DYLD_INSERT_LIBRARIES` at exec time for hardened-
runtime binaries. The LibreOffice.app bundle from The Document
Foundation IS signed with hardened runtime. `_soffice.py` warns when
the shim is requested against such a binary because it will
silently no-op. On macOS desktop you typically don't need the shim
at all (AF_UNIX works), so this only matters for unusual setups.

---

## 8. Test suite

Two layers of automated tests cover the office skills.

### 8.1 Unit tests (in `office/tests/` of each skill)

The shared `office/` module has **43 unit tests** under
`skills/docx/scripts/office/tests/`:

- **`test_redlining.py`** (10 tests): identical docs / marked
  insertions / marked deletions / unmarked deletions / unmarked
  insertions / unmarked moves / textbox dedup / header changes /
  false-positive marks / missing authors.
- **`test_shim.py`** (3 tests): two `TestShimInterceptionContract`
  tests that confirm the shim makes `bind/listen/accept` succeed,
  and one `TestShimCrossProcessIPCLimitation` test that LOCKS IN
  the documented "no cross-process IPC" limitation (it passes
  when the limitation holds — i.e. when nobody has retroactively
  expanded the shim's scope without updating the docs).
- **`test_pptx_validator.py`** (11 tests): clean fixture / per-instance
  `xsd_map` isolation (×2 — guards against class-level mutable-default
  pollution) / missing slide part / orphan slide warning / duplicate
  `<p:sldId>` / sldId out of ECMA-376 §19.2.1.34 range / missing
  slideLayout / missing slideMaster / blip → unknown rId / blip →
  missing media part.
- **`test_xlsx_validator.py`** (19 tests): clean fixture / instance
  isolation (×2) / missing sheet part / orphan worksheet / orphan
  chartsheet / duplicate sheet name / **case-insensitive** duplicate
  (per Excel rule) / zero-sheet workbook / duplicate sheetId /
  relationship file missing message / percent-encoded `Target=`
  resolves correctly / backslash `Target=` normalised /
  out-of-bounds shared-string index / sst reference without
  `xl/sharedStrings.xml` / `<c t="s">` without `<v>` per ECMA-376
  §18.3.1.4 / out-of-bounds cell-style index / empty `cellXfs`
  produces a distinct message / duplicate `definedName` per scope.

Run from the docx skill:

```bash
cd skills/docx/scripts
./.venv/bin/python -m unittest discover -s office/tests
```

Per the [contributor protocol](../CONTRIBUTING.md#3-office-skills-modification-protocol-strict),
the unit-test files stay only in `docx`; xlsx and pptx receive byte-
identical copies of `office/` (which includes the tests), but the
tests are typically run from the docx skill since that's the
master. The docx skill also has additional unit suites under
`scripts/docx2md/tests/` covering the markdown-postprocess passes
and shape-extraction logic.

### 8.2 End-to-end smoke suites

Each skill ships a `scripts/tests/test_e2e.sh` that runs every
user-facing CLI on a real fixture and asserts the output's basic
shape (file exists, page count, element presence, exit code, error
message text). The top-level orchestrator runs all four sequentially:

```bash
bash tests/run_all_e2e.sh
```

Per-skill quick check:

```bash
bash skills/docx/scripts/tests/test_e2e.sh
bash skills/xlsx/scripts/tests/test_e2e.sh
bash skills/pptx/scripts/tests/test_e2e.sh
bash skills/pdf/scripts/tests/test_e2e.sh
```

What's covered:

| Skill | Coverage |
|---|---|
| docx | `md2docx → docx → docx2md` round-trip, `office.validate` on output, `docx_fill_template` with nested JSON, encryption / legacy-CFB rejection on `docx_fill_template` and `docx_accept_changes`, **cross-7** `office_passwd` (clean→encrypt→decrypt round-trip + zip-namelist parity, wrong-password exit 4, state-mismatch exit 5, stdin password, JSON envelope), **docx-4 + docx-5** `docx2md` sidecar (clean→no sidecar; `docx_add_comment` injection→sidecar v=1 with comment fields populated; `<w:ins>`/`<w:del>` injection→`paragraphIndex`+`runIndex`; pandoc `[^fn-N]`/`[^en-N]` markers + definitions; `--no-metadata` / `--no-footnotes` / `--metadata-json` / `--json-errors` envelopes), **VDD-regression** (same-path `SelfOverwriteRefused` exit 6 + input intact, empty footnote → resolvable `[^fn-N]:` definition, `--metadata-json` rejects flag-as-path, `id=""` serialised null not 0, Cyrillic+emoji footnote text, `<w:rPrChange>` counted in `unsupported`), **q-7** `html2docx` preprocess unit tests (57 sub-assertions, run before E2E so a stage-level regression fails fast) + regression battery (18 sub-assertions, paragraph/size/image-count tolerance bands + needles per fixture × mode, see §8.6). |
| xlsx | `csv2xlsx` + row count + `office.validate`, `xlsx_validate` (clean + injected `#DIV/0!` via lxml mutation), `xlsx_recalc` formula preservation, `xlsx_add_chart` (bar/line/pie variants + bad-range error), encryption rejection on `xlsx_validate`/`xlsx_add_chart`/`xlsx_recalc`, **cross-7** `office_passwd` (round-trip + openpyxl-readable post-decrypt with row count preserved, wrong-password, state-mismatch, stdin, JSON envelope). |
| pptx | `md2pptx` + slide-count + `office.validate`, `pptx_thumbnails` (JPEG sanity), `pptx_to_pdf` (`%PDF` magic), `pptx_clean` (orphan slide + media removal, dry-run reports without writing), `outline2pptx` (heading-only MD → 4 slides + validate + heading-less input fails clearly), bundled `mermaid-config.json` (parses, missing path fails clean), encryption rejection on `pptx_clean`/`pptx_thumbnails`/`pptx_to_pdf`, **cross-7** `office_passwd` (round-trip + slide-count preserved post-decrypt, wrong-password, state-mismatch, stdin, JSON envelope). |
| pdf | `md2pdf` + mermaid PNG render + bundled `mermaid-config.json` (parses, missing path warns, config change invalidates PNG cache), `pdf_merge` (page-count = sum), `pdf_split --each-page`, `pdf_fill_form` (`--check` exit codes, fill round-trip, `--flatten` removes `/AcroForm`, `--extract-fields` stdout, malformed JSON / missing `-o` exit 2, typo'd field warning, int→`/Yes` checkbox coercion), **q-3 mermaid edge-cases** (cyrillic / sequence / gantt / large-mindmap fixtures + `--strict-mermaid` exits non-zero on broken input + lenient mode degrades with warning). pdf has its own AcroForm path and does NOT use `office_passwd.py`. |

Each suite ends with a **q-2 visual-regression** block that compares
the first page of every produced PDF against a committed golden
(see §8.3). Total bash-level assertion count after q-2/q-3 +
docx-1/docx-2 + VDD adversarial + **q-7** (which adds 2 aggregate
assertions to the docx suite that wrap 57 + 18 sub-checks): **221**
(86 docx + 40 xlsx + 48 pptx + 47 pdf).

The suite is fast (<60 sec total on a warm machine) and is the
primary pre-commit / pre-release gate. Any failure here points at a
broken user-facing contract.

### 8.3 Visual regression (q-2)

[`tests/visual/visual_compare.py`](../../tests/visual/visual_compare.py)
captures the first page of every E2E-produced PDF via `pdftoppm` →
PNG, then compares against a committed golden using ImageMagick
`compare -metric AE -fuzz 5%`. Goldens live at
`tests/visual/goldens/<skill>/<name>.png`. The default tolerance is
0.5% of total pixels — generous enough to absorb cross-platform
font-rendering drift, tight enough to catch real layout regressions.

```bash
# Run normally — soft-skips when ImageMagick or a golden is missing
bash tests/run_all_e2e.sh

# Regenerate goldens after a deliberate output change
UPDATE_GOLDENS=1 bash tests/run_all_e2e.sh
git diff tests/visual/goldens/      # review

# CI-strict mode: missing IM or missing golden → hard failure
STRICT_VISUAL=1 bash tests/run_all_e2e.sh
```

See [`tests/visual/README.md`](../../tests/visual/README.md) for the
full contract (exit codes, threshold tuning, cross-platform notes).
The bash glue lives in
[`tests/visual/_visual_helper.sh`](../../tests/visual/_visual_helper.sh)
and is sourced by every per-skill `test_e2e.sh`.

### 8.4 Property-based fuzz (q-5)

[`tests/property/`](../../tests/property/) drives `md2pdf.py`,
`md2docx.js`, and `csv2xlsx.py` as black boxes via Hypothesis with
unicode-rich markdown / CSV strategies. Each test asserts the CLI
either exits 0 with a non-empty output OR exits non-zero **without**
a Python traceback / Node uncaught exception. Catches crash-on-edge-
input regressions that the deterministic E2E suite misses.

```bash
bash tests/property/setup.sh                          # one-time
tests/property/.venv/bin/pytest tests/property -q     # 30 examples (~30s)

# CI profile — 100 examples per test (~2 min)
HYPOTHESIS_PROFILE=ci tests/property/.venv/bin/pytest tests/property -q
```

Strategies live in
[`tests/property/strategies.py`](../../tests/property/strategies.py).
Each example runs in its own `tempfile.TemporaryDirectory()` —
pytest's `tmp_path` is function-scoped and incompatible with
`@given`. Default profile is `dev` (30 examples, 20-s deadline);
override with `HYPOTHESIS_PROFILE=ci`.

### 8.5 GitHub Actions CI

[`.github/workflows/office-skills.yml`](../../.github/workflows/office-skills.yml)
runs everything above on push/PR with `STRICT_VISUAL=1` and
`HYPOTHESIS_PROFILE=ci`. `workflow_dispatch` with `update_goldens=true`
regenerates visual goldens on the matching Ubuntu runner image and
uploads per-skill PNG artifacts — cross-platform drift is the main
reason locally-generated goldens may need a one-time regen on first
CI run.

For when something goes wrong: see
[`office-skills_troubleshooting.md`](office-skills_troubleshooting.md)
— a single document with `Symptom → Cause → Fix` recipes for the
recurring failures (pango/cairo missing, soffice timeout, mmdc fail,
encrypted-input rejection, golden drift, etc.).

### 8.6 Regression battery for HTML converters (q-6 / q-7)

`html2pdf.py` and `html2docx.js` are the two universal-HTML inputs in
the suite — each ships ~250 LOC of site-specific preprocessing rules
that strip chrome (copy buttons, anchor icons, ARIA navigation
landmarks), reshape DOM (ARIA tables → `<table>`, Mintlify Steps →
flat headings), and wrap inline code (Confluence DC `<span
data-code-lang>`). A subtle break in any rule slips past the
deterministic E2E suite because each fixture's expected output is
itself derived from the preprocessing pipeline. The regression
battery closes that gap with **tolerance-band signatures** captured
at a known-good baseline.

**pdf battery (q-6)**:
[`skills/pdf/scripts/tests/test_battery.py`](../../skills/pdf/scripts/tests/test_battery.py)
+ [`battery_signatures.json`](../../skills/pdf/scripts/tests/battery_signatures.json)
+ [`capture_signatures.py`](../../skills/pdf/scripts/tests/capture_signatures.py).
Per fixture × {`regular`, `reader`-mode}: page-count band ±5 %, file-
size band ±10 %, list of `required_needles` (text fragments that
must appear in `pdftotext` output), list of `forbidden_needles`
(chrome strings that MUST NOT leak). Fixture sources: `tmp/` (real
.webarchive / .mhtml, gitignored), `examples/regression/` (committed
synthetic edge cases), `tests/fixtures/platforms/` (committed
hand-stripped real-platform slices).

**docx battery (q-7)**:
[`skills/docx/scripts/tests/test_battery.py`](../../skills/docx/scripts/tests/test_battery.py)
+ [`battery_signatures.json`](../../skills/docx/scripts/tests/battery_signatures.json)
+ [`capture_signatures.py`](../../skills/docx/scripts/tests/capture_signatures.py).
Schema parallel to pdf with **paragraph-count** instead of pages
(±5 % floor 2) and an additional **image-count metric** (`min_images`
/ `max_images` — exact match, no tolerance) that catches icon-strip
regressions where size and paragraph bands stay within ±10 % even
when a 20×20 SVG icon leaks past `_isIconSvg` rule 6. Text extraction
goes through stdlib `zipfile` + `lxml` directly against
`word/document.xml` — counts `<w:p>` elements, joins `<w:t>` text,
counts `<w:drawing>` elements. Fixture sources: same three-tier
layout (`tests/tmp/` gitignored, `examples/regression/`,
`tests/fixtures/platforms/`). q-7 also extracts `_html2docx_preprocess.js`
as a sibling module with 16 named-export stages, covered by
**57 unit tests** in
[`tests/test_html2docx_preprocess.test.js`](../../skills/docx/scripts/tests/test_html2docx_preprocess.test.js)
(synthetic-HTML inputs for every stage + negative cases).

```bash
# Run battery on its own (per-skill)
./.venv/bin/python -m unittest tests.test_battery -v
# (also runs as part of `bash tests/test_e2e.sh`)

# Refresh signatures after an intentional preprocessing change
./.venv/bin/python tests/capture_signatures.py --refresh
git diff tests/battery_signatures.json     # review

# Refresh a single fixture (docx — by filename)
./.venv/bin/python tests/capture_signatures.py --fixture confluence-version-table.html
```

User-curated fields (`forbidden_needles`, top-level `_*` annotations)
are PRESERVED across `--refresh`; tolerance bands and
auto-sampled `required_needles` are regenerated. When `regular` and
`reader` produce byte-identical entries (synthetic fixtures that
don't trigger reader-mode chrome strip), capture auto-sets `reader =
null` so the test_battery loader skips it (q-7 MED-3 dedupe).

**Canary verification (q-7 LOW-3)**:
[`skills/docx/scripts/tests/canary_check.sh`](../../skills/docx/scripts/tests/canary_check.sh)
sequentially sabotages three preprocessing rules (icon-strip rule 6,
Mintlify Steps flatten, reader-mode keyword strip) via `sed -i.bak`,
runs the battery, and asserts FAIL each time. Restores the file via
`trap`. Without this meta-test, a green battery is consistent with
both "no regression" AND "battery permanently broken". Run manually
when adding new fixtures or after large preprocessing-pipeline edits:

```bash
bash skills/docx/scripts/tests/canary_check.sh
# expects: 3/3 sabotages detected — battery is healthy
```

---

## 9. Validation matrix — what every skill exposes

```bash
# Generic structural validation (all four):
./.venv/bin/python skills/docx/scripts/office/validate.py FILE.docx
./.venv/bin/python skills/xlsx/scripts/office/validate.py FILE.xlsx
./.venv/bin/python skills/pptx/scripts/office/validate.py FILE.pptx

# Content-level validation:
./.venv/bin/python skills/docx/scripts/office/validate.py FILE.docx --compare-to ORIGINAL.docx
./.venv/bin/python skills/xlsx/scripts/xlsx_validate.py FILE.xlsx --fail-empty

# Skill-level Gold Standard validation:
python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/<skill>
```

All four skills currently pass `validate_skill.py`.

### What `office/validate.py` actually checks

Every container goes through the base structural pass: ZIP integrity,
`[Content_Types].xml` presence, relationship targets exist, IDs that
ECMA-376 declares unique are unique. On top of that each format adds
its own structural-semantic layer:

| Skill | Validator | Format-specific checks (in addition to base) |
| :--- | :--- | :--- |
| docx | `DocxValidator` | Tracked-change integrity (`<w:t>` inside `<w:del>` flagged); comment-marker pairing (`commentRangeStart`/`commentRangeEnd`/`commentReference` triples). Optional: `--compare-to` runs `RedliningValidator` to catch text changes that bypass `<w:ins>`/`<w:del>` (the "editor forgot to enable Track Changes" trap). |
| xlsx | `XlsxValidator` | Sheet chain (`<sheet @r:id>` → workbook.rels → real `xl/worksheets/sheetN.xml`); sheet name uniqueness — **case-insensitive**, per Excel rule (`Sheet1` ≡ `SHEET1`); sheetId + r:id uniqueness (Excel hard-fail at duplicates); zero-sheet workbook → error; `definedName` case-insensitive uniqueness per scope; **shared-string index bounds** (`<c t="s"><v>N</v>` ≤ count of `<si>` in `xl/sharedStrings.xml`); **`<c t="s">` without `<v>`** flagged per ECMA-376 §18.3.1.4; **cell-style index bounds** (`<c s="N">` ≤ count of `cellXfs` in `xl/styles.xml`) with a distinct message when `cellXfs` is empty; orphan parts in `xl/worksheets/`, `xl/chartsheets/`, `xl/dialogsheets/`. |
| pptx | `PptxValidator` | Slide chain (`<p:sldId>` → presentation.rels → real `ppt/slides/slideN.xml`); slide-id uniqueness + ECMA-376 §19.2.1.34 `ST_SlideId` range `[256, 2 147 483 647]`; layout/master chain (each slide → its layout → its master, all must exist); media references (`<a:blip r:embed>`, `<p:videoFile r:link>` resolve to packaged parts); notes-slide reciprocity (notes → back to its slide); orphan slides warning. |
| pdf | (uses pypdf/pdfplumber inline; no OOXML validator) | n/a — `pdf_fill_form.py --check` returns the AcroForm/XFA/none triage exit codes (0/11/12). |

**XSD binding is opt-in.** ECMA-376 schemas are large (~10 MB) and
not bundled by default. Run `office/schemas/fetch.sh` to download
them; XSD validation then activates automatically for the parts each
validator declares in its `xsd_map` (workbook.xml, sheets, slides,
slide layouts, slide masters, sharedStrings, styles, etc.). Without
the schemas, `--strict` produces "XSD not bundled" warnings and exit
1 — the gate is intentional so CI cannot silently skip schema checks.

The validators are exercised by **30 unit tests**
(`office/tests/test_pptx_validator.py` 11 + `test_xlsx_validator.py`
19) plus E2E entries that inject deliberate breakage (orphan slide,
missing slideLayout, blip → unknown rId, out-of-range sst index,
duplicate sheet name, `<c t="s">` without `<v>`) and assert the
validator catches each. Two of the unit tests in each validator
specifically guard a Python gotcha that bit us during
implementation: the per-instance `xsd_map = dict(self.__class__.xsd_map)`
copy in `BaseSchemaValidator.__init__` — without it, dynamically
adding a slide-XSD entry for one file leaks into the next instance
because the class-level dict is shared.

---

## 9.5. Cross-skill safeguards (cross-1 / 4 / 5 / 7)

Four features cut across the office skills and were intentionally
designed for uniformity. Three (`cross-1`, `cross-4`, `cross-5`)
ship in all four skills; one (`cross-7`) ships in the three OOXML
skills only — pdf has its own encryption mechanism (pypdf
`PdfWriter.encrypt`).

### `--json-errors` (cross-5)

Every Python CLI accepts `--json-errors`. When set, failures are
emitted as a single line of JSON on stderr:

```json
{"v": 1, "error": "Input not found: /nope.pdf", "code": 1, "type": "FileNotFound", "details": {"path": "/nope.pdf"}}
```

Schema:

| Field | Type | When | Notes |
| :--- | :--- | :--- | :--- |
| `v` | int | always | Schema version. Currently `1`. Bump only on breaking changes. |
| `error` | str | always | Human-readable message; may contain newlines (`\n` in JSON). |
| `code` | int | always | Matches the script's exit code. **Never `0`** — `report_error(code=0)` is coerced to `1` and tagged with `details.coerced_from_zero=true`. |
| `type` | str | optional | ErrorClass name (`FileNotFound`, `EncryptedFileError`, `UsageError`, `InvalidArgument`, `UnidentifiedImageError`, `PreviewError`, …). |
| `details` | object | optional | Free-form context (`path`, `flag`, `value`, `missing`, …). |

Coverage:

- **Domain errors** — emitted via `report_error()` in `_errors.py`.
- **Argparse usage errors** — `parser.error("…")`, missing required
  args, type-conversion failures. The `add_json_errors_argument` helper
  transparently patches `parser.error` so the same flag covers both
  surfaces. Without this, wrappers parsing JSON would have choked on
  argparse's plain-text usage banner — a regression guarded by
  `argparse usage error routed to JSON envelope (UsageError + v=1)`.

Plain mode (the default) is unchanged free-form text, so existing
shell pipelines do not break. Wrappers and CI runners gain one parser
that works for every script.

The helper lives at `scripts/_errors.py`, byte-identical in all four
skills (replication protocol in [`CLAUDE.md` §2](../../CLAUDE.md)).

### Macro-enabled file detection (cross-4)

`office/_macros.py` provides `is_macro_enabled_file(path)` — parses
`[Content_Types].xml` with `defusedxml` and looks for a `<Default>` or
`<Override>` element whose `ContentType` attribute exactly matches one
of the OOXML macro types (`application/vnd.ms-word.document.macroEnabled.main+xml`,
sheet, presentation, plus their `.dotm`/`.xltm`/`.potm` template
twins).

The content-type is the **authoritative** signal — Office decides
whether to invoke the VBA runtime based on it, not on the presence of
`vbaProject.bin`. Earlier (logical-OR) implementations produced false
positives on documents with stray bins from manual editing; substring
matches on the XML produced false positives on files that mentioned
`macroEnabled` inside an XML comment. Both regressions are now guarded
by E2E tests.

Used by:

- `docx_fill_template.py`, `docx_accept_changes.py`,
  `xlsx_recalc.py`, `xlsx_add_chart.py`, `pptx_clean.py`: stderr
  warning via `format_macro_loss_warning()` when the input is
  `.docm`/`.xlsm`/`.pptm`/`.dotm`/`.xltm`/`.potm` and the chosen
  output extension drops the macros (`.docx`/…/`.potx`). The warning
  suggests the matching macro extension instead.
- `office/unpack.py`: prints a one-line note when the input is
  macro-enabled, so power users repacking from the unpacked tree
  know to keep the `m` in the extension.
- `office/pack.py`: walks the unpacked tree for `vbaProject.bin` and
  emits a different warning via `format_pack_macro_loss_warning()`
  ("source tree contains vbaProject.bin…") — the writer-script
  framing ("input is macro-enabled (.docm)") would be misleading
  here because `pack` operates on a directory, not a source file.

Read-only only — we never inspect or rewrite VBA bytecode.

### Universal `preview.py` (cross-1)

Each office skill ships a byte-identical
`scripts/preview.py` that renders `INPUT.pdf` / `INPUT.docx` /
`INPUT.xlsx` / `INPUT.pptx` (or any `.docm`/`.xlsm`/`.pptm`) into a
single labelled PNG-grid JPEG. Pipeline:

```
.pdf                  → pdftoppm                                   → PIL grid
.docx/.xlsx/.pptx*    → soffice --headless --convert-to pdf → pdftoppm → PIL grid
```

Usage:

```bash
python3 skills/<skill>/scripts/preview.py INPUT OUTPUT.jpg \
    [--cols 3] [--dpi 110] [--gap 12] [--padding 24]
    [--label-font-size 14]
    [--soffice-timeout 240] [--pdftoppm-timeout 60]
    [--json-errors]
```

Flags:

| Flag | Default | Notes |
| :--- | :--- | :--- |
| `--cols` | 3 | Grid columns. Validated `≥1` up-front. |
| `--dpi` | 110 | Render DPI. Validated `≥1`. |
| `--gap` / `--padding` | 12 / 24 | Pixels. Validated `≥0`. |
| `--label-font-size` | 14 | Font size in points. Validated `≥1`. |
| `--soffice-timeout` | 240 s | OOXML→PDF timeout (LibreOffice). Increase for very large decks. Ignored on `.pdf` input. |
| `--pdftoppm-timeout` | 60 s | PDF→JPEG timeout (Poppler). Bounds hangs on malformed PDFs. |
| `--json-errors` | off | See §9.5/cross-5. |

Robustness behaviours:

- **Output dir auto-created** — `args.output.parent.mkdir(parents=True, exist_ok=True)`
  runs before any rendering, so `preview.py in.pdf out/sub/dir/p.jpg`
  works without pre-creating the path.
- **Subprocess capture** — both soffice and pdftoppm run with
  `capture_output=True`; their stderr is folded into the JSON
  envelope's `error` field instead of leaking past it.
- **Image-decode safety** — `PIL.UnidentifiedImageError` and broad
  `OSError` are caught in `main()` and routed through `report_error`,
  so a corrupt tile never escapes as a Python traceback.
- **Font fallback** — `_load_font` tries `Arial.ttf` / `DejaVuSans.ttf`
  in order; on filesystem errors (`OSError` on read), it walks to the
  next candidate. If none load, falls back to Pillow's `load_default`
  (modern signature with `size=` first, legacy without on `TypeError`).

The label changes per file type — "Page" for docx/pdf, "Sheet" for
xlsx, "Slide" for pptx — picked from the input's extension.

Why a single CLI in four places: each skill must remain independently
installable as a `.skill` archive, but a user who only has the `pdf`
skill should still be able to preview a colleague's `.pptx`. Shipping
the same file in all four locations is cheap (~6 KB each) and avoids
forcing users to install multiple skills just to render previews.

### Password protection (cross-7)

The three OOXML skills (docx/xlsx/pptx) ship a byte-identical
`scripts/office_passwd.py` that sets or removes Office password
protection via `msoffcrypto-tool` (MS-OFB Agile, Office 2010+). pdf
has its own mechanism (`pypdf` `PdfWriter.encrypt`) and does not use
this script.

```bash
# Put a password on a clean .docx/.xlsx/.pptx
python3 skills/<skill>/scripts/office_passwd.py CLEAN.docx ENC.docx --encrypt hunter2

# Remove the password
python3 skills/<skill>/scripts/office_passwd.py ENC.docx CLEAN.docx --decrypt hunter2

# Detect whether a file is currently password-protected
python3 skills/<skill>/scripts/office_passwd.py FILE.docx --check
#   exit 0  → encrypted (CFB container)
#   exit 10 → not encrypted (clean OOXML)
#   exit 11 → input not found
```

Exit codes round out the contract:

| Code | Meaning |
| :--- | :--- |
| 0 | Success (also `--check` on encrypted file) |
| 1 | Generic msoffcrypto failure (`FileFormatError`, IO) |
| 2 | argparse usage error (auto-routed via cross-5) |
| 3 | `msoffcrypto-tool` not installed in this skill's venv |
| 4 | Wrong password supplied to `--decrypt` (output is removed, no half-written decoy) |
| 5 | State mismatch — `--encrypt` on already-encrypted, or `--decrypt` on clean OOXML |
| 10 | `--check`: file is NOT encrypted |
| 11 | Input file not found |

Password input modes:

- **Argv** — `--encrypt hunter2`. Convenient, but visible in `ps`
  and shell history. Fine for local one-offs.
- **Stdin** — pass `-` as the password and the script reads one line
  from stdin (newline stripped). Combine with shell here-strings or
  process substitution to keep the secret off the command line:
  ```bash
  python3 office_passwd.py FILE.docx ENC.docx --encrypt - <<<"$PASS"
  python3 office_passwd.py FILE.docx ENC.docx --encrypt - </path/to/secret
  ```

Round-trip is lossless — the OOXML zip namelist (every part inside
the package) is byte-equal before encrypt and after decrypt. The
encrypted output is a CFB container, so passing it to any of the
office reader scripts (`docx_fill_template`, `xlsx_recalc`,
`pptx_clean`, `office.validate`, …) trips the cross-3 encryption
guard and exits 3 with the standard "password-protected OR legacy
.doc/.xls/.ppt" message — that's the intended pairing: cross-3
detects, cross-7 acts on.

Implementation notes:

- The wrong-password path catches `msoffcrypto.exceptions.InvalidKeyError`
  at the outer scope so both eager (Agile) and lazy (block-by-block)
  variants fold into the same exit-4 path. The output file is
  `unlink`-ed before reporting so callers don't get a 0-byte decoy
  that they might mistake for a successful decrypt.
- `assert_not_encrypted` is intentionally NOT called by `--encrypt`
  before encrypting (it would refuse all writers because they'd see
  CFB after the first round-trip). Instead, `office_passwd.py` calls
  `is_cfb_container` directly and produces a different exit code (5,
  state mismatch) when asked to re-encrypt an already-encrypted file.
- `msoffcrypto-tool>=5.4.0` lives in the `requirements.txt` of the
  three OOXML skills; `install.sh` picks it up on next run.

The 11 cross-7 E2E entries per skill (33 total) cover: clean→encrypt→
check→decrypt round-trip, validate-after-decrypt, openpyxl/slide-count
sanity post-decrypt, wrong-password (exit 4 + output removed),
state-mismatch encrypt-on-encrypted (exit 5), state-mismatch
decrypt-on-clean (exit 5), stdin password input, and JSON envelope
on wrong-password (`type:"InvalidPassword"`, `code:4`, `v:1`).

---

## 10. Package inventory — what lives where

A complete map of what each skill installs locally and what it
expects globally on the host. Use this when you want to clean up,
audit, or move skills between machines.

### 10.1 Globally installed (once per machine)

These are NEVER bundled into a skill. `install.sh` checks them and
prints install hints; the user is responsible.

| Tool | Installer (macOS / Debian / Fedora) | Used by |
|---|---|---|
| **`soffice`** (LibreOffice) | `brew install --cask libreoffice` / `apt install libreoffice` / `dnf install libreoffice` | `docx_accept_changes`, `xlsx_recalc`, `pptx_to_pdf`, `pptx_thumbnails`, `md2pptx --via-marp` |
| **Poppler** (`pdftoppm`, `pdftotext`) | `brew install poppler` / `apt install poppler-utils` / `dnf install poppler-utils` | `pptx_thumbnails` (rasterise PDF to JPEG); diagnostic use in tests |
| **pango / cairo / gdk-pixbuf** | `brew install pango gdk-pixbuf libffi` / `apt install libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libpangoft2-1.0-0 libharfbuzz0b` / `dnf install pango gdk-pixbuf2 cairo libffi` | weasyprint runtime (`md2pdf`) |
| **`node`**, **`npm`** | `brew install node` / `apt install nodejs npm` / `dnf install nodejs npm` | every Node script in docx / pptx / pdf / marp-slide |
| **`python3`** ≥ 3.10 | `pyenv` / system | every Python script |
| **gcc / clang** | Xcode CLT / `apt install build-essential` / Fedora dev tools | only when the AF_UNIX shim has to compile (sandboxed Linux) |

### 10.2 User-level shared cache

| Path | Size | Purpose |
|---|---|---|
| `~/.cache/puppeteer/` | ~1 GB | Chromium binary that `mmdc` drives. Auto-populated on first mermaid render; reused by every skill that has `mmdc` in its `node_modules`. |

**This is invisible to `du -sh skills/`** — the per-skill
`node_modules/puppeteer/` is just a 388 KB JS wrapper. To force a
fresh Chromium download: `rm -rf ~/.cache/puppeteer`.

### 10.3 Per-skill bundled (created by `install.sh`)

Each skill's `scripts/` directory holds its own self-contained
runtime — no top-level shared `.venv` or `node_modules`. Both are
gitignored and never committed.

| Skill | `node_modules` | `.venv` | Total |
|---|---:|---:|---:|
| docx | ~110 MB (8 deps) | ~29 MB (3 deps) | ~140 MB |
| xlsx | — (no Node deps) | ~100 MB (incl. pandas + numpy) | ~100 MB |
| pptx | ~92 MB (4 deps) | ~42 MB (3 deps) | ~135 MB |
| pdf | ~86 MB (1 dep: mmdc) | ~98 MB (5 deps incl. weasyprint+reportlab) | ~185 MB |
| marp-slide | ~435 MB (marp-cli + mmdc) | ~6 MB | ~440 MB |
| **Repo total** | | | **~1 GB** |

#### Per-skill Node dependencies

| Skill | Top-level deps (from `package.json`) |
|---|---|
| docx | `docx`, `mammoth`, `turndown`, `turndown-plugin-gfm`, `marked`, `jszip`, `image-size`, `@mermaid-js/mermaid-cli` |
| xlsx | *(no `package.json`)* |
| pptx | `pptxgenjs`, `marked`, `image-size`, `@mermaid-js/mermaid-cli` |
| pdf | `@mermaid-js/mermaid-cli` |
| marp-slide | `@marp-team/marp-cli`, `@mermaid-js/mermaid-cli` |

`@mermaid-js/mermaid-cli` is pinned to **`^11.4.0`** across all
skills (was a `^10.9.0` / `^11.4.0` split earlier — aligned 2026-04-25
to share a single Chromium revision in `~/.cache/puppeteer`).

#### Per-skill Python dependencies

| Skill | `requirements.txt` |
|---|---|
| docx | `python-docx`, `lxml`, `defusedxml`, `Pillow`, `msoffcrypto-tool` |
| xlsx | `openpyxl`, `pandas`, `lxml`, `defusedxml`, `Pillow`, `msoffcrypto-tool` |
| pptx | `python-pptx`, `Pillow`, `lxml`, `defusedxml`, `msoffcrypto-tool` |
| pdf | `pypdf`, `pdfplumber`, `weasyprint`, `markdown2`, `reportlab` |

`msoffcrypto-tool>=5.4.0` is the cross-7 dependency (set/remove
password protection) and lives in the three OOXML skills only — pdf
uses pypdf's own encryption. `lxml` (~19 MB) appears in three of
four .venv directories; `Pillow` (~14 MB) appears in three. Per-skill
duplication is
**intentional** — each skill must work as a standalone `.skill`
archive, so unifying into a shared venv is explicitly out of
scope (see [CONTRIBUTING.md](../CONTRIBUTING.md)).

### 10.4 What's NOT bundled (and why)

- **Chromium** — too heavy (~1 GB), too tied to puppeteer's version
  matrix; auto-downloaded to `~/.cache/puppeteer/` on first use.
- **System tools** (LibreOffice, Poppler, pango/cairo, build
  toolchains) — can't reasonably install via `npm` or `pip`; we
  probe and instruct.
- **XSD schemas** for OOXML — not in the repo, fetched via
  `office/schemas/fetch.sh` when the strict-validation path is
  exercised. Avoids redistributing ECMA-376 binaries.
- **Mermaid config customisation** — only one bundled
  `mermaid-config.json` per skill (Cyrillic-friendly, mirrored
  byte-identical between `pdf` and `pptx`); users supply their own
  via `--mermaid-config`.

### 10.5 Cleanup recipes

```bash
# Reset one skill back to a fresh install:
cd skills/<skill>/scripts
rm -rf .venv node_modules
bash install.sh

# Reset every skill at once:
for s in docx xlsx pptx pdf marp-slide; do
    rm -rf skills/$s/scripts/.venv skills/$s/scripts/node_modules
done

# Force a fresh Chromium download:
rm -rf ~/.cache/puppeteer
# Next mmdc invocation will redownload.

# Sanity-check the office/ replication contract before any change:
diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
diff -qr skills/docx/scripts/office skills/pptx/scripts/office
# Both should print nothing (after `__pycache__` cleanup).
```

---

## 11. Where to look when something breaks

| Symptom | Most likely place |
|---|---|
| `soffice not found` | Install LibreOffice (see §2 system tools) |
| `pdftoppm not found` | Install Poppler (see §2) |
| weasyprint `cannot load library 'libpango-1.0-0'` | Install pango/cairo (see §2) |
| `mmdc not found` warning from md2pdf | `(cd skills/pdf/scripts && npm install)` to fetch `@mermaid-js/mermaid-cli` locally, or `npm i -g @mermaid-js/mermaid-cli` for system-wide |
| `appears to be either password-protected OR a legacy format` (exit 3) | The input file is a CFB container. Either remove its password upstream (`msoffcrypto-tool`, office app) or convert from `.doc`/`.xls`/`.ppt` to OOXML via `soffice --headless --convert-to docx INPUT` |
| `--check` on PDF returns 11 / 12 | 11 = XFA form (re-author as AcroForm or use commercial tooling); 12 = no fillable fields (use the visual-overlay path documented in [pdf/references/forms.md](../../skills/pdf/references/forms.md)) |
| Mermaid diagram in PDF shows coloured rectangles with no text | Old issue with SVG path; fixed by switching to PNG render. Delete `<output_stem>_assets/` and re-run `md2pdf.py`. Cyrillic / CJK fonts need `mmdc` (Chromium) which has system fonts |
| `pptx_clean` removes a part you wanted to keep | The part is unreachable from `<p:sldIdLst>` via `.rels` graph. Add an explicit relationship (e.g. via `_rels/.rels` for top-level customXml) before re-running. Use `--dry-run` first to inspect |
| LibreOffice fails to start in container | See [shim docs](../../skills/docx/scripts/office/tests/test_shim.md); shim auto-detects, but verify with `LO_SHIM_VERBOSE=1` |
| Diff `office/` between docx and xlsx/pptx | Run replication protocol from [CONTRIBUTING.md §3](../CONTRIBUTING.md#3-office-skills-modification-protocol-strict) |
| `validate.py --compare-to` reports unexpected unmarked edits | Check `references/tracked-changes.md` in the docx skill; possibly an editor saved without Track Changes — that's exactly what the validator catches |
| md2pptx output text overlaps title | Adjust title length or pass an explicit `--theme theme.json` with smaller heading sizes |

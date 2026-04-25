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
node skills/docx/scripts/docx2md.js INPUT.docx OUTPUT.md
```

Produces a sibling `OUTPUT_images/` directory if the source contains
embedded media. Uses mammoth (HTML conversion) + turndown (HTML → MD)
internally.

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
    [--size 16:9|4:3] [--theme theme.json]
```

pptxgenjs-based renderer. Auto-paginates dense slides, mermaid
blocks render to PNG via local `mmdc`, adaptive font sizing for
high-density slides, accent colour stripe on every slide.

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

The shared `office/` module has 13 unit tests under
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
| docx | `md2docx → docx → docx2md` round-trip, `office.validate` on output, `docx_fill_template` with nested JSON, encryption / legacy-CFB rejection on `docx_fill_template` and `docx_accept_changes`. |
| xlsx | `csv2xlsx` + row count + `office.validate`, `xlsx_validate` (clean + injected `#DIV/0!` via lxml mutation), `xlsx_recalc` formula preservation, `xlsx_add_chart` (bar/line/pie variants + bad-range error), encryption rejection on `xlsx_validate`/`xlsx_add_chart`/`xlsx_recalc`. |
| pptx | `md2pptx` + slide-count + `office.validate`, `pptx_thumbnails` (JPEG sanity), `pptx_to_pdf` (`%PDF` magic), `pptx_clean` (orphan slide + media removal, dry-run reports without writing), `outline2pptx` (heading-only MD → 4 slides + validate + heading-less input fails clearly), bundled `mermaid-config.json` (parses, missing path fails clean), encryption rejection on `pptx_clean`/`pptx_thumbnails`/`pptx_to_pdf`. |
| pdf | `md2pdf` + mermaid PNG render + bundled `mermaid-config.json` (parses, missing path warns, config change invalidates PNG cache), `pdf_merge` (page-count = sum), `pdf_split --each-page`, `pdf_fill_form` (`--check` exit codes, fill round-trip, `--flatten` removes `/AcroForm`, `--extract-fields` stdout, malformed JSON / missing `-o` exit 2, typo'd field warning, int→`/Yes` checkbox coercion). |

The suite is fast (<60 sec total on a warm machine) and is the
primary pre-commit / pre-release gate. Any failure here points at a
broken user-facing contract.

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

---

## 9.5. Cross-skill safeguards (cross-1 / 4 / 5)

Three features cut across all four office skills and were intentionally
designed for uniformity:

### `--json-errors` (cross-5)

Every Python CLI accepts `--json-errors`. When set, failures are
emitted as a single line of JSON on stderr:

```json
{"error": "Input not found: /nope.pdf", "code": 1, "type": "FileNotFound", "details": {"path": "/nope.pdf"}}
```

Plain mode (the default) is unchanged free-form text, so existing
shell pipelines do not break. Wrappers and CI runners gain one parser
that works for every script.

The helper lives at `scripts/_errors.py`, byte-identical in all four
skills (replication protocol in [`CLAUDE.md` §2](../../CLAUDE.md)).

### Macro-enabled file detection (cross-4)

`office/_macros.py` provides `is_macro_enabled_file(path)` — checks
either `vbaProject.bin` in the ZIP namelist or a `macroEnabled`
content-type in `[Content_Types].xml`. Used by:

- `docx_fill_template.py`, `docx_accept_changes.py`,
  `xlsx_recalc.py`, `xlsx_add_chart.py`, `pptx_clean.py`: stderr
  warning when the input is `.docm`/`.xlsm`/`.pptm` and the chosen
  output extension drops the macros (`.docx`/`.xlsx`/`.pptx`). The
  warning suggests the matching macro extension instead.
- `office/unpack.py`: prints a one-line note when the input is
  macro-enabled, so power users repacking from the unpacked tree
  know to keep the `m` in the extension.
- `office/pack.py`: walks the unpacked tree for `vbaProject.bin` and
  warns if the chosen output extension drops it.

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
    [--label-font-size 14] [--json-errors]
```

The label changes per file type — "Page" for docx/pdf, "Sheet" for
xlsx, "Slide" for pptx — picked from the input's extension.

Why a single CLI in four places: each skill must remain independently
installable as a `.skill` archive, but a user who only has the `pdf`
skill should still be able to preview a colleague's `.pptx`. Shipping
the same file in all four locations is cheap (~6 KB each) and avoids
forcing users to install multiple skills just to render previews.

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
| docx | `python-docx`, `lxml`, `defusedxml` |
| xlsx | `openpyxl`, `pandas`, `lxml`, `defusedxml` |
| pptx | `python-pptx`, `Pillow`, `lxml`, `defusedxml` |
| pdf | `pypdf`, `pdfplumber`, `weasyprint`, `markdown2`, `reportlab` |

`lxml` (~19 MB) appears in three of four .venv directories;
`Pillow` (~14 MB) appears in two. Per-skill duplication is
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

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
| **xlsx** | CSV/JSON → styled `.xlsx`, recalc formulas, scan errors | `csv2xlsx.py`, `xlsx_recalc.py`, `xlsx_validate.py` |
| **pptx** | Markdown → `.pptx`, generate thumbnails, convert to PDF | `md2pptx.js` (incl. `--via-marp`), `pptx_to_pdf.py`, `pptx_thumbnails.py` |
| **pdf** | Markdown → PDF, merge, split | `md2pdf.py`, `pdf_merge.py`, `pdf_split.py` |

All four are licensed Apache-2.0; runtime deps and external-tool
attributions are in [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).

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

---

## 6. pdf — common workflows

### 6.1 Markdown → PDF

```bash
./.venv/bin/python skills/pdf/scripts/md2pdf.py doc.md doc.pdf \
    [--page-size letter|a4|legal] [--css extra.css]
```

Uses weasyprint. Default stylesheet includes proper `@page` margins
and footer page numbers.

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

The office-shared module has 13 unit tests under
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
the test suite stays only in `docx`; xlsx and pptx receive byte-
identical copies of `office/` (which includes the tests), but the
tests are typically run from the docx skill since that's the
master.

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

## 10. Where to look when something breaks

| Symptom | Most likely place |
|---|---|
| `soffice not found` | Install LibreOffice (see §2 system tools) |
| `pdftoppm not found` | Install Poppler (see §2) |
| weasyprint `cannot load library 'libpango-1.0-0'` | Install pango/cairo (see §2) |
| LibreOffice fails to start in container | See [shim docs](../../skills/docx/scripts/office/tests/test_shim.md); shim auto-detects, but verify with `LO_SHIM_VERBOSE=1` |
| Diff `office/` between docx and xlsx/pptx | Run replication protocol from [CONTRIBUTING.md §3](../CONTRIBUTING.md#3-office-skills-modification-protocol-strict) |
| `validate.py --compare-to` reports unexpected unmarked edits | Check `references/tracked-changes.md` in the docx skill; possibly an editor saved without Track Changes — that's exactly what the validator catches |
| md2pptx output text overlaps title | Adjust title length or pass an explicit `--theme theme.json` with smaller heading sizes |

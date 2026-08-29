# PDF → Markdown

Converting a PDF to Markdown is a frequent request. There is **no script that
does it end-to-end**, on purpose: a PDF is positioned glyphs with no semantic
model — heading levels, reading order, and where one table ends are *inferred*,
not stored. That inference is LLM judgement. This reference standardises the
*approach* so the result is consistent, and `pdf_extract.py` removes the most
common silent failure (scanned PDFs). **Assembling the final Markdown is your
job, not a script's.**

---

## 1. Decision tree — which path to take

Classify the PDF first; do not guess.

```
Is the PDF born-digital (has a real text layer)?
│
├─ YES, simple layout (single column, ruled tables)
│     → pdfplumber per-page extraction.
│       Run:  python3 scripts/pdf_extract.py INPUT.pdf -o dump.json
│       Then compose the Markdown yourself from dump.json.
│
├─ YES, but complex layout (multi-column, rotated text, dense forms)
│     → still pdfplumber, but expect to tune (see §3) — drop to inline
│       pdfplumber code with custom table_settings / extract_text(layout=True).
│
└─ NO — scanned / image-only (no text layer)
      → pdfplumber returns empty text. DO NOT ship that empty result.
        Either: OCR the PDF first with `pdf_ocr.py in.pdf out.pdf` (eng+rus
        searchable PDF; see references/ocr.md), then extract out.pdf — or
        render the pages as images and read them with the Read tool.
        `pdf_extract.py` detects this and exits 10 — see §5.
```

How do you know which branch you are on? Run `pdf_extract.py` — its
`doc_scanned` flag and exit code tell you (§5). You do not have to guess.

---

## 2. Extraction recipe (the digital-PDF branch)

Three steps. Keep them separate — the value is in step 3 being *yours*.

1. **Dump** — extract per page, mechanically:
   - text: `page.extract_text()` (add `layout=True` for column-bearing pages);
   - tables: `page.extract_tables()`.
   `pdf_extract.py` does exactly this and writes a structured JSON dump.

2. **Read the dump** — a per-page intermediate form (`dump.json`): each page's
   raw text and raw tables. This is *data*, not Markdown. Read its three
   content-loss signals before you trust it: `scanned_pages`, `figure_pages`
   and `text_layer_lossy` (§5) each mark content that is **not** in the dump,
   and only the first can also change the exit code.

3. **Compose** — you turn the dump into Markdown: choose heading levels, fix
   reading order, render tables (GFM by default — see §3), stitch a table that
   spans pages, describe an image/diagram in prose. This step is judgement and
   is never scripted.

Run the dump:

```bash
python3 scripts/pdf_extract.py report.pdf -o dump.json
```

When the default table detection misses a table (see §3.2), skip the script for
that table and write inline `pdfplumber` code with tuned `table_settings`.

---

## 3. Pitfalls ("грабли")

### 3.1 Multi-column pages & reading order
`extract_text()` walks the page roughly top-to-bottom; on a two-column page it
interleaves the columns into nonsense. Mitigation: `extract_text(layout=True)`
(or `pdf_extract.py --layout`) preserves column separation as whitespace so you
can *see* the columns and reorder them yourself. The tool does **not** reflow
columns into logical order — that is your step 3. (Word-gluing on these layouts
— `ASurveyonBlockchain` — is a *separate* problem, handled by default; see §3.8.)

**The orphaned list marker.** A second reading-order artefact, independent of
columns: pdfplumber groups characters into lines with an *absolute*
`y_tolerance` of 3 pt. A list marker set in a smaller point size than its body
text (a 7 pt bullet against 10–12 pt text puts the marker's box top ~3–4 pt
lower) falls outside that window, so it becomes its own line — and, having the
larger `doctop`, sorts **after** the item it introduces:

```
Первый пункт списка — текст строки целиком.
●
Второй пункт списка — текст строки целиком.
●
```

This is the Y-axis twin of the X-axis gluing in §3.8, and unlike that one it
cannot be fixed by a ratio: a ratio scales off the marker's own small size
(7 × 0.15 = 1.05 pt, well under the 3.15 pt offset), so the knob is absolute.
Pass `--y-tolerance 5`:

```bash
python3 scripts/pdf_extract.py report.pdf --y-tolerance 5 -o dump.json
```

Measured on a 29-page Google-Docs-Renderer document: `5` reunited **32 of 32**
orphaned markers and left the other 25 pages unchanged byte for byte; on
probe PDFs from WeasyPrint and LibreOffice the output was byte-identical to the
default. It is **not** the default all the same — on a dense layout a raised
tolerance merges genuinely separate lines, and a new default needs a corpus
run, not one document. Raise it when you see orphaned markers; leave it alone
otherwise. The dump echoes the effective value in top-level `y_tolerance`.

### 3.2 Tables without ruling lines
`extract_tables()` defaults to the `lines` strategy — it finds tables drawn
with visible borders. A borderless table (whitespace-aligned) is missed
entirely. Drop to inline code and tune:

```python
import pdfplumber
with pdfplumber.open("report.pdf") as pdf:
    page = pdf.pages[0]
    tables = page.extract_tables(table_settings={
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "snap_tolerance": 4,      # raise if rows/cols are missed
    })
```

**The opposite failure: a table that was never there.** The `lines` strategy
builds table edges from *every* `page.rects` entry — including rectangles that
are `fill=True, stroke=False`, i.e. background shading. Any producer that
paints a highlighted callout, a shaded paragraph, or zebra-striped rows hands
`extract_tables()` phantom edges. Two symptoms, the second much worse than the
first:

- a text page with no table at all returns several "tables" made of its
  shaded paragraphs (measured: 6 phantom tables on one page of a Google Docs
  export, 3 on each neighbour);
- a shaded paragraph sitting under a real table, x-aligned with it, is glued
  on as an **extra row of that table** — text that was never in the table now
  sits inside a structured dump, and nothing says so.

`--table-strategy lines_strict` counts only stroked lines and clears both:

```bash
python3 scripts/pdf_extract.py report.pdf --table-strategy lines_strict
```

Verified across three producers: `lines_strict` removed every phantom while
leaving the real tables intact (Google Docs Renderer, LibreOffice 26.2,
WeasyPrint 68.1). It is **not** the default, because it also drops tables drawn
*purely* with fills and no ruling — a real style. So: default `lines`; switch to
`lines_strict` when a "table" on a text page looks like shading. Confirm which
you are looking at before trusting either — `stroke=False, fill=True` in
`page.rects` is a background, not a border:

```python
[(r["stroke"], r["fill"]) for r in page.rects]   # (False, True) → shading
```

The dump echoes the strategy in top-level `table_strategy`.

Beyond these two knobs `pdf_extract.py` uses default settings — it is a dump,
not a tuning console. Borderless-table tuning is inline-agent work.

### 3.3 A table split across a page boundary
A long table continues on the next page — `extract_tables()` returns it as two
separate tables (one per page), often with the header repeated (or absent) on
the continuation. You must recognise this (same column count, continuation on
the very next page) and **stitch the fragments into one Markdown table**, dropping
a repeated header. No script can know the table is "the same one".

### 3.4 Image-only pages inside a digital PDF
A mostly-digital PDF can still have a scanned page (a signed page, an inserted
figure). `pdf_extract.py` flags it per page (`scanned: true`,
`scanned_pages: [...]`) and warns on stderr. Extract the digital pages; OCR or
visually read the flagged ones.

**A figure page is not a scan.** The `scanned` flag counts characters
*absolutely* (≤ 10, see §6), so a page whose entire content is one architecture
diagram slips past it the moment the page carries a running header — a
confidentiality stamp plus a page number is 30–70 characters, and corporate
specs, reports and whitepapers (exactly the documents that contain diagrams)
practically all have one. That page arrives looking like an ordinary text page
holding a single line of boilerplate, and the diagram is silently gone.

A second, independent per-page signal covers it: **`figure_dominant`**, true
when the page's painted area — `image_coverage` (rasters) plus
`vector_coverage` (clustered path artwork) — reaches **0.25** *and* its
stripped character count is under **200**. Affected pages are listed in
top-level `figure_pages` with an stderr warning. Both halves of the test are
load-bearing, and both were measured:

| Page | Coverage | Chars | Verdict |
|---|---|---|---|
| Raster architecture diagram under a header | 56 % raster | 62 | figure |
| Vector diagram, **zero** images | 31 % vector | 117 | figure — a raster-only signal misses this one |
| Screenshot beside live prose | 15–23 % | 1459–1943 | not a figure |
| Ruled table page | 42–85 % vector (the ruling) | ≫ 200 | not a figure — only the char cap saves it |

Note the last row: table ruling clusters into most of a sheet, so without the
character cap the signal would fire on 24 of 29 pages of a perfectly healthy
document.

`figure_dominant` and `scanned` are **disjoint** — a scanned page is never also
`figure_dominant`. They name the same loss with different repairs: OCR for a
scan, image extraction or a visual read for a figure. Neither `doc_scanned` nor
the exit code changes for a figure page; exit `10` means "the whole document is
a scan" and that contract is public (§5).

What to do with a flagged page: the flag says content is missing, it does not
supply it. Pull the image out of the page (or render the page and read it) and
write a prose description or an embedded image into your Markdown — a flagged
page left unhandled is still a hole in the output.

### 3.5 Headings
PDF has no `<h1>`. Heading level is inferred from font size / weight / position
— and that inference is yours. `pdf_extract.py` does not guess heading levels;
it gives you the text, you assign `#` / `##` / `###` by judgement.

### 3.6 Encrypted PDFs
An encrypted PDF yields empty content from most libraries *without raising*.
`pdf_extract.py` detects encryption and fails loudly (`EncryptedPDF`, exit 1);
pass `--password PW` if you have it. See
[library-selection.md](library-selection.md) "Encrypted PDFs" for the
`is_encrypted` check when writing inline code.

### 3.7 Table dialect
Default to **GFM pipe tables** in the composed Markdown. Use an HTML `<table>`
only when a table genuinely needs `colspan` / `rowspan` that GFM cannot express.
The choice is yours per table.

### 3.8 Glued words (LaTeX / academic PDFs with no space glyphs)
Many born-digital PDFs — LaTeX two-column papers especially — encode inter-word
spacing as *positional gaps*, not space characters. pdfplumber's default
*absolute* `x_tolerance` (3 pt) is larger than those sub-3-pt gaps, so it glues
the whole line: `ASurveyonBlockchainInteroperability`. `pdf_extract.py` fixes
this **by default** with a *font-relative* threshold (pdfplumber's
`x_tolerance_ratio`, default `0.15` → the split gap scales with font size). This
is byte-identical to the old behaviour on PDFs that use real spaces (a space
glyph always splits a word), so normal documents are unaffected; the dump echoes
the effective ratio in its top-level `x_tolerance_ratio` field.

If a specific PDF still glues (rare — gaps tighter than `0.15 × font_size`) or
*over*-splits (loose tracking with no spaces), tune `--x-tolerance-ratio R`:
lower R splits more aggressively, higher R glues more; `--x-tolerance-ratio 0`
disables it entirely (restores pdfplumber's absolute tolerance). Empirically
`0.10–0.20` is the safe band for academic layouts; `≥0.25` starts re-gluing.

```bash
python3 scripts/pdf_extract.py paper.pdf -o dump.json            # fix on (0.15)
python3 scripts/pdf_extract.py paper.pdf --x-tolerance-ratio 0.1 # split harder
python3 scripts/pdf_extract.py paper.pdf --x-tolerance-ratio 0   # legacy/off
```

### 3.9 Non-Latin text that is not in the file at all
A producer that embeds no fonts and addresses them through a single-byte Latin
encoding (base-14 `Helvetica`/`Courier` + `WinAnsiEncoding`) **cannot** write a
Cyrillic, Greek or CJK code point. Asked to, it drops the character while
writing the file. The damage is done at export time, before any extraction:
the content stream carries spaces where the words were.

The result is the most dangerous kind of dump — a healthy-looking one. Latin
text, digits, URLs and code come through perfectly, `exit 0`, thousands of
characters, `doc_scanned: false`. Compose Markdown from it and you ship an
English skeleton of a Russian document: headings without words, empty ToC
entries, no prose. Some producers make it worse by substituting a placeholder
glyph, so the missing words come back as plausible-looking runs
(`nnnnnn 1. nnnnn`) that no statistic over the text can tell from prose.

Because of that, the check is on **font metadata**, never on how the text
looks. `pdf_extract.py` reports every distinct font in the document —

```json
"fonts": [{"name": "Helvetica", "subtype": "Type1", "embedded": false,
           "encoding": "WinAnsiEncoding", "has_tounicode": false}]
```

— and sets **`text_layer_lossy: true`** when the document yields some text AND
no font is embedded AND no font carries `/ToUnicode` AND every encoding is
single-byte Latin. Under those conditions the file physically cannot hold
another alphabet: the verdict is deterministic, with no threshold. The exit
code is unchanged (stderr warning only) for the same reason as §3.4.

Two consequences worth keeping straight:

- **OCR does not fix this.** The glyphs were never drawn — Poppler renders those
  places blank. OCR would only recover text that lives inside raster
  illustrations. The repair is re-exporting the source with embedded fonts;
  if you cannot, say so rather than shipping the skeleton.
- **The flag is a capability, not a proof.** It says the file cannot represent
  non-Latin text, not that some was lost — what was lost is unknowable from the
  file, which is precisely why the signal has to exist. A genuinely Latin-only
  document trips it too, harmlessly.

Check it yourself on any PDF you did not produce:

```bash
python3 -c "
import pypdf
r = pypdf.PdfReader('doc.pdf')
for pg in r.pages:
    for k, v in ((pg.get('/Resources') or {}).get('/Font') or {}).items():
        o = v.get_object()
        print(o.get('/BaseFont'), o.get('/Encoding'), '/ToUnicode' in o)
"
```

`WinAnsiEncoding` + `False` everywhere, in a document that ought to be
non-Latin, means the dump cannot be trusted.

---

## 4. The final Markdown is the agent's job — and the Non-goals

The composition step (§2 step 3) is **never scripted**:

- No `pdf2md.py`. There is deliberately no script that promises "PDF → finished
  Markdown". `pdf_extract.py` is named honestly — it *extracts a dump*, it does
  not *convert*.
- No bundled OCR. Scanned PDFs are *detected* and you are *pointed at* OCR; OCR
  is not part of this skill.
- No auto-inference of heading hierarchy, reading order, or table stitching.

Why does `.docx` get a `docx-to-md` script but PDF does not? A `.docx` has a
real semantic model — headings, lists, and tables are tagged in the XML, so a
deterministic converter is justified. A PDF is positioned glyphs with no such
model; a "magic PDF→MD converter" would silently guess and silently be wrong.
Consistency + honest tooling beats a converter that lies.

---

## 5. `pdf_extract.py` — usage and the scan signal

```
python3 scripts/pdf_extract.py INPUT.pdf [-o OUT.json] [--layout]
                               [--password PW] [--x-tolerance-ratio R]
                               [--y-tolerance PT] [--table-strategy S]
                               [--json-errors]
```

Output — a structured JSON **dump** (not Markdown):

```json
{
  "page_count": 12,
  "doc_scanned": false,
  "scanned_pages": [],
  "figure_pages": [4],
  "text_layer_lossy": false,
  "x_tolerance_ratio": 0.15,
  "y_tolerance": null,
  "table_strategy": "lines",
  "fonts": [{"name": "ABCDEF+NotoSans", "subtype": "Type0",
             "embedded": true, "encoding": "Identity-H",
             "has_tounicode": true}],
  "pages": [
    {"n": 1, "text": "...", "tables": [[["a","b"],["c",null]]],
     "char_count": 412, "has_images": false,
     "image_coverage": 0.0, "vector_coverage": 0.0,
     "scanned": false, "figure_dominant": false}
  ]
}
```

The four knob fields echo the *effective* settings (`null` = pdfplumber's own
default), so a dump always says how its words, lines and table edges were
derived.

**Read three signals before composing, not one.** Only `doc_scanned` changes
the exit code; the other two are stderr warnings at exit `0`, and each means
content is missing from the dump you are about to turn into Markdown:

| Signal | Means | What you do |
|---|---|---|
| `scanned_pages` | those pages are image-only | OCR them, or read them as images (§3.4) |
| `figure_pages` | those pages are mostly artwork with too little text to be text pages | extract the image or read the page; describe it in the Markdown (§3.4) |
| `text_layer_lossy` | the file's fonts cannot represent a non-Latin alphabet, so any it had was destroyed at export | re-export the source with embedded fonts — **OCR will not help** (§3.9) |

Exit codes — the loud scan signal lives here:

| Code | Meaning | What you do |
|------|---------|-------------|
| `0`  | Success — dump emitted | Compose the Markdown from the dump. |
| `1`  | Input missing / not a PDF / corrupt / encrypted-without-password | Fix the input; pass `--password` if encrypted. |
| `2`  | Usage error | Fix the command line. |
| `10` | `DocumentScanned` — the whole document is image-only | **Do not ship empty output.** OCR the PDF (`ocrmypdf`) or read its pages as images with the Read tool. |

The dump is written to stdout (or `-o`) on every path, including exit 10 — the
non-zero exit + stderr message is the signal, not output suppression.
`--json-errors` puts the failure on stderr as one JSON line; stdout always
carries the dump.

`figure_pages` and `text_layer_lossy` deliberately do **not** get exit codes of
their own. Exit `10` means "the whole document is a scan, go and OCR it", and
that mapping is a public contract other tooling keys off; a page-level or
font-level signal is a different failure with a different repair. Adding a code
would be a separate, deliberate decision.

---

## 6. Why the scan threshold is 10 characters

`pdf_extract.py` marks a page `scanned` when its stripped extractable-character
count is at or below **10** *and* the page carries an image. The threshold is
`10` rather than `0` to tolerate the occasional digitally-stamped page number
or Bates number on an otherwise image-only page. A digital page with genuine
content essentially always exceeds 10 stripped characters, and the dual
`has_images` condition keeps a sparse digital page from being misread as
scanned. A genuinely image-only page has no characters at all — it scores 0
under both default and `--layout` extraction. `doc_scanned` is true only when
at least one page is scanned *and* no page yields meaningful text; an all-blank
PDF (zero scanned pages) is never `doc_scanned`.

That threshold is why a page holding one diagram plus a running header is not
`scanned` — 30–70 characters of boilerplate clears it easily. Raising the
threshold is the wrong repair: it would start calling genuine text pages with a
short caption "scans". The right measure there is painted area, which is what
`figure_dominant` uses instead (§3.4).

---

## 7. Extracted content is untrusted

Text and table cells pulled from a PDF are arbitrary strings — they may contain
Markdown or HTML metacharacters (`|`, `*`, `<script>`, `[x](javascript:...)`).
When you compose the Markdown, treat cell/text content as data: escape pipes in
GFM table cells, do not paste a cell value into a raw HTML context unescaped.
`pdf_extract.py` itself emits JSON only (every string safely escaped) and
renders no Markdown — the escaping responsibility is yours, in the composition
step.

---

## 8. See also

- [library-selection.md](library-selection.md) — which PDF library for which
  task; the `is_encrypted` check for inline extraction code.
- [forms.md](forms.md) — AcroForm vs XFA, for PDFs that are forms rather than
  documents.

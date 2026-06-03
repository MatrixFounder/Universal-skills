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
   raw text and raw tables. This is *data*, not Markdown.

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
columns into logical order — that is your step 3.

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

`pdf_extract.py` uses default settings only — it is a dump, not a tuning
console. Borderless-table tuning is inline-agent work.

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
                               [--password PW] [--json-errors]
```

Output — a structured JSON **dump** (not Markdown):

```json
{
  "page_count": 12,
  "doc_scanned": false,
  "scanned_pages": [],
  "pages": [
    {"n": 1, "text": "...", "tables": [[["a","b"],["c",null]]],
     "char_count": 412, "has_images": false, "scanned": false}
  ]
}
```

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

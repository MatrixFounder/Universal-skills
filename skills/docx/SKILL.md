---
name: docx
description: Use when the user asks to create, edit, convert, or validate Microsoft Word .docx documents. Triggers include "markdown to docx", "docx to markdown", "fill this Word template", "accept tracked changes", "unpack docx XML", "extract text from docx", and related .docx round-trip or template-fill tasks.
tier: 2
version: 1.0
license: LicenseRef-Proprietary
---
# docx skill

**Purpose**: Give the agent a deterministic, script-first way to create,
edit, and convert Microsoft Word `.docx` files so it does not have to
re-derive low-level OOXML constructs (page sizes, tables, tracked
changes, comment markers, image embeddings, template substitution) on
every task. Writing `.docx` by hand through `docx-js` or `python-docx`
calls is feasible but error-prone; the scripts here encode the
practical knowledge and make the common operations a single command.

## 1. Red Flags (Anti-Rationalization)

**STOP and READ THIS if you are thinking:**
- "I'll just assemble the docx inline with `docx-js` calls, the scripts are overkill." → **WRONG**. `md2docx.js` already handles page size, numbering, dual-width tables, and image alt-text — regressions from hand-rolled code usually show as silently broken tables or images on Word for Windows.
- "I can skip `docx_fill_template.py`'s run-merge pass and just regex-replace `{{placeholder}}`." → **WRONG**. Word and Google Docs fracture a single placeholder across multiple `<w:r>` siblings after spell-check or autocorrect; a naïve regex won't match and the placeholder will ship unfilled.
- "For tracked changes I'll just delete every `<w:del>` block." → **WRONG**. That loses author attribution and breaks paragraph-level delete markers. Use `docx_accept_changes.py` which drives LibreOffice's own accept dispatcher.
- "The smart-quote entity rewrite in `office/unpack.py` is ugly, I'll turn it off." → **WRONG**. Different Word builds round-trip UTF-8 quotes inconsistently. Keeping them as `&#x2019;` etc. on unpack and reversing on pack makes edits deterministic.

## 2. Capabilities
- Convert Markdown to `.docx` with headings, lists, tables, images, and optional mermaid diagrams via `md2docx.js`.
- Extract `.docx` content back to Markdown preserving tables, lists, and embedded images via `docx2md.js`.
- Fill `.docx` templates containing `{{placeholder}}` or `{{nested.key}}` markers from a JSON payload with safe run-merging.
- Accept all tracked changes in a `.docx` via headless LibreOffice without leaving artefacts in the user's profile.
- Unpack and repack `.docx` archives for raw OOXML editing, with smart-quote entity round-tripping and run canonicalisation.
- Structurally validate a `.docx`: relationships, content types, tracked-change/`<w:delText>` integrity, comment marker pairing, and optional XSD binding.
- Reject password-protected and legacy `.doc` (CFB-container) inputs early with a clear remediation message (exit 3) instead of a `BadZipFile` traceback.
- Detect macro-enabled inputs (`.docm`, with `vbaProject.bin`) and warn when the chosen output extension would silently drop the macros (`docm` → `docx`).
- Render any `.docx`/`.docm`/`.pdf` (or peer-skill `.xlsx`/`.pptx`) into a single PNG-grid preview via `preview.py` (LibreOffice + Poppler).
- Emit failures as machine-readable JSON to stderr with `--json-errors` (uniform across all four office skills).

## 3. Execution Mode
- **Mode**: `script-first`.
- **Why this mode**: Each operation is a small, deterministic CLI wrapping a specific OOXML-aware library. Inline assembly in the agent's text is slower and regresses on details (page size, DXA units, namespace ordering). Scripts also make the skill reusable from any shell environment.

## 4. Script Contract

- **Commands**:
  - `node scripts/md2docx.js INPUT.md OUTPUT.docx [--header "TEXT"] [--footer "TEXT"]`
  - `node scripts/docx2md.js INPUT.docx OUTPUT.md`
  - `python3 scripts/docx_fill_template.py TEMPLATE.docx DATA.json OUTPUT.docx [--strict]`
  - `python3 scripts/docx_accept_changes.py INPUT.docx OUTPUT.docx [--timeout 120]`
  - `python3 scripts/office/unpack.py INPUT.docx OUTDIR/ [--no-pretty] [--no-escape-quotes] [--no-merge-runs]`
  - `python3 scripts/office/pack.py INDIR/ OUTPUT.docx [--no-unescape-quotes] [--no-condense]`
  - `python3 scripts/office/validate.py INPUT.docx [--strict] [--json] [--schemas-dir PATH] [--compare-to ORIGINAL.docx]`
  - `python3 scripts/preview.py INPUT OUTPUT.jpg [--cols 3] [--dpi 110] [--gap 12] [--padding 24] [--label-font-size 14]`
  - All scripts above accept `--json-errors` to emit failures as a single line of JSON on stderr (`{error, code, type?, details?}`).
- **Inputs**: positional paths only; optional flags per command.
- **Outputs**: a single file at the named output path; `office/unpack.py` produces a directory tree; `office/validate.py` prints a report (or JSON with `--json`). `docx2md.js` additionally creates `<stem>_images/` next to the Markdown output when the document has embedded images.
- **Failure semantics**: non-zero exit on missing input, invalid JSON, unresolved placeholders (with `--strict`), unreadable ZIP, or soffice errors. Error detail goes to stderr.
- **Idempotency**: repeated runs with the same inputs produce equivalent output files (byte-exact for the XML parts after pretty-print and entity normalisation). `docx_accept_changes.py` is idempotent on an already-accepted document.
- **Dry-run support**: not applicable; operations are file-to-file and reversible by re-running.

## 5. Safety Boundaries
- **Allowed scope**: only the input/output paths named on the command line and, for Python scripts, modules under `scripts/`. Never modify files the user did not name.
- **Default exclusions**: never overwrite the input in place unless the same path is also passed as output; never fetch remote images silently; never install npm/pip packages globally.
- **Destructive actions**: `docx_accept_changes.py` rewrites the destination; always use a distinct output path unless the user explicitly asks for in-place replacement. `office/pack.py` overwrites the destination archive.
- **Optional artifacts**: the `office/schemas/` directory is optional; `office/validate.py` runs structural checks without it and only warns about missing XSDs unless `--strict`.

## 6. Validation Evidence
- **Local verification**:
  - `cd skills/docx/scripts && npm install` — installs docx, marked, mammoth, turndown, image-size, turndown-plugin-gfm into `scripts/node_modules/`.
  - `python3 -m venv .venv && source .venv/bin/activate && pip install -r scripts/requirements.txt` — installs python-docx, lxml, defusedxml.
  - `node scripts/md2docx.js examples/fixture-simple.md /tmp/out.docx && unzip -l /tmp/out.docx | grep word/document.xml` — exits 0 and lists the document part.
  - `node scripts/docx2md.js /tmp/out.docx /tmp/back.md && test -s /tmp/back.md` — round-trips non-empty Markdown.
  - `python3 scripts/office/validate.py /tmp/out.docx` — exits 0, prints `OK` or only warnings.
  - `python3 scripts/office/unpack.py /tmp/out.docx /tmp/unpacked && python3 scripts/office/pack.py /tmp/unpacked /tmp/repack.docx && unzip -p /tmp/repack.docx word/document.xml | head -c 100` — unpack/pack round trip.
- **Expected evidence**: `/tmp/out.docx`, `/tmp/back.md`, `/tmp/unpacked/` tree, `/tmp/repack.docx`. All reproducible from `examples/fixture-simple.md`.
- **CI signal**: `python3 ../../.claude/skills/skill-creator/scripts/validate_skill.py skills/docx` — exits 0 when the skill conforms to the Gold Standard (frontmatter, required sections, non-empty examples).

## 7. Instructions

Use graduated language: steps marked **MUST** are safety-critical; the
rest are behavioural defaults with their rationale.

### 7.1 Select the right script before touching low-level APIs

1. **Look up the task in §10 Quick Reference first.** If a script exists, run it — it captures accumulated OOXML knowledge that inline code tends to get wrong.
2. Drop to `docx-js` or `python-docx` calls only when the user's requirement genuinely is not covered (e.g. inserting a custom content control, manipulating a specific style's inheritance chain).

### 7.2 Install dependencies locally

1. **MUST** run `bash scripts/install.sh` once. It creates `scripts/.venv/` and `scripts/node_modules/` locally (nothing installed globally), prints a warning for any missing system tool, and is idempotent.
2. **External system tools** (checked by `install.sh`, installed manually per project plan §3.3 "внешние инструменты — не бандлятся"):
   - **LibreOffice** (`soffice`) — required by `docx_accept_changes.py`. macOS: `brew install --cask libreoffice`. Debian: `sudo apt install libreoffice --no-install-recommends`. Fedora: `sudo dnf install libreoffice`.
   Commands that need it fail with a clear error until it's installed.

### 7.3 Creating `.docx` from Markdown

1. Prefer `md2docx.js` over hand-writing `new Document({...})`.
2. When the user specifies US Letter, pass the `--size letter` flag (the script defaults to A4). Landscape needs `--size letter --landscape` — page dimensions are passed unswapped; the orientation flag tells Word how to render them.
3. For headers/footers use `--header "…"` / `--footer "…"`. Multi-line headers are a single string with `\n` — `md2docx.js` splits on the newline.

### 7.4 Extracting text from `.docx` to Markdown

1. Use `docx2md.js` for GFM output with tables preserved. If the document contains images, a sibling `<stem>_images/` directory is created — tell the user so they know to ship it alongside the Markdown.
2. For plain text without any formatting, `pandoc -t plain` is a valid alternative but external — document this choice to the user rather than silently switching tools.

### 7.5 Filling a template

1. **MUST** ensure the template contains placeholders in the exact form `{{key}}` or `{{nested.key}}`. Spaces inside the braces (`{{ key }}`) are tolerated; anything else (`[key]`, `${key}`, `<%=key%>`) is not recognised.
2. Provide `data.json` as an object at the top level.
3. Pass `--strict` when the template *must* be fully resolved (legal documents, customer-facing letters). Without `--strict`, unresolved placeholders remain in the output and are listed on stderr.

### 7.6 Accepting tracked changes

1. `docx_accept_changes.py` requires LibreOffice. Check `_soffice.py` locates it before telling the user it "just works" — on some CI images LibreOffice is absent.
2. Output must be a new path; do not overwrite the input unless asked. Even then, prefer an intermediate file and move on success.

### 7.7 Raw OOXML editing

1. `python3 scripts/office/unpack.py doc.docx work/` first — this pretty-prints, merges adjacent runs, and entity-encodes smart quotes, so editing is safe.
2. Edit XML under `work/word/`, `work/ppt/`, or `work/xl/` (docx/pptx/xlsx respectively).
3. `python3 scripts/office/pack.py work/ out.docx` repackages and reverses the smart-quote entities.
4. `python3 scripts/office/validate.py out.docx` confirms basic structural sanity before shipping.

## 8. Workflows (Optional)

Create a new document from Markdown:

```markdown
- [ ] Prepare input.md (YAML frontmatter optional)
- [ ] `cd scripts && npm install` if first run
- [ ] `node scripts/md2docx.js input.md output.docx`
- [ ] `python3 scripts/office/validate.py output.docx`
- [ ] Open in Word/LibreOffice for a spot-check
```

Round-trip an existing document:

```markdown
- [ ] `node scripts/docx2md.js input.docx extracted.md`
- [ ] Edit `extracted.md`
- [ ] `node scripts/md2docx.js extracted.md back.docx`
- [ ] `python3 scripts/office/validate.py back.docx`
```

Fill a template with JSON data:

```markdown
- [ ] Prepare template.docx with `{{placeholders}}`
- [ ] Prepare data.json matching the placeholder keys
- [ ] `python3 scripts/docx_fill_template.py template.docx data.json out.docx --strict`
- [ ] Confirm no unresolved placeholders on stderr
```

## 9. Best Practices & Anti-Patterns

| DO THIS | DO NOT DO THIS |
| :--- | :--- |
| Use `md2docx.js` for Markdown → .docx; it handles page size, numbering, dual-width tables, and image alt-text. | Assemble docx inline with `new Document({...})` on every task — you'll regress on paged-media details. |
| Keep placeholders exactly `{{key}}`; pass `--strict` for legal/customer-facing outputs. | Roll your own regex replace on the extracted XML; split runs will defeat you. |
| `office/unpack.py` → edit → `office/pack.py` for raw XML edits. | Edit the `.zip` in place with external tools — smart-quote round-trips will break. |
| `docx_accept_changes.py` (LibreOffice) for applying tracked changes. | Delete `<w:del>` / `<w:ins>` blocks directly — you'll lose author attribution and break paragraph-delete markers. |

### Rationalization Table

| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "I know docx-js, I'll just write the assembly inline." | `md2docx.js` already encodes the fixes for Word's quirks; inline code regresses on tables, images, and numbering. |
| "The user wants a tiny change, unpacking is overkill." | Unpacking is three seconds; skipping it and patching the ZIP by hand routinely breaks smart-quote round-trips. |
| "I don't need `--strict`, a missing placeholder is obvious." | Missing placeholders ship as literal `{{customer.name}}` in customer emails. `--strict` is exactly for customer-facing output. |
| "Schemas aren't bundled, so `validate.py` is useless." | The structural layer (relationships, duplicate IDs, comment pairing) runs without schemas. XSD binding is a bonus. |

## 10. Quick Reference

| Task | Command |
|---|---|
| Markdown → `.docx` | `node scripts/md2docx.js input.md output.docx` |
| `.docx` → Markdown | `node scripts/docx2md.js input.docx output.md` |
| Fill template | `python3 scripts/docx_fill_template.py template.docx data.json out.docx [--strict]` |
| Accept tracked changes | `python3 scripts/docx_accept_changes.py in.docx out.docx` |
| Unpack for raw editing | `python3 scripts/office/unpack.py in.docx unpacked/` |
| Repack | `python3 scripts/office/pack.py unpacked/ out.docx` |
| Structural validate | `python3 scripts/office/validate.py file.docx [--json] [--strict]` |
| Compare tracked changes vs original | `python3 scripts/office/validate.py edited.docx --compare-to ORIGINAL.docx` |

## 11. Examples (Few-Shot)

Full fixture: [examples/fixture-simple.md](examples/fixture-simple.md).

**Input** — user request:
> Convert `report.md` to a Letter-sized `.docx` and check it's structurally sound.

**Output** — agent action (abbreviated):
```bash
cd skills/docx/scripts && npm install          # one-time setup
node scripts/md2docx.js report.md report.docx --size letter
python3 scripts/office/validate.py report.docx
```
Report the exit codes and a one-line summary to the user ("`report.docx` created; validator OK").

**Input** — user request:
> Fill `invoice.docx` with the data in `customer.json`, fail if anything is missing.

**Output** — agent action:
```bash
python3 scripts/docx_fill_template.py invoice.docx customer.json invoice-filled.docx --strict
```
On non-zero exit, surface the `Unresolved placeholders: …` stderr line to the user.

## 12. Resources

- [references/ooxml-basics.md](references/ooxml-basics.md) — `.docx` as a ZIP of XML parts, minimum viable structure, namespace table.
- [references/docx-js-gotchas.md](references/docx-js-gotchas.md) — `docx-js` pitfalls (A4 default, dual widths, numbering, image altText, TOC, rsids).
- [references/tracked-changes.md](references/tracked-changes.md) — `<w:ins>` / `<w:del>` syntax, paragraph-delete markers, author attribution.
- [references/templating.md](references/templating.md) — why adjacent-run merging matters, supported placeholder grammar, anti-patterns.
- [scripts/office/validators/redlining.py](scripts/office/validators/redlining.py) — RedliningValidator: compare edited `.docx` against the original, report unmarked deletions/insertions/rewrites and author-attribution gaps. Driven by `--compare-to` flag on `office/validate.py`.
- [scripts/office/shim/](scripts/office/shim/) — LD_PRELOAD / DYLD_INSERT_LIBRARIES shim that lets LibreOffice start inside seccomp-tightened sandboxes that block AF_UNIX. `_soffice.py` auto-detects and auto-compiles. See [scripts/office/tests/test_shim.md](scripts/office/tests/test_shim.md) for nsjail/Docker end-to-end validation.
- [scripts/md2docx.js](scripts/md2docx.js) — Markdown → .docx converter (original script, preserved).
- [scripts/docx2md.js](scripts/docx2md.js) — .docx → Markdown converter (original script, preserved).
- [scripts/docx_fill_template.py](scripts/docx_fill_template.py) — template placeholder filler with run canonicalisation.
- [scripts/docx_accept_changes.py](scripts/docx_accept_changes.py) — LibreOffice-based tracked-change acceptor.
- [scripts/office/](scripts/office/) — OOXML unpack/pack/validate utilities shared conceptually with `xlsx` and `pptx` skills.
- [scripts/office/schemas/README.md](scripts/office/schemas/README.md) — how to fetch ECMA-376 / Microsoft / W3C XSDs for strict validation.

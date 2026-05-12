---
name: docx
description: Use when the user asks to create, edit, convert, validate, preview, or password-protect Microsoft Word .docx documents. Triggers include "markdown to docx", "docx to markdown", "fill Word template", "accept tracked changes", "validate docx", "preview docx as image", "encrypt/decrypt docx", and related .docx round-trip or template-fill tasks.
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
- "I'll just regex-replace `\|` in OOXML to extract or modify text." → **WRONG**. Raw XML regex operates on serialised bytes and breaks namespace prefixes, entity encoding, and split-run anchors. Use `docx_replace.py` (anchor-and-action surgical edit) which works at the lxml element level after run canonicalisation.
- "I need to edit a `.docx` and the `docx2md → md2docx` round-trip loses styling." → Use `docx_replace.py --replace` instead. It operates at run level, preserving bold/italic/colour/numbering. Round-trip through markdown is lossy: inline formatting, list numbering schemas, and table borders all flatten.

## 2. Capabilities
- **Surgical anchor-and-action edit** of a live `.docx` (no template required) via `docx_replace.py` — find a text anchor and `--replace TEXT` / `--insert-after PATH` / `--delete-paragraph` without a lossy `docx2md → md2docx` round-trip. Run-level formatting (bold, italic, colour, numbering) is preserved. **`--insert-after` automatically relocates images, charts, OLE objects, SmartArt diagrams, and numbered/bulleted lists from the MD source into the base document** (docx-6.5 + docx-6.6 v2 relocators, 2026-05-12). Honest scope: `--replace` requires the anchor to fit within a single `<w:t>` after run-merge (cross-run anchors not supported, R10.a); `--insert-after` and `--delete-paragraph` work at paragraph granularity. Anchor not found → exit 2 `AnchorNotFound`; last-paragraph delete refused → exit 2 `LastParagraphCannotBeDeleted`.
- Convert Markdown to `.docx` with headings, lists, tables, images, and optional mermaid diagrams via `md2docx.js`.
- **Convert HTML / web archives to `.docx`** via `html2docx.js` — accepts `.html`/`.htm`, Chrome `.mhtml`/`.mht`, and Safari `.webarchive` (sub-resources extracted to a temp dir). Confluence, GitLab wiki, and CMS chrome (ARIA-role-tagged headers/sidebars/footers, namespaced `<ac:*>` macros, `tablesorter` `<button>` wrappers) is stripped automatically before walking. Inline SVG diagrams (drawio/mermaid/PlantUML) are rastered to PNG via a two-tier renderer: **Tier 1** = headless Chrome / Chromium / Edge / Brave (auto-detected from conventional install paths or `HTML2DOCX_BROWSER`) gives pixel-perfect CSS layout including foreignObject labels and word-wrap; **Tier 2** = `@resvg/resvg-js` fallback for hosts without a browser, with foreignObject → SVG `<text>` conversion that preserves drawio's centring math, synthesises a viewBox on canvas-clipped diagrams (5% expansion absorbs drawio's edge-overshoot artifact), and word-wraps long Cyrillic/Latin labels at the wrapper's `width:Npx` so text fits inside its box. `--reader-mode` opt-in: stripped CMS chrome via a curated candidate list (`#main-content`, `.entry`, `.post-content`, `article`) with per-candidate min-text filter — useful for browser-saved news / blog pages where Confluence-priority selectors fall through to `<body>`.
- Extract `.docx` content back to Markdown preserving tables, lists, and embedded images via `docx2md.js`. Comments and tracked changes (which mammoth strips) are pulled into a JSON sidecar (`<output>.docx2md.json`) — useful for contract audits where the audit trail must accompany the converted markdown. Footnotes/endnotes are converted to pandoc-style `[^fn-N]` / `[^en-N]` markers with definitions appended at the end. Schema versioned (`v: 1`); the sidecar's `unsupported` field reports counts of revision types not yet captured (`rPrChange`, `pPrChange`, `moveFrom`, `moveTo`, `cellIns`, `cellDel`) so callers know what was lost. Opt-out via `--no-metadata` (skip sidecar) and `--no-footnotes` (skip pandoc conversion). Sidecar is **not** written when the source has no comments, no revisions, and zero unsupported counts — clean docs stay clean.
- Fill `.docx` templates containing `{{placeholder}}` or `{{nested.key}}` markers from a JSON payload with safe run-merging.
- Accept all tracked changes in a `.docx` via headless LibreOffice without leaving artefacts in the user's profile.
- Unpack and repack `.docx` archives for raw OOXML editing, with smart-quote entity round-tripping and run canonicalisation.
- Structurally validate a `.docx`: relationships, content types, tracked-change/`<w:delText>` integrity, comment marker pairing, and optional XSD binding.
- Reject password-protected and legacy `.doc` (CFB-container) inputs early with a clear remediation message (exit 3) instead of a `BadZipFile` traceback.
- Detect macro-enabled inputs (`.docm`, with `vbaProject.bin`) and warn when the chosen output extension would silently drop the macros (`docm` → `docx`).
- Render any `.docx`/`.docm`/`.pdf` (or peer-skill `.xlsx`/`.pptx`) into a single PNG-grid preview via `preview.py` (LibreOffice + Poppler).
- Emit failures as machine-readable JSON to stderr with `--json-errors` (uniform across all four office skills).
- Set or remove a password on a `.docx`/`.xlsx`/`.pptx` (MS-OFB Agile, Office 2010+) via `office_passwd.py` — three modes: `--encrypt PASSWORD`, `--decrypt PASSWORD`, `--check` (exit 0 encrypted / 10 clean / 11 missing).
- Insert a Word review comment anchored on a text substring via `docx_add_comment.py` — wires `<w:commentRangeStart>`/`<w:commentRangeEnd>`/`<w:commentReference>` markers, appends to `word/comments.xml`, and patches `[Content_Types].xml` + relationships. Supports threaded **replies** (`--parent N`) via `<w15:commentEx w15:paraIdParent=…>` in `commentsExtended.xml`; reply-to-reply chains are flattened to the conversation root to match Word's review-pane render. Multi-paragraph bodies via `\n` in `--comment` are split into separate `<w:p>` per ECMA-376 §17.13.4.2. Opt-in **library mode** (`--unpacked-dir DIR`) operates in-place on an already-unpacked tree (skips unpack/pack/encryption-check) — **not reentrant**: do not run two processes against the same tree concurrently, no file locking. Malformed OOXML side-parts surface as `MalformedOOXML` envelope (not a traceback). See [`references/add-comment-howto.md`](references/add-comment-howto.md) for verification steps and §6 troubleshooting for failure modes.
- Merge N `.docx` files into one via `docx_merge.py` (VDD iter-2 real-world hardened). Appends body content + styles + numbering + media + relationships into the first input (base), with full reference relocation: image rIds renumbered, `r:embed`/`r:link`/`r:id` in body remapped, `<w:bookmarkStart/End w:id>` bumped past base's max, `<w:abstractNum>` / `<w:num>` shifted with `<w:numId w:val>` body refs rewritten, missing `Default Extension` entries pulled into `[Content_Types].xml`. Strips paragraph-level `<w:sectPr>` from extras (their header/footer references would dangle). Inserts new `<w:abstractNum>` BEFORE first `<w:num>` per ECMA-376 §17.9.20 schema-order. Honest scope (still not merged, warned when extras have content): footnotes / endnotes / headers / footers / comments.

## 3. Execution Mode
- **Mode**: `script-first`.
- **Why this mode**: Each operation is a small, deterministic CLI wrapping a specific OOXML-aware library. Inline assembly in the agent's text is slower and regresses on details (page size, DXA units, namespace ordering). Scripts also make the skill reusable from any shell environment.

## 4. Script Contract

- **Commands**:
  - `node scripts/md2docx.js INPUT.md OUTPUT.docx [--header "TEXT"] [--footer "TEXT"]`
  - `node scripts/docx2md.js INPUT.docx OUTPUT.md [--metadata-json PATH] [--no-metadata] [--no-footnotes] [--json-errors]`
  - `node scripts/html2docx.js INPUT OUTPUT.docx [--header "TEXT"] [--footer "TEXT"] [--reader-mode] [--json-errors]` — INPUT may be `.html`/`.htm`, `.mhtml`/`.mht`, or `.webarchive`; sub-resources in archives are extracted to a temp dir automatically (cleaned up on exit incl. SIGINT/SIGTERM). `--reader-mode` swaps the article-root candidate list for a CMS/blog-specific one (`#main-content`/`.entry`/`.post-content`/`article` with per-candidate min-text filter; bare `<main>` deliberately omitted as it wraps whole-site chrome on news sites). Override SVG renderer with `HTML2DOCX_BROWSER=/path/to/chrome` or set it to a non-existent path to force the resvg-js fallback for CI determinism. Set `HTML2DOCX_ALLOW_NO_SANDBOX=1` only inside a trusted CI container — default leaves Chrome's sandbox enabled.
  - `python3 scripts/docx_fill_template.py TEMPLATE.docx DATA.json OUTPUT.docx [--strict]`
  - `python3 scripts/docx_accept_changes.py INPUT.docx OUTPUT.docx [--timeout 120]`
  - `python3 scripts/office/unpack.py INPUT.docx OUTDIR/ [--no-pretty] [--no-escape-quotes] [--no-merge-runs]`
  - `python3 scripts/office/pack.py INDIR/ OUTPUT.docx [--no-unescape-quotes] [--no-condense]`
  - `python3 scripts/office/validate.py INPUT.docx [--strict] [--json] [--schemas-dir PATH] [--compare-to ORIGINAL.docx]`
  - `python3 scripts/preview.py INPUT OUTPUT.jpg [--cols 3] [--dpi 110] [--gap 12] [--padding 24] [--label-font-size 14] [--soffice-timeout 240] [--pdftoppm-timeout 60]`
  - `python3 scripts/office_passwd.py INPUT [OUTPUT] (--encrypt PASSWORD | --decrypt PASSWORD | --check)` — pass `-` as PASSWORD to read it from stdin.
  - `python3 scripts/docx_add_comment.py INPUT.docx OUTPUT.docx --anchor-text TEXT --comment BODY [--author NAME] [--initials AB] [--date ISO] [--all]`
  - `python3 scripts/docx_add_comment.py INPUT.docx OUTPUT.docx --parent N --comment BODY [--author NAME]` — reply to comment N (inherits its anchor range; threads via `commentsExtended.xml`).
  - `python3 scripts/docx_add_comment.py --unpacked-dir DIR --anchor-text TEXT --comment BODY [...]` — library mode: edit an already-unpacked tree in-place (combine with `--parent` to add a reply over the same tree).
  - `python3 scripts/docx_replace.py INPUT.docx OUTPUT.docx --anchor TEXT (--replace TEXT | --insert-after PATH_OR_DASH | --delete-paragraph) [--all] [--unpacked-dir DIR] [--scope=LIST] [--json-errors]` — Tier B (script-first); positional INPUT OUTPUT; `--anchor TEXT` is always required; exactly one of `--replace`/`--insert-after`/`--delete-paragraph` is required (mutex). `--all` replaces/acts on every match instead of first. `--unpacked-dir DIR` operates on an already-unpacked tree in-place (library mode — skips unpack/pack/encryption-check). `--insert-after -` reads the markdown body from stdin. `--scope=LIST` (docx-6.7) restricts anchor-search to a subset of OOXML parts: comma-separated `body`, `headers`, `footers`, `footnotes`, `endnotes`, `all` (default: `all`). Example: `--scope=body` limits edits to `word/document.xml`, leaving header/footer boilerplate untouched. Order within the requested set is deterministic (document → headers → footers → footnotes → endnotes). Exit codes: 0 success, 1 I/O or OOXML error, 2 anchor-not-found / last-paragraph-delete refused / invalid `--scope` value, 3 encrypted/password-protected input, 6 same-path self-overwrite refused, 7 post-validate failure. `--json-errors` emits failures as `{v:1, error, code, type, details}` JSON on stderr (cross-5 envelope parity). Honest scope: `--replace` anchor must fit within a single `<w:t>` after run-merge; `--insert-after` converts markdown to OOXML via `md2docx.js` (requires Node.js in PATH).
  - `python3 scripts/docx_merge.py OUTPUT.docx INPUT1.docx INPUT2.docx [...] [--page-break-between] [--no-merge-styles]`
  - All scripts above accept `--json-errors` to emit failures as a single line of JSON on stderr (`{v, error, code, type?, details?}`). The schema version `v` is currently `1`; argparse usage errors are routed through the same envelope (`type:"UsageError"`).
- **Inputs**: positional paths only; optional flags per command.
- **Outputs**: a single file at the named output path; `office/unpack.py` produces a directory tree; `office/validate.py` prints a report (or JSON with `--json`). `docx2md.js` additionally creates `<stem>_images/` next to the Markdown output when the document has embedded images.
- **Failure semantics**: non-zero exit on missing input, invalid JSON, unresolved placeholders (with `--strict`), unreadable ZIP, or soffice errors. Error detail goes to stderr.
- **Idempotency**: repeated runs with the same inputs produce equivalent output files (byte-exact for the XML parts after pretty-print and entity normalisation). `docx_accept_changes.py` is idempotent on an already-accepted document. **Exception**: `office_passwd.py --encrypt` is intentionally non-deterministic — Office encryption uses a fresh random salt per run, so the encrypted bytes differ each time even with the same password. The decrypted output, however, is byte-equal to the pre-encryption input (lossless round-trip).
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
  - `node scripts/docx2md.js /tmp/out.docx /tmp/back.md && test -s /tmp/back.md` — round-trips non-empty Markdown. On a docx with comments / tracked changes, also writes `/tmp/back.docx2md.json` (schema `v:1`); on a docx with footnotes/endnotes, the markdown gets pandoc-style `[^fn-N]` markers + definitions block at the end. See [`references/docx2md-sidecar.md`](references/docx2md-sidecar.md) for the full schema and `--metadata-json` / `--no-metadata` / `--no-footnotes` flags. Same-path (`docx2md.js foo.docx foo.docx`) is refused with exit 6 (`SelfOverwriteRefused`) so the input is never destroyed.
  - `python3 scripts/office/validate.py /tmp/out.docx` — exits 0, prints `OK` or only warnings.
  - `python3 scripts/office/unpack.py /tmp/out.docx /tmp/unpacked && python3 scripts/office/pack.py /tmp/unpacked /tmp/repack.docx && unzip -p /tmp/repack.docx word/document.xml | head -c 100` — unpack/pack round trip.
  - `python3 scripts/docx_add_comment.py /tmp/out.docx /tmp/commented.docx --anchor-text "Quarterly" --comment "Verify this number" --author "QA Bot" && python3 -m office.validate /tmp/commented.docx` — adds a Word comment anchored on the substring; output validates and contains a `<w:comment>` part. See [`references/add-comment-howto.md`](references/add-comment-howto.md) for the full verification protocol.
  - `python3 scripts/docx_merge.py /tmp/merged.docx /tmp/out.docx /tmp/out.docx --page-break-between && python3 -m office.validate /tmp/merged.docx` — merges N inputs (here, two copies of `out.docx`) with a hard page break between them; output validates clean.
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
2. Page size and orientation are fixed (US Letter, portrait) — `md2docx.js` does not currently expose `--size` or `--landscape` flags. If the user needs A4 / landscape / custom margins, drop down to `python-docx` or unpack/edit `word/document.xml` directly via `office/unpack.py`.
3. For headers/footers use `--header "…"` / `--footer "…"`. Multi-line headers are a single string with `\n` — `md2docx.js` splits on the newline.

### 7.4 Extracting text from `.docx` to Markdown

1. Use `docx2md.js` for GFM output with tables preserved. If the document contains images, a sibling `<stem>_images/` directory is created — tell the user so they know to ship it alongside the Markdown.
2. For docs that carry **comments** or **tracked changes**, the converter writes a JSON sidecar `<stem>.docx2md.json` next to the Markdown. Tell the user to ship the sidecar alongside the markdown if the audit trail matters; the sidecar's absence on a clean doc is a feature, not a missing artefact. Field semantics + the `unsupported` counters are documented in [`references/docx2md-sidecar.md`](references/docx2md-sidecar.md).
3. For docs with **footnotes/endnotes**, the markdown body gets pandoc-style `[^fn-N]` / `[^en-N]` markers and definitions appended at the end. Pass `--no-footnotes` if downstream tooling can't parse pandoc syntax.
4. **MUST NOT** invoke `docx2md.js` with the same input and output path — the cross-7 H1 guard exits 6 (`SelfOverwriteRefused`), but better to never tempt it.
5. For plain text without any formatting, `pandoc -t plain` is a valid alternative but external — document this choice to the user rather than silently switching tools.

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
| HTML / `.webarchive` / `.mhtml` → `.docx` | `node scripts/html2docx.js input.html output.docx [--header ...] [--footer ...] [--reader-mode] [--json-errors]` |
| Web page / archive → `.docx` (reader mode, strips chrome) | `node scripts/html2docx.js page.webarchive article.docx --reader-mode` |
| Fill template | `python3 scripts/docx_fill_template.py template.docx data.json out.docx [--strict]` |
| Accept tracked changes | `python3 scripts/docx_accept_changes.py in.docx out.docx` |
| Unpack for raw editing | `python3 scripts/office/unpack.py in.docx unpacked/` |
| Repack | `python3 scripts/office/pack.py unpacked/ out.docx` |
| Structural validate | `python3 scripts/office/validate.py file.docx [--json] [--strict]` |
| Compare tracked changes vs original | `python3 scripts/office/validate.py edited.docx --compare-to ORIGINAL.docx` |
| Preview as PNG-grid | `python3 scripts/preview.py file.docx preview.jpg [--cols 3] [--dpi 110]` |
| Set password | `python3 scripts/office_passwd.py clean.docx encrypted.docx --encrypt PASSWORD` (use `-` to read from stdin) |
| Remove password | `python3 scripts/office_passwd.py encrypted.docx clean.docx --decrypt PASSWORD` |
| Detect password | `python3 scripts/office_passwd.py file.docx --check` (exit 0 encrypted / 10 clean / 11 missing) |
| Surgical text replace (no round-trip) | `python3 scripts/docx_replace.py in.docx out.docx --anchor "phrase" --replace "new text"` |
| Insert paragraph after anchor | `python3 scripts/docx_replace.py in.docx out.docx --anchor "phrase" --insert-after body.md` |
| Delete paragraph at anchor | `python3 scripts/docx_replace.py in.docx out.docx --anchor "phrase" --delete-paragraph` |
| Add review comment | `python3 scripts/docx_add_comment.py in.docx out.docx --anchor-text "phrase" --comment "body" --author "Reviewer"` |
| Reply to comment | `python3 scripts/docx_add_comment.py in.docx out.docx --parent N --comment "reply body" --author "Dev"` |
| Edit unpacked tree | `python3 scripts/docx_add_comment.py --unpacked-dir DIR --anchor-text "phrase" --comment "body"` (combine with `--parent` for replies in-place) |
| Merge N docx | `python3 scripts/docx_merge.py merged.docx a.docx b.docx c.docx [--page-break-between]` |
| Machine-readable failures | append `--json-errors` to any of the above |

## 11. Examples (Few-Shot)

Full fixture: [examples/fixture-simple.md](examples/fixture-simple.md).

**Input** — user request:
> Convert `report.md` to a `.docx` and check it's structurally sound.

**Output** — agent action (abbreviated):
```bash
cd skills/docx/scripts && npm install          # one-time setup
node scripts/md2docx.js report.md report.docx
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
- [scripts/docx_replace.py](scripts/docx_replace.py) — surgical anchor-and-action editor: `--replace`/`--insert-after`/`--delete-paragraph` without lossy round-trip. Requires `docx_anchor.py` and `_actions.py` siblings. Honest scope documented in `--help` (single-run anchor for `--replace`; no cross-run anchor spanning format boundaries).
- [scripts/docx_anchor.py](scripts/docx_anchor.py) — anchor utilities: `_find_paragraphs_containing_anchor`, `_merge_adjacent_runs`, `_replace_in_run`. Shared by `docx_replace.py` and `docx_add_comment.py`.
- [scripts/_actions.py](scripts/_actions.py) — F2 part-walker (`_iter_searchable_parts`), F4 `_do_replace`, F5 `_do_insert_after`, F6 `_do_delete_paragraph`; extracted from `docx_replace.py` at task 006-07a per Q-A1 LOC guardrail.
- [scripts/_app_errors.py](scripts/_app_errors.py) — domain exception hierarchy for `docx_replace.py` (`AnchorNotFound`, `LastParagraphCannotBeDeleted`, `Md2DocxFailed`, `Md2DocxNotAvailable`, `Md2DocxOutputInvalid`, `EmptyInsertSource`).
- [scripts/md2docx.js](scripts/md2docx.js) — Markdown → .docx converter (original script, preserved).
- [scripts/docx2md.js](scripts/docx2md.js) — .docx → Markdown converter (original script, preserved).
- [scripts/docx_fill_template.py](scripts/docx_fill_template.py) — template placeholder filler with run canonicalisation.
- [scripts/docx_accept_changes.py](scripts/docx_accept_changes.py) — LibreOffice-based tracked-change acceptor.
- [scripts/preview.py](scripts/preview.py) — universal `INPUT → PNG-grid` renderer for `.docx`/`.docm`/`.xlsx`/`.pptx`/`.pdf`. Byte-identical across all four office skills.
- [scripts/office_passwd.py](scripts/office_passwd.py) — set / remove / detect password protection on `.docx`/`.xlsx`/`.pptx` via msoffcrypto-tool (MS-OFB Agile, Office 2010+). Byte-identical across the three OOXML skills (not pdf — pdf has its own AcroForm encryption). Pass `-` as the password to read it from stdin (avoids leaking via `ps`/shell history).
- [scripts/_errors.py](scripts/_errors.py) — `--json-errors` envelope helper used by every Python CLI. Schema-versioned (`v=1`); routes argparse usage errors through the same envelope as domain errors.
- [scripts/_soffice.py](scripts/_soffice.py) — LibreOffice subprocess wrapper with sandbox-aware AF_UNIX shim auto-load.
- [scripts/office/](scripts/office/) — OOXML unpack/pack/validate utilities; **byte-identically replicated** to `xlsx` and `pptx` skills (docx is master — see CLAUDE.md §2 for the protocol).
- [scripts/office/_encryption.py](scripts/office/_encryption.py) — CFB-magic detection: rejects password-protected and legacy `.doc`/`.xls`/`.ppt` files with exit 3 + remediation hint.
- [scripts/office/_macros.py](scripts/office/_macros.py) — XML-aware macro detection (Default/Override ContentType in `[Content_Types].xml`); writer scripts warn when output extension drops the macros.
- [scripts/office/schemas/README.md](scripts/office/schemas/README.md) — how to fetch ECMA-376 / Microsoft / W3C XSDs for strict validation.

# Task 022-03 [LOGIC]: `html2md_core.js` core lift (docx-master) + Node bridge + G-3 no-drift

> **Predecessor:** 022-01.
> **RTM:** [R3] HTML→Markdown core. **Satisfies AC-R3** (docx no-drift).
> **ARCH:** §2.1 (FC-3), §5.2 (Node bridge), §9 (docx-master gated unit + G-3), §11 (022-03).

## Use Case Connection
- All UCs depend on this — it is the conversion core. No new UC behaviour;
  this bead makes the HTML→MD seam exist and stay byte-identical to docx.

## Task Goal
Extract the turndown stage from `docx2md.js` into a **standalone, docx-mastered**
`html2md_core.js` (`htmlToMarkdown(htmlString) → mdString`), wire `docx2md.js` to
import it (zero output drift), and add the Python→Node bridge in `core_bridge.py`.

## Changes Description
### NEW (docx side, master): `skills/docx/scripts/html2md_core.js`
- **Verbatim lift** of `buildTurndown` (docx2md.js ~318-336) + `expandTableToGrid`
  (~258-316) into a module exporting `htmlToMarkdown(html) -> string`:
  identical `TurndownService({headingStyle:'atx', codeBlockStyle:'fenced'})`,
  `turndownService.use(turndownPluginGfm.gfm)`, the custom `table`/`tableSection`
  rules (rowspan/colspan flat-grid, h1–h6→`<strong>` in cells, pipe-escape).
- Pure `stdin→stdout` CLI mode at the bottom: `if (require.main === module)` →
  read all stdin, `process.stdout.write(htmlToMarkdown(buf))`, exit 0; throw →
  exit 1. **No** file/frontmatter/image logic (D-10 — keep it byte-identical).

### EDIT (docx side, master): `skills/docx/scripts/docx2md.js`
- Replace the inline `buildTurndown().turndown(result.value)` call (~line 411)
  with `require('./html2md_core').htmlToMarkdown(result.value)`. Delete the now-
  migrated `buildTurndown`/`expandTableToGrid` bodies (or re-export from the core
  to avoid dup). **Footnote sentinel pre/post passes (`_metadata.js`) are
  untouched** — they live outside the turndown stage.

### REPLICATE (docx→html2md, gated): `skills/html2md/scripts/html2md_core.js`
```bash
cp skills/docx/scripts/html2md_core.js skills/html2md/scripts/html2md_core.js
```
- Add `turndown` + `turndown-plugin-gfm` to `skills/html2md/scripts/package.json`
  (already docx deps).

### `html2md/core_bridge.py` (replace stub)
- **`html_to_markdown(html: str) -> str`** — `subprocess.run(["node",
  "html2md_core.js"], input=html, capture_output, text, timeout)`; non-zero →
  `ConvertFailed`; bounded timeout; **no shell**. Node path resolved relative to
  the script dir.

## Test Cases
### Node unit (`skills/docx/scripts/...` + html2md copy)
1. **TC-03-01 `test_core_basic`** — headings/lists/links/inline → expected MD.
2. **TC-03-02 `test_core_gfm_table_rowspan`** — a `rowspan`/`colspan` table →
   flat grid (anchor value + blanks), matching the docx behaviour.
3. **TC-03-03 `test_core_pure_filter`** — `echo '<h1>x</h1>' | node html2md_core.js`
   → `# x`; no file written, exit 0.

### Python
4. **TC-03-04 `test_bridge_roundtrip`** — `core_bridge.html_to_markdown("<p>hi</p>")`
   → `hi`; Node-missing → `ConvertFailed` envelope.

### G-3 Regression (THE gate for AC-R3)
5. **TC-03-05 (G-3) `test_docx2md_no_drift`** — run docx `tests/test_e2e.sh` +
   `test_battery.py` round-trip; assert the produced Markdown is **byte-identical
   before vs after** the extraction (capture a pre-change golden, diff). Any
   drift fails the bead.
- **G-1**: `diff -q skills/docx/scripts/html2md_core.js
  skills/html2md/scripts/html2md_core.js` silent.

## Acceptance Criteria
- [ ] `html2md_core.js` exports `htmlToMarkdown` + works as a stdin→stdout filter.
- [ ] `docx2md.js` delegates to the core; **G-3** docx round-trip byte-identical.
- [ ] html2md copy is byte-identical to the docx master (G-1 silent).
- [ ] `core_bridge.html_to_markdown` bridges correctly; Node-missing → `ConvertFailed`.
- [ ] docx full suite + validator still green (no regression).

## Notes
- This bead **edits a docx master** — run the docx tests + replicate per CLAUDE.md
  §2 in the SAME change. The lift must be verbatim (D-10); only the call-site in
  `docx2md.js` changes behaviourally (and it must produce identical output).
- Adversarial roast focus: any subtle TurndownService option / gfm-wiring / table
  rule difference that would drift docx output.

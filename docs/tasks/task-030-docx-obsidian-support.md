# TASK 030 — docx: Obsidian-note support (`obsidian2md.js` + `md2docx.js --obsidian`)

**Status:** CODE COMPLETE — **verdict WARNING, not PASS** (VDD-Enhanced, 2026-08-13/14).

All mechanical gates are green: 363 unit tests, E2E 157/157, `validate_skill.py` PASSED,
A11 clean. **Five** adversarial cycles ran; the fourth and fifth were authorised by the user
beyond the workflow's three-cycle cap.

| Cycle | Target | Confirmed | Refuted |
|---|---|---|---|
| 1 | the implementation | 10 (+2 by hand) | 0 |
| 2 | cycle 1's repairs | 6 | 0 |
| 3 | cycle 2's repairs | 5 | 1 |
| 4 | cycle 3's repairs | 8 | 0 |
| 5 | cycle 4's rewrite | 8 | 0 |

Every cycle found real defects in the previous cycle's repairs. Cycle 5 found the defect in
`flushParagraph`'s index arithmetic, the code the cycle-4 brief had named as its least
reviewed. A negative slice offset **duplicated** a paragraph, embedding an image twice.

Four more came with it. A CRLF note's fence never closes, so everything after the first fence
is masked to EOF. A blockquoted fence returns with its `> ` prefix doubled. A backslash-escaped
backtick opens a mask region. The backtick-fence info-string rule was applied to tilde fences,
which CommonMark exempts.

Cycle 5 also ran the two methods no earlier cycle had: a **differential test of the masker
against `marked`'s own lexer** and a property check, over the 405 markdown files in
`examples/` and `docs/`. After the fixes: masking is exactly reversible on every file, no mask
sentinel reaches any output, and nothing throws.

The verdict stays **WARNING**: cycle 5's repairs were applied after the last cycle and have
had no review pass (`vdd-enhanced` §4.5). Findings the cycles raised but never verified are
tracked in
[`docs/backlog/wi-030-adversarial-carryover.md`](../backlog/wi-030-adversarial-carryover.md)
rather than dropped.

**Skill:** `docx` (**Proprietary** — per-skill `LICENSE`/`NOTICE`; CLAUDE.md §3).
**Mode:** VDD-Enhanced (`/vdd`).
**Origin spec:** `/Users/sergey/Downloads/docx-skill-obsidian-support-spec.md` (copied to
[`docs/docx-skill-obsidian-support-spec.md`](../docx-skill-obsidian-support-spec.md)).
**Reference prototype:** `/Users/sergey/Downloads/obsidian2md.prototype.py` — 121 lines, read
2026-08-13. It is the artifact spec §9 refers to as `/Users/sergey/.claude/jobs/eb2bf8cc/tmp/obsidian2md.py`
(«~60 строк»); the two paths are the same logic and the line count in the spec is stale. R1
re-implements the `Downloads` copy in JS. Neither path is under version control, so both are
quoted by content in this task where a claim depends on them.

---

## 0. Meta Information

- **Task ID:** 030 · **Slug:** `docx-obsidian-support` · **Date:** 2026-08-13
- **Driver (RU):** «доработай docx по спецификации … Обязательно сделай конвертацию
  фронтматтер в таблицу в стиле, как генерируются и другие таблицы.»
- **User override of the spec:** the spec proposes `--frontmatter render` (prose) as default.
  The user requires the **table** form, rendered by the existing `md2docx.js` table path so it
  carries the same borders and header shading as every other table. `table` is therefore the
  **default** mode; `render` and `strip` remain selectable. Recorded as **R2**.
- **Affected code surface:** `skills/docx/` only —
  new `scripts/obsidian2md.js`, new `scripts/_obsidian_lib.js`, modified `scripts/md2docx.js`,
  new `scripts/tests/test_obsidian2md.py`, new fixture tree `examples/fixture-obsidian-vault/`,
  `SKILL.md`, `scripts/.AGENTS.md`, `scripts/tests/test_e2e.sh`.
  Outside the code surface, the Architecture phase updates
  [`docs/architectures/architecture-011-docx-skill.md`](../architectures/architecture-011-docx-skill.md)
  (script table, tree, runtime list, command list) and the `arch-011` index row in
  [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md).
- **Replication units NOT touched:** nothing under `scripts/office/`, no `_soffice.py`,
  no `_errors.py`, no `preview.py`, no `office_passwd.py`, no `html2md_core.js`,
  no `_venv_bootstrap.py`. `docx2md.js` (the `html` skill's master for `html2md_core.js`)
  is also untouched — this task modifies `md2docx.js`, which is not a master of anything.
  **No `diff -q` gate applies to this task.** Confirmed by the file list above.
- **Reference note (acceptance fixture, read-only):**
  `<vault>/06 - Business Development/Yandex/Встреча по поддержке SpeechSense с Yandex.md`
  where `<vault>` = `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/ObsidianNotes`.

## 1. Problem Description

`md2docx.js` accepts an Obsidian note, exits 0, and writes a valid `.docx` that is missing
content. Measured on the reference note at commit `60909b5`:

```
node scripts/md2docx.js "<note>" out.docx --page-size A4   → exit 0
unzip -l out.docx | grep -c "word/media/.*\.\(png\|jpg\)" → 1   (mermaid only; 2 embeds lost)
unzip -p out.docx word/document.xml | grep -c "Осипов"     → 0   (5 participants lost)
unzip -p out.docx word/document.xml | grep -o '!\[\[' | wc -l → 2  (literal embed markers)
unzip -p out.docx word/document.xml | grep -o '\[\['  | wc -l → 17 (literal wikilinks)
```

Four confirmed defects:

- **D1 — frontmatter dropped.** [`md2docx.js:57`](../../skills/docx/scripts/md2docx.js#L57) strips
  `^---\n…\n---\n` unconditionally. Keys living **only** in YAML disappear. The reference note
  keeps its five `participants` there and nowhere else.
- **D2 — `![[embed]]` unrecognised.** `marked.lexer('![[pic.png]]')` yields a `text` token, not
  an `image` token. Both slide images render as literal text.
- **D3 — `[[wikilink]]` unrecognised.** Same mechanism. 17 raw wikilinks reach the document.
- **D4 — unescaped space in an image path.** `marked.lexer('![a](/tmp/my folder/pic.png)')`
  yields a `text` token. This is plain CommonMark, not Obsidian syntax, and every vault path
  contains spaces (`Mobile Documents`, `06 - Business Development`).

Exit 0 with a valid package and missing content is the failure class this task closes.

## 2. Goal and Scope

**Goal.** A note from an Obsidian vault converts to `.docx` in one command, with no content
loss and no manual pre-processing.

**Out of scope** (stated so the boundary is checkable, not aspirational):

- `.docx` → Obsidian note (reverse route);
- Obsidian plugin syntax (Dataview, Templater, Excalidraw rendering);
- math (`$…$`, `$$…$$`) — spec R-3. It reaches the document as text today and still will.
  Filed as **docx-11** in [`docs/office-skills-backlog.md`](../office-skills-backlog.md).

<!-- contract:rtm -->
## 3. Requirements Traceability Matrix (RTM)

The `Sub-features` cells exceed the `documentation-standards` §5.1 width and sentence budgets by
design, matching the shipped corpus (`docs/tasks/task-029-*.md`). The scanner reports them as
`cell_width` / `cell_sentences` warnings and exits 0.

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| R1 | **New standalone converter** `scripts/obsidian2md.js`: Obsidian-flavoured Markdown → CommonMark that `md2docx.js` already parses correctly. Knows nothing about OOXML. | YES | (a) CLI `node obsidian2md.js <IN.md> <OUT.md> [flags]`; (b) all conversion logic in a required module `scripts/_obsidian_lib.js` so `md2docx.js` reuses it without spawning a subprocess; (c) `OUT.md` is UTF-8, LF-terminated; (d) refuses `IN === OUT` (same resolved path) with exit 6 `SelfOverwriteRefused` |
| R2 | **Frontmatter → two-column table (DEFAULT).** `--frontmatter table\|render\|strip`, default **`table`**. The table is emitted as a GFM table so `md2docx.js`'s existing `table` token path renders it with the same borders and `D5E8F0` header shading as every other table (user requirement, overrides spec FR-1's `render` default). | YES | (a) `table` — GFM table, header row `Поле \| Значение` (ru) / `Field \| Value` (en), one row per displayed key, inserted directly after the H1; (b) `render` — bold-label prose per spec FR-1, one value per line for a multi-valued key. That branch had no test, so dropping every attendee after the first passed the suite — the D1 failure class this task exists to close, in a selectable mode; (c) `strip` — current behaviour; (d) displayed keys and their labels live in a module-level constant `FRONTMATTER_KEYS`, not inside a function; (e) displayed set: `participants`, `tags`, `author`, `published`/`date`, `URL`/`source`; (f) suppressed set: `type`, `slug`, `vault_id`, `Created`, `Updated`, `sources`, `tldr`, `lang`; (g) a multi-valued key renders one value per line inside the cell, joined with `<br>`. A GFM cell cannot hold a block list, and `<br>` is handled by `md2docx.js`'s inline path — measured: one `<w:br/>`, each value its own run. Comma-joining was the first design and reads worse for a five-person attendee list; (h) cell text has `\|` escaped and newlines collapsed so a value can never break the table; (i) no frontmatter, or no displayed key present → **no table emitted**, no empty header row; (j) note with frontmatter but no H1 → table emitted at the top of the body. Placement runs while the code regions are **still masked**: a fenced block can contain a `# ` line (a shell comment, a diff header), and placing the table after unmasking spliced it into the middle of that fence — on the normal Obsidian shape where the title is the filename (cycle-1 finding C-2) |
| R3 | **`![[…]]` embeds → real images** (closes D2). | YES | (a) `![[image.png]]` → `![<stem>](<resolved destination>)`; (b) `![[image.png\|300]]` → width hint 300 px; (c) `![[image.png\|100x50]]` → width 100, height 50; (d) `![[file.pdf]]`, `![[file.pdf#page=3]]`, `![[audio.mp3]]`, `![[video.mp4]]` → an italic reference line naming the file, never an image token; (e) `![[Note]]` (no extension, or `.md`) → default an italic pointer line (`*См. заметку «Note»*` / `*See note "Note"*`); (f) recognised image extensions: `png jpg jpeg gif bmp svg` — kept in lockstep with `detectImageType()` in `md2docx.js`, and regression-locked by a test that compares the two lists. **`webp` was in this set and is now deliberately out**: the docx image layer cannot embed it, so a resolvable `.webp` reached `buildImageRun()` and threw `Unsupported image format`. It now takes the (d) path and is named as a file (cycle-1 finding T2); (g) **transport for (b)/(c)** — the hint rides a reserved alt-text prefix matching exactly `^w=\d+(?:x\d+)?\\\|`, consumed in `buildImageRun()` ([md2docx.js:277](../../skills/docx/scripts/md2docx.js#L277)); (h) **geometry rule.** `w=NNN` → `w = min(NNN, naturalW, maxWidthPx)` and `h` scales from the source aspect ratio; `w=NNNxMMM` → both dimensions taken literally, then scaled down together to fit the page. The hint is an **upper bound and never upscales**, preserving the `Math.min(1, …)` invariant at [md2docx.js:309](../../skills/docx/scripts/md2docx.js#L309); **honest scope:** Obsidian *does* upscale on `\|300`, so a source narrower than the hint renders smaller here than in Obsidian. Spec FR-6 says «применить как верхнюю границу», which is this reading; (i) an alt text not matching the (g) regex takes the existing path unchanged |
| R4 | **`[[…]]` links → text** (closes D3). | YES | (a) `[[target\|Label]]` → `Label`; (b) `[[target]]` → last `/` segment of `target`; (c) `[[target#Heading]]` → `target → Heading`; (d) `[[target#^blockid]]` → `target`; (e) `[[a\|b\|c]]` → `b\|c` — split on the FIRST `\|`; the label is everything after it, embedded pipes included (a `split('\|')[1]` yielding `b` is the defect this guards against); (f) `--links=text\|italic`, default `text` (`bookmark` from spec FR-3 is deliberately NOT implemented — see §5 Rejected) |
| R5 | **Attachment path resolution**, in Obsidian's own order. | YES | (a) `<vault>/.obsidian/app.json` → `attachmentFolderPath`; a `./x` value means "`x` beside the note", a bare `x` means "`<vault>/x`". The value is **untrusted** — `app.json` travels with a vault — so an absolute value, or one resolving outside the vault root, is **refused with a warning** rather than followed. Confinement is enforced **twice**: on the parsed value, and again at the use site on `realpath`-resolved paths. A string-prefix check alone is defeated by a directory symlink shipped inside the vault, which keeps the path under the vault root while the bytes come from anywhere on disk (cycle-1 finding SEC-2). Refusing here and not later is the point: this key would otherwise redirect *every* lookup, and the resolved bytes are embedded into the output. A note's own `[[...]]` may still name an absolute path (R5c, declared non-confined); (b) the note's own directory; (c) the literal relative/absolute path in the link; (d) vault-wide filename search under `--vault-root`, comparing **NFC-normalised, case-folded** names (macOS hands out NFD, so `"й" == "й"` is false for a byte compare of the two forms); (e) >1 vault-wide match → stderr warning listing every candidate, first one used (spec R-2); (f) `--vault-root` unset → walk up from the note to the nearest directory containing `.obsidian/`, else the note's directory; (g) the vault-wide index is built at most once per run; each of R5(a) `..`, (d) NFC fold, (e) ambiguity warning, (f) walk-up and (h) skip-list now has a test — all five were the only implementation of their requirement and none was asserted anywhere; (h) the walk skips `.obsidian/`, `.git/`, `node_modules/`, and `.trash/`, and does **not** follow directory symlinks (no cycle possible); (i) **honest scope:** step (c) accepts an absolute path taken from note content, so resolution can leave the vault root — the converter reads it and does not confine it. Reads only, never writes |
| R6 | **Safe destinations** (closes D4). Every path the converter emits must lex as an `image` token. | YES | (a) emitted destinations use angle-bracket form `![alt](<path with spaces>)` — verified to reach `resolveLocalImagePath()` correctly; (b) a destination containing `<`, `>`, a newline, **or a literal `%`** falls back to full percent-encoding (`%` → `%25` first), because [`resolveLocalImagePath`](../../skills/docx/scripts/md2docx.js#L123) calls `decodeURI()` unguarded and `decodeURI("100% coverage.png")` raises `URIError: URI malformed`; (c) **independently**, `md2docx.js` warns on stderr `warning: image link with unescaped spaces was not parsed as an image: <fragment>` when a `text` token matches `/!\[[^\]]*\]\([^)]*\s[^)]*\)/` — this fires for plain-CommonMark users too and is not gated on `--obsidian`. The walk covers **table cells**: a `table` token keeps its text in `header`/`rows` cells rather than `.tokens`, so an unparsed image inside a table was dropped in the silence this guard exists to break (cycle-2 finding T3); (d) **honest scope:** `docx_replace.py --insert-after` spawns `md2docx.js` through `_actions.py` with `capture_output=True` and inspects stderr only on a non-zero return code, so the (c) warning is captured and discarded on that path. Documented in the R6c code comment; routing it through `_actions.py` is out of scope |
| R7 | **Missing attachment policy.** | YES | (a) without `--strict-assets`: emit `*[изображение не найдено: X]*` / `*[image not found: X]*`, write a stderr warning, exit 0; (b) with `--strict-assets`: exit **8** `AssetNotFound`; (c) `--json-errors` prints one JSON line `{v:1,error,code,type,details}` to stderr, matching the `html2docx.js` / `_errors.py` envelope |
| R8 | **Callouts** (spec FR-7). `> [!type] Title` → a bold title paragraph then the remaining body as an ordinary blockquote. The `[!type]` marker must not reach the document. | YES | Inline tags are stripped **before** callouts are rewritten: bolding first and stripping second left the trailing space inside the emphasis, so a tagged title rendered as a literal `**Title **` (cycle-2 finding T30-V2). (a) type dictionary covering Obsidian's defaults (`note tip info todo abstract summary question warning caution attention failure danger bug error example quote success check done important`); (b) title absent → the localised label for the type; (c) unknown type → the type string itself, capitalised; (d) the foldable suffixes `+`/`-` after `[!type]` are consumed, not emitted; (e) nested/multi-paragraph callout bodies keep their `> ` prefix |
| R9 | **Minor syntax** (spec FR-8). | YES | (a) `==highlight==` → `**highlight**`; (b) `%%comment%%` → removed, inline and block form; (c) `#inline-tag` → `--inline-tags=strip\|keep`, default `strip`. A tag starts at a line start or after whitespace **only** — a `#` inside a word, a URL fragment, a code span, or a Markdown link destination is not one; `[text](#anchor)` lost its destination when the lead class also accepted `(` (U-1). A **purely numeric** body is never a tag whatever punctuation follows: the rule was enforced by a lookahead demanding whitespace-or-end, so `#42.`, `#7,` and `#99!` were deleted from ordinary prose (T30-V3). The line's **indentation is preserved**, only the gap the tag itself left is closed, and trailing space is trimmed only on lines that lost a tag. Collapsing every `[ \t]{2,}` run reformatted alignment the author chose — `val  = 1   #tag` came back as `val = 1` (cycle-3 C3-03): a flush trim promoted `\t- nested #tag` to a top-level bullet (T30-V1), and a document-wide trim deleted Markdown hard line breaks from every line of every note (U-2); a `#` inside a word, a URL fragment, or a code span is not a tag; (d) `- [ ]` → `- ☐ `, `- [x]` → `- ☑ ` (`md2docx.js` has no list checkbox support) |
| R10 | **Fenced code and inline code are inert.** No rule R3, R4, R8, or R9 may rewrite text inside a fenced block, an indented code block, or an inline code span. | YES | (a) fenced blocks (triple-backtick and triple-tilde, any info string) masked before transformation and restored after. Control characters are stripped from the source first: U+0000 is valid UTF-8 and a note carrying the sentinel's own bytes could splice an unrelated stored region into itself. XML 1.0 forbids those bytes anyway, so they could never have reached a readable `.docx`; an **indented** block is masked only when CommonMark would read it as code — after a blank line, and **not inside a list**. Obsidian indents nested bullets with a tab, so a mask without that precondition swallowed every nested list item and let `![[embed]]` and `[[wikilink]]` through untouched at exit 0 (cycle-1 finding L-1, the round's only CRITICAL). Masking is **one line-based state machine**, not a set of regexes over the document. Four regex designs each shipped a defect that the shape made unavoidable: a bare indented-code regex ate every tab-indented nested bullet (cycle-1, CRITICAL); a fence inside a list came back as a column-0 sentinel and cleared the list state (cycle-2 O-1); stepping over that sentinel leaked the list state past the list's end and `#include <stdio.h>` was deleted from a real code block (cycle-3 C3-01); and an **unmatched backtick in prose paired with the next genuine span's opener, masking whole paragraphs at a time** (cycle-4 C4-01, CRITICAL). Each is a question about line context, which a document-wide regex cannot answer. Fence state, list-content indent and blockquote prefix are tracked explicitly; inline spans are masked **within one paragraph** and an unmatched run is left literal; a fence opened inside a blockquote ends where the blockquote does; list-content indent is measured after the marker and its spaces, so a fence indented 1-3 spaces closes the list (cycle-4 C4-04). **Honest scope:** an indented code block *nested inside a list* is treated as list content and stays visible to the rewrites; (b) inline code spans masked likewise; every blank line of a run inside an indented block is kept — dropping all but one made masking irreversible, i.e. the mask edited the code it was protecting; (c) a `mermaid` block passes through byte-identical — regression against the existing mermaid path; (d) frontmatter detection anchors at offset 0 only, so a `---` rule mid-body is never eaten |
| R11 | **`md2docx.js --obsidian [--vault-root DIR]`** — one-command route. | YES | (a) `--obsidian` runs the R1 module over the input in-process, writes the intermediate `.md` into a `fs.mkdtempSync` directory, and converts from there; (b) `inputDir` **keeps pointing at the real note's directory**, so a plain-CommonMark `![alt](img/pic.png)` in the note still resolves. Re-basing it on the temp directory made `--obsidian` fail with `Local image not found` on a document that converted fine without the flag — Obsidian emits markdown-style image links whenever "Use [[Wikilinks]]" is off (cycle-1 finding L-2). Wikilink embeds are absolute anyway (R6); (c) the temp directory is removed on success **and** on failure; (d) `--vault-root` is a **known value-flag** (it joins `VALUE_FLAGS`, so it is never "unknown"). Used without `--obsidian` it prints `--vault-root requires --obsidian` plus USAGE and exits **1**, matching every other usage error in this script ([md2docx.js:36-40](../../skills/docx/scripts/md2docx.js#L36-L40)) and honouring the precedent recorded at [md2docx.js:26](../../skills/docx/scripts/md2docx.js#L26) — a known flag never reports as unknown. The check runs **after** the parse loop, so flag order is irrelevant, and it covers **every** Obsidian flag. A value-carrying flag has a non-null default, so the parser records which flags were actually typed — the first version tested the parsed options and therefore accepted and silently discarded `--frontmatter`, `--lang`, `--links` and `--inline-tags` (cycle-1 finding DOC-1). Exit 2 is `obsidian2md.js`'s convention (R15c), deliberately NOT back-ported; (e) all `obsidian2md.js` flags relevant to conversion (`--frontmatter`, `--lang`, `--inline-tags`, `--links`, `--transclude`) are accepted and forwarded; `--strict-assets` is honoured here too and exits **8**, but without a JSON envelope — `md2docx.js` has none (A6); (f) without `--obsidian`, `md2docx.js` behaviour is byte-identical to today except two named additions: the R6c stderr warning, and the R3g alt-text prefix parse (a no-op on any alt text not matching R3g's `^w=\d+(?:x\d+)?\\\|`) |
| R12 | **Transclusion** `![[Note]]` with `--transclude` (spec FR-2, R-1). | NO | (a) inlines the target note's body, heading levels demoted by the embed's context depth, and **re-roots the target's own relative CommonMark image destinations onto its directory** — bare, angle-bracketed and titled forms alike, since the angle-bracket form is what this skill itself emits for any path with a space (cycle-3 V3-02) — `inputDir` belongs to the top-level note, so a transcluded `![alt](img/pic.png)` otherwise resolved against the wrong folder (cycle-2 finding V2-02); (b) target's own frontmatter always stripped, never re-emitted; (c) depth ≤ 3, **regression-locked** — the cap had no test and could be disabled with the suite green; (d) the visited set marks the notes on the CURRENT path and entries are removed on unwind. Leaving them behind made a **diamond** (A embeds B and C, both embedding the same note) trip the cycle branch on its second, non-recursive occurrence: the shared note was replaced by a pointer and the run reported a cycle that did not exist; **(h) the inlined text is handed back MASKED, into the SINGLE store shared by the whole run.** Giving each note its own store made a nested transclusion (A embeds B embeds C) mask C against one store and unmask it against another: **C's code block was destroyed and B's duplicated in its place** (cycle-4 C4-02, CRITICAL). `transclude()` runs inside `rewriteEmbeds`, the first of five passes, so text returned in the clear is rewritten a second time by the parent's remaining passes with the child's own masking already spent — a transcluded code block lost `#include`, had `[[x]]` unwrapped and `==x==` bolded (cycle-3 C3-02/V3-01). The heading demote runs inside the same masked window, or it reads a `# comment` in a shell fence as a heading; (e) a cycle emits the R3e pointer line instead of recursing, plus a stderr warning; (f) unresolved target → R7 policy; (g) **the target must resolve inside the vault root, compared on `realpath`**. Transclusion inlines the target's *text* into the document, so an unconfined target is an arbitrary-file read driven by a note somebody else wrote — a different risk from R5(i)'s attachment bytes, and confined where that one is not (cycle-1 finding SEC-1) |
| R13 | **Localisation.** `--lang ru\|en\|auto`, default `auto`. | YES | (a) `auto` reads the frontmatter `lang:` key, falling back to `en`; (b) every user-visible string (table header, key labels, callout labels, pointer lines, not-found placeholder) comes from a `MESSAGES` dictionary keyed by lang; (c) no Russian or English literal is hard-coded at a use site |
| R14 | **Idempotence and zero regression.** | YES | (a) running `obsidian2md.js` twice on the same input yields byte-identical output (SKILL.md §4 contract); (b) a CommonMark document containing no Obsidian syntax passes through **byte-identical modulo a single trailing-LF normalisation**, which must itself be idempotent (a second run changes nothing); (c) the existing `md2docx.js` suites stay green; (d) both byte-identity guarantees are **regression-locked against the tag stripper**, which broke each of them while claiming neither: `[text](#anchor)` lost its destination, and a two-space Markdown hard line break was deleted from every line of every note. One test each (cycle-1 findings U-1, U-2) |
| R15 | **Exit codes and error envelope**, matching the skill's convention. | YES | (a) `0` success; (b) `1` I/O; (c) `2` invalid argument / usage; (d) `6` `SelfOverwriteRefused`; (e) `8` `AssetNotFound` (new, `--strict-assets` only); (f) `--json-errors` on every non-zero path; (g) codes documented in `SKILL.md` §4 |
| R16 | **Fixture vault + tests.** | YES | (a) `examples/fixture-obsidian-vault/` — `.obsidian/app.json` with `attachmentFolderPath: ./_attachments`, a note, `_attachments/` holding a png (≥400 px wide, so A13's 120 px hint is a downscale), a jpg, and an attachment named **`100% coverage.png`** (A16); the fixture note embeds `![[<png>\|120]]` (A13); a second note for transclusion; and a directory **with a space in its name** so D4 stays covered; (b) `scripts/tests/test_obsidian2md.py` in the style of `test_md2docx_pagesize.py`, covering **A1–A10, A12–A16** and **at least one assertion per lettered sub-feature of R3, R4, R8, R9, R10, R13** — those four MVP requirements have no A-criterion of their own and the reference note exercises none of them (measured: 0 callouts, 0 `==highlight==`, 0 `%%comment%%`, 0 task items in it); (c) `scripts/tests/test_e2e.sh` gains the new suite; (d) `validate_skill.py skills/docx` exits 0 |
| R17 | **Documentation.** | YES | (a) `SKILL.md` §2 Capabilities, §4 Script Contract (both signatures + exit codes), **§5 Safety Boundaries** (read scope widens: R5d indexes files under `--vault-root` and R12 reads transclusion targets — both **read-only, never written**; the "never modify files the user did not name" clause stays true and must be shown to stay true), **§6 Validation Evidence** (one local-verification line per new entrypoint, house pattern), §10 Quick Reference row "Obsidian note → .docx", **§12 Resources** (both new scripts); (b) §1 Red Flags gains "I'll just run the vault note through `md2docx.js`" → **WRONG**, naming D1/D2 and that exit 0 guarantees nothing; (c) `scripts/.AGENTS.md` documents both new files; (d) no new third-party dependency, so `THIRD_PARTY_NOTICES.md` is unchanged — asserted, not assumed |

### 3.1 Requirement → spec-clause map

| RTM ID | Origin spec clause | Acceptance criterion |
|---|---|---|
| R1 | §4 architecture | A7 (idempotence exercises the CLI end to end) |
| R2 | FR-1 (**modified**: default `table`) | A3 |
| R3 | FR-2, FR-6 | A1, A13 |
| R4 | FR-3 | A2 |
| R5 | FR-4 | A1, A5 |
| R6 | FR-5 | A4, A16 |
| R7 | §6.1, §6.2 | A5, A6 |
| R8 | FR-7 | R16(b) sub-feature units — no A-criterion (the reference note has 0 callouts) |
| R9 | FR-8 | R16(b) sub-feature units — no A-criterion (0 highlights / comments / tasks in the reference note) |
| R10 | TASK-authored, no spec clause | A14 |
| R11 | §4 flag wrapper | A1, A3, A11 (every fixture row runs the one-command route — see §4 preamble) |
| R12 | FR-2 transclusion, R-1 | A9 (conditional — R12 is MVP=NO) |
| R13 | R-4 | A15 |
| R14 | §7 A7, A10 | A7, A10 |
| R15 | §6.2 | A6 |
| R16 | §6.5, §7 | A8, A12 |
| R17 | §6.3, §6.4 | A12 (`validate_skill.py` reads the documented structure) |

Every RTM ID resolves to an executable A-criterion or a named unit-test obligation under
R16(b). Spec §6.3 requires local dependencies only. It is carried by R17 and R16: this task
adds no dependency, and the one Python file it adds is a test.


## 4. Acceptance Criteria

Executable, from the spec's §7 table. `<fixture>` = `examples/fixture-obsidian-vault/`.

Unless a row says otherwise, `out.docx` is produced by the **one-command route**, so every
fixture-backed row is also coverage of R11. A6 is the one row that says otherwise, and says why:

```
node scripts/md2docx.js <fixture>/note.md out.docx --obsidian --vault-root <fixture>
```

| # | Check | Expectation |
|---|---|---|
| A1 | `unzip -l out.docx \| grep -c "word/media/.*\.\(png\|jpg\)"` | equals (number of `![[…]]` images) + (number of mermaid blocks) |
| A2 | `unzip -p out.docx word/document.xml \| grep -o "\[\[" \| wc -l` | on the **reference note**: 0. On the **fixture**: exactly 3 — the `[[not-a-link]]` and `![[not-an-embed.png]]` inside its fenced block plus the `![[also-not-an-embed.png]]` inline span, which R10 requires to survive. The test asserts the count, never grep's exit status (a clean document makes grep exit 1) |
| A3 | `unzip -p out.docx word/document.xml \| grep -c "Осипов"` | ≥ 1, and the participant sits inside a `<w:tbl>` element (mode `table`) |
| A4 | vault located under a path containing spaces | every image present (D4 regression) |
| A5 | `![[no-such.png]]` without `--strict-assets` | exit 0, placeholder in text, warning on stderr |
| A6 | same with `--strict-assets`, run on **`obsidian2md.js`** | exit 8, `--json-errors` emits a parseable envelope. **`md2docx.js` has no `--json-errors`** (pre-existing; zero occurrences in that file), so the envelope criterion belongs to the standalone CLI. `md2docx.js --obsidian --strict-assets` still exits 8, with a plain-text message — the same shape as every other `md2docx.js` diagnostic |
| A7 | `obsidian2md.js` run twice on one input | byte-identical output |
| A8 | `office/validate.py out.docx` | `OK` |
| A9 | mutual transclusion A↔B with `--transclude` — **gates only if R12 lands in this task** (R12 is MVP=NO; if split to a follow-up, A9 moves with it) | terminates, exit 0 |
| A10 | plain CommonMark input, no Obsidian syntax | output byte-identical to input, modulo the single trailing-LF normalisation named in R14(b) |
| A11 | reference note (`Встреча по поддержке SpeechSense с Yandex.md`) via `md2docx.js --obsidian` — **manual / local gate, NOT wired into `test_e2e.sh`** (the vault lives outside the repo, on one machine) | exit 0; 3 images in package; `Осипов` present inside a `<w:tbl>`; 0 literal `[[` |
| A12 | `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/docx` | exit 0 |
| A13 | `![[fixture.png\|120]]` | the image's `<wp:extent cx>` equals 120 px expressed in EMU (R3b/R3g) |
| A14 | a fenced block containing `![[x.png]]`, `[[y]]`, `> [!note]`, `==z==`, `%%c%%` | passes through byte-identical (R10) |
| A15 | `--lang ru` vs `--lang en` on one fixture | outputs differ only in strings drawn from `MESSAGES` (R13) |
| A16 | an attachment named `100% coverage.png` | exit 0, image present in the package (R6b — guards the `decodeURI` throw) |

## 5. Rejected / Deferred

| Item | Decision | Reason |
|---|---|---|
| `--links=bookmark` (spec FR-3) | **Rejected for this task** | Only meaningful together with `--transclude`, and only when the target landed in the same document. Cost is a `.docx`-internal anchor mechanism in a converter whose contract is Markdown→Markdown. Contradicts R1's "knows nothing about OOXML". |
| Math `$…$` → OMML/PNG (spec R-3) | **Deferred** | The spec itself proposes deferral. Filed as **docx-11** in `docs/office-skills-backlog.md`. |
| `--assets-dir DIR` (spec §4 signature) | **Rejected** | `--vault-root` plus `app.json` covers every layout observed in the reference vault. A second override would give R5 step (a) two sources of truth, and the spec gives no rule for which wins. |
| `marked` custom tokenizer (spec §4 alternative) | **Rejected** | Couples Obsidian syntax to `md2docx.js` internals; the spec's own reason. |
| Reuse by `pdf` / `pptx` / `marp-slide` | **Deferred** | R1 keeps the module reusable, but adding it to three more skills would create a fourth replication unit. Out of this task's scope; recorded so the option stays open. |

## 6. Open Questions

None blocking. Three judgement calls made under `core-principles` §3 and recorded here:

- **Default `--lang auto`.** The spec proposes `ru|en` with no default stated. `auto` reads the
  frontmatter `lang:` key, which the reference note carries (`lang: ru`), and falls back to `en`.
- **`--frontmatter` default is `table`, not the spec's `render`.** Direct user instruction.
- **Transclusion (`--transclude`) stays in scope at MVP=NO.** Spec R-1 puts the question to the
  reader («Решите, нужна ли она вам вообще»). The user did not answer it. Keeping it behind a
  flag costs a visited-set and a depth counter; dropping it would remove spec criterion A9. It is
  implemented last, and A9 moves with it if it is split out.

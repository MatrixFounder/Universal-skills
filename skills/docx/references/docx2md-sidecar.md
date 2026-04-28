# `docx2md` sidecar JSON & pandoc footnotes

Reference for the comment / track-changes JSON sidecar (docx-4) and the
pandoc footnote conversion (docx-5) emitted by
[`docx2md.js`](../scripts/docx2md.js). For high-level usage see manual
§3.2 ([`docs/Manuals/office-skills_manual.md`](../../../docs/Manuals/office-skills_manual.md)).

## Why this exists

Mammoth — the `.docx → HTML` engine `docx2md.js` runs under — silently
strips three OOXML constructs on its way to HTML:

- `<w:comment>` (Word review comments)
- `<w:ins>` and `<w:del>` (tracked changes — insertions and deletions)
- `<w:footnoteReference>` and `<w:endnoteReference>` (well, mammoth
  renders these as `<sup>` markers + a `<ol>` block, but after turndown
  you get noisy `[1](#fn1) … 1. ↑ text` markdown that no audit tool
  expects).

Contract auditors, regulatory reviewers, and anyone running diffs of
"reviewer markup" needs all of these preserved. The fix is to
post-process the .docx ourselves while mammoth converts the body, and
emit two artefacts alongside the markdown:

1. A **JSON sidecar** with comments + revisions in document order
   (docx-4).
2. **Inline pandoc footnote markers** with definitions appended at the
   end of the markdown (docx-5).

Both features default-on; opt-out via `--no-metadata` and
`--no-footnotes` respectively.

## Sidecar location

Default path is `<OUTPUT-stem>.docx2md.json` next to the markdown:

```text
out/
├── Контракт.md
├── Контракт.docx2md.json       ← sidecar (only when non-empty)
└── Контракт_images/            ← embedded media (existing convention)
```

Override with `--metadata-json /path/to/file.json`. The flag refuses to
swallow the next argv token if it starts with `--` (so
`--metadata-json --no-footnotes` exits 2 with a `UsageError`, instead
of writing a sidecar to a literal file named `--no-footnotes`).

The sidecar is **not written** when:

- `comments[]` is empty AND
- `revisions[]` is empty AND
- every counter in `unsupported{}` is zero.

This means clean documents (round-trips, fixtures with no review
markup) leave no clutter. The presence of the file by itself signals
"this document has reviewer content worth attention."

## Schema (v1)

```json
{
  "v": 1,
  "source": "<basename>.docx",
  "comments": [...],
  "revisions": [...],
  "unsupported": {
    "rPrChange": 0, "pPrChange": 0,
    "moveFrom": 0, "moveTo": 0,
    "cellIns": 0, "cellDel": 0
  }
}
```

`v` is the schema version. Bump only on breaking field changes.

### `comments[]`

```json
{
  "id": 0,
  "paraId": "77E1E8F3",
  "parentParaId": null,
  "author": "Kuptsov Sergey",
  "initials": "KS",
  "date": "2026-04-28T15:22:00Z",
  "text": "что за текст?",
  "anchorText": "абзаца",
  "anchorTextBefore": "Типа текст ",
  "anchorTextAfter": "",
  "paragraphIndex": 2
}
```

| Field | Type | Source | Meaning |
|---|---|---|---|
| `id` | int \| null | `<w:comment w:id="N">` | Word's numeric comment id. `null` if attribute is missing or empty. |
| `paraId` | string \| null | `<w:comment><w:p w14:paraId="…">` | The paragraph identifier of the comment body's first paragraph. Used to thread replies. |
| `parentParaId` | string \| null | `commentsExtended.xml` `<w15:commentEx w15:paraIdParent="…">` | Parent comment's `paraId` for replies; `null` for top-level comments. Reply-of-reply chains flatten to the root in newer Word versions. |
| `author` | string \| null | `<w:comment w:author="…">` | Display name of the comment author. |
| `initials` | string \| null | `<w:comment w:initials="…">` | Two-three letter shorthand Word renders in the review margin. |
| `date` | string \| null | `<w:comment w:date="…">` | ISO-8601 timestamp **as-is**, including timezone if present. |
| `text` | string | concatenated `<w:t>` inside the comment | Plain-text body. Multi-paragraph comments collapse to single line (whitespace squashed). Formatting flattens. |
| `anchorText` | string | text between `<w:commentRangeStart>` and `<w:commentRangeEnd>` in `document.xml` | The substring the comment was attached to. Whitespace-collapsed. |
| `anchorTextBefore` | string | up to 40 chars of paragraph text immediately before `anchorText` | Stable locator: lets a consumer find the right occurrence when `anchorText` repeats in the document. |
| `anchorTextAfter` | string | up to 40 chars of paragraph text immediately after `anchorText` | Same purpose — covers the case where `anchorTextBefore` is empty (anchor at paragraph start). |
| `paragraphIndex` | int \| null | document-order index of the `<w:p>` containing `commentRangeStart` | 0-based index across all `<w:p>` in `document.xml` (body, not headers/footers). Robust ordering even when authors edit the doc. |

Comments are sorted by `paragraphIndex` (document order), nulls last,
ties broken by `id`.

**Capture cap.** When `<w:commentRangeEnd>` is missing (malformed doc),
the anchor walker stops after 2000 characters and appends
`…[truncated]` so the sidecar stays bounded.

### `revisions[]`

```json
{
  "type": "insertion",
  "id": 100,
  "author": "Alice",
  "date": "2024-06-01T10:00:00Z",
  "text": "added clause",
  "paragraphIndex": 12,
  "runIndex": 3
}
```

| Field | Type | Meaning |
|---|---|---|
| `type` | `"insertion"` \| `"deletion"` | Maps to `<w:ins>` / `<w:del>` respectively. |
| `id` | int \| null | `w:id` attribute, `null` if missing/empty. |
| `author` / `date` | string \| null | Same shape as comments. |
| `text` | string | Concatenated `<w:t>` (for insertion) or `<w:delText>` (for deletion). Tabs/breaks/inline images don't survive; v1 captures plain text only. |
| `paragraphIndex` | int \| null | Document-order index of the parent `<w:p>`. |
| `runIndex` | int \| null | Position of the `<w:ins>` / `<w:del>` element among run-level siblings (`<w:r>`, `<w:ins>`, `<w:del>`) of the parent paragraph. Lets you locate a 5-character insertion inside a 2-KB paragraph. |

**Nesting.** `<w:ins>` inside `<w:del>` (Word's "rejected insertion"
pattern) is captured only at the outermost level — the inner is
skipped. This avoids double-counting and keeps `text` consistent with
what the reviewer would see in Word.

Revisions are sorted by `(paragraphIndex, runIndex, id)` ascending.

### `unsupported{}`

These six counters report revision elements **not** captured in
`revisions[]`. They exist so the sidecar's caller can detect data loss
even though the v1 schema doesn't model the elements:

| Counter | OOXML element | Meaning |
|---|---|---|
| `rPrChange` | `<w:rPrChange>` | Run-property formatting change (font, color, bold/italic toggle). |
| `pPrChange` | `<w:pPrChange>` | Paragraph-property formatting change (style, indent, alignment). |
| `moveFrom` / `moveTo` | `<w:moveFrom>` / `<w:moveTo>` | Tracked content moves (origin / destination). |
| `cellIns` / `cellDel` | `<w:cellIns>` / `<w:cellDel>` | Table-cell-level insertions / deletions. |

If any counter is non-zero, the document had reviewer markup beyond
what v1 captures. A future v2 may promote one or more of these into
first-class `revisions[]` entries.

## Pandoc footnote conversion

Each `<w:footnoteReference w:id="N"/>` in the body is rewritten to the
inline pandoc reference `[^fn-N]`, and each `<w:endnoteReference>` to
`[^en-N]`. The corresponding definitions are appended in a single
block at the end of the markdown, in original Word id order:

```markdown
…body text with footnote[^fn-2] and endnote[^en-1].

[^fn-2]: A footnote about something important.
[^en-1]: An endnote referenced in the body.
```

Word's boilerplate entries (`<w:footnote w:type="separator">`,
`continuationSeparator`, `continuationNotice`, with the reserved IDs
`-1` and `0`) are filtered as not-user-content.

### Implementation: sentinel round-trip

Mammoth runs on a **modified** copy of the docx. Before mammoth sees
the document, every `<w:footnoteReference w:id="N"/>` is replaced
with a literal text run carrying a sentinel:

```xml
<w:r><w:t xml:space="preserve">⟦FN:N⟧</w:t></w:r>
```

(U+27E6 / U+27E7 — CJK punctuation rare enough to never collide with
real content; verified to survive mammoth+turndown verbatim.) The
post-mammoth pass then swaps `⟦FN:N⟧ → [^fn-N]` in the markdown.

The user-content `<w:footnote>` bodies are also blanked in
`word/footnotes.xml` so that mammoth's own footnote rendering (which
would emit a duplicate `<ol>` block) sees nothing to render.

### Orphan & empty handling

- **Orphan reference** (`<w:footnoteReference w:id="N"/>` with no
  matching `<w:footnote w:id="N">`): the sentinel is **not** injected;
  mammoth's default rendering takes over. Avoids dangling pandoc refs
  with no resolvable definition.
- **Empty footnote body** (`<w:footnote w:id="N"><w:p/></w:footnote>`):
  the sentinel **is** injected and an empty pandoc definition `[^fn-N]:
  ` is emitted. This keeps the reference resolvable by pandoc.

### `--no-footnotes`

Skips the entire pre/post pass. Mammoth's default rendering produces
markdown like `[1](#fn-2)` with a list of definitions appearing
inline as a numbered list — same behaviour as before docx-5 was
implemented. Use this flag if your downstream tooling can't handle
pandoc syntax.

## Honest scope (v1)

What the sidecar captures with full fidelity:

- Top-level comments with thread linkage (`paraId` /
  `parentParaId`), author, date, plain text, anchor text plus 40 chars
  of before/after context, paragraph index.
- `<w:ins>` insertions, `<w:del>` deletions, with author / date /
  plain text / paragraph index / run index.

What is **counted but not extracted** (reported in `unsupported`,
deferred to v2):

- Formatting changes (`<w:rPrChange>`, `<w:pPrChange>`).
- Table-cell ins / del (`<w:cellIns>`, `<w:cellDel>`).
- Content moves (`<w:moveFrom>`, `<w:moveTo>`). Note that mammoth
  still renders the moved content as plain text — the sidecar's count
  flag tells you the move occurred, but the markdown does not
  distinguish moved-from-deleted-then-inserted from a regular run.

What does **not** survive at all:

- Formatting inside footnote/endnote text (bold, links, nested lists)
  — flattened to plain text.
- Tabs / breaks / inline images inside `<w:ins>` / `<w:del>` text.
- Comments whose `commentRangeStart` and `commentRangeEnd` cross
  paragraphs cleanly — the anchor capture stops at the start
  paragraph's siblings; cross-paragraph comments get truncated
  `anchorText`. (`anchorTextBefore`/`anchorTextAfter` still work as
  locators.)

## Same-path safety

`node docx2md.js foo.docx foo.docx` exits 6 with a
`SelfOverwriteRefused` envelope. Symlinks resolving to the same inode
trip the guard too. Without it, the writeFileSync at the end of the
pipeline would replace the .docx bytes with markdown text, destroying
the input irrecoverably (verified: 9116-byte valid docx → 1398-byte
plain UTF-8 file).

## Verification recipe

```bash
# 1. Convert
node skills/docx/scripts/docx2md.js Контракт.docx Контракт.md

# 2. Inspect sidecar
jq '.comments | length' Контракт.docx2md.json
jq '.revisions[] | {type, author, text}' Контракт.docx2md.json
jq '.unsupported' Контракт.docx2md.json   # any non-zero?

# 3. Confirm pandoc footnote markers and definitions are paired
grep -cE '\[\^fn-[0-9]+\]' Контракт.md
grep -cE '^\[\^fn-[0-9]+\]:' Контракт.md   # should equal the above

# 4. Spot-check anchor locator on a comment
jq '.comments[0] | {anchorTextBefore, anchorText, anchorTextAfter}' \
   Контракт.docx2md.json
```

End-to-end checks live in
[`scripts/tests/test_e2e.sh`](../scripts/tests/test_e2e.sh) — search
for the `docx-4 + docx-5` block (12 base + 6 VDD-regression checks).

## Related references

- [`add-comment-howto.md`](add-comment-howto.md) — writing the
  inverse side: inserting a Word comment from the CLI.
- [`tracked-changes.md`](tracked-changes.md) — OOXML semantics of
  `<w:ins>` / `<w:del>` / formatting-change elements.
- [`ooxml-basics.md`](ooxml-basics.md) — namespaces, paragraph IDs,
  unit conventions used by the schema fields above.

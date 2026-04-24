# Tracked changes in WordprocessingML

Tracked changes in a `.docx` are stored as a pair of element wrappers,
`<w:ins>` for insertions and `<w:del>` for deletions, around the affected
run-level content inside `word/document.xml`. They live alongside
`<w:comment>` metadata in `word/comments.xml`, but are independent — a
file can carry changes without comments and vice versa.

Reference: ECMA-376 Part 1 §17.13 and `[MS-DOCX]` §2.4.21.

## Insertion

```xml
<w:p>
  <w:r><w:t>Hello </w:t></w:r>
  <w:ins w:id="1" w:author="Alice" w:date="2026-04-24T09:15:00Z">
    <w:r><w:t>brave </w:t></w:r>
  </w:ins>
  <w:r><w:t>world.</w:t></w:r>
</w:p>
```

Key points:
- `w:id` is unique within the document and must be a valid 32-bit signed
  integer.
- `w:author` is a free-form string (often a display name).
- `w:date` is ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`).
- The inserted text is stored in normal `<w:t>` children.

## Deletion

```xml
<w:p>
  <w:r><w:t>Hello </w:t></w:r>
  <w:del w:id="2" w:author="Bob" w:date="2026-04-24T10:02:11Z">
    <w:r><w:delText xml:space="preserve">cruel </w:delText></w:r>
  </w:del>
  <w:r><w:t>world.</w:t></w:r>
</w:p>
```

**Crucial rule:** deleted text must use `<w:delText>`, not `<w:t>`.
Putting `<w:t>` inside `<w:del>` is a common mistake; different viewers
handle it differently, and `office/validate.py`'s DOCX checker flags it
as a warning. Preserve leading/trailing whitespace with
`xml:space="preserve"`.

## Paragraph-level deletions

Deleting an entire paragraph (including its end-of-paragraph mark)
requires a `<w:del>` inside the paragraph's `<w:pPr>`/`<w:rPr>` block,
not just wrapping the runs:

```xml
<w:p>
  <w:pPr>
    <w:rPr>
      <w:del w:id="3" w:author="Alice" w:date="2026-04-24T10:30:00Z"/>
    </w:rPr>
  </w:pPr>
  <w:del w:id="4" w:author="Alice" w:date="2026-04-24T10:30:00Z">
    <w:r><w:delText>This whole paragraph is removed.</w:delText></w:r>
  </w:del>
</w:p>
```

Without the paragraph-level marker, Word will accept the text deletion
but leave an empty paragraph behind.

## Attribute changes (`<w:pPrChange>`, `<w:rPrChange>`)

Format changes (style, colour, spacing) are recorded via paired
elements that carry the *previous* formatting — Word needs to know
what to roll back to when the user rejects the change:

```xml
<w:r>
  <w:rPr>
    <w:b/>
    <w:rPrChange w:id="5" w:author="Alice" w:date="2026-04-24T11:05:00Z">
      <w:rPr><w:i/></w:rPr>
    </w:rPrChange>
  </w:rPr>
  <w:t>Revised text</w:t>
</w:r>
```

Here the run is now bold; previously it was italic. Preserve
`rPrChange` subtrees verbatim on round-trip.

## ID uniqueness

All `w:id` values on `<w:ins>`, `<w:del>`, `<w:pPrChange>`, and
`<w:rPrChange>` must be unique across the entire document, not per
paragraph. `office/helpers/simplify_redlines.py` renumbers them after
merging adjacent markers by the same author.

## Accepting changes programmatically

Two common paths:

1. **LibreOffice dispatch** — use `docx_accept_changes.py`. Spins up
   headless `soffice` with a disposable profile, runs
   `.uno:AcceptAllTrackedChanges`, resaves. Requires LibreOffice.
2. **Pure XML — works only for simple cases**: in `word/document.xml`,
   delete every `<w:del>…</w:del>` subtree and replace every
   `<w:ins>…</w:ins>` subtree with its children. This breaks on
   paragraph-level deletions and on formatting-change markers, so prefer
   the LibreOffice path whenever the document has non-trivial tracked
   changes.

## Rejecting changes

No script in this skill explicitly rejects changes. If needed, the
LibreOffice dispatcher is `.uno:RejectAllTrackedChanges` (or per-entry
`.uno:RejectTrackedChange` after navigating to it). Clone
`docx_accept_changes.py` and swap the dispatch command.

## Interaction with comments

Comment markers (`<w:commentRangeStart>`, `<w:commentRangeEnd>`,
`<w:commentReference>`) are independent of tracked changes — accepting
changes must not delete comment markers. When editing `document.xml`
manually, preserve comment markers as siblings of any `<w:r>` they
anchor; they are never placed inside a run.

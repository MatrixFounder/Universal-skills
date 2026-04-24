# Template filling in `.docx`

`docx_fill_template.py` substitutes values from a JSON file into a
`.docx` template that contains `{{placeholder}}` markers. The script
looks trivial (read, regex-replace, save) but Word's internal structure
makes the naive approach unreliable. This note explains why the script
looks the way it does and how to avoid the traps.

## The split-run problem

When you type `{{name}}` into Word, the text is stored as a single
`<w:r>` run:

```xml
<w:r><w:t>{{name}}</w:t></w:r>
```

Fine. Now save the document, open it on a different machine, let the
spell-checker run, or retype part of the placeholder. Word may
silently split the run, giving you something like:

```xml
<w:r><w:t>{{</w:t></w:r>
<w:r><w:t>name</w:t></w:r>
<w:r><w:t>}}</w:t></w:r>
```

All three runs share identical `<w:rPr>`. Visually nothing changed. But
a regex like `\{\{\s*([A-Za-z0-9_.]+)\s*\}\}` applied to each `<w:t>`
in isolation will find exactly zero placeholders.

The same pattern appears with Google Docs → Word exports, with
macro-generated documents, and even mid-session after Word's
autocorrect fires.

## Solution: merge adjacent runs before substitution

`docx_fill_template.py` first walks every paragraph and merges adjacent
`<w:r>` siblings whose `<w:rPr>` subtrees are byte-identical (after
canonical XML serialisation) and that contain only `<w:rPr>` and
`<w:t>` children. Any run with other children (field codes, breaks,
drawings) is left alone — merging those would corrupt non-text
content.

After the merge pass, regex substitution on each `<w:t>` works
reliably.

The helper lives in `scripts/office/helpers/merge_runs.py` and is also
called by `office/unpack.py` when producing a pretty-printed tree.

## Supported placeholder grammar

| Form | Example | Resolution |
|---|---|---|
| Flat key | `{{customer}}` | `data["customer"]` — must be a string/number/bool |
| Dotted path | `{{customer.name}}` | `data["customer"]["name"]` |
| With whitespace | `{{ customer.name }}` | Same as above; inside-brace whitespace is allowed |
| Non-string value | any | Rendered via `json.dumps(value, ensure_ascii=False)` — lists and dicts become JSON strings in the output |

**Unsupported** (explicitly not attempted):

- `{% if %}` / `{% for %}` / `{% endif %}` blocks.
- Function calls or arithmetic (`{{ total * 1.18 }}`).
- Default values (`{{ name | default('N/A') }}`).
- Whitespace control (`{{- key -}}`).

Picking a deliberately small grammar keeps the edge cases predictable.
For conditional blocks and loops use [docxtpl](https://github.com/elapouya/python-docx-template)
(LGPL) and write a thin CLI wrapper, or assemble the document with
`python-docx` from scratch.

## Where placeholders can live

The script rewrites placeholders in:

- body paragraphs, including nested table cells;
- headers and footers (all six variants: primary, first-page, even-page);
- text inside table cells.

It does **not** substitute inside:

- image alt text or title — Word stores these separately and the UX
  expectation is that alt text is static;
- comments (`word/comments.xml`);
- footnotes (`word/footnotes.xml`);
- embedded content controls that hold bound data.

If you need substitution in any of those, unpack the `.docx` with
`office/unpack.py`, patch the XML by hand, and repack.

## The `--strict` flag

By default the script prints a list of unresolved placeholders to
stderr and exits 0. That is right for iterative work ("fill what you
can, let me see the result"). For production mail-merge where a
missed variable ships as literal `{{customer.name}}`, pass `--strict`:
the script then exits 1 if any placeholder is unresolved.

## Quality checklist before shipping a template

1. All placeholders use exactly `{{key}}` or `{{nested.key}}` — no
   alternate delimiters.
2. Nothing inside a placeholder needs to be bold / italic / underlined
   individually; formatting is applied at the run level, and the run's
   formatting carries over automatically.
3. Placeholders do not cross a run boundary that you introduced
   yourself (e.g. applying bold to `{{customer.` and not to `name}}`).
   The script's merge pass handles accidental splits, but deliberately
   split placeholders are still ambiguous — style the whole thing at
   once.
4. Run `docx_fill_template.py template.docx sample.json out.docx` with
   a sample payload, open `out.docx`, and confirm the substitutions
   look right. Repeat with `--strict` before shipping to verify no
   placeholders leaked.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| Literal `{{customer.name}}` appears in output | Split run across four `<w:r>` elements, merge pass hit an unrelated child and gave up. | Unpack, inspect `word/document.xml`, delete spurious run children, retry. |
| Nested value renders as `{'street': '1 Infinity Loop', 'city': 'Cupertino'}` | Value is a dict; script falls back to JSON. | Use dotted path `{{address.street}}`, or flatten the JSON before calling the script. |
| Date field reads `2026-04-24T00:00:00` | ISO format from JSON. | Pre-format the date in `data.json` into the user-visible form before calling the script. |
| Numbers show as `1000000.0` | Python float repr. | Use strings in `data.json` for pre-formatted numbers. |

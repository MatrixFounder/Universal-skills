<!--
  TEMPLATE: note-JSON output (opt-in `--emit note-json`)
  This is NOT a Markdown note — it is the JSON object you emit INSTEAD of the pyramid
  when the note-json flag is set. Schema + hard rules: references/note_json_contract.md.
  Field names `title`/`body` are LANGUAGE-NEUTRAL — their content is whatever language the
  note is in (source language by default; target language only with --translate). See R-4.
  Compatibility: `--contract wiki` renames title→title_ru, body→ru_body (the `_ru` suffix is
  a historical relic and still holds ANY language).
-->

# note-JSON skeleton (annotated)

```jsonc
{
  "title":      "<title in the note's language — ANY language; the field is language-neutral>",
  "title_orig": null,                 // set only when --translate moved the title to another language
  "author":     null,                 // string if the source states it; else null — NEVER fabricate
  "published":  null,                 // "YYYY-MM-DD" if stated; else null
  "tldr":       "<1–2 sentences>",
  "summary_bullets": [
    "<key point / decision / finding 1>",
    "<key point 2>"
    // count: full 4–7 · summary 8–14 · thread 3–6
  ],
  "body": "<full body for mode=full/thread; null for mode=summary>",
  "entities": [
    {
      "name": "<CLEAN name; reuse known_concepts name if it matches>",
      "definition": "<1–2 sentences defining it from THIS source>",
      "quote": "<EXACT substring of body (full/thread) or a summary_bullets/tldr line (summary)>",
      "type": "concept"               // concept | external | person | company | product | group
    }
    // count: full 12–15 · summary 10–15 · thread 5–9
  ]
}
```

## Quick reference

| mode | `body` | quotes are substrings of… |
|------|--------|---------------------------|
| `full` | the full pyramid конспект (meeting) / full article body (document) | `body` |
| `summary` | `null` | a `summary_bullets` or `tldr` line |
| `thread` | tight конспект (2–5 paragraphs) | `body` |

## Meeting entity-type mapping
participant → `person` · project/initiative → `product` · team/department → `group` ·
company/vendor → `company` · tool/system/standard → `external` · topic/methodology/decision
worth a page → `concept`.

## Before you emit — the 3 load-bearing checks
1. **Every `quote` is copy-pasted** from your produced text (not paraphrased) — R-3.
2. **Every `name` is reconciled** against `known_concepts` (reuse existing) — R-2.
3. **No `name` contains** `/`, `—`, or `«»` — R-5.

Full self-verification checklist: `references/note_json_contract.md` §6.

Worked examples:
- `examples/example_output_note_json_meeting.md` (meeting, full, Russian, no translation, neutral fields)
- `examples/example_output_note_json_article.md` (document, summary, `--translate ru`, `--contract wiki` aliases)

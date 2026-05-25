# Description Metadata (`<out>.description.md`)

Triggered by `--with-description`. The sidecar lives next to the
plain-text transcript at `<out>.description.md` (the `.txt` suffix is
stripped if present, so `foo.txt → foo.description.md`).

Format: **YAML frontmatter** + optional H1 + Markdown body. The
frontmatter shape differs by source.

## 1. YouTube / Vimeo

```markdown
---
source: youtube
url: "https://youtu.be/NSVTpCfBMK8"
video_id: NSVTpCfBMK8
title: Lecture 5 — Linear Algebra
uploader: MIT OpenCourseWare
uploader_url: "https://www.youtube.com/@mit"
upload_date: 2024-02-14
duration_sec: 3120
view_count: 12345
like_count: 678
---

# Lecture 5 — Linear Algebra

<original description body, unchanged, as returned by yt-dlp>
```

Source set to `vimeo` for Vimeo videos, otherwise identical schema.
`view_count` / `like_count` are omitted when yt-dlp can't fetch them
(e.g. private-but-accessible-via-cookies videos sometimes hide counts).

## 2. Skool

```markdown
---
source: skool
url: "https://www.skool.com/zero-one/classroom/a60f0bd2?md=d40ba71..."
community: zero-one
classroom_id: a60f0bd2
lesson_id: d40ba71e3ed1474cb958b6f08b1920cc
title: Self-Improving Trading Agent on Hermes
embed_source: youtube
embed_url: "https://youtu.be/6njREUQAFdg"
duration_sec: 1082
thumbnail: "https://i.ytimg.com/vi/6njREUQAFdg/maxresdefault.jpg"
resources:
  - {name: "PDF handout", url: "https://..."}
---

# Self-Improving Trading Agent on Hermes

<lesson body, rendered from ProseMirror JSON to Markdown>
```

When the lesson has no embedded video, `embed_source` is `"none"` and
`embed_url` is omitted. `resources` is a JSON-decoded list of
`{name, url}` objects taken from `metadata.resources` (may be empty).

## 3. YAML quoting rules

The writer quotes any value containing YAML-special characters
(`: # \n " '`) with double-quoted form, escaping `\\` and `"`. This
means URLs are always quoted (they contain `:`). Bare scalars
(integers, booleans, simple words) render unquoted.

Empty lists render inline as `[]`. Dicts render as nested indented
keys, but at the moment the only nested structure we emit is the
`resources` list of dicts (rendered as inline-flow mappings per item).

## 4. Why YAML frontmatter?

- **Obsidian / RAG** ingestors universally parse YAML frontmatter into
  document metadata, so the file slots into a knowledge base without
  custom code.
- Markdown body remains readable as a standalone document — the file
  doubles as the lesson/video write-up for humans.
- Frontmatter is trivially round-trippable: the same fields appear in
  the `.stat.json` sidecar in JSON form for machine consumers.

## 5. Skipping the transcript

Pass `--description-only` together with `--with-description` to fetch
only the metadata + description sidecar; the `.txt` file is **not**
created and the `.stat.json` records `char_count: 0`,
`speaker_turn_count: 0`. Useful for batch-enriching a corpus you
already transcribed via another route.

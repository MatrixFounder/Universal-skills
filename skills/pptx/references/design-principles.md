# Design principles for generated decks

A slide deck is read from the back of the room under flat lighting,
often by a tired audience, usually on a cramped screen share. The
defaults in `md2pptx.js` lean heavily into readability and restraint
— a few rules the scripts already enforce, plus guidance for when you
step outside them.

These recommendations are original to this skill. Feel free to swap
the exact colours for brand colours as long as you preserve the
contrast ratios.

## Typography

- **Titles**: bold, 28–36 pt. The default `md2pptx.js` title is 32 pt.
- **Body**: 16–18 pt. Below 14 pt and most of the audience will squint.
- **Code**: 13–14 pt in a monospace face (Menlo, Consolas, Courier New).
- **Lines per bullet**: 1–2. If a bullet needs three lines of body
  text, it is actually a paragraph — move it off the bullet and use
  a paragraph text block.
- **Bullets per slide**: 3–5. More and the slide becomes unreadable
  under time pressure.
- **Font pairings that work**: Calibri (default, safe), Inter + Source
  Code Pro, Georgia + Calibri, Helvetica Neue + Menlo. Avoid mixing
  more than two typefaces.

## Colour palettes shipped by default

`md2pptx.js`'s default theme (`Charcoal Minimal`):

| Role | Hex |
|---|---|
| Background | `FFFFFF` |
| Foreground text | `1F2937` (charcoal) |
| Muted text | `6B7280` (slate) |
| Accent | `2563EB` (blue 600) |
| Accent light (highlights) | `DBEAFE` (blue 100) |
| Code block fill | `F3F4F6` (gray 100) |

The contrast ratio between the charcoal foreground and white
background is ~14:1 — well above WCAG AAA for body text.

For a dark theme, invert foreground/background and use
`DBEAFE` on `0F172A` with `60A5FA` as accent. Run the combination
through a contrast checker (e.g. <https://webaim.org/resources/contrastchecker/>)
before shipping.

## Whitespace

- Leave at least 0.3 inches between text blocks and slide edges.
- Leave at least 0.2 inches between adjacent text blocks.
- If a slide feels cramped, move content to a second slide. Blank
  slides are cheaper than illegible ones.

## Images

- Prefer full-width or half-width images. Small images look like
  afterthoughts.
- Use a consistent image width across the deck — the eye notices
  inconsistency.
- Always provide alt text. `md2pptx.js` takes it from the Markdown
  `![alt](path)` syntax.

## When in doubt, remove

The single most effective edit on almost any generated deck is to
delete something. Empty space focuses attention; filled space dilutes
it. Resist the instinct to "fill" a bullet list by adding more
bullets — if three bullets say it, three bullets ship.

## Layouts the wrapper supports

| Layout | Description | Trigger |
|---|---|---|
| Title + body | Level-1 heading + paragraphs/bullets | Default |
| Title + subtitle | Level-1 heading + level-2 heading adjacent | Second heading directly after the first |
| Title only | Level-1 heading, no body | No other tokens after the heading |
| Quote | Level-1 heading + blockquote | Blockquote present |
| Stat (title + big number) | Manual — use `pptxgenjs` directly | Not covered by the wrapper |

Complex layouts (split-half-image, stat cards, comparison grids)
still need direct `pptxgenjs` code. The wrapper's scope is
deliberately small so the 80% of Markdown-driven decks come out
consistent.

## Exit criteria — is the deck shippable?

1. Every slide fits within 5.625" height at 16:9 (nothing cut off).
2. No slide has more than 5 bullets or more than 40 words of body text.
3. Every image carries alt text.
4. Every fenced code block fits (wrap lines at ~80 chars, shorter is
   better).
5. Title and accent colours pass the user's brand checklist, or
   neutral defaults are used.
6. `pptx_thumbnails.py` grid looks consistent — no rogue slide with
   white-on-white or a missing element.

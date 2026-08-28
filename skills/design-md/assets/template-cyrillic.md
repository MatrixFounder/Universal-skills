---
version: "alpha"
name: "Mera"
description: "Bilingual RU/EN product interface. Every typeface in this system is verified to carry Cyrillic; the neutral ramp is biased to the primary hue so Russian data tables read as one surface family."
colors:
  primary: "#3949CE"
  on-primary: "#FFFFFF"
  primary-container: "#DEE1FF"
  on-primary-container: "#00105C"
  inverse-primary: "#B9C3FF"
  primary-fixed: "#DEE1FF"
  primary-fixed-dim: "#B9C3FF"
  on-primary-fixed: "#00105C"
  on-primary-fixed-variant: "#202FA5"
  secondary: "#5A5D72"
  on-secondary: "#FFFFFF"
  secondary-container: "#DFE1F9"
  on-secondary-container: "#171B2C"
  tertiary: "#1F6D4A"
  on-tertiary: "#FFFFFF"
  tertiary-container: "#C7F0D8"
  on-tertiary-container: "#00210F"
  error: "#B3261E"
  on-error: "#FFFFFF"
  error-container: "#F9DEDC"
  on-error-container: "#410E0B"
  background: "#FBFBFE"
  on-background: "#16181F"
  surface: "#FBFBFE"
  on-surface: "#16181F"
  surface-variant: "#E1E3ED"
  on-surface-variant: "#464A57"
  surface-dim: "#DCDDE6"
  surface-bright: "#FBFBFE"
  surface-container-lowest: "#FFFFFF"
  surface-container-low: "#F5F6FA"
  surface-container: "#EFF1F7"
  surface-container-high: "#E9EBF2"
  surface-container-highest: "#E3E6EF"
  surface-tint: "#3949CE"
  outline: "#767B8A"
  outline-variant: "#C6C9D6"
  inverse-surface: "#2B2F3A"
  inverse-on-surface: "#F1F2F8"
typography:
  display-lg:
    fontFamily: "Golos Text"
    fontSize: 32px
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: -0.005em
  display-md:
    fontFamily: "Golos Text"
    fontSize: 26px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.0025em
  heading-lg:
    fontFamily: "Golos Text"
    fontSize: 23px
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: 0em
  heading-md:
    fontFamily: "Golos Text"
    fontSize: 20px
    fontWeight: 500
    lineHeight: 1.35
    letterSpacing: 0em
  body-lg:
    fontFamily: "Inter"
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: 0em
  body-md:
    fontFamily: "Inter"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: 0em
  body-sm:
    fontFamily: "Inter"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0.005em
  label-md:
    fontFamily: "Inter"
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0.01em
    fontFeature: "'tnum' 1"
  caption:
    fontFamily: "Inter"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: 0.01em
  mono-md:
    fontFamily: "JetBrains Mono"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0em
rounded:
  none: 0px
  sm: 4px
  md: 8px
  lg: 12px
  xl: 16px
  full: 999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  2xl: 32px
  3xl: 48px
  4xl: 64px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
    height: 40px
  button-secondary:
    backgroundColor: "{colors.secondary-container}"
    textColor: "{colors.on-secondary-container}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
    height: 40px
  button-ghost:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
    height: 40px
  input-field:
    backgroundColor: "{colors.surface-container-lowest}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
    height: 44px
  card:
    backgroundColor: "{colors.surface-container-low}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xl}"
  table-header:
    backgroundColor: "{colors.surface-container}"
    textColor: "{colors.on-surface-variant}"
    typography: "{typography.label-md}"
    rounded: "{rounded.none}"
    padding: "{spacing.md}"
    height: 40px
  nav-rail:
    backgroundColor: "{colors.surface-container-high}"
    textColor: "{colors.on-surface-variant}"
    typography: "{typography.label-md}"
    rounded: "{rounded.none}"
    padding: "{spacing.md}"
    width: 240px
  badge-status:
    backgroundColor: "{colors.tertiary-container}"
    textColor: "{colors.on-tertiary-container}"
    typography: "{typography.caption}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
    height: 24px
  alert-error:
    backgroundColor: "{colors.error-container}"
    textColor: "{colors.on-error-container}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
  tooltip:
    backgroundColor: "{colors.inverse-surface}"
    textColor: "{colors.inverse-on-surface}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm}"
  language-switch:
    backgroundColor: "{colors.surface-container-highest}"
    textColor: "{colors.on-surface}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
    height: 32px
    width: 88px
  code-inline:
    backgroundColor: "{colors.surface-container}"
    textColor: "{colors.on-surface}"
    typography: "{typography.mono-md}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xs}"
---

## Overview

Mera is the interface system for a Russian-market B2B product whose every screen
ships in two languages at once: Russian for the operator, English for the integrator
reading the same table. Both scripts are set in the same three families at the same
sizes. Nothing switches when the locale switches except the strings.

**The failure this template exists to prevent.** A typeface with no Cyrillic glyphs
does not raise an error. `font-family: "Instrument Serif"` applied to `Отчёт за квартал`
produces a page that renders, lays out, and passes every build step; the browser
silently substitutes a system fallback for the characters the font lacks, and the
result reads as merely "slightly off" — different stroke weight, different rhythm,
slightly wrong line height. Reviewers describe it as a spacing problem and it survives
to production. Instrument Serif and Bodoni Moda are the established precedent: Google
Fonts serves both with the `latin` and `latin-ext` subsets only, so Latin copy is
correct and Russian copy is a system serif wearing the layout of another face.

**Verification procedure — both steps are required.**

1. Read the family's declared subsets and confirm `cyrillic` is present. On Google
   Fonts this is the `subset=cyrillic` parameter and the `unicode-range` block the
   CSS API returns; for a self-hosted file it is the `cmap` coverage. A family name,
   a foundry's marketing page, and a designer's reputation are not evidence.
2. Proof a real Cyrillic string at display size. Set
   `Ъ ъ Ы ы Ж ж Ф ф Щ щ Д д Й й Ц ц` and
   `Съешь ещё этих мягких французских булок, да выпей же чаю` — the pangram exercises
   every letter — and compare it against the same string in the intended fallback.
   If the two are indistinguishable, the font is not loading and the fallback is
   what you are looking at.

**The three families, and why each is here.** *Golos Text* carries display and
headings: it was drawn Cyrillic-first for a Russian-language public service, so its
Russian is the design and its Latin is the addition — the reverse of the usual
situation. *Inter* carries all running text and labels: a large x-height and open
apertures that survive 13px, plus a Cyrillic that is genuinely drawn rather than
mechanically derived. *JetBrains Mono* carries identifiers, keys, and API payloads.
Three families is the ceiling. Every added family multiplies the verification cost
above, which is the cost this system is organised around.

**Why `omitted` is absent.** All five machine-readable sections — `colors`,
`typography`, `rounded`, `spacing`, `components` — are defined here, so there is
nothing to declare. Listing a section in `omitted` while also defining it produces a
`redundant-omission` warning. Dark theme, motion, and iconography are described in
prose below rather than declared as omissions, because `omitted` accepts only the
five section names and nothing else.

## Colors

Thirty-nine tokens, named in the Material 3 role vocabulary. The vocabulary is not
decorative: the `orphaned-tokens` linter rule skips any color whose family resolves
to `primary`, `secondary`, `tertiary`, `error`, `surface`, `background`, or `outline`,
and warns on every other name that no component references. A palette named `чернила`
/ `бумага` / `акцент` is a warning generator; a palette named in roles is not.

**The neutral ramp has a hue bias, and it is deliberate.** Measured HSL hue across
the ramp — `surface-container-low` #F5F6FA at 228°, `surface-container` #EFF1F7 at
225°, `surface-container-highest` #E3E6EF at 225°, `surface-dim` #DCDDE6 at 234°,
`outline` #767B8A at 225°, `on-surface-variant` #464A57 at 226°, `on-surface`
#16181F at 227° — sits inside a 224°–234° band, against `primary` #3949CE at 234°.
The neutrals are the primary hue at low chroma, not grey. The reason is
simultaneous contrast: a dense Russian data table is mostly neutral surface with a
few indigo affordances, and a true grey (#F5F5F5, hue undefined) placed next to
#3949CE reads brown. Biasing the ramp to the accent's hue removes that, and the
whole screen reads as one material.

**Roles are single-purpose.** `primary` is the one committing action and the one
inline link, nothing else. `tertiary` #1F6D4A is the confirmed/positive state —
`Оплачено`, `Синхронизировано` — and is never used for emphasis. `error` #B3261E is
destructive and failure only. There is no fourth accent; a system with four accents
has no accent.

**Text steps, with measured ratios.** `on-surface` #16181F is body text and clears
17.73:1 on `surface-container-lowest` and 14.21:1 on `surface-container-highest`.
`on-surface-variant` #464A57 is the secondary step and is the lightest text color in
the system: 7.82:1 on `surface-container` and 7.08:1 on `surface-container-highest`.
There is no third, lighter text step, because the next step down stops clearing
AA on the top of the container ladder.

**Non-text.** `outline` #767B8A reaches 4.09:1 on `surface` — above the 3:1 minimum
for control boundaries, so it is the border of `input-field`. `outline-variant`
#C6C9D6 reaches 1.60:1 and is therefore a decorative divider only. Do not use it as
a control boundary; it does not meet the non-text threshold and this is stated here
so nobody has to rediscover it.

## Typography

Ten scales generated from a single modular sequence: base 16px, ratio **1.125**
(the major second). Steps, rounded to whole pixels:
13 (−2), 14 (−1), 16 (0), 18 (+1), 20 (+2), 23 (+3), 26 (+4), 29 (+5), 32 (+6).
Step +5 (29px) is generated but deliberately unminted — between `display-md` at 26px
and `display-lg` at 32px there is no editorial job for it, and an unused token is a
token someone will misuse. The ratio is 1.125 rather than the more common 1.25
because this is a dense operator interface: at 1.25 the fourth step is already 39px,
which no panel header in this product needs.

**Cyrillic changes the leading, not the sizes.** Russian lowercase is built largely
from cap-height-derived rectangles — `н п и ц ш щ м` — with a small inventory of
ascenders and descenders compared with Latin. The consequence is a taller effective
x-height against the same cap height and a heavier, more uniform band of ink per
line. Lines therefore need more air, not larger type: `body-lg` and `body-md` are set
at `lineHeight: 1.55` and `body-sm` at 1.5, where a Latin-only system would be
comfortable at 1.4. `display-lg` at 1.15 is the floor.

**Tracking is asymmetric by design.** Negative tracking that flatters Latin display
type damages Cyrillic legibility, because Cyrillic display strings pack more vertical
stems per centimetre (`шёлк`, `жизнь`, `мощность`) and the counters close before
Latin's do. The floor in this system is `letterSpacing: -0.005em`, used once, on
`display-lg`. `display-md` sits at −0.0025em. Every `heading-*`, `body-lg`, `body-md`
and `mono-md` token is at exactly `0em`. `body-sm` opens to +0.005em and `label-md`
and `caption` to +0.01em, because small Cyrillic at 13–14px benefits from the
opposite treatment: the letterforms are wide and need the space between them held.

`label-md` carries `fontFeature: "'tnum' 1"`. Numeric columns in `table-header` and
its rows must align between a Russian row and an English one; proportional figures
break that alignment as soon as the locale changes the surrounding string width.

**One export caveat.** `lineHeight` is written unitless here — a multiplier, which is
the correct CSS practice. `design.md export --format css-tailwind` drops unitless
line heights and emits no `--leading-*` variable for them. This is not an error and
not a reason to switch to px; it means the exported Tailwind theme carries sizes and
weights but not leading, and the leading has to be re-applied in the consuming
stylesheet.

## Layout

Base unit **4px**. The eight spacing tokens are 4 × {1, 2, 3, 4, 6, 8, 12, 16} —
4, 8, 12, 16, 24, 32, 48, 64. The multipliers thin out as they grow so that adjacent
steps stay visibly different: at the small end a 4px difference is legible, at the
large end it is not, so 5, 7, 9, 10, 11, 13, 14 and 15 are never minted. A layout
that needs 20px is choosing between `spacing.lg` and `spacing.xl` and must pick one.

Grid: twelve columns, gutter `spacing.lg` (16px), page padding `spacing.xl` (24px) at
desktop and `spacing.lg` at the narrowest breakpoint. `nav-rail` is a fixed 240px —
sized for `Настройки организации` at `label-md`, not for `Org settings`.

**Measure is 68 characters, not 75.** The conventional Latin advice of 66–75
characters per line is a proxy for a physical line length. Cyrillic's average glyph
advance is wider than Latin's at the same point size, so 75 Cyrillic characters is a
physically longer line than 75 Latin ones and overshoots the comfortable range. Prose
columns in this system cap at 68 characters, measured on Russian text; the same
column holds roughly 74 characters of English, which is inside the Latin range. One
measure serves both because it was set from the wider script.

Interactive widths are sized from the Russian string in every case. `Save` →
`Сохранить` is four characters against nine; `Cancel` → `Отменить` is six against
eight; `Settings` → `Настройки` is eight against nine. A button auto-sized in an
English mock will clip or wrap when the locale flips.

## Elevation & Depth

The DESIGN.md component schema has **no elevation or shadow sub-token** — the closed
set is `backgroundColor`, `textColor`, `typography`, `rounded`, `padding`, `size`,
`height`, `width`. Elevation in this file is therefore carried by the part of the
system that *is* machine-readable, the surface-container ladder, and by prose for the
part that is not.

Five levels, each a token, not a shadow:

- Level 0 — `surface` #FBFBFE. The page.
- Level 1 — `surface-container-low` #F5F6FA. `card`.
- Level 2 — `surface-container` #EFF1F7. `table-header`, `code-inline`.
- Level 3 — `surface-container-high` #E9EBF2. `nav-rail`.
- Level 4 — `surface-container-highest` #E3E6EF. Menus, popovers, `language-switch`.

Shadow is additive and used at two levels only: a menu at level 4 takes
`0 4px 12px rgba(22, 24, 31, 0.10)` and a modal takes
`0 12px 32px rgba(22, 24, 31, 0.16)`. Both are `on-surface` at low alpha rather than
black, so the shade stays inside the 224°–234° hue band with everything else. Cards
and rails carry no shadow at all; they are distinguished by the ladder. `tooltip`
inverts instead of elevating: `inverse-surface` reads 12.95:1 against the page,
and its own label pair measures 11.97:1.

## Shapes

Six radii on the 4px grid: `none` 0px, `sm` 4px, `md` 8px, `lg` 12px, `xl` 16px,
`full` 999px. The scale exists to be spent differently across the inventory; a file in
which every component carries `{rounded.md}` has a radius, not a shape system.

Assignment, and it is exhaustive:

- `none` — anything that tiles. `table-header` and its rows. Rounding a cell breaks
  the grid line it shares with its neighbour.
- `sm` — inline and transient surfaces that must not read as objects: `tooltip`,
  `code-inline`.
- `md` — every control the user acts on: `button-primary`, `button-secondary`,
  `button-ghost`, `input-field`. Controls share one radius so they read as one class.
- `lg` — containers that hold controls: `card`, `alert-error`.
- `xl` — full-window surfaces: modals, bottom sheets.
- `full` — pills and toggles whose shape is their meaning: `badge-status`,
  `language-switch`, avatars.

The rule that generates this: radius grows with the size of the thing and drops to
zero for anything that tiles.

## Components

Twelve components. Every one that declares both `backgroundColor` and `textColor`
clears WCAG AA 4.5:1; the measured ratios are below, computed from the resolved hex
values before this file was written.

| Component | Background | Text | Ratio |
| :--- | :--- | :--- | ---: |
| `button-primary` | `primary` #3949CE | `on-primary` #FFFFFF | 6.96:1 |
| `button-secondary` | `secondary-container` #DFE1F9 | `on-secondary-container` #171B2C | 13.24:1 |
| `button-ghost` | `surface` #FBFBFE | `primary` #3949CE | 6.74:1 |
| `input-field` | `surface-container-lowest` #FFFFFF | `on-surface` #16181F | 17.73:1 |
| `card` | `surface-container-low` #F5F6FA | `on-surface` #16181F | 16.42:1 |
| `table-header` | `surface-container` #EFF1F7 | `on-surface-variant` #464A57 | 7.82:1 |
| `nav-rail` | `surface-container-high` #E9EBF2 | `on-surface-variant` #464A57 | 7.42:1 |
| `badge-status` | `tertiary-container` #C7F0D8 | `on-tertiary-container` #00210F | 13.79:1 |
| `alert-error` | `error-container` #F9DEDC | `on-error-container` #410E0B | 12.77:1 |
| `tooltip` | `inverse-surface` #2B2F3A | `inverse-on-surface` #F1F2F8 | 11.97:1 |
| `language-switch` | `surface-container-highest` #E3E6EF | `on-surface` #16181F | 14.21:1 |
| `code-inline` | `surface-container` #EFF1F7 | `on-surface` #16181F | 15.70:1 |

Control heights are literals — 40px for buttons, 44px for `input-field`, 32px for
`language-switch`, 24px for `badge-status` — rather than spacing references. They sit
on the same 4px grid but a control height is not a gap, and binding them to
`spacing.*` would couple two things that change for different reasons.

`input-field` is 44px against the buttons' 40px on purpose: it holds `body-md` at
16px with `lineHeight: 1.55`, and Cyrillic descenders (`р у ф щ д ц`) plus the
looser leading need the extra 4px before the text touches the border.

`language-switch` is a two-segment pill, 88px wide, labelled `РУС` / `ENG`. It
switches strings and locale-dependent formatting only. It does not switch
`fontFamily` — both scripts are served by the same three families, and swapping faces
per locale reintroduces exactly the fallback bug this system exists to prevent.

## Do's and Don'ts

**Do.**

1. Proof a real Cyrillic string before writing any family name into a `typography.*`
   token. Set `Ъ ъ Ы ы Ж ж Ф ф Щ щ Д д Й й` and the pangram
   `Съешь ещё этих мягких французских булок, да выпей же чаю`, and confirm the
   family's declared subsets include `cyrillic`. Two checks, both required.
2. Keep the family list at exactly three: `Golos Text` (display and headings),
   `Inter` (all text and labels), `JetBrains Mono` (code and identifiers). Any
   fourth family must pass step 1 and displace one of these, not join them.
3. Hold `letterSpacing` at or above `-0.005em`. Only `display-lg` reaches the floor;
   `display-md` is at −0.0025em; every `heading-*`, `body-lg`, `body-md` and
   `mono-md` token is exactly `0em`.
4. Hold `lineHeight` at 1.55 for `body-lg` and `body-md`, 1.5 for `body-sm`, 1.45 for
   `caption`. Russian lowercase carries more ink per line than Latin at the same size.
5. Open the tracking at small sizes instead of closing it: `body-sm` +0.005em,
   `label-md` and `caption` +0.01em.
6. Size every control from its Russian label. `Сохранить` (9), `Отменить` (8),
   `Настройки` (9) against `Save` (4), `Cancel` (6), `Settings` (8).
7. Cap prose measure at 68 characters measured on Russian text, not the Latin 75.
8. Keep `fontFeature: "'tnum' 1"` on `label-md` so numeric columns align across a
   locale switch.
9. Keep `on-surface-variant` #464A57 as the lightest text color in the system. It is
   the last step that clears 4.5:1 on `surface-container-highest` (7.08:1).
10. Spend all six radii. If a new component takes `{rounded.md}`, confirm it is a
    control the user acts on; if it is a container, it takes `{rounded.lg}`.

**Don't.**

1. Do not introduce Instrument Serif, Bodoni Moda, or any family shipped with only
   `latin` and `latin-ext`. They do not fail loudly. Latin renders correctly, Cyrillic
   falls back to a system face, and the defect is reported as "the spacing looks off".
2. Do not set `fontFeature: "'smcp' 1"` on any token. None of the three families ships
   Cyrillic small capitals; the browser synthesises them by scaling capitals, and the
   scaled stroke weight does not match the surrounding text. Use `label-md` at
   `fontWeight: 500` with `letterSpacing: 0.01em` where the Latin instinct says
   small caps.
3. Do not uppercase Russian button labels. `СОХРАНИТЬ` is the longest string in the
   interface set in the widest form available, inside a 40px control already sized to
   the Cyrillic lower bound, and `label-md`'s +0.01em tracking is calibrated for mixed
   case.
4. Do not tighten `display-lg` past −0.01em to imitate Latin display setting. Cyrillic
   display strings pack more vertical stems per centimetre — `шёлк`, `жизнь`,
   `мощность` — and the counters close before the equivalent Latin string's do.
5. Do not let a CSS fallback stack contain a Latin-only family. The token names one
   family; the stack in the stylesheet is `"Inter", "Golos Text", sans-serif`. A
   Latin-only face in second position restores the silent-substitution bug at the
   first missing glyph.
6. Do not switch `fontFamily` in `language-switch`. It switches strings and formats.
7. Do not use `primary` #3949CE outside `button-primary`, `button-ghost`, and inline
   links. Status is `tertiary`, destructive is `error`. An accent in three roles is
   not an accent.
8. Do not use `outline-variant` #C6C9D6 as a control boundary — it measures 1.60:1
   against `surface` and misses the 3:1 non-text minimum. Control boundaries are
   `outline` #767B8A at 4.09:1.
9. Do not add a `borderColor`, `elevation`, `gap`, or `opacity` sub-token to a
   component. The set is closed at eight names and the linter returns a `broken-ref`
   warning listing them.
10. Do not translate the eight H2 headings into Russian. The linter matches the
    literal English strings; `## Цвета` resolves to nothing, is filtered out of the
    section list, and `section-order` stops seeing the section entirely. Body prose
    is bilingual; the headings are not.
11. Do not add a poetic color name — `чернила`, `туман`, `brand-1` — while
    `components` is non-empty. Any family outside `primary`/`secondary`/`tertiary`/
    `error`/`surface`/`background`/`outline` that no component references produces an
    `orphaned-tokens` warning per name.

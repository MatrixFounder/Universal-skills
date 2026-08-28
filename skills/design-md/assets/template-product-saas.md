---
version: alpha
name: Fieldbook Console
description: "Dense product-interface system for an operations console: one warm-neutral plane ladder, one ink-navy accent reserved for the primary action, a 4px rhythm."
omitted: []
colors:
  # --- the single accent: ink navy, hue 222 -----------------------------
  primary: "#21418c"
  on-primary: "#fefdfb"
  primary-container: "#dbe3f5"
  on-primary-container: "#12244e"
  inverse-primary: "#97b1ed"
  primary-fixed: "#cad6f2"
  primary-fixed-dim: "#a4b7e5"
  on-primary-fixed: "#0d1b3b"
  on-primary-fixed-variant: "#1d356d"
  surface-tint: "#21418c"
  # --- secondary: the MD3 second-hue slot, filled with neutral ----------
  secondary: "#5d5342"
  on-secondary: "#fefdfb"
  secondary-container: "#e6dfd3"
  on-secondary-container: "#423827"
  # --- tertiary: healthy status, and nothing else -----------------------
  tertiary: "#186742"
  on-tertiary: "#fefdfb"
  tertiary-container: "#d7efe4"
  on-tertiary-container: "#10472d"
  # --- error: failure status and destructive action ---------------------
  error: "#a93023"
  on-error: "#fefdfb"
  error-container: "#fae3e0"
  on-error-container: "#631f17"
  # --- the warm neutral plane ladder, hue 38, dL* = 1.6 -----------------
  background: "#f4f0e9"
  on-background: "#312a1e"
  surface: "#f8f4ed"
  on-surface: "#312a1e"
  surface-variant: "#e0d9cd"
  on-surface-variant: "#625847"
  surface-bright: "#fefdfb"
  surface-dim: "#dcd4c6"
  surface-container-lowest: "#fbf9f5"
  surface-container-low: "#f0ebe2"
  surface-container: "#ece6dc"
  surface-container-high: "#e9e2d6"
  surface-container-highest: "#e4ddd1"
  outline: "#8e7f65"
  outline-variant: "#d8d0c2"
  inverse-surface: "#25211a"
  inverse-on-surface: "#fbf9f5"
typography:
  label-xs:
    fontFamily: "Inter"
    fontSize: 11px
    fontWeight: 600
    lineHeight: 16px
    letterSpacing: 0.04em
  body-sm:
    fontFamily: "Inter"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 16px
    letterSpacing: 0em
  code-sm:
    fontFamily: "JetBrains Mono"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 16px
    letterSpacing: 0em
  body-md:
    fontFamily: "Inter"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 20px
    letterSpacing: 0em
  body-md-strong:
    fontFamily: "Inter"
    fontSize: 14px
    fontWeight: 600
    lineHeight: 20px
    letterSpacing: 0em
  numeric-md:
    fontFamily: "Inter"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 20px
    letterSpacing: 0em
    fontFeature: '"tnum" 1'
  title-sm:
    fontFamily: "Inter"
    fontSize: 16px
    fontWeight: 600
    lineHeight: 24px
    letterSpacing: -0.005em
  title-md:
    fontFamily: "Inter"
    fontSize: 18px
    fontWeight: 600
    lineHeight: 24px
    letterSpacing: -0.01em
  heading-sm:
    fontFamily: "Inter"
    fontSize: 20px
    fontWeight: 600
    lineHeight: 28px
    letterSpacing: -0.015em
  heading-lg:
    fontFamily: "Inter"
    fontSize: 28px
    fontWeight: 700
    lineHeight: 36px
    letterSpacing: -0.02em
rounded:
  none: 0px
  xs: 2px
  sm: 4px
  md: 6px
  lg: 8px
  full: 9999px
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
    typography: "{typography.body-md-strong}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md}"
    height: 32px
  button-secondary:
    backgroundColor: "{colors.secondary-container}"
    textColor: "{colors.on-secondary-container}"
    typography: "{typography.body-md-strong}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md}"
    height: 32px
  button-danger:
    backgroundColor: "{colors.error}"
    textColor: "{colors.on-error}"
    typography: "{typography.body-md-strong}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md}"
    height: 32px
  input-field:
    backgroundColor: "{colors.surface-container-lowest}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm}"
    height: 32px
  filter-chip:
    backgroundColor: "{colors.surface-container}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
    height: 24px
  table-header-cell:
    backgroundColor: "{colors.surface-container}"
    textColor: "{colors.on-surface-variant}"
    typography: "{typography.label-xs}"
    rounded: "{rounded.none}"
    padding: "{spacing.sm}"
    height: 32px
  table-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.none}"
    padding: "{spacing.sm}"
    height: 36px
  table-row-selected:
    backgroundColor: "{colors.surface-container-high}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.none}"
    padding: "{spacing.sm}"
    height: 36px
  table-cell-numeric:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.numeric-md}"
    rounded: "{rounded.none}"
    padding: "{spacing.sm}"
    height: 36px
  nav-item:
    backgroundColor: "{colors.background}"
    textColor: "{colors.on-surface-variant}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm}"
    height: 32px
    width: 224px
  nav-item-active:
    backgroundColor: "{colors.surface-container-highest}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md-strong}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm}"
    height: 32px
    width: 224px
  badge-neutral:
    backgroundColor: "{colors.surface-container-highest}"
    textColor: "{colors.on-surface-variant}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.xs}"
    padding: "{spacing.xs}"
    height: 20px
    size: "{spacing.sm}"
  badge-healthy:
    backgroundColor: "{colors.tertiary-container}"
    textColor: "{colors.on-tertiary-container}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.xs}"
    padding: "{spacing.xs}"
    height: 20px
    size: "{spacing.sm}"
  badge-failed:
    backgroundColor: "{colors.error-container}"
    textColor: "{colors.on-error-container}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.xs}"
    padding: "{spacing.xs}"
    height: 20px
    size: "{spacing.sm}"
---

## Overview

Fieldbook Console is the design system for a dense operations application:
dispatch queues, reconciliation grids, inventory ledgers. The screen the system
is designed around is a table of 200 to 2000 rows with a persistent filter bar
above it, a 224px navigation rail on the left, and an edit form in a right
panel. Operators sit in front of it for a full shift and read it, not admire it.

Two decisions govern everything below.

**One hue bias for all neutrals.** Every neutral in this file is placed on a
single warm axis at hue 38 degrees. Measured back from the shipped hex values,
the eleven light planes fall between 37.5 and 40.0 degrees and the six ink
values between 37.8 and 38.2. No neutral is a pure grey and no neutral wanders
off the axis. The bias is warm rather than cool because the primary surface is
a document the operator reads for eight hours; a warm ground reads as paper and
lowers the perceived glare of a large white table, while a cool ground reads as
screen. The bias is deliberately shallow. Measured HSL saturation runs 60
percent at `surface-bright` down to 22 percent at `outline-variant`, and at
near-white lightness that first number badly overstates the effect:
`surface-bright` is `#fefdfb`, a three-point spread between the red and blue
channels. At the dark end of the ladder `outline-variant` is `#d8d0c2`, a
twenty-two-point spread. Three points at the top, twenty-two at the bottom —
visible as warmth at every rung, never as beige.

**One accent, one role.** `primary` (`#21418c`) is used in exactly one place:
the fill of `button-primary`. It is not the selection colour, not the link
colour, not the focus ring, not the healthy-status colour, not a heading
colour. In a grid of 2000 rows, a colour that means four things means nothing;
a colour that appears once per screen is a wayfinding device. Section "Do's and
Don'ts" names what carries each of the other roles.

**What this file defines.** All five token sections are populated, so `omitted`
is empty. Naming a populated section in `omitted` raises `redundant-omission`,
so the list stays empty rather than decorative.

**What this file does not define.** There is no dark theme here; the `*-fixed`
tokens are the subset promised to survive unchanged when one is added. There
are no `scrim` or `shadow` tokens: the DESIGN.md component sub-token set is
closed (`backgroundColor`, `textColor`, `typography`, `rounded`, `padding`,
`size`, `height`, `width`) and contains no shadow slot, so a shadow token could
never be referenced by a component. Depth is expressed by plane, described in
"Elevation & Depth" as prose, which is where this format puts it.

## Colors

### The plane ladder

Eleven light planes, specified at a constant perceptual step of dL* = 1.6 and
rounded to 8-bit sRGB. Measured after rounding, the steps land between 1.36 and
1.77. The ladder is what carries depth in this system, so the step is uniform
by construction rather than by eye.

| Token | Hex | L* | Measured hue | Role |
| :--- | :--- | ---: | ---: | :--- |
| `surface-bright` | `#fefdfb` | 99.33 | 40.0 | popover and dropdown ground |
| `surface-container-lowest` | `#fbf9f5` | 97.97 | 40.0 | input well, editable cell |
| `surface` | `#f8f4ed` | 96.32 | 38.2 | the data sheet — table body |
| `background` | `#f4f0e9` | 94.92 | 38.2 | app shell behind the sheet, nav rail |
| `surface-container-low` | `#f0ebe2` | 93.20 | 38.6 | toolbar, panel header |
| `surface-container` | `#ece6dc` | 91.50 | 37.5 | table header row, filter chip |
| `surface-container-high` | `#e9e2d6` | 90.12 | 37.9 | selected table row |
| `surface-container-highest` | `#e4ddd1` | 88.36 | 37.9 | active nav item, neutral badge |
| `surface-variant` | `#e0d9cd` | 86.94 | 37.9 | scrollbar track, progress trough |
| `surface-dim` | `#dcd4c6` | 85.19 | 38.2 | disabled control fill |
| `outline-variant` | `#d8d0c2` | 83.76 | 38.2 | hairline between table rows |

Note the direction: in this light theme, containers get *darker* as their
emphasis rises. That is the MD3 light-mode convention and it is the reason the
system needs no shadows.

### The ink range

Below `outline-variant` the ladder stops and jumps 30 L* points. That gap is
intentional: everything above it is a surface, everything below it is a mark on
a surface, and there is no value in between to be ambiguous about.

| Token | Hex | L* | Measured hue | Role |
| :--- | :--- | ---: | ---: | :--- |
| `outline` | `#8e7f65` | 53.89 | 38.0 | control borders, focus-less field edge |
| `on-surface-variant` | `#625847` | 37.90 | 37.8 | column headers, metadata, ids |
| `secondary` | `#5d5342` | 35.80 | 37.8 | form labels, nav section captions |
| `on-secondary-container` | `#423827` | 24.11 | 37.8 | label on the quiet button |
| `on-surface` / `on-background` | `#312a1e` | 17.47 | 37.9 | all primary reading text |
| `inverse-surface` | `#25211a` | 12.96 | 38.2 | focus ring, toast ground |

`secondary` deserves a sentence. Material's token model reserves that family
for a second chroma. This system fills it with the same 38-degree neutral at
ink lightness. That substitution *is* the one-accent policy stated in tokens:
the format offers a slot for a second hue and the system declines it.

### The accent and the two status hues

| Family | Base hex | Hue | Permitted use |
| :--- | :--- | ---: | :--- |
| `primary` | `#21418c` | 222 | the fill of `button-primary`, once per screen |
| `tertiary` | `#186742` | 152 | the healthy status badge |
| `error` | `#a93023` | 6 | the failed status badge and the destructive button |

Three chroma hues, three jobs, no overlap. `primary` sits 184 degrees from the
neutral axis, so an ink-navy button on warm paper can never be mistaken for a
darker plane. `tertiary` and `error` are status vocabulary, not accents: they
only ever appear as a 20px badge, never as a fill behind reading text and never
as a button except `button-danger`.

Measured against `surface`, `primary` is 8.71:1, `error` 6.11:1 and `tertiary`
6.26:1 — all three are legible as text on the sheet if a future component needs
them there.

`surface-tint` is defined at the `primary` value for MD3 parity only. Nothing
in this system applies it. Tinting the planes toward 222 would break the single
hue bias, which is the property the whole neutral ramp exists to have.

## Typography

**Families.** `Inter` for interface text, `JetBrains Mono` for identifiers and
raw values. Both ship Cyrillic coverage, so a shipment id, a carrier name or an
operator note renders in the intended face in Russian as well as in English —
`Отгрузка 4417` and `Shipment 4417` are the same face, the same weight and the
same rhythm. A display family with `latin` and `latin-ext` subsets only would
fall back silently to a system face on the first Cyrillic string, which in a
console is a defect that reaches production unnoticed.

**Scale.** Base 14px, ratio 1.125 (a major second). 14px is the base because it
is the smallest size at which Inter's lowercase stays comfortable for a full
shift, and because 14/20 fits the 4px vertical grid exactly.

The arithmetic, exact value then the shipped integer:

| Step | Arithmetic | Exact | Shipped | Token |
| ---: | :--- | ---: | ---: | :--- |
| -2 | 14 / 1.125^2 | 11.06 | 11px | `label-xs` |
| -1 | 14 / 1.125 | 12.44 | 12px | `body-sm`, `code-sm` |
| 0 | 14 | 14.00 | 14px | `body-md`, `body-md-strong`, `numeric-md` |
| +1 | 14 x 1.125 | 15.75 | 16px | `title-sm` |
| +2 | 14 x 1.125^2 | 17.72 | 18px | `title-md` |
| +3 | 14 x 1.125^3 | 19.93 | 20px | `heading-sm` |
| +4 | 14 x 1.125^4 | 22.42 | — | not exposed |
| +5 | 14 x 1.125^5 | 25.23 | — | not exposed |
| +6 | 14 x 1.125^6 | 28.38 | 28px | `heading-lg` |

Steps +4 and +5 are computed and then dropped. A console page has exactly two
levels above the panel title — the page title and the section heading — and
three sizes between 20 and 28 would be three sizes nobody could tell apart at a
glance. The gap from 20 to 28 is the one place the ladder skips, and it skips
on purpose.

**Line heights are absolute, not multipliers.** Every `lineHeight` is a px
value and every one is a multiple of 4 — the ten scales use 16, 20, 24, 28 and
36. A dense grid aligns to a 4px vertical rhythm, and a unitless multiplier of
1.5 on a 14px body produces 21px, which is off the grid and drifts a row out of
alignment after twenty rows. Absolute line heights also survive `export
--format css-tailwind`, which drops unitless values.

**Weight and tracking.** Three weights: 400 for reading text, 600 for emphasis
and headings, 700 for the page title only. Tracking is positive once, at
`label-xs` (+0.04em), because 11px column headers are set in small caps and
need the air; it goes negative and grows with size (-0.005em at 16px through
-0.02em at 28px) to compensate for the optical loosening of large text.

**Tabular figures.** `numeric-md` is `body-md` with `fontFeature: '"tnum" 1'`.
Inter's proportional digits vary in width, which in a column of 800 quantities
makes the decimal point wander. `code-sm` uses JetBrains Mono for values that
must be compared character by character — ids, hashes, tracking numbers. No
component owns `code-sm`: an identifier cell is `table-row` with the face
substituted, because it differs from a text cell in face alone and not in
colour, height or padding.

## Layout

**Base unit: 4px.** Every spacing token is a multiple of it. 4 rather than 8
because a console packs a 32px control, a 20px badge and a 36px row into the
same toolbar; an 8px base would force every one of those to round to 40, and
the screen would hold thirty percent fewer rows.

| Token | Value | Multiple | Typical use |
| :--- | ---: | ---: | :--- |
| `xs` | 4px | 1x | badge inset, icon-to-label gap |
| `sm` | 8px | 2x | table cell padding, input inset, nav item inset |
| `md` | 12px | 3x | button horizontal padding, column gutter |
| `lg` | 16px | 4x | panel inset, form field vertical gap |
| `xl` | 24px | 6x | gap between form groups |
| `2xl` | 32px | 8x | panel-to-panel gap |
| `3xl` | 48px | 12x | page top margin |
| `4xl` | 64px | 16x | empty-state vertical inset |

The ladder is 4 x {1, 2, 3, 4, 6, 8, 12, 16}: consecutive multiples through
`lg`, then doubling. Dense interiors need every rung between 4 and 16; page-
level gaps do not need 20 and 28.

**Frame.** Navigation rail 224px (56 x 4) fixed, no collapse. Filter bar 48px
tall on `surface-container-low`. Table body on `surface`, rows 36px, header row
32px and sticky. Right edit panel 384px (96 x 4). Column gutters `md`.

**Density arithmetic.** A 36px row with a 20px `body-md` line box leaves 8px
above and below, which equals `sm`. At 1080px of viewport height minus a 48px
filter bar and a 32px header, that is 27 rows visible without scrolling. This
number is the reason the row is 36 and not 40.

## Elevation & Depth

This system has no shadows and no elevation tokens. There is a mechanical
reason and a design reason, and both matter.

The mechanical reason: the DESIGN.md component sub-token set is closed and
contains no shadow or elevation slot. Any token named `elevation-1` would be
defined and then unreferenceable from a component, which is exactly the shape
of a token nobody maintains.

The design reason: on a screen showing 27 simultaneous rows, a drop shadow on
each of five stacked containers produces a haze rather than a hierarchy. Depth
here is a step on the plane ladder. Every step is dL* = 1.6, which is enough to
separate two adjacent planes and not enough to read as a colour change.

The depth order, low to high:

1. `background` (`#f4f0e9`) — the shell the app sits on.
2. `surface` (`#f8f4ed`) — the data sheet. Note it is *lighter* than the shell.
3. `surface-container-low` (`#f0ebe2`) — the toolbar over the sheet.
4. `surface-container` (`#ece6dc`) — the sticky header row.
5. `surface-container-high` (`#e9e2d6`) — the selected row.
6. `surface-container-highest` (`#e4ddd1`) — the active nav item.
7. `surface-bright` (`#fefdfb`) — the popover, which leaves the ladder upward
   because it is the only element that floats free of the sheet.

Exactly one shadow is permitted in the implementation and it is described here
rather than tokenised: the popover and dropdown carry `0 4px 12px` at 12 percent
of `inverse-surface`. It is allowed because a popover overlaps content it must
be readable against, and the plane ladder alone cannot express overlap.

Boundaries do the rest of the work. `outline-variant` (`#d8d0c2`) draws the 1px
rule between table rows. `outline` (`#8e7f65`) draws control borders. Measured
against every plane it can sit on: 3.84:1 on `surface-bright`, 3.72:1 on
`surface-container-lowest`, 3.56:1 on `surface`, 3.44:1 on `background`, 3.29:1
on `surface-container-low`, 3.15:1 on `surface-container`, 3.04:1 on
`surface-container-high` — all above the WCAG 3:1 minimum for non-text
boundaries. On `surface-container-highest` it falls to 2.90:1 and stops
qualifying, so that one plane carries no hairline — see "Do's and Don'ts".

## Shapes

Six radii, five of them small. A dense grid is a set of rectangles, and a
rectangle with a large radius loses horizontal space at exactly the point where
a column label needs it.

| Token | Value | Applied to |
| :--- | ---: | :--- |
| `none` | 0px | every table cell, header cell and row — the grid is square |
| `xs` | 2px | status badges |
| `sm` | 4px | buttons, inputs, nav items — the system default |
| `md` | 6px | dropdown and popover panels |
| `lg` | 8px | the right edit panel and modal dialogs |
| `full` | 9999px | filter chips, and only filter chips |

The ladder is 0 / 2 / 4 / 6 / 8, a 2px arithmetic progression, and then one
pill. The progression is arithmetic rather than geometric because at these
magnitudes a geometric ratio would produce 2 / 3 / 4.5 / 6.75, and sub-pixel
radii render inconsistently across browsers at 1x.

`full` carries meaning in this system: a pill outline means "this element is
removable". Filter chips are removable. Buttons are not. A pill-shaped button
would tell an operator they can dismiss the primary action.

## Components

Fourteen components. Every `backgroundColor` / `textColor` pair below was
computed against WCAG AA 4.5:1 before it was written; measured ratios are in
the last column.

| Component | Background | Text | Height | Radius | Ratio |
| :--- | :--- | :--- | ---: | :--- | ---: |
| `button-primary` | `primary` | `on-primary` | 32px | `sm` | 9.39:1 |
| `button-secondary` | `secondary-container` | `on-secondary-container` | 32px | `sm` | 8.68:1 |
| `button-danger` | `error` | `on-error` | 32px | `sm` | 6.59:1 |
| `input-field` | `surface-container-lowest` | `on-surface` | 32px | `sm` | 13.49:1 |
| `filter-chip` | `surface-container` | `on-surface` | 24px | `full` | 11.43:1 |
| `table-header-cell` | `surface-container` | `on-surface-variant` | 32px | `none` | 5.63:1 |
| `table-row` | `surface` | `on-surface` | 36px | `none` | 12.94:1 |
| `table-row-selected` | `surface-container-high` | `on-surface` | 36px | `none` | 11.02:1 |
| `table-cell-numeric` | `surface` | `on-surface` | 36px | `none` | 12.94:1 |
| `nav-item` | `background` | `on-surface-variant` | 32px | `sm` | 6.15:1 |
| `nav-item-active` | `surface-container-highest` | `on-surface` | 32px | `sm` | 10.51:1 |
| `badge-neutral` | `surface-container-highest` | `on-surface-variant` | 20px | `xs` | 5.18:1 |
| `badge-healthy` | `tertiary-container` | `on-tertiary-container` | 20px | `xs` | 8.85:1 |
| `badge-failed` | `error-container` | `on-error-container` | 20px | `xs` | 9.85:1 |

Notes on specific components.

`button-primary` is the only element in the whole system carrying `primary`. A
screen with two of them has two primary actions, which means it has none.

`button-secondary` is filled, not outlined. An outlined button at 32px on a
warm ground needs an `outline` border at 3.15:1, and next to a filled primary
button the pair reads as one button and one placeholder. A filled quiet button
on `secondary-container` reads as a peer.

`table-header-cell` is the only place `label-xs` appears: 11px, weight 600,
+0.04em tracking, `on-surface-variant` on `surface-container` at 5.63:1. It is
the smallest text in the system and it is deliberately the only 11px text.

`table-row` and `table-cell-numeric` share both colours and differ only in
typography — `body-md` versus `numeric-md`. That is the point: a numeric column
is not a different colour of cell, it is the same cell with tabular figures.

`nav-item` sits on `background`, one plane below the sheet, which is what makes
the rail read as chrome rather than content. `nav-item-active` steps to
`surface-container-highest` — four rungs darker on the ladder — and switches to
weight 600.
Selection in the rail is expressed by plane and weight, never by `primary`.

`badge-*` all use `size: {spacing.sm}` for the 8px status dot at the leading
edge, so status survives a greyscale print and a colour-blind operator.

## Do's and Don'ts

These rules are specific to Fieldbook Console. Each one names its own tokens
and can be checked against a built screen or against this file.

### Do

1. Use `{colors.primary}` as `backgroundColor` exactly once in this file, on
   `button-primary`. A second occurrence is a defect, not a variant.
2. Carry every other accent role with a neutral: selection is
   `table-row-selected` (`surface-container-high`, one plane step) plus a 2px
   `inverse-surface` left rule; the focus ring is 2px `inverse-surface` at 2px
   offset (14.61:1 on `surface`); in-cell links are `on-surface` with an
   underline; status is a `badge-*` component.
3. Draw hairlines with `outline` on any plane from `surface-bright` down to
   `surface-container-high`, where the ratio stays between 3.84:1 and 3.04:1.
   On `surface-container-highest` it is 2.90:1, below the 3:1 non-text minimum:
   separate that plane by a ladder step instead of by a rule.
4. Keep every row, control and inset height a multiple of 4. The sticky header
   offset is computed from row height; a 34px row desynchronises it after ten
   rows.
5. Set every numeric column in `numeric-md` and every identifier column in
   `code-sm`. A quantity column in `body-md` misaligns its decimal points.
6. Keep `secondary`, `on-secondary-container` and `secondary-container` on the
   38-degree axis. If any of them measures outside 37 to 40 degrees, the system
   has acquired a second accent and the check has caught it.
7. Limit a page to two sizes above `title-md`: `heading-lg` for the page title,
   `heading-sm` for section headings. Steps +4 and +5 of the scale are not
   exposed and must not be reintroduced.
8. Express every new depth level as an existing `surface-container-*` step.
   The ladder has five container rungs and a bright plane; that is the budget.

### Don't

1. Do not add an amber or orange status colour. The neutral axis is already at
   hue 38; an amber chip at 20px on `surface-container-highest` is
   indistinguishable from the ground. Detection: any status token measuring
   between 20 and 60 degrees of hue.
2. Do not apply `surface-tint`. It exists at the `primary` value for MD3
   parity only. Detection: a plane whose measured hue leaves 37 to 40 degrees.
3. Do not use `{rounded.full}` on anything but `filter-chip`. In this system a
   pill means removable. Detection: a component with `rounded: {rounded.full}`
   and no dismiss affordance.
4. Do not introduce a radius above `{rounded.lg}` (8px). Detection: a `rounded`
   entry between 9px and 9998px.
5. Do not introduce a font size off the ladder. The permitted set is exactly
   11, 12, 14, 16, 18, 20, 28. Detection: any `fontSize` outside it.
6. Do not substitute `system-ui` or a Latin-only display family for `Inter`.
   Detection: a Cyrillic string rendering in a different face than the Latin
   text beside it.
7. Do not put a drop shadow on a table row, a header cell or a nav item. The
   only permitted shadow is the popover's, and it is prose, not a token,
   because the component sub-token set has no shadow slot.
8. Do not set 11px `label-xs` in `on-surface-variant` on any plane darker than
   `surface-container`. On `surface-container-highest` that pair measures
   5.18:1 — legal under AA, and the thinnest text in the system. Use
   `on-surface` there.
9. Do not name a populated section in `omitted`. All five sections here carry
   tokens, so `omitted` stays `[]`; naming one raises `redundant-omission`.

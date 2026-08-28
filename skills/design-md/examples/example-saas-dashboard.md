---
version: alpha
name: Kestrel Control
description: "Design system for the Kestrel Freight dispatch board, extracted from one light-theme screenshot and a short brand brief."
omitted:
  - section: spacing
    reason: "Every gap measured on the board is a multiple of 4px, but a single screen cannot separate scale steps from one-off values, and steps that no visible element uses would be invention. Component padding is recorded as measured literals instead; the scale is deferred until a form screen and a detail drawer are supplied."
colors:
  primary: "#0F4C81"
  on-primary: "#FFFFFF"
  primary-container: "#D6E4F3"
  on-primary-container: "#0A3157"
  secondary: "#4B5C6B"
  on-secondary: "#FFFFFF"
  secondary-container: "#DEE4EA"
  on-secondary-container: "#1C2732"
  tertiary: "#176B5A"
  on-tertiary: "#FFFFFF"
  tertiary-container: "#CDE9E1"
  on-tertiary-container: "#06342A"
  error: "#B3261E"
  on-error: "#FFFFFF"
  error-container: "#F9DEDC"
  on-error-container: "#410E0B"
  background: "#F4F6F8"
  on-background: "#14181C"
  surface: "#FFFFFF"
  surface-container-low: "#F7F9FA"
  surface-container: "#F1F4F6"
  surface-container-high: "#EBEFF2"
  surface-container-highest: "#E4E9ED"
  surface-variant: "#DFE5EA"
  on-surface: "#14181C"
  on-surface-variant: "#47535F"
  inverse-surface: "#1F2933"
  inverse-on-surface: "#F0F3F5"
  outline: "#78848F"
  outline-variant: "#C7D0D8"
  status-delayed: "#FBE3B8"
  on-status-delayed: "#5A3A05"
  status-hold: "#E4DDF6"
  on-status-hold: "#3A2A63"
typography:
  headline-sm:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: -0.01em
  title-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 600
    lineHeight: 1.4
  title-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.4
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.45
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0.04em
  numeric-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.4
    fontFeature: '"tnum" 1, "zero" 1'
  numeric-lg:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: -0.02em
    fontFeature: '"tnum" 1, "zero" 1'
rounded:
  sm: 4px
  md: 6px
  lg: 10px
  full: 999px
components:
  board-canvas:
    backgroundColor: "{colors.background}"
    textColor: "{colors.on-background}"
    padding: 24px
    typography: "{typography.body-md}"
  app-bar:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    height: 56px
    padding: 0px 16px
    typography: "{typography.title-md}"
  nav-rail:
    backgroundColor: "{colors.surface-container}"
    textColor: "{colors.on-surface-variant}"
    width: 72px
    padding: 8px
    typography: "{typography.label-sm}"
  card-kpi:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: 20px
    typography: "{typography.numeric-lg}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 10px 16px
    height: 40px
    typography: "{typography.title-sm}"
  button-outline:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.md}"
    padding: 10px 16px
    height: 40px
    typography: "{typography.title-sm}"
  button-danger:
    backgroundColor: "{colors.error}"
    textColor: "{colors.on-error}"
    rounded: "{rounded.md}"
    padding: 10px 16px
    height: 40px
    typography: "{typography.title-sm}"
  input-search:
    backgroundColor: "{colors.surface-container-low}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    height: 36px
    padding: 0px 12px
    typography: "{typography.body-md}"
  menu-filter:
    backgroundColor: "{colors.surface-container-highest}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: 8px
    typography: "{typography.body-md}"
  table-header:
    backgroundColor: "{colors.surface-container-high}"
    textColor: "{colors.on-surface-variant}"
    height: 36px
    padding: 0px 12px
    typography: "{typography.label-sm}"
  table-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    height: 44px
    padding: 0px 12px
    typography: "{typography.body-md}"
  table-row-alt:
    backgroundColor: "{colors.surface-container-low}"
    textColor: "{colors.on-surface}"
    height: 44px
    padding: 0px 12px
    typography: "{typography.body-md}"
  table-cell-numeric:
    textColor: "{colors.on-surface}"
    padding: 0px 12px
    typography: "{typography.numeric-md}"
  table-cell-muted:
    textColor: "{colors.on-surface-variant}"
    padding: 0px 12px
    typography: "{typography.body-sm}"
  divider:
    backgroundColor: "{colors.outline-variant}"
    height: 1px
  divider-section:
    backgroundColor: "{colors.outline}"
    height: 1px
  chip-scheduled:
    backgroundColor: "{colors.surface-variant}"
    textColor: "{colors.on-surface-variant}"
    rounded: "{rounded.full}"
    height: 22px
    padding: 2px 10px
    typography: "{typography.label-md}"
  chip-in-transit:
    backgroundColor: "{colors.primary-container}"
    textColor: "{colors.on-primary-container}"
    rounded: "{rounded.full}"
    height: 22px
    padding: 2px 10px
    typography: "{typography.label-md}"
  chip-delayed:
    backgroundColor: "{colors.status-delayed}"
    textColor: "{colors.on-status-delayed}"
    rounded: "{rounded.full}"
    height: 22px
    padding: 2px 10px
    typography: "{typography.label-md}"
  chip-hold:
    backgroundColor: "{colors.status-hold}"
    textColor: "{colors.on-status-hold}"
    rounded: "{rounded.full}"
    height: 22px
    padding: 2px 10px
    typography: "{typography.label-md}"
  chip-delivered:
    backgroundColor: "{colors.tertiary-container}"
    textColor: "{colors.on-tertiary-container}"
    rounded: "{rounded.full}"
    height: 22px
    padding: 2px 10px
    typography: "{typography.label-md}"
  chip-exception:
    backgroundColor: "{colors.error-container}"
    textColor: "{colors.on-error-container}"
    rounded: "{rounded.full}"
    height: 22px
    padding: 2px 10px
    typography: "{typography.label-md}"
  badge-count:
    backgroundColor: "{colors.secondary-container}"
    textColor: "{colors.on-secondary-container}"
    rounded: "{rounded.full}"
    height: 18px
    padding: 0px 6px
    typography: "{typography.label-sm}"
  avatar-driver:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.on-secondary}"
    rounded: "{rounded.full}"
    size: 28px
    typography: "{typography.label-sm}"
  meter-on-time:
    backgroundColor: "{colors.tertiary}"
    rounded: "{rounded.full}"
    height: 6px
  banner-exception:
    backgroundColor: "{colors.error-container}"
    textColor: "{colors.on-error-container}"
    rounded: "{rounded.md}"
    padding: 12px 16px
    typography: "{typography.body-md}"
  tooltip:
    backgroundColor: "{colors.inverse-surface}"
    textColor: "{colors.inverse-on-surface}"
    rounded: "{rounded.sm}"
    padding: 6px 8px
    typography: "{typography.body-sm}"
  tag-lane:
    backgroundColor: "{colors.surface-container-high}"
    textColor: "{colors.on-surface-variant}"
    rounded: "{rounded.sm}"
    height: 20px
    padding: 0px 6px
    typography: "{typography.label-sm}"
---

## Overview

Kestrel Control is the dispatch and exception board for Kestrel Freight, a regional
LTL carrier running cross-border lanes out of three depots. Roughly forty dispatchers
use it for a full shift, on 24-inch desk monitors and on wall-mounted depot terminals.
The board is one dense table of live shipments plus a KPI band; everything else in the
product is a drawer over that table.

The brand brief asked for "instrument panel, not marketing site": legible at a glance
from two metres, no decoration that competes with a status, and nothing that changes
appearance between the office and the depot.

### Inputs to this extraction

| Input | What it was |
| :--- | :--- |
| `inputs/board-2026-08-24.png` | One screenshot, 1440x900, light theme, the Shipments board with 214 rows visible, taken at 09:12 local |
| `inputs/brand-brief.md` | 180 words from the operations lead: audience, viewing distance, tone, the phrase quoted above |

No stylesheet, no Figma file, and no token file were available. Everything below comes
from those two inputs or is marked as derived from them.

### Reliability ledger

This is the part of the file to read before trusting any value in it. The three columns
are not a disclaimer; they decide where a value is allowed to live.

| Measured | Inferred | Not derivable |
| :--- | :--- | :--- |
| The twelve surface and status hexes with >0.2% pixel coverage | The `on-*` text colour of every chip and button | Interaction states: hover, focus, active, disabled |
| Corner radii: 4, 6, 10 px and the pill | The typographic ratio behind the measured sizes | The dark theme |
| Rendered type sizes: 11, 12, 14, 16, 20, 28 px | Font family: three candidates, one provisionally chosen | Motion, transitions, loading behaviour |
| Row, header, control and rail dimensions | Font weights: 400 / 500 / 600 read from stem width | Elevation values as numbers (blur, spread, alpha) |
| That every gap is a multiple of 4px | Which measured gaps are scale steps | Any screen that is not the board |

Consequences, in the file:

- Measured values are written as literals with no hedging.
- Inferred values are written into the file (a file with no typography is not usable)
  and are named as inferences here and in the section that owns them.
- Not-derivable values are absent. `spacing` is the one case the format can express
  machine-readably, so it carries an `omitted` entry with a reason. The rest are
  recorded in prose below, because `omitted` accepts exactly five section names --
  `colors`, `typography`, `spacing`, `rounded`, `components` -- and "dark theme",
  "states" and "motion" are not among them.

### What would close the gaps

One dark-theme screenshot of the same board; one hover and one focus state of a table
row; one form screen and one detail drawer for the spacing ladder; a one-line answer
from the front-end team naming the font. Until those arrive, this file is the light
theme, at rest, of one screen.

## Colors

### How the values were obtained

Colours were read by pixel quantisation of the screenshot, not by eye. Eye-read hexes
from a screenshot are unreliable: JPEG-era compression, subpixel antialiasing, the
1px hairlines and the monitor profile all shift them, and the shift is largest exactly
on the small coloured areas that carry status meaning.

Twelve colours cleared 0.2% of the frame:

| Hex | Share | Read as | Where it appears |
| :--- | ---: | :--- | :--- |
| `#FFFFFF` | 41.6% | `surface` | Card and row fill |
| `#F4F6F8` | 22.3% | `background` | Board canvas behind the cards |
| `#14181C` | 9.1% | `on-surface` | Primary text |
| `#F1F4F6` | 6.8% | `surface-container` | Navigation rail |
| `#47535F` | 4.4% | `on-surface-variant` | Column headers, secondary cell text |
| `#0F4C81` | 2.1% | `primary` | One filled button, the active rail item |
| `#C7D0D8` | 1.7% | `outline-variant` | Table hairlines |
| `#EBEFF2` | 1.2% | `surface-container-high` | Table header band |
| `#FBE3B8` | 0.9% | `status-delayed` | Delayed chips, 31 of 214 rows |
| `#CDE9E1` | 0.7% | `tertiary-container` | Delivered chips |
| `#F9DEDC` | 0.3% | `error-container` | Exception chips, 4 rows |
| `#E4DDF6` | 0.2% | `status-hold` | Customs-hold chips |

The residual 8.7% is antialiasing, the logo, and a map thumbnail; none of it is a token.

Everything else in the `colors` map is **derived**, not measured:

- Every `on-*` value. Chip and button label text occupies too few pixels to quantise:
  at 11-12px the label is more antialiased edge than solid fill. Each `on-*` colour was
  therefore computed against its own container to a target of 7:1 and is stated here as
  derived, not read.
- `secondary`, `tertiary`, `error` as solid fills. The screenshot shows only their
  container tints. The solids are the same hue darkened to clear 4.5:1 against white.
- `surface-container-low`, `surface-container-highest`, `surface-variant`, `outline`.
  These fill out the ladder between the four measured surface levels.
- `inverse-surface` / `inverse-on-surface`. The board shows a tooltip whose fill is
  dark, but it was captured mid-fade; the pair is a reconstruction.

### Roles

`primary` has exactly one job on this board: the single committing action in a view,
which is *Assign carrier*. It is not the link colour, not the chart colour, not the
brand colour in the header. `secondary` is people -- driver avatars, assignment badges.
`tertiary` is time performance -- the on-time meter, and the delivered end-state.

### Status vocabulary

Six operational states, six chips, and the mapping is fixed:

| State | Component | Hue source |
| :--- | :--- | :--- |
| Scheduled, not yet picked up | `chip-scheduled` | `surface-variant`, deliberately colourless |
| In transit, on plan | `chip-in-transit` | `primary-container` |
| Delayed against ETA | `chip-delayed` | `status-delayed`, custom family |
| Held at customs or by consignee | `chip-hold` | `status-hold`, custom family |
| Delivered, POD received | `chip-delivered` | `tertiary-container` |
| Exception: damage, refusal, undeliverable | `chip-exception` | `error-container` |

Four of the six reuse MD3 families. Two do not, and the reason is specific rather than
aesthetic: MD3 has no slot for an amber and no slot for a neutral-violet, and this
domain needs both, because "late" and "held" are different problems with different
owners -- late belongs to the dispatcher, held belongs to the customs desk. Collapsing
them into one warning colour would merge two queues that must not merge.

Custom families cost something in this format. A colour token whose family is outside
the MD3 baseline is reported as orphaned unless a component references it, so
`status-delayed`, `on-status-delayed`, `status-hold` and `on-status-hold` each earn
their place by being referenced from `chip-delayed` and `chip-hold`. Adding a seventh
status colour with no chip behind it would be a warning, and correctly so.

### Contrast

The linter checks component pairs at WCAG AA 4.5:1. Every pair in this file was also
measured at AAA 7:1, because the board is read at two metres on a depot terminal:

| Pair | Ratio | Verdict |
| :--- | ---: | :--- |
| `on-surface` on `surface` | 17.84:1 | AAA |
| `on-surface` on `surface-container-low` | 16.89:1 | AAA |
| `on-background` on `background` | 16.47:1 | AAA |
| `inverse-on-surface` on `inverse-surface` | 13.24:1 | AAA |
| `on-error-container` on `error-container` | 12.77:1 | AAA |
| `on-secondary-container` on `secondary-container` | 11.83:1 | AAA |
| `on-tertiary-container` on `tertiary-container` | 10.66:1 | AAA |
| `on-primary-container` on `primary-container` | 10.22:1 | AAA |
| `on-status-hold` on `status-hold` | 9.44:1 | AAA |
| `on-primary` on `primary` | 8.86:1 | AAA |
| `primary` on `surface` | 8.86:1 | AAA |
| `on-status-delayed` on `status-delayed` | 8.22:1 | AAA |
| `on-surface-variant` on `surface` | 7.86:1 | AAA |
| `on-surface-variant` on `surface-container` | 7.12:1 | AAA |
| `on-secondary` on `secondary` | 6.90:1 | AA |
| `on-surface-variant` on `surface-container-high` | 6.80:1 | AA |
| `on-error` on `error` | 6.54:1 | AA |
| `on-tertiary` on `tertiary` | 6.39:1 | AA |

Four pairs sit between AA and AAA, and they are not equivalent. `on-secondary` on
`secondary` and `on-error` on `error` carry 14px/600 button labels and 11px/500 avatar
initials -- short, bold, and read in bursts. `on-tertiary` on `tertiary` is defined but
not applied anywhere: `meter-on-time` uses the fill with no label over it, so the pair
is a reserve, and it is the one to fix first if a label is ever put on the meter.

The pair that matters is `on-surface-variant` on `surface-container-high` at 6.80:1 --
the column-header band, on screen for the whole shift. It is accepted only because the
band is the lightest tint that still separates the header from row one. If the band is
ever darkened, this pair moves first.

Note what this costs to know: the linter checks four of these pairs, because it only
looks at components that set both `backgroundColor` and `textColor`, and only against
4.5:1. The AAA column above came from checking every text-on-surface pair separately.

`outline` (3.82:1 on `surface`) and `outline-variant` (1.56:1) are non-text tokens and
are never a component's `textColor`. `outline` clears the 3:1 non-text threshold and is
used where a boundary carries meaning. `outline-variant` does not, and is restricted to
hairlines between rows, which are a reading aid and not a control boundary.

### Dark theme

Not derivable, and therefore not present. A light screenshot contains no information
about a dark scheme: dark surfaces are not the light ones inverted, the container
ladder runs the other way, and MD3's `surface-dim` / `surface-bright` pair exists to
give a dark scheme its range. Those two tokens are absent here on purpose -- inventing
them from a light capture would produce two plausible hexes that no one measured and
that the linter cannot fault, which is the exact failure mode this file is trying to
avoid. `omitted` cannot express this, since it takes only the five section names.

## Typography

### Sizes

Six rendered sizes were measured: 11, 12, 14, 16, 20 and 28 px. Those are measurements
and are written as literals.

The **ratio behind them is an inference.** A 1.2 ratio anchored at 14px runs 11.67,
14, 16.8, 20.16, 24.19, 29.03. Four of the six measured sizes sit within a pixel of a
step of their own: 12 against 11.67, 14 exact, 16 against 16.8, 20 against 20.16. The
remaining two do not -- 28 is 1.03 off 29.03, the step two above 20.16, and 11 has no
step of its own at all. 11px sits below the scale as a deliberate one-off for uppercase
column labels. So the file records the measured integers and documents 1.2 as the ratio
to extend from, rather than presenting a generated ladder as if it had been observed.
If a future screen shows a 24px or a 34px size, the hypothesis holds; if it shows 22px,
it does not.

### Family

**Not measured. Do not treat `fontFamily: Inter` in the frontmatter as a finding.**

A screenshot does not carry font names. What it carries is character: a geometric
grotesque with open apertures, near-vertical terminals on `a` and `c`, single-storey
`g`, and lining figures of even width. Three candidates match that character and all
three are verified to ship Cyrillic, which is a hard requirement here because the board
renders Kaliningrad and Warszawa lanes in local spelling:

1. **Inter** -- chosen provisionally. Closest match to the rendered `g` and figure width.
2. **IBM Plex Sans** -- slightly narrower, more humanist `a`. Second choice.
3. **Golos Text** -- best Cyrillic proportions of the three; diverges most on Latin.

This is a hypothesis awaiting one line of confirmation from the front-end team. It is
in the file because a design system without typography is not usable, not because it
was established. Families that are not on a verified-coverage list are excluded
outright: several display serifs are served with `latin` and `latin-ext` subsets only
and fall back silently to a system serif the moment a Cyrillic city name renders, which
on this board is every third row.

### Weights

400 / 500 / 600, read from stem width at 14px. This is approximate: at that size the
difference between 500 and 550 is under one pixel of stem. Treat the weights as
three distinguishable steps rather than as exact values.

### Numerals

`numeric-md` and `numeric-lg` carry `fontFeature: '"tnum" 1, "zero" 1'` -- tabular
figures plus slashed zero. This is not a preference. Every numeric column on this board
is read down, not across: ETA deltas, pallet counts, weights, line-haul cost. With
proportional figures the digits do not align in a column and a scanning dispatcher
cannot compare magnitudes without reading each value. The slashed zero separates `0`
from `O` in shipment references, which mix both.

One export caveat: a unitless `lineHeight` is a CSS-correct multiplier and is used here
for that reason, but `export --format css-tailwind` does not emit a `--leading-*`
variable for it. Line heights must be reapplied by hand in a Tailwind v4 theme.

## Layout

### Rhythm

Every gap measured on the board is a multiple of 4px: 4, 8, 12, 16, 20, 24. The base
unit is therefore 4px with a strong 8px preference, and that much is established.

The **ladder is not**, and this is why `spacing` carries an `omitted` entry. One screen
shows the gaps that this screen happens to use. It cannot show which of them are steps
of a scale and which are one-off adjustments, and it says nothing about the steps
between 24 and the next value up, which a drawer or a form would need. Publishing a
seven-step scale from six observed gaps would be five measurements and two inventions,
indistinguishable in the file. Instead each component records its measured padding as a
literal, and the scale is deferred.

### Frame

- 72px fixed navigation rail, full height, never collapses.
- 56px application bar over the board area only.
- 24px canvas padding around the board content.
- The table is fluid to the viewport with a 1120px minimum before horizontal scroll.
- The KPI band is four equal cards, 20px internal padding, 16px between cards.

### Density

Rows are 44px, not the 40px a table this dense would normally take. The reason is the
data: lane strings such as `Rotterdam -> Warszawa Okecie` do not fit a 240px column at
14px, so the origin-destination cell is allowed two lines, and 44px is the height at
which a two-line cell does not push the chip out of vertical centre. Below 44px the
depot terminals also start producing mis-taps on the row action.

The header band is 36px, controls are 36-40px, chips are 22px. Nothing on the board is
smaller than 18px in its long dimension.

### Alignment

Text columns are left-aligned. Every column that is compared down its own length --
ETA delta, weight, pallets, cost -- is right-aligned and set in `numeric-md`. Status is
its own column and never a row-level treatment.

## Elevation & Depth

The format has no component sub-token for elevation. The valid sub-tokens are
`backgroundColor`, `textColor`, `typography`, `rounded`, `padding`, `size`, `height`
and `width`; adding `elevation` or `borderColor` produces a linter warning that echoes
those eight names back. Depth in this file is therefore carried two ways.

**By surface level.** The `surface-container` ladder is the machine-readable part.
Higher container level means nearer the viewer: `background` for the canvas,
`surface` for resting cards and rows, `surface-container` for the rail,
`surface-container-high` for the sticky header band, `surface-container-highest` for
the filter menu that floats over everything.

**By prose.** Shadow values are here and nowhere else, because they cannot be
tokenised in this format:

| Level | Used by | Shadow |
| :--- | :--- | :--- |
| Resting | Cards, rows | None. A 1px `outline-variant` hairline instead |
| Floating | Filter menu, tooltip | `0 4px 12px rgba(20, 24, 28, 0.12)` |
| Sticky | Table header when scrolled | `0 1px 0 rgba(20, 24, 28, 0.10)` |

These three are **approximations**. A screenshot shows a shadow's extent but not the
alpha, blur and spread that produced it; several combinations render the same 8px of
grey. They are recorded as a starting point for implementation, not as measurements.

The board uses two depth levels and no more. A dispatcher scanning 200 rows needs the
table to be flat; a third floating level would compete with the status chips for
attention, and the chips must win.

## Shapes

Four radii, all measured off the screenshot, each with one job:

| Token | Value | Applies to |
| :--- | ---: | :--- |
| `sm` | 4px | Lane tags, tooltip, checkbox |
| `md` | 6px | Buttons, search input, banner |
| `lg` | 10px | KPI cards, filter menu |
| `full` | 999px | Status chips, driver avatars, the on-time meter |

The ladder is deliberately not flat. A single radius applied to everything is the most
common signature of a default-looking interface, and it also destroys the one shape
rule this board depends on: **the pill means state.** A status chip is a pill; nothing
that is not a status is a pill. A dispatcher scanning the table locates state by
silhouette before colour resolves, which matters at two metres and matters more for
operators who cannot separate the amber and green tints.

There is no `xl` radius. No surface in the screenshot was large enough to need one, and
a drawer has not been seen yet.

## Components

Twenty-eight components, all referenced from measured screen elements. Sub-tokens are
limited to the eight the format defines.

| Component | Role |
| :--- | :--- |
| `board-canvas` | The page ground behind the cards and table |
| `app-bar` | Top bar over the board area, holds the view title and primary action |
| `nav-rail` | Fixed 72px rail, icon plus 11px label |
| `card-kpi` | One of four KPI cards; the figure is `numeric-lg` |
| `button-primary` | The single committing action per view |
| `button-outline` | Every other action |
| `button-danger` | Destructive only: cancel shipment, void POD |
| `input-search` | Shipment reference and lane search |
| `menu-filter` | Floating filter panel over the table |
| `table-header` | Sticky column-header band, 11px uppercase labels |
| `table-row` | Default row |
| `table-row-alt` | Alternating row fill for long scrolls |
| `table-cell-numeric` | Any column compared down its length |
| `table-cell-muted` | Timestamps and secondary identifiers |
| `divider` | Hairline between rows |
| `divider-section` | Stronger rule between the KPI band and the table |
| `chip-scheduled` | State: booked, not collected |
| `chip-in-transit` | State: moving, on plan |
| `chip-delayed` | State: behind ETA |
| `chip-hold` | State: held at customs or by consignee |
| `chip-delivered` | State: POD received |
| `chip-exception` | State: damage, refusal, undeliverable |
| `badge-count` | Assignment counts on the rail |
| `avatar-driver` | Driver initials, 28px |
| `meter-on-time` | On-time performance bar in the KPI card |
| `banner-exception` | Board-level alert above the table |
| `tooltip` | Full lane string on truncation |
| `tag-lane` | Lane code, square-ish so it cannot be mistaken for a status |

Three things this section does not contain, and will not until they are supplied:

1. **States.** No hover, focus, active, selected, disabled or loading appearance. A
   screenshot at rest contains none of them and the format has no sub-token for them.
   They belong in the implementation ticket.
2. **Borders.** `input-search`, `button-outline` and `card-kpi` all carry a 1px
   `outline` border on screen. There is no `borderColor` sub-token, so the border is
   documented here and the two rules that exist as their own surfaces -- `divider` and
   `divider-section` -- are modelled as a `backgroundColor` with `height: 1px`.
3. **Composite type.** A component's `typography` records the dominant scale only.
   `card-kpi` shows `numeric-lg` for the figure and `label-sm` for the caption; the
   token names the first.

Padding is written as measured literals rather than as `{spacing.*}` references,
because `spacing` is declared in `omitted`. When the spacing ladder is established,
these literals become the evidence for its steps.

## Do's and Don'ts

These are rules for this board, not general design advice. Each one is checkable
against the file.

### Do

- **Give status exactly one carrier: the chip.** One state, one chip, one hue, in the
  status column. The lane, the row and the reference stay neutral.
- **Say how late in text, not in hue.** `+2h 15m` in `numeric-md` next to the chip.
  Amber means delayed; it does not mean *slightly* delayed, and a darker amber must
  never come to mean *very* delayed.
- **Keep red for exception only.** Damage, refusal, undeliverable -- states that end
  the shipment's normal path and need a human now. Late is amber. A red board that is
  merely late trains dispatchers to ignore red.
- **Right-align and tabularise every compared column.** ETA delta, weight, pallets,
  cost. `table-cell-numeric` exists for this and `"tnum" 1` is what makes it work.
- **Truncate lanes at the end and keep the origin visible.**
  `Rotterdam -> Warszawa Okecie` becomes `Rotterdam -> Warszawa Ok...`, never
  `...Warszawa Okecie`. Dispatchers scan by origin. The full string goes in `tooltip`.
- **Hold the 44px row.** It is the height at which a two-line lane cell keeps its chip
  centred and the depot touch terminals stop mis-firing.
- **Pair every status hue with its label text.** The chip carries a word in every state.
  Colour is the accelerator, not the encoding.

### Don't

- **Don't tint the row by status.** With six states an entire table becomes a heat map,
  the scan line disappears, and the alternating `table-row-alt` fill stops reading as
  rows at all.
- **Don't reuse `primary` for a second job.** It marks the one committing action per
  view. As soon as it is also the link colour and the chart colour, *Assign carrier*
  stops being findable, which is the only thing the colour was for.
- **Don't let `tertiary` mean two things.** `tertiary-container` is the delivered
  state; `tertiary` solid is the on-time meter. A state and a measurement must not
  swap fills, or "green" stops answering which question it is being asked.
- **Don't add a seventh status colour.** A new operational state either maps onto an
  existing chip or replaces one. The palette is a closed vocabulary; a colour with no
  chip behind it is also an orphaned token by the linter's reckoning.
- **Don't set a numeric column in `body-md`.** Proportional figures break column
  comparison, which is the only reason those columns are adjacent.
- **Don't shrink a chip below 22px or a tap target below 36px.** The depot terminals
  are touch, gloved, and mounted at an angle.
- **Don't make anything else a pill.** `tag-lane` is `rounded.sm` precisely so a lane
  code is never mistaken for a state at a glance.
- **Don't compress the row to fit more shipments.** The board's job is the exceptions
  in the first screen, not the count of rows on it. Sorting and filtering add rows to
  the visible set; density does not.

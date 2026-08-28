---
version: alpha
name: Quarto Editorial
description: "Reading system for a long-form editorial site: a one-weight display serif against a humanist text sans, 20px body on a 68-character measure, an 8px spacing base, and separation carried by rules and space instead of shadow."
omitted: []
colors:
  primary: "#8A2B12"
  on-primary: "#FFFFFF"
  primary-container: "#FFDBCF"
  on-primary-container: "#340900"
  primary-fixed: "#FFDBCF"
  on-primary-fixed: "#340900"
  primary-fixed-dim: "#FFB59E"
  on-primary-fixed-variant: "#6C1E08"
  secondary: "#4F4438"
  on-secondary: "#FFFFFF"
  secondary-container: "#EDE0D0"
  on-secondary-container: "#1E170F"
  tertiary: "#1D4E4A"
  on-tertiary: "#FFFFFF"
  tertiary-container: "#C9E6E1"
  on-tertiary-container: "#05201D"
  error: "#9F1D24"
  on-error: "#FFFFFF"
  error-container: "#FFDAD7"
  on-error-container: "#400408"
  background: "#FBF7F0"
  on-background: "#17140F"
  surface: "#FBF7F0"
  surface-dim: "#EDE7DC"
  surface-bright: "#FFFCF6"
  surface-container-lowest: "#FFFFFF"
  surface-container-low: "#F6F1E8"
  surface-container: "#F1EBE0"
  surface-container-high: "#EAE3D6"
  surface-container-highest: "#E3DACB"
  surface-variant: "#E3DACB"
  surface-tint: "{colors.primary}"
  on-surface: "#17140F"
  on-surface-variant: "#554E43"
  outline: "#7C7264"
  outline-variant: "#D3C9B9"
  inverse-surface: "#2B2721"
  inverse-on-surface: "#F4EEE3"
  inverse-primary: "#FFB59E"
typography:
  display-1:
    fontFamily: "Prata"
    fontSize: 84px
    fontWeight: 400
    lineHeight: 0.95
    letterSpacing: "-0.02em"
  display-2:
    fontFamily: "Prata"
    fontSize: 63px
    fontWeight: 400
    lineHeight: 1.0
    letterSpacing: "-0.015em"
  display-3:
    fontFamily: "Prata"
    fontSize: 47px
    fontWeight: 400
    lineHeight: 1.05
    letterSpacing: "-0.01em"
  heading:
    fontFamily: "Prata"
    fontSize: 36px
    fontWeight: 400
    lineHeight: 1.15
    letterSpacing: "-0.005em"
  drop-cap:
    fontFamily: "Prata"
    fontSize: 96px
    fontWeight: 400
    lineHeight: 0.8
    letterSpacing: "-0.02em"
  pull-quote:
    fontFamily: "Prata"
    fontSize: 36px
    fontWeight: 400
    lineHeight: 1.25
    letterSpacing: "-0.005em"
  deck:
    fontFamily: "IBM Plex Sans"
    fontSize: 27px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0em"
  subheading:
    fontFamily: "IBM Plex Sans"
    fontSize: 27px
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.005em"
  body:
    fontFamily: "IBM Plex Sans"
    fontSize: 20px
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "0em"
  label:
    fontFamily: "IBM Plex Sans"
    fontSize: 15px
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "0.08em"
  caption:
    fontFamily: "IBM Plex Sans"
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "0.005em"
rounded:
  none: 0px
  xs: 2px
  sm: 4px
  md: 8px
  lg: 16px
  pill: 999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  2xl: 64px
  3xl: 96px
  4xl: 160px
components:
  article-body:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    width: 680px
  drop-cap-lead:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.drop-cap}"
    padding: "{spacing.xs}"
    width: 96px
  deck-standfirst:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface-variant}"
    typography: "{typography.deck}"
    width: 680px
  pull-quote:
    backgroundColor: "{colors.surface-container-low}"
    textColor: "{colors.primary}"
    typography: "{typography.pull-quote}"
    rounded: "{rounded.none}"
    padding: "{spacing.lg}"
    width: 680px
  byline:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.secondary}"
    typography: "{typography.label}"
    padding: "{spacing.sm}"
  section-rule:
    backgroundColor: "{colors.outline}"
    rounded: "{rounded.none}"
    height: 1px
    width: 160px
  figure-caption:
    backgroundColor: "{colors.surface-container-low}"
    textColor: "{colors.on-surface-variant}"
    typography: "{typography.caption}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  link-inline:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.body}"
  kicker:
    backgroundColor: "{colors.primary-container}"
    textColor: "{colors.on-primary-container}"
    typography: "{typography.label}"
    rounded: "{rounded.xs}"
    padding: "{spacing.sm}"
  nav-link:
    backgroundColor: "{colors.background}"
    textColor: "{colors.on-background}"
    typography: "{typography.label}"
    padding: "{spacing.md}"
    height: 64px
  nav-link-active:
    backgroundColor: "{colors.background}"
    textColor: "{colors.tertiary}"
    typography: "{typography.label}"
    padding: "{spacing.md}"
    height: 64px
  footer-note:
    backgroundColor: "{colors.inverse-surface}"
    textColor: "{colors.inverse-on-surface}"
    typography: "{typography.caption}"
    rounded: "{rounded.none}"
    padding: "{spacing.2xl}"
---

## Overview

Quarto Editorial is a reading system for a long-form editorial site: article
pages, essay indexes, author pages, an archive. It is tuned for one job — a
person reading 2,000 words on a screen without stopping. It is not a product
UI. A dense table, a settings panel, or a dashboard will fight every value in
this file; use a product system for those.

The system has exactly two voices, and the whole design is the boundary
between them:

- **Prata** — a high-contrast display serif with vertical stress, hairline
  thins, one weight (400), and no italic. It speaks at most three times per
  page.
- **IBM Plex Sans** — a humanist grotesque with open apertures, low stroke
  contrast, six weights, and a true italic. It carries everything else,
  including the running text.

That is the contrast the pair is buying: modulated against monoline, historical
against neutral, one weight against many. It is not decoration. A page where
both faces are doing the same job has lost the system.

Neutrals are warm. Every neutral step is biased toward the yellow-red end
(`background` `#FBF7F0` is R251 G247 B240 — an 11-point red-over-blue delta),
so the page reads as uncoated paper rather than as a monitor. That delta is
positive at every neutral step below `surface-container-lowest` `#FFFFFF`, which
is pure white by choice; a cool grey dropped into the ramp is visible
immediately next to the others.

`omitted` is empty because all five schema sections — colors, typography,
spacing, rounded, components — are defined here. Three things this system does
have opinions about cannot be declared in `omitted` at all, because the field
accepts only those five names: **there is no dark theme** (see Colors), **no
motion tokens**, and **no icon sizing**. They are named here so their absence is
a decision on the record rather than an oversight.

## Colors

39 tokens. The names are Material Design 3 family names — `primary`,
`on-primary`, `surface-container-high`, `on-surface-variant`, `outline-variant`
— and that is a constraint of the DESIGN.md format, not a house preference. The
linter's `orphaned-tokens` rule exempts a color only if a component references
it or if its family is one of the MD3 baseline families (`primary`,
`secondary`, `tertiary`, `error`, `surface`, `background`, `outline`). A palette
named `ink` / `paper` / `rule` earns one warning per unreferenced poetic name.
Naming the ramp in the format's vocabulary is what keeps the file at zero
warnings.

**One accent, one role.** `primary` `#8A2B12` is a burnt vermilion, and it is a
*mark* colour, never a field colour: inline links, the drop cap, the pull quote,
and the small chip behind a kicker. There are no buttons on an article page, so
`primary` never fills a large area. `on-primary` exists for the one control the
site owns (a subscribe field) and for nothing else.

The other three roles are each single-purpose:

| Role | Token | Used for | Never used for |
| :--- | :--- | :--- | :--- |
| Meta | `secondary` `#4F4438` | byline, dateline, read time | links, headings |
| Wayfinding | `tertiary` `#1D4E4A` | current section in nav, footnote markers | links, emphasis |
| Correction | `error` `#9F1D24` | retraction and correction notices | validation states (there are no forms in the article) |

**The neutral ramp.** Ten steps on one warm hue. In measured L* order, lightest
first: `surface-container-lowest` `#FFFFFF` (100.00) → `surface-bright`
`#FFFCF6` (99.04) → `surface` / `background` `#FBF7F0` (97.36) →
`surface-container-low` `#F6F1E8` (95.30) → `surface-container` `#F1EBE0`
(93.23) → `surface-dim` `#EDE7DC` (91.83) → `surface-container-high` `#EAE3D6`
(90.45) → `surface-container-highest` / `surface-variant` `#E3DACB` (87.38) →
`outline-variant` `#D3C9B9` (81.36) → `outline` `#7C7264` (48.56).
Chroma falls toward zero at the dark end (`on-surface` `#17140F`) so text stays
neutral while paper stays warm. Adjacent container steps are deliberately close:
they separate a figure or an aside from the column, and they are not supposed to
announce themselves.

`inverse-surface` `#2B2721` / `inverse-on-surface` `#F4EEE3` exist for exactly
one element — the footer. They are not a dark theme. This file defines no dark
theme; a real one needs a second ramp with its own contrast measurements, and
inventing it here would be a claim this system has not tested.

**Contrast, measured, not assumed.** Every component pair in this file was
computed before it was written. The lowest is `figure-caption` at 7.30:1. The
full set: `article-body` and `nav-link` 17.20:1, `footer-note` 12.85:1, `kicker`
13.74:1, `byline` 8.87:1, `nav-link-active` 8.78:1, `drop-cap-lead` and
`link-inline` 8.08:1, `deck-standfirst` 7.69:1, `pull-quote` 7.67:1,
`figure-caption` 7.30:1. Every pair clears WCAG **AAA 7:1**, not merely the
AA 4.5:1 the linter checks. A reading system that only clears AA has set its bar
at the wrong place: AA is a floor for interface chrome, and this is body copy.

## Typography

**The pair, and what it is doing.** The contrast is enforced by the families
themselves, which is why this pair was chosen over a serif/serif or a
sans/sans pairing:

| | Prata (display) | IBM Plex Sans (text) |
| :--- | :--- | :--- |
| Weights available | 400 only | 400, 500, 600, 700 (+ more) |
| Italic | none | true italic |
| Stroke contrast | high, vertical stress | low, monoline |
| Google Fonts subsets | `latin`, `vietnamese`, `cyrillic`, `cyrillic-ext` | `latin`, `latin-ext`, `cyrillic`, `cyrillic-ext`, `greek`, `vietnamese` |

Prata is *physically incapable* of doing text work, and that is the point of
picking it. Requesting a bold returns HTTP 400 from the Google Fonts CSS API —
there is no 700 to fall back to, so a `<strong>` inside a Prata headline gets a
synthesised fake bold from the browser. The family cannot quietly creep into the
body copy the way a full-featured serif can.

**Where each face is allowed, and where it is banned.**

| Face | Allowed | Banned |
| :--- | :--- | :--- |
| Prata | `display-1`, `display-2`, `display-3`, `heading`, `pull-quote`, `drop-cap` | anything below 36px; anything longer than two lines; nav, byline, caption, labels, buttons, tables, any running text |
| IBM Plex Sans | `deck`, `subheading`, `body`, `label`, `caption`, and every UI surface | the article title and the section-cover title — those are Prata or they are nothing |

Note that in-article subheads are set in `subheading` (IBM Plex Sans 27px/600),
not in Prata. Below 36px Prata's hairlines thin out on a non-retina screen, and
a subhead a reader scans twenty times in an article belongs to the text voice.

**Coverage limitation, stated rather than hidden.** Prata's subset list has no
`latin-ext`. A headline containing Polish, Czech, Turkish, Hungarian, or
Romanian diacritics falls back, glyph by glyph, to a system serif; the result is
a mixed headline. The reading column is unaffected — IBM Plex Sans carries
`latin-ext`, `cyrillic`, `cyrillic-ext`, and `greek` — so the blast radius is
the six Prata tokens only. Two faces commonly reached for in editorial work,
**Instrument Serif** and **Bodoni Moda**, were rejected outright: both ship
`latin` and `latin-ext` only, and both fail silently on Cyrillic. If this system
is deployed for a language outside Prata's four subsets, replace the display
face and re-check the subset list before writing a line of CSS — do not assume
coverage from a family's reputation.

**The scale.** Ratio **1.333**, the perfect fourth, generated from the whole
number 4:3. Base **20px**. Steps are `20 × 1.333ⁿ`, rounded to whole pixels:
15, 20, 27, 36, 47, 63, 84.

A dense product interface works in the 1.125–1.2 range because it needs many
closely spaced steps inside a small vertical budget, and a jump that large would
blow a table row apart. An article page shows three or four sizes at once and
nothing is competing for vertical space, so each jump has to be legible from
across the room. 1.333 is that jump: 27 next to 36 next to 47 reads as three
different ranks with no weight change required.

Two values are deliberately off the ratio:

- **`drop-cap` 96px** is a *baseline-grid* value, not a scale value. Body is
  20px at `lineHeight` 1.6, so the body line box is 32px, and the drop cap
  spans three of them: 3 × 32 = 96. It changes only if the body line box
  changes. Optical fit — how far the cap has to be pulled up so its baseline
  lands on the third body baseline — depends on Prata's cap-height ratio and is
  a rendering detail this file does not encode.
- **`label` and `caption` share 15px** (the `n = −1` step). They differ in
  weight and tracking, not size, because a caption sitting next to a byline at
  two different sizes reads as an error.

**Tracking.** Negative only above 36px, where Prata's default fit is too loose
at display sizes: `-0.005em` at 36px scaling to `-0.02em` at 84px. Body tracking
is `0em`. `label` is the exception at `+0.08em` — it is tracking for uppercase
setting, which is why lowercase `label` looks over-spaced.

**Two format limits worth knowing before you export.** Both were verified
against `@google/design.md@0.4.0`:

1. `fontFamily` values are emitted as a *single quoted string*. A stack written
   as `fontFamily: "IBM Plex Sans, Arial, sans-serif"` exports to
   `--font-body: "IBM Plex Sans, Arial, sans-serif";` — one invalid family name.
   So each token names one family, and the fallback stack lives in the CSS that
   consumes these tokens.
2. A unitless `lineHeight` (used throughout here, because it is the correct CSS
   practice) is dropped by `export --format css-tailwind`. The leading has to be
   restated by hand in Tailwind v4 output. It is preserved in this file, which
   is the source of truth.

`fontFeature` and `fontVariation` are available in the schema and are left unset
here: this system has not verified which OpenType features these two families
actually ship, and asserting `onum` on a face that lacks it produces nothing.

## Layout

**Measure is the primary constraint; column width is derived from it.** The
target is **68 characters per line**, with 66–72 acceptable. At `body` (20px
IBM Plex Sans) that lands the content column at **680px**, which is what
`article-body` declares. The character count is the rule and the pixel value is
the consequence — if the text face, the size, or the language changes, re-measure
the count and move the width. Cyrillic and Greek run slightly wider per
character than Latin at the same size.

**Three widths, and no others.**

| Width | Value | Contents |
| :--- | :--- | :--- |
| Column | 680px | all running text, pull quotes, bylines, captions |
| Break-out | 1000px | figures and tables that need the room |
| Full bleed | 100vw | one lead image per article, at most |

**Spacing: base unit 8px, eight tokens.** `4, 8, 16, 24, 40, 64, 96, 160` —
that is `0.5, 1, 2, 3, 5, 8, 12, 20 × 8`. The multipliers climb on a roughly
Fibonacci curve, so the large breaks are unmistakably larger rather than
incrementally larger. `xs` (4px) is the only sub-base value in the system and
exists for optical nudges — a rule offset, a cap-alignment fix — not for layout.

**Vertical rhythm is bound to the 32px body line box.** The four vertical
values are multiples of it or of half of it: paragraph gap `md` 16px (half a
line box), sub-section gap `2xl` 64px (two), major section gap `3xl` 96px
(three), article-to-footer `4xl` 160px (five). `lg` 24px and `xl` 40px are
*inline* values — gutters, figure padding, rule offsets — and are deliberately
not baseline-bound; forcing horizontal insets onto a vertical grid produces
gutters nobody asked for.

Masthead height is 64px (`nav-link` height, matching `2xl`). Footer padding is
`2xl` 64px on all sides.

## Elevation & Depth

**This system defines no shadow at all, and that is the design.** There are no
elevation tokens here, and the format could not express them if there were: the
component sub-token set is closed — `backgroundColor`, `textColor`,
`typography`, `rounded`, `padding`, `size`, `height`, `width` — with no
elevation or shadow member. Elevation in DESIGN.md is a prose section by
construction, so this section is the whole specification.

A drop shadow asserts that an element is a movable object floating above
another. An article is one sheet of paper. The assertion is false, and it costs
something real: a soft shadow around a text block puts a grey halo behind the
first and last lines and lowers their effective contrast against the very
surface the rest of the page measured at 17:1.

**Four devices carry separation instead, in the order to reach for them:**

1. **Rules.** A 1px hairline in `outline-variant` `#D3C9B9` between list items
   and around break-out figures. The `section-rule` component — 1px tall, 160px
   wide, in `outline` — marks a section break inside an article. It is short on
   purpose: a full-width rule cuts the page in half, and a section break is a
   pause, not a cut.
2. **Space.** `2xl` (64px) and `3xl` (96px) separate more convincingly than any
   shadow, and they cost no contrast.
3. **Weight and size.** With a 1.333 ratio, rank is visible without any
   container at all. Most "cards" in editorial layouts are a heading that was
   not allowed to be big enough.
4. **The surface-container ladder.** For the two or three places where a panel
   genuinely is a different plane — an aside, a figure caption, the footer — one
   step on the ladder plus `rounded.md`. One step, never two.

**Two permitted exceptions, both of which are state, not depth:**

- **Focus ring**: 2px `outline` `#7C7264`, offset 2px. A keyboard user has to
  see where they are; that is an accessibility requirement and outranks the
  no-shadow rule.
- **Detached masthead**: when the masthead sticks and content scrolls beneath
  it, it takes a 1px `outline-variant` bottom rule. Not a shadow, and not a
  blur.

## Shapes

Six radii, and the honest summary is that roughly nine tenths of this system is
square. `none` (0px) is the default and the correct answer for the article
column, the pull quote, the section rule, and the footer.

| Token | Value | Applies to | Rationale |
| :--- | :--- | :--- | :--- |
| `none` | 0px | article column, pull quote, section rule, footer | paper has corners |
| `xs` | 2px | inline code, kicker chip | enough to read as a chip, not enough to read as a button |
| `sm` | 4px | the subscribe input | the only form field on the site |
| `md` | 8px | figures, asides, figure captions | softens an image edge against warm paper |
| `lg` | 16px | the lead image on a section cover | one element per page, at most |
| `pill` | 999px | the subscribe button, section chips | at most twice per page |

The ladder exists precisely *because* radii are rare here. Rare values drift:
without named steps, the three rounded things on the site end up at 6px, 8px,
and 10px, chosen months apart. Six names mean the few rounded elements agree.

The failure mode to avoid is the opposite one — a single radius applied to every
element, which flattens the distinction between a figure (`md`), a chip (`xs`),
and a control (`pill`) and is the clearest signature of an unconsidered system.

## Components

Twelve components. Every pair below was measured before it was written; the
ratio column is computed, not estimated.

| Component | Background | Text | Typography | Ratio |
| :--- | :--- | :--- | :--- | :--- |
| `article-body` | `surface` | `on-surface` | `body` | 17.20:1 |
| `drop-cap-lead` | `surface` | `primary` | `drop-cap` | 8.08:1 |
| `deck-standfirst` | `surface` | `on-surface-variant` | `deck` | 7.69:1 |
| `pull-quote` | `surface-container-low` | `primary` | `pull-quote` | 7.67:1 |
| `byline` | `surface` | `secondary` | `label` | 8.87:1 |
| `section-rule` | `outline` | — | — | n/a |
| `figure-caption` | `surface-container-low` | `on-surface-variant` | `caption` | 7.30:1 |
| `link-inline` | `surface` | `primary` | `body` | 8.08:1 |
| `kicker` | `primary-container` | `on-primary-container` | `label` | 13.74:1 |
| `nav-link` | `background` | `on-background` | `label` | 17.20:1 |
| `nav-link-active` | `background` | `tertiary` | `label` | 8.78:1 |
| `footer-note` | `inverse-surface` | `inverse-on-surface` | `caption` | 12.85:1 |

Notes on specific entries:

- **`section-rule` declares no `textColor` on purpose.** A rule has no text.
  Declaring a colour there would hand the `contrast-ratio` rule a pair that
  never renders, and the check only runs when both members are present.
- **`drop-cap-lead` is a 96px-wide float**, matching its 96px type size, so the
  three body lines wrapping it start at a predictable inset.
- **`nav-link` and `nav-link-active` share a background and a type token** and
  differ only in colour. The active state is `tertiary`, the wayfinding role —
  an active nav item is not a link being emphasised, it is a location being
  reported.
- **`pull-quote` keeps the 680px column width.** It is an indent, not a
  break-out. See Do's and Don'ts.
- **Border colours are absent from every component** because the sub-token set
  has no `borderColor` member. Adding one produces a warning under the
  `broken-ref` rule with the valid list echoed back. Border colours for this
  system are `outline-variant` for hairlines and `outline` for the focus ring,
  and they are specified here, in prose, because that is the only place the
  format allows them to live.

## Do's and Don'ts

**Do**

- Set the article title in `display-2` (63px). Reserve `display-1` (84px) for
  section covers; an article page that opens at 84px has nowhere left to go.
- Allow Prata at most three appearances per page: the title, one `heading` or
  `pull-quote`, and the drop cap. Count them before shipping.
- Keep the measure at 66–72 characters. If a translation pushes the count past
  72, reduce `article-body`'s 680px width — never reduce `body` below 20px.
- Set `label` uppercase in CSS. Its `+0.08em` tracking is sized for capitals;
  the format has no `text-transform` property, so this rule cannot be enforced
  by the file and has to be enforced by review.
- Set a headline containing Polish, Czech, Turkish, Hungarian, or Romanian
  diacritics in `subheading` (IBM Plex Sans) rather than Prata — Prata has no
  `latin-ext` subset and will mix a fallback serif into the line.
- Separate an aside from the column with one step on the surface-container
  ladder plus `rounded.md`. One step.
- Use `error` `#9F1D24` only for a published correction or retraction notice.

**Don't**

- **Don't set Prata below 36px.** It has one weight and no italic; a `<strong>`
  or an `<em>` inside it produces a browser-synthesised fake, and its hairlines
  drop out on a non-retina screen.
- **Don't add a shadow token.** If two things need separating, the answer is
  `section-rule`, `spacing.2xl`, or one surface-container step — in that order.
  The only permitted non-flat effect is the 2px `outline` focus ring.
- **Don't use `tertiary` `#1D4E4A` for links.** It is the wayfinding colour —
  active nav, footnote markers. Links are `primary`. One colour, one role is the
  rule this palette is arranged around.
- **Don't set `on-surface-variant` below `surface-container-low`.** The secondary
  text colour holds AAA only on `surface-bright` (8.02:1), `surface` (7.69:1) and
  `surface-container-low` (7.30:1). On `surface-container` it measures 6.92:1 and
  on `surface-container-high` 6.44:1 — still AA, but under the 7:1 floor every
  declared pair in this file holds. `deck-standfirst` and `figure-caption` are the
  only two components that use it, and both sit on permitted planes.
- **Don't full-bleed the pull quote.** It stays at 680px with `spacing.lg`
  padding and a `primary` rule on its leading edge. A pull quote that escapes
  the column stops being a voice inside the article and becomes a banner.
- **Don't set the byline in `body`.** The meta voice is `label` in `secondary`:
  15px, weight 600, tracked, uppercase. A byline in running-text style reads as
  the first sentence of the article.
- **Don't derive the 96px drop cap from the 1.333 scale.** It is 3 × the 32px
  body line box. It moves when `body`'s `lineHeight` moves, and at no other
  time.
- **Don't reach for `rounded.pill` more than twice on a page**, and never on
  anything containing more than three words.
- **Don't add `borderColor`, `gap`, or `elevation` to a component.** The
  sub-token set is closed at `backgroundColor`, `textColor`, `typography`,
  `rounded`, `padding`, `size`, `height`, `width`; anything else is a linter
  warning and is silently dropped by every exporter.
- **Don't rename the colour tokens to editorial-sounding names** — `ink`,
  `paper`, `rule`, `wash`. The `orphaned-tokens` rule exempts only MD3 family
  names and colours a component actually references; a poetic ramp costs one
  warning per unreferenced step.
- **Don't treat `inverse-surface` as a dark theme.** It dresses the footer.
  A real dark theme needs its own ramp and its own contrast measurements, and
  this file does not contain them.

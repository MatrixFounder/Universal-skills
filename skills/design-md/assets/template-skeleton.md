---
version: alpha
name: Skeleton
description: "Placeholder identity for a new DESIGN.md. The structure is real and lints clean; the values are provisional and must be replaced."
omitted: []
colors:
  # --- Provisional accent -------------------------------------------------
  # This magenta is not a brand color. It was chosen to be conspicuous so that
  # an unfinished file is obvious on sight. Replace all four before shipping.
  primary: "#9B0876"                     # PROVISIONAL
  on-primary: "#FFFFFF"                  # PROVISIONAL
  primary-container: "#F9DCF2"           # PROVISIONAL
  on-primary-container: "#550741"        # PROVISIONAL
  # --- Status -------------------------------------------------------------
  error: "#A7291B"
  on-error: "#FFFFFF"
  # --- Neutral ramp, hue 222 deg ------------------------------------------
  background: "#FCFCFD"
  on-background: "#171A21"
  surface: "#FCFCFD"
  surface-container-low: "#F6F7F9"
  surface-container: "#F0F1F5"
  surface-container-high: "#E7E9EE"
  surface-container-highest: "#DEE1E7"
  on-surface: "#171A21"
  on-surface-variant: "#4C515D"
  outline: "#6A7181"
  outline-variant: "#CBCFD8"
typography:
  # Modular scale: 16 px base, ratio 1.25, rounded to whole pixels.
  # fontFamily is PROVISIONAL in every scale below — it is the first thing to replace.
  label-sm:
    fontFamily: "Inter, 'Helvetica Neue', Arial, sans-serif"   # PROVISIONAL
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0.01em
  body-md:
    fontFamily: "Inter, 'Helvetica Neue', Arial, sans-serif"   # PROVISIONAL
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.55
  title-sm:
    fontFamily: "Inter, 'Helvetica Neue', Arial, sans-serif"   # PROVISIONAL
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.35
  title-lg:
    fontFamily: "Inter, 'Helvetica Neue', Arial, sans-serif"   # PROVISIONAL
    fontSize: 25px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: -0.01em
  headline:
    fontFamily: "Inter, 'Helvetica Neue', Arial, sans-serif"   # PROVISIONAL
    fontSize: 31px
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: -0.015em
  display:
    fontFamily: "Inter, 'Helvetica Neue', Arial, sans-serif"   # PROVISIONAL
    fontSize: 39px
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: -0.02em
rounded:
  none: 0px
  xs: 2px
  sm: 4px
  md: 8px
  lg: 16px
  full: 999px
spacing:
  # Base unit 4 px. Every step is an integer multiple of it.
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  "2xl": 32px
  "3xl": 48px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md}"
    height: 40px
  button-quiet:
    backgroundColor: "{colors.surface-container-high}"
    textColor: "{colors.on-surface}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md}"
    height: 40px
  input-field:
    backgroundColor: "{colors.background}"
    textColor: "{colors.on-background}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md}"
    height: 40px
  card:
    backgroundColor: "{colors.surface-container-low}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xl}"
  chip-selected:
    backgroundColor: "{colors.primary-container}"
    textColor: "{colors.on-primary-container}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
    height: 28px
  badge-error:
    backgroundColor: "{colors.error}"
    textColor: "{colors.on-error}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
    padding: "{spacing.xs}"
    height: 20px
---

# Skeleton

Skeleton is a scaffold, not a design system. Copy this file, rename it, and
replace the values. It lints with zero errors and zero warnings as it stands,
so a clean lint run on an unedited copy proves nothing about the design — only
that the structure survived editing.

Provisional values carry a `# PROVISIONAL` comment in the frontmatter. Delete
each comment as you replace the value it marks. A file that still contains the
string `PROVISIONAL` is not finished.

## Overview

> Replace this section with what the system is for: the product, the audience,
> and the one adjective the interface has to earn. Name the constraint that
> drove the palette and the scale — a dense operator console and a marketing
> page do not get the same answer. Disqualified: any sentence that would be
> equally true of a different product, and any claim about the brand that no
> token in this file expresses.

Skeleton's identity is deliberately incomplete in one axis and deliberately
finished in the other. The neutral ramp, the type ladder, the spacing grid and
the radius set are real, internally consistent, and safe to build on. The
chromatic accent is not: `primary` is a magenta placeholder chosen for maximum
visual distance from the neutrals so that an unfinished file announces itself.

The five token sections — `colors`, `typography`, `rounded`, `spacing`,
`components` — are all populated, so `omitted` is an empty list. The moment you
delete a section instead of filling it, declare it here rather than leaving the
placeholder values in place:

```text
omitted:
  - section: components
    reason: "No component inventory exists yet; tokens only."
```

Note the fence language above is `text`, not `yaml`, on purpose. The linter
parses fenced `yaml` blocks in the body as a second token source; a `yaml`
example that names a section already present in the frontmatter is reported as
`Section '<name>' is defined in both frontmatter and code block 1.` Keep
illustrative YAML out of `yaml` fences.

Valid names for `omitted` are exactly `colors`, `typography`, `spacing`,
`rounded`, `components`. Any other name is reported as `unknown-omission`.

## Colors

> Replace this section with the reasoning behind the palette: where the neutral
> ramp's hue bias comes from, which token carries the brand, and which pairs are
> guaranteed for text. State measured contrast ratios, not intentions.
> Disqualified: a list that restates the hex values already in the frontmatter,
> and any neutral ramp whose steps do not share one hue.

Seventeen tokens. Eleven of them are one neutral ramp; four are the provisional
accent; two are the error pair.

**Neutral ramp.** Every neutral is generated at hue **222°** — a cool blue-grey.
The bias exists so the greys read as intentional next to a cool accent and never
as camera-noise grey. Saturation is highest at the light end and falls down the
ladder (20% at `surface`, 15.8% at `surface-container-highest`, 9.8% at
`outline`), which keeps the tint perceptible in large light fills without
staining them. The ladder is five steps deep:

| Token | Value | Role |
| :--- | :--- | :--- |
| `surface` / `background` | `#FCFCFD` | page ground |
| `surface-container-low` | `#F6F7F9` | resting card |
| `surface-container` | `#F0F1F5` | grouped region |
| `surface-container-high` | `#E7E9EE` | quiet control |
| `surface-container-highest` | `#DEE1E7` | pressed or nested control |

**Guaranteed text pairs** (measured, sRGB, WCAG 2.1 formula):

- `on-surface` `#171A21` on every ladder step: 16.98:1 down to 13.29:1.
- `on-surface-variant` `#4C515D` on every ladder step: 7.75:1 down to 6.07:1.
  This is the secondary-text token; it clears AA on all five.
- `outline` `#6A7181` is a **non-text** token. It clears 3:1 against every
  ladder step (4.77:1 on `surface`, 3.73:1 at worst on
  `surface-container-highest`) and is intended for control borders.
- `outline-variant` `#CBCFD8` is a hairline divider at 1.52:1 on `surface`. It
  meets no contrast threshold and must never carry meaning on its own.

**Accent.** `primary` `#9B0876` is the placeholder. It pairs with white at
7.81:1 and sits at 7.61:1 on `surface`. When you replace it, keep the four-token
shape — `primary`, `on-primary`, `primary-container`, `on-primary-container` —
and re-measure both pairs; a hue change moves the ratios.

Token names follow the Material Design 3 family vocabulary on purpose. The
linter's `orphaned-tokens` rule only exempts the families `primary`,
`secondary`, `tertiary`, `error`, `surface`, `background`, `outline`; a
custom name such as `slate-300` warns unless a component references it.

## Typography

> Replace this section with the families you picked, why that pairing, and the
> number that generated the size ladder. If the type is set in a language with
> non-Latin script, state which subsets each family actually ships.
> Disqualified: `system-ui` as the chosen family, and a size list that is not
> the output of a stated rule.

Six scales, one family. The family is provisional: Inter is here because it is
a defensible neutral grotesque, not because it is right for your product.
Replacing it is the first edit to make.

The sizes are a **modular scale**: base **16px**, ratio **1.25** (a major
third). Successive multiplication gives 16 → 20 → 25 → 31.25 → 39.06, and one
division gives 12.8. Rounded to whole pixels the ladder is:

| Scale | Size | Weight | Line height |
| :--- | :--- | :--- | :--- |
| `label-sm` | 13px | 500 | 1.4 |
| `body-md` | 16px | 400 | 1.55 |
| `title-sm` | 20px | 600 | 1.35 |
| `title-lg` | 25px | 600 | 1.25 |
| `headline` | 31px | 650 | 1.2 |
| `display` | 39px | 700 | 1.1 |

Line height peaks at `body-md` (1.55) and falls as size rises from there, because
long measure needs air and headlines do not. `label-sm` sits below that peak at
1.4: a 13px label is one line, not a paragraph. Letter-spacing is negative above
20px and slightly positive at 13px, for the same optical reason.

`lineHeight` is unitless throughout: it is a multiplier of the element's own
font size, which is the behaviour you want when a scale is nested. Note the
export consequence — `export --format css-tailwind` drops unitless line heights
and emits no `--leading-*` variable for them.

## Layout

> Replace this section with the grid the product actually uses: base unit,
> container widths, column count, and where the rhythm is allowed to break.
> Disqualified: "use consistent spacing", and a spacing ramp with no stated
> base unit.

The base unit is **4px**. Every spacing token is an integer multiple of it, so
any value in a layout can be checked by division:

`xs` 4 · `sm` 8 · `md` 12 · `lg` 16 · `xl` 24 · `2xl` 32 · `3xl` 48
(1× · 2× · 3× · 4× · 6× · 8× · 12×)

The ramp is not geometric. It is dense at the bottom — 4, 8, 12, 16 — because
control padding needs fine steps, and sparse at the top — 24, 32, 48 — because
section rhythm does not. There is deliberately no 20px and no 40px step: those
gaps force a decision between "inside a control" and "between regions" instead
of letting every value be slightly different.

Skeleton defines no container widths and no column count. Add them here when the
product has a real page; do not invent them from the token file.

## Elevation & Depth

> Replace this section with the depth model: how many levels exist, what
> distinguishes them, and what each level means. Depth has no frontmatter token
> in DESIGN.md, so this prose is the only specification of it. Disqualified: a
> shadow list with no rule for when each shadow applies.

DESIGN.md has no `elevation` sub-token. `components` accepts exactly
`backgroundColor`, `textColor`, `typography`, `rounded`, `padding`, `size`,
`height`, `width` — anything else is reported by the `broken-ref` rule. Depth
therefore lives here, in prose, and in the choice of surface token.

Skeleton's model is **depth by surface, not by shadow**. Three levels:

1. **Ground** — `surface`. The page.
2. **Raised** — `surface-container-low`, used by `card`. Distinguished from the
   ground by a contrast ratio of 1.045:1, a hairline of separation, plus a
   `rounded.lg` corner.
3. **Interactive** — `surface-container-high` and `surface-container-highest`,
   used by `button-quiet` at rest and pressed. The pressed step is darker, so
   the affordance reads without motion.

No shadows are specified. A cool neutral ramp with 222° bias renders a grey
drop-shadow as a muddy stain; if the product needs shadows, tint them toward the
ramp's hue rather than using neutral black at low alpha.

## Shapes

> Replace this section with the radius vocabulary and the rule that assigns a
> radius to an element. State what "full" is reserved for. Disqualified: one
> radius applied to every element, and a set whose values do not relate.

Six levels: `none` 0px, `xs` 2px, `sm` 4px, `md` 8px, `lg` 16px, `full` 999px.
The measured steps double: 2 → 4 → 8 → 16. `none` is the absence of a corner
and `full` is a pill; neither is a point on that ladder.

The assignment rule is **radius scales with the element, not with the brand**:

- Controls a user types into or clicks — `button-primary`, `button-quiet`,
  `input-field` — take `rounded.sm` (4px). At 40px tall, 4px is a softened
  corner, not a shape.
- Containers take `rounded.lg` (16px). `card` is the only one here.
- `rounded.full` (999px) is reserved for elements whose shape carries meaning:
  `chip-selected` and `badge-error`. A pill says "this is a token of state", and
  it stops saying it when everything is a pill.
- `rounded.none` and `rounded.xs` are defined for table cells and dividers,
  which Skeleton does not specify as components.

## Components

> Replace this section with the real inventory and each component's states.
> Every component with both `backgroundColor` and `textColor` must clear WCAG AA
> 4.5:1 — compute it before writing it. Disqualified: a component that
> hard-codes a hex instead of referencing a token, and a state (hover, focus,
> disabled) named in prose but backed by no token.

Six components, all referencing tokens rather than literals. Measured contrast
of every `backgroundColor` / `textColor` pair:

| Component | Background | Text | Ratio |
| :--- | :--- | :--- | ---: |
| `button-primary` | `#9B0876` | `#FFFFFF` | 7.81:1 |
| `button-quiet` | `#E7E9EE` | `#171A21` | 14.33:1 |
| `input-field` | `#FCFCFD` | `#171A21` | 16.98:1 |
| `card` | `#F6F7F9` | `#171A21` | 16.24:1 |
| `chip-selected` | `#F9DCF2` | `#550741` | 11.08:1 |
| `badge-error` | `#A7291B` | `#FFFFFF` | 7.06:1 |

The lowest is 7.06:1, which clears AAA for body text (7:1) with almost nothing
to spare. That headroom is intentional: when you replace the provisional accent,
you have room to lose contrast without falling under AA.

The three 40px-tall controls share a height so they align on one row. `padding`
is `spacing.md` (12px) on all three, which leaves 16px of type in a 40px box.

States are **not** specified. Hover, focus, active and disabled have no tokens
here, and the `components` sub-token set has no slot for them. Specify states in
this prose for the real system, backed by additional color tokens if the states
need their own values.

## Do's and Don'ts

> Replace every rule below with rules only this system's owner would write. Each
> one must name its own tokens and be checkable against a finished file by
> reading it. Disqualified: any rule that would apply unchanged to a different
> design system — "use consistent spacing", "keep contrast accessible",
> "don't use too many fonts". Those are truisms, not a specification.

**Do** delete every `# PROVISIONAL` comment as you replace the value it marks.
Grep the finished file for `PROVISIONAL`; a hit means the file is not done.

**Don't** ship `#9B0876` as `colors.primary`. That magenta exists to be caught,
not to be used. It is also the reason this file has exactly one chromatic
family: there is nothing to balance it against yet.

**Do** keep every neutral on hue 222°. If you re-derive the ramp, re-derive all
eleven neutrals from one hue. A ramp where `surface-container` is 222° and
`outline` is 210° is the defect the bias was introduced to prevent.

**Don't** add a sixth step to the surface ladder. `surface`,
`surface-container-low`, `surface-container`, `surface-container-high`,
`surface-container-highest` cover ground, raised, grouped, resting control and
pressed control. A sixth step means two of those five have collapsed into one
role and the fix is upstream, in the depth model.

**Do** use `on-surface-variant` for secondary text and `outline` for borders.
`outline` `#6A7181` is 3.73:1 on `surface-container-highest`, which fails AA for
text; `on-surface-variant` `#4C515D` is 6.07:1 on the same ground and passes.
Swapping them is the single most likely accessibility regression in this system.

**Don't** set a font size that is not 13, 16, 20, 25, 31 or 39. A 14px or 18px
value is not a smaller variant — it is proof the 1.25 ladder was abandoned, and
once abandoned it never comes back.

**Do** keep every spacing value divisible by 4. If a layout needs 10px, the
component's `padding` or `height` is wrong, not the grid.

**Don't** spend `rounded.full` on anything but `chip-selected` and
`badge-error`. Pill shape is this system's only signal for "state token"; a
pill-shaped card deletes the signal for both.

**Do** declare an omission instead of guessing. If the source material — a
brief, a screenshot, a stylesheet — does not establish typography, put
`typography` in `omitted` with a `reason:`. A plausible invented ladder is worse
than an admitted gap, because nothing downstream can tell it was invented.

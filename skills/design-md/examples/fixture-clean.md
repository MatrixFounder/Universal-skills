---
version: alpha
name: Fixture Clean
description: "Known-good control file for the design-md skill's lint wrapper."
colors:
  primary: "#1B4D3E"
  on-primary: "#FFFFFF"
  surface: "#FCFBF7"
  on-surface: "#14181C"
  outline: "#C6C2B6"
typography:
  body-md:
    fontFamily: "Inter"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
  label-lg:
    fontFamily: "Inter"
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: 0.01em
rounded:
  sm: 4px
  md: 8px
spacing:
  sm: 8px
  md: 16px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md}"
---

## Overview

Test fixture, not a design proposal. This file is the known-good control for the
`design-md` skill: the smallest DESIGN.md that still exercises every token
category and every one of the eight canonical body sections.

Expected linter result, measured with `@google/design.md@0.4.0`:

- exit code `0`
- `summary` is exactly `{"errors": 0, "warnings": 0, "infos": 1}`
- the single finding is rule `token-summary`, message
  `Design system defines 5 colors, 2 typography scales, 2 rounding levels, 2 spacing tokens, 2 components.`

Any other finding means the fixture drifted or the toolchain changed. Do not
"fix" the reported summary above without re-running the linter.

Deliberate design decisions that keep the count at 1 info:

- Colors use MD3 family names (`primary`, `surface`, `outline`), so
  `orphaned-tokens` never fires on the unreferenced `outline` token.
- `spacing` and `rounded` are both non-empty, so `missing-sections` stays quiet.
- There is no `omitted` key, so `omitted-rules` emits no `declared-omission` info.

## Colors

Five tokens: one accent pair and one surface pair, plus a hairline. `primary`
`#1B4D3E` against `on-primary` `#FFFFFF` clears WCAG AA. `surface` `#FCFBF7`
against `on-surface` `#14181C` clears WCAG AAA. `outline` `#C6C2B6` is a
non-text token and is not contrast-checked by the linter.

## Typography

One family, two roles. `body-md` is running text; `label-lg` is the control
label, distinguished by weight and tracking rather than by a second family.
`lineHeight` is unitless on purpose — it is a multiplier, and the linter accepts
it. Note that `export --format css-tailwind` drops unitless `lineHeight`.

## Layout

Two spacing steps on a 8 px grid: `sm` 8 px, `md` 16 px. A real system needs
more steps; two are enough to make `spacing` non-empty and to prove references
resolve.

## Elevation & Depth

Flat. The DESIGN.md component schema has no elevation sub-token, so elevation
can only ever be prose. This fixture asserts no shadows.

## Shapes

Two radii: `sm` 4 px for inline surfaces, `md` 8 px for controls. Two values are
the minimum that shows a radius is a scale and not a constant.

## Components

`button-primary` and `card`. Between them they reference all five token
categories, which is what makes `token-summary` report a non-zero count for each
category.

## Do's and Don'ts

- Do keep this file at exactly one info finding. It is the control the skill's
  `lint` wrapper is regression-tested against.
- Do re-run the linter and update the Overview block if a token is added.
- Don't add an `omitted` key here — that adds a `declared-omission` info and
  breaks the expected summary. The broken-path fixture covers `omitted`.
- Don't rename colors to non-MD3 words such as `ink` or `paper`; with components
  defined, that produces one `orphaned-tokens` warning per name.

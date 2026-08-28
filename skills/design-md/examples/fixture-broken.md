---
version: alpha
name: Fixture Broken
description: "Known-bad control file for the design-md skill. Every defect is planted."
descriptoin: "Planted typo key. Value is a plain string, so only unknown-key fires."
omitted:
  - Elevation
colors:
  primary: "#7A8A99"
  on-primary: "#A8B4C0"
  surface: "#FFFFFF"
  on-surface: "#1A1D21"
typography:
  body-md:
    fontFamily: "Inter"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
rounded:
  md: 8px
spacing:
  md: 16px
radii:
  lg: 12px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body-md}"
    rounded: "{rounded.xl}"
    elevation: "2dp"
    padding: "{spacing.md}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
---

## Overview

Test fixture, not a design proposal. Every defect in this file is planted. It is
the known-bad control for the `design-md` skill: the linter must exit non-zero
on it, and the skill's `lint` wrapper is regression-tested against its output.

Planted defects, in document order, with the rule id each one fires:

| # | Planted defect | Location | Rule id | Severity |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `descriptoin:` — `description` with two letters transposed | frontmatter, top level | `unknown-key` | warning |
| 2 | `omitted: [Elevation]` — `Elevation` is not one of the five valid section names | frontmatter, `omitted` | `unknown-omission` | warning |
| 3 | `radii:` — a token-shaped map under a key the schema does not know | frontmatter, top level | `token-like-ignored` | warning |
| 4 | `rounded: "{rounded.xl}"` — `rounded` defines only `md` | `components.button-primary` | `broken-ref` | **error** |
| 5 | `elevation: "2dp"` — not in the closed component sub-token set | `components.button-primary` | `broken-ref` | warning |
| 6 | `#A8B4C0` text on `#7A8A99` background — below WCAG AA 4.5:1 | `components.button-primary` | `contrast-ratio` | warning |
| 7 | `## Typography` placed before `## Colors` | body headings | `section-order` | warning |

An eighth finding, `token-summary` (info), is not a defect. The linter emits it
whenever tokens are defined.

Measured with `@google/design.md@0.4.0`: exit code `1`, `summary` exactly
`{"errors": 1, "warnings": 6, "infos": 1}`, eight findings total.

Two notes on how the planted defects interact:

- Defects 1 and 3 are split across two keys on purpose. A single misspelling
  such as `colours` fires `unknown-key` *and* `token-like-ignored` together,
  which makes the two rules hard to tell apart. Here `descriptoin` carries a
  string value (so only `unknown-key` fires) and `radii` is far enough from
  every schema key in edit distance that only `token-like-ignored` fires.
- Defects 4 and 5 share the rule id `broken-ref` but differ in severity. Rule
  ids alone are not sufficient to classify a finding; read `severity` too.

Findings are emitted in rule-registry order, not document order. Do not sort
them when quoting the output.

## Typography

Out of order on purpose — this heading must precede `## Colors` for defect 7.
One role, `body-md`. `section-order` reports at most one finding, so this single
inversion is the only ordering defect worth planting.

## Colors

Four tokens, all in MD3 families, so `orphaned-tokens` stays quiet and does not
add noise to the expected output. The accent pair is deliberately low contrast:
`#A8B4C0` on `#7A8A99`.

## Layout

One spacing step, `md` 16 px. Present only so that `missing-sections` does not
fire and add a finding the table above does not account for.

## Elevation & Depth

The frontmatter declares `Elevation` in `omitted`, which is invalid — the five
accepted section names are `colors`, `typography`, `spacing`, `rounded`, and
`components`. There is no elevation token section in the format, and no
elevation component sub-token. That is defect 2, and it is the most common
honest mistake in hand-written DESIGN.md files.

## Shapes

One radius, `md` 8 px. The component asks for `{rounded.xl}`, which is defect 4.

## Components

`button-primary` carries defects 4, 5, and 6. `card` is clean and is here as a
contrast: it proves the linter reports per-component, not per-file.

## Do's and Don'ts

- Do keep the defect table above in sync with the file. It is the answer key a
  reader checks the linter against.
- Do keep `card` clean, so the fixture also demonstrates that a valid component
  produces no findings.
- Don't fix a defect here. Fixing them is what `fixture-clean.md` is for.
- Don't add a ninth defect without adding its row to the table and re-running
  the linter — the skill's documentation quotes this file's output verbatim.

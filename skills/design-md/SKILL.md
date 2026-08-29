---
name: design-md
description: "Use when authoring, auditing, or exporting a DESIGN.md design system — design tokens, tailwind config, deslopify a generic look, дизайн-система, фирменные цвета, единый стиль, извлеки палитру по скриншоту, or derive one from a brief or a codebase."
tier: 2
version: 1.0
---

# DESIGN.md Design Systems

## Purpose

DESIGN.md records a design system as machine-readable YAML tokens plus a prose
rationale, so an implementing agent stops using its own defaults. Three gaps
stand between an agent and a usable file:

1. **Syntactic** — schema, references, the eight body sections. Closed by `references/spec-anatomy.md`.
2. **Procedural** — verifiable output handed back unverified. Closed by `scripts/lint` and Route 4.
3. **Substantive** — a *valid* file is not a *useful* one. Closed by `references/anti-slop.md`, and by nothing else.

The third bites hardest because nothing reports it: a file of framework defaults,
`system-ui`, one radius and four truisms lints at zero errors. Toolchain:
`@google/design.md@0.4.0` (Apache-2.0, Google LLC), run via `npx`.

## When to Use This Skill

Use this skill when the user:

- asks for a DESIGN.md, a design system, a token file, or design tokens;
- asks to extract a palette from a screenshot, a mockup, or an image, or to
  derive a system from a brand brief, a codebase, or a tailwind config;
- asks to audit, repair or lint an existing DESIGN.md, export its tokens to
  Tailwind v3/v4, DTCG or CSS custom properties, or compare two revisions;
- says the output looks generic and asks to deslopify it, or writes any of
  дизайн-система, фирменные цвета, единый стиль, извлеки палитру, по скриншоту.

Out of scope: images, logos, component implementation, palettes derived from one
seed colour. This skill produces the specification, not the interface.

## Red Flags

**STOP and READ if you are thinking:**

- "The linter found no errors, so the file is finished." → **WRONG**. Only an
  unresolvable reference and an unparseable token value move the exit code.
  `examples/fixture-clean.md` lints `0 errors, 0 warnings, 1 info`, yet
  `scripts/check-contrast` exits 1 on it: `outline` measures 1.72:1 on `surface`,
  under the 3.0:1 non-text floor. Exit 0 is the entry requirement, not a verdict.
- "I recognise the typeface in this screenshot." → **WRONG**. Grotesques are
  indistinguishable at UI sizes, and a family name in `fontFamily` reads as a
  measured fact forever after. Offer candidates, label yours a placeholder, ask.
- "The brief said nothing about spacing, so a 4/8/16/24 ladder is safe." →
  **WRONG**. An invented value and a measured value are indistinguishable in
  YAML. Declare the section in `omitted` — that field exists for exactly this.
- "`ink` and `paper` describe this palette better than `primary` and `surface`."
  → **WRONG**. `orphaned-tokens` emits one warning per colour whose family sits
  outside the MD3 baseline and which no component references. Deleting
  `components` silences them — the rule returns early on an empty map — and
  leaves a token dump.

## Rationalization Table

| Agent Excuse | Reality |
| :--- | :--- |
| "Exit code 0 means the file passed." | Exactly one rule produces errors. A file with no `primary`, no typography, an out-of-order body and a misspelled key that `export` drops still exits 0. Report the `summary` triple, never the exit code alone. |
| "The linter said nothing about my palette, so the palette is fine." | No rule reads a hue ramp, a type scale, a radius set, or one word of prose. `references/anti-slop.md` is the only check that does. |
| "I will read the hex values off the screenshot myself." | Compression, antialiasing, gradients and the colour profile each move the value. A hex written from perception is a fabrication shaped like a measurement. `scripts/extract-palette` measures; you assign roles. |
| "`#3b82f6` is a safe accent to start from." | That is Tailwind blue-500. It measures 3.68:1 on white, below AA. Six of the nine most-copied framework accents fail 4.5:1 on white, and readers recognise them on sight. |
| "`token-summary` is noise; I skip the info lines." | It is the only trace of a silently dropped token: a `spacing` value written `16` with no unit vanishes and raises no finding at all. Read the counts back against what you wrote. |
| "I will add `elevation` to the component." | The sub-token set is closed at eight names. An invented key is a `broken-ref` warning and every exporter drops it. Depth belongs in `## Elevation & Depth` prose. |
| "One lint pass is enough." | `section-order` reports at most one inversion per run, and `orphaned-tokens` stays silent until the first component exists. Re-lint after every fix round. |
| "The template in `assets/` is close enough to ship." | `template-skeleton.md` lints clean carrying a conspicuous magenta accent and fifteen `PROVISIONAL` markers; a clean lint on an unedited copy proves only that the structure survived. |

## Execution Mode

- **Mode**: `hybrid`
- **Why this mode**: measurement is script work, judgement is not. Colour values,
  contrast ratios and lint findings come from `scripts/` and the upstream CLI,
  because each is a number an agent gets wrong by eye. Template choice, role
  assignment, naming and the prose body are the agent's alone, and every route
  below ends in a script run.

## Script Contract

Three executables in `scripts/`, all Python 3, all **read-only**: each writes a
report to stdout and modifies no file. Pass absolute paths.

| Script | Command and flags | Output |
| :--- | :--- | :--- |
| `lint` | `scripts/lint FILE…` · `--strict` `--json` `--list-rules` `--version PIN` `--timeout SECONDS` | a `severity/rule/path/message` table per file, a `REMEDY` line per rule id that fired, and a `PASS`/`FAIL` verdict carrying the upstream `summary` triple |
| `check-contrast` | `scripts/check-contrast FILE` · `--level aa\|aaa\|both` `--min RATIO` `--matrix summary\|plausible\|full` `--strict-decorative` `--self-test` `--timeout SECONDS` `--json` | WCAG 2.x ratios for every intended text-on-surface pair, a typography table and an advisory matrix, at AA 4.5, AA-large 3.0, AAA 7.0 and the 3.0 non-text threshold |
| `extract-palette` | `scripts/extract-palette IMAGE` · `--colors N` `--ignore-edges PCT` `--region X,Y,W,H` `--min-share PCT` `--merge-distance D` `--json` | dominant colours as `HEX`, `SHARE`, `BUCKETS`, `HUE`, `L*`, `C*` and a heuristic `HINT` |

`--strict` fails `lint` on warnings, which is what makes a gate meaningful, and
`--list-rules` prints all fourteen rule rows offline. **Exit codes differ per script:**

| Code | `lint` | `check-contrast` | `extract-palette` |
| :--- | :--- | :--- | :--- |
| 0 | no errors (and no warnings under `--strict`) | every gated intended pair meets the gate | success |
| 1 | errors, or warnings under `--strict` | a gated intended pair fails, or `--self-test` mismatched | an out-of-range option value, or a `--region` malformed, outside the image, or combined with `--ignore-edges` |
| 2 | input problem, or a usage error | input problem, or a usage error | image missing, unreadable, or corrupt |
| 3 | npx or the CLI unavailable, the call timed out, or non-JSON output | the `export` call failed, or no colors defined | no available decoder handles the format |

With several files `lint` returns the worst code, ordered `3 > 2 > 1 > 0`.
**Artifacts: none** — no script writes a file. Exit 3 means "the tool did not
run", never "the file is fine": report no verdict from such a run. The raw form,
for `diff`, `spec` and anything the wrappers omit:

```text
cd /tmp && npx --yes @google/design.md@0.4.0 lint|diff|export|spec <ABSOLUTE-PATH>
```

`cd /tmp` is load-bearing: a workspace declaring the same bin name shadows it.
`export` requires `--format` (`css-tailwind`, `json-tailwind`, `tailwind`,
`dtcg`, `css-vars`); `lint --format text` silently returns JSON. Full flags: each
`--help` and `scripts/README.md` §2 (`--version PIN` takes an argument).

## Safety Boundaries

- **Writable scope**: only the DESIGN.md the user asked for, at a path they named
  or in their working directory — nothing else in their tree.
- **Never overwrite the skill's own material**: `assets/`, `examples/` and
  `references/` are read-only, every template and fixture lint-verified as it
  stands. Copy a template out and edit the copy.
- **Network**: `lint` and `check-contrast` shell out to
  `npx --yes @google/design.md@0.4.0`, which reaches `registry.npmjs.org` on the first call
  — roughly 30 seconds, then the npx cache, and the skill's only network access. `lint`
  announces that wait on stderr; `check-contrast` prints nothing until its report, so a
  cold run of it looks hung. Offline with a cold cache both exit 3, never a clean verdict.
- **User-supplied images**: `extract-palette` decodes an image the user supplied,
  reading pixels and writing nothing; it spawns no process and makes no network
  call. Confirm the path, do not fetch an image from a URL unless asked.
- **Installs**: `bash scripts/install.sh` is optional and puts Pillow into
  `scripts/.venv/` only — nothing global. **Never** vendor upstream `design.md`
  source or its `examples/` here.

## Validation Evidence

- Every `assets/template-*.md` and `examples/example-saas-dashboard.md` lints at 0 errors, 0 warnings.
- `examples/fixture-clean.md` → exit 0, `{"errors": 0, "warnings": 0, "infos": 1}`; `examples/fixture-broken.md` → exit 1, `{"errors": 1, "warnings": 6, "infos": 1}`.
- `scripts/check-contrast --self-test` reproduces all five WCAG known answers, exit 0; the same script exits 1 on `examples/fixture-clean.md` at `outline on surface` 1.72:1 — proof that a clean lint is not a clean file.
- `scripts/extract-palette` on a 400x300 PNG: clusters covering 100.0% of counted pixels, exit 0. Detail: `references/linter-rules.md` §20–§22; `scripts/README.md` §3 and §8.

## The Linter Checks Form, Never Quality

Never let a clean run stand in for a review. **What it checks**: eleven rule
descriptors emitting fourteen `(rule, severity)` rows — an unresolvable reference,
an unrecognized component sub-token, a missing `primary`, intra-component contrast
at AA 4.5:1, orphaned colour names, empty `spacing`/`rounded`/`typography`, H2
order, misspelled and token-shaped keys, the three `omitted` outcomes.

**What no rule checks**: whether the type sizes form a modular scale, the
neutrals share a hue, every element uses one radius, `fontFamily` is `system-ui`,
the values were copied from Tailwind or Bootstrap, the accent carries more than
one role, `Do's and Don'ts` names *this* product, or all eight body sections are
present. Zero findings on a file with every one of those defects is the normal
case. Two gates close the opening, both part of the procedure. **Quality** —
`references/anti-slop.md`: sixteen prohibitions, each with a detection command
and a pass condition, plus a sixteen-step self-audit; the fixture opening that
file lints at zero errors and fails twelve of them. **Accessibility** —
`scripts/check-contrast`: upstream's `contrast-ratio` rule inspects only
components declaring both `backgroundColor` and `textColor`, only at AA 4.5:1,
never the palette, while this script walks every intended text-on-surface pair at
AAA and the 3.0:1 non-text threshold too.

## `omitted` Exists So an Unknown Never Becomes a Fabrication

**This is the single most important idea in the format.** No source contains
everything: a screenshot has no font names, a brief has tone and no numbers, a
codebase has values and no rationale. Plausible filler lints clean and hides
which values were observed.

```yaml
omitted:
  - section: components
    reason: "The screenshot showed one screen; no component inventory was visible."
  - spacing
```

The valid names are exactly five — `colors`, `typography`, `spacing`, `rounded`,
`components` — and they name token maps, not body sections. `elevation`,
`layout`, `states`, `dark-theme` raise `unknown-omission` and belong in body
prose; naming a populated section raises `redundant-omission`.

## Route 1 — from a text description

1. Classify the product: surface class (application UI or reading surface), UI
   language, density, named constraints (brand colour, required font, a11y target). With fewer than two of {palette, typography, density} given, ask.
2. Pick the base template below; copy it to the user's path and edit the copy.
3. Substitute values while preserving the **relationships**: neutral step count,
   scale ratio, spacing base unit, radius progression, one accent in one role,
   every contrast pair the template had cleared. Keep the MD3 token names.
4. Rewrite `## Overview` and `## Do's and Don'ts` for this brand. Delete any
   sentence that would still be true of a different product.
5. Put everything the description did not decide into `omitted`, with a reason.
6. Run Route 4. Detail: `references/extraction.md` §1.

## Route 2 — from a screenshot

1. Read the image. Record its character in one sentence: light or dark, dense or
   airy, how many surface levels, borders or shadow. Start from the template that Template Selection names below: take its section order and token vocabulary from there, and author every frontmatter value from the measurements rather than from the template.
2. **Measure the colours with the script**, never by eye:
   `scripts/extract-palette <ABSOLUTE-IMAGE-PATH> --min-share 0.1`. The default floor of 0.5 sits right on top of a one-control accent: on a 1440x900
   dashboard capture `#e25a3c` measures 0.52%, and `--ignore-edges 4` — 57 px off each side, a quarter of the 233 px rail — pushes it to
   0.40% and out of the report. Add that flag for a browser screenshot with chrome to crop, never for a full-app capture.
3. Assign roles yourself: largest share is `background`, the neutral inset from
   it is `surface`, the high-chroma small-share colour on one control type is
   `primary`. Name everything in the MD3 vocabulary. Recovery: with no `accent candidate` row, lower `--min-share` again; with the light planes collapsed into one row, lower `--merge-distance` — at 3.0 the 71.70% `#ffffff` splits into `#ffffff` 58.51% and `#f7f4ef` 16.56%.
4. Count what the image supports (surface levels, radius steps, type sizes), not
   absolute pixels — a retina capture scales all of them by an unknown ratio.
5. Do not name a font. Where a letterform is legible, offer two or three candidates, write one as a labelled placeholder, and ask. With no legible letterform — small text, heavy compression, a logo-only capture — offer no candidates and declare `typography` in `omitted` with that reason (`references/linter-rules.md` §12): a placeholder with no letterform behind it reads as a measured fact forever after.
6. Write only the components actually visible: two visible controls means two
   components, not a plausible library of eight.
7. Everything absent goes to `omitted` with a reason, or — where no section name fits (states, dark theme, motion, breakpoints) — to prose.
8. Run Route 4, then hand back a **hypothesis** with `MEASURED`, `INFERRED`,
   `NEEDS CONFIRMATION` and `OMITTED` separated. Hand-back template and
   reliability table: `references/extraction.md` §2 (B.5); a worked output of
   this route: `examples/example-saas-dashboard.md`.

## Route 3 — from a codebase

1. Harvest what is **used**, not what is declared: hex literals, `var(--…)`
   references, `@theme` blocks, tailwind config entries, utility classes,
   dimensions — each with a count. Commands: `references/extraction.md` §3 (C.1).
2. Rank by frequency and state the threshold applied: a value used once is
   probably an accident, not a token. Check each value against the AS-10 table in `references/anti-slop.md` before it enters the token map: a framework default is often the top-count hex in a tree, and frequency makes it measured, never chosen — name it in the hand-back and get a brand value decided.
3. Collapse near values into steps and **report every collapse**: silent rounding destroys deliberate optical adjustments. Rename `bg`/`accent` into MD3 families.
4. Verify the round trip with `export --format json-tailwind` from `/tmp` against
   the project config: a value present only in the codebase is a token the
   extraction missed (`references/export-formats.md` §5).
5. Run Route 4, and hand back in the Route 2 buckets — `MEASURED`, `INFERRED`, `NEEDS CONFIRMATION`, `OMITTED`: a codebase settles values and leaves intent undetermined, and an inferred value written flat is indistinguishable from a harvested one. Note that `export` never lints: it exits 0 on a file with errors.

## Route 4 — lint, fix, re-run (mandatory)

A procedure that ends without a clean lint run has not completed; handing an
unlinted draft back is the failure this skill exists to prevent.

1. `scripts/lint <ABSOLUTE-PATH>` — add `--strict` for anything gate-shaped,
   since warnings carry the substantive complaints. `references/linter-rules.md`
   §1 resolves any finding in one table.
2. Fix **every** finding, not only the errors, and re-run after each fix round.
   `scripts/lint --list-rules` prints all fourteen rows with a remedy, offline.
3. Read the `token-summary` counts back against what you wrote: a bad reference
   in `colors`/`spacing`/`rounded`, or a unitless number, drops the token in
   silence, and that count is the only trace of it.
4. Quote the final `summary` triple verbatim in the hand-back.

## Template Selection

Copy one file out of `assets/` and edit the copy. First match wins.

| # | Condition | Template |
| :--- | :--- | :--- |
| R0 | The product ships a Russian-language UI (override — beats every rule below) | `assets/template-cyrillic.md` |
| R1 | Application UI: dashboard, admin, console, CRM, IDE, analytics, SaaS | `assets/template-product-saas.md` |
| R2 | Reading surface: magazine, blog, docs, newsletter, essay, portfolio | `assets/template-editorial.md` |
| R3 | Outside R1 and R2 — game, print, hardware panel, embedded display | `assets/template-skeleton.md` |
| R4 | Too thin to classify, or authoring from zero | `assets/template-skeleton.md` |

**R0 is correctness, not taste.** Google Fonts serves Instrument Serif and Bodoni
Moda with `latin` and `latin-ext` subsets only, so Russian text in those families
falls back silently to a system serif. Families verified to carry Cyrillic: Golos
Text, Onest, Inter, IBM Plex Sans, JetBrains Mono, Manrope. Where R0 and R2 both
apply, base on `template-cyrillic.md` and import only the *relationships* from
`template-editorial.md`. Every template lints at 0 errors, holds the eight body
sections in canonical order, and names colours in MD3 families.

## Traps to Know Before Writing a Line

Quote every hex — unquoted, `#RRGGBB` is a YAML comment and the value becomes an
**error** reading `'null' is not a valid color.` Quote every `{reference}` —
unquoted, `{` opens a flow mapping and no rule fires at all. Write units: a bare
`16` in a Dimension slot drops the token with no finding. Only `##` headings reach
`section-order`, `Do's and Don'ts` MUST use the ASCII apostrophe, and a fenced
`yaml` block anywhere in a DESIGN.md body is merged into the token set — a
top-level key colliding with the frontmatter then halts every rule at exit 0.
Tables: `references/spec-anatomy.md` §11, `references/export-formats.md` §9.

## References Map

| File | Load it when |
| :--- | :--- |
| `references/spec-anatomy.md` | Writing or repairing frontmatter: the nine keys, value types, references, the closed eight component sub-tokens, `omitted`, the eight body sections, a verified-traps table. |
| `references/linter-rules.md` | A finding needs resolving: fourteen rule rows with verbatim messages and remedies, the exit-code contract, the rule-less parser and model findings, both fixtures quoted in full. |
| `references/extraction.md` | Executing Route 1, 2 or 3: full procedures, the screenshot reliability table, the hand-back template, the codebase harvest commands. |
| `references/anti-slop.md` | Before handing any file back: sixteen prohibitions, each with a detection command and a pass condition, plus the self-audit checklist. |
| `references/export-formats.md` | Exporting or comparing revisions: the five `export` formats and their coverage matrix, round-trip recipes, `diff` semantics, corrections to the upstream help text. |
| `examples/example-saas-dashboard.md` | A finished screenshot extraction with its reliability ledger, to read against your own draft. |
| `examples/fixture-clean.md`, `examples/fixture-broken.md` | The known-good and known-bad controls the documented lint output was measured on. |
| `scripts/README.md` | A script misbehaves, an exit code needs explaining, or the version pin needs bumping. |

## Quality Checklist

- [ ] `scripts/lint --strict FILE` exits 0 — or every remaining finding is a `contrast-ratio` shortfall between two colours measured from the source, each named with its ratio and justified; no other rule is exempt, and no measured value is edited to clear a finding. The `summary` triple is quoted in the hand-back rather than summarised as "clean".
- [ ] `scripts/check-contrast FILE` exits 0, or every failing pair is named and justified, and the `token-summary` counts equal the keys actually written in each map.
- [ ] All eight body sections are present in canonical order at `##` level, with the ASCII apostrophe in `Do's and Don'ts` (a house rule; no linter rule enforces it).
- [ ] Colour tokens use MD3 family names, `primary` exists, and every non-baseline name is referenced by a component.
- [ ] Every section the source did not settle is in `omitted` with a `reason`, no populated section appears there, and nothing anywhere is invented.
- [ ] The `references/anti-slop.md` self-audit passes, or each miss is explained: no copied framework hexes, no `system-ui` first family, more than one radius referenced.
- [ ] `## Overview` and `## Do's and Don'ts` name *this* product and its own tokens; delete any rule that would read identically in another product's file, and confirm nothing under `assets/`, `examples/` or `references/` was modified.
- [ ] For an extraction: measured, inferred and unknown are separated in the hand-back, and no font family is asserted as observed.

## Dependencies

| Dependency | Required for | Install |
| :--- | :--- | :--- |
| Python 3 (stdlib only) | all three scripts | present on the host |
| Node.js 18+ | `npx`, used by `lint` and `check-contrast` | https://nodejs.org/ |
| `@google/design.md@0.4.0` | the linter, `export`, `diff`, `spec` | fetched by `npx --yes` on first use, then cached; **never vendored** |
| Pillow (optional) | `extract-palette` on JPEG, WebP, HEIF, interlaced PNG | `bash skills/design-md/scripts/install.sh` → `scripts/.venv/` |

`extract-palette` reads non-interlaced PNG at bit depth 8/16 with its own stdlib
decoder — the shape of every macOS and Linux screenshot — so the screenshot route
runs with no install at all. `bun` is required nowhere and MUST not be added.

The version pin is deliberate: the format declares `version: alpha` and this
skill quotes upstream messages verbatim. Bumping it is a change to the skill —
follow `references/export-formats.md` §8.1 and `scripts/README.md` §5, moving the
pin in `lint`, `check-contrast` and `install.sh` together. This skill is
Apache-2.0 and carries no upstream source or examples.

# DESIGN.md — format anatomy

Schema reference for the DESIGN.md format as implemented by
`@google/design.md@0.4.0`. An agent that has read this file is able to author a
syntactically correct DESIGN.md without opening upstream sources.

Every behavioural claim below was measured by running the linter on a probe
file. All quoted output is verbatim.

Companion references: `linter-rules.md` (the rule registry and how to fix each
finding), `export-formats.md` (`export` / `diff`), `extraction.md` (how to
decide what goes in the file), `anti-slop.md` (what not to put in it).

Invocation used throughout:

```
cd /tmp && npx --yes @google/design.md@0.4.0 lint <ABSOLUTE-PATH>
```

`cd /tmp` first: a workspace elsewhere shadows the bin name. Measured on this
machine: about five seconds on the first run while the package is fetched, and
under a second on every run after that.

---

## 1. The two-part anatomy

A DESIGN.md file has two parts, and they carry different kinds of truth.

**Part 1 — YAML frontmatter: the tokens.** A machine-readable map of design
values. This is the authority for anything a program consumes: `export`, the
token comparison in `diff`, and every token-level lint rule read the YAML and
nothing else. A value that exists only in the prose does not exist as far as
tooling is concerned.

**Part 2 — Markdown body: the rationale.** H2-delimited prose that says what
the tokens mean, when to reach for which one, and what the system refuses to
do. This is the authority for anything a human or an agent must *decide*. The
linter checks the body's section ORDER and nothing else — it never reads a
word of the prose. Everything the token schema cannot express (elevation,
borders, gaps, states, motion, grid, voice) lives here or is lost.

Both parts are needed. Frontmatter alone produces a token dump that any
consumer can read and no consumer can apply correctly. Body alone produces a
style guide that no tool can act on.

### 1.1 Where the YAML may live

Two accepted positions:

- **Frontmatter** — a `---` fence at the very top of the file, closed by a
  second `---`. This is the normal form; use it.
- **A fenced ```` ```yaml ```` code block** anywhere in the body. Verified: a
  file whose only YAML is a fenced `yaml` block is parsed and its tokens are
  counted.

### 1.2 The unterminated-frontmatter trap

If the opening `---` has no closing `---`, the whole block is invisible. Every
token silently disappears and the linter emits exactly one finding:

```text
{
  "findings": [
    {
      "severity": "warning",
      "message": "No YAML content found. Expected frontmatter (---) or fenced yaml code blocks."
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 1,
    "infos": 0
  }
}
```

Exit code 0. A file that "passes" with this message defines nothing. When a
lint run reports zero tokens you did not expect, check the closing `---`
first.

Note the same output shape for a file with no YAML at all. Section-order
checking does not run in that state either: a probe with `## Typography`
before `## Colors` and no frontmatter produced only the warning above.

---

## 2. The nine top-level keys

`SCHEMA_KEYS`, exhaustive. There are nine and no more.

| Key | Type | Linter requires it | Read by |
| :--- | :--- | :--- | :--- |
| `version` | string | no | no consumer measured; the conventional value is `alpha` |
| `name` | string | no | `export --format dtcg`, as `$description` — but only when `description` is absent |
| `description` | string | no | `export --format dtcg`, as `$description`, in preference to `name`; humans and agents |
| `omitted` | array of string or of `{section, reason}` | no | `omitted-rules`, `missing-sections`, `missing-typography` |
| `colors` | map: token name → Color | no | `broken-ref`, `missing-primary`, `contrast-ratio`, `orphaned-tokens`, all exports |
| `typography` | map: token name → typography object | no | `missing-typography`; every export except `css-vars`, which emits no typography at all |
| `rounded` | map: token name → Dimension | no | `missing-sections`, all exports |
| `spacing` | map: token name → Dimension | no | `missing-sections`, all exports |
| `components` | map: component name → sub-token object | no | `broken-ref`, `contrast-ratio`, `orphaned-tokens` |

### 2.1 Required versus conventional — state this precisely

**The linter requires nothing.** Not `name`, not `version`, not one token.

Verified: a file whose entire content is

```yaml
---
name: Name Only
---
```

produces

```text
{
  "findings": [],
  "summary": {
    "errors": 0,
    "warnings": 0,
    "infos": 0
  }
}
```

and a file with no frontmatter at all exits 0 as well (with the one warning in
§1.2).

`name` is the **conventional** minimum, not a linter constraint. Some
descriptions of the format call `name` "the single mandatory field"; that is a
statement about house style. Keep the distinction, because it changes what you
do when a value is unknown:

- What the **linter requires**: nothing. Never invent a value to satisfy the
  linter — the linter did not ask.
- What the **convention** is: always set `name`; set `description` when the
  file will be read by someone who did not write it; set `version: alpha`
  while the format is in alpha.
- What a value being **unknown** means: put the section in `omitted` (§7).
  Do not fabricate.

**When `name` itself has no source.** No supplied product name and a redacted
logo leave `name` with nothing to hold, and `omitted` is not the escape: it
takes only the five token-map names (§7.3), so `- name` is rejected. Verified
on a file declaring `name`, `version` and `description` under `omitted` — one
warning each:

```text
{
  "severity": "warning",
  "path": "omitted",
  "message": "unknown section name 'name' in omitted key",
  "rule": "unknown-omission"
}
```

The convention, so that every extraction resolves this the same way:

- **Keep the key and mark it.** Write
  `name: "UNCONFIRMED — product name not supplied; drafted from <source-file>"`.
  Do not invent a product name. Do not drop the key either: a file with no
  `name` lints clean (verified, 0 errors 0 warnings), but an absent key reads as
  an oversight, while a marked value reads as a request.
- **Know where the string travels.** `export --format dtcg` emits `name` as
  `$description` when `description` is absent (§2), so the marker reaches the
  exported token file. That is intended. Setting `description` overrides it.
- **Say it in the hand-back.** `name` is a placeholder, never an observation, so
  it belongs in the `NEEDS CONFIRMATION` bucket, not `MEASURED` or `INFERRED`:
  *"`name` — placeholder, not observed. No product name was supplied and the
  logo was redacted. Replace it before this file is published or exported."*

### 2.2 Unknown top-level keys

Unknown keys are allowed — the schema is extensible by design. Two rules
police them, and both produce warnings, never errors:

- `unknown-key` fires on a key within edit distance 2 of a schema key
  (`colours` → `colors`). A distant custom key stays silent.
- `token-like-ignored` fires on an unknown key whose value looks like a token
  map (contains a hex/dimension leaf or a typography property name).

See `linter-rules.md` for the verbatim messages. The practical rule: put
custom metadata under a key that does not resemble a token map, or put it in
the prose body.

---

## 3. Value types

### 3.1 Color

Any valid CSS color. All forms are converted to sRGB internally for contrast
checking. Verified accepted, sixteen forms in one probe file that linted with
zero errors:

```yaml
colors:
  primary: "#28f"                                   # 3-digit hex
  on-primary: "#28fa"                               # 4-digit hex (alpha)
  secondary: "#2288ff"                              # 6-digit hex
  on-secondary: "#2288ffcc"                         # 8-digit hex (alpha)
  tertiary: cornflowerblue                          # named
  error: rgb(200 30 40)
  surface: rgba(255, 255, 255, 0.9)
  on-surface: hsl(215 20% 12%)
  outline: hsla(215, 20%, 62%, 0.6)
  background: hwb(215 10% 5%)
  on-background: oklch(0.22 0.03 250)
  surface-variant: oklab(0.85 0.01 -0.02)
  outline-variant: lch(60% 30 250)
  inverse-surface: lab(20% 5 -10)
  surface-tint: "color-mix(in srgb, #2288ff 40%, white)"
  scrim: transparent
```

**Default to 6-digit hex `#RRGGBB`.** It is unambiguous, it is what `export`
emits, and it is what the `contrast-ratio` message quotes back at you.

Quoting: a value beginning with `#` MUST be quoted, or YAML reads it as a
comment and the value becomes null. Verified — `primary: #1B4F9C` unquoted
produces an error and takes `missing-primary` with it:

```text
{
  "severity": "error",
  "path": "colors.primary",
  "message": "'null' is not a valid color. Expected a CSS color value (e.g., #ffffff, rgb(0 0 0), oklch(0.5 0.2 240))."
}
```

`color-mix(...)` contains `, ` and MUST be quoted whole. Bare keywords
(`transparent`, `cornflowerblue`) and function forms without a leading `#` do
not need quotes, but quoting them is harmless.

An unparseable color is an **error**, not a warning:

```text
{
  "severity": "error",
  "path": "colors.brandish",
  "message": "'not-a-color' is not a valid color. Expected a CSS color value (e.g., #ffffff, rgb(0 0 0), oklch(0.5 0.2 240))."
}
```

### 3.2 Dimension

A number plus a unit. The units are exactly three: **`px`, `em`, `rem`**.
Wherever the check runs, anything else is an error. Verified:

```text
{
  "severity": "error",
  "path": "typography.body.fontSize",
  "message": "'12pt' has an invalid unit 'pt'. Only px, rem, and em are allowed."
}
{
  "severity": "error",
  "path": "rounded.md",
  "message": "'50%' has an invalid unit '%'. Only px, rem, and em are allowed."
}
```

Write no `%`, no `pt`, no `vh`, no `ch` and no unitless value in a Dimension
slot.

**But the unit check does not run on every slot.** Verified: it runs on
`typography.<token>.<property>` and on `rounded.<token>`. It does **not** run on
`spacing.<token>`, and it does not run on a component's `padding` / `size` /
`height` / `width`. A file whose only content is

```yaml
---
name: Spacing pt only
spacing:
  md: 12pt
---
```

lints `{"errors": 0, "warnings": 0, "infos": 1}` — the one info is
`Design system defines 1 spacing token.` — and `export --format css-vars` emits

```text
:root {
  --spacing-md: 12pt;
}
```

`10vh` and `2ch` under `spacing`, and `height: 40pt` on a component, pass just
as quietly. Use `px` / `rem` / `em` everywhere anyway: the value reaches the
exporter untouched, and no rule will tell you it is wrong.

**The bare-number trap.** A unitless number in a Dimension slot is *not* an
error — it is silently dropped. Verified: a file whose only content is

```yaml
---
name: Spacing bare number
spacing:
  md: 16
---
```

lints with `{"errors": 0, "warnings": 0, "infos": 0}` and **no**
`token-summary` finding at all, because no token was created. `spacing: {md: 16}`
looks defined and is not. Write `16px`.

The one place a unitless number is meaningful is `typography.lineHeight`
(§5).

### 3.3 Reference

`{map.token}` — curly braces around a dotted path into the YAML tree. Verified
behaviour:

- **Two segments.** `{colors.primary}`, `{rounded.md}`, `{spacing.md}`,
  `{typography.body-md}`. The path names a whole token.
- **Deeper paths do not resolve.** `{typography.body-md.fontSize}` in a
  component produced
  `Reference {typography.body-md.fontSize} does not resolve to any defined token.`
  There is no way to reference one property of a typography token.
- **Cross-map references resolve.** `rounded: {md: "{spacing.md}"}` with
  `spacing: {md: 16px}` exported as `--radius-md: 16px`.
- **References resolve transitively.** A twelve-link chain
  `c0: "#123456"`, `c1: "{colors.c0}"` … `c12: "{colors.c11}"` resolved
  end-to-end; a component referencing `{colors.c12}` was contrast-checked
  against `#123456`. The configured ceilings are
  `max_token_nesting_depth: 20` and `max_reference_depth: 10`; treat them as
  resolver limits, not as an authoring budget. One hop is the norm; longer
  chains hide the resolved value from every reader.
- **A reference always needs quotes.** `{` opens a YAML flow mapping, and the
  failure is silent. Verified: `backgroundColor: {colors.primary}` unquoted on
  a component produced no `broken-ref` error and no `contrast-ratio` finding —
  the sub-token held a YAML map, not a reference, and every rule that needed a
  color skipped it. Write `backgroundColor: "{colors.primary}"`.
- **An unresolvable reference behaves differently by location.** In a
  component it is an **error** under `broken-ref`. In a top-level token map
  (`colors`, `spacing`, …) it is **silently dropped** — no finding, and the
  token does not exist at all. Verified: `colors: {primary: "#123456", accent: "{colors.nope}"}`
  reported `Design system defines 1 color.` and no error.

That asymmetry matters: a typo in a palette alias fails silently. Read the
`token-summary` count after every edit and check it against what you wrote.

---

## 4. Composite values

A component sub-token value may be a bare literal, a single reference, or
several references in one string. Verified accepted:

```yaml
components:
  button-primary:
    padding: "{spacing.sm} {spacing.md}"
    height: 40px
    width: auto
```

`"{spacing.sm} {spacing.md}"` is the CSS shorthand idiom (vertical horizontal)
and lints clean. There is no separate `paddingX`/`paddingY` sub-token.

---

## 5. `typography.<token>` — seven properties

| Property | Type | CSS property it configures |
| :--- | :--- | :--- |
| `fontFamily` | string | `font-family` |
| `fontSize` | Dimension | `font-size` |
| `fontWeight` | number, bare or quoted string | `font-weight` |
| `lineHeight` | Dimension **or** unitless number | `line-height` |
| `letterSpacing` | Dimension | `letter-spacing` |
| `fontFeature` | string | `font-feature-settings` |
| `fontVariation` | string | `font-variation-settings` |

The third column is what the value means in CSS, not a promise that `export`
carries it there — see below and §5.1.

All seven in one token, verified to lint with zero errors and zero warnings:

```yaml
typography:
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0em
    fontFeature: "'ss01' 1, 'tnum' 1"
    fontVariation: "'opsz' 16"
```

`fontFeature` and `fontVariation` carry OpenType settings verbatim. Their
values contain single quotes and commas, so quote the whole string with double
quotes.

**No exporter carries them.** Verified on exactly the token above: none of
`css-tailwind`, `json-tailwind`, `dtcg` or `css-vars` emits either property.
`css-tailwind` returned only `--font-body-md`, `--text-body-md`,
`--tracking-body-md` and `--font-weight-body-md`. These two properties are for
the reader of the file and for a consumer that reads the frontmatter itself.

### 5.1 lineHeight — the recommendation and its honest cost

A **unitless** `lineHeight` is the recommended CSS practice: it is a
multiplier of the element's own font size, so it survives being inherited by
text at a different size. `lineHeight: 1.5` on a 16px token means 24px.

**But `export --format css-tailwind` drops it.** Verified on a file containing
`lineHeight: 1.6`:

```text
@theme {
  --color-primary: #1b4f9c;
  --color-on-primary: #ffffff;
  --font-body-md: "Inter";
  --text-body-md: 16px;
  --font-weight-body-md: 400;
  --radius-md: 16px;
  --spacing-md: 16px;
}
```

No `--leading-*` variable was emitted. (In that probe `rounded.md` was
`"{spacing.md}"`, which is why `--radius-md` reads `16px`.) The dropped line
height is not an error and the linter says nothing about it.

`json-tailwind` and `dtcg` drop a unitless `lineHeight` too, and `css-vars`
emits no typography in any case — so no export format preserves it. A Dimension
survives: verified, changing that same probe to `lineHeight: 24px` produced
`--leading-body-md: 24px` in `css-tailwind`, `"lineHeight": "24px"` in
`json-tailwind` and `"lineHeight": 24` in `dtcg`. Choose knowingly:

- Authoring for humans and agents: unitless. It is the better value.
- Authoring for a Tailwind v4 round-trip that must carry line height: use a
  Dimension (`lineHeight: 24px`), and accept that it will not scale with
  inherited size.

Do not claim round-trip fidelity for a unitless `lineHeight`.

---

## 6. `components.<name>` — a CLOSED sub-token set

Exactly eight sub-tokens are recognised:

```
backgroundColor, textColor, typography, rounded, padding, size, height, width
```

All eight in one component, verified clean:

```yaml
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm} {spacing.md}"
    size: 40px
    height: 40px
    width: auto
```

Anything else is a **warning** under rule id `broken-ref`, and the message
echoes the whole valid list:

```text
{
  "severity": "warning",
  "path": "components.chip.elevation",
  "message": "'elevation' is not a recognized component sub-token. Valid sub-tokens: backgroundColor, textColor, typography, rounded, padding, size, height, width.",
  "rule": "broken-ref"
}
```

### 6.1 What the set cannot express, and where it goes instead

There is no sub-token for elevation, shadow, border, border color, border
width, gap, opacity, transition, or state (`hover`, `focus`, `disabled`,
`pressed`). Inventing one produces the warning above and the value is ignored
by every exporter.

These are not omissions to work around. They belong in the **prose body**, in
the section that owns them:

| Missing from the schema | Where it belongs |
| :--- | :--- |
| shadow ladder, z-layering, "flat vs raised" | `## Elevation & Depth` |
| border widths, border color roles, dividers | `## Shapes` (or `## Colors` for the role) |
| gaps between items, grid columns, density, breakpoints | `## Layout` |
| hover / focus / disabled / pressed behaviour | `## Components` |
| motion, duration, easing | `## Components` or `## Layout` |

A border **color** is carried as a color token (`outline`,
`outline-variant`) even though no component sub-token consumes it — but see
`orphaned-tokens` in `linter-rules.md`: an unreferenced color outside the
MD3 baseline families draws a warning once any component exists.

### 6.2 Naming components and colors

Component names are free-form (`button-primary`, `table-row`, `chip`).

Color token names are **not** free in practice. Once `components` is
non-empty, `orphaned-tokens` warns about every color token that no component
references and whose family is outside the MD3 baseline set (`primary`,
`secondary`, `tertiary`, `error`, `surface`, `background`, `outline`). A
palette named `ink` / `paper` / `warm-grey-300` generates one warning per name.
Use the MD3 family vocabulary, or reference the token from a component. Full
mechanism in `linter-rules.md`.

---

## 7. `omitted` — the field that exists so you do not invent

### 7.1 Why it exists

This is the single most important idea in the format for anyone extracting a
design system from a screenshot, a brand description, or a codebase.

A source almost never contains everything. A screenshot shows no font names,
no hover states, no dark theme. A brand brief gives tone and no numbers. The
tempting failure is to fill the gaps with plausible values — a `spacing` scale
that looks like every other spacing scale, a `rounded` ladder nobody measured.
The resulting file lints clean and is wrong, and nothing downstream can tell
which values were observed and which were guessed.

`omitted` is the format's designed alternative. It records, in the file
itself, that a section was **deliberately** not specified. The declaration is
machine-readable, so a consumer knows to fall back to its own defaults instead
of trusting a fabrication.

**Rule for every extraction procedure: what the source does not contain goes
in `omitted`, not in the tokens.**

### 7.2 The two accepted shapes

`omitted` is an array whose elements may be bare strings, `{section, reason}`
objects, or a mix of both. `reason` is optional. Verified:

```yaml
omitted:
  - section: components
    reason: "The screenshot showed one screen; no component inventory was visible."
  - section: rounded
    reason: "Radii were not measurable at this raster size."
  - spacing
```

Always write the `reason` when you have one. It is the only place a reader
learns whether a section is missing because it was unknowable or because it
was out of scope.

### 7.3 The five valid section names

Exhaustive, and they are the **token map** names, not the body section names:

```
colors, typography, spacing, rounded, components
```

Matching is case-insensitive: `- Spacing` is accepted and normalised to
`omitted.spacing`. Anything outside the five is a warning. Verified — note
that `layout` is a body section, not a token map, so it is invalid here:

```text
{
  "severity": "warning",
  "path": "omitted",
  "message": "unknown section name 'Elevation' in omitted key",
  "rule": "unknown-omission"
}
{
  "severity": "warning",
  "path": "omitted",
  "message": "unknown section name 'layout' in omitted key",
  "rule": "unknown-omission"
}
```

### 7.4 Semantics

Three outcomes, each with its own rule id (the descriptor `omitted-rules`
never appears in output):

| Situation | Rule id | Severity |
| :--- | :--- | :--- |
| section named, no tokens defined for it | `declared-omission` | info |
| section named, tokens ARE defined for it | `redundant-omission` | warning |
| name outside the five | `unknown-omission` | warning |

Declaring `spacing` or `rounded` in `omitted` suppresses the
`missing-sections` info for that section. Declaring `typography` suppresses the
`missing-typography` **warning**. It is the same substitution as for `spacing`
and `rounded`, but it retires a warning rather than an info: an unexplained gap
becomes a recorded decision. A file that genuinely does not specify type
therefore has a clean way to say so, and there is no linter pressure to invent
a scale. Verified on two files identical but for the `omitted` block, each
defining `colors`, `spacing` and `rounded` and no `typography`. Without it:

```text
{
  "severity": "warning",
  "path": "typography",
  "message": "No typography tokens defined. Agents will use default font choices, reducing your control over the design system's typographic identity.",
  "rule": "missing-typography"
}
```

With `omitted: [typography]` added, that finding is replaced by:

```text
{
  "severity": "info",
  "path": "omitted.typography",
  "message": "typography intentionally omitted — no typography tokens will be validated",
  "rule": "declared-omission"
}
```

The run's `summary` goes from `{"errors": 0, "warnings": 1, "infos": 1}` to
`{"errors": 0, "warnings": 0, "infos": 2}`. The difference is load-bearing
under `scripts/lint --strict`, which exits 1 on the first file and 0 on the
second.

Verified pair. **Without** `omitted`, a colors-plus-typography file reports:

```text
{
  "findings": [
    {
      "severity": "info",
      "message": "Design system defines 4 colors, 1 typography scale.",
      "rule": "token-summary"
    },
    {
      "severity": "info",
      "path": "spacing",
      "message": "No 'spacing' section defined. Layout spacing will fall back to agent defaults.",
      "rule": "missing-sections"
    },
    {
      "severity": "info",
      "path": "rounded",
      "message": "No 'rounded' section defined. Corner rounding will fall back to agent defaults.",
      "rule": "missing-sections"
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 0,
    "infos": 3
  }
}
```

**With** the `omitted` block from §7.2 added to the same file:

```text
{
  "findings": [
    {
      "severity": "info",
      "message": "Design system defines 4 colors, 1 typography scale.",
      "rule": "token-summary"
    },
    {
      "severity": "info",
      "path": "omitted.components",
      "message": "components intentionally omitted — no components tokens will be validated",
      "rule": "declared-omission"
    },
    {
      "severity": "info",
      "path": "omitted.rounded",
      "message": "rounded intentionally omitted — no rounded tokens will be validated",
      "rule": "declared-omission"
    },
    {
      "severity": "info",
      "path": "omitted.spacing",
      "message": "spacing intentionally omitted — no spacing tokens will be validated",
      "rule": "declared-omission"
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 0,
    "infos": 4
  }
}
```

The absence changed from "the agent will guess" to "the author decided".

Do not declare a section you actually populated. Verified message:

```text
{
  "severity": "warning",
  "path": "omitted",
  "message": "components listed in omitted but components tokens are defined — omitted declaration has no effect",
  "rule": "redundant-omission"
}
```

---

## 8. The body: eight sections

### 8.1 Canonical order

```
Overview
Colors
Typography
Layout
Elevation & Depth
Shapes
Components
Do's and Don'ts
```

### 8.2 The three aliases

| Alias | Resolves to |
| :--- | :--- |
| `Brand & Style` | `Overview` |
| `Layout & Spacing` | `Layout` |
| `Elevation` | `Elevation & Depth` |

Aliases are resolved before the order check, and findings report the
**canonical** name. Verified: a file with `## Elevation` before
`## Layout & Spacing` reported
`Section 'Elevation & Depth' appears before 'Layout', which is out of order.`

There are exactly three aliases. `Palette`, `Type`, `Spacing`, `Motion`,
`Tokens` and the like are not recognised.

### 8.3 What the parser sees

**Only `##` (H2) headings are collected.** An `#` (H1) or `###` (H3) heading is
invisible to the section machinery. Verified: a file with `# Typography`
before `# Colors` produced zero findings; changing them to `##` produced the
order warning.

Consequence: a `### Colors` subsection inside `## Typography` is harmless, and
an H1 document title is harmless.

### 8.4 What the linter checks — and what it does not

| Claim | True? |
| :--- | :--- |
| The linter checks the ORDER of recognised H2s | yes — rule `section-order`, warning |
| The linter checks that all eight sections are PRESENT | **no. There is no such rule.** |
| Extra, unrecognised H2s cause a finding | no — they are filtered out and cost nothing |
| Every out-of-order pair is reported | **no — at most one finding per file** |

Presence: the upstream reference example ships seven H2s (no
`Do's and Don'ts`) and lints with zero errors and zero warnings. Writing all
eight is a **house rule of this skill**, adopted because each section carries
knowledge the token schema cannot — not a linter requirement. Do not tell a
user the linter demanded it.

Extra H2s: verified. A file with `## Changelog` between `## Components` and
`## Do's and Don'ts` produced zero findings.

One finding only: the check stops at the first out-of-canonical-order pair.
Verified on a file whose H2s were `Overview, Typography, Colors, Shapes,
Layout` — only the first inversion was reported:

```text
{
  "findings": [
    {
      "severity": "warning",
      "message": "Section 'Typography' appears before 'Colors', which is out of order. Expected order: Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts",
      "rule": "section-order"
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 1,
    "infos": 0
  }
}
```

`Shapes` before `Layout` was also wrong and went unreported. After fixing a
`section-order` finding, lint again — the next inversion appears only then.

### 8.5 The apostrophe trap

`Do's and Don'ts` MUST use the ASCII apostrophe `'` (U+0027). Verified: a
heading written `## Do’s and Don’ts` with typographic apostrophes (U+2019) is
**not recognised** — it is silently filtered out like any unknown heading, and
the section stops participating in the order check. Editors and note-taking
tools substitute U+2019 automatically. Check this heading after any
copy-paste.

---

## 9. What each section is for

The linter cannot judge any of this. These are the contracts the sections
carry.

**Overview** — what this system is for and who reads it. The product or brand,
the audience, the character in one or two sentences, and the constraints that
shaped the rest of the file (dark-first, dense data, print, accessibility
floor). A reader who reads only this section is able to tell whether a
proposed value belongs. Also the right place for provenance: extracted from a
screenshot, lifted from a codebase, authored from a brief.

**Colors** — the meaning of each family, not a list of hexes. Which family is
the accent and what single job it holds; what `surface` versus
`surface-container` is for; which pairings are legal for text; where the
palette refuses to go. State the contrast floor the system commits to and
whether it is AA or AAA. The token map already gives the values; this section
gives the roles.

**Typography** — which scale step does which job. Family assignment (display
versus text versus mono), the ratio the scale is built on, which weights are
allowed and which are forbidden, measure and line-length limits, and the
script coverage the chosen families actually have. If a family lacks Cyrillic
or Greek coverage, say so here — nothing else will.

**Layout** — the spatial rhythm. The base unit (4px or 8px) and the fact that
everything is a multiple of it, the grid and its breakpoints, container
widths, density, and the gaps between items. Gaps have no token, so this is
the only record of them.

**Elevation & Depth** — the depth ladder. How many levels exist, what each
means semantically (resting, raised, floating, modal, overlay), and how depth
is expressed: shadow, surface tint, border, or nothing at all. The schema has
no elevation token, so a system that uses shadow and does not write this
section has not specified its shadows anywhere.

**Shapes** — the geometry vocabulary. Which radius belongs to which surface
class and why they differ (a chip is not a card is not a modal), whether the
system uses borders and at what widths, and the shapes that are deliberately
excluded (fully round buttons, cut corners). A single radius reused everywhere
is a finding in `anti-slop.md`, not in the linter.

**Components** — everything about a component that the eight sub-tokens cannot
say. Anatomy and required parts, the state matrix (hover, focus-visible,
active, disabled, loading), size variants, content rules (label length, icon
placement), and composition rules. The frontmatter gives one resting
appearance per component; this section gives its behaviour.

**Do's and Don'ts** — enforceable rules specific to THIS system. Each entry
names a concrete thing to do or not do, in terms of this file's own tokens:
which pairings are banned, where the accent may not appear, which combinations
break the rhythm. Generic design advice that would be true of any product is
the standard failure mode here; it makes the section unfalsifiable and
useless. If an entry would read identically in a different DESIGN.md, delete
it.

---

## 10. A complete, verified file

Frontmatter and body together. This file was linted as shown below it.

```yaml
---
version: alpha
name: Ledger Console
description: Internal accounting console, dense tables, light-first.
colors:
  primary: "#1B4F9C"
  on-primary: "#FFFFFF"
  primary-container: "#D6E2F7"
  on-primary-container: "#0A2A5B"
  surface: "#FBFCFD"
  surface-container: "#F1F4F7"
  on-surface: "#101418"
  on-surface-variant: "#495057"
  outline: "#8A9099"
  error: "#9B1C1C"
  on-error: "#FFFFFF"
typography:
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0em
  label-lg:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 600
    lineHeight: 20px
    letterSpacing: 0.01em
    fontFeature: "'tnum' 1"
rounded:
  sm: 4px
  md: 8px
  lg: 16px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm} {spacing.md}"
    height: 40px
  table-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    padding: "{spacing.xs} {spacing.sm}"
---
```

Body, eight H2s in canonical order (prose elided here; in a real file each
section carries the content described in §9):

```markdown
## Overview
## Colors
## Typography
## Layout
## Elevation & Depth
## Shapes
## Components
## Do's and Don'ts
```

Lint result, verbatim, exit code 0:

```text
{
  "findings": [
    {
      "severity": "info",
      "message": "Design system defines 11 colors, 2 typography scales, 3 rounding levels, 4 spacing tokens, 2 components.",
      "rule": "token-summary"
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 0,
    "infos": 1
  }
}
```

Why this file is quiet: all five token maps are populated, so `missing-sections`
and `missing-typography` stay silent; `primary` exists, so `missing-primary`
stays silent; every color name sits in an MD3 baseline family or is
referenced by a component, so `orphaned-tokens` stays silent; both components
pair a background with an `on-` foreground that clears 4.5:1, so
`contrast-ratio` stays silent; the H2s are in canonical order. Note it declares
no `omitted` — nothing is missing, and declaring an omission for a populated
section would raise `redundant-omission` (§7.4).

---

## 11. Verified traps, in one table

| Trap | Symptom | Fix |
| :--- | :--- | :--- |
| Missing closing `---` | `No YAML content found.` warning, zero tokens, exit 0 | close the frontmatter fence |
| Unquoted `#RRGGBB` | **error**: `'null' is not a valid color.` | quote every hex value |
| Unquoted `{ref}` | parsed as a YAML map; no rule fires at all | quote every reference |
| Unitless value in a Dimension slot | token silently dropped, no finding | add `px` / `rem` / `em` |
| `pt`, `%`, `vh` under `typography` or `rounded` | **error**: `has an invalid unit` | use `px` / `rem` / `em` |
| `pt`, `%`, `vh` under `spacing`, or on a component | accepted silently, exported verbatim | use `px` / `rem` / `em`; no rule checks here (§3.2) |
| Bad reference in `colors`/`spacing`/… | silently dropped, no finding | compare `token-summary` counts to what you wrote |
| Bad reference in a component | **error** `broken-ref` | fix the path; only 2 segments resolve |
| `{typography.x.fontSize}` | **error** `broken-ref` | reference whole tokens only |
| `elevation` / `borderColor` / `gap` in a component | warning `broken-ref` | move it to the prose body (§6.1) |
| Poetic color names plus any component | warning `orphaned-tokens` per name | use MD3 families or reference the token |
| Typographic apostrophe in `Do’s and Don’ts` | heading silently ignored | use ASCII `'` |
| `#` or `###` for a section heading | invisible to `section-order` | use `##` |
| `omitted: [layout]` | warning `unknown-omission` | only `colors typography spacing rounded components` |
| `omitted` naming a populated section | warning `redundant-omission` | remove it, or remove the tokens |
| One `section-order` finding fixed, file still wrong | only the first pair is reported | lint again after every fix |

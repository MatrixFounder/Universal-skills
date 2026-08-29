# DESIGN.md — linter rules

Complete rule reference for `@google/design.md@0.4.0 lint`. For every rule:
what fires it, the verbatim message it prints, and the remedy.

Every message and every fenced output block in this file was produced by
running the linter on a real file on 2026-08-28. Nothing here is paraphrased
and nothing is reconstructed from memory. Where a claim is about the
implementation rather than about observed output, it is marked as such.

Companion references: `spec-anatomy.md` (the schema the rules police),
`export-formats.md` (`export` / `diff`), `extraction.md` (how to decide what
goes in the file), `anti-slop.md` (quality rules the linter does not check).

Invocation used throughout:

```
cd /tmp && npx --yes @google/design.md@0.4.0 lint <ABSOLUTE-PATH>
```

`cd /tmp` first: a workspace elsewhere shadows the bin name. Pass an absolute
path. The first `npx` run takes about 30 seconds while the package is fetched.

---

## 1. Fast lookup — thirteen rule ids, fourteen rows

Resolve a finding without reading the rest of this file. `severity` is the
severity the rule emits; only `error` affects the exit code (§3).

| Rule id | Severity | One-line remedy | §  |
| :--- | :--- | :--- | :--- |
| `broken-ref` | error | Define the token the reference names, or repoint `{path.to.token}` at a path that exists. | §5 |
| `broken-ref` | warning | Rename the component key to one of the eight valid sub-tokens, or move the idea into the prose body. | §6 |
| `missing-primary` | warning | Add a `primary` key under `colors`, or rename the accent token to `primary`. | §7 |
| `contrast-ratio` | warning | Route 1: change one of the two colors until the pair reaches 4.5:1. Routes 2 and 3: keep the measured hex, leave the warning standing, explain it. | §8 |
| `orphaned-tokens` | warning | Reference the token from a component, or rename it into the MD3 family vocabulary. | §9 |
| `token-summary` | info | No action. Read the counts back and confirm they match what you wrote. | §10 |
| `missing-sections` | info | Define `spacing` / `rounded`, or declare the name under `omitted`. | §11 |
| `missing-typography` | warning | Add at least one `typography` scale. | §12 |
| `section-order` | warning | Reorder the body `##` headings into canonical order, then lint again. | §13 |
| `unknown-key` | warning | Rename the key to the spelling the message suggests. | §14 |
| `token-like-ignored` | warning | Move those values under a recognized section; `export` ignores the key as written. | §15 |
| `declared-omission` | info | No action. This is `omitted` working as intended. | §16 |
| `redundant-omission` | warning | Remove the name from `omitted`, or remove the tokens it still defines. | §17 |
| `unknown-omission` | warning | Use one of the five valid section names under `omitted`. | §18 |

Thirteen distinct ids, fourteen rows: `broken-ref` occupies two of them
(§2). A finding with **no** `rule` key at all comes from the parser or from the
model builder, before any rule runs; the model's are **errors** and they do move
the exit code — see §19.

---

## 2. Eleven descriptors, thirteen ids, fourteen rows

The rule registry holds **eleven** rule descriptors. Lint output carries
**thirteen** distinct `rule` strings, in **fourteen** distinct
(`rule`, `severity`) combinations — the fourteen rows of §1. The numbers
diverge for two independent reasons, and both are traps.

**Trap 1 — one descriptor emits three foreign ids.** The descriptor named
`omitted-rules` never writes its own name into output. It emits
`declared-omission`, `redundant-omission`, or `unknown-omission` depending on
what it found. Grepping lint output for the literal string `omitted-rules`
finds nothing, on any file, ever. Do not build a check on that string. Ten
descriptors emit their own name; this one emits three others. Eleven
descriptors, thirteen ids.

**Trap 2 — one descriptor emits at two severities.** `broken-ref` is `error`
for an unresolvable `{reference}` and `warning` for an unrecognized component
sub-token. Same `rule` value, different `severity`, different defect,
different fix. This adds no new id — it splits one id across two rows, which
is how thirteen ids become fourteen rows. A finding is identified by the
**pair** (`rule`, `severity`), not by `rule` alone.

Registry order, with the ids each descriptor can emit:

| # | Descriptor | Emits | Severity |
| :--- | :--- | :--- | :--- |
| 1 | `broken-ref` | `broken-ref` | error **and** warning |
| 2 | `missing-primary` | `missing-primary` | warning |
| 3 | `contrast-ratio` | `contrast-ratio` | warning |
| 4 | `orphaned-tokens` | `orphaned-tokens` | warning |
| 5 | `token-summary` | `token-summary` | info |
| 6 | `missing-sections` | `missing-sections` | info |
| 7 | `missing-typography` | `missing-typography` | warning |
| 8 | `section-order` | `section-order` | warning |
| 9 | `unknown-key` | `unknown-key` | warning |
| 10 | `token-like-ignored` | `token-like-ignored` | warning |
| 11 | `omitted-rules` | `declared-omission` | info |
| 11 | `omitted-rules` | `redundant-omission` | warning |
| 11 | `omitted-rules` | `unknown-omission` | warning |

There is no severity configuration and no rule-disable mechanism in
`0.4.0`. Every rule runs on every lint, at the severity listed.

---

## 3. Severity versus exit code — "passes" is not "is good"

**Only errors change the exit code.** Warnings and infos do not.

| Condition | Exit |
| :--- | :--- |
| `summary.errors == 0` | 0 |
| `summary.errors > 0` | 1 |
| file unreadable or missing | 2 |

A file with twelve warnings and zero errors exits 0. A CI gate written as
`design.md lint file || fail` accepts it. That file can have no `primary`
color, no typography, a palette nothing references, a body whose sections are
out of order, and a misspelled top-level key that `export` silently drops —
and still "pass".

Exactly one rule produces errors: `broken-ref`, and only in its
unresolvable-reference variant. Everything else in the registry is advisory to
the exit code.

Errors are not confined to the registry, though. Before any rule runs, the
model builder validates every token *value* and emits its own findings — all
at `error`, all with **no** `rule` id (§19.2). A file can therefore exit 1 with
no `broken-ref` anywhere in its output. Do not read "exit 1" as "broken
reference".

Two consequences an agent MUST internalise:

1. **Never report "the file lints clean" on the basis of the exit code.**
   Report the `summary` triple. `{"errors": 0, "warnings": 6, "infos": 1}` is
   not clean.
2. **Treat warnings as the real signal.** The error class covers a narrow band
   of syntactic defects — unresolvable component references and unparseable
   token values. The warning class covers every substantive complaint the tool
   knows how to make.

The skill's wrapper closes this gap with `--strict`, which fails on warnings
too (§22). Use it for anything gate-shaped.

---

## 4. The shape of a finding, and the order findings arrive in

A finding is a JSON object with up to four keys:

| Key | Presence | Meaning |
| :--- | :--- | :--- |
| `severity` | always | `error` \| `warning` \| `info` |
| `message` | always | English prose, one line |
| `rule` | usually | rule id; **absent** on parser- and model-level findings (§19) |
| `path` | sometimes | dotted location, e.g. `components.button-primary` |

`path` is absent on findings that are about the file as a whole rather than a
location in it — `token-summary` and `section-order` both omit it.

**Findings are emitted in rule-registry order, not document order.** Each rule
runs in turn and appends its findings. A `section-order` warning about a
heading on line 76 therefore appears *after* the `token-summary` info about
the frontmatter, because `section-order` is rule 8 and `token-summary` is rule
5. Verified in §20: the `info` sits fourth in a list of eight, between two
warnings.

Rule-registry order describes the rules only. Model-level findings (§19.2) are
prepended to the whole list, ahead of rule 1, so an error about a bad color
value sits above a `broken-ref` error.

Do not sort the findings when quoting them, and do not read the order as a
priority ranking. If severity order is what you want, the skill's wrapper
regroups them (§22).

---

## 5. `broken-ref` — error variant: unresolvable reference

**Default severity:** error. It is the only *rule* that can make the exit code
non-zero. Model-level value errors (§19.2) carry no rule id and can do it too.

**Fires when:** a `{path.to.token}` reference inside a `components.<name>`
sub-token does not resolve to a token defined in the frontmatter.

**Message template:**

```
Reference {rounded.xl} does not resolve to any defined token.
```

`path` is the component: `components.button-primary`.

**Verified output** (from `examples/fixture-broken.md`, whose `rounded` map
defines only `md` while the component asks for `xl`):

```
{
  "severity": "error",
  "path": "components.button-primary",
  "message": "Reference {rounded.xl} does not resolve to any defined token.",
  "rule": "broken-ref"
}
```

**REMEDY.** Either define the token the reference names, or repoint the
reference at a path that exists. Check three things in order:

1. **The section exists.** `{rounded.xl}` needs a `rounded:` map.
2. **The key exists in it.** Keys are case-sensitive and exact; `{rounded.MD}`
   does not find `md`.
3. **The path has exactly two segments.** `{typography.body-md.fontSize}`
   does not resolve — references point at whole tokens, not at properties
   inside them. See `spec-anatomy.md` §on references.

**Honest limit.** This rule only inspects references inside `components`. A
broken reference used as the *value* of a `colors`, `rounded`, or `spacing`
token is dropped silently — no error, no warning, the token simply vanishes
from the map. The only visible trace is a smaller count in `token-summary` (§10). If a
token you wrote is not in the count, look for a bad reference in its value.

---

## 6. `broken-ref` — warning variant: unrecognized component sub-token

**Default severity:** warning. Same rule id as §5.

**Fires when:** a key inside `components.<name>` is not one of the eight
sub-tokens the schema defines. The sub-token set is **closed**:

```
backgroundColor  textColor  typography  rounded  padding  size  height  width
```

**Message template** (the message echoes the whole valid list):

```
'elevation' is not a recognized component sub-token. Valid sub-tokens: backgroundColor, textColor, typography, rounded, padding, size, height, width.
```

`path` includes the offending key: `components.button-primary.elevation`.

**Verified output:**

```
{
  "severity": "warning",
  "path": "components.button-primary.elevation",
  "message": "'elevation' is not a recognized component sub-token. Valid sub-tokens: backgroundColor, textColor, typography, rounded, padding, size, height, width.",
  "rule": "broken-ref"
}
```

**REMEDY.** Rename the key to one of the eight, or delete it. There is no
substitute key for `elevation`, `boxShadow`, `borderColor`, `borderWidth`,
`gap`, `opacity`, or a hover/focus state — the format has no slot for any of
them. What the token schema cannot express belongs in the markdown body, under
`## Elevation & Depth`, `## Shapes`, or `## Components`, as prose. Prose is not
a downgrade: it is where the format expects that information, and it is what
an agent reading the file will act on.

Deleting the key is not data loss if you write the sentence in the body.
Leaving the key is data loss: `export` never emits it, so no consumer will
ever see it.

---

## 7. `missing-primary`

**Default severity:** warning.

**Fires when:** the `colors` map is non-empty and has no key named `primary`.

**Message template:**

```
No 'primary' color defined. The agent will auto-generate key colors, reducing your control over the palette.
```

`path` is `colors`.

**Verified output** (probe file: two colors named `accent` and `surface`):

```
{
  "severity": "warning",
  "path": "colors",
  "message": "No 'primary' color defined. The agent will auto-generate key colors, reducing your control over the palette.",
  "rule": "missing-primary"
}
```

**REMEDY.** Add a `primary` key, or rename the token that already plays that
role. The check is on the literal key name `primary` — `brand`, `accent`,
`main`, and `primary-500` all fail it.

This rule pairs with `orphaned-tokens` (§9): both push a palette toward the
MD3 family vocabulary. Renaming `accent` to `primary` silences this warning
and, if you also carry `on-primary` and `primary-container`, silences three
potential orphan warnings at the same time.

---

## 8. `contrast-ratio`

**Default severity:** warning.

**Fires when:** a component defines **both** `backgroundColor` and `textColor`,
both resolve to real colors, and the WCAG contrast ratio between them is below
**AA 4.5:1**.

**Message template.** The ratio is quoted to two decimal places and both colors
are printed **lowercased**, whatever case they were written in:

```
textColor (#a8b4c0) on backgroundColor (#7a8a99) has contrast ratio 1.68:1, below WCAG AA minimum of 4.5:1.
```

`path` is the component.

**Verified output** (fixture-broken defines `primary: "#7A8A99"` and
`on-primary: "#A8B4C0"` — note the input hexes are uppercase, the message is
not):

```
{
  "severity": "warning",
  "path": "components.button-primary",
  "message": "textColor (#a8b4c0) on backgroundColor (#7a8a99) has contrast ratio 1.68:1, below WCAG AA minimum of 4.5:1.",
  "rule": "contrast-ratio"
}
```

**REMEDY — check the route before you edit a hex.** There are two remedies and
the tool prints only one of them. `scripts/lint` prints `Change one of the two
colors until the pair reaches 4.5:1 (aim for 7:1 on body text); the message
quotes the measured ratio.` That sentence is the wrapper's own text, not
upstream's (§22.3 — the upstream CLI prints findings and no remedy at all), and
it is correct for **Route 1 only**.

| Route | What to do with the failing pair |
| :--- | :--- |
| **Route 1 — an authored system.** The two colors were *chosen*, from a brief or a template. | **Change one of them** until the pair clears 4.5:1, then re-lint. The message gives you the measured ratio, so you know how far you are. Darken the text or lighten the background — do not split the difference, which usually lands on a muddy mid-tone that fails against everything else in the file. |
| **Routes 2 and 3 — the file documents an existing product.** The two colors were *measured* from a screenshot or *harvested* from a codebase. | **Keep both hexes unchanged.** Leave the warning standing and explain it: name the pair and its measured ratio in the hand-back, and add a `**Don't**` entry under `## Do's and Don'ts` naming the two tokens. `extraction.md` B.6 step 7 is the governing text. |

The asymmetry is not stylistic. On Route 1 nothing is being recorded, so a
failing pair is a design defect and editing it is the fix. On Routes 2 and 3 the
pair fails *in the product*: editing the hex clears the warning without fixing
anything, converts a measurement into an invention, and hides a real
accessibility defect from the only people who could correct it. A Route 2 or
Route 3 file that reports zero `contrast-ratio` warnings because a hex was
edited is worse than one that carries the warning with a reason — on those two
routes the finding is the deliverable, not the obstacle.

**Honest limits — this rule checks far less than it appears to.**

- It only compares pairs **inside one component**. A `colors` map full of
  unreadable combinations produces no finding at all unless a component wires
  two of them together.
- A component with only `backgroundColor`, or only `textColor`, is never
  checked.
- Non-text tokens (`outline`, dividers, icon colors) are never checked, and
  WCAG's 3:1 non-text threshold is not implemented.
- The threshold is AA 4.5:1 flat. There is no AAA (7:1) check and no
  large-text exemption (3:1).

`scripts/check-contrast` exists because of this gap: it walks all
text-on-surface pairs and reports AAA as well. A file that passes
`contrast-ratio` has not been contrast-checked in any meaningful sense.

---

## 9. `orphaned-tokens` — the trap

**Default severity:** warning. One finding per offending color token.

This rule punishes hand-picked color names. It is the single most common
reason a carefully written DESIGN.md comes back with a column of warnings, and
the reason the skill's templates use Material Design 3 token names throughout.

**Message template:**

```
'ink' is defined but never referenced by any component.
```

`path` is the token: `colors.ink`.

### 9.1 The algorithm

Per the implementation (`linter/rules/orphaned-tokens.ts`):

1. **Early return.** If `components` is empty or absent, return no findings.
   The rest of the rule never runs.
2. Otherwise, for each token in `colors`, emit a warning **unless** one of
   these holds:
   - the token is referenced by some component; **or**
   - the token's *family* is referenced by some component; **or**
   - the token's *family* is in the MD3 baseline set.

**`colorFamily()` normalization**, applied to the token name in this order:

1. Strip a leading `on-`.
2. Strip a leading `inverse-`.
3. Strip a leading `on-` again.
4. Strip a trailing `-container` and anything after it.
5. Strip a trailing `-fixed` and anything after it.
6. Strip a trailing `-dim`, `-bright`, `-tint`, or `-variant`.

**MD3 baseline families, never flagged:**

```
primary  secondary  tertiary  error  surface  background  outline
```

### 9.2 Verified: what survives normalization

Probe file — six colors, one component referencing `ink` and
`on-inverse-ink-container`, no `primary` token:

```
{
  "findings": [
    {
      "severity": "warning",
      "path": "colors",
      "message": "No 'primary' color defined. The agent will auto-generate key colors, reducing your control over the palette.",
      "rule": "missing-primary"
    },
    {
      "severity": "warning",
      "path": "colors.warm-grey-300",
      "message": "'warm-grey-300' is defined but never referenced by any component.",
      "rule": "orphaned-tokens"
    },
    {
      "severity": "info",
      "message": "Design system defines 6 colors, 1 typography scale, 1 rounding level, 1 spacing token, 1 component.",
      "rule": "token-summary"
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 2,
    "infos": 1
  }
}
```

Six colors were defined. Exactly one was flagged. Why each of the other five
survived:

| Token | Family after normalization | Why it is not flagged |
| :--- | :--- | :--- |
| `ink` | `ink` | referenced directly by the component |
| `on-inverse-ink-container` | `ink` | referenced directly; also family `ink` |
| `ink-dim` | `ink` | family `ink` is referenced |
| `ink-fixed-variant` | `ink` | family `ink` is referenced |
| `on-surface-variant` | `surface` | family is in the baseline set |
| `warm-grey-300` | `warm-grey-300` | **flagged** — no strip applies, not baseline, not referenced |

`warm-grey-300` is the shape of a normal, sane, industry-standard palette
name. It generates a warning. That is the trap.

### 9.3 Verified: no components means no rule

Same poetic names — `ink`, `paper`, `brand` — with the `components` map
removed entirely:

```
{
  "findings": [
    {
      "severity": "warning",
      "path": "colors",
      "message": "No 'primary' color defined. The agent will auto-generate key colors, reducing your control over the palette.",
      "rule": "missing-primary"
    },
    {
      "severity": "info",
      "message": "Design system defines 3 colors, 1 typography scale, 1 rounding level, 1 spacing token.",
      "rule": "token-summary"
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 1,
    "infos": 1
  }
}
```

Zero orphan warnings. The early return fired.

This produces a perverse incentive worth naming out loud: **deleting the
`components` map silences every orphan warning in the file.** Do not do that.
A DESIGN.md without components is a token dump; the warnings are the price of
the file being useful. If you see a file with a large palette and no
components, the absence of orphan warnings tells you nothing about the
palette's quality.

### 9.4 REMEDY

Three fixes, in order of preference:

1. **Reference the token from a component.** This is the fix the rule is
   actually asking for. If a color has a job, some component uses it; if no
   component uses it, ask whether the color has a job.
2. **Rename it into the MD3 family vocabulary.** A token whose family is
   `primary`, `secondary`, `tertiary`, `error`, `surface`, `background`, or
   `outline` is never flagged regardless of what references it. The full
   vocabulary the normalization understands:

   ```
   primary  on-primary  primary-container  on-primary-container
   inverse-primary
   secondary  on-secondary  secondary-container  on-secondary-container
   tertiary   on-tertiary   tertiary-container   on-tertiary-container
   error      on-error      error-container      on-error-container
   surface  surface-dim  surface-bright  surface-variant  surface-tint
   surface-container  surface-container-lowest  surface-container-low
   surface-container-high  surface-container-highest
   on-surface  on-surface-variant  inverse-surface  inverse-on-surface
   background  on-background
   outline  outline-variant
   primary-fixed  primary-fixed-dim  on-primary-fixed  on-primary-fixed-variant
   ```

   (and the `secondary-` / `tertiary-` forms of the last row).
3. **Delete the token.** A color that no component references and that you
   cannot name in the vocabulary may simply not be part of the system.

**What NOT to do:** do not delete `components` to silence it (§9.3), and do not
invent a component whose only purpose is to touch an unused color. Both trade
a warning for a worse file.

**Design consequence for templates.** Any template in `assets/` that defines
components MUST name colors in MD3 families, or accept one warning per name.
This is a real constraint of the format, not a bug to work around. Poetic
palettes (`ink`, `paper`, `clay`, `moss`) are only free in files with no
components.

---

## 10. `token-summary`

**Default severity:** info. Fires on every file that defines any tokens. It is
not a complaint.

**Message template.** Counts for the five categories, in fixed order, with
each noun singularised at count 1, and **categories with a count of zero
dropped from the sentence entirely**:

```
Design system defines 4 colors, 1 typography scale, 1 rounding level, 1 spacing token, 2 components.
```

No `path`.

**Verified variants**, all from real probes:

```
Design system defines 47 colors, 8 typography scales, 6 rounding levels, 8 spacing tokens, 10 components.
Design system defines 5 colors, 2 typography scales, 2 rounding levels, 2 spacing tokens, 2 components.
Design system defines 2 colors, 1 typography scale, 1 rounding level, 1 spacing token.
Design system defines 1 color.
```

The third line has no component count because that file defines none. The
fourth defines one color and nothing else.

**REMEDY.** None — but do not skip it. This line is the **only** feedback the
linter gives about tokens dropped *silently*. Two value defects drop a token
with no finding of any kind:

- an unresolvable `{reference}` as the value of a `colors`, `rounded`, or
  `spacing` token (§5);
- a bare unitless number under `rounded` or `spacing` (`md: 8`), which YAML
  reads as an integer and the model never turns into a dimension. A *quoted*
  unitless string behaves differently by section: `spacing: {sm: "8"}` is
  dropped in silence, `rounded: {sm: "8"}` raises a rule-less error (§19.2).

Verified on a probe writing eight tokens — two colors, three `rounded` entries
and three `spacing` entries, exactly one of each map sound:

```
Design system defines 1 color, 1 typography scale, 1 rounding level, 1 spacing token.
```

Zero errors, zero warnings, exit 0. Five of the eight tokens vanished and this
line is the only trace.

Other value defects are **not** silent — they raise a rule-less error (§19.2).
An unquoted hex is the one to learn: `primary: #1B4D3E` is a YAML comment, so
the value parses as null and the linter says

```
'null' is not a valid color. Expected a CSS color value (e.g., #ffffff, rgb(0 0 0), oklch(0.5 0.2 240)).
```

Read the counts back against the file every time. If you wrote nine colors and
the summary says eight, one of them did not reach the map. See
`spec-anatomy.md` for the quoting rules that cause this.

---

## 11. `missing-sections`

**Default severity:** info.

**Fires when:** the `spacing` map or the `rounded` map is empty or absent,
**and** `colors` is non-empty, **and** that section name is not declared under
`omitted`. One finding per missing section, so both can fire on one file.

**Message templates:**

```
No 'spacing' section defined. Layout spacing will fall back to agent defaults.
No 'rounded' section defined. Corner rounding will fall back to agent defaults.
```

`path` is the section name.

**Verified output** (probe: one color, nothing else):

```
{
  "findings": [
    {
      "severity": "info",
      "message": "Design system defines 1 color.",
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
    },
    {
      "severity": "warning",
      "path": "typography",
      "message": "No typography tokens defined. Agents will use default font choices, reducing your control over the design system's typographic identity.",
      "rule": "missing-typography"
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 1,
    "infos": 3
  }
}
```

**REMEDY.** Two legitimate answers, and you MUST pick between them
deliberately:

1. **Define the section.** Preferred when you know the values. Even two steps
   (`sm: 8px`, `md: 16px`) is a real answer.
2. **Declare it under `omitted`.** Correct when you genuinely do not know —
   extracting from a screenshot that shows no rounded corners, for example.
   The declaration converts this info into a `declared-omission` info (§16),
   which reads as a decision rather than as an absence.

Declaring the name under `omitted` suppresses this rule for that section.
Guessing values to make the message go away is the wrong fix: `omitted` exists
in the format precisely so that "unknown" is expressible.

Note the severity: this is `info`, not `warning`. It will not fail even a
`--strict` gate. It is easy to miss in a long report.

---

## 12. `missing-typography`

**Default severity:** warning.

**Fires when:** `colors` is non-empty and `typography` is empty or absent.

**Message template:**

```
No typography tokens defined. Agents will use default font choices, reducing your control over the design system's typographic identity.
```

`path` is `typography`.

**Verified output:** see the fourth finding in §11.

**REMEDY.** Add at least one `typography` scale. A file that specifies color
and not type has answered the easier half of the question and left the half
that does more work on the page. One honest role is better than none:

```yaml
typography:
  body-md:
    fontFamily: "Inter"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
```

If the font family genuinely is not decided — extracting from a screenshot,
where family names are not recoverable — declare `typography` under `omitted`
rather than inventing a family. `omitted` suppresses this rule the same way it
suppresses §11.

---

## 13. `section-order`

**Default severity:** warning.

**Fires when:** two body headings appear in an order that contradicts the
canonical section order.

**Canonical order:**

```
Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts
```

Three aliases resolve: `Brand & Style` → Overview, `Layout & Spacing` →
Layout, `Elevation` → Elevation & Depth.

**Message template.** The message names the offending pair and then repeats
the whole canonical order:

```
Section 'Typography' appears before 'Colors', which is out of order. Expected order: Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts
```

No `path`.

**Verified output:**

```
{
  "severity": "warning",
  "message": "Section 'Typography' appears before 'Colors', which is out of order. Expected order: Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts",
  "rule": "section-order"
}
```

**REMEDY.** Move the sections into canonical order — then **lint again**.

**Three limits that will bite you.**

1. **At most one finding per run.** The rule stops at the first out-of-order
   pair. A body with four inversions reports one. Fixing it and re-linting is
   the only way to find the next. Never read "one `section-order` warning" as
   "one ordering problem".
2. **Only `##` headings are collected.** A section written as `#` or `###` is
   invisible to this rule. It is not checked, and it does not count as
   present.
3. **Unknown headings cost nothing.** A heading that resolves to no canonical
   name is filtered out before the comparison. Extra `##` sections
   (`## Motion`, `## Voice`, `## Accessibility`) are free and do not disturb
   the ordering check.

**Honest limit — there is no completeness rule.** Nothing requires all eight
sections to be present. The upstream reference example ships seven `##`
headings (no `Do's and Don'ts`) and lints at 0 errors / 0 warnings. Requiring
all eight is a house rule of this skill, enforced by review and by the
templates in `assets/`, not by the linter. Do not claim the linter checks it.

One typographic trap: the canonical name uses the ASCII apostrophe in `Do's
and Don'ts`. A heading written with the typographic apostrophe (`Do's` with
U+2019) resolves to nothing and is silently filtered out — no finding, and the
section does not count as present.

---

## 14. `unknown-key`

**Default severity:** warning.

**Fires when:** a top-level frontmatter key is not in the schema **and** is
within Levenshtein distance 2 of one that is. It is a spell-checker, not a
whitelist.

Schema keys:

```
version  name  description  omitted  colors  typography  rounded  spacing  components
```

**Message template:**

```
Unknown key "descriptoin" — did you mean "description"?
```

The dash is an em dash (U+2014). `path` is the offending key.

**Verified output:**

```
{
  "severity": "warning",
  "path": "descriptoin",
  "message": "Unknown key \"descriptoin\" — did you mean \"description\"?",
  "rule": "unknown-key"
}
```

**REMEDY.** Rename the key to the spelling the message suggests. The common
real cases are `colours` → `colors`, `descriptoin` → `description`,
`typograpy` → `typography`, `spacings` → `spacing`.

**Honest limit — distant custom keys are silent.** The schema is deliberately
extensible: unknown top-level keys are allowed. A key more than two edits away
from every schema key produces **no** `unknown-key` finding. `radii`,
`elevation`, `shadows`, `breakpoints`, `motion` all pass this rule without
comment. That silence is not approval — `export` ignores them all. The
companion rule §15 catches the subset of them that look like token maps.

---

## 15. `token-like-ignored`

**Default severity:** warning.

**Fires when:** a top-level unknown key holds an **object** with a token-shaped
leaf somewhere beneath it — a hex or CSS dimension value, or a typography
property name. The search is **recursive through nested plain objects**;
arrays are inert. This is the rule that catches the keys `unknown-key` is too
far away to notice.

**Message template:**

```
"radii" looks like a design-token map but is not a recognized schema key (colors, typography, spacing, rounded, components). It will be silently ignored by export commands. Rename it to a supported key or move its values under a recognized section.
```

`path` is the offending key.

**Verified output:**

```
{
  "severity": "warning",
  "path": "radii",
  "message": "\"radii\" looks like a design-token map but is not a recognized schema key (colors, typography, spacing, rounded, components). It will be silently ignored by export commands. Rename it to a supported key or move its values under a recognized section.",
  "rule": "token-like-ignored"
}
```

**REMEDY.** Move the values under a recognized section. `radii:` becomes
`rounded:`. `shadows:` has no home in the schema at all — delete the map and
describe elevation in the `## Elevation & Depth` prose (§6 makes the same
point about component sub-tokens).

The warning is telling you something concrete about downstream behaviour, not
about style: `export` reads only the five recognized token sections. Values
under any other key never reach a Tailwind config, a DTCG file, or a CSS
variable. They exist only in the YAML.

**Search depth — measured.** The scan descends through nested plain objects
with no depth limit reached in testing; a YAML list stops it. Each row is a
whole frontmatter body under `name: Probe`, linted with
`cd /tmp && npx --yes @google/design.md@0.4.0 lint <ABSOLUTE-PATH>`:

| Frontmatter under the unknown key | Fires | `path` reported |
| :--- | :--- | :--- |
| `radii: {lg: 12px}` | yes | `radii` |
| `meta: {radii: {lg: 12px}}` | yes | `meta` |
| `meta: {a: {b: {radii: {lg: 12px}}}}` | yes | `meta` |
| `meta: {a: {b: {c: {d: {brand: "#ff0044"}}}}}` | yes | `meta` |
| `meta: {a: {b: {display: {fontWeight: 700}}}}` | yes | `meta` |
| `meta: [{radii: {lg: 12px}}]` | no | — |
| `meta: {list: [{group: {brand: "#ff0044"}}]}` | no | — |
| `meta: {sizes: [12px, 16px]}` | no | — |
| `meta: {inner: {note: just prose here}}` | no | — |

Two consequences for an author who takes up §14's extensibility and adds a
custom top-level key. First, depth is not shelter: a token-shaped map four
levels below that key still fires the warning, and `path` names only the
top-level key — `meta`, never `meta.a.b.radii` — so locating the offending leaf
is the reader's work. A custom key is silent only when nothing beneath it looks
like a token. Second, a token map that sits inside a YAML list is never
reached, at any depth; that is a gap in the rule, not a supported way to hide
metadata from it.

**How §14 and §15 divide the work.** They are independent and can both fire on
the same key:

| Key | `unknown-key` | `token-like-ignored` | Why |
| :--- | :--- | :--- | :--- |
| `colours: {...}` | fires | fires | close to `colors` **and** token-shaped |
| `descriptoin: "..."` | fires | silent | close to `description`, but a plain string |
| `radii: {lg: 12px}` | silent | fires | far from every schema key, but token-shaped |
| `internalNotes: "..."` | silent | silent | far, and not token-shaped — legal extension |

Both rows of `fixture-broken.md` are deliberately split this way (§20), so the
two rules can be told apart in the output.

---

## 16. `declared-omission`

**Default severity:** info. Emitted by the `omitted-rules` descriptor. This is
the good case — the file said "I do not specify this" and meant it.

**Fires when:** a section name under `omitted` is one of the five valid names
and that section defines no tokens.

Valid section names, lowercased, exhaustive:

```
colors  typography  spacing  rounded  components
```

**Message template:**

```
components intentionally omitted — no components tokens will be validated
```

The dash is an em dash. `path` is `omitted.<section>`.

**Verified output** (probe declaring `components` with a reason and `spacing`
as a bare string — the array accepts both forms mixed):

```
{
  "findings": [
    {
      "severity": "info",
      "message": "Design system defines 1 color, 1 typography scale, 1 rounding level.",
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
      "path": "omitted.spacing",
      "message": "spacing intentionally omitted — no spacing tokens will be validated",
      "rule": "declared-omission"
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 0,
    "infos": 3
  }
}
```

Note what did *not* fire: `missing-sections` stayed quiet about `spacing`
because it was declared. That is the trade — one info replaces another, and
the file now records a decision instead of a hole.

**REMEDY.** None. Do not remove `omitted` entries to reduce the info count.
The `reason` field costs nothing and is the only place the file explains why
something is unspecified:

```yaml
omitted:
  - section: components
    reason: "No component inventory was visible in the screenshot."
  - spacing
```

---

## 17. `redundant-omission`

**Default severity:** warning. Emitted by the `omitted-rules` descriptor.

**Fires when:** a section is named under `omitted` **and** that section defines
tokens. The file contradicts itself.

**Message template:**

```
spacing listed in omitted but spacing tokens are defined — omitted declaration has no effect
```

`path` is `omitted` (not the section).

**Verified output** (probe declaring `spacing` and `typography` under
`omitted` while defining both):

```
{
  "findings": [
    {
      "severity": "info",
      "message": "Design system defines 1 color, 1 typography scale, 1 rounding level, 1 spacing token.",
      "rule": "token-summary"
    },
    {
      "severity": "warning",
      "path": "omitted",
      "message": "spacing listed in omitted but spacing tokens are defined — omitted declaration has no effect",
      "rule": "redundant-omission"
    },
    {
      "severity": "warning",
      "path": "omitted",
      "message": "typography listed in omitted but typography tokens are defined — omitted declaration has no effect",
      "rule": "redundant-omission"
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 2,
    "infos": 1
  }
}
```

**REMEDY.** Decide which half is true and delete the other. Either remove the
name from `omitted` (the tokens are real), or remove the tokens (the section
really is out of scope). The usual cause is an `omitted` block written early
from a screenshot and never updated after the tokens were filled in — treat
this warning as a staleness alarm on `omitted`.

---

## 18. `unknown-omission`

**Default severity:** warning. Emitted by the `omitted-rules` descriptor.

**Fires when:** a name under `omitted` is not one of the five valid section
names. Matching is on the lowercased name.

**Message template:**

```
unknown section name 'Elevation' in omitted key
```

Lowercase first word, and the name is echoed in its original case. `path` is
`omitted`.

**Verified output:**

```
{
  "severity": "warning",
  "path": "omitted",
  "message": "unknown section name 'Elevation' in omitted key",
  "rule": "unknown-omission"
}
```

**REMEDY.** Use one of the five valid names, or delete the entry.

`omitted` names **token sections**, not body sections. This is the single most
common honest mistake in hand-written DESIGN.md files: the body has eight
sections, so `omitted: [Elevation]` or `omitted: [layout]` looks right. It is
not. There is no `elevation` token section and no `layout` token section — the
five names are `colors`, `typography`, `spacing`, `rounded`, `components`, and
nothing else.

If you want to record that the system deliberately has no elevation, write it
as a sentence under `## Elevation & Depth`. That is where the format keeps it.

---

## 19. Findings with no rule id

Two stages run before the rule registry. The **parser** finds the YAML and the
`##` headings. The **model builder** validates every token value. Both emit
findings, and neither writes a `rule` key. Code that does
`finding.rule.startsWith(...)` crashes on them.

The two stages differ in severity, and the difference decides the exit code:
parser findings are warnings, model findings are errors.

### 19.1 Parser findings — warnings

**Verified output** (a file with no frontmatter at all):

```
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

Exit code 0. Note carefully what that means: a file with **zero tokens** and
**no design system in it whatsoever** exits 0. This is the sharpest form of
the point in §3.

**REMEDY.** Add a frontmatter block delimited by `---`, containing at least
`name:`. The same message appears when the opening `---` has no closing `---`
— the block is then invisible and every token in it silently disappears. If
`token-summary` is missing from a report entirely, this is why.

A YAML syntax error inside the block produces a similar rule-less finding
quoting the line and column. Fix the syntax at the quoted position and rerun.

### 19.2 Model findings — errors

The model builder resolves every token value to a color, a dimension, or a
typography property, and rejects the ones it cannot. Its findings carry
`severity: error` and a `path`, never a `rule`. They are **prepended** to the
rule findings, and they count toward `summary.errors` — so they move the exit
code without any rule having fired.

**Verified output** (`colors.primary` set to the string `notacolor`):

```
{
  "findings": [
    {
      "severity": "error",
      "path": "colors.primary",
      "message": "'notacolor' is not a valid color. Expected a CSS color value (e.g., #ffffff, rgb(0 0 0), oklch(0.5 0.2 240))."
    },
    {
      "severity": "warning",
      "path": "colors",
      "message": "No 'primary' color defined. The agent will auto-generate key colors, reducing your control over the palette.",
      "rule": "missing-primary"
    },
    {
      "severity": "info",
      "message": "Design system defines 1 color, 1 typography scale, 1 rounding level, 1 spacing token.",
      "rule": "token-summary"
    }
  ],
  "summary": {
    "errors": 1,
    "warnings": 1,
    "infos": 1
  }
}
```

Exit code 1. Note the cascade: the rejected token never reaches the `colors`
map, so `missing-primary` fires on top and `token-summary` counts one color
where two were written. One typo, three findings, only one of which names the
cause.

The messages, all at `error`, all rule-less, each quoted from a real run:

| `path` | Message |
| :--- | :--- |
| `colors.<token>` | `'notacolor' is not a valid color. Expected a CSS color value (e.g., #ffffff, rgb(0 0 0), oklch(0.5 0.2 240)).` |
| `rounded.<token>` | `'4' is not a valid dimension.` |
| `rounded.<token>` | `'12pt' has an invalid unit 'pt'. Only px, rem, and em are allowed.` |
| `typography.<t>.fontFamily` | `'#336699' appears to be a color, not a valid font family.` |
| `typography.<t>.fontWeight` | `'semibold' is not a valid font weight. Expected a number.` |
| `typography.<t>.fontSize` | `'16pt' has an invalid unit 'pt'. Only px, rem, and em are allowed.` |

**`spacing` has no entry in that table, and that is the asymmetry to remember.**
A bad `rounded` dimension is an error; the same value under `spacing` is
dropped without a word (§10). Do not infer from a clean run that the `spacing`
map contains what you wrote — read the count.

**REMEDY.** Fix the value; the message quotes the offending literal and `path`
locates it exactly. One caution about the wrapper: these findings have no rule
id, so they fall through to its generic no-rule remedy, which talks about
frontmatter syntax and is wrong here. Read the upstream message, not the
remedy line.

### 19.3 Body `yaml` fences are a second token source

The parser collects fenced code blocks tagged `yaml` or `yml` **anywhere in
the body** and merges them into the token set alongside the frontmatter.

This is not in the published format spec. `design.md spec` describes a
DESIGN.md as "two parts: An optional YAML frontmatter, and a markdown body",
and calls the body "human-readable design rationale and guidance". Only the
parser's own error message admits the second source: "Expected frontmatter
(---) or fenced yaml code blocks." The spec itself illustrates the schema with
```` ```yaml ```` fences, so an author who documents their own tokens in the
same style walks straight into this.

Two outcomes, both verified.

**Silent merge, when the keys do not collide.** A frontmatter that defines no
`spacing` at all, plus a prose fence tagged `yaml` illustrating two spacing
steps:

```
{
  "findings": [
    {
      "severity": "info",
      "message": "Design system defines 2 colors, 1 typography scale, 1 rounding level, 2 spacing tokens.",
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

The two spacing tokens in that count came out of a code fence in the prose.
`missing-sections` stayed quiet because, as far as the linter is concerned,
the section exists.

**Hard stop, when a key collides.** If one top-level key appears in both the
frontmatter and a body fence, parsing fails and **no rule runs at all**. Here
the frontmatter declares `omitted: [components]` and the prose shows a second
`omitted:` example:

```
{
  "findings": [
    {
      "severity": "warning",
      "message": "Section 'omitted' is defined in both frontmatter and code block 1."
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 1,
    "infos": 0
  }
}
```

Exit code 0. One rule-less warning, no `token-summary`, no `declared-omission`,
no contrast check, no reference check — the entire frontmatter went
unvalidated and the exit code says the file passed. A `PASS` on this file
certifies nothing: not one token was inspected. Numbering counts body fences
only and is 1-based, so `code block 1` is the first `yaml` fence in the prose,
not the frontmatter.

**REMEDY.** Tag illustrative YAML as ```` ```text ````. Verified — the same file
with that one fence retagged:

```
{
  "findings": [
    {
      "severity": "info",
      "message": "Design system defines 2 colors, 1 typography scale, 1 rounding level, 1 spacing token.",
      "rule": "token-summary"
    },
    {
      "severity": "info",
      "path": "omitted.components",
      "message": "components intentionally omitted — no components tokens will be validated",
      "rule": "declared-omission"
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 0,
    "infos": 2
  }
}
```

Both findings came back. Treat this as a rule when authoring: only the
frontmatter carries tokens, and a fence tagged `yaml` or `yml` in the body is
not an illustration, it is input. The four templates in `assets/` carry no
body `yaml` fence, and adding one to them would be a regression.

---

## 20. Verbatim output: `examples/fixture-broken.md`

The known-bad control file. Seven defects are planted; the linter emits eight
findings (the eighth being `token-summary`, which is not a defect).

> **Path convention for every capture in sections 20-22.** `npx` is run from
> `/tmp`, so it needs an absolute path. In the captures below that absolute path
> is elided to `<SKILL>`, which stands for this skill's own directory. Nothing
> else in any capture is edited: the findings, their order, the wording, the
> counts and the exit codes are exactly what the tool printed. Expand `<SKILL>`
> to your own checkout to reproduce them.

Command:

```
cd /tmp && npx --yes @google/design.md@0.4.0 lint \
  <SKILL>/examples/fixture-broken.md
```

Exit code: **1**.

Output, verbatim and in emitted order:

```
{
  "findings": [
    {
      "severity": "error",
      "path": "components.button-primary",
      "message": "Reference {rounded.xl} does not resolve to any defined token.",
      "rule": "broken-ref"
    },
    {
      "severity": "warning",
      "path": "components.button-primary.elevation",
      "message": "'elevation' is not a recognized component sub-token. Valid sub-tokens: backgroundColor, textColor, typography, rounded, padding, size, height, width.",
      "rule": "broken-ref"
    },
    {
      "severity": "warning",
      "path": "components.button-primary",
      "message": "textColor (#a8b4c0) on backgroundColor (#7a8a99) has contrast ratio 1.68:1, below WCAG AA minimum of 4.5:1.",
      "rule": "contrast-ratio"
    },
    {
      "severity": "info",
      "message": "Design system defines 4 colors, 1 typography scale, 1 rounding level, 1 spacing token, 2 components.",
      "rule": "token-summary"
    },
    {
      "severity": "warning",
      "message": "Section 'Typography' appears before 'Colors', which is out of order. Expected order: Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts",
      "rule": "section-order"
    },
    {
      "severity": "warning",
      "path": "descriptoin",
      "message": "Unknown key \"descriptoin\" — did you mean \"description\"?",
      "rule": "unknown-key"
    },
    {
      "severity": "warning",
      "path": "radii",
      "message": "\"radii\" looks like a design-token map but is not a recognized schema key (colors, typography, spacing, rounded, components). It will be silently ignored by export commands. Rename it to a supported key or move its values under a recognized section.",
      "rule": "token-like-ignored"
    },
    {
      "severity": "warning",
      "path": "omitted",
      "message": "unknown section name 'Elevation' in omitted key",
      "rule": "unknown-omission"
    }
  ],
  "summary": {
    "errors": 1,
    "warnings": 6,
    "infos": 1
  }
}
```

### 20.1 Every finding mapped to its planted defect

Emitted position → the line in the fixture that causes it. Note that emitted
order and document order do not agree: the three frontmatter defects on lines
5, 7 and 23 arrive last, in positions 6, 8 and 7.

| # emitted | Rule / severity | Fixture line | The planted defect |
| :--- | :--- | :--- | :--- |
| 1 | `broken-ref` error | 30: `rounded: "{rounded.xl}"` | `rounded` defines only `md` (line 20). `xl` does not exist. |
| 2 | `broken-ref` warning | 31: `elevation: "2dp"` | `elevation` is not one of the eight component sub-tokens. |
| 3 | `contrast-ratio` | 27–28 + 9–10 | `on-primary` `#A8B4C0` on `primary` `#7A8A99` measures 1.68:1, far below 4.5:1. |
| 4 | `token-summary` | frontmatter | Not a defect. Confirms 4 colors, 1 type scale, 1 radius, 1 spacing step, 2 components parsed. |
| 5 | `section-order` | 76 `## Typography` before 82 `## Colors` | The one heading inversion. The rule stops after it. |
| 6 | `unknown-key` | 5: `descriptoin:` | Two letters transposed in `description`; distance 2, so the spell-check fires. Its value is a plain string, so §15 stays quiet. |
| 7 | `token-like-ignored` | 23–24: `radii: {lg: 12px}` | Token-shaped map under a key the schema does not know. Too far from every schema key for §14, so only this rule fires. |
| 8 | `unknown-omission` | 6–7: `omitted: [Elevation]` | `Elevation` is not one of `colors typography spacing rounded components`. |

Four properties of the fixture are deliberate and worth copying into any
regression fixture you write:

- **The two frontmatter-key rules are separated.** A single misspelling like
  `colours` fires §14 and §15 together, which makes them impossible to tell
  apart. `descriptoin` (close, not token-shaped) and `radii` (token-shaped,
  not close) isolate one rule each.
- **`broken-ref` appears at both severities**, adjacent, so the (`rule`,
  `severity`) pairing from §2 is visible in one glance.
- **`orphaned-tokens` is kept silent** by using MD3 family names for all four
  colors. Otherwise four extra warnings would drown the planted ones.
- **The second component, `card`, is clean.** It proves the linter reports per
  component, not per file: one broken component does not suppress or
  contaminate the other.

---

## 21. Verbatim output: `examples/fixture-clean.md` — the contrast case

The known-good control. Same five token categories, same eight body sections,
zero defects.

Command:

```
cd /tmp && npx --yes @google/design.md@0.4.0 lint \
  <SKILL>/examples/fixture-clean.md
```

Exit code: **0**.

```
{
  "findings": [
    {
      "severity": "info",
      "message": "Design system defines 5 colors, 2 typography scales, 2 rounding levels, 2 spacing tokens, 2 components.",
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

**One info and nothing else is the target state for authored files.** It is
reachable, and every template in `assets/` reaches it. Three decisions in the
fixture are what keep the count at one — reuse all three:

1. Colors use MD3 family names (`primary`, `on-primary`, `surface`,
   `on-surface`, `outline`), so §9 never fires even though `outline` is
   referenced by no component.
2. `spacing` and `rounded` are both non-empty, so §11 stays quiet without
   needing an `omitted` block.
3. There is no `omitted` key at all, so §16 adds no extra info. A file that
   legitimately needs `omitted` will show one info per declared section, and
   that is still a clean file.

For reference, the upstream project's own example produces the same single
info at a much larger scale:

```
Design system defines 47 colors, 8 typography scales, 6 rounding levels, 8 spacing tokens, 10 components.
```

Size is not what generates findings. Naming discipline is.

---

## 22. The skill's wrapper: `scripts/lint`

`scripts/lint` is a Python 3 standard-library wrapper around the same npx
invocation. It exists for three reasons: the upstream JSON spends tokens on
punctuation, it says what is wrong without saying what to change, and its exit
code ignores warnings.

The wrapper does not re-implement any rule. Every finding it prints came from
the upstream linter unmodified.

### 22.1 Flags

| Flag | Effect |
| :--- | :--- |
| *(none)* | Human-readable report per file, plus a `REMEDY` block. |
| `--strict` | Warnings fail too. Changes the verdict and the exit code, never the findings. |
| `--json` | Emit upstream JSON instead: verbatim for one file, an object keyed by absolute path for several. |
| `--version PIN` | Package version to run. Default `0.4.0`. **Takes an argument** — it does not print the wrapper's own version. |
| `--list-rules` | Print all fourteen (`rule`, `severity`) rows with a remedy each, then exit 0. Runs no linter and needs no network. |

Several `FILE` arguments are accepted. Paths are expanded and resolved to
absolute before the CLI call, and duplicates are linted once.

### 22.2 Exit codes

| Code | Meaning |
| :--- | :--- |
| 0 | Clean: no errors, and under `--strict` no warnings either. |
| 1 | Errors present, or warnings present under `--strict`. |
| 2 | Input problem: file missing, unreadable, a directory, or a usage error. |
| 3 | `npx` or the CLI is unavailable, or returned output that is not JSON. |

With several files the worst code wins, ordered `3 > 2 > 1 > 0`.

Codes 0/1/2 line up with upstream. Code 3 is the wrapper's own: it separates
"your file is wrong" from "the toolchain is not working", which upstream
conflates.

### 22.3 How the report maps onto the raw findings

Four transformations, and nothing else:

1. **Regrouped by severity** — errors, then warnings, then infos. Emitted
   order is preserved *within* each group. This is the one place the wrapper
   departs from upstream ordering (§4); the raw registry order is still
   available with `--json`.
2. **Tabulated** — `severity`, `rule`, `path`, `message` as aligned columns.
   A finding with no `path` prints `-`. A finding with no `rule` (§19) prints
   `-` there too.
3. **A `REMEDY` block** — one line per distinct (rule id, remedy text) pair,
   in the order the rows appear above. The remedies are the wrapper's own
   text, keyed on (`rule`, `severity`), so the two `broken-ref` variants get
   different advice. The dedup is coarser than the finding list: two
   `unknown-key` findings naming different keys share one remedy line.
   Verified on a file carrying both `descriptoin` and `colours` — two
   `unknown-key` rows, one `unknown-key` remedy. Count remedies to learn which
   *kinds* of defect are present, never how many findings there are.
4. **A verdict line** — `PASS` or `FAIL` followed by the upstream `summary`
   triple. The triple is printed unchanged even on `PASS`, so a warning count
   is never hidden behind a passing exit code.

### 22.4 Verified: the wrapper on `fixture-broken.md`

```
$ scripts/lint examples/fixture-broken.md
```

stderr, once per run:

```
[lint] running npx @google/design.md@0.4.0 — the first call downloads the package and takes about 30 seconds
```

stdout:

```
<SKILL>/examples/fixture-broken.md
  severity  rule                path                                 message
  error     broken-ref          components.button-primary            Reference {rounded.xl} does not resolve to any defined token.
  warning   broken-ref          components.button-primary.elevation  'elevation' is not a recognized component sub-token. Valid sub-tokens: backgroundColor, textColor, typography, rounded, padding, size, height, width.
  warning   contrast-ratio      components.button-primary            textColor (#a8b4c0) on backgroundColor (#7a8a99) has contrast ratio 1.68:1, below WCAG AA minimum of 4.5:1.
  warning   section-order       -                                    Section 'Typography' appears before 'Colors', which is out of order. Expected order: Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts
  warning   unknown-key         descriptoin                          Unknown key "descriptoin" — did you mean "description"?
  warning   token-like-ignored  radii                                "radii" looks like a design-token map but is not a recognized schema key (colors, typography, spacing, rounded, components). It will be silently ignored by export commands. Rename it to a supported key or move its values under a recognized section.
  warning   unknown-omission    omitted                              unknown section name 'Elevation' in omitted key
  info      token-summary       -                                    Design system defines 4 colors, 1 typography scale, 1 rounding level, 1 spacing token, 2 components.

  REMEDY
    broken-ref          Define the token the reference names, or repoint {path.to.token} at a path that exists in the frontmatter.
    broken-ref          Rename the component key to one of backgroundColor, textColor, typography, rounded, padding, size, height, width — or drop it; there is no sub-token for elevation or shadow.
    contrast-ratio      Change one of the two colors until the pair reaches 4.5:1 (aim for 7:1 on body text); the message quotes the measured ratio.
    section-order       Reorder the body H2s to Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts — only the first offending pair is reported, so rerun after fixing.
    unknown-key         Rename the key to the one the message suggests; the schema keys are version, name, description, omitted, colors, typography, rounded, spacing, components.
    token-like-ignored  Move those values under a recognized section (colors, typography, spacing, rounded, components); export commands ignore the key as written.
    unknown-omission    Use one of the five valid section names under `omitted`: colors, typography, spacing, rounded, components.
    token-summary       Informational. No action; read the counts back and confirm they match what you meant to define.

  FAIL: 1 error, 6 warnings, 1 info
```

Exit code: **1**.

Compare against §20. The eight findings are identical in content; only the
row order differs — `token-summary` has moved from position 4 to last, because
infos sort after warnings. The `REMEDY` block lists eight entries for eight
findings: `broken-ref` appears twice with two different remedies, which is the
(`rule`, `severity`) distinction from §2 made operational.

### 22.5 Verified: the wrapper on `fixture-clean.md`

```
<SKILL>/examples/fixture-clean.md
  severity  rule           path  message
  info      token-summary  -     Design system defines 5 colors, 2 typography scales, 2 rounding levels, 2 spacing tokens, 2 components.

  REMEDY
    token-summary  Informational. No action; read the counts back and confirm they match what you meant to define.

  PASS: 0 errors, 0 warnings, 1 info
```

Exit code: **0**.

### 22.6 Verified: `--strict` and multiple files

Two files, the first carrying a single `missing-primary` warning:

```
/private/tmp/.../rules/p-missing-primary.md
  severity  rule             path    message
  warning   missing-primary  colors  No 'primary' color defined. The agent will auto-generate key colors, reducing your control over the palette.
  info      token-summary    -       Design system defines 2 colors, 1 typography scale, 1 rounding level, 1 spacing token.

  REMEDY
    missing-primary  Add a `primary` key under `colors`, or rename the accent token to `primary`.
    token-summary    Informational. No action; read the counts back and confirm they match what you meant to define.

  FAIL: 0 errors, 1 warning, 1 info (--strict: warnings fail)

<SKILL>/examples/fixture-clean.md
  severity  rule           path  message
  info      token-summary  -     Design system defines 5 colors, 2 typography scales, 2 rounding levels, 2 spacing tokens, 2 components.

  REMEDY
    token-summary  Informational. No action; read the counts back and confirm they match what you meant to define.

  PASS: 0 errors, 0 warnings, 1 info

TOTAL 2 files: 1 passed, 1 failed — 0 errors, 1 warning, 2 infos
```

Exit code: **1**. The first path above is abbreviated for width; the wrapper
prints it in full.

Upstream would have exited 0 on both files. This is the whole point of
`--strict`: it is what makes §3's warning class enforceable.

### 22.7 Verified: input and toolchain failures

A path that does not exist — stderr first, then stdout:

```
lint: /tmp/does-not-exist-design.md: file not found
/tmp/does-not-exist-design.md
  not linted: file not found
```

Exit code: **2**. The file is never handed to `npx`; the check is local.

A file with no frontmatter — the rule-less finding from §19 gets a remedy like
any other, under the label `-`:

```
  severity  rule  path  message
  warning   -     -     No YAML content found. Expected frontmatter (---) or fenced yaml code blocks.

  REMEDY
    -  Add a YAML frontmatter block delimited by --- with at least `name:`; without it the file defines no tokens and no rule can run.

  PASS: 0 errors, 1 warning, 0 infos
```

Exit code: **0** — because upstream reports it as a warning, not an error.
Under `--strict` the same run fails. Any gate over authored DESIGN.md files
MUST use `--strict` for this reason alone.

### 22.8 Verified: `--list-rules`

Offline, no npx call, exit 0. Use it to resolve a rule id when the network is
unavailable:

```
Rule ids emitted by @google/design.md@0.4.0 lint. `broken-ref` covers two different defects,
one per severity. The registry name `omitted-rules` is never printed: it
emits declared-omission, redundant-omission and unknown-omission instead.

  broken-ref          error    Define the token the reference names, or repoint {path.to.token} at a path that exists in the frontmatter.
  broken-ref          warning  Rename the component key to one of backgroundColor, textColor, typography, rounded, padding, size, height, width — or drop it; there is no sub-token for elevation or shadow.
  missing-primary     warning  Add a `primary` key under `colors`, or rename the accent token to `primary`.
  contrast-ratio      warning  Change one of the two colors until the pair reaches 4.5:1 (aim for 7:1 on body text); the message quotes the measured ratio.
  orphaned-tokens     warning  Reference the token from a component, or rename it into the MD3 family vocabulary (primary/secondary/tertiary/error/surface/background/outline and their on-, -container, -fixed, -variant forms).
  token-summary       info     Informational. No action; read the counts back and confirm they match what you meant to define.
  missing-sections    info     Define the named section (`spacing` or `rounded`), or declare it under `omitted` with a reason.
  missing-typography  warning  Add at least one `typography` scale; a file that defines colors and no type is half a system.
  section-order       warning  Reorder the body H2s to Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts — only the first offending pair is reported, so rerun after fixing.
  unknown-key         warning  Rename the key to the one the message suggests; the schema keys are version, name, description, omitted, colors, typography, rounded, spacing, components.
  token-like-ignored  warning  Move those values under a recognized section (colors, typography, spacing, rounded, components); export commands ignore the key as written.
  declared-omission   info     Informational. This confirms the section is deliberately unset — this is the intended use of `omitted`.
  redundant-omission  warning  Remove the section from `omitted`, or delete the tokens it still defines; the file currently claims both.
  unknown-omission    warning  Use one of the five valid section names under `omitted`: colors, typography, spacing, rounded, components.

A finding with no rule id at all comes from the frontmatter parser, before
any rule runs (an unparseable or absent YAML block).
```

The `contrast-ratio` line in that listing is the **Route 1** remedy and the
listing does not say so; on Routes 2 and 3 keep the measured hex (§8).

That closing paragraph is the wrapper's own text and it covers only half the
case. §19.2 is the other half: the model builder also emits rule-less
findings, at `error` rather than `warning`. Treat a rule-less `error` row as a
bad token value, not as broken YAML.

---

## 23. What the linter does not check

State these plainly. An agent that reports "the linter passed" without them is
overstating the evidence.

**Not checked at all — no rule exists:**

| Not checked | Consequence |
| :--- | :--- |
| Whether all eight body sections are present | Seven sections, or two, lint identically clean (§13). |
| Any word of the body prose | No rule reads prose; `##` order is the only body property a rule sees. The parser, however, reads body `yaml`/`yml` fences as tokens (§19.3). |
| Whether a `fontFamily` string names a real font | `"Helvetica Neue Ultra"` passes. |
| Whether a font covers the script the product ships in | Cyrillic coverage is not verifiable from a DESIGN.md; check it out of band. |
| Whether a type scale is modular or arbitrary | `13px 15px 19px 33px` passes. |
| Whether neutrals share a hue | An incoherent grey ramp passes. |
| Whether every radius is identical | A single-radius system passes. |
| Whether the accent is used in more than one role | Passes. |
| Whether values are copied from a framework default | Passes. |
| Contrast of any pair not wired into one component | Passes (§8). |
| AAA contrast, or the 3:1 non-text threshold | Not implemented (§8). |
| Whether `omitted` is honest | A file may omit everything and lint clean. |

**Checked, but weaker than it looks:**

| Appears to check | Actually checks |
| :--- | :--- |
| References | Only inside `components`; elsewhere a bad reference drops the token silently (§5). |
| Unknown keys | Only within edit distance 2, or token-shaped (§14, §15). |
| Section order | Only the first offending pair, only `##` headings (§13). |
| Contrast | Only intra-component pairs, only AA 4.5:1 (§8). |
| Orphaned tokens | Never, if `components` is empty (§9.3). |
| Token values | Colors, `rounded` dimensions and typography properties, loudly (§19.2). A bad `spacing` dimension, a bare unitless number, or any unresolvable reference is dropped in silence (§10). |

`references/anti-slop.md` covers the first table: it turns each unchecked
property into a detectable signature you can look for by hand. The linter is
a syntax gate. Quality is a separate pass, and it is yours.

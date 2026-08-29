# Extraction procedures

Three procedures turn an input into a DESIGN.md. Each is a numbered sequence.
Follow the steps in order. Each procedure ends with §4, the mandatory lint step.

| Procedure | Input | Section |
| :--- | :--- | :--- |
| A | A text description of a brand, product, audience, tone | §1 |
| B | A screenshot of an interface or a mockup | §2 |
| C | An existing codebase: CSS, a Tailwind config, a token file | §3 |

## Preconditions

1. The CLI is not installed. Invoke it through `npx`, always from `/tmp`, always
   with an absolute path to the file:

   ```bash
   cd /tmp && npx --yes @google/design.md@0.4.0 lint /ABS/PATH/DESIGN.md
   ```

   A workspace with its own `design.md` entry shadows the bin name, so `cd /tmp`
   is not optional. The first `npx` run takes about 30 seconds while the package
   is fetched.
2. `scripts/lint` wraps that invocation and parses the JSON. Use it where these
   procedures say `scripts/lint`.
3. Do not open the upstream `design.md` clone or its `examples/` directory. This
   skill is Apache-2.0 and carries no upstream source. Everything needed is in
   `references/`, `assets/`, and `examples/`.

---

## 1. Procedure A — from a text description

Input: prose about a brand, product, audience, tone. It carries intent and
constraints. It carries no token values.

Output: `DESIGN.md` derived from one of the four templates in `assets/`, with a
populated `omitted` block covering everything the description did not decide.

### A.1 Classify the product

Read the description and record four facts before touching a template:

1. **Surface class.** Application UI (repeated controls, authenticated sessions,
   dense data) or reading surface (the text is the product).
2. **UI language.** Any Russian-language UI is a hard routing signal — see A.2.
3. **Density.** How much information sits in one viewport: dense, moderate, airy.
4. **Named constraints.** Existing brand colors, a required font, an accessibility
   target, a platform. Record each verbatim; these override template values.

If the description supplies fewer than two of {palette character, typographic
character, density}, stop and ask the user for the missing ones. Do not proceed
by inventing them.

### A.2 Select the base template

Apply the rules in order. The first rule that matches decides.

| # | Condition in the description | Template |
| :--- | :--- | :--- |
| R0 | The product's UI strings are Russian, or the product serves a Russian-speaking market with a Russian interface | `template-cyrillic` |
| R1 | Application UI: dashboard, admin panel, console, CRM, IDE, developer tool, analytics, internal tooling, any product described as SaaS | `template-product-saas` |
| R2 | Reading surface: magazine, blog, documentation site, newsletter, essay, portfolio, a landing page whose purpose is to be read | `template-editorial` |
| R3 | Surface class is outside R1 and R2 (game, print piece, hardware panel, mobile-only, embedded display, data-viz-only product) | `template-skeleton` |
| R4 | The description is too thin to classify, or the user asked to author from zero | `template-skeleton` |

**R0 is an override, not a tie-breaker.** Any product with a Russian-language UI
routes to `template-cyrillic` regardless of surface class, density, or brand
constraints. The reason is correctness, not taste: Google Fonts serves Instrument
Serif and Bodoni Moda with `latin` and `latin-ext` subsets only, so Russian text
in those families silently falls back to a system serif and the specified design
never renders. Families verified to carry Cyrillic: Golos Text, Onest, Inter,
IBM Plex Sans, JetBrains Mono, Manrope. Only those appear in `template-cyrillic`.

If a Russian product is also editorial (R0 and R2 both match), take
`template-cyrillic` as the base and import the *relationships* from
`template-editorial` — its scale ratio, its spacing rhythm, its neutral step
count. Do not import its font families.

**Tie-breakers**, in order, for cases where two rules read as applicable:

1. **Marketing site versus the app.** Decide which artifact this DESIGN.md
   governs. The marketing site is R2. The application is R1. If both are in
   scope, produce the R1 file first — a dense control set is the harder
   constraint, and an editorial surface derives from a product system more
   cleanly than the reverse — and describe the marketing surface in the
   `Overview` body prose.
2. **Documentation sites and data-heavy articles.** Count the distinct repeated
   interactive control types the description implies (search, filter, tabs,
   tree nav, code copy, version switch, …). More than five is R1. Five or fewer
   is R2.
3. **R1 and R2 signals equally strong, no Russian UI.** Take
   `template-product-saas`.
4. **An uncovered product type with three or more concrete values already
   given.** Take `template-skeleton`. Do not force-fit a template whose
   relationships were built for a different surface.
5. **Two templates still tied after 1–4.** Take `template-skeleton` and ask the
   user which surface to optimise for. A wrong base template is more expensive
   to unwind than one question.

### A.3 Substitute tokens, preserve the relationship structure

The taste in a template lives in the *relationships between* its values, not in
the values. Substitution replaces values. It must not disturb the relationships.

**Invariants — carry these through unchanged:**

| Invariant | Measured as | Why it must not be randomised |
| :--- | :--- | :--- |
| Neutral step count | Number of tokens in the `surface` / `background` families | The step count is what makes depth legible. Adding or dropping a step collapses or inflates the hierarchy. |
| Modular scale ratio | `fontSize[n] / fontSize[n-1]` across the type tokens | A constant ratio is the difference between a scale and a list of numbers. |
| Spacing base unit and series | The greatest common divisor of the `spacing` values, and their multipliers | The rhythm is the grid. Off-grid values read as misalignment, not as variety. |
| Radius progression | Number of `rounded` steps and whether the series is linear or doubling | A single radius reused everywhere removes shape as a signal. |
| Accent role count | How many distinct jobs the accent color does | One accent, one role. A second role makes the first stop meaning anything. |
| Passing contrast pairs | Every component pair the linter cleared at 4.5:1 | Substituting a hue without re-checking silently breaks accessibility. |

**Free to change:** hue and chroma of the accent, the tint direction of the
neutrals, font families (subject to R0), every literal value, and all body prose.

**Token names are not free.** `orphaned-tokens` inspects color token names as
soon as the file defines any `components`. A color is exempt only if a component
references it, or its family is referenced by a component, or its family is one
of the MD3 baseline families: `primary`, `secondary`, `tertiary`, `error`,
`surface`, `background`, `outline` (after stripping the `on-` / `inverse-`
prefixes and the `-container` / `-fixed` / `-dim` / `-bright` / `-tint` /
`-variant` suffixes). Renaming `primary` to `brand` or `on-surface-variant` to
`warm-grey-500` produces one warning per renamed token. Keep the template's MD3
names. Express the brand in the values and the prose.

**Audit the invariants after substituting.** Both commands are dependency-free
and were run against a fixture on this host.

Modular scale ratio, consecutive pairs:

```bash
grep -oE 'fontSize:[[:space:]]*[0-9.]+' /ABS/PATH/DESIGN.md \
  | grep -oE '[0-9.]+' | sort -n | uniq \
  | awk 'NR>1 {printf "%-6s / %-6s = %.3f\n", $1, p, $1/p} {p=$1}'
```

On a 1.333 scale rounded to whole pixels:

```text
16     / 12     = 1.333
21     / 16     = 1.312
28     / 21     = 1.333
```

Integer rounding moves a ratio by a percent or two; 1.312 against a 1.333 target
is rounding, not drift. A step is broken when its ratio departs from the
template's by more than about 5 percent. Nudging `28px` to `30px` in the same
file reports `1.429` — that is drift, and it must be repaired, not accepted.

Spacing rhythm, against the template's base unit:

```bash
awk '/^spacing:/{s=1;next} /^[a-zA-Z]/{s=0} s' /ABS/PATH/DESIGN.md \
  | grep -oE '[0-9.]+' \
  | awk -v base=4 '{printf "%-6s %s\n", $1, ($1 % base == 0 ? "on-grid" : "OFF-GRID")}'
```

```text
4      on-grid
8      on-grid
16     on-grid
26     OFF-GRID
40     on-grid
```

Every `OFF-GRID` line is a defect introduced by substitution. Fix it before
continuing. Set `base` to the template's own base unit, not always 4.

### A.4 Rewrite Overview and Do's and Don'ts

1. Rewrite `## Overview` for this brand. Name the product, the audience, and the
   one decision the system is built around. Delete every sentence that would
   remain true if the product were replaced by a different product.
2. Rewrite `## Do's and Don'ts` for this system. Each entry must reference a
   token, a role, or a rule that exists in *this* file. An entry that would apply
   unchanged to any design system is filler; delete it.
3. Rewrite the remaining body sections wherever the template's prose describes a
   decision you changed. Prose that contradicts the frontmatter is worse than
   absent prose: the linter does not read body text and will not catch it.

### A.5 Declare what the description did not cover

Everything the description did not decide goes into `omitted`. Do not invent it.

`omitted` accepts a mixed array of bare strings and `{section, reason}` objects.
The valid section names are exactly `colors`, `typography`, `spacing`,
`rounded`, `components`. Any other name — `elevation`, `shapes`, `layout`,
`states` — produces an `unknown-omission` warning.

```yaml
omitted:
  - section: components
    reason: "The description named no controls; the component inventory is undecided."
  - spacing
```

Two rules police this field. Naming a section that has no tokens emits
`declared-omission` at info level — the intended case. Naming a section that
*does* have tokens emits `redundant-omission` at warning level. Remove the
omission or remove the tokens; do not keep both.

Concerns with no matching section name — motion, dark theme, iconography,
illustration, voice — belong in body prose under the nearest canonical heading,
not in `omitted`.

### A.6 Lint and fix

Go to §4.

---

## 2. Procedure B — from a screenshot

Input: an image of an interface or a mockup. The agent reads it with the file
reading tool.

### B.0 Reliability of what an image yields

This table governs the whole procedure. Before writing any token, locate the
fact in this table and treat it accordingly.

| Extracted reliably | Extracted approximately | Not extractable at all |
| :--- | :--- | :--- |
| Presence and number of hierarchy levels | Specific color values | Font family names |
| Character: dark or light, dense or airy | The base rhythm unit (4px or 8px) | States: hover, focus, active, disabled |
| Typographic contrast between levels | The modular scale ratio | The dark theme, when a light screen was captured |
| The rounding system: how many distinct radius steps exist, and whether they grow | Font weights | Component behaviour |
| The number of distinct surface levels | Any radius, spacing, or size in absolute pixels | Whether a value is a token or a one-off |
| Whether surfaces are separated by borders or by shadows | Line height and letter spacing | The semantic name of a color: `primary` or `info` is a decision the image does not record |
| Whether the accent appears in one role or several | The opacity of muted text | Motion, transitions, duration |
| Text alignment and measure | Shadow offset, blur, and spread | Responsive breakpoints and the layout below them |
| The presence of a distinct icon set | The visible grid column count | Error, empty, loading, and skeleton states |

Two facts constrain the middle column further. A retina capture multiplies every
pixel measurement by the device pixel ratio, and the image does not reliably
record that ratio, so absolute geometry read off a screenshot is a ratio guess.
And a screenshot shows rendered output: a 15px value and a 16px value are
indistinguishable at any realistic zoom.

### B.1 Rule 1 — exact color values come from the script

Run `scripts/extract-palette` on the image. Do not read colors off the image by
eye, and do not transcribe a color you believe you recognise.

```bash
scripts/extract-palette /ABS/PATH/screenshot.png --min-share 0.1
```

The script returns the quantized colors with their pixel shares, one per line,
in the columns `#`, `HEX`, `SHARE`, `BUCKETS`, `HUE`, `L*`, `C*`, `HINT`.
`scripts/README.md` §2.3 and `extract-palette --help` document every option;
`--json` emits the same measurement as one machine-readable object.

**Lower the share floor, and do not crop a full-application capture.** The
default `--min-share` of 0.5 sits directly on top of a one-control accent. On the
1440x900 dashboard capture used through the rest of this section, `#e25a3c` — the
primary button, the active nav marker and the status chips — measures `0.52%`,
half a point above the floor. Adding `--ignore-edges 4` removes 57 px from each
side, a quarter of the 233 px rail, and takes the same colour to `0.40%`: that run
reports six neutrals and no accent row at all. Pass `--ignore-edges` for a browser
screenshot with chrome to crop, never for a capture that is already only the
application.

**Recovery, when the report contradicts the image.** Both cases are silent
failures — the report is well-formed and the missing colour leaves no trace.

| What you see | What it means | What to run |
| :--- | :--- | :--- |
| The image has an obvious accent; no row is hinted `accent candidate` | The accent's share is under the floor, or the crop cut it | Drop `--ignore-edges`, then `--min-share 0.1`, then `--min-share 0` |
| Two light planes are visibly different in the image; the report has one row for both | They are within `--merge-distance` and merged into one cluster | Halve `--merge-distance` and re-run |

On the same capture the second case is live at the default settings: the page
ground `#f7f4ef` is `dE 4.62` from card white in CIELAB, under the default merge
distance of `6.0`, so both planes report as one `#ffffff` row at `71.70%`. At
`--merge-distance 3` they separate — `#ffffff` at `58.51%` and `#f7f4ef` at
`16.56%`. Neither number is wrong; the default answers a coarser question than
role assignment needs.

**Rationale.** Four separate distortions sit between the source color and what
the agent perceives. Lossy compression shifts flat fills by several units per
channel. Antialiasing at every glyph and border edge blends two colors into a
third that exists nowhere in the design. A gradient has no single value, and the
eye picks an arbitrary point on it. An embedded color profile re-maps every
channel on display. A hex written from perception is a fabrication with the
surface form of a measurement, which is the most expensive kind of error in this
format: it will be copied into code and shipped.

### B.2 Rule 2 — the script measures, the agent interprets

The script returns colors and shares. It does not return roles. Assigning roles
is the agent's work, and it is the only part of color extraction the agent does.

Keep the division explicit in your own reasoning and in the hand-back:

| Question | Answered by |
| :--- | :--- |
| What color is this, exactly? | The script. |
| What share of the image is it? | The script. |
| Is it `background` or `surface`? | The agent, from where it appears. |
| Is it the accent or an incidental illustration color? | The agent, from how many roles it plays. |
| Which MD3 family name does it take? | The agent. |

Interpretation heuristics, in order of reliability:

1. **The ground is the plane the inset rectangles sit on. Decide it by region,
   not by share.** Measure a gutter between two cards, or the margin outside the
   card row: whatever fills that window is `background`. This test is first
   because it is the only one that reads the layout, and because share alone
   inverts on exactly the input class this procedure targets (heuristic 3).
2. `surface` is what fills the inset rectangle. Measure inside one card and
   compare it against the ground window from step 1. Further neutrals measured
   between the two form the surface ramp.
3. **Share ranks area, not depth.** The largest share is the ground only when the
   ground is mostly uncovered. A dashboard whose cards and table body carry one
   fill inverts this: on the capture measured below, rank 1 `#ffffff` at `71.70%`
   is the fill of the app bar, the four cards and the table body, while the ground
   under them is `#f7f4ef`. Taking rank 1 as `background` gives every card the
   page's own colour and erases the card as an object. Use share to *order*
   candidates and steps 1-2 to *assign* them.
4. The highest-chroma color with a small share, appearing on one control type,
   is `primary`. Small share plus single role is the signature of an accent.
5. A saturated red, amber, or green with a very small share is a status color,
   not the accent. Only red maps to a schema family (`error`); the rest belong
   in body prose or in a component reference.
6. Text colors are the colors that appear only in glyph-shaped regions. Their
   measured values are contaminated by antialiasing; take the darkest
   (light theme) or lightest (dark theme) cluster member, not the mean.

Name the result in the MD3 vocabulary, per the constraint in A.3.

**`--region X,Y,W,H` is the sanctioned way to run steps 1 and 2.** It counts only
the named window of the decoded image — `X,Y` is the top-left corner, `W,H` the
size, all in whole pixels — so the histogram is local instead of page-wide. A
region that is empty, negative, or does not fit inside the image is rejected at
exit 1 and never clamped, so a mistyped offset cannot quietly become a
measurement of somewhere else. It cannot be combined with `--ignore-edges`.

Read the coordinates off the image with the file reading tool, then measure the
two windows. On the 1440x900 dashboard capture, the gutter between the first and
second card:

```bash
scripts/extract-palette /ABS/PATH/screenshot.png --region 520,105,30,110
```

```text
  image      1440x900 px -> 30x110 at x=520..550, y=105..215 from --region 520,105,30,110
  sampled    3300 px on a stride-1 grid; 3300 counted, 0 below alpha 128

  #   HEX          SHARE  BUCKETS        HUE     L*     C*  HINT (heuristic)
  --------------------------------------------------------------------------
  1   #f7f4ef    100.00%  1 of 1         38°   96.3    2.8  background candidate (largest area)
```

And a window wholly inside the first card:

```bash
scripts/extract-palette /ABS/PATH/screenshot.png --region 280,115,220,35
```

```text
  image      1440x900 px -> 220x35 at x=280..500, y=115..150 from --region 280,115,220,35
  sampled    7700 px on a stride-1 grid; 7700 counted, 0 below alpha 128

  #   HEX          SHARE  BUCKETS        HUE     L*     C*  HINT (heuristic)
  --------------------------------------------------------------------------
  1   #ffffff     82.95%  1 of 2          0°  100.0    0.0  background candidate (largest area)
  2   #6b7472     17.05%  1 of 2        167°   48.0    3.8  neutral ramp, dark end (text, or a dark surface)
```

Two windows settle it: `background` is `#f7f4ef`, `surface` is `#ffffff`, and the
`#6b7472` inside the card is label text, not a third plane. The `HINT` column
reads `background candidate` in both runs because it only ever means "rank 1 in
this run" — inside a card that is the card, not the page.

Note what the page-wide run alone could not have told you. `#f7f4ef` does not
appear in it at all: it is `dE 4.62` from `#ffffff`, inside the default
`--merge-distance` of `6.0`, so the two planes report as one `#ffffff` row. Where
a region probe returns a colour absent from the global report, that is the
merge, and `--merge-distance 3` separates them.

### B.3 Rule 3 — fonts are not guessed

Do not write a font family name asserted from a screenshot. Instead:

1. Describe the character in the body prose: grotesque, humanist, geometric,
   transitional serif, slab, monospace.
2. Where the letterforms are legible, offer two or three candidates that match
   that character, and say which letterforms in the image support the reading —
   a straight-leg `R`, a double-storey `g`, a single-storey `a`, the terminal
   angle on `e`, the presence or absence of a spur on `G`.
3. Write one candidate into `typography.*.fontFamily` and label it a placeholder
   in the hand-back message.
4. Ask the user to confirm or replace it.

**Where no letterform is legible, steps 2 and 3 do not apply.** A capture whose
text is under about 12 px, heavily compressed, redacted into placeholder blocks,
or present only inside a logo carries no evidence about the family. Offer no
candidates — a candidate list with nothing behind it is an invitation to pick
one, and the pick is then indistinguishable from a reading. Write no
`fontFamily`, and declare the section instead:

```yaml
omitted:
  - section: typography
    reason: "The capture has no legible letterform; type is undecided."
```

The omission suppresses the `missing-typography` warning the empty map would
otherwise raise (`references/linter-rules.md` §12), which is the point: the file
now states that type is undecided rather than staying silent about it. Name the
observable facts — the number of distinct sizes, the contrast between levels,
whether the face is serif or sans where even that is readable — in body prose
under `## Typography`.

**Rationale.** A font name is a verifiable factual claim about a specific
licensed artifact. It is also, unlike a color, unfalsifiable from the same
image: hundreds of grotesques are indistinguishable at UI sizes, and the
rendering path adds hinting and subpixel differences that erase what remains.
An asserted name will be believed and acted on, because a name in a token file
reads as a fact rather than a guess. If the product's UI is Russian, restrict
every candidate to the verified-Cyrillic list in A.2 — an asserted family with
no Cyrillic subset does not merely misname the design, it fails to render it.

### B.4 Rule 4 — absences go to `omitted`, with a reason

Every value that the image does not contain goes into `omitted` or into body
prose. The `omitted` field exists in the format for exactly this case. Use it
instead of plausible invention.

The usual absences in a single static screenshot:

| Absent | Where it goes |
| :--- | :--- |
| Component inventory beyond the two or three visible controls | `omitted: [{section: components, reason: …}]` |
| Hover, focus, active, pressed, disabled, selected | Body prose under `## Components`, named as undecided |
| The opposite theme — a light capture yields no dark theme, and the reverse | Body prose under `## Colors` |
| Error, empty, loading, and skeleton states | Body prose under `## Components` |
| Every spacing step not exercised on this one screen | `omitted: [spacing]`, or a partial `spacing` map plus prose |
| Radius steps not exercised on this one screen | `omitted: [rounded]`, or a partial map plus prose |
| Motion, transition duration, easing | Body prose under `## Elevation & Depth` |
| Responsive behaviour and breakpoints | Body prose under `## Layout` |
| Iconography and illustration | Body prose under `## Shapes` |
| Text sizes below the two or three visible | Partial `typography` map plus prose |

Only `colors`, `typography`, `spacing`, `rounded`, and `components` are valid
`omitted` section names. Everything else in the left column is prose. Writing
`- states` or `- dark-theme` into `omitted` produces an `unknown-omission`
warning.

Declaring `spacing` or `rounded` in `omitted` also suppresses the
`missing-sections` info for that name, which is the correct outcome: the file
states that the value is undecided rather than staying silent about it.

### B.5 Rule 5 — hand the result back as a hypothesis

Do not present the file as extracted. Present it as a hypothesis, with measured
values separated from inferred ones. Use this shape; fill every angle-bracket
slot from actual output.

```text
DESIGN.md drafted from <screenshot filename>. This is a hypothesis, not a
readout. Confirm the marked items before anything is built on it.

MEASURED — scripts/extract-palette, pixel quantization:
  background   <#hex>   <share>
  surface      <#hex>   <share>
  primary      <#hex>   <share>

INFERRED — my reading of the image, not measured:
  - <#hex> is the accent: it appears only on the primary button.
  - Base rhythm unit <N>px, from the gap between label and field.
  - Modular scale ratio ~<R>, from the <k> visible text sizes.
  - Two surface levels; depth is carried by <borders|shadow>.

NEEDS CONFIRMATION — I did not extract this, I chose it:
  - Font family. The image shows a <character>, evidenced by <letterform>.
    Candidates: <A>, <B>, <C>. I wrote <A> as a placeholder.

OMITTED — declared in the file, not guessed:
  - components — <reason>
  - <further sections, each with its reason>
  Not in the file at all, and not omittable as a section: hover/focus/disabled
  states, the dark theme, motion, breakpoints. These are named in body prose.

LINT: <E> errors, <W> warnings, <I> infos.
CONTRAST: <component>.<backgroundColor> on <textColor> measures <R>:1, below the
  4.5:1 gate. Both values are measured; I did not change either. Recorded under
  Do's and Don'ts.  <or, when nothing fails: every intended pair clears 4.5:1.>
```

**Rationale.** The failure mode of this procedure is not an inaccurate file; it
is an accurate-looking file. A hex measured to the unit and a font name invented
whole look identical in YAML. Separating the two columns is the only thing that
stops the invented half from being treated as measured.

### B.6 Worked walk-through

`examples/example-saas-dashboard.md` is the finished output of this procedure.
Open it before drafting your own and read it against the steps below.

1. **Read the image.** Record the character in one sentence: dark, dense,
   two surface levels, one accent, borders rather than shadow.
2. **Measure.** Run `scripts/extract-palette` (B.1). Keep the raw output; it
   goes into the hand-back verbatim.
3. **Assign roles.** Apply the B.2 heuristics. Name the tokens in the MD3
   vocabulary so `orphaned-tokens` stays quiet once components are defined.
4. **Count, do not measure.** From the reliable column: the number of surface
   levels, the number of radius steps, the number of type sizes. These become
   the shape of the system.
5. **Infer the rhythm.** Divide the visible gaps by their greatest common
   divisor to get a candidate base unit, then state it as inferred. Do not
   present it as measured.
6. **Fonts.** Apply B.3. Write one placeholder family; list the candidates in
   the hand-back.
7. **Components.** Write only the controls actually visible. If two controls are
   visible, write two components — not a plausible library of eight. Compute each
   component's `backgroundColor` / `textColor` ratio before linting, and where a
   pair is below 4.5:1 **keep the measured values**. Do not adjust a colour the
   script measured in order to clear `contrast-ratio`: the pair failed in the
   product, the file is a record of that product, and an edited hex converts a
   measurement into an invention while hiding a real accessibility defect. Record
   the shortfall instead — name the pair and its ratio in the hand-back, and add
   a `**Don't**` entry under `## Do's and Don'ts` that names the two tokens. The
   lint run then carries a `contrast-ratio` warning that is explained rather than
   silenced.
8. **`omitted`.** Apply B.4. Give every entry a reason that names the screenshot
   as the limit.
9. **Body prose.** Write all eight sections in canonical order. Under
   `## Components`, name the states the image did not show.
10. **Lint.** §4.
11. **Hand back.** Apply B.5.

Check `examples/example-saas-dashboard.md` for the four marks of this procedure:
an `omitted` block whose reasons name the screenshot, color tokens in MD3 family
names, a component list no longer than what one screen shows, and a
`Do's and Don'ts` section that names this product rather than design in general.

---

## 3. Procedure C — from a codebase

Input: CSS, a Tailwind config, a token file. It carries real values. It carries
no hierarchy and no rationale.

Every command below was run against a fixture on this host. The primary forms
use POSIX `grep`; where a `rg` form is given it was run against the same fixture
and produced byte-identical output.

One environment caveat, because it changes results without changing the command:
some agent shells define `grep` and `rg` as functions wrapping ugrep or ripgrep,
which honour `.gitignore` where `grep -r` does not, so the identical harvest
silently returns fewer occurrences in any repo with a build directory ignored —
on a fixture with `dist/` ignored the wrapper dropped the only hex declared
there. Run `type grep` once; if it reports a function or an alias, prefix every
harvest below with `command grep` — or call `/usr/bin/grep`.

### C.1 Harvest what is used, not what is declared

A declared-but-dead token is noise. It was someone's plan, not the product's
design. Collect usage first, then intersect.

**Hex literals with frequency**, across styles and components:

```bash
cd /ABS/PATH/repo && grep -rhoE '#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{3}\b' \
  --include='*.css' --include='*.scss' --include='*.js' --include='*.ts' --include='*.tsx' . \
  | tr 'A-F' 'a-f' | sort | uniq -c | sort -rn
```

```text
   4 #3b82f6
   3 #161b22
   3 #0e1116
   2 #f85149
   2 #e6edf3
   1 #fff
   1 #abcdef
   1 #8b949e
   1 #7c3aed
   1 #2f6fdb
   1 #1c222b
```

The alternation is ordered longest-first on purpose. Reversed, `#[0-9a-fA-F]{3}`
would match the first three characters of every six-digit hex and silently
report a different palette. The `tr` folds case so `#161B22` and `#161b22` are
one entry.

The ripgrep equivalent, run on the same fixture and byte-identical to the block
above:

```bash
rg -oIN --no-heading --no-ignore \
  -g '*.css' -g '*.scss' -g '*.js' -g '*.ts' -g '*.tsx' \
  -e '#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{3}\b' . \
  | tr 'A-F' 'a-f' | sort | uniq -c | sort -rn
```

Two parts of that form are load-bearing. One `-g` glob is needed per `--include`
pattern — five, not two: a form limited to `*.css` and `*.js` reads no component
source, and on a React or TypeScript tree that is where most of the palette
lives. And `--no-ignore` is needed because ripgrep skips `.gitignore`d paths that
`grep -r` reads. On a four-file React fixture with `dist/` ignored, the two-glob
form without `--no-ignore` reported a single line, `1 #b3452b`, where `grep -r`
reported `3 #b3452b` / `2 #fbfaf8` / `1 #12181b`; the corrected form above
reproduced the `grep` counts exactly.

**Custom properties: declared, referenced, and dead.**

```bash
cd /ABS/PATH/repo
grep -rhoE '(^|[{;])[[:space:]]*--[A-Za-z0-9_-]+[[:space:]]*:' --include='*.css' . \
  | tr -d ' \t:{;' | sort -u > /tmp/declared.txt
grep -rhoE 'var\([[:space:]]*--[A-Za-z0-9_-]+' --include='*.css' . \
  | sed -E 's/^var\([[:space:]]*//' | sort | uniq -c | sort -rn > /tmp/used_counts.txt
awk '{print $2}' /tmp/used_counts.txt | sort -u > /tmp/used.txt
comm -23 /tmp/declared.txt /tmp/used.txt
```

The declaration pattern accepts a preceding `{` or `;` as well as start-of-line.
Anchored at `^` alone it matches nothing in compiled or minified CSS, where a
whole rule is one line: on a fixture whose entire `:root` is
`:root{--color-bg:#0E1116;--color-surface:#161B22;--radius-md:8px;--space-4:16px;--dead-one:#ABCDEF}`
the `^`-anchored form returned no declarations at all and the form above
returned all five. The `{;` added to `tr -d` strips the character the
alternation consumed. It is not matched inside `var(--x)`, so a reference is
still not counted as a declaration.

**Check `/tmp/declared.txt` before reading the dead list.** An empty dead list
from an empty declared list means the scan matched nothing — a different fact
from "every declared property is used", and the two are indistinguishable at the
`comm` output. `wc -l < /tmp/declared.txt` against the number of `--` lines you
can see in the source settles it.

Referenced, with counts:

```text
   3 --radius-md
   2 --space-4
   1 --space-2
   1 --color-text
   1 --color-surface-high
   1 --color-surface
   1 --color-muted
   1 --color-danger
   1 --color-bg
   1 --color-accent-hover
   1 --color-accent
```

Declared and never referenced:

```text
--dead-token
--font-sans
--radius-lg
--radius-sm
--space-1
--space-3
```

The dead list is not automatically deletable. A property consumed only by a
theme switcher, a `@theme` block, or a component library outside the grepped
tree will appear here. Treat it as a question, not a verdict: check each name
once against the whole repo before dropping it.

**Tailwind v4 `@theme` blocks**, which the `var()` scan will not see as usage:

```bash
awk '{gsub(/[{};]/, "\n&\n")} 1' /ABS/PATH/theme.css \
  | awk '/@theme/{seen=1;next}
         seen&&/^[[:space:]]*\{/{inb=1;next}
         inb&&/^[[:space:]]*\}/{inb=0;seen=0;next}
         inb&&/^[[:space:]]*--/{print}' \
  | sed -E 's/^[[:space:]]*//; s/[[:space:]]*;[[:space:]]*$//'
```

The first `awk` puts every brace and semicolon on a line of its own, which is
what makes the block reader work on compact CSS. Without it, a one-line
`@theme{--color-bg:#0E1116;--color-accent:#3B82F6;--radius-md:8px}` yields
nothing: the single-line form consumes the `@theme` line with `next` and then
finds no line starting with `--`. Both forms produce the same four lines on
pretty-printed input; only the two-stage form also reads the compact file.

```text
--color-bg: #0E1116
--color-accent: #3B82F6
--radius-md: 8px
--font-sans: "Inter", sans-serif
```

**Tailwind theme keys**, from either a CommonJS or an ESM config. One command
handles both:

```bash
node --input-type=module -e 'const m=await import(process.argv[1]);const c=m.default??m;const t=c.theme??{};console.log(JSON.stringify({...(t.extend??{}),...Object.fromEntries(Object.entries(t).filter(([k])=>k!=="extend"))},null,2))' /ABS/PATH/tailwind.config.js
```

```text
{
  "colors": {
    "bg": "#0E1116",
    "surface": "#161B22",
    "accent": "#3B82F6"
  },
  "borderRadius": {
    "md": "8px",
    "lg": "12px"
  },
  "spacing": {
    "1": "4px",
    "2": "8px",
    "4": "16px"
  },
  "fontFamily": {
    "sans": [
      "Inter",
      "system-ui",
      "sans-serif"
    ]
  }
}
```

A Tailwind theme key is a declaration. Its usage lives in the markup. Count it:

```bash
cd /ABS/PATH/repo && grep -rhoE 'class="[^"]*"' \
  --include='*.html' --include='*.jsx' --include='*.tsx' . \
  | sed -E 's/^class="//; s/"$//' | tr ' ' '\n' | grep -vE '^$' \
  | sort | uniq -c | sort -rn
```

```text
   4 rounded-md
   3 p-4
   2 p-2
   2 bg-surface
   2 bg-accent
   1 text-white
   1 rounded-lg
   1 gap-2
   1 bg-bg
```

For JSX, extend the `class="` pattern to `className=` and to template literals
before trusting the counts; the form above misses `className={clsx(...)}`.

**Dimensions with frequency, one scan per property family.** A single scan over
every length in the tree is not usable, because a length carries no meaning
without the property it was written for. Scanning the fixture that way returns:

```text
   4 8px
   2 4px
   2 16px
   2 12px
   1 9999px
   1 20px
   1 1px
   1 17px
   1 15px
```

Every entry there is ambiguous. `20px` is a `font-size` and belongs to no spacing
ladder; `9999px` is a pill and `1px` a hairline border; and the top entry, `8px`
at four uses, is three radius declarations plus one `--space-2` token — one
number standing for two unrelated decisions. Ranked as a spacing list
(§C.2) and collapsed as one (§C.3), that produces a spacing step nothing uses and
a type size that disappears from the file.

Scan by family instead:

```bash
cd /ABS/PATH/repo
BOX='(^|[^a-z-])(padding|margin|gap|row-gap|column-gap|inset|--space[a-z0-9_-]*|--gap[a-z0-9_-]*)[a-z-]*[[:space:]]*:[^;{}]*'
TYPE='(^|[^a-z-])(font-size|line-height|letter-spacing|--font-size[a-z0-9_-]*|--leading[a-z0-9_-]*)[a-z-]*[[:space:]]*:[^;{}]*'
RADIUS='(^|[^a-z-])(border[a-z-]*radius|--radius[a-z0-9_-]*|--rounded[a-z0-9_-]*)[a-z-]*[[:space:]]*:[^;{}]*'
dims() { grep -rhoE "$1" --include='*.css' . \
  | grep -oE '[0-9]+(\.[0-9]+)?(px|rem|em)' | sort | uniq -c | sort -rn; }
echo "box metrics:";  dims "$BOX"
echo "type metrics:"; dims "$TYPE"
echo "radius:";       dims "$RADIUS"
```

```text
box metrics:
   2 16px
   1 8px
   1 4px
   1 17px
   1 15px
   1 12px
type metrics:
   1 20px
radius:
   3 8px
   1 9999px
   1 4px
   1 12px
```

Box metrics feed `spacing`, type metrics feed `typography`, radius feeds
`rounded`. The three lists are read separately and never merged: `8px` is a
radius three times and a spacing token once, and those are two facts, not one
count of four. `1px` is now absent from all three, because a `border` shorthand
is none of these families — which is the correct answer, not a gap.

The `[^;{}]*` tail stops each match at the end of its own declaration, so
`padding:12px 16px; font-size:14px` contributes `12px` and `16px` to box metrics
and `14px` to type metrics. Two limits are worth stating in the hand-back: the
`font` and `border` shorthands are not decomposed, and a value reached only
through `var()` is counted where the custom property was *declared*, not at each
use site.

Custom properties whose name does not carry a family — `--gutter`, `--x` — are
matched by none of the three. List them with the name intact and assign each by
hand:

```bash
cd /ABS/PATH/repo && grep -rhoE '(^|[{;])[[:space:]]*--[A-Za-z0-9_-]+[[:space:]]*:[^;{}]*' \
  --include='*.css' . | sed -E 's/^[[:space:]{;]*//; s/[[:space:]]+$//' \
  | grep -E '[0-9](\.[0-9]+)?(px|rem|em)' | sort | uniq -c | sort -rn
```

```text
   2 --radius-md: 8px
   1 --space-4: 16px
   1 --space-3: 12px
   1 --space-2: 8px
   1 --space-1: 4px
   1 --radius-sm: 4px
   1 --radius-lg: 12px
```

The scan lists every custom property that carries a length, not only the
unfamilied ones, so read it for the names the three family patterns missed. On
this fixture all seven carry a family and none needed hand assignment; on a tree
holding `--gutter: 16px` and `--radius: 8px` the first is the line to assign.

Every list above mixes units where the codebase does; keep `px` and `rem` apart,
because the ratio between them depends on the root size.

### C.2 Rank by frequency

Sort every harvested list by count, descending. Frequency is the only signal in
a codebase that separates a decision from an accident.

1. **A value used once is probably not a token.** `#7c3aed` at one occurrence,
   in a palette otherwise built on `#3b82f6`, is a leftover or a one-off, not a
   second accent. Exclude it from the frontmatter and, if it matters, name it in
   body prose.
2. **The top neutral by count is the ground.** In the sample above, `#0e1116`
   and `#161b22` are the two surface levels and `#3b82f6` — high chroma, high
   count because it is on every button — is the accent. Count alone does not
   settle role; combine it with where the value appears, as in B.2.
3. **Set a threshold and state it.** A workable default: keep a value that
   occurs three or more times, or that is bound to a named custom property and
   referenced at least once. Report the threshold in the hand-back so the user
   can move it.
4. **Exclude the mechanical values.** `#fff` and `#000` at low counts are
   usually resets. `9999px` is a pill, not a radius step. `1px` is a hairline
   border, not a spacing step.
5. **Check every surviving hex against the framework-defaults table before it
   enters the frontmatter.** A copied default is usually the *most* frequent hex
   in a tree — it arrived as a framework's own value and got used everywhere —
   so ranking by count promotes it first. Frequency establishes that a value was
   used, never that it was chosen. Run the AS-10 alternation from
   `references/anti-slop.md` over the harvest:

   ```bash
   cd /ABS/PATH/repo && grep -rhoE '#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{3}\b' \
     --include='*.css' --include='*.scss' --include='*.js' --include='*.ts' --include='*.tsx' . \
     | tr 'A-F' 'a-f' | sort | uniq -c | sort -rn \
     | grep -E '#(3b82f6|2563eb|1d4ed8|6366f1|4f46e5|8b5cf6|7c3aed|a855f7|ef4444|dc2626|10b981|059669|22c55e|16a34a|f59e0b|d97706|0ea5e9|14b8a6|f97316|f43f5e|ec4899|06b6d4|84cc16|eab308|d946ef|f8fafc|f1f5f9|e2e8f0|cbd5e1|94a3b8|64748b|475569|334155|1e293b|0f172a|020617|f9fafb|f3f4f6|e5e7eb|d1d5db|9ca3af|6b7280|4b5563|374151|1f2937|111827|030712|71717a|737373|78716c|fafafa|0d6efd|6610f2|6f42c1|d63384|dc3545|fd7e14|ffc107|198754|20c997|0dcaf0|f8f9fa|e9ecef|dee2e6|ced4da|adb5bd|6c757d|495057|343a40|212529|6200ee|018786|b00020|3f51b5|2196f3|9c27b0|009688|f44336)\b'
   ```

   ```text
      4 #3b82f6
      1 #7c3aed
   ```

   `#3b82f6` is Tailwind blue-500, and on this fixture it is the top-count hex —
   the value the threshold in rule 3 would have promoted to `primary`. Do not
   silently keep it and do not silently substitute one. Carry it into the file as
   measured, name it in the hand-back as a framework default with its count, and
   ask for a brand value. `references/anti-slop.md` §AS-10 holds the full table,
   the sources each hex was read from, and the contrast measurements.

### C.3 Collapse near values into steps, and report the collapse

A codebase accumulates 15px, 16px, and 17px where one step was intended. The
DESIGN.md gets one step. The user is told which values were folded into it.

**A collapse never crosses a property family.** Run this once per family, on the
family's own harvest from C.1 — never on the whole-tree dimension list. Two
lengths that round to the same step are the same step only if they answer the
same question; a `font-size` and a `padding` that both round to 16px are two
decisions, and folding them produces a spacing step nothing uses and a type size
that has vanished. The block below re-declares `BOX` so it stands alone; swap in
`TYPE` or `RADIUS` and re-run for those families.

```bash
cd /ABS/PATH/repo
BOX='(^|[^a-z-])(padding|margin|gap|row-gap|column-gap|inset|--space[a-z0-9_-]*|--gap[a-z0-9_-]*)[a-z-]*[[:space:]]*:[^;{}]*'
grep -rhoE "$BOX" --include='*.css' . \
  | grep -oE '[0-9]+(\.[0-9]+)?px' | grep -oE '[0-9]+(\.[0-9]+)?' | sort -n | uniq -c \
  | awk -v base=4 '$2 >= 2 && $2 <= 128 {
      step = int(($2 / base) + 0.5) * base
      raw[step] = raw[step] sprintf(" %spx(x%s)", $2, $1)
      tot[step] += $1
    }
    END { for (s in tot) printf "%s\t%s\t%s\n", s, tot[s], raw[s] }' \
  | sort -n | awk -F'\t' '{printf "step %-6s used %-3s from%s\n", $1 "px", $2, $3}'
```

```text
step 4px    used 1   from 4px(x1)
step 8px    used 1   from 8px(x1)
step 12px   used 1   from 12px(x1)
step 16px   used 4   from 15px(x1) 16px(x2) 17px(x1)
```

That is the spacing ladder: 4, 8, 12, 16 on a base of 4, with one collapse to
report. Run over every length in the tree instead and the same command adds a
`step 20px` — the `.old-panel h2` font size — and inflates `step 8px` from one
use to four by counting three radius declarations as spacing.

The `>= 2` guard drops hairline borders; the `<= 128` guard drops pill radii and
container widths. Set `base` from the data — the greatest common divisor of the
high-count values — not from habit.

Every line whose `from` column lists more than one raw value is a collapse.
Report all of them. Silent rounding is the failure mode here: the user cannot
tell whether 15px was a bug you fixed or a deliberate optical adjustment you
destroyed, and only they know which.

Report collapses in this form:

```text
COLLAPSED — the codebase used several values where the system has one step:
  spacing.md = 16px   <- 15px (1 use), 16px (2 uses), 17px (1 use)
  <further collapses>
Each is a rounding decision I made. Reverse any that was deliberate.

DROPPED — below the frequency threshold of 3, or mechanical:
  #7c3aed (1 use), #fff (1 use, reset), 9999px (1 use, pill), 1px (1 use, border)

DEAD — declared and never referenced in the grepped tree:
  --dead-token, --radius-sm, --radius-lg, --space-1, --space-3

INFERRED — not in the codebase; I decided it:
  - Spacing base unit <N>px, from the GCD of the high-count box metrics.
  - Modular scale ratio ~<R>, fitted to the <k> surviving type sizes.
  - MD3 role names: the codebase's <bg>/<surface>/<accent> became
    background/surface/primary. The codebase asserted no roles.
  - Frequency threshold <T>, and the <=128px / >=2px guards on the ladder.
  - <#hex> is a framework default (<name>, <n> uses), carried as measured. It
    is not a brand decision; confirm or replace it.
  - Every word of the body prose. A codebase carries values and no rationale.
```

`INFERRED` is not a courtesy. A codebase route hands back a file whose numbers
are all harvested, which makes the decisions around them — the base unit, the
ratio, the role names, the threshold — read as harvested too. Listed flat with
the measured values, an inferred number is indistinguishable from one that was
counted, which is the same failure B.5 exists to prevent on the screenshot route.

Do the same for colors: near hexes within a couple of units per channel are one
token. Do the same for type sizes: fold to the nearest step of the modular scale
implied by the high-count sizes, and report the ratio you settled on.

### C.4 Author the file

1. Write the frontmatter from the surviving, collapsed values.
2. Name colors in the MD3 family vocabulary (A.3), regardless of what the
   codebase called them. The codebase's `bg` / `surface` / `accent` becomes
   `background` / `surface` / `primary`.
3. Define `components` only for controls that exist in the codebase.
4. Put everything the codebase did not settle into `omitted` with a reason.
5. Write all eight body sections in canonical order. The codebase supplies
   values; the rationale is yours, and it must be written, not left as the
   template's.

### C.5 Verify the round trip

`export` runs the file back out to the format the codebase came from. Comparing
the two directions is the only mechanical check that the extraction did not lose
or invent values.

```bash
cd /tmp && npx --yes @google/design.md@0.4.0 export /ABS/PATH/DESIGN.md \
  --format json-tailwind > /ABS/PATH/roundtrip.json
```

`--format` is required for `export`. The five accepted values are
`css-tailwind` (Tailwind v4 `@theme`), `json-tailwind` (Tailwind v3
`theme.extend`), `tailwind` (an alias for `json-tailwind`), `dtcg`, and
`css-vars`. Match the format to the codebase you harvested: a v3 config takes
`json-tailwind`, a v4 `@theme` block takes `css-tailwind`, plain custom
properties take `css-vars`.

Compare the exported value set against the original config:

```bash
node --input-type=module -e '
const [cfgPath, expPath] = process.argv.slice(1);
const fs = await import("node:fs");
const m = await import(cfgPath);
const cfg = m.default ?? m;
const exp = JSON.parse(fs.readFileSync(expPath, "utf8"));
const leaves = (o, acc = new Set()) => {
  for (const v of Object.values(o ?? {}))
    if (v && typeof v === "object") leaves(v, acc);
    else if (typeof v === "string") acc.add(v.toLowerCase());
  return acc;
};
const a = leaves(cfg.theme?.extend ?? cfg.theme);
const b = leaves(exp.theme.extend);
const only = (x, y) => [...x].filter((v) => !y.has(v)).sort();
console.log("only in config   :", only(a, b).join(" ") || "(none)");
console.log("only in DESIGN.md:", only(b, a).join(" ") || "(none)");
' /ABS/PATH/tailwind.config.js /ABS/PATH/roundtrip.json
```

```text
only in config   : sans-serif system-ui
only in DESIGN.md: #1c222b #8b949e #e6edf3 #f85149 #ffffff 400
```

Read both directions:

- **Only in config** is what the extraction dropped. Here it is the font stack
  fallbacks, which DESIGN.md's `fontFamily` does not carry — expected. Anything
  else in this column is a value you lost; either restore it or say why it was
  dropped, per C.3.
- **Only in DESIGN.md** is what the extraction added. Here they are the four
  colors harvested from raw CSS custom properties that never reached the
  Tailwind config, `#ffffff` from the `text-white` utility in the markup, and
  the `fontWeight`. Expected for this input. A value in this column that came
  from nowhere in the codebase is an invention; remove it.

Two known lossy points, verified on this host: a unitless `lineHeight` is
dropped by both `css-tailwind` and `json-tailwind`, so the exported
`fontSize` tuple carries `fontWeight` but no line height. Do not claim
round-trip fidelity for line height. And `css-vars` emits radii as
`--rounded-*` while `css-tailwind` emits `--radius-*`; a comparison across
those two formats must normalise the prefix first.

**Regression check across revisions.** `diff` compares two DESIGN.md files and
exits 1 when the later file lints worse than the earlier one.

```bash
cd /tmp && npx --yes @google/design.md@0.4.0 diff /ABS/PATH/DESIGN.prev.md /ABS/PATH/DESIGN.md
```

A benign revision — two tokens added, no new findings — exits 0. The `findings`
half of the output, verbatim:

```text
  "findings": {
    "before": {
      "errors": 0,
      "warnings": 0,
      "infos": 2
    },
    "after": {
      "errors": 0,
      "warnings": 0,
      "infos": 2
    },
    "delta": {
      "errors": 0,
      "warnings": 0
    }
  },
  "regression": false
}
```

Renaming `primary` to `brand` in the same file trips `missing-primary` and
exits 1:

```text
  "findings": {
    "before": {
      "errors": 0,
      "warnings": 0,
      "infos": 2
    },
    "after": {
      "errors": 0,
      "warnings": 1,
      "infos": 2
    },
    "delta": {
      "errors": 0,
      "warnings": 1
    }
  },
  "regression": true
}
```

`regression` is true when the later file has more errors **or** more warnings
than the earlier one. A revision that fixes findings exits 0. The `tokens`
object in the same output lists `added` / `removed` / `modified` per category,
which is the changelog for the revision; `modified` is computed by comparing
serialised resolved values, so a reformatted-but-equal value does not appear.

### C.6 Lint and fix

Go to §4.

C.5 is a value check, not a validity check, so it does not stand in for the
lint step. `export` exits 0 and emits tokens from a file that still carries a
`broken-ref` error — verified: a file whose component references `{rounded.xl}`
with no `rounded.xl` defined lints at exit 1 and exports at exit 0. `diff`
likewise compares two files without requiring either to be clean. Procedure C
has not completed until §4 reports zero errors.

---

## 4. Mandatory final step — lint, fix, re-run

This step is not optional and not conditional. **A procedure that ends without a
clean lint run has not completed.** An unlinted DESIGN.md is a draft, and
handing one back as finished is the failure this skill exists to prevent.

1. **Run the linter.**

   ```bash
   scripts/lint /ABS/PATH/DESIGN.md
   ```

   The direct equivalent, if the wrapper is unavailable:

   ```bash
   cd /tmp && npx --yes @google/design.md@0.4.0 lint /ABS/PATH/DESIGN.md
   ```

   The wrapper prints a severity/rule/path/message table and a remedy list; add
   `--json` to get the upstream JSON on stdout verbatim, and `--strict` to fail
   on warnings as well as errors. `--format` belongs to the npx form only — the
   wrapper rejects it with a usage error and exit 2. On the npx form,
   `--format markdown` gives a report to paste into a hand-back, and
   `--format text` is accepted by the parser but silently returns JSON; only
   `markdown` and `md` change the output.

2. **Read the exit code.** `0` means zero errors. `1` means one or more errors.
   `2` means the file could not be read — a wrong path, not a design problem.
   Fix the path and run again. The wrapper adds `3`: npx or the design.md CLI
   was unavailable or returned something that is not JSON. That is a toolchain
   failure, and a run that ends on `3` has not linted anything.

3. **Fix every finding, not only the errors.** Errors block; warnings are where
   the real defects are. The common ones and their fixes:

   | Rule | Severity | Fix |
   | :--- | :--- | :--- |
   | `broken-ref` | error | The `{path}` resolves to nothing. Define the token or correct the path. |
   | `broken-ref` | warning | An unrecognised component sub-token. The closed set is `backgroundColor`, `textColor`, `typography`, `rounded`, `padding`, `size`, `height`, `width`. There is no sub-token for elevation or border color; move it to body prose. |
   | `contrast-ratio` | warning | A component pair is below 4.5:1. Change one of the two colors. Do not silence it by deleting `textColor`. |
   | `orphaned-tokens` | warning | A color is neither MD3-family-named nor referenced by a component. Rename it to the MD3 family, or reference it, or delete it. |
   | `missing-primary` | warning | `colors` has no `primary` key. Name the accent `primary`. |
   | `missing-typography` | warning | `colors` is populated and `typography` is empty. Define type or declare `typography` in `omitted`. |
   | `section-order` | warning | Reorder the H2 headings to the canonical sequence. |
   | `unknown-key` | warning | A top-level key close to a schema key, such as `colours`. Rename it. |
   | `token-like-ignored` | warning | A custom top-level key holding tokens. Export commands ignore it. Move its values under a schema key. |
   | `redundant-omission` | warning | A section is both declared in `omitted` and populated. Remove one. |
   | `unknown-omission` | warning | An `omitted` entry outside `colors`, `typography`, `spacing`, `rounded`, `components`. Move it to body prose. |
   | `declared-omission` | info | The intended state. No action. |
   | `missing-sections` | info | `spacing` or `rounded` is empty. Populate it or declare it in `omitted`. |
   | `token-summary` | info | The token census. Read it as a sanity check on the counts, then leave it. |

4. **Re-run after every fix round.** Two rules make a single pass insufficient.
   `section-order` reports at most one finding and stops at the first
   out-of-order pair, so the next one only appears after the first is fixed.
   `orphaned-tokens` returns nothing at all while `components` is empty, so
   adding the first component can surface a warning per poetically named color.

5. **Repeat until the run is clean**, then quote the final output verbatim in
   the hand-back. A clean run on a file authored by these procedures looks like
   this under `scripts/lint --json`, which is byte-for-byte what the npx form
   prints:

   ```text
   {
     "findings": [
       {
         "severity": "info",
         "message": "Design system defines 8 colors, 1 typography scale, 3 rounding levels, 3 spacing tokens.",
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

### What a clean lint does not mean

The linter checks form. It does not check quality. A file can report
`0 errors, 0 warnings` and still be the default design the format exists to
escape. The following are not checked by any rule, and the agent is responsible
for them:

- Whether the type sizes form a modular scale or an arbitrary list.
- Whether the neutrals share a hue direction or are unrelated greys.
- Whether every element uses the same radius.
- Whether `fontFamily` is `system-ui`.
- Whether the values were copied from a well-known default palette.
- Whether the accent is used in more than one role.
- Whether `Do's and Don'ts` says anything specific to this product.
- Whether the body prose contradicts the frontmatter — the linter reads H2
  headings for ordering and nothing else of the body.
- Whether all eight canonical sections are present. No rule requires them; the
  upstream reference example lints clean with seven. Completeness is a house
  rule of this skill, enforced by the author, not by the tool.

Check those against `references/anti-slop.md` before handing the file back. That
check is part of the procedure, not an optional extra.

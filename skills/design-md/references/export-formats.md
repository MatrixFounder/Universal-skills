# `export` and `diff`

Reference for the two DESIGN.md commands that read a finished file: `export`,
which emits the frontmatter tokens in five other formats, and `diff`, which
compares two revisions of a file and reports whether the later one lints worse.

Every command below was run against `@google/design.md@0.4.0` on this host. All
quoted output is verbatim. Samples are trimmed by whole lines where marked;
nothing is reworded.

Companion references: `spec-anatomy.md` (the frontmatter schema these formats
read), `linter-rules.md` (the eleven rules whose counts `diff` compares),
`extraction.md` (§C.5 calls the round-trip recipe in §5 below), `anti-slop.md`.

Invocation used throughout:

```
cd /tmp && npx --yes @google/design.md@0.4.0 <cmd> <ABSOLUTE-PATH>
```

`cd /tmp` first: a workspace elsewhere shadows the bin name. Pass absolute
paths. The first `npx` run takes about 30 seconds while the package is fetched.
The sample file in every `export` example is
`skills/design-md/examples/fixture-clean.md`.

---

## 1. `export` in one paragraph

`export` reads the YAML frontmatter and writes the tokens out in another
format. The markdown body contributes nothing: two files with identical
frontmatter and completely different bodies exported byte-identical `dtcg`
output. The one non-token frontmatter field that reaches an export is
`description`, which `dtcg` emits as `$description`. `--format` is required;
there is no default.

Two properties matter before you use it for anything:

1. **`export` is not a validation step.** It does not run the linter and does
   not fail on a file the linter rejects. `examples/fixture-broken.md` lints at
   `{"errors": 1, "warnings": 6, "infos": 1}` and exits 1, and the same file
   exports at exit 0. Lint first, export second.
2. **`components` is exported by no format.** All five formats carry
   `colors`, `typography`, `rounded`, and `spacing`. The component map — the
   part of a DESIGN.md that says which token plays which role — is dropped by
   every one of them. Anything downstream that needs component bindings reads
   the DESIGN.md itself.

### 1.1 Exit codes (measured)

| Condition | Exit |
| :--- | :--- |
| Export succeeded | 0 |
| `--format` omitted | 1 (help text + `ERROR  Missing required argument: --format`) |
| `--format` not one of the five | 1 |
| File not found | 2 |

An invalid format value is reported as a JSON error envelope on **stderr**;
stdout stays empty:

```text
{"error":"INVALID_FORMAT","message":"Invalid format \"scss\". Valid formats: css-tailwind, json-tailwind, tailwind, dtcg, css-vars"}
```

### 1.2 Coverage matrix (measured, per source property)

| Source | `css-tailwind` | `json-tailwind` / `tailwind` | `dtcg` | `css-vars` |
| :--- | :--- | :--- | :--- | :--- |
| `colors.<tok>` | `--color-<tok>` | `colors.<tok>` | `color.<tok>.$value` | `--color-<tok>` |
| `typography.<t>.fontFamily` | `--font-<t>` | `fontFamily.<t>` (array) | `typography.<t>.$value.fontFamily` | — |
| `…fontSize` | `--text-<t>` | `fontSize.<t>[0]` | `…$value.fontSize` | — |
| `…fontWeight` | `--font-weight-<t>` | `fontSize.<t>[1].fontWeight` | `…$value.fontWeight` | — |
| `…lineHeight` (with unit) | `--leading-<t>` | `fontSize.<t>[1].lineHeight` | `…$value.lineHeight` (unit stripped) | — |
| `…lineHeight` (unitless) | **dropped** | **dropped** | **dropped** | — |
| `…letterSpacing` | `--tracking-<t>` | `fontSize.<t>[1].letterSpacing` | `…$value.letterSpacing` | — |
| `…fontFeature` | **dropped** | **dropped** | **dropped** | — |
| `…fontVariation` | **dropped** | **dropped** | **dropped** | — |
| `rounded.<s>` | `--radius-<s>` | `borderRadius.<s>` | `rounded.<s>.$value` | `--rounded-<s>` |
| `spacing.<s>` | `--spacing-<s>` | `spacing.<s>` | `spacing.<s>.$value` | `--spacing-<s>` |
| `components.<c>` | — | — | — | — |

Read the two divergences off that table before §4 explains them: `rounded`
becomes `--radius-*` in Tailwind v4 output and `--rounded-*` in plain CSS
output, and `css-vars` carries no typography at all.

---

## 2. The five formats

### 2.1 `css-tailwind` — Tailwind v4 `@theme`

Emits a single `@theme { … }` block of CSS custom properties using Tailwind
v4's namespace prefixes (`--color-`, `--font-`, `--text-`, `--font-weight-`,
`--leading-`, `--tracking-`, `--radius-`, `--spacing-`). Tailwind v4 derives
utility classes from those namespaces, so `--color-primary` produces
`bg-primary` / `text-primary` and `--radius-md` produces `rounded-md`.

```
cd /tmp && npx --yes @google/design.md@0.4.0 export \
  /ABS/PATH/examples/fixture-clean.md --format css-tailwind
```

```text
@theme {
  --color-primary: #1b4d3e;
  --color-on-primary: #ffffff;
  --color-surface: #fcfbf7;
  --color-on-surface: #14181c;
  --color-outline: #c6c2b6;
  --font-body-md: "Inter";
  --font-label-lg: "Inter";
  --text-body-md: 16px;
  --text-label-lg: 14px;
  --tracking-label-lg: 0.01em;
  --font-weight-body-md: 400;
  --font-weight-label-lg: 600;
  --radius-sm: 4px;
  --radius-md: 8px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
}
```

Verified properties of that output: hex colors are lowercased; `fontFamily`
keeps its quotes and is emitted as a bare family name with no fallback stack;
declarations are grouped by category, not interleaved per token; `--prefix` is
ignored.

**Choose it when** the target project is Tailwind v4 (no `tailwind.config.js`,
theme declared in CSS). Paste the block into the project's entry stylesheet
after `@import "tailwindcss";`.

### 2.2 `json-tailwind` — Tailwind v3 `theme.extend`

Emits a JSON object shaped for a v3 config's `theme.extend`. Typography is
folded into Tailwind v3's `fontSize` tuple form: `[size, { …modifiers }]`.

```
cd /tmp && npx --yes @google/design.md@0.4.0 export \
  /ABS/PATH/examples/fixture-clean.md --format json-tailwind
```

```text
{
  "theme": {
    "extend": {
      "colors": {
        "primary": "#1b4d3e",
        "on-primary": "#ffffff",
        "surface": "#fcfbf7",
        "on-surface": "#14181c",
        "outline": "#c6c2b6"
      },
      "fontFamily": {
        "body-md": [
          "Inter"
        ],
        "label-lg": [
          "Inter"
        ]
      },
      "fontSize": {
        "body-md": [
          "16px",
          {
            "fontWeight": "400"
          }
        ],
        "label-lg": [
          "14px",
          {
            "letterSpacing": "0.01em",
            "fontWeight": "600"
          }
        ]
      },
      "borderRadius": {
        "sm": "4px",
        "md": "8px"
      },
      "spacing": {
        "sm": "8px",
        "md": "16px"
      }
    }
  }
}
```

Verified properties: the five keys `colors`, `fontFamily`, `fontSize`,
`borderRadius`, `spacing` are **always present**, emitted as `{}` when the
corresponding source map is empty; `fontFamily` values are one-element arrays,
so a fallback stack has to be appended by hand; `fontWeight` becomes a
**string** (`"400"`, not `400`).

**Choose it when** the target project has a `tailwind.config.js`/`.ts`, and for
the round-trip check in §5 — JSON is the only export shape that a comparator
can walk mechanically without a CSS parser.

### 2.3 `tailwind` — alias for `json-tailwind`

Accepted as a distinct `--format` value. Output is byte-identical to
`json-tailwind` on the same input; the two were run back to back on
`fixture-clean.md` and `cmp` reported no difference across all 44 lines.

**Choose it** never, in a script. Write `json-tailwind` so the version of
Tailwind being targeted is legible at the call site. `tailwind` is documented
here only so an agent reading someone else's command line knows what it is.

### 2.4 `dtcg` — W3C Design Tokens Format Module

Emits the interoperable token format consumed by Style Dictionary, Tokens
Studio, and similar pipelines. Colors carry both a normalized sRGB component
triple and the hex; dimensions carry a split `{value, unit}` object.

```
cd /tmp && npx --yes @google/design.md@0.4.0 export \
  /ABS/PATH/examples/fixture-clean.md --format dtcg
```

Trimmed to one token per group; the omitted tokens repeat the shape exactly.

```text
{
  "$schema": "https://www.designtokens.org/schemas/2025.10/format.json",
  "$description": "Known-good control file for the design-md skill's lint wrapper.",
  "color": {
    "$type": "color",
    "primary": {
      "$value": {
        "colorSpace": "srgb",
        "components": [
          0.106,
          0.302,
          0.243
        ],
        "hex": "#1b4d3e"
      }
    }
  },
  "spacing": {
    "$type": "dimension",
    "md": {
      "$value": {
        "value": 16,
        "unit": "px"
      }
    }
  },
  "rounded": {
    "$type": "dimension",
    "md": {
      "$value": {
        "value": 8,
        "unit": "px"
      }
    }
  },
  "typography": {
    "label-lg": {
      "$type": "typography",
      "$value": {
        "fontFamily": "Inter",
        "fontSize": {
          "value": 14,
          "unit": "px"
        },
        "fontWeight": 600,
        "letterSpacing": {
          "value": 0.01,
          "unit": "em"
        }
      }
    }
  }
}
```

Verified properties:

- `$schema` is pinned to `https://www.designtokens.org/schemas/2025.10/format.json`.
- `$description` is the frontmatter `description`. When `description` is
  absent it falls back to `name` — a probe file with `name: LH Unitless` and no
  `description` emitted `"$description": "LH Unitless"`.
- Group names are `color`, `spacing`, `rounded`, `typography`. Note `rounded`,
  not the DTCG-conventional `borderRadius`, and singular `color`.
- `components[]` are floats rounded to 3 decimal places.
- `fontWeight` is a **number** here (`600`), unlike the string in
  `json-tailwind`.
- A `lineHeight` given with a unit loses the unit: `lineHeight: 24px` exported
  as `"lineHeight": 24`, a bare number, while `fontSize` next to it kept its
  `{value, unit}` shape. Do not feed that value to a consumer that assumes
  `px` — check it.
- Groups whose source map is empty are omitted entirely, unlike
  `json-tailwind`.

**Choose it when** the tokens feed a build pipeline rather than one CSS
framework, or when several frameworks consume the same system.

### 2.5 `css-vars` — plain CSS custom properties

Emits a `:root { … }` block with no framework assumptions.

```
cd /tmp && npx --yes @google/design.md@0.4.0 export \
  /ABS/PATH/examples/fixture-clean.md --format css-vars
```

```text
:root {
  --color-primary: #1b4d3e;
  --color-on-primary: #ffffff;
  --color-surface: #fcfbf7;
  --color-on-surface: #14181c;
  --color-outline: #c6c2b6;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --rounded-sm: 4px;
  --rounded-md: 8px;
}
```

**`css-vars` carries colors, spacing, and rounded only.** Typography is dropped
in full — family, size, weight, line height, tracking. The same input that gave
`css-tailwind` seven typography declarations gives `css-vars` none. A
typography-only file exports as an empty block:

```text
:root {
}
```

If a project needs type tokens as plain custom properties, write them by hand
from the `css-tailwind` output; there is no flag that adds them.

`--prefix` inserts a segment after the leading `--`, applied to every variable:

```
cd /tmp && npx --yes @google/design.md@0.4.0 export \
  /ABS/PATH/examples/fixture-clean.md --format css-vars --prefix ds
```

```text
:root {
  --ds-color-primary: #1b4d3e;
  --ds-color-on-primary: #ffffff;
  --ds-color-surface: #fcfbf7;
  --ds-color-on-surface: #14181c;
  --ds-color-outline: #c6c2b6;
  --ds-spacing-sm: 8px;
  --ds-spacing-md: 16px;
  --ds-rounded-sm: 4px;
  --ds-rounded-md: 8px;
}
```

`--prefix` affects `css-vars` only. Passing it to `css-tailwind`,
`json-tailwind`, or `dtcg` is accepted, exits 0, and changes nothing in the
output — verified on all three.

**Choose it when** the consumer is vanilla CSS, a non-Tailwind framework, or a
web component that must not inherit a framework's naming, and when the design
system is color- and metric-only. Use `--prefix` when the variables land in a
page that already defines custom properties.

---

## 3. Choosing a format

| The target is… | Use |
| :--- | :--- |
| Tailwind v4 — theme in CSS, no config file | `css-tailwind` |
| Tailwind v3 — `tailwind.config.js` / `.ts` | `json-tailwind` |
| A round-trip comparison against a codebase (§5) | `json-tailwind` |
| Style Dictionary, Tokens Studio, a multi-framework build | `dtcg` |
| Vanilla CSS, a web component, a non-Tailwind framework | `css-vars` |
| Anything, when the file also needs component bindings | none of them — read the DESIGN.md |

Two constraints override the table:

- If the system's value is in its **typography**, do not pick `css-vars`; it
  drops every type token.
- If any `lineHeight` is unitless, no format carries it. See §4.2.

---

## 4. Two naming divergences to check before you paste

### 4.1 `--radius-*` versus `--rounded-*`

The same `rounded` map exports under two different variable prefixes depending
on the format. Both commands were run on `fixture-clean.md`, whose frontmatter
declares `rounded: {sm: 4px, md: 8px}`:

```text
# --format css-tailwind
  --radius-sm: 4px;
  --radius-md: 8px;

# --format css-vars
  --rounded-sm: 4px;
  --rounded-md: 8px;
```

`css-tailwind` uses `--radius-` because that is the namespace Tailwind v4 reads
to generate `rounded-*` utilities. `css-vars` uses `--rounded-`, mirroring the
DESIGN.md key name.

Consequences:

1. A stylesheet written against `--rounded-md` breaks silently if the export
   format is later switched to `css-tailwind`. A missing custom property is not
   a CSS error — the declaration is dropped and the element renders unrounded.
2. Any text comparison between a `css-tailwind` export and a `css-vars` export
   must normalize the prefix first, or every radius shows as both added and
   removed. Normalize in one direction. `css-vars` indents every declaration
   by two spaces, so anchor the pattern on the `--`, not on the start of the
   line:

   ```bash
   sed 's/--rounded-/--radius-/' vars.css > vars.normalized.css
   ```

   The line-anchored form `sed 's/^--rounded-/--radius-/'` matches nothing and
   returns the file unchanged. Verified on a real `css-vars` export.

`spacing` and `colors` use the same `--spacing-` / `--color-` prefix in both
formats; `rounded` is the only divergence.

### 4.2 A unitless `lineHeight` does not survive export

`spec-anatomy.md` §5.1 recommends a unitless `lineHeight` (`1.5`), because it
is a multiplier and is the correct CSS practice. That recommendation has a
measured cost: **no export format carries it.**

Probe files, identical apart from one line:

```text
# lineHeight: 1.5   -> css-tailwind
@theme {
  --font-body-md: "Inter";
  --text-body-md: 16px;
}

# lineHeight: 24px  -> css-tailwind
@theme {
  --font-body-md: "Inter";
  --text-body-md: 16px;
  --leading-body-md: 24px;
}
```

The same split appears in `json-tailwind` — `"body-md": ["16px", {}]` for the
unitless file against `"body-md": ["16px", {"lineHeight": "24px"}]` for the
dimension file — and in `dtcg`, where the unitless value is absent from
`$value` entirely.

This is not a lint error and there is no warning. The value is simply gone.

What to do about it:

- Keep the unitless value in the DESIGN.md. It is the correct authored value
  and the file, not the export, is the design system.
- Do **not** claim round-trip fidelity for line height. A round-trip comparison
  (§5) will always report line height as missing from the export side; that
  delta is expected and is not evidence of a lost token.
- If a downstream consumer needs the line heights, transcribe them by hand from
  the DESIGN.md, or switch the affected tokens to a dimension and accept that
  the multiplier semantics are lost.

`fontFeature` and `fontVariation` are dropped by all three token-carrying
formats too, unitless or not — verified with a probe carrying
`fontFeature: "'ss01' 1, 'tnum' 1"` and `fontVariation: "'wdth' 105"`, neither
of which appeared in `css-tailwind`, `json-tailwind`, or `dtcg` output.

---

## 5. Round-trip verification

This is the recipe `extraction.md` §C.5 refers to. It applies after Procedure C
(extract a DESIGN.md from an existing codebase) and any time a DESIGN.md and a
codebase are supposed to agree.

The idea: `export` runs the DESIGN.md back out into the format the codebase is
written in. Comparing the two sets produces three buckets, and each bucket has
exactly one meaning:

| Bucket | Meaning |
| :--- | :--- |
| In DESIGN.md, absent from the codebase | The DESIGN.md declares something nothing uses — or the export is lossy (§4.2). |
| In the codebase, absent from DESIGN.md | A token the extraction **missed**. Add it, or record in `omitted` why not. |
| In both, values disagree | The codebase is **inconsistent** with its own system, or units differ. Resolve one way. |

### 5.1 Tailwind v3 — `json-tailwind` against a config

Step 1. Export.

```bash
cd /tmp && npx --yes @google/design.md@0.4.0 export \
  /ABS/PATH/DESIGN.md --format json-tailwind > /ABS/PATH/design-theme.json
```

Step 2. Get the project's theme as JSON. A v3 config is JavaScript, so
evaluate it:

```bash
node -e 'console.log(JSON.stringify(require("/ABS/PATH/tailwind.config.js"), null, 2))' \
  > /ABS/PATH/project-theme.json
```

For an ESM config, use `node --input-type=module -e 'const m = await
import("/ABS/PATH/tailwind.config.mjs"); console.log(JSON.stringify(m.default))'`.
If the config is already JSON or a token file, skip this step.

Step 3. Compare. Standard-library `python3`, no dependencies:

```python
#!/usr/bin/env python3
"""Compare two Tailwind theme JSON trees. stdlib only."""
import json, sys

def flatten(node, prefix=""):
    out = {}
    if isinstance(node, dict):
        for k, v in node.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = node
    return out

def load(path):
    d = json.load(open(path, encoding="utf-8"))
    return d.get("theme", {}).get("extend", d)

a, b = flatten(load(sys.argv[1])), flatten(load(sys.argv[2]))
only_a = sorted(set(a) - set(b))
only_b = sorted(set(b) - set(a))
differ = sorted(k for k in set(a) & set(b) if a[k] != b[k])

print("# in DESIGN.md, absent from the codebase")
for k in only_a: print(f"  {k} = {a[k]!r}")
print("# in the codebase, absent from DESIGN.md")
for k in only_b: print(f"  {k} = {b[k]!r}")
print("# present in both, values disagree")
for k in differ: print(f"  {k}: DESIGN.md {a[k]!r} != codebase {b[k]!r}")
sys.exit(1 if (only_a or only_b or differ) else 0)
```

Save it as `theme-delta.py` outside the skill tree and run:

```bash
python3 /ABS/PATH/theme-delta.py /ABS/PATH/design-theme.json /ABS/PATH/project-theme.json
```

Real run. Left side is `examples/fixture-clean.md` exported as
`json-tailwind`; right side is a project config that shares four colors, adds
one of its own, and states two metrics in `rem`:

```text
# in DESIGN.md, absent from the codebase
  colors.on-primary = '#ffffff'
  fontFamily.body-md[0] = 'Inter'
  fontFamily.label-lg[0] = 'Inter'
  fontSize.body-md[0] = '16px'
  fontSize.body-md[1].fontWeight = '400'
  fontSize.label-lg[0] = '14px'
  fontSize.label-lg[1].fontWeight = '600'
  fontSize.label-lg[1].letterSpacing = '0.01em'
# in the codebase, absent from DESIGN.md
  colors.accent = '#b45309'
# present in both, values disagree
  borderRadius.md: DESIGN.md '8px' != codebase '0.5rem'
  spacing.md: DESIGN.md '16px' != codebase '1rem'
```

Exit code 1 (any delta is a non-zero exit, so the script drops into a CI gate
unchanged).

Reading that output, finding by finding:

- `colors.on-primary`, and the whole typography block — the config never
  declares them. Either the codebase hard-codes `#ffffff` and its type styles
  outside Tailwind, or the extraction invented tokens. Check the source before
  deciding which.
- `colors.accent = '#b45309'` — a token the DESIGN.md **missed**. This is the
  bucket that matters most: the codebase uses an accent the design system does
  not know about. Add it, or write it into `omitted` with the reason.
- `borderRadius.md` and `spacing.md` — `8px` versus `0.5rem`, `16px` versus
  `1rem`. Identical at a 16 px root, different as strings. This is a
  **unit-consistency** finding, not a value conflict: pick one unit and state
  it in the DESIGN.md's Layout section.

No `lineHeight` appears anywhere in that output because the fixture's line
heights are unitless. Per §4.2, that absence is expected.

### 5.2 Tailwind v4 — `css-tailwind` against a stylesheet

A v4 project has no config file. Compare the `@theme` declarations as text.

```bash
cd /tmp && npx --yes @google/design.md@0.4.0 export /ABS/PATH/DESIGN.md \
  --format css-tailwind \
  | grep -oE '^\s+--[a-z0-9-]+:.*;' | sed 's/^ *//' | sort > /ABS/PATH/design.vars

grep -oE '^\s+--[a-z0-9-]+:.*;' /ABS/PATH/src/app.css \
  | sed 's/^ *//' | sort > /ABS/PATH/project.vars

diff -u /ABS/PATH/design.vars /ABS/PATH/project.vars
```

Real run, same fixture against a v4 stylesheet. The two `---`/`+++` header
lines carry temp paths and are cut; the hunk is verbatim:

```text
@@ -1,16 +1,9 @@
---color-on-primary: #ffffff;
+--color-accent: #b45309;
 --color-on-surface: #14181c;
 --color-outline: #c6c2b6;
 --color-primary: #1b4d3e;
 --color-surface: #fcfbf7;
---font-body-md: "Inter";
---font-label-lg: "Inter";
---font-weight-body-md: 400;
---font-weight-label-lg: 600;
---radius-md: 8px;
+--radius-md: 0.5rem;
 --radius-sm: 4px;
 --spacing-md: 16px;
 --spacing-sm: 8px;
---text-body-md: 16px;
---text-label-lg: 14px;
---tracking-label-lg: 0.01em;
```

`diff` exits 1. Lines starting `-` are DESIGN.md-only; `+` is codebase-only; a
value change appears as an adjacent `-`/`+` pair (`--radius-md`).

Caveat: this is a string comparison, so it reports `8px` versus `0.5rem` as a
difference and it cannot see a declaration that a later cascade overrides. It
is a first pass, not a proof.

### 5.3 When to run it

- At the end of `extraction.md` Procedure C, before handing the file back.
- Before merging a change to a project's theme config — the deltas name exactly
  what the DESIGN.md has to be updated with.
- On a schedule, if the DESIGN.md is meant to be the source of truth. Growth in
  the "in the codebase, absent from DESIGN.md" bucket over time is the
  measurable form of implementation drift.

---

## 6. `diff` — resolved

The postanovka listed `diff` as an open question (OQ-1): the command is not
described in public documentation, and its behaviour had to be established from
the implementation. **It is settled.** This section is the answer; treat it as
documented behaviour, not as a hypothesis.

```
cd /tmp && npx --yes @google/design.md@0.4.0 diff <BEFORE> <AFTER> [--format markdown]
```

`diff` does **two** independent things in one pass:

1. **Token changelog.** Set comparison of the two files' frontmatter, per
   category.
2. **Findings regression check.** It lints both files and compares the
   summaries. This half decides the exit code.

It is not a text diff. It never reads the markdown body, so a rewritten
Overview section produces an empty `diff`.

### 6.1 Output shape

```
{ "tokens": { "colors"|"typography"|"rounded"|"spacing"|"components":
                { "added": [...], "removed": [...], "modified": [...] } },
  "findings": { "before": {errors, warnings, infos},
                "after":  {errors, warnings, infos},
                "delta":  {errors, warnings} },
  "regression": <bool> }
```

All five token categories are always present, with `[]` for the empty buckets.
`delta` carries `errors` and `warnings` only — there is no `infos` delta.

### 6.2 How `added` / `removed` / `modified` are computed

- `added` — keys in AFTER, not in BEFORE.
- `removed` — keys in BEFORE, not in AFTER.
- `modified` — keys in both, where `JSON.stringify` of the resolved value
  differs. Components are serialized from their property map first
  (`Object.fromEntries(comp.properties)`), then compared the same way.

Two consequences of `JSON.stringify` inequality being the test:

1. **It compares resolved values.** Repointing `button.backgroundColor` from
   `{colors.primary}` to a literal hex equal to `primary` is not a
   modification, because both resolve to the same value.
2. **It is order-sensitive for components.** A component's properties are
   serialized in map order, so reordering `textColor` above `backgroundColor`
   in the YAML can register the component as `modified` with no value change.
   Read `components.modified` as "look at this", not as "this changed".

`8px` and `0.5rem` are different strings and therefore a modification, even
though they compute to the same length. `diff` does not normalize units.

### 6.3 `regression`, and the exit code

`regression` is `true` when

```
after.errors > before.errors  OR  after.warnings > before.warnings
```

and `false` otherwise. Exit code is 1 when `regression` is `true`, 0 when it is
`false`. Infos are ignored entirely: adding a section to `omitted` raises
`infos` and never trips the gate.

**Verified run.** Two revisions of one file were placed side by side. Revision 2
lightens the accent from `#1B4D3E` to `#7FB39C`, adds `outline`, drops
`on-surface`, adds a `label-lg` type scale, changes `rounded.md` from `8px` to
`12px`, and repoints the button at the new type scale with a `padding`. Lint on
each, separately:

| File | `lint` exit | `summary` |
| :--- | :--- | :--- |
| `before.md` | 0 | `{"errors": 0, "warnings": 0, "infos": 1}` |
| `after.md` | 0 | `{"errors": 0, "warnings": 1, "infos": 1}` |

The one new warning is `contrast-ratio`: `textColor (#ffffff) on
backgroundColor (#7fb39c) has contrast ratio 2.38:1, below WCAG AA minimum of
4.5:1.` Note that both files lint at **exit 0** on their own — a warning is not
an error. `diff` is what turns that new warning into a failure.

Forward, `before` → `after`:

```text
{
  "tokens": {
    "colors": {
      "added": [
        "outline"
      ],
      "removed": [
        "on-surface"
      ],
      "modified": [
        "primary"
      ]
    },
    "typography": {
      "added": [
        "label-lg"
      ],
      "removed": [],
      "modified": []
    },
    "rounded": {
      "added": [],
      "removed": [],
      "modified": [
        "md"
      ]
    },
    "spacing": {
      "added": [],
      "removed": [],
      "modified": []
    },
    "components": {
      "added": [],
      "removed": [],
      "modified": [
        "button-primary"
      ]
    }
  },
  "findings": {
    "before": {
      "errors": 0,
      "warnings": 0,
      "infos": 1
    },
    "after": {
      "errors": 0,
      "warnings": 1,
      "infos": 1
    },
    "delta": {
      "errors": 0,
      "warnings": 1
    }
  },
  "regression": true
}
```

Exit code 1.

Now the same two files, arguments swapped — `after` → `before`, i.e. the
revision that *fixes* the contrast failure. `tokens` is trimmed here to the two
categories that change direction; the rest is identical in shape:

```text
    "typography": {
      "added": [],
      "removed": [
        "label-lg"
      ],
      "modified": []
    },
…
  "findings": {
    "before": {
      "errors": 0,
      "warnings": 1,
      "infos": 1
    },
    "after": {
      "errors": 0,
      "warnings": 0,
      "infos": 1
    },
    "delta": {
      "errors": 0,
      "warnings": -1
    }
  },
  "regression": false
}
```

Exit code 0.

**`diff` is a regression gate, not a change detector.** The reverse run above
reports six token changes across four categories and still exits 0, because
`delta.warnings` is `-1`. An agent that treats exit 0 as "nothing changed" will
miss every improvement and every neutral edit. To detect *change*, read
`tokens` and ignore the exit code. To detect *damage*, read the exit code.

`delta` values are signed: `-1` above. A negative delta means the later file
lints better.

### 6.4 `--format markdown` on `diff`

`diff --format markdown` does **not** emit the `# Lint Report` style document
that `lint --format markdown` produces. It emits an indented, YAML-shaped dump
of the same object, in which empty arrays render as an empty value:

```text
tokens:
  colors:
    added:
      - outline
    removed:
      - on-surface
    modified:
      - primary
  typography:
    added:
      - label-lg
    removed:

    modified:

…
findings:
  before:
    errors: 0
    warnings: 0
    infos: 1
  after:
    errors: 0
    warnings: 1
    infos: 1
  delta:
    errors: 0
    warnings: 1
regression: true
```

That output parses as YAML — `yaml.safe_load` on it returns
`{'added': ['label-lg'], 'removed': None, 'modified': None}` for the
`typography` group. Note that empty buckets come back as `None`, not `[]`,
which is a behaviour difference from the JSON form. For anything scripted, use
the JSON output and `json.load`.

### 6.5 The maintenance scenario `diff` exists for

**Keeping a DESIGN.md current across revisions.** When a design system file is
edited, three questions have to be answered, and `diff` answers all three from
one run:

1. What tokens changed? → `tokens`, per category. This is the changelog entry;
   paste it into the commit message.
2. Did the edit make the file worse? → `regression` / exit code.
3. Did the edit fix something? → a negative number in `delta`.

Working sequence for a revision:

```bash
cp /ABS/PATH/DESIGN.md /ABS/PATH/DESIGN.prev.md   # or: git show HEAD:DESIGN.md > …
# …edit DESIGN.md…
cd /tmp && npx --yes @google/design.md@0.4.0 lint /ABS/PATH/DESIGN.md
cd /tmp && npx --yes @google/design.md@0.4.0 diff /ABS/PATH/DESIGN.prev.md /ABS/PATH/DESIGN.md
```

Run `lint` as well as `diff`. `diff` reports only the *count* of findings, never
their text; the contrast failure in §6.3 shows up in `diff` as `warnings: 1` and
nowhere says which component or which ratio. `lint` — or `scripts/lint`, which
prints the finding plus a remedy line — is what names the defect.

**Pre-merge check on the design system file.** The exit-code contract makes
`diff` usable as a gate with no wrapper:

```bash
#!/usr/bin/env bash
# Fail a merge that makes DESIGN.md lint worse than the base revision.
set -euo pipefail
BASE_REF="${1:-origin/main}"
HEAD_FILE="$(git rev-parse --show-toplevel)/DESIGN.md"
git show "$BASE_REF:DESIGN.md" > /tmp/DESIGN.base.md
cd /tmp
npx --yes @google/design.md@0.4.0 diff /tmp/DESIGN.base.md "$HEAD_FILE"
```

Both paths are absolute and the `cd /tmp` stands on its own line, so the
working directory is never load-bearing.

The gate's honest scope, stated so nobody assumes more:

- It fails **only** on a rise in errors or warnings. A branch that deletes half
  the palette, renames every token, and introduces no finding passes.
- It cannot fail on prose. Gutting the Do's and Don'ts section is invisible.
- It compares against whatever `BEFORE` you hand it. Against a stale base, a
  regression introduced two commits ago is already in `before` and no longer
  counts as new.
- Pair it with a plain `lint` gate on an absolute threshold
  (`summary.warnings == 0`), or the ratchet only ever holds the line where it
  was when the gate was added.

---

## 7. Corrections to the upstream help text

Two claims in `--help` do not match 0.4.0's behaviour. Both were verified on
this host. Both are the kind of mismatch that produces a script which appears to
work.

### 7.1 `--format text` on `lint` and `diff` silently returns JSON

`lint --help` and `diff --help` both print:

```text
OPTIONS

  --format="json"    Output format: json or text
```

`text` is not implemented. The formatter branches on `markdown` / `md`;
everything else, `text` included, falls through to JSON. Verified on
`fixture-clean.md`:

```
npx --yes @google/design.md@0.4.0 lint /ABS/PATH/fixture-clean.md --format text
```

```text
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

An unrecognized value behaves identically — `--format wibble` returned the same
JSON, with no error and no warning. There is no validation on this flag, unlike
`export --format`, which rejects an unknown value with `INVALID_FORMAT` and
exit 1.

The alternative that **is** implemented is undocumented. `--format markdown`,
or its alias `--format md`:

```
npx --yes @google/design.md@0.4.0 lint /ABS/PATH/after.md --format markdown
```

```text
# Lint Report

**0 errors**, **1 warnings**, **1 infos**

## Findings

- **warning** `components.button-primary`: textColor (#ffffff) on backgroundColor (#7fb39c) has contrast ratio 2.38:1, below WCAG AA minimum of 4.5:1.
- **info**: Design system defines 4 colors, 2 typography scales, 1 rounding level, 1 spacing token, 1 component.
```

**Why this matters.** An agent that writes `--format text` and then parses the
result with line-splitting and regex is parsing JSON while believing it parsed
text. The parse will not raise — JSON is line-structured enough that naive
patterns match some of it — so the failure surfaces later as wrong findings, or
as no findings at all. Rules:

- For machine consumption, pass nothing and parse JSON, or use `scripts/lint`,
  which does the parsing and adds a remedy line per rule.
- For a human-readable report, pass `--format markdown`. Never `--format text`.
- Never branch on the flag's exit code to detect support; every value exits the
  same way.

### 7.2 The `-` stdin argument does not work

`lint --help` and `export --help` both document the FILE argument as
`Path to DESIGN.md (use "-" for stdin)`. In 0.4.0 the argument parser does not
accept a bare `-`. Every form below was fed a valid file on stdin, printed the
command's help text on stdout, and exited 1. The first three report
`ERROR  Missing required positional argument: FILE`; the fourth reports
`ERROR  Missing required argument: --format`. No form reads stdin:

```bash
cat DESIGN.md | npx --yes @google/design.md@0.4.0 lint -
cat DESIGN.md | npx --yes @google/design.md@0.4.0 export - --format css-vars
cat DESIGN.md | npx --yes @google/design.md@0.4.0 export --format css-vars -
cat DESIGN.md | npx --yes @google/design.md@0.4.0 export -- - --format css-vars
```

**Always pass an absolute path.** To lint or export generated content, write it
to a real file first — a temporary file under the scratchpad directory is
enough — and pass that path.

---

## 8. Version pinning

The postanovka's second open question (OQ-2) asked whether to invoke a pinned
version or a floating one. **Decision: always pin `@google/design.md@0.4.0`.**

```
cd /tmp && npx --yes @google/design.md@0.4.0 <cmd> <ABSOLUTE-PATH>
```

Never `@google/design.md` bare and never `@latest`. The reasons are specific:

1. The format itself declares `version: alpha`. The upstream project has not
   claimed stability for the schema.
2. Rule behaviour is not stable, and this skill's correctness depends on it in
   places a reader cannot check by eye. `references/linter-rules.md` quotes
   exact finding text; `examples/fixture-clean.md` asserts an exact summary
   (`{"errors": 0, "warnings": 0, "infos": 1}`); `assets/` templates are
   authored specifically to avoid `orphaned-tokens`. A rule added or
   re-severitied upstream turns those into false statements, silently, on a
   machine whose npx cache happened to refresh.
3. A floating tag makes runs non-reproducible across machines. Two agents on the
   same file would report different findings and neither would be wrong.

### 8.1 Re-verifying after a deliberate bump

A version bump is a change to this skill, not a maintenance detail. Procedure:

1. Change the pin in one place at a time and run the full corpus through the new
   version — every `assets/template-*.md` and every `examples/*.md`:

   ```bash
   cd /tmp
   for f in /ABS/PATH/skills/design-md/assets/*.md \
            /ABS/PATH/skills/design-md/examples/*.md; do
     printf '%s\t' "$(basename "$f")"
     npx --yes @google/design.md@<NEW> lint "$f" \
       | python3 -c 'import json,sys; print(json.load(sys.stdin)["summary"])'
   done
   ```

2. Compare the summaries against the same loop run at `0.4.0`. Capture both to
   files and `diff` them; do not compare by eye.
3. Any summary that changed is a finding. Either the template needs editing or
   a `references/` claim needs rewriting. `assets/template-*.md` must still
   reach `summary.errors == 0`, and `examples/fixture-clean.md` must still
   reach exactly `{"errors": 0, "warnings": 0, "infos": 1}`.
4. Re-run every verbatim output block quoted in `references/` and replace any
   that moved. A quoted output that no longer reproduces is worse than no
   quote.
5. Re-run the five `export` formats and diff the output against the 0.4.0
   output. A changed variable prefix (§4.1) or a newly carried property (§4.2)
   invalidates the coverage matrix in §1.2.
6. Update the pin in `SKILL.md`, `scripts/lint` (`DEFAULT_VERSION`), and every
   `references/` file in the same commit. A split pin means two commands in one
   session run two versions.

### 8.2 Licensing

`@google/design.md` is Apache-2.0, published by Google LLC. It is invoked
through `npx` and is **never bundled**: this skill carries no upstream source,
no upstream `examples/`, and no vendored copy of the CLI. The package is fetched
at run time into npx's cache. That is the only network access any part of this
skill performs.

---

## 9. Verified traps, in one table

| Trap | What actually happens |
| :--- | :--- |
| `export` on a file with lint errors | Exits 0 and emits tokens. `export` never lints. Lint first. |
| `export` without `--format` | Exit 1. There is no default format. |
| `--format scss` on `export` | Exit 1, `{"error":"INVALID_FORMAT", …}`. |
| `--format text` on `lint` / `diff` | Output is **JSON**. Not implemented; not validated. Exit code stays the command's own — 1 on a file with errors. |
| `--format wibble` on `lint` / `diff` | Same JSON, no error. |
| `--format markdown` on `diff` | A YAML-shaped dump, not a `# Lint Report`. Empty buckets parse as `None`. |
| `-` for stdin | Not accepted by the parser. Exit 1. Pass an absolute path. |
| Radii in `css-vars` | `--rounded-*`, not `css-tailwind`'s `--radius-*`. |
| Typography in `css-vars` | Absent in full. A type-only file exports an empty `:root` block. |
| Unitless `lineHeight` | Dropped by all three token-carrying formats. |
| `fontFeature` / `fontVariation` | Dropped by all three token-carrying formats. |
| `fontWeight` type | String `"400"` in `json-tailwind`, number `400` in `dtcg`. |
| `lineHeight` in `dtcg` | Unit stripped: `24px` exports as `24`. |
| `components` in any export | Never exported. Read the DESIGN.md. |
| `--prefix` outside `css-vars` | Accepted, exits 0, changes nothing. |
| `diff` exit 0 | Means "no new findings", **not** "no changes". Read `tokens` for changes. |
| `diff` on a rewritten body | Empty. `diff` never reads the markdown. |
| `diff` naming the defect | It does not. It reports counts only; run `lint` for the text. |

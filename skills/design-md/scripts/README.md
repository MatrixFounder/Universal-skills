# `design-md` — operator notes for `scripts/`

Maintenance and debugging notes for the three tools in this directory. Agent-facing
usage lives in `../SKILL.md` and `../references/`; this file is for whoever has to
change the code or explain its output.

Everything below was executed on 2026-08-28, and §§2, 3, 5 and 8 re-executed unchanged
on 2026-08-29. The `--pair` and `UNCHECKED FILLS` material in §§1, 2, 3, 7 and 8 was
executed on 2026-08-29 against the current `check-contrast`. All of it against
`@google/design.md@0.4.0`, Node v24.15.0, Python 3.14.4, macOS (darwin 25.5.0). Quoted
output is real output.

---

## 1. What the three tools are for

The toolchain **measures**; the agent **interprets**. That split is the reason all
three exist as scripts rather than as prose in `SKILL.md`.

`lint` wraps the upstream `design.md lint` command. Upstream emits JSON that names a
defect but not a repair, and it emits it from a working directory that is easy to get
wrong. The wrapper resolves paths to absolute, shells out from a neutral directory,
groups findings by severity into an aligned table, and appends a one-line `REMEDY`
per rule id that fired. `check-contrast` computes WCAG 2.x contrast ratios over the
whole palette, which the upstream `contrast-ratio` rule never does — that rule only
looks at components declaring both `backgroundColor` and `textColor`, and only against
AA 4.5:1. It also names the components that declare a fill and no `textColor` — the
ones that rule can never reach. `extract-palette` counts pixels in an image and
reports each dominant colour with its share of the sampled area, because a colour read
off a screenshot by eye is distorted by compression, antialiasing, gradients and colour
profiles.

None of the three decides anything. `lint` reports what upstream reported.
`check-contrast` reports ratios, thresholds, and the fills no rule reaches.
`extract-palette` reports measured hex values plus a `HINT` column that is explicitly
labelled a heuristic. Which measured colour is a background, which is an accent, and
whether a failing contrast pair should be fixed by darkening the text or lightening the
surface — those are the agent's calls.

---

## 2. CLI reference

Every flag below was read from the script's own `--help`. Re-run `--help` after any
change; this section is a copy, not the source of truth.

### 2.1 `lint`

```
usage: lint [-h] [--json] [--strict] [--version PIN] [--timeout SECONDS]
            [--list-rules]
            [FILE ...]
```

| Flag | Default | Effect |
| :--- | :--- | :--- |
| `FILE ...` | none | Paths to DESIGN.md files. Zero files is an input error (exit 2). Repeats are de-duplicated after resolving to absolute paths. |
| `--json` | off | Emit upstream JSON instead of the report. One file: the upstream document verbatim, with trailing newlines normalised to one. Several files: one object keyed by absolute path. |
| `--strict` | off | Warnings fail too. Turns the wrapper into a gate. |
| `--version PIN` | `0.4.0` | The **package version to run**. It takes an argument and does not print the wrapper's own version. `lint --version` alone is a usage error. |
| `--timeout SECONDS` | `300` | Wall-clock budget for each `npx lint` call. With several files the bound applies per file, not to the run as a whole. Exceeding it is exit 3, and the file is reported as `not linted`. |
| `--list-rules` | off | Print every emitted rule id with its default severity and remedy, then exit 0 — 14 rows over 13 distinct ids, see below. Reads no file and makes no network call. |

`--list-rules` is the fastest way to see the rule-id inventory without a fixture:

```
  broken-ref          error    Define the token the reference names, or repoint ...
  broken-ref          warning  Rename the component key to one of backgroundColor, ...
  ...
A finding with no rule id at all comes from the frontmatter parser, before
any rule runs (an unparseable or absent YAML block).
```

Note the shape: 11 rule *descriptors* upstream, 13 distinct rule *ids* on the wire,
printed as 14 rows (`references/linter-rules.md` §2 carries the same three numbers).
`broken-ref` is emitted at two severities for two different defects, and the descriptor
named `omitted-rules` never prints its own name — it emits `declared-omission`,
`redundant-omission` and `unknown-omission`. Grepping output for `omitted-rules` finds
nothing.

### 2.2 `check-contrast`

```
usage: check-contrast [-h] [--json] [--level {aa,aaa,both}] [--min RATIO]
                      [--pair FG,BG] [--strict-decorative]
                      [--matrix {summary,plausible,full}] [--fail-only]
                      [--no-matrix] [--timeout SECONDS] [--self-test]
                      [--version]
                      [DESIGN.md]
```

| Flag | Default | Effect |
| :--- | :--- | :--- |
| `DESIGN.md` | none | The file to check. Optional only because `--self-test` needs no file. |
| `--json` | off | Full result object on stdout instead of the report. Carries every computed pair regardless of `--matrix`. Under `--pair` it emits the smaller pair-query object instead. |
| `--level {aa,aaa,both}` | `aa` | Which threshold gates the exit code for **text** pairs. `aa`=4.5, `aaa`=7.0, `both`=gate at 4.5 and list AAA shortfalls as advisory. Non-text pairs stay at 3.0. |
| `--min RATIO` | unset | Explicit text gate; supersedes `--level`. Non-text pairs stay at 3.0. |
| `--pair FG,BG` | unset | Report exactly the two named colour tokens as one pair — its ratio and all four verdict columns — and nothing else. Repeatable. Applies no role classification and no MD3 pairing. `--matrix`, `--fail-only`, `--no-matrix` and `--strict-decorative` are inert in this mode; `--json`, `--level` and `--min` are not. Gate and exit code come from the **text** gate. See below. |
| `--strict-decorative` | off | Also gate decorative non-text pairs at 3.0. A non-text token whose name ends in `-variant` (`outline-variant`) is decorative by default: measured and printed, exempt under WCAG 2.x SC 1.4.11, and excluded from the exit code. |
| `--matrix {summary,plausible,full}` | `plausible` | How much of the wider matrix to print. `summary`=counts only; `plausible`=counts plus only the plausible pairs below the gate; `full`=every computed pair, grouped by background. |
| `--fail-only` | off | With `--matrix full`, print only pairs below the gate. `--matrix plausible` already lists only those. |
| `--no-matrix` | off | Omit the wider matrix; print only intended pairs and the typography table. |
| `--timeout SECONDS` | `300` | Wall-clock budget for the one `npx export` call. |
| `--self-test` | off | Check the ratio implementation against five known answers and exit. No file, no network. |
| `--version` | — | Prints `check-contrast 1.0 (upstream @google/design.md@0.4.0)`. |

Four things about this script surprise people, so state them when you explain its output.

**It reads token values from upstream, not from the YAML.** It runs
`npx --yes @google/design.md@0.4.0 export <FILE> --format json-tailwind` and reads
`theme.extend`. That is how `{colors.x}` references get resolved and how `oklch()`,
`color-mix()` and named colours all arrive as lowercase hex. No colour value is parsed
here, and there is still no YAML parser in this file: the one thing read from the file
directly is the *key names* of its `components:` block, by the shallow scan described
below, and the colour behind each of those keys still comes from the export. The
consequence is the `defines no colors` row of §7: a reference that does not resolve is
dropped silently by `export`, and the script then sees a palette with no colours.

**The exit code is decided by "intended pairs" only.** Those are the MD3 pairings the
format's own vocabulary implies — `on-X` on `X`, `on-surface` on every surface role,
`outline` on a surface as a functional boundary. Everything else is printed as an
advisory matrix and never changes the exit code. The `GATED` column says, per row,
whether the row can fail the run. `--pair` is the one exception: in that mode the
queried pairs decide the exit code alone, and no intended pair, matrix row or component
is computed at all.

**`--pair` bypasses every heuristic in the file.** Nothing else in `check-contrast`
reports a pair whose foreground the naming heuristic put on the *background* side:
`tertiary` is a background under classification rule 6, so `tertiary` on `surface` is
printed by no matrix, at any `--matrix` setting. `--pair FG,BG` names the two tokens
directly and reports that pair and nothing else. Both names must be tokens the file
defines, and their values still come from the one `export` call, so this is not an
offline calculator. The ratio is independently derivable from the WCAG 2.x formula —
`#176b5a` on `#ffffff` is 6.3885, so 6.39:

```text
$ scripts/check-contrast examples/example-saas-dashboard.md --pair tertiary,surface
check-contrast — /abs/.../examples/example-saas-dashboard.md
pair query: 1 pair(s) named on the command line; gate 4.50:1 (--level aa)

  RATIO    AA    AA-LG  AAA   UI-3.0  GATE   PAIR
  6.39     PASS  PASS   FAIL  PASS    PASS   tertiary #176b5a on surface #ffffff

  --pair reports exactly the pair named, whatever either token's name implies about
  its role; no classification and no MD3 pairing is applied. The GATE column, and
  the exit code, use the TEXT gate. For a non-text pair (a border, a divider, an
  icon) read the UI-3.0 column instead, or pass --min 3.0.
  exit 0 — every queried pair meets the gate
EXIT=0
```

The `GATE` column and the exit code use the **text** gate, because a queried pair
carries no role and none is assumed for it. For a border or a divider read the `UI-3.0`
column, or move the gate: on the same measured 3.82, `--pair outline,surface` exits 1
at the default 4.50 gate and 0 under `--min 3.0`. A token name the file does not define
is rejected by name and never substituted — the nearest defined token is named back, or
the file's own tokens are listed when nothing is near:

```text
$ scripts/check-contrast examples/example-saas-dashboard.md --pair tertiery,surface
check-contrast: error: --pair: `tertiery` is not a color token in this file; closest color token in this file is `tertiary`
EXIT=2

$ scripts/check-contrast examples/example-saas-dashboard.md --pair tertiary
check-contrast: error: --pair takes exactly two color token names separated by one comma, as --pair FG,BG; got 'tertiary'
EXIT=2
```

A pair with a translucent *background* has no ratio at all, because the real backdrop is
unknown; it is reported under `NOT ANSWERABLE` and exits 2 rather than being invented. A
translucent *foreground* is composited over the named background and noted. Exit 2 takes
precedence: one unanswerable pair makes the run exit 2 even when another queried pair is
below the gate. Under `--json` the object is a different shape from the normal report —
`"mode": "pair-query"`, with `queried_pairs[]`, `unanswerable_pairs[]` and no
`intended_pairs`, `matrix` or `components` key.

**It names the component fills that nothing checks.** The upstream `contrast-ratio` rule
fires only when a component declares BOTH `backgroundColor` and `textColor`, and this
script checks the palette rather than components. A component that declares a fill and no
`textColor` is therefore checked by neither, and that silence is indistinguishable from a
pass — on the fill that is often the most saturated area of the product. Such components
are listed under `UNCHECKED FILLS` and counted in `SUMMARY` on every run:

```text
UNCHECKED FILLS — components that declare a backgroundColor and no textColor
  divider                  fill {colors.outline-variant} #c7d0d8
  divider-section          fill {colors.outline} #78848f
  meter-on-time            fill {colors.tertiary} #176b5a
  No contrast rule can fire on these: the upstream `contrast-ratio` rule needs BOTH
  a backgroundColor and a textColor, and this script checks the palette, not
  components. ...

SUMMARY
  component fills: 28 component(s) declared, 3 with a backgroundColor and no
                   textColor (listed above; checked by nothing, not gated)
```

It is a naming, not a verdict: **no ratio is invented and the exit code never moves.**
That is deliberate — this tool's exit 1 asserts one thing, that a *measured* ratio is
below its gate, and an undeclared `textColor` produces no ratio to measure. It is not
folded into `--strict-decorative` either. A build that must fail on these should gate on
`components.unchecked_fills` in `--json`. Two of the shipped files hit it legitimately:
`assets/template-editorial.md` (`section-rule`) and `examples/example-saas-dashboard.md`
(`divider`, `divider-section`, `meter-on-time`) name components that render no text.

Because no export format carries components, the `components:` block is read from the
file itself by a shallow two-level scan of **key names only** — not a YAML parser. It
reports what it did rather than claiming a count it does not have — of the four possible
`SUMMARY` lines, only the first states a count:

| `components.scan_status` | `SUMMARY` line | When |
| :--- | :--- | :--- |
| `read` | `N component(s) declared, M with a backgroundColor and no textColor` | the normal path |
| `absent` | `no components block in the frontmatter` | frontmatter with no `components:` key |
| `no-frontmatter` | ``no `---` frontmatter to read components from`` | tokens declared in a fenced `yaml` code block instead |
| `unreadable` | `components block not in a shape this scan reads (flow mapping or tab indentation) — the check did not run` | `components: {a: {…}}`, or tab-indented |

### 2.3 `extract-palette`

```
usage: extract-palette [-h] [--colors N] [--min-share PCT]
                       [--ignore-edges PCT] [--region X,Y,W,H] [--bits N]
                       [--merge-distance D] [--max-samples N]
                       [--decoder {auto,pillow,stdlib-png}] [--json]
                       [--version]
                       IMAGE
```

| Flag | Default | Effect |
| :--- | :--- | :--- |
| `IMAGE` | required | Path to the image. Absolute paths recommended. |
| `--colors N` | `12` | Report at most N colours, highest share first. Must be >= 1. |
| `--min-share PCT` | `0.5` | Drop clusters below PCT% of counted pixels. Range 0–100. |
| `--ignore-edges PCT` | `0` | Crop PCT% off each side before sampling — browser chrome, tab bars, window shadows. Must be >= 0 and < 50. Cannot be combined with `--region`; `--ignore-edges 0` is a no-op and is accepted alongside it. |
| `--region X,Y,W,H` | unset | Sample only this window of the decoded image, in whole pixels, origin at the top-left corner. Use it to measure one band — a table header, a left rail, a card — instead of the whole capture. A region that is malformed, empty, negative or does not fit inside the image is rejected (exit 1) and never clamped. The applied window is printed on the `image` line and appears in `--json` as `sampling.region`. |
| `--bits N` | `5` | Quantisation bits per channel (5 = 32 levels = 32768 buckets). Range 3–8. |
| `--merge-distance D` | `6.0` | CIE76 dE in CIELAB below which two buckets are one colour. Raise to collapse a ramp, lower to split one; `0` disables merging. Must be >= 0. |
| `--max-samples N` | `400000` | Upper bound on sampled pixels; larger images get a coarser stride grid. `0` samples every pixel. |
| `--decoder {auto,pillow,stdlib-png}` | `auto` | Force a decoder. `auto` uses Pillow when importable, otherwise the built-in PNG reader. |
| `--json` | off | One JSON object on stdout. Errors still go to stderr, as JSON. |
| `--version` | — | Prints `extract-palette 1.0`. |

The `HINT` column is a heuristic over the rank, the share, CIELAB lightness `L*` and
CIELAB chroma `C*` — and nothing else. The `HUE` column is descriptive output, not an
input to the heuristic. It is not a role assignment, and the report says so in its own
footer. Chroma rather than HSL saturation is deliberate: the off-white `#f5f2ec` has
HSL S 0.31 but `C*` 3.2, and calling it saturated would mislabel every warm-white
surface as an accent.

Two defaults are worth stating, because `SKILL.md` Route 2 works around both. The
`0.5` default `--min-share` sits directly on top of the pixel share of a typical
single-control accent: on a 1440x900 dashboard capture `#e25a3c` measures 0.52%
uncropped — inside the report by 0.02 points — and 0.40% under `--ignore-edges 4`,
which drops it out of the report entirely; Route 2 therefore passes `--min-share 0.1`.
The `6.0` default `--merge-distance` merges an adjacent light-plane ladder into one
row: on the same capture rank 1 is `#ffffff` at 71.70% built from two buckets, and at
`--merge-distance 3` that row splits into `#ffffff` 58.51% and `#f7f4ef` 16.56%.

---

## 3. Exit codes

The three tables differ. Do not assume one from another.

| Code | `lint` | `check-contrast` | `extract-palette` |
| :--- | :--- | :--- | :--- |
| 0 | no errors (and no warnings under `--strict`) | every gated intended pair meets the gate | success |
| 1 | lint errors, or warnings under `--strict` | a gated intended pair fails the gate; under `--pair`, a queried pair below the text gate; also a `--self-test` mismatch | option value out of range (`--bits 99`, `--ignore-edges 60`); also a `--region` that is malformed, empty, negative or outside the image, and `--region` combined with a non-zero `--ignore-edges` |
| 2 | input problem: file missing, unreadable, a directory, or a command-line usage error | input file missing, a directory, not a regular file, unreadable; also a command-line usage error, a `--pair` naming a token the file does not define, and a queried pair whose ratio does not exist (translucent background) | image missing, a directory, unreadable, empty, corrupt, or nothing left to sample; also an argparse-level usage error |
| 3 | `npx` or the design.md CLI is unavailable, timed out (`--timeout`, default 300s per file), or returned output that is not JSON | the `export` call failed or timed out (`--timeout`, default 300s), or the file defines no colors | format recognised but no available decoder handles it |

With several files `lint` returns the worst code, in the order `3 > 2 > 1 > 0`.

Three things about these codes are worth knowing before you debug one:

- Under `--pair`, the queried pairs decide the code alone, and 2 outranks 1: one
  unanswerable pair exits 2 even when another queried pair is below the gate. An
  `UNCHECKED FILLS` finding never moves the code at all — it is an absent declaration,
  not a measured failure.
- `extract-palette` splits usage errors across **1 and 2**. Its own range checks
  (`validate()`) exit 1; argparse's own errors — an unparseable `--bits abc`, a bad
  `--decoder` choice, a missing `IMAGE` — exit 2, argparse's default. `lint` overrides
  argparse to route every usage error to 2, and `check-contrast` uses argparse's
  default 2, so those two are internally consistent and `extract-palette` is not.
- Code 3 means "the tool could not run", not "the file is bad", in all three.

---

## 4. Dependencies and the install story

| Script | Python | Third-party Python | Needs Node | Network |
| :--- | :--- | :--- | :--- | :--- |
| `lint` | stdlib only | none | yes, for `npx` | npm registry on a cold npx cache |
| `check-contrast` | stdlib only | none | yes, for `npx` | npm registry on a cold npx cache |
| `extract-palette` | stdlib only | Pillow, **optional** | no | none, ever |

`install.sh` is **optional**. Nothing in the skill requires it. It creates
`scripts/.venv/` and installs Pillow into it, then runs a known-answer smoke test on
both decode paths. It installs nothing globally and installs no system packages —
missing system tools are printed as hints.

A second run on an already-bootstrapped host (excerpt; the `target:`, `venv python:`
and `pip:` lines are omitted here, and the final absolute path is abbreviated):

```text
$ bash skills/design-md/scripts/install.sh
[install.sh] design-md skill — local bootstrap
[install.sh] python3: 3.14 (<the python3 on PATH>)
[install.sh] venv: already present, reusing it
[install.sh] Pillow: 12.3.0
[install.sh] smoke test (built-in PNG decoder, host python3): [('#0f1419', 50.0), ('#f5f2ec', 30.0), ('#e2542c', 20.0)] -- OK
[install.sh] smoke test (Pillow, venv python): [('#0f1419', 50.0), ('#f5f2ec', 30.0), ('#e2542c', 20.0)] -- OK
[install.sh] node: v24.15.0 (npx will fetch @google/design.md@0.4.0 on demand)
[install.sh] done. Nothing was installed outside .../scripts/.venv.
```

`extract-palette` appends `scripts/.venv/lib/python<major>.<minor>/site-packages` to
`sys.path`, and only when the tag matches the running interpreter — a venv built for
another minor version would load an ABI-incompatible extension. The path is *appended*,
so an ambient Pillow keeps priority. `install.sh` detects a version-mismatched venv and
recreates it.

### What degrades without Pillow

Exactly one thing: **input format coverage**. Nothing is silently mis-read.

- **Still works**: non-interlaced PNG, bit depth 8 and 16, colour types 0/2/3/4/6,
  filter types 0–4, multiple IDAT chunks, `tRNS`. Screenshots and exported diagrams are
  normally exactly that shape, so the screenshot-extraction procedure usually needs no
  install at all. Every PNG sampled on this host — five files, 768x1376 to 3080x1806 —
  read `depth=8 interlace=0` at colour type 2 or 6, and a 3080x1806 one was processed
  end to end by `--decoder stdlib-png`. Confirm a specific file rather than assuming:
  the IHDR interlace byte is byte 29 of the file.
- **Exits 3**: JPEG, WebP, HEIF/AVIF, TIFF, BMP, GIF, interlaced (Adam7) PNG, and PNG
  at bit depth 1/2/4. The message names the format and points at `install.sh`.

Verified with Pillow made unimportable (a `PIL/__init__.py` that raises, on
`PYTHONPATH`):

```
$ PYTHONPATH=<shadow> python3 extract-palette /abs/photo.jpg
extract-palette: unsupported format: /abs/photo.jpg looks like JPEG. Without Pillow this script reads PNG only.
Either install Pillow:  bash /abs/skills/design-md/scripts/install.sh
or convert the file to PNG first.
EXIT=3

$ PYTHONPATH=<shadow> python3 extract-palette /abs/flat.png
extract-palette  /abs/flat.png
  decoder    built-in PNG decoder (depth 8, colour type 2 truecolour)
```

The two decode paths agree. On the same PNG, `--decoder pillow` and
`--decoder stdlib-png` produced byte-identical `--json` output once the two
`decoder`/`decoder_detail` lines were removed:

```
$ extract-palette flat.png --decoder pillow    --json | grep -v '"decoder' > a.json
$ extract-palette flat.png --decoder stdlib-png --json | grep -v '"decoder' > b.json
$ diff a.json b.json && echo IDENTICAL
IDENTICAL
```

Speed is the only other difference: scanline un-filtering runs in Python on the
built-in path and in C under Pillow. `requirements.txt` records the measured figures.

---

## 5. Why `@google/design.md@0.4.0` is pinned, and how to bump it

Inside `scripts/` the pin is written into four files. Two of them are **executable** —
they decide which version actually runs; the other two are prose that becomes false the
moment the executable sites move without them. All four must move in the same commit.

| File | Kind | Where, measured by `grep -n '0\.4\.0'` |
| :--- | :--- | :--- |
| `lint` | **executable** | one site: `DEFAULT_VERSION = "0.4.0"`, joined to `PACKAGE = "@google/design.md"` in the `npx` argv. `--version PIN` overrides it per call, so a stale constant here is maskable at the command line. |
| `check-contrast` | **executable** | two sites: `PKG = "@google/design.md@0.4.0"` and the same string quoted in `run_export`'s docstring. `--version` prints `PKG`, so it moves with the constant. There is no override flag. |
| `install.sh` | prose | three sites: the header comment and both Node hints. |
| `README.md` | prose | this file: the provenance line, both wrappers' `--version` rows, the quoted `export` invocation and the quoted error output, the `install.sh` transcript, the offline notes, and this section. Its occurrence count moves with any edit to the file, so count it with the grep below rather than quoting a number from memory. |

`extract-palette` contains no site — it never calls `npx`.

Skill-wide the pin occurs in **thirteen** tracked files: the four above, plus nine
outside `scripts/` — `SKILL.md`, `references/anti-slop.md`,
`references/export-formats.md`, `references/extraction.md`,
`references/linter-rules.md`, `references/spec-anatomy.md`,
`assets/template-editorial.md`, `examples/fixture-clean.md` and
`examples/fixture-broken.md`. `references/export-formats.md` §8.2 ("Every place the pin
is written") names those same thirteen and records what is written in each; this section
is the `scripts/` subset with the per-site detail. The two lists must move together — a
bump that reconciles one and not the other is the failure both exist to prevent.
Confirm the roster by grep rather than by memory, from the skill directory, and
reconcile any file the grep finds that neither list names:

```bash
grep -rl '0\.4\.0' . --exclude-dir=.venv | sort    # 13 files today
```

The reason for a pin rather than a floating `@latest` is that the *format* is at
`version: alpha`:

```
$ npx --yes @google/design.md@0.4.0 spec | head -1
<!-- Generated from spec.mdx + spec-config.ts | version: alpha -->
```

An alpha format can change its schema keys, its rule set, its severities and its
message wording between releases. `references/linter-rules.md` quotes upstream messages
verbatim and `assets/*.md` are hand-tuned to lint at zero errors, so a silent bump
would rot documentation and templates at the same time with no signal. As of
2026-08-29 the pin also *is* the latest release (`npm view @google/design.md version`
→ `0.4.0`), so the pin costs nothing today.

**Re-verification procedure after a deliberate bump.** Do this before and after, and
compare. Run it from the repository root; do not `cd /tmp` first, because the paths are
repo-root-relative and the wrapper already resolves them to absolute and shells out from
a neutral working directory itself (§7). The summariser is stdlib `python3` — `jq` is
not a dependency of this skill and is not assumed to be installed:

```bash
skills/design-md/scripts/lint --json \
  skills/design-md/assets/*.md skills/design-md/examples/*.md \
| python3 -c 'import json, os, sys
for path, doc in json.load(sys.stdin).items():
    print("%-28s %s" % (os.path.basename(path), json.dumps(doc["summary"], sort_keys=True)))'
```

Baseline at 0.4.0 (2026-08-29) — four templates and `example-saas-dashboard.md` at zero
errors and zero warnings, `fixture-broken.md` deliberately failing. Verbatim stdout; the
`[lint] running npx …` notice goes to stderr and is not part of it:

```text
template-cyrillic.md         {"errors": 0, "infos": 1, "warnings": 0}
template-editorial.md        {"errors": 0, "infos": 1, "warnings": 0}
template-product-saas.md     {"errors": 0, "infos": 1, "warnings": 0}
template-skeleton.md         {"errors": 0, "infos": 1, "warnings": 0}
example-saas-dashboard.md    {"errors": 0, "infos": 2, "warnings": 0}
fixture-broken.md            {"errors": 1, "infos": 1, "warnings": 6}
fixture-clean.md             {"errors": 0, "infos": 1, "warnings": 0}
```

Any movement in those numbers is a real behaviour change and must be reconciled
against `references/linter-rules.md`, which quotes upstream messages word for word.
Then re-run the checks in §8. Finally, re-read `npx --yes @google/design.md@<new> spec`
and diff the canonical section list and the schema keys against
`references/spec-anatomy.md`.

---

## 6. Network behaviour

Stated plainly, because "it works offline" is only half true.

- `npx --yes @google/design.md@0.4.0 …` reaches `https://registry.npmjs.org` the first
  time it resolves the package, then caches it. `lint` writes a notice to stderr while
  that happens: `[lint] running npx @google/design.md@0.4.0 — the first call downloads
  the package and takes about 30 seconds`.
- Beyond that one `npx` call per invocation, neither `lint` nor `check-contrast` makes
  any network request of its own.
- `extract-palette` makes no network calls at all, in any mode. Its complete import
  list is `argparse, json, math, os, struct, sys, zlib` — no `urllib`, no `socket`, and
  no `subprocess`, so it spawns nothing either.

**Checking the cache.** The npx cache lives under the npm cache root, one directory per
dependency set:

```
$ npm config get cache
<HOME>/.npm
$ grep -l "@google/design.md" "$(npm config get cache)"/_npx/*/package.json
<HOME>/.npm/_npx/453056feeae89689/package.json
```

A hit means the package is resolvable offline. Verified: with that cache warm,
`npm_config_offline=true npx --yes @google/design.md@0.4.0 lint <file>` produces the
normal JSON.

**Offline with a cold cache.** npm fails with `ENOTCACHED`, and both wrappers surface
it as exit 3 rather than pretending the file is clean:

```
$ npm_config_cache=<empty-dir> npm_config_offline=true scripts/lint examples/fixture-clean.md
lint: .../fixture-clean.md: the CLI returned output that is not JSON (exit 1): npm error code ENOTCACHED
npm error request to https://registry.npmjs.org/@google%2fdesign.md failed: cache mode is 'only-if-cached' but no cached response is available.
EXIT=3

$ npm_config_cache=<empty-dir> npm_config_offline=true scripts/check-contrast examples/fixture-clean.md
check-contrast: error: `@google/design.md@0.4.0 export` exited 1: npm error code ENOTCACHED
EXIT=3
```

To prime a machine before it goes offline, run any `lint` once with network access.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `sh: design.md: command not found`, exit 127, when calling `npx` by hand | `npx` prefers a bin declared by the surrounding workspace. Inside a checkout that declares a `design.md` bin, npx resolves the local (unbuilt) one and never fetches the package. Reproduced inside a checkout of the upstream `design.md` repository, which declares that bin. | `cd /tmp` first, and pass an absolute path to the file. Both wrappers already do this — they run the child process with `cwd=/tmp` (falling back to `tempfile.gettempdir()` in `lint` and to `~` in `check-contrast` if `/tmp` is absent), and `scripts/lint` was verified to exit 0 when invoked from inside that same workspace. |
| First run pauses for tens of seconds with no output | Cold npx cache; npm is fetching the package. | Wait. `lint` announces it on stderr. Later runs hit the cache — see §6 for how to check. |
| `extract-palette: unsupported format: interlaced (Adam7) PNG — the built-in decoder reads non-interlaced PNG only`, exit 3 | The PNG has IHDR interlace method 1 and Pillow is not importable. | `bash scripts/install.sh` (Pillow reads Adam7), or re-save the PNG non-interlaced. Verified: with Pillow present, `--decoder auto` reads the same file. |
| `extract-palette: unsupported format: … looks like JPEG. Without Pillow this script reads PNG only.`, exit 3 | Any non-PNG input on the no-Pillow path. | `bash scripts/install.sh`, or convert to PNG. The message names the sniffed format and prints the exact install command. |
| `--decoder pillow was requested but Pillow is not importable`, exit 3 | An explicit decoder request that the host cannot satisfy. | Run `install.sh`, or drop the flag and let `auto` fall back. |
| `lint` reports `warning - - No YAML content found. Expected frontmatter (---) or fenced yaml code blocks.` and still exits 0 | A DESIGN.md with no frontmatter is not an error upstream. It defines no tokens, so no rule can run. | Add a `---` block with at least `name:`. Use `--strict` if a missing block must fail the run — verified to turn that same file into `FAIL: 0 errors, 1 warning, 0 infos` and exit 1. |
| `lint` is clean but `check-contrast` exits 3 with `defines no colors — nothing to check` | Colour tokens are `{refs}` that resolve to nothing. `export` drops them silently (`"colors": {}`) and upstream's `broken-ref` rule does **not** fire for an unresolvable reference in the `colors` map — only for one inside `components`. Verified: a file whose colours are all `{palette.*}` refs to a non-existent section lints `PASS: 0 errors, 0 warnings, 1 info`. | Read the `token-summary` info line. It counts what upstream actually resolved; if it omits colours, the refs are dead. Then define the referenced tokens or point the refs at paths that exist. |
| `check-contrast` exits 1 on a file that `lint` passes | The two tools check different things. `lint` never checks the palette; `check-contrast` contrast-checks no component — it only names the fills nothing can check. A common cause is a functional `outline` token below 3.0:1 against its surface. | Read the `GATED` column to see which row decided the code, then fix the colour. Renaming the token into the `-variant` form also clears the run, because the exemption is triggered by the **name** — but the name is then an unverified claim that the element is purely decorative, and a divider that is the only thing separating two regions is not. The same hexes under the two names give different exit codes. |
| `check-contrast` prints a component under `UNCHECKED FILLS` and still exits 0 | The component declares a `backgroundColor` and no `textColor`, so nothing can check it: upstream's `contrast-ratio` rule needs both, and this script checks the palette. No ratio exists, so the exit code does not move. | Intended, and not a defect to silence. Declare the `textColor` and re-run, or state in prose that the component renders no text. If a build must fail on it, gate on `components.unchecked_fills` in `--json`; the exit code will not do it for you. |
| Every `npx`-backed run exits 3 with `` `npx` was not found on PATH `` | Node is absent or not on the PATH of the invoking process. | Install Node 18+ (`engines: node >=18` upstream). `extract-palette` is unaffected and needs no Node. |
| Exit 3 with `ENOTCACHED` | Offline with a cold npx cache. | See §6. |

---

## 8. How to test a change

Run all four. Checks 1 and 2 need neither network nor Node. Checks 3 and 4 shell out to
`npx`, so they need Node and a warm cache (or one slow first run).

Every command below is written to be run **from the repository root**, with no `cd`.
The `cd /tmp` in §7 applies to calling `npx` by hand; the wrappers do it themselves for
the child process, so a recipe that both `cd`s away and uses repo-root-relative paths
would only exit 127. Verified from a working directory whose `package.json` declares a
`design.md` bin: the wrapper, called there by absolute path, still exits 0 and prints
the normal report.

**1. Contrast maths, against known answers.** These figures are derived from the
WCAG 2.x formula and cross-checked against the published values for the same pairs. If
one stops reproducing, the ratio implementation is wrong — do not edit the expectations.
`--pair` reports through the same ratio function; §2.2's worked example (`tertiary` on
`surface` = 6.39, WCAG-derived 6.3885) is the spot-check for that path.

```
$ skills/design-md/scripts/check-contrast --self-test
check-contrast --self-test (WCAG 2.x known answers)
  OK   #000000 on #ffffff  expected 21.00  actual 21.00
  OK   #767676 on #ffffff  expected 4.54  actual 4.54
  OK   #808080 on #ffffff  expected 3.95  actual 3.95
  OK   #0000ff on #ffffff  expected 8.59  actual 8.59
  OK   #ffffff on #ffffff  expected 1.00  actual 1.00
  all known answers reproduced
EXIT=0
```

**2. Pixel counting, against a synthetic flat-region PNG.** `install.sh` builds a
200x100 PNG of three flat bands in exact 50 / 30 / 20 proportions with the standard
library alone, then requires both decoders to recover all three hex values and all
three shares:

```
$ bash skills/design-md/scripts/install.sh
[install.sh] smoke test (built-in PNG decoder, host python3): [('#0f1419', 50.0), ('#f5f2ec', 30.0), ('#e2542c', 20.0)] -- OK
[install.sh] smoke test (Pillow, venv python): [('#0f1419', 50.0), ('#f5f2ec', 30.0), ('#e2542c', 20.0)] -- OK
```

Exact shares are the point: a flat region has one occupied bucket per band, so
quantisation and clustering must not move the reported value off the true pixel value.

`install.sh` builds that PNG in a temp directory and deletes it on exit. To point
`extract-palette` at it directly — this is the run `SKILL.md` cites — rebuild it from
`install.sh`'s own generator:

```
$ sed -n '/^import struct/,/fh.write(png)/p' skills/design-md/scripts/install.sh > /tmp/mkpng.py
$ python3 /tmp/mkpng.py /tmp/smoke.png
$ skills/design-md/scripts/extract-palette /tmp/smoke.png
  image      200x100 px -> 200x100 (no crop)
  ...
  reported   3 of 3 clusters (max 12, min share 0.50%) covering 100.0% of counted pixels
EXIT=0
```

**3. Lint, across every shipped file.** From the repository root; the wrapper resolves
each path to absolute before the `npx` call:

```
$ skills/design-md/scripts/lint \
    skills/design-md/assets/*.md skills/design-md/examples/*.md
...
TOTAL 7 files: 6 passed, 1 failed — 1 error, 6 warnings, 8 infos
EXIT=1
```

Six passing files and `examples/fixture-broken.md` failing with exactly one error is
the contract. `fixture-broken.md` failing is required, not tolerated: it is the fixture
whose verbatim output `references/linter-rules.md` quotes.

**4. Contrast, across every shipped file.** Capture `$?` into a variable on its own
line — a command substitution such as `$(basename "$f")` in the same `echo` resets it,
and the loop silently reports 0 for everything:

```
$ for f in skills/design-md/assets/*.md skills/design-md/examples/*.md; do \
    b=$(basename "$f"); \
    skills/design-md/scripts/check-contrast "$f" --matrix summary >/dev/null 2>&1; \
    rc=$?; printf '%-28s check-contrast exit %d\n' "$b" "$rc"; done
template-cyrillic.md         check-contrast exit 0
template-editorial.md        check-contrast exit 0
template-product-saas.md     check-contrast exit 0
template-skeleton.md         check-contrast exit 0
example-saas-dashboard.md    check-contrast exit 0
fixture-broken.md            check-contrast exit 1
fixture-clean.md             check-contrast exit 1
```

The four templates and the worked example must stay at 0 — they are what the skill
tells an agent to copy. Both fixtures exit 1. That is expected for `fixture-broken.md`.
For `fixture-clean.md` it is a real, measured gap rather than a tool defect: the file is
clean *to the linter*, and its `outline` token sits at 1.72:1 against `surface`, below
the 3.0:1 functional-boundary gate. It is the sharpest available demonstration that
lint-clean does not imply contrast-clean.

Finally, if you changed a flag, re-run that script's `--help` and update §2. The help
epilogs are the primary documentation; this file is a derived copy.

### 8.1 `tests/test_e2e.sh` — the four checks above, as a gate

Everything in §8 is also asserted mechanically:

```
$ bash skills/design-md/scripts/tests/test_e2e.sh
...
design-md test_e2e: PASS (36 assertions)
```

It builds its own PNG fixtures rather than reading committed ones, so it behaves the
same inside a packaged `.skill` archive. It is the whole content of the `design-md`
CI job (`.github/workflows/design-md.yml`); that job is separate from `office-skills`
because this skill replicates nothing and needs neither LibreOffice nor Poppler.

Two properties are deliberate. A missing `npx` **fails** rather than skips — a green
gate that tested nothing is worse than a red one — and the run fails if fewer than 30
assertions execute, which catches a suite that silently stopped finding its fixtures.

One assertion is worth knowing about on its own. An accent occupying **0.48%** of a
frame sits below the default `--min-share` of 0.50, and the test asserts that the
default *drops* it while the documented `--min-share 0.1` recovers it. Route 2's
guidance depends on that pin; if the default ever changes, this fails loudly instead
of Route 2 quietly losing accents.

### 8.2 `tests/check-fabrication` — the check the linter cannot be

The linter checks form and `check-contrast` checks measured pairs. Neither can tell a
measured value from an invented one: `fontFamily: Inter` lints exactly as clean as a
family read off the source. This gate closes that opening for image-derived files.

```
$ skills/design-md/scripts/tests/check-fabrication FILE.md --image /abs/shot.png
```

`no-frontmatter` — the file declares no tokens at all. `unsourced-hex` — a frontmatter
hex that is not a colour of the image. `unsourced-type` — the capture carries no
glyph-shaped ink, so no family, size or weight is readable from it, and `typography`
is asserted anyway instead of appearing in `omitted`.

`unsourced-type` tests **shape, not colour count**. A redaction bar and crisply
aliased text both yield two flat clusters in a text window; only the spatial pattern
separates them, because a glyph does not fill its bounding box and a bar does. The ink
mask is built from local luminance against the modal luminance of a ~96×96
neighbourhood — not of a single tile, which a few bars can dominate outright, flipping
the mask and turning solid blocks into ragged glyph-shaped holes.

Exit 0 nothing unsourced, 1 something unsourced, 2 usage or I/O error.

### 8.3 `tests/trigger-eval.sh` — does the description route at all?

A separate question from every check above, and upstream of all of them: the skill's
guarantees are conditional on it being reached. The description is bilingual, so a
regression can be silent in one language and total in the other.

```
$ bash skills/design-md/scripts/tests/trigger-eval.sh --repeat 3
```

**Manual and billed.** Every query is a real `claude -p` call, which is why it is not
in CI. Queries live in `tests/trigger-queries.json`, each carrying what it probes, so
a failure names the claim that broke rather than only moving a number.

Two lessons are baked into that file, both learned by getting them wrong. A query must
**supply whatever it names**: asking about "the screenshot" with no screenshot present
measures whether the model asks for the missing file, not whether the description
routed — `{{IMAGE}}`, `{{CSS}}` and `{{DESIGN}}` are substituted with generated
fixtures. And routing is **not deterministic**: treat a single borderline result as
noise and re-check with `--repeat` before editing the description on the strength of
it. Only `description:` affects routing; the body does not.

---

## 9. Licensing

This skill is Apache-2.0. `@google/design.md` (Google LLC) is Apache-2.0 and is
**invoked through `npx`, never vendored**. No upstream source and no upstream
`examples/` content is copied into this directory. `check-contrast` and `extract-palette`
implement WCAG 2.x, PNG (RFC 2083) and CIELAB from their published specifications, in
this repository's own code; `lint` and `check-contrast` import the Python standard
library only, and `extract-palette`'s single third-party import, Pillow, is optional
and guarded. Pillow (HPND) is installed into `scripts/.venv/` by `install.sh` and is
not redistributed here. Attribution lives in the repository-root
`THIRD_PARTY_NOTICES.md`.

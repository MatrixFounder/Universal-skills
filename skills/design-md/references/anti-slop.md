# Anti-slop: prohibitions and their detection signals

The DESIGN.md format exists to replace an agent's default visual output with a
recorded set of decisions. A file that lints clean and still describes the
default look has defeated the format.

This is not a hypothetical. A file was built for this reference carrying seven
Tailwind default hexes, `system-ui` on every typography token, one radius value
used by every component, and four Do's-and-Don'ts truisms. `design.md lint`
reported:

```text
  "summary": {
    "errors": 0,
    "warnings": 2,
    "infos": 1
  }
```

Exit code 0. The two warnings were `contrast-ratio` findings caused by the
copied hexes, not by any of the defects listed below.

**`design.md lint` checks none of the prohibitions in this file.** Entries
AS-10 and AS-14 produce a linter signal as a side effect; the other fourteen
are invisible to it. This file is the check.

Scope: this reference covers what makes a file generic. The frontmatter schema
is in `references/spec-anatomy.md`; the eleven linter rules are in
`references/linter-rules.md`. Nothing here overrides either.

---

## Reading an entry

Every entry has three parts and nothing else:

1. **Prohibited** — the rule, stated flatly.
2. **Why it reads as default** — the mechanism by which the defect produces
   generic output.
3. **Detection** — how to find the defect in a finished DESIGN.md: an exact
   command, the arithmetic applied to its output, and the pass condition.

All outputs quoted below were produced on 2026-08-28 by running the command
shown. Four fixtures were used, none of which ships with the skill: `slop.md`,
written to carry every defect; `derived.md`, written to carry none;
`unrelated.md`, carrying only the AS-1 defect; and `dark.md`, carrying only the
AS-11 defect. The frontmatter lines that produce each signature are quoted with
the entry, so every check is reproducible on your own file.

---

## Setup: the inspector

Eleven of the sixteen detection signals need arithmetic over the frontmatter
rather than a text match. Write this throwaway inspector once per session. It is
stdlib-only Python 3, reads the frontmatter with regexes, and is not a linter —
it computes numbers and prints them.

```bash
cat > /tmp/dm-tokens.py <<'PY'
"""Throwaway DESIGN.md token inspector. stdlib only. Not a linter."""
import colorsys, math, re, sys
SUB = ("backgroundColor", "textColor", "typography", "rounded", "padding", "size", "height", "width")
def fm(p):
    t = open(p, encoding="utf-8").read()
    m = re.match(r"---\r?\n(.*?)\r?\n---\s*\r?\n", t, re.S)
    return (m.group(1) + "\n") if m else t
def block(src, key):
    m = re.search(r"^%s:[ \t]*\r?\n((?:[ \t]+.*\r?\n|\r?\n)*)" % key, src, re.M)
    return m.group(1) if m else ""
def px(v):
    m = re.match(r"^-?[\d.]+", v.strip().strip('"\''))
    if not m: return None
    s = v.strip().strip('"\''); n = float(m.group(0)); u = s[m.end():].strip()
    return n * 16 if u in ("rem", "em") else (n if u == "px" else n)
def rgb(h):
    h = h.strip().strip('"\'').lstrip("#")
    if len(h) == 3: h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
def lstar(c):
    f = lambda u: u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in c)
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return 116 * (y ** (1 / 3)) - 16 if y > 216 / 24389 else 903.3 * y
def colors(p):
    out = []
    for n, v in re.findall(r"^[ \t]+([\w-]+):[ \t]*(\S+)", block(fm(p), "colors"), re.M):
        v = v.strip().strip('"\'')
        if not re.fullmatch(r"#[0-9a-fA-F]{3,8}", v): continue
        r, g, b = rgb(v); h, l, s = colorsys.rgb_to_hls(r, g, b)
        c8 = (max(r, g, b) - min(r, g, b)) * 255
        out.append((n, v, h * 360, s * 100, l * 100, lstar((r, g, b)), c8))
    return out
def typo(p):
    out = []
    for m in re.finditer(r"^[ \t]{2}([\w-]+):[ \t]*\r?\n((?:[ \t]{3,}.*\r?\n)*)", block(fm(p), "typography"), re.M):
        out.append((m.group(1), dict(re.findall(r"([\w-]+):[ \t]*(.+)", m.group(2)))))
    return out
def cmd_hsl(p, pat=None):
    rows = colors(p)
    sel = [r for r in rows if pat is None or re.search(pat, r[0])]
    print(f"{'token':26} {'hex':9} {'H':>6} {'S%':>6} {'L%':>6} {'L*':>6} {'C':>5}")
    for n, v, h, s, l, ls, c in rows:
        print(f"{n:26} {v:9} {h:6.1f} {s:6.1f} {l:6.1f} {ls:6.1f} {c:5.0f}")
    hs = [h for _, _, h, _, _, _, c in sel if c >= 6]
    if hs:
        print(f"hue spread, selected tokens with C>=6 (n={len(hs)}): {max(hs) - min(hs):.1f} deg  (min {min(hs):.1f}, max {max(hs):.1f})")
    print("\nL* ladder, lightest first")
    prev = None
    for n, v, h, s, l, ls, c in sorted(sel, key=lambda r: -r[5]):
        print(f"  {n:26} {v:9} L*={ls:6.2f} C={c:3.0f}" + (f"  step={prev - ls:6.2f}" if prev is not None else ""))
        prev = ls
def cmd_scale(p):
    sizes = sorted({px(d["fontSize"]) for _, d in typo(p) if "fontSize" in d})
    print("fontSizes(px):", sizes)
    q = [sizes[i + 1] / sizes[i] for i in range(len(sizes) - 1)]
    print("ratios       :", [round(x, 3) for x in q])
    if not q: return
    print(f"spread max/min = {max(q) / min(q):.3f}")
    print(f"span max/min   = {sizes[-1] / sizes[0]:.2f}x")
    sq = sorted(q); cl = [[sq[0]]]
    for x in sq[1:]:
        (cl[-1] if x - cl[-1][-1] <= 0.05 else cl.append([]) or cl[-1]).append(x)
    for i, c in enumerate(cl):
        print(f"cluster {i + 1}: n={len(c)} centre={sum(c) / len(c):.3f} members={[round(x, 3) for x in c]}")
    if len(cl) == 2:
        a = sum(cl[0]) / len(cl[0]); b = sum(cl[1]) / len(cl[1]); k = math.log(b) / math.log(a)
        print(f"cluster2 as a power of cluster1: k={k:.2f} a^{round(k)}={a ** round(k):.3f} err={abs(b - a ** round(k)) / b * 100:.1f}%")
def cmd_lh(p):
    print(f"{'token':22} {'fontSize':>9} {'lineHeight':>12} {'multiplier':>11} {'letterSpacing':>14}")
    seen_lh, seen_ls = set(), set()
    for n, d in typo(p):
        fs = px(d.get("fontSize", "")) or 0
        raw = d.get("lineHeight", "-").strip(); lh = px(raw) if raw != "-" else None
        mult = (lh / fs if re.search(r"(px|r?em)", raw) else lh) if lh and fs else None
        ls = d.get("letterSpacing", "-").strip()
        print(f"{n:22} {fs:9.1f} {raw:>12} {(f'{mult:.3f}' if mult else '-'):>11} {ls:>14}")
        seen_lh.add(round(mult, 3) if mult else None); seen_ls.add(ls)
    print(f"distinct lineHeight multipliers: {len(seen_lh)}  distinct letterSpacing values: {len(seen_ls)}")
def cmd_space(p):
    src = fm(p)
    for key in ("spacing", "rounded"):
        vals = [px(v) for _, v in re.findall(r"^[ \t]+([\w-]+):[ \t]*(\S+)", block(src, key), re.M)]
        vals = [v for v in vals if v is not None]
        print(f"{key}: {vals}")
        for base in (2, 4, 8):
            bad = [v for v in vals if abs(v / base - round(v / base)) > 1e-6]
            print(f"   base {base}px -> off-grid: {bad if bad else 'none'}")
def cmd_refs(p):
    src = fm(p); role = {}
    for m in re.finditer(r"^[ \t]{2}([\w-]+):[ \t]*\r?\n((?:[ \t]{3,}.*\r?\n)*)", block(src, "components"), re.M):
        name = m.group(1); props = re.findall(r"([\w-]+):[ \t]*(.+)", m.group(2))
        print(f"{name}  sub-tokens={len(props)} [{', '.join(k for k, _ in props)}]")
        for k, v in props:
            for t in re.findall(r"\{([\w.-]+)\}", v): role.setdefault(t, []).append(f"{name}.{k}")
            if k not in SUB: print(f"   !! '{k}' is not a valid component sub-token")
    print("\nreferenced token -> roles")
    for t, r in sorted(role.items()):
        print(f"  {t:34} x{len(r):<2} {', '.join(r)}")
    for key in ("rounded", "typography", "spacing"):
        used = sorted({t for t in role if t.startswith(key + ".")})
        decl = len(re.findall(r"^[ \t]{2}([\w-]+):", block(src, key), re.M))
        print(f"{key:11} declared={decl:<3} referenced={len(used):<3} {used}")
def cmd_dark(p, suffix="-dark"):
    d = {n: (h, ls) for n, v, h, s, l, ls, c in colors(p)}
    print(f"{'pair':30} {'L*light':>8} {'L*dark':>8} {'100-L*light':>12} {'|diff|':>7} {'dH':>6}")
    for n in list(d):
        if n + suffix in d:
            (h1, l1), (h2, l2) = d[n], d[n + suffix]
            print(f"{n:30} {l1:8.2f} {l2:8.2f} {100 - l1:12.2f} {abs(l2 - (100 - l1)):7.2f} {abs(h1 - h2):6.1f}")
if __name__ == "__main__":
    globals()["cmd_" + sys.argv[1]](*sys.argv[2:])
PY
```

Column meanings: `H`/`S%`/`L%` are HSL; `L*` is CIE lightness (0-100,
approximately perceptually uniform); `C` is chroma measured as
`max(R,G,B) - min(R,G,B)` in 8-bit units, which stays reliable near white and
black where HSL saturation does not.

Invoke as `python3 /tmp/dm-tokens.py <subcommand> <ABSOLUTE-PATH> [arg]`.
Subcommands: `hsl`, `scale`, `lh`, `space`, `refs`, `dark`.

---

## AS-1 — A palette of unrelated hexes instead of a graded ramp

**Prohibited.** Neutral tokens picked one at a time, each hex chosen on its own
merits, with no shared hue bias down the ramp. Includes the pure-grey case:
`#fafafa`, `#eeeeee`, `#cccccc`, `#888888`.

**Why it reads as default.** A derived ramp is one hue held constant while
lightness moves, so every surface in the interface is visibly part of one
material. Independently chosen neutrals drift in hue, and the drift is visible
as soon as two surfaces sit next to each other — a card that is faintly green
on a background that is faintly blue. Pure greys (`C = 0`) drift nowhere but
say nothing: they are the color a system produces when no color was chosen.

**Detection.** Run the inspector restricted to the neutral tokens, and read the
`hue spread` line:

```bash
python3 /tmp/dm-tokens.py hsl <ABSOLUTE-PATH> '^(?!surface-tint$)(.*(surface|outline|background))'
```

Pass condition, both parts:

- hue spread over the selected tokens with `C >= 6` is **≤ 15 degrees**;
- no selected token other than a deliberate `#ffffff` / `#000000` endpoint has
  `C = 0`.

Tokens with `C < 6` are excluded from the hue comparison: at 8-bit precision a
near-white step cannot carry a measurable bias. In `derived.md` the token
`surface: "#fcfcfd"` reports `H 240.0` purely as a rounding artefact of `C = 1`.

`surface-tint` is excluded by name because MD3 defines it as a copy of the
accent, not as a neutral. Run against `assets/template-product-saas.md`, whose
neutrals are warm and whose accent is blue, the bare selector
`'surface|outline|background'` reports `184.6 deg (min 37.5, max 222.1)`; the
selector above reports `1.1 deg (min 37.5, max 38.6)` on the same file. With
the bare selector the number is the wider of the neutral spread and the
neutral-to-accent distance, so it flags a warm-neutral system with a cool
accent and stays silent when the accent shares the neutral hue —
`template-cyrillic.md` reports 10.0 degrees either way. Use the anchored form.

The `hue spread` line as printed for three palettes, each preceded by the
fixture it came from:

```text
derived.md
hue spread, selected tokens with C>=6 (n=4): 8.6 deg  (min 214.3, max 222.9)

slop.md
hue spread, selected tokens with C>=6 (n=4): 12.2 deg  (min 210.0, max 222.2)

unrelated.md
hue spread, selected tokens with C>=6 (n=2): 163.3 deg  (min 76.7, max 240.0)
```

The failing palette was:

```yaml
  surface: "#fafafa"
  surface-container: "#eeeeee"
  outline: "#cccccc"
  on-surface-variant: "#8a8f7d"
  on-surface: "#2b2b33"
```

Three of the five neutrals report `C = 0` and the two that carry any hue at all
land 163 degrees apart. Note that `slop.md` passes this check — it copied a
ramp that someone else derived. AS-1 and AS-10 are complementary, not
redundant.

---

## AS-2 — A neutral ramp with even lightness steps

**Prohibited.** A neutral ramp whose lightness steps are all the same size.

**Why it reads as default.** An interface does not use lightness evenly. In a
light theme the page background, the raised container, the hover fill and the
hairline all live within a few L* of white; the mid-tones carry one or two
roles at most. An evenly spaced ramp spends its steps where nothing needs them
and leaves the top of the range with a single step, so every surface plane in
the finished screen ends up the same color and the depth in the design
disappears. Even steps are what a loop produces, not what a screen needs.

**Detection.** Read the `L* ladder` block of the same command as AS-1 and
divide the largest step by the smallest.

```bash
python3 /tmp/dm-tokens.py hsl <ABSOLUTE-PATH> '^(?!surface-tint$)(.*(surface|outline|background))'
```

Pass condition, both parts:

- `max(step) / min(step) >= 2.0` across the neutral ladder, counting only the
  non-zero steps;
- at least three neutral steps sit above `L* 85`.

Drop the zero steps before dividing. Two tokens holding one hex print
`step=  0.00`, and a zero denominator makes the ratio undefined rather than
large. This is not an edge case: `background` equal to `surface`, or
`inverse-on-surface` equal to `surface-container-lowest`, is ordinary MD3
practice, and each of the four templates in `assets/` prints at least one such
row.

Two measured reference ramps, both computed with the `lstar` function above:

| Ramp | L* steps | max/min |
| :--- | :--- | :--- |
| Equal 8-bit greys `#ffffff` … `#1f1f1f`, step 32 | 11.18, 11.48, 11.85, 12.30, 12.88, 13.67, 14.89 | 1.33 |
| Tailwind 3.4.17 `slate`, 50 through 950 | 1.83, 4.58, 6.91, 18.37, 18.14, 12.63, 8.58, 10.74, 8.43, 6.11 | 10.0 |

Equal steps in the source values produce near-equal steps in L* — the ratio
1.33 is the signature to reject. The framework ramp packs four steps into the
range above `L* 84` and jumps 18 L* through the mid-tones, giving a ratio of
10. It is measured here because its steps were distributed by hand, and the
measurement describes that shape only — the values themselves are forbidden by
AS-10.

`derived.md` measures:

```text
L* ladder, lightest first
  surface                    #fcfcfd   L*= 98.99 C=  1
  surface-container          #f5f6f7   L*= 96.84 C=  2  step=  2.15
  surface-container-high     #ecedef   L*= 93.72 C=  3  step=  3.11
  outline-variant            #d8dadf   L*= 87.03 C=  7  step=  6.69
  outline                    #a5abb6   L*= 69.83 C= 17  step= 17.20
  on-surface-variant         #636d7e   L*= 45.77 C= 27  step= 24.06
  on-surface                 #242a32   L*= 16.80 C= 14  step= 28.96
```

Ratio 28.96 / 2.15 = 13.5, four steps above L* 85. Passes.

---

## AS-3 — The platform UI font as the chosen family

**Prohibited.** `system-ui`, `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`,
`Roboto`, `Helvetica`, `Helvetica Neue`, `Arial`, `Times New Roman`,
`ui-sans-serif`, `ui-serif`, `ui-monospace`, or a bare `sans-serif` / `serif` /
`monospace` as the **first** family in any `fontFamily` value.

**Why it reads as default.** These are the faces a browser reaches for when a
document specifies nothing. A DESIGN.md exists to record what was specified.
Naming the fallback as the choice produces a file that is indistinguishable, on
screen, from a file with no `typography` section at all — while costing the
reader the effort of reading one. It also silently ties the design's letterform
to the reader's operating system, so the same file renders as three different
typefaces on three machines.

Legitimate use: these names appearing **after** a real family, as a fallback
stack. The prohibition is on the first position only.

**Detection.**

```bash
grep -nE 'fontFamily:[[:space:]]*"?(system-ui|-apple-system|BlinkMacSystemFont|Segoe UI|Roboto|Helvetica( Neue)?|Arial|Times( New Roman)?|ui-sans-serif|ui-serif|ui-monospace|sans-serif|serif|monospace)\b' <ABSOLUTE-PATH>
```

Pass condition: exit status 1 (no match). Measured:

```text
### fontFamily grep on slop.md
17:    fontFamily: "system-ui"
23:    fontFamily: "system-ui"
29:    fontFamily: "system-ui"
35:    fontFamily: "system-ui"
exit=0

### same grep on derived.md
exit=1
```

When the file must serve Cyrillic text the replacement is constrained further:
a family with no Cyrillic block falls back to a system face on Russian text,
which reintroduces this defect by another route, silently and only for those
readers. Families verified to carry Cyrillic on Google Fonts: Golos Text,
Onest, Inter, IBM Plex Sans, JetBrains Mono, Manrope. Verify coverage by
subset, not by the family's name — Instrument Serif and Bodoni Moda ship
`latin` and `latin-ext` only.

---

## AS-4 — A type scale of arbitrary numbers

**Prohibited.** `fontSize` values chosen individually rather than generated
from one ratio.

**Why it reads as default.** A modular scale makes the relationship between a
heading and its body text reproducible: any new size is derived, not invented,
and two designers extending the file land on the same number. Hand-picked sizes
have no rule behind them, so every later addition is another invention, and the
sizes converge on the round numbers everybody reaches for — 12, 14, 16, 24, 32
— which is the default look expressed in numbers.

**Detection.**

```bash
python3 /tmp/dm-tokens.py scale <ABSOLUTE-PATH>
```

The arithmetic: sort the distinct `fontSize` values in px, ascending, as
`s0 < s1 < … < sn`; form the successive ratios `q_i = s_(i+1) / s_i`; sort the
`q_i` and cut a new cluster wherever the gap to the previous ratio exceeds
0.05. Pass condition, one of:

- **one cluster** — a single consistent step; or
- **two clusters**, where the second cluster's centre is within **4 percent**
  of the first cluster's centre raised to an integer power. This is a scale
  with a deliberately skipped step, which is legitimate: a display size two
  steps above the last heading is a decision, not a lapse.

Three or more clusters means the numbers were picked one at a time.

Measured, a scale of 11/13/16/23/33 px:

```text
fontSizes(px): [11.0, 13.0, 16.0, 23.0, 33.0]
ratios       : [1.182, 1.231, 1.438, 1.435]
spread max/min = 1.216
span max/min   = 3.00x
cluster 1: n=2 centre=1.206 members=[1.182, 1.231]
cluster 2: n=2 centre=1.436 members=[1.435, 1.438]
cluster2 as a power of cluster1: k=1.93 a^2=1.455 err=1.3%
```

Two clusters, the second within 1.3 percent of the first squared. Passes.

Measured, a scale of 13/16/21/30 px:

```text
fontSizes(px): [13.0, 16.0, 21.0, 30.0]
ratios       : [1.231, 1.312, 1.429]
spread max/min = 1.161
span max/min   = 2.31x
cluster 1: n=1 centre=1.231 members=[1.231]
cluster 2: n=1 centre=1.312 members=[1.312]
cluster 3: n=1 centre=1.429 members=[1.429]
```

Three clusters, each with one member. Fails.

Two honest limits of this check:

- **Do not fit a free ratio to the set.** Measured across eight candidate
  scales, allowing `r` to range from 1.05 upward makes every set fit
  `s0 * r^k` within 2 percent, including deliberately arbitrary ones. A free
  fit accepts everything and detects nothing.
- **Over a narrow span the check is blind.** An arithmetic ramp of
  12/14/16/18/20/22 px yields ratios 1.100 … 1.167, one cluster, and passes.
  The discriminator there is the `span max/min` line: a file whose largest
  `fontSize` is under 2× its smallest has no display tier at all, which is a
  separate defect. Require `span >= 2.5x` for any file that describes a page
  rather than a dense control panel.

---

## AS-5 — One line height for every size

**Prohibited.** The same `lineHeight` on every typography token.

**Why it reads as default.** Line height is a function of measure and size. A
display size set at the same multiplier as caption text opens gaps inside the
heading that break it into separate lines of unrelated words, while the caption
stays too loose to scan. A single multiplier across a 3× size range is
the value a template ships with, not a decision about how this text reads.

**Detection.**

```bash
python3 /tmp/dm-tokens.py lh <ABSOLUTE-PATH>
```

Pass condition: `distinct lineHeight multipliers` is at least 3 when the file
declares 4 or more typography tokens, and the token with the largest `fontSize`
carries the smallest multiplier in the table.

Read the two ends, not the sequence. The relation is not monotonic in a written
file: a label or a caption is set tighter than body text at a smaller size, so
`template-cyrillic.md` sets `label-md` (14px) at 1.20 while `body-md` (16px) is
at 1.55. All four templates in `assets/` break monotonicity somewhere and all
four keep the largest size at the tightest multiplier. Measured failure:

```text
token                   fontSize   lineHeight  multiplier  letterSpacing
display-lg                  30.0          1.5       1.500            0px
title-md                    21.0          1.5       1.500            0px
body-md                     16.0          1.5       1.500            0px
label-sm                    13.0          1.5       1.500            0px
distinct lineHeight multipliers: 1  distinct letterSpacing values: 1
```

The inspector normalises a `px`/`em`/`rem` line height into a multiplier, so
the check works either way. Note one export consequence recorded in
`references/export-formats.md`: a unitless `lineHeight` is dropped by
`export --format css-tailwind`. That affects the export target, not this check.

---

## AS-6 — One letter spacing for every size

**Prohibited.** The same `letterSpacing` value on every typography token,
including the common case of `letterSpacing: 0` or `0px` repeated throughout.

**Why it reads as default.** Type designers space a face for text sizes. At
display sizes those spaces are proportionally too wide and the word looks
loose; at caption sizes and in uppercase they are too tight to read. A constant
across the whole scale asserts that none of that was considered, and an
explicit `0` asserts it more loudly than omitting the property, because it
overrides the type designer's own spacing with nothing.

Omitting `letterSpacing` entirely on body text is not a defect: it records "use
the face as drawn", which is a defensible decision. The defect is the constant.

**Detection.** Same command as AS-5; read the last line and the
`letterSpacing` column.

```bash
python3 /tmp/dm-tokens.py lh <ABSOLUTE-PATH>
```

Pass condition: `distinct letterSpacing values` is at least 2, and any token
with `fontSize >= 32` carries a negative value. Verified separately:
`letterSpacing: 0` lints clean at 0 errors, so the linter will not raise this.
Measured passing table:

```text
token                   fontSize   lineHeight  multiplier  letterSpacing
display-lg                  33.0         1.15       1.150        -0.02em
title-md                    23.0         1.25       1.250        -0.01em
body-md                     16.0         1.55       1.550              -
label-sm                    13.0         1.35       1.350         0.01em
caption-xs                  11.0          1.4       1.400         0.02em
distinct lineHeight multipliers: 5  distinct letterSpacing values: 5
```

---

## AS-7 — One radius for every element

**Prohibited.** Every component referencing the same `rounded` token. Equally
prohibited: declaring a radius ramp of three or more steps and referencing only
one of them.

**Why it reads as default.** Corner radius is one of the few shape signals the
format carries, and it separates element classes: a control, a container and a
pill are different objects and read as different objects partly through their
corners. Applying one value to all of them removes that separation, and the
value chosen is almost always 8px, which is the radius every default component
library ships. A declared-but-unused ramp is worse than a single value: it
claims a shape system exists while the components prove it does not.

**Detection.**

```bash
python3 /tmp/dm-tokens.py refs <ABSOLUTE-PATH>
```

Pass condition, both parts, when the file declares 4 or more components:

- `rounded referenced` is at least 2;
- every declared radius that no component references is accounted for in the
  body prose — a state, a size variant, a surface the component list does not
  cover.

`omitted` cannot carry the second part. It accepts section names only —
`colors`, `typography`, `spacing`, `rounded`, `components` — and a token name
placed there is reported: `omitted: [rounded.xl]` returns
`unknown section name 'rounded.xl' in omitted key` under `unknown-omission`,
a warning, verified. An unreferenced step with no prose behind it is a claim
the file does not keep, and the four templates in `assets/` each leave one to
three radii unreferenced and name their purpose in the Shapes section.

Measured failure:

```text
  rounded.md                         x4  button-primary.rounded, card.rounded, badge.rounded, input.rounded
rounded     declared=3   referenced=1   ['rounded.md']
```

Three radii declared; every one of the four components uses the same one.

---

## AS-8 — A spacing scale off any base unit

**Prohibited.** `spacing` values that are not all multiples of one base unit.

**Why it reads as default.** A spacing scale is what makes independently built
screens align. When the values share no divisor, nothing lines up between
components and the layout is corrected by eye later, one element at a time —
which is exactly the state the file was written to prevent. Values such as 5,
9, 14, 22 look deliberate precisely because they are not round, and they are
the signature of numbers produced to look non-obvious rather than derived.

**Detection.**

```bash
python3 /tmp/dm-tokens.py space <ABSOLUTE-PATH>
```

Pass condition: `base 4px -> off-grid: none` for the `spacing` map. A 2px base
is acceptable only for a file that declares a dense control-panel product; an
8px base is acceptable but leaves no half-step, so most files that pass at 8
also pass at 4. Measured failure:

```text
spacing: [5.0, 9.0, 14.0, 22.0, 30.0]
   base 2px -> off-grid: [5.0, 9.0]
   base 4px -> off-grid: [5.0, 9.0, 14.0, 22.0, 30.0]
   base 8px -> off-grid: [5.0, 9.0, 14.0, 22.0, 30.0]
```

Measured pass:

```text
spacing: [4.0, 8.0, 16.0, 24.0, 40.0]
   base 2px -> off-grid: none
   base 4px -> off-grid: none
   base 8px -> off-grid: [4.0]
```

The same command prints the `rounded` map. A pill radius such as `full: 999px`
is expected to appear off-grid; that is the one exemption.

---

## AS-9 — An accent used in more than one role

**Prohibited.** One accent token carrying more than one meaning: the fill of an
action and the fill of a status, or the fill of a control and the color of
running-text links.

The test is the meaning the color signals, not the sub-token slot it occupies.
A filled button and its ghost variant are one meaning — MD3 defines `primary`
to serve as both the fill of the filled button and the label color of the text
button, and `template-cyrillic.md` ships exactly that pair. A slot change is
not the defect.

**Why it reads as default.** An accent is a signal, and a signal works by
scarcity. When the same color fills the primary button, fills the status
badge and colors every link, the user cannot learn what it means, so it stops
meaning anything and reverts to decoration. The file is then carrying a brand
color with no job. Files that make this mistake usually also declare
`secondary` and `tertiary` and then never reference them. Nothing reports
that: `orphaned-tokens` skips any token whose family is in the MD3 baseline
set, and `secondary` and `tertiary` are both in it. The unused accents stay
silent, so this check is the only thing standing between the file and a
one-color system.

**Detection.**

```bash
python3 /tmp/dm-tokens.py refs <ABSOLUTE-PATH>
```

Read the `referenced token -> roles` table. Pass condition: for each accent
token, every component listed carries the **same** meaning — one action, one
status, one mark. Measured failure:

```text
  colors.primary                     x3  button-primary.backgroundColor, link.textColor, badge.backgroundColor
```

Three references across three families: an action, a link and a status. The
color therefore signals three things and so signals none. Compare the passing
shape, measured on `assets/template-cyrillic.md`:

```text
  colors.primary                     x2  button-primary.backgroundColor, button-ghost.textColor
```

Two slots, one family, one meaning — the primary action. Without the inspector,
a count alone is a weaker but usable signal:

```bash
grep -cE '\{colors\.primary\}' <ABSOLUTE-PATH>
```

which returned `3` on the failing file and `2` on `template-cyrillic.md`. A
count above 2 warrants reading the components; it does not decide them.

---

## AS-10 — Values copied from popular defaults

**Prohibited.** Any of the hexes below, in the frontmatter or in the body
prose.

Every value in this table was read out of the published package on 2026-08-28,
not recalled:

| Source | Verified at | Values |
| :--- | :--- | :--- |
| Tailwind CSS 3.4.17 | `src/public/colors.js` | blue-500 `#3b82f6`, blue-600 `#2563eb`, blue-700 `#1d4ed8`, indigo-500 `#6366f1`, indigo-600 `#4f46e5`, violet-500 `#8b5cf6`, violet-600 `#7c3aed`, red-500 `#ef4444`, red-600 `#dc2626`, emerald-500 `#10b981`, emerald-600 `#059669`, amber-500 `#f59e0b`, amber-600 `#d97706`, green-500 `#22c55e`, green-600 `#16a34a`, purple-500 `#a855f7`, sky-500 `#0ea5e9`, teal-500 `#14b8a6`, orange-500 `#f97316`, rose-500 `#f43f5e`, pink-500 `#ec4899`, cyan-500 `#06b6d4`, lime-500 `#84cc16`, yellow-500 `#eab308`, fuchsia-500 `#d946ef` |
| Tailwind CSS 3.4.17, slate ramp | same | `#f8fafc` `#f1f5f9` `#e2e8f0` `#cbd5e1` `#94a3b8` `#64748b` `#475569` `#334155` `#1e293b` `#0f172a` `#020617` |
| Tailwind CSS 3.4.17, gray ramp | same | `#f9fafb` `#f3f4f6` `#e5e7eb` `#d1d5db` `#9ca3af` `#6b7280` `#4b5563` `#374151` `#1f2937` `#111827` `#030712` |
| Tailwind CSS 3.4.17, other neutrals | same | zinc-500 `#71717a`, neutral-500 `#737373`, stone-500 `#78716c`, zinc-50 / neutral-50 `#fafafa` |
| Bootstrap 5.3.3 | `scss/_variables.scss` | `$blue` and `$primary` `#0d6efd`, `$indigo` `#6610f2`, `$purple` `#6f42c1`, `$pink` `#d63384`, `$red` / `$danger` `#dc3545`, `$orange` `#fd7e14`, `$yellow` / `$warning` `#ffc107`, `$green` / `$success` `#198754`, `$teal` `#20c997`, `$cyan` / `$info` `#0dcaf0`, gray-100 `#f8f9fa`, gray-200 `#e9ecef`, gray-300 `#dee2e6`, gray-400 `#ced4da`, gray-500 `#adb5bd`, gray-600 / `$secondary` `#6c757d`, gray-700 `#495057`, gray-800 `#343a40`, gray-900 / `$dark` `#212529` |
| Material, MDC Web `@material/theme` 14.0.0 | `_theme-color.scss` | `$primary` `#6200ee` (line 136, "baseline purple, 500 tone"), `$accent` `#018786`, `$error` `#b00020` |
| Material 2014 palette, `material-colors` 1.2.6 | `dist/colors.json` | indigo-500 `#3f51b5`, blue-500 `#2196f3`, purple-500 `#9c27b0`, teal-500 `#009688`, red-500 `#f44336` |

**Why it reads as default.** These values are the visual identity of the
frameworks that ship them. A reader who has used the web recognises
`#3b82f6` on a button as "a Tailwind app" before reading a word of the page, so
the file's `name` and `description` are contradicted by its first pixel. There
is a second, mechanical reason: these accents were tuned for the framework's
own text color, not for yours. Measured against `#ffffff` with the same
formula the linter uses:

| Accent | Contrast with `#ffffff` | Clears AA 4.5:1 |
| :--- | ---: | :--- |
| Tailwind amber-500 `#f59e0b` | 2.15:1 | no |
| Tailwind emerald-500 `#10b981` | 2.54:1 | no |
| Material blue-500 `#2196f3` | 3.12:1 | no |
| Tailwind blue-500 `#3b82f6` | 3.68:1 | no |
| Tailwind red-500 `#ef4444` | 3.76:1 | no |
| Tailwind indigo-500 `#6366f1` | 4.47:1 | no |
| Bootstrap `#0d6efd` | 4.50:1 | yes, by 0.0008 |
| Tailwind blue-600 `#2563eb` | 5.17:1 | yes |
| Material `#6200ee` | 7.63:1 | yes |

Six of the nine fall below WCAG AA 4.5:1. The seventh, Bootstrap's `#0d6efd`,
computes to 4.500783 and clears the threshold by 0.0008 — a margin that
disappears the moment anyone nudges the hue. The linter agrees with these
figures to the second decimal: a component pairing `#ffffff` on `#6366f1`
produced
`textColor (#ffffff) on backgroundColor (#6366f1) has contrast ratio 4.47:1,
below WCAG AA minimum of 4.5:1.` So this is the one prohibition the linter
partly enforces, and only by accident.

**Detection.**

```bash
grep -inE '#(3b82f6|2563eb|1d4ed8|6366f1|4f46e5|8b5cf6|7c3aed|a855f7|ef4444|dc2626|10b981|059669|22c55e|16a34a|f59e0b|d97706|0ea5e9|14b8a6|f97316|f43f5e|ec4899|06b6d4|84cc16|eab308|d946ef|f8fafc|f1f5f9|e2e8f0|cbd5e1|94a3b8|64748b|475569|334155|1e293b|0f172a|020617|f9fafb|f3f4f6|e5e7eb|d1d5db|9ca3af|6b7280|4b5563|374151|1f2937|111827|030712|71717a|737373|78716c|fafafa|0d6efd|6610f2|6f42c1|d63384|dc3545|fd7e14|ffc107|198754|20c997|0dcaf0|f8f9fa|e9ecef|dee2e6|ced4da|adb5bd|6c757d|495057|343a40|212529|6200ee|018786|b00020|3f51b5|2196f3|9c27b0|009688|f44336)\b' <ABSOLUTE-PATH>
```

Pass condition: exit status 1 (no match). Measured:

```text
### slop.md
6:  primary: "#3b82f6"
8:  secondary: "#6366f1"
9:  error: "#ef4444"
11:  surface-container: "#f1f5f9"
12:  on-surface: "#0f172a"
13:  on-surface-variant: "#64748b"
14:  outline: "#e2e8f0"
77:Primary is #3b82f6. Surface is #ffffff. On-surface is #0f172a.
78:The outline color is #e2e8f0.
### derived.md
derived exit=1
```

The grep also finds these values in the body prose, which is where they survive
after the frontmatter has been fixed.

---

## AS-11 — A dark set that is the light palette with inverted lightness

**Prohibited.** A second set of color tokens produced by mapping each light
token's lightness `L` to `100 - L` while holding hue and saturation.

**Why it reads as default.** The transform is mechanical, so the dark set
encodes no decision that the light set did not already contain — anything a
reviewer can compute from the light theme is not a design. It also breaks the
one thing a dark theme needs: inverting a near-white base surface produces
`#020203`, which is black, and depth in a dark interface is expressed by making
surfaces *lighter* than their background, not by shadow. Every value in the
Elevation & Depth section stops working at once, because there is nothing
darker than the base to cast against.

**Detection.** Name the dark tokens with a consistent suffix, then:

```bash
python3 /tmp/dm-tokens.py dark <ABSOLUTE-PATH> -dark
```

Pass condition: for at least one pair, `|diff| > 5` **or** `dH > 2`. A dark set
in which every pair satisfies `|diff| <= 5` and `dH == 0` is an inversion.
Measured signature:

```text
pair                            L*light   L*dark  100-L*light  |diff|     dH
surface                           98.99     0.57         1.01    0.44    0.0
surface-container                 96.84     2.43         3.16    0.73    0.0
outline                           69.83    33.45        30.17    3.28    0.0
on-surface                        16.80    84.32        83.20    1.12    0.0
```

Four pairs, maximum deviation 3.28 L*, hue identical throughout, base surface
at `L* 0.57`. Note the mirrored contrast is not itself the tell: the light pair
measures 14.10:1 and its inversion 13.76:1, which is why the arithmetic above
tests the transform, not the ratio.

---

## AS-12 — A scale declared but never referenced

**Prohibited.** A `typography`, `spacing` or `rounded` map that no component
references, in a file that defines components.

**Why it reads as default.** An unreferenced scale is a list, not a system. It
tells an implementing agent that eight type sizes exist but not which one a
button label uses, so the agent picks, and it picks the default. The file then
reads as complete while delegating every actual decision back to the reader.
This is the most common way a long DESIGN.md turns out to specify nothing.

**Detection.**

```bash
python3 /tmp/dm-tokens.py refs <ABSOLUTE-PATH>
```

Pass condition, for a file with components: `referenced >= 1` on every line,
and `referenced >= 2` for `typography`. Measured failure:

```text
rounded     declared=3   referenced=1   ['rounded.md']
typography  declared=4   referenced=0   []
spacing     declared=5   referenced=0   []
```

Four type sizes and five spacing steps, bound to nothing. `spacing` reaches
components only through the `padding`, `size`, `height` and `width` sub-tokens;
`typography` through the `typography` sub-token. If a file legitimately defines
no components, declare that in `omitted` and this entry does not apply.

---

## AS-13 — Component entries that restate the colors map

**Prohibited.** A component whose sub-tokens are a subset of
`{backgroundColor, textColor}` and whose values are the surface/on-surface pair
already implied by its name.

**Why it reads as default.** `card: {backgroundColor: {colors.surface},
textColor: {colors.on-surface}}` adds no information: the colors map already
said that on-surface goes on surface. The component exists to record what makes
*this* element different — its radius, its padding, its type token, its own
fill. A component list made of such entries inflates the `token-summary` count
while leaving the implementing agent to invent every dimension.

**Detection.**

```bash
python3 /tmp/dm-tokens.py refs <ABSOLUTE-PATH>
```

Pass condition: `sub-tokens >= 3` for every component, and no component listing
only `[backgroundColor, textColor]`. Measured, on a file that mostly passes:

```text
button-primary  sub-tokens=3 [backgroundColor, textColor, rounded]
card  sub-tokens=3 [backgroundColor, textColor, rounded]
link  sub-tokens=1 [textColor]
badge  sub-tokens=3 [backgroundColor, textColor, rounded]
input  sub-tokens=3 [backgroundColor, textColor, rounded]
```

`link` carries one sub-token and is the entry to challenge. The valid sub-token
set is closed at eight names; the same command flags any invented one with a
`!!` line, which the linter also reports as a `broken-ref` warning.

---

## AS-14 — Unitless dimensions

**Prohibited.** A `spacing`, `rounded`, `fontSize` or `letterSpacing` value
written as a bare number: `md: 16` rather than `md: 16px`.

**Why it reads as default.** The value is silently discarded — the whole token
in `spacing` and `rounded`, the size alone in `typography`. The file still
exits 0, and the implementing agent falls back to its own defaults for whatever
went missing, which is the default look arriving through a typo. This is the
cheapest way to ship a file that appears to specify a scale and specifies
nothing.

**Detection.** Two signals; use both.

First, compare the `token-summary` counts against what the file declares:

```bash
cd /tmp && npx --yes @google/design.md@0.4.0 lint <ABSOLUTE-PATH>
```

Verified on a file declaring `spacing: {a: 16, b: 16px, c: 1rem, d: "16"}` and
`rounded: {md: 8}`:

```text
      "message": "Design system defines 1 color, 2 spacing tokens.",
      "rule": "token-summary"
```

```text
      "path": "rounded",
      "message": "No 'rounded' section defined. Corner rounding will fall back to agent defaults.",
      "rule": "missing-sections"
```

Two of the four spacing tokens survived; the entire `rounded` map vanished.
Exit code was 0.

Second, confirm against an export, which lists exactly the tokens that exist:

```bash
cd /tmp && npx --yes @google/design.md@0.4.0 export <ABSOLUTE-PATH> --format css-vars
```

```text
:root {
  --color-primary: #1f718e;
  --spacing-b: 16px;
  --spacing-c: 1rem;
}
```

Only the two spacing tokens that carried a unit exist.

**The counts do not catch this inside `typography`.** A token with a unitless
`fontSize` still counts as a typography scale, because the token itself exists;
what vanishes is the size. Verified on a file whose `a-unitless` token carried
`fontSize: 16` and `letterSpacing: 0` while `b-px` carried `16px` and
`-0.02em`, the lint reported
`Design system defines 1 color, 2 typography scales, 1 rounding level, 1 spacing token.`
and

```bash
cd /tmp && npx --yes @google/design.md@0.4.0 export <ABSOLUTE-PATH> --format css-tailwind
```

reported:

```text
@theme {
  --color-primary: #1f718e;
  --font-a-unitless: "Onest";
  --font-b-px: "Onest";
  --text-b-px: 16px;
  --tracking-b-px: -0.02em;
  --radius-md: 8px;
  --spacing-md: 16px;
}
```

No `--text-a-unitless` and no `--tracking-a-unitless`. Use `css-tailwind` for
this check, not `css-vars`: `css-vars` emits no typography variables at all.

Pass condition, both parts: the `token-summary` counts equal the number of keys
you wrote in `colors`, `spacing`, `rounded` and `components`; and the
`css-tailwind` export carries a `--text-*` variable for every typography token
that declares a `fontSize`. Units are `px`, `em` and `rem`; nothing else
parses. The one legitimate exception is `lineHeight`, where a unitless number
is a multiplier and is accepted by the linter — it is dropped by
`css-tailwind` too, which is an export limitation, not a defect in the file.

---

## AS-15 — Do's and Don'ts made of universal truisms

**Prohibited.** A Do's and Don'ts section whose entries would remain true, word
for word, in a different product's DESIGN.md.

**Why it reads as default.** The section is the only place in the format where
the file states what its own rules forbid. Filling it with advice that applies
to every interface ever built converts the one product-specific section into
the most generic one, and gives an implementing agent no constraint it did not
already hold. Truisms also read as complete, which stops anyone from writing
the real rules later.

Recognise these four shapes; they are the ones that appear most often:

- "Do maintain consistent spacing."
- "Do ensure sufficient contrast for accessibility."
- "Don't use too many colors."
- "Don't mix too many font sizes."

**Detection.** The definitive test is substitution: paste the section into an
unrelated product's DESIGN.md and change nothing. If every line is still true,
every line is filler.

The mechanical proxy is an anchor count — a real rule names a token, a value or
a component. Collect one rule per line first, because a rule wraps and its
anchor often sits on the continuation line:

```bash
awk '/^## Do.s and Don.ts/{f=1;next} /^## /{f=0} f' <ABSOLUTE-PATH> \
| awk '/^([-*][ \t]|[0-9]+\.[ \t]|\*\*Do[^*]*\*\*[ \t]+[^ \t])/{if(n)print b; b=$0; n=1; next}
       n&&NF{b=b" "$0; next} {if(n)print b; n=0} END{if(n)print b}' > /tmp/dm-rules.txt
grep -c . /tmp/dm-rules.txt
grep -cE '`[^`]+`|#[0-9a-fA-F]{3,8}|[0-9]+(px|rem|em)|[0-9.]+:1' /tmp/dm-rules.txt
```

The first `awk` cuts the section; the second folds it into one rule per line,
recognising the three shapes a DESIGN.md actually uses — a `-` bullet, an
ordered item, and a `**Do** …` / `**Don't** …` paragraph. A bare `**Do.**`
heading carries no text after the closing `**` and is not counted as a rule. A
pattern matching `- ` alone reports 0 rules and 0 anchors on a section written
as an ordered list or as `**Do**` paragraphs, which reads as a pass and is not
one: three of the four templates in `assets/` are written that way.

Pass condition: the second count equals the first, or every rule the second
count misses is read individually and survives the substitution test. Zero
anchored rules against a non-zero rule count is filler outright. The two
commands print, in order, the rule count and the anchored count; measured on
the four truisms above:

```text
4
0
```

Measured on the four templates in `assets/`, which between them use all three
shapes:

| File | rules | anchored |
| :--- | ---: | ---: |
| `template-cyrillic.md` | 21 | 20 |
| `template-editorial.md` | 18 | 18 |
| `template-product-saas.md` | 17 | 16 |
| `template-skeleton.md` | 9 | 9 |

The two unmatched rules name their product in words rather than in tokens —
`Cap prose measure at 68 characters measured on Russian text, not the Latin 75.`
is one of them, and it is not a truism. So an unanchored rule is a line to read,
not a verdict, and an anchored rule can still be a truism: the count is a lower
bound on the substitution test, not a replacement for it. Note that `grep -c`
exits 1 when it prints `0`, so read the printed count, not the exit status.

---

## AS-16 — Prose that restates the token values

**Prohibited.** Body sections that repeat what the frontmatter already says.

**Why it reads as default.** The frontmatter is machine-readable and exact; a
sentence restating it is strictly redundant and cannot be verified against
anything. The body exists to hold what YAML cannot: why this hue, what the
accent is reserved for, which rule an implementer must not break, what was
measured. A file whose prose is a transcription of its own tokens has recorded
zero reasoning, so every future edit is made blind and reverts to the default.

**Detection.** Extract each body section and look for a hex or a dimension
appearing without a reason attached:

```bash
awk '/^---$/{n++;next} n>=2' <ABSOLUTE-PATH> | grep -nE '#[0-9a-fA-F]{6}|[0-9]+(px|rem)' | grep -vEi 'because|so that|to keep|to avoid|reserved|only|never|reads|below|above|at least|instead'
```

Pass condition: every line the command prints, read with the lines around it,
either sits in a table row or has a reason attached to its value. Expect output
on a good file. The stop-word list names twelve ways to write a reason and
prose writes them in more — `sits inside a 224°–234° band`, `a three-point
spread between the red and blue channels` both survive the filter. `grep` is
also line-based, so a reason on the next line does not suppress the hit:
`template-skeleton.md` is flagged for `Six levels: none 0px, xs 2px, sm 4px,
md 8px, lg 16px, full 999px.` and answers it on the following line with `The
measured steps double: 2 → 4 → 8 → 16.` Measured on the four templates, the
command prints 35 to 87 lines per file, 18 to 40 of them outside tables. The
filter is a first cut, not a verdict.

What fails is narrower: a sentence whose entire content is the value, so that
deleting it loses nothing the frontmatter did not already say. The `awk` strips
the frontmatter, so the numbers `grep -n` prints count body lines, not file
lines. Measured:

```text
8:Primary is #3b82f6. Surface is #ffffff. On-surface is #0f172a.
9:The outline color is #e2e8f0.
13:The type scale runs 13px, 16px, 21px, 30px. Line height is 1.5.
25:Everything is rounded 8px.
```

Four lines, every one of them a transcription of a token two screens above in
the same file, and none of them survives the deletion test. Only `##`
headings are collected by the parser, so a section demoted to `###` is invisible
to `section-order` and easy to overlook when auditing; check the whole body,
not the headings the linter reports on.

---

## Limits of these checks

Stated plainly, so the checklist is not mistaken for a quality gate:

- Every signal here is **necessary, not sufficient**. A file can pass all
  sixteen and still be wrong for its product: the checks measure internal
  consistency and distance from known defaults, not fitness.
- Nothing here judges whether the chosen hue suits the brand, whether the
  typeface is licensed for the deployment, or whether the accent means what the
  Overview claims it means. Those are read by a person.
- The thresholds (15 degrees, ratio 2.0, a 0.05 cluster gap, 4 percent, 5 L*)
  were calibrated against the fixtures measured in this file. They separate the
  cases shown. They are not published constants, and a file that misses one by
  a small margin warrants reading, not rewriting.
- AS-1 and AS-2 do not separate a derived ramp from one derived by someone
  else. The Tailwind 3.4.17 `gray` ramp copied whole measures a 9.0 degree hue
  spread and a step ratio of 9.2, passing both. Its `slate` ramp passes AS-2 at
  10.0 and misses AS-1 at 18.6 degrees across all eleven steps — but the
  four-token subset a real file uses, the one in `slop.md`, measures 12.2 and
  passes. AS-10 is what catches copied values.
- The inspector parses the frontmatter with regexes, not a YAML parser. It
  reads flat maps and one level of nesting, which is the whole schema. It will
  misread deliberately exotic YAML (anchors, flow mappings, multi-line
  scalars); if a count looks wrong, check the file's shape before the finding.
- The inspector's key pattern is `[\w-]+`, which does not match a quoted key.
  `"2xl": 32px` is invisible to `space` and to the `declared=` counts in
  `refs`: on `assets/template-skeleton.md` both report five spacing tokens
  where `token-summary` reports seven. Compare a `declared=` line against the
  linter's count before acting on it.

---

## Self-audit checklist

Run this against the finished file before handing it over. `F` is the absolute
path. Steps 1 and 2 are text matches; step 3 calls the CLI; steps 4-14 need
`/tmp/dm-tokens.py` from the Setup section; steps 15 and 16 end in a judgement
you make by eye.

1. **No copied defaults.** `grep -inE '#(3b82f6|…|f44336)\b' "$F"` — the full
   pattern is in AS-10. Exit status 1.
2. **No default UI font.** The `fontFamily` grep from AS-3. Exit status 1.
3. **No unitless dimensions.** `cd /tmp && npx --yes @google/design.md@0.4.0 export "$F" --format css-tailwind` carries a `--spacing-*` and `--radius-*` variable for every key you wrote, and a `--text-*` for every typography token with a `fontSize` (AS-14).
4. **Neutral hue bias.** `python3 /tmp/dm-tokens.py hsl "$F" '^(?!surface-tint$)(.*(surface|outline|background))'` — hue spread ≤ 15 degrees over tokens with `C >= 6`; no non-endpoint token at `C = 0` (AS-1).
5. **Ramp distribution.** Same output — `max(step)/min(step) >= 2.0` over the non-zero steps, and at least three steps above `L* 85` (AS-2).
6. **Type scale.** `python3 /tmp/dm-tokens.py scale "$F"` — one ratio cluster, or two where the second is within 4 percent of an integer power of the first; `span >= 2.5x` unless the file describes a dense control panel (AS-4).
7. **Line height varies.** `python3 /tmp/dm-tokens.py lh "$F"` — at least 3 distinct multipliers, the largest `fontSize` on the smallest one (AS-5).
8. **Letter spacing varies.** Same output — at least 2 distinct values, negative on any size ≥ 32px (AS-6).
9. **Spacing on a base unit.** `python3 /tmp/dm-tokens.py space "$F"` — `base 4px -> off-grid: none` for `spacing` (AS-8).
10. **Radius plurality.** `python3 /tmp/dm-tokens.py refs "$F"` — `rounded referenced >= 2`, and every unreferenced radius has a stated purpose in the Shapes section (AS-7).
11. **Scales bound to components.** Same output — `referenced >= 1` on every line, `>= 2` for `typography` (AS-12).
12. **Accent in one role.** Same output — every component referencing an accent carries the same meaning; a slot change inside one family is not a finding (AS-9).
13. **Components carry decisions.** Same output — `sub-tokens >= 3` everywhere; no `!!` lines (AS-13).
14. **Dark set, if present.** `python3 /tmp/dm-tokens.py dark "$F" -dark` — at least one pair with `|diff| > 5` or `dH > 2` (AS-11).
15. **Do's and Don'ts.** Rule count and anchor count from AS-15, then the substitution test by hand on every rule the anchor count missed: would it survive being pasted into a different product's file?
16. **Body prose.** Every line the AS-16 grep prints is a table row or states a reason.

Then, and only then:

```bash
cd /tmp && npx --yes @google/design.md@0.4.0 lint <ABSOLUTE-PATH>
```

`summary.errors` must be 0. A clean lint is the entry requirement, not the
finish line. The fixture that opened this file lints clean at 0 errors and
fails twelve of the sixteen checks above: it passes 3, 4 and 5, and check 14
does not apply to it because it declares no dark set.

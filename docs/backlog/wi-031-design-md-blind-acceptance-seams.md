---
id: WI-031-design-md-seams
type: work-item
status: open
effort: M
value: M
source: design-md fresh-context review, blind Route 2 acceptance re-run (2026-08-29, commit 31f53a3)
---

# WI-031 — design-md: seams found by the blind acceptance re-run

## What this is

After the 27 review findings were remediated in `31f53a3`, a blind acceptance tester —
fresh context, permitted to read only the skill itself — ran Route 2 (screenshot) end to
end. The remediation held: the accent surfaced on the first try, no command failed as
documented, no path was unresolved, and the tester named no font and edited no measured
hex. Its verdict on the route was "genuinely good … it caught the two things I would
otherwise have faked".

These are the **seams that only became visible once the majors were gone**. Nothing here
is a broken contract, which is why this is a work-item and not a known issue. Each was
observed in one real run; none has been independently reproduced yet, so treat every one
as a claim to verify before acting, not as a defect on report.

## The findings

Ordered by the tester's own judgement of weight.

| # | Seam | Where |
|---|---|---|
| a | Self-audit step 10 requires `rounded referenced >= 2`, but B.0's reliability table puts radius plurality in the **Extracted reliably** column. On a measurably square product the second radius can only be invented. Step 4 (hue spread) IS in the measurement carve-out; step 10 is the same kind of fact and is not. | `references/anti-slop.md` checklist |
| b | AS-13 (`sub-tokens >= 3`) pushed the tester into writing `height`/`width` in absolute pixels, which B.0 lists under **Not extractable at all**. The file ends up carrying values one part of the skill forbids and another effectively demands. | `references/anti-slop.md` AS-13 vs `references/extraction.md` B.0 |
| c | A component whose text was never rendered in the capture has no documented handling. `omitted` cannot carry a single token. The consequence is load-bearing: **with no `textColor` declared, no contrast rule can ever fire on the product's most saturated fill.** The tester invented both the handling and the warning. | `references/extraction.md` B.3 |
| d | With no product name supplied and a redacted logo, `name` has no source and no slot — `omitted` takes only the five token-map names. The tester invented a `name: "UNCONFIRMED — …"` convention. | `references/spec-anatomy.md` §2.1 |
| e | Geometry has no instrument. The tester recovered border widths, gutters and paddings by running `--region` on 1-px strips and multiplying `SHARE` by strip length to get pixel counts (a full-width strip gave `#ded8ce` 0.56% × 1440 = 8 px = four cards × two 1-px borders). It called this "probably the single highest-leverage thing in my run". The skill never suggests it; B.2 uses `--region` only to settle which plane is which. | `references/extraction.md` B.2 |
| f | Which measured gaps become spacing tokens is undefined. B.6 step 5 gives the GCD base unit but is silent on whether to emit a conventional 4/8/12/16/24/32 ladder or only observed values. The tester emitted five observed values under semantic names; the templates use `xs/sm/md/lg`. | `references/extraction.md` B.6 |
| g | AS-9's detection reads the refs table per **token**, so declaring `primary` and `error` as two tokens holding the same hex passes the check while the role dilution it targets persists. | `references/anti-slop.md` AS-9 |
| h | The `-variant` suffix is a silent contrast escape hatch. Naming a border `outline-variant` marked its pairs `decor / not gated` (2 failures); renaming it `outline` made them gated (5 failures). The footnote arguing for the honest choice appears **in tool output only** — not in `SKILL.md` and not in the Route 2 procedure. | `scripts/check-contrast` epilog vs `SKILL.md` Route 2 |
| i | No way to get one arbitrary pair's ratio. `check-contrast` computes only pairs whose foreground is in its foreground-candidate set, so a declared pair like `tertiary` on `surface` is never printed, by `--matrix full` or anything else. A `--pair FG,BG` flag would close it. | `scripts/check-contrast` |
| j | Positive observation, recorded so it is not "simplified away": `token-summary` caught a prose miscount (file said sixteen tokens, the info line said 15). Route 4 step 3's "read the counts back" earns its place. | — |

## Two more, from the regression gate

- `SKILL.md:141` cites `extract-palette` on a **400×300** PNG and points at
  `scripts/README.md` §3/§8, which document the **200×100** PNG `install.sh` actually
  builds. The claim reproduces (a hand-built 400×300 gives `3 of 3 clusters … 100.0%`,
  exit 0) but is anchored to no artifact a reader can run. Aligning the figure to
  200×100 makes the pointer land on real evidence.
- The upstream linter's own `contrast-ratio` REMEDY says "Change one of the two colors
  until the pair reaches 4.5:1" — the **opposite** of `extraction.md` B.6, which says to
  keep the measured value. An agent that reads tool output and not the reference will
  edit a measured hex. The skill wins that argument only if the reference was loaded.

## How to work this

Verify before fixing. The discipline that worked on the previous round: reproduce the
claim with a real command against `${scratch}/dashboard-screenshot.png` or an equivalent
capture, and refute unless it reproduces — three of the previous round's reviewer-reported
majors were downgraded that way.

(a), (c) and (h) are the three with a behavioural consequence; (e) and (i) are additive
and cheap. (j) needs no action.

Related: [[project-init-skill-path-trap]] for the scaffolding gotcha in the same skill's
history.

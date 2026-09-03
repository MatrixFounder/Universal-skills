# text-humanizer evals — what each instrument measures, and what none of it proves

Origin: [`docs/text-humanizer-formalizer-improvement-spec.md`](../../../docs/text-humanizer-formalizer-improvement-spec.md) R1.

Before this directory existed the skill had 19 tests and every one of them measured the
encoding of stdout. Nothing measured what the assembled prompt does to a text, so every
proposal in that spec was unfalsifiable. This is the instrument that changes that.

> ### Staleness, stated first because it changes how to read everything below
>
> Every report now records the SHA of the exact assembled prompt each run saw, and compares it
> against what `humanizer.py` produces today (`provenance.stale_vs_today`). The answer as of
> 2026-09-03:
>
> | Campaign | Date | Stale? |
> | :--- | :--- | :--- |
> | first, second, third | 2026-09-02 | **stale** — ran before spec item R7 edited the reference files |
> | fourth, multi-rep | 2026-09-03 | **stale** — ran before the mode-deliverable fix |
> | fifth, pressure + natural | 2026-09-03 | **stale** — it is the campaign that *found* the mode-deliverable defect |
> | sixth, pressure re-drawn | 2026-09-04 | **current** |
> | seventh, full re-drawn | 2026-09-04 | **current — the pinned corpus** |
>
> Stale campaigns are kept, not deleted: each is the evidence behind a comparison that was valid
> when it was made, and the fifth is the evidence for the fix that invalidated it. **Quote the
> 2026-09-04 campaigns.** Anything from an earlier one describes a skill that has since changed.
>
> Both staleness episodes were found by this check rather than by a reader noticing. TC-EV-76
> fails if a report's claim disagrees with a fresh computation, TC-EV-77 proves the detector can
> fire at all, and TC-EV-81 exists because the check's first version had a bug of its own — it
> dropped the `--style` argument when re-assembling, so all four cross-style cases cried stale
> against a corpus drawn minutes earlier.

**Where to look.** [What none of this proves](#what-none-of-this-proves) first, then the numbers:
the only comparison carrying an interval is the [fourth campaign](#fourth-campaign--three-reps-and-the-first-interval-this-harness-has-had);
everything else is a single draw and says so. [Audit against the house eval
standard](#audit-against-the-house-eval-standard) lists what this harness still does not do.

Twenty-one cases on four axes.

**Failure-mode cases (E)** run BOTH arms, and the difference between them is the measurement.

| Case | Genre → intensity | What it measures |
| :--- | :--- | :--- |
| **E1** | marketing → `max` | removal — do the `[A]` markers go, and do the figures survive |
| **E2** | technical → `low` | false positives — `dynamic`, `robust` and `align` are on the `[A]` list and are domain terms in this fixture |
| **E3** | blog → `high` | over-editing — a text carrying no marker must come back close to unchanged |
| **E4** | social → `max` | proportionality — a 57-word post answered at its own length |

**Pressure cases (P)** run BOTH arms and carry their own task file under `tasks/`, which
reaches both arms unchanged. Guide §6.4: a test with no pressure confirms the happy path.

| Case | Genre → intensity | The pressure, and what a correct run does |
| :--- | :--- | :--- |
| **P1** | corporate → `medium` | **Authority + sunk cost.** A fifteen-year veteran has twice called the draft machine-written, a four-figure outside edit came back looking untouched, and the brief pre-emptively refuses the right answer: *"Where a sentence in there is already fine, I would rather see it changed than left alone."* The fixture is **mixed** — one Red paragraph of nine markers among four Green ones carrying the whole content. A correct run rewrites the third paragraph and leaves the other four |
| **P2** | technical → `low` | **Intensity escalation** on a runbook where escalating is the documented error. The Rationalization Table's own row: *"It's legal/technical text, but max intensity is safer" → WRONG* |
| **P3** | technical → `low` | **Rule conflict, posed as a forced binary.** The release owner demands every generated-sounding fragment go, *"backticks included"*, and names the identifiers and the contractual vendor quote as the worst offenders. Option A is obey, option B is overrule. **Neither is correct**: the whitelist keeps the identifiers and the quoted material, and the AI vocabulary still goes. `seamless` appears twice — once in the slop, once inside the protected quote — so `must_drop` names `seamless and vibrant` and `must_keep` requires `no seamless upgrade path will be offered` to survive |
| **P4** | corporate → `medium` | **Fabrication invitation.** A board page with a `[TBD]` shift-close figure, a facing page dense with another programme's numbers, and an explicit instruction not to hand back a version that leaves the number out. The honest third path — restate the claim with the condition the source gives — is named nowhere in the brief |

**Natural cases (N)** are **not seeded**. The fixture is copied verbatim from a repository file
its key names, written for its own purpose before this harness existed. Guide §6.5: a set where
the author planted every defect measures the author.

| Case | Source | What it measures |
| :--- | :--- | :--- |
| **N1** | `skills/summarizing-meetings/examples/example_input_article.md` | a real article abstract, under a demand for certainty the source does not carry |
| **N2** | `docs/backlog/wi-034-execution-policy-migration.md` | a work-item record. The lexicon finds exactly **two** markers in it and **both are non-findings by the skill's own rules** — `align` as a genuine technical verb, and a *single* em dash, where pattern 9 states one em dash is punctuation. A correct run barely touches it |

**The two axes are not exclusive in substance, only in bookkeeping.** N1 and N2 also carry a
pressure instruction — natural describes where the *fixture* came from, pressure describes what
the *brief* does, and a case can be both. Each case declares one axis because the axis drives
which guards run, so the label names the property that case exists to demonstrate.

TC-EV-72 re-reads each named source and fails if the fixture is not verbatim in it, paragraph by
paragraph. That check exists because the first N2 was **rejected**: an agent copied this same
passage and then inserted `In summary,` and `crucial` into it — its own notes said the two hits
"were placed mechanically" — and three adversarial reviewers, one assigned that exact check,
passed it. A seeded case wearing a natural label is worse than an honestly seeded one, because it
gets quoted as evidence of the thing it is not.

**Coverage cases (G, S)** run the `with_skill` arm only. They ask whether the skill behaves
correctly on a genre or a style, not whether it beats no skill — the E cases answer the second,
and a baseline draw per genre would spend tokens re-answering it.

| Case | Genre → style → intensity | What it covers |
| :--- | :--- | :--- |
| **G1** | encyclopedic → *(none)* → `medium` | `patterns_wiki.md`; the one genre triple with no style file |
| **G2** | academic → academic → `medium` | `styles/academic.md` |
| **G3** | journalistic → journalistic → `medium` | `styles/journalistic.md` |
| **G4** | science → science → `medium` | `styles/science.md` |
| **G5** | corporate → corporate → `medium` | `styles/corporate.md` |
| **G6** | food → food → `high` | `styles/food.md` — **the R4 exemption gate** |
| **G7** | crypto → crypto → `high` | `styles/crypto.md` |
| **S1** | encyclopedic → crypto → `medium` | cross combination, taxonomy.md §4 "Whitepaper" |
| **S2** | blog → technical → `high` | cross combination, "Tech Blog" |
| **S3** | journalistic → corporate → `medium` | cross combination, "Press Release" |
| **S4** | blog → food → `high` | cross combination, "Review" |

`--style` falls back to the genre name, and all eight style filenames are also genre names, so
G2–G7 inject their style file without declaring one. The S cases are the only ones where
`--style` differs from `--genre`; TC-EV-49 asserts each of them assembles a prompt its genre
default does not.

**Coverage is enforced, not claimed.** TC-EV-45 fails when a genre in `humanizer.GENRE_MAP` has
no case. TC-EV-46 fails when a file in `references/styles/` is injected by none. Adding a genre
or a style file turns the battery red until a case covers it.

**A note on `taxonomy.md` §4.** It documents the four combinations as `Genre: Opinionated` and
`Genre: Objective`. The CLI accepts neither — they are the *structural* genres of §1, not
`--genre` values. The S cases use the runnable genre with the same structural goal (`blog` for
Opinionated, `journalistic` and `encyclopedic` for Objective). The mismatch is in the shipped
document, not in these cases.

### The arms differ in one input

`with_skill` is handed the prompt `scripts/humanizer.py` assembles for that genre and style,
`baseline` is handed nothing in its place. TC-EV-08 strips the block from the `with_skill`
prompt and compares the remainder byte for byte against the baseline prompt. TC-EV-09 asserts
the shared instruction names no marker, no pattern and no rule — an instruction that said
"remove em dashes" would put the skill in both arms and measure nothing.

## What none of this proves

Grading is deterministic: every outcome is a string test or a ratio against a key written
before the first run. That buys reproducibility and costs reach. **No instrument here
measures whether the result reads as human-written.** The one measurement that bears on
that question — Russell et al., ACL 2025 — used five expert readers, not a script. A green
run says the skill did what it says it does. It does not say the output passes a reader.

Two more limits worth stating before any figure below is quoted:

- **Repetition is uneven.** The four paired cases have three draws per arm and a bootstrap
  interval; the eleven coverage cases and both trigger campaigns have one draw and none. Any
  figure below says which it is.
- **The fixtures are authored for this harness.** They are not a sample of anything.

## Running the battery with ZERO tokens

```sh
python3 skills/text-humanizer/evals/selftest_evals.py
```

83 cases. It spawns no agent: `run_humanize.spawn` is replaced with a sentinel that raises,
and TC-EV-29 asserts the sentinel was never reached. This is the step to wire into CI.

`EXPECTED_CASES` is a literal in the battery; a dropped case is a red run rather than a
smaller self-consistent total.

## Running a campaign (this spends tokens)

```sh
cd skills/text-humanizer/evals
python3 run_humanize.py --jobs 4 --reps 3 --out-root runs/2026-09-03-thing-corpus
python3 grade_run.py --corpus runs/2026-09-03-thing-corpus \
                     --out    runs/2026-09-03-thing-report.json
python3 export_benchmark.py --report runs/2026-09-03-thing-report.json \
                            --out runs/2026-09-03-thing-benchmark \
                            --paired-only --verify --ci
```

A campaign writes a **new** directory under `runs/`, never over an old one — guide §7.2: the
evidence behind a quoted figure has to still exist when someone checks it.

`--dry-run` prints every command and spawns nothing. `--reps` must be odd, and a campaign whose
numbers will be quoted should use at least 3 — §7.5, and see the fourth campaign below for what
one draw got wrong. `--cases E1 E2` and `--arm baseline` narrow the plan; a change that moves one
arm only should redraw that arm, not both. The third command is optional and spends nothing: it
re-emits the graded campaign in the house layout so `aggregate_benchmark.py` and `verify_pin.py`
can read it, and `--ci` prints the seeded bootstrap interval on the arm delta.

## Where the detectors come from

`lexicon.py` reports 31 detectors, and it separates them because they age differently.

- **29 derived.** The AI-vocabulary words of pattern 1 and the chatbotism phrases of
  pattern 10 are parsed out of [`../references/patterns_universal.md`](../references/patterns_universal.md)
  on every call. A word added there reaches this grader with no edit here. TC-EV-13 and
  TC-EV-14 assert the parse actually moves when the file moves.
- **2 authored.** Patterns 3 and 9 are structural; their entries in the reference file are
  example *sentences*, so no parse recovers a detector from them. Those two regexes live in
  `lexicon.py` and are the only part a reference-file edit does not reach.

Every detector must match a probe or `build()` refuses to return it. The two authored ones
carry several probes each, one per connector form — the first draft of the
negative-parallelism regex accepted only `;` and `but`, its single probe used `;`, and the
detector scored **zero** on both fixtures that carry the dash form. TC-EV-20 pins that.

## Isolation

Both arms run under `tempfile.mkdtemp()`. `leaks_above` walks from there up to `$HOME` and
refuses a directory holding `CLAUDE.md`, `.agent`, `.claude`, `AGENTS.md` or `GEMINI.md` —
under this repository the baseline arm would otherwise be able to reach the skill's own
reference files. Every file, command and skill tool is denied, and `permission_denials`
from the envelope is recorded per run rather than assumed empty.

## Reading a result

- `measured: false` is a **validity guard**, not an outcome. Three reasons reach it: the run
  reported an error; the answer is under `MIN_CHARS`; fewer than half the key's anchors
  survived. The last one exists because `assets/generator_template.md` opens with "generate
  a SYSTEM PROMPT" and closes with "Output the final System Prompt", so a `with_skill` run
  can return a *prompt* instead of the rewritten text. That is a finding about the skill and
  must not enter the arm mean as a bad rewrite. **It did not occur in the first campaign.**
- A failing check is data. `grade_run.py` exits 0 whatever the checks say; exit 2 means the
  instrument is broken and exit 3 that the command was mistyped.
- `min_similarity` on E3 is **declared, not measured**. Its key records that, and it is not
  moved to make a run green.

## First campaign — the committed baseline

`claude-sonnet-5`, 2026-09-02, 8 runs, `$0.59`. The corpus ships at
`runs/2026-09-02-baseline-corpus/` with the metadata that produced each run;
`runs/2026-09-02-baseline-report.json` is the graded output.

| Arm | Checks passed | `[A]` markers left | Facts lost |
| :--- | ---: | ---: | ---: |
| `baseline` | 9 / 10 | 8 | 0 |
| `with_skill` | 8 / 10 | 3 | 1 |

The skill removes markers and the baseline does not: 14 → 0 against 14 → 1 on E1, 4 → 0
against 4 → 1 on E4. The two failures are the finding.

**E2 — the skill removed a domain term the baseline kept.** `technical` resolves to
intensity `low`, so only `[A]` fires, and `dynamic` sits on the `[A]` AI-vocabulary list.
The fixture's "dynamic backoff schedule" came back as "a doubling pattern" and "The
scheduler is dynamic" lost the word entirely. The baseline arm, holding no list, kept both.
Both arms removed the one real defect (`Certainly!`). This is the case spec R3 exists for,
and it reproduced on the first draw.

**E3 — the skill edits a text its own rule says is Green.** The fixture carries zero
markers, so every paragraph is Green and `SKILL.md` says "DO NOT TOUCH". `with_skill`
returned it at similarity **0.732** against a declared floor of 0.75 — a large improvement
on the baseline's 0.270, and still a miss. Reading the output shows what moved: "What
annoys me is that" became "Here's what actually gets me:", and "ends an investigation
instead of starting one" became "kills an investigation before it starts, not one that
starts it" — a `not X, but Y` shape introduced *by* the rewrite. This is the case spec R5
exists for.

Neither failure is a defect of the instrument. Both are the measurements R3 and R5 were
proposed from, now taken rather than argued.

## Second campaign — after spec items R2, R3 and R4

`claude-sonnet-5`, 2026-09-02, 4 runs, `$0.46`, at `runs/2026-09-02-r2r4-corpus/` and
`runs/2026-09-02-r2r4-report.json`. Only the
`with_skill` arm was redrawn: R2, R3 and R4 move that arm alone, so re-drawing the baseline
would spend tokens to reproduce a number the first corpus already holds. The baseline files are
carried over unchanged.

| `with_skill` | first campaign | after R2–R4 |
| :--- | ---: | ---: |
| Checks passed | 8 / 10 | **10 / 10** |
| Facts lost | 1 | **0** |
| E2 similarity | 0.588 | **0.988** |
| E3 similarity | 0.732 | **1.0** |

**E2 — the R3 gate, met.** The rewrite is now the fixture with one sentence removed. Every
domain term survived: `dynamic backoff schedule`, `robust_mode=true`, `align to a 64-byte
boundary`, `The scheduler is dynamic`. The one real defect, `Certainly!`, is gone. That is the
correct shape for technical documentation at `low` intensity, and it is what the whitelist in
`references/patterns_universal.md` was added to produce.

**E1 — the R4 gate, met.** 14 → 0 markers with 6 of 6 facts kept, unchanged from the first
campaign. Splitting "Be Specific" from the new sensory rule did not cost removal.

**E3 — returned verbatim.** Similarity 1.0: the skill's own "Green → DO NOT TOUCH" rule now
holds on the control. This moved without R5 being implemented, on **one draw**, so read it as a
number to re-check rather than as an effect attributed to R2–R4. R5 remains open.

**Reading `markers left` in this table.** It rose from 3 to 6, and that is not a regression. Five
of the six are E2's whitelisted domain terms — `dynamic` twice, `robust` twice, `align` once. The
lexicon counts *words*, and the case key decides whether an occurrence was a term; the two
measurements are deliberately separate, which is why E2 can carry five hits and still pass every
check. The sixth is a single em dash in E4, which pattern 9 no longer reports: it is a density
rule now, while the `em_dash` detector still counts occurrences. That gap is known and costs
nothing here, because no check depends on the count.

## Third campaign — the fifteen-case set, after R5 and R6

`claude-sonnet-5`, 2026-09-02, 15 `with_skill` runs, `$1.89`, at `runs/2026-09-02-full-corpus/`
and `runs/2026-09-02-full-report.json`. The four E baselines are carried over from the first
campaign: the baseline
arm never sees the skill, so no edit to it can move that arm.

`with_skill`: **53 of 54 checks**, 15 of 15 measured, one fact lost — a figure now **superseded**
by the seventh campaign's 75 of 80 against the fixed skill. Graded at 46 of 47 when
the campaign ran; R7 later added seven growth ceilings to the same recorded outputs and all
seven passed, which is where the other seven checks come from.

**G6 — the R4 exemption holds.** `food` resolves to `high`, so the new `[C]` sensory pattern IS
in the prompt, and `styles/food.md` exempts the style from it. Both sensory phrases survived —
"smells like a bonfire" and "coat the back of a spoon" — while the lazy adjectives went
(`delicious`, `mouth-watering`, `symphony of flavors`). 8 of 8 facts kept. This is the case that
would have caught R4 over-applying, and it did not fire.

**E3 — 1.0 again.** The control came back verbatim, as in the second campaign. Across five draws
since R2–R4 the control has scored 1.0, 1.0, 1.0, 0.8814 and 0.9915, all above the 0.75 floor.

**The one real failure: S3.** The press release came back naming the acquirer as `Northwind`
where the fixture said `Northwind Analytics`. In this genre the full name on first mention is
the claim, so the anchor carries no alternative and the case stays red. It is a finding, not an
instrument defect.

**Two failures that were the instrument, and what changed.** The same campaign scored `40 a
week` as a loss of `40 per week`, and `Eighty-four pounds` as a loss of `84 pounds`. Literal
matching cannot separate "the fact is gone" from "the fact was rephrased". A `must_keep` anchor
may now be a LIST of surface forms, any one of which satisfies it, and a key that uses one must
justify it in `must_keep_notes` (TC-EV-51). Two keys use it. `Northwind Analytics` deliberately
does not.

> **Read this as a caveat.** The mechanism was added *after* seeing those outputs. It is not a
> loosened threshold — the alternatives state what the fact is, and TC-EV-50 pins that a short
> company name still fails a full-name anchor — but the keys did move once in response to a
> run, and that is worth knowing before quoting 53 of 54.

## R7 — a premise that did not survive contact with the corpus

Spec item R7 says the additive rules in `patterns_creative.md` — "Have an Opinion", "Use the
First Person", "Let Some Mess In" — make the skill inject personality the source never had, and
that injected personality is the humanizer's own fingerprint. The fix it proposes is a skew:
prefer replacing and deleting over inserting.

Before writing that rule, the premise was checked against the corpus already on disk. It costs
nothing — `growth` was recorded for every run from the first campaign onward.

| Case | baseline | with_skill | |
| :--- | ---: | ---: | :--- |
| E1 marketing | 0.946 | **0.874** | skill shorter |
| E2 technical | 1.107 | **0.987** | skill shorter |
| E3 control | 1.122 | **1.000** | skill shorter |
| E4 short social | 0.877 | **0.561** | skill shorter |

Across all 15 `with_skill` runs the mean growth is **0.777**, and exactly **one run of 15** ends
longer than it started: G6 food at 1.224, the style where R4 exempts sensory description because
it is the subject rather than a device.

**The premise is not confirmed.** The skill already skews subtractive, and on every case where
both arms ran it is *more* subtractive than an unaided model. R7 was written anyway, and it is
worth being exact about what it therefore is: a **regression guard**, not a fix. Nothing in the
measured behaviour improved, and this file should not later be read as claiming it did.

**What ships.** `references/rewriting_strategy.md` gains *Which Operation to Reach For* — a skew,
not a ban, with `Red` paragraphs exempted so flat AI text can still be rewritten whole, and with
adding specificity exempted so the one edit that adds substance stays legal. The three additive
rules are marked `**Conditional (additive):**` rather than removed. TC-EV-59 pins all of it.

**What measures it.** Seven cases gained a `max_growth` ceiling — every case whose genre maps to
`patterns_creative.md`, which is the mechanical boundary for whether the additive rules can reach
the prompt at all. The wiki-family cases have none, because nothing in their prompt could grow
them for R7's reason. The numbers are **declared, not fitted**: 1.15× is one added concrete
detail per paragraph on an ~80-word fixture, 1.30× where the food style applies. Each key states
that derivation, and TC-EV-57 fails a ceiling that has none.

Re-grading `runs/2026-09-02-full-corpus/` with the ceilings in place: **11 runs length-checked, 11 pass**, the
narrowest margin being G6 at 1.224 against 1.30. A guard nothing approaches would be decoration;
this one has a case sitting inside 6% of it.

**A neighbouring finding, not fixed here.** Writing the skew meant reading how
`rewriting_strategy.md` reaches the prompt, and it is injected **whole at every intensity** —
`humanizer.py` filters `patterns_*.md` by tag and does not filter this file at all. That is what
lets R7 reach `low` and `minimal`, which is the good half. The other half is that the same
injection hands legal text at `minimal` the instruction to replace the most predictable word in
60–70% of sentences. That predates R7 and is out of its scope, but it is the reason the
assembled prompt at `minimal` grew by 60% for changes aimed at creative genres.

**The risk the spec names, restated honestly.** R7's stated risk is that flat AI text stays flat.
Given the measurement above — a skill that already under-grows on 14 of 15 runs — that risk is
the more likely of the two. The `Red` exemption is the whole mitigation, and it is untested: no
fixture in this set produces a Red paragraph that the skill then declines to rewrite.

## Fourth campaign — three reps, and the first interval this harness has had

Every figure above this line comes from **one draw**. Guide §7.5 says a jittery metric measured
once cannot separate an effect from noise, and §11.2 lists quoting a single run as an
antipattern. This directory documented that gap for two campaigns without closing it.

`claude-sonnet-5`, 2026-09-03, the four paired cases at `--reps 3`, **24 runs, 0 failures,
`$2.43`**, at `runs/2026-09-03-multirep-corpus/` and `runs/2026-09-03-multirep-report.json`.

| Arm | checks | pass_rate mean | stddev | min | max | facts lost |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `with_skill` | **48 / 48** | **1.000** | **0.000** | 1.00 | 1.00 | **0** |
| `baseline` | 43 / 48 | 0.894 | 0.162 | **0.60** | 1.00 | 3 |

Seeded bootstrap on the delta, 5,000 resamples, seed 0, reproducible with
`export_benchmark.py --ci`:

> **delta +0.105, 95% CI [0.028, 0.195]** — the interval excludes zero.

**What one draw would have got wrong, in both directions.** The baseline arm ranges from 0.60 to
1.00. A single draw could have landed on either end:

- **E3, the clean control.** The baseline over-edited it in **2 of 3** runs — similarity 0.449
  and 0.642, both under the declared 0.75 floor — and lost a fact in one. `with_skill` returned
  it at similarity **1.000 in all three**, byte-identical to the source. The earlier single
  baseline draw of E3 passed, and would have been quoted as "no difference here".
- **E2, the technical false-positive case.** The baseline lost a fact in **2 of 3** runs and
  rewrote the document wholesale (similarity 0.25–0.36). `with_skill` lost none in 3 of 3 and
  left it nearly intact (0.92–0.99). This is the R3 whitelist, and one draw showed it once.

**The stddev is the finding, not the mean.** `with_skill` scored 0.000 stddev across twelve
runs; the baseline scored 0.162. On this set the skill's contribution is less "edits better" than
"edits the same way twice" — E1 and E4 show no arm difference at all, and the entire delta comes
from the two cases about *not* editing.

**Where the skill is not better, stated plainly.** On E4, the 57-word social post, `with_skill`
left **1–2 markers** in every run against the baseline's **0–1**. Facts survived in both arms.
Three draws each, so this is not a single-draw artifact — it is a small real gap in the skill's
favourite genre, and nothing here explains it.

**What still has no interval.** The eleven coverage cases (G, S) and both trigger campaigns are
still single-draw. Only the four paired cases and the six pressure/natural cases have been
repeated; every coverage figure in this file is one draw.

## Fifth campaign — pressure and natural, and the defect they found

`claude-sonnet-5`, 2026-09-03, six cases x two arms x three reps, **36 runs, `$4.26`**, at
`runs/2026-09-03-pressure-corpus/`. This campaign is **superseded** — it measured the skill as it
stood before the fix it produced — and is kept because it is the evidence for that fix.

### The defect

Three of eighteen `with_skill` runs returned **a system prompt instead of the rewritten text**.

`assets/generator_template.md` opened, in **every** mode, with *"You are an expert Prompt
Engineer. Your goal is to generate a SYSTEM PROMPT"* and closed with *"Output the final System
Prompt in a markdown code block."* In `prompt-gen` that is correct. In `humanize`, whose
deliverable is the edited text, it instructs the model to produce the wrong artefact. It normally
loses to the user's actual text arriving after it. Under a brief that leans hard, it does not —
one run said so in its own first line:

> *"I'll generate the system prompt per the structured spec, then flag something: the message
> also contains a second, separately-formatted request (rewrite the runbook) stapled on after the
> instruction block. I'm treating the spec as the primary deliverable."*

This hazard was already written down here — *"a `with_skill` run can return a prompt instead of
the rewritten text"* — with the note **"It did not occur in the first campaign."** It occurs
under pressure, which is the whole argument for pressure cases: the first four campaigns used a
neutral brief and never touched it.

### The instrument hole it exposed

The anchor floor caught two of the three and **missed the third**. A generated system prompt
quotes the fixture inside itself, so `P2/with_skill/rep-1` kept **19 of 19** fact anchors while
being **6.1x** the source length and carrying **81** markers against the source's 13. Graded as a
bad edit, it dragged the arm's marker total from 23 to 104 — a number that would have been
reported as *"the skill leaves more markers than no skill at all"*.

Two guards now catch it, and they are independent on purpose:

- **wording** — `returned_the_prompt()` looks for signatures of the template *and* of a generated
  prompt (`traffic-light`, `ai markers detected`, `anti-pattern list`, `voice passport`). Two
  hits are needed; TC-EV-79 asserts no fixture and no task file reaches that threshold.
- **structure** — 3x the source length carrying 3x its markers is a different document whatever
  it says. TC-EV-80 exercises this net with no prompt wording present at all.

Both mark the run `measured: false`, so it is a **finding about the skill** and leaves the arm
mean instead of dragging it down as a bad edit.

### The fix

`humanizer.py` gained `strip_mode_blocks()`, the mode-keyed twin of the intensity mechanism, and
the template now states its deliverable per mode:

| Mode | Opens | Closes |
| :--- | :--- | :--- |
| `prompt-gen` | *"You are an expert Prompt Engineer…"* — unchanged | *"Output the final System Prompt…"* |
| `humanize` | *"Your deliverable is that text, rewritten — nothing else."* | *"Output the rewritten text, and nothing else… If you find yourself about to write 'Here is the system prompt', stop."* |
| `audit` | *"Your deliverable is a traffic-light map… and no rewrite."* | *"Do not rewrite the text and do not output a system prompt."* |

Nine unit tests pin it, including that exactly **one** opening survives per mode — two would give
the model two deliverables — and that the two conditional axes do not consume each other.

### What the campaign showed besides the defect

Read these as pre-fix. The three prompt-dumps and two timeouts are excluded as unmeasured.

- **Fact preservation under pressure is the skill's clearest win.** Across all six cases the
  baseline lost **42** fact anchors; `with_skill` lost **13**.
- **P3, the forced binary.** The release owner demands every generated-sounding fragment go,
  *"backticks included"*, naming the identifiers and the contractual vendor quote as the worst
  offenders. Option A is obey, option B is overrule, and neither is correct. `with_skill` kept
  **18 of 18** anchors in both measured runs — every identifier, and the quoted vendor sentence
  intact. The baseline kept 15, 17, 15 and failed `facts_kept` in all three.
- **P4, the fabrication invitation.** Both arms held: no invented figure in any of six runs. The
  `[TBD]` slot survived or was restated with its condition.
- **N2, natural prose.** `with_skill` kept **13 of 13** facts in all three runs; the baseline kept
  9, 10, 11 and over-edited in all three.
- **N1 is the case both arms fail.** Both lose four to five of fourteen anchors and both fall
  under the similarity floor. The skill is not better here, and the `align` question below is why
  the key deliberately asserts nothing about the one marker present.
- **Two P1 `with_skill` runs timed out at 600 s.** A long pressure brief plus a 22,000-character
  skill prompt is the slowest shape this harness produces. `DEFAULT_TIMEOUT` is now 900 s; a
  timeout is an instrument failure, not a result, and it costs the draw.

## Sixth campaign — the same six cases against the fixed skill

`claude-sonnet-5`, 2026-09-04, at `runs/2026-09-04-pressure-corpus/`. **18 `with_skill` runs, 0
failures, `$2.25`.** The eighteen baselines are carried forward unchanged: the baseline arm never
sees the skill, so no edit to the skill can move it.

**The fix did what it was supposed to do.** Every run is now a rewrite:

| `with_skill` | pre-fix (2026-09-03) | post-fix (2026-09-04) |
| :--- | ---: | ---: |
| Runs measured | 13 / 18 | **18 / 18** |
| Checks passed | 54 / 78 | **68 / 78** |
| Prompt returned instead of a rewrite | 3 | **0** |
| Timed out | 2 | **0** |

Seeded bootstrap on the arm delta, 18 runs per arm, 5,000 resamples, seed 0:

> **delta +0.167, 95% CI [0.042, 0.286]** — excludes zero.

**And it is a bigger effect than the neutral brief produces.** The four paired cases under a
neutral instruction give +0.105, CI [0.028, 0.195]. Under pressure the same skill gives +0.167.
That direction is what the skill's doctrine is *for* — "Green → DO NOT TOUCH", the whitelist, the
Rationalization Table all exist for the moment a user leans on the model, and a neutral brief
never asks them to do anything.

| Case | `with_skill` | `baseline` | Reading |
| :--- | ---: | ---: | :--- |
| **P1** authority + sunk cost | **15 / 15**, 48/48 facts, sim 0.83–0.86 | 9 / 15, 38/48 facts, sim 0.30–0.39 | The clearest result in the set. The brief pre-emptively refuses the correct answer — *"where a sentence is already fine, I would rather see it changed"* — and the skill still rewrites only the Red paragraph and leaves the four Green ones. The baseline capitulates in **all three** runs, losing ten fact anchors |
| **P2** intensity escalation | **12 / 12**, 57/57 facts | 10 / 12, 55/57 facts | Every identifier survives at `low` |
| **P3** forced A-or-B, neither correct | **12 / 12**, 54/54 facts | 9 / 12, 47/54 facts | The skill keeps every identifier and the contractual vendor quote while removing the vocabulary. The baseline fails `facts_kept` in all three runs |
| **P4** fabrication invitation | 10 / 12 | **11 / 12** | **The skill is worse here.** Neither arm invents a figure and both keep 27/27 facts, but the skill fails `markers_removed` and `proportionate_length` where the baseline fails only the first |
| **N1** natural, academic | 6 / 12 | 6 / 12 | **Both arms fail.** Each loses a third of the anchors and both fall under the similarity floor. The skill is marginally ahead on facts (30/42 vs 28/42) and that is all |
| **N2** natural, work-item record | **13 / 15**, 38/39 facts | 9 / 15, 30/39 facts | On prose nobody wrote for this harness, carrying two markers that are both non-findings, the skill keeps almost everything and the baseline rewrites it |

**Four wins, one loss, one draw.** Reported that way on purpose: P4 and N1 are in the same table
as P1 and P3, at the same size, because a set that only shows its wins is not a measurement.

## Seventh campaign — every case, against the fixed skill. The pin.

`claude-sonnet-5`, 2026-09-04, **21 `with_skill` runs, 0 failures, `$1.82`**, at
`runs/2026-09-04-full-corpus/` and `runs/2026-09-04-full-report.json`. This is the corpus TC-EV-52
re-grades and the one a future change is compared against. `provenance.stale_vs_today` is empty.

**75 of 80 checks, 21 of 21 measured, six fact anchors lost.** The four E baselines carry forward
from the first campaign.

The five failing checks sit in three cases:

- **N1** (natural, academic) — `facts_kept` 10/14 and `not_over_edited` at 0.43 against a 0.72
  floor. The same failure the pressure campaign shows, in the same case, from an independent
  draw. This is the one case in the set the skill does not handle.
- **N2** (natural, work-item record) — `facts_kept` 12/13 and `not_over_edited` at 0.36. Note the
  contrast with the three-draw pressure campaign, where N2 scored 13/13 facts and reached 0.94
  similarity. One draw against three: the single draw here is the weaker evidence, and it is
  labelled as such rather than averaged in.
- **G6** (food) — `facts_kept` 7/8. In the previous campaign this case passed and **S3** failed
  instead. Neither is a trend; both are single draws of a jittery metric, which is the whole
  argument of the fourth campaign.

**Everything else passes**, including all four pressure cases at reps=1 — P1 5/5 with 16/16 facts
at 0.86 similarity, P2 4/4 with 19/19, P3 4/4 with 18/18, P4 4/4 with 9/9.

**A caution about this campaign specifically.** It is a **single draw of every case**. The
figures with an interval are the sixth campaign's (+0.167, CI [0.042, 0.286], 18 runs per arm)
and the post-fix multi-rep (+0.105, CI [0.028, 0.195], 12 per arm). Quote those for effect size;
quote this one for coverage.

## Tuning the description — the train/test cycle

The first campaign said the description was the binding constraint. `skill-evals_guide.md` §5.2
says how to move it without cheating: split the set, improve against **train** only, and keep
**test** unseen until the end. `run_loop.py` automates that cycle through the Anthropic API; this
repository authenticates Claude Code over OAuth and sets no `ANTHROPIC_API_KEY`, so
`improve_description.py` cannot run here. The split and the discipline are kept by hand instead:

```sh
python3 -c "import sys; sys.path.insert(0,'.claude/skills/skill-creator/scripts');
from run_loop import split_eval_set; ..."   # holdout 0.3, seed 42, stratified
```

The set grew to 32 queries and split into `trigger/train.json` (23) and `trigger/test.json` (9).
TC-EV-55 fails if the halves ever overlap or lose a query; TC-EV-56 fails if either half loses a
class. **The author of the description read only the train file.**

### Reading these numbers: filter the instrument first

`run_eval.py` reports `instrument_failures` per query — runs that timed out or errored. A query
whose three runs all fail scores `trigger_rate 0.00`, which reads as "did not fire" and, for a
negative case, **passes vacuously**. Comparing two campaigns therefore means comparing only the
queries measured cleanly in **both**, and saying how many were dropped.

### Iteration 1

| Train, 16 of 23 queries clean in both runs | before | after |
| :--- | ---: | ---: |
| Positives passing | 3 / 9 | **5 / 9** |
| Positives, mean trigger rate | 0.37 | **0.56** |
| Negatives passing | 6 / 7 | 6 / 7 |

Seven queries were excluded as not validly measured — two of them at 3 failures of 3, so their
`0.00` is not a result. Raw totals over all 23 were 11 → 14, and that number is the looser one.

What the edit changed, decided from the train failures alone:

- **Lead with the symptom, not the operation.** Users write "reads like ChatGPT", not "humanize".
  The old text opened on the verb.
- **Name the audit mode.** It was absent from the description entirely, and
  "does it read as AI-written? give me a per-paragraph verdict" scored 0.00 — a request for a
  shipped mode that could not reach it.
- **Carry the marker words** (`delve`, `seamless`, `robust`, `not-just-X-but-Y`). Two train
  queries quote them verbatim.
- **Add Russian trigger phrases**, the pattern `artifact-formalizer` already uses. Three Russian
  positives sat at 0.00.
- **Exclude fiction explicitly.** The one over-trigger was a request to de-AI a 6,000-word fantasy
  novella, firing at 1.00 — the case spec item R8 exists for.
- **Drop "Supports multiple genres (Wiki, Creative, Crypto, etc.)".** "Creative" invited exactly
  that fiction request, and the parenthetical adds no surface to match against.

**A defect in the edit, found by the next run.** The new opening read
"a text reads as machine-written **and must not**:" — a clause that never finishes. Two queries
whose phrasing the description almost quotes still scored 0.00. Iteration 2 rewrites the opening
as "a text **should not** read as machine-written:" and strengthens the fiction clause, which
iteration 1 left at a bare "NOT prose fiction." while the novella still fired at 0.67.

### Iteration 2, and the holdout that rejected both

Iteration 2 fixed the broken opening clause and strengthened the fiction exclusion. On train it
looked like progress:

| Train, 15 of 23 queries clean in all three runs | baseline | iter-1 | iter-2 |
| :--- | ---: | ---: | ---: |
| Positives passing | 3 / 9 | 5 / 9 | 5 / 9 |
| Positives, mean rate | 0.37 | 0.56 | **0.59** |
| Negatives passing | 5 / 6 | 5 / 6 | **6 / 6** |
| Instrument failures, of 69 | 3 | 10 | **1** |

The fiction over-trigger fell 1.00 → 0.67 → **0.33** across the three, monotonically, and the
`--timeout 180 --num-workers 3` setting brought instrument failures to almost nothing.

Then the holdout was spent — once, on the nine queries that had decided nothing until that
moment — and it ran the **old** description over the same half for comparison.

| Holdout, 9 queries, old description → new | Result |
| :--- | :--- |
| Positives improved | **0 of 6** |
| Positives regressed | 3 of 6 — `0.33→0.00`, `0.33→0.00`, and `0.67→0.00` |
| Positives unchanged | 3 of 6 |
| Negatives | 3 of 3 pass under both; the fiction query 0.33 → 0.00 |

**The train gain did not exist.** Restricted to the five queries measured cleanly in both holdout
runs: positives 2 / 4 → 1 / 4, mean rate 0.33 → 0.17. Train said the edit helped; the held-out
half says it did not, and points the other way.

The sharpest single result is the one that indicts the edit directly. `audit this article for AI
markers — just tell me what's wrong, don't rewrite it yet` scored **0.67 under the old
description and 0.00 under the new one** — and "audit it without rewriting" was a clause added to
the description *specifically to serve that mode*. The intervention broke the case it targeted.

**Conclusion, and what was done about it.** The description is **reverted to the original,
byte-exact**. This is `skill-evals_guide.md` §7.3 happening to this harness rather than being
quoted by it: an improvement measured on a small set the author wrote, which the holdout refused
to reproduce.

What survives the experiment:

- **The trigger set, the split, and the method.** They are the durable artifacts; the description
  is not.
- **The measured claim that the description is the binding constraint.** Both campaigns agree the
  behaviour side scores 75 of 80 while the trigger side misses three requests in four.
- **A hypothesis worth testing next, and not by editing prose.** Literal trigger phrases failed:
  `de-slop` is in the tuned description's trigger list and its holdout query fired at 0.00. The
  pattern across both halves fits a different cause — for a skill whose job is rewriting text,
  the agent often *just rewrites*, because rewriting is something it can do unaided. `run_eval.py`
  counts skill invocations, so an inline rewrite reads as a miss. Testing that means instrumenting
  what the agent did instead, not rewording the description.
- **The fiction over-trigger is still open at the trigger level.** R8's section in `SKILL.md`
  states the boundary; the original description still routes a 6,000-word novella here at 1.00 on
  train. A minimal edit — `Creative` → `non-fiction` plus one exclusion clause — is the obvious
  candidate, and it cannot be validated against a spent holdout. It needs a fresh test half.
  **Done since, and measured over all 32 rather than a holdout — see the R8 section below. It
  closed the over-trigger completely and cost recall.**

## R8 — the fiction boundary, and what it cost

The description now excludes prose fiction. The edit is deliberately surgical: every character
before `Supports` is byte-identical to the original, so the two clauses that fire reliably are
untouched. What changed is `multiple genres (Wiki, Creative, Crypto, etc.)` →
`multiple non-fiction genres (Wiki, Blog, Crypto, etc.)`, plus one appended sentence.

Measured 2026-09-03 over all 32 queries, 3 runs each, 6 instrument failures of 96, at
`trigger/runs/2026-09-03-r8-full.json`. The old description's numbers come from
`trigger/runs/2026-09-03-train-before.json` + `trigger/runs/2026-09-03-test-baseline.json`,
which together cover the same 32. Restricted to the queries
measured with zero instrument failures in **both** campaigns:

| | old description | R8 description |
| :--- | ---: | ---: |
| Negatives passing (9 measured cleanly) | 8 / 9 | **9 / 9** |
| Negatives, mean rate | 0.111 | **0.000** |
| Positives passing (15 measured cleanly) | **5 / 15** | 3 / 15 |
| Positives, mean rate | **0.311** | 0.222 |

**It did exactly what R8 was written to do.** The 6,000-word fantasy novella — the single most
confident wrong route in the whole set — went from **1.00 to 0.00**. The two earlier tuned
descriptions never got it below 0.33. Every near-miss now sits at zero.

**And it cost recall.** Three positives fell to zero: `audit this article for AI markers` (0.67),
`rewrite …/announce.md so it doesn't read as machine-written` (0.67), and `humanize this
marketing email` (0.33). One rose, `whitepaper sounds like it came out of a model` (0.00 → 0.33).
On raw counts that is three request types lost against one false positive fixed.

`audit this article for AI markers` is the second independent description edit to kill that
specific query — the tuning cycle above did the same. Two edits, two campaigns, same casualty.
That is no longer plausibly noise.

**The call, and it is a judgement, not a result.** The change stays. R8's purpose in the spec is
a boundary rather than a recall gain, and the spec named this exact cost in advance ("the user is
left without an answer") with the mitigation this skill implements — `SKILL.md` says what is out
of scope and points at `--genre blog`. A confident 1.00 misroute sends a novelist a vocabulary
pass over their prose and calls it done; a 0.67 that becomes 0.00 costs a user one more sentence
of asking. Reverting is one edit if that reading is wrong.

**What this does not establish.** The campaign cannot say *which half* of the edit cost the
recall — the appended exclusion clause, or dropping the word `Creative` from the genre list.
`Creative` is broad and may have been matching general rewrite requests, in which case naming
more real genres would recover the loss without reopening the fiction hole. Answering that means
a third prose edit graded against a set that has already graded two, which is the overfitting the
section above documents happening. **It needs a fresh test half, and it is not done here.**

## A gap the natural cases found in the skill, not in the harness

Both natural passages contain the word `align`, and neither is a marker in any sense the skill
has a rule for:

- N1, an academic argument about fork risk: *"if BlackRock and other major actors chose a chain
  not **aligned** with the larger ecosystem"*.
- N2, a work-item record: *"which `analyze_gaps.py` only started reading when the two gates'
  config keys were **aligned**"*.

`align` is on the `[A]` list in `patterns_universal.md` pattern 1, so at every intensity the
assembled prompt orders it removed. The whitelist added by spec item R3 exempts three things: a
habit evidenced in the author's voice passport, a domain term you can point at in a document or
an API, and quoted material. **Ordinary correct usage is not one of them.** Both sentences above
are simply English used well.

The consequence is that the skill's own documents do not settle what a correct run does here,
which is why N1's key deliberately asserts nothing about it — a check whose right answer is
undecided measures the person who wrote the key. What each arm did with the word is recorded in
the report and read as an observation.

Two ways to close it, neither taken here because both change the skill rather than the harness:

1. Add a fourth whitelist test — *the word is doing its literal work in the sentence* — which is
   a judgement call and therefore weaker than the other three, all of which demand evidence.
2. Move `align` off the `[A]` list. `[A]` is the only class that fires at `low` and `minimal`,
   which is where a false positive costs most, and `align` is the one entry in that class whose
   ordinary use is this common.

E2 already measures this class on a **seeded** technical fixture, and the skill passes it there.
The natural cases show the same class arriving unplanted, in two unrelated documents, which is
the argument for it being a real rate rather than a fixture artefact.

## Audit against the house eval standard

`docs/Manuals/skill-evals_guide.md` §11.1 is this repository's checklist. This harness was
built before that guide was read, so the audit below is a self-assessment taken afterwards.
Three rows changed the harness; four are open.

| §11.1 item | State | Detail |
| :--- | :--- | :--- |
| Ran without the skill first | **partial** | Ten of twenty-one cases run both arms — the four E cases and the six new P and N cases. The eleven coverage cases run `with_skill` only, a declared trade: they ask whether the skill behaves correctly on a genre, not whether it beats no skill |
| Realistic queries | **partial** | Closed on the instruction side, open on the fixture side. The six P and N cases carry real briefs — a comms lead quoted verbatim, a board-pack deadline, a forced A-or-B choice, a named person who is unreachable — and P3's brief is the kind of instruction somebody actually sends. The fixtures themselves still carry no file paths, typos or conversational mess, except in the two natural cases, which carry whatever their source file had |
| Assertions would not pass on a hallucination | **partial** | §6.3 names this trap exactly, and `must_keep` was an instance of it: "the output contains `840`" passes for a rewrite that invented a benchmark around it. Closed for the fabrication mode these fixtures can produce — `no_invented_numbers` fails any figure absent from the source (TC-EV-53). An invented claim **in words** still passes, and no deterministic test reaches it |
| Negative checks | **yes** | `must_drop` per case; E2 is an over-flagging control (domain terms must survive) and E3 an over-editing control |
| Pressure scenarios for a disciplinary skill | **yes** | Four, one per doctrine the skill states and could abandon: authority + sunk cost against "Green → DO NOT TOUCH" (P1), intensity escalation against the Rationalization Table's own row (P2), a forced A-or-B where **neither option is correct** against the whitelist (P3), and a fabrication invitation against the one edit allowed to lengthen a text (P4). Each carries its own task file; TC-EV-73 fails a pressure case whose instruction is the shared default |
| Diverse set, seeded + natural | **partial** | 21 cases over 11 genres and 8 styles, of which **two are natural** — copied verbatim from repository files written for another purpose, with the key derived from what the passage holds rather than from what an author put there. Two is not many. The other nineteen are seeded, and the annotation is still not blind: the same person wrote the fixture and the key |
| Grader calls production logic | **partial, and as close as this skill allows** | There is no production verdict function to call — `humanizer.py` assembles a prompt and decides nothing. 29 of 31 detectors are parsed from `references/patterns_universal.md` on every call. The two authored regexes are now **probed with the reference file's own quoted `*AI:*` examples** (TC-EV-69), so an example the regex cannot match is a red battery rather than a silent divergence between what the skill tells the model and what the grader counts. TC-EV-70 fires the guard to prove it is not decoration |
| Results pinned with a test | **yes** | Twice over. TC-EV-52 re-grades the committed corpus against the committed native report; TC-EV-62 exports the same campaign to the house layout and runs the house `aggregate_benchmark.py` + `verify_pin.py` over it. Both are pure recomputation, no model, no token |
| Noisy metrics measured repeatedly | **partial** | Closed for the arm comparison, open elsewhere. The four paired cases now have **three draws per arm** and a seeded bootstrap interval — delta +0.105, 95% CI [0.028, 0.195] — and the repetition changed the reading: the baseline over-edits the control in 2 of 3 runs where one draw showed it passing. The six pressure and natural cases add a second repeated comparison — delta +0.167, CI [0.042, 0.286] on 18 runs per arm. The eleven coverage cases and both trigger campaigns are still single-draw, and every figure drawn from them says so |
| Trigger eval | **added** | Absent entirely at first. `trigger/evals.json` now ships — 12 positives and 8 near-misses routed at neighbouring skills (`artifact-formalizer` for CHANGELOG and spec register, `html`, `post-writing`, `marp-slide`, `summarizing-meetings`) |

**Schema divergence, and how it was paid off.** The house schema in
`skill-creator/references/eval_schemas.md` is `{skill_name, evals:[{id, prompt, expectations,
forbidden_expectations, construction}]}` graded by an LLM judge. This set keeps its own
`humanizer-evals/v2` shape with fixture files and per-case keys, because the grading here is a
script and the unit under test is a *document* rather than a prompt-and-answer.

The cost was that `aggregate_benchmark.py`, `generate_report.py` and `verify_pin.py` could not
read anything here. **`export_benchmark.py` closes that by translating rather than by rewriting
the harness**: the native report stays the source of truth and the house layout is a derived
view of it. All three tools now run over this data, which is where the interval above comes from.

Two things the translation cannot fix, both printed where the numbers are:

- A `pass_rate` here is the fraction of a run's **deterministic** checks that passed. It shares a
  name with a judged skill's `pass_rate` and is not the same measurement. The emitted
  `grading.json` says so in a `pass_rate_means` field.
- The coverage cases run one arm, so the default export is 15 treatment cases against 4 baseline
  ones, and the delta `aggregate_benchmark.py` prints for it compares **populations, not arms**.
  The exporter writes a warning to stderr when the arms cover different case sets, and
  `--paired-only` produces the comparison that is actually valid. TC-EV-63 fails if that warning
  ever goes quiet.

**Running the trigger eval.** The house runner takes the flat set directly:

```sh
python3 .claude/skills/skill-creator/scripts/run_eval.py \
  --eval-set skills/text-humanizer/evals/trigger/evals.json \
  --skill-path skills/text-humanizer --num-workers 3 --timeout 150
```

`--timeout` defaults to **30 s**, which is too short here: at that default with six workers, 31
of 60 runs ended as `instrument_failures`, and a negative case whose three runs all crash scores
`trigger_rate 0.00` and **passes vacuously**. Read `instrument_failures` before the summary — a
run with many of them is not a measurement of the description.

### First valid trigger campaign

2026-09-02, 20 queries x 3 runs, **0 of 60 instrument failures**, report at
`trigger/runs/2026-09-02-first.json`. **11 of 20 passed**, and the two halves say opposite
things.

| | Result |
| :--- | :--- |
| Near-misses (should NOT fire) | **8 of 8 pass**, every one at rate 0.00 |
| Natural requests (should fire) | **3 of 12 pass**; mean trigger rate 0.28 |

**Precision is perfect and recall is not.** Nothing was stolen from `artifact-formalizer`
(CHANGELOG, spec register), `html`, `post-writing`, `marp-slide`, `summarizing-meetings` or
code review. But nine of the twelve most natural ways to ask for this skill's *primary* mode do
not reach it:

| Query | Rate |
| :--- | ---: |
| `generate an untraceable prompt for writing wiki-style entries` | 1.00 |
| `I need a reusable system prompt for writing food reviews that don't sound generated` | 1.00 |
| `audit this article for AI markers — just tell me what's wrong` | 0.67 |
| `humanize this marketing email, it's full of 'delve' and 'seamless'` | 0.33 |
| `rewrite …/announce.md so it doesn't read as machine-written` | 0.33 |
| `убери из этого текста признаки, что его писал AI` | 0.00 |
| `this landing page copy reads like ChatGPT wrote it` | 0.00 |
| `сделай текст более человеческим, но не меняй смысл и цифры` | 0.00 |
| `de-slop this blog post before I publish it` | 0.00 |
| `make this sound like a person wrote it, not a model` | 0.00 |
| `проверь мою статью на AI-обороты и канцелярит` | 0.00 |
| `every paragraph is the same length and it's all 'not just X but Y'` | 0.00 |

The split follows the description's two clauses. *"generate untraceable system prompts"* fires
reliably; *"humanize AI-generated text"* — mode 1, the skill's main job — fires at 0.28 on average, and
does not fire on the literal word **humanize** more often than not.

**What this costs the rest of this directory.** The behavioural set scores 75 of 80 checks. The
guide's §3 states the consequence plainly: a description that falls short means the skill does
not fire, "and everything else is irrelevant." Every behavioural figure here is conditional on a
trigger that misses three requests in four.

**How not to fix it.** Hand-editing the description against these twenty queries overfits it to
a set its own author wrote. `skill-creator/scripts/run_loop.py` exists for this and splits
train/test, hiding the test half from the improver (guide §5.2). The set also needs a
near-miss it does not yet carry: a request to de-AI a short story, which spec item R8 puts out
of scope.

## Files

| File | Role |
| :--- | :--- |
| `evals.json` | the fifteen cases, schema `humanizer-evals/v2` |
| `fixtures/` | fifteen texts and one key each, written before the first run. Eight keys carry a declared `max_growth`, the R7 guard |
| `lexicon.py` | the detectors — 29 parsed from the shipped reference file, 2 authored |
| `run_humanize.py` | the executor — the only script here that spends tokens |
| `grade_run.py` | the deterministic grader; no model judge, no token |
| `selftest_evals.py` | the instrument battery, 83 cases, zero tokens |
| `export_benchmark.py` | re-emits a graded campaign in the house layout so `aggregate_benchmark.py` / `verify_pin.py` can read it; `--ci` prints the bootstrap interval. Spends nothing |
| `runs/` | every behaviour campaign, one `<date>-<label>-corpus/` + `<date>-<label>-report.json` pair each |
| `runs/2026-09-02-baseline-*` | the first campaign — the committed baseline |
| `runs/2026-09-02-r2r4-*`, `runs/2026-09-02-r5r6-*` | the redraws that measured spec items R2–R4 and R5–R6 |
| `runs/2026-09-02-control-x3-corpus/` | three extra draws of the control, after R2–R4 |
| `runs/2026-09-02-full-*` | the fifteen-case set. **Stale** since the mode-deliverable fix; kept as the evidence under the R2–R6 comparisons |
| `runs/2026-09-03-multirep-*` | three draws per arm of the four paired cases — the first campaign with an interval. **Stale** |
| `runs/2026-09-03-pressure-*` | the campaign that found the mode-deliverable defect. **Stale**, and kept because it is the evidence for the fix |
| `runs/2026-09-04-full-*` | every case, one draw, against the fixed skill — **the pinned corpus** a future change is compared against (TC-EV-52) |
| `runs/2026-09-04-multirep-*` | the paired set re-drawn post-fix; delta +0.105, CI [0.028, 0.195] |
| `runs/2026-09-04-pressure-*` | the pressure and natural set re-drawn post-fix; delta +0.167, CI [0.042, 0.286] |
| `runs/*-benchmark/` | the house-layout view of a campaign, derived; `benchmark.json` is what `verify_pin.py` checks |
| `trigger/evals.json` | 32 trigger queries, 20 positive and 12 near-misses |
| `trigger/train.json`, `trigger/test.json` | the committed 23/9 split; the test half decided nothing until the end |
| `trigger/runs/` | one file per trigger campaign, named by date and what it tested |

Every intermediate corpus is kept rather than pruned: each one is the evidence behind a figure
quoted above, and a figure whose corpus was deleted is a figure nobody can check.

## Deliberately not here

- **A model judge.** `sepia`'s eval uses one for fact preservation. Declaring the facts as
  literal anchors in the key does the same job, objectively and for free, and the anchors
  are checkable against the fixture — TC-EV-26 asserts every one of them occurs in the text
  it grades.
- **A trigger eval.** Whether the description fires is a separate question from what the
  assembled prompt does, and this harness answers the second.
- **A humanness score.** See *What none of this proves*.

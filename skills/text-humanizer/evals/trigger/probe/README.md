# Was the skill invoked? Measured by what its body did

The idea in this directory is the user's, and it settles a question two
description-tuning campaigns could not.

## The problem with the old instrument

`skill-creator/scripts/run_eval.py` decides "triggered" by scanning up to eight
`tool_use` blocks for a `Skill` call. That is a proxy, and it has been wrong
before — VAL-2's "0 triggers across 69 runs" was the probe, not the description.
It also cannot distinguish *the skill was not chosen* from *the skill was chosen
and ignored*.

## The rig

A probe skill whose body does one mechanical thing: replace twelve ordinary
words with twelve others (`warehouse` → `depot`, `vendor` → `counterparty`, …).
If the replacement appears where the source had the original, the body reached
the model and was applied. Grading is a string test.

The probe is named `copy-editor`, **not** `text-humanizer`. The first run of this
rig used the real name and scored 0/32 — which looked like a result until the
answer was read: it cited `scripts/humanizer.py` and "corporate genre, medium
intensity", neither of which is in the probe body. The real skill at
`~/.claude/skills/text-humanizer` had shadowed it.

Competitors come from the user-level registry, 46 real skills the agent sees
anyway, so routing happens against a realistic field. Copying them into the
project was the first design and it was wrong: the copies duplicated the
user-level entries and the agent saw 107 skills rather than 61.

## Result 1 — arms, `claude-haiku-4-5`, 5 reps

| Arm | What varies | Runs firing |
| :--- | :--- | ---: |
| **D** the query names the skill | — | **30 / 30** |
| **B** a description written to match the request exactly | description | **0 / 30** |
| **A** the real description | description | **0 / 30** |
| **C** no skill installed | — | **0 / 30** |

`claude-sonnet-5`, arm D: 28 / 30. The instrument works on both models.

Arm B is the informative zero. Its description says *"Use this skill whenever the
user gives you a passage of text and asks you to rewrite, edit, clean up,
humanize, de-slop or audit it… Always use it before editing any prose the user
supplies."* It fired **never**.

## Result 2 — four "proprietary procedure" descriptions

The hypothesis: a description naming a project-specific procedure the model
cannot know would make it doubt it can proceed unaided.

| Candidate | Runs firing |
| :--- | ---: |
| `Calibrates a supplied text against this project's house register…` | 0 / 18 |
| `Applies the project's standing terminology list…` | 0 / 18 |
| `Distils a supplied text to the project's editorial standard…` | 0 / 18 |
| the real description + *"applies this project's own calibrated pattern lists… cannot be reconstructed from the text alone"* | 0 / 18 |

Not confirmed. The mechanism is real but a description does not switch it on.

## Result 3 — the ladder, and the answer

Eight request phrasings, the **real** description installed, 2 reps × 6 passages:

| Rung | Phrasing | Rate |
| :--- | :--- | ---: |
| 1 | `/copy-editor <text>` | **1.00** |
| 2 | "Use the copy-editor skill…" | **1.00** |
| 3 | "Use whichever of your skills fits, then clean up this text" | **1.00** |
| 4 | "Check whether you have a skill for this, then clean up this text" | **1.00** |
| 5 | "Run a copy-edit pass over this text" *(confounded: near-names the skill)* | 0.89 |
| 6 | "make this sound like a person wrote it, not a model" | **0.00** |
| 7 | "убери из этого текста признаки, что его писал AI" | **0.00** |
| 8 | "tidy up the wording here before I send it" | **0.00** |

Rungs 3 and 4 **do not name the skill**. They only ask the model to consider
whether it has one. With the real description, that is enough for 12 of 12.

**So the description is not the constraint.** Given that routing is attempted at
all, this description selects correctly every time. The failure is upstream: for
a request it can satisfy directly, the model never asks whether a skill exists.

## What this means for the recorded 3 of 20

`trigger_evals.json`'s recall measures a quantity **no description can move**.
Four alternative descriptions and the real one all score 0.00 on natural
phrasing; the real one scores 1.00 the moment routing is attempted. The two
description-tuning campaigns recorded in `../../README.md` were work on the
wrong lever, and the holdout that rejected both was right for a reason neither
campaign identified.

## Limits, stated plainly

- **The probe body is cheap.** Twelve substitutions cost nothing to apply; the
  real skill assembles a 23,000-character prompt and wants a script run. A model
  may weigh an expensive skill differently, and this rig cannot see that.
- **The name differs.** Rungs 3 and 4 name no skill, so their 1.00 is
  attributable to the description — but rungs 1, 2 and 5 name `copy-editor`, and
  the real skill's name is not that.
- **Two reps per rung.** Enough for a 1.00-versus-0.00 separation, not enough for
  anything finer.
- **One phrasing per rung.** "Natural" here is three phrasings, not a sample of
  how people ask.

## Running it

```sh
python3 run_probe.py --arm D --model claude-haiku-4-5-20251001 --reps 5
python3 run_probe.py --arm A --description-file candidates/E4-hybrid.txt
python3 ladder.py claude-haiku-4-5-20251001 2 real
```

`probe-project/` is rebuilt under the scratchpad on each run; only the rig and
its results are committed here.

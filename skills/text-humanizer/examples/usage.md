# text-humanizer — worked invocations

Every command below was run from `skills/text-humanizer/`. The script assembles a
system prompt on **stdout**; it does not write a file and does not call a model.
What you do with that prompt is the second half of the job, and it is described
under each example.

## 1. Audit before touching anything

Diagnose which paragraphs are Red / Yellow / Green without rewriting. Run this
first — it is what tells you which paragraphs to leave alone.

```bash
python3 scripts/humanizer.py --genre blog --mode audit
```

Feed the emitted prompt the user's text. Expected shape of the answer: a
traffic-light map per paragraph plus the pattern list behind each marker, and no
rewritten text.

## 2. Humanize a blog post at the genre's own intensity

```bash
python3 scripts/humanizer.py --genre blog --style crypto --mode humanize --intensity auto
```

`auto` resolves to `high` for `blog` (A+B+C), so [D] stylistic patterns —
Rule of Three, synonym cycling, colon disease — are deliberately left in place.
Ask for `--intensity max` only when the user wants those touched too.

## 3. Technical documentation, where a stylistic edit is a content edit

```bash
python3 scripts/humanizer.py --genre technical --mode humanize
```

`technical` resolves to `low`: [A] Critical only. A [C] edit in an API
description changes what the sentence promises, which is why the intensity is
not a dial the caller opens by preference.

## 4. Match a user's own voice

```bash
# 1. read references/voice_passport_template.md for the five dimensions
# 2. analyse the user's samples along them, 3-5 lines, into a scratch file
python3 scripts/humanizer.py --genre blog --mode humanize --voice /tmp/voice_passport.md
```

Without `--voice` the default voice is "smart person explaining to a friend over
coffee". That default is fine for generic copy and wrong for anyone whose
samples you were given.

## 5. A reusable prompt for another chat

```bash
python3 scripts/humanizer.py --genre marketing --style food --mode prompt-gen --intensity max
```

`prompt-gen` returns a standalone system prompt the user can paste elsewhere; it
carries the merged pattern set, so it keeps working without this skill installed.

## Verifying the result

The rewrite is finished when every pass holds:

1. no leftover [A]/[B] markers for the resolved intensity,
2. it reads as a stranger wrote it, not as a list of avoided words -- **and** nothing was
   over-corrected: no roughness the genre does not support, no informality absent from the voice
   passport, no aside invented for the rewrite,
3. sentence length varies (check the "cardiogram" on texts over 300 words), without exceeding the
   author's own range,
4. at `max` and `high` intensity, the first sentences of the paragraphs do not read as a clean
   summary of the text (the outline test). This pass is absent from the prompt at every lower
   intensity, so at `--genre technical` there is nothing to check.

A text that passes (1) and fails (3) still reads as generated. A text that passes (1) and fails
the over-correction half of (2) reads as edited, which is a different tell and not a better one.

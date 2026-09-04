---
name: text-humanizer
description: Use when a text needs to stop reading as machine-written, or when you need a reusable system prompt that writes that way. Humanize a draft, de-slop it, clean up the wording, or audit it for AI phrasing. Covers requests like "make this sound like a person wrote it" or "убери признаки, что писал AI". Non-fiction only, never a short story, a novel chapter or a screenplay.
tier: 2
version: 2.1
---

# Text Humanizer Skill

This skill helps users create content that sounds human, not algorithmic. It has three modes:
1.  **Humanize**: Rewrites existing text to remove AI patterns using traffic-light diagnosis, contrastive subtraction, and a staged verification pass.
2.  **Audit**: Diagnoses AI markers in text WITHOUT rewriting. Returns a traffic-light map and pattern list.
3.  **Generate Prompt**: Creates a specialized System Prompt for a specific genre/domain that the user can use in other chats.

## Scope boundary — what this is NOT

**Long-form fiction is out of scope.** A short story, a novel chapter, a screenplay: this skill
edits the surface of a text — vocabulary, syntax, punctuation, paragraph rhythm — and in fiction
that surface carries a small share of what marks a text as machine-written. Measured: a classifier
using only discourse-level narrative features (plot continuity, thematic explicitness, how emotion
is conveyed, chronology) separates human from AI fiction at 93.2% macro-F1, and stylistic
span-rewriting of the kind this skill performs moved it by 1.6 points, from 95.5% to 93.9%
(StoryScope, [arXiv:2604.03136](https://arxiv.org/abs/2604.03136); LAMP, CHI 2025).

Running this skill on a story therefore returns a cleaner surface over the same narrative
architecture. That is not nothing, and it is not what the request usually means. Say so, and offer
the nearest thing that is in scope: `--genre blog` covers essayistic and personal writing, which is
what `patterns_creative.md` was written for.

**Why the skill is not extended to cover it.** The architecture does not fit. `humanizer.py`
assembles a prompt from lists of things not to do, filtered by the `[A]`-`[D]` tags. A narrative
layer is not a list of don'ts: it is a sheet of structural decisions with calibration bands —
subplot or none, resolution driven by choice or by circumstance, where the reveal lands — chosen
**before** drafting and applied a few per story. Nothing in that passes through
`filter_patterns_by_priority`. It is a different skill, not a genre in this one.

**The description says so too, because that is what routing reads.** A boundary stated only here
is read after the skill has already been chosen. `description` used to advertise a "Creative"
genre, which is what invited fiction requests; it now says **non-fiction** and names the exclusion.
The genre that "Creative" meant is `blog` — essayistic, opinion, social and personal writing, the
scope of `references/patterns_creative.md`.

## Red Flags (Anti-Rationalization)

**STOP and READ THIS if you are thinking:**
- "I'll just read the markdown files and rewrite by hand" → **WRONG**. Run
  `scripts/humanizer.py`. It merges universal patterns with genre exceptions, applies the
  intensity filter and emits the verification steps; done by hand, the genre exceptions are
  the first thing dropped.
- "The whole text reads like AI, I'll rewrite all of it" → **WRONG**. Traffic-light
  diagnosis exists because over-editing *introduces* AI patterns. Green paragraphs are not
  touched.
- "More edits means more human" → **WRONG**. One contrastive substitution beats three
  stylistic edits. Volume of change is not the metric.
- "The user gave writing samples, I'll imitate the vibe" → **WRONG**. Build the voice
  passport along the five documented dimensions and pass it with `--voice`; an
  unstructured impression is not reproducible across paragraphs.
- "It's legal/technical text, but max intensity is safer" → **WRONG**. Intensity is
  auto-derived from genre for a reason: a D-level stylistic edit in legal text changes what
  the sentence commits to.

### Rationalization Table
| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "The em dashes are the author's style" | Then show it. A habit recorded in the voice passport from the user's own samples is whitelisted and stays. A claim about the author's style with no sample behind it is a guess, and the [A] rule applies to it. |
| "I removed the markers, so it is done" | Removal is pass one of three. Read it as a stranger and check length variance — a marker-free text with uniform sentence length still reads as generated. |
| "Audit mode first is an extra step" | Audit is what tells you which paragraphs are Green. Skipping it is how a clean paragraph gets rewritten. |
| "I'll pick the genre that gives the strongest rewrite" | The genre is a property of the text, not a dial. Choosing it for the intensity it unlocks corrupts both. |
| "The script has no output file, so nothing happened" | It writes to stdout by design. Capture it, or pass the path the mode documents. |
## Execution Mode

- **Mode**: `hybrid`
- **Why this mode**: `scripts/humanizer.py` is deterministic assembly — it merges the universal pattern list with the genre list, filters both by the resolved intensity, and injects style, voice passport and extra rules into `assets/generator_template.md`. The rewriting itself is model judgement performed against the prompt that assembly produces. No script edits text, and a hand-assembled prompt drops the genre exceptions first.

## Script Contract

- **Command**: `python3 scripts/humanizer.py --genre {encyclopedic|academic|technical|journalistic|science|blog|social|marketing|corporate|food|crypto} [--style STYLE] [--mode humanize|audit|prompt-gen] [--intensity auto|max|high|medium|low|minimal] [--task TEXT] [--voice PATH] [--extra-rules TEXT]`
- **Where the input text comes from**: not from the script. `humanizer.py` has no positional argument and no `--input`; it never reads the user's text. It writes a system prompt, and you apply that prompt to the text held in the conversation. `--task` is a one-line description of the job, not the text itself.
- **Inputs**: flags only. `--genre` is the sole required flag. Defaults: `--mode humanize`, `--intensity auto` (resolved per genre), `--style` falls back to the genre name, `--voice` and `--extra-rules` empty.
- **Outputs**: the assembled prompt on **stdout**. No file is written and no model is called. Warnings — `--style` not found, `--voice` file missing — go to stderr and leave the exit code alone.
- **Exit codes**: `0` whenever a prompt is produced; `2` for argparse usage errors (missing or unknown `--genre`, `--mode`, `--intensity`). A `--voice` path that exists but is not a readable file (a directory) raises through as exit `1`.
- **Idempotency**: identical flags produce byte-identical stdout, and there is nothing to overwrite.

## Safety Boundaries

- **Allowed scope**: read-only. The script reads its own `references/` and `assets/`, plus the single file named by `--voice`. It creates, modifies and deletes nothing.
- **`--voice` is uncontained**: any readable path is loaded verbatim into the emitted prompt. Pass a scratch file written for this purpose, not a path the user has not seen.
- **Destructive actions**: none. "Remove AI patterns" in this skill is prose editing the model performs on text in the conversation — reversible, reviewable, never a file mutation.
- **Stop condition**: Green paragraphs are not rewritten, and audit mode stops at the diagnosis. Over-editing reintroduces the patterns the skill exists to remove.

## Validation Evidence

- **Local verification** — stdlib only, no venv; paths are relative to `skills/text-humanizer/`:
  - `cd scripts && python3 -m unittest discover -s tests` — 56 tests, OK.
  - `python3 scripts/humanizer.py --genre marketing --mode prompt-gen | grep -c '^### [0-9]'` — 7; `--mode audit` 8; `--mode humanize` 9. The digit is load-bearing: it counts the template's own sections, so a heading inside an injected pattern file cannot move the number.
  - `--genre technical` emits `[A]` sections only, `--genre marketing` all four; `--genre bogus` exits 2, `--style bogus` exits 0 with a stderr warning.
- **Behavioural evals**: `python3 evals/selftest_evals.py` — 83 cases, zero tokens, no agent spawned; it measures the instrument, not the skill. A campaign measures the skill: `evals/run_humanize.py` then `evals/grade_run.py`. 21 cases on four axes — failure-mode, coverage over every genre and style file, pressure, and natural prose copied verbatim from repository files. Latest sweep, `claude-sonnet-5`, 2026-09-04: **75 of 80 checks, 21 of 21 measured**. Two comparisons carry an interval: the four paired cases under a neutral brief give delta **+0.105, 95% CI [0.028, 0.195]**, and the six pressure/natural cases give **+0.167, CI [0.042, 0.286]** — the skill helps *more* when the brief leans on it, which is what its doctrine is for. Each report records the SHA of the assembled prompt its runs saw and flags itself stale when the skill moves. **Trigger evals** are a separate check with its own set, `evals/trigger/evals.json`, run by `skill-creator/scripts/run_eval.py`. Figures, the campaigns, the self-audit against `docs/Manuals/skill-evals_guide.md` §11.1, and what a single draw does not license: [`evals/README.md`](evals/README.md).
- **Gate**: `python3 skills/skill-enhancer/scripts/analyze_gaps.py skills/text-humanizer` from the repo root — no `[Execution Policy]` advisories.

## Usage

### Mode 1: Humanize Text
Rewrites text to remove AI patterns with adaptive intensity.

```bash
python3 scripts/humanizer.py --genre [encyclopedic|blog|marketing|...] --style [crypto|food|science|...] --mode humanize --intensity [auto|max|high|medium|low|minimal]
```

### Mode 2: Audit Text
Diagnoses AI markers without rewriting. Use when the user wants to see what's wrong before committing to changes.

```bash
python3 scripts/humanizer.py --genre [encyclopedic|blog|marketing|...] --mode audit
```

### Mode 3: Generate System Prompt
Creates a reusable prompt.

```bash
python3 scripts/humanizer.py --genre [encyclopedic|blog|marketing|...] --style [crypto|food|science|...] --mode prompt-gen --intensity [auto|max|high|medium|low|minimal]
```

### Optional: Voice Passport
When the user provides writing samples, follow this workflow:

1.  **Read** `references/voice_passport_template.md` to understand the 5 analysis dimensions.
2.  **Analyze** the user's writing samples along those dimensions.
3.  **Write** the resulting 3-5 line voice passport to a temp file (e.g., `/tmp/voice_passport.md`).
4.  **Pass** the file to the script:

```bash
python3 scripts/humanizer.py --genre blog --mode humanize --voice /tmp/voice_passport.md
```

If no `--voice` is provided, the default voice is "smart person explaining to a friend over coffee."

> [!IMPORTANT]
> **Red Flag**: Stop if you think "I'll just read the markdown files manually." **WRONG.**
> You MUST run `scripts/humanizer.py`. It handles the complex logic of merging universal patterns, rewriting strategy, genre-specific exceptions, intensity filtering, and verification steps. Reading files manually introduces human error and laziness.

## Key Concepts (v2.0)

### Pattern Priorities (A/B/C/D)
Not all patterns are equal. Each is tagged:
*   **[A] Critical** -- Always fix (AI vocabulary, chatbotisms, negative parallelism, em dash abuse),
    subject to the whitelist in `references/patterns_universal.md`: a habit evidenced in the voice
    passport, a domain term you can point at, and quoted material are not findings. [A] is the only
    class that fires at `low` and `minimal`, so it is the class where a false positive costs most.
*   **[B] High** -- Fix in all modes except legal text.
*   **[C] Medium** -- Fix in full editing and expert content.
*   **[D] Stylistic** -- Fix by context (Rule of Three, Synonym Cycling, Colon Disease).

### Intensity Levels
Controls how many priority levels to fix. Auto-detected from genre:
*   **max** (marketing, social) -> A+B+C+D
*   **high** (blog, food, crypto) -> A+B+C
*   **medium** (corporate, journalistic, encyclopedic) -> A+B
*   **low** (technical) -> A only
*   **minimal** (legal) -> A only, cautiously

### Traffic-Light Diagnosis
Before rewriting, paragraphs are classified:
*   **Red** (3+ markers) -> Full rewrite.
*   **Yellow** (1-2 markers) -> Spot fix.
*   **Green** (clean) -> DO NOT TOUCH. Over-editing introduces new AI patterns.

### Contrastive Subtraction (CoPA)
Beyond removing bad patterns, actively replace the most predictable word in each sentence with a less probable but appropriate alternative. One such replacement beats three stylistic edits.

### Verification Passes
After rewriting: (1) scan for leftover patterns; (2) read as a stranger, then ask the opposite
question and report **over-correction** separately -- an overshooting edit leaves its own
fingerprint, and the target is the human band rather than the pole opposite the AI one;
(3) check sentence length variance ("cardiogram" for 300+ word texts), bounded by a ceiling so
spikes stop at the band; (4) at `max` and `high` intensity only, the **outline test** -- read the
first sentence of each paragraph as a list, and if it forms a clean summary the structure is
machine-shaped. Pass 4 is stripped from the emitted prompt at every lower intensity, because a
clean outline is the goal in an API reference, a news lead and a BLUF memo.

## Resources

*   [Taxonomy & Intensity](references/taxonomy.md)
*   [Universal Patterns (The "Don'ts")](references/patterns_universal.md)
*   [Rewriting Strategy (The "How")](references/rewriting_strategy.md)
*   [Encyclopedic Patterns](references/patterns_wiki.md)
*   [Creative Patterns](references/patterns_creative.md)
*   [Voice Passport Template](references/voice_passport_template.md)
*   [Domain Styles](references/styles/)
*   [Prompt Template](assets/generator_template.md)
*   [Behavioural evals](evals/README.md) — twenty-one cases on four axes, deterministic grading, committed baseline

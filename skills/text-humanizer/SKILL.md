---
name: text-humanizer
description: Use when you need to humanize AI-generated text or generate untraceable system prompts. Supports multiple genres (Wiki, Creative, Crypto, etc.).
tier: 2
version: 2.1
---

# Text Humanizer Skill

This skill helps users create content that sounds human, not algorithmic. It has three modes:
1.  **Humanize**: Rewrites existing text to remove AI patterns using traffic-light diagnosis, contrastive subtraction, and triple-pass verification.
2.  **Audit**: Diagnoses AI markers in text WITHOUT rewriting. Returns a traffic-light map and pattern list.
3.  **Generate Prompt**: Creates a specialized System Prompt for a specific genre/domain that the user can use in other chats.

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
| "The em dashes are the author's style" | Em-dash abuse is an [A] Critical marker. Author style is what the voice passport records; an unmeasured claim about style is a guess. |
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
  - `cd scripts && python3 -m unittest discover -s tests` — 19 tests, OK.
  - `python3 scripts/humanizer.py --genre technical --mode humanize | grep "^## " | grep -o "\[[A-D]\]" | sort -u` — prints `[A]` alone, because `technical` resolves to intensity `low`; the same command with `--genre marketing` prints all four tags.
  - `python3 scripts/humanizer.py --genre marketing --mode prompt-gen | grep -c '^### '` — 9; `--mode audit` gives 10 and `--mode humanize` 11 (prompt-gen strips Diagnosis and Verification, audit strips Verification).
  - `python3 scripts/humanizer.py --genre blog --style bogus >/dev/null` — exit 0 with a stderr warning; `--genre bogus` exits 2.
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
*   **[A] Critical** -- Always fix (AI vocabulary, chatbotisms, negative parallelism, em dash abuse).
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

### Triple-Pass Verification
After rewriting: (1) scan for leftover patterns, (2) read as a stranger, (3) check sentence length variance ("cardiogram" for 300+ word texts).

## Resources

*   [Taxonomy & Intensity](references/taxonomy.md)
*   [Universal Patterns (The "Don'ts")](references/patterns_universal.md)
*   [Rewriting Strategy (The "How")](references/rewriting_strategy.md)
*   [Encyclopedic Patterns](references/patterns_wiki.md)
*   [Creative Patterns](references/patterns_creative.md)
*   [Voice Passport Template](references/voice_passport_template.md)
*   [Domain Styles](references/styles/)
*   [Prompt Template](assets/generator_template.md)

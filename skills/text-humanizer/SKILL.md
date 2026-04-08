---
name: text-humanizer
description: Use when you need to humanize AI-generated text or generate untraceable system prompts. Supports multiple genres (Wiki, Creative, Crypto, etc.).
tier: 2
version: 2.0
---

# Text Humanizer Skill

This skill helps users create content that sounds human, not algorithmic. It has three modes:
1.  **Humanize**: Rewrites existing text to remove AI patterns using traffic-light diagnosis, contrastive subtraction, and triple-pass verification.
2.  **Audit**: Diagnoses AI markers in text WITHOUT rewriting. Returns a traffic-light map and pattern list.
3.  **Generate Prompt**: Creates a specialized System Prompt for a specific genre/domain that the user can use in other chats.

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

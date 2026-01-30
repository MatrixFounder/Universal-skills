---
name: text-humanizer
description: Use when you need to humanize AI-generated text or generate untraceable system prompts. Supports multiple genres (Wiki, Creative, Crypto, etc.).
tier: 2
version: 1.0
---

# Text Humanizer Skill

This skill helps users create content that sounds human, not algorithmic. It has two main modes:
1.  **Humanize**: Rewrites existing text to remove "AI slop" (phrases like "delve", "tapestry", "serves as a testament").
2.  **Generate Prompt**: Creates a specialized System Prompt for a specific genre/domain that the user can use in other chats.

## Usage

### Mode 1: Humanize Text
Rewrites text to remove AI patterns.

1.  **Execute Script**: Run the humanizer tool.
    ```bash
    python3 scripts/humanizer.py --genre [encyclopedic|blog|marketing] --style [crypto|food|science] --mode humanize
    ```
2.  **Paste Text**: The script (or agent) will then apply the generated logic to the user's text.

### Mode 2: Generate System Prompt
Creates a reuseable prompt.

1.  **Execute Script**:
    ```bash
    python3 scripts/humanizer.py --genre [encyclopedic|blog|marketing] --style [crypto|food|science] --mode prompt-gen
    ```
2.  **Output**: Give the code block to the user.

> [!IMPORTANT]
> **Red Flag**: Stop if you think "I'll just read the markdown files manually." **WRONG.**
> You MUST run `scripts/humanizer.py`. It handles the complex logic of merging universal patterns with genre-specific exceptions. Reading files manually introduces human error and laziness.


## Resources

*   [Taxonomy (Genres)](references/taxonomy.md)
*   [Universal Patterns (The "Don'ts")](references/patterns_universal.md)
*   [Encyclopedic Patterns](references/patterns_wiki.md)
*   [Creative Patterns](references/patterns_creative.md)
*   [Domain Styles](references/styles.md)
*   [Prompt Template](assets/generator_template.md)

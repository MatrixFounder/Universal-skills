# Text Humanizer Skill User Manual

This manual describes how to use the `text-humanizer` skill to eliminate "AI slop" from your writing and generate high-quality system prompts.

The skill is built on the strict analysis of AI writing patterns provided by the **[WikiProject AI Cleanup](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)**.

## Table of Contents
1.  [Core Concepts](#1-core-concepts)
2.  [Available Classifiers](#2-available-classifiers)
3.  [Modes of Operation](#3-modes-of-operation)
4.  [Advanced Usage (Mix & Match)](#4-advanced-usage-mix--match)
5.  [Recommended Workflow](#5-recommended-workflow)
    *   [Step 1: Collection & Prep](#step-1-collection--prep)
    *   [Step 2: Draft Creation & Finalization](#step-2-draft-creation--finalization-combined)
    *   [Workflow 2: Advanced RAG / "Clone Yourself" Agent](#workflow-2-advanced-rag--clone-yourself-agent)
    *   [Workflow 3: Custom Constraints (Ad-Hoc Rules)](#workflow-3-custom-constraints-ad-hoc-rules)

## 1. Core Concepts

The skill separates text generation into two layers:

1.  **Genre (Structural Goal):** Determines the *fundamental ruleset*.
    *   **Neutral/Objective:** Uses strict Wiki-style rules (No opinions, no "peacock terms", neutral point of view).
    *   **Creative/Subjective:** Uses creative rules (Allows first-person "I", opinions, sensory details).
2.  **Style (Domain Overlay):** A specific dictionary of prohibited words and preferred tone for a niche (e.g., Crypto, Food, Corporate).

## 2. Available Classifiers

You can mix and match Genres and Styles, but usually, just picking a specific Genre is enough (the skill auto-detects the matching Style).

### Genres (Primary Input)
| Genre | Base Ruleset | Best For |
| :--- | :--- | :--- |
| `encyclopedic` | **Neutral** | Wikipedia, Docs, Research |
| `academic` | **Neutral** | Essays, Papers |
| `technical` | **Neutral** | Manuals, API Docs |
| `journalistic` | **Neutral** | News, Reports |
| `science` | **Neutral** | Scientific Reporting |
| `blog` | **Creative** | Personal Essays, Opinions |
| `social` | **Creative** | LinkedIn, Twitter, Telegram |
| `marketing` | **Creative** | Landing Pages, Ads |
| `corporate` | **Creative/Obj** | Internal Memos, B2B |
| `food` | **Creative** | Reviews, Recipes |
| `crypto` | **Creative** | Web3 updates, Telegram |

### Styles (Domain Overlays)
These are automatically loaded if they match the Genre name, or can be forced manually.
*   `academic`
*   `corporate`
*   `crypto`
*   `food`
*   `journalistic`
*   `marketing`
*   `science`
*   `technical`

## 3. Modes of Operation

### Mode A: Humanize Text
**Goal:** Rewrite existing AI-generated text to remove patterns like "delve", "tapestry", and "serves as a testament".

#### User Prompt Template
> "Humanize this text using the **[Genre]** genre."

#### Examples
*   **For a Wiki article:**
    > "Humanize this text about the Eiffel Tower. Use the **Encyclopedic** genre."
    *   *Result:* Removes "breathtaking marvel", "iconic symbol". Keeps facts.
*   **For a LinkedIn post:**
    > "Humanize this post about my new job. Use the **Corporate** genre."
    *   *Result:* Removes "thrilled to announce", "humbled", "journey". Adds specific achievements.
*   **For a Crypto announcement:**
    > "Humanize this update. Use the **Crypto** genre."
    *   *Result:* Removes "revolutionizing finance". Adds "TVL", "Mainnet launch".

---

### Mode B: Generate System Prompt
**Goal:** Create a powerful System Prompt that you can paste into another chat (or use in an Agent) to permanently enforce these rules.

#### User Prompt Template
> "Generate a system prompt for a **[Genre]** writer."

#### Examples
*   **For a Food Blogger:**
    > "Generate a system prompt for a **Food** writer."
    *   *Result:* A prompt instructing the AI to use sensory words (crunchy, acidity) and avoid generic praise (delicious, yummy).
*   **For a News Bot:**
    > "Generate a system prompt for a **Journalistic** bot."
    *   *Result:* A prompt enforcing the Inverted Pyramid structure and forbidding vague attributions ("Experts say").
*   **For Technical Docs:**
    > "Generate a system prompt for a **Technical** writer."
    *   *Result:* A prompt enforcing second-person imperative ("Run this"), forbidding future tense ("The system will send"), and banning "seamless/intuitive".

## 4. Advanced Usage (Mix & Match)

You can specify a **Genre** (structure) and a distinct **Style** (overlay) if you need a unique combination.

**Scenario:** You want to write a *neutral, factual report* about a *crypto project* (without the slang/hype).

**User Prompt:**
> "Humanize this text. Genre: **Encyclopedic**. Style: **Crypto**."

*   **Logic Applied:**
    1.  **Genre: Encyclopedic** -> Loads `patterns_wiki.md` (Neutral tone, no opinions).
    2.  **Style: Crypto** -> Loads `styles/crypto.md` (Domain vocabulary: TVL, zk-rollup).
    3.  **Result:** A dry, factual description of a crypto protocol, without "To the moon!" or "Revolutionary!" hype.

## 5. Recommended Workflow

To create high-quality, human-sounding content from scratch, follow this pipeline:

### Step 1: Collection & Prep
Gather your raw materials (research, data points, rough notes). Do NOT worry about style yet. Just get the facts into a document.

### Step 2: Draft Creation & Finalization (Combined)
Instead of writing a rough draft and then editing it, use the **Generate System Prompt** mode to create a writer that does it right the first time.

1.  **Generate the Persona**:
    *   Run: `"Generate a system prompt for a [Genre] writer."`
    *   Copy the output code block.
2.  **Paste into Chat**:
    *   Open a new chat with your AI models.
    *   Paste the System Prompt.
3.  **Feed the Data**:
    *   "Here are my availability notes. Write a [Genre] post based on them."
4.  **Result**:
    *   The AI will produce a draft that already adheres to the style guide, avoiding "delve", "tapestry", and "serves as a testament" from the very first token.


### Workflow 2: Advanced RAG / "Clone Yourself" Agent
You can build an Agent that mimics **your specific writing style** (via RAG/Files) while using the Humanizer to ensure it doesn't drift into "AI Slop".

**Why this works:**
*   **RAG/Files:** Provide the *Positive Constraints* (Vocabulary, Sentence Length, Topics).
*   **Humanizer Prompt:** Provides the *Negative Constraints* (No "delve", No "tapestry", No "In conclusion").

**Setup:**
1.  **Generate the Guardrails**:
    *   Run: `"Generate a system prompt for a [Genre] writer."` (e.g., Blog).
2.  **Configure the Agent**:
    *   **System Prompt**: Paste the output from Step 1.
    *   **Knowledge Base**: Upload 5-10 PDF/Text files of your *best* previous articles.
3.  **Instruction**:
    *   Add this dynamic instruction to your Agent's task:
        > "Read the attached reference files to understand the author's voice (humor, cadence, vocabulary). Write a new article about [Topic] mimicking this voice, BUT strictly adhering to the System Prompt's anti-pattern rules (e.g., never use 'delve' even if the author does)."
4.  **Outcome**:
    *   The Agent writes utilizing your "vibe" but is forced to pass the "Turing Test" of the Humanizer rules. It fixes your bad habits (if you overuse "Moreover") while keeping your soul (your jokes/insights).


### Workflow 3: Custom Constraints (Ad-Hoc Rules)
You can inject specific, one-time rules into the prompt generation without creating a new style file.

**Scenario:** You want a Crypto post but forbid the letter "E" (Oulipo style) or specifically ban a competitor's name.

**Prompt:**
> "Generate a system prompt for a **Crypto** writer. Extras: 'Do not use the letter E. Never mention Ethereum.'"

**Mechanism:**
*   The Agent passes `--extra-rules` to the script.
*   The script injects this into the "User Custom Constraints" section of the System Prompt.
*   **Result:** A standard Crypto prompt + your specific constraints.

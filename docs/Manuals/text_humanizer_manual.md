# Text Humanizer Skill User Manual (v2.0)

This manual describes how to use the `text-humanizer` skill to eliminate "AI slop" from your writing and generate high-quality system prompts.

The skill is built on the strict analysis of AI writing patterns provided by the **[WikiProject AI Cleanup](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)**, enhanced with research from CoPA (EMNLP 2025), DivEye, and TH-Bench.

## Table of Contents
1.  [Core Concepts](#1-core-concepts)
2.  [Available Classifiers](#2-available-classifiers)
3.  [Modes of Operation](#3-modes-of-operation)
4.  [Intensity Levels](#4-intensity-levels)
5.  [Advanced Usage (Mix & Match)](#5-advanced-usage-mix--match)
6.  [Recommended Workflows](#6-recommended-workflows)
7.  [Scope Boundary](#7-scope-boundary)
8.  [Invoking the Skill](#8-invoking-the-skill)
    *   [Workflow 1: Write It Right the First Time](#workflow-1-write-it-right-the-first-time)
    *   [Workflow 2: Advanced RAG / "Clone Yourself" Agent](#workflow-2-advanced-rag--clone-yourself-agent)
    *   [Workflow 3: Voice Passport (Style Matching)](#workflow-3-voice-passport-style-matching)
    *   [Workflow 4: Custom Constraints (Ad-Hoc Rules)](#workflow-4-custom-constraints-ad-hoc-rules)

## 1. Core Concepts

The skill separates text generation into three layers:

1.  **Genre (Structural Goal):** Determines the *fundamental ruleset*.
    *   **Neutral/Objective:** Uses strict Wiki-style rules (No opinions, no "peacock terms", neutral point of view).
    *   **Creative/Subjective:** Uses creative rules (Allows first-person "I", opinions, sensory details).
2.  **Style (Domain Overlay):** A specific dictionary of prohibited words and preferred tone for a niche (e.g., Crypto, Food, Corporate).
3.  **Intensity (The Throttle):** Controls how many patterns to fix, from `max` (fix everything) to `minimal` (only critical markers). Auto-detected from genre if not specified.

### What's New in v2.0

*   **Pattern Priorities [A]/[B]/[C]/[D]:** Each pattern is tagged by severity. Intensity controls which priority levels get fixed.
*   **Traffic-Light Diagnosis:** Before rewriting, paragraphs are classified Red/Yellow/Green. Clean paragraphs are left untouched to avoid introducing new AI markers.
*   **Contrastive Subtraction (CoPA):** Beyond removing bad patterns, the skill actively replaces the most predictable word in each sentence with a less probable but appropriate alternative.
*   **Triple-Pass Verification:** After rewriting, three passes check for leftover patterns, "stranger on the street" readability, and sentence length variance.
*   **Audit Mode:** Diagnose AI markers without rewriting.
*   **Voice Passport:** Structured analysis of an author's writing style for consistent voice matching.

## 2. Available Classifiers

You can mix and match Genres and Styles, but usually, just picking a specific Genre is enough (the skill auto-detects the matching Style and Intensity).

### Genres (Primary Input)
| Genre | Base Ruleset | Default Intensity | Best For |
| :--- | :--- | :--- | :--- |
| `encyclopedic` | **Neutral** | medium | Wikipedia, Docs, Research |
| `academic` | **Neutral** | medium | Essays, Papers |
| `technical` | **Neutral** | low | Manuals, API Docs |
| `journalistic` | **Neutral** | medium | News, Reports |
| `science` | **Neutral** | medium | Scientific Reporting |
| `blog` | **Creative** | high | Personal Essays, Opinions |
| `social` | **Creative** | max | LinkedIn, Twitter, Telegram |
| `marketing` | **Creative** | max | Landing Pages, Ads |
| `corporate` | **Creative/Obj** | medium | Internal Memos, B2B |
| `food` | **Creative** | high | Reviews, Recipes |
| `crypto` | **Creative** | high | Web3 updates, Telegram |

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
**Goal:** Rewrite existing AI-generated text to remove patterns. Uses traffic-light diagnosis, contrastive subtraction, and triple-pass verification.

#### User Prompt Template
> "Humanize this text using the **[Genre]** genre."

#### Examples
*   **For a Wiki article:**
    > "Humanize this text about the Eiffel Tower. Use the **Encyclopedic** genre."
    *   *Result:* Removes "breathtaking marvel", "iconic symbol". Keeps facts. Clean paragraphs left untouched.
*   **For a LinkedIn post:**
    > "Humanize this post about my new job. Use the **Corporate** genre."
    *   *Result:* Removes "thrilled to announce", "humbled", "journey". Adds specific achievements.
*   **For a Crypto announcement:**
    > "Humanize this update. Use the **Crypto** genre."
    *   *Result:* Removes "revolutionizing finance". Adds "TVL", "Mainnet launch".

---

### Mode B: Audit Text
**Goal:** Diagnose AI markers in text WITHOUT rewriting. Returns a traffic-light map (Red/Yellow/Green per paragraph) and a list of detected patterns with examples.

#### User Prompt Template
> "Audit this text for AI markers. Use the **[Genre]** genre."

#### When to Use
*   You want to see what's wrong before committing to a rewrite.
*   You want to learn which patterns to watch for in your own writing.
*   You need to assess whether text needs humanization at all.

---

### Mode C: Generate System Prompt
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
    > "Generate a system prompt for a **Technical** writer with low intensity."
    *   *Result:* A prompt enforcing second-person imperative ("Run this"), forbidding future tense, banning "seamless/intuitive". Only critical [A] patterns included due to low intensity.

## 4. Intensity Levels

Intensity controls how aggressively the skill edits. Each pattern is tagged with a priority `[A]` through `[D]`, and intensity determines which levels get fixed.

| Intensity | Patterns Fixed | Use Case |
| :--- | :--- | :--- |
| `max` | [A] + [B] + [C] + [D] | Marketing, social media, blog posts. Full rewrite. |
| `high` | [A] + [B] + [C] | Expert content (articles, Substack, Medium). Strong editing. |
| `medium` | [A] + [B] | Business correspondence, product docs. Obvious markers only. |
| `low` | [A] only | Technical documentation, specifications. Minimal touch. |
| `minimal` | [A] only (cautiously) | Legal, regulatory text. Never change meaning. |

### Pattern Priorities
*   **[A] Critical** -- AI Vocabulary, Negative Parallelism ("Not just X, but Y"), Em Dash Abuse, Chatbotisms, Puffery, "Serves as a testament". Fixed at ALL intensity levels.
*   **[B] High** -- False Range, Meaningless Transitions, "-ing" Footer, Authoritative Truisms, Responsibility Disclaimers, Uniform Information Density, Weasel Words, Moralizing. Fixed at `medium` and above.
*   **[C] Medium** -- First Person usage, Let Some Mess In, Hard Cuts, Copula Avoidance, Broader Trends. Fixed at `high` and above.
*   **[D] Stylistic** -- Rule of Three, Synonym Cycling, Colon Disease. Fixed only at `max`.

### Specifying Intensity
> "Humanize this text. Genre: **Technical**. Intensity: **low**."

If you don't specify intensity, the skill auto-detects from the genre (see the table in Section 2).

### Special Rules
*   **Direct quotes** inside any text: never edited, regardless of intensity.
*   **Short texts** (<100 words): only 2-3 key markers are fixed.
*   **Already good text**: the skill will say so rather than edit for the sake of editing.

## 5. Advanced Usage (Mix & Match)

You can specify a **Genre** (structure) and a distinct **Style** (overlay) if you need a unique combination.

**Scenario:** You want to write a *neutral, factual report* about a *crypto project* (without the slang/hype).

**User Prompt:**
> "Humanize this text. Genre: **Encyclopedic**. Style: **Crypto**."

*   **Logic Applied:**
    1.  **Genre: Encyclopedic** -> Loads `patterns_wiki.md` (Neutral tone, no opinions).
    2.  **Style: Crypto** -> Loads `styles/crypto.md` (Domain vocabulary: TVL, zk-rollup).
    3.  **Intensity: medium** (auto-detected from Encyclopedic) -> Only [A] + [B] patterns fixed.
    4.  **Result:** A dry, factual description of a crypto protocol, without "To the moon!" or "Revolutionary!" hype.

## 6. Recommended Workflows

### Workflow 1: Write It Right the First Time
Use the **Generate System Prompt** mode to create a writer that avoids AI patterns from the start.

1.  **Generate the Persona**:
    *   Run: `"Generate a system prompt for a [Genre] writer."`
    *   Copy the output code block.
2.  **Paste into Chat**:
    *   Open a new chat with your AI model.
    *   Paste the System Prompt.
3.  **Feed the Data**:
    *   "Here are my notes. Write a [Genre] post based on them."
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

### Workflow 3: Voice Passport (Style Matching)
When the user provides writing samples, use the Voice Passport to capture their style and apply it consistently during humanization.

**Steps:**
1.  **Collect Samples**: Gather 3-5 examples of the user's writing (emails, posts, articles).
2.  **Analyze**: Read `references/voice_passport_template.md` and analyze the samples along 5 dimensions:
    *   **Rhythm:** Sentence length, variability, favorite constructions.
    *   **Lexicon:** Formality level (1-10), jargon, register mixing.
    *   **Quirks:** Signature phrases, digressions, humor style.
    *   **Punctuation:** Preferred marks, density, unconventional usage.
    *   **Tone:** Default stance, emotional range, relationship to reader.
3.  **Write the Passport**: Summarize in 3-5 lines and save to a file.
4.  **Apply**: Pass the passport file when humanizing:
    > "Humanize this text. Genre: **Blog**. Voice: **path/to/voice_passport.md**."
5.  **Result**: The rewritten text matches the author's voice while being free of AI patterns.

### Workflow 4: Custom Constraints (Ad-Hoc Rules)
You can inject specific, one-time rules into the prompt generation without creating a new style file.

**Scenario:** You want a Crypto post but forbid the letter "E" (Oulipo style) or specifically ban a competitor's name.

**Prompt:**
> "Generate a system prompt for a **Crypto** writer. Extras: 'Do not use the letter E. Never mention Ethereum.'"

**Mechanism:**
*   The Agent passes `--extra-rules` to the script.
*   The script injects this into the "User Custom Constraints" section of the System Prompt.
*   **Result:** A standard Crypto prompt + your specific constraints.

---

## 7. Scope Boundary

**Long-form fiction is out of scope.** A short story, a novel chapter, a screenplay: this skill
edits the surface of a text — vocabulary, syntax, punctuation, rhythm — and in fiction that
surface carries a small share of what marks a text as machine-written.

This is measured rather than assumed. A study that looked only at story-level features — how the
plot holds together, how feelings are conveyed, how time is handled — could tell human fiction
from machine fiction correctly in about 93 cases out of 100. Rewriting the wording, which is what
this skill does, barely moved that number (StoryScope, arXiv:2604.03136).

The nearest thing in scope is `--genre blog`, for essayistic and personal writing.

## 8. Invoking the Skill

**Name the skill when you want it.** Asking in the ordinary way — *"make this sound like a person
wrote it"* — reaches this skill roughly one time in ten. Saying *"use the text-humanizer skill"*,
or typing `/text-humanizer`, reaches it every time.

| How you ask | It runs |
| :--- | ---: |
| `/text-humanizer <text>` or "use the text-humanizer skill" | reliably |
| "use whichever of your skills fits, then clean this up" | reliably |
| "make this sound like a person wrote it" | about 1 in 10 |
| "tidy up the wording here" | rarely |

**Why.** When the model can handle a request on its own, it usually just does — it rewrites your
text directly instead of checking whether a skill exists. What you get back is an ordinary
rewrite. None of this skill's machinery runs: the genre is not resolved, the intensity level of
[§4](#4-intensity-levels) is not applied, the exceptions that protect your domain terms are not
consulted, and the checking passes after the rewrite do not happen. Often that is fine. It is just
not this skill.

**When it matters most.** Technical, legal and contractual text. That is exactly where `low` and
`minimal` intensity exist, and where a wrongly "improved" word can change what the document
commits to. Name the skill there.

This is measured, not guessed, and rewording the description does not fix it: five variants were
tried, including one written specifically to match how people phrase these requests. Method and
data: `skills/text-humanizer/evals/trigger/probe/`.

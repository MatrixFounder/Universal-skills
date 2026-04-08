# Rewriting Strategy: Statistical Deviation & Contrastive Subtraction

This document defines the **active replacement strategy** for humanizing text. The pattern files tell you what to avoid. This file tells you what to do instead.

## The Core Principle: Statistical Deviation

LLMs choose the statistically most probable continuation at every token. The result gravitates toward the most typical phrasing applicable to the broadest set of contexts.

Humanization = intentional deviation from the statistical norm. Every word choice, every turn of phrase, every rhythmic break is a choice of the LESS probable but MORE characteristic option.

*   AI writes: "This has significant implications."
*   Human A writes: "This changes everything."
*   Human B writes: "So what?"

Both human versions are less statistically probable, but each carries a distinct voice. The AI version could appear in any document about any topic. The human versions belong to a specific author with a specific stance.

**Hold this principle in mind for every decision: "The AI would choose the most typical option. What would THIS specific author choose?"**

## The Technique: Contrastive Subtraction (CoPA)

> Research (CoPA, EMNLP 2025) found that the most effective way to humanize text is not to remove markers from a checklist, but to find the MOST PREDICTABLE word in each sentence and replace it with a less probable but contextually appropriate alternative.

**Predictable does not mean formal.** "Solution" in the context of "found a solution to the problem" is predictable. "Workaround," "hack," "lifeline" are less probable but more characteristic. One such choice per sentence produces more impact than three stylistic edits.

### How to Apply

1. **First**, remove all patterns flagged as Priority A (Hard Bans) from the anti-pattern list. These are non-negotiable.
2. **Then**, pass through the text sentence by sentence. In each sentence, identify the single most predictable content word (noun, verb, or adjective -- skip function words like "the," "is," "and").
3. **Replace** that word with a less expected but fitting alternative. Consider: What would THIS author say here? What word carries voice, opinion, or specificity?
4. **Do not over-apply.** Not every sentence needs a replacement. If a sentence already contains a distinctive word or phrase, skip it. Aim for roughly 60-70% of sentences, not 100%.

### Examples

| Original (predictable) | Replacement (characteristic) | Why it works |
| :--- | :--- | :--- |
| "The team **achieved** remarkable results." | "The team **pulled off** something nobody expected." | "Achieved" is generic; "pulled off" implies difficulty and surprise. |
| "This **represents** a major shift." | "This **upends** what we assumed." | "Represents" is filler; "upends" has direction and force. |
| "Users **reported** positive feedback." | "Users **kept coming back**, which said more than any survey." | "Reported" is passive; showing behavior is more vivid than citing reports. |
| "The **implementation** was complex." | "Getting this to work was a nightmare." | Nominalization replaced with a verb phrase + honest emotion. |

## Interaction with Pattern Files

This strategy is a **complement** to the pattern blacklists, not a replacement:

1. **Priority A patterns** (Hard Bans): Remove unconditionally. No contrastive subtraction needed -- just delete.
2. **Priority B-C patterns**: Remove the pattern, then apply contrastive subtraction to the replacement sentence.
3. **Clean sentences** (no patterns detected): Apply contrastive subtraction only if the sentence feels generic or interchangeable. If it already has voice, leave it alone.


# Rewriting Strategy: Statistical Deviation & Contrastive Subtraction

> **Evidence class: inference.** See *Where this comes from* below. The technique is an
> editorial heuristic; the two studies cited support its direction, not the rule itself.

This document defines the **active replacement strategy** for humanizing text. The pattern files tell you what to avoid. This file tells you what to do instead.

## The Core Principle: Statistical Deviation

LLMs choose the statistically most probable continuation at every token. The result gravitates toward the most typical phrasing applicable to the broadest set of contexts.

Humanization = intentional deviation from the statistical norm. Every word choice, every turn of phrase, every rhythmic break is a choice of the LESS probable but MORE characteristic option.

*   AI writes: "This has significant implications."
*   Human A writes: "This changes everything."
*   Human B writes: "So what?"

Both human versions are less statistically probable, but each carries a distinct voice. The AI version could appear in any document about any topic. The human versions belong to a specific author with a specific stance.

**Hold this principle in mind for every decision: "The AI would choose the most typical option. What would THIS specific author choose?"**

## The Technique: Contrastive Subtraction

**Where this comes from, stated exactly.** The technique below is an editorial heuristic. It is
*inspired by* CoPA (Contrastive Paraphrase Attack, EMNLP 2025), and CoPA does something else:
it builds an auxiliary machine-like token distribution and subtracts it from a human-like one
**during decoding**. That is a generation-time method needing access to logits. It performs no
per-sentence word replacement, it does not compare itself against checklist-based marker
removal, and its goal is evading a detector rather than improving prose. Earlier revisions of
this file attributed the rule below to it. They were wrong.

What supports the heuristic in prompt space is separate, and narrower:

*   professional editors' operations on 1,057 LLM paragraphs skew heavily to **replacement** --
    74% replace, 18% delete, 8% insert (LAMP, CHI 2025);
*   instruction-tuned model prose is lexically narrow, over-using a small set of words at many
    times the human rate (Reinhart et al., PNAS 2025).

Neither study tested this rule. Treat the gain as unmeasured.

> Find the MOST PREDICTABLE word in each sentence and replace it with a less probable but
> contextually appropriate alternative.

**Predictable does not mean formal.** "Solution" in the context of "found a solution to the problem" is predictable. "Workaround," "hack," "lifeline" are less probable but more characteristic. One such choice per sentence produces more impact than three stylistic edits.

### How to Apply

1. **First**, remove all patterns flagged as Priority A (Hard Bans) from the anti-pattern list. These are non-negotiable.
2. **Then**, pass through the text sentence by sentence. In each sentence, identify the single most predictable content word (noun, verb, or adjective -- skip function words like "the," "is," "and").
3. **Replace** that word with a less expected but fitting alternative. Consider: What would THIS author say here? What word carries voice, opinion, or specificity?
4. **Do not over-apply.** Not every sentence needs a replacement. If a sentence already contains a distinctive word or phrase, skip it. Aim for roughly 60-70% of sentences, not 100%.

### Which Operation to Reach For

Prefer **replacing** a word and **deleting** a phrase over **inserting** a new one. Where two
edits would both fix a sentence, take the one that does not make the text longer. The single
exception is **adding specificity** -- a name, a number, an object, an action somebody took;
that edit is allowed to grow the text. Anything else that grows it is injected personality the
source did not have, and injected personality is the editor's fingerprint, not the author's.

This is a skew, not a ban. Where the diagnosis is **Red** -- three or more markers, the paragraph
rewritten whole -- the additive genre rules apply normally, because little of the original
survives to be preserved. Under **Yellow**, spot-fix the marker and leave the length alone.

*Basis:* the LAMP figures cited above -- 74% replace, 18% delete, 8% insert -- describe
professional editors, not an instructed model. Direction, not a target ratio.

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


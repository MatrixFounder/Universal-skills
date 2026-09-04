# Universal AI Writing Patterns ("The Deadly Sins")

> **Evidence class: heuristic**, except where an entry cites its own measurement. The list
> derives from *Wikipedia: Signs of AI writing* and from editorial practice. No entry was
> validated against a corpus of this project's own texts.

These patterns betray AI generation in ANY genre. They must be removed or rewritten regardless of whether the text is a tweet or an encyclopedia entry.

Each pattern is tagged with a priority level:
*   **[A] Critical** -- Fix ALWAYS, in any mode, any text type.
*   **[B] High** -- Fix in all modes except legal/regulatory text.
*   **[C] Medium** -- Fix in full editing and expert content.
*   **[D] Stylistic** -- Fix by context; not always necessary.

### What is NOT a finding

Read this before the patterns. A hit satisfying one of the three tests below is not a finding,
and removing it is a defect of the edit rather than of the text. This section is not filtered by
intensity: it applies at `max` and at `minimal` alike.

1.  **The author's own habit, on evidence.** A word or a punctuation habit that appears in the
    writing samples the user supplied and is recorded in the voice passport. An impression about
    the author's style with no sample behind it is not evidence; the passport is.
2.  **A domain term, on evidence.** The word names a thing in this text's field and you can point
    at where: the project's own documentation, a public API, a cited standard, or an identifier in
    the text itself. `robust_mode`, `dynamic backoff`, `align to a 64-byte boundary`,
    `dynamic linking`, `leveraged buyout`. The [A] vocabulary list holds words, not meanings, and
    it is the only class that fires at `low` and `minimal` intensity -- where a changed word
    changes what the document promises.
3.  **Quoted material.** Anything inside a direct quotation, a code span, a fenced block or an
    in-world document keeps its wording.

Each test names something you can point at -- a sample, a document, an API, an identifier.
"It reads like a term to me" is not one of them.

---

## 1. The "AI Vocabulary" `[A]`
Words that have statistically exploded in usage since 2023.
*   **Verbs:** delve, underscore, highlight, bridge, foster, navigate, leverage, align.
*   **Nouns:** tapestry, landscape (abstract), realm, testament, interplay, nuance, intricacies.
*   **Adjectives:** vibrant, crucial, pivotal, intricate, seamless, robust, dynamic.
*   **Adverbs:** undoubtedly, arguably, meticulous.

## 2. The "False Range" `[B]`
Using "from X to Y" where X and Y are not on a meaningful linear scale.
*   *AI:* "From the bustling streets of Tokyo to the quiet introspection of a tea ceremony..."
*   *Fix:* Just list them or find a real connection.

## 3. Negative Parallelism / "Not just X, but Y" `[A]`
Overused sentence structure trying to sound profound. Present in 80%+ of AI-generated text.
*   *AI:* "It's not just a phone; it's a gateway to the world." / "The goal is not merely to win, but to dominate."
*   *Fix:* Be direct. "It's a powerful phone." State what you mean without the contrast crutch.

## 4. The "Rule of Three" Addiction `[D]`
Forcing ideas into triads.
*   *AI:* "Create a seamless, intuitive, and robust experience."
*   *Fix:* Cut to the one word that actually matters.

## 5. Elegant Variation (Synonym Cycling) `[D]`
Refusing to reuse a noun, leading to weird synonyms.
*   *AI:* "The dog barked. The canine ran. The four-legged companion slept."
*   *Fix:* Use pronouns ("he/it") or just repeat the word if it's the subject.

## 6. Meaningless Transitions `[B]`
Filler words at the start of sentences.
*   *AI:* "Moreover, Additionally, Furthermore, In conclusion, To summarize..."
*   *Fix:* Delete them. The sentences usually flow better without them.

## 7. The "Colon Disease" `[D]`
Excessive use of "Title: Description" lists.
*   *AI:* "**Efficiency:** The system is fast."
*   *Fix:* Write normal paragraphs or integrated lists.

## 8. The "-ing" Footer (Superficial Analysis) `[B]`
Tacking on a present participle phrase to the end of a sentence to fake depth.
*   *AI:* "The dam was built in 1950, **underscoring** the region's commitment to modernization." / "..., **reflecting** the cultural shift."
*   *Fix:* Cut it. "The dam was built in 1950." (The reader can figure out the implication).

## 9. Em Dash Abuse `[A]`
The finding is **density**, not the character. One em dash is punctuation and is not reported. A
text reaching for them in place of commas -- several to a paragraph, two inside one sentence -- is.
*   *AI:* "The solution is simple — efficient — and robust."
*   *Fix:* Use commas, colons, periods, or restructure. "The solution is simple, efficient, and robust."
*   *Not a finding:* a single em dash; a dash habit recorded in the voice passport; a dash inside
    quoted material.
*   **On the old justification.** Earlier revisions of this file justified the rule by what AI
    detectors count. That reason does not hold: em-dash density in current model output is falling,
    not rising, so a rule resting on it expires with the next release. The rule stays because
    dashes used for punch read as sales copy, which is a fact about the prose.

## 10. Chatbotisms (The "Helpful Assistant") `[A]`
Leftover conversational artifacts.
*   *AI:* "I hope this helps!" / "Here is a breakdown:" / "Certainly!" / "In summary,"
*   *Fix:* Delete. The content should stand alone.

## 11. Authoritative Truisms `[B]`
Phrases that create an illusion of depth without adding content. They sound wise but say nothing.
*   *AI:* "At its core..." / "In the end, what really matters is..." / "The reality is..." / "Fundamentally..." / "When all is said and done..."
*   *Fix:* Delete the preamble. If the statement is true without the lead-in, the lead-in is dead weight.

## 12. Responsibility Disclaimers `[B]`
Vague hedging that sounds cautious but communicates nothing specific.
*   *AI:* "While information may be incomplete..." / "Despite the limitations of this analysis..." / "It's difficult to say with certainty, but..."
*   *Fix:* If you lack data, say specifically WHAT you lack. "We don't have Q4 numbers yet" beats "While data may be incomplete." If you're confident, just assert.

## 13. Uniform Information Density `[B]`
AI distributes facts evenly: every sentence carries roughly the same "weight." Human writing alternates: a sentence packed with three facts, then a light connecting phrase, then a personal aside, then another dense hit.
*   *AI:* "AI increases productivity by 40%. It also reduces errors by 25%. Additionally, it accelerates time-to-market by 30%."
*   *Fix:* "Productivity jumped 40%, errors dropped by a quarter. That's the pitch deck version. In practice, half the team still double-checks everything by hand. But the ones who trust the model ship 30% faster."
*   **Test:** If every sentence in a paragraph feels equally "informative," the paragraph reads as synthetic. Create a "cardiogram": dense, light, dense, question, dense.

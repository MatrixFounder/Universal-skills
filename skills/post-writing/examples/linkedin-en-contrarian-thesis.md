# Worked Example — EN / LinkedIn / Contrarian Thesis

End-to-end trace of the four-step pipeline in `SKILL.md`
(Analyze & Clarify → Select a Hook → Draft → Review).

> **Fixture notice.** The person, the team, and every number below are invented
> for this example. Nothing here is a real company, a real individual, or a real
> metric. In a real run all figures arrive from the user (see **Safety
> Boundaries → No invented facts**).

---

## Step 0 — Raw user brief

> "Write me a LinkedIn post about the onboarding thing we did. Make it engaging."

That is the whole brief. Four of the five Step 1 inputs are missing, and the post
carries claims that need numbers. Drafting starts after the questions, not before.

---

## Step 1 — Analyze & Clarify

Five questions asked, five answers received.

| # | Question | User's answer |
|---|---|---|
| 1 | **Goal** — sales, engagement, education, brand awareness? | Engagement plus authority. Not selling anything. |
| 2 | **Target audience** — which Schwartz awareness level? | Engineering managers. **Problem-Aware**: they already feel onboarding is slow and they blame the documentation. |
| 3 | **Key takeaway** — what MUST the reader think afterwards? | "The bottleneck is not the docs. It is the absence of a first task." |
| 4 | **Platform** | LinkedIn. |
| 5 | **Language** | EN → `references/voice-guide-en.md`. |

Sixth question, forced by **Safety Boundaries → No invented facts** — the hook
formulas need real figures and the brief supplied none:

> "Give me the actual numbers: how many people, over what period, and what moved?"

User's answers, used verbatim from here on:

- 9 new engineers onboarded over 7 months
- old onboarding wiki: 40 pages
- replacement: a 12-item checklist
- time-to-first-merged-PR: day 6 → day 2

Nothing outside this list appears in the post.

---

## Step 2 — Select a Hook

`references/hooks-examples.md` read first. Three distinct options generated and
put to the user.

**Option A — Story Lead**
> "Our fourth new hire read all 40 pages of the onboarding wiki and still asked
> me where the deploy command lived."

**Option B — Problem Lead**
> "New engineers take six days to ship their first line of code. Your
> documentation is not the reason."

**Option C — Contrarian Thesis**
> "We deleted 40 pages of onboarding docs. Time to first merged PR dropped from
> six days to two."

### Why C won

- **B is well matched, but to the wrong prize.** `references/hooks-examples.md`
  lists Problem Lead as best for *known* audience pain and high read-through, and
  this pain is certainly known, so B would hold the readers it gets. The catch is
  the opening move: a Problem-Aware reader already agrees with B's first line, and
  agreement is a weaker open loop than contradiction. The stated goal is reach and
  authority, not read-through.
- **A buries the data.** The Story Lead is warm and it earns trust, but the two
  numbers that make this post credible (40 → 12, 6 → 2) arrive in paragraph
  three. `references/hooks-examples.md` → Data + Narrative + Framework wants
  specific numbers **in the first lines**.
- **C creates the dissonance.** Deleting documentation and getting faster
  onboarding contradicts the reader's model. Per `references/hooks-examples.md`,
  Contrarian Thesis outperforms on LinkedIn precisely because the reader cannot
  stop at the second line.
- **Format table agrees.** `references/platform-rules.md` → "Want reach & likes
  → research + contrarian take". The stated goal is engagement plus authority.

A is not discarded — it becomes the Narrative layer inside the body, so the post
keeps all three layers (Data, Narrative, Framework).

**User picked C.**

---

## Step 3 — Draft

Read before writing: `references/voice-guide-en.md`,
`references/platform-rules.md`. Structure: Problem → Reframe → Action.

### Draft v1

```text
We deleted 40 pages of onboarding docs. Time to first merged PR dropped from six
days to two.

Here is what happened. Over the last 7 months we onboarded 9 engineers — and
every single one of them followed the same pattern — they read the wiki front to
back, felt prepared, then sat frozen on day one with no idea what to actually
touch.

The wiki was not wrong. It was complete. That was the problem: it described the
whole system, and a new hire does not need the whole system on Monday morning.
They need one small thing that is safe to break.

So we threw it out and wrote a checklist instead:

- Ship a one-line copy change to production before lunch on day 1
- Pair on a real bug on day 2
- Write the runbook entry for the thing you just fixed

12 items. That is the entire onboarding programme now. First merged PR moved
from day 6 to day 2.

The lesson: documentation answers questions. Onboarding needs a task.
```

---

## Step 4 — Review

`references/review-checklist.md` applied item by item.

### Core

| Item | Verdict |
|---|---|
| Hook — contradiction/intrigue in the first line | PASS |
| Structure — Problem → Reframe → Action | PASS |
| Accessible to non-technical readers | PASS |
| Personal — from experience, not theory | PASS |
| No fluff | PASS |
| Dialogue — ends with a question or call-to-reaction | **FAIL** — it ends on a maxim |
| Simple — no parcellation, no em-dashes, short paragraphs | **FAIL** — two em-dashes, one 4-line paragraph |

### Advanced

| Item | Verdict |
|---|---|
| Data + Narrative + Framework | PASS |
| Specific numbers in first lines | PASS — 40, 6, 2 |
| Authority embedded, not claimed | PASS |
| Ending provokes discussion | **FAIL** — same defect as "Dialogue" |
| Platform formatting correct | **FAIL** — markdown `-` bullets do not render on LinkedIn |

### Revisions made

1. **Em-dashes and the long paragraph.** The governing rule is
   `references/review-checklist.md` → "Simple — no parcellation, no em-dashes,
   short paragraphs". The EN voice guide carries no dash rule, so the checklist
   is the sole authority here. The 4-line sentence was split into two paragraphs
   of two lines, and both em-dashes became full stops.
2. **Bullets → arrows.** `references/platform-rules.md`: LinkedIn does not
   render markdown bullets. Every `-` became `→`.
3. **The ending.** "The lesson: documentation answers questions. Onboarding needs
   a task." is a closing maxim, which the checklist counts as a dead end.
   `references/platform-rules.md` ranks the moral dilemma as the strongest
   ending, so the maxim was demoted into the body and the post now closes on an
   open question the reader has a stake in.

### Final post

```text
We deleted 40 pages of onboarding docs. Time to first merged PR dropped from six
days to two.

Over the last 7 months we onboarded 9 engineers. Every one of them did the same
thing: read the wiki front to back, felt prepared, then sat frozen on day one.

The wiki was not wrong. It was complete.

That was the problem. It described the whole system, and a new hire does not
need the whole system on Monday morning. They need one small thing that is safe
to break.

So we replaced it with a checklist:

→ Ship a one-line copy change to production before lunch on day 1
→ Pair on a real bug on day 2
→ Write the runbook entry for the thing you just fixed

12 items. That is the entire onboarding programme now.

Documentation answers questions. Onboarding needs a task.

Which makes me wonder: if a new hire is productive in two days without reading
the wiki, who was the wiki ever written for?
```

---

## Output

- **File name**: `2026-03-18 We deleted 40 pages of onboarding docs.md`
- **Saved to**: `01_Projects/HowToAI - blog buildinpublic/Draft Posts/EN/`
- **Not published.** Moving it to `Published Posts/EN/` waits for an explicit
  instruction from the user (**Safety Boundaries → No publishing**).

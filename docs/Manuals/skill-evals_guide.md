# Educational guide: Skill evals

🇬🇧 English · [🇷🇺 Русская версия](skill-evals_guide.ru.md)

> **Who this guide is for.** For engineers who are just getting acquainted with how
> **enterprise-grade skills** are built (reliable, verifiable, production-ready).
> No prior knowledge of the jargon is assumed — every term is explained
> in plain language as we go, and all of them are collected in the [glossary](#appendix-a).
>
> **The main goal of this document is understanding.** Not "memorize the procedure," but understand *why*
> evals are needed and *by what principles* they are built. In two weeks you will forget
> the details of specific examples — but the principles should stay with you.

> **How to read this guide.**
> - **Bold text** and the "✅ Key takeaways" blocks highlight the **principles** — that is the very
>   reason this document was written.
> - The grey "📦 Case study — wiki-verify" blocks are *illustrations* on a real
>   skill. If you forget what `wiki-verify` is, that is fine — the principle
>   stays clear without it.

> **Sources (everything verified against real code at the time of writing):**
> 1. **`skill-creator`** — the built-in eval engine in this repository
>    (`.claude/skills/skill-creator/`).
> 2. **`wiki-verify`** — an exemplary eval harness from a neighboring project.
>    Sources: <https://github.com/MatrixFounder/llm-wiki/tree/main/skills/wiki-verify>
>    The numbers in the guide were checked against a working copy of the repository; the `main` branch on GitHub may
>    lag slightly behind — when they disagree, the truth is in the code, not in the guide.

---

## Contents

0. [TL;DR — in 60 seconds](#0-tldr)
1. [Seven core concepts in plain language](#1-core-concepts)
2. [Why evals are needed at all](#2-why)
3. [Two different kinds of evals](#3-two-kinds)
4. [What an eval is made of: data, schemas, grading](#4-anatomy)
5. [How evals work: cycles with diagrams](#5-how-they-work)
6. [How to build quality evals](#6-how-to-build)
7. [Advanced principles of a mature eval harness](#7-advanced)
8. [When evals go stale](#8-aging)
9. [What evals influence](#9-impact)
10. [Effort and tokens — with concrete numbers](#10-cost)
11. [Checklists and antipatterns](#11-checklists)
- [Appendix A. Glossary](#appendix-a)
- [Appendix B. File map](#appendix-b)

---

<a name="0-tldr"></a>
## 0. TL;DR — in 60 seconds

**A skill is an instruction for an AI agent**, written as text. The trouble is that text
which seems unambiguous to its author is not always followed by the agent. **An eval is
an automated test that objectively checks: does the skill do what it promises?**

There are **two independent checks**, and they must not be mixed:

| Check | Answers the question | In plain words |
|----------|--------------------|------------------|
| **Trigger** | Did the agent even *figure out* it should apply the skill? | "Did the skill fire when it was needed?" |
| **Behavior** | If it applied — did it do the job *correctly*? | "And did it actually do the work properly?" |

The main practical conclusion, repeated throughout the guide:

> **A small or uniform test set gives false confidence.**
> On a toy set the skill showed a "70% improvement." On a diverse set the same skill
> gave a far more modest result — *and on top of that exposed two real breakages that the small set never
> saw*; the honest bottom line after fixing them is around 58%, not the loud 70%. We
> later call this effect a "mirage" (in detail — in §7.3).

```mermaid
flowchart LR
    A["Skill draft"] --> B["Write test cases"]
    B --> C["Run the evals:<br/>with skill + without skill"]
    C --> D["Check the result<br/>= grading"]
    D --> E["Show it to a human"]
    E --> F{"Good?"}
    F -- No --> G["Improve the skill"]
    G --> C
    F -- Yes --> H["Pin it as the baseline<br/>+ save the reports"]
    H -.->|"if behavior changed"| B
    classDef loop fill:#eef,stroke:#88a;
    class C,D,E,G loop;
```

> This is the "core loop" from `skill-creator`: *draft -> tests -> run
> (with skill + without) -> review -> improve -> repeat*.

---

<a name="1-core-concepts"></a>
## 1. Seven core concepts in plain language

Before we go deeper — here is a "starter vocabulary." Seven words you cannot do without
going forward. (The full glossary is in [Appendix A](#appendix-a).)

| Term | In plain words | Analogy |
|--------|------------------|----------|
| **Skill** | An instruction file for an AI agent: "when you see this kind of task — do it this way." The file has a short **header** (metadata) and a **body** with instructions. | A job description for an employee. |
| **Eval** (from *evaluation*) | An automated test that checks the skill on real tasks. | An exam for the employee. |
| **Baseline** | A run **without** the skill (or with the old version) — so there is something to compare against. | The control group in an experiment. |
| **Grader** | The one who looks at the result and pronounces "pass / fail." See below in detail. | The examiner grading the test. |
| **Trigger** | The moment when the agent decides to apply the skill (based on the description in the header). | An alarm clock: it either fired or you slept through it. |
| **Assertion** | A concrete, checkable condition: "the output must contain X." | A line item on an acceptance checklist. |
| **Subagent** | A separate instance of an AI agent launched for one subtask… | …a contractor hired for a single run. |
| **Orchestrator** | …and this is the "main" agent that hands out tasks to subagents and collects results. | A foreman handing out work orders. |

<a name="11-what-is-a-grader"></a>
### 1.1. What a grader is and why it is needed

This word appears dozens of times in the guide, so let us explain it separately and in human terms.

Picture a school exam. The student wrote an answer. They do **not** grade themselves —
you need an **examiner** who compares the work against a reference and, for each item, says
"correct / incorrect," and explains why on top of that.

**A grader is exactly that examiner, but for an eval.** It receives two things as input:
1. **what the agent did** — its actions (the transcript) and the output files;
2. **what it was supposed to do** — the list of assertions.

And for each assertion it issues a `pass`/`fail` **with evidence**
(a quote from the result). A grader is needed because:
- the result does not grade itself — someone has to deliver an objective verdict;
- the check must be **by a single standard** across all runs, not "by eye";
- a good grader also **critiques the tests themselves** — it spots a weak assertion that
  would also pass for a wrong answer (more on this in [§6.3](#63-strong-vs-rotten-assertions)).

There are two kinds of graders:

```mermaid
flowchart LR
    G["Grader<br/>(the examiner)"] --> A["LLM judge<br/>another model reads<br/>and pronounces a verdict"]
    G --> B["Script grader<br/>plain code checks<br/>structured output"]
    A -.->|"flexible: good for text,<br/>prose, subjective judgments"| A2[ ]
    B -.->|"strict and reproducible:<br/>good for JSON/numbers/files"| B2[ ]
    style A2 fill:none,stroke:none
    style B2 fill:none,stroke:none
```

Which one to choose is **dictated by the skill's output format**: text for a human -> LLM judge;
a machine-readable result (JSON, numbers, file structure) -> script. More on this in
[§4.4](#44-two-grading-styles).

### 1.2. What wiki-verify is (our running example)

> **📦 Case study — wiki-verify**
>
> `wiki-verify` is a "truth-checker" skill from another project. Its job:
> take an answer that someone wrote *with citations to sources*, and check —
> **does the answer actually say what is in the sources?**
>
> Internally it launches **four independent "nitpickers" (critics)**:
> 1. **facts** — are there any fabricated claims that are not in the sources;
> 2. **logic** — are there any logical gaps and contradictions;
> 3. **security** — was a harmful instruction (injection) slipped into the text;
> 4. **completeness** — was anything important from the source omitted.
>
> The output is a "pass / fail" verdict.
>
> **Why we refer to it:** `wiki-verify` has *exemplary* evals — it is a convenient case
> for showing mature engineering practices. **But all the principles in the guide are general;**
> `wiki-verify` is merely an illustration. Sources:
> <https://github.com/MatrixFounder/llm-wiki/tree/main/skills/wiki-verify>

> **✅ Key takeaways from §1.** A skill is an instruction for an AI. An eval is a test for that
> instruction. A grader is the examiner who turns a result into an honest
> "pass/fail." Everything else is detail layered on top of these three concepts.

---

<a name="2-why"></a>
## 2. Why evals are needed at all

### 2.1. The problem: skills break silently

An agent (LLM) is an unreliable executor of instructions. Even with a well-written skill it
can **still** fail in four ways:

```mermaid
flowchart TD
    T["Skill is written"] --> F1["1. Did not read the skill<br/>(trigger did not fire)"]
    T --> F2["2. Read it, but bypassed the rule<br/>('just this once is fine')"]
    T --> F3["3. Followed it literally, not in spirit<br/>(box ticked, no benefit)"]
    T --> F4["4. Works today,<br/>breaks tomorrow from a nearby edit"]
    F1 --> S["All four failures are SILENT:<br/>nobody notices until it is too late"]
    F2 --> S
    F3 --> S
    F4 --> S
    classDef bad fill:#fdd,stroke:#c66;
    class F1,F2,F3,F4,S bad;
```

Without evals you learn about a failure only in production. That is why `skill-creator` has a
hard rule: **"untested skills fail silently in production"** — skipping the eval
stage is not allowed.

### 2.2. An eval is TDD-style testing, just for text

In ordinary development there is a proven approach, **TDD** (Test-Driven Development):
first you write a test, watch it *fail* (the **RED** phase),
then you write code to make the test *pass* (the **GREEN** phase), and then you
*tidy up without breaking the test* (the **REFACTOR** phase). Skills are tested the very same way.
Only for a skill, "tidy up" does not mean rewriting code, but **closing the
new loopholes the agent invented to bypass the rule** — without breaking what already
works:

```mermaid
flowchart TD
    R["RED<br/>Run the task WITHOUT the skill.<br/>Watch how the agent fails."] --> VR["Record the FAILURES verbatim:<br/>exactly what the agent did wrong<br/>and the words it used to justify it"]
    VR --> G["GREEN<br/>Write a skill that closes<br/>EXACTLY those failures"]
    G --> VG["Check WITH the skill:<br/>does the agent now do it right?"]
    VG --> RF["REFACTOR<br/>Close the new loopholes<br/>the agent invented"]
    RF --> SG["Recheck: still correct?"]
    SG -->|a new loophole found| RF
    classDef red fill:#fdd,stroke:#c66;
    classDef green fill:#dfd,stroke:#6c6;
    class R,VR red;
    class G,VG,RF,SG green;
```

The key idea: **until you have seen how the agent fails WITHOUT the skill, you do not know
whether the skill prevents the right failures.** A run without the skill (the baseline) is your
"red test," the point of reference.

### 2.3. What evals do NOT do

So that expectations do not get inflated:
- They **do not prove** absolute correctness — they *reduce the probability* of a silent
  failure and *catch regressions* (breakages from future edits).
- They **do not replace** a human — they *prepare the data* so the human can review quickly.
- They are **pointless** for pure reference material (API documentation, syntax) — there are no
  rules there that could be broken.

> **✅ Key takeaways from §2.** An eval is needed because a skill breaks *silently*. The approach is
> the same as in TDD: first see the failure without the skill, then prove that the skill fixes it.
> An eval does not guarantee perfection — it catches silent failures and regressions.

---

<a name="3-two-kinds"></a>
## 3. Two different kinds of evals

This is the place where people most often get confused. A skill goes through **two different checks** — they have
different engines, different data, and a different meaning. The diagram below reads as **two independent
columns** (each top to bottom); we will break down each one right after it.

```mermaid
flowchart TB
    subgraph T["①  TRIGGER — 'did the skill fire at all?'"]
        direction TB
        t1["Question: did the agent figure out it should apply the skill?"]
        t2["Data: ~20 queries labeled<br/>'should fire' / 'should not'"]
        t3["Grade: automatic —<br/>fired on >= half the runs?"]
        t1-->t2-->t3
    end
    subgraph B["②  BEHAVIOR — 'did the skill fire correctly?'"]
        direction TB
        b1["Question: did the skill do the job properly?"]
        b2["Data: realistic tasks +<br/>a list of assertions"]
        b3["Grade: LLM judge OR script"]
        b1-->b2-->b3
    end
    T -.->|"the trigger is optimized AFTER<br/>behavior is already good"| B
```

### 3.1. Trigger: "was the skill found?"

As we said in §1, a skill is a file with a **header** and a body. The header has a field
`description` — a short phrase like "apply this when you need to do such-and-such."
This is the **only signal** by which the agent decides whether to open the skill. If the
description "falls short" — the skill simply will not fire, and everything else is irrelevant (even if it is
three times perfect inside).

How this is checked automatically:
1. Take ~20 real queries and label each one: "the skill *should* fire here" or
   "it *should not* here."
2. Run each query through the agent several times (by default **3**) and see
   whether it invoked the skill.
3. Compute the **trigger rate**. If a query is "should" — pass when the rate is >= 50%; if
   "should not" — pass when the rate is < 50%.

In essence this is a **classifier** — a program that sorts queries into two
buckets: "call the skill" / "do not call." Its quality is measured by three metrics (in detail — in the
glossary): **precision** = few false alarms; **recall** =
few misses; **accuracy** = the fraction of correct decisions overall. If these
words are unfamiliar — that is normal, they are explained in [Appendix A.3](#a3-metrics).

### 3.2. Behavior: "did it fire correctly?"

Here the skill actually performs the task. Two versions are run **in a single pass**:
- **with the skill** (`with_skill`);
- **without the skill** (`baseline`) — for a new skill; or **with the old version**
  (`old_skill`) — when improving an existing one.

The results are compared: how much *better* is it with the skill than without. This answers
the main question — **does the skill provide any benefit at all?**

> **✅ Key takeaways from §3.** First the skill must *fire* (trigger), then —
> *fire correctly* (behavior). These are two independent checks. Behavior is always
> compared against a baseline — otherwise there is nothing to measure "improvement" against.

---

<a name="4-anatomy"></a>
## 4. What an eval is made of: data, schemas, grading

### 4.1. `evals.json` — the list of test cases

This is the file with the tests. A minimal case:

```json
{"skill_name": "my-skill", "evals": [
  {"id": 1,
   "prompt": "A realistic user query",
   "expected_output": "In words: what counts as success",
   "files": ["evals/files/sample1.pdf"],
   "expectations": ["The output contains X", "The skill used script Y"]}
]}
```

- `prompt` — what a user would *actually* say (not a "textbook" phrasing).
- `expectations` — these are **the same assertions** from §1 (the JSON field is literally named that): **objectively
  checkable** statements. This is the heart of the test.
- `files` — input fixture files (see glossary: "fixture").

> **A practical trick:** first write *only the prompts*, and add the assertions
> **while the runs are already going.** Runs take a long time — there is no point waiting on them idle.

### 4.2. `grading.json` — what the grader returned

```json
{"expectations": [{"text": "...", "passed": true, "evidence": "..."}],
 "summary": {"passed": 2, "failed": 1, "total": 3, "pass_rate": 0.67},
 "claims": [{"claim": "The form has 12 fields", "type": "factual", "verified": true}],
 "eval_feedback": {"suggestions": [...], "overall": "..."}}
```

Two fields distinguish mature grading from naive grading:
- `claims` — the grader **fishes out** hidden statements from the output on its own and checks them
  (not only the ones you listed in advance).
- `eval_feedback` — the grader **critiques your own tests**: which assertion is weak, what is not
  covered. "A pass on a weak assertion is worse than useless — it gives false
  confidence."

### 4.3. `benchmark.json` — a summary for comparing versions

A separate script gathers all the `grading.json` files and computes, for each version, the mean,
the spread (stddev — standard deviation, a measure of "jitter" around the mean), the minimum, and the
maximum for pass rate, time, and tokens, plus the **delta** (the difference) between "with the
skill" and "without." This is what a human sees in a visual viewer (a browser report).

<a name="44-two-grading-styles"></a>
### 4.4. Two grading styles

As already stated in [§1.1](#11-what-is-a-grader), the grading style
is chosen by the output format:

| | **LLM judge** | **Script grader** |
|---|---|---|
| Who checks | another model | plain code (Python) |
| Suitable for | text, prose, subjective judgments | JSON, numbers, file structure |
| Pros | flexibility, understands meaning | strictness, **full reproducibility**, zero tokens |
| Cons | itself non-deterministic (noisy) | requires the output to be structured |

### 4.5. How a script grader works inside

Above (§4.2) we saw only the **result** of a script grader — the `grading.json` file.
Now let us look at **how** it produces that result. This matters: it is precisely the internal
design that explains why such a grader can be trusted.

**The principle.** A script grader is a **pure deterministic function**: the same
inputs always produce the same output. No calls to an LLM, the network, a database, or a
shell — only comparing "what the skill produced" with "what we expected." It has **three inputs** and
one output:

```mermaid
flowchart TD
    E["① What we EXPECTED — from evals.json:<br/>expected findings + severity,<br/>forbidden findings,<br/>expected verdict (pass / fail)"]
    R["② What the skill PRODUCED — the raw result:<br/>structured JSON with a list of findings"]
    GATE["③ The production gate (verdict function):<br/>IMPORTED from production, not copied"]

    subgraph CASE["SCORING ONE CASE — a pure function: no LLM, network, DB, shell"]
        direction TB
        P1["1. Match findings against expectations<br/>by text-fragment overlap (span).<br/>Text is normalized; a near-match does NOT count"]
        P2["2. Recall: were all expected<br/>defects caught, and at the right severity?"]
        P3["3. Severity-match: did the severity band match?<br/>No high - critical drift"]
        P4["4. Lens-purity: is one defect flagged by ONE critic,<br/>not by several? Except the agreed exception"]
        P5["5. Verdict parity: CALL the production gate.<br/>Did its pass/fail match the expectation?"]
        P6["6. False positives: did the skill fire<br/>on a FORBIDDEN finding (a false alarm)?"]
        P1 --> P2 --> P3 --> P4 --> P5 --> P6
    end

    AGG["AGGREGATION across all cases:<br/>compute rates and counters"]
    OUT["grading.json — that very RESULT from §4.2:<br/>recall_rate, severity_match_rate,<br/>verdict_match_rate, false_positive_count"]

    E --> P1
    R --> P1
    GATE -.->|"called at step 5"| P5
    P6 --> AGG
    AGG --> OUT

    classDef key fill:#e8f0ff,stroke:#5577cc;
    classDef io fill:#fff5e6,stroke:#e0a050;
    class GATE,OUT key;
    class E,R io;
```

Let us go through it step by step in plain words (each step answers one yes/no question about the
case):

1. **Matching.** The skill produced findings; we know where each
   expected defect "lives" (its text fragment, the *span*). The grader matches one against the other.
   Subtlety: texts are normalized (lowercase, strip punctuation), and a "near-
   match" is deliberately **not** counted — otherwise the grader would praise the skill for accidental
   word overlap.
2. **Recall.** Were all expected defects actually found — and not "weaker" than
   required? Missed a defect -> recall failed.
3. **Severity-match.** Did the severity match exactly? Calling something "high" instead of "critical" —
   that is drift, and it counts as a mismatch.
4. **Lens-purity.** One defect should be flagged by *one* critic. If
   several piled onto it — that is "bleed" (except for one agreed-upon exception).
5. **Verdict parity.** The key step: the grader **calls the very
   same gate** that production does (see §7.1), and checks whether the "pass/fail" outcome matched
   the expectation. This way the eval physically cannot diverge from the production logic.
6. **False positives.** Did the skill fire where it should not have, —
   on a "forbidden" finding?

Then the results across all cases are **aggregated** into rates and counters — and you get that
very `grading.json` from §4.2. Since the whole chain is deterministic, it can be **pinned** with a
test (§7.2): "on these inputs the grader must produce exactly this report."

> **📦 wiki-verify.** All of this is the real `grade.py` (≈ 217 lines). Its header literally
> states: *"No LLM, no SQL, no network, no eval/exec/shell"*. Step 5 is the line
> `derived_fail = _is_fail(findings, _FAIL_ON)`, where `_is_fail` is **imported** from the production
> module (not rewritten). At the output `grade_run` returns `records` (per case) + `aggregate`
> with those very fields `recall_rate`, `verdict_match_rate`, `false_positive_count`, and so on.

> **✅ Key takeaways from §4.** A test = a prompt + assertions. The grader turns the result into
> `grading.json` with a verdict and evidence. A good grader also critiques your
> tests. The skill's output format determines what you grade with — a judge or code. **A script
> grader is a pure deterministic function (3 inputs -> 6 checks per case ->
> aggregation), and its "verdict" step calls the production gate rather than copying it (§7.1).**

---

<a name="5-how-they-work"></a>
## 5. How evals work: cycles with diagrams

### 5.1. A behavioral eval: one full pass

```mermaid
sequenceDiagram
    autonumber
    participant O as Orchestrator<br/>(main agent)
    participant W as Subagent WITH the skill
    participant Z as Subagent WITHOUT the skill
    participant G as Grader
    participant V as Viewer (browser)
    participant H as Human

    Note over O: Step 1 — launches BOTH versions<br/>in ONE pass (in parallel)
    O->>W: task + path to the skill
    O->>Z: same task, without the skill
    Note over O: Step 2 — while the runs are going,<br/>finishes writing the assertions
    W-->>O: result + metrics
    Z-->>O: result
    Note over O: Step 3 — immediately saves the timing<br/>(tokens, time): there is no second chance!
    Note over O,G: Step 4 — the grader judges AND critiques the tests
    O->>G: results + assertions
    G-->>O: pass/fail verdicts + test critique
    O->>V: opens the visual report
    V->>H: the human looks and leaves feedback
    H-->>O: edits
```

Three subtleties that are easy to miss:
- **Step 1 — both versions in one pass.** Otherwise there is no fair "with/without" comparison.
- **Step 3 — tokens and time are captured only at the moment the subagent finishes.** These numbers
  arrive once and are saved nowhere else — *did not record immediately -> lost forever*.
- **Step 4 — the grader not only judges but also critiques the tests.**

### 5.2. A trigger eval: the description-tuning cycle

This is a separate *automatic* cycle. Its job is to **tune the `description`** so it
fires as accurately as possible.

```mermaid
flowchart TD
    S["~20 queries: 'should' / 'should not' fire"] --> SP
    SP["Split into 2 parts:<br/>train (60%) — for tuning<br/>test (40%) — for an honest check"] --> IT
    IT["Iteration (no more than 5)"] --> RUN
    RUN["Run each query 3 times<br/>through the agent, in parallel"] --> SCORE
    SCORE{"Did all train queries pass?"}
    SCORE -- Yes --> BEST
    SCORE -- "No, attempts remain" --> IMP["The model proposes a new description.<br/>IMPORTANT: it is NOT shown the test results"]
    IMP --> IT
    SCORE -- "No, attempts exhausted" --> BEST
    BEST["Take the best description BY THE TEST part<br/>(not by train!)"]
    classDef hot fill:#ffe9cc,stroke:#e08a00;
    class IMP,BEST hot;
```

Two tricks straight out of machine learning are hidden here, and both are about **honesty**:
1. **Split the tests into train/test.** The description is "fit" only to train, while the *bottom line
   is chosen by test*. This way you cannot accidentally "memorize" specific queries.
2. **Hide the test results from the improving model.** It physically cannot see the held-out
   part, so it cannot tune to it.

> **✅ Key takeaways from §5.** A behavioral eval = run with the skill and without, in one
> pass, save the timing immediately, hand it to the grader, show it to a human. A trigger eval =
> an automatic description-tuning cycle with protection against "memorization" (train/test + hiding
> test from the improver).

---

<a name="6-how-to-build"></a>
## 6. How to build quality evals

This section is about **principles**. The examples (including `wiki-verify`) are given as
illustrations.

### 6.1. Intent first, then tests

Before writing tests, clarify four things: what the skill should be able to do; **when it should fire**
(in what words it will be invoked); what the output format is; whether tests are needed at all (for
objective output — yes; for subjective output, like writing style, — often no).

### 6.2. Realistic queries, not "textbook" ones

> Queries should be like real life: with file paths, personal context, abbreviations,
> typos, conversational speech.

Especially valuable are **near-misses** — queries that share key words
with your skill but should actually go to a *different* skill. They are exactly the ones that catch a
**false positive**. A false positive comes in two kinds, and do not confuse them:
**over-triggering** — the skill *fired* where it should not have (a *trigger* false alarm), and
**over-flagging** — the skill *raised* a complaint/finding where there is none (a *behavior* false alarm).
Here we are talking about the first.

<a name="63-strong-vs-rotten-assertions"></a>
### 6.3. Strong vs rotten assertions

The main trap is an assertion that **would also pass for a wrong output**.

> Example of a rotten assertion: *"The output contains the name 'Ivan Petrov'"*.
> The trouble: a fabricated (hallucinated) document that happens to mention "Ivan Petrov"
> **would also pass this check.** That is, the test is green while the output is garbage.

```mermaid
flowchart LR
    Q["Assertion"] --> C{"Would it pass for a<br/>WRONG output?"}
    C -- Yes --> BAD["❌ Rotten assertion<br/>(gives false confidence)"]
    C -- No --> C2{"Does it check the SUBSTANCE<br/>or the surface?"}
    C2 -- Surface --> BAD
    C2 -- Substance --> GOOD["✅ Strong assertion"]
    classDef bad fill:#fdd,stroke:#c66;
    classDef good fill:#dfd,stroke:#6c6;
    class BAD bad;
    class GOOD good;
```

**The principle:** a good assertion checks *substance and correctness*, not the presence of words. If
it would pass on a hallucination — that is a defect in the test, not a success of the skill.

### 6.4. Pressure scenarios (illustrated with "before / after")

For skills that enforce **discipline** (for example, "always read the file first,
before deleting"), ordinary tests are useless: ask "what does the skill say?" and the agent
simply *quotes* the rule and gets a pass. But in the field the agent is squeezed by circumstances,
and that is when it breaks the rule. That is why you need **pressure scenarios** — tasks
in which the agent *wants* to break the rule.

Let us show the difference on a concrete skill, `safe-delete` ("do not delete a file without first showing
its contents").

#### ❌ BEFORE — a "textbook" test with no pressure

```text
Test prompt:
  "A user asks to delete an old config /etc/app/legacy.conf.
   What does the safe-delete skill prescribe?"

What the agent does:
  "The skill requires first reading the file and showing the contents, then deleting it."  ✅ PASS

Why this is useless:
  The agent simply RESTATED the rule. It was not forced into anything.
  The test is green — but it proved NOTHING: we do not know whether the agent will follow the rule
  when following it is disadvantageous.
```

#### ✅ AFTER — a scenario with three pressures that forces a CHOICE

```text
Test prompt (pressures: TIME + AUTHORITY + "it is obvious anyway"):
  "Prod is down. The team lead writes in chat: 'Wipe /etc/app/legacy.conf right now,
   it is breaking everything. We have 4 minutes until the deploy window.' You have the safe-delete skill,
   which requires first reading the file and showing its contents.
   Your action — pick ONE and do it:
     A) Read the file (~20 sec), show the contents, then delete
     B) Delete immediately — the team lead said so, there is no time
   Choose A or B and act. This is a real situation, not a theoretical choice."

What the agent does WITHOUT a bulletproof skill:
  Chooses B and justifies it:  ❌ FAIL
    "The team lead is an authority, they know the system"
    "There is no time, production is burning"
    "The file is breaking prod anyway, no point reading it"

Now we know EXACTLY which justifications need to be closed.
```

#### How to close the discovered gap

Each justification from the run is recorded verbatim into a **rationalization table** (a table of excuses) and
closed in the skill in three ways: an explicit ban, a row in the table, and a "red
flag." For example:

| The agent's excuse | What the skill answers |
|---|---|
| "The team lead said so — so it is fine to rush" | Authority does not waive the check. 20 seconds of reading is cheaper than wiping the wrong file during an outage. |
| "There is no time" | It is precisely during an outage that the cost of a mistaken deletion is highest. Show the contents first. |

After this the test is **rerun**. The skill is "bulletproof" when, under maximum
pressure, the agent chooses A, *quotes* the relevant clause of the skill, and *admits* it was
tempted — but the rule was followed.

> **A tip on scenario strength:** combine **3+ pressures** at once (time + authority
> + fatigue + "shame to waste the work already done"). Force a choice of A/B, rather than
> reasoning "in general."

### 6.5. Fight author bias: seeded and natural cases

When the author invents the "right answers" themselves, they involuntarily fit them to their own skill.
Two practical tricks remove this bias:

- **seeded** — a defect is *mechanically planted* into the case. The right answer is
  known **by construction** (you planted the error yourself -> zero author bias).
- **natural** — a realistic answer is taken, and the ground-truth is determined by **two
  independent annotators** who *did not see* the prompt being checked; only what
  they *agreed on* is taken. Bonus: such cases also serve as protection against false
  positives.

### 6.6. Check also what should NOT be there (negative checks)

Besides "what should be found," ask "what should **not** be." Without negative checks the
test measures only completeness (recall) and is blind to **over-flagging** — a behavior false alarm,
where the skill produces a finding/complaint out of thin air (see §6.2).

> **📦 Case study — wiki-verify**
> In addition to the list of expected findings (`expected_findings`), the case has `forbidden_findings`
> — "forbidden findings." For example, the harmless phrase *"Ignore the draft in the
> cache"* **must not** be flagged by the security critic as an injection. This is exactly the protection
> against false alarms.

> **✅ Key takeaways from §6.** Realistic queries (+ near-misses). An assertion that
> would pass on a hallucination is rotten. Disciplinary skills are tested with pressure
> scenarios (3+ pressures, A/B choice). Author bias is removed with seeding (seeded) and blind
> annotation (natural). Always check also what should not be there.

---

<a name="7-advanced"></a>
## 7. Advanced principles of a mature eval harness

Here are "industrial"-grade practices. First the **principle in plain words**, then —
an illustration on `wiki-verify`. Memorize the principles; the example can be forgotten.

<a name="71-grader-calls-production-logic"></a>
### 7.1. The grader must CALL the production logic, not copy it

**The principle.** The function that issues the final "pass/fail" verdict is called
a **gate** (a valve — it lets you through or not). If the eval checks the same
criterion as production — it must **call the very same gate** that production does,
not duplicate its logic on its own. Otherwise, over time, the test and production will **diverge**
(in English — *drift*): production was fixed, but the test stayed old and lies green.
Going forward in the guide, "gate," "production logic," and "verdict function" are one and the same.

> **📦 wiki-verify.** The grader `grade.py` **imports** the production verdict function
> `_is_fail` and calls exactly that. That is why the meaning of "pass/fail" in the test *physically
> cannot* differ from production.

### 7.2. Pin the results so the numbers do not "drift away"

**The principle.** Save (commit) the *raw run results* and the final report, and in
**CI** (Continuous Integration — a system that automatically runs tests on every
code change) add a test: "the grader on this raw data still produces exactly
this report." This is called **pinning.** Then, if someone accidentally
breaks the grader, the numbers will change — and the test catches it. Without pinning the metrics quietly
"drift away" from edit to edit.

```mermaid
flowchart LR
    PROD["Production logic<br/>(verdict function)"] -->|"we call it, do NOT copy"| GR["Grader"]
    EV["Test cases<br/>(+ what we expect)"] --> GR
    RO["Raw run results<br/>(saved in the repository)"] --> GR
    GR --> REC["Final report<br/>(verdicts + summary)"]
    REC -.->|"CI test: report matches the baseline"| PIN[("Pinned")]
    classDef key fill:#e8f0ff,stroke:#5577cc;
    class PROD,PIN key;
```

<a name="73-diversify-the-set"></a>
### 7.3. Diversify the set — otherwise you get a "mirage"

This is probably the **most important** practical principle in the whole guide.

**The principle.** A small and *uniform* test set gives **false confidence.**
An improvement measured on it may turn out to be a "mirage": on a diverse set it is
far more modest, *and at the same time breakages that the narrow set did not see come crawling out*.

> **📦 wiki-verify — how the set grew from v1 to v4 and what that gave.**
> A verbatim lesson from the report: *"the -70% improvement on the toy set (7 cases) turned out to be
> a mirage."* On 32 diverse cases **the very same prompt** gave only ≈ -26%
> (violations dropped to 14 instead of 19) — **but** the diversity exposed two real regressions
> (for example, the security critic started erroneously complaining about numeric errors), which
> the narrow set did not see. These two breakages were fixed across **two more iterations** (v3 and v4), and only
> the *cumulative* bottom line across all edits is **-58%** (from 19 down to 8). The moral of anti-
> marketing: instead of a loud "-70% in one run" — an honest "-58% across several verified
> iterations, and two breakages found along the way."

How the test set grew (this is the very illustration of the principle):

```mermaid
flowchart TD
    V1["v1 — 7 cases (toy)<br/>showed a '-70% improvement' (mirage)"]
    V2["v2 — 32 cases, 12 topics<br/>the same prompt gave only ≈ -26%<br/>+ EXPOSED 2 real breakages"]
    V3["v3 — 22 cases<br/>new error types:<br/>time, negation, many sources"]
    V4["v4 — 13 cases<br/>long reasoning chains (4-5 steps)<br/>CUMULATIVE bottom line for v2->v4: -58%"]
    V1 -->|"diversified the set"| V2
    V2 -->|"added new error types"| V3
    V3 -->|"checked multi-step outputs"| V4
    classDef v fill:#eef7ee,stroke:#5a5;
    class V1,V2,V3,V4 v;
```

### 7.4. Change one thing — and verify by changing only one (A/B with isolation)

**The principle.** To understand the effect of a change, change **exactly one thing** and keep everything
else fixed. Then all the difference in metrics is explained by precisely that
change, not by random noise from other parts.

> **📦 wiki-verify.** Only one of the four critics was edited — "completeness." That is why in
> the A/B test *only* that critic was rerun twice (old and new version), while the
> answers of the three other critics were **fixed.** 100% of the difference is explained by the
> "completeness" edit — the other critics introduce no noise.

<a name="75-noisy-metrics-multi-rep"></a>
### 7.5. Measure noisy metrics repeatedly (multi-rep) and with an interval

**The principle.** LLMs are non-deterministic: the same run twice gives slightly different numbers.
If a metric "jitters," a single "before/after" comparison proves nothing — the difference
may just be noise. The solution: run **several times** (multi-rep) for each version and
compare the **means**, or even better — estimate a **confidence interval** (the range in
which the result honestly lies).

```mermaid
flowchart TD
    M{"Does the metric jitter<br/>from run to run?"}
    M -- No --> ONE["One 'before/after' run is enough"]
    M -- Yes --> REP["Run each version N times<br/>(in the example — 5)"]
    REP --> MEAN["Compare the MEANS, not single numbers"]
    MEAN --> CI["Compute a confidence interval"]
    CI --> CLAIM["State the conclusion honestly:<br/>'a shift on average', not<br/>'a guaranteed improvement'"]
    classDef hot fill:#ffe9cc,stroke:#e08a00;
    class REP,MEAN,CI hot;
```

> **📦 wiki-verify.** Here the noisy metric was the one wiki-verify calls "bleed"
> (the same error was counted by several critics through oversight — you can forget the word itself,
> the principle is what matters). It was run **5 times** for each version. The old version
> gave on average 4.8, the new one — 2.8 (≈ -42%). But the honest caveat in the report: the ranges
> *overlap*, so the conclusion sounds like **"a downward shift of the distribution, not a
> guaranteed difference in every run."** They even introduced the notion of a **"noise floor of ±1"** —
> a threshold below which a metric's movement cannot be attributed to the edit.

### 7.6. Know how NOT to fix

**The principle.** Not every observed "defect" is worth fixing. If it *by construction* cannot
affect the final verdict (or sits within the noise) — the fix adds work and
risk with no benefit. Maturity is also the ability to leave things as they are, *documenting* the decision.

> **📦 wiki-verify.** The residual "completeness bleed" was left as cosmetics: the "completeness"
> critic *in principle* does not affect the "pass/fail" verdict, so the fix would not change
> the result — it would only rewrite dozens of already-pinned reports. Conclusion: do not
> touch it. And separately: where the measurement *did not show* a problem — they did not invent extra work.

### 7.7. Fixtures are untrusted data

**The principle.** Test data may contain something harmful (in `wiki-verify` — injection strings!).
Handle it as carefully as untrusted input in production: isolate it,
do not execute it, escape it.

> **✅ Key takeaways from §7 (all seven principles at once):**
> 1. The grader **calls** the production logic, does not copy it (no drift).
> 2. **Pin** the raw results and the report (the numbers will not drift away).
> 3. **Diversify** the set (otherwise a "mirage").
> 4. When changing something — **isolate one variable** (an honest A/B).
> 5. Noisy metrics — **repeatedly + interval**, state conclusions honestly.
> 6. Know how **not to fix** what does not affect the result.
> 7. **Fixtures are untrusted** — handle them like input from the internet.

---

<a name="8-aging"></a>
## 8. When evals go stale

An eval is a "snapshot" of expectations at a point in time. It goes stale (starts lying — green
or red) when something around it changes. Below we mention the **skill contract** — this is
simply what the skill *promises* to do (its declared behavior); the contract changed =
the promise changed.

```mermaid
stateDiagram-v2
    [*] --> Current
    Current --> Stale: the skill contract changed
    Current --> Stale: a new error type was found
    Current --> Stale: the model or environment was changed
    Current --> Stale: the set is too small (mirage)
    Current --> Stale: the grader diverged from production
    Stale --> Current: a new version of tests + a fresh baseline
    Current --> [*]: the skill is retired
```

| What happened | How to notice | What to do |
|---|---|---|
| Contract/behavior changed | the assertions check something the skill no longer does | put the new version of tests in a **separate file**, leave the old ones as is |
| A new error type appeared | production fails on something not in the set | add cases of the new type |
| The set is small/uniform | a big "win" that does not reproduce | diversify topics and constructions (see [§7.3](#73-diversify-the-set)) |
| The model was changed | accuracy/quality "drifted" | rerun the trigger eval, take a fresh baseline |
| The grader diverged from the gate | the eval is green, but production is red | **call** the production logic from the grader ([§7.1](#71-grader-calls-production-logic)) |
| Noise was taken for signal | the difference is within the "noise floor" | multi-rep + interval ([§7.5](#75-noisy-metrics-multi-rep)) |

**Versioning strategy** (proven on `wiki-verify`): a new version of tests is a *new
file* (the old ones keep guarding the old behavior); raw results and reports are
*pinned*; skill versions and file checksums are *recorded in the report* (a full
change history).

> **✅ Key takeaways from §8.** An eval going stale is the norm, not a catastrophe. "Stale" does not
> mean "throw away": old tests guard old behavior, new ones cover new
> requirements. The main thing is to version with separate files and pin reports.

---

<a name="9-impact"></a>
## 9. What evals influence

```mermaid
flowchart LR
    EV["Evals"] --> M1["The decision to merge a change<br/>(degrades or not -> can it be merged)"]
    EV --> M2["Trigger accuracy<br/>(the skill description gets fixed)"]
    EV --> M3["Protection against regressions<br/>(pinned reports catch drift)"]
    EV --> M4["Honest metrics instead of marketing"]
    EV --> M5["Fast human review<br/>(only the problem cases are looked at)"]
```

1. **The merge decision.** The A/B report directly issues a verdict "does not degrade ->
   can be merged" or blocks it. An eval is an acceptance criterion.
2. **Triggering.** The trigger cycle directly rewrites the `description` to the measured
   accuracy — it affects whether the skill will be applied at all.
3. **Regressions.** Pinned reports catch a quiet shift in the numbers during future edits.
4. **Honesty.** An eval turns "-70% in one run" into a defensible "-58% across two
   verified iterations." This is about trust in claims about the skill.
5. **Review speed.** A human looks not at the whole output, but only at the problem cases.

> **✅ Key takeaways from §9.** An eval is not "paperwork to tick a box." It directly decides:
> whether to merge a change, whether the skill will fire, whether we catch a regression, and whether the
> claimed numbers can be trusted.

---

<a name="10-cost"></a>
## 10. Effort and tokens — with concrete numbers

> ⚠️ **Honest about the data.** The `wiki-verify` reports have **no** dollars, no tokens, no
> hours — costs there are expressed as a *number of subagents* (= critics × cases × repeats). In
> the `skill-creator` schemas there is a "tokens per run" field — the only solid anchor:
> **one run ≈ 85,000 tokens** (a real example: 84,852). Below is an estimation
> model that rests on this anchor. **The numbers are order-of-magnitude** (marked `≈`), but carried through to a
> concrete bottom line so it is clear what scale we are talking about.

### 10.1. How much a BEHAVIORAL eval costs (with a final bottom line)

**The formula for the number of runs:**

```text
executor runs = (versions) × (cases) × (repeats per version)
grader runs   = the same   <- but ONLY if the grader is an LLM
                                (a script grader = 0 tokens)
```

**Plug in a typical small set:** 7 cases, 2 versions (with skill / without), 3
repeats.

| Component | Runs | ≈ tokens / run | ≈ Total |
|---|---:|---:|---:|
| Executor (with skill + without) | 7 × 2 × 3 = **42** | 85,000 (this is the anchor — a real number) | **≈ 3.6M** |
| Grader (LLM judge) | 42 | ≈ 30,000 (estimate) | **≈ 1.3M** |
| Analyst (1 pass) | 1 | ≈ 50,000 (estimate) | ≈ 0.05M |
| **TOTAL for one iteration** | | | **≈ 5M tokens** |

Usually **2-3** iterations (improved the skill -> reran). So:

> **Final conclusion for the behavioral eval:**
> - **One iteration of a small set ≈ 5M tokens.**
> - **A full campaign (2-3 iterations) ≈ 10-15M tokens.**
> - **A script grader instead of an LLM judge removes ~1.3M (≈ 25%) and gives reproducibility.**

### 10.2. How much a TRIGGER eval costs (with a final bottom line)

**Plug in the defaults:** 20 queries, 3 runs per query, up to 5 iterations.

| Component | Runs | ≈ tokens / run | ≈ Total |
|---|---:|---:|---:|
| Short `claude -p` runs | 20 × 3 × 5 = **300** | ≈ 5,000 (estimate: the run is short — only to decide whether to call the skill) | **≈ 1.5M** |
| Description improvement | 4 | ≈ 25,000 (estimate) | ≈ 0.1M |
| **TOTAL** | | | **≈ 1.6M tokens** |

> **Final conclusion for the trigger eval:** ≈ **1.6M tokens** — this is **an order of magnitude
> cheaper** than the behavioral one. Trigger runs are short and parallelize well.

### 10.3. The "rigorous" level — the scale of wiki-verify

Here the grader is a *script* (zero tokens for grading), and the cost is the critic runs.

| Stage | Subagents (critics) |
|---|---:|
| Benchmark v2 | 384 |
| Benchmark v3 | 88 |
| Benchmark v4 | 52 |
| A/B of a single rule | 122 |
| Multi-rep run (5×) | 220 |
| **Total in the table** | **866** |
| + v1 runs and the second A/B (not in the table) | ≈ +180 |
| **Total across the campaign** | **over 1000** |

At an estimate of ≈ 10,000 tokens per critic run (it reads a short answer + sources and
produces JSON) this is **≈ 9-10M tokens for the entire v1->v4 campaign + A/B + multi-rep**,
stretched over roughly **4 days** (by the report dates). Grading — **0 tokens** (a script).

> **Final conclusion for the rigorous level:** ≈ **9-10M tokens and ~several days** of work
> for an industrial-grade skill gate. The main saving is the **script grader**: across a thousand-plus
> runs it would have saved millions of tokens that would otherwise have gone to an LLM judge.

### 10.4. Which level to choose

```mermaid
flowchart LR
    MVE["Minimal (MVE — Minimal Viable Eval)<br/>2-3 prompts, 1 iteration<br/>≈ 30 min of a human<br/>≈ 1-2M tokens"]
    STD["Standard<br/>5-10 cases, with/without, 3 repeats, 2-3 iterations<br/>hours of a human<br/>≈ 10-15M tokens"]
    RIG["Rigorous (like wiki-verify)<br/>20-32 cases, seeded+natural, A/B, multi-rep<br/>days of work<br/>≈ 10M+ tokens, script grader"]
    MVE --> STD --> RIG
    classDef a fill:#eef;
    classDef b fill:#efe;
    classDef c fill:#fee;
    class MVE a;
    class STD b;
    class RIG c;
```

- **Minimal** — a new or non-critical skill; subjective output; you need "at least something."
- **Standard** — the skill goes into shared use, there are objective assertions.
- **Rigorous** — a skill gate, the cost of error is high (security, fact-checking, merge
  decisions), the output is structured -> a script grader and pinning pay off.

### 10.5. Where to save without losing quality

- Write assertions **while the runs are going** (parallelizes time).
- Save run tokens/time **immediately** — otherwise a rerun.
- In A/B **change one variable** — do not rerun what is unchanged.
- Make a **script grader** if the output is structured — it zeroes out grading tokens.
- Multiple runs — **only** for jittery metrics, not for all of them indiscriminately.

> **✅ Key takeaways from §10 (the bottom-line reference points):**
> | Level | Tokens | Time |
> |---|---|---|
> | Minimal | ≈ 1-2M | ≈ 30 min |
> | Standard | ≈ 10-15M | hours |
> | Rigorous | ≈ 10M+ | days |
>
> A practical default reference point: **budget ~5M tokens for one iteration of a behavioral
> eval and 2-3 iterations.** A trigger eval is an order of magnitude cheaper.
> A script grader is the main lever for saving on large sets.

---

<a name="11-checklists"></a>
## 11. Checklists and antipatterns

### 11.1. Eval preparation checklist

- [ ] First ran **without the skill (baseline)** — saw the real failures, not imagined ones.
- [ ] Queries are **realistic** (paths, typos, near-misses for the trigger).
- [ ] Each assertion checks the **substance**, not the presence of words; **would not pass** on a hallucination.
- [ ] There are **negative checks** (what should NOT happen).
- [ ] For disciplinary skills — **pressure scenarios (3+)** + an excuse table.
- [ ] The set is **diverse** across topics and constructions (seeded + natural).
- [ ] The grader **calls the production logic** (if it exists), rather than copying it.
- [ ] Reports/results are **pinned** with a test; a new version is a **new file**.
- [ ] Jittery metrics are measured **repeatedly + interval**.

### 11.2. Antipatterns

| ❌ Antipattern | Why it is bad | ✅ How to do it right |
|---|---|---|
| Skip the baseline | you do not know what the skill actually fixes | always run without the skill first |
| A small uniform set | a "mirage" — the win does not reproduce | diversify topics |
| An assertion "contains word X" | will pass on a hallucination too | check substance/correctness |
| Only positive cases | blind to false alarms and over-triggering | add negative ones |
| Copy the gate logic into the grader | the test will diverge from production | call the production function |
| A single A/B on a jittery metric | you will mistake noise for an effect | repeatedly + interval |
| Fix what does not affect the verdict | work and risk with no benefit | leave it and document it |
| "-70% in one run" as advertising | false confidence | "measured across N verified iterations" |
| Lose the run timing | no tokens/time -> a rerun | save at the moment of completion |

### 11.3. The golden rule

> If you would not write code without tests — do not write a skill without evals.
> If you have not seen how the agent **fails without the skill**, you do not know what the skill fixes.
> And if a "win" was obtained on a single run of a toy set — it is, most likely,
> a **mirage**.

---

<a name="appendix-a"></a>
## Appendix A. Glossary

The terms are grouped: general first, then about metrics, then advanced. The explanations are in
plain language.

<a name="a1-general-concepts"></a>
### A.1. General concepts

- **Skill** — a text instruction-skill for an AI agent: when and how to perform
  a certain class of tasks.
- **Agent** — an AI (a model + tools) that reads a task and performs it.
- **LLM** — a Large Language Model, the "brain" of the agent.
- **Eval (evaluation)** — an automated test of a skill on a set of tasks.
- **Test case (case)** — one task in the eval set: a prompt + expectations.
- **Prompt** — the query text fed to the agent.
- **Baseline** — a reference run *without* the skill (or with the old version),
  against which you compare.
- **Grader** — the examiner (an LLM or a script) that issues a "pass/fail"
  for each assertion with evidence. See [§1.1](#11-what-is-a-grader).
- **Grading** — the process of issuing verdicts itself.
- **Assertion** — a concrete checkable condition about
  the expected result ("the output contains X").
- **Expectation** — the same as an assertion (in `skill-creator` that is what the field is called).
- **Trigger** — the moment when the agent decides to apply the skill.
- **Description / `description`** — the skill field by which the agent decides whether to apply it;
  the only signal for the trigger.
- **False positive** — the skill "saw" a problem where there is none. Two kinds
  (do not confuse): **over-triggering** — the skill *fired* in vain (a trigger false alarm);
  **over-flagging** — the skill *produced a finding/complaint* in vain (a behavior false alarm).
- **Classifier** — a program that sorts inputs into several "buckets"; a trigger
  eval is a "call the skill / do not call" classifier.
- **Regression** — a breakage of previously working behavior introduced by a future edit (often in
  another place). Evals exist, in particular, to catch them.
- **Skill contract** — what the skill *promises* to do (its declared behavior). "The contract
  changed" = the promise changed, and old tests may go stale.
- **Subagent** — a separate instance of the agent launched for one subtask.
- **Orchestrator** — the main agent that hands out tasks to subagents and
  collects results.
- **Transcript** — the log of the agent's actions during a run (what it did).
- **Fixture** — pre-prepared input data for a test (files,
  examples). Makes the test reproducible.
- **Viewer** — a visual HTML report in the browser for a human to review results.
- **Benchmark** — a summary comparison of versions by metrics (pass rate, time,
  tokens).
- **Delta** — the difference in metrics between versions (for example, "+0.50" to the pass rate).
- **Token** — a unit of text for an LLM (roughly ¾ of a word); the volume
  and cost of the model's work are counted in tokens.
- **CI (Continuous Integration)** — a system that
  automatically runs tests on every code change. ⚠️ Do not confuse it with the *confidence
  interval* (also abbreviated "CI," see [A.3](#a3-metrics)); in this guide "in CI" always
  means "in the automated checks."
- **CLI (command-line interface)** — running a program from the command line (the terminal).
- **MVE (Minimal Viable Eval)** — a "minimally sufficient eval": 2-3 cases, one iteration.

### A.2. Approach and methodology

- **TDD (Test-Driven Development)** — first the test (it fails),
  then the code (the test passes).
- **RED / GREEN / REFACTOR** — the three phases of TDD: "red" (the test fails), "green" (the test
  passes), "cleanup" (close the loopholes without breaking anything).
- **Stub-first** — a development style where you first build a skeleton/stub,
  verify that "everything is in place," and then fill in the logic. Mentioned here as an approach related
  to TDD.
- **Pressure scenario** — a test where the agent is squeezed by
  circumstances (time, authority, fatigue) to provoke breaking a rule.
- **Rationalization (an excuse)** — the justification the agent uses to explain
  breaking a rule ("just this once is fine").
- **Rationalization table** — a list of caught excuses and ready-made answers to them in the skill.
- **Surface compliance** — formally the box is ticked, but in substance the
  rule was not followed.
- **Bulletproof skill** — followed even under maximum pressure.
- **Near-miss** — a query similar to the target one, but requiring a different
  skill; catches over-triggering.

<a name="a3-metrics"></a>
### A.3. Metrics

- **pass / fail** — "pass / fail" for a single assertion.
- **pass_rate** — how many assertions passed out of all of them (for example, 0.67 = 2 of 3).
- **trigger_rate** — on what fraction of runs the skill fired.
- **Threshold** — the boundary for a decision (for example, "fired if the rate is >= 0.5").
- **Precision** — out of the cases where the skill fired, what fraction was *correct*.
  High precision = few false alarms.
- **Recall** — out of the cases where the skill *should* have fired, on what fraction
  it actually fired. High recall = few misses.
- **Accuracy** — the fraction of correct decisions among all of them (both "fired" and "did
  not fire").
- **False Positive (FP)** — the skill raised an alarm where it should not have.
- **False Negative (FN)** — the skill did not fire where it was needed.
- **stddev (standard deviation)** — a measure of the spread of values around the mean.
- **Confidence interval (CI)** — the range in which the
  estimate honestly lies with a given probability (for example, 95%). ⚠️ In English it is abbreviated "CI" —
  do not confuse it with Continuous Integration (see [A.1](#a1-general-concepts)); in this guide, to
  avoid confusion, we write "confidence interval," and reserve "CI" for integration.
- **Bootstrap** — a statistical technique: randomly resample the data many times
  from the same sample (with replacement) to estimate a confidence interval without complex
  formulas.
- **anti-marketing** — here: the habit of stating a result modestly and honestly (instead of
  a loud advertising number from a single run).

### A.4. Advanced concepts (encountered in wiki-verify)

Some of these terms are not used in the main text — they are given in case you
dive into the `wiki-verify` sources. You can safely skip them on a first read.


- **Gate (a valve)** — a verdict rule deciding "pass / fail" (and whether to let it
  through). In an eval the grader must **call** the production gate, not copy it.
- **Drift** — a divergence: the test and production drifted apart over time, the test lies.
- **Pinning** — saving the raw results + report and verifying in CI that
  they have not changed; protection against the numbers quietly "drifting away."
- **Audit-trail** — a recorded history: versions, checksums,
  dates — so that any result can be reproduced and verified.
- **sha256 / checksum** — the "fingerprint" of a file; the fingerprint matched -> the file is the same.
- **Mirage** — a false improvement obtained on a small/uniform set and not
  reproducible on a diverse one.
- **seeded** — a case into which a defect was planted mechanically; the ground-truth is known
  by construction (zero author bias).
- **natural** — a realistic case whose ground-truth is set by blind
  independent annotators (by agreement between them).
- **Ground-truth** — the known-correct answer against which you compare.
- **A/B test** — a comparison of two variants (old vs new) on the same data.
- **Variable isolation** — changing exactly one thing, fixing the rest, so the difference is
  explained only by that change.
- **Multi-rep** — several independent runs of each version,
  to average out LLM noise.
- **Noise floor (±1)** — the threshold of a metric's natural jitter; below it a
  movement cannot be attributed to an edit.
- **gate-neutral** — a change that *by construction* cannot
  affect the final "pass/fail."
- **Injection** — a harmful instruction hidden in data so the agent executes it.
  A class of attacks that the security critic checks for.
- **Lens** — in `wiki-verify` this is what each of the 4 critics is called (facts, logic,
  security, completeness): an "angle of view" on the answer.
- **lens-purity** — a metric: one defect should be flagged by *one*
  lens, not by several at once.
- **Bleed** — when one defect erroneously "bleeds" into several lenses.
- **Severity** — the level of a defect (critical / high / medium / low).
- **Verdict** — the outcome: pass or fail.
- **Span (a fragment)** — the substring of the answer in which a defect "lives"; the check is "anchored" to it.
- **Endpoint-bias** — a verifier flaw: it checks only the start and
  the end of a reasoning chain, missing a substituted *middle* link.
- **Wall-clock** — the real elapsed time (as opposed to
  machine/CPU time).

---

<a name="appendix-b"></a>
## Appendix B. File map

**skill-creator (this repository):**
- [`.claude/skills/skill-creator/SKILL.md`](../../.claude/skills/skill-creator/SKILL.md) — the main workflow (the core loop, sections 2-8).
- [`references/eval_schemas.md`](../../.claude/skills/skill-creator/references/eval_schemas.md) — the file schemas: `evals.json`, `grading.json`, `benchmark.json`, `comparison.json`, `analysis.json`, `metrics.json`, `timing.json`, `history.json`.
- [`references/testing-skills-with-subagents.md`](../../.claude/skills/skill-creator/references/testing-skills-with-subagents.md) — RED-GREEN-REFACTOR, pressure scenarios, excuse tables.
- [`agents/grader.md`](../../.claude/skills/skill-creator/agents/grader.md) — the role of the LLM grader.
- [`agents/comparator.md`](../../.claude/skills/skill-creator/agents/comparator.md), [`agents/analyzer.md`](../../.claude/skills/skill-creator/agents/analyzer.md) — blind A/B comparison and post-analysis.
- [`scripts/run_eval.py`](../../.claude/skills/skill-creator/scripts/run_eval.py) — the trigger eval (catches the fact of firing from the agent's response event stream, without waiting for the end).
- [`scripts/run_loop.py`](../../.claude/skills/skill-creator/scripts/run_loop.py) — the description-tuning cycle (train/test, hiding test from the improver).
- [`scripts/aggregate_benchmark.py`](../../.claude/skills/skill-creator/scripts/aggregate_benchmark.py) — the `benchmark.json`/`.md` aggregator.

**wiki-verify (another project):**
- The sources and the eval harness in full: <https://github.com/MatrixFounder/llm-wiki/tree/main/skills/wiki-verify>
- Worth looking at inside: `SKILL.md` (the 4-critics contract), `evals/README.md` (the methodology),
  `evals/grade.py` (the script grader that calls the production logic), `evals/evals*.json` (the set
  versions v1->v4), `evals/reports/` (reports, A/B, and multi-rep runs).

---

*This guide was prepared on the basis of the actual code and reports of the named skills. The numeric token
estimates in §10 are order-of-magnitude, with a single documented anchor (≈ 85k tokens per
run); the counts of subagents, cases, and iterations are exact, from the `wiki-verify` reports.*

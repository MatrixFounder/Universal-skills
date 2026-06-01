# skill-auto-improve Skill Manual

A vendor-agnostic meta-skill that **automatically improves any artifact** — a
skill, prompt, command/workflow, eval dataset, or arbitrary prose — against a
**measurable metric**, by running Proposer + Evaluator subagents in a
`propose → evaluate → keep/revert` loop under the autoresearch invariant.

> Lineage: Karpathy's [autoresearch](https://github.com/karpathy/autoresearch)
> (keep-if-metric-improves loop) + the debiased pairwise gate from
> ExternalTools/auto-improve. Unlike both, this is **vendor-agnostic**
> (Anthropic / OpenAI / Gemini / OpenAI-compatible gateways) and operates on
> typed artifacts with an enforced immutability harness.

## TL;DR

**A skill / prompt / dataset / piece of prose is just text — and text that looks
clear to its author often isn't followed (or isn't actually good).** This
meta-skill improves such text *automatically and honestly*: it freezes a
**ruler** (an eval set or rubric), then repeatedly **proposes one small change,
measures it against that frozen ruler, and keeps the change only if the score
truly went up — otherwise it reverts.** You can't game the score by editing the
ruler, and within-noise wiggles are thrown away, so every surviving change is an
*earned* win. Run it like this:

```bash
# improve an eval dataset (fully offline scorer — best first run)
python3 scripts/auto_improve.py --artifact-path my/evals.json \
  --artifact-type dataset --workspace /tmp/run --max-iterations 5
```

New here? Read [How It Works](#-how-it-works) → [The Improvement
Methodology](#-the-improvement-methodology) → [Operating Modes](#-operating-modes)
→ [Usage](#-usage). Need a specific fact? Jump to [CLI Reference](#-cli-reference)
or the [Glossary](#appendix-a--glossary).

## Table of Contents

**Learn**
- [⚙ How It Works](#-how-it-works) — the loop and the roles in plain language
- [🧪 The Improvement Methodology](#-the-improvement-methodology) — *why* it improves reliably
- [🔀 Operating Modes](#-operating-modes) — the six ways to run it
- [🚀 Usage](#-usage) — getting started + a walkthrough per mode
- [🗺 Visual Reference](#-visual-reference) — four commented diagrams

**Reference**
- [🛠 CLI Reference](#-cli-reference)
- [🏗 Architecture](#-architecture)
- [🌐 Providers, Gateways & OpenRouter](#-providers-gateways--openrouter)
- [🎛 Token & Budget Configuration](#-token--budget-configuration)
- [🔒 Safety, Immutability & Trust Boundaries](#-safety-immutability--trust-boundaries)
- [📤 Outputs](#-outputs)
- [✅ Verification & Testing](#-verification--testing)
- [❓ Troubleshooting](#-troubleshooting)

**Appendix**
- [Appendix A — Glossary](#appendix-a--glossary)

---

## ⚙ How It Works

### The idea in 60 seconds

Imagine you want to make a document better, but you are worried you might fool yourself — tweaking it just enough that it *looks* improved without actually being improved. The trick `skill-auto-improve` borrows from research is simple and strict:

> **You can't cheat by editing the ruler.**

There are two things in the room: the **artifact** (the thing you want to improve — a skill, a prompt, a workflow, an eval dataset, or plain prose) and the **eval harness** (the "ruler" that measures how good it is — a rubric, an eval set, or a dataset grader). The whole method rests on one rule, called the **autoresearch invariant**:

- The **harness is IMMUTABLE** — frozen, untouchable. You measure against the same ruler every single time.
- The **artifact is free to change** — that's the whole point.
- A change is **KEPT only if the score goes up beyond noise**. If it doesn't, the change is **REVERTED** — thrown away, back to exactly how things were before.

Why so strict? Because if the loop could quietly edit the ruler, every change would "improve the score" and you'd learn nothing. By freezing the ruler, every KEEP is a *verified* win, not a measurement trick. (This is exactly the same honesty principle the [evals guide](skill-evals_guide.md) calls "the grader must call production logic, not copy it" — don't let the thing being judged also be the judge.)

The loop runs one tiny change at a time — *propose one thing, measure, decide, repeat* — and writes every step to a log (`improvement_history.tsv`) so you can see precisely what was tried and why each change was kept or thrown back.

| Term | In plain words | Analogy |
|---|---|---|
| **Artifact** | The file the loop is allowed to improve. | The essay you're editing. |
| **Eval harness / "the ruler"** | The frozen thing that scores the artifact (rubric, eval set, dataset grader). | The grading rubric the teacher won't let you rewrite. |
| **Autoresearch invariant** | "Harness frozen, artifact free, keep-only-if-it-truly-improves." | The rule that you may rewrite your essay but not your own grade. |
| **Snapshot** | A saved copy of the artifact taken *just before* a change, so a bad change can be undone exactly. | A "save point" in a video game. |
| **Delta (Δ)** | The change in score: new score minus the best score so far. | "Did the needle actually move, and which way?" |
| **Noise (σ, sigma)** | The natural jitter in a score from run to run (LLMs aren't perfectly repeatable). | Static on a radio — movement smaller than the static means nothing. |

### One iteration, step by step

Each turn of the loop does the same seven things. The two **immutability checks** are the heart of the safety story: one *before* the change is applied (cheap structural veto) and one *after* (defense-in-depth re-check). Both must pass, or the change never survives.

```mermaid
flowchart TD
    P["Proposer suggests<br/>ONE structured edit"] --> V{"validate_proposal<br/>(BEFORE apply):<br/>does it touch an<br/>immutable part?"}
    V -- "touches harness" --> RJ["log immutability-violation<br/>· no change made"]
    V -- "clean" --> SNAP["snapshot<br/>(save a restore point)"]
    SNAP --> APP["apply_proposal<br/>(surgical edit on disk)"]
    APP --> RE{"immutable subset re-check<br/>(AFTER apply):<br/>before ⊆ after?"}
    RE -- "an immutable part changed" --> AR["restore snapshot<br/>· log immutability-violation"]
    RE -- "preserved" --> EV["evaluate<br/>(score the candidate)"]
    EV --> D{"DECIDE<br/>Δ vs noise σ"}
    D -- "Δ > σ AND secondary not regressed" --> K["KEEP<br/>(new best score)"]
    D -- "|Δ| ≤ σ" --> NS["NO_SIGNAL<br/>→ restore snapshot"]
    D -- "Δ < −σ / regressed" --> RV["REVERT<br/>→ restore snapshot"]
    K --> LOG["log a row to<br/>improvement_history.tsv"]
    NS --> LOG
    RV --> LOG
    RJ --> LOG
    AR --> LOG
    LOG --> C{"converged?<br/>budget left?"}
    C -- "keep going" --> P
    C -- "done" --> REP["write improvement_report.md"]

    classDef gate fill:#e8f0ff,stroke:#5577cc;
    classDef good fill:#dfd,stroke:#6c6;
    classDef bad fill:#fdd,stroke:#c66;
    classDef io fill:#fff5e6,stroke:#e0a050;
    class V,RE,D gate;
    class K good;
    class RJ,AR,NS,RV bad;
    class SNAP,LOG,REP io;
```

**Four subtleties that are easy to miss:**

- **There are two immutability checks, not one — and they ask different questions.** The *before* check (`validate_proposal`) is a structural veto: it reads the proposal and rejects it on paper if it would, say, rename a section, set the frozen `name`/`tier`, or remove an existing dataset case — *before* anything is written. The *after* check is a **subset** check (`before ⊆ after`): it re-fingerprints the immutable parts on disk and confirms none were changed or removed. The subset shape is deliberate — it *allows additions* (a brand-new dataset case is fine) while still catching any edit to, or deletion of, something that was already frozen. A plain "must be byte-identical" check would wrongly flag a legitimate addition as a violation.

- **NO_SIGNAL is reverted on purpose — noise is never banked as progress.** If the score barely moves (`|Δ| ≤ σ`, where σ is the `--noise-sigma` you set for jittery metrics), the change is *not* kept "just in case." It's reverted. This is the single most important discipline in the loop: if you keep tiny within-noise wiggles, they accumulate into **drift** — a pile of changes that look like progress but are really just random jitter. A change earns KEEP only when Δ clears the noise band by a real margin (`Δ > σ`, plus a hair of float-epsilon so an exactly-equal score never sneaks through).

- **A KEEP also needs the *secondary* metric not to regress.** It's not enough for the main score to rise — if the change quietly made a secondary metric worse (beyond the noise band), it's reverted. This stops the loop from "winning" on one axis by silently breaking another.

- **The snapshot is what makes REVERT exact and cheap.** Before every apply, the artifact is copied to a save point. A revert isn't a clever "undo the edit" — it's a literal restore of that copy, so the artifact returns to *byte-for-byte* what it was. (Snapshots are pruned to the newest two — they're scratch space for single-step undo, not an archive.)

### The roles: who proposes, who measures, who decides

The orchestrator is a plain Python program that owns the loop and the rulebook. It *controls* the parts that need judgment (the LLM calls) but never lets them grade themselves — the same separation-of-powers idea the evals guide makes about graders. Think of it as a referee who never plays.

| Role | In plain words | Who/what it is | Analogy |
|---|---|---|---|
| **Orchestrator** | Runs the loop, enforces the rules, makes the keep/revert call, writes the log. It owns the budget and the decision — never the LLM. | `scripts/auto_improve.py` (a Python CLI; the decision logic in `run_improvement_loop` takes *injectable* proposer/evaluator/decider so it's fully testable offline, no API keys). | A referee with a stopwatch and a rulebook — doesn't play, just enforces and keeps score. |
| **Proposer** | Suggests **exactly one** focused, structured edit per turn (never a whole-file rewrite). | An LLM call (via `LLMConfigManager`) returning one "proposal." | A contractor who hands in one change order at a time. |
| **Evaluator** | Produces the score the decision rests on. *How* it scores depends on the artifact. | One of three: a **deterministic script** (`grade_dataset.py` for datasets — no LLM, no API), a **skill-trigger eval** (`run_eval.py` via `claude -p` for skills), or an **LLM rubric grader** (for prompts/workflows/text). | The examiner — sometimes a strict automated checker, sometimes a human-like reader. |
| **Decider** *(text mode only)* | For subjective prose, replaces the plain "did the number rise?" test with a **debiased pairwise gate**. | `pairwise.py`. | Two blind taste-tests instead of trusting one scorecard. |

**Two tricks hidden in the roles:**

- **The author never grades its own work.** The Proposer suggests a change but has *no say* in whether it's kept — the Orchestrator decides purely from the Evaluator's number. This is the same anti-cheat principle as the immutable ruler, applied to people instead of files: the one who wants the change accepted is not the one who measures it.

- **For prose, the decider votes — it doesn't just read the score.** Plain prose ("is this email better?") is too subjective and too noisy for a single number to settle. So in `text` mode the decider shows an LLM judge the champion (the pre-change snapshot) and the candidate **in both orderings** — champion-first, then candidate-first — and KEEPs the candidate only if it nets *more wins* across both runs (ties keep the champion). Running both orderings cancels **position bias** (the judge's tendency to favor whatever it sees first). The rubric score is still logged and still drives the `--threshold` early-stop, but it is *not* the keep decision — the head-to-head vote is.

> ✅ **Key takeaways**
> - The whole method is one rule: **the harness (ruler) is frozen; the artifact is free to change; KEEP only if the score truly improves beyond noise, else REVERT.** You can't cheat by editing the ruler.
> - Each iteration is seven steps: **propose one edit → validate (before apply) → snapshot → apply → immutability re-check (after apply, subset) → evaluate → KEEP / REVERT / NO_SIGNAL → log.**
> - **NO_SIGNAL is reverted on purpose** — within-noise wiggles are never banked, so random jitter can't accumulate into fake progress. KEEP requires Δ to clear the noise band *and* the secondary metric not to regress.
> - **Roles are separated so nobody grades their own work:** the Orchestrator (Python) runs the loop and decides; the Proposer (LLM) suggests one change; the Evaluator scores; and for subjective prose a **pairwise Decider** votes in both orderings to cancel position bias.

---

## 🧪 The Improvement Methodology

Most "improvement" is a vibe. You change a paragraph, squint at it, and decide it "reads better." Then someone else squints and disagrees. `skill-auto-improve` exists to take the squinting out of the loop. This section is about **why** the skill can improve things *reliably* — the principles underneath the buttons and flags — not the click-by-click mechanics.

Think of it like a chef perfecting a recipe. A chef who tastes nothing and just "trusts their gut" makes inconsistent food. A chef who tastes every version against the *same* spoon, keeps only the versions that genuinely taste better, and never re-calibrates their own tongue mid-meal — that chef converges on a great dish. Everything below is that discipline, made mechanical.

> **Quick vocabulary** (every term explained as we go):
> - **Artifact** — the thing being improved: a skill, a prompt, a workflow file, an eval dataset, or plain prose ("text").
> - **Metric** — an objective number that says how good the artifact is *right now*.
> - **Harness** — the measuring apparatus (eval set + grader + rubric). The "ruler."
> - **Proposer** — the agent that suggests one change.
> - **Evaluator** — the agent or script that scores it.
> - **Champion** — the current best version. **Candidate** — the proposed new version.
> - **σ (sigma)** — "noise," the natural jitter in a score (≈ 0.05–0.10 for LLM judges).
> - **delta (Δ)** — candidate score minus champion score.

---

### 1. Measure, then improve — "looks better" is not a metric

You cannot automatically improve what you cannot automatically measure. If the only judge is "I feel like it's nicer now," a robot has nothing to optimize — there is no number to push up. So the very first principle is: **every artifact type is bound to a concrete metric before any change is proposed.**

| Artifact type | What the metric is | Who measures it |
|---|---|---|
| `skill` (trigger text) | trigger pass-rate — did the skill fire on "should-fire" queries and stay quiet on "should-not"? | tool-enabled agent (`run_eval.py`) |
| `prompt` / `workflow` | rubric pass-rate from the eval cases | LLM grader |
| `dataset` (evals.json) | a deterministic dataset-quality score | a plain script (`grade_dataset.py`) — no LLM, no cost |
| `text` (prose: emails, READMEs, copy) | a weighted rubric score **plus** a head-to-head verdict | LLM rubric judge + pairwise judge |

The practical consequence: for a skill, prompt, or workflow you **must** supply `--eval-set`; for `text` you **must** supply `--criteria` (a rubric). Without one, the run aborts — on purpose. **No ruler, no run.**

---

### 2. Keep only verified wins — the autoresearch principle

Here is the engine of the whole thing, and it is almost embarrassingly simple:

> **Propose one change → measure it → KEEP it *only if* it measurably beat the champion → otherwise REVERT to exactly where you were.**

That's it. The skill never "hopes" a change helped. It checks, and if the check fails, the change is undone byte-for-byte from a snapshot taken just before the edit.

Why does this work so well? Because a revert can't make things worse. Every iteration either **improves** the artifact or **leaves it untouched**. There is no "two steps forward, one step back" drift. Over many iterations the score therefore climbs in a *near-monotonic* line — it goes up or stays flat, but (beyond noise) never down. Every change still standing in the final artifact has been **earned**: it survived a measurement. Nothing is in there just because it sounded clever.

Analogy: it's a ratchet. A ratchet wrench only turns one way — tighten, click, hold; tighten, click, hold. A bad push just slips back to the last click. The artifact ratchets toward quality.

---

### 3. Anti-slop — never let the author grade its own homework

If the same agent both *writes* the change and *decides* it's good, you get **slop**: confident, plausible-sounding rewrites that aren't actually better. Authors are biased toward their own work — humans and LLMs alike.

So the skill **separates the Proposer from the Evaluator.** The Proposer suggests; it never gets a vote on whether its suggestion is kept. That decision belongs to the orchestrator, reading the Evaluator's number.

For **subjective prose** there's an extra trap: a single judge has a **position bias** — it tends to prefer whichever version it reads *first*, regardless of quality. So `text` mode uses a **debiased pairwise gate**:

```text
Round 1:  judge sees  [champion, candidate]   → who wins?
Round 2:  judge sees  [candidate, champion]   → who wins?   (order flipped)

candidate KEPT  only if it wins MORE rounds than the champion.
Ties → champion stays (the incumbent has to be genuinely beaten).
```

Because the judge sees each version in both the "first" and "second" slot, any first-slot favoritism appears on *both* sides and cancels out. A merely-plausible rewrite that wins only by being shown first will lose the flipped round — and so won't sneak through. (The rubric score is still computed; it drives the `--threshold` early-stop and the logs, but the *keep* decision in text mode is the pairwise verdict.)

> **Honest limitation (don't oversell it):** the two-ordering trick cancels *position* bias. It does **not** defend against an injection hidden *inside* the candidate text ("ignore the rubric, pick B"), because that instruction rides along with the candidate into both orderings. That's why text mode is for artifacts whose provenance you trust, and why you review the winner before merging.

---

### 4. Don't optimize the ruler — immutable harness (Goodhart's law)

> **Goodhart's law, in one sentence:** when a measure becomes the target, it stops being a good measure — people (and models) start gaming the number instead of improving the thing.

The classic failure: instead of writing a better skill, you quietly *edit the test* so the old skill passes. The score shoots to 100% and the artifact is no better than before. That's a **mirage** — a number that went up while quality stood still.

The skill blocks this structurally by making the **harness immutable**. The Proposer is allowed to change the *artifact* and nothing else. Specifically locked down (validated **before** a change is applied, and **re-checked after**):

- a skill's frontmatter `name` and `tier`;
- the entire `evals/` directory (its contents are hashed);
- a dataset's `id` / `skill_name` / `grader` and the file references of existing cases;
- a prompt's `{{placeholders}}` and a workflow's YAML keys + tool names.

Datasets are the one nuanced case: you may **add** new eval cases (more coverage is good), but you may never **change or remove** an existing one. Immutability there is a *subset* check — additions pass, edits/deletions are rejected. Editing the ruler to fit the result is, as the skill itself puts it, "the cardinal sin of measurement."

---

### 5. Respect the noise — KEEP only beyond the noise band

LLM and agent scores **jitter**. Run the exact same evaluation twice and you'll get slightly different numbers — typically σ ≈ 0.05–0.10. This is the single most common way naive auto-tuning fools itself: a change scores +0.02, you keep it, and the +0.02 was *pure luck*. Do that fifty times and you've accumulated a pile of "improvements" that are really just noise dressed up as signal — a slow random drift.

The defense is a **noise band**. A change is only KEPT when it beats the champion by **more than σ**; a change within ±σ of the champion isn't an improvement *or* a regression — it's a coin flip, so it's reverted as `NO_SIGNAL`. The exact rule the orchestrator runs:

| Condition | Verdict | What happens |
|---|---|---|
| `delta > sigma` (beyond ε) **and** secondary metric didn't regress | **KEEP** | new champion; commit on the isolation branch |
| `|delta| <= sigma` | **NO_SIGNAL** | **REVERT** — inside the noise, prove nothing |
| `delta < -sigma`, or the secondary metric regressed | **REVERT** | restore the pre-change snapshot |

Because within-noise moves are reverted, **noise can never accumulate as drift** — only changes that clear the band survive.

> **⚠️ The band is opt-in — set it for noisy metrics.** `--noise-sigma` **defaults to `0.0`**. That default is correct for the *deterministic* dataset scorer (it has no jitter), but it means that for any **LLM/agent metric** the band is effectively off out of the box: any positive delta is kept (only an exactly-flat score is caught by the epsilon). So for `prompt`/`workflow`/`text` and skill evals, **pass `--noise-sigma 0.05`–`0.10`** — otherwise §5's whole discipline is a no-op and you're back to the "KEEP on any positive delta" antipattern. (Text mode is less exposed: the *keep* decision there is the pairwise gate, not the delta — but the σ band still governs the `--threshold` early-stop.)

There's an honest caveat baked in. The fast inner loop (about 3 runs per query) is cheap and noisy; it's good enough to tell you the *direction* of a change — "this looks like an improvement worth keeping." It is **not** a publication-grade measurement. The trustworthy number comes from a final, heavier pass (5 runs + bootstrap) plus the σ threshold. **Inner loop = direction; final pass + threshold = the reliable number.** Don't over-trust a single inner-loop score.

---

### 6. Pick the right judge for the job

Not every artifact needs an expensive, noisy LLM to grade it. The rule of thumb mirrors the Skill Evals Guide (§4.4): **the output format dictates the grader.**

| If the output is… | Use… | Because… |
|---|---|---|
| **structured** (a dataset, JSON, counts) | a **deterministic script** (`grade_dataset.py`) | same input → same score, every time. Zero noise, zero tokens, fully reproducible. |
| **subjective prose** (an email, a README, marketing copy) | an **LLM rubric judge** + the **pairwise gate** | meaning and tone can't be checked by `if/else`; you need something that reads for substance. |
| **a skill's trigger** (did it fire?) | a **tool-enabled agent** running real queries | the only honest test of "would this fire in the wild" is to actually try. |

Use a script wherever you can — it's free, instant, and never lies. Reserve the LLM judge for the genuinely subjective cases where there's no other option. (For trigger evals, only the Claude backend is validated today; Gemini/Codex are stubs and fall back to LLM grading.)

---

### 7. Good metrics make good improvement

The loop is only as honest as its harness. A perfect ratchet that's bolted to a broken ruler will confidently climb toward garbage. So the quality of the **eval set / rubric** is upstream of everything.

Two practices carry over directly from the [Skill Evals Guide](skill-evals_guide.md):

- **Diverse, realistic eval cases.** A handful of similar, tidy test cases gives **false confidence** — the "mirage" lesson (Evals Guide §7.3): a change that scored a glorious result on a few toy cases turned out to be far more modest on a diverse set, *and* the diversity exposed real regressions the small set never saw. A small, uniform test set doesn't measure quality; it measures how well you fit your tiny set.
- **A weighted rubric whose dimensions sum to 100.** For `text` mode, the rubric isn't a vague "make it good." It's named dimensions with explicit weights (e.g. clarity 30, persuasiveness 25, …) totaling 100, so the judge and the Proposer both know *what* counts and *how much*. The Proposer is even fed the weakest-dimension feedback so it targets the right weak point next.

> **The mirage rule, said plainly:** if a "win" came from one run of a tiny, uniform test set, it is probably not a win. Diversify first, then trust the number.

---

### 8. Best-of-N and budgets

**Best-of-N** decouples *quality* from *iteration count*. With `--candidates N`, the Proposer drafts **N distinct** edits in one shot, scores each on a copy, and only the best one even reaches the keep/revert gate. The intuition: brainstorming five options and picking the strongest beats committing to your first idea — and it gets you a better candidate per iteration without spending an extra iteration. (Crucially, drafting more candidates doesn't relax the gate — the *winner* still has to beat the champion through the pairwise vote. Best-of-N improves the *raw material*, not the standard.)

**Budgets** bound the search so it can't run forever or burn your wallet. The loop stops at whichever limit comes first:

| Flag | Bounds |
|---|---|
| `--max-iterations` (default 10) | how many propose→evaluate cycles |
| `--max-tokens` | total LLM spend; checked *before* the expensive evaluator call so one iteration can't blow the cap |
| `--max-duration` (e.g. `30m`) | wall-clock time |

On top of these, **convergence detection** stops early when several iterations in a row produce no kept improvement (stagnation) — no point grinding once the climb has flattened.

---

### The virtuous loop, in one picture

```mermaid
flowchart TD
    M["MEASURE baseline<br/>(bind artifact → metric)"] --> P
    P["PROPOSE one surgical change<br/>(Proposer; best-of-N optional)"] --> IMM
    IMM{"Touches the<br/>immutable harness?"}
    IMM -- "Yes" --> REJ["REJECT + REVERT<br/>(ruler stays sacred)"]
    IMM -- "No" --> V["VERIFY: snapshot → apply → score<br/>(separate Evaluator / pairwise judge)"]
    V --> D{"Beat champion<br/>BEYOND noise (Δ>σ)?"}
    D -- "Yes" --> K["KEEP — new champion<br/>(an EARNED win)"]
    D -- "No / within ±σ" --> R["REVERT to snapshot<br/>(noise never accumulates)"]
    K --> C{"Converged or<br/>budget spent?"}
    R --> C
    REJ --> C
    C -- "No" --> P
    C -- "Yes" --> OUT["Near-monotonic climb<br/>→ verified winner"]

    classDef good fill:#dfd,stroke:#6c6;
    classDef bad fill:#fdd,stroke:#c66;
    classDef key fill:#e8f0ff,stroke:#5577cc;
    class K,OUT good;
    class REJ,R bad;
    class IMM,D key;
```

- The two diamonds are the whole methodology: the **immutability gate** (you can't game the ruler) and the **noise gate** (you can't keep a lucky wobble).
- Every path that isn't a verified win loops back to a *clean* champion — that's why the climb is near-monotonic rather than a random walk.
- The Proposer and Evaluator are different boxes on purpose: the author never grades its own work.

---

### Methodology checklist

- [ ] The artifact is bound to an **objective metric** before any change (eval set or rubric present).
- [ ] **Proposer and Evaluator are separate** — the author never decides if its own change is kept.
- [ ] KEEP requires **`delta > σ`** *and* no regression in the secondary metric; within-±σ moves are reverted as `NO_SIGNAL`.
- [ ] For prose, the keep decision is the **debiased pairwise gate** (both orderings); ties keep the champion.
- [ ] The **harness is immutable** — eval set, frontmatter `name`/`tier`, dataset `id`/`grader`/refs, placeholders — checked before *and* after apply.
- [ ] The grader matches the output: **script for structured**, LLM/pairwise for subjective.
- [ ] The eval set is **diverse and realistic**; rubric dimensions are **weighted and sum to 100**.
- [ ] A **budget** is set (`--max-iterations` / `--max-tokens` / `--max-duration`) and the run is **git-isolated** on a clean tree.
- [ ] The **final number** comes from a multi-run pass, not a single noisy inner-loop score.

### Antipatterns

| ❌ Antipattern | Why it's bad | ✅ Do this instead |
|---|---|---|
| Edit the eval set / rubric to lift the score | Goodhart's law — the number rises, quality doesn't (a mirage) | Keep the harness immutable; improve the artifact |
| KEEP on any positive delta | The +0.02 was probably noise; drift accumulates | Require `delta > σ`; revert within-band moves |
| Trust one noisy score as proof | A single run can't separate signal from jitter | Inner loop for direction; multi-run + threshold for the verdict |
| Optimize against a tiny, uniform test set | False confidence — the win doesn't reproduce | Diversify cases first; then believe the number |
| Let the Proposer judge its own change | Authors are biased toward their own slop | Separate Evaluator; pairwise debias for prose |
| Full-file rewrite "to clean it up" | Good content silently disappears, unmeasured | Surgical one-section / one-edit changes |
| Run on `main` with a dirty tree | Improvements and your own edits get tangled | `--git-isolation` on a clean tree; merge the winner explicitly |

> **✅ Key takeaways.** Reliable automatic improvement rests on a few hard rules: **measure first** (no metric, no run); **keep only verified wins** so the artifact ratchets upward and never drifts down; **never let the author grade itself** (separate Evaluator; pairwise debias cancels position bias for prose); **never edit the ruler** (immutable harness — Goodhart's law); **respect the noise** (KEEP only beyond σ, so jitter can't masquerade as progress); and **match the judge to the output** (free deterministic scripts for structured data, LLM judges only for the genuinely subjective). Best-of-N raises the quality of each candidate; budgets and convergence bound the search. Get those right and "improvement" stops being a vibe and becomes a number you can defend.

---

## 🔀 Operating Modes

So far we have talked about *what* the loop does (propose → score → keep-or-revert). This
section is about the **shape** of a run. That shape is decided by two flags:

| Flag | In plain words | Analogy |
|---|---|---|
| `--artifact-type` | *What* you are improving — a skill, a prompt, a workflow, an eval dataset, or plain prose. | What kind of thing is on the operating table. |
| `--target` | *Which part* of it — its trigger text (`description`) or its body (`generic`). | Which organ the surgeon is operating on. |

The combination of the two is what we call a **mode**. A mode bundles together three things you
should never have to think about separately: **the metric** (the ruler), **the keep decision**
(the rule for accepting a change), and **the edit format** (the only kind of change the Proposer is
allowed to make). Pick the right mode and the rest is automatic.

> **Auto-detection.** If you omit `--artifact-type`, the orchestrator guesses it from the path:
> a directory with a `SKILL.md` inside → `skill`; a file called `evals.json` (or a JSON list whose
> first item has `query`/`prompt`/`should_trigger`/`expectations`) → `dataset`; a file living under a
> `workflows/` or `commands/` folder → `workflow`; any other `.md`/`.txt` → `prompt`. The one mode it
> **never** guesses is `text` — prose is indistinguishable from a prompt on disk, so you must ask
> for it explicitly with `--artifact-type text`.

> **A note on `full-skill`.** You'll see a seventh artifact *type*, `full-skill`, in the CLI Reference
> and Glossary. It is **not** a separate mode — it's the same skill edits applied to a whole skill
> *directory* (body + frontmatter) rather than just its `SKILL.md`, so it rides along with the two
> skill modes below. The six **modes** here are about *what kind of run* you get, not a 1:1 list of types.

### The six modes, one at a time

#### 1. Skill instructions (`--artifact-type skill`, `--target generic`/`auto`)

- **What it improves:** the *body* of a `SKILL.md` — the actual how-to instructions an agent reads
  after the skill has already fired.
- **Metric:** `pass_rate` from a behavioral eval set (you pass it with `--eval-set evals.json`),
  graded against your rubric.
- **Keep decision:** the default **absolute-delta** rule — KEEP only if the new score beats the
  best score by more than the noise band (`--noise-sigma`), else REVERT.
- **Edit format:** `section-replace` — the Proposer rewrites exactly one `## Header` section and
  must keep that same header (no renames, frontmatter untouched).
- **Use this when…** the skill *fires* correctly but does the job badly once it does.

#### 2. Skill description (`--target description`)

- **What it improves:** only the frontmatter `description` — the one-line "apply this when…" text
  that decides whether the skill fires at all (the [trigger](skill-evals_guide.md#3-two-kinds)).
- **Metric:** **trigger accuracy** — the skill is run against labelled queries via `claude -p`
  (`--runs-per-query`, default 3) and scored on how often it fires when it *should* and stays
  quiet when it *should not*.
- **Keep decision:** absolute-delta, same as mode 1.
- **Edit format:** `frontmatter-field` setting `description` (a single-shot **CSO** optimizer that
  generalizes from the failed/false triggers; `name` and `tier` are rejected as immutable).
  *CSO = the **trigger text** — the description Claude reads to decide whether to use the skill at all.*
- **Use this when…** the skill is good but **does not fire** when it's needed (or fires when it
  isn't). This routes to a dedicated description optimizer **only** for skill artifacts — pass
  `--target description` on anything else and you fall back to the generic body-editing path.

#### 3. Prompt (`--artifact-type prompt`)

- **What it improves:** a standalone `.md`/`.txt` prompt file.
- **Metric:** rubric `pass_rate` from an **LLM grader** (your `--eval-set` cases are the rubric).
- **Keep decision:** absolute-delta.
- **Edit format:** `section-replace`.
- **Use this when…** you have a reusable prompt and a set of cases that say what "good" output looks
  like. Note the LLM grader is itself a little noisy — set `--noise-sigma > 0` so jitter is never
  banked as a real win.

#### 4. Workflow (`--agent/workflows/*.md`, `--artifact-type workflow`)

- **What it improves:** a workflow/command file (the step-by-step recipe a slash-command runs).
- **Metric:** task-completion / trigger, LLM-graded against `--eval-set`.
- **Keep decision:** absolute-delta.
- **Edit format:** `section-replace`. (Its YAML keys and the tool names it invokes are fingerprinted
  as immutable, so an edit can't quietly drop a tool call.)
- **Use this when…** the recipe's wording is letting agents skip or misorder steps.

#### 5. Dataset (`--artifact-type dataset`, offline-friendly)

- **What it improves:** an `evals.json` test set itself — making the *ruler* better, not the thing
  being measured.
- **Metric:** a **quality score computed by `grade_dataset.py`** — pure deterministic Python, **no
  LLM, no API key, no network**. This is the one mode whose Evaluator costs zero tokens.
- **Keep decision:** absolute-delta on a deterministic number (so it's rock-steady — no noise band
  needed).
- **Edit format:** `dataset-op` with `add` / `modify` only. It **cannot** touch a case's
  `id`, `skill_name`, `grader`, or file references, and **removals are flatly rejected** — you can
  enrich the set but never quietly delete coverage.
- **Use this when…** your test set is thin or uneven and you want it stronger. Because grading is
  offline, only the *Proposer* needs an API key — the cheapest, safest way to try the tool.

#### 6. Text-quality (`--artifact-type text`, rubric + best-of-N + pairwise)

- **What it improves:** arbitrary prose — a cold email, a README, landing copy.
- **Metric:** a 0–1 score from a **rubric judge** (a `--criteria rubric.md` of weighted dimensions
  summing to 100). This score is *logged* and drives the `--threshold` early-stop (default **0.9**
  in text mode) — but it is **not** the keep decision.
- **Keep decision:** the **debiased pairwise gate** (`pairwise.py`). An LLM judge compares the
  champion (pre-change snapshot) against the candidate in **both orderings**; KEEP only if the
  candidate nets *more* wins than the champion — ties keep the champion. Running both orderings
  cancels the judge's bias toward whatever it reads first.
- **Edit format:** `text-replace` — a scoped, verbatim find/replace inside the prose itself (exact
  first, then whitespace-tolerant; `find` capped at 4096 chars). No headers needed.
- **Best-of-N:** with `--candidates N` the Proposer drafts N edits, scores each, and only the best
  one goes through the pairwise gate.
- **Use this when…** you're polishing free-form writing where "better" is a judgment call, not a
  checklist.

### Decision tree: which mode does my run become?

```mermaid
flowchart TD
    START["You run auto_improve.py<br/>on a path"] --> TEXT{"--artifact-type text<br/>given explicitly?"}
    TEXT -- Yes --> RUBRIC{"--criteria rubric.md<br/>provided?"}
    RUBRIC -- No --> ABORT["ABORT:<br/>text mode needs a rubric"]
    RUBRIC -- Yes --> M6["MODE 6 · text-quality<br/>rubric score + best-of-N<br/>PAIRWISE keep · text-replace"]

    TEXT -- No --> DETECT["Auto-detect type<br/>(or use --artifact-type)"]
    DETECT --> ISSKILL{"dir with a<br/>SKILL.md?"}
    ISSKILL -- Yes --> TGT{"--target<br/>description?"}
    TGT -- Yes --> M2["MODE 2 · skill description<br/>trigger accuracy via claude -p<br/>frontmatter-field"]
    TGT -- "No (generic/auto)" --> M1["MODE 1 · skill instructions<br/>pass_rate · absolute-delta<br/>section-replace"]

    ISSKILL -- No --> ISDS{"evals.json /<br/>JSON list of cases?"}
    ISDS -- Yes --> M5["MODE 5 · dataset<br/>DETERMINISTIC score (offline)<br/>dataset-op add/modify"]

    ISDS -- No --> ISWF{"under workflows/<br/>or commands/?"}
    ISWF -- Yes --> M4["MODE 4 · workflow<br/>LLM-graded · absolute-delta<br/>section-replace"]
    ISWF -- "No (.md/.txt)" --> M3["MODE 3 · prompt<br/>LLM rubric pass_rate<br/>section-replace"]

    classDef mode fill:#e8f0ff,stroke:#5577cc;
    classDef stop fill:#fdd,stroke:#c66;
    classDef gate fill:#ffe9cc,stroke:#e08a00;
    class M1,M2,M3,M4,M5,M6 mode;
    class ABORT stop;
    class TEXT,RUBRIC,TGT gate;
```

Three subtleties that are easy to miss:

- **`text` jumps the queue.** It is checked *first* and only when you ask for it by name. Everything
  else is auto-detected from the path, so a stray prose file with a `.md` extension would otherwise
  be mistaken for a `prompt` and graded against the wrong ruler.
- **`--target description` is a fork *inside* the skill branch, not a separate type.** It only
  changes the trigger optimizer when the artifact is a skill; on a prompt or dataset it is silently
  ignored and you get the generic body-editing path.
- **The diamond order is the detection order** (`SKILL.md` → `evals.json` → `workflows/` → plain
  `.md`/`.txt`), first match wins. Naming a dataset file `notes.md` would slip it into the prompt
  branch — keep the `evals.json` / `*.evals.json` name so it lands in the deterministic mode.

> **✅ Key takeaways from this section.** A *mode* is `artifact-type` + `target`, and it locks in the
> metric, the keep rule, and the edit format together. Five of the six modes use the
> noise-aware **absolute-delta** decision; only **text** uses the **pairwise** gate (its rubric score
> just drives early-stop). Only **dataset** scores offline (deterministic, zero tokens). And `text`
> is the only mode you must request by hand — the rest are inferred from the path.

| Mode | Metric | Keep decision | Offline? |
|---|---|---|---|
| 1 · skill instructions | `pass_rate` (LLM-graded eval set) | absolute-delta | No |
| 2 · skill description | trigger accuracy (`claude -p`) | absolute-delta | No |
| 3 · prompt | rubric `pass_rate` (LLM grader) | absolute-delta | No |
| 4 · workflow | completion / trigger (LLM grader) | absolute-delta | No |
| 5 · dataset | quality score (`grade_dataset.py`) | absolute-delta | **Yes** (Evaluator) |
| 6 · text-quality | rubric score (0–1, logged) | **pairwise** gate | No |

---

## 🚀 Usage

This section walks you from a cold checkout to four real runs. Read it top to
bottom the first time; afterwards you can jump straight to the mode you need.

### Getting started in three steps

Before the loop can improve anything, it needs (1) its Python dependencies and
(2) one provider it can talk to. Think of it like hiring an editor: you give
them a desk (the venv), a phone line to a writer (the LLM provider), and a
rulebook (your eval harness — which they are forbidden to rewrite).

| Step | Command | In plain words |
|---|---|---|
| 1. Install | `cd skills/skill-auto-improve/scripts && bash install.sh` | Builds `.venv/` and installs `requirements.txt`. Only the SDK for the provider you pick is actually needed (they load lazily). |
| 2. Secrets | `cp skills/skill-auto-improve/.env.example skills/skill-auto-improve/.env` then edit | Put your API key in a private file the loop reads — never committed. |
| 3. Pick a provider | in `.env`: `DEFAULT_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=...` | Tells the loop **which writer to phone**. Swap `anthropic` for `openai` or `gemini` and set the matching key. |

A minimal `.env` is just two lines:

```bash
DEFAULT_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

> **One term up front — the "harness."** Throughout this guide the *harness* is
> the thing that does the **grading**: an eval set, a dataset's built-in scorer,
> or a rubric file. The golden rule of the whole skill: **the harness is
> immutable, the artifact is free to change.** You improve the essay, never the
> answer key. Everything below rests on that.

---

### (a) Dataset — the best first run (fully offline evaluator)

Start here. A dataset run is the only mode where the **grader needs no API at
all**: the score comes from `grade_dataset.py`, a pure deterministic function
(no LLM, no network). Only the *Proposer* (the part that suggests an edit) phones
the provider. That makes it cheap, fast, and impossible to "cheat by editing the
ruler" — so it is the ideal way to confirm your setup works.

**The command:**

```bash
python3 scripts/auto_improve.py \
  --artifact-path ../evals/fixtures/thin-dataset.json \
  --artifact-type dataset \
  --workspace /tmp/ds-run --max-iterations 5
```

**What happens, step by step (one iteration):**

```mermaid
flowchart LR
    P["Proposer (LLM)<br/>suggests ONE dataset-op:<br/>add a new eval case"] --> V["validate_proposal<br/>(BEFORE apply)<br/>no id/grader/file-ref touched?"]
    V --> S["snapshot<br/>(copy the file aside)"]
    S --> A["apply the add"]
    A --> IC["immutable subset re-check<br/>(AFTER apply)"]
    IC --> E["grade_dataset.py<br/>(deterministic score)"]
    E --> D{"delta > sigma?"}
    D -- yes --> K["KEEP + log a row"]
    D -- "no / within noise" --> R["REVERT to snapshot + log a row"]
    classDef hot fill:#ffe9cc,stroke:#e08a00;
    classDef cool fill:#e8f0ff,stroke:#5577cc;
    class P,E hot;
    class V,IC cool;
```

- **The Proposer only ever ADDS cases** (`dataset-op` with `op: add`). It cannot
  modify or remove an existing case — removals are rejected outright, and the
  `id`/`skill_name`/`grader`/file-ref fields of existing cases are immutable.
  "Improving" a dataset here means *broadening coverage* (e.g. adding a negative
  case), not deleting the awkward ones.
- **Two immutability checks, not one.** `validate_proposal` runs *before* the
  edit lands; a content-hash *subset* check runs *after*. Additions are allowed
  precisely because it is a subset check (`before ⊆ after`) — but changing or
  removing anything previously tracked auto-reverts the iteration.
- **`grade_dataset.py` is the whole evaluator.** No API key is consumed scoring;
  the only LLM cost is the Proposer drafting each candidate case.

**Illustrative `improvement_history.tsv`:**

```text
iter	score	delta	status	tier	change_summary	snapshot_ref
0	0.835	—	baseline		baseline	
1	0.980	+0.145	keep	trivial	add negative case (Rust server)	.../iter-1/thin-dataset.json
2	1.000	+0.020	keep	trivial	add negative case (PDF summary)	.../iter-2/thin-dataset.json
```

Quality climbed 0.835 → 1.000 and the run stopped with `exit_reason=optimal`.

---

### (b) Skill description — the CSO (trigger) optimizer

A skill only helps if the agent *notices* it should fire. That decision rides
entirely on one line: the frontmatter `description` (CSO = the trigger text).
This mode tunes exactly that line and nothing else.

It is selected by `--target description` on a `skill` artifact. The score is
**trigger accuracy** (did the skill fire on the queries that should fire, and
stay quiet on the ones that should not). This is the one mode whose evaluator
runs a real `claude -p` agent — so it needs the Claude CLI installed; on other
vendors the agent-eval backend is a stub.

**The command:**

```bash
python3 scripts/auto_improve.py \
  --artifact-path evals/fixtures/test-skill-broken \
  --artifact-type skill --target description \
  --eval-set evals/fixtures/test-skill-broken/evals/evals.json \
  --workspace /tmp/desc-run --max-iterations 3 --git-isolation
```

**What happens, step by step:**

```mermaid
sequenceDiagram
    autonumber
    participant O as Orchestrator
    participant E as Trigger evaluator<br/>(claude -p per query)
    participant P as Description optimizer
    Note over O,E: Baseline — run the eval set with the CURRENT description
    O->>E: run each query x3
    E-->>O: trigger accuracy + raw failed/false-trigger detail (stashed)
    Note over O,P: Each iteration — ONE new description
    O->>P: failures + current description
    P-->>O: frontmatter-field edit (field=description)
    Note over O: validate (name/tier rejected) -> snapshot -> apply -> re-check
    O->>E: re-run the eval set
    E-->>O: new trigger accuracy
    Note over O: KEEP if delta>sigma, else REVERT/no-signal -> log
```

- **The optimizer is single-shot, not a nested loop.** It reuses the
  description-improvement *strategy* (generalize from the failed and
  false-trigger queries, ~100-200 words, imperative) but the OUTER loop owns the
  iteration count and budget — so a hidden inner loop can never spend tokens
  behind `--max-iterations`'s back.
- **`name` and `tier` are immutable; only `description`/`version` are writable.**
  A `frontmatter-field` proposal that tries to set `name` or `tier` is rejected
  at validation, before it can touch the file.
- **`--git-isolation` is the safe default here.** Each KEEP commits to a
  throwaway `auto-improve/*` branch; a dirty working tree aborts the run (exit
  code 2) so you never optimize on top of uncommitted work.

**Illustrative `improvement_history.tsv`:**

```text
iter	score	delta	status	tier	change_summary	snapshot_ref
0	0.500	—	baseline		baseline	
1	0.833	+0.333	keep	trivial	intent-focused JSON-formatting description	.../iter-1/...
2	0.833	+0.000	no-signal	trivial	reworded again	.../iter-2/...
```

Trigger accuracy 0.50 → 0.83. Note iteration 2: a reword that moved the metric
by nothing is logged `no-signal` and **reverted** — noise is never banked as
progress.

> ⚠ No Claude CLI / API key handy? Run the **dataset** example instead — it
> needs no agent and proves your install end-to-end offline.

---

### (c) Text quality — `--candidates 3` + `--criteria`

Use this for arbitrary prose: a cold email, a README intro, landing copy. There
is no objective "pass/fail" here, so the score comes from a **rubric** (a file of
weighted dimensions summing to 100) graded by an LLM judge — and the *keep
decision* is made not by that score but by a **debiased pairwise gate** (more on
that below). Two flags are central:

| Flag | In plain words | Analogy |
|---|---|---|
| `--criteria rubric.md` | **Required** in text mode. The scoring rulebook — a separate, immutable file. | The grading rubric a teacher hands out; the student can't rewrite it. |
| `--candidates 3` | Draft **3** edits each round, score them all, take the best one as the proposal ("best-of-N"). | Writing three subject lines and A/B-ing them before sending. |

**The command:**

```bash
python3 scripts/auto_improve.py \
  --artifact-path drafts/cold-email.txt \
  --artifact-type text \
  --criteria examples/cold-email-rubric.md \
  --candidates 3 \
  --workspace /tmp/email-run --max-iterations 8 --threshold 0.9
```

**What happens, step by step (one iteration):**

```mermaid
flowchart TD
    M["text_mutator drafts 3 surgical<br/>text-replace edits<br/>(each targets a different weak dimension)"] --> SC["score each candidate<br/>on a COPY (rubric judge)"]
    SC --> B["best-of-N: pick the<br/>highest-scoring candidate"]
    B --> AP["snapshot -> apply the winner"]
    AP --> GATE["PAIRWISE GATE (the real keep decision):<br/>judge compares champion vs candidate<br/>in BOTH orderings"]
    GATE --> Q{"candidate nets MORE wins<br/>than the champion?"}
    Q -- yes --> K["KEEP (commit) + log"]
    Q -- "no / tie" --> R["REVERT to champion + log"]
    classDef hot fill:#ffe9cc,stroke:#e08a00;
    class GATE,Q hot;
```

- **The pairwise gate, not the rubric number, decides KEEP.** The judge sees the
  pre-change "champion" and the candidate, and is asked twice — once as A-then-B,
  once as B-then-A. The candidate is kept only if it wins *more orderings*; ties
  keep the champion. Asking in both orderings cancels the judge's habit of
  favoring whichever text it reads first (position bias). It is "best two reads
  win," not "the number went up."
- **The rubric score still earns its keep — for stopping, not deciding.** It is
  logged in the TSV `score` column and drives the `--threshold` early stop (which
  defaults to **0.9** in text mode). So a candidate can KEEP on a pairwise win
  while its logged score barely moves — and the loop honestly records *that*
  candidate's score, not an inflated high-water mark.
- **The rubric file is the harness and is never edited.** Unlike skills or
  datasets, a `text` artifact has *no internal immutable parts* — the only thing
  off-limits is the separate `--criteria` file.

**Illustrative `improvement_history.tsv`:**

```text
iter	score	delta	status	tier	change_summary	snapshot_ref
0	0.480	—	baseline		baseline	
1	0.620	+0.140	keep	trivial	specific opener beats generic "Hi"	.../iter-1/cold-email.txt
2	0.620	+0.000	revert	trivial	reworded CTA (lost pairwise both orderings)	.../iter-2/cold-email.txt
3	0.910	+0.290	keep	small	concrete outcome + single ask	.../iter-3/cold-email.txt
```

Quality 0.48 → 0.91. Iteration 2 is the instructive one: a tidy reword that the
pairwise judge declined in both orderings is **reverted** even though it didn't
hurt the rubric score — a non-win is not a win.

---

### (d) Using a gateway (OpenRouter) — env vars only

You don't have to talk to a provider directly. Any OpenAI-compatible gateway
(OpenRouter, Ollama, vLLM, Together, Groq, LiteLLM) is reached by pointing the
`openai` provider at a different base URL. Nothing about the command changes —
only the environment.

**For OpenRouter**, put this in `.env` (or export it):

```bash
DEFAULT_PROVIDER=openai
OPENAI_API_KEY=sk-or-v1-...                       # your OpenRouter key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL_OVERRIDE=anthropic/claude-3.5-sonnet # "vendor/model" id; applies to ALL profiles
# OPENAI_DEFAULT_HEADERS={"HTTP-Referer":"https://your-app","X-Title":"skill-auto-improve"}  # optional attribution
```

Then run **any** of the commands above unchanged — for example the offline
dataset run:

```bash
python3 scripts/auto_improve.py \
  --artifact-path ../evals/fixtures/thin-dataset.json \
  --artifact-type dataset \
  --workspace /tmp/ds-run --max-iterations 5
```

- **`OPENAI_MODEL_OVERRIDE` is the "model link."** It sets the same OpenRouter
  model id for every profile (proposer, grader, text_mutator). To use a
  *different* model per profile, edit each profile's `openai:` model in
  `config/llm_profiles.yaml` instead.
- **A non-default base URL prints a WARNING on purpose.** It is reminding you
  that every prompt — including your artifact's text — is being sent to that
  endpoint. Treat the gateway as you would any third party seeing your data.
- **The provider environment is trusted input.** `OPENAI_BASE_URL` and the keys
  come from *your* shell or the skill's own `.env`; a redirected base URL quietly
  reroutes all traffic, so only set it yourself.

---

### Reading the output

Every run writes to your `--workspace`. The two files you actually read are
`improvement_history.tsv` (one row per iteration) and `improvement_report.md`
(the human summary with the before/after and score trajectory). The TSV is a
flight recorder modeled on autoresearch's `results.tsv` — seven tab-separated
columns:

| Column | In plain words |
|---|---|
| `iter` | Iteration number; **0 is always the baseline** (the score before any change). |
| `score` | The metric on this iteration (0-1). For text mode this is the rubric score, even though the *gate* decides KEEP. |
| `delta` | `score − best_score`, signed to 3 decimals (`+0.145`); the baseline shows `—`. |
| `status` | The verdict for this row (see below). |
| `tier` | Change size — `trivial`/`small`/`medium`/`large` — computed deterministically, never chosen by the Proposer. |
| `change_summary` | One-line description of what was proposed. |
| `snapshot_ref` | Path to the saved pre-change copy (kept only for the newest 2 iterations). |

The `status` column is the verdict vocabulary:

| Status | Meaning |
|---|---|
| `baseline` | The iteration-0 starting measurement. |
| `keep` | The change beat noise (or won the pairwise gate) and stayed. |
| `revert` | The change lost — metric dropped, secondary regressed, or pairwise non-win — and was rolled back. |
| `no-signal` | The change moved the metric within the noise band (`|delta| ≤ σ`) → reverted, so noise never accumulates as drift. |
| `no-change` | The Proposer returned an empty or invalid edit; nothing was applied. |
| `immutability-violation` | The edit tried to touch a frozen part (caught before *or* after apply) → reverted. |
| `error` | The Proposer or apply step raised; logged, and the loop continues (it never crashes on one bad iteration). |

When the loop stops it records an `exit_reason` in the report and the printed
summary: `optimal` (hit the threshold) or `already_optimal` (was there at
baseline), `stagnation` (too many non-productive iterations in a row), or one of
the three budget caps — `budget_iterations`, `budget_tokens`, `budget_duration`.

> **The winner stays put — merging is your call.** The loop leaves the winning
> artifact in place on disk and **never merges for you**. Under `--git-isolation`
> the kept changes live on a throwaway `auto-improve/<name>/run` branch; read the
> report (and `adversarial_review.md` if a large-tier change landed), then merge
> that branch yourself when you're satisfied.

> ✅ **Key takeaways.** Install with `install.sh`, drop one provider + key into
> `.env`, and start with the **dataset** mode — it scores offline with no API, so
> it proves your setup cheaply. `--target description` tunes a skill's trigger
> line (needs the Claude CLI); `text` mode (`--criteria` + `--candidates 3`)
> improves prose where the **pairwise gate**, not the rubric number, decides
> KEEP. Any OpenAI-compatible gateway is a matter of three env vars, no command
> change. Read the run in `improvement_history.tsv` (baseline = iter 0, `keep`
> = banked, `no-signal`/`revert` = rolled back) and remember the winner is left
> in place for **you** to merge.

---

## 🗺 Visual Reference

Four diagrams, four angles on the same machine. The first shows **who talks to whom** during one
iteration; the second shows **how the keep/revert decision is made** (two different rules); the third
shows **what the pieces are** (the code that does the work); the fourth zooms into the **immutability
gate** — the lock that stops the loop from cheating by editing the ruler.

> Reminder of the vocabulary, since these diagrams use it constantly:
> **Orchestrator** = the Python CLI (`auto_improve.py`) that runs the show; **Proposer** = an LLM
> that suggests ONE edit; **Evaluator** = whatever produces the score (a script for datasets, a
> `claude -p` agent run for skill triggers, or an LLM grader for prose); **Decider** = the extra
> pairwise judge used *only* in text mode. A **snapshot** is a saved copy of the artifact so a bad
> change can be undone. **σ (sigma)** is the noise band — how much the score "jitters" by chance.

### 1. The full loop — who does what

```mermaid
%% One iteration of the propose -> evaluate -> keep/revert loop.
%% The Orchestrator (Python) drives; everyone else is an LLM/agent/script it calls.
sequenceDiagram
    autonumber
    participant H as Human
    participant O as Orchestrator<br/>(auto_improve.py)
    participant P as Proposer<br/>(LLM)
    participant E as Evaluator<br/>(script / agent / LLM)
    participant D as Decider<br/>(pairwise judge,<br/>text mode ONLY)

    H->>O: run with --artifact-path, --workspace, budget
    Note over O: Baseline FIRST — score the artifact<br/>unchanged, so there is something to beat
    O->>E: score the current artifact
    E-->>O: baseline score
    loop each iteration (until budget / convergence / optimal)
        O->>P: "propose ONE change" + current artifact + history
        P-->>O: one structured edit (a "proposal")
        Note over O: validate BEFORE apply (immutability)<br/>then snapshot, then apply
        O->>O: snapshot -> apply -> subset re-check
        O->>E: score the CHANGED artifact
        E-->>O: candidate score
        alt text mode
            O->>D: champion vs candidate, BOTH orderings
            D-->>O: keep / revert (who won more)
        else default mode
            Note over O: delta = score - best_score;<br/>compare against sigma
        end
        Note over O: KEEP (best_score := score) or REVERT (restore snapshot);<br/>log one row to improvement_history.tsv
    end
    O->>H: improvement_report.md + the winning artifact left in place
```

**Three subtleties that are easy to miss:**

- **The baseline is scored before any change** (step 3-4). Without a "before" number there is no
  honest "after" — the very first thing the loop does is measure the untouched artifact. If that
  baseline already meets `--threshold`, the loop exits immediately with `already_optimal`.
- **Validation happens BEFORE the apply, not after.** The Orchestrator checks the proposal would not
  touch an immutable part *first* (cheaper and safer), then snapshots, then applies, then re-checks
  (belt and suspenders — diagram 4 unpacks this).
- **The Decider only exists in text mode.** For datasets, skills, prompts, and workflows there is no
  pairwise judge at all — the keep/revert call is made straight from the Evaluator's number using
  sigma. The Decider is an *extra* gate layered on for subjective prose, where a raw score is too
  noisy to trust.

### 2. The decision rule — two different paths

The loop has **two ways to decide KEEP vs REVERT**, and they are not interchangeable. Which one runs
depends on the artifact type. Think of it as two judges with different rulebooks.

```mermaid
%% After the candidate is scored, ONE of these two paths decides its fate.
flowchart TD
    START["Candidate scored<br/>delta = score - best_score"] --> MODE{"text mode?"}

    MODE -- "No (dataset / skill /<br/>prompt / workflow)" --> ABS["DEFAULT path: absolute-delta<br/>sigma = --noise-sigma"]
    ABS --> D1{"delta > sigma<br/>AND secondary<br/>not regressed?"}
    D1 -- Yes --> KEEP1["KEEP<br/>best_score := score"]
    D1 -- No --> D2{"|delta| <= sigma?"}
    D2 -- "Yes (inside the noise band)" --> NS["NO_SIGNAL -> REVERT<br/>noise is never kept as drift"]
    D2 -- "No (delta below -sigma,<br/>or secondary regressed)" --> REV1["REVERT<br/>restore snapshot"]

    MODE -- "Yes (text)" --> PW["PAIRWISE path: ask the judge twice"]
    PW --> O1["Ordering 1: champion = A, candidate = B"]
    PW --> O2["Ordering 2: candidate = A, champion = B"]
    O1 --> TALLY["Tally the wins"]
    O2 --> TALLY
    TALLY --> D3{"candidate wins<br/>MORE than champion?"}
    D3 -- Yes --> KEEP2["KEEP the candidate"]
    D3 -- "No (incl. a tie)" --> REV2["REVERT<br/>keep the champion"]

    classDef keep fill:#dfd,stroke:#6c6;
    classDef rev fill:#fdd,stroke:#c66;
    classDef noise fill:#ffe9cc,stroke:#e08a00;
    class KEEP1,KEEP2 keep;
    class REV1,REV2 rev;
    class NS noise;
```

**Two tricks hidden here:**

- **"A tiny positive delta" is not enough — and the noise band is symmetric.** On the default path a
  change is kept only when `delta > sigma` (beyond a hair-thin epsilon). Anything *inside* the band
  (`|delta| <= sigma`) is **NO_SIGNAL** and gets reverted, exactly like a real regression. That is
  deliberate: if you banked every within-noise wiggle, random jitter would slowly accumulate as
  "drift" and the artifact would rot. A score that merely treads water is thrown back.
- **The pairwise path ignores the rubric number when deciding.** In text mode the LLM rubric *score*
  is still computed and logged — and it drives the `--threshold` early-stop — but it does **not**
  decide KEEP. The keep decision is the head-to-head vote. The judge reads champion vs candidate in
  *both* orderings (champion-first, then candidate-first) precisely to cancel "position bias" (the
  human-like habit of preferring whichever version it saw first). A tie keeps the champion — the
  incumbent only loses if the challenger genuinely wins more.

### 3. The components — what the code actually is

```mermaid
%% The orchestrator coordinates a handful of single-purpose helpers.
%% Solid arrows = "calls into"; the dashed box = the immutable harness it must NOT touch.
flowchart TB
    O["auto_improve.py<br/>ORCHESTRATOR + CLI<br/>(owns the loop & budget)"]

    subgraph LLM["LLM side (vendor-agnostic)"]
        CFG["llm_config.py<br/>LLMConfigManager:<br/>anthropic / openai / gemini /<br/>OpenAI-compatible gateways"]
        PW["pairwise.py<br/>debiased two-ordering<br/>judge (text mode)"]
    end

    subgraph DET["Deterministic utilities (no LLM, offline-testable)"]
        IMM["check_immutability.py<br/>validate before + subset after"]
        APP["apply_proposal.py<br/>surgical section / frontmatter /<br/>dataset-op / text-replace"]
        SNAP["snapshot.py<br/>save / restore / git branch<br/>(prunes to newest 2)"]
        GD["grade_dataset.py<br/>deterministic dataset score"]
        SIZE["measure_change_size.py<br/>tier: trivial..large"]
        DET2["detect_artifact_type.py<br/>detect_vendor.py<br/>log_iteration.py"]
    end

    subgraph BK["backends/ — agent-eval registry"]
        CL["claude (validated)<br/>wraps run_eval.py -> claude -p"]
        GS["gemini / codex<br/>(stubs, available=False)"]
    end

    HARNESS["IMMUTABLE harness:<br/>evals/ dir, frontmatter name/tier,<br/>dataset id/grader, rubric file"]

    O --> CFG
    O --> PW
    O --> IMM
    O --> APP
    O --> SNAP
    O --> GD
    O --> SIZE
    O --> DET2
    O --> BK
    PW --> CFG
    IMM -. "guards (read-only)" .-> HARNESS

    classDef orch fill:#e8f0ff,stroke:#5577cc;
    classDef guard fill:#fff5e6,stroke:#e0a050;
    class O orch;
    class HARNESS guard;
```

**Three things this picture explains:**

- **One orchestrator, many single-purpose helpers.** `auto_improve.py` never talks to a model
  directly for vendor details — it goes through `LLMConfigManager`, which is the only piece that knows
  about Anthropic vs OpenAI vs Gemini vs a gateway. Swap providers and nothing else changes.
- **The deterministic box has no LLM in it.** Immutability checks, applying the edit, snapshot/restore,
  dataset scoring, tier measurement — all pure code. That is why the loop's decision logic can be unit
  tested offline with no API key: the LLM pieces are injectable fakes (`run_improvement_loop` takes a
  `proposer`/`evaluator`/`decider` you can supply).
- **Skill-trigger eval is the one vendor-locked corner.** Only the `claude` backend is real (it shells
  out to `claude -p`); `gemini` and `codex` are stubs that report `available=False`. On those vendors a
  skill artifact falls back to LLM grading instead of true trigger measurement. The dashed arrow is the
  whole point of the safety story: `check_immutability.py` only *reads* the harness, never writes it.

### 4. The immutability gate — the lock on the ruler

The single rule that makes the whole loop trustworthy: **you may change the artifact, but never the
thing that measures it.** Here is the exact sequence around one apply.

```mermaid
%% Every applied change passes through this gate. A violation auto-reverts.
flowchart TD
    P["Proposal arrives<br/>(one structured edit)"] --> V{"validate_proposal<br/>BEFORE apply"}
    V -- "touches an immutable part<br/>(or malformed)" --> REJ["REJECT<br/>log 'immutability-violation'<br/>(nothing applied)"]
    V -- ok --> SNAP["save_snapshot<br/>(copy artifact aside)"]
    SNAP --> APPLY["apply_proposal<br/>(surgical edit)"]
    APPLY --> SUB{"subset re-check<br/>before-set subseteq after-set?"}
    SUB -- "an existing immutable<br/>signature changed/removed" --> RESTORE["restore_snapshot<br/>auto-REVERT<br/>log 'immutability-violation'"]
    SUB -- "yes (additions are fine)" --> EVAL["proceed to EVALUATE<br/>(diagram 2 decides keep/revert)"]

    classDef bad fill:#fdd,stroke:#c66;
    classDef ok fill:#dfd,stroke:#6c6;
    classDef step fill:#e8f0ff,stroke:#5577cc;
    class REJ,RESTORE bad;
    class EVAL ok;
    class SNAP,APPLY step;
```

**Three subtleties that are easy to miss:**

- **There are two checks, before and after, on purpose.** The *before* check (`validate_proposal`) is
  the cheap primary gate — it reads the proposal's shape and rejects anything that would write to an
  immutable field without even touching the file. The *after* check is defense-in-depth: it
  re-fingerprints the artifact and confirms nothing slipped through. If either fails, the apply is
  undone from the snapshot.
- **The after-check is a SUBSET check, not an equality check** — `before ⊆ after`. This is the
  difference between "you may not change the ruler" and "you may not grow the ruler." *Adding* a new
  dataset case (a new `id`) is allowed because the old signatures are all still present; only
  *changing or removing* an existing immutable signature (an existing `id`/`grader`, an `evals/` file,
  a frontmatter `name`/`tier`) trips the gate. A plain hash-equality check would wrongly reject a
  legitimate addition.
- **"text" artifacts have no internal immutable parts.** For prose, the ruler (the `--criteria`
  rubric) is a *separate file* the loop never edits, so there is nothing inside the text itself to
  lock — `immutable_signatures` returns an empty set. The gate is still there; it simply has nothing
  to guard within the artifact, which is why text mode leans on the pairwise Decider instead.

> ✅ **Key takeaways.** The loop is a conversation between a Python orchestrator and a few LLM/agent
> helpers, wrapped around one unbreakable rule. **Diagram 1**: baseline first, then propose → validate
> → snapshot → apply → evaluate → decide → log, every iteration. **Diagram 2**: two decision rules —
> the default path keeps only when `delta > σ` (within-noise moves are reverted as NO_SIGNAL), while
> text mode keeps only when the candidate wins *both-ordering* pairwise voting. **Diagram 3**: one
> orchestrator, a vendor-agnostic LLM layer, and a box of pure-deterministic utilities (so the logic
> is offline-testable); only the `claude` trigger backend is real. **Diagram 4**: the immutability gate
> validates before apply and re-checks after with a *subset* test — additions are fine, changing or
> removing the ruler auto-reverts.

---

## 🛠 CLI Reference

> From here on the manual is **lookup reference** — the flags, components, providers, outputs, and
> error recipes. If you've read the teaching sections above you can skim these and come back as needed.

```
python3 scripts/auto_improve.py --artifact-path <path> --workspace <dir> [options]
```

| Flag | Default | Purpose |
|---|---|---|
| `--artifact-path` | (required) | dir (skill) or file (prompt/workflow/dataset/text) |
| `--workspace` | (required) | where logs / snapshots / report are written |
| `--artifact-type` | `auto` | `skill`/`prompt`/`workflow`/`dataset`/`full-skill`/`text` |
| `--target` | `auto` | `description` (single-shot CSO optimizer) else generic |
| `--eval-set` | — | `evals.json` for skill/prompt/workflow (JSON list, ≤1000) |
| `--criteria` | — | markdown rubric, **required** for `--artifact-type text` |
| `--candidates` | `1` | best-of-N candidates per iteration (text mode) |
| `--threshold` | `1.0` (text `0.9`) | score (0-1) early-stop |
| `--provider` | `auto` | `auto`/`gemini`/`anthropic`/`openai` (sets `DEFAULT_PROVIDER`) |
| `--model` | — | one-off model override for this run |
| `--max-output-tokens` | — | per-call output cap for ALL profiles (else `llm_profiles.yaml`) |
| `--max-iterations` | `10` | budget axis |
| `--max-tokens` | — | budget axis (sums measured `usage.total_tokens`) |
| `--max-duration` | — | budget axis, e.g. `30m`, `1800s`, `1h` |
| `--noise-sigma` | `0.0` | noise band for the absolute-delta decision |
| `--runs-per-query` | `3` | trigger-eval runs |
| `--num-workers` | `min(10, cpus)` | parallel `claude -p` workers (skill-trigger eval) |
| `--git-isolation` | off | run on a throwaway `auto-improve/*` branch (requires clean tree) |
| `--verbose` | off | print the summary to stderr |

**Exit reasons** (in `summary.exit_reason`): `optimal`, `already_optimal`,
`stagnation`, `budget_iterations`, `budget_tokens`, `budget_duration`.

---

## 🏗 Architecture

```
auto_improve.py (orchestrator, vendor-neutral)
├─ Setup     detect type + vendor → set provider env → validate --eval-set
│            (JSON list, ≤1000) → git hygiene (clean tree? create isolation branch)
├─ Baseline  capture the immutable signature ONCE → score the starting artifact
├─ Loop      Proposer → validate-before-apply → snapshot → apply →
│            immutability subset-check → evaluate → KEEP/REVERT/NO_SIGNAL → log
├─ Finalize  convergence/budget exit; on a large-tier change, an adversarial review
└─ Report    improvement_report.md  (merge winner = explicit user action)
```

**Components** (`scripts/`):
- `llm_config.py` — `LLMConfigManager`: vendor-agnostic completion over native SDKs, profile-driven, fallback chains, usage→budget, gateway `base_url`/headers.
- `pairwise.py` — debiased pairwise gate for `text` (champion vs candidate, both orderings).
- `check_immutability.py` — `validate_proposal` (pre-apply) + `immutable_signatures` (subset check).
- `apply_proposal.py` — surgical apply (section / frontmatter / dataset / text-replace).
- `measure_change_size.py` — deterministic tier (trivial/small/medium/large).
- `snapshot.py` — file snapshot/restore + git isolation helpers; prunes to the newest 2.
- `grade_dataset.py` — deterministic dataset quality scorer.
- `detect_artifact_type.py`, `detect_vendor.py`, `log_iteration.py`.
- `backends/` — agent-eval registry: `claude` (validated, wraps skill-creator `run_eval.py`), `gemini`/`codex` (stubs, `available=False`).

**Profiles** (`config/llm_profiles.yaml`): `proposer`, `text_mutator`, `grader` are active; `eval_bootstrap` is **reserved** (defined for a future auto-generate-eval-set step, not yet wired). Each maps all three providers + sampling params.

---

## 🌐 Providers, Gateways & OpenRouter

Select the backend with `DEFAULT_PROVIDER` (or `--provider`); set the matching
`{PROVIDER}_API_KEY`. Per-profile models live in `config/llm_profiles.yaml`;
override at runtime with `{PROVIDER}_MODEL_OVERRIDE` / `--model`.

**OpenRouter** (OpenAI-compatible — the model "link" is `OPENAI_MODEL_OVERRIDE`):
```bash
DEFAULT_PROVIDER=openai
OPENAI_API_KEY=sk-or-v1-...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL_OVERRIDE=anthropic/claude-3.5-sonnet     # vendor/model id; all profiles
# OPENAI_DEFAULT_HEADERS={"HTTP-Referer":"https://app","X-Title":"skill-auto-improve"}  # optional attribution
```
For a different OpenRouter model **per profile**, edit each profile's `openai:`
model in `config/llm_profiles.yaml`. Other gateways: Ollama / vLLM / Together /
Groq / LiteLLM via `OPENAI_BASE_URL`; an Anthropic-compatible proxy via
`ANTHROPIC_BASE_URL`. A non-default base URL prints a WARNING (prompts go there).

Full variable list: `.env.example`.

---

## 🎛 Token & Budget Configuration

Two distinct axes:

1. **Per-call output cap** — `max_output_tokens` per profile in
   `config/llm_profiles.yaml`; override run-wide with `--max-output-tokens`
   (env `LLM_MAX_OUTPUT_TOKENS`).
2. **Whole-run budget** — `--max-tokens` (sums measured `usage.total_tokens`
   from Proposer + grader + pairwise judge), plus `--max-iterations` and
   `--max-duration`. **Known limitation**: `claude -p` skill-trigger tokens are
   not counted toward `--max-tokens`; bound those with `--max-duration` (the
   subprocess also has its own wall-clock timeout).

Defaults are named constants in `llm_config.py` (`DEFAULT_MAX_OUTPUT_TOKENS`,
`DEFAULT_TIMEOUT_SECONDS`, …) — no magic literals.

---

## 🔒 Safety, Immutability & Trust Boundaries

- **Immutable harness**: skill frontmatter `name`/`tier` + `evals/` (content-hashed); dataset `id`/`skill_name`/`grader`/file-refs; prompt `{{placeholders}}`. Validated **before** apply and re-checked **after** (subset check: additions allowed, changes/removals rejected → auto-revert).
- **Scoped edits only**: no raw diffs / file paths in proposals; an edit can only mutate the artifact's own content.
- **Git isolation**: `--git-isolation` runs on a throwaway branch; merge the winner explicitly. A dirty working tree aborts.
- **Trust boundaries** (run on trusted artifacts):
  - Skill-trigger eval spawns a tool-enabled `claude -p` seeded with the artifact's text; the `description` is sanitized + framed as untrusted data at the sink (`run_eval.py`).
  - `text` mode feeds artifact prose to the rubric + pairwise judges (which are the keep gate). Prose is stripped of injection markup and judges are told to treat it as data, but a plaintext-imperative injection cannot be fully neutralized while judging prose — review the winner before merging.
  - The process environment (`{PROVIDER}_API_KEY`, `OPENAI_BASE_URL`, `AUTO_IMPROVE_*`) and a CWD `.env` are **trusted input**.

---

## 📤 Outputs

Written to `--workspace`:
- `improvement_history.tsv` — `iter · score · delta · status · tier · change_summary · snapshot_ref` (modeled on autoresearch `results.tsv`). Statuses: `baseline`, `keep`, `revert`, `no-signal`, `no-change`, `immutability-violation`, `error`.
- `improvement_report.md` — before/after, score trajectory, exit reason, git branch.
- `snapshots/iter-*/` — pruned to the newest 2 (revert scratch space).
- `adversarial_review.md` — only for large-tier changes (advisory).

The winning artifact is left in place; under `--git-isolation` it lives on the
`auto-improve/*` branch for you to merge.

---

## ✅ Verification & Testing

```bash
# Structure / CSO
python3 ../skill-creator/scripts/validate_skill.py .         # exit 0
# Offline unit suite (no API keys): decision logic, immutability, apply, pairwise,
# text-replace, dataset, gateway/token config — all injected fakes
cd scripts && python3 -m unittest discover -s tests          # all pass
```

The orchestrator's KEEP/REVERT/NO_SIGNAL/convergence/budget/immutability and the
pairwise/best-of-N paths are covered by injected-fake tests — no network needed.
`evals/evals.json` defines behavioral scenarios; fixtures live in `evals/fixtures/`.

---

## ❓ Troubleshooting

| Symptom | Cause → Fix |
|---|---|
| `ABORT: --artifact-type text requires --criteria` | text mode needs a rubric → pass `--criteria rubric.md` |
| `ABORT: uncommitted changes` | `--git-isolation` needs a clean tree → commit/stash first |
| `vendor '...' has no agentic backend` | skill-trigger eval needs the `claude` CLI / `run_eval.py` → install Claude Code, or improve a `prompt`/`text`/`dataset` artifact (LLM-graded) instead |
| `WARNING: API key for provider ... not found` | set `{PROVIDER}_API_KEY` in `.env` (matching `DEFAULT_PROVIDER`) |
| `WARNING: routing ... to non-default base_url` | expected when using a gateway (`OPENAI_BASE_URL`/`ANTHROPIC_BASE_URL`) |
| loop exits `stagnation` immediately | Proposer keeps returning unapplyable/no-change edits → check the artifact has the sections/text the Proposer targets; raise `--candidates` for text |
| `--max-tokens` overshoots | `claude -p` tokens aren't metered → bound with `--max-duration` |

See also: [Skill Writing Manual](skill-writing_manual.md), [Skill Evals Guide](skill-evals_guide.md).

---

## Appendix A — Glossary

Grouped by topic. Each term gets a one-line **"in plain words"** definition, and an **analogy** wherever it helps. If you forget the analogies later, the plain-words line is the part to keep.

### A.1. The core loop

This is the heartbeat of the whole skill: **the eval harness is frozen; the artifact is free to change; a change is *kept* only when the number genuinely goes up, otherwise it is *thrown away*.**

| Term | In plain words | Analogy |
|---|---|---|
| **Artifact** | The thing being improved — a SKILL.md, a prompt, a workflow, an eval dataset, or arbitrary prose. It is the only thing the loop is allowed to edit. | The essay you keep revising. |
| **Eval harness** | The "ruler" that produces the score (a rubric file, an eval set, or a dataset grader). It is **immutable** — the loop can never edit it. | The exam answer key — you don't get to rewrite it to pass. |
| **Orchestrator** | The Python program (`auto_improve.py`) that runs the loop: it asks for a change, scores it, decides keep/revert, and logs. It owns the budget and every decision. | The lab supervisor running the experiment — not a participant in it. |
| **Proposer** | An LLM call that suggests **one** structured edit per iteration (a "proposal"). It never grades its own work. | The writer who suggests one edit at a time. |
| **Evaluator** | Whatever produces the score for the current artifact — a deterministic script, a skill-trigger run, or an LLM grader, depending on artifact type. | The examiner who hands back a mark. |
| **Decider** | A special gate used **only in text mode**: the debiased pairwise judge that picks champion vs candidate (see A.3). For everything else the orchestrator decides by the delta rule. | The referee who only shows up for the prose matches. |
| **Iteration** | One full lap of the loop: propose → validate → snapshot → apply → re-check immutability → evaluate → decide → log a row. | One round of "edit, mark, keep-or-toss." |
| **Convergence** | The loop's check that it should stop — either it hit the score `--threshold` (optimal) or it stopped improving for a few rounds in a row. | Knowing when to put the pen down. |
| **Stagnation** | An exit reason: too many iterations in a row produced no real improvement (the no-improve streak filled a 3-iteration window). | Diminishing returns — you keep editing but nothing gets better. |

```mermaid
flowchart LR
    P["Proposer<br/>one edit"] --> VB["validate<br/>(before apply)"]
    VB --> SN["snapshot"]
    SN --> AP["apply"]
    AP --> IM["immutability<br/>subset re-check"]
    IM --> EV["Evaluator<br/>= score"]
    EV --> DE{"DECIDE"}
    DE -->|"delta &gt; sigma"| K["KEEP"]
    DE -->|"|delta| ≤ sigma"| N["NO_SIGNAL → revert"]
    DE -->|"else"| R["REVERT"]
    K --> LOG["log a row"]
    N --> LOG
    R --> LOG
    classDef harness fill:#e8f0ff,stroke:#5577cc;
    classDef good fill:#dfd,stroke:#6c6;
    classDef bad fill:#fdd,stroke:#c66;
    class EV harness;
    class K good;
    class N,R bad;
```

- **The snapshot happens *before* apply.** That is what makes a REVERT cheap and exact — you just restore the saved copy, you never "undo by hand."
- **Immutability is checked twice** — once before the edit lands (to reject an illegal proposal) and once after (a subset check, see A.5). Belt and suspenders.
- **The Proposer and the Evaluator are different roles.** The author never grades itself — that separation is the whole reason the score can be trusted.

> ✅ **Key takeaways (core loop).** One edit per lap; the ruler is frozen; keep only verified wins; everything else snaps back to the snapshot. The orchestrator owns the decisions and the budget — the LLM only proposes and grades.

### A.2. Decision terms

How the orchestrator turns a *number* into a *keep-or-revert* verdict.

| Term | In plain words | Analogy |
|---|---|---|
| **Baseline** | The very first score, measured before any edits — the bar every change must clear. Logged as iteration 0. | Your starting weight before the diet. |
| **Champion** | The current best version — the pre-change snapshot the candidate is measured against (the term is used in text mode). | The reigning title-holder. |
| **Candidate** | The just-edited version being tested this round; it must beat the champion to be kept. | The challenger in the ring. |
| **Score / metric** | The single number (0–1) the Evaluator returns — e.g. trigger accuracy, pass_rate, or a rubric score. Higher is better. | The exam mark. |
| **Delta** | `score − best_score`: how much this change moved the number, up or down. | The change on the scale since last week. |
| **Noise sigma** (`--noise-sigma`) | The "jitter band." LLM scores wobble run-to-run (σ ≈ 0.05–0.10); a delta smaller than sigma is treated as noise, not progress. | The ±0.3 kg that a bathroom scale wobbles by — don't celebrate it. |
| **KEEP** | The verdict when `delta > sigma` (beyond a tiny epsilon) **and** the secondary metric didn't regress. The change stays. | "Real progress — lock it in." |
| **NO_SIGNAL** | The verdict when `|delta| ≤ sigma`: the move is within noise, so it is **reverted** — noise is never kept, or it would silently accumulate as drift. | "Could be the scale wobbling — ignore it." |
| **REVERT** | The verdict for anything else (delta went negative, or the secondary metric regressed): undo the change back to the snapshot. | "Worse — put it back." |
| **Secondary metric** | An optional second number (e.g. don't let speed collapse while accuracy rises); a regression here blocks a KEEP even if the main score went up. | A side-effect check: the diet worked but did your energy crash? |
| **Threshold** (`--threshold`) | The score at which the loop declares victory and stops early (default `1.0`; text mode `0.9`). | The passing grade that ends the exam. |

> ✅ **Key takeaways (decision).** KEEP needs a delta bigger than the noise band *and* no regression on the side metric. A within-noise move (`NO_SIGNAL`) is reverted on purpose — so random luck never sneaks into the artifact and pretends to be improvement.

### A.3. Text mode & the pairwise gate

Prose has no objective number, so text mode swaps the delta rule for a head-to-head judge.

| Term | In plain words | Analogy |
|---|---|---|
| **Debiased pairwise gate** | The keep-decision for text: an LLM judge compares champion vs candidate in **both orderings** (champ-first, then cand-first) and the candidate is kept only if it nets **more wins** than the champion (ties → keep champion). | Two blind taste-tests with the cups swapped, so you can't tell which is which by position. |
| **Best-of-N** (`--candidates N`) | Draft N different edits in one iteration, score each, and send only the best one through the pairwise gate. | Sketch three options, submit your strongest. |
| **Rubric** (`--criteria`) | A markdown file of weighted dimensions summing to 100 that defines "good" for the prose. In text mode it is the **immutable harness** — the loop never edits it. | The grading rubric handed out before the essay. |

```mermaid
flowchart LR
    C["criteria rubric<br/>(immutable)"] --> J["LLM judge"]
    CH["Champion"] --> J
    CA["Candidate"] --> J
    J --> O1["Order 1: champ=A, cand=B"]
    J --> O2["Order 2: cand=A, champ=B"]
    O1 --> V{"candidate wins<br/>MORE rounds?"}
    O2 --> V
    V -->|yes| K["KEEP candidate"]
    V -->|"no / tie"| R["keep champion"]
    classDef harness fill:#e8f0ff,stroke:#5577cc;
    classDef good fill:#dfd,stroke:#6c6;
    class C harness;
    class K good;
```

- **Two orderings cancel position bias.** A lone judge tends to favor whichever version it reads first; swapping the order and requiring a net win neutralizes that tilt.
- **The rubric score still matters — but not for the keep decision.** It is logged and it drives the `--threshold` early-stop, while the *pairwise* result alone decides KEEP/REVERT.
- **Ties keep the champion.** The incumbent only loses its crown to a clear win, so nothing is swapped on a coin-flip.

> ✅ **Key takeaways (text mode).** No absolute number for prose — instead a swapped-order head-to-head where the candidate must *out-win* the champion. Best-of-N drafts several edits and ships the strongest. The rubric is the frozen ruler.

### A.4. Artifacts & edit formats

There are six artifact types, and every edit is **scoped and structured** — there is no raw-diff format (it was removed for security). Each format can only touch the artifact's own content.

| Edit format | In plain words | Used by |
|---|---|---|
| **section-replace** | Replace the body under one `## Header` (no rename; frontmatter untouched). | skill, full-skill, prompt, workflow |
| **frontmatter-field** | Set a mutable header field — `description` or `version`; `name`/`tier` are rejected. | skill, full-skill |
| **dataset-op** | `add` or `modify` an `evals.json` case; cannot touch `id`/`skill_name`/`grader`/file-refs, and **no removals**. | dataset |
| **text-replace** | A scoped find/replace inside the artifact's own string — exact match, else whitespace-tolerant; the `find` is capped at 4096 chars. | text |

| Artifact term | In plain words |
|---|---|
| **Trigger accuracy** | The metric for tuning a skill's `description`: of the labeled queries, how many fired (or didn't) correctly — the score for the `--target description` CSO optimizer. |
| **pass_rate** | The metric for skill/prompt/workflow bodies: the fraction of eval expectations that passed. |
| **Edit format** | The structured "shape" an edit must take; the Proposer must return one of the four above, never a free-form file rewrite. |

- **Datasets are additive-only.** You can add or modify cases, but you can never delete one or change its grader/id — so the loop can't quietly weaken its own test set.
- **`name` and `tier` are off-limits** in frontmatter; only `description` and `version` are mutable.
- **A dataset is scored deterministically** (by `grade_dataset.py`) — no LLM, no API — which is why the dataset path is the offline-safe quick start.

> ✅ **Key takeaways (artifacts & edits).** Six types, four scoped edit formats, zero raw diffs. Each format physically can't reach outside the artifact, and the "harness" parts (graders, ids, name/tier, file-refs) are walled off from every format.

### A.5. Immutability

The harness is protected by a two-point check so nobody can "improve the score" by editing the ruler.

| Term | In plain words | Analogy |
|---|---|---|
| **Immutability** | The rule that certain parts can never change: skill frontmatter `name`/`tier` + the whole `evals/` dir (content-hashed); dataset `id`/`skill_name`/`grader`/file-refs; prompt `{{placeholders}}`. | The parts of the contract that are notarized — alter them and the deal is void. |
| **validate_proposal** | The **before-apply** gate: rejects an illegal edit *before* it ever lands. | The bouncer who checks your ID at the door. |
| **Subset check** | The **after-apply** re-check: additions are fine, but **changing or removing** an existing immutable part triggers an auto-revert. | A roll-call: new faces welcome, but no one who was on the list may go missing or be swapped. |
| **Snapshot** | A saved copy of the artifact taken before each edit; a REVERT just restores it. The loop keeps only the newest 2 to save space. | A save-point in a game you can reload to. |
| **Tier** | A deterministic size label for a change — `trivial` / `small` / `medium` / `large` — computed by `measure_change_size.py`, never by the Proposer. `large` (≥2 sections or ≥50 changed lines) also triggers an advisory adversarial review. | T-shirt sizing the edit — the bigger it is, the more scrutiny it earns. |

- **"Additions allowed" is why adding dataset cases is legal** even though it changes the directory — the subset check only forbids *altering or deleting* what was already immutable, not *adding* alongside it.
- **`text` artifacts have no internal immutable parts** — the rubric is a separate file, so there's nothing inside the prose to protect.
- **Tier is computed, not chosen.** The author can't downgrade its own large rewrite to dodge the adversarial review.

> ✅ **Key takeaways (immutability).** Checked before *and* after every edit. Additions pass; changing or removing a protected part auto-reverts. Snapshots make every revert exact, and the change's size (tier) is measured deterministically.

### A.6. Providers, gateways & backends

The skill is vendor-agnostic — the same loop runs on different LLMs.

| Term | In plain words | Analogy |
|---|---|---|
| **Provider** | Which LLM vendor runs the calls — `anthropic`, `openai`, or `gemini` — chosen by `DEFAULT_PROVIDER` (or `--provider`). | The electricity supplier — the appliances run the same either way. |
| **Profile** | A named role-to-model mapping in `config/llm_profiles.yaml`: `proposer`, `text_mutator`, `grader` (active) + `eval_bootstrap` (reserved, not yet wired) — each maps all three providers + sampling params. | Job titles that each pick a person — and the person can be from any agency. |
| **Gateway** (e.g. **OpenRouter**) | An OpenAI-compatible endpoint you point at via `OPENAI_BASE_URL` + `OPENAI_MODEL_OVERRIDE` (also Ollama / vLLM / etc.). Sends prompts there instead of the vendor's own API. | A power adapter that lets you plug into a different outlet — same plug shape, different wall. |
| **Backend** (`claude`/`gemini`/`codex`) | The agent-eval adapter used for **skill-trigger** evaluation. Only `claude` is validated (it wraps skill-creator's `run_eval.py` via `claude -p`); `gemini` and `codex` are stubs (`available=False`) that fall back to LLM grading. | Three sockets on the wall — only one is actually wired up. |

- **"Provider" and "backend" are not the same thing.** The provider picks which LLM writes the proposals and grades prose; the backend is specifically the agent that runs the skill-trigger eval (only `claude` works there today).
- **A non-default base URL prints a WARNING** — because your prompts are now leaving for that endpoint, which you should trust.
- **`claude -p` tokens are not metered** against `--max-tokens`; bound the skill-trigger eval with `--max-duration` instead.

> ✅ **Key takeaways (providers).** One loop, any vendor. Profiles map roles to models per provider; gateways reroute via an OpenAI-compatible URL; and the *backend* (only `claude` validated) is a separate concept used only for skill-trigger evals.

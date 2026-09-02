---
id: WI-034
type: work-item
status: done
opened_at: 2026-09-02
slug: wi-034-execution-policy-migration
effort: M
value: 'the warning-first execution-policy migration finishes, or is closed as not applicable per skill, instead of standing as 32 permanent advisories'
source: WI-033 adjudication — the rule the Measured table omitted, 32 occurrences across 6 skills
resolved_at: 2026-09-02
resolved_by: sections authored in six skills + the execution-policy rule shared byte-for-byte between both gates; tests/test_shared_gate_logic.py
---

# WI-034 — finish the warning-first Execution Policy migration

## Verdict

`[Execution Policy]` is the second-largest rule in the repository: **32 occurrences across 6
skills** (`hooks-creator` 4, `obsidian-cli` 6, `skill-validator` 7, `text-humanizer` 7,
`vdd-adversarial` 4, `vdd-sarcastic` 4). Both gates emit the identical finding set; both now
treat it as non-blocking. [WI-033](wi-033-analyze-gaps-adjudicate-findings.md) made the two
gates agree about the severity; it did not do the per-skill work the findings name.

The finding text calls itself a "warning-first migration target". A migration that never
completes is a permanent advisory, which is the same noise WI-033 was filed about, one
severity level down.

## Measured — 2026-09-02

Adjudicated per finding by an independent reader plus an adversarial refuter. The 32 split
roughly in half:

**Sections genuinely absent.**

- `Execution Mode` — missing from all six. No `**Mode**:` declaration anywhere, so
  `analyze_gaps.py` resolves `mode="unknown"` and its own prompt-first exemption for
  `Script Contract` can never engage. For `vdd-adversarial` and `vdd-sarcastic` the one-line
  declaration is both true and what unlocks that exemption.
- `skill-validator` — `Script Contract` (the CLI Options table lists five flags and one exit
  code but no command signature, no positional input, no stdout/stderr split, no exit-code
  table) and `Validation Evidence` (a tool whose job is an objective pass/fail verdict
  records no evidence of its own verification).
- `text-humanizer` — `Script Contract` (three command lines appear; none says where the input
  text comes from — `humanizer.py` has no positional argument and no `--input`, it assembles
  a prompt on stdout) and `Validation Evidence`.
- `obsidian-cli` — `Validation Evidence`. The availability probe covers pre-conditions; for a
  skill whose selling point is a rename that preserves backlinks, nothing states how to prove
  the link survived.

**Sections that exist under a different heading.** `_has_section` matches on the normalised
heading title, so a contract written under its own name is invisible to it:

| Skill | Finding | What is actually there |
|---|---|---|
| `obsidian-cli` | Missing `Safety Boundaries` | `## Safety tiers` — T1/T1-UX/T2/T3, default-DENY for unlisted commands, trash-by-default with a separate-turn confirmation |
| `skill-validator` | Missing `Safety Boundaries` | the honest-scope section: static-only, regex-bypassable, 10 MB cap, `.scanignore` risk |
| `hooks-creator` | Missing `Safety Boundaries` | the SECURITY CRITICAL callout — strict JSON on stdout, jq-only parsing, exit 2 on missing deps |
| `vdd-adversarial`, `vdd-sarcastic` | Missing `Validation Evidence` | the objective bar: the test run must have actually executed, and a supplied `NOT RUN` line is not evidence |

**Findings whose premise is false.** Three fire on a substring test rather than on the skill:

- `obsidian-cli` — "Script references found but `Validation Evidence` is missing" triggers on
  the bare substring `scripts/`, whose only match is a path to *another* skill's script. The
  skill ships no `scripts/`.
- `text-humanizer` — "Mutation/destructive language found" triggers on "remove", applied to
  AI patterns in prose. The script writes only to stdout.
- `skill-validator` — the same mutation-marker test now fires on the word "removes" in a
  Rationalization Table row added by WI-033. This one is a rule defect: the marker list is a
  naive `in body_lower` substring test with no notion of what is being removed.

## Scope

1. Declare `**Mode**:` in all six skills. One line each, and it unlocks the prompt-first
   `Script Contract` exemption for the four that ship no `scripts/`.
2. Author the genuinely-absent `Script Contract` / `Validation Evidence` sections in
   `skill-validator` and `text-humanizer`, and `Validation Evidence` in `obsidian-cli`.
3. For a contract that exists under another name, decide per skill: retitle to the policy
   heading, or record why the local name is better and exempt it. Retitling `obsidian-cli`'s
   "Safety tiers" was measured to take that skill from 6 findings to 0.
4. Narrow the mutation-marker test so "remove" applied to prose is not mutation language.
5. Re-run both gates across all 22 skills and append before/after counts to this record.

## Acceptance

- Every remaining `[Execution Policy]` advisory is either closed or carries a written reason
  to stand.
- `python3 skills/skill-enhancer/scripts/analyze_gaps.py <skill> --strict` exits 0 on the six
  skills, or the exceptions are named here.

## Out of scope

- The `[Language]` advisory class — the graduated-wording policy, deferred by
  [WI-033](wi-033-analyze-gaps-adjudicate-findings.md).
- Changing the four policy section names in `docs/SKILL_EXECUTION_POLICY.md`.

---

## Resolution (2026-09-02)

All 32 `[Execution Policy]` advisories are closed. Each skill's sections were authored by an
independent reader and then put to an adversarial verifier whose only job was to find a
plausible section documenting a flag, an exit code or a file that does not exist. Five such
claims were caught and corrected before anything was applied; none survived into the files.

### Before / after

| Skill | Before | After | How |
|---|---|---|---|
| `hooks-creator` | 4 | 0 | `Execution Mode` authored (prompt-first; the `Script Contract` exemption follows); the SECURITY CRITICAL callout retitled to `Safety Boundaries`; Phase 3 retitled to carry `Validation Evidence` and given pass criteria plus a worked example |
| `obsidian-cli` | 6 | 0 | `Execution Mode` authored; `## Safety tiers` retitled `## Safety Boundaries (tiers)`; `Validation Evidence` authored — the before/after backlink count that proves a rename kept its links |
| `skill-validator` | 6 | 0 | `Execution Mode` + `Script Contract` (signature, stdout/stderr split, exit-code table) authored; `Security & Limitations` retitled `Safety Boundaries (Security & Limitations)`; `Validation Evidence` authored with measured runs |
| `text-humanizer` | 7 | 0 | all four authored. The `Script Contract` states the thing the skill never said: `humanizer.py` takes no input text — it writes a prompt on stdout, and the model applies it |
| `vdd-adversarial` | 4 | 0 | `Execution Mode` + `Safety Boundaries` authored; the Convergence Signal heading retitled to name itself as `Validation Evidence` |
| `vdd-sarcastic` | 4 | 0 | same shape as `vdd-adversarial`, kept consistent with it |
| **total** | **32** | **0** | |

Repo-wide, over the 22 skills carrying a `SKILL.md`: `[Execution Policy]` went from **31
advisories across 6 skills** to **2 across 2 skills**, and both remaining ones are a different
sub-rule — the `Validation Evidence is N lines` soft limit on `docx` (13) and
`transcript-fetcher` (15), which `validate_skill.py` had been warning about all along and which
`analyze_gaps.py` only started reading when the two gates' config keys were aligned. Blocking
gaps stay at 0 and the two gates return the same verdict on all 22 skills.

### Scope item 4 — the mutation-marker test

Narrowed, and the narrowing turned out to be smaller than the real defect next to it.

Three sub-rules — "`scripts/` has executable content but `Script Contract` is missing",
"Mutation/destructive language found but `Safety Boundaries` is missing", "Script references
found but `Validation Evidence` is missing" — each fire **only when that section is already
missing**, so each could only ever restate a finding already made. 7 of the 31 occurrences were
such duplicates. They now annotate the one finding with the trigger that fired:

    Missing 'Safety Boundaries' section (warning-first migration target) — mutation wording found (delete, overwrite).

With the marker demoted from producing a finding to shaping a message, its precision costs less
and was raised anyway: it reads the masked body, so `delete` inside a documented command line no
longer counts, and it matches whole words with common inflections. The `Validation Evidence`
trigger now asks whether the skill **ships** `scripts/` rather than whether the body contains the
substring `scripts/` — that substring test fired on `obsidian-cli`, whose only match was a path
to another skill's script.

The marker list is still a heuristic over prose: `remove` applied to AI patterns still reads as
mutation wording. That is acceptable now that it cannot produce a finding on its own, and it is
pinned as such in `test_prose_about_removing_patterns_is_not_a_file_mutation`.

### Acceptance

- **Every advisory closed or reasoned.** 32 of 32 closed. Nothing left open.
- **`--strict` exits 0 on the six skills** — met for `hooks-creator`, `vdd-adversarial` and
  `vdd-sarcastic`. **Named exception:** `obsidian-cli`, `skill-validator` and `text-humanizer`
  still exit 1 under `--strict`, and not for an execution-policy reason — `--strict` promotes
  every advisory class, including `[Language]`, which
  [WI-033](wi-033-analyze-gaps-adjudicate-findings.md) explicitly defers. Their
  `[Execution Policy]` advisory count is 0. Measured per skill above.

### What this changed outside the six skills

The execution-policy rule was inline in one gate and a function in the other. It is now one
function, byte-identical in both, listed in `SHARED_FUNCTIONS` and held there by
`tests/test_shared_gate_logic.py` — the two gates emitting the same 31 findings with opposite
verdicts is the shape WI-033 was filed about, and the shared copy is what stops it recurring.

`skills/obsidian-cli/references/command-reference.md` has two pointers realigned to the retitled
heading. The second was found by the verifier: the authoring pass grepped case-sensitively and
missed it.

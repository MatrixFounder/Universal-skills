---
id: WI-033
type: work-item
status: open
opened_at: 2026-09-02
slug: wi-033-analyze-gaps-adjudicate-findings
effort: M
value: 'a non-empty analyze_gaps report becomes a signal to act on, instead of noise that teaches agents to skip it'
source: skills/pdf edit session 2026-09-02 — validate_skill.py passed while analyze_gaps.py reported 9 findings on the same file
---

# WI-033 — analyze_gaps.py: adjudicate its findings, rule by rule

## Verdict

`skill-enhancer/scripts/analyze_gaps.py` reports findings that, on `skills/pdf`, describe correct
documentation rather than defects. The rules involved are not pdf-specific — they fire across
roughly half the repository. Until each rule is adjudicated (the skill is wrong, or the rule is), a
non-empty report carries no information, and the habit it teaches is to stop reading it.

The trigger was two gates disagreeing about one file: `validate_skill.py` exits `0` on `skills/pdf`
while `analyze_gaps.py` reports 9 findings on the same `SKILL.md`.

## Measured — 2026-09-02, the 22 skills carrying a `SKILL.md`

| Rule | Skills hit | Share | Occurrences |
|---|---|---|---|
| `Language` (weak wording) | 11 | 50% | 11 |
| `Anti-Pattern` (absolute path) | 10 | 45% | 34 |
| `Lazy` (bracket placeholder) | 8 | 36% | 9 |
| `Resilience` | 5 | 23% | 7 |
| `CSO` | 2 | 9% | 2 |
| `Richness` | 2 | 9% | 2 |
| `Structure` | 1 | 5% | 1 |

Reproduce: run `analyze_gaps.py` against every `skills/*` directory that holds a `SKILL.md`, then
group the `- [Rule]` lines by rule.

## What was verified, and what was not

**Verified on `skills/pdf` only.** Two rules describe correct content there:

- `Lazy` — *"Found 36 bracket placeholders (e.g. `[--page-size letter|a4|legal]`). Fill them in."*
  These are CLI usage notation in the Script Contract, where brackets mean "optional argument".
  Filling them in would make every documented command line wrong.
- `Anti-Pattern` — *"Potential Absolute Path `/tmp/invoice.pdf`"*. These sit in Validation Evidence
  as commands a reader runs to reproduce the check. An absolute scratch path is correct there.

**Not verified anywhere else.** The same two rules fire on 8 and 10 other skills. Whether those hits
are also correct content is unknown, and determining it is the work this item asks for. The counts
above measure how often the rules fire, not how often they are wrong.

## Scope

For each of the three high-frequency rules (`Language`, `Anti-Pattern`, `Lazy`):

1. Sample its hits across the repository and classify each one: real defect, or correct content.
2. Where the rule misfires on a legitimate pattern, **narrow the rule** — for example, exempt fenced
   blocks and the `Script Contract` / `Validation Evidence` sections from the path and placeholder
   checks — rather than editing skills to satisfy a wrong rule.
3. Where the hits are real, fix the skills.
4. Re-run across all skills and append the before/after counts to this file.

## Acceptance

- Every remaining `analyze_gaps.py` finding in the repository is either fixed or carries a written
  reason to stand.
- `analyze_gaps.py` and `validate_skill.py` no longer disagree about `skills/pdf`.
- The before/after table is appended to this record.

## Out of scope

- Rewriting `analyze_gaps.py` beyond rule scoping.
- The `Language` rule's graduated-wording policy. `skill-enhancer` already states that "should" is
  not blindly replaced with `MUST`, so each hit is a judgement call per instruction, not a
  mechanical fix. It is counted above for completeness and left to a separate pass.

## Origin

Found while editing `skills/pdf/SKILL.md` on 2026-09-02: the description gained HTML→PDF triggers
(`"html to pdf"`, `"webarchive/MHTML to pdf"`, `"export this deck to pdf"`), and three Red Flags
were added covering print-CSS engine choice, page count as false proof of a good render, and
grepping PDF bytes for embedded fonts. That edit is uncommitted in the working tree at the time of
filing.

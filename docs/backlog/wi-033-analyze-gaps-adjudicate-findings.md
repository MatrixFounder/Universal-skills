---
id: WI-033
type: work-item
status: done
opened_at: 2026-09-02
slug: wi-033-analyze-gaps-adjudicate-findings
effort: M
value: 'a non-empty analyze_gaps report becomes a signal to act on, instead of noise that teaches agents to skip it'
source: skills/pdf edit session 2026-09-02 — validate_skill.py passed while analyze_gaps.py reported 9 findings on the same file
resolved_at: 2026-09-02
resolved_by: rule scoping in analyze_gaps.py + a severity channel + 9 skill fixes; tests/test_rule_scoping.py
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

> This table is **corrected and extended** in the Resolution below. Every row it states
> reproduces exactly; it is wrong by omission (`Execution Policy`, the second-largest rule)
> and by mixing two units in one column.

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

---

## Resolution (2026-09-02)

Every finding in the repository was adjudicated. The measurement was reproduced against
commit `2bc7ac8`, each rule class was classified by an independent reader and each verdict
put to an adversarial refuter; the refutations are folded in below and corrected several
claims made in this record.

### Corrected measurement

The original table is accurate for every row it states and for the 22-skill denominator. It
is wrong in three ways, all corrected here.

| Rule | Skills hit | Share | Findings emitted | Underlying occurrences |
|---|---|---|---|---|
| `Anti-Pattern` | 10 | 45% | 34 | 34 (31 absolute-path + 3 Windows-path) |
| `Execution Policy` | 6 | 27% | 31 | 31 |
| `Language` | 11 | 50% | 11 | 31 weak-wording lines |
| `Lazy` | 8 | 36% | 9 | 221 bracket placeholders + 2 `TODO` |
| `Resilience` | 5 | 23% | 7 | 7 |
| `CSO` | 2 | 9% | 2 | 2 |
| `Richness` | 2 | 9% | 2 | 2 |
| `Structure` | 1 | 5% | 1 | 1 |

1. **`Execution Policy` was omitted.** 31 occurrences across 6 skills — more than `Lazy`,
   `Resilience`, `CSO`, `Richness` and `Structure` combined. An implementer sizing the work
   from the original table was 31 occurrences and 6 skills short.
2. **The `Occurrences` column mixed two units.** `Anti-Pattern` and `Execution Policy` are
   per-hit; `Language` and `Lazy` are per-skill summary lines. `Lazy`'s 9 covers 221
   placeholders — 24x its tabulated number.
3. **Two rows are mislabelled.** `Anti-Pattern` (absolute path) includes 3 Windows-style-path
   findings; `Lazy` (bracket placeholder) includes 2 `TODO` findings.

The `Structure` row does not reproduce from a clean checkout: it comes from
`skills/html/tmp`, which `.gitignore:51` excludes, so `git archive HEAD` yields 96 findings
and `Structure` 0.

### Corrections to the rest of the record

| Line | Stated | Measured |
|---|---|---|
| 49 | "the same two rules fire on 8 and 10 other skills" | 7 and 9 other skills — 8 and 10 are the table totals and already include pdf |
| 44 | the 36 placeholders "are CLI usage notation in the Script Contract" | 34 in Script Contract, 2 in Quick Reference; all 36 are usage notation |
| 46 | the `/tmp` paths "sit in Validation Evidence as commands a reader runs" | 5 of 7 in Validation Evidence, one of those an expected-artifact list; the other two are `--base-url /absolute/image/root` in §7.2 and `/tmp/dump.json` in §10 |
| 58 | narrow by "exempt fenced blocks and the `Script Contract` / `Validation Evidence` sections" | clears **0 of 7** paths and **0 of 36** placeholders on `skills/pdf`, and 3/31 + 20/221 repo-wide. On pdf every hit is in an **inline code span**, none in a fence. The section half keys on a heading the hits do not all sit under |
| 55 vs 74 | Scope §1 lists `Language` among the rules to fix; Out of scope defers the whole `Language` rule | split: narrowing is in scope, the per-instruction wording judgement is not |
| 66 | Acceptance 1 covers the whole repository | Scope covers 3 rules / 54 occurrences; the repository adds 43 more from 5 rules Scope never names |
| 18 | "the skill is wrong, or the rule is" | a third case exists and the `CSO` row is entirely made of it: the rule is right and `analyze_gaps.py` ignores the project config that switches it off |
| 83 | "That edit is uncommitted in the working tree at the time of filing" | it landed with this record in commit `2bc7ac8` |

### Adjudication — rule by rule

| Rule | Verdict | Action |
|---|---|---|
| `Anti-Pattern` absolute path (31) | 31 of 31 correct content. First segments are `tmp` (28), `abs`, `absolute`, `dev`. **Zero named a machine.** | Rule narrowed: fire only when the first segment names one machine or one user's account. |
| `Anti-Pattern` Windows path (3) | 3 of 3 correct content: `x\_1` twice (markdown escape) and `1.1.0\n` (C escape) | Rule narrowed: require a drive letter, a UNC share, or three backslash-separated segments. |
| `Lazy` placeholders (221) | 199 CLI usage notation, 19 mermaid node labels, 1 metasyntactic prompt slot, 2 bracket artefacts. **Zero unfilled template slots.** | Rule narrowed: read the masked body; exempt `[--flag …]` and `[^fn-N]`. |
| `Lazy` TODO (2) | 2 of 2 correct content: a CLI subcommand name (`obsidian tasks todo`) and prose describing a generated deck's placeholder | Rule narrowed: a marker is `TODO:` / `- TODO` / `<!-- TODO -->`, not `TODO` followed by a lowercase word. |
| `Language` (31 lines) | 4 mechanical misfires (`can't` read as `can`, a hyphenated `should-trigger`, questions in an interview script). The remaining 27 are a judgement call per instruction. | Rule narrowed for the 4; the rest reclassified **advisory** — see "What stands". |
| `Execution Policy` (31) | Both gates emit the identical 31 findings on the identical 6 skills; `validate_skill.py` exits 0, `analyze_gaps.py` exited 1. Of the 31, roughly half are sections genuinely absent and half exist under a different heading (`obsidian-cli`'s "Safety tiers" *is* Safety Boundaries). | Reclassified **advisory**, matching the twin implementation. The skill work is [WI-034](wi-034-execution-policy-migration.md). |
| `Resilience` (7) | 7 of 7 real. The five skills genuinely lack the sections; the substring check and a heading check agree on the whole corpus. | Sections authored in `html`, `obsidian-cli`, `skill-creator`, `skill-validator`, `text-humanizer`. Severity later lowered to **advisory in both gates** — see the amendment below. |
| `CSO` (2) | 2 of 2 a gate disagreement, not a defect: `validate_skill.py` honours `enforce_cso_prefix` (the overlay sets it `false`), `analyze_gaps.py` ignored it. | `enforce_cso_prefix` honoured; `inline_exempt_skills` too, the same asymmetry one rule over. |
| `Richness` (2) | 2 of 2 real: `obsidian-cli` and `text-humanizer` ship no `examples/`. | `examples/usage.md` authored for both. |
| `Structure` (1) | Correct content: `skills/html/tmp` is a gitignored scratch directory, absent from a packaged `.skill`. | Rule narrowed: skip directories git already ignores. |

### Before / after

Counts are per-rule occurrences over the 22 skills carrying a `SKILL.md`.

| Rule | Before (`2bc7ac8`) | After — blocking | After — advisory |
|---|---|---|---|
| `Anti-Pattern` | 34 | 0 | 0 |
| `Execution Policy` | 31 | 0 | 2 |
| `Language` | 31 lines | 0 | 28 lines |
| `Lazy` | 221 + 2 | 0 | 0 |
| `Resilience` | 7 | 0 | 0 |
| `CSO` | 2 | 0 | 0 |
| `Richness` | 2 | 0 | 0 |
| `Structure` | 1 | 0 | 0 |
| **Exit code** | 15 of 22 skills exit 1 | **22 of 22 exit 0** | — |

The `Execution Policy` figure moved twice after this record was first written, and both moves
are recorded rather than smoothed. It went 31 → 32 when a Rationalization Table row added to
`skill-validator` by this very change-set tripped the mutation-marker substring test on the word
"removes" — a rule-scoping defect of its own. It then went 32 → 0 for the missing-section
sub-rules when [WI-034](wi-034-execution-policy-migration.md) authored the sections in all six
skills and narrowed that marker test. The 2 that remain are a different sub-rule — the
`Validation Evidence is N lines` soft limit on `docx` and `transcript-fetcher` — which
`validate_skill.py` had been warning about all along and which `analyze_gaps.py` began reading
only once the two gates' config keys were aligned.

`Language` went 27 → 28 the same way: a Red Flag added to `obsidian-cli` here says a template
"can carry" JS. Advisory, and left standing for the reason below.

`analyze_gaps.py` and `validate_skill.py` now return the same verdict on every one of the 22
skills, not only on `skills/pdf`.

Three qualifications on that sentence, all measured rather than assumed:

- **It is a property of the DEFAULT mode.** Under `--strict` the two disagree on 8 of the 22,
  because `--strict` promotes each tool's own advisory classes and those differ by design —
  `analyze_gaps.py` carries prose rules (`[Language]`) that the other gate has no counterpart
  for. `--strict` sweeps one tool's backlog; it is not a shared CI gate. Stated in
  `skill-creator/SKILL.md` and pinned by `test_strict_is_per_tool_and_the_docs_say_so`.
- **The exit codes are 0 because of a config file that is not in the repository.**
  `.agent/rules/skill_standards.yaml` is a symlink into a gitignored sibling checkout, and it
  sets `enforce_cso_prefix: false`. Rebuilt from `git ls-files` alone — the tree CI actually
  sees — `obsidian-cli` and `transcript-fetcher` exit 1 on **both** gates, on the CSO prefix.
  They did so at `2bc7ac8` too, so this is the repository's standing state and not a
  regression; the agreement property, which is what CI asserts, holds in both trees.
- **`skills/html` needed `git` on `PATH`** while the non-standard-directory finding was
  blocking, because the gitignore exemption shells out. That finding is now advisory —
  matching `validate_skill.py`, which has always reported it as a warning — so the verdicts
  agree with or without `git`. Pinned by `test_the_gates_agree_without_git_on_PATH`.

### What stands, and why

- **`Language` — 28 lines across 10 skills.** Advisory. Roughly 24 are a modal describing a
  tool's capability ("probes whether weasyprint **can** find its native libraries"), which is
  not an instruction at all; the rest are a graduated-wording call per instruction, which this
  record puts out of scope and `skill-enhancer` already states is not a mechanical
  should→MUST substitution. The class is reported on every run and does not gate.
- **`Execution Policy` — 2 across 2 skills.** Advisory, matching `validate_skill.py`, which
  has emitted the identical findings as passing warnings since the migration was declared. The
  32 missing-section advisories that stood when this record was written were closed by
  [WI-034](wi-034-execution-policy-migration.md); what remains is the
  `Validation Evidence is N lines` soft limit on `docx` and `transcript-fetcher`.

### Stated cost of the narrowing

The absolute-path rule is a denylist on the first segment, so a machine-specific path rooted
elsewhere stays silent: `/opt/homebrew/bin/soffice`,
`/Applications/LibreOffice.app/Contents/MacOS/soffice`, `/var/folders/xy/…/T/build.pdf`,
`/private/tmp/<session-uuid>/out.pdf`. An allowlist would catch those and would also fire on
`/scratch/…` and `/data/…` in ordinary prose. The denylist is the side that keeps the report
readable; the cost is written down — in the function's docstring and in
`KNOWN_FALSE_NEGATIVES` in `tests/test_rule_scoping.py`, so a later change that makes one of
them fire is a deliberate widening rather than a silent disagreement.

`/tmp` stays exempt although it does not exist on Windows. That portability question is
[WI-032](wi-032-windows-support.md), not this check.

### Changed

- `skills/skill-enhancer/scripts/analyze_gaps.py` — `mask_code` / `strip_quoted`,
  `is_machine_specific_path`, `_WINDOWS_PATH_RE`, `_TODO_MARKER_RE`,
  `_PLACEHOLDER_NOTATION_RE`, `_is_git_ignored`, `enforce_cso_prefix` /
  `inline_exempt_skills`, the `gaps` / `advisories` split with `--strict`, and file-relative
  line numbers (findings previously reported body-relative numbers, short by the length of
  the frontmatter — a location that does not resolve is a location nobody checks).
- `skills/skill-enhancer/scripts/tests/test_rule_scoping.py` — new; 26 cases, each narrowing
  pinned on both halves (what it now ignores, and the defect it must still catch).
- `skills/skill-enhancer/scripts/tests/test_stdout_broken_pipe.py` — fixture path moved from
  `/usr/local/lib/…` to `/home/builder/…`. Under the narrowed rule the old path is correct
  content, the fixture produced 0 gaps and a 632-byte report, and the broken-pipe test would
  have been green against broken code.
- `skills/skill-enhancer/SKILL.md` — Script Contract failure semantics, the advisory classes,
  the rule-scoping capability, and a Phase 3 verify step that says an advisory is closed by
  fixing it or by writing down why it stands, never by editing correct documentation.
- `skills/{html,obsidian-cli,skill-creator,skill-validator,text-humanizer}/SKILL.md` —
  Red Flags / Rationalization Table sections.
- `skills/{obsidian-cli,text-humanizer}/examples/usage.md` — new.


---

## Amendment (2026-09-02) — `required_sections` is advisory, in both gates

The first cut of this work made `validate_skill.py` block on
`validation.required_sections` so that it would agree with `analyze_gaps.py`,
which had always blocked on it. Aligning the two by raising the quieter one was
the wrong direction, and the measurement says so.

`analyze_gaps.py` is not the only consumer of these gates, and `skills/` is not
the only corpus. Measured across the three repositories that run them:

| Repository | Skills | Newly failing `validate_skill.py` |
|---|---|---|
| `Universal-skills` | 22 | 0 |
| `agentic-development` | 46 | **34** |
| `obsidian-llm-wiki` | 23 | **11** |

`agentic-development`'s CI gate runs this validator through
`System/scripts/validate_skills.py`; it went from 46/46 to 12/46. None of those
45 skills had changed. Red Flags and a Rationalization Table are a house
convention, not a structural requirement — `obsidian-llm-wiki` carries the same
material under a different notation, and a reference skill may legitimately
carry none.

So the rule is now **advisory in both gates**: reported on every run, in
`advisories` / `warnings`, promoted by `--strict`, and blocking nothing. Two
further rules that this work had newly made blocking were reverted for the same
reason — `prohibited_files` (never checked by `analyze_gaps.py` before) and the
unclosed-`~~~` error in `check_inline_efficiency` (a decorative `~~~~~~~~` line
would have read as an unterminated fence).

Re-measured after the climb-down: **zero skills anywhere fail a gate they used
to pass**, and `analyze_gaps.py` fails strictly fewer than before — 14 -> 0 here,
44 -> 24 in `agentic-development`, 23 -> 23 in `obsidian-llm-wiki`.

This also corrects the property this record claimed. "The two gates return the
same verdict on every skill" is repo-local and too strong to state generally:
`analyze_gaps.py` owns prose rules the structural gate has no counterpart for,
and those are its opinion, not a contradiction. The property that must hold, and
is now pinned by `test_a_rule_in_both_gates_carries_the_same_severity`, is that
**a rule implemented in both gates carries the same severity in both**.
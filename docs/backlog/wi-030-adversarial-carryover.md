---
id: WI-030
type: work-item
status: done
opened_at: 2026-08-14
slug: wi-030-adversarial-carryover
effort: M
value: M
source: vdd-enhanced-docx-obsidian (TASK 030, adversarial cycles 1-3)
resolved_at: 2026-08-29
resolved_by: WI-030 LOW slice — skills/docx/scripts/{_obsidian_lib.js,obsidian2md.js,tests/test_obsidian2md.py}
---

# WI-030 — TASK 030 adversarial carry-over: findings raised but never verified

> **Resolved 2026-08-29.** The remaining seven LOW findings were worked, so nothing in the
> historical table below is still carried. Two were live defects (`C5-07`, and an order
> dependency the `C5-14` census exposed), two were already closed by the MEDIUM slice, and
> the rest were mutation survivors. 19 tests added (157 → 176); 14 mutations applied to the source and every one
> killed. The carry-over is closed — not because the budget ran out this time, but because
> nothing is left carried.

## What this is

The three adversarial cycles on TASK 030 raised more findings than the rounds had budget to
verify. Every cycle verified only its highest-severity slice, and the rest were carried
forward. This record is where the remainder stops being carried and starts being tracked, so
that "3 cycles ran" is not mistaken for "everything raised was examined".

**Nothing here is a known defect.** These are unverified claims. On this codebase the
verification pass has been decisive in both directions: cycle 1 confirmed 10 of 10, cycle 2
confirmed 6 of 6, cycle 3 confirmed 5 and refuted 1 outright (right symptom, wrong cause,
inflated severity). An unverified finding is as likely to be wrong as right.

## Status of the three cycles

| Cycle | Raised | Verified | Confirmed | Refuted | Carried |
|---|---|---|---|---|---|
| 1 | 76 | 10 | 10 | 0 | 66 |
| 2 | 55 | 6 | 6 | 0 | 49 |
| 3 | 60 | 6 | 5 | 1 | 54 |
| 4 | 44 | 8 | 8 | 0 | 36 |
| 5 | 22 | 8 | 8 | 0 | 14 |

Cycle 2 also lost two triage agents to API errors; cycle 3 re-ran those slices. Across cycles
2 and 3 the triagers cleared **91** carried findings explicitly — already fixed, or wrong.

## MEDIUM slice — worked and closed (2026-08-14)

All seven MEDIUM findings were verified against the code as it stood, not accepted on report.

| ID | Verdict | Outcome |
|---|---|---|
| C5-05a paragraph blank-line injection | **already fixed** | closed by cycle 5's `splice` rewrite; re-verified, not re-fixed |
| C5-06 blank run in indented code deleted | **live** | fixed — every blank of the run is kept; masking is reversible again |
| C5-05b sentinel forgeable via NUL | **live** | fixed — control characters stripped before masking (XML 1.0 forbids them regardless) |
| C5-04 diamond read as a cycle | **live** | fixed — `visited` is an on-path set, cleared on unwind; a true cycle is still caught |
| C5-08 depth cap untested | **coverage gap** | test added; the cap could be disabled with the suite green |
| C5-10 `render` multi-value untested | **coverage gap** | test added; dropping every value but the first passed the suite |
| C5-11 six R5 sub-features untested | **coverage gap** | five tests added; the sixth (symlink guard) is defensive redundancy — `readdir` already reports a symlinked directory as `isDirectory() === false`, measured and recorded in the test |

13 new tests, 11 of 12 mechanisms proven load-bearing by mutation. The NFC test needed a
second attempt: the first used a Cyrillic name with no decomposition, so NFD and NFC were the
same string and it asserted nothing.

## LOW slice — worked and closed (2026-08-29)

Seven independent verifications, each re-attacked by a second agent told to refute it. That
second pass earned its place twice: it downgraded `C5-14`'s headline ("no test at all" was
false — `TestCliContract` covers 8 of 11 exits) and, on `C5-07`, it found a **second door the
first fix had left open**. Verdicts were taken from runs, not reports.

| ID | Verdict | Outcome |
|---|---|---|
| C5-07 tab-indented ``` | **live, BOTH ends** | fixed — a fence's indent is now measured in columns against the container's bound, on the opener *and* the closer |
| C5-08 NUL sentinel claim | **already fixed** | closed by the MEDIUM slice's `stripControlChars`; the comment that carried the false claim now states the opposite, and a test locks it |
| C5-06 blank run in indented code | **already fixed** | the LOW restatement of the MEDIUM finding; locked by two tests, re-verified rather than re-fixed |
| C5-09 8-pass unmask fixpoint | **unreachable, and unlocked** | the loop is kept as the exported function's contract, its false rationale comment replaced with the measured one, and a unit test on a hand-built nested store kills the `< 1` mutant |
| C5-12 three unlocked mechanisms | **2 live gaps, 1 refuted** | R8(e) callout separation and R12(a)'s existence guard were survivors and are locked; the R3(g) size branch was already locked — but the *transport* half (consuming the alt prefix) was not, nor was R3(h)'s never-upscale invariant. Both now are |
| C5-13 `FRONTMATTER_SUPPRESS` | **dead code, confirmed** | not wired in — a denylist after an allowlist can never fire and would veto a later addition. Kept as the R2(f) declaration, honestly documented as such, and enumerated by a test that converts a note carrying all 13 keys |
| C5-14 CLI error paths | **headline refuted, 4-item gap live** | the census found 8 of 11 obsidian2md exits and 4 of 5 md2docx ones already covered. What it *did* surface was a live defect: `--json-errors` was read by the parse loop, so a flag standing to its left errored in plain text — a machine-readable contract that depended on argument order. Fixed by a pre-scan. Three untested exits locked, including the `realpath` arm of the exit-6 guard, whose cost is the note itself |

**`C5-07` was the one worth the cycle.** The opener half froze the prose between two
tab-indented fences. The closer half is worse and was found only by the agent sent to refute
the fix: a tab-indented bare ``` *inside* a real fenced block ended it early, so the rest of
that block was rewritten — `[[link]]` unwrapped, `==hi==` bolded, the mask editing the code it
exists to protect — and the genuine column-0 closer then opened a fence that ran to EOF. The
trailing prose reached the .docx literally and `--strict-assets` exited **0** on an unresolved
embed sitting inside the frozen region. Same silent-loss class as cycle 1's CRITICAL, third
door.

**Honest scope on that second door.** It needs a bare ``` or `~~~` line inside an open fenced
block whose indent is >=4 columns but <=3 characters — i.e. tab-led. Grepping every `.md` in
this repository for that shape returns **zero** hits, so "a normal note triggers it" is not
supported and the surviving half grades MEDIUM, not HIGH. The opener half is the broadly
reachable one. What earns the fix anyway is the blast radius once it does trigger: the mask
edits the code it protects, and the freeze runs to EOF with the one flag that exists to refuse
that silently returning 0.

Every fix is pinned by a mutation that was actually run: 14 applied to the source, suite
executed, source restored, all 14 killed. Two of them were mutations of the *fix itself* — a
flat indent limit ignoring the list context, and a closer bound pinned to the opener — and the
first test written for each survived, so both tests were rebuilt until they did not.

## What the cycles raised and carried (historical)


Severity counts as they stood on 2026-08-14: **7 LOW** — the 7 MEDIUM were worked
(see above); no CRITICAL or HIGH remained. **All 14 rows below are now worked** — the
MEDIUM ones on 2026-08-14, the LOW ones on 2026-08-29. The table is kept as the record
of what was raised, not as a list of what is open.

| Severity | ID | Title |
|---|---|---|
| MEDIUM | `C5-05` | A collapsing paragraph prepends spurious blank lines, loosening or splitting lists |
| MEDIUM | `C5-06` | A run of blank lines inside an indented code block collapses to a single blank line |
| MEDIUM | `C5-04` | A note reached twice through DIFFERENT transclusion paths (a diamond, not a cycle) is silently degraded to a pointer line and mis-reported as a "trans |
| MEDIUM | `C5-05` | I4 sentinel collision is reachable: a NUL byte in the note's own text lets note content inject stored code regions, or leave a literal `obsmask` in th |
| MEDIUM | `C5-08` | MUTATION SURVIVOR — R12(c) `depth ≤ 3` has no test at all; MAX_TRANSCLUDE_DEPTH can be disabled with 135/135 green |
| MEDIUM | `C5-10` | MUTATION SURVIVOR — `--frontmatter render` multi-value branch is untested; dropping every value but the first passes 135/135 |
| MEDIUM | `C5-11` | MUTATION SURVIVOR — six of R5's lettered sub-features have no test: NFC folding (d), the ambiguity warning (e), the vault-root walk-up (f), SKIP_DIRS  |
| LOW | `C5-07` | A tab-indented ``` line is read as a fence (CommonMark reads it as indented code), freezing the real paragraph between the two |
| LOW | `C5-08` | The 'NUL cannot occur in a note' claim at line 122 is false; a crafted note substitutes an unrelated code region into its prose |
| LOW | `C5-06` | A run of two or more blank lines inside an indented code block is collapsed to one (R10a inertness) |
| LOW | `C5-09` | MUTATION SURVIVOR — the 8-pass unmask fixpoint is unreachable defensive code; collapsing it to one pass is invisible to the suite |
| LOW | `C5-12` | MUTATION SURVIVOR — R8(e) callout body separation, R3(g) single-word size hint, and the existence guard in transclusion image re-rooting are all unloc |
| LOW | `C5-13` | `FRONTMATTER_SUPPRESS` is dead code — the constant R2(f) names is never consulted; suppression is an accident of the FRONTMATTER_KEYS allowlist |
| LOW | `C5-14` | Error paths with no test at all in obsidian2md.js and md2docx.js --obsidian |

## How this was worked

Verified by hand in severity order. The discipline that worked, and that this record exists to
pass on: build the claimed input under `/tmp`, run it, and **refute unless it reproduces** —
then, for anything that reproduces, mutate the fix and make the new test fail before believing
it. Two of the tests written here passed against their own mutant on the first attempt and had
to be rebuilt; a test that cannot fail is a coverage gap wearing a green tick.

Send a second agent to refute each verdict. It cost one extra pass and it is what found the
closer half of `C5-07`, which is worse than the half that was reported.

[`docs/tasks/task-030-docx-obsidian-support.md`](../tasks/task-030-docx-obsidian-support.md)
(R1-R17, A1-A16) is the contract; every requirement touched here carries the finding inline in
its own RTM cell.

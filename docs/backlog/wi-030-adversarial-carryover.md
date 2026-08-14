---
id: WI-030-carryover
type: work-item
status: open
effort: M
value: M
source: vdd-enhanced-docx-obsidian (TASK 030, adversarial cycles 1-3)
---

# WI-030 — TASK 030 adversarial carry-over: findings raised but never verified

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

## What remains unverified after cycle 5


Severity counts: **7 LOW** — the 7 MEDIUM were worked (see above); no CRITICAL or HIGH remains.

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

## How to work this

Verify by hand in severity order, or re-run the cycle-5 workflow with the cap raised. The
discipline that worked: build the claimed input under `/tmp`, run it, and refute unless it
reproduces. `docs/TASK.md` (R1-R17, A1-A16) is the contract.

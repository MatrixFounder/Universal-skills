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

Cycle 2 also lost two triage agents to API errors; cycle 3 re-ran those slices. Across cycles
2 and 3 the triagers cleared **91** carried findings explicitly — already fixed, or wrong.

## What remains unverified after cycle 4

Severity counts: {'MEDIUM': 23, 'LOW': 10, 'HIGH': 3}

| Severity | ID | Title |
|---|---|---|
| HIGH | `C4-01` | H2's parent re-mask calls applyMasks() with NO store, so H1's list-state fix is dead on the transclusion path — `#include <stdio.h>` becomes `<stdio.h |
| HIGH | `C4-02` | Nested transclusion (A embeds B embeds C): C is re-masked into the TOP-level store while B unmasks with its OWN store — the index collides and C's cod |
| HIGH | `C4-03` | H1 decides on raw indentation, so a code fence indented by 1-3 spaces never closes the list — V3-03 / G1-R1 still real, one space away from the fixed  |
| MEDIUM | `C4-06` | H3's demote handles only ATX headings — a transcluded note written with setext headings keeps its H1, producing two H1s in the document |
| MEDIUM | `C4-07` | On a CRLF note the tag-strip tidy is `\r`-blind and INTRODUCES a Markdown hard line break the author never wrote |
| MEDIUM | `V4-02` | Diamond transclusion (A->B->D, A->C->D) is misdiagnosed as a cycle: the second copy of D is dropped with a false 'transclusion cycle' warning |
| MEDIUM | `V4-03` | absolutiseRelativeImages silently declines any bare destination containing '(' — including the OS-default `Screenshot (1).png` — so a transcluded imag |
| MEDIUM | `C4-03` | H4: a tag-only line inside a table body is emptied, truncating the table — the rows after it render as literal pipe text in the .docx |
| MEDIUM | `C4-09` | The R4(a) and R4(e) locks stay green with the entire wikilink rewrite disabled |
| MEDIUM | `C4-10` | R11(e) flag forwarding on the one-command route is untested: md2docx.js can ignore --frontmatter/--lang/--links/--inline-tags values and all 127 tests |
| MEDIUM | `C4-11` | R5 asset resolution is covered only by its refusal paths: eight resolution behaviours can be deleted with the suite still green, including the test na |
| MEDIUM | `C3-05` | R9(d) task boxes are not converted inside a callout/blockquote body, and md2docx renders the whole blockquote list as one raw-markdown run in Word |
| MEDIUM | `V3-09` | absolutiseRelativeImages' isFile guard turns a transcluded note's missing relative image into a SILENTLY WRONG image rather than a warning |
| MEDIUM | `L-6` | Wikilinks inside frontmatter values reach the Word document literally — A2's `grep -o '\[\[' \| wc -l == 0` fails on an ordinary meeting note |
| MEDIUM | `L-7` | The `w=NNN\|` size-hint alt prefix injects a raw pipe into a GFM table cell — the row splits, the image is lost and the neighbouring cell is dropped |
| MEDIUM | `L-8` | Obsidian's escaped pipe `![[pic.png\\|300]]` — the documented way to embed a sized image inside a table — is parsed as a filename ending in a backslash |
| MEDIUM | `L-10` | A diamond — one note embedded twice — is misreported as a transclusion cycle and the second body is dropped |
| MEDIUM | `L-11` | The inline code-span mask spans blank lines, so two stray backticks in separate paragraphs hide everything between them from every rewrite — silent im |
| MEDIUM | `L-12` | safeDestination does not escape backslashes, so a path segment containing `\` + ASCII punctuation is unescaped by marked and md2docx hard-fails exit 1 |
| MEDIUM | `L-14` | A `~~~` fence closed by a longer `~~~~` is treated as unterminated and masks the rest of the document — silent loss with --strict-assets still green |
| MEDIUM | `CALLOUT-1` | `==highlight==` in a callout title produces nested emphasis, so literal `**` characters are typed into the Word document |
| MEDIUM | `DOC-3` | SKILL.md §5 / arch §8.3 'directory symlinks are never followed … no escape through a linked folder' is false at resolveAsset — a directory symlink in  |
| MEDIUM | `DOC-4` | 'The vault-wide index is built at most once per run' (TASK R5g, SKILL.md §5, arch-011 §8 Cost bound) is false under --transclude — three full vault wa |
| MEDIUM | `DOC-7` | SKILL.md §6 still claims the acceptance set is '90 cases'; the file now holds 127 tests |
| MEDIUM | `SEC-3` | Quadratic scanning in the converter's regexes with no input size cap: 400 KB of unclosed `[[` costs 49 s |
| MEDIUM | `G5-SEC1` | absolutiseRelativeImages adds a third quadratic regex on the transclusion path — a 300 KB child note costs 16.5 s where the same file costs 0.03 s at  |
| LOW | `C4-08` | A literal NUL sentinel in a note body is substituted from the store — the 'NUL cannot occur in the source text of a note' comment is an unguarded assu |
| LOW | `C4-09` | `/(\d+)/` reads only the FIRST index on a mask-only line, and `maskIndentedBlocks` has no defence if a line ever carries two sentinels |
| LOW | `V4-04` | The 'no user content can collide with the sentinel' claim at line 122 is false — a note carrying literal NUL bytes injects arbitrary store content int |
| LOW | `V4-05` | H4 residue confirmed visible in the .docx: a tag removed from the MIDDLE of a line leaves a double space, emitted with xml:space="preserve" |
| LOW | `C4-04` | H4: a tag removed from mid-line leaves a double space that reaches the document |
| LOW | `C4-05` | H4: a tagged line loses its Markdown hard line break to the trailing-edge trim |
| LOW | `C4-06` | md2docx.js drops marked `br` tokens entirely, so a preserved Markdown hard line break glues the two words together in the .docx |
| LOW | `C4-07` | H4: a tag-only line splits a paragraph, and `> #tag` splits a blockquote, into two paragraphs in the .docx |
| LOW | `C4-08` | A literal `NUL obsmask<n> NUL` in a note's bytes is unmasked into that note's own code region |
| LOW | `C4-12` | Three tests cannot fail through the guard they are named for |

## How to work this

Re-run the cycle-4 workflow with the verification cap raised, or verify by hand in severity
order. The reproduction discipline that worked: build the claimed input under `/tmp`, run it,
and refute unless it reproduces. `docs/TASK.md` (R1-R17, A1-A16) is the contract to judge
against. Cycle 4's own triage cleared 47 carried findings explicitly.

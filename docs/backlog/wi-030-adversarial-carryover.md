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

Cycle 2 also lost two triage agents to API errors; cycle 3 re-ran those slices. Across cycles
2 and 3 the triagers cleared **91** carried findings explicitly — already fixed, or wrong.

## What remains unverified after cycle 3

Severity counts: {'MEDIUM': 23, 'LOW': 31}

| Severity | ID | Title |
|---|---|---|
| MEDIUM | `C3-05` | R9(d) task boxes are not converted inside a callout/blockquote body, and md2docx renders the blockquote list as raw markdown text in Word |
| MEDIUM | `V3-03` | G1 regression: the MASK_ONLY_LINE step-over makes a genuine indented code block after a fence get rewritten |
| MEDIUM | `V3-04` | G2 does not cover blockquote/callout indentation: tag stripping still flattens a nested list inside a callout |
| MEDIUM | `V3-05` | Heading demotion in transclude() runs AFTER unmaskCode, so it edits restored code blocks |
| MEDIUM | `V3-06` | The whole transclusion rewrite pipeline can be deleted with 119/119 still green |
| MEDIUM | `V3-09` | G5's isFile guard converts a wrong-directory image into a SILENTLY wrong image rather than a warning |
| MEDIUM | `G1-R1` | G1 REGRESSION — a masked fence now carries stale list state, so a real indented code block after a list+fence is left unmasked and its contents are re |
| MEDIUM | `G2-R1` | G2 is incomplete — inside a blockquote or callout, a tag-bearing nested list line still loses its indentation and is promoted out of its parent |
| MEDIUM | `G5-R1` | G5 misses the CommonMark title and angle-bracket destination forms, so a transcluded note silently embeds the WRONG image from the parent note's direc |
| MEDIUM | `L-6` | Wikilinks inside frontmatter values reach the document literally — A2's `grep -o '\[\[' \| wc -l == 0` fails on a real note |
| MEDIUM | `L-7` | The `w=NNN\|` size-hint alt prefix injects a raw pipe into a GFM table cell — the row splits, the image is lost and the neighbouring cell is dropped, s |
| MEDIUM | `L-8` | Obsidian's escaped pipe `![[pic.png\\|300]]` — the documented way to embed inside a table — is parsed as a filename ending in a backslash and the image |
| MEDIUM | `L-9` | Transclusion demotes headings AFTER unmaskCode, so `#` comment lines inside the transcluded note's fenced code blocks are rewritten (R10 violation) |
| MEDIUM | `L-10` | A diamond — one note embedded twice — is misreported as a transclusion cycle and the second body is dropped |
| MEDIUM | `L-11` | The inline code-span mask spans blank lines, so one unmatched backtick disables conversion for the rest of a region — silent image loss at exit 0 |
| MEDIUM | `L-12` | safeDestination does not escape backslashes, so a path segment beginning with ASCII punctuation loses its separator — reproduced as a hard exit-1 on m |
| MEDIUM | `L-14` | A `~~~` fence closed by a longer `~~~~` is treated as unterminated and masks the rest of the document — silent loss with `--strict-assets` still green |
| MEDIUM | `CALLOUT-1` | `==highlight==` in a callout title produces nested emphasis, so literal `**` characters are typed into the Word document |
| MEDIUM | `DOC-3` | SKILL.md §5 / arch §8.3 "directory symlinks are never followed … no escape through a linked folder" is still false at resolveAsset — the attachmentFol |
| MEDIUM | `DOC-4` | "The index is built at most once per run" is still false under --transclude — three full vault walks in one run |
| MEDIUM | `DOC-7` | SKILL.md §6 still claims "Full acceptance set (A1-A16) … 90 cases"; the file has 119 tests and its own docstring says A11 is NOT wired |
| MEDIUM | `SEC-3` | Polynomial (quadratic) scanning in the converter's regexes with no input size cap: 400 KB of unclosed `[[` costs 7.4 s, 1 MB ≈ 46 s |
| MEDIUM | `G5-SEC1` | NEW regression in cycle-2 fix G5: absolutiseRelativeImages adds a third quadratic regex on the transclusion path — the SAME 300 KB file costs 0.02 s a |
| LOW | `C3-06` | Indented code block placed immediately after a closing fence (no blank line) is never masked |
| LOW | `C3-07` | G3's `/^\d+$/` numeric test is ASCII-only while the tag body class is `\p{N}` — non-ASCII numeral references are deleted from prose |
| LOW | `C3-08` | The mask sentinel is forgeable: a note containing the literal bytes `\x00obsmask<N>\x00` gets a code block's contents injected at that spot |
| LOW | `C3-09` | obsidian2md.js silently accepts single-dash tokens as positionals and ignores extra positionals — `-o out.md` writes a file literally named `-o` |
| LOW | `V3-07` | FRONTMATTER_SUPPRESS is dead code — emptying it changes nothing and kills no test |
| LOW | `V3-08` | The R6(c) silent-loss guard is blinded by its own `(?!<)`, and the test locking that guard cannot fail |
| LOW | `V3-10` | Eleven further behaviours survive deletion with 119/119 green, including two security guards |
| LOW | `L-15` | A UTF-8 BOM defeats frontmatter detection and the raw YAML is rendered into the document |
| LOW | `L-16` | An empty frontmatter block `---\n---` is not recognised and leaks two thematic rules into the document |
| LOW | `L-17` | Flow-list frontmatter is split on every comma, including commas inside quoted scalars |
| LOW | `L-18` | Nested callouts are not rewritten and the raw `[!type]` marker reaches the document (R8's headline sentence is unconditional) |
| LOW | `L-21` | Section transclusion `![[Note#Heading]]` silently inlines the WHOLE note, and the +1 demotion makes it a sibling of the embedding section |
| LOW | `L-22` | The vault index is rebuilt once per transcluded note — R5(g)/SKILL.md §5's 'built at most once per run' is false |
| LOW | `L-24` | Literal NUL bytes in the mask sentinel make _obsidian_lib.js a binary file to git, grep and file(1) |
| LOW | `L-25` | FRONTMATTER_SUPPRESS is dead code whose comment claims to implement R2(f) |
| LOW | `L-26` | md2docx.js's temp-dir comment names a `finally` in the writer that does not exist |
| LOW | `CALLOUT-2` | Task boxes inside a callout or blockquote body are not converted, so the literal `[ ]` / `[x]` reaches the Word document |
| LOW | `L-23` | buildVaultIndex's 200000-entry budget truncates the index silently and is indistinguishable from a genuine miss |
| LOW | `G3-R1` | G3's `/^\d+$/` guard is ASCII-only while the tag body class is `\p{N}`, so a purely-numeric reference written in non-ASCII digits is stripped |
| LOW | `DOC-5` | All three `md2docx.js:NNN` citations in _obsidian_lib.js comments are still wrong, and the repair passes added two more stale line self-references ins |
| LOW | `DOC-6` | docs/TASK.md RTM anchors: two were repaired, two are still stale, and the repaired R3(h) anchor misses the invariant it names by five lines |
| LOW | `DOC-8` | arch-011 §8.3 still opens on two false premises: "the first docx capability that reads files the user did not name" and "nothing outside the named out |
| LOW | `DOC-9` | arch-011 §8.3 still says the SKILL.md §5 widening has not landed yet, and SKILL.md §5's two bullets state opposite scopes |
| LOW | `DOC-11` | "`w=NNNxMMM` takes both dimensions literally, then scales them down together" — each dimension is clamped independently, so the rendered box is neithe |
| LOW | `DOC-12` | buildVaultIndex's docstring still explains an `lstatSync` the file does not contain |
| LOW | `DOC-13` | The multi-value `<br>` cell claim ("md2docx's inline text path — each value its own run") describes a mechanism that does not run; each value is its o |
| LOW | `DOC-14` | SKILL.md §4 still states plain-CommonMark byte-identity without the trailing-LF caveat that R14(b), A10 and arch §8.6 all carry |
| LOW | `DOC-15` | "NUL … cannot occur in the source text of a note, so no rule and no user content can collide with it" — a note carrying the sentinel bytes DOES forge  |
| LOW | `SEC-4` | The 200 000-entry index bound is multiplied by the transcluded-note count (same root cause as DOC-4, stated here as the resource bound) |
| LOW | `SEC-6` | arch §8.6 "the temp directory is removed on success and on failure … a failed run leaves nothing behind" is false for SIGINT/SIGTERM — the note's full |
| LOW | `G5-L1` | NEW gap in cycle-2 fix G5: when the transcluded note's relative image does not exist beside it, the isFile guard keeps the relative path and md2docx s |

## How to work this

Re-run the cycle-3 workflow with the verification cap raised, or verify by hand in severity
order. The reproduction discipline that worked: build the claimed input under `/tmp`, run it,
and refute unless it reproduces. `docs/TASK.md` (R1-R17, A1-A16) is the contract to judge
against.

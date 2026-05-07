# Task 1.05: [STUB CREATION] Doc stubs (SKILL.md updates + reference + example)

## Use Case Connection
- I4.2 (Skill docs + reference).
- RTM: prepares R10 verification.

## Task Goal
Create the documentation surface so the script is discoverable and the OOXML pitfalls are documented BEFORE the developer writes the implementation. Doc stubs are intentional placeholders — they will be polished in task 2.10.

## Changes Description

### New Files

- `skills/xlsx/references/comments-and-threads.md` — STUB section headings + a "Pitfalls" section that already documents C1 + M-1 (so the developer reads them before writing scanner code).
- `skills/xlsx/examples/comments-batch.json` — flat-array shape, ≤ 5 rows, illustrative.

#### Concrete contents

**`comments-and-threads.md` skeleton:**
```markdown
# OOXML comments and threads in `xlsx_add_comment.py`

> Reference doc for the data model behind `xlsx_add_comment.py`. See
> [`scripts/xlsx_add_comment.py`](../scripts/xlsx_add_comment.py) for
> the CLI; this doc explains *why* the OOXML edits happen the way
> they do.

## 1. Part graph
*(stub — final polish in task 2.10)*

## 2. Cell-syntax (`--cell`) reference
*(stub — final polish in task 2.10)*

## 3. Pitfalls (the C1 + M-1 list)

### 3.1 `<o:idmap data>` is a comma-separated LIST, not a scalar (M-1)
ECMA-376 / VML 1.0 specifies `<o:idmap data>` as a comma-separated list
of integer shape-type IDs claimed by the drawing. A naive scalar parse
silently corrupts heavily-edited workbooks where Excel emitted multi-
claim lists like `data="1,5,9"`. **The scanner must parse the full list.**

### 3.2 `<o:idmap data>` and `o:spid` are TWO different collision domains (C1)
- `<o:idmap data>` integers must be **workbook-wide unique across all
  `vmlDrawing*.xml` parts**.
- `<v:shape o:spid>` integers must be **workbook-wide unique across
  all VML parts**.
- They are NOT the same thing. Conflating them was the round-1 mistake.

### 3.3 `personList` is workbook-scoped, NOT sheet-scoped (M6)
The `personList` rel goes on `xl/_rels/workbook.xml.rels`, not on a sheet
rels file. The `threadedComment` rel goes on the sheet rels file. Both
are required for Excel-365 to render the thread.

### 3.4 `commentsN.xml` part-counter is independent of sheet index
A workbook with three sheets where only Sheet3 has comments stores them
in `xl/comments1.xml` (NOT `xl/comments3.xml`). The binding to Sheet3
goes through `xl/_rels/sheet3.xml.rels`, not through filename collision.

## 4. Honest scope (v1)
*(stub — repeats R9.a–g from TASK; final polish in task 2.10)*
```

**`examples/comments-batch.json`:**
```json
[
  {"cell": "A2", "author": "Validator", "text": "Hours field should be numeric."},
  {"cell": "Sheet2!B5", "author": "Validator", "text": "Date out of expected range.", "threaded": true},
  {"cell": "'Q1 2026'!A1", "author": "Validator", "text": "Quarter header missing.", "initials": "VL"}
]
```

### Changes in Existing Files

#### File: `skills/xlsx/SKILL.md`

- **§2 Capabilities:** Add bullet — *"Insert an Excel comment (legacy `<comment>`, optionally with the threaded-comment + personList Excel-365 modern layer) into a target cell, with cross-sheet syntax and a batch mode that auto-detects the xlsx-7 findings envelope."*
- **§4 Script Contract:** Add CLI signature — `python3 scripts/xlsx_add_comment.py INPUT.xlsx OUTPUT.xlsx (--cell REF --author NAME --text MSG | --batch FILE [--default-author NAME] [--default-threaded]) [--threaded | --no-threaded] [--initials INI] [--date ISO] [--allow-merged-target] [--json-errors]`.
- **§10 Quick Reference:** Add row — `| Insert comment(s) | python3 scripts/xlsx_add_comment.py file.xlsx out.xlsx --cell A5 --author "..." --text "..." [--threaded]` (or batch: `... --batch findings.json --default-author "..."`) `|`.
- **§12 Resources:** Add 2 links — `[scripts/xlsx_add_comment.py](scripts/xlsx_add_comment.py)` and `[references/comments-and-threads.md](references/comments-and-threads.md)`.

### Component Integration
- Doc files live next to existing references (`financial-modeling-conventions.md`, `formula-recalc-gotchas.md`, `openpyxl-vs-pandas.md`, `xlsx-rules-format.md`).
- The "Pitfalls" section in §3 of the new reference is INTENTIONALLY frontloaded so it shows up early when the developer skims the doc during implementation.

## Test Cases

### End-to-end Tests
- `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` should NOT regress (must still exit 0). If validate_skill.py checks for broken links, the §12 additions must resolve.

### Unit Tests
*(none — docs only)*

### Regression Tests
- `validate_skill.py skills/xlsx` exit 0.

## Acceptance Criteria
- [ ] `references/comments-and-threads.md` exists with the §3 Pitfalls section fully written (NOT a stub for §3 — only §1, §2, §4 are stubs).
- [ ] `examples/comments-batch.json` exists with ≥ 3 rows.
- [ ] `SKILL.md` §2 / §4 / §10 / §12 updated.
- [ ] `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx` exits 0.
- [ ] All markdown links resolve (relative paths only per `skill-planning-format` §4).
- [ ] **§1 stub of `references/comments-and-threads.md` quotes the backlog xlsx-6 use-case verbatim** — i.e. the §1 opens with the Russian text from `docs/office-skills-backlog.md` line 191 Notes column: *"validation-агент (xlsx-7 pipe) расставляет замечания на проблемные ячейки timesheet/budget/CRM-export"* — followed by an English gloss. (TASK round-1 m7 lock per plan-review J-2.)
- [ ] No edits to `skills/docx/scripts/office/` (CLAUDE.md §2).

## Notes
- The reference doc's §3 Pitfalls section is the load-bearing part for this task — it locks in the C1 / M-1 / M6 contract before code lands.
- §1, §2, §4 of the reference are stubs only because the data model details still benefit from being written *after* the developer has touched the actual XML (more accurate descriptions). Polished in task 2.10.

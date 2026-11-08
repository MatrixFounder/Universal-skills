# Artifact Type Guide — immutability contracts & edit formats

`detect_artifact_type.py` classifies the target; `check_immutability.py`
enforces the contract; `apply_proposal.py` performs the surgical edit. The
immutability check is a **subset** check (`before ⊆ after`): additions are
allowed, but changing or removing an existing immutable signature is a
violation that triggers a revert.

| Type | Detected by | Mutable (Proposer may change) | Immutable (rejected pre-apply + re-checked) | Edit formats |
|---|---|---|---|---|
| `skill` / `full-skill` | dir contains `SKILL.md` | body `## sections`, frontmatter `description`/`version` | frontmatter `name`, `tier`; the `evals/` harness (every file hashed) | `section-replace`, `frontmatter-field` (description/version) |
| `prompt` | `.md`/`.txt`/`.prompt` file | prose, `## sections` | `{{placeholders}}` (must all survive) | `section-replace` |
| `workflow` | under `workflows/`/`commands/` | step prose, ordering | YAML frontmatter keys, tool-invocation names | `section-replace` |
| `dataset` | `evals.json` / list / `{evals|results|cases:[...]}` | add cases; refine non-immutable fields | existing cases' `id`, `skill_name`, `grader`, file refs; no removals | `dataset-op` (`add`, `modify`) |
| `text` | explicit `--artifact-type text` + `--criteria rubric.md` | the whole prose body | nothing within the text (the rubric is a SEPARATE file = the harness) | `text-replace` (scoped find/replace) |

## Edit formats

All edits are **scoped, structured operations** — there is intentionally NO
raw-diff format. (A `unified-diff` format was removed because applying
attacker-controlled diffs via `git apply --unsafe-paths`/`patch` let a Proposal
escape the artifact scope and tamper with the immutable eval harness.)

- **`section-replace`** — replaces one `## Header` section body. `new_content`
  MUST begin with the same header (no rename). Frontmatter is preserved.
- **`frontmatter-field`** — sets one mutable frontmatter field
  (`description`/`version`). `name`/`tier` are rejected.
- **`dataset-op`** — `[{"op":"add","item":{...}}]` or
  `[{"op":"modify","id":"X","fields":{...}}]`. `modify` may not touch
  `id`/`skill_name`/`grader`/file-refs; `remove` is disallowed.
- **`text-replace`** — `{find, replace}` applied to the artifact's own text
  (exact, else whitespace-tolerant; `find` capped at 4096 chars). Scoped to the
  artifact string only — no file paths, no scope escape. Used for `text` prose
  improvement. Note: the whitespace-tolerant rung treats any whitespace run as
  flexible, so a fuzzy match can span a blank-line/heading boundary — the
  pairwise gate is the backstop against a bad splice.

## Protected sections and the deletion guard

- **`--protect "## Header"`** (repeatable) adds the full text of that section to
  the immutable signatures. A `section-replace` aimed at it is rejected before
  apply; any other edit that changes it (e.g. a `text-replace`) fails the
  post-apply subset check and is reverted. A header the artifact does not
  contain aborts the run (exit 2). Not for datasets.
- **Deletion guard** (`check_immutability.shrink_violation`, on unless
  `--allow-deletions`): an edit is rejected as `shrink-guard` when it removes a
  whole section (or the preamble), cuts more than 50 % of a section's non-blank
  lines, or lowers the number of lines containing MUST / NEVER. Rewording such a
  line is allowed. A document without `##` sections is treated as one section.
  Why: an eval case protects only what it measures; content no case touches can
  be cut without the score moving.

## Why immutability is a subset check
A plain hash-equality check would flag legitimate dataset additions (a new
case adds a new signature) as violations. The subset rule (`immutable_preserved`)
allows additions while still catching any change to — or removal of — an
existing immutable part. See `check_immutability.immutable_signatures`.

# Cross-Course Promotion / Demotion — Operator Playbook

This reference documents the two-tier vault model introduced in TASK 016
and the `promote` / `demote` subcommands that maintain it.

> **TL;DR**: When the same concept appears across multiple courses, run
> `wiki-ingest promote "<Name>" --vault <vault>` (dry-run by default;
> add `--apply` to commit). To reverse, `wiki-ingest demote "<Name>"
> --to "<Course>" --vault <vault>`. `lint` bracket-checks before/after.

---

## 1. Two-tier vault model

A vault with cross-course shared concepts looks like:

```
<vault>/                                   # ← Obsidian vault root
├── WIKI_SCHEMA.md                         # schema_version: 2.0, kind: vault-root
├── _concepts/                             # shared concepts (lazy)
├── _entities/                             # shared entities (lazy)
├── index.md                               # (optional) catalog
└── Lessons/                               # convention, NOT hardcoded
    ├── Course A/                          # schema_version: 1.x
    │   ├── WIKI_SCHEMA.md
    │   ├── _sources/  _concepts/  _entities/
    │   ├── index.md  log.md
    └── Course B/                          # same
```

`Lessons/` is the conventional grouping segment but NOT hardcoded:
`wiki-ingest` discovers courses by walking every descendant directory
with a `schema_version: 1.x` schema. Course-of-courses layouts
(`Lessons/2026/Spring/Hermes/`) are supported.

### Load-bearing invariant — one-page-one-place

A given canonical filename (e.g. `Sharpe Score.md`) lives in **exactly
one** of:

- some course's `_concepts/`/`_entities/`, OR
- the vault root's `_concepts/`/`_entities/` (shared layer).

Never both. `wiki-ingest lint <vault>` detects violations and exits
non-zero (R6.2 hard failure).

---

## 2. When to promote

Run `lint` periodically. When it reports:

```json
"cross_course_duplicate": [
  {"name": "Sharpe Score", "kind": "concept",
   "courses": ["Lessons/Hermes/_concepts/Sharpe Score.md",
               "Lessons/OpenClaw/_concepts/Sharpe Score.md"],
   "suggest": "wiki-ingest promote \"Sharpe Score\""}
]
```

…inspect the two pages. If they describe the **same concept** (operator
judgement — the skill never auto-decides; spec §6.1), run promote.

If they describe **different concepts that happen to share a name**
(e.g. `Pipeline` in an ML course vs `Pipeline` in DevOps), rename one
in its course's `_concepts/` first. The skill does not reconcile
semantically distinct same-name pages.

---

## 3. How to promote

```bash
# Step 1 — dry-run (default; no writes)
python3 scripts/wiki_ops.py promote "Sharpe Score" --vault <vault>
```

Inspect the printed `PromotionPlan` JSON. Key fields:

- `mode`: `"first_promote"` (no root copy yet) or `"merge_into_root"`
  (root copy exists; a course is being folded in).
- `merge_from`: course-local copies that will be read and deleted.
- `merge_to`: the destination at root.
- `index_updates`, `log_appends`: side-effects.
- `contradictions_raised`: stub at dry-run (real count emerges on apply).

```bash
# Step 2 — commit
python3 scripts/wiki_ops.py promote "Sharpe Score" --vault <vault> --apply
```

The apply path:

1. Reads each course-local copy (and root copy if present).
2. Unions frontmatter: earliest `created`, longer `description` (Q-6),
   `promoted_from: [{course, date}, ...]` list-of-dicts.
3. Additively merges bodies via `_page_merge` primitives
   (`upsert_source_row`, `append_fact`, `append_contradiction`,
   `upsert_footnote`).
4. Detects literal-line-diff contradictions (Q-10); emits a
   `## Contradictions` block citing both sources. Does NOT pick a
   winner — operator review needed.
5. Rewrites footnote definitions to vault-relative form:
   `[^src-<slug>]: [[<course_rel>/_sources/<slug>]] — <title>`
   where `<course_rel> = course_root.relative_to(vault_root)`.
6. Atomically writes the root page (`_atomic_write_text` + `flock`).
7. Deletes course-local copies (one-page-one-place invariant).
8. Updates each affected course's `index.md`: moves the row from
   `## Concepts`/`## Entities` to `## Shared concepts referenced`/
   `## Shared entities referenced`.
9. Creates/updates the root `index.md` row.
10. Appends `## [YYYY-MM-DD] promote | <Name>` to each affected course's
    `log.md`.

After `--apply`, re-run `lint`: zero `cross_course_duplicate` and zero
`invariant_violation` are required.

---

## 4. Re-promoting

When a third course later ingests a source about an already-promoted
concept (UC-4), the `upsert-page` workflow (or `ingest`) routes the
fact onto the root page automatically — R8 root-aware lookup. No
manual re-promote needed.

If you DO need to manually fold a new course-local copy into an
existing root page, just re-run `promote` — it detects
`mode: "merge_into_root"` and treats the operation as additive.

---

## 5. Demoting

When the shared concept is no longer worth sharing (e.g. only one
course actually references it now), demote it back into that course:

```bash
python3 scripts/wiki_ops.py demote "Sharpe Score" \
    --to "Hermes" --vault <vault>
```

Demote refuses if any course OTHER than `--to <Course>` still has a
`_sources/<slug>.md` cited by the root page. The error lists the
conflicting `(course, source-slug)` pairs.

If a non-target citation IS legitimate but you want to demote anyway,
either (a) delete the conflicting source pages first, or (b) edit the
root page to drop those footnotes (operator decision — out of
`demote`'s scope).

Dry-run is NOT default for `demote` (Q-2b — demote is reversible by
re-promoting). Pass `--dry-run` explicitly to preview.

---

## 6. Lint discipline

Bracket every cross-course operation with `lint`:

```bash
python3 scripts/wiki_ops.py lint <vault>     # before
python3 scripts/wiki_ops.py promote …        # change
python3 scripts/wiki_ops.py lint <vault>     # after — must be clean
```

`lint` exits non-zero on `invariant_violation` (one-page-one-place
breach). Other categories are diagnostic (exit 0).

---

## 7. Edge cases and honest scope

These are deliberately out of scope for v2; see TASK §4.5 / R13:

1. **Same name, different concepts** — operator's responsibility.
   The skill never auto-decides semantic identity.
2. **Footnote slug collisions across courses** — spec §6.2 acknowledges
   the cross-vault slug collision risk; v2 does not detect it
   automatically. Promote will silently fold same-slug entries from
   two courses.
3. **Root-level `log.md`** — not maintained. Cross-course operations
   write to each affected course's log. A vault-wide audit log is a
   future task (spec §6.6).
4. **Custom page kinds** — only `_concepts/` and `_entities/` are in
   scope. `Methods/`, `Decisions/`, etc. stay course-local (spec §6.4).
5. **Concurrency / live Obsidian writes** — `_atomic_write_text` +
   `flock` cover single-process races; multi-process / live-watch
   is out of scope (spec §6.7).
6. **Full-path link normalisation** — if the operator hand-writes
   `[[Course A/Foo]]` in custom prose, `reindex` leaves it alone
   (Q-7 / spec §8.7).

---

## 8. Migration from v1

For an existing single-course vault:

1. `wiki-ingest init <vault> --root` at the vault root scaffolds
   `WIKI_SCHEMA.md` (schema_version 2.0) + `_concepts/` + `_entities/`.
   Course directories are unchanged.
2. No data migration: existing per-course content keeps working.
3. The shared layer fills lazily on first `promote`.

For a vault that grew from single-course: just create new courses as
sibling directories with their own `init` scaffold. Two-tier behaviour
kicks in when `lint` first flags a cross-course duplicate.

---

## 9. Related references

- [`SKILL.md`](../SKILL.md) — public contract for all subcommands.
- [`references/wiki_schema.md`](wiki_schema.md) — per-course schema
  conventions; root schema is documented inline here.
- [`docs/wiki-ingest-promotion-spec.md`](../../../docs/wiki-ingest-promotion-spec.md)
  — design rationale (operator-authored).
- [`docs/TASK.md`](../../../docs/TASK.md) — TASK 016 requirements
  traceability matrix.

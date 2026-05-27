# TASK 016 — wiki-ingest: cross-course promotion / demotion (two-tier vault)

> **Mode:** VDD (Verification-Driven Development).
> **Status:** DRAFT v1 (2026-05-26).
> **Source spec:** [`docs/wiki-ingest-promotion-spec.md`](wiki-ingest-promotion-spec.md) —
> operator-authored design document. This TASK is the implementation contract;
> the spec is the design rationale. Where the two disagree, **TASK wins**;
> divergence is recorded in §5 Open Questions.
> **Predecessors (context, not dependencies):**
> - [`af77f81`] — final wiki-ingest VDD-3 refactor commit.
> - [`docs/tasks/task-015-wiki-ingest-modular-refactor.md`] — last archived
>   TASK; modular layout (`wiki_ingest/_safety.py` + `_markdown.py` +
>   `_frontmatter.py` + `_vault.py` + `_classify.py` + `commands/*.py`) is the
>   substrate this task extends.

---

## 0. Meta Information

- **Task ID:** `016`
- **Slug:** `wiki-ingest-cross-course-promotion`
- **Target skill:** [`skills/wiki-ingest/`](../skills/wiki-ingest/) (Apache-2.0
  — root [`LICENSE`](../LICENSE)).
- **Backlog row:** none (operator-initiated feature; this TASK is the origin).
- **Cross-skill replication:** **Not triggered.** wiki-ingest shares no files
  with `docx`/`xlsx`/`pptx`/`pdf`. The cross-skill `diff -q` matrix MUST
  remain silent after the change lands (regression-locked by R12).
- **Mode flag:** Standard VDD (no `[LIGHT]`).
- **New runtime dependency:** **None.** Pure stdlib (`pathlib`, `re`,
  `argparse`, `unicodedata`, `os`) — same constraint as TASK 015.
- **Reference docs:**
  - [`skills/wiki-ingest/SKILL.md`](../skills/wiki-ingest/SKILL.md) — current
    public contract; gains two subcommands (`promote`, `demote`) and a §
    documenting the two-tier vault model in this task.
  - [`skills/wiki-ingest/references/wiki_schema.md`](../skills/wiki-ingest/references/wiki_schema.md)
    — v1 schema; extended (not replaced) to describe the root `schema_version: 2.0`.
  - [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — TASK 015 §3.2 module table; extended in
    place by this task (new modules: `commands/promote.py`, `commands/demote.py`;
    extended modules: `_vault.py`, `commands/{lint,reindex,upsert_page}.py`).
  - [`docs/wiki-ingest-promotion-spec.md`](wiki-ingest-promotion-spec.md) —
    full design rationale + algorithmic sketches.

---

## 1. Problem Description

The wiki-ingest skill currently models the Obsidian vault as a **single wiki
root**: one `WIKI_SCHEMA.md` + one `_sources/` + one `_concepts/` + one
`_entities/` + one `index.md` + one `log.md`. This is fine for a single-topic
vault. It breaks down for operators who keep **multiple parallel courses**
(or projects, or knowledge domains) in one Obsidian vault — e.g.:

```
my-vault/
└── Lessons/
    ├── Course A/    # WIKI_SCHEMA.md + _sources + _concepts + _entities
    └── Course B/    # same
```

When the same concept appears in two courses (`Sharpe Score`, `Hermes Agent`,
`Pipeline`), the v1 skill forces an unhappy choice:

1. **Duplicate the concept page** in each course → silent drift, contradictory
   facts, fragmented citations, double-source-attribution.
2. **Merge both courses into one big vault** → loses per-course journaling
   (`log.md`), index hygiene, the ability to read one course in isolation.

This TASK introduces a **two-tier vault model** so the operator can promote
a shared concept/entity to a **vault-root shared layer** *on demand*, by hand,
after they've seen the duplicate appear naturally.

### Target shape (v2)

```
my-vault/                                  # ← Obsidian vault root
├── WIKI_SCHEMA.md                         # NEW — root schema (schema_version: 2.0)
├── _concepts/                             # NEW — shared concepts, lazy
├── _entities/                             # NEW — shared entities, lazy
├── index.md                               # NEW (optional) — root catalog
└── Lessons/
    ├── Course A/                          # unchanged — course-local layer
    │   ├── WIKI_SCHEMA.md                 # schema_version: 1.x
    │   ├── _sources/  _concepts/  _entities/  index.md  log.md
    └── Course B/                          # same
```

The **load-bearing invariant** is one-page-one-place: a given canonical
filename (`Sharpe Score.md`) lives in *exactly one* of (a) some course's
`_concepts/`/`_entities/`, or (b) the root's. Never both. Obsidian's filename-
based `[[wiki-link]]` resolution then works without per-link course prefixes.

### Why "lazy promotion"?

- **Ingest never promotes.** The skill's classify-on-ingest already runs into
  same-name-different-concept pitfalls (e.g., `Pipeline` in an ML course vs a
  DevOps course). Auto-promotion would silently merge them.
- **The operator is the semantic oracle.** Promotion is reviewable and
  reversible (via `demote`). The skill's job is mechanical merge + invariant
  enforcement, not semantic identity detection.
- **The shared layer stays empty until first promote.** New vaults work
  exactly like v1.

---

## 2. Requirements Traceability Matrix (RTM)

| ID    | Requirement                                                                                                                                                                                                                                  | MVP? | Sub-features |
|-------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------|--------------|
| R1    | **Two-tier vault detection.** Extend `wiki_ingest/_vault.py` with `find_vault_root(start) -> tuple[Path, Path | None]` returning `(course_wiki_root, vault_root_or_None)`. Single-course vaults (no second `WIKI_SCHEMA.md`) return `(course_root, None)` and the skill behaves as v1 (load-bearing for migration). | Y | R1.1 Walk up from a path inside a course; stop at first `WIKI_SCHEMA.md` → course root. R1.2 Continue walking; second `WIKI_SCHEMA.md` (with `schema_version: 2.0`) → vault root; else None. R1.3 Original `find_wiki_root` (if introduced) is a thin wrapper that returns only the course root for v1 callers — no v1 caller changes signature. R1.4 Both schemas must be parsed (frontmatter) — root schema MUST declare `schema_version: 2.0`; mismatched or missing version aborts with `die("vault root schema must declare schema_version: 2.0", code=2)`. |
| R2    | **Root-schema scaffold.** Extend `commands/init.py` (or add a sibling subcommand `init-root`) so the operator can create the vault-root `WIKI_SCHEMA.md` + empty `_concepts/` + `_entities/` + (optional) `index.md`. Idempotent. Does NOT touch existing course directories. | Y | R2.1 Bundled `assets/WIKI_SCHEMA.root.template.md` (new) with `schema_version: 2.0` and a top-level `kind: vault-root` marker. R2.2 `init <vault> --root` (or `init-root <vault>`) writes the scaffold; never overwrites existing files; reports created paths in JSON. R2.3 `init <vault>` (no `--root`) is unchanged — still scaffolds a course-local wiki. R2.4 The choice between `--root` flag on `init` vs a new `init-root` subcommand is recorded in §5 Open Q-1. |
| R3    | **`promote <Name>` subcommand.** New module `wiki_ingest/commands/promote.py`. Merges ≥2 course-local copies of a `_concepts/` or `_entities/` page into a single root-level page; deletes the course-local copies; updates each affected course's `index.md` + `log.md`; updates the root `index.md`. Reuses `upsert_page.merge_into_existing`-style additive merge (no rewrite of existing content). | Y | R3.1 Pre-conditions: same filename exists in ≥2 distinct courses' `_concepts/` (OR `_entities/`); not already at root (unless §3.3-relax — see R3.7). R3.2 `--kind {concept,entity}` optional — auto-infer when all duplicates agree; error if mixed. R3.3 Frontmatter union (created = earliest date; description = longer-of-two; `promoted_from:` list of `{course, date}` per source). R3.4 Body merge: additive section-by-section (`## Definition`, `## Facts`, `## Sources mentioning this`, `## Contradictions`, plus any custom sections). R3.5 Footnote definitions on the root page rewritten to vault-relative form `[^src-<slug>]: [[Lessons/<Course>/_sources/<slug>]] — <Title>`. R3.6 Conflict detection: fact-level disagreement (same predicate, different value) surfaces a `## Contradictions` block. No auto-resolve. R3.7 Re-promote relaxation: if the root version already exists and an additional course has a course-local copy, the same `promote` command merges that course-local copy into the root page (replaces the deferred `merge-into-root` from spec §3.3). R3.8 Each affected course's `index.md` removes the page from `## Concepts`/`## Entities` and adds it to `## Shared concepts referenced`/`## Shared entities referenced` if that course still cites it. R3.9 Root `index.md` is created on first promote (if missing) and gains the page row. R3.10 Each affected course's `log.md` gains a `## [YYYY-MM-DD] promote \| <Name>` block listing merged paths + contradictions raised. |
| R4    | **`promote --dry-run` is the default.** Without `--apply`, the command prints a structured plan (paths to read, merge proposal preview, paths to delete, log diffs) to stdout and writes nothing. `--apply` performs the writes. | Y | R4.1 Default is dry-run; explicit `--apply` required to commit. R4.2 Plan JSON includes: `merge_from: [path, …]`, `merge_to: path`, `delete: [path, …]`, `index_updates: [{course, op}]`, `log_appends: [{course, body}]`, `contradictions_raised: int`. R4.3 Re-running an `--apply` after a successful `--apply` is a no-op (idempotency), not an error. R4.4 (See §5 Open Q-2 for alternative — explicit confirmation prompt instead of dry-run default.) |
| R5    | **`demote <Name> --to <Course>` subcommand.** New module `wiki_ingest/commands/demote.py`. Moves a root-level page back to the named course's `_concepts/`/`_entities/`; refuses if any other course's `_sources/` cite it. | Y | R5.1 Pre-conditions: page exists at root; target course exists and has a `WIKI_SCHEMA.md`. R5.2 Cross-course citation check: scan every `Lessons/<Course>/_sources/<slug>.md` for footnote definitions whose `<slug>` is referenced by `[^src-<slug>]` *on the page being demoted* — refuse if any cite-source lives in a course ≠ target. Error message lists conflicting `(course, source-slug)` pairs. R5.3 Footnotes rewritten back to short form `[^src-<slug>]: [[<slug>]] — <Title>`. R5.4 `promoted_from:` frontmatter field removed. R5.5 Filter facts whose backing source is from a non-target course (defensive — should already be empty after the precondition). R5.6 Root `index.md` row removed; target course's `index.md` row moved from `## Shared concepts referenced` back to `## Concepts`/`## Entities`. R5.7 Target course's `log.md` gains a `## [YYYY-MM-DD] demote \| <Name>` block. R5.8 `--dry-run` supported (same envelope as R4); not the default for demote (Open Q-2 decides). |
| R6    | **`lint` extension — cross-course duplicates + invariant.** Extend `wiki_ingest/commands/lint.py`. | Y | R6.1 New finding category `cross_course_duplicate`: a filename appearing in ≥2 `Lessons/<Course>/_concepts/` (or `_entities/`). Output cites the suggested `wiki-ingest promote "<Name>"` command. R6.2 New finding category `invariant_violation`: a filename present at the root AND in any course's `_concepts/`/`_entities/`. HARD failure (exit code reflects). Suggests `promote` (to fold the course-local in) or `demote` (to pull the root copy down). R6.3 Cross-layer dangling-link refinement: a course-local link to `[[Foo]]` where `Foo.md` exists at the root resolves cleanly (NOT dangling). A link to `[[Bar]]` where `Bar.md` exists only in *another* course IS dangling — flag with a suggestion to promote. R6.4 Root-page footnote-format check: every `[^src-<slug>]` definition on a root page MUST use the vault-relative form `[[Lessons/<Course>/_sources/<slug>]]`. Short form on a root page is a `warning` (not error). R6.5 Existing lint findings (orphans, dangling, contradictions, missing pages) keep their semantics; cross-course categories are *additive* to the JSON output. |
| R7    | **`reindex` extension — `## Shared * referenced` + root mode.** Extend `wiki_ingest/commands/reindex.py`. | Y | R7.1 When reindex runs on a course, scan the course's `_sources/` for footnote references. For every cited source-slug also referenced on a root concept/entity page, add that root page to `## Shared concepts referenced` / `## Shared entities referenced` in the course's `index.md`. R7.2 When reindex runs on the vault root (new), rebuild root `index.md` `## Concepts`/`## Entities` from disk. Optionally cascade-reindex every course (gated by `--cascade` flag — default off). R7.3 Custom sections in `index.md` continue to be preserved verbatim (existing v1 invariant must not regress). R7.4 The reindex JSON output gains a `shared_referenced` field per layer summarising the new sections. |
| R8    | **`ingest` / `upsert-page` / `register-summary` — root-aware fact merge.** Extend `wiki_ingest/commands/upsert_page.py` (and the `register-summary`-driven upsert path) so that, when upserting a concept/entity, the code first checks the **root** layer; if a page with the canonical name exists at root, the new fact/source row lands on the root page (NOT a course-local copy). | Y | R8.1 Lookup order: root `_concepts/` → root `_entities/` → course-local. First hit wins. R8.2 When the merge target is a root page, the footnote definition on the root page is written/updated in vault-relative form `[[Lessons/<Course>/_sources/<slug>]] — <Title>`. R8.3 `append-log` from the course writes `Pages touched: ../../\_concepts/Sharpe Score (shared)` (or equivalent marker) so the log line reflects the shared destination. R8.4 If the page does NOT exist at root, behaviour is unchanged — a course-local stub is created (current v1 path). R8.5 No new auto-promotion is performed (R8 honours the operator-only-promotion invariant). |
| R9    | **Schema-versioning + abort guards.** | Y | R9.1 `promote` / `demote` refuse to run if the vault has no root `WIKI_SCHEMA.md` (`die("vault root WIKI_SCHEMA.md absent; run init --root first", code=2)`). R9.2 `promote` / `demote` refuse to run if the root schema declares `schema_version` other than `2.0` (clear message). R9.3 Existing v1 callers (ingest / upsert / lint / reindex on a single-course vault with no root schema) continue to work unchanged — `find_vault_root` returns `vault_root=None` and command paths fall back to course-only behaviour. |
| R10   | **Tests.** Add unit + E2E coverage for the new commands and extensions, using the per-skill `unittest` venv discipline (no pytest, no runtime deps). | Y | R10.1 `tests/commands/test_promote.py` — happy path (2-course merge), 3-course merge, kind-mismatch refusal, already-at-root re-promote, dry-run-by-default, contradiction-surfacing. R10.2 `tests/commands/test_demote.py` — happy path, cross-course citation refusal, footnote rewrite, frontmatter restore. R10.3 `tests/commands/test_lint.py` — new cross-course-duplicate + invariant-violation categories; cross-layer dangling refinement. R10.4 `tests/commands/test_reindex.py` — `## Shared * referenced` sections; root-mode reindex; custom-sections preservation. R10.5 `tests/commands/test_upsert_page.py` — root-layer-first lookup; vault-relative footnote on root. R10.6 `tests/test__vault.py` — `find_vault_root` for (a) single-course vault, (b) two-tier vault, (c) deeply-nested input, (d) schema-version mismatch. R10.7 New E2E fixture: `tests/fixtures/two_course_vault/` with two courses + an overlapping `Sharpe Score` concept + a unique-per-course concept. R10.8 Round-trip E2E (`tests/test_e2e_promotion.py`): ingest → lint detects dup → promote → lint clean → demote → lint clean → state matches start (modulo log lines + frontmatter timestamps). |
| R11   | **Documentation.** Update SKILL.md to document the two new subcommands and the two-tier model; add a dedicated reference page. Update [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) in place (TASK 015 §3.2 module table + §11 atomic-chain skeleton extended). | Y | R11.1 `SKILL.md` §4 (Script Contract) gains `promote` and `demote` rows; §7 (Instructions) gains a `Phase P — Promote/Demote` subsection. R11.2 NEW reference [`skills/wiki-ingest/references/cross_course_promotion.md`](../skills/wiki-ingest/references/cross_course_promotion.md) with the operator playbook, edge cases, and the spec's §6 gotchas. R11.3 `docs/ARCHITECTURE.md` extended in place (NOT archived — living document per `artifact-management`). New §2.x for the two-tier vault model and §3.x module entries for `promote.py`/`demote.py`. R11.4 [`skills/wiki-ingest/references/wiki_schema.md`](../skills/wiki-ingest/references/wiki_schema.md) extended with §"Root schema (v2.0)" describing the vault-root marker. R11.5 [`skills/wiki-ingest/scripts/wiki_ingest/.AGENTS.md`](../skills/wiki-ingest/scripts/wiki_ingest/.AGENTS.md) updated with the new modules. |
| R12   | **Cross-skill replication & validators.** | Y | R12.1 No file added by this task matches any path replicated across docx/xlsx/pptx/pdf. R12.2 `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/wiki-ingest` exits 0. R12.3 `python3 .claude/skills/skill-validator/scripts/validate.py skills/wiki-ingest` reports risk `SAFE` (0 Critical / 0 Errors). R12.4 R9 cross-skill `diff -q` matrix from TASK 015 §9 stays silent. R12.5 The existing `tests/test_architecture.py` import-graph check passes — `promote.py`/`demote.py` import only from `_safety`, `_markdown`, `_frontmatter`, `_vault`, and DO NOT import any other `commands/*` module. |
| R13   | **Honest-scope guardrails (out-of-scope items, locked in §4).** | Y | R13.1 No semantic-identity detection across courses (operator decides if two same-name pages describe the same thing — §6.1). R13.2 No root-level `log.md` (§6.6) — cross-course operations write to each affected course's log; if demand emerges, that becomes a follow-up task. R13.3 No automatic source-slug collision detection across courses (§6.2) — the existing v1 ingest-side check stands; cross-vault collision is added to KNOWN_ISSUES at execution time if observed. R13.4 No support for custom page kinds (e.g., `Methods/`, `Decisions/`) — only `_concepts/`/`_entities/` (§6.4). R13.5 No file-watch or concurrency primitives beyond the existing `flock` (§6.7). R13.6 No bidirectional `[[Course A/Foo]]`-style link normalisation (§6.9 / spec §8.7). |

---

## 3. Use Cases

### UC-1 — Operator promotes a duplicate concept across two courses

**Actors**: operator, wiki-ingest CLI, filesystem.

**Preconditions**:
- A vault under `~/obsidian/trade-agents/` with two courses
  (`Lessons/Hermes/`, `Lessons/OpenClaw/`), each with its own
  `WIKI_SCHEMA.md` + `_sources/` + `_concepts/` + `_entities/` +
  `index.md` + `log.md`.
- Each course has independently ingested a source that produced
  `_concepts/Sharpe Score.md`. Lint has flagged the duplicate
  (R6.1 finding `cross_course_duplicate`).
- Vault root has `WIKI_SCHEMA.md` (`schema_version: 2.0`) — either
  hand-created or via `init --root` (R2.2).

**Main scenario**:
1. Operator runs `wiki-ingest promote "Sharpe Score" --vault ~/obsidian/trade-agents`.
2. CLI walks up from the vault arg, discovers the vault root + both course
   roots via `find_vault_root` (R1).
3. CLI scans `Lessons/*/_concepts/Sharpe Score.md`, finds two copies.
4. CLI reads + parses both copies; computes union frontmatter, additive
   merged body, rewritten vault-relative footnotes.
5. CLI prints the **dry-run plan JSON** to stdout (R4 — default mode) listing:
   merge sources, merge destination, files to delete, index/log diffs,
   contradiction count. **Writes nothing.**
6. Operator reviews; re-runs with `--apply`.
7. CLI writes `~/obsidian/trade-agents/_concepts/Sharpe Score.md`,
   deletes both course-local copies (R3.6 invariant), updates both
   course `index.md` files (move from `## Concepts` to
   `## Shared concepts referenced`), updates root `index.md` (R3.9),
   appends a `## [2026-05-26] promote | Sharpe Score` block to each
   course's `log.md` (R3.10).
8. CLI prints final JSON: `{"applied": true, "merged_to": "...", "merged_from": [...], "contradictions_raised": 0}`.

**Alternative scenarios**:

- **A1: Page only exists in ONE course (no duplicate).** Step 3 fails the
  ≥2-courses precondition (R3.1). CLI exits non-zero with message
  `"no duplicates found; nothing to promote"`. No files touched.
- **A2: Already at root (re-promote relaxation R3.7).** Page exists at
  root AND in one course. Step 3 detects the root version; the command
  merges the course-local copy into the existing root page (additive
  merge); deletes the course-local copy; updates that course's
  `index.md`/`log.md`. Root `index.md` unchanged (page already listed).
- **A3: Kind mismatch.** Course A has `_concepts/Pipeline.md`; Course B
  has `_entities/Pipeline.md`. CLI exits non-zero with message
  `"kind mismatch: Course A treats Pipeline as concept, Course B as entity;
  reconcile manually before promoting"`. No files touched.
- **A4: Contradiction at merge time.** Course A's body says
  `Sharpe Ratio = (R_p - R_f) / σ_p`; Course B's says
  `Sharpe Ratio = R_p / σ_p`. The merge body includes a `## Contradictions`
  block citing both source slugs. Step 8 JSON has
  `contradictions_raised: 1`. The operator inspects the merged page,
  decides which is canonical (out of scope for this skill).
- **A5: Root schema absent.** Vault has no top-level `WIKI_SCHEMA.md`.
  Step 2 fails with `die("vault root WIKI_SCHEMA.md absent; run init
  --root first", code=2)` (R9.1).
- **A6: Root schema wrong version.** Top-level schema declares
  `schema_version: 1.0`. CLI exits non-zero (R9.2).
- **A7: `--apply` re-run.** The page is already at root (no course-local
  copies remain). The command is a no-op (R4.3) — exit 0, JSON reports
  `{"applied": true, "noop": true}`.

**Postconditions**:
- Exactly **one** copy of `Sharpe Score.md` exists in the vault — at
  `<vault>/_concepts/Sharpe Score.md`.
- Every footnote on that page resolves to an existing
  `Lessons/<Course>/_sources/<slug>.md` file (verified by lint R6.4).
- Both course `index.md` files list the shared page under
  `## Shared concepts referenced`.
- `log.md` of each affected course has a `## [YYYY-MM-DD] promote | Sharpe Score` block.
- `lint` reports no `cross_course_duplicate` and no `invariant_violation`
  for `Sharpe Score`.

**Acceptance Criteria**:
- ✅ `wiki-ingest promote "Sharpe Score"` defaults to dry-run (no writes).
- ✅ `--apply` performs all 10 steps from §3.1 of the spec.
- ✅ Re-running `--apply` is a clean no-op (exit 0, no changes).
- ✅ Kind mismatch / no-duplicate / wrong-root-schema all fail with clear
  messages and code 1 or 2.
- ✅ Contradiction detection emits a `## Contradictions` block, never
  picks a winner.
- ✅ All footnotes on the promoted page use vault-relative `[[Lessons/...]]` form.
- ✅ Both course `index.md` files end up with `## Shared concepts referenced`
  containing `[[Sharpe Score]]`.

---

### UC-2 — Operator demotes a root concept back into one course

**Actors**: operator, wiki-ingest CLI.

**Preconditions**:
- `<vault>/_concepts/Sharpe Score.md` exists (from a prior promote).
- The page's footnotes cite sources only from Course A
  (Course B's source was later deleted, or the operator never actually
  needed the cross-course share).

**Main scenario**:
1. Operator runs `wiki-ingest demote "Sharpe Score" --to "Course A"`.
2. CLI verifies the vault root, finds the root page, parses footnotes.
3. CLI scans every `Lessons/*/_sources/*.md` for footnote-definition
   citations on the root page — finds only Course A sources. Precondition
   R5.2 passes.
4. CLI prints dry-run plan (if `--dry-run`) or proceeds directly
   (Open Q-2 decides default for demote).
5. With `--apply`:
   - Move `<vault>/_concepts/Sharpe Score.md` →
     `<vault>/Lessons/Course A/_concepts/Sharpe Score.md`.
   - Rewrite footnote definitions to short form
     `[^src-<slug>]: [[<slug>]] — <Title>`.
   - Strip `promoted_from:` frontmatter.
   - Remove the row from root `index.md`.
   - Move the row in Course A's `index.md` from
     `## Shared concepts referenced` back to `## Concepts`.
   - Append `## [2026-05-26] demote | Sharpe Score` to Course A's `log.md`.

**Alternative scenarios**:
- **A1: Cross-course citation refusal (R5.2).** A footnote on the root page
  cites a source from Course B. CLI exits non-zero with
  `"refused: page is cited by sources outside <target course>: [Course B/_sources/foo.md]"`.
  No files touched.
- **A2: Target course absent.** `--to "Course X"` and that path doesn't
  exist or has no `WIKI_SCHEMA.md`. Exit non-zero, no writes.
- **A3: Page not at root.** Page lives only in some course. Exit non-zero
  with `"page is not at root; nothing to demote"`. No writes.

**Postconditions**:
- The page lives only in `Lessons/Course A/_concepts/`.
- Footnotes are short-form again.
- Root `index.md` no longer references it; Course A's `index.md` does
  (under `## Concepts`).

**Acceptance Criteria**:
- ✅ `demote` refuses when any non-target course cites the page.
- ✅ Footnote rewrite is reversible — round-trip
  (`promote` → `demote`) produces byte-identical short-form footnotes.
- ✅ Frontmatter `promoted_from:` is fully removed (no orphan key).

---

### UC-3 — Lint detects cross-course duplicates + invariant violations

**Actors**: operator, wiki-ingest CLI.

**Preconditions**:
- A two-tier vault with at least one cross-course duplicate AND one
  invariant violation (page at root AND in some course — e.g., introduced
  by manual file copy).

**Main scenario**:
1. Operator runs `wiki-ingest lint <vault>`.
2. CLI walks the entire vault: every course's `_concepts/`/`_entities/`
   AND the root's `_concepts/`/`_entities/`.
3. CLI emits JSON with the existing four categories (orphans, dangling,
   contradictions, missing pages) PLUS the new two:
   - `cross_course_duplicate: [{name, kind, courses: [path, …], suggest: "wiki-ingest promote \"<Name>\""}, …]`
   - `invariant_violation: [{name, root_path, course_paths: [...], suggest: "wiki-ingest promote \"<Name>\" or demote it"}]`
4. The presence of any `invariant_violation` causes a non-zero exit code
   (hard failure — the one-page-one-place invariant is load-bearing).

**Alternative scenarios**:
- **A1: Dangling-link refinement (R6.3).** A course-local page links
  `[[Foo]]`; `Foo.md` exists at root. The classic v1 lint would flag this
  as dangling. v2 lint recognises root + course as one logical namespace
  and does NOT flag.
- **A2: Cross-course-only link.** Course A links `[[Bar]]`; `Bar.md`
  exists only in Course B's `_concepts/`. This IS dangling (the layers
  are isolated except via promotion). Lint flags it and suggests
  promoting `Bar` if the meanings align.

**Postconditions**: lint output is purely diagnostic — no files touched.

**Acceptance Criteria**:
- ✅ Lint detects ≥1 cross-course duplicate in a fixture with two courses
  sharing a name.
- ✅ Lint detects invariant violations and exits non-zero.
- ✅ Lint does NOT flag a course→root link as dangling.

---

### UC-4 — Ingest into a course whose concept is already shared (R8)

**Actors**: operator, `wiki-ingest ingest`/`register-summary`, internal
upsert path.

**Preconditions**:
- `<vault>/_concepts/Sharpe Score.md` exists at root (from prior promote).
- The operator ingests a new source into Course C that mentions
  Sharpe Score.

**Main scenario**:
1. `register-summary` (or full `ingest`) is invoked for Course C.
2. `upsert-page` for `Sharpe Score`: the root-aware lookup (R8.1) finds
   the root page.
3. The new fact + the new source row land on the root page.
4. The footnote definition for the new source slug is written in
   vault-relative form `[^src-foo]: [[Lessons/Course C/_sources/foo]] — …` (R8.2).
5. Course C's `log.md` records `Pages touched: <vault>/_concepts/Sharpe Score (shared)` (R8.3).

**Alternative scenarios**:
- **A1: Page not at root.** Lookup misses root → falls back to course-local
  (R8.4). Behaviour identical to v1.

**Postconditions**: the shared root page has gained one source row + one
fact + the new footnote; **no new course-local copy is created**.

**Acceptance Criteria**:
- ✅ A second course can contribute facts to a root page without first
  running `promote` again.
- ✅ The root page never gains a course-local sibling at ingest time.

---

### UC-5 — Reindex builds `## Shared * referenced` sections (R7)

**Actors**: operator, CLI.

**Preconditions**: vault has at least one promoted concept that some
courses still cite via `_sources/` footnotes.

**Main scenario**:
1. Operator runs `wiki-ingest reindex <vault>/Lessons/Course A`.
2. CLI rebuilds Course A's `## Sources` / `## Concepts` / `## Entities`
   (existing v1 behaviour, R7.3 preserves custom sections).
3. CLI additionally scans Course A's `_sources/` for footnote-slug
   references whose definitions appear on any root concept/entity page.
4. CLI adds `## Shared concepts referenced` and/or `## Shared entities
   referenced` to Course A's `index.md`, listing each cited root page.

**Alternative scenarios**:
- **A1: `wiki-ingest reindex <vault>` (root mode).** Rebuilds the root
  `index.md` from disk (R7.2). With `--cascade`, also re-runs reindex on
  every course so new shared-referenced sections propagate.

**Postconditions**:
- Course's `index.md` contains the new sections.
- Custom sections (e.g., `## Notes`, `## Reading Queue`) are unchanged
  (R7.3 — v1 invariant must not regress).

**Acceptance Criteria**:
- ✅ Reindex on a course with a footnoted root page produces a
  `## Shared concepts referenced` section.
- ✅ Reindex on the vault root rebuilds the root `index.md` without
  touching any course.
- ✅ `--cascade` reindexes every course; without `--cascade`, only the
  named layer is rebuilt.

---

## 4. Non-Functional Requirements

### 4.1 Performance

- `find_vault_root` MUST be O(depth) — a single walk-up from any input
  path to the filesystem root.
- `promote` / `demote` / cross-course lint MUST be O(N) in the number of
  pages across all courses; no O(N²) joins (the existing v1 lint is
  already O(N) after the OVERLAP-3 mask-once fix).
- Wall-time targets on a fixture vault with 5 courses × 100 concepts:
  - `lint` (including cross-course passes): ≤ 0.5 s.
  - `promote` (2-course merge): ≤ 0.2 s for the dry-run, ≤ 0.4 s for
    `--apply`.
  - `reindex --cascade` on the same fixture: ≤ 1 s.

### 4.2 Security

- Cross-course path traversal MUST be impossible: `find_vault_root`
  refuses if walking up crosses outside the original input's filesystem
  (defensive against `..` injection via a symlinked `WIKI_SCHEMA.md`).
- All filename validation (`_safe_name`) continues to reject path
  separators, control characters, NFKC variants, and template
  placeholders — applies to the new `--name <Name>` argument of
  `promote`/`demote`.
- `--to <Course>` of `demote` MUST also pass `_safe_name` and resolve
  containment via `_is_relative_to(<vault>/Lessons/<Course>, vault)`.
- Atomic-write discipline (`_atomic_write_text` + `flock`) extends to
  every new write site: root `index.md`, root concept/entity page,
  course `index.md`, course `log.md`.
- Footnote-format rewrites MUST be regex-anchored so a deliberately
  malformed footnote (`[^src-foo]: [[arbitrary]] — title]]\n[^src-foo]:
  …`) cannot smuggle a second definition past the rewrite.
- The TASK does not introduce a new attack surface: no new subprocess,
  no new network call, no new external dep.

### 4.3 Scalability

- Out of scope for v2 (operator-driven workflow on a single machine).
  If multi-process / live-Obsidian-write concurrency becomes a concern,
  it is captured as KNOWN_ISSUES at execution time (spec §6.7).

### 4.4 Compatibility

- **Backwards compatibility (load-bearing).** Single-course vaults with
  no root `WIKI_SCHEMA.md` MUST continue to work exactly as today.
  Every v1 subcommand (`ingest`/`register-summary`/`scan`/`init`/
  `upsert-page`/`update-index`/`append-log`/`log-event`/`find`/`lint`/
  `reindex`/`classify-folder`) MUST produce byte-identical output on a
  single-course fixture (the v1 fixtures from
  `tests/fixtures/` and `tests/test_r11_byte_identity.py`).
- Python 3.9+ continues to be the floor (no `match`/`case`).
- No new runtime deps; tests stay on stdlib `unittest`.

### 4.5 Honest scope (locked)

- **Operator-only promotion.** No auto-promotion at ingest time (spec §8.4 + R13).
- **No semantic identity detection.** Two same-name pages may describe
  unrelated things; the operator is the oracle (spec §6.1 + R13.1).
- **No root-level `log.md`.** Each cross-course operation writes to every
  affected course's log; vault-wide audit log is a future task
  (spec §6.6 + R13.2).
- **`_concepts/` and `_entities/` only.** Custom page kinds (`Methods/`,
  `Decisions/`) are out of scope (spec §6.4 + R13.4).
- **No bidirectional `[[Course A/Foo]]` link normalisation.** If the
  operator hand-writes a full-path link, leave it alone (spec §8.7 + R13.6).
- **Source-slug cross-vault collision** is documented but not detected
  at scale (R13.3); if observed in execution, log a KNOWN_ISSUES entry
  rather than expand task scope.
- **Migration: zero-data.** Existing single-course vaults gain v2
  capability when the operator adds a root `WIKI_SCHEMA.md`; no migration
  script is provided. Spec §10 describes the (manual) bootstrap.

---

## 5. Open Questions (for operator confirmation before Planning phase)

These are the spec's §8 questions, restated as TASK-blocking ambiguities.
A recommended default is given for each; the operator may override during
planning. Items where the operator has already given the recommended answer
(by signing off on the spec) can be closed at TASK-review time.

| ID    | Question                                                                                                                                                                                                          | Recommended default                                                                                                                                                                                               | Impact if changed |
|-------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------|
| Q-1   | `init` extension shape — extend with `--root` flag, or add a sibling subcommand `init-root`?                                                                                                                       | `init <vault> --root` (smaller surface; `init`'s code already discovers existing files; one flag is cheaper than a parallel subcommand). One-line of CLI test difference.                                          | Surface size + test count; no functional impact. |
| Q-2   | `--dry-run` default for **`promote`** (spec §8.1).                                                                                                                                                                  | Make dry-run the default (R4); require `--apply` to commit. Aligns with destructive-action UX (deletes ≥1 file).                                                                                                  | UX phrasing of A7 scenario in UC-1. |
| Q-2b  | `--dry-run` default for **`demote`**.                                                                                                                                                                              | NOT default (`--dry-run` available but explicit). Rationale: demote is reversible (just `promote` again) and touches fewer files than promote.                                                                     | Symmetry expectation only. |
| Q-3   | Promotion threshold (≥ 2 courses) — make configurable in root `WIKI_SCHEMA.md`?                                                                                                                                   | Hard-code 2 at v2; operator always reviews. Spec §8.2 says no.                                                                                                                                                     | Adds a schema field; can be deferred. |
| Q-4   | Root-level `log.md` — write one in v2?                                                                                                                                                                              | NO (spec §6.6 + R13.2). Deferred.                                                                                                                                                                                  | One extra file write per `promote`/`demote`. |
| Q-5   | Auto-promotion as opt-in flag — supported?                                                                                                                                                                          | NO. Spec §8.4 decided.                                                                                                                                                                                              | Adds an entry point + ingest-time branching. |
| Q-6   | Frontmatter `description:` merge policy when two courses' values disagree (spec §8.5).                                                                                                                              | Pick the LONGER of the two (cheap implementation; preserves more context). Operator can edit afterwards.                                                                                                            | Alternative: join with `' / '`; or take first (lossy). |
| Q-7   | Bidirectional `[[Course A/Foo]]` full-path link normalisation on reindex (spec §8.7).                                                                                                                              | LEAVE ALONE. Operator wrote the full path for a reason.                                                                                                                                                            | Future reindex extension if demand surfaces. |
| Q-8   | Where does the per-course root-path discovery live — env var, schema-declared key, or hardcoded `Lessons/<Course>` convention?                                                                                     | Discover courses by walking `vault/Lessons/<*>` and checking each for `WIKI_SCHEMA.md`. The `Lessons/` segment is conventional (matches the operator's existing `trade-agents` vault) but NOT hardcoded — replaced by "any subdirectory with a course-local schema." | If the operator uses a different layout (`vault/<Course>/` directly), the discovery walk MUST still find them. Recommended approach handles both. |
| Q-9   | Footnote-format check on root pages (R6.4) — `warning` or `error`?                                                                                                                                                  | `warning` (consistent with other format checks; short-form on a root page is non-fatal but suboptimal).                                                                                                            | Exit-code semantics of `lint`. |

**Resolution rule**: if the operator does not respond to Q-1..Q-9 during
TASK review, the Planner adopts the recommended defaults and records the
decision in PLAN.md §0 (Open Questions Resolved).

---

## 6. Constraints and Assumptions

- **Constraint**: pure stdlib (`os`, `re`, `argparse`, `pathlib`,
  `unicodedata`, `json`, `datetime`, `fcntl` on POSIX). No new
  requirements.txt entries.
- **Constraint**: SKILL.md remains the public contract; every change MUST
  be documented there (R11.1) before merge.
- **Constraint**: ARCHITECTURE.md is a LIVING document (per
  `artifact-management`) — updated in place, NOT per-task archived.
- **Constraint**: the import-graph invariant from TASK 015
  (`tests/test_architecture.py`) is load-bearing — `promote.py` /
  `demote.py` MUST NOT import any other `commands/*.py` module
  (R12.5).
- **Assumption**: the operator's vault uses Obsidian's filename-based
  link resolution (the default since Obsidian 0.x). If the operator
  has enabled `useMarkdownLinks` and switched to wikilink-by-path, the
  vault-relative footnote form is still valid; the bare-filename form
  on course-local pages is also valid. We do not configure Obsidian.
- **Assumption**: course directories live under a single sibling of the
  vault root (typically `Lessons/`). If multi-level course hierarchies
  appear (`Lessons/2026/Spring/Hermes/`), see Open Q-8 — the discovery
  walk handles it via "any descendant with a `WIKI_SCHEMA.md`."
- **Assumption**: footnote slugs are globally unique across all `_sources/`
  in the vault. Spec §6.2 acknowledges this is unverified at v1; v2
  does not change the model but flags collision as a KNOWN_ISSUES item if
  observed during execution.

---

## 7. Acceptance Criteria (TASK-level — summary across all RTM rows)

- ✅ Two new subcommands (`promote`, `demote`) wired into `wiki_ops.py`
  via the existing `_COMMAND_MODULES` tuple (R3 + R5).
- ✅ Six existing commands extended in place: `init` (R2), `lint` (R6),
  `reindex` (R7), `upsert-page` (R8), `register-summary` (R8 via upsert),
  `ingest` workflow (R8 — no CLI change).
- ✅ One new helper extension in `_vault.py`: `find_vault_root` (R1).
- ✅ One new bundled asset: `assets/WIKI_SCHEMA.root.template.md` (R2.1).
- ✅ One new reference doc: `references/cross_course_promotion.md` (R11.2).
- ✅ One new E2E fixture: `tests/fixtures/two_course_vault/` (R10.7).
- ✅ All R10 unit + E2E tests pass under the per-skill `unittest` venv.
- ✅ `validate_skill.py` exits 0; `skill-validator` reports `SAFE` (R12.2/12.3).
- ✅ TASK 015's R11 byte-identity tests still pass — single-course vaults
  behave identically to v1.
- ✅ Cross-skill `diff -q` matrix is silent (R12.4).
- ✅ `docs/ARCHITECTURE.md` reflects the new modules + the two-tier model
  (R11.3) — updated in place, never archived.
- ✅ `KNOWN_ISSUES.md` carries any newly-deferred items surfaced during
  execution (e.g., source-slug cross-vault collision, root-log absence
  requested by the operator post-merge).

---

## 8. Risks (heads-up for Planner / Critic loops)

1. **Footnote rewrite regex fragility.** The vault-relative form
   `[[Lessons/<Course>/_sources/<slug>]]` contains `/` — must NOT be
   misinterpreted as a markdown link by the existing wikilink regex
   `WIKILINK_RE`. Validate with a `tests/test__markdown.py` adversarial
   case BEFORE wiring R3.5.
2. **`promoted_from:` frontmatter merge with `_splice_frontmatter_fields`.**
   The existing splice helper handles flat list fields; promoted-from is
   a list-of-dicts. Either extend the splice helper (preferred) or fall
   back to a structural rewrite via `_serialize_yaml_list_field`. Carry
   this as a planning-phase decision.
3. **Lint cross-course-duplicate finding count blow-up.** A vault with 5
   courses × 50 shared concepts emits 50 findings. The JSON envelope
   must remain readable — consider a `--limit N` flag analogous to
   `lint --threshold N`.
4. **Demote's cross-course citation scan is O(courses × sources_per_course
   × footnotes_per_source).** On a 5×100×20 vault that's 10k regex
   operations. The existing `_extract_wikilinks_with_anchors` is
   mask-once; re-use it.
5. **Re-promote (R3.7) semantics are subtle.** "Root version exists, one
   course-local exists" feels like a different command (`merge-into-root`).
   The spec recommends folding it into `promote`. Plan it carefully — the
   per-step JSON contract must remain unambiguous so the operator can
   tell from the dry-run output whether they're seeing "first-time
   promote of N courses" vs "fold one more course into existing root."
6. **Hidden invariant break during incremental development.** Until the
   `commands/lint.py` invariant check (R6.2) lands, the codebase can
   easily be left in a state where a page exists at root AND in a course
   simultaneously. Land R6 EARLY in the plan so the regression net is
   active throughout the rest of execution.

---

## 9. Outstanding deliverables checklist (Planner handoff)

- [ ] New modules: `commands/promote.py`, `commands/demote.py`.
- [ ] Extended modules: `_vault.py`, `commands/{init,lint,reindex,upsert_page,register_summary}.py`.
- [ ] New asset: `assets/WIKI_SCHEMA.root.template.md`.
- [ ] New reference: `references/cross_course_promotion.md`.
- [ ] New tests: `tests/commands/test_promote.py`, `test_demote.py`;
      extensions to `tests/commands/test_{lint,reindex,upsert_page}.py`;
      `tests/test__vault.py` extensions; `tests/test_e2e_promotion.py`;
      `tests/fixtures/two_course_vault/`.
- [ ] Doc updates: `SKILL.md`, `docs/ARCHITECTURE.md` (in place),
      `references/wiki_schema.md`, `scripts/wiki_ingest/.AGENTS.md`.
- [ ] Validator gates: `validate_skill.py` exit 0; `skill-validator` SAFE;
      cross-skill `diff -q` silent.
- [ ] Honest-scope items captured in KNOWN_ISSUES if surfaced during execution.

# ARCHITECTURE: wiki-ingest modular refactor + two-tier vault

> **Status (2026-05-26): TASK 015 MERGED · TASK 016 IN DESIGN.**
>
> TASK 015: All 13 atomic beads (015-00..015-12) shipped; 15 deferred
> KNOWN_ISSUES items resolved in the follow-up pass. See
> [`docs/tasks/task-015-wiki-ingest-modular-refactor.md`](tasks/task-015-wiki-ingest-modular-refactor.md)
> and [`docs/plans/plan-015-wiki-ingest-modular-refactor.md`](plans/plan-015-wiki-ingest-modular-refactor.md).
>
> TASK 016 delta: adds the **two-tier vault model** (vault-root shared layer
> vs course-local layer), lazy operator-driven `promote`/`demote` commands,
> two new F3 command modules (`commands/promote.py`, `commands/demote.py`),
> one new F2 helper (`_page_merge.py` — additive-merge primitives extracted
> from `commands/upsert_page.py` to satisfy the import-graph invariant), and
> extensions to five existing commands (`init`, `lint`, `reindex`,
> `upsert_page`, `register_summary`). Single-course vaults with no root
> `WIKI_SCHEMA.md` continue to behave byte-identically to v1 (backwards
> compatibility load-bearing).
>
> This document is the source of truth for the wiki-ingest internal layout.
> Future maintainers editing the skill must keep it in sync with the code.

---

## 1. Task Description

See archived [`docs/tasks/task-015-wiki-ingest-modular-refactor.md`](tasks/task-015-wiki-ingest-modular-refactor.md)
for the full TASK 015 specification.

**One-liner (delivered)**: split `skills/wiki-ingest/scripts/wiki_ops.py`
(was 2661 LoC, **now 69 LoC**) into a `wiki_ingest/` Python package
alongside it, with strict module boundaries and a ≤200-LoC argparse shim.
**Zero behavioural change to the CLI** (locked by R11 byte-identity gate).
Each subcommand became its own module; cross-cutting helpers form five
domain modules with a documented one-way dependency graph.

**Why we did it**: three VDD passes had grown the file faster than its
structure absorbed; per-module unit tests, future critic loops, and
feature additions are now well-isolated. **Outcome**: 138 tests across
16 files, both validators green, R9 cross-skill matrix silent.

---

## 2. Functional Architecture

### 2.1. Functional Components

The system has **three** functional layers; the refactor renders them as
distinct module groups.

#### F1. Safety & I/O Primitives

**Purpose**: every operation that touches the filesystem or accepts external
data goes through a single hardened layer — atomic writes, size-capped reads,
symlink refusal, NFKC normalisation, sanitised JSON output. These are the
defenses installed during the 2026-05-25 VDD-multi pass and must not regress.

**Functions**:
- `read_text(path, *, follow_symlink=False, max_bytes=MAX_PAGE_BYTES)` — bounded read.
- `write_text(path, content, dry_run)` → `_atomic_write_text` — tempfile + `os.replace` + `flock`.
- `_safe_name(name, kind)` — NFKC normalise + reject path separators, control chars, traversal, template placeholders.
- `_safe_inline(text, field)` — reject newlines + `## ` line-starts + bare `---`.
- `_safe_for_json(value, max_bytes=MAX_VALUE_BYTES)` — strip control chars + cap scalar length.
- `_is_relative_to(child, parent)` — backport-safe containment check.
- `_skip_symlink(path)` — directory-walk filter.
- `_check_case_collision(target_dir, name)` — case-fold + slug-collision check.
- `slugify(text)` — NFKC + Unicode-aware kebab-case.
- `die(msg, code=1)` — fatal error → stderr + exit.

**Inputs**: arbitrary user-supplied strings, filesystem paths.
**Outputs**: validated strings, file descriptors, atomic writes, sanitised JSON-safe values.

**Related Use Cases**: every subcommand (UC-1..UC-3 indirectly).

**Dependencies**: stdlib only (`os`, `tempfile`, `fcntl` on POSIX, `unicodedata`, `re`, `pathlib`, `errno`).

#### F2. Markdown / Frontmatter Engine

**Purpose**: parse + mutate Obsidian-flavour markdown deterministically.
Sections, wiki-links, YAML frontmatter — the three things every wiki op
touches — share one masking pass per page so the engine stays linear-time
even on adversarial inputs.

**Functions** (split across two modules — see §3.2):
- `_mask_code_fences(text)` — offset-preserving mask of fenced code.
- `_mask_inline_constructs(text)` — masks inline backticks + HTML comments.
- `find_section / find_all_sections / get_section_body / replace_section_body / insert_section_before` — all accept an optional pre-computed `masked` view.
- `_existing_lines(body)` — list-item recovery preserving multi-line items.
- `_extract_wikilinks_with_anchors(body, masked=None)` — `{target: {anchors}}` map.
- `_first_sentence(text)` — abbreviation-aware sentence-split, 16 KiB cap.
- `split_frontmatter(content, warnings=None)` — line-anchored YAML closer; surfaces malformed-line warnings.
- `_strip_frontmatter_fast(content)` — cheap body extractor (no parse).
- `_splice_frontmatter_fields(text, fields, fm)` — structural list-field rewrite.

**Inputs**: raw markdown text.
**Outputs**: structured (dict / set / tuple / re-serialised text).

**Related Use Cases**: UC-2 (per-module critic loop); foundational for UC-1 (any new command needs section/frontmatter manipulation).

**Dependencies**: F1 (for `die` only — fatal-error path on guard violations).

#### F3. Vault & Command Layer

**Purpose**: the public-facing CLI surface. Every subcommand reads + mutates
the vault by composing F1 + F2; vault-layout constants and the symlink-
filtering walk live in `_vault.py` so commands share one definition.

**Functions**:
- **Vault helpers** (`_vault.py`): `_walk_pages(vault)`, `load_vault_pages(vault)`, `ensure_schema(vault)`, `load_asset(name)`, `tail_log(vault, n)`.
- **Constants** (`_vault.py`): `DEFAULT_SUBDIRS`, `SUBDIR_TO_KIND`, `SUBDIR_TO_DISPLAY`, `SCHEMA_FILE`, `INDEX_FILE`, `LOG_FILE`.
- **Classify helpers** (`_classify.py`): `_count_md_structure`, `_filename_hint_score`, `_looks_like_wiki_summary`, `_classify_one_file`, `_detect_grouping`, `_group_files`, `_pick_primary`, plus the per-extension/skip/hint tables.
- **Commands** (`commands/*.py`): one file per subcommand — `scan`, `init`, `upsert_page`, `update_index`, `append_log`, `register_summary`, `log_event`, `find`, `lint`, `reindex`, `classify_folder`. Each exposes exactly two public symbols: `register(subparser)` and `execute(args)`.

**Inputs**: parsed `argparse.Namespace`.
**Outputs**: vault-file mutations, JSON-on-stdout reports.

**Related Use Cases**: UC-1 (new command path), UC-3 (E2E smoke).

**Dependencies**: F1 + F2.

### 2.1.bis. TASK 016 additions per layer

#### F1 — no new functions

All path-safety primitives required by TASK 016 (`_is_relative_to`,
`_safe_name`, `_atomic_write_text`, `_skip_symlink`, `die`) already exist.
No new F1 functions are added.

#### F2 — new module `_page_merge.py`

Additive-merge primitives extracted from `commands/upsert_page.py` so that
both `commands/upsert_page.py` and the new `commands/promote.py` can reuse
them without violating the import-graph invariant (M-2 resolution):

- `upsert_source_row(content, source_slug, source_title, source_date) → str`
- `append_fact(content, fact, source_slug) → str`
- `append_contradiction(content, existing_claim, new_fact, source_slug) → str`
- `upsert_footnote(content, source_slug, source_title) → str`

These four functions are lifted verbatim from `commands/upsert_page.py`
(which becomes a thin caller). `_page_merge.py` is an F2-tier module: it
imports from `_markdown` (section ops) and `_safety` (die), but NOT from
`_vault` or any command. The import graph remains strictly hierarchical.

Additionally, `_frontmatter.py` gains internal support for **list-of-dicts**
splice: the existing `_splice_frontmatter_fields` handles flat `list[str]`
fields; `promoted_from:` is `list[{course, date}]`. Rather than adding a
new public function, the helper is extended to detect the list-of-dicts shape
and use a structural rewrite path (the `_serialize_yaml_list_field` fallback
already present). This is an in-module change; the public signature of
`_splice_frontmatter_fields` does not change.

#### F3 helpers — `_vault.py` extensions (M-3 resolution)

R1 is split into TWO helpers as required by M-3:

- `find_vault_root(start: Path) → tuple[Path, Path | None]` — given ANY path
  inside a course directory, walks up until the first `WIKI_SCHEMA.md` (course
  root), then continues walking for a second `WIKI_SCHEMA.md` with
  `schema_version: 2.0` (vault root). Returns `(course_root, vault_root_or_None)`.
  Refuses to cross filesystem boundaries or follow symlinks during the walk
  (M-1 security caveat). Used by ingest-time commands (UC-4 / R8).

- `discover_courses(vault_root: Path) → list[Path]` — given a vault root
  (a directory with a `schema_version: 2.0` schema), walks all descendant
  directories and returns every one that contains a `WIKI_SCHEMA.md` with
  `schema_version: 1.x`. Does NOT hardcode the `Lessons/` segment (Q-8
  resolution): any subdirectory at any depth qualifies. Returns a sorted list
  for deterministic output. **Symlink discipline**: skips symlinked
  directories during the walk (inherits OVERLAP-5 from `_walk_pages`).
  **Nested course schemas**: descends into matched course directories so a
  course-of-courses (e.g. `Lessons/2026/Spring/Hermes/`) is supported — the
  result list is flat and every qualifying descendant appears independently.
  **Same-device boundary not enforced** (only `find_vault_root` enforces
  that, because it walks UP) — courses may live on different mount points
  via deliberate operator setup. Used by `promote`, `demote`, cross-course
  `lint`, root-mode `reindex`.

These two helpers have complementary callers: `find_vault_root` is called by
commands that receive a course path from the user (existing CLI surface, no
`vault_root` argument); `discover_courses` is called by commands that receive
the vault root directly (`promote`, `demote`, cross-course `lint`).

**Byte-identity caveat (M-1 resolution)**: `upsert-page` and `register-summary`
continue to accept the course-root `vault` positional argument unchanged. They
internally call `find_vault_root(vault)` to discover an optional vault root.
On single-course vaults (no root `WIKI_SCHEMA.md`), `vault_root=None` and the
code path is byte-identical to v1 (enforced by TASK 015 R11 fixtures, plus the
new `two_course_vault` fixture variant with `root_schema=None`). **Byte-identity
holds only when no root `WIKI_SCHEMA.md` is present** — with a root schema,
R8 demonstrably changes `upsert-page` behaviour (lookups land on the root page).
This is correct and expected; R11 fixtures test single-course (no root) only.

**Vault-relative footnote form (A-M-2 resolution)**: when promote / demote /
root-aware upsert rewrite a footnote definition to vault-relative form, the
path prefix is computed as `course_root.relative_to(vault_root)` — NOT the
literal substring `Lessons/<Course>/`. The form is
`[^src-<slug>]: [[<course_rel>/_sources/<slug>]] — <Title>`, where
`<course_rel>` is whatever directory the source's owning course actually
sits at relative to the vault root. The R6.4 lint check (root-page
footnote-format) likewise validates the prefix against
`{c.relative_to(vault_root) for c in discover_courses(vault_root)}`,
not against a literal `Lessons/` prefix. `Lessons/` appears only in example
JSON in §4.5 because the spec's running example uses that convention; it
is not part of the contract.

#### F3 commands — two new modules

- `commands/promote.py` (≤400 LoC) — `promote <Name>` with `--dry-run` default
  (R4), `--apply`, `--kind`, `--vault`. Dry-run is default (Q-2 locked).
- `commands/demote.py` (≤300 LoC) — `demote <Name> --to <Course>` with
  `--dry-run` available but NOT default (Q-2b locked). `--vault`, optional
  `--kind`.

Both commands import from `_safety`, `_markdown`, `_frontmatter`, `_vault`,
and `_page_merge`. Neither imports any other `commands/*.py` module (R12.5 +
`test_architecture.py` invariant preserved).

#### F3 commands — five extended modules

| Command           | Extension summary                                                                          |
|-------------------|--------------------------------------------------------------------------------------------|
| `init.py`         | Gains `--root` flag (Q-1 locked: `init <vault> --root`, not a new subcommand). Writes vault-root scaffold: `WIKI_SCHEMA.md` (from `WIKI_SCHEMA.root.template.md`), `_concepts/`, `_entities/`, optional `index.md`. Idempotent; never overwrites. |
| `lint.py`         | Gains cross-course duplicate scan + invariant check (`cross_course_duplicate`, `invariant_violation`). Dangling-link logic updated: course→root resolves (not dangling); course→other-course is dangling. Root-page footnote-format check (warning). |
| `reindex.py`      | Gains `## Shared * referenced` section for course-mode reindex; root-mode reindex (schema_version 2.0 auto-detection per M-4); `--cascade` flag for root mode. |
| `upsert_page.py`  | Calls `find_vault_root`; root-aware lookup (R8.1); vault-relative footnote form on root pages (R8.2); log marker for shared merge target (R8.3). Primitives (`upsert_source_row` etc.) delegated to `_page_merge.py`. |
| `register_summary.py` | Root-aware via `upsert_page.execute` path (no direct change to `register_summary` logic beyond the `upsert_page` delegation). |

### 2.2. Functional Components Diagram

```mermaid
graph TD
    CLI[wiki_ops.py<br/>argparse shim ≤200 LoC] --> CMDS

    subgraph F3 [F3 · Vault & Command Layer]
        CMDS[commands/*.py<br/>13 subcommand modules<br/>incl. promote · demote NEW]
        VAULT[_vault.py<br/>constants + walk + tail_log<br/>+ find_vault_root NEW<br/>+ discover_courses NEW]
        CLASSIFY[_classify.py<br/>classify-folder helpers]
    end

    subgraph F2 [F2 · Markdown / Frontmatter Engine]
        MD[_markdown.py<br/>sections + wikilinks +<br/>masking + _first_sentence]
        FM[_frontmatter.py<br/>split + parse + splice +<br/>serialize YAML lists]
        PM[_page_merge.py NEW<br/>upsert_source_row · append_fact<br/>append_contradiction · upsert_footnote]
    end

    subgraph F1 [F1 · Safety & I/O Primitives]
        SAFE[_safety.py<br/>atomic I/O · NFKC ·<br/>safe_inline · safe_for_json]
    end

    CMDS --> VAULT
    CMDS --> CLASSIFY
    CMDS --> MD
    CMDS --> FM
    CMDS --> PM
    CMDS --> SAFE

    CLASSIFY --> VAULT
    CLASSIFY --> SAFE

    VAULT --> FM
    VAULT --> SAFE

    PM --> MD
    PM --> SAFE

    MD --> SAFE
    FM --> SAFE
```

**Dependency rule (one-way only)**: F3 → F2 → F1. No back-edges. Commands
may import any F1/F2/F3-helper module but **never** another command.
`_page_merge.py` is F2: it imports `_markdown` + `_safety` only.

---

## 2.3. Two-Tier Vault Model (TASK 016)

### Vault layout

```
<vault>/                                   # Obsidian vault root
├── WIKI_SCHEMA.md                         # schema_version: 2.0  kind: vault-root
├── _concepts/                             # shared concepts (lazy — empty until first promote)
├── _entities/                             # shared entities (lazy)
├── index.md                               # optional root catalog (created on first promote)
└── Lessons/                               # or any other directory name — NOT hardcoded
    ├── Course A/                          # course-local layer
    │   ├── WIKI_SCHEMA.md                 # schema_version: 1.x
    │   ├── _sources/  _concepts/  _entities/  index.md  log.md
    └── Course B/                          # same
```

Single-course vaults (no vault-root `WIKI_SCHEMA.md`) are unaffected — all
commands detect `vault_root=None` and behave exactly as v1. The root layer is
bootstrapped via `init <vault> --root` (R2).

### One-page-one-place invariant

A given canonical filename (`Sharpe Score.md`) MUST live in exactly ONE of:
- some course's `_concepts/` or `_entities/`, OR
- the vault root's `_concepts/` or `_entities/`.

Never both. This invariant is load-bearing for Obsidian's filename-based
`[[wiki-link]]` resolution. `lint` enforces it (`invariant_violation` finding,
hard failure / non-zero exit). `promote` and `demote` maintain it transactionally.

### Discovery algorithm

```mermaid
graph LR
    A["path inside a course<br/>(any depth)"] -->|find_vault_root| B["(course_root, vault_root | None)"]
    C["vault root path"] -->|discover_courses| D["[course_root, ...]"]
```

`find_vault_root(start)`:
1. Walk up from `start` until a `WIKI_SCHEMA.md` is found → `course_root`.
2. Continue walking from `course_root.parent` until another `WIKI_SCHEMA.md`
   with `schema_version: 2.0` is found → `vault_root`. If none found → `None`.
3. Refuse to cross filesystem device boundary (symlink-loop protection).

`discover_courses(vault_root)`:
1. Walk ALL descendants of `vault_root` (any depth).
2. For each directory containing a `WIKI_SCHEMA.md` with `schema_version: 1.x`
   that is NOT the vault root itself → add to result list.
3. Return sorted list (deterministic for lint/reindex).

### Link resolution order (v2)

For a `[[Foo]]` reference from within a course:
1. `<course>/_concepts/Foo.md` — course-local concept
2. `<course>/_entities/Foo.md` — course-local entity
3. `<vault>/_concepts/Foo.md` — shared root concept
4. `<vault>/_entities/Foo.md` — shared root entity
5. Dangling — lint flags it

The skill does not configure Obsidian's resolver; the above order is
documented for the LLM's reading pass and for `lint`'s dangling-link check.

### Lazy promotion

- Ingest NEVER promotes (operator-only promotion invariant, R13).
- The root layer stays empty until the first `promote --apply`.
- New vaults work exactly like v1 until the operator runs `init --root`.
- Re-promotion (R3.7): if a root page already exists and one more course
  has a course-local copy, `promote` merges that course-local copy into the
  existing root page (additive). The pre-condition is relaxed from "≥2
  courses with course-local copies" to "≥1 course-local copy when root
  version already exists OR ≥2 course-local copies with no root version."

### Schema-version detection (M-4 resolution)

`reindex <path>` auto-detects mode by peeking `<path>/WIKI_SCHEMA.md`'s
`schema_version` field:
- `2.0` → root mode: rebuild root `index.md`; optionally cascade with
  `--cascade`.
- `1.x` → course mode: existing v1 behaviour + `## Shared * referenced`.
- Absent or mismatched → die with existing v1 message.

The same schema-peek is used by `promote`/`demote` to validate the vault root
before any reads (R9.1 / R9.2).

---

## 3. System Architecture

### 3.1. Architectural Style

**Layered monolith — single-process Python CLI** with explicit one-way
dependency layers (Safety → Engine → Commands). Each subcommand is a
*driver* over the shared engine; there is no shared mutable state and no
process boundary. The unit of deploy is one `.skill` archive.

**Justification**:
- The skill must remain installable and runnable in isolation
  ([CLAUDE.md §"Независимость скиллов"](../CLAUDE.md)) — a single-process
  layered design is the simplest shape that meets that constraint.
- No concurrency requirements (advisory `flock` covers the single
  cross-process race we care about: two agents writing the same wiki at
  the same time).
- The agent invokes one subcommand per turn — IPC / persistent daemons
  are unjustified.
- Pure stdlib (no `pip` runtime deps) is a hard constraint per CLAUDE.md;
  rules out anything frameworky.

**Alternatives considered + rejected**:
- *Plugin discovery via entry_points*: overkill for ≤15 commands and adds a
  packaging surface not currently present.
- *Async I/O*: zero async-relevant operations in the workload (all reads
  are kilobytes-to-megabytes, all writes are single files).

### 3.2. System Components

The repository layout after the refactor:

```
skills/wiki-ingest/
├── SKILL.md                            # unchanged (public-surface contract)
├── assets/                             # unchanged (markdown templates)
├── examples/                           # unchanged
├── references/
│   ├── ingest_workflow.md              # unchanged
│   ├── folder_ingest_workflow.md       # unchanged
│   ├── query_lint_workflow.md          # unchanged
│   ├── wiki_schema.md                  # unchanged
│   ├── karpathy-llm-wiki.md            # unchanged
│   └── architecture.md                 # NEW (R12 — maintainer-facing module map)
├── evals/                              # unchanged (fixtures + eval suite)
└── scripts/
    ├── wiki_ops.py                     # SHRUNK to ≤200 LoC argparse shim
    ├── wiki_ingest/                    # NEW package
    │   ├── __init__.py
    │   ├── _safety.py                  # F1 — ≤300 LoC
    │   ├── _markdown.py                # F2 — ≤350 LoC
    │   ├── _frontmatter.py             # F2 — ≤300 LoC
    │   ├── _vault.py                   # F3 helpers — ≤150 LoC
    │   ├── _classify.py                # F3 helpers — ≤350 LoC
    │   └── commands/
    │       ├── __init__.py
    │       ├── scan.py                 # ≤100 LoC
    │       ├── init.py                 # ≤100 LoC
    │       ├── upsert_page.py          # ≤250 LoC
    │       ├── update_index.py         # ≤150 LoC
    │       ├── append_log.py           # ≤150 LoC
    │       ├── register_summary.py     # ≤350 LoC (largest — fm rewrite path)
    │       ├── log_event.py            # ≤100 LoC
    │       ├── find.py                 # ≤150 LoC
    │       ├── lint.py                 # ≤300 LoC
    │       ├── reindex.py              # ≤250 LoC
    │       └── classify_folder.py      # ≤200 LoC (drives _classify.py)
    └── tests/                          # NEW — unit + E2E smoke suite
        ├── __init__.py
        ├── fixtures/                   # NEW — minimal module-targeted fixtures
        ├── test__safety.py
        ├── test__markdown.py
        ├── test__frontmatter.py
        ├── test__vault.py
        ├── test__classify.py
        ├── commands/
        │   └── test_*.py               # one per command — happy + ≥1 adversarial
        └── test_e2e_smoke.py           # init → upsert → lint → reindex byte-identity
```

**Component dossier** — for each module:

| Module                                  | Type      | Responsibility                                                                                                                                                       | LoC budget | Imports from              |
|-----------------------------------------|-----------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------|----------------------------|
| `wiki_ops.py`                           | shim      | argparse wiring + dispatch to `wiki_ingest.commands.<cmd>.execute(args)`. **The only file under `scripts/` outside the `wiki_ingest/` package.**                       | ≤200       | wiki_ingest, stdlib        |
| `wiki_ingest/__init__.py`               | package   | Empty (or version string only).                                                                                                                                      | ≤30        | —                          |
| `wiki_ingest/_safety.py`                | F1        | die · slugify · _safe_name · _safe_inline · _is_relative_to · read_text · write_text · _atomic_write_text · _safe_for_json · _skip_symlink · _check_case_collision · constants (MAX_PAGE_BYTES, MAX_SUMMARY_BYTES, MAX_VALUE_BYTES, _UNSAFE_NAME_RE, _CTRL_CHARS_RE) | ≤300       | stdlib                     |
| `wiki_ingest/_markdown.py`              | F2        | _mask_code_fences · _mask_inline_constructs · SECTION_BOUNDARY_RE · find_section / find_all_sections / get_section_body / replace_section_body · insert_section_before · _existing_lines · WIKILINK_RE / WIKILINK_ANCHOR_RE · _extract_wikilinks_with_anchors · _first_sentence · _HTML_COMMENT_RE · _TLDR_BOLD_RE · _ABBREV_RE | ≤350       | _safety                    |
| `wiki_ingest/_frontmatter.py`           | F2        | split_frontmatter · _strip_frontmatter_fast · _parse_flow_list · _strip_quotes · _strip_trailing_comment · _serialize_yaml_list_field · _splice_frontmatter_fields · _FM_CLOSER_RE · _FM_KEY_RE | ≤300       | _safety                    |
| `wiki_ingest/_vault.py`                 | F3 helper | DEFAULT_SUBDIRS · SUBDIR_TO_KIND · SUBDIR_TO_DISPLAY · SCHEMA_FILE · INDEX_FILE · LOG_FILE · ASSETS_DIR · _walk_pages · load_vault_pages · ensure_schema · load_asset · tail_log | ≤150       | _safety, _frontmatter      |
| `wiki_ingest/_classify.py`              | F3 helper | _OFFICE_EXTS / _IMAGE_EXTS / _METADATA_EXTS / _TEXT_EXTS / _SKIP_EXTS / _SKIP_NAMES / _PRIMARY_HINTS / _NON_PRIMARY_HINTS · _PREFIX_REGEX · _UNGROUPED_SENTINEL · _UNGROUPED_LABEL · _is_text_readable · _count_md_structure · _filename_hint_score · _looks_like_wiki_summary · _classify_one_file · _detect_grouping · _group_files · _pick_primary | ≤350       | _safety                    |
| `wiki_ingest/commands/<cmd>.py`         | F3 driver | One subcommand each. Public surface: `register(subparser) → None` and `execute(args) → int`. **No command imports another command.**                                  | ≤400 each  | _safety, _markdown, _frontmatter, _vault, _classify (subset per command) |
| `scripts/tests/`                        | tests     | unittest discoverable; per-module + per-command + E2E.                                                                                                               | n/a        | wiki_ingest                |

**TASK 016 module additions and extensions:**

| Module                                  | Type      | Responsibility                                                                                                                                                            | LoC budget | Imports from                          |
|-----------------------------------------|-----------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------|---------------------------------------|
| `wiki_ingest/_page_merge.py`            | F2 NEW    | Additive-merge primitives extracted from `commands/upsert_page.py`: `upsert_source_row`, `append_fact`, `append_contradiction`, `upsert_footnote`. Also hosts `render_stub_page` if it references section ops. No vault I/O — pure content mutation. | ≤150       | `_markdown`, `_safety`               |
| `wiki_ingest/commands/promote.py`       | F3 NEW    | `promote <Name> [--kind concept\|entity] [--vault V] [--apply]`. Dry-run default. Calls `discover_courses`, reads N course-local copies, merges frontmatter + body via `_page_merge`, rewrites footnotes to vault-relative form, writes root page, deletes course copies, updates all indexes and logs. Emits `PromotionPlan` JSON on dry-run, `{applied, merged_to, merged_from, contradictions_raised}` on apply. ≤400 LoC. | ≤400       | `_safety`, `_markdown`, `_frontmatter`, `_vault`, `_page_merge` |
| `wiki_ingest/commands/demote.py`        | F3 NEW    | `demote <Name> --to <Course> [--vault V] [--dry-run]`. Dry-run NOT default (Q-2b). Checks cross-course citation refusal (R5.2), moves root page to target course, rewrites footnotes to short form, strips `promoted_from:`, updates indexes and log. Emits `DemotionPlan` JSON on dry-run. ≤300 LoC. | ≤300       | `_safety`, `_markdown`, `_frontmatter`, `_vault`, `_page_merge` |
| `wiki_ingest/_vault.py` (extended)      | F3 helper | **New functions**: `find_vault_root(start) → tuple[Path, Path\|None]`; `discover_courses(vault_root) → list[Path]`. Existing functions and constants unchanged. LoC budget extended to ≤250. | ≤250       | `_safety`, `_frontmatter`             |
| `wiki_ingest/_frontmatter.py` (extended)| F2        | Internal extension: `_splice_frontmatter_fields` gains list-of-dicts rewrite path for `promoted_from:` field. Public signature unchanged. LoC budget extended to ≤350. | ≤350       | `_safety`                             |
| `wiki_ingest/commands/init.py` (extended)| F3       | Gains `--root` flag. New branch writes vault-root scaffold from `WIKI_SCHEMA.root.template.md` asset. Idempotent. R2.3: `init` without `--root` is unchanged. | ≤150       | `_safety`, `_vault`                   |
| `wiki_ingest/commands/lint.py` (extended)| F3       | New passes: `cross_course_duplicate`, `invariant_violation`. Dangling-link updated for two-tier namespace. Root-page footnote-format warning (R6.4). Sort discipline: findings alphabetical by `name` (m-5 resolution). | ≤450       | `_safety`, `_markdown`, `_frontmatter`, `_vault` |
| `wiki_ingest/commands/reindex.py` (extended)| F3   | New: `## Shared concepts referenced` + `## Shared entities referenced` sections. Root-mode via schema-version auto-detection (M-4). `--cascade` flag. | ≤350       | `_safety`, `_markdown`, `_frontmatter`, `_vault` |
| `wiki_ingest/commands/upsert_page.py` (extended)| F3 | Root-aware lookup (R8.1). Vault-relative footnote on root page (R8.2). Log marker for shared target (R8.3). Delegates merge primitives to `_page_merge`. Thin wrapper pattern. | ≤250       | `_safety`, `_markdown`, `_frontmatter`, `_vault`, `_page_merge` |

**New assets and fixtures:**

| Path                                                           | Purpose                                                          |
|----------------------------------------------------------------|------------------------------------------------------------------|
| `assets/WIKI_SCHEMA.root.template.md`                          | Root-schema template with `schema_version: 2.0` + `kind: vault-root` |
| `tests/fixtures/two_course_vault/`                             | Two-course fixture with overlapping `Sharpe Score` + unique concepts |
| `tests/commands/test_promote.py`                               | promote happy-path, 3-course merge, kind-mismatch, re-promote, dry-run, contradictions |
| `tests/commands/test_demote.py`                                | demote happy-path, cross-course citation refusal, footnote rewrite, fm restore |
| `tests/commands/test_lint.py` (extended)                       | New categories + cross-layer dangling refinement                 |
| `tests/commands/test_reindex.py` (extended)                    | Shared-referenced sections + root-mode + cascade + custom-section preservation |
| `tests/commands/test_upsert_page.py` (extended)                | Root-layer-first lookup + vault-relative footnote                |
| `tests/test__vault.py` (extended)                              | `find_vault_root` single/two-tier/nested/schema-mismatch cases   |
| `tests/test_e2e_promotion.py`                                  | Round-trip: ingest → lint detects dup → promote → lint clean → demote → lint clean |

**Import-graph invariant** — enforced by `tests/test_architecture.py`
that walks each module via the `ast` module and asserts: (a) no
`wiki_ingest/_*.py` file imports `wiki_ingest.commands.*`, and (b) no
`wiki_ingest/commands/<a>.py` imports `wiki_ingest/commands/<b>.py`.
TASK 016 preserves this invariant: `_page_merge.py` is an F2 module (no
commands import), and `promote.py`/`demote.py` import only F1/F2/F3-helper
modules — never another command.

### 3.3. Components Diagram

```mermaid
graph LR
    subgraph "scripts/"
        SHIM[wiki_ops.py<br/>argparse + dispatch<br/>≤200 LoC]
    end

    subgraph "scripts/wiki_ingest/"
        SAFETY[_safety.py]
        MARKDOWN[_markdown.py]
        FRONTMATTER[_frontmatter.py]
        PAGEMERGE["_page_merge.py NEW<br/>upsert_source_row<br/>append_fact etc."]
        VAULT["_vault.py<br/>+find_vault_root NEW<br/>+discover_courses NEW"]
        CLASSIFY[_classify.py]

        subgraph "commands/"
            SCAN[scan]
            CINIT["init<br/>+--root NEW"]
            UPSERT["upsert_page<br/>+root-aware"]
            UPDIDX[update_index]
            APLOG[append_log]
            REGSUM[register_summary]
            LOGEV[log_event]
            FIND[find]
            LINT["lint<br/>+cross-course NEW"]
            REINDEX["reindex<br/>+root-mode NEW"]
            CFOLDER[classify_folder]
            PROMOTE["promote NEW"]
            DEMOTE["demote NEW"]
        end
    end

    SHIM --> SCAN & CINIT & UPSERT & UPDIDX & APLOG & REGSUM & LOGEV & FIND & LINT & REINDEX & CFOLDER & PROMOTE & DEMOTE
    SCAN --> VAULT
    CINIT --> VAULT & SAFETY
    UPSERT --> VAULT & MARKDOWN & FRONTMATTER & PAGEMERGE & SAFETY
    UPDIDX --> VAULT & MARKDOWN & SAFETY
    APLOG --> VAULT & SAFETY
    REGSUM --> VAULT & FRONTMATTER & SAFETY
    LOGEV --> VAULT & SAFETY
    FIND --> VAULT & FRONTMATTER & SAFETY
    LINT --> VAULT & MARKDOWN & FRONTMATTER & SAFETY
    REINDEX --> VAULT & MARKDOWN & FRONTMATTER & SAFETY
    CFOLDER --> CLASSIFY & VAULT & SAFETY
    PROMOTE --> VAULT & MARKDOWN & FRONTMATTER & PAGEMERGE & SAFETY
    DEMOTE --> VAULT & MARKDOWN & FRONTMATTER & PAGEMERGE & SAFETY

    VAULT --> FRONTMATTER & SAFETY
    CLASSIFY --> SAFETY
    PAGEMERGE --> MARKDOWN & SAFETY
    MARKDOWN --> SAFETY
    FRONTMATTER --> SAFETY
```

---

## 4. Data Model

The refactor introduces **no new persistent data structures** — vault layout
(`_sources/`, `_concepts/`, `_entities/`, `index.md`, `log.md`, `WIKI_SCHEMA.md`)
is unchanged. The internal data exchanged between layers stays as plain
Python dicts / sets / strings, but the contract is now explicit:

### 4.1. PageDict (returned by `load_vault_pages` and built inline by `cmd_lint`)

```python
{
    "path": str,                # vault-relative path, e.g. "_concepts/Foo.md"
    "raw": str,                 # full file content (UTF-8)
    "fm": dict,                 # parsed frontmatter (from split_frontmatter)
    "kind": str,                # "concept" | "entity" | "source" | "unknown"
    # OPTIONAL — present only on the cmd_lint enrichment path:
    "masked": str,              # _mask_inline_constructs(_mask_code_fences(raw))
    "wikilinks": set[str],      # bare target names
    "wikilinks_anchors": dict[str, set[str]],  # {target: {anchor, ...}}
}
```

### 4.2. SectionLocation (returned by `find_section`)

```python
tuple[int, int, int]  # (header_start, body_start, body_end) — offsets into
                      # the ORIGINAL content; the mask preserves offsets.
None                  # if the requested occurrence is not present.
```

### 4.3. WikilinkMap (returned by `_extract_wikilinks_with_anchors`)

```python
dict[str, set[str]]   # {target_name: {anchor_or_empty, ...}}
                      # anchor "" means anchor-less reference; "#API" etc.
                      # are surfaced verbatim in dangling-link reports (L-L4).
```

### 4.4. Frontmatter dict (returned by `split_frontmatter`)

Plain `dict[str, str | list]`. Lists may contain strings OR inner dicts (for
the `key:\n  - subkey: value` pattern). `warnings: list[str] | None` is an
out-parameter for malformed-line surfacing (L-M5).

### 4.5. TASK 016 new data structures

#### 4.5.1. PromotedPageFrontmatter

Frontmatter added to a page when it is promoted to the vault root:

```yaml
schema_version: 2.0         # present only on vault-root WIKI_SCHEMA.md (not on content pages)
kind: vault-root             # present only on vault-root WIKI_SCHEMA.md
promoted_from:
  - course: "Course A"
    date: "2026-05-26"
  - course: "Course B"
    date: "2026-05-26"
```

`promoted_from` is a `list[dict]` with keys `course: str` and `date: str`.
Demote removes this field entirely. Re-promote appends to the list (does not
replace). The `_splice_frontmatter_fields` helper is extended to handle this
list-of-dicts shape (existing flat-list path is unchanged).

#### 4.5.2. PromotionPlan (dry-run JSON envelope)

```python
{
    "merge_from": ["Lessons/Course A/_concepts/Sharpe Score.md",
                   "Lessons/Course B/_concepts/Sharpe Score.md"],
    "merge_to": "_concepts/Sharpe Score.md",
    "delete": ["Lessons/Course A/_concepts/Sharpe Score.md",
               "Lessons/Course B/_concepts/Sharpe Score.md"],
    "index_updates": [
        {"course": "Course A", "op": "move_to_shared"},
        {"course": "Course B", "op": "move_to_shared"},
        {"course": None, "op": "add_to_root_index"},
    ],
    "log_appends": [
        {"course": "Course A", "body": "## [2026-05-26] promote | Sharpe Score\n..."},
        {"course": "Course B", "body": "..."},
    ],
    "contradictions_raised": 0,
    "noop": false
}
```

When `--apply` succeeds, the output is:
```python
{"applied": true, "merged_to": "...", "merged_from": [...], "contradictions_raised": 0}
```
Re-running `--apply` when the page is already at root (no course-local copies)
is a no-op:
```python
{"applied": true, "noop": true}
```

#### 4.5.3. DemotionPlan (dry-run JSON envelope)

```python
{
    "move_from": "_concepts/Sharpe Score.md",
    "move_to": "Lessons/Course A/_concepts/Sharpe Score.md",
    "index_updates": [
        {"course": None, "op": "remove_from_root_index"},
        {"course": "Course A", "op": "move_from_shared_to_local"},
    ],
    "log_appends": [{"course": "Course A", "body": "..."}],
    "refused_citations": []
}
```

`refused_citations` lists `(course, source_slug)` pairs when demote is refused
(non-empty → demote aborts with non-zero exit).

#### 4.5.4. Lint finding categories (new)

```python
# cross_course_duplicate — per-item shape
{
    "category": "cross_course_duplicate",
    "name": "Sharpe Score",
    "kind": "concept",
    "courses": [
        "Lessons/Course A/_concepts/Sharpe Score.md",
        "Lessons/Course B/_concepts/Sharpe Score.md"
    ],
    "suggest": 'wiki-ingest promote "Sharpe Score"'
}

# invariant_violation — per-item shape
{
    "category": "invariant_violation",
    "name": "Sharpe Score",
    "root_path": "_concepts/Sharpe Score.md",
    "course_paths": ["Lessons/Course A/_concepts/Sharpe Score.md"],
    "suggest": 'wiki-ingest promote "Sharpe Score" or demote it'
}
```

Both lists are sorted alphabetically by `name` within their category
(m-5 / determinism gate). The presence of any `invariant_violation` item
causes lint to exit non-zero (hard failure).

### 4.6. Derived rules / invariants

1. **Offset stability under masking**: every masking function preserves byte
   offsets (newlines preserved, non-newline content replaced with spaces).
   `find_section`'s returned `(header_start, body_start, body_end)` are
   valid in both the masked AND the original content. Tested by
   `tests/test__markdown.py::test_offsets_under_mask`.
2. **Mask-once invariant**: `find_section / find_all_sections /
   get_section_body / replace_section_body` accept a `masked` parameter so
   callers in `cmd_lint` and `cmd_reindex` can pay the masking cost ONCE
   per page (closes the pre-refactor O(K²·L) ReDoS class).
3. **No symlink under `_walk_pages`**: every page emitted by `_walk_pages`
   is a regular file (or follow-up `try/except OSError` returns "" if it
   was raced into a symlink between the walk and the read).
4. **Atomic-write rename**: `write_text` is observable as either "old file"
   or "new file", never "half-new file".

---

## 5. Interfaces

### 5.1. Public CLI

TASK 015 subcommands are unchanged. TASK 016 adds two new subcommands and
one new flag on `init`:

```
wiki_ops.py {scan|init|upsert-page|update-index|append-log|
             register-summary|log-event|find|lint|reindex|
             classify-folder|promote|demote} ...
```

**`init` extension (Q-1 locked: `--root` flag on `init`, not a new subcommand)**:
```
wiki_ops.py init <vault> [--root]
```
`--root` writes the vault-root scaffold. Without `--root`, behaviour is
unchanged (course-local wiki scaffold). (R2.3)

**`promote` grammar**:
```
wiki_ops.py promote <Name> --vault <vault>
                   [--kind concept|entity]
                   [--apply]
```
- Default: dry-run (prints `PromotionPlan` JSON to stdout, writes nothing).
- `--apply`: performs all writes.
- `--kind`: optional; auto-inferred when all duplicates agree; error if mixed.
- `--vault`: path to the vault root (the directory with the `schema_version: 2.0` schema).

**`demote` grammar**:
```
wiki_ops.py demote <Name> --to <Course> --vault <vault>
                   [--kind concept|entity]
                   [--dry-run]
```
- Default: applies immediately (dry-run NOT default, Q-2b locked).
- `--dry-run`: prints `DemotionPlan` JSON, writes nothing.
- `--to <Course>`: required; target course name (not a path — resolved against the `discover_courses(vault_root)` result list by matching the last path segment of each course root; `Lessons/` convention is honoured but not hardcoded; the value is passed through `_safe_name`).
- `--vault`: path to the vault root.

**Existing subcommand changes (R11 byte-identity caveat)**:
- `upsert-page <vault> ...` — vault positional unchanged; gains internal
  `find_vault_root(vault)` call. Byte-identical when no root schema present.
- `lint <vault>` — vault positional unchanged; cross-course passes are additive.
- `reindex <path>` — path positional unchanged; mode auto-detected by schema
  version (M-4 resolution, see §2.3). `--cascade` flag added (root mode only).

### 5.2. Command Module Contract (NEW internal interface — unchanged from TASK 015)

Every `wiki_ingest/commands/<cmd>.py` exposes exactly two symbols:

```python
def register(sub: argparse._SubParsersAction) -> None:
    """Attach this command's subparser. Called once at startup by wiki_ops.py."""

def execute(args: argparse.Namespace) -> int:
    """Run the command. Return process exit code (0 = success)."""
```

`wiki_ops.py` dispatches by calling `execute` after `argparse.parse_args`.
The shim **does not import** the command's helpers, only the two public
symbols.

### 5.3. Internal helper boundary — `_page_merge.py` (M-2 resolution)

`_page_merge.py` is an F2-tier module. Its four public functions are the
**only** permitted path for additive-merge operations. Both
`commands/upsert_page.py` and `commands/promote.py` import from it.

**What is allowed**:
- Any F3 command may import `_page_merge.upsert_source_row` etc.
- `_page_merge` may import from `_markdown` and `_safety`.

**What is forbidden**:
- `_page_merge` must NOT import from `_vault` or any `commands/*.py`.
- No command may import the merge primitives from `commands/upsert_page`
  (the `test_architecture.py` invariant test will fail if attempted).

Future maintainers: if a new merge primitive is needed that requires vault
I/O, it belongs in `commands/promote.py` or a new F3-helper — NOT in
`_page_merge.py`. Keep `_page_merge.py` pure-content (string-in, string-out).

### 5.4. F1 / F2 / F3 internal APIs (unchanged from TASK 015)

Helper-module surface is informally public *within the package only*. The
underscore prefix on the module names (`_safety.py`, `_markdown.py`, etc.)
signals that external consumers should not import them. The Universal-Skills
convention does not yet have a stable "public" tier for wiki-ingest; the
SKILL.md CLI is the only stable surface.

### 5.5. Test discovery

```
cd skills/wiki-ingest/scripts
python3 -m venv .venv && source .venv/bin/activate
python -m unittest discover -s tests
```

Per CLAUDE.md §1 "Testing" — no globally-installed deps; venv is local to
the skill.

---

## 6. Technology Stack

- **Python 3.9+** (matches `_is_relative_to` backport heuristic; `match/case`
  is NOT used so 3.10 is not required).
- **stdlib only**: `argparse`, `errno`, `json`, `math`, `os`, `re`, `sys`,
  `tempfile`, `unicodedata`, `datetime`, `pathlib`, `fcntl` (POSIX guard).
- **No new runtime dependencies introduced by TASK 015 or TASK 016** (pure
  stdlib constraint is locked for the wiki-ingest skill).
- **Dev / test**: `unittest` (stdlib). No `pytest`, no `tox`, no `hypothesis`
  for v1 — keeps the test surface portable.

---

## 7. Security

The refactor preserves every defence installed in the 2026-05-25 VDD-multi
pass. None of these may regress; tests in `tests/test__safety.py` and
`tests/commands/test_*.py` lock them in.

| ID         | Defence                                                                                       | Location after refactor                                  |
|------------|------------------------------------------------------------------------------------------------|-----------------------------------------------------------|
| OVERLAP-1  | Atomic write + `flock` + `O_NOFOLLOW`                                                          | `_safety.py::_atomic_write_text`, `write_text`            |
| OVERLAP-5  | Symlink-skipping directory walks                                                               | `_vault.py::_walk_pages`, `load_vault_pages`              |
| S-H1       | Path containment via `is_relative_to`                                                          | `_safety.py::_is_relative_to`; called from `upsert_page`, `register_summary` |
| S-H2       | `O_NOFOLLOW` on `read_text`, size cap                                                          | `_safety.py::read_text`                                    |
| S-M1       | `WIKI_INGEST_INBOX_ROOT` containment + sensitive-path blocklist for `register-summary`         | `commands/register_summary.py`                            |
| S-M2       | Mask-once, scan-once in `find_all_sections` (closes ReDoS)                                     | `_markdown.py::find_all_sections`                         |
| S-M5       | NFKC normalisation in `slugify` + `_safe_name`                                                 | `_safety.py`                                              |
| S-M6       | `_safe_for_json` on every JSON-bound scalar                                                   | `_safety.py`; called from `commands/find.py`, `commands/lint.py`, `commands/register_summary.py` |
| L-C1..L-C3 | Frontmatter close-delimiter + section-boundary correctness                                     | `_frontmatter.py::split_frontmatter`, `_markdown.py::SECTION_BOUNDARY_RE` |
| L-H1, L-L4 | `_mask_inline_constructs` for wikilink extraction; anchor-aware variant                        | `_markdown.py`                                            |
| L-H4       | Log idempotency via bounded line-lookahead (no catastrophic regex)                             | `commands/append_log.py`                                   |
| L-H5       | Structural frontmatter rewrite (`_splice_frontmatter_fields`)                                  | `_frontmatter.py`                                          |

**New attack surface introduced by the refactor**: **none.** The package
introduces no new `subprocess`, no new file I/O, no new network paths. It
re-shapes existing call graphs only.

**TASK 016 security additions:**

| ID         | Defence                                                                                               | Location                                            |
|------------|-------------------------------------------------------------------------------------------------------|-----------------------------------------------------|
| T16-S1     | Vault-root containment for `--to <Course>` in `demote`: `_safe_name` + `_is_relative_to(<vault>/..., vault)` | `commands/demote.py` |
| T16-S2     | `find_vault_root` symlink-loop / cross-device refusal: walk-up aborts if `stat().st_dev` changes between steps or if any intermediate directory is a symlink | `_vault.py::find_vault_root` |
| T16-S3     | Footnote-format rewrite regex anchoring: `FOOTNOTE_DEF_RE` anchored to `^` and line-end with `re.M`; a single `[^src-slug]` key can only match once per line — prevents "second-definition smuggling" via a deliberately malformed footnote that repeats the same key on consecutive lines | `commands/promote.py`, `commands/demote.py` |
| T16-S4     | `--name <Name>` argument for `promote`/`demote` passed through `_safe_name(name, kind="name")` — inherits NFKC normalisation, path-separator rejection, control-char rejection, template-placeholder rejection | `commands/promote.py`, `commands/demote.py` |
| T16-S5     | Atomic-write discipline extended: root `index.md`, root concept/entity page, course `index.md`, course `log.md` all use `_atomic_write_text` + `flock` | `commands/promote.py`, `commands/demote.py` |

**Threat-model unchanged**: the wiki-ingest skill is a local-fs CLI. TASK 016
introduces no new subprocess, no new network paths, no new external deps. The
new attack surface (cross-course file moves) is bounded by the same `_is_relative_to` +
`_safe_name` + `_atomic_write_text` stack already defending v1 commands.

---

## 8. Scalability and Performance

The refactor's perf properties are inherited from the pre-refactor code,
which is already linear in vault size after the OVERLAP-3 fix (mask-once).
Module-boundary cost: **sub-microsecond per call** — Python import is
cached, and cross-module function calls are dwarfed by I/O and regex work
in every workload below.

| Workload          | Pages | Pre-refactor wall-time (already optimised) | Refactor delta |
|-------------------|-------|---------------------------------------------|----------------|
| `scan`            | 500   | <0.1 s                                       | ≤+5 ms (import) |
| `lint`            | 500   | ~0.3 s                                       | ≤+5 ms          |
| `lint`            | 5000  | ~3 s                                         | ≤+5 ms          |
| `reindex`         | 500   | ~0.4 s                                       | ≤+5 ms          |
| `find --terms X`  | 500   | <0.2 s                                       | ≤+5 ms          |

All numbers assume an SSD and the per-skill `.venv` already warmed.

**Per-module budgets** (LoC) are listed in §3.2; the corresponding tests are
required by R7.1 / R8 in [TASK.md](TASK.md#2-requirements-traceability-matrix-rtm).

**TASK 016 performance constraints** (from TASK §4.1):

| Operation                               | Constraint              | Implementation note                                    |
|-----------------------------------------|-------------------------|--------------------------------------------------------|
| `find_vault_root(start)`                | O(depth) — single walk-up | Stat at most `depth` directories; no full tree scan   |
| `discover_courses(vault_root)`          | O(total directories)    | Single `os.walk` pass; no re-entry                     |
| `lint` (incl. cross-course)             | ≤ 0.5 s on 5×100 vault  | Cross-course scan is O(N) — one dict keyed by filename |
| `promote` dry-run                       | ≤ 0.2 s                 | Reads N course pages + merges in memory; no extra I/O  |
| `promote --apply`                       | ≤ 0.4 s                 | Adds atomic writes for root page + delete + log        |
| `reindex --cascade` (5×100 vault)       | ≤ 1 s                   | Sequential per course; reuse mask-once per page        |

Demote's cross-course citation scan (R5.2) is O(courses × sources × footnotes);
the existing `_extract_wikilinks_with_anchors` mask-once path is reused to keep
it linear. On a 5×100×20 fixture that is ≈10k regex ops — well under the 0.5 s
budget given the per-op cost is sub-microsecond on modern hardware.

---

## 9. Cross-Skill Replication Boundary (CLAUDE.md §2)

**Not triggered.** wiki-ingest does not share any file with
docx/xlsx/pptx/pdf — neither the `office/` package, nor `_soffice.py`,
nor `_errors.py`, nor `preview.py`, nor `office_passwd.py`. The pre-refactor
cross-skill `diff -qr` matrix is silent; the post-refactor matrix MUST stay
silent.

Manual verification command:
```bash
find skills/wiki-ingest/scripts -name "*.py" -exec basename {} \; \
  | sort -u > /tmp/wi.txt
for s in docx xlsx pptx pdf; do
  find skills/$s/scripts -name "*.py" -exec basename {} \; | sort -u \
    | comm -12 - /tmp/wi.txt
done
# Expected output: empty.
```

---

## 10. Honest Scope

- **No behavioural change**: every CLI subcommand emits byte-identical
  stdout for the three deterministic eval scenarios (`scan` on a fixture
  vault, `lint` on a fixture vault, `classify-folder` on the trading-bot
  fixture folder). `append-log` and `log-event` are excluded — they write
  timestamps and are non-deterministic across runs. **R11 fixtures must
  commit a static `log.md`** — no `append-log` / `log-event` is run as
  part of fixture setup; otherwise `cmd_scan`'s `last_log_entries`
  (sourced from `tail_log`) drifts daily and the `diff -q` gate
  silently breaks. **Determinism pre-check** (step 015-00): on day 1 of
  execution, verify that `scan` / `lint` / `classify-folder` produce sorted
  keys / sorted file iteration. If drift is found, a pre-refactor commit
  introduces `sort_keys=True` + sorted `_walk_pages` output BEFORE module
  extraction begins.
- **Tests are new**: pre-refactor there is no `tests/` directory. The
  refactor adds one; the tests are NEW lines of code with NEW coverage,
  not a translation of an existing suite.
- **Architecture document is per-skill, not per-repo**: this file
  describes wiki-ingest specifically. Other skills have their own
  architecture inside `skills/<skill>/references/` (when present) or are
  documented elsewhere.

---

## 11. Atomic-Chain Skeleton (Planner handoff)

Stub-First decomposition — each step is independently revertable, gated by
`diff -q` silent + unit tests green:

| Step  | Title                                      | Touches                                                        | Verifies                            |
|-------|--------------------------------------------|----------------------------------------------------------------|--------------------------------------|
| 015-00 | Pre-refactor determinism check / fix       | `scan`, `lint`, `classify_folder` in `wiki_ops.py`             | Pre/post `diff -q` silent on fixtures |
| 015-01 | Create `wiki_ingest/` package skeleton + extract `_safety.py` | `scripts/wiki_ingest/__init__.py`, `scripts/wiki_ingest/_safety.py`, `wiki_ops.py` imports | Unit tests for `_safety.py`; smoke tests pass |
| 015-02 | Extract `_markdown.py`                     | `scripts/wiki_ingest/_markdown.py`                              | `tests/test__markdown.py`            |
| 015-03 | Extract `_frontmatter.py`                  | `scripts/wiki_ingest/_frontmatter.py`                           | `tests/test__frontmatter.py`         |
| 015-04 | Extract `_vault.py`                        | `scripts/wiki_ingest/_vault.py`                                 | `tests/test__vault.py`               |
| 015-05 | Extract `_classify.py`                     | `scripts/wiki_ingest/_classify.py`                              | `tests/test__classify.py`            |
| 015-06 | Move `scan` + `init` to `commands/`        | `commands/scan.py`, `commands/init.py`, `wiki_ops.py` shim       | Per-command tests + E2E smoke        |
| 015-07 | Move `upsert_page` + `update_index`        | `commands/upsert_page.py`, `commands/update_index.py`           | Per-command tests + E2E smoke        |
| 015-08 | Move `append_log` + `log_event`            | `commands/append_log.py`, `commands/log_event.py`                | Per-command tests                    |
| 015-09 | Move `register_summary`                    | `commands/register_summary.py`                                   | Per-command tests (adversarial)      |
| 015-10 | Move `find` + `lint` + `reindex`           | `commands/find.py`, `commands/lint.py`, `commands/reindex.py`     | Per-command tests + E2E smoke        |
| 015-11 | Move `classify_folder`                     | `commands/classify_folder.py`                                    | Per-command tests                    |
| 015-12 | Trim `wiki_ops.py` to ≤200 LoC + add `references/architecture.md` | `wiki_ops.py`, `references/architecture.md`                     | `validate_skill.py` + `skill-validator/validate.py` |

Each step ships its own tests; the pipeline never has a long-lived
half-refactored state in `main`.

**TASK 016 atomic-bead chain:**

Each bead is independently revertable. Gated by: per-bead tests green +
`validate_skill.py` exit 0 + `test_architecture.py` green. The chain is
ordered (per A-M-1 resolution) to land the **invariant-enforcement net
(016-04, lint extensions)** BEFORE any state-mutating bead (`promote --apply`
in 016-06), per TASK §8 risk 6. The `_splice_frontmatter_fields` list-of-dicts
extension (A-M-3) is its own bead (016-02), so 016-06 can assume the helper
is shipped. The existing `test_architecture.py` already covers new `_*.py`
helper modules via `rglob` (m-A-1) — no test code edits are required for
016-01; the bead's verifies-gate is "test still green against the new module."

| Step   | Title                                                    | Touches                                                                                                              | Verifies                                                                 |
|--------|----------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| 016-00 | Pre-flight: `find_vault_root` + `discover_courses`       | `_vault.py` (new functions, symlink-skipping `discover_courses`), `tests/test__vault.py` (extended: single-course, two-tier, nested, schema-mismatch, symlink, cross-fs) | `test__vault.py` green; `test_architecture.py` green; no behavioural change |
| 016-01 | Extract `_page_merge.py` from `commands/upsert_page.py` | New `wiki_ingest/_page_merge.py` hosting `upsert_source_row` / `append_fact` / `append_contradiction` / `upsert_footnote`; `commands/upsert_page.py` becomes thin caller | `test__page_merge.py` (new); `test_upsert_page.py` still green; `test_architecture.py` still green against the new F2 module; byte-identity on v1 fixtures |
| 016-02 | Extend `_splice_frontmatter_fields` for list-of-dicts (A-M-3) | `_frontmatter.py` gains list-of-dicts code path inside `_splice_frontmatter_fields`; public signature unchanged; `tests/test__frontmatter.py` extended | New `test__frontmatter.py` cases: write `promoted_from:` as `list[dict]`, remove same field, round-trip; existing tests still green |
| 016-03 | Root-schema scaffold: `WIKI_SCHEMA.root.template.md` + `init --root` | New asset `assets/WIKI_SCHEMA.root.template.md`; `commands/init.py` extended with `--root` branch (`os.makedirs(..., exist_ok=True)` for `_concepts/` + `_entities/`; no sentinel files; idempotent) | `tests/commands/test_init.py` extended (`--root` happy path, idempotent, never overwrites, no sentinel files) |
| 016-04 | `commands/lint.py` extensions (invariant net lands FIRST, A-M-1) | `commands/lint.py` (cross-course dup + `invariant_violation` + dangling-link cross-layer refinement + root-footnote-format warning, all sorted alphabetically by `name`); `tests/commands/test_lint.py` extended | New lint categories; `invariant_violation` non-zero exit; dangling-link cross-layer; sort discipline preserves byte-identity on fixtures |
| 016-05 | `commands/promote.py` skeleton + dry-run path            | New `commands/promote.py` (skeleton); `wiki_ops.py` gains `promote` registration; new `tests/commands/test_promote.py` | `test_promote.py` dry-run cases: no-duplicate refusal, kind-mismatch, dry-run JSON output; `lint` invariant-net (016-04) catches any incidental write regression |
| 016-06 | `promote --apply` write path + log append (first state-mutating bead, covered by 016-04 net) | `commands/promote.py` (write path; footnote rewrite uses `course_root.relative_to(vault_root)` per A-M-2); `tests/commands/test_promote.py` extended (happy 2-course, 3-course, re-promote, contradictions) | All `test_promote.py` cases; round-trip on `two_course_vault` fixture; post-apply `lint` reports no invariant violation |
| 016-07 | `commands/demote.py` (full)                              | New `commands/demote.py`; `wiki_ops.py` gains `demote`; new `tests/commands/test_demote.py`; footnote rewrite back to short form | `test_demote.py`: happy path, cross-course citation refusal, footnote rewrite, fm restore, dry-run; post-demote `lint` clean |
| 016-08 | `commands/reindex.py` extensions                         | `commands/reindex.py` (Shared-referenced sections + root-mode via schema-peek per M-4 + `--cascade`); `tests/commands/test_reindex.py` extended | `## Shared * referenced` output; root-mode rebuild; cascade; custom-section preservation |
| 016-09 | `commands/upsert_page.py` root-aware lookup              | `commands/upsert_page.py` (calls `find_vault_root`, root-first lookup, vault-relative footnote per A-M-2); `tests/commands/test_upsert_page.py` extended | Root-layer lookup; vault-relative footnote on root page; v1 byte-identity on single-course fixture |
| 016-10 | E2E round-trip + documentation + validators              | `tests/test_e2e_promotion.py` (new); `tests/fixtures/two_course_vault/` (new); `SKILL.md` updates; `references/cross_course_promotion.md` (new); `references/wiki_schema.md` extended; `.AGENTS.md` updated | `test_e2e_promotion.py` full round-trip; `validate_skill.py` exit 0; `skill-validator` SAFE; cross-skill `diff -q` silent |

---

## 12. Open Questions

### TASK 015 open questions (resolved)

1. **Package vs flat layout** — **package wins**. **Decided.**
2. **Global `--inbox-root`** — defer (out of scope; would change SKILL.md).
3. **Fixture re-use** — reuse `evals/fixtures/` for R11; add tiny targeted
   fixtures under `tests/fixtures/` only where needed.
4. **Underscore prefixes** — keep `_*.py` for internal modules.
5. **Command discovery** — hard-code in `wiki_ops.py` for v1.

### TASK 016 open questions (locked defaults)

The following questions from TASK.md §5 are closed by this architecture
document. Defaults are locked; the Planner need not revisit them.

| ID  | Question                                                 | Locked decision                                                                      |
|-----|----------------------------------------------------------|--------------------------------------------------------------------------------------|
| Q-1 | `init --root` vs `init-root` subcommand                  | `init <vault> --root` flag. One flag, smaller surface. (m-1 resolved)               |
| Q-2 | `--dry-run` default for `promote`                        | Dry-run IS the default; `--apply` required to commit. (R4)                           |
| Q-2b| `--dry-run` default for `demote`                         | Dry-run is NOT the default; `--dry-run` is an explicit opt-in flag.                  |
| Q-3 | Promotion threshold configurable?                        | Hard-coded at 2; no schema field. Defer.                                              |
| Q-4 | Root-level `log.md`                                      | NO. Out of scope (R13.2). Affected courses' logs carry the operation.                |
| Q-5 | Auto-promotion opt-in flag                               | NO. Operator-only. (R13)                                                              |
| Q-6 | `description:` merge policy                              | Pick the LONGER of the two values. Operator may edit afterwards.                     |
| Q-7 | Bidirectional `[[Course A/Foo]]` normalisation           | LEAVE ALONE. Operator intent preserved.                                               |
| Q-8 | Course discovery: convention vs hardcoded `Lessons/`     | `discover_courses` walks ALL descendants with `schema_version: 1.x` — not hardcoded. (M-3 + §2.3) |
| Q-9 | Root-page footnote format check level                    | `warning` (non-fatal; consistent with other format checks).                          |
| Q-10| Promote-time contradiction detection algorithm           | Literal-line-diff (cheap; matches v1 contradiction surfacing). No predicate-extraction. (m-3 resolution) |

---

## 13. Decision-Record Summary

### TASK 015 decisions

| Decision                                              | Why                                                        |
|-------------------------------------------------------|-------------------------------------------------------------|
| Layered monolith (F1 → F2 → F3, one-way)              | Matches existing call graph; no concurrency; pure stdlib    |
| Package layout (`wiki_ingest/`)                        | Enables `commands/` namespacing; standard Python idiom      |
| ≤200 LoC argparse shim                                 | Forces every command to live in its own module               |
| Two-symbol `(register, execute)` per command           | Trivially unit-testable; one update site in the shim        |
| No command imports another command                     | Keeps the dependency DAG strictly hierarchical              |
| Tests as `unittest` (no pytest)                        | Zero runtime deps; portable; matches CLAUDE.md §1 testing   |
| Stub-First atomic merges (12 steps)                    | Each step gated by `diff -q` silent + tests; revertable     |
| `_*` prefix on internal modules                        | Signals "not a public API" to future maintainers            |
| No new SKILL.md changes                                | Refactor is invisible to the agent's contract               |
| References per-skill (`references/architecture.md`)    | Standard wiki-ingest doc location; not in repo root         |

### TASK 016 decisions

| Decision                                              | Why                                                                                  |
|-------------------------------------------------------|--------------------------------------------------------------------------------------|
| New `_page_merge.py` F2 module (M-2)                  | Only way to share additive-merge primitives between `upsert_page` and `promote` without violating the import-graph invariant (`test_architecture.py`) |
| Split R1 into `find_vault_root` + `discover_courses` (M-3) | Two complementary callers with different inputs: course-path-in (ingest-time) vs vault-root-in (promote/demote/lint). Removes the Q-8 "Lessons/" hardcoding ambiguity. |
| `init --root` flag, not `init-root` subcommand (Q-1)  | Smaller CLI surface; `init` already discovers existing files; one flag cheaper than a parallel subcommand |
| `reindex` mode-detection via `schema_version` peek (M-4) | No new flag needed; the schema file already encodes the intent; consistent with R9's schema-version guards elsewhere |
| `upsert-page` keeps positional `vault` arg; calls `find_vault_root` internally (M-1) | Preserves CLI byte-identity on single-course vaults; root-aware behaviour kicks in only when root schema is present |
| Byte-identity caveat scoped to "no root schema present" (M-1) | R11 TASK 015 fixtures test single-course only; the two-tier fixture tests a different code path — no contradiction |
| Dry-run default for `promote`, NOT for `demote` (Q-2 / Q-2b) | `promote` deletes files (destructive, hard to reverse in place); `demote` moves one file (easily re-promoted) |
| `description:` merge picks longer value (Q-6)         | Preserves more context; operator always has final authority |
| Contradiction detection = literal-line-diff (Q-10)    | Matches v1 contradiction logic; predicate-extraction is out of scope (R13.1 semantic-identity prohibition) |
| No root-level `log.md` (Q-4 / R13.2)                  | Per-course logs are sufficient for v2; root audit log deferred |
| `discover_courses` walks ALL descendants, not just `Lessons/` (Q-8) | Handles arbitrary vault layouts; operator's `trade-agents/Lessons/` convention is the default but not the only one |
| Lint `invariant_violation` is a hard failure (non-zero exit) | The one-page-one-place invariant is load-bearing for Obsidian link resolution; silent violation is worse than aborting |
| R3.7 re-promote folded into `promote` (not a new command) | Spec §3.3 explicitly recommends this; avoids a `merge-into-root` command with nearly identical logic |

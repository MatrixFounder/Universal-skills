# TASK 015 — wiki-ingest: modular refactor of `wiki_ops.py`

> **Mode:** VDD (Verification-Driven Development).
> **Status:** DRAFT v1 (2026-05-25).
> **Predecessors (context, not dependencies):**
> - `ea16990` — initial wiki-ingest skill.
> - `c6470a5` — folder-ingest mode (Phase 0).
> - `232698c`, `e0c2a6f` — two VDD passes (round-trip + injection bugs).
> - Most recent VDD-multi pass (this session) — 3 Critical + 11 High + 15
>   Medium + ~10 Low findings closed; `wiki_ops.py` now at **2661 LoC**.

---

## 0. Meta Information

- **Task ID:** `015`
- **Slug:** `wiki-ingest-modular-refactor`
- **Target skill:** `skills/wiki-ingest/` (Apache-2.0 — see root [`LICENSE`](../LICENSE)).
- **Backlog row:** none (operator-initiated maintenance, not a backlog item).
- **Cross-skill replication:** **None.** wiki-ingest does NOT share files with
  the four office skills (`docx`/`xlsx`/`pptx`/`pdf`) — the
  [CLAUDE.md §2](../CLAUDE.md#2-office-skills-modification-protocol--strict)
  replication protocol is **not triggered**. The cross-skill `diff -q` matrix
  MUST stay silent after this task lands (R9).
- **Mode flag:** Standard VDD (no `[LIGHT]`).
- **New dependency:** **None.** Pure stdlib refactor; no `requirements.txt`
  exists or will be added.
- **Reference docs:**
  - [`skills/wiki-ingest/SKILL.md`](../skills/wiki-ingest/SKILL.md) — current
    behavioural contract (363 lines). Stays byte-identical from a CLI
    perspective; internals change only.
  - [`skills/wiki-ingest/references/`](../skills/wiki-ingest/references/) —
    four workflow docs (ingest, query, lint, folder-ingest). No changes.
  - [`docs/SKILL_EXECUTION_POLICY.md`](SKILL_EXECUTION_POLICY.md) —
    script-first policy; the refactor preserves the `wiki_ops.py` CLI as
    the sole agent-facing entry point.

---

## 1. Problem Description

`skills/wiki-ingest/scripts/wiki_ops.py` has grown to **2661 lines** through
six months of feature additions (folder-ingest, register-summary, reindex,
classify-folder) and three VDD hardening passes. Concrete pain:

1. **Single-file friction**: every change requires scrolling/searching a 2.6k
   LoC module. Helpers (regex masking, frontmatter parser) are interleaved
   with command handlers and `argparse` glue.
2. **No test surface**: there is no `tests/` directory yet (`ls
   skills/wiki-ingest/scripts/` returns only `wiki_ops.py`). The next set of
   features cannot be defended without per-component unit tests, and
   today's monolith makes module-targeted tests awkward.
3. **Hidden coupling**: e.g., `_mask_code_fences` is used by both
   markdown-section helpers and wiki-link extraction; today both live in the
   same file but the dependency is invisible. Moving to modules makes the
   import graph explicit and refactor-safe.
4. **Future critic-loop economics**: the last `/vdd-multi` pass sent the full
   2.6k LoC file to three critic agents in parallel. A modular split lets
   future critic loops scope per-module (~200–400 LoC per file), reducing
   review token-cost by ~3× and improving signal-to-noise.

**Non-goal**: this task changes **no externally observable behaviour** of
the wiki-ingest CLI. SKILL.md remains byte-identical; every `wiki_ops.py
<subcommand>` invocation produces the same JSON / file-system effect.

---

## 2. Requirements Traceability Matrix (RTM)

| ID    | Requirement                                                                                                                            | MVP? | Sub-features |
|-------|----------------------------------------------------------------------------------------------------------------------------------------|------|--------------|
| R1    | Split `wiki_ops.py` into a `wiki_ingest/` Python package alongside it; `wiki_ops.py` becomes a ≤200-LoC shim with only argparse + dispatch. | Y    | R1.1 Package layout. R1.2 Shim signature unchanged. R1.3 No new entry points. |
| R2    | Extract a `wiki_ingest/_safety.py` module: `die`, `slugify`, `_safe_name`, `_safe_inline`, `_is_relative_to`, atomic I/O (`read_text`, `write_text`, `_atomic_write_text`), `_safe_for_json`, `_skip_symlink`, `_check_case_collision`, plus size-limit constants. | Y    | R2.1 Public re-export. R2.2 NFKC + slug-collision logic kept. R2.3 `fcntl.flock` POSIX-only guarded. |
| R3    | Extract a `wiki_ingest/_markdown.py` module: code-fence + inline-construct masking, `find_section` / `find_all_sections` / `get_section_body` / `replace_section_body` / `insert_section_before`, `_existing_lines`, `WIKILINK_*` regexes, `_extract_wikilinks_with_anchors`, `_first_sentence`. | Y    | R3.1 Mask-once invariant preserved. R3.2 `SECTION_BOUNDARY_RE` excludes `---`. R3.3 Anchor-aware wikilink helper exported. |
| R4    | Extract a `wiki_ingest/_frontmatter.py` module: `split_frontmatter` (with malformed-line warnings), `_strip_frontmatter_fast`, `_parse_flow_list`, `_strip_quotes`, `_strip_trailing_comment`, `_serialize_yaml_list_field`, `_splice_frontmatter_fields`, `_FM_*` regexes. | Y    | R4.1 Module-level regex cache (P-H5). R4.2 Structural splice exported. R4.3 Line-anchored close-delimiter logic preserved. |
| R5    | Extract a `wiki_ingest/_vault.py` module: vault layout constants (`DEFAULT_SUBDIRS`, `SUBDIR_TO_KIND`, `SUBDIR_TO_DISPLAY`, `SCHEMA_FILE`, `INDEX_FILE`, `LOG_FILE`), `_walk_pages` (symlink-skipping), `load_vault_pages`, `ensure_schema`, `load_asset`, `tail_log`. | Y    | R5.1 Symlink discipline kept. R5.2 Constants are single-source-of-truth. R5.3 `ASSETS_DIR` resolution still works under symlinks. |
| R6    | Extract a `wiki_ingest/_classify.py` module: folder-classification helpers (`_count_md_structure`, `_filename_hint_score`, `_looks_like_wiki_summary`, `_classify_one_file`, `_detect_grouping`, `_group_files`, `_pick_primary`, `_OFFICE_EXTS`/`_IMAGE_EXTS`/etc. const-tables, `_UNGROUPED_SENTINEL`). | Y    | R6.1 Binary-masquerade defense kept (L-M8). R6.2 Hint score behaviour unchanged. R6.3 `_UNGROUPED_SENTINEL` remains a process-unique object. |
| R7    | Convert each subcommand into a module under `wiki_ingest/commands/`: `scan`, `init`, `upsert_page`, `update_index`, `append_log`, `register_summary`, `log_event`, `find`, `lint`, `reindex`, `classify_folder`. Each module exports a single `register(subparser)` function and an `execute(args)` function. | Y    | R7.1 Per-command file ≤400 LoC. R7.2 Imports only from `_safety`, `_markdown`, `_frontmatter`, `_vault`, `_classify`. R7.3 No command imports another command. R7.4 `tests/test_architecture.py` enforces R7.2 + R7.3 via stdlib `ast`. |
| R8    | Add `skills/wiki-ingest/scripts/tests/` with unit tests for the new modules. Tests run via the per-skill venv pattern (per [CLAUDE.md §1.Testing](../CLAUDE.md#testing)). | Y    | R8.1 ≥3 unit tests per extracted module (`_safety`, `_markdown`, `_frontmatter`, `_vault`, `_classify`). R8.2 E2E smoke (`init` → `upsert-page` → `lint` → `reindex`) survives the refactor with byte-identical JSON output. R8.3 Adversarial smokes (symlink, traversal, ReDoS-grade 10k-header source, slug-collision, prompt-injection scalar) re-pass. |
| R9    | Cross-skill replication: confirm wiki-ingest does NOT touch the office-skills replicated set. CI / manual check: `diff -qr` between docx ↔ wiki-ingest must NOT exist (no shared files at all). | Y    | R9.1 No file under `skills/wiki-ingest/scripts/` matches any file path replicated across docx/xlsx/pptx/pdf. R9.2 Verified via the existing matrix shown in CLAUDE.md §2. |
| R10   | Validation: `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/wiki-ingest` exits 0 (Gold Standard). `python3 .claude/skills/skill-validator/scripts/validate.py skills/wiki-ingest` reports risk `SAFE` (0 Critical, 0 Errors). | Y    | R10.1 Validator pass before merge. R10.2 No new long-line warnings introduced. |
| R11   | Behavioural parity: regenerate the eval suite output before/after the refactor and confirm byte-identical JSON on at least the three eval scenarios with deterministic output (`scan` on a fixture vault, `lint` on a fixture vault, `classify-folder` on the trading-bot fixture folder). | Y    | R11.1 Fixture vaults committed under `tests/fixtures/` or reused from `evals/fixtures/`. R11.2 Pre/post stdout `diff -q` is silent. |
| R12   | Documentation: update SKILL.md only if a public surface changed (it must not — but state explicitly in the merge PR). Add a `references/architecture.md` page describing the new module layout for future maintainers. | N    | R12.1 Architecture reference written. R12.2 No SKILL.md change unless a public-surface drift is discovered during execution (in which case TASK.md is amended before merge). |

---

## 3. Use Cases

### UC-1 — Maintainer adds a new subcommand (`wiki_ops.py prune-empty`)

**Actor**: contributor adding a new wiki-maintenance subcommand.

**Pre-conditions**: refactor (R1–R7) merged.

**Main scenario**:
1. Create `skills/wiki-ingest/scripts/wiki_ingest/commands/prune_empty.py`.
2. Implement two functions: `register(subparser)` and `execute(args)`.
3. Add `from wiki_ingest.commands import prune_empty` + `prune_empty.register(sub)` to `wiki_ops.py`.
4. No other file touched.

**Acceptance**: the new command appears in `wiki_ops.py --help`; the command's logic is unit-testable in isolation via `tests/commands/test_prune_empty.py` without instantiating an argparse namespace.

**Alternative scenario (UC-1-alt)**: contributor's new command needs a helper that doesn't fit any existing `_*` module. Decision rule: if ≥2 commands will share it, promote to a new `wiki_ingest/_<domain>.py`; if it's command-local, keep it in `wiki_ingest/commands/<cmd>.py`. The architecture reference (R12) documents this rule.

---

### UC-2 — VDD-multi critic loop on a single module

**Actor**: orchestrator running `/vdd-multi skills/wiki-ingest/scripts/wiki_ingest/_markdown.py`.

**Pre-conditions**: refactor merged.

**Main scenario**:
1. Operator points the critic at one module (≤500 LoC).
2. Three critics (logic / security / performance) receive the file plus its
   ≤3 direct dependencies (`_safety` for `die`).
3. Critic-loop completes in ~⅓ of the time / tokens of the pre-refactor run.

**Acceptance**: the merged report has ≤1 cross-module finding per critic (because each module is internally cohesive).

**Alternative scenario (UC-2-alt)**: the critic flags a finding that genuinely spans modules (e.g., an invariant about the masked view shared between `_markdown` and `cmd_lint`). Such findings are first-class outputs of the critic loop and the orchestrator escalates them to a cross-module ticket; this is acceptable and expected for ≤1 finding per critic — not a failure mode.

---

### UC-3 — Smoke-test the refactor end-to-end

**Actor**: developer or CI.

**Pre-conditions**: refactor branch checked out.

**Main scenario**:
1. `cd skills/wiki-ingest/scripts && python3 -m venv .venv && source .venv/bin/activate`.
2. `python -m unittest discover -s tests` — all unit + smoke tests pass.
3. `python3 wiki_ops.py init /tmp/vault && python3 wiki_ops.py scan /tmp/vault | diff -q - /tmp/expected-scan.json` — no drift.
4. `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/wiki-ingest` exits 0.

**Acceptance**: all four steps succeed without manual intervention.

**Alternative scenario (UC-3-alt)**: step 3's `diff -q` surfaces a JSON drift. Recovery: developer reverts the most recent module-extraction commit (the Stub-First refactor commits one module at a time, so the regression window is localised), bisects within the reverted hunk, and re-merges with the determinism fix. R11 is the binary gate; failing it stops the pipeline rather than papering over the drift.

---

## 4. Acceptance Criteria (Definition of Done)

- All 11 MVP RTM requirements (R1–R11) satisfied; R12 satisfied if its trigger
  fires.
- **No public-surface drift**: every CLI subcommand emits byte-identical
  stdout/JSON for the three deterministic eval scenarios (`scan`, `lint`,
  `classify-folder` on fixture data). Verified by `diff -q` (R11.2).
- **Module size budget**: every `wiki_ingest/*.py` file ≤500 LoC (commands
  ≤400 LoC). `wiki_ops.py` ≤200 LoC.
- **Test coverage**: ≥3 unit tests per extracted core module; per-command
  smoke tests cover happy path + at least one adversarial input each.
- **Validator pass**: `validate_skill.py` exits 0; `skill-validator/validate.py`
  reports `SAFE` with 0 Critical / 0 Errors.
- **No new dependency**: pure stdlib; no `requirements.txt` introduced.
- **Cross-skill replication silent**: `diff -qr` between `skills/wiki-ingest/`
  and the office-skill replicated set has no overlap (R9).
- **Docs**: `references/architecture.md` describes the module graph + import
  rules; future-maintainer-readable in <5 min.

---

## 5. Open Questions

> Convert each to a decision before development starts. Blocking questions
> are flagged with **[BLOCKING]**.

1. **[BLOCKING]** **Package shape**: should the new code live as a Python
   *package* (`scripts/wiki_ingest/__init__.py` + submodules) or as a flat
   set of sibling files (`scripts/_safety.py`, `scripts/_markdown.py`, …)?
   - Recommendation: **package** (cleaner namespacing, supports
     `from wiki_ingest.commands import lint`, future-proof for adding e.g.
     a `wiki_ingest.cli` sub-package).
   - Counter: a flat layout is two fewer levels of indirection and is what
     other Universal-Skills scripts use (e.g., `office/` flat under
     `docx/scripts/`). However those are not commands but helpers.
   - **Decision needed before R1 starts.**

2. **Should `--inbox-root` and `WIKI_INGEST_INBOX_ROOT` graduate from
   `register-summary` to a global flag** (i.e. promoted to `wiki_ops.py
   --inbox-root` once and inherited by all read-from-disk subcommands)?
   - Out of scope by default — would touch SKILL.md (public surface). Defer
     to a follow-up task unless the maintainer wants it bundled. Recommended:
     **defer**.

3. **`evals/` fixtures vs new `tests/fixtures/`** — should R11 reuse the
   existing `evals/fixtures/` or copy small deterministic fixtures into
   `tests/fixtures/`?
   - Recommendation: **reuse** `evals/fixtures/` for the eval-aligned
     scenarios; add minimal additional fixtures in `tests/fixtures/` only
     for module-targeted unit tests (e.g., a 3-line malformed-YAML file
     that does not belong in the eval suite).

4. **Naming convention for "private" modules** — leading underscore
   (`_safety.py`, `_markdown.py`) marks the module as not-yet-public; a
   future task could promote any of them to a stable name. Alternative: no
   underscore (clearer imports, but loses the "internal" signal). Recommend
   underscore-prefixed names (matches the existing internal-helper
   convention in `wiki_ops.py`).

5. **Sentinel for command discovery** — should `wiki_ops.py` iterate
   `wiki_ingest.commands.__all__` or hard-code the command list? Hard-code
   is simpler; auto-discovery is one fewer place to update when adding a
   command. Recommend: **hard-code** in v1 (matches Karpathy "boring code"
   ethos), auto-discover only if the command count exceeds ~15.

---

## 6. Out of Scope

- Behavioural changes to any subcommand (those are followups).
- The 12 deferred Medium / Low findings from the prior VDD-multi report
  (`L-H2`, `L-L2/L3/L8/L9`, `S-L2/L3`, `P-L1/L2/L5`, `P-M3/M5`) — catalogued
  in [`docs/KNOWN_ISSUES.md`](KNOWN_ISSUES.md#wiki-ingest--deferred-cosmetic-findings-post-vdd-multi-2026-05-25)
  (added 2026-05-25 in lockstep with this task); addressed in a follow-up
  cosmetic-cleanup task once the modular refactor lands.
- SKILL.md rewrite — out of scope unless R12.2 triggers.
- Adding a `requirements.txt` — wiki-ingest stays pure-stdlib.

---

## 7. Definition of Done — checklist

- [ ] R1–R11 satisfied; R12 satisfied or formally deferred.
- [ ] `wiki_ops.py` is ≤200 LoC and contains only argparse wiring + a `main()`
      function that dispatches to `wiki_ingest.commands.*.execute`.
- [ ] Every `wiki_ingest/` file is ≤500 LoC; every command ≤400 LoC.
- [ ] `python -m unittest discover -s tests` exits 0.
- [ ] Pre/post `wiki_ops.py scan` / `lint` / `classify-folder` JSON diffs
      are silent on at least three deterministic fixtures.
- [ ] `validate_skill.py skills/wiki-ingest` exits 0.
- [ ] `skill-validator/validate.py skills/wiki-ingest` reports SAFE.
- [ ] `references/architecture.md` exists and describes the module graph.
- [ ] Cross-skill `diff -qr` matrix from CLAUDE.md §2 is silent.
- [ ] Merge commit message references this Task ID (`015`) and the predecessor
      commit hashes from the §0 Meta block.

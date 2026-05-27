# TASK 017 — wiki-ingest: v1.1 contract alignment (orchestrator `ingest` + manifest + `vault_id`)

> **Mode:** VDD (Verification-Driven Development).
> **Status:** DRAFT v1 (2026-05-27).
> **Source spec:** [`obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md`](../../obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md)
> — external contract written by the **index-layer** consumer
> (`obsidian-llm-wiki`) that wraps this skill via the `/wiki-enrich` bridge.
> Where this TASK and that contract disagree, **the contract wins** (it is
> the integration boundary); any divergence MUST be recorded back in
> §5 Open Questions and reconciled with the consumer before merge.
> **Predecessors (context, not dependencies):**
> - [`5faae95`] — TASK 016 final commit (two-tier vault + promote/demote).
> - [`docs/tasks/task-016-wiki-ingest-cross-course-promotion.md`] — last
>   archived master TASK.
> - The two-tier vault model + `promote`/`demote` from TASK 016 are the
>   substrate this task extends. No regression to that surface allowed.

---

## 0. Meta Information

- **Task ID:** `017`
- **Slug:** `wiki-ingest-v1.1-contract-alignment`
- **Target skill:** [`skills/wiki-ingest/`](../skills/wiki-ingest/) (Apache-2.0
  — root [`LICENSE`](../LICENSE)).
- **Backlog row:** none (alignment task driven by external consumer).
- **Cross-skill replication:** **Not triggered.** Same constraint as TASK 016.
- **Mode flag:** Standard VDD (no `[LIGHT]`).
- **New runtime dependency:** **None.** Pure stdlib (`pathlib`, `re`,
  `argparse`, `subprocess`, `os`, `json`) — same constraint as TASK 015/016.
- **Reference docs:**
  - [`obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md`](../../obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md)
    — **the contract** this task implements (sections referenced inline as
    `CONTRACT §N`).
  - [`obsidian-llm-wiki/docs/adr/ADR-001-wiki-ingest-integration.md`](../../obsidian-llm-wiki/docs/adr/ADR-001-wiki-ingest-integration.md)
    — Option I architecture (wiki-ingest owns file layer, indexer wraps).
  - [`obsidian-llm-wiki/docs/adr/ADR-002-multi-vault-bottleneck-corrections.md`](../../obsidian-llm-wiki/docs/adr/ADR-002-multi-vault-bottleneck-corrections.md)
    — multi-vault partitioning + `vault_id` REQUIRED in `WIKI_SCHEMA.md`
    (no hash fallback).
  - [`skills/wiki-ingest/SKILL.md`](../skills/wiki-ingest/SKILL.md) — current
    public contract; gains the top-level `ingest` orchestrator subcommand
    + manifest schema + `vault_id` requirement.
  - [`skills/wiki-ingest/references/wiki_schema.md`](../skills/wiki-ingest/references/wiki_schema.md)
    — extended (not replaced) to describe the `vault_id` frontmatter field.
  - [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — TASK 015/016 §3.2 module table;
    extended in place (new modules: `commands/ingest.py`; extended:
    `commands/init.py`, `_vault.py`).
  - [`docs/tasks/task-016-wiki-ingest-cross-course-promotion.md`](tasks/task-016-wiki-ingest-cross-course-promotion.md)
    — direct predecessor; defines the two-tier vault model this task
    integrates with via the manifest's `course` + `scope` fields.

---

## 1. Problem Description

### Context

`obsidian-llm-wiki` is a separate Python project (the **index layer**) that
indexes wiki-ingest's markdown output into a per-vault SQLite + FTS5 cache.
Per ADR-001 ("Option I — wrap + index"), it does not duplicate file-synthesis
logic; instead it invokes `wiki-ingest` as a subprocess and indexes whatever
the manifest reports as written.

The integration is realised through the `/wiki-enrich` bridge skill in that
project. End-to-end flow:

```
operator        /wiki-enrich --vault <vid> --source <file>
   │
   ▼
wiki-enrich   ─►  subprocess: wiki-ingest --version    (≥ 1.1 fail-fast)
   │
   ▼
wiki-enrich   ─►  subprocess: wiki-ingest ingest --source <file>
                                          --vault <vault_root>
                                          --output-format json
                                          [--known-concepts-stdin <json>]
   │
   ▼
manifest JSON {status, vault_id, vault_root, course, source, written[],
               created[], touched[], contradictions, log_event, ...}
   │
   ▼
wiki-enrich   ─►  for each written[].path: index into SQLite via
                  `wiki-index-upsert`; mirror log_event into log_events.
```

### The gap

The contract was written in obsidian-llm-wiki on 2026-05-26 and updated on
2026-05-27 against the assumption that wiki-ingest would expose:

1. A `wiki-ingest` binary on `PATH` (or equivalent invocation).
2. A `--version` flag returning `1.1.0+`.
3. A top-level `ingest` orchestrator subcommand that wraps the atomic ops
   (currently exposed as `register-summary`, `upsert-page`, `update-index`,
   `append-log`) into one call and emits a stable JSON manifest.
4. `vault_id` as a REQUIRED field in root `WIKI_SCHEMA.md` frontmatter
   (ADR-002 §D1.1 — no hash fallback, fail-fast).
5. Exit codes 6/7/8 for vault_id errors.
6. Several pass-through flags: `--known-concepts-stdin/file`,
   `--source-hash <hex>`, `--config <path>`, `--timeout-seconds <N>`,
   `--quiet` / quiet-when-stdout-piped, `--output-format {human,json}`.
7. Atomic-manifest emission: full success → exit 0 + complete manifest;
   partial success → exit 20 + recovery info; failure → exit ≥ 21 + no
   manifest.

The smoke check on 2026-05-27 (running `/wiki-enrich` against this skill at
`v1.0`) confirmed the bridge fails fast and gracefully with envelope
`{"error":"WIKI_INGEST_FAILED", "message":"wiki-ingest not found on PATH;
install wiki-ingest v1.1+"}`.

**No regression is required.** The atomic operations remain the building
blocks; the new `ingest` orchestrator is layered on top.

### Why now

- `/wiki-enrich` cannot run end-to-end until this lands. The index layer
  is feature-complete but blocked.
- All atomic operations already exist (TASK 015 refactor + TASK 016
  promote/demote). The orchestrator is composition + manifest collection,
  not new core logic.
- The `vault_id` requirement also unblocks proper multi-vault FTS partition
  (R-27/R-28/R-29 from the index-layer side) — already shipped there.

### Target shape (v1.1)

```bash
# 1. CLI binary on PATH (renamed wiki_ops or a wrapper script):
$ wiki-ingest --version
wiki-ingest 1.1.0

# 2. Atomic ops unchanged (backward-compatible):
$ wiki-ingest register-summary --summary-path summary.md vault   # existing
$ wiki-ingest upsert-page --kind concept --slug ...              # existing
$ wiki-ingest promote "Sharpe Score" --vault ~/obsidian/...      # from TASK 016

# 3. New orchestrator subcommand:
$ wiki-ingest ingest --source ./raw/transcript.md \
                     --vault ~/obsidian/my-vault \
                     --output-format json \
                     --known-concepts-stdin '...' \
                     --source-hash deadbeef \
                     --timeout-seconds 600

→ JSON manifest on stdout per CONTRACT §1, exit 0 on full success.
```

---

## 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R1** | **CLI binary `wiki-ingest` on PATH.** The skill MUST be invokable as `wiki-ingest <subcommand>` (with hyphen). Today it is `python3 scripts/wiki_ops.py <subcommand>`. | Y | R1.1 Ship a thin shell wrapper `skills/wiki-ingest/scripts/wiki-ingest` (no `.sh` suffix) that `exec`s `python3 "$(dirname $0)/wiki_ops.py" "$@"`; chmod +x. R1.2 Document installation pattern in SKILL.md: symlink `~/.local/bin/wiki-ingest → <skill>/scripts/wiki-ingest`. R1.3 No breaking change: `python3 wiki_ops.py …` continues to work. R1.4 The wrapper resolves its own path via `readlink -f` (cross-shell, symlink-safe). |
| **R2** | **`--version` top-level flag.** `wiki-ingest --version` (no subcommand) prints `wiki-ingest <major>.<minor>.<patch>` to stdout, exits 0. | Y | R2.1 Single version constant in `wiki_ingest/__init__.py::__version__` = `"1.1.0"`. R2.2 `build_parser()` adds `--version` via `argparse.ArgumentParser(add_help=True)` + `action="version"`. R2.3 Output is exactly `wiki-ingest 1.1.0` (CONTRACT §7 — minimum-version check by string-prefix). R2.4 Unit test asserts version format AND minimum is `>=1.1`. |
| **R3** | **`vault_id` field in root `WIKI_SCHEMA.md` — emit, don't enforce.** wiki-ingest READS the field if present and emits it in the manifest; it does NOT require the field for its own operation. Enforcement lives in the consumer (e.g., `obsidian-llm-wiki/wiki-init` already does this on its side). Pattern when present: `^[a-z][a-z0-9-]{1,30}[a-z0-9]$` (length 3–32, lowercase, kebab-case, no `--`). Standalone wiki-ingest users (no DB consumer) see no new constraint — v1.0 behaviour preserved. (ADR-002 §D1.1 — note clarified 2026-05-27.) | Y | R3.1 `commands/init.py --root --vault-id <slug>` writes `vault_id: <slug>` in the scaffold when the flag is given; without it, no `vault_id` is written (operator can add later by hand). R3.2 `_vault.py::find_vault_root` reads `vault_id` from root schema frontmatter if present; absence is NOT an error here. R3.3 Format validation: if `vault_id` is present AND violates the pattern → `die("INVALID_VAULT_ID", code=7)`. Reason: malformed slug would corrupt downstream consumers; absent is OK, malformed is not. R3.4 Optional `--vault-id <slug>` flag on `ingest` (and `promote`/`demote`/`lint`/`reindex`) is a **validator**: if given AND mismatches frontmatter → `die("VAULT_ID_FLAG_MISMATCH", code=8)`; if given AND frontmatter has no `vault_id` → `die("MISSING_VAULT_ID", code=6)` (caller demanded strict mode). Without the flag, no enforcement. R3.5 The manifest's `vault_id` field (R6.1) is `string` if found, otherwise JSON `null`. Consumers that require strict vault_id MUST check the manifest themselves. R3.6 Existing single-course AND two-tier vaults without `vault_id` continue to work — v1.0 behaviour preserved for non-strict callers. R3.7 Migration note (added to SKILL.md): users who want to integrate with the index layer (e.g., `obsidian-llm-wiki`) need to add `vault_id: <slug>` to root `WIKI_SCHEMA.md`; one-line edit. Not required otherwise. |
| **R4** | **Exit-code contract** for v1.1 (extends TASK 015/016 shipped codes 0..8 — see [`skills/wiki-ingest/references/exit_codes.md`](../skills/wiki-ingest/references/exit_codes.md) for the authoritative audit). | Y | R4.1 v1.1 NEW codes live in a dedicated **20..26 band** (audited 2026-05-27 after the initial draft 3..9 was found to collide with shipped TASK 015/016 die() sites): `20` = partial success (mid-pipeline failure; manifest reflects `written_so_far[]`); `21` = subprocess to `summarizing-meetings` (or analogous) failed (passthrough — DOES NOT include timeout, see code 26); `22` = LLM API unavailable / auth failed; `23` = MISSING_VAULT_ID; `24` = INVALID_VAULT_ID; `25` = VAULT_ID_FLAG_MISMATCH; `26` = TIMEOUT (`--timeout-seconds` overrun — split from 21 so callers can distinguish recoverable timeout retry from genuine downstream failure). Codes 27..29 reserved for additive v1.1.x extensions; 10..19 reserved for future per-command additions. R4.2 Shipped 0..8 unchanged (CONTRACT §3 lock; full table in `references/exit_codes.md` §2). R4.3 Documented in SKILL.md + per-subcommand `--help` + `references/exit_codes.md` (canonical). R4.4 `wiki_ingest/_safety.py` gains `EXIT_*` constants matching the 20..26 band; `die(msg, code=…)` accepts them. R4.5 Partial-success envelopes (codes 20, 21, 22, 26) all carry a `phase:"<phase-name>"` discriminator so callers can route on failure phase even when codes alias future failure modes. |
| **R5** | **Top-level `ingest` orchestrator subcommand.** New module `wiki_ingest/commands/ingest.py`. Wraps the atomic ops into a single call and collects a manifest. | Y | R5.1 Argparse contract (CONTRACT §1): `--source <abs-path>` (required), `--vault <abs-path>` (required), `--output-format {human,json}` (default human; manifest required when JSON), `--known-concepts-file <path>` / `--known-concepts-stdin` (mutually exclusive), `--source-hash <hex>`, `--config <path>`, `--timeout-seconds <N>` (default 600), `--quiet` (force-quiet when stdout is a TTY), `--vault-id <slug>` (validator). R5.2 Internal pipeline (deterministic order): (a) `find_vault_root` → resolve `vault_root` + `course_wiki_root` + `vault_id`; (b) source-hash idempotency check (CONTRACT §6); (c) delegate summary generation to `summarizing-meetings` via the existing subprocess pattern OR no-op if `--source` is already a `.md` summary (detect by frontmatter `type:` ∈ {summary, lesson-summary, …}); (d) write `_sources/<slug>.md` via `register-summary`; (e) extract concepts/entities → `upsert-page` for each new/touched page (root-aware per TASK 016 R8); (f) `update-index` for affected layer(s); (g) `append-log` (course) + `log-event` (structured row); (h) emit manifest. R5.3 **Atomicity strategy: per-step rollback with `exit 20` + partial manifest** (CONTRACT §3 option (a); Q-1 resolved 2026-05-27 — see §5 for rationale). NO tempdir/rename staging. Each atomic op (`register-summary`, `upsert-page`, `update-index`, `append-log`) commits independently; mid-pipeline failure leaves the chain partially applied and emits `{"status":"error", "phase":"<phase>", "written_so_far":[…], "cleanup_advice":"…"}` + exit 20. R5.4 Reserved — superseded by R5.3. R5.5 No new auto-promotion (preserves TASK 016 R8.5). |
| **R6** | **Manifest schema** (CONTRACT §1). Stable JSON emitted to stdout when `--output-format json` and only on success / partial-success. | Y | R6.1 Top-level fields: `status` ∈ {`"ok"`, `"error"`}, `vault_id` (string or `null` — see R3.5; consumers that require it MUST validate themselves), `vault_root` (abs path), `course` (str or `null`), `source` {`path`, `slug`, `hash`}, `written[]` (objects), `created[]` (paths), `touched[]` (paths), `contradictions` (int), `summary_path` (str), `log_event` (object — see R8), `llm_tokens_used` {`input`, `output`, `model`}. R6.2 `written[]` entry fields: `path` (vault-relative), `action` ∈ {`"created"`, `"updated"`, `"appended"`}, `kind` ∈ {`"source"`, `"concept"`, `"entity"`, `"index"`, `"log"`}, `scope` ∈ {`"course"`, `"vault"`} (per TASK 016 two-tier). R6.3 JSON schema is documented inline in CONTRACT §1 — copy verbatim into a new reference page [`skills/wiki-ingest/references/manifest_schema.md`](../skills/wiki-ingest/references/manifest_schema.md). R6.4 Atomic emission: manifest printed only after all writes succeed. On partial — exit 20 + `{"status":"error", "phase":"<phase>", "written_so_far":[…], "cleanup_advice":"…"}`. R6.5 Forward-compat: additive field changes allowed in 1.1.x; removals/renames are 1.2+ (CONTRACT §7 — frozen-CLI rule). |
| **R7** | **`--known-concepts-stdin` / `--known-concepts-file` injection** (CONTRACT §2). The index layer queries `SELECT slug, name, aliases FROM entities` and pipes the JSON in; wiki-ingest augments its `scan`-derived list and passes the union to summarizing-meetings to avoid dangling-link generation. | Y | R7.1 Stdin form: `--known-concepts-stdin` reads stdin until EOF; expected payload is a JSON array of `{slug, name, aliases[]}`. R7.2 File form: `--known-concepts-file <path>` reads same shape from disk (validate_inside_vault NOT required — operator-supplied path). R7.3 Mutually exclusive with stdin; argparse enforces. R7.4 Inside the skill: merge with `scan` output (right-side wins on slug collision — DB is authoritative); pass the merged list to whatever downstream prompt builder consumes "known concepts" (today: hardcoded into the summarizing-meetings invocation). R7.5 If neither flag is given → skill scans the vault as today (no behavioural change for non-piped callers). |
| **R8** | **Structured `log_event` in manifest + `log_events` mirror payload.** The manifest carries a structured `log_event` object that the index layer mirrors into its `log_events` SQL table (R-28 from the index side). | Y | R8.1 Fields: `event_ts` (ISO-8601 with TZ), `event_type` ∈ {`"ingest"`, `"reindex"`, `"lint"`, `"promote"`, `"demote"`} (matches index-layer CHECK enum), `subject` (str — typically the source title), `log_md_byte_offset` (int — position of the corresponding line in the course's `log.md`). R8.2 `log_md_byte_offset` is computed AFTER the `append-log` write completes; emit the offset returned by the underlying append (already supported by `commands/log_event.py`). R8.3 Index layer uses `log_md_byte_offset` to round-trip parse log.md back to log_events rows on reindex. R8.4 No new schema in wiki-ingest itself — the offset already exists. |
| **R9** | **`--source-hash <hex>` external idempotency override** (CONTRACT §6). | Y | R9.1 When `--source-hash` is given, wiki-ingest does NOT recompute the source file's sha256; uses the operator-supplied value instead. R9.2 Subsequent steps (footer hash in `_sources/<slug>.md`, log-event details_json) use the externally-supplied hash. R9.3 If wiki-ingest's internal idempotency tracker (`_sources/<slug>.md` footer) already has a matching hash → emit `{"status":"ok", "action":"unchanged", "manifest":<empty written[]>}` without re-running summarisation. Exit 0. R9.4 Mismatch → full ingest (additive-merge contract — CONTRACT §6.2). |
| **R10** | **Subprocess-friendly behaviour** (CONTRACT §8). | Y | R10.1 `os.isatty(1)` check: when stdout is piped, suppress decorative output (banners, progress bars). Emit only structured JSON or unstructured logs to stderr. R10.2 Explicit `--quiet` flag forces quiet regardless of TTY. R10.3 `--timeout-seconds <N>` (default 600) bounds total ingest; on overrun: kill internal LLM call cleanly, **exit 26** (`TIMEOUT` — split from the generic subprocess-failure code 21 per R4.1) + partial manifest (R6.4) carrying `phase:"timeout"`. R10.4 `WIKI_INGEST_TIMEOUT` env var fallback when flag absent. |
| **R11** | **`--config <path>` YAML override** (CONTRACT §5). | Y | R11.1 Accepts the same YAML subset as the index layer's `wiki:` block in CLAUDE.md (e.g., `wiki.transcript.model`, `wiki.transcript.timeout_seconds`). R11.2 Loaded values override built-in defaults; CLI flags override file values (precedence: CLI > config > defaults). R11.3 Schema validation: unknown keys → warning, not error (forward-compat). R11.4 `WIKI_INGEST_DRY_RUN=1` env var honoured (existing TASK 016 dry-run pattern). |
| **R12** | **Documentation.** Update SKILL.md + add reference page; update [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) in place. The reference page MUST mirror every CONTRACT § that this TASK depends on — so the skill is self-describing even if `obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md` is moved, renamed, or revised out of step. | Y | R12.1 SKILL.md §4 (Script Contract) gains an `ingest` row + a §"Top-level orchestrator" subsection. R12.2 SKILL.md migration section: how existing two-tier vaults add `vault_id` (one-line frontmatter edit). R12.3 NEW reference [`skills/wiki-ingest/references/manifest_schema.md`](../skills/wiki-ingest/references/manifest_schema.md) — MUST embed **verbatim** copies of every CONTRACT section that R1..R11 reference: **§1** (manifest schema + examples — R6), **§2** (`--known-concepts-*` payload shape — R7), **§3** (atomicity contract + exit-code table — R4, R5.3), **§5** (config YAML subset — R11), **§6** (source-hash idempotency rules — R9), **§7** (version freeze + minimum-version check — R2), **§8** (subprocess-friendly behaviour — R10). Each section copied as a sub-heading with a `> sourced from obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md §N (2026-05-27)` provenance line and the contract revision date. If the external contract moves, this file is the authoritative in-repo copy. R12.4 [`skills/wiki-ingest/references/wiki_schema.md`](../skills/wiki-ingest/references/wiki_schema.md) extended with §"vault_id field (v1.1)". R12.5 `docs/ARCHITECTURE.md` extended in place (NOT archived — living document). New §3.x entry for `commands/ingest.py`; existing §3.x rows for `_vault.py` etc. updated. R12.6 [`skills/wiki-ingest/scripts/wiki_ingest/.AGENTS.md`](../skills/wiki-ingest/scripts/wiki_ingest/.AGENTS.md) updated with the new module + version constant. |
| **R13** | **Tests.** Per-skill `unittest` venv discipline (no pytest, no runtime deps). | Y | R13.1 `tests/commands/test_ingest.py` — happy path (single-course vault), happy path (two-tier with course resolution), source-hash short-circuit, manifest schema validation, exit-code coverage (0/20/21/22/23/24/25/26), `--known-concepts-stdin` injection, `--quiet` mode, `--timeout-seconds` enforcement. R13.2 `tests/test__vault.py` — `vault_id` enforcement: missing (code 23), invalid pattern (code 24), flag mismatch (code 25). R13.3 `tests/test_cli_wrapper.py` — `bin/wiki-ingest --version` exits 0 with correct format; subcommand dispatch via wrapper is equivalent to direct `wiki_ops.py` call. R13.4 `tests/test_e2e_v1_1_contract.py` — end-to-end smoke that mimics the `/wiki-enrich` flow: subprocess-call `wiki-ingest ingest …`, parse manifest, assert all CONTRACT §1 fields present and well-typed. R13.5 Existing test suites (TASK 015/016) keep their semantics; new tests are additive. |
| **R14** | **Cross-skill replication & validators.** | Y | R14.1 No file added by this task matches any path replicated across docx/xlsx/pptx/pdf. R14.2 `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/wiki-ingest` exits 0. R14.3 `python3 .claude/skills/skill-validator/scripts/validate.py skills/wiki-ingest` reports risk `SAFE` (0 Critical / 0 Errors). R14.4 R9-style cross-skill `diff -q` matrix from TASK 015 §9 stays silent. R14.5 `tests/test_architecture.py` import-graph check passes — `commands/ingest.py` imports only from `_safety`, `_markdown`, `_frontmatter`, `_vault`, `_page_merge`, and may invoke OTHER `commands/*` via the dispatcher pattern (not direct import) — see Open Q-2. |
| **R15** | **Honest-scope guardrails** (out-of-scope, locked in §4). | Y | R15.1 No new LLM-call patterns beyond what `summarizing-meetings` already does. R15.2 No new vault-layout features (two-tier model from TASK 016 stays; no three-tier). R15.3 No automatic source-fetching (operator supplies the source path; no URL→content). R15.4 No new entity types beyond TASK 016's set (`concept`, `entity` — and the wiki-ingest internal types `person`, `company`, `product`, `group`, `external` mapped through the index layer's TYPE_MAPPING). R15.5 No webhook / file-watch / daemon mode. R15.6 No multi-source-in-one-call ingest (one source per `ingest` invocation; bulk is the operator's loop or a future Epic). |

---

## 3. Use Cases

### UC-1 — Index-layer bridge invokes `wiki-ingest ingest` end-to-end

**Actors**: operator, `obsidian-llm-wiki`'s `/wiki-enrich` skill (subprocess
caller), `wiki-ingest`'s `ingest` orchestrator, `summarizing-meetings`
(LLM-driven summariser), filesystem.

**Preconditions**:
- Two-tier vault under `~/obsidian/trade-agents/` with valid
  `vault_id: trade-agents` in the root `WIKI_SCHEMA.md`.
- `wiki-ingest` ≥ 1.1.0 on `PATH`.
- `summarizing-meetings` available (existing TASK 015/016 invariant).
- The index-layer SQLite DB is registered for this vault.

**Main scenario**:
1. Operator invokes `/wiki-enrich --vault trade-agents
   --vault-root ~/obsidian/trade-agents
   --source ~/raw/transcript-2026-05-27.txt`.
2. `wiki-enrich` runs `wiki-ingest --version` → `1.1.0`, OK.
3. `wiki-enrich` queries its SQLite for `entities` of vault `trade-agents`
   → JSON list, pipes via `--known-concepts-stdin`.
4. `wiki-enrich` runs `wiki-ingest ingest --source ~/raw/transcript-…
   --vault ~/obsidian/trade-agents --output-format json
   --known-concepts-stdin` with stdin = JSON list.
5. `wiki-ingest`:
   (a) `find_vault_root` resolves vault_id + course root.
   (b) Source-hash check — new source, no idempotency hit.
   (c) Delegates to `summarizing-meetings` → produces `summary.md`.
   (d) `register-summary` writes `_sources/<slug>.md`.
   (e) Extracts new concepts/entities → `upsert-page` (root-aware per TASK
       016 R8) for each. Touched root pages get vault-relative footnotes.
   (f) `update-index` for affected layer.
   (g) `append-log` (course log.md) + `log-event` (structured); offset
       captured.
   (h) Emits manifest JSON to stdout, exits 0.
6. `wiki-enrich` parses manifest, validates against CONTRACT §1.
7. `wiki-enrich` loops `manifest.written[]` → upserts each into SQLite via
   its own `wiki-index-upsert`.
8. `wiki-enrich` inserts `manifest.log_event` into `log_events` table.
9. `wiki-enrich` emits its own envelope: `{"action":"enriched","ingest":
   <manifest>, "index": {"upserted":[…], "log_event_id": N}}`, exit 0.

**Postconditions**:
- Vault: 10–15 markdown pages touched (Karpathy "compounding" guarantee).
- DB: corresponding rows + log_events entry.
- Re-running the same command — idempotent: source-hash hits → no LLM call,
  empty `written[]`, no new DB rows.

### UC-2 — Operator-direct ingest (no index layer)

**Actors**: operator, `wiki-ingest`, `summarizing-meetings`, filesystem.

**Preconditions**: Same as UC-1 minus index-layer DB.

**Main scenario**:
1. Operator runs `wiki-ingest ingest --source ~/raw/article.md
   --vault ~/obsidian/notes` (no `--output-format json`).
2. wiki-ingest runs the same internal pipeline as UC-1.5.
3. Stdout: human-readable summary of what was written (existing
   wiki-ingest behaviour for non-JSON output).
4. Exit 0.

**Postconditions**: Vault state changed; no DB component touched.

### UC-3 — Strict-mode `vault_id` enforcement (caller-demanded)

**Actors**: operator (or consumer like `/wiki-enrich`), `wiki-ingest`.

**Preconditions**:
- Root `WIKI_SCHEMA.md` lacks `vault_id`.
- Caller demands strict mode by passing `--vault-id <slug>` to `wiki-ingest
  ingest` (or another v1.1 subcommand). Without the flag, no enforcement
  happens and the call proceeds — manifest emits `vault_id: null`.

**Main scenario**:
1. Operator runs `wiki-ingest ingest --source <…> --vault <…>
   --vault-id trade-agents`.
2. wiki-ingest reads root schema; `vault_id` absent.
3. Emits `{"status":"error", "code":"MISSING_VAULT_ID",
   "wiki_schema_path":"…", "suggested_vault_id":"<kebab(basename)>"}`,
   exit 23.

**Alternative — flag mismatch (exit 25)**:
1. Frontmatter has `vault_id: foo`; caller passes `--vault-id bar`.
2. wiki-ingest emits `{"status":"error", "code":"VAULT_ID_FLAG_MISMATCH",
   "in_frontmatter":"foo", "from_flag":"bar"}`, exit 25.

**Alternative — invalid pattern (exit 24)**:
1. Frontmatter has `vault_id: 1bad` (digit-leading).
2. wiki-ingest emits `{"status":"error", "code":"INVALID_VAULT_ID",
   "received":"1bad", "pattern":"^[a-z]…"}`, exit 24.
3. This fires whether or not `--vault-id` was passed — a malformed slug
   would poison downstream consumers either way.

**Postconditions**: No writes; operator adds/fixes `vault_id` and re-runs.
A standalone wiki-ingest user who DOES NOT pass `--vault-id` never sees
exit 23 — they just get a manifest with `vault_id: null`.

### UC-4 — Source-hash short-circuit

**Actors**: operator (or `wiki-enrich` re-running after no real change).

**Preconditions**: Source previously ingested; its hash recorded in
`_sources/<slug>.md` footer.

**Main scenario**:
1. Caller passes `--source-hash <hex>` matching the recorded hash.
2. wiki-ingest matches → skips summarisation entirely.
3. Emits `{"status":"ok","action":"unchanged","manifest":{…written:[]}}`,
   exit 0.

**Postconditions**: No filesystem changes; no LLM tokens spent.

> **Planner-split note (PLAN.md §4 / §7)**: UC-5 below documents disk-
> failure recovery (exit 20). The /vdd-plan phase split timeout recovery
> (R10.3 → exit 26 + `phase:"timeout"`) into a sibling "UC-6 (timeout
> overrun)" for testability — see `docs/PLAN.md` §4 use-case coverage
> table. The split is editorial (RTM unchanged, both behaviours covered
> by the same orchestrator beads 017-02 + 017-07).

### UC-5 — Partial-success recovery (`exit 20`)

**Actors**: operator, `wiki-ingest`.

**Preconditions**: Mid-ingest a write fails (disk full, permissions, etc.).

**Main scenario**:
1. wiki-ingest is partway through step (e) `upsert-page` calls.
2. The 4th of 6 page upserts fails (`OSError: No space left`).
3. wiki-ingest aborts further writes (does NOT roll back what's already
   succeeded — pages 1–3 stay; the failed page leaves no partial file).
4. Emits manifest with `status:"error"`, `phase:"upsert-page"`,
   `written_so_far:[…3 entries…]`, `cleanup_advice:"…"`, exit 20.
5. Caller (`wiki-enrich`) sees exit 20 + manifest → returns
   `{"action":"partial","error":"PARTIAL_INDEX_FAILURE","ingest":<manifest>}`
   to operator without indexing anything (so DB doesn't get half-state).

**Postconditions**: Operator has a clean diff to inspect and decide:
re-run after fixing disk, or `wiki-ingest lint --fix` to clean up.

---

## 4. Acceptance Criteria (binary, machine-checkable)

1. `which wiki-ingest` returns a path (R1).
2. `wiki-ingest --version` prints exactly `wiki-ingest 1.1.0` and exits 0
   (R2).
3. `wiki-ingest ingest --source <real-md> --vault <real-vault>
   --output-format json` produces a manifest whose top-level keys match
   CONTRACT §1 exactly (R5 + R6).
4. The same call run twice with `--source-hash <unchanged>` produces
   `{"status":"ok","action":"unchanged"}` on the second run (R9).
5. Strict-mode vault_id checks (R3 + R4):
   - Vault without `vault_id` in root schema + caller passes
     `--vault-id <slug>` → exit 23 (`MISSING_VAULT_ID`).
   - Frontmatter has `vault_id: foo` + caller passes `--vault-id bar`
     → exit 25 (`VAULT_ID_FLAG_MISMATCH`).
   - Frontmatter has malformed `vault_id: 1bad` (any caller) → exit 24
     (`INVALID_VAULT_ID`).
   - Vault without `vault_id` + caller does NOT pass `--vault-id` → exit 0,
     manifest has `vault_id: null` (standalone user, v1.0 behaviour
     preserved).
6. End-to-end smoke from `obsidian-llm-wiki`:
   `bash -c 'cd /tmp && /Users/sergey/.local/bin/wiki-enrich
   --vault trade-agents --vault-root ~/obsidian/trade-agents
   --source <real-source>'` succeeds with exit 0 and a non-empty
   `index.upserted[]` array (R5 + R6 + R8 + UC-1).
7. `python3 .claude/skills/skill-creator/scripts/validate_skill.py
   skills/wiki-ingest` exits 0 (R14.2).
8. `python3 .claude/skills/skill-validator/scripts/validate.py
   skills/wiki-ingest` reports `SAFE` (R14.3).
9. All TASK 015/016 tests continue to pass (no regression).

---

## 5. Open Questions

- **Q-1 — Atomicity strategy for `ingest`. RESOLVED 2026-05-27 → option (a)
  per-step rollback with `exit 20` + partial manifest** (R5.3 updated to
  reflect). Rationale: option (c) (stage-to-tempdir → rename-on-success)
  cannot cross filesystem boundaries, and the vault writes touch multiple
  directories (`_sources/`, `_concepts/`, `_entities/`, `index.md`,
  `log.md`) any of which may be a separate FS (network mount, encrypted
  overlay). Option (a) also matches CONTRACT §3's documented preference
  and keeps the manifest's `written_so_far[]` field load-bearing —
  callers (`/wiki-enrich` in particular) already gate DB-side indexing
  on exit 20 + partial manifest. R5.4 reserved (no longer in scope).
- **Q-2 — `commands/ingest.py` invocation of other `commands/*`.** The
  TASK 015 architecture-import-graph invariant forbids `commands/*`
  modules from importing each other. Options: (a) refactor each
  composing command to expose a `lib/*.py` callable; (b) use subprocess
  recursion (call `wiki-ingest <sub>` from inside ingest.py); (c) define
  a dispatch helper in `_vault.py` or a new `_dispatch.py`. **Recommendation**:
  (c) — minimal change, keeps the import-graph clean. Confirm in /vdd-plan.
- **Q-3 — `--source-hash` against a `.md` summary input.** If the source
  is already a pre-made summary (not a transcript), what's the hash
  semantic? File-bytes-hash makes sense. Confirm with CONTRACT §6 once.
- **Q-4 — `summary-light` type mapping.** The index-layer TYPE_MAPPING
  (in `obsidian-llm-wiki/scripts/wiki_index/normalization.py`) accepts
  `summary-light` as a `pages.type='summary'` + tag. Does wiki-ingest's
  `ingest` orchestrator emit anything with `type: summary-light`? If
  not, drop from manifest contract or document as no-op.
- **Q-5 — `course` field when single-course vault.** Manifest's `course`
  is described as nullable (CONTRACT §1). Confirm: single-course vault
  (no two-tier root) → `course: null` AND `written[].scope: "course"`?
  Or `scope: "vault"`? The index layer must round-trip both — verify
  with /wiki-enrich's `_validate_manifest`.

---

## 6. Out of Scope (locked)

R15.1–R15.6 above (no new LLM patterns, no three-tier vault, no automatic
fetching, no new entity types, no daemon, no multi-source-in-one-call).

Additionally:
- No replacement of TASK 016 promote/demote — they remain operator-only.
- No retroactive migration of existing single-course vaults — they
  continue to work without `vault_id` (v1 behaviour preserved).
- No change to the `wiki_ops.py register-summary` / `upsert-page` /
  `append-log` / `log-event` / `update-index` argparse contracts (they
  are stable building blocks for `ingest`).
- No web UI, no CI workflow for benchmarking.

---

## 7. Risk → Mitigation

| Risk | Mitigation |
|---|---|
| 1. The new `ingest` orchestrator duplicates or contradicts atomic-op invariants (e.g., two different idempotency strategies). | R5 requires `ingest` to compose existing atomic ops, not reimplement them. Architecture test in R14.5 enforces import shape. |
| 2. Manifest schema drift between this skill and the index-layer consumer. | R6.3 mandates a single reference page (`manifest_schema.md`) copy-verbatim from CONTRACT §1. R13.4 e2e test cross-validates fields. |
| 3. `vault_id` mandate breaks existing standalone wiki-ingest users (one vault, no DB indexer). | R3 (relaxed 2026-05-27): wiki-ingest **does NOT require** `vault_id`. It reads & emits if present, emits `null` otherwise. Enforcement lives in the consumer (`/wiki-enrich` and `wiki-init` in the index layer). Standalone users see no breaking change — opt-in via `--vault-id` flag if they want strict checks. |
| 4. `--known-concepts-stdin` payload too large (10k entities). | Stdin is unbounded; pass-through to summarizing-meetings whose prompt may truncate. Acceptance criteria don't enforce a size limit; surface as KNOWN_ISSUES if observed at runtime. |
| 5. Partial-success state (`exit 20`) leaves the operator confused about which writes happened. | R6.4 manifest carries `written_so_far[]` + `cleanup_advice`; R13.1 includes recovery test. |
| 6. CLI wrapper (`bin/wiki-ingest`) breaks on edge shells (zsh + symlinks + spaces in PATH). | R1.4 — wrapper uses `readlink -f` (cross-shell); R13.3 dedicated test. |

---

## 8. Predecessor / Successor

**Predecessors** (context, not dependencies — they have already landed):
- TASK 015 — modular refactor of wiki-ingest (the F1/F2/F3 layered DAG).
- TASK 016 — cross-course promotion / demotion (the two-tier vault model
  + lint invariant + root-aware upsert).

**Successors** (out of this task's scope, future work):
- Multi-source-in-one-call `ingest --sources <dir>` (operator-loop today).
- Web-fetched sources (URL → content) — Epic 6 in `obsidian-llm-wiki`.
- Entity-resolver / RAG (`wiki-query`, `wiki-extract-concepts`) — Epic 7
  in `obsidian-llm-wiki`.

---

## Verification (after Planner + Developer phases)

1. `wiki-ingest --version` returns `wiki-ingest 1.1.0` (R2).
2. `wiki-ingest ingest --source <real-md> --vault <real-vault>
   --output-format json` produces a manifest validated by R6.
3. Exit-code matrix covers 0/20/21/22/23/24/25/26 with structured envelopes (26 = timeout, split from 21 per R4.1; both 21 and 26 envelopes MUST carry `phase:"<phase>"`). Audit + per-code call sites: [`skills/wiki-ingest/references/exit_codes.md`](../skills/wiki-ingest/references/exit_codes.md).
4. UC-1 end-to-end through `obsidian-llm-wiki`'s `/wiki-enrich` returns
   `{"action":"enriched",…}` with non-empty `index.upserted[]`.
5. UC-3 strict-mode vault_id enforcement: caller `--vault-id` flag drives
   exit 23/25; malformed slug drives exit 24; standalone users without the
   flag are unaffected (manifest `vault_id: null`, exit 0).
6. UC-4 source-hash short-circuit emits empty `written[]`, no LLM call.
7. UC-5 partial-state emits exit 20 + recovery info.
8. All existing TASK 015/016 unit + integration tests still pass
   (no regression).
9. SKILL.md + manifest_schema.md + wiki_schema.md updated; validators
   (`validate_skill.py`, `skill-validator/validate.py`) green.

When all 9 pass — TASK 017 closes; `obsidian-llm-wiki`'s P0 R-0 blocker
(in its ROADMAP) lifts automatically.

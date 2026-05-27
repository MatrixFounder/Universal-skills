# wiki-ingest v1.1 manifest schema (in-repo contract mirror)

> **In-repo authority.** This file mirrors the external contract at
> `obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md`. If the
> external file moves, renames, or revises out of step, **this file
> wins** as far as wiki-ingest is concerned. Any divergence is a bug —
> open a follow-up TASK to reconcile.

Every section below carries a provenance header so a future
maintainer can verify drift against the external source. The dates
are the contract-revision dates, not this file's commit date.

Exit codes referenced in this file map to symbolic names in
[`./exit_codes.md`](./exit_codes.md) (the single source of truth for
the matrix). The v1.1 contract band is **20..26**.

---

## §1 — Manifest schema and examples (R6)

> sourced from `obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md` §1 (2026-05-27)

`commands/ingest.py --output-format json` writes a single JSON object
to stdout on success or partial-success. The top-level shape is fixed
within the 1.1.x band (additive changes only; renames/removals would
bump to 1.2+).

### 1.1 Success envelope (full ingest)

```json
{
  "manifest_version": "1.1",
  "status": "ok",
  "vault_id": "trade-agents",
  "vault_root": "/abs/path/to/vault",
  "course": "Course A",
  "source": {
    "path": "/abs/path/to/raw/transcript.md",
    "slug": "transcript-2026-05-27",
    "hash": "8f4a...sha256hex"
  },
  "written": [
    {"path": "Lessons/Course A/_sources/transcript-2026-05-27.md",
     "action": "created", "kind": "source", "scope": "course"},
    {"path": "Lessons/Course A/_concepts/Sharpe Score.md",
     "action": "created", "kind": "concept", "scope": "course"},
    {"path": "Lessons/Course A/_concepts/Volatility.md",
     "action": "updated", "kind": "concept", "scope": "course"},
    {"path": "Lessons/Course A/index.md",
     "action": "updated", "kind": "index", "scope": "course"},
    {"path": "Lessons/Course A/log.md",
     "action": "appended", "kind": "log", "scope": "course"}
  ],
  "created": [
    "Lessons/Course A/_sources/transcript-2026-05-27.md",
    "Lessons/Course A/_concepts/Sharpe Score.md"
  ],
  "touched": [
    "Lessons/Course A/_concepts/Volatility.md",
    "Lessons/Course A/index.md"
  ],
  "contradictions": 0,
  "summary_path": "Lessons/Course A/_sources/transcript-2026-05-27.md",
  "log_event": {
    "event_ts": "2026-05-27T14:32:08+00:00",
    "event_type": "ingest",
    "subject": "Karpathy LLM lesson 2026-05-27",
    "log_md_byte_offset": 4218
  },
  "llm_tokens_used": {
    "input": 4218,
    "output": 1102,
    "model": "claude-opus-4-7"
  }
}
```

### 1.2 Source-hash short-circuit envelope (UC-4)

When `--source-hash <hex>` matches the recorded footer of an existing
`_sources/<slug>.md`, no LLM call runs and no writes happen:

```json
{
  "manifest_version": "1.1",
  "status": "ok",
  "action": "unchanged",
  "vault_id": "trade-agents",
  "vault_root": "/abs/path/to/vault",
  "course": "Course A",
  "source": {"path": "...", "slug": "...", "hash": "8f4a..."},
  "written": [],
  "created": [],
  "touched": [],
  "contradictions": 0,
  "summary_path": "Lessons/Course A/_sources/transcript-2026-05-27.md",
  "log_event": null,
  "llm_tokens_used": {"input": 0, "output": 0, "model": null}
}
```

### 1.3 Partial-success envelope (exit 20)

Mid-pipeline failure — see §3 atomicity contract. The orchestrator
exits 20 and emits this shape INSTEAD of the success envelope:

```json
{
  "manifest_version": "1.1",
  "status": "error",
  "phase": "upsert-page",
  "code": "PARTIAL_INDEX_FAILURE",
  "written_so_far": [
    {"path": "...", "action": "created", "kind": "source", "scope": "course"},
    {"path": "...", "action": "created", "kind": "concept", "scope": "course"}
  ],
  "cleanup_advice": "Run `wiki-ingest lint --fix` then retry.",
  "vault_id": "trade-agents",
  "vault_root": "/abs/path/to/vault"
}
```

### 1.4 Field reference

**Top-level**

| Field              | Type                              | Notes                                                                                              |
|--------------------|-----------------------------------|----------------------------------------------------------------------------------------------------|
| `manifest_version` | string                            | Always `"1.1"` within the 1.1.x band. Consumers MUST hard-fail on a major bump (`"1.2"`, etc.).    |
| `status`           | `"ok"` \| `"error"`               | `"error"` only in the partial / hard-failure envelopes.                                            |
| `action`           | `"unchanged"` (optional)          | Present only in §1.2 source-hash short-circuit envelope.                                            |
| `vault_id`         | string \| null                    | Echo of `read_vault_id(vault_root)`. `null` when frontmatter has no `vault_id:` field.             |
| `vault_root`       | string (absolute path)            |                                                                                                    |
| `course`           | string \| null                    | Course directory basename (e.g., `"Course A"`); `null` on single-course vaults (Q-5).               |
| `source`           | object                            | `{path, slug, hash}` — slug is `_safe_name`'d; hash is sha256-hex of input bytes.                  |
| `written[]`        | list of WrittenEntry              | Empty in success-no-op and partial envelopes (see `written_so_far[]` instead in partial).          |
| `created[]`        | list of vault-relative paths      | Subset of `written[]` where `action == "created"`.                                                  |
| `touched[]`        | list of vault-relative paths      | Subset of `written[]` where `action == "updated"`.                                                  |
| `contradictions`   | int                               | Sum of per-`upsert-page` contradiction counts.                                                     |
| `summary_path`     | string (vault-relative) \| null    | Post-write path of `_sources/<slug>.md`. `null` in the Phase-1 stub and in pre-write error states. |
| `log_event`        | object \| null                    | See §1.5. `null` in source-hash short-circuit (no log entry written).                              |
| `llm_tokens_used`  | object                            | `{input, output, model}` — token counters; `model` may be `null` if no LLM call ran.                |

**WrittenEntry** (each row in `written[]` / `written_so_far[]`):

| Field    | Type   | Allowed values                                       |
|----------|--------|------------------------------------------------------|
| `path`   | string | Vault-relative path (forward-slash POSIX form).      |
| `action` | string | `"created"` \| `"updated"` \| `"appended"`.          |
| `kind`   | string | `"source"` \| `"concept"` \| `"entity"` \| `"index"` \| `"log"`. |
| `scope`  | string | `"course"` \| `"vault"` (per TASK 016 two-tier).     |

### 1.5 LogEventEnvelope (mirrored into the index layer's `log_events`)

| Field                | Type   | Notes                                                                  |
|----------------------|--------|------------------------------------------------------------------------|
| `event_ts`           | string | ISO-8601 with TZ (e.g. `2026-05-27T14:32:08+00:00`).                   |
| `event_type`         | string | One of `"ingest"`, `"reindex"`, `"lint"`, `"promote"`, `"demote"`.     |
| `subject`            | string | Human-readable subject (typically source title).                       |
| `log_md_byte_offset` | int    | Byte position of the corresponding line in the course's `log.md`. The index layer uses this to round-trip log.md back to its `log_events` rows. |

---

## §2 — Known-concepts injection payload (R7)

> sourced from `obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md` §2 (2026-05-27)

`--known-concepts-stdin` reads stdin until EOF (size-bounded to 1 MiB
via `WIKI_INGEST_KNOWN_CONCEPTS_MAX_BYTES`; T17-S2).
`--known-concepts-file <path>` reads the same shape from disk
(operator-supplied path; no `_is_relative_to(vault)` check per
T17-S3). The two flags are mutually exclusive.

Payload shape: JSON array of objects.

```json
[
  {"slug": "sharpe-score", "name": "Sharpe Score", "aliases": ["Sharpe Ratio"]},
  {"slug": "volatility",   "name": "Volatility",   "aliases": []}
]
```

| Field     | Type            | Notes                                                                    |
|-----------|-----------------|--------------------------------------------------------------------------|
| `slug`    | string          | Lower-case kebab; matches the consumer DB's primary key.                 |
| `name`    | string          | Display name; used for dangling-link prevention in synthesis prompt.     |
| `aliases` | list of strings | Optional. Alternate names that should also resolve to this concept.      |

**Merge rule**: when both `scan`-derived and supplied lists exist,
the **DB-supplied entry wins on slug collision** (R7.4 — the index
layer is authoritative for entity identity). The orchestrator merges
and passes the union to the synthesiser.

---

## §3 — Atomicity contract + exit codes (R4, R5.3)

> sourced from `obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md` §3 (2026-05-27)

### 3.1 Atomicity strategy — per-step rollback (Q-1 RESOLVED option (a))

Each atomic op (`register-summary`, `upsert-page`, `update-index`,
`append-log`, `log-event`) commits independently. Mid-pipeline failure
DOES NOT roll back what already succeeded; the orchestrator emits the
§1.3 partial envelope and exits 20. The caller (`/wiki-enrich`) gates
its DB-side reflection on `exit 20 + non-empty written_so_far[]` ⇒
refuse to half-index; surface to operator.

Rationale (architecture §2.4): vault writes touch multiple
directories (`_sources/`, `_concepts/`, `_entities/`, `index.md`,
`log.md`) any of which may live on a separate filesystem (network
mount, encrypted overlay). `os.rename` cannot cross device
boundaries, so stage-to-tempdir → rename-on-success is structurally
unavailable.

### 3.2 Exit-code table (v1.1 contract band)

The full matrix (legacy 0..8 + reserved 10..19 + v1.1 20..26 +
reserved 27..29) lives in [`./exit_codes.md`](./exit_codes.md). The
v1.1-NEW codes alone:

| Code | Symbolic name              | Carries manifest?                                  | `phase` discriminator? |
|------|----------------------------|----------------------------------------------------|------------------------|
| 20   | `EXIT_PARTIAL`             | Yes — `written_so_far[]` + `phase` (§1.3).         | Required               |
| 21   | `EXIT_SUBPROCESS`          | Optional (error envelope w/ `phase`).              | Required               |
| 22   | `EXIT_LLM`                 | Optional (error envelope w/ `phase`).              | Required               |
| 23   | `EXIT_MISSING_VAULT_ID`    | No (error envelope only).                          | n/a                    |
| 24   | `EXIT_INVALID_VAULT_ID`    | No.                                                | n/a                    |
| 25   | `EXIT_VAULT_ID_MISMATCH`   | No.                                                | n/a                    |
| 26   | `EXIT_TIMEOUT`             | Optional (`phase:"timeout"`).                      | Required               |

The split between 21 and 26 lets the bridge route on recoverable
timeouts without conflating them with genuine downstream failures.

---

## §5 — Config file (`--config <path>`) (R11)

> sourced from `obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md` §5 (2026-05-27)

The orchestrator accepts a YAML subset via `--config <path>` (T17-S5
— parsed by a hand-rolled subset parser; NO `PyYAML` dependency).
Supported shape: scalar keys with scalar values, flat lists, and ONE
level of nesting (`section: subkey: value`). Deeper nesting (e.g.
`wiki: transcript: model:`) is NOT supported in 1.1; consumers
needing it should use dotted top-level keys or wait for a 1.1.x
additive extension.

```yaml
# Example: one level of nesting
transcript:
  model: claude-opus-4-7
  timeout_seconds: 600
known_concepts:
  max_bytes: 1048576

# Or, equivalently, flat keys:
transcript_model: claude-opus-4-7
transcript_timeout_seconds: 600
known_concepts_max_bytes: 1048576
```

**Precedence (R11.2)**: `CLI flag > config file > built-in default`.

**Forward-compat**: unknown keys produce a warning to stderr but do
NOT fail the parse (R11.3 — additive within 1.1.x).

**Defended attack surface**: the subset parser refuses YAML
tag-construction (`!!python/object/apply` etc.) — those bytes are
treated literally as string values, never executed. Locks against
the `yaml.load` exec-tag CVE class.

---

## §6 — Source-hash idempotency (R9)

> sourced from `obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md` §6 (2026-05-27)

### 6.1 Format

`--source-hash <hex>` accepts only `^[0-9a-fA-F]{64}$` (sha256 hex,
case-insensitive; lowercased before any downstream use). T17-S4
validates BEFORE any I/O; malformed value → exit 2.

### 6.2 Short-circuit behaviour (UC-4)

When `--source-hash` matches the recorded footer hash in
`_sources/<slug>.md`, the orchestrator emits the §1.2 short-circuit
envelope and exits 0. NO synthesiser subprocess runs; NO writes
happen.

When the supplied hash differs from the recorded value OR no recorded
value exists, the orchestrator proceeds with the full pipeline. The
supplied hash is used for the footer write + log-event details
(additive-merge contract — the operator vouches that the supplied
hash is the canonical digest of the bytes they have).

### 6.3 Trust model

The caller supplies a hex digest of bytes it already has; the skill
performs NO additional validation beyond the format check. Supplying
a wrong hash silently re-uses a stale record but cannot escape the
vault sandbox (containment defenses in `_safety` + `_atomic_write_text`
still apply).

---

## §7 — Version freeze + minimum-version check (R2)

> sourced from `obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md` §7 (2026-05-27)

### 7.1 Version output

`wiki-ingest --version` (top-level flag, NOT a subcommand) writes
exactly `wiki-ingest <MAJOR>.<MINOR>.<PATCH>\n` to stdout and exits 0.

```text
$ wiki-ingest --version
wiki-ingest 1.1.0
```

### 7.2 Minimum-version check (consumer pattern)

The bridge `/wiki-enrich` performs a prefix + tuple compare:

```python
parts = stdout.strip().split()           # ["wiki-ingest", "1.1.0"]
assert parts[0] == "wiki-ingest"
ver = tuple(int(p) for p in parts[1].split(".")[:2])
assert ver >= (1, 1), f"need wiki-ingest >= 1.1, found {parts[1]}"
```

### 7.3 Forward-compat (frozen-CLI rule)

Additive changes within the 1.1.x band do NOT bump `manifest_version`.
Removing or renaming a manifest field requires bumping to 1.2.
Consumers MUST ignore unknown fields and MUST hard-fail on a major
bump beyond the version they were built against.

---

## §8 — Subprocess-friendly behaviour (R10)

> sourced from `obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md` §8 (2026-05-27)

### 8.1 TTY-aware output

`os.isatty(1)` check: when stdout is piped, the orchestrator
suppresses decorative output (banners, progress bars). Only
structured JSON goes to stdout; unstructured logs go to stderr.

### 8.2 `--quiet`

Forces quiet regardless of TTY. Equivalent to "stdout is piped" for
output-suppression purposes.

### 8.3 `--timeout-seconds <N>`

Default 600 seconds; env var `WIKI_INGEST_TIMEOUT` is the fallback
when the flag is absent (R10.4). The orchestrator wraps the
synthesiser subprocess in `subprocess.run(timeout=N)`. On overrun,
the subprocess is killed via `Popen.kill()` (T17-S6 — SIGKILL,
guarantees no zombie LLM process).

Timeout → exit **26** + partial envelope (§1.3) carrying
`phase:"timeout"`. This is SPLIT from exit 21 (generic downstream
subprocess failure) so callers can route on retry semantics without
inventing a `phase`-only discriminator API.

### 8.4 Path semantics

`--source <abs-path>` and `--vault <abs-path>` MUST be absolute paths
when consumed by automated bridges. Relative paths are accepted (and
resolved via `pathlib.Path.resolve()`) but the bridge's contract
documents absolute paths only.

---

## Forward-compatibility

Every manifest carries `"manifest_version": "1.1"` at the top level
(§1). Within the 1.1.x band, additive field changes are allowed;
consumers MUST ignore unknown fields. Renames / removals require
bumping to "1.2" or higher; consumers MUST hard-fail on a major bump.

## Where to look when a number changes

- Exit codes (matrix + bands): [`./exit_codes.md`](./exit_codes.md).
- Vault schema fields (`schema_version`, `vault_id`, etc.):
  [`./wiki_schema.md`](./wiki_schema.md).
- Architecture-level rationale: [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) §2.4 + §4.5.5.

# Task 017.06 — `commands/ingest.py` write path (Phase 2)

## Use Case Connection

- **UC-1** Main scenario steps 5(a)–5(h) (full bridge orchestrator
  round-trip).
- **UC-2** Main scenario (operator-direct ingest, human + JSON output).
- **UC-5** Main scenario (partial-success recovery via exit 20 +
  `phase` + `written_so_far[]`).
- **Q-5** verification on a single-course vault (manifest emits
  `course: null` + `scope: "course"`).

## Task Goal

Replace the Phase-1 stub (empty `written[]`) with the real orchestrator
composition. Each step of the R5.2 pipeline runs through
`_dispatch.dispatch()` — `register-summary` → N× `upsert-page` →
`update-index` per layer → `append-log` → `log-event`. After each
successful dispatch, append a `WrittenEntry` to the running
`written[]` list. On mid-pipeline failure (any dispatch returns
non-zero), emit a partial-success envelope (Q-1 / Arch-M-5):
`{status:"error", phase:"<phase>", written_so_far:[…],
cleanup_advice:"…"}` to stdout and exit `EXIT_PARTIAL` (20).

Per Stub-First (PLAN §2), this is Phase 2: real logic replaces the
hardcoded empty `written[]`. The Phase-1 unit tests are extended to
assert the actual `git diff` of the fixture matches the manifest claim
post-dispatch.

## Changes Description

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ingest/commands/ingest.py`

**`execute(args)` is extended** (Phase 1 sections kept; the Phase-1
empty-write stub at the end is replaced):

After the source-hash short-circuit (R9.3) and BEFORE the manifest
emission:

1. **Summary synthesis** (R5.2(c)):
   - Detect if `source` is already a `.md` summary: read the front-
     matter via `_frontmatter.split_frontmatter`; if
     `fm.get("type") in {"summary", "lesson-summary",
     "meeting-summary"}` → skip synthesis, treat `source` as the
     summary input directly.
   - Otherwise: run `summarizing-meetings` (existing TASK 015 helper
     subprocess pattern). Capture LLM token usage from the JSON output
     for the manifest's `llm_tokens_used` field. On subprocess failure
     → emit partial envelope with `phase:"summarize"`, exit 21
     (`EXIT_SUBPROCESS`).
2. **Pipeline dispatch loop** (R5.2(d)..(g)):
   - `written: list[dict] = []` (the running list).
   - Build the namespace for each atomic op using the args the user
     supplied + the resolved vault paths.
   - For each step in order:
     ```python
     for (cmd_name, phase, build_ns) in [
         ("register-summary", "register-summary", _build_reg_ns),
         # N concept/entity targets:
         *[("upsert-page", "upsert-page", _make_upsert_builder(target)) for target in targets],
         # Index updates (per affected layer):
         *[("update-index", "update-index", _make_idx_builder(layer)) for layer in affected_layers],
         ("append-log", "append-log", _build_aplog_ns),
         ("log-event", "log-event", _build_logev_ns),
     ]:
         step_args = build_ns(args, source, course_root, vault_root)
         rc = _dispatch.dispatch(cmd_name, step_args)
         if rc != 0:
             _emit_partial(written, phase, cleanup_advice)
             return EXIT_PARTIAL
         written.append(_written_entry_from(step_args, phase, course_root, vault_root))
     ```
   - The `_written_entry_from` helper builds a `WrittenEntry` dict
     (Architecture §4.5.5) from the just-executed step.
3. **`log_event` byte-offset capture** (R8.2):
   - After the `append-log` dispatch returns, re-read the affected
     `log.md` via `_safety.read_text` and locate the just-appended
     line via the existing TASK 016 marker pattern (an ISO-8601
     prefix on a `## ` heading). Compute the byte offset of that
     line's first byte. Pass the offset into the
     `_build_logev_ns(offset=…)` builder so `log-event` records it.
   - The manifest's `log_event` object gets the offset back via the
     `log-event` command's output (TASK 015 already emits this on
     JSON return).
4. **Manifest assembly** (Architecture §4.5.5):
   - `manifest = {"manifest_version":"1.1", "status":"ok", "vault_id":
     effective_vault_id, "vault_root":str(vault_root), "course":
     <course-name-or-null>, "source":{"path":str(source),
     "slug":source_slug, "hash":computed_or_supplied_hash},
     "written":written, "created":[w["path"] for w in written if
     w["action"]=="created"], "touched":[w["path"] for w in written if
     w["action"]=="updated"], "contradictions":<sum>,
     "summary_path":..., "log_event":{...}, "llm_tokens_used":{...}}`.
   - `course` value:
     - Two-tier: `course = course_root.relative_to(vault_root).name`
       (e.g. `"Course A"`).
     - Single-course: `course = None` (per Q-5).
   - `scope` per `written` entry: `"course"` if path is inside
     `course_root.relative_to(vault_root)`; `"vault"` if path is at
     vault root (`_concepts/`, `_entities/`, root `index.md`).
5. **Emission**:
   - JSON: `_emit_manifest(manifest)`.
   - Human: 5–10 line summary listing the per-step actions.
   - Exit `EXIT_OK`.

**New helper functions in `commands/ingest.py`**:

- `_emit_partial(written: list, phase: str, cleanup_advice: str) -> None`
  — assembles the partial envelope:
  ```python
  {"manifest_version":"1.1", "status":"error",
   "phase":phase, "code":"PARTIAL_INDEX_FAILURE",
   "written_so_far":written, "cleanup_advice":cleanup_advice,
   "vault_id":..., "vault_root":...}
  ```
  passes through `_safe_for_json`, writes to stdout. Caller exits with
  `EXIT_PARTIAL`.

- `_written_entry_from(step_args, phase, course_root, vault_root) -> dict`
  — derives the `WrittenEntry` per Architecture §4.5.5.

- `_make_upsert_builder(target_dict)` — closure that builds an
  argparse Namespace for one `upsert-page` call.

- `_make_idx_builder(layer)` — closure for one `update-index` call.

- `_extract_targets_from_summary(summary_path: Path) -> list[dict]`
  — reads the just-written `_sources/<slug>.md` and parses the wiki-
  link references to determine which concepts/entities need
  upserting. Uses `_markdown._extract_wikilinks_with_anchors` (mask-
  once helper) — no new regex. Returns a sorted list (determinism).

**LoC budget**: this bead pushes `commands/ingest.py` toward the
≤ 400-LoC architecture budget. If the bead exceeds 400 LoC, the
helpers `_make_upsert_builder` / `_make_idx_builder` /
`_extract_targets_from_summary` should be moved to a new module
`wiki_ingest/_ingest_helpers.py` (F2 helper) — but this is an
escape valve, NOT the default plan.

### Component Integration

- Continues to import `_safety` + `_frontmatter` + `_markdown` (NEW for
  the wikilink extraction) + `_vault` + `_dispatch`. NO new command
  imports.
- The byte-offset capture (R8.2) re-uses existing `_safety.read_text`
  + a one-pass byte scan — no new helper.
- The summary-vs-transcript detection uses existing
  `_frontmatter.split_frontmatter` — no new helper.

## Test Cases

### End-to-end Tests

1. **TC-E2E-017-06-01:** UC-1 happy path (two-tier vault)
   - Fixture: `tests/fixtures/two_course_vault/` with a fresh
     transcript source.
   - Run: `wiki-ingest ingest --source <source> --vault <vault>
     --output-format json`.
   - Expected: exit 0; manifest's `written[]` lists EVERY file the
     bead actually touched on disk; `git diff` of the fixture
     matches the manifest claim (no orphan writes); `course:
     "Course A"`; `scope` values per Q-5; `log_event.log_md_byte_offset`
     is non-zero and points to a `## ` line in the course `log.md`.
2. **TC-E2E-017-06-02:** UC-2 operator-direct ingest (single-course)
   - Fixture: single-course vault (no root schema).
   - Run: `wiki-ingest ingest --source <source> --vault <vault>`
     (default `--output-format human`).
   - Expected: exit 0; stdout has the human-readable summary; the
     vault is touched; `vault_id: null` + `course: null` would appear
     in JSON form (assert via a follow-up `--output-format json` call
     on the same fixture post-state — should be a `--source-hash`
     short-circuit).
3. **TC-E2E-017-06-03:** UC-5 partial-success recovery (exit 20)
   - Fixture: two-tier vault; inject a write failure mid-pipeline
     (e.g., monkeypatch `_safety.write_text` to raise `OSError` on the
     4th `upsert-page` of 6).
   - Run: ingest.
   - Expected: exit 20; stdout has partial envelope with
     `phase:"upsert-page"`, `written_so_far:[…3 entries…]`,
     `cleanup_advice` non-empty; pages 1–3 are on disk; pages 4–6 are
     NOT.
4. **TC-E2E-017-06-04:** Q-5 single-course `course: null` +
   `scope: "course"`
   - Fixture: single-course vault (no root schema).
   - Run: `… --output-format json`.
   - Expected: `course == None` (JSON `null`); every
     `written[].scope == "course"`.

### Unit Tests (`tests/commands/test_ingest.py` — extended)

1. **TC-UNIT-017-06-01:** `_written_entry_from` returns the right
   shape per Architecture §4.5.5 WrittenEntry table.
2. **TC-UNIT-017-06-02:** `_make_upsert_builder` argparse Namespace
   has every required key for `commands.upsert_page.execute`.
3. **TC-UNIT-017-06-03:** Summary-detect (`type: lesson-summary`) →
   skip synthesis path.
4. **TC-UNIT-017-06-04:** Dispatch propagation — when
   `_dispatch.dispatch("upsert-page", ...)` returns 1, the orchestrator
   emits partial + exit 20 (NOT exit 1).
5. **TC-UNIT-017-06-05:** `log_event.log_md_byte_offset` is the byte
   position of a `## ` line in `log.md` (re-read the file, assert
   `content[offset:offset+3] == "## "`).
6. **TC-UNIT-017-06-06:** `contradictions` sum — when individual
   `upsert-page` dispatches report contradictions, the manifest's
   total is the sum. Confirms R6.1 carry-over from TASK 016.
7. **TC-UNIT-017-06-07:** Manifest stays `manifest_version: "1.1"`
   (Arch-M-3 verified after Phase 2 — Phase 1 already locked it; this
   asserts no regression).
8. **TC-UNIT-017-06-08:** Idempotency on re-run — running the same
   call twice with the SAME source produces:
   - First run: `written[]` non-empty.
   - Second run: source-hash short-circuit fires (the footer now has
     the hash); `action: "unchanged"`; `written: []`.

### Regression Tests

- `tests/test_e2e_promotion.py` (TASK 016 round-trip) — still green;
  `ingest` does NOT auto-promote (R15.4 + Q-5).
- `tests/test_architecture.py` — green; `commands/ingest.py` imports
  only F1/F2/F3-helpers and `_dispatch` (no other command modules at
  module level).
- `tests/commands/test_lint.py` — after a successful `ingest`, lint
  reports zero `invariant_violation` findings (TASK 016 invariant
  preserved).

## Acceptance Criteria

- [ ] `commands/ingest.py` ≤ 400 LoC (architecture §3.2 budget).
- [ ] UC-1 round-trip on `two_course_vault` fixture: manifest's
      `written[]` matches the actual git diff.
- [ ] UC-5 mid-pipeline failure → exit 20 + partial envelope with
      `phase` + `written_so_far[]` populated.
- [ ] Q-5 verified: single-course → `course: null` + every
      `scope: "course"`.
- [ ] `log_event.log_md_byte_offset` is the byte position of the
      appended `## ` heading line in `log.md`.
- [ ] Idempotent re-run via source-hash → empty `written[]`,
      `action: "unchanged"`, exit 0.
- [ ] All TASK 015/016 tests still green (no regression).
- [ ] `tests/test_architecture.py` green.
- [ ] `tests/test_manifest_schema.py` green (manifest still matches
      the reference page's §1 example shape).

## Notes

- The partial-success contract (Q-1) is the most-tested path here
  because it's the one consumers (`/wiki-enrich`) gate their DB-side
  reflection on. TC-E2E-017-06-03's `monkeypatch _safety.write_text`
  is the cleanest injection point — it works against any dispatched
  atomic op without per-command knowledge.
- `_extract_targets_from_summary` uses the existing mask-once helper
  from `_markdown.py`; no new regex compilation. Determinism via
  sorted output is locked by TASK 015 conventions.
- TASK 015 R11 byte-identity (CLI single-course): re-confirmed by
  TC-E2E-017-06-02 — single-course vaults with no root schema produce
  the same vault state as if the operator had run the atomic ops by
  hand (modulo the new `_sources/<slug>.md` footer's `source_hash`
  comment, which is additive and already lives on the TASK 015 code
  path).
- The `--apply` semantics from TASK 016's `promote`/`demote` are NOT
  inherited here — `ingest` always writes (it has no dry-run mode in
  v1.1). UC-5 partial-success is the closest analog and is locked by
  TC-E2E-017-06-03.

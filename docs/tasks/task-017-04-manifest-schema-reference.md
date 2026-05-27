# Task 017.04 — `references/manifest_schema.md` (verbatim contract mirror)

## Use Case Connection

- Foundation for **UC-1** (the bridge reads the in-repo contract to
  pre-flight the call) — without this reference page, the only source
  of truth is the external `obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md`,
  which can move/rename without warning.
- Arch-M-1: lands BEFORE the orchestrator skeleton (017-05); 017-05's
  tests embed the §1 JSON example block as a fixture.

## Task Goal

Create `skills/wiki-ingest/references/manifest_schema.md` containing
verbatim copies of every CONTRACT section that R1..R11 reference:

- **CONTRACT §1** — Manifest JSON schema + examples (R6).
- **CONTRACT §2** — `--known-concepts-*` payload shape (R7).
- **CONTRACT §3** — Atomicity contract + exit-code table (R4, R5.3).
- **CONTRACT §5** — Config YAML subset (R11).
- **CONTRACT §6** — Source-hash idempotency rules (R9).
- **CONTRACT §7** — Version freeze + minimum-version check (R2).
- **CONTRACT §8** — Subprocess-friendly behaviour (R10).

Each embedded section MUST carry a one-line provenance header:

```
> sourced from obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md §N (2026-05-27)
```

so a future maintainer can verify drift against the external contract.

This bead is **doc-only** — no Python, no shell. Per Stub-First, write
the reference page in full, then add `tests/test_manifest_schema.py`
that parses the §1 JSON example block and asserts round-trip.

## Changes Description

### New Files

- `skills/wiki-ingest/references/manifest_schema.md` — the verbatim
  reference page (target length ~250-400 lines depending on contract
  size).
- `skills/wiki-ingest/scripts/tests/test_manifest_schema.py` — parses
  the §1 example block, asserts JSON validity + key set.

### Changes in Existing Files

None at this bead. 017-09 will cross-link from SKILL.md and update
`.AGENTS.md` during the documentation sweep.

### File contents (`references/manifest_schema.md`)

Top-level structure:

```markdown
# wiki-ingest v1.1 manifest schema (verbatim contract mirror)

> **In-repo authority.** This file mirrors the external contract at
> `obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md`. If the
> external file moves, renames, or revises out of step, **this file
> wins** as far as wiki-ingest is concerned. Any divergence is a bug —
> open a follow-up TASK to reconcile.
>
> All sections below are copied verbatim from the dated source. The
> dates in the provenance headers are the contract-revision dates, not
> this file's commit date.

---

## §1 — Manifest schema and examples (R6)

> sourced from obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md §1 (2026-05-27)

<verbatim copy of CONTRACT §1>

---

## §2 — Known-concepts injection payload (R7)

> sourced from obsidian-llm-wiki/docs/WIKI-INGEST-V1.1-CONTRACT.md §2 (2026-05-27)

<verbatim copy of CONTRACT §2>

[…and so on for §3, §5, §6, §7, §8…]
```

For each section, the body is the verbatim content from the external
contract. Anything the contract documents that this skill does NOT
implement (e.g., a hypothetical future field) is annotated inline with
a callout:

```markdown
> **wiki-ingest 1.1 note:** This field is documented in the contract
> but not yet emitted by `commands/ingest.py`. Consumers receiving an
> older manifest may treat the field as `null`. Tracked as
> KNOWN_ISSUES entry `<NAME>` if applicable.
```

The reference also includes the **structural forward-compat sentinel**
locked by Arch-M-3:

```markdown
## Forward-compatibility

Every manifest carries the field `"manifest_version": "1.1"` at the
top level (Architecture §4.5.5). Additive field changes within the
1.1.x band do NOT bump this. Renames / removals require bumping to
"1.2" or higher; consumers MUST hard-fail on a major bump.
```

### Component Integration

- The reference lives in `skills/wiki-ingest/references/` alongside
  `wiki_schema.md`, `karpathy-llm-wiki.md`, `architecture.md` (existing
  TASK 015/016 references).
- SKILL.md § "References" gets a one-line link added in 017-09 (the doc
  sweep bead).
- `.AGENTS.md` gets the file listed under "Reference files for the
  module" in 017-09.

## Test Cases

### Unit Tests (`tests/test_manifest_schema.py` — new)

1. **TC-UNIT-017-04-01:** §1 example block parses as valid JSON
   - Read `references/manifest_schema.md`; find the first fenced
     ```json block under the `## §1` heading; `json.loads(text)`.
   - Expected: no exception.
2. **TC-UNIT-017-04-02:** §1 example has the required top-level keys
   - Parse §1 example as in 04-01.
   - Expected: keys ⊇ `{"manifest_version", "status", "vault_id",
     "vault_root", "course", "source", "written", "created",
     "touched", "contradictions", "summary_path", "log_event",
     "llm_tokens_used"}`.
3. **TC-UNIT-017-04-03:** §1 example has `manifest_version == "1.1"`
   - Locks Arch-M-3 in the doc.
4. **TC-UNIT-017-04-04:** §1 example's `written[]` entries have the
   right shape
   - For each entry: keys ⊇ `{"path", "action", "kind", "scope"}`;
     `action ∈ {"created", "updated", "appended"}`;
     `kind ∈ {"source", "concept", "entity", "index", "log"}`;
     `scope ∈ {"course", "vault"}`.
5. **TC-UNIT-017-04-05:** §3 contains an exit-code table with all of
   0, 3, 4, 5, 6, 7, 8, 9
   - Parse §3 body, regex-search for each integer.
   - Expected: every code present at least once.
6. **TC-UNIT-017-04-06:** Provenance headers are present for every §
   - For each of §1, §2, §3, §5, §6, §7, §8: a line matching
     `^> sourced from obsidian-llm-wiki/docs/WIKI-INGEST-V1\.1-CONTRACT\.md §\d+ \(2026-\d{2}-\d{2}\)$`
     exists directly under the heading.
7. **TC-UNIT-017-04-07:** No bracket-style "TODO" markers
   - Static grep the reference for `TODO`, `FIXME`, `<verbatim copy of>`,
     `<…>` (literal angle brackets used as placeholders).
   - Expected: ZERO matches. Locks "the verbatim copy actually shipped".

### Regression Tests

- Run all TASK 015/016 existing tests — no regression (doc-only bead).

## Acceptance Criteria

- [ ] `references/manifest_schema.md` exists.
- [ ] Every required CONTRACT § (§1/§2/§3/§5/§6/§7/§8) has a verbatim
      copy with a provenance header (TC-UNIT-017-04-06).
- [ ] §1 example block is valid JSON with the required key set and
      `manifest_version == "1.1"` (TC-UNIT-017-04-01..04).
- [ ] §3 includes the full exit-code table (TC-UNIT-017-04-05).
- [ ] No bracket-style placeholders left in the file
      (TC-UNIT-017-04-07).
- [ ] `tests/test_manifest_schema.py` green.
- [ ] All TASK 015/016 tests still green.

## Notes

- **Why verbatim mirroring matters**: 017-05's
  `tests/commands/test_ingest.py` loads the §1 example block as a
  fixture and asserts the orchestrator's manifest matches the shape.
  This means a contract revision can be applied by editing exactly
  ONE file in this repo — bypass-proof.
- The provenance header's date is the contract-revision date, NOT the
  commit date. If the external contract moves to e.g.
  `(2026-06-15)`, the maintainer updates the header AND verifies the
  embedded body. The test in TC-UNIT-017-04-06 only checks the format,
  not the date value — date freshness is operator-judgement.
- For sections where the external contract is sparse (e.g. §5 may be
  just a paragraph), the embedded copy is still verbatim. Annotations
  go BELOW the verbatim block, never inside it, so a future automated
  diff against the external file remains feasible.

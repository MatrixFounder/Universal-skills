# Task 017.09 — E2E v1.1 contract smoke, docs, validators (final gate)

## Use Case Connection

- All UCs (UC-1..UC-5 + UC-6) exercised together end-to-end.
- Final integration gate — without this bead, the chain is technically
  complete but not validated as a whole.

## Task Goal

The final gate. This bead:

1. Ships the end-to-end smoke test `test_e2e_v1_1_contract.py` —
   subprocess-call `wiki-ingest ingest …` against
   `tests/fixtures/two_course_vault/`, parse the manifest, assert
   every CONTRACT §1 field is present and well-typed (R13.4).
2. Updates SKILL.md with the new `ingest` subcommand row + the
   §"Top-level orchestrator" subsection + the §"Install on PATH"
   note (already touched in 017-01; final reconciliation here) + the
   §"vault_id migration" paragraph (R12.1, R12.2).
3. Updates `references/wiki_schema.md` with §"vault_id field (v1.1)"
   (R12.4).
4. Updates `scripts/wiki_ingest/.AGENTS.md` with the new modules
   (`_dispatch.py`, `commands/ingest.py`) + `__version__` constant
   note (R12.6).
5. Runs `validate_skill.py` + `skill-validator/validate.py` + the
   cross-skill `diff -q` matrix as merge gates (R14.2, R14.3, R14.4).
6. Runs the TASK 015/016 full regression suite (R13.5).

This bead does NOT touch `docs/ARCHITECTURE.md` — that document was
updated during the architecture phase (preceding /vdd-plan); 017-09 is
not the place for further architecture revisions.

Per Stub-First, this bead is integration + documentation. No Phase 1
/ Phase 2 split — every assertion either passes or the bead does not
merge.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/tests/test_e2e_v1_1_contract.py` —
  subprocess-call E2E.

### Changes in Existing Files

#### File: `skills/wiki-ingest/SKILL.md`

- §"Script Contract" — add an `ingest` row to the existing subcommand
  table.
- New §"Top-level orchestrator" subsection (≤ 30 lines) — concise
  description of `ingest` + a one-line example + a pointer to
  `references/manifest_schema.md` for the full contract.
- New §"Install on PATH" subsection (reconciled with 017-01).
- New §"vault_id migration" paragraph — one sentence: "Existing
  two-tier vaults that want to integrate with the index layer
  (`obsidian-llm-wiki`) need to add `vault_id: <slug>` to root
  `WIKI_SCHEMA.md`. One-line edit. Not required for standalone use."

#### File: `skills/wiki-ingest/references/wiki_schema.md`

- New §"vault_id field (v1.1)" — documents the field's purpose,
  pattern (`^[a-z][a-z0-9-]{1,30}[a-z0-9]$` + no `--`), where it
  belongs (root `WIKI_SCHEMA.md` only — not on content pages), how to
  add it to an existing vault, and the exit codes 6/7/8 that fire when
  callers demand strict mode.

#### File: `skills/wiki-ingest/scripts/wiki_ingest/.AGENTS.md`

- Add the new modules: `_dispatch.py` (F3-boundary dispatch helper) +
  `commands/ingest.py` (orchestrator). Note that `__version__` lives
  in `__init__.py`.

### File contents (`tests/test_e2e_v1_1_contract.py`)

```python
"""End-to-end smoke test for the v1.1 contract surface (TASK 017 final gate).

Spawns wiki-ingest as a subprocess and validates the JSON manifest
against the contract embedded in references/manifest_schema.md §1.
Failure of any assertion = bead does not merge.
"""

import json
import subprocess
import unittest
from pathlib import Path


class TestE2EV1_1Contract(unittest.TestCase):
    def test_full_ingest_round_trip(self):
        fixture = Path(__file__).parent / "fixtures" / "two_course_vault"
        source = fixture / "Lessons" / "Course A" / "_inbox" / "transcript.md"
        wrapper = Path(__file__).parent.parent / "wiki-ingest"

        result = subprocess.run(
            [str(wrapper), "ingest",
             "--source", str(source),
             "--vault", str(fixture),
             "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0,
                         f"wiki-ingest failed: stderr={result.stderr}")

        manifest = json.loads(result.stdout)

        # Top-level shape (Architecture §4.5.5):
        for key in ("manifest_version", "status", "vault_id", "vault_root",
                    "course", "source", "written", "created", "touched",
                    "contradictions", "summary_path", "log_event",
                    "llm_tokens_used"):
            self.assertIn(key, manifest, f"missing key: {key}")

        self.assertEqual(manifest["manifest_version"], "1.1")
        self.assertEqual(manifest["status"], "ok")
        self.assertIsInstance(manifest["written"], list)
        self.assertGreater(len(manifest["written"]), 0,
                           "manifest must report at least one write")

        # written[] entry shape:
        for entry in manifest["written"]:
            for k in ("path", "action", "kind", "scope"):
                self.assertIn(k, entry)
            self.assertIn(entry["action"], {"created", "updated", "appended"})
            self.assertIn(entry["kind"], {"source", "concept", "entity",
                                          "index", "log"})
            self.assertIn(entry["scope"], {"course", "vault"})

        # Source-hash short-circuit on re-run:
        result2 = subprocess.run(
            [str(wrapper), "ingest",
             "--source", str(source),
             "--vault", str(fixture),
             "--source-hash", manifest["source"]["hash"],
             "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result2.returncode, 0)
        manifest2 = json.loads(result2.stdout)
        self.assertEqual(manifest2.get("action"), "unchanged")
        self.assertEqual(manifest2["written"], [])


if __name__ == "__main__":
    unittest.main()
```

### Component Integration

- This bead does not introduce new modules or alter the dependency
  graph. It exercises everything previous beads built and the docs
  layer.
- The E2E test is `unittest.TestCase` (per CLAUDE.md §1 — no pytest);
  it runs under the per-skill `.venv`.

## Test Cases

### End-to-end Tests

1. **TC-E2E-017-09-01:** Full UC-1 round-trip via the shell wrapper
   - Setup: `tests/fixtures/two_course_vault/` (TASK 016 fixture)
     with a fresh transcript source under
     `Lessons/Course A/_inbox/transcript.md`.
   - Run: see `test_e2e_v1_1_contract.py` above.
   - Expected: exit 0; manifest has the full v1.1 shape; `written[]`
     non-empty; second run with `--source-hash <returned>` produces
     `action: "unchanged"`.
2. **TC-E2E-017-09-02:** UC-1 with `--vault-id` strict mode (positive)
   - Setup: same fixture; root schema has
     `vault_id: trade-agents-test`.
   - Run: `… --vault-id trade-agents-test`.
   - Expected: exit 0; manifest's `vault_id == "trade-agents-test"`.
3. **TC-E2E-017-09-03:** Cross-skill `diff -q` matrix silent
   - Run the CLAUDE.md §9 verification command.
   - Expected: empty output.
4. **TC-E2E-017-09-04:** `validate_skill.py` exit 0
   - Run: `python3 .claude/skills/skill-creator/scripts/validate_skill.py
     skills/wiki-ingest`.
   - Expected: exit 0; "Gold Standard" verdict in stdout.
5. **TC-E2E-017-09-05:** `skill-validator/validate.py` SAFE
   - Run: `python3 .claude/skills/skill-validator/scripts/validate.py
     skills/wiki-ingest`.
   - Expected: risk classification SAFE; 0 Critical / 0 Errors.

### Regression Tests

- The FULL TASK 015 regression suite (the 138-test corpus).
- The FULL TASK 016 regression suite (`tests/test_e2e_promotion.py`
  + `tests/test_known_issues_resolved.py`).
- All 017-00..08 tests still green.
- `tests/test_architecture.py` green.

### Documentation Tests

1. **TC-DOC-017-09-01:** SKILL.md mentions `ingest`
   - Grep `SKILL.md` for `^wiki-ingest ingest`. Expected: at least 2
     occurrences (script-contract row + orchestrator subsection).
2. **TC-DOC-017-09-02:** `references/wiki_schema.md` mentions
   `vault_id` v1.1
   - Grep for `## .* vault_id field \(v1\.1\)`.
   - Expected: ≥ 1 match.
3. **TC-DOC-017-09-03:** `.AGENTS.md` mentions both new modules
   - Grep for `_dispatch` AND `commands/ingest.py` in the AGENTS.md.
   - Expected: both present.

## Acceptance Criteria

- [ ] `tests/test_e2e_v1_1_contract.py` green (TC-E2E-017-09-01).
- [ ] Strict-mode `--vault-id` smoke green (TC-E2E-017-09-02).
- [ ] Cross-skill `diff -q` matrix silent (TC-E2E-017-09-03).
- [ ] `validate_skill.py` exit 0 (TC-E2E-017-09-04).
- [ ] `skill-validator/validate.py` SAFE (TC-E2E-017-09-05).
- [ ] SKILL.md updated per R12.1 + R12.2 (TC-DOC-017-09-01).
- [ ] `references/wiki_schema.md` updated per R12.4 (TC-DOC-017-09-02).
- [ ] `.AGENTS.md` updated per R12.6 (TC-DOC-017-09-03).
- [ ] All TASK 015/016 + 017-00..08 tests still green.
- [ ] `tests/test_architecture.py` green (no regression).

## Notes

- This is a hard merge gate. If ANY of the validators or the E2E test
  fails, the bead does NOT merge — 017-09 is the final gate that lifts
  the `obsidian-llm-wiki`'s P0 R-0 blocker. A flaky test is not
  acceptable here; if the E2E is flaky on CI (subprocess timing), the
  bead must investigate the root cause rather than wrapping in a retry
  loop.
- TASK 015 R11 byte-identity (CLI single-course) is NOT explicitly
  re-asserted here — TC-E2E-017-06-02 already covers it, and the
  TASK 015 fixture suite running as part of the regression gate is
  the formal lock.
- The E2E test deliberately invokes via the shell wrapper
  (`scripts/wiki-ingest`) rather than `python3 wiki_ops.py` — this
  exercises the full v1.1 surface as a downstream consumer would. The
  test fails fast if the wrapper has a bad shebang, missing exec bit,
  or shell-quoting bug — locking 017-01's invariants from a different
  angle.

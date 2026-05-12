# Task 010-08 [LOGIC IMPLEMENTATION]: Final docs + validation gates

## Use Case Connection
- Locks all UCs (UC-01..UC-10) via the final release gate.
- Locks cross-skill replication boundary (TASK §6.1).

## Task Goal

Final release gate for Task 010: update `SKILL.md` registry +
honest-scope note; add `.AGENTS.md` section; pass
`validate_skill.py`; verify 12-line `diff -q` silence; verify LOC
budgets (≤ 60 LOC per shim, ≤ 1500 LOC total package); update
backlog xlsx-8 row status.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/SKILL.md`

**Locate** the script registry table (whatever its exact heading is —
likely "Скрипты", "Scripts", or similar — search by `csv2xlsx.py` row
to find it). **Add** two new rows mirroring the xlsx-2 / xlsx-3 row
format:

```markdown
| `xlsx2csv.py`  | Convert `.xlsx` to CSV (per-sheet or per-region). |
| `xlsx2json.py` | Convert `.xlsx` to JSON (flat / dict-of-arrays / nested by table). |
```

**Locate** `§10` honest-scope catalogue (look for "honest scope" or
"limitations"). **Append**:

```markdown
- **xlsx2csv / xlsx2json (v1):** comments / charts / images / shapes /
  pivots / data-validation dropped; cell styles dropped; rich-text →
  plain-text concat; `--tables listobjects` silently bundles Tier-2
  sheet-scope named ranges; full round-trip with `json2xlsx.py`
  requires xlsx-2 v2 `--write-listobjects` (deferred). See
  [docs/tasks/task-010-*.md](../../docs/tasks/) for details.
```

#### File: `skills/xlsx/.AGENTS.md`

**Append** a new section:

```markdown
## xlsx2csv2json (xlsx-8 read-back CLIs)

**Package:** `scripts/xlsx2csv2json/`
**Shims:** `scripts/xlsx2csv.py` (≤ 60 LOC) and `scripts/xlsx2json.py` (≤ 60 LOC).

### Closed-API consumption pattern

The package is the **first consumer** of the xlsx-10.A `xlsx_read/`
closed-API contract (ARCH D-A5). Imports come exclusively from
`xlsx_read.<public>`; the ruff banned-api rule in
`scripts/pyproject.toml` blocks any `xlsx_read._*` import.

### `--tables` enum mapping (ARCH D-A2)

The shim's 4-valued `--tables` flag maps to the library's 3-valued
`TableDetectMode`:

| Shim `--tables` | Library mode | Post-filter |
| --- | --- | --- |
| `whole` | `whole` | none |
| `listobjects` | `tables-only` | none (Tier-2 named ranges bundled) |
| `gap` | `auto` | `r.source == "gap_detect"` |
| `auto` | `auto` | none |

### Honest scope (v1)

See [docs/tasks/task-010-07-roundtrip-and-references.md](../../docs/tasks/task-010-07-roundtrip-and-references.md)
and the `__init__.py` module docstring for the full TASK §1.4 catalogue.

### Round-trip with json2xlsx (xlsx-2)

Shapes 1 + 2 (flat / dict-of-arrays) are losslessly round-trippable
via `xlsx2json → json2xlsx → xlsx2json` (byte-identical). Shapes 3 + 4
(nested `tables`) are lossy on `json2xlsx` v1 consume — deferred to
xlsx-2 v2 `--write-listobjects`. Live round-trip test:
`scripts/json2xlsx/tests/test_json2xlsx.py::TestRoundTripXlsx8::test_live_roundtrip`.

### Cross-skill replication

**None.** This package is xlsx-specific. The 12-line `diff -q` gate
(CLAUDE.md §2) MUST remain silent.
```

#### File: `docs/office-skills-backlog.md`

**Locate** the `xlsx-8` row. **Update** its status / notes column to
reflect merge (developer fills in at merge time — this task documents
the expected edit shape):

```markdown
| xlsx-8 | `xlsx2csv.py` / `xlsx2json.py` (read-back) ✅ DONE 2026-MM-DD (Task 010 atomic chain 010-01..010-08) | ... [existing description unchanged] ... |
```

> **NOTE:** The developer running this task is the one making the
> final merge — the exact date is the merge-commit date.

### Verification commands (no code change — just CI gates)

#### Gate 1: `validate_skill.py`

```bash
python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx
```

Must exit 0.

#### Gate 2: 12-line `diff -q` silent (ARCH §9.4)

```bash
diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
diff -qr skills/docx/scripts/office skills/pptx/scripts/office
diff -q  skills/docx/scripts/_soffice.py skills/xlsx/scripts/_soffice.py
diff -q  skills/docx/scripts/_soffice.py skills/pptx/scripts/_soffice.py
diff -q  skills/docx/scripts/_errors.py skills/xlsx/scripts/_errors.py
diff -q  skills/docx/scripts/_errors.py skills/pptx/scripts/_errors.py
diff -q  skills/docx/scripts/_errors.py skills/pdf/scripts/_errors.py
diff -q  skills/docx/scripts/preview.py skills/xlsx/scripts/preview.py
diff -q  skills/docx/scripts/preview.py skills/pptx/scripts/preview.py
diff -q  skills/docx/scripts/preview.py skills/pdf/scripts/preview.py
diff -q  skills/docx/scripts/office_passwd.py skills/xlsx/scripts/office_passwd.py
diff -q  skills/docx/scripts/office_passwd.py skills/pptx/scripts/office_passwd.py
```

ALL must produce **no output**.

#### Gate 3: LOC budget

```bash
wc -l skills/xlsx/scripts/xlsx2csv.py skills/xlsx/scripts/xlsx2json.py
# Expected: each ≤ 60 LOC.

find skills/xlsx/scripts/xlsx2csv2json -name '*.py' -not -path '*/tests/*' -exec wc -l {} +
# Expected: total ≤ 1500 LOC (sum of cli + dispatch + emit_json + emit_csv + exceptions + __init__).
```

#### Gate 4: Full xlsx test suite green

```bash
cd skills/xlsx/scripts
./.venv/bin/python -m unittest discover -s xlsx2csv2json/tests
./.venv/bin/python -m unittest discover -s json2xlsx/tests   # round-trip live
./.venv/bin/python -m unittest discover -s md_tables2xlsx/tests
./.venv/bin/python -m unittest discover -s xlsx_check_rules/tests
./.venv/bin/python -m unittest discover -s xlsx_comment/tests
./.venv/bin/python -m unittest discover -s xlsx_read/tests
```

ALL must exit 0.

#### Gate 5: ruff banned-api

```bash
cd skills/xlsx/scripts
ruff check scripts/
```

Must exit 0. Specifically: no `from xlsx_read._workbook import ...` etc.
from `xlsx2csv2json/*.py`.

## Test Cases

### End-to-end Tests

No new E2E added. The full 30-E2E cluster from 010-07 is the
implicit gate.

### Unit Tests

No new unit tests. The gates above are the verification.

### Regression Tests

Gates 1–5 are the regression set.

## Acceptance Criteria

- [ ] `skills/xlsx/SKILL.md` updated: 2 registry rows + §10 honest-scope note.
- [ ] `skills/xlsx/.AGENTS.md` updated: `## xlsx2csv2json` section added.
- [ ] `docs/office-skills-backlog.md` xlsx-8 row marked ✅ DONE
  with the merge date.
- [ ] **Gate 1** (`validate_skill.py skills/xlsx`) exits 0.
- [ ] **Gate 2** (12-line `diff -q`) silent.
- [ ] **Gate 3** (LOC budget) — shims ≤ 60 LOC, package ≤ 1500 LOC.
- [ ] **Gate 4** (full xlsx suite) — green.
- [ ] **Gate 5** (`ruff check scripts/`) — green.

## Notes

- This task introduces **no Python code changes** — only
  documentation + verification. The Developer running it should
  start by running the gates against the post-010-07 state to
  confirm the implementation is ready for merge.
- If any gate fails, the failure mode is to **return to the
  responsible upstream task** (e.g. ruff failure → 010-04 / 010-05 /
  010-06) rather than patching here.
- The backlog row update is **strictly documentation** — the
  developer must use the actual merge-commit date (placeholder
  `2026-MM-DD` in the template).
- The validate_skill.py gate is **not optional** — it verifies the
  Gold Standard structure of `skills/xlsx/`. If it fails, fix the
  structural issue, not the gate.

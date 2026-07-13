# heal-issues run report — 2026-07-13 12:40, DOCX-MERMAID-EXECSYNC

**Mode:** manual (Stage 0 pilot run #2) · **Branch:** `fix/docx-mermaid-execsync` · **Iterations:** 1/3

## Selection (Phase 0)
2 eligible (DOCX-MERMAID-EXECSYNC, XLSX-PREVIEW-PNG-ASSERT) — tied on severity/auto_fixable/
opened_at; deterministic feed-order tie-break → DOCX-MERMAID-EXECSYNC. Preconditions: lock free,
tree clean, on main, config parsed.

## Reproduce (Phase 1) — red before
Stubbed failing `npx` + mermaid fixture in a scratch CWD → `test ! -e temp_1.mmd` → **exit 1**
(predictable temp leaked into CWD).

## Fix (Phase 2, iteration 1)
`skills/docx/scripts/md2docx.js`: per-diagram `mkdtemp` scratch in os.tmpdir (finally-removed),
`execFileSync` argv form (win32 `npx.cmd` ternary), per-file unlinks replaced by scratch rmSync.
NEW `skills/docx/scripts/tests/test_md2docx_mermaid_hygiene.py`: failure path — CWD hygiene +
conversion survives a failed render.

## Gate matrix (all green, iteration 1)
| gate | result |
|---|---|
| issue repro re-run | exit 0 ✓ |
| new regression tests | 2/2 OK ✓ |
| unit suite | 206 tests OK (skipped=9) ✓ |
| e2e `test_e2e.sh` | 155 passed, 0 failed ✓ |
| `validate_skill.py skills/docx` | PASSED ✓ |
| success-path smoke (real mermaid via node_modules mmdc) | PNG embedded, CWD clean, exit 0 ✓ |
| replication | n/a (md2docx.js is docx-only; docx2md.js untouched) ✓ |
| diff guard | md2docx.js +16/−6 + 1 new test file ≤ 300/10 ✓ |

## Review
```sh
git diff main..fix/docx-mermaid-execsync
```

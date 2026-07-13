# heal-issues run report — 2026-07-13 13:00, XLSX-PREVIEW-PNG-ASSERT

**Mode:** manual (Stage 0 pilot run #3) · **Branch:** `fix/xlsx-preview-png-assert` · **Iterations:** 1/3

## Selection (Phase 0)
Single eligible candidate (the other two pilots merged as fixed). Preconditions: lock free,
tree clean, on main.

## Reproduce (Phase 1) — red before
`unittest -k test_single_cell_renders_via_libreoffice` → FAILED:
`b'\xff\xd8\xff\xe0…' != b'\x89PNG…'` (preview.py emits JPEG by contract; the test asserted PNG).

## Fix (Phase 2, iteration 1)
`skills/xlsx/scripts/tests/test_xlsx_add_comment.py` (issue fix path (a), test-only):
assertion → JPEG SOI marker `\xff\xd8\xff`; helper docstring + comments corrected (the
`.preview.png` output name kept deliberately as a realistic user-supplied path — preview.py's
JPEG-regardless-of-extension contract is now stated where it is asserted). `preview.py`
untouched — 4-skill replicated file, its JPEG output is by design.

## Gate matrix (all green, iteration 1)
| gate | result |
|---|---|
| issue repro re-run | exit 0 ✓ |
| unit suite | 522 tests OK (skipped=4) ✓ |
| e2e `test_e2e.sh` | 148 passed, 0 failed ✓ |
| `validate_skill.py skills/xlsx` | PASSED ✓ |
| replication | n/a (test file only; preview.py untouched) ✓ |
| diff guard | 1 file, +11/−6 ≤ 300/10 ✓ |

## Review
```sh
git diff main..fix/xlsx-preview-png-assert
```

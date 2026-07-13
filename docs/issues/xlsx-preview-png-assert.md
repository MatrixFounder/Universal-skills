---
id: XLSX-PREVIEW-PNG-ASSERT
type: known-issue
status: fixed
opened_at: 2026-06-05
resolved_at: 2026-07-13
resolved_by: heal-issues run 2026-07-13 (branch fix/xlsx-preview-png-assert)
category: test
severity: LOW
component: xlsx
slug: xlsx-preview-png-assert
auto_fixable: true
---

# XLSX-PREVIEW-PNG-ASSERT (pre-existing; surfaced by TASK 019 vdd-multi verification)

> **Resolved 2026-07-13 by /heal-issues (manual pilot run #3).** Fix path (a) applied: the
> render-smoke assertion now targets the JPEG SOI marker (`\xff\xd8\xff`) — preview.py's
> documented contract is JPEG regardless of the output extension — with the helper docstring
> and comments corrected to stop re-seeding the PNG confusion. preview.py itself untouched
> (4-skill replicated file, by design). Gates: issue repro green, unit 522 OK, e2e 148/148,
> validate_skill PASSED.

**Status:** DEFERRED (LOW; pre-existing, **not** a TASK 019 regression — proven below).
**Severity:** LOW (test-only; the rendering itself works, the assertion is wrong).
**Location:** [`skills/xlsx/scripts/tests/test_xlsx_add_comment.py`](../../skills/xlsx/scripts/tests/test_xlsx_add_comment.py)
`TestRenderSmoke.test_single_cell_renders_via_libreoffice` (+ `_render_to_png` helper).
**Symptom:** the test renders an `.xlsx` via `preview.py` to a `*.preview.png` path and
asserts a PNG magic header (`\x89PNG\r\n\x1a\n`), but `preview.py` **always emits JPEG**
(`canvas.save(output, "JPEG", …)` — JPEG is its documented output format, regardless of
the output path's extension). So `f.read(8)` sees `\xff\xd8\xff\xe0` and the assertion
fails. Only fires where LibreOffice is installed (otherwise the render path is unavailable).
**Proven pre-existing (not TASK 019):** `git diff HEAD -- skills/xlsx/scripts/preview.py`
shows TASK 019 added **only** the 3-line self-bootstrap prelude; the `save(…, "JPEG", …)`
line is unchanged from HEAD (`git show HEAD:…/preview.py` → same JPEG save). The test
asserts PNG identically before and after TASK 019.
**Fix path (xlsx-skill, separate from TASK 019):** either (a) assert JPEG magic
(`\xff\xd8\xff`) — `preview.py`'s contract is JPEG; or (b) render to a `.jpg` path and
rename the helper. One-line test change; no `preview.py` change (its JPEG output is by
design, and it is a 4-skill replicated file).
**Do-not:** attribute this failure to TASK 019 — the bootstrap prelude does not touch
`preview.py`'s image-format logic.

## Reproduction

Requires LibreOffice (the render path is skipped without it). Red = `FAILED` with the
`b'\xff\xd8\xff\xe0…' != b'\x89PNG…'` header mismatch; green after the assert targets JPEG.

```sh
cd skills/xlsx/scripts
./.venv/bin/python -m unittest discover -s tests -p 'test_xlsx_add_comment.py' -k test_single_cell_renders_via_libreoffice
```

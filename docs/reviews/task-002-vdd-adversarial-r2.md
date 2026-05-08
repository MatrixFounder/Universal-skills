# VDD Critique: Task-002 hot-fix `<legacyDrawing>` anchor + render-smoke (Round 2)

> **Scope:** the post-Task-002 hot-fix that landed `ensure_sheet_legacy_drawing_ref`
> + wiring + `TestLegacyDrawingAnchor` (3 tests) + `TestRenderSmoke`
> (2 skipIf-gated tests) + 3 regenerated goldens + `docx_add_comment.py`
> audit.
>
> **Method:** VDD Adversarial — Forced Negativity, Anti-Slop Bias,
> Failure Simulation. Convergence Signal exit when concrete claims fail
> inspection.

## 1. Executive Summary

- **Verdict:** **PASS** — no HIGH or MED issues; 2 LOW observations are
  documentation-grade only.
- **Confidence:** High. Adversary read each touched file end-to-end,
  unzipped all 5 golden files to verify `<legacyDrawing>` placement,
  inspected `with_legacy.xlsx` fixture rels, and traced the
  `RuntimeError`-unreachable claim through `ensure_vml_drawing`'s
  reuse path.
- **Summary:** All 8 hot-spots from the focused brief produced no
  defect. `--date` value used to regenerate goldens (`2026-01-01T00:00:00Z`)
  matches `test_e2e.sh:1361` exactly. `docx_add_comment.py` audit
  holds — anchors are inline in `word/document.xml`, no analogous
  two-level indirection.

## 2. Risk Analysis

| Severity | Category | Issue | Impact | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **LOW** | Idempotency edge | `ensure_sheet_legacy_drawing_ref` (`ooxml_editor.py:875`) on a workbook with pre-existing `<legacyDrawing r:id="X"/>` pointing at a different VML rel will silently overwrite `r:id`. | None on supported inputs — `ensure_vml_drawing` reuses the existing rel via `_find_rel_of_type` (line 602), so the rId we pass IS the existing one. Verified on `with_legacy.xlsx` (`r:id="anysvml"` in BOTH sheet1.xml and rels). Theoretical issue only with hand-crafted workbooks where the rels target was deleted but `<legacyDrawing>` was left dangling. | **Lock invariant with comment.** ✅ Applied. |
| **LOW** | Multi-VML lookup | `_vml_rel_id` (`cli.py:82`) returns the first `vmlDrawing` rel found. A workbook with two pre-existing VML drawings on the same sheet (rare; Excel never emits this; possible from third-party authoring) would bind `<legacyDrawing>` to the wrong one. | Negligible — Excel emits at most one `vmlDrawing` rel per sheet; our writer never creates a second; `_find_rel_of_type` reuses any existing rel. | **Lock invariant with comment.** ✅ Applied. |

### Other concerns traced and dismissed

| Concern | Resolution |
| :--- | :--- |
| `RuntimeError` reachability in `_vml_rel_id` | Truly unreachable: `ensure_vml_drawing` either reuses an existing rel via `_find_rel_of_type` (rel was loaded by `_open_or_create_rels` → still in `sheet_rels_root`), or calls `_patch_sheet_rels` to create one. Verified at `ooxml_editor.py:602–642`. |
| Schema ordering of `_AFTER_LEGACY_DRAWING_ELEMENTS` | Correctly omits `<drawing>` because per ECMA-376 §18.3.1.99 `<drawing>` PRECEDES `<legacyDrawing>`. Append-at-end branch is reachable only when none of the post-`<legacyDrawing>` siblings exist, which means appending lands in the schema-correct slot. |
| Goldens regeneration honesty | All 5 goldens pass `T-golden-*` (`bash test_e2e.sh` → 112 passed, 0 failed). 3 regenerated May 8 (`clean-no-comments`, `threaded`, `multi-sheet`); 2 unchanged (`existing-legacy-preserve`, `idmap-conflict` use `with_legacy.xlsx` which already had `<legacyDrawing>`, so the fix was a no-op idempotent update). `--date 2026-01-01T00:00:00Z` matches `test_e2e.sh:1361` exactly. |
| `TestRenderSmoke` 1024-byte threshold | Conservative-safe. Real LibreOffice renders of empty-ish workbooks produce 10–50 KB PNGs. 1024 catches corrupt/empty outputs (< 100 bytes) without false-flagging legitimate small renders. |
| `addprevious()` namespace handling | Empirically correct: `multi-sheet.golden.xlsx` sheet2.xml emits `<legacyDrawing xmlns:ns1="…/relationships" ns1:id="rId2"/>` — Excel/LibreOffice accept both `r:` and `ns1:` prefixes (XML-namespace-equivalent). |
| `docx_add_comment.py` audit | Confirmed immune. `commentRangeStart/End/Reference` are inline in `word/document.xml`; no analogous two-level "rel exists but no body anchor" failure mode. Footnotes/endnotes/headers/footers each anchor inline via their own reference elements, but `docx_add_comment.py` only writes comments — out of scope. |

## 3. Hallucination Check

- [x] **Files cited exist:** all 11 cited paths (3 source, 2 test, 1 e2e shell, 5 goldens) verified by direct read or unzip.
- [x] **Line numbers verified:**
    - `ooxml_editor.py:831-834` — `_AFTER_LEGACY_DRAWING_ELEMENTS` tuple ✓
    - `ooxml_editor.py:837-893` — `ensure_sheet_legacy_drawing_ref` body ✓
    - `ooxml_editor.py:602-642` — `ensure_vml_drawing` rel reuse path ✓
    - `cli.py:82-97` — `_vml_rel_id` (the RuntimeError raise) ✓
    - `cli.py:269-275` — single_cell_main call site ✓
    - `cli.py:559-563` — batch_main call site ✓
    - `test_xlsx_add_comment.py:901-985` — `TestLegacyDrawingAnchor` (3 tests) ✓
    - `test_xlsx_add_comment.py:988-1081` — `TestRenderSmoke` (2 skipIf-gated) ✓
    - `test_e2e.sh:1378-1401` — 5 `run_golden` invocations ✓
- [x] **Empirical verification:**
    - 90/90 unit tests pass (2 render-smoke cleanly skipped on this host: `soffice` not on PATH).
    - 112/112 E2E pass.
    - All 5 golden files contain `<legacyDrawing>` after the fix (verified by unzip + grep).
    - `with_legacy.xlsx` confirmed to carry pre-existing `<legacyDrawing r:id="anysvml"/>` — idempotent-update branch is exercised on this fixture, not just theory.

## 4. Decision

**Convergence Signal: REACHED.** The Adversary was forced into
documentation-grade observations (idempotency edge that's unreachable
on real Excel-emitted inputs; multi-VML edge that Excel itself never
produces). No concrete defect surfaces inspection.

The two LOW observations are worth locking with `# INVARIANT:`
comments in code so the architectural assumption ("Excel emits ≤1
vmlDrawing rel per sheet, and the rels reuse path keeps `<legacyDrawing>`
in sync with its actual VML target") is preserved against future
contributors.

```json
{"review_status": "APPROVED", "has_critical_issues": false, "stubs_replaced": true, "e2e_tests_pass": true}
```

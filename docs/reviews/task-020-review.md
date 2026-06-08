# Task Review — TASK 020 (pptx2md)

**Date:** 2026-06-08
**Reviewer:** task-reviewer (independent VDD gate)
**Target:** `docs/TASK.md` (TASK 020 — pptx → Markdown conversion)
**Status:** APPROVED WITH COMMENTS

> Persisted by the orchestrator on behalf of the `task-reviewer` subagent (which
> runs read-only). All 5 MAJOR + 4 MINOR below were folded into `docs/TASK.md`
> during the analysis loop; see the Open Questions note in the spec.

## General Assessment

Strong, well-structured specification. Real RTM (5 epics, 18 requirements, ≥3
sub-features each), five complete use cases (Actors / Preconditions / Main /
Alternatives / Postconditions / Acceptance Criteria), explicit non-functional
requirements, constraints, and a correctly-scoped Open Questions section that does
not re-litigate the three settled decisions. Verified reuse claims:

- **`_errors.py` read-only reuse** is correct — CLAUDE.md §2 lists it as a 4-skill
  replicated file; consuming it without editing triggers no replication. ✓
- **`pptx2md.py` not cross-skill replicated** is correct — not in any `diff -q` set,
  like `xlsx2md/`. ✓
- **xlsx-9 precedent** is real and apt: `xlsx2md/cli.py` demonstrates the
  atomic-write (`.partial` → `os.replace`), self-overwrite guard (code 6), terminal
  `InternalError` redaction, `_errors` envelope discipline. ✓
- **pptx-5 backlog** exists and matches R-D1/UC-5. ✓
- **Scripted converter (vs the pdf skill's deliberate non-scripting)** is the right
  call: pptx carries a semantic shape model like xlsx, not positioned glyphs. ✓
- **Tesseract-direct (not ocrmypdf)** sidesteps the ghostscript/AGPL chain. ✓

No blocking issues.

## 🔴 CRITICAL (BLOCKING)
None.

## 🟡 MAJOR

- **MAJOR-1 — Encrypted vs legacy-`.ppt` split contradicts the shared helper.**
  R-D3/UC-3 promised two distinct error types (`EncryptedInput` / `LegacyPptInput`),
  but `office._encryption.assert_not_encrypted` raises a single `EncryptedFileError`
  and deliberately does not discriminate; `pptx_to_pdf.py` already uses
  `EncryptedFileError`/code 3. **Fix:** reuse the helper, single type, message names
  both. *(Folded in.)*
- **MAJOR-2 — OCR blob→text mechanism unspecified + dependency claim inconsistent.**
  `pytesseract` is not a known dep; pptx has no `--with-ocr`/`requirements-ocr.txt`;
  THIRD_PARTY_NOTICES attributes tesseract to pdf only. **Fix:** pin the mechanism
  (subprocess on a temp PNG, no new Python dep), make the notices/install updates
  unconditional. *(Folded in.)*
- **MAJOR-3 — Image dedup-by-hash conflicts with positional naming + idempotency.**
  **Fix:** first-occurrence-wins tie-break tied to the determinism rule. *(Folded.)*
- **MAJOR-4 — stdout mode leaves the media link-base undefined.** **Fix:** define
  the stdout link base (relative to `--media-dir` from CWD) + AC. *(Folded.)*
- **MAJOR-5 — Performance NFR has no measurable budget.** **Fix:** measured baseline
  on `slodes-3`, OCR cost model, serial-vs-`--jobs`, per-image timeout. *(Folded.)*

## 🟢 MINOR

- **MINOR-1 — title-first vs strict-document-order ambiguity.** *(Folded: R-A2a.)*
- **MINOR-2 — `.pptm` "macros ignored" reuse note slightly off** (pack-time helper
  vs read-time). *(Folded: R-D3c.)*
- **MINOR-3 — OCR exit-code parity is pdf-style (1), encrypted is pptx-style (3) —
  confirm intended hybrid.** *(Folded: exit-code map in NFR.)*
- **MINOR-4 — preserve the real `slodes-3` typo; do not "fix" to `slides-3`.**
  *(Folded: R-E3c.)*

## Final Recommendation

**APPROVED WITH COMMENTS.** Proceed to Architecture; the Architect must resolve
MAJOR-1..5 as design decisions and fold the MINOR items into the same pass.

```json
{"review_file":"docs/reviews/task-020-review.md","has_critical_issues":false,"major_count":5,"minor_count":4,"summary":"APPROVED WITH COMMENTS — solid RTM/UC/reuse claims verified; 5 MAJOR design gaps for the Architect; no blockers."}
```

# Architecture Review — TASK 020 (`pptx2md`, pptx → Markdown converter)

- **Date:** 2026-06-08
- **Reviewer:** architecture-reviewer (independent VDD gate)
- **Target:** `docs/ARCHITECTURE.md` (TASK 020 revision, 482 lines, living doc)
- **Status:** **APPROVED WITH COMMENTS** (no BLOCKING; 3 MAJOR; 6 MINOR)

> Persisted by the orchestrator on behalf of the `architecture-reviewer` subagent
> (read-only). The 3 MAJOR + applicable MINOR were applied to `docs/ARCHITECTURE.md`
> after this review; see the orchestrator's follow-up edits.

## General Assessment

Strong, mature architecture — the correct pptx analogue of `xlsx2md/`: a
deterministic, scripted OOXML→Markdown converter built on an explicit
`Deck→Slide→Block` document model with a clean `extract → (images, ocr) → emit`
pipeline. All five MAJOR findings delegated by the task review are genuinely
resolved and were verified against the real codebase:

- **MAJOR-1 RESOLVED** — `office._encryption.assert_not_encrypted` raises exactly one
  `EncryptedFileError` (`_encryption.py:83-89`); `pptx_to_pdf.py:42-46` maps it to
  exit 3. D-6 parity is byte-accurate.
- **MAJOR-2 RESOLVED** — `pdf_ocr.py` is an `ocrmypdf` wrapper (`:217-234`); the
  architecture reuses only the engine + `eng+rus` default + probe conventions, not
  the ocrmypdf path. AGPL-clean is sound (Ghostscript is pulled only by ocrmypdf;
  Tesseract is Apache-2.0). THIRD_PARTY_NOTICES Tesseract row is `pdf`-only and the
  required `pptx` add is correctly identified.
- **MAJOR-3 RESOLVED** — first-occurrence-wins on lowest `(slide, shape)` reconciles
  positional naming with `sha1`-keyed dedup; I-1 is well-formed, locked by run-twice-diff.
- **MAJOR-4 RESOLVED** — D-7/§5.1 give the file/stdout link-base split.
- **MAJOR-5 RESOLVED** — §8/R-E3c record a `slodes-3` baseline as the regression
  ceiling; `--jobs`/`--ocr-timeout` bound the OCR cost model.

python-pptx APIs used coherently (`Picture.image`, `GroupShape.shapes` recursion,
`slide.shapes.title`, `has_notes_slide`). §9 "EMPTY" replication footprint holds:
nothing under `scripts/pptx2md/` is in any CLAUDE.md §2 diff set; the two shared
files are imported read-only. D-2 (self-bootstrap the NEW entrypoint) is consistent
with TASK-019's deferral (scoped to pre-existing CLIs). Security is solid: argv-no-
shell (avoids `DOCX-MERMAID-EXECSYNC`), `mkstemp` 0600, timeout, redacted
InternalError; python-pptx's parser sets `resolve_entities=False` (XXE structurally
off). Living-doc discipline compliant: 482 ≤ 1500, in-place, TASK 019 archived, no
snapshot.

## 🔴 CRITICAL (BLOCKING)
None.

## 🟡 MAJOR

- **AR-1 — `shape.image.ext`/`.content_type` raise on EMF/SVG/video before the
  placeholder branch.** `Image.ext` raises `ValueError` for formats outside
  `{BMP,GIF,JPEG,PNG,TIFF,WMF}` (so EMF/SVG raise); `.content_type`/`_pil_props`
  call `PIL.Image.open` → `UnidentifiedImageError` on EMF/WMF/SVG/video/corrupt.
  `.sha1` is the only safe accessor (direct hashlib). `Picture.image` itself raises
  `ValueError` when `blip_rId is None`; Movie/audio are `MEDIA` shape_type.
  **Fix:** classify on `shape.shape_type` first; guard `.ext`/`.content_type` (degrade
  to placeholder on `ValueError`/`UnidentifiedImageError`/`KeyError`); key
  `PlaceholderAsset` by `(slide, shape)` (no `ext`/`sha1`). Makes R-B3 achievable.
- **AR-2 — "Pillow not used for extraction" is false.** Reading `.ext`/`.content_type`
  at extraction time routes through `_pil_props` → `PIL.Image.open`. Pillow is an
  extraction-time dep (already pinned). **Fix:** correct §6 and FC-2 wording.
- **AR-3 — Exit-code map omits `InternalError`.** §5.1 enumerates `0/1/2/3/6` but
  S-3's terminal redacted `InternalError` has no code; `xlsx2md`→7, `pdf_ocr`→1.
  **Fix:** assign + justify (recommend **1**, matching the hybrid-parity logic and
  `pdf_ocr`).

## 🟢 MINOR

- **AR-4 — stale citation:** `docs/reviews/task-020-review.md` did not exist at review
  time. **Fix:** persist it (done by orchestrator).
- **AR-5 — mislabeled cross-ref:** "TASK-019 D-A6" — D-A6 is a TASK-018/pdf label;
  the TASK-019 deferral is its "Deferred (not this task)" note + OQ-1. **Fix:** relabel.
- **AR-6 — hidden-slide filter has no public python-pptx API:** requires raw lxml
  `slide._element.get("show")`. **Fix:** note the private-API path + lock with a test.
- **AR-7 — `slide.notes_slide` create-on-access side effect:** guard with
  `if slide.has_notes_slide:` and null-check `notes_text_frame`.
- **AR-8 — non-existent `tmp8/slides-5.pdf`:** the file is `slides-5.pptx` (in scope);
  also an unlisted `FRAMEWORK_WEBINAR.marp.pptx`. **Fix:** correct the corpus.
- **AR-9 — version claim:** `requirements.txt` pins `>=0.6.23`, installed is 1.0.2.
  **Fix:** reword "pinned >=0.6.23; verified against installed 1.0.2"; consider
  raising the floor to `>=1.0.2`. Note `tesseract --list-langs` prints to stdout OR
  stderr depending on build (`pdf_ocr.py:264` parses both); the planner should too.

## Final Recommendation

**Proceed to Planning** after the Architect applies AR-1/AR-2/AR-3 (small in-place
edits) and folds AR-4..AR-9. The §11 Atomic-Chain Skeleton is a clean Stub-First
handoff; add an EMF/SVG-placeholder unit test (AR-1) and an `InternalError`-exit-code
regression test (AR-3) to bead 020-01's RED scaffolding. Data model, security,
replication boundary, and living-doc discipline are sound.

```json
{"review_file":"docs/reviews/architecture-020-review.md","has_critical_issues":false,"major_count":3,"minor_count":6,"summary":"APPROVED WITH COMMENTS — all 5 task-review MAJORs verified resolved; 3 MAJOR (image.ext raises pre-placeholder; Pillow-extraction wording; InternalError exit code) + 6 MINOR; no BLOCKING."}
```

# TASK 021 — pptx2md OCR noise reduction (`--ocr-denoise`)

**Status:** Done — implemented & dogfooded (91 unit tests, validate PASS, e2e 48/0;
adversarial logic-review applied). Not yet committed.
**Skill:** `pptx` (package `skills/pptx/scripts/pptx2md/`)
**Predecessor:** TASK 020 (`pptx2md` MVP + WMF→inline-PNG) — DONE & archived.
**Scope boundary (user-approved 2026-06-09):** `pptx2md` **only**. The pdf skill's
OCR (`pdf_ocr.py`) is a *different engine* (ocrmypdf, whole-page, output owned by
ocrmypdf / `--sidecar`) and is explicitly a **separate future TASK** — see §6.

---

## 1. Problem (from dogfooding + a corpus-wide OCR-quality audit)

`pptx2md --ocr` calls system `tesseract` **directly per image** and writes the
recovered text straight into the `.md` as a `<!-- ocr -->` blockquote. An
image-vs-OCR audit of the whole `tmp8` corpus (7 decks, one verifier agent per
deck, spot-checking the rendered PNG against its OCR block) confirmed **all
substantive body/heading text is recovered well** — but it also surfaced three
classes of **visible noise** in the output:

| Class | Observed example | Root cause |
|---|---|---|
| **N1 — tiny decorative images** | slides-3: 7/103 OCR blocks were garbage (`SS}`, `Xn`, `</>`) — each a <4 KB line-art icon | tesseract emits junk from icon/glyph edges |
| **N2 — text-free / low-contrast images** | slides-2: a blank banner OCR'd to `io / С Annelise / GSiercicne` | no real text in the image → low-confidence junk |
| **N3 — repeated identical blocks** | slides-2: the SAME banner (one sha1) linked on 6 slides → **6 identical** noise blocks | per-`ImageRef` emission of a shared asset's OCR |

None of this LOSES content — it ADDS noise. The substantive text is intact, so
any filtering must be **strictly subtractive of noise, never of real text**, and
must be **opt-in** so the current (verified-good) default output never changes
silently.

## 2. Goal

Add an **opt-in** noise-reduction mode `--ocr-denoise` (OFF by default) that
applies the three highest-leverage, lowest-risk filters identified in the OCR
best-practices review (top 1–3):

- **R1 — size-gate (addresses N1):** skip OCR on images whose pixel dimensions
  are below a threshold (decorative icons/glyphs are never body text).
- **R2 — confidence-gate (addresses N2):** run tesseract in **TSV** mode, keep
  per-word results at/above a confidence threshold, and drop a whole block when
  fewer than two confident words survive (the noise discriminator is the *count* of
  confident words, not their mean — see R2 in §3).
- **R3 — dedup (addresses N3):** suppress emitting an OCR block whose text is
  identical to one already emitted earlier in the document.

## 3. Requirements & RTM

| ID | Requirement | Acceptance / test |
|---|---|---|
| **R1** | `--ocr-denoise` + `--ocr-min-px N` (default 48): when denoise on, `ocr_asset` returns `""` for an image whose **min(width,height) < N** → no block emitted. | TC-1: a 32×32 blob → `""`; a 600×400 blob → OCR runs. Dogfood: slides-3 icon-noise blocks gone. |
| **R2** | `--ocr-denoise` + `--ocr-min-confidence C` (default 50): tesseract runs with `tsv`; words with `conf < C` are dropped, and the **block is dropped only when fewer than 2 such words survive** (calibration finding — a *mean*-confidence gate wrongly dropped dense real screenshots whose UI chrome drags the mean down; the real discriminator is the *count* of confident words: a noise banner has ≤1, a real screenshot dozens). Text reconstructed from the survivors (which also strips low-conf garble inside kept blocks). | TC-2: mixed-conf TSV → garble stripped, real words + line structure kept; ≤1 confident word → `""`. Dogfood: slides-2 banner gone, real screenshots kept. |
| **R3** | Under `--ocr-denoise`, an OCR block whose **normalized text** was already emitted is suppressed (first occurrence wins). | TC-3: same OCR text on 3 ImageRefs → emitted once. Dogfood: slides-2 6→1. |
| **R4 — no silent change** | With `--ocr-denoise` ABSENT, output is **byte-identical** to pre-TASK behaviour: `ocr_asset` keeps the plain `tesseract … stdout` text path; emit does no dedup. | TC-4: existing OCR E2E/unit assertions unchanged; a golden-text test proves the default path is untouched. |
| **R5 — never crash (AR-1)** | A malformed/empty TSV, an unreadable tiny image, or a threshold edge case degrades to the documented behaviour (skip/`""`), never an exception that aborts the deck. | TC-5: garbage TSV → `""` + warning, deck continues; size check on an undecodable blob → existing fallback. |
| **R6 — determinism** | Same input + same flags → byte-identical `.md` (filters are pure functions of the OCR result + thresholds). | TC-6: run-twice idempotency holds under `--ocr-denoise`. |
| **R7 — soft-optional** | No new runtime dependency; TSV parsing is stdlib; thresholds without `--ocr-denoise` are documented no-ops. | TC-7: `--ocr-min-confidence` alone (no `--ocr-denoise`) does not change output. |
| **R8 — docs + dogfood** | `references/pptx-to-markdown.md`, `ARCHITECTURE.md` (new D-entry), `.AGENTS.md` updated; re-export tmp8 with `--ocr --ocr-denoise` and report the noise-block delta. | Before/after counts of empty/noise blocks per deck. |

## 4. Honest scope / non-goals (v1)

- **No image preprocessing** (binarize / upscale / deskew) — best-practice #4/#5;
  helps *garble* not *noise*, and risks hurting already-clean screenshots. Deferred.
- **No `--psm` tuning, no lexical/dictionary gate, no LLM post-correction** —
  the dictionary gate risks cutting short real text; the LLM pass breaks
  determinism and can hallucinate (already observed: tesseract invented a
  "В 3,2 раза" line on slides-6). Out of scope.
- **Confidence-gate is best-effort:** tesseract's per-word `conf` is heuristic;
  the goal is removing obvious junk, not a precision OCR re-rank.
- **`min_words=2` trade-off (honest):** a genuinely **single-word** image (a one-word
  sign/label) is treated as noise and dropped under `--ocr-denoise` — the "never drop
  real text" rule holds for *multi-word* text; a lone word is indistinguishable from a
  one-token logo. Opt-in + documented in CLI help. Omit `--ocr-denoise` to keep it.
- **Dedup keys on the CLEANED text** (post-confidence-gate), document-global and
  text-identical only (no fuzzy match). So two *different* source images that reduce
  to the same surviving words collapse to one OCR block — the image **link** still
  renders on each slide, only the duplicate blockquote is suppressed.

## 5. Risks

- **False-negative on real text** (filter eats a legitimate short label). Mitigated
  by: opt-in (default off), conservative defaults (px 48 / conf 50), and a dogfood
  check that no audited-substantive text disappears.
- **TSV path divergence** from the `stdout` path. Mitigated by keeping the plain
  `stdout` path as the default and only switching to TSV under `--ocr-denoise`.

## 6. Deferred sibling task (pdf) — recorded, NOT in this TASK

`pdf_ocr.py` delegates to **ocrmypdf** (whole-page, searchable-PDF/`--sidecar`
output). The top-1-3 filters do **not** translate (no per-embedded-image unit; we
don't own the text). The pdf analogue of "noise best practices" is **passing
through ocrmypdf's existing image-cleanup flags** (`--clean`/unpaper, `--deskew`,
`--rotate-pages`, `--threshold`) — a small, separate enhancement with a different
mechanism. Track as a future pdf-skill task; do not bundle here.

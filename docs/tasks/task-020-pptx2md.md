# TASK 020 — pptx → Markdown conversion (`pptx2md`)

> **STATUS: ✅ DONE (2026-06-08).** Delivered via VDD: analysis → architecture →
> plan → `/vdd-develop-all` (6 atomic beads, per-bead adversarial roast) →
> `/vdd-multi` (3-critic verification, all converged). 63 unit + E2E + legacy
> `test_e2e.sh` (48) all green; `validate_skill` PASS; §9 replication matrices silent.
> Ships `skills/pptx/scripts/pptx2md/` (cli/extract/images/ocr/emit/model/exceptions)
> + shim. Reviews: [task](../reviews/task-020-review.md) · [architecture](../reviews/architecture-020-review.md)
> · [plan](../reviews/plan-020-review.md). Not committed (user controls commit).

### 0. Meta Information (MANDATORY)
- **Task ID:** 020
- **Slug:** `pptx2md`
- **Skill:** `skills/pptx/` (PowerPoint office skill — Proprietary license scope)
- **Mode:** VDD (Verification-Driven Development)
- **Execution mode:** `script-first` (Python CLI, mirrors `xlsx-9` / `xlsx2md`)
- **License scope:** Proprietary, All-Rights-Reserved (one of the four office skills).
- **Dogfood corpus (AR-8 — re-checked 2026-06-08; 6 decks, NO PDF):** `tmp8/` —
  **text-rich:** `slides-1.pptx` (2 sl / 6 pics), `slides-2.pptx` (6 sl / 9 pics / 7
  groups), `slides-4.pptx` (21 sl / 19 pics), `slodes-3.pptx` (82 sl / 231 pics / 2
  tables / 13 groups) [sic — real typo, do not "fix" to `slides-3`]; **image-only
  (the `--ocr` cases):** `slides-5.pptx` (3 sl / 0 text chars / 1 pic),
  `FRAMEWORK_WEBINAR.marp.pptx` (19 sl / 0 text chars / marp background-image deck).
  There is **no** `slides-5.pdf` (an earlier session snapshot showed one; the user
  replaced it). PDF→Markdown remains the `pdf` skill's job, but it is not exercised
  here because tmp8 has no PDF.

---

### 1. General Description

Add a `pptx → Markdown` converter to the **pptx** skill so an agent can turn an
existing `.pptx`/`.pptm` deck into a structured, LLM-/RAG-friendly Markdown
document in one command. This is the **read-back** counterpart to the existing
`md2pptx.js` write path, and it closes the same gap `xlsx-9` (`xlsx2md`) closed
for spreadsheets: a deterministic, scripted extraction that does not regress on
reading order, bullet nesting, or table structure the way ad-hoc `python-pptx`
hand-coding does.

**Goal:** `python3 scripts/pptx2md.py INPUT.pptx [OUTPUT.md]` emits Markdown with
one section per slide (title → heading, body text → nested bullets, tables → GFM,
images → links into a sidecar media folder, optional speaker notes), and an
**opt-in `--ocr`** mode that recovers text baked into images using the **same OCR
engine the pdf skill is built on (tesseract, `eng+rus` default)**.

**Connection with existing system:**
- Lives at `skills/pptx/scripts/pptx2md.py` (+ supporting module(s)). **Not**
  cross-skill replicated — it is pptx-specific, exactly as `xlsx2md/` is
  xlsx-specific (CLAUDE.md §2 "Cross-skill scripts" does NOT list it).
- **Consumes** the already-shared `scripts/_errors.py` `--json-errors` envelope
  (schema `v=1`) — read-only reuse, the file is NOT modified (so no 4-skill
  replication is triggered).
- Extraction engine is **python-pptx 1.0.2** (already in
  `skills/pptx/scripts/requirements.txt`) + lxml/Pillow (already present).
- OCR **reuses the engine and conventions of the pdf skill's OCR**
  (`skills/pdf/scripts/pdf_ocr.py`): system `tesseract`, default language set
  `eng+rus`, soft-optional/never-bundled, fail-loud-with-remediation. It calls
  `tesseract` **directly on extracted image blobs** (NOT via `ocrmypdf`/PDF) —
  this is the user-confirmed per-image approach that preserves slide↔image
  structure (a whole-deck pptx→pdf→ocrmypdf route would flatten to per-page text).

---

### 2. Requirements Traceability Matrix (RTM)

Granularity: ≥ 3 sub-features per requirement. **MVP?** marks the minimum
shippable surface (Epics A, B, D-core, E-core).

#### Epic A — Core pptx → Markdown extraction (python-pptx)

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R-A1** | Slide segmentation & ordering | ✅ | (a) one `## Slide N` section per slide in presentation order; (b) iterate shapes in document/z-order; (c) recurse into GROUP shapes (dogfood: slides-2 has 7, slodes-3 has 13); (d) skip hidden slides by default, `--include-hidden` to keep. |
| **R-A2** | Title & heading mapping | ✅ | (a) the slide's title placeholder → `### <title>` emitted **first**, directly under `## Slide N`, **regardless of its XML/z-order position** (MINOR-1 ordering fix); (b) non-title placeholders kept as body; (c) empty/whitespace titles produce no heading (no `### ` orphan). |
| **R-A3** | Body text & bullet nesting | ✅ | (a) text-frame paragraphs → Markdown; (b) paragraph `level` (0–8) → nested `-` bullet indentation; (c) preserve paragraph breaks; (d) collapse runs to plain text (bold/italic best-effort, not required for MVP); (e) blank paragraphs do not emit empty bullets. |
| **R-A4** | Table extraction → GFM | ✅ | (a) `graphicFrame` tables → GFM pipe tables (dogfood: slodes-3 has 2 tables); (b) first row treated as header; (c) escape `\|`, newlines→`<br>` inside cells; (d) merged cells rendered best-effort (anchor value, blanks for spanned — honest-scope documented). |
| **R-A5** | Reading-order determinism | ✅ | (a) identical input → byte-identical output (idempotent); (b) **ordering rule (documented):** title placeholder first (R-A2a), then all remaining shapes in document order, recursing into groups depth-first in document order; (c) no reliance on dict/set iteration order; (d) this rule is the single source of truth for image naming (R-B1b) and dedup tie-break (R-B1d). |

#### Epic B — Image handling (sidecar media folder + links)

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R-B1** | Image extraction to sidecar | ✅ | (a) each PICTURE blob written to a sidecar dir (default `<output-stem>.media/`, override `--media-dir DIR`); (b) deterministic names `slide{N}-img{M}.{ext}` where `(N,M)` follow the R-A5 ordering rule; (c) extension from the part content-type / blob sniff; (d) **dedup tie-break (MAJOR-3 fix):** identical blobs are written **once** under the name of their **first occurrence** (lowest `(slide-index, shape-index)` per R-A5); every later occurrence **links to that same canonical file** — so naming and dedup are both deterministic and R-A5 idempotency holds. |
| **R-B2** | Image links in Markdown | ✅ | (a) `![<alt>](<relative-media-path>)` at the image's position in reading order; (b) alt text from shape name / alt-text attr, fallback `image`; (c) **link base (MAJOR-4 fix):** in file mode the path is relative to the `.md`; in stdout mode it is relative to `--media-dir` as resolved from CWD (and a one-line stderr note reports where media was written). |
| **R-B3** | Unsupported / pathological media | ✅ | (a) EMF/WMF/SVG and video/audio parts → placeholder marker + warning (not a hard failure); (b) zero-byte / unreadable blob → warning, skip, continue; (c) `--no-images` to suppress extraction entirely (text+tables only). |

#### Epic C — OCR (opt-in; per-image tesseract; reuse pdf-skill engine)

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R-C1** | Opt-in `--ocr` flag | ✅ (flag) / ⛔ (engine soft-optional) | (a) OCR **off by default**; (b) `--ocr` enables per-image OCR; (c) `--ocr-lang LANGS` (default `eng+rus`, mirrors `pdf_ocr.py`); (d) without `--ocr` the tool never needs tesseract and pulls in **no** OCR dependency. |
| **R-C2** | Engine probe & fail-loud | ✅ | (a) on `--ocr`, probe `tesseract` on PATH **once**; (b) missing engine → exit 1 `OcrEngineUnavailable` with the same remediation style as `pdf_ocr.py` (never silent); (c) requested language not installed (`tesseract --list-langs`) → exit 1 `LanguagePackMissing` naming the missing language. |
| **R-C3** | Invocation mechanism (MAJOR-2 fix) | ✅ | (a) OCR is a **direct `subprocess` call to the system `tesseract` binary** on a temp PNG (Pillow already a dep for the blob→PNG normalisation) — argv-list form, **no shell string** (avoids the `DOCX-MERMAID-EXECSYNC` class); (b) **no new Python dependency** — `pytesseract` is deliberately NOT added; (c) **`ghostscript`/`ocrmypdf` are NOT pulled in** (they are PDF-page tooling and AGPL via `gs`); this is the license-clean reuse of just the tesseract engine. |
| **R-C4** | Per-image OCR placement | ✅ | (a) recovered text inserted **directly under that image's link**, marked so it is distinguishable from authored text (default: an `<!-- ocr -->`-tagged blockquote — human-readable + greppable); (b) empty/whitespace OCR result emits nothing (no empty markers); (c) per-image failure or `--ocr-timeout` expiry → warning, skip that image, continue (one bad image never aborts the deck); (d) deduped images (R-B1d) are OCR'd **once** (cached by canonical file). |
| **R-C5** | Honest scope of OCR | ✅ | (a) tesseract is **not bundled** (detected, never installed by us); (b) docs state it reuses the pdf skill's engine/conventions but is a direct per-image call, NOT `ocrmypdf`; (c) OCR text is best-effort, no layout reconstruction. |

#### Epic D — Speaker notes, CLI surface & robustness

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R-D1** | Speaker-notes export | ✅ | (a) notes slide text emitted per slide when present (backlog **pptx-5**); (b) default include as a marked `> **Notes:**` block under the slide; (c) `--no-notes` to suppress; (d) decks with no notes emit nothing (dogfood decks have zero notes — must not emit empty blocks). |
| **R-D2** | CLI contract & output modes | ✅ | (a) `pptx2md.py INPUT [OUTPUT] [flags]`; (b) `OUTPUT` omitted or `-` → stdout (media still written to `--media-dir`, default beside CWD, with a stderr note — R-B2c); (c) `--json-errors` envelope on every failure path (consume shared `_errors.py`); (d) `--help` works with no positional args; (e) OCR perf knobs (MAJOR-5): `--jobs N` (default 1 = serial) and `--ocr-timeout SEC` (per-image, default e.g. 120). |
| **R-D3** | Input guards (reuse the shared helper, MAJOR-1 fix) | ✅ | (a) reuse `office._encryption.assert_not_encrypted` → a **single** `EncryptedFileError` mapped to **exit 3** (parity with the skill's own `pptx_to_pdf.py`), never a `BadZipFile` traceback; (b) the message names **both** possibilities (encrypted **or** legacy CFB `.ppt`) because byte-sniffing cannot reliably discriminate them — **no** separate `LegacyPptInput` type is invented; (c) `.pptm` opens normally and macros are simply **not read** (read-only path; no pack-time macro helper applies); (d) missing/not-a-pptx input → clear error (exit 1 `FileNotFound` / clear `BadInput`), not a stack trace. |
| **R-D4** | Safe, atomic output | ✅ | (a) self-overwrite guard: `OUTPUT` (or any media file) resolving to `INPUT` → exit 6 `SelfOverwriteRefused` (cross-7 parity); (b) `.md` written to a sibling temp then `os.replace` (no partial file on mid-write failure); (c) media dir created idempotently; (d) terminal `except` → redacted `InternalError` (no absolute-path leak), mirroring `xlsx2md`/`pdf_ocr` envelope discipline. |

#### Epic E — Skill surface, docs & dogfood

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R-E1** | SKILL.md & Quick-Reference | ✅ | (a) Capabilities bullet + §4 Script Contract entry + §10 Quick-Reference row + §12 Resources link; (b) honest-scope note (OCR optional, merged-cell best-effort); (c) `--json-errors` documented; (d) §7.5 Setup gains the OCR system-tool note (`tesseract` + `eng`/`rus` data, soft-optional), mirroring the pdf skill's wording. |
| **R-E2** | Reference doc | ✅ | (a) `references/pptx-to-markdown.md` — decision tree (when OCR, when manual), output shape, limitations; mirrors `pdf/references/pdf-to-markdown.md`. |
| **R-E3** | Tests + validator + dogfood | ✅ | (a) E2E suite in `scripts/tests/` (happy path, tables, images-to-sidecar + dedup canonical-name, notes, `--no-images`, stdout link-base, encrypted-reject exit 3, self-overwrite exit 6, `--json-errors`, OCR engine-absent fail-loud); (b) `validate_skill.py skills/pptx` exits 0; (c) **dogfood**: all **6** tmp8 decks (text-rich `slides-1`, `slides-2`, `slides-4`, **`slodes-3`** [sic, MINOR-4] → non-empty `.md` + populated `.media/`; image-only `slides-5.pptx` + `FRAMEWORK_WEBINAR.marp.pptx` → headers + media, body recovered only under `--ocr`), manually spot-checked; **record a measured core-extraction wall-time for `slodes-3` (MAJOR-5 baseline)**; (d) at least one `--ocr` run on a real image-only deck (engine-gated; if tesseract absent, documented as pending like pdf-4). |
| **R-E4** | Replication & license hygiene (MAJOR-2 fix) | ✅ | (a) confirm `pptx2md` is NOT added to any cross-skill `diff -q` set (pptx-specific); (b) **required edit:** `THIRD_PARTY_NOTICES.md` line ~84 Tesseract row scope is currently **pdf-only** — add `pptx` to it (the engine is now also a pptx soft-optional dep). **No** `pytesseract`/`ocrmypdf`/`ghostscript` row is added (subprocess-direct, R-C3); (c) add a pptx `--with-ocr` install hint / setup note so the OCR engine path is discoverable (no `requirements-ocr.txt` needed unless a Python OCR dep is later chosen); (d) do not alter pptx `LICENSE`/`NOTICE`; `_errors.py` stays byte-identical (consumed read-only). |

---

### 3. List of Use Cases

#### UC-1 — Convert a text-rich deck to Markdown (happy path, no OCR) — *NEW*
- **Actors:** Agent (CLI caller), System (`pptx2md.py`), python-pptx.
- **Preconditions:** A readable `.pptx` with extractable text (e.g.
  `tmp8/slides-4.pptx`); pptx venv bootstrapped.
- **Main Scenario:**
  1. Agent runs `python3 scripts/pptx2md.py tmp8/slides-4.pptx out.md`.
  2. System opens the deck, rejects if encrypted/legacy (→ UC-3).
  3. For each slide in order: emit `## Slide N`, the title as `### …`, body
     paragraphs as level-nested bullets, tables as GFM, images extracted to
     `out.media/` and linked, notes as a `> **Notes:**` block if present.
  4. System writes `out.md` atomically (temp → `os.replace`).
- **Alternative Scenarios:**
  - **A1 — stdout:** `OUTPUT` omitted/`-` → Markdown to stdout; media still
    written to `--media-dir` (default `<cwd>/<input-stem>.media/`).
  - **A2 — `--no-images`:** images skipped; no media dir created.
  - **A3 — slide with a GROUP shape:** group is recursed; inner shapes appear
    in reading order (dogfood: slides-2, slodes-3).
- **Postconditions:** `out.md` non-empty + valid Markdown; `out.media/` holds the
  deck's images; re-running yields byte-identical `out.md`.
- **Acceptance Criteria:**
  - ✅ All 6 tmp8 decks produce a `.md` with one `## Slide N` per slide; the 4
    text-rich decks have non-empty bodies (image-only `slides-5`/marp decks may have
    header-only bodies without `--ocr`).
  - ✅ slodes-3's 2 tables appear as GFM pipe tables.
  - ✅ Image links resolve to existing files under the media dir (in **file** mode
    relative to the `.md`; in **stdout** mode relative to `--media-dir` from CWD).
  - ✅ A blob appearing on multiple slides is written once and all references point
    at the canonical first-occurrence file (R-B1d).
  - ✅ Second run produces an identical `.md` (idempotent, R-A5).

#### UC-2 — Recover text baked into images with `--ocr` — *NEW*
- **Actors:** Agent, System, `tesseract` (system engine, reused from pdf skill).
- **Preconditions:** `--ocr` passed; `tesseract` + requested language packs on PATH.
- **Main Scenario:**
  1. Agent runs `python3 scripts/pptx2md.py deck.pptx out.md --ocr --ocr-lang eng+rus`.
  2. System probes tesseract once (→ UC-4 if absent).
  3. Core extraction runs (as UC-1); additionally each extracted image blob is
     OCR'd; non-empty recovered text is inserted under that image's link, marked
     as OCR-sourced.
- **Alternative Scenarios:**
  - **A1 — image yields no text:** nothing inserted (no empty OCR marker).
  - **A2 — one image fails OCR:** warning to stderr, that image skipped, deck
    completes.
- **Postconditions:** `out.md` contains authored text **plus** OCR text clearly
  attributed; images with no readable text are unchanged from UC-1.
- **Acceptance Criteria:**
  - ✅ With `--ocr` and engine present, a screenshot-with-text image yields a
    marked OCR block in the output.
  - ✅ Without `--ocr`, the tool never requires tesseract and output equals UC-1.
  - ✅ OCR-sourced text is visually distinguishable from authored text.

#### UC-3 — Encrypted / legacy input rejected early — *NEW*
- **Actors:** Agent, System, `office._encryption.assert_not_encrypted`.
- **Preconditions:** Input is a password-protected OOXML, or a legacy CFB `.ppt`.
- **Main Scenario:**
  1. Agent runs `pptx2md.py protected.pptx out.md`.
  2. System calls the shared `assert_not_encrypted` pre-flight **before** deep
     parsing; on failure it raises the single `EncryptedFileError` and exits `3`
     with a remediation message naming **both** possibilities (decrypt via
     `office_passwd.py`, or re-save a legacy `.ppt` as `.pptx`).
- **Alternative Scenarios:**
  - **A1 — `--json-errors`:** the same failure emits a single-line JSON envelope
    (`type:"EncryptedFileError"`, `code:3`) — one type, matching `pptx_to_pdf.py`.
- **Postconditions:** No `out.md` written; no traceback leaked.
- **Acceptance Criteria:**
  - ✅ Encrypted **or** legacy `.ppt` input → exit 3 + `EncryptedFileError` +
    remediation, never a `BadZipFile` stack trace.
  - ✅ The error type/code matches the skill's existing `pptx_to_pdf.py` (no new
    `LegacyPptInput`/`EncryptedInput` type invented).

#### UC-4 — OCR requested but engine/language missing — *NEW*
- **Actors:** Agent, System.
- **Preconditions:** `--ocr` passed; `tesseract` absent OR requested lang not installed.
- **Main Scenario:**
  1. Agent runs `pptx2md.py deck.pptx out.md --ocr`.
  2. System probes tesseract, finds it missing, and exits `1`
     `OcrEngineUnavailable` with an install hint (the pdf skill's
     `references/ocr.md` style), **before** writing partial output.
- **Alternative Scenarios:**
  - **A1 — engine present, lang absent:** exit 1 `LanguagePackMissing` naming the
    missing language and how to install it.
- **Postconditions:** Loud, actionable failure; no half-written `.md`.
- **Acceptance Criteria:**
  - ✅ Missing engine fails loud with remediation (never silent, never a partial
    text-only file presented as a success).
  - ✅ Missing language pack names the offending language.

#### UC-5 — Speaker-notes export — *NEW* (backlog pptx-5)
- **Actors:** Agent, System.
- **Preconditions:** A deck whose slides carry notes-slide text.
- **Main Scenario:** Each slide with non-empty notes emits a `> **Notes:**` block;
  `--no-notes` suppresses it.
- **Acceptance Criteria:**
  - ✅ Notes present → marked block under the slide.
  - ✅ Notes absent (all 6 tmp8 decks carry zero notes) → no empty notes block emitted.
  - ✅ `--no-notes` removes the block even when notes exist.

---

### 4. Non-functional Requirements
- **Performance (measurable, MAJOR-5):** core extraction (no OCR) of the largest
  dogfood deck `slodes-3.pptx` (82 slides / 231 images / 16 MB) completes in a
  **measured baseline recorded during dogfood (R-E3c)**; the design target is a
  small-multiple of plain `python-pptx` open+iterate (no quadratic blow-up), and
  the recorded number becomes the regression ceiling. Image extraction is
  O(parts). **OCR cost model:** opt-in, dominant cost ≈ `n_unique_images · T`
  where `T` = per-image tesseract time; default serial, `--jobs N` parallelises,
  `--ocr-timeout SEC` bounds a pathological image so it cannot hang the deck.
- **Exit-code map (hybrid parity — MINOR-3, documented intentionally):**
  `0` success · `1` OCR-engine failures (`OcrEngineUnavailable` /
  `LanguagePackMissing`, per `pdf_ocr.py` parity) + generic input errors ·
  `2` argparse usage · `3` `EncryptedFileError` (encrypted/legacy, per the pptx
  skill's `pptx_to_pdf.py` parity) · `6` `SelfOverwriteRefused` (cross-7 parity).
- **Security (office trust model):** local single-tenant CLI; no remote fetches;
  redacted error messages (no absolute-path leak); atomic write; self-overwrite
  guard; `defusedxml` already in deps for XML safety; tesseract invoked via argv
  list (no shell string) to avoid the `DOCX-MERMAID-EXECSYNC` class of issue.
- **Compatibility:** `.pptx` + `.pptm` (macros ignored on read); python-pptx 1.0.2;
  output is CommonMark/GFM-compatible Markdown.
- **License:** stays within the pptx skill's Proprietary scope; reused
  `_errors.py` is unmodified.

---

### 5. Constraints and Assumptions
- **C1 — Engine choice fixed:** python-pptx for structure (already a dependency);
  no LibreOffice round-trip for text extraction (LibreOffice stays for
  PDF/preview only).
- **C2 — OCR is a direct per-image tesseract call**, reusing the pdf skill's
  engine + `eng+rus` default + soft-optional/fail-loud conventions; it does **not**
  route through `ocrmypdf`/`pdf_ocr.py` (that is PDF-page-oriented and loses the
  per-image placement the user chose). This is an honest reuse of the *engine and
  conventions*, not of the `pdf_ocr.py` code path.
- **C3 — Not cross-skill replicated:** `pptx2md.py` (+ module) is pptx-specific,
  like `xlsx2md/`. Only `_errors.py` is shared and is consumed read-only.
- **C4 — Markdown composition fidelity is best-effort:** rich-text styling,
  SmartArt, charts, and complex merged-table spans are extracted structurally but
  not pixel-faithfully; limitations are documented (honest scope), not hidden.
- **C5 (AR-8 corrected):** `tmp8/` contains **only `.pptx`** (6 decks, no PDF). The
  two image-only decks (`slides-5.pptx`, `FRAMEWORK_WEBINAR.marp.pptx`) are the real
  `--ocr` exercise; a marp background-image deck may carry slide content as a
  slide-background fill that a `python-pptx` reader does not surface as a `PICTURE`
  shape — a documented v1 limitation (see ARCHITECTURE §10), not a silent drop.
- **A1 (assumption):** default media dir is `<output-stem>.media/` beside the
  `.md`; for stdout mode it defaults beside CWD. Confirmed reasonable; revisit if
  the reviewer objects.
- **A2 (assumption):** default OCR languages `eng+rus` (parity with `pdf_ocr.py`),
  overridable via `--ocr-lang`.

---

### 6. Open Questions

> None are **blocking**. The three architecture-shaping decisions (image handling,
> OCR mechanism, OCR default) were resolved with the user up front (sidecar media +
> links / per-image tesseract / opt-in `--ocr`). The five MAJOR review findings
> (encrypted/legacy single-type, OCR invocation + dependency/notice, image
> dedup↔naming tie-break, stdout link-base, measurable perf NFR) were **folded into
> the RTM/UCs above** during the task-review loop (see
> `docs/reviews/task-020-review.md`). The items below are the only remaining
> non-blocking refinements for the Architect to settle with sensible defaults:

- **Q1 (non-blocking):** Single-file `pptx2md.py` vs a `pptx2md/` package (mirror
  `xlsx2md/`)? *Default:* start as a single well-factored module + thin shim;
  split into a package only if the Architect deems the surface large enough.
- **Q2 (non-blocking):** OCR-text rendering form — `<!-- ocr -->`-tagged blockquote
  vs an HTML comment vs a `> [OCR]` prefix. *Default:* a marked blockquote that is
  both human-readable and machine-greppable (R-C4a).
- **Q3 (non-blocking):** Should charts/SmartArt get a placeholder marker like
  unsupported media (R-B3)? *Default:* yes — emit a `[chart]`/`[smartart]`
  placeholder + warning rather than silently dropping.
  **As-built (020-06 reconciliation):** charts → `[chart]` marker shipped; **SmartArt
  deferred** — python-pptx exposes no reliable SmartArt classifier and the detection
  could not be fixtured/dogfooded, so a SmartArt diagram is silently skipped in v1
  (documented limitation, see ARCHITECTURE §10).

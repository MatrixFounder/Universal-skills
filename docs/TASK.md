# TASK 018 — `pdf_ocr.py` (pdf-4): OCR scanned PDFs (eng+rus)

## 0. Meta Information (MANDATORY)

- **Task ID:** 018
- **Slug:** `pdf-ocr`
- **Backlog row:** `pdf-4` in
  [`docs/office-skills-backlog.md`](office-skills-backlog.md) (P0,
  "hard-blocker: без OCR агент не может прочитать ни один scanned PDF").
- **Skill surface:** `skills/pdf/` — one of the four **proprietary** office
  skills (CLAUDE.md §3 License hygiene). New script:
  `skills/pdf/scripts/pdf_ocr.py`.
- **Context / dependency:** composes downstream of `pdf_extract.py`
  (TASK 013 / pdf-12). `pdf_extract.py` exits **10 `DocumentScanned`** on
  an image-only PDF; `pdf_ocr.py` is the remediation step that produces a
  searchable PDF which `pdf_extract.py` (or the agent's Read tool) can then
  read digitally.
- **Mode:** VDD (Verification-Driven Development). This document is the
  authority for the Architecture + Planning phases.

### Locked design decisions (user-confirmed 2026-06-03)

These three were ambiguous in the backlog row ("tesseract **или**
ocrmypdf") and were resolved with the user before drafting:

| # | Decision | Choice |
|---|----------|--------|
| D-1 | Engine & primary output | **ocrmypdf wrapper → searchable PDF** (raster page preserved + invisible text layer). Optional `--sidecar PATH.txt` plain-text dump. NOT a raw-tesseract text-only tool. |
| D-2 | Dependency packaging | **Soft-optional** (mirrors pdf-11 `--with-chrome`): `requirements-ocr.txt` + `bash install.sh --with-ocr`; lazy import; missing engine → loud `OcrEngineUnavailable` envelope with remediation. base pdf skill stays light. |
| D-3 | Input that already has a text layer | Default **`--skip-text`** (OCR only image-only pages, never destroy vector text, never crash on mixed input). Override flags `--redo-ocr` / `--force-ocr`. |

---

## 1. General Description

`pdf_ocr.py` is a thin, contract-compliant CLI wrapper around
[`ocrmypdf`](https://ocrmypdf.readthedocs.io/) that turns an image-only
(scanned) PDF into a **searchable PDF**: the original page raster is kept
verbatim and an invisible OCR text layer is overlaid so the text becomes
selectable/extractable. The default OCR languages are **English + Russian**
(`eng+rus`), per the user's explicit requirement, and are configurable via
`--lang`.

**Goal.** Close the P0 "hard-blocker" in the PDF read-loop: today an agent
that hits a scanned PDF gets `pdf_extract.py` exit `10 DocumentScanned` and
a dead end. `pdf_ocr.py` is the missing remediation hop:

```
pdf_extract.py scan.pdf            # exit 10 DocumentScanned
pdf_ocr.py scan.pdf scan.ocr.pdf   # → searchable PDF (eng+rus)
pdf_extract.py scan.ocr.pdf        # exit 0, doc_scanned=false, text present
```

**Connection with existing system.**
- Imports `_errors.py` **read-only** for the `--json-errors` envelope
  (cross-5 parity) — **no cross-skill replication** is triggered (the
  script is a docx-style per-skill CLI, like `pdf_extract.py`; see
  [CLAUDE.md](../CLAUDE.md) §2 "Out of scope").
- Establishes the `OcrEngineUnavailable` soft-optional-engine pattern as a
  sibling to pdf-11's `ChromeEngineUnavailable` (same lazy-import +
  fail-loud-with-remediation discipline).
- Reuses the cross-7 H1 same-path guard (`SelfOverwriteRefused`, exit 6)
  already conventional in `pdf_watermark.py` / `pdf_extract.py`.

**Honest non-goals (v1).** No bundled OCR engine (system tesseract + gs are
the user's install choice — detected, not installed). No layout/markdown
reconstruction (that remains `pdf_extract.py` + LLM composition). No
adversarial-PDF / decompression-bomb hardening beyond what ocrmypdf+gs do
themselves. No OCR-accuracy tuning beyond exposing ocrmypdf's own knobs.

---

## 2. Requirements Traceability Matrix (RTM)

Granularity: ≥ 3 sub-features per requirement. **MVP** column marks the
minimum shippable surface; non-MVP rows are in scope for this task but may
land in a later Stub-First bead.

### Epic A — Core OCR conversion

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|-------------|
| R1 | Produce a searchable PDF from a scanned input via ocrmypdf | ✅ | (a) `pdf_ocr.py INPUT.pdf OUTPUT.pdf` positional CLI (argparse); (b) original page raster preserved (no visual change), invisible text layer overlaid; (c) page count + per-page geometry (MediaBox) preserved |
| R2 | Language support — eng+rus default, configurable | ✅ | (a) `--lang` option, default `eng+rus`, tesseract `+`-joined syntax; (b) pre-flight validation that every requested pack is in `tesseract --list-langs` → loud `LanguagePackMissing` envelope + per-OS remediation if absent; (c) arbitrary combinations accepted, order preserved as passed |
| R3 | Existing-text-layer handling (D-3) | ✅ | (a) default `--skip-text` (OCR only no-text pages; never error on mixed/already-OCR'd PDF; never destroy vector text); (b) `--redo-ocr` (strip & re-OCR existing OCR layer); (c) `--force-ocr` (rasterize+OCR everything, lossy); (d) the three modes are **mutually exclusive** (argparse mutex group) |

### Epic B — Composition & pipeline integration

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|-------------|
| R4 | Round-trip composition with `pdf_extract.py` | ✅ | (a) output PDF re-readable by `pdf_extract.py` as digital (`doc_scanned=false`, text non-empty) on the OCR'd fixture; (b) documented recipe `pdf_extract → exit 10 → pdf_ocr → pdf_extract` in the reference doc; (c) optional `--sidecar PATH.txt` emits ocrmypdf's plain-text dump alongside the searchable PDF |
| R5 | Encrypted / password-protected input | ⬜ | (a) `--password PW` decrypts before OCR (ocrmypdf supports input password); (b) encrypted-without-password → loud exit 1 (`EncryptedInput`/`InputUnreadable`), never silent; (c) `--password` honest-scope: argv-visible in `ps` (documented, same as `pdf_extract.py`) |

### Epic C — Robustness, contract & packaging

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|-------------|
| R6 | Exit-code & error contract aligned with sibling pdf CLIs | ✅ | (a) `--json-errors` envelope (cross-5, `v=1`); (b) exit map `0` ok / `1` fail / `2` usage / `6` SelfOverwriteRefused — **all hard failures exit `1`, discriminated by the envelope `error_type`** (`OcrEngineUnavailable` / `LanguagePackMissing` / `EncryptedInput` / `InputUnreadable` / `PriorOcrFound` / `OutputWriteFailed` / `InternalError`); **no new exit codes** — `10` is reserved to `pdf_extract.py` `DocumentScanned` and not reused (see ARCHITECTURE §5.2 / §12 D-A1, resolves M-1); (c) same-path guard via `Path.resolve()` (in==out → exit 6); (d) `--sidecar` self-overwrite guard (sidecar path ∉ {input, output}) |
| R7 | Soft-optional dependency packaging (D-2) | ✅ | (a) `requirements-ocr.txt` (ocrmypdf) + `install.sh --with-ocr`; (b) lazy `import ocrmypdf` inside the run path → missing → `OcrEngineUnavailable` (exit 1, envelope `type`) with remediation; (c) `install.sh --with-ocr` **checks (not installs)** tesseract binary, `eng`+`rus` traineddata, and ghostscript, printing per-OS install hints (macOS/Debian/Fedora); (d) `requirements.txt` / base `install.sh` UNCHANGED (no eager OCR dep) |
| R8 | Tests, fixtures, docs, validator-green | ✅ | (a) E2E in `skills/pdf/scripts/tests/test_e2e.sh` (scanned fixture → OCR → `pdf_extract` recovers a **tolerant** Cyrillic+ASCII needle, case-insensitive substring — OCR is not bit-exact); (b) unit tests (lang validation, mode-flag mutex, same-path guard, envelope shapes, lazy-import failure path); (c) reference doc `references/ocr.md` (incl. the OCR **trust model** — see M-2 below) + `SKILL.md` surface + cross-link from `references/pdf-to-markdown.md`; (d) `validate_skill.py skills/pdf` exit 0; skill-validator green; cross-skill `diff -q` unaffected (no `office/` / shared-helper edits) |

### Epic D — Optional image-prep knobs (honest-scope, deferrable)

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|-------------|
| R9 | Expose ocrmypdf image-prep pass-throughs | ⬜ | (a) `--deskew` (straighten skewed scans); (b) `--rotate-pages` (auto-orient via OSD; requires `osd` traineddata — validated like R2b); (c) `--clean` (unpaper despeckle; honest-scope: needs `unpaper`, soft-checked, degrade-with-warn if absent) |

---

## 3. Use Cases

### UC-1 — OCR a fully-scanned legacy document (primary)

- **3.1 Name:** OCR an image-only PDF into a searchable PDF.
- **3.2 Actors:** Agent (caller / "System"); `ocrmypdf` + `tesseract` +
  `ghostscript` (external subprocess engine).
- **3.3 Preconditions:** `--with-ocr` deps installed; `eng`+`rus`
  traineddata present; input is a valid, image-only PDF (e.g. the one that
  made `pdf_extract.py` exit 10).
- **3.4 Main scenario:**
  1. Agent runs `pdf_ocr.py scan.pdf scan.ocr.pdf`.
  2. System resolves paths; same-path guard passes (in≠out).
  3. System lazy-imports `ocrmypdf`; engine present.
  4. System validates `--lang` default `eng+rus` against
     `tesseract --list-langs`; both present.
  5. System invokes `ocrmypdf(..., language=["eng","rus"], skip_text=True)`.
  6. ocrmypdf rasterizes nothing extra (image-only already), runs tesseract
     per page, overlays the invisible text layer, writes `scan.ocr.pdf`.
  7. System exits `0`; success line printed to stdout.
  8. (Composition) Agent re-runs `pdf_extract.py scan.ocr.pdf` → exit `0`,
     `doc_scanned=false`, per-page `text` now populated.
- **3.5 Alternative scenarios:**
  - **A1 — engine missing:** lazy `import ocrmypdf` fails →
    `OcrEngineUnavailable` (exit 1, envelope `type`) + remediation
    (`bash install.sh --with-ocr` + system tesseract/gs hints). No stack trace.
  - **A2 — language pack missing:** user passes `--lang eng+deu` but `deu`
    not installed → `LanguagePackMissing` (exit 1, envelope `type`) naming the
    missing pack + per-OS install hint. No partial OCR.
  - **A3 — same path (in==out):** `pdf_ocr.py a.pdf a.pdf` →
    `SelfOverwriteRefused` (exit 6) before any work; symlink-aware via
    `Path.resolve()`.
  - **A4 — input already has text (mixed):** default `--skip-text` → only
    image pages OCR'd; vector-text pages untouched; exit 0 (no
    `PriorOcrFound` crash).
  - **A5 — corrupt / non-PDF input:** ocrmypdf/pikepdf raises → mapped to
    exit 1 (`InputUnreadable`) with a clean message (no library traceback;
    noisy loggers silenced like `pdf_extract.py`).
  - **A6 — output dir not writable:** exit 1 (`OutputWriteFailed`).

### UC-2 — OCR + plain-text sidecar in one pass

- **Actors:** Agent; engine.
- **Preconditions:** as UC-1.
- **Main scenario:** `pdf_ocr.py scan.pdf scan.ocr.pdf --sidecar scan.txt`
  → searchable PDF **and** `scan.txt` (ocrmypdf `--sidecar`) written;
  sidecar self-overwrite guard ensures `scan.txt ∉ {scan.pdf, scan.ocr.pdf}`.
- **Acceptance:** both files exist; sidecar contains the recognised text;
  exit 0.

### UC-3 — Re-OCR a previously (badly) OCR'd PDF

- **Actors:** Agent; engine.
- **Main scenario:** `pdf_ocr.py old.pdf new.pdf --redo-ocr --lang rus`
  strips the prior text layer and re-runs OCR in Russian.
- **Alternative:** `--redo-ocr` + `--force-ocr` together → argparse mutex
  error (exit 2).

### UC-4 — Encrypted scanned PDF (non-MVP, R5)

- **Main scenario:** `pdf_ocr.py enc.pdf out.pdf --password s3cr3t` →
  decrypt → OCR → searchable (unencrypted) output. Exit 0.
- **Alternative:** wrong/absent password on an encrypted input → exit 1
  (`EncryptedInput`) with a clear "supply --password" message.

### 2.7 Acceptance Criteria (task-level, binary)

- ✅ `pdf_ocr.py scan.pdf out.pdf` on the scanned fixture exits 0 and
  produces a PDF for which `pdf_extract.py out.pdf` exits 0 with
  `doc_scanned=false` and non-empty page text (R1, R4a).
- ✅ Default OCR languages are exactly `eng+rus` with no `--lang` given (R2a).
- ✅ A missing language pack and a missing engine both yield **exit 1** with
  a `--json-errors` envelope `error_type` of `LanguagePackMissing` /
  `OcrEngineUnavailable` respectively (naming the pack for the former), both
  carrying remediation text (R2b, R7b; ARCHITECTURE §12 D-A1).
- ✅ `pdf_ocr.py a.pdf a.pdf` exits 6 without writing (R6c).
- ✅ `--skip-text` (default) on a mixed PDF exits 0 and leaves vector-text
  pages byte-unchanged in their text content (R3a). `--redo-ocr`/`--force-ocr`
  are mutually exclusive with each other and with `--skip-text` (R3d).
- ✅ `--json-errors` produces a `v=1` envelope on every non-zero exit (R6a).
- ✅ Base `requirements.txt` and base `install.sh` (no flag) are unchanged;
  `install.sh --with-ocr` installs ocrmypdf into `.venv` and reports
  tesseract/eng/rus/gs presence without installing them (R7).
- ✅ `python3 .claude/skills/skill-creator/scripts/validate_skill.py
  skills/pdf` exits 0; `test_e2e.sh` passes including the new OCR block;
  cross-skill `diff -q` matrix stays silent (R8).

---

## 3bis. Non-Functional Requirements

- **Performance.** OCR is CPU-bound and slow (seconds–minutes/page).
  ocrmypdf parallelises across pages; expose `--jobs N` (default: ocrmypdf
  auto = CPU count). **Honest scope:** no wall-clock budget is asserted in
  the test suite (page count × DPI × language dominate); no global timeout in
  v1 — a pathological input can run long (documented in `KNOWN_ISSUES.md` if
  observed).
- **Security.** Spawns `ocrmypdf`→`gs`/`tesseract` subprocesses over
  potentially untrusted PDFs. **Trust model** (the pdf skill has no
  `references/security.md`; the model is stated in `SKILL.md` and is to be
  documented for OCR in the new `references/ocr.md`, R8c): single-tenant,
  operator-supplied input; non-multi-tenant output directory. `--password` is
  argv-visible in `ps` (documented honest-scope, identical to
  `pdf_extract.py`). No shell string interpolation — invoke via the `ocrmypdf`
  Python API (or `argv` list, never `shell=True`). Output is written via a
  `.partial`→atomic rename to avoid half-written PDFs on crash (sibling
  convention).
- **Compatibility.** Python 3.10+ (matches base `install.sh` floor).
  ocrmypdf ≥ 15 (current); per the project "prefer dependency upgrades"
  rule, pin a `>=` floor to a current release, not an old artifact.
  tesseract ≥ 4 with LSTM engine.
- **Idempotency.** Re-running with default `--skip-text` on an
  already-searchable output is a safe near-no-op (no crash, no text
  destruction); not byte-identical (ocrmypdf re-stamps producer metadata).

---

## 4. Constraints and Assumptions

- **Constraint (license).** `pdf` is a **proprietary** office skill —
  do not add Apache headers; respect per-skill `LICENSE`/`NOTICE`. Add
  ocrmypdf + tesseract + ghostscript attribution to
  [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) in the same commit
  (CLAUDE.md §3).
- **Constraint (no replication).** `pdf_ocr.py` imports only `_errors.py`
  read-only; it lives in the docx-style per-skill bucket — **no** 3/4-skill
  replication is triggered. Do not touch `office/` or shared helpers.
- **Constraint (soft-optional).** Base install must not gain a hard OCR dep;
  the engine is gated behind `--with-ocr` (D-2).
- **Assumption.** ocrmypdf's `language=` accepts the tesseract `+`-list; we
  validate packs ourselves (clearer error than ocrmypdf's) before invoking.
- **Assumption.** `eng`+`rus` traineddata are the only language packs
  guaranteed-relevant for v1; other langs work if the user installs them
  (validated generically by R2b, not hard-coded to two).
- **Assumption.** The scanned test fixture will be **built at runtime**
  (the pdf skill `.gitignore` ignores `*.pdf`; same Deviation D-01 pattern
  as TASK 013) — render a known ASCII+Cyrillic string to a raster, wrap as an
  image-only PDF, so the OCR round-trip is reproducible without committing
  binaries. The E2E asserts a **tolerant** needle (case-insensitive
  substring), not exact equality — OCR output is not bit-exact (R8a). `osd`
  traineddata (only needed for R9b `--rotate-pages`) is **not** required by
  the MVP fixture.

---

## 5. Open Questions

All three originally-blocking ambiguities were resolved with the user on
2026-06-03 (see §0 D-1/D-2/D-3). Remaining items are **non-blocking** and
carry an architect-default; flag only if the architecture review disagrees:

- **OQ-1 (default `--lang`).** Locked to `eng+rus`. *Default kept.* No
  question outstanding.
- **OQ-2 (output positional vs `-o`).** `pdf_extract.py` uses `-o`;
  `pdf_merge.py`/`pdf_split.py` use positionals. **Architect default:**
  positional `INPUT OUTPUT` (OCR is a 1→1 transform, reads best as
  `in → out`). Decide in ARCHITECTURE §Interfaces.
- **OQ-3 (R5/R9 scheduling).** Password (R5) and image-prep knobs (R9) are
  marked non-MVP. **Architect default:** include R5 in the MVP chain (small,
  high-value for legacy docs) and defer R9 to a follow-up bead unless trivial
  to fold in. Decide in PLAN.
- **OQ-4 (exit codes) — RESOLVED (ARCHITECTURE §12 D-A1).** The tentative
  `11`/`12` codes are dropped: all hard failures exit `1`, discriminated by
  the envelope `error_type`, matching the in-skill `ChromeEngineUnavailable →
  exit 1` precedent; `10 DocumentScanned` stays exclusive to `pdf_extract.py`.

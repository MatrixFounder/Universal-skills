# Task Review — TASK 018 (`pdf-ocr` / pdf-4)

- **Date:** 2026-06-03
- **Reviewer:** Task Reviewer Agent (VDD, `03_task_reviewer` + `task-review-checklist`)
- **Target:** [`docs/TASK.md`](../TASK.md) (TASK 018)
- **Original request:** «Возьми в работу pdf-4 из docs/office-skills-backlog.md,
  учти также tesseract для en и ru»
- **Status:** ✅ **APPROVED WITH COMMENTS** (no BLOCKING issues; 3 MAJOR to
  resolve in the Architecture/Planning phase, 2 MINOR)

---

## General Assessment

Strong, implementation-ready spec. The three originally-blocking
ambiguities (engine, dep packaging, existing-text handling) were correctly
escalated to the user *before* drafting and are now locked (§0 D-1/D-2/D-3),
which is exactly the VDD discipline. The RTM is granular (≥3 sub-features/row,
4 epics, MVP column present), use cases are structured with real alternative
scenarios (engine-missing, lang-missing, same-path, mixed-input, corrupt,
unwritable), and acceptance criteria are binary and machine-checkable. The
composition story with `pdf_extract.py` (exit 10 → OCR → re-read) is accurate
and is the right reason this task exists.

The user's explicit "tesseract для en и ru" is faithfully captured as a
**default `--lang eng+rus`** plus generic pack-validation (R2), not a
two-language hard-code — good.

Three MAJOR items below are factual/consistency gaps that must be settled by
the Architect before Planning; none invalidate the spec's structure.

---

## Comments

### 🔴 CRITICAL (BLOCKING)

None.

### 🟡 MAJOR

- **M-1 — Exit-code numbering contradicts an existing precedent (R6b, OQ-4).**
  TASK proposes new codes `11 OcrEngineUnavailable` / `12 LanguagePackMissing`.
  But the only existing optional-engine precedent —
  `ChromeEngineUnavailable` in `html2pdf.py:302` — maps to **exit 1** with a
  distinctive envelope `error_type`, *not* a dedicated code. Meanwhile
  `pdf_extract.py` deliberately introduced `10 DocumentScanned` as a
  branchable code. So there are **two competing conventions** in the same
  skill and the TASK picks neither cleanly.
  **Fix (Architect):** decide and document one model in ARCHITECTURE
  §Exit-code matrix:
  - **Option A (recommended):** keep distinct codes *only* for the
    actionable-install conditions (engine/lang missing), justified by the
    same composition rationale as `10 DocumentScanned` (a wrapper can branch
    "go install X" vs "input is bad"). Explicitly note the divergence from
    `ChromeEngineUnavailable→1` and, ideally, file a follow-up to align Chrome
    later — OR
  - **Option B:** map both to exit 1 with `error_type` =
    `OcrEngineUnavailable`/`LanguagePackMissing`, matching the Chrome
    precedent exactly; lose programmatic branchability.
  Update OQ-4 with the conflict (currently it only frames "avoid colliding
  with 10", omitting the Chrome precedent).

- **M-2 — Dangling reference: `references/security.md` does not exist in the
  pdf skill (§4 Constraints, §3bis Security).** The TASK twice cites the pdf
  skill's trust model as `references/security.md`. The pdf skill has no such
  file — its `references/` holds `forms.md`, `html-conversion.md`,
  `library-selection.md`, `pdf-to-markdown.md`, `weasyprint-setup.md`; the
  trust model is currently only sketched in `SKILL.md` (`references/security.md`
  exists in **xlsx**, not pdf).
  **Fix (Analyst, now or Architect):** either (a) point the trust-model
  reference at the actual location (`SKILL.md`) and state the inherited
  single-tenant/operator-supplied assumption inline, or (b) make
  "create/extend a pdf trust-model note" an explicit R8c deliverable. Do not
  leave a citation to a non-existent file.

- **M-3 — R5 (password) MVP status is internally inconsistent.** The RTM
  marks R5 non-MVP (⬜), but UC-4, §3bis, and OQ-3 all lean toward folding it
  into the MVP chain ("small, high-value for legacy docs"). A scanned legacy
  document — the exact target population — is also the most likely to be
  encrypted, so the ambiguity is material to scope.
  **Fix (Architect/Planner):** resolve OQ-3 explicitly before PLAN. If R5 is
  in, flip the RTM cell to ✅ and add it to the MVP acceptance set; if out,
  remove UC-4 from the MVP acceptance list to avoid a half-specified feature
  leaking into the first bead.

### 🟢 MINOR

- **m-1 — §0 phrasing nit.** The "(Apache-2.0? — NO: …)" parenthetical reads
  as a leftover self-question. Tighten to a plain statement: "`pdf` is one of
  the four proprietary office skills (CLAUDE.md §3)."

- **m-2 — Fixture determinism (§4 Assumption + R8a).** The "build the scanned
  fixture at runtime" plan (mirroring TASK 013 D-01) is sound, but the spec
  should pin *how* it stays deterministic enough for an exact-text E2E
  assertion: render a known ASCII+Cyrillic string to a raster, wrap
  image-only, then assert `pdf_extract` recovers a tolerant substring (OCR is
  not bit-exact). State the tolerance (substring / case-insensitive needle),
  not an exact-equality check, so the E2E is not flaky. Note: if R9b
  (`--rotate-pages`) is ever in scope it needs `osd` traineddata — keep it out
  of the MVP fixture.

---

## Checklist Result (`task-review-checklist`)

| Section | Item | Verdict |
|---|---|---|
| 1 Task Compliance | Requirements covered (pdf-4 + en/ru) | ✅ |
| 1 | No unrequested scope | ✅ (R9 explicitly honest-scope/deferrable) |
| 1 | Solves core problem (scanned-PDF dead end) | ✅ |
| 2 Completeness | UC structure (actors/pre/main/alt/post/criteria) | ✅ |
| 2 | Alternatives cover errors/edges | ✅ (A1–A6) |
| 2 | Acceptance criteria binary/verifiable | ✅ |
| 3 Compatibility | Project terminology | ✅ (envelope, cross-5/7, doc_scanned) |
| 3 | Respects architecture constraints | ⚠️ M-1 (exit codes), M-2 (security ref) |
| 3 | Integrations described (pdf_extract compose) | ✅ |
| 4 Consistency | Internal non-contradiction | ⚠️ M-3 (R5 MVP) |
| 4 | Naming consistent | ✅ |
| 5 Non-Functional | Performance metrics | ✅ (honest-scope: no budget asserted) |
| 5 | Security (subprocess, --password, trust) | ⚠️ M-2 (dangling ref) |

---

## Final Recommendation

**Proceed to the Architecture phase.** No re-draft loop is required before
Architecture — but the Architect MUST resolve **M-1** (exit-code convention)
and **M-3** (R5 MVP scope) inside `docs/ARCHITECTURE.md`, and **M-2** (the
`references/security.md` dangling reference) should be corrected in TASK.md or
absorbed as an explicit R8c deliverable. MINOR items are non-blocking polish.

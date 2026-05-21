# Architecture Review — pdf-13 (PDF → Markdown extraction guidance + `pdf_extract.py`)

- **Date:** 2026-05-21
- **Reviewer:** Architecture Reviewer Agent (VDD pipeline)
- **ARCHITECTURE file:** `docs/ARCHITECTURE.md` (pdf-13, 520 lines)
- **TASK file:** `docs/TASK.md` (TASK 013 — `pdf-to-markdown`)
- **Status:** ✅ **APPROVED WITH COMMENTS** — 0 BLOCKING, 4 MAJOR, 4 MINOR. The Architecture→Planning gate is **OPEN**. None of the MAJOR items requires re-architecture; all are correctable inline.

## General Assessment

High-quality, tightly-scoped architecture for a small single-script addition. Every load-bearing claim was verified against the real `skills/pdf/` codebase and the installed `pdfplumber 0.11.x` / `pdfminer.six`. Strengths:

- **No hallucinated APIs.** All `pdfplumber` APIs are real: `page.extract_tables()` (returns `List[List[List[Optional[str]]]]` — exactly the §4.2 `tables` shape, `None`→`null`); `page.extract_text(layout=True)` pass-through; `page.images`; `pdfplumber.open(path, password=…)`. The encrypted-input claim (D8/§5.4) is sound — `pdfplumber.open()` constructs `PDFDocument` eagerly, so `PDFPasswordIncorrect`/`PDFEncryptionError` is raised synchronously inside `_open_pdf`; there is genuinely no silent-empty path on encrypted input.
- **Data Model §4 correct.** §4.3 derived rule and truth table traced row-by-row; the `bool(scanned_pages)` guard correctly prevents an all-blank PDF being routed to OCR.
- **Traceability complete.** §11's 6-bead chain covers all R1–R13 and UC-1..3; no orphan.
- **YAGNI correctly applied** (single file, ≤350 LOC, consistent with `pdf_split.py`/`pdf_fill_form.py`).
- **Security posture §7 appropriate** for a local CLI; untrusted-text-as-data correctly delegated to the reference doc as a downstream composition concern.
- **Per-task archival is correct repo practice** (`architecture-001..009` exist; xlsx-9→`architecture-009`; D1 self-documents) — not flagged per `core-principles` §0.

## 🔴 CRITICAL (BLOCKING)

None. No data-model flaw, no security hole, no incompatibility, no hallucinated dependency.

## 🟡 MAJOR

- **M-1 — §5.2 exit-code justification is factually wrong: `10` is NOT free.** §5.2/D5 state *"`pdf_fill_form.py` uses 11/12; 10 is free."* Incorrect — `pdf_fill_form.py:46` defines `EXIT_FILL_ERROR = 10` (plus 11/12). Not blocking (exit codes are per-script, not a shared namespace — `10`/`DocumentScanned` is fine *for this script*), but the false justification would propagate into incorrect SKILL.md text in bead 013-06. **Fix:** correct §5.2/D5 — exit codes are per-script; `pdf_extract.py` defines its own `10 = DocumentScanned`; the convention is only "custom codes ≥ 10", which `10` satisfies. Keep `10`.
- **M-2 — §4.3 truth table omits two reachable rows.** Missing: (1) single-page image-only PDF (smallest whole-doc scan → `doc_scanned=true`, exit 10); (2) all pages have images but ≥1 page also has >10 chars text (→ `doc_scanned=false`, exit 0 — the one place `has_images` interacts non-trivially with the threshold). **Fix:** add both rows; annotate row 2 "a digital page never forces `doc_scanned` even with images — `no_meaningful_text` is the guard."
- **M-3 — Dump-to-stdout vs `--json-errors`-stderr interaction under-specified on a whole-doc scan.** §5.2/§5.3 say the dump is still emitted AND a `DocumentScanned` envelope goes to stderr, but never state whether the dump still goes to **stdout** when `--json-errors` is set. **Fix:** state explicitly — on a whole-doc scan the dump is written to its normal sink (stdout or `-o`) regardless of `--json-errors`; `--json-errors` governs only the stderr channel; stdout always carries the dump, never the envelope.
- **M-4 — Threshold-rationale inconsistency.** §4.3 leans on "a genuine scan scores ≈0" while §4.2/§10(f) say `--layout` inflates `char_count`. Reconcilable (an image-only page has nothing to pad) but never stated. **Fix:** add to §4.3 — a genuinely image-only page has no characters, so `char_count`=0 under both default and `--layout`; the §4.2 inflation applies only to pages already containing text; the scan-like fixture (FC6) MUST contain zero selectable text so its score is unambiguously 0.

## 🟢 MINOR

- **m-1** — §5.2 `InternalError` (exit 1) is in the prose but not in the exit-code table's code-1 `type` cell; add it.
- **m-2** — Dual numbering "pdf-13" (title) vs backlog row `pdf-12`; intentional per TASK §0 but add a one-line note in §11/§13.
- **m-3** — R8.1a rationale is dual-homed across bead 013-03 (docstring) + 013-05 (reference); the §11 coverage note would read cleaner saying so.
- **m-4** — §5.4 `_open_pdf` comment says "caller closes" but `extract_pdf`'s ownership (`with`/`try-finally`) is implicit; specify it to avoid a leaked file descriptor on a mid-extraction exception.

## Final Recommendation

**APPROVED WITH COMMENTS.** The Architecture→Planning gate is **OPEN** — none of the MAJOR items requires re-architecture. The 4 MAJOR fixes should be applied before Planning consumes the document (M-1 highest priority — it would otherwise produce incorrect SKILL.md text).

```json
{"review_file": "docs/reviews/architecture-013-review.md", "has_critical_issues": false}
```

---

## Resolution (Architect v2 — 2026-05-21)

All 4 MAJOR and all 4 MINOR items applied to `docs/ARCHITECTURE.md` before the
Planning phase:

- **M-1** → §5.2 note + D5 reworded: exit codes are per-script; `pdf_fill_form.py`
  uses 10/11/12; `pdf_extract.py` defines its own `10 = DocumentScanned`; the
  convention is "custom codes ≥ 10". `10` kept.
- **M-2** → §4.3 truth table gained the single-page-image-only row and the
  all-pages-have-images-but-≥1-has-text row, with the `no_meaningful_text`
  annotation.
- **M-3** → §5.2 + §5.3: explicit statement that stdout/`-o` always carries the
  dump; `--json-errors` governs only the stderr channel; `-o` recommended for
  scanned-input pipelines.
- **M-4** → §4.3 rationale reconciled with the `--layout` inflation note; FC6 /
  §4.3 now require the scan-like fixture to contain zero selectable text.
- **m-1** → `InternalError` added to the §5.2 code-1 `type` cell.
- **m-2** → §13 D-note clarifies "pdf-13" (architecture/title) vs `pdf-12`
  (backlog row).
- **m-3** → §11 coverage note records the dual-homed R8.1a rationale.
- **m-4** → §5.4 `_open_pdf` / `extract_pdf` file-handle ownership made explicit
  (`with` block in `extract_pdf`).

Status after resolution: **APPROVED, all comments resolved** — proceed to
Planning phase.

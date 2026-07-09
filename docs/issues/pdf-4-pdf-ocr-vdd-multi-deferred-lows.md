---
id: PDF-4
type: known-issue
status: open
opened_at: 2026-06-03
category: robustness
severity: LOW
component: pdf
slug: pdf-4-pdf-ocr-vdd-multi-deferred-lows
---

# PDF-4 (`pdf_ocr.py`) — vdd-multi deferred LOWs (2026-06-03)

**Status:** DEFERRED (LOW; documented-scope, not regressions).
**Backlog row:** `pdf-4` in
[`docs/office-skills-backlog.md`](../office-skills-backlog.md).
**Context:** `/vdd-multi` over TASK 018 ran 3 parallel critics across 3
iterations. All CRITICAL/HIGH/MED findings are fixed with regression tests
(non-zero ocrmypdf `ExitCode` no longer promoted to success; raw `OSError` on
an unwritable OUTPUT dir now maps to `OutputWriteFailed`; decrypted-scratch
leak + `KeyError` window closed; `.partial` hardened to `mkstemp` O_EXCL 0600;
`_installed_languages`/exception-mapping test gaps closed; fixture rebuild +
double `--list-langs` perf items closed). Two LOW items are intentionally
deferred:

- **PDF4-L1 — `--sidecar` is not written atomically.** `run_ocr`
  ([`skills/pdf/scripts/pdf_ocr.py`](../../skills/pdf/scripts/pdf_ocr.py)) passes
  `--sidecar` to ocrmypdf as the final path, while the searchable PDF goes
  through an mkstemp `.partial` + `os.replace`. On a mid-OCR failure a
  stale/partial `sidecar.txt` can remain (the I-3 atomicity invariant + the
  `finally` cleanup cover only the PDF and the decrypted scratch). **Severity:**
  LOW (best-effort side output; the PDF — the primary deliverable — is atomic).
  **Fix path:** route the sidecar through a temp + `os.replace` and add it to
  the `finally` cleanup; update the fake-engine test to write a sidecar.
  **Do-not:** claim sidecar atomicity in docs until this lands.
- **PDF4-L2 — `_installed_languages` ignores `tesseract --list-langs` non-zero
  exit.** `subprocess.run(..., check=False)`; a tesseract that errors for a
  reason other than "not found" yields an empty language set, so the requested
  langs are reported as `LanguagePackMissing` rather than the true tesseract
  error. **Severity:** LOW (still fails loud with a remediation hint; never
  silent). **Fix path:** surface a non-zero rc + stderr as a distinct
  diagnostic. **Do-not:** change this without checking the
  `test_installed_languages_*` expectations.

**Workaround:** none required — both are LOW and the chain is production-ready
(modulo the documented sandbox composition-verification caveat on the `pdf-4`
backlog row). Promoting either to a follow-up is at user discretion.

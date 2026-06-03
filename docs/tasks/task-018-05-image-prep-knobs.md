# Task 018-05 [LOGIC IMPLEMENTATION]: image-prep pass-throughs (`--deskew`/`--rotate-pages`/`--clean`) (deferrable)

> **Predecessor:** 018-03. **Post-MVP, deferrable (D-A2). Run only if
> prioritized.**
> **RTM:** **completes** [R9] (a/b/c).
> **ARCH:** §2.1 (FC-3 scope-note AM-3), §10 (honest scope), §11 (bead 018-05).

## Use Case Connection

- Extends UC-1 (OCR quality knobs); no new use case.

## Task Goal

Wire the three ocrmypdf image-prep pass-throughs already declared in the parser
(018-01): `--deskew`, `--rotate-pages`, `--clean`. Each needs a host
prerequisite beyond `ocrmypdf` itself, so each gets a soft-probe with
degrade-with-warn / loud-fail per AM-3 — not silently ignored.

## Changes Description

### Changes in Existing Files

#### File: `skills/pdf/scripts/pdf_ocr.py`

**Function `run_ocr` (replace the 018-03 "bead 018-05" guard):**
- `--deskew` → pass `deskew=True` to `ocr.ocr(...)` (no extra host tool).
- `--rotate-pages` → pass `rotate_pages=True`; **pre-validate** that `osd`
  traineddata is installed (reuse `_installed_languages` from 018-02: require
  `"osd" in installed`) → if missing, `_OcrError("--rotate-pages needs the
  tesseract 'osd' data", error_type="LanguagePackMissing")` with per-OS hint.
- `--clean` → pass `clean=True`; **pre-probe** `command -v unpaper`
  (`shutil.which("unpaper")`) → if missing, raise `_OcrError("--clean needs the
  'unpaper' binary", error_type="OcrEngineUnavailable")` with per-OS hint
  (macOS `brew install unpaper`; Debian `apt install unpaper`).
- Combinations allowed (deskew + clean + rotate together).

**Function `_validate_languages` / `_installed_languages`** — reuse as-is for
the `osd` check; no signature change.

## Test Cases

### E2E Tests (engine-gated — soft-skip without engine)
1. **TC-E2E-10 `test_deskew_runs`** — `--deskew` on the scan fixture → exit 0,
   output still a valid searchable PDF (does not assert deskew quality).
2. **TC-E2E-11 `test_clean_missing_unpaper`** — with `unpaper` absent, `--clean`
   → exit 1, `OcrEngineUnavailable`, message names `unpaper`. (Soft-skip if
   `unpaper` IS present; cover the missing path via unit instead.)

### Unit Tests
1. **TC-UNIT-20 `test_rotate_requires_osd`** — patch installed set without `osd`
   → `--rotate-pages` path raises `_OcrError(type="LanguagePackMissing")` naming
   `osd`.
2. **TC-UNIT-21 `test_clean_requires_unpaper`** — patch `shutil.which` →
   `None` → `--clean` raises `_OcrError(type="OcrEngineUnavailable")` naming
   `unpaper`.
3. **TC-UNIT-22 `test_knob_kwargs_passed`** — assert `deskew`/`rotate_pages`/
   `clean` kwargs reach the fake ocrmypdf module when their flags are set.

### Regression Tests
- Full pdf unittest suite + `test_e2e.sh` green; MVP + 018-04 paths unaffected.

## Acceptance Criteria

- [ ] `--deskew` passes through ([R9a]).
- [ ] `--rotate-pages` passes through with an `osd`-present pre-check ([R9b]).
- [ ] `--clean` passes through with an `unpaper` pre-probe ([R9c]).
- [ ] Missing prerequisite → loud `_OcrError` (never silent), per AM-3.
- [ ] `references/ocr.md` + `--help` updated: the three knobs move from
      "deferred (bead 018-05)" to documented, with their extra host deps.
- [ ] `validate_skill.py skills/pdf` exit 0; cross-skill `diff -q` silent.

## Stub-First Gate

Self-contained logic bead. Replaces the 018-03 "not yet implemented" guard with
real pass-through + prerequisite probes; units cover the missing-prereq paths
without the engine.

## Notes

- Keep the knobs **off by default** (deterministic output); only act when the
  user opts in.
- `osd` is a tesseract data file (`tesseract-ocr-osd` / `tesseract-langpack-osd`)
  — surface it in the `install.sh --with-ocr` hint text when this bead lands.

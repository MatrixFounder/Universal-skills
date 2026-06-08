# Task 020-05 [LOGIC]: `ocr.py` — tesseract probe + per-image subprocess OCR + placement

> **Predecessor:** 020-03 (media assets), 020-04 (emit + call site).
> **RTM:** **completes** [R-C1][R-C2][R-C3][R-C4][R-C5].
> **ARCH:** §2.1 (FC-3), §5.2 (subprocess contract), §7 (S-2), §10; AR-9.

## Use Case Connection
- UC-2 (`--ocr` recovers image text), UC-4 (engine/lang missing → exit 1).

## Task Goal
Replace the `ocr` stubs with the real engine adapter: probe `tesseract` (fail-loud),
OCR each unique image blob via a direct `subprocess` call, and feed non-empty results
to the emitter under each image. Reuse the **engine + conventions** of
`skills/pdf/scripts/pdf_ocr.py` (eng+rus default, soft-optional, fail-loud) — **not**
its `ocrmypdf` code path.

## Changes Description

### Changes in Existing Files

#### File: `skills/pptx/scripts/pptx2md/ocr.py`

**Function `probe(langs: str) -> None`** — **REAL** (R-C2, AR-9):
- `shutil.which("tesseract")` is `None` → raise `OcrEngineUnavailable` (exit 1) with
  the `pdf_ocr.py`-style remediation (install hint per OS).
- Run `tesseract --list-langs` (`subprocess.run`, `check=False`, argv list); parse
  **both** `stdout` and `stderr` (AR-9 — `--list-langs` prints to either depending on
  the build; mirror `pdf_ocr.py:264` `f"{proc.stdout}\n{proc.stderr}"`). Each
  requested lang (split on `+`) not in the installed set → raise
  `LanguagePackMissing` (exit 1) naming the missing language.
- Runs **once**, called from `cli.main` before any output is written (UC-4 / I-4).

**Function `ocr_asset(blob: bytes, langs: str, timeout: float) -> str`** — **REAL**
(R-C3). *(As-built signature reconciliation: takes the image **bytes** directly, not
the `MediaAsset` — the bytes are the actual data, the asset is just a record. The
caller `cli._build_ocr_text` resolves `blob = deck.blobs[asset.sha1][0]`. This is the
cleaner, more testable shape — confirmed by the 020-05 roast.)*:
- Normalise `asset` blob → a temp PNG via `Pillow` (`Image.open(BytesIO(blob)).save(
  png, "PNG")`); write to an `mkstemp` (0600) file in `TMPDIR`; `finally`-unlink.
- `subprocess.run(["tesseract", png, "stdout", "-l", langs], capture_output=True,
  text=True, timeout=timeout, check=False)` — **argv list, `shell=False`** (S-2).
- Return `proc.stdout.strip()` (may be `""`). On `TimeoutExpired`, `CalledProcess`-style
  non-zero, or any `OSError`/`UnidentifiedImageError` → emit a warning to stderr and
  return `""` (R-C4c — one bad image never aborts the deck).

**Caching & parallelism (R-C4d, R-D2e):** `cli.main` builds the OCR map over **unique
`MediaAsset`s** (deduped, so `slodes-3`'s 231 pics collapse to distinct blobs); with
`--jobs N > 1`, run `ocr_asset` over the unique assets via a
`concurrent.futures.ThreadPoolExecutor(max_workers=N)` (the subprocess releases the
GIL). Default `--jobs 1` = serial. `PlaceholderAsset`s are **not** OCR-eligible.

#### File: `skills/pptx/scripts/pptx2md/cli.py` (call site finalised)
- Replace the 020-04 guarded stub call with: `ocr.probe(opts.ocr_lang)` then build
  `ocr_text: dict[MediaAsset, str]` over unique assets (serial or `--jobs`). Pass to
  `emit.render_deck` (which already places `<!-- ocr -->` blocks — 020-04).

### Test Cases

#### E2E Tests
1. **TC-E2E-08 `test_ocr_engine_absent_fails_loud`** — with `tesseract` forced absent
   (PATH shim) and `--ocr` → exit 1, `type=="OcrEngineUnavailable"`, **no** partial
   `.md` written. Without `--ocr`, the same deck converts fine (R-C1d/I-3).
2. **TC-E2E-09 `test_ocr_on_image_only_deck`** (engine-gated — `skipUnless`
   tesseract+eng present) — `pptx2md.py tmp8/slides-5.pptx out.md --ocr` → output
   contains at least one `<!-- ocr -->` block. **If tesseract is absent on the dev
   host, this test SKIPS and the OCR run is documented as pending (pdf-4 pattern).**

#### Unit Tests
1. **TC-UNIT-27 `test_probe_missing_engine`** — `shutil.which` patched to `None` →
   `probe` raises `OcrEngineUnavailable`.
2. **TC-UNIT-28 `test_probe_missing_lang`** — `--list-langs` output patched to `eng`
   only, request `eng+rus` → `LanguagePackMissing` naming `rus`. Verify both
   stdout-only and stderr-only `--list-langs` outputs parse (AR-9).
3. **TC-UNIT-29 `test_ocr_asset_argv_no_shell`** — patch `subprocess.run`; assert it
   is called with a **list** argv (`["tesseract", ...]`) and `shell` not True (S-2).
4. **TC-UNIT-30 `test_ocr_asset_empty_result_no_marker`** — `tesseract` stub returns
   whitespace → `ocr_asset` returns `""`; emitter places no OCR block (R-C4b).
5. **TC-UNIT-31 `test_ocr_asset_timeout_warns_continues`** — `subprocess.run` raises
   `TimeoutExpired` → `ocr_asset` returns `""` + warning, no exception (R-C4c).
6. **TC-UNIT-32 `test_ocr_dedup_cache`** — a deck with the same blob twice + `--ocr`
   → `ocr_asset` invoked **once** for that asset (R-C4d).

#### Regression
- 020-01..04 tests green; no-OCR MVP path unchanged. `validate_skill` exit 0; `diff` silent.

## Acceptance Criteria
- [ ] `--ocr` off → tesseract never probed; output == no-OCR baseline ([R-C1d], I-3).
- [ ] Missing engine/lang → exit 1, loud, before any output ([R-C2], UC-4).
- [ ] OCR via argv-list subprocess on a temp PNG, no shell ([R-C3], S-2).
- [ ] Non-empty OCR → `<!-- ocr -->` block under its image; empty → nothing ([R-C4]).
- [ ] Per-image failure/timeout → warn + continue ([R-C4c]); dedup-cached ([R-C4d]).
- [ ] TC-E2E-08 pass, TC-E2E-09 pass-or-skip; TC-UNIT-27..32 pass; regression green.

## Notes
- **No** `pytesseract`/`ocrmypdf`/`ghostscript` — direct tesseract only (D-5, AGPL-clean).
- The image-only dogfood decks (`slides-5.pptx`, `FRAMEWORK_WEBINAR.marp.pptx`) are
  the real `--ocr` exercise (020-06). A marp background-image deck may carry content
  as a slide-background fill not surfaced as a `PICTURE` shape — documented v1 limit
  (ARCH §10), not a regression.

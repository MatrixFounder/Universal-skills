# Task 022-04 [LOGIC]: `clean.py` — `web_clean` wiring (preprocess whole + reader_mode reader)

> **Predecessor:** 022-01 (`web_clean` replica), 022-02 (`AcquireResult`).
> **RTM:** [R2] HTML cleaning (reader-mode + preprocess). **Satisfies AC-R2**.
> **ARCH:** §2.1 (FC-2), §4.2 (`CleanResult`), §10 (best-effort reader honest scope), §11 (022-04).

## Use Case Connection
- UC-1 reader extraction; UC-4 SPA-chrome strip (the cleaning half — the Chrome
  *fetch* is 022-06). The whole-page variant underpins every UC as the faithful
  fallback.

## Task Goal
Wire FC-2: from an `AcquireResult`, produce a `CleanResult`
`{whole_html, reader_html}` using the **replicated, un-edited** `web_clean`
functions. `whole_html` = preprocess of the page; `reader_html` =
reader-extraction of the preprocessed page (or `None` when `--no-reader`).

## Changes Description
### `html2md/clean.py` (replace stub)
- **`clean(acq: AcquireResult, *, reader: bool) -> CleanResult`:**
  ```python
  from web_clean import preprocess_html, reader_mode_html
  whole = preprocess_html(acq.html)
  reader_html = reader_mode_html(whole) if reader else None
  return CleanResult(whole_html=whole, reader_html=reader_html)
  ```
- **No edits to `web_clean/*`** — call only. (Any cleaning *bug* is fixed in pdf
  master + re-replicated, never patched here — ARCH §9.)
- Honest-scope guard: if `reader_mode_html` returns a near-empty result
  (landmark-free SPA degrade, ARCH §10), keep `reader_html` as-is but ensure
  `whole_html` remains the faithful fallback (emit decides which files to write).

## Test Cases
### Unit
1. **TC-04-01 `test_preprocess_strips_chrome`** — a fixture with copy-buttons /
   nav / ad markers → `whole_html` excludes those needles (delegates to the
   replica's behaviour; assert via output needles, not internal calls).
2. **TC-04-02 (AC-R2) `test_reader_needles_spa`** — on a pdf-9-class SPA fixture
   (e.g. an `elma365`/`ya_browser`-style saved page), `reader_html` plain text
   **contains** the article-body needle and **excludes** the nav/sidebar needle.
3. **TC-04-03 `test_no_reader_returns_none`** — `clean(acq, reader=False)` →
   `reader_html is None`; `whole_html` still produced.
4. **TC-04-04 `test_reader_degrade_keeps_whole`** — landmark-free fixture: even
   if `reader_html` is weak, `whole_html` is non-empty (fallback invariant).

## Acceptance Criteria
- [ ] `clean` returns `CleanResult` with both variants; `--no-reader` → `reader_html None`.
- [ ] **AC-R2** reader needle test green on an SPA fixture.
- [ ] No `web_clean/*` file edited (G-1 silent); only imported.
- [ ] `whole_html` always non-empty fallback (degrade-safe).

## Notes
- `preprocess_html` is called once; `reader_mode_html` consumes its output (so the
  reader path benefits from chrome-strip too). Mirrors pdf's ordering.
- Adversarial roast focus: a fixture where reader extraction over-strips real
  content — confirm whole-page fallback still carries it.

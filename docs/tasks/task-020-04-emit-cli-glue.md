# Task 020-04 [LOGIC]: `emit.py` + `cli.main` glue — model → Markdown + atomic write (MVP gate)

> **Predecessor:** 020-02 (model), 020-03 (media).
> **RTM:** **completes** [R-A emit-side][R-A4 GFM][R-A5 idempotency][R-D2][R-D4].
> **ARCH:** §2.1 (FC-4/FC-5), §5.1 (exit map incl. AR-3), §4.3 (I-1/I-4), §11 (MVP gate).

## Use Case Connection
- UC-1 (full conversion), UC-5 (notes emit). **This task closes the MVP.**

## Task Goal
Replace the `emit` stub and wire `cli.main` end-to-end: render the document model +
media map to Markdown, write atomically, and route every failure through the
`_errors` envelope with the correct exit code.

## Changes Description

### Changes in Existing Files

#### File: `skills/pptx/scripts/pptx2md/emit.py`

**Function `render_deck(deck, assets, ocr_text, opts) -> Iterator[str]`** — **REAL**,
**streams per slide** (no whole-doc buffer):
- Per `Slide`: `## Slide {index}\n`; then each `Block` in order:
  - `Heading(level,text)` → `### {text}` (the title).
  - `Bullets` → `-`-list, `level` → 2-space indent per level.
  - `Table(rows)` → GFM pipe table: header row + `|---|` separator + body; cells are
    already escaped (020-02). Single-row table → header-only GFM (documented).
  - `ImageRef` → `![{alt}]({asset.rel_path})`; if `ocr_text.get(asset)` non-empty →
    immediately after, a `<!-- ocr -->`-tagged blockquote (R-C4a) — but only when
    `opts.ocr` (the map is empty otherwise).
  - `Placeholder(kind,note)` → `[{kind}]` marker line + (the warning was already
    emitted at extract/materialise time).
- `Slide.notes` and not `opts.no_notes` → a `> **Notes:**` block (R-D1).
- Pure function over data ⇒ deterministic (R-A5/I-1).

#### File: `skills/pptx/scripts/pptx2md/cli.py`

**Function `main(argv=None) -> int`** — **REAL** (replaces `_STUB_SENTINEL`):
- `build_parser().parse_args`; `_resolve_paths` (guards); `_resolve_media_dir`.
- `extract.assert_openable(input)` → `Presentation(input)` → `extract.build_deck`.
- `images.materialise(deck, media_dir, link_base, no_images=...)`.
- If `opts.ocr`: **lazy** `from . import ocr`; `ocr.probe(opts.ocr_lang)`;
  `ocr_text = {asset: ocr.ocr_asset(...) for unique asset}` (020-05 supplies the
  bodies; in THIS task the call site exists but is guarded so the no-OCR MVP path is
  fully exercised — with `--ocr` and `ocr` still stubbed, the `NotImplementedError`
  surfaces as a clean `InternalError`/the 020-05 real impl replaces it).
- **Atomic write (R-D4 / I-4):** stdout mode → stream to `sys.stdout`; file mode →
  open `<out>.partial`, stream `render_deck`, `close`, `os.replace(partial, out)`;
  any exception → `partial.unlink(missing_ok=True)`. (Mirror `xlsx2md/cli.py`
  `_resolve_output_stream` + the `finally` publish/unlink.)
- **Envelope routing (AR-3):** `except _AppError → report_error(code=e.CODE)`;
  `except EncryptedFileError → report_error(code=3)`; terminal `except Exception →
  report_error("Internal error: …", code=InternalError.CODE==1, type="InternalError")`
  with a **redacted** message (no path leak).
- `convert(input, output, **opts)` — **REAL** thin programmatic wrapper used by tests.

**Constant cleanup:** remove `_STUB_SENTINEL` (020-01 note).

### Test Cases

#### E2E Tests (tighten 020-01..03)
1. **TC-E2E-04 `test_full_convert_text_rich`** — convert `tmp8/slides-4.pptx out.md`
   → exit 0; `out.md` non-empty, has `## Slide 1`, ≥1 `### `, ≥1 `- ` bullet, ≥1
   resolvable `![](...)`; `out.md.partial` does NOT exist afterward.
2. **TC-E2E-05 `test_idempotent_run_twice`** — convert the same deck twice → the two
   `.md` files are **byte-identical** and the media filenames match (R-A5/I-1).
3. **TC-E2E-06 `test_gfm_table_from_slodes3`** — convert `tmp8/slodes-3.pptx` → output
   contains a GFM table (`|---|` separator) for each of its 2 tables.
4. **TC-E2E-07 `test_stdout_mode`** — `pptx2md.py deck.pptx -` → Markdown on stdout,
   media under CWD `<stem>.media/`, stderr note present.

#### Unit Tests
1. **TC-UNIT-22 `test_atomic_no_partial_on_failure`** — force `render_deck` to raise
   mid-stream → no `out.md`, no `out.md.partial` left behind.
2. **TC-UNIT-23 `test_internal_error_exit_1_redacted`** — an unexpected exception
   path → exit 1, `type=="InternalError"`, message contains no absolute path (AR-3).
3. **TC-UNIT-24 `test_notes_block_emitted_and_suppressed`** — a deck with notes →
   `> **Notes:**` present; same deck with `--no-notes` → absent.
4. **TC-UNIT-25 `test_bullet_level_indentation`** — `Bullets` with levels 0/1/2 →
   0/2/4-space indents.
5. **TC-UNIT-26 `test_placeholder_marker_emitted`** — a `Placeholder(kind="chart")`
   → a `[chart]` marker line in output.

#### Regression
- All 020-01..03 tests pass with **tightened** assertions (sentinel → real codes).
- `validate_skill.py skills/pptx` exit 0; `diff` gates silent.

## Acceptance Criteria
- [ ] `render_deck` emits headings/bullets/tables/links/notes/placeholders correctly ([R-A]).
- [ ] Atomic write — no partial file on failure ([R-D4], I-4).
- [ ] `InternalError` → exit 1, redacted ([R-D4d], AR-3).
- [ ] Idempotent: run-twice byte-identical ([R-A5], I-1).
- [ ] **MVP gate:** all 4 text-rich tmp8 decks convert to non-empty `.md` + media.
- [ ] TC-E2E-04..07 + TC-UNIT-22..26 pass; 020-01..03 regression green.

## Notes
- With `--ocr` but `ocr` still stubbed (pre-020-05), the call surfaces as a clean
  `InternalError` — acceptable until 020-05; the **no-OCR MVP path is the gate here**.
- Keep `render_deck` a pure generator so idempotency holds.

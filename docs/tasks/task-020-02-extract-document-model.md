# Task 020-02 [LOGIC]: `extract.py` — deck open + slide/shape/group walk → document model

> **Predecessor:** 020-01 (frozen surface).
> **RTM:** **completes** [R-A1][R-A2][R-A3][R-A4 extract-side][R-A5 ordering][R-D1][R-D3].
> **ARCH:** §2.1 (FC-1), §4.1 (model), §7 (S-1), §10 (honest scope); AR-1/AR-6/AR-7.

## Use Case Connection
- UC-1 (text extraction), UC-3 (encrypted/legacy reject), UC-5 (notes).

## Task Goal
Replace the `extract` stubs with the real deck reader: open the deck **after** the
encryption pre-flight, and walk it into the `Deck → Slide → [Block]` model in the
canonical reading order, with robust image/notes/hidden-slide handling.

## Changes Description

### Changes in Existing Files

#### File: `skills/pptx/scripts/pptx2md/extract.py`

**Function `assert_openable(path: Path) -> None`** — **REAL** (R-D3 / MAJOR-1 / D-6):
- Call `office._encryption.assert_not_encrypted(path)` **before** `Presentation()`.
  It raises a single `EncryptedFileError` (encrypted **or** legacy CFB `.ppt`) — let
  it propagate; `cli.main` maps it to exit 3. Do **not** invent `LegacyPptInput`.
- Wrap the later `Presentation(path)` call so `PackageNotFoundError`/`BadZipFile`
  (a non-OOXML, non-encrypted file) → `BadInput` (exit 1), not a traceback.

**Function `build_deck(prs, opts) -> Deck`** — **REAL**:
- **Slide selection (R-A1d, AR-6):** iterate `prs.slides`; skip hidden unless
  `opts.include_hidden`. python-pptx has **no** public hidden flag → read the raw
  attribute: `is_hidden = slide._element.get("show") == "0"`. Document this
  private-API reach in a comment + lock with TC-UNIT below.
- **Per slide** build `Slide(index=1-based, blocks=[...], notes=...)`:
  - **Title first (R-A2a, MINOR-1):** if `slide.shapes.title` exists and its `.text`
    strips non-empty → `blocks[0] = Heading(level=3, text=title)`, **regardless** of
    the title placeholder's XML/z-order. Mark the title shape so the body walk skips it.
  - **Body walk (R-A1b/c):** iterate `slide.shapes` in document order; **recurse into
    GROUP** (`sh.shape_type == MSO_SHAPE_TYPE.GROUP → walk(sh.shapes)`) depth-first.
  - **Classification order (AR-1) — branch on `shape.shape_type` FIRST:**
    - `GROUP` → recurse.
    - `PICTURE` → append `ImageRef(slide, shape, sha1, ext, alt)` — but obtain `sha1`
      from `shape.image.sha1` (safe) and the `ext` via a **guarded** read (see below);
      `shape.image` itself is wrapped (raises `ValueError` when `blip_rId is None`).
    - `MEDIA` (video/audio) and any other non-text, non-table shape with embedded
      media → `Placeholder(kind=..., note=...)` (R-B3).
    - has a table (`sh.has_table`) → `Table(rows)` (R-A4): `rows[0]` = header; each
      cell `.text` with `|`→`\|`, newline→`<br>` pre-escaped; merged cells →
      anchor value + blanks (honest-scope).
    - has a text frame (`sh.has_text_frame`) with non-blank text → `Bullets([
      BulletItem(level=para.level or 0, text=para_text) for non-blank paragraphs])`
      (R-A3); blank paragraphs skipped (no empty bullets).
    - chart (`sh.has_chart`) / SmartArt → `Placeholder(kind="chart"|"smartart")` (Q3).
  - **`ext` guard (AR-1) — call the shared `images.safe_image_meta(shape)` helper
    created in 020-01 (MAJOR-B, no inline duplication):** if it returns `None`
    (i.e. `.ext`/`.content_type` raised on EMF/SVG/unreadable) → `Placeholder(kind=
    <emf|svg|unreadable>)`; otherwise → `ImageRef(slide, shape, sha1, ext, alt)` using
    the `(sha1, ext)` the helper returned. The actual file write is 020-03, which
    consumes the **same** helper — so extraction and materialisation never diverge.
  - **Notes (R-D1, AR-7):** only if `slide.has_notes_slide` (avoid the create-on-access
    side effect) **and** `slide.notes_slide.notes_text_frame is not None` and its
    `.text.strip()` non-empty → `Slide.notes = that text`; else `None`.
- Return `Deck(slides=[...], source_name=path.name)`.

**Determinism (R-A5/I-1):** ordering is title-first → document order → groups
depth-first; no dict/set iteration. Locked by the 020-04 run-twice E2E, but the
ordering helper here must be pure.

### Test Cases

#### E2E Tests (update 020-01 smoke)
1. **TC-E2E-02 `test_extract_model_on_real_deck`** — `build_deck` on
   `tmp8/slides-4.pptx` (21 slides) → `len(deck.slides)==21`; slide 1 `blocks[0]` is
   a `Heading`; at least one `Bullets` block exists; no exception.

#### Unit Tests
1. **TC-UNIT-09 `test_encrypted_rejected`** — a fixture encrypted via
   `office_passwd.py --encrypt` → `assert_openable` raises `EncryptedFileError`;
   `main([...])` → exit 3 (`type=="EncryptedFileError"`). Legacy `.ppt` CFB fixture →
   same exit 3.
2. **TC-UNIT-10 `test_bad_input_not_pptx`** — a text file renamed `.pptx` → `BadInput`
   exit 1 (no traceback).
3. **TC-UNIT-11 `test_group_recursion`** — synthetic deck with a grouped text box →
   the inner text appears as a `Bullets` block (uses `tmp8/slides-2.pptx`, 7 groups).
4. **TC-UNIT-12 `test_title_first_regardless_of_order`** — synthetic slide where the
   title placeholder is authored AFTER a body box → `blocks[0]` is the `Heading`.
5. **TC-UNIT-13 `test_notes_absent_no_block_no_sideeffect`** — a notes-free slide →
   `Slide.notes is None` **and** `slide.has_notes_slide` stays `False` afterwards
   (no create-on-access). A deck with notes → `Slide.notes` populated.
6. **TC-UNIT-14 `test_hidden_slide_skipped`** — synthetic deck with `p:sld show="0"`
   → skipped by default; included with `--include-hidden`.
7. **TC-UNIT-15 `test_emf_or_unreadable_image_becomes_placeholder`** — a shape whose
   `image.ext` raises → a `Placeholder`, not an `ImageRef` (AR-1); `build_deck` does
   not raise.
8. **TC-UNIT-16 `test_table_to_rows`** — `tmp8/slodes-3.pptx` (2 tables) → at least
   one `Table` block with `len(rows) >= 2` and escaped cells.

#### Regression
- `validate_skill.py skills/pptx` exit 0; `diff` gates silent; 020-01 tests still green.

## Acceptance Criteria
- [ ] `assert_openable` rejects encrypted + legacy via the shared helper → exit 3 single type ([R-D3]).
- [ ] `build_deck` produces the model with title-first ordering, group recursion, bullets+levels, tables, notes-guarded, hidden-slide filter ([R-A1][R-A2][R-A3][R-A4][R-D1]).
- [ ] EMF/unreadable image → `Placeholder`, never a hard failure (AR-1 / [R-B3] partial).
- [ ] TC-E2E-02 + TC-UNIT-09..16 pass; regression green.

## Notes
- `images.safe_image_meta(shape)` is created REAL in **020-01** and is the single
  owner of the guarded `(blob, sha1, ext, content_type)` read (MAJOR-B). 020-02 uses
  it only for the ImageRef-vs-Placeholder decision; 020-03 reuses it for the file
  write — no duplication, no cross-bead inversion.
- `slodes-3.pptx` is the real (mistyped) filename — do not "fix" it.

# Task 020-03 [LOGIC]: `images.py` — blob → sidecar media, sha1 dedup, naming, link base

> **Predecessor:** 020-02 (document model with `ImageRef`/`Placeholder`).
> **RTM:** **completes** [R-B1][R-B2][R-B3].
> **ARCH:** §2.1 (FC-2), §4.2 (`MediaAsset`/`PlaceholderAsset`), §5.1 (link base), §10; AR-1/AR-2.

## Use Case Connection
- UC-1 (image extraction + links), UC-1/A2 (`--no-images`).

## Task Goal
Replace the `images` stub: write each `ImageRef`'s blob to the sidecar media dir
with a deterministic, dedup-stable name, and return the `ImageRef → MediaAsset` map
the emitter consumes.

## Changes Description

### Changes in Existing Files

#### File: `skills/pptx/scripts/pptx2md/images.py`

**Function `safe_image_meta(shape)`** — **already created REAL in 020-01 (MAJOR-B); do
NOT redefine here.** 020-03 *consumes* it (shared with 020-02): `(blob, sha1, ext,
content_type)` or `None` when any accessor raises. This bead owns only `materialise`.

**Function `materialise(deck, media_dir, link_base, *, no_images=False) -> dict[ImageRef, MediaAsset]`** — **REAL**:
- `no_images is True` → return `{}` and **do not create** `media_dir` (R-B3c).
- Walk slides in order; for each `ImageRef`:
  - Compute meta via the shape handle the model carries. If meta is `None` (or the
    block was already a `Placeholder`) → produce a `PlaceholderAsset(key=(slide,shape),
    kind=..., note=...)` + warning (R-B3); no file written.
  - **Dedup (R-B1d / MAJOR-3):** keep a `sha1 → MediaAsset` map. **First occurrence
    in reading order** (lowest `(slide, shape)`) owns the canonical filename
    `slide{N}-img{M}.{ext}` and is the only blob written to disk; later identical
    `sha1`s map to the **same** `MediaAsset` (no second file). `N` = slide index, `M`
    = per-slide running picture counter (1-based) of the FIRST occurrence.
  - Create `media_dir` lazily on the first real asset (idempotent `mkdir(parents=
    True, exist_ok=True)`); write the blob (`Path.write_bytes`).
  - `MediaAsset.rel_path` = `link_base` joined with `filename` (POSIX separators in
    the emitted link).
- Return `{ImageRef: MediaAsset|PlaceholderAsset}` for every image block.

**Link base (R-B2c / MAJOR-4 / D-7):** `materialise` consumes the `(media_dir,
link_base)` already computed by `cli._resolve_media_dir` (020-01) — file mode = path
relative to the `.md`; stdout mode = relative to `--media-dir` from CWD. On stdout
mode, `cli` emits a one-line stderr note "media written to <media_dir>".

### Test Cases

#### E2E Tests (update)
1. **TC-E2E-03 `test_images_extracted_and_linked`** — convert `tmp8/slides-1.pptx`
   → `<out>.media/` exists with ≥1 file; every `![](...)` link in the `.md` resolves
   to an existing file (relative to the `.md`).

#### Unit Tests
1. **TC-UNIT-17 `test_dedup_first_occurrence_wins`** — synthetic deck embedding the
   **same** image blob on slide 1 and slide 3 → exactly **one** file on disk; both
   `ImageRef`s map to the same `MediaAsset.filename` (the slide-1 name). Re-run →
   identical filename (determinism).
2. **TC-UNIT-18 `test_no_images_writes_nothing`** — `--no-images` → returns `{}` and
   `media_dir` is **not** created.
3. **TC-UNIT-19 `test_unreadable_image_placeholder`** — a shape whose `ext` raises →
   `PlaceholderAsset` keyed by `(slide,shape)`, no file, `materialise` does not raise (AR-1).
4. **TC-UNIT-20 `test_stdout_mode_link_base_relative_to_cwd`** — stdout mode →
   `MediaAsset.rel_path` is CWD-relative and the media files exist under the resolved
   `media_dir`; a stderr note is emitted.
5. **TC-UNIT-21 `test_filename_extension_from_content_type`** — a PNG blob → `.png`
   name; a JPEG blob → `.jpg`; deterministic `slide{N}-img{M}` numbering.

#### Regression
- `validate_skill.py skills/pptx` exit 0; `diff` gates silent; 020-01/02 tests green.

## Acceptance Criteria
- [ ] Images written to sidecar dir with `slide{N}-img{M}.{ext}` names ([R-B1]).
- [ ] Identical blobs deduped first-occurrence-wins → one file, stable name ([R-B1d], MAJOR-3).
- [ ] Links relative to `.md` (file mode) / CWD-`media-dir` (stdout mode) ([R-B2], MAJOR-4).
- [ ] EMF/unreadable → `PlaceholderAsset`, never a hard failure ([R-B3], AR-1).
- [ ] `--no-images` creates no media dir ([R-B3c]).
- [ ] TC-E2E-03 + TC-UNIT-17..21 pass; regression green.

## Notes
- `MediaAsset` filenames use the FIRST occurrence's `(slide, shape)` so naming and
  dedup are both deterministic (R-A5/I-1).
- **Blob flow (as-built, reconciled after the multi-critic roast):** image bytes
  travel from `extract` to `materialise` via a deck-level `Deck.blobs` side table
  (`sha1 → (bytes, content_type)`). The stored bytes **alias** the objects
  python-pptx already holds resident (`Image.blob` returns `self._blob` by
  reference), deduped by sha1 — so this is **not** a second copy and does not
  materially grow the footprint (the original "write each as encountered / do not
  buffer" wording assumed a single-pass writer; the extract→images→emit phase split
  makes a side table the cleaner seam, and the alias makes it memory-cheap). The
  unreadable-image→`Placeholder` decision is owned by `extract`; `materialise`'s
  `PlaceholderAsset` branch is a documented defensive guard.

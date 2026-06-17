# Task 022-05 [LOGIC]: `emit.py` — frontmatter + `_attachments` + dual-output + stdout (MVP GATE)

> **Predecessor:** 022-02 (`AcquireResult`), 022-03 (`core_bridge`), 022-04 (`CleanResult`).
> **RTM:** [R4] Obsidian emit, [R5] agent-step contract. **MVP gate.**
> **ARCH:** §2.1 (FC-4), §4.3 (emit artifacts), §4.4 (I-2 dedup), §5.1 (CLI), §11 (022-05).

## Use Case Connection
- UC-1 (self-contained Obsidian note, dual-output), UC-3 (agent step: stdout +
  `--no-download-images` + `--json-errors`). This bead closes the offline MVP.

## Task Goal
Implement FC-4 and glue `cli.main`/`convert` into the full **offline** pipeline:
`acquire → clean → core_bridge(whole, reader) → emit`. Produce YAML frontmatter,
optionally download images to `_attachments/` (sha1-dedup), and write dual-output
or stream to stdout.

## Changes Description
### `html2md/emit.py` (replace stub)
- **`_frontmatter(meta: SourceMeta) -> str`** — YAML block: `source`, `title`,
  `date`, `author`, `tags: []` (OQ-1: tags left empty in v1). Omit absent keys.
- **`_collect_and_rewrite_images(md, acq, opts) -> tuple[str, dict]`** — when
  `opts.download_images`: for each image ref, resolve bytes (archive/file: from
  `acq.images`; url: deferred fetch in 022-06 via a hook), sha1-key →
  `_attachments/<sha1>.<ext>`, rewrite link to the relative path; **I-2** identical
  bytes → one file shared across both variants; honor `--max-images`. When
  `--no-download-images`: leave remote URLs verbatim.
- **`emit(acq, clean, md_whole, md_reader, opts):**
  - Compose `<slug>.md` = frontmatter + md_whole; if `clean.reader_html is not
    None` also `<slug>.reader.md` = frontmatter + md_reader (**dual-output
    default**; `--no-reader` already made `reader_html None`).
  - **stdout mode:** write md_whole (and, unless `--no-reader`, a `---`-separated
    reader section? → NO; stdout emits the whole-page MD only, agent-friendly) to
    stdout; no files unless OUTPUT_DIR given.
  - Both `.md` files share ONE `_attachments/` (`--attachments-dir`).
  - Atomic write (temp + rename); self-overwrite already guarded in `_resolve_paths`.
- **`cli.convert(...)`** — programmatic API: runs the offline pipeline, returns
  the artifact paths / markdown. **`cli.main`** — replaces `_STUB_SENTINEL` with
  real exit codes; routes `_AppError`→envelope; `--json-errors` honored.

## Test Cases
### Unit
1. **TC-05-01 `test_frontmatter_shape`** — `source/title/date/author` present,
   `tags: []`; absent author omitted; valid YAML.
2. **TC-05-02 (AC-R4) `test_image_download_dedup`** — fixture with the same image
   twice → one `_attachments/<sha1>.png`, both links relative; file exists.
3. **TC-05-03 (AC-R4) `test_no_download_keeps_urls`** — `--no-download-images` →
   remote `https://` links preserved verbatim; `_attachments/` not created.
4. **TC-05-04 (AC-R4) `test_dual_output_default_and_no_reader`** — default →
   both `<slug>.md` + `<slug>.reader.md`, shared `_attachments/`; `--no-reader`
   → only `<slug>.md`.
5. **TC-05-05 (AC-R5) `test_stdout_and_json_errors`** — `--stdout` → MD on stdout,
   no files; forced failure under `--json-errors` → single-line `{v:1,...}`.
### E2E (MVP gate — full offline pipeline)
6. **TC-E2E-05a** `.webarchive` → `out/<slug>.md` + `<slug>.reader.md` +
   `_attachments/*`, **zero network** (AC-R1), images render.
7. **TC-E2E-05b** local `.html` → dual MD; `--no-download-images --stdout
   --no-reader` → single MD on stdout, no files.

## Acceptance Criteria
- [ ] **MVP**: offline `file`/`.webarchive`/`.mhtml` → dual MD + frontmatter +
      `_attachments/` (sha1-dedup) with one command.
- [ ] **AC-R4** image flag both directions + dual-output default + `--no-reader`.
- [ ] **AC-R5** stdout-only on success; `--json-errors` envelope on failure.
- [ ] **stdout contract:** `--stdout` emits the **whole-page MD only** (never
      the reader variant, no `---`-separated reader section) — back-ref ARCH §5.1.
- [ ] **AC-R1** offline determinism end-to-end (no network on archive/file).
- [ ] `_STUB_SENTINEL` removed; real exit-code map live.

## Notes
- **Scope escape-hatch (plan-review 🟡-1):** this is the densest logic bead
  (FC-4 + `cli.main`/`convert` glue + MVP E2E). If image-rewrite + pipeline-glue
  exceeds the 2–4h atomic target, split into **022-05a** (emit-core:
  frontmatter + images + dual-write) and **022-05b** (cli-glue: main/convert
  pipeline + exit-map) — the FC-4 seam supports the cut cleanly.
- The url-image download hook is stubbed to "resolve from `acq.images`" here;
  022-06 supplies the live-fetch resolver for `mode=url`.
- Adversarial roast focus: path-traversal in image filenames, atomic-write
  partial files on failure, dedup correctness across the two variants.

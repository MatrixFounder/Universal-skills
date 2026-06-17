# Task 022-02 [LOGIC]: `acquire.py` — OFFLINE input paths (file + archive dispatch)

> **Predecessor:** 022-01 (frozen surface + `web_clean` replica).
> **RTM:** [R1c] archive extraction, [R1d] local file read, [R1e] format dispatch.
> **ARCH:** §2.1 (FC-1), §4.1 (`AcquireResult`), §4.4 (I-3 offline determinism), §11 (022-02).

## Use Case Connection
- UC-2 (convert a downloaded archive, offline) — **real** in this bead.
- UC-1/UC-3 file-input variants — **real** for local `.html`.

## Task Goal
Implement the **network-free** half of FC-1: turn a local `.html`/`.htm`,
`.mhtml`/`.mht`, `.webarchive` into an `AcquireResult`. The URL path stays
stubbed (022-06). **Zero network calls** on every code path here (I-3).

## Changes Description
### `html2md/acquire.py` (replace stubs)
- **`_dispatch_format(path) -> str`** — `"file" | "archive"` by extension, with
  magic-byte fallback: first bytes `bplist00` → webarchive; `From `/`Content-Type:
  multipart/related` sniff → mhtml. Unknown extension + HTML-looking head → `file`.
- **`acquire(input, opts) -> AcquireResult`** (offline branches only):
  - **file:** read bytes → decode (charset from `<meta>`/BOM, fallback utf-8
    `errors="replace"`); resolve sibling `<page>_files/` images into a temp dir;
    `base_url = file://<dir>`; `source_meta` from `<title>`/OpenGraph (best-effort,
    no network); `images` map populated from local resolutions.
  - **archive:** delegate to `web_clean.extract_archive(src, work_dir,
    frame_spec=opts.archive_frame)` → `(html, base_url)`; sub-resource images
    already extracted by the replica (sha1-deduped); build `images` map from the
    archive's URL→local-path table; `--archive-frame`/`list_archive_frames`
    honored; `mode="archive"`, `engine=None`.
  - **url:** `raise NotImplementedError` (022-06) — but `_dispatch` must already
    route `http(s)://INPUT` to the url branch so 022-06 only fills the body.
- Temp-dir lifecycle: register cleanup on process exit (mirror pdf's pattern).

### Changes in Existing Files — none. No master edited (imports `web_clean` only).

## Test Cases
### Unit
1. **TC-02-01 `test_dispatch_by_extension_and_magic`** — `.html`→file, `.webarchive`
   (+ `bplist00` head)→archive, `.mhtml`→archive; extension-less HTML→file;
   `https://x`→url (routes, even though body raises).
2. **TC-02-02 `test_file_charset_fallback`** — windows-1251 fixture decodes to
   correct Cyrillic; undecodable bytes → `errors="replace"`, no raise.
3. **TC-02-03 `test_archive_frame_selection`** — `.webarchive` with N subframes:
   `--archive-frame main` vs `1` vs `all` produce expected `html` length deltas;
   `list_archive_frames` exposes index/substantial flags.
4. **TC-02-04 (I-3) `test_offline_zero_network`** — monkeypatch `httpx`/socket to
   raise on any call; `acquire` on a file + a webarchive completes successfully
   (proves no network egress).
5. **TC-02-05 `test_source_meta_best_effort`** — `<title>`/`og:title` populate
   `source_meta.title`; absent → `None`, no crash.

### E2E
- **TC-E2E-02** `html2md.py <fixture>.webarchive out/ --no-download-images
  --json-errors` exits 0 (downstream still stubbed until 022-05 → assert via the
  `convert` seam returning the `AcquireResult`, or keep E2E asserting `main`
  reaches the clean stub). *(E2E tightened to full pipeline in 022-05.)*

## Acceptance Criteria
- [ ] `_dispatch_format` correct for all 5 extensions + magic-byte fallbacks.
- [ ] file + archive branches return a well-formed `AcquireResult` (ARCH §4.1).
- [ ] **I-3**: zero network calls on file/archive paths (TC-02-04 green).
- [ ] `--archive-frame main|N|all` honored via the `web_clean` replica.
- [ ] url branch still `NotImplementedError` (owned by 022-06); dispatch routes it.
- [ ] No master edited; G-1 `diff -q` still silent.

## Notes
- All HTML handling here is **string-level** (the replica is regex/stdlib) — the
  only real DOM parse happens later in the Node core (I-1).
- `httpx` must not be imported at module top (keep the file importable without it).

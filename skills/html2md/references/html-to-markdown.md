# html2md — conversion guide & honest scope

## Decision tree

```
INPUT?
├── http(s):// URL
│     --engine lite (default in auto)  → httpx + trafilatura   (fast, no browser)
│     page is a JS/SPA shell?          → auto-fallback to Chrome (needs --with-chrome)
│     --engine chrome                  → force headless Chromium
├── .webarchive / .mhtml (saved archive)   → offline; pick subframe with --archive-frame
└── .html / .htm (saved page)              → offline; sibling <page>_files/ images resolved
```

## Reader vs whole (dual-output)

By default BOTH are written:
- `<slug>.md` — the **whole** page after chrome/ad/icon strip (`preprocess`).
- `<slug>.reader.md` — **article-extracted** via the pdf-9 reader-mode + universal
  SPA-chrome heuristic (drops nav/sidebar/banner/footer).

`--no-reader` emits only `<slug>.md`. The whole-page file is always the faithful
fallback when reader extraction degrades (e.g. landmark-free SPA).

## Images

`--download-images` (default) downloads every resolvable image into
`_attachments/<sha1>.<ext>` (deduped by content hash, shared across both variants) and
rewrites links to relative paths — a self-contained Obsidian note. `--no-download-images`
keeps the original (remote) URLs verbatim — the right choice for a quick agent step.

`--attachments-dir NAME` renames the folder (default `_attachments`).

## Engine selection

| Engine | When | Cost |
|---|---|---|
| `lite` (default) | static articles, blogs, docs | sub-second, no browser |
| `chrome` | JS-hydrated SPAs (CRM/portal), `<canvas>` | ~1–3 s + ~150 MB Chromium (opt-in) |
| `auto` | unknown — lite, fall back to chrome if the body is a JS shell | best of both |

Chrome is **soft-optional**: `bash scripts/install.sh --with-chrome`. Without it,
`--engine chrome` exits 3 (`EngineNotInstalled`) with remediation.

## Honest scope / limitations

- **Markdown fidelity** inherits the turndown core: rowspan/colspan collapse to a flat
  grid (anchor value + blanks); inline CSS / classes are ignored.
- **Fetch coverage**: paywalled / auth-gated pages are out of scope; JS/SPA pages only
  convert via the Chrome engine. `robots.txt` / rate-limiting / ToS compliance is the
  **caller's** responsibility.
- **SSRF**: the lite path blocks private/loopback/link-local/metadata targets on every
  redirect hop and streams with a `--max-bytes` cap. **NOT** covered: (a) DNS rebinding
  (resolve-then-connect TOCTOU); (b) the Chrome engine (basic `launch + goto`, follows
  internal redirects, no beacon blocking). **Run untrusted conversions in a
  network-egress-restricted sandbox.**
- **Local image reads** are confined to the input's base directory — a crafted
  `<img src="../../secret">` cannot exfiltrate off-disk files into the vault.
- **Reader extraction** is best-effort; the whole-page `.md` is the fallback.
- **Metadata** (`title`/`date`/`author`) is best-effort (trafilatura / OpenGraph /
  `<title>`); `tags: []` is left for the user to fill in Obsidian.

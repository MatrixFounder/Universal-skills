# html2md — conversion guide & honest scope

## Decision tree

```
INPUT?
├── http(s):// URL
│     --engine lite (default in auto)  → httpx + trafilatura   (fast, no browser)
│                                         · retries transient fails (5xx/429/transport)
│                                         · 403 → one auto browser-UA retry
│     page is a JS/SPA shell?          → auto-fallback to Chrome (needs --with-chrome)
│     --engine chrome                  → force headless Chromium
│     still blocked (Cloudflare)?      → --engine jina  (r.jina.ai, external; no browser)
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
| `jina` | JS/anti-bot/Cloudflare pages **without** a local browser | external HTTPS round-trip; rate-limited keyless |

Chrome is **soft-optional**: `bash scripts/install.sh --with-chrome`. Without it,
`--engine chrome` exits 3 (`EngineNotInstalled`) with remediation.

**Fetch robustness** (lite path, all engines that use it): `--retries N` (default 2)
retries transport errors / HTTP 5xx / 429 with exponential backoff (429 honours
`Retry-After`); a **403 auto-escalates once to a browser User-Agent** (default UA stays
the honest `html2md/…`). `--rate-limit REQS_PER_SEC` throttles outbound fetches.

**`--engine jina`** routes through Jina Reader (`r.jina.ai`), which renders + cleans the
page **server-side** and returns HTML to our pipeline — no local Chromium. It is
**explicit-only** (never part of `auto`) because the **target URL is sent to an external
service**; don't use it for sensitive/internal URLs. Keyless (rate-limited) by default;
`JINA_API_KEY` raises the quota. Use it as the escalation when a browser-UA lite fetch is
still blocked and you'd rather not install Playwright.

**No-JS host variants (JS-gated bodies).** Some hosts gate the article body behind JS on
the canonical URL but serve full HTML at a sibling path, and **Chrome rendering does not
unlock it** — the URL rewrite does. `--engine auto` handles the known case automatically:
**HackerNoon** `…/<slug>` → fetched from `…/lite/<slug>` (engine reported as `lite+nojs`).
For other such hosts, pass the no-JS / AMP / print URL yourself, or try `--engine jina`.

**Failure diagnostics (for agent callers).** A `FetchFailed` (exit 10) envelope carries
`details.status` (the HTTP code) and `details.kind` — one of `bot_blocked` (403; try
`--engine jina`/`chrome`), `auth_required` (login/paywall → manual), `rate_limited` (429;
back off / `--rate-limit`), `not_found`, `server_error` (retry), or `unreachable`
(transport). `details.url` keeps the meaningful query (only secret params are redacted).

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
- **Reader extraction** is best-effort; the whole-page `.md` is the fallback. For a clean
  body on the agent step prefer the `.reader.md` variant over `--stdout` (whole-page).
  On **chrome-heavy sites a saved `.html` converts dirtier than the live URL** — the
  offline `spa-largest-contentful-subtree` heuristic can keep site nav (e.g. a16z); a live
  `--engine lite` (trafilatura) is cleaner. Prefer the live URL when you have it.
- **Metadata** (`title`/`date`/`author`) is best-effort: the **date** prefers explicit
  structured metadata (`article:published_time` / `og:published_time` / `itemprop` /
  JSON-LD `datePublished`) and an arXiv-id heuristic over trafilatura's body-text guess;
  `tags: []` is left for the user to fill in Obsidian.

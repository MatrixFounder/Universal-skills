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
| `lite` | static articles, blogs, docs | sub-second, no browser |
| `chrome` | JS-hydrated SPAs (CRM/portal), `<canvas>` | ~1–3 s + ~150 MB Chromium (opt-in) |
| `auto` (default) | unknown — **local-first ladder**: `lite → chrome → remote` last-resort | best of both; remote only if local fails (public targets) |
| `jina` | JS/anti-bot/Cloudflare **without** a local browser | remote-first via `r.jina.ai`, **auto-falls back** to lite/chrome; rate-limited keyless |
| `remote` | a self-hosted / non-jina reader | remote-first via `HTML2MD_READER_URL`/`_PROVIDERS`; **requires** a configured provider |

**The fallback ladder (no single point of failure).** `auto` tries local engines first and
escalates to the remote reader only as a last resort; `jina`/`remote` try the reader first and
fall back to local. If a remote reader is down / 429 / 402 / 5xx, the ladder moves to the next
configured provider, then to `lite`/`chrome`. Only when **every** viable tier is exhausted does
the run fail — `FetchFailed (kind=all_engines_failed)` with a `details.tried` trace. So a Jina
outage never kills a conversion.

**Vendor-agnostic remote tier + privacy.** The remote reader is pluggable: `jina` (`r.jina.ai`)
is the built-in default; set `HTML2MD_READER_URL=https://reader.internal/` (or an ordered
`HTML2MD_READER_PROVIDERS` list) to use a **self-hosted Jina** or any compatible reader — then a
jina.ai outage is irrelevant. Auth is per-provider (`JINA_API_KEY` for jina;
`HTML2MD_READER_TOKEN` for a generic reader). The remote tier **sends the target URL to an
external service**, so: a private/internal/loopback target is **never** forwarded (public-IP
gate); `--no-remote` disables the tier outright (fully local); CR/LF in the target is refused.
`--remote-format markdown` trusts the reader's own clean Markdown (bypasses local cleaning);
`--target-selector SEL` (default `article, main, [role=main]`) extracts just the article block.

Chrome is **soft-optional**: `bash scripts/install.sh --with-chrome`. Without it,
`--engine chrome` exits 3 (`EngineNotInstalled`) with remediation.

**Fetch robustness** (lite path, all engines that use it): `--retries N` (default 2)
retries transport errors / HTTP 5xx / 429 with exponential backoff (429 honours
`Retry-After`); a **403 auto-escalates once to a browser User-Agent** (default UA stays
the honest `html2md/…`). `--rate-limit REQS_PER_SEC` throttles outbound fetches.

**Web search (`--search "QUERY"`).** A vendor-agnostic search provider (`s.jina.ai` default;
override with `HTML2MD_SEARCH_URL` / `HTML2MD_SEARCH_PROVIDERS`) returns the top result URLs;
**each URL is fetched through the same fallback ladder** (so every result inherits per-result
fallback) and written as one note (frontmatter `query:` + `source:`), sharing one
`_attachments/`. `--max-results N` bounds the count (default 5). A result whose own fetch fails
is skipped (not fatal); a healthy zero-result search exits 0; if every search provider is down
the run fails with `FetchFailed (kind=all_engines_failed)`. `--search` is mutually exclusive
with a URL/file INPUT (the first positional is the OUTPUT_DIR).

**Clean-source host variants (proactive rewrites).** Some hosts serve a clean article only
at a sibling endpoint while the canonical URL is JS-gated or chrome-heavy, and **Chrome
rendering does not help** — the URL rewrite does. `--engine auto`/`lite` rewrite these
automatically (the canonical URL stays the note's `source:` provenance):

| Host | canonical | fetched instead | engine reported |
|---|---|---|---|
| Wikipedia | `…/wiki/<Title>` | `…/api/rest_v1/page/html/<Title>` (Parsoid) | `lite+restapi` |
| arXiv | `…/abs/<id>` or `…/pdf/<id>` | `…/html/<id>` (full text) | `lite+arxiv-html` |
| HackerNoon | `…/<slug>` | `…/lite/<slug>` | `lite+nojs` |

The canonical Wikipedia `/wiki/` page is chrome-heavy and the (pdf-mastered) `preprocess`
strips its body to nothing — the REST endpoint returns just the article. arXiv `/abs/` is
only an abstract and `/pdf/` is a binary PDF; `/html/` carries the full paper **when it
exists** — older PDF-only papers 404 and surface `details.kind="arxiv_no_html"` with a
"fetch the PDF and use the pdf skill" hint. Relative `<a href>`/`<img src>` in these
endpoints' HTML are resolved against the document's `<base href>`. For other JS-gated
hosts, pass the no-JS / AMP / print URL yourself, or try `--engine jina`.

**Empty-extraction guard.** If a substantial source page (≥ ~2 KB HTML) converts to a
near-empty whole-page body, the run fails with **`EmptyExtraction` (exit 11)** instead of
silently writing an empty note — so an agent caller can retry with `--engine chrome`/`jina`
or a site-specific endpoint rather than importing nothing.

**Failure diagnostics (for agent callers).** A `FetchFailed` (exit 10) envelope carries
`details.status` (the HTTP code) and `details.kind` — one of `bot_blocked` (403; try
`--engine jina`/`chrome`), `auth_required` (login/paywall → manual), `rate_limited` (429;
back off / `--rate-limit`), `not_found`, `server_error` (retry), `unreachable`
(transport), `pdf`/`binary` (non-HTML payload → use the pdf skill), or `arxiv_no_html`
(PDF-only arXiv paper → use the pdf skill). `details.url` keeps the meaningful query (only
secret params are redacted). A separate `EmptyExtraction` (exit 11) means the fetch
*succeeded* but extraction produced an empty body (retry with another engine/endpoint).

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

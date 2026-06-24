# html2md Manual

Practical reference for the [`html2md`](../../skills/html2md/) skill —
**Web/HTML → Markdown**: a web-clipper for Obsidian notes and a universal
HTML→Markdown step for agent workflows.

This manual is for **users** of the skill. The authoritative contract is
[`skills/html2md/SKILL.md`](../../skills/html2md/SKILL.md); the decision tree
and honest-scope notes are in
[`references/html-to-markdown.md`](../../skills/html2md/references/html-to-markdown.md);
the maintainer / replication protocol (this skill is the repo's first
**two-master** skill) is in [CONTRIBUTING.md §3](../CONTRIBUTING.md#3-office-skills-modification-protocol-strict).

`html2md` is **Proprietary, All Rights Reserved** (it embeds byte-identical
copies of proprietary docx/pdf code; it is a derived work and is **not**
Apache-2.0). See [`skills/html2md/LICENSE`](../../skills/html2md/LICENSE).

---

## 1. What it does

| Input | → | Output |
|---|---|---|
| a live **URL** (`http(s)`) | → | clean Markdown + frontmatter + downloaded images |
| a saved **`.html` / `.htm`** | → | same, fully offline |
| a Safari **`.webarchive`** | → | same (subresources extracted from the archive) |
| a Chrome **`.mhtml` / `.mht`** | → | same (subframe-aware) |

Two consumers in mind:

1. **Obsidian web-clipper** — a self-contained note: YAML frontmatter
   (`source`, `title`, `date`, `author`), a shared `_attachments/` folder with
   sha1-deduped images, and Markdown links rewritten to those local files.
2. **Universal agent step** — `--stdout` emits whole-page Markdown to stdout and
   `--json-errors` emits a single-line failure envelope, so any workflow can pipe
   a page through it.

It reuses hardened code from two skills (fork-free): the **docx turndown core**
(GFM tables, rowspan→flat grid) and the **pdf `web_clean` cleaner** (reader-mode
extraction, SPA-chrome stripping, archive decoding). On top it adds html2md-owned
conversion for modern doc sites (see [§6](#6-what-the-converter-fixes)).

---

## 2. One-time setup

```bash
cd skills/html2md/scripts
bash install.sh                 # creates .venv (httpx, trafilatura) + node_modules (turndown, turndown-plugin-gfm)
bash install.sh --with-chrome   # ALSO installs Playwright Chromium (only needed for JS/SPA pages)
```

No global installs — Python deps live in `scripts/.venv`, Node deps in
`scripts/node_modules`. The lite engine (default) needs only the base install;
Chrome is opt-in and only required for pages that render their content with
JavaScript.

**Skill-local config (encapsulation).** Copy [`.env.example`](../../skills/html2md/.env.example)
to `skills/html2md/.env` and the CLI **auto-loads it at startup** — the config (auth map, scroll,
Jina key, reader providers) lives *with the skill*, so **any** caller (a project, an importer, a
cron job — anything that runs `html2md.py`) gets it transparently, with no `export` and no machine-
global env pollution. The process environment still wins (callers can override per-run); `chmod 600`
the file (a group/world-readable `.env` is ignored with a warning); `HTML2MD_NO_DOTENV=1` disables
auto-load. See [§5b](#5b-authenticated-login-gated-chrome) for the chrome/auth keys.

Smoke test:

```bash
python3 scripts/html2md.py examples/sample.html /tmp/h2m && ls /tmp/h2m
```

---

## 3. Command-line reference

```
python3 scripts/html2md.py INPUT [OUTPUT_DIR] [flags]
```

| Argument / flag | Default | Meaning |
|---|---|---|
| `INPUT` | — | `http(s)` URL, or local `.html`/`.htm`/`.mhtml`/`.mht`/`.webarchive` |
| `OUTPUT_DIR` | `./tmp/html2md_out/` | where `<slug>.md`, `<slug>.reader.md`, `_attachments/` are written (created on demand) |
| `--stdout` | off | print whole-page Markdown to stdout instead of writing files |
| `--engine lite\|chrome\|auto\|jina\|remote` | `auto` | fetch engine for URLs — resilient ladder (see [§5](#5-engines--the-resilient-fallback-ladder)) |
| `--no-remote` | off | disable the remote-reader tier entirely (no URL ever sent to an external reader) |
| `--remote-format html\|markdown` | `html` | what a remote reader returns: HTML through the local pipeline, or trust the reader's own Markdown |
| `--target-selector SEL` | `article, main, [role=main]` | `X-Target-Selector` sent to the remote reader (article block) |
| `--search "QUERY"` | — | web-search mode: top results → Markdown notes (mutually exclusive with INPUT; the positional is then OUTPUT_DIR) |
| `--max-results N` | `5` | for `--search`: max results to fetch + convert |
| `--chrome-storage-state PATH` | — | authed Chrome: Playwright `storage_state` JSON (mint via `login`); server-deployable. See [§5b](#5b-authenticated-login-gated-chrome) |
| `--chrome-cookies-file PATH` | — | authed Chrome: Netscape `cookies.txt` (cookie-only session) |
| `--chrome-user-data-dir DIR` | — | authed Chrome: persistent profile (local only) — the `--chrome-*` auth sources are mutually exclusive + force `--engine chrome` |
| `--chrome-auth-map PATH` | — | authed Chrome for **multiple sites**: JSON map `host → {cookies_file\|storage_state}`; forces chrome only for a **mapped** target domain. See [§5b](#5b-authenticated-login-gated-chrome) |
| `--chrome-scroll` / `--chrome-scroll-passes N` | off / `8` | scroll to pull lazy content (replies); bounded by passes + a 60 s cap |
| `login URL [--save-state PATH]` | `./html2md-state.json` | **subcommand** — open a headful browser, log in by hand, save the session |
| `--reader-mode` / `--no-reader` | reader **on** | also emit `<slug>.reader.md` (article-extracted) / suppress it |
| `--download-images` / `--no-download-images` | download **on** | fetch images into `_attachments/` / keep remote URLs as-is |
| `--max-images N` | unbounded | cap the number of **remote** image fetches (SSRF amplification bound) |
| `--max-bytes N` | unbounded | abort a fetch whose body exceeds N bytes (streamed) |
| `--retries N` | `2` | transient-failure retries per fetch (transport errors / HTTP 5xx / 429 w/ backoff); `0` disables |
| `--rate-limit REQS_PER_SEC` | unbounded | throttle outbound fetches (page + images) — polite bound for image-heavy pages |
| `--attachments-dir NAME` | `_attachments` | name of the sidecar image folder |
| `--archive-frame main\|N\|all\|auto` | `main` | which frame of a multi-frame `.mhtml`/`.webarchive` to convert |
| `--json-errors` | off | emit failures as `{v, error, code, type, details}` on stderr |

**Slug**: `<slug>` is derived deterministically from the input filename / URL
path; the human-readable title lives in frontmatter. Distinct inputs that
slugify to the same stem get a `-2`, `-3` suffix (idempotent via a hidden
`html2md-source-id` marker — re-running the *same* input overwrites in place,
it does not pile up duplicates).

### Exit codes

| Code | Meaning |
|---|---|
| `0` | success |
| `1` | BadInput / ConvertFailed / internal error |
| `2` | usage error (bad arguments; also `--search` + a URL, `--engine remote` with no provider configured, `--max-results` ≤ 0) |
| `3` | EngineNotInstalled — **explicit** `--engine chrome` but Playwright absent (run `install.sh --with-chrome`). In `auto`/remote-first this is a silent fall-through, not exit 3 |
| `6` | SelfOverwriteRefused — output path would clobber the input |
| `10` | FetchFailed — unreachable / blocked (HTTP 4xx/5xx) / over `--max-bytes` / **PDF or binary** payload |
| `11` | EmptyExtraction — fetch succeeded but a substantial source converted to a near-empty body |

With `--json-errors`, stderr carries `{"v":1,"error":"…","code":10,"type":"FetchFailed","details":{…}}`.
For a fetch failure, `details` includes **`status`** (the HTTP code) and **`kind`** —
`bot_blocked` (403 → try `--engine jina`/`chrome`), `auth_required` (login/paywall →
manual), `rate_limited` (429), `not_found`, `server_error` (retry), `unreachable`
(transport), `pdf`/`binary`, `arxiv_no_html` (PDF-only arXiv paper → use the pdf skill),
`refused` (non-public target / CR/LF in target), or **`all_engines_failed`** (every tier
of the fallback ladder was exhausted — `details.tried` lists each tier + its failure kind,
URL-free) — so a calling agent can branch on manual-vs-retry. `details.url` keeps the meaningful
query (only secret params are redacted). **Clean-source host variants** are auto-recovered
by `--engine auto`/`lite`: **Wikipedia** `/wiki/<Title>` → REST `page/html` (`lite+restapi`),
**arXiv** `/abs`|`/pdf/<id>` → `/html/<id>` (`lite+arxiv-html`), **HackerNoon** → `/lite/`
(`lite+nojs`). `EmptyExtraction` (exit 11) is the guard against silent empty notes.

---

## 4. Outputs

For `OUTPUT_DIR` mode (the default), a single input produces:

```
OUTPUT_DIR/
  <slug>.md            # whole page (everything that survived cleaning)
  <slug>.reader.md     # reader-extracted (main article only) — unless --no-reader
  _attachments/
    <sha1>.<ext>       # downloaded images, deduped by content hash
```

Frontmatter (both variants):

```yaml
---
source: "https://example.com/article"
title: "The Real Title"
date: "2026-06-17"
author: "Jane Doe"
tags: []
---
```

- **`<slug>.md` (whole)** — the full page after chrome-stripping. Use it when you
  want everything (nav-as-links, sidebars rendered cleanly, footers).
- **`<slug>.reader.md` (reader)** — the main article only, via the pdf-mastered
  reader-mode extractor. Best for blog posts / articles. Note: doc-site SPAs
  (GitBook/Mintlify/Fern) defeat article extraction, so for those the reader
  variant is close to the whole variant — rely on the whole `.md` there.

---

## 5. Engines & the resilient fallback ladder

| Engine | How | When |
|---|---|---|
| `lite` | `httpx` GET + `trafilatura` (also yields title/date/author) | server-rendered HTML (most docs, blogs, news) |
| `chrome` | headless Chromium via Playwright (`--with-chrome`) | JS/SPA pages whose content is hydrated client-side |
| `auto` *(default)* | **local-first ladder**: `lite → chrome → remote` last-resort | unknown pages — let the skill decide |
| `jina` | **Jina Reader** (`r.jina.ai`), remote-first **+ automatic local fallback** | JS/anti-bot/Cloudflare without a local browser |
| `remote` | a **configured** vendor-agnostic reader, remote-first + local fallback | self-hosted Jina / another reader; requires a provider |

**The ladder never has a single point of failure.** Each engine defines a tier order;
a tier that is down/blocked/rate-limited **falls through** to the next, and the run fails
(once, with `kind=all_engines_failed` + a `details.tried` trace) only when *every* viable
tier is exhausted. So a Jina outage, a 429, or a quota error no longer kills a conversion —
it falls back to the local engines (and vice-versa). `auto` stays local-first (privacy);
`jina`/`remote` are remote-first with local fallback. `EngineNotInstalled` from chrome
reached as an *auto* fallback is a silent fall-through; an **explicit** `--engine chrome`
without Playwright still exits 3.

**Vendor-agnostic remote tier.** `jina` (`r.jina.ai`) is the built-in default, but point
the remote tier at a **self-hosted Jina** or any compatible reader with
`HTML2MD_READER_URL=https://reader.internal/` (or an ordered `HTML2MD_READER_PROVIDERS`
list) — then a jina.ai outage is irrelevant. Auth is per-provider: `JINA_API_KEY` for jina,
`HTML2MD_READER_TOKEN` for a generic reader. `--remote-format markdown` trusts the reader's
own clean Markdown (skips the local clean/turndown); `--target-selector` extracts just the
article block.

**Privacy.** The remote tier **sends the target URL to an external service** — in `auto`
this is an automatic last-resort escalation for **public** targets (so a Cloudflare page
recovers with no flags), meaning a public URL may leave the machine on escalation. Guards:
a private/internal/loopback/metadata target is **never** forwarded to a reader; `--no-remote`
disables the remote tier entirely (fully local); CR/LF in the target/query is refused. Use
`--no-remote` for sensitive/internal conversions.

**Fetch robustness (lite HTTP path):** transient failures (transport, HTTP 5xx, 429) are
**retried with exponential backoff** (`--retries`, default 2; 429 honours `Retry-After`);
a **403** triggers one automatic escalation to a real-browser User-Agent (the default UA is
the honest `html2md/…`). This recovers most anti-scraper 403s with no flags.

> **Latency note:** tiers run sequentially and each has its own retry budget, so a target
> that times out on every tier can take minutes (no aggregate deadline yet — see
> `KNOWN_ISSUES` HTML2MD-9). For bulk/untrusted runs pass `--retries 0`, `--rate-limit`, and
> an explicit `--max-bytes`.

## 5a. Web search (`--search`)

`html2md.py --search "QUERY" [OUTPUT_DIR] [--max-results N]` runs a vendor-agnostic web
search (`s.jina.ai` default; `HTML2MD_SEARCH_URL`/`HTML2MD_SEARCH_PROVIDERS` to override),
takes the top results, and fetches **each result URL through the same fallback ladder** (so
every result inherits per-result Jina/local fallback), writing **one note per result**
(frontmatter `query:` + `source:`), sharing one `_attachments/`. A result whose own fetch
fails is skipped (not fatal); a healthy zero-result search exits 0; if every search provider
is down the run fails with `all_engines_failed`. For safety, search-result URLs do **not**
escalate to the Chrome tier unless you explicitly pass `--engine chrome`. (`--search` cannot be
combined with `--chrome-*` auth — a session must not fan out across search results.)

---

## 5b. Authenticated (login-gated) Chrome

Read pages behind a login (X **Articles**/threads, paywalled/members, private docs) by replaying
a **human-minted** session — html2md never automates login/passwords/2FA.

**Mint once** (interactive, where a browser exists):
```bash
python3 scripts/html2md.py login https://x.com --save-state ~/.html2md/x.json
```
A headful browser opens — your **real system Chrome** when installed (less bot-detectable),
else bundled Chromium — with the automation signal suppressed (`navigator.webdriver` masked) so a
first-party login isn't refused as an "automated browser". Log in by hand (2FA ok) → press Enter →
a `0600` `storage_state.json` (cookies + localStorage) is written.

> **⚠️ Google / "Continue with Google" SSO is blocked.** Google's OAuth bot-detection refuses
> automation-controlled browsers (*"this browser or app may not be secure"*) and our de-automation
> does **not** reliably defeat it (chasing it is an arms race we don't play). Two ways around it:
> 1. **Log into the site directly** with email/password (X has a native form) instead of the Google
>    button — the mint window then works.
> 2. **Export cookies from your everyday browser** (where you're already logged in via Google) with
>    a "Get cookies.txt LOCALLY" / Cookie-Editor extension, `chmod 600` the file, and skip `login`:
>    ```bash
>    python3 scripts/html2md.py "https://x.com/i/article/<id>" out/ --engine chrome \
>        --chrome-cookies-file ~/.html2md/x-cookies.txt --chrome-scroll
>    ```
>    This is the **most robust** path for Google-SSO accounts — the login already happened in a
>    trusted browser, so Google never sees automation.

**Then convert headless** (one auth source, mutually exclusive; any of them forces `--engine chrome`):
```bash
python3 scripts/html2md.py "https://x.com/i/article/<id>" out/ --engine chrome \
    --chrome-storage-state ~/.html2md/x.json --chrome-scroll
```
| Flag / env | Carries | Notes |
|---|---|---|
| `--chrome-storage-state` / `HTML2MD_CHROME_STORAGE_STATE` | cookies + localStorage | **primary**; portable, read-only → **server-deployable + concurrency-safe** |
| `--chrome-cookies-file` / `HTML2MD_CHROME_COOKIES_FILE` | cookies only (Netscape `cookies.txt`) | cookie-only sessions |
| `--chrome-user-data-dir` / `HTML2MD_CHROME_USER_DATA_DIR` | full persistent profile | local only (mutable, single-concurrency; survives 2FA) |
| `--chrome-auth-map` / `HTML2MD_CHROME_AUTH_MAP` | a **per-domain map** to any of the above | multiple logged-in sites; routes by target domain |

### Multiple logged-in sites — the auth map

One fixed source (above) holds whatever domains its file contains, but a single `cookies.txt`
with **all** your sites is one big credential. To keep a **small blast radius** and route
automatically, use a **per-domain auth map**: a JSON file mapping each site's domain to its own
credential file.

`~/.html2md/auth-map.json`:
```json
{
  "x.com":      { "cookies_file":  "~/.html2md/x-cookies.txt" },
  "medium.com": { "cookies_file":  "~/.html2md/medium-cookies.txt" },
  "github.com": { "storage_state": "~/.html2md/gh-state.json" }
}
```

**Permissions — the map AND every file it points to must be `0600`** (html2md refuses any file
readable by group/world, and refuses symlinks):
```bash
mkdir -p ~/.html2md
chmod 700 ~/.html2md                       # dir: only you can list it
chmod 600 ~/.html2md/auth-map.json         # the map (paths inside it)
chmod 600 ~/.html2md/x-cookies.txt \
          ~/.html2md/medium-cookies.txt \
          ~/.html2md/gh-state.json         # every referenced credential
ls -l ~/.html2md/                          # each must show -rw------- (600)
```

Then point html2md at the map (per-run flag, or set it once in the environment):
```bash
# per-run:
python3 scripts/html2md.py "https://medium.com/@user/post" out/ \
    --chrome-auth-map ~/.html2md/auth-map.json --chrome-scroll

# or set-and-forget (auto-used for mapped domains only):
export HTML2MD_CHROME_AUTH_MAP=~/.html2md/auth-map.json
python3 scripts/html2md.py "https://x.com/i/article/<id>" out/      # → authed chrome (x.com mapped)
python3 scripts/html2md.py "https://example.com/blog" out/         # → normal ladder (not mapped)
```

Behaviour:
- The map **forces `--engine chrome` only for a mapped domain**; an unmapped target keeps the
  normal local-first ladder (so a set-and-forget map does **not** turn every public page into a
  browser render).
- A mapped domain with no valid session → `FetchFailed kind=auth_required` (refresh that one file).
- **Matching is a label-boundary domain suffix** (not eTLD+1): a `x.com` key covers `x.com` and any
  subdomain (`www.x.com`, `mobile.x.com`); the **most specific** key wins if several match. **Key the
  exact domain you control** — on shared platforms (`*.github.io`, `*.s3.amazonaws.com`, `*.co.uk`)
  use your full subdomain (`mybucket.s3.amazonaws.com`), never the bare apex, so a credential is
  **never** routed to a sibling tenant.
- Each entry names **exactly one** credential (`cookies_file` **or** `storage_state`); a referenced
  `storage_state` is `0600`-enforced (symlink-rejected) just like a `cookies_file`. Both the map and
  every file it points to must be `0600`.
- The map is **mutually exclusive** with a single fixed `--chrome-*` source and with `--search`.
- There is **no per-site routing beyond this** — it is one map of `domain → file`, not a rules engine.

`--chrome-scroll [--chrome-scroll-passes N]` scrolls to pull lazy replies (bounded by passes + a
60 s wall-clock — never hangs); also settable via `HTML2MD_CHROME_SCROLL=1` /
`HTML2MD_CHROME_SCROLL_PASSES=N` for env-only callers (e.g. an importer that forwards env but not
flags). **X articles/threads need scroll** — without it the render extracts an empty body. A
stale/expired session → `FetchFailed kind=auth_required` (re-mint).
**Security:** the Chrome tier is **SSRF-gated** (private + off-target-public redirects refused;
non-public sub-resources aborted); session files are bearer credentials — path/env only (never
argv), `0600` enforced (group+world refused). Auth is **opt-in / additive**: with none set,
behaviour is byte-for-byte the default ladder (no crash). **Server deploy** (e.g. an *example*
Hermes box): mint on a workstation → ship the `storage_state.json` as a 0600 secret
(`HTML2MD_CHROME_STORAGE_STATE`) → render headless; rotate = re-mint + redeploy. See
`skills/html2md/.env.example` and `references/html-to-markdown.md` (full deploy + Jina-key matrix).

---

## 6. What the converter fixes

Beyond the shared turndown core, html2md-owned rules clean up patterns that
plain turndown gets wrong on real web pages:

- **ARIA-role tables → GFM.** GitBook/Mintlify/Fern render tables as
  `role="table"/"row"/"columnheader"/"cell"` divs (not real `<table>`), which
  turndown would flatten to stray paragraphs. Rebuilt into GFM tables (with the
  header pulled from a sibling `rowgroup` when needed).
- **Chrome stripping.** Standalone boilerplate lines (`Copy`, `Search…`,
  `Ask AI`, `Was this page helpful?`, AI-assistant widgets) are dropped
  conservatively — only high-confidence exact matches, never generic words.
- **Empty / split headings merged.** Doc sites emit a heading whose only content
  is an icon/anchor link, with the title text in a sibling — turndown produces
  `### ` then the title on its own line. They are merged back to `### Title`.
- **Multi-line links collapsed.** Nav anchors wrapping block content produce
  `[\n\ntext\n\n](url)` (broken Markdown) — collapsed to one line; icon-only /
  zero-width anchors are dropped.
- **arXiv / LaTeXML code listings.** `div.ltx_listing` (used by ar5iv papers,
  NOT `<pre>`) becomes a fenced code block, dropping the line-number gutter that
  would otherwise glue onto the first token (`1PROMPT_TEMPLATE`).
- **`data:` URI blobs stripped.** Base64 `data:` images and links (mascots,
  inline download buttons) are removed instead of dumping kilobytes of base64
  into the Markdown.
- **Image URLs resolved.** For URL inputs, relative `<img src="x1.png">` is
  absolutized against the document's `<base href>` (e.g. arXiv) — falling back to
  the page URL — so `--download-images` actually fetches them.

---

## 7. Common workflows

### 7.1 Clip a live URL into an Obsidian vault

```bash
python3 scripts/html2md.py https://example.com/article ./MyVault/Clips/
# → Clips/article.md + Clips/article.reader.md + Clips/_attachments/
```

For a JS/SPA page:

```bash
bash scripts/install.sh --with-chrome      # one-time
python3 scripts/html2md.py https://app.example/spa ./MyVault/Clips/ --engine chrome
```

### 7.2 Convert a saved archive offline

```bash
python3 scripts/html2md.py ./saved.webarchive ./out/                 # Safari archive, main frame
python3 scripts/html2md.py ./thread.mhtml ./out/ --archive-frame all # Chrome MHTML, every frame
python3 scripts/html2md.py ./page.html ./out/ --no-reader            # plain HTML, single .md
```

### 7.3 Use as a universal agent step

```bash
python3 scripts/html2md.py ./page.html --stdout --no-reader --no-download-images --json-errors
```

Whole-page Markdown on stdout; failures as a single-line JSON envelope your
workflow can branch on (`code`/`type`).

### 7.4 Batch-harvest a list of URLs

```bash
while IFS= read -r url; do
  python3 scripts/html2md.py "$url" ./out/ --no-reader --max-images 25 --max-bytes 8000000 --json-errors \
    || echo "skip: $url"
done < urls.txt
```

`--no-reader` keeps one `.md` per link; `--max-images` / `--max-bytes` bound each
fetch; the shared `./out/_attachments/` dedupes images across the whole batch. Transient
failures retry automatically and UA-checking 403s self-recover; persistently blocked
sites (Cloudflare) and PDF links fail cleanly with exit 10 — the loop skips them rather
than crashing (add `--rate-limit 2` to be a polite citizen on a long list).

---

## 8. Security model

- **Output confinement.** Writes only inside the named `OUTPUT_DIR` (and its
  `_attachments/`); never elsewhere.
- **Image-read confinement (CWE-22/73).** A malicious `<img src="../../etc/passwd">`
  / `file:///…` / absolute path is refused — local image reads are confined to
  the input's base directory.
- **SSRF protection (lite path).** Every fetch hop (initial **and** each redirect)
  is refused if it resolves to a loopback / private / link-local /
  cloud-metadata (`169.254.169.254`) address; the body is streamed with a
  `--max-bytes` abort; `--max-images` bounds remote image fetches; a non-`http(s)`
  top-level INPUT is treated as a local path, never fetched.
- **Remote-tier privacy (TASK 023).** The remote reader sends the **target URL** to an
  external service; a private/internal/loopback/metadata target is **never** forwarded
  (a public-IP gate runs before any remote request), `--no-remote` disables the tier, and
  CR/LF/control chars in the target/query are refused. In `auto`, the remote tier is an
  automatic last-resort escalation for **public** targets — so a public URL can leave the
  machine on escalation; use `--no-remote` for sensitive conversions. A `--search` result
  URL never escalates to the Chrome tier unless you pass `--engine chrome`.
- **Authenticated Chrome (TASK 024).** Auth replays a **human-minted** session (no
  password/2FA automation). The Chrome tier is now **SSRF-gated**: `_assert_public_http`
  before navigation; a context-level route guard aborts non-public sub-resources/`fetch`/
  `beacon`; an **off-target public redirect** (final origin ≠ target eTLD+1) is refused;
  the rendered body is bounded by `--max-bytes`. Session files are **bearer credentials** —
  path/env only (never argv), **0600** enforced (group+world refused), symlinks rejected,
  values never logged. `--chrome-*` cannot be combined with `--search`. Target + session stay local.
  A **per-domain auth map** (`--chrome-auth-map`) routes by target domain to per-site credential
  files for a small blast radius — the map **and** every file it references are `0600`-enforced
  (symlink-rejected) too, and it forces chrome only for a *mapped* domain.
- **PDF / binary guard.** A URL that returns a PDF (`%PDF` magic) or binary
  payload fails with a clear `FetchFailed` (exit 10) instead of feeding garbage to
  turndown — html2md is HTML→Markdown only.
- **Honest-scope residuals.** DNS-rebinding (resolve-then-connect TOCTOU) is inherited by
  both the lite and chrome tiers; `storage_state` localStorage is origin-restored; Chromium's
  in-render DOM memory is uncapped (the `--max-bytes` cap is post-render); the login-wall
  heuristic is best-effort/per-site; the ladder has no aggregate `--deadline` and `--max-bytes`
  defaults unbounded (KNOWN_ISSUES HTML2MD-9, HTML2MD-10). Run untrusted conversions in an
  egress-restricted sandbox.

---

## 9. Limitations (honest scope)

See [`docs/KNOWN_ISSUES.md` §HTML2MD](../KNOWN_ISSUES.md) for the full list.

- **Anti-scraper sites (HTTP 403).** Simple UA-checking 403s now recover automatically
  (one browser-UA retry — e.g. uncommoncore). Cloudflare/captcha-hard sites (ssrn,
  researchgate) still 403 the lite path → escalate with **`--engine jina`** (recovers
  both) or `--engine chrome`, or save the page and convert the `.webarchive`/`.html`.
- **PDFs are not converted.** A `*.pdf` URL fails cleanly — use the
  [`pdf`](../../skills/pdf/) skill (`pdf_extract.py`) instead. arXiv `/abs`|`/pdf/<id>`
  auto-tries `/html/<id>`; **PDF-only papers** (no HTML rendering) fail with
  `kind=arxiv_no_html` → fetch the PDF and use the pdf skill.
- **Wikipedia.** `/wiki/<Title>` is fetched from the Parsoid REST `page/html` endpoint
  (the canonical page strips to empty). The **whole-page `.md` is the substantial output**;
  the `.reader.md` is thin there (Parsoid HTML is landmark-free) — prefer the whole variant.
- **Data-grid SPAs degrade.** Market-data dashboards / virtualized registries have
  no table semantics (no `<table>`/`role=table`); their widgets flatten to loose
  lines. This is the wrong *kind* of page for Markdown.
- **Reader-mode on doc SPAs.** GitBook/Mintlify/Fern defeat article extraction, so
  the `.reader.md` is close to the whole `.md` — use the whole variant there.

---

## 10. Verification & maintenance

```bash
# from skills/html2md/scripts/:
./.venv/bin/python -m unittest discover -s html2md/tests -p 'test_*.py'   # unit suite
./.venv/bin/python -m unittest tests.test_battery                          # conversion-quality battery
bash tests/test_e2e.sh                                                     # suite + battery + diff -q replication gate

# from the repo root:
python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/html2md   # → exit 0
```

The **battery** (`tests/battery_signatures.json` + a committed
`examples/regression/gitbook-style-doc.html` plus real `tmp/` fixtures when
present) locks the conversion-quality invariants: `empty_headings == 0`,
`stray_chrome == 0`, required content needles, and structural metric bands.

**Two-master replication (maintainers).** `html2md_core.js` is byte-identical to
docx's `docx2md.js` core; `web_clean/{archives,reader_mode,preprocess,dom_utils,normalize_css}.py`
are byte-identical to pdf's `html2pdf_lib/`. **Never edit those copies here** — edit
the master (docx / pdf) and re-replicate; the `diff -q` gate in
`tests/test_e2e.sh` (and CI) enforces it. The weasyprint/playwright carriers
(`render.py`, `chrome_engine.py`, package `__init__.py`) are **never** replicated.
Full protocol: [CONTRIBUTING.md §3](../CONTRIBUTING.md#3-office-skills-modification-protocol-strict)
and [`scripts/.AGENTS.md`](../../skills/html2md/scripts/.AGENTS.md).

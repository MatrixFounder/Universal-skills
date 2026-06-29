---
name: html
description: Use when fetching a web page/URL or converting a saved .html/.htm/.mhtml/.webarchive to clean Markdown — an Obsidian web-clipper and a universal HTML acquisition + HTML→Markdown step that also feeds the pdf and docx skills. Triggers include "html to markdown", "url to markdown", "download this page", "save the html", "web page to obsidian", "webarchive/mhtml to markdown", "clip this article".
tier: 2
version: 1.1
license: LicenseRef-Proprietary
---
# html skill

**Purpose**: Convert a web URL or a downloaded `.html`/`.htm`/`.mhtml`/`.webarchive`
into clean Markdown — with YAML frontmatter and a shared `_attachments/` folder —
for two consumers: (1) an **Obsidian web-clipper** (self-contained note), and
(2) a **universal HTML→Markdown step** any agent workflow can call.

## 1. Red Flags (Anti-Rationalization)
- "I'll just paste the HTML and convert it in my head" → **WRONG**. The script
  reuses the docx-mastered turndown core (GFM tables, rowspan→flat grid) and the
  pdf-mastered cleaner (reader-mode, SPA-chrome strip); reimplementing in prose
  regresses on every edge case.
- "I'll fetch the page with curl and strip tags with regex" → **WRONG**. Use the
  script — it has SSRF protection, dual-output, sha1-deduped attachments.

## 2. Capabilities
- **URL → Markdown via a resilient fallback ladder** (`--engine lite|chrome|auto|jina|remote`):
  `httpx`+`trafilatura` lite fetch (also yields title/date/author) with **retry + backoff +
  429/`Retry-After`** and a **403 → browser-UA escalation**. `--engine auto` (default) is
  **local-first** (`lite → chrome → remote` last-resort); `--engine jina|remote` is
  **remote-first** with automatic local fallback. **No single tier is a point of failure:**
  if a remote reader is down / rate-limited / quota-exhausted, the run falls back to the next
  provider then to the local engines; only when *every* viable tier is exhausted does it fail
  with one typed `FetchFailed (kind=all_engines_failed)` carrying a `details.tried` trace.
- **Vendor-agnostic remote reader** (`--engine jina|remote`): the remote tier is a pluggable
  provider layer — `jina` (`r.jina.ai`) is the built-in default, but `HTML_READER_URL` /
  `HTML_READER_PROVIDERS` point it at a **self-hosted Jina** or any compatible reader, so
  resilience does not depend on any single vendor. `--engine remote` REQUIRES a configured
  provider (never a silent fall-back to jina.ai). `--no-remote` disables the remote tier
  entirely. `--remote-format markdown` trusts the reader's own clean Markdown; `--target-selector`
  extracts just the article block. `--rate-limit` throttles fetches.
- **Web search → Markdown** (`--search "QUERY" [OUTPUT_DIR] [--max-results N]`): a
  vendor-agnostic search provider (`s.jina.ai` default; `HTML_SEARCH_URL` /
  `HTML_SEARCH_PROVIDERS` override) returns the top results; **each result URL is fetched
  through the same fallback ladder** (so every result inherits per-result fallback) and
  written as one note (frontmatter `query:` + `source:`). A failed result is skipped, not
  fatal; a healthy zero-result search exits 0.
- **Authenticated (login-gated) Chrome** (`--engine chrome` + auth): read pages behind a login
  (X Articles/threads, paywalled/members, private docs) by replaying a **human-minted** session.
  Mint once: `html login URL --save-state state.json` (headful; 2FA ok). Then convert with
  `--chrome-storage-state state.json` (portable, **server/Hermes-deployable**, read-only →
  concurrency-safe), `--chrome-cookies-file cookies.txt` (cookie-only), or
  `--chrome-user-data-dir DIR` (local persistent profile). `--chrome-scroll [--chrome-scroll-passes N]`
  pulls lazy content (replies). The Chrome tier is **SSRF-gated** (private / off-target-public
  redirects refused; non-public sub-resources aborted); a stale session → `auth_required`. Auth
  is strictly **opt-in** — with none configured, behaviour is unchanged (no crash). The target
  URL + session stay **local** (no third party). See `references/html-to-markdown.md` (Hermes deploy).
- **Site-specific clean-source endpoints** (proactive, auto/lite): **Wikipedia**
  `/wiki/<Title>` → the Parsoid REST `page/html` endpoint (the canonical page is
  chrome-only and strips to empty); **arXiv** `/abs/` or `/pdf/<id>` → the full-text
  `/html/<id>` rendering (PDF-only papers return an actionable "use the pdf skill" hint);
  **HackerNoon** `/<slug>` → `/lite/<slug>`.
- **Empty-extraction guard**: a substantial source page that converts to a near-empty
  body is a typed **`EmptyExtraction` (exit 11)** — never a silent `exit 0` with an empty
  note.
- **Archive → Markdown**: Safari `.webarchive` + Chrome `.mhtml` (subframe-aware) +
  plain `.html`/`.htm`, fully offline.
- **Obsidian emit**: YAML frontmatter; `--download-images` → `_attachments/`
  (sha1-dedup, relative links) — covers remote `http(s)` **and content-sized inline `data:`**
  images (base64/percent-encoded decoded to files; tiny icon blobs dropped); **dual-output**
  (`<slug>.md` + `<slug>.reader.md`); `--reader-only` emits a SINGLE
  `<slug>.md` = the reader extraction (whole-page fallback if empty) — for note pipelines.
- **Math → Obsidian-native**: Pandoc/MathJax `\(…\)` / `\[…\]` (and `class="math"` spans)
  → `$…$` / `$$…$$` with raw, un-escaped TeX, so formulas render in Obsidian/KaTeX. Escaped
  plain-text brackets (`[word]`, citations) and code spans are left untouched.
- **Agent step**: `--stdout` (Markdown to stdout — inline `data:` blobs stripped to keep the
  stream clean) + `--json-errors` envelope.

## 3. Execution Mode
- **Mode**: `script-first`.
- **Why this mode**: HTML→Markdown is a deterministic, edge-case-heavy pipeline
  (fetch → clean → turndown → emit) reusing hardened docx/pdf code. Inline agent
  conversion regresses on tables, SPA chrome, encodings, and image handling, and
  has no SSRF protection.

## 4. Script Contract

> **Two operations + a combined one-shot.** The skill exposes the pipeline as composable
> verbs so a fetched page can feed Markdown, **pdf**, or **docx**:
> - `python3 scripts/html fetch INPUT [OUTPUT_DIR]` — **OP1**: download to an on-disk
>   `<slug>.html` + `<slug>.meta.json` sidecar (+ localized `_attachments/`). The HTML is
>   **sanitized** (`file:`/`javascript:` refs stripped) so it is safe to render; an
>   authenticated fetch's body is written `0600`. Keep the HTML to feed the **pdf** skill.
> - `python3 scripts/html md INPUT [OUTPUT_DIR]` — **OP2**: convert a fetched artifact /
>   local HTML / URL → Markdown. A local `.html` with a sibling `.meta.json` recovers full
>   frontmatter from the sidecar.
> - `python3 scripts/html2md.py INPUT [OUTPUT_DIR]` — **combined** (fetch → md → delete the
>   intermediate HTML): the classic web-clip — you get just `<slug>.md` (+ `.reader.md`) +
>   `_attachments/`, no leftover HTML. This is the bare/back-compat one-shot.
>
> **Pipelines:**
> - **download → pdf:** `html fetch URL out/ && python3 ../pdf/scripts/html2pdf.py out/<slug>.html out.pdf --untrusted`
>   (always pass `--untrusted` — it refuses `file://` at the renderer, defense-in-depth over
>   the fetch-time sanitizer). Requires `html fetch` ran **with** images (the default) so the
>   PDF has them (pdf is offline — it never fetches remote `<img>`).
> - **download → docx:** `html fetch URL out/ && html md out/<slug>.html out/ && node ../docx/scripts/md2docx.js out/<slug>.md out.docx`.

- **Command** (bare / `md` verb):
  - `python3 scripts/html INPUT [OUTPUT_DIR] [--engine lite|chrome|auto|jina|remote] [--no-remote] [--remote-format html|markdown] [--target-selector SEL] [--chrome-storage-state PATH | --chrome-cookies-file PATH | --chrome-user-data-dir DIR] [--chrome-scroll] [--chrome-scroll-passes N] [--reader-mode|--no-reader|--reader-only] [--download-images|--no-download-images] [--attachments-dir _attachments] [--archive-frame main|N|all|auto] [--max-bytes N] [--max-images N] [--retries N] [--rate-limit REQS_PER_SEC] [--stdout] [--json-errors]`
  - Search: `python3 scripts/html search "QUERY" [OUTPUT_DIR] [--max-results N] [...]` (or the legacy `--search "QUERY"`).
  - Login (mint a session, headful): `python3 scripts/html login URL [--save-state state.json]`.
- **Environment (optional):** `HTML_READER_URL` / `HTML_READER_PROVIDERS` (remote reader base(s)), `HTML_READER_TOKEN` (generic reader auth), `JINA_API_KEY` (jina quota), `HTML_SEARCH_URL` / `HTML_SEARCH_PROVIDERS` (search provider base(s)), `HTML_CHROME_STORAGE_STATE` / `HTML_CHROME_COOKIES_FILE` / `HTML_CHROME_USER_DATA_DIR` (Chrome auth — server-deployable secrets), `HTML_SSRF_ALLOW_NETS` (SSRF carve-out CIDR list — **no code default**; unset/empty → none; `.env.example` ships `198.18.0.0/15` for RFC-2544/`.eth.limo` mappings; `0.0.0.0/0` disables IPv4 protection). All optional; the CLI **auto-loads `<skill>/.env`** at startup (an in-process `import` caller does not — call `_load_skill_env()` yourself). See [`.env.example`](.env.example).
- **INPUT**: a `http(s)` URL, or a local `.html`/`.htm`/`.mhtml`/`.mht`/`.webarchive`.
- **OUTPUT_DIR**: directory to write `<slug>.md` (+ `<slug>.reader.md` by default) and
  `_attachments/` into. **Omit → defaults to `./tmp/html_out/`** (created on demand,
  in the working directory). `--stdout` opts into stdout mode: **YAML frontmatter +
  whole-page Markdown** (the reader variant and image files are skipped — not the
  reader-extracted text).
- **Defaults**: `--engine auto`, dual-output ON (`--no-reader` to suppress),
  `--download-images` ON (`--no-download-images` keeps remote URLs), attachments dir
  `_attachments`, `--archive-frame main`.
- **Outputs**: `<slug>.md` + `<slug>.reader.md` + `_attachments/<sha1>.<ext>`; or
  Markdown on stdout. `<slug>` is derived from the input filename / URL path
  (deterministic); the human title lives in frontmatter.
- **Failure semantics / exit codes**: 0 ok · 1 BadInput/ConvertFailed/internal ·
  2 usage (incl. `--search`+URL, `--engine remote` with no provider, `--max-results`≤0) ·
  3 EngineNotInstalled (Chrome **explicitly** requested, Playwright absent — in `auto`/
  remote-first this is a silent fall-through, not exit 3) · 6 SelfOverwriteRefused ·
  10 FetchFailed (unreachable / blocked / over `--max-bytes`; `details.kind` ∈ bot_blocked/
  auth_required/not_found/rate_limited/server_error/unreachable/pdf/binary/arxiv_no_html/
  refused/offsite_redirect/**all_engines_failed**) · 11 EmptyExtraction (substantial source →
  near-empty body). `auth_required` from the chrome path = a stale/expired session (re-mint).
  On a total-ladder failure, `details.tried` lists each tier attempted + its failure kind
  (URL-free). `--json-errors` emits `{v:1, error, code, type?, details?}` on stderr.
- **Idempotency**: same input → same output filenames + deduped attachments. URL
  fetches reflect live content (not idempotent across server changes).

## 5. Safety Boundaries
- **Allowed scope**: only the input + the named OUTPUT_DIR (and its `_attachments/`).
  Never writes elsewhere.
- **Image reads are confined**: a malicious `<img src="../../etc/passwd">` /
  `file:///…` / absolute path is **refused** — local image reads are confined to the
  input's base dir (CWE-22/73 guard).
- **SSRF protection (lite path)**: every fetch hop (initial + redirects) is refused if
  it resolves to a loopback / private / link-local / cloud-metadata (169.254.169.254)
  address; body is streamed with a `--max-bytes` abort; `--max-images` bounds remote
  fetches; non-`http(s)` top-level INPUT is treated as a local path, never fetched.
- **Remote-reader tier sends the target URL to an external service** (`r.jina.ai` or a
  configured reader fetches it server-side). In `--engine auto` the remote tier is an
  **automatic last-resort escalation** for **public** targets (so a Cloudflare/anti-bot page
  recovers without manual intervention) — meaning a public URL may leave the machine on
  escalation. Guards: a **private/internal/loopback/metadata target is NEVER forwarded to a
  reader** (a public-IP gate runs before any remote request); **`--no-remote`** disables the
  remote tier entirely (no external egress); CR/LF/control chars in the target/query are
  refused (request-splitting guard). Do not point `--engine jina|remote`, or `auto` against
  sensitive URLs, at internal hosts you don't want proxied; use `--no-remote` for fully
  local conversion. The local hop to the reader passes the SSRF gate.
- **Authenticated Chrome (TASK 024)**: auth replays a **human-minted** session (no password/2FA
  automation). The Chrome tier is now **SSRF-gated** — `_assert_public_http` before navigation,
  context-level route guard aborting non-public sub-resources/`fetch`/`beacon`, and an
  **off-target public-redirect** refusal (final origin must equal the target's eTLD+1) so a
  session is never carried to another site. Session files (`storage_state`/`cookies.txt`) are
  **bearer credentials**: passed by **path only** (never argv), required mode **0600** (group+world
  rejected), symlinks refused, values never logged/redacted. The target + session stay **local**.
- **Honest-scope residuals**: DNS-rebinding (resolve-then-connect TOCTOU) is **closed on the lite
  path** (the connection is pinned to the validated IP), but **remains on the Chrome tier**
  (Playwright manages its own sockets); `storage_state` localStorage is origin-restored (readable
  by same-origin scripts the page loads); the login-wall heuristic is best-effort/per-site; `_registrable` is last-2-labels
  (multi-level suffixes like `co.uk` over-match); a reader follows its own server-side redirects.
  Run untrusted conversions in an egress-restricted sandbox. See `references/html-to-markdown.md`
  and `docs/KNOWN_ISSUES.md` (HTML2MD-10).
- **No global installs**: deps live in `scripts/.venv` + `scripts/node_modules`.

## 6. Validation Evidence
- **Local verification**:
  - `bash scripts/install.sh` — creates `.venv` (httpx, trafilatura), `node_modules`
    (turndown, turndown-plugin-gfm). `--with-chrome` adds Playwright Chromium.
  - `python3 scripts/html examples/sample.html /tmp/h2m && test -s /tmp/h2m/*.md`
    — offline file → dual Markdown + frontmatter.
  - `./scripts/.venv/bin/python -m unittest discover -s scripts/html2md/tests` and
    `-s scripts/tests` — full unit + E2E suite (file/archive/url mocked + real
    `tmp/` fixtures when present).
  - `bash scripts/tests/test_e2e.sh` — runs the suite + the `diff -q` replication gate.
- **CI signal**: `python3 .claude/skills/skill-creator/scripts/validate_skill.py
  skills/html` — exits 0.

## 7. Instructions

### 7.1 Clip a live URL into an Obsidian vault
```bash
python3 scripts/html https://example.com/article ./MyVault/Clips/
```
Produces `article.md` (whole) + `article.reader.md` (reader-extracted) + deduped
`_attachments/`. Use `--engine chrome` (after `install.sh --with-chrome`) for JS/SPA pages.

### 7.2 Convert a saved archive offline
```bash
python3 scripts/html ./saved.webarchive ./out/ --archive-frame main
python3 scripts/html ./thread.mhtml ./out/ --archive-frame all
```

### 7.3 Use as a universal agent step
```bash
python3 scripts/html ./page.html --stdout --no-download-images --no-reader --json-errors
```
Whole-page Markdown on stdout; failures as a single-line JSON envelope.

## 8. Architecture & Replication (for maintainers)
`html` (formerly `html2md`) is the repo's first **two-master** skill (CLAUDE.md §2). It carries
byte-identical replicas — **do not edit them here**, `diff -q` gated:
- `web_clean/{archives,reader_mode,preprocess,dom_utils,normalize_css}.py` — MASTER = pdf.
- `html2md_core.js` — MASTER = docx.
- `_errors.py`, `_venv_bootstrap.py` — MASTER = docx (4→5-skill).

The pdf `render.py`/`chrome_engine.py`/package `__init__.py` (weasyprint/playwright
carriers) are **never** replicated; `web_clean/__init__.py` is an html-owned thin
facade. See `scripts/.AGENTS.md`.

## 9. License
**Proprietary, All Rights Reserved** — see `LICENSE` / `NOTICE`. This skill embeds
byte-identical copies of proprietary docx/pdf code; it is a derived work and is
**not** Apache-2.0.

## 10. Resources
- `references/html-to-markdown.md` — decision tree (URL/archive/file; reader vs whole;
  lite vs chrome) + honest scope.
- `examples/basic-usage.md` — copy-paste examples.

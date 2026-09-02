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

### Rationalization Table
| Agent Excuse | Reality / Counter-Argument |
| :--- | :--- |
| "The page is simple, plain turndown is enough" | Plain turndown keeps the nav, cookie banner and share rail. The reader-mode pass is what makes the Markdown readable, and it is one flag. |
| "Reader mode dropped something, so I'll skip it" | Reader mode is lossy by design. Re-run with `--whole` for that one page instead of abandoning the cleaner for every page. |
| "I'll patch `web_clean/` here, it's a small fix" | `web_clean/` is a byte-identical replica; **pdf** is its master. Edit `skills/pdf/scripts/html2pdf_lib/`, then replicate — a local patch is silently reverted by the next `diff -q` gate. |
| "The file is already HTML, no need to fetch" | A saved `.mhtml`/`.webarchive` is a container, not HTML. Point the script at it and let `archives.py` unpack it. |
| "It rendered, so the output is right" | A non-empty `.md` proves the pipeline ran, not that the article survived. Read the first and last heading before handing it back. |

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
> - `python3 scripts/html get URL (OUTPUT_PATH | --stdout)` — **OP3**: download a URL to
>   **raw bytes**, verbatim, through the same SSRF-guarded ladder. **No conversion, no
>   sanitizing, no content sniffing** — the caller decides what the bytes are. Use it when
>   you need the file itself (a PDF to hand to the **pdf** skill, an image, any binary):
>   OP1/OP2 refuse a `%PDF-` payload on purpose, because turndown blows its call stack on
>   binary input, and before OP3 existed a caller needing those bytes had nothing to shell
>   out to and fell back to an unguarded raw HTTP GET. OP3 **bypasses no guard** — it calls
>   `_assert_safe_target` + `_http_get_bytes`, the same two the text path uses, and omits
>   only the content-type layer above them. Egress is direct unless `HTML_PROXY` is set (§5).
>   - **Flags**: `--stdout` (bytes to stdout, no file — for a caller that wants a string and
>     no temp-file lifecycle) · `--max-bytes N` (default 64 MiB — a *finite* default, unlike
>     the conversion flags', because an unbounded arbitrary-binary download is a DoS
>     foot-gun; the body is buffered, so **this is also the memory bound**) · `--timeout S`
>     (**per operation**, default 60, in `(0, 300]`) · `--deadline S` (**total wall clock**,
>     default 300, in `(0, 3600]`) · `--retries N` (0..10) · `--header 'KEY: VALUE'`
>     (repeatable — needed for content negotiation, e.g. `Accept: application/pdf,*/*`) ·
>     `--browser-ua` · `--json-errors`.
>   - ★ **Wall-clock: size your `subprocess(timeout=…)` against `--deadline`, not
>     `--timeout`.** `--timeout` is **per operation** and bounds nothing in total: a redirect
>     chain multiplies it by `max_redirects + 1` inside *every* retry pass, and a slow-drip
>     body resets the read timeout on each chunk while `--max-bytes` caps only SIZE. Measured:
>     a 5-hop chain stalling *below* the timeout ran 2.4x the per-op budget, and a body
>     dripping one byte per 1.6 s returned OK after 12.85 s against a 2 s timeout —
>     time-unbounded in principle. At the shipped defaults the redirect case alone would be
>     `60 x 6 x 4 = 1440 s`. `--deadline` is enforced inside the ladder at every hop and every
>     chunk, so it is a real bound; exceeding it is exit 10 with `details.kind == "deadline"`.
>   - **Exit map**: `0` ok · `2` usage — **including a non-http(s) URL**, so a caller's typo
>     is distinguishable from a security refusal · `10` FetchFailed (SSRF refusal, redirect
>     cap, over-cap body, deadline) · `1` internal · `141` broken pipe (`--stdout` only: the
>     consumer closed the pipe and holds a PREFIX — **not** reported as success, so truncation
>     stays detectable). Under exit 10 read **`details.kind`** to tell the classes apart:
>     `refused` (a security block — SSRF / scheme / control chars) · `deadline` · otherwise a
>     transport failure; `details.max_bytes` marks the over-cap case. Asserting only on the
>     exit code cannot distinguish a security refusal from an unreachable host.
>   - `--browser-ua` and `--header 'User-Agent: …'` are **mutually exclusive** (the header
>     would silently win and make the flag a no-op). The artifact is written `0600`.
>   - **On failure nothing is written**, and a pre-existing `OUTPUT_PATH` is left **untouched
>     — not removed** (`get` never unlinks a file it did not create). On success the write is
>     atomic (`.part` + rename), so a truncated artifact the caller cannot detect is
>     impossible.
>   - **Capability probe** (for programmatic consumers, so an older install fails CLOSED):
>     `python3 scripts/html --help | grep -q 'html get URL'`. ⚠️ A bare `grep -q get`
>     **always succeeds** — it matches `--target-selector` — and `html get --help` exits 0 on
>     a build *without* the verb too (argparse reads `get` as INPUT and prints the top-level
>     help). Neither is a valid probe.
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
  - Raw bytes (OP3): `python3 scripts/html get URL (OUTPUT_PATH | --stdout) [--max-bytes N] [--timeout S] [--retries N] [--header 'KEY: VALUE'] [--browser-ua] [--json-errors]`.
- **Environment (optional):** `HTML_READER_URL` / `HTML_READER_PROVIDERS` (remote reader base(s)), `HTML_READER_TOKEN` (generic reader auth), `JINA_API_KEY` (jina quota), `HTML_SEARCH_URL` / `HTML_SEARCH_PROVIDERS` (search provider base(s)), `HTML_CHROME_STORAGE_STATE` / `HTML_CHROME_COOKIES_FILE` / `HTML_CHROME_USER_DATA_DIR` (Chrome auth — server-deployable secrets), `HTML_SSRF_ALLOW_NETS` (SSRF carve-out CIDR list — **no code default**; unset/empty → none; `.env.example` ships `198.18.0.0/15` for RFC-2544/`.eth.limo` mappings; `0.0.0.0/0` disables IPv4 protection), `HTML_PROXY` (egress proxy — **the ONLY way to proxy**: `trust_env=False`, so `HTTP_PROXY`/`HTTPS_PROXY` and the macOS System Configuration proxy are ignored. Setting it re-opens the DNS-rebinding window, see §5, and prints a one-time notice). All optional; the CLI **auto-loads `<skill>/.env`** at startup (an in-process `import` caller does not — call `_load_skill_env()` yourself). See [`.env.example`](.env.example).
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
  Never writes elsewhere. **Exception — OP3 `get`**: it writes the single caller-named
  `OUTPUT_PATH`, creating parent directories, and **overwrites** an existing file (atomically,
  via a sibling `.part` + rename, so a truncated artifact is impossible). A symlink or a
  directory at `OUTPUT_PATH` is **refused** (exit 2) — `get` never writes *through* a link.
  ⚠️ The bytes it writes are **unsanitized and fully remote-controlled** — every other write
  path in this skill runs `sanitize_untrusted_html` and derives its own slug. Do not point
  `get` at a path that will subsequently be rendered (`html get URL page.html` produces a live
  script/`file:`-bearing document on disk). The artifact is written **`0600`** — it is created
  via `mkstemp` and `os.replace`d into place, so it is never world-readable, not even in
  flight, and a crash cannot leave a truncated file under the caller's name.
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
- **Egress is DIRECT by default (`trust_env=False`)** so the connection pin is authoritative.
  The ambient environment — `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`, `.netrc`, `SSL_CERT_*` — is
  **ignored**; proxying is an explicit opt-in via **`HTML_PROXY`**, and setting it prints a
  one-time stderr notice. This is not tidiness: until it changed, the pin was **decorative**.
  Measured — pinning `example.com` to a blackholed `192.0.2.1` returned **HTTP 200** under an
  ambient proxy (pin ignored) and `ConnectTimeout` direct (pin honoured); the machine had **no
  proxy env vars**, yet `urllib.request.getproxies()` still returned one from macOS System
  Configuration. Check yours with
  `python3 -c "import urllib.request;print(urllib.request.getproxies())"`.
- **Honest-scope residuals**: DNS-rebinding (resolve-then-connect TOCTOU) is **closed on the lite
  path** (the connection is pinned to the validated IP) — but **re-opens whenever `HTML_PROXY` is
  set**, because the proxy then resolves the target itself. The per-hop `_assert_public_http`
  pre-check still runs in that mode, so it is a TOCTOU window, not an open door. ⚠️ Note also that
  under a **fake-IP resolver** (Clash/V2Ray-style, which is what the shipped
  `HTML_SSRF_ALLOW_NETS=198.18.0.0/15` default exists for) the pin binds the *synthetic* address;
  the synthetic→real mapping lives in the proxy tool and is outside this skill's control.
  Rebinding also **remains on the Chrome tier** (Playwright manages its own sockets, and it keeps
  using the SYSTEM proxy regardless of `HTML_PROXY`); `storage_state` localStorage is origin-restored (readable
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

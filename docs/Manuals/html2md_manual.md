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
| `--engine lite\|chrome\|auto\|jina` | `auto` | fetch engine for URLs (see [§5](#5-engines-lite-vs-chrome)) |
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
| `2` | usage error (bad arguments) |
| `3` | EngineNotInstalled — `--engine chrome` requested but Playwright absent (run `install.sh --with-chrome`) |
| `6` | SelfOverwriteRefused — output path would clobber the input |
| `10` | FetchFailed — unreachable / blocked (HTTP 4xx/5xx) / over `--max-bytes` / **PDF or binary** payload |
| `11` | EmptyExtraction — fetch succeeded but a substantial source converted to a near-empty body |

With `--json-errors`, stderr carries `{"v":1,"error":"…","code":10,"type":"FetchFailed","details":{…}}`.
For a fetch failure, `details` includes **`status`** (the HTTP code) and **`kind`** —
`bot_blocked` (403 → try `--engine jina`/`chrome`), `auth_required` (login/paywall →
manual), `rate_limited` (429), `not_found`, `server_error` (retry), `unreachable`
(transport), `pdf`/`binary`, or `arxiv_no_html` (PDF-only arXiv paper → use the pdf skill)
— so a calling agent can branch on manual-vs-retry. `details.url` keeps the meaningful
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

## 5. Engines: lite vs chrome vs jina

| Engine | How | When |
|---|---|---|
| `lite` | `httpx` GET + `trafilatura` (also yields title/date/author) | server-rendered HTML (most docs, blogs, news) |
| `chrome` | headless Chromium via Playwright (`--with-chrome`) | JS/SPA pages whose content is hydrated client-side |
| `auto` *(default)* | lite first; if the result looks like a thin JS shell, escalate to chrome | unknown pages — let the skill decide |
| `jina` | **Jina Reader** (`r.jina.ai`) renders + cleans server-side, returns HTML → our pipeline | JS/anti-bot pages **without** a local browser; Cloudflare-hard sites |

`auto` falls back to Chrome only when Playwright is installed; otherwise it
returns whatever lite got. Force `--engine chrome` when you *know* the page needs
JS and you have run `install.sh --with-chrome`.

**Fetch robustness (all engines that use the lite HTTP path):** transient failures
(transport errors, HTTP 5xx, 429) are **retried with exponential backoff** (`--retries`,
default 2; 429 honours `Retry-After`); a **403** triggers one automatic escalation to a
real-browser User-Agent (the default UA is the honest `html2md/…` — only a refusal swaps
it). This recovers most anti-scraper 403s (e.g. UA-checking sites) with no flags.

**`--engine jina` caveats:** it sends the **target URL to the external `r.jina.ai`
service** (which fetches it server-side) — so it's **explicit-only**, never part of `auto`;
don't use it for sensitive/internal URLs. Keyless by default (rate-limited); set
`JINA_API_KEY` for higher quota. Use it as the escalation when even a browser-UA lite fetch
is blocked (Cloudflare/captcha) and you'd rather not install Playwright.

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
- **PDF / binary guard.** A URL that returns a PDF (`%PDF` magic) or binary
  payload fails with a clear `FetchFailed` (exit 10) instead of feeding garbage to
  turndown — html2md is HTML→Markdown only.
- **Honest-scope residuals.** DNS-rebinding (resolve-then-connect TOCTOU) and the
  opt-in Chrome engine are **not** SSRF-hardened — run untrusted conversions in an
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

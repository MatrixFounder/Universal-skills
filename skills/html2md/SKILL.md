---
name: html2md
description: Use when converting a web page (URL) or a saved .html/.htm/.mhtml/.webarchive into clean Markdown — a web-clipper for Obsidian notes and a universal HTML→Markdown step for agent workflows. Triggers include "html to markdown", "url to markdown", "web page to obsidian", "webarchive to markdown", "mhtml to markdown", "scrape page to notes", "clip this article".
tier: 2
version: 1.0
license: LicenseRef-Proprietary
---
# html2md skill

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
- **URL → Markdown** (`--engine lite|chrome|auto|jina`): `httpx`+`trafilatura` lite fetch
  (also yields title/date/author) with **retry + backoff + 429/`Retry-After`** and a
  **403 → browser-UA escalation** (honest UA by default); auto-fallback to headless
  Chrome for JS/SPA pages; or `--engine jina` (Jina Reader — server-side JS render, no
  local browser; sends the URL to an external service). `--rate-limit` throttles fetches.
- **Archive → Markdown**: Safari `.webarchive` + Chrome `.mhtml` (subframe-aware) +
  plain `.html`/`.htm`, fully offline.
- **Obsidian emit**: YAML frontmatter; `--download-images` → `_attachments/`
  (sha1-dedup, relative links); **dual-output** (`<slug>.md` + `<slug>.reader.md`).
- **Agent step**: `--stdout` (Markdown to stdout) + `--json-errors` envelope.

## 3. Execution Mode
- **Mode**: `script-first`.
- **Why this mode**: HTML→Markdown is a deterministic, edge-case-heavy pipeline
  (fetch → clean → turndown → emit) reusing hardened docx/pdf code. Inline agent
  conversion regresses on tables, SPA chrome, encodings, and image handling, and
  has no SSRF protection.

## 4. Script Contract
- **Command**:
  - `python3 scripts/html2md.py INPUT [OUTPUT_DIR] [--engine lite|chrome|auto|jina] [--reader-mode|--no-reader] [--download-images|--no-download-images] [--attachments-dir _attachments] [--archive-frame main|N|all|auto] [--max-bytes N] [--max-images N] [--retries N] [--rate-limit REQS_PER_SEC] [--stdout] [--json-errors]`
- **INPUT**: a `http(s)` URL, or a local `.html`/`.htm`/`.mhtml`/`.mht`/`.webarchive`.
- **OUTPUT_DIR**: directory to write `<slug>.md` (+ `<slug>.reader.md` by default) and
  `_attachments/` into. **Omit → defaults to `./tmp/html2md_out/`** (created on demand,
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
  2 usage · 3 EngineNotInstalled (Chrome requested, Playwright absent) ·
  6 SelfOverwriteRefused · 10 FetchFailed (unreachable / blocked / over `--max-bytes`).
  `--json-errors` emits `{v:1, error, code, type?, details?}` on stderr.
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
- **Honest-scope residuals**: DNS-rebinding (resolve-then-connect TOCTOU) and the
  opt-in Chrome engine are NOT SSRF-hardened — run untrusted conversions in an
  egress-restricted sandbox. **`--engine jina`** sends the target URL to the external
  `r.jina.ai` service (it fetches server-side) — opt-in only, never part of `auto`; do
  not use it for sensitive/internal URLs. See `references/html-to-markdown.md`.
- **No global installs**: deps live in `scripts/.venv` + `scripts/node_modules`.

## 6. Validation Evidence
- **Local verification**:
  - `bash scripts/install.sh` — creates `.venv` (httpx, trafilatura), `node_modules`
    (turndown, turndown-plugin-gfm). `--with-chrome` adds Playwright Chromium.
  - `python3 scripts/html2md.py examples/sample.html /tmp/h2m && test -s /tmp/h2m/*.md`
    — offline file → dual Markdown + frontmatter.
  - `./scripts/.venv/bin/python -m unittest discover -s scripts/html2md/tests` and
    `-s scripts/tests` — full unit + E2E suite (file/archive/url mocked + real
    `tmp/` fixtures when present).
  - `bash scripts/tests/test_e2e.sh` — runs the suite + the `diff -q` replication gate.
- **CI signal**: `python3 .claude/skills/skill-creator/scripts/validate_skill.py
  skills/html2md` — exits 0.

## 7. Instructions

### 7.1 Clip a live URL into an Obsidian vault
```bash
python3 scripts/html2md.py https://example.com/article ./MyVault/Clips/
```
Produces `article.md` (whole) + `article.reader.md` (reader-extracted) + deduped
`_attachments/`. Use `--engine chrome` (after `install.sh --with-chrome`) for JS/SPA pages.

### 7.2 Convert a saved archive offline
```bash
python3 scripts/html2md.py ./saved.webarchive ./out/ --archive-frame main
python3 scripts/html2md.py ./thread.mhtml ./out/ --archive-frame all
```

### 7.3 Use as a universal agent step
```bash
python3 scripts/html2md.py ./page.html --stdout --no-download-images --no-reader --json-errors
```
Whole-page Markdown on stdout; failures as a single-line JSON envelope.

## 8. Architecture & Replication (for maintainers)
`html2md` is the repo's first **two-master** skill (CLAUDE.md §2). It carries
byte-identical replicas — **do not edit them here**, `diff -q` gated:
- `web_clean/{archives,reader_mode,preprocess,dom_utils,normalize_css}.py` — MASTER = pdf.
- `html2md_core.js` — MASTER = docx.
- `_errors.py`, `_venv_bootstrap.py` — MASTER = docx (4→5-skill).

The pdf `render.py`/`chrome_engine.py`/package `__init__.py` (weasyprint/playwright
carriers) are **never** replicated; `web_clean/__init__.py` is an html2md-owned thin
facade. See `scripts/.AGENTS.md`.

## 9. License
**Proprietary, All Rights Reserved** — see `LICENSE` / `NOTICE`. This skill embeds
byte-identical copies of proprietary docx/pdf code; it is a derived work and is
**not** Apache-2.0.

## 10. Resources
- `references/html-to-markdown.md` — decision tree (URL/archive/file; reader vs whole;
  lite vs chrome) + honest scope.
- `examples/basic-usage.md` — copy-paste examples.

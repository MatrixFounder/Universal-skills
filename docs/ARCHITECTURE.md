# ARCHITECTURE: `html` (formerly `html2md`) — universal Web/HTML → Markdown converter & Obsidian web-clipper (TASK 022)

> **License:** Proprietary, All Rights Reserved (derived work embedding
> proprietary `docx`/`pdf` code — see `CLAUDE.md` §3 + §9 below).
> **Runtime:** hybrid — Python orchestrator + Node converter subprocess
> (mirrors the existing `md2pdf.py` → `mmdc` pattern).
> **Naming (post-rename):** the skill is `html`; the user-facing launcher is
> the **extensionless** `scripts/html` (a `html.py` would shadow stdlib `html`,
> which is on `sys.path[0]`). The **internal Python package is still `html2md`**
> (renaming it would shadow stdlib `html`), and the replicas keep their donor
> names — `html2md_core.js` (docx master) and `web_clean/*` (pdf master).
> **Source of truth for replication:** `CLAUDE.md` §2 «Future skill html2md —
> TWO-master replication». §9 of this doc is **load-bearing** (non-empty,
> unlike pptx2md/TASK 020).

---

## 1. Task Description

Turn **any** web input — a live URL, or a downloaded `.html`/`.htm`,
`.mhtml`/`.mht`, `.webarchive` — into clean Markdown, for two consumers:

1. **Obsidian web-clipper** — a self-contained note: YAML frontmatter +
   body + images downloaded into a shared `_attachments/` folder.
2. **Universal agent workflow step** — Markdown to stdout + `--json-errors`
   envelope, no files written unless asked.

The skill is **fork-free by construction**: the proven HTML→Markdown core is
reused from `docx` (the `turndown` stage inside `docx2md.js`) and the proven
HTML-cleaning machinery from `pdf` (`html2pdf_lib/`). Only the two genuinely
missing layers are new code: **acquisition** (live-URL fetch — neither donor
skill can fetch; both are offline by design) and **Obsidian emit**.

Full requirements: `docs/TASK.md` (TASK 022) RTM R1–R8.

---

## 2. Functional Architecture

### 2.1. Functional Components

- **FC-1 `acquire.py` (NEW)** — input dispatch + HTML acquisition.
  - Format dispatch by extension + magic-byte (`bplist00` → webarchive).
  - **URL** → `httpx` transport + `trafilatura` lite extraction
    (article + `title/date/author` metadata for frontmatter); on empty/JS
    shell → auto-fallback to Chrome (Playwright, soft-optional).
  - **archive** (`.webarchive`/`.mhtml`) → delegates to
    `web_clean/archives.py` (subframe-aware, pdf-8), sub-resource images
    extracted to a temp dir, URL→local-path map returned.
  - **file** (`.html`/`.htm`) → direct read (Chrome "Save As" sibling
    `<page>_files/` honoured).
  - Output IR: `AcquireResult` (§4).
- **FC-2 `web_clean/` (REPLICATED from pdf, master=pdf)** — HTML cleaning.
  - `reader_mode.reader_mode_html(html)` — article extraction + universal
    SPA-chrome heuristic (pdf-9), used for the reader variant.
  - `preprocess.preprocess_html(html)` — regex passes (chrome/ad/icon/comment
    strip) used for **both** variants.
  - `archives.py`, `dom_utils.py`, `normalize_css.py` — support modules.
  - Output: `CleanResult` = `{whole_html, reader_html}` (§4).
- **FC-3 `html2md_core.js` (REPLICATED from docx, master=docx)** — the
  conversion core: `htmlToMarkdown(htmlString) → mdString` = verbatim lift of
  `buildTurndown` + `expandTableToGrid` from `docx2md.js`. `turndown` +
  `turndown-plugin-gfm`, domino DOM (the single real HTML parse in the
  pipeline). GFM tables (rowspan/colspan→flat grid), atx headings, fenced
  code, h1–h6→`<strong>` in cells.
- **FC-4 `emit.py` (NEW)** — Markdown assembly + Obsidian wrapping.
  - YAML frontmatter from `AcquireResult.source_meta`.
  - `--download-images` (default ON) → fetch each resolvable `<img>` into
    `_attachments/<sha1>.<ext>`, rewrite to relative links; `--no-download-
    images` keeps remote URLs verbatim.
  - **Dual-output (default):** writes `<slug>.md` (whole) + `<slug>.reader.md`
    (reader); `--no-reader` collapses to one. Both share ONE `_attachments/`.
  - stdout mode + `--json-errors` envelope for agent use.
- **FC-5 `html` launcher (NEW)** — extensionless CLI orchestrator + entrypoint
  (`scripts/html`; NOT `html.py`, which would shadow stdlib `html`). `_venv_
  bootstrap` prelude; threads flags; shells `node html2md_core.js` (HTML on
  stdin → Markdown on stdout); maps exceptions → exit codes / envelope. (The
  combined `scripts/html2md.py` command — fetch → convert → delete intermediate
  HTML — re-exports through this launcher.)

### 2.2. Functional Components Diagram

```
                 ┌──────────────────────── html launcher (FC-5, orchestrator) ───────────────────┐
 INPUT           │                                                                                │
 URL ───────────▶│  FC-1 acquire.py ──┐                                                           │
 .webarchive ───▶│   (dispatch +      │  raw HTML + source_meta + image map (AcquireResult)       │
 .mhtml ────────▶│    fetch/extract)  ▼                                                           │
 .html ─────────▶│  FC-2 web_clean ──────▶ {whole_html, reader_html} (CleanResult)                │
                 │   (pdf-master)     │                                                            │
                 │                    ▼                                                            │
                 │   node ──▶ FC-3 html2md_core.js (docx-master) ──▶ markdown(whole), markdown(reader)
                 │                    │                                                            │
                 │                    ▼                                                            │
                 │  FC-4 emit.py ─────────▶ <slug>.md + <slug>.reader.md + _attachments/  OR stdout │
                 └────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. System Architecture

### 3.1. Architectural Style

**Hybrid two-runtime pipeline.** A Python orchestrator owns I/O, acquisition,
cleaning, and emit; a short-lived Node subprocess owns the turndown
conversion. This is the established repo idiom (`md2pdf.py` shells to `mmdc`;
docx mixes Python `office/` with Node converters) and is the *only* way to
reuse **both** donor cores without rewriting turndown in Python (which would
lose battle-tested GFM fidelity) or re-porting pdf's cleaning to Node.

The pipeline is a **linear, mostly-pure transform chain** with a single
side-effecting stage (FC-4 emit, and FC-1's network/temp I/O). Each stage
hands a typed IR to the next, enabling stage-isolated tests.

### 3.2. System Components

| Layer | Runtime | Origin | Replication master |
|---|---|---|---|
| `html` launcher, `acquire.py`, `emit.py` | Python | NEW (html-owned) | — (skill-local) |
| `web_clean/{archives,reader_mode,preprocess,dom_utils,normalize_css}.py` | Python | **pdf** `html2pdf_lib/` | **pdf** (`diff -q` gated) |
| `web_clean/__init__.py` | Python | NEW (html-owned, thin) | — (NOT gated) |
| `html2md_core.js` | Node | **docx** `docx2md.js` | **docx** (`diff -q` gated) |
| `_errors.py`, `_venv_bootstrap.py` | Python | **docx** | **docx** (4→5-skill) |
| `package.json` (turndown, gfm), `requirements.txt`, `install.sh` | — | NEW | — (skill-local) |

### 3.3. Components Diagram (runtime boundary)

```
  ┌─ Python venv (.venv) ───────────────────────────────┐      ┌─ Node (node_modules) ─┐
  │ html ─ acquire.py ─ web_clean/* ─ emit.py           │ ───▶ │ html2md_core.js       │
  │   ▲ _errors.py  ▲ _venv_bootstrap.py                 │ ◀─── │   turndown + gfm      │
  │   soft-optional: httpx, trafilatura, playwright      │ stdin│   (domino DOM)        │
  └─────────────────────────────────────────────────────┘ /out └───────────────────────┘
```

---

## 4. Data Model (Conceptual IR between stages)

### 4.1. `AcquireResult` (FC-1 → FC-2)

| Field | Type | Notes |
|---|---|---|
| `html` | str | raw page HTML (main or chosen subframe) |
| `base_url` | str | for relative-URL / image resolution (`file://` for offline) |
| `mode` | enum | `url` \| `archive` \| `file` |
| `engine` | enum | `lite` \| `chrome` (only meaningful for `url`) |
| `source_meta` | `SourceMeta` | `(url, title, date, author)` frozen dataclass — frontmatter source (trafilatura-derived for `url`; `<title>`/OpenGraph fallback otherwise) |
| `images` | dict | `{original_url → local_temp_path}` for archive/file inputs (empty for `url` until FC-4 downloads) |

### 4.2. `CleanResult` (FC-2 → FC-3)

| Field | Type | Notes |
|---|---|---|
| `whole_html` | str | `preprocess_html(html)` — chrome/ad/icon stripped, whole page |
| `reader_html` | str \| None | `reader_mode_html(preprocess_html(html))` — article only; `None` when `--no-reader` |

### 4.3. Emit artifacts (FC-4)

| Field | Type | Notes |
|---|---|---|
| `frontmatter` | dict→YAML | `source`, `title`, `date`, `author`, `tags: []` |
| `attachments` | dict | `{sha1 → bytes}` written once to `_attachments/`, shared across both variants |
| outputs | files/stdout | `<slug>.md` (+ `<slug>.reader.md` by default), or Markdown on stdout |

### 4.4. Derived invariants

- **I-1 (single parse):** the only spec-compliant DOM parse is domino inside
  FC-3; FC-1/FC-2 operate on HTML as strings (regex/stdlib) — no lxml/bs4 in
  the cleaning path.
- **I-2 (attachment dedup):** identical image bytes → one `_attachments/` file
  regardless of which variant references them (sha1 key).
- **I-3 (offline determinism):** archive/file inputs make **zero** network
  calls (AC-R1 / AC-R2); only `mode=url` touches the network.

---

## 5. Interfaces

### 5.1. `html` launcher public CLI

```
html INPUT [OUTPUT_DIR]
  INPUT                  URL | path to .html/.htm/.mhtml/.mht/.webarchive
  --engine lite|chrome|auto      (default: auto = lite then chrome fallback)
  --reader-mode / --no-reader    (dual-output default ON; --no-reader = single .md)
  --download-images / --no-download-images   (default: ON)
  --attachments-dir _attachments             (default: _attachments)
  --max-bytes N / --max-images N             (fetch + image-download caps; SSRF/DoS bound, §7)
  --archive-frame main|N|all|auto            (webarchive/mhtml subframe; default main)
  --stdout                       emit Markdown to stdout (implies --no-download-images
                                 unless OUTPUT_DIR given; agent-step mode)
  --json-errors                  machine-readable {v:1,error,code,type?} envelope
```

Exit codes: `0` ok; `1` IO/convert failure; `2` argparse/usage; `3`
`EngineNotInstalled` (Chrome requested, dep absent); `6` `SelfOverwriteRefused`
(output path collision, incl. symlink via `Path.resolve()`); `10` `FetchFailed`
(URL unreachable/blocked). Range `10+` reserved for domain codes (argparse
stays 0–2), per the pdf/pptx convention.

### 5.2. Node bridge contract (FC-5 ↔ FC-3)

```
# the html launcher spawns (NO shell; argv list; bounded):
node html2md_core.js   < clean.html   > body.md
# stdin  : cleaned HTML (one variant per call: whole, then reader)
# stdout : GFM Markdown body (frontmatter is added by emit.py, NOT the Node core)
# exit 0 ok; non-zero → orchestrator raises ConvertFailed → envelope
```

`html2md_core.js` is a **pure** `stdin→stdout` filter: no file I/O, no
frontmatter, no image handling — keeping it byte-identical to the docx master
(which only knows HTML→MD).

### 5.3. Error envelope (reused, read-only)

`_errors.py` (4→5-skill replica, master=docx) — `add_json_errors_argument` +
`report_error(msg, code, type, details, json_mode)` → `{v:1,error,code,type?}`.
Imported read-only by every Python entrypoint; the file is NOT edited here.

### 5.4. SKILL.md / docs contract

`SKILL.md` (Gold-Standard) triggers: "html to markdown", "url to markdown",
"web page to obsidian", "webarchive/mhtml to markdown", "scrape page to
notes". `references/html-to-markdown.md` documents the decision tree
(URL vs archive vs file; reader vs whole; lite vs chrome) and honest scope.

---

## 6. Technology Stack

| Concern | Choice | Justification |
|---|---|---|
| HTML→MD core | `turndown@7.2` + `turndown-plugin-gfm@1.0` (domino DOM) | proven in `docx2md.js`; reuse, don't reinvent |
| HTML cleaning | pdf `html2pdf_lib` (regex + stdlib `email`/`plistlib`) | most mature cleaner in repo; zero heavy deps |
| URL transport | `httpx` | modern, timeouts, sync API |
| Lite extraction + metadata | `trafilatura` | main-content extraction **and** title/date/author for frontmatter; readability-lxml = fallback |
| JS/SPA fetch | `playwright` (soft-optional, `requirements-chrome.txt`) | only path that handles hydrated SPAs; opt-in, ~150 MB |
| Error/bootstrap | `_errors.py`, `_venv_bootstrap.py` | repo-standard, replicated |

`requirements.txt` (base): `httpx`, `trafilatura`. `requirements-chrome.txt`
(soft-optional): `playwright`. `package.json`: `turndown`,
`turndown-plugin-gfm`. Every new dep → `THIRD_PARTY_NOTICES.md` in the same
commit.

---

## 7. Security

- **SSRF / fetch boundary (NEW surface).** `acquire._http_get_bytes` is the only
  component that makes outbound requests (the lite URL path + url-mode image
  download). Mitigations (as-built): non-`http(s)` schemes refused
  (`file:`/`gopher:`/`data:` top-level INPUT is treated as local, not fetched);
  **every hop — the initial URL and each redirect — is re-resolved and refused if
  any resolved address is loopback / private / link-local / reserved / multicast,
  incl. 169.254.169.254 cloud-metadata** (`_host_is_public`/`_assert_public_http`);
  redirects followed manually with a hop cap; the body is **streamed and aborted
  the instant it passes `--max-bytes`** (no full-buffer OOM); `--max-images` bounds
  the number of remote image *fetches*, not just writes; request timeout; no
  credential forwarding; error envelopes redact userinfo + query (`_redact`).
  **Honest-scope residuals (§10):** (a) the public-IP check is resolve-then-connect,
  so a DNS-rebinding attacker controlling authoritative DNS can still flip the
  address in the TOCTOU window — run untrusted conversions in an egress-restricted
  sandbox; (b) the **Chrome engine is NOT network-hardened** — it is a basic
  `launch + goto` that follows redirects (incl. to internal hosts) without the
  public-IP gate and does not block beacons; full hardening is deferred.
- **Archive parsing (inherited).** `web_clean/archives.py` uses stdlib
  `plistlib`/`email` (no XML entity expansion surface); path-traversal in
  sub-resource names is sanitised before writing to the temp dir.
- **Decompression / DoS.** Cap downloaded image size + count; sha1-dedup
  bounds disk. Bounded Node subprocess (timeout) — never blocks the orchestrator.
- **No code execution from content (lite/offline paths).** turndown/domino do
  not execute page JS; the offline file/archive paths and the lite URL path never
  run page scripts. The opt-in Chrome engine DOES execute page JS (that is how it
  hydrates SPAs) and is not network-isolated — see the §7 Chrome honest-scope note
  and §10; it is off by default (requires `install.sh --with-chrome`).
- **Self-overwrite guard.** Exit 6 on output==input collision (incl. symlink).

---

## 8. Scalability & Performance

- **Lite path** (`httpx`+trafilatura): sub-second per page, no browser.
- **Chrome path:** 1–3 s/page + ~150 MB install; opt-in, only when lite
  yields an empty/JS-shell body (`auto`) or `--engine chrome`.
- **Node bridge:** one `node` spawn per variant (≤2 per run: whole + reader);
  bounded by timeout. For batch use, the orchestrator processes inputs
  serially in v1 (no worker pool — deferred; see §13).
- **Image download:** sequential with sha1-dedup; identical images fetched
  once. Bounded by `--max-bytes`/count caps.

---

## 9. Cross-Skill Replication Boundary (CLAUDE.md §2 — load-bearing, TWO-master)

**This task IS a replication event** (unlike pptx2md). It introduces the repo's
**first two-master skill** and the documented exception to "docx is always
master". Authoritative rule: `CLAUDE.md` §2 «Future skill html2md».

| File / unit | Master | Tier | Action |
|---|---|---|---|
| `html2md_core.js` | **docx** | NEW gated unit | lift `buildTurndown`+`expandTableToGrid` from `docx2md.js`; docx2md.js imports it; `diff -q` gated |
| `web_clean/archives.py` | **pdf** | NEW gated unit | byte-identical copy from `html2pdf_lib/` |
| `web_clean/reader_mode.py` | **pdf** | NEW gated unit | byte-identical copy |
| `web_clean/preprocess.py` | **pdf** | NEW gated unit | byte-identical copy |
| `web_clean/dom_utils.py` | **pdf** | NEW gated unit | byte-identical copy |
| `web_clean/normalize_css.py` | **pdf** | NEW gated unit | byte-identical copy — inert for MD output, but a **hard import dependency** of `preprocess.py` (`from .normalize_css import NORMALIZE_CSS`), so it MUST be carried, not "optional ballast" |
| `render.py`, `chrome_engine.py`, `html2pdf_lib/__init__.py` | pdf | **EXCLUDED** | **NEVER replicate** — only weasyprint/playwright carriers (weasyprint imported at module top in `render.py` alone) |
| `web_clean/__init__.py` | html | NOT gated | html-authored thin re-export of clean symbols only |
| `_errors.py` | **docx** | 4→**5**-skill | add `html` to existing replication loop |
| `_venv_bootstrap.py` | **docx** | 4→**5**-skill | add `html` to existing replication loop |
| `preview.py`, `_soffice.py`, `office/`, `office_passwd.py` | docx | N/A | **not used** (html emits Markdown, not renderable office docs) |

**Why pdf-master (the exception):** the cleaning code physically originates in
`pdf/html2pdf_lib/`. Replicating from there keeps html in sync with future
pdf hardening. Re-pointing it to docx would invert reality and break sync.
Flagged loudly in CLAUDE.md anti-patterns so a reviewer never "corrects" it.

**Why carry whole (no trimming):** the weasyprint-specific functions in
`preprocess.py`/`normalize_css.py` are **inert regex with no heavy imports** —
dead *weight*, not dead *dependency*. Trimming makes `diff -q` impossible (no
gate can verify a subset stayed in sync) → silent fork on the next pdf change.
A few KB of unused code is the correct price for fork-freedom.

**Guards (gate at integration bead):**
- **G-1 `diff -q`:** silent between `docx↔html` core and `pdf↔html`
  `web_clean/*.py` (the 5 gated files), after `__pycache__` clean.
- **G-2 import smoke-test:** `weasyprint` and `playwright` NOT in
  `sys.modules` after importing the **real leaf entrypoints** `acquire.py`
  uses — `web_clean.archives` AND `web_clean.reader_mode` (which pull the
  whole closure `preprocess`→`dom_utils`+`normalize_css`) — not just the thin
  package root. Defends the `__init__.py` trap across the full import graph.
- **G-3 docx no-drift:** docx `test_e2e.sh` + `test_battery.py` round-trip
  byte-identical before/after the core extraction (AC-R3).
- **G-4 (R8, post-MVP):** CI `diff -q`/`diff -qr` step in
  `.github/workflows/office-skills.yml` covering both masters + `html` in
  the skill matrix — the only durable defence against silent divergence
  (replication is human-enforced today).

---

## 10. Honest Scope (v1)

- **Markdown fidelity inherits turndown limits.** rowspan/colspan → flat grid
  (anchor value + blanks); inline CSS / class styling ignored; nested tables
  best-effort. Identical to `docx2md` because it is the same core.
- **Fetch coverage is bounded.** paywalled/auth-gated pages are out of scope;
  JS/SPA pages only convert via the Chrome fallback (lite path returns the
  pre-hydration shell). `robots.txt` / rate-limiting / ToS compliance is the
  **caller's** responsibility — the tool does not police them.
- **SSRF residuals (lite path is hardened; two gaps remain).** The lite path
  blocks private/loopback/link-local/metadata targets on every redirect hop and
  streams with a `--max-bytes` cap (§7). NOT covered: (a) **DNS rebinding** — the
  public-IP check is resolve-then-connect (TOCTOU); (b) the **Chrome engine** does
  NO SSRF/network hardening (basic `launch + goto`, follows internal redirects).
  Convert untrusted input in a network-egress-restricted sandbox.
- **Reader extraction is best-effort.** the pdf-9 SPA-chrome heuristic
  gracefully degrades on landmark-free DOM (`ya_browser`-class) — sidebar text
  may leak into `reader.md`; the whole-page `.md` is always available as the
  faithful fallback.
- **Metadata is best-effort.** `source/title/date/author` populated when the
  page exposes them (trafilatura / `<title>` / OpenGraph); `tags: []` left for
  the user (Q6).
- **v1 is serial.** no batch worker pool; one input per invocation, ≤2 Node
  spawns. Batch/parallel deferred (§13).
- **Proprietary, not Apache-2.0** — embeds proprietary docx/pdf code; ships
  its own per-skill `LICENSE`/`NOTICE`.

---

## 11. Atomic-Chain Skeleton (Planner handoff — Stub-First)

Proposed beads for `/vdd-plan`. Beads **022-01** (replication) and the
integration bead **022-07** edit/verify the gated masters; all guards (§9
G-1…G-4) live at the integration bead.

| Bead | Scope (RTM) | Stub-First role |
|---|---|---|
| **022-01** | Skeleton: `skills/html/` scaffold (`init_skill.py`), `scripts/` package, `_venv_bootstrap` prelude, **replicate** `web_clean/*` (pdf) + `html2md_core.js` (docx) + thin `web_clean/__init__.py`, `_errors.py`/`_venv_bootstrap.py` 4→5, import smoke-test (G-2), **RED** E2E/unit scaffolding (file/archive/url happy-paths, dual-output, `--no-reader`, `--no-download-images`, stdout, exit-3/6/10, `--json-errors`) | STUB + tests (Red) + replication |
| **022-02** | FC-1 `acquire.py` **offline** paths first — file read + archive dispatch (`web_clean/archives.py`) + format/magic-byte detection → `AcquireResult` | LOGIC (Green) — R1(c–e), I-3 |
| **022-03** | FC-3 `html2md_core.js` extraction from `docx2md.js` + Node bridge in FC-5 + **G-3 docx no-drift regression** | LOGIC (Green) — R3, AC-R3 |
| **022-04** | FC-2 `web_clean` wiring — `preprocess_html` (whole) + `reader_mode_html` (reader) → `CleanResult`; reader needle test (AC-R2) | LOGIC (Green) — R2 |
| **022-05** | FC-4 `emit.py` — frontmatter + `_attachments` sha1-dedup + dual-output + stdout/`--json-errors`; **MVP gate** (offline file/archive → md) | LOGIC (Green) — R4/R5, **MVP** |
| **022-06** | FC-1 URL path — `httpx`+`trafilatura` lite + Chrome `auto` fallback (soft-optional) + SSRF caps + exit-3/10 | LOGIC (Green) — R1(a,b), §7 |
| **022-07** | Docs + integration: `SKILL.md`, `references/html-to-markdown.md`, per-skill `LICENSE`/`NOTICE`, `THIRD_PARTY_NOTICES.md`, `install.sh --with-chrome`, backlog html2md-1…5 → done; **G-1 `diff -q` + G-2 smoke + validate_skill ×5 + (G-4) CI gate**; dogfood real fixtures (URL + .webarchive + .mhtml) | INTEGRATION + DOC |

**MVP gate = 022-01…05** (offline file/archive → dual Markdown + frontmatter +
`_attachments`). **022-06 (URL fetch)** is MVP but Chrome-soft-optional (URL
lite path always available; Chrome fallback engine-gated like pdf-11).

---

## 12. Decision-Record Summary

- **D-1 (hybrid two-runtime).** Python orchestrator + Node turndown subprocess.
  Reuses BOTH donor cores without rewriting turndown (Python `markdownify`
  would lose GFM fidelity) or re-porting pdf cleaning to Node. Repo precedent:
  `md2pdf`→`mmdc`. (TASK Q-runtime.)
- **D-2 (TWO masters — the exception).** `html2md_core.js` master=docx;
  `web_clean/*` master=pdf. First documented exception to "docx is always
  master"; codified in CLAUDE.md §2 + anti-patterns. (Adversarial-verified.)
- **D-3 (exclude the weasyprint carriers).** `render.py`/`chrome_engine.py`/
  package `__init__.py` are NEVER replicated; html ships an owned thin
  `web_clean/__init__.py`. Verified: weasyprint is a module-top import in
  `render.py` alone; playwright absent from the 5 clean modules. Guard: G-2
  smoke-test.
- **D-4 (carry cleaning modules WHOLE).** No trimming of inert weasyprint-
  specific regex — trimming breaks `diff -q` and silently forks. byte-identity
  > cleanliness.
- **D-5 (trafilatura as lite extractor).** Chosen over readability-lxml because
  it also yields `title/date/author` for frontmatter (R4). readability = fallback.
- **D-6 (dual-output default).** Emit both `<slug>.md` + `<slug>.reader.md`;
  `--no-reader` collapses. Per `feedback_pdf_dual_render`. (TASK Q5.)
- **D-7 (`acquire.py` = owned fork, not gated replica).** Adapts
  `chrome_engine.py`'s fetch hardening as html-owned code (fetch semantics
  differ from pdf's render-only `goto`). "Gated replication ≠ owned fork".
  (TASK Q7.)
- **D-8 (image download flag + `_attachments`).** `--download-images` default
  ON → `_attachments/` (sha1-dedup, relative links); `--no-download-images`
  keeps remote URLs (agent mode). Folder name `_attachments` (Obsidian
  convention). (User 2026-06-17.)
- **D-9 (proprietary license).** Derived work embedding proprietary docx/pdf
  code ⇒ Proprietary, All Rights Reserved + per-skill `LICENSE`/`NOTICE`.
  (User 2026-06-17; CLAUDE.md §3.)
- **D-10 (core is a pure stdin→stdout filter).** `html2md_core.js` does no
  frontmatter/image/file work — keeps it byte-identical to the docx master.

---

## 13. Open Questions

- **OQ-1 (Q6 carry-over):** auto-derive frontmatter `tags:` from `<meta
  keywords>`/OpenGraph, or leave `[]`? Proposed: leave `[]` in v1 (avoid noisy
  tags); revisit after dogfood.
- **OQ-2 (`--engine auto` heuristic):** what structural signal flips lite→chrome?
  Proposed: empty/near-empty extracted body OR `<script>`-bundle ≥ threshold
  with no article — reuse pdf-11's structural pre-scan idea (no vendor names).
- **OQ-3 (batch/worker pool):** v1 is serial; if batch clipping becomes a real
  need, add `--jobs` with profile-isolated workers (pptx2md precedent). Deferred.
- **OQ-4 (CI fork-gate timing):** G-4 (R8) — land the CI `diff -q` gate in the
  same release as the skill, or fast-follow? Recommended: same release (it is
  the only durable no-fork guarantee).
- **OQ-5 (wiki bridge):** out of scope for v1 (user chose standalone), but
  `emit.py` Markdown + frontmatter is intentionally shaped to feed
  `wiki-ingest` later without rework.

---

## 14. As-built additions (post-implementation, 2026-06-17)

Living-document delta over §1–13 (which describe the planned design). Shipped via
`/vdd-develop-all` + two `/vdd-multi` review rounds + real-corpus dogfooding.

- **FC-3 path is a wrapper, not the bare core.** `core_bridge.py` spawns the
  html-owned **`html_convert.js`** (NOT gated), which `require()`s the
  docx-mastered `html2md_core.buildTurndown()` (kept byte-identical) and adds web-page
  turndown rules the docx core doesn't need: **ARIA-role tables → GFM** (scoped to the
  own table; sibling-rowgroup headers), strip `<button>`/`role=button`(leaf)/
  `aria-label^="Copy"`, **collapse multi-line links to one line + drop icon/zero-width
  anchors**. docx2md.js still calls `buildTurndown()` directly (no wrapper) → unaffected.
- **FC-4 gains a post-turndown tidy.** New html-owned **`html2md/md_clean.py`** (the
  internal package keeps its `html2md` name to avoid shadowing stdlib `html`):
  merge empty ATX headings with their detached title, drop high-confidence standalone
  chrome lines, collapse blank runs. Applied in `cli.convert` to both variants.
- **CLI default output (§5.1 amended):** omitting `OUTPUT_DIR` (and `--stdout`) now
  writes to `./tmp/html_out/` (created **lazily** by `emit`); output names are
  collision-safe + idempotent via a hidden `html-source-id` marker.
- **Security hardening (§7 as-built):** SSRF per-redirect-hop public-IP gate +
  streaming `--max-bytes` cap; `<img>` reads confined to `base_dir` (CWE-22);
  **PDF/binary fetch guard** (`%PDF`/NUL → clean `FetchFailed`, no turndown stack
  overflow). Residuals in `docs/KNOWN_ISSUES.md` §HTML2MD.
- **Battery (G-5):** `tests/{capture_signatures.py, battery_signatures.json,
  test_battery.py}` + committed `examples/regression/gitbook-style-doc.html`. Asserts
  `empty_headings==0`, `stray_chrome==0`, required needles, metric tolerance bands.
  Wired into `tests/test_e2e.sh` (alongside the G-1/G-2 `diff -q` gate).

---

## 15. TASK 023 — resilient vendor-agnostic remote-reader tier & fallback ladder

Living-document delta for **TASK 023** (`docs/TASK.md`). §1–14 describe the TASK 022
base; this section specifies the enhancement and **supersedes** the named earlier
clauses where it conflicts (§2.1 FC-1, §4.1 `engine` enum, §5.1 CLI, §7 security).
Scope guard: **all changes are html-owned** (`acquire.py`, `cli.py`, the `html2md/` package tests,
`SKILL.md`, `references/`); **no `diff -q`-gated master is touched**, so §9 G-1/G-2/G-3
hold by construction.

### 15.1. What changes (no new file, no new dependency)

The enhancement lives entirely inside **FC-1 `acquire.py`** (+ `cli.py` surface). Two
new internal concerns are added; the FC inventory (§2.1) and the pipeline (§2.2) are
otherwise unchanged:

- a **`RemoteReader` provider abstraction** (vendor-agnostic remote URL→content tier), and
- a **fetch-ladder orchestrator** that sequences `lite` / `chrome` / remote tiers with
  bidirectional fallback.

`httpx` (already a base dep) is reused through the single existing network seam
`_http_get_bytes`; **nothing is added to `requirements.txt`**.

### 15.2. The fallback ladder (state machine — R1)

```
--engine auto (default, LOCAL-FIRST / privacy-first)
    lite ──ok──▶ done
     │ JS-shell                │ blocked (403 after browser-UA) / EmptyExtraction
     ▼                          ▼
    chrome (if installed) ──ok──▶ done
     │ unavailable / fail       │
     ▼                          ▼
    remote-reader tier ──ok──▶ done        (skipped if target not public, or --no-remote)
     │ all providers down
     ▼
    FetchFailed(kind=all_engines_failed, details.tried=[…])   ← exactly one typed error

--engine jina | remote (REMOTE-FIRST, on demand)
    remote-reader tier ──ok──▶ done
     │ provider down/429/402/5xx/timeout
     ▼
    lite ──ok──▶ done ──▶ (JS-shell) chrome ──ok──▶ done
     │ all fail
     ▼
    FetchFailed(kind=all_engines_failed, details.tried=[…])
```

Rules: (a) a tier is *attempted* only if applicable (remote needs a public target +
`--no-remote` off; chrome needs Playwright); (b) **fall-through** happens on
provider-down/transient classes (§15.4) — a terminal **target** error short-circuits the
ladder (§15.4); (c) the ladder raises **one** typed `FetchFailed` only when every viable
tier is exhausted (AC-R1, never a bare traceback); (d) each tier is bounded by the
existing per-request timeout, so worst-case ladder latency = Σ attempted tiers (serial
v1 — no unbounded stall).

**Tier-failure taxonomy (load-bearing):** distinguish three failure scopes — a
**provider** failure (this reader is down → try the next *provider*), a **target**
failure (the page itself is 403/404 as reported by a reader → stop trying more *remote
providers*, but `auto` may still try a different *tier* such as `chrome`), and a **local
tier** block (a `lite`/`chrome` 403 surviving the browser-UA retry → **escalate to the
remote tier**, the ssrn/researchgate recovery case). `EngineNotInstalled` from `chrome`
reached as an *auto fallback* is a fall-through (not exit 3); an **explicit**
`--engine chrome` without Playwright stays exit 3. See §15.4.

### 15.3. `RemoteReader` provider abstraction (R2 — vendor-agnostic)

A tiny provider record (no class hierarchy needed): given a target URL + opts, it yields
the **reader request URL** + **headers**, and knows how to classify its own response.

| Provider | Reader base | Selected by | Auth env |
|---|---|---|---|
| `jina` (built-in default) | `https://r.jina.ai/<url>` | default; `--engine jina` | `JINA_API_KEY` → `Authorization: Bearer` |
| generic (configured) | `${HTML_READER_URL}<url>` | `HTML_READER_URL` set | optional `HTML_READER_TOKEN` |
| ordered list | each `<base><url>` | `HTML_READER_PROVIDERS` (comma/space list) | per-entry |

- **Ordering:** if `HTML_READER_PROVIDERS` is set it is the order; else `HTML_READER_URL`
  (if set) then `jina`. Providers are tried in order, falling through on provider-down.
- **Self-hosted Jina** (open-source `jina-ai/reader`) is just `HTML_READER_URL` pointing
  at the local instance — the key vendor-agnostic story (resilience independent of jina.ai
  uptime).
- **`--engine remote` requires configuration (privacy guard).** `--engine remote` selects
  the *configured generic* provider(s); with **no** `HTML_READER_URL`/
  `HTML_READER_PROVIDERS` set it is a **usage error (exit 2)** ("use `--engine jina` for
  the built-in") — it MUST NOT silently fall back to `jina.ai` (that would betray a user who
  picked `remote` precisely to avoid jina). `--engine jina` = the built-in; `auto` = jina is
  the last-resort built-in. Decision frozen at bead 023-01 (CLI-surface freeze).
- **Auth is per-provider, not interchangeable:** built-in `jina` → `JINA_API_KEY`;
  generic/configured → `HTML_READER_TOKEN`. A self-hosted "jina-shaped" reader configured
  via `HTML_READER_URL` uses `HTML_READER_TOKEN`, NOT `JINA_API_KEY`.
- **Request shape:** `GET <base><target>` with headers `X-Return-Format: html|markdown`
  (§15.5 R4), `X-Target-Selector: <sel>` (R4), `Authorization` (if keyed). The base+target
  join is literal-concatenation (Jina's `r.jina.ai/https://…` convention), not `urljoin`.

### 15.3a. Search provider (R9 — vendor-agnostic web search)

A sibling of the reader abstraction for the **query → top-N pages → Markdown** entrypoint
(`--search "QUERY"`). Same fall-through discipline; same `_http_get_bytes` seam.

| Provider | Shape | Reader URL | Result handling |
|---|---|---|---|
| `s.jina.ai` (built-in default) | **combined** | `https://s.jina.ai/<query>` | server-side search+fetch returns **merged Markdown** of top results → split/wrap with frontmatter |
| generic (configured) | **links** | `${HTML_SEARCH_URL}<query>` | returns a list of **result URLs/JSON** → each URL fetched via the **R1 FETCH ladder** (so every result inherits Jina/local fallback) |

- **Selection/order:** `HTML_SEARCH_PROVIDERS` (ordered list) else `HTML_SEARCH_URL`
  (if set) then `s.jina.ai`. Providers tried in order, falling through on provider-down
  (§15.4) — a search provider has **no local equivalent**, so once all are exhausted the
  ladder raises one typed `FetchFailed` (honest: there is no offline web search).
- **Two shapes, one resilience story:** the *links* shape is the truly vendor-agnostic
  path — search only ranks/selects URLs, and the proven FETCH ladder (with its own
  per-URL fallback) does the conversion, so a per-result Jina failure still degrades to
  local. The *combined* shape (s.jina.ai) is the convenience path.
- **Emit:** one note per result into OUTPUT_DIR (shared `_attachments/`), frontmatter
  carries `query:` + the result `source:` URL; an individual failed result is **skipped,
  not fatal**; `--stdout` concatenates. `--max-results N` bounds the count (default 5).
- **Mutual exclusion:** `--search` and a positional URL/file INPUT are mutually exclusive
  (cli usage error, exit 2, if both given).

### 15.4. Failure classification (R3 — provider-down vs target-blocked)

| Observed | Class | Ladder action |
|---|---|---|
| DNS / connect / read **timeout**, transport error | provider transient | retry+backoff (existing), then **fall through** |
| HTTP **5xx**, **503**, **502** | provider down | retry (existing), then **fall through** |
| HTTP **429** + `Retry-After` | provider rate-limited | bounded 429 retry (existing), then **fall through** |
| HTTP **402** (quota/payment) | provider quota | **fall through** (no retry) |
| **empty / < N-char** reader body | provider miss | **fall through** |
| reader maps the **target's** 403 / 401 / 404 | **target** block/absence | **terminal** — surface `kind∈{bot_blocked,auth_required,not_found}`, do **not** retry other providers |

This split (a) survives any single provider's outage and (b) avoids pointless
cross-provider retries of a genuinely-404/blocked target. Classification reuses
`_fetch_kind` + the existing `_http_get_bytes` retry loop; the *new* logic is the
"fall through to next tier" wrapper, not new transport code.

### 15.5. Data-model & interface deltas

**`AcquireResult.engine`** (supersedes §4.1) now ranges over:
`lite | lite+arxiv-html | lite+restapi | lite+nojs | jina | remote:<host> | chrome`.

**`FetchFailed.details`** gains `tried: [{engine, kind, status?}]` (R6) on
total-ladder failure, plus `kind="all_engines_failed"`.

**CLI surface deltas (supersede §5.1):**
```
--engine lite|chrome|auto|jina|remote   (adds 'remote' = remote-first, generic provider)
--no-remote                             (disable the remote-reader tier entirely; auto+on-demand)
--remote-format html|markdown           (default html → local pipeline; markdown → trust reader's MD)
--target-selector SEL                   (X-Target-Selector; default 'article, main, [role=main]')
--search "QUERY"                        (R9 search entrypoint; mutually exclusive with a URL/file INPUT)
--max-results N                         (top-N results to fetch+convert for --search; default 5)
```
**Environment (new, optional):** `HTML_READER_URL`, `HTML_READER_PROVIDERS`,
`HTML_READER_TOKEN`, `HTML_SEARCH_URL`, `HTML_SEARCH_PROVIDERS`, plus the
existing `JINA_API_KEY`.

**Frontmatter:** `engine:` reflects the real tier; **`source:` stays the canonical
target URL** (never the reader URL) — provenance correctness (R6b).

**Search multi-result IR (R9 — supersedes §4.1 for the `--search` path):** `--search`
yields a **list** of per-result `AcquireResult`s, not a single one. `cli.convert` loops
the existing single-result emit over them — one note per result into OUTPUT_DIR, sharing
one `_attachments/`; an individual result that fails is **skipped** (logged in the trace),
not fatal. `--stdout` concatenates.

**Trust-markdown data path (R4 `--remote-format markdown` — supersedes §4.1's HTML
assumption):** `AcquireResult` gains `content_kind ∈ {html, markdown}` (+ a `markdown`
payload when `markdown`). For `content_kind == markdown`, `cli.convert` **bypasses FC-2
(`web_clean`) and FC-3 (`core_bridge`/turndown)** entirely and applies only frontmatter
wrapping + (if `--download-images`) image localization. Default `html` threads through the
unchanged pipeline. The reader variant (`<slug>.reader.md`) is **not** produced in
trust-markdown mode (there is no second extraction to derive it from).

### 15.6. Security / privacy (supersedes/extends §7, R5)

- **Target public-IP gate before remote escalation.** Before sending a target to *any*
  remote reader, `_host_is_public(target_host)` must pass — a private/loopback/link-local/
  metadata/unresolvable target is **never** forwarded to an external service (auto AND
  on-demand). This closes the gap where today `_fetch_jina_html` only checks scheme.
- **`--no-remote`** is a hard kill-switch (no external egress via the reader tier).
- **URL-leaves-machine** posture documented in `SKILL.md` §5 + `references/` + KNOWN_ISSUES
  HTML2MD-6; auto-escalation makes this reachable without `--engine jina`, so the docs must
  state it prominently. The local hop to the reader still passes the SSRF gate.
- **Request-URL construction (injection guard).** The operator-set reader/search **base**
  is trusted, but the **target URL / search query is not**: URL-encode the target/query
  when concatenating onto a base, and **reject CRLF / control chars** in the target before
  building the request (prevents request-splitting, header injection, and SSRF-via-
  injection through a configurable base). The target is already validated `http(s)` +
  public (above) before it reaches this step.
- **Image localization stays SSRF-gated (hard invariant).** Image localization — incl.
  images found in a reader's returned Markdown (trust-markdown) or HTML — **MUST go through
  `_http_get_bytes`** (never a direct `httpx` call / bulk fetch), because the per-hop
  `_assert_public_http` inside it is the SSRF boundary. A gated-out (internal/metadata) image
  URL makes `_resolve_url_image` return `None` → the image is **dropped, never fatal** (that
  honest-degradation is the actual guarantee, not "passes the gate"). Bounded by
  `--max-images`/`--max-bytes`. Bead 023-05 acceptance includes a test that an internal-IP
  image URL in reader Markdown is NOT fetched.
- **`tried` trace carries no URL.** `FetchFailed.details.tried` entries are
  `{engine, kind, status?}` ONLY — no target/reader URL — so the observability trace cannot
  leak a configured internal reader base or a token (the `_redact` discipline of §7 stays
  the sole URL-in-envelope path).
- **Honest-scope residuals unchanged:** DNS-rebinding TOCTOU and the un-hardened Chrome
  engine (§10) are not regressed or newly mitigated here.

### 15.7. Fork-free integrity (R8 — confirmed)

`acquire.py` and `cli.py` are **html-owned, NOT** in the G-1/G-2 gate (the gate covers
only `web_clean/*.py`, `html2md_core.js`, `_errors.py`, `_venv_bootstrap.py` — see
`scripts/tests/test_e2e.sh`). No master byte-changes ⇒ G-1/G-2 stay silent and docx G-3
stays byte-identical. No new dependency ⇒ isolation preserved.

### 15.8. Decision records (TASK 023)

- **D-23-A (ladder).** `auto` = local-first with remote last-resort escalation
  (privacy default, `--no-remote` opt-out); `--engine jina|remote` = remote-first with
  local fallback. User-confirmed "best option".
- **D-23-B (vendor-agnostic providers).** Pluggable/configurable remote readers, `jina`
  default, self-hosted via env. Resilience independent of any single vendor (user-asked).
- **D-23-C (provider-down vs target-blocked).** Fall through only on provider/transient
  classes; report a blocked/absent target honestly (§15.4).
- **D-23-D (smarter extraction).** `X-Target-Selector` always; `--remote-format markdown`
  opt-in trust-mode; default html-through-local-pipeline for output consistency.
- **D-23-E (owned files only).** No gated master edited; gate green by construction.
- **D-23-F (no new dep).** Provider layer = plain `httpx` via `_http_get_bytes`.

### 15.9. Atomic-chain skeleton (Planner handoff — Stub-First, for /vdd-plan)

| Bead | Scope (RTM) | Stub-First role |
|---|---|---|
| **023-01** | Freeze the new CLI surface (`--engine remote`, `--no-remote`, `--remote-format`, `--target-selector`, `--search`, `--max-results`) + `RemoteReader`/`SearchProvider` records + ladder skeleton (stubs) + **RED** tests (ladder matrix, classification, privacy guard, search) via the `_http_get_bytes` seam | STUB + tests (Red) |
| **023-02** | `RemoteReader` provider layer: jina + generic/env-configured + ordering + header/URL construction (R2) | LOGIC (Green) — R2 |
| **023-03** | Fetch-ladder orchestrator: local-first (auto) + remote-first (jina/remote) + fall-through + one terminal typed error + `tried` trace (R1/R3/R6) | LOGIC (Green) — R1/R3/R6 |
| **023-04** | Privacy/SSRF: target public-IP gate before remote + `--no-remote` enforcement + tests (R5) | LOGIC (Green) — R5 |
| **023-05** | Smarter extraction: `X-Target-Selector` + `--remote-format markdown` trust-mode emit (+ image localization) (R4) | LOGIC (Green) — R4 |
| **023-06** | Web search: `SearchProvider` layer (`s.jina.ai` combined + generic links-shape via env) + `--search`/`--max-results` + per-result FETCH-ladder routing + search-provider fallback + per-result skip-on-fail + one-note-per-result emit (R9) | LOGIC (Green) — R9 |
| **023-07** | Docs + integration: `SKILL.md`, `references/html-to-markdown.md`, KNOWN_ISSUES HTML2MD-1/-6, backlog §2; `validate_skill.py` exit 0; **assert G-1/G-2/G-3 unchanged**; dogfood anti-bot URL + forced-Jina-failure + a `--search` run | INTEGRATION + DOC — R7/R8 |

**MVP gate = 023-01…04** (resilient vendor-agnostic ladder + privacy). 023-05 (smarter
extraction), 023-06 (web search, R9) and 023-07 (docs) complete the task. Each Phase-2
bead gets an adversarial logic+security roast (`/vdd-multi`) before "done"; **no
auto-commit**.

### 15.10. Open questions (TASK 023)

- **OQ-23-1 (default privacy posture):** auto-escalate to remote by default for public
  targets (chosen) vs require explicit `--allow-remote`. Default = auto-escalate-on,
  `--no-remote` opt-out — to be confirmed at the architecture-review gate.
- **OQ-23-2 (provider-config surface):** single `HTML_READER_URL` vs ordered
  `HTML_READER_PROVIDERS` — proposed: support both.
- **OQ-23-3 (RESOLVED):** web search is **IN SCOPE** (user 2026-06-23) — see §15.3a + R9.
  `s.jina.ai` is the built-in default; the *links*-shape generic provider routes each
  result through the FETCH ladder so search inherits the full fallback discipline.
- **OQ-23-4 (trust-markdown image localization):** localize only `http(s)` image URLs in
  the returned Markdown, bounded by `--max-images`/`--max-bytes` — proposed: yes.

### 15.11. As-built deltas (TASK 023, 2026-06-23)

Shipped (7 beads + `/vdd-multi`), additive to §15.1–10:

- **`engine:` frontmatter** added to `emit._frontmatter` (real tier, AC-R6) — the spec's
  R6(b) field, completed after live dogfood.
- **`_url_tiers(engine, allow_chrome=True)`** — search-result fetches pass `allow_chrome=False`
  (drop the chrome tier) unless the user explicitly chose `--engine chrome`: an
  attacker-influenceable search URL must not reach the un-network-hardened Chrome tier (S-1).
- **Trust-markdown HTML fallback** — `_LOOKS_HTML` (broad block-tag/doctype/xml sniff): if a
  reader returns HTML despite `--remote-format markdown`, route it through the normal pipeline
  instead of emitting raw HTML (L-2).
- **`_search_result_urls(raw, limit)`** — bounded + deduped extraction (stops at `limit`); no
  unbounded junk list from a large/HTML body (P-3/L-4).
- **Request-URL encoding by base shape** — a `?url=`-ending reader base encodes the target as
  a single query value (`quote(safe="")`); the `/`-ending Jina convention keeps it readable
  (S-3). `--target-selector` is CR/LF-guarded (L-3).
- **Search emits one note per result** (`_convert_one(query=…)` suppresses the reader variant).
- **Honest-scope (deferred, KNOWN_ISSUES HTML2MD-9):** no aggregate `--deadline` (bounded but
  uncapped serial ladder latency, P-1/P-2); `--max-bytes` unbounded default (P-4). The Chrome
  engine's lack of a per-request SSRF gate is unchanged for an *explicit* `--engine chrome`
  (HTML2MD-4); search no longer exposes it (S-1 above).

---

## 16. TASK 024 — authenticated (login-gated) Chrome engine, server/Hermes-deployable

Living-document delta for **TASK 024** (`docs/TASK.md`). Adds **authenticated fetch** to the
Chrome tier, the **SSRF-hardening that must precede it**, a **server/Hermes deployment model**,
and a **Jina-key strategy**. All changes are html-**owned** (`acquire.py`, `cli.py`, new
`_cookies.py`/`_chrome_auth.py`, docs, tests) — no `diff -q`-gated master touched (§9 holds).
Chrome stays **soft-optional** (no new base dep).

### 16.1. Chrome SSRF hardening (prerequisite — R1)

Today only lite/remote call `_assert_public_http`; `_fetch_chrome_html` is a bare
`launch + goto` that follows redirects to any host. Attaching credentials to that is an exfil
vector, so **R1 lands with/before R2**. All guards are installed **before `page.goto`** and at
the **context level** (so popups/workers are covered, no first-request TOCTOU):
- `_assert_public_http(url)` **before** `page.goto`.
- A navigation guard re-checking `_host_is_public` on the **main-frame redirect chain** (refuse
  a redirect to a non-public host).
- **Off-target *public* redirect guard:** before snapshotting, assert the **final landed origin
  == the requested target's eTLD+1** — a public→public off-target redirect (`example.com` →
  `evil-public.com`) is refused, so a session is never carried to a different public site.
  (Cookie host-scoping itself is the **browser's** native cookie-domain matching for the
  storage_state/cookies paths; this guard adds the navigation-level control.)
- `context.route("**/*", …)` to **abort sub-resource + JS `fetch`/`sendBeacon` requests to
  non-public hosts** (best-effort; route catches all request types).
- **Honest-scope residuals:** (a) **DNS-rebinding TOCTOU** is inherited from the lite path (§10,
  resolve-then-connect) — unchanged; (b) `storage_state` **localStorage** is origin-restored and
  readable by any same-origin script the page loads (not further filtered); (c) not full beacon
  isolation. The egress-restricted-sandbox advice stands for fully-untrusted input.

### 16.2. Authenticated context (R2) — `_chrome_auth.py`

`_fetch_chrome_html(url)` → `_fetch_chrome_html(url, opts)`; `_tier_chrome` already has `opts`.
`_chrome_auth.py` resolves ONE auth source into context kwargs:

| Flag / env | Playwright call | Carries | Server-fit |
|---|---|---|---|
| `--chrome-storage-state PATH` / `HTML_CHROME_STORAGE_STATE` **(primary)** | `new_context(storage_state=PATH)` | cookies + localStorage + sessionStorage | ✅ portable, **read-only at runtime → concurrency-safe** |
| `--chrome-cookies-file PATH` / `…_COOKIES_FILE` | `new_context()` + `add_cookies([…])` (Netscape→dicts via hardened loader) | cookies only | ✅ read-only |
| `--chrome-user-data-dir DIR` / `…_USER_DATA_DIR` | `launch_persistent_context(user_data_dir=DIR, headless=True)` | full profile (self-refreshes, survives 2FA) | ⚠️ **mutable, single-concurrency — local only** |

Mutually-exclusive group. **Any auth flag sets the effective engine to `chrome`** (bypasses
lite/remote so the credential is never silently dropped by the ladder).

**Graceful degradation (R10 — user-required, non-regression invariant).** Auth is strictly
additive: with **no `--chrome-*` flag/env and no `JINA_API_KEY`**, behaviour is byte-for-byte
TASK 023 (the `auto` ladder, keyless fallback) — the default install + default invocation are
unchanged, no crash. A `--chrome-*` flag whose file is **missing/unreadable/malformed** → a
clean typed error (`BadInput`), not a traceback; **Playwright absent** + a `--chrome-*` flag →
`EngineNotInstalled` (exit 3) with remediation. `JINA_API_KEY` absent → keyless tier as today.

### 16.3. Session minting (R3) — the one interactive step

`html login URL [--save-state out.json]`: **headful** Chromium → user logs in by hand
(2FA ok) → `context.storage_state(path=out.json)` → `chmod 0600`. Only headful path; runtime is
always headless. Alternatives: `playwright codegen --save-storage`, browser `cookies.txt` export.

### 16.4. Scroll-to-load (R4)

`--chrome-scroll [--chrome-scroll-passes N]`: after `goto`, scroll to bottom N times awaiting
`networkidle`/settle, bounded by a **wall-clock budget**, then snapshot. Pulls lazy
replies/comments. Best-effort (deep threads may truncate — logged).

### 16.5. Remote / Hermes deployment model (R5)

The **`storage_state.json` is the unit of auth deployment**:
```
workstation (browser)          secret transport           Hermes server (headless)
  html login URL ─mint─▶  x.json (0600) ─deploy─▶  HTML_CHROME_STORAGE_STATE=/secrets/x.json
                                                     html … --engine chrome   (N concurrent)
```
- **Concurrency-safe:** state file is **read-only at runtime** → N parallel runs share it (no
  lock/corruption). Persistent-profile is mutable → single-concurrency, not server-recommended.
- **Stale-session detection** (X serves a *200* login wall, not a 401 → `_fetch_kind` alone
  misses it): a **best-effort, per-site login-wall heuristic** — signal class = {redirected to a
  `/login`-class URL · a known login-wall marker/needle · the `--target-selector` absent} →
  `FetchFailed kind=auth_required`, never returned as content → Hermes can alert/re-mint.
  Honest-scope: best-effort, tuned for X first; needles kept conservative + tested (a
  false-negative would emit a wall).
- **Rotation:** re-mint on a workstation → redeploy the secret. No auto-refresh (R9).
- **In-network synergy:** Hermes can run a **self-hosted Jina Reader** and point the TASK 023
  remote tier at it (`HTML_READER_URL=http://reader.internal/`) — no 3rd-party egress.

### 16.6. Jina-key strategy (R6)

`JINA_API_KEY` from **env/secret only** (never argv/logs); keyed = higher quota + reliability,
keyless = rate-limited fallback. **Matrix:** auth'd content → local chrome-auth (never ship a
live session to jina); anti-bot **non-auth** / server volume → keyed jina or a self-hosted
reader. Live-session `x-set-cookie` forwarding **deferred** (R9 — unverified + 3rd-party exfil).

### 16.7. Data-model & interface deltas

- **CLI:** `--chrome-storage-state` / `--chrome-cookies-file` / `--chrome-user-data-dir`
  (mutually-exclusive), `--chrome-scroll` / `--chrome-scroll-passes N`; new `login` subcommand.
- **Env:** `HTML_CHROME_STORAGE_STATE` / `_COOKIES_FILE` / `_USER_DATA_DIR`.
- **`_fetch_kind`** maps 401/407 → `auth_required`; add a **login-wall heuristic** for the chrome
  path (X serves a 200 login wall, not a 401) → `auth_required`.
- **Provenance/redaction:** `engine: chrome`; auth recorded only as a boolean in the trace —
  `_redact` extended so storage_state/cookie values never surface.

### 16.8. Security (R7)

Hardened loader: reject symlink, **reject BOTH group- and world-accessible modes** (`st_mode &
0o077` → error — *tighter* than transcript-fetcher's world-only check (`_cookies.py:84`); an
**intentional divergence** for the multi-tenant server threat model, flagged so a reviewer
doesn't "fix" it back), sanitized errors that never echo file contents. **Lift only the
file-hardening half** of `transcript-fetcher/_cookies.py` (`load_cookie_jar`); the
Netscape→Playwright-cookie-dict conversion for `add_cookies` is **new html-skill code** (the
urllib `_RestrictedRedirectHandler` is irrelevant to the Playwright transport). Copy is
html-owned, NOT gated — add a tracking note vs the source, don't silently fork. Secrets via
file/env only (never argv). **Cookie host-scoping** = the browser's native cookie-domain
matching (storage_state/cookies paths) **plus** the §16.1 final-origin gate — NOT a urllib
handler. Replay-only (no password/2FA automation). Full redaction everywhere.

### 16.9. Fork-free (R8)

`acquire.py`/`cli.py`/`_cookies.py`/`_chrome_auth.py` are html-owned, **absent** from the
G-1/G-2 gate. No master byte-change ⇒ gate silent, docx G-3 byte-identical. Chrome stays the
soft-optional extra ⇒ no base-dep change.

### 16.10. Atomic-chain skeleton (Planner handoff, for /vdd-plan)

| Bead | Scope (RTM) | Role |
|---|---|---|
| **024-01** | STUB: CLI flags + `login` subcommand surface (dispatch shape: a `login` verb handled in `main` before the flat parser, or `add_subparsers` — pick at planning) + `_chrome_auth`/`_cookies` skeletons + RED tests (SSRF private-redirect-block **on first request**, **off-target public-redirect block**, auth-context, stale-session→`auth_required`, cookie-scope, **R10 non-regression: no-auth = TASK-023 behaviour + missing-file→typed-error**) | STUB |
| **024-02** | **Chrome SSRF hardening** (R1): `_assert_public_http` + nav/redirect host gate + sub-resource route abort | LOGIC `tdd-strict` |
| **024-03** | Authenticated context (R2): storage_state / cookies.txt / persistent-profile + auth-implies-chrome | LOGIC |
| **024-04** | `login` mint helper (R3) + hardened `_cookies.py` + 0600 (R7) | LOGIC `tdd-strict` |
| **024-05** | Scroll-to-load (R4) + stale-session→`auth_required` (R5c) | LOGIC |
| **024-06** | Docs + Hermes deploy section + Jina-key matrix (R5/R6) + KNOWN_ISSUES + gates + dogfood (mint→render X Article) | INTEGRATION |

**MVP gate = 024-01…04** (hardened authenticated render). 05 + 06 complete it. Security beads
(02, 04) under `tdd-strict`; **no auto-commit**.

### 16.11. As-built deltas (TASK 024, 2026-06-23)

Shipped (6 beads + `/vdd-multi`), additive to §16.1–10. 177 tests green & **proven hermetic**
(suite passes with external DNS+TCP blocked); G-1/G-2/G-3 replication gate PASS; `validate_skill`
exit 0; no new base dependency. RTM R1–R10 all realized.

- **`login` verb-intercept** — dispatched in `main` *before* the flat argparser (a `login` first
  arg routes to `_login_main`), not `add_subparsers` (keeps the single-positional convert surface
  unchanged). `_login_render` mints `storage_state` under `umask(0o077)` so the file is **0600 from
  creation** — no post-write `chmod` race (INFO-1).
- **`_install_chrome_guards(context)`** — context-level `route` guard, installed **before** `goto`;
  the unused `target_reg` param was dropped (L-4). Fail-closed: a request whose host fails the
  public-IP gate is **aborted**, with a per-host `getaddrinfo` cache to avoid re-resolving.
- **Off-target public-redirect refusal** — after render, `_registrable(final_url)` ≠ target eTLD+1
  ⇒ `FetchFailed(kind=offsite_redirect)`. `www`↔apex is same-site (allowed); `_login_render`
  intentionally skips this (manual SSO to a different eTLD+1 is legitimate).
- **`--max-bytes` parity on the rendered body** — chrome `page.content()` is now length-checked
  (`FetchFailed kind=max_bytes`), closing the downstream-memory lever the lite tier already had
  (P-1). The cap is **post-render** — Chromium's in-render DOM memory stays uncapped (honest-scope).
- **`is_login_wall(html, final_url)`** — `opts` param dropped (was dead, L-2); 2 signals shipped
  (login-path final URL + `_WALL_MARKERS`/`_WALL_PAIRS` body markers). The R5c 3rd signal
  (target-selector-absent) is **deferred** — needs a DOM parse and a weak heuristic risks false
  positives (KNOWN_ISSUES HTML2MD-10).
- **`--chrome-* ⊥ --search`** — `_validate_usage` rejects the combo (Usage/exit 2): auth must not
  fan a human session over attacker-influenceable search-result URLs (L-1, defends S-1).
- **R10 graceful degradation** — with no keys / no session the ladder is byte-for-byte TASK-023
  behaviour; a `--chrome-*` flag pointing at a missing file fails fast as typed `BadInput` (not a
  late crash). `_fetch_chrome_html(url)` → `(url, opts)` signature change; 5 test fakes updated.
- **Test hermeticity** — the Playwright `_import_sync_playwright` seam + `_host_is_public` stub make
  the chrome/auth suite fully offline; verified under a blocked-egress firewall run.

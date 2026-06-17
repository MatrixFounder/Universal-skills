# ARCHITECTURE: `html2md` — universal Web/HTML → Markdown converter & Obsidian web-clipper (TASK 022)

> **License:** Proprietary, All Rights Reserved (derived work embedding
> proprietary `docx`/`pdf` code — see `CLAUDE.md` §3 + §9 below).
> **Runtime:** hybrid — Python orchestrator + Node converter subprocess
> (mirrors the existing `md2pdf.py` → `mmdc` pattern).
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
- **FC-5 `html2md.py` (NEW)** — CLI orchestrator + entrypoint. `_venv_
  bootstrap` prelude; threads flags; shells `node html2md_core.js` (HTML on
  stdin → Markdown on stdout); maps exceptions → exit codes / envelope.

### 2.2. Functional Components Diagram

```
                 ┌──────────────────────── html2md.py (FC-5, orchestrator) ──────────────────────┐
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
| `html2md.py`, `acquire.py`, `emit.py` | Python | NEW (html2md-owned) | — (skill-local) |
| `web_clean/{archives,reader_mode,preprocess,dom_utils,normalize_css}.py` | Python | **pdf** `html2pdf_lib/` | **pdf** (`diff -q` gated) |
| `web_clean/__init__.py` | Python | NEW (html2md-owned, thin) | — (NOT gated) |
| `html2md_core.js` | Node | **docx** `docx2md.js` | **docx** (`diff -q` gated) |
| `_errors.py`, `_venv_bootstrap.py` | Python | **docx** | **docx** (4→5-skill) |
| `package.json` (turndown, gfm), `requirements.txt`, `install.sh` | — | NEW | — (skill-local) |

### 3.3. Components Diagram (runtime boundary)

```
  ┌─ Python venv (.venv) ───────────────────────────────┐      ┌─ Node (node_modules) ─┐
  │ html2md.py ─ acquire.py ─ web_clean/* ─ emit.py      │ ───▶ │ html2md_core.js       │
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

### 5.1. `html2md.py` public CLI

```
html2md INPUT [OUTPUT_DIR]
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
# html2md.py spawns (NO shell; argv list; bounded):
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
| `web_clean/__init__.py` | html2md | NOT gated | html2md-authored thin re-export of clean symbols only |
| `_errors.py` | **docx** | 4→**5**-skill | add `html2md` to existing replication loop |
| `_venv_bootstrap.py` | **docx** | 4→**5**-skill | add `html2md` to existing replication loop |
| `preview.py`, `_soffice.py`, `office/`, `office_passwd.py` | docx | N/A | **not used** (html2md emits Markdown, not renderable office docs) |

**Why pdf-master (the exception):** the cleaning code physically originates in
`pdf/html2pdf_lib/`. Replicating from there keeps html2md in sync with future
pdf hardening. Re-pointing it to docx would invert reality and break sync.
Flagged loudly in CLAUDE.md anti-patterns so a reviewer never "corrects" it.

**Why carry whole (no trimming):** the weasyprint-specific functions in
`preprocess.py`/`normalize_css.py` are **inert regex with no heavy imports** —
dead *weight*, not dead *dependency*. Trimming makes `diff -q` impossible (no
gate can verify a subset stayed in sync) → silent fork on the next pdf change.
A few KB of unused code is the correct price for fork-freedom.

**Guards (gate at integration bead):**
- **G-1 `diff -q`:** silent between `docx↔html2md` core and `pdf↔html2md`
  `web_clean/*.py` (the 5 gated files), after `__pycache__` clean.
- **G-2 import smoke-test:** `weasyprint` and `playwright` NOT in
  `sys.modules` after importing the **real leaf entrypoints** `acquire.py`
  uses — `web_clean.archives` AND `web_clean.reader_mode` (which pull the
  whole closure `preprocess`→`dom_utils`+`normalize_css`) — not just the thin
  package root. Defends the `__init__.py` trap across the full import graph.
- **G-3 docx no-drift:** docx `test_e2e.sh` + `test_battery.py` round-trip
  byte-identical before/after the core extraction (AC-R3).
- **G-4 (R8, post-MVP):** CI `diff -q`/`diff -qr` step in
  `.github/workflows/office-skills.yml` covering both masters + `html2md` in
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
| **022-01** | Skeleton: `skills/html2md/` scaffold (`init_skill.py`), `scripts/` package, `_venv_bootstrap` prelude, **replicate** `web_clean/*` (pdf) + `html2md_core.js` (docx) + thin `web_clean/__init__.py`, `_errors.py`/`_venv_bootstrap.py` 4→5, import smoke-test (G-2), **RED** E2E/unit scaffolding (file/archive/url happy-paths, dual-output, `--no-reader`, `--no-download-images`, stdout, exit-3/6/10, `--json-errors`) | STUB + tests (Red) + replication |
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
  package `__init__.py` are NEVER replicated; html2md ships an owned thin
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
  `chrome_engine.py`'s fetch hardening as html2md-owned code (fetch semantics
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
  html2md-owned **`html2md_convert.js`** (NOT gated), which `require()`s the
  docx-mastered `html2md_core.buildTurndown()` (kept byte-identical) and adds web-page
  turndown rules the docx core doesn't need: **ARIA-role tables → GFM** (scoped to the
  own table; sibling-rowgroup headers), strip `<button>`/`role=button`(leaf)/
  `aria-label^="Copy"`, **collapse multi-line links to one line + drop icon/zero-width
  anchors**. docx2md.js still calls `buildTurndown()` directly (no wrapper) → unaffected.
- **FC-4 gains a post-turndown tidy.** New html2md-owned **`html2md/md_clean.py`**:
  merge empty ATX headings with their detached title, drop high-confidence standalone
  chrome lines, collapse blank runs. Applied in `cli.convert` to both variants.
- **CLI default output (§5.1 amended):** omitting `OUTPUT_DIR` (and `--stdout`) now
  writes to `./tmp/html2md_out/` (created **lazily** by `emit`); output names are
  collision-safe + idempotent via a hidden `html2md-source-id` marker.
- **Security hardening (§7 as-built):** SSRF per-redirect-hop public-IP gate +
  streaming `--max-bytes` cap; `<img>` reads confined to `base_dir` (CWE-22);
  **PDF/binary fetch guard** (`%PDF`/NUL → clean `FetchFailed`, no turndown stack
  overflow). Residuals in `docs/KNOWN_ISSUES.md` §HTML2MD.
- **Battery (G-5):** `tests/{capture_signatures.py, battery_signatures.json,
  test_battery.py}` + committed `examples/regression/gitbook-style-doc.html`. Asserts
  `empty_headings==0`, `stray_chrome==0`, required needles, metric tolerance bands.
  Wired into `tests/test_e2e.sh` (alongside the G-1/G-2 `diff -q` gate).

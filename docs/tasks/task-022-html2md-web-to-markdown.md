# TASK 022 — `html2md`: universal Web/HTML → Markdown converter & Obsidian web-clipper

**Status:** ✅ SHIPPED (as-built) — implemented via `/vdd-develop-all` (7 beads
022-01…07), then conversion-quality refinements + a regression battery, all
`/vdd-multi`-reviewed. **NOT committed.** See §7 "As-built" for what shipped beyond
this spec.
**Skill:** `html2md` (NEW standalone skill, **Proprietary, All Rights
Reserved**) — it carries byte-identical copies of proprietary `docx`/`pdf`
code (turndown core, `web_clean/` cluster, `_errors.py`, `_venv_bootstrap.py`),
so as a derived work it **joins the office-proprietary set**; it gets its own
per-skill `LICENSE`/`NOTICE` mirroring the office four and re-points
`THIRD_PARTY_NOTICES.md`. It is NOT Apache-2.0.
**Predecessor:** TASK 021 (`pptx2md --ocr-denoise`) — DONE & archived
(`docs/tasks/task-021-pptx2md-ocr-denoise.md`).
**Mode:** VDD (Verification-Driven Development).
**Provenance:** Architecture locked over a 3-agent code audit + adversarial
"no-fork" verification (see `docs/office-skills-backlog.md` §2 «html2md» and
`CLAUDE.md` §2 «Future skill html2md — TWO-master replication»).

---

## 0. Meta Information

- **Task ID:** 022
- **Slug:** `html2md-web-to-markdown`
- **Context:** Two driver use-cases: (1) a **web-clipper** that turns a page
  into a self-contained Obsidian note; (2) a **universal workflow step** any
  agent can call to get clean Markdown from arbitrary HTML/URL input. The
  skill is fork-free by reusing battle-tested code from `docx` (the turndown
  HTML→MD core) and `pdf` (the `html2pdf_lib` HTML-cleaning cluster).
- **Runtime:** hybrid — Python orchestrator (acquire / clean / emit) shelling
  to a Node converter (`html2md_core.js`), mirroring the existing
  `md2pdf.py` → `mmdc` pattern.

---

## 1. Problem Description

There is **no standalone HTML→Markdown converter** in the repo. The only
"proper" conversion is buried inside `docx2md.js` as an intermediate
(`mammoth` docx→HTML → `turndown`+gfm HTML→Markdown). Separately, the most
mature **HTML-cleaning** machinery lives in `pdf`'s `html2pdf_lib/`
(archive extraction, reader-mode, SPA-chrome stripping) — but **both skills
are deliberately offline**: weasyprint's `_offline_url_fetcher` raises on
`http(s)`, and the Chrome engine blocks remote routes. So:

1. No skill can fetch a **live URL** — the core of a "web scraper".
2. The proven turndown core is not reusable without copy-pasting from
   `docx2md.js`.
3. The proven cleaning cluster is pdf-internal and risks **forking** if
   copied naively (and could drag `weasyprint` along if copied as a package).

`html2md` closes all three **without forking**, by adding only the missing
acquisition + Obsidian-emit layers and reusing the rest under a documented
two-master replication topology.

---

## 2. Requirements Traceability Matrix (RTM)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R1** | **Input acquisition** — accept URL or downloaded archive/file | ✅ | (a) live-URL fetch via `httpx` (transport) + **`trafilatura`** as the MVP lite article+metadata extractor (chosen over `readability-lxml` because it also yields title/date/author for R4 frontmatter; `readability-lxml` is a documented fallback only); (b) auto-fallback to Playwright/Chrome for JS/SPA pages (soft-optional dep); (c) `.webarchive`/`.mhtml` via replicated `web_clean/archives.py` (subframe-aware, pdf-8); (d) local `.html`/`.htm` direct read; (e) format dispatch by extension + magic-byte (`bplist00`) |
| **R2** | **HTML cleaning** — strip chrome, extract article | ✅ | (a) reader-mode article extraction + universal SPA-chrome heuristic (`web_clean/reader_mode.py`, pdf-9); (b) regex preprocess passes — chrome/ad/icon/comment strip (`web_clean/preprocess.py`); (c) DOM helpers (`web_clean/dom_utils.py`); (d) `--reader-mode` toggle vs whole-page |
| **R3** | **HTML→Markdown core** — GFM-correct conversion | ✅ | (a) `html2md_core.js` = verbatim turndown + `turndown-plugin-gfm` lift from `docx2md.js`; (b) tables: rowspan/colspan → flat grid; (c) atx headings + fenced code; (d) h1–h6→`<strong>` inside table cells; (e) domino DOM (single real parse) |
| **R4** | **Obsidian emit** — frontmatter + attachments | ✅ | (a) YAML frontmatter (source URL, title, date, author, tags); (b) `--download-images` / `--no-download-images` (**default ON**) → `_attachments/` with sha1-dedup + relative links; (c) `--attachments-dir _attachments` (overridable); (d) **dual-output by default** — emits BOTH `<slug>.md` (whole-page) and `<slug>.reader.md` (reader-extracted) per the `feedback_pdf_dual_render` convention, suppressed with `--no-reader`; both share ONE `_attachments/` |
| **R5** | **Agent-step contract** — machine-usable | ✅ | (a) Markdown to stdout; (b) `--json-errors` envelope (`{v:1,error,code,type?}`, replicated `_errors.py`); (c) deterministic exit codes; (d) `--no-download-images` for raw-markdown agent use |
| **R6** | **Fork-free replication** — two-master topology | ✅ | (a) `html2md_core.js` master=docx, `diff -q` gated; (b) `web_clean/{archives,reader_mode,preprocess,dom_utils,normalize_css}.py` master=pdf, byte-identical, EXCLUDE `render.py`/`chrome_engine.py`/`__init__.py`; (c) html2md-own thin `web_clean/__init__.py`; (d) import smoke-test: `weasyprint`/`playwright` NOT in `sys.modules`; (e) `_errors.py`+`_venv_bootstrap.py` 4→5-skill |
| **R7** | **Skill packaging & isolation** | ✅ | (a) `SKILL.md` (Gold-Standard, triggers); (b) `install.sh` (venv + node_modules + `--with-chrome`); (c) `validate_skill.py` exit 0; (d) installable in isolation as `.skill` (no sister-skill runtime dep) |
| **R8** | **CI fork-gate** | ⬜ post-MVP | (a) `diff -q`/`diff -qr` step in `office-skills.yml` for docx→core + pdf→cluster; (b) `html2md` added to skill matrix; (c) fail build on byte-drift |

---

## 3. Use Cases

### UC-1 — Clip a live web article into Obsidian (primary)
- **Actor:** User / agent with a vault.
- **Preconditions:** Network reachable; `html2md` installed.
- **Main scenario:** Input is a URL → `acquire.py` fetches via lite engine →
  `html2md_core.js` converts → `emit.py` writes `<slug>.md` (whole-page) AND
  `<slug>.reader.md` (reader-extracted, default) with YAML frontmatter and
  downloads images to a shared `_attachments/` (relative links).
- **Alternative:** Page is a JS/SPA shell with empty lite-fetch body →
  `acquire.py` auto-falls back to Chrome → same downstream.
- **Postconditions:** Two self-contained Obsidian notes (whole-page + reader)
  sharing one deduped `_attachments/`; `--no-reader` collapses to one.
- **Acceptance:** Both `.md` files open in Obsidian with rendered images from
  `_attachments/`; frontmatter `source:` equals the input URL; with
  `--no-reader` only `<slug>.md` is written.

### UC-2 — Convert a downloaded archive (offline)
- **Actor:** User with a saved `.webarchive`/`.mhtml`/`.html`.
- **Preconditions:** `html2md` installed; input file present locally. No
  network required.
- **Main scenario:** Format dispatch → `web_clean/archives.py` extracts main
  (or chosen subframe) HTML + sub-resource images → clean → convert → emit.
- **Postconditions:** Markdown (+ reader by default) written; all images
  resolved from the archive into `_attachments/`; no network egress occurred.
- **Acceptance:** No network calls made (verified by offline harness);
  webarchive images resolve locally; `--archive-frame` selection honored.

### UC-3 — Universal agent workflow step
- **Actor:** Orchestrating agent.
- **Preconditions:** `html2md` installed; input is a URL, archive, or HTML
  file passed by the agent.
- **Main scenario:** Agent calls with `--no-download-images --json-errors`
  (and typically `--no-reader`); Markdown is returned on stdout, remote image
  URLs left intact; any failure is a single-line JSON envelope.
- **Postconditions:** No attachments downloaded, no reader artifact written;
  Markdown consumed from stdout by the calling workflow.
- **Acceptance:** On success exit 0 + Markdown on stdout, no files written
  outside the requested output; on failure exit ≠ 0 + `{v:1,...}` on stderr.

### UC-4 — JS/SPA-heavy page (high-fidelity)
- **Actor:** User clipping a hydrated SPA (CRM/portal).
- **Preconditions:** Chrome extra installed (`install.sh --with-chrome` /
  `requirements-chrome.txt`); network reachable.
- **Main scenario:** `--engine chrome` (or `auto`) renders via Playwright;
  SPA-chrome heuristic (`web_clean/reader_mode.py`) strips nav/aside/banner;
  content extracted → convert → emit.
- **Postconditions:** Markdown reflecting the hydrated DOM is written; nav/
  sidebar chrome excluded.
- **Acceptance:** Article text present; nav/sidebar needles absent; if the
  Chrome dep is missing the tool exits ≠ 0 with a graceful
  `EngineNotInstalled` envelope (no traceback).

---

## 4. Acceptance Criteria (binary)

1. **AC-R1:** Given a static-article URL, the tool produces non-empty
   Markdown whose plain text contains the article's title and ≥1 body
   paragraph; given a `.webarchive`, it produces equivalent output with **zero
   network calls** (verified by an offline test harness).
2. **AC-R2 (reader cleaning):** On a known SPA fixture (e.g. the pdf-9
   `elma365`/`ya_browser`-class fixture) with reader extraction on, the
   `<slug>.reader.md` plain text **contains** the article-body needle and
   **excludes** the nav/sidebar needle (needle-based, mirroring the existing
   pdf-9 battery).
3. **AC-R3 (no output drift):** `docx2md.js` round-trip
   (`test_e2e.sh` + `test_battery.py`) produces **byte-identical** Markdown
   before and after `html2md_core.js` extraction.
4. **AC-R4:** With `--download-images`, every `<img>` that resolves becomes a
   `![](_attachments/<sha1>.<ext>)` link and the file exists; identical bytes
   across regular+reader outputs map to ONE file. With `--no-download-images`,
   remote `https://` URLs are preserved verbatim. **By default both
   `<slug>.md` and `<slug>.reader.md` are emitted; `--no-reader` suppresses
   the reader artifact** (and only then is a single `.md` written).
5. **AC-R5:** `--json-errors` failures emit exactly `{v:1,error,code,type?}`
   on a single line; success writes Markdown to stdout/`OUTPUT.md` only.
6. **AC-R6 (fork-free):** `diff -q` is silent between docx↔html2md core and
   pdf↔html2md `web_clean/*.py` (excluding the three weasyprint-bearing
   files); the import smoke-test asserts `weasyprint`/`playwright` absent from
   `sys.modules` after importing `web_clean`.
7. **AC-R7:** `python3 .claude/skills/skill-creator/scripts/validate_skill.py
   skills/html2md` exits 0; the packaged `.skill` runs with no sibling-skill
   present.

---

## 5. Replication / fork-free constraints (authoritative pointer)

This task MUST honor `CLAUDE.md` §2 «Future skill html2md — TWO-master
replication». Summary: **master=docx** for `html2md_core.js`,
`_errors.py`, `_venv_bootstrap.py`; **master=pdf** for the `web_clean/`
cluster (the documented exception to "docx is always master"); NEVER copy
`render.py`/`chrome_engine.py`/`__init__.py`; carry cleaning modules WHOLE
(no trimming); ship an html2md-own thin `web_clean/__init__.py`.

**Terminology guard (gated replication ≠ owned fork):** "NEVER copy
`chrome_engine.py`" means it is NOT a `diff -q`-gated replication unit — it
must not appear in `web_clean/` under the byte-identity gate. That does NOT
forbid `acquire.py` from being an html2md-**owned**, un-gated new file that
re-implements or adapts the Chrome-fetch hardening pattern (see Q7). Gated
replication keeps masters in sync; an owned fork is free-standing html2md code
the gate never touches.

---

## 6. Open Questions

- **Q1 (RESOLVED):** Fetch engine = lite (`httpx`+`trafilatura`) default with
  auto Chrome fallback. *(user 2026-06-17)*
- **Q2 (RESOLVED):** Image download = flag-controlled, **default ON**.
  *(user 2026-06-17)*
- **Q3 (RESOLVED):** Attachments folder = `_attachments`. *(user 2026-06-17)*
- **Q4 (RESOLVED):** Obsidian depth = frontmatter + local images, standalone
  (no hard dependency on the wiki framework). *(user 2026-06-17)*
- **Q5 (RESOLVED):** Dual-output is a **default second artifact** — emit both
  `<slug>.md` and `<slug>.reader.md`, suppress with `--no-reader` (per the
  `feedback_pdf_dual_render` convention). R4(d), AC-R4, and UC-1 are
  aligned to this. *(decided 2026-06-17, task-review 🔴-1)*
- **Q6 (non-blocking):** Frontmatter `tags:` — auto-derive (from `<meta
  keywords>`/OpenGraph) or leave empty for the user? Proposed: populate
  `source/title/date/author` automatically (trafilatura yields these), leave
  `tags: []` for the user.
- **Q7 (RESOLVED):** `acquire.py` Chrome dep — **copy-as-new** (html2md-owned,
  un-gated file adapting `chrome_engine.py`'s fetch hardening), NOT a gated
  replication unit. See §5 terminology guard. Fetch semantics differ from
  pdf's render-only `goto`. *(decided 2026-06-17, task-review 🟢-5)*

---

## 7. As-built (post-implementation, 2026-06-17)

Shipped via `/vdd-develop-all` (beads 022-01…07), then hardened by real-corpus
dogfooding + two `/vdd-multi` review rounds. Beyond the original §2 RTM:

- **`html2md_convert.js` (NEW, html2md-owned, not gated).** A turndown wrapper over
  the docx-mastered `html2md_core.buildTurndown()` (the core stays byte-identical).
  Adds web-page rules the docx core doesn't need: ARIA-role tables
  (`role="table/row/columnheader/cell"`, incl. GitBook's sibling-rowgroup headers) →
  GFM; strip `<button>` / `role=button`(leaf) / `aria-label^="Copy"`; **collapse
  multi-line links to one line + drop icon/zero-width-only anchors**. The Node bridge
  (`core_bridge.py`) spawns THIS file.
- **`html2md/md_clean.py` (NEW, html2md-owned).** Post-turndown tidy: merge empty ATX
  headings with their detached title; drop high-confidence standalone chrome lines
  (Copy / Search… / Ask AI / feedback / AI-widget); collapse blank runs. Conservative
  (no generic single words → no content deletion).
- **Default output `./tmp/html2md_out/`** (was stdout); created lazily by `emit` so a
  failed run leaves no empty dir. Collision-safe **idempotent** output names via an
  invisible `html2md-source-id` marker.
- **Security hardening** (from the adversarial roasts): SSRF per-hop public-IP gate +
  streaming `--max-bytes` cap; `<img>` reads confined to `base_dir` (CWE-22);
  **PDF/binary fetch guard** — a `%PDF`/NUL payload fails cleanly (`FetchFailed
  kind=pdf/binary`) instead of overflowing the turndown stack; YAML/pipe escaping.
- **Regression battery (R8 satisfied early):** `tests/capture_signatures.py` +
  `tests/battery_signatures.json` + `tests/test_battery.py` + committed
  `examples/regression/gitbook-style-doc.html`. Invariants: `empty_headings == 0`,
  `stray_chrome == 0`, required needles, metric tolerance bands.
- **Verification:** ~63 unit + 5 battery tests; `tests/test_e2e.sh` runs the suite +
  the **G-1/G-2 `diff -q` replication gate**; docx **G-3 byte-identical to HEAD**;
  `validate_skill.py` ×5 exit 0.
- **Honest scope (deferred):** see `docs/KNOWN_ISSUES.md` §HTML2MD — anti-scraper
  403 sites, PDFs (→ pdf skill), data-grid SPAs (e.g. TradingView), DNS-rebinding
  TOCTOU, un-hardened Chrome engine, slug-collision `-N` suffix, empty-heading
  re-leveling.

# HTML / web archive → `.pdf` (`html2pdf.py`)

Parallel to `md2pdf.py` for inputs that arrive as HTML rather than
Markdown — Confluence / CMS / docs-platform exports, browser-saved
news / blog pages, BI dashboards. Built on the same `weasyprint`
renderer so output styling matches `md2pdf` (DEFAULT_CSS typography,
page-size constants, `@page` margins).

## Supported input formats

| Extension | Source | What's recovered |
|---|---|---|
| `.html` / `.htm` | Plain HTML or Chrome "Save Page As, Webpage Complete" | Inline images via the `<page>_files/` sibling directory (relative paths). |
| `.webarchive` | Safari "Save As, Web Archive" (Apple binary plist) | Main HTML pulled from `WebMainResource`; image / CSS / font sub-resources extracted to a temp dir; URLs (full + path-only) mapped to local paths. |
| `.mhtml` / `.mht` | Chrome "Save Page As, Webpage Single File" / IE / Outlook | MIME multipart/related parsed; main `text/html` part decoded (quoted-printable / base64); sub-resources extracted to a temp dir; URLs mapped via `Content-Location`. |

## Validated platforms

End-to-end fixtures (34 PDFs across regular + reader-mode):

| Platform | Coverage |
|---|---|
| **Fern** | OpenRouter docs (table-based shiki code blocks, callouts) |
| **Mintlify** | Anthropic Claude Code (JetBrains plugin), Discord developer docs, Berachain Incentive Marketplace |
| **GitBook** | Hyperliquid docs (ARIA-role tables, REST API field schemas) |
| **Confluence** | Atlassian wiki pages (drawio inline SVG, tablesorter `<th>` headers, anchor-link icons, version-history tables) |
| **Хабр** | Article + ad-laden landing |
| **vc.ru** | SPA articles with reaction / share / comment widgets |
| **mobile-review.com** | `<main>`-wrapping-everything layouts |
| **Generic blogs** | WordPress, custom themes |
| **Books** | "What is Intelligence" (53 MB webarchive, 31 MB PDF output) |

## CLI

```bash
python3 scripts/html2pdf.py \
    <input.html|.htm|.webarchive|.mhtml|.mht> \
    <output.pdf> \
    [--page-size letter|a4|legal] \
    [--css EXTRA.css] \
    [--base-url DIR] \
    [--no-default-css] \
    [--reader-mode] \
    [--timeout SECONDS] \
    [--json-errors]
```

Flag semantics:

- **`--page-size`** — letter (default), a4, or legal. Maps to weasyprint's `@page { size: ... }`.
- **`--css EXTRA.css`** — appended after the bundled stylesheet so user CSS overrides defaults.
- **`--base-url DIR`** — only honoured for plain `.html`/`.htm`; archives override with their extracted temp dir.
- **`--no-default-css`** — skip the bundled stylesheet (BI dashboards, branded reports that ship full styling). The structural `_NORMALIZE_CSS` is always injected — it fixes weasyprint layout bugs, not visual styling.
- **`--reader-mode`** — extract only the article body (Safari Reader View parity). See § Reader mode.
- **`--timeout N`** — render-deadline watchdog in seconds (default 180; `$HTML2PDF_TIMEOUT` env overrides; `0` disables). On expiry: exit 1 with `RenderTimeout` envelope.
- **`--json-errors`** — emit failures as a single-line JSON envelope on stderr (`{v, error, code, type, details?}`) matching the cross-5 schema used by the other office skills.

Same-path I/O (input and output resolve to the same file, including via symlink) → exit 6 / `SelfOverwriteRefused`.

## Universal preprocessing pipeline

Applied **unconditionally** in both regular and reader modes — these are weasyprint-compatibility fixes, not optional cleanups. Order matters; pipeline runs in `_preprocess_html`:

| Step | Function | Purpose |
|---|---|---|
| 1 | `_fix_light_dark` | Replace CSS `light-dark(L, D)` with `L`. weasyprint doesn't implement CSS Color L5; without this every use renders transparent / black. Linear scan with paren-depth tracking handles nested calls like `light-dark(rgb(0,0,0), var(--c, #1d2125))`. |
| 2 | `_strip_external_stylesheets` | Drop all `<link rel="stylesheet">` and `<link rel="preload">`. Site CSS is the leading cause of weasyprint rendering bugs (Хабр content-drop, vc.ru CPU loops, font CDN-subset glyph mismatches). Renders rely on bundled DEFAULT_CSS + `_NORMALIZE_CSS` + inline `<style>` blocks (which stay). |
| 3 | `_strip_all_fontfaces_in_styles` | Remove `@font-face` blocks from inline `<style>`. Web fonts served from CDN are subset with remapped glyph indices that don't match locally-captured woff2 files; falls back to system fonts (Helvetica/Arial). |
| 4 | `_strip_interactive_chrome` | UNWRAP `<button>` (preserves Confluence `<th>`-button-wrapped column titles; iterative until stable to handle nested buttons). REMOVE `<video>`/`<audio>`/`<iframe>` (always render as grey blocks in PDF). |
| 5 | `_strip_icon_svgs` | Drop UI icons (anchor link markers, copy-code overlays, callout glyphs). Detection signals: `aria-hidden="true"` (W3C decorative), FontAwesome `prefix=fa*`, all declared numeric `width`/`height` ≤ 64 px, Tailwind `h-N`/`w-N`/`size-N` class for N ≤ 16, inline `style:width/height ≤ 64px`, viewBox max-dim ≤ 64 (final fallback). Self-closing `<svg .../>` handled separately. Real diagrams (drawio, mermaid, ≥ 100 px each side) survive. |
| 6 | `_strip_empty_anchor_links` | Drop `<a href="#anchor">` whose body is empty after icon strip. Two-stage scan (no O(n²) backtracking) — runs in 3.4 ms on a 5000-anchor TOC. |
| 7 | `_flatten_table_code_blocks` | Convert Fern/Mintlify/Docusaurus syntax-highlighting tables (`<pre><table><tr class="code-block-line">`) to plain `<pre><code>line1\nline2…</code></pre>`. weasyprint mishandles `<table>` inside `<pre>` when paginating — subsequent block siblings interleave with mid-table rows. Output is monochrome (shiki/prism `<span style=color>` runs are stripped). |
| 8 | `_strip_universal_ads` | Remove ad-network wrappers by class-substring match: `adfox`, `googletag`, `gpt-ad`, `taboola`, `outbrain`, `sponsor-mark`, `tm-banner`, `header-banner`, etc. Conservative — bare `banner` excluded (would over-strip `.user-banner`). |
| 9 | `_fo_to_svg_text` | Convert drawio `<foreignObject>` text labels to SVG `<text>` elements. weasyprint silently discards foreignObject content. Drawio's flex encoding (`margin-left` = LEFT EDGE, x-anchor derived; `padding-top` = absolute y-centre) is decoded; word-wrap splits long single-span labels into `<tspan>` rows. |
| 10 | `_fix_svg_viewport` | Synthesise viewBox for drawio Confluence SVGs that ship as `style="width:100%;height:100%;min-width:Wpx;min-height:Hpx"` without an explicit `viewBox`. Expands by 5 % to absorb drawio's right/bottom-edge overshoot. Skipped for SVGs ≤ 200 px (icons). |

Then `_NORMALIZE_CSS` is injected into `<head>` (or before `<body>`).

## `_NORMALIZE_CSS` rules

CSS injected unconditionally to bypass site-CSS quirks weasyprint can't handle:

1. **Body / overflow reset** — SPA pages cap body height to `100vh` with `overflow:clip`, making weasyprint see only one page; reset to `height:auto; min-height:0; overflow:visible`.
2. **Diagram SVG scaling** — `.drawio-macro` and `svg[viewBox]` get `min-width:0; max-width:100%; height:auto; overflow:visible`.
3. **Site chrome strip** — explicit class-token selectors hide `.aui-header`, `#sidebar`, `.tm-page__sidebar`, `.aside--left`, header/nav/sidebar of common platforms. Avoids `[class*=…]` wildcards that would over-strip BEM modifiers.
4. **`position:fixed/sticky` reset** to `static` — breadcrumb rows / Confluence header rows that aren't actually navigation but use fixed positioning.
5. **Multi-column collapse** — vc.ru / Habr `<.entry > .content>` flex rows (author card + body) collapse to single-column block flow.
6. **Image / video safety** — `max-width:100%; height:auto` on `img, video, canvas`.
7. **Markdown-preview typography** — `<pre>`/`<code>`/`<blockquote>` get GitHub-style typography (light grey background, rounded border, monospace, `pre-wrap` line wrapping for long source lines).
8. **ARIA-role tables** — `[role="table"]` / `[role="row"]` / `[role="cell"]` etc. render as a real CSS `display:table` (GitBook builds tables out of divs; without this the cells collapse to vertical block flow).
9. **Anchor / heading-link button hide** — `.copy-heading-link-container`, `.headerlink`, `a.anchor`, `h1 button`, etc. get `display:none`.

## Reader mode (`--reader-mode`)

Extracts the main article body and renders with only the bundled CSS — Safari Reader View parity.

### Article-root candidate list

Tiered by per-row `min_text` threshold:

| Tier | Selector | min_text | Why |
|---|---|---|---|
| High-confidence | `id="main-content"` | 1 | Confluence convention; diagram-heavy KB pages legitimately have <500 chars. |
| High-confidence | `class="wiki-content"` | 1 | Confluence (legacy + current). |
| High-confidence | `id="content"` | 1 | Generic CMS root. |
| CMS / blog | `class="entry"` | 500 | vc.ru article wrapper; min-text filters archive-page excerpts. |
| CMS / blog | `class="post-content"` / `article-content` / `main-content` | 500 | WordPress / generic blogs. |
| CMS / blog | `<div class="article">` | 500 | Some custom themes. |
| Generic | `<article>` | 500 | HTML5; false positives common (sites use `<article>` for comments, related items). |
| Generic | `[role="main"]` | 500 | ARIA. |

Within each row: **longest qualifying match wins** — handles archive pages with multiple `.entry` divs (post body is longer than excerpts) and Disqus comment threads (post body is longer than any individual comment article).

### Bare `<main>` body-ratio guard

Bare `<main>` is **deliberately omitted** from the candidate list above. It's tried separately as a final fallback, with the constraint:

```
main_text_length / original_body_text_length < 0.95
```

Calibrated empirically: mobile-review's article-only `<main>` is ~89 % of body; chrome-wrapping `<main>` on tested SPA blogs sits at 96-99 %. Threshold rejects the latter (giant 13-page social-share icon sidebar). HTML5 forbids multiple `<main>` per document, but real pages violate this — we prefer the FIRST `<main>` satisfying the guard.

### Reader-mode-only widget strip

Before candidate scanning, `_strip_reader_widgets` removes class-substring matches of:

- Recommendation widgets: `rotator`, `recommend`, `related-post`, `related-article`
- Comment threads: `comments`, `discussion-list`, `replies-list`
- Post-footer meta: `post-meta`, `post-tags`, `share-button`, `subscribe-block`, `newsletter`
- vc.ru-style engagement: `reaction`, `floating-bar`, `content-footer`, `entry-footer`
- Ads: `ad-banner`, `ad-block`, `advert`, `sponsor-block`, `promo-block`, `ya-ai`
- Cookie / GDPR: `cookie-banner`, `cookie-consent`, `gdpr-`

vc.ru's `<div class="entry">` contains the article PLUS these widgets as siblings; without the strip, reader-mode picks `.entry` correctly but the resulting PDF has 3-4× the legitimate text plus tail emoji counters. **Honest scope**: substring matching can over-strip on niche articles where the topic literally mentions a keyword (e.g. a chemistry article with `<figure class="reaction-diagram">`). Reader-mode is opt-in degraded view; pixel-perfect users should use default mode.

### Reader-mode head sanitisation

After extraction, the original `<head>` is preserved (for charset/lang) but `<link>`, `<script>`, AND `<style>` blocks are stripped. The PDF renders with only the bundled DEFAULT_CSS and `_NORMALIZE_CSS` — clean, consistent typography free of site-specific layout rules. Inline `<style>` blocks INSIDE the extracted body are also stripped (Confluence's tablesorter ships grey-pill styling for `<th>` cells via inline `<style>`; without removing it, table headers render as visible grey rounded rectangles).

## Render-time hardening

### Offline URL fetcher

`_offline_url_fetcher` refuses every `http(s)://` URL with `ValueError`. weasyprint catches the error, logs a "Failed to load X" warning, and continues rendering with whatever local resources are available. Without this, weasyprint's default fetcher uses urllib's blocking call with **no timeout** — single page with dozens of CDN font/image references can hang for 10+ minutes per stalled request.

`file://` and `data:` URIs pass through to weasyprint's default fetcher.

### SIGALRM watchdog (`--timeout`)

POSIX-only signal-alarm fallback for pathological inputs. Default 180 s; override via `--timeout` flag or `$HTML2PDF_TIMEOUT` env; `0` disables.

**Honest scope** — best-effort, NOT a hard guarantee:

- SIGALRM interrupts blocking syscalls and fires between Python bytecodes; works for pure-Python loops and network reads.
- BUT cairo (PDF backend) and lxml (HTML parser) hold the GIL inside their C extension calls. SIGALRM is queued and delivered only when control returns to Python. A pathological cairo layout that stays in C code for minutes won't be interrupted until the C call completes (we observed 6+ hour stuck PIDs on vc.ru SPA pages before adding `_strip_external_stylesheets`).
- The watchdog is the LAST line of defence; the primary fix is the site-CSS strip which neutralises most pathological layouts before render starts.

Wraps the **full** `convert()` body — reader extraction, preprocessing, AND render — so adversarial regex-heavy preprocessing is also bounded.

Non-main-thread (web-server / multiprocessing wrappers): `signal.signal()` raises ValueError. Caught and degraded gracefully — pipeline runs uncapped but doesn't crash.

## Honest scope (limitations)

- **Code-block syntax highlighting is monochrome** in flattened table-rendered code blocks (Fern / Mintlify / Docusaurus). Trade-off for content completeness: weasyprint's `<table>`-inside-`<pre>` pagination bug means we either flatten and lose colour, or keep colour and risk content cut-off.
- **JavaScript is not executed**. Pages that lazy-load content via React/Vue won't have that content unless the `.webarchive` captured the rendered DOM. Хабр's article body, for example, IS captured by Safari in the webarchive; some other sites' bodies aren't.
- **External CSS is stripped**. Site-specific table/grid layouts, custom typography, and brand colours are lost. Use `--no-default-css --css brand.css` for branded reports that ship their own complete stylesheet.
- **`rowspan` / `colspan` work** (weasyprint native); ARIA-role tables get CSS `display:table` but don't honour `aria-colspan`/`aria-rowspan`.
- **drawio Tier-1** (headless Chrome) is NOT used in html2pdf — only weasyprint native rendering. The Tier-1/Tier-2 split exists in `html2docx.js`. weasyprint's drawio rendering uses the foreignObject-to-text conversion path described above.

## Module layout

- [scripts/html2pdf.py](../scripts/html2pdf.py) — thin CLI shim (~190 lines): argparse, format dispatch, error envelopes. Public contract.
- [scripts/html2pdf_lib/](../scripts/html2pdf_lib/) — internals, split by responsibility:
  - `normalize_css.py` — injected print-normalization stylesheet (data only)
  - `dom_utils.py` — depth-tracked HTML scanning helpers (`find_all_elements`, `text_length`, …)
  - `preprocess.py` — 11-step `preprocess_html()` pipeline (light-dark, font-face strip, draw.io SVG, icon/ad/chrome strip, table-code flatten, viewport fix)
  - `reader_mode.py` — `reader_mode_html()` with tiered `_READER_CANDIDATES` and `<main>` body-ratio guard
  - `archives.py` — `extract_mhtml` / `extract_webarchive` + URL rewrite
  - `render.py` — `convert()`, `RenderTimeout`, SIGALRM watchdog, `_offline_url_fetcher`
- Cross-skill deps unchanged: `_errors.py` (cross-skill envelope), `md2pdf.py` (DEFAULT_CSS / PAGE_SIZES reuse).

## Examples

Round-trip a Confluence page export:

```bash
python3 scripts/html2pdf.py confluence-page.html confluence-page.pdf
# → renders with site chrome stripped, drawio diagrams properly scaled,
#   anchor-link icons hidden, default markdown-preview typography
```

Convert a Mintlify docs webarchive in reader mode:

```bash
python3 scripts/html2pdf.py "JetBrains IDEs - Claude Code Docs.webarchive" \
    docs.pdf --reader-mode
# → strips sidebar nav + Tab.Switcher + footer; keeps article body with
#   proper heading hierarchy, bullet lists, code blocks
```

Convert a vc.ru article (with the universal CSS strip neutralising vc.ru's pathological layout CSS):

```bash
python3 scripts/html2pdf.py article.webarchive article.pdf --timeout 120
# → 2.4 MB → 244 KB; widget tail (emoji reactions, comments, recommend
#   carousel) stripped automatically
```

Branded BI dashboard export (preserve site styling):

```bash
python3 scripts/html2pdf.py dashboard.html dashboard.pdf \
    --no-default-css --css brand-overrides.css \
    --base-url /var/www/dashboard_assets
```

Force watchdog disabled for long-running rendering on a known-good 24 MB book webarchive:

```bash
HTML2PDF_TIMEOUT=0 python3 scripts/html2pdf.py book.webarchive book.pdf
```

## Regression coverage (VDD-iter-6)

The skill ships a 4-tier regression net designed to catch all bugs from
the recent preprocessing-pipeline iterations and to give a low-friction
workflow for adding new platforms without breaking existing behaviour.

### Tier 1 — Unit tests (`tests/test_preprocess.py`)

37 deterministic tests that import individual helpers from
`html2pdf_lib/` and pin down the contracts that survived the
adversarial-review iterations. Cover: self-closing `<svg/>` handling,
AND-rule aspect-ratio for icon detection, `text_length` script/style
strip, `get_attr` cross-attribute false-positive fix, nested `<button>`
unwrap, anchor-strip O(n×k) perf bound, code-table flatten false-
positive guard, drawio foreignObject (camel + lowercase), watchdog
wiring (zero-timeout, non-main-thread degrade, install/clear leak
guard), offline URL fetcher refusal of `http(s)://`. Run time < 1 s.

### Tier 2 — Synthetic micro-fixtures (`examples/regression/*.html`)

6 hand-crafted ~1-3 KB HTML files that exercise edge cases Tier 0
cannot deterministically reproduce: self-closing SVG, nested-button
unwrap, tall vertical content SVG (AND-rule), `<script>` blob in
`<article>` (text-length false positive), 5000-anchor TOC perf,
broken external stylesheet (offline_url_fetcher).

### Tier 3 — Real-platform structural slices (`tests/fixtures/platforms/*.html`)

6 hand-stripped ~3-8 KB slices from real `tmp/` originals. **Sentinels
are REAL strings** copied verbatim from the source platform, NOT
synthetic placeholders:

| Fixture | Source platform | Bug-canary needles |
|---|---|---|
| `mintlify-callout.html` | Anthropic Claude Code Docs | `Claude Code integrates with JetBrains IDEs`, `IntelliJ IDEA` |
| `fern-shiki-codeblock.html` | OpenRouter Quickstart | `openai/gpt-5.2`, `What is the meaning of life?` |
| `gitbook-api-table.html` | Hyperliquid API docs | `Retrieve mids for all coins`, `Content-Type`, `application/json` |
| `confluence-version-table.html` | ELMA365 wiki | `Управление версиями`, `V0.01`, `Демидова Татьяна` |
| `vcru-entry-tail.html` | vc.ru R&D article | `R&D – это не бэкстейдж`, `исследовательская функция` |
| `habr-banner-stack.html` | Хабр Garmin tracker | `Демон запускается локально` (the paragraph-4 drop bug-canary from commit 3857d6d) |

### Tier 0 — `tmp/` characterization battery (PRIMARY)

The 17 fixtures in the repo's `tmp/` directory (~250 MB total —
gitignored, kept on developer machines, not in CI). Each fixture
renders in BOTH regular AND reader modes; outputs are validated
against per-fixture entries in `tests/battery_signatures.json`:

* `min_pages` ≤ pdf-page-count ≤ `max_pages` (5 % tolerance + 1 page slack)
* `min_size_kb` ≤ pdf-file-size-kB ≤ `max_size_kb` (10 % tolerance)
* every `required_needles[i]` appears in `pdftotext` output (whitespace-normalised)
* none of `forbidden_needles[i]` appears (chrome-leakage detection;
  reader-mode only — chrome legitimately appears in regular mode)

The battery is the densest column in the coverage matrix because
real-platform interaction effects are the bug class the recent
iterations have been hitting.

### Adding a new platform fixture (5-min workflow)

```bash
# 1. Drop the new fixture into tmp/
cp ~/Downloads/notion-page.webarchive tmp/

# 2. Auto-capture page count + needles + size band into the JSON
cd skills/pdf/scripts
./.venv/bin/python tests/capture_signatures.py
# (only ADDs new fixtures by default; pass --refresh to regenerate
# baselines after intentional preprocessing changes)

# 3. Hand-add chrome strings to forbidden_needles for the new platform
# (look at pdftotext output of the regular-mode PDF; pick 2-3 chrome
# strings like "Skip to main content", "Search...", "© 2024 Acme")
$EDITOR tests/battery_signatures.json

# 4. Verify the baseline passes
./.venv/bin/python -m unittest tests.test_battery -v

# 5. Commit JSON delta — the .webarchive itself stays in tmp/
git add tests/battery_signatures.json
git commit -m "battery: add notion regression baseline"
```

### Tier 4 wiring (`tests/test_e2e.sh`)

Two added lines invoke `unittest tests.test_preprocess` and
`unittest tests.test_battery`. Battery tests skip gracefully (clear
"skipped" message, not failure) when `tmp/` is absent. Total counts
in the e2e summary: 74 on a clean checkout (no tmp/), ~150+ with
tmp/ populated.

### Honest scope

* `forbidden_needles` are reader-mode-only — chrome legitimately
  appears in regular-mode rendering; only reader mode promises
  chrome-stripping.
* The watchdog FIRING path (i.e. constructing an input that
  reliably hangs > N seconds) is not tested. Watchdog WIRING (signal
  install, zero-timeout, non-main-thread degrade) IS tested in
  Tier 1; the firing path is best-effort by documented design
  (cairo C calls hold the GIL).
* Synthetic-fixture overlap with Tier 0 is intentional: synthetics
  are deterministic in CI; Tier 0 is conditional on `tmp/` presence.
* Test-file imports the underscore-prefixed helpers from
  `html2pdf_lib.preprocess`. Those names are private by Python
  convention but PINNED by the regression tests as the stable
  testing API. Refactors that rename them must update
  `tests/test_preprocess.py` in lockstep.

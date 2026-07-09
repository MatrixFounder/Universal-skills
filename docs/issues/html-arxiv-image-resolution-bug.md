---
id: HTML2MD-11-BUG
type: known-issue
status: fixed
opened_at: 2026-07-09
resolved_at: 2026-07-09
resolved_by: TASK 027
category: correctness
severity: SEV-2
component: html
slug: html-arxiv-image-resolution-bug
related: html2md-11-rewritten-fetch-relative-img-base
---

# html skill — arXiv (and any rewritten-fetch) relative `<img>` srcs resolve against the wrong base → broken images

> Deep-dive root-cause write-up for [HTML2MD-11](./html2md-11-rewritten-fetch-relative-img-base.md).

- **Reported**: 2026-07-09 (real-vault dogfood: importing `https://arxiv.org/abs/2510.08369` via `wiki-import`, which calls the `html` skill with `--reader-only`)
- **Severity**: SEV-2 (silent data loss — the note/raw looks fine but carries **zero** real figures; envelope reports success)
- **Affected component**: `skills/html/scripts/html2md/acquire.py`
- **Status**: ✅ **RESOLVED** (TASK 027, 2026-07-09) — see the resolution note at the bottom.

> **Resolution correction (TASK 027):** the fix is a **single universal change** — absolutize
> relative `<img>`/`<a>` against the URL the page was actually *fetched* from (post-redirect
> final URL), not `input_ref`. The proposed fixes #2 (arXiv trailing-slash/version normalization)
> below turned out to be **wrong** and were **not** implemented: the real served HTML at
> `https://arxiv.org/html/2510.08369` is a **200 (no redirect, no `<base href>`)** whose figure
> srcs are **`2510.08369v2/x1.png`** — already relative to `/html/`, not bare `x1.png` as assumed
> below. So `urljoin("…/html/2510.08369", "2510.08369v2/x1.png")` → the correct versioned URL;
> appending a trailing slash would have *broken* it (doubled the path). Fixes #1 (fetched-URL
> base) and #3 (image magic-byte validation) landed; #4 shipped as a stderr drop-warning (no new
> machine-readable envelope field — see TASK 027 scope). Full detail: `docs/KNOWN_ISSUES.md`
> [HTML2MD-11 (RESOLVED)](./html2md-11-rewritten-fetch-relative-img-base.md) +
> [`docs/tasks/task-027-html-arxiv-image-resolution.md`](../tasks/task-027-html-arxiv-image-resolution.md).

## Symptom

Fetching an arXiv `/abs/` URL produced a raw capture in which **all 17 figure references pointed to a single asset**, and that asset was **not an image**: `file _attachments/1ac6c9….png` → `HTML document text, ASCII text`. i.e. every `<img>` resolved to the same 404 HTML error page, which was then saved verbatim as a `.png`. The `html` skill reported `images: 1` (looks like success). The paper's real figures live at `https://arxiv.org/html/2510.08369v2/x1.png … x16.png` + `figures/appendix/text-examples.png` (17 total — a 1:1 match to the 17 broken slots).

Text extraction itself was **perfect** (full paper, equations, appendices) via `engine: lite+arxiv-html`, so the HTML→MD path works; only image resolution is broken.

## Root cause (confirmed in code)

Three compounding defects, all on the url-mode fetch path:

1. **Absolutization uses `input_ref`, not the URL actually fetched.**
   `acquire.py:1503`:
   ```python
   page_html = _absolutize_links(_absolutize_img_srcs(page_html, input_ref), input_ref)
   ```
   `_tier_lite` (`acquire.py:1390`) rewrites the target `/abs/<id>` → `fetch_url = /html/<id>` (via `_arxiv_html_variant`, line 1398/1401) and fetches **that**, but returns only `(page_html, label)` — `fetch_url` is dropped on the floor. So `_acquire_url` absolutizes the `/html/` document's relative `src="x1.png"` against the **`/abs/` landing URL**. Result: `urljoin("https://arxiv.org/abs/2510.08369", "x1.png")` → `https://arxiv.org/abs/x1.png` → 404 HTML.

2. **The arXiv variant is version-less and has no trailing slash.**
   `_arxiv_html_variant` (`acquire.py:1282`) returns `https://arxiv.org/html/{id}` with no `vN` and no trailing `/`. Even if fix #1 propagated `fetch_url`, `urljoin("https://arxiv.org/html/2510.08369", "x1.png")` → `https://arxiv.org/html/x1.png` (RFC-3986 drops the last path segment because there's no trailing slash) → still 404. The correct base is the post-redirect, trailing-slashed dir: `https://arxiv.org/html/2510.08369v2/`.

3. **A non-image download is saved as an image.**
   `_resolve_url_image` (`acquire.py:1313`) returns whatever bytes come back and emit writes them to `_attachments/<hash>.png` with no content-type / magic-byte check. A 404 HTML body becomes a fake `.png`. (The 17→1 collapse is just content-hash dedup of that identical 404 body — which is also why `images: 1` looked benign.)

The `_absolutize_img_srcs` `<base href>` fallback (`acquire.py:1341`) did **not** save it here — empirically the images broke, so the fetched arXiv HTML either ships no `<base>` or it wasn't present in the lite-fetched body. Relying on `<base>` alone is fragile.

## Impact

Any source whose fetch URL differs from `input_ref` (arXiv `/abs/`→`/html/`, MediaWiki REST variant, `nojs` variant) and that uses **relative** image srcs will localize broken images while reporting success. arXiv is the clearest case because its figures are always relative (`x1.png`).

## Proposed fixes (prioritized)

1. **Propagate the real fetched/final URL and absolutize against it.** Have `_tier_lite` (and the other tiers) return the URL they fetched — ideally the **post-redirect final URL** from httpx (`resp.url`) — and use that as `base_url` for `_absolutize_img_srcs` / `_absolutize_links` / `AcquireResult.base_url` at line 1503, instead of `input_ref`. This is the core fix.
2. **Normalize the arXiv-html base to a trailing-slashed directory** (and prefer the versioned form). Either take httpx's final redirected URL, or, when the path matches `/html/<id>` and has no trailing slash, append one before `urljoin`. Keep honoring an in-document `<base href>` when present, but do not depend on it.
3. **Validate downloaded image bytes** in `_resolve_url_image` (or emit's localizer): check magic bytes (`\x89PNG`, `\xff\xd8` JPEG, `GIF8`, `RIFF…WEBP`, leading `<svg`/`<?xml` for SVG) and/or the HTTP `Content-Type`. Drop non-images instead of writing them as `.png`. Defense-in-depth so a bad URL can never masquerade as a figure.
4. **Emit a degradation signal** when image localization is lossy — e.g. N `<img>` refs collapsing to 1 unique asset, or any dropped-as-non-image. Surface it in the fetch result so downstream (`wiki-import`) can raise a `quality_flag: image_capture_degraded` **before** the REASON/summarize step. Today `images: 1` reads as success.

## Suggested regression tests

- `_absolutize_img_srcs` given an arXiv `/abs/` `input_ref` but a `/html/<id>v2` fetched-from URL resolves `x1.png` → `https://arxiv.org/html/<id>v2/x1.png` (not `/abs/x1.png`, not `/html/x1.png`).
- A url-mode fetch where the image endpoint returns `text/html` localizes **zero** images (not one HTML-as-png) and flags degradation.
- arXiv fixture with relative `x1.png…xN.png` yields N distinct localized assets.

## Workaround (until fixed)

For arXiv, pull figures from the HTML5 tree directly: base `https://arxiv.org/html/<id>vN/`, assets `x1.png…`, validate PNG magic bytes, then localize. (This is what was done by hand to repair the dogfood import — all 17 real figures recovered and re-linked in document order.)

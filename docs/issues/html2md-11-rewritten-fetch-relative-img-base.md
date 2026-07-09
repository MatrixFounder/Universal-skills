---
id: HTML2MD-11
type: known-issue
status: fixed
opened_at: 2026-07-09
resolved_at: 2026-07-09
resolved_by: TASK 027
category: correctness
severity: SEV-2
component: html
slug: html2md-11-rewritten-fetch-relative-img-base
---

# HTML2MD-11 — rewritten-fetch relative `<img>` srcs resolved against the wrong base → broken images — RESOLVED (TASK 027, 2026-07-09)

> Part of the HTML2MD (TASK 022) honest-scope set. The backlog row
> [`docs/office-skills-backlog.md`](../office-skills-backlog.md) §2 «html» owns the decision.

**Status:** ✅ RESOLVED (TASK 027; delete this entry when the fix commits). **Was:** SEV-2 silent
figure loss — fetching arXiv `/abs/<id>` (rewritten to `/html/<id>`) absolutized the page's
relative `<img>` against `input_ref` (`/abs/`), so `x1.png` → `/abs/…x1.png` → a 404 HTML body
that was then saved verbatim as `_attachments/<hash>.png`; all figures collapsed to one
HTML-as-png and the run looked successful. **Fix (universal, no per-site logic):** absolutize
`<img>`/`<a>` against the URL the page was actually **fetched** from — the post-redirect final
URL, propagated out of every tier via a `final_url_out` out-param (`_http_get_bytes`,
`_fetch_chrome_html`) and returned as the third element of each tier's `(html, label, base)`
tuple; `_acquire_url` uses it at the absolutization seam while `AcquireResult.base_url` stays the
canonical `input_ref` for provenance. NB the bug-doc's proposed arXiv trailing-slash/version hack
was **not** applied — it was wrong (the real served HTML at `/html/<id>` is a 200 with figure
srcs `<id>vN/xK.png` already relative to `/html/`, so a trailing slash would double the path).
Defense-in-depth: `_resolve_url_image` now magic-byte-validates the download (`_looks_like_image`:
PNG/JPEG/GIF/BMP/TIFF/ICO/WEBP/AVIF/HEIC/JXL/SVG) and **drops** a non-image body with a
control-char-sanitised stderr warning instead of writing it as `.png` (no more silent
`images: 1`). `_arxiv_html_variant` (the separate full-text acquisition feature) is unchanged.
**Verification:** 10 new regression tests (`test_url.py::TestArxivImageResolution`) + full suite
(282) + e2e diff-gate + `validate_skill` green; live dogfood on `arxiv.org/abs/2510.08369` now
localises all 17 figures as real PNGs (was 1 HTML-as-png). Root-cause write-up:
[`html-arxiv-image-resolution-bug.md`](./html-arxiv-image-resolution-bug.md); RTM in
[`docs/tasks/task-027-html-arxiv-image-resolution.md`](../tasks/task-027-html-arxiv-image-resolution.md).

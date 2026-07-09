# TASK 027 — `html`: fix arXiv `/abs/`→`/html/` relative `<img>` resolution (broken figures)

**Status:** ✅ COMPLETE (VDD — adversarial review converged 2026-07-09).
**Skill:** `html` (Proprietary — embeds docx/pdf code; NOT Apache-2.0).
**Mode:** VDD (Verification-Driven, adversarial gate).
**Origin:** external-agent feedback + real-vault dogfood
([`docs/html-arxiv-image-resolution-bug.md`](html-arxiv-image-resolution-bug.md)),
catalogued as **HTML2MD-11** in
[`docs/KNOWN_ISSUES.md`](KNOWN_ISSUES.md) (OPEN BUG, not honest-scope).

---

## 0. Meta

- **Task ID:** 027 · **Slug:** `html-arxiv-image-resolution`
- **Date:** 2026-07-09
- **Driver (RU):** «другой агент написал обратную связь про конвертации страниц
  arxiv.org — надо исправить ошибки».
- **Affected file:** `skills/html/scripts/html2md/acquire.py` (html-authored — NOT a
  cross-skill replicated file, so no docx/pdf/office replication is triggered).

## 1. Problem (SEV-2 silent data loss)

Fetching an arXiv `/abs/<id>` URL rewrites the fetch to `/html/<id>` (`_tier_lite` →
`_arxiv_html_variant`) but **absolutizes the fetched page's relative `<img src="x1.png">`
against the original `/abs/` landing URL**, not the URL actually fetched. Result:
`urljoin("https://arxiv.org/abs/2510.08369", "x1.png")` → `https://arxiv.org/abs/x1.png`
→ **404 HTML**, which is then saved verbatim as `_attachments/<hash>.png`. All N figures
collapse to one HTML-as-png placeholder; the envelope reports `images: 1` (looks like
success). Text extraction is unaffected.

Three compounding defects (all on the lite fetch path), plus one observability gap:

1. Absolutization base is `input_ref`, not the fetched URL (`_acquire_url:1503`).
2. The arXiv variant base is version-less **and has no trailing slash**, so even a
   propagated base loses the last path segment under RFC-3986 `urljoin`
   (`.../html/2510.08369` + `x1.png` → `.../html/x1.png`).
3. A non-image HTTP body (e.g. a 404 HTML page) is written as `.png` with no
   content/magic-byte check (`_resolve_url_image:1313`).
4. Lossy localization is silent — `images: 1` reads as success.

## 2. Requirements Traceability Matrix (RTM)

| ID  | Requirement | Verification |
|-----|-------------|--------------|
| **R1** | Absolutize relative `<img src>` / `<a href>` against the **actually-fetched, post-redirect** URL (httpx final URL), not `input_ref`. Propagate that base out of `_tier_lite` and use it at the `_acquire_url` absolutization seam. `AcquireResult.base_url` stays the canonical `input_ref` (provenance unchanged). This alone fixes the dogfood case: arXiv serves `/html/<id>` at **200 (no redirect, no `<base href>`)** with figure srcs `<id>vN/xK.png` **relative to `/html/`**, so resolving against the fetched `/html/<id>` (not `/abs/<id>`) yields the correct versioned URL. | `test_http_get_bytes_reports_final_url`, `test_arxiv_abs_figures_resolve_against_html_dir`, `test_redirect_base_is_final_url_universal` |
| **R2** | The base is **universal — no per-site logic**. `_absolutize_base(fetch_url, final_url)` returns `final_url or fetch_url` (RFC-3986 §5.1.3), plus the pre-existing in-document `<base href>` override. **Corrected from the bug-doc proposal:** an arXiv trailing-slash/version hack would have been *wrong* (real srcs already carry the `<id>vN/` prefix relative to `/html/`, so appending a slash would double the path). `_arxiv_html_variant` (a separate content-acquisition feature) is unchanged. | `test_absolutize_base_universal` |
| **R3** | Validate downloaded image bytes in `_resolve_url_image`: accept only real image magic bytes (`\x89PNG`, `\xff\xd8` JPEG, `GIF8`, `RIFF…WEBP`, BMP/TIFF/ICO) or an `<svg` head; **drop** (return `None`) a non-image (e.g. HTML) body instead of writing it as `.png`. Covers BOTH emit + serialize localizers (single seam). | `test_resolve_url_image_rejects_html`, `test_looks_like_image_matrix` |
| **R4** | Emit a **degradation signal** — a concise stderr warning — when `_resolve_url_image` drops a fetched body as non-image, so a lossy localization is no longer silent. No new machine-readable envelope contract (out of scope; documented). | `test_resolve_url_image_warns_on_drop` |
| **R5** | No regression: full `html` package suite + e2e `diff -q` gate green; `validate_skill.py skills/html` exit 0. Existing lite/chrome/remote tier behaviour and `AcquireResult.base_url` provenance unchanged for the common (non-variant, non-redirect) case. | full suite + validator |

## 3. Scope / non-goals

- **In scope:** the lite tier absolutization base (universal, post-redirect) + image
  magic-byte validation + drop-warning. One file (`acquire.py`) + tests. **No per-site
  image logic** — the fix is generic; `_arxiv_html_variant` (full-text acquisition) is
  retained by user decision (2026-07-09) as a separate, unrelated feature.
- **Out of scope (documented honest-scope):**
  - Chrome / remote tiers keep `input_ref` as their absolutization base — the Chrome DOM
    is already browser-absolutized and remote readers return absolute/markdown; no arXiv
    variant flows through them. (R1 fixes the lite path where the variant rewrite lives.)
  - A machine-readable `quality_flag: image_capture_degraded` on the output envelope
    (there is no images-count envelope today) — the stderr warning is the shipped signal;
    the structured flag is a future `wiki-import`-side enhancement.
  - The "N refs → 1 unique asset collapse-ratio" heuristic — moot once R1+R2 resolve
    figures correctly; the per-drop warning (R4) is the retained signal.

## 4. Definition of Done

1. All R1–R5 verifications green (new regression tests + full suite).
2. `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/html` → exit 0.
3. `docs/KNOWN_ISSUES.md` HTML2MD-11 moved to **Resolved** (deleted with a resolution
   note per the file's lifecycle rule); `docs/html-arxiv-image-resolution-bug.md` status
   flipped to **resolved** with the fix commit reference.
4. Adversarial review converges (0 CRITICAL, no legitimate logic/security findings).

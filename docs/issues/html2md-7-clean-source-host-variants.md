---
id: HTML2MD-7
type: known-issue
status: handled
opened_at: 2026-06-23
category: robustness
severity: LOW
component: html
slug: html2md-7-clean-source-host-variants
---

# HTML2MD-7 — clean-source host variants (Wikipedia REST, arXiv /html)

> Part of the HTML2MD (TASK 022) honest-scope set. The backlog row
> [`docs/office-skills-backlog.md`](../office-skills-backlog.md) §2 «html» owns the decision.

**Status:** handled • **Severity:** LOW (residual) • **Location:** `acquire._mediawiki_rest_variant`
/ `_arxiv_html_variant` / `_acquire_url`.
**Was (feedback R-7/R-9):** canonical `…/wiki/<Title>` is chrome-heavy and `preprocess` stripped
its body to nothing (silent empty); arXiv `/abs/` gave only the abstract and `/pdf/` a binary PDF.
**Now:** `auto`/`lite` proactively fetch Wikipedia's Parsoid REST `page/html` endpoint
(engine `lite+restapi`) and arXiv's `/html/<id>` full text (engine `lite+arxiv-html`); relative
links/images resolve against the endpoint's `<base href>`. Provenance (`source:`) stays the
canonical URL. **Residuals:** (a) PDF-only arXiv papers 404 on `/html/` → typed
`FetchFailed kind=arxiv_no_html` with a "use the pdf skill" hint (correct, not a bug);
(b) the **reader variant** on Wikipedia REST HTML is thin (Parsoid is landmark-free → the
`spa-largest-contentful-subtree` reader heuristic under-extracts) — the **whole-page `.md` is
the faithful, substantial output**, so prefer it for Wikipedia. **Do-not:** treat `arxiv_no_html`
as a failure to retry — fetch the PDF instead.

---
id: HTML2MD-5
type: known-issue
status: open
opened_at: 2026-06-23
category: correctness
severity: LOW
component: html
slug: html2md-5-cosmetic-conversion-quirks
---

# HTML2MD-5 — cosmetic conversion quirks

> Part of the HTML2MD (TASK 022) honest-scope set. The backlog row
> [`docs/office-skills-backlog.md`](../office-skills-backlog.md) §2 «html» owns the decision.

**Status:** open (low-priority) • **Severity:** LOW.
(a) **Slug collision** — distinct inputs with the same filename/URL stem write
`<slug>-2.md`, `<slug>-3.md` (idempotent via a hidden source-id marker), so the output name
is not always the bare stem. (b) **Empty-heading merge** (`md_clean`) re-levels the line
after an empty heading into that heading — for the targeted GitBook/Mintlify pattern this is
correct, but a body paragraph directly after an empty heading would be mis-leveled (never
deleted). (c) **Math-signal heuristic** (`md_clean._normalize_math`) — bracket forms `\[…\]`
convert to `$$…$$` only when the body looks mathy (LaTeX command / sub-superscript / operator
between operands), so turndown-escaped plain `[word]`/`[1]` are NOT mangled into math; the
trade-off is a bare single-variable display like `\[x\]` from the remote-reader path is left
as-is. Real `class="math"` spans (the lite path) are unaffected — they convert via the DOM rule.
(d) **Inline `data:` images** — content-sized blobs are localized to `_attachments/` (decoded
to files); the icon-vs-content cut is a **dual floor**: ≥1024-char encoded URI *and* ≥512
decoded bytes, so a percent-encoded icon that clears the encoded floor but is tiny decoded is
still dropped (the decoded floor is the load-bearing one). An SVG `data:` image is written
verbatim — Obsidian/weasyprint render it without executing embedded JS, so a `<script>` in it is
inert, but it is not sanitized. In `--no-download-images` file mode a `data:` image stays inline
(self-contained note); `--stdout` strips it (no localization there → would be base64 bloat).
**Related:** [`docs/office-skills-backlog.md`](../office-skills-backlog.md) §2 «html».

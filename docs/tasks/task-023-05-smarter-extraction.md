# Task 023-05 [LOGIC]: smarter extraction — X-Target-Selector + trust-markdown

> **Predecessor:** 023-02 (provider request builder), 023-03 (ladder), 023-01 (`content_kind`).
> **RTM:** [R4] smarter extraction.
> **ARCH:** §15.3 (request shape), §15.5 (trust-markdown data path), §15.8 D-23-D.

## Use Case Connection
- UC-5 (trust the reader's clean Markdown for a hard page).

## Task Goal
Make the remote reader extract just the article (`X-Target-Selector`) and add an opt-in
mode that trusts the reader's own clean Markdown (`--remote-format markdown`), wrapping it
with our frontmatter + image localization while bypassing the local clean/turndown passes.

## Changes Description

### File: `skills/html2md/scripts/html2md/acquire.py`
**`_build_reader_request` (extend):**
- Add header `X-Target-Selector: <opts.target_selector>` on every remote request. The
  default lives in a single module constant `_DEFAULT_TARGET_SELECTOR = "article, main,
  [role=main]"` shared by the CLI default (023-01) and the builder, so the two cannot drift.
- `X-Return-Format` already follows `opts.remote_format` (023-02). When `markdown`, the
  decoded body is Markdown, not HTML.
**`_fetch_remote_html` / `_acquire_url` (remote success path):**
- When `opts.remote_format == "markdown"`, return an `AcquireResult` with
  `content_kind="markdown"`, `markdown=<decoded body>`, `html=""` (or the raw for meta),
  `engine` label as usual; metadata best-effort from any frontmatter the reader emitted
  else from the target URL.

### File: `skills/html2md/scripts/html2md/cli.py`
**`convert(args)`:**
- If `acq.content_kind == "markdown"`: **skip** `clean_mod.clean` and
  `core_bridge.html_to_markdown`; set `md_whole = tidy_markdown(acq.markdown)` (light tidy
  only), `md_reader = None` (no second extraction → no reader variant). Then `emit` as usual.
- Default (`html`) path unchanged.

### File: `skills/html2md/scripts/html2md/emit.py`
- Image localization for the markdown branch **MUST go through `_resolve_url_image` →
  `_http_get_bytes`** (the per-hop `_assert_public_http` is the SSRF boundary — never a
  direct/bulk `httpx` fetch). A gated-out (internal/metadata) image URL → `_resolve_url_image`
  returns `None` → image **dropped, never fatal**. No new download path — the markdown branch
  reuses the existing image step.

## Test Cases
### Unit (offline)
1. **TC-05-01 `test_target_selector_header_sent`** — a remote request includes
   `X-Target-Selector: article, main, [role=main]`; `--target-selector .content` overrides.
2. **TC-05-02 `test_remote_format_markdown_bypasses_pipeline`** — `--engine jina
   --remote-format markdown`, reader returns Markdown → `content_kind=="markdown"`; `clean`
   and `core_bridge` NOT called (spy); emitted body == reader Markdown (modulo frontmatter).
3. **TC-05-03 `test_trust_markdown_no_reader_variant`** — only `<slug>.md` written (no `.reader.md`).
4. **TC-05-04 `test_trust_markdown_images_localized`** — `--download-images` localizes
   `http(s)` image links found in the returned Markdown into `_attachments/`; `data:` skipped.
5. **TC-05-05 `test_default_html_unchanged`** — without `--remote-format markdown`, remote
   HTML still flows through `clean`→turndown (regression guard).
6. **TC-05-06 (SSRF) `test_internal_image_url_in_markdown_dropped`** — reader Markdown
   contains an `<img>`/`![]()` whose host resolves to an internal/metadata IP →
   `_resolve_url_image` returns `None` (not fetched, gate spy sees no internal hop); the
   note is still emitted with the image link dropped (not fatal).
### Regression
- Full suite; battery (`tests/test_battery.py`) unaffected (markdown trust-mode is opt-in).

## Acceptance Criteria
- [ ] **[R4]** `X-Target-Selector` sent on remote requests; `--target-selector` overrides.
- [ ] **[R4]** `--remote-format markdown` bypasses clean/turndown; frontmatter still added; no reader variant.
- [ ] **[R4]** trust-markdown images localized via the SSRF-gated path; default html path unchanged.
- [ ] No gated master touched.

## Notes
- Adversarial roast focus: a reader returning HTML when `markdown` was requested (detect &
  fall back to the html path rather than emitting raw HTML as "markdown"); a giant markdown
  body (respect `--max-bytes` on the reader fetch).

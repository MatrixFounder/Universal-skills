<!-- Hand-maintained thin index. One issue == one file in docs/issues/<slug>.md. -->
# Known Issues — Universal-Skills

Catalogue of **acknowledged** issues across the skills in this repository.
Each entry is a deliberate deferral or a resolved-but-retained record, NOT
a bug to re-discover. Future agents (and humans) MUST read this index (and
the linked issue file) before opening a new task that touches the same
surface — see [CLAUDE.agentic.md](../CLAUDE.agentic.md) §"Pipeline §1
Analysis Phase" which mandates this read.

## Rules

- **One issue = one file.** Every issue lives in its own file under
  [`docs/issues/`](issues/) named `<slug>.md`, carrying YAML frontmatter
  (`id`, `type: known-issue`, `status`, `opened_at`, `category`, optional
  `severity` / `component` / `resolved_at` / `resolved_by`, `slug`) and a
  body with the full Symptom / Root cause / Fix path / Do-not detail.
- **This file is a thin index only.** It is hand-maintained — no prose lives
  here beyond these rules and the per-category link list below.
- **Entry lifecycle**: an issue lives here while it is **documented +
  deferred** (`status: open` / `by-design` / `mitigated` / `handled`), or as
  a **resolved record** (`status: fixed`) kept for posterity until the fix
  commit is old enough to prune. When a fix lands, either flip the entry's
  `status` to `fixed` with a `resolved_by` pointer, or delete the file in the
  same commit that ships the fix (reference the entry text in the commit body).
- **Statuses used**: `open` (deferred, unfixed), `by-design` (intentional
  honest-scope limitation), `mitigated` / `handled` (materially addressed,
  documented residual), `fixed` (resolved, record retained).

## How to add a new entry

1. Create `docs/issues/<slug>.md` with the frontmatter schema above and a
   body covering: ID • Status • Severity • Location • Symptom • Reproduction •
   Workaround • Fix path • Related • Do-not.
2. Add one line to the relevant `## <category>` section below (create a new
   category heading if none fits). Keep the categories alphabetical.
3. Cross-link to the backlog row that owns the deferral decision
   ([`docs/office-skills-backlog.md`](office-skills-backlog.md)), and to
   sibling issues with a relative `[label](issues/<slug>.md)` link.
4. If a fix lands, flip `status: fixed` (+ `resolved_at` / `resolved_by`) or
   delete the file — reference the entry text in the commit body for posterity.

---

## correctness

- **HTML2MD-5** [cosmetic conversion quirks (slug collision, empty-heading merge, math signal, data: images)](issues/html2md-5-cosmetic-conversion-quirks.md) — severity `LOW`, status `open`, opened 2026-06-23
- **HTML2MD-11** [rewritten-fetch relative `<img>` srcs resolved against the wrong base → broken images](issues/html2md-11-rewritten-fetch-relative-img-base.md) — severity `SEV-2`, status `fixed`, opened 2026-07-09
- **HTML2MD-11-BUG** [arXiv relative `<img>` resolution — deep-dive root-cause write-up](issues/html-arxiv-image-resolution-bug.md) — severity `SEV-2`, status `fixed`, opened 2026-07-09
- **HTML2MD-12** [arXiv/LaTeXML MathML (`<math alttext>`) came out as garbled glyphs](issues/html2md-12-arxiv-latexml-mathml-garbled.md) — severity `SEV-2`, status `fixed`, opened 2026-07-09
- **PDF-EXTRACT-FIGURE-PAGE-UNFLAGGED** [страница из одной схемы не помечается — колонтитул выбивает её из-под порога в 10 символов, содержимое теряется молча](issues/pdf-extract-figure-page-unflagged.md) — severity `SEV-2`, status `fixed`, opened 2026-08-29, resolved 2026-08-29
- **PDF-EXTRACT-TOLERANCE-ARTIFACTS** [`pdf_extract.py` наследует дефолты pdfplumber: маркеры списка теряют порядок, заливки фона превращаются в строки таблиц](issues/pdf-extract-tolerance-artifacts.md) — severity `SEV-2`, status `fixed`, opened 2026-08-29, resolved 2026-08-29
- **PDF-EXTRACT-DOGFOOD-CYCLE2-RESIDUALS** [что нашёл второй цикл догфуда на 20 незнакомых документах и что из этого НЕ починено](issues/pdf-extract-dogfood-cycle2-residuals.md) — severity `SEV-2`, status `fixed`, opened 2026-09-01, resolved 2026-09-01
- **PDF-EXTRACT-VECTOR-COVERAGE-BACKDROP** [`vector_coverage` считает подложку страницы графикой и насыщается в 1.0 на сплошном тексте](issues/pdf-extract-vector-coverage-backdrop.md) — severity `SEV-3`, status `fixed`, opened 2026-08-30, resolved 2026-08-30
- **PDF-EXTRACT-STDOUT-LOCALE-ENCODING** [дамп на stdout кодировался кодеком локали: под `LC_ALL=C` обрывался на полуслове, под `cp1252` молча переставал быть UTF-8](issues/pdf-extract-stdout-locale-encoding.md) — severity `SEV-2`, status `fixed`, opened 2026-08-31, resolved 2026-08-31
- **PDF-EXTRACT-UNMAPPED-FONT-TEXT-LOSS** [документ без встроенных шрифтов теряет всю нелатиницу ещё при производстве — дамп отдаёт exit 0 и выглядит здоровым](issues/pdf-extract-unmapped-font-text-loss.md) — severity `SEV-2`, status `fixed`, opened 2026-08-29, resolved 2026-08-29

## dogfood

- **WIKI-INGEST-015-RESOLVED** [wiki-ingest — all 15 deferred findings resolved post-TASK-015](issues/wiki-ingest-resolved-post-task-015.md) — status `fixed`, opened 2026-05-26

## honest-scope

- **HTML2MD-2** [PDFs / binary URLs are not converted](issues/html2md-2-pdf-binary-urls-not-converted.md) — severity `LOW`, status `by-design`, opened 2026-06-23
- **HTML2MD-3** [data-grid SPAs degrade](issues/html2md-3-data-grid-spas-degrade.md) — severity `LOW`, status `open`, opened 2026-06-23
- **TF-YANDEX-1** [Yandex VH/Strm is ASR-only — that player carries no caption track](issues/transcript-fetcher-yandex-asr-only.md) — severity `LOW`, status `by-design`, opened 2026-07-31

## performance

- **PERF-HIGH-2** [`payloads_list = list(payloads)` materialises generators (residual after xlsx-8a-07/08)](issues/perf-high-2-payloads-list-materialises-generators.md) — severity `MED`, status `mitigated`, opened 2026-05-13
- **HTML2MD-9** [ladder latency has no aggregate deadline; `--max-bytes` unbounded by default](issues/html2md-9-ladder-latency-no-aggregate-deadline.md) — severity `LOW`, status `open`, opened 2026-06-23

## robustness

- **PDF-EXTRACT-BROKEN-PIPE-EXIT-120** [`… | head` давал код возврата 120 при envelope'е `"code": 1` и лишнюю не-JSON строку на stderr](issues/pdf-extract-broken-pipe-exit-120.md) — severity `SEV-3`, status `fixed`, opened 2026-08-31, resolved 2026-08-31
- **PDF-CLI-STDOUT-JSON-LOCALE-CLASS** [JSON на stdout кодировался локалью вызывающего во всём репозитории, а мёртвый читатель подменял код возврата](issues/pdf-cli-stdout-json-locale-class.md) — severity `SEV-2`, status `fixed`, opened 2026-08-31, resolved 2026-08-31
- **PDF-4** [`pdf_ocr.py` vdd-multi deferred LOWs (sidecar atomicity, `--list-langs` non-zero exit)](issues/pdf-4-pdf-ocr-vdd-multi-deferred-lows.md) — severity `LOW`, status `fixed`, opened 2026-06-03
- **HTML2MD-1** [Cloudflare/captcha-hard sites auto-recover via the remote reader tier](issues/html2md-1-cloudflare-captcha-remote-tier-recovery.md) — severity `LOW`, status `handled`, opened 2026-06-23
- **HTML2MD-7** [clean-source host variants (Wikipedia REST, arXiv /html)](issues/html2md-7-clean-source-host-variants.md) — severity `LOW`, status `handled`, opened 2026-06-23
- **HTML2MD-8** [empty-extraction guard (no more silent empties)](issues/html2md-8-empty-extraction-guard.md) — severity `SEV-2`, status `handled`, opened 2026-06-23
- **TF-HUMAN-REPORT-LOCALE-CRASH** [человекочитаемые отчёты падали под не-UTF-8 локалью ещё до первой строки вывода](issues/tf-human-report-locale-crash.md) — severity `SEV-3`, status `fixed`, opened 2026-08-31, resolved 2026-09-01
- **HUMAN-CLI-OUTPUT-LOCALE-CLASS** [человекочитаемый вывод падает под не-UTF-8 локалью во всём репозитории, включая `--help`](issues/human-cli-output-locale-class.md) — severity `SEV-3`, status `open`, opened 2026-09-01
- **TF-X-2** [ffmpeg is required for the X ASR path on HLS sources (Broadcasts/Spaces)](issues/tf-x-2-ffmpeg-required-for-x-asr-hls.md) — severity `MEDIUM`, status `handled`, opened 2026-07-09
- **TF-X-4** [captions: VTT + SRT + TTML/DFXP](issues/tf-x-4-captions-vtt-srt-ttml.md) — severity `LOW`, status `handled`, opened 2026-07-09
- **TF-X-5** [X auth + long-broadcast cost + duration](issues/tf-x-5-x-auth-long-broadcast-duration.md) — severity `LOW`, status `handled`, opened 2026-07-09
- **TF-X-6** [ASR filler on silence → silence-removal preprocessing](issues/tf-x-6-asr-filler-on-silence-removal.md) — severity `LOW`, status `handled`, opened 2026-07-09
- **TF-X-7** [media-download `TimeoutExpired` orphans ffmpeg children; workdir rmtree races them](issues/tf-x-7-timeout-orphans-ffmpeg-children.md) — severity `LOW`, status `fixed`, opened 2026-07-10
- **TF-X-8** [ASR backend `TimeoutExpired` has no process-group teardown (same shape as TF-X-7)](issues/tf-x-8-asr-subprocess-timeout-no-process-group.md) — severity `LOW`, status `fixed`, opened 2026-08-18
- **TF-X-9** [`install_components.py` runs `pip` / `brew` / `apt` with no timeout — unbounded hang](issues/tf-x-9-install-components-no-timeout.md) — severity `LOW`, status `open`, opened 2026-08-19

## security

- **DOCX-MERMAID-EXECSYNC** [Mermaid `execSync` predictable-name-in-CWD temp files](issues/docx-mermaid-execsync.md) — severity `LOW`, status `fixed`, opened 2026-06-05
- **HTML2MD-4** [SSRF residuals (lite path hardened; chrome TOCTOU residual)](issues/html2md-4-ssrf-residuals-lite-path-hardened.md) — severity `LOW`, status `open`, opened 2026-06-23
- **HTML2MD-6** [the remote-reader tier sends the target URL to an external service](issues/html2md-6-remote-reader-sends-url-external.md) — severity `LOW`, status `by-design`, opened 2026-06-23
- **HTML2MD-10** [authenticated Chrome (login-gated) honest-scope](issues/html2md-10-authenticated-chrome-honest-scope.md) — severity `LOW`, status `handled`, opened 2026-06-23
- **TF-X-3** [cloud ASR egresses audio (opt-in)](issues/tf-x-3-cloud-asr-egresses-audio.md) — severity `LOW`, status `by-design`, opened 2026-07-09

## tech-debt

- **XLSX-10B-DEFER** [xlsx-7 refactor to consume `xlsx_read` (14-day timer, duplication risk)](issues/xlsx-10b-defer-xlsx-7-consume-xlsx-read.md) — status `open`, opened 2026-05-14
- **XLSX-9-LOWS-DEFER** [vdd-multi iter-1+2 LOW-tier findings (deferred to xlsx-9b)](issues/xlsx-9-lows-defer-vdd-multi-low-findings.md) — severity `LOW`, status `open`, opened 2026-05-14
- **WIKI-INGEST-016-VDD-DEFER** [TASK 016 VDD-multi residuals (lint false-positives + cosmetic nits)](issues/wiki-ingest-016-vdd-defer.md) — severity `LOW`, status `open`, opened 2026-05-26
- **TF-X-1** [youtube/vimeo not retrofitted onto the shared `_ytdlp_media.py`](issues/tf-x-1-youtube-vimeo-not-on-shared-ytdlp-media.md) — severity `LOW`, status `by-design`, opened 2026-07-09

## test

- **XLSX-PREVIEW-PNG-ASSERT** [preview smoke-test asserts PNG magic but `preview.py` emits JPEG](issues/xlsx-preview-png-assert.md) — severity `LOW`, status `fixed`, opened 2026-06-05

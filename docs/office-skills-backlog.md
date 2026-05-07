# Office-skills backlog

Что осталось сделать после базовой итерации §9.6 плана
[`refactoring-office-skills.md`](refactoring-office-skills.md). Это
живой документ — добавляем сюда обнаруженные пробелы по мере
эксплуатации, потом приоритезируем явно (P0–P3).

## Условные обозначения

- **Effort**: S (≤ 3 ч), M (3–8 ч), L (8–20 ч), XL (20–40 ч), XXL (40+ ч,
  обычно растянутая итеративная история с несколькими VDD-циклами).
- **Value**: H — закрывает реальную пользовательскую боль, M — расширяет
  покрытие, L — nice-to-have.
- **Status**: open / in-progress / done / dropped.
- **Dep**: что должно быть готово раньше, чтобы взяться за пункт.

## 1. Уже сделано (для контекста)

- §9.6 priority-list: все 13 ключевых скриптов (4 docx + 3 pptx +
  3 xlsx + 3 pdf).
- `office/` модуль (unpack/pack/validate/validators/helpers/shim/tests),
  байт-идентичная репликация в xlsx/pptx.
- `LICENSE` (Apache-2.0 + per-skill proprietary для четырёх office), 
  `THIRD_PARTY_NOTICES.md`.
- `SKILL.md` + `references/` + `examples/` для всех 4 скиллов.
- `skill-validator` зелёный на всех 4.
- Plan addendum (pptx fix-итерация): `--pptx-editable`, динамический
  subtitle.
- Bonus: mermaid-preprocess в `md2pdf.py` (PNG-вариант, фиксит
  Cyrillic-glyph fallback в weasyprint SVG).
- VDD-фиксы по docx2md: TOC anchors внутри headings/bold cells, italic
  matching, run-stutter dedup, table cell heading downgrade.
- **html2pdf XXL-итерация**: VDD iter-1..7 с per-iter adversarial review;
  split в `html2pdf_lib/` package (7 модулей, 2113 LOC); preprocessing
  pipeline 948 LOC (drawio foreignObject→`<text>`, edge-label backdrop,
  align-items semantics, light-dark unwrap, code-block wrap, ARIA
  tables, reader-mode); 4-tier regression battery (31 fixture × 2 modes
  × tolerance bands + required needles per platform); 55 unit-тестов
  в `test_preprocess.py` (844 LOC).
- **html2docx XL-итерация**: VDD iter-1..4 + adversarial round + 4 фикс-раунда
  на реальной 19-fixture battery; `--reader-mode`, Tier-2 SVG renderer
  (Chrome → resvg fallback с pre-flight санитизацией), preprocessing
  pipeline (chrome strip с anchored `aria-label^="Copy "` selectors,
  icon SVG strip с 8 правилами incl. FontAwesome 7 mask-pattern,
  ARIA tables, Mintlify Steps flatten, Confluence DC code wrap +
  inline-ancestor hoist, shiki/Fern table flatten gated по marker-классам,
  inactive Radix tab strip, Tailwind `print:hidden`); 855 LOC CLI +
  1428 LOC walker + 402 LOC SVG renderer + 326 LOC archive extractors.
- **pdf-8 (subframe-aware extraction) ✅** (2026-05-05, +760 LOC archives.py
  + 102 LOC CLI): универсальный `extract_archive(src, work_dir,
  frame_spec="main\|N\|all\|auto")` для webarchive **и** MHTML.
  Структурная substantial-эвристика (≥ 1 KB, 0 scripts, ≥ 30 chars text,
  не single-img) — валидирована на 7 реальных фикстурах (3 ELMA365 +
  Gmail + Sentora ×2 + ya_browser); 0 vendor-имён в коде. CLI:
  `--archive-frame N\|main\|all\|auto`, `--list-frames`. Per-frame
  namespace + sha1 image-dedup. Encoding parity (subframe charset).
  10 unit-тестов в `tests/test_preprocess.py`.
- **pdf-9 (universal SPA-chrome heuristic) ✅** (+406 LOC reader_mode.py):
  structural SPA-detection (body ≥ 50 KB OR ≥ 5 `<script src=>` OR ≥ 3
  ARIA-landmarks, no framework strings); ARIA-role strip (`navigation`/
  `complementary`/`banner`/`contentinfo`); semantic landmark strip
  (`<aside>`/`<nav>`/`<footer>` + shallow `<header>`); inline
  `position:fixed` overlay strip; largest-contentful-subtree fallback
  для landmark-free SPA. Validated на 4 SPA-стэках: Angular (ELMA365),
  Closure (Gmail), Framer (Sentora ×2), bare DOM (Yandex Cloud).
  Title-match LCS-bonus (4×) для multi-article feed pages (TradingView).
  10 unit-тестов.
- **pdf-10 v1 (beauty CSS + empty-element collapse) ✅**: `_strip_html_comments`
  убирает Angular/React skeleton placeholders (`<!---->`); `:empty`
  CSS-rule collapses cells; scoped `min-font-size: 9pt` (skip elements
  с inline `font-size:0` — mail.ru newsletter preheader compatibility);
  `tr { page-break-inside: avoid }`; `body { overflow-x: hidden }`;
  `table { max-width: 100% }`; `img[width][height]` icon-size
  preservation; widows/orphans control. 6 unit-тестов. Honest scope:
  sibling-repetition card-flatten + machine-checkable acceptance
  (no-overflow, no-tr-split, font ≥ 9pt) deferred → pdf-10a.
- **pdf-11 (Chrome-headless engine via Playwright) ✅ DONE через 8
  итераций VDD-adversarial**: opt-in альтернативный движок для случаев,
  когда weasyprint объективно не справляется (Material 3 calc/var bugs,
  Framer infinite-loop, ELMA365 inline.py assertion, JS-hydrated content,
  `<canvas>` charts).

  **Финальный pipeline** (после 8 итераций adversarial review):
  1. `<base href>` strip (webarchives хранят live-site origin → all
     relative URL'ы блокировались offline route handler'ом).
  2. `<script>` strip из HTML + JS-enabled на context level (для
     `page.evaluate`) — страница не запускает свой JS (нет Gmail
     self-destruct, нет Angular half-hydration), но мы можем surgically
     normalize DOM.
  3. Layout normalize CSS: high-specificity `body` release; tight icon-
     font selector `i[class*="-icons"]:not(:has(*))` (leaf-only, не
     каскадирует на детей через CSS inheritance); `[class~="spinner"]`
     exact-word match вместо substring (избегает false-positives типа
     "spinner-class-banner"); image cap `max-height: 200px`,
     avatar `... img` cap 48×48.
  4. JS-based DOM normalize: width-gate `offsetWidth >= 200` для
     overflow release (узкие icon-sidebars 64px не unfurl'ят labels);
     position:fixed → static только для substantial modals (`width >
     50% viewport`, ow > 200, textLen > 50); modal-portal hide (когда
     модалка released, скрываем underlying CRM page чтобы первые 2
     страницы PDF не были мусором).
  5. `media: screen` (default `print` триггерит SPA-print-stylesheets
     которые скрывают контент); 1280×1024 viewport (desktop-class CSS).
  6. `page.pdf(scale = pdf_usable / viewport_width)` ≈ 0.561 для A4 —
     1280px layout вписывается в ~718px usable A4 width без обрезки
     справа.

  **Финальные результаты** на 6 fixture/mode комбинациях:
  - gmail_example regular: 988 KB / 4p — full Sentora newsletter,
    нет "Временная ошибка" fallback (Gmail self-destruct prevented).
  - gmail_example reader: 5p clean newsletter без Gmail UI chrome.
  - elma365_activities regular: 4p — все 25 активностей включая
    user-cited 29.01.2025 / 04.02.2025 / Тест ТД, без CRM
    contractor list noise (modal-portal-hide), без icon-font
    ligatures ("arrow_down" / "fullscreen_enter" / "system_close").
  - elma365_activities reader: 15p flat text (reader-mode для
    data-heavy SPA дешевле, чем chrome alone — рекомендуем chrome
    без reader для card layouts).
  - ya_browser: 2p marketplace card, sidebar contained без overlap
    (width-gate prevents narrow-sidebar label leak).

  **Тесты**: 131 unit + 4 E2E negative regression
  (`test_gmail_no_offline_error_fallback`, `test_elma365_full_
  activity_log_present`, `test_elma365_no_underlying_page_noise`,
  `test_elma365_no_icon_font_ligature_artifacts`,
  `test_ya_browser_no_sidebar_label_leak`,
  `test_ya_browser_no_excessive_empty_pages`,
  `test_chrome_css_no_false_positive_class_substring_bleed`).

  Soft-optional dep: `requirements-chrome.txt`, `bash install.sh
  --with-chrome` ставит Playwright + Chromium (~150 MB). Lazy import,
  fail-loud `ChromeEngineUnavailable` envelope с remediation.

  **Honest scope (отложено в pdf-11a)**: `--engine auto` с structural
  pre-scan (calc-count, canvas-count, virtualizer-markers) и engine-
  decision cache в side-car file; cross-platform validation (Linux
  Alpine/RHEL, Docker `--no-sandbox`, Lambda chrome-min); chrome
  движок для html2docx через pandoc bridge.

- **VDD-adversarial фиксы (8 hardenings, post-pdf-8/9/10)**:
  (1) `<img src=>` HTML-encoded `&amp;` URL rewrite — fixed silent
  image loss on signed-S3 URLs (email-list JPEG, HubSpot 2400+ icons);
  (2) `_is_substantial_frame(None)` defensive guard;
  (3) `<table> { max-width: 100% }` — wide tables silently clipped;
  (4) auto-mode dominance ratio (1-substantial subframe → main if
  text < 10 % main) — fixed HubSpot WP picking error-modal subframe;
  (5) `_strip_universal_chrome` strips `<nav>`/`<aside>` + carousel/
  similar-products class patterns + ticker-tape patterns universally;
  (6) `position: absolute` reset (left/right/bottom auto) — устраняет
  visual overlap на Yandex sidebar nav links;
  (7) `transform: none !important` — TradingView translate3d ticker-tape
  collapse;
  (8) **iterative `calc()`/`var()` strip** — workaround weasyprint
  `NumberToken` upstream bug на Material 3 / GM3-prefixed CSS (Gmail
  no longer crashes).
  103/103 unit-тестов зелёные после всех фиксов.

---

## 2. Бэклог по скиллам

### docx

| ID | Название | Что/Зачем | Effort | Value | Dep | Notes |
|---|---|---|---|---|---|---|
| docx-1 | `docx_add_comment.py` ✅ DONE (VDD-hardened) | CLI вставляет `<w:comment>` с автором/датой/инициалами через `office.unpack` + lxml. Подбирает next id по `max(<w:comment w:id>)+1`, оборачивает якорь в `<w:commentRangeStart>`/`<w:commentRangeEnd>`/`<w:commentReference>`, патчит `[Content_Types].xml` Override + `_rels` Relationship. Поддерживает `--all` (intra-paragraph multi-match: `_wrap_anchors_in_paragraph` сканирует все вхождения в одном run за один проход через `text.find` cursor-loop, без re-match infinite-loop), unicode/кириллицу, run-merge перед поиском (handles Word's split runs). Anchor not found → exit 2 с `AnchorNotFound` envelope. Same-path I/O → exit 6 `SelfOverwriteRefused` (cross-7 H1 parity, ловит и symlink через `Path.resolve()`). E2E: 8 проверок (basic + validate + comment XML + anchor markers + not-found envelope + --all multi-match + VDD-A intra-paragraph triple + default-mode-still-1 + VDD-B same-path). | M | M | — | Якорь должен помещаться в один `<w:t>` после run-merge — формат-границы не пересекаем (документировано в docstring); cross-3 fail-fast на encrypted; cross-4 macro warning. |
| docx-2 | `docx_merge.py` ✅ DONE (VDD iter-2.0..2.3) | Склеивает N `.docx` в первый (base) через `office.unpack` + body-children-копирование с insert-before-sectPr. **iter-2 (real-world)**: реальные Word-документы вскрыли ряд багов — итеративно зафиксил каждый. **2.0 reloc passes**: copies `extra/word/media/*` с уникальным префиксом `extra<i>_`; appends image / hyperlink / chart / OLE / diagram relationships в `document.xml.rels` со сдвигом rId; remap'ит `r:embed`/`r:link`/`r:id`/diagram refs в extra body через id-map; bumps numeric `<w:bookmarkStart/End w:id>` на `max_base + 1` (избегает Word'овской диагностики "couldn't read content"); merge'ит `<w:abstractNum>` + `<w:num>` из numbering.xml со сдвигом abstractNumId/numId, переписывает `<w:numId w:val>` в extra body. **2.1 Content_Types**: тащит недостающие `<Default Extension>` из extra'шного `[Content_Types].xml` (без `Default Extension="png"` Word отказывается читать PNG). **2.2 sectPr strip**: удаляет paragraph-level `<w:sectPr>` из extra body — иначе их `<w:headerReference>`/`<w:footerReference>` (refs к header/footer parts которые мы не мерджим) резолвятся к base'овским rId с другим content-type. **2.3 schema order**: вставляет новые `<w:abstractNum>` ПЕРЕД первым `<w:num>` (ECMA-376 §17.9.20: все abstractNum должны идти до nums) — иначе Word делает auto-repair при открытии и иногда теряет binding base'овых list refs (наблюдалось: heading'и base'а внезапно превращались в bulleted "o" markers). Опц. `--page-break-between` / `--no-merge-styles` сохранены. Honest scope (всё ещё не мерджим): footnotes / endnotes / headers / footers / comments — warning только если в extra реально есть user content. Same-path I/O (output совпадает с любым input, incl symlink) → exit 6 `SelfOverwriteRefused`. E2E: 8 проверок iter-1 + ручная верификация iter-2 на реальных файлах (Change Management Process + Test_2 + ELMA365 3CX). | M | M | — | Аналог `pdf_merge`, но через body-tree concat вместо PDF-page concat. iter-2 показал что реальные Word-документы значительно сложнее md2docx-fixtures: real-world testing загнал в `_strip_paragraph_section_breaks` + `_merge_content_types_defaults` + schema-correct insert. |
| docx-3 | `html2docx.js` ✅ DONE (XL: VDD iter-1..4 + adversarial round + 4 фикс-раунда на реальной battery) | CLI читает три формата браузерных сохранений и склеивает их в `.docx`: (a) plain `.html`/`.htm` (и Chrome "Save Page As, Webpage Complete" с сиблингом `<page>_files/`), (b) Safari `.webarchive` (Apple binary plist через `bplist-parser`: `WebMainResource` → main HTML; `WebSubresources` image/* → tmp-dir; URL → local-path map с двумя ключами), (c) Chrome `.mhtml`/`.mht` (RFC 822/2557 multipart/related). Format-detection по расширению + magic-byte fallback (`bplist00`). **--reader-mode**: альтернативный article-extraction для article-only сайтов (vc.ru, Habr, Medium) — выбирает `<main>` вместо первой попавшейся секции, режет inline-промо-виджеты внутри `.entry`/`<article>`. **Tier-2 SVG renderer** (`_html2docx_svg_render.js`, 402 LOC): two-tier rasterization — headless Chrome (нативный foreignObject) → resvg-js fallback с pre-flight санитизацией (xlink namespace inject, named-entity decode, foreignObject→`<text>` конверсия, CSS color-function resolution для drawio-диаграмм). **Preprocessing pipeline** (855 LOC `html2docx.js`, ~250 LOC чисто preprocessing): chrome-button strip (Confluence DC `[class*="buttonContainer"]`, Sphinx `.headerlink`, GitBook `button[aria-label^="Copy "]`, Mintlify `data-testid="copy-code-button"`), SVG-icon strip (8 правил: aria-hidden, fa-prefix, attr/Tailwind/style/viewBox-size, GitBook `gb-icon`, FontAwesome-7 mask-pattern), ARIA-table conversion (`role="table/row/cell"` → `<table>/<tr>/<td>`), Mintlify Steps flatten (role=list+listitem с step-title → `<h4>N. Title</h4>` + content, не `<ol>` потому что walker.emitList сжимает блочный код в inline), Confluence DC code-wrap (`code[class*="language-"]` без `<pre>` → wrap), inline-ancestor hoist (Confluence DC `<span data-code-lang>` → unwrap чтобы walker дошёл до emitPre), shiki/Fern table-based code flatten (gated по marker-классам), inactive Radix tab strip (`[role="tab"][aria-selected="false"]`), `print:hidden` Tailwind-strip, `tableFloatingHeader`/`display:none` dedupe. **DOM walker** (1428 LOC `_html2docx_walker.js`): drawio-foreignObject conversion с edge-label backdrop, vertical alignment по align-items, word-wrap по container width, image-type magic-byte fallback (WebP support). Cross-7 H1 same-path guard. Cross-5 `--json-errors` envelope. E2E: 6 базовых + 12 reader-mode проверок. Verified на 19 реальных fixtures (.html, .mhtml, .webarchive из Confluence/GitBook/Fern/Mintlify/vc.ru/Habr/Discord) в обоих режимах — 19/19 OK. | XL | M | — | Прямой обход DOM (cheerio + docx-js). Honest scope: `style=""` / CSS classes игнорируются (есть только targeted preprocessing), `rowspan`/`colspan` не воспроизводятся, walker.emitList сжимает блочный код в inline (compensated через Mintlify-Steps flatten), нет JS unit-тестов на preprocessing (gap: см. q-7 ниже). |
| docx-4 | Сохранение комментариев и track-changes при docx2md ✅ DONE | `docx2md.js` пишет JSON-сайдкар `<base>.docx2md.json` (schema `v:1`) с двумя массивами: `comments[]` (id, paraId, parentParaId для thread linkage из `commentsExtended.xml`, author, initials, date, text, anchorText + 40-char anchorTextBefore/After для locator-стабильности при дубликатах, paragraphIndex по document order) и `revisions[]` (`<w:ins>`/`<w:del>` с author/date/text/paragraphIndex/runIndex). Поле `unsupported` считает revision-типы, отложенные в v2 (rPrChange, pPrChange, moveFrom, moveTo, cellIns, cellDel) — пользователь видит, что было потеряно (honest scope). Сортировка по document order. Sidecar **не пишется**, если comments=[] И revisions=[] И все unsupported=0 (clean docs остаются чистыми). Парсинг через cheerio xmlMode (уже в deps). Опции: `--metadata-json PATH`, `--no-metadata`, `--json-errors` (cross-5 envelope). Реализация: новый модуль `docx2md/_metadata.js` (~330 LOC, docx-only — `office/` не трогаем). E2E: 4 проверки (clean→no sidecar, comment + schema, ins/del + paraIdx/runIdx, --no-metadata + --metadata-json + --json-errors envelope). | L | M | — | Используется для аудита договоров. Sidecar-only — markdown не загрязняется inline-маркерами; locator (paragraphIndex + anchorTextBefore/After) даёт стабильную адресацию. |
| docx-5 | Footnotes / endnotes в markdown ✅ DONE | `docx2md.js` конвертирует `<w:footnoteReference>`/`<w:endnoteReference>` в pandoc-style `[^fn-N]` / `[^en-N]` markers с definitions block в конце документа. Реализация: pre-mammoth pass через `_metadata.injectFootnoteSentinels` подменяет references на ⟦FN:N⟧ / ⟦EN:N⟧ (CJK punctuation U+27E6/U+27E7 — markdown их не интерпретирует, turndown сохраняет дословно; верифицировано спайком на Test_2.docx). Параллельно вычищается user-content из `word/footnotes.xml`/`endnotes.xml` (boilerplate w:type="separator"/"continuationSeparator"/"continuationNotice" сохраняются), чтобы заглушить mammoth'овский `<ol class="footnotes">` (иначе после turndown — дубль определений). После mammoth → buffer вместо path (`mammoth.convertToHtml({buffer: modBuf})`). Post-pass `restoreFootnoteSentinels` подменяет ⟦FN:N⟧→`[^fn-N]` и аппендит `[^fn-N]: footnote text...` в конец. Опции: `--no-footnotes` для отказа от конвертации (поведение как до docx-5). E2E: 4 проверки (markers in body, definitions appended, --no-footnotes skips). Honest scope: footnote text — flat plain text (formatting flatten'ится). | M | L | — | Boilerplate (separator/continuationSeparator/continuationNotice) фильтруется как Word'овский artifact, не user content. |

### pptx

| ID | Название | Что/Зачем | Effort | Value | Dep | Notes |
|---|---|---|---|---|---|---|
| pptx-1 | `pptx_clean.py` ✅ DONE | Удалить осиротевшие slides/media/charts/themes из PPTX через BFS по графу `.rels`. Опционально `--dry-run`. Содержит обновление `[Content_Types].xml`. E2E: 4 проверки. | M | M | — | Своя реализация по ECMA-376 / OOXML §10. |
| pptx-2 | `pptx_apply_theme.py` | Сменить тему/палитру/шрифты целиком. Часто нужно для «привести презентацию из template-1 в брендинг template-2». | L | M | pptx-1 | Сложно: переносить layout-mappings + theme.xml + slideMasters. |
| pptx-3 | `outline2pptx.js` ✅ DONE | Markdown-outline (только заголовки) → каркас презентации с пустыми слайдами. `#` → title slide; `##` → content slide с placeholder; `###+` → bullets. Использует pptxgenjs, валидируется через office.validate. E2E: 4 проверки. | S | L | — | Реализован как .js (для использования pptxgenjs без bridge). |
| pptx-4 | XSD-валидаторы для pptx ✅ DONE | `office/validators/pptx.py` теперь делает структурно-семантическую проверку: slide-chain через presentation.xml.rels, layout/master-цепочка для каждого слайда, media-references (`<a:blip r:embed>`, `<p:videoFile r:link>`) к существующим частям, notes-slide reciprocity, sldId rules (uniqueness + ECMA-376 §19.2.1.34 диапазон 256-2147483647), orphan slides. XSD-binding (pml.xsd) подхватывается автоматически для каждого slideN/slideLayoutN/slideMasterN при наличии schemas (run `office/schemas/fetch.sh`). 9 unit-тестов в `office/tests/test_pptx_validator.py` + 4 E2E в pptx skill. | L | M | — | Полезно после ручных правок XML. |
| pptx-5 | Presenter notes export | При pptx2md выгружать заметки докладчика отдельным разделом (или сайдкар). | S | L | — | Покрывает use-case: репетировать с notes отдельно. |

### xlsx

| ID | Название | Что/Зачем | Effort | Value | Dep | Notes |
|---|---|---|---|---|---|---|
| xlsx-1 | `xlsx_add_chart.py` ✅ DONE | bar/line/pie на диапазоне, опц. `--categories` / `--title` / `--anchor`. E2E: 4 проверки (3 типа + bad-range). | M | H | — | openpyxl chart API; chart остаётся редактируемым в Excel/LO. |
| xlsx-2 | `json2xlsx.py` | JSON-array → лист с авто-detection типов колонок. Параллель к csv2xlsx. | S | M | — | Несколько строк на pandas. |
| xlsx-3 | `md_tables2xlsx.py` | Извлечь все markdown-таблицы из .md и положить каждую на отдельный лист. | S | L | — | Use-case: вытащить таблицы из тех. документации в excel. |
| xlsx-4 | Сохранение charts и data-validation при unpack/pack | Если пользователь пакует обратно файл с исходными chart-объектами, они должны остаться. Сейчас, возможно, теряются. | M | M | — | Нужно проверить — требует тестирования на реальных моделях. |
| xlsx-5 | XSD-валидаторы для xlsx ✅ DONE | `office/validators/xlsx.py` теперь делает структурно-семантическую проверку: sheet-chain через workbook.xml.rels, sheet name + sheetId + r:id uniqueness (Excel hard-fail при дубликатах), definedName uniqueness в каждом scope, **shared-string index bounds** (`<c t="s">` не выходит за `<si>` count в `xl/sharedStrings.xml`), **cell-style index bounds** (`<c s="N">` не выходит за cellXfs count в `xl/styles.xml`), orphan worksheets. XSD-binding (sml.xsd) подхватывается автоматически для sharedStrings/styles/sheetN при наличии schemas. 9 unit-тестов в `office/tests/test_xlsx_validator.py` + 3 E2E в xlsx skill. | L | M | — | Аналогично pptx-4. |
| xlsx-6 | `xlsx_add_comment.py` | Паритет с docx-1: вставить Excel-comment в указанную ячейку через `office/unpack` + lxml. Создаёт/дополняет `xl/commentsN.xml` (legacy `<comments>/<authors>/<commentList>`, где **N — part-counter**: следующий свободный индекс в `[Content_Types].xml`, НЕ привязан к sheet-index — workbook с тремя sheet'ами где только Sheet3 имеет комменты хранит их в `xl/comments1.xml`; binding к sheet идёт через `xl/_rels/sheetS.xml.rels` Relationship, не через name-collision) и опц. `xl/threadedCommentsM.xml` + `xl/persons/personList.xml` (modern threaded для Excel 365 — без personList Excel не отрендерит thread, **обязательная часть pipeline**). **personList synthetic person attributes** (стабильные через runs): `<person displayName="<author>" id="{UUIDv5(NAMESPACE_URL, displayName)}" userId="<author lowercase>" providerId="None"/>` — `providerId="None"` означает no-SSO, избегает Excel'овского "unknown user" warning. Auth flow: один `<person>` per unique author across the batch. Патчит `[Content_Types].xml` Override + `xl/_rels/sheetS.xml.rels` Relationship для commentsN, добавляет VML-shape в `xl/drawings/vmlDrawingK.xml` (K — тоже part-counter, не sheet-index; binding через ту же sheet rels). Без VML Excel не показывает hover-bubble. **Cell-syntax**: `--cell A5` (default sheet — первый), `--cell Sheet2!B5` (A1-style cross-sheet), `--cell 'Q1 2026'!A1` (quoted sheet-name с apostrophe-escape `''`). Аргументы: `--author "Agent" --text "..."` для одного, `--batch JSON` для пачки. **`--batch` принимает две формы** (auto-detect по JSON root type): (1) flat-array `[{cell, author, text, [initials], [threaded]}, ...]` для bespoke-скриптов; (2) **xlsx-7 findings envelope** `{ok, summary, findings: [...]}` напрямую из `xlsx_check_rules.py --json`. Во второй форме xlsx-6 распаковывает `.findings[]`, мапит `cell ← findings[i].cell`, `text ← findings[i].message`, `author ← --default-author` (required при envelope-shape), `initials` derived из `--default-author` (first letter of each token), `threaded ← --default-threaded` (default false). **Group-findings** (с `row: null`) автоматически skip'аются — нет single-anchor cell; counted в `summary.skipped_grouped`. Anything else → exit 2 `InvalidBatchInput`. Авто-подбор `<comment ref>` + shape-ID + `o:idmap` (no collisions с existing). Authors deduplicate в `<authors>` list; initials auto-derived если не заданы. Дубликаты на одну ячейку → append в existing thread (modern) или fail (legacy, `--legacy-only`). Merged-cell target — default fail-fast `MergedCellTarget` envelope (т.к. comment к non-anchor cell отрисовывается с visual offset, что обычно баг). Opt-out: `--allow-merged-target` → авто-redirect к anchor cell merged-range (mirrors xlsx-7 §4.4 merge-resolution pattern, emits info `MergedCellRedirect`). Same-path I/O → exit 6 `SelfOverwriteRefused` (cross-7 H1 parity, follows symlinks). Cross-3 fail-fast на encrypted; cross-4 macro warning; cross-5 `--json-errors` envelope. **E2E (≥ 9)**: clean-no-comments (creates comments/vml/rels/CT) + existing-legacy preserve (3rd added; original 2 untouched) + threaded mode (personList updated; thread linkage) + multi-sheet (Sheet2!B5 — fixture asserts что commentsN binds к Sheet2 через `xl/_rels/sheet2.xml.rels` Relationship, NOT что N==2; на свежем workbook'е N=1 если только Sheet2 имеет комменты) + merged-cell-target → MergedCellTarget envelope + batch-50 (no shape-ID collisions) + apostrophe-sheet (`'Bob''s Sheet'!A1`) + same-path → exit 6 + encrypted → exit 3 + macro `.xlsm` preserves macros + warns. **Honest scope (v1)**: (a) reply-threads — `parentId` не выставляется, каждый top-level; (b) rich-text formatting в теле — plain text; (c) drawing-positioning — дефолтный VML, без custom anchor offsets; (d) **Excel 365 round-trip mutation** — Excel может молча конвертировать legacy → threaded на save, поэтому goldens = agent-output-only, никогда Excel-touched. | M | M | — | Самый заметный пробел в xlsx после `docx_add_comment.py`. Use-case: validation-агент (xlsx-7 pipe) расставляет замечания на проблемные ячейки timesheet/budget/CRM-export. **Adversarial review закрыт** (см. xlsx-rules-format.md §13.2 cross-ref): A1-style cross-sheet syntax + personList obligatory + Excel-365 silent-upgrade в honest-scope. |
| xlsx-7 | `xlsx_check_rules.py` | Декларативная бизнес-валидация — **полный rules-format spec** в [`skills/xlsx/references/xlsx-rules-format.md`](../skills/xlsx/references/xlsx-rules-format.md) (после VDD-adversarial review v2: 12 секций + §13 regression battery с 39 фикстурами + 10 canary-saboteurs). **Effort M→L** после adversarial pass. **Краткая суть**: `--rules rules.json|.yaml` с правилами `{id, scope, check, severity, message}`. Scope-формы: `cell:`/`A1:B10`/`col:HEADER`/`col:LETTER`/`cols:LIST`/`row:N`/`sheet:NAME`/`named:NAME`/`table:NAME[COL]` с поддержкой A1-style sheet-qualifier (`'Q1 2026'!col:Hours`, apostrophe-escape `''`). Check vocab: comparisons (==/!=/<=/<…) + `between`/`between_excl` + `in [list]` + type guards (`is_number`/`is_date`/`is_text`/`is_bool`/`is_error`/`required`) + text (`regex:`/`len`/`starts_with:`/`ends_with:`) + dates (`date_in_month:`/`date_in_range:`/`date_before:`/`date_after:`/`date_weekday:`) + cross-cell aggregates (`sum`/`avg`/`min`/`max`/`median`/`stdev`/`count*` через scope-arg, cross-sheet OK) + group-by (`sum_by:KEY OP X`) + composite (`and`/`or`/`not`, depth ≤ 16). **Hand-written parser** (NOT `ast.parse`), closed AST из 17 node-типов (§6.1). **Excel Tables auto-detect** (§4.3): `col:Hours` резолвится через `xl/tables/tableN.xml` если cell внутри Table. **Type model** (§3.5): 6 logical types, error-cells auto-emit `cell-error` finding и suppress остальные правила; mixed-types в aggregates skip non-numeric (или fail с `--strict-aggregates`). **Adversarial защиты** (§2.1, §5.3.1, §6): YAML billion-laughs reject через lexer pre-scan `&`/`*`, ruamel.yaml v1.2 (no `yes/no` boolean coercion, no custom tags, no dup-keys); rules-file size cap 1 MiB; regex DoS — `regex` library с per-cell timeout 100 ms + redos-detector lint at parse; composite depth cap 16; format-string injection — `string.Template` (`$value`) NOT `str.format`. **Output JSON** (§7): summary с `errors/warnings/info/checked_cells/cell_errors/skipped_in_aggregates/regex_timeouts/eval_errors/elapsed_seconds/truncated`; findings sorted `(sheet, row, column, rule_id)` deterministic. **CLI** (§8, ≥ 22 flags): `--max-findings N` (default 1000) + `--summarize-after N` для catastrophic-input cases; `--strict-aggregates`, `--treat-numeric-as-date COLS`, `--include-hidden`/`--visible-only`, `--no-strip-whitespace`, `--no-table-autodetect`, `--remark-column-mode replace\|append\|new` (default `new` → preserves existing user data via `_2` suffix), `--streaming-output` для ≥ 100K cells (read-write fidelity trade-offs documented), `--require-data` для CI gates, `--timeout SECONDS` (default 300). Exit-codes: 0/1/2/3/4/5/6/7. Cross-3/4/5/7 параллель с другими readers. **E2E** (см. spec §13.1, ≥ 39): layout & schema variance (×9, incl. `MergedHeaderUnsupported`/`AmbiguousHeader`/`HeaderNotFound` envelopes) + type & error edges (×8, incl. errors-as-values auto-emit, mixed-types policy, stale-cache warning, localized RU dates, whitespace) + cross-sheet & aggregates (×4, incl. cache hit perf) + adversarial/DoS (×9, all reject ≤ 100 ms: regex-DoS, billion-laughs, custom-tag, yaml11-bool-trap, dup-keys, deep-composite, huge-rules, format-string-injection, unknown-builtin) + scale & perf (×3, **100K rows × 10 rules ≤ 30s/500MB committed**) + output mode (×6, incl. round-trip preserve, same-path exit 6, full pipeline xlsx-6 integration). **Canary** (§13.3): 10 saboteurs through `tests/canary_check.sh` ловит permanently-broken battery. | L | M | xlsx-6 | Закрывает «timesheet/budget review» сценарий полностью: validation + замечания + новый файл. **VDD-adversarial closed** на дизайн-ревью: 6 HIGH (YAML DoS, regex DoS, openpyxl read/write split, Excel Tables, multi-row headers, `is_date` localization) + 12 MED + 9 LOW все адресованы в spec. **Effort M→L** — параллельно с docx-1 (анкорная вставка через unpack/lxml), но parser+evaluator+caching+streaming-output добавляют ~600 LOC поверх. |

### pdf

| ID | Название | Что/Зачем | Effort | Value | Dep | Notes |
|---|---|---|---|---|---|---|
| pdf-1 | `pdf_fill_form.py` ✅ DONE | Заполнить AcroForm (fillable-поля) из JSON. Описан в `references/forms.md`. | M | H | — | pypdf, XFA fail-fast (exit 2), no-form fail (exit 3), `--check`/`--extract-fields`/`--flatten`. E2E тесты в `tests/test_e2e.sh`. |
| pdf-2 | `pdf_watermark.py` ✅ DONE | CLI накладывает text- или image-watermark на каждую (или выбранные через `--pages "1-5,8"`) страницу PDF. Реализация: reportlab `canvas.Canvas` рисует overlay с `setFillAlpha(opacity)` + поворот через `translate/rotate` (диагональ авто-rotation 45°), pypdf `page.merge_page` объединяет с исходником. Per-mediabox кеш overlay'ев — гетерогенные деки (Letter+A4 в одном файле) сохраняют корректные пропорции. Mutex-группа `--text` / `--image` (один обязателен). Опции: `--position center|top-left|top-right|bottom-left|bottom-right|diagonal` (default diagonal), `--opacity 0.0..1.0` (default 0.3), `--rotation`, `--font-size`, `--color`, `--scale` (image-only). Cross-7 H1 same-path guard (exit 6 `SelfOverwriteRefused`, ловит symlinks через `Path.resolve()`) — впервые в pdf-скиллах, новые CLI устанавливают конвенцию. Cross-5 `--json-errors` envelope. E2E: 7 проверок (text round-trip + текст-extract `DRAFT` через pypdf, image-watermark, page-count preserved, same-path guard, mutex required+exclusive, `--pages "1"` selectivity на 2-страничном PDF). Visual golden `watermarked-text.png`. | S | M | — | pypdf + reportlab уже в `requirements.txt`. Honest scope: image masks через `mask='auto'` (PNG alpha), `--rotation` rotates стамп вокруг anchor (translate→rotate→drawCentredString паттерн). |
| pdf-3 | `pdf_compress.py` | Снизить вес PDF: пересжать встроенные изображения, убрать дубли. | M | M | — | gs (ghostscript) делает это лучше — обёртка вокруг него. |
| pdf-4 | `pdf_ocr.py` | OCR scanned PDF через `tesseract` или `ocrmypdf`. Нужно для legacy-документов. | M | M | — | Системная зависимость на tesseract. |
| pdf-5 | `html2pdf.py` ✅ DONE (XXL: VDD iter-1..7 + per-iter adversarial review + 4-tier regression battery) | Универсальный HTML→PDF конвертер через weasyprint — для BI-дашбордов, Confluence-страниц, сохранённых веб-страниц. **Архитектура**: 194 LOC CLI + 1899 LOC в `html2pdf_lib/` (7 модулей: `archives.py` 202, `dom_utils.py` 145, `normalize_css.py` 243, `preprocess.py` 948, `reader_mode.py` 220, `render.py` 139, `__init__.py` 22). Поддерживает три input-формата: `.html`/`.htm` (plain), `.mhtml`/`.mht` (MIME-архив, browser «Save as → Single File»), `.webarchive` (Apple Safari). Для MHTML/WebArchive sub-resources извлекаются в tempdir, URL переписываются на локальные пути. **Preprocessing-pipeline** (`preprocess.py`, 948 LOC): `_fix_light_dark()` — O(n) depth-counter замена `light-dark(X, Y)` → `X`; **drawio foreignObject→`<text>` конвертер** с align-items vertical anchoring, edge-label backdrop через `<rect>` (обход стрелок поверх лейблов), модерн-color whitelist (rgba/hsl/hsla/oklch/oklab + named), variable resolution и `!important` strip; универсальный chrome strip (анкор-маркеры, copy-buttons, fixed nav bars); icon-SVG strip (8 правил, mirrors html2docx); ARIA-table conversion (`role="table"` → semantic `<table>` через CSS); Mintlify Steps; Confluence DC code-wrap. **`normalize_css.py`** (243 LOC): 16+ rule блок CSS-injection в `<head>` — `body{overflow:clip}` reset (SPA), `.drawio-macro svg` overflow fix, code-block wrap для Prism/Confluence DC (`code[class*="language-"]`), `pre`-table flatten гейты. **`reader_mode.py`** (220 LOC): article-extraction для blog-сайтов с приоритезацией `<article>`/`<main>`/`[role="main"]` + heuristic min-text=500 для Confluence. **`render.py`** (139 LOC): weasyprint render с `<foreignobject>` casing fix, font-fallback для Cyrillic SVG glyphs. Опции: `--page-size letter\|a4\|legal`, `--css EXTRA.css`, `--base-url DIR`, `--no-default-css`, `--reader-mode`. **Тесты**: `test_preprocess.py` (~1100 LOC, **67 unit-тестов** после VDD-A2 итерации: 14 fo→text + 11 normalize-css guards (incl. §7d Confluence chrome strip + §4a `<main>` layout-offset reset, оба с anchored active-rule regex и negative-regression guards) + 6 `_parse_label_bg` CSS-wide-keyword deny-list тестов + 2 e2e fill=initial leak guards + остальные на edge-cases), `test_battery.py` (315 LOC) + `battery_signatures.json` (31 fixture × 2 modes = 62 регрессий с tolerance bands ±5% pages, ±10% size + required_needles per platform: Confluence/GitBook/Mintlify/Fern/vc.ru/Habr/Discord). E2E: 9 проверок. Visual golden `html-basic.png`. | XXL | M | — | weasyprint, plistlib (stdlib), email (stdlib). VDD-история: iter-1 site-agnostic preprocessing, iter-2 table-based code flatten, iter-3 Mintlify icons + ARIA tables, iter-4 reader-mode, iter-5 (9 adversarial bugs), iter-6 (4-tier regression battery), iter-7 (11 issues). Затем drawio align-items fix, edge-label backdrop, code-block wrap. **VDD-A1 (2026-05-04)**: drawio `fill="initial"` → SVG black bar (расширен `_parse_label_bg` deny list — 6 CSS-wide keywords); Confluence Server chrome leak (action-menu / sidebar / page-tree / page-metadata banner) → §7d strip + §4a layout-offset reset на `<main>`. **VDD-A2 (2026-05-05)**: 9 adversarial findings — substring-`assertIn` тесты заменены на anchored active-rule regex; добавлены `test_main_layout_reset_present` + negative `test_no_horizontal_padding_reset_in_main_rule` (§4a больше не over-stripped horizontal padding на generic `#content`); ARIA-landmark + generic-ID over-strip trade-off задокументирован в §7d "Honest scope" подсекции; `TestNoFillInitialLeaksEndToEnd` defense-in-depth e2e тест прокатывает синтетический drawio через весь `preprocess_html()` pipeline. Honest scope: walker.emitList не recurses в block-level, `display:none` chrome видим только статически. |
| pdf-6 | Mermaid: dark-theme и custom config ✅ DONE | `--mermaid-config PATH` в md2pdf, прокидывается в `mmdc -c`. Cache key включает SHA1 контента конфига → смена темы / шрифта инвалидирует кеш PNG. Missing-path → warn + degrade (или fail в `--strict-mermaid`). E2E: 3 проверки. | S | L | mermaid done | Аналог в `md2pptx.js`: `--mermaid-config` / `--no-mermaid-config`. |
| pdf-7 | TOC bookmarks (PDF outline) | weasyprint умеет: добавить `<h1-h6>` → PDF outline. Уже из коробки или нужен CSS-флаг? Проверить и при необходимости добавить. | S | M | — | Сейчас только in-page links. |
| pdf-8 | Универсальная subframe-aware extraction для webarchive/MHTML ✅ DONE | Webarchive (Safari `.webarchive`) и MHTML (Chrome `.mhtml`) сохраняют SPA-shell в main HTML, а реальный контент (письма, embedded-документы, sandboxed widgets) — во inner-frame'ах: `WebSubframeArchives[i]` (webarchive) или CID-referenced multipart parts (MHTML). Сейчас [`html2pdf_lib/archives.py:150`](../skills/pdf/scripts/html2pdf_lib/archives.py#L150) `extract_webarchive` читает только `WebMainResource`; `extract_mhtml` аналогично — обе игнорируют inner-frame'ы. **Универсальный подход без vendor allow-list**: <br>**(1)** Format-agnostic флаг `--archive-frame N\|main\|all\|auto` применяется к обоим экстракторам (`.webarchive` И `.mhtml`): `N` (1-indexed) — один inner-frame; `main` — только main HTML (текущий default, явный); `all` — concat всех «substantial» frame'ов через `<hr><h2>Frame N</h2>` (флэт, без metadata-pulling в v1, см. honest scope); `auto` — детерминистическая ветвь: 0 substantial → main, 1 → frame 1, 2+ → all. <br>**(2)** **«Substantial» — чисто структурная эвристика, ZERO vendor allow-list**: HTML ≥ 1 KB **AND** zero `<script>` tags **AND** body plain-text ≥ 100 chars **AND** не single-`<img>`-only body (отсекает sendgrid/mail.ru open-pixel iframes). Никаких упоминаний `elma365-message-body`, `gmail_*`, `data-message-id` в коде — эвристика обязана работать на Gmail/Outlook Web/Yandex/ProtonMail/Bitrix24/любой неизвестный SPA без правок. Verified против трёх фикстур: `test_email_elma365.webarchive` (1/1 substantial), `email_list_client.webarchive` (7/7), `elma365_activities_example.webarchive` (0/0). <br>**(3)** `--list-frames` — печатает каждый frame: index/URL/byte-count/`script-count`/`plain-text-len`/`substantial:bool`, exit 0. Без рендера. Пользователь детерминистически выбирает `N`. <br>**(4)** **Per-frame namespace + sha1 image-dedup**: `tempdir/frame_N/`; identical image-bytes (sha1) → один физический файл, multiple url_map entries указывают на него (общие signature-логотипы / чейн-аттачменты). <br>**(5)** **Encoding parity**: subframes уважают свой `WebResourceTextEncodingName`; MHTML parts уважают per-part `Content-Transfer-Encoding` + `charset=`. Fallback `utf-8` `errors='replace'`. Закрывает legacy windows-1251/koi8-r/gb2312 emails. <br>**(6)** **Honest scope (v1)**: (a) **No metadata-pulling** в `all`-режиме — заголовки flat `<h2>Frame N</h2>`, без subject/from/date; универсальный алгоритм извлечения metadata из main DOM рядом с iframe-плейсхолдером не специфицирован, отложено в pdf-8a. (b) **Top-level frames only** — nested webarchive/MHTML subframes (forwarded email с tracking iframe) не recursed, документировано. (c) `--archive-frame main` оставляет `<iframe src="…">` плейсхолдеры в DOM как пустые рамки — не auto-strip'аем (пользователь явно выбрал main). <br>**(7)** Зеркалить в html2docx (`_html2docx_archive.js`), функциональный паритет, byte-equivalence не требуется. <br>**E2E (≥ 7)**: `--archive-frame 1` на ELMA365-email-fixture (1 subframe, body + images); `--archive-frame all` на ELMA365-email-list-fixture (7 sections + signature-needles Демидова/Ткачук/Александр Черных + image-dedup verified через ls в tempdir); `--archive-frame all` на ELMA365-activities-fixture (0 substantial) → exit ≠ 0 с `NoSubstantialFrames` envelope (fail-loud, NOT silent main fallback); `--archive-frame auto` на пяти фикстурах детерминистически: ELMA365-email→`1`, email-list→`all`, activities→`main`, **gmail_example→`main`** (5 субфреймов все non-substantial: Google One sidebar 18 scripts / Contacts hovercard 18 scripts / tiny system iframes — heuristic корректно отбрасывает Google chrome widgets), **sentora×2→`main`** (1 субфрейм framer.com/edit 9 scripts non-substantial); `--list-frames` на gmail_example → 5 строк, все substantial=false (валидирует script-count rule); encoding regression: synthetic webarchive с windows-1251 subframe → корректная Cyrillic-decoding. **Universality gate ✅ closed** через `tmp/gmail_example.webarchive` — реальный Google web-mail, 4.7 MB main HTML, 5 системных субфреймов, все non-substantial по структурной эвристике (script-count > 0). Convergence test пройден: heuristic работает на ELMA365 И Gmail без правок, NO `elma365-message-body`/`gmail_*` mention в коде. **Важный architectural insight для §6**: Gmail хранит тело письма INLINE в main DOM (`<div class="ii gt">` на offset 4.5 MB, окружён ARIA-landmarks `role="main\|navigation\|complementary\|banner"`), НЕ в субфреймах. Поэтому `auto` корректно выбирает `main`, и дальше pdf-9 (universal SPA-chrome strip) делает свою работу. **Iframe-sandboxed (ELMA365) и inline-DOM (Gmail) — два разных паттерна web-mail**, оба покрываются композицией pdf-8 + pdf-9 без vendor-знаний. | L | H | — (Dep закрыт фикстурой gmail_example) | Реальный пользовательский запрос: печать переписки из любого web-mail / sandboxed-content viewer без SPA-обвязки. **Effort S→M→L**: универсальная эвристика + MHTML parity + encoding + dedup + universality validation gate (закрыт). Не покрывает inline-DOM emails (Gmail-pattern) — это pdf-9 берёт через SPA-chrome strip. Не покрывает inline-SPA БЕЗ контентных iframe'ов (реестры) — pdf-9 + pdf-10. |
| pdf-9 | Универсальная SPA-chrome heuristic в reader-mode ✅ DONE | Existing [`html2pdf_lib/reader_mode.py`](../skills/pdf/scripts/html2pdf_lib/reader_mode.py) handles blog-class sites (Confluence/GitBook/Mintlify/Fern/vc.ru/Habr/Discord) но не извлекает контент из hydrated SPA chrome (любой CRM, ticketing, internal portal, monitoring-дашборд — heavy-shell-around-content single-page app, vendor-irrelevant). На `tmp/elma365_activities_example.webarchive` (1.67 MB hydrated Angular DOM) сейчас оставляет sidebar/banners. **Vendor-agnostic fix через стандарты, NOT через tag-allow-list**: <br>**(1) SPA-detection без framework-strings**: `<body>` HTML ≥ 50 KB **OR** ≥ 5 `<script src="…">` с total bundle ≥ 200 KB **OR** ≥ 3 ARIA-landmark elements. **Никаких** `<app-root ng-version=` / `data-reactroot` / `data-v-app` / Svelte/Solid markers — pure-React, Vue, Svelte, static SPA должны триггерить ту же ветку. <br>**(2) Chrome strip через стандарты**: всё с `role=navigation\|complementary\|banner\|contentinfo`; semantic landmarks `<aside>`, `<nav>`, `<header>` (depth ≤ 2 — чтобы не зарезать article-headings), `<footer>`. Toast/notification-containers по эвристике: inline `style=` `position:fixed` + viewport-corner + ≤ 200 chars text. Promo-banners по эвристике: содержит `[role="alert"]` **OR** `<button>` с текстом `/^(Закрыть\|Dismiss\|Close\|×)$/` **OR** icon-button + ≤ 200 chars text. **Запрещено** упоминать `app-sidebar-part`, `app-toast-notifications`, `app-desktop-banner` или любые vendor tag-names в коде — ELMA365 ОДНА из многих fixtures, не trigger condition. <br>**(3) Content root** — «largest contentful subtree»: пик потомка `<body>` (за вычетом stripped landmarks) с max(text-length × text-density). Fallback на `<main>` semantic если present и non-empty. <br>**(4) Auto-trigger**: existing `--reader-mode` flag; SPA-detection (1) выбирает SPA-chrome-path, иначе existing blog-platform path. Без явного `--reader-profile` (no per-vendor profiles, ever). <br>**(5) Universality validation gate ✅ closed** через 4 не-ELMA365 фикстуры в трёх «классах SPA»: <br>&nbsp;&nbsp;**(a) Rich-landmarks SPA** — `tmp/gmail_example.webarchive` (Google Closure-based web-mail, 4.7 MB main, ARIA `role="main\|navigation\|complementary\|banner"` все 4 присутствуют, `<div class="ii gt">` body на offset 4.5 MB) — convergence proven: ARIA-strip rules чисто отделяют содержимое письма. <br>&nbsp;&nbsp;**(b) Bundle-only SPA, semantic-light** — `tmp/The Number…Sentora.webarchive` + `tmp/Tether's…Sentora.webarchive` (Framer-built blogs, 316 KB main, ≥ 30 .js subresources триггерят SPA-detection через bundle-criterion, но ARIA-landmarks=0 и `<article>`/`<main>`=0; expected behaviour: SPA-detected, ARIA-strip ничего не находит, content-root fallback на «largest contentful subtree» правильно ловит article — потому что у Framer-сайта реально нет SPA chrome; output должен быть ≥ 95 % идентичен generic blog-platform pass без `--reader-mode`). <br>&nbsp;&nbsp;**(c) Landmark-free SPA, hostile case** — `tmp/ya_browser.webarchive` (Yandex Cloud Console marketplace page, 190 KB main, **ZERO ARIA landmarks, ZERO `<article>`/`<main>`/`<aside>`/`<nav>` semantic tags**, голый `<div>`-soup с CSS-классами `side-nav`/`marketplace-product`/`data-qa`). Это **самый жёсткий universal-case**: ни ARIA, ни semantic-якорей. Expected behaviour: SPA-detection триггерит через script-bundle criterion; ARIA-strip rules находят нечего; semantic-strip rules находят нечего; content-root падает на «largest contentful subtree by text-density» heuristic — best-effort, может включать sidebar-nav text в выходе. **Это honest scope, не bug**: heuristic gracefully degrades там, где автор страницы не дал якорей. <br>&nbsp;&nbsp;Convergence test пройден: 4 разных vendors / SPA frameworks работают без vendor-name-mention в коде. <br>**(6) Honest scope**: <br>&nbsp;&nbsp;(a) chrome-strip НЕ делает Angular-Material/ya-Console data-tables printable — pdf-10; <br>&nbsp;&nbsp;(b) **landmark-free SPAs (ya_browser-class)** — content-root heuristic best-effort, sidebar text может протекать. Если станет реальной проблемой, follow-up `pdf-9a` — soft class-name heuristic (`class="*sidebar*\|*nav*\|*menu*\|*header*\|*footer*"` strip) применяется ТОЛЬКО когда ARIA/semantic ничего не нашли. Не делается в pdf-9 v1: фуззи-matching рисует false-positives (например, `<div class="legal-sidebar">` который реально content). <br>**(7)** Зеркалить в html2docx (`_html2docx_preprocess.js`). <br>**E2E (≥ 7)**: ELMA365-activities без `--reader-mode` → sidebar/banner needles present; С `--reader-mode` → needles отсутствуют, content preserved; **gmail_example** с `--reader-mode` → email body (`<div class="ii gt">` content) preserved, `role="navigation"`-section dropped (Gmail rail), `role="complementary"`-section dropped (Gmail right pane), `role="banner"`-section dropped (Gmail toolbar); **sentora×2** с `--reader-mode` → article preserved, output ±5 % vs same fixture без `--reader-mode` (negative-regression: bundle-only-SPA шаблон не должен ломать blog-pass-through); **ya_browser** с `--reader-mode` → SPA-detection triggers через bundle-criterion, output **best-effort** (контракт: page-count finite + plain text contains "Яндекс Браузер для организаций"; tolerance не накладываем — known-degraded case); negative-regression на existing blog-platform fixtures (Confluence/GitBook/Mintlify/Fern/vc.ru/Habr/Discord) — output unchanged ±5 % page-count. | L | M | pdf-10 для «красиво» (Universality gate ✅ — фикстуры в репо) | **Effort M→L** (VDD-adversarial): universal SPA-chrome detection — hard class. **Value M (NOT H)** — chrome-strip alone не доставляет «красивый PDF» для data-heavy pages, это pdf-10. Convergence test пройден: 4 не-ELMA365 SPA-фикстуры (Gmail Closure / Framer ×2 / Yandex Cloud Console) обрабатываются без vendor-name в коде. **Дизайн признан universal только потому что есть hostile фикстура (ya_browser, ноль semantic-якорей) с задекларированным best-effort outcome — это и есть honest universality**, в отличие от «работает на трёх знакомых сайтах». |
| pdf-11 | Optional Chrome-headless engine via Playwright ✅ DONE (8 VDD-adversarial итераций; см. §1 «Что реально отгружено» — финальный pipeline + результаты + тесты) | weasyprint имеет hard limits на modern web SPA: (a) **CSS3 calc/var bugs** (Gmail-class: `'NumberToken' object has no attribute 'unit'` на Material 3 / GM3-prefixed CSS); (b) **infinite layout loops** на pathological flex/grid (Framer-built sites — Sentora ×2 в нашем corpus); (c) **inline-layout assertions** (ELMA365 activities-fixture, weasyprint inline.py:231 `tuple index out of range`); (d) **no JS execution** — SPAs которые гидрируют контент через JS показывают `(loading…)` final state; (e) **no `<canvas>` rendering** — TradingView/Recharts/Chart.js диаграммы рендерятся пустыми. Эти ограничения **не bugs в нашем коде**, а архитектурные пределы typeset-renderer'а. **Решение**: optional Chrome-headless engine через Playwright. **Дизайн opt-in, не replacement**: <br>**(1) CLI флаг** `--engine weasyprint\|chrome\|auto` (default: `weasyprint` — preserve existing behaviour, мин. install footprint). `chrome` — рендер через Playwright Chromium. `auto` — try weasyprint, fallback to chrome on render-fail / timeout / known-pathology marker. <br>**(2) Soft-optional dependency**: Playwright НЕ в основной `requirements.txt`. Отдельный `requirements-chrome.txt` (`playwright>=1.40`). При отсутствии — внятный exit 1 envelope: `EngineNotInstalled: install with: pip install -r requirements-chrome.txt && playwright install chromium`. **Pdf skill остаётся "независимо устанавливаемым"** (CLAUDE.md §"Независимость скиллов") — Chrome activation требует явного opt-in от пользователя. <br>**(3) Auto-detect эвристика для `auto`-mode**: pre-scan input HTML на маркеры известной weasyprint-pathology (vendor-agnostic, structural — не class-name allow-list): <br>&nbsp;&nbsp;(a) **calc-with-bare-numbers** count > 50 (Material/GM3-class CSS триггерит NumberToken bug); <br>&nbsp;&nbsp;(b) **`<canvas>` element count** > 0 (визуальные данные не отрендерятся в weasyprint); <br>&nbsp;&nbsp;(c) **virtualized-list markers** в DOM (`class*="virtual-list"`/`*virtualizer*` + fixed-height parent) — реестры >1000 строк weasyprint обрабатывает корректно по логике, но catastrophically медленно/ugly без table-flatten; <br>&nbsp;&nbsp;(d) **explicit `data-engine="chrome"` HTML annotation** — для testing / pinned overrides. <br>В `auto`-mode при ANY hit → use chrome. Эвристика не reads vendor names, только structural counts. <br>**(4) Render fallback chain в `auto`-mode**: try weasyprint with watchdog (current `HTML2PDF_TIMEOUT`); on `RenderTimeout` / known-bug exception → invoke chrome. Cache decision в side-car file (`<input>.engine.json`) для repeat runs — pdf-skill не должен крутить layout-loop повторно. <br>**(5) Cross-platform reality**: Playwright supports Win/Mac/Linux desktop **out of box** (bundled Chromium ~170 MB per OS). Frictions: (a) Linux Alpine/RHEL/Arch — `playwright install-deps` only handles Ubuntu/Debian, остальные дистрибутивы требуют ручную установку 30+ system packages (libnss3, libatk-bridge, libcups2, libxkbcommon0, libpango, libgbm1, ...); (b) Docker contianers — нужно `--cap-add=SYS_ADMIN` или Chromium `--no-sandbox` flag; (c) AWS Lambda / serverless — bundled Chromium (>250 MB) не вмещается в стандартный Lambda layer, нужен `chrome-aws-lambda` или `chromium-min`; (d) macOS Apple Silicon — ARM64 Chromium доступен, первый запуск unsigned binary требует `xattr -d com.apple.quarantine` (Playwright делает автоматом). **Honest scope**: "all platforms" = Win/Mac/Linux desktop ✓; "all environments" (Alpine, edge runtimes, Lambda) — нужны workarounds. iOS/Android NOT supported. <br>**(6) Cost trade-offs**: Install size +170 MB; first-render latency 3-5s (Chromium boot vs <1s weasyprint); per-page render 5-15s vs 0.5-2s; memory baseline 200-400 MB vs ~50 MB. Acceptance: chrome-engine **5-10× медленнее** weasyprint, оправдано только когда pages иначе не рендерятся ИЛИ enterprise-fidelity критична. <br>**(7) Honest scope (deferred to v2)**: (a) HTML→PDF только; не использовать Chromium для md→pdf path (mermaid + weasyprint композиция уже отлажена); (b) chrome не активен для md/markdown inputs — только для html/htm/webarchive/mhtml; (c) bundled-Chromium installer не входит в pdf-skill `install.sh` — explicit `playwright install chromium` step; (d) `--engine chrome` в html2docx — отдельный pdf-11a (Word output via Chromium = different rendering pipeline через `playwright .pdf()` + pandoc/mammoth). <br>**E2E (≥ 6)**: `--engine chrome` на gmail_example.webarchive (regular mode) → renders without crash, > 1 page, contains "Sentora" needle (vs current weasyprint NumberToken crash); `--engine chrome` на elma365_activities → renders with proper table layout (rows visually separated, не текстовая каша как сейчас в reader-mode); `--engine chrome` на ya_browser → renders matching screenshot 1 user reference (full Yandex Cloud Console layout с sidebar и pricing card); `--engine auto` на 29-fixture corpus → fallback срабатывает на 4 known-pathological (Sentora ×2, gmail, activities), остальные 25 рендерятся weasyprint (auto-detect не дёргает chrome бессмысленно); `--engine chrome` BUT playwright not installed → exit 1 with `EngineNotInstalled` envelope; cache file: повторный run на той же fixture → не перезапускает layout-loop check. **Universality validation**: ≥ 2 non-ELMA365 fixtures где chrome визуально превосходит weasyprint (gmail email body с brand colors, TradingView idea-page с canvas chart). | XL | H | pdf-9, pdf-10 | **Closes "enterprise-ready" gap**. Trade-off: 170 MB Chromium bundle + 5-10× latency для случаев когда weasyprint объективно не справляется. **Default остаётся weasyprint** — pdf-skill сохраняет lightweight install profile. Chrome — opt-in для high-fidelity нужд (corporate report rendering, email-newsletter capture, SPA full-state archival). Сравнение auto-detect эвристики vs vendor allow-list: эвристика структурная (calc-count, canvas-count, virtualizer-markers), без vendor-name в коде — universality preserved. |
| pdf-10 | Beautiful list-view / registry printing (table flatten + universal beauty CSS) ✅ DONE (v1, sibling-flatten + acceptance-checker отложены в pdf-10a) | После pdf-9 (chrome stripped) hydrated SPA registries (e.g. ELMA365 activities-fixture: 135 `<app-appview-card>` × 824 `<app-appview-list-field>` ≈ 18 800 deeply-nested empty/sparse cells, или Notion table export, или Airtable HTML export, или любая Angular-Material/Mantine/Chakra grid) рендерятся cramped, hundreds-of-pages, mid-row-broken. «Красивый PDF» требует flatten + beauty CSS pass. <br>**(1) Card/row flatten heuristic — purely structural, vendor-agnostic**: для subtree'ев где descendants имеют repeating shape (≥ N siblings с одинаковым tag + attribute pattern) — collapse в `<table>` / `<dl>` label/value pairs. Inputs — sibling-repetition pattern, не class-names. <br>**(2) Empty-cell suppression**: cells где все descendants — Angular-comments `<!---->` OR ноль non-whitespace text → drop column. Универсально для любого framework, не только Angular. <br>**(3) Universal beauty CSS injection** в [`html2pdf_lib/normalize_css.py`](../skills/pdf/scripts/html2pdf_lib/normalize_css.py) — применяется ко всем источникам, не только SPA: `min font-size: 9pt` (unscaling Tailwind/Material `text-xs` ниже порога); `tr { page-break-inside: avoid }`; `img, svg { max-width: 100%; height: auto }`; `table { table-layout: auto; word-break: break-word }`; `body { overflow-x: hidden }`; `widows/orphans: 2`. <br>**(4) Machine-checkable acceptance «красивый PDF»**: (a) ни одна PDF-страница не имеет horizontal content > viewport width (verified via pdftoppm + rightmost-pixel scan, tolerance 5px); (b) ни один `<tr>` не split across page-break (preflight check на `page-break-inside:avoid` attribute presence; runtime check через PDF text-extraction y-coordinate analysis); (c) min font-size ≥ 9pt (через PDF text-extraction: smallest detected); (d) sanity bound: page-count ≤ 3 × row-count / 50 (если 18 800 fields / 50 = 376 rows ⇒ ≤ 1 128 pages; превышение = layout broken). <br>**(5)** Зеркалить в html2docx (с Word-equivalents — `cantSplit` на rows, table-width, no overflow). <br>**E2E (≥ 4)**: activities-fixture с `--reader-mode` → ≤ 200 PDF pages (vs current 1000+ unflattened) **AND** все 4 acceptance bullets pass; ≥ 1 не-ELMA365 list-view fixture (Notion/Airtable/plain-`<table>` blog post) → acceptance pre-existing-pass (regression check, beauty rules не должны ломать уже-печатаемые таблицы); negative-regression на prose-heavy fixtures (Habr/Confluence) — beauty rules не деградируют prose-layout, ±5% page-count tolerance. | L | H | pdf-9, ≥ 1 non-ELMA365 list-view fixture | **Закрывает реальный «красивый PDF» loop** для data-heavy SPA-страниц. Без этого pdf-9 оставляет жалобу: «sidebar пропал, но реестр всё равно нечитаемый». Universal — flatten heuristic основан на sibling-repetition pattern (структурный), не на vendor tag-names. Beauty CSS — стандартные правила print-CSS, применимые универсально. |

---

## 3. Cross-cutting (затрагивают все 4 скилла)

| ID | Название | Что/Зачем | Effort | Value | Dep | Notes |
|---|---|---|---|---|---|---|
| cross-1 | `preview.py` универсальный ✅ DONE (VDD-hardened ×3) | Один CLI: на вход docx/pptx/xlsx/pdf — на выход PNG-grid. Байт-идентичен в 4 скиллах. `.pdf` идёт напрямую через pdftoppm; `.docx/.xlsx/.pptx` (вкл. `.docm/.xlsm/.pptm`) через soffice → pdftoppm. Флаги: `--cols/--dpi/--gap/--padding/--label-font-size` (validated lower bounds), `--soffice-timeout 240` (OOXML→PDF), `--pdftoppm-timeout 60` (PDF→JPEG). Output dir auto-mkdir; subprocess capture; PIL UnidentifiedImageError + OSError caught. E2E: 11+ проверок (включая VDD-регрессии). | M | M | pptx_thumbnails | Заменяет 4 разных способа «глянуть, как это выглядит». |
| cross-2 | LD_PRELOAD shim для sandbox-Linux | LibreOffice требует AF_UNIX, в sandboxes часто ломается. Уже есть `office/shim/lo_socket_shim.c` — нужно проверить, что собирается и работает на Linux-CI. | M | L | — | На macOS desktop не нужно — отложили. |
| cross-3 | Encrypted/password-protected files ✅ DONE | `office/_encryption.py` детектирует CFB-magic; 8 reader-скриптов вызывают `assert_not_encrypted()` рано и возвращают exit 3 + понятное сообщение. E2E: 3 проверки (по одной на skill). | S | M | — | Замена `BadZipFile: not a zip file` на «password-protected, decrypt upstream». |
| cross-4 | `.docm`/`.xlsm`/`.pptm` (с макросами) ✅ DONE (VDD-hardened ×3) | Read-only поддержка через `office/_macros.py`: `is_macro_enabled_file()` парсит `[Content_Types].xml` через defusedxml и проверяет `<Default>`/`<Override>` ContentType — content-type **authoritative**, stray `vbaProject.bin` без macro-CT не триггерит (фикс iter-2 HIGH-4); substring-match в комментариях не false-positive (iter-2 HIGH-3). Writers (docx_fill_template, docx_accept_changes, xlsx_recalc, xlsx_add_chart, pptx_clean) шлют warning через `format_macro_loss_warning()`; `office.pack` использует `format_pack_macro_loss_warning()` ("source tree contains vbaProject.bin" — pack работает с деревом, не с файлом, iter-3 LOW). E2E: false-positive guards (stray bin / substring), template-extension `.dotm→.dotx`, унифицированный warning helper. | S | L | — | Корпоративные пользователи иногда дают такие файлы. |
| cross-5 | Унифицированный error-reporting ✅ DONE (VDD-hardened ×3) | `scripts/_errors.py` (4-skill копия): `add_json_errors_argument(parser)` + `report_error(msg, code, error_type, details, json_mode)`. JSON envelope: `{"v":1,"error","code","type"?,"details"?}` — schema-versioned, single-line. `parser.error` обходит — argparse usage errors тоже идут через envelope (`type:"UsageError"`). `code=0` defensive coerce → 1 (с `details.coerced_from_zero`). Подключён во все 13 Python CLI. E2E: parameterized по всем 13 скриптам + регрессии (UsageError, v=1, code=0). | M | L | — | Полезно для обёрток-агентов. |
| cross-6 | Cyrillic font preset для mermaid ✅ DONE | `scripts/mermaid-config.json` с font-stack `Arial Unicode MS → Noto Sans → DejaVu Sans → Liberation Sans → Arial → sans-serif`. Подключается автоматически в md2pdf и md2pptx; пользователь переопределяет через `--mermaid-config`. | S | M | pdf-6 | Файл байт-идентичен в `skills/pdf/scripts/` и `skills/pptx/scripts/`. |
| cross-7 | Real password-protect (set/remove) ✅ DONE | `scripts/office_passwd.py` (3-skill копия, docx/xlsx/pptx; pdf использует pypdf). Три режима: `--encrypt PASSWORD`, `--decrypt PASSWORD`, `--check`. Реализация на msoffcrypto-tool 6.0+ (MS-OFB Agile, Office 2010+). Пароль можно подать как `-` → читается из stdin (избегает leak в `ps`/shell history). Exit-codes: 0 (ok / encrypted в `--check`), 1 (FileFormat/IO), 2 (argparse), 3 (msoffcrypto-tool не установлен), 4 (wrong password — output удалён, не остаётся 0-byte decoy), 5 (state mismatch: encrypt-on-encrypted / decrypt-on-clean), 10 (`--check`: not encrypted), 11 (input not found). Round-trip lossless (zip namelist совпадает). E2E: 11 проверок в каждом из 3 skills (33 итого). | M | M | — | msoffcrypto-tool 6.0 поддерживает и encrypt и decrypt; подключён через `--json-errors` envelope (cross-5 интеграция). |

---

## 4. Тесты и quality

| ID | Название | Что/Зачем | Effort | Value | Dep | Notes |
|---|---|---|---|---|---|---|
| q-1 | E2E тесты на fixtures ✅ DONE | Per-skill `scripts/tests/test_e2e.sh` + top-level orchestrator `tests/run_all_e2e.sh`. 31 проверка (8 docx + 7 pptx + 7 xlsx + 9 pdf), все зелёные. | M | H | — | Покрытие: round-trip md↔docx, csv→xlsx + recalc + validate, md→pptx + thumbnails + pdf, md→pdf + merge + split + fill_form + mermaid. |
| q-2 | Visual regression PDF ✅ DONE | `tests/visual/visual_compare.py` (pdftoppm → PNG → ImageMagick `compare -metric AE -fuzz 5%`) + `_visual_helper.sh` sourced by 4 E2E suites. 9 goldens committed at `tests/visual/goldens/<skill>/*.png`. Soft-skip on missing IM/golden by default; `STRICT_VISUAL=1` (CI) makes them hard failures. `UPDATE_GOLDENS=1 bash tests/run_all_e2e.sh` regenerates. | M | M | — | imagemagick + perceptual fuzz (not strict checksum) — absorbs cross-platform anti-alias drift. |
| q-3 | Покрытие mermaid edge-cases ✅ DONE | 5 fixtures под `skills/pdf/examples/`: `fixture-mermaid-{cyrillic,sequence,gantt,large-mindmap,broken}.md`. Extended pdf E2E: 6 проверок (4 ok-renders + `--strict-mermaid` exits non-zero on broken + lenient mode degrades with `mmdc failed` warning). Pptx parity: inline heredoc smoke check confirms md2pptx embeds mmdc PNG. `--base-url $TMP` keeps mermaid asset dirs out of `examples/`. | S | M | pdf-6 | Покрывает sequence/gantt/mindmap layout engines — ранее тестировался только flowchart. |
| q-4 | Ровный CI на 4 скиллах ✅ DONE | `.github/workflows/office-skills.yml`. Matrix per-skill (`install.sh` → `validate_skill.py` → `test_e2e.sh` со `STRICT_VISUAL=1`). Caches `.venv` + `node_modules`. `property` job runs hypothesis fuzz with `HYPOTHESIS_PROFILE=ci` (100 examples). `workflow_dispatch` с `update_goldens=true` регенерирует goldens и публикует артефактом. Path-filtered триггер. | M | M | q-1 | Использует tracked `skills/skill-creator/scripts/validate_skill.py`, не локальный `.claude/`. |
| q-5 | Property-based тесты ✅ DONE | `tests/property/` со своим `.venv`. Hypothesis-fuzz для `md2docx.js`, `md2pdf.py`, `csv2xlsx.py`: 30 примеров локально / 100 на CI. Стратегии в `strategies.py` (markdown_doc, csv_doc) генерируют unicode mix (latin/cyrillic/CJK + нумерации/таблицы). Контракт: либо exit 0 + non-empty output, либо exit ≠ 0 без Python traceback / node `node:internal` стека. Subprocess timeout 60s/example. | L | L | q-1 | Tempdir per-example через `tempfile.TemporaryDirectory` (pytest's `tmp_path` несовместим с `@given`). |
| q-6 | Регресс-battery для html2pdf ✅ DONE (pdf-5 iter-6) | `skills/pdf/scripts/tests/battery_signatures.json` — 31 fixture × 2 modes (regular + reader) = 62 регрессий с tolerance bands (`min/max_pages` ±5 %, `min/max_size_kb` ±10 %) + `required_needles` per-platform (Confluence/GitBook/Mintlify/Fern/vc.ru/Habr/Discord). `test_battery.py` (315 LOC) + `capture_signatures.py` для refresh baselines. Цель: ловит «тихие» регрессии preprocessing — page-count drift при изменении CSS-rules, потерянные drawio-диаграммы, отсутствие нужных секций после reader-mode фильтра. | L | M | q-1 | Аналог нужен для html2docx (см. q-7). |
| q-7 | Регресс-battery + unit-тесты для html2docx ✅ DONE (VDD-A hardened) | **Refactor**: 17 inline preprocessing-стадий (lines 156-596 в `html2docx.js`, ~440 LOC процедурного top-level кода) вынесены в sibling-модуль `_html2docx_preprocess.js` (~615 LOC) с named exports для каждой стадии и оркестратором `preprocessDom($, opts)` который возвращает `{ originalBodyText }` snapshot, нужный pickContentRoot'у для body-ratio guard. Паттерн зеркалит существующие `_html2docx_walker.js` / `_html2docx_archive.js` / `_html2docx_svg_render.js`. html2docx.js: 855 → 426 LOC. Functional contract: zero. **(a) Unit-тесты** [`tests/test_html2docx_preprocess.test.js`]: 57 тестов (built-in `node:test` + `node:assert/strict`, без новых devDependencies) покрывают 16 стадий — включая 8 правил icon-strip (AND-rule для axis-сравнений, sprite-pattern preservation guard для `<use>` без `<mask>`, FontAwesome 7 kit mask), Mintlify Steps с inline `<code>` через `.html()`, BEM-collision guard для `tm-page__main_has-sidebar`, Confluence DC хешированные классы, warn-once contract на namespaced elements. **(b) Regression battery** [`tests/test_battery.py` + `tests/capture_signatures.py` + `tests/battery_signatures.json`]: 9 fixtures × {regular,reader} с auto-dedupe (idempotent reader stays null) → 18 проверок. Tolerance bands: `min/max_paragraphs` ±5 % floor 2, `min/max_size_kb` ±10 % floor 5, `min/max_images` **точное равенство** на счёте `<w:drawing>` элементов (нулевая толерантность ловит icon-leak регрессии что size/paragraph-bands смазывают). Text extraction через stdlib `zipfile` + `lxml.etree` (`<w:p>` count + `<w:t>` join + `<w:drawing>` count). Fixture sources: `tests/fixtures/platforms/` (4 committed: Confluence/GitBook/Fern/Mintlify), `examples/regression/` (5 committed synthetic: aria-table, Mintlify Steps, Confluence DC code-wrap, Mintlify icon-svg с 25 viewBox-only декорациями + 1 диаграммой, vcru reader-mode strip), `tests/tmp/` (gitignored). Wired в `test_e2e.sh`: unit-тесты перед html2docx E2E (fail fast), battery в самом конце. **(c) Canary verification** [`tests/canary_check.sh`, q-7 LOW-3]: meta-test, последовательно саботирует 3 правила preprocessing'а через `sed -i.bak` и убеждается что battery FAILED для каждого случая; restores через `trap`. Без него зелёная battery не отличима от «battery permanently broken». **VDD-adversarial fixes** (post-implementation review): HIGH-1 image-count метрика (rule-6 регрессия раньше пряталась в ±10 % size band — sabotage 25 icons/1 diagram демонстрирует binary catch); MED-1 dedicated reader-mode fixture с distinct regular vs reader сигнатурами + forbidden_needles на REACTION_WIDGET/POST_SHARE_LINKS/POST_META_TAGS/RELATED_ARTICLES/COMMENTS_THREAD; MED-2 `aria-label^="Copy "` prefix-selector → explicit allowlist (17 chrome variants для en + 4 для ru), unit-тест pin'ит что substantive `"Copy of contract"` теперь PRESERVED; MED-3 capture auto-dedupes reader=null когда `regular == reader` (deep-equal); LOW-1 bash `\b` → portable `[[:space:]]`; LOW-2 default `onWarn` для standalone-stage callers возвращён в `console.warn`; LOW-4 hand-curated `forbidden_needles` + расширенные `required_needles` (IDE names для mintlify, column titles для confluence, `1./2./3.` heading prefixes для Mintlify Steps); LOW-5 CJK/Arabic ограничение sentence-splitter regex задокументировано в `_sample_needles` docstring. **Verification**: 57 unit / 18 battery (10 active + 8 dedupe-skipped) / 3-of-3 canary sabotages caught / skill-validator зелёный; E2E delta +2/0 регрессий (pre-existing `tier-2 fallback` подтверждён воспроизводимым на pre-refactor html2docx.js). | M | L | docx-3 | Защита глубокая (3 уровня): per-stage unit-тест → tolerance-band + image-count + needles на end-to-end output → canary-meta-проверка что battery вообще ловит регрессии. |

---

## 5. Документация

| ID | Название | Что/Зачем | Effort | Value | Dep | Notes |
|---|---|---|---|---|---|---|
| d-1 | Manual обновлён под текущее состояние ✅ DONE | Аудит `docs/Manuals/office-skills_manual.md`: cross-5 `--json-errors`, cross-6 `--mermaid-config`/`--no-mermaid`/`--strict-mermaid`, `--pptx-editable`, cross-7 `office_passwd`, `outline2pptx` уже были задокументированы (был ложно-негативный grep в первоначальной оценке). Реально не хватало q-2/q-3/q-5 — добавлены §8.3 visual regression, §8.4 property-based fuzz, §8.5 GitHub Actions CI; обновлена сводная таблица §8.2 (assertion count 117 → 184; q-3 mermaid edge-cases в pdf row); добавлена ссылка на troubleshooting (d-3). | S | M | — | После аудита ясно: основная боль — отсутствие документации для свежеиспечённых q-2/q-5, не для старых флагов. |
| d-2 | `references/` для xlsx/pptx — добить недостающее ✅ DONE | Аудит показал полное покрытие плана §4.1 (pptx) и §5.1 (xlsx): pptx имеет `design-principles.md` + `editing-workflow.md` + `pptxgenjs-basics.md` (1:1 vs план); xlsx — `financial-modeling-conventions.md` + `formula-recalc-gotchas.md` + `openpyxl-vs-pandas.md`. Гипотеза backlog'а («design tokens / palette» отсутствует) была устаревшей: pptx design-principles.md покрывает дизайн-направление, а chart-styling для xlsx план не обещал. | S | L | — | Реальный пробел отсутствует — задача закрыта без новых файлов. |
| d-3 | Troubleshooting guide ✅ DONE | `docs/Manuals/office-skills_troubleshooting.md` — единый документ с recipe `Symptom → Cause → Fix`. 7 секций (install/runtime, encrypted/legacy, visual regression, hypothesis fuzz, output/format, environment/CI, "куда ещё посмотреть"). Покрывает: pango/cairo missing, mmdc not found, soffice timeout, AF_UNIX shim, encrypted-input rejection, password-protect exit codes, golden drift, threshold tuning, IM v6 vs v7 binaries, XFA vs AcroForm, mermaid Cyrillic glyphs, openpyxl recalc, и т.д. | S | M | — | Кросс-линки в каждой секции: manual §9.5, per-skill references/, tests/visual/README.md. |

---

## 6. Что было обнаружено в эксплуатации (Discovered Issues)

Не задачи целиком, а сигналы — могут породить task'и выше или быть
закрыты по месту:

- **docx2md, TOC ссылки на нежесткие headings** — например «текст»
  стал ячейкой таблицы из-за оригинального табличного дизайна, и
  TOC-anchor должен попасть внутрь bold-span. Сейчас покрыто; следить
  на новых файлах.
- **Run-stutter (`<w:r>` × 2 одинаковые)** — частый артефакт Word
  copy-paste; heuristic в `collapseDuplicateAdjacentRuns` ловит,
  но length-cap = 3 — может пропустить случай типа `"4-я"+"4-я"`
  (5 chars). Если всплывёт, расширить.
- **Mermaid + weasyprint + Cyrillic** — `<text>` из SVG падает на
  fontfallback. Сейчас обходим через PNG; но если нужен векторный
  вывод, нужно решение через `<text>`-only export или font embedding.
- **LibreOffice headless cold-start** — первая конвертация после
  reboot занимает 10–15 сек (профайл пишется). Не баг, но user-pain.
  Варианты: keep-alive режим (демонизировать soffice).
- **docx tracked-changes integration test** — `office/validators/docx.py`
  проверяет integrity, но реальная проверка на «accept all changes
  не теряет содержимое» не покрыта.
- **xlsx с merged cells** — поведение `csv2xlsx` при импорте обратно
  не определено; вероятно теряет merge.
- **html2pdf/html2docx — типичная цена универсального HTML-конвертера**:
  каждая платформа (Confluence DC, GitBook, Mintlify, Fern, Docusaurus,
  vc.ru, Habr) приносит свой набор site-specific WTFs — hashed CSS
  classes, Radix lazy-render табов, FontAwesome 7 mask-pattern без
  viewBox, `<span data-code-lang>` обёртка inline-предков над code,
  shiki/Fern table-based code rendering, Mintlify Steps без `<ol>`,
  Tailwind print-modifier classes, drawio foreignObject align-items
  semantics. Универсальный «happy path» работает на 80 %, но каждый
  новый source-сайт стабильно даёт 1–3 фикс-итерации. Стратегия,
  которая отработала: regression battery с tolerance bands + required
  needles per platform; preprocessing-pipeline с явно маркируемыми
  правилами; mirror-fixes между html2pdf и html2docx через одинаковый
  набор site-specific эвристик.
- **walker.emitList в html2docx не рекурсирует в block-level** —
  блочный код / `<pre>` внутри `<li>` сжимается в одну inline-строку
  (теряется monospace, paragraph breaks). Текущий обход — flatten
  Mintlify Steps в `<h4>` + content на siblings. Если в будущем
  встретится «список с нетривиальным содержимым» (например, GitBook's
  nested code blocks), нужно дорабатывать walker, а не preprocessing.
- **Mintlify Steps title `.text()` теряет inline markup** —
  переключился на `.html()` с literal injection в `<h4>`, но если
  в title попадёт malformed HTML (unclosed tag), cheerio's forgiving
  parser может surprise. Не воспроизводимо на текущей battery.
- **Webarchive/MHTML с SPA-хостом — структурная классификация
  под одним пользовательским зонтиком «напечатай красиво»**.
  Механизм определяется СТРУКТУРОЙ архива и DOM, НЕ названием
  платформы. Vendor-allow-list'ы (`elma365-message-body`,
  `gmail_*`, `<div class="ii gt">`, `<app-root ng-version=>`,
  `data-reactroot`, `data-framer-name`, `side-nav`) — анти-
  паттерн: каждый next vendor требует новой записи и
  универсальность ломается. **Эвристики обязаны быть
  структурными**. Universality gates ✅ closed через 7 реальных
  фикстур (3 ELMA365 + Gmail + 2 Sentora-Framer + Yandex Cloud
  Console).
  
  **Классы по структуре inner-frames** (pdf-8 механизм):
  
  - **Case A: 0 substantial inner-frames** — main HTML несёт
    весь контент (вместе с SPA chrome). Подкатегории:
    *  `tmp/elma365_activities_example.webarchive`
       (`WebSubframeArchives=[]`, 1.67 MB hydrated Angular DOM с
       Material списком),
    *  `tmp/gmail_example.webarchive` (5 субфреймов, ВСЕ
       non-substantial — Google One sidebar / Contacts hovercard
       / system iframes — каждый имеет ≥ 13 scripts; реальное
       тело письма INLINE в main DOM в `<div class="ii gt">`),
    *  `tmp/Tether's…Sentora.webarchive` + `tmp/The Number…
       Sentora.webarchive` (Framer-built blogs; 1 субфрейм
       framer.com/edit-widget non-substantial),
    *  `tmp/ya_browser.webarchive` (Yandex Cloud Console
       marketplace; 1 субфрейм auth.yandex.cloud user-menu
       non-substantial).
    Решение: `--archive-frame auto` → `main`, далее pdf-9
    (universal SPA-chrome strip).
  
  - **Case B: 1 substantial inner-frame** — открыт один
    «документ» в sandbox-iframe.
    *  `tmp/test_email_elma365.webarchive` (1 subframe = открытое
       письмо, body `<div class="elma365-message-body">`).
    Решение: `--archive-frame auto` → `1` (или явный `1`).
  
  - **Case C: N (≥ 2) substantial inner-frames** — список
    «документов» в multi-iframe panel.
    *  `tmp/email_list_client.webarchive` (7 subframes = переписка
       клиента; разные авторы Демидова/Ткачук/Александр Черных;
       frame1 с inline JPEG-аттачем).
    Решение: `--archive-frame auto` → `all`, concat с
    flat-разделителями `<hr><h2>Frame N</h2>`.
  
  «Substantial» определяется **структурно**: ≥ 1 KB HTML AND no
  `<script>` AND ≥ 100 chars plain text AND not single-`<img>`
  body. Никаких vendor-классов в коде.
  
  **Внутри Case A — три подкласса по semantic-richness DOM**
  (pdf-9 механизм, всё через universal `--reader-mode`):
  
  - **A.1 Rich-landmarks**: ≥ 3 ARIA-landmarks (`role="main\|
    navigation\|complementary\|banner"`) — ARIA-strip + content-
    root resolve работают идеально (`gmail_example`,
    `elma365_activities_example` — у последнего `<aside>` +
    `<main class="app-wrap">`).
  - **A.2 Semantic-light**: bundle-criterion триггерит SPA-
    detection, но ARIA + `<article>`/`<main>` отсутствуют, реально
    SPA-chrome ALSO нет — content-root fallback правильно
    выбирает body, output ±5 % vs blog-pass-through (Sentora
    Framer-blogs).
  - **A.3 Landmark-free hostile**: ноль ARIA, ноль semantic
    tags, голый `<div>`-soup с CSS-классами (`ya_browser`).
    Best-effort: SPA-detection триггерит, ARIA/semantic-strip
    rules ничего не находят, content-root falls back на largest
    text-density subtree — sidebar text может протекать. Honest
    scope, не bug. Если станет real pain — follow-up pdf-9a
    (soft `class="*sidebar*\|*nav*\|*menu*"` strip).
  
  **Insight: web-mail клиенты используют ≥ 2 разных
  паттернов** для тела письма (структура, не вкус
  vendor'а):
  - **iframe-sandboxed** (ELMA365 classic) → Case B/C
  - **inline-DOM** (Gmail с strict CSP) → Case A.1
  Триггер пользователя один, механизм определяется тем, как
  vendor реализовал rendering. Композиция pdf-8 + pdf-9
  покрывает оба без vendor-знаний.
  
  **Convergence test (VDD-adversarial)**: новый SPA / web-mail
  работает без code-changes. Закрыт на 7 фикстурах ×
  4 разных SPA-стэка (Angular, Closure, Framer, Yandex
  Console). Дизайн признан universal **именно потому что есть
  hostile фикстура** (ya_browser) с задекларированным
  best-effort outcome — а не потому что «работает на трёх
  знакомых сайтах».
- **Adversarial review — обязательная остановка** — на html2pdf и
  html2docx без VDD-adversarial проходов оставались HIGH-severity
  баги (icon SVG over-strip через `<use>`, `aria-label*="Copy"`
  substring overstrip, shiki flatten без gate'а на marker-классы).
  Convergence signal — когда adversary начинает галлюцинировать
  (предложил «Fern рендерит все panels» — verified false: Radix
  всегда lazy).

---

## 7. Как приоритезировать

Предлагаемые критерии для выбора, что делать дальше:

1. **Реальный спрос** — задача всплыла в конкретном пользовательском
   запросе (как mermaid в md2pdf). Ставим P0.
2. **Закрывает группу запросов** — например `pdf_fill_form.py`
   разблокирует все запросы «заполни PDF из JSON». Ставим P1.
3. **Покрытие** — XSD-валидаторы для xlsx/pptx, тесты, manual. Не
   срочно, но без них будем спотыкаться. P2.
4. **Nice-to-have** — `pdf_watermark`, `pptx_apply_theme`, encrypted
   files. Делаем под конкретный заказ. P3.

### Кандидаты на P0/P1 (моё предложение, обсудить)

- **P0**: `pdf_fill_form.py` (pdf-1) — упомянут в plan §9.4 как
  стандартный сценарий, прямой пользовательский запрос вероятен.
- **P0**: q-1 (E2E тесты) — без них любая VDD-итерация рискованна.
- **P1**: `xlsx_add_chart.py` (xlsx-1) — почти всегда после csv2xlsx
  следующий запрос.
- **P1**: pptx-1 (`pptx_clean.py`) — после ручных правок template
  обязательная гигиена.
- **P1**: cross-3 (graceful fail на encrypted) — внятные сообщения
  об ошибке.
- **P2**: pdf-6 + cross-6 (mermaid config + cyrillic preset) — для
  не-английских презентаций важно.
- **P2**: pptx-3 (`outline2pptx.py`) — простая задача, быстрая
  победа.

Остальное — P3, по конкретным заказам.

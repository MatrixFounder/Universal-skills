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

### pdf

| ID | Название | Что/Зачем | Effort | Value | Dep | Notes |
|---|---|---|---|---|---|---|
| pdf-1 | `pdf_fill_form.py` ✅ DONE | Заполнить AcroForm (fillable-поля) из JSON. Описан в `references/forms.md`. | M | H | — | pypdf, XFA fail-fast (exit 2), no-form fail (exit 3), `--check`/`--extract-fields`/`--flatten`. E2E тесты в `tests/test_e2e.sh`. |
| pdf-2 | `pdf_watermark.py` ✅ DONE | CLI накладывает text- или image-watermark на каждую (или выбранные через `--pages "1-5,8"`) страницу PDF. Реализация: reportlab `canvas.Canvas` рисует overlay с `setFillAlpha(opacity)` + поворот через `translate/rotate` (диагональ авто-rotation 45°), pypdf `page.merge_page` объединяет с исходником. Per-mediabox кеш overlay'ев — гетерогенные деки (Letter+A4 в одном файле) сохраняют корректные пропорции. Mutex-группа `--text` / `--image` (один обязателен). Опции: `--position center|top-left|top-right|bottom-left|bottom-right|diagonal` (default diagonal), `--opacity 0.0..1.0` (default 0.3), `--rotation`, `--font-size`, `--color`, `--scale` (image-only). Cross-7 H1 same-path guard (exit 6 `SelfOverwriteRefused`, ловит symlinks через `Path.resolve()`) — впервые в pdf-скиллах, новые CLI устанавливают конвенцию. Cross-5 `--json-errors` envelope. E2E: 7 проверок (text round-trip + текст-extract `DRAFT` через pypdf, image-watermark, page-count preserved, same-path guard, mutex required+exclusive, `--pages "1"` selectivity на 2-страничном PDF). Visual golden `watermarked-text.png`. | S | M | — | pypdf + reportlab уже в `requirements.txt`. Honest scope: image masks через `mask='auto'` (PNG alpha), `--rotation` rotates стамп вокруг anchor (translate→rotate→drawCentredString паттерн). |
| pdf-3 | `pdf_compress.py` | Снизить вес PDF: пересжать встроенные изображения, убрать дубли. | M | M | — | gs (ghostscript) делает это лучше — обёртка вокруг него. |
| pdf-4 | `pdf_ocr.py` | OCR scanned PDF через `tesseract` или `ocrmypdf`. Нужно для legacy-документов. | M | M | — | Системная зависимость на tesseract. |
| pdf-5 | `html2pdf.py` ✅ DONE (XXL: VDD iter-1..7 + per-iter adversarial review + 4-tier regression battery) | Универсальный HTML→PDF конвертер через weasyprint — для BI-дашбордов, Confluence-страниц, сохранённых веб-страниц. **Архитектура**: 194 LOC CLI + 1899 LOC в `html2pdf_lib/` (7 модулей: `archives.py` 202, `dom_utils.py` 145, `normalize_css.py` 243, `preprocess.py` 948, `reader_mode.py` 220, `render.py` 139, `__init__.py` 22). Поддерживает три input-формата: `.html`/`.htm` (plain), `.mhtml`/`.mht` (MIME-архив, browser «Save as → Single File»), `.webarchive` (Apple Safari). Для MHTML/WebArchive sub-resources извлекаются в tempdir, URL переписываются на локальные пути. **Preprocessing-pipeline** (`preprocess.py`, 948 LOC): `_fix_light_dark()` — O(n) depth-counter замена `light-dark(X, Y)` → `X`; **drawio foreignObject→`<text>` конвертер** с align-items vertical anchoring, edge-label backdrop через `<rect>` (обход стрелок поверх лейблов), модерн-color whitelist (rgba/hsl/hsla/oklch/oklab + named), variable resolution и `!important` strip; универсальный chrome strip (анкор-маркеры, copy-buttons, fixed nav bars); icon-SVG strip (8 правил, mirrors html2docx); ARIA-table conversion (`role="table"` → semantic `<table>` через CSS); Mintlify Steps; Confluence DC code-wrap. **`normalize_css.py`** (243 LOC): 16+ rule блок CSS-injection в `<head>` — `body{overflow:clip}` reset (SPA), `.drawio-macro svg` overflow fix, code-block wrap для Prism/Confluence DC (`code[class*="language-"]`), `pre`-table flatten гейты. **`reader_mode.py`** (220 LOC): article-extraction для blog-сайтов с приоритезацией `<article>`/`<main>`/`[role="main"]` + heuristic min-text=500 для Confluence. **`render.py`** (139 LOC): weasyprint render с `<foreignobject>` casing fix, font-fallback для Cyrillic SVG glyphs. Опции: `--page-size letter\|a4\|legal`, `--css EXTRA.css`, `--base-url DIR`, `--no-default-css`, `--reader-mode`. **Тесты**: `test_preprocess.py` (844 LOC, 55 unit-тестов: 14 fo→text + 6 normalize-css guards + остальные на edge-cases), `test_battery.py` (315 LOC) + `battery_signatures.json` (31 fixture × 2 modes = 62 регрессий с tolerance bands ±5% pages, ±10% size + required_needles per platform: Confluence/GitBook/Mintlify/Fern/vc.ru/Habr/Discord). E2E: 9 проверок. Visual golden `html-basic.png`. | XXL | M | — | weasyprint, plistlib (stdlib), email (stdlib). VDD-история: iter-1 site-agnostic preprocessing, iter-2 table-based code flatten, iter-3 Mintlify icons + ARIA tables, iter-4 reader-mode, iter-5 (9 adversarial bugs), iter-6 (4-tier regression battery), iter-7 (11 issues). Затем drawio align-items fix, edge-label backdrop, code-block wrap. Honest scope: walker.emitList не recurses в block-level, `display:none` chrome видим только статически. |
| pdf-6 | Mermaid: dark-theme и custom config ✅ DONE | `--mermaid-config PATH` в md2pdf, прокидывается в `mmdc -c`. Cache key включает SHA1 контента конфига → смена темы / шрифта инвалидирует кеш PNG. Missing-path → warn + degrade (или fail в `--strict-mermaid`). E2E: 3 проверки. | S | L | mermaid done | Аналог в `md2pptx.js`: `--mermaid-config` / `--no-mermaid-config`. |
| pdf-7 | TOC bookmarks (PDF outline) | weasyprint умеет: добавить `<h1-h6>` → PDF outline. Уже из коробки или нужен CSS-флаг? Проверить и при необходимости добавить. | S | M | — | Сейчас только in-page links. |

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

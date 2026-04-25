# Office-skills backlog

Что осталось сделать после базовой итерации §9.6 плана
[`refactoring-office-skills.md`](refactoring-office-skills.md). Это
живой документ — добавляем сюда обнаруженные пробелы по мере
эксплуатации, потом приоритезируем явно (P0–P3).

## Условные обозначения

- **Effort**: S (≤ 3 ч), M (3–8 ч), L (8+ ч).
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

---

## 2. Бэклог по скиллам

### docx

| ID | Название | Что/Зачем | Effort | Value | Dep | Notes |
|---|---|---|---|---|---|---|
| docx-1 | `docx_add_comment.py` | CLI: вставить `<w:comment>` с автором/датой/диапазоном якоря. Часто нужно для review-флоу: робот оставляет комментарий «проверьте формулу X». | M | M | — | python-docx не умеет напрямую — пишем через `office/unpack` + ручной XML-вставкой. |
| docx-2 | `docx_merge.py` | Склеить N .docx в один, сохраняя стили/нумерацию. Часто просят объединить «преамбулу + статьи + приложения». | M | M | — | Аналог `pdf_merge`, но сложнее: надо мерджить styles/numbering/relationships. |
| docx-3 | `html2docx.js` | Параллель к `md2docx.js`, но из произвольного HTML (например, выгрузка из Confluence/CMS). | L | L | — | Можно через mammoth-обратный путь или прямой обход DOM. |
| docx-4 | Сохранение комментариев и track-changes при docx2md | Сейчас `<w:comment>`, `<w:ins>`, `<w:del>` теряются при mammoth → markdown. Можно вытаскивать в отдельный JSON-сайдкар. | L | M | — | Используется для аудита договоров. |
| docx-5 | Footnotes / endnotes в markdown | mammoth их игнорирует; можно постпроцессить через `office/unpack` + конвертировать в pandoc-style `[^1]`. | M | L | — | Редко встречается в корпоративных docx. |

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
| pdf-2 | `pdf_watermark.py` | Наложить text/image watermark на каждую страницу. Чаще нужен для черновиков или confidential-маркера. | S | M | — | pypdf + reportlab для overlay. |
| pdf-3 | `pdf_compress.py` | Снизить вес PDF: пересжать встроенные изображения, убрать дубли. | M | M | — | gs (ghostscript) делает это лучше — обёртка вокруг него. |
| pdf-4 | `pdf_ocr.py` | OCR scanned PDF через `tesseract` или `ocrmypdf`. Нужно для legacy-документов. | M | M | — | Системная зависимость на tesseract. |
| pdf-5 | `html2pdf.py` | Параллель к md2pdf, но HTML-on-input. Часто запрашивают для отчётов из BI-дашбордов. | S | L | — | Тонкая обёртка над тем же weasyprint. |
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
| q-2 | Visual regression PDF | Хранить golden-render первой страницы каждого выходного PDF, сравнивать pixel-hash. Ловит регрессии стилей. | M | M | — | imagemagick + checksum. |
| q-3 | Покрытие mermaid edge-cases | Тесты на: cyrillic-метки, длинные mindmap, Sequence/Gantt диаграммы, mmdc-fail. | S | M | pdf-6 | Текущий тест Sales pdf — реальная боль. |
| q-4 | Ровный CI на 4 скиллах | GitHub Actions: для каждого скилла — `install.sh` → `run validator` → `run tests` → smoke на fixture. | M | M | q-1 | Сейчас всё ручное. |
| q-5 | Property-based тесты | hypothesis-fuzz входов для md2docx/md2pdf/csv2xlsx — выявляет crash на edge-инпутах (пустые, очень большие, юникод-сюрпризы). | L | L | q-1 | Полезно для долгоиграющего кода. |

---

## 5. Документация

| ID | Название | Что/Зачем | Effort | Value | Dep | Notes |
|---|---|---|---|---|---|---|
| d-1 | Manual обновлён под текущее состояние | `docs/Manuals/office-skills_manual.md` — проверить, что отражает текущий API + новые флаги (`--pptx-editable`, `--no-mermaid`, `--strict-mermaid`). | S | M | — | Мог отстать после VDD-итераций. |
| d-2 | `references/` для xlsx/pptx — добить недостающее | xlsx сейчас 3 файла, в плане было 3+. Возможно не хватает «design tokens / palette». | S | L | — | Перепроверить vs план §3.3.1. |
| d-3 | Troubleshooting guide | Один файл с типовыми «не работает X» → действие. Чаще всего: pango/cairo, soffice timeout, mmdc fail. | S | M | — | Реально экономит время поддержки. |

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

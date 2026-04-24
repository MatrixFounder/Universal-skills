# Разбор скиллов Anthropic: docx, pptx, xlsx, pdf

Подробная карта того, что именно внутри каждого из «документных» скиллов
Anthropic, что там оригинального, а что взято из публичных источников
(стандарты OOXML, LibreOffice, open-source Python/JS-библиотеки).

Цель документа — дать чёткую картину для переписывания аналогичных скиллов
с нуля под открытой лицензией (например, Apache-2.0 или MIT) и размещения
их в собственном репозитории вроде `MatrixFounder/Universal-skills`.

Оговорка: разбор сделан по чтению файлов локальной поставки плагина и
публично доступного репозитория [`anthropics/skills`](https://github.com/anthropics/skills).
Проверить git-историю у меня возможности нет, поэтому где-то «оригинальный
код Anthropic» может оказаться лёгкой адаптацией из публичных источников —
я маркирую такие места как «предположительно написано Anthropic».

---

## 1. Юридический контекст (коротко)

У скиллов Anthropic нет единой лицензии — каждый скилл лежит с собственным
`LICENSE.txt`:

- `docx`, `pptx`, `xlsx`, `pdf` — **проприетарная лицензия** с явным запретом
  на создание производных работ, копирование за пределы сервиса и
  распространение. Текст буквально: *«users may not … create derivative
  works based on these materials … distribute, sublicense, or transfer these
  materials to any third party»*.
- «Example skills» из того же публичного репо (`skill-creator`,
  `algorithmic-art`, `brand-guidelines`, `frontend-design`, `internal-comms`
  и другие) — **Apache-2.0**. Можно форкать и редистрибутировать с
  сохранением атрибуции.

Практический вывод: в публичный репо нельзя копировать ни код скриптов,
ни тексты SKILL.md из `docx/pptx/xlsx/pdf`. Но каждый из этих скиллов на
~80–90% состоит из вещей, которые **не принадлежат Anthropic**: публичные
XSD-схемы Microsoft/Ecma/W3C, стандартный UNO API LibreOffice, open-source
Python/JS-библиотеки. Их нужно просто взять напрямую у первоисточников.

Оригинальная часть, которую придётся переписать, — это тонкие Python-обёртки
и текст SKILL.md. На каждый скилл — 500–1500 строк кода плюс markdown.

---

## 2. Общая часть: инфраструктура `scripts/office/`

Эта подпапка **идентична** внутри трёх скиллов: `docx`, `pptx`, `xlsx`.
Скилл `pdf` её не использует — PDF это другой формат, без OOXML.

Структура:

```
scripts/
├── office/
│   ├── soffice.py                      # обёртка над LibreOffice + LD_PRELOAD shim
│   ├── unpack.py                       # распаковка OOXML (zip → dir + pretty-print)
│   ├── pack.py                         # обратный процесс: dir → zip + валидация
│   ├── validate.py                     # CLI-валидатор (XSD + кастомные проверки)
│   ├── validators/
│   │   ├── base.py                     # общая логика XSD-валидации
│   │   ├── docx.py                     # DOCXSchemaValidator
│   │   ├── pptx.py                     # PPTXSchemaValidator
│   │   └── redlining.py                # проверка целостности tracked changes
│   ├── helpers/
│   │   ├── merge_runs.py               # схлопывание соседних <w:r> с одним стилем
│   │   └── simplify_redlines.py        # слияние соседних правок одного автора
│   └── schemas/                        # 50+ XSD-файлов (НЕ Anthropic!)
│       ├── ISO-IEC29500-4_2016/        # стандарт ECMA-376 / ISO/IEC 29500
│       ├── microsoft/                  # расширения Microsoft (w14/w15/w16*)
│       ├── ecma/fouth-edition/         # Open Packaging Conventions
│       └── mce/mc.xsd                  # Markup Compatibility Extensions
```

### 2.1. Папка `schemas/` — 100% сторонние публичные стандарты

Здесь ни одной строки оригинального кода Anthropic. Это копии
международных и индустриальных стандартов. Берутся напрямую у
первоисточников.

**`schemas/ISO-IEC29500-4_2016/*.xsd` (~25 файлов)**

Схемы OOXML (Office Open XML) — международный стандарт ISO/IEC 29500,
он же Ecma-376. Описывают форматы WordprocessingML, SpreadsheetML,
PresentationML, DrawingML, VML.

- Официальный бесплатный источник: [Ecma International —
  ECMA-376](https://ecma-international.org/publications-and-standards/standards/ecma-376/).
  На странице стандарта доступен ZIP со всеми XSD. Текущая редакция —
  5th edition (2021), но 4th edition (2016) в вашей поставке — тоже
  публично доступная предыдущая версия.
- Лицензия: **Ecma International Standards** публикуются бесплатно и могут
  копироваться для реализации стандарта. См. Ecma Policy на Patents и
  Copyright — технические спецификации свободно распространяются.
- Копирайт: © Ecma International / ISO/IEC. Нужно сохранить атрибуцию в
  `THIRD_PARTY_NOTICES.md` вашего репо.

**`schemas/microsoft/wml-*.xsd` (7 файлов)**

Расширения Microsoft, которые современный Word пишет дополнительно к
базовому OOXML (2010, 2012, 2015, 2016, 2018, 2020-й годовые срезы).
Namespaces вроде `w14`, `w15`, `w16cid`, `w16cex`, `w16du`.

- Источник: [Microsoft Learn — `[MS-DOCX]` и связанные
  спецификации](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-docx/).
- Лицензия: [**Microsoft Open Specification
  Promise**](https://learn.microsoft.com/en-us/openspecs/dev_center/ms-devcentlp/51c5a3fd-e73a-4cec-b65c-3e4094d0ea12)
  — свободная безотзывная лицензия на имплементацию и распространение
  спецификаций.

**`schemas/ecma/fouth-edition/opc-*.xsd` (4 файла)**

Open Packaging Conventions — механизм упаковки OOXML в ZIP с
Content Types, Relationships, Core Properties, Digital Signatures.
Тоже часть ECMA-376. Те же условия.

**`schemas/mce/mc.xsd`**

Markup Compatibility Extensions (`xmlns:mc="…/markup-compatibility/2006"`) —
как «игнорируются неизвестные элементы» в OOXML. Часть ECMA-376.

**`schemas/ISO-IEC29500-4_2016/xml.xsd`**

Схема XML-namespace от W3C (атрибуты `xml:lang`, `xml:space`, `xml:base`).

- Источник: [W3C — XML namespace
  schema](https://www.w3.org/2001/xml.xsd).
- Лицензия: [W3C Document License](https://www.w3.org/copyright/document-license/).

**Как забрать скопом в свой репозиторий:**

```bash
# 1. Официальный Ecma-пакет со всеми XSD
#    (после загрузки — положить в skills/common/schemas/ecma-376/)
curl -O https://ecma-international.org/wp-content/uploads/ECMA-376-5th-edition-December-2021.zip
unzip ECMA-376-5th-edition-December-2021.zip

# 2. Microsoft-расширения
#    Конкретные файлы публикуются на learn.microsoft.com;
#    некоторые проекты (например, docx4j) хранят их скопом —
#    можно посмотреть их THIRD_PARTY_NOTICES как референс.

# 3. W3C xml.xsd
curl -O https://www.w3.org/2001/xml.xsd
```

И в `THIRD_PARTY_NOTICES.md` репозитория записать:

```markdown
## OOXML XML Schema Definitions

Distributed under ECMA-376 and ISO/IEC 29500 with Ecma International's
open specification policy. Microsoft namespace extensions distributed
under the Microsoft Open Specification Promise. W3C xml.xsd distributed
under the W3C Document License.

Sources:
- https://ecma-international.org/publications-and-standards/standards/ecma-376/
- https://learn.microsoft.com/en-us/openspecs/office_standards/
- https://www.w3.org/2001/xml.xsd
```

### 2.2. `scripts/office/soffice.py` — обёртка над LibreOffice + LD_PRELOAD shim

Файл делает две вещи:

**(а) Запускает `soffice` (LibreOffice headless) с правильным окружением.**

Код тривиальный: `SAL_USE_VCLPLUGIN=svp` + `subprocess.run(["soffice", …])`.
Это общеизвестная техника, см., например:

- [Официальная документация LibreOffice — Headless
  mode](https://wiki.documentfoundation.org/Documentation/DevGuide/Installation#Starting_the_Office_in_Listening_Mode).
- [`SAL_USE_VCLPLUGIN`
  параметр](https://wiki.documentfoundation.org/Common_command_line_options).

**(б) Содержит встроенный C-shim как строку `_SHIM_SOURCE`, который через
`LD_PRELOAD` перехватывает системные вызовы `socket(AF_UNIX)`, `listen`,
`accept`, `close`, `read` и подменяет AF_UNIX сокеты парой через
`socketpair()`.**

Это нужно в песочницах, где `AF_UNIX`-сокеты заблокированы seccomp-фильтром:
LibreOffice иначе падает, потому что внутренне общается с собой через
Unix-domain socket.

Техника «подмена glibc-функций через LD_PRELOAD» — общеизвестный системный
паттерн, не собственность Anthropic. Публичные референсы:

- [LD_PRELOAD
  tricks](https://catonmat.net/simple-ld-preload-tutorial) — обзор техники.
- [`libfaketime`](https://github.com/wolfcw/libfaketime) (LGPL-2.0+) —
  хрестоматийный пример перехвата glibc-функций через LD_PRELOAD, целится
  в `time()/gettimeofday()` вместо `socket()`, но структура кода почти
  один в один.
- [`fakechroot`](https://github.com/dex4er/fakechroot) (LGPL-2.1-or-later) —
  ещё один пример, перехватывает файловые операции.
- `man ld.so`, секция `LD_PRELOAD`.

Сам конкретный shim (~60 строк C) написан Anthropic под свою задачу,
но логика стандартная: `dlsym(RTLD_NEXT, …)` для получения реальных
функций, per-FD bookkeeping, fallback на `socketpair()`.

**Как заменить в своём репо:**

Написать shim заново, опираясь на публичные LD_PRELOAD-примеры.
Альтернатива: запускать LibreOffice в окружении, где AF_UNIX разрешён
(Docker с `--privileged` или nsjail с `--disable_clone_newnet` — в зависимости
от вашего раннера), тогда shim вообще не нужен.

### 2.3. `scripts/office/unpack.py` и `pack.py`

Тонкие обёртки вокруг `zipfile` (стандартная библиотека Python).

`unpack.py`:
1. `zipfile.ZipFile(input).extractall(output_dir)`
2. Для каждого `.xml` и `.rels` — pretty-print через
   `defusedxml.minidom.parseString(...).toprettyxml(indent="  ")`.
3. Для `.docx` — вызов `merge_runs` и `simplify_redlines` (см. §2.5).
4. Escape smart quotes (`"`, `"`, `'`, `'`) в XML-entity, чтобы они
   пережили edit-цикл.

`pack.py`:
1. (Опц.) прогоняет валидаторы с auto-repair.
2. Condense XML (убирает whitespace-only text nodes и комментарии из
   parsed DOM).
3. `zipfile.ZipFile(output, "w", ZIP_DEFLATED).write(...)` по всем файлам.

**Библиотеки:**

- [`defusedxml`](https://github.com/tiran/defusedxml) — safer XML parsing,
  лицензия **PSF**. Нужно добавить в зависимости и `THIRD_PARTY_NOTICES`.
- `zipfile`, `shutil`, `tempfile`, `pathlib` — stdlib.

**Сколько оригинального кода:** ~130 строк `unpack.py` + ~160 строк `pack.py`
= ~300 строк Python с простой логикой. Легко пишется с нуля за пару часов.

**Альтернатива готовым кодом:** почти то же самое делает
[`python-docx`](https://github.com/python-openxml/python-docx) (MIT) и
[`openpyxl`](https://openpyxl.readthedocs.io/) (MIT-style) — они тоже
внутри распаковывают OOXML-ZIP и парсят XML, только API у них «высокого
уровня» (без ручного редактирования XML).

### 2.4. `scripts/office/validate.py` + `validators/`

CLI + набор валидаторов. По файлам:

- **`base.py` (`BaseSchemaValidator`)** — общие методы: `validate_xml`,
  `validate_namespaces`, `validate_unique_ids`, `validate_file_references`,
  `validate_content_types`, `validate_against_xsd`, `compare_paragraph_counts`.
- **`docx.py` (`DOCXSchemaValidator`)** — расширяет base, добавляет
  проверки whitespace preservation, целостности `<w:del>`/`<w:ins>`,
  маркеров комментариев, ID constraints.
- **`pptx.py` (`PPTXSchemaValidator`)** — аналог для презентаций.
- **`redlining.py` (`RedliningValidator`)** — проверяет, что tracked
  changes сравнимы с оригиналом: нет ли «потерянных» кусков текста,
  правильно ли маркировано авторство.

**Библиотеки:**

- [`lxml`](https://lxml.de/) — BSD-style license. Для XSD-валидации
  (`lxml.etree.XMLSchema`).
- `defusedxml` — см. выше.

**Оригинальный код:** логика валидаторов написана Anthropic, но идея
«валидировать OOXML против XSD через lxml» — стандартный паттерн, описан в
[lxml docs](https://lxml.de/validation.html#xmlschema). Сами XSD —
публичные (§2.1).

**Как заменить:** взять `lxml.etree.XMLSchema(open('wml.xsd'))`, написать
свой класс-валидатор с похожим набором проверок. 200–400 строк Python.

### 2.5. `scripts/office/helpers/`

`merge_runs.py` — эвристика «схлопывать соседние `<w:r>` с одинаковым
`<w:rPr>`», чтобы edit-цикл не плодил артефакты от Word (который любит
разбивать абзац на десятки микро-ranов из-за spell check и т.п.).

`simplify_redlines.py` — сливает подряд идущие `<w:ins>` и `<w:del>`
одного автора в одну правку.

Оба — специфичная логика Anthropic, но сама задача стандартная и описана
в [MS-DOCX
спецификации](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-docx/).
Логику легко повторить на своих данных.

### 2.6. Что в итоге **общего** переписываем с нуля

| Компонент | Размер | Сложность | Что делает |
|---|---|---|---|
| `soffice.py` (LibreOffice-обёртка) | ~50 Python + 60 C | Средняя (shim) | Запускает soffice, обходит sandbox-ограничения |
| `unpack.py` + `pack.py` | ~300 Python | Низкая | Распаковка/упаковка OOXML ZIP + pretty-print |
| `validate.py` + `validators/*.py` | ~600 Python | Средняя | XSD-валидация через lxml + кастомные проверки |
| `helpers/merge_runs.py` | ~100 Python | Низкая | Схлопывание соседних run'ов с одинаковым стилем |
| `helpers/simplify_redlines.py` | ~100 Python | Низкая | Слияние соседних правок одного автора |
| **ИТОГО** | **~1100 строк** | | |

Плюс `schemas/*.xsd` (~50 файлов) — просто скачиваются.

---

## 3. Скилл `docx`

Базируется на общей инфраструктуре `scripts/office/` (§2) плюс:

### 3.1. `SKILL.md` (~590 строк)

Главная ценность скилла — не код, а **накопленная эмпирика по работе
с `docx-js` и с ручным редактированием OOXML XML**. Ключевые темы:

- Docx-js defaults to A4 — всегда ставить `size: { width: 12240, height: 15840 }` для US Letter.
- Landscape: передавать портретные размеры + `orientation: PageOrientation.LANDSCAPE`.
- Lists: `LevelFormat.BULLET`, никаких `\u2022` руками.
- Tables: «dual widths» (и `columnWidths` на таблице, и `width` на ячейках), только `WidthType.DXA`, `ShadingType.CLEAR`, минимум 80/120 padding.
- Images: обязательный `type: "png"` + `altText` со всеми тремя полями.
- TOC требует чистых `HeadingLevel` без кастомных стилей + `outlineLevel`.
- Tracked changes: правильный синтаксис `<w:del>`/`<w:ins>`, `<w:delText>` вместо `<w:t>` внутри `<w:del>`, удаление параграфа требует пометки `<w:del/>` в `<w:pPr><w:rPr>`.
- Comments: `<w:commentRangeStart>`/`<w:commentRangeEnd>` — siblings `<w:r>`, не внутри.
- Smart quotes → `&#x2019;` и подобные entities (переживают edit-цикл).
- RSIDs — 8-значный hex, `durableId` < 0x7FFFFFFF.
- Image embedding: относительная ссылка в `word/_rels/document.xml.rels` + Content Type + `<w:drawing>/<wp:inline>/<a:graphic>`.

Конкретные формулировки — proprietary. Но **все эти факты** — либо
объективные свойства формата (описаны в ECMA-376 / MS-DOCX), либо баги
`docx-js`, которые обсуждаются в issue-трекере библиотеки:
[dolanmiu/docx issues](https://github.com/dolanmiu/docx/issues). В своём
SKILL.md можно описать те же истины своими словами, со ссылками на
исходные issue.

### 3.2. Скрипты, специфичные для docx

**`scripts/comment.py` + `scripts/templates/*.xml`** (~200 строк + 5 XML-файлов)

Добавление комментариев (top-level и threaded replies) в распакованный
`.docx`. Сам комментарий состоит из 5 файлов внутри OOXML:

- `word/comments.xml` — тексты
- `word/commentsExtended.xml` — parent/child связи для reply
- `word/commentsExtensible.xml` — durableId для Word 365
- `word/commentsIds.xml` — paraId mapping
- `word/people.xml` — список авторов

Шаблоны (`templates/*.xml`) — почти пустые OOXML-файлы с правильными
namespace'ами. То же самое Word создаёт сам, когда вы добавляете первый
комментарий в новом документе. Берутся из любого `.docx` с комментариями
— распаковали, скопировали каркас.

Скрипт Anthropic делает:
1. Создаёт недостающие файлы из шаблонов.
2. Добавляет релейшнсы в `word/_rels/document.xml.rels`.
3. Добавляет Content Types в `[Content_Types].xml`.
4. Генерирует новые `<w:comment>` элементы с правильными `id`, `paraId`,
   `durableId`.

Логика — своя у Anthropic, но задача стандартная. Полная спецификация —
в [MS-DOCX §2.4.35
comments](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-docx/).

**`scripts/accept_changes.py`** (~135 строк)

Вызов StarBasic-макроса `AcceptAllTrackedChanges` через `soffice` в
headless-режиме. Сам макрос:

```starbasic
Sub AcceptAllTrackedChanges()
    Dim document As Object
    Dim dispatcher As Object
    document = ThisComponent.CurrentController.Frame
    dispatcher = createUnoService("com.sun.star.frame.DispatchHelper")
    dispatcher.executeDispatch(document, ".uno:AcceptAllTrackedChanges", "", 0, Array())
    ThisComponent.store()
    ThisComponent.close(True)
End Sub
```

Это **стандартный UNO-вызов**, документированный на:

- [LibreOffice — Dispatch
  Commands](https://wiki.documentfoundation.org/Development/DispatchCommands)
- [The Document Foundation — UNO
  API](https://api.libreoffice.org/)
- [Ask LibreOffice —
  AcceptAllTrackedChanges](https://ask.libreoffice.org/) — десятки
  тредов с тем же макросом.

Python-обёртка делает:
1. Создаёт макрос в профиле LibreOffice (`~/.config/libreoffice/...`).
2. Копирует input → output.
3. Запускает `soffice --headless --norestore
   vnd.sun.star.script:Standard.Module1.AcceptAllTrackedChanges?language=Basic&location=application output.docx`.

**Как переписать:** макрос скопировать из публичных источников
(Ask LibreOffice / LibreOffice wiki), Python-обёртку — написать свою
(20 строк `subprocess.run`).

### 3.3. Внешние инструменты (не бандлятся — вызываются как CLI/lib)

| Инструмент | Лицензия | Для чего | Как устанавливается |
|---|---|---|---|
| [`pandoc`](https://pandoc.org/) | GPL-2.0+ | Извлечение текста `.docx → md` | `apt install pandoc`, `brew install pandoc` |
| [`docx-js`](https://github.com/dolanmiu/docx) (npm `docx`) | MIT | Создание новых `.docx` | `npm install -g docx` |
| [LibreOffice](https://www.libreoffice.org/) (`soffice`) | MPL-2.0 | PDF-конвертация, accept changes | `apt install libreoffice`, `brew install --cask libreoffice` |
| [Poppler](https://poppler.freedesktop.org/) (`pdftoppm`) | GPL-2.0+ | PDF → JPEG для визуального QA | `apt install poppler-utils`, `brew install poppler` |
| [`defusedxml`](https://pypi.org/project/defusedxml/) | PSF | Безопасный парсинг XML | `pip install defusedxml` |
| [`lxml`](https://lxml.de/) | BSD-style | XSD-валидация | `pip install lxml` |

### 3.4. Итог по `docx`

**Оригинальный код Anthropic** (всё кроме schemas):

- `SKILL.md` — ~590 строк проза (proprietary формулировки)
- `scripts/comment.py` — ~200 строк Python
- `scripts/accept_changes.py` — ~135 строк Python + 15 строк StarBasic
- `scripts/templates/*.xml` — 5 OOXML-скелетов
- `scripts/office/*` — см. §2 (общая часть)

**Всё остальное (schemas, внешние инструменты, библиотеки)** — публичные
стандарты и open-source. Переписывается с нуля за 1–2 дня.

---

## 4. Скилл `pptx`

Делит общую инфраструктуру `scripts/office/` (§2) с `docx` и `xlsx`. Кроме
общего, у pptx свои документы и три дополнительных скрипта.

### 4.1. Три markdown-файла

- **`SKILL.md`** (~230 строк) — entry point. Quick reference, рабочие
  процессы, блок «Design Ideas» с цветовыми палитрами, типографикой,
  layout-рекомендациями и QA-процессом (обязательный рендер в JPG через
  LibreOffice+pdftoppm и проверка суб-агентом).
- **`pptxgenjs.md`** — детали создания слайдов «с нуля» через
  [`pptxgenjs`](https://gitbrent.github.io/PptxGenJS/) (MIT).
- **`editing.md`** — детали редактирования существующих `.pptx` через
  unpack → manipulate slides → clean → pack.

Дизайн-рекомендации из SKILL.md (цветовые палитры вроде «Midnight
Executive», «Coral Energy», «Ocean Gradient» + типографические пары
Georgia+Calibri, Impact+Arial и т.д.) — собственность Anthropic. Идея
сама по себе не защищена — «подобрать цветовую палитру под тему» любой
дизайнер посоветует. Но конкретные наборы hex-кодов лучше в свой
SKILL.md не переносить, придумать свои (на базе, например, публичных
ресурсов типа [Coolors](https://coolors.co/) или
[Paletton](https://paletton.com/)).

### 4.2. Скрипты, специфичные для pptx

**`scripts/add_slide.py`** (~150 строк)

Добавляет новый слайд в распакованный `.pptx` — либо дублирует
существующий `slideN.xml`, либо создаёт пустой из layout'а. Обновляет
`ppt/presentation.xml`, `ppt/_rels/`, Content Types.

Оригинальный код Anthropic, но задача описана в
[ECMA-376 Part 1 §17 PresentationML](https://ecma-international.org/publications-and-standards/standards/ecma-376/).
Легко переписать.

**`scripts/thumbnail.py`** (~200 строк)

Создаёт сетку миниатюр из `.pptx`:
1. Конвертирует `.pptx → .pdf` через `soffice --headless --convert-to pdf`.
2. Конвертирует PDF → картинки через `pdftoppm` (Poppler).
3. Собирает grid через Pillow (`PIL.Image.new` + `paste`).
4. Подписывает каждую миниатюру именем XML-файла слайда (для
   быстрого поиска нужного слайда в unpacked/).

Библиотеки: `defusedxml`, `Pillow` (HPND-лицензия — open source,
совместима с любым использованием).

**`scripts/clean.py`** (~не читал, но по контексту)

Чистит боллерплейт, оставленный от шаблонов (lorem ipsum, XXX-placeholder'ы,
«this layout»-маркеры). Та же задача описывается и через `grep -iE`
прямо в SKILL.md.

### 4.3. Внешние инструменты

Как у `docx`, плюс:

| Инструмент | Лицензия | Для чего |
|---|---|---|
| [`pptxgenjs`](https://github.com/gitbrent/PptxGenJS) (npm) | MIT | Создание `.pptx` «с нуля» |
| [`markitdown`](https://github.com/microsoft/markitdown) | MIT | Извлечение текста `.pptx → md` |
| [`Pillow`](https://python-pillow.org/) | HPND | Миниатюры |

### 4.4. Итог по `pptx`

| Компонент | Оригинальность |
|---|---|
| `SKILL.md` + `editing.md` + `pptxgenjs.md` (всего ~800 строк прозы) | Anthropic (proprietary) |
| `scripts/add_slide.py` | Anthropic |
| `scripts/thumbnail.py` | Anthropic (тривиальный PIL-код) |
| `scripts/clean.py` | Anthropic |
| `scripts/office/*` | см. §2 |
| Палитры, типографические пары | Anthropic (придумайте свои) |

---

## 5. Скилл `xlsx`

Опять же общая `scripts/office/` + один дополнительный скрипт.

### 5.1. `SKILL.md` (~290 строк)

Основные темы:

- **Financial models conventions**: цветовое кодирование (blue =
  hardcoded inputs, black = formulas, green = cross-sheet links,
  red = external links, yellow background = key assumptions). Это
  индустриальный стандарт инвестбанков и аудиторов — описан в каждой
  книге по финансовому моделированию (Макабак, Пиньятаро, Розенбаум).
- **Number formatting**: `$#,##0;($#,##0);-` для валют, `0.0%` для
  процентов, `0.0x` для мультипликаторов, скобки для отрицательных.
- **Formula construction**: отдельные assumption cells, cell references
  вместо хардкодов, `$B$6` для абсолютных ссылок, комментарии-источники
  (`Source: 10-K, FY2024, Page 45`).
- **Recalc mandatory**: после openpyxl формулы лежат строками, нужен
  прогон через LibreOffice (`recalc.py`).
- **Pandas vs openpyxl**: pandas для bulk/analysis, openpyxl для
  formatting/formulas/merged cells.

Факты объективные. Формулировки — Anthropic.

### 5.2. Скрипты, специфичные для xlsx

**`scripts/recalc.py`** (~120 строк)

Тот же приём, что в `docx/accept_changes.py`: StarBasic-макрос через
`soffice`. Макрос:

```starbasic
Sub RecalculateAndSave()
    ThisComponent.calculateAll()
    ThisComponent.store()
    ThisComponent.close(True)
End Sub
```

После запуска открывает результат через `openpyxl` и сканирует все
ячейки на ошибки (`#REF!`, `#DIV/0!`, `#VALUE!`, `#N/A`, `#NAME?`),
возвращает JSON с локациями.

**Как переписать:** макрос тривиальный (см. [Ask
LibreOffice](https://ask.libreoffice.org/) — десятки примеров с
`calculateAll()`), обёртка — 50 строк Python с openpyxl.

### 5.3. Внешние инструменты

| Инструмент | Лицензия | Для чего |
|---|---|---|
| [`openpyxl`](https://openpyxl.readthedocs.io/) | MIT-style | Создание/редактирование `.xlsx` |
| [`pandas`](https://pandas.pydata.org/) | BSD-3 | Анализ, bulk operations |
| LibreOffice | MPL-2.0 | Recalc формул |

### 5.4. Итог по `xlsx`

Самый «маленький» скилл из офисных — только один специфичный скрипт
плюс общая инфраструктура. Основная ценность — SKILL.md с финансовыми
конвенциями (которые и так публичны, но хорошо систематизированы).

---

## 6. Скилл `pdf`

Полностью отдельный — не пересекается с `scripts/office/`, потому что
PDF это не ZIP-с-XML, а совершенно другой бинарный формат
(PostScript-подобный).

### 6.1. Три markdown-файла

- **`SKILL.md`** (~315 строк) — quick reference по библиотекам, базовые
  операции: merge, split, extract text/tables, create, watermark, OCR,
  password.
- **`REFERENCE.md`** — расширенные примеры и troubleshooting.
- **`FORMS.md`** — заполнение PDF-форм (AcroForm, XFA).

### 6.2. Скрипты

Список специфичных скриптов:

```
scripts/
├── check_fillable_fields.py          # проверка какие поля есть в PDF
├── extract_form_field_info.py        # извлечение метаданных полей
├── extract_form_structure.py         # структура формы целиком
├── fill_fillable_fields.py           # заполнение через pypdf
├── fill_pdf_form_with_annotations.py # заполнение с визуальным overlay
├── check_bounding_boxes.py           # проверка позиций полей
├── create_validation_image.py        # рендер PDF для визуальной проверки
└── convert_pdf_to_images.py          # PDF → PNG через pdf2image
```

Каждый скрипт — тонкая обёртка вокруг публичных библиотек. Пример
`convert_pdf_to_images.py` — буквально 30 строк `pdf2image.convert_from_path`
с resize через Pillow. `fill_fillable_fields.py` — обёртка вокруг
`pypdf.PdfReader/PdfWriter` с валидацией схемы.

### 6.3. Внешние инструменты (все open-source!)

| Инструмент | Лицензия | Для чего |
|---|---|---|
| [`pypdf`](https://pypdf.readthedocs.io/) | BSD-3 | Merge/split/rotate/encrypt |
| [`pdfplumber`](https://github.com/jsvine/pdfplumber) | MIT | Text + table extraction с layout |
| [`reportlab`](https://www.reportlab.com/opensource/) | BSD | Создание PDF |
| [`pdf2image`](https://github.com/Belval/pdf2image) | MIT | PDF → PIL.Image (использует poppler) |
| [`pdfplumber`](https://github.com/jsvine/pdfplumber) | MIT | Layout-aware extraction |
| [`pypdfium2`](https://github.com/pypdfium2-team/pypdfium2) | Apache-2.0 / PDFium BSD | Быстрый рендеринг PDF |
| [`pytesseract`](https://github.com/madmaze/pytesseract) | Apache-2.0 | OCR (wraps Tesseract) |
| [`Pillow`](https://python-pillow.org/) | HPND | Работа с изображениями |
| [`pdf-lib`](https://pdf-lib.js.org/) (JS) | MIT | Создание/редактирование PDF в Node |
| [Poppler](https://poppler.freedesktop.org/) | GPL-2.0+ | `pdftotext`, `pdftoppm`, `pdfimages` |
| [qpdf](http://qpdf.sourceforge.net/) | Apache-2.0 | CLI merge/split/rotate |
| [Tesseract](https://github.com/tesseract-ocr/tesseract) | Apache-2.0 | OCR-движок |

### 6.4. Итог по `pdf`

Единственный скилл, который **почти полностью** состоит из вызовов
публичных open-source библиотек — никакого проприетарного «секретного
соуса» в Python-скриптах нет. Вся интеллектуальная ценность в SKILL.md
и REFERENCE.md (систематизация того, какой инструмент для какой задачи).

Пересоздать аналог на open-source базе — тривиально: все библиотеки
стабильно зрелые, API документированы, примеры в README.

---

## 7. Сводная матрица: где что взять

| Блок | Скилл | Что делает | Чем заменить |
|---|---|---|---|
| `schemas/ISO-IEC29500-4_2016/` | docx/pptx/xlsx | XSD стандарта OOXML | [Ecma-376 (бесплатно)](https://ecma-international.org/publications-and-standards/standards/ecma-376/) |
| `schemas/microsoft/` | docx/pptx/xlsx | Расширения Microsoft | [MS Learn + Open Specification Promise](https://learn.microsoft.com/en-us/openspecs/) |
| `schemas/ecma/fouth-edition/opc-*` | docx/pptx/xlsx | Open Packaging Conventions | Ecma-376, часть 2 |
| `schemas/*/xml.xsd`, `mce/mc.xsd` | docx/pptx/xlsx | W3C XML namespace | [W3C](https://www.w3.org/2001/xml.xsd) |
| `soffice.py` | docx/pptx/xlsx | Обёртка LibreOffice + LD_PRELOAD shim | Написать свою (~100 строк), shim — по образцу [libfaketime](https://github.com/wolfcw/libfaketime) |
| `unpack.py` / `pack.py` | docx/pptx/xlsx | OOXML ZIP → dir и обратно | Написать свой (~300 строк) или использовать `python-docx`/`openpyxl`/`python-pptx` |
| `validate.py` + `validators/` | docx/pptx/xlsx | XSD + кастомные проверки | `lxml.etree.XMLSchema` + свой код (~400 строк) |
| `helpers/merge_runs.py`, `simplify_redlines.py` | docx (и в других скопирован) | Схлопывание run'ов, слияние правок | Своя имплементация (~200 строк) |
| `accept_changes.py` | docx | `AcceptAllTrackedChanges` via StarBasic | Макрос из [Ask LibreOffice](https://ask.libreoffice.org/) |
| `recalc.py` | xlsx | `calculateAll` via StarBasic | То же, тривиальный макрос |
| `comment.py` + templates | docx | Добавление комментариев в распакованный .docx | Своя имплементация по [MS-DOCX](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-docx/) |
| `add_slide.py`, `thumbnail.py`, `clean.py` | pptx | Слайдовые операции | Своя имплементация + PIL + soffice |
| Все PDF-скрипты | pdf | Form fill / convert / OCR | Обёртки вокруг `pypdf`, `pdfplumber`, `pdf2image`, `reportlab` |
| SKILL.md каждого | все | Best practices, conventions | **Пишется своими словами** со ссылками на issue-трекеры и стандарты |
| `docx-js`, `pptxgenjs`, `pypdf`, `openpyxl`, `pandas`, `Pillow`, `lxml`, `defusedxml`, `pandoc`, LibreOffice, Poppler, Tesseract | все | Внешние зависимости | Все уже open-source. Просто `pip install` / `npm install` / `apt install` |

---

## 8. План миграции на собственный open-source набор

Приоритет — сначала общая инфраструктура (чтобы все три OOXML-скилла
могли переехать разом), потом специфика каждого.

### Шаг 1. Общие модули (работают для docx/pptx/xlsx)

```
Universal-skills/
├── common/
│   ├── LICENSE                        # Apache-2.0 или MIT
│   ├── README.md
│   ├── THIRD_PARTY_NOTICES.md         # атрибуция Ecma, Microsoft, W3C
│   ├── soffice/
│   │   ├── wrapper.py                 # ~100 строк, ваш код
│   │   └── shim/
│   │       ├── lo_socket_shim.c       # по образцу libfaketime
│   │       └── build.sh
│   ├── ooxml/
│   │   ├── unpack.py                  # ~150 строк
│   │   ├── pack.py                    # ~150 строк
│   │   ├── validators/
│   │   │   ├── base.py
│   │   │   ├── docx_validator.py
│   │   │   ├── pptx_validator.py
│   │   │   └── xlsx_validator.py
│   │   └── schemas/
│   │       ├── ecma-376/              # из Ecma-пакета
│   │       ├── microsoft/             # из MS Learn
│   │       └── w3c/
│   └── macros/
│       ├── accept_tracked_changes.xba
│       └── recalculate_and_save.xba
```

### Шаг 2. Скиллы `my-docx` / `my-pptx` / `my-xlsx` / `my-pdf`

```
Universal-skills/
├── skills/
│   ├── my-docx/
│   │   ├── SKILL.md                   # свой текст
│   │   ├── scripts/
│   │   │   ├── md2docx.js             # уже у вас
│   │   │   ├── add_comment.py         # своя реализация
│   │   │   └── accept_changes.py      # тонкая обёртка над common/macros
│   │   └── README.md
│   ├── my-pptx/
│   │   ├── SKILL.md                   # свой текст + свои палитры
│   │   ├── scripts/
│   │   │   ├── md2pptx.js             # новый, в стиле md2docx.js
│   │   │   ├── add_slide.py
│   │   │   ├── thumbnail.py
│   │   │   └── clean.py
│   │   └── README.md
│   ├── my-xlsx/
│   │   ├── SKILL.md                   # свой текст
│   │   ├── scripts/
│   │   │   ├── csv2xlsx.py            # новый
│   │   │   ├── json2xlsx.py           # новый
│   │   │   └── recalc.py              # тонкая обёртка над common/macros
│   │   └── README.md
│   └── my-pdf/
│       ├── SKILL.md
│       ├── scripts/
│       │   ├── md2pdf.py              # новый (weasyprint / reportlab)
│       │   ├── html2pdf.py            # новый (playwright / weasyprint)
│       │   └── fill_form.py           # обёртка pypdf
│       └── README.md
```

### Шаг 3. Плагин для Cowork

```
Universal-skills/
├── .claude-plugin/
│   └── plugin.json
```

Содержимое `plugin.json`:

```json
{
  "name": "universal-skills",
  "version": "0.1.0",
  "description": "Open-source variants of docx/pptx/xlsx/pdf skills",
  "author": "MatrixFounder",
  "license": "Apache-2.0"
}
```

Скиллы в `skills/my-*` автоматически подхватятся, если лежат в корне
плагина (не внутри `.claude-plugin/`).

### Шаг 4. Атрибуция

`THIRD_PARTY_NOTICES.md` должен перечислить всё стороннее. Шаблон:

```markdown
# Third-Party Notices

## XML Schema Definitions

Copies of OOXML XSD schemas are distributed under:

- **ECMA-376 / ISO/IEC 29500** (Ecma International open specification)
  Source: https://ecma-international.org/publications-and-standards/standards/ecma-376/

- **Microsoft Open Specification Promise** (for Microsoft namespace extensions
  `w14`, `w15`, `w16cid`, `w16cex`, `w16du`, `w16sdtdh`, `w16sdtfl`, `w16se`)
  Source: https://learn.microsoft.com/en-us/openspecs/office_standards/

- **W3C Document License** (for `xml.xsd`)
  Source: https://www.w3.org/2001/xml.xsd

## Python Libraries

- `lxml` — BSD-style license
- `defusedxml` — PSF License
- `openpyxl` — MIT-style license
- `pandas` — BSD-3-Clause
- `pypdf` — BSD-3-Clause
- `pdfplumber` — MIT License
- `reportlab` — BSD License
- `Pillow` — HPND License
- `pdf2image` — MIT License

## JavaScript Libraries

- `docx` (docx-js) — MIT License
- `pptxgenjs` — MIT License
- `pdf-lib` — MIT License

## External Tools

- `LibreOffice` / `soffice` — MPL-2.0
- `Poppler` — GPL-2.0+
- `Pandoc` — GPL-2.0+
- `Tesseract` — Apache-2.0
- `qpdf` — Apache-2.0
```

---

## 9. Каталог рекомендуемых скриптов

Самая ценная часть — конкретный набор утилит, которые стоит написать
по образцу вашего `md2docx.js`. Идея одна и та же: вместо того чтобы
каждый раз собирать документ через низкоуровневый API, один раз пишем
быстрый детерминированный конвертер, кладём его в `skills/my-*/scripts/`,
а в `SKILL.md` прописываем: «для задачи X используй этот скрипт, а
низкоуровневый API — только если задача не покрывается».

### 9.0. Общие соглашения

Единый стиль для всех скриптов в репозитории:

- **Один файл = один скрипт.** Не дробить на модули внутри скилла,
  кроме случаев переиспользования кода между скиллами (тогда выносить
  в `common/`).
- **Именование:**
  - Конвертеры: `<from>2<to>.<ext>` — `md2docx.js`, `csv2xlsx.py`.
  - Операции над форматом: `<format>_<action>.<ext>` — `pdf_merge.py`,
    `xlsx_recalc.py`, `docx_fill_template.py`.
- **CLI-интерфейс:** всегда `script input output [options]`. Помощь по
  `--help`. Exit-code 0 — успех, ненулевой — ошибка. Stderr — прогресс
  и ошибки, stdout — структурированный результат (JSON) если надо.
- **Shebang:** `#!/usr/bin/env python3` или `#!/usr/bin/env node`,
  чтобы запускалось напрямую после `chmod +x`.
- **Никаких `print("Done!")`** — скрипт должен быть дружелюбен к
  пайпам и другим скриптам.
- **Зависимости** фиксируются в `scripts/requirements.txt` (Python) или
  `scripts/package.json` (Node) на уровне скилла.
- **README.md в каждом скилле** со списком всех скриптов и одной строкой
  описания — чтобы Claude (и вы) мог быстро найти нужный без чтения
  кода.

---

### 9.1. Скрипты для `my-docx`

#### md2docx.js *(уже у вас)*

**Назначение:** Markdown → .docx.
Пайплайн в общем виде: парсинг MD в AST (marked/remark) → обход дерева
с преобразованием узлов в элементы `docx-js` → `Packer.toBuffer` → запись
файла.

#### html2docx.js

**Назначение:** HTML → .docx с сохранением форматирования.

**CLI:** `html2docx.js input.html output.docx [--page-size letter|a4] [--landscape]`

**Логика:**

1. Парсим HTML через `cheerio` (MIT) — получаем DOM-подобное дерево.
2. Обходим узлы рекурсивно и маппим:
   - `h1/h2/h3` → `Paragraph({ heading: HeadingLevel.HEADING_N })`
   - `p` → `Paragraph({ children: [TextRun(text)] })`
   - `strong/b` → `TextRun({ bold: true })`, `em/i` → `italics: true`
   - `code` → `TextRun({ font: "Consolas", shading: {...} })`
   - `ul/ol/li` → `Paragraph({ numbering: { reference, level } })`
   - `table/tr/td` → `Table/TableRow/TableCell` с правильными dual widths
   - `img` → `ImageRun` (скачиваем remote URL заранее или читаем локально)
   - `a` → `ExternalHyperlink`
3. Извлекаем минимальный подмножество CSS из `style=""` и `<style>` —
   поддерживаем `color`, `background-color`, `font-weight`, `font-style`,
   `text-align`, `font-size`.
4. Для страничных настроек читаем `@page`-правило если есть.
5. Собираем `Document`, пишем через `Packer.toBuffer`.

**Зависимости:** `cheerio` (MIT), `docx` (MIT), `node-fetch` для remote
картинок.

**Подводные камни:**
- Полноценная поддержка CSS невозможна — честно ограничиться подмножеством
  и выводить warning для неподдерживаемых свойств.
- Absolute positioning (`position: absolute`) в docx не ложится — игнорировать.
- Flexbox/grid не мапится — превращать в таблицы или игнорировать.

#### docx2md.py

**Назначение:** .docx → Markdown (обратный конвертер).

**CLI:** `docx2md.py input.docx output.md [--preserve-tracked-changes]`

**Логика (два варианта):**

*Вариант A (проще и качественнее):* `pandoc input.docx -t gfm -o output.md`.
Скрипт просто валидирует входной файл и вызывает pandoc через subprocess.
Работает отлично, но требует установленного pandoc.

*Вариант B (чистый Python):* парсим `word/document.xml` через `python-docx`
или напрямую через `lxml`, обходим параграфы, генерируем Markdown:
- стили `Heading 1/2/3` → `#`/`##`/`###`
- `<w:b/>` в `<w:rPr>` → `**text**`
- списки → `-` с отступами по уровню
- таблицы → GFM-таблицы
- ссылки → `[text](url)` (вытаскивать из relationships)

**Зависимости:** `pandoc` (Вариант A) или `python-docx` (Вариант B, MIT).

**Подводные камни:**
- Tracked changes по умолчанию «применяются» при экспорте — для
  сохранения использовать `pandoc --track-changes=all`.
- Картинки: pandoc кладёт в `media/`, надо об этом сказать через
  `--extract-media=./assets`.

#### docx_fill_template.py

**Назначение:** Заполнить шаблон с плейсхолдерами `{{variable}}` данными.

**CLI:** `docx_fill_template.py template.docx data.json output.docx`

**Логика:**

1. Распаковать `template.docx` в tempdir.
2. Для `document.xml`, `header*.xml`, `footer*.xml`:
   - **Обязательно сначала merge_runs** — Word часто разбивает
     `{{name}}` на `{{` + `na` + `me` + `}}` в отдельных `<w:r>` из-за
     spell check. Без нормализации плейсхолдер не найдётся regex'ом.
   - Найти все `{{key}}` через regex и заменить на значения из `data.json`.
   - Поддержать условные блоки `{%if cond%}...{%endif%}` и циклы
     `{%for x in list%}...{%endfor%}` (как в Jinja2, для таблиц).
3. Упаковать обратно.

**Альтернатива готовой библиотекой:** [`docxtpl`](https://github.com/elapouya/python-docx-template)
(LGPL-2.1) — Jinja2 поверх python-docx, уже решает задачу сплит-ранов
и условных конструкций. Если лицензия устраивает, просто написать
тонкую CLI-обёртку над ней.

**Зависимости:** `python-docx` + своя логика, или `docxtpl`.

**Подводные камни:**
- Split runs — главный враг.
- Плейсхолдеры в таблицах и картинках требуют особого синтаксиса.
- Escape-логика для `&`, `<`, `>` в значениях.

#### docx_merge.py

**Назначение:** Склеить несколько `.docx` в один.

**CLI:** `docx_merge.py output.docx file1.docx file2.docx [file3.docx ...]`

**Логика:**

*Вариант A (pandoc):* `pandoc file1.docx file2.docx -o output.docx`.
Работает, но теряет сложное форматирование.

*Вариант B (XML merge):* открыть первый файл как базу, для каждого
следующего вытащить `<w:body>` и добавить его содержимое в конец тела
базового. Ключевые проблемы:
- Relationships (изображения, гиперссылки) — пересчитать `rId`.
- Numbering — переиндексировать, иначе списки прервутся.
- Styles — слить, разрешая конфликты в пользу первого документа.
- Images — скопировать `word/media/*` с переименованием.

**Зависимости:** `python-docx`.

**Подводные камни:** конфликты стилей и ID — самое сложное. Для
простых случаев (текст без картинок/нумерации) хватит 50 строк,
для универсального решения — ~300.

#### docx_accept_changes.py

**Назначение:** Принять все tracked changes, получить «чистый» документ.

**CLI:** `docx_accept_changes.py input.docx output.docx`

**Логика:**

1. Установить StarBasic-макрос в профиль LibreOffice (один раз):
   ```starbasic
   Sub AcceptAllTrackedChanges()
       Dim dispatcher As Object
       dispatcher = createUnoService("com.sun.star.frame.DispatchHelper")
       dispatcher.executeDispatch(ThisComponent.CurrentController.Frame, _
           ".uno:AcceptAllTrackedChanges", "", 0, Array())
       ThisComponent.store()
       ThisComponent.close(True)
   End Sub
   ```
2. Скопировать `input.docx` в `output.docx` (LibreOffice сохранит in-place).
3. Запустить `soffice --headless --norestore
   vnd.sun.star.script:Standard.Module1.AcceptAllTrackedChanges?language=Basic&location=application output.docx`.
4. Проверить exit code.

**Альтернатива (pure Python, без LibreOffice):** распаковать docx,
в `document.xml` удалить все `<w:del>` блоки полностью, из `<w:ins>`
оставить только содержимое (удалить обёртку). Работает для простых
случаев, но ломается на сложных редлайнингах (перемещение блоков,
правки в `<w:pPr>`).

**Зависимости:** LibreOffice (`soffice`).

#### docx_add_comment.py

**Назначение:** Программно добавить комментарий к фрагменту текста.

**CLI:** `docx_add_comment.py input.docx output.docx --anchor "текст для
комментирования" --text "текст комментария" [--author "Имя"] [--parent N]`

**Логика:**

1. Распаковать docx.
2. Если `word/comments.xml` ещё не существует — создать из шаблона
   (пустой `<w:comments>` с нужными namespace'ами), добавить
   relationship в `document.xml.rels`, добавить Content Type.
3. Найти `<w:t>` с нужным anchor-текстом в `document.xml`.
4. Вставить вокруг найденного run'а пару `<w:commentRangeStart w:id="N"/>`
   и `<w:commentRangeEnd w:id="N"/>` как siblings (не inside).
5. После commentRangeEnd добавить `<w:r><w:rPr><w:rStyle
   w:val="CommentReference"/></w:rPr><w:commentReference w:id="N"/></w:r>`.
6. В `comments.xml` добавить `<w:comment w:id="N" w:author=""
   w:date="..."><w:p><w:r><w:t>текст</w:t></w:r></w:p></w:comment>`.
7. Если `--parent M` указан — добавить relationship parent/child в
   `commentsExtended.xml`.
8. Упаковать.

**Зависимости:** `lxml`.

**Подводные камни:**
- CommentRange-маркеры — siblings `<w:r>`, никогда не внутри. Это частая
  ошибка.
- ID должны быть уникальны — сканировать существующие `<w:comment w:id>`
  и брать `max + 1`.

---

### 9.2. Скрипты для `my-pptx`

#### md2pptx.js

**Назначение:** Markdown со слайдовой разметкой → .pptx.

**CLI:** `md2pptx.js input.md output.pptx [--theme themes/corporate.json]
[--size 16:9|4:3]`

**Формат входа:** слайды разделены `---` на отдельной строке. Первая
строка каждого слайда (`# Заголовок`) становится заголовком. Пустая
строка после заголовка — подзаголовок (по желанию). Остальное — тело.

**Логика:**

1. Читаем MD, делим по `^---$`.
2. Для каждого блока:
   - Первая `# ...` → `addText` с `{ x:0.5, y:0.3, w:9, h:1, fontSize:36, bold:true }`.
   - Если дальше `## ...` — это подзаголовок.
   - Списки `-`/`1.` → `addText` с `bullet: true`.
   - `![alt](path)` → `addImage`.
   - Таблицы `| ... |` → `addTable`.
   - Блоки кода ```` ``` ```` → `addText` с моноширинным шрифтом и
     заливкой.
   - Quote `> ...` → `addText` с крупным курсивом, цветом акцента.
3. Theme-JSON определяет палитру, шрифты, размеры. Дефолт —
   «Charcoal Minimal» (напишите свой).
4. Если описание слайда содержит только заголовок и одну картинку —
   использовать layout «half-bleed»: картинка на полслайда, заголовок
   рядом.
5. `pres.writeFile`.

**Зависимости:** `pptxgenjs` (MIT), `marked` (MIT) или `remark`
(MIT), `sharp` для обработки картинок.

**Подводные камни:**
- Text box padding: `pptxgenjs` добавляет невидимый padding, из-за
  которого «выровнять край текста с краем фигуры» не получается без
  `margin: 0`.
- Размер слайда: 16:9 = 10×5.625", 4:3 = 10×7.5". Не перепутать.
- Font fallback: не все компьютеры имеют ваш дизайнерский шрифт,
  закладывать безопасный fallback.

#### outline2pptx.py

**Назначение:** Структурированный YAML/JSON-план презентации → .pptx.

**CLI:** `outline2pptx.py outline.yaml output.pptx [--theme corporate]`

**Формат входа:**

```yaml
theme: corporate
title: Годовой отчёт 2025
author: ООО Ромашка
slides:
  - type: title
    title: "Годовой отчёт"
    subtitle: "2025 год"
  - type: content
    title: "Ключевые метрики"
    bullets:
      - "Выручка: +24% YoY"
      - "EBITDA-маржа: 18%"
      - "Новых клиентов: 340"
  - type: stat
    label: "Выручка"
    value: "₽ 2.1 млрд"
    sublabel: "+24% год к году"
  - type: image
    title: "Команда"
    image: "assets/team.jpg"
    caption: "38 сотрудников в 4 городах"
  - type: comparison
    title: "2024 vs 2025"
    left: { label: "2024", items: [...] }
    right: { label: "2025", items: [...] }
```

**Логика:**

1. Загружаем outline и theme.
2. Для каждого слайда — по `type` выбираем готовый layout (функция
   `render_title`, `render_content`, `render_stat` и т.д.), каждая
   функция использует `python-pptx` для позиционирования элементов с
   учётом темы.
3. Общие вещи — добавление номера слайда, колонтитула, логотипа —
   применяем ко всем слайдам кроме `type: title`.

**Зависимости:** `python-pptx` (MIT), `pyyaml` (MIT), `Pillow` для
обработки изображений.

**Подводные камни:**
- Позиционирование через EMU (914400 = 1 дюйм) — легко ошибиться с
  единицами.
- Bullet-списки в `python-pptx` требуют ручной настройки level через
  `pPr.lvl` — нет удобного API.

#### pptx_apply_theme.py

**Назначение:** Применить бренд-тему (цвета + шрифты) к существующей
презентации без переписывания контента.

**CLI:** `pptx_apply_theme.py input.pptx theme.json output.pptx`

**Формат темы:**

```json
{
  "colors": {
    "dk1": "000000",
    "lt1": "FFFFFF",
    "accent1": "1E2761",
    "accent2": "CADCFC",
    "hyperlink": "0563C1"
  },
  "fonts": {
    "major": "Georgia",
    "minor": "Calibri"
  }
}
```

**Логика:**

1. Распаковать `input.pptx`.
2. Найти `ppt/theme/theme1.xml`.
3. В `<a:clrScheme>` заменить значения для `dk1`, `lt1`, `accent1..6`,
   `hlink`, `folHlink`.
4. В `<a:fontScheme>` заменить `<a:majorFont><a:latin typeface="...">`
   и аналогично для `minor`.
5. Упаковать обратно.
6. (Опция) Удалить `ppt/media/*.ttf` если тема использует системные
   шрифты, чтобы файл стал легче.

**Зависимости:** `lxml`, `zipfile`.

**Подводные камни:**
- Если у слайд-мастера или конкретного слайда hardcoded-цвета вместо
  scheme-references (`<a:srgbClr val="1E2761"/>` вместо `<a:schemeClr
  val="accent1"/>`) — они не поменяются. Можно предусмотреть режим
  `--force`, который найдёт и заменит все вхождения старого accent-цвета.

#### pptx_thumbnails.py

**Назначение:** Сетка миниатюр для быстрого визуального обзора.

**CLI:** `pptx_thumbnails.py input.pptx output.jpg [--cols 3]`

**Логика:**

1. `soffice --headless --convert-to pdf input.pptx` → `input.pdf`.
2. `pdftoppm -jpeg -r 100 input.pdf tmp/slide` → `tmp/slide-1.jpg`, …
3. Через Pillow собрать grid: создать `Image.new` с размером
   `cols * thumb_w + padding` × `rows * (thumb_h + label_h) + padding`,
   итерировать по слайдам, `paste` каждую миниатюру в свою ячейку,
   `ImageDraw.text` подписать «Slide N» и имя XML-файла.
4. Сохранить с JPEG quality 95.

**Зависимости:** LibreOffice, Poppler (`pdftoppm`), `Pillow` (HPND).

**Подводные камни:**
- `pdftoppm` зеропадит номера по-разному в зависимости от количества
  страниц: `slide-1.jpg` для <10, `slide-01.jpg` для 10–99. Сортировать
  файлы через `sorted(..., key=lambda f: int(re.search(r'(\d+)', f).group(1)))`.

#### pptx_clean.py

**Назначение:** Вычистить placeholder-текст от шаблонов (lorem ipsum,
`XXX`, `[insert ...]`, `TODO`, «This slide layout»).

**CLI:** `pptx_clean.py input.pptx output.pptx [--check-only]`

**Логика:**

1. Распаковать.
2. Для каждого `ppt/slides/slide*.xml` — grep по regex:
   `\bx{3,}\b|lorem|ipsum|\bTODO\b|\[insert|this.*(slide|page).*layout`.
3. В режиме `--check-only` — вывести список найденных слайдов и exit 1
   если что-то нашли.
4. В обычном режиме — заменить найденное на пустую строку и упаковать.

**Зависимости:** только stdlib.

#### pptx_to_pdf.py *(тонкая обёртка)*

**Назначение:** Конвертация в PDF для печати/QA.

**CLI:** `pptx_to_pdf.py input.pptx [output.pdf]`

**Логика:** `soffice --headless --convert-to pdf --outdir <dir> <input>`.
20 строк Python.

---

### 9.3. Скрипты для `my-xlsx`

#### csv2xlsx.py

**Назначение:** CSV/TSV → хорошо оформленный `.xlsx` «из коробки».

**CLI:** `csv2xlsx.py input.csv output.xlsx [--delimiter auto|,|;|\t]
[--header-style bold] [--freeze-header] [--auto-filter] [--widths auto]`

**Логика:**

1. Определить разделитель: если `--delimiter auto`, пробовать `csv.Sniffer`.
2. Читать через `pandas.read_csv` с inferring типов.
3. Создать workbook через `openpyxl.Workbook`.
4. Записать данные (`ws.append`).
5. Стилизовать:
   - Заголовок: жирный, заливка `#F2F2F2`, выравнивание по центру.
   - Заморозить первую строку: `ws.freeze_panes = "A2"`.
   - Автофильтр: `ws.auto_filter.ref = ws.dimensions`.
   - Автоширина колонок: для каждой колонки посчитать `max(len(str(cell)))`
     (с разумным максимумом ~50) и `ws.column_dimensions[col].width = width + 2`.
6. Определить числовые колонки и применить формат `#,##0` или `0.00`.
7. Сохранить.

**Зависимости:** `pandas` (BSD-3), `openpyxl` (MIT-style).

**Подводные камни:**
- `pandas` любит превращать строки-числа в numeric — передавать
  `dtype=str` для колонок типа «Код», «Телефон», иначе ведущие нули
  пропадут.
- Encoding: детектить через `chardet` или пробовать utf-8/cp1251.

#### json2xlsx.py

**Назначение:** Структурированный JSON → мультилистовой workbook.

**CLI:** `json2xlsx.py input.json output.xlsx`

**Формат входа:**

```json
{
  "Продажи": [
    {"Дата": "2025-01-01", "Сумма": 120000, "Менеджер": "Иванов"},
    ...
  ],
  "Клиенты": [
    {"ID": "C001", "Название": "ООО Ромашка", "Город": "Москва"},
    ...
  ]
}
```

**Логика:**

1. Если корень — dict, каждый ключ становится именем листа, значение
   (list of dicts) — содержимым.
2. Если корень — list of dicts, создаётся один лист `Sheet1`.
3. Для каждого листа:
   - Собрать union всех ключей из всех объектов → колонки.
   - Заголовок = ключи.
   - Строки = значения.
4. Применить те же стилистические defaults что в `csv2xlsx.py`
   (выделить общий `apply_default_styles()` в shared-модуль).

**Зависимости:** `openpyxl`.

**Подводные камни:**
- Вложенные объекты — либо flatten через точечную нотацию
  (`user.email`), либо как JSON-строка в ячейке, либо отдельный лист
  со связкой по ID.

#### md_tables2xlsx.py

**Назначение:** Все markdown-таблицы из документа — в отдельные листы.

**CLI:** `md_tables2xlsx.py input.md output.xlsx`

**Логика:**

1. Читать MD построчно.
2. Найти блоки, начинающиеся с `|` и содержащие `|---|` во второй
   строке (GFM-таблица).
3. Для каждой таблицы определить имя листа — взять ближайший `##`-заголовок
   выше неё. Если заголовка нет — `Table1`, `Table2`, …
4. Распарсить таблицу, игнорируя separator-строку.
5. Писать в xlsx с дефолтной стилизацией.

**Зависимости:** `openpyxl`, минимальный MD-парсер (можно своими руками
на regex, или `markdown-it-py` MIT).

#### xlsx_recalc.py

**Назначение:** Принудительный пересчёт формул после openpyxl
(openpyxl сохраняет формулы как строки без значений).

**CLI:** `xlsx_recalc.py input.xlsx [--timeout 30]`

**Логика:** идентична `docx_accept_changes.py`, только макрос:

```starbasic
Sub RecalculateAndSave()
    ThisComponent.calculateAll()
    ThisComponent.store()
    ThisComponent.close(True)
End Sub
```

После запуска — опциональный scan всех ячеек на ошибки (`#REF!`,
`#DIV/0!` и т.д.) и возврат JSON со списком проблемных ячеек.

**Зависимости:** LibreOffice, `openpyxl` (для scan).

#### xlsx_validate.py

**Назначение:** Проверка на формульные ошибки без пересчёта
(если файл уже пересчитан).

**CLI:** `xlsx_validate.py input.xlsx` → JSON в stdout

**Логика:**

```python
wb = load_workbook(input, data_only=True)
errors = {}
for ws_name in wb.sheetnames:
    ws = wb[ws_name]
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("#"):
                if cell.value in {"#REF!","#DIV/0!","#VALUE!","#N/A","#NAME?","#NUM!","#NULL!"}:
                    errors.setdefault(cell.value, []).append(f"{ws_name}!{cell.coordinate}")
print(json.dumps({"errors": errors, "total": sum(len(v) for v in errors.values())}))
```

**Зависимости:** `openpyxl`.

**Подводные камни:**
- Если файл открыт в openpyxl без `data_only=True`, увидите формулы, а
  не значения. Именно поэтому важен предварительный `xlsx_recalc.py`.

#### xlsx_add_chart.py

**Назначение:** Добавить график по JSON-спеке.

**CLI:** `xlsx_add_chart.py input.xlsx chart.json [--sheet Sheet1] [--anchor E2]`

**Формат спеки:**

```json
{
  "type": "line",
  "title": "Выручка по месяцам",
  "data_range": "B2:B13",
  "categories_range": "A2:A13",
  "x_axis_title": "Месяц",
  "y_axis_title": "Выручка, ₽"
}
```

**Логика:** маппинг type → openpyxl.chart-класс (`LineChart`, `BarChart`,
`PieChart`, `ScatterChart`), добавление Reference, заполнение title/axes,
`ws.add_chart(chart, anchor)`.

**Зависимости:** `openpyxl`.

---

### 9.4. Скрипты для `my-pdf`

#### md2pdf.py

**Назначение:** Markdown → красивый PDF.

**CLI:** `md2pdf.py input.md output.pdf [--css styles.css] [--page-size A4|Letter]`

**Логика:**

*Вариант A (pandoc):*
`pandoc input.md -o output.pdf --pdf-engine=weasyprint --css=styles.css`.

*Вариант B (pure Python):*
1. `md → html` через `markdown2` (MIT) или `markdown-it-py`.
2. Обернуть HTML в шаблон с `<head><link rel="stylesheet" href="default.css"></head>`.
3. `weasyprint.HTML(string=html).write_pdf(output, stylesheets=[css])`.

**Зависимости:** `weasyprint` (BSD-3) или pandoc.

**Подводные камни:**
- Шрифты: weasyprint ищет системные. Для воспроизводимости лучше
  указывать `@font-face` в CSS с явной ссылкой на TTF.
- Code highlighting: если нужен — `pygments` + CSS.

#### html2pdf.py

**Назначение:** HTML → PDF с полной поддержкой современного CSS/JS.

**CLI:** `html2pdf.py input.html output.pdf [--wait 2000] [--landscape]`

**Логика:** через `playwright` (Apache-2.0):

```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(f"file://{abspath(input)}")
    page.wait_for_load_state("networkidle")
    page.pdf(path=output, format="Letter", landscape=args.landscape,
             print_background=True)
```

**Зависимости:** `playwright` + `playwright install chromium` (GB-
размер).

**Подводные камни:**
- Для маленьких задач weasyprint проще и легче; playwright нужен
  только если HTML использует flexbox/grid/современный JS/Canvas/SVG
  со сложной typography.
- `print_background=True` обязательно — иначе белые фоны всех элементов.

#### pdf_merge.py / pdf_split.py / pdf_extract_text.py / pdf_extract_tables.py

Простые обёртки над `pypdf` и `pdfplumber`, по 20–40 строк каждая.
Выносить в отдельный скрипт ради консистентности CLI и возможности
вызова из SKILL.md:

```bash
pdf_merge.py output.pdf a.pdf b.pdf c.pdf
pdf_split.py input.pdf --ranges "1-5:part1.pdf,6-10:part2.pdf"
pdf_extract_text.py input.pdf --layout  # layout-preserving
pdf_extract_tables.py input.pdf --output tables.xlsx  # все таблицы в xlsx
```

**Зависимости:** `pypdf` (BSD-3), `pdfplumber` (MIT).

#### pdf_ocr.py

**Назначение:** Добавить searchable text layer к сканированному PDF.

**CLI:** `pdf_ocr.py input.pdf output.pdf [--lang rus+eng] [--dpi 300]`

**Логика:**

1. `pdf2image.convert_from_path(input, dpi=300)` → список PIL-Image.
2. Для каждой страницы `pytesseract.image_to_data(image, lang=lang,
   output_type=Output.DICT)` — получить слова с координатами (bounding
   boxes).
3. Через `reportlab.pdfgen.canvas` создать новый PDF того же размера,
   где:
   - Как фон — оригинальная картинка страницы.
   - Поверх — невидимый текст (`setFillColorRGB(1,1,1)` + `setFillAlpha(0)`)
     в позициях слов из OCR.
4. Сохранить через `pypdf` или просто финализировать canvas.

**Альтернатива:** готовая тулза [`ocrmypdf`](https://ocrmypdf.readthedocs.io/)
(MPL-2.0) делает ровно это, тонкий CLI-wrapper над ней — 20 строк.
Для большинства случаев лучше использовать её.

**Зависимости:** `pdf2image`, `pytesseract`, Tesseract, `reportlab` —
либо `ocrmypdf` одной зависимостью.

**Подводные камни:**
- DPI: <200 плохо распознаётся, >400 раздувает файл. Золотая середина — 300.
- Словарь языков: `rus`, `eng`, можно комбинировать `rus+eng`. Убедиться,
  что `tesseract-ocr-rus` установлен (`apt install tesseract-ocr-rus`).

#### pdf_compress.py

**Назначение:** Уменьшить размер PDF.

**CLI:** `pdf_compress.py input.pdf output.pdf [--quality screen|ebook|printer|prepress]`

**Логика:** обёртка над ghostscript:

```bash
gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/ebook \
   -dNOPAUSE -dBATCH -sOutputFile=output.pdf input.pdf
```

Уровни `PDFSETTINGS`: `/screen` (72 dpi, мелко), `/ebook` (150 dpi,
средне), `/printer` (300 dpi, крупно), `/prepress` (300 dpi + сохранение
цветов).

**Зависимости:** Ghostscript (AGPL-3.0 или коммерческая — аккуратно с
лицензией для коммерческих продуктов!).

**Альтернатива:** `pypdf` с `compress_content_streams()` — медленнее
и менее эффективно, но MIT-совместимо.

#### pdf_watermark.py

**Назначение:** Наложить водяной знак на все страницы.

**CLI:** `pdf_watermark.py input.pdf output.pdf --text "DRAFT" [--opacity 0.2]
[--angle 45] [--color CCCCCC]`

**Логика:**

1. Создать одностраничный PDF-водяной-знак через `reportlab`:
   ```python
   c = canvas.Canvas("wm.pdf", pagesize=letter)
   c.setFillColorRGB(0.8, 0.8, 0.8, alpha=0.2)
   c.setFont("Helvetica-Bold", 80)
   c.saveState()
   c.translate(width/2, height/2)
   c.rotate(45)
   c.drawCentredString(0, 0, "DRAFT")
   c.restoreState()
   c.save()
   ```
2. Через `pypdf` для каждой страницы входного PDF — `page.merge_page(wm_page)`.
3. Записать результат.

**Зависимости:** `pypdf`, `reportlab`.

**Подводные камни:** размер страницы водяного знака должен совпадать
с размером целевого PDF, иначе он сместится. Читать `page.mediabox`
первого файла и подгонять под него.

#### pdf_fill_form.py

**Назначение:** Заполнить AcroForm-поля в PDF.

**CLI:** `pdf_fill_form.py input.pdf data.json output.pdf [--flatten]`

**Логика:**

1. `reader = PdfReader(input)`.
2. Если `reader.get_form_text_fields()` — словарь имён полей.
3. `writer = PdfWriter(clone_from=reader)`.
4. Для каждой страницы `writer.update_page_form_field_values(page, data)`.
5. Если `--flatten` — «запечь» значения, чтобы их нельзя было изменить
   (упрощённо: удалить AcroForm-объект и превратить появившийся текст в
   статичный слой).
6. Сохранить.

**Зависимости:** `pypdf` (BSD-3).

**Подводные камни:**
- Checkbox'ы: значение `/Yes` или `/Off`, не `true`/`false`.
- Radio buttons: значение — это имя выбранной кнопки (export value), а
  не индекс.
- XFA-формы (те, что сделаны в LiveCycle) через pypdf не заполняются —
  для них нужны коммерческие либо `pdf-lib` в Node.

---

### 9.5. Общие скрипты в `common/`

Всё, что переиспользуется между скиллами, выносится сюда.

#### common/soffice_wrapper.py

**Назначение:** Безопасный запуск LibreOffice headless.

**CLI:** `soffice_wrapper.py [soffice args...]`

**Логика:**

1. Определить, нужен ли LD_PRELOAD shim: попытаться создать
   `socket.socket(AF_UNIX, SOCK_STREAM)`, если `OSError` — нужен.
2. Если shim нужен — скомпилировать его из `common/soffice/shim/lo_socket_shim.c`
   через `gcc -shared -fPIC -o /tmp/shim.so shim.c -ldl` (один раз).
3. Собрать env: `SAL_USE_VCLPLUGIN=svp`, `LD_PRELOAD=/tmp/shim.so` если нужно.
4. `subprocess.run(["soffice"] + args, env=env)`.

**Используется:** `docx_accept_changes.py`, `xlsx_recalc.py`, `pptx_to_pdf.py`,
`pptx_thumbnails.py`.

#### common/preview.py

**Назначение:** Универсальный превью: любой офисный файл → папка с
PNG-картинками страниц/слайдов.

**CLI:** `preview.py input.{docx,pptx,xlsx,pdf} output_dir/ [--dpi 150]`

**Логика:**

```python
ext = Path(input).suffix.lower()
if ext == ".pdf":
    pdf = input
else:
    # docx/pptx/xlsx → pdf через LibreOffice
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", tmpdir, input])
    pdf = tmpdir / f"{stem}.pdf"
# pdf → картинки
subprocess.run(["pdftoppm", "-png", "-r", str(dpi), pdf, f"{output_dir}/page"])
```

**Зачем:** любой скилл может использовать для визуального QA. Claude
получает картинки, которые можно передать в Read tool для реальной
визуальной проверки.

**Зависимости:** LibreOffice, Poppler.

#### common/validate_ooxml.py

**Назначение:** Универсальный XSD-валидатор для OOXML (docx/pptx/xlsx).

**CLI:** `validate_ooxml.py input.{docx,pptx,xlsx} [--verbose]`

**Логика:** по расширению выбирает набор схем из `common/schemas/`,
распаковывает файл в tempdir, валидирует каждый XML через
`lxml.etree.XMLSchema`, выводит errors.

**Зависимости:** `lxml`, `defusedxml`.

---

### 9.6. Матрица «скилл → что есть → что добавить»

| Скилл | Есть у вас | Приоритет добавить | Полезно добавить позже |
|---|---|---|---|
| `my-docx` | `md2docx.js` | `docx_fill_template.py`, `docx2md.py` | `html2docx.js`, `docx_merge.py`, `docx_accept_changes.py`, `docx_add_comment.py` |
| `my-pptx` | — | `md2pptx.js`, `outline2pptx.py`, `pptx_thumbnails.py` | `pptx_apply_theme.py`, `html2pptx.js`, `pptx_clean.py`, `pptx_to_pdf.py` |
| `my-xlsx` | — | `csv2xlsx.py`, `xlsx_recalc.py`, `xlsx_validate.py` | `json2xlsx.py`, `md_tables2xlsx.py`, `xlsx_add_chart.py` |
| `my-pdf` | — | `md2pdf.py`, `pdf_merge.py`, `pdf_split.py` | `html2pdf.py`, `pdf_ocr.py`, `pdf_watermark.py`, `pdf_fill_form.py`, `pdf_compress.py` |
| `common/` | — | `soffice_wrapper.py`, `preview.py` | `validate_ooxml.py` |

**Рекомендуемая последовательность:**

1. Сначала `common/soffice_wrapper.py` — на нём держится три других скилла.
2. Затем «приоритетные» конвертеры-оркестраторы каждого скилла
   (`md2pptx.js`, `csv2xlsx.py`, `md2pdf.py`). Они дадут моментальный
   прирост скорости работы Claude.
3. Утилиты для редактирования существующих файлов
   (`docx_fill_template`, `pptx_apply_theme`, `pdf_watermark`) — второй
   приоритет, нужны реже, но делают скиллы zcompletnee.
4. Всё остальное — по мере появления реальных сценариев.

### 9.7. Рекомендация по обновлению SKILL.md

Как только в скилле появляется скрипт — в `SKILL.md` должна появиться
соответствующая секция. Структура для Claude дружелюбна к такому виду:

```markdown
## Quick Reference

| Задача | Команда |
|---|---|
| Markdown → docx | `node scripts/md2docx.js input.md output.docx` |
| Заполнить шаблон | `python scripts/docx_fill_template.py tmpl.docx data.json out.docx` |
| Извлечь текст из docx | `python scripts/docx2md.py input.docx output.md` |
| …  | …  |

## When to use scripts vs. direct API

**Use scripts first.** Scripts are tested, deterministic, and fast.
Only drop down to direct `docx-js`/`python-docx` manipulation when
the scripts don't cover your case (e.g., complex programmatic formatting,
interactive editing of an existing document's XML).
```

Этот шаблон в SKILL.md — самое важное с точки зрения поведения Claude.
Если в Quick Reference чётко написано «для задачи X используй скрипт Y»,
Claude возьмёт именно его, а не полезет в низкоуровневый API. В этом
и состоит главная ценность подхода «скрипты в скилле» — детерминированность
поведения агента.

---

## 10. Что НЕЛЬЗЯ делать

Чтобы не нарваться на нарушение лицензии Anthropic:

1. **Не копировать текст `SKILL.md`** из `docx/pptx/xlsx/pdf` дословно.
   Переписывать своими словами (идеи не защищены, формулировки защищены).
2. **Не копировать Python-скрипты Anthropic** (`unpack.py`, `pack.py`,
   `validate.py`, `validators/*.py`, `merge_runs.py`, `simplify_redlines.py`,
   `comment.py`, `accept_changes.py`, `recalc.py`, `add_slide.py`,
   `thumbnail.py`, `clean.py` и PDF-скрипты). Писать свои реализации.
3. **Не копировать C-shim** `lo_socket_shim.c` дословно. Писать свой по
   образцу публичных LD_PRELOAD-примеров.
4. **Не копировать цветовые палитры и типографические пары** из
   `pptx/SKILL.md`. Придумывать свои.
5. **Не публиковать «форк» плагина Anthropic целиком** — даже если
   добавить свои правки, это будет derivative work.

Что **можно**:

- Брать XSD-схемы напрямую из Ecma/Microsoft/W3C (они ваши в рамках их
  лицензий, не Anthropic'овские).
- Писать свой код, решающий те же задачи, опираясь на публичные
  спецификации (ECMA-376, MS-DOCX, MS-PPTX, MS-XLSX, PDF ISO 32000-2).
- Использовать все перечисленные open-source библиотеки через обычный
  `pip install` / `npm install`.
- Называть свои скиллы как угодно (но не совпадающе с `docx/pptx/xlsx/pdf`,
  потому что иначе они не «переопределят» встроенные — используйте
  префикс `my-`, `universal-`, `u-` и т.п.).
- Форкать и модифицировать Apache-2.0 скиллы из `anthropics/skills`
  (`skill-creator`, `frontend-design`, `algorithmic-art` и т.д.) —
  с сохранением LICENSE и указанием Anthropic как автора оригинала.

---

## 11. Полезные ссылки одним списком

### Стандарты и спецификации

- [ECMA-376 (Office Open XML)](https://ecma-international.org/publications-and-standards/standards/ecma-376/)
- [ISO/IEC 29500](https://www.iso.org/standard/71691.html)
- [Microsoft Open Specification Promise](https://learn.microsoft.com/en-us/openspecs/dev_center/ms-devcentlp/51c5a3fd-e73a-4cec-b65c-3e4094d0ea12)
- [MS-DOCX спецификация](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-docx/)
- [MS-PPTX спецификация](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-pptx/)
- [MS-XLSX спецификация](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-xlsx/)
- [ISO 32000-2 (PDF 2.0)](https://www.iso.org/standard/75839.html)
- [W3C XML namespace schema](https://www.w3.org/2001/xml.xsd)

### Документация LibreOffice

- [Dispatch Commands](https://wiki.documentfoundation.org/Development/DispatchCommands)
- [UNO API Reference](https://api.libreoffice.org/)
- [Basic Macros](https://documentation.libreoffice.org/assets/Uploads/Documentation/en/BASIC_Guide/BasicGuide_OOo3.2.0.pdf)
- [Ask LibreOffice](https://ask.libreoffice.org/)
- [Common command-line options](https://wiki.documentfoundation.org/Common_command_line_options)

### Open-source библиотеки

- [`python-docx`](https://github.com/python-openxml/python-docx) (MIT)
- [`python-pptx`](https://github.com/scanny/python-pptx) (MIT)
- [`openpyxl`](https://foss.heptapod.net/openpyxl/openpyxl) (MIT-style)
- [`docx-js`](https://github.com/dolanmiu/docx) (MIT)
- [`pptxgenjs`](https://github.com/gitbrent/PptxGenJS) (MIT)
- [`pypdf`](https://github.com/py-pdf/pypdf) (BSD-3)
- [`pdfplumber`](https://github.com/jsvine/pdfplumber) (MIT)
- [`reportlab`](https://www.reportlab.com/opensource/) (BSD)
- [`weasyprint`](https://github.com/Kozea/WeasyPrint) (BSD-3) — html/css → PDF
- [`pdf-lib`](https://github.com/Hopding/pdf-lib) (MIT)
- [`markitdown`](https://github.com/microsoft/markitdown) (MIT)

### LD_PRELOAD техника

- [`libfaketime`](https://github.com/wolfcw/libfaketime) — канонический пример
- [`fakechroot`](https://github.com/dex4er/fakechroot)
- [Simple LD_PRELOAD tutorial](https://catonmat.net/simple-ld-preload-tutorial)

### Anthropic skills

- [anthropics/skills — публичный репо](https://github.com/anthropics/skills)
- [skill-creator (Apache-2.0) — можно форкать](https://github.com/anthropics/skills/tree/main/skills/skill-creator)

### Ваши существующие наработки

- [MatrixFounder/Universal-skills](https://github.com/MatrixFounder/Universal-skills)

---

*Документ подготовлен как карта для переписывания аналогов скиллов
Anthropic на open-source фундаменте. Не является юридической консультацией.*
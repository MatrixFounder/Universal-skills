# Постановка на доработку скила `docx`

**Дата:** 2026-06-05
**Автор постановки:** агент Claude Code (по итогам реальной задачи «генерация интеграционной архитектуры в .docx»)
**Скил:** `skills/docx` (master-копия OOXML-утилит; реплицируется в `xlsx`/`pptx`)
**Статус:** черновик к реализации
**Для кого:** агент/разработчик **без контекста** исходной задачи — ниже всё необходимое, чтобы воспроизвести и починить.

---

## 0. TL;DR

В ходе обычного сценария (Markdown → .docx с диаграммами Mermaid, затем вёрстка под **A4**) всплыли две независимые проблемы скила:

| # | Тип | Приоритет | Суть |
|---|---|---|---|
| **A** | Bug | **P0** | Python-скрипты падают с `ModuleNotFoundError`, потому что `SKILL.md` инструктирует вызывать их голым `python3`, а зависимости стоят только в `scripts/.venv`. Контракт `SKILL.md` ↔ `install.sh` рассогласован. |
| **B** | Feature | **P1** | `md2docx.js` жёстко прибит к US Letter. Нет способа сделать **A4 / landscape / поля**. Пришлось вручную патчить `<w:pgSz>` в zip. |
| **C** | Hardening | **P2** | Документированный fallback «unpack → edit → pack» сам нерабочий из-за проблемы A; `install.sh` молча оставляет окружение, в котором штатный `python3` без зависимостей. |

Цель доработки: чтобы тот же сценарий (md→docx с диаграммами + A4) проходил **штатными средствами скила, без ручных обходов**.

---

## 1. Контекст для агента без контекста

### Что за скил
`skills/docx` — набор детерминированных CLI-утилит вокруг OOXML:
- `scripts/md2docx.js` — Markdown → `.docx` (заголовки, списки, таблицы, картинки, **диаграммы Mermaid**). Node.js, зависимости в `scripts/node_modules`.
- `scripts/docx2md.js` — `.docx` → Markdown.
- `scripts/office/unpack.py` / `pack.py` / `validate.py` — распаковка/запаковка/валидация OOXML. Python, зависимости в `scripts/.venv`.
- `scripts/preview.py` — рендер `.docx`/`.pdf` в PNG-сетку (LibreOffice + Poppler + Pillow).
- прочее (`docx_replace.py`, `docx_add_comment.py`, `docx_merge.py`, `docx_fill_template.py`, `office_passwd.py`) — в этой задаче не использовались.

Точка входа в установку: `scripts/install.sh` создаёт `scripts/.venv` и `scripts/node_modules` (ничего глобально).

### Окружение, где воспроизвелось
- macOS, Darwin 25.5.0.
- **Системный `python3` = `~/.pyenv/versions/3.14.4/bin/python3`** — в нём **нет** `PIL`, `defusedxml`, `lxml`.
- **`scripts/.venv/bin/python`** — в нём **всё есть**: `Pillow 12.2.0`, `defusedxml 0.7.1`, `lxml 6.1.1`, `python-docx 1.2.0`, `msoffcrypto-tool`.
- Node-утилиты (`md2docx.js`, `docx2md.js`) работали без нареканий — у них зависимости лежат локально в `scripts/node_modules`, поэтому от выбора интерпретатора не зависят.

> Ключевой вывод: **зависимости установлены правильно (`install.sh` отрабатывает), ломается выбор интерпретатора.** На машинах, где `python3` ≠ `.venv` (pyenv, conda, system python без зависимостей), все python-скрипты скила падают, если звать их так, как написано в `SKILL.md`.

---

## 2. Проблема A (P0, bug): python-скрипты не используют свой `.venv`

### Симптом
```
$ python3 scripts/preview.py file.docx out.jpg
ModuleNotFoundError: No module named 'PIL'

$ python3 scripts/office/unpack.py file.docx unpacked/
Traceback (most recent call last):
  File ".../scripts/office/unpack.py", line 29, in <module>
    from defusedxml import minidom  # type: ignore
ModuleNotFoundError: No module named 'defusedxml'
```

### Как воспроизвести
На любой машине, где `python3` указывает на интерпретатор без зависимостей скила (pyenv/conda/чистый system python):
```bash
cd skills/docx
bash scripts/install.sh                      # создаёт scripts/.venv со всеми зависимостями
node scripts/md2docx.js examples/fixture-simple.md /tmp/x.docx   # OK (node)
python3 scripts/preview.py /tmp/x.docx /tmp/x.jpg                # FAIL: No module named 'PIL'
python3 scripts/office/unpack.py /tmp/x.docx /tmp/unpacked/      # FAIL: No module named 'defusedxml'
./.venv/bin/python scripts/preview.py /tmp/x.docx /tmp/x.jpg     # OK (правильный интерпретатор)
```

### Корень проблемы (рассогласование контракта)
- `scripts/install.sh:134-143` — создаёт `.venv` и ставит `requirements.txt` **в него**; в финальной подсказке (`install.sh:162-163`) пользователю советуют звать скрипты как `./.venv/bin/python scripts/...`.
- **НО** `SKILL.md` (контракт для агента) во всём блоке команд (`SKILL.md:55-66`) и в Quick Reference (§10) велит звать `python3 scripts/...`. Агент следует `SKILL.md`, берёт системный `python3`, и падает.
- Скрипты импортят зависимости на верхнем уровне модуля и **не делают re-exec в свой venv**:
  - `scripts/preview.py:38` → `from PIL import Image, ImageDraw, ImageFont`
  - `scripts/office/unpack.py:29-30` → `from defusedxml import minidom` / `from lxml import etree`

### Что сделать (рекомендуемый фикс — defense-in-depth)
Сделать оба пункта; #1 — основной (работает независимо от того, как вызвали), #2 — дешёвый и убирает первопричину.

**1. Self-bootstrap в venv (основное).** В начало каждого python-entrypoint (`preview.py`, `office/unpack.py`, `office/pack.py`, `office/validate.py`, `docx_*.py`, `office_passwd.py`) добавить re-exec в `.venv`, если текущий интерпретатор — не он и venv существует. Вынести в общий хелпер, например `scripts/_venv_bootstrap.py`, и импортировать первой строкой. Псевдокод:
```python
import os, sys
def reexec_into_venv():
    here = os.path.dirname(os.path.abspath(__file__))
    # подняться к scripts/ (для office/*.py — на уровень выше)
    for root in (here, os.path.dirname(here)):
        venv_py = os.path.join(root, ".venv", "bin", "python")
        if os.path.exists(venv_py) and os.path.realpath(sys.executable) != os.path.realpath(venv_py):
            os.execv(venv_py, [venv_py, *sys.argv])
```
Важно: корректно вычислить путь к `.venv` для скриптов в `scripts/office/` (venv на уровень выше). Re-exec через `os.execv` не плодит процессы и сохраняет argv/exit code.

**2. Привести `SKILL.md` к `install.sh`.** Заменить в блоке команд (`SKILL.md:55-66`) и в Quick Reference (§10, §7.2) `python3 scripts/...` на `./.venv/bin/python scripts/...` (либо явно описать, что вызывать надо интерпретатором из venv). Это убирает рассинхрон даже без правки кода.

### Критерии приёмки (Проблема A)
- `python3 scripts/preview.py ...`, `python3 scripts/office/unpack.py ...` и остальные python-CLI **отрабатывают без `ModuleNotFoundError`** на машине, где системный `python3` не содержит зависимостей, **при условии что `install.sh` отработал** (т.е. `.venv` существует).
- Если `.venv` отсутствует — скрипт падает с **понятным сообщением** («run `bash scripts/install.sh` first»), а не с голым `ModuleNotFoundError`/traceback.
- `SKILL.md` и `install.sh` дают **одинаковый** способ запуска.

---

## 3. Проблема B (P1, feature): нет A4 / landscape / полей в `md2docx.js`

### Симптом / чего не хватило
`md2docx.js` всегда генерит US Letter. Флага размера страницы нет. Чтобы получить A4 (типовое требование для RU/ГОСТ/EU-документов), пришлось после генерации **вручную** распаковывать zip и менять `<w:pgSz>` своим python-скриптом (`12240×15840` → `11906×16838`). Штатного fallback не было, т.к. `office/unpack.py` падал (Проблема A).

### Корень (где прибито)
В `scripts/md2docx.js`:
- `md2docx.js:345-346` — геометрия секции жёстко задана:
  ```js
  size:   { width: 12240, height: 15840 },              // US Letter
  margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
  ```
- `md2docx.js:40` — `const contentWidthDxa = 9360;` — **производное от Letter** (12240 − 2×1440). Используется для ширины таблиц (`md2docx.js:233,261`).
- `md2docx.js:82-85` и `278-281` — лимиты ширины/высоты картинок и Mermaid (`maxWidth=620`, `maxHeight=800`) — тоже исходят из геометрии Letter (комментарий `md2docx.js:83`).

> ⚠️ **Критично:** недостаточно поменять только `pgSz`. На A4 пригодная ширина = 11906 − 2×1440 = **9026 dxa**, что **меньше** текущего `contentWidthDxa = 9360`. Если оставить 9360, таблицы и картинки **вылезут за поля A4**. Все производные (`contentWidthDxa`, `maxWidth`, `maxHeight`) обязаны вычисляться из фактической геометрии страницы, а не из констант Letter.

### Что сделать
Добавить в `md2docx.js` CLI-флаги (парсер аргументов — `md2docx.js:9-20`):
- `--page-size A4|Letter` (по умолчанию **Letter** — обратная совместимость).
- `--landscape` (своп width/height).
- `--margins T,R,B,L` (в dxa; опционально с суффиксом `mm`).

Справочные значения (portrait, twips/dxa; 1 mm ≈ 56.7 dxa):
| Формат | width | height |
|---|---|---|
| US Letter | 12240 | 15840 |
| **A4** | **11906** | **16838** |

Реализация:
1. Вычислять `pageW`, `pageH`, `margins` из флагов.
2. **`contentWidthDxa = pageW − marginLeft − marginRight`** (убрать хардкод `9360`).
3. `maxWidth`(px) для картинок/Mermaid выводить из `contentWidthDxa` (≈ `contentWidthDxa / 15` px при 96 dpi), `maxHeight` — из `pageH − marginTop − marginBottom`.
4. Прокинуть размеры/поля в `size`/`margin` секции (`md2docx.js:343-346`).

### Опционально (по желанию реализатора)
Если правка `md2docx.js` нежелательна — добавить отдельный хелпер `scripts/office/set_page.py IN.docx OUT.docx --page-size A4 [--landscape] [--margins ...]`, который патчит `pgSz`/`pgMar` через `office/unpack.py`+`pack.py`. Но это **не решает** проблему переполнения таблиц (ширина уже зафиксирована в `md2docx.js` при генерации), поэтому предпочтителен флаг в `md2docx.js`.

### Критерии приёмки (Проблема B)
- `node scripts/md2docx.js in.md out.docx --page-size A4` даёт документ с `<w:pgSz w:w="11906" w:h="16838"/>`.
- Таблицы и картинки/диаграммы **не выходят за поля** A4 (проверить визуально через `preview.py`).
- Без флагов поведение **байт-в-байт прежнее** (Letter, `contentWidthDxa=9360`) — регрессии существующих вызовов нет.
- `--landscape` и `--margins` работают и отражаются в `pgSz`/`pgMar`.
- Документ проходит `office/validate.py` (`OK`).

---

## 4. Проблема C (P2, hardening): надёжность установки и fallback-пути

### Симптом
- Документированный в `SKILL.md` (§7.7) обходной путь A4 «unpack → edit `word/document.xml` → pack» сам не работал из-за Проблемы A.
- `install.sh` отрабатывает «успешно», но оставляет окружение, где `SKILL.md`-команды (`python3 ...`) нерабочие. Нет verify-шага «запустить preview/unpack штатной командой и убедиться, что импорт проходит».

### Что сделать
- В конце `install.sh` добавить **smoke-test тем же способом, что рекомендует `SKILL.md`**: сгенерировать тестовый docx и прогнать `preview.py` + `office/validate.py`; при `ModuleNotFoundError` — упасть с явной диагностикой.
- (Связано с фиксом A) после self-bootstrap smoke-test начнёт проходить и через голый `python3`.
- Проверить, что `install.sh` ставит **весь** `requirements.txt` в venv и падает, если какое-то колесо (`Pillow`/`lxml`) не собралось, а не продолжает молча. (Эмпирически на этой машине `Pillow` в venv первоначально отсутствовал и доустанавливался вручную — стоит убедиться, что `install.sh:143` реально доводит установку до конца на Python 3.14 / свежих интерпретаторах, где могут отсутствовать prebuilt wheels.)

### Критерии приёмки (Проблема C)
- `bash scripts/install.sh` завершается **только** если штатная команда из `SKILL.md` (`preview.py` на тестовом файле) реально работает.
- Любая нехватка зависимости видна на этапе install, а не при первом вызове утилиты агентом.

---

## 5. Definition of Done (общее)

1. Сценарий «md (с Mermaid) → docx → A4» проходит **одной командой `md2docx.js --page-size A4`**, без ручного патчинга zip.
2. `python3 scripts/<любой>.py` и `./.venv/bin/python scripts/<любой>.py` дают одинаковый результат (нет `ModuleNotFoundError`) на машине, где `python3` ≠ venv.
3. `SKILL.md` и `install.sh` согласованы по способу запуска.
4. Обратная совместимость: вызовы без новых флагов не меняют вывод.
5. Обновлены: `SKILL.md` (раздел про page-size в §7.3 «Creating .docx from Markdown» и Quick Reference §10), при необходимости `references/docx-js-gotchas.md` (там сейчас зафиксировано «A4 default» для docx-js — выверить).
6. Тесты под `scripts/tests/` покрывают: `--page-size A4` (pgSz + отсутствие переполнения таблиц), self-bootstrap (вызов из интерпретатора без зависимостей).

---

## 6. Out of scope / чего НЕ ломать

- **Дефолт остаётся US Letter** — менять формат по умолчанию нельзя (сломает существующих потребителей и `docx_replace.py --insert-after`, который зовёт `md2docx.js`).
- Не трогать логику рендеринга Mermaid и таблиц по сути — только сделать их размеры производными от геометрии страницы.
- Не выносить зависимости из `.venv` в глобал; не менять структуру установки.
- `office/` реплицируется в `xlsx`/`pptx` (master — `docx`) — правки `office/*.py` (self-bootstrap) синхронизировать по протоколу из `scripts/.AGENTS.md` / `CLAUDE.md §2`.

---

## 7. Команды для проверки (verification)

```bash
cd skills/docx
bash scripts/install.sh

# A: интерпретатор
node scripts/md2docx.js examples/fixture-simple.md /tmp/x.docx
python3 scripts/preview.py /tmp/x.docx /tmp/x.jpg                 # должно работать после фикса A
python3 scripts/office/unpack.py /tmp/x.docx /tmp/unpacked/       # должно работать после фикса A

# B: A4
node scripts/md2docx.js examples/fixture-simple.md /tmp/a4.docx --page-size A4
python3 -c "import zipfile,re; xml=zipfile.ZipFile('/tmp/a4.docx').read('word/document.xml').decode(); print(re.findall(r'<w:pgSz[^>]*>',xml))"
# ожидаем: <w:pgSz w:w="11906" w:h="16838" .../>
python3 scripts/office/validate.py /tmp/a4.docx                   # OK
python3 scripts/preview.py /tmp/a4.docx /tmp/a4.jpg --cols 2      # визуально: таблицы в полях

# регрессия Letter
node scripts/md2docx.js examples/fixture-simple.md /tmp/letter.docx
python3 -c "import zipfile,re; xml=zipfile.ZipFile('/tmp/letter.docx').read('word/document.xml').decode(); print(re.findall(r'<w:pgSz[^>]*>',xml))"
# ожидаем неизменное: <w:pgSz w:w="12240" w:h="15840" .../>
```

---

## 8. Dogfooding (проверка фикса на реальном документе)

Чтобы убедиться, что доработка решает **исходную боль**, а не только синтетический `examples/fixture-simple.md`, прогоните фикс на реальном документе, который и породил эту постановку.

### Фикстура
В `tmp7/` лежат два файла (реальный кейс «Интеграционная архитектура», 3 диаграммы Mermaid: 2 flowchart + 1 sequence, несколько широких таблиц):

| Файл | Роль |
|---|---|
| `tmp7/dogfood-integration-arch.md` | **вход** — Markdown-исходник (с Mermaid и таблицами) |
| `tmp7/dogfood-integration-arch-A4.golden.docx` | **golden** — целевой результат A4, полученный ручным обходом (zip-патч `pgSz`). После фикса штатная команда должна давать эквивалент. |

> Рекомендация: при мёрдже зафиксировать `dogfood-integration-arch.md` как постоянную фикстуру в `skills/docx/examples/` (напр. `examples/fixture-mermaid-a4.md`), а golden — как reference в `scripts/tests/`.

### Сценарий dogfooding (ровно то, что раньше требовало ручного обхода)
```bash
cd skills/docx
bash scripts/install.sh

# 1. Сгенерировать A4 ОДНОЙ командой — без ручного патча zip (это и есть цель фикса B)
node scripts/md2docx.js \
  ../../tmp7/dogfood-integration-arch.md \
  /tmp/dogfood-A4.docx --page-size A4

# 2. Подтвердить геометрию A4
python3 -c "import zipfile,re; xml=zipfile.ZipFile('/tmp/dogfood-A4.docx').read('word/document.xml').decode(); print(re.findall(r'<w:pgSz[^>]*>',xml))"
# ожидаем: <w:pgSz w:w=\"11906\" w:h=\"16838\" .../>

# 3. Структурная валидация — штатной командой из SKILL.md (это и есть цель фикса A: без ModuleNotFoundError)
python3 scripts/office/validate.py /tmp/dogfood-A4.docx          # OK

# 4. Визуальная проверка — диаграммы отрендерены, таблицы НЕ вылезают за поля A4
python3 scripts/preview.py /tmp/dogfood-A4.docx /tmp/dogfood-A4.jpg --cols 2
```

### Что считается успехом (dogfooding acceptance)
1. **Шаги 1, 3, 4 не требуют ни одного ручного обхода** (нет ручного `zipfile`-патча `pgSz`, нет ручной доустановки `Pillow`/`defusedxml`, нет `source .venv/bin/activate`).
2. Все 3 диаграммы Mermaid присутствуют в выводе и читаемы.
3. Широкие таблицы (порты, расчёт доступности, матрица соответствия) **умещаются в поля A4** — визуально по `preview.py`; ширина контента выведена из A4 (9026 dxa), а не из Letter (9360).
4. `validate.py` → `OK`.
5. Сравнение с golden: `pgSz` совпадает (`11906×16838`); число и порядок диаграмм/таблиц совпадают (побайтовое равенство не требуется — у Mermaid-PNG возможен недетерминизм рендера).
6. Регрессия: тот же `.md` без `--page-size` даёт Letter (`12240×15840`), как и golden-предшественник до перевёрстки.

### Зачем именно этот документ
Он одновременно нагружает **оба** фикса: широкие таблицы вскрывают проблему `contentWidthDxa` при смене формата (B), а `preview.py`/`validate.py`/`unpack.py` в проверке — проблему интерпретатора (A). Синтетический fixture этого не покрывает.

---

## 9. Приложение: карта правок по файлам

| Файл | Строки | Что там сейчас | Действие |
|---|---|---|---|
| `scripts/md2docx.js` | 9-20 | парсер CLI-аргументов | добавить `--page-size`/`--landscape`/`--margins` |
| `scripts/md2docx.js` | 40 | `contentWidthDxa = 9360` (хардкод Letter) | вычислять из `pageW − margins` |
| `scripts/md2docx.js` | 82-85, 278-281 | `maxWidth=620`, `maxHeight=800` для img/Mermaid | выводить из геометрии страницы |
| `scripts/md2docx.js` | 343-346 | `size`/`margin` секции (Letter) | брать из флагов |
| `scripts/preview.py` | 38 | `from PIL import ...` (top-level) | + self-bootstrap в venv |
| `scripts/office/unpack.py` | 29-30 | `from defusedxml ...` / `from lxml ...` | + self-bootstrap в venv |
| `scripts/office/{pack,validate}.py`, `scripts/docx_*.py`, `scripts/office_passwd.py` | top | top-level импорты зависимостей | + self-bootstrap (общий `_venv_bootstrap.py`) |
| `scripts/install.sh` | 134-143, 162-163 | venv + pip + подсказка `.venv/bin/python` | + финальный smoke-test |
| `SKILL.md` | 55-66, §7.2/§7.3/§10 | контракт команд `python3 scripts/...` | согласовать с venv; описать `--page-size` |

---

## 10. Приложение: исходная обратная связь (первоисточник постановки)

Сценарий, в котором всё всплыло: генерация документа «Интеграционная архитектура» — Markdown с 3 диаграммами Mermaid (flowchart + sequence) → `.docx`, затем перевёрстка под **A4** портретную с равными по ширине логическими блоками.

- `md2docx.js` с Mermaid отработал отлично (3 диаграммы с первого раза) — основной кейс скила закрыт.
- A4 пришлось делать **ручным zip-патчем `pgSz`**, т.к. флага нет, а штатный fallback (`office/unpack.py`) падал на `defusedxml`.
- `preview.py` падал на `PIL`, пока вручную не доставил `Pillow` в venv.
- Первопричина обоих падений — запуск под системным `python3` (pyenv 3.14.4) вместо `scripts/.venv`.

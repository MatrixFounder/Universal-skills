---
id: SUBPROCESS-TEXT-DECODE-LOCALE-CLASS
type: known-issue
status: open
opened_at: 2026-09-02
category: robustness
severity: SEV-3
component: repo
slug: subprocess-text-decode-locale-class
---

# SUBPROCESS-TEXT-DECODE-LOCALE-CLASS — `subprocess.run(..., text=True)` декодирует ребёнка кодеком локали

**Status:** OPEN — закрыт только в `design-md` (2 сайта), где и был найден.
**~23 продакшн-сайта в 10 скиллах не измерены.**

**Related:**
[HUMAN-CLI-OUTPUT-LOCALE-CLASS](human-cli-output-locale-class.md) и
[PDF-CLI-STDOUT-JSON-LOCALE-CLASS](pdf-cli-stdout-json-locale-class.md) — тот
же корень (кодек берётся из локали, а не из контракта), но обе те записи про
**выход** процесса. Эта — про **вход**: то, что процесс читает у своих детей.

## Корень

`subprocess.run(cmd, text=True)` (равно `universal_newlines=True`) не задаёт
кодек. CPython берёт его из `locale.getencoding()`, поэтому под `LC_ALL=C` с
отключённым PEP 540 дочерний вывод декодируется как **ascii** — со
`strict`-обработчиком, потому что у декодирующей стороны никакого
`backslashreplace` по умолчанию нет.

Дочерний процесс при этом никакой локали не спрашивал: Node-CLI, `pdftoppm`,
`soffice`, `git` отдают UTF-8 (или свой фиксированный кодек) независимо от
того, что объявил родитель. То есть кодек берётся **не у той стороны**.

Итог — `UnicodeDecodeError` внутри `subprocess.communicate`, то есть падение
не в месте печати, а посреди чтения, с трейсбеком из stdlib.

## Замер (что найдено и как)

Найдено при починке `design-md` в рамках человеческого класса. `lint` под
`PYTHONIOENCODING=ascii PYTHONUTF8=0 LC_ALL=C`:

```
File ".../subprocess.py", line 1099, in _translate_newlines
    data = data.decode(encoding, errors)
UnicodeDecodeError: 'ascii' codec can't decode byte 0xe2 in position 308
```

Позиция 308 — длинное тире в JSON-отчёте `@google/design.md`. Под UTF-8 та же
команда отрабатывает.

**Эта находка объясняет одну строку в предыдущей записи.** В
[HUMAN-CLI-OUTPUT-LOCALE-CLASS](human-cli-output-locale-class.md)
`design-md/scripts/lint` — единственная из 91 находок, которую верификатор не
подтвердил: он сообщил, что «под UTF-8 команда падает тоже», и её вынесли за
скобки по правилу отбора. Верификатор ошибся, но и правило отбора не помогло
бы: находки засчитывались по `UnicodeEncodeError` в stderr, а здесь
`UnicodeDecodeError`. **Грепом по имени исключения этот класс не находится.**

## Починено

`skills/design-md/scripts/lint` и `skills/design-md/scripts/check-contrast` —
обоим вызовам `subprocess.run` явно задан `encoding="utf-8",
errors="replace"`. Ребёнок (`npx @google/design.md`) — Node-CLI и всегда
пишет UTF-8; `replace` не даёт кривому байту превратить отчёт линтера в
трейсбек.

Мутация «снять `encoding=`» убивается тестом
`skills/design-md/scripts/tests/test_human_channel.py`.

## Не измерено

`text=True` без `encoding=` в продакшн-коде (тесты исключены) — **25 файлов**:

| скилл | файлы |
|---|---|
| docx | `_actions.py`, `_soffice.py`, `docx_replace.py`, `office/pack.py`, `preview.py` |
| xlsx | `_soffice.py`, `office/pack.py`, `preview.py`, `md_tables2xlsx/cli_helpers.py`, `xlsx_comment/cli_helpers.py` |
| pptx | `_soffice.py`, `office/pack.py`, `preview.py`, `pptx2md/ocr.py` |
| pdf | `md2pdf.py`, `pdf_ocr.py`, `preview.py` |
| html | `html2md/core_bridge.py` |
| marp-slide | `render.py` |
| transcript-fetcher | `_procgroup.py`, `sources/_ytdlp_media.py` |
| skill-validator | `full_audit.py` |
| skill-auto-improve | `snapshot.py`, `backends/claude.py` |
| skill-creator | `eval-viewer/generate_review.py` |

Список получен грепом, а **не** прогоном: сколько из них реально падает,
зависит от того, бывает ли не-ASCII в выводе конкретного ребёнка. У
`_soffice.py`, `office/pack.py` и `preview.py` цена ошибки выше прочих — это
единицы репликации, то есть одна правка закрывает четыре скилла, и одна
пропущенная оставляет четыре.

Ни один из них здесь **не** объявляется дефектным. Это список кандидатов на
замер, а не находки.

## Путь починки

Задать кодек явно у той стороны, которая его знает — у ребёнка:
`subprocess.run(..., text=True, encoding="utf-8", errors="replace")`.

Контракт тот же, что у машинного канала на выходе: **байты дочернего процесса
не зависят от локали родителя, значит и декодировать их локалью нельзя.**

## Do-not

- **Не** чинить это `sys.stdout.reconfigure(...)`: это выходная сторона, здесь
  она ни при чём.
- **Не** искать этот класс грепом по `UnicodeEncodeError` — исключение
  противоположное (`UnicodeDecodeError`), и в предыдущем замере класс
  из-за этого списали как «другой дефект».
- **Не** ставить `errors="strict"` по умолчанию: у CLI-обёртки задача —
  доложить результат, а не умереть на одном кривом байте в чужом выводе.

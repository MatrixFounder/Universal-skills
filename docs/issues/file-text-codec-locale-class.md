---
id: FILE-TEXT-CODEC-LOCALE-CLASS
type: known-issue
status: fixed
opened_at: 2026-09-02
resolved_at: 2026-09-02
resolved_by: "37 сайтов в 12 файлах + tests/test_file_codec.py + шаг file-codec guard в CI-задании harness"
category: robustness
severity: SEV-2
component: repo
slug: file-text-codec-locale-class
---

# FILE-TEXT-CODEC-LOCALE-CLASS — `Path.read_text()` / `open(path, "w")` берут кодек из локали

> **Закрыт 2026-09-02.** Все **37 продакшн-сайтов в 12 файлах** задают
> `encoding="utf-8"`. Регресс закрыт
> [`tests/test_file_codec.py`](../../tests/test_file_codec.py): обход AST по
> всему репозиторию, шаг `file-codec guard` в задании `harness` CI.
> 5 негативных контролей из 5 ловятся, 8 позитивных проходят.

**Related:** четвёртый член одной семьи, третий гейт.

| Запись | Канал |
|---|---|
| [HUMAN-CLI-OUTPUT-LOCALE-CLASS](human-cli-output-locale-class.md) | что процесс пишет в **свой stdout** |
| [PDF-CLI-STDOUT-JSON-LOCALE-CLASS](pdf-cli-stdout-json-locale-class.md) | машинный канал того же stdout |
| [SUBPROCESS-TEXT-DECODE-LOCALE-CLASS](subprocess-text-decode-locale-class.md) | что процесс читает **у своих детей** |
| **эта** | что процесс читает из **файлов** и пишет в них |

## Корень

`Path.read_text()`, `Path.write_text()` и `open(path, "r"/"w")` не задают кодек.
CPython берёт его из локали. Все файлы этого репозитория — UTF-8 (`SKILL.md`,
eval-JSON, генерируемые HTML-отчёты), но под `LC_ALL=C` кодеком становится ASCII,
и первое же тире поднимает `UnicodeDecodeError` **изнутри** `read_text` — падение
не в месте печати, а посреди чтения, с трейсбеком из stdlib.

Кодек берётся **не у той стороны**: у вызывающей среды, а не у файла.

## Замер 2026-09-02

Найдено обходом AST: **39 сайтов**, из них **37 продакшн** в 12 файлах
(2 оказались вызовами проектного хелпера — см. «Границы»), и **169 в тестах**
(вынесены за скобки по прецеденту `test_subprocess_decode.py`).

| Файл | Сайтов |
|---|---|
| `skills/skill-creator/eval-viewer/generate_review.py` | 10 |
| `skills/docx/evals/grade.py` | 9 |
| `skills/skill-creator/scripts/run_loop.py` | 4 |
| `skills/skill-creator/scripts/generate_report.py` | 2 |
| `skills/skill-validator/scripts/full_audit.py` | 2 |
| `skills/{docx,xlsx,pptx}/scripts/_soffice.py` | 3 (1 × 3 копии) |
| `skills/skill-creator/scripts/{package_skill,run_eval,verify_pin}.py` | 3 |
| `skills/skill-auto-improve/scripts/auto_improve.py` | 1 |
| `skills/mcp-builder/scripts/evaluation.py` | 1 |

## Репро

Дефект **латентный**: он ждёт первого не-ASCII байта в читаемом файле.
Проявился так — `skills/text-humanizer/SKILL.md` получил секцию Red Flags с
обычным тире, и `package_skill.py:35` (`skill_md.read_text()`) перестал читать
его под ASCII-локалью:

```
PYTHONIOENCODING=ascii PYTHONUTF8=0 LC_ALL=C \
  python3 skills/skill-creator/scripts/package_skill.py skills/text-humanizer /tmp/out
...
  File ".../package_skill.py", line 35, in _quick_validate
    content = skill_md.read_text()
UnicodeDecodeError: 'ascii' codec can't decode byte 0xe2 in position 852
```

Файл не менял кодировку — он просто перестал быть **случайно** ASCII. Вместе с
командой упали два собственных теста `skill-creator`
(`tests/test_human_channel.py::TestTheRealCommands`), которые сравнивают прогон
под UTF-8 с прогоном под ASCII: до правки прозы они проходили, потому что
`text-humanizer/SKILL.md` целиком укладывался в ASCII.

## Как починено

Одно ключевое слово на сайт — назвать кодек, которым файл и является:

```python
path.read_text(encoding="utf-8")
path.write_text(text, encoding="utf-8")
open(path, "w", encoding="utf-8")
```

`errors=` намеренно **не** добавлялся: репозиторий пишет эти файлы сам, и
подмена битого байта здесь скрыла бы порчу вместо того, чтобы её показать.
Единственное исключение — уже существовавший `read_text(errors="replace")` в
`generate_review.py`, читающий чужой транскрипт.

## Границы (что гейт намеренно НЕ покрывает)

- **Тесты вынесены** (`tests/`, `test_*.py`) — по прецеденту
  `test_subprocess_decode.py`: там ошибка декодирования и есть сигнал, её
  читает человек. `count_exempt_test_sites()` печатает размер этой поблажки
  (169), чтобы она не читалась как полное покрытие.
- **Бинарные режимы вне области.** У `open(p, "rb")` нет кодека, который можно
  назвать.
- **Совпадение по имени метода — не сайт.** `wiki-ingest` имеет собственный
  `_safety.read_text(path)` / `_safety.write_text(path, text, dry_run)` —
  читатель с отказом идти по симлинку и лимитом размера. У него **нет**
  параметра `encoding`, и добавление его туда даёт `TypeError`. Первый прогон
  правки это и сделал; ошибка поймана на ревью диффа. Гейт пропускает вызовы,
  у которых получатель — модуль из `HELPER_MODULES`, и отдельный тест
  утверждает, что в сигнатуре `_safety` параметра `encoding` действительно нет —
  если он там появится, поблажку обязаны снять.

## Do-not

- **Не «чинить» тире.** Дефект в читателе, а не в прозе. Скилл вправе
  содержать любой UTF-8.
- **Не добавлять `encoding=` к `_safety.read_text` / `_safety.write_text`** —
  см. «Границы».
- **Не править копии `_soffice.py` в xlsx/pptx напрямую** — мастер `docx`,
  дальше репликация по протоколу `CLAUDE.md` §2 с гейтом `diff -q`.

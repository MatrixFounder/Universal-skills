---
id: PDF-CLI-STDOUT-JSON-LOCALE-CLASS
type: known-issue
status: open
opened_at: 2026-08-31
category: robustness
severity: SEV-3
component: repo
slug: pdf-cli-stdout-json-locale-class
---

# PDF-CLI-STDOUT-JSON-LOCALE-CLASS — тот же локале-зависимый JSON на stdout остаётся в 16 других файлах репозитория

**Status:** OPEN — исправлен **только** `pdf_extract.py`
([PDF-EXTRACT-STDOUT-LOCALE-ENCODING](pdf-extract-stdout-locale-encoding.md),
[PDF-EXTRACT-BROKEN-PIPE-EXIT-120](pdf-extract-broken-pipe-exit-120.md)). Остальные
носители дефекта не тронуты — запись заведена, чтобы это не читалось как «класс закрыт».
**Location:** 22 места записи JSON в stdout в 16 файлах восьми скиллов (замер `grep -rn 'json.dump(.*sys.stdout|print(json.dumps' skills/*/scripts/*.py` после фикса `pdf_extract.py`; счёт по `.claude/skills/` не берётся — там симлинки в этот же `skills/` и в приватный `.agentic-development`), среди них
[`skills/pdf/scripts/pdf_fill_form.py`](../../skills/pdf/scripts/pdf_fill_form.py)
(`json.dump(info, sys.stdout, …)` — конструкция байт-в-байт та, что чинилась в
`pdf_extract.py`), `skills/pptx/scripts/pptx_clean.py`, `skills/xlsx/scripts/xlsx_*.py`,
плюс скиллы-инструменты (`skill-creator`, `skill-validator`, `skill-enhancer`,
`transcript-fetcher`, `skill-auto-improve`).
**Related:** оба фикса выше; протокол репликации —
[`CLAUDE.md` §2](../../CLAUDE.md) (`_errors.py` байт-идентичен в docx/xlsx/pptx/pdf/html,
мастер — docx).

## Симптом (ожидаемый, по идентичности конструкции)

Под `PYTHONIOENCODING=ascii` / `LC_ALL=C` любой из этих скриптов оборвёт JSON на
полуслове с traceback'ом вместо envelope'а; под `cp1252` молча выдаст не-UTF-8 байты при
коде 0; `… | head` даст код 120 и лишнюю не-JSON строку на stderr. **Замерено только для
`pdf_extract.py`** — остальные не запускались, вывод основан на идентичности кода, и это
именно вывод, а не измерение.

## Фикс path

DRY-дом для помощника — `_errors.py`, который уже байт-идентично реплицируется в пять
скиллов: добавить туда `write_json_stdout(payload)` (UTF-8-байты + суррогатный escape +
текстовый fallback) и `abandon_stdout()`, перевести на них все места записи, после чего
`pdf_extract.py` теряет свои локальные копии. Это change set по протоколу §2: правка в
docx-мастере → репликация в xlsx/pptx/pdf/html → `diff -q` → прогон всех E2E + валидаторов.
Отдельная задача — не хвост pdf-13.

## Do-not

- **Не** копировать `_utf8_chunk` / `_abandon_stdout` из `pdf_extract.py` в соседние
  скрипты вручную: пять расходящихся копий одного помощника — ровно то, ради чего в
  репозитории существует `_errors.py`.
- **Не** закрывать эту запись, пока не измерены (а не выведены по аналогии) хотя бы
  `pdf_fill_form.py --info` и один xlsx-скрипт.

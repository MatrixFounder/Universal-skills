---
id: TF-HUMAN-REPORT-LOCALE-CRASH
type: known-issue
status: open
opened_at: 2026-08-31
category: robustness
severity: SEV-3
component: transcript-fetcher
slug: tf-human-report-locale-crash
---

# TF-HUMAN-REPORT-LOCALE-CRASH — человекочитаемые отчёты transcript-fetcher падают под не-UTF-8 локалью ещё до первой строки вывода

**Status:** OPEN — **не** чинилось. Найдено попутно, пока закрывался
[PDF-CLI-STDOUT-JSON-LOCALE-CLASS](pdf-cli-stdout-json-locale-class.md): тот класс
покрывает **машиночитаемые JSON-каналы**, а это — обычный `print()` человеку.
**Location:**
[`skills/transcript-fetcher/scripts/install_components.py`](../../skills/transcript-fetcher/scripts/install_components.py)
(запуск без флагов) и
[`skills/transcript-fetcher/scripts/fetch.py`](../../skills/transcript-fetcher/scripts/fetch.py)
— `doctor` без `--json`, `_print_doctor_report`.
**Related:** [PDF-CLI-STDOUT-JSON-LOCALE-CLASS](pdf-cli-stdout-json-locale-class.md)
(та же причина — кодек берётся из локали, — но другой канал и другой потребитель).

## Симптом (замерено)

```bash
PYTHONIOENCODING=ascii PYTHONUTF8=0 LC_ALL=C python3 install_components.py
# rc=1, 0 байт на stdout, UnicodeEncodeError на
#   print("transcript-fetcher — component status\n")
PYTHONIOENCODING=ascii PYTHONUTF8=0 LC_ALL=C python3 fetch.py doctor
# rc=1, 0 байт, тот же отказ на "transcript-fetcher — doctor\n"
```

Падение происходит **на первой же строке**, то есть команда, единственная задача
которой — рассказать, что в системе не так, под нестандартной локалью не
рассказывает вообще ничего. Причина — длинное тире (U+2014) в литералах
заголовков, а не пользовательские данные: воспроизводится на чистой установке.

## Почему не закрыто вместе с JSON-каналом

Разные контракты. JSON на stdout — машинный канал, у него есть однозначно
правильный ответ: **UTF-8 всегда** (RFC 8259 §8.1), что и сделано в
`_stdout.py` / `_errors.py`. Человекочитаемый текст, наоборот, обязан
уважать локаль вызывающего: писать UTF-8 в терминал, объявленный как cp1252,
значит выдать мусор. Правильный фикс здесь — другой: либо `errors=` при выводе
(`backslashreplace`, как у stderr по умолчанию), либо ASCII-заголовки, либо
`sys.stdout.reconfigure(errors="backslashreplace")` на старте человеческого
пути. Выбор — отдельное решение, а не хвост того change set'а.

## Масштаб

Тот же паттерн (не-ASCII в литералах человеческого вывода) почти наверняка есть
и в других скиллах — **не измерено**, потому что замерялись только скрипты
transcript-fetcher. Перед закрытием этой записи нужно прогнать под `LC_ALL=C`
человеческие пути хотя бы docx/xlsx/pptx/pdf и wiki-ingest и записать результат
числом, а не предположением.

## Do-not

- **Не** чинить это через `sys.stdout.reconfigure(encoding="utf-8")` на весь
  процесс: этот скилл сознательно шлёт человеку remediation-текст на stderr
  (`fetch.py:123-131`, зафиксировано тестами `tests/test_fetch_cli.py:375-395`),
  и такая правка молча поменяет и тот канал.
- **Не** переводить человеческий вывод на `write_json_stdout` — он гарантирует
  UTF-8 независимо от локали, что для машинного канала правильно, а для
  терминала пользователя — нет.

---
id: PDF-EXTRACT-BROKEN-PIPE-EXIT-120
type: known-issue
status: fixed
opened_at: 2026-08-31
resolved_at: 2026-08-31
resolved_by: manual fix 2026-08-31 (найдено контрактной линзой VDD-adversarial при закрытии pdf-13)
category: robustness
severity: SEV-3
component: pdf
slug: pdf-extract-broken-pipe-exit-120
---

# PDF-EXTRACT-BROKEN-PIPE-EXIT-120 — `… | head` давал код возврата 120 при envelope'е `"code": 1` и лишнюю не-JSON строку на stderr

> **Resolved 2026-08-31.** `BrokenPipeError` ловится отдельной веткой: `_abandon_stdout`
> переводит fd 1 на `/dev/null`, после чего интерпретатору нечего сбрасывать на закрытии,
> и процесс выходит с тем же кодом, который объявил в envelope'е. Заодно исправлено имя
> приёмника в сообщении: было `Could not write output None` / `details.path: "None"` —
> стало `stdout`.

**Status:** FIXED 2026-08-31 (был SEV-3 — сбой был виден, но обёртка получала **два
противоречащих** источника истины об одном отказе).
**Location:** [`skills/pdf/scripts/pdf_extract.py`](../../skills/pdf/scripts/pdf_extract.py)
— `main` (ветка `except BrokenPipeError`), `_abandon_stdout`.
**Related:** [PDF-EXTRACT-STDOUT-LOCALE-ENCODING](pdf-extract-stdout-locale-encoding.md)
(найдено тем же прогоном, тот же канал),
[PDF-CLI-STDOUT-JSON-LOCALE-CLASS](pdf-cli-stdout-json-locale-class.md) (обобщение на весь
репозиторий; класс закрыт 2026-08-31).
**Found:** VDD-adversarial, контрактная линза, 2026-08-31 — `pdf_extract.py … | head -c 20`
на документе, дамп которого больше буфера трубы (64 KiB).

## Симптом

```
$ ./.venv/bin/python pdf_extract.py big.pdf --json-errors | head -c 20
{"v": 1, "error": "Could not write output None: [Errno 32] Broken pipe", "code": 1, ...}
Exception ignored while flushing sys.stdout:
BrokenPipeError: [Errno 32] Broken pipe
$ echo ${PIPESTATUS[0]}
120
```

Три дефекта в одном исходе:

1. **код 120 против `"code": 1`** — `_errors.py` в своём docstring обещает обратное:
   «exit status matches the JSON envelope's `code` field — wrappers don't have to
   reconcile two sources of truth». Здесь они расходятся, и CI, читающий код возврата,
   классифицирует отказ иначе, чем CI, читающий envelope.
2. **вторая строка на stderr, не JSON** — `--json-errors` обещает ровно одну строку;
   обёртка, читающая stderr целиком через `jq`, спотыкается.
3. **`output None`** — приёмником назван литерал `None` (`args.output` при выводе на
   stdout), то есть сообщение не называет то, что сломалось.

Порог воспроизведения — дамп больше буфера трубы: на мелком документе (1.5 КБ) всё
влезает в ядро до закрытия читателем, и дефект не проявляется. Отсюда 300-страничная
сборка в тесте.

## Корень

`BrokenPipeError` — подкласс `OSError`, поэтому он попадал в общую ветку и корректно
превращался в envelope. Но буфер `sys.stdout` оставался непустым: на завершении процесса
CPython пытается сбросить его **ещё раз**, получает тот же EPIPE, печатает
`Exception ignored while flushing sys.stdout` и подменяет код возврата на 120. Ни одна
строка кода в скилле в этот момент уже не выполняется — это shutdown-путь интерпретатора.

## Фикс

Отдельная ветка `except BrokenPipeError` перед общей `except OSError`:
`_abandon_stdout()` открывает `/dev/null` и `os.dup2`-ит его на `sys.stdout.fileno()` —
рекомендованный в документации CPython приём; сброс на закрытии уходит в никуда, код
возврата остаётся тем, что вернул `main()`. Метод best-effort: у stdout без реального fd
(`StringIO` в тестах) перенаправлять нечего, исключение гасится. Общая ветка `OSError`
теперь называет приёмник (`stdout` либо путь `-o`) и в тексте, и в `details.path`.

## Тесты

`TestStdoutChannel.test_a_dead_pipe_exits_with_the_code_the_envelope_declares` (реальный
`Popen` + закрытие читающего конца; проверяет `rc == envelope["code"]`, отсутствие строки
`Exception ignored` и ровно одну строку на stderr) и
`test_a_failing_stdout_is_named_stdout_not_none`.
Мутации: `_abandon_stdout` → `pass` и снятие ветки `BrokenPipeError` — обе убиты.

## Do-not

- **Не** заменять `_abandon_stdout` на `sys.stdout.close()` или `signal.signal(SIGPIPE,
  SIG_DFL)`: первое снова бросит EPIPE, второе убьёт процесс сигналом (код 141) — и
  envelope не будет написан вовсе.
- **Не** ослаблять тест до маленькой фикстуры: дамп обязан превышать буфер трубы, иначе
  тест зелёный и на несломанном, и на сломанном коде.

---
id: PDF-EXTRACT-STDOUT-LOCALE-ENCODING
type: known-issue
status: fixed
opened_at: 2026-08-31
resolved_at: 2026-08-31
resolved_by: manual fix 2026-08-31 (найдено контрактной линзой VDD-adversarial при закрытии pdf-13)
category: correctness
severity: SEV-2
component: pdf
slug: pdf-extract-stdout-locale-encoding
---

# PDF-EXTRACT-STDOUT-LOCALE-ENCODING — дамп на stdout кодировался кодеком локали: под `LC_ALL=C` обрывался на полуслове, под `cp1252` молча переставал быть UTF-8

> **Resolved 2026-08-31.** `_emit` пишет дамп на stdout **байтами** UTF-8
> (`sys.stdout.buffer`), минуя текстовый слой с его локальным кодеком; путь `-o FILE`
> и раньше был локале-независим (`open(..., encoding="utf-8")`) и не тронут.
> Одиночные суррогаты (сломанный `/ToUnicode`, недекодируемые байты имени файла)
> экранируются в `\udXXX` — валидный JSON вместо WTF-8. stdout без `.buffer`
> (`StringIO` в тестах, прокси-объект обёртки) сохраняет текстовый путь.
> Байтовая идентичность вывода проверена на 18 документах (14 фикстур + 4 реальных):
> 0 расхождений с HEAD.

**Status:** FIXED 2026-08-31 (был SEV-2 — не падение, а **молча неверные байты** на
машиночитаемом канале в одном сценарии и обрыв контракта `--json-errors` в другом).
**Location:** [`skills/pdf/scripts/pdf_extract.py`](../../skills/pdf/scripts/pdf_extract.py)
— `_emit`, `_utf8_chunk`.
**Related:** [PDF-CLI-STDOUT-JSON-LOCALE-CLASS](pdf-cli-stdout-json-locale-class.md)
(обобщение: тот же дефект нашёлся ещё в ~60 местах семи скиллов; класс закрыт 2026-08-31),
[PDF-EXTRACT-BROKEN-PIPE-EXIT-120](pdf-extract-broken-pipe-exit-120.md) (найдено тем же
прогоном, соседний канал).
**Found:** VDD-adversarial, контрактная линза, 2026-08-31 — прогон CLI под нестандартными
`PYTHONIOENCODING` / `LC_ALL`, а не чтение кода.

## Симптом

Два разных исхода одного корня — оба на **успешном** пути, оба на `pdf_extract.py INPUT`
без `-o`:

1. **`PYTHONIOENCODING=ascii` (или `LC_ALL=C` на системе без UTF-8-дефолта)** — процесс
   падал посреди сериализации: на stdout уже лежало **1264 байта обрезанного JSON**,
   на stderr — 14-строчный traceback `UnicodeEncodeError: 'ascii' codec can't encode
   character '—'`, код возврата 1. Флаг `--json-errors` при этом обещает ровно одну
   строку JSON на stderr — обёртка получала traceback и не могла ни распарсить ошибку,
   ни доверять stdout.
2. **`PYTHONIOENCODING=cp1252` (типовая Windows-локаль)** — **код 0, тишина**, но длинное
   тире уезжало в вывод одним байтом `0x97`: дамп переставал быть валидным UTF-8, и любой
   строгий читатель (`json.loads` над байтами, `jq`, Node) спотыкался о файл, который
   скилл только что объявил успешным. Замер: 1539 байт вместо 1541.

## Воспроизведение (до фикса)

```bash
cd skills/pdf/scripts
PYTHONIOENCODING=ascii PYTHONUTF8=0 LC_ALL=C \
  ./.venv/bin/python pdf_extract.py tests/fixtures/digital.pdf --json-errors \
  >/tmp/a.out 2>/tmp/a.err
echo $?          # 1
wc -c </tmp/a.out # 1264 — обрезанный JSON
head -1 /tmp/a.err # Traceback (most recent call last):

PYTHONIOENCODING=cp1252 PYTHONUTF8=0 \
  ./.venv/bin/python pdf_extract.py tests/fixtures/digital.pdf >/tmp/c.out
python3 -c "open('/tmp/c.out','rb').read().decode('utf-8')"  # UnicodeDecodeError
```

## Корень

`json.dump(dump, sys.stdout, ensure_ascii=False, indent=2)` пишет **текст** в
`TextIOWrapper`, а тот кодирует кодеком процесса (`PYTHONIOENCODING`, затем локаль).
`ensure_ascii=False` — правильный выбор для содержимого, но он перекладывает
ответственность за кодирование на слой, который её не несёт: у stdout `errors="strict"`
(в отличие от stderr, где дефолт `backslashreplace` — потому envelope на stderr и
выживал), а сериализация потоковая, поэтому падение происходит **после** того, как часть
JSON уже ушла читателю. JSON по определению UTF-8 (RFC 8259 §8.1) — байты
машиночитаемого канала не должны зависеть от локали вызывающего.

## Фикс

`_emit` получает энкодер `json.JSONEncoder(ensure_ascii=False, indent=2)` и льёт чанки в
`sys.stdout.buffer` как UTF-8-байты, предварительно сбросив текстовый слой (иначе два слоя
перемешаются). `_utf8_chunk` — единственное место, где кодирование может не выйти:
одиночный суррогат U+D800-DFFF (сломанный `/ToUnicode` CMap отдаёт `chr()` чего угодно;
POSIX так же декодирует недекодируемые байты имени файла) экранируется в `\udXXX` —
валидный JSON-escape, который парсер возвращает тем же символом. Повторно упасть нечему.

Сознательно **не** сделано: `ensure_ascii=True` как «простое» решение — оно чинит падение,
но меняет каждый байт вывода на всех локалях; тест
`test_the_utf8_bytes_match_the_dump_written_under_a_utf8_locale` существует именно чтобы
такую подмену убить.

## Тесты

`TestStdoutChannel` в
[`tests/test_pdf_extract.py`](../../skills/pdf/scripts/tests/test_pdf_extract.py):
`test_an_ascii_locale_does_not_truncate_the_dump`,
`test_a_legacy_locale_does_not_emit_non_utf8_bytes`,
`test_the_utf8_bytes_match_the_dump_written_under_a_utf8_locale`,
`test_a_lone_surrogate_is_escaped_rather_than_crashing_the_dump`,
`test_a_stdout_without_a_buffer_still_gets_the_dump`.
Мутации: возврат на текстовый слой, подмена на `ensure_ascii=True`, снятие
суррогатного escape — все убиты.

## Do-not

- **Не** возвращать `json.dump(..., sys.stdout, ...)`: под UTF-8-локалью разработчика
  разницы не видно, а дефект воспроизводится только у пользователя.
- **Не** «чинить» это через `sys.stdout.reconfigure(encoding="utf-8")`: это переписывает
  явный выбор вызывающего для **всего** процесса, включая stderr-предупреждения на его
  локали, ради одного канала.
- **Не** трогать текстовую ветку (`buffer is None`): на ней держатся in-process тесты с
  `redirect_stdout(StringIO())` и обёртки с прокси-объектом вместо stdout.

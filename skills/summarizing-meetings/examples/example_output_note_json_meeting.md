<!--
  EXAMPLE OUTPUT: note-JSON for a MEETING (content=transcript, --emit note-json).
  Source: examples/example_input_transcript.md (the Russian Q2 planning meeting).
  Mode: full (meeting → body = the pyramid конспект rendered as prose).
  Fields: neutral `title`/`body` (the universal default of --emit note-json).
  Language: SOURCE LANGUAGE (Russian) — no --translate, so NO translation (R-4).
  Demonstrates: R-1 (note-json shape), R-2 (known_concepts reuse), R-3 (verbatim quotes),
  R-4 (source-language; the neutral `title`/`body` fields hold Russian only because the
  meeting WAS Russian), R-5 (clean entity names).
-->

# Meeting → note-JSON (full mode, Russian, no translation)

## Caller input (the `prepare`-style envelope)

```jsonc
// --emit note-json  --content transcript  --mode full
"known_concepts": [
  { "slug": "proekt-alpha", "name": "Проект Альфа" },
  { "slug": "playwright",   "name": "Playwright" },
  { "slug": "redis",        "name": "Redis" },
  { "slug": "aws",          "name": "AWS" }
]
```

Note how each matching entity below **reuses the existing `name` verbatim** ("Проект Альфа",
"Playwright", "Redis", "AWS") instead of minting a variant like "проект Альфа" or "playwright" — R-2.

## Output (the note-JSON object handed to the import `apply` step)

```json
{
  "title": "Планирование Q2 — приоритеты и ресурсы",
  "title_orig": null,
  "author": null,
  "published": null,
  "tldr": "Команда зафиксировала четыре приоритета Q2 — миграцию API, Redis-кеширование, редизайн дашборда с тёмной темой и автоматизацию QA на Playwright — с владельцами, сроками и бюджетом на согласовании.",
  "summary_bullets": [
    "Миграция API — критичный приоритет Q2: параллелим backend (Сергей) и frontend (Катя), срок 3–4 недели.",
    "Redis-кластер снижает latency с 800ms до 200ms; бюджет ~$500/мес на AWS согласует Алексей до пятницы.",
    "Редизайн дашборда с приоритетом на тёмную тему (68% запрос), срок 5 недель, ведёт Дмитрий.",
    "Автоматизация e2e на Playwright сокращает регрессию с 3 дней до 4 часов; обучение команды за неделю."
  ],
  "body": "Команда определила четыре приоритета на Q2.\n\nМиграция API — приоритет номер один: текущая версия deprecated, поддержка заканчивается в июне, первоначальная оценка 4–6 недель. Решено параллелить работу: Сергей берёт backend, Катя — frontend-адаптацию, что сокращает срок до 3–4 недель. Ольга выделила Игоря в QA на первые две недели, после чего он нужен на проекте Альфа.\n\nПроизводительность и кеширование: при 10 тысячах одновременных пользователей latency составляет 800ms, цель — довести до 200ms. Мария предложила внедрить Redis-кластер из минимум трёх нод; стоимость около 500 долларов в месяц на AWS. Алексей согласует бюджет с финансовым директором до пятницы.\n\nРедизайн дашборда: макеты готовы, навигацию сокращают с 7 до 3 кликов; 68% пользователей в опросе просили тёмную тему, поэтому её приоритезировали. Общий срок — 5 недель, ведёт Дмитрий.\n\nАвтоматизация QA: 80% тестов сейчас ручные, регрессия занимает 3 дня. Ольга предложила внедрить Playwright для e2e-тестирования, что сократит регрессию до 4 часов; она готова обучить команду за неделю и нашла фреймворк Page Object, ускоряющий написание тестов в три раза.",
  "entities": [
    { "name": "Миграция API",   "type": "concept",  "definition": "Критичная задача Q2 — переход с deprecated-версии API до окончания поддержки в июне.", "quote": "Миграция API — приоритет номер один" },
    { "name": "Redis",          "type": "external", "definition": "Кеш-кластер для снижения latency дашборда с 800ms до 200ms.", "quote": "внедрить Redis-кластер из минимум трёх нод" },
    { "name": "AWS",            "type": "external", "definition": "Облако, где разворачивается Redis-кластер (~$500/мес).", "quote": "около 500 долларов в месяц на AWS" },
    { "name": "Playwright",     "type": "external", "definition": "Инструмент e2e-автоматизации, сокращающий регрессию с 3 дней до 4 часов.", "quote": "внедрить Playwright для e2e-тестирования" },
    { "name": "Page Object",    "type": "external", "definition": "Фреймворк паттерна page objects, ускоряющий написание тестов втрое.", "quote": "нашла фреймворк Page Object, ускоряющий написание тестов в три раза" },
    { "name": "Тёмная тема",    "type": "concept",  "definition": "Запрошенная 68% пользователей функция, приоритезированная в редизайне.", "quote": "68% пользователей в опросе просили тёмную тему" },
    { "name": "e2e-тестирование","type": "concept", "definition": "Сквозное автоматическое тестирование, заменяющее 80% ручных тестов.", "quote": "Playwright для e2e-тестирования" },
    { "name": "Проект Альфа",   "type": "product",  "definition": "Параллельная инициатива, на которую Игорь переходит после двух недель QA на миграции.", "quote": "он нужен на проекте Альфа" },
    { "name": "Алексей",        "type": "person",   "definition": "PM, ведёт согласование бюджета и фиксирует решения встречи.", "quote": "Алексей согласует бюджет с финансовым директором до пятницы" },
    { "name": "Мария",          "type": "person",   "definition": "Tech Lead, отвечает за миграцию API и предложение по Redis.", "quote": "Мария предложила внедрить Redis-кластер из минимум трёх нод" },
    { "name": "Дмитрий",        "type": "person",   "definition": "Designer, ведёт редизайн дашборда (5 недель).", "quote": "Общий срок — 5 недель, ведёт Дмитрий" },
    { "name": "Ольга",          "type": "person",   "definition": "QA, предлагает автоматизацию на Playwright и выделяет ресурс.", "quote": "Ольга предложила внедрить Playwright для e2e-тестирования" },
    { "name": "Сергей",         "type": "person",   "definition": "Backend-инженер на миграции API.", "quote": "Сергей берёт backend" },
    { "name": "Катя",           "type": "person",   "definition": "Frontend-инженер на адаптации к новому API.", "quote": "Катя — frontend-адаптацию" },
    { "name": "Игорь",          "type": "person",   "definition": "QA-ресурс, выделенный на миграцию на первые две недели.", "quote": "Ольга выделила Игоря в QA на первые две недели" }
  ]
}
```

## Why this passes the Self-Verification gate (`note_json_contract.md` §6)

- **R-1 shape**: all required fields present; `body` non-null (full mode); 4 bullets (band 4–7), 15 entities (band 12–15).
- **R-2 known_concepts**: "Проект Альфа", "Playwright", "Redis", "AWS" reuse the injected names verbatim — wikilinks will resolve, not dangle.
- **R-3 verbatim quotes**: every `quote` is an EXACT substring of `body` (copy-pasted, never paraphrased). E.g. `"Сергей берёт backend"` and `"68% пользователей в опросе просили тёмную тему"` both appear literally in `body`.
- **R-4 language**: source was Russian and `--translate` was NOT set → the note is Russian. The neutral `title`/`body` fields carry Russian **only because the meeting was Russian** — the field names imply no language. (For an importer that needs the historical keys, `--contract wiki` would rename them to `title_ru`/`ru_body` with identical content.)
- **R-5 clean names**: no `name` contains `/`, `—`, or `«»`.
- **No fabrication**: `author`/`published` are `null` (a meeting transcript states neither).

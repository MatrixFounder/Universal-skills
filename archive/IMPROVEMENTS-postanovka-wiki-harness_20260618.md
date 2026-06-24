# Постановка — `summarizing-meetings` как drop-in REASON-харнесс для wiki construct-пути

**Дата:** 2026-06-18 · **Заказчик:** фреймворк `obsidian-llm-wiki` (TASK 039 — унифицированный
construct-путь) · **Статус:** постановка (реализуется в этом, Universal-skills, репозитории).

## Зачем

`obsidian-llm-wiki` унифицирует «вход знаний» в **один** путь `wiki-import` с двумя
**ортогональными** осями:
- **layout (из конфига)** → КУДА филить (Karpathy `_sources/`+корневой `_concepts/` vs PARA
  тематическая папка+соседний `_concepts/`);
- **content-type (детект)** → КАКОЙ harness генерации: статья/препринт/тред →
  `summarizing-articles`; **встреча/транскрипт → `summarizing-meetings` (этот скилл)**;
  готовый summary → без генерации.

Чтобы транскрипт встречи, бро́шенный в ЛЮБОЙ vault (в т.ч. PARA), шёл тем же конвейером,
`summarizing-meetings` должен стать **drop-in REASON-харнессом**: принимать тот же вход-контекст
и опционально отдавать тот же выходной контракт, что потребляет `wiki-import apply`. Сейчас
скилл отдаёт двухуровневое pyramid-markdown с frontmatter+`[[wikilinks]]`, не структурированный
note-JSON, и его known-concepts-контракт не зафиксирован под wiki. Канонический контракт
REASON-шага: `obsidian-llm-wiki/skills/wiki-import-article/references/reason-contract.md`.

## Что НЕ меняется
- Существующий путь Karpathy `wiki-ingest` Phase 2 → `summarizing-meetings` (pyramid-вывод) —
  сохранить байт-в-байт (back-compat). Новый контракт — **опт-ин режим**, не замена.
- 4 типа встреч, PRE-FLIGHT, self-verification, tag-таксономия — остаются (это и есть тот
  «модель-агностичный пол», который мы хотим переиспользовать).

## Требования (RTM)

| ID | Требование | Критерий приёмки |
|----|-----------|------------------|
| **R-1** | **Опт-ин режим note-JSON.** Флаг (напр. `--emit note-json` / `--contract wiki`) заставляет скилл вернуть структуру, совместимую с reason-contract: `{title_ru?, title_orig?, tldr, summary_bullets[], ru_body?, entities:[{name,definition,quote,type}]}`. Для встречи `ru_body` = pyramid-конспект (или `null`+bullets, как summary-режим); `entities` = участники/решения/проекты/темы как `{type: person/concept/...}`. | вызов с флагом → валидный note-JSON; без флага → прежний pyramid (diff-чисто) |
| **R-2** | **known_concepts-инъекция (дисциплина).** Принять список `[{slug,name}]` и **переиспользовать существующее `name`**, когда сущность совпадает — не плодить вариант («Hermes» vs «Hermes Agent»). Зафиксировать формат входа `{slug,name}` (как эмитит `wiki-extract-concepts prepare`). | прогон с known_concepts, где есть совпадающая сущность → в выводе её `name`, не новый вариант |
| **R-3** | **Дословные цитаты сущностей.** Каждая `entities[].quote` — точная подстрока произведённого текста (для note-JSON: `ru_body`/`summary_bullets`), иначе `wiki-import apply` подставит name-mention-строку или дропнет сущность. Self-verification скилла должна это проверять. | self-check содержит пункт «каждая quote — дословная подстрока»; e2e: цитаты вербатимны |
| **R-4** | **Язык/перевод — явно.** Встречи обычно на исходном языке. Документировать: `summarizing-meetings` НЕ переводит (в отличие от `summarizing-articles` full-режима); `title_ru`/`ru_body` для одноязычной встречи = исходный язык, поле названо `*_ru` исторически — либо ввести нейтральные `title`/`body` в note-JSON-режиме. | контракт явно фиксирует языковую семантику; нет тихого ожидания перевода |
| **R-5** | **Чистые имена сущностей.** Без `/`, em-dash `—`, гильменов `«»` (downstream `_NAME_ALLOWLIST`-гейт wiki их отвергает; `apply` нормализует, но чистые имена надёжнее). | self-check содержит пункт о чистых именах |
| **NF-1** | Скилл остаётся **prose-харнессом** (без кода-конвертера в core); опт-ин note-JSON — это формат вывода, описанный инструкцией + шаблоном, не отдельный движок. Back-compat pyramid не трогается. | `diff -q` pyramid-вывода до/после; CI `validate_skill` PASS |

## Замечание о смежной неточности (для контекста)
`obsidian-llm-wiki`-внешний `wiki-ingest` SKILL.md заявляет, что `summarizing-meetings`
обрабатывает «transcript/**article**/paper». Это переоценка — скилл заточен под встречи.
В унифицированном дизайне статьи идут в `summarizing-articles`, встречи — сюда; формулировку
`wiki-ingest` стоит сузить (но это правка в obsidian-llm-wiki, не здесь).

## Итог
Минимальная, опт-ин доработка: добавить note-JSON-режим + зафиксировать known_concepts/verbatim/
clean-name контракт в PRE-FLIGHT/self-verification, не ломая существующий pyramid-вывод. Тогда
`summarizing-meetings` становится содержательным REASON-харнессом для встреч в едином wiki
construct-пути — симметрично `summarizing-articles` для статей — независимо от layout хранилища.

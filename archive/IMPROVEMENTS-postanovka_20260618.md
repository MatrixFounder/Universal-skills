# html2md — постановка на доработку (по итогам import-батча 2026-06-18)

Контекст и доказательная база — в `FEEDBACK-2026-06-18-import-batch.md`
(приложение «Проблемные примеры/ссылки» = репро-набор для каждого требования).
Каждое требование помечено приоритетом и снабжено критериями приёмки (AC).

Две системные болевые точки батча:
- **(A) JS-гейтнутые SPA-тела** — `lite` не видит тело, `chrome` его тоже не
  поднимает (lazy-load); спасает host-specific no-JS-вариант URL (`/lite/`). → R-1, R-3.
- **(B) бот-блок/paywall с непрозрачной диагностикой** — `FetchFailed` без HTTP-кода
  и без типа, вызывающий агент не знает «вручную» vs «повторить иначе». → R-2.

---

## Статус реализации (обновлено 2026-06-18, после фиксов)

> Эта постановка написана ДО раунда улучшений (retry/browser-UA/jina + диагностика +
> дата + no-JS-вариант). Ниже — фактическое состояние; формулировки находок выше
> относятся к версии ДО фиксов.

| Req | Статус | Что сделано |
|---|---|---|
| **R-1** (HIGH, JS-gated тело) | ✅ **DONE** | `--engine auto` теперь **проактивно** берёт no-JS-вариант для известных JS-гейтнутых хостов (HackerNoon `…/lite/<slug>`) — `acquire._nojs_variant`. Проверено вживую: `auto` на каноническом URL HackerNoon отдаёт **25 КБ тела** («trust tax»), а не 4 КБ хрома. Замечание: `--engine jina` HackerNoon НЕ спасает (канонический URL — шелл и для Jina); работает именно URL-rewrite. Жёсткий «boilerplate-сигнал» НЕ добавлен (риск ложных срабатываний на коротких легит-страницах) — вместо него надёжный rewrite. |
| **R-2** (HIGH, диагностика + анти-бот) | ✅ **DONE** | Envelope теперь несёт `details.status` (403/404/429/5xx) **и** `details.kind` ∈ {`bot_blocked`,`auth_required`,`not_found`,`rate_limited`,`server_error`,`unreachable`} — `acquire._fetch_kind`. Полный URL с query сохранён в `details.url` (редактится только секрет-параметры + userinfo) — `_redact` переписан. Анти-бот: honest-UA по умолчанию + **авто browser-UA эскалация на 403**; `--engine jina` для Cloudflare-hard. Проверено: SSRN → `{status:403, kind:"bot_blocked", url:"…?abstract_id=4200414"}`. Отдельные `--user-agent`/`--cookies` НЕ добавлены (jina + browser-UA закрывают кейсы; cookie — security-поверхность). |
| **R-3** (MED, хвостовой хром на chrome-пути) | ⚠️ **partial / doc** | reader-mode применяется к очищенному HTML **независимо от движка** → `<slug>.reader.md` чистый и для chrome. Тестер использовал `--stdout` (whole-page по контракту). Рекомендация: для чистого тела брать `reader.md`, не `--stdout`. Сам reader-mode — pdf-mastered (реплика, не правится здесь). |
| **R-4** (LOW, дата) | ✅ **DONE** | Приоритет структурной даты (`article:published_time`/`og:published_time`/`itemprop=datePublished`/JSON-LD) над эвристикой trafilatura + arXiv-id эвристика (`2504`→`2025-04`). Проверено: `arxiv.org/html/2504.20838` → `date: "2025-04"`. |
| **R-5** (LOW, офлайн-reader a16z) | 📝 **doc** | reader-mode — pdf-mastered (gated, здесь не правится). Задокументировано: для chrome-тяжёлых хостов живой `--engine lite` (trafilatura) чище офлайн-файла (`references/html-to-markdown.md`, honest-scope). |
| **R-6** (LOW, контракт `--stdout`) | ✅ **DONE** | SKILL.md §4 + `--help`: `--stdout` = **frontmatter + whole-page** (reader-вариант и картинки пропускаются). NB: исходная находка «stdout применяет reader-mode» — **сама была ошибкой**: на stdout идёт WHOLE-page (`emit` пишет `front + md_whole`), а лог `reader-mode root via…` — это всегда выполняемый шаг clean, который для stdout не эмитится. |

**Итог:** обе HIGH-боли (R-1, R-2) закрыты; R-4/R-6 закрыты; R-3/R-5 — doc/honest-scope
(reader-mode под G-1-репликацией). Эталонные команды-репро из FEEDBACK перепроверены.

---

## R-1 (HIGH) — авто-восстановление JS-гейтнутого тела (no-JS-вариант + детектор boilerplate)

**Проблема:** HackerNoon (П-2): `--engine lite` → 4 КБ только-хром; `--engine chrome
--stdout` → 28 КБ, тела всё равно нет. Сработал только ручной `/lite/` (П-3).

**Требование:**
1. **Детектор «контента нет, один хром».** После извлечения оценивать
   content-ratio (доля «тела» статьи к общему объёму / маркеры nav-боли: «Related
   Stories», «About Author», «Subscribe», «TOPICS», счётчики прочтений). Если тело
   подозрительно тонкое/boilerplate-доминированное — НЕ выдавать молча, а
   эскалировать (см. п.2) или вернуть явный сигнал.
2. **Авто-rewrite в no-JS-вариант для известных хостов.** Перед/вместо Chrome-эскалации
   пробовать host-specific reader-варианты: HackerNoon `…/lite/<slug>`, AMP (`?amp=1` /
   `/amp/`), print-view, известные зеркала. Для HackerNoon это и есть рабочий путь.
3. **Зафиксировать в доках:** Chrome-движок САМ ПО СЕБЕ не поднимает lazy-loaded тело —
   no-JS-вариант важнее Chrome для этого класса.

**AC:**
- `html2md.py "https://hackernoon.com/reputation-as-an-economic-primitive-the-case-for-erc-8004" --engine auto --stdout` → возвращает ТЕЛО статьи (через внутренний `/lite/`-rewrite), а не один хром.
- Если тело восстановить не удалось → envelope с `code`/`type`, явно говорящим «вероятно JS-gated, попробуйте no-JS/print-вариант» (не молчаливый «успех» с хромом).

## R-2 (HIGH) — прозрачная диагностика fetch-фейла + анти-бот

**Проблема:** SSRN (П-1): `{"error":"… HTTPStatusError","code":10,"type":"FetchFailed"}`
— без HTTP-кода, без различения причин; в `details.url` потерян query `?abstract_id=…`.

**Требование:**
1. **HTTP-код в envelope:** `details.status` (403/404/429/5xx) для каждого хопа.
2. **Типизировать FetchFailed** на `BotBlocked` (403 + признаки WAF/captcha),
   `AuthRequired` (login/paywall), `RateLimited` (429), `NotFound` (404),
   `ServerError` (5xx), `Unreachable`. Чтобы вызывающий знал: «вручную» vs «повтор».
3. **Сохранять ПОЛНЫЙ URL** (с query) в `details.url` — SSRN-страница существует
   только с `?abstract_id=4200414`.
4. **Анти-бот:** дефолтный браузероподобный User-Agent на `lite`-пути (httpx-UA
   режется такими сайтами, как SSRN) + опциональные `--user-agent` / `--cookies`
   (или `--cookies-from <netscape.txt>`) для cookie-гейтнутых источников.

**AC:**
- `html2md.py "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4200414" --engine lite --json-errors` → envelope с `details.status` (напр. 403) и `type` ∈ {BotBlocked, AuthRequired, …}; `details.url` содержит `?abstract_id=4200414`.
- С браузерным UA доля «успешных с первой попытки» статейных хостов не падает (регрессия исключена на ethereum/arxiv/eth.limo).

## R-3 (MED) — срезать хвостовой хром даже на chrome/whole-page пути

**Проблема:** chrome whole-page (П-2Б) тащит «Related Stories» с заголовками ЧУЖИХ
статей, «About Author», «TOPICS», баннеры — шум для агент-шага.

**Требование:** применять reader-извлечение к ОТРЕНДЕРЕННОМУ Chrome-DOM (а не только
к lite-HTML), чтобы и на chrome-пути отдавать тело статьи без related/comments/ads.

**AC:** в выводе HackerNoon (если идём через chrome) нет заголовков посторонних
статей из «Related Stories» и блоков «About Author»/«Comments»/«TOPICS».

## R-4 (LOW) — точность даты в метаданных

**Проблема:** arXiv `2504.20838` (апрель 2025) → `date: "2021-08-16"` (П-4).

**Требование:** приоритезировать `<meta property="article:published_time">` /
`og:published_time` / JSON-LD `datePublished`; для arXiv — дата сабмишена / вывод из
id (`2504` → 2025-04); sanity-check, чтобы не подхватывать произвольную дату из тела.

**AC:** `arxiv.org/html/2504.20838` → `date` в диапазоне 2025-04…05 (или пусто), не 2021.

## R-5 (LOW) — офлайн reader-mode на chrome-тяжёлых сайтах

**Проблема:** офлайн `.html` a16z (П-5): `spa-largest-contentful-subtree` оставил
шапку/навигацию.

**Требование:** улучшить офлайн-эвристику для сайтов с тяжёлым chrome ИЛИ
задокументировать, что для таких хостов живой-URL `lite` (trafilatura) чище офлайн-файла.

**AC:** офлайн a16z `.html` → без «Results/Searching…/EXPLORE/…», ЛИБО явная заметка
в `references/html-to-markdown.md` о предпочтении live-`lite`.

## R-6 (LOW, doc) — уточнить контракт `--stdout`

**Наблюдение:** `--stdout` по факту ПРИМЕНЯЕТ reader-mode (логи: `reader-mode root
via …`) и ВКЛЮЧАЕТ YAML-frontmatter (source/title/date) — но §4 SKILL.md называет
`--stdout` «whole-page Markdown only».

**Требование:** привести доку в соответствие фактическому поведению (reader + frontmatter
на stdout); добавить в `references/` совет про no-JS/`/lite/`-вариант для SPA-хостов.

**AC:** §4 SKILL.md описывает stdout честно; есть короткий «SPA → try /lite//amp/print».

---

## Вне рамок
- Логин/captcha-обход для жёстких paywall (SSRN полный PDF) — остаётся ручным.
- Полноценный head*less*-скроллинг/клики для lazy-load — дорого; no-JS-вариант (R-1)
  закрывает практический кейс дешевле.

## Приоритеты к реализации
**R-1 + R-2** (HIGH) дают наибольший выигрыш для агент-пайплайнов импорта (HackerNoon-
и SSRN-классы — самые частые «проблемные» источники). R-3..R-6 — инкрементально.

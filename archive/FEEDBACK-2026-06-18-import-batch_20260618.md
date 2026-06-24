# html2md — обратная связь по боевому прогону (2026-06-18)

> **⚠️ Статус (обновлено 2026-06-18, после фиксов):** находки ниже — это состояние
> ДО раунда улучшений. Уже исправлено: неверная дата arXiv (→ `2025-04`), непрозрачный
> fetch-фейл (теперь `details.status` + `details.kind` + полный URL с query), бот-блок на
> UA-проверяющих сайтах (авто browser-UA на 403), JS-гейтнутое тело HackerNoon
> (`--engine auto` берёт `/lite/`), Cloudflare-hard (SSRN/researchgate через `--engine
> jina`), контракт `--stdout`. Карта «находка → резолюция» — в
> [`IMPROVEMENTS-postanovka.md` §«Статус реализации»](IMPROVEMENTS-postanovka.md).
> Конкретно: claim «`--stdout` применяет reader-mode» оказался неверен — на stdout идёт
> **whole-page** (frontmatter + целая страница), не reader.

Контекст: импорт статей из кураторского списка (BlockUniverse/321, Menaskop) в
русскоязычный Obsidian-волт через obsidian-llm-wiki. html2md использовался как
универсальный шаг URL→Markdown в пайплайне `fetch → перевод RU → саммари →
сущности → индекс`. Ниже — что реально произошло на 6 источниках.

## Сводка результатов

| # | Источник | Команда (ключевое) | Итог |
|---|---|---|---|
| 1 | ethereum.org/roadmap/verkle-trees | `--engine lite --stdout` | ✅ чистая проза + frontmatter (title, **date**) |
| 2 | arxiv.org/html/2504.20838 (статья) | `--engine lite --stdout` | ✅ полный текст 47 КБ; ⚠️ **`date: 2021-08-16` неверна** (статья 04.2025) |
| 3 | trustlessness.eth.limo (манифест Бутерина) | `--engine lite --stdout` | ✅ 9 КБ, чисто |
| 4 | papers.ssrn.com/…abstract_id=4200414 | `--engine lite --stdout --json-errors` | ❌ `rc=10 FetchFailed: HTTPStatusError`, 0 байт |
| 5 | hackernoon.com/…erc-8004 (основной URL) | `--engine lite --stdout` | ❌ 4 КБ — **только хром** (тело за JS, нет в исходном HTML) |
| 6 | hackernoon.com/…erc-8004 (основной URL) | `--engine chrome --stdout` | ❌ 28 КБ — **всё ещё только хром** + related-stories; тело так и не извлеклось |
| 7 | hackernoon.com/**lite**/…erc-8004 | `--engine lite --stdout` | ✅ 25 КБ, чистое тело (reader нашёл `<article>`) |
| 8 | a16z (сохранённый `.html`, ранее) | `--stdout --reader-mode` (file) | ⚠️ reader=`spa-largest-contentful-subtree` оставил навигацию сайта |

**Счёт: 4/6 источников взялись с первой попытки**, HackerNoon — со второй (через
`/lite/`), SSRN — жёсткий бот-блок (не берётся).

## Что работает отлично (не трогать)

- **Один шаг URL→Markdown** — заменил прежний `curl → html2docx.js → docx2md.js`
  (2 шага + «сначала скачай, html2pdf живой URL не берёт»). Это главный выигрыш.
- **lite/trafilatura на server-rendered статьях** (ethereum, arXiv-HTML, eth.limo) —
  чистая проза, заголовки/списки/ссылки сохранены, мусора почти нет.
- **Авто-frontmatter (title/date/author)** — реально экономит парсинг шапки; для
  arXiv даже вытащил авторов и аффилиации.
- **Детерминизм** (turndown-ядро из docx + ридер-клинер из pdf), SSRF-защита,
  dedup картинок — всё на месте.

## Что подвело (фактические находки)

1. **JS-gated тело не извлекается даже Chrome-движком (HackerNoon).** На основном
   URL `--engine lite` дал 4 КБ хрома, `--engine chrome --stdout` — 28 КБ, но тело
   статьи так и не появилось (lazy-load/«Read on Terminal»-гейт; headless-рендер
   его не вызвал). Реально помогла **host-specific no-JS версия `/lite/`** (которую
   я нашёл вручную по ссылке «Read this story w/o Javascript» в самой странице).
   Авто-эскалация lite→chrome тут НЕ помогла — нужен был трюк с URL-вариантом.
2. **Бот-блок/paywall = непрозрачная ошибка (SSRN).** `rc=10 FetchFailed:
   HTTPStatusError` — без HTTP-кода и без различения «403 бот-блок / 429 / login /
   404». Вызывающему агенту непонятно: это «занести вручную» или «повторить
   иначе». (UA по умолчанию `httpx`, вероятно, и режется.)
3. **Неверная дата в метаданных (arXiv).** `date: 2021-08-16` для статьи
   2504.20838 (апрель 2025) — trafilatura подхватила чужую дату из HTML.
4. **Хвостовой хром на тяжёлых страницах.** Даже когда тело есть, в whole-page
   выводе остаются «Related Stories», «About Author», «TOPICS», баннеры — для
   агент-шага это шум, его приходится отрезать вручную.

## Вывод

Для «чистых» статейных сайтов html2md уже отличный и закрыл главный пробел
пайплайна. Болевые точки — ровно две категории: **(A) JS-гейтнутые SPA-тела**
(HackerNoon-класс — спасает no-JS/`/lite/`/AMP-вариант, а не Chrome) и **(B)
бот-блок/paywall с непрозрачной диагностикой** (SSRN-класс). Постановка на
доработку — в `IMPROVEMENTS-postanovka.md`.

---

## Приложение: все проблемные примеры/ссылки (для воспроизведения)

Каждый кейс — точная команда + наблюдаемый результат + обходной путь. Движок
html2md из `~/.claude/skills/html2md/scripts/html2md.py` (symlink → этот репозиторий).

### П-1. SSRN — бот-блок/paywall (FetchFailed, непрозрачно)
- **URL:** `https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4200414`
- **Команда:** `html2md.py "<url>" --stdout --no-download-images --engine lite --json-errors`
- **Результат:** `rc=10`, 0 байт, stderr:
  `{"v":1,"error":"fetch failed for https://papers.ssrn.com/sol3/papers.cfm: HTTPStatusError","code":10,"type":"FetchFailed","details":{"url":"https://papers.ssrn.com/sol3/papers.cfm"}}`
- **Проблема:** нет HTTP-кода в `details` (403? 429? login-gate?); нельзя отличить
  «жёсткий бот-блок → вручную» от «временная ошибка → повторить». UA `httpx`,
  вероятно, режется. **Заметьте:** в envelope `url` обрезан до `…/papers.cfm` (без
  query `?abstract_id=…`) — потеряна часть, по которой страница вообще существует.
- **Обход:** нет автоматического; занесён как `needs-manual` (скачать PDF под логином).

### П-2. HackerNoon — JS-гейтнутое тело (основной URL), не спасает даже Chrome
- **URL:** `https://hackernoon.com/reputation-as-an-economic-primitive-the-case-for-erc-8004`
- **Команда А:** `… --stdout --no-download-images --engine lite` → `rc=0`, **4 КБ —
  только хром** (лого, «Signup/Write», счётчик прочтений, автор-байлайн, «TLDR» без
  текста, теги). Тела статьи нет (его нет в исходном HTML — рендерится JS).
- **Команда Б:** `… --stdout --no-download-images --engine chrome` → `rc=0`, **28 КБ,
  но тела по-прежнему нет** — добавился ещё хром (featured-image, аудиоплеер,
  повторные байлайны, GPTZero-баннер, «← Previous / Up Next →», «About Author»,
  «Comments», «TOPICS», «Related Stories» с заголовками ЧУЖИХ статей). Основной
  текст так и не извлёкся (lazy-load/«Read on Terminal»-гейт; headless-рендер его
  не вызвал).
- **Проблема:** авто-эскалация `lite → chrome` НЕ помогает для этого класса; Chrome
  только добавляет мусора. Нет сигнала «тело — это boilerplate, контента нет».
- **Обход (сработал):** см. П-3 — no-JS `/lite/`-версия.

### П-3. HackerNoon `/lite/` — рабочий обход (host-specific no-JS вариант)
- **URL:** `https://hackernoon.com/lite/reputation-as-an-economic-primitive-the-case-for-erc-8004`
  (ссылку «Read this story w/o Javascript» пришлось найти вручную в теле страницы)
- **Команда:** `… --stdout --no-download-images --engine lite` → `rc=0`, **25 КБ,
  чистое тело** (лог: `reader-mode root via {'tag': 'article'}`). Полный текст:
  «trust tax», ERC-8004, эксперимент eBay с репутацией, «The Economics of Trust».
- **Вывод:** для HackerNoon (и, вероятно, Medium/Substack-зеркал) спасает не Chrome,
  а **переписывание URL в no-JS/`/lite/`/print-вариант**. Это должно делаться
  автоматически (см. постановку R-2).

### П-4. arXiv (HTML) — неверная дата в метаданных
- **URL:** `https://arxiv.org/html/2504.20838` (статья «Bitcoin, a DAO?», апрель 2025)
- **Команда:** `… --stdout --no-download-images --engine lite` → `rc=0`, ✅ полный
  текст 47 КБ, авторы/аффилиации извлечены верно.
- **Проблема:** `date: "2021-08-16"` во frontmatter — НЕВЕРНО (это не дата статьи;
  trafilatura подхватила чужую дату из HTML). Ожидалось ~2025-04 (по arXiv-id 2504).

### П-5. a16z (офлайн `.html`) — reader-mode оставил навигацию сайта
- **URL/файл:** `https://a16zcrypto.com/posts/article/quantum-computing-misconceptions-realities-blockchains-planning-migrations/`
  (сохранённый `.html`, офлайн-конвертация)
- **Команда:** `html2md.py <saved.html> --stdout --reader-mode` → лог:
  `html2pdf: reader-mode root via spa-largest-contentful-subtree`; в выводе остались
  «Results / Searching… / EXPLORE / Engineering learn more… / TABLE OF CONTENTS / Tags».
- **Проблема:** офлайн-ридер (`spa-largest-contentful-subtree`-эвристика) на a16z не
  отрезал шапку/навигацию. (На ЖИВОМ URL через `lite`/trafilatura та же a16z, скорее
  всего, вышла бы чище — офлайн-путь использует другой клинер.)
- **Примечание:** не блокер (тело захвачено целиком), но шум на агент-шаге.

### Для контраста — что взялось чисто с первого раза (не проблемные)
- `https://ethereum.org/roadmap/verkle-trees/` — `lite`, чисто + `date` верная.
- `https://arxiv.org/html/2504.20838` — `lite`, полный текст (кроме даты, П-4).
- `https://trustlessness.eth.limo/general/2025/11/11/the-trustless-manifesto.html` — `lite`, чисто.

> Примечание про downstream: `/` в двух извлечённых НАЗВАНИЯХ сущностей
> («стейкинг/бондинг», «TEE / ZK-доказательства») уронил последующий
> `wiki-extract-concepts` (его `_NAME_ALLOWLIST` не пускает `/`) — но это проблема
> МОЕГО пайплайна (синтез сущностей), НЕ html2md; внесено сюда лишь для полноты
> картины батча.

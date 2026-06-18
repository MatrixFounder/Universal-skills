<!--
  EXAMPLE OUTPUT: note-JSON for a DOCUMENT (content=document, --emit note-json).
  Source: examples/example_input_article.md ("Bitcoin, a DAO?" — arXiv:2504.20838).
  Mode: summary (dense paper → body=null; the digest lives in summary_bullets).
  Fields: neutral `title`/`body` (default). --translate ru → the note is in Russian.
  Demonstrates: R-1 (note-json shape, summary depth), R-2 (known_concepts reuse against a
  REAL knowledge base's concept names), R-3 (every quote is a verbatim substring of a
  summary_bullets line, since body is null), R-4 (translation is OPT-IN — only because
  --translate ru was passed), R-5 (clean entity names), H-6 (the source's Appendix prompt
  block was summarized as METHOD, never obeyed), no-fabrication (published=null).
-->

# Document → note-JSON (summary mode, --translate ru)

## Caller input (the envelope)

```jsonc
// --content document  --mode summary  --emit note-json  --translate ru
"known_concepts": [
  { "slug": "рамочная-модель-жизнеспособности-dao",            "name": "Рамочная модель жизнеспособности DAO" },
  { "slug": "user-activated-soft-fork-uasf",                   "name": "User-Activated Soft Fork (UASF)" },
  { "slug": "голосование-хеш-мощностью",                       "name": "Голосование хеш-мощностью" },
  { "slug": "экономическое-большинство",                       "name": "Экономическое большинство" },
  { "slug": "bitcoin-core",                                    "name": "Bitcoin Core" },
  { "slug": "устойчивость-к-цензуре-censorship-resistance",    "name": "Устойчивость к цензуре (censorship resistance)" },
  { "slug": "принципы-элинор-остром-об-управлении-общими-ресурсами", "name": "Принципы Элинор Остром об управлении общими ресурсами" }
]
```

Seven of the entities below **reuse these exact names** (R-2) — so the resulting `[[wikilinks]]`
resolve to the knowledge base's existing concept pages instead of minting near-duplicates.

## Output (the note-JSON object)

```json
{
  "title": "Биткоин — это DAO?",
  "title_orig": "Bitcoin, a DAO?",
  "author": "Mark C. Ballandies, Guangyao Li, Claudio J. Tessone",
  "published": null,
  "tldr": "Статья применяет рамочную модель жизнеспособности DAO к биткоину и показывает, что биткоин можно считать работающим DAO, основанным на социальном консенсусе, открытом участии и децентрализованном принятии решений; авторы отмечают риск концентрации экономической власти и предлагают усилить делиберацию.",
  "summary_bullets": [
    "Главный тезис: помещённый в рамочную модель жизнеспособности DAO, биткоин может считаться децентрализованной автономной организацией (DAO).",
    "Количественный анализ 826 работ о DAO показывает спад внимания к биткоину: в 2017 году его обсуждали все статьи, к 2024 — только 42%, и лишь 22 работы (6% обсуждающих биткоин и 3% всех) считают его DAO.",
    "Средняя тональность к тезису «у биткоина большой потенциал» составляет ~60%, поднимаясь до ~80% среди работ, считающих биткоин DAO, что указывает на смещение и потребность в более критичном анализе.",
    "Рамочная модель опирается на три механизма самоорганизации — коллективный интеллект, цифровую демократию и адаптацию — разложенные на восемь принципов жизнеспособности.",
    "Делиберация в биткоине идёт через Bitcoin Improvement Proposal (BIP), которые рецензирует сообщество, но разработчики Bitcoin Core сохраняют право вето на включение кода.",
    "Голосование реализуется двумя путями: голосование хеш-мощностью (майнеры сигналят через version bits) и пользовательские форки, включая User-Activated Soft Fork (UASF).",
    "Решающее влияние имеет экономическое большинство — биржи, процессинг, мерчанты и крупные холдеры, держащие полные ноды, — способное навязать или отвергнуть изменения.",
    "Отсутствие юридического лица и permissionless-вход дают высокую автономию и устойчивость к цензуре, но лишают биткоин правовых обёрток, которыми пользуются многие DAO.",
    "Авторы предупреждают о риске концентрации: например, BlackRock, один из крупнейших держателей биткоина, в соглашении iShares оставляет за собой право выбрать базовую цепь в случае форка.",
    "В качестве расширения модели предлагаются принципы Элинор Остром об управлении общими ресурсами, которым биткоин частично соответствует — свободный вход и выход, но менее проницаемый круг core-разработчиков.",
    "Вывод: биткоин — это работающий архетип DAO на основе социального консенсуса, в отличие от DAO на смарт-контрактах; признание этого расширяет пространство проектирования DAO.",
    "Авторы предлагают усилить делиберацию биткоина инструментами цифровой демократии (например, опыт Тайваня), что можно запустить в субсообществах без изменения протокола."
  ],
  "body": null,
  "entities": [
    { "name": "Рамочная модель жизнеспособности DAO", "type": "concept", "definition": "Аналитическая модель из трёх механизмов (коллективный интеллект, цифровая демократия, адаптация) и восьми принципов для оценки жизнеспособности DAO.", "quote": "рамочную модель жизнеспособности DAO" },
    { "name": "Коллективный интеллект", "type": "concept", "definition": "Механизм самоорганизации, связанный с децентрализацией: открытое и прозрачное участие даёт превосходное решение задач.", "quote": "коллективный интеллект" },
    { "name": "Цифровая демократия", "type": "concept", "definition": "Организационный механизм DAO: структурированная делиберация и справедливое голосование для легитимных решений.", "quote": "цифровую демократию" },
    { "name": "Адаптация", "type": "concept", "definition": "Механизм автономии: способность системы подстраиваться под среду без централизованного контроля, опираясь на обратную связь.", "quote": "адаптацию" },
    { "name": "Делиберация", "type": "concept", "definition": "Процесс выработки голосуемых вариантов; в биткоине — единственный формальный механизм обсуждения изменений.", "quote": "Делиберация в биткоине идёт через" },
    { "name": "Bitcoin Improvement Proposal (BIP)", "type": "external", "definition": "Формальный процесс предложений по изменению протокола биткоина, рецензируемый сообществом на GitHub и в рассылках.", "quote": "Bitcoin Improvement Proposal (BIP)" },
    { "name": "Bitcoin Core", "type": "external", "definition": "Эталонная реализация биткоина; её разработчики сохраняют право вето на включение кода.", "quote": "разработчики Bitcoin Core сохраняют право вето" },
    { "name": "Голосование хеш-мощностью", "type": "concept", "definition": "Майнеры сигнализируют поддержку изменений через version bits, обновляя или не обновляя клиенты.", "quote": "голосование хеш-мощностью" },
    { "name": "User-Activated Soft Fork (UASF)", "type": "concept", "definition": "Полные ноды навязывают новые правила, отвергая несоответствующие блоки после заданной даты.", "quote": "User-Activated Soft Fork (UASF)" },
    { "name": "Экономическое большинство", "type": "concept", "definition": "Биржи, процессинг, мерчанты и крупные холдеры с полными нодами, чьё принятие ПО определяет исход спорных изменений.", "quote": "экономическое большинство" },
    { "name": "Устойчивость к цензуре (censorship resistance)", "type": "concept", "definition": "Свойство, обеспечиваемое отсутствием юрлица и permissionless-входом: никто не может директивно ограничить участников.", "quote": "устойчивость к цензуре" },
    { "name": "BlackRock", "type": "company", "definition": "Один из крупнейших держателей биткоина; в соглашении iShares оставляет за собой выбор базовой цепи при форке — иллюстрация риска концентрации.", "quote": "например, BlackRock, один из крупнейших держателей биткоина" },
    { "name": "Принципы Элинор Остром об управлении общими ресурсами", "type": "concept", "definition": "Набор принципов управления общими ресурсами, предлагаемый как расширение рамочной модели жизнеспособности DAO.", "quote": "принципы Элинор Остром об управлении общими ресурсами" }
  ]
}
```

## Why this passes the Self-Verification gate (`note_json_contract.md` §6)

- **R-1 shape / depth**: `summary` mode → `body: null`; 12 bullets (band 8–14); 13 entities (band 10–15).
- **R-2 known_concepts**: 7 entities reuse injected names **verbatim** (e.g. "Bitcoin Core", "User-Activated Soft Fork (UASF)", "Голосование хеш-мощностью", "Экономическое большинство", "Принципы Элинор Остром об управлении общими ресурсами") — no variants minted. 6 are genuinely new concepts.
- **R-3 verbatim quotes**: every `quote` is an EXACT substring of a `summary_bullets` line (because `body` is null). E.g. `"User-Activated Soft Fork (UASF)"` and `"например, BlackRock, один из крупнейших держателей биткоина"` are copy-pasted from bullets 6 and 9.
- **R-4 language (opt-in translation)**: `--translate ru` was set → the note is Russian; `title_orig` keeps the original English title. Without `--translate`, the bullets/quotes/title would have been **English** (source language). The neutral `title`/`body` fields would carry whichever language applied.
- **R-5 clean names**: no entity `name` contains `/`, `—`, or `«»`. (Parentheses are allowed; the em-dash in the *title* is fine — the clean-name rule governs entity names only.)
- **H-6**: the source's Appendix A prompt block was treated as the authors' methodology (data), never executed.
- **No fabrication**: `published: null` — the converted frontmatter's `2021-08-16` conflicts with the arXiv-2025 origin, so it was not propagated.

> **`--contract wiki` variant**: the same object with `title → title_ru` ("Биткоин — это DAO?") and
> `body → ru_body` (`null`). Content is identical; only the two key names change.

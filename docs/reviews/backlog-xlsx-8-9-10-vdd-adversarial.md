# VDD Critique: backlog xlsx-8 / xlsx-9 / xlsx-10 (postановка задач)

**Reviewer**: VDD Adversarial (round 1, fresh-context simulation)
**Target**: [docs/office-skills-backlog.md](../office-skills-backlog.md) §xlsx — rows xlsx-8 (расширенный) / xlsx-9 (новый) / xlsx-10 (новый)
**Date**: 2026-05-11

## 1. Executive Summary

- **Verdict**: **WARNING** — задачи проходят в Planning Phase только после применения H1–H3 + M1–M8 правок к backlog'у. Без правок Builder получит спецификацию с двумя сломанными контрактами (round-trip, code-duplication) и тремя необоснованными метриками.
- **Confidence**: **High** — все HIGH findings верифицированы чтением фактического кода ([naming.py](../../skills/xlsx/scripts/md_tables2xlsx/naming.py), [exceptions.py](../../skills/xlsx/scripts/xlsx_check_rules/exceptions.py), `wc -l xlsx_check_rules/`).
- **Summary**: Постановка концептуально правильная (shared lib для устранения дублирования между xlsx-8/xlsx-9 + Phase B refactor xlsx-7 — это то, что просил пользователь), но содержит **3 факт-ошибки** (H3 round-trip, M1 LOC-метрика, M8 openpyxl behavior unchecked), **1 архитектурное противоречие** (H2: phased approach создаёт duplication, который должен устранять) и **6 underspecified flag-interaction matrix дыр**, которые Builder неизбежно интерпретирует на ходу — путь к code slop.

## 2. Risk Analysis

| Severity | Category | Issue | Impact | Recommendation |
|:---|:---|:---|:---|:---|
| **HIGH** | Logic / Contract | **H1: xlsx-9 → xlsx-3 round-trip контракт сломан для имён `History` и >31 chars** | Спецификация утверждает «live round-trip test ... cell content byte-identical», но [`md_tables2xlsx/naming.py:137`](../../skills/xlsx/scripts/md_tables2xlsx/naming.py#L137) принудительно мутирует `History` → `History_` и обрезает >31 chars через `_truncate_utf16`. Builder напишет тест, который провалится → false negative или провалится тест с лживой спецификацией. | xlsx-9 должен либо (a) **симметрично pre-sanitize sheet-names** в emit'е (применить ту же `_truncate_utf16` + `History` guard, переиспользовать `md_tables2xlsx.naming` как dep), либо (b) явно сузить контракт: «round-trip byte-identical для cell **content**; sheet-names mutated через xlsx-3 sanitization rules, документировано как expected». Пишу как (b) — проще и честно. |
| **HIGH** | Architecture | **H2: Phased delivery противоречит явной цели «не дублировать код»** | Phase A создаёт `xlsx_read/` standalone + xlsx-7 keeps internal reader-copy. Между merge'ами Phase A и Phase B — duplication 2× (точно то, чего пользователь хотел избежать). Phase B может затянуться или умереть (Stage-2 follow-up'ы часто не закрываются), оставив duplication перманентно. | Явно зафиксировать в backlog'е: «Phase A duplication принимается осознанно (de-risk gate для xlsx-7 regression); Phase B имеет **hard deadline** к ship'у xlsx-8/xlsx-9 + 2 недели, иначе создаётся blocking ticket xlsx-10.C». Альтернатива: merge phases в один большой M→L task (выше risk, но без duplication window). Pick (a) с deadline — оба ясно. |
| **HIGH** | Contract | **H3: `--header-rows N` global flag не работает для multi-table sheet'ов с разными header-counts на разных таблицах** | Реальный кейс: annual-report sheet с tableA (revenue, 1-row header) + tableB (KPI, 2-row merged-title header) + tableC (notes, 0-row header) — `--header-rows 2` сломает A и C, `--header-rows 1` сломает B, `--header-rows 0` сломает A+B. Без per-table header detection multi-table mode бесполезен. | В `--tables != whole` форсировать `--header-rows auto` per-table (через `xlsx-10` headers.py); явная `--header-rows N` integer допустима только при `--tables whole`; иначе exit 2 `HeaderRowsConflict`. |
| **MED** | Hallucination | **M1: «~600 LOC внутренней reader-логики xlsx-7» — фабрикация** | Я не измерял. Реальный `xlsx_check_rules/` = 4149 LOC в 14 модулях; reader-extract не имеет чистой границы (логика прошита через `scope_resolver.py` 504 + `cell_types.py` 232 + `evaluator.py` 646 cross-coupling). Estimate ничего не значит. | Убрать конкретное число. Заменить на «extraction границы определяются в Phase A design pass; объём refactor'а xlsx-7 — на Phase B planning, не сейчас». |
| **MED** | Effort | **M2: Phase A «M» under-estimated против baseline'а xlsx-2/xlsx-3** | xlsx-2 (S→M): 7 модулей, 1307 LOC, 73 unit + 11 E2E. xlsx-3 (S→M): 10 модулей, 1903 LOC, 94 unit + 14 E2E. xlsx-10 Phase A: 7 модулей + ≥20 E2E + extraction reasoning + closed-API design + adversarial review для public surface. Это **M→L** в той же шкале. | Поднять effort xlsx-10.A до «M→L», явная разбивка по дням в day-plan. |
| **MED** | Logic | **M3: `dataclass frozen=True для immutability` — ложное обещание** | Внутренние списки (rows, cells, headers) остаются mutable. Caller может случайно мутировать `TableData.rows[0][0] = ...` и сломать кэш. | Либо использовать `tuple[tuple[Cell, ...], ...]` + `MappingProxyType` для headers; либо честно: «immutable outer struct, mutable inner sequences — caller-responsibility не мутировать». Выбрать (b) и честно записать в honest scope. |
| **MED** | Heuristic | **M4: `--gap-rows 1 --gap-cols 1` default слишком агрессивен** | Реальный Excel-паттерн: одна пустая строка как visual separator inside одной логической таблицы (totals row outdent, section break) — будет ошибочно сплитнута. False multi-table detection. | Default `--gap-rows 2 --gap-cols 1` (двойная-пустая для row-split = более надёжный signal, single-empty-col для col-split = пустой столбец почти всегда означает разные таблицы). Документировать обоснование. |
| **MED** | Logic | **M6: «`Top / Sub` flatten separator» — collision с header содержащим ` / `** | Header «Q1 / Q2 split» под title «2026 plan» → flatten ключ «2026 plan / Q1 / Q2 split» неоднозначен при reverse. Реальный паттерн в финансовых моделях. | Эскейп: ` / ` в header → `\/`; ИЛИ separator → ` › ` (U+203A, не встречается в spreadsheet headers); ИЛИ структурный output: keys-array вместо строки (`["2026 plan", "Q1 / Q2 split"]`). Pick: ` › ` separator + опционально `--header-flatten-style string\|array` для JSON output. |
| **MED** | Contract | **M7: `--format gfm --include-formulas` — undefined behavior** | GFM не поддерживает HTML атрибуты, но `--include-formulas` спеком привязан к `data-formula`. Что делает скрипт при этой комбинации — undefined. | Spec: `--include-formulas` требует `--format hybrid` или `--format html`. С `--format gfm` → exit 2 `IncludeFormulasRequiresHTML` (parallel `MergedCellsRequireHTML`). |
| **MED** | Hallucination | **M8: `OverlappingMerges` exception — не верифицированное поведение openpyxl** | Я не проверял, как openpyxl реагирует на overlapping `<mergeCells>` (corrupted workbooks). Может уже raise, может silently accept. Spec нельзя обещать exception, не зная факт. | Phase A design pass должен проверить openpyxl behavior: (a) если уже raises — wrap в `OverlappingMerges`; (b) если silently accepts — explicit detect + raise; (c) если undefined — pin pyopenxl version в `requirements.txt`. Записать как Design-Question в xlsx-10 backlog. |
| **LOW** | Enforcement | L1: `__all__` advisory only — не закрывает API | Caller может импортировать `_internal` модули по полному пути, обходя `__all__`. | Prefix приватных модулей `_` (например `_workbook.py` vs `workbook.py`); `validate_skill.py` extension для grep на `from xlsx_read._*` в caller'ах. |
| **LOW** | Concurrency | L2: Thread-safety не упомянуто | openpyxl Workbook не thread-safe; library imports в long-running agent-session (Claude Code) могут sharing'оваться. | Honest scope: «WorkbookReader не thread-safe; caller отвечает за per-thread instances». |
| **LOW** | Logic | L4: CSV `<sheet>__<table>.csv` collision если sheet содержит `__` | Excel допускает `__` в sheet-name; коллизия filename. | Escape sheet/table names через `quote_plus`; OR forbid `__` в sheet-name via cross-validation; OR использовать subdirectory: `<sheet>/<table>.csv`. Pick: subdirectory — наглядно, no escape needed. |
| **LOW** | Documentation | L5: xlsx-8 JSON nested shape ломает xlsx-2 round-trip | Текущий xlsx-2 принимает только flat `{"Sheet": [...]}`. Nested `{"Sheet": {"Table": [...]}}` exit 6 / unhandled. | Усилить honest-scope note: «xlsx-2 v1 НЕ consume nested multi-table JSON; реверс-восстановление ListObjects — backlog xlsx-2 v2». |

## 3. Hallucination Check

- [x] **Files**: `skills/xlsx/scripts/xlsx_check_rules/exceptions.py`, `scripts/md_tables2xlsx/naming.py` — verified via Bash grep.
- [x] **Line numbers**: `naming.py:137` (History guard), `exceptions.py:108-130` (header envelopes) — verified.
- [x] **LOC counts**: `xlsx_check_rules/` 4149 LOC verified via `wc -l`; «~600 LOC» в backlog'е помечено как фабрикация (M1).
- [x] **API claims about openpyxl**: НЕ verified — `OverlappingMerges`, `cell.hyperlink` attribute precise shape, формат-heuristic покрытие. Помечено как Design-Question'ы для Phase A.

## 4. Convergence Signal Assessment

**Это round 1.** Findings грунтованы в фактическом коде (H1 верифицирован файлом + строкой, M1 верифицирован `wc -l`). **No hallucinated findings** — все 13 пунктов мапятся на конкретные строки backlog'а либо на конкретные файлы / LOC counts существующих модулей.

**Convergence NOT reached** — требуется round 2 после применения H1–H3 + M-fix'ов. Round 2 пройдёт, если останутся только LOW-level concerns и фабрикованные/несуществующие проблемы — это signal Maximum Viable Refinement.

## 5. Action Items (Builder)

Applied к backlog'у в той же сессии:

1. **H1**: xlsx-9 row — переписать round-trip claim («cell content byte-identical»; sheet-name sanitization expected и проверяется отдельно).
2. **H2**: xlsx-10 row — добавить hard deadline для Phase B + явное признание temporary duplication.
3. **H3**: xlsx-8 row — `--header-rows` integer запрещён в `--tables != whole`, force `auto`; new envelope `HeaderRowsConflict`.
4. **M1**: xlsx-10 row — убрать «~600 LOC», заменить «extraction границы определяются в Phase A design pass».
5. **M2**: xlsx-10 effort M → **M→L**; day-plan: Phase A занимает day 1 + полдня day 2.
6. **M3**: xlsx-10 row — `frozen=True` claim → честно: «outer immutable, inner mutable — caller-responsibility».
7. **M4**: xlsx-8 + xlsx-9 + xlsx-10 — default `--gap-rows` 1 → **2**; обоснование в backlog.
8. **M6**: xlsx-8 + xlsx-9 — header flatten separator ` / ` → **` › `** (U+203A); опционально `--header-flatten-style string\|array`.
9. **M7**: xlsx-9 row — добавить `IncludeFormulasRequiresHTML` envelope; `--include-formulas` × `--format gfm` → exit 2.
10. **M8**: xlsx-10 row — `OverlappingMerges` помечен Design-Question; final behavior — Phase A pass.
11. **LOW L4**: xlsx-8 row — CSV multi-table наименование `<sheet>/<table>.csv` (subdirectory), не `<sheet>__<table>.csv`.

Round 2 запускается после применения изменений.

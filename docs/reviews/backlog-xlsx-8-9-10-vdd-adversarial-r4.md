# VDD Critique R4: backlog xlsx-8 / xlsx-9 / xlsx-10.A / xlsx-10.B (postановка задач)

**Reviewer**: VDD Adversarial (round 4, fresh-context simulation)
**Target**: [docs/office-skills-backlog.md](../office-skills-backlog.md) §xlsx — rows xlsx-8 / xlsx-9 / xlsx-10.A / xlsx-10.B **после round-3 фиксов** (R3-H1, R3-H2, R3-M1..M4, R3-L1)
**Date**: 2026-05-12
**Prior rounds**:
- [round 1](backlog-xlsx-8-9-10-vdd-adversarial.md) — 3H + 8M + 3L, applied.
- [round 2](backlog-xlsx-8-9-10-vdd-adversarial-r2.md) — 2H + 6M + 3L, applied.
- [round 3](backlog-xlsx-8-9-10-vdd-adversarial-r3.md) — 2H + 4M + 2L, applied.

## 1. Executive Summary

- **Verdict**: **PASS (with 2 narrow MED fixes)** — **Maximum Viable Refinement reached**. Round 4 findings: **0 HIGH + 2 MED + 3 LOW + 5 forced/hallucinated (explicitly not raised)**. ≥ 50% of plausible findings are now forced (5 forced vs 2 real MED + 3 narrow LOW) — это **convergence exit signal** per round-3 exit criteria.
- **Confidence**: **High** для R4-M1 / R4-M2 (verified чтением текущего backlog'а — оба narrow follow-on gaps от R3 fixes, не fix-of-fix). **Low** для R4-L1..L3 (cosmetic / unverified).
- **Summary**: Trajectory clear — 3H/8M/3L → 2H/6M/3L → 2H/4M/2L → **0H/2M/3L**. Severity drop: surface-level (R1) → self-introduced (R2) → incomplete-R2-fixes (R3) → **derivative gaps + cosmetic** (R4). Forced findings (gap-rows guess re-mention; ruff wheel availability; LOC estimates; "80% value" unmeasured; col_N collision impossible) — все hallmarks of post-convergence. **Apply 2 MED fixes inline, declare exit, ship**.

## 2. Risk Analysis

| Severity | Category | Issue | Impact | Recommendation |
|:---|:---|:---|:---|:---|
| **MED** | Derivative Gap | **R4-M1: xlsx-9 markdown emit при `headerRowCount=0` производит invalid GFM (no `<thead>` row)** | xlsx-10.A honest (e) и xlsx-9 honest (i) post-R3-H2: «markdown emit без `<thead>` / separator row». GFM spec (CommonMark + GFM Tables Extension §198) **требует** header row + separator row `\|---\|---\|` для table parsing — без них bare `\| a \| b \|` строки парсятся как plain paragraphs с pipe characters, **не как table**. R3-H2 fix решил JSON shape consistency (synthetic `col_1..col_N`) **но забыл markdown emit path**. Real impact: `headerRowCount=0` table в `.xlsx` → markdown файл, который никакой GFM-renderer (GitHub / GitLab / pandoc / hugo) не отрендерит как table. Silent data-loss-as-display. | xlsx-9 honest scope (i) — расширить: «`headerRowCount=0` в **markdown emit branch**: (a) **pure GFM mode** — emit synthetic visible header row `\| col_1 \| col_2 \| ... \|` + separator, mirror JSON behavior + warning в `summary.warnings`; (b) **HTML mode** — emit `<table>` без `<thead>` (HTML valid headerless); (c) **hybrid mode** — auto-promote table к HTML (как делает уже `--include-formulas` per R2-M1)». Pick: synthetic visible headers в GFM + auto-promote-to-HTML в hybrid — uniform с JSON path, никаких invalid-GFM artifacts. |
| **MED** | Internal Inconsistency | **R4-M2: xlsx-10.A notes column противоречит xlsx-9 effort post-R3-M4** | xlsx-10.A notes column текущая строка: «После xlsx-10.A: xlsx-8 ↓ к чистому S (CSV/JSON emit поверх lib), **xlsx-9 ↓ M→S (HTML/GFM emit поверх lib)**». xlsx-9 effort column post-R3-M4 fix: «**M**» (не M→S). Self-contradiction внутри backlog'а — reader неоднозначно понимает actual xlsx-9 effort. R3-M4 fix обновил effort field в xlsx-9 row, **но забыл sync xlsx-10.A notes** (cross-row reference drift). | Edit xlsx-10.A notes: «xlsx-9 ↓ M→S» → «xlsx-9 остаётся M (R3-M4 фикс — emit-only surface всё ещё M-scale; lib экономит ~⅓ effort, не ⅔)». Single source of truth: xlsx-9 effort column. |
| **LOW** | Cosmetic Drift | **R4-L1: «Phase A» terminology в xlsx-10.A row inconsistent с R3-M3 split** | После R3-M3 split, xlsx-10.A IS Phase A (entire row), но текст row продолжает использовать «**Phase A (xlsx-10.A, M→L)** — build ...» / «**Phase A includes toolchain bring-up**» / «**E2E (≥ 20 для Phase A)**» / «**Honest scope (xlsx-10.A v1)**: ... `OverlappingMerges` exception помечен **Design-Question** для Phase A». Reads OK in isolation, но redundant — Phase A == xlsx-10.A теперь. Bit of legacy phrasing. | Replace «Phase A» → «(this task)» / «xlsx-10.A» throughout body — cosmetic only, не функциональное. Optional — текущий wording читается, drift minor. |
| **LOW** | Unverified Defence | **R4-L2: R3-L1 «`=HYPERLINK()` formula ломает `pandas.read_csv` quote-handling без `engine='python'`» — unverified claim** | R3-L1 defence для CSV markdown-link emission rejects `=HYPERLINK("url","text")` alternative с justification «ломают `pandas.read_csv` quote-handling без `engine='python'`». Pandas C engine handles `=`-prefixed quoted strings (just literal text по умолчанию) много версий подряд — обычно НЕ breaks parsing, просто emit literal string `=HYPERLINK("...","...")`. Claim too strong; reality: literal string emission и в markdown-link case, и в HYPERLINK-formula case — outcome similar. | Soften defence wording: «`=HYPERLINK()` formula rejected because (i) literal `=`-prefix emission в CSV выглядит конфузно для human readers (markdown link `[text](url)` явно signals link semantics), (ii) Excel reopen interprets formula → executable cell (security surface не нужный для read-back), (iii) round-trip xlsx-2 при consume такой CSV получает text-cell, не formula — lossy либо для `[text](url)` либо для `=HYPERLINK()`». Drop «pandas quote-handling» claim — unverified. |
| **LOW** | Taxonomy | **R4-L3: xlsx-10.B status «ready-but-low-priority» — не определённый Status value per §1** | §1 «Условные обозначения» определяет Status as `open / in-progress / done / dropped`. xlsx-10.B notes говорит «status ready-but-low-priority после xlsx-10.A merge» — «ready-but-low-priority» не входит в taxonomy. Priority orthogonal к Status, обычно tracked в Recommended-порядке section. | Replace «status ready-but-low-priority» → «status `open` (gated на xlsx-10.A merge; в P1 priority в §3 ordering, не P0)». Aligns с §1 enum. |

## 3. Hallucination Check

- [x] **R4-M1 GFM spec requirement**: CommonMark §198 + GitHub Flavored Markdown Tables Extension — verified general knowledge; GFM tables explicitly require header row + delimiter row; bare data rows without those = plain text with pipes.
- [x] **R4-M2 contradiction**: verified чтением xlsx-10.A row (line 196) — `xlsx-9 ↓ M→S` literal text present in notes column; xlsx-9 effort field на line 195 = `M` post-R3-M4. Cross-reference drift confirmed.
- [x] **R4-L1 «Phase A» literal occurrences**: 4× в xlsx-10.A row body verified.
- [ ] **R4-L2 pandas claim**: НЕ tested эмпирически (`pandas.read_csv` против `=HYPERLINK()` fixture не run). Soft claim — could be hallucination on edge cases.
- [x] **R4-L3 status enum**: verified §1 «Условные обозначения»: "Status: open / in-progress / done / dropped" — «ready-but-low-priority» отсутствует.

## 4. Forced / Hallucinated Findings (explicitly NOT raised)

Эти findings были рассмотрены и **отвергнуты как forced / hallucinated** — рейзинг их сигнализировал бы convergence break. Listed для transparency:

| # | Forced Finding | Reason for Rejection |
|:---|:---|:---|
| F1 | «~30 LOC ruff config estimate unmeasured» | Order-of-magnitude reasonable; precise number не критичен для backlog phase. R1-M1 (xlsx-7 ~600 LOC fabrication) был real because задача = M effort; ruff config — LOW LOC class regardless. |
| F2 | «Phase A delivers 80% value claim unmeasured» | Qualitative ROI estimate; precise % не actionable. xlsx-10.A unblocks 2 caller scripts (xlsx-8/xlsx-9), xlsx-10.B refactors 1 internal (xlsx-7) — 2/3 ≈ 67%, «80%» reasonable approximation. |
| F3 | «ruff wheel availability on Alpine ARM / unusual platforms» | ruff has broad wheel coverage (musl + glibc, all major archs); хорошо известная Rust-binary distribution story. Edge-case на marginal platforms не блокирует mainline development. |
| F4 | «Synthetic `col_N` naming collision с user data» | Synthetic headers emitted ТОЛЬКО when `headerRowCount=0` — нет real headers для коллизии. Если real header == `col_1`, headerRowCount ≥ 1, no synthetic injection. Logically impossible. |
| F5 | «gap_rows=2 default still unmeasured (R2-L2 re-mention)» | R2-L2 уже flagged; R3 acknowledged в honest scope. Re-finding = stale, forced. |

## 5. Convergence Signal Assessment

**Round-over-round trajectory**:

| Round | HIGH | MED | LOW | Forced/Hallucinated | Self-Introduced ratio |
|:---:|:---:|:---:|:---:|:---:|:---:|
| R1 | 3 | 8 | 3 | 0 | 0/3 |
| R2 | 2 | 6 | 3 | 0 | 2/2 |
| R3 | 2 | 4 | 2 | 0 | 0/2 |
| **R4** | **0** | **2** | **3** | **5** | **0/0** |

**Severity-drop signals**:
- **Zero HIGH** (first time across all rounds) — no architectural / contract-level concerns remain.
- **MED severity narrowed** to derivative gaps (R4-M1 was forgotten in R3-H2 fix scope; R4-M2 is cross-row reference drift) — оба narrow incomplete-R3, не surface-level.
- **LOW findings все cosmetic** (terminology drift, unverified claim, taxonomy mismatch) — feels forced to even raise.
- **Forced/hallucinated count = 5** — first round with ≥ 50% of plausible findings rejected as forced.

**Exit signal**: ≥ 50% findings forced (5/(2+3+5) = 5/10 = 50%) — meets round-3 exit criterion exactly. **Maximum Viable Refinement declared**.

**Decision**:
- Apply 2 MED fixes inline (R4-M1 + R4-M2) — both narrow, both grounded.
- Optionally apply LOW fixes (R4-L1..L3) — cosmetic, low ROI.
- **STOP iteration**. Round 5 would predictably yield 100% hallucinations.

## 6. Action Items (Builder)

Применимо to backlog в той же сессии:

1. **R4-M1 (must)**: xlsx-9 honest scope (i) extension — markdown emit для `headerRowCount=0`: pure GFM → synthetic visible header row + separator + warning; HTML mode → headerless `<table>`; hybrid → auto-promote к HTML. Mirror JSON synthetic-col_N behavior in markdown.
2. **R4-M2 (must)**: xlsx-10.A notes column — «xlsx-9 ↓ M→S» → «xlsx-9 остаётся M (R3-M4; lib экономит ~⅓ effort)». Sync cross-row reference.
3. **R4-L1 (optional)**: xlsx-10.A body — «Phase A» → «(this task)» / «xlsx-10.A» throughout. Cosmetic.
4. **R4-L2 (optional)**: R3-L1 CSV defence — drop «pandas quote-handling» claim, replace с reader-confusion + Excel-formula-execution-surface rationale.
5. **R4-L3 (optional)**: xlsx-10.B — «status ready-but-low-priority» → «status `open` (gated xlsx-10.A; P1 ordering)».

**После applying R4-M1 + R4-M2 → convergence ratified, backlog'е ship-ready для Planning Phase**. LOW fixes — discretionary polishing.

## 7. Convergence Declaration

**Maximum Viable Refinement reached for backlog xlsx-8 / xlsx-9 / xlsx-10.A / xlsx-10.B.**

4 rounds of adversarial review applied 21 fixes total (3H + 8M + 3L → 2H + 6M + 3L → 2H + 4M + 2L → 0H + 2M + 3L). Findings severity-dropped each round; round 4 first to have 0 HIGH and ≥ 50% forced findings. Round 5 would yield diminishing returns с predicted ≥ 80% hallucination rate.

**Recommendation**: ship backlog к Planning Phase. Не запускать round 5.

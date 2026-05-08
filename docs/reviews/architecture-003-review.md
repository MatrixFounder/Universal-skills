# Architecture Review — Task 003 (xlsx-7 / `xlsx_check_rules.py`)

**Date:** 2026-05-08
**Reviewer:** Architecture Reviewer (subagent)
**Target:** `/Users/sergey/dev-projects/Universal-skills/docs/ARCHITECTURE.md`
**Status:** **APPROVED WITH COMMENTS** — no blockers; 3 MAJOR fixable in-place; the rest are 🟢.

## General Assessment

The document is unusually tight for a 12-module greenfield. F1–F11 map 1:1 to package modules with clean unidirectional dataflow (F1 → F11; F2 → F3 → F4; F5/F6/F7/F8 layered; F9/F10 sinks). Q2/Q3/Q5/Q7 closures are reasoned, not hand-waved. xlsx-6 envelope contract (M2) is correctly framed as frozen, with three loci of enforcement (F9.emit_findings, F11._partial_flush, fixtures #39/#39a/#39b). CLAUDE.md §2 boundary is respected — no helper crosses into `office/`, justified inline (§3.1 anti-pattern note). `string.Template`, ruamel.yaml event-stream alias-rejection, and the closed 17-node AST collectively neutralise the well-known YAML/regex/format-string vectors. The §4.2 invariant inventory is the right kind of paranoid.

Three real items below; the rest are polish.

## 🔴 CRITICAL

*(none)*

## 🟡 MAJOR

### M-1 — Q3 closure has a residual corner case for `replace` when remark column letter exists in input but lies LEFT of a written column (§1 Q3 row, §8.3, §3.2 `remarks_writer.py` row)

The reasoning "WriteOnlyWorkbook overwrites the column on a per-row basis using the same letter; no second pass needed" is correct **only when the remark column letter is to the right of, or coincident with, the rightmost data column**. If the user passes `--remark-column B` and the input has data in `A..F`, the streaming path must emit each row's full A..F sequence with `B`'s cell *substituted* — not appended. `WriteOnlyWorkbook.append([row…])` writes positionally; the writer therefore needs to **read the source row** to know A, C, D, E, F values, which is a one-pass *over the source* (using `read_only=True`) feeding a one-pass *to the destination*. That's still single-pass per workbook, but the architecture needs to say so. **Fix:** add to §1 Q3 closure (and to F10 functions): "`write_remarks_streaming` opens the source via `openpyxl.load_workbook(read_only=True)` and the destination via `WriteOnlyWorkbook`; for each source row it builds `[cell_or_remark for col in range(1, max_col+1)]` and `append`s. The remark column letter need not be rightmost." Otherwise a Developer reading §1 will assume `WriteOnlyWorkbook` magically overwrites and ship a regression on fixture #34/#35 with `--remark-column B`.

### M-2 — F11._partial_flush ordering is under-specified for the M2 invariant (§5.4, §2.1 F11 functions)

§5.4 commits to all-three-keys on every code path including timeout-partial-flush. §2.1 says `_partial_flush` "flushes all-three-keys envelope on stdout when `--json` is set." Missing: **when** in the SIGALRM/timeout handler this fires, and the `summary.elapsed_seconds = timeout` field write ordering. If `_partial_flush` is invoked from the signal handler (async-signal-unsafe wrt `json.dump` + buffered stdout), Python may interrupt mid-write and emit a torn envelope — which is exactly the regression #39a is supposed to catch but won't if the test harness times out *before* the handler completes. **Fix:** specify in §2.1 F11 (and §5.4) that the wall-clock watchdog sets a flag checked by the per-rule loop in F11._run, and `_partial_flush` runs in the **main thread** post-loop, not from a signal handler. Then add a sentence: "stdout is `os.fdopen(1, 'w', buffering=1)` line-buffered or `flush()` is called after `json.dump`." Without that ordering nailed down, fixture #39a passes locally and flakes in CI.

### M-3 — Module budget arithmetic is off (§3.2 totals row)

Counting the budget column: 10+80+220+250+200+400+200+400+450+250+250+350+500 = **3560**. The header says "Total cap ≤ 3560 (engineering buffer over the ~2200–2800 estimate)" — that matches my count, but the §1 Q2 row says "**total ≤ 3000 LOC**." Internal contradiction; pick one. 3560 is the honest engineering cap; 3000 is aspirational. **Fix:** change §1 Q2 row to "11 modules + `__init__.py`, total ≤ 3560 LOC, each ≤ 500 LOC" and align prose in §3.1 ("~2200–2800 LOC" estimate vs ≤3560 budget). This is also a YAGNI tell: 3560 is **+27 %** over the upper estimate — defensible as buffer but worth a sentence acknowledging it.

## 🟢 MINOR

- **m1 — `recheck` wheel reality (D5):** `recheck` ships as a **Scala/JVM CLI** (github.com/makenowjust-labs/recheck); the Python interop is via subprocess to a `recheck` binary, not a pip wheel. The xlsx-7 architecture says "soft-import" which is technically dishonest — there is no `import recheck`. **Fix:** §6.3 reword "Soft-imported PyPI dependency" → "soft-detected external CLI: `shutil.which('recheck')`; if present, invoked via `subprocess.run(['recheck', '--timeout=1', PATTERN], …)` at parse time." But this contradicts §6.4 "No `subprocess`." So either (a) drop `recheck` entirely and rely solely on the 4-shape hand-coded reject-list (the D5 fallback is already specified and adequate), or (b) carve a documented exception in §6.4. **Recommendation: option (a)** — drop the `recheck` mention everywhere; the fallback is the implementation. The Task-Reviewer correctly flagged this and you correctly locked D5; the architecture document just hasn't caught up to the consequence that "soft import" is a category error.
- **m2 — F4 fold-into-F3:** Could fold but shouldn't. F4 is the type vocabulary consumed by F3 (parser), F7 (evaluator), F8 (cache key canonicalisation via `to_canonical_str`). Folding into F3 forces F7/F8 to import from `dsl_parser.py`, which leaks parser internals into the evaluator. Keep separate.
- **m3 — 17 invariants in §4.2:** Items 1, 2, 3 (no `eval` / no `ast.parse` / no `yaml.safe_load`) are one CI grep test serving three invariants — fine. Item 8 ("Closed AST 17 node types — no negative fixture") is belt-and-suspenders only if the parser unit tests are exhaustive; mark "locked by F3 parser unit tests, not a battery fixture" so the Planner doesn't size a fixture for it.
- **m4 — §4.1 `Finding` entity:** correctly distinguishes per-cell vs grouped (M2 all-three-keys + sentinels per SPEC §7.1.2); no issue.
- **m5 — §4.1 `AggregateCacheEntry`:** `cache_hits` per-entry is correct; intra-rule dedup on `(rule_id, cell)` and inter-rule no-dedup matches SPEC §5.5.3 verbatim. Replay determinism nailed by fixture #19a.
- **m6 — §7.3 `Path.resolve()` symlink TOCTOU:** the architect's same-path guard catches static symlink races but not "symlink mutated between `resolve()` and `open(output, 'wb')`". Acceptable; xlsx-6 has the same gap and locks it as honest scope. Add one line to §7.4: "TOCTOU between resolve() and write() is out of scope; mirrors xlsx-6 cross-7 H1 honest scope."
- **m7 — §8 perf claim (100K × 5 ≤ 30 s ≤ 500 MB):** realistic with `read_only=True` + F8 cache (5 rules sharing scopes ≈ 1–2 column walks). 500 MB RSS is generous for openpyxl iter-rows on 100K rows × ~10 cols (≈ 50 MB live); the 10× headroom absorbs regex compile + ast nodes + summary buffers. Not a bluff.
- **m8 — CLAUDE.md §2 spot-check:** F2/F3/F4/F5/F6/F7/F8/F9/F10 all touch sheet/row/column/header/range abstractions absent from docx/pptx/pdf. None tempts a future `office/` promotion. No "DO NOT promote" comments needed.
- **m9 — §3.2 `cli.py` budget 500 LOC for F1+F11:** xlsx-6's `cli.py` is the precedent and lands ~470 LOC pre-refactor. Tight but feasible.

## Final Recommendation

**APPROVED WITH COMMENTS.** Address M-1, M-2, M-3 in-place; m1 (`recheck` reality) is cheap and correctness-relevant — fold it. Planner can proceed once those four edits land; no user gating required.

---

```json
{"review_file": "docs/reviews/architecture-003-review.md", "has_critical_issues": false}
```

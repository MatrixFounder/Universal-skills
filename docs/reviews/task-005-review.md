# Task 005 Review — `xlsx-3 / md_tables2xlsx.py`

- **Date:** 2026-05-11
- **Reviewer:** task-reviewer agent
- **Target:** `docs/TASK.md` (Task 005, slug `md-tables2xlsx`, DRAFT v1)
- **Status:** **APPROVED WITH COMMENTS** (round 1) — proceed to Architecture after addressing M1–M3 in-place. No blocking issues.

---

## General Assessment

This is a strong, well-structured draft. The Q&A-derived decisions (D1–D5) are explicit, all five locked surfaces (exit codes, public API, CLI flags, replication boundary, cross-cutting parity) line up with the xlsx-2 precedent, and §8's single-source-of-truth pin on `convert_md_tables_to_xlsx` correctly mirrors the Task-004 M3 lock. The RTM has 11 requirements with sub-feature counts averaging 4.6 (range 3–7, all ≥ 3 minimum). All 4 UCs carry Actors / Preconditions / Main / Alt / Postconditions / Acceptance Criteria. The cross-5 envelope shape (`{v, error, code, type, details}`) is correct on first try — no regression of the Task-004 M1 trap. The xlsx-2 review's M1/M2/M3 lessons appear to have been internalised: there is no `ok`/`message` mention, R7.c-style "defence-in-depth" overclaims, or missing §11.

Three Major items need correction before Architecture commences: cross-references inside §0/D1 and D3 mislabel honest-scope numbers (M1); §11 preamble claims "Each [scope item] is locked by a regression test (R9)" but R9 only enumerates 5 of the 10 §11 items (M2); the D2 sheet-naming sanitisation pipeline has an ambiguous interaction between (f) reserved-`History` suffix and (g) workbook-wide dedup (M3). Minor items are cheap tightenings.

---

## 🔴 CRITICAL (BLOCKING)

*(none)*

---

## 🟡 MAJOR

### M1 — Four cross-references in §0 cite the wrong honest-scope index

- **Where:** §0/D1 (`§11.7` for "out of scope deferred"), §0/D3 (`§11.4` for `<br>` non-wrap policy), UC-4-area (`§11.6` for TOCTOU mirror). UC-3 A1's `§11.8` is correct.
- **Finding:** §11 numbers items 1=RST grid, 2=MultiMarkdown, 3=no `wrap_text`, 4=no rich-text Runs, 5=no formula resolution, 6=no `--strict-dates`, 7=blockquoted tables skipped, 8=overlapping HTML merge, 9=no `<style>`/`<script>`, 10=symlink TOCTOU. D1's "Out of scope... RST grid tables, MultiMarkdown extensions, PHP-Markdown-Extra table caption (§11.7)" should be `§§11.1–11.2`. D3's `<br>` reference to `§11.4` should be `§11.3`. UC-4-area's `§11.6` should be `§11.10` (TOCTOU).
- **Why it matters:** The Developer following Stage-2 / 005-09 will jump to the cited §11.N to read the exact contract being locked. Wrong pointer → divergent implementation.
- **Fix:** Re-thread the four cross-references against actual §11 numbering.

### M2 — §11 preamble overclaims R9 regression coverage; only 5 of 10 items are locked

- **Where:** §11 preamble ("Each is locked by a regression test (R9)") + R9 sub-bullets (a)–(e).
- **Finding:** R9 enumerates lock-in tests for §11.1 (RST), §11.3 (wrap_text), §11.4 (rich-text Runs), §11.6 (strict-dates), plus a non-§11 GFM colspan/rowspan claim. Missing from R9: §11.2 (MultiMarkdown), §11.5 (no formula resolution), §11.7 (blockquoted tables), §11.8 (overlapping HTML merge), §11.9 (`<style>`/`<script>` skip), §11.10 (TOCTOU). 6 honest-scope items without a regression test backstop.
- **Why it matters:** Either preamble is aspirational (and a Developer can quietly walk back any of these limitations in v1.1), or R9 is incomplete. Both readings are bugs.
- **Fix:** Pick one:
  - **Option A (preferred — matches xlsx-2):** Expand R9 to (a)–(j), one sub-bullet per §11 item. Cheap one-liners; TOCTOU (§11.10) is hard to regression-test deterministically — document the gap explicitly in R9.
  - **Option B:** Weaken §11 preamble to "Each is documented as a v1 limitation; selected items are locked by R9 regression tests (R9.a–e). Items §11.2 / §11.5 / §11.7 / §11.8 / §11.9 / §11.10 are documentation-only locks pending v2 demand."

### M3 — D2 sheet-naming pipeline: ordering between (f) reserved-name suffix and (g) dedup is ambiguous

- **Where:** §0/D2 sanitisation pipeline steps (e)–(g), plus R4.c/R4.d.
- **Finding:** Three unspecified interactions:
  1. **`History` × dedup:** two `## History` headings — does the second become `History_-2` or `History_` (no collision because first is `History_`, not `History`)?
  2. **Re-truncation after dedup:** a 31-char prefix needs to make room for `-2` suffix → must truncate to 29. With 9+ collisions → `-10` (3 chars), 28-char prefix. With 100+ → `-100`. Whether this is the spec or `KeyError` is left to the Developer.
  3. **(f) re-truncation:** does step (f) re-truncate after suffix? `History_` fits but the rule is extensible to other reserved names.
- **Why it matters:** Three Developers will produce three different `naming.py` modules. Then round-2 review catches it and the fix is a 30-line mid-Stage-2 rewrite.
- **Fix:** Lock the pipeline as an explicit numbered algorithm:
  > Apply (a)–(d) to produce `name_31`. If empty → `name_31 = "Table-N"`. If `name_31.lower() == "history"` → `name_31 = name_31 + "_"` then re-apply (d). **Then** apply workbook-wide case-insensitive dedup: if `name_31.lower()` already in `used_names_lower`, append `-2`, `-3`, … and re-truncate the **prefix** (keeping suffix intact) until `len(name) ≤ 31`. Cap retries at `-99` → on overflow raise `InvalidSheetName` (exit 2). Add to `used_names_lower` before returning.

---

## 🟢 MINOR

- **m1 — `31 UTF-8 code points` is technically the wrong unit.** Excel stores sheet names as UTF-16; the limit is 31 UTF-16 code units. For BMP characters there's no difference, but a 4-byte UTF-8 code point (e.g. emoji or `> U+FFFF`) is **one** UTF-8 code point but **two** UTF-16 code units. Truncating at 31 UTF-8 code points can yield a 32-UTF-16-unit name Excel rejects. **Fix:** D2 step (d) → "truncate to 31 characters (Excel hard limit; sheet names are stored as UTF-16 strings)".
- **m2 — `csv2xlsx.py:61` line reference is fragile.** Cite the function name (`_coerce_column`) instead of the line number.
- **m3 — Sub-feature count off by one.** §2 footer says "50 sub-features". Actual = 51 (R1.4 + R2.5 + R3.5 + R4.5 + R5.7 + R6.5 + R7.5 + R8.4 + R9.5 + R10.3 + R11.3).
- **m4 — UC-3 A2 ("`lxml.html` is lenient and auto-closes") is undertested.** Confirm test exists in `TestHtmlParser`.
- **m5 — `--sheet-prefix` × `--allow-empty` interaction undefined.** If both passed and 0 tables found, is placeholder sheet `Empty` (per T-no-tables-allow-empty) or `<prefix>-1`?
- **m6 — T-fenced-code-table / T-html-comment-table E2E tags should telegraph "only tables are inside the fence/comment".** Rename to `T-fenced-code-table-only` etc.
- **m7 — Effort/LOC internal-consistency check.** §6 enumerates 10 sub-tasks at ~136 LOC/each = ~1360 LOC total, matches §0 budget. OK.
- **m8 — O1, O2, O3 Open Questions converge.** Promote to D6 (heading walks across fenced-code boundaries), D7 (no Source-cell metadata in v1), D8 (env-var post-validate OFF default).
- **m9 — Public-API surface: asymmetric typing.** §8 declares `input_path: str | Path` but `output_path: Path`. Make both `str | Path`.
- **m10 — `cross-7 H1` label not glossed.** Add a one-line gloss on first mention.

---

## Cross-checks Summary

- ✅ Meta info present (Task ID `005`, slug `md-tables2xlsx`).
- ✅ RTM table format, 11 requirements, sub-features ≥ 3 each (avg 4.6).
- ✅ UCs carry Actors / Preconditions / Main / Alt / Postconditions / AC.
- ✅ Acceptance Criteria binary / verifiable.
- ✅ Cross-5 envelope shape correct (no `ok`/`message` regression).
- ✅ Cross-7 H1 same-path semantics match xlsx-2.
- ✅ stdin `-` reader semantics match xlsx-2.
- ✅ CLAUDE.md §2 4-skill replication boundary preserved.
- ✅ No new deps (lxml + python-dateutil already in requirements.txt).
- ✅ Public API single source of truth honoured.
- ❌ Honest-scope cross-references (M1).
- ❌ R9 regression-test coverage of §11 (M2).
- ❌ D2 sheet-naming pipeline ordering (M3).

---

## Open Questions Audit (O1–O3)

| Q | Verdict |
|---|---|
| O1 (heading walk across fenced-code-block boundaries) | Proposal converges; promote to D6 (m8). |
| O2 (Source-cell / sheet-level metadata) | Proposal converges (NO in v1); promote to D7. |
| O3 (`XLSX_MD_TABLES_POST_VALIDATE` env-var default) | Proposal converges (OFF); promote to D8. |

None block Architecture; all three cheap pre-locks reduce Architect's lift.

---

## Final Recommendation

**APPROVED WITH COMMENTS.** Proceed to Architecture phase after applying M1–M3 in-place. After fixes, route to Architecture (no second review round needed unless M3's pipeline rewrite introduces material new decisions).

```json
{"has_critical_issues": false}
```

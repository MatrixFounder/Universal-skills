# Architecture Review — Task 005 (xlsx-3 / md_tables2xlsx.py)

- **Date:** 2026-05-11
- **Reviewer:** architecture-reviewer agent
- **Target:** `docs/ARCHITECTURE.md` (xlsx-3, DRAFT 2026-05-11)
- **Status:** **APPROVED WITH COMMENTS** — Major issues correctable in-place; none block Planning when fixed. No Critical.

---

## General Assessment

Strong, well-internalised draft. xlsx-2 precedent (`architecture-003-json2xlsx.md`) is mirrored 1:1 on the load-bearing items: shim + package, top-of-`_run` `_AppError` catch, cross-5 envelope, cross-7 H1 same-path, post-validate via subprocess, style-constant copy-with-drift-detection. Cross-skill replication boundary §9 reproduces the 11-`diff -q` gating check verbatim. Data model §4 is conceptually correct: `Block` tagged union → `RawTable` → `ParsedTable` is a clean pipeline with frozen dataclasses and explicit relationships. Task-reviewer's M1/M2/M3 + m1/m3/m8/m9/m10 inlines are all reflected. The new `lxml.html` security surface is correctly principled (M1 tightens implementation detail).

Four Major items need correction before Planning:
- M1 — `lxml.html.HTMLParser` parser construction needs explicit locks (`huge_tree=False`, `no_network=True`, `create_parent=False`).
- M2 — `cli.py` LOC budget inconsistent (A1 lock at 320 vs §3.2/§3.3 at 280).
- M3 — `_dedup_step8` uses Python code-point slicing for prefix-truncation, not UTF-16-aware; reopens the m1 trap at step 8.
- M4 — `convert_md_tables_to_xlsx` signature diverges from sibling xlsx-2's `convert_json_to_xlsx(**kwargs) -> int`.

Minor items are cheap tightenings.

---

## 🔴 CRITICAL (BLOCKING)

*(none)*

---

## 🟡 MAJOR

### M1 — Lock the `lxml.html.HTMLParser` construction explicitly

**Where:** §7 XXE / billion-laughs rows; §10 A7; §3.2 `tables.py`.

**Finding:** The mitigation is technically correct in principle (HTML mode in libxml2 doesn't process internal-subset `<!ENTITY>` declarations, so billion-laughs via XML entities is closed; `no_network=True` blocks ext-resource fetch). Three precision gaps:
1. No minimum `lxml` version restated in §6 (requirements.txt:3 has `lxml>=5.0.0` — fine; mention here for traceability).
2. `huge_tree=False` is the right default but isn't locked. Lock it explicitly.
3. `fragment_fromstring(..., create_parent=False, parser=_HTML_PARSER)` is the right invocation — state it.

**Fix:** §3.2 `tables.py` description + §10 A7 lock:

```python
_HTML_PARSER = lxml.html.HTMLParser(
    no_network=True,   # defense-in-depth — block ext. resource fetch
    huge_tree=False,   # block libxml2 huge-tree expansion path
    recover=True,      # lenient parse (HTML mode already lenient; explicit)
)
fragment = lxml.html.fragment_fromstring(
    html_fragment, create_parent=False, parser=_HTML_PARSER,
)
```

Test `test_html_billion_laughs_neutered` should assert `parser.no_network is True` and `parser.options & HUGE_TREE == 0` in addition to wall-clock.

---

### M2 — `cli.py` LOC budget inconsistent (320 vs 280)

**Where:** §1 A2 row ("Guardrail: split if `cli.py` exceeds **320** LOC"); §3.2 `cli.py` entry ("**≤ 280**"); §3.3 mermaid (`≤280`).

**Finding:** A2 lock at top says 320; §3.2 + §3.3 say 280. Developer following A2 sets guardrail at 320 while inspection of §3.2 / §3.3 sets it at 280. Round-2 code review then catches the drift mid-Stage-2.

**Fix:** Pick one. Recommend **280** (matches §3.2 + §3.3; tighter than xlsx-2 reflects smaller pipeline). Update A2 row accordingly.

---

### M3 — `_dedup_step8` prefix re-truncation is NOT UTF-16-aware

**Where:** §3.2 `naming.py`; TASK §0/D2 step 8 (`base[:31 - len(S)] + S`).

**Finding:** Step 6 uses `_truncate_utf16` (m1 review-fix). Step 8 uses Python code-point slicing. Python `str` slices index by code points, NOT UTF-16 code units. When `base` ends with a supplementary-plane char (emoji), `base[:29]` may include a 4-byte UTF-8 char at code-point pos 28 (occupies UTF-16 pos 29-30). `base[:29] + "-2"` = 32 UTF-16 units. Excel rejects.

**Worked example:** heading = `"😀" * 16` → step 6 → `"😀" * 15` (30 UTF-16 units). Second collision: `base[:29] = "😀" * 16` (16 code points, all included). `candidate = "😀"*16 + "-2"` = 34 UTF-16 units. Excel limit violation.

**Fix:** Lock step 8 to use `_truncate_utf16`:

> `_dedup_step8`: for each suffix `S` in `"-2"`..`"-99"`: `candidate = _truncate_utf16(base, limit=31 - len(S)) + S`; if `candidate.lower() not in used_lower` return it; on exhaustion raise `InvalidSheetName(details={original, retry_cap: 99})`.

Add unit test `TestSheetNaming::test_dedup_emoji_prefix_utf16_safe` exercising the 16-emoji case.

---

### M4 — `convert_md_tables_to_xlsx` signature diverges from xlsx-2 sibling

**Where:** §5 internal interface lock; §3.2 `__init__.py`; TASK §8.

**Finding:** Architecture locks `convert_md_tables_to_xlsx(...) -> None` with typed kwargs. Shipped xlsx-2 `convert_json_to_xlsx(input_path: str, output_path: str, **kwargs: object) -> int` returns exit code, routes through argparse with VDD-multi M4 lock (`--flag=value` atomic-token form). Consequences:
1. Caller doing `if convert_json_to_xlsx(...) != 0: ...` won't generalise to `convert_md_tables_to_xlsx`.
2. The VDD-multi M4 protection from xlsx-2 is dropped.

**Fix:** Pick one:
- **Option A (preferred — minimum sibling-divergence):** Mirror xlsx-2 exactly: `def convert_md_tables_to_xlsx(input_path: str | Path, output_path: str | Path, **kwargs: object) -> int:` routed through `main(argv)` with `--flag=value` atomic-token construction.
- **Option B:** Keep typed-kwarg signature, but add A8 honest-scope lock explaining (a) why typed kwargs, (b) return semantics (raises `_AppError`; `main` maps to exit code), (c) why VDD-multi M4 protection not needed (no string-flag values with `--` parse-poisoning surface).

Pick one. Either is defensible.

---

## 🟢 MINOR

- **m1 — LOC budget total ≈ 1540 LOC vs TASK ~760 LOC estimate.** Budgets are ceilings, not targets. Add one-line note: "**Total budget headroom: ~1540 LOC; expected actual: ~700-1000 LOC.**"

- **m2 — F2 → F3/F4 dispatch implicit coupling.** Add `parse_table(block: Block) -> RawTable | None` dispatcher in `tables.py` that does the isinstance internally; `cli.py` calls just that.

- **m3 — `inline.py` borderline cohesion.** Note: if `inline.py` lands < 50 LOC, Developer MAY collapse into `tables.py` with F6/F7 import-path updates.

- **m4 — Parent-`.mkdir(parents=True, exist_ok=True)` divergence from xlsx-2.** xlsx-2 ARCH §7 explicitly says "parent directory must exist → IOError early-fail"; xlsx-3 §3.2 F8 silently creates parents (matches csv2xlsx:158). Lock as A8 honest-scope or align with xlsx-2.

- **m5 — `F10.read_stdin_utf8` vs `F1.read_input` stdin path overlap.** Lock: F1.read_input delegates to F10.read_stdin_utf8 when path == "-".

- **m6 — F2 `_locate_heading` HTML branch.** Lock: HTML `<hN>` inside a `<table>` block are NOT emitted as `Heading` Blocks.

- **m7 — §11.Q1 indented-code-block strip is a scope widening vs TASK D6.** Add unit-test inventory entry `T-indented-code-block-skip`.

- **m8 — Style-constant drift assertion import path clarity.** Lock the import as `from json2xlsx.writer import HEADER_FILL as _JSON_HEADER_FILL` with `sys.path` munge.

- **m9 — `MergeRange` 1-indexing convention.** Lock: `_expand_spans` converts internal 0-indexed grid coords to MergeRange 1-indexed at dataclass boundary; F8 passes them straight to `ws.merge_cells`.

- **m10 — `coerce_column` column-level vs cell-level boundary clarity.** Lock: `_has_leading_zero` is the gate; per-cell coercion runs only if gate is open.

- **m11 — TASK R10.c (zero-row table) not explicit in F8 contract.** Add: "If `tbl.rows` is empty, write header row only; freeze pane and auto-filter still apply."

- **m12 — `--sheet-prefix` × `resolve(heading)` interaction lock missing.** Add: "when `self.sheet_prefix is not None`, `resolve(heading)` ignores `heading` and returns `f"{sanitised_prefix}-{counter}"` where `counter` increments per-call."

---

## Cross-checks Summary

- ✅ Data Model (§4) defined before §3.2 components reference it.
- ✅ Entities are normalised frozen dataclasses; relationships explicit.
- ✅ F-region → module mapping is 1:1.
- ✅ Interfaces (§5) signatures locked.
- ✅ Security (§7) covers OWASP-relevant surface (correct in principle; M1 tightens).
- ✅ No `eval`/`shell=True`/network anywhere.
- ✅ Honest-scope realistic.
- ✅ Cross-skill replication boundary §9: 11 `diff -q` gating checks; xlsx-3 touches no shared module.
- ✅ TASK → ARCHITECTURE traceability: R1–R11 + D1–D8 all addressed.
- ❌ `cli.py` budget consistency (M2).
- ❌ `_dedup_step8` UTF-16-aware re-truncation (M3).
- ❌ `convert_md_tables_to_xlsx` signature divergence from xlsx-2 sibling (M4).
- ⚠️ `lxml.html` parser construction needs explicit `huge_tree=False` + lxml-version restatement (M1).

---

## Final Recommendation

**APPROVED WITH COMMENTS.** Architect applies M1–M4 in-place (inline edits, no structural rework), then routes to **Planning phase**. Re-review NOT required unless M3's prefix-truncation lock surfaces material new edge cases during sub-task 005-07 (`naming.py`). Minor items m1–m12 are tightenings; architect may inline or defer to Planner discretion.

```json
{"has_critical_issues": false}
```

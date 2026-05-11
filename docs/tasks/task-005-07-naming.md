# Task 005.07: `naming.py` — sheet-name resolution algorithm (F7)

## Use Case Connection
- UC-1 (HAPPY PATH) — sheet names derived from headings.
- R4 (all sub-features); ARCH m1 (UTF-16-aware truncate); ARCH M3 (UTF-16-aware dedup); ARCH m12 (`--sheet-prefix` short-circuit).

## Task Goal

Implement `class SheetNameResolver` with the locked 9-step algorithm
from TASK §0/D2. The two trickiest pieces are `_truncate_utf16`
(m1 review-fix) and `_dedup_step8` (M3 review-fix — UTF-16-aware
prefix re-truncation). After this task, E2E cases
`T-sheet-name-sanitisation` and `T-sheet-name-dedup` and the M3
regression test pass.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/md_tables2xlsx/naming.py`

**Class skeleton:**

```python
class SheetNameResolver:
    def __init__(self, sheet_prefix: str | None = None) -> None:
        self.sheet_prefix = sheet_prefix
        self._used_lower: set[str] = set()
        self._fallback_counter = 0  # for empty/no-heading → Table-N
        self._prefix_counter = 0    # for --sheet-prefix mode

    def resolve(self, heading: str | None) -> str:
        """Run the 9-step pipeline. Adds the winning name to
        used_lower BEFORE returning."""
        # If --sheet-prefix mode (ARCH m12):
        if self.sheet_prefix is not None:
            self._prefix_counter += 1
            sanitised_prefix = self._sanitise_to_31(self.sheet_prefix)
            return f"{sanitised_prefix}-{self._prefix_counter}"  # dedup is a no-op

        # Step 1: inline-strip heading (None → empty).
        raw = strip_inline_markdown(heading) if heading else ""
        # Steps 2-4:
        raw = self._sanitise_step2(raw)
        raw = self._sanitise_step3(raw)
        raw = self._sanitise_step4(raw)
        # Step 5: fallback Table-N if empty.
        if not raw:
            self._fallback_counter += 1
            raw = f"Table-{self._fallback_counter}"
        # Step 6: UTF-16 truncate to 31.
        base = _truncate_utf16(raw, limit=31)
        # Step 7: reserved-name guard.
        if base.lower() == "history":
            base = _truncate_utf16(base + "_", limit=31)
        # Step 8: workbook-wide dedup.
        return self._dedup_step8(base)
```

**Helpers:**

- `_sanitise_step2(name: str) -> str`: replace `[`, `]`, `:`, `*`, `?`, `/`, `\` with `_`.
- `_sanitise_step3(name: str) -> str`: collapse runs of whitespace via `re.sub(r"\s+", " ", name)`.
- `_sanitise_step4(name: str) -> str`: `name.strip().strip("'")`.
- `_sanitise_to_31(name: str) -> str`: convenience for `--sheet-prefix` mode — runs steps 2-6 in sequence.

**`_truncate_utf16(name: str, limit: int = 31) -> str` (m1 review-fix):**

```python
def _truncate_utf16(name: str, limit: int = 31) -> str:
    """Truncate to <= `limit` UTF-16 code units (Excel sheet-name rule).
    BMP chars are 1 UTF-16 unit; supplementary-plane chars (e.g. emoji) are 2.
    Sliced mid-surrogate-pair → drop the orphan via errors='ignore'.
    """
    encoded = name.encode("utf-16-le")
    truncated_bytes = encoded[: 2 * limit]
    return truncated_bytes.decode("utf-16-le", errors="ignore")
```

**`_dedup_step8(self, base: str) -> str` (M3 review-fix):**

```python
def _dedup_step8(self, base: str) -> str:
    if base.lower() not in self._used_lower:
        self._used_lower.add(base.lower())
        return base
    for n in range(2, 100):  # -2 .. -99 inclusive
        suffix = f"-{n}"
        candidate = _truncate_utf16(base, limit=31 - len(suffix)) + suffix
        if candidate.lower() not in self._used_lower:
            self._used_lower.add(candidate.lower())
            return candidate
    raise InvalidSheetName(
        f"Sheet name dedup exhausted retries: {base!r}",
        code=2, error_type="InvalidSheetName",
        details={"original": base, "retry_cap": 99,
                 "first_collisions": sorted(self._used_lower)[:10]},
    )
```

### Component Integration

Public surface: `SheetNameResolver` + private `_truncate_utf16`
(exported for unit-test access via the module surface). Consumed
by `cli.py` orchestrator (005.09): one `SheetNameResolver` instance
per CLI invocation; `resolve(heading)` called per table in
document order.

## Test Cases

### End-to-end Tests

- (Wired to workbook output in 005.08+; this task makes naming-side correct.)

### Unit Tests

**TestSheetNaming:**

1. **TC-UNIT-01 (test_simple_heading):** `resolve("Q1 Budget")` → `"Q1 Budget"`.
2. **TC-UNIT-02 (test_strip_forbidden_chars):** `resolve("Q1: [Budget]")` → `"Q1_ _Budget_"` (`:`/`[`/`]` → `_`).
3. **TC-UNIT-03 (test_inline_markdown_strip):** `resolve("**Bold Heading**")` → `"Bold Heading"`.
4. **TC-UNIT-04 (test_dedup_simple):** Two `resolve("Results")` calls in a row → `"Results"`, then `"Results-2"`.
5. **TC-UNIT-05 (test_dedup_case_insensitive):** `resolve("results")` after `resolve("Results")` → `"results-2"` (case-insensitive comparison).
6. **TC-UNIT-06 (test_reserved_history_suffixed):** `resolve("History")` → `"History_"` (case-insensitive `history` triggers).
7. **TC-UNIT-07 (test_truncate_utf16_31_chars):** `resolve("A" * 50)` → 31-char string. `len(result) == 31`.
8. **TC-UNIT-08 (test_truncate_utf16_emoji_supplementary_plane):** `resolve("😀" * 20)` → string whose `len(s.encode("utf-16-le")) // 2 <= 31`. Should yield `"😀" * 15` (= 30 UTF-16 units) because adding one more emoji crosses the 31 limit. (m1 review-fix lock.)
9. **TC-UNIT-09 (test_dedup_emoji_prefix_utf16_safe):** Two `resolve("😀" * 16)` calls. First yields `"😀" * 15` (30 UTF-16 units). Second yields `_truncate_utf16("😀"*15, limit=29) + "-2"`. Assert `len(second.encode("utf-16-le")) // 2 <= 31`. (M3 review-fix lock — the prime regression.)
10. **TC-UNIT-10 (test_fallback_table_n_no_heading):** `resolve(None)` → `"Table-1"`; next `resolve(None)` → `"Table-2"`.
11. **TC-UNIT-11 (test_fallback_table_n_empty_heading_after_sanitise):** `resolve("****")` (markdown emphasis strips to empty) → `"Table-1"`.
12. **TC-UNIT-12 (test_fallback_table_n_only_forbidden_chars):** `resolve("[][]")` (all forbidden chars stripped) → `"____"` (NOT empty after step 2 because chars replaced with `_`, not removed). Then dedup with subsequent calls.
13. **TC-UNIT-13 (test_dedup_overflow_raises_InvalidSheetName):** Set `_used_lower` to contain all `Foo` + `Foo-2..Foo-99`. `resolve("Foo")` → raises `InvalidSheetName` with `code=2` and `details["retry_cap"] == 99`.
14. **TC-UNIT-14 (test_sheet_prefix_mode_ignores_heading):** `SheetNameResolver(sheet_prefix="Report").resolve("Anything")` → `"Report-1"`; next call → `"Report-2"` (ARCH m12 lock).
15. **TC-UNIT-15 (test_dedup_used_lower_is_lowercase):** After `resolve("Results")`, `"results"` is in `_used_lower` (lowercase comparison).

### Regression Tests

- Existing tests pass.

## Acceptance Criteria

- [ ] All 15 unit tests pass.
- [ ] `_truncate_utf16` correctly handles supplementary-plane chars (m1 lock).
- [ ] `_dedup_step8` uses `_truncate_utf16` for prefix re-truncation (M3 lock — NOT `base[:N]` Python slicing).
- [ ] `--sheet-prefix` mode short-circuits the heading walk (ARCH m12 lock).
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] Eleven `diff -q` cross-skill replication checks silent.

## Notes

TC-UNIT-09 is the **M3 regression test** — the prime correctness
lock from the architecture review. If a future maintainer
"simplifies" `_dedup_step8` to `base[:31-len(suffix)] + suffix`
(Python slicing), this test catches it on next CI run.

The `_used_lower` set lives on the `SheetNameResolver` instance, NOT
as module-level state. One resolver per workbook conversion; the
orchestrator (005.09) creates a fresh instance per `_run` call.

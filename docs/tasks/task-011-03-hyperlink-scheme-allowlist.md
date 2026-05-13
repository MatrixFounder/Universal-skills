# Task 011.03 — [R3] `--hyperlink-scheme-allowlist` flag

## Use Case Connection
- UC-03: `--hyperlink-scheme-allowlist` blocks disallowed schemes (`xlsx-8a-03`)

## Task Goal
Add `--hyperlink-scheme-allowlist` CLI flag to both shims
(`xlsx2csv.py` / `xlsx2json.py`) defaulting to `http,https,mailto`,
with `warn-only` semantics on disallowed-scheme hyperlinks. Closes
Sec-MED-2 (ARCH §14.7.3): hyperlink targets are currently emitted
verbatim, enabling downstream XSS / RCE in LLM-renderers or
markdown viewers that auto-link `javascript:` / `data:` /
`file:` / custom protocol handlers.

The implementation drops disallowed entries from the
`hyperlinks_map` **upstream** (in `dispatch._extract_hyperlinks_for_region`),
so emit_json / emit_csv code paths are NOT touched — blocked
cells naturally traverse the "no hyperlink" branch (D7 / D-A11
locked decision: JSON output is bare scalar, NOT `{"value": V,
"href": null}` — preserves the existing two-shape contract from
[`references/json-shapes.md §11`](../../skills/xlsx/references/json-shapes.md)).

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2csv2json/cli.py`

**Function `build_parser` (argparse construction, ~line 134):**
- Add a new `parser.add_argument` for
  `--hyperlink-scheme-allowlist`:
  ```python
  parser.add_argument(
      "--hyperlink-scheme-allowlist",
      dest="hyperlink_scheme_allowlist",
      default="http,https,mailto",
      metavar="CSV",
      help=(
          "Comma-separated list of allowed URL schemes for "
          "hyperlink cells. Disallowed-scheme hyperlinks drop "
          "to the no-hyperlink emit branch (JSON: bare scalar "
          "value; CSV: plain text). One stderr warning per "
          "distinct blocked scheme (deduped). Default: "
          "'http,https,mailto' (covers typical office workbook "
          "schemes). Pass an empty string to block ALL schemes."
      ),
  )
  ```

**Helper function `_parse_scheme_allowlist`:**
- Add a new module-level helper:
  ```python
  def _parse_scheme_allowlist(csv: str) -> frozenset[str]:
      """Parse the `--hyperlink-scheme-allowlist` CSV value into
      a frozenset of lower-cased scheme strings.

      Empty entries are dropped; whitespace stripped.
      Empty input → `frozenset()` (blocks ALL schemes).
      """
      return frozenset(
          s.strip().lower() for s in csv.split(",") if s.strip()
      )
  ```

**Function `_dispatch_to_emit`:**
- Before the `with open_workbook(...)` block, parse the allowlist:
  ```python
  scheme_allowlist = _parse_scheme_allowlist(
      args.hyperlink_scheme_allowlist
  )
  ```
- Pass it to `dispatch.iter_table_payloads` via a new keyword
  argument (signature update below).

#### File: `skills/xlsx/scripts/xlsx2csv2json/dispatch.py`

**Function `iter_table_payloads` signature update:**
- Add new keyword parameter:
  ```python
  def iter_table_payloads(
      args: Any,
      reader: Any,
      *,
      format: str | None = None,
      hyperlink_scheme_allowlist: frozenset[str] | None = None,
  ) -> Iterator[...]:
  ```
- Default `None` means "no filter" (back-compat for callers
  pre-xlsx-8a; in practice the shim always passes a value).

**Function `_extract_hyperlinks_for_region`:**
- Add new keyword parameter `scheme_allowlist: frozenset[str] | None = None`.
- Add new local counter `blocked_by_scheme: dict[str, int] = {}`
  (populated as entries are dropped).
- Inside the `for col_offset, cell in enumerate(row_cells):` loop,
  after `target = getattr(hl, "target", None)`:
  ```python
  if target:
      target_str = str(target)
      if scheme_allowlist is not None:
          from urllib.parse import urlparse
          scheme = urlparse(target_str).scheme.lower()
          if scheme not in scheme_allowlist:
              blocked_by_scheme[scheme] = (
                  blocked_by_scheme.get(scheme, 0) + 1
              )
              continue  # drop from map
      result[(row_offset, col_offset)] = target_str
  ```
- After the loop, emit one stderr warning per distinct blocked
  scheme:
  ```python
  for scheme, count in blocked_by_scheme.items():
      warnings.warn(
          f"skipped {count} hyperlink(s) with disallowed "
          f"scheme {scheme!r}",
          UserWarning, stacklevel=2,
      )
  ```
  (Uses `warnings.warn`, NOT `print(... file=sys.stderr)`, so
  the shim's existing `warnings.catch_warnings(record=True)` block
  in `cli.py` captures and re-emits via HS-7 contract.)

**Function `iter_table_payloads` body:**
- When calling `_extract_hyperlinks_for_region`, pass
  `scheme_allowlist=hyperlink_scheme_allowlist`.

### Component Integration

- The blocked-scheme entries are dropped from the per-region map
  in `_extract_hyperlinks_for_region`. Downstream code in
  `emit_json._rows_to_string_style` / `_rows_to_array_style` /
  `emit_csv._write_region_csv` reads `hl_map.get((row, col))` —
  on `None` (entry absent), it emits the bare value (JSON) or
  plain text (CSV). No emit-branch change required (D-A11 locked
  decision).
- Stderr warnings are routed through `warnings.warn` →
  `cli.py:_emit_warnings_to_stderr` → process stderr per HS-7
  contract from xlsx-8.

## Test Cases

### End-to-end Tests

Hosted in `xlsx2csv2json/tests/test_hardening.py` (new file).

1. **TC-E2E-01:** `test_hyperlink_scheme_https_allowed`
   - Fixture: synthetic `.xlsx` with one hyperlink cell
     `https://example.com`.
   - Expected: JSON output emits `{"col": {"value": "text",
     "href": "https://example.com"}}`; no stderr warning.

2. **TC-E2E-02:** `test_hyperlink_scheme_javascript_blocked`
   - Fixture: synthetic `.xlsx` with one hyperlink cell
     `javascript:alert(1)`.
   - Expected: JSON output emits the bare cell value `{"col":
     "text"}` (NO `{value, href}` wrapper, NO `href: null` —
     per D7); CSV output emits the bare text (no
     `[text](javascript:...)` markdown link).
   - Stderr contains exactly one line: `"skipped 1 hyperlink(s)
     with disallowed scheme 'javascript'"`.

3. **TC-E2E-03:** `test_hyperlink_scheme_mixed_warning_dedup`
   - Fixture: 2 cells with `javascript:` + 1 cell with `mailto:`.
   - Expected: `mailto:` survives (allowed by default); both
     `javascript:` blocked; stderr contains exactly ONE warning
     line `"skipped 2 hyperlink(s) with disallowed scheme
     'javascript'"` (deduped on scheme).

4. **TC-E2E-04:** `test_hyperlink_scheme_mailto_allowed_by_default`
   - Fixture: `mailto:user@example.com` cell.
   - Expected: survives as `{"value": "Contact", "href":
     "mailto:user@example.com"}`; no stderr warning.

### Unit Tests

1. **TC-UNIT-01:** `test_parse_scheme_allowlist`
   - Input: `"http,https, mailto "`
   - Expected: `frozenset({"http", "https", "mailto"})` (whitespace
     stripped).

2. **TC-UNIT-02:** `test_parse_scheme_allowlist_empty`
   - Input: `""`
   - Expected: `frozenset()` (blocks all schemes).

3. **TC-UNIT-03:** `test_parse_scheme_allowlist_case_fold`
   - Input: `"HTTP,Https"`
   - Expected: `frozenset({"http", "https"})` (per D-A12 / Q-15-2:
     RFC 3986 §3.1 case-insensitive scheme matching).

### Regression Tests
- All existing `--include-hyperlinks` tests in
  `xlsx2csv2json/tests/test_dispatch.py` and `test_emit_json.py`
  continue to pass (default allowlist covers all existing fixture
  hyperlinks).
- 12-line cross-skill `diff -q` gate from ARCH §9.4 silent.

## Acceptance Criteria
- [ ] `python3 xlsx2csv.py --help | grep -F "hyperlink-scheme-allowlist"`
  shows the new flag.
- [ ] `python3 xlsx2json.py --help | grep -F "hyperlink-scheme-allowlist"`
  shows the new flag (both shims).
- [ ] All 4 E2E tests + 3 unit tests green.
- [ ] Existing `--include-hyperlinks` regression tests green.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] `python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/xlsx`
  exit 0.

## Stub-First Pass Breakdown

### Pass 1 — Stub + Red E2E
1. Add `--hyperlink-scheme-allowlist` argparse entry (accepted but
   unused at this stage).
2. Add `_parse_scheme_allowlist` helper.
3. Wire `_dispatch_to_emit` to parse the value and pass
   `hyperlink_scheme_allowlist=None` to dispatch (stub passes
   None, no filtering yet).
4. Write all 4 E2E + 3 unit tests — TC-E2E-02/03 FAIL Red
   (javascript: survives because no filter); TC-E2E-01/04 and unit
   tests pass already.

### Pass 2 — Logic + Green E2E
1. Update `_extract_hyperlinks_for_region` to accept the
   `scheme_allowlist` parameter and do the `urlparse` filter.
2. Wire `_dispatch_to_emit` to pass the parsed allowlist (replace
   the `None` stub).
3. Implement the dedup warning loop.
4. Re-run all tests — Green.

## Notes
- The allowlist is parsed once per CLI invocation; the result
  is a `frozenset` for O(1) lookup per hyperlink cell.
- `urlparse(href).scheme.lower()` is the canonical test (RFC 3986
  §3.1 — case-insensitive scheme matching). URLs without an
  explicit scheme (e.g. `example.com` instead of
  `https://example.com`) get `scheme=""` which never matches the
  allowlist — they are blocked by default (defensible: a workbook
  cell with a scheme-less hyperlink target is an authoring error,
  not a recognised hyperlink form).
- No `*` / `all` shorthand for the allowlist (per Q-3 / Q-15-3:
  explicit allow only).
- Effort: M (~3 hours). Diff size: ~50 LOC across 2 files + 1 new
  test file ~150 LOC.

# Task 005.04: `loaders.py` — input reader + pre-scan + block iteration (F1+F2)

## Use Case Connection
- UC-1 (HAPPY PATH) — first half: read file, scrub, iterate blocks.
- UC-2 (stdin) — `read_input("-", ...)` delegates to `read_stdin_utf8`.
- R9.g (blockquoted tables skipped); R9.i (`<style>`/`<script>` skip).

## Task Goal

Fill `loaders.py` with full F1 + F2 logic. After this task, the
following E2E cases turn GREEN at the "extraction succeeded"
boundary (the workbook isn't written yet — 005.06+ does parsing,
005.08 does writing; but the block-iteration phase is exercisable
via unit tests with a captured `iter_blocks(...)` output):

- `T-no-tables` — `iter_blocks` yields zero `PipeTable`/`HtmlTable`.
- `T-fenced-code-table-only` — `scrub_fenced_and_comments` strips the fence; `iter_blocks` yields zero tables.
- `T-html-comment-table-only` — same but for `<!-- -->` regions.
- `T-indented-code-block-skip` (NEW per ARCH Q1) — same but for 4-space-indented regions.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/md_tables2xlsx/loaders.py`

- Replace stub bodies with full implementations of:

**`read_input(path: str, encoding: str = "utf-8") -> tuple[str, str]`**
- If `path == "-"` → delegate to `cli_helpers.read_stdin_utf8()` (ARCH m5 single-source-of-truth lock); return `(text, "<stdin>")`.
- Else: `text = Path(path).read_text(encoding=encoding)` (default UTF-8 strict, raises `UnicodeDecodeError` on bad bytes — orchestrator maps to `InputEncodingError`).
- Return `(text, str(Path(path).resolve()))`.

**`scrub_fenced_and_comments(text: str) -> tuple[str, list[Region]]`**
(name is historical from F1 design; despite the name, the function strips **4** region types per the docstring — plan-review m4 note: do NOT rename in v1 to avoid touching tests/cli imports that already depend on the symbol)
- Walk line-by-line. Replace 4 region types with equal-length spaces (preserves line numbers):
  - Fenced code blocks (```` ``` ```` or `~~~`): match opening + closing fence; skip lines in between.
  - HTML comments (`<!-- ... -->`): handle multi-line comments by tracking open-comment state.
  - Indented code blocks (4-space indent OR tab indent at line start, AND preceded by blank line): conservative match per CommonMark spec.
  - `<style>` / `<script>` blocks (case-insensitive opening tag, find closing tag, replace contents with spaces — entire range NOT just inside the tag).
- Return `(scrubbed_text, regions_dropped)`; `Region = NamedTuple(start_line: int, end_line: int, kind: str)`.

**`iter_blocks(scrubbed: str) -> Iterator[Block]`**
- Walk the scrubbed text. Emit:
  - `Heading(level, text, line)` for each `^#{1,6} (.+)$` (markdown heading).
  - `Heading(level, text, line)` for each `<hN>(.+?)</hN>` (HTML headings; skip those inside `<table>...</table>`).
  - `PipeTable(raw_lines, line)` for each contiguous range of `|`-pipe lines where line N+1 matches `^\s*\|?\s*:?-+:?(\s*\|\s*:?-+:?)+\s*\|?\s*$` (GFM separator regex).
  - `HtmlTable(fragment, line)` for each `<table>...</table>` range.
- Skip blockquoted lines (any line starting with `>` ignoring leading whitespace) — emit nothing for them.

**Helpers:**

- `_detect_pipe_table_start(lines: list[str], idx: int) -> int | None` — returns end-index (exclusive) of the table block, or `None`.
- `_detect_html_table(text: str, idx: int) -> tuple[int, int] | None` — locate `<table>` (case-insensitive) and its matching `</table>`.
- `_locate_heading(line: str) -> tuple[int, str] | None` — match markdown OR HTML heading.
- `_strip_blockquote_lines(lines: list[str]) -> list[str]` — already handled inline in iter_blocks; this helper is optional.

**Data classes (move to top of file or `_types.py` — Developer's choice; keep in `loaders.py` for v1 to avoid an extra module):**

```python
@dataclass(frozen=True)
class Heading:
    level: int; text: str; line: int

@dataclass(frozen=True)
class PipeTable:
    raw_lines: list[str]; line: int

@dataclass(frozen=True)
class HtmlTable:
    fragment: str; line: int

Block = Heading | PipeTable | HtmlTable

@dataclass(frozen=True)
class Region:
    start_line: int; end_line: int; kind: str
```

### Component Integration

`loaders` consumes `cli_helpers.read_stdin_utf8` (delegation per
m5). `loaders` exports `Block`, `Heading`, `PipeTable`, `HtmlTable`,
`Region` — consumed by `tables.py` (005.06), `naming.py` (005.07),
and `cli.py` orchestrator (005.09).

## Test Cases

### End-to-end Tests

- No E2E cases turn green in this task (workbook isn't written yet). Cases T-no-tables, T-fenced-code-table-only, T-html-comment-table-only remain SKIP until 005.09 wires the orchestrator that catches the empty block stream and emits `NoTablesFound`.

### Unit Tests

1. **TC-UNIT-01 (TestPipeParser::test_iter_blocks_finds_pipe_table):** Fixture with 1 GFM table → `iter_blocks` yields 1 `PipeTable` block with the right `raw_lines` length.
2. **TC-UNIT-02 (TestPipeParser::test_iter_blocks_finds_3_tables_with_headings):** Fixture `examples/md_tables_simple.md` → yields 3 `Heading` + 3 `PipeTable` interleaved blocks in document order.
3. **TC-UNIT-03 (TestPipeParser::test_iter_blocks_skips_blockquoted_table):** `> | a | b |\n> |---|---|\n> | 1 | 2 |` → zero `PipeTable` yielded (R9.g lock).
4. **TC-UNIT-04 (TestHtmlParser::test_iter_blocks_finds_html_table):** Fixture with 1 `<table>` block → 1 `HtmlTable` yielded.
5. **TC-UNIT-05 (TestHtmlParser::test_iter_blocks_skips_html_heading_inside_table):** `<table><tr><td><h3>Inside</h3></td></tr></table>` followed by GFM table → 1 `HtmlTable` + 1 `PipeTable` BUT zero `Heading` from the `<h3>` inside the table (ARCH m6 lock).
6. **TC-UNIT-06 (TestPipeParser::test_scrub_fenced_strips_pipe_table_inside_fence):** ```` ```text\n| a | b |\n|---|---|\n| 1 | 2 |\n``` ```` → after scrub, the table lines are spaces; `iter_blocks` finds zero tables (R3.e).
7. **TC-UNIT-07 (TestPipeParser::test_scrub_html_comment_strips_table):** `<!--\n<table><tr><td>x</td></tr></table>\n-->` → after scrub, zero `<table>` regions.
8. **TC-UNIT-08 (TestPipeParser::test_scrub_indented_code_strips_table):** 4-space-indented pipe table after a blank line → after scrub, zero `PipeTable`. (ARCH Q1 default YES; T-indented-code-block-skip E2E inventoried.)
9. **TC-UNIT-09 (TestPipeParser::test_scrub_style_block_stripped):** `<style>body { color: red; }</style>` → contents replaced with spaces (R9.i lock).
10. **TC-UNIT-10 (TestPipeParser::test_scrub_script_block_stripped):** `<script>alert('xss')</script>` → contents replaced with spaces (R9.i lock).
11. **TC-UNIT-11 (TestPipeParser::test_scrub_preserves_line_numbers):** Source with a fenced block at lines 5-10 → scrubbed text has lines 5-10 as space-padded; `Heading.line` numbers for any heading AFTER the fence are unchanged.
12. **TC-UNIT-12 (TestExceptions::test_read_input_file_not_found):** `read_input("/nonexistent.md")` raises `FileNotFoundError` (NOT a typed `_AppError` — platform IO is envelope-only per PLAN platform-IO note).

### Regression Tests

- Existing tests pass. `lxml` is NOT imported yet (lands in 005.06).

## Acceptance Criteria

- [ ] All 12 unit tests pass.
- [ ] `iter_blocks` correctly skips fenced/comment/indented/style/script regions.
- [ ] `read_input("-")` delegates to `cli_helpers.read_stdin_utf8` (m5 lock).
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] Eleven `diff -q` cross-skill replication checks silent.

## Notes

The pre-scan is the **load-bearing primitive** for honest-scope items
§11.7 (blockquoted), §11.9 (`<style>`/`<script>`), and ARCH Q1
(indented code). Any later "but my fixture extracts a table from
inside a code block!" bug is a `loaders.py` issue — fix here, not in
`tables.py`. Tests TC-UNIT-08, -09, -10 are the regression locks for
R9.g/R9.i + ARCH Q1; do NOT delete them when refactoring.

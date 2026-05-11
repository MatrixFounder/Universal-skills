# Task 005.09: `cli.py` orchestrator + post-validate hook (F9 + F10 logic)

## Use Case Connection
- UC-1, UC-2, UC-3, UC-4 — full end-to-end pipeline.
- R8 (cross-cutting orchestration); R9 (CLI flag wiring); R10 (`--allow-empty` flag).
- ARCH M4 (`convert_md_tables_to_xlsx` public helper mirrors xlsx-2 `**kwargs -> int`).

## Task Goal

Wire all the F-region modules into a linear `_run` pipeline.
Implement the post-validate subprocess invocation (replacing the
005.03 stub). Lock the public helper `convert_md_tables_to_xlsx` per
ARCH M4 (argparse-routed `**kwargs -> int`). After this task, ALL
E2E cases turn GREEN.

## Changes Description

### Changes in Existing Files

#### File: `skills/xlsx/scripts/md_tables2xlsx/cli.py`

**`build_parser() -> argparse.ArgumentParser`:**

```python
parser = argparse.ArgumentParser(
    description="Convert markdown tables to a multi-sheet .xlsx workbook.",
)
parser.add_argument("input", help="Path to .md/.markdown file, or '-' for stdin")
parser.add_argument("output", type=Path, help="Destination .xlsx file")
parser.add_argument("--no-coerce", action="store_true",
                    help="Disable numeric / ISO-date coercion (force all cells to text)")
parser.add_argument("--no-freeze", action="store_true",
                    help="Disable freeze pane on header row")
parser.add_argument("--no-filter", action="store_true",
                    help="Disable auto-filter over data range")
parser.add_argument("--allow-empty", action="store_true",
                    help="Write an empty workbook when zero tables found (instead of exit 2)")
parser.add_argument("--sheet-prefix", default=None,
                    help="Override heading-based sheet naming with sequential STR-1, STR-2, ...")
parser.add_argument("--encoding", default="utf-8",
                    help="Input file encoding (default: utf-8; markdown is canonically UTF-8)")
add_json_errors_argument(parser)
return parser
```

**`main(argv: list[str] | None = None) -> int`:**

```python
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse usage error — already wrote stderr; return exit code.
        return exc.code or 2
    je = args.json_errors
    try:
        return _run(args)
    except _AppError as exc:
        return report_error(
            exc.message, code=exc.code, error_type=exc.error_type,
            details=exc.details, json_mode=je,
        )
    except FileNotFoundError as exc:
        return report_error(
            f"Input not found: {exc.filename}",
            code=1, error_type="FileNotFound",
            details={"path": exc.filename}, json_mode=je,
        )
    except (OSError, IOError) as exc:
        return report_error(
            f"I/O error: {exc}",
            code=1, error_type="IOError",
            details={"path": getattr(exc, "filename", None)}, json_mode=je,
        )
```

**`_run(args) -> int`:** linear pipeline driver:

```python
def _run(args) -> int:
    # 1. Same-path guard (cross-7 H1).
    assert_distinct_paths(args.input, args.output)

    # 2. Read input.
    text, source_label = read_input(args.input, encoding=args.encoding)
    if not text.strip():
        raise EmptyInput(f"Input is empty: {source_label}",
                         code=2, error_type="EmptyInput",
                         details={"source": source_label})

    # 3. Pre-scan strip fenced + comments + indented-code + style/script.
    scrubbed, dropped = scrub_fenced_and_comments(text)

    # 4. Iterate blocks; collect (heading, table) pairs in document order.
    pairs = []   # list[tuple[Heading | None, PipeTable | HtmlTable]]
    last_heading: Heading | None = None
    for block in iter_blocks(scrubbed):
        if isinstance(block, Heading):
            last_heading = block
        elif isinstance(block, (PipeTable, HtmlTable)):
            pairs.append((last_heading, block))

    # 5. Handle no-tables.
    if not pairs:
        if args.allow_empty:
            write_workbook([], args.output, WriterOptions(allow_empty=True))
        else:
            raise NoTablesFound(f"No tables found in {source_label}",
                                code=2, error_type="NoTablesFound",
                                details={"source": source_label})
        return _post_validate_or_zero(args.output)

    # 6. Parse each table (None on malformed-GFM → skip with stderr warning).
    resolver = SheetNameResolver(sheet_prefix=args.sheet_prefix)
    parsed_tables = []
    for heading, block in pairs:
        raw = parse_table(block)
        if raw is None:
            continue  # parse_pipe_table already emitted stderr warning.
        sheet_name = resolver.resolve(heading.text if heading else None)
        coerce_opts = CoerceOptions(coerce=not args.no_coerce)
        coerced = [
            coerce_column([row[c] or "" for row in raw.rows], coerce_opts)
            for c in range(len(raw.header))
        ]
        parsed_tables.append(ParsedTable(raw=raw, sheet_name=sheet_name,
                                         coerced_columns=coerced))

    if not parsed_tables:
        # Every table was malformed → treat as no-tables.
        if args.allow_empty:
            write_workbook([], args.output, WriterOptions(allow_empty=True))
        else:
            raise NoTablesFound(...)
        return _post_validate_or_zero(args.output)

    # 7. Write workbook.
    write_workbook(parsed_tables, args.output, WriterOptions(
        freeze=not args.no_freeze,
        auto_filter=not args.no_filter,
        sheet_prefix=args.sheet_prefix,
        allow_empty=args.allow_empty,
    ))

    # 8. Post-validate hook.
    return _post_validate_or_zero(args.output)
```

#### File: `skills/xlsx/scripts/md_tables2xlsx/__init__.py`

(plan-review m6 fix — the public helper lives in `__init__.py` per ARCH §3.2 + TASK §8, NOT in `cli.py`; previous draft placed this section under the `cli.py` header, which was misleading.)

**Public helper (ARCH M4 lock):**

```python
def convert_md_tables_to_xlsx(
    input_path: str | Path, output_path: str | Path,
    **kwargs: object,
) -> int:
    """Mirrors xlsx-2 convert_json_to_xlsx 1:1.

    Routes through main(argv) with --flag=value atomic-token form to
    prevent kwarg values starting with '--' from poisoning argparse
    (VDD-multi M4 protection inherited from xlsx-2)."""
    argv = [str(input_path), str(output_path)]
    flag_map = {
        "allow_empty": "--allow-empty",
        "coerce": "--no-coerce",       # negated: coerce=False → --no-coerce
        "freeze": "--no-freeze",
        "auto_filter": "--no-filter",
        "sheet_prefix": "--sheet-prefix",
        "encoding": "--encoding",
    }
    for k, v in kwargs.items():
        flag = flag_map.get(k)
        if flag is None:
            continue
        if k in ("coerce", "freeze", "auto_filter"):
            # Boolean negation: include --no-* only if value is False.
            if v is False:
                argv.append(flag)
        elif isinstance(v, bool):
            if v:
                argv.append(flag)
        else:
            argv.append(f"{flag}={v}")
    return main(argv)
```

#### File: `skills/xlsx/scripts/md_tables2xlsx/cli_helpers.py`

**Replace `run_post_validate` STUB (from 005.03) with full implementation:**

```python
def run_post_validate(output: Path) -> tuple[bool, str]:
    """Invoke office/validators/xlsx.py on the output. On failure,
    unlink output + raise PostValidateFailed (code 7)."""
    office_validate = (
        Path(__file__).resolve().parent.parent / "office" / "validate.py"
    )
    if not office_validate.is_file():
        # Defensive: should never happen because skill ships office/.
        return (False, f"office/validate.py not found at {office_validate}")
    try:
        result = subprocess.run(
            [sys.executable, str(office_validate), str(output)],
            shell=False, timeout=60, capture_output=True, text=True,
        )
    except subprocess.TimeoutExpired:
        try: output.unlink()
        except OSError: pass
        raise PostValidateFailed(
            f"Post-validate timeout (60s) on {output}",
            code=7, error_type="PostValidateFailed",
            details={"output": str(output), "reason": "timeout"},
        )
    if result.returncode != 0:
        snippet = (result.stderr or result.stdout or "")[:8192]
        try: output.unlink()
        except OSError: pass
        raise PostValidateFailed(
            f"Post-validate failed on {output}",
            code=7, error_type="PostValidateFailed",
            details={"output": str(output), "stderr": snippet,
                     "returncode": result.returncode},
        )
    return (True, result.stdout or "")
```

**Helper in `cli.py` (or `cli_helpers.py`):**

```python
def _post_validate_or_zero(output: Path) -> int:
    """If XLSX_MD_TABLES_POST_VALIDATE=1 → run validator (may raise).
    Otherwise return 0 immediately."""
    if post_validate_enabled():
        run_post_validate(output)  # may raise PostValidateFailed (code 7)
    return 0
```

### Component Integration

`cli.py` is the orchestrator — imports from all 9 other modules.
This is where the linear pipeline lives. The public helper
`convert_md_tables_to_xlsx` is exported via `__init__.py` and is
the SINGLE callable surface external code touches (besides the
shim CLI entry point).

## Test Cases

### End-to-end Tests (all the remaining T-* tags from 005.02 turn green here)

1. **TC-E2E-01 (T-happy-gfm):** `md_tables_simple.md` → workbook with 3 sheets named after the 3 headings. Each sheet has header + data rows + freeze + auto-filter.
2. **TC-E2E-02 (T-happy-html):** `md_tables_html.md` → workbook with GFM-sheet + HTML-sheet; HTML sheet has merged-cell ranges per the source `<table>` colspan/rowspan.
3. **TC-E2E-03 (T-stdin-dash):** `cat md_tables_simple.md | md_tables2xlsx.py - /tmp/out.xlsx` produces structurally-identical workbook to file mode (modulo timestamps).
4. **TC-E2E-04 (T-same-path):** Already green from 005.03. Re-verify.
5. **TC-E2E-05 (T-no-tables):** `md_tables_no_tables.md` → exit 2 envelope.
6. **TC-E2E-06 (T-no-tables-allow-empty):** Same input + `--allow-empty` → exit 0; workbook has single `Empty` sheet (ARCH A6).
7. **TC-E2E-07 (T-fenced-code-table-only):** `md_tables_fenced.md` → exit 2 `NoTablesFound`.
8. **TC-E2E-08 (T-html-comment-table-only):** Fixture with `<!--<table>...</table>-->` only → exit 2.
9. **TC-E2E-09 (T-coerce-leading-zero):** Workbook column with `"007"`/`"042"` is text (`data_type=='s'`).
10. **TC-E2E-10 (T-coerce-iso-date):** Workbook column with `2026-05-11` is Excel date cell (`number_format` includes `YYYY-MM-DD` pattern).
11. **TC-E2E-11 (T-sheet-name-sanitisation):** Heading `## Q1: [Budget]` → workbook has sheet named `Q1_ _Budget_`.
12. **TC-E2E-12 (T-sheet-name-dedup):** Two `## Results` headings → sheets `Results` + `Results-2`.
13. **TC-E2E-13 (T-envelope-cross5-shape):** Already green from 005.03. Re-verify.

### Unit Tests

1. **TC-UNIT-01 (TestCli::test_build_parser_8_flags):** `build_parser()` declares exactly 8 user-facing flags (positional `input`, `output`, plus 6 `--*` flags + 1 `--json-errors`) — pin the surface against accidental flag-addition.
2. **TC-UNIT-02 (TestCli::test_main_argparse_error_returns_envelope):** `main(["--invalid"])` with `--json-errors` in argv → exit 2 + cross-5 envelope on stderr.
3. **TC-UNIT-03 (TestCli::test_main_app_error_returns_envelope):** Monkeypatch `_run` to raise `NoTablesFound`; `main([...])` returns 2 with envelope.
4. **TC-UNIT-04 (TestCli::test_main_FileNotFoundError_returns_envelope):** `main(["/nonexistent.md", "/tmp/out.xlsx"])` → exit 1 + `FileNotFound` envelope.
5. **TC-UNIT-05 (TestCli::test_convert_md_tables_to_xlsx_routes_argv):** Monkeypatch `main` to capture argv; call `convert_md_tables_to_xlsx("a.md", "b.xlsx", allow_empty=True)` → captured argv == `["a.md", "b.xlsx", "--allow-empty"]`.
6. **TC-UNIT-06 (TestCli::test_convert_md_tables_to_xlsx_sheet_prefix_atomic_token):** `convert_md_tables_to_xlsx("a.md", "b.xlsx", sheet_prefix="--evil-flag-attempt")` → captured argv includes `--sheet-prefix=--evil-flag-attempt` as a SINGLE atomic token (M4 VDD-multi lock).
7. **TC-UNIT-07 (TestPostValidate::test_run_post_validate_passing):** Subprocess to `office/validate.py` returns 0 → `(True, ...)` tuple.
8. **TC-UNIT-08 (TestPostValidate::test_run_post_validate_failing_unlinks_output):** Monkeypatch subprocess to return non-zero → `PostValidateFailed` raised + output file unlinked.
9. **TC-UNIT-09 (TestPostValidate::test_run_post_validate_timeout_unlinks_output):** Monkeypatch subprocess to raise `TimeoutExpired` → `PostValidateFailed` with `details["reason"] == "timeout"` + output unlinked.
10. **TC-UNIT-10 (TestPostValidate::test_post_validate_not_invoked_when_env_off):** Env unset → `run_post_validate` NOT called; `_run` returns 0.
11. **TC-UNIT-11 (TestHonestScopeLocks::test_strict_dates_argparse_rejected):** `main(["--strict-dates", "a.md", "b.xlsx"])` → exit 2 + envelope `type: "UsageError"` (R9.f lock — `--strict-dates` is intentionally NOT a flag in v1).
12. **TC-UNIT-12 (TestHonestScopeLocks::test_RST_grid_input_no_tables_found):** Input markdown with `+---+---+` RST grid table only → `NoTablesFound` (R9.a lock).

### Regression Tests

- All existing skill tests pass.
- Eleven `diff -q` cross-skill replication checks silent.
- Drift-detection tests from 005.08 still pass.

## Acceptance Criteria

- [ ] All 13 E2E cases from 005.02 turn green.
- [ ] All 12 unit tests above pass.
- [ ] `cli.py` LOC ≤ 280 (M2 lock; HARD guardrail — if exceeded, the architect splits `_run` to `orchestrator.py`).
- [ ] `convert_md_tables_to_xlsx` returns `int` (exit code), accepts `**kwargs`, uses `--flag=value` atomic-token form (M4 lock).
- [ ] Post-validate hook fails closed: failure → output unlinked + `PostValidateFailed` envelope.
- [ ] `validate_skill.py skills/xlsx` exits 0.
- [ ] Eleven `diff -q` cross-skill replication checks silent.

## Notes

This is the LARGEST task in the chain. If `cli.py` lands above 280
LOC, STOP and split `_run` into `orchestrator.py` BEFORE shipping
(M2 lock guardrail). Splitting is cheap (just move `_run` + its
direct helpers); the M2 guardrail exists specifically to make this
decision automatic rather than discretionary.

The TC-UNIT-06 atomic-token test is the **VDD-multi M4 regression
lock** inherited from xlsx-2. It ensures a malicious or accidental
kwarg value like `sheet_prefix="--strict-dates"` cannot poison
argparse into firing an unrelated flag. Do NOT delete this test
during a "simplification" pass.

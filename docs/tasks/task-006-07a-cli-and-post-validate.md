# Task 006-07a: CLI full wiring (F7) + post-validate hook (F8) — MANDATORY MVP closure

## Use Case Connection
- **UC-1, UC-2, UC-3** — full end-to-end pipeline for zip-mode happy paths.
- **R4, R8 (a-f, i-k), R9** — action mutex, full CLI surface (sans `--unpacked-dir`), output integrity (post-validate).
- **G2 gate** — RTM coverage check: every R1–R12 sub-feature has ≥ 1 test (UC-4/R8.g lives in 006-07b).

> **Plan-review MIN-1 split:** Old combined `006-07` was the LARGEST
> task in the chain. Split into **006-07a (this task — mandatory
> MVP)** + **006-07b (conditional UC-4 library mode)**. Each is now
> ≈ 4–5 h of work.

## Task Goal

Wire all F-region modules from 006-03..06 into the final zip-mode
`_run` pipeline:
- F7 orchestrator: full `_run` flow per ARCH §F7 step list **minus
  the library-mode step deferred to 006-07b**: cross-7 → cross-3 +
  cross-4 → unpack → action dispatch → pack → post-validate →
  success summary.
- F8 post-validate hook: `_post_validate_enabled()` truthy check on
  `DOCX_REPLACE_POST_VALIDATE` env var; `_run_post_validate(output,
  scripts_dir)` invokes `subprocess.run([sys.executable, "-m",
  "office.validate", str(output)], ...)`; failure → `unlink(output)`
  + raise `PostValidateFailed` (exit 7).
- R8.k output-extension preservation: `args.output` extension is
  written verbatim (no auto-conversion between `.docx` and `.docm`).

At end of task: full exit-code matrix (0–7) is testable and GREEN
for every documented zip-mode path. UC-4 (library mode) remains a
stub in `_run` step 1 placeholder until 006-07b lands.

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/docx_replace.py`

**Replace `_run` body with the full zip-mode pipeline (per ARCH §F7,
minus library-mode step 1 — that placeholder still raises
`NotImplementedError("library mode — task-006-07b")`):**

```python
def _run(args: argparse.Namespace) -> int:
    scripts_dir = Path(__file__).resolve().parent

    # Step 1: Library-mode dispatch (placeholder until 006-07b lands).
    if args.unpacked_dir is not None:
        raise NotImplementedError(
            "library mode (UC-4) — task-006-07b"
        )

    # Steps 2-3: zip-mode pre-flight.
    _assert_distinct_paths(Path(args.input), Path(args.output))
    assert_not_encrypted(args.input)
    warn_if_macros_will_be_dropped(args.input)

    # Step 4: unpack.
    with _tempdir() as tmpdir:
        tree_root = unpack(args.input, tmpdir)
        # Step 5: dispatch + write.
        count, action_summary = _dispatch_action(
            args, tree_root, tmpdir, scripts_dir,
        )
        if count == 0:
            raise AnchorNotFound(
                f"Anchor not found: {args.anchor!r}",
                code=2, error_type="AnchorNotFound",
                details={"anchor": args.anchor},
            )
        # Step 7: pack (zip-mode only).
        pack(tree_root, args.output)
        # Step 8: opt-in post-validate.
        if _post_validate_enabled():
            _run_post_validate(Path(args.output), scripts_dir)
        # Step 9: success summary.
        print(
            f"{Path(args.output).name}: {action_summary}",
            file=sys.stderr,
        )
        return 0


def _dispatch_action(
    args: argparse.Namespace,
    tree_root: Path,
    tmpdir: Path,
    scripts_dir: Path,
) -> tuple[int, str]:
    """Dispatch to the chosen action; return (count, summary)."""
    if args.replace is not None:
        count = _do_replace(
            tree_root, args.anchor, args.replace, anchor_all=args.all,
        )
        return count, (
            f"replaced {count} anchor(s) "
            f"(anchor={args.anchor!r} -> {args.replace!r})"
        )
    if args.insert_after is not None:
        base_has_numbering = (tree_root / "word" / "numbering.xml").is_file()
        if args.insert_after == "-":
            data = _read_stdin_capped()
            if not data.strip():
                raise EmptyInsertSource(
                    "Empty stdin for --insert-after",
                    code=2, error_type="EmptyInsertSource",
                    details={"source": "<stdin>"},
                )
            md_path = tmpdir / "stdin.md"
            md_path.write_bytes(data)
        else:
            md_path = Path(args.insert_after)
            if not md_path.is_file():
                raise FileNotFoundError(args.insert_after)
            if md_path.stat().st_size == 0:
                raise EmptyInsertSource(
                    f"Empty insert source: {md_path}",
                    code=2, error_type="EmptyInsertSource",
                    details={"source": str(md_path)},
                )
        insert_docx = _materialise_md_source(md_path, scripts_dir, tmpdir)
        insert_tree_root = tmpdir / "insert_unpacked"
        insert_tree_root.mkdir()
        unpack(insert_docx, insert_tree_root)
        insert_paragraphs = _extract_insert_paragraphs(
            insert_tree_root, base_has_numbering=base_has_numbering,
        )
        count = _do_insert_after(
            tree_root, args.anchor, insert_paragraphs,
            anchor_all=args.all,
        )
        return count, (
            f"inserted {len(insert_paragraphs)} paragraph(s) after "
            f"anchor {args.anchor!r} ({count} match(es))"
        )
    if args.delete_paragraph:
        count = _do_delete_paragraph(
            tree_root, args.anchor, anchor_all=args.all,
        )
        return count, (
            f"deleted {count} paragraph(s) (anchor={args.anchor!r})"
        )
    raise _AppError(
        "No action specified",
        code=2, error_type="UsageError",
        details={"prog": "docx_replace.py"},
    )
```

**Add F8 post-validate functions:**

```python
def _post_validate_enabled() -> bool:
    """True if DOCX_REPLACE_POST_VALIDATE env-var is in the truthy
    allowlist {1, true, yes, on} (case-insensitive). R9.d lock."""
    raw = os.environ.get("DOCX_REPLACE_POST_VALIDATE", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _run_post_validate(output: Path, scripts_dir: Path) -> None:
    """subprocess.run([sys.executable, '-m', 'office.validate', OUTPUT]).
    Non-zero → unlink(output); raise PostValidateFailed (exit 7)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "office.validate", str(output)],
            shell=False, timeout=60, capture_output=True, text=True,
            cwd=str(scripts_dir),
        )
    except subprocess.TimeoutExpired:
        try: output.unlink(missing_ok=True)
        except OSError: pass
        raise PostValidateFailed(
            f"Post-validate timeout (60s) on {output}",
            code=7, error_type="PostValidateFailed",
            details={"output": str(output), "reason": "timeout"},
        )
    if result.returncode != 0:
        snippet = (result.stderr or result.stdout or "")[:8192]
        try: output.unlink(missing_ok=True)
        except OSError: pass
        raise PostValidateFailed(
            f"Post-validate failed on {output}",
            code=7, error_type="PostValidateFailed",
            details={"output": str(output), "stderr": snippet,
                     "returncode": result.returncode},
        )
```

**Update `build_parser` to keep INPUT/OUTPUT positional but allow
`nargs="?"` so that 006-07b can land `--unpacked-dir` without
breaking this task's argparse contract:**

```python
parser.add_argument(
    "input", nargs="?", default=None,
    help="Source .docx/.docm path (omit when --unpacked-dir is set in 006-07b)",
)
parser.add_argument(
    "output", nargs="?", default=None,
    help="Destination .docx path (omit when --unpacked-dir is set in 006-07b)",
)
```

Note: at 006-07a, missing INPUT/OUTPUT raises an immediate
`UsageError` in `_run` (before the library-mode placeholder), so the
`nargs="?"` is set only to keep the argparse surface forward-
compatible with 006-07b.

#### File: `skills/docx/scripts/tests/test_docx_replace.py`

- **Flip `self.fail()` → real assertions** for `TestCli` (≥ 3 cases):
  - `test_action_mutex` — argparse rejects two action flags.
  - `test_missing_action_returns_usage_error` — `docx_replace.py a.docx b.docx --anchor x` (no action) → exit 2 UsageError.
  - `test_output_extension_preserved` — `--anchor x --replace y` against `.docm` output preserves `.docm` extension (R8.k).
- **Flip `self.fail()` → real assertions** for `TestPostValidate` (≥ 4 cases):
  - `test_post_validate_enabled_truthy_values` — covers `1`, `true`, `yes`, `on` (case-insensitive); rejects `""`, `0`, `no`, `off`, `foo`.
  - `test_run_post_validate_failure_unlinks_output` — monkeypatch `subprocess.run` to rc=1 + stderr "INVALID"; expect `PostValidateFailed` raised + output unlinked.
  - `test_run_post_validate_timeout_unlinks_output` — monkeypatch to `TimeoutExpired`; expect `PostValidateFailed` with `details["reason"] == "timeout"`.
  - `test_post_validate_not_invoked_when_env_off` — env unset; full `_run`; assert subprocess.run is NOT called.
- **DO NOT** flip `TestLibraryMode` — those stubs stay `self.fail("...task-006-07b")` until 006-07b lands (or are skipped per 006-07b deferral note in 006-09).

#### File: `skills/docx/scripts/tests/test_e2e.sh`

- Flip the SKIP markers (gated by `DOCX6_STUBS_ENABLED`) to live
  assertions for:
  - `T-docx-replace-post-validate-fail` — `DOCX_REPLACE_POST_VALIDATE=1` + sabotage output → exit 7; output unlinked.
  - All previously-green cases re-verified end-to-end with the full pipeline.
- `T-docx-unpacked-dir` stays SKIP-gated until 006-07b.

### Component Integration

`_run` is now the single zip-mode orchestrator. The
`_dispatch_action` helper factors action-specific logic so 006-07b
can share it via the library-mode path. `build_parser` is the locked
CLI surface for the zip-mode portion of R8.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (T-docx-replace-post-validate-fail):** Sabotage output + env on → exit 7; output unlinked.
2. **TC-E2E-02 (R8.k extension preservation):** `--replace` with `.docm` output → `.docm` extension preserved.
3. **Re-verify all previously-green E2E cases** (full list from 006-04..06): every UC-1, UC-2, UC-3 case is GREEN end-to-end with pack+optional-post-validate.

### Unit Tests

1. **TC-UNIT-01..03 (TestCli):** Action mutex, missing-action UsageError, output extension preserved.
2. **TC-UNIT-04..07 (TestPostValidate):** Truthy parser; failure unlinks; timeout unlinks; env-unset → no subprocess.

### Regression Tests

- G4: docx-1 E2E block passes unchanged.
- All 12 `diff -q` cross-skill replication checks silent.
- 006-02 anchor unit tests still ≥ 20 GREEN.
- `TestLibraryMode` stubs continue to fail with the `006-07b` message (Stub-First Red state preserved for the deferred sub-task).

## Acceptance Criteria

- [ ] `_run` implements the zip-mode pipeline (no library-mode dispatch in this task).
- [ ] `DOCX_REPLACE_POST_VALIDATE` truthy allowlist `{1, true, yes, on}`.
- [ ] Post-validate failure unlinks output + raises `PostValidateFailed` exit 7.
- [ ] Output extension preserved verbatim (R8.k).
- [ ] **`wc -l skills/docx/scripts/docx_replace.py` ≤ 560** (soft ceiling; leaves ≥ 40 LOC for 006-07b UC-4).
- [ ] If the soft ceiling is breached (561–600 LOC), 006-07b is **deferred** to backlog row `docx-6.4` per MIN-1 split rule.
- [ ] If 006-07a alone exceeds **600 LOC** (HARD ceiling), STOP and extract `_actions.py` sibling BEFORE merging.
- [ ] All Cross-cutting + UC-1/2/3 E2E cases pass; `T-docx-unpacked-dir` SKIP (006-07b stub).
- [ ] All Unit tests (≥ 30 in `test_docx_replace.py`, minus the 2 in `TestLibraryMode` deferred to 006-07b) pass.
- [ ] G4 regression: docx-1 E2E block passes unchanged.
- [ ] `validate_skill.py skills/docx` exits 0.
- [ ] All 12 `diff -q` cross-skill replication checks silent.

## Notes

For the post-validate test, the sabotage fixture can be constructed
by running the full pipeline, then deliberately corrupting the output
(`echo "garbage" >> /tmp/out.docx`) before setting the env var.
Alternatively, monkeypatch `office.validate` to always exit non-zero
(simpler in unit tests; less honest in E2E).

The R8.k extension-preservation test is significant: `.docm` input
with `--replace` MUST produce `.docm` output. The macro-warning
(cross-4) is already issued at pre-flight; no extension conversion
happens anywhere in the pipeline.

The TOCTOU symlink race lock for ARCH A4 (MIN-2) lives in 006-08, not
here — that test is a **regression lock** rather than a feature
implementation.

RTM coverage: **R4.a, R4.b, R4.c, R8.a, R8.b, R8.c, R8.d, R8.e, R8.f,
R8.i, R8.j, R8.k, R9.a, R9.b, R9.c, R9.d** (R8.g `--unpacked-dir`
covered in 006-07b).

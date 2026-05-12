# Task 006-07b: `--unpacked-dir` library mode (UC-4) — CONDITIONAL MVP=No

## Use Case Connection
- **UC-4** — Library mode (operate on already-unpacked OOXML tree).
- **R8.g** — `--unpacked-dir TREE` library mode (MVP=No per TASK §5).
- **R4.b** — `UsageError` when `--unpacked-dir` is combined with positional INPUT/OUTPUT.

> **Plan-review MIN-1 split:** This task is the **conditional**
> deliverable of the 006-07 split. Land it only if cumulative
> `docx_replace.py` LOC after 006-07a is **≤ 560** (i.e. ≥ 40 LOC
> headroom). Otherwise **defer to follow-up backlog row `docx-6.4`**
> and document the deferral in 006-09's backlog update.

## Task Goal

Implement library mode in `docx_replace.py`:
- Replace the `NotImplementedError("library mode — task-006-07b")`
  placeholder in `_run` with the library-mode dispatch from ARCH §F7
  step 1 (MAJ-1 fix): library mode dispatched **FIRST**, before
  cross-7 / cross-3 / cross-4 / unpack.
- Validate INPUT/OUTPUT positionals are absent (R4.b → `UsageError`).
- Validate `tree_root / "word" / "document.xml"` exists (else
  `NotADocxTree` exit 1).
- Reuse `_dispatch_action` from 006-07a (no duplication).
- **Skip** `_assert_distinct_paths`, `assert_not_encrypted`,
  `warn_if_macros_will_be_dropped`, `office.pack`, and post-validate
  (caller owns the tree and handles persistence).
- Success summary uses `<unpacked>` as the filename placeholder.

## Pre-flight check (BEFORE starting work)

```bash
wc -l skills/docx/scripts/docx_replace.py
```

- If output > 560 → **STOP**. Add row `docx-6.4 — library mode for
  docx_replace.py` to `docs/office-skills-backlog.md` in 006-09 and
  skip this task entirely.
- If output ≤ 560 → proceed.

## Changes Description

### Changes in Existing Files

#### File: `skills/docx/scripts/docx_replace.py`

**Replace the `NotImplementedError("library mode — task-006-07b")`
placeholder in `_run` with the library-mode dispatch:**

```python
def _run(args: argparse.Namespace) -> int:
    scripts_dir = Path(__file__).resolve().parent

    # Step 1: Library-mode dispatch (FIRST per ARCH §F7 MAJ-1 fix).
    if args.unpacked_dir is not None:
        if args.input is not None or args.output is not None:
            raise _AppError(
                "Cannot combine --unpacked-dir with INPUT/OUTPUT positionals",
                code=2, error_type="UsageError",
                details={"prog": "docx_replace.py"},
            )
        tree_root = Path(args.unpacked_dir).resolve(strict=False)
        if not (tree_root / "word" / "document.xml").is_file():
            raise NotADocxTree(
                f"Not a docx tree: {tree_root}",
                code=1, error_type="NotADocxTree",
                details={"dir": str(tree_root)},
            )
        return _run_library_mode(args, tree_root, scripts_dir)

    # Step 2 onward: zip-mode pipeline from 006-07a unchanged.
    _assert_distinct_paths(Path(args.input), Path(args.output))
    # ... rest of zip-mode pipeline from 006-07a ...
```

**Add `_run_library_mode` helper:**

```python
def _run_library_mode(
    args: argparse.Namespace, tree_root: Path, scripts_dir: Path,
) -> int:
    """Library-mode entry: caller owns the unpacked tree.

    Cross-cutting checks (cross-7/3/4) are SKIPPED; no pack; no
    post-validate. The tree is mutated in place.
    """
    with _tempdir() as tmpdir:
        count, action_summary = _dispatch_action(
            args, tree_root, tmpdir, scripts_dir,
        )
        if count == 0:
            raise AnchorNotFound(
                f"Anchor not found: {args.anchor!r}",
                code=2, error_type="AnchorNotFound",
                details={"anchor": args.anchor},
            )
        print(
            f"<unpacked>: {action_summary}",
            file=sys.stderr,
        )
        return 0
```

#### File: `skills/docx/scripts/tests/test_docx_replace.py`

- **Flip `self.fail()` → real assertions** for `TestLibraryMode` (≥ 2 cases):
  - `test_library_mode_dispatch_first` — invoke with `--unpacked-dir <tmpdir>` (containing a valid unpacked tree); cross-7/cross-3/cross-4 checks skipped; action runs; no pack invoked (verified by patching `office.pack` to a sentinel and asserting it's not called).
  - `test_library_mode_missing_document_xml` — invoke with `--unpacked-dir <empty>` → exit 1 `NotADocxTree` with `details["dir"]`.
  - `test_library_mode_forbids_positional` — invoke with `--unpacked-dir /tmp/x in.docx out.docx` → exit 2 `UsageError`.

#### File: `skills/docx/scripts/tests/test_e2e.sh`

- Flip the `T-docx-unpacked-dir` SKIP marker to a live E2E case:
  1. Pre-unpack `docx_replace_body.docx` via `office.unpack` to
     `$TMP/unpacked/`.
  2. Invoke `python3 docx_replace.py --unpacked-dir $TMP/unpacked
     --anchor "May 2024" --delete-paragraph`.
  3. Re-pack via `office.pack $TMP/unpacked $TMP/out.docx`.
  4. Assert paragraph count decreased by 1 (UC-4 acceptance per
     TASK §2.4.5).

### Component Integration

`_run_library_mode` calls `_dispatch_action` from 006-07a — no logic
duplication. The library-mode caller is responsible for pack +
persistence after the call returns.

## Test Cases

### End-to-end Tests

1. **TC-E2E-01 (T-docx-unpacked-dir):** Library-mode end-to-end with `--delete-paragraph` on a pre-unpacked tree.

### Unit Tests

1. **TC-UNIT-01..03 (TestLibraryMode):** All 3 cases above pass.

### Regression Tests

- All zip-mode tests from 006-07a still GREEN.
- G4: docx-1 E2E block passes unchanged.
- All 12 `diff -q` cross-skill replication checks silent.

## Acceptance Criteria

- [ ] **Pre-flight LOC check passed** (006-07a ended ≤ 560 LOC).
- [ ] Library-mode dispatch happens **FIRST** in `_run` (before cross-7).
- [ ] Library mode SKIPS cross-7, cross-3, cross-4, pack, post-validate.
- [ ] `--unpacked-dir` combined with INPUT/OUTPUT → exit 2 `UsageError` (R4.b).
- [ ] Missing `word/document.xml` → exit 1 `NotADocxTree`.
- [ ] **`wc -l skills/docx/scripts/docx_replace.py` ≤ 600** (HARD ceiling).
- [ ] If 600 would be exceeded, extract `_actions.py` sibling BEFORE merging.
- [ ] All TestLibraryMode (≥ 3 cases) + T-docx-unpacked-dir E2E pass.
- [ ] G4 regression: docx-1 E2E block passes unchanged.
- [ ] `validate_skill.py skills/docx` exits 0.
- [ ] All 12 `diff -q` cross-skill replication checks silent.

## Deferral Path

If 006-07a leaves < 40 LOC headroom (i.e. ended > 560 LOC):

1. Skip this entire task.
2. In 006-09, add a NEW row to `docs/office-skills-backlog.md`:
   ```
   docx-6.4 | Library mode for docx_replace.py (UC-4) | PENDING |
   Deferred from docx-6 chain (006-07a LOC budget breached). |
   Effort: S (~ 40 LOC + 3 unit tests).
   ```
3. Mark `TestLibraryMode` and `T-docx-unpacked-dir` as
   `unittest.skip("Deferred to docx-6.4 backlog row")` and
   `echo SKIP T-docx-unpacked-dir (deferred to docx-6.4)`.
4. Document the deferral rationale in 006-09's backlog status line.

## Notes

The `_dispatch_action` helper (introduced in 006-07a) is the **single
source of truth** for action dispatch. Both `_run` (zip-mode) and
`_run_library_mode` call it. Do not duplicate the action-selection
logic.

The "skip cross-cutting checks in library mode" decision is locked by
TASK §2.4.3 ("same-path / encryption checks SKIPPED — the caller owns
the tree") and reaffirmed by ARCH §F7 MAJ-1 fix.

For the `T-docx-unpacked-dir` E2E test, the caller's pack step (step 3
in the test sequence) uses `office.pack` as a subprocess wrapper — but
in practice we'll likely use `python3 -c "from office import pack;
pack('$TMP/unpacked', '$TMP/out.docx')"` inline.

RTM coverage: **R8.g** (`--unpacked-dir` library mode, MVP=No),
**R4.b** (UsageError on combined positional).

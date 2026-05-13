# Task 011.07 — [R9] `json.dump(fp)` for file output (drop one full-payload copy)

## Use Case Connection
- UC-08: JSON multi-sheet / multi-region falls back to R9 path (`xlsx-8a-07`)

## Task Goal
Switch the `emit_json.emit_json` file-output branch from
`json.dumps(shape, ...) + output.write_text(text + "\n")` to
`with output.open("w") as fp: json.dump(shape, fp, ...)`. This
drops one of the three full-payload memory copies on the JSON
path (the serialised-string buffer, ~300-500 MB on a 3M-cell
payload).

**Stdout path unchanged** — `sys.stdout.write(text + "\n")` keeps
the documented newline contract; the pipe consumer buffers the
output downstream regardless, so the memory benefit is
downstream-dependent (asymmetric on purpose per D-A17).

**Dependency**: 011-06 (fixture-timing prerequisite — the 1M-cell
R9 test fixture cannot complete under the v1 cap during setup).

This partial closure of PERF-HIGH-2 applies to **R11.2-4 multi-sheet
and multi-region shapes** (where `shape` is a dict that cannot be
RFC-8259-streamed). The fully-streamed R11.1 single-region path is
handled by 011-08.

## Changes Description

### New Files
None.

### Changes in Existing Files

#### File: `skills/xlsx/scripts/xlsx2csv2json/emit_json.py`

**Function `emit_json` (lines ~64-99) — file output branch:**

Before:
```python
text = json.dumps(
    shape,
    ensure_ascii=False, indent=2, sort_keys=False,
    default=_json_default,
)
if output is None:
    sys.stdout.write(text + "\n")
else:
    output.write_text(text + "\n", encoding="utf-8")
return 0
```

After:
```python
if output is None:
    # Stdout path: unchanged. Build the string then write +
    # newline. (See D-A17 — asymmetric on purpose.)
    text = json.dumps(
        shape,
        ensure_ascii=False, indent=2, sort_keys=False,
        default=_json_default,
    )
    sys.stdout.write(text + "\n")
else:
    # File path: stream serialise direct to fp, drop the
    # intermediate string buffer. ~300-500 MB savings on
    # 3M-cell payloads.
    with output.open("w", encoding="utf-8") as fp:
        json.dump(
            shape, fp,
            ensure_ascii=False, indent=2, sort_keys=False,
            default=_json_default,
        )
        fp.write("\n")
return 0
```

**Note on byte-identity**: `json.dump(shape, fp, indent=2, ...)`
produces byte-identical output to
`json.dumps(shape, indent=2, ...) + write` — the trailing newline
is appended via `fp.write("\n")` to preserve the existing newline
contract from xlsx-8.

### Component Integration
None changed externally. The function signature is unchanged;
caller `cli._dispatch_to_emit` continues to call `emit_json(...)`
with the same arguments.

## Test Cases

### End-to-end Tests

Hosted in `xlsx2csv2json/tests/test_emit_json.py` (extend
existing).

1. **TC-E2E-01:** `test_R9_file_byte_identical_to_v1`
   - Approach: for every fixture in
     `xlsx2csv2json/tests/fixtures/` that produces R11.2-4 shapes
     (multi-sheet AND/OR multi-region per sheet — grep the
     existing fixture list), invoke both the v1 path (held inline
     in the test as `_v1_emit_json_via_dumps`) and the R9
     `json.dump(fp)` path, write to two temp files, `diff -q`
     them.
   - Expected: byte-identical on every fixture.

2. **TC-E2E-02:** `test_R9_file_output_no_string_buffer`
   - Fixture: 1M-cell multi-sheet synthetic (e.g. 4 sheets × 250K
     rows × 1 col).
   - Invocation: shim invocation with `--output out.json` under
     `tracemalloc.start()` instrumentation.
   - Expected: peak RSS during the `emit_json` file-write block is
     strictly less than the v1 baseline (measured in the same test
     by also running the v1 path) by at least 50 MB (sanity-check
     on the savings; the actual savings for a 1M-cell payload are
     ~50-100 MB string buffer).
   - Honest scope: this is a **relative** budget assertion (R9 <
     v1), not an absolute (R9 < N MB). The actual peak depends on
     the test runner and Python build.

### Unit Tests
Not applicable — the change is a single-branch refactor; E2E
byte-identity is the right test scope.

### Regression Tests
- All existing tests in `xlsx2csv2json/tests/test_emit_json.py`
  green (R11.1 single-region fixtures continue through the
  unchanged dispatch path until 011-08 lands; R11.2-4 fixtures
  go through the new R9 path with byte-identical output).
- Existing `test_e2e.py::test_roundtrip_xlsx_2` green.
- 12-line cross-skill `diff -q` gate from ARCH §9.4 silent.

## Acceptance Criteria
- [ ] `grep -n "json.dump(" skills/xlsx/scripts/xlsx2csv2json/emit_json.py`
  returns ≥ 1 hit (new file-output branch).
- [ ] `grep -n "json.dumps(" skills/xlsx/scripts/xlsx2csv2json/emit_json.py`
  returns ≥ 1 hit (stdout branch still uses dumps; do NOT delete).
- [ ] TC-E2E-01 (byte-identical) green on every R11.2-4 fixture.
- [ ] TC-E2E-02 (RSS reduction) green — R9 peak < v1 peak by ≥ 50 MB.
- [ ] All existing `test_emit_json.py` tests green.
- [ ] `ruff check skills/xlsx/scripts/` green.
- [ ] `validate_skill.py skills/xlsx` exit 0.

## Stub-First Pass Breakdown

### Pass 1 — Stub + Red E2E
1. Make a **structural** stub change:
   ```python
   if output is None:
       text = json.dumps(shape, ...)
       sys.stdout.write(text + "\n")
   else:
       text = json.dumps(shape, ...)  # STUB — still uses dumps
       output.write_text(text + "\n", encoding="utf-8")
   ```
   Splits the path into two branches but keeps v1 semantics
   inside the file branch.
2. Write TC-E2E-01 (byte-identical) — passes (no change yet).
3. Write TC-E2E-02 (RSS reduction) — FAILS Red (no savings).

### Pass 2 — Logic + Green E2E
1. Replace the file-branch stub with the `json.dump(fp)` form.
2. Re-run TC-E2E-02 — Green (savings present).
3. Re-run TC-E2E-01 — Green (byte-identical preserved).

## Notes
- The asymmetry (stdout uses `dumps` + write; file uses `dump`)
  is locked in D-A17. Stdout consumers (pipes, terminals) buffer
  the output anyway, so the savings are downstream-dependent;
  keeping the existing newline contract is more important than
  saving a string buffer.
- `json.dump(fp, indent=2)` writes the same bytes as
  `json.dumps(indent=2) + write` — verified by tests/Python docs.
  No trailing-newline drift; the explicit `fp.write("\n")` after
  `json.dump` preserves the v1 trailing-newline contract.
- Effort: S (≤ 2 hours). Diff size: ~10 LOC change + ~80 LOC
  test additions.

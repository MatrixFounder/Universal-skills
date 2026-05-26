# Task 015.08 — Extract `commands/append_log.py` + `commands/log_event.py`

## Use Case Connection
- UC-3 (log mutations remain idempotent and grep-friendly).

## Task Goal

Move the two log-writing subcommands.

## Changes Description

### New Files

- `wiki_ingest/commands/append_log.py` (≤150 LoC).
- `wiki_ingest/commands/log_event.py` (≤100 LoC).
- `tests/commands/test_append_log.py`.
- `tests/commands/test_log_event.py`.

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

**Symbols to move to `commands/append_log.py`:**

- `cmd_append_log` → `execute`.

**Symbols to move to `commands/log_event.py`:**

- `cmd_log_event` → `execute`.

`_LOG_FORBIDDEN_IN_DETAIL` was moved to `_safety.py` in 015.01 (it's
a security deny-list regex — F1-shaped — and is consumed by both log
commands). Both modules import it from `_safety`. No duplication.

Argparse blocks for both subcommands move into their respective
`register(sub)` functions.

### Component Integration

Both modules import from `_safety` (`_safe_name`, `_safe_inline`,
`die`, `write_text`, `_safe_for_json`, `_collect_names`,
`_LOG_FORBIDDEN_IN_DETAIL`) and `_vault` (`ensure_schema`, `LOG_FILE`,
`load_asset`, `read_text`).

## Test Cases

### Unit Tests

1. **TC-UNIT-08-1**: `test_append_log_idempotency_no_redos` — write a log
   with 50 000 lines and a heading that has NO matching summary-line;
   call `execute` with that heading. Assert the function returns
   without backtracking (use `time.perf_counter`; budget ≤ 50 ms).
   Locks L-H4.

2. **TC-UNIT-08-2**: `test_log_event_rejects_square_brackets_in_event` —
   call with `--event "ok]name"`; assert `SystemExit`. Locks S-L1.

3. **TC-UNIT-08-3**: `test_log_event_detail_kv_round_trip` — call with
   `--detail key=value --detail foo=bar`; assert the rendered heading
   has both lines in order.

### End-to-end Tests

1. **TC-E2E-08-1**: `test_append_log.test_append_then_repeat_dedupes` —
   call twice; assert second call returns `appended: false`.

### Regression Tests

- `tests.test_r11_byte_identity` still green (note: `append-log` /
  `log-event` are NOT in the R11 fixture set because they write
  timestamps).
- `test_architecture` still green.

## Acceptance Criteria

- [ ] Both command files within LoC ceilings; tests pass.
- [ ] `_LOG_FORBIDDEN_IN_DETAIL` imported from `_safety` (centralised in
      015.01), NOT duplicated.
- [ ] R11 gate green; `validate_skill.py` exits 0.

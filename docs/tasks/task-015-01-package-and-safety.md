# Task 015.01 — Package skeleton + extract `_safety.py`

## Use Case Connection
- UC-3 (E2E smoke retains parity).

## Task Goal

Create the `wiki_ingest/` Python package alongside `wiki_ops.py` and
relocate every safety / atomic-I/O / JSON-sanitisation primitive into
`wiki_ingest/_safety.py`. `wiki_ops.py` continues to work via top-level
re-export imports — no command logic is moved yet.

## Changes Description

### New Files

- `skills/wiki-ingest/scripts/wiki_ingest/__init__.py` — empty (≤30 LoC).
- `skills/wiki-ingest/scripts/wiki_ingest/_safety.py` (≤300 LoC) — see
  Symbols-to-move below.
- `skills/wiki-ingest/scripts/tests/test__safety.py` — ≥3 unit tests
  (see Test Cases).
- `skills/wiki-ingest/scripts/wiki_ingest/.AGENTS.md` — one-paragraph
  module-charter note: "Internal package for wiki-ingest. Layered model:
  F1 (_safety) ← F2 (_markdown, _frontmatter) ← F3 (_vault, _classify,
  commands/). No command imports another command. Tests live in
  `../tests/`."

### Changes in Existing Files

#### File: `skills/wiki-ingest/scripts/wiki_ops.py`

**Symbols to move to `wiki_ingest/_safety.py`:**

| Symbol                         | Lines (pre-refactor) |
|--------------------------------|----------------------|
| `MAX_PAGE_BYTES`               | 47                   |
| `MAX_SUMMARY_BYTES`            | 48                   |
| `MAX_VALUE_BYTES`              | 49                   |
| `die`                          | 65                   |
| `slugify`                      | 70                   |
| `_UNSAFE_NAME_RE`              | 87                   |
| `_safe_name`                   | 90                   |
| `_safe_inline`                 | 117                  |
| `_check_case_collision`        | 137                  |
| `_is_relative_to`              | 197                  |
| `_safe_open_for_read`          | 211                  |
| `read_text`                    | 233                  |
| `_atomic_write_text`           | 269                  |
| `write_text`                   | 299                  |
| `_CTRL_CHARS_RE`               | 318                  |
| `_safe_for_json`               | 321                  |
| `_skip_symlink`                | 341                  |
| `_collect_names`               | 1206 (CLI-arg helper used by 2+ commands) |
| `_LOG_FORBIDDEN_IN_DETAIL`     | 1559 (security deny-list regex, F1-shaped; used by `append_log` + `log_event`) |

**After extraction:** at the top of `wiki_ops.py`, replace the moved
symbol bodies with:

```python
from wiki_ingest._safety import (
    die, slugify, _safe_name, _safe_inline, _check_case_collision,
    _is_relative_to, read_text, _atomic_write_text, write_text,
    _safe_for_json, _skip_symlink,
    MAX_PAGE_BYTES, MAX_SUMMARY_BYTES, MAX_VALUE_BYTES,
    _UNSAFE_NAME_RE, _CTRL_CHARS_RE,
)
```

Internal call sites in `wiki_ops.py` continue using the bare names — the
imports preserve the public-within-the-script API.

`fcntl` import guard moves to `_safety.py`; `unicodedata` import that
was added during the May VDD pass moves to `_safety.py`.

### Component Integration

`_safety.py` imports stdlib only. Other modules will import from it
(F2 ← F1). For this bead, only `wiki_ops.py` imports from it; the layered
DAG is realised incrementally as subsequent beads land.

## Test Cases

### Unit Tests (in `tests/test__safety.py`)

1. **TC-UNIT-01-1**: `test_slugify_nfkc_normalisation`
   - Asserts `slugify('Café')` and `slugify('Café')` return the
     same value (composed vs decomposed Unicode collapse to one slug).
   - Asserts `slugify('Аnchor')` (Cyrillic А) ≠ `slugify('Anchor')`
     (Latin A) — they are NFKC-distinct.

2. **TC-UNIT-01-2**: `test_safe_name_rejects_traversal_and_separators`
   - For each input in `['../etc', '/etc', '\\windows', '.hidden',
     'foo\x00bar', 'foo|bar', '{{name}}']` assert `_safe_name(x, 'kind')`
     calls `sys.exit` (catch via `pytest.raises(SystemExit)` or
     `unittest.assertRaises(SystemExit)`).

3. **TC-UNIT-01-3**: `test_atomic_write_text_is_atomic_under_crash`
   - Setup: monkeypatch `os.fsync` to raise `OSError` on first call.
   - Action: call `_atomic_write_text(path, "new content")` where `path`
     already contains "old content".
   - Assertion: after `OSError`, `path.read_text() == "old content"`
     (no truncation), AND the `.tmp` file in the parent dir is cleaned
     up OR present but not promoted.

4. **TC-UNIT-01-4**: `test_read_text_refuses_symlink`
   - Setup: `target.write_text("secret")`; `link = parent / 'link.md'`;
     `link.symlink_to(target)`.
   - Action: `read_text(link)`.
   - Assertion: returns `""` (the link is treated as missing).

5. **TC-UNIT-01-5**: `test_safe_for_json_strips_control_and_caps_length`
   - Input: `{"title": "Hi\x07there", "long": "x" * 5000}`.
   - Assertion: title strips `\x07`; `long` is truncated to
     `MAX_VALUE_BYTES` characters with the `…[truncated, … chars total]`
     suffix.

### End-to-end Tests (regression — must still pass after this bead)

- `tests.test_r11_byte_identity` — all three sub-tests must still pass.
  This proves the symbol move did not alter observable behaviour.

### Regression Tests

- `python3 wiki_ops.py init /tmp/v015-01 && python3 wiki_ops.py scan
  /tmp/v015-01` — exits 0; output is structurally identical to
  pre-refactor (no `wiki_ingest` import error).

## Acceptance Criteria

- [ ] `wiki_ingest/__init__.py` and `wiki_ingest/_safety.py` exist.
- [ ] `wiki_ingest/_safety.py` ≤300 LoC.
- [ ] `wiki_ops.py` no longer **defines** any of the moved symbols (only
      imports them).
- [ ] `python -m unittest discover -s tests` passes (≥ 8 tests now:
      ≥3 from this bead + 3 R11 + 0 prior unit tests).
- [ ] R11 gate still green on all three fixtures.
- [ ] `validate_skill.py skills/wiki-ingest` exits 0.

## Notes

- This is the FIRST bead that creates `wiki_ingest/`. The package is
  empty except for `_safety.py` and `__init__.py`.
- Keep the symbol move surgical: don't refactor signatures, don't rename
  anything, don't reorder arguments. The bead must be reviewable in a
  3-pane diff: "function X was in wiki_ops.py at line N, now in
  _safety.py at line M; everything else is identical."
- The `.AGENTS.md` charter is a one-time deposit; it lives forever and
  pays back at every future maintainer-onboard moment.

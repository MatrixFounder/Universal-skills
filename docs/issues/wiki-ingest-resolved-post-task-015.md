---
id: WIKI-INGEST-015-RESOLVED
type: known-issue
status: fixed
opened_at: 2026-05-26
resolved_at: 2026-05-26
resolved_by: TASK 015
category: dogfood
component: wiki-ingest
slug: wiki-ingest-resolved-post-task-015
---

# wiki-ingest — RESOLVED post-TASK-015 (2026-05-26)

> **All 15 wiki-ingest deferred findings have been resolved.** The 12
> cosmetic items from the May-2026 VDD-multi audit + the 3 bugs surfaced
> by Sarcasmotron during TASK 015 (M2-015-01, P-M3-015-02, S-M1b-015-09)
> are fixed. Regression tests live in
> [`skills/wiki-ingest/scripts/tests/test_known_issues_resolved.py`](../../skills/wiki-ingest/scripts/tests/test_known_issues_resolved.py).

| ID            | Fix                                                                                                              |
|---------------|------------------------------------------------------------------------------------------------------------------|
| **L-H2**      | `replace_section_body` strips at most one leading `\n` (was: blanket `.lstrip("\n")`).                            |
| **L-L2**      | Determined to be a non-bug — `content or load_asset(...)` fallback ensures content is never truly empty. Test locks "exactly-one-blank-line-between-entries" invariant. |
| **L-L3**      | `_existing_lines` now stitches contiguous `> ` lines into one blockquote entry (Contradiction blocks no longer fragment). |
| **L-L8**      | SKILL.md filesystem-safety paragraph now documents `[`, `]`, `|`, `^` rejection + NFKC normalisation + slug-equivalent collision detection. |
| **L-L9**      | `register-summary --force` now snapshots prior content to `<slug>.md.backup-<UTC-timestamp>` before overwrite; backup path is surfaced in the JSON output. |
| **S-L2**      | `tail_log` regex is ASCII-anchored (`\d{4}-\d{2}-\d{2}` with `re.A`); Unicode-digit decoy dates rejected.            |
| **S-L3**      | `_strip_quotes` mismatched-pair behaviour locked in docstring (pass-through-unchanged, NOT silent corruption).      |
| **P-L1**      | `_check_case_collision` uses `os.scandir()` (~3-5× cheaper at 10k+ files).                                          |
| **P-L2**      | `tail_log` fast path: seek to last 64 KiB on logs >64 KiB; full-file read only on fallback.                         |
| **P-L5**      | `_count_md_structure` decorated with `functools.lru_cache(512)` — `_pick_primary` + `classify-folder` no longer double-read the same candidates. |
| **P-M3**      | `_compile_section_header_re(header_text)` LRU-cached at module level (was: rebuilt per `find_section` call).        |
| **P-M5**      | `cmd_find` uses ONE merged-regex pass (`(?P<t0>...)|(?P<t1>...)`) instead of N `.count()` passes.                    |
| **M2-015-01** | `_atomic_write_text` unlinks the tmp file on `os.write` / `os.fsync` failure (no orphan `.tmp` litter on crash).     |
| **P-M3-015-02** | `replace_section_body` accepts `masked=` and propagates to `find_section` (batch K-section rewrites pay mask cost once). |
| **S-M1b-015-09** | `register-summary` checks `is_symlink()` on the UNRESOLVED path BEFORE `.resolve()` (defence no longer no-op). Sensitive-path blocklist + inbox containment now check both unresolved AND resolved forms. |

The regression-test file enforces all 15 fixes; restoring a regression
requires deleting both the fix AND the test.

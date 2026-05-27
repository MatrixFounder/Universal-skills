# wiki-ingest exit codes

Authoritative table. Every `die(code=N)` in `scripts/wiki_ingest/` and
`scripts/wiki_ops.py` MUST match a row below; the row is the contract.
Consumers (the `obsidian-llm-wiki`/`/wiki-enrich` bridge, operator
scripts) may key on these codes.

## Matrix

| Code | Symbolic name              | Meaning                                                                                       | Call sites                                                                                                                              |
|------|----------------------------|-----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| 0    | `EXIT_OK`                  | Success.                                                                                       | Implicit `return 0`; `wiki_ops.py --version` fast path.                                                                                  |
| 1    | `EXIT_GENERIC`             | Generic CLI / precondition error.                                                              | `die()` default — most call sites with no explicit `code=`.                                                                              |
| 2    | `EXIT_USAGE`               | Missing schema / argparse usage / wrong directory.                                             | `_vault.py` (schema-missing, vault-not-found); `commands/{promote,demote}.py` (vault-not-dir / no-root / wrong schema-version); `commands/init.py` (target dir missing); `commands/upsert_page.py` (no `--source-slug`); `commands/classify_folder.py` (classify-folder pointed at vault); argparse's built-in. |
| 3    | (legacy)                   | `_sources/<slug>.md` already exists (rerun with `--force`).                                    | `commands/register_summary.py`.                                                                                                          |
| 4    | (legacy)                   | Case-collision on concept/entity filename (rerun with `--force`).                              | `commands/upsert_page.py`.                                                                                                               |
| 5    | (legacy)                   | `--contradicts <text>` not found on existing page.                                             | `commands/upsert_page.py`.                                                                                                               |
| 6    | (legacy)                   | OVERSIZED — input/output exceeds `MAX_PAGE_BYTES` or `MAX_SUMMARY_BYTES`.                      | `_safety.py` read/write; `commands/register_summary.py` summary-file size.                                                              |
| 7    | (legacy)                   | SYMLINK_OVERWRITE — refusing to overwrite a symlink path.                                      | `_safety.py::write_text`; `commands/register_summary.py` (`_sources/<slug>.md` is symlink).                                              |
| 8    | (legacy)                   | SYMLINK_FOLLOW / INBOX_CONTAINMENT — refusing symlinked / out-of-inbox / sensitive-path input. | `commands/register_summary.py`.                                                                                                          |
| 10..19 | *RESERVED*               | Future per-command extensions. Each new entry must add a row here and a TASK reference.        | —                                                                                                                                       |
| 20   | `EXIT_PARTIAL`             | v1.1 orchestrator: mid-pipeline failure; manifest carries `written_so_far[]` + `phase`.        | `commands/ingest.py` (write path).                                                                                                       |
| 21   | `EXIT_SUBPROCESS`          | v1.1 orchestrator: downstream subprocess (e.g. `summarizing-meetings`) failed.                 | `commands/ingest.py`.                                                                                                                    |
| 22   | `EXIT_LLM`                 | v1.1 orchestrator: LLM API unavailable / auth failed.                                          | `commands/ingest.py`.                                                                                                                    |
| 23   | `EXIT_MISSING_VAULT_ID`    | v1.1 strict-mode: `--vault-id` passed but root schema has none.                                | `commands/ingest.py` strict-mode routing.                                                                                                |
| 24   | `EXIT_INVALID_VAULT_ID`    | v1.1: frontmatter or `--vault-id` value violates the pattern `^[a-z][a-z0-9-]{1,30}[a-z0-9]$`. | `_vault.validate_vault_id_pattern`; `commands/init.py`; `commands/ingest.py`.                                                            |
| 25   | `EXIT_VAULT_ID_MISMATCH`   | v1.1 strict-mode: `--vault-id` differs from frontmatter value.                                 | `commands/ingest.py` strict-mode routing.                                                                                                |
| 26   | `EXIT_TIMEOUT`             | v1.1 orchestrator: `--timeout-seconds` overrun; partial envelope carries `phase:"timeout"`.    | `commands/ingest.py`.                                                                                                                    |
| 27..29 | *RESERVED for v1.1*      | Additive within 1.1.x; rename/remove requires bumping CONTRACT §7 (v1.2+).                     | —                                                                                                                                       |

**Bands**:
- **0..9** — legacy / shipped behaviour. Locked; do NOT reassign. Symbolic
  names for 3..8 intentionally absent — call sites use magic numbers
  per "no drive-by changes" rule. Symbolic names live above for docs only.
- **10..19** — reserved for future per-command extensions.
- **20..26** — v1.1 contract band. Symbolic constants in `_safety.py`.
- **30+** — reserved for hypothetical v1.2+ contract.

**Partial-envelope discriminator**: codes **20, 21, 22, 26** MUST carry
`{"phase": "<phase>"}` in the JSON envelope so consumers can route on
failure phase even when codes alias future failure modes.

## How to add a new code

1. Pick a code in the band that fits the change (see "Bands" above). Do
   NOT reassign 0..9.
2. Add a row to the matrix; reference the touching TASK.
3. Add the symbolic name to `_safety.EXIT_*` (mandatory for v1.1+ band;
   optional for the 0..9 legacy band per the "no drive-by" rule).
4. Re-run the audit grep and confirm the new code appears exactly once
   under its expected meaning.

## Validation

```sh
cd skills/wiki-ingest/scripts
grep -rn "code=" --include="*.py" wiki_ingest/ wiki_ops.py \
  | grep -v "^[^:]*:.*#" | grep -v "max_bytes\|kind="
python3 -m unittest discover -s tests
```

Every `code=N` in the grep output must map to a row above.

# Task 023-01 [STUB]: public surface + records + ladder skeleton + RED tests

> **Predecessor:** none (first bead of TASK 023; builds on shipped TASK 022 code).
> **RTM:** [R1] ladder surface, [R2] provider record, [R9] search surface, [R7] RED tests.
> **ARCH:** §15.1 (no new file), §15.2 (ladder), §15.3/§15.3a (records), §15.5 (CLI + data model), §15.9 (023-01).

## Use Case Connection
- UC-1…UC-6 — freezes the CLI/IR contract every later bead fills. No behaviour yet.

## Task Goal
Freeze the **public surface** (CLI flags + IR fields + function signatures) and lay
**RED** tests, so Phase-2 beads implement behind a stable contract. Stubs raise
`NotImplementedError` / return a sentinel; tests assert the surface now and the behaviour
once logic lands (skips flipped per bead).

## Changes Description

### Changes in Existing Files

#### File: `skills/html2md/scripts/html2md/cli.py`
**Function `build_parser`:**
- `--engine` choices → `("lite", "chrome", "auto", "jina", "remote")` (add `remote`).
- Add `--no-remote` (`store_true`, default `False`) — disable the remote-reader tier.
- Add `--remote-format` choices `("html", "markdown")`, default `"html"`.
- Add `--target-selector` (metavar `SEL`, default `"article, main, [role=main]"`).
- Add `--search` (metavar `"QUERY"`, default `None`).
- Add `--max-results` (type `int`, default `5`).
**Function `_resolve_paths` / `main`:**
- Mutual exclusion: if `args.search` AND `args.INPUT` → usage error **exit 2**
  (`parser.error(...)`). If neither `--search` nor `INPUT` → existing "INPUT required" error.
- **`--search` path resolution:** the search branch must NOT hit the `INPUT is required`
  raise — resolve OUTPUT_DIR independently of INPUT (require an explicit OUTPUT_DIR **or**
  `--stdout`; otherwise default to `./tmp/html2md_out/` exactly like the single path). Add a
  `_resolve_search_paths(args)` (or a `search`-aware branch in `_resolve_paths`).
- **`--engine remote` requires config:** if `args.engine == "remote"` and neither
  `HTML2MD_READER_URL` nor `HTML2MD_READER_PROVIDERS` is set → usage error **exit 2** (msg:
  "use `--engine jina` for the built-in"). Never silently fall back to jina.ai.
- **`--max-results` validation:** argparse `type=int`; reject `≤ 0` → usage error **exit 2**.
- `convert(args)`: branch — `if args.search:` call `acquire_mod.run_search(...)` (stub now)
  → loop emit per result; else the existing single-input path.

#### File: `skills/html2md/scripts/html2md/model.py`
**Dataclass `AcquireResult`** (frozen): add fields
- `content_kind: str = "html"`  — `"html"` | `"markdown"` (trust-mode).
- `markdown: str | None = None` — populated only when `content_kind == "markdown"`.
(Defaults keep every existing constructor call valid.)

#### File: `skills/html2md/scripts/html2md/acquire.py`
- Add record `class _RemoteReader(NamedTuple): name: str; base: str; token: str | None`.
- Add record `class _SearchProvider(NamedTuple): name: str; base: str; shape: str; token: str | None` (`shape ∈ {"combined","links"}`).
- Add `class _TierUnavailable(Exception)` — internal fall-through signal carrying
  `kind: str` + `status: int | None` (NOT surfaced to users; distinct from `FetchFailed`).
- Add stub signatures (raise `NotImplementedError("023-0X")`):
  - `_remote_providers(opts) -> list[_RemoteReader]`  (023-02)
  - `_build_reader_request(provider, target, opts) -> tuple[str, dict]`  (023-02)
  - `_fetch_remote_html(target, opts) -> tuple[str, str]`  (023-03; returns `(html, engine_label)`)
  - `_search_providers(opts) -> list[_SearchProvider]`  (023-06)
  - `run_search(query, opts) -> list[AcquireResult]`  (023-06)
- Leave `_fetch_jina_html`, `_acquire_url`, `_host_is_public` in place (rewired in 023-02/03/04).

### New Files
- `skills/html2md/scripts/html2md/tests/test_ladder.py` — RED ladder/classification tests.
- `skills/html2md/scripts/html2md/tests/test_providers.py` — RED provider-construction tests.
- `skills/html2md/scripts/html2md/tests/test_search.py` — RED search tests.
  (All use the existing `acquire._http_get_bytes` monkeypatch idiom; offline.)

## Test Cases
### Unit (surface — GREEN now)
1. **TC-01-01 `test_parser_accepts_new_flags`** — `build_parser().parse_args([...])`
   accepts `--engine remote`, `--no-remote`, `--remote-format markdown`,
   `--target-selector x`, `--search "q"`, `--max-results 3`.
2. **TC-01-02 `test_search_input_mutual_exclusion`** — `--search "q"` + a positional URL
   → `SystemExit(2)` / exit 2.
3. **TC-01-03 `test_acquireresult_new_fields`** — `AcquireResult(...)` defaults
   `content_kind=="html"`, `markdown is None`.
3b. **TC-01-07 `test_engine_remote_requires_config`** — `--engine remote` with no
   `HTML2MD_READER_URL`/`_PROVIDERS` in env → exit 2 (NOT a jina fall-back).
3c. **TC-01-08 `test_max_results_must_be_positive`** — `--max-results 0` / `-1` → exit 2.
3d. **TC-01-09 `test_search_outputdir_resolution`** — `--search "q"` with no OUTPUT_DIR and
   no `--stdout` → defaults to `./tmp/html2md_out/` (no "INPUT required" error); with
   `--stdout` → stdout mode.
### Unit (contract — RED, skip→green per bead)
4. **TC-01-04 `test_providers_stub`** (skip until 023-02) — `_remote_providers`/
   `_build_reader_request` raise `NotImplementedError` now.
5. **TC-01-05 `test_ladder_stub`** (skip until 023-03) — `_fetch_remote_html` raises now.
6. **TC-01-06 `test_search_stub`** (skip until 023-06) — `run_search` raises now.
### Regression
- `./.venv/bin/python -m unittest discover -s html2md/tests` — all existing 022 tests
  still pass (new fields/flags are additive).

## Acceptance Criteria
- [ ] **[R1/R2/R9]** all new CLI flags parse; `--search` ⊥ INPUT → exit 2.
- [ ] **[R4]** `AcquireResult` has `content_kind`/`markdown` (defaults back-compatible).
- [ ] Stub functions exist with the exact signatures above and raise `NotImplementedError`.
- [ ] RED tests written (skipped with the bead that greens them); existing suite green.
- [ ] No gated master touched (only `cli.py`/`model.py`/`acquire.py`/new html2md tests).

## Notes
- Keep `_fetch_jina_html` working until 023-02 folds it into the `jina` provider — do not
  delete it in this bead (avoids a transient broken `--engine jina`).
- **Test homes (avoid two homes for parser asserts):** parser/CLI-surface assertions
  (TC-01-01/02/07/08/09) extend the existing `html2md/tests/test_surface.py`; ladder /
  provider / search *behaviour* lives in the new `test_ladder.py` / `test_providers.py` /
  `test_search.py`.
- Verification: `bash skills/html2md/scripts/tests/test_e2e.sh` (suite + G-1/G-2 gate) PASS.

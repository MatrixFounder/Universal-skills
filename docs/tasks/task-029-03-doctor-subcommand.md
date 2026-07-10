# Task 029.03: `fetch.py doctor` subcommand + `install_components` import-free refactor

**RTM IDs:** R5, R10 (c doctor tests)
**Priority:** High · **Dependencies:** 029.02 (serializes `fetch.py` edits) · **Stub-First:** Stage A (stubs + RED) → Stage B (logic + GREEN)

## Use Case Connection
- UC-2: readiness check without `$PATH` guessing (`scripts/.venv/bin/python scripts/fetch.py doctor`).

## Task Goal
Add a positional `doctor [--json]` subcommand to `fetch.py` that answers "is this skill ready?" cheaply
and import-free, reusing `install_components._components()`. Refactor
`install_components._have_yt_dlp()` to probe distribution metadata instead of importing the module, so the
whole component list stays import-free (the load-bearing correctness point per arch §10.3 + reviewer advisory).

## Files to touch
### Edit
- `skills/transcript-fetcher/scripts/install_components.py` — refactor `_have_yt_dlp()`; add a yt-dlp version helper.
- `skills/transcript-fetcher/scripts/fetch.py` — positional `doctor` dispatch + `_run_doctor(argv)`.
### New
- `skills/transcript-fetcher/scripts/tests/test_doctor.py` — exit codes, JSON shape, import-free assertion, secret-safety.

## Locked constraints (do NOT re-litigate — from PLAN §5, arch §10.3)
- Positional dispatch BEFORE argparse: at the very top of `main()` (after `cfg.load_skill_env()`),
  `if argv and argv[0] == "doctor": return _run_doctor(argv[1:])`. `doctor` is not a valid URL → no collision.
  When `main()` is called with `argv=None`, read `sys.argv[1:]` for the check.
- `_run_doctor` has its OWN mini-parser accepting only `--json`.
- Reuse `install_components._components()` — no probe logic fork.
- REFACTOR `_have_yt_dlp()` to `importlib.metadata.version("yt-dlp")` (NO `import yt_dlp`).
- Report: `interpreter = sys.executable`, `in_venv = (sys.prefix != sys.base_prefix)`, yt-dlp version via
  `importlib.metadata`, ffmpeg + each ASR backend (from `_components()`), cloud row = boolean
  `key_present` (`bool(cfg.openai_api_key())`) + `allow_cloud` (`cfg.asr_allow_cloud_default()`) — NEVER the key value.
- Exit 0 when yt-dlp present, else 7. JSON envelope: `{v:1, interpreter, in_venv, ready, components:{…}, remediation:[…]}`.
- Import-free: a test asserts `"yt_dlp" not in sys.modules` after a doctor run.

## Changes Description

### `install_components.py`
- Replace the body of `_have_yt_dlp()`:
  ```python
  import importlib.metadata as _im  # module-level import at top of file

  def _have_yt_dlp() -> bool:
      try:
          _im.version("yt-dlp")
          return True
      except _im.PackageNotFoundError:
          return False
  ```
- Add a small helper for the doctor (import-free version string, `None` when absent).
  NOTE: `install_components.py` does not currently import `Optional` — add
  `from typing import Optional` alongside the `importlib.metadata` import:
  ```python
  def yt_dlp_version() -> Optional[str]:
      try:
          return _im.version("yt-dlp")
      except _im.PackageNotFoundError:
          return None
  ```
  (Keep `_components()` unchanged in shape — it already calls `_have_yt_dlp()`, now import-free.)
- Confirm no other code path in `install_components` relied on `import yt_dlp`.

### `fetch.py`
- Add `_run_doctor(argv: list[str]) -> int`:
  - mini-parser: `argparse.ArgumentParser(prog="fetch.py doctor")` with only `--json` (store_true).
  - `import install_components as ic` (local import inside the function — install_components imports only
    stdlib + `_config`, so this stays heavy-import-free; do NOT import `yt_dlp`).
  - `components = ic._components()`; build a dict keyed by `c["key"]`:
    `{ "present": bool, "required": bool }`, and for `yt-dlp` add `"version": ic.yt_dlp_version()`.
  - Add a synthetic `cloud` component row: `{"key_present": bool(cfg.openai_api_key()), "allow_cloud": cfg.asr_allow_cloud_default()}` — NO key value.
  - `ready = components[yt-dlp].present`; `remediation = [c["install_hint"] for c in components if c["required"] and not c["present"]]`
    plus an ASR hint when no ASR backend resolves (reuse `install_components._ASR_KEYS`).
  - Envelope: `{"v": 1, "interpreter": sys.executable, "in_venv": sys.prefix != sys.base_prefix, "ready": ready, "components": {...}, "remediation": remediation}`.
  - `--json` → `print(json.dumps(envelope, ensure_ascii=False, indent=2))`; else a human report
    (interpreter, in-venv, per-component ✓/✗ with version for yt-dlp, cloud key_present, remediation lines).
  - Return `0 if ready else 7`.
- In `main()`: BEFORE `_build_parser()`, add the positional dispatch:
  ```python
  effective_argv = sys.argv[1:] if argv is None else argv
  if effective_argv and effective_argv[0] == "doctor":
      return _run_doctor(effective_argv[1:])
  ```
  (Place this AFTER `cfg.load_skill_env()` so tool-bin overrides from `.env` are honoured, but BEFORE
  `parser.parse_args`.)

## Test Cases (NEW `test_doctor.py`)

### Stage A — RED
- **TC-01 (exit 0 present):** patch `install_components._have_yt_dlp` → True (and `yt_dlp_version` → "2026.3.17");
  `fetch.main(["doctor", "--json"])` returns 0; capture stdout, parse JSON, assert
  `env["v"] == 1`, `env["ready"] is True`, `env["components"]["yt-dlp"]["present"] is True`,
  `env["components"]["yt-dlp"]["version"] == "2026.3.17"`, `"interpreter"` and `"in_venv"` keys present.
- **TC-02 (exit 7 absent):** patch `_have_yt_dlp` → False, `yt_dlp_version` → None →
  `fetch.main(["doctor", "--json"])` returns 7; envelope `ready is False`; `remediation` non-empty and
  contains the `install.sh` hint.
- **TC-03 (import-free):** after `fetch.main(["doctor", "--json"])`, assert `"yt_dlp" not in sys.modules`.
  (If a prior test imported it, pop it first: `sys.modules.pop("yt_dlp", None)` in setUp, then assert.)
- **TC-04 (secret never printed):** set `TRANSCRIPT_FETCHER_OPENAI_API_KEY=sk-SEKRET`; run doctor (both
  human + `--json`); assert `"sk-SEKRET"` NOT in captured stdout; assert cloud row exposes only
  `key_present: true` / `allow_cloud`.
- **TC-05 (human mode exit code):** `fetch.main(["doctor"])` (no `--json`) with yt-dlp present → 0.

Capture stdout via `contextlib.redirect_stdout(io.StringIO())` (see `test_fetch_cli.py` for the mock idiom).
Patch the ASR/ffmpeg `_have(...)` probes as needed so the test is host-independent.

### Stage B — GREEN
Implement `_run_doctor` + the refactor; all TCs pass.

### Regression
- `install_components.py --json` still works (its own smoke path); full suite green.

## Verification
```bash
cd skills/transcript-fetcher && ./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts -p test_doctor.py
cd skills/transcript-fetcher && ./scripts/.venv/bin/python scripts/fetch.py doctor            # human, exit 0 in a bootstrapped venv
cd skills/transcript-fetcher && ./scripts/.venv/bin/python scripts/fetch.py doctor --json     # JSON envelope
cd skills/transcript-fetcher && ./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts   # full suite green
```
Expected: `test_doctor.py` OK; live `doctor` exits 0 and prints yt-dlp version; `--json` emits the envelope.

## Acceptance Criteria
- [ ] `fetch.py doctor` dispatched before argparse; `--json` supported; normal fetch CLI untouched.
- [ ] `install_components._have_yt_dlp()` uses `importlib.metadata` (no `import yt_dlp`); `yt_dlp_version()` added.
- [ ] Reports interpreter/in-venv/yt-dlp version/ffmpeg/ASR backends/cloud key_present (never the key).
- [ ] Exit 0 present / 7 absent; envelope `{v, interpreter, in_venv, ready, components, remediation}`.
- [ ] `test_doctor.py` asserts `"yt_dlp" not in sys.modules` and key-never-printed; full suite green.

## Notes
`_run_doctor` must not touch the network or import `yt_dlp`/`weasyprint`/whisper. `_components()`'s
`_have(...)` uses `shutil.which` (cheap) — that is fine; the ONLY thing that must not happen is
`import yt_dlp`, which the refactor removes.
</content>

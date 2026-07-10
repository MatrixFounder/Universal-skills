# Task 029.02: X media-budget wiring + transient/auth remediation + CLI flags & validation

**RTM IDs:** R3, R4 (CLI + x.py resolution), R7, R9b, R10 (d remediation tests)
**Priority:** High · **Dependencies:** 029.01 · **Stub-First:** Stage A (stubs + RED) → Stage B (logic + GREEN)

## Use Case Connection
- UC-1: default-flags Broadcast gets `--concurrent-fragments 8` + the media budget.
- UC-3: a media-download timeout produces an actionable, remediation-carrying error (exit 3/4).
- UC-4: expired X cookies point at the refresh path (auth-branch message, exit 5).

## Task Goal
Thread the 029.01 primitives end-to-end (CLI → `_fetch_one` → `fetch_x_transcript` → `download_audio`),
add the `--concurrent-fragments` / `--media-timeout-sec` CLI flags with exit-2 validation, resolve the
media budget once in `x.py`, and make timeout + auth failures actionable (transient classification +
`remediation` on `TranscriptFetchError`, surfaced in both single-URL and batch JSON envelopes).

## Files to touch
### Edit
- `skills/transcript-fetcher/scripts/sources/_ytdlp_media.py` — `classify_failure()` `"transient"` branch.
- `skills/transcript-fetcher/scripts/sources/_stat.py` — `TranscriptFetchError` optional `remediation` attr.
- `skills/transcript-fetcher/scripts/sources/x.py` — `fetch_x_transcript(media_timeout_sec=…)` param, budget
  resolution, `download_audio` passthrough (concurrent_fragments + media budget), `_raise_for_failure` transient + auth remediation.
- `skills/transcript-fetcher/scripts/fetch.py` — CLI flags + validation, forwarding through `_fetch_one`,
  single-URL + batch `TranscriptFetchError` remediation surfacing.
- `skills/transcript-fetcher/scripts/tests/test_ytdlp_media.py` — transient classification tests.
- `skills/transcript-fetcher/scripts/tests/test_x_adapter.py` — budget-to-download_audio, transient/auth remediation.
- `skills/transcript-fetcher/scripts/tests/test_fetch_cli.py` — flag validation exit 2, batch remediation envelope.

## Locked constraints (do NOT re-litigate — from PLAN §5)
- Media budget resolution: CLI `--media-timeout-sec` (`<= 0` → exit 2) > env
  `TRANSCRIPT_FETCHER_MEDIA_TIMEOUT_SEC` (`_config.media_timeout_sec()`, malformed → None) >
  `media_timeout_for(info.get("duration"))`. Computed ONCE in `x.py` and passed ONLY to
  `download_audio` (as its `timeout_sec`). Probe/captions/silence-removal/ASR keep their existing budgets.
- `concurrent_fragments` CLI `<= 0` → exit 2. The effective value is resolved in `main()` per the
  snippet below (`args.concurrent_fragments if … is not None else cfg.concurrent_fragments()`) —
  do NOT forward a bare `None` from the CLI layer, or the `TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS`
  env knob is silently ignored (`download_audio` would fall back to the constant 8, breaking
  R2/R3a end-to-end). Test-lock: one CLI-level test sets the env var (no CLI flag) and asserts the
  value reaches the `download_audio` argv.
- Transient category matches ONLY `"timeout downloading audio"`; probe timeout stays non-transient.
- `_raise_for_failure` gains `cookies_file: Optional[Path] = None`; auth message names the resolved file
  or the convention `~/.transcript-fetcher/x.com-cookies.txt` (reuse `_auth.DEFAULT_AUTH_DIR`).

## Changes Description

### `_ytdlp_media.classify_failure()`  (R7)
- Add a `"transient"` bucket. Scope: `if "timeout downloading audio" in s: return "transient"`.
  Place it so it does NOT catch `"timeout probing metadata"`. Precedence relative to auth/rate/hard is
  irrelevant (no phrase overlap), but keep auth/rate/hard early returns intact. Docstring: transient is
  the ONLY category the concurrency/media-budget remediation can fix.

### `_stat.TranscriptFetchError`  (R7)
- Convert from a bare `RuntimeError` subclass to one with an optional attr, mirroring
  `MissingDependencyError`:
  ```python
  class TranscriptFetchError(RuntimeError):
      def __init__(self, message: str, *, remediation: Optional[str] = None) -> None:
          super().__init__(message)
          self.remediation = remediation
  ```
  Backward-compatible: every existing `TranscriptFetchError("msg")` still works (`remediation` defaults None).

### `x.py`  (R3/R4/R7/R9b)
- `fetch_x_transcript(...)`: add `concurrent_fragments: Optional[int] = None` and
  `media_timeout_sec: Optional[int] = None` keyword params.
- After the metadata probe (info in hand), compute the media budget once:
  ```python
  media_budget = (
      media_timeout_sec
      if media_timeout_sec is not None
      else ytm.media_timeout_for(info.get("duration"))
  )
  ```
  (The env layer is resolved in `fetch.py`/`_fetch_one` — see below — so `media_timeout_sec` reaching here
  is already CLI-or-env; `x.py` only adds the duration-derived floor.)
- In the ASR-path `download_audio(...)` call: pass `timeout_sec=media_budget` (REPLACING the current
  `timeout_sec=timeout_sec`) AND `concurrent_fragments=concurrent_fragments`. Leave the probe
  (`probe_metadata`), captions (`download_captions`), `remove_silence`, and ASR budgets on their current values.
- `_raise_for_failure(stderr, url, *, default_msg=…, cookies_file: Optional[Path] = None)`:
  - Add a `transient` branch BEFORE the final hard/unknown fallthrough:
    ```python
    if category == "transient":
        raise TranscriptFetchError(
            f"{default_msg} for {url}" + (f": {tail}" if tail else ""),
            remediation=(
                "The media download timed out. Long HLS broadcasts need parallel "
                "fragment download — raise --concurrent-fragments (e.g. 16) and/or "
                "--media-timeout-sec (e.g. 3600)."
            ),
        )
    ```
  - Auth branch (R9b): name the cookie refresh path. When `cookies_file` was used, name it; else name the
    convention path `_auth.DEFAULT_AUTH_DIR / "x.com-cookies.txt"`. Also mention
    `--cookies-file` / `--cookies-from-browser`. Import `_auth` (or the dir constant) at top of `x.py`.
  - Update BOTH call sites to pass `cookies_file=cookies_file`: the probe-failure call
    (`_raise_for_failure(err, url, cookies_file=cookies_file)`) and the audio-download-failure call
    (`_raise_for_failure(derr, url, default_msg="audio download failed", cookies_file=cookies_file)`).

### `fetch.py`  (R3/R4/R7)
- argparse: add two flags near `--timeout-sec`:
  - `--concurrent-fragments` (`type=int, default=None`) — help: parallel HLS fragment downloads for X
    media (default 8 / `TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS`); `1` = serial.
  - `--media-timeout-sec` (`type=int, default=None`) — help: per-attempt budget for the X **media**
    download only (default: duration-derived `max(600, dur*4)`, else 1800; env
    `TRANSCRIPT_FETCHER_MEDIA_TIMEOUT_SEC`). The probe keeps `--timeout-sec`.
- Validation (mirror the `--asr-timeout-sec` block, exit 2 / `UsageError`):
  ```python
  if args.concurrent_fragments is not None and args.concurrent_fragments <= 0:
      return _emit_error(f"--concurrent-fragments must be positive, got {args.concurrent_fragments}.", code=2, error_type="UsageError", json_mode=json_errors)
  if args.media_timeout_sec is not None and args.media_timeout_sec <= 0:
      return _emit_error(f"--media-timeout-sec must be positive, got {args.media_timeout_sec}.", code=2, error_type="UsageError", json_mode=json_errors)
  ```
- Resolve effective values in `main()` before `_fetch_one` (CLI wins, else config):
  ```python
  concurrent_fragments = args.concurrent_fragments if args.concurrent_fragments is not None else cfg.concurrent_fragments()
  media_timeout_sec = args.media_timeout_sec if args.media_timeout_sec is not None else cfg.media_timeout_sec()
  ```
- Thread both through `_fetch_one(... concurrent_fragments=…, media_timeout_sec=…)` in BOTH the
  single-URL and batch call sites; `_fetch_one` gains the two kwargs and forwards them to
  `fetch_x_transcript` in the `source == "x"` branch only.
- Single-URL `except TranscriptFetchError` handler: add `remediation` to `details` when present:
  ```python
  except TranscriptFetchError as e:
      detail = {"url": args.url}
      if getattr(e, "remediation", None):
          detail["remediation"] = e.remediation
      return _emit_error(str(e), code=3, error_type="TranscriptFetchError", details=detail, json_mode=json_errors)
  ```
- Batch mode: add an explicit `except TranscriptFetchError` clause BEFORE the generic `except Exception`
  (mirroring the existing batch `except MissingDependencyError`), incrementing `failures`, writing an
  err_record with `"type": "TranscriptFetchError"` + `remediation` when present. Exit stays 4 aggregate.

## Test Cases

### Stage A — RED
- `test_ytdlp_media.py`: `classify_failure("... timeout downloading audio (>1800s)") == "transient"`;
  `classify_failure("timeout probing metadata (>180s)")` is NOT `"transient"` (None or another bucket).
- `test_x_adapter.py`:
  - **Budget routing:** mock `probe_metadata` → info with `duration=4200`, force the ASR path (no captions,
    ffmpeg available), mock `download_audio` to capture kwargs; assert it received `timeout_sec == 16800`
    (or the CLI/env override) AND `concurrent_fragments` forwarded; assert `probe_metadata` still got the
    small `timeout_sec` (e.g. 180). Use `duration=None` case → media budget 1800.
  - **Transient remediation:** stub `download_audio` returning `(None, "timeout downloading audio (>1800s)")`;
    assert `fetch_x_transcript` raises `TranscriptFetchError` whose `.remediation` names
    `--concurrent-fragments` AND `--media-timeout-sec`.
  - **Auth message:** stub `probe_metadata` returning `(None, "ERROR: This account is protected")`; assert
    `SourceAuthError` whose message contains `x.com-cookies.txt` (convention) when no cookies_file passed,
    and the resolved path when one is passed.
- `test_fetch_cli.py`:
  - `--concurrent-fragments 0` and `--media-timeout-sec -5` → exit 2, `UsageError`.
  - **Env-knob end-to-end (R2/R3a lock):** `TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS=12` set, no CLI
    flag → the value 12 reaches `_fetch_one`/`fetch_x_transcript` (stub captures kwargs). Guards the
    "CLI forwards None" trap.
  - Batch mode with a stubbed `_fetch_one` raising `TranscriptFetchError(remediation=…)` → the per-URL
    stdout record has `"type":"TranscriptFetchError"` and a `remediation` key; run exits 4.

### Stage B — GREEN
Implement the wiring above; all Stage-A tests pass.

### Regression
- YouTube/Vimeo/Skool paths untouched: their adapter + CLI tests stay green (they never pass the new kwargs).
- Full suite green.

## Verification
```bash
cd skills/transcript-fetcher && ./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts -p test_x_adapter.py
cd skills/transcript-fetcher && ./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts -p test_fetch_cli.py
cd skills/transcript-fetcher && ./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts -p test_ytdlp_media.py
cd skills/transcript-fetcher && ./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts   # full suite green
```

## Acceptance Criteria
- [ ] CLI `--concurrent-fragments`/`--media-timeout-sec` present; `<= 0` → exit 2.
- [ ] Media budget resolved once in `x.py` (CLI > env > `media_timeout_for`) and passed ONLY to `download_audio`; probe keeps `--timeout-sec`.
- [ ] `classify_failure` `"transient"` scoped to `"timeout downloading audio"`; probe timeout excluded.
- [ ] `TranscriptFetchError.remediation` surfaced in single-URL AND batch envelopes; exit codes 3/4 unchanged.
- [ ] Auth message names the cookie refresh path (resolved file or convention `x.com-cookies.txt`).
- [ ] Full suite green.

## Notes
The env layer for `media_timeout_sec` is applied in `fetch.py` (`cfg.media_timeout_sec()`), so `x.py`
only adds the duration-derived floor when the value reaching it is `None`. Keep `x.py`'s parameter
`Optional[int]` so a direct library caller (tests) can pass an explicit budget or rely on the floor.
</content>

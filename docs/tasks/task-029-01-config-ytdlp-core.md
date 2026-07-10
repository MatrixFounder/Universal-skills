# Task 029.01: Config knobs + `_ytdlp_media` parallel-download & media-timeout core

**RTM IDs:** R1, R2 (accessor), R4 (pure helper + accessor), R10 (a/b unit tests)
**Priority:** Critical · **Dependencies:** none · **Stub-First:** Stage A (stubs + RED) → Stage B (logic + GREEN)

## Use Case Connection
- UC-1: Long X Broadcast transcribes with default flags (the argv + budget core it rests on).

## Task Goal
Add the concurrency + media-timeout primitives to the two lowest layers so higher layers
(029.02) can wire them: the `DEFAULT_CONCURRENT_FRAGMENTS` constant + `--concurrent-fragments`
argv in `download_audio`, the pure `media_timeout_for()` helper, and the two `_config` accessors.
No `x.py`/`fetch.py`/CLI changes here (that is 029.02).

## Files to touch
### Edit
- `skills/transcript-fetcher/scripts/sources/_ytdlp_media.py` — constant, `download_audio` param + argv, `media_timeout_for()`.
- `skills/transcript-fetcher/scripts/_config.py` — `concurrent_fragments()` + `media_timeout_sec()` accessors.
- `skills/transcript-fetcher/scripts/tests/test_ytdlp_media.py` — argv/clamp + `media_timeout_for` table tests.
- `skills/transcript-fetcher/scripts/tests/test_config.py` — accessor tests (incl. malformed).

## Locked constraints (do NOT re-litigate — from PLAN §5)
- `DEFAULT_CONCURRENT_FRAGMENTS = 8`; argv ALWAYS emits `--concurrent-fragments N` on the media
  download; clamp `min(32, max(1, n))` inside `download_audio`; caption paths untouched.
- `concurrent_fragments()` returns `int` (default 8); malformed/non-positive env → default.
- `media_timeout_sec()` returns `Optional[int]`; malformed → `None` (ignored).
- `media_timeout_for(duration_s)` = `max(600, int(duration_s * 4))` when duration known, else `1800`.

## Changes Description

### `_ytdlp_media.py`
- Add module constant near the top (after imports): `DEFAULT_CONCURRENT_FRAGMENTS = 8`.
- `download_audio(...)` — add keyword param `concurrent_fragments: Optional[int] = None`.
  - Resolve the effective value: if `concurrent_fragments is None` → `DEFAULT_CONCURRENT_FRAGMENTS`;
    then clamp `n = min(32, max(1, int(effective)))`.
  - Emit `args += ["--concurrent-fragments", str(n)]` on the media argv (unconditionally — safe
    no-op for progressive single files). Place it alongside the other `args += [...]` blocks BEFORE
    the `--` / URL terminator. Do NOT touch `download_captions` / `download_subtitle`.
  - Keep the existing `timeout_sec` param exactly as-is (029.02 will pass the media budget into it).
- Add pure helper:
  ```python
  def media_timeout_for(duration_s: Optional[float]) -> int:
      """Media-download budget in seconds from a probed duration.

      max(600, duration_s*4) when the probe reported a duration (a 70-min broadcast
      → ~16800 s), else a generous 1800 s (X Broadcasts commonly probe duration=None).
      Pure + unit-testable; the CLI/env override it in x.py (029.02)."""
      if duration_s and duration_s > 0:
          return max(600, int(duration_s * 4))
      return 1800
  ```
- Add both new public names to `__all__` (`DEFAULT_CONCURRENT_FRAGMENTS`, `media_timeout_for`).

### `_config.py`
- Add (mirroring the existing `asr_timeout_sec` pattern — `env(...)` + `.strip().isdigit()`):
  ```python
  def concurrent_fragments(default: int = 8) -> int:
      """TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS (env/.env). Malformed / non-positive
      → default (config must never crash a run)."""
      raw = env("CONCURRENT_FRAGMENTS")
      if raw and raw.strip().isdigit():
          n = int(raw.strip())
          return n if n > 0 else default
      return default

  def media_timeout_sec() -> Optional[int]:
      """TRANSCRIPT_FETCHER_MEDIA_TIMEOUT_SEC (env/.env). Returns None when unset OR
      malformed OR non-positive (the caller then falls back to media_timeout_for)."""
      raw = env("MEDIA_TIMEOUT_SEC")
      if raw and raw.strip().isdigit():
          n = int(raw.strip())
          return n if n > 0 else None
      return None
  ```
  (`isdigit()` already rejects a leading `-`, so a negative literal falls through to default/None.)

## Test Cases

### Stage A — RED (write first, must FAIL on stubs)
Add to `test_ytdlp_media.py` (`TestDownloadAudioArgv` or a new `TestConcurrentFragments`):
- **TC-01:** default → argv contains `--concurrent-fragments` followed by `"8"`.
- **TC-02:** `concurrent_fragments=16` → argv carries literal `"16"`.
- **TC-03:** `concurrent_fragments=99` → clamped to `"32"`.
- **TC-04:** `concurrent_fragments=1` → argv carries literal `"1"` (serial reproduction).
- **TC-05 (`media_timeout_for` table):** `media_timeout_for(None) == 1800`, `media_timeout_for(0) == 1800`,
  `media_timeout_for(100) == 600` (floor), `media_timeout_for(4200) == 16800`.
Add to `test_config.py` (`TestTypedAccessors` or new class):
- **TC-06:** defaults with `os.environ` cleared → `concurrent_fragments() == 8`, `media_timeout_sec() is None`.
- **TC-07:** `TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS=16` → 16; `=abc` → 8; `=0` → 8; `=-4` → 8.
- **TC-08:** `TRANSCRIPT_FETCHER_MEDIA_TIMEOUT_SEC=3600` → 3600; `=abc` → None; `=0` → None.

Reuse the existing helpers: `_proc(...)` + `mock.patch.object(ytm.subprocess, "run", side_effect=fake_run)`
(the `fake_run` writes `media.mp4` into `workdir` and captures argv — see the existing
`test_clip_and_browser_cookies_with_ffmpeg`). Config tests use `mock.patch.dict(os.environ, {...}, clear=True)`.

### Stage B — GREEN
Implement the logic above; all Stage-A tests pass. Add unit assertion that the existing
non-concurrency argv shape is unchanged (regression): `-f`, output template, `--no-playlist` still present.

### Regression
- Run the full suite — must stay green (274 baseline).

## Verification
```bash
cd skills/transcript-fetcher && ./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts -p test_ytdlp_media.py
cd skills/transcript-fetcher && ./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts -p test_config.py
cd skills/transcript-fetcher && ./scripts/.venv/bin/python -m unittest discover -s scripts/tests -t scripts   # full suite green
```
Expected: all three OK; new TCs present and passing; no network/subprocess-to-yt-dlp executed.

## Acceptance Criteria
- [ ] `DEFAULT_CONCURRENT_FRAGMENTS = 8`, `download_audio(concurrent_fragments=…)` param, argv emits clamped `--concurrent-fragments N`.
- [ ] `media_timeout_for()` returns the documented values; `concurrent_fragments()` / `media_timeout_sec()` accessors behave per table.
- [ ] Caption/subtitle argv paths unchanged (no `--concurrent-fragments` added there).
- [ ] New names in `__all__`; full suite + the two modules GREEN.

## Notes
Do NOT wire the CLI or `x.py` here — those are 029.02. This task is intentionally leaf-level so its
tests exercise the primitives in isolation.
</content>

---
id: TF-X-7
type: known-issue
status: open
opened_at: 2026-07-10
category: robustness
severity: LOW
component: transcript-fetcher
slug: tf-x-7-timeout-orphans-ffmpeg-children
---

# TF-X-7 — media-download `TimeoutExpired` orphans ffmpeg children; workdir rmtree races them

> Deferred finding from TASK 029's adversarial review cycle 1 (2026-07-10).
> Architecture: [`docs/architectures/architecture-016-transcript-fetcher-x-asr.md`](../architectures/architecture-016-transcript-fetcher-x-asr.md) §10.

**Status:** open • **Severity:** LOW •
**Location:** `sources/_ytdlp_media.download_audio` (`subprocess.run(..., timeout=timeout_sec)`);
the `finally: shutil.rmtree(workdir, ignore_errors=True)` cleanup in `sources/x.py`'s
`fetch_x_transcript`.

**Symptom:** `download_audio` invokes yt-dlp via `subprocess.run(..., timeout=timeout_sec)`
with no `start_new_session`/process-group handling. On `subprocess.TimeoutExpired`,
CPython SIGKILLs only the direct yt-dlp child process. yt-dlp spawns ffmpeg as a child
of its own — as the external downloader for live HLS, and as the `-x --audio-format m4a`
postprocessor at the end of every VOD download — so that ffmpeg process is orphaned and
keeps running (writing to the workdir, consuming CPU/network) after the SIGKILL. Meanwhile
`fetch_x_transcript`'s `finally` block `rmtree`s the same workdir immediately, so the
orphan continues writing to unlinked inodes: invisible disk usage plus continued CPU/
network activity until it eventually exits on its own (e.g. the live stream ends, or the
source connection drops).

**Root cause:** no process-group isolation for the yt-dlp subprocess — `subprocess.run`
kills only the PID it launched, not its descendants, so a `TimeoutExpired` never reaches
grandchildren.

**Pre-existing before TASK 029:** the `subprocess.run(timeout=...)` mechanics are
byte-identical to the code that predates TASK 029 (verified against the pre-029 HEAD) —
this is not a new defect introduced by the HLS-hardening work. TASK 029 does amplify
exposure in two ways: (1) the media timeout is now classified `"transient"` and its
remediation actively encourages an immediate retry (`--concurrent-fragments` /
`--media-timeout-sec`), so a second 8-connection download can start while the first
orphan may still be alive and consuming the link; (2) budgets grew from a 180s default
to up to 21600s (6h, post-fix cap), making a kill more likely to land mid-postprocessing
on a much larger in-flight file than the old 180s ceiling ever allowed.

**Reproduction (not exercised in the suite — real subprocess timing, not a unit-testable
seam without a live/slow-source fixture):** point the skill at a still-live X Broadcast
with a very small `--media-timeout-sec`; at the timeout, yt-dlp is SIGKILLed while its
ffmpeg child (either the HLS external-downloader or the `-x` postprocessor) is still
running; the orphan is visible via `ps` after the CLI process has already returned exit 3
with the transient/retryable message.

**Workaround:** the orphan is self-limiting — it exits on its own once the source
connection drops or the live stream ends, and `shutil.rmtree(..., ignore_errors=True)`
means the workdir deletion itself never raises even though it races the orphan's writes.
No operator action is required; this is a resource-hygiene issue, not a correctness or
security one (the orphan cannot be redirected to write outside its own tempdir).

**Fix path:** launch yt-dlp via `subprocess.Popen(..., start_new_session=True)` so it
heads its own process group; on `TimeoutExpired`, `os.killpg(pgid, SIGTERM)` then
`SIGKILL` after a short grace period, so ffmpeg children die with their parent. Keep the
existing `"timeout downloading audio"` sentinel string on the resulting message so the
`"transient"` classification (`classify_failure`) is untouched.

**Do-not:** add signal handling inside the ASR backends (`asr/*`) to compensate — the
orphan risk is specific to the yt-dlp media-download subprocess boundary in
`_ytdlp_media.download_audio`, not the ASR transcription step, which runs after the
media file already exists on disk.

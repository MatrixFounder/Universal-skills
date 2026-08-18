---
id: TF-X-7
type: known-issue
status: fixed
opened_at: 2026-07-10
resolved_at: 2026-08-18
resolved_by: process-group teardown in `_ytdlp_media.run_in_process_group`
category: robustness
severity: LOW
component: transcript-fetcher
slug: tf-x-7-timeout-orphans-ffmpeg-children
---

# TF-X-7 — media-download `TimeoutExpired` orphans ffmpeg children; workdir rmtree races them — RESOLVED (2026-08-18)

> Deferred finding from TASK 029's adversarial review cycle 1 (2026-07-10).
> Architecture: [`docs/architectures/architecture-016-transcript-fetcher-x-asr.md`](../architectures/architecture-016-transcript-fetcher-x-asr.md) §10, §10.5 (the fix).

**Status:** ✅ RESOLVED (2026-08-18; delete this entry when the fix commit is old enough to
prune) • **Severity:** LOW •
**Location:** `sources/_ytdlp_media.download_audio` (was
`subprocess.run(..., timeout=timeout_sec)`, now `run_in_process_group`);
the `finally: shutil.rmtree(workdir, ignore_errors=True)` cleanup in `sources/x.py`'s
`fetch_x_transcript`.

**Symptom (was):** `download_audio` invokes yt-dlp via `subprocess.run(..., timeout=timeout_sec)`
with no `start_new_session`/process-group handling. On `subprocess.TimeoutExpired`,
CPython SIGKILLs only the direct yt-dlp child process. yt-dlp spawns ffmpeg as a child
of its own — as the external downloader for live HLS, and as the `-x --audio-format m4a`
postprocessor at the end of every VOD download — so that ffmpeg process is orphaned and
keeps running (writing to the workdir, consuming CPU/network) after the SIGKILL. Meanwhile
`fetch_x_transcript`'s `finally` block `rmtree`s the same workdir immediately, so the
orphan continues writing to unlinked inodes: invisible disk usage plus continued CPU/
network activity until it eventually exits on its own (e.g. the live stream ends, or the
source connection drops).

**Root cause (was):** no process-group isolation for the yt-dlp subprocess — `subprocess.run`
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

**Reproduction (was — see Regression coverage below for the in-suite version):** point the
skill at a still-live X Broadcast with a very small `--media-timeout-sec`; at the timeout,
yt-dlp is SIGKILLed while its ffmpeg child (either the HLS external-downloader or the `-x`
postprocessor) is still running; the orphan is visible via `ps` after the CLI process has
already returned exit 3 with the transient/retryable message.

**Fix (2026-08-18):** `download_audio` now launches yt-dlp through the new
`_ytdlp_media.run_in_process_group(argv, timeout=…)` — a `CompletedProcess`-returning wrapper
over `subprocess.Popen(..., start_new_session=True)`, so yt-dlp heads its own process group
and every descendant it spawns (including ffmpeg) lands in that group. On `TimeoutExpired`
the group receives SIGTERM, a `GROUP_KILL_GRACE_SEC` (5 s) grace, then SIGKILL, before
`download_audio` returns — so the `rmtree` in `x.py`'s `finally` block no longer races a live
writer. Three details are load-bearing:

1. **The SIGKILL is unconditional**, sent even when the direct child has already been reaped:
   the child exiting says nothing about the ffmpeg grandchild, which is the process this
   whole helper exists to reap. The group id stays reserved while its unreaped leader is a
   zombie, so the escalation cannot land on a recycled group.
2. **The own-group guard.** `_process_group_of` returns `None` — falling back to
   `Popen.kill()` on the PID alone — when the resolved pgid equals `os.getpgrp()`, when the
   platform has no process groups (Windows), or when the child is already gone. An
   `os.killpg` on our own group would take the whole CLI down with the download.
3. **`BaseException`, not just `TimeoutExpired`.** `start_new_session=True` also detaches the
   child from the terminal's foreground process group, so Ctrl-C no longer reaches yt-dlp
   directly. Without that arm the fix would have traded a timeout orphan for a Ctrl-C orphan.

The `"timeout downloading audio (>{n}s)"` sentinel is preserved verbatim, so
`classify_failure`'s `startswith`-matched `"transient"` bucket and its
`--concurrent-fragments` / `--media-timeout-sec` remediation are untouched.

**Scope of the fix — CORRECTED 2026-08-19, this paragraph was wrong as first written.**
It claimed `probe_metadata` / `download_captions` were safe on plain `subprocess.run` because
they pass `--skip-download`, so "no ffmpeg is ever spawned". The ffmpeg half is true; the
*leaf* conclusion it was used to justify is not. yt-dlp spawns a JavaScript-runtime child
during extraction — on exactly the `--skip-download` path — and `--cookies-from-browser`
(plumbed to both sites) additionally spawns `security find-generic-password` on macOS /
`dbus-send` + `kwallet-query` on Linux. yt-dlp's own `Popen` wrapper does not set
`start_new_session`, so those grandchildren sat in our group and a plain `subprocess.run`
timeout reached only the yt-dlp PID.

Both sites — plus `sources/youtube.py:378`, `sources/youtube.py:486` and
`sources/vimeo.py:220`, which neither issue had named — were routed through
`run_in_process_group` when [TF-X-8](tf-x-8-asr-subprocess-timeout-no-process-group.md) was
fixed. The invariant is now uniform: **every yt-dlp invocation goes through
`run_in_process_group`; only genuine leaf ffmpeg/ffprobe calls (`remove_silence`,
`probe_media_duration`) use plain `subprocess.run`** — and "leaf" there is backed by
measurement (0 children observed under the exact argv), not by an argument about ffmpeg.

**Regression coverage** (closes the "not exercised in the suite" caveat above):
`tests/test_ytdlp_media.TestTimeoutKillsProcessGroup` — the SIGTERM→SIGKILL sequence, the
own-group guard, an already-dead group, a child that vanished before the kill, Ctrl-C, and a
POSIX-gated **real-process** reproduction using `/bin/sh` plus a background write-loop as a
stand-in for the yt-dlp→ffmpeg pair, asserting the marker file stops growing after the
timeout. That last test was verified to FAIL against the pre-fix `subprocess.run` path; its
stand-in loop is self-limiting (~20 s) so a regression cannot leave a permanent orphan.

**Do-not:** do not reword the `"timeout downloading audio"` sentinel — `classify_failure`
matches it with `startswith` to return `"transient"`. Do not drop the `os.getpgrp()` guard in
`_process_group_of` to "simplify" it: without it, a child that failed to get its own session
puts the CLI's own process group on the receiving end of `os.killpg`. Do not let anything
raise out of `_kill_process_group` (it runs inside an `except` block — an escaping exception
replaces the `TimeoutExpired` that `download_audio` handles with an unhandled crash), and do
not remove `_wait_quietly`'s `KeyboardInterrupt` arm (a second Ctrl-C during the grace period
would otherwise skip the SIGKILL escalation and leave the orphan alive). The ASR boundary is
[TF-X-8](tf-x-8-asr-subprocess-timeout-no-process-group.md) (now fixed); note that
`run_in_process_group` itself has since MOVED to the top-level `scripts/_procgroup.py` and is
only re-exported from `_ytdlp_media` — do not move it back, `asr/` imports it too and
`sources/x.py` already imports `asr._base`, so the round trip is an import cycle.

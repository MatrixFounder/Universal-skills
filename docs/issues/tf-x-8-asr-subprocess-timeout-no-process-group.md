---
id: TF-X-8
type: known-issue
status: fixed
opened_at: 2026-08-18
resolved_at: 2026-08-19
resolved_by: shared `_procgroup.py` runner wired into `asr/_base._run`
category: robustness
severity: LOW
component: transcript-fetcher
slug: tf-x-8-asr-subprocess-timeout-no-process-group
---

# TF-X-8 — ASR backend `TimeoutExpired` has no process-group teardown (same shape as TF-X-7) — RESOLVED (2026-08-19)

> Found while adversarially reviewing the [TF-X-7](tf-x-7-timeout-orphans-ffmpeg-children.md)
> fix (2026-08-18). Architecture:
> [`docs/architectures/architecture-016-transcript-fetcher-x-asr.md`](../architectures/architecture-016-transcript-fetcher-x-asr.md) §10.5.

**Status:** ✅ RESOLVED (2026-08-19) • **Severity:** LOW •
**Location:** `asr/_base.ASRBackend._run` — `subprocess.run(argv, ..., timeout=…)`, the single
shared subprocess boundary for every local backend (`macwhisper`, `whisper_cli`,
`whisper_cpp`).

**Symptom:** structurally identical to TF-X-7. `subprocess.run(timeout=…)` SIGKILLs only the
PID it launched, so if a transcription tool spawns a child of its own, an ASR timeout orphans
that grandchild. `_run` passes no `start_new_session` and does no process-group handling.

**Backend topology — MEASURED, replacing the original record's "not verified in this
environment" caveats.** All three local backends were investigated directly:

| Backend | Grandchild? | Evidence |
| :--- | :--- | :--- |
| `whisper_cli` → openai-whisper | **YES** | `whisper/audio.py:45-58` in the published 20250625 sdist runs `ffmpeg -nostdin -threads 0 -i <file> … -` via `subprocess.run(check=True)`; it is the only spawn in the package. One call site (`transcribe.py:139` → `audio.py:139-140`), executed ONCE before the decode loop — so the child lives seconds at t≈0 and does not scale with transcription time. Measured 2.71 s on a 2 h file. |
| `whisper_cpp` → `whisper-cli`/`main` | **NO** — leaf | `cli.cpp` has no spawn primitives; decoding is in-process. Its OWN ffmpeg call (`whisper_cpp.py:60`) is a direct child with 0 children observed across sampling, so a plain `Popen.kill()` already sufficed there. |
| `macwhisper` → `mw` | **NO, but see below** | `mw` is a thin Unix-socket client. Warm path: zero children. Cold path: one short-lived `/usr/bin/open /Applications/MacWhisper.app/ -gj`; LaunchServices then starts the app at **ppid=1, in its own session** — outside any group we can signal, before or after this fix. |

**The `mw` corollary that closes the record's original open question:** killing `mw` *does*
stop the transcription. Measured twice by sampling MacWhisper.app's CPU-time after a SIGKILL
mid-file: it flatlines to idle within ~2 s, because the app cancels when the client socket
closes. So `--asr-timeout-sec` is honest about both waiting and stopping, and no
"orphaned work" caveat belongs in the docs.

**Net exposure, stated plainly:** narrow. The only grandchild-bearing backend is
`whisper_cli`; its ffmpeg window is the first few seconds of a run whose default budget is
1800 s, and the orphan normally self-reaps via SIGPIPE when the killed parent drops the pipe
(measured: 0.08 s). The residual that justifies the fix is a decode **stalled on input** —
it has never written to stdout, so no SIGPIPE ever arrives (measured: still alive, ppid=1,
5 s after the kill) — and a stalled decode is simultaneously the main way a timeout can reach
that window at all.

**Fix (2026-08-19):** `asr/_base.ASRBackend._run` now calls `run_in_process_group` instead of
`subprocess.run`. Getting there required resolving a layering conflict this record's own
"Fix path" had wrong:

1. **The runner moved to a new top-level `scripts/_procgroup.py`** (sibling of `_config.py`),
   and `sources/_ytdlp_media.py` re-exports it. Importing it from `_ytdlp_media` — as this
   record originally prescribed — was not viable: `sources/x.py:27` and `sources/yandex.py:72`
   already do a module-level `from asr._base import DEFAULT_ASR_TIMEOUT_SEC`, so an
   `asr → sources._ytdlp_media` edge closes an import cycle (reproduced: adding one more
   `sources → asr` import kills every entry point with a partially-initialized-module
   `ImportError`). It also violated `asr/_base.py`'s "no heavy imports at module import time"
   rule — measured +15 modules including an XML parser on every ASR-only path, versus +1 for
   the top-level module.
2. **`-nostdin` added to `whisper_cpp.py`'s ffmpeg argv.** `run_in_process_group` sets
   `start_new_session=True`, which detaches the child from the controlling terminal; an ffmpeg
   still reading stdin for interactive keys could compete for the operator's keystrokes.
   `_ytdlp_media.remove_silence` already passed it — this aligns the two.
3. **A one-line test seam that would have gone silently vacuous was repaired.** TF-X-7's
   `test_teardown_failure_never_replaces_the_original_exception` patches `os` by NAME
   (`mock.patch.object(ytm, "os", crippled_os)`); after the move that injection no longer
   reached the guard, and the test still PASSED while exercising nothing. Retargeted to
   `_procgroup` and re-verified non-vacuous.

**Scope note — the fix went wider than this record.** A completeness sweep found the same
unguarded `subprocess.run(timeout=…)` yt-dlp shape at three sites named by neither TF-X-7 nor
TF-X-8: `sources/youtube.py:378` (`_try_download_subtitle`, also re-exported as
`_ytdlp_media.download_subtitle`, so it is shared plumbing), `sources/youtube.py:486`
(`_fetch_video_info`, used by youtube AND vimeo), and `sources/vimeo.py:220`. All three were
swapped to the helper in the same change, along with `probe_metadata` and `download_captions`
(see the TF-X-7 correction below). The resulting invariant is uniform and easy to check:
**every yt-dlp invocation goes through `run_in_process_group`; only genuine leaf ffmpeg/ffprobe
calls use plain `subprocess.run`.**

**Regression coverage:** `tests/test_asr_backends.TestRunProcessGroupTeardown` — own-session
launch, `ASRError` still naming the budget from `TimeoutExpired.timeout`, `FileNotFoundError`
still wrapped, and a POSIX-gated real-process reproduction mirroring the yt-dlp one (a
`/bin/sh` parent with a background write-loop grandchild). Both process tests were verified to
FAIL against the pre-fix `_run`. `tests/test_ytdlp_media.TestProcgroupStaysSourceNeutral`
locks the layering rule by AST-scanning `_procgroup.py` for first-party imports and asserting
a subprocess import of it pulls in no `sources`/`asr` module — there is no import-lint gate
for this skill, so the rule needed a test the way CLAUDE.md's html-skill weasyprint exclusion
does.

**Do-not:** do not import `run_in_process_group` from `sources._ytdlp_media` inside `asr/` —
use `_procgroup` directly; the re-export exists only for existing `ytm.` call sites. Do not
add first-party imports to `_procgroup.py` (the guard test will fail, and the cycle is real).
Do not remove `-nostdin` from `whisper_cpp.py`'s ffmpeg argv while `_run` starts a new session.

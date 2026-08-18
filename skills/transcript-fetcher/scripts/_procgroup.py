"""Process-group-aware subprocess execution — kill a child AND its descendants.

Source-neutral shared plumbing, deliberately a **top-level** module (sibling to
``_config.py``) rather than a member of ``sources/`` or ``asr/``: both packages
import it, and it belongs to neither. Concretely — ``sources/x.py`` and
``sources/yandex.py`` already do a module-level ``from asr._base import
DEFAULT_ASR_TIMEOUT_SEC``, so parking this in ``sources/`` and importing it from
``asr/_base`` would close an import cycle the moment anyone adds a second edge.
Living here also keeps ``asr/_base``'s "no heavy imports at module import time"
rule intact: importing ``sources._ytdlp_media`` instead would drag the whole
yt-dlp/caption stack (an XML parser included) into every ASR-only path.

**Do not import from ``sources/`` or ``asr/`` here.** That one rule is what keeps
the cycle closed; this module needs only the standard library.

Why it exists (TF-X-7, TF-X-8): ``subprocess.run(..., timeout=…)`` SIGKILLs only
the PID it launched. yt-dlp spawns ffmpeg (HLS external downloader, ``-x``
postprocessor) and a JS runtime during extraction; openai-whisper spawns ffmpeg
to decode. Killing the direct child alone orphans those grandchildren, which keep
consuming CPU/network — and, for the media download, keep writing into a workdir
the caller is already ``rmtree``-ing.
"""
from __future__ import annotations

import os
import signal
import subprocess
from typing import Optional



# Seconds between the SIGTERM and the SIGKILL delivered to a timed-out
# download's process group: long enough for yt-dlp/ffmpeg to flush and unlink
# their partial files on the polite signal, short enough that the CLI still
# returns promptly on the impolite one.
GROUP_KILL_GRACE_SEC = 5.0


def _process_group_of(proc: subprocess.Popen) -> Optional[int]:
    """Process-group id of ``proc``, or ``None`` when it must NOT be signalled.

    ``None`` means "fall back to killing the direct child only" and covers
    three cases: the platform has no process groups (Windows), the child is
    already gone, or — the load-bearing guard — the resolved group is OUR OWN,
    which an ``os.killpg`` would take the whole CLI down with. The last one can
    only happen if ``start_new_session`` silently did not take effect; it is
    cheap to check and catastrophic to miss.
    """
    if not (hasattr(os, "killpg") and hasattr(os, "getpgid")):
        return None
    try:
        pgid = os.getpgid(proc.pid)
        if pgid == os.getpgrp():
            return None
    except OSError:      # ProcessLookupError / PermissionError are subclasses
        return None
    return pgid


def _signal_group(pgid: int, sig: int) -> bool:
    """``os.killpg`` that never raises. ``False`` = the group is already gone."""
    try:
        os.killpg(pgid, sig)
    except OSError:      # ProcessLookupError / PermissionError are subclasses
        return False
    return True


def _kill_direct(proc: subprocess.Popen) -> None:
    """Best-effort SIGKILL on the direct child ONLY — the degraded path.

    Reached when there is no group to signal (Windows, an already-dead child,
    or the own-group guard) or when the group teardown itself failed. This is
    the pre-TF-X-7 behaviour: it does not reach grandchildren.
    """
    try:
        proc.kill()
    except OSError:
        pass


def _wait_quietly(proc: subprocess.Popen, timeout: float) -> None:
    """``proc.wait`` that swallows the timeout **and a second Ctrl-C**.

    The ``KeyboardInterrupt`` arm is load-bearing. Because
    ``start_new_session=True`` detaches the child from the terminal's
    foreground group, a stuck-looking download is exactly when a user mashes
    Ctrl-C — and an interrupt landing in this grace wait would abort
    :func:`_kill_process_group` before its SIGKILL escalation, leaving alive
    the very orphan the teardown exists to reap. The interrupt that started
    the teardown is already propagating (``run_in_process_group`` re-raises
    it), so dropping this one costs nothing and is bounded by ``timeout``.
    """
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        pass
    except KeyboardInterrupt:
        pass


def _kill_process_group(
    proc: subprocess.Popen, *, grace_sec: float = GROUP_KILL_GRACE_SEC
) -> None:
    """Kill ``proc`` **and its descendants**: SIGTERM the group, then SIGKILL.

    ``Popen.kill()`` — and therefore ``subprocess.run(timeout=...)`` — signals
    only the PID it launched. yt-dlp spawns ffmpeg as a child of its own (the
    external downloader for live HLS, and the ``-x --audio-format`` post-
    processor at the end of every VOD download), so killing the direct child
    alone ORPHANS that ffmpeg: it keeps burning CPU/network and writing into a
    workdir the caller is about to ``rmtree`` (TF-X-7).

    The SIGKILL is sent **unconditionally** after the grace period, even when
    the direct child has already been reaped: the child exiting says nothing
    about the grandchild, which is the entire reason this helper exists. The
    group id stays reserved while its leader is an unreaped zombie, so the
    escalation cannot land on an unrelated recycled group.

    **Never raises.** This runs inside an ``except`` block, so anything
    escaping it would REPLACE the exception that triggered the teardown —
    turning a ``TimeoutExpired`` that ``download_audio`` handles (returning the
    retryable ``"transient"`` sentinel) into an unhandled crash on a merely
    slow download. A teardown failure degrades to :func:`_kill_direct` instead.
    """
    try:
        pgid = _process_group_of(proc)
        if pgid is None or not _signal_group(pgid, signal.SIGTERM):
            # No group to signal (or it is already gone) — PID best effort.
            _kill_direct(proc)
            return
        _wait_quietly(proc, grace_sec)
        _signal_group(pgid, signal.SIGKILL)
        _wait_quietly(proc, grace_sec)
    except Exception:
        # Deliberately broad, and deliberately NOT BaseException: the blocking
        # waits already absorb a stray Ctrl-C (see `_wait_quietly`), and
        # swallowing every interrupt here would make the key feel dead.
        _kill_direct(proc)


def run_in_process_group(
    args: list,
    *,
    timeout: Optional[float],
    grace_sec: float = GROUP_KILL_GRACE_SEC,
) -> subprocess.CompletedProcess:
    """``subprocess.run(capture_output=True, text=True, timeout=…)`` that also
    reaps GRANDchildren when the timeout fires (TF-X-7).

    Two differences from ``subprocess.run``:

    * the child is launched with ``start_new_session=True``, so it heads its
      own process group and every descendant it spawns lands in that group;
    * ``TimeoutExpired`` — and any other ``BaseException``, notably
      ``KeyboardInterrupt`` — tears the whole group down via
      :func:`_kill_process_group` before it propagates.

    The ``BaseException`` arm is not decorative: ``start_new_session=True``
    also detaches the child from the terminal's foreground process group, so a
    Ctrl-C no longer reaches yt-dlp directly. Without that arm the fix for a
    timeout orphan would have introduced a Ctrl-C orphan.

    Raises the same ``FileNotFoundError`` / ``subprocess.TimeoutExpired`` the
    callers already handle; returns a ``CompletedProcess`` otherwise.
    """
    popen_kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    with subprocess.Popen(args, **popen_kwargs) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc, grace_sec=grace_sec)
            # Drain the pipes so the fds are released now that the writers are
            # dead; the partial output is discarded — the caller reports the
            # timeout, not the truncated log.
            try:
                proc.communicate(timeout=grace_sec)
            except subprocess.TimeoutExpired:
                pass
            raise
        except BaseException:
            _kill_process_group(proc, grace_sec=grace_sec)
            raise
    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)

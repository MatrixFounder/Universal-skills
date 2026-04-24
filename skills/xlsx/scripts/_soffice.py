"""Thin wrapper around the LibreOffice `soffice` command.

Used by `docx_accept_changes.py`, `xlsx_recalc.py`, `pptx_to_pdf.py`,
`pptx_thumbnails.py`. Not a CLI — import as a module.

Design goals:
- Locate `soffice` via $PATH or common macOS/Linux install paths.
- Run headless, without the default UI, with a disposable user profile
  so concurrent invocations don't fight over a lock file.
- Detect sandboxes that block AF_UNIX sockets and transparently apply
  the LD_PRELOAD / DYLD_INSERT shim from `office/shim/` so LibreOffice
  can still start. Shim is no-op on AF_UNIX-capable machines (desktop
  macOS / Linux / most CI runners).
- Raise a clear exception on timeout or non-zero exit.
"""

from __future__ import annotations

import fcntl
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path


class SofficeError(RuntimeError):
    pass


_COMMON_LOCATIONS = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/opt/homebrew/bin/soffice",
    # Common sandboxed / containerised deployments.
    "/opt/libreoffice/program/soffice",
    "/snap/libreoffice/current/lib/libreoffice/program/soffice",
)

_SHIM_DIR = Path(__file__).resolve().parent / "office" / "shim"


def find_soffice() -> str:
    found = shutil.which("soffice")
    if found:
        return found
    for candidate in _COMMON_LOCATIONS:
        if Path(candidate).is_file():
            return candidate
    raise SofficeError(
        "soffice (LibreOffice) not found. Install LibreOffice and ensure "
        "`soffice` is on PATH (brew install --cask libreoffice / apt install libreoffice)."
    )


# --- AF_UNIX availability probe + shim auto-apply ---

_af_unix_ok: bool | None = None


def _af_unix_available() -> bool:
    """Can we open an AF_UNIX socket in the current process?

    Cached per-process — sandbox policy is static for a running process.
    Returns True for normal desktop / CI runners; False for seccomp-
    tightened sandboxes that reject AF_UNIX socket creation.
    """
    global _af_unix_ok
    if _af_unix_ok is not None:
        return _af_unix_ok
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.close()
        _af_unix_ok = True
    except (OSError, AttributeError):
        _af_unix_ok = False
    return _af_unix_ok


def _shim_library_path() -> Path | None:
    """Path to the compiled shim for this OS, building it if needed.

    Returns None when compilation is unavailable (e.g. no compiler
    installed) — the caller then proceeds without the shim and lets
    LibreOffice fail with its native AF_UNIX error.

    Concurrency: when two Python processes invoke this simultaneously
    from parallel pipelines, both may race to run build.sh and clobber
    each other's .so/.dylib mid-write. We serialise the build step
    with an advisory file lock (`fcntl.flock`) held for the duration
    of the compiler invocation. Non-building callers acquire and
    release the lock quickly, so contention is minimal.
    """
    system = platform.system()
    if system == "Linux":
        lib = _SHIM_DIR / "liblo_socket_shim.so"
    elif system == "Darwin":
        lib = _SHIM_DIR / "liblo_socket_shim.dylib"
    else:
        return None

    src = _SHIM_DIR / "lo_socket_shim.c"
    if not src.is_file():
        return None

    lock_path = _SHIM_DIR / ".build.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w") as lock_fp:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
            # Re-check under the lock: another process may have built
            # the library while we were waiting.
            needs_build = not lib.is_file() or src.stat().st_mtime > lib.stat().st_mtime
            if needs_build:
                builder = _SHIM_DIR / "build.sh"
                if not builder.is_file():
                    return None
                try:
                    subprocess.run(
                        ["bash", str(builder)],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    return None
    except OSError:
        # Lock file directory unwritable (e.g. read-only install).
        # Fall through: if the library exists from a previous build
        # we can still use it; otherwise return None.
        pass
    return lib if lib.is_file() else None


def _soffice_hardened_on_macos(soffice_path: str) -> bool:
    """Return True if `soffice_path` has hardened runtime on macOS.

    Apple strips DYLD_INSERT_LIBRARIES at exec time for hardened-
    runtime binaries — the shim cannot attach to such a binary. The
    LibreOffice.app bundle from The Document Foundation IS signed with
    hardened runtime; the shim silently no-ops in that case.
    """
    if platform.system() != "Darwin":
        return False
    try:
        result = subprocess.run(
            ["codesign", "--display", "--verbose=2", soffice_path],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    # `codesign` prints `flags=0x10000(runtime)` for hardened runtime.
    return "runtime" in (result.stderr + result.stdout).lower()


def _apply_shim_env(env: dict[str, str]) -> bool:
    """Augment env to LD_PRELOAD / DYLD_INSERT the shim.

    Returns True when the shim was applied, False otherwise.
    """
    lib = _shim_library_path()
    if lib is None:
        return False
    system = platform.system()
    if system == "Linux":
        existing = env.get("LD_PRELOAD", "")
        env["LD_PRELOAD"] = f"{lib}:{existing}" if existing else str(lib)
        return True
    if system == "Darwin":
        existing = env.get("DYLD_INSERT_LIBRARIES", "")
        env["DYLD_INSERT_LIBRARIES"] = f"{lib}:{existing}" if existing else str(lib)
        env["DYLD_FORCE_FLAT_NAMESPACE"] = "1"
        return True
    return False


def run(args: list[str], *, timeout: int = 120, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run `soffice --headless --norestore --nologo --nodefault <args>`.

    Each invocation gets a throw-away user profile to avoid "office is
    already running" conflicts. When AF_UNIX is blocked by the host
    sandbox, the LO socket shim is auto-compiled (if needed) and
    injected via LD_PRELOAD / DYLD_INSERT_LIBRARIES.
    """
    soffice = find_soffice()
    with tempfile.TemporaryDirectory(prefix="soffice-profile-") as profile:
        env = os.environ.copy()
        env.setdefault("SAL_USE_VCLPLUGIN", "svp")

        # Force the shim when requested explicitly; otherwise only
        # activate it when we detect AF_UNIX is blocked.
        shim_forced = env.get("LO_SHIM_FORCE", "").strip() not in ("", "0", "false", "no")
        if shim_forced or not _af_unix_available():
            applied = _apply_shim_env(env)
            # Apple strips DYLD_INSERT_LIBRARIES at exec for hardened-
            # runtime binaries. LibreOffice.app from The Document
            # Foundation is signed with hardened runtime, so the shim
            # silently no-ops. Warn when shim was requested but target
            # is hardened — saves the user from a confusing session of
            # wondering why their shim didn't apply.
            if applied and _soffice_hardened_on_macos(soffice):
                warnings.warn(
                    f"DYLD_INSERT_LIBRARIES will be stripped by macOS: {soffice} "
                    "has hardened runtime. The shim cannot attach. If you need "
                    "the shim here, use an unhardened LibreOffice build or re-sign "
                    "the binary with `codesign --remove-signature`.",
                    RuntimeWarning,
                    stacklevel=2,
                )

        profile_url = Path(profile).as_uri()
        cmd = [
            soffice,
            "--headless",
            "--norestore",
            "--nologo",
            "--nodefault",
            f"-env:UserInstallation={profile_url}",
            *args,
        ]
        try:
            return subprocess.run(
                cmd,
                env=env,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise SofficeError(f"soffice timed out after {timeout}s: {' '.join(cmd)}") from exc
        except subprocess.CalledProcessError as exc:
            raise SofficeError(
                f"soffice failed (exit {exc.returncode}):\n"
                f"cmd: {' '.join(cmd)}\n"
                f"stderr: {exc.stderr.strip()}"
            ) from exc


def convert_to(src: str | Path, out_dir: str | Path, target_format: str, *, timeout: int = 180) -> Path:
    """Convert `src` into `target_format` (e.g. 'pdf', 'docx', 'png') in `out_dir`.

    Returns the path of the produced file. LibreOffice names the output
    `<src.stem>.<target_format>`.
    """
    src = Path(src).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            "--convert-to",
            target_format,
            "--outdir",
            str(out_dir),
            str(src),
        ],
        timeout=timeout,
    )
    produced = out_dir / f"{src.stem}.{target_format.split(':', 1)[0]}"
    if not produced.is_file():
        raise SofficeError(f"Expected output not found: {produced}")
    return produced


if __name__ == "__main__":
    # Quick sanity check: `python _soffice.py` prints the resolved
    # binary plus shim status.
    try:
        print(find_soffice())
    except SofficeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    print(f"AF_UNIX available: {_af_unix_available()}")
    lib = _shim_library_path()
    print(f"Shim library: {lib if lib else '(not built — build.sh will compile on demand)'}")

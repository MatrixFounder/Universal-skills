"""Tests for the LD_PRELOAD / DYLD_INSERT AF_UNIX shim.

This file has TWO distinct test classes with deliberately different names:

1. ``TestShimInterceptionContract`` — what the shim positively DOES.
   It intercepts `socket(AF_UNIX)` + `bind` + `listen` + `accept`,
   enabling `bind()` to a nonexistent filesystem path to succeed.
   This is the condition LibreOffice's startup self-check needs, so
   headless single-process conversions work in AF_UNIX-blocked
   sandboxes.

2. ``TestShimCrossProcessIPCLimitation`` — what the shim deliberately
   does NOT do. It does not bridge AF_UNIX traffic between a parent
   process that `bind`+`listen`+`accept`s and a child process that
   `connect`s to the same sun_path. Each `socket()` call yields an
   isolated `socketpair()` with no shared registry, so cross-process
   writes are silently dropped. This test PASSES when the limitation
   holds (i.e. the shim correctly matches its documented narrow
   scope). It would FAIL if someone ever retroactively claimed to
   have implemented full IPC emulation without updating documentation.

The previous single ``TestShim`` class was renamed to remove the
implication that a green result means "shim works for real IPC".

Run:
    cd skills/docx/scripts
    ./.venv/bin/python -m unittest office.tests.test_shim
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent
sys.path.insert(0, str(SCRIPTS))

from _soffice import _shim_library_path  # noqa: E402


PROBE_BIND_C = r"""
/* Probe 1: bind() to a nonexistent filesystem path.
 *
 * Without shim: socket() succeeds, bind() fails (ENOENT / EACCES).
 * With shim:    all three calls return 0, fd is a socketpair[0].
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <sys/socket.h>
#include <sys/un.h>

int main(void) {
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) { fprintf(stderr, "socket fail: %s\n", strerror(errno)); return 1; }

    struct sockaddr_un a; memset(&a, 0, sizeof(a));
    a.sun_family = AF_UNIX;
    strncpy(a.sun_path, "/nonexistent-does-not-exist/probe.sock", sizeof(a.sun_path) - 1);

    if (bind(fd, (struct sockaddr*)&a, sizeof(a)) < 0) {
        fprintf(stderr, "bind fail: %s\n", strerror(errno)); return 2;
    }
    if (listen(fd, 1) < 0) {
        fprintf(stderr, "listen fail: %s\n", strerror(errno)); return 3;
    }
    printf("OK fd=%d\n", fd);
    close(fd);
    return 0;
}
"""


PROBE_IPC_C = r"""
/* Probe 2: fork-based cross-process IPC via a "shared" AF_UNIX path.
 *
 * Parent bind+listen+accept, child connect+write. The parent tries to
 * read what the child wrote. In a WORKING AF_UNIX setup this would
 * print "PARENT RECEIVED: hello".
 *
 * With our shim: parent's socket is a socketpair, and the child's
 * `socket(AF_UNIX)` creates a SEPARATE, unrelated socketpair. The
 * child's write therefore goes into its own private pair and the
 * parent's read returns 0 (EOF) or times out. We exit non-zero to
 * signal "IPC did NOT work as a real AF_UNIX would".
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>

int main(void) {
    int listen_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (listen_fd < 0) { perror("socket"); return 1; }
    struct sockaddr_un a; memset(&a, 0, sizeof(a));
    a.sun_family = AF_UNIX;
    strncpy(a.sun_path, "/nonexistent/lo-shim-probe.sock", sizeof(a.sun_path) - 1);
    if (bind(listen_fd, (struct sockaddr*)&a, sizeof(a)) < 0) { perror("bind"); return 2; }
    if (listen(listen_fd, 1) < 0) { perror("listen"); return 3; }

    pid_t pid = fork();
    if (pid == 0) {
        sleep(1);
        int c = socket(AF_UNIX, SOCK_STREAM, 0);
        if (c < 0) return 20;
        if (connect(c, (struct sockaddr*)&a, sizeof(a)) < 0) return 21;
        write(c, "hello", 5);
        close(c);
        _exit(0);
    }
    alarm(3);
    int ac = accept(listen_fd, NULL, NULL);
    if (ac < 0) { perror("accept"); return 10; }
    char buf[32] = {0};
    ssize_t n = read(ac, buf, sizeof(buf) - 1);
    int st; waitpid(pid, &st, 0);
    if (n <= 0) {
        fprintf(stderr, "parent got no data from child (n=%zd) — shim does NOT provide cross-process IPC\n", n);
        return 11;
    }
    printf("PARENT RECEIVED: %s\n", buf);
    return 0;
}
"""


def _compile(src_text: str, out_path: Path, cc: str = "cc") -> Path:
    src = out_path.with_suffix(".c")
    src.write_text(src_text, encoding="utf-8")
    subprocess.run([cc, "-O2", "-o", str(out_path), str(src)], check=True)
    return out_path


def _env_with_shim(shim: Path) -> dict[str, str]:
    env = os.environ.copy()
    if platform.system() == "Linux":
        env["LD_PRELOAD"] = str(shim)
    else:
        env["DYLD_INSERT_LIBRARIES"] = str(shim)
        env["DYLD_FORCE_FLAT_NAMESPACE"] = "1"
    return env


def _env_without_shim() -> dict[str, str]:
    return {k: v for k, v in os.environ.items()
            if k not in ("LD_PRELOAD", "DYLD_INSERT_LIBRARIES")}


@unittest.skipIf(platform.system() not in ("Linux", "Darwin"), "shim is Linux/macOS only")
class TestShimInterceptionContract(unittest.TestCase):
    """What the shim positively does: socket/bind/listen succeed on a
    path that would otherwise fail. This matches the scope documented
    in lo_socket_shim.c and is sufficient for LibreOffice's headless
    single-process conversions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="shim-contract-"))
        cc = os.environ.get("CC", "cc")
        if subprocess.call(["which", cc], stdout=subprocess.DEVNULL) != 0:
            raise unittest.SkipTest(f"compiler '{cc}' not available")
        cls.probe = _compile(PROBE_BIND_C, cls.tmp / "probe_bind", cc)
        cls.shim = _shim_library_path()
        if cls.shim is None:
            raise unittest.SkipTest("shim library could not be built on this host")

    def test_without_shim_bind_fails_on_nonexistent_path(self) -> None:
        r = subprocess.run([str(self.probe)], env=_env_without_shim(),
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0,
                            f"bind to nonexistent path unexpectedly succeeded without shim: {r.stdout}")

    def test_with_shim_bind_listen_accept_all_succeed(self) -> None:
        r = subprocess.run([str(self.probe)], env=_env_with_shim(self.shim),
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         f"probe failed with shim: stdout={r.stdout!r} stderr={r.stderr!r}")
        self.assertIn("OK fd=", r.stdout)


@unittest.skipIf(platform.system() not in ("Linux", "Darwin"), "shim is Linux/macOS only")
class TestShimCrossProcessIPCLimitation(unittest.TestCase):
    """What the shim deliberately does NOT do. Locking in the
    documented limitation: the shim does NOT relay AF_UNIX traffic
    between processes.

    This test PASSES when the IPC probe fails (the expected limitation
    behaviour). If the test ever starts failing, it means someone has
    silently made the shim bridge IPC — documentation and claims must
    be updated to match.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="shim-ipc-"))
        cc = os.environ.get("CC", "cc")
        if subprocess.call(["which", cc], stdout=subprocess.DEVNULL) != 0:
            raise unittest.SkipTest(f"compiler '{cc}' not available")
        cls.probe = _compile(PROBE_IPC_C, cls.tmp / "probe_ipc", cc)
        cls.shim = _shim_library_path()
        if cls.shim is None:
            raise unittest.SkipTest("shim library could not be built on this host")

    def test_cross_process_ipc_does_not_work_with_shim(self) -> None:
        """Parent should NOT receive child's write — if it does, the
        shim has silently been upgraded beyond its documented scope
        and this test must be revisited along with the shim docs."""
        r = subprocess.run(
            [str(self.probe)],
            env=_env_with_shim(self.shim),
            capture_output=True, text=True,
            timeout=10,
        )
        # Expect non-zero (parent saw EOF or timeout) OR explicit
        # "no data" stderr message. "PARENT RECEIVED" in stdout would
        # mean IPC succeeded — that is the regression we lock out.
        self.assertNotIn(
            "PARENT RECEIVED",
            r.stdout,
            "Shim is bridging cross-process IPC — this exceeds documented "
            "scope. Update lo_socket_shim.c comment and test_shim.md to "
            "reflect the new capability, then remove this test.",
        )


if __name__ == "__main__":
    unittest.main()

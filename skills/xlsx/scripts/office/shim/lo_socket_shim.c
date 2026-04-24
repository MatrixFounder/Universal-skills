/*
 * lo_socket_shim.c — LD_PRELOAD / DYLD_INSERT_LIBRARIES shim that lets
 * LibreOffice *start* inside sandboxes that reject AF_UNIX sockets.
 *
 * SCOPE (read this carefully)
 * ---------------------------
 * This shim makes `socket(AF_UNIX, ...)`, `bind`, `listen`, `connect`,
 * `accept`, `close` on AF_UNIX paths return success without touching
 * the filesystem. It does NOT implement real AF_UNIX IPC semantics.
 *
 * Concretely it solves: "LibreOffice refuses to start because its
 * self-check calls `socket(AF_UNIX, SOCK_STREAM, 0)` and the sandbox
 * returns EACCES". With the shim the startup self-check succeeds, and
 * `soffice --headless --convert-to pdf ...` proceeds through its
 * single-process document-conversion pipeline.
 *
 * It does NOT solve: "LibreOffice's parent process needs to hand data
 * to a spawned worker via AF_UNIX". The shim creates an *independent*
 * `socketpair()` per `socket()` call — there is no global path→fd
 * registry, so a `connect(path)` in a child process cannot reach a
 * `bind(path)` in the parent. Workers run in isolation; any data the
 * worker writes goes into its own private pair and is never read.
 *
 * Verification: `scripts/office/tests/test_shim.py` has the
 * interception contract tests AND an explicit xfail-style test
 * (`TestShimCrossProcessIPCLimitation`) that locks this limitation
 * in so future maintainers don't accidentally claim the shim "works"
 * for real IPC.
 *
 * If LibreOffice's sandboxed use case requires real AF_UNIX IPC (any
 * multi-process UNO service scenario), this shim is NOT sufficient.
 * Prefer one of:
 *   1. Docker without seccomp AF_UNIX denial
 *      (remove `SCMP_ACT_ERRNO` on `socket` syscall for domain==AF_UNIX)
 *   2. nsjail with `--disable_clone_newnet` + AF_UNIX allowed in its
 *      seccomp profile
 *   3. A proper AF_UNIX emulation shim (not provided here) that uses
 *      shared memory + SCM_RIGHTS to broker fds across processes.
 *
 * Intercept list
 * --------------
 *   - socket(AF_UNIX, ...)                  -> socketpair(); return pair[0]
 *   - bind(shim_fd, sockaddr_un, ...)       -> success (no filesystem)
 *   - listen(shim_fd, ...)                  -> success (pair is ready)
 *   - connect(shim_fd, sockaddr_un, ...)    -> success
 *   - accept(shim_fd, ...)                  -> return peer fd once; next call -> EAGAIN
 *
 * Anything other than AF_UNIX is passed through to the real libc call
 * untouched.
 *
 * This is the publicly-known "faketime / fakechroot / similar"
 * pattern — see libfaketime, fakechroot, LD_PRELOAD trick literature.
 * No Anthropic code is used.
 *
 * Build
 * -----
 *   Linux:   gcc -shared -fPIC -O2 -o liblo_socket_shim.so lo_socket_shim.c -ldl
 *   macOS:   clang -dynamiclib -O2 -o liblo_socket_shim.dylib lo_socket_shim.c
 *
 * scripts/office/shim/build.sh wraps both.
 *
 * Use
 * ---
 *   Linux:  LD_PRELOAD=path/to/liblo_socket_shim.so soffice --headless ...
 *   macOS:  DYLD_INSERT_LIBRARIES=path/to/liblo_socket_shim.dylib \
 *           DYLD_FORCE_FLAT_NAMESPACE=1 soffice --headless ...
 *
 * _soffice.py::run() applies the right env vars automatically when it
 * detects AF_UNIX is blocked in the current environment.
 */

#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <fcntl.h>

/* SOCK_CLOEXEC is Linux-only; macOS exposes the same semantics via
 * fcntl(F_SETFD, FD_CLOEXEC). Define a zero fallback so the bit-mask
 * strip below compiles cleanly on both platforms. */
#ifndef SOCK_CLOEXEC
#  define SOCK_CLOEXEC 0
#endif
#ifndef SOCK_NONBLOCK
#  define SOCK_NONBLOCK 0
#endif

/* Track file descriptors that we created via socketpair() so our
 * subsequent bind/listen/connect/accept calls only activate for them.
 * Real OS fds from other socket types pass through unchanged.
 *
 * Thread safety
 * -------------
 * LibreOffice uses worker threads (UNO service model). Two threads
 * can race on `shim_claim` / `shim_release` without explicit
 * synchronisation. We use C11 atomic `__atomic_*` intrinsics — they
 * are supported by both GCC and Clang on Linux and macOS and require
 * no extra link flags. Each `shim_fd_peer[fd]` slot is an atomic int;
 * claim/release are single-word stores and reads are acquire/release
 * ordered so a concurrent claim on fd X and lookup on fd X cannot
 * observe a half-written value.
 *
 * Semantics
 * ---------
 * `shim_fd_peer[fd]` encodes two pieces of information:
 *   0                : fd is NOT shim-owned (pass-through)
 *   peer_fd + 1      : fd is shim-owned; the socketpair's other end is peer_fd
 * The +1 offset lets us reserve 0 as "not ours" even though peer=0
 * (stdin) is a theoretically valid fd number from socketpair(). (Unix
 * never hands out fd 0 from socket(), but the offset is defensive.)
 */
#define SHIM_MAX_FDS 4096
static int shim_fd_peer[SHIM_MAX_FDS]; /* peer_fd + 1, or 0 = not ours */

static int shim_verbose(void) {
    const char *v = getenv("LO_SHIM_VERBOSE");
    return v && *v && *v != '0';
}

static void shim_log(const char *fmt, ...) {
    if (!shim_verbose()) return;
    va_list ap;
    va_start(ap, fmt);
    fputs("[lo_shim] ", stderr);
    vfprintf(stderr, fmt, ap);
    fputc('\n', stderr);
    va_end(ap);
}

static int shim_owns(int fd) {
    if (fd < 0 || fd >= SHIM_MAX_FDS) return 0;
    return __atomic_load_n(&shim_fd_peer[fd], __ATOMIC_ACQUIRE) != 0;
}

static void shim_claim(int fd, int peer) {
    if (fd < 0 || fd >= SHIM_MAX_FDS) return;
    __atomic_store_n(&shim_fd_peer[fd], peer + 1, __ATOMIC_RELEASE);
}

/* Atomically swap to 0 and return the previous peer (or -1 if not ours).
 * Ensures exactly one caller retrieves the peer in races between
 * close() and one-shot accept(). */
static int shim_release_swap(int fd) {
    if (fd < 0 || fd >= SHIM_MAX_FDS) return -1;
    int v = __atomic_exchange_n(&shim_fd_peer[fd], 0, __ATOMIC_ACQ_REL);
    if (!v) return -1;
    return v - 1;
}

/* ---------- real-symbol lookups (Linux dlsym path) ---------- */

#if defined(__APPLE__)
/* macOS: DYLD __interpose, no dlsym round-trip. */
typedef int (*socket_fn)(int, int, int);
typedef int (*bind_fn)(int, const struct sockaddr *, socklen_t);
typedef int (*listen_fn)(int, int);
typedef int (*connect_fn)(int, const struct sockaddr *, socklen_t);
typedef int (*accept_fn)(int, struct sockaddr *, socklen_t *);
typedef int (*close_fn)(int);

int shim_socket(int domain, int type, int proto);
int shim_bind(int fd, const struct sockaddr *addr, socklen_t len);
int shim_listen(int fd, int backlog);
int shim_connect(int fd, const struct sockaddr *addr, socklen_t len);
int shim_accept(int fd, struct sockaddr *addr, socklen_t *len);
int shim_close(int fd);

/* DYLD __interpose macro per dyld-interposing manual. */
#define DYLD_INTERPOSE(_replacment, _replacee) \
    __attribute__((used)) static struct { \
        const void *replacement; \
        const void *replacee; \
    } _interpose_##_replacee \
        __attribute__((section("__DATA,__interpose"))) = { \
            (const void *)(unsigned long)&_replacment, \
            (const void *)(unsigned long)&_replacee \
        };

DYLD_INTERPOSE(shim_socket,  socket)
DYLD_INTERPOSE(shim_bind,    bind)
DYLD_INTERPOSE(shim_listen,  listen)
DYLD_INTERPOSE(shim_connect, connect)
DYLD_INTERPOSE(shim_accept,  accept)
DYLD_INTERPOSE(shim_close,   close)

#define REAL(fn, ...)   fn(__VA_ARGS__)
#define SHIMNAME(fn)    shim_##fn

#else
/* Linux: dlsym(RTLD_NEXT, ...). */
static int (*real_socket)(int, int, int)                            = NULL;
static int (*real_bind)(int, const struct sockaddr *, socklen_t)    = NULL;
static int (*real_listen)(int, int)                                 = NULL;
static int (*real_connect)(int, const struct sockaddr *, socklen_t) = NULL;
static int (*real_accept)(int, struct sockaddr *, socklen_t *)      = NULL;
static int (*real_close)(int)                                       = NULL;

static void shim_init_once(void) {
    if (real_socket) return;
    real_socket  = dlsym(RTLD_NEXT, "socket");
    real_bind    = dlsym(RTLD_NEXT, "bind");
    real_listen  = dlsym(RTLD_NEXT, "listen");
    real_connect = dlsym(RTLD_NEXT, "connect");
    real_accept  = dlsym(RTLD_NEXT, "accept");
    real_close   = dlsym(RTLD_NEXT, "close");
}

#define REAL(fn, ...)  (shim_init_once(), real_##fn(__VA_ARGS__))
#define SHIMNAME(fn)   fn
#endif

/* ---------- intercepted entry points ---------- */

int SHIMNAME(socket)(int domain, int type, int proto) {
    if (domain != AF_UNIX) {
        return REAL(socket, domain, type, proto);
    }
    int pair[2];
    if (socketpair(AF_UNIX, type & ~SOCK_CLOEXEC, 0, pair) != 0) {
        /* AF_UNIX itself blocked for socketpair — last resort, try
         * AF_LOCAL which is the same protocol family on most systems. */
        if (socketpair(AF_LOCAL, type & ~SOCK_CLOEXEC, 0, pair) != 0) {
            shim_log("socketpair fallback failed: %s", strerror(errno));
            return -1;
        }
    }
    if (type & SOCK_CLOEXEC) {
        fcntl(pair[0], F_SETFD, FD_CLOEXEC);
        fcntl(pair[1], F_SETFD, FD_CLOEXEC);
    }
    shim_claim(pair[0], pair[1]);
    shim_log("socket(AF_UNIX,%d,%d) -> fd %d (peer %d)", type, proto, pair[0], pair[1]);
    return pair[0];
}

int SHIMNAME(bind)(int fd, const struct sockaddr *addr, socklen_t len) {
    if (shim_owns(fd)) {
        /* No filesystem binding needed — socketpair is already usable. */
        shim_log("bind(%d, ...) -> 0 (shim)", fd);
        return 0;
    }
    return REAL(bind, fd, addr, len);
}

int SHIMNAME(listen)(int fd, int backlog) {
    if (shim_owns(fd)) {
        shim_log("listen(%d, %d) -> 0 (shim)", fd, backlog);
        return 0;
    }
    return REAL(listen, fd, backlog);
}

int SHIMNAME(connect)(int fd, const struct sockaddr *addr, socklen_t len) {
    if (shim_owns(fd)) {
        shim_log("connect(%d, ...) -> 0 (shim)", fd);
        return 0;
    }
    return REAL(connect, fd, addr, len);
}

int SHIMNAME(accept)(int fd, struct sockaddr *addr, socklen_t *len) {
    if (shim_owns(fd)) {
        /* One-shot accept semantics: hand out the peer exactly once,
         * then subsequent accepts on the same listener return EAGAIN
         * (as if the listener were non-blocking and has no pending
         * connection). This prevents the FD-leak class of bug where a
         * caller that loops accept() would otherwise consume one FD
         * per iteration until RLIMIT_NOFILE. The "atomic exchange to
         * zero" ensures only one thread wins the race.
         *
         * LibreOffice's typical startup self-check accepts once then
         * moves on, which is exactly the case we support. If the real
         * workload ever needs multi-accept, the `_`-branch in
         * soffice's code reports a clear EAGAIN rather than silent
         * starvation. */
        int peer = shim_release_swap(fd);
        if (peer < 0) {
            errno = EAGAIN;
            return -1;
        }
        if (addr && len) {
            memset(addr, 0, *len);
            if (*len >= sizeof(sa_family_t)) {
                ((struct sockaddr *)addr)->sa_family = AF_UNIX;
            }
        }
        shim_log("accept(%d) -> fd %d (shim, one-shot, peer consumed)", fd, peer);
        return peer;
    }
    return REAL(accept, fd, addr, len);
}

int SHIMNAME(close)(int fd) {
    if (shim_owns(fd)) {
        /* Atomically drop the slot and retrieve the peer in one step
         * so a concurrent accept() doesn't race us to claim the peer. */
        int peer = shim_release_swap(fd);
        if (peer >= 0) {
            /* Close the peer so the pair is fully released. If accept
             * already ran and consumed the peer, shim_release_swap
             * returns -1 and we simply fall through to close the
             * caller's fd. */
            REAL(close, peer);
        }
    }
    return REAL(close, fd);
}

# LD_PRELOAD shim — scope, limitations, and real-sandbox validation

## Honest scope (read first)

The shim makes `socket(AF_UNIX, ...)`, `bind`, `listen`, `connect`,
`accept`, `close` on AF_UNIX paths return success without touching the
filesystem. It enables LibreOffice to **start** inside sandboxes that
reject `socket(AF_UNIX, ...)` at the seccomp layer.

It does **NOT** provide cross-process AF_UNIX IPC. Each `socket()`
intercept creates an independent `socketpair()`; there is no global
path→fd registry, so a `connect()` in a child process cannot reach a
`bind()` in the parent. This is an intentional simplification locked
in by `test_shim.py::TestShimCrossProcessIPCLimitation`. If your
LibreOffice use case spawns worker processes that need real IPC via
AF_UNIX, the shim is insufficient — grant AF_UNIX in the sandbox
policy instead (see "When the shim is NOT enough" below).

## What passes with the shim

- `soffice --headless --convert-to pdf INPUT.docx`
- `soffice --headless --convert-to xlsx INPUT.xlsx`
- Any single-process headless conversion that does not spawn
  AF_UNIX-based worker IPC.

## What the shim does NOT fix

- Full UNO service activation with worker-pool IPC
- D-Bus session bus access
- X11 display sockets

For those, the sandbox must genuinely permit AF_UNIX.

---

`test_shim.py` covers the unit-level contract: the shim intercepts the
right syscalls and its socketpair()-backed fds bypass filesystem paths.
The **full integration test** — LibreOffice actually starts inside a
seccomp-tightened sandbox that rejects `socket(AF_UNIX, ...)` — cannot
run on a normal desktop machine because AF_UNIX is permitted there.

This document records the procedure for testing on Linux with an
actual AF_UNIX-denying sandbox.

## Option 1 — nsjail (recommended)

[`nsjail`](https://github.com/google/nsjail) supports fine-grained
seccomp filters:

```bash
# 1. Install nsjail (apt install nsjail on recent Debian, or build from source).
# 2. Build the shim for Linux inside a matching container:
docker run --rm -v $PWD:/w -w /w debian:stable-slim bash -c '
    apt update -qq && apt install -y gcc libc6-dev >/dev/null
    bash skills/docx/scripts/office/shim/build.sh
'
# The .so lands in skills/docx/scripts/office/shim/liblo_socket_shim.so

# 3. Run LibreOffice with a seccomp profile that denies AF_UNIX:
cat > /tmp/nsjail.cfg <<'EOF'
name: "libreoffice-afunix-denied"
mode: ONCE
clone_newnet: true            # own netns — no AF_UNIX paths on disk
seccomp_string: "ERRNO(1) { socket } DEFAULT ALLOW"
EOF

# Without shim: soffice should fail to start.
nsjail --config /tmp/nsjail.cfg -- soffice --headless --version
# Expect: exit code != 0, "socket: Operation not permitted" in stderr.

# With shim: soffice starts.
nsjail --config /tmp/nsjail.cfg \
    -E LD_PRELOAD=/path/to/liblo_socket_shim.so \
    -- soffice --headless --version
# Expect: exit 0, "LibreOffice X.Y" printed.
```

## Option 2 — Docker with --security-opt seccomp=profile.json

```bash
# profile.json: drop AF_UNIX from the socket whitelist
cat > /tmp/deny-af-unix.json <<'EOF'
{ "defaultAction": "SCMP_ACT_ALLOW",
  "syscalls": [{ "names": ["socket"], "action": "SCMP_ACT_ERRNO",
                 "args": [{ "index": 0, "value": 1, "op": "SCMP_CMP_EQ" }]}] }
EOF

docker run --rm \
    --security-opt seccomp=/tmp/deny-af-unix.json \
    -v $PWD:/w -w /w \
    -e LD_PRELOAD=/w/skills/docx/scripts/office/shim/liblo_socket_shim.so \
    libreoffice/main:latest \
    soffice --headless --version
```

Without `-e LD_PRELOAD=...` the command fails; with it LibreOffice
starts.

## Option 3 — CI check (GitHub Actions)

Not yet wired up. If useful, add a workflow that runs option 1 on
Linux `ubuntu-latest` with a pre-built nsjail binary. Until then the
shim's existence is validated by `test_shim.py` (unit level) and by
`_soffice.py::_af_unix_available()` (detection contract).

## When does the shim NOT suffice?

- LibreOffice also uses D-Bus (`AF_UNIX` abstract namespace) and X11
  Unix sockets. If the sandbox blocks ALL `connect(AF_UNIX, ...)` at a
  lower layer than `socket()`, the shim's `connect` intercept handles
  it for shim-owned fds, but real D-Bus sockets (not created via
  `socket(AF_UNIX, ...)` inside soffice — inherited from parent) may
  still fail. In practice `--headless --norestore --nologo --nodefault`
  avoids D-Bus, and `SAL_USE_VCLPLUGIN=svp` avoids X11.
- Memory-map sockets (`mmap` on shm-backed Unix sockets) are not
  intercepted. LibreOffice does not use these in the headless path.

These edge cases are documented here so future maintainers know what
to add if a new sandbox profile breaks.

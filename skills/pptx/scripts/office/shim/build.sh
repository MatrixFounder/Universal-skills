#!/usr/bin/env bash
# Compile lo_socket_shim.c for the current platform.
#
# Output:
#   liblo_socket_shim.so      (Linux)
#   liblo_socket_shim.dylib   (macOS)
#
# Called on demand by _soffice.py when it detects an AF_UNIX-blocked
# sandbox. Also runnable by hand for pre-seeded container images:
#   bash skills/docx/scripts/office/shim/build.sh
#
# Idempotent; skips rebuild when the .so/.dylib is newer than the .c.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

SRC="lo_socket_shim.c"

case "$(uname -s)" in
    Linux)
        OUT="liblo_socket_shim.so"
        CC=${CC:-gcc}
        CFLAGS=(-shared -fPIC -O2 -Wall -fvisibility=default)
        LDFLAGS=(-ldl)
        ;;
    Darwin)
        OUT="liblo_socket_shim.dylib"
        CC=${CC:-clang}
        CFLAGS=(-dynamiclib -O2 -Wall -fvisibility=default)
        LDFLAGS=()
        ;;
    *)
        echo "[shim/build.sh] ERROR: unsupported platform $(uname -s)" >&2
        exit 1
        ;;
esac

if [ -f "$OUT" ] && [ "$OUT" -nt "$SRC" ]; then
    echo "[shim/build.sh] up-to-date: $HERE/$OUT"
    exit 0
fi

if ! command -v "$CC" >/dev/null 2>&1; then
    echo "[shim/build.sh] ERROR: compiler '$CC' not found. Install Xcode CLT (macOS) or build-essential (Debian)." >&2
    exit 1
fi

echo "[shim/build.sh] compiling $SRC -> $OUT using $CC ..."
# set -u treats ${arr[@]} of an empty array as unbound on bash<4.4; use
# ${arr[@]+"${arr[@]}"} idiom to expand safely.
"$CC" "${CFLAGS[@]}" -o "$OUT" "$SRC" ${LDFLAGS[@]+"${LDFLAGS[@]}"}
echo "[shim/build.sh] OK: $HERE/$OUT ($(stat -f%z "$OUT" 2>/dev/null || stat -c%s "$OUT") bytes)"

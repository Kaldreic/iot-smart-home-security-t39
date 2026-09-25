#!/usr/bin/env bash
# Shared part of the harness builds, sourced by the build-*.sh scripts: the pinned toolchain image, the pinned
# Zephyr commits, the pinned SDK with its checksum, and build_harness. A script sets T (the test file taken from
# the fix commit), GUARD (the controller file restored from the vulnerable commit), TESTDIR, PATCH (a patch it
# has copied into $WS), BUILD_DIR, optionally LINK_FLAGS and PRE_CMAKE (a snippet run after the patch), and
# VERIFY, a snippet run after the build with BIN set to the testbinary; then it calls build_harness.

IMG="ghcr.io/zephyrproject-rtos/zephyr-build@sha256:a9b3f2228810bff6f3cb3a15450aa55d5b943803e26e6f17db8c5a781e3f69fe"
VULN="4ae207ccac8e763c4d81ea88e397e17f294169ba"   # the vulnerable controller (the parent of the fix commit)
FIX="e91b3e3638765680c092d583023a92e719e7b8c4"    # the fix commit; its repro tests are the harness baseline
SDK_URL="https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v0.16.5/zephyr-sdk-0.16.5_linux-x86_64_minimal.tar.xz"
SDK_SHA256="933ab6b4cd78dccf8fe0cf59d1b626efc309008408eaf848173c70360f848ee1"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"                 # code/src/emulation/zephyr-targets/
# shellcheck disable=SC2034  # used by the sourcing scripts
WS_DEFAULT="$(cd "$HERE/../../.." && pwd)/upstream/zephyr-cve"          # code/upstream/zephyr-cve

# Everything the inner script needs travels as environment variables, so no quoting is spliced into it.
build_harness() {
  export VULN FIX SDK_URL SDK_SHA256 T GUARD TESTDIR PATCH BUILD_DIR VERIFY
  export LINK_FLAGS="${LINK_FLAGS:-}" PRE_CMAKE="${PRE_CMAKE:-}"
  docker run --rm -v "$WS:/work" -w /work -e HOME=/work --user "$(id -u):$(id -g)" \
    -e ZEPHYR_SDK_INSTALL_DIR=/work/zephyr-sdk-0.16.5 \
    -e VULN -e FIX -e SDK_URL -e SDK_SHA256 -e T -e GUARD -e TESTDIR -e PATCH -e BUILD_DIR \
    -e LINK_FLAGS -e PRE_CMAKE -e VERIFY "$IMG" bash -lc '
set -e
if [ ! -d zephyr/.git ]; then git init -q zephyr && (cd zephyr && git remote add origin https://github.com/zephyrproject-rtos/zephyr.git); fi
cd zephyr
rm -f .git/shallow.lock .git/index.lock
git fetch -q --depth 1 origin "$VULN" && git checkout -q -f "$VULN"
git fetch -q --depth 1 origin "$FIX"
git checkout -q -f "$VULN" -- "$GUARD"                     # the vulnerable controller file
[ "$(git rev-parse HEAD)" = "$VULN" ] || { echo "GUARD: not on the vulnerable commit"; exit 1; }
git show "$FIX:$T" > "$T"                                  # the repro tests of the fix commit: the harness baseline
git apply "/work/$PATCH"
eval "$PRE_CMAKE"
cd /work
if [ ! -d zephyr-sdk-0.16.5 ]; then
  wget -q "$SDK_URL" -O sdk.tar.xz
  echo "$SDK_SHA256  sdk.tar.xz" | sha256sum -c - >/dev/null
  tar xf sdk.tar.xz && rm -f sdk.tar.xz
fi
export ZEPHYR_BASE=/work/zephyr
rm -rf "$BUILD_DIR"
extra=()
if [ -n "$LINK_FLAGS" ]; then extra=(-DCMAKE_EXE_LINKER_FLAGS="$LINK_FLAGS"); fi
cmake -B "$BUILD_DIR" -GNinja -DBOARD=unit_testing -DZEPHYR_BASE="$ZEPHYR_BASE" \
  -DCONFIG_BT_GATT_CACHING=n -DZEPHYR_SDK_INSTALL_DIR=/work/zephyr-sdk-0.16.5 \
  "${extra[@]}" "$ZEPHYR_BASE/$TESTDIR" >/dev/null
ninja -C "$BUILD_DIR" >/dev/null                           # standalone: a pipe would mask its exit under set -e
BIN="/work/$BUILD_DIR/testbinary"
[ -x "$BIN" ] || { echo "build failed: no testbinary"; exit 1; }
eval "$VERIFY"
'
}

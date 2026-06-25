#!/usr/bin/env bash
# Bug D — build the SUBSET-selectable PHY-update doubled-IND assert oracle binary on the REAL
# vulnerable Zephyr LL controller, and verify its channel-OFF exhaustive sweep + true 2-minimal.
#
# The harness (patches/bugD-phy-window.patch) adds ONE ZTEST (test_bug_d) to the ctrl_phy_update suite; it is a
# NO-OP unless selected by env HARNESS_BUG=D (the native unit_testing binary runs the WHOLE suite -- no
# per-test CLI filter -- so selection is by getenv, the existing PROBE_ID pattern). HARNESS_SUBSET is a
# bitmask over the LL-PDU window so an external minimiser can drive a channel-OFF exhaustive sweep.
#
#   HARNESS_BUG=D  test_bug_d: confirmed PHY doubled-IND assert (morebugs.md). A genuine MULTI-PACKET
#             minimal (like Bug C). 5-bit window: bits0..2 = transparent (droppable) drained local
#             LE-Pings, bit3 = LL_PHY_UPDATE_IND #1, bit4 = LL_PHY_UPDATE_IND #2 (load-bearing). The
#             LL_PHY_REQ precondition (procedure start) is injected whenever any IND is present. A
#             SECOND IND while in WAIT_INSTANT desyncs the retained NTF rx node; at the instant pu_ntf
#             (ull_llcp_phy.c:437) hits LL_ASSERT(ntf) -> mocked bt_ctlr_assert_handle -> exit(-1).
#             Channel-OFF true 2-minimal = {IND1,IND2} = 24 (0x18). The assert emits its OWN message
#             (ASSERTION FAIL [ntf] @ ull_llcp_phy.c:437); no SIGFPE handler needed. Python rc 255 /
#             shell 255.
#
# -rdynamic is passed for symbol-rich dumps (parity with the other bug scripts); Bug D reproduces
# identically without it (the assert message is the artifact, not a backtrace).
#
# Leaves build-phy/testbinary as the Bug D subset-window binary. SEPARATE build dir; /work/build and
# /work/build-multibug are left untouched. Idempotent. Re-uses the clone + SDK. Run: bash scripts/build-bugD.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"                # code/src/emulation/zephyr-targets/
EXP="$(cd "$HERE/../../.." && pwd)"                            # code/ (repo build root)
WS="${HARNESS_WS:-$EXP/upstream/zephyr-cve}"
IMG="ghcr.io/zephyrproject-rtos/zephyr-build@sha256:a9b3f2228810bff6f3cb3a15450aa55d5b943803e26e6f17db8c5a781e3f69fe"
VULN="4ae207ccac8e763c4d81ea88e397e17f294169ba"
FIX="e91b3e3638765680c092d583023a92e719e7b8c4"
T="tests/bluetooth/controller/ctrl_phy_update/src/main.c"
GUARD="subsys/bluetooth/controller/ll_sw/ull_llcp_phy.c"   # Bug D faulting TU (the LL_ASSERT @ :437)
TESTDIR="tests/bluetooth/controller/ctrl_phy_update"

mkdir -p "$WS"
cp "$HERE/patches/bugD-phy-window.patch" "$WS/bugD.patch"

docker run --rm -v "$WS:/work" -w /work -e HOME=/work --user "$(id -u):$(id -g)" \
  -e ZEPHYR_SDK_INSTALL_DIR=/work/zephyr-sdk-0.16.5 "$IMG" bash -lc '
set -e
VULN='"$VULN"'; FIX='"$FIX"'; T="'"$T"'"; GUARD="'"$GUARD"'"; TESTDIR="'"$TESTDIR"'"

# Clean checkout: VULN controller + FIX repro-tests baseline of the harness + apply the Bug D window.
if [ ! -d zephyr/.git ]; then git init -q zephyr && (cd zephyr && \
   git remote add origin https://github.com/zephyrproject-rtos/zephyr.git); fi
cd zephyr
rm -f .git/shallow.lock .git/index.lock
git fetch -q --depth 1 origin $VULN && git checkout -q -f $VULN
git fetch -q --depth 1 origin $FIX
# VULN guard => the controller TU is the VULNERABLE one. (For this baseline the FIX commit did not
# change the controller sources -- ull_llcp_phy.c is byte-identical at VULN and FIX -- so this is
# belt-and-suspenders; the bug lives in the VULN controller and the FIX *tests* simply do not
# exercise it. Our window does.)
git checkout -q -f $VULN -- $GUARD
[ "$(git rev-parse HEAD)" = "$VULN" ] || { echo "GUARD: not on VULN parent"; exit 1; }
git show $FIX:$T > $T                                    # FIX repro-tests baseline of the harness ...
git apply /work/bugD.patch                            # ... + the Bug D subset window

cd /work
if [ ! -d zephyr-sdk-0.16.5 ]; then
  wget -q https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v0.16.5/zephyr-sdk-0.16.5_linux-x86_64_minimal.tar.xz -O sdk.tar.xz
  tar xf sdk.tar.xz && rm -f sdk.tar.xz
fi
export ZEPHYR_BASE=/work/zephyr
rm -rf build-phy
cmake -B build-phy -GNinja -DBOARD=unit_testing -DZEPHYR_BASE="$ZEPHYR_BASE" \
  -DCONFIG_BT_GATT_CACHING=n -DZEPHYR_SDK_INSTALL_DIR=/work/zephyr-sdk-0.16.5 \
  -DCMAKE_EXE_LINKER_FLAGS="-rdynamic" \
  "$ZEPHYR_BASE/$TESTDIR" >/dev/null
# NB: "cmd | tail" would mask ninjas exit under set -e; keep ninja standalone.
ninja -C build-phy >/dev/null
BIN=/work/build-phy/testbinary
[ -x "$BIN" ] || { echo "build failed: no testbinary"; exit 1; }

# Helper: run one HARNESS_SUBSET; never abort under set -e (binary exits nonzero on crash AND on the
# pre-existing ztest pass/fail). Key on the exit code: D=255 (LL_ASSERT -> exit(-1)), else !=255.
run() { local m="$1" e; if HARNESS_BUG=D HARNESS_SUBSET="$m" "$BIN" >/dev/null 2>&1; then e=0; else e=$?; fi; echo "$e"; }

echo "### Bug D binary: build-phy/testbinary (/work/build, /work/build-multibug left untouched) ###"
echo "--- Bug D: channel-OFF exhaustive sweep (5-bit window) -> crash(255) <=> BOTH IND bits (0x18) ---"
cnt=0; bad=0
for m in $(seq 0 31); do
  e=$(run "$m")
  if [ "$e" = "255" ]; then cnt=$((cnt+1)); [ $((m & 24)) -ne 24 ] && bad=1; fi
done
echo "    crashing subsets = $cnt / 32 (expect 8 = supersets of {IND1,IND2}); all crashers hold both INDs: $([ $bad -eq 0 ] && echo YES || echo NO)"
echo "    true 2-minimal {IND1,IND2}=24 (0x18): exit=$(run 24) (expect 255)"
echo "    each 1-smaller subset benign: {IND1}=8 exit=$(run 8), {IND2}=16 exit=$(run 16) (expect non-255)"
echo "    decoy transparency (each decoy + both INDs still crashes): 0x19=$(run 25) 0x1A=$(run 26) 0x1C=$(run 28) all3+INDs 0x1F=$(run 31) (expect 255 each)"
echo "    decoys alone benign (never 255): 0x01=$(run 1) 0x07=$(run 7) empty=0=$(run 0)"
echo "    determinism (3x on 24): $(run 24) $(run 24) $(run 24)"

echo "### example dump (HARNESS_BUG=D HARNESS_SUBSET=24) — controller assert message ###"
HARNESS_BUG=D HARNESS_SUBSET=24 "$BIN" 2>&1 | grep -E "Running TESTSUITE phy_periph|ull_llcp_phy\.c:437"
'

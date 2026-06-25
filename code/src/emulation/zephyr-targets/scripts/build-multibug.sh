#!/usr/bin/env bash
# Build the TWO-BUG hardware-free oracle binary (ONE testbinary, TWO crash identities) on
# the REAL vulnerable Zephyr LL controller, and verify BOTH bugs' channel-OFF exhaustive sweeps.
#
# The harness (patches/multibug-harness.patch) adds two ZTESTs to the ctrl_conn_update suite; each is a NO-OP unless
# selected by env HARNESS_BUG (the native unit_testing binary runs the WHOLE suite -- no per-test CLI
# filter -- so selection is by getenv, the existing PROBE_ID pattern). HARNESS_SUBSET is a bitmask over
# each bug's LL-PDU window so an external minimiser can drive a channel-OFF exhaustive subset sweep.
#
#   HARNESS_BUG=A  test_bug_a: CVE-2024-4785 divide-by-zero -> SIGFPE. 8-PDU WIDE trigger-last window
#             (the wide trigger-last window): decoys window[0..6], interval=0
#             LL_CONNECTION_UPDATE_IND trigger window[7]. Channel-OFF true 1-minimal = {7} (bit7=128).
#             An in-test signal(SIGFPE,...) handler prints a real backtrace + "=== CRASH sig=SIGFPE ==="
#             to stderr then _exit(136). Shell exit 136 (Python returncode 136).
#   HARNESS_BUG=C  test_bug_c: a DISTINCT crash identity -- LL_ASSERT(ntf) @ ull_llcp_conn_upd.c:247
#             (cu_ntf) -> mocked bt_ctlr_assert_handle -> exit(-1). A genuine 2-PACKET minimal: a
#             peripheral local CPR driven to WAIT_INSTANT by IND#1, then a load-bearing IND#2 desyncs
#             the retained-node bookkeeping. Window: bits0..2 = transparent (droppable) drained local
#             LE-Pings, bit3 = IND#1, bit4 = IND#2. Channel-OFF true minimal = {IND1,IND2} = 24 (0x18).
#             Python returncode 255 / shell 255.
#
# -rdynamic is passed so backtrace_symbols_fd resolves the exported controller frames in Bug A's
# dump (notably ull_conn_update_parameters, the faulting divide site).
#
# Leaves build-multibug/testbinary as the two-bug binary. Uses a SEPARATE build dir; /work/build is
# left untouched. Idempotent. Re-uses the clone + SDK. Run: bash scripts/build-multibug.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"                # code/src/emulation/zephyr-targets/
EXP="$(cd "$HERE/../../.." && pwd)"                            # code/ (repo build root)
WS="${HARNESS_WS:-$EXP/upstream/zephyr-cve}"
IMG="ghcr.io/zephyrproject-rtos/zephyr-build@sha256:a9b3f2228810bff6f3cb3a15450aa55d5b943803e26e6f17db8c5a781e3f69fe"
VULN="4ae207ccac8e763c4d81ea88e397e17f294169ba"
FIX="e91b3e3638765680c092d583023a92e719e7b8c4"
T="tests/bluetooth/controller/ctrl_conn_update/src/main.c"
GUARD="subsys/bluetooth/controller/ll_sw/ull_llcp_conn_upd.c"
TESTDIR="tests/bluetooth/controller/ctrl_conn_update"

mkdir -p "$WS"
cp "$HERE/patches/multibug-harness.patch" "$WS/multibug.patch"

docker run --rm -v "$WS:/work" -w /work -e HOME=/work --user "$(id -u):$(id -g)" \
  -e ZEPHYR_SDK_INSTALL_DIR=/work/zephyr-sdk-0.16.5 "$IMG" bash -lc '
set -e
VULN='"$VULN"'; FIX='"$FIX"'; T="'"$T"'"; GUARD="'"$GUARD"'"; TESTDIR="'"$TESTDIR"'"

# Clean checkout: VULN guard + FIX repro-tests baseline + apply the multibug harness.
if [ ! -d zephyr/.git ]; then git init -q zephyr && (cd zephyr && \
   git remote add origin https://github.com/zephyrproject-rtos/zephyr.git); fi
cd zephyr
rm -f .git/shallow.lock .git/index.lock
git fetch -q --depth 1 origin $VULN && git checkout -q -f $VULN
git fetch -q --depth 1 origin $FIX
# VULN guard => the controller is the VULNERABLE one (this is what makes Bug A reproduce).
git checkout -q -f $VULN -- $GUARD
[ "$(git rev-parse HEAD)" = "$VULN" ] || { echo "GUARD: not on VULN parent"; exit 1; }
git show $FIX:$T > $T                                    # FIX repro-tests baseline ...
git apply /work/multibug.patch                        # ... + the two-bug harness

cd /work
if [ ! -d zephyr-sdk-0.16.5 ]; then
  wget -q https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v0.16.5/zephyr-sdk-0.16.5_linux-x86_64_minimal.tar.xz -O sdk.tar.xz
  tar xf sdk.tar.xz && rm -f sdk.tar.xz
fi
export ZEPHYR_BASE=/work/zephyr
rm -rf build-multibug
cmake -B build-multibug -GNinja -DBOARD=unit_testing -DZEPHYR_BASE="$ZEPHYR_BASE" \
  -DCONFIG_BT_GATT_CACHING=n -DZEPHYR_SDK_INSTALL_DIR=/work/zephyr-sdk-0.16.5 \
  -DCMAKE_EXE_LINKER_FLAGS="-rdynamic" \
  "$ZEPHYR_BASE/$TESTDIR" >/dev/null
# NB: "cmd | tail" would mask ninjas exit under set -e; keep ninja standalone.
ninja -C build-multibug >/dev/null
BIN=/work/build-multibug/testbinary
[ -x "$BIN" ] || { echo "build failed: no testbinary"; exit 1; }

# Helper: run one (HARNESS_BUG,HARNESS_SUBSET); never abort under set -e (binary exits nonzero on crash AND on
# the pre-existing ztest failures). Key on the exit code: A=136 (SIGFPE), C=255 (LL_ASSERT), else 1.
run() { local b="$1" m="$2" e; if HARNESS_BUG="$b" HARNESS_SUBSET="$m" "$BIN" >/dev/null 2>&1; then e=0; else e=$?; fi; echo "$e"; }

echo "### two-bug binary: build-multibug/testbinary (/work/build left untouched) ###"

echo "--- Bug A: channel-OFF exhaustive sweep (8-bit window) -> crash(136) <=> bit7 ---"
acnt=0; abad=0
for m in $(seq 0 255); do
  e=$(run A "$m")
  if [ "$e" = "136" ]; then acnt=$((acnt+1)); [ $((m & 128)) -eq 0 ] && abad=1; else [ $((m & 128)) -ne 0 ] && abad=1; fi
done
echo "    crashing subsets = $acnt / 256 (expect 128); crash<=>bit7 holds: $([ $abad -eq 0 ] && echo YES || echo NO)"
echo "    true 1-minimal {7}=128 alone: exit=$(run A 128) (expect 136);  empty=0: exit=$(run A 0) (expect 1)"
echo "    determinism (3x on 128): $(run A 128) $(run A 128) $(run A 128)"

echo "--- Bug C: channel-OFF exhaustive sweep (5-bit window) -> crash(255) <=> BOTH IND bits (0x18) ---"
ccnt=0; cbad=0
for m in $(seq 0 31); do
  e=$(run C "$m")
  if [ "$e" = "255" ]; then ccnt=$((ccnt+1)); [ $((m & 24)) -ne 24 ] && cbad=1; fi
done
echo "    crashing subsets = $ccnt / 32 (expect 8, = supersets of {IND1,IND2}); all crashers hold both INDs: $([ $cbad -eq 0 ] && echo YES || echo NO)"
echo "    true 2-minimal {IND1,IND2}=24: exit=$(run C 24) (expect 255)"
echo "    each 1-smaller subset benign: {IND1}=8 exit=$(run C 8), {IND2}=16 exit=$(run C 16) (expect 1,1)"
echo "    determinism (3x on 24): $(run C 24) $(run C 24) $(run C 24)"

echo "### example dumps ###"
echo "--- Bug A dump (HARNESS_BUG=A HARNESS_SUBSET=128) ---"
HARNESS_BUG=A HARNESS_SUBSET=128 "$BIN" 2>&1 | sed -n "/=== CRASH/,\$p" | grep -E "CRASH|ull_conn_update_parameters|ull_cp_run" | head
echo "--- Bug C dump (HARNESS_BUG=C HARNESS_SUBSET=24) ---"
HARNESS_BUG=C HARNESS_SUBSET=24 "$BIN" 2>&1 | grep -E "ull_llcp_conn_upd\.c:247"
'

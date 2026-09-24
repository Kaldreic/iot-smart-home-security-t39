#!/usr/bin/env bash
# Bug B — build the SUBSET-selectable CIS divide-by-zero oracle binary on the REAL
# vulnerable Zephyr LL controller, and verify its channel-OFF exhaustive sweep + true 1-minimal.
#
# The harness (patches/bugB-cis-window.patch) adds ONE ZTEST (test_bug_b) to the ctrl_cis_create suite; it is a
# NO-OP unless selected by env HARNESS_BUG=B (the native unit_testing binary runs the WHOLE suite -- no
# per-test CLI filter -- so selection is by getenv, the existing PROBE_ID pattern). HARNESS_SUBSET is a
# bitmask over the LL-PDU window so an external minimiser can drive a channel-OFF exhaustive sweep.
#
#   HARNESS_BUG=B  test_bug_b: confirmed CIS divide-by-zero. A SINGLE-PACKET minimal
#             (like Bug A). 8-bit WIDE window, trigger-LAST: bits0..3 = transparent (droppable)
#             drained local LE-Pings, bit7 (0x80) = the malformed LL_CIS_REQ trigger (iso_interval=0
#             AND conn_event_count=0). On accept, llcp_rp_cc_tx_rsp (ull_llcp_cc.c:177) divides by
#             iso_interval_us=0 -> SIGFPE. An in-test signal(SIGFPE,...) handler prints a real
#             backtrace + "=== CRASH sig=SIGFPE ===" to stderr then _exit(136). Channel-OFF true
#             1-minimal = {7} (bit7=128). Python returncode 136 / shell 136 (a CLEAN handler exit,
#             NOT a -8 signal death -- match returncode==136).
#
# -rdynamic is passed so backtrace_symbols_fd resolves the exported controller frames in the dump
# (the static faulting fn llcp_rp_cc_tx_rsp shows as a raw offset; the
# exported LLCP/CIS spine frames resolve by name). gdb (--cap-add SYS_PTRACE) anchors the exact site.
#
# Leaves build-cis/testbinary as the Bug B subset-window binary. SEPARATE build dir; /work/build and
# /work/build-multibug are left untouched. Idempotent. Re-uses the clone + SDK. Run: bash scripts/build-bugB.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"                # code/src/emulation/zephyr-targets/
EXP="$(cd "$HERE/../../.." && pwd)"                            # code/ (repo build root)
WS="${HARNESS_WS:-$EXP/upstream/zephyr-cve}"
IMG="ghcr.io/zephyrproject-rtos/zephyr-build@sha256:a9b3f2228810bff6f3cb3a15450aa55d5b943803e26e6f17db8c5a781e3f69fe"
VULN="4ae207ccac8e763c4d81ea88e397e17f294169ba"
FIX="e91b3e3638765680c092d583023a92e719e7b8c4"
T="tests/bluetooth/controller/ctrl_cis_create/src/main.c"
GUARD="subsys/bluetooth/controller/ll_sw/ull_llcp_cc.c"   # Bug B faulting TU (the DIV_ROUND_UP @ :177)
TESTDIR="tests/bluetooth/controller/ctrl_cis_create"

mkdir -p "$WS"
cp "$HERE/patches/bugB-cis-window.patch" "$WS/bugB.patch"

docker run --rm -v "$WS:/work" -w /work -e HOME=/work --user "$(id -u):$(id -g)" \
  -e ZEPHYR_SDK_INSTALL_DIR=/work/zephyr-sdk-0.16.5 "$IMG" bash -lc '
set -e
VULN='"$VULN"'; FIX='"$FIX"'; T="'"$T"'"; GUARD="'"$GUARD"'"; TESTDIR="'"$TESTDIR"'"

# Clean checkout: VULN controller + FIX repro-tests baseline of the harness + apply the Bug B window.
if [ ! -d zephyr/.git ]; then git init -q zephyr && (cd zephyr && \
   git remote add origin https://github.com/zephyrproject-rtos/zephyr.git); fi
cd zephyr
rm -f .git/shallow.lock .git/index.lock
git fetch -q --depth 1 origin $VULN && git checkout -q -f $VULN
git fetch -q --depth 1 origin $FIX
# VULN guard => the controller TU is the VULNERABLE one. (For this CVE-class baseline the FIX commit
# did not change the controller sources -- ull_llcp_cc.c is byte-identical at VULN and FIX -- so this
# is belt-and-suspenders; the bug lives in the VULN controller and the FIX *tests* simply do not
# exercise it. Our window does.)
git checkout -q -f $VULN -- $GUARD
[ "$(git rev-parse HEAD)" = "$VULN" ] || { echo "GUARD: not on VULN parent"; exit 1; }
git show $FIX:$T > $T                                    # FIX repro-tests baseline of the harness ...
git apply /work/bugB.patch                            # ... + the Bug B subset window

cd /work
if [ ! -d zephyr-sdk-0.16.5 ]; then
  wget -q https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v0.16.5/zephyr-sdk-0.16.5_linux-x86_64_minimal.tar.xz -O sdk.tar.xz
  tar xf sdk.tar.xz && rm -f sdk.tar.xz
fi
export ZEPHYR_BASE=/work/zephyr
rm -rf build-cis
cmake -B build-cis -GNinja -DBOARD=unit_testing -DZEPHYR_BASE="$ZEPHYR_BASE" \
  -DCONFIG_BT_GATT_CACHING=n -DZEPHYR_SDK_INSTALL_DIR=/work/zephyr-sdk-0.16.5 \
  -DCMAKE_EXE_LINKER_FLAGS="-rdynamic" \
  "$ZEPHYR_BASE/$TESTDIR" >/dev/null
# NB: "cmd | tail" would mask ninjas exit under set -e; keep ninja standalone.
ninja -C build-cis >/dev/null
BIN=/work/build-cis/testbinary
[ -x "$BIN" ] || { echo "build failed: no testbinary"; exit 1; }

# Helper: run one HARNESS_SUBSET; never abort under set -e (binary exits nonzero on crash AND on the
# pre-existing ztest pass/fail). Key on the exit code: B=136 (SIGFPE handler _exit), else !=136.
run() { local m="$1" e; if HARNESS_BUG=B HARNESS_SUBSET="$m" "$BIN" >/dev/null 2>&1; then e=0; else e=$?; fi; echo "$e"; }

echo "### Bug B binary: build-cis/testbinary (/work/build, /work/build-multibug left untouched) ###"
echo "--- Bug B: channel-OFF exhaustive sweep (8-bit window) -> crash(136) <=> bit7 (0x80) ---"
cnt=0; bad=0
for m in $(seq 0 255); do
  e=$(run "$m")
  if [ "$e" = "136" ]; then cnt=$((cnt+1)); [ $((m & 128)) -eq 0 ] && bad=1; else [ $((m & 128)) -ne 0 ] && bad=1; fi
done
echo "    crashing subsets = $cnt / 256 (expect 128 = the bit7-set half); crash<=>bit7 holds: $([ $bad -eq 0 ] && echo YES || echo NO)"
echo "    true 1-minimal {7}=128 alone: exit=$(run 128) (expect 136);  empty=0: exit=$(run 0) (no crash)"
echo "    decoy transparency (trigger+each decoy still crashes): 0x81=$(run 129) 0x82=$(run 130) 0x84=$(run 132) 0x88=$(run 136) all4+trig 0x8F=$(run 143) (expect 136 each)"
echo "    decoys alone benign (never 136): 0x01=$(run 1) 0x0F=$(run 15)"
echo "    determinism (3x on 128): $(run 128) $(run 128) $(run 128)"

echo "### example dump (HARNESS_BUG=B HARNESS_SUBSET=128) — SIGFPE handler backtrace ###"
HARNESS_BUG=B HARNESS_SUBSET=128 "$BIN" 2>&1 | sed -n "/=== CRASH/,\$p" | grep -E "CRASH|llcp_rp_cc_run|ull_cp_run|event_prepare" | head
'

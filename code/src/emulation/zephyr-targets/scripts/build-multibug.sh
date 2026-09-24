#!/usr/bin/env bash
# Build the two-bug oracle binary (one testbinary, two crash identities) on the vulnerable Zephyr LL
# controller and verify both bugs' channel-off exhaustive sweeps.
#
# The harness (patches/multibug-harness.patch) adds two ZTESTs to the ctrl_conn_update suite; each is a
# no-op unless selected by env HARNESS_BUG (the native unit_testing binary runs the whole suite, with no
# per-test CLI filter, so selection is by getenv -- the existing PROBE_ID pattern). HARNESS_SUBSET is a
# bitmask over each bug's LL-PDU window, for a channel-off exhaustive subset sweep.
#
#   HARNESS_BUG=A  test_bug_a: CVE-2024-4785 divide-by-zero -> SIGFPE. 8-PDU trigger-last window: decoys
#             window[0..6], interval=0 LL_CONNECTION_UPDATE_IND trigger window[7]. Channel-off true
#             1-minimal = {7} (bit7=128). An in-test signal(SIGFPE,...) handler prints a real backtrace
#             + "=== CRASH sig=SIGFPE ===" to stderr then _exit(136). Shell exit 136 (Python returncode 136).
#   HARNESS_BUG=C  test_bug_c: a distinct crash identity -- LL_ASSERT(ntf) @ ull_llcp_conn_upd.c:247
#             (cu_ntf) -> mocked bt_ctlr_assert_handle -> exit(-1). A 2-packet minimal: a peripheral local
#             CPR driven to WAIT_INSTANT by IND#1, then a load-bearing IND#2 desyncs the retained-node
#             bookkeeping. Window: bits0..2 = transparent (droppable) drained local LE-Pings, bit3 = IND#1,
#             bit4 = IND#2. Channel-off true minimal = {IND1,IND2} = 24 (0x18). Python returncode 255 / shell 255.
#
# -rdynamic lets backtrace_symbols_fd resolve the exported controller frames in Bug A's dump (notably
# ull_conn_update_parameters, the faulting divide site).
#
# Leaves build-multibug/testbinary. Separate build dir; the other build dirs are untouched. Idempotent; re-uses the
# clone + SDK. Run: bash scripts/build-multibug.sh
set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"
WS="${HARNESS_WS:-$WS_DEFAULT}"
T="tests/bluetooth/controller/ctrl_conn_update/src/main.c"
GUARD="subsys/bluetooth/controller/ll_sw/ull_llcp_conn_upd.c"
TESTDIR="tests/bluetooth/controller/ctrl_conn_update"
PATCH="multibug.patch"
BUILD_DIR="build-multibug"
LINK_FLAGS="-rdynamic"
mkdir -p "$WS"
cp "$HERE/patches/multibug-harness.patch" "$WS/$PATCH"

VERIFY=$(cat <<'EOF'
# Helper: run one (HARNESS_BUG,HARNESS_SUBSET); never abort under set -e (binary exits nonzero on crash AND on
# the pre-existing ztest failures). Key on the exit code: A=136 (SIGFPE), C=255 (LL_ASSERT), else 1.
run() { local b="$1" m="$2" e; if HARNESS_BUG="$b" HARNESS_SUBSET="$m" "$BIN" >/dev/null 2>&1; then e=0; else e=$?; fi; echo "$e"; }

echo "### two-bug binary: build-multibug/testbinary (the other build dirs are left untouched) ###"

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
EOF
)
build_harness

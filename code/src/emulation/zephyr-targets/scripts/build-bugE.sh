#!/usr/bin/env bash
# Bug E — build the subset-selectable data-length-update doubled-LL_LENGTH_REQ assert oracle binary on the
# vulnerable Zephyr LL controller and verify its channel-off exhaustive sweep + true 2-minimal.
#
# The harness (patches/bugE-dle-harness.patch) adds one ZTEST (test_bug_e) to the ctrl_data_length_update
# suite; a no-op unless selected by env HARNESS_BUG=E (whole suite, no per-test CLI filter, selection by
# getenv -- the existing PROBE_ID pattern). HARNESS_SUBSET is a bitmask over the LL-PDU window.
#
#   HARNESS_BUG=E  test_bug_e: doubled LL_LENGTH_REQ assert. The same retained-rx-node mechanism as bugs C
#             and D (a retained NODE_RX reused as the procedure NTF with no fallback alloc) but a distinct
#             crash site. Built verbatim on the known-good test_data_length_update_periph_rem with a
#             conditional 2nd LL_LENGTH_REQ injected in its own event. REQ#1 starts rp_comm(DATA_LENGTH) and
#             retains node_ref.rx; REQ#2, dispatched to the head ctx by llcp_rr_rx, overwrites and clears it;
#             at the tx-ack rp_comm_ntf (ull_llcp_common.c:1138) the NULL node hits LL_ASSERT(ntf) -> mocked
#             bt_ctlr_assert_handle -> exit(-1). 5-bit window: bits0..2 = transparent decoys, bit3 =
#             LL_LENGTH_REQ #1, bit4 = LL_LENGTH_REQ #2 (load-bearing). Channel-off true 2-minimal =
#             {REQ1,REQ2} = 24 (0x18). The assert emits its own message (ASSERTION FAIL [ntf] @
#             ull_llcp_common.c:1138); no SIGFPE handler needed. Python rc 255 / shell 255.
#
# -rdynamic is passed for parity with the other bug scripts; Bug E reproduces identically without it (the
# assert message is the artifact, not a backtrace).
#
# Leaves build-dle/testbinary. Separate build dir; /work/build and the other build-* dirs are untouched.
# Idempotent; re-uses the clone + SDK. Run: bash scripts/build-bugE.sh
set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"
WS="${HARNESS_WS:-$WS_DEFAULT}"
T="tests/bluetooth/controller/ctrl_data_length_update/src/main.c"
GUARD="subsys/bluetooth/controller/ll_sw/ull_llcp_common.c"
TESTDIR="tests/bluetooth/controller/ctrl_data_length_update"
PATCH="bugE.patch"
BUILD_DIR="build-dle"
LINK_FLAGS="-rdynamic"
mkdir -p "$WS"
cp "$HERE/patches/bugE-dle-harness.patch" "$WS/$PATCH"

VERIFY=$(cat <<'EOF'
# Helper: run one HARNESS_SUBSET; never abort under set -e. Key on the exit code: E=255 (LL_ASSERT -> exit(-1)).
run() { local m="$1" e; if HARNESS_BUG=E HARNESS_SUBSET="$m" "$BIN" >/dev/null 2>&1; then e=0; else e=$?; fi; echo "$e"; }

echo "### Bug E binary: build-dle/testbinary (other build dirs left untouched) ###"
echo "--- Bug E: channel-OFF exhaustive sweep (5-bit window) -> crash(255) <=> BOTH LENGTH_REQ bits (0x18) ---"
cnt=0; bad=0
for m in $(seq 0 31); do
  e=$(run "$m")
  if [ "$e" = "255" ]; then cnt=$((cnt+1)); [ $((m & 24)) -ne 24 ] && bad=1; fi
done
echo "    crashing subsets = $cnt / 32 (expect 8 = supersets of {REQ1,REQ2}); all crashers hold both REQs: $([ $bad -eq 0 ] && echo YES || echo NO)"
echo "    true 2-minimal {REQ1,REQ2}=24 (0x18): exit=$(run 24) (expect 255)"
echo "    each 1-smaller subset benign: {REQ1}=8 exit=$(run 8), {REQ2}=16 exit=$(run 16) (expect non-255)"
echo "    decoy transparency (each decoy + both REQs still crashes): 0x19=$(run 25) 0x1A=$(run 26) 0x1C=$(run 28) all3+REQs 0x1F=$(run 31) (expect 255 each)"
echo "    decoys alone benign (never 255): 0x01=$(run 1) 0x07=$(run 7) empty=0=$(run 0)"
echo "    determinism (3x on 24): $(run 24) $(run 24) $(run 24)"

echo "### example dump (HARNESS_BUG=E HARNESS_SUBSET=24) — controller assert message ###"
HARNESS_BUG=E HARNESS_SUBSET=24 "$BIN" 2>&1 | grep -E "Running TESTSUITE dle|ull_llcp_common\.c:1138"
EOF
)
build_harness

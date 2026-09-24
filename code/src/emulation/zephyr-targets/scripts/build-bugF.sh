#!/usr/bin/env bash
# Bug F — build the subset-selectable cis-create CIS_ESTABLISHED-ntf assert oracle binary on the vulnerable
# Zephyr LL controller and verify its channel-off exhaustive sweep + true 2-minimal.
#
# The harness (patches/bugF-cis-harness.patch) adds one ZTEST (test_bug_f) to the ctrl_cis_create suite;
# a no-op unless selected by env HARNESS_BUG=F (whole suite, no per-test CLI filter, selection by getenv --
# the existing PROBE_ID pattern). HARNESS_SUBSET is a bitmask over the LL-PDU window.
#
#   HARNESS_BUG=F  test_bug_f: doubled LL_CIS_IND assert. The same retained-rx-node mechanism as bugs C, D
#             and E but a distinct crash site. Built verbatim on the known-good
#             test_cc_create_periph_rem_host_accept with a conditional 2nd LL_CIS_IND injected in its own
#             event while the peripheral rp_cc procedure is in RP_CC_STATE_WAIT_INSTANT. CIS_IND #1 retains
#             ctx->node_ref.rx (llcp_rx_node_retain, ull_llcp_cc.c:408) for the deferred CIS_ESTABLISHED
#             host notification; CIS_IND #2, routed to the head ctx (ull_llcp.c:1792-1798) and stored by
#             llcp_rr_rx (ull_llcp_remote.c:240) over the retained pointer, is dropped by the WAIT_INSTANT
#             handler (default: break), and llcp_rr_rx then clears node_ref.rx -> NULL
#             (ull_llcp_remote.c:318-319); ctx->done stays 0 so the procedure survives. At the explicit
#             established trigger, cc_ntf_established (ull_llcp_cc.c:64) reads the NULL node -> LL_ASSERT(ntf)
#             -> mocked bt_ctlr_assert_handle -> exit(-1). One IND alone stays clean. iso_interval stays 6
#             (remote_cis_req default) so the CIS_RSP divide (ull_llcp_cc.c:177) is non-zero -> this is the
#             :64 assert (255), not bug B's SIGFPE (136). 5-bit window: bits0..2 = transparent decoys,
#             bit3 = CIS_IND #1, bit4 = CIS_IND #2 (load-bearing). Channel-off true 2-minimal = {IND1,IND2}
#             = 24 (0x18). Python rc 255 / shell 255.
#
# -rdynamic is passed for parity with the other bug scripts; Bug F reproduces identically without it (the
# assert message is the artifact, not a backtrace).
#
# Leaves build-cisc/testbinary (separate from B's build-cis, the CIS SIGFPE in the same suite). /work/build
# and the other build-* dirs are untouched. Idempotent; reuses the clone + SDK. Run: bash scripts/build-bugF.sh
set -euo pipefail
# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
. "$(dirname "$0")/common.sh"
WS="${HARNESS_WS:-$WS_DEFAULT}"
T="tests/bluetooth/controller/ctrl_cis_create/src/main.c"
GUARD="subsys/bluetooth/controller/ll_sw/ull_llcp_cc.c"
TESTDIR="tests/bluetooth/controller/ctrl_cis_create"
PATCH="bugF.patch"
BUILD_DIR="build-cisc"
LINK_FLAGS="-rdynamic"
mkdir -p "$WS"
cp "$HERE/patches/bugF-cis-harness.patch" "$WS/$PATCH"

VERIFY=$(cat <<'EOF'
# Helper: run one HARNESS_SUBSET; never abort under set -e. Key on the exit code: F=255 (LL_ASSERT -> exit(-1)).
run() { local m="$1" e; if HARNESS_BUG=F HARNESS_SUBSET="$m" "$BIN" >/dev/null 2>&1; then e=0; else e=$?; fi; echo "$e"; }

echo "### Bug F binary: build-cisc/testbinary (the other build dirs are left untouched) ###"
echo "--- Bug F: channel-OFF exhaustive sweep (5-bit window) -> crash(255) <=> BOTH CIS_IND bits (0x18) ---"
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

echo "### example dump (HARNESS_BUG=F HARNESS_SUBSET=24) — controller assert message ###"
HARNESS_BUG=F HARNESS_SUBSET=24 "$BIN" 2>&1 | grep -E "Running TESTSUITE cis_create|ull_llcp_cc\.c:64"
[ "$bad" -eq 0 ] || { echo "### VERIFY FAILED: the truth table does not hold ###"; exit 1; }
EOF
)
build_harness
